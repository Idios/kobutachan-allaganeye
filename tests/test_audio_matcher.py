"""Tests for allaganeye.audio.matcher module."""

import numpy as np
import pytest

from allaganeye.audio.matcher import (
    find_match_peaks,
    sliding_cosine_similarity,
)


def _random_spec(n_features: int, n_frames: int, seed: int = 0) -> np.ndarray:
    rng = np.random.RandomState(seed)
    return rng.rand(n_features, n_frames).astype(np.float32)


def test_self_match_returns_one():
    """Aligning a reference with itself inside a longer target gives sim=1."""
    rng = np.random.RandomState(0)
    ref = rng.rand(20, 50).astype(np.float32)
    pre = rng.rand(20, 30).astype(np.float32)
    post = rng.rand(20, 40).astype(np.float32)
    target = np.concatenate([pre, ref, post], axis=1)

    sim = sliding_cosine_similarity(ref, target)

    expected_position = pre.shape[1]
    assert sim[expected_position] == pytest.approx(1.0, abs=1e-4)


def test_unrelated_signals_have_lower_similarity():
    """Different random signals produce lower similarity than self-match."""
    ref = _random_spec(40, 30, seed=1)
    target = _random_spec(40, 200, seed=2)
    sim = sliding_cosine_similarity(ref, target)
    assert sim.max() < 0.95
    assert sim.shape == (200 - 30 + 1,)


def test_reference_longer_than_target_returns_empty():
    """If the reference is longer than the target, the result is empty."""
    ref = _random_spec(10, 100)
    target = _random_spec(10, 50)
    sim = sliding_cosine_similarity(ref, target)
    assert sim.shape == (0,)


def test_zero_frame_reference_raises():
    """A zero-frame reference is invalid input."""
    ref = np.zeros((10, 0), dtype=np.float32)
    target = _random_spec(10, 50)
    with pytest.raises(ValueError, match="at least one frame"):
        sliding_cosine_similarity(ref, target)


def test_find_match_peaks_returns_sorted_hits():
    """find_match_peaks returns hits sorted by timestamp ascending."""
    sim = np.zeros(1000, dtype=np.float32)
    sim[100] = 0.8
    sim[400] = 0.9
    sim[700] = 0.75

    hits = find_match_peaks(
        sim, threshold=0.7, min_gap_seconds=1.0, frames_per_second=10.0
    )

    assert [h["timestamp"] for h in hits] == [10.0, 40.0, 70.0]
    assert all(0.74 <= h["similarity"] <= 0.91 for h in hits)


def test_find_match_peaks_filters_below_threshold():
    sim = np.zeros(100, dtype=np.float32)
    sim[10] = 0.4
    sim[50] = 0.8

    hits = find_match_peaks(
        sim, threshold=0.7, min_gap_seconds=1.0, frames_per_second=10.0
    )

    assert len(hits) == 1
    assert hits[0]["similarity"] == pytest.approx(0.8)


def test_find_match_peaks_enforces_min_gap():
    """Two close peaks with a gap shorter than min_gap_seconds are deduplicated."""
    sim = np.zeros(100, dtype=np.float32)
    sim[10] = 0.8
    sim[15] = 0.9  # only 0.5s away at 10 fps

    hits = find_match_peaks(
        sim, threshold=0.7, min_gap_seconds=1.0, frames_per_second=10.0
    )

    assert len(hits) == 1
    # Highest score wins per scipy's find_peaks distance behavior
    assert hits[0]["timestamp"] == pytest.approx(1.5)


def test_find_match_peaks_invalid_fps():
    sim = np.zeros(50, dtype=np.float32)
    with pytest.raises(ValueError, match="frames_per_second"):
        find_match_peaks(sim, threshold=0.5, min_gap_seconds=1.0, frames_per_second=0)
