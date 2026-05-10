"""Tests for AllaganEyeError context/verbose_detail (issue #351)."""

from allaganeye.exceptions import (
    STDERR_TAIL_BYTES,
    AllaganEyeError,
    DetectionError,
    VideoProcessingError,
)


def test_context_defaults_to_empty():
    exc = AllaganEyeError("boom")
    assert exc.context == {}
    assert exc.verbose_detail() == ""


def test_context_stored_and_rendered():
    exc = VideoProcessingError(
        "ffmpeg failed",
        context={"command": "ffmpeg -i x.mp4", "return_code": 1},
    )
    detail = exc.verbose_detail()
    assert "command: ffmpeg -i x.mp4" in detail
    assert "return_code: 1" in detail


def test_multiline_value_is_indented():
    """stderr tails span many lines; verbose_detail indents them."""
    exc = VideoProcessingError(
        "x",
        context={"stderr_tail": "line1\nline2\nline3"},
    )
    detail = exc.verbose_detail()
    assert "stderr_tail:" in detail
    # Each continuation line gets deeper indentation
    assert "    line1" in detail
    assert "    line2" in detail


def test_exit_code_preserved_with_context():
    exc = DetectionError("nope", context={"stats": {"a": 1}})
    assert exc.exit_code == 4
    assert "stats: {'a': 1}" in exc.verbose_detail()


def test_str_message_independent_of_context():
    """The short message stays clean for non-verbose display."""
    exc = VideoProcessingError("ffmpeg failed", context={"stderr_tail": "junk"})
    assert str(exc) == "ffmpeg failed"


# --- Raise-site context wiring (issue #351) ---


def test_probe_video_error_attaches_command_and_stderr():
    """ffprobe CalledProcessError is wrapped with command/return_code/stderr_tail (#351)."""
    import subprocess
    from pathlib import Path
    from unittest.mock import patch

    import pytest

    from allaganeye.video.probe import probe_video

    err = subprocess.CalledProcessError(
        returncode=2,
        cmd=["ffprobe", "-i", "bad.mkv"],
        stderr="Invalid data found when processing input",
    )
    with (
        patch("allaganeye.video.probe.subprocess.run", side_effect=err),
        patch("allaganeye.video.probe.find_ffprobe", return_value="ffprobe"),
    ):
        with pytest.raises(VideoProcessingError) as excinfo:
            probe_video(Path("bad.mkv"))

    ctx = excinfo.value.context
    assert ctx["return_code"] == 2
    assert "ffprobe" in ctx["command"]
    assert "bad.mkv" in ctx["command"]
    assert "Invalid data" in ctx["stderr_tail"]


def test_stderr_tail_truncated_to_constant_cap():
    """Long stderr output is truncated to last ``STDERR_TAIL_BYTES`` chars (#351, #413).

    Guards against silent bloat of context if someone raises
    ``STDERR_TAIL_BYTES`` or removes the slice entirely.  Verified via
    the probe.py raise site which is representative of all three (probe
    / gpu / extract) that share the same cap.
    """
    import subprocess
    from pathlib import Path
    from unittest.mock import patch

    import pytest

    from allaganeye.video.probe import probe_video

    huge_stderr = "x" * (STDERR_TAIL_BYTES + 3000) + "END"
    err = subprocess.CalledProcessError(
        returncode=1, cmd=["ffprobe"], stderr=huge_stderr
    )
    with (
        patch("allaganeye.video.probe.subprocess.run", side_effect=err),
        patch("allaganeye.video.probe.find_ffprobe", return_value="ffprobe"),
    ):
        with pytest.raises(VideoProcessingError) as excinfo:
            probe_video(Path("bad.mkv"))

    tail = excinfo.value.context["stderr_tail"]
    assert len(tail) == STDERR_TAIL_BYTES
    # Ensure we kept the tail (not the head): the final marker survives
    assert tail.endswith("END")


def test_detection_error_context_includes_audio_hits():
    """DetectionError with empty boundaries carries audio_hits context (#351 / #335).

    Debugging hook lead-1 wants for the #335 GPU/CPU discrepancy
    investigation: when detection finds nothing the context must show
    audio_hits status (= "disabled" when no_audio / frozen).  Guards
    against a future refactor dropping the context dict.
    """
    from pathlib import Path
    from unittest.mock import patch

    import pytest

    from allaganeye.commands.split_matches import run_split
    from allaganeye.config import SplitConfig

    PROBE_RESULT = {
        "duration": 1800.0,
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "codec": "h264",
        "audio_codec": "aac",
    }

    with (
        patch(
            "allaganeye.commands.split_matches.probe_video",
            return_value=PROBE_RESULT,
        ),
        patch(
            "allaganeye.commands.split_matches.detect_match_boundaries",
            return_value=[],
        ),
        patch("allaganeye.commands.split_matches._run_audio_scan", return_value=None),
    ):
        config = SplitConfig(min_match_duration=60.0)
        with pytest.raises(DetectionError) as excinfo:
            run_split(Path("v.mp4"), config)

    ctx = excinfo.value.context
    assert "audio_hits" in ctx
    assert ctx["audio_hits"] == "disabled"


def test_integrity_error_exit_code_seven():
    """IntegrityError reports exit_code 7 (#668)."""
    from allaganeye.exceptions import IntegrityError

    exc = IntegrityError("bundled file missing")
    assert exc.exit_code == 7
    assert isinstance(exc, AllaganEyeError)
    assert exc.context == {}


def test_integrity_error_context_renders_in_verbose():
    """IntegrityError uses base verbose_detail for context dicts (#668)."""
    from allaganeye.exceptions import IntegrityError

    exc = IntegrityError(
        "integrity check failed",
        context={
            "missing": ["lib/allaganeye/audio/refs/fanfare.npz"],
            "size_mismatch": [],
        },
    )
    detail = exc.verbose_detail()
    assert "missing:" in detail
    assert "size_mismatch:" in detail
