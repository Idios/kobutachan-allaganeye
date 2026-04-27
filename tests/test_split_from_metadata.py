"""Tests for ``run_split_from_metadata`` (#463).

The legacy ``run_split(video)`` flow has separate coverage in
``test_split_matches.py``; the cases here focus on the new code path
where the entry point is a ``metadata.json`` and no detection runs.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from allaganeye.commands.split_matches import (
    _split_and_write_metadata,
    run_split_from_metadata,
)
from allaganeye.config import SplitConfig
from allaganeye.exceptions import InputFileError
from allaganeye.video.probe import ProbeResult

MODULE = "allaganeye.commands.split_matches"

PROBE_RESULT: ProbeResult = {
    "duration": 1800.0,
    "width": 1920,
    "height": 1080,
    "fps": 30.0,
    "codec": "h264",
    "audio_codec": "aac",
}


def _sample_metadata(source_path: str = "input.mp4") -> dict:
    return {
        "source": source_path,
        "source_duration": 1800.0,
        "source_duration_display": "30:00",
        "detected_at": "2026-04-22T00:00:00Z",
        "detection_params": {
            "sample_interval": 1.0,
            "blackout_threshold": 15.0,
            "min_match_duration": 300.0,
            "min_blackout_duration": 3.0,
            "no_audio": False,
            "use_gpu": None,
            "workers": None,
        },
        "matches": [
            {
                "index": 1,
                "start_time": 0.0,
                "end_time": 600.0,
                "start_display": "00:00",
                "end_display": "10:00",
                "duration": 600.0,
                "duration_display": "10m00s",
                "type": "fl_match",
                "output_file": "match_001.mp4",
            },
            {
                "index": 2,
                "start_time": 610.0,
                "end_time": 1200.0,
                "start_display": "10:10",
                "end_display": "20:00",
                "duration": 590.0,
                "duration_display": "09m50s",
                "type": "fl_match",
                "output_file": "match_002.mp4",
            },
        ],
        "gaps": [],
    }


def _write_metadata(tmp_path: Path, payload: dict) -> Path:
    meta_path = tmp_path / "metadata.json"
    meta_path.write_text(json.dumps(payload), encoding="utf-8")
    return meta_path


def test_run_split_from_metadata_skips_detection(tmp_path):
    source = tmp_path / "input.mp4"
    source.write_bytes(b"")  # existence check

    payload = _sample_metadata(str(source))
    meta_path = _write_metadata(tmp_path, payload)
    config = SplitConfig(output_dir=tmp_path / "out", min_match_duration=60.0)

    with (
        patch(f"{MODULE}.probe_video", return_value=PROBE_RESULT) as mock_probe,
        patch(f"{MODULE}.detect_match_boundaries") as mock_detect,
        patch(
            f"{MODULE}.split_video",
            return_value=[
                tmp_path / "out" / "match_001.mp4",
                tmp_path / "out" / "match_002.mp4",
            ],
        ) as mock_split,
    ):
        run_split_from_metadata(meta_path, config, quiet=True)

    mock_probe.assert_called_once_with(source)
    mock_detect.assert_not_called()
    mock_split.assert_called_once()
    args = mock_split.call_args[0]
    assert args[0] == source
    boundaries_arg = args[1]
    assert [b["start"] for b in boundaries_arg] == [0.0, 610.0]
    assert [b["end"] for b in boundaries_arg] == [600.0, 1200.0]


def test_run_split_from_metadata_rewrites_metadata_without_note(tmp_path):
    source = tmp_path / "input.mp4"
    source.write_bytes(b"")
    # Seed a legacy metadata file with a "note" to prove it doesn't
    # propagate into the fresh write.
    payload = {**_sample_metadata(str(source)), "note": "legacy caveat"}
    meta_path = _write_metadata(tmp_path, payload)
    config = SplitConfig(output_dir=tmp_path / "out", min_match_duration=60.0)

    with (
        patch(f"{MODULE}.probe_video", return_value=PROBE_RESULT),
        patch(
            f"{MODULE}.split_video",
            return_value=[
                tmp_path / "out" / "match_001.mp4",
                tmp_path / "out" / "match_002.mp4",
            ],
        ),
    ):
        run_split_from_metadata(meta_path, config, quiet=True)

    out_meta = tmp_path / "out" / "metadata.json"
    assert out_meta.exists()
    fresh = json.loads(out_meta.read_text("utf-8"))
    assert "note" not in fresh


def test_run_split_from_metadata_missing_source_raises(tmp_path):
    # Absolute path inside a fresh metadata file that does not exist.
    payload = _sample_metadata(str(tmp_path / "missing.mp4"))
    meta_path = _write_metadata(tmp_path, payload)
    config = SplitConfig(output_dir=tmp_path / "out", min_match_duration=60.0)

    with pytest.raises(InputFileError, match="source video"):
        run_split_from_metadata(meta_path, config, quiet=True)


def test_run_split_from_metadata_missing_matches_raises(tmp_path):
    source = tmp_path / "input.mp4"
    source.write_bytes(b"")
    payload = _sample_metadata(str(source))
    payload["matches"] = []
    meta_path = _write_metadata(tmp_path, payload)
    config = SplitConfig(output_dir=tmp_path / "out", min_match_duration=60.0)

    with pytest.raises(InputFileError, match="no match entries"):
        run_split_from_metadata(meta_path, config, quiet=True)


def test_run_split_from_metadata_nonexistent_file_raises(tmp_path):
    config = SplitConfig(output_dir=tmp_path / "out", min_match_duration=60.0)
    with pytest.raises(InputFileError, match="metadata file not found"):
        run_split_from_metadata(tmp_path / "nope.json", config, quiet=True)


def test_run_split_from_metadata_invalid_json_raises(tmp_path):
    meta_path = tmp_path / "metadata.json"
    meta_path.write_text("{ not valid json", encoding="utf-8")
    config = SplitConfig(output_dir=tmp_path / "out", min_match_duration=60.0)
    with pytest.raises(InputFileError, match="not valid JSON"):
        run_split_from_metadata(meta_path, config, quiet=True)


def test_split_and_write_metadata_has_no_note_field(tmp_path):
    """Regression: ``_split_and_write_metadata`` stopped emitting `note` in #463."""
    from allaganeye.video.detector import MatchBoundary

    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    boundaries: list[MatchBoundary] = [
        {"start": 0.0, "end": 120.0, "type": "fl_match"},
    ]

    with patch(
        f"{MODULE}.split_video",
        return_value=[tmp_path / "match_001.mp4"],
    ):
        _split_and_write_metadata(
            tmp_path / "input.mp4",
            boundaries,
            [],
            PROBE_RESULT,
            config,
            effective_interval=1.0,
            detected_at="2026-04-22T00:00:00Z",
            system_info={
                "gpu_vendors_available": [],
                "gpu_vendor_used": None,
                "vendor_preference": ["nvidia", "amd", "intel"],
            },
            quiet=True,
        )

    payload = json.loads((tmp_path / "metadata.json").read_text("utf-8"))
    assert "note" not in payload


def test_split_and_write_metadata_contains_schema_version(tmp_path):
    """#515: newly written metadata.json declares ``schema_version: "1"``."""
    from allaganeye.video.detector import MatchBoundary

    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    boundaries: list[MatchBoundary] = [
        {"start": 0.0, "end": 120.0, "type": "fl_match"},
    ]

    with patch(
        f"{MODULE}.split_video",
        return_value=[tmp_path / "match_001.mp4"],
    ):
        _split_and_write_metadata(
            tmp_path / "input.mp4",
            boundaries,
            [],
            PROBE_RESULT,
            config,
            effective_interval=1.0,
            detected_at="2026-04-22T00:00:00Z",
            system_info={
                "gpu_vendors_available": [],
                "gpu_vendor_used": None,
                "vendor_preference": ["nvidia", "amd", "intel"],
            },
            quiet=True,
        )

    payload = json.loads((tmp_path / "metadata.json").read_text("utf-8"))
    assert payload["schema_version"] == "1"


def test_split_and_write_metadata_emits_empty_warnings_array(tmp_path):
    """#518: metadata.json writer always emits a `warnings` field (default []).

    Locks in the schema for consumers so that once concrete codes ship in
    a later PR, readers already treat `warnings` as a known key.
    """
    from allaganeye.video.detector import MatchBoundary

    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    boundaries: list[MatchBoundary] = [
        {"start": 0.0, "end": 120.0, "type": "fl_match"},
    ]

    with patch(
        f"{MODULE}.split_video",
        return_value=[tmp_path / "match_001.mp4"],
    ):
        _split_and_write_metadata(
            tmp_path / "input.mp4",
            boundaries,
            [],
            PROBE_RESULT,
            config,
            effective_interval=1.0,
            detected_at="2026-04-22T00:00:00Z",
            system_info={
                "gpu_vendors_available": [],
                "gpu_vendor_used": None,
                "vendor_preference": ["nvidia", "amd", "intel"],
            },
            quiet=True,
        )

    payload = json.loads((tmp_path / "metadata.json").read_text("utf-8"))
    assert payload["warnings"] == []


def test_run_split_from_metadata_accepts_legacy_file_without_schema_version(
    tmp_path,
):
    """#515: pre-0.2.0 metadata.json files without schema_version still load."""
    meta = _sample_metadata(source_path=str(tmp_path / "input.mp4"))
    # legacy file explicitly has no schema_version
    assert "schema_version" not in meta
    meta_path = tmp_path / "metadata.json"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    (tmp_path / "input.mp4").write_bytes(b"")  # satisfies source path check

    out_dir = tmp_path / "out"
    config = SplitConfig(output_dir=out_dir, min_match_duration=60.0)
    with (
        patch(f"{MODULE}.probe_video", return_value=PROBE_RESULT),
        patch(
            f"{MODULE}.split_video",
            return_value=[
                out_dir / "match_001.mp4",
                out_dir / "match_002.mp4",
            ],
        ),
    ):
        run_split_from_metadata(meta_path, config, quiet=True)  # no raise


def test_run_split_from_metadata_rejects_future_schema_version(tmp_path):
    """#515: metadata.json with an unknown future schema_version is rejected."""
    meta = _sample_metadata(source_path=str(tmp_path / "input.mp4"))
    meta["schema_version"] = "99"
    meta_path = tmp_path / "metadata.json"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    config = SplitConfig(output_dir=tmp_path / "out", min_match_duration=60.0)
    with pytest.raises(InputFileError, match="unsupported schema_version"):
        run_split_from_metadata(meta_path, config, quiet=True)
