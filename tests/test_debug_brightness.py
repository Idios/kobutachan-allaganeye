"""Tests for debug-brightness command."""

from pathlib import Path
from unittest.mock import patch

import click.exceptions
import numpy as np
import pytest

from allaganeye.commands.debug_brightness import run_debug_brightness

MODULE = "allaganeye.commands.debug_brightness"

PROBE_RESULT = {
    "duration": 300.0,
    "width": 1920,
    "height": 1080,
    "fps": 30.0,
    "codec": "h264",
    "audio_codec": "aac",
}


@patch(f"{MODULE}._probe_single_frame")
@patch(f"{MODULE}.probe_video")
def test_csv_output(mock_probe_video, mock_probe_frame, capsys):
    """Output is CSV with header and sorted rows."""
    mock_probe_video.return_value = PROBE_RESULT
    mock_probe_frame.return_value = 42.5

    run_debug_brightness(Path("test.mp4"), start=0.0, end=3.0, interval=1.0)

    output = capsys.readouterr().out
    lines = output.strip().split("\n")
    assert lines[0] == "timestamp,brightness"
    assert len(lines) == 4  # header + 3 rows (0.0, 1.0, 2.0)
    assert lines[1] == "0.0,42.5"
    assert lines[2] == "1.0,42.5"
    assert lines[3] == "2.0,42.5"


@patch(f"{MODULE}._probe_single_frame")
@patch(f"{MODULE}.probe_video")
def test_start_end_range(mock_probe_video, mock_probe_frame, capsys):
    """--start and --end restrict the probed range."""
    mock_probe_video.return_value = PROBE_RESULT
    mock_probe_frame.return_value = 10.0

    run_debug_brightness(Path("test.mp4"), start=100.0, end=103.0, interval=1.0)

    output = capsys.readouterr().out
    lines = output.strip().split("\n")
    assert len(lines) == 4  # header + 3 rows
    assert "100.0" in lines[1]
    assert "101.0" in lines[2]
    assert "102.0" in lines[3]


@patch(f"{MODULE}._probe_single_frame")
@patch(f"{MODULE}.probe_video")
def test_end_defaults_to_duration(mock_probe_video, mock_probe_frame, capsys):
    """end=None uses video duration."""
    mock_probe_video.return_value = {**PROBE_RESULT, "duration": 5.0}
    mock_probe_frame.return_value = 50.0

    run_debug_brightness(Path("test.mp4"), start=0.0, end=None, interval=1.0)

    output = capsys.readouterr().out
    lines = output.strip().split("\n")
    assert len(lines) == 6  # header + 5 rows (0,1,2,3,4)


@patch(f"{MODULE}._probe_single_frame")
@patch(f"{MODULE}.probe_video")
def test_custom_interval(mock_probe_video, mock_probe_frame, capsys):
    """Custom interval changes sample count."""
    mock_probe_video.return_value = PROBE_RESULT
    mock_probe_frame.return_value = 30.0

    run_debug_brightness(Path("test.mp4"), start=0.0, end=5.0, interval=2.0)

    output = capsys.readouterr().out
    lines = output.strip().split("\n")
    # 0.0, 2.0, 4.0 = 3 rows
    assert len(lines) == 4  # header + 3 rows


@patch(f"{MODULE}._probe_single_frame")
@patch(f"{MODULE}.probe_video")
def test_end_clamped_to_duration(mock_probe_video, mock_probe_frame, capsys):
    """--end beyond duration is clamped."""
    mock_probe_video.return_value = {**PROBE_RESULT, "duration": 3.0}
    mock_probe_frame.return_value = 20.0

    run_debug_brightness(Path("test.mp4"), start=0.0, end=999.0, interval=1.0)

    output = capsys.readouterr().out
    lines = output.strip().split("\n")
    assert len(lines) == 4  # header + 3 rows (0,1,2)


@patch(f"{MODULE}.probe_video")
def test_start_ge_end_exits(mock_probe_video):
    """start >= end raises SystemExit."""
    mock_probe_video.return_value = PROBE_RESULT

    with pytest.raises(click.exceptions.Exit):
        run_debug_brightness(Path("test.mp4"), start=200.0, end=100.0, interval=1.0)


@patch(f"{MODULE}._probe_single_frame")
@patch(f"{MODULE}.probe_video")
def test_varying_brightness(mock_probe_video, mock_probe_frame, capsys):
    """Different brightness values per timestamp are correctly reported."""
    mock_probe_video.return_value = PROBE_RESULT

    def side_effect(path, t):
        return {0.0: 5.0, 1.0: 128.0, 2.0: 42.3}.get(t, 100.0)

    mock_probe_frame.side_effect = side_effect

    run_debug_brightness(Path("test.mp4"), start=0.0, end=3.0, interval=1.0)

    output = capsys.readouterr().out
    lines = output.strip().split("\n")
    assert lines[1] == "0.0,5.0"
    assert lines[2] == "1.0,128.0"
    assert lines[3] == "2.0,42.3"


# --- Scorebar ROI mode tests ---


def _make_rgb_frame(r: int = 128, g: int = 128, b: int = 128) -> bytes:
    """Create a 320x180 RGB24 frame filled with a uniform color."""
    frame = np.zeros((180, 320, 3), dtype=np.uint8)
    frame[:, :, 0] = r
    frame[:, :, 1] = g
    frame[:, :, 2] = b
    return frame.tobytes()


@patch(f"{MODULE}._probe_frame_rgb")
@patch(f"{MODULE}.probe_video")
def test_scorebar_csv_header(mock_probe_video, mock_probe_rgb, capsys):
    """Scorebar mode outputs CSV with ROI columns."""
    mock_probe_video.return_value = PROBE_RESULT
    mock_probe_rgb.return_value = _make_rgb_frame(100, 50, 200)

    run_debug_brightness(
        Path("test.mp4"), start=0.0, end=2.0, interval=1.0, roi_mode="scorebar"
    )

    output = capsys.readouterr().out
    lines = output.strip().split("\n")
    assert (
        lines[0]
        == "timestamp,brightness,roi_r_mean,roi_g_mean,roi_b_mean,roi_brightness"
    )
    assert len(lines) == 3  # header + 2 rows


@patch(f"{MODULE}._probe_frame_rgb")
@patch(f"{MODULE}.probe_video")
def test_scorebar_roi_values(mock_probe_video, mock_probe_rgb, capsys):
    """Scorebar mode computes correct ROI channel means."""
    mock_probe_video.return_value = PROBE_RESULT
    # Create frame with distinct ROI: scorebar region (y=0:15, x=80:240) = red
    frame = np.zeros((180, 320, 3), dtype=np.uint8)
    frame[:, :, :] = 50  # background
    frame[0:15, 80:240, 0] = 200  # ROI red channel
    frame[0:15, 80:240, 1] = 30  # ROI green channel
    frame[0:15, 80:240, 2] = 80  # ROI blue channel
    mock_probe_rgb.return_value = frame.tobytes()

    run_debug_brightness(
        Path("test.mp4"), start=0.0, end=1.0, interval=1.0, roi_mode="scorebar"
    )

    output = capsys.readouterr().out
    lines = output.strip().split("\n")
    parts = lines[1].split(",")
    assert len(parts) == 6
    assert parts[0] == "0.0"
    # ROI values should be the distinct values we set
    assert float(parts[2]) == pytest.approx(200.0, abs=0.1)  # roi_r
    assert float(parts[3]) == pytest.approx(30.0, abs=0.1)  # roi_g
    assert float(parts[4]) == pytest.approx(80.0, abs=0.1)  # roi_b


@patch(f"{MODULE}._probe_single_frame")
@patch(f"{MODULE}.probe_video")
def test_roi_mode_none_unchanged(mock_probe_video, mock_probe_frame, capsys):
    """roi_mode=None produces original 2-column CSV."""
    mock_probe_video.return_value = PROBE_RESULT
    mock_probe_frame.return_value = 42.5

    run_debug_brightness(
        Path("test.mp4"), start=0.0, end=2.0, interval=1.0, roi_mode=None
    )

    output = capsys.readouterr().out
    lines = output.strip().split("\n")
    assert lines[0] == "timestamp,brightness"
    assert len(lines[1].split(",")) == 2


@patch(f"{MODULE}._probe_frame_rgb")
@patch(f"{MODULE}.probe_video")
def test_scorebar_probe_failure(mock_probe_video, mock_probe_rgb, capsys):
    """Probe failure (None) outputs fallback values."""
    mock_probe_video.return_value = PROBE_RESULT
    mock_probe_rgb.return_value = None

    run_debug_brightness(
        Path("test.mp4"), start=0.0, end=1.0, interval=1.0, roi_mode="scorebar"
    )

    output = capsys.readouterr().out
    lines = output.strip().split("\n")
    parts = lines[1].split(",")
    assert parts[1] == "255.0"  # fallback brightness
