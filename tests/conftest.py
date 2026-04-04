"""Shared test fixtures for Allagan Eye."""

from pathlib import Path

import pytest


@pytest.fixture
def sample_video_dir() -> Path:
    """Path to sample video data directory."""
    return Path(r"E:\royalstraightflesh\videos")


@pytest.fixture
def tmp_output_dir(tmp_path: Path) -> Path:
    """Temporary output directory for test results."""
    output = tmp_path / "output"
    output.mkdir()
    return output


@pytest.fixture
def fake_video(tmp_path: Path) -> Path:
    """Create a zero-byte .mp4 file that passes CLI validation."""
    video = tmp_path / "test_video.mp4"
    video.write_bytes(b"")
    return video
