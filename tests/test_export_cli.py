"""Tests for 'allaganeye export' CLI (#761)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from allaganeye.commands.export import register
from allaganeye.export.schema import ExportSummary

runner = CliRunner()


@pytest.fixture
def app() -> typer.Typer:
    a = typer.Typer()

    # Force group mode for single-command isolation testing (see Task 8 fixture)
    @a.callback()
    def _():
        pass

    register(a)
    return a


def _make_metadata(tmp_path: Path) -> Path:
    """metadata.json on disk with 2 matches."""
    payload = {
        "schema_version": "1",
        "source": str(tmp_path / "in.mp4"),
        "matches": [
            {"index": 0, "start_time": 0.0, "end_time": 10.0, "type": "match"},
            {"index": 1, "start_time": 10.0, "end_time": 20.0, "type": "match"},
        ],
        "system_info": {
            "gpu_vendors_available": ["nvidia"],
            "vendor_preference": ["nvidia", "amd", "intel"],
            "gpu": ["NVIDIA GeForce RTX 5090"],
        },
    }
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@patch("allaganeye.commands.export.export_matches")
def test_export_positional_metadata_path(
    mock_export: MagicMock, app: typer.Typer, tmp_path: Path
):
    mock_export.return_value = ExportSummary(success=2, failure=0)
    metadata_path = _make_metadata(tmp_path)
    result = runner.invoke(
        app,
        [
            "export",
            str(metadata_path),
            "--output-dir",
            str(tmp_path),
            "--codec",
            "h264",
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    mock_export.assert_called_once()


@patch("allaganeye.commands.export.export_matches")
def test_export_stdin_mode(mock_export: MagicMock, app: typer.Typer, tmp_path: Path):
    mock_export.return_value = ExportSummary(success=1, failure=0)
    payload = json.dumps(
        {
            "source": str(tmp_path / "in.mp4"),
            "matches": [
                {"index": 0, "start_time": 0.0, "end_time": 5.0, "type": "match"}
            ],
            "system_info": {
                "gpu_vendors_available": [],
                "vendor_preference": ["nvidia"],
                "gpu": [],
            },
        }
    )
    result = runner.invoke(
        app,
        [
            "export",
            "--stdin",
            "--output-dir",
            str(tmp_path),
            "--codec",
            "copy",
            "--quiet",
        ],
        input=payload,
    )
    assert result.exit_code == 0
    mock_export.assert_called_once()


@patch("allaganeye.commands.export.export_matches")
def test_export_json_mode_emits_summary_line(
    mock_export: MagicMock, app: typer.Typer, tmp_path: Path
):
    """--json mode で stdout の最後の行が summary event."""
    mock_export.return_value = ExportSummary(success=1, failure=0, cancelled=False)
    metadata_path = _make_metadata(tmp_path)
    result = runner.invoke(
        app,
        [
            "export",
            str(metadata_path),
            "--output-dir",
            str(tmp_path),
            "--codec",
            "h264",
            "--json",
        ],
    )
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert lines, "expected at least one JSON line"
    last = json.loads(lines[-1])
    assert last["type"] == "summary"


@patch("allaganeye.commands.export.export_matches")
def test_export_exclude_filters_matches(
    mock_export: MagicMock, app: typer.Typer, tmp_path: Path
):
    mock_export.return_value = ExportSummary(success=1, failure=0)
    metadata_path = _make_metadata(tmp_path)
    result = runner.invoke(
        app,
        [
            "export",
            str(metadata_path),
            "--output-dir",
            str(tmp_path),
            "--codec",
            "h264",
            "--exclude",
            "1",
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    args, kwargs = mock_export.call_args
    # matches[] should have index 0 only after filter
    passed_matches = kwargs.get("matches") or args[0]
    assert [m.index for m in passed_matches] == [0]


def test_export_no_metadata_no_stdin_errors(app: typer.Typer):
    result = runner.invoke(app, ["export"])
    assert result.exit_code != 0  # Typer error: missing argument


@patch("allaganeye.commands.export.export_matches")
def test_export_returns_exit_1_on_failure(
    mock_export: MagicMock, app: typer.Typer, tmp_path: Path
):
    mock_export.return_value = ExportSummary(success=0, failure=2)
    metadata_path = _make_metadata(tmp_path)
    result = runner.invoke(
        app,
        [
            "export",
            str(metadata_path),
            "--output-dir",
            str(tmp_path),
            "--codec",
            "h264",
            "--quiet",
        ],
    )
    assert result.exit_code == 1
