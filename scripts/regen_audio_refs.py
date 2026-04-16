"""Regenerate bundled audio reference feature files from source recordings.

Reference features are short BGM segments captured from recordings the
maintainer owns.  The script extracts one or more windows via ffmpeg,
computes the log-mel spectrogram, and writes a compressed ``.npz`` to
the bundled ``allaganeye/audio/refs/`` directory.

Single-reference mode (Fanfare, #287):
    python scripts/regen_audio_refs.py \\
        --video "E:/videos/2026-04-08 21-14-05.mkv" \\
        --start 50 --duration 5 --name fanfare

Multi-reference mode (War Room, #289):
    # WR plays differently in pre-patch 20260116-era recordings vs. the
    # canonical ogg / 2026-04-08 recording.  We bundle two windows; the
    # scanner takes the per-frame max of their sliding similarities.
    python scripts/regen_audio_refs.py \\
        --name war_room \\
        --window "E:/projects/kobutachan-tools/kobutachan-allaganeye-eng1/tmp/bgm_extracted/219_PvP_Intro_WarRoom.ogg" 0 1.5 \\
        --window "E:/royalstraightflesh/videos/20260116/2026-01-16 22-12-57.mkv" 6520 3

The output is ``allaganeye/audio/refs/<name>.npz`` (relative to repo root).
Existing files are overwritten.  Single-reference mode writes format v2;
multi-reference mode writes format v3 (backward-compatible loader).
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
    save_features_multi,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Regenerate a bundled audio reference feature file."
    )
    parser.add_argument(
        "--video", type=Path, help="Source recording path (single-ref mode)"
    )
    parser.add_argument(
        "--start",
        type=float,
        help="Start time of the BGM window in seconds (single-ref mode)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=5.0,
        help="Window duration in seconds, default 5 (single-ref mode)",
    )
    parser.add_argument(
        "--window",
        action="append",
        nargs=3,
        metavar=("VIDEO", "START", "DURATION"),
        default=[],
        help=(
            "Multi-ref mode: repeat to add a reference window. "
            "Each window takes 3 args: video path, start sec, duration sec. "
            "Mutually exclusive with --video/--start."
        ),
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


def _extract_window(
    video: Path, start: float, duration: float, config: LogMelConfig
) -> tuple:
    if not video.exists():
        raise FileNotFoundError(f"video not found: {video}")
    print(f"Extracting from {video.name}: start={start}s duration={duration}s")
    pcm = extract_pcm(
        video, sample_rate=config.sample_rate, start=start, duration=duration
    )
    print(f"  PCM samples: {len(pcm)} ({len(pcm) / config.sample_rate:.2f}s)")
    features = log_mel_spectrogram(pcm, config)
    print(f"  features shape: {features.shape}")
    return features, {
        "source_filename": video.name,
        "source_start": start,
        "source_duration": duration,
    }


def main() -> int:
    args = parse_args()

    single_mode = args.video is not None
    multi_mode = len(args.window) > 0
    if single_mode and multi_mode:
        print(
            "ERROR: --video/--start and --window are mutually exclusive",
            file=sys.stderr,
        )
        return 1
    if not single_mode and not multi_mode:
        print(
            "ERROR: provide either --video/--start or at least one --window",
            file=sys.stderr,
        )
        return 1
    if single_mode and args.start is None:
        print("ERROR: --start is required in single-ref mode", file=sys.stderr)
        return 1

    config = LogMelConfig(sample_rate=args.sample_rate, n_mels=args.n_mels)
    out_path = ROOT / "allaganeye" / "audio" / "refs" / f"{args.name}.npz"

    if single_mode:
        features, window_meta = _extract_window(
            args.video, args.start, args.duration, config
        )
        save_features(out_path, features, config, window_meta)
    else:
        features_list = []
        windows_meta = []
        for video_str, start_str, dur_str in args.window:
            f, meta = _extract_window(
                Path(video_str), float(start_str), float(dur_str), config
            )
            features_list.append(f)
            windows_meta.append(meta)
        save_features_multi(
            out_path,
            features_list,
            config,
            {"windows": windows_meta, "n_windows": len(windows_meta)},
        )

    print(f"Wrote {out_path} ({out_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
