"""Tests for scripts/audit-prepare.py."""

from __future__ import annotations

import importlib.util
import json
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


def test_resolve_video_path_uses_env_var(monkeypatch, tmp_path):
    mod = _load_module()
    video_dir = tmp_path / "videos"
    video_dir.mkdir()
    (video_dir / "20260116").mkdir()
    target = video_dir / "20260116" / "2026-01-16 22-12-57.mkv"
    target.write_bytes(b"")  # placeholder

    monkeypatch.setenv("ALLAGANEYE_SAMPLE_VIDEO_DIR", str(video_dir))
    resolved = mod.resolve_video_path("20260116/2026-01-16 22-12-57.mkv")

    assert resolved == target


def test_resolve_video_path_missing_env_raises(monkeypatch):
    mod = _load_module()
    monkeypatch.delenv("ALLAGANEYE_SAMPLE_VIDEO_DIR", raising=False)
    with pytest.raises(EnvironmentError, match="ALLAGANEYE_SAMPLE_VIDEO_DIR"):
        mod.resolve_video_path("20260116/2026-01-16 22-12-57.mkv")


def test_resolve_video_path_missing_file_raises(monkeypatch, tmp_path):
    mod = _load_module()
    monkeypatch.setenv("ALLAGANEYE_SAMPLE_VIDEO_DIR", str(tmp_path))
    with pytest.raises(FileNotFoundError):
        mod.resolve_video_path("20260116/not-there.mkv")


def test_export_brightness_csv_writes_expected_rows(tmp_path, monkeypatch):
    mod = _load_module()

    # Stub _probe_single_frame to avoid needing a real video
    calls: list[float] = []

    def fake_probe(video_path, timestamp):
        calls.append(timestamp)
        # Synthetic brightness: dip near t=100
        return 5.0 if abs(timestamp - 100.0) < 1.0 else 80.0

    monkeypatch.setattr(mod, "_probe_single_frame", fake_probe)

    out_path = tmp_path / "brightness-around-100.000.csv"
    mod.export_brightness_csv(
        video_path=tmp_path / "fake.mkv",
        boundary_timestamp=100.0,
        out_path=out_path,
        window_sec=5.0,
        interval_sec=0.25,
    )

    assert out_path.exists()
    content = out_path.read_text(encoding="utf-8").strip().splitlines()
    # Header + (5s before + 5s after) / 0.25s + 1 = 41 rows
    assert content[0] == "timestamp,brightness"
    assert len(content) == 1 + 41
    # First data row should be at 95.000
    assert content[1].startswith("95.000,")
    # Last data row should be at 105.000
    assert content[-1].startswith("105.000,")


def test_export_sample_frames_writes_three_pngs(tmp_path, monkeypatch):
    import numpy as np

    mod = _load_module()

    def fake_probe_rgb(video_path, timestamp, height):
        # Return a 320x180x3 black-and-mid frame
        frame = np.full((180, 320, 3), int(timestamp) % 256, dtype=np.uint8)
        return frame.tobytes()

    monkeypatch.setattr(mod, "_probe_frame_rgb", fake_probe_rgb)

    out_dir = tmp_path / "obs-fake"
    out_dir.mkdir()

    mod.export_sample_frames(
        video_path=tmp_path / "fake.mkv",
        boundary_timestamp=100.0,
        out_dir=out_dir,
        height=180,
    )

    pngs = sorted(out_dir.glob("frame-around-*.png"))
    assert len(pngs) == 3
    assert pngs[0].name == "frame-around-099.000.png"
    assert pngs[1].name == "frame-around-100.000.png"
    assert pngs[2].name == "frame-around-101.000.png"
    # Sanity: each file is non-empty
    for p in pngs:
        assert p.stat().st_size > 0


def test_main_writes_worksheet_csv(tmp_path, monkeypatch):
    """End-to-end: main() reads metadata.json + writes worksheet CSV.

    Brightness/PNG step is stubbed; this verifies worksheet CSV shape only.
    """
    mod = _load_module()

    # Fake baseline dir with one metadata.json
    baseline_dir = tmp_path / "baselines"
    baseline_dir.mkdir()
    metadata = {
        "schema_version": "1",
        "source": "20260116/fake.mkv",
        "matches": [
            {
                "index": 1,
                "start_time": 49.125,
                "end_time": 1054.5,
                "duration": 1005.375,
                "type": "fl_match",
            },
        ],
        "gaps": [],
    }
    (baseline_dir / "obs-20260116.metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )

    # Fake video so resolve_video_path doesn't raise
    video_dir = tmp_path / "videos"
    (video_dir / "20260116").mkdir(parents=True)
    (video_dir / "20260116" / "fake.mkv").write_bytes(b"")
    monkeypatch.setenv("ALLAGANEYE_SAMPLE_VIDEO_DIR", str(video_dir))

    # Stub brightness / PNG exporters
    monkeypatch.setattr(mod, "export_brightness_csv", lambda **kw: None)
    monkeypatch.setattr(mod, "export_sample_frames", lambda **kw: None)

    worksheet_dir = tmp_path / "audit-worksheet"
    rc = mod.main(
        [
            "obs-20260116",
            "--baseline-dir",
            str(baseline_dir),
            "--worksheet-dir",
            str(worksheet_dir),
        ]
    )
    assert rc == 0

    worksheet_csv = worksheet_dir / "obs-20260116.csv"
    assert worksheet_csv.exists()
    lines = worksheet_csv.read_text(encoding="utf-8").strip().splitlines()
    # Header + 2 rows (match_start + match_end)
    assert len(lines) == 1 + 2
    assert lines[0].startswith("index,boundary_type,timestamp_sec,")
    assert "match_start" in lines[1]
    assert "match_end" in lines[2]
