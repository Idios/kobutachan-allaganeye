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
    "codex-invocation",
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
# Phase 2 gates: exit codes / CLI options / line refs
# --------------------------------------------------------------------------


def test_exit_codes_documented_set_matches_code() -> None:
    """AGENTS.md の Exit Codes 表と実装が一致する。"""
    assert cd.check_exit_codes(REPO_ROOT) == []


def test_exit_codes_gate_detects_undocumented_code(tmp_path: Path) -> None:
    """実装にしか無い code と、表にしか無い code の両方を報告する。"""
    (tmp_path / "allaganeye").mkdir()
    (tmp_path / "allaganeye" / "cli.py").write_text(
        "raise typer.Exit(code=99)\n", encoding="utf-8"
    )
    (tmp_path / "AGENTS.md").write_text(
        "## Exit Codes\n\n| 0 | ok |\n| 1 | general |\n| 42 | ghost |\n",
        encoding="utf-8",
    )
    problems = cd.check_exit_codes(tmp_path)
    assert any("99" in p and "undocumented" in p for p in problems)
    assert any("42" in p and "never produced" in p for p in problems)


def test_exit_code_class_attributes_count_as_produced(tmp_path: Path) -> None:
    """`exit_code = N` (例外クラス) は produced に含める。"""
    (tmp_path / "allaganeye").mkdir()
    (tmp_path / "allaganeye" / "exceptions.py").write_text(
        "class E:\n    exit_code = 3\n", encoding="utf-8"
    )
    (tmp_path / "AGENTS.md").write_text(
        "## Exit Codes\n\n| 0 | ok |\n| 3 | ffmpeg |\n", encoding="utf-8"
    )
    assert cd.check_exit_codes(tmp_path) == []


def test_cli_options_documented_set_matches_runtime() -> None:
    """runtime registry の option 集合と docs/cli-spec.md が一致する。"""
    assert cd.check_cli_options(REPO_ROOT) == []


def test_cli_options_gate_reports_both_directions() -> None:
    problems = cd._compare_cli_options(
        {"--kept", "--undocumented"}, {"--kept", "--ghost"}
    )
    assert any("--undocumented" in p and "not documented" in p for p in problems)
    assert any("--ghost" in p and "not implemented" in p for p in problems)


def test_cli_options_are_compared_per_command() -> None:
    """共有 option が片方のコマンドから消えた drift を検出する。

    全体の和集合だけを見ると `--gpu` が `split` に残っている限り緑になる。
    Codex adversarial-review [P2]。
    """
    problems = cd._compare_cli_options_per_command(
        {"detect": {"--gpu", "--workers"}, "split": {"--gpu"}},
        {"detect": {"--workers"}, "split": {"--gpu"}},
    )
    assert any("detect" in p and "--gpu" in p for p in problems)


def test_cli_options_reports_command_set_drift() -> None:
    problems = cd._compare_cli_options_per_command(
        {"shown": set(), "hidden_in_doc": set()}, {"shown": set(), "ghost": set()}
    )
    assert any("hidden_in_doc" in p and "無い" in p for p in problems)
    assert any("ghost" in p and "実装に無い" in p for p in problems)


def test_line_refs_are_absent_from_living_docs() -> None:
    """living doc に行番号参照 (`path:NNN`) が無い (Phase 2 で 49 件を除去)。"""
    assert cd.check_line_refs(REPO_ROOT) == []


def test_line_refs_gate_detects_reference(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "sample.md").write_text(
        "see `allaganeye/cli.py:12` for details\n", encoding="utf-8"
    )
    problems = cd.check_line_refs(tmp_path)
    assert any("sample.md" in p and "line reference" in p for p in problems)


def test_line_refs_allows_placeholder_and_history(tmp_path: Path) -> None:
    """`path/to/...` の記入例と、履歴記録 (`docs/superpowers/**`) は対象外。"""
    docs = tmp_path / "docs"
    (docs / "superpowers").mkdir(parents=True)
    (docs / "sample.md").write_text(
        "write `path/to/file.py:123` here\n", encoding="utf-8"
    )
    (docs / "superpowers" / "old.md").write_text(
        "`allaganeye/cli.py:12`\n", encoding="utf-8"
    )
    assert cd.check_line_refs(tmp_path) == []


# --------------------------------------------------------------------------
# Phase 3 gates: iron law / bulk threshold / required checks / path refs
# --------------------------------------------------------------------------


def test_iron_law_is_not_duplicated_in_hook() -> None:
    """Iron Law 本文は AGENTS.md に 1 つだけ置き、hook は実行時に抽出する。"""
    assert cd.check_iron_law_mirror(REPO_ROOT) == []


def test_iron_law_gate_detects_copy(tmp_path: Path) -> None:
    hooks = tmp_path / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "session-start.sh").write_text(
        "# NO PR MERGE WITHOUT ALL ACCEPTANCE CRITERIA CHECKED\n", encoding="utf-8"
    )
    problems = cd.check_iron_law_mirror(tmp_path)
    assert any("copy" in p for p in problems)


def test_iron_law_gate_requires_agents_md_reference(tmp_path: Path) -> None:
    hooks = tmp_path / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "session-start.sh").write_text("echo hi\n", encoding="utf-8")
    problems = cd.check_iron_law_mirror(tmp_path)
    assert any("AGENTS.md" in p for p in problems)


def test_bulk_threshold_matches_docs() -> None:
    assert cd.check_bulk_threshold(REPO_ROOT) == []


def test_bulk_threshold_gate_detects_drift(tmp_path: Path) -> None:
    hooks = tmp_path / ".claude" / "hooks"
    docs = tmp_path / "docs"
    hooks.mkdir(parents=True)
    docs.mkdir()
    (hooks / "preuse.py").write_text(
        "_BULK_THRESHOLD: int = 9\n_BULK_WINDOW_SEC: float = 5.0\n", encoding="utf-8"
    )
    (docs / "l2-workflow.md").write_text("bulk 閾値 (3 件 / 60s)\n", encoding="utf-8")
    problems = cd.check_bulk_threshold(tmp_path)
    assert any(("9" in p and "60" in p) or "5" in p for p in problems)


def test_required_checks_exist_as_jobs() -> None:
    assert cd.check_required_checks(REPO_ROOT) == []


def test_required_checks_gate_detects_missing_job(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    workflows = tmp_path / ".github" / "workflows"
    docs.mkdir()
    workflows.mkdir(parents=True)
    (docs / "release-process.md").write_text(
        "## ブランチ保護と required status checks (#947)\n\n"
        "| check 名 | 定義元 | 役割 |\n| --- | --- | --- |\n"
        "| `python` | `.github/workflows/ci.yml` | x |\n"
        "| `ghost-job` | `.github/workflows/ci.yml` | x |\n",
        encoding="utf-8",
    )
    (workflows / "ci.yml").write_text(
        "jobs:\n  python:\n    runs-on: ubuntu\n", encoding="utf-8"
    )
    problems = cd.check_required_checks(tmp_path)
    assert any("ghost-job" in p for p in problems)


def test_path_refs_resolve() -> None:
    assert cd.check_path_refs(REPO_ROOT) == []


def test_path_refs_gate_detects_broken(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        "see `docs/no_such_doc.md` for details\n", encoding="utf-8"
    )
    problems = cd.check_path_refs(tmp_path)
    assert any("no_such_doc" in p for p in problems)


def test_path_refs_skips_examples_and_unknown_roots(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        "runtime `output/metadata.json` / example `path/to/file.py`\n",
        encoding="utf-8",
    )
    assert cd.check_path_refs(tmp_path) == []


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
