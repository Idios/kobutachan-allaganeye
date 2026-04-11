"""Tests for video probe module."""

import json
import subprocess
from unittest.mock import patch

import pytest

from allaganeye.exceptions import InputFileError, VideoProcessingError
from allaganeye.video.probe import _parse_frame_rate, probe_video


# --- Existing test ---


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


# --- Helpers ---


def _make_ffprobe_output(r_frame_rate="30/1", avg_frame_rate="30/1", **overrides):
    """Build a fake ffprobe JSON output.

    Args:
        r_frame_rate: Value for r_frame_rate field.
        avg_frame_rate: Value for avg_frame_rate field.
        **overrides: Override keys in the video stream or format dict.
            Supported: duration, width, height, codec_name, audio_codec,
            include_audio, include_video.
    """
    duration = overrides.get("duration", "600.0")
    width = overrides.get("width", 1920)
    height = overrides.get("height", 1080)
    codec_name = overrides.get("codec_name", "h264")
    audio_codec = overrides.get("audio_codec", "aac")
    include_audio = overrides.get("include_audio", True)
    include_video = overrides.get("include_video", True)

    streams = []
    if include_video:
        streams.append(
            {
                "codec_type": "video",
                "codec_name": codec_name,
                "width": width,
                "height": height,
                "r_frame_rate": r_frame_rate,
                "avg_frame_rate": avg_frame_rate,
            }
        )
    if include_audio:
        streams.append({"codec_type": "audio", "codec_name": audio_codec})
    return json.dumps({"streams": streams, "format": {"duration": duration}})


def _mock_result(stdout="", returncode=0):
    return subprocess.CompletedProcess(
        args=["ffprobe"], returncode=returncode, stdout=stdout, stderr=""
    )


# --- fps fallback tests ---


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


# --- Normal cases ---


@patch("allaganeye.video.probe.subprocess.run")
def test_probe_normal_mp4(mock_run, tmp_path):
    """Normal ffprobe output is parsed correctly."""
    video = tmp_path / "test.mp4"
    video.touch()
    mock_run.return_value = _mock_result(stdout=_make_ffprobe_output(duration="1800.5"))

    result = probe_video(video)

    assert result["duration"] == 1800.5
    assert result["width"] == 1920
    assert result["height"] == 1080
    assert result["fps"] == 30.0
    assert result["codec"] == "h264"
    assert result["audio_codec"] == "aac"


@patch("allaganeye.video.probe.subprocess.run")
def test_probe_fractional_fps(mock_run, tmp_path):
    """Fractional fps (e.g., 60000/1001) is parsed correctly."""
    video = tmp_path / "test.mp4"
    video.touch()
    mock_run.return_value = _mock_result(
        stdout=_make_ffprobe_output(
            r_frame_rate="60000/1001", avg_frame_rate="60000/1001"
        )
    )

    result = probe_video(video)
    assert result["fps"] == pytest.approx(59.94, rel=1e-2)


# --- FPS edge cases (both r_frame_rate and avg_frame_rate must fail) ---


@patch("allaganeye.video.probe.subprocess.run")
def test_probe_fps_zero_denominator(mock_run, tmp_path):
    """Zero denominator in both frame rate fields raises VideoProcessingError."""
    video = tmp_path / "test.mp4"
    video.touch()
    mock_run.return_value = _mock_result(
        stdout=_make_ffprobe_output(r_frame_rate="30/0", avg_frame_rate="0/0")
    )

    with pytest.raises(VideoProcessingError, match="Cannot determine video frame rate"):
        probe_video(video)


@patch("allaganeye.video.probe.subprocess.run")
def test_probe_fps_non_numeric(mock_run, tmp_path):
    """Non-numeric fps in both fields raises VideoProcessingError."""
    video = tmp_path / "test.mp4"
    video.touch()
    mock_run.return_value = _mock_result(
        stdout=_make_ffprobe_output(r_frame_rate="abc/def", avg_frame_rate="N/A")
    )

    with pytest.raises(VideoProcessingError, match="Cannot determine video frame rate"):
        probe_video(video)


@patch("allaganeye.video.probe.subprocess.run")
def test_probe_fps_missing_key(mock_run, tmp_path):
    """Missing r_frame_rate falls back to avg_frame_rate; both empty raises error."""
    video = tmp_path / "test.mp4"
    video.touch()
    data = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "avg_frame_rate": "",
            }
        ],
        "format": {"duration": "600.0"},
    }
    mock_run.return_value = _mock_result(stdout=json.dumps(data))

    with pytest.raises(VideoProcessingError, match="Cannot determine video frame rate"):
        probe_video(video)


# --- Stream handling ---


@patch("allaganeye.video.probe.subprocess.run")
def test_probe_no_audio_stream(mock_run, tmp_path):
    """Video without audio stream returns audio_codec=None."""
    video = tmp_path / "test.mp4"
    video.touch()
    mock_run.return_value = _mock_result(
        stdout=_make_ffprobe_output(include_audio=False)
    )

    result = probe_video(video)
    assert result["audio_codec"] is None


@patch("allaganeye.video.probe.subprocess.run")
def test_probe_no_video_stream(mock_run, tmp_path):
    """File with no video stream raises InputFileError."""
    video = tmp_path / "test.mp4"
    video.touch()
    mock_run.return_value = _mock_result(
        stdout=_make_ffprobe_output(include_video=False)
    )

    with pytest.raises(InputFileError, match="No video stream"):
        probe_video(video)


@patch("allaganeye.video.probe.subprocess.run")
def test_probe_empty_streams(mock_run, tmp_path):
    """Empty streams list raises InputFileError."""
    video = tmp_path / "test.mp4"
    video.touch()
    mock_run.return_value = _mock_result(
        stdout=json.dumps({"streams": [], "format": {"duration": "600.0"}})
    )

    with pytest.raises(InputFileError, match="No video stream"):
        probe_video(video)


# --- Error cases ---


@patch("allaganeye.video.probe.subprocess.run")
def test_probe_invalid_json(mock_run, tmp_path):
    """Invalid JSON from ffprobe raises VideoProcessingError."""
    video = tmp_path / "test.mp4"
    video.touch()
    mock_run.return_value = _mock_result(stdout="not valid json {{{")

    with pytest.raises(VideoProcessingError, match="invalid JSON"):
        probe_video(video)


@patch("allaganeye.video.probe.subprocess.run")
def test_probe_subprocess_failure(mock_run, tmp_path):
    """ffprobe CalledProcessError raises VideoProcessingError."""
    video = tmp_path / "test.mp4"
    video.touch()
    mock_run.side_effect = subprocess.CalledProcessError(1, "ffprobe", stderr="error")

    with pytest.raises(VideoProcessingError, match="ffprobe failed"):
        probe_video(video)


@patch("allaganeye.video.probe.subprocess.run")
def test_probe_ffprobe_not_found(mock_run, tmp_path):
    """Missing ffprobe raises VideoProcessingError."""
    video = tmp_path / "test.mp4"
    video.touch()
    mock_run.side_effect = FileNotFoundError()

    with pytest.raises(VideoProcessingError, match="ffprobe not found"):
        probe_video(video)


# --- Missing metadata ---


@patch("allaganeye.video.probe.subprocess.run")
def test_probe_missing_duration(mock_run, tmp_path):
    """Missing duration in format raises VideoProcessingError."""
    video = tmp_path / "test.mp4"
    video.touch()
    data = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "r_frame_rate": "30/1",
                "avg_frame_rate": "30/1",
            }
        ],
        "format": {},
    }
    mock_run.return_value = _mock_result(stdout=json.dumps(data))

    with pytest.raises(VideoProcessingError, match="duration"):
        probe_video(video)


@patch("allaganeye.video.probe.subprocess.run")
def test_probe_missing_dimensions(mock_run, tmp_path):
    """Missing width/height raises VideoProcessingError."""
    video = tmp_path / "test.mp4"
    video.touch()
    data = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "r_frame_rate": "30/1",
                "avg_frame_rate": "30/1",
            }
        ],
        "format": {"duration": "600.0"},
    }
    mock_run.return_value = _mock_result(stdout=json.dumps(data))

    with pytest.raises(VideoProcessingError, match="resolution"):
        probe_video(video)


@patch("allaganeye.video.probe.subprocess.run")
@patch("allaganeye.video.probe.find_ffprobe", return_value="ffprobe")
def test_timeout_raises_video_processing_error(_mock_ffprobe, mock_run, tmp_path):
    """ffprobe timeout raises VideoProcessingError."""
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="ffprobe", timeout=30)
    video = tmp_path / "test.mp4"
    video.write_bytes(b"")
    with pytest.raises(VideoProcessingError, match="timed out"):
        probe_video(video)
