"""Tests for video splitter module."""

import pytest

from allaganeye.video.splitter import split_video
from allaganeye.exceptions import VideoProcessingError


def test_split_nonexistent_file(tmp_path):
    """Splitting a nonexistent file raises VideoProcessingError."""
    fake = tmp_path / "nonexistent.mp4"
    boundaries = [{"start": 0.0, "end": 10.0}]
    with pytest.raises(VideoProcessingError):
        split_video(fake, boundaries, tmp_path)
