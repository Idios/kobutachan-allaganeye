"""GPU/CPU brightness-dict parity probe for #392.

Runs ``_scan_cpu`` and ``scan_gpu`` against the same video + interval,
then diffs the resulting ``{timestamp: brightness}`` dicts.  Missing
timestamps and per-timestamp brightness deltas are printed so we can tell
which of the three failure modes (ケース A: decode pixel delta, ケース B:
timestamp miss, ケース C: borderline hysteresis) explains a specific
regression.

Usage:

    python scripts/gpu_brightness_parity.py <video> \\
        [--interval 3.0] [--start 9200] [--end 9320] \\
        [--brightness-delta 1.0] [--threshold 15.0]

Outputs a plain-text report to stdout + optionally a CSV of the union of
timestamps to ``--csv`` for spreadsheet diffing.  Only samples the
requested ``[start, end)`` window by default so the 2:33-2:35 #392
reproduction stays cheap; omit ``--start`` / ``--end`` to diff the full
video (slow on multi-hour recordings).

Not a test -- manual investigation tool, hence ``scripts/``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make the project root importable when this script is run directly,
# so CI / background tasks that don't pip-install the package can still
# invoke ``python scripts/gpu_brightness_parity.py ...``.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("video", type=Path, help="Input video (mkv/mp4/...)")
    p.add_argument(
        "--interval",
        type=float,
        default=3.0,
        help="Sample interval in seconds (default: 3.0, matches L1 AV1 auto-adjust)",
    )
    p.add_argument(
        "--start",
        type=float,
        default=None,
        help="Window start (seconds). Default: 0",
    )
    p.add_argument(
        "--end",
        type=float,
        default=None,
        help="Window end (seconds). Default: full duration",
    )
    p.add_argument(
        "--threshold",
        type=float,
        default=15.0,
        help="Blackout brightness threshold (default: 15.0)",
    )
    p.add_argument(
        "--brightness-delta",
        type=float,
        default=1.0,
        help=(
            "Report per-timestamp brightness deltas >= this value. "
            "Small deltas (< 1.0) are normal NV12/GRAY conversion noise."
        ),
    )
    p.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="Write union-of-timestamps CSV to this path.",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    if not args.video.exists():
        print(f"error: video not found: {args.video}", file=sys.stderr)
        return 2

    from allaganeye.video.detector import _scan_cpu
    from allaganeye.video.gpu_detector import scan_gpu
    from allaganeye.video.probe import probe_video

    meta = probe_video(args.video)
    duration = meta["duration"]
    codec = meta.get("codec")
    print(
        f"video: {args.video.name}\n"
        f"  duration={duration:.1f}s, codec={codec}, "
        f"resolution={meta['width']}x{meta['height']}"
    )

    win_start = args.start if args.start is not None else 0.0
    win_end = args.end if args.end is not None else duration
    print(
        f"window: [{win_start:.1f}, {win_end:.1f}) "
        f"interval={args.interval}s threshold={args.threshold}"
    )

    # CPU scan: scan the full video (cheap enough at interval=3) to
    # stay identical to production behaviour, then filter to the window.
    print("\n[cpu] scanning...")
    cpu_all = _scan_cpu(args.video, duration, args.interval, args.threshold, None, None)
    cpu = {t: b for t, b in cpu_all.items() if win_start <= t < win_end}
    print(f"[cpu] {len(cpu)} samples in window, {len(cpu_all)} total")

    print("\n[gpu] scanning...")
    try:
        gpu_all = scan_gpu(
            args.video,
            duration,
            args.interval,
            args.threshold,
            None,
            codec=codec,
        )
    except Exception as e:
        print(f"error: GPU scan failed: {e}", file=sys.stderr)
        return 3
    gpu = {t: b for t, b in gpu_all.items() if win_start <= t < win_end}
    print(f"[gpu] {len(gpu)} samples in window, {len(gpu_all)} total")

    # --- Diff ---

    cpu_keys = set(cpu)
    gpu_keys = set(gpu)
    only_cpu = sorted(cpu_keys - gpu_keys)
    only_gpu = sorted(gpu_keys - cpu_keys)
    common = sorted(cpu_keys & gpu_keys)

    print(
        f"\nsample overlap: common={len(common)}, only_cpu={len(only_cpu)}, "
        f"only_gpu={len(only_gpu)}"
    )

    # ケース B: timestamp misses
    if only_cpu:
        print("\n[missing in GPU] timestamps present in CPU scan but not GPU:")
        for t in only_cpu[:30]:
            b = cpu[t]
            marker = "<-- blackout" if b < args.threshold else ""
            print(f"  {t:>8.2f}  brightness={b:6.2f}  {marker}")
        if len(only_cpu) > 30:
            print(f"  ... and {len(only_cpu) - 30} more")
    if only_gpu:
        print("\n[missing in CPU] timestamps present in GPU scan but not CPU:")
        for t in only_gpu[:30]:
            b = gpu[t]
            print(f"  {t:>8.2f}  brightness={b:6.2f}")
        if len(only_gpu) > 30:
            print(f"  ... and {len(only_gpu) - 30} more")

    # ケース A/C: brightness deltas
    print(f"\n[brightness delta >= {args.brightness_delta}] per-timestamp cpu vs gpu:")
    disagree: list[tuple[float, float, float]] = []
    blackout_disagree: list[tuple[float, float, float]] = []
    for t in common:
        c = cpu[t]
        g = gpu[t]
        diff = g - c
        if abs(diff) >= args.brightness_delta:
            disagree.append((t, c, g))
        # Highlight any timestamp where one side is blackout and the
        # other isn't -- these are the specific regressions #392 cares
        # about.
        if (c < args.threshold) != (g < args.threshold):
            blackout_disagree.append((t, c, g))

    if disagree:
        for t, c, g in disagree[:30]:
            print(f"  {t:>8.2f}  cpu={c:6.2f}  gpu={g:6.2f}  delta={g - c:+.2f}")
        if len(disagree) > 30:
            print(f"  ... and {len(disagree) - 30} more")
    else:
        print("  (none above delta threshold)")

    print(
        f"\n[blackout disagreement] one side < {args.threshold}, "
        "the other side >= threshold:"
    )
    if blackout_disagree:
        for t, c, g in blackout_disagree:
            cpu_side = "blackout" if c < args.threshold else "bright"
            gpu_side = "blackout" if g < args.threshold else "bright"
            print(f"  {t:>8.2f}  cpu={c:6.2f} ({cpu_side})  gpu={g:6.2f} ({gpu_side})")
        # This is the smoking gun for #392.
        print(
            f"\n  -> {len(blackout_disagree)} timestamps flip blackout "
            "verdict between modes. This is the #392 failure mode."
        )
    else:
        print("  (none -- blackout verdicts agree across modes)")

    # --- Optional CSV dump ---
    if args.csv is not None:
        keys = sorted(cpu_keys | gpu_keys)
        lines = ["timestamp,cpu_brightness,gpu_brightness,delta"]
        for t in keys:
            c = cpu.get(t)
            g = gpu.get(t)
            if c is None or g is None:
                delta = ""
            else:
                delta = f"{g - c:.3f}"
            lines.append(
                f"{t:.3f},"
                f"{'' if c is None else f'{c:.3f}'},"
                f"{'' if g is None else f'{g:.3f}'},"
                f"{delta}"
            )
        args.csv.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\n[csv] {len(keys)} rows written to {args.csv}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
