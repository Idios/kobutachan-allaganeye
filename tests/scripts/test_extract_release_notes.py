"""Tests for scripts/extract_release_notes.py (#948).

本スクリプトは GitHub Release の本文を CHANGELOG.md から切り出す。**タグ push で
しか動かない**ため、壊れていても気付くのはリリース当日である。にもかかわらず
これまで対応するテストが 1 件も存在しなかった (#948 の裏取り)。

`check_version_consistency.py` 側とは**別 job / 別発火条件**である点に注意する:
こちらが見るのは「日付が書式として存在するか」だけで、値の正しさは見ない
(逆に、日付さえ書式通りなら本文が空でも通る)。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"

_spec = importlib.util.spec_from_file_location(
    "extract_release_notes", SCRIPTS_DIR / "extract_release_notes.py"
)
assert _spec is not None and _spec.loader is not None
ern = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = ern
_spec.loader.exec_module(ern)


_PREAMBLE = "# Changelog\n\nAll notable changes to this project.\n\n"


def _changelog(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "CHANGELOG.md"
    path.write_text(_PREAMBLE + body, encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# 正常系
# --------------------------------------------------------------------------


def test_extracts_dated_section(tmp_path: Path) -> None:
    source = _changelog(
        tmp_path,
        "## [0.3.1] - 2026-08-07\n\n### Fixed\n\n- 直した\n\n"
        "## [0.3.0] - 2026-08-04\n\n### Added\n\n- 足した\n",
    )

    notes = ern.extract("0.3.1", source)

    assert notes.startswith("## [0.3.1] - 2026-08-07")
    assert "- 直した" in notes
    # 次の version 見出しで打ち切ること (前リリースの内容を巻き込まない)。
    assert "0.3.0" not in notes
    assert "- 足した" not in notes


def test_last_section_extends_to_end_of_file(tmp_path: Path) -> None:
    source = _changelog(
        tmp_path,
        "## [0.3.1] - 2026-08-07\n\n- 新しい\n\n## [0.1.1] - 2026-04-20\n\n- 最古\n",
    )

    notes = ern.extract("0.1.1", source)

    assert notes.startswith("## [0.1.1] - 2026-04-20")
    assert "- 最古" in notes


# --------------------------------------------------------------------------
# 発火実証: 日付が無ければ落とす (#948 受け入れ条件)
# --------------------------------------------------------------------------


def test_section_without_date_raises_system_exit(tmp_path: Path) -> None:
    """日付なしの見出しは `SystemExit` で落とすこと。

    厳格化前の regex は `## \\[{version}\\]` だけを見ていたため、日付が抜けた
    まま Release 本文が出来上がっていた。
    """
    source = _changelog(tmp_path, "## [0.3.1]\n\n### Fixed\n\n- 直した\n")

    with pytest.raises(SystemExit) as excinfo:
        ern.extract("0.3.1", source)

    # 「節が無い」ではなく「日付が無い」と分かるメッセージであること
    # (リリース当日に原因を探す時間を作らない)。
    assert "date" in str(excinfo.value).lower()


@pytest.mark.parametrize(
    "heading",
    [
        "## [0.3.1] - 2026-8-7",  # ゼロ埋めなし
        "## [0.3.1] - 2026/08/07",  # 区切りがスラッシュ
        "## [0.3.1] 2026-08-07",  # ハイフン区切りなし
        "## [0.3.1] - TBD",
    ],
    ids=["no-zero-pad", "slash-separator", "missing-dash", "placeholder"],
)
def test_malformed_date_raises_system_exit(tmp_path: Path, heading: str) -> None:
    """`YYYY-MM-DD` 以外の書式を通さないこと。"""
    source = _changelog(tmp_path, f"{heading}\n\n- 何か\n")

    with pytest.raises(SystemExit):
        ern.extract("0.3.1", source)


def test_missing_version_raises_system_exit(tmp_path: Path) -> None:
    source = _changelog(tmp_path, "## [0.3.0] - 2026-08-04\n\n- 何か\n")

    with pytest.raises(SystemExit) as excinfo:
        ern.extract("0.3.1", source)

    assert "0.3.1" in str(excinfo.value)


# --------------------------------------------------------------------------
# `## [Unreleased]` (D7 で新設予定) との相互作用
# --------------------------------------------------------------------------


def test_unreleased_section_is_never_extractable(tmp_path: Path) -> None:
    """`## [Unreleased]` は日付を持たないので抽出対象にならないこと。

    未リリースの節を Release 本文にしてしまう事故を構造的に防ぐ。
    """
    source = _changelog(tmp_path, "## [Unreleased]\n\n- 開発中\n")

    with pytest.raises(SystemExit):
        ern.extract("Unreleased", source)


def test_unreleased_section_above_target_is_not_included(tmp_path: Path) -> None:
    """先頭の `## [Unreleased]` が対象節へ混ざらないこと (D7 の前方互換)。"""
    source = _changelog(
        tmp_path,
        "## [Unreleased]\n\n- まだ出していない変更\n\n"
        "## [0.3.1] - 2026-08-07\n\n- 出す変更\n",
    )

    notes = ern.extract("0.3.1", source)

    assert notes.startswith("## [0.3.1] - 2026-08-07")
    assert "まだ出していない変更" not in notes


def test_version_string_is_matched_literally(tmp_path: Path) -> None:
    """version はメタ文字ではなくリテラルとして突合すること (`.` が任意文字にならない)。"""
    source = _changelog(tmp_path, "## [0.3.1] - 2026-08-07\n\n- 出す変更\n")

    with pytest.raises(SystemExit):
        ern.extract("0!3!1", source)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [["extract_release_notes.py"], ["extract_release_notes.py", "0.3.1"]],
    ids=["no-args", "missing-output"],
)
def test_main_rejects_wrong_argv(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        ern.main(argv)

    assert excinfo.value.code == 2


def test_main_writes_notes_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`main` が cwd の CHANGELOG.md を読んで出力ファイルを書くこと。"""
    _changelog(tmp_path, "## [0.3.1] - 2026-08-07\n\n- 出す変更\n")
    monkeypatch.chdir(tmp_path)

    ern.main(["extract_release_notes.py", "0.3.1", "release-notes.md"])

    written = (tmp_path / "release-notes.md").read_text(encoding="utf-8")
    assert written.startswith("## [0.3.1] - 2026-08-07")
    assert written.endswith("\n")


# --------------------------------------------------------------------------
# fenced code block (Release 本文の途中切れ)
# --------------------------------------------------------------------------


def test_fenced_heading_does_not_truncate_notes(tmp_path: Path) -> None:
    """fence 内の `## [...]` で本文を打ち切らないこと。

    リリースノートが見出しの書式例を fence で囲んで載せると、素朴な
    `(?=\\n## \\[)` 終端がその例で止まり、**GitHub Release の本文が途中までしか
    公開されない** (Codex adversarial-review round 2 medium finding)。
    fence の中身は本文の一部として**そのまま残る**必要がある。
    """
    fence = "`" * 3
    source = _changelog(
        tmp_path,
        "## [0.3.1] - 2026-08-07\n"
        "\n"
        "- 見出しの書式例:\n"
        "\n"
        f"{fence}text\n"
        "## [9.9.9] - 2026-01-01\n"
        f"{fence}\n"
        "\n"
        "- fence の後ろの変更点\n"
        "\n"
        "## [0.3.0] - 2026-08-04\n"
        "\n"
        "- 前リリース\n",
    )

    notes = ern.extract("0.3.1", source)

    # fence を跨いで最後まで拾うこと。
    assert "fence の後ろの変更点" in notes, "fence 内の見出しで本文が途中切れした"
    # fence の中身は本文の一部としてそのまま残ること (マスクが出力へ漏れない)。
    assert "## [9.9.9] - 2026-01-01" in notes
    # それでも次の実在の見出しでは打ち切ること。
    assert "前リリース" not in notes


def test_fenced_heading_cannot_impersonate_a_missing_section(tmp_path: Path) -> None:
    """fence 内にしか無いバージョンは抽出対象にならないこと (逆方向)。"""
    fence = "~" * 3
    source = _changelog(
        tmp_path,
        f"## [0.3.1] - 2026-08-07\n\n{fence}\n## [9.9.9] - 2026-01-01\n{fence}\n",
    )

    with pytest.raises(SystemExit):
        ern.extract("9.9.9", source)


# --------------------------------------------------------------------------
# CRLF (Windows checkout)
# --------------------------------------------------------------------------


def test_crlf_changelog_extracts_and_terminates(tmp_path: Path) -> None:
    """CRLF 改行でも抽出でき、次の節の手前で打ち切ること。

    本 repo は `core.autocrlf=true` で、CHANGELOG.md は `.gitattributes` の
    `eol=lf` 対象**外**なので Windows では CRLF で checkout される (実測)。CI は
    Linux (LF) なので、CRLF を壊しても CI は緑のまま。ここでは改行をバイト列で
    書いてプラットフォームに依らず CRLF 経路を通す。
    """
    path = tmp_path / "CHANGELOG.md"
    path.write_bytes(
        "# Changelog\r\n"
        "\r\n"
        "## [0.3.1] - 2026-08-07\r\n"
        "\r\n"
        "- 出す変更\r\n"
        "\r\n"
        "## [0.3.0] - 2026-08-04\r\n"
        "\r\n"
        "- 前リリース\r\n".encode()
    )

    notes = ern.extract("0.3.1", path)

    assert notes.startswith("## [0.3.1] - 2026-08-07")
    assert "出す変更" in notes
    # 次の見出しを跨いで前リリース分を巻き込まないこと。
    assert "前リリース" not in notes
    assert "0.3.0" not in notes


def test_crlf_changelog_without_date_still_raises(tmp_path: Path) -> None:
    """CRLF でも日付欠落を素通ししないこと (ガードの発火側)。"""
    path = tmp_path / "CHANGELOG.md"
    path.write_bytes(b"# Changelog\r\n\r\n## [0.3.1]\r\n\r\n- x\r\n")

    with pytest.raises(SystemExit):
        ern.extract("0.3.1", path)


# --------------------------------------------------------------------------
# 実 repo に対する pin test
# --------------------------------------------------------------------------


def test_real_changelog_sections_are_all_extractable() -> None:
    """実 CHANGELOG.md の全リリース節が厳格化後も抽出できること。

    regex を締めた結果、既存の節が抽出できなくなっていたら次のリリースで
    Release 本文が空になる。既リリース分を回帰から守る。
    """
    changelog = REPO_ROOT / "CHANGELOG.md"
    versions = ["0.3.0", "0.2.1", "0.2.0", "0.1.1"]

    for version in versions:
        notes = ern.extract(version, changelog)
        assert notes.startswith(f"## [{version}] - ")
        assert len(notes.splitlines()) > 1, f"{version} の本文が見出しだけ"
