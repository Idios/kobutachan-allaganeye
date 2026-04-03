"""Tests for video probe module."""

import pytest

from allaganeye.video.probe import probe_video
from allaganeye.exceptions import VideoProcessingError


def test_probe_nonexistent_file(tmp_path):
    """Probing a nonexistent file raises VideoProcessingError."""
    fake = tmp_path / "nonexistent.mp4"
    with pytest.raises(VideoProcessingError):
        probe_video(fake)
