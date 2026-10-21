"""Tests for scripts/check_agent_migration_sweep.py (#1041/#1042 再発防止).

保護機構は不発でも green になるため、本テストは **違反を注入して exit code の
生値を観測する** 形で書く (`test_check_doc_code_refs.py` / `test_check_changelog_style.py`
と同じ規律)。正常系だけを見て「ガードがある」と判断しない。

本 file が特に固定するのは **scope** である:
- 検査対象 = living doc (`.md` / `.sh` の doc / skill / hook / AGENTS.md / README)。
- コードファイル (`.py` / `.js` / `.ts` / `.rs` / `.ps1` / `.yml`) は `_SCAN_EXTS` の
  allowlist (living doc のみ) により対象外。CHANGELOG、eval fixture
  (`.agents/skills/**/eval/**`)、`docs/superpowers/**` (dated 以外も含む)、
  archive、audits、GUI ソース、`build-cache/` は対象外 (#1044)。
- コードコメントの旧参照は #1076 で追跡する (#1044 は未参照ファイルの削除が範囲)。
- `.claude/agents/**` は Claude Code 用のロール定義 (`model:` frontmatter が Claude
  エイリアスのみ) のため対象外 (旧 invocation 契約は #1068)。
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


# --------------------------------------------------------------------------
# regex: 主エージェント=Claude の旧表記 検出 vs 維持対象の誤検出 (#1066)
# --------------------------------------------------------------------------

# (label, text) -- いずれも「主エージェント=Claude の旧表記を検出する」べき。
_CLAUDE_AGENT_POSITIVE: list[tuple[str, str]] = [
    ("subject-ha", "Claude は自動的に段階を進め、要所で判断を仰ぐ"),
    ("subject-ga", "Claude が `gh` コマンドを発行する"),
    ("possessive-no", "ユーザーが Claude の判断を訂正した場合、蓄積する"),
    ("host-uchi", "Stage 1: Claude 内 fresh subagent が実装"),
    ("main", "Stage 2: controller (Claude main) が到達確認"),
    ("thinking-body", "superpowers subagent (Claude 思考体) と Codex"),
    ("code-fallback", "Claude Code fallback は同一 model の self-review に近い"),
    ("fallback-de", "(B) Claude fallback で push する"),
    ("fallback-ha", "Claude fallback は同一 model の self-review に近い"),
    ("fallback-slash", "(再試行 / Claude fallback / abort) 3 択"),
    ("paren-eq-plus", "エージェント (= Claude + 人間メンテナ Idios) が手動で実行する"),
    (
        "code-session-ugoku",
        "メンテナ (= Claude Code セッションで動くアシスタント) が受領する",
    ),
    ("code-no-plan", "Claude Code の plan モード (ExitPlanMode ツール) を活用し"),
    # tradeoff pin: 主語形は助詞のみで判定するため、維持対象の文脈でも検出される
    # (FP 側に倒す設計)。narrow 化が silent に入らないよう現挙動を pin する。
    (
        "claude-maintenance-context-tradeoff",
        "Claude が復旧したら再レビューを依頼する",
    ),
]

# (label, text) -- いずれも「誤検出してはならない」維持対象 (レビュー専用ツール / 製品名)。
_CLAUDE_AGENT_NEGATIVE: list[tuple[str, str]] = [
    (
        "claude-code",
        "Claude Code / Fable / Kimi Code は別途セッションを起動して利用する",
    ),
    ("claude-fable", "全体レビュー・相談は Claude Fable 最新に依頼する"),
    ("claude-sonnet", "中難度定型は Claude Sonnet 最新 / DeepSeek V4 Flash"),
    (
        "claude-design",
        "Claude Design (claude.ai/design) からエクスポートされた handoff bundle",
    ),
    (
        "fallback-notice",
        "> **Claude fallback notice**: 本成果物のレビューは Claude 不可のため DeepSeek が代行した",
    ),
    ("section-heading", "## Claude fallback（Claude レビュー不可時）"),
    (
        "claude-opus-fable",
        "Claude（Opus / Fable）復旧後に再レビューしてから merge する",
    ),
    ("codex-independent", "Codex 本体は Claude と独立である"),
    ("claude-kaifuku", "Claude 復旧後の再レビューを推奨する"),
    (
        "claude-review-noun",
        "Claude レビューが使えない状況で DeepSeek がレビューを代行した",
    ),
    ("claude-code-slash", "Claude Code のスラッシュコマンドは invoke 不可"),
    ("claude-code-subagent", "DeepSeek は Claude Code の subagent になれない"),
    ("claude-code-session-review", "別途 Claude Code セッションで review 依頼"),
    ("claude-ni-review", "Claude に再レビューを依頼する"),
    ("claude-no-review", "Claude のレビュー結果を突合する"),
    ("claude-no-rereview", "Claude の再レビューを推奨する"),
    ("claude-no-usage", "Claude の usage limit 時"),
    ("claude-no-permission", "Claude の permission prompt を表示する"),
    ("claude-no-session", "Claude のセッション起動"),
    ("claude-no-memory", "Claude の auto-memory"),
    ("claude-no-slash", "Claude のスラッシュコマンド"),
    # whitelist の残り 7 語 (#1066 Round 2)。whitelist は FP 抑制の唯一の契約なので、
    # 各語が実際に branch を抑止することを pin する。
    ("claude-no-kaifuku", "Claude の復旧を待つ"),
    ("claude-no-fuka", "Claude の不可時は DeepSeek が代行する"),
    ("claude-no-code-interpreter", "Claude の Code Interpreter を使う"),
    ("claude-no-fable", "Claude の Fable 最新版に依頼する"),
    ("claude-no-sonnet", "Claude の Sonnet 環境で実行する"),
    ("claude-no-opus", "Claude の Opus モデルを選ぶ"),
    ("claude-no-design", "Claude の Design 資料を参照する"),
]


@pytest.mark.parametrize(("label", "text"), _SLASH_POSITIVE, ids=lambda v: str(v)[:24])
def test_slash_command_is_detected(label: str, text: str) -> None:
    assert guard._SLASH_RE.search(text), f"{label} が slash command と見なされなかった"


@pytest.mark.parametrize(("label", "text"), _SLASH_NEGATIVE, ids=lambda v: str(v)[:24])
def test_path_like_slash_is_not_detected(label: str, text: str) -> None:
    assert guard._SLASH_RE.search(text) is None, (
        f"{label} が slash command と誤検出された: {guard._SLASH_RE.search(text)}"
    )


@pytest.mark.parametrize(
    ("label", "text"), _CLAUDE_AGENT_POSITIVE, ids=lambda v: str(v)[:24]
)
def test_claude_agent_old_term_is_detected(label: str, text: str) -> None:
    assert guard._CLAUDE_AGENT_RE.search(text), (
        f"{label} が主エージェント=Claude の旧表記と見なされなかった"
    )


@pytest.mark.parametrize(
    ("label", "text"), _CLAUDE_AGENT_NEGATIVE, ids=lambda v: str(v)[:24]
)
def test_kept_claude_term_is_not_detected(label: str, text: str) -> None:
    assert guard._CLAUDE_AGENT_RE.search(text) is None, (
        f"{label} が主エージェント=Claude の旧表記と誤検出された: "
        f"{guard._CLAUDE_AGENT_RE.search(text)}"
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


def _run_repo_result(repo_root: Path) -> subprocess.CompletedProcess[str]:
    """checker を subprocess で起動し、exit code と stdout / stderr を返す。"""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--repo-root", str(repo_root)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


def _run_repo(repo_root: Path) -> int:
    return _run_repo_result(repo_root).returncode


def test_runtime_messages_are_pinned(tmp_path: Path) -> None:
    """実行時メッセージの header / hint 文言を pin する (#1066)。

    宣言 (docstring / `ci.yml` comment) と発火側の文言が乖離すると、違反時に
    保守者が誤った原因を読む。文言の revert が silent に通らないようにする。
    """
    _make_repo(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "old.md").write_text(
        "Claude は自動的に段階を進める。\n", encoding="utf-8"
    )
    result = _run_repo_result(tmp_path)
    assert result.returncode == 1
    assert "旧用語残存 または 検査不能" in result.stderr
    assert "Zed + DeepSeek" in result.stderr
    # per-violation label と `.claude/agents/**` の帰属行 (#1068) も pin する
    assert "主エージェント=Claude の旧表記残存" in result.stderr
    assert "#1068" in result.stderr
    # hint の除外列挙も pin する (宣言側 drift を止める)
    assert "archive / audits" in result.stderr
    assert ".claude/agents/**" in result.stderr


def test_declarations_name_the_detection_classes() -> None:
    """宣言 (module docstring / `ci.yml` comment) が検出 class を名指ししていることを pin する。

    発火側 (実行時文言) だけでなく宣言側の drift も止める (#1073 AC4)。
    `AGENTS.md` 側の追補は Phase 2 (PR-B) で扱う。
    """
    assert "主エージェント=Claude" in (guard.__doc__ or "")
    assert "Codex 旧表記" in (guard.__doc__ or "")
    assert "検査不能 (fail-closed)" in (guard.__doc__ or "")

    ci_yml = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    assert "主エージェント=Claude" in ci_yml
    assert "Codex 旧表記" in ci_yml
    assert "検査不能 (fail-closed)" in ci_yml


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


def test_living_doc_claude_agent_old_term_is_exit_1(tmp_path: Path) -> None:
    """主エージェント=Claude の旧表記残存は exit 1 (#1066)。"""
    _make_repo(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text(
        "# Guide\n\nClaude は自動的に段階を進め、要所で判断を仰ぐ。\n",
        encoding="utf-8",
    )
    assert _run_repo(tmp_path) == 1


def test_living_doc_kept_claude_terms_pass(tmp_path: Path) -> None:
    """維持対象 (Claude Code / Fable / Design / fallback notice) は exit 0 (#1066)。"""
    _make_repo(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text(
        "# Guide\n\nClaude Code / Claude Fable / Claude Design をレビュー専用とする。\n"
        "> **Claude fallback notice**: 本成果物のレビューは Claude 不可のため代行した。\n",
        encoding="utf-8",
    )
    assert _run_repo(tmp_path) == 0


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
    """コードファイルのコメント旧参照は #1076 で追跡するため対象外。"""
    _make_repo(tmp_path)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "check_version_consistency.py").write_text(
        "# `/release` の手元実行が壊れる。\n", encoding="utf-8"
    )
    assert _run_repo(tmp_path) == 0


def test_gui_source_is_excluded(tmp_path: Path) -> None:
    """`gui/**` 配下は `.md` でも検査対象外 (screenshot-freshness 回避、#1044)。"""
    _make_repo(tmp_path)
    (tmp_path / "gui" / "src").mkdir(parents=True)
    (tmp_path / "gui" / "src" / "README.md").write_text(
        "Claude は自動的に段階を進める。\n", encoding="utf-8"
    )
    assert _run_repo(tmp_path) == 0


def test_docs_archive_is_excluded(tmp_path: Path) -> None:
    """`docs/archive/**` は履歴記録として検査対象外 (#1044)。"""
    _make_repo(tmp_path)
    (tmp_path / "docs" / "archive").mkdir(parents=True)
    (tmp_path / "docs" / "archive" / "old.md").write_text(
        "Claude は自動的に段階を進める。\n", encoding="utf-8"
    )
    assert _run_repo(tmp_path) == 0


def test_build_cache_dir_is_skipped(tmp_path: Path) -> None:
    """`build-cache/` は Portable ZIP の build キャッシュ置き場なので検査対象外 (#1066)。

    red 実証の展開先は repo 外を推奨するが、repo 内に置かれた場合の false red を
    防ぐため `_SKIP_DIRS` で除外する。
    """
    _make_repo(tmp_path)
    (tmp_path / "build-cache" / "old").mkdir(parents=True)
    (tmp_path / "build-cache" / "old" / "old.md").write_text(
        "Claude は自動的に段階を進める。\n", encoding="utf-8"
    )
    assert _run_repo(tmp_path) == 0


def test_claude_agents_dir_is_excluded(tmp_path: Path) -> None:
    """`.claude/agents/**` は Claude Code 用ロール定義なので除外する (#1066)。"""
    _make_repo(tmp_path)
    (tmp_path / ".claude" / "agents").mkdir(parents=True)
    (tmp_path / ".claude" / "agents" / "role.md").write_text(
        "Claude は自動的に段階を進める。\n", encoding="utf-8"
    )
    assert _run_repo(tmp_path) == 0


def test_eval_report_is_excluded(tmp_path: Path) -> None:
    """skill eval fixture の `.claude/skills` 参照は eval fixture 全体の除外により対象外。

    残置の追跡先は #1068。
    """
    _make_repo(tmp_path)
    (tmp_path / ".agents" / "skills" / "review-pr" / "eval" / "reports").mkdir(
        parents=True
    )
    (
        tmp_path / ".agents" / "skills" / "review-pr" / "eval" / "reports" / "r.md"
    ).write_text("# 対象 `.claude/skills/review-pr/SKILL.md`\n", encoding="utf-8")
    assert _run_repo(tmp_path) == 0


def test_eval_requirements_is_excluded(tmp_path: Path) -> None:
    """`.agents/skills/**/eval/**` は fixture 全体 (requirements.md 含む) を除外する (#1066)。"""
    _make_repo(tmp_path)
    (tmp_path / ".agents" / "skills" / "review-pr" / "eval").mkdir(parents=True)
    (
        tmp_path / ".agents" / "skills" / "review-pr" / "eval" / "requirements.md"
    ).write_text("# 要件\n\nClaude は自動的に段階を進める。\n", encoding="utf-8")
    assert _run_repo(tmp_path) == 0


def test_undecodable_living_doc_is_exit_1(tmp_path: Path) -> None:
    """living doc (.md) が utf-8 decode 不能なら検査不能 = fail-closed (exit 1) (#1066)。"""
    _make_repo(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "bad.md").write_bytes(b"\xff\xfe\x00 broken")
    result = _run_repo_result(tmp_path)
    assert result.returncode == 1
    # 見出しが「旧用語残存」だけを原因として提示しない (検査不能も exit 1 の原因) (#1066)
    assert "bad.md: 検査不能" in result.stderr


def test_read_oserror_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """read 時の `OSError` も検査不能 = fail-closed で違反として扱う (#1066)。

    subprocess では `OSError` を再現しにくいため、本 file で唯一 in-process で
    `Path.read_text` を差し替えて分岐を pin する。
    """
    _make_repo(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "unreadable.md").write_text("# ok\n", encoding="utf-8")

    original_read_text = Path.read_text

    def _fail_on_unreadable(self, *args, **kwargs):
        if self.name == "unreadable.md":
            raise OSError("simulated read failure")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _fail_on_unreadable)
    violations = guard.check_sweep(tmp_path)
    assert any("unreadable.md: 検査不能" in v for v in violations)


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
