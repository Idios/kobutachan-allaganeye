"""Tests for GPU-accelerated detection."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from allaganeye.exceptions import VideoProcessingError
from allaganeye.video.detector import _FRAME_SIZE
from allaganeye.video.gpu_detector import _decode_chunk, scan_gpu


def _make_frames(brightness_values: list[int]) -> bytes:
    """Create raw frame data for a sequence of brightness values."""
    return b"".join(bytes([b]) * _FRAME_SIZE for b in brightness_values)


class TestDecodeChunk:
    @patch("allaganeye.video.gpu_detector.subprocess.run")
    def test_parses_frames(self, mock_run):
        """Correctly parses multiple frames from stdout."""
        mock_run.return_value = MagicMock(
            stdout=_make_frames([128, 5, 200]),
            stderr=b"",
            returncode=0,
        )
        result = _decode_chunk(Path("test.mp4"), 100.0, 103.0, 1.0)

        assert len(result) == 3
        assert result[100.0] == pytest.approx(128.0)
        assert result[101.0] == pytest.approx(5.0)
        assert result[102.0] == pytest.approx(200.0)

    @patch("allaganeye.video.gpu_detector.subprocess.run")
    def test_hwaccel_in_cmd(self, mock_run):
        """ffmpeg command includes -hwaccel auto."""
        mock_run.return_value = MagicMock(stdout=b"", stderr=b"", returncode=0)
        _decode_chunk(Path("test.mp4"), 0.0, 10.0, 1.0)

        cmd = mock_run.call_args[0][0]
        assert "-hwaccel" in cmd
        assert "auto" in cmd

    @patch("allaganeye.video.gpu_detector.subprocess.run")
    def test_nonzero_returncode_raises(self, mock_run):
        mock_run.return_value = MagicMock(stdout=b"", stderr=b"error", returncode=1)
        with pytest.raises(VideoProcessingError, match="GPU decode failed"):
            _decode_chunk(Path("test.mp4"), 0.0, 10.0, 1.0)

    @patch("allaganeye.video.gpu_detector.subprocess.run")
    def test_ffmpeg_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError("ffmpeg")
        with pytest.raises(VideoProcessingError, match="ffmpeg not found"):
            _decode_chunk(Path("test.mp4"), 0.0, 10.0, 1.0)

    @patch("allaganeye.video.gpu_detector.subprocess.run")
    def test_timeout_raises(self, mock_run):
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ffmpeg", timeout=300)
        with pytest.raises(VideoProcessingError, match="timed out"):
            _decode_chunk(Path("test.mp4"), 0.0, 10.0, 1.0)

    @patch("allaganeye.video.gpu_detector.subprocess.run")
    def test_timestamps_respect_chunk_start(self, mock_run):
        """Timestamps start from chunk_start, not 0."""
        mock_run.return_value = MagicMock(
            stdout=_make_frames([100, 100]),
            stderr=b"",
            returncode=0,
        )
        result = _decode_chunk(Path("test.mp4"), 500.0, 502.0, 1.0)

        assert 500.0 in result
        assert 501.0 in result
        assert 0.0 not in result


class TestScanGpu:
    @patch("allaganeye.video.gpu_detector._decode_chunk")
    def test_collects_all_chunks(self, mock_decode):
        """Results from all chunks are merged."""
        mock_decode.return_value = {0.0: 128.0}
        result = scan_gpu(Path("test.mp4"), 10.0, 1.0, 15.0)

        assert len(result) >= 1
        assert mock_decode.call_count >= 1

    @patch("allaganeye.video.gpu_detector._decode_chunk")
    def test_gpu_failure_raises(self, mock_decode):
        """GPU failure raises VideoProcessingError for fallback."""
        mock_decode.side_effect = VideoProcessingError("GPU decode failed")

        with pytest.raises(VideoProcessingError, match="falling back"):
            scan_gpu(Path("test.mp4"), 10.0, 1.0, 15.0)

    @patch("allaganeye.video.gpu_detector._decode_chunk")
    def test_gpu_failure_cancels_pending_futures(self, mock_decode):
        """GPU failure cancels pending futures via shutdown(cancel_futures=True)."""
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise VideoProcessingError("GPU decode failed")
            return {0.0: 128.0}

        mock_decode.side_effect = side_effect

        with pytest.raises(VideoProcessingError, match="falling back"):
            scan_gpu(Path("test.mp4"), 100.0, 1.0, 15.0)

        # With cancel_futures=True, not all chunks should have been executed
        # (some were cancelled before starting)
        assert call_count < min(os.cpu_count() or 4, 16)

    @patch("allaganeye.video.gpu_detector._decode_chunk")
    def test_progress_callback(self, mock_decode):
        """Progress callback is invoked."""
        mock_decode.return_value = {0.0: 128.0, 1.0: 5.0}
        calls: list[tuple] = []

        scan_gpu(
            Path("test.mp4"),
            10.0,
            1.0,
            15.0,
            progress_callback=lambda c, t, bc: calls.append((c, t, bc)),
        )

        assert len(calls) >= 1


class TestGpuFallbackIntegration:
    @patch("allaganeye.video.detector._scan_cpu")
    @patch("allaganeye.video.gpu_detector.scan_gpu")
    def test_fallback_to_cpu(self, mock_gpu, mock_cpu):
        """GPU failure triggers CPU fallback in detect_match_boundaries."""
        from allaganeye.video.detector import detect_match_boundaries

        mock_gpu.side_effect = VideoProcessingError("GPU failed")
        mock_cpu.return_value = {0.0: 128.0, 100.0: 128.0, 200.0: 128.0}

        result = detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=300.0,
            min_match_duration=100.0,
            use_gpu=True,
        )

        mock_gpu.assert_called_once()
        mock_cpu.assert_called_once()
        assert len(result) >= 1
