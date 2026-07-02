"""Unit tests for scripts/validate-fps-retirement.py (#576 S4.4 / S9.3)."""

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "validate-fps-retirement.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("validate_fps_retirement", _SCRIPT)
    assert spec is not None and spec.loader is not None, (
        f"Could not load module spec from {_SCRIPT}"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["validate_fps_retirement"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestEdgeCaseTailChunk:
    """tail chunk SKIP (#576 S4.4 edge cases)."""

    def test_chunk_past_duration_is_skipped(self):
        mod = _load_module()
        # video duration = 100s, chunk_start = 99.6 -> 99.6 + 0.5 > 100 = SKIP
        result = mod._classify_chunk(chunk_start=99.6, duration=100.0)
        assert result == "skip_tail"

    def test_chunk_within_video_is_run(self):
        mod = _load_module()
        result = mod._classify_chunk(chunk_start=50.0, duration=100.0)
        assert result == "run"


class TestEdgeCaseVendorCodecMismatch:
    """codec/vendor capability mismatch exits 2 (#576 S4.4)."""

    def test_intel_av1_rejected(self):
        mod = _load_module()
        # Tiger Lake av1_qsv is runtime-only unsupported (#550).
        # At script level, map existence = run; codec absent = exit 2.
        # cpu vendor has no capability constraints -> av1 is run.
        assert mod._check_vendor_codec_supported("cpu", "av1") is True

    def test_unknown_codec_for_amd_rejected(self):
        mod = _load_module()
        # AMD does not have vp9 in _GPU_DECODER_MAP
        assert mod._check_vendor_codec_supported("amd", "vp9") is False

    def test_known_combination_supported(self):
        mod = _load_module()
        assert mod._check_vendor_codec_supported("nvidia", "av1") is True
        assert mod._check_vendor_codec_supported("intel", "h264") is True


class TestEdgeCaseShortClip:
    """duration < smallest chunk_start exits 2 (#576 S4.4)."""

    def test_duration_too_short_for_chunks(self):
        mod = _load_module()
        with pytest.raises(SystemExit) as excinfo:
            mod._validate_duration_against_chunks(
                duration=50.0,
                chunks=[100.0, 200.0],
            )
        assert excinfo.value.code == 2


class TestParsePtsTime:
    """ffmpeg showinfo stderr first *emitted* frame pts_time extraction (#804).

    Output seek (``-ss`` after ``-i``) trims at the muxer stage AFTER the
    filter graph, so showinfo logs every decoded frame from t=0.  The first
    emitted frame is therefore the first showinfo line with
    ``pts_time >= chunk_start``, NOT the ``n: 0`` line (which is always the
    video's first frame = container start_time, e.g. the constant 0.021 of
    OBS MKV recordings that #804 reported).
    """

    def test_parse_first_emitted_pts_skips_pre_seek_frames(self):
        """#804 regression: n:0 is the video head (0.021), not the emitted frame."""
        mod = _load_module()
        stderr = (
            "[Parsed_showinfo_0 @ 0x1234] n:   0 pts:     21 pts_time:0.021 "
            "duration: 0 duration_time: 0 ...\n"
            "[Parsed_showinfo_0 @ 0x1234] n:   1 pts:    533 pts_time:0.0543333 ...\n"
            "[Parsed_showinfo_0 @ 0x1234] n: 899 pts: 460288 pts_time:29.966667 ...\n"
            "[Parsed_showinfo_0 @ 0x1234] n: 900 pts: 460800 pts_time:30 ...\n"
            "[Parsed_showinfo_0 @ 0x1234] n: 901 pts: 461312 pts_time:30.033333 ...\n"
        )
        assert mod._parse_first_emitted_pts_time(stderr, 30.0) == pytest.approx(30.0)

    def test_no_match_returns_none(self):
        mod = _load_module()
        assert (
            mod._parse_first_emitted_pts_time("no showinfo output here", 30.0) is None
        )

    def test_all_frames_before_chunk_start_returns_none(self):
        """Stream that ends before chunk_start (e.g. ffmpeg died early) -> None."""
        mod = _load_module()
        stderr = (
            "[Parsed_showinfo_0 @ 0x5678] n: 0 pts: 21 pts_time:0.021 ...\n"
            "[Parsed_showinfo_0 @ 0x5678] n: 1 pts: 533 pts_time:0.0543333 ...\n"
        )
        assert mod._parse_first_emitted_pts_time(stderr, 30.0) is None

    def test_just_below_boundary_frame_is_not_selected(self):
        """codex #804: a dropped frame printed a hair below chunk_start must be
        skipped -- selecting it would pair its PTS with the brightness of the
        NEXT frame (the actually emitted one) and forge PASS evidence."""
        mod = _load_module()
        stderr = (
            "[Parsed_showinfo_0 @ 0x9abc] n: 0 pts: 0 pts_time:0 ...\n"
            "[Parsed_showinfo_0 @ 0x9abc] n: 900 pts: 460799 pts_time:29.99995 ...\n"
            "[Parsed_showinfo_0 @ 0x9abc] n: 901 pts: 461312 pts_time:30.016667 ...\n"
        )
        assert mod._parse_first_emitted_pts_time(stderr, 30.0) == pytest.approx(
            30.016667
        )

    def test_stream_ending_just_below_boundary_returns_none(self):
        """Strict >= boundary: only pre-boundary frames -> None (no forged PTS)."""
        mod = _load_module()
        stderr = (
            "[Parsed_showinfo_0 @ 0x9abc] n: 900 pts: 460799 pts_time:29.99995 ...\n"
        )
        assert mod._parse_first_emitted_pts_time(stderr, 30.0) is None

    def test_chunk_start_zero_returns_first_frame(self):
        """chunk_start=0: the video's first frame IS the emitted frame."""
        mod = _load_module()
        stderr = "[Parsed_showinfo_0 @ 0x1234] n: 0 pts: 21 pts_time:0.021 ...\n"
        assert mod._parse_first_emitted_pts_time(stderr, 0.0) == pytest.approx(0.021)


class TestRunChunkTimeout:
    """long chunk_start decode-from-0 timeout handling (codex #804)."""

    def _fake_completed(self, mod, stderr_text: str):
        import subprocess

        return subprocess.CompletedProcess(
            args=["ffmpeg"],
            returncode=0,
            stdout=b"\x40" * mod._FRAME_SIZE,
            stderr=stderr_text.encode(),
        )

    def test_timeout_expired_degrades_to_fail_row_not_crash(self, monkeypatch):
        """TimeoutExpired -> (None, None, probe) so the caller prints a FAIL row."""
        import subprocess

        mod = _load_module()

        def _raise_timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd=["ffmpeg"], timeout=kwargs["timeout"])

        monkeypatch.setattr(mod.subprocess, "run", _raise_timeout)
        monkeypatch.setattr(mod, "_probe_single_frame", lambda *a, **k: 42.0)
        emit_pts, emit_brightness, probe_brightness = mod._run_chunk(
            Path("dummy.mkv"), 7200.0, "cpu", "h264", 60.0
        )
        assert emit_pts is None
        assert emit_brightness is None
        assert probe_brightness == 42.0

    def test_timeout_scales_with_chunk_start(self, monkeypatch):
        """decode-from-0 needs ~chunk_start seconds of decode budget, not fixed 60s."""
        mod = _load_module()
        captured: dict = {}

        def _capture(cmd, **kwargs):
            captured.update(kwargs)
            return self._fake_completed(
                mod, "[Parsed_showinfo_0 @ 0x1] n: 0 pts: 0 pts_time:7200 ...\n"
            )

        monkeypatch.setattr(mod.subprocess, "run", _capture)
        monkeypatch.setattr(mod, "_probe_single_frame", lambda *a, **k: 42.0)
        mod._run_chunk(Path("dummy.mkv"), 7200.0, "cpu", "h264", 60.0)
        assert captured["timeout"] >= 7200.0
