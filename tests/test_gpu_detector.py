"""Tests for GPU-accelerated detection."""

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
        result, stderr = _decode_chunk(Path("test.mp4"), 100.0, 103.0, 1.0)

        assert len(result) == 3
        assert result[100.0] == pytest.approx(128.0)
        assert result[101.0] == pytest.approx(5.0)
        assert result[102.0] == pytest.approx(200.0)
        assert isinstance(stderr, str)

    @patch("allaganeye.video.gpu_detector.subprocess.run")
    def test_hwaccel_auto_when_no_codec(self, mock_run):
        """ffmpeg command includes -hwaccel auto when codec is unknown."""
        mock_run.return_value = MagicMock(stdout=b"", stderr=b"", returncode=0)
        _decode_chunk(Path("test.mp4"), 0.0, 10.0, 1.0)

        cmd = mock_run.call_args[0][0]
        assert "-hwaccel" in cmd
        assert "auto" in cmd

    @patch("allaganeye.video.gpu_detector.subprocess.run")
    def test_hwaccel_cuda_with_known_codec(self, mock_run):
        """ffmpeg command uses -hwaccel cuda -c:v av1_cuvid for AV1."""
        mock_run.return_value = MagicMock(stdout=b"", stderr=b"", returncode=0)
        _decode_chunk(Path("test.mp4"), 0.0, 10.0, 1.0, codec="av1")

        cmd = mock_run.call_args[0][0]
        assert "-hwaccel" in cmd
        cuda_idx = cmd.index("-hwaccel")
        assert cmd[cuda_idx + 1] == "cuda"
        assert "-c:v" in cmd
        cv_idx = cmd.index("-c:v")
        assert cmd[cv_idx + 1] == "av1_cuvid"

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
        result, _ = _decode_chunk(Path("test.mp4"), 500.0, 502.0, 1.0)

        assert 500.0 in result
        assert 501.0 in result
        assert 0.0 not in result


class TestScanGpu:
    @patch("allaganeye.video.gpu_detector._decode_chunk")
    def test_collects_all_chunks(self, mock_decode):
        """Results from all chunks are merged."""
        mock_decode.return_value = ({0.0: 128.0}, "")
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
        """GPU failure triggers shutdown(cancel_futures=True) and raises.

        Uses threading.Event to synchronize mock chunks: the first chunk
        raises immediately while subsequent chunks block until released.
        This prevents the timing-dependent flakiness of the original test
        where fast mock completion could race with cancellation (#299).

        Note: since scan_gpu uses max_workers == num_chunks, all futures
        start immediately and cancel_futures has no pending futures to
        cancel.  The test verifies the error propagation path works
        correctly under concurrent conditions.
        """
        import threading

        lock = threading.Lock()
        call_order = 0
        release = threading.Event()

        def side_effect(*args, **kwargs):
            nonlocal call_order
            with lock:
                call_order += 1
                my_order = call_order
            if my_order == 1:
                raise VideoProcessingError("GPU decode failed")
            # Block subsequent chunks until released after scan_gpu returns.
            # Short timeout prevents test hang if release is not set.
            release.wait(timeout=2)
            return ({0.0: 128.0}, "")

        mock_decode.side_effect = side_effect

        with pytest.raises(VideoProcessingError, match="falling back"):
            scan_gpu(Path("test.mp4"), 100.0, 1.0, 15.0)

        # Release blocked threads so ThreadPoolExecutor can shut down cleanly
        release.set()

        # Verify the error propagated and no results were returned.
        # The assertion above (pytest.raises) confirms scan_gpu raised
        # without returning partial results from other chunks.

    @patch("allaganeye.video.gpu_detector._decode_chunk")
    def test_progress_callback(self, mock_decode):
        """Progress callback is invoked."""
        mock_decode.return_value = ({0.0: 128.0, 1.0: 5.0}, "")
        calls: list[tuple] = []

        scan_gpu(
            Path("test.mp4"),
            10.0,
            1.0,
            15.0,
            progress_callback=lambda c, t, bc: calls.append((c, t, bc)),
        )

        assert len(calls) >= 1

    @patch("allaganeye.video.gpu_detector._decode_chunk")
    def test_chunk_progress_callback_fires_per_chunk(self, mock_decode):
        """chunk_progress_callback fires once per chunk with (done, total, eta) (#333)."""
        mock_decode.return_value = ({0.0: 128.0, 1.0: 5.0}, "")
        chunk_calls: list[tuple[int, int, float]] = []

        scan_gpu(
            Path("test.mp4"),
            10.0,
            1.0,
            15.0,
            chunk_progress_callback=lambda d, t, eta: chunk_calls.append((d, t, eta)),
        )

        # One call per chunk -- exactly num_chunks total (lead review).
        assert len(chunk_calls) >= 1
        num_chunks = chunk_calls[-1][1]
        assert len(chunk_calls) == num_chunks
        # done is monotonically increasing 1..num_chunks
        dones = [c[0] for c in chunk_calls]
        assert dones == list(range(1, num_chunks + 1))
        # total stays constant at num_chunks
        assert all(c[1] == num_chunks for c in chunk_calls)
        # Final ETA is 0 (no remaining chunks)
        assert chunk_calls[-1][2] == 0.0
        # Intermediate ETAs are non-negative
        assert all(c[2] >= 0 for c in chunk_calls)

    @patch("allaganeye.video.gpu_detector._decode_chunk")
    def test_chunk_progress_not_called_on_failure(self, mock_decode):
        """Callback must not fire for a failed chunk (#333)."""
        mock_decode.side_effect = VideoProcessingError("fail")
        chunk_calls: list[tuple[int, int, float]] = []

        with pytest.raises(VideoProcessingError):
            scan_gpu(
                Path("test.mp4"),
                10.0,
                1.0,
                15.0,
                chunk_progress_callback=lambda d, t, eta: chunk_calls.append(
                    (d, t, eta)
                ),
            )
        assert chunk_calls == []

    # ------------------------------------------------------------
    # Chunk boundaries aligned to sample grid (#392)
    # ------------------------------------------------------------

    @patch("allaganeye.video.gpu_detector._decode_chunk")
    def test_chunk_starts_aligned_to_sample_interval(self, mock_decode):
        """All chunk_starts are multiples of sample_interval (#392).

        Without alignment, ``chunk_start = i * (duration / num_chunks)``
        lands on arbitrary floats; ffmpeg's ``fps=1/interval`` filter
        then emits frames at ``chunk_start + k*interval`` off-grid, so
        GPU timestamps diverge from ``_scan_cpu``'s global grid.  After
        the fix, every dispatched chunk starts at a multiple of
        sample_interval, which keeps GPU and CPU output keyed identically.
        """
        mock_decode.return_value = ({}, "")
        scan_gpu(Path("test.mp4"), 10228.7, 3.0, 15.0)

        # Extract chunk_start from each dispatched ffmpeg call.
        chunk_starts = [call.args[1] for call in mock_decode.call_args_list]
        assert chunk_starts, "no chunks dispatched"
        for cs in chunk_starts:
            remainder = cs - round(cs / 3.0) * 3.0
            assert abs(remainder) < 1e-6, (
                f"chunk_start={cs} not aligned to sample_interval=3.0 "
                f"(remainder={remainder})"
            )

    @patch("allaganeye.video.gpu_detector._decode_chunk")
    def test_chunks_cover_full_duration_without_overlap(self, mock_decode):
        """Adjacent chunks tile the timeline without gaps or overlap (#392).

        After grid snapping, chunks may merge or collapse, but the union
        of ``[chunk_start, chunk_end)`` ranges must still cover the whole
        video duration, and no frame should be decoded by two chunks
        (which would produce duplicate dict keys at the boundary).
        """
        mock_decode.return_value = ({}, "")
        scan_gpu(Path("test.mp4"), 1000.0, 3.0, 15.0)

        ranges = [(call.args[1], call.args[2]) for call in mock_decode.call_args_list]
        ranges.sort()
        assert ranges, "no chunks dispatched"
        assert ranges[0][0] == 0.0, f"first chunk should start at 0, got {ranges[0][0]}"
        assert ranges[-1][1] == 1000.0, (
            f"last chunk should end at duration, got {ranges[-1][1]}"
        )
        for i in range(len(ranges) - 1):
            prev_end = ranges[i][1]
            next_start = ranges[i + 1][0]
            assert prev_end <= next_start, f"chunks overlap: {prev_end} > {next_start}"
            # Boundary points are shared, but timestamp-filter uses
            # ``< chunk_end`` so the frame at the boundary is counted
            # exactly once (in the next chunk).

    @patch("allaganeye.video.gpu_detector._decode_chunk")
    def test_chunk_count_reported_via_callback_matches_dispatched(self, mock_decode):
        """Progress callback's ``total`` equals actually-dispatched chunks (#392).

        Regression guard for the original 16 vs 10 mismatch when grid
        snapping collapses degenerate chunks.
        """
        mock_decode.return_value = ({0.0: 128.0}, "")
        chunk_calls: list[tuple[int, int, float]] = []

        scan_gpu(
            Path("test.mp4"),
            10.0,
            3.0,
            15.0,
            chunk_progress_callback=lambda d, t, eta: chunk_calls.append((d, t, eta)),
        )

        # Total from last callback must equal number of actual dispatches.
        assert chunk_calls
        total_reported = chunk_calls[-1][1]
        assert total_reported == mock_decode.call_count, (
            f"callback total={total_reported}, actual={mock_decode.call_count}"
        )


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
