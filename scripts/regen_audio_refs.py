"""Regenerate bundled audio reference feature files from a source recording.

Reference features are short BGM segments captured from a recording the
maintainer owns.  The script extracts a window via ffmpeg, computes the
log-mel spectrogram, and writes a compressed ``.npz`` to the bundled
``allaganeye/audio/refs/`` directory.

Usage:
    python scripts/regen_audio_refs.py \\
        --video PATH --start 50 --duration 5 --name fanfare

The output is ``allaganeye/audio/refs/<name>.npz`` (relative to repo root).
Existing files are overwritten.
"""

import argparse
import sys
from pathlib import Path

# Allow running from a fresh checkout without installing the package
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from allaganeye.audio.extract import extract_pcm  # noqa: E402
from allaganeye.audio.features import (  # noqa: E402
    LogMelConfig,
    log_mel_spectrogram,
    save_features,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Regenerate a bundled audio reference feature file."
    )
    parser.add_argument(
        "--video", type=Path, required=True, help="Source recording path"
    )
    parser.add_argument(
        "--start",
        type=float,
        required=True,
        help="Start time of the BGM window (seconds)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=5.0,
        help="Window duration (seconds, default: 5)",
    )
    parser.add_argument(
        "--name",
        required=True,
        help="Reference name (e.g. 'fanfare'). Output: allaganeye/audio/refs/<name>.npz",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=22050,
        help="Sample rate for STFT (default: 22050)",
    )
    parser.add_argument(
        "--n-mels", type=int, default=80, help="Number of mel bands (default: 80)"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.video.exists():
        print(f"ERROR: video not found: {args.video}", file=sys.stderr)
        return 1

    config = LogMelConfig(sample_rate=args.sample_rate, n_mels=args.n_mels)
    out_path = ROOT / "allaganeye" / "audio" / "refs" / f"{args.name}.npz"

    print(
        f"Extracting audio from {args.video.name}: start={args.start}s duration={args.duration}s"
    )
    pcm = extract_pcm(
        args.video,
        sample_rate=config.sample_rate,
        start=args.start,
        duration=args.duration,
    )
    print(f"  PCM samples: {len(pcm)} ({len(pcm) / config.sample_rate:.2f}s)")

    print("Computing log-mel features...")
    features = log_mel_spectrogram(pcm, config)
    print(f"  features shape: {features.shape} (n_mels={config.n_mels})")

    metadata = {
        "source_filename": args.video.name,
        "source_start": args.start,
        "source_duration": args.duration,
    }
    save_features(out_path, features, config, metadata)
    print(f"Wrote {out_path} ({out_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
