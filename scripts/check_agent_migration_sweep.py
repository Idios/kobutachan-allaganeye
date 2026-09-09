#!/usr/bin/env python3
"""Check the Claude Code → Zed+DeepSeek agent migration sweep is complete (#1041/#1042).

Detects "old terminology" (skill slash commands / old path `.claude/skills` /
old filename `CLAUDE.md`) that remains in **living docs**, to prevent the
incomplete-sweep recurrence seen in PR #1051 Round 4/5 (session-start.sh /
docs/versioning.md に slash 残存を個別に拾う事象)。

再発防止の設計意図:
- 用語 sweep は「まとめて置換」だけでは漏れる (対象ファイルの取りこぼし)。
  本 check は **旧用語が living doc に残っていれば fail** するため、sweep の
  完全性を CI で担保する。

検査対象 = living doc のみ (`docs/l2-workflow.md` §「歴史記録の扱い」#854 R2 の
整合対象と同一方針):
  - 拡張子 `.md` / `.sh` のファイル (docs / skill / hook / AGENTS.md / README)。
  - コードファイル (`.py` / `.js` / `.ts` / `.rs` / `.ps1` / `.yml` 等) は対象外。
    コードコメントの旧参照 (GUI ソースの `CLAUDE.md` / `// … /iterate-review Round N`
    等の歴史記録) は棚卸 #1044 に回す。
  - 履歴記録 (`CHANGELOG.md` / eval レポート / dated plans・specs / archive /
    audits) も対象外。

exit code: 0 = clean / 1 = 旧用語残存 (sweep 未完了) / 2 = 検査自体が壊れている。
"""

from __future__ import annotations

import fnmatch
import re
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_STRUCTURAL = 2

# --------------------------------------------------------------------------
# 旧用語 (migration target の old 側)
# --------------------------------------------------------------------------

# slash command (Claude Code) → Zed skill name / CLI。
# `(?<![a-z0-9._-])` + `(?![a-z0-9._-])` で「前後が path/単語文字でない」ことを要求し、
# `.agents/skills/review-pr/SKILL.md` (path 中の /review-pr) や
# `refs/heads/release/vX` (branch 名) を誤検出しない。
_SLASH_SKILLS = [
    "review-pr",
    "iterate-review",
    "release",
    "scope-guard",
    "close-issue",
    "create-task",
    "enforce-acceptance-criteria",
    "test-pr",
]
_SLASH_RE = re.compile(
    r"(?<![a-z0-9._-])/(" + "|".join(_SLASH_SKILLS) + r")(?![a-z0-9._-])"
)

# 旧 path / 旧 filename (literal 一致)
_LITERAL_TERMS = [
    ".claude/skills",
    "CLAUDE.md",
]

# --------------------------------------------------------------------------
# 検査対象と除外
# --------------------------------------------------------------------------

# living doc = doc / skill / hook のみ (コードファイルは #1044 へ)
_SCAN_EXTS = {".md", ".sh"}

_SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
    "dist",
    "target",
    "output",
    ".mypy_cache",
}

# historical record / deferred: 遡及書き換えしない (棚卸 #1044 / 歴史記録 #854 R2)
_EXCLUDED_GLOBS = [
    "CHANGELOG.md",
    ".agents/skills/**/eval/**",
    "docs/superpowers/**",
    "docs/archive/**",
    "docs/audits/**",
    "gui/**",
]


def _is_excluded(rel: Path) -> bool:
    rel_s = rel.as_posix()
    return any(fnmatch.fnmatch(rel_s, g) for g in _EXCLUDED_GLOBS)


def _iter_living_docs(repo_root: Path):
    for path in sorted(repo_root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(repo_root)
        parts = rel.parts
        if any(part in _SKIP_DIRS for part in parts):
            continue
        if path.suffix.lower() not in _SCAN_EXTS:
            continue
        if _is_excluded(rel):
            continue
        yield path, rel


def check_sweep(repo_root: Path) -> list[str]:
    """Return human-readable violations (each = "path:line: text")."""
    violations: list[str] = []
    for path, rel in _iter_living_docs(repo_root):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary / unreadable → not a text doc
        for lineno, line in enumerate(text.splitlines(), 1):
            if _SLASH_RE.search(line):
                violations.append(f"{rel}:{lineno}: slash command 残存: {line.strip()}")
            for term in _LITERAL_TERMS:
                if term in line:
                    violations.append(
                        f"{rel}:{lineno}: 旧表記残存 ({term}): {line.strip()}"
                    )
    return violations


def main(argv: list[str] | None = None) -> int:
    import argparse

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

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    if not (repo_root / "AGENTS.md").exists():
        print(
            "ERROR: 検査自体が壊れている: AGENTS.md が見つからない "
            f"(repo root が誤っている?: {repo_root})",
            file=sys.stderr,
        )
        return EXIT_STRUCTURAL

    violations = check_sweep(repo_root)

    if violations:
        print(
            "ERROR: agent migration sweep が未完了 (旧用語が living doc に残存)。\n",
            file=sys.stderr,
        )
        for v in violations:
            print(v, file=sys.stderr)
        print(
            "\nslash command は skill 名へ、`.claude/skills` は `.agents/skills` へ、"
            "`CLAUDE.md` は `AGENTS.md` へ置換すること。\n"
            "コードファイル / CHANGELOG / eval / dated plans・specs は対象外 (#1044)。",
            file=sys.stderr,
        )
        return EXIT_DRIFT

    print("OK: agent migration sweep は完了 (旧用語の living doc 残存なし)")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
