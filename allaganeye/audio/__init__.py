"""Audio BGM detection for L1 match boundary refinement.

This module provides one signal among many for accurate match boundary
detection.  See ``allaganeye/video/`` for visual signals and the high-level
``commands/split_matches.py`` for orchestration.

Public API:
    AUDIO_FROZEN -- whether the audio module is frozen (True = skip scan)
    extract_pcm -- pull mono PCM from a video via ffmpeg
    LogMelConfig / log_mel_spectrogram -- compute reference/target features
    save_features / load_features -- persist/load .npz feature files
    sliding_cosine_similarity / find_match_peaks -- match a reference window
    BgmHit -- typed dict for matcher results

Removal (director Q3 compliance, #284):
    If this module ever needs to be stripped from the distribution, the
    package contains no irreversible coupling and can be excised in three
    discrete edits:

    1. delete the ``allaganeye/audio/`` directory (this package and
       ``refs/`` containing the bundled feature references)
    2. drop the ``[tool.setuptools.package-data]`` entry for
       ``allaganeye.audio.refs`` in ``pyproject.toml``
    3. remove the ``scipy`` runtime dependency from ``pyproject.toml``;
       it is used only inside this module (STFT and FFT convolution)
"""

from typing import Final

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
from allaganeye.audio.scan import scan_fanfare_hits

# Audio module freeze flag (#327, l1-detection-redesign.md).
# Fanfare scan alone produces false positives (#303); the module is
# frozen until compound-signal integration is ready.  Set to False
# to re-enable audio promotion as the default behaviour.
AUDIO_FROZEN: Final[bool] = True

__all__ = [
    "AUDIO_FROZEN",
    "BgmHit",
    "LogMelConfig",
    "extract_pcm",
    "find_match_peaks",
    "load_features",
    "log_mel_spectrogram",
    "save_features",
    "scan_fanfare_hits",
    "sliding_cosine_similarity",
]
