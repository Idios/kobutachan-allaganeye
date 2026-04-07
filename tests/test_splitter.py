"""Tests for video splitter module."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from allaganeye.exceptions import VideoProcessingError
from allaganeye.video.splitter import _ffmpeg_split, split_video


# --- Existing test ---


def test_split_nonexistent_file(tmp_path):
    """Splitting a nonexistent file raises VideoProcessingError."""
    fake = tmp_path / "nonexistent.mp4"
    boundaries = [{"start": 0.0, "end": 10.0}]
    with pytest.raises(VideoProcessingError):
        split_video(fake, boundaries, tmp_path)


# --- _ffmpeg_split command verification ---


class TestFfmpegSplitCommand:
    """Verify ffmpeg command argument order and values."""

    @patch("allaganeye.video.splitter.subprocess.run")
    def test_ss_before_i(self, mock_run):
        """'-ss' must appear before '-i' for fast input seeking."""
        mock_run.return_value = MagicMock(returncode=0)
        _ffmpeg_split(
            Path("input.mp4"), start=600.0, end=1200.0, output=Path("out.mp4")
        )

        args = mock_run.call_args[0][0]
        ss_idx = args.index("-ss")
        i_idx = args.index("-i")
        assert ss_idx < i_idx, f"-ss (pos {ss_idx}) should be before -i (pos {i_idx})"

    @patch("allaganeye.video.splitter.subprocess.run")
    def test_to_is_duration(self, mock_run):
        """-to should be duration (end - start), not absolute end time."""
        mock_run.return_value = MagicMock(returncode=0)
        _ffmpeg_split(
            Path("input.mp4"), start=600.0, end=1200.0, output=Path("out.mp4")
        )

        args = mock_run.call_args[0][0]
        to_idx = args.index("-to")
        to_value = float(args[to_idx + 1])
        assert to_value == pytest.approx(600.0)

    @patch("allaganeye.video.splitter.subprocess.run")
    def test_ss_value(self, mock_run):
        """-ss should have the start time value."""
        mock_run.return_value = MagicMock(returncode=0)
        _ffmpeg_split(
            Path("input.mp4"), start=120.5, end=1380.2, output=Path("out.mp4")
        )

        args = mock_run.call_args[0][0]
        ss_idx = args.index("-ss")
        ss_value = float(args[ss_idx + 1])
        assert ss_value == pytest.approx(120.5)


# --- split_video normal cases ---


@patch("allaganeye.video.splitter.subprocess.run")
def test_split_single_boundary(mock_run, tmp_path):
    """Single boundary produces one output file."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=["ffmpeg"], returncode=0, stdout="", stderr=""
    )
    video = tmp_path / "input.mp4"
    boundaries = [{"start": 10.0, "end": 300.0}]

    result = split_video(video, boundaries, tmp_path)

    assert len(result) == 1
    assert result[0] == tmp_path / "match_001.mp4"
    assert mock_run.call_count == 1


@patch("allaganeye.video.splitter.subprocess.run")
def test_split_multiple_boundaries(mock_run, tmp_path):
    """Multiple boundaries produce correctly numbered files."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=["ffmpeg"], returncode=0, stdout="", stderr=""
    )
    video = tmp_path / "input.mp4"
    boundaries = [
        {"start": 0.0, "end": 600.0},
        {"start": 610.0, "end": 1200.0},
        {"start": 1210.0, "end": 1800.0},
    ]

    result = split_video(video, boundaries, tmp_path)

    assert len(result) == 3
    assert result[0].name == "match_001.mp4"
    assert result[1].name == "match_002.mp4"
    assert result[2].name == "match_003.mp4"
    assert mock_run.call_count == 3


@patch("allaganeye.video.splitter.subprocess.run")
def test_split_empty_boundaries(mock_run, tmp_path):
    """Empty boundaries list returns empty list without calling ffmpeg."""
    video = tmp_path / "input.mp4"

    result = split_video(video, [], tmp_path)

    assert result == []
    mock_run.assert_not_called()


# --- Error cases ---


@patch("allaganeye.video.splitter.subprocess.run")
def test_split_ffmpeg_returns_nonzero(mock_run, tmp_path):
    """FFmpeg non-zero exit raises VideoProcessingError."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=["ffmpeg"], returncode=1, stdout="", stderr="encoding failed"
    )
    video = tmp_path / "input.mp4"
    boundaries = [{"start": 0.0, "end": 300.0}]

    with pytest.raises(VideoProcessingError, match="ffmpeg split failed"):
        split_video(video, boundaries, tmp_path)


@patch("allaganeye.video.splitter.subprocess.run")
def test_split_ffmpeg_not_found(mock_run, tmp_path):
    """Missing ffmpeg raises VideoProcessingError."""
    mock_run.side_effect = FileNotFoundError()
    video = tmp_path / "input.mp4"
    boundaries = [{"start": 0.0, "end": 300.0}]

    with pytest.raises(VideoProcessingError, match="ffmpeg not found"):
        split_video(video, boundaries, tmp_path)


@patch("allaganeye.video.splitter.subprocess.run")
def test_split_partial_failure(mock_run, tmp_path):
    """Partial failure: first split succeeds, second fails, error propagates."""
    success = subprocess.CompletedProcess(
        args=["ffmpeg"], returncode=0, stdout="", stderr=""
    )
    failure = subprocess.CompletedProcess(
        args=["ffmpeg"], returncode=1, stdout="", stderr="disk full"
    )
    mock_run.side_effect = [success, failure]
    video = tmp_path / "input.mp4"
    boundaries = [
        {"start": 0.0, "end": 600.0},
        {"start": 610.0, "end": 1200.0},
    ]

    with pytest.raises(VideoProcessingError, match="ffmpeg split failed"):
        split_video(video, boundaries, tmp_path)

    # First call succeeded, second failed
    assert mock_run.call_count == 2


@patch("allaganeye.video.splitter.subprocess.run")
@patch("allaganeye.video.splitter.find_ffmpeg", return_value="ffmpeg")
def test_timeout_raises_video_processing_error(_mock_ffmpeg, mock_run, tmp_path):
    """ffmpeg split timeout raises VideoProcessingError."""
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="ffmpeg", timeout=120)
    output = tmp_path / "out.mp4"
    with pytest.raises(VideoProcessingError, match="timed out"):
        _ffmpeg_split(Path("input.mp4"), start=0.0, end=600.0, output=output)


@patch("allaganeye.video.splitter.subprocess.run")
@patch("allaganeye.video.splitter.find_ffmpeg", return_value="ffmpeg")
def test_timeout_scales_with_duration(_mock_ffmpeg, mock_run, tmp_path):
    """Timeout scales: max(duration*2 + 60, 120)."""
    result = MagicMock()
    result.returncode = 0
    mock_run.return_value = result
    output = tmp_path / "out.mp4"
    _ffmpeg_split(Path("input.mp4"), start=0.0, end=600.0, output=output)
    # 600 * 2 + 60 = 1260 > 120
    assert mock_run.call_args.kwargs["timeout"] == 1260
