#!/usr/bin/env python3
"""全バージョン保持箇所の一致を検証する (#911)。

`.github/workflows/release.yml` の `version-check` job から呼ばれる。tag push 時は
`--tag` で tag との突合も行う。

    python scripts/check_version_consistency.py [--tag vX.Y.Z] [--github-output]
                                                [--changelog-date-from ISO8601]

`--tag` 指定時は追加で CHANGELOG.md も検査する (#948 / #918):

* 対象バージョンの節が存在し、`## [x.y.z] - YYYY-MM-DD` の日付を持つこと
* `--changelog-date-from` を渡した場合、その日付が**タグを打つ日** (`Asia/Tokyo`) と
  一致すること (裁定 D6、`docs/release-process.md` §タグ運用)
* バンプ方向が正しいこと (既存の最新リリースより新しいこと、#918 item3)

exit code:

* 0 -- 全箇所一致 (`--tag` 指定時は tag / CHANGELOG とも一致)
* 1 -- バージョン不一致 / CHANGELOG 見出しの不備 / バンプ方向が不正
* 2 -- 構造エラー (ファイル欠損 / パース不能 / フィールド欠損 / 基準日を解釈できない)

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
import re
import sys
import tomllib
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
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


CHANGELOG_PATH = "CHANGELOG.md"

# CHANGELOG 見出し日付の基準タイムゾーン (裁定 D6)。規約の正は
# `docs/release-process.md` §タグ運用 で、`tests/scripts/test_check_version_consistency.py`
# が doc と本定数の突合を行う。
#
# **`zoneinfo.ZoneInfo("Asia/Tokyo")` を使わない理由**: Windows には IANA tz
# database が同梱されておらず、`tzdata` パッケージ無しでは
# `ZoneInfoNotFoundError` になる (本 repo の venv で実測)。CI (ubuntu) だけ通って
# **開発機 (Windows、本 repo の唯一の対応プラットフォーム) で落ちる**ため、
# `/release` の手元実行が壊れる。日本標準時は 1951 年を最後に夏時間を廃止しており
# UTC+9 固定なので、扱う範囲 (2026 年以降のリリース日) では固定 offset が IANA
# `Asia/Tokyo` と一致する。一致することは CI 側 (tzdata のある環境) の
# `test_fixed_offset_matches_iana_asia_tokyo` が実データで突合する。
CHANGELOG_TIMEZONE_NAME = "Asia/Tokyo"
CHANGELOG_TIMEZONE = timezone(timedelta(hours=9), CHANGELOG_TIMEZONE_NAME)

# version 部分と、その後ろに続く文字列 (`rest`) を分けて捉える。
#
# **日付の妥当性で見出しを捨ててはいけない。** 日付が読めた行だけを見出しとして
# 扱うと、`## [0.4.0] - TBD` のような書き損じが「見出しではない」ことになり、
# バンプ方向チェックの比較対象から静かに消える (= 0.4.0 が既にある CHANGELOG で
# v0.3.1 を打っても通る false-green)。まず全ての `## [...]` 行を拾い、日付として
# 妥当かどうかは後段で別に判定する。
_CHANGELOG_HEADING_RE = re.compile(
    r"^## \[(?P<version>[^\]]+)\](?P<rest>.*)$", re.MULTILINE
)
# 見出し末尾の ` - YYYY-MM-DD`。`rest` を strip したものに当てる。
_HEADING_DATE_RE = re.compile(r"^-\s+(?P<date>\d{4}-\d{2}-\d{2})$")


@dataclass(frozen=True)
class ChangelogHeading:
    """CHANGELOG.md の `## [...]` 見出し 1 行。

    `raw_date` は書式 (`YYYY-MM-DD`) だけを満たした文字列で、暦日として妥当か
    (`2026-13-45` でないか) は検査時に判定する。`trailing` は version の後ろに
    続く文字列 (前後 strip 済み) で、「日付が無い」(`## [Unreleased]`) と
    「日付の書式が壊れている」(`## [0.4.0] - TBD`) を区別するために持つ。
    """

    version: str
    raw_date: str | None
    trailing: str


def parse_changelog_headings(text: str) -> list[ChangelogHeading]:
    """CHANGELOG 本文から `## [...]` 見出しを出現順に**全て**取り出す。"""
    headings: list[ChangelogHeading] = []
    for match in _CHANGELOG_HEADING_RE.finditer(text):
        trailing = match.group("rest").strip()
        date_match = _HEADING_DATE_RE.match(trailing)
        headings.append(
            ChangelogHeading(
                version=match.group("version"),
                raw_date=date_match.group("date") if date_match else None,
                trailing=trailing,
            )
        )
    return headings


def _release_order_key(version: str) -> tuple[int, int, int, int] | None:
    """`X.Y.Z` (+ pre-release / build 識別子) を比較可能なタプルにする。

    `Unreleased` のような非リリース節は `None` を返して順序比較から外す。
    第 4 要素は「正式リリースなら 1、pre-release 識別子付きなら 0」で、同一 core の
    `0.4.0-rc1` を `0.4.0` より**下位**に置く。これがないと `0.4.0-rc1` を持つ
    CHANGELOG で `v0.4.0` を打てなくなる (false-red)。

    **近似であることの明示**: pre-release 同士の順序 (`rc1` < `rc2`) は見ない
    (同値として扱うので `rc2` の打ち直しは重複扱いで落ちる)。本 repo は
    CHANGELOG に pre-release 節を持たないため実害が無い範囲で単純化している。
    """
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?P<suffix>[-+].+)?", version)
    if match is None:
        return None
    return (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3)),
        0 if match.group("suffix") else 1,
    )


def parse_reference_date(raw: str) -> date:
    """ISO8601 の時刻を `Asia/Tokyo` の暦日へ変換する。

    offset を持たない値は**推測せずに落とす**。naive な値を UTC / JST のどちらかと
    見なす実装は、本検査が潰そうとしている「1 日ずれ」を検査側で再生産する。
    """
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise VersionProbeError(
            f"--changelog-date-from を ISO8601 として解釈できません ({raw!r}): {exc}"
        ) from exc
    if moment.tzinfo is None:
        raise VersionProbeError(
            f"--changelog-date-from には UTC オフセット付きの ISO8601 が必要です "
            f"({raw!r})。オフセットの無い値を UTC / JST のどちらかとして推測すると、"
            f"本検査が防ごうとしている 1 日ずれを検査側で作り込むことになる"
        )
    return moment.astimezone(CHANGELOG_TIMEZONE).date()


def check_changelog_heading(
    repo_root: Path,
    expected_version: str,
    reference_date: date | None,
) -> list[str]:
    """CHANGELOG.md の対象バージョン見出しを検査する (#948 / #918 item3)。

    戻り値は `::error::` として出す問題の一覧 (空 = 合格)。CHANGELOG.md 自体を
    読めない場合は `VersionProbeError` (呼び出し側が exit 2 に倒す)。

    `reference_date` は**タグを打つ日** を `Asia/Tokyo` の暦日で表したもの。
    `None` のときは日付の**値**を比較せず、日付欄が存在することだけを見る
    (`/release` のバンプ手順は、タグを打つ日より前に手元で走ることがあるため)。

    **この検査が見ていない集合** (spec §5.2 G2-0 の共通処方。列挙できない検査は
    「網羅している」と誤読されるため入れない):

    * **`--tag` 指定時しか発火しない。** `release.yml` は tag push でのみ `--tag`
      を付けるため、PR / `workflow_dispatch` / branch push では 1 度も走らない。
      Track D の PR 段階は緑のままで、タグ push で初めて赤になる
    * **`--changelog-date-from` を渡さなければ日付の値は見ない。** 呼び出し側が
      引数を落とすと構造チェックまで縮退する。退化の検知は
      `tests/scripts/test_check_version_consistency.py` の release.yml 配線 pin
      に依存しており、本関数自身は検知できない
    * **基準日は呼び出し側が渡した値でしかない。** `release.yml` は annotated tag
      の `taggerdate` (= タグを打った時刻) を渡すが、本関数はそれが本当にタグ
      作成時刻かを検証できない。commit 日時のような別の値を渡されれば、それを
      「正」として比較する
    * **日付以外の中身は検査しない。** 主要変更点 / breaking changes / リンク
      定義の欠落は `docs/release-process.md` §共通項目 の人手チェックのまま
    * **対象バージョン以外の節の日付は見ない。** 既リリース節が後から書き換え
      られても検知しない (D7 の「既リリース済み節を触らせない」は運用規約で
      あって検査ではない)
    * **pre-release 同士の順序は見ない。** `0.4.0-rc1` と `0.4.0-rc2` は同値として
      扱う (`_release_order_key` 参照)。`Unreleased` のように `X.Y.Z` で始まらない
      節は順序比較の対象外
    * **CHANGELOG.md だけを触る PR では `release.yml` が起動しない**
      (`pull_request.paths` に CHANGELOG.md が無い)。ただし本 script の test は
      `ci.yml` の `pytest` に載る
    """
    path = repo_root / CHANGELOG_PATH
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise VersionProbeError(f"{path}: 読み込めません ({exc})") from exc

    headings = parse_changelog_headings(text)
    matched = [heading for heading in headings if heading.version == expected_version]

    if not matched:
        listed = ", ".join(heading.version for heading in headings) or "(見出しなし)"
        return [
            f"{CHANGELOG_PATH}: バージョン {expected_version} の節がありません "
            f"(検出した見出し: {listed})"
        ]
    if len(matched) > 1:
        # 同じ版の節が複数あると、どれを検査すべきか決められない。打ち直し
        # (既リリース版の再タグ) もここで捕まる。
        return [
            f"{CHANGELOG_PATH}: バージョン {expected_version} の節が "
            f"{len(matched)} 個あります (1 個であるべき)"
        ]

    problems: list[str] = []
    heading_date: date | None = None
    raw_date = matched[0].raw_date

    if raw_date is None:
        # 「日付欄が無い」と「日付欄はあるが書式が壊れている」を区別する。後者を
        # 前者と同じ文言にすると、リリース当日に原因を探す時間が生まれる。
        detail = (
            "日付がありません"
            if not matched[0].trailing
            else f"日付として読めない文字列が続いています ({matched[0].trailing!r})"
        )
        problems.append(
            f"{CHANGELOG_PATH}: 見出し `## [{expected_version}]` に{detail} "
            f"(`## [{expected_version}] - YYYY-MM-DD` の形で、タグを打つ日を "
            f"{CHANGELOG_TIMEZONE_NAME} で書く)"
        )
    else:
        try:
            heading_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            problems.append(
                f"{CHANGELOG_PATH}: 見出しの日付 {raw_date!r} が暦日として不正です"
            )

    if heading_date is not None and reference_date is not None:
        if heading_date != reference_date:
            problems.append(
                f"{CHANGELOG_PATH}: 見出し日付 {heading_date.isoformat()} が "
                f"タグを打つ日 {reference_date.isoformat()} "
                f"({CHANGELOG_TIMEZONE_NAME}) と一致しません"
            )

    problems.extend(_check_bump_direction(expected_version, headings))
    return problems


def _check_bump_direction(
    expected_version: str, headings: list[ChangelogHeading]
) -> list[str]:
    """既存の最新リリースより新しいバージョンであることを見る (#918 item3)。

    比較対象を CHANGELOG から採るのは、`version-check` job の checkout が
    `fetch-depth: 1` で **git 履歴を持たない**ため (`git describe HEAD^` が
    `fatal: Not a valid object name` で落ちることを実測済み)。呼び出し側が
    比較対象を渡す形にすると、渡し忘れで検査が静かに消える。
    """
    target = _release_order_key(expected_version)
    if target is None:
        return []

    others: list[tuple[tuple[int, int, int, int], str]] = []
    for heading in headings:
        if heading.version == expected_version:
            continue
        key = _release_order_key(heading.version)
        if key is not None:
            others.append((key, heading.version))

    if not others:
        # 初回リリース (比較対象なし)。
        return []

    highest_key, highest_version = max(others)
    if target <= highest_key:
        return [
            f"{CHANGELOG_PATH}: バンプ方向が不正です — タグ {expected_version} は "
            f"既存の最新リリース {highest_version} より新しくありません"
        ]
    return []


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
        "--changelog-date-from",
        default=None,
        metavar="ISO8601",
        help="CHANGELOG 見出し日付の基準となる時刻 (UTC オフセット必須)。"
        f"{CHANGELOG_TIMEZONE_NAME} へ変換した暦日と突合する。--tag と併用する "
        "(省略時は日付欄の有無だけを見る)",
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

    if args.changelog_date_from is not None and args.tag is None:
        # 日付検査は --tag 指定時のみ発火する。基準日だけ渡されている状態は
        # 「検査させたいのに発火しない」呼び出し側の配線ミスなので、0 で通すと
        # release.yml がこの形へ退化しても気付けない (false-green)。
        print(
            "::error::--changelog-date-from は --tag と併用してください "
            "(単独指定では CHANGELOG 日付検査が発火しません)"
        )
        return 2

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

        # CHANGELOG 見出し日付 / バンプ方向 (#948 / #918)。--tag 指定時のみ発火。
        try:
            reference_date = (
                parse_reference_date(args.changelog_date_from)
                if args.changelog_date_from is not None
                else None
            )
            changelog_problems = check_changelog_heading(
                args.repo_root, expected, reference_date
            )
        except VersionProbeError as exc:
            print(f"::error::CHANGELOG 検査に失敗しました: {exc}")
            return 2

        if reference_date is not None:
            # どの日付を「正」として比較したかを release 当日のログに残す。
            print(
                f"CHANGELOG 見出し日付の基準日: {reference_date.isoformat()} "
                f"({CHANGELOG_TIMEZONE_NAME}, from {args.changelog_date_from})"
            )
        for problem in changelog_problems:
            print(f"::error::{problem}")
        if changelog_problems:
            failed = True

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
