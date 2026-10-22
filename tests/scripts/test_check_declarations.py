"""Tests for scripts/check_declarations.py (#1079 Phase 1).

`docs/declaration-catalog.md` は「同じ事実が 2 spot 以上にある」ことを宣言する
台帳である。本ファイルが固定するのは次の 2 点:

- **整合性**: 台帳の各セル (SSoT / 複製 spot / gate) が実 tree で解決すること。
  `active` と宣言した gate が未実装なら red にする (未実装のまま「守られている」
  ように見える状態を塞ぐ)。
- **集合**: 台帳の行を消しても `check_declarations.py` は 0 を返す (行の削除は
  drift ではなく「未登録クラス」である)。したがって id 集合そのものを本 test が
  pin する。片方だけでは「台帳の腐り」と「クラスの消失」を区別できない。

規律は `test_check_agent_migration_sweep.py` / `test_check_doc_code_refs.py` と
同じで、**違反を注入して exit code の生値を観測する**。正常系だけを見て
「ガードがある」と判断しない。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_declarations.py"
CATALOG_PATH = REPO_ROOT / "docs" / "declaration-catalog.md"

_spec = importlib.util.spec_from_file_location("check_declarations", SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
cd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cd)

# 台帳の id 集合。行の追加・削除・rename は必ずここも更新する。
# planned -> active への移行では id は変わらないため、本 pin は維持される。
EXPECTED_IDS = {
    "exit-codes",
    "cli-options",
    "tauri-commands",
    "tauri-commands-agents",
    "iron-law",
    "bulk-threshold",
    "required-checks",
    "line-refs",
    "path-refs",
    "metadata-schema",
    "version-locations",
    "error-hints",
    "shipped-commands",
    "model-routing",
    "gui-screens",
    "detection-modules",
}


def _row(**overrides: str) -> str:
    row = {
        "id": "sample",
        "事実": "sample fact",
        "SSoT": "allaganeye/exceptions.py",
        "複製 spot": "docs/cli-spec.md",
        "mode": "checked",
        "gate": "ci:python",
        "status": "active",
    }
    row.update(overrides)
    cells = [row[column].replace("|", "/") for column in cd.COLUMNS]
    return "| " + " | ".join(cells) + " |"


def _catalog(tmp_path: Path, rows: list[str], *, header: bool = True) -> Path:
    lines: list[str] = []
    if header:
        lines.append("| " + " | ".join(cd.COLUMNS) + " |")
        lines.append("| " + " | ".join(["---"] * len(cd.COLUMNS)) + " |")
    lines.extend(rows)
    path = tmp_path / "catalog.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _problems(tmp_path: Path, rows: list[str]) -> list[str]:
    parsed = cd.parse_catalog(_catalog(tmp_path, rows))
    return cd.check(REPO_ROOT, parsed, REPO_ROOT)


# --------------------------------------------------------------------------
# 集合 pin (行の削除検出)
# --------------------------------------------------------------------------


def test_catalog_ids_are_pinned() -> None:
    """台帳の id 集合が EXPECTED_IDS と一致する。

    行を消しても check_declarations.py は 0 を返すため、消失は本 test だけが検出する。
    """
    rows = cd.parse_catalog(CATALOG_PATH)
    assert {row["id"] for row in rows} == EXPECTED_IDS


def test_real_catalog_is_consistent() -> None:
    """実台帳と実 tree が一致する (正常系)。"""
    rows = cd.parse_catalog(CATALOG_PATH)
    assert cd.check(REPO_ROOT, rows, REPO_ROOT) == []


def test_every_row_declares_a_mode_and_gate() -> None:
    """全行が 4 モードのいずれかと、モードに整合する gate を持つ。"""
    for row in cd.parse_catalog(CATALOG_PATH):
        assert row["mode"] in cd.MODES, row["id"]
        if row["mode"] == "prose-only":
            assert row["gate"] == "none", row["id"]
        else:
            assert row["gate"] != "none", row["id"]
        assert cd.STATUS_RE.match(row["status"]), row["id"]


# --------------------------------------------------------------------------
# 整合性の red 実証 (注入)
# --------------------------------------------------------------------------


def test_missing_ssot_is_reported(tmp_path: Path) -> None:
    problems = _problems(tmp_path, [_row(SSoT="allaganeye/does_not_exist.py")])
    assert any("SSoT path missing" in p for p in problems)


def test_missing_mirror_is_reported(tmp_path: Path) -> None:
    problems = _problems(tmp_path, [_row(**{"複製 spot": "docs/no_such_doc.md"})])
    assert any("mirror missing" in p for p in problems)


def test_unknown_ci_job_is_reported(tmp_path: Path) -> None:
    problems = _problems(tmp_path, [_row(gate="ci:no-such-job")])
    assert any("job not found" in p for p in problems)


def test_missing_ci_step_is_reported(tmp_path: Path) -> None:
    """ci:<job>:<step> の step 名が workflow に無ければ red。

    metadata-schema は python / gui-frontend の 2 つの codegen step で守られており、
    step 名が rename されると守りが静かに消える。
    """
    problems = _problems(tmp_path, [_row(gate="ci:python:No such step name")])
    assert any("step not found" in p for p in problems)


def test_ci_step_is_scoped_to_its_job(tmp_path: Path) -> None:
    """step 名の探索は宣言された job の中に限定する。

    workflow 全体を探すと、別 job に同名 step があるだけで誤って通る。
    metadata-schema の ts 側 step は gui-frontend にあるため、
    `ci:python:` に付けると red にならなければならない (Codex review [P2])。
    """
    problems = _problems(
        tmp_path,
        [_row(gate="ci:python:Verify generated metadata.generated.ts is up to date")],
    )
    assert any("step not found in job python" in p for p in problems)


def test_ci_step_in_its_own_job_passes(tmp_path: Path) -> None:
    """正しい job に付けた step は通る (上の test の対照)。"""
    problems = _problems(
        tmp_path,
        [
            _row(
                gate="ci:gui-frontend:Verify generated metadata.generated.ts is up to date"
            )
        ],
    )
    assert problems == []


def test_duplicate_id_is_reported(tmp_path: Path) -> None:
    problems = _problems(tmp_path, [_row(id="dup"), _row(id="dup")])
    assert any("duplicate id" in p for p in problems)


def test_non_kebab_id_is_reported(tmp_path: Path) -> None:
    problems = _problems(tmp_path, [_row(id="Not_Kebab")])
    assert any("not kebab-case" in p for p in problems)


def test_prose_only_with_gate_is_reported(tmp_path: Path) -> None:
    problems = _problems(tmp_path, [_row(mode="prose-only", gate="ci:python")])
    assert any("prose-only must use gate none" in p for p in problems)


def test_non_prose_without_gate_is_reported(tmp_path: Path) -> None:
    problems = _problems(tmp_path, [_row(mode="checked", gate="none")])
    assert any("must declare a gate" in p for p in problems)


def test_active_gate_without_function_is_reported(tmp_path: Path) -> None:
    """active と宣言した script gate の関数が無ければ red。

    これが無いと「planned のつもりで active と書いた」行が無検査で通る。
    """
    problems = _problems(
        tmp_path,
        [
            _row(
                gate="script:scripts/check_declarations.py::not_implemented_gate",
                status="active",
            )
        ],
    )
    assert any("active gate function not implemented" in p for p in problems)


def test_planned_gate_without_function_is_allowed(tmp_path: Path) -> None:
    """planned は未実装 gate を許す (Phase 2/3 で active 化する)。"""
    problems = _problems(
        tmp_path,
        [
            _row(
                gate="script:scripts/check_declarations.py::not_implemented_gate",
                status="planned:2",
            )
        ],
    )
    assert problems == []


def test_unknown_mode_is_reported(tmp_path: Path) -> None:
    problems = _problems(tmp_path, [_row(mode="mystery")])
    assert any("unknown mode" in p for p in problems)


def test_multi_gate_is_checked_per_edge(tmp_path: Path) -> None:
    """`+` で連ねた gate は 1 本ずつ検証する (metadata-schema が 2 本持つ)。"""
    problems = _problems(tmp_path, [_row(gate="ci:python + ci:no-such-job")])
    assert any("job not found" in p for p in problems)


# --------------------------------------------------------------------------
# 構造エラー (exit 2)
# --------------------------------------------------------------------------


def test_missing_header_is_structure_error(tmp_path: Path) -> None:
    with pytest.raises(cd.StructureError):
        cd.parse_catalog(_catalog(tmp_path, [_row()], header=False))


def test_zero_rows_is_structure_error(tmp_path: Path) -> None:
    with pytest.raises(cd.StructureError):
        cd.parse_catalog(_catalog(tmp_path, []))


def test_wrong_cell_count_is_structure_error(tmp_path: Path) -> None:
    with pytest.raises(cd.StructureError):
        cd.parse_catalog(_catalog(tmp_path, ["| a | b | c |"]))


def test_missing_catalog_is_structure_error(tmp_path: Path) -> None:
    with pytest.raises(cd.StructureError):
        cd.parse_catalog(tmp_path / "absent.md")


# --------------------------------------------------------------------------
# main() の exit code
# --------------------------------------------------------------------------


def _run_main(monkeypatch: pytest.MonkeyPatch, catalog: Path) -> int:
    argv = [
        "check_declarations.py",
        "--repo-root",
        str(REPO_ROOT),
        "--catalog",
        str(catalog),
        "--gate-root",
        str(REPO_ROOT),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    return cd.main()


def test_main_exit_zero_for_real_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _run_main(monkeypatch, CATALOG_PATH) == 0


def test_main_exit_one_for_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = _catalog(tmp_path, [_row(SSoT="allaganeye/does_not_exist.py")])
    assert _run_main(monkeypatch, catalog) == 1


def test_main_exit_two_for_structure_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = _catalog(tmp_path, [], header=False)
    assert _run_main(monkeypatch, catalog) == 2
