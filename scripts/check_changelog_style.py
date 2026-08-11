#!/usr/bin/env python3
r"""CHANGELOG entry が記述規約に従っているかを検査する (#952)。

`.github/workflows/ci.yml` の `changelog-style` job から引数なしで呼ばれる。
標準ライブラリのみを使う (CI job に pip install を持たせないため)。

    python scripts/check_changelog_style.py [--changelog PATH]

exit code:

* 0 -- 規約を満たす
* 1 -- 規約違反 (CHANGELOG を直す)
* 2 -- 構造エラー (CHANGELOG 欠損 / 走査対象セクションが 0 件)

1 と 2 を分けるのは `scripts/check_version_consistency.py` /
`scripts/check_doc_code_refs.py` と同じ理由による。「違反している」と「検査自体が
壊れた」を CI ログ上で区別するためで、見出し書式を変えた改稿で走査対象が 0 件に
なったときに「0 件と 0 件が一致した」で緑を返すと、ガードが無いより有害になる。

**規約の正 (SSoT) は [`docs/release-process.md`](../docs/release-process.md)
§CHANGELOG entry の記述規約 である。** 本 docstring はその要約と、実装上の
判定規則を述べるに留める。両者が食い違ったら doc を正とする。

## 走査対象 (scope)

`## [Unreleased]` セクション**のみ**。無い場合は最新 (ファイル先頭に最も近い)
`## [x.y.z] - YYYY-MM-DD` セクションのみ。**両方を同時に見ることはしない。**

- 既リリース済みセクションを見ないのは裁定 D7 (既リリース節不可侵) のため。
  v0.3.0 の `### Added` は内部段階名を 14 箇所含む (2026-08-11 実測:
  V0x2 / V1x1 / V2x2 / V3x2 / V4x2 / anchor x3 / presence x2) が、公開済みの
  Release 本文は CHANGELOG を直しても再生成されないので歴史記録として残す
- `## [Unreleased]` が無いときに最新 version セクションへ落ちるのは、PR-D1 が
  `## [Unreleased]` を `## [x.y.z] - <date>` へ改名した直後も検査を継続させる
  ため。ここが抜けると **release 直前の 1 手で無検査になる**

## 検査する 2 つの契約

**V1 (禁止内部用語)** 走査対象セクションの本文に、アルゴリズムの段階名・内部
識別子が出現しないこと。読者は FF14 プレイヤーであり、これらの語で自分の症状を
検索しない。語彙は `FORBIDDEN_TERMS` で人手管理する。

**V2 (`### Internal` 節)** 走査対象セクションが `### Internal` を持たないこと
(裁定 R9)。`scripts/extract_release_notes.py` は version セクションを**丸ごと**
Release 本文にするため、内部変更を書くと読者に届く。内部作業の記録は PR と
issue に残す。過去バージョンの `### Internal` は歴史記録として残す。

## マスクする範囲 (false-red を出さないため)

規約は「詳細は spec / doc へのリンクで送れ」と定めている。ところが送り先の
**ファイル名自体に内部段階名が入っている** (実在例:
`docs/superpowers/specs/2026-07-11-issue-822-masked-oversplit-anchor-design.md`)。
リンク先を検査対象にすると規約が自分の推奨を罰するので、以下を走査前に
**同じ長さの空白へ置換**する (長さを保つので行番号がずれない)。

* fenced code block の中身 (出力例をそのまま貼る用途を守る)
* markdown リンクの destination (`](...)` の中身)
* 裸の URL (`http://` / `https://` で始まる連続非空白)
* **path 風の inline code** — backtick span のうち `/` を含むか既知の拡張子で
  終わるもの。ファイルパスは「実装の場所」であって読者向けの説明語ではない

## この gate が見ていない集合

**形と語彙しか見ない。** 以下は構造的に検査外である。

* **entry の内容が正しいか** — 書かれた振る舞いが実装と一致するかは見ない
* **書くべき entry が欠けているか** — 「利用者に見える変更なのに entry が無い」は
  検出できない。これは doc 側の「非実施時の記録義務」(PR 本文に 1 行) と Track D
  の確認で担保する**人手ゲート**である。本 script は代替にならない
* **entry の長さ・リンクの有無** — 規約は「利用者向け 2-3 行 + 必要なら spec への
  リンク」と定めるが、行数もリンク有無も検査しない。機械化すると箇条書きの
  折り返しや複数段落で false-red が多発し、規約ごと形骸化する
* **既リリース済みセクション** — 上記 scope のとおり
* **禁止語のリスト漏れ** — `FORBIDDEN_TERMS` は人手管理。新しい内部段階名が
  生まれても自動では追加されない。段階名を導入する PR が自分で足す
* **マスクした範囲の中身** — code block や path 内の語は一切見ない。読者向けの
  散文に見せかけて path 風 backtick に埋めれば通る

Refs: https://github.com/Idios/kobutachan-allaganeye/issues/952
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# V1: 禁止内部用語
# --------------------------------------------------------------------------

# (label, pattern)。label は違反報告にそのまま出す。
#
# `V0`-`V4` だけ **case-sensitive** にしてある。case-insensitive にすると
# `v0.3.1` のようなバージョン文字列に当たって全 entry が red になる。後続の
# `(?!\.)` は `V0.3.1` 形 (大文字表記のバージョン) を除くため。
FORBIDDEN_TERMS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("V0-V4 (アルゴリズム段階名)", re.compile(r"\bV[0-4]\b(?!\.)")),
    ("quorum", re.compile(r"\bquorum\b", re.IGNORECASE)),
    ("anchor", re.compile(r"\banchors?\b", re.IGNORECASE)),
    ("presence", re.compile(r"\bpresence\b", re.IGNORECASE)),
    ("tri-state", re.compile(r"\btri-state\b", re.IGNORECASE)),
)

# 走査対象セクションの見出し。`_ANY_H2_RE` で「最初の h2」を取ってから
# `_UNRELEASED_RE` / `_VERSION_RE` で分類する (find_scannable_section の docstring
# にある false-green を避けるため、分類に失敗したら fail へ倒す)。
_ANY_H2_RE = re.compile(r"^## .*$", re.MULTILINE)
_UNRELEASED_RE = re.compile(r"^## \[Unreleased\]$")
_VERSION_RE = re.compile(r"^## \[\d+\.\d+\.\d+\] - \d{4}-\d{2}-\d{2}.*$")
# 節の終端は「次の h2 全般」。`^## \[` に限ると、次の節の見出し書式が壊れた場合に
# 走査範囲がそこを越えて広がる。
_NEXT_SECTION_RE = re.compile(r"^## ", re.MULTILINE)
_INTERNAL_HEADING_RE = re.compile(r"^### Internal\s*$", re.MULTILINE)

# fenced code block の開始 / 終了行 (``` または ~~~、先頭 3 文字までのインデント可)。
_FENCE_RE = re.compile(r"^[ \t]{0,3}(?P<fence>`{3,}|~{3,})(?P<info>.*)$")

# マスク対象。
_LINK_DEST_RE = re.compile(r"\]\(([^)]*)\)")
_BARE_URL_RE = re.compile(r"https?://\S+")
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_PATHISH_SUFFIXES = (
    ".md",
    ".py",
    ".ts",
    ".tsx",
    ".rs",
    ".json",
    ".yml",
    ".yaml",
    ".ps1",
    ".mjs",
    ".js",
    ".sh",
    ".txt",
    ".toml",
)


def mask_fenced_blocks(text: str) -> str:
    r"""fenced code block の中身を**同じ長さの空白**へ置き換える。

    `scripts/check_version_consistency.py` の `mask_fenced_blocks` および
    `scripts/extract_release_notes.py` の `_mask_fenced_blocks` と同じ処理を
    意図的に複製している。3 スクリプトは CI の別 job から独立に呼ばれるので、
    import で結合させない。3 者が一致することは
    `tests/scripts/test_check_version_consistency.py` の
    `test_mask_implementations_stay_in_sync` が固定する。

    閉じ判定は CommonMark の fenced code block 規則に従い、**文字種と開始時の
    長さの両方**を見る。
    """
    masked: list[str] = []
    fence_char: str | None = None
    fence_length = 0
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        newline = line[len(body) :]
        marker = _FENCE_RE.match(body)
        if fence_char is None:
            if marker is not None:
                fence_char = marker.group("fence")[0]
                fence_length = len(marker.group("fence"))
                masked.append(" " * len(body) + newline)
                continue
            masked.append(line)
            continue
        if (
            marker is not None
            and marker.group("fence")[0] == fence_char
            and len(marker.group("fence")) >= fence_length
            and not marker.group("info").strip()
        ):
            fence_char = None
            fence_length = 0
        masked.append(" " * len(body) + newline)
    return "".join(masked)


def _blank_span(text: str, start: int, end: int) -> str:
    """``text[start:end]`` を改行を保ったまま空白へ置換する (長さ不変)。"""
    chunk = text[start:end]
    replaced = "".join("\n" if ch == "\n" else " " for ch in chunk)
    return text[:start] + replaced + text[end:]


def _is_pathish(inner: str) -> bool:
    """inline code の中身が「実装の場所」に見えるか。"""
    stripped = inner.strip()
    if "/" in stripped or "\\" in stripped:
        return True
    return stripped.endswith(_PATHISH_SUFFIXES)


def mask_non_prose(text: str) -> str:
    """散文でない範囲 (code / リンク先 / URL / path 風 backtick) を空白化する。

    長さを保つので、返り値上で得た offset を元テキストの行番号へそのまま使える。
    """
    masked = mask_fenced_blocks(text)
    for match in _LINK_DEST_RE.finditer(masked):
        masked = _blank_span(masked, match.start(1), match.end(1))
    for match in _BARE_URL_RE.finditer(masked):
        masked = _blank_span(masked, match.start(), match.end())
    for match in _INLINE_CODE_RE.finditer(masked):
        if _is_pathish(match.group(1)):
            masked = _blank_span(masked, match.start(1), match.end(1))
    return masked


def find_scannable_section(
    text: str,
) -> tuple[tuple[str, int, int] | None, str | None]:
    """走査対象セクションの ``((label, start, end), None)`` を返す。

    失敗時は ``(None, reason)``。**必ずどちらか一方だけが非 None** になる。

    判定は「**最初の `## ` 見出しを分類する**」形で行う。「最初に見つかる
    *正しい書式の* version 見出しを探す」実装にすると、最新セクションの見出し
    書式が壊れたときに **さらに古いセクションを拾って緑を返す** (実装時に実測で
    踏んだ false-green。`## [Unreleased]` と `## [0.3.0] - ...` を崩した
    CHANGELOG が `## [0.2.1]` を検査して OK と報告した)。古い節は既リリースで
    違反が無いことが多いため、検査対象が黙って過去へ移ったことに気づけない。

    `## [Unreleased]` を優先し、無ければ最新 version セクションを見る。
    **両方を見ることはしない** (docstring §走査対象 の理由)。
    """
    scannable = mask_fenced_blocks(text)
    head = _ANY_H2_RE.search(scannable)
    if head is None:
        return None, (
            "走査対象セクションが 0 件: '## ' 見出しが 1 つも無い。"
            "CHANGELOG の構造が壊れている"
        )

    heading = head.group(0).strip()
    if _UNRELEASED_RE.match(heading):
        label = "## [Unreleased]"
    elif _VERSION_RE.match(heading):
        label = heading
    else:
        return None, (
            f"最新セクションの見出しが認識できない書式: {heading!r} -- "
            "'## [Unreleased]' か '## [x.y.z] - YYYY-MM-DD' のいずれかである必要が "
            "ある。書式を変えるなら docs/release-process.md §CHANGELOG entry の"
            "記述規約 と本 script を同時に更新すること "
            "(古いセクションへ fall through して緑を返さないため、ここは fail に "
            "倒してある)"
        )

    body_start = head.end()
    nxt = _NEXT_SECTION_RE.search(scannable, body_start)
    return (label, body_start, nxt.start() if nxt else len(text)), None


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def scan(text: str) -> tuple[list[str], str | None]:
    """規約違反を列挙する。``(violations, structural_error)`` を返す。"""
    section, reason = find_scannable_section(text)
    if section is None:
        return [], reason
    label, start, end = section
    prose = mask_non_prose(text)[start:end]
    raw = mask_fenced_blocks(text)[start:end]
    violations: list[str] = []

    for term_label, pattern in FORBIDDEN_TERMS:
        for match in pattern.finditer(prose):
            line = _line_of(text, start + match.start())
            violations.append(
                f"CHANGELOG.md:{line}: {label} に内部用語 '{match.group(0)}' "
                f"({term_label}) がある -- 利用者向けの語に置き換え、詳細は "
                f"spec へのリンクで送る"
            )

    for match in _INTERNAL_HEADING_RE.finditer(raw):
        line = _line_of(text, start + match.start())
        violations.append(
            f"CHANGELOG.md:{line}: {label} に '### Internal' 節がある -- "
            f"新規バージョンでは使わない (Release 本文へ丸ごと出る)。"
            f"内部変更の記録は PR / issue 側に残す"
        )

    return violations, None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--changelog",
        type=Path,
        default=Path("CHANGELOG.md"),
        help="検査する CHANGELOG のパス (既定: ./CHANGELOG.md)",
    )
    args = parser.parse_args(argv)

    if not args.changelog.is_file():
        print(f"ERROR: CHANGELOG が見つからない: {args.changelog}", file=sys.stderr)
        return 2

    text = args.changelog.read_text(encoding="utf-8")
    violations, structural = scan(text)

    if structural is not None:
        print(f"ERROR: {structural}", file=sys.stderr)
        return 2

    if violations:
        print("CHANGELOG entry が記述規約に違反している:", file=sys.stderr)
        for line in violations:
            print(f"  {line}", file=sys.stderr)
        print(
            "\n規約: docs/release-process.md §CHANGELOG entry の記述規約",
            file=sys.stderr,
        )
        return 1

    section, _ = find_scannable_section(text)
    assert section is not None  # structural is None なのでここは必ず取れる
    print(f"OK: {section[0]} は CHANGELOG entry の記述規約を満たす")
    return 0


if __name__ == "__main__":
    sys.exit(main())
