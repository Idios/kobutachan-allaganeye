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


@patch("allaganeye.commands.export.export_matches")
def test_export_respects_edited_zero_start(
    mock_export: MagicMock, app: typer.Typer, tmp_path: Path
):
    """edited.start_time == 0.0 must be honored (not fall back to start_time)."""
    mock_export.return_value = ExportSummary(success=1, failure=0)
    payload = {
        "schema_version": "1",
        "source": str(tmp_path / "in.mp4"),
        "matches": [
            {
                "index": 0,
                "start_time": 5.0,
                "end_time": 10.0,
                "type": "match",
                "edited": {"start_time": 0.0, "end_time": 7.5},
            },
        ],
        "system_info": {
            "gpu_vendors_available": [],
            "vendor_preference": ["nvidia"],
            "gpu": [],
        },
    }
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "export",
            str(metadata_path),
            "--output-dir",
            str(tmp_path),
            "--codec",
            "copy",
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    _, kwargs = mock_export.call_args
    passed_matches = kwargs.get("matches")
    assert passed_matches[0].start == 0.0  # not 5.0
    assert passed_matches[0].end == 7.5


@patch("allaganeye.commands.export.export_matches")
def test_export_include_filters_matches(
    mock_export: MagicMock, app: typer.Typer, tmp_path: Path
):
    """--include keeps only listed indexes (others skipped)."""
    mock_export.return_value = ExportSummary(success=1, failure=0)
    metadata_path = _make_metadata(tmp_path)  # 2 matches: indexes 0, 1
    result = runner.invoke(
        app,
        [
            "export",
            str(metadata_path),
            "--output-dir",
            str(tmp_path),
            "--codec",
            "h264",
            "--include",
            "1",
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    _, kwargs = mock_export.call_args
    assert [m.index for m in kwargs.get("matches")] == [1]


@patch("allaganeye.commands.export.export_matches")
@patch("allaganeye.commands.export.enumerate_h264_encoders")
def test_export_concurrency_slices_slots(
    mock_enumerate: MagicMock, mock_export: MagicMock, app: typer.Typer, tmp_path: Path
):
    """--concurrency N truncates the slot list returned by enumerate_h264_encoders to first N."""
    from allaganeye.export.encoder import EncoderSlot, H264Encoder

    mock_enumerate.return_value = [
        EncoderSlot(
            slot_index=i,
            encoder_kind=H264Encoder.NVENC,
            display_label=f"NVENC #{i + 1}",
        )
        for i in range(3)
    ]
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
            "--concurrency",
            "2",
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    _, kwargs = mock_export.call_args
    assert len(kwargs.get("slots")) == 2


@patch("allaganeye.commands.export.export_matches")
def test_export_include_minus_exclude(
    mock_export: MagicMock, app: typer.Typer, tmp_path: Path
):
    """--include and --exclude combined: effective set = include - exclude."""
    mock_export.return_value = ExportSummary(success=1, failure=0)
    # build metadata with 3 matches (indexes 0, 1, 2)
    payload = {
        "schema_version": "1",
        "source": str(tmp_path / "in.mp4"),
        "matches": [
            {"index": 0, "start_time": 0.0, "end_time": 10.0, "type": "match"},
            {"index": 1, "start_time": 10.0, "end_time": 20.0, "type": "match"},
            {"index": 2, "start_time": 20.0, "end_time": 30.0, "type": "match"},
        ],
        "system_info": {
            "gpu_vendors_available": [],
            "vendor_preference": ["nvidia"],
            "gpu": [],
        },
    }
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "export",
            str(metadata_path),
            "--output-dir",
            str(tmp_path),
            "--codec",
            "h264",
            "--include",
            "0,1,2",
            "--exclude",
            "1",
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    _, kwargs = mock_export.call_args
    assert [m.index for m in kwargs.get("matches")] == [0, 2]
