"""Integration tests using real video files.

All tests require:
- ALLAGANEYE_SAMPLE_VIDEO_DIR environment variable set to the sample video directory
- ffmpeg/ffprobe installed and in PATH

Run with: pytest -m slow

Design: The ``split_subdir`` fixture is parameterized over every
subdirectory that contains both a source MKV and manual splits.
The full pipeline (probe -> detect -> split) runs once per subdirectory
via the ``pipeline_result`` fixture.  Individual tests verify different
aspects of that single run to avoid repeated detection passes.
"""

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from allaganeye.ffmpeg_path import find_ffmpeg
from allaganeye.video.probe import ProbeResult, probe_video

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


def _discover_split_subdirs() -> list[Path]:
    """Discover all subdirectories with source MKV and manual splits.

    Called at import time so that pytest can parameterize fixtures.
    Returns an empty list when the environment variable is unset.
    """
    env_path = os.environ.get("ALLAGANEYE_SAMPLE_VIDEO_DIR")
    if not env_path:
        return []
    base = Path(env_path)
    if not base.is_dir():
        return []
    return [
        subdir
        for subdir in sorted(base.iterdir())
        if subdir.is_dir() and _find_source_mkv(subdir) and _find_manual_splits(subdir)
    ]


_SPLIT_SUBDIRS = _discover_split_subdirs()


def _gpu_available() -> bool:
    """Check if GPU decode is available by running a minimal ffmpeg hwaccel probe."""
    try:
        result = subprocess.run(
            [find_ffmpeg(), "-hwaccels"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        accels = result.stdout.lower()
        return any(
            a in accels for a in ("cuda", "d3d11va", "qsv", "vulkan", "videotoolbox")
        )
    except Exception:
        return False


# --- Fixtures ---


@pytest.fixture(scope="session")
def _sample_video_dir_session() -> Path:
    """Session-scoped sample_video_dir (avoids per-test skip)."""
    env_path = os.environ.get("ALLAGANEYE_SAMPLE_VIDEO_DIR")
    if not env_path:
        pytest.skip("ALLAGANEYE_SAMPLE_VIDEO_DIR not set")
    path = Path(env_path)
    if not path.is_dir():
        pytest.skip(f"Sample video directory not found: {path}")
    return path


@pytest.fixture(
    scope="session",
    params=_SPLIT_SUBDIRS or [None],
    ids=lambda p: p.name if p else "no-data",
)
def split_subdir(request: pytest.FixtureRequest) -> Path:
    """Parameterized over every subdirectory with source MKV + manual splits."""
    if request.param is None:
        pytest.skip("No subdirectory with source MKV and manual splits found")
    return request.param


@pytest.fixture(scope="session")
def source_mkv(split_subdir: Path) -> Path:
    """Source MKV from a subdirectory with manual splits."""
    mkv = _find_source_mkv(split_subdir)
    assert mkv is not None
    return mkv


@pytest.fixture(scope="session")
def source_metadata(source_mkv: Path) -> ProbeResult:
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
    source_mkv: Path,
    source_metadata: dict,
    tmp_path_factory: pytest.TempPathFactory,
    _cache_context: dict,
) -> dict:
    """Run the full split pipeline ONCE and return results for all tests.

    Returns dict with keys: output_dir, output_files, metadata, boundaries.
    On cache hit, skips detection and runs only the split step.
    """
    from allaganeye.commands.split_matches import (
        _find_gaps,
        _split_and_write_metadata,
        run_split,
    )
    from allaganeye.config import SplitConfig
    from allaganeye.video.probe import probe_video
    from tests.detection_cache import read_fixture_cache, write_fixture_cache

    detection_params = {
        "sample_interval": 2.0,
        "blackout_threshold": 15.0,
        "min_match_duration": 300.0,
        "min_blackout_duration": 3.0,
    }

    cache_dir = _cache_context["cache_dir"]
    source_hashes = _cache_context["source_hashes"]
    output_dir = tmp_path_factory.mktemp("pipeline_output")

    cached = None
    if not _cache_context["no_cache"]:
        cached = read_fixture_cache(
            cache_dir,
            source_mkv,
            "pipeline_result",
            detection_params,
            source_hashes,
        )

    if cached is not None:
        name = source_mkv.parent.name
        print(f"\n[cache] HIT pipeline_result for {name}")
        boundaries = cached["boundaries"]
        # Run split only (skip detection)
        meta = probe_video(source_mkv)
        config = SplitConfig(
            output_dir=output_dir,
            sample_interval=2.0,
            blackout_threshold=15.0,
            min_match_duration=300.0,
        )
        gaps = _find_gaps(boundaries, meta["duration"], min_gap=300.0)
        _split_and_write_metadata(
            source_mkv,
            boundaries,
            gaps,
            meta,
            config,
            effective_interval=config.sample_interval,
            detected_at="1970-01-01T00:00:00Z",
            system_info={
                "gpu_vendors_available": [],
                "gpu_vendor_used": None,
                "vendor_preference": ["nvidia", "amd", "intel"],
            },
        )
    else:
        name = source_mkv.parent.name
        print(f"\n[cache] MISS pipeline_result for {name}")
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

    # Extract boundaries from metadata.json
    boundaries = []
    if metadata:
        for m in metadata["matches"]:
            boundaries.append({"start": m["start_time"], "end": m["end_time"]})

    # Write cache on miss
    if cached is None and boundaries:
        write_fixture_cache(
            cache_dir,
            source_mkv,
            "pipeline_result",
            detection_params,
            source_hashes,
            result={"boundaries": boundaries},
        )

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


@pytest.mark.slow_probe
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


@pytest.mark.slow_detect
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

        Transition expansion (#71/#75) and 2-pass refinement (#77/#79)
        improved detection to 7/7.  Tolerance +-2 allows for edge cases
        in other recordings.

        Skipped when manual splits < 3 (likely incomplete hand-splitting).
        """
        if len(manual_splits) < 3:
            pytest.skip(
                f"Incomplete manual splits ({len(manual_splits)}): "
                "comparison unreliable"
            )
        boundaries = pipeline_result["boundaries"]
        expected_count = len(manual_splits)
        # Allow +/- 2 tolerance
        assert abs(len(boundaries) - expected_count) <= 2, (
            f"Detected {len(boundaries)} matches, expected ~{expected_count} "
            f"(manual splits: {[f.name for f in manual_splits]})"
        )

    def test_detect_total_duration_accuracy(
        self, pipeline_result: dict, manual_splits: list[Path]
    ):
        """Total detected match duration is close to total manual duration.

        Individual match boundaries may differ from manual splits (the
        detector and human choose different cut points), so per-match
        comparison is unreliable.  Total duration comparison validates
        that the detector captures roughly the same amount of content.

        Skipped when manual splits < 3 (likely incomplete hand-splitting).
        """
        if len(manual_splits) < 3:
            pytest.skip(
                f"Incomplete manual splits ({len(manual_splits)}): "
                "comparison unreliable"
            )
        boundaries = pipeline_result["boundaries"]
        if not boundaries:
            pytest.skip("No boundaries detected")

        detected_total = sum(b["end"] - b["start"] for b in boundaries)

        manual_total = 0.0
        for mp4 in manual_splits:
            meta = probe_video(mp4)
            manual_total += meta["duration"]

        # Allow 25% tolerance on total duration
        ratio = detected_total / manual_total
        assert 0.75 <= ratio <= 1.25, (
            f"Total duration ratio {ratio:.2f}: "
            f"detected {detected_total:.0f}s vs manual {manual_total:.0f}s"
        )

    def test_detect_match_durations_reasonable(
        self, pipeline_result: dict, manual_splits: list[Path]
    ):
        """Each detected match duration is within a plausible FL match range.

        FL matches typically last 8-20 minutes but overtime can push
        to ~26 minutes.  Upper bound set to 30 minutes.
        """
        boundaries = pipeline_result["boundaries"]

        for i, b in enumerate(boundaries):
            dur = b["end"] - b["start"]
            assert 300.0 <= dur <= 1800.0, (
                f"Match {i + 1}: {dur:.0f}s is outside plausible range "
                f"(5-30 min for FL matches)"
            )


# --- Split tests ---


@pytest.mark.slow_pipeline
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


@pytest.mark.slow_pipeline
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


# --- GPU/CPU consistency fixtures ---


@pytest.fixture(scope="session")
def gpu_cpu_results(
    source_mkv: Path, source_metadata: dict, _cache_context: dict
) -> dict:
    """Run detection in both CPU and GPU modes (cached for session)."""
    if not _gpu_available():
        pytest.skip("No GPU available")

    from allaganeye.video.detector import detect_match_boundaries
    from tests.detection_cache import read_fixture_cache, write_fixture_cache

    detection_params = {
        "sample_interval": 2.0,
        "blackout_threshold": 15.0,
        "min_match_duration": 300.0,
        "min_blackout_duration": 3.0,
        "src_resolution": [source_metadata["width"], source_metadata["height"]],
    }

    cache_dir = _cache_context["cache_dir"]
    source_hashes = _cache_context["source_hashes"]

    if not _cache_context["no_cache"]:
        cached = read_fixture_cache(
            cache_dir,
            source_mkv,
            "gpu_cpu_results",
            detection_params,
            source_hashes,
        )
        if cached is not None:
            name = source_mkv.parent.name
            print(f"\n[cache] HIT gpu_cpu_results for {name}")
            return {"cpu": cached["cpu"], "gpu": cached["gpu"]}
        name = source_mkv.parent.name
        print(f"\n[cache] MISS gpu_cpu_results for {name}")

    cpu = detect_match_boundaries(
        source_mkv,
        use_gpu=False,
        duration_hint=source_metadata["duration"],
        sample_interval=2.0,
        blackout_threshold=15.0,
        min_match_duration=300.0,
        min_blackout_duration=3.0,
        src_resolution=(source_metadata["width"], source_metadata["height"]),
    )
    gpu = detect_match_boundaries(
        source_mkv,
        use_gpu=True,
        duration_hint=source_metadata["duration"],
        sample_interval=2.0,
        blackout_threshold=15.0,
        min_match_duration=300.0,
        min_blackout_duration=3.0,
        src_resolution=(source_metadata["width"], source_metadata["height"]),
    )

    write_fixture_cache(
        cache_dir,
        source_mkv,
        "gpu_cpu_results",
        detection_params,
        source_hashes,
        result={"cpu": cpu, "gpu": gpu},
    )

    return {"cpu": cpu, "gpu": gpu}


# --- GPU/CPU consistency tests ---


@pytest.mark.slow_gpu
class TestGpuCpuConsistency:
    """Verify GPU and CPU detection produce consistent results."""

    def test_gpu_cpu_boundary_count_matches(self, gpu_cpu_results: dict):
        """GPU and CPU modes detect similar number of matches (+-1).

        Exact match is not guaranteed due to ffmpeg seek non-determinism:
        per-frame ``-ss`` (CPU) and chunked ``fps`` filter (GPU) may
        decode different frames at the same timestamp, causing +-1
        boundary difference at threshold edges.  (#214)
        """
        if not _gpu_available():
            pytest.skip("No GPU hardware acceleration available")
        cpu = gpu_cpu_results["cpu"]
        gpu = gpu_cpu_results["gpu"]

        assert abs(len(cpu) - len(gpu)) <= 1, (
            f"CPU detected {len(cpu)} matches, GPU detected {len(gpu)} "
            f"(diff {abs(len(cpu) - len(gpu))} > 1)"
        )

    def test_gpu_cpu_boundaries_close(self, gpu_cpu_results: dict):
        """GPU and CPU boundary timestamps are within tolerance."""
        if not _gpu_available():
            pytest.skip("No GPU hardware acceleration available")
        cpu = gpu_cpu_results["cpu"]
        gpu = gpu_cpu_results["gpu"]

        if abs(len(cpu) - len(gpu)) > 1:
            pytest.skip(
                "Boundary count mismatch > 1 -- see test_gpu_cpu_boundary_count_matches"
            )
        if len(cpu) != len(gpu):
            pytest.skip(
                "Boundary count differs by 1 -- timestamp comparison not meaningful"
            )

        tolerance = 10.0  # seconds
        for i, (c, g) in enumerate(zip(cpu, gpu, strict=True)):
            assert abs(c["start"] - g["start"]) <= tolerance, (
                f"Match {i + 1} start: CPU={c['start']:.1f}s, GPU={g['start']:.1f}s "
                f"(diff={abs(c['start'] - g['start']):.1f}s > {tolerance}s)"
            )
            assert abs(c["end"] - g["end"]) <= tolerance, (
                f"Match {i + 1} end: CPU={c['end']:.1f}s, GPU={g['end']:.1f}s "
                f"(diff={abs(c['end'] - g['end']):.1f}s > {tolerance}s)"
            )

    def test_gpu_cpu_boundaries_strict_parity(self, gpu_cpu_results: dict):
        """CPU/GPU boundary timestamps within +-5s (#392).

        Tighter contract than ``test_gpu_cpu_boundaries_close`` (+-10s):
        verifies the #392 fix (grid-aligned GPU chunk starts) keeps the
        two modes within 5s per boundary.  Regression from this level
        means GPU has drifted off the sample grid again.
        """
        if not _gpu_available():
            pytest.skip("No GPU hardware acceleration available")
        cpu = gpu_cpu_results["cpu"]
        gpu = gpu_cpu_results["gpu"]

        # #392: GPU should now match CPU match count exactly, not +-1.
        assert len(cpu) == len(gpu), (
            f"match count differs: CPU={len(cpu)}, GPU={len(gpu)}. "
            "Regression of #392 -- GPU chunk_start no longer aligned to "
            "sample grid, causing different blackout region boundaries."
        )

        tolerance = 5.0  # seconds
        for i, (c, g) in enumerate(zip(cpu, gpu, strict=True)):
            assert abs(c["start"] - g["start"]) <= tolerance, (
                f"Match {i + 1} start drift: CPU={c['start']:.1f}, "
                f"GPU={g['start']:.1f}, diff={abs(c['start'] - g['start']):.2f}s "
                f"(>{tolerance}s). #392 regression."
            )
            assert abs(c["end"] - g["end"]) <= tolerance, (
                f"Match {i + 1} end drift: CPU={c['end']:.1f}, "
                f"GPU={g['end']:.1f}, diff={abs(c['end'] - g['end']):.2f}s "
                f"(>{tolerance}s). #392 regression."
            )
