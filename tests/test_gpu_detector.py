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


# Two grid timestamps is enough for every cmd-shape assertion below.
_GRID = [0.0, 5.0]
_FPS_KWARGS = {"source_fps_num": 60, "source_fps_den": 1, "is_tail_chunk": False}


def _popen_mock(mock_popen, stdout_bytes: bytes | None = None, returncode: int = 0):
    """Wire a ``subprocess.Popen`` mock for the select-filter decode path.

    #864 removed the fps-filter path (which used ``subprocess.run``), so the
    direct ``_decode_chunk`` unit tests below drive the select-filter path.

    The default stream emits exactly ``len(_GRID)`` frames rather than ``b""``.
    An empty stream would still satisfy the dynamic VFR check (its slack at
    60fps is ``ceil(60 * 0.1)`` = 6 frames, well above a 2-frame grid), so a
    cmd-shape test built on ``b""`` would pass without the sampling contract
    ever being exercised (Codex adversarial-review, #864). Tests that need a
    specific stream still pass one explicitly.
    """
    import io

    if stdout_bytes is None:
        stdout_bytes = _make_frames([0] * len(_GRID))

    proc = MagicMock()
    proc.stdout = io.BytesIO(stdout_bytes)
    proc.stderr = io.BytesIO(b"")
    proc.wait.return_value = returncode
    proc.returncode = returncode
    mock_popen.return_value.__enter__.return_value = proc
    return proc


class TestDecodeChunk:
    """``_decode_chunk`` vendor/decoder resolution on the select-filter path.

    Pre-#864 these ran through ``_decode_chunk_legacy``; the resolution logic
    they pin (``_GPU_DECODER_MAP`` / ``_VENDOR_HWACCEL_MAP`` /
    ``_HWACCELS_NEED_HWDOWNLOAD`` + hwdownload prefix) is identical in
    ``_decode_chunk_v2``, so the coverage is retargeted rather than dropped.
    """

    @patch("allaganeye.video.gpu_detector.subprocess.Popen")
    def test_parses_frames(self, mock_popen):
        """Correctly parses multiple frames from stdout."""
        _popen_mock(mock_popen, _make_frames([128, 5, 200]))
        result, stderr = _decode_chunk(
            Path("test.mp4"),
            100.0,
            103.0,
            1.0,
            chunk_timestamps=[100.0, 101.0, 102.0],
            **_FPS_KWARGS,
        )

        assert len(result) == 3
        assert result[100.0] == pytest.approx(128.0)
        assert result[101.0] == pytest.approx(5.0)
        assert result[102.0] == pytest.approx(200.0)
        assert isinstance(stderr, str)

    @patch("allaganeye.video.gpu_detector.subprocess.Popen")
    def test_hwaccel_auto_when_no_codec(self, mock_popen):
        """ffmpeg command includes -hwaccel auto when codec is unknown."""
        _popen_mock(mock_popen)
        _decode_chunk(
            Path("test.mp4"), 0.0, 10.0, 1.0, chunk_timestamps=_GRID, **_FPS_KWARGS
        )

        cmd = mock_popen.call_args[0][0]
        assert "-hwaccel" in cmd
        assert "auto" in cmd

    @patch("allaganeye.video.gpu_detector.subprocess.Popen")
    def test_hwaccel_cuda_with_known_codec(self, mock_popen):
        """ffmpeg command uses -hwaccel cuda -c:v av1_cuvid for AV1."""
        _popen_mock(mock_popen)
        _decode_chunk(
            Path("test.mp4"),
            0.0,
            10.0,
            1.0,
            codec="av1",
            chunk_timestamps=_GRID,
            **_FPS_KWARGS,
        )

        cmd = mock_popen.call_args[0][0]
        assert "-hwaccel" in cmd
        cuda_idx = cmd.index("-hwaccel")
        assert cmd[cuda_idx + 1] == "cuda"
        assert "-c:v" in cmd
        cv_idx = cmd.index("-c:v")
        assert cmd[cv_idx + 1] == "av1_cuvid"

    @patch("allaganeye.video.gpu_detector.subprocess.Popen")
    def test_hwaccel_auto_for_vp9_codec(self, mock_popen):
        """VP9 は #538 で NVIDIA cuvid を強制しない (vendor=None path).

        ffmpeg 8.1 の vp9_cuvid は nv12+csp:gbr を出力し swscaler gray 変換が
        EOPNOTSUPP で失敗するため、NVIDIA dict から vp9 を除外。
        codec=vp9, vendor=None では else branch に落ち、``-hwaccel auto``
        で動作する。`-c:v vp9_cuvid` は cmd に含まれない。
        AMD AMF 経路は別 test (#546) で vp9_amf が使えることを検証。
        """
        _popen_mock(mock_popen)
        _decode_chunk(
            Path("test.mp4"),
            0.0,
            10.0,
            1.0,
            codec="vp9",
            chunk_timestamps=_GRID,
            **_FPS_KWARGS,
        )

        cmd = mock_popen.call_args[0][0]
        assert "-hwaccel" in cmd
        hw_idx = cmd.index("-hwaccel")
        assert cmd[hw_idx + 1] == "auto", (
            f"Expected -hwaccel auto for vp9 (soft decode fallback), "
            f"got -hwaccel {cmd[hw_idx + 1]}"
        )
        assert "vp9_cuvid" not in cmd, "vp9_cuvid must not appear in ffmpeg args (#538)"

    @patch("allaganeye.video.gpu_detector.subprocess.Popen")
    def test_hwaccel_cuda_for_nvidia_explicit_vendor(self, mock_popen):
        """vendor=nvidia 明示時も既存挙動を維持 (#546 回帰防止)."""
        _popen_mock(mock_popen)
        _decode_chunk(
            Path("test.mp4"),
            0.0,
            10.0,
            1.0,
            codec="av1",
            vendor="nvidia",
            chunk_timestamps=_GRID,
            **_FPS_KWARGS,
        )

        cmd = mock_popen.call_args[0][0]
        hw_idx = cmd.index("-hwaccel")
        assert cmd[hw_idx + 1] == "cuda"
        cv_idx = cmd.index("-c:v")
        assert cmd[cv_idx + 1] == "av1_cuvid"
        # NVIDIA は -hwaccel_output_format を指定しない (cuvid が default
        # で nv12 system memory 出力するため不要)。Intel との挙動差
        # を回帰防止する (#550)。
        assert "-hwaccel_output_format" not in cmd

    @pytest.mark.parametrize(
        ("codec", "expected_decoder"),
        [
            ("av1", "av1_qsv"),
            ("hevc", "hevc_qsv"),
            ("h264", "h264_qsv"),
            # #582 で追加。vp9_qsv は ffmpeg 8.1 に存在し、Tiger Lake
            # 以降で QSV decode 対応 (実機 i7-1185G7 / Iris Xe で 8.29x
            # speed @ 720p 確認)。NVIDIA vp9_cuvid (#538/#549 で除外) と
            # 異なり QSV では csp:gbr 問題は発生せず、hwdownload 経由で
            # 後段の select/scale/format=gray と整合する。
            ("vp9", "vp9_qsv"),
        ],
    )
    @patch("allaganeye.video.gpu_detector.subprocess.Popen")
    def test_hwaccel_qsv_for_intel_codecs(self, mock_popen, codec, expected_decoder):
        """vendor=intel + codec で `-hwaccel qsv -hwaccel_output_format qsv
        -c:v {codec}_qsv` + `hwdownload,format=nv12,` filter prefix を
        組み立てる (#550 / #582, #553 と同じ汎用機構を再利用).

        QSV decoder は default で `pix_fmt=qsv` の GPU surface を出力し、
        後段の swscaler (`select -> scale -> format=gray`) が `Function not
        implemented (-40)` で失敗する。`_HWACCELS_NEED_HWDOWNLOAD` に
        "qsv" を加え、`-hwaccel_output_format qsv` で surface format を
        明示しつつ filter chain 先頭の `hwdownload,format=nv12,` で
        system memory に降ろすのが #550 実装の核心 (#553 の AMD d3d11va
        と同じパターン)。VP9 (#582) は同パターンで追加。

        実機検証 (i7-1185G7 / Iris Xe Graphics, ffmpeg 8.1):
        - h264_qsv: 13.7x speed (`-hwaccel_output_format qsv` + hwdownload)
        - hevc_qsv: 3.76x speed @ 720p
        - vp9_qsv: 8.29x speed @ 720p (#582)
        - av1_qsv: Tiger Lake 非対応 -> VideoProcessingError -> CPU fallback
        """
        _popen_mock(mock_popen)
        _decode_chunk(
            Path("test.mp4"),
            0.0,
            10.0,
            1.0,
            codec=codec,
            vendor="intel",
            chunk_timestamps=_GRID,
            **_FPS_KWARGS,
        )

        cmd = mock_popen.call_args[0][0]
        hw_idx = cmd.index("-hwaccel")
        assert cmd[hw_idx + 1] == "qsv"
        out_idx = cmd.index("-hwaccel_output_format")
        assert cmd[out_idx + 1] == "qsv", (
            "-hwaccel_output_format qsv で surface format を hwaccel に揃え、"
            "hwdownload filter で system memory へ降ろす (#550)"
        )
        cv_idx = cmd.index("-c:v")
        assert cmd[cv_idx + 1] == expected_decoder
        # 引数順序: -hwaccel qsv -hwaccel_output_format qsv -c:v ...
        # ffmpeg の input option は -i より前に並ぶ必要がある。
        assert hw_idx < out_idx < cv_idx
        i_idx = cmd.index("-i")
        assert cv_idx < i_idx
        # filter graph 先頭で system memory に降ろす (#553 と同じパターン)
        vf_idx = cmd.index("-vf")
        assert cmd[vf_idx + 1].startswith("hwdownload,format=nv12,"), (
            "qsv decode 出力 (GPU surface) を hwdownload で system memory に "
            "降ろさないと swscaler が pix_fmt=qsv を扱えず失敗する (#550)"
        )

    @patch("allaganeye.video.gpu_detector.subprocess.Popen")
    def test_hwaccel_auto_for_intel_unsupported_codec(self, mock_popen):
        """vendor=intel + `_GPU_DECODER_MAP["intel"]` 未登録 codec
        (mpeg2video / mpeg4 / vc1 等) は `-hwaccel auto` に fallback
        (#550 / #582).

        現時点で Intel 用 dict は h264 / hevc / vp9 / av1 を登録。それ以外の
        codec (例: mpeg2video / mpeg4) は QSV decoder (`mpeg2_qsv` / `vc1_qsv`)
        が ffmpeg に存在しても `_GPU_DECODER_MAP["intel"]` には未登録のため
        `-hwaccel auto` に落ち、ffmpeg 側で soft / 自動 hwaccel decode が
        選ばれる。VP9 は #582 で intel dict に登録済みなので、本テストは
        mpeg2video で代替。
        """
        _popen_mock(mock_popen)
        _decode_chunk(
            Path("test.mp4"),
            0.0,
            10.0,
            1.0,
            codec="mpeg2video",
            vendor="intel",
            chunk_timestamps=_GRID,
            **_FPS_KWARGS,
        )

        cmd = mock_popen.call_args[0][0]
        hw_idx = cmd.index("-hwaccel")
        assert cmd[hw_idx + 1] == "auto"
        assert "mpeg2_qsv" not in cmd
        assert "-hwaccel_output_format" not in cmd

    @patch("allaganeye.video.gpu_detector.subprocess.Popen")
    def test_hwaccel_d3d11va_for_amd_av1(self, mock_popen):
        """vendor=amd で AV1 は d3d11va + native av1 decoder + hwdownload (#553)."""
        _popen_mock(mock_popen)
        _decode_chunk(
            Path("test.mp4"),
            0.0,
            10.0,
            1.0,
            codec="av1",
            vendor="amd",
            chunk_timestamps=_GRID,
            **_FPS_KWARGS,
        )

        cmd = mock_popen.call_args[0][0]
        hw_idx = cmd.index("-hwaccel")
        assert cmd[hw_idx + 1] == "d3d11va"
        # AMD は AMF decoder ではなく native decoder + d3d11va wrapping
        cv_idx = cmd.index("-c:v")
        assert cmd[cv_idx + 1] == "av1"
        assert "av1_amf" not in cmd
        # surface format を明示して hwdownload と整合
        of_idx = cmd.index("-hwaccel_output_format")
        assert cmd[of_idx + 1] == "d3d11"
        # filter graph 先頭で system memory に降ろす
        vf_idx = cmd.index("-vf")
        assert cmd[vf_idx + 1].startswith("hwdownload,format=nv12,")

    @patch("allaganeye.video.gpu_detector.subprocess.Popen")
    def test_hwaccel_d3d11va_for_amd_h264(self, mock_popen):
        """vendor=amd / codec=h264 でも d3d11va 経路 (#553)."""
        _popen_mock(mock_popen)
        _decode_chunk(
            Path("test.mp4"),
            0.0,
            10.0,
            1.0,
            codec="h264",
            vendor="amd",
            chunk_timestamps=_GRID,
            **_FPS_KWARGS,
        )

        cmd = mock_popen.call_args[0][0]
        hw_idx = cmd.index("-hwaccel")
        assert cmd[hw_idx + 1] == "d3d11va"
        cv_idx = cmd.index("-c:v")
        assert cmd[cv_idx + 1] == "h264"
        assert "h264_amf" not in cmd

    @patch("allaganeye.video.gpu_detector.subprocess.Popen")
    def test_hwaccel_d3d11va_for_amd_hevc(self, mock_popen):
        """vendor=amd / codec=hevc でも d3d11va 経路 (#553)."""
        _popen_mock(mock_popen)
        _decode_chunk(
            Path("test.mp4"),
            0.0,
            10.0,
            1.0,
            codec="hevc",
            vendor="amd",
            chunk_timestamps=_GRID,
            **_FPS_KWARGS,
        )

        cmd = mock_popen.call_args[0][0]
        hw_idx = cmd.index("-hwaccel")
        assert cmd[hw_idx + 1] == "d3d11va"
        cv_idx = cmd.index("-c:v")
        assert cmd[cv_idx + 1] == "hevc"

    @patch("allaganeye.video.gpu_detector.subprocess.Popen")
    def test_nvidia_path_skips_hwdownload(self, mock_popen):
        """NVIDIA cuvid 経路は hwdownload prefix を付けない (#553 / #550 回帰防止).

        cuvid decoder は decode 結果を nv12 system memory に直接出力する
        ため、d3d11va / qsv のような hwdownload は不要。filter chain 先頭が
        ``select=`` で始まることを確認 (#864 で ``fps=`` 起点の legacy path
        は撤去済み)。
        """
        _popen_mock(mock_popen)
        _decode_chunk(
            Path("test.mp4"),
            0.0,
            10.0,
            1.0,
            codec="av1",
            vendor="nvidia",
            chunk_timestamps=_GRID,
            **_FPS_KWARGS,
        )

        cmd = mock_popen.call_args[0][0]
        assert "-hwaccel_output_format" not in cmd
        vf_idx = cmd.index("-vf")
        assert cmd[vf_idx + 1].startswith("select="), (
            "NVIDIA cuvid path must not include hwdownload prefix"
        )

    @patch("allaganeye.video.gpu_detector.subprocess.Popen")
    def test_unknown_vendor_falls_back_to_hwaccel_auto(self, mock_popen):
        """`_VENDOR_HWACCEL_MAP` 未定義の vendor 名は `-hwaccel auto` に
        fallback する (#546 / #553 / #550 回帰防止 + 将来追加忘れガード).

        現在 nvidia / amd / intel は全て実装済みなので config 層で先に
        validation される。本テストは将来新 vendor を `_VENDOR_HWACCEL_MAP`
        に登録し忘れたケースに備えた防御。
        """
        _popen_mock(mock_popen)
        _decode_chunk(
            Path("test.mp4"),
            0.0,
            10.0,
            1.0,
            codec="av1",
            vendor="apple",  # not in _VENDOR_HWACCEL_MAP
            chunk_timestamps=_GRID,
            **_FPS_KWARGS,
        )
        cmd = mock_popen.call_args[0][0]
        hw_idx = cmd.index("-hwaccel")
        assert cmd[hw_idx + 1] == "auto", (
            f"unknown vendor should fall back to -hwaccel auto, "
            f"got -hwaccel {cmd[hw_idx + 1]}"
        )
        assert "av1_qsv" not in cmd
        assert "av1_amf" not in cmd
        assert "av1_cuvid" not in cmd
        assert "-hwaccel_output_format" not in cmd

    def test_select_gpu_vendor_auto_returns_implemented_vendor(self):
        """auto 選択は preference 順に _VENDOR_HWACCEL_MAP 登録済みの
        vendor を返す (#546 / #553 / #550).

        nvidia / amd / intel すべて実装済み。dual / triple GPU 環境では
        `_VENDOR_PREFERENCE` (nvidia > amd > intel) に従い、最も優先度の
        高い vendor が選ばれる。
        """
        from allaganeye.video.gpu_detector import _select_gpu_vendor

        # NVIDIA が available にあれば最優先
        assert _select_gpu_vendor(None, ["nvidia", "amd"]) == "nvidia"
        assert _select_gpu_vendor("auto", ["nvidia", "amd"]) == "nvidia"
        assert _select_gpu_vendor(None, ["nvidia", "intel"]) == "nvidia"
        assert _select_gpu_vendor(None, ["nvidia", "amd", "intel"]) == "nvidia"
        # NVIDIA 不在で AMD があれば AMD (#553)
        assert _select_gpu_vendor(None, ["amd", "intel"]) == "amd"
        assert _select_gpu_vendor(None, ["amd"]) == "amd"
        # AMD / NVIDIA 不在で Intel があれば Intel (#550)
        assert _select_gpu_vendor(None, ["intel"]) == "intel"
        assert _select_gpu_vendor("auto", ["intel"]) == "intel"
        # 何も無い -> None
        assert _select_gpu_vendor(None, []) is None

    def test_select_gpu_vendor_explicit_nvidia_match(self):
        """explicit nvidia request が available に含まれれば返す (#546)."""
        from allaganeye.video.gpu_detector import _select_gpu_vendor

        assert _select_gpu_vendor("nvidia", ["nvidia"]) == "nvidia"
        assert _select_gpu_vendor("nvidia", ["nvidia", "amd"]) == "nvidia"

    def test_select_gpu_vendor_explicit_intel_match(self):
        """explicit intel request が available に含まれれば返す (#550)."""
        from allaganeye.video.gpu_detector import _select_gpu_vendor

        assert _select_gpu_vendor("intel", ["intel"]) == "intel"
        assert _select_gpu_vendor("intel", ["nvidia", "intel"]) == "intel"

    def test_select_gpu_vendor_explicit_unavailable_returns_none(self):
        """explicit vendor が available に無い場合は None (#546 / #553 / #550).

        実装済み (nvidia / amd / intel) のいずれを explicit 指定しても、
        probe で見つからなければ None を返す。実行時は _resolve_gpu_mode が
        ConfigValidationError で落とす仕組み。
        """
        from allaganeye.video.gpu_detector import _select_gpu_vendor

        assert _select_gpu_vendor("nvidia", ["amd"]) is None
        assert _select_gpu_vendor("intel", ["nvidia"]) is None
        # AMD は #553 で _VENDOR_HWACCEL_MAP=d3d11va として実装済み
        assert _select_gpu_vendor("amd", ["amd", "nvidia"]) == "amd"
        assert _select_gpu_vendor("amd", ["nvidia"]) is None

    @patch("allaganeye.video.gpu_detector.subprocess.Popen")
    def test_nonzero_returncode_raises(self, mock_popen):
        _popen_mock(mock_popen, b"", returncode=1)
        with pytest.raises(VideoProcessingError, match="GPU decode v2 failed"):
            _decode_chunk(
                Path("test.mp4"), 0.0, 10.0, 1.0, chunk_timestamps=_GRID, **_FPS_KWARGS
            )

    @patch("allaganeye.video.gpu_detector.subprocess.Popen")
    def test_ffmpeg_not_found(self, mock_popen):
        mock_popen.side_effect = FileNotFoundError("ffmpeg")
        with pytest.raises(VideoProcessingError, match="ffmpeg not found"):
            _decode_chunk(
                Path("test.mp4"), 0.0, 10.0, 1.0, chunk_timestamps=_GRID, **_FPS_KWARGS
            )

    @patch("allaganeye.video.gpu_detector.subprocess.Popen")
    def test_timeout_raises(self, mock_popen):
        import subprocess

        proc = _popen_mock(mock_popen)
        proc.wait.side_effect = subprocess.TimeoutExpired(cmd="ffmpeg", timeout=300)
        with pytest.raises(VideoProcessingError, match="timed out"):
            _decode_chunk(
                Path("test.mp4"), 0.0, 10.0, 1.0, chunk_timestamps=_GRID, **_FPS_KWARGS
            )

    @patch("allaganeye.video.gpu_detector.subprocess.Popen")
    def test_timestamps_respect_chunk_start(self, mock_popen):
        """Timestamps start from chunk_start, not 0."""
        _popen_mock(mock_popen, _make_frames([100, 100]))
        result, _ = _decode_chunk(
            Path("test.mp4"),
            500.0,
            502.0,
            1.0,
            chunk_timestamps=[500.0, 501.0],
            **_FPS_KWARGS,
        )

        assert 500.0 in result
        assert 501.0 in result
        assert 0.0 not in result

    @patch("allaganeye.video.gpu_detector.subprocess.Popen")
    def test_silent_zero_frame_decode_raises_on_non_tail_chunk(self, mock_popen):
        """A non-tail chunk that emits nothing is a decode failure, not 255.0 (#864).

        The cmd-shape tests above only inspect the ffmpeg argv, so on their own
        they cannot tell a working decode from a broken one. This pins the other
        side: when the emitted frame count misses the expected count by more than
        the dynamic VFR slack, ``_sample_chunk_frames`` raises and ``scan_gpu``
        turns that into the CPU fallback -- it must never be swallowed into a
        silently all-bright chunk (Codex adversarial-review, #864).
        """
        grid = [float(i) for i in range(100)]  # slack = max(1, ceil(60*0.1)) = 6
        _popen_mock(mock_popen, b"")

        with pytest.raises(VideoProcessingError, match="Dynamic VFR"):
            _decode_chunk(
                Path("test.mp4"),
                0.0,
                100.0,
                1.0,
                chunk_timestamps=grid,
                source_fps_num=60,
                source_fps_den=1,
                is_tail_chunk=False,
            )


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
    # Dynamic chunk sizing / dispatch callback / force 100% (#437, #439)
    # ------------------------------------------------------------

    @patch("allaganeye.video.gpu_detector._decode_chunk")
    def test_chunk_dispatch_callback_fires_before_chunks(self, mock_decode):
        """chunk_dispatch_callback fires exactly once before any chunk executes (#437).

        Long videos used to sit at ``Detecting 0%`` for 2-3 minutes
        while the first chunk decoded; this callback is the hook that
        lets the UI show ``[dispatching N chunks, ...]`` immediately.
        """
        calls: list[str] = []

        def _decode_mock(*args, **kwargs):
            calls.append("chunk")
            return ({0.0: 100.0}, "")

        mock_decode.side_effect = _decode_mock

        def dispatch_cb(n: int) -> None:
            calls.append(f"dispatch:{n}")

        scan_gpu(
            Path("test.mp4"),
            5.0,
            1.0,
            15.0,
            chunk_dispatch_callback=dispatch_cb,
        )

        dispatch_events = [c for c in calls if c.startswith("dispatch")]
        assert len(dispatch_events) == 1, "dispatch callback should fire exactly once"
        assert calls[0].startswith("dispatch"), (
            "dispatch callback should fire before any chunk runs"
        )

    @patch("allaganeye.video.gpu_detector._decode_chunk")
    def test_num_chunks_scales_with_duration(self, mock_decode):
        """Long videos break into more chunks than the old fixed 16 (#437).

        Short videos stay at the historical ``max_parallel`` cap; long
        videos push chunk count up toward ``_MAX_CHUNKS`` so the
        Detecting label can update every ~90s wall time instead of
        every 10 minutes.
        """
        from allaganeye.video.gpu_detector import _MAX_CHUNKS

        mock_decode.return_value = ({}, "")

        scan_gpu(Path("short.mp4"), 10.0, 1.0, 15.0)
        short_chunks = mock_decode.call_count
        mock_decode.reset_mock()

        # 10000s (~2h47m) is well past the _TARGET_CHUNK_WALL_SECS budget
        # so the ceiling engages.
        scan_gpu(Path("long.mp4"), 10000.0, 1.0, 15.0)
        long_chunks = mock_decode.call_count

        assert long_chunks > short_chunks, (
            "long videos must break into more chunks than short ones"
        )
        assert long_chunks == _MAX_CHUNKS, (
            f"long videos should hit the _MAX_CHUNKS ceiling "
            f"(got {long_chunks}, expected {_MAX_CHUNKS})"
        )

    @patch("allaganeye.video.gpu_detector._decode_chunk")
    def test_progress_callback_reaches_total_even_with_drops(self, mock_decode):
        """Final emit equalizes completed with total so bar hits 100% (#439).

        Returning only 1 frame per chunk simulates the frame-drop
        pattern where completed < total_expected naturally.  Without
        the fix, the Detecting bar stopped at 99% and the next line
        (Refining) opened before the user saw completion.
        """
        mock_decode.return_value = ({0.0: 100.0}, "")

        events: list[tuple[int, int]] = []

        scan_gpu(
            Path("test.mp4"),
            20.0,
            1.0,
            15.0,
            progress_callback=lambda c, t, bc: events.append((c, t)),
        )

        assert events, "progress_callback should fire at least once"
        final_completed, final_total = events[-1]
        assert final_completed == final_total, (
            f"last emit must equalize completed with total "
            f"(got {final_completed}/{final_total})"
        )

    @patch("allaganeye.video.gpu_detector._decode_chunk")
    def test_frame_drop_warning_logged(self, mock_decode, caplog):
        """Dropped frames trigger an info log so verbose users can see (#439)."""
        import logging

        mock_decode.return_value = ({0.0: 100.0}, "")

        with caplog.at_level(logging.INFO, logger="allaganeye.video.gpu_detector"):
            scan_gpu(
                Path("test.mp4"),
                20.0,
                1.0,
                15.0,
                progress_callback=lambda c, t, bc: None,
            )

        assert any("boundary drop" in rec.message for rec in caplog.records), (
            "dropped-frame info log not emitted"
        )

    # ------------------------------------------------------------
    # Global sample grid labeling (#392)
    # ------------------------------------------------------------

    @patch("allaganeye.video.gpu_detector._decode_chunk")
    def test_chunks_receive_global_grid_timestamps(self, mock_decode):
        """Each chunk is passed grid-aligned timestamps (#392).

        Before the fix, ``_decode_chunk`` derived timestamps from
        ``chunk_start + k*interval``; chunks whose start wasn't a
        multiple of ``sample_interval`` then labeled frames off-grid, so
        GPU and CPU dicts had different keys for the same physical
        content.  The fix pre-computes the global grid via
        ``_generate_timestamps`` and passes the per-chunk slice to
        ``_decode_chunk`` as ``chunk_timestamps``, mirroring what
        ``_decode_chunk_cpu`` does.
        """
        mock_decode.return_value = ({}, "")
        scan_gpu(Path("test.mp4"), 10228.7, 3.0, 15.0)

        all_timestamps: list[float] = []
        for call in mock_decode.call_args_list:
            kwargs = call.kwargs
            if "chunk_timestamps" in kwargs:
                ts = kwargs["chunk_timestamps"]
            elif len(call.args) >= 6:
                ts = call.args[5]
            else:
                ts = None
            assert ts is not None, (
                "scan_gpu must pass chunk_timestamps to _decode_chunk (#392)"
            )
            all_timestamps.extend(ts)

        assert all_timestamps, "no timestamps dispatched"
        for t in all_timestamps:
            remainder = t - round(t / 3.0) * 3.0
            assert abs(remainder) < 1e-6, (
                f"timestamp={t} not aligned to sample_interval=3.0 "
                f"(remainder={remainder})"
            )

    @patch("allaganeye.video.gpu_detector._decode_chunk")
    def test_dispatched_timestamps_match_cpu_grid_exactly(self, mock_decode):
        """The union of dispatched timestamps equals ``_generate_timestamps`` (#392).

        Ensures no grid point is skipped and no duplicates are dispatched
        across chunks.  With this guarantee, GPU's resulting dict has
        exactly the same keys as ``_scan_cpu``'s.
        """
        from allaganeye.video.detector import _generate_timestamps

        mock_decode.return_value = ({}, "")
        scan_gpu(Path("test.mp4"), 1000.0, 3.0, 15.0)

        dispatched: list[float] = []
        for call in mock_decode.call_args_list:
            kwargs = call.kwargs
            ts = kwargs.get("chunk_timestamps")
            if ts is None and len(call.args) >= 6:
                ts = call.args[5]
            assert ts is not None
            dispatched.extend(ts)

        expected = _generate_timestamps(1000.0, 3.0)
        assert sorted(dispatched) == expected, (
            f"dispatched grid mismatch: "
            f"missing={set(expected) - set(dispatched)}, "
            f"extra={set(dispatched) - set(expected)}"
        )

    @patch("allaganeye.video.gpu_detector._decode_chunk")
    def test_chunk_count_reported_via_callback_matches_dispatched(self, mock_decode):
        """Progress callback's ``total`` equals actually-dispatched chunks (#392).

        Short videos where ``chunk_duration < sample_interval`` collapse
        some chunks (no grid point in range).  The callback must report
        the post-collapse count so ``done / total`` tracks reality.
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

        assert chunk_calls
        total_reported = chunk_calls[-1][1]
        assert total_reported == mock_decode.call_count, (
            f"callback total={total_reported}, actual={mock_decode.call_count}"
        )

    def test_decode_chunk_labels_frames_by_pre_assigned_grid(self):
        """_decode_chunk uses chunk_timestamps[frame_idx] when supplied (#392).

        Direct unit check: passing 3 grid timestamps and 3 decoded frames
        yields a dict keyed by those exact timestamps (not by
        ``chunk_start + k*interval``).
        """
        mock_grid = [321.0, 324.0, 327.0]  # deliberately off from chunk_start
        with patch("allaganeye.video.gpu_detector.subprocess.Popen") as mock_popen:
            _popen_mock(mock_popen, _make_frames([100, 5, 200]))
            result, _ = _decode_chunk(
                Path("test.mp4"),
                319.65,  # off-grid chunk_start
                330.0,
                3.0,
                codec=None,
                chunk_timestamps=mock_grid,
                **_FPS_KWARGS,
            )

        assert set(result) == set(mock_grid), (
            f"labels should come from chunk_timestamps, got {sorted(result)}"
        )
        assert result[321.0] == pytest.approx(100.0)
        assert result[324.0] == pytest.approx(5.0)
        assert result[327.0] == pytest.approx(200.0)

    # ------------------------------------------------------------
    # Parametric duration/interval sweep + short-video edge case
    # (#392 follow-up - extends engineer-1's single-case tests)
    # ------------------------------------------------------------
    #
    # ``test_dispatched_timestamps_match_cpu_grid_exactly`` covers a
    # single (1000, 3.0) configuration and
    # ``test_chunk_count_reported_via_callback_matches_dispatched`` only
    # pins the short-video (10, 3.0) shape.  These bounded parametric
    # cases sweep additional boundary conditions so regressions in the
    # per-chunk slicing logic (``[t for t in global_grid if start <= t <
    # end]``) show up here instead of on a user's 30-second clip.

    @pytest.mark.parametrize(
        ("duration", "interval"),
        [
            (48.0, 3.0),  # exact divide (16 chunks * 3s each)
            (100.0, 3.0),  # partial final chunk
            (60.0, 2.5),  # non-integer interval (L1 auto-adjust)
            (30.0, 3.0),  # target_chunks (16) vs 10 available slots
            (5.0, 3.0),  # ultra-short: most chunks collapse
            (100.0, 5.0),  # large interval
            (3.0, 3.0),  # duration == interval
            (8.0, 3.0),  # short with 3 grid points
        ],
    )
    @patch("allaganeye.video.gpu_detector._decode_chunk")
    def test_dispatched_timestamps_match_cpu_grid_parametric(
        self, mock_decode, duration, interval
    ):
        """dispatched timestamps union == _generate_timestamps across cases.

        The strongest contract for #392: regardless of duration/interval,
        the per-chunk ``chunk_timestamps`` slices together must equal the
        CPU grid with no duplicates and no missing points.  A broken
        per-chunk filter (``start <= t < end``) would drop boundary
        points or re-emit them in two chunks; either would fail here.
        """
        from allaganeye.video.detector import _generate_timestamps

        mock_decode.return_value = ({}, "")
        scan_gpu(Path("test.mp4"), duration, interval, 15.0)

        dispatched: list[float] = []
        for call in mock_decode.call_args_list:
            ts = call.kwargs.get("chunk_timestamps")
            if ts is None and len(call.args) >= 6:
                ts = call.args[5]
            assert ts is not None, (
                f"scan_gpu must pass chunk_timestamps (duration={duration}, "
                f"interval={interval})"
            )
            dispatched.extend(ts)

        expected = _generate_timestamps(duration, interval)
        assert sorted(dispatched) == expected, (
            f"grid mismatch for duration={duration}, interval={interval}: "
            f"missing={sorted(set(expected) - set(dispatched))}, "
            f"extra={sorted(set(dispatched) - set(expected))}"
        )
        # No duplicates across chunks (same frame dispatched twice would
        # confuse _decode_chunk's frame_idx labeling).
        assert len(dispatched) == len(set(dispatched)), (
            f"duplicate timestamps dispatched for duration={duration}, "
            f"interval={interval}"
        )

    @patch("allaganeye.video.gpu_detector._decode_chunk")
    def test_ultra_short_video_dispatches_minimum_chunks(self, mock_decode):
        """Ultra-short video (duration < chunk_duration_target) collapses cleanly.

        For duration=5 / interval=3, only 2 grid points exist (0.0, 3.0)
        but target_chunks=16.  All intermediate chunks collapse to
        zero-grid-points and are dropped by ``if chunk_timestamps:``.
        The call must still dispatch at least one chunk covering those
        2 points, and the callback's total must match actual dispatches.
        """
        from allaganeye.video.detector import _generate_timestamps

        mock_decode.return_value = ({}, "")
        scan_gpu(Path("test.mp4"), 5.0, 3.0, 15.0)

        expected_grid = _generate_timestamps(5.0, 3.0)
        # Few chunks dispatched, but their union covers the full grid.
        dispatched: list[float] = []
        for call in mock_decode.call_args_list:
            ts = call.kwargs.get("chunk_timestamps")
            if ts is None and len(call.args) >= 6:
                ts = call.args[5]
            dispatched.extend(ts or [])

        assert sorted(dispatched) == expected_grid, (
            f"short-video grid mismatch: dispatched={sorted(dispatched)}, "
            f"expected={expected_grid}"
        )
        # ``target_chunks`` (16) is too high for 5 seconds -- collapse
        # must cull degenerate chunks rather than dispatching 16.
        assert mock_decode.call_count < 16, (
            f"too many chunks for short video: {mock_decode.call_count}"
        )


class TestDecodeChunkV2Cmd:
    """GPU _decode_chunk 新 path の cmd 構築検証 (#576 S2.1 / S7.1.10)."""

    import io as _io

    @patch("allaganeye.video.gpu_detector.subprocess.Popen")
    @patch("allaganeye.video.gpu_detector.find_ffmpeg", return_value="ffmpeg")
    def test_nvidia_new_path(self, _mock_ff, mock_popen, monkeypatch):
        import io

        mock_proc = MagicMock()
        # chunk_timestamps has 2 entries -> select filter emits exactly 2 frames.
        # expected_frames = len(chunk_timestamps) = 2; stream must match.
        from allaganeye.video.detector import _FRAME_SIZE as _FS

        mock_proc.stdout = io.BytesIO(bytes([0] * _FS * 2))
        mock_proc.stderr = io.BytesIO(b"")
        mock_proc.wait.return_value = 0
        mock_proc.returncode = 0
        mock_popen.return_value.__enter__.return_value = mock_proc

        _decode_chunk(
            Path("test.mp4"),
            chunk_start=0.0,
            chunk_end=10.0,
            sample_interval=1.0,
            codec="av1",
            chunk_timestamps=[0.0, 5.0],
            vendor="nvidia",
            source_fps_num=60,
            source_fps_den=1,
            is_tail_chunk=False,
        )

        cmd = mock_popen.call_args[0][0]
        # dual seek: one -ss before -i (input seek), one after -i (output seek)
        ss_positions = [i for i, arg in enumerate(cmd) if arg == "-ss"]
        i_idx = cmd.index("-i")
        assert len(ss_positions) == 2, (
            f"expected 2 -ss flags for dual seek, got {ss_positions}"
        )
        assert ss_positions[0] < i_idx, "first -ss should be input seek (before -i)"
        assert ss_positions[1] > i_idx, "second -ss should be output seek (after -i)"
        # -vf must contain select filter (frame-index based, not PTS-based fps=)
        vf_value = cmd[cmd.index("-vf") + 1]
        assert "fps=" not in vf_value
        assert "select='not(mod(n\\," in vf_value, (
            f"select filter missing in GPU -vf, got {vf_value!r}"
        )
        # -fps_mode passthrough explicit
        assert cmd[cmd.index("-fps_mode") + 1] == "passthrough"
        # nvidia decoder preserved
        assert "-c:v" in cmd
        cv_idx = cmd.index("-c:v")
        assert cmd[cv_idx + 1] == "av1_cuvid"

    @patch("allaganeye.video.gpu_detector.subprocess.Popen")
    @patch("allaganeye.video.gpu_detector.find_ffmpeg", return_value="ffmpeg")
    def test_amd_new_path_keeps_hwdownload(self, _mock_ff, mock_popen, monkeypatch):
        import io

        mock_proc = MagicMock()
        # chunk_timestamps has 2 entries -> select filter emits exactly 2 frames.
        from allaganeye.video.detector import _FRAME_SIZE as _FS

        mock_proc.stdout = io.BytesIO(bytes([0] * _FS * 2))
        mock_proc.stderr = io.BytesIO(b"")
        mock_proc.wait.return_value = 0
        mock_proc.returncode = 0
        mock_popen.return_value.__enter__.return_value = mock_proc

        _decode_chunk(
            Path("test.mp4"),
            chunk_start=0.0,
            chunk_end=10.0,
            sample_interval=1.0,
            codec="h264",
            chunk_timestamps=[0.0, 5.0],
            vendor="amd",
            source_fps_num=60,
            source_fps_den=1,
            is_tail_chunk=False,
        )

        cmd = mock_popen.call_args[0][0]
        # AMD: hwdownload prefix in -vf, select filter, dual seek + passthrough
        vf_value = cmd[cmd.index("-vf") + 1]
        assert "hwdownload,format=nv12" in vf_value
        assert "fps=" not in vf_value
        assert "select='not(mod(n\\," in vf_value, (
            f"select filter missing in AMD GPU -vf, got {vf_value!r}"
        )
        # dual seek: one -ss before -i (input seek), one after -i (output seek)
        ss_positions = [i for i, arg in enumerate(cmd) if arg == "-ss"]
        i_idx = cmd.index("-i")
        assert len(ss_positions) == 2, (
            f"expected 2 -ss flags for dual seek, got {ss_positions}"
        )
        assert ss_positions[0] < i_idx, "first -ss should be input seek (before -i)"
        assert ss_positions[1] > i_idx, "second -ss should be output seek (after -i)"
        assert cmd[cmd.index("-fps_mode") + 1] == "passthrough"

    @patch("allaganeye.video.gpu_detector.subprocess.Popen")
    @patch("allaganeye.video.gpu_detector.find_ffmpeg", return_value="ffmpeg")
    def test_intel_qsv_new_path(self, _mock_ff, mock_popen, monkeypatch):
        import io

        mock_proc = MagicMock()
        # chunk_timestamps has 2 entries -> select filter emits exactly 2 frames.
        from allaganeye.video.detector import _FRAME_SIZE as _FS

        mock_proc.stdout = io.BytesIO(bytes([0] * _FS * 2))
        mock_proc.stderr = io.BytesIO(b"")
        mock_proc.wait.return_value = 0
        mock_proc.returncode = 0
        mock_popen.return_value.__enter__.return_value = mock_proc

        _decode_chunk(
            Path("test.mp4"),
            chunk_start=0.0,
            chunk_end=10.0,
            sample_interval=1.0,
            codec="h264",
            chunk_timestamps=[0.0, 5.0],
            vendor="intel",
            source_fps_num=60,
            source_fps_den=1,
            is_tail_chunk=False,
        )

        cmd = mock_popen.call_args[0][0]
        # Intel QSV: hwdownload prefix preserved, select filter, decoder = h264_qsv
        vf_value = cmd[cmd.index("-vf") + 1]
        assert "hwdownload,format=nv12" in vf_value
        assert "fps=" not in vf_value
        assert "select='not(mod(n\\," in vf_value, (
            f"select filter missing in Intel QSV -vf, got {vf_value!r}"
        )
        cv_idx = cmd.index("-c:v")
        assert cmd[cv_idx + 1] == "h264_qsv"
        # dual seek: one -ss before -i (input seek), one after -i (output seek)
        ss_positions = [i for i, arg in enumerate(cmd) if arg == "-ss"]
        i_idx = cmd.index("-i")
        assert len(ss_positions) == 2, (
            f"expected 2 -ss flags for dual seek, got {ss_positions}"
        )
        assert ss_positions[0] < i_idx, "first -ss should be input seek (before -i)"
        assert ss_positions[1] > i_idx, "second -ss should be output seek (after -i)"

    def test_decode_chunk_v2_watchdog_fire_raises_for_cpu_fallback(self, monkeypatch):
        """GPU watchdog-fire (stall) raises VideoProcessingError so scan_gpu falls
        back to CPU, not silently swallow the stalled chunk (#842 codex, GPU side).

        Symmetric to the CPU test
        ``test_decode_chunk_cpu_v2_watchdog_fire_returns_fallback``: the CPU path
        degrades to 255.0, the GPU path re-raises (its decode-failed contract ->
        upstream CPU fallback). Both must surface the stall, never hang/swallow.
        """
        import contextlib
        from types import SimpleNamespace

        from allaganeye.exceptions import VideoProcessingError
        from allaganeye.video import gpu_detector as gd

        @contextlib.contextmanager
        def _fired_watchdog(_proc, _deadline_s):
            yield SimpleNamespace(fired=True)

        def _raise_vfr(**_kwargs):
            raise VideoProcessingError("Dynamic VFR detection: chunk emitted 0 frames")

        fake_proc = MagicMock()
        fake_proc.returncode = -9
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_proc
        fake_cm.__exit__.return_value = False

        monkeypatch.setattr(gd, "_proc_deadline_watchdog", _fired_watchdog)
        monkeypatch.setattr(gd, "_sample_chunk_frames", _raise_vfr)
        monkeypatch.setattr(gd, "find_ffmpeg", lambda: "ffmpeg")
        monkeypatch.setattr(gd.subprocess, "Popen", MagicMock(return_value=fake_cm))

        with pytest.raises(VideoProcessingError):
            gd._decode_chunk_v2(
                Path("x.mkv"),
                chunk_start=0.0,
                chunk_end=9.0,
                sample_interval=3.0,
                codec="h264",
                chunk_timestamps=[0.0, 3.0, 6.0],
                vendor=None,
                fps_num=60,
                fps_den=1,
                is_tail_chunk=False,
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


class TestGpuBrightnessParity:
    """GPU Pass1 brightness must route through detector._frame_brightness so
    CPU and GPU compute brightness identically (Phase 1 B3, Codex #8)."""

    def test_gpu_brightness_shares_frame_brightness_helper(self):
        # GPU path must use the same _frame_brightness so CPU/GPU parity holds.
        import numpy as np

        from allaganeye.video import detector as det
        from allaganeye.video.capture_region import FULL_FRAME

        frame = np.arange(det._FRAME_SIZE, dtype=np.uint8)
        assert det._frame_brightness(frame, FULL_FRAME) == float(frame.mean())

    def test_scan_gpu_accepts_region_kwarg_default_full_frame(self):
        import inspect

        from allaganeye.video import gpu_detector as gpu
        from allaganeye.video.capture_region import FULL_FRAME

        sig = inspect.signature(gpu.scan_gpu)
        assert "region" in sig.parameters
        assert sig.parameters["region"].default is FULL_FRAME


class TestCheckGpuUsage:
    """_check_gpu_usage は honesty 原則: cuvid 実 decoder 名一致のみ "active" と
    断言し、hwaccel コマンドエコーによる substring 一致は "requested (unconfirmed)"
    と正直に記す (#842 P3)。"""

    def test_check_gpu_usage_d3d11va_does_not_overclaim(self, caplog):
        import logging

        from allaganeye.video.gpu_detector import _check_gpu_usage

        stderr = "ffmpeg ... -hwaccel d3d11va -c:v ... \nframe= 100 ..."
        with caplog.at_level(logging.INFO):
            _check_gpu_usage(stderr, "h264", None)
        text = " ".join(r.message for r in caplog.records).lower()
        assert "active (d3d11va)" not in text  # no over-claim
        assert "requested" in text or "unconfirmed" in text  # honest wording

    def test_check_gpu_usage_cuvid_confirms_active(self, caplog):
        import logging

        from allaganeye.video.gpu_detector import _check_gpu_usage

        with caplog.at_level(logging.INFO):
            _check_gpu_usage("Using h264_cuvid decoder ...", "h264", "h264_cuvid")
        assert any("active" in r.message.lower() for r in caplog.records)

    def test_check_gpu_usage_no_marker_warns_cpu(self, caplog):
        import logging

        from allaganeye.video.gpu_detector import _check_gpu_usage

        with caplog.at_level(logging.WARNING):
            _check_gpu_usage("plain software decode log", "h264", None)
        assert any(
            "cpu" in r.message.lower() or "not active" in r.message.lower()
            for r in caplog.records
        )
