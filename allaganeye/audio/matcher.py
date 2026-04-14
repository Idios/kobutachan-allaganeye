"""Cross-correlate a reference feature window against a target spectrogram."""

from typing import TypedDict

import numpy as np
from scipy.signal import fftconvolve, find_peaks


class BgmHit(TypedDict):
    """A single peak in the sliding similarity curve."""

    timestamp: float
    similarity: float


def _normalize_columns(x: np.ndarray) -> np.ndarray:
    """L2-normalize each time frame to unit vector for cosine similarity."""
    norms = np.linalg.norm(x, axis=0, keepdims=True)
    return x / np.maximum(norms, 1e-10)


def sliding_cosine_similarity(reference: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Mean per-frame cosine similarity of *reference* slid across *target*.

    Both inputs are spectrograms of shape ``(n_features, n_frames)``.
    The cross-correlation is computed per feature dimension via FFT and
    summed, yielding the same numeric result as a frame-by-frame loop
    but at a fraction of the cost.

    Returns a (n_target_frames - n_reference_frames + 1,) array with
    values in [-1, 1].  A near-1.0 value indicates the reference window
    aligns at that position.
    """
    ref = _normalize_columns(reference).astype(np.float32)
    tgt = _normalize_columns(target).astype(np.float32)

    n_ref = ref.shape[1]
    n_tgt = tgt.shape[1]
    if n_ref == 0:
        raise ValueError("reference must have at least one frame")
    if n_ref > n_tgt:
        return np.zeros(0, dtype=np.float32)

    out = np.zeros(n_tgt - n_ref + 1, dtype=np.float32)
    for f in range(ref.shape[0]):
        out += fftconvolve(tgt[f], ref[f, ::-1], mode="valid")
    out /= n_ref
    return out


def find_match_peaks(
    similarity: np.ndarray,
    *,
    threshold: float,
    min_gap_seconds: float,
    frames_per_second: float,
) -> list[BgmHit]:
    """Return peaks above *threshold*, separated by at least *min_gap_seconds*.

    Returned hits are sorted by timestamp ascending.  ``timestamp`` is in
    seconds from the start of the target audio (frame index / fps).
    """
    if frames_per_second <= 0:
        raise ValueError("frames_per_second must be positive")
    min_distance = max(1, int(min_gap_seconds * frames_per_second))
    peak_indices, _ = find_peaks(similarity, height=threshold, distance=min_distance)
    return [
        {
            "timestamp": float(idx) / frames_per_second,
            "similarity": float(similarity[idx]),
        }
        for idx in peak_indices
    ]
