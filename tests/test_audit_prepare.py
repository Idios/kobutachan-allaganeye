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

    # 2 matches x 2 boundaries + 1 gap x 2 boundaries = 6 rows
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

    # 49.125 -> "00:00:49.125"
    assert rows[0]["timestamp_sec"] == pytest.approx(49.125)
    assert rows[0]["timestamp_display"] == "00:00:49.125"
    # 2178.75 -> "00:36:18.750"
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
    # NOTE: implementation raises OSError; EnvironmentError is the Python 3
    # alias for OSError (kept as a comment for searchability). Test mirrors
    # the impl literal to keep intent unambiguous.
    with pytest.raises(OSError, match="ALLAGANEYE_SAMPLE_VIDEO_DIR"):
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


def test_main_atomic_success_replaces_old_artifacts(tmp_path, monkeypatch):
    """Success run atomically replaces old artifacts; no .new residue (R3#2)."""
    mod = _load_module()
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
    (baseline_dir / "obs-fake.metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )
    video_dir = tmp_path / "videos"
    (video_dir / "20260116").mkdir(parents=True)
    (video_dir / "20260116" / "fake.mkv").write_bytes(b"")
    monkeypatch.setenv("ALLAGANEYE_SAMPLE_VIDEO_DIR", str(video_dir))
    monkeypatch.setattr(mod, "export_brightness_csv", lambda **kw: None)
    monkeypatch.setattr(mod, "export_sample_frames", lambda **kw: None)

    worksheet_dir = tmp_path / "audit-worksheet"
    per_boundary_dir = worksheet_dir / "obs-fake"
    worksheet_csv = worksheet_dir / "obs-fake.csv"

    # Seed pre-existing artifacts so we can verify they get replaced
    per_boundary_dir.mkdir(parents=True)
    (per_boundary_dir / "stale.txt").write_text("STALE", encoding="utf-8")
    worksheet_csv.write_text("STALE_HEADER\n", encoding="utf-8")

    rc = mod.main(
        [
            "obs-fake",
            "--baseline-dir",
            str(baseline_dir),
            "--worksheet-dir",
            str(worksheet_dir),
        ]
    )
    assert rc == 0
    # Stale must be gone, new artifacts present
    assert not (per_boundary_dir / "stale.txt").exists()
    assert "STALE_HEADER" not in worksheet_csv.read_text(encoding="utf-8")
    # No .new suffix residue
    assert not (worksheet_dir / "obs-fake.new").exists()
    assert not (worksheet_dir / "obs-fake.csv.new").exists()


def test_main_atomic_failure_preserves_old_artifacts(tmp_path, monkeypatch):
    """Failure mid-run keeps old artifacts intact; .new cleaned up (R3#2)."""
    mod = _load_module()
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
    (baseline_dir / "obs-fake.metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )
    video_dir = tmp_path / "videos"
    (video_dir / "20260116").mkdir(parents=True)
    (video_dir / "20260116" / "fake.mkv").write_bytes(b"")
    monkeypatch.setenv("ALLAGANEYE_SAMPLE_VIDEO_DIR", str(video_dir))

    # export_brightness_csv succeeds; export_sample_frames raises -> mid-run failure
    monkeypatch.setattr(mod, "export_brightness_csv", lambda **kw: None)

    def _fail(**kw):
        raise RuntimeError("simulated export failure")

    monkeypatch.setattr(mod, "export_sample_frames", _fail)

    worksheet_dir = tmp_path / "audit-worksheet"
    per_boundary_dir = worksheet_dir / "obs-fake"
    worksheet_csv = worksheet_dir / "obs-fake.csv"

    # Seed pre-existing artifacts that must survive the failure
    per_boundary_dir.mkdir(parents=True)
    (per_boundary_dir / "keep.txt").write_text("KEEP", encoding="utf-8")
    worksheet_csv.write_text("KEEP_HEADER\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="simulated export failure"):
        mod.main(
            [
                "obs-fake",
                "--baseline-dir",
                str(baseline_dir),
                "--worksheet-dir",
                str(worksheet_dir),
            ]
        )

    # Old artifacts must be intact
    assert (per_boundary_dir / "keep.txt").read_text(encoding="utf-8") == "KEEP"
    assert worksheet_csv.read_text(encoding="utf-8") == "KEEP_HEADER\n"
    # .new suffix dirs cleaned up
    assert not (worksheet_dir / "obs-fake.new").exists()
    assert not (worksheet_dir / "obs-fake.csv.new").exists()


def test_main_recovers_from_stale_new_dir(tmp_path, monkeypatch):
    """Stale .new dir from prior crash is pre-cleaned and new run succeeds (R3#2)."""
    mod = _load_module()
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
    (baseline_dir / "obs-fake.metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )
    video_dir = tmp_path / "videos"
    (video_dir / "20260116").mkdir(parents=True)
    (video_dir / "20260116" / "fake.mkv").write_bytes(b"")
    monkeypatch.setenv("ALLAGANEYE_SAMPLE_VIDEO_DIR", str(video_dir))
    monkeypatch.setattr(mod, "export_brightness_csv", lambda **kw: None)
    monkeypatch.setattr(mod, "export_sample_frames", lambda **kw: None)

    worksheet_dir = tmp_path / "audit-worksheet"
    # Seed stale .new dir (simulating prior crash mid-write)
    stale_new = worksheet_dir / "obs-fake.new"
    stale_new.mkdir(parents=True)
    (stale_new / "junk.txt").write_text("JUNK", encoding="utf-8")
    stale_csv_new = worksheet_dir / "obs-fake.csv.new"
    stale_csv_new.write_text("JUNK\n", encoding="utf-8")

    rc = mod.main(
        [
            "obs-fake",
            "--baseline-dir",
            str(baseline_dir),
            "--worksheet-dir",
            str(worksheet_dir),
        ]
    )
    assert rc == 0
    # Stale .new must be gone (replaced by either rename target or cleanup)
    assert not stale_new.exists()
    assert not stale_csv_new.exists()
    # Final artifacts in place
    assert (worksheet_dir / "obs-fake.csv").exists()


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


# --- Issue #800: tx-state helpers ---


def test_read_tx_state_returns_none_when_missing(tmp_path, capsys):
    """File-not-exist is legacy / first-run case; no warning."""
    mod = _load_module()
    tx_path = tmp_path / "obs.tx.json"
    assert mod._read_tx_state(tx_path) is None
    assert capsys.readouterr().err == ""


def test_read_tx_state_returns_consistent_state(tmp_path):
    mod = _load_module()
    tx_path = tmp_path / "obs.tx.json"
    tx_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "state": "consistent",
                "updated_at": "2026-05-21T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    result = mod._read_tx_state(tx_path)
    assert result is not None
    assert result["state"] == "consistent"


def test_read_tx_state_returns_swapping_state(tmp_path):
    mod = _load_module()
    tx_path = tmp_path / "obs.tx.json"
    tx_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "state": "swapping",
                "updated_at": "2026-05-21T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    result = mod._read_tx_state(tx_path)
    assert result is not None
    assert result["state"] == "swapping"


@pytest.mark.parametrize(
    "payload,variant",
    [
        ("not valid json{{{", "invalid_json"),
        ('["a", "b"]', "non_dict"),
        ('{"schema_version": 2, "state": "consistent"}', "unknown_schema_version"),
        ('{"schema_version": 1, "state": "unknown"}', "unknown_state"),
    ],
)
def test_tx_state_corrupted_treated_as_missing(tmp_path, capsys, payload, variant):
    """All 4 corrupted variants return None + warn on stderr."""
    mod = _load_module()
    tx_path = tmp_path / "obs.tx.json"
    tx_path.write_text(payload, encoding="utf-8")
    result = mod._read_tx_state(tx_path)
    assert result is None, f"variant={variant}"
    err = capsys.readouterr().err
    assert "WARNING" in err, f"variant={variant} stderr: {err!r}"
    assert str(tx_path) in err, f"variant={variant} stderr: {err!r}"


def test_write_tx_state_atomic_creates_file(tmp_path):
    mod = _load_module()
    tx_path = tmp_path / "obs.tx.json"
    mod._write_tx_state_atomic(tx_path, state="consistent")
    assert tx_path.exists()
    data = json.loads(tx_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["state"] == "consistent"
    assert data["updated_at"].endswith("Z")  # ISO 8601 UTC


def test_write_tx_state_atomic_overwrites_existing(tmp_path):
    mod = _load_module()
    tx_path = tmp_path / "obs.tx.json"
    mod._write_tx_state_atomic(tx_path, state="swapping")
    mod._write_tx_state_atomic(tx_path, state="consistent")
    data = json.loads(tx_path.read_text(encoding="utf-8"))
    assert data["state"] == "consistent"


def test_write_tx_state_atomic_cleans_up_new_suffix(tmp_path):
    """No `.tx.json.new` should remain after successful write."""
    mod = _load_module()
    tx_path = tmp_path / "obs.tx.json"
    mod._write_tx_state_atomic(tx_path, state="consistent")
    assert tx_path.exists()
    assert not (tmp_path / "obs.tx.json.new").exists()
