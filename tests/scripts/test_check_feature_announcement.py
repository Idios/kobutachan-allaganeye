"""Tests for scripts/check_feature_announcement.py (#944).

保護機構は不発でも green になるため、本テストは **違反を注入して exit code の
生値を観測する** 形で書く (`tests/scripts/test_check_doc_code_refs.py` と同じ規律)。

本 file の主眼は `_EVASIONS` の parametrize 群である。「機能名が doc に出現するか」
という検査は素朴に substring で書くと、
(a) 散文中の英単語 (`export` / `detect`) が告知として数えられる
(b) `detect` が `detected` の一部として数えられる
(c) URL や ZIP ファイル名の中の `allaganeye` に引きずられる
という 3 つの false-green を必ず踏む。**告知とは「呼び出し形が書いてあること」**
と定義し、その定義が実際に回避形を弾くことを fixture で常駐させる。

ここで使う doc 断片は、すべて `README.md` / `docs/quickstart.md` に **今日実在
する行** を写したものである (各 fixture に出典行を記す)。架空の回避形ではない。
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
SCRIPT_PATH = SCRIPTS_DIR / "check_feature_announcement.py"

_spec = importlib.util.spec_from_file_location(
    "check_feature_announcement", SCRIPT_PATH
)
assert _spec is not None and _spec.loader is not None
guard = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = guard
_spec.loader.exec_module(guard)


# --------------------------------------------------------------------------
# SSoT: typer runtime registry
# --------------------------------------------------------------------------


def test_collects_the_five_shipped_commands() -> None:
    """SSoT は typer runtime registry であり、`@app.command` の静的走査ではない。

    `minimap` (`commands/minimap.py:46`) と `export` (`commands/export.py:69`) は
    `cli.py:654-656` の `register(app)` 経由で登録されるため、`cli.py` の
    `@app.command` だけを見ると **#944 で漏れた 2 機能がちょうど検査対象外**になる。
    """
    assert guard.collect_shipped_commands() == {
        "split",
        "detect",
        "export",
        "minimap",
        "debug-brightness",
    }


def test_hidden_commands_are_excluded_from_the_ssot() -> None:
    """`encoder-slots` は `hidden=True` (`commands/encoder_slots.py:23`)。

    隠しコマンドは `allaganeye --help` に出ないので、入口 doc に告知する対象でもない。
    """
    assert "encoder-slots" not in guard.collect_shipped_commands()


# --------------------------------------------------------------------------
# 告知の定義: 呼び出し形が書いてあること
# --------------------------------------------------------------------------

# (label, doc 断片) -- いずれも `export` の告知として数えて **はならない**。
_EVASIONS: list[tuple[str, str]] = [
    (
        # README.md:93 に実在する散文 (「エクスポート」ではなく英語が出る形の代表)
        "bare-english-word-in-prose",
        "出力先: D&D 時は allaganeye-*\\output\\、GUI 時は画面上で export 先を指定",
    ),
    (
        # quickstart.md:11 に実在: ZIP ファイル名の中の `allaganeye`
        "product-name-in-zip-filename",
        "**Assets** から `allaganeye-*-windows.zip` をクリックしてダウンロードします。",
    ),
    (
        # README.md:21 に実在: repo URL の中の `allaganeye`
        "product-name-inside-repo-url",
        '<a href="https://github.com/Idios/kobutachan-allaganeye">export</a>',
    ),
    (
        "command-name-as-substring-of-longer-word",
        "検出された区間は exported / detected として metadata に残ります。",
    ),
    (
        # 「一覧表に名前だけ載っている」形。#944 が問題視した「発見経路が無い」状態
        # そのものなので、告知として数えない。
        "name-only-in-a-table-cell",
        "| `export` | 並列書き出し | v0.3.0 |",
    ),
    (
        "hyphen-glued-to-another-token",
        "内部識別子は pre-export-hook と呼ばれます。",
    ),
]


@pytest.mark.parametrize(("label", "text"), _EVASIONS, ids=[e[0] for e in _EVASIONS])
def test_evasion_forms_do_not_count_as_announcement(label: str, text: str) -> None:
    assert guard.is_announced("export", text) is False, label


# (label, doc 断片) -- いずれも告知として数えなければならない (false-red 側の固定)。
_ANNOUNCED: list[tuple[str, str, str]] = [
    (
        # quickstart.md:110 に実在する形
        "bat-launcher-form",
        "detect",
        '    allaganeye.bat detect "C:\\Users\\あなた\\Videos\\動画.mkv"',
    ),
    (
        # CLAUDE.md のコマンド節に実在する形 (開発者向け doc の標準形)
        "bare-entrypoint-form",
        "minimap",
        "allaganeye minimap <metadata.json> --region X,Y,W,H",
    ),
    (
        "hyphenated-command-name",
        "debug-brightness",
        "allaganeye debug-brightness <video_path>",
    ),
    (
        "inside-a-fenced-code-block",
        "export",
        "```bash\nallaganeye export metadata.json -o out/\n```",
    ),
    (
        "inside-an-html-code-element",
        "split",
        "<code>allaganeye.bat split &quot;C:\\video.mkv&quot;</code>",
    ),
]


@pytest.mark.parametrize(
    ("label", "command", "text"), _ANNOUNCED, ids=[a[0] for a in _ANNOUNCED]
)
def test_invocation_forms_count_as_announcement(
    label: str, command: str, text: str
) -> None:
    assert guard.is_announced(command, text) is True, label


# --------------------------------------------------------------------------
# drift 検出 (exit 1)
# --------------------------------------------------------------------------


def test_reports_one_violation_per_missing_command_surface_pair() -> None:
    surfaces = [
        guard.Surface("README.md", "allaganeye split video.mkv"),
        guard.Surface("docs/quickstart.md", "allaganeye split video.mkv"),
    ]
    violations = guard.check_announcements({"split", "minimap"}, surfaces)
    assert [(v.command, v.surface) for v in violations] == [
        ("minimap", "README.md"),
        ("minimap", "docs/quickstart.md"),
    ]


def test_no_violations_when_every_command_is_announced_on_every_surface() -> None:
    text = "allaganeye split x\nallaganeye minimap y\n"
    surfaces = [
        guard.Surface("README.md", text),
        guard.Surface("docs/quickstart.md", text),
    ]
    assert guard.check_announcements({"split", "minimap"}, surfaces) == []


# --------------------------------------------------------------------------
# fail-closed (exit 2)
# --------------------------------------------------------------------------


def test_empty_command_set_is_structural_not_success() -> None:
    """「0 件と 0 件が一致した」で緑を返さない。

    registry の読み方が壊れた (typer の API 変更 / import 失敗) ときに素通り
    すると、ガードが無いより有害になる。
    """
    with pytest.raises(guard.GuardStructureError):
        guard.check_announcements(set(), [guard.Surface("README.md", "")])


def test_missing_surface_is_structural() -> None:
    with pytest.raises(guard.GuardStructureError):
        guard.check_announcements({"split"}, [])


def test_render_portable_readme_raises_when_powershell_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PowerShell が無い環境では **黙って skip せず** 構造エラーにする。

    `Format-ReadmeContent` は同梱 README.txt の唯一の生成元なので、描画できない
    ことは「検査対象が 1 面消える」ことを意味する。skip すると #944 A-1 と同じ
    「ZIP を落としたユーザーだけが古い記述を読む」状態を検査が見逃す。
    """
    monkeypatch.setattr(guard, "_find_powershell", lambda: None)
    with pytest.raises(guard.GuardStructureError):
        guard.render_portable_readme(REPO_ROOT)


# --------------------------------------------------------------------------
# 実 repo に対する end-to-end (exit code の生値を観測)
# --------------------------------------------------------------------------


def _run_guard(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO_ROOT),
    )


def test_real_repo_passes() -> None:
    result = _run_guard()
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"


def test_repo_root_without_surfaces_exits_structural(tmp_path: Path) -> None:
    """検査対象ファイルが無い repo root を渡すと exit 2 (生値で観測)."""
    result = _run_guard("--repo-root", str(tmp_path))
    assert result.returncode == 2, f"stdout={result.stdout}\nstderr={result.stderr}"


def test_removing_an_announcement_turns_the_guard_red(tmp_path: Path) -> None:
    """入口 doc から呼び出し形を 1 件消すと exit 1 になる (発火実証).

    `README.md` を「minimap の呼び出し形が無い」状態へ書き戻し、ガードが実際に
    赤くなることを exit code の生値で確認する。
    """
    import shutil

    fake_root = tmp_path / "repo"
    shutil.copytree(
        REPO_ROOT,
        fake_root,
        ignore=shutil.ignore_patterns(
            ".git", "node_modules", ".venv", "__pycache__", "target", "dist"
        ),
    )
    readme = fake_root / "README.md"
    text = readme.read_text(encoding="utf-8")
    # minimap の呼び出し形だけを潰す (他コマンドは残す)。
    text = text.replace("allaganeye minimap", "allaganeye MINIMAP-REMOVED")
    text = text.replace("allaganeye.bat minimap", "allaganeye.bat MINIMAP-REMOVED")
    readme.write_text(text, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--repo-root", str(fake_root)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 1, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "minimap" in result.stderr
