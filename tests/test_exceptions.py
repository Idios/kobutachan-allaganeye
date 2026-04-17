"""Tests for AllaganEyeError context/verbose_detail (issue #351)."""

from allaganeye.exceptions import (
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
