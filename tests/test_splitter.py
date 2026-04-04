"""Tests for video splitter module."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from allaganeye.video.splitter import split_video, _ffmpeg_split
from allaganeye.exceptions import VideoProcessingError


def test_split_nonexistent_file(tmp_path):
    """Splitting a nonexistent file raises VideoProcessingError."""
    fake = tmp_path / "nonexistent.mp4"
    boundaries = [{"start": 0.0, "end": 10.0}]
    with pytest.raises(VideoProcessingError):
        split_video(fake, boundaries, tmp_path)


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
