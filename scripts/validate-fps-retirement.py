#!/usr/bin/env python3
"""Validate ffmpeg output seek + N-th sampling correctness (#576).

One-off implementation-time evidence tool for #576 (detect fps filter
retirement). For each chunk_start, run the new ffmpeg command and
verify:

1. First emitted frame's PTS equals chunk_start within 1 frame slack
2. First emitted frame's brightness matches _probe_single_frame() at
   chunk_start within +-2.0 (= _BLACKOUT_THRESHOLD_UPPER_MARGIN)

Not a CI gate; the PR body pastes the stdout TSV as evidence.

Usage:
    python scripts/validate-fps-retirement.py \\
        --video <path> \\
        --chunks 0,100.5,3600,7200 \\
        --vendor nvidia \\
        --codec av1

Exit codes: 0 = all PASS, 1 = any FAIL, 2 = script error.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Add repo root to PYTHONPATH so we can import allaganeye.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from allaganeye.ffmpeg_path import find_ffmpeg  # noqa: E402
from allaganeye.video.detector import (  # noqa: E402
    _BLACKOUT_THRESHOLD_UPPER_MARGIN,
    _FRAME_SIZE,
    _SAMPLE_HEIGHT,
    _SAMPLE_WIDTH,
    _probe_single_frame,
)
from allaganeye.video.gpu_detector import (  # noqa: E402
    _GPU_DECODER_MAP,
    _HWACCEL_OUTPUT_FORMAT_MAP,
    _HWACCELS_NEED_HWDOWNLOAD,
    _VENDOR_HWACCEL_MAP,
)
from allaganeye.video.probe import probe_video  # noqa: E402

import numpy as np  # noqa: E402

# Matches every showinfo line, capturing its pts_time value.
# Pattern: n: <int> pts: <int> pts_time:<float>
_PTS_RE = re.compile(r"n:\s*\d+\s+pts:\s*-?\d+\s+pts_time:(-?[\d.]+)")

# Printed pts_time has finite decimal precision; a frame exactly at chunk_start
# can print a hair below it.  0.1 ms is far under any real frame period (#804).
_PTS_EPSILON = 1e-4


def _classify_chunk(chunk_start: float, duration: float) -> str:
    """Return 'skip_tail' if chunk_start + 0.5 > duration, else 'run'."""
    if chunk_start + 0.5 > duration:
        return "skip_tail"
    return "run"


def _check_vendor_codec_supported(vendor: str, codec: str) -> bool:
    """True if vendor supports codec per _GPU_DECODER_MAP; CPU always True."""
    if vendor == "cpu":
        return True
    vendor_map = _GPU_DECODER_MAP.get(vendor, {})
    return codec in vendor_map


def _validate_duration_against_chunks(duration: float, chunks: list[float]) -> None:
    """Exit 2 if smallest chunk_start exceeds video duration."""
    if not chunks:
        return
    smallest = min(chunks)
    if duration < smallest:
        print(
            f"ERROR: video duration {duration}s shorter than smallest "
            f"chunk_start {smallest}s",
            file=sys.stderr,
        )
        sys.exit(2)


def _parse_first_emitted_pts_time(stderr_text: str, chunk_start: float) -> float | None:
    """Extract pts_time of the first *emitted* showinfo frame. None if absent.

    Output seek (``-ss`` after ``-i``) trims at the muxer stage AFTER the
    filter graph, so showinfo logs every decoded frame from t=0 and the
    ``n: 0`` line is always the video's first frame (= container start_time,
    the constant 0.021 that #804 reported).  The first frame the muxer
    actually emits is the first showinfo line with
    ``pts_time >= chunk_start`` (within printing-precision epsilon).
    """
    for m in _PTS_RE.finditer(stderr_text):
        pts = float(m.group(1))
        if pts >= chunk_start - _PTS_EPSILON:
            return pts
    return None


def _build_ffmpeg_cmd(
    video: Path,
    chunk_start: float,
    vendor: str,
    codec: str,
) -> list[str]:
    """Build ffmpeg cmd for showinfo + new path (output seek + passthrough)."""
    hwaccel_args: list[str] = []
    decoder: str | None = None
    if vendor != "cpu":
        decoder = _GPU_DECODER_MAP.get(vendor, {}).get(codec)
        hwaccel_name = _VENDOR_HWACCEL_MAP.get(vendor)
        if decoder and hwaccel_name:
            hwaccel_args = ["-hwaccel", hwaccel_name]
            if hwaccel_name in _HWACCELS_NEED_HWDOWNLOAD:
                surface_fmt = _HWACCEL_OUTPUT_FORMAT_MAP.get(hwaccel_name, hwaccel_name)
                hwaccel_args += ["-hwaccel_output_format", surface_fmt]
            hwaccel_args += ["-c:v", decoder]

    needs_hwdownload = bool(
        decoder and _VENDOR_HWACCEL_MAP.get(vendor) in _HWACCELS_NEED_HWDOWNLOAD
    )
    vf_prefix = "hwdownload,format=nv12," if needs_hwdownload else ""

    return [
        find_ffmpeg(),
        *hwaccel_args,
        "-i",
        str(video),
        "-ss",
        str(chunk_start),
        "-t",
        "0.5",
        "-fps_mode",
        "passthrough",
        "-vf",
        f"{vf_prefix}showinfo,scale={_SAMPLE_WIDTH}:{_SAMPLE_HEIGHT},format=gray",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "pipe:1",
    ]


def _run_chunk(
    video: Path,
    chunk_start: float,
    vendor: str,
    codec: str,
    source_fps: float,
) -> tuple[float | None, float | None, float]:
    """Run ffmpeg and return (emit_pts, emit_brightness, probe_brightness)."""
    cmd = _build_ffmpeg_cmd(video, chunk_start, vendor, codec)
    proc = subprocess.run(cmd, capture_output=True, timeout=60)
    stderr_text = proc.stderr.decode(errors="replace")
    emit_pts = _parse_first_emitted_pts_time(stderr_text, chunk_start)

    if proc.returncode != 0 or len(proc.stdout) < _FRAME_SIZE:
        emit_brightness: float | None = None
    else:
        frame = np.frombuffer(proc.stdout[:_FRAME_SIZE], dtype=np.uint8)
        emit_brightness = float(frame.mean())

    probe_brightness = _probe_single_frame(video, chunk_start)
    return emit_pts, emit_brightness, probe_brightness


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns exit code: 0 = all PASS, 1 = any FAIL, 2 = error."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--video", type=Path, required=True)
    p.add_argument("--chunks", required=True, help="CSV of chunk_start floats")
    p.add_argument("--vendor", choices=["cpu", "nvidia", "amd", "intel"], required=True)
    p.add_argument("--codec", choices=["h264", "hevc", "av1", "vp9"], required=True)
    p.add_argument("--source-fps-num", type=int, default=None)
    p.add_argument("--source-fps-den", type=int, default=None)
    args = p.parse_args(argv)

    if not args.video.exists():
        print(f"ERROR: video not found: {args.video}", file=sys.stderr)
        return 2

    if not _check_vendor_codec_supported(args.vendor, args.codec):
        print(
            f"ERROR: vendor {args.vendor} does not support codec {args.codec} "
            f"in _GPU_DECODER_MAP (refer to gpu_detector.py)",
            file=sys.stderr,
        )
        return 2

    try:
        chunks = [float(s) for s in args.chunks.split(",") if s.strip()]
    except ValueError as e:
        print(f"ERROR: invalid --chunks value: {e}", file=sys.stderr)
        return 2
    if not chunks:
        print("ERROR: --chunks must contain at least one value", file=sys.stderr)
        return 2

    probe = probe_video(args.video)
    duration = probe["duration"]
    source_fps = probe["fps"]

    _validate_duration_against_chunks(duration, chunks)

    # TSV header
    print(
        "chunk_start\tvendor\tcodec\temit_pts\temit_brightness\tprobe_brightness"
        "\tpts_diff\tbrightness_diff\tverdict"
    )

    total = 0
    pass_ = 0
    fail = 0
    skipped = 0

    for chunk_start in chunks:
        cls = _classify_chunk(chunk_start, duration)
        if cls == "skip_tail":
            print(
                f"WARN: chunk_start {chunk_start} too close to duration {duration}",
                file=sys.stderr,
            )
            skipped += 1
            continue

        emit_pts, emit_brightness, probe_brightness = _run_chunk(
            args.video,
            chunk_start,
            args.vendor,
            args.codec,
            source_fps,
        )
        if emit_pts is None or emit_brightness is None:
            verdict = "FAIL"
            fail += 1
            pts_diff_s = "n/a"
            brightness_diff_s = "n/a"
        else:
            pts_diff = abs(emit_pts - chunk_start)
            brightness_diff = abs(emit_brightness - probe_brightness)
            pts_ok = pts_diff < (1.0 / source_fps)
            brightness_ok = brightness_diff < _BLACKOUT_THRESHOLD_UPPER_MARGIN
            verdict = "PASS" if pts_ok and brightness_ok else "FAIL"
            if verdict == "PASS":
                pass_ += 1
            else:
                fail += 1
            pts_diff_s = f"{pts_diff:.4f}"
            brightness_diff_s = f"{brightness_diff:.4f}"
        total += 1
        print(
            f"{chunk_start}\t{args.vendor}\t{args.codec}\t"
            f"{emit_pts}\t{emit_brightness}\t{probe_brightness}\t"
            f"{pts_diff_s}\t{brightness_diff_s}\t{verdict}"
        )

    print(f"# SUMMARY total={total} pass={pass_} fail={fail} skipped={skipped}")

    if total == 0:
        # All chunks were skipped -> no test material
        return 2
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
