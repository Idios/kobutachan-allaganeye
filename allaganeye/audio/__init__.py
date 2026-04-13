"""Audio BGM detection for L1 match boundary refinement.

This module provides one signal among many for accurate match boundary
detection.  See ``allaganeye/video/`` for visual signals and the high-level
``commands/split_matches.py`` for orchestration.

Public API:
    extract_pcm — pull mono PCM from a video via ffmpeg
    LogMelConfig / log_mel_spectrogram — compute reference/target features
    save_features / load_features — persist/load .npz feature files
    sliding_cosine_similarity / find_match_peaks — match a reference window
    BgmHit — typed dict for matcher results
"""

from allaganeye.audio.extract import extract_pcm
from allaganeye.audio.features import (
    LogMelConfig,
    load_features,
    log_mel_spectrogram,
    save_features,
)
from allaganeye.audio.matcher import (
    BgmHit,
    find_match_peaks,
    sliding_cosine_similarity,
)

__all__ = [
    "BgmHit",
    "LogMelConfig",
    "extract_pcm",
    "find_match_peaks",
    "load_features",
    "log_mel_spectrogram",
    "save_features",
    "sliding_cosine_similarity",
]
