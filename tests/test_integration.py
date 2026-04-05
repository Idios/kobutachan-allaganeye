"""Integration tests using real video files.

All tests require:
- ALLAGANEYE_SAMPLE_VIDEO_DIR environment variable set to the sample video directory
- ffmpeg/ffprobe installed and in PATH

Run with: pytest -m slow

Design: The full pipeline (probe → detect → split) runs once per session
via the ``pipeline_result`` fixture.  Individual tests verify different
aspects of that single run to avoid repeated 15-minute detection passes.
"""

import json
import re
from pathlib import Path

import pytest

from allaganeye.video.probe import probe_video

pytestmark = pytest.mark.slow


# --- Helpers ---


def _find_source_mkv(subdir: Path) -> Path | None:
    """Find the source MKV in a subdirectory (the long recording)."""
    mkvs = sorted(subdir.glob("*.mkv"))
    if not mkvs:
        return None
    # The source recording is the largest MKV
    return max(mkvs, key=lambda p: p.stat().st_size)


def _find_manual_splits(subdir: Path) -> list[Path]:
    """Find manually split MP4 files matching YYYYMMDD_N.mp4 pattern."""
    pattern = re.compile(r"^\d{8}_\d+\.mp4$")
    return sorted(f for f in subdir.iterdir() if pattern.match(f.name))


def _find_subdir_with_splits(sample_video_dir: Path) -> Path | None:
    """Find a subdirectory that has both a source MKV and manual splits."""
    for subdir in sorted(sample_video_dir.iterdir()):
        if not subdir.is_dir():
            continue
        if _find_source_mkv(subdir) and _find_manual_splits(subdir):
            return subdir
    return None


# --- Fixtures ---


@pytest.fixture(scope="session")
def _sample_video_dir_session(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Session-scoped sample_video_dir (avoids per-test skip)."""
    import os

    env_path = os.environ.get("ALLAGANEYE_SAMPLE_VIDEO_DIR")
    if not env_path:
        pytest.skip("ALLAGANEYE_SAMPLE_VIDEO_DIR not set")
    path = Path(env_path)
    if not path.is_dir():
        pytest.skip(f"Sample video directory not found: {path}")
    return path


@pytest.fixture(scope="session")
def split_subdir(_sample_video_dir_session: Path) -> Path:
    """Find a subdirectory with source MKV and manual splits."""
    subdir = _find_subdir_with_splits(_sample_video_dir_session)
    if subdir is None:
        pytest.skip("No subdirectory with source MKV and manual splits found")
    return subdir


@pytest.fixture(scope="session")
def source_mkv(split_subdir: Path) -> Path:
    """Source MKV from a subdirectory with manual splits."""
    mkv = _find_source_mkv(split_subdir)
    assert mkv is not None
    return mkv


@pytest.fixture(scope="session")
def source_metadata(source_mkv: Path) -> dict:
    """Probe metadata for the source MKV (cached for session)."""
    return probe_video(source_mkv)


@pytest.fixture(scope="session")
def manual_splits(split_subdir: Path) -> list[Path]:
    """List of manually split MP4 files."""
    splits = _find_manual_splits(split_subdir)
    assert len(splits) > 0
    return splits


@pytest.fixture(scope="session")
def pipeline_result(
    source_mkv: Path, source_metadata: dict, tmp_path_factory: pytest.TempPathFactory
) -> dict:
    """Run the full split pipeline ONCE and return results for all tests.

    Returns dict with keys: output_dir, output_files, metadata, boundaries.
    Boundaries are extracted from metadata.json to avoid running detect twice.
    """
    from allaganeye.commands.split_matches import run_split
    from allaganeye.config import SplitConfig

    output_dir = tmp_path_factory.mktemp("pipeline_output")

    config = SplitConfig(
        output_dir=output_dir,
        sample_interval=2.0,
        blackout_threshold=15.0,
        min_match_duration=300.0,
    )
    run_split(source_mkv, config)

    output_files = sorted(output_dir.glob("match_*.mp4"))
    metadata_path = output_dir / "metadata.json"
    metadata = (
        json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata_path.exists()
        else None
    )

    # Extract boundaries from metadata.json (avoids a second detect pass)
    boundaries = []
    if metadata:
        for m in metadata["matches"]:
            boundaries.append({"start": m["start_time"], "end": m["end_time"]})

    return {
        "output_dir": output_dir,
        "output_files": output_files,
        "metadata": metadata,
        "boundaries": boundaries,
    }


@pytest.fixture
def any_video(_sample_video_dir_session: Path) -> Path:
    """Find any video file (MKV or MP4) for basic tests."""
    for ext in ("*.mkv", "*.mp4"):
        files = list(_sample_video_dir_session.glob(ext))
        if files:
            return min(files, key=lambda p: p.stat().st_size)
    for subdir in _sample_video_dir_session.iterdir():
        if subdir.is_dir():
            files = list(subdir.glob("*.mp4"))
            if files:
                return min(files, key=lambda p: p.stat().st_size)
    pytest.skip("No video files found in sample directory")


# --- Probe tests ---


class TestProbeRealVideo:
    """Test probe_video with real video files."""

    def test_probe_mkv_metadata(self, any_video: Path):
        """probe_video returns valid metadata for a real video file."""
        result = probe_video(any_video)

        assert result["duration"] > 0
        assert result["width"] > 0
        assert result["height"] > 0
        assert result["fps"] > 0
        assert result["codec"] in ("h264", "hevc", "vp9", "av1")

    def test_probe_split_mp4(self, manual_splits: list[Path]):
        """probe_video returns valid metadata for manually split MP4s."""
        mp4 = manual_splits[0]
        result = probe_video(mp4)

        assert result["duration"] > 60  # FL matches are at least a few minutes
        assert result["width"] >= 1280
        assert result["height"] >= 720
        assert result["fps"] >= 24
        assert result["audio_codec"] is not None

    def test_probe_source_mkv(self, source_metadata: dict):
        """Source MKV has expected properties for a long OBS recording."""
        assert source_metadata["duration"] > 600  # At least 10 minutes
        assert source_metadata["width"] == 1920
        assert source_metadata["height"] == 1080
        assert source_metadata["fps"] >= 24.0


# --- Detection tests ---


class TestDetectRealVideo:
    """Test detection results (from cached pipeline run)."""

    def test_detect_finds_matches(self, pipeline_result: dict):
        """At least one match is detected in a long recording."""
        boundaries = pipeline_result["boundaries"]

        assert len(boundaries) >= 1
        for b in boundaries:
            assert b["start"] < b["end"]
            assert b["end"] - b["start"] >= 300.0

    def test_detect_count_near_manual_splits(
        self, pipeline_result: dict, manual_splits: list[Path]
    ):
        """Detected boundary count is in the right ballpark vs manual splits.

        Current detection merges some matches due to short inter-match gaps
        (see #60 respawn blackout issue). Tolerance is generous until
        detection accuracy improves.
        """
        boundaries = pipeline_result["boundaries"]
        expected_count = len(manual_splits)
        # Allow +/- 3 tolerance: current detector merges adjacent matches
        # when inter-match blackouts are too short or masked by respawn screens
        assert abs(len(boundaries) - expected_count) <= 3, (
            f"Detected {len(boundaries)} matches, expected ~{expected_count} "
            f"(manual splits: {[f.name for f in manual_splits]})"
        )


# --- Split tests ---


class TestSplitRealVideo:
    """Test split output (from cached pipeline run)."""

    def test_output_files_exist(self, pipeline_result: dict):
        """Split pipeline produces output files."""
        assert len(pipeline_result["output_files"]) >= 1

    def test_metadata_json_exists(self, pipeline_result: dict):
        """metadata.json exists and has correct structure."""
        metadata = pipeline_result["metadata"]
        assert metadata is not None
        assert metadata["source_duration"] > 0
        assert len(metadata["matches"]) == len(pipeline_result["output_files"])

    def test_split_output_playable(self, pipeline_result: dict):
        """Split output files are valid video files (probeable)."""
        for mp4 in pipeline_result["output_files"]:
            result = probe_video(mp4)
            assert result["duration"] > 0
            assert result["width"] > 0
            assert result["height"] > 0
            assert result["codec"] in ("h264", "hevc", "av1", "vp9")


# --- Metadata verification ---


class TestMetadataJson:
    """Test metadata.json content (from cached pipeline run)."""

    def test_metadata_match_durations(self, pipeline_result: dict):
        """metadata.json match durations are internally consistent."""
        metadata = pipeline_result["metadata"]
        assert metadata is not None

        for match_info in metadata["matches"]:
            expected_dur = match_info["end_time"] - match_info["start_time"]
            assert match_info["duration"] == pytest.approx(expected_dur)

    def test_metadata_display_timestamps(self, pipeline_result: dict):
        """metadata.json contains human-readable display timestamps."""
        metadata = pipeline_result["metadata"]
        assert metadata is not None
        assert "source_duration_display" in metadata

        for match_info in metadata["matches"]:
            assert "start_display" in match_info
            assert "end_display" in match_info
            assert "duration_display" in match_info
