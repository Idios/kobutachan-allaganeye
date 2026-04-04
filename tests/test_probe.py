"""Tests for video probe module."""

import json
from unittest.mock import patch

import pytest

from allaganeye.video.probe import _parse_frame_rate, probe_video
from allaganeye.exceptions import VideoProcessingError


def test_probe_nonexistent_file(tmp_path):
    """Probing a nonexistent file raises VideoProcessingError."""
    fake = tmp_path / "nonexistent.mp4"
    with pytest.raises(VideoProcessingError):
        probe_video(fake)


# --- _parse_frame_rate tests ---


@pytest.mark.parametrize(
    ("rate_str", "expected"),
    [
        ("30/1", 30.0),
        ("60000/1001", pytest.approx(59.94, rel=1e-2)),
        ("24/1", 24.0),
    ],
)
def test_parse_frame_rate_valid(rate_str, expected):
    assert _parse_frame_rate(rate_str) == expected


@pytest.mark.parametrize(
    "rate_str",
    ["0/0", "0/1", "invalid", "", "30", "abc/def"],
)
def test_parse_frame_rate_invalid(rate_str):
    assert _parse_frame_rate(rate_str) == 0.0


# --- fps fallback tests ---


def _make_ffprobe_output(r_frame_rate="30/1", avg_frame_rate="30/1"):
    """Build a fake ffprobe JSON output."""
    return json.dumps(
        {
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080,
                    "r_frame_rate": r_frame_rate,
                    "avg_frame_rate": avg_frame_rate,
                }
            ],
            "format": {"duration": "600.0"},
        }
    )


@patch("allaganeye.video.probe.subprocess.run")
def test_probe_fps_from_r_frame_rate(mock_run, tmp_path):
    """fps is parsed from r_frame_rate when valid."""
    video = tmp_path / "test.mp4"
    video.touch()
    mock_run.return_value.stdout = _make_ffprobe_output(
        r_frame_rate="60/1", avg_frame_rate="30/1"
    )
    result = probe_video(video)
    assert result["fps"] == 60.0


@patch("allaganeye.video.probe.subprocess.run")
def test_probe_fps_fallback_to_avg_frame_rate(mock_run, tmp_path):
    """fps falls back to avg_frame_rate when r_frame_rate is unusable."""
    video = tmp_path / "test.mp4"
    video.touch()
    mock_run.return_value.stdout = _make_ffprobe_output(
        r_frame_rate="0/0", avg_frame_rate="29/1"
    )
    result = probe_video(video)
    assert result["fps"] == 29.0


@patch("allaganeye.video.probe.subprocess.run")
def test_probe_fps_error_when_both_fail(mock_run, tmp_path):
    """VideoProcessingError raised when both frame rate fields are unusable."""
    video = tmp_path / "test.mp4"
    video.touch()
    mock_run.return_value.stdout = _make_ffprobe_output(
        r_frame_rate="0/0", avg_frame_rate="invalid"
    )
    with pytest.raises(VideoProcessingError, match="Cannot determine video frame rate"):
        probe_video(video)
