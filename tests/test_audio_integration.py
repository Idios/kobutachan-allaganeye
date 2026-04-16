"""Integration tests for allaganeye.audio -- exercises real video files.

Requires:
- ALLAGANEYE_SAMPLE_VIDEO_DIR pointing to a directory that contains the
  per-date subdirectories (20260116/, 20260118/, 20260119/) used elsewhere.
- ALLAGANEYE_AUDIO_TEST_VIDEO (optional) pointing to the 2026-04-08 21-14-05
  primary recording referenced in the bundled fanfare reference's metadata.
- ffmpeg/ffprobe in PATH.

Run with: pytest -m slow tests/test_audio_integration.py
"""

import os
from pathlib import Path

import pytest

import numpy as np

from allaganeye.audio.extract import extract_pcm
from allaganeye.audio.features import (
    LogMelConfig,
    load_features,
    load_features_multi,
    log_mel_spectrogram,
)
from allaganeye.audio.matcher import (
    find_match_peaks,
    sliding_cosine_similarity,
)
from allaganeye.audio.refs import get_reference_path

pytestmark = pytest.mark.slow


# Expected match-start timestamps (seconds) for 2026-04-08 21-14-05.mkv.
# Match 3 (the disputed false split at 34:49) is intentionally excluded.
_PRIMARY_EXPECTED_STARTS = [50, 1129, 2437, 5021, 6037, 7186, 8179, 9315]
_PRIMARY_REQUIRED_HITS = 8  # acceptance: >= 8/8 starts at sim >= 0.65

# Sample-dir recordings. ``expected_starts`` lists the match-start timestamps
# (seconds) that the engineer-1 prototype confirmed Fanfare-detectable during
# the horizontal validation reported in issue #271. The cumulative acceptance
# threshold (13) equals the sum of entries below and guards against regression
# on this known-detectable baseline.
# (subdir_name, mkv_name, expected_starts)
_SAMPLE_DIR_EXPECTATIONS: list[tuple[str, str, list[float]]] = [
    ("20260116", "2026-01-16 22-12-57.mkv", [2355.8, 3367.1, 5624.2]),
    ("20260118", "2026-01-18 22-15-18.mkv", [2976.2, 4200.2, 5499.0, 7231.8]),
    (
        "20260119",
        "2026-01-19 22-09-07.mkv",
        [1985.0, 3069.1, 3993.0, 5099.5, 7556.0, 8413.2],
    ),
]
# Cumulative acceptance (per #287): 13/20 starts across the 3 recordings.
_CUMULATIVE_REQUIRED_HITS = 13


def _detect_fanfare_hits(
    video: Path, ref_features, config: LogMelConfig, threshold: float = 0.65
):
    """Run the full pipeline once and return BgmHits above *threshold*."""
    pcm = extract_pcm(video, sample_rate=config.sample_rate)
    target = log_mel_spectrogram(pcm, config)
    sim = sliding_cosine_similarity(ref_features, target)
    return find_match_peaks(
        sim,
        threshold=threshold,
        min_gap_seconds=30.0,
        frames_per_second=config.frames_per_second,
    )


def _hits_within_offset(hits, expected_starts, *, lo_sec=0.0, hi_sec=120.0):
    """Count expected starts that have a hit within [lo, hi] seconds after them."""
    matched = 0
    for exp in expected_starts:
        if any(lo_sec <= h["timestamp"] - exp <= hi_sec for h in hits):
            matched += 1
    return matched


@pytest.fixture(scope="module")
def _fanfare_reference():
    features, config, _ = load_features(get_reference_path("fanfare"))
    return features, config


def test_primary_recording_fanfare_coverage(_fanfare_reference):
    """Bundled fanfare reference detects >= 8/8 starts in the source recording."""
    env_path = os.environ.get("ALLAGANEYE_AUDIO_TEST_VIDEO")
    if not env_path:
        pytest.skip("ALLAGANEYE_AUDIO_TEST_VIDEO not set")
    video = Path(env_path)
    if not video.exists():
        pytest.skip(f"Primary test video not found: {video}")

    ref_features, config = _fanfare_reference
    hits = _detect_fanfare_hits(video, ref_features, config, threshold=0.65)
    matched = _hits_within_offset(hits, _PRIMARY_EXPECTED_STARTS)
    assert matched >= _PRIMARY_REQUIRED_HITS, (
        f"Expected >= {_PRIMARY_REQUIRED_HITS} matched starts, got {matched}. "
        f"Hits: {[(h['timestamp'], h['similarity']) for h in hits]}"
    )


def test_sample_recordings_cumulative_coverage(
    _fanfare_reference, sample_video_dir: Path
):
    """Matched starts across the 3 sample recordings reach the baseline >= 13."""
    ref_features, config = _fanfare_reference

    total_matched = 0
    per_video: dict[str, tuple[int, int]] = {}
    for subdir_name, mkv_name, expected_starts in _SAMPLE_DIR_EXPECTATIONS:
        video = sample_video_dir / subdir_name / mkv_name
        if not video.exists():
            pytest.skip(f"Sample recording missing: {video}")
        hits = _detect_fanfare_hits(video, ref_features, config, threshold=0.65)
        matched = _hits_within_offset(hits, expected_starts)
        total_matched += matched
        per_video[subdir_name] = (matched, len(expected_starts))

    assert total_matched >= _CUMULATIVE_REQUIRED_HITS, (
        f"Expected >= {_CUMULATIVE_REQUIRED_HITS} matched starts, "
        f"got {total_matched} (per video matched/expected: {per_video})"
    )


def test_bundled_fanfare_reference_loads():
    """The bundled fanfare reference file is valid and matches LogMelConfig defaults."""
    features, config, metadata = load_features(get_reference_path("fanfare"))
    default = LogMelConfig()
    assert config.sample_rate == default.sample_rate
    assert config.n_mels == default.n_mels
    assert features.shape[0] == config.n_mels
    # Expected ~5 seconds of frames at default settings (~213 frames)
    assert 200 <= features.shape[1] <= 250
    assert "source_filename" in metadata


# War Room reference acceptance (issue #289).
#
# The bundle contains two references (OR-combined): the canonical ogg
# 1.5s window (covers 2026-04-08 era) and a 3s window from 20260116 at
# t=6520s (covers the 20260116/18/19-era rendition of the BGM).  At scan
# time we take per-frame max across both refs, matching how
# scan_fanfare_hits now combines multi-ref bundles.
_WAR_ROOM_ACCEPT_WINDOW = 240.0
_WAR_ROOM_COVERAGE_MIN = 0.50
_WAR_ROOM_THRESHOLD = 0.65

# Primary (2026-04-08) must retain sim_max at the lower edge of the
# issue-stated baseline band [0.78, 0.88] -- "no regression".  The original
# ogg@0_1.5 reference actually produces sim_max ~= 0.89 on 2026-04-08 (above
# the upper edge of the stated band), so we interpret "maintain" as a
# lower-bound guarantee: sim_max must stay >= 0.78.  Going higher than 0.88
# is not a regression.
_WAR_ROOM_PRIMARY_SIM_MIN = 0.78

# Match ends per recording.  Sourced from user-confirmed blackout types
# (see issue #286 comment for 20260116) where available; for recordings
# without user confirmation, we use the Fanfare-derived match-start times
# as proxy (a Fanfare start N implies the previous match ended just before N).
_WAR_ROOM_SAMPLE_EXPECTATIONS: list[tuple[str, str, list[float]]] = [
    (
        "20260116",
        "2026-01-16 22-12-57.mkv",
        # 20260116 match ends from detector output, corrected per #286
        # user confirmation (match 6 real end = 6541s, not 6469s).
        [1054.4, 2355.8, 3367.2, 4352.0, 5622.9, 6541.1],
    ),
    (
        "20260118",
        "2026-01-18 22-15-18.mkv",
        # 20260118 real match ends (user-confirmed in #286 follow-up):
        # 1:05:25 / 1:27:33 / 1:47:44 -> 3925, 5253, 6464.  The remaining
        # entries in the detector output were knockdown blackouts and are
        # excluded to avoid testing against false boundaries.
        [3925.0, 5253.3, 6464.0],
    ),
    (
        "20260119",
        "2026-01-19 22-09-07.mkv",
        # 20260119 match ends (user-confirmed in #286 follow-up):
        # 0:14:26 / 1:03:59 / 1:40:35 / 2:03:03 -> 866, 3839, 6035, 7383.
        [866.0, 3839.0, 6035.0, 7383.0],
    ),
]


def _detect_multi_ref_hits(
    video: Path, refs: list, config: LogMelConfig, threshold: float = 0.65
):
    """Scan with multi-ref OR logic (max per-frame similarity), same as scan.py."""
    pcm = extract_pcm(video, sample_rate=config.sample_rate)
    target = log_mel_spectrogram(pcm, config)
    sims = [sliding_cosine_similarity(f, target) for f in refs]
    min_len = min(s.size for s in sims)
    combined = np.maximum.reduce([s[:min_len] for s in sims])
    return (
        combined,
        find_match_peaks(
            combined,
            threshold=threshold,
            min_gap_seconds=30.0,
            frames_per_second=config.frames_per_second,
        ),
    )


def _count_covered_ends(hits, match_ends: list[float]) -> int:
    """How many *match_ends* have at least one hit within the accept window."""
    covered = 0
    for end in match_ends:
        if any(
            end - 60.0 <= h["timestamp"] <= end + _WAR_ROOM_ACCEPT_WINDOW for h in hits
        ):
            covered += 1
    return covered


@pytest.fixture(scope="module")
def _war_room_reference():
    refs, config, _ = load_features_multi(get_reference_path("war_room"))
    return refs, config


def test_bundled_war_room_reference_loads():
    """The bundled war_room reference file is multi-window (v3) and config-valid."""
    refs, config, metadata = load_features_multi(get_reference_path("war_room"))
    default = LogMelConfig()
    assert config.sample_rate == default.sample_rate
    assert config.n_mels == default.n_mels
    # Expect 2 refs (ogg + self-extracted 20260116) per issue #289 design.
    assert len(refs) == 2
    for r in refs:
        assert r.shape[0] == config.n_mels
        assert r.shape[1] > 0
    assert "windows" in metadata
    assert metadata.get("n_windows") == 2


def test_war_room_sample_recordings_coverage(
    _war_room_reference, sample_video_dir: Path
):
    """War Room reference meets >=50% match-end coverage on all 3 sample recordings."""
    refs, config = _war_room_reference

    per_video: dict[str, tuple[int, int]] = {}
    failures: list[str] = []
    for subdir_name, mkv_name, match_ends in _WAR_ROOM_SAMPLE_EXPECTATIONS:
        video = sample_video_dir / subdir_name / mkv_name
        if not video.exists():
            pytest.skip(f"Sample recording missing: {video}")
        _, hits = _detect_multi_ref_hits(
            video, refs, config, threshold=_WAR_ROOM_THRESHOLD
        )
        covered = _count_covered_ends(hits, match_ends)
        total = len(match_ends)
        per_video[subdir_name] = (covered, total)
        if covered / total < _WAR_ROOM_COVERAGE_MIN:
            failures.append(
                f"{subdir_name}: {covered}/{total} "
                f"({covered / total * 100:.0f}%) < {_WAR_ROOM_COVERAGE_MIN * 100:.0f}%"
            )

    assert not failures, (
        f"War Room coverage below threshold: {failures} "
        f"(per video covered/total: {per_video})"
    )


def test_war_room_primary_sim_maintained(_war_room_reference):
    """Primary (2026-04-08) combined sim_max stays >= 0.78 -- no regression."""
    env_path = os.environ.get("ALLAGANEYE_AUDIO_TEST_VIDEO")
    if not env_path:
        pytest.skip("ALLAGANEYE_AUDIO_TEST_VIDEO not set")
    video = Path(env_path)
    if not video.exists():
        pytest.skip(f"Primary test video not found: {video}")

    refs, config = _war_room_reference
    combined, _ = _detect_multi_ref_hits(
        video, refs, config, threshold=_WAR_ROOM_THRESHOLD
    )
    sim_max = float(combined.max())
    assert sim_max >= _WAR_ROOM_PRIMARY_SIM_MIN, (
        f"Primary sim_max {sim_max:.3f} < {_WAR_ROOM_PRIMARY_SIM_MIN}. "
        "#289 acceptance requires 2026-04-08 sim to not regress below 0.78."
    )
