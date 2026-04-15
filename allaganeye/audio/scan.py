"""Full-video BGM scanning for match boundary promotion (#288).

Wraps the audio pipeline (extract → log-mel → sliding correlation → peaks)
into a single call so higher-level detection code does not need to thread
four primitives together.  The scan runs once per video; the resulting
hits are reused for every blackout region evaluated during classification.
"""

from pathlib import Path

from allaganeye.audio.extract import extract_pcm
from allaganeye.audio.features import log_mel_spectrogram, load_features
from allaganeye.audio.matcher import BgmHit, find_match_peaks, sliding_cosine_similarity
from allaganeye.audio.refs import get_reference_path


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
    audio track); callers may catch this to fall back to audio-less
    classification.
    """
    features, config, _ = load_features(get_reference_path(ref_name))
    pcm = extract_pcm(video_path, sample_rate=config.sample_rate)
    target = log_mel_spectrogram(pcm, config)
    similarity = sliding_cosine_similarity(features, target)
    return find_match_peaks(
        similarity,
        threshold=threshold,
        min_gap_seconds=min_gap_seconds,
        frames_per_second=config.frames_per_second,
    )
