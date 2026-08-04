#!/usr/bin/env python3
"""全バージョン保持箇所の一致を検証する (#911)。

`.github/workflows/release.yml` の `version-check` job から呼ばれる。tag push 時は
`--tag` で tag との突合も行う。

    python scripts/check_version_consistency.py [--tag vX.Y.Z] [--github-output]

exit code:

* 0 -- 全箇所一致 (`--tag` 指定時は tag とも一致)
* 1 -- バージョン不一致
* 2 -- 構造エラー (ファイル欠損 / パース不能 / フィールド欠損)

1 と 2 を分けるのは「ズレている」と「検査自体が壊れた」を CI ログ上で区別するため。
検査の自己崩壊を 0 で通すと、ガードが無いより有害になる。

`VERSION_LOCATIONS` が **バージョン保持箇所の機械可読な正** (`docs/coding-conventions.md`
§ドキュメント SSoT 規約 #818 の「管轄が重なる場合は実装を canonical」)。
`docs/versioning.md` の一覧との乖離は
`tests/scripts/test_check_version_consistency.py` が検知する。
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


class VersionProbeError(Exception):
    """バージョン値を取り出せなかった (ファイル欠損 / パース不能 / フィールド欠損)。"""


@dataclass(frozen=True)
class VersionLocation:
    """バージョンを保持するファイルと、その中のフィールド位置。

    `keys` は 1 ファイル内の複数フィールドを表す (例: package-lock.json は root の
    `version` と `packages[""].version` の 2 箇所を持ち、片方だけが古びる drift が実在する)。

    `select` は「配列の中から 1 要素を選んでから `keys` を辿る」場合に使う
    (`(配列を持つ key, 一致させるフィールド, 期待値)`)。Cargo.lock は全依存クレートを
    `[[package]]` 配列に並べるため固定 key path では辿れない。しかも root 直下に
    lockfile フォーマット版を示す `version = 4` を持つので、素朴に `("version",)` を
    辿ると**依存でもパッケージでもない別物**を読んでしまう。
    """

    path: str
    fmt: Literal["toml", "json"]
    keys: tuple[tuple[str, ...], ...]
    consumer: str
    select: tuple[str, str, str] | None = None


VERSION_LOCATIONS: tuple[VersionLocation, ...] = (
    VersionLocation(
        path="pyproject.toml",
        fmt="toml",
        keys=(("project", "version"),),
        consumer="CLI `allaganeye --version`",
    ),
    VersionLocation(
        path="gui/src-tauri/tauri.conf.json",
        fmt="json",
        keys=(("version",),),
        consumer="Tauri bundle metadata / exe ファイルバージョン",
    ),
    VersionLocation(
        path="gui/src-tauri/Cargo.toml",
        fmt="toml",
        keys=(("package", "version"),),
        consumer='env!("CARGO_PKG_VERSION") -> probe_environment_info().allaganeye_version',
    ),
    VersionLocation(
        path="gui/package.json",
        fmt="json",
        keys=(("version",),),
        consumer="npm package metadata",
    ),
    VersionLocation(
        path="gui/package-lock.json",
        fmt="json",
        keys=(("version",), ("packages", "", "version")),
        consumer="npm が package.json から同期",
    ),
    VersionLocation(
        path="gui/src-tauri/Cargo.lock",
        fmt="toml",
        keys=(("version",),),
        select=("package", "name", "allaganeye-gui"),
        consumer="cargo が Cargo.toml から同期",
    ),
)


def _describe(keys: tuple[str, ...]) -> str:
    """key path を `docs/versioning.md` と同じ記法で表す。

    空文字 key は npm lockfile の root package entry (`packages[""]`) を指す。
    素直にドット連結すると `packages."".version` になり、doc 側の
    `packages[""].version` と表記が割れる。表記が割れると
    `tests/scripts/test_check_version_consistency.py` の**フィールド単位**の
    doc 突合ができなくなる (ファイル単位でしか照合できず、
    「同じファイルは載っているがフィールドが 1 つ抜けた」drift を見逃す) ので、
    doc 側の記法に揃える。
    """
    rendered = ""
    for key in keys:
        if not key:
            rendered += '[""]'
        elif rendered:
            rendered += f".{key}"
        else:
            rendered = key
    return rendered


def field_label(location: VersionLocation, keys: tuple[str, ...]) -> str:
    """ファイル内のフィールド位置を表す (`docs/versioning.md` のフィールド列と同記法)。

    doc 突合テストが参照するので public。
    """
    described = _describe(keys)
    if location.select is None:
        return described
    array_key, field, expected = location.select
    return f"{array_key}[{field}={expected}].{described}"


def _label(location: VersionLocation, keys: tuple[str, ...]) -> str:
    return f"{location.path} ({field_label(location, keys)})"


def _load(path: Path, fmt: Literal["toml", "json"]) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise VersionProbeError(f"{path}: 読み込めません ({exc})") from exc
    try:
        if fmt == "toml":
            return tomllib.loads(raw.decode("utf-8"))
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise VersionProbeError(f"{path}: パースできません ({exc})") from exc


def collect_versions(repo_root: Path) -> list[tuple[str, str]]:
    """`(表示名, バージョン値)` を全箇所ぶん返す。

    構造エラーは `VersionProbeError` で送出する (呼び出し側が exit 2 に落とす)。
    """
    collected: list[tuple[str, str]] = []
    for location in VERSION_LOCATIONS:
        document = _load(repo_root / location.path, location.fmt)
        root: Any = document
        if location.select is not None:
            array_key, field, expected = location.select
            entries = document.get(array_key)
            if not isinstance(entries, list):
                raise VersionProbeError(
                    f"{location.path}: {array_key} が配列ではありません"
                )
            matched = [
                entry
                for entry in entries
                if isinstance(entry, dict) and entry.get(field) == expected
            ]
            # 0 件 = パッケージ名が変わった / 2 件以上 = どれを見るべきか曖昧。
            # どちらも「検査対象を特定できない」ので exit 2 (構造エラー) に倒す。
            if len(matched) != 1:
                raise VersionProbeError(
                    f"{location.path}: {array_key} に {field}={expected!r} の要素が "
                    f"{len(matched)} 個あります (1 個であるべき)"
                )
            root = matched[0]

        for keys in location.keys:
            node: Any = root
            for key in keys:
                if not isinstance(node, dict) or key not in node:
                    raise VersionProbeError(
                        f"{location.path}: フィールド {_label(location, keys)} が存在しません"
                    )
                node = node[key]
            if not isinstance(node, str):
                raise VersionProbeError(
                    f"{location.path}: フィールド {_label(location, keys)} が"
                    f"文字列ではありません ({node!r})"
                )
            collected.append((_label(location, keys), node))
    return collected


def _group_by_version(collected: list[tuple[str, str]]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for label, version in collected:
        groups.setdefault(version, []).append(label)
    return groups


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="検査対象の repo root (default: このスクリプトの親ディレクトリ)",
    )
    parser.add_argument(
        "--tag",
        default=None,
        help="突合する git tag (例: v0.3.0)。省略時は箇所間の相互一致のみ検証する",
    )
    parser.add_argument(
        "--github-output",
        action="store_true",
        help="一致時に version=<値> を $GITHUB_OUTPUT へ追記する",
    )
    parser.add_argument(
        "--list-paths",
        action="store_true",
        help="検査対象ファイルの path を 1 行 1 件で出力して終了する "
        "(バンプ時の `git add --` 引数用。値は読まない)",
    )
    args = parser.parse_args(argv)

    if args.list_paths:
        # バンプ「途中」に stage 対象を得るための mode なので、値の一致は見ない
        # (この時点ではまだ不一致なのが正常)。dict.fromkeys で宣言順を保ったまま
        # 重複 path を畳む (package-lock.json は 2 フィールド = 1 ファイル)。
        #
        # 改行は LF に固定する。この出力は `git add -- $(...)` で機械消費されるが、
        # Windows の text-mode stdout は "\n" を CRLF へ変換する一方 bash の既定
        # IFS は "\r" を区切りに含めないため、path 末尾に "\r" が残って
        # `fatal: pathspec 'pyproject.toml?' did not match any files` になる。
        if isinstance(sys.stdout, io.TextIOWrapper):
            sys.stdout.reconfigure(newline="\n")
        for path in dict.fromkeys(location.path for location in VERSION_LOCATIONS):
            print(path)
        return 0

    try:
        collected = collect_versions(args.repo_root)
    except VersionProbeError as exc:
        print(f"::error::バージョン検査に失敗しました: {exc}")
        return 2

    for label, version in collected:
        print(f"{label}: {version}")

    groups = _group_by_version(collected)
    failed = False

    if len(groups) > 1:
        print(f"::error::バージョンが {len(groups)} 種類に分裂しています")
        for version, labels in sorted(groups.items()):
            print(f'::error::version "{version}" at: {", ".join(sorted(labels))}')
        failed = True

    resolved = collected[0][1]
    if args.tag is not None:
        expected = args.tag[1:] if args.tag.startswith("v") else args.tag
        stale = sorted(label for label, version in collected if version != expected)
        if stale:
            print(
                f'::error::tag "{args.tag}" (= {expected}) と一致しない箇所があります: '
                f"{', '.join(stale)}"
            )
            failed = True
        resolved = expected

    if failed:
        return 1

    print(f"OK: 全 {len(collected)} 箇所が {resolved} で一致しています")

    if args.github_output:
        github_output = os.environ.get("GITHUB_OUTPUT")
        if not github_output:
            print("::error::--github-output 指定時は $GITHUB_OUTPUT が必要です")
            return 2
        with open(github_output, "a", encoding="utf-8") as handle:
            handle.write(f"version={resolved}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
