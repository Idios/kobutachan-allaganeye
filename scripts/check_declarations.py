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
from collections.abc import Callable
from pathlib import Path

COLUMNS = ["id", "事実", "SSoT", "複製 spot", "mode", "gate", "status"]
MODES = {"generated", "checked", "runtime-extract", "prose-only"}
ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
STATUS_RE = re.compile(r"^(active|planned:[0-9]+)$")
GATE_RE = re.compile(
    r"^(none|ci:[^:]+(?::.+)?|script:([^:]+)::([A-Za-z_][A-Za-z0-9_]*))$"
)

# `script:` gate の実体。catalog の gate 名と 1:1 で登録する。
# 名前だけ合っていて実体が無い状態を compile 時に気づけるよう、登録は明示的に行う。
_GATES: dict[str, Callable[[Path], list[str]]] = {}

_BUILTIN_OPTIONS = {"--help", "--install-completion", "--show-completion"}
_LINE_REF_RE = re.compile(r"`([A-Za-z0-9_./-]+\.(?:py|md|sh|ts|tsx|yml|rs)):\d+")
# 記入例 (`path/to/file.py:123`) は実在参照ではないので対象外。
_LINE_REF_PLACEHOLDERS = ("path/to/",)
_LINE_REF_DOC_GLOBS = (
    "AGENTS.md",
    "docs/*.md",
    ".agents/skills/*/SKILL.md",
    ".claude/agents/*.md",
)
_EXIT_CODES_HEADING = "Exit Codes"


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


def _job_block(text: str, job: str) -> str | None:
    """workflow の text から job の block を切り出す (見つからなければ None)。

    job 名は 2 space indent の key で、job 内の key は 4 space 以降にしか
    現れない。step 名の探索を **job 内に限定する**ため、次の job 名
    (または EOF) までを 1 block として返す。
    """
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if re.fullmatch(rf"  {re.escape(job)}:\s*", line):
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.fullmatch(r"  [A-Za-z0-9_-]+:\s*", lines[j]):
            end = j
            break
    return "\n".join(lines[start:end])


def _job_exists(root: Path, job: str, step: str | None) -> tuple[bool, str]:
    for wf in sorted((root / ".github" / "workflows").glob("*.yml")):
        block = _job_block(wf.read_text(encoding="utf-8"), job)
        if block is None:
            continue
        if step is None or step in block:
            return True, ""
        return False, f"step not found in job {job} ({wf.name}): {step}"
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
            gate_fn = _GATES.get(m.group(3))
            if gate_fn is None:
                problems.append(
                    f"{where}: active gate function not implemented: {m.group(3)}"
                )
            else:
                problems.extend(gate_fn(root))
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


def _section(text: str, title: str) -> str:
    """`## title` / `### title` の節を、次の見出しまで切り出す。"""
    lines = text.splitlines()
    heading_re = re.compile(rf"^#{{2,4}} {re.escape(title)}$")
    start = next(
        (i for i, line in enumerate(lines) if heading_re.match(line.strip())), None
    )
    if start is None:
        return ""
    end = next(
        (i for i in range(start + 1, len(lines)) if re.match(r"^#{2,4} ", lines[i])),
        len(lines),
    )
    return "\n".join(lines[start:end])


def _documented_exit_codes(agents_text: str) -> set[int]:
    section = _section(agents_text, _EXIT_CODES_HEADING)
    return {int(m) for m in re.findall(r"^\|\s*(\d+)\s*\|", section, re.M)}


def _produced_exit_codes(root: Path) -> set[int]:
    """`exit_code = N` (例外クラス) と `typer.Exit(code=N)` (直接終了) を集める。

    正常終了 (0) は明示されないため初期値に含める。
    """
    produced = {0}
    for path in sorted((root / "allaganeye").rglob("*.py")):
        if "__pycache__" in path.as_posix():
            continue
        text = path.read_text(encoding="utf-8")
        produced |= {
            int(m) for m in re.findall(r"exit_code(?::\s*int)?\s*=\s*(\d+)", text)
        }
        produced |= {int(m) for m in re.findall(r"typer\.Exit\(code=(\d+)\)", text)}
    return produced


def check_exit_codes(root: Path) -> list[str]:
    """AGENTS.md の Exit Codes 表と実装が同じ集合を指すことを検査する。

    「実装にしか無い code」は利用者が遭遇しても文書で説明されない code、
    「表にしか無い code」は実装から消えたのに残った行で、どちらも
    表を信じた判断を誤らせる。
    """
    agents = root / "AGENTS.md"
    if not agents.is_file():
        return ["exit-codes: AGENTS.md が無い"]
    documented = _documented_exit_codes(agents.read_text(encoding="utf-8"))
    if not documented:
        return [
            "exit-codes: AGENTS.md の Exit Codes 表を読めない (走査 0 行 = 検査不能)"
        ]
    produced = _produced_exit_codes(root)
    problems: list[str] = []
    for code in sorted(produced - documented):
        problems.append(
            f"exit-codes: exit {code} は実装にあるが AGENTS.md §Exit Codes に"
            " undocumented"
        )
    for code in sorted(documented - produced):
        problems.append(
            f"exit-codes: exit {code} は AGENTS.md にあるが実装で never produced"
        )
    return problems


def _compare_cli_options(code_opts: set[str], doc_opts: set[str]) -> list[str]:
    problems: list[str] = []
    for opt in sorted(code_opts - doc_opts):
        problems.append(
            f"cli-options: {opt} は実装にあるが docs/cli-spec.md に not documented"
        )
    for opt in sorted(doc_opts - code_opts):
        problems.append(
            f"cli-options: {opt} は docs/cli-spec.md にあるが実装で not implemented"
        )
    return problems


def check_cli_options(root: Path) -> list[str]:
    """typer runtime registry の option 集合と `docs/cli-spec.md` を突合する。

    静的な regex 抽出では typer の宣言形（`typer.Option` の位置引数 /
    `Annotated`）を取りこぼすため、実際に登録された click command を読む
    (`scripts/check_feature_announcement.py` と同じ理由)。
    hidden command (`encoder-slots`) と typer 組み込み option は対象外。
    """
    doc = root / "docs" / "cli-spec.md"
    if not doc.is_file():
        return ["cli-options: docs/cli-spec.md が無い"]
    try:
        import typer.main

        sys.path.insert(0, str(root))
        from allaganeye.cli import app
    except Exception as exc:  # pragma: no cover - 環境依存
        return [
            f"cli-options: CLI registry を読めない ({exc!r})。"
            " pip install -e . -c constraints.txt が必要"
        ]

    group = typer.main.get_command(app)
    code_opts: set[str] = set()

    def _collect(params: list[object]) -> set[str]:
        found: set[str] = set()
        for param in params:
            opts = list(getattr(param, "opts", [])) + list(
                getattr(param, "secondary_opts", [])
            )
            found |= {opt for opt in opts if opt.startswith("--")}
        return found

    for command in getattr(group, "commands", {}).values():
        if getattr(command, "hidden", False):
            continue
        code_opts |= _collect(list(getattr(command, "params", [])))
    code_opts |= _collect(list(getattr(group, "params", [])))
    code_opts -= _BUILTIN_OPTIONS

    doc_opts = set(
        re.findall(r"`(--[a-z0-9][a-z0-9-]*)", doc.read_text(encoding="utf-8"))
    )
    doc_opts -= _BUILTIN_OPTIONS
    return _compare_cli_options(code_opts, doc_opts)


def check_line_refs(root: Path) -> list[str]:
    """living doc の行番号参照 (`path:NNN`) を禁止する。

    行番号は必ず腐る（実測: `docs/axum-video-server.md` の 43 件がすべて
    同一 commit 内で 2 行以上ずれていた）。symbol 名で参照すれば、rename は
    `check_doc_code_refs.py` の C2 が見る。履歴記録 (`docs/superpowers/**`
    等) は当時の記録なので対象外。
    """
    problems: list[str] = []
    for pattern in _LINE_REF_DOC_GLOBS:
        for path in sorted(root.glob(pattern)):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            text = path.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), 1):
                for match in _LINE_REF_RE.finditer(line):
                    target = match.group(1)
                    if target.startswith(_LINE_REF_PLACEHOLDERS):
                        continue
                    problems.append(
                        f"line-refs: {rel} の {lineno} 行目に line reference"
                        f" `{target}:<line>` がある。symbol 参照に置換すること"
                    )
    return problems


_GATES.update(
    {
        "check_exit_codes": check_exit_codes,
        "check_cli_options": check_cli_options,
        "check_line_refs": check_line_refs,
    }
)


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
