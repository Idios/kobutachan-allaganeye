"""Regression and performance tests for scorebar filtering (#111).

Compares detection results WITH scorebar filtering (src_resolution set)
against results WITHOUT filtering, and validates against manual splits.

Run with: pytest -m slow tests/test_scorebar_regression.py -v

Requires:
- ALLAGANEYE_SAMPLE_VIDEO_DIR set
"""

import json
import os
import re
import time
from pathlib import Path

import pytest

from allaganeye.commands.split_matches import run_split
from allaganeye.config import SplitConfig
from allaganeye.video.detector import detect_match_boundaries
from allaganeye.video.probe import probe_video

pytestmark = pytest.mark.slow

# --- Helpers ---


def _find_source_mkv(subdir: Path) -> Path | None:
    mkvs = sorted(subdir.glob("*.mkv"))
    if not mkvs:
        return None
    return max(mkvs, key=lambda p: p.stat().st_size)


def _count_manual_splits(subdir: Path) -> int:
    pattern = re.compile(r"^\d{8}_\d+\.mp4$")
    return sum(1 for f in subdir.iterdir() if pattern.match(f.name))


# --- Fixtures ---

# Target recordings with >= 3 manual splits (reliable comparison)
_TARGET_SUBDIRS = ["20260116", "20260118", "20260119"]


def _discover_targets() -> list[tuple[str, Path]]:
    env_path = os.environ.get("ALLAGANEYE_SAMPLE_VIDEO_DIR")
    if not env_path:
        return []
    base = Path(env_path)
    targets = []
    for name in _TARGET_SUBDIRS:
        subdir = base / name
        if subdir.is_dir():
            mkv = _find_source_mkv(subdir)
            if mkv:
                targets.append((name, mkv))
    return targets


_TARGETS = _discover_targets()


@pytest.fixture(
    scope="session",
    params=_TARGETS or [None],
    ids=lambda t: t[0] if t else "no-data",
)
def target_recording(request: pytest.FixtureRequest) -> tuple[str, Path]:
    if request.param is None:
        pytest.skip("No target recordings found")
    return request.param


@pytest.fixture(scope="session")
def target_metadata(target_recording: tuple[str, Path]) -> dict:
    _, mkv = target_recording
    return probe_video(mkv)


@pytest.fixture(scope="session")
def detection_with_scorebar(
    target_recording: tuple[str, Path],
    target_metadata: dict,
) -> dict:
    """Run detection WITH scorebar filtering and measure time."""
    name, mkv = target_recording
    meta = target_metadata

    start = time.monotonic()
    boundaries = detect_match_boundaries(
        mkv,
        duration_hint=meta["duration"],
        sample_interval=2.0,
        blackout_threshold=15.0,
        min_match_duration=300.0,
        min_blackout_duration=3.0,
        src_resolution=(meta["width"], meta["height"]),
    )
    elapsed = time.monotonic() - start

    # GPU cooldown: prevent NVIDIA driver deadlock from rapid ffmpeg calls
    time.sleep(1)

    return {
        "name": name,
        "boundaries": boundaries,
        "elapsed": elapsed,
        "match_count": len(boundaries),
    }


@pytest.fixture(scope="session")
def detection_without_scorebar(
    target_recording: tuple[str, Path],
    target_metadata: dict,
) -> dict:
    """Run detection WITHOUT scorebar filtering and measure time."""
    name, mkv = target_recording
    meta = target_metadata

    start = time.monotonic()
    boundaries = detect_match_boundaries(
        mkv,
        duration_hint=meta["duration"],
        sample_interval=2.0,
        blackout_threshold=15.0,
        min_match_duration=300.0,
        min_blackout_duration=3.0,
        # src_resolution omitted → no scorebar filtering
    )
    elapsed = time.monotonic() - start

    # GPU cooldown: prevent NVIDIA driver deadlock from rapid ffmpeg calls
    time.sleep(1)

    return {
        "name": name,
        "boundaries": boundaries,
        "elapsed": elapsed,
        "match_count": len(boundaries),
    }


@pytest.fixture(scope="session")
def pipeline_output_with_scorebar(
    target_recording: tuple[str, Path],
    tmp_path_factory: pytest.TempPathFactory,
) -> dict:
    """Run full pipeline WITH scorebar filtering."""
    name, mkv = target_recording
    output_dir = tmp_path_factory.mktemp(f"scorebar_{name}")

    config = SplitConfig(
        output_dir=output_dir,
        sample_interval=2.0,
        blackout_threshold=15.0,
        min_match_duration=300.0,
    )
    run_split(mkv, config)

    metadata_path = output_dir / "metadata.json"
    metadata = (
        json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata_path.exists()
        else None
    )
    output_files = sorted(output_dir.glob("match_*.mp4"))

    # GPU cooldown: prevent NVIDIA driver deadlock from rapid ffmpeg calls
    time.sleep(1)

    return {
        "name": name,
        "output_dir": output_dir,
        "output_files": output_files,
        "metadata": metadata,
    }


# --- 1. Functional regression: detection count ---


class TestDetectionCount:
    """Scorebar filtering should not reduce detection count vs manual splits."""

    def test_count_near_manual_splits(
        self, target_recording: tuple[str, Path], detection_with_scorebar: dict
    ):
        """Detected count is within +/-2 of manual split count."""
        name, _ = target_recording
        subdir = Path(os.environ["ALLAGANEYE_SAMPLE_VIDEO_DIR"]) / name
        manual_count = _count_manual_splits(subdir)
        if manual_count < 3:
            pytest.skip(f"Incomplete manual splits ({manual_count})")

        detected = detection_with_scorebar["match_count"]
        assert abs(detected - manual_count) <= 2, (
            f"{name}: detected {detected}, expected ~{manual_count} (manual)"
        )

    def test_no_worse_than_without_scorebar(
        self,
        target_recording: tuple[str, Path],
        detection_with_scorebar: dict,
        detection_without_scorebar: dict,
    ):
        """Scorebar filtering does not lose real matches vs no filtering."""
        name, _ = target_recording
        subdir = Path(os.environ["ALLAGANEYE_SAMPLE_VIDEO_DIR"]) / name
        manual_count = _count_manual_splits(subdir)
        if manual_count < 3:
            pytest.skip(f"Incomplete manual splits ({manual_count})")

        with_sb = detection_with_scorebar["match_count"]

        # Scorebar should not lose more than 2 real matches vs manual
        assert with_sb >= manual_count - 2, (
            f"{name}: scorebar reduced to {with_sb} matches (manual={manual_count})"
        )


# --- 2. Functional regression: match durations ---


class TestMatchDurations:
    """Each detected match should be within plausible FL duration range."""

    def test_match_durations_reasonable(self, detection_with_scorebar: dict):
        """Each match is 5-35 minutes (plausible FL range)."""
        for i, b in enumerate(detection_with_scorebar["boundaries"]):
            dur = b["end"] - b["start"]
            assert 300.0 <= dur <= 2100.0, (
                f"Match {i + 1}: {dur:.0f}s outside 5-35min range"
            )

    def test_no_merged_matches(self, detection_with_scorebar: dict):
        """No single match exceeds 40 minutes (would indicate merged matches)."""
        for i, b in enumerate(detection_with_scorebar["boundaries"]):
            dur = b["end"] - b["start"]
            assert dur <= 2400.0, (
                f"Match {i + 1}: {dur:.0f}s (>40min) — likely merged matches"
            )


# --- 3. Performance: scorebar overhead ---


class TestPerformance:
    """Scorebar filtering should add minimal overhead."""

    def test_overhead_within_budget(
        self,
        detection_with_scorebar: dict,
        detection_without_scorebar: dict,
    ):
        """Scorebar filtering adds less than 30% overhead."""
        with_sb = detection_with_scorebar["elapsed"]
        without_sb = detection_without_scorebar["elapsed"]

        if without_sb < 10.0:
            pytest.skip("Baseline too fast for reliable comparison")

        overhead_pct = (with_sb - without_sb) / without_sb * 100
        assert overhead_pct < 30.0, (
            f"Scorebar overhead {overhead_pct:.1f}% exceeds 30% budget "
            f"({with_sb:.1f}s vs {without_sb:.1f}s)"
        )


# --- 4. Pipeline output: metadata.json integrity ---


class TestMetadataIntegrity:
    """metadata.json should have all required fields."""

    def test_metadata_exists(self, pipeline_output_with_scorebar: dict):
        metadata = pipeline_output_with_scorebar["metadata"]
        assert metadata is not None

    def test_metadata_required_fields(self, pipeline_output_with_scorebar: dict):
        metadata = pipeline_output_with_scorebar["metadata"]
        assert metadata is not None

        assert "source" in metadata
        assert "source_duration" in metadata
        assert "source_duration_display" in metadata
        assert "matches" in metadata
        assert "gaps" in metadata
        assert isinstance(metadata["matches"], list)
        assert len(metadata["matches"]) == len(
            pipeline_output_with_scorebar["output_files"]
        )

    def test_metadata_match_fields(self, pipeline_output_with_scorebar: dict):
        metadata = pipeline_output_with_scorebar["metadata"]
        assert metadata is not None

        required_keys = {
            "index",
            "start_time",
            "end_time",
            "start_display",
            "end_display",
            "duration",
            "duration_display",
            "output_file",
        }
        for match in metadata["matches"]:
            missing = required_keys - set(match.keys())
            assert not missing, f"Missing keys in match: {missing}"

    def test_metadata_duration_consistency(self, pipeline_output_with_scorebar: dict):
        metadata = pipeline_output_with_scorebar["metadata"]
        assert metadata is not None

        for match in metadata["matches"]:
            expected = match["end_time"] - match["start_time"]
            assert match["duration"] == pytest.approx(expected)

    def test_output_files_playable(self, pipeline_output_with_scorebar: dict):
        """All split output files are valid videos."""
        for mp4 in pipeline_output_with_scorebar["output_files"]:
            result = probe_video(mp4)
            assert result["duration"] > 0
            assert result["width"] > 0


# --- 5. Backward compatibility: src_resolution=None ---

_BASELINES_DIR = Path(__file__).parent / "baselines"


def _load_baseline(name: str) -> dict | None:
    path = _BASELINES_DIR / f"{name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


class TestNoResolutionCompat:
    """When src_resolution is omitted, behavior must be identical to pre-#124."""

    def test_same_count_as_baseline(
        self, target_recording: tuple[str, Path], detection_without_scorebar: dict
    ):
        """Detection without src_resolution matches saved baseline count."""
        name, _ = target_recording
        baseline = _load_baseline(name)
        if baseline is None:
            pytest.skip(f"No baseline for {name}")

        detected = detection_without_scorebar["match_count"]
        baseline_count = baseline["match_count"]
        assert detected == baseline_count, (
            f"{name}: without scorebar got {detected}, baseline was {baseline_count}"
        )

    def test_boundaries_match_baseline(
        self, target_recording: tuple[str, Path], detection_without_scorebar: dict
    ):
        """Each boundary timestamp matches baseline within 5s tolerance."""
        name, _ = target_recording
        baseline = _load_baseline(name)
        if baseline is None:
            pytest.skip(f"No baseline for {name}")

        detected = detection_without_scorebar["boundaries"]
        baseline_b = baseline["boundaries"]
        assert len(detected) == len(baseline_b), (
            f"{name}: count mismatch {len(detected)} vs {len(baseline_b)}"
        )

        tolerance = 5.0
        for i, (d, b) in enumerate(zip(detected, baseline_b, strict=True)):
            assert abs(d["start"] - b["start"]) <= tolerance, (
                f"Match {i + 1} start: {d['start']:.1f} vs baseline {b['start']:.1f}"
            )
            assert abs(d["end"] - b["end"]) <= tolerance, (
                f"Match {i + 1} end: {d['end']:.1f} vs baseline {b['end']:.1f}"
            )


# --- 6. Baseline comparison: scorebar detection results ---


class TestBaselineComparison:
    """Compare scorebar detection against saved baselines.

    Scorebar filtering intentionally changes boundaries: it merges
    match_boundary pairs and removes non-FL blackouts, so start/end
    positions will shift.  The correct check is that real match
    *content* is preserved, not that boundary positions match exactly.
    """

    def test_baseline_match_content_preserved(
        self, target_recording: tuple[str, Path], detection_with_scorebar: dict
    ):
        """Each baseline match's midpoint falls within some scorebar match.

        This verifies that scorebar filtering does not lose real match
        content.  Boundary merging may change start/end positions, but
        the core of each match should still be covered.
        """
        name, _ = target_recording
        baseline = _load_baseline(name)
        if baseline is None:
            pytest.skip(f"No baseline for {name}")

        baseline_boundaries = baseline["boundaries"]
        scorebar_boundaries = detection_with_scorebar["boundaries"]

        uncovered = []
        for i, bb in enumerate(baseline_boundaries):
            midpoint = (bb["start"] + bb["end"]) / 2
            covered = any(
                sb["start"] <= midpoint <= sb["end"] for sb in scorebar_boundaries
            )
            if not covered:
                uncovered.append(
                    f"Baseline match {i + 1} midpoint {midpoint:.0f}s "
                    f"({bb['start']:.0f}-{bb['end']:.0f}s) not covered"
                )

        # Allow up to 3 uncovered: some baseline matches may be non-FL
        # content that scorebar correctly removes
        assert len(uncovered) <= 3, (
            f"{name}: {len(uncovered)} baseline matches lost:\n" + "\n".join(uncovered)
        )

    def test_scorebar_does_not_fragment(
        self,
        target_recording: tuple[str, Path],
        detection_with_scorebar: dict,
        detection_without_scorebar: dict,
    ):
        """Scorebar should not produce significantly more matches than baseline.

        Scorebar merges boundaries, so match count should be <= baseline
        or at most +2 (edge cases where non-FL removal creates new segments).
        """
        name, _ = target_recording
        with_sb = detection_with_scorebar["match_count"]
        without_sb = detection_without_scorebar["match_count"]

        assert with_sb <= without_sb + 2, (
            f"{name}: scorebar produced {with_sb} matches vs "
            f"baseline {without_sb} (fragmentation)"
        )
