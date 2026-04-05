"""Tests for debug-brightness command."""

from pathlib import Path
from unittest.mock import patch

import click.exceptions
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
