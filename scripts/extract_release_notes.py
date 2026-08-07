#!/usr/bin/env python3
r"""Extract a single version's section from CHANGELOG.md for GitHub Release notes.

見出しは `## [x.y.z] - YYYY-MM-DD` の形を要求する (#948)。日付は**タグを打つ日**を
`Asia/Tokyo` で表した値という規約 (`docs/release-process.md` §タグ運用、裁定 D6)。

**この検査が見ていない集合**:

* 日付が**書式として存在するか**しか見ない。値が規約どおり (= タグを打つ日) かは
  `scripts/check_version_consistency.py --tag` 側にしかなく、両者は別 job・別発火
  条件である。逆に、日付さえ書式通りなら本文が空でも通る
* 日付を必須にしたのは**節の開始側だけ**である。終端の lookahead は
  `(?=\n## \[|\Z)` のまま変更しない — `## [Unreleased]` は Keep a Changelog の
  慣行で常に先頭に置かれるので version 節の終端には現れず、ここを締めても防げる
  事故が無い一方、締め方を誤ると Release 本文の範囲が黙って変わる (#948 の
  「終端 lookahead を厳格化するかを明示的に判断して記録する」への回答)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# 見出し日付。`YYYY-MM-DD` のゼロ埋め固定 (`2026-8-7` や `TBD` は通さない)。
_HEADING_DATE = r"\d{4}-\d{2}-\d{2}"


def extract(version: str, source: Path) -> str:
    text = source.read_text(encoding="utf-8")
    # 行頭アンカー + 日付必須。`re.MULTILINE` は `^`、`re.DOTALL` は節本文を
    # 改行込みで拾うために要る。
    pattern = rf"^## \[{re.escape(version)}\] - {_HEADING_DATE}.*?(?=\n## \[|\Z)"
    match = re.search(pattern, text, re.DOTALL | re.MULTILINE)
    if not match:
        if re.search(rf"^## \[{re.escape(version)}\]", text, re.MULTILINE):
            raise SystemExit(
                f"CHANGELOG section for version {version} has no release date: "
                f"expected '## [{version}] - YYYY-MM-DD' where the date is the day "
                "the tag is cut (Asia/Tokyo). See docs/release-process.md §タグ運用."
            )
        raise SystemExit(f"No CHANGELOG section for version {version}")
    return match.group(0).strip()


def main(argv: list[str]) -> None:
    if len(argv) != 3:
        print(
            "Usage: extract_release_notes.py <version> <output_path>",
            file=sys.stderr,
        )
        raise SystemExit(2)
    version = argv[1]
    output = Path(argv[2])
    source = Path("CHANGELOG.md")
    notes = extract(version, source)
    output.write_text(notes + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv)
