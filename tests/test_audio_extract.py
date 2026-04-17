"""Tests for allaganeye.audio.extract module."""

import subprocess
from unittest.mock import patch

import numpy as np
import pytest

from allaganeye.audio.extract import extract_pcm
from allaganeye.exceptions import VideoProcessingError


def _mock_result(stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0):
    return subprocess.CompletedProcess(
        args=["ffmpeg"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def _silence_pcm(samples: int) -> bytes:
    return np.zeros(samples, dtype=np.int16).tobytes()


@patch("allaganeye.audio.extract.subprocess.run")
@patch("allaganeye.audio.extract.find_ffmpeg", return_value="ffmpeg")
def test_extract_pcm_returns_float32_array(_mock_ffmpeg, mock_run, tmp_path):
    """Normal extraction returns float32 PCM in [-1, 1]."""
    video = tmp_path / "test.mp4"
    video.touch()
    samples = np.array([0, 16384, -16384, 32767], dtype=np.int16)
    mock_run.return_value = _mock_result(stdout=samples.tobytes())

    pcm = extract_pcm(video)

    assert pcm.dtype == np.float32
    assert pcm.shape == (4,)
    assert pcm[0] == 0.0
    assert pcm[1] == pytest.approx(0.5, abs=1e-3)
    assert pcm[2] == pytest.approx(-0.5, abs=1e-3)


@patch("allaganeye.audio.extract.subprocess.run")
@patch("allaganeye.audio.extract.find_ffmpeg", return_value="ffmpeg")
def test_extract_pcm_passes_start_and_duration(_mock_ffmpeg, mock_run, tmp_path):
    """start and duration arguments are forwarded to ffmpeg."""
    video = tmp_path / "test.mp4"
    video.touch()
    mock_run.return_value = _mock_result(stdout=_silence_pcm(100))

    extract_pcm(video, sample_rate=16000, start=12.5, duration=3.0)

    cmd = mock_run.call_args.args[0]
    assert "-ss" in cmd
    assert cmd[cmd.index("-ss") + 1] == "12.5"
    assert "-t" in cmd
    assert cmd[cmd.index("-t") + 1] == "3.0"
    assert "-ar" in cmd
    assert cmd[cmd.index("-ar") + 1] == "16000"


@patch("allaganeye.audio.extract.subprocess.run")
@patch("allaganeye.audio.extract.find_ffmpeg", return_value="ffmpeg")
def test_extract_pcm_omits_seek_args_when_unset(_mock_ffmpeg, mock_run, tmp_path):
    """When start/duration are None, -ss and -t are not in the command."""
    video = tmp_path / "test.mp4"
    video.touch()
    mock_run.return_value = _mock_result(stdout=_silence_pcm(100))

    extract_pcm(video)

    cmd = mock_run.call_args.args[0]
    assert "-ss" not in cmd
    assert "-t" not in cmd


@patch("allaganeye.audio.extract.subprocess.run")
@patch("allaganeye.audio.extract.find_ffmpeg", return_value="ffmpeg")
def test_extract_pcm_ffmpeg_not_found(_mock_ffmpeg, mock_run, tmp_path):
    """FileNotFoundError -> VideoProcessingError with helpful message."""
    video = tmp_path / "test.mp4"
    video.touch()
    mock_run.side_effect = FileNotFoundError()

    with pytest.raises(VideoProcessingError, match="ffmpeg not found"):
        extract_pcm(video)


@patch("allaganeye.audio.extract.subprocess.run")
@patch("allaganeye.audio.extract.find_ffmpeg", return_value="ffmpeg")
def test_extract_pcm_timeout(_mock_ffmpeg, mock_run, tmp_path):
    """TimeoutExpired -> VideoProcessingError."""
    video = tmp_path / "test.mp4"
    video.touch()
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="ffmpeg", timeout=1800)

    with pytest.raises(VideoProcessingError, match="timed out"):
        extract_pcm(video)


@patch("allaganeye.audio.extract.subprocess.run")
@patch("allaganeye.audio.extract.find_ffmpeg", return_value="ffmpeg")
def test_extract_pcm_nonzero_returncode(_mock_ffmpeg, mock_run, tmp_path):
    """Non-zero ffmpeg return code -> VideoProcessingError including stderr tail."""
    video = tmp_path / "test.mp4"
    video.touch()
    mock_run.return_value = _mock_result(returncode=1, stderr=b"some ffmpeg error here")

    with pytest.raises(VideoProcessingError) as exc_info:
        extract_pcm(video)
    # stderr tail is now on .context (verbose detail), not the message (#351)
    assert "some ffmpeg error here" in exc_info.value.context["stderr_tail"]


@patch("allaganeye.audio.extract.subprocess.run")
@patch("allaganeye.audio.extract.find_ffmpeg", return_value="ffmpeg")
def test_extract_pcm_empty_output(_mock_ffmpeg, mock_run, tmp_path):
    """Empty stdout (no audio track) -> VideoProcessingError."""
    video = tmp_path / "test.mp4"
    video.touch()
    mock_run.return_value = _mock_result(stdout=b"")

    with pytest.raises(VideoProcessingError, match="No audio data"):
        extract_pcm(video)
