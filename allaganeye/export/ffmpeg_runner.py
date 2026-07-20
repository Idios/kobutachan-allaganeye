"""Single-match ffmpeg launcher + libx264 fallback retry (#761).

Ported from gui/src-tauri/src/lib.rs (pre-#761 run_ffmpeg_export_attempt
+ export_match fallback logic, see #591/#761). See spec section 4.3.
"""

from __future__ import annotations

import queue as _queue
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable

from allaganeye.export.encoder import H264Encoder
from allaganeye.export.schema import ExportError, ExportResult
from allaganeye.ffmpeg_path import find_ffmpeg


# P2-40: cap the stderr reader queue so a noisy/runaway ffmpeg can't grow it
# without bound (memory). Round 1 FIX 2: under a flood the queue evicts the
# OLDEST line (ring), so the recent tail -- where a fatal ffmpeg error appears --
# survives, which is what matters for the error message.
_STDERR_QUEUE_MAX = 4096


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


# #899: video_filter 有り (minimap crop 等) 用の decode-only hwaccel。
# -hwaccel_output_format cuda を付けない = NVDEC decode 後に auto-download し
# CPU crop filter に渡せる。GPU decode + CPU crop + NVENC encode。
_DECODE_HWACCEL_ARGS_FILTERED: dict[H264Encoder, tuple[str, ...]] = {
    H264Encoder.NVENC: ("-hwaccel", "cuda"),  # decode-only, auto-download
    H264Encoder.QSV: (),  # #762 保留 (software decode 継続)
    H264Encoder.AMF: (),  # #762 保留
    H264Encoder.LIBX264: (),
}


# #899: NVENC の失敗 pattern を 2 段に分割 (値は #791 の 14 個と同一)。
# encode-init: NVENC encoder が使えない -> libx264 直行 (tier3)。
_NVENC_ENCODE_STAGE_PATTERNS: tuple[str, ...] = (
    "no nvenc capable devices found",
    "cannot load cuda driver",
    "openencodesessionex failed",
)
# decode-stage: NVDEC decode が失敗 (`-hwaccel cuda`) -> software decode + NVENC (tier2)。
_NVENC_DECODE_STAGE_PATTERNS: tuple[str, ...] = (
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
)


_GPU_ENCODER_FAILURE_PATTERNS: dict[H264Encoder, tuple[str, ...]] = {
    # Patterns mirror gui/src-tauri/src/lib.rs:1738+ (#591). Memory:
    # feedback_ffmpeg_qsv_stderr_pattern.md notes ffmpeg 8.1 QSV uses
    # "Error creating a MFX session" (not pre-8.1 "Error initializing").
    # #899: NVENC entry is the union of encode-init (3) + decode-stage (11)
    # subsets -- value is identical to the pre-#899 14-pattern tuple.
    H264Encoder.NVENC: _NVENC_ENCODE_STAGE_PATTERNS + _NVENC_DECODE_STAGE_PATTERNS,
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


def _nvenc_decode_stage_failure(stderr_text: str) -> bool:
    """True iff stderr is NVDEC decode-stage (`-hwaccel cuda`) failure.

    #899: filter 有り NVENC の tier1 (NVDEC+NVENC) 失敗を、decode 段
    (-> tier2 software decode + NVENC) か encode 段 (-> tier3 libx264) かに
    振り分けるために使う。
    """
    text = stderr_text.lower()
    return any(p in text for p in _NVENC_DECODE_STAGE_PATTERNS)


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

    stderr is pumped by a daemon reader thread into a queue so the main loop
    can poll ``cancel_event`` on a bounded cadence even when ffmpeg produces no
    output (audit P2-40 -- the old direct ``readline()`` blocked indefinitely
    and ignored cancel until the next line arrived). ``out_time_ms`` lines are
    converted to a percent and passed to ``progress_cb``; the rest accumulate in
    a bounded stderr tail buffer.
    """
    proc = subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    assert proc.stderr is not None
    stderr = proc.stderr  # bind narrowed (non-None) handle for the reader closure
    # P2-40: a bounded queue + stop flag keep the stderr reader thread from
    # outliving the attempt or growing memory without bound. The pump exits on
    # stderr EOF or when stop_reading is set (finally below); the main loop
    # detects completion via reader.is_alive() + a drained queue, so a missing
    # sentinel can't hang it. Round 1 FIX 2: under a flood the queue drops the
    # OLDEST line (ring), so the recent tail -- where a fatal ffmpeg error
    # appears -- is retained for the error message. Same bounded-drain concern
    # as start_detect / #838.
    line_q: _queue.Queue[bytes] = _queue.Queue(maxsize=_STDERR_QUEUE_MAX)
    stop_reading = threading.Event()

    def _pump() -> None:
        while not stop_reading.is_set():
            line = stderr.readline()
            if not line:  # EOF
                break
            try:
                line_q.put_nowait(line)
            except _queue.Full:
                # Round 1 FIX 2: ring under flood -- drop the OLDEST queued line
                # so the most recent output (where a fatal ffmpeg error appears)
                # is retained. Dropping the NEW line instead would discard exactly
                # the error tail we need for the failure message.
                try:
                    line_q.get_nowait()
                except _queue.Empty:
                    pass
                try:
                    line_q.put_nowait(line)
                except _queue.Full:
                    pass

    reader = threading.Thread(target=_pump, name="ffmpeg-stderr", daemon=True)
    reader.start()

    stderr_tail_bytes: list[bytes] = []
    # Round 1 FIX 5: track the running byte total so the tail trim is O(1)
    # amortized instead of recomputing sum(len(b) ...) on every append/pop.
    stderr_tail_total = 0
    max_tail = 2048
    try:
        while True:
            if cancel_event.is_set():
                proc.kill()
                break
            try:
                line = line_q.get(timeout=0.1)  # bounded: re-check cancel every 100ms
            except _queue.Empty:
                # Reader finished (EOF or stopped) and the queue is drained.
                if not reader.is_alive() and line_q.empty():
                    break
                continue
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
            # Accumulate remaining lines in stderr_tail buffer. Trim from the
            # front once it grows past max_tail*2, keeping ~max_tail trailing
            # bytes. The running total avoids an O(n) sum() on each iteration.
            stderr_tail_bytes.append(line)
            stderr_tail_total += len(line)
            if stderr_tail_total > max_tail * 2:
                while stderr_tail_total > max_tail:
                    stderr_tail_total -= len(stderr_tail_bytes.pop(0))
    finally:
        stop_reading.set()

    # Bounded wait: kill if the process doesn't exit promptly (cancel already
    # killed above; this guards a stalled-but-EOF process).
    try:
        returncode = proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
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
    video_filter: str | None = None,
    *,
    force_software_decode: bool = False,
) -> list[str]:
    """Construct the ffmpeg argv list. Mirrors pre-#761 build_ffmpeg_args in gui/src-tauri/src/lib.rs (see #591/#761).

    #791: codec=="h264" のとき encoder に対応する decode hwaccel 引数を
    `-i` の前に挿入する。codec=="copy" / encoder==LIBX264 は除外。

    #481: video_filter 指定時は `-vf <filter>` を `-c:v` の直前に挿入する。

    #899: video_filter 有りの NVENC は zero-copy でなく `-hwaccel cuda` 単独
    (auto-download) で GPU decode + CPU crop。force_software_decode=True は
    decode hwaccel を挿入しない (3-tier ladder の tier2 = software decode + NVENC)。
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
    if codec != "copy" and not force_software_decode:
        if video_filter is None:
            args.extend(_DECODE_HWACCEL_ARGS[encoder])  # zero-copy (export、不変)
        else:
            args.extend(_DECODE_HWACCEL_ARGS_FILTERED[encoder])  # #899: decode-only
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
        if video_filter is not None:
            args.extend(["-vf", video_filter])
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
    video_filter: str | None = None,
) -> ExportResult:
    """Launch ffmpeg for one match and wait; retries with libx264 if needed.

    - codec == "copy"  -> encoder is ignored; runs ffmpeg -c copy
    - codec == "h264" -> starts with encoder; retries libx264 on GPU init failure

    #481: video_filter 指定時は -vf <filter> を挿入する。
    codec=="copy" との併用は意味的矛盾のため ValueError を raise する。
    """
    if video_filter is not None and codec == "copy":
        raise ValueError(
            "video_filter cannot be used with codec='copy': "
            "stream-copy does not re-encode and therefore cannot apply a video filter."
        )
    ffmpeg = find_ffmpeg()
    duration = end - start
    started = time.monotonic()
    # Finding 1: record whether the output already existed BEFORE this attempt.
    # The I-5 cleanup below skips any path that existed before the attempt, so
    # we never delete a file the current attempt did not create.
    # Round 1 FIX 3 (comment accuracy): with ffmpeg's `-y`, the output is
    # truncated on open, so a pre-existing file that ffmpeg opened-then-failed
    # is ALREADY destroyed (and may remain as a truncated partial) -- the gate
    # cannot preserve its contents. The gate's real guarantee is narrower: it
    # only protects a file ffmpeg failed to open at all. Leaving a truncated
    # pre-existing partial in place is the accepted lesser-evil vs. unlinking a
    # file ffmpeg never touched.
    output_pre_existed = output.exists()

    # 1st attempt
    args = _build_ffmpeg_args(
        ffmpeg, video, start, end, output, codec, encoder, video_filter
    )
    outcome = _run_single_attempt(args, duration, progress_cb, cancel_event)

    if cancel_event.is_set():
        # P3 I-5: clean up the partial output on cancel so a half-written .mp4
        # is not left behind. NEVER unlink on success returns. Finding 1: only
        # remove a file THIS attempt created (a pre-existing one is preserved).
        if not output_pre_existed:
            output.unlink(missing_ok=True)
        raise ExportError(kind="cancelled", message="export cancelled by user")

    if outcome.returncode == 0:
        return ExportResult(
            match_index=-1,  # caller (pool.py) overwrites
            output_path=output,
            duration_ms=int((time.monotonic() - started) * 1000),
            encoder_used=encoder.value,
            fallback_from=None,
        )

    # #899 tier2: filter 有り NVENC の tier1 (NVDEC decode) が decode 段で失敗
    # した場合のみ software decode + NVENC で 1 回 retry する (encode は GPU 維持)。
    # tier2 は出力品質が変わらないため fallback_cb は呼ばない (silent decode retry)。
    # tier2 が失敗したら outcome を上書きして下の libx264 (tier3) ブロックへ流す。
    if (
        codec == "h264"
        and encoder == H264Encoder.NVENC
        and video_filter is not None
        and _nvenc_decode_stage_failure(outcome.stderr_tail)
    ):
        tier2_args = _build_ffmpeg_args(
            ffmpeg,
            video,
            start,
            end,
            output,
            codec,
            encoder,
            video_filter,
            force_software_decode=True,
        )
        outcome = _run_single_attempt(tier2_args, duration, progress_cb, cancel_event)
        if cancel_event.is_set():
            if not output_pre_existed:
                output.unlink(missing_ok=True)
            raise ExportError(kind="cancelled", message="export cancelled by user")
        if outcome.returncode == 0:
            return ExportResult(
                match_index=-1,
                output_path=output,
                duration_ms=int((time.monotonic() - started) * 1000),
                encoder_used=encoder.value,
                fallback_from=None,
            )
        # tier2 も失敗 -> outcome は tier2 の失敗。下の libx264 ブロックが拾う。

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
        # NOTE: do NOT unlink here -- the retry uses -y to overwrite in place.
        retry_args = _build_ffmpeg_args(
            ffmpeg, video, start, end, output, codec, H264Encoder.LIBX264, video_filter
        )
        retry_outcome = _run_single_attempt(
            retry_args, duration, progress_cb, cancel_event
        )

        if cancel_event.is_set():
            # P3 I-5: clean up partial from the retry attempt on cancel.
            # Finding 1: only if this attempt created it (skip pre-existing).
            if not output_pre_existed:
                output.unlink(missing_ok=True)
            raise ExportError(kind="cancelled", message="export cancelled by user")

        if retry_outcome.returncode == 0:
            return ExportResult(
                match_index=-1,
                output_path=output,
                duration_ms=int((time.monotonic() - started) * 1000),
                encoder_used=H264Encoder.LIBX264.value,
                fallback_from=encoder.value,
            )
        # P3 I-5: final failure (libx264 retry also failed) -> remove partial.
        # Finding 1: only if this attempt created it (skip pre-existing).
        if not output_pre_existed:
            output.unlink(missing_ok=True)
        raise ExportError(
            kind="ffmpeg.exit_failed",
            message=f"libx264 retry exited with {retry_outcome.returncode}: "
            + retry_outcome.stderr_tail.strip(),
            hint="Check ffmpeg/codec installation or verify the input video.",
        )

    # Other failures (libx264 1st attempt fail, codec=copy fail, etc.)
    # P3 I-5: remove the partial output left by a failed encode.
    # Finding 1: only if this attempt created it (skip pre-existing).
    if not output_pre_existed:
        output.unlink(missing_ok=True)
    raise ExportError(
        kind="ffmpeg.exit_failed",
        message=f"ffmpeg ({encoder.value}) exited with {outcome.returncode}: "
        + outcome.stderr_tail.strip(),
        hint="Check ffmpeg/codec installation or verify the input video.",
    )
