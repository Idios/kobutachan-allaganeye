"""Tests for the ``allaganeye detect`` command (#463)."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from allaganeye.commands.detect import run_detect
from allaganeye.config import SplitConfig
from allaganeye.exceptions import DetectionError
from allaganeye.video.detector import MatchBoundary
from allaganeye.video.probe import ProbeResult

PROBE_RESULT: ProbeResult = {
    "duration": 1800.0,
    "width": 1920,
    "height": 1080,
    "fps": 30.0,
    "codec": "h264",
    "audio_codec": "aac",
}

BOUNDARIES: list[MatchBoundary] = [
    {"start": 0.0, "end": 600.0, "type": "fl_match"},
    {"start": 610.0, "end": 1200.0, "type": "fl_match"},
]

MODULE_DETECT = "allaganeye.commands.detect"
MODULE_SPLIT = "allaganeye.commands.split_matches"


@pytest.fixture(autouse=True)
def _mock_audio_scan():
    """Detect also consumes the shared ``_run_audio_scan`` helper."""
    with patch(f"{MODULE_SPLIT}._run_audio_scan", return_value=None) as m:
        yield m


def _mock_detect_only(tmp_path: Path):
    """Common patches for ``run_detect`` pipeline tests."""
    return (
        patch(f"{MODULE_DETECT}.probe_video", return_value=PROBE_RESULT),
        patch(f"{MODULE_DETECT}._run_detection", return_value=BOUNDARIES),
    )


def test_detect_writes_metadata_without_note(tmp_path):
    probe, detect = _mock_detect_only(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    with probe, detect:
        run_detect(Path("input.mp4"), config, quiet=True)

    meta_path = tmp_path / "metadata.json"
    assert meta_path.exists()
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    # `note` was retired in #463
    assert "note" not in payload
    assert payload["source"] == str(Path("input.mp4"))
    assert payload["source_duration"] == PROBE_RESULT["duration"]
    assert len(payload["matches"]) == len(BOUNDARIES)
    assert payload["matches"][0]["output_file"] == "match_001.mp4"
    assert payload["matches"][1]["output_file"] == "match_002.mp4"


def test_detect_does_not_call_split_video(tmp_path):
    probe, detect = _mock_detect_only(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    with probe, detect, patch(f"{MODULE_SPLIT}.split_video") as mock_split:
        run_detect(Path("input.mp4"), config, quiet=True)

    mock_split.assert_not_called()


def test_detect_uses_placeholder_output_file_names(tmp_path):
    probe, detect = _mock_detect_only(tmp_path)
    config = SplitConfig(output_dir=tmp_path / "nested", min_match_duration=60.0)
    with probe, detect:
        run_detect(Path("input.mp4"), config, quiet=True)

    payload = json.loads((tmp_path / "nested" / "metadata.json").read_text("utf-8"))
    names = [m["output_file"] for m in payload["matches"]]
    assert names == ["match_001.mp4", "match_002.mp4"]


def test_detect_raises_when_no_boundaries(tmp_path):
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    with (
        patch(f"{MODULE_DETECT}.probe_video", return_value=PROBE_RESULT),
        patch(f"{MODULE_DETECT}._run_detection", return_value=[]),
        pytest.raises(DetectionError),
    ):
        run_detect(Path("input.mp4"), config, quiet=True)


def test_detect_uses_cache_when_present(tmp_path):
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    with (
        patch(f"{MODULE_DETECT}.probe_video", return_value=PROBE_RESULT),
        patch(f"{MODULE_DETECT}._load_cache", return_value=BOUNDARIES),
        patch(f"{MODULE_DETECT}._run_detection") as mock_detect,
    ):
        run_detect(Path("input.mp4"), config, quiet=True)

    mock_detect.assert_not_called()
    assert (tmp_path / "metadata.json").exists()
