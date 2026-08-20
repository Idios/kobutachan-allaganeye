#!/usr/bin/env python3
"""出荷している CLI サブコマンドが入口 doc に告知されているかを検査する (#944)。

`.github/workflows/ci.yml` の `feature-announcement` job から引数なしで呼ばれる。

    python scripts/check_feature_announcement.py [--repo-root DIR]

exit code:

* 0 -- 全サブコマンドが全ての告知面に登場した
* 1 -- 告知漏れがある (doc を直す)
* 2 -- 構造エラー (registry が空 / 告知面のファイル欠損 / PowerShell 不在)

1 と 2 を分けるのは `scripts/check_doc_code_refs.py` / `check_version_consistency.py`
と同じ理由による。「漏れている」と「検査自体が壊れた」を CI ログ上で区別するため
で、検査の自己崩壊を 0 で通すとガードが無いより有害になる。

## なぜこの gate が要るか

#932 / #941 の記述ドリフト・スイープは「**振る舞いを説明する仕様書**」を対象に
していた。その file set は既に機能ごとの節を持つ doc の集合だったため、「節はある
が記述が古い」ドリフトは diff に出て直った一方、「**どこにも節が無い機能**」
(`minimap` / `export`) は diff にも grep 差分にも現れず不可視だった。v0.3.0 出荷
時点で `minimap` は README / quickstart / 同梱 README.txt のいずれにも 1 度も
登場せず、一般ユーザーの発見経路が存在しなかった。

## SSoT: typer runtime registry

正は `typer.main.get_command(app).commands` を列挙し `hidden=True` を除いた集合。

**`allaganeye/cli.py` の `@app.command` を静的走査してはならない。** `cli.py` の
`@app.command` は `split` / `detect` / `debug-brightness` の 3 つだけで、
`minimap` (`allaganeye/commands/minimap.py`) と `export`
(`allaganeye/commands/export.py`) は `cli.py` 末尾の `register(app)` 経由で
登録される。静的走査は **#944 で実際に漏れた 2 機能をちょうど検査対象外にする**。

## 告知面 (3 面)

| 面 | 実体 | 読者 |
| --- | --- | --- |
| `README.md` | repo の入口 | GitHub を見る人 |
| `docs/quickstart.md` | 一般ユーザー向け導入 | ZIP を落とす人 |
| 同梱 `README.txt` | `Format-ReadmeContent` (`scripts/build-portable-zip.ps1`) の出力 | **GitHub を見ない人** |

3 面目は source を grep せず **PowerShell で実際に描画して**その出力を見る。
ここを正規表現で読むと here-string / 関数境界の取り違えで false-green になる
(本 repo は source-scan guard の lexer desync を過去に複数回踏んでいる)。
`build-portable-zip.ps1` は `-Version` 省略時に関数定義だけ読み込んで return
する設計 (同 script の `if ([string]::IsNullOrEmpty($Version)) { return }`) なので、
dot-source しても build は走らない。

## 告知の定義

**「呼び出し形が書いてあること」**、すなわち ``allaganeye`` または
``allaganeye.bat`` に続けてサブコマンド名が現れること。

単なる名前の出現を告知と数えると、以下がすべて素通りする (いずれも本 repo に
実在した形。`tests/scripts/test_check_feature_announcement.py` の `_EVASIONS` に
fixture として常駐させてある)。

* 散文中の英単語 -- 「画面上で export 先を指定」
* ZIP ファイル名 -- ``allaganeye-*-windows.zip``
* repo URL -- ``https://github.com/Idios/kobutachan-allaganeye``
* 長い語の部分一致 -- ``exported`` / ``detected``
* 表のセルに名前だけ -- ``| `export` | 並列書き出し |``

## この gate が見ていない集合

**「呼び出し形が 1 回以上出るか」しか見ない。** 以下は検査外である。

* **記述の正しさ** -- 引数・オプション・説明文が実装と合っているかは見ない。
  ``allaganeye minimap`` と 1 行書けば、その説明が全部間違っていても通る。
* **フラグ単位の機能** -- ``--masked`` / ``--vtuber`` / ``--keep-trailing`` は
  サブコマンド粒度では原理的に捕まらない。#944 が挙げた 6 機能のうち本 gate が
  射程に持つのは ``minimap`` / ``export`` の 2 つだけである。
* **`hidden=True` のコマンド** -- ``encoder-slots`` は設計上除外している。逆に
  言えば、既存コマンドを `hidden=True` にすると本 gate から黙って消える。
* **告知の質と導線** -- 折りたたみの中・索引リンクの中に 1 度出るだけで pass
  する。「一般ユーザーが辿り着けるか」は測っていない。
* **README.txt 以外の同梱物** -- ZIP に入る他のファイル (`allaganeye.bat` の
  ヘルプ文言等) は見ていない。
* **GUI 内の文言** -- アプリ内から機能を発見できるかは別軸 (#944 §D)。

Refs: https://github.com/Idios/kobutachan-allaganeye/issues/944
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Iterable, Sequence

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_STRUCTURAL = 2

# 告知面のうち repo 内のファイルとして存在するもの。
_DOC_SURFACES = ("README.md", "docs/quickstart.md")

# `Format-ReadmeContent` を描画するときの引数。値そのものは検査に無関係なので
# placeholder でよいが、Mandatory なので省略はできない。
_README_RENDER_ARGS = {
    "Version": "0.0.0",
    "FFmpegVersion": "0.0",
    "FFmpegBuildTag": "placeholder",
    "FFmpegSourceRef": "placeholder",
}


class GuardStructureError(RuntimeError):
    """検査自体が成立しないときに送出する (exit 2)。"""


@dataclass(frozen=True)
class Surface:
    """告知面 1 つ分のラベルと本文。"""

    label: str
    text: str


@dataclass(frozen=True)
class Violation:
    command: str
    surface: str

    def render(self) -> str:
        return (
            f"  - `{self.command}` の呼び出し形が {self.surface} に無い"
            f" (`allaganeye {self.command} ...` の形で 1 箇所以上書くこと)"
        )


def collect_shipped_commands() -> set[str]:
    """typer runtime registry から非 hidden のサブコマンド名を集める。

    静的走査ではなく実際に登録された click group を読む理由は module docstring
    §SSoT を参照。

    SSoT は **本 script が同梱されている repo の CLI** から読む (`--repo-root` は
    告知面の選択にのみ効く)。script と CLI は同じ ZIP に同梱されて出荷される以上、
    両者は常に対で動く。pip install 済みでなくても動くよう repo root を
    `sys.path` に載せる。
    """
    own_repo_root = str(Path(__file__).resolve().parents[1])
    if own_repo_root not in sys.path:
        sys.path.insert(0, own_repo_root)

    try:
        import typer.main

        from allaganeye.cli import app
    except Exception as exc:  # pragma: no cover - import 失敗は環境問題
        raise GuardStructureError(
            f"allaganeye の CLI registry を読めない ({exc!r})。"
            " 本 job は `pip install -e . -c constraints.txt` を必要とする。"
        ) from exc

    group = typer.main.get_command(app)
    commands = getattr(group, "commands", None)
    if not commands:
        raise GuardStructureError(
            "typer runtime registry からサブコマンドを 1 件も取得できなかった。"
            " typer / click の API 変更で registry の読み方が壊れた可能性がある。"
        )
    return {name for name, cmd in commands.items() if not getattr(cmd, "hidden", False)}


# HTML コメントはレンダリング後の読者に見えないので告知面から除く。
# 閉じていない `<!--` は GitHub 上で以降を丸ごと飲み込むため、末尾まで除く
# (false-red 側に倒す。false-green にはしない)。
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_UNCLOSED_HTML_COMMENT_RE = re.compile(r"<!--.*\Z", re.DOTALL)


def strip_invisible(text: str) -> str:
    """レンダリング後に読者へ見えない領域を落とす。"""
    without_closed = _HTML_COMMENT_RE.sub(" ", text)
    return _UNCLOSED_HTML_COMMENT_RE.sub(" ", without_closed)


def is_announced(command: str, text: str) -> bool:
    """`text` に `command` の**呼び出し形**が現れるか。

    定義と、単なる名前出現を採らない理由は module docstring §告知の定義 を参照。
    HTML コメント内の記述は告知として数えない (Codex adversarial-review
    2026-08-20 の指摘。`README.md` は冒頭に markdownlint 設定用のコメント塊を
    持つため、「コメントに書いただけ」で緑になる経路が実在した)。
    """
    pattern = re.compile(
        r"(?<![A-Za-z0-9_-])allaganeye(?:\.bat)?[ \t]+"
        + re.escape(command)
        + r"(?![A-Za-z0-9_-])"
    )
    return pattern.search(strip_invisible(text)) is not None


def check_announcements(
    commands: Iterable[str], surfaces: Sequence[Surface]
) -> list[Violation]:
    """全 (command, surface) 組を突合し、告知漏れを列挙する。"""
    command_list = sorted(commands)
    if not command_list:
        raise GuardStructureError(
            "検査対象のサブコマンドが 0 件。"
            " 「0 件と 0 件が一致した」で緑を返さないため構造エラーとして扱う。"
        )
    if not surfaces:
        raise GuardStructureError("告知面が 0 件。検査対象ファイルを解決できていない。")

    return [
        Violation(command=command, surface=surface.label)
        for command in command_list
        for surface in surfaces
        if not is_announced(command, surface.text)
    ]


def _find_powershell() -> str | None:
    """`pwsh` (PowerShell 7, ubuntu runner 同梱) を優先し Windows の 5.1 に fallback。"""
    for exe in ("pwsh", "powershell"):
        found = shutil.which(exe)
        if found:
            return found
    return None


def render_portable_readme(repo_root: Path, *, include_gui: bool = True) -> str:
    """`Format-ReadmeContent` を実際に描画して同梱 README.txt の本文を得る。"""
    powershell = _find_powershell()
    if powershell is None:
        raise GuardStructureError(
            "pwsh / powershell が見つからないため同梱 README.txt を描画できない。"
            " 黙って skip すると告知面が 1 つ検査対象から消えるので構造エラーにする。"
        )

    script_path = repo_root / "scripts" / "build-portable-zip.ps1"
    if not script_path.is_file():
        raise GuardStructureError(f"{script_path} が無い。")

    args = " ".join(f"-{k} '{v}'" for k, v in _README_RENDER_ARGS.items())
    if include_gui:
        args += " -IncludeGui"
    ps_literal = str(script_path).replace("'", "''")
    script = (
        "$ErrorActionPreference='Stop'; "
        "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
        f". '{ps_literal}'; "
        f"Write-Output (Format-ReadmeContent {args})"
    )

    try:
        result = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GuardStructureError(f"PowerShell の起動に失敗した: {exc!r}") from exc

    if result.returncode != 0:
        raise GuardStructureError(
            f"Format-ReadmeContent の描画が非ゼロ終了した (rc={result.returncode}):"
            f"\n{result.stderr.strip()}"
        )
    rendered = result.stdout
    if "allaganeye" not in rendered:
        raise GuardStructureError(
            "Format-ReadmeContent の出力が README.txt に見えない"
            " (関数名の変更・戻り値の形の変更を疑うこと)。"
        )
    return rendered


def collect_surfaces(repo_root: Path) -> list[Surface]:
    """3 つの告知面を読み込む。1 つでも欠ければ構造エラー。"""
    surfaces: list[Surface] = []
    for rel in _DOC_SURFACES:
        path = repo_root / rel
        if not path.is_file():
            raise GuardStructureError(f"告知面 {rel} が見つからない ({path})。")
        surfaces.append(Surface(label=rel, text=path.read_text(encoding="utf-8")))

    # どの PowerShell で描画したかは CI ログに残す。pwsh 不在で落ちたときに
    # 「検査対象が 1 面消えた」のか「shell が違った」のかを即断できるようにする。
    print(f"README.txt を描画する PowerShell: {_find_powershell()}")

    for include_gui in (True, False):
        variant = "GUI 同梱" if include_gui else "CLI のみ"
        surfaces.append(
            Surface(
                label=f"同梱 README.txt ({variant})",
                text=render_portable_readme(repo_root, include_gui=include_gui),
            )
        )
    return surfaces


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else ""
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="検査対象の repo ルート (既定: 本 script の 1 つ上)",
    )
    args = parser.parse_args(argv)
    repo_root: Path = args.repo_root.resolve()

    # 診断は日本語を含む。Windows の既定 code page (cp932) のまま出すと
    # CI ログ / 呼び出し側の capture で化けるため UTF-8 に固定する。
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    try:
        commands = collect_shipped_commands()
        surfaces = collect_surfaces(repo_root)
        violations = check_announcements(commands, surfaces)
    except GuardStructureError as exc:
        print(f"ERROR: 検査自体が壊れている: {exc}", file=sys.stderr)
        return EXIT_STRUCTURAL

    if violations:
        print(
            "ERROR: 出荷している CLI サブコマンドが入口 doc に告知されていない。\n",
            file=sys.stderr,
        )
        for violation in violations:
            print(violation.render(), file=sys.stderr)
        print(
            "\n入口 doc に呼び出し形を書くこと。"
            "\n契約の詳細は scripts/check_feature_announcement.py の docstring を参照。",
            file=sys.stderr,
        )
        return EXIT_DRIFT

    print(
        f"OK: {len(commands)} 個の CLI サブコマンドが {len(surfaces)} 面すべてに告知されている"
        f" ({', '.join(sorted(commands))})"
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
