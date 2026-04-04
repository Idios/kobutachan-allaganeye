"""Shared test fixtures for Allagan Eye."""

import os
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
