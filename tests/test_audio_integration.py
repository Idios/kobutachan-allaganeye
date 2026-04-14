"""Integration tests for allaganeye.audio — exercises real video files.

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

from allaganeye.audio.extract import extract_pcm
from allaganeye.audio.features import LogMelConfig, log_mel_spectrogram, load_features
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
