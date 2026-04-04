"""Tests for split_matches pipeline orchestration."""

from pathlib import Path
from unittest.mock import patch

import pytest

from allaganeye.config import SplitConfig
from allaganeye.exceptions import AllaganEyeError, DetectionError


@pytest.fixture
def config(tmp_path):
    return SplitConfig(output_dir=tmp_path / "output", min_match_duration=60.0)


@pytest.fixture
def mock_pipeline():
    """Mock probe/detect/split for pipeline tests."""
    with (
        patch("allaganeye.commands.split_matches.probe_video") as mock_probe,
        patch(
            "allaganeye.commands.split_matches.detect_match_boundaries"
        ) as mock_detect,
        patch("allaganeye.commands.split_matches.split_video") as mock_split,
    ):
        mock_probe.return_value = {
            "duration": 1200.0,
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "codec": "h264",
            "audio_codec": "aac",
        }
        mock_detect.return_value = [
            {"start": 0.0, "end": 600.0},
            {"start": 610.0, "end": 1200.0},
        ]
        mock_split.return_value = [
            Path("output/match_001.mp4"),
            Path("output/match_002.mp4"),
        ]
        yield mock_probe, mock_detect, mock_split


class TestMkdirError:
    def test_mkdir_permission_error(self, config, mock_pipeline):
        from allaganeye.commands.split_matches import run_split

        with patch.object(
            Path, "mkdir", side_effect=PermissionError("Permission denied")
        ):
            with pytest.raises(AllaganEyeError, match="Cannot create output directory"):
                run_split(Path("video.mp4"), config)

    def test_mkdir_oserror(self, config, mock_pipeline):
        from allaganeye.commands.split_matches import run_split

        with patch.object(Path, "mkdir", side_effect=OSError("Disk error")):
            with pytest.raises(AllaganEyeError, match="Cannot create output directory"):
                run_split(Path("video.mp4"), config)


class TestMetadataWriteError:
    def test_write_text_oserror(self, tmp_path, mock_pipeline):
        config = SplitConfig(output_dir=tmp_path / "output", min_match_duration=60.0)

        from allaganeye.commands.split_matches import run_split

        with patch.object(Path, "write_text", side_effect=OSError("Disk full")):
            with pytest.raises(AllaganEyeError, match="Cannot write metadata"):
                run_split(Path("video.mp4"), config)


class TestDetectionEmpty:
    def test_no_boundaries_raises(self, config):
        from allaganeye.commands.split_matches import run_split

        with (
            patch("allaganeye.commands.split_matches.probe_video") as mock_probe,
            patch(
                "allaganeye.commands.split_matches.detect_match_boundaries"
            ) as mock_detect,
        ):
            mock_probe.return_value = {
                "duration": 1200.0,
                "width": 1920,
                "height": 1080,
                "fps": 30.0,
                "codec": "h264",
                "audio_codec": "aac",
            }
            mock_detect.return_value = []
            with pytest.raises(DetectionError):
                run_split(Path("video.mp4"), config)
