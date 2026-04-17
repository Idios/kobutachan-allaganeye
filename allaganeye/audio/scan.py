"""Full-video BGM scanning for match boundary promotion (#288).

Wraps the audio pipeline (extract -> log-mel -> sliding correlation -> peaks)
into a single call so higher-level detection code does not need to thread
four primitives together.  The scan runs once per video; the resulting
hits are reused for every blackout region evaluated during classification.

Multi-reference bundles (introduced in #289 for War Room, which requires
both pre-patch and post-patch BGM windows) are handled transparently by
taking the per-frame max across all references' sliding similarities
before peak-finding -- the OR-style detection described in issue #289
scope item (b).
"""

from pathlib import Path

import numpy as np

from allaganeye.audio.extract import extract_pcm
from allaganeye.audio.features import load_features_multi, log_mel_spectrogram
from allaganeye.audio.matcher import BgmHit, find_match_peaks, sliding_cosine_similarity
from allaganeye.audio.refs import get_reference_path
from allaganeye.exceptions import VideoProcessingError


_DEFAULT_THRESHOLD = 0.65
"""Similarity threshold shared with #287 horizontal validation.

Fanfare reference hits FL match starts with sim in [0.65, 0.85] on the
recordings covered by the cumulative coverage baseline.  Values below this
band include unrelated BGM cues observed during validation.
"""

_DEFAULT_MIN_GAP_SECONDS = 30.0
"""Minimum spacing between consecutive peaks.

Fanfare plays for ~5s at most, so any second peak within 30s is the same
event's side lobe rather than a separate match start.
"""


def scan_fanfare_hits(
    video_path: Path,
    *,
    threshold: float = _DEFAULT_THRESHOLD,
    min_gap_seconds: float = _DEFAULT_MIN_GAP_SECONDS,
    ref_name: str = "fanfare",
) -> list[BgmHit]:
    """Scan the full audio track for reference-BGM peaks.

    Returns hits sorted by timestamp (seconds from video start).  Raises
    ``VideoProcessingError`` when audio extraction fails (e.g. missing
    audio track) or when the bundled reference feature file is missing;
    callers may catch this to fall back to audio-less classification.

    When the referenced feature file bundles multiple reference windows
    (#289, War Room spans BGM version differences), the per-frame max of
    all references' sliding similarity curves is used; peaks are then
    detected on that combined curve.
    """
    try:
        ref_path = get_reference_path(ref_name)
    except FileNotFoundError as e:
        raise VideoProcessingError(f"fanfare reference feature missing: {e}") from e
    features_list, config, _ = load_features_multi(ref_path)
    pcm = extract_pcm(video_path, sample_rate=config.sample_rate)
    target = log_mel_spectrogram(pcm, config)

    similarity = _combine_sliding_similarity(features_list, target)
    return find_match_peaks(
        similarity,
        threshold=threshold,
        min_gap_seconds=min_gap_seconds,
        frames_per_second=config.frames_per_second,
    )


def _combine_sliding_similarity(
    features_list: list[np.ndarray], target: np.ndarray
) -> np.ndarray:
    """Per-frame max of each reference's sliding cosine similarity.

    Different references may have different frame counts, which makes
    each sliding similarity curve a different length.  We truncate all
    curves to the shortest length before taking the element-wise max so
    the resulting array corresponds to positions where every reference
    could have been placed.  This is safe because we only lose evaluation
    at the very end of the target where a longer reference would not fit
    anyway.
    """
    if not features_list:
        raise ValueError("features_list must contain at least one reference")
    sims = [sliding_cosine_similarity(f, target) for f in features_list]
    if len(sims) == 1:
        return sims[0]
    min_len = min(sim.size for sim in sims)
    stacked = np.stack([sim[:min_len] for sim in sims], axis=0)
    return stacked.max(axis=0)
