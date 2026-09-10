"""Tests for scripts/check_agent_migration_sweep.py (#1041/#1042 再発防止).

保護機構は不発でも green になるため、本テストは **違反を注入して exit code の
生値を観測する** 形で書く (`test_check_doc_code_refs.py` / `test_check_changelog_style.py`
と同じ規律)。正常系だけを見て「ガードがある」と判断しない。

本 file が特に固定するのは **scope** である:
- 検査対象 = living doc (`.md` / `.sh` の doc / skill / hook / AGENTS.md / README)。
- コードファイル (`.py` / `.js` / `.ts` / `.rs` / `.ps1` / `.yml`)、CHANGELOG、
  eval レポート、dated plans・specs、archive、audits、GUI ソースは対象外 (#1044)。
- slash command の正規表現は path / branch 名の `/release` 等を誤検出しない
  (`(?<![a-z0-9._-])` + `(?![a-z0-9._-])` の前後境界)。
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_agent_migration_sweep.py"

_spec = importlib.util.spec_from_file_location(
    "check_agent_migration_sweep", SCRIPT_PATH
)
assert _spec is not None and _spec.loader is not None
guard = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = guard
_spec.loader.exec_module(guard)


# --------------------------------------------------------------------------
# regex: slash command 検出 vs path 誤検出
# --------------------------------------------------------------------------

# (label, text) -- いずれも「slash command を検出する」べき。
_SLASH_POSITIVE: list[tuple[str, str]] = [
    ("backtick", "実行時は `/review-pr` を呼ぶ"),
    ("space-wrapped", "-> /release [patch|minor|major] で bump"),
    ("leading", "/iterate-review <PR#> で処理"),
    ("paren", "(/scope-guard を呼ぶ)"),
]

# (label, text) -- いずれも「slash command と誤検出してはならない」。
_SLASH_NEGATIVE: list[tuple[str, str]] = [
    ("skill-dir-path", "参照: `.agents/skills/review-pr/SKILL.md`"),
    ("branch-name", "push run (`github.ref=refs/heads/release/vX`)"),
    ("url-path", "https://img.shields.io/github/v/release/Idios/x"),
    ("cargo-target", "# gui/src-tauri/target/release/allaganeye-gui.exe"),
]


@pytest.mark.parametrize(("label", "text"), _SLASH_POSITIVE, ids=lambda v: str(v)[:24])
def test_slash_command_is_detected(label: str, text: str) -> None:
    assert guard._SLASH_RE.search(text), f"{label} が slash command と見なされなかった"


@pytest.mark.parametrize(("label", "text"), _SLASH_NEGATIVE, ids=lambda v: str(v)[:24])
def test_path_like_slash_is_not_detected(label: str, text: str) -> None:
    assert guard._SLASH_RE.search(text) is None, (
        f"{label} が slash command と誤検出された: {guard._SLASH_RE.search(text)}"
    )


def test_slash_skills_list_is_non_empty() -> None:
    assert guard._SLASH_SKILLS, "_SLASH_SKILLS が空"


def test_literal_terms_list_is_non_empty() -> None:
    assert guard._LITERAL_TERMS, "_LITERAL_TERMS が空"


def test_codex_old_terms_list_is_non_empty() -> None:
    assert guard._CODEX_OLD_TERMS, "_CODEX_OLD_TERMS が空 (#1043)"


def test_codex_old_terms_cover_invocation_contract() -> None:
    """Codex 呼び出し契約の旧表記 (companion script / plugin path / env var) を覆う。"""
    assert "codex-companion.mjs" in guard._CODEX_OLD_TERMS
    assert "CLAUDE_PLUGIN_ROOT" in guard._CODEX_OLD_TERMS
    assert ".claude/plugins" in guard._CODEX_OLD_TERMS


# --------------------------------------------------------------------------
# scope: 検査対象 (living doc) vs 除外 (historical / deferred)
# --------------------------------------------------------------------------


def _make_repo(tmp_path: Path) -> None:
    """最小の repo 骨格を作る (AGENTS.md が必須 anchor)。"""
    (tmp_path / "AGENTS.md").write_text("# Allagan Eye\n", encoding="utf-8")


def _run_repo(repo_root: Path) -> int:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--repo-root", str(repo_root)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    return result.returncode


def test_clean_repo_passes(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "versioning.md").write_text(
        "# バージョニング\n", encoding="utf-8"
    )
    assert _run_repo(tmp_path) == 0


def test_living_doc_slash_command_is_exit_1(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "versioning.md").write_text(
        "# バージョニング\n\n`/release` で bump する。\n", encoding="utf-8"
    )
    assert _run_repo(tmp_path) == 1


def test_living_doc_old_path_is_exit_1(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text(
        "# Guide\n\n`.claude/skills/` を参照。\n", encoding="utf-8"
    )
    assert _run_repo(tmp_path) == 1


def test_living_doc_codex_companion_is_exit_1(tmp_path: Path) -> None:
    """Codex 呼び出し契約の旧表記 (codex-companion.mjs) 残存は exit 1 (#1043)。"""
    _make_repo(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text(
        "# Guide\n\n`codex-companion.mjs` を実行。\n", encoding="utf-8"
    )
    assert _run_repo(tmp_path) == 1


def test_hook_file_is_scanned(tmp_path: Path) -> None:
    """hook (session-start.sh) の slash 残存も検出する (Round 5 の再発事象)。"""
    _make_repo(tmp_path)
    (tmp_path / ".claude" / "hooks").mkdir(parents=True)
    (tmp_path / ".claude" / "hooks" / "session-start.sh").write_text(
        "cat <<'EOF'\n- `/review-pr` 実行時は...\nEOF\n", encoding="utf-8"
    )
    assert _run_repo(tmp_path) == 1


def test_changelog_is_excluded(tmp_path: Path) -> None:
    """CHANGELOG の旧 slash 表記は歴史記録 (既リリース節) なので対象外。"""
    _make_repo(tmp_path)
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n- `/close-issue` skill 新設 (#594)\n", encoding="utf-8"
    )
    assert _run_repo(tmp_path) == 0


def test_code_file_is_excluded(tmp_path: Path) -> None:
    """コードファイルのコメント旧参照は #1044 (コードコメント棚卸) 対象外。"""
    _make_repo(tmp_path)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "check_version_consistency.py").write_text(
        "# `/release` の手元実行が壊れる。\n", encoding="utf-8"
    )
    assert _run_repo(tmp_path) == 0


def test_gui_source_is_excluded(tmp_path: Path) -> None:
    """GUI ソースの `CLAUDE.md` 参照は screenshot-freshness 回避で #1044 に defer。"""
    _make_repo(tmp_path)
    (tmp_path / "gui" / "src").mkdir(parents=True)
    (tmp_path / "gui" / "src" / "store.ts").write_text(
        "// Windows-only (see CLAUDE.md).\n", encoding="utf-8"
    )
    assert _run_repo(tmp_path) == 0


def test_eval_report_is_excluded(tmp_path: Path) -> None:
    """skill eval レポートの `.claude/skills` 参照は歴史記録 (棚卸 #1044) 対象外。"""
    _make_repo(tmp_path)
    (tmp_path / ".agents" / "skills" / "review-pr" / "eval" / "reports").mkdir(
        parents=True
    )
    (
        tmp_path / ".agents" / "skills" / "review-pr" / "eval" / "reports" / "r.md"
    ).write_text("# 対象 `.claude/skills/review-pr/SKILL.md`\n", encoding="utf-8")
    assert _run_repo(tmp_path) == 0


# --------------------------------------------------------------------------
# exit 2: 検査自体が壊れている
# --------------------------------------------------------------------------


def test_missing_agents_md_is_exit_2(tmp_path: Path) -> None:
    """anchor (AGENTS.md) 不在は「検査対象を特定できない」ので exit 2。"""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "versioning.md").write_text(
        "# バージョニング\n", encoding="utf-8"
    )
    assert _run_repo(tmp_path) == 2


# --------------------------------------------------------------------------
# 実物との統合
# --------------------------------------------------------------------------


def test_repo_sweep_passes() -> None:
    """repo の実 living doc が規約を満たす (CI が見るのと同じ経路)。"""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
