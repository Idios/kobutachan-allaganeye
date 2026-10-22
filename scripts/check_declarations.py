#!/usr/bin/env python3
"""宣言カタログ (`docs/declaration-catalog.md`) の自己整合を検査する。

`docs/coding-conventions.md` §ドキュメント SSoT 規約 が定める「正 1 箇所 +
複製 spot」の台帳が、実 tree と食い違っていないかを検査する。台帳そのものが
腐ると「登録したのに誰も見ていない」= no-op になるため、本 script は
**台帳の各セルが実在するか** と **active と宣言した gate が実装済みか** を見る。

    python scripts/check_declarations.py [--repo-root DIR] [--catalog PATH]

exit code:

* 0 -- 台帳が自己整合
* 1 -- 台帳と実 tree が食い違う (SSoT / mirror / gate の解決失敗)
* 2 -- 構造エラー (header 不在 / 走査 0 行 / セル数不一致)

1 と 2 を分けるのは `scripts/check_version_consistency.py` と同じ理由による。
台帳の行を 1 つ消しても本 script は 0 を返す (行の削除は「未登録クラス」であって
drift ではない) ため、**id 集合は `tests/scripts/test_check_declarations.py` が pin する**。
片方だけでは「台帳の腐り」と「クラスの消失」を区別できない。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

COLUMNS = ["id", "事実", "SSoT", "複製 spot", "mode", "gate", "status"]
MODES = {"generated", "checked", "runtime-extract", "prose-only"}
ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
STATUS_RE = re.compile(r"^(active|planned:[0-9]+)$")
GATE_RE = re.compile(
    r"^(none|ci:[^:]+(?::.+)?|script:([^:]+)::([A-Za-z_][A-Za-z0-9_]*))$"
)


class StructureError(Exception):
    """台帳そのものを読めない状態 (drift ではない)。"""


def parse_catalog(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise StructureError(f"catalog not found: {path}")
    rows: list[dict[str, str]] = []
    header_seen = False
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not header_seen:
            if cells == COLUMNS:
                header_seen = True
            continue
        if all(set(c) <= set("-: ") for c in cells):
            continue
        if len(cells) != len(COLUMNS):
            raise StructureError(
                f"line {lineno}: expected {len(COLUMNS)} cells, got {len(cells)}"
            )
        rows.append(dict(zip(COLUMNS, cells, strict=True)))
    if not header_seen:
        raise StructureError("table header not found")
    if not rows:
        raise StructureError("scan produced zero rows (checker is broken)")
    return rows


def _job_exists(root: Path, job: str, step: str | None) -> tuple[bool, str]:
    for wf in sorted((root / ".github" / "workflows").glob("*.yml")):
        text = wf.read_text(encoding="utf-8")
        if not re.search(rf"^  {re.escape(job)}:\s*$", text, re.M):
            continue
        if step is None or step in text:
            return True, ""
        return False, f"step not found in {wf.name}: {step}"
    return False, f"job not found in workflows: {job}"


def _check_gate(
    gate: str, root: Path, gate_root: Path, row: dict[str, str], where: str
) -> list[str]:
    problems: list[str] = []
    m = GATE_RE.match(gate)
    if not m:
        return [f"{where}: bad gate {gate!r}"]
    if m.group(2):
        script = gate_root / m.group(2)
        if not script.is_file():
            problems.append(f"{where}: gate script missing: {m.group(2)}")
        elif row["status"] == "active":
            body = script.read_text(encoding="utf-8")
            if not re.search(rf"^def {re.escape(m.group(3))}\(", body, re.M):
                problems.append(
                    f"{where}: active gate function not implemented: {m.group(3)}"
                )
    if gate.startswith("ci:"):
        _, job, *rest = gate.split(":", 2)
        ok, why = _job_exists(root, job, rest[0] if rest else None)
        if not ok:
            problems.append(f"{where}: {why}")
    return problems


def check(root: Path, rows: list[dict[str, str]], gate_root: Path) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    for i, row in enumerate(rows, 2):
        rid = row["id"]
        where = f"row {i} ({rid})"
        if not ID_RE.match(rid):
            problems.append(f"{where}: id is not kebab-case")
        if rid in seen:
            problems.append(f"{where}: duplicate id")
        seen.add(rid)

        if row["mode"] not in MODES:
            problems.append(f"{where}: unknown mode {row['mode']!r}")
        if not STATUS_RE.match(row["status"]):
            problems.append(f"{where}: bad status {row['status']!r}")

        gates = [g.strip() for g in row["gate"].split("+")]
        if row["mode"] == "prose-only":
            if gates != ["none"]:
                problems.append(f"{where}: prose-only must use gate none")
        elif "none" in gates:
            problems.append(f"{where}: non-prose row must declare a gate")
        for gate in gates:
            if gate != "none":
                problems.extend(_check_gate(gate, root, gate_root, row, where))

        ssot = row["SSoT"]
        if not (root / ssot).exists():
            problems.append(f"{where}: SSoT path missing: {ssot}")
        for mirror in [x.strip() for x in row["複製 spot"].split(",") if x.strip()]:
            if mirror == "-":
                continue
            target = mirror.rstrip("/")
            if "*" in target:
                if not list(root.glob(target)):
                    problems.append(f"{where}: mirror glob matches nothing: {mirror}")
            elif not (root / target).exists():
                problems.append(f"{where}: mirror missing: {mirror}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--catalog", default="docs/declaration-catalog.md")
    ap.add_argument("--gate-root", default=None)
    args = ap.parse_args()
    root = Path(args.repo_root).resolve()
    gate_root = Path(args.gate_root).resolve() if args.gate_root else root
    try:
        rows = parse_catalog(root / args.catalog)
    except StructureError as exc:
        print(f"structure error: {exc}", file=sys.stderr)
        return 2
    problems = check(root, rows, gate_root)
    active = sum(1 for r in rows if r["status"] == "active")
    if problems:
        for p in problems:
            print(f"::error::{p}")
        return 1
    print(
        f"OK: {len(rows)} declarations ({active} active / {len(rows) - active} planned)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
