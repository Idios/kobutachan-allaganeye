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


def test_detect_writes_system_info_to_metadata(tmp_path, monkeypatch):
    """#591 -- detect で書き出した metadata.json に system_info が含まれる."""
    monkeypatch.setattr(
        "allaganeye.system_info.probe_gpu_vendors",
        lambda: ["nvidia", "amd"],
    )
    probe, detect = _mock_detect_only(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    with probe, detect:
        run_detect(Path("input.mp4"), config, quiet=True)

    payload = json.loads((tmp_path / "metadata.json").read_text("utf-8"))
    assert "system_info" in payload
    info = payload["system_info"]
    assert info["gpu_vendors_available"] == ["nvidia", "amd"]
    # detect は h264 codec -> use_gpu=True で auto 選択 -> vendor=nvidia
    assert info["gpu_vendor_used"] == "nvidia"
    assert info["vendor_preference"] == ["nvidia", "amd", "intel"]


def test_detect_records_vendor_used_null_when_cpu_forced(tmp_path, monkeypatch):
    """#591 -- --no-gpu (use_gpu=False) では vendor_used=None だが available は埋まる."""
    monkeypatch.setattr(
        "allaganeye.system_info.probe_gpu_vendors",
        lambda: ["nvidia"],
    )
    probe, detect = _mock_detect_only(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0, use_gpu=False)
    with probe, detect:
        run_detect(Path("input.mp4"), config, quiet=True)

    payload = json.loads((tmp_path / "metadata.json").read_text("utf-8"))
    info = payload["system_info"]
    assert info["gpu_vendor_used"] is None
    assert info["gpu_vendors_available"] == ["nvidia"]


def test_detect_cache_hit_records_vendor_used_null(tmp_path, monkeypatch):
    """#591 -- cache hit でも system_info を書く (vendor_used=None, probe は実行)."""
    monkeypatch.setattr(
        "allaganeye.system_info.probe_gpu_vendors",
        lambda: ["intel"],
    )
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    with (
        patch(f"{MODULE_DETECT}.probe_video", return_value=PROBE_RESULT),
        patch(f"{MODULE_DETECT}._load_cache", return_value=BOUNDARIES),
    ):
        run_detect(Path("input.mp4"), config, quiet=True)

    payload = json.loads((tmp_path / "metadata.json").read_text("utf-8"))
    info = payload["system_info"]
    assert info["gpu_vendor_used"] is None  # cache hit で detect していない
    assert info["gpu_vendors_available"] == ["intel"]
