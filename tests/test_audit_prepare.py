"""Tests for scripts/audit-prepare.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit-prepare.py"


def _load_module() -> Any:
    """Load scripts/audit-prepare.py as a Python module."""
    spec = importlib.util.spec_from_file_location("audit_prepare", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def sample_metadata() -> dict[str, Any]:
    return {
        "schema_version": "1",
        "source": "20260116/2026-01-16 22-12-57.mkv",
        "source_duration": 7303.488,
        "source_fps": 60.0,
        "matches": [
            {
                "index": 1,
                "start_time": 49.125,
                "end_time": 1054.5,
                "duration": 1005.375,
                "type": "fl_match",
            },
            {
                "index": 2,
                "start_time": 1256.0,
                "end_time": 2178.75,
                "duration": 922.75,
                "type": "fl_match",
            },
        ],
        "gaps": [
            {
                "start_time": 2610.75,
                "end_time": 2976.25,
                "duration": 365.5,
            }
        ],
    }


def test_build_worksheet_rows_includes_all_boundaries(sample_metadata):
    mod = _load_module()
    rows = mod.build_worksheet_rows(sample_metadata)

    # 2 matches × 2 boundaries + 1 gap × 2 boundaries = 6 rows
    assert len(rows) == 6

    types = [r["boundary_type"] for r in rows]
    assert types == [
        "match_start",
        "match_end",
        "match_start",
        "match_end",
        "gap_start",
        "gap_end",
    ]


def test_build_worksheet_rows_timestamp_display_format(sample_metadata):
    mod = _load_module()
    rows = mod.build_worksheet_rows(sample_metadata)

    # 49.125 → "00:00:49.125"
    assert rows[0]["timestamp_sec"] == pytest.approx(49.125)
    assert rows[0]["timestamp_display"] == "00:00:49.125"
    # 2178.75 → "00:36:18.750"
    assert rows[3]["timestamp_display"] == "00:36:18.750"


def test_build_worksheet_rows_timestamp_display_format_hours():
    """HH:MM:SS.fff format includes hours for timestamps > 1hr."""
    mod = _load_module()
    metadata = {
        "matches": [
            {
                "index": 1,
                "start_time": 7305.125,  # 02:01:45.125
                "end_time": 7310.0,  # 02:01:50.000
                "duration": 4.875,
                "type": "fl_match",
            },
        ],
        "gaps": [],
    }
    rows = mod.build_worksheet_rows(metadata)
    assert rows[0]["timestamp_display"] == "02:01:45.125"
    assert rows[1]["timestamp_display"] == "02:01:50.000"


def test_build_worksheet_rows_current_type(sample_metadata):
    mod = _load_module()
    rows = mod.build_worksheet_rows(sample_metadata)

    assert rows[0]["current_type"] == "fl_match"
    assert rows[4]["current_type"] == "gap"


def test_build_worksheet_rows_empty_inputs():
    mod = _load_module()
    rows = mod.build_worksheet_rows({"matches": [], "gaps": []})
    assert rows == []
