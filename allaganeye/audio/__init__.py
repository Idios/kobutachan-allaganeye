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

Removal (Q3 compliance, #284):
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

# Audio module freeze flag (#327, docs/archive/l1-detection-redesign.md).
# Fanfare scan alone produces false positives (#303); the module is
# frozen until compound-signal integration is ready.  Set to False
# to re-enable audio promotion as the default behaviour.
#
# **Indefinite freeze is the standing decision** (#865, 2026-08-26). The three
# options -- unfreeze / remove per the Q3 steps above / keep frozen -- were
# weighed and "keep frozen" was chosen: the module costs nothing at runtime
# (the scan is skipped unconditionally, `--no-audio` is inert, verbose prints
# `audio=frozen`), whereas removing it would be a **breaking change shipped in
# a patch release** -- it retires the `--no-audio` CLI surface, and dropping
# `scipy` (a benefit in itself) would change the distributed dependency set.
# There is **no scheduled review date**; the next natural trigger is the
# two-signal detection re-architecture (see
# `docs/superpowers/specs/2026-07-17-vtuber-timeline-detection-design.md` and
# `docs/detection-map.md`), whose outcome decides whether the compound-signal
# integration below ever lands.
#
# Material for a future unfreeze, kept here because #327 is closed and the
# ledger of open issues cannot reach it:
#
# * the (B) condition -- gate a Fanfare peak on the preceding War Room peak,
#   using the bundled `refs/war_room.npz` (#306), to drop the in-match false
#   positives that make the Fanfare-only rule unusable (#303)
# * the 2026-06-10 audit items P2-1 (corroboration) and P2-5 (memory), see
#   `docs/audits/2026-06-10-full-audit.md`
#
# AGENTS.md section "音声昇格" carries the same decision for readers who never
# open this file.
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
