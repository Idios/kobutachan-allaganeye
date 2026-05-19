"""Tests for single-attempt ffmpeg runner + libx264 fallback (#761).

Ported from gui/src-tauri/src/lib.rs tests (pre-#761 run_ffmpeg_export_attempt /
is_gpu_encoder_failure coverage, see #591/#761). Heavy mocking around subprocess.Popen.
"""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from allaganeye.export.encoder import H264Encoder
from allaganeye.export.ffmpeg_runner import (
    _build_ffmpeg_args,
    is_gpu_encoder_failure,
    run_export_attempt,
)
from allaganeye.export.schema import ExportError


# --- is_gpu_encoder_failure ---


def test_nvenc_no_capable_devices():
    text = "[h264_nvenc @ 0xfff] No NVENC capable devices found"
    assert is_gpu_encoder_failure(text, H264Encoder.NVENC)


def test_nvenc_init_failed():
    text = "Cannot load CUDA driver"
    assert is_gpu_encoder_failure(text, H264Encoder.NVENC)


def test_qsv_mfx_session_creation_failure():
    """Memory: feedback_ffmpeg_qsv_stderr_pattern.md notes 8.1 uses 'Error creating'."""
    text = "[h264_qsv @ 0xfff] Error creating a MFX session: -3 (unsupported)"
    assert is_gpu_encoder_failure(text, H264Encoder.QSV)


def test_amf_dll_failure():
    text = "DLL amfrt64.dll failed to open"
    assert is_gpu_encoder_failure(text, H264Encoder.AMF)


def test_libx264_never_triggers_fallback():
    """libx264 itself is the fallback target -- fallback predicate is False."""
    text = "anything"
    assert not is_gpu_encoder_failure(text, H264Encoder.LIBX264)


def test_unrelated_error_not_classified_as_gpu_init():
    text = "Conversion failed!"
    assert not is_gpu_encoder_failure(text, H264Encoder.NVENC)


def test_nvenc_nvdec_decode_failure_cuvidcreatedecoder():
    """#791: NVDEC decode stage failures (introduced by -hwaccel cuda) trigger libx264 retry."""
    text = "[h264_cuvid @ 0x...] cuvidCreateDecoder failed: invalid argument"
    assert is_gpu_encoder_failure(text, H264Encoder.NVENC)


def test_nvenc_nvdec_decode_failure_cuda_context():
    text = "Failed to create CUDA context (1)"
    assert is_gpu_encoder_failure(text, H264Encoder.NVENC)


def test_nvenc_nvdec_decode_failure_hwaccel_transfer():
    text = "hwaccel transfer data failed"
    assert is_gpu_encoder_failure(text, H264Encoder.NVENC)


def test_nvenc_nvdec_cuda_dynamic_load_failure():
    """#791 Codex Round 2: CUDA dynamic library load failure (Linux variant)."""
    text = "Could not dynamically load CUDA"
    assert is_gpu_encoder_failure(text, H264Encoder.NVENC)


def test_nvenc_nvdec_device_creation_failure():
    """#791 Codex Round 2: CUDA device creation (cuInit / cuDeviceGet) failure."""
    text = "Device creation failed: out of memory"
    assert is_gpu_encoder_failure(text, H264Encoder.NVENC)


def test_nvenc_nvdec_device_setup_failure():
    """#791 Codex Round 2: decoder device setup failure (between device init and decoder creation)."""
    text = "Device setup failed for decoder on input stream #0:0"
    assert is_gpu_encoder_failure(text, H264Encoder.NVENC)


def test_nvenc_nvdec_no_device_available():
    """#791 Codex Round 2: no CUDA device available for the decoder."""
    text = "No device available for decoder: device type cuda needed"
    assert is_gpu_encoder_failure(text, H264Encoder.NVENC)


# --- run_export_attempt: success path ---


@patch("allaganeye.export.ffmpeg_runner.subprocess.Popen")
def test_run_export_attempt_nvenc_success(mock_popen: MagicMock, tmp_path: Path):
    proc = MagicMock()
    proc.stderr = MagicMock()
    proc.stderr.readline = MagicMock(
        side_effect=[
            b"frame=  100 fps=30 q=23.0 size=    256kB time=00:00:01.00 bitrate=2097.2kbits/s speed=1x    \n",
            b"out_time_ms=1000000\n",
            b"progress=continue\n",
            b"out_time_ms=2000000\n",
            b"progress=end\n",
            b"",  # EOF
        ]
    )
    proc.wait = MagicMock(return_value=0)
    proc.returncode = 0
    mock_popen.return_value = proc

    progress_calls: list[tuple[float, str]] = []

    def cb(percent: float, stage: str):
        progress_calls.append((percent, stage))

    result = run_export_attempt(
        video=tmp_path / "in.mp4",
        start=0.0,
        end=10.0,
        output=tmp_path / "out.mp4",
        codec="h264",
        encoder=H264Encoder.NVENC,
        progress_cb=cb,
        fallback_cb=None,
        cancel_event=threading.Event(),
    )
    assert result.encoder_used == H264Encoder.NVENC.value
    assert result.fallback_from is None
    assert any(stage == "encoding" for _, stage in progress_calls)


# --- run_export_attempt: libx264 fallback ---


@patch("allaganeye.export.ffmpeg_runner.subprocess.Popen")
def test_run_export_attempt_nvenc_init_fail_falls_back_to_libx264(
    mock_popen: MagicMock, tmp_path: Path
):
    """1st attempt (NVENC) returns non-zero with init-fail stderr -> 2nd attempt libx264."""
    proc_nvenc = MagicMock()
    proc_nvenc.stderr = MagicMock()
    proc_nvenc.stderr.readline = MagicMock(
        side_effect=[
            b"[h264_nvenc @ 0xfff] No NVENC capable devices found\n",
            b"",
        ]
    )
    proc_nvenc.wait = MagicMock(return_value=1)
    proc_nvenc.returncode = 1

    proc_libx264 = MagicMock()
    proc_libx264.stderr = MagicMock()
    proc_libx264.stderr.readline = MagicMock(
        side_effect=[
            b"out_time_ms=1000000\n",
            b"progress=end\n",
            b"",
        ]
    )
    proc_libx264.wait = MagicMock(return_value=0)
    proc_libx264.returncode = 0

    mock_popen.side_effect = [proc_nvenc, proc_libx264]

    fallback_calls: list[tuple[H264Encoder, H264Encoder, str]] = []
    result = run_export_attempt(
        video=tmp_path / "in.mp4",
        start=0.0,
        end=10.0,
        output=tmp_path / "out.mp4",
        codec="h264",
        encoder=H264Encoder.NVENC,
        progress_cb=lambda p, s: None,
        fallback_cb=lambda f, t, m: fallback_calls.append((f, t, m)),
        cancel_event=threading.Event(),
    )
    assert result.encoder_used == H264Encoder.LIBX264.value
    assert result.fallback_from == H264Encoder.NVENC.value
    assert len(fallback_calls) == 1
    assert fallback_calls[0][0] == H264Encoder.NVENC
    assert fallback_calls[0][1] == H264Encoder.LIBX264


# --- run_export_attempt: cancel ---


@patch("allaganeye.export.ffmpeg_runner.subprocess.Popen")
def test_run_export_attempt_cancel_event_kills_ffmpeg(
    mock_popen: MagicMock, tmp_path: Path
):
    """cancel_event が set されたら ffmpeg を kill して ExportError(kind='cancelled') raise."""
    proc = MagicMock()
    proc.stderr = MagicMock()
    proc.stderr.readline = MagicMock(return_value=b"out_time_ms=1000000\n")
    proc.wait = MagicMock(return_value=-9)  # SIGKILL
    proc.returncode = -9
    mock_popen.return_value = proc

    cancel = threading.Event()
    cancel.set()  # cancel 即時

    with pytest.raises(ExportError) as exc_info:
        run_export_attempt(
            video=tmp_path / "in.mp4",
            start=0.0,
            end=10.0,
            output=tmp_path / "out.mp4",
            codec="h264",
            encoder=H264Encoder.LIBX264,  # fallback 経路を回避
            progress_cb=lambda p, s: None,
            fallback_cb=None,
            cancel_event=cancel,
        )
    assert exc_info.value.kind == "cancelled"
    proc.kill.assert_called()


# --- run_export_attempt: libx264 retry also fails ---


@patch("allaganeye.export.ffmpeg_runner.subprocess.Popen")
def test_run_export_attempt_both_attempts_fail(mock_popen: MagicMock, tmp_path: Path):
    proc_nvenc = MagicMock()
    proc_nvenc.stderr = MagicMock()
    proc_nvenc.stderr.readline = MagicMock(
        side_effect=[
            b"[h264_nvenc @ 0xfff] No NVENC capable devices found\n",
            b"",
        ]
    )
    proc_nvenc.wait = MagicMock(return_value=1)
    proc_nvenc.returncode = 1

    proc_libx264 = MagicMock()
    proc_libx264.stderr = MagicMock()
    proc_libx264.stderr.readline = MagicMock(
        side_effect=[
            b"Error opening codec\n",
            b"",
        ]
    )
    proc_libx264.wait = MagicMock(return_value=1)
    proc_libx264.returncode = 1

    mock_popen.side_effect = [proc_nvenc, proc_libx264]

    with pytest.raises(ExportError) as exc_info:
        run_export_attempt(
            video=tmp_path / "in.mp4",
            start=0.0,
            end=10.0,
            output=tmp_path / "out.mp4",
            codec="h264",
            encoder=H264Encoder.NVENC,
            progress_cb=lambda p, s: None,
            fallback_cb=lambda f, t, m: None,
            cancel_event=threading.Event(),
        )
    assert exc_info.value.kind == "ffmpeg.exit_failed"


# --- _build_ffmpeg_args: decode hwaccel (#791) ---


def test_build_args_nvenc_inserts_hwaccel_cuda_before_input(tmp_path: Path):
    args = _build_ffmpeg_args(
        ffmpeg="ffmpeg",
        video=tmp_path / "in.mp4",
        start=0.0,
        end=10.0,
        output=tmp_path / "out.mp4",
        codec="h264",
        encoder=H264Encoder.NVENC,
    )
    # -hwaccel cuda -hwaccel_output_format cuda が連続で含まれる
    idx_hwaccel = args.index("-hwaccel")
    assert args[idx_hwaccel : idx_hwaccel + 4] == [
        "-hwaccel",
        "cuda",
        "-hwaccel_output_format",
        "cuda",
    ]
    # -i より前に置かれている (ffmpeg input flag 規則)
    idx_i = args.index("-i")
    assert idx_hwaccel < idx_i


def test_build_args_qsv_has_no_hwaccel_deferred_to_762(tmp_path: Path):
    """QSV decode hwaccel は #762 で wire 予定。現状は no-op (Codex adversarial-review #791 + Idios 判断)."""
    args = _build_ffmpeg_args(
        ffmpeg="ffmpeg",
        video=tmp_path / "in.mp4",
        start=0.0,
        end=10.0,
        output=tmp_path / "out.mp4",
        codec="h264",
        encoder=H264Encoder.QSV,
    )
    assert "-hwaccel" not in args
    assert "-hwaccel_output_format" not in args
    # QSV encoder 本体は使われる
    assert "h264_qsv" in args


def test_build_args_amf_has_no_hwaccel_deferred_to_762(tmp_path: Path):
    """AMF decode hwaccel は #762 で wire 予定。現状は no-op (Codex adversarial-review #791 + Idios 判断)."""
    args = _build_ffmpeg_args(
        ffmpeg="ffmpeg",
        video=tmp_path / "in.mp4",
        start=0.0,
        end=10.0,
        output=tmp_path / "out.mp4",
        codec="h264",
        encoder=H264Encoder.AMF,
    )
    assert "-hwaccel" not in args
    assert "-hwaccel_output_format" not in args
    # AMF encoder 本体は使われる
    assert "h264_amf" in args


def test_build_args_libx264_has_no_hwaccel(tmp_path: Path):
    args = _build_ffmpeg_args(
        ffmpeg="ffmpeg",
        video=tmp_path / "in.mp4",
        start=0.0,
        end=10.0,
        output=tmp_path / "out.mp4",
        codec="h264",
        encoder=H264Encoder.LIBX264,
    )
    # GPU->CPU memcpy 回避: libx264 path には decode hwaccel を付けない
    assert "-hwaccel" not in args
    assert "-hwaccel_output_format" not in args
    # libx264 自体は使われる
    assert "libx264" in args


def test_build_args_copy_codec_has_no_hwaccel_even_with_nvenc_encoder(
    tmp_path: Path,
):
    """codec='copy' は decode/encode しないため、encoder が NVENC でも hwaccel 不要."""
    args = _build_ffmpeg_args(
        ffmpeg="ffmpeg",
        video=tmp_path / "in.mp4",
        start=0.0,
        end=10.0,
        output=tmp_path / "out.mp4",
        codec="copy",
        encoder=H264Encoder.NVENC,
    )
    assert "-hwaccel" not in args
    assert "-hwaccel_output_format" not in args
    # -c copy が指定されている
    idx_c = args.index("-c")
    assert args[idx_c + 1] == "copy"


def test_build_args_hwaccel_positioned_before_ss_to_i(tmp_path: Path):
    """ffmpeg の -hwaccel は input flag であり -ss/-to/-i より前に置く必要がある."""
    args = _build_ffmpeg_args(
        ffmpeg="ffmpeg",
        video=tmp_path / "in.mp4",
        start=1.5,
        end=12.5,
        output=tmp_path / "out.mp4",
        codec="h264",
        encoder=H264Encoder.NVENC,
    )
    idx_hwaccel = args.index("-hwaccel")
    idx_ss = args.index("-ss")
    idx_to = args.index("-to")
    idx_i = args.index("-i")
    assert idx_hwaccel < idx_ss
    assert idx_hwaccel < idx_to
    assert idx_hwaccel < idx_i


# --- run_export_attempt: Popen argv integration tests (#791) ---


@patch("allaganeye.export.ffmpeg_runner.subprocess.Popen")
def test_run_export_attempt_nvenc_argv_includes_hwaccel_cuda(
    mock_popen: MagicMock, tmp_path: Path
):
    """run_export_attempt -> Popen に渡る argv に -hwaccel cuda が含まれる."""
    proc = MagicMock()
    proc.stderr = MagicMock()
    proc.stderr.readline = MagicMock(
        side_effect=[
            b"out_time_ms=1000000\n",
            b"progress=end\n",
            b"",
        ]
    )
    proc.wait = MagicMock(return_value=0)
    proc.returncode = 0
    mock_popen.return_value = proc

    run_export_attempt(
        video=tmp_path / "in.mp4",
        start=0.0,
        end=10.0,
        output=tmp_path / "out.mp4",
        codec="h264",
        encoder=H264Encoder.NVENC,
        progress_cb=lambda p, s: None,
        fallback_cb=None,
        cancel_event=threading.Event(),
    )
    # Popen の 1st positional arg (argv list) を取得
    first_call_args = mock_popen.call_args_list[0]
    argv = first_call_args.args[0]
    assert "-hwaccel" in argv
    idx = argv.index("-hwaccel")
    assert argv[idx : idx + 4] == [
        "-hwaccel",
        "cuda",
        "-hwaccel_output_format",
        "cuda",
    ]


@patch("allaganeye.export.ffmpeg_runner.subprocess.Popen")
def test_run_export_attempt_libx264_fallback_argv_lacks_hwaccel(
    mock_popen: MagicMock, tmp_path: Path
):
    """NVENC init fail -> libx264 retry の 2nd Popen call argv に -hwaccel なし.

    libx264 path で -hwaccel を付けると GPU->CPU memcpy が逆コストになるため、
    fallback retry では確実に decode hwaccel を外すことを担保する.
    """
    proc_nvenc = MagicMock()
    proc_nvenc.stderr = MagicMock()
    proc_nvenc.stderr.readline = MagicMock(
        side_effect=[
            b"[h264_nvenc @ 0xfff] No NVENC capable devices found\n",
            b"",
        ]
    )
    proc_nvenc.wait = MagicMock(return_value=1)
    proc_nvenc.returncode = 1

    proc_libx264 = MagicMock()
    proc_libx264.stderr = MagicMock()
    proc_libx264.stderr.readline = MagicMock(
        side_effect=[
            b"out_time_ms=1000000\n",
            b"progress=end\n",
            b"",
        ]
    )
    proc_libx264.wait = MagicMock(return_value=0)
    proc_libx264.returncode = 0

    mock_popen.side_effect = [proc_nvenc, proc_libx264]

    run_export_attempt(
        video=tmp_path / "in.mp4",
        start=0.0,
        end=10.0,
        output=tmp_path / "out.mp4",
        codec="h264",
        encoder=H264Encoder.NVENC,
        progress_cb=lambda p, s: None,
        fallback_cb=lambda f, t, m: None,
        cancel_event=threading.Event(),
    )
    # 1st call (NVENC) は hwaccel あり、2nd call (libx264 retry) は hwaccel なし
    first_argv = mock_popen.call_args_list[0].args[0]
    second_argv = mock_popen.call_args_list[1].args[0]
    assert "-hwaccel" in first_argv
    assert "-hwaccel" not in second_argv
    assert "libx264" in second_argv


@patch("allaganeye.export.ffmpeg_runner.subprocess.Popen")
def test_run_export_attempt_nvdec_decode_failure_triggers_libx264_retry(
    mock_popen: MagicMock, tmp_path: Path
):
    """#791 Codex Finding 2: NVDEC decode-stage failure (not encoder init) -> libx264 retry.

    With -hwaccel cuda routed through NVDEC, ffmpeg can fail at decode setup
    (cuvidCreateDecoder, CUDA context creation, etc.) before reaching the
    encoder. is_gpu_encoder_failure must detect these stderr patterns so
    run_export_attempt rebuilds argv without -hwaccel cuda and retries with
    libx264.

    Note: real-machine fallback behavior (actual ffmpeg argv hand-off) is
    verified via Iron Law 6 trigger (Idios RTX 5090) per spec section 5.1,
    not in this mocked test.
    """
    proc_nvenc = MagicMock()
    proc_nvenc.stderr = MagicMock()
    proc_nvenc.stderr.readline = MagicMock(
        side_effect=[
            b"[h264_cuvid @ 0xfff] cuvidCreateDecoder failed: invalid argument\n",
            b"",
        ]
    )
    proc_nvenc.wait = MagicMock(return_value=1)
    proc_nvenc.returncode = 1

    proc_libx264 = MagicMock()
    proc_libx264.stderr = MagicMock()
    proc_libx264.stderr.readline = MagicMock(
        side_effect=[
            b"out_time_ms=1000000\n",
            b"progress=end\n",
            b"",
        ]
    )
    proc_libx264.wait = MagicMock(return_value=0)
    proc_libx264.returncode = 0

    mock_popen.side_effect = [proc_nvenc, proc_libx264]

    fallback_calls: list[tuple[H264Encoder, H264Encoder, str]] = []
    result = run_export_attempt(
        video=tmp_path / "in.mp4",
        start=0.0,
        end=10.0,
        output=tmp_path / "out.mp4",
        codec="h264",
        encoder=H264Encoder.NVENC,
        progress_cb=lambda p, s: None,
        fallback_cb=lambda f, t, m: fallback_calls.append((f, t, m)),
        cancel_event=threading.Event(),
    )
    assert result.encoder_used == H264Encoder.LIBX264.value
    assert result.fallback_from == H264Encoder.NVENC.value
    assert len(fallback_calls) == 1
    # libx264 retry argv lacks -hwaccel
    second_argv = mock_popen.call_args_list[1].args[0]
    assert "-hwaccel" not in second_argv
