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
    """ffmpeg showinfo stderr frame 0 pts_time extraction (#576 S4.4)."""

    def test_parse_first_frame_pts(self):
        mod = _load_module()
        stderr = (
            "[Parsed_showinfo_0 @ 0x1234] n: 0 pts: 0 pts_time:10.5 "
            "duration: 0 duration_time: 0 ...\n"
            "[Parsed_showinfo_0 @ 0x1234] n: 1 pts: 60 pts_time:10.516667 ...\n"
        )
        assert mod._parse_first_pts_time(stderr) == pytest.approx(10.5)

    def test_no_match_returns_none(self):
        mod = _load_module()
        assert mod._parse_first_pts_time("no showinfo output here") is None

    def test_second_frame_not_extracted(self):
        mod = _load_module()
        # Only n:0 should match; a stream starting at n:1 has no n:0
        stderr = "[Parsed_showinfo_0 @ 0x5678] n: 1 pts: 60 pts_time:10.516667 ...\n"
        assert mod._parse_first_pts_time(stderr) is None
