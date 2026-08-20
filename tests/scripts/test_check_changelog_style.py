"""Tests for scripts/check_changelog_style.py (#952).

保護機構は不発でも green になるため、本テストは **違反を注入して exit code の
生値を観測する** 形で書く (`tests/scripts/test_check_doc_code_refs.py` /
`test_check_version_consistency.py` と同じ規律)。正常系だけを見て
「ガードがある」と判断しない。

本 file が特に固定するのは **scope** である。この検査は `## [Unreleased]` (無い
場合は最新 version セクション) だけを走査し、既リリース済みセクションは見ない
(裁定 D7 の既リリース節不可侵)。scope を切り忘れると v0.3.0 の `### Added` が
恒久 red になり、逆に scope を広げすぎると「0 件と 0 件が一致した」で自己崩壊
した検査を緑で通してしまう。両側を parametrize で常駐させる。

`_FALSE_RED` 群は「規約が推奨している書き方」を red にしないことを固定する。
規約 (`docs/release-process.md` の CHANGELOG entry の記述規約) は詳細を spec への
リンクで送れと書いており、その spec の **ファイル名自体に内部段階名が入っている**
(実在例: `docs/superpowers/specs/2026-07-11-issue-822-masked-oversplit-anchor-design.md`
は `anchor` を含む)。リンク先を検査対象にすると規約が自分の推奨を罰する。
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_changelog_style.py"

_spec = importlib.util.spec_from_file_location("check_changelog_style", SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
guard = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = guard
_spec.loader.exec_module(guard)


_HEADER = """# Changelog

All notable changes to this project will be documented in this file.

"""

_RELEASED = """## [0.3.0] - 2026-08-04

### Added

- **`--vtuber`** (#895): V0 anchor 解決 / V2 粗 segmentation / V3 gap merge。
  presence quorum と tri-state で判定する。

### Internal

- 内部作業の記録 (#844)。
"""


def _write(tmp_path: Path, unreleased: str | None, released: str = _RELEASED) -> Path:
    """CHANGELOG.md を組み立てる。``unreleased`` が None なら節自体を置かない。"""
    body = _HEADER
    if unreleased is not None:
        body += f"## [Unreleased]\n\n{unreleased}\n"
    body += released
    path = tmp_path / "CHANGELOG.md"
    path.write_text(body, encoding="utf-8")
    return path


def _run(changelog: Path) -> subprocess.CompletedProcess[str]:
    """script を subprocess で回し exit code の生値を得る。

    `PYTHONIOENCODING=utf-8` を渡すのは、違反報告が日本語なため。Windows の
    既定 code page (cp932) だと child の stderr が cp932 で符号化され、UTF-8 で
    読む側が `UnicodeDecodeError` で落ちて **exit code の観測前にテストが死ぬ**
    (実測)。CI (ubuntu) は既定 UTF-8 なのでこの差は本番挙動には現れない。
    """
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--changelog", str(changelog)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


# --------------------------------------------------------------------------
# 正常系
# --------------------------------------------------------------------------


def test_clean_unreleased_section_passes(tmp_path: Path) -> None:
    changelog = _write(
        tmp_path,
        "### Changed\n\n- 配布 ZIP に同梱する依存の版を固定した (#916)。\n",
    )
    result = _run(changelog)
    assert result.returncode == 0, result.stdout + result.stderr


def test_empty_unreleased_section_passes(tmp_path: Path) -> None:
    """節はあるが entry がまだ無い状態は違反ではない (PR-B2 直後の状態)。"""
    changelog = _write(tmp_path, "")
    assert _run(changelog).returncode == 0


# --------------------------------------------------------------------------
# V1: 禁止内部用語 -- 違反注入で exit 1 を生値観測
# --------------------------------------------------------------------------

_FORBIDDEN_SAMPLES: list[tuple[str, str]] = [
    ("V0", "- V0 anchor の解決を改善した (#1)。"),
    ("V3", "- V3 の gap merge 裁定を変更した (#1)。"),
    ("quorum", "- quorum 判定のしきい値を変えた (#1)。"),
    ("anchor", "- anchor の再解決を追加した (#1)。"),
    ("presence", "- presence 判定を tri-state 化した (#1)。"),
    ("tri-state", "- 判定を tri-state に変更した (#1)。"),
]


@pytest.mark.parametrize(
    ("label", "entry"), _FORBIDDEN_SAMPLES, ids=lambda v: str(v)[:24]
)
def test_forbidden_term_in_unreleased_is_exit_1(
    tmp_path: Path, label: str, entry: str
) -> None:
    changelog = _write(tmp_path, f"### Changed\n\n{entry}\n")
    result = _run(changelog)
    assert result.returncode == 1, (
        f"{label} を含む entry が緑で通った: {result.stdout + result.stderr}"
    )
    assert label in result.stdout + result.stderr


# --------------------------------------------------------------------------
# V2: `### Internal` 節 -- 新規バージョンでは使わない (裁定 R9)
# --------------------------------------------------------------------------


def test_internal_section_in_unreleased_is_exit_1(tmp_path: Path) -> None:
    changelog = _write(tmp_path, "### Internal\n\n- CI job を足した (#1)。\n")
    result = _run(changelog)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Internal" in result.stdout + result.stderr


def test_internal_section_in_released_section_is_ignored(tmp_path: Path) -> None:
    """既リリース節の `### Internal` は歴史記録として残す (遡って直さない)。"""
    changelog = _write(tmp_path, "### Changed\n\n- 出力先の表示を変えた (#1)。\n")
    assert _run(changelog).returncode == 0


# --------------------------------------------------------------------------
# scope: 既リリース済みセクションは走査しない
# --------------------------------------------------------------------------


def test_released_section_forbidden_terms_are_ignored(tmp_path: Path) -> None:
    """v0.3.0 の `### Added` は実測で内部用語を 14 箇所含む。scope を切らないと
    恒久 red になる。"""
    changelog = _write(tmp_path, "### Changed\n\n- 表示を変えた (#1)。\n")
    result = _run(changelog)
    assert result.returncode == 0, result.stdout + result.stderr


def test_latest_version_section_is_scanned_when_no_unreleased(tmp_path: Path) -> None:
    """`## [Unreleased]` が無いときは最新 version セクションを見る。

    PR-D1 が `## [Unreleased]` を `## [0.3.1] - <date>` に改名した後も検査が
    継続することの担保。ここが抜けると release 直前の 1 手で無検査になる。
    """
    released = (
        "## [0.3.1] - 2026-08-20\n\n### Changed\n\n"
        "- presence 判定を変更した (#1)。\n\n" + _RELEASED
    )
    changelog = _write(tmp_path, None, released=released)
    result = _run(changelog)
    assert result.returncode == 1, result.stdout + result.stderr


def test_only_one_section_is_scanned(tmp_path: Path) -> None:
    """`## [Unreleased]` があるときは最新 version セクションを見ない。

    両方見ると、リリース直後 (Unreleased 新設 + 直前 version が残っている状態)
    で直前 version の内部用語を蒸し返して red になる。
    """
    released = (
        "## [0.3.1] - 2026-08-20\n\n### Changed\n\n"
        "- presence 判定を変更した (#1)。\n\n" + _RELEASED
    )
    changelog = _write(
        tmp_path, "### Changed\n\n- 表示を変えた (#1)。\n", released=released
    )
    assert _run(changelog).returncode == 0


# --------------------------------------------------------------------------
# _FALSE_RED: 規約が推奨する書き方を red にしない
# --------------------------------------------------------------------------

# (label, entry) -- いずれも exit 0 でなければならない。
_FALSE_RED: list[tuple[str, str]] = [
    (
        "spec link destination",
        "- 配信録画の検出を改善した (#895)。詳細は "
        "[spec](docs/superpowers/specs/2026-07-11-issue-822-masked-oversplit-anchor-design.md)"
        " を参照。\n",
    ),
    (
        "path-like inline code",
        "- GT データを同梱した (#895)。`tests/baselines/v0.3.0/vtuber-gt/anchor.json` に置く。\n",
    ),
    (
        "fenced code block",
        "### Changed\n\n- 使い方が変わった (#1)。\n\n```text\nV3: 4 gaps tested\n```\n",
    ),
    (
        "bare url containing jargon",
        "- 検出を改善した (#1)。[設計メモ](https://example.com/anchor-quorum) 参照。\n",
    ),
]


@pytest.mark.parametrize(("label", "entry"), _FALSE_RED, ids=lambda v: str(v)[:24])
def test_recommended_forms_are_not_false_red(
    tmp_path: Path, label: str, entry: str
) -> None:
    changelog = _write(tmp_path, entry)
    result = _run(changelog)
    assert result.returncode == 0, (
        f"{label} が false-red になった: {result.stdout + result.stderr}"
    )


def test_jargon_in_link_label_still_fires(tmp_path: Path) -> None:
    """マスクするのはリンクの **destination だけ**。label は読者に見える散文。

    `[presence design](url)` の `presence` は読者の目に入るので違反である。
    destination のマスクを「リンク全体のマスク」に広げると、この経路で内部用語が
    素通りする (実装時に実際に取り違えた)。
    """
    changelog = _write(
        tmp_path,
        "- 改善した (#1)。[presence design](https://example.com/x) 参照。\n",
    )
    result = _run(changelog)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "presence" in result.stdout + result.stderr


# --------------------------------------------------------------------------
# exit 2: 構造エラー -- 「検査自体が壊れた」を 0 で通さない
# --------------------------------------------------------------------------


def test_missing_changelog_is_exit_2(tmp_path: Path) -> None:
    result = _run(tmp_path / "does-not-exist.md")
    assert result.returncode == 2, result.stdout + result.stderr


def test_malformed_newest_heading_does_not_fall_through_to_older_section(
    tmp_path: Path,
) -> None:
    """最新セクションの見出し書式が壊れたら exit 2。**古い節へ落ちない**。

    実装時に実際に踏んだ false-green: 「最初に見つかる version 見出し」を探す
    素朴な実装だと、`## [Unreleased]` と `## [0.3.0] - ...` の書式を崩した
    CHANGELOG で **さらに古い `## [0.2.1]` を拾って緑を返した** (実測)。
    古い節は既リリースで内部用語が無いことが多いため、これは
    「検査対象が黙って過去に移った」ことに気づけない最悪の形になる。
    """
    path = tmp_path / "CHANGELOG.md"
    path.write_text(
        _HEADER
        # 最新セクション: 見出し書式が壊れている (bracket 無し)
        + "## 未リリース\n\n### Changed\n\n- presence 判定を変えた (#1)。\n\n"
        # 古いセクション: 書式は正しく、違反も無い
        + "## [0.2.1] - 2026-05-17\n\n### Fixed\n\n- 何かを直した (#2)。\n",
        encoding="utf-8",
    )
    result = _run(path)
    assert result.returncode == 2, (
        f"古い節へ fall through して緑になった: {result.stdout + result.stderr}"
    )


def test_unreleased_not_first_h2_is_exit_2(tmp_path: Path) -> None:
    """`## [Unreleased]` が先頭 h2 でないなら exit 2。**released 節で緑にしない**。

    Codex adversarial-review [medium] の指摘。「最初の h2 を分類する」だけの実装
    では、released 節が上・`## [Unreleased]` が下という順序の CHANGELOG で
    **released 節 (通常は clean) を検査して exit 0** を返し、Unreleased 側の
    内部用語や `### Internal` が無検査で残る。docstring が主張する scope 規則
    (「Unreleased を優先」) と実装が矛盾していた。

    ここで fail-closed を選ぶのは、順序が壊れている時点でどちらを検査すべきかを
    推測させるべきでないため。Keep a Changelog では Unreleased は常に先頭に置く。
    """
    path = tmp_path / "CHANGELOG.md"
    path.write_text(
        _HEADER
        # 順序が逆: released が先、Unreleased が後
        + "## [0.3.1] - 2026-08-20\n\n### Fixed\n\n- 何かを直した (#2)。\n\n"
        + "## [Unreleased]\n\n### Changed\n\n- presence 判定を変えた (#1)。\n",
        encoding="utf-8",
    )
    result = _run(path)
    assert result.returncode == 2, (
        f"Unreleased を飛ばして released 節で緑になった: "
        f"{result.stdout + result.stderr}"
    )


def test_no_scannable_section_is_exit_2(tmp_path: Path) -> None:
    """`## [Unreleased]` も version セクションも無い = anchor 消失。

    「0 件と 0 件が一致した」で緑を返すと、見出し書式を変えた改稿で検査が
    黙って no-op になる。
    """
    path = tmp_path / "CHANGELOG.md"
    path.write_text(_HEADER + "## 変更履歴\n\n- 何か (#1)。\n", encoding="utf-8")
    result = _run(path)
    assert result.returncode == 2, result.stdout + result.stderr


# --------------------------------------------------------------------------
# 実物との統合
# --------------------------------------------------------------------------


def test_repo_changelog_passes() -> None:
    """repo の実 CHANGELOG.md が規約を満たす (CI が見るのと同じ経路)。"""
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


def test_forbidden_terms_list_is_non_empty() -> None:
    """語彙リストが空になると検査は静かに no-op になる。"""
    assert guard.FORBIDDEN_TERMS, "FORBIDDEN_TERMS が空"
