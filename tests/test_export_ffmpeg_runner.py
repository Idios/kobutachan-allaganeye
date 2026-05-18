"""Tests for single-attempt ffmpeg runner + libx264 fallback (#761).

Ported from gui/src-tauri/src/lib.rs::tests run_ffmpeg_export_attempt /
is_gpu_encoder_failure coverage. Heavy mocking around subprocess.Popen.
"""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from allaganeye.export.encoder import H264Encoder
from allaganeye.export.ffmpeg_runner import (
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
    """libx264 itself is the fallback target — fallback predicate is False."""
    text = "anything"
    assert not is_gpu_encoder_failure(text, H264Encoder.LIBX264)


def test_unrelated_error_not_classified_as_gpu_init():
    text = "Conversion failed!"
    assert not is_gpu_encoder_failure(text, H264Encoder.NVENC)


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
