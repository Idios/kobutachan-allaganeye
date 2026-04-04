"""Tests for split_matches pipeline orchestration."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from allaganeye.commands.split_matches import run_split
from allaganeye.config import SplitConfig
from allaganeye.exceptions import AllaganEyeError, DetectionError, VideoProcessingError

# Standard mock return values
PROBE_RESULT = {
    "duration": 1800.0,
    "width": 1920,
    "height": 1080,
    "fps": 30.0,
    "codec": "h264",
    "audio_codec": "aac",
}

BOUNDARIES = [
    {"start": 0.0, "end": 600.0},
    {"start": 610.0, "end": 1200.0},
]

MODULE = "allaganeye.commands.split_matches"


def _output_files(output_dir: Path) -> list[Path]:
    return [output_dir / "match_001.mp4", output_dir / "match_002.mp4"]


# --- Fixtures ---


@pytest.fixture
def config(tmp_path):
    return SplitConfig(output_dir=tmp_path / "output", min_match_duration=60.0)


@pytest.fixture
def mock_pipeline():
    """Mock probe/detect/split for pipeline tests."""
    with (
        patch(f"{MODULE}.probe_video") as mock_probe,
        patch(f"{MODULE}.detect_match_boundaries") as mock_detect,
        patch(f"{MODULE}.split_video") as mock_split,
    ):
        mock_probe.return_value = PROBE_RESULT
        mock_detect.return_value = BOUNDARIES
        mock_split.return_value = [
            Path("output/match_001.mp4"),
            Path("output/match_002.mp4"),
        ]
        yield mock_probe, mock_detect, mock_split


# --- Pipeline happy path ---


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_pipeline_happy_path(mock_probe, mock_detect, mock_split, tmp_path):
    """Full pipeline calls probe, detect, split in order and writes metadata."""
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    video = Path("input.mp4")

    run_split(video, config)

    mock_probe.assert_called_once_with(video)
    mock_detect.assert_called_once_with(
        video,
        duration_hint=PROBE_RESULT["duration"],
        sample_interval=config.sample_interval,
        blackout_threshold=config.blackout_threshold,
        min_match_duration=config.min_match_duration,
    )
    mock_split.assert_called_once_with(video, BOUNDARIES, tmp_path)
    assert (tmp_path / "metadata.json").exists()


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_pipeline_metadata_json_content(mock_probe, mock_detect, mock_split, tmp_path):
    """metadata.json contains correct structure and values."""
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config)

    data = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    assert data["source"] == "input.mp4"
    assert data["source_duration"] == 1800.0
    assert len(data["matches"]) == 2
    m1 = data["matches"][0]
    assert m1["index"] == 1
    assert m1["start_time"] == 0.0
    assert m1["end_time"] == 600.0
    assert m1["duration"] == 600.0
    assert "match_001" in m1["output_file"]


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_pipeline_output_dir_created(mock_probe, mock_detect, mock_split, tmp_path):
    """Output directory is created if it doesn't exist."""
    output = tmp_path / "subdir" / "output"
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = [output / "match_001.mp4", output / "match_002.mp4"]
    config = SplitConfig(output_dir=output, min_match_duration=60.0)

    run_split(Path("input.mp4"), config)

    assert output.is_dir()


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_pipeline_dry_run(mock_probe, mock_detect, mock_split, tmp_path):
    """Dry-run mode skips split and metadata writing."""
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    config = SplitConfig(output_dir=tmp_path, dry_run=True, min_match_duration=60.0)

    run_split(Path("input.mp4"), config)

    mock_probe.assert_called_once()
    mock_detect.assert_called_once()
    mock_split.assert_not_called()
    assert not (tmp_path / "metadata.json").exists()


# --- Detection empty ---


def test_pipeline_no_boundaries():
    """Zero boundaries raises DetectionError."""
    with (
        patch(f"{MODULE}.probe_video") as mock_probe,
        patch(f"{MODULE}.detect_match_boundaries") as mock_detect,
    ):
        mock_probe.return_value = PROBE_RESULT
        mock_detect.return_value = []
        config = SplitConfig(min_match_duration=60.0)

        with pytest.raises(DetectionError, match="No match boundaries detected"):
            run_split(Path("input.mp4"), config)


# --- Error propagation ---


@patch(f"{MODULE}.probe_video")
def test_pipeline_probe_failure(mock_probe):
    """Probe failure propagates VideoProcessingError."""
    mock_probe.side_effect = VideoProcessingError("ffprobe failed")
    config = SplitConfig(min_match_duration=60.0)

    with pytest.raises(VideoProcessingError, match="ffprobe failed"):
        run_split(Path("input.mp4"), config)


@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_pipeline_detect_failure(mock_probe, mock_detect):
    """Detection failure propagates VideoProcessingError."""
    mock_probe.return_value = PROBE_RESULT
    mock_detect.side_effect = VideoProcessingError("Cannot open video")
    config = SplitConfig(min_match_duration=60.0)

    with pytest.raises(VideoProcessingError, match="Cannot open video"):
        run_split(Path("input.mp4"), config)


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_pipeline_split_failure(mock_probe, mock_detect, mock_split, tmp_path):
    """Split failure propagates VideoProcessingError."""
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.side_effect = VideoProcessingError("ffmpeg failed")
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    with pytest.raises(VideoProcessingError, match="ffmpeg failed"):
        run_split(Path("input.mp4"), config)


# --- Error handling (from PR #34) ---


class TestMkdirError:
    def test_mkdir_permission_error(self, config, mock_pipeline):
        with patch.object(
            Path, "mkdir", side_effect=PermissionError("Permission denied")
        ):
            with pytest.raises(AllaganEyeError, match="Cannot create output directory"):
                run_split(Path("video.mp4"), config)


class TestMetadataWriteError:
    def test_write_text_oserror(self, tmp_path, mock_pipeline):
        cfg = SplitConfig(output_dir=tmp_path / "output", min_match_duration=60.0)

        with patch.object(Path, "write_text", side_effect=OSError("Disk full")):
            with pytest.raises(AllaganEyeError, match="Cannot write metadata"):
                run_split(Path("video.mp4"), cfg)


# --- Verbose output ---


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_pipeline_verbose_output(mock_probe, mock_detect, mock_split, tmp_path, capsys):
    """Verbose mode prints probe info and match details."""
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config, verbose=True)

    output = capsys.readouterr().out
    assert "Probing:" in output
    assert "Duration:" in output
    assert "Detecting match boundaries" in output
    assert "Match 1:" in output
    assert "Match 2:" in output


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_pipeline_non_verbose_output(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """Non-verbose mode prints summary but not details."""
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config, verbose=False)

    output = capsys.readouterr().out
    assert "Detected 2 match(es)" in output
    assert "Probing:" not in output
    assert "Match 1:" not in output


# --- Config forwarding ---


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_pipeline_config_params_forwarded(
    mock_probe, mock_detect, mock_split, tmp_path
):
    """Non-default config values are forwarded to detect_match_boundaries."""
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(
        output_dir=tmp_path,
        sample_interval=2.0,
        blackout_threshold=20.0,
        min_match_duration=120.0,
    )

    run_split(Path("input.mp4"), config)

    mock_detect.assert_called_once_with(
        Path("input.mp4"),
        duration_hint=PROBE_RESULT["duration"],
        sample_interval=2.0,
        blackout_threshold=20.0,
        min_match_duration=120.0,
    )
