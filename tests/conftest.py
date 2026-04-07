"""Shared test fixtures for Allagan Eye."""

import os
import time
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def sample_video_dir() -> Path:
    """Path to sample video data directory.

    Reads from ALLAGANEYE_SAMPLE_VIDEO_DIR environment variable.
    Skips the test if the variable is not set or the directory does not exist.
    """
    env_path = os.environ.get("ALLAGANEYE_SAMPLE_VIDEO_DIR")
    if not env_path:
        pytest.skip("ALLAGANEYE_SAMPLE_VIDEO_DIR not set")
    path = Path(env_path)
    if not path.is_dir():
        pytest.skip(f"Sample video directory not found: {path}")
    return path


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


@pytest.fixture(autouse=True)
def _ffmpeg_interval(request: pytest.FixtureRequest) -> Iterator[None]:
    """Insert 1s interval after slow-marked tests to prevent GPU deadlock.

    Repeated ffmpeg calls can cause NVIDIA driver unresponsiveness due to
    GPU memory fragmentation.  A 1s cooldown between tests mitigates this.
    """
    yield
    if request.node.get_closest_marker("slow"):
        time.sleep(1)
