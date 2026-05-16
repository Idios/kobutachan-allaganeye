#!/usr/bin/env python3
"""Extract a single version's section from CHANGELOG.md for GitHub Release notes."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def extract(version: str, source: Path) -> str:
    text = source.read_text(encoding="utf-8")
    pattern = rf"## \[{re.escape(version)}\].*?(?=\n## \[|\Z)"
    match = re.search(pattern, text, re.DOTALL)
    if not match:
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
