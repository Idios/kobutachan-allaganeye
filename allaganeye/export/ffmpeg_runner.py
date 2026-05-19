"""Single-match ffmpeg launcher + libx264 fallback retry (#761).

Ported from gui/src-tauri/src/lib.rs (pre-#761 run_ffmpeg_export_attempt
+ export_match fallback logic, see #591/#761). See spec section 4.3.
"""

from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable

from allaganeye.export.encoder import H264Encoder
from allaganeye.export.schema import ExportError, ExportResult
from allaganeye.ffmpeg_path import find_ffmpeg


_DECODE_HWACCEL_ARGS: dict[H264Encoder, tuple[str, ...]] = {
    # #791: encoder->decode hwaccel mapping.
    # NVENC: NVDEC -> NVENC zero-copy (CUDA memory) on RTX 5090 / driver
    # verified by Idios (#791 Iron Law 6 trigger).
    # QSV / AMF: intentionally empty in this PR. Per Codex adversarial-review
    # (#791) and Idios decision: Intel/AMD decode hwaccel will be wired in
    # #762 (multi-vendor encoder pool) where real-machine validation on
    # Intel iGPU / AMD dGPU is part of the acceptance criteria. Keys kept
    # explicit so a future H264Encoder member doesn't silently miss the
    # mapping via KeyError.
    H264Encoder.NVENC: ("-hwaccel", "cuda", "-hwaccel_output_format", "cuda"),
    H264Encoder.QSV: (),  # wired in #762
    H264Encoder.AMF: (),  # wired in #762
    H264Encoder.LIBX264: (),  # CPU path, no GPU->CPU memcpy
}


_GPU_ENCODER_FAILURE_PATTERNS: dict[H264Encoder, tuple[str, ...]] = {
    # Patterns mirror gui/src-tauri/src/lib.rs:1738+ (#591). Memory:
    # feedback_ffmpeg_qsv_stderr_pattern.md notes ffmpeg 8.1 QSV uses
    # "Error creating a MFX session" (not pre-8.1 "Error initializing").
    H264Encoder.NVENC: (
        # Encoder init failures (pre-#791):
        "no nvenc capable devices found",
        "cannot load cuda driver",
        "openencodesessionex failed",
        # NVDEC decode-stage failures introduced by #791 `-hwaccel cuda`
        # injection. With decode now routed through NVDEC, ffmpeg can fail
        # before reaching the encoder. Detect representative stderr and
        # treat as a GPU failure -> libx264 retry rebuilds argv without
        # `-hwaccel cuda` (mapping returns () for LIBX264) and decodes on CPU.
        # Three failure layers covered (Codex Round 2 finding):
        # (1) CUDA dynamic-library load / device init (earliest):
        "could not dynamically load cuda",
        "cannot load libcuda",
        # (2) CUDA device creation / decoder device setup:
        "device creation failed",
        "device setup failed for decoder",
        "no device available for decoder",
        "failed to create cuda context",
        "cannot init cuda",
        # (3) Decoder creation / frame transfer (latest):
        "cuvidcreatedecoder",  # cuvidCreateDecoder failed
        "hwaccel transfer data failed",
        "cuvid: failed",
        "could not allocate hardware frames",
    ),
    H264Encoder.QSV: (
        "error creating a mfx session",  # 8.1+
        "error initializing an internal mfx session",  # pre-8.1
        "no device available for encoder",
    ),
    H264Encoder.AMF: (
        "dll amfrt64.dll failed to open",
        "amf failed",
        "no opencl-supported device",
    ),
}


def is_gpu_encoder_failure(stderr_text: str, encoder: H264Encoder) -> bool:
    """True iff stderr indicates the GPU encoder failed to initialise."""
    if encoder == H264Encoder.LIBX264:
        return False
    text = stderr_text.lower()
    patterns = _GPU_ENCODER_FAILURE_PATTERNS.get(encoder, ())
    return any(p in text for p in patterns)


@dataclass(frozen=True)
class _AttemptOutcome:
    returncode: int
    stderr_tail: str


def _run_single_attempt(
    args: list[str],
    duration_s: float,
    progress_cb: Callable[[float, str], None],
    cancel_event: threading.Event,
) -> _AttemptOutcome:
    """Launch one ffmpeg process and wait for completion.

    Reads stderr line by line, converts ``out_time_ms`` to a percent and
    passes it to progress_cb. Checks ``cancel_event.is_set()`` on each read;
    calls ``proc.kill()`` if set.
    """
    proc = subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    stderr_tail_bytes: list[bytes] = []
    max_tail = 2048

    assert proc.stderr is not None
    while True:
        if cancel_event.is_set():
            proc.kill()
            break
        line = proc.stderr.readline()
        if not line:
            break
        line_str = line.decode("utf-8", errors="replace").rstrip("\n")
        # Parse progress (ffmpeg -progress pipe:2 format)
        if line_str.startswith("out_time_ms="):
            raw = line_str.split("=", 1)[1]
            us = int(raw) if raw.strip().lstrip("-").isdigit() else 0
            seconds = us / 1_000_000.0
            percent = (seconds / duration_s * 100.0) if duration_s > 0 else 0.0
            percent = max(0.0, min(100.0, percent))
            progress_cb(percent, "encoding")
            continue
        if line_str.strip() == "progress=end":
            progress_cb(100.0, "done")
            continue
        # Accumulate remaining lines in stderr_tail buffer
        stderr_tail_bytes.append(line)
        if sum(len(b) for b in stderr_tail_bytes) > max_tail * 2:
            # Keep only the tail
            while sum(len(b) for b in stderr_tail_bytes) > max_tail:
                stderr_tail_bytes.pop(0)

    returncode = proc.wait()
    tail = b"".join(stderr_tail_bytes).decode("utf-8", errors="replace")
    return _AttemptOutcome(returncode=returncode, stderr_tail=tail[-max_tail:])


def _build_ffmpeg_args(
    ffmpeg: str,
    video: Path,
    start: float,
    end: float,
    output: Path,
    codec: str,
    encoder: H264Encoder,
) -> list[str]:
    """Construct the ffmpeg argv list. Mirrors pre-#761 build_ffmpeg_args in gui/src-tauri/src/lib.rs (see #591/#761).

    #791: codec=="h264" のとき encoder に対応する decode hwaccel 引数を
    `-i` の前に挿入する。codec=="copy" / encoder==LIBX264 は除外。
    """
    args: list[str] = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "info",
        "-progress",
        "pipe:2",
        "-y",
    ]
    if codec != "copy":
        args.extend(_DECODE_HWACCEL_ARGS[encoder])
    args.extend(
        [
            "-ss",
            f"{start:.3f}",
            "-to",
            f"{end:.3f}",
            "-i",
            str(video),
        ]
    )
    if codec == "copy":
        args.extend(["-c", "copy"])
    else:
        args.extend(["-c:v", encoder.value])
        args.extend(list(encoder.quality_args()))
        args.extend(["-c:a", "copy"])
    args.append(str(output))
    return args


def run_export_attempt(
    video: Path,
    start: float,
    end: float,
    output: Path,
    codec: str,
    encoder: H264Encoder,
    *,
    progress_cb: Callable[[float, str], None],
    fallback_cb: Callable[[H264Encoder, H264Encoder, str], None] | None,
    cancel_event: threading.Event,
) -> ExportResult:
    """Launch ffmpeg for one match and wait; retries with libx264 if needed.

    - codec == "copy"  -> encoder is ignored; runs ffmpeg -c copy
    - codec == "h264" -> starts with encoder; retries libx264 on GPU init failure
    """
    ffmpeg = find_ffmpeg()
    duration = end - start
    started = time.monotonic()

    # 1st attempt
    args = _build_ffmpeg_args(ffmpeg, video, start, end, output, codec, encoder)
    outcome = _run_single_attempt(args, duration, progress_cb, cancel_event)

    if cancel_event.is_set():
        raise ExportError(kind="cancelled", message="export cancelled by user")

    if outcome.returncode == 0:
        return ExportResult(
            match_index=-1,  # caller (pool.py) overwrites
            output_path=output,
            duration_ms=int((time.monotonic() - started) * 1000),
            encoder_used=encoder.value,
            fallback_from=None,
        )

    # GPU encoder init failure -> libx264 retry
    if (
        codec == "h264"
        and encoder != H264Encoder.LIBX264
        and is_gpu_encoder_failure(outcome.stderr_tail, encoder)
    ):
        if fallback_cb is not None:
            fallback_cb(
                encoder,
                H264Encoder.LIBX264,
                f"{encoder.display_label} init failed; retrying with libx264",
            )
        retry_args = _build_ffmpeg_args(
            ffmpeg, video, start, end, output, codec, H264Encoder.LIBX264
        )
        retry_outcome = _run_single_attempt(
            retry_args, duration, progress_cb, cancel_event
        )

        if cancel_event.is_set():
            raise ExportError(kind="cancelled", message="export cancelled by user")

        if retry_outcome.returncode == 0:
            return ExportResult(
                match_index=-1,
                output_path=output,
                duration_ms=int((time.monotonic() - started) * 1000),
                encoder_used=H264Encoder.LIBX264.value,
                fallback_from=encoder.value,
            )
        raise ExportError(
            kind="ffmpeg.exit_failed",
            message=f"libx264 retry exited with {retry_outcome.returncode}: "
            + retry_outcome.stderr_tail.strip(),
            hint="Check ffmpeg/codec installation or verify the input video.",
        )

    # Other failures (libx264 1st attempt fail, codec=copy fail, etc.)
    raise ExportError(
        kind="ffmpeg.exit_failed",
        message=f"ffmpeg ({encoder.value}) exited with {outcome.returncode}: "
        + outcome.stderr_tail.strip(),
        hint="Check ffmpeg/codec installation or verify the input video.",
    )
