"""Tests for CLI entry point."""

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from allaganeye.cli import app
from allaganeye.exceptions import (
    AllaganEyeError,
    DetectionError,
    InputFileError,
    VideoProcessingError,
)

runner = CliRunner()

MODULE = "allaganeye.commands.split_matches.run_split"


# --- Basic tests ---


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "allaganeye" in result.stdout


def test_version_short_flag():
    """-V should be an alias for --version (issue #337)."""
    result = runner.invoke(app, ["-V"])
    assert result.exit_code == 0
    assert "allaganeye" in result.stdout


def test_verbose_short_flag_unchanged():
    """-v must still map to --verbose (not --version) on the split command.

    Breaking-change policy for v0.1.x: we add -V for --version but keep
    -v = --verbose to avoid disrupting existing preview users (issue #337).
    """
    result = runner.invoke(app, ["split", "--help"])
    assert result.exit_code == 0
    # -v appears in the verbose flag help
    assert "-v" in result.stdout
    assert "verbose" in result.stdout.lower()


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "FF14 Frontline" in result.stdout


def test_split_help():
    result = runner.invoke(app, ["split", "--help"])
    assert result.exit_code == 0
    assert "video_path" in result.stdout.lower() or "VIDEO_PATH" in result.stdout


def test_split_missing_file():
    result = runner.invoke(app, ["split", "nonexistent.mp4"])
    assert result.exit_code == 2
    assert (
        "not found" in result.stdout.lower()
        or "not found" in (result.stderr or "").lower()
    )


def test_split_unsupported_format(tmp_path):
    fake_file = tmp_path / "video.txt"
    fake_file.write_text("not a video")
    result = runner.invoke(app, ["split", str(fake_file)])
    assert result.exit_code == 2
    assert (
        "unsupported" in result.stdout.lower()
        or "unsupported" in (result.stderr or "").lower()
    )


# --- Validation tests (exit code 5) ---


def test_split_negative_sample_interval(tmp_path):
    fake_file = tmp_path / "video.mp4"
    fake_file.write_bytes(b"\x00")
    result = runner.invoke(app, ["split", str(fake_file), "--sample-interval", "-1"])
    assert result.exit_code == 5


def test_split_zero_sample_interval(tmp_path):
    fake_file = tmp_path / "video.mp4"
    fake_file.write_bytes(b"\x00")
    result = runner.invoke(app, ["split", str(fake_file), "--sample-interval", "0"])
    assert result.exit_code == 5


def test_split_blackout_threshold_over_255(tmp_path):
    fake_file = tmp_path / "video.mp4"
    fake_file.write_bytes(b"\x00")
    result = runner.invoke(
        app, ["split", str(fake_file), "--blackout-threshold", "300"]
    )
    assert result.exit_code == 5


def test_split_negative_min_match_duration(tmp_path):
    fake_file = tmp_path / "video.mp4"
    fake_file.write_bytes(b"\x00")
    result = runner.invoke(app, ["split", str(fake_file), "--min-match-duration", "-1"])
    assert result.exit_code == 5


def test_split_negative_min_blackout_duration(tmp_path):
    """--min-blackout-duration -1 should fail validation (must be >= 0)."""
    fake_file = tmp_path / "video.mp4"
    fake_file.write_bytes(b"\x00")
    result = runner.invoke(
        app, ["split", str(fake_file), "--min-blackout-duration", "-1"]
    )
    assert result.exit_code == 5


def test_split_workers_zero(tmp_path):
    """--workers 0 should fail validation (must be >= 1)."""
    fake_file = tmp_path / "video.mp4"
    fake_file.write_bytes(b"\x00")
    result = runner.invoke(app, ["split", str(fake_file), "--workers", "0"])
    assert result.exit_code == 5


def test_split_workers_negative(tmp_path):
    """--workers -1 should fail validation."""
    fake_file = tmp_path / "video.mp4"
    fake_file.write_bytes(b"\x00")
    result = runner.invoke(app, ["split", str(fake_file), "--workers", "-1"])
    assert result.exit_code == 5


# --- Option tests ---


@patch(MODULE)
def test_split_default_options(mock_run_split, fake_video):
    """Default options produce expected SplitConfig values."""
    result = runner.invoke(app, ["split", str(fake_video)])

    assert result.exit_code == 0
    mock_run_split.assert_called_once()
    _, kwargs = mock_run_split.call_args
    config = mock_run_split.call_args[0][1]
    assert config.output_dir == Path("./output")
    assert config.sample_interval == 1.0
    assert config.blackout_threshold == 15.0
    assert config.min_match_duration == 300.0
    assert config.min_blackout_duration == 3.0
    assert config.workers is None
    assert config.use_gpu is None  # auto mode (#334)
    assert config.dry_run is False
    assert kwargs["verbose"] is False
    assert kwargs["quiet"] is False


@patch(MODULE)
def test_split_output_dir_option(mock_run_split, fake_video, tmp_path):
    """Short -o option sets output_dir."""
    out = tmp_path / "custom"
    result = runner.invoke(app, ["split", str(fake_video), "-o", str(out)])

    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.output_dir == out


@patch(MODULE)
def test_split_output_dir_long_form(mock_run_split, fake_video, tmp_path):
    """Long --output-dir option sets output_dir."""
    out = tmp_path / "custom"
    result = runner.invoke(app, ["split", str(fake_video), "--output-dir", str(out)])

    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.output_dir == out


@patch(MODULE)
def test_split_sample_interval(mock_run_split, fake_video):
    """--sample-interval option is forwarded to config."""
    result = runner.invoke(app, ["split", str(fake_video), "--sample-interval", "2.5"])

    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.sample_interval == 2.5


@patch(MODULE)
def test_split_blackout_threshold(mock_run_split, fake_video):
    """--blackout-threshold option is forwarded to config."""
    result = runner.invoke(
        app, ["split", str(fake_video), "--blackout-threshold", "20.0"]
    )

    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.blackout_threshold == 20.0


@patch(MODULE)
def test_split_min_match_duration(mock_run_split, fake_video):
    """--min-match-duration option is forwarded to config."""
    result = runner.invoke(
        app, ["split", str(fake_video), "--min-match-duration", "120"]
    )

    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.min_match_duration == 120.0


@patch(MODULE)
def test_split_min_blackout_duration(mock_run_split, fake_video):
    """--min-blackout-duration option is forwarded to config."""
    result = runner.invoke(
        app, ["split", str(fake_video), "--min-blackout-duration", "5.0"]
    )

    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.min_blackout_duration == 5.0


@patch(MODULE)
def test_split_dry_run(mock_run_split, fake_video):
    """--dry-run flag sets config.dry_run=True."""
    result = runner.invoke(app, ["split", str(fake_video), "--dry-run"])

    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.dry_run is True


@patch(MODULE)
def test_split_workers_option(mock_run_split, fake_video):
    """--workers 8 sets config.workers=8."""
    result = runner.invoke(app, ["split", str(fake_video), "--workers", "8"])

    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.workers == 8


@patch(MODULE)
def test_split_gpu_flag(mock_run_split, fake_video):
    """--gpu sets config.use_gpu=True."""
    result = runner.invoke(app, ["split", str(fake_video), "--gpu"])

    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.use_gpu is True


@patch(MODULE)
def test_split_no_gpu_flag(mock_run_split, fake_video):
    """--no-gpu explicitly sets config.use_gpu=False."""
    result = runner.invoke(app, ["split", str(fake_video), "--no-gpu"])

    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.use_gpu is False


@patch(MODULE)
def test_split_verbose_short(mock_run_split, fake_video):
    """-v flag sets verbose=True."""
    result = runner.invoke(app, ["split", str(fake_video), "-v"])

    assert result.exit_code == 0
    assert mock_run_split.call_args[1]["verbose"] is True


@patch(MODULE)
def test_split_verbose_long(mock_run_split, fake_video):
    """--verbose flag sets verbose=True."""
    result = runner.invoke(app, ["split", str(fake_video), "--verbose"])

    assert result.exit_code == 0
    assert mock_run_split.call_args[1]["verbose"] is True


@patch(MODULE)
def test_split_quiet_short(mock_run_split, fake_video):
    """-q flag sets quiet=True."""
    result = runner.invoke(app, ["split", str(fake_video), "-q"])

    assert result.exit_code == 0
    assert mock_run_split.call_args[1]["quiet"] is True


@patch(MODULE)
def test_split_quiet_long(mock_run_split, fake_video):
    """--quiet flag sets quiet=True."""
    result = runner.invoke(app, ["split", str(fake_video), "--quiet"])

    assert result.exit_code == 0
    assert mock_run_split.call_args[1]["quiet"] is True


@patch(MODULE)
def test_split_all_options_combined(mock_run_split, fake_video, tmp_path):
    """All options combined are correctly forwarded."""
    out = tmp_path / "all"
    result = runner.invoke(
        app,
        [
            "split",
            str(fake_video),
            "-o",
            str(out),
            "--sample-interval",
            "0.5",
            "--blackout-threshold",
            "25.0",
            "--min-match-duration",
            "60",
            "--min-blackout-duration",
            "5.0",
            "--workers",
            "4",
            "--gpu",
            "--dry-run",
            "-v",
        ],
    )

    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.output_dir == out
    assert config.sample_interval == 0.5
    assert config.blackout_threshold == 25.0
    assert config.min_match_duration == 60.0
    assert config.min_blackout_duration == 5.0
    assert config.workers == 4
    assert config.use_gpu is True
    assert config.dry_run is True
    assert mock_run_split.call_args[1]["verbose"] is True


# --- Error exit code tests ---


@patch(MODULE)
def test_split_processing_error_exit_code(mock_run_split, fake_video):
    """VideoProcessingError produces exit code 3."""
    mock_run_split.side_effect = VideoProcessingError("ffmpeg failed")

    result = runner.invoke(app, ["split", str(fake_video)])
    assert result.exit_code == 3


@patch(MODULE)
def test_split_detection_error_exit_code(mock_run_split, fake_video):
    """DetectionError produces exit code 4."""
    mock_run_split.side_effect = DetectionError("No boundaries found")

    result = runner.invoke(app, ["split", str(fake_video)])
    assert result.exit_code == 4


@patch(MODULE)
def test_split_input_file_error_exit_code(mock_run_split, fake_video):
    """InputFileError from run_split produces exit code 2."""
    mock_run_split.side_effect = InputFileError("No video stream found")

    result = runner.invoke(app, ["split", str(fake_video)])
    assert result.exit_code == 2


@patch(MODULE)
def test_split_base_error_exit_code(mock_run_split, fake_video):
    """AllaganEyeError (base class) produces exit code 1."""
    mock_run_split.side_effect = AllaganEyeError("generic error")

    result = runner.invoke(app, ["split", str(fake_video)])
    assert result.exit_code == 1


@patch(MODULE)
def test_split_unexpected_error_exit_code(mock_run_split, fake_video):
    """Unexpected RuntimeError produces exit code 1."""
    mock_run_split.side_effect = RuntimeError("unexpected")

    result = runner.invoke(app, ["split", str(fake_video)])
    assert result.exit_code == 1


# --- Verbose error detail tests (issue #351) ---


@patch(MODULE)
def test_split_verbose_shows_context_detail(mock_run_split, fake_video):
    """VideoProcessingError with context emits 'stderr_tail:' in verbose mode."""
    mock_run_split.side_effect = VideoProcessingError(
        "ffmpeg failed",
        context={
            "command": "ffmpeg -i foo.mp4",
            "return_code": 1,
            "stderr_tail": "NAL unit type 12 not supported",
        },
    )
    result = runner.invoke(app, ["split", str(fake_video), "-v"])
    assert result.exit_code == 3
    combined = result.stdout + (result.stderr or "")
    assert "Error: ffmpeg failed" in combined
    assert "command:" in combined
    assert "return_code:" in combined
    assert "stderr_tail:" in combined
    assert "NAL unit type 12 not supported" in combined


@patch(MODULE)
def test_split_non_verbose_hides_context_detail(mock_run_split, fake_video):
    """Without -v, context detail stays hidden (short error only)."""
    mock_run_split.side_effect = VideoProcessingError(
        "ffmpeg failed",
        context={"stderr_tail": "NAL unit type 12 not supported"},
    )
    result = runner.invoke(app, ["split", str(fake_video)])
    assert result.exit_code == 3
    combined = result.stdout + (result.stderr or "")
    assert "Error: ffmpeg failed" in combined
    assert "stderr_tail" not in combined
    assert "NAL unit type 12 not supported" not in combined


@patch(MODULE)
def test_split_verbose_shows_traceback_for_unexpected(mock_run_split, fake_video):
    """Unexpected Exception emits traceback to stderr in verbose mode."""
    mock_run_split.side_effect = RuntimeError("boom")
    result = runner.invoke(app, ["split", str(fake_video), "-v"])
    assert result.exit_code == 1
    combined = result.stdout + (result.stderr or "")
    assert "Traceback" in combined
    assert "RuntimeError: boom" in combined


@patch(MODULE)
def test_split_non_verbose_hides_traceback_for_unexpected(mock_run_split, fake_video):
    """Without -v, unexpected error shows short one-liner (no traceback)."""
    mock_run_split.side_effect = RuntimeError("boom")
    result = runner.invoke(app, ["split", str(fake_video)])
    assert result.exit_code == 1
    combined = result.stdout + (result.stderr or "")
    assert "Traceback" not in combined
    assert "Unexpected error" in combined
    assert "boom" in combined


# --- Matrix v2 19a/19b/19c error display tests (issue #428) ---


@patch(MODULE)
def test_matrix_19a_verbose_emits_traceback_for_app_error(mock_run_split, fake_video):
    """19a: -v shows Error + verbose_detail + full traceback for AllaganEyeError.

    The traceback must be emitted even though the CLI handler re-raises
    via ``raise typer.Exit from None``: we print the traceback *before*
    the re-raise, when the original exception stack is still attached.
    """
    mock_run_split.side_effect = VideoProcessingError(
        "ffmpeg failed",
        context={
            "command": "ffmpeg -i foo.mp4",
            "return_code": 1,
            "stderr_tail": "NAL unit type 12 not supported",
        },
    )
    result = runner.invoke(app, ["split", str(fake_video), "-v"])
    assert result.exit_code == 3
    combined = result.stdout + (result.stderr or "")
    # Error line + verbose detail + traceback lines all present.
    assert "Error: ffmpeg failed" in combined
    assert "stderr_tail:" in combined
    assert "NAL unit type 12 not supported" in combined
    assert "Traceback" in combined
    assert "VideoProcessingError" in combined
    # Hint must NOT appear in verbose mode (hint is 19b's signal).
    assert "--verbose for full details" not in combined


@patch(MODULE)
def test_matrix_19b_default_emits_hint_for_app_error(mock_run_split, fake_video):
    """19b: default shows Error + 1-line hint (no context, no traceback)."""
    mock_run_split.side_effect = VideoProcessingError(
        "ffmpeg failed",
        context={"stderr_tail": "NAL unit type 12 not supported"},
    )
    result = runner.invoke(app, ["split", str(fake_video)])
    assert result.exit_code == 3
    combined = result.stdout + (result.stderr or "")
    assert "Error: ffmpeg failed" in combined
    # Hint is the defining 19b signal.
    assert "Run with -v / --verbose for full details" in combined
    # Neither context detail nor traceback leak into default mode.
    assert "stderr_tail" not in combined
    assert "NAL unit type" not in combined
    assert "Traceback" not in combined


@patch(MODULE)
def test_matrix_19c_quiet_emits_error_only_for_app_error(mock_run_split, fake_video):
    """19c: -q shows Error only.  No context, no hint, no traceback."""
    mock_run_split.side_effect = VideoProcessingError(
        "ffmpeg failed",
        context={"stderr_tail": "NAL unit type 12 not supported"},
    )
    result = runner.invoke(app, ["split", str(fake_video), "-q"])
    assert result.exit_code == 3
    combined = result.stdout + (result.stderr or "")
    assert "Error: ffmpeg failed" in combined
    assert "--verbose for full details" not in combined
    assert "stderr_tail" not in combined
    assert "NAL unit type" not in combined
    assert "Traceback" not in combined


@patch(MODULE)
def test_matrix_19b_default_emits_hint_for_unexpected(mock_run_split, fake_video):
    """19b applies to non-AllaganEyeError too: one-liner + hint."""
    mock_run_split.side_effect = RuntimeError("boom")
    result = runner.invoke(app, ["split", str(fake_video)])
    assert result.exit_code == 1
    combined = result.stdout + (result.stderr or "")
    assert "Unexpected error: boom" in combined
    assert "Run with -v / --verbose for full details" in combined
    assert "Traceback" not in combined


@patch(MODULE)
def test_matrix_19c_quiet_emits_error_only_for_unexpected(mock_run_split, fake_video):
    """19c for non-AllaganEyeError: one-liner only (no hint, no traceback)."""
    mock_run_split.side_effect = RuntimeError("boom")
    result = runner.invoke(app, ["split", str(fake_video), "-q"])
    assert result.exit_code == 1
    combined = result.stdout + (result.stderr or "")
    assert "Unexpected error: boom" in combined
    assert "--verbose for full details" not in combined
    assert "Traceback" not in combined


@patch(MODULE)
def test_matrix_traceback_includes_exception_class_name(mock_run_split, fake_video):
    """-v traceback must surface the concrete AllaganEyeError subclass.

    Bug reports lean on the subclass name to classify failures; a bare
    base-class ``AllaganEyeError`` would lose the signal.
    """
    mock_run_split.side_effect = DetectionError("no boundaries")
    result = runner.invoke(app, ["split", str(fake_video), "-v"])
    assert result.exit_code == 4
    combined = result.stdout + (result.stderr or "")
    assert "Traceback" in combined
    assert "DetectionError" in combined


@patch(MODULE)
def test_matrix_config_error_follows_matrix(mock_run_split, fake_video):
    """ConfigValidationError (pre-run_split path) still follows the matrix.

    The CLI raises ConfigValidationError itself when -v and -q conflict
    (#419); the reporter must use the correct mode for the *successful*
    option -- i.e. when only -v is passed, -v wins and 19a applies.
    """
    # Invalid threshold raises during SplitConfig.__post_init__ -> CVE.
    # Run with -v so we assert 19a's output shape.
    result = runner.invoke(
        app,
        ["split", str(fake_video), "--blackout-threshold", "-5", "-v"],
    )
    assert result.exit_code == 5
    combined = result.stdout + (result.stderr or "")
    assert "Error:" in combined
    assert "Traceback" in combined
    assert "ConfigValidationError" in combined


def test_matrix_debug_brightness_hint_suppressed(tmp_path):
    """debug-brightness has no -v option; do not show the -v hint on error.

    Input-validation error path triggers InputFileError without -v / -q
    flags available.  The hint would be misleading ("Run with -v" is not
    a valid option here), so ``show_hint=False`` is passed in the
    debug-brightness handler.  Exit code must stay at 2 (InputFileError).
    """
    missing = tmp_path / "does_not_exist.mp4"
    result = runner.invoke(app, ["debug-brightness", str(missing)])
    assert result.exit_code == 2
    combined = result.stdout + (result.stderr or "")
    assert "Error:" in combined
    assert "--verbose for full details" not in combined


# --- Extension support tests ---


@patch(MODULE)
def test_split_mkv_extension(mock_run_split, tmp_path):
    """MKV files are accepted."""
    video = tmp_path / "recording.mkv"
    video.write_bytes(b"")
    result = runner.invoke(app, ["split", str(video)])
    assert result.exit_code == 0
    mock_run_split.assert_called_once()


@patch(MODULE)
def test_split_avi_extension(mock_run_split, tmp_path):
    """AVI files are accepted."""
    video = tmp_path / "recording.avi"
    video.write_bytes(b"")
    result = runner.invoke(app, ["split", str(video)])
    assert result.exit_code == 0
    mock_run_split.assert_called_once()


# ============================================================
# debug-brightness CLI tests
# ============================================================

DEBUG_MODULE = "allaganeye.commands.debug_brightness.run_debug_brightness"


def test_debug_brightness_help():
    """debug-brightness --help shows usage."""
    result = runner.invoke(app, ["debug-brightness", "--help"])
    assert result.exit_code == 0
    assert "video_path" in result.stdout.lower() or "VIDEO_PATH" in result.stdout


def test_debug_brightness_missing_file():
    """Nonexistent file produces exit code 2."""
    result = runner.invoke(app, ["debug-brightness", "nonexistent.mp4"])
    assert result.exit_code == 2
    assert (
        "not found" in result.stdout.lower()
        or "not found" in (result.stderr or "").lower()
    )


def test_debug_brightness_unsupported_format(tmp_path):
    """Unsupported extension produces exit code 2."""
    fake_file = tmp_path / "video.txt"
    fake_file.write_text("not a video")
    result = runner.invoke(app, ["debug-brightness", str(fake_file)])
    assert result.exit_code == 2
    assert (
        "unsupported" in result.stdout.lower()
        or "unsupported" in (result.stderr or "").lower()
    )


@patch(DEBUG_MODULE)
def test_debug_brightness_default_options(mock_run, fake_video):
    """Default options are forwarded correctly."""
    result = runner.invoke(app, ["debug-brightness", str(fake_video)])

    assert result.exit_code == 0
    mock_run.assert_called_once()
    _, kwargs = mock_run.call_args
    assert kwargs["start"] == 0.0
    assert kwargs["end"] is None
    assert kwargs["interval"] == 1.0
    assert kwargs["workers"] is None
    assert kwargs["roi_mode"] is None


@patch(DEBUG_MODULE)
def test_debug_brightness_roi_mode_scorebar(mock_run, fake_video):
    """--roi-mode scorebar is forwarded."""
    result = runner.invoke(
        app, ["debug-brightness", str(fake_video), "--roi-mode", "scorebar"]
    )

    assert result.exit_code == 0
    assert mock_run.call_args[1]["roi_mode"] == "scorebar"


@patch(DEBUG_MODULE)
def test_debug_brightness_roi_mode_scorebar_detail(mock_run, fake_video):
    """--roi-mode scorebar-detail is forwarded."""
    result = runner.invoke(
        app, ["debug-brightness", str(fake_video), "--roi-mode", "scorebar-detail"]
    )

    assert result.exit_code == 0
    assert mock_run.call_args[1]["roi_mode"] == "scorebar-detail"


@patch(DEBUG_MODULE)
def test_debug_brightness_start_end_interval(mock_run, fake_video):
    """--start, --end, --interval are forwarded."""
    result = runner.invoke(
        app,
        [
            "debug-brightness",
            str(fake_video),
            "--start",
            "10.0",
            "--end",
            "60.0",
            "--interval",
            "0.5",
        ],
    )

    assert result.exit_code == 0
    _, kwargs = mock_run.call_args
    assert kwargs["start"] == 10.0
    assert kwargs["end"] == 60.0
    assert kwargs["interval"] == 0.5


@patch(MODULE)
def test_no_cache_option_accepted(mock_run, fake_video):
    """--no-cache option is accepted without error."""
    result = runner.invoke(app, ["split", str(fake_video), "--no-cache"])
    assert result.exit_code == 0
    config = mock_run.call_args[0][1]
    assert config.no_cache is True


# --- Mutually exclusive flag tests (#419) ---
#
# -q / -v and --gpu / --no-gpu are semantically exclusive.  Typer's default
# parse treats each pair as last-wins (silent), so scripts that set both
# end up with non-deterministic behaviour.  Exit code 5 (config-invalid)
# surfaces the mistake instead.


@patch(MODULE)
def test_split_quiet_verbose_mutually_exclusive(mock_run_split, fake_video):
    """-q and -v together exit 5 without calling run_split (#419 P)."""
    result = runner.invoke(app, ["split", str(fake_video), "-q", "-v"])
    assert result.exit_code == 5
    mock_run_split.assert_not_called()
    combined = result.stdout + (result.stderr or "")
    assert "--quiet and --verbose are mutually exclusive" in combined
    assert result.stdout == "", f"stdout must be empty: {result.stdout!r}"


@patch(MODULE)
def test_split_verbose_quiet_mutually_exclusive_order_independent(
    mock_run_split, fake_video
):
    """-v -q (reverse order) also exits 5 (#419 P)."""
    result = runner.invoke(app, ["split", str(fake_video), "-v", "-q"])
    assert result.exit_code == 5
    mock_run_split.assert_not_called()


@patch(MODULE)
def test_split_long_quiet_verbose_mutually_exclusive(mock_run_split, fake_video):
    """Long forms --quiet --verbose are also caught (#419 P)."""
    result = runner.invoke(app, ["split", str(fake_video), "--quiet", "--verbose"])
    assert result.exit_code == 5
    mock_run_split.assert_not_called()


@patch(MODULE)
def test_split_gpu_no_gpu_mutually_exclusive(mock_run_split, fake_video):
    """--gpu and --no-gpu together exit 5 (#419)."""
    result = runner.invoke(app, ["split", str(fake_video), "--gpu", "--no-gpu"])
    assert result.exit_code == 5
    mock_run_split.assert_not_called()
    combined = result.stdout + (result.stderr or "")
    assert "--gpu and --no-gpu are mutually exclusive" in combined
    assert result.stdout == "", f"stdout must be empty: {result.stdout!r}"


@patch(MODULE)
def test_split_no_gpu_gpu_order_independent(mock_run_split, fake_video):
    """--no-gpu --gpu (reverse order) also exits 5 (#419)."""
    result = runner.invoke(app, ["split", str(fake_video), "--no-gpu", "--gpu"])
    assert result.exit_code == 5
    mock_run_split.assert_not_called()


@patch(MODULE)
def test_split_no_gpu_alone_still_works(mock_run_split, fake_video):
    """--no-gpu alone continues to force CPU mode (#419 regression guard)."""
    result = runner.invoke(app, ["split", str(fake_video), "--no-gpu"])
    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.use_gpu is False


@patch(MODULE)
def test_split_gpu_alone_still_works(mock_run_split, fake_video):
    """--gpu alone forces GPU mode (#419 regression guard)."""
    result = runner.invoke(app, ["split", str(fake_video), "--gpu"])
    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.use_gpu is True


@patch(MODULE)
def test_split_neither_gpu_flag_preserves_auto(mock_run_split, fake_video):
    """Neither --gpu nor --no-gpu keeps use_gpu=None (auto-select, #334)."""
    result = runner.invoke(app, ["split", str(fake_video)])
    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.use_gpu is None


# --- CLI option combination tests ---
#
# The existing per-option tests verify each flag in isolation.  Users run
# the CLI with *combinations* (e.g. ``--dry-run --no-cache -v`` when
# troubleshooting), and individual-flag tests don't guarantee that
# pairwise and three-way interactions still wire through to SplitConfig
# correctly.
#
# Full 2^N cartesian coverage is infeasible (~16k cases for ~14 options).
# Instead we cover three bounded axes:
#
#   1. Real usecase patterns - the combinations a user actually types
#   2. Risk-high pairs - flags that interact via the same code path
#      (cache + dry-run, GPU + cache, etc.)
#   3. Order-independence - Typer should not care about flag order
#
# All cases mock ``run_split`` so a full parametrize sweep is < 1 second.


class TestCliOptionCombinations:
    """Representative CLI flag combinations forward to SplitConfig."""

    @pytest.mark.parametrize(
        ("argv_extras", "expected_config"),
        [
            # --- Real usecase patterns ---
            # Inspect mode: check what would be detected without splitting.
            (["--dry-run", "-v"], {"dry_run": True}),
            # Force fresh inspect: ignore cache and dry-run.
            (
                ["--dry-run", "--no-cache", "-v"],
                {"dry_run": True, "no_cache": True},
            ),
            # Silent bulk processing with audio disabled.
            (["-q", "--no-audio"], {"no_audio": True}),
            # CPU debugging: verbose, force CPU, limit workers.
            (
                ["-v", "--no-gpu", "--workers", "4"],
                {"use_gpu": False, "workers": 4},
            ),
            # Custom output + GPU + workers (typical batch script).
            (
                ["--gpu", "--workers", "8"],
                {"use_gpu": True, "workers": 8},
            ),
            # Tuned detection parameters (no flags).
            (
                [
                    "--sample-interval",
                    "1.0",
                    "--blackout-threshold",
                    "20.0",
                    "--min-match-duration",
                    "180",
                ],
                {
                    "sample_interval": 1.0,
                    "blackout_threshold": 20.0,
                    "min_match_duration": 180.0,
                },
            ),
            # --- Risk-high pairs (shared code paths) ---
            # dry-run writes cache; --no-cache invalidates on read.
            (
                ["--dry-run", "--no-cache"],
                {"dry_run": True, "no_cache": True},
            ),
            # Force fresh GPU detection.
            (
                ["--gpu", "--no-cache"],
                {"use_gpu": True, "no_cache": True},
            ),
            # Full debug invocation.
            (
                ["-v", "--no-cache", "--dry-run"],
                {"no_cache": True, "dry_run": True},
            ),
            # Silent dry-run with fresh detection.
            (
                ["-q", "--dry-run", "--no-cache"],
                {"dry_run": True, "no_cache": True},
            ),
            # --- Three-way flag interaction ---
            # All three boolean flags with GPU.
            (
                ["--no-cache", "--dry-run", "--no-audio", "--gpu"],
                {
                    "no_cache": True,
                    "dry_run": True,
                    "no_audio": True,
                    "use_gpu": True,
                },
            ),
            # Value options + flag combination.
            (
                ["--sample-interval", "2.0", "--no-gpu", "--no-audio"],
                {
                    "sample_interval": 2.0,
                    "use_gpu": False,
                    "no_audio": True,
                },
            ),
        ],
    )
    @patch(MODULE)
    def test_cli_combination_forwards_to_config(
        self, mock_run_split, fake_video, argv_extras, expected_config
    ):
        """Combination of CLI flags forwards expected values to SplitConfig."""
        result = runner.invoke(app, ["split", str(fake_video), *argv_extras])
        assert result.exit_code == 0, (
            f"exit code {result.exit_code} for argv={argv_extras!r}: {result.stdout}"
        )
        config = mock_run_split.call_args[0][1]
        for key, expected in expected_config.items():
            actual = getattr(config, key)
            assert actual == expected, (
                f"argv={argv_extras!r}: expected {key}={expected!r}, got {actual!r}"
            )

    @pytest.mark.parametrize(
        "argv_order",
        [
            ["--dry-run", "-v"],
            ["-v", "--dry-run"],
            ["--no-gpu", "--no-audio", "-v"],
            ["-v", "--no-audio", "--no-gpu"],
            ["--no-audio", "-v", "--no-gpu"],
        ],
    )
    @patch(MODULE)
    def test_flag_order_is_independent(self, mock_run_split, fake_video, argv_order):
        """Flag order does not alter which config fields end up set."""
        result = runner.invoke(app, ["split", str(fake_video), *argv_order])
        assert result.exit_code == 0
        config = mock_run_split.call_args[0][1]
        # Regardless of order, presence of each flag flips its field.
        if "--dry-run" in argv_order:
            assert config.dry_run is True
        if "--no-gpu" in argv_order:
            assert config.use_gpu is False
        if "--no-audio" in argv_order:
            assert config.no_audio is True

    @patch(MODULE)
    def test_verbose_routed_as_kwarg_not_config_in_combo(
        self, mock_run_split, fake_video
    ):
        """Combinations containing -v route verbose as run_split kwarg.

        ``verbose`` is not a SplitConfig field -- it's a display-side
        kwarg for ``run_split``.  Any combination including ``-v`` must
        preserve that routing.
        """
        result = runner.invoke(
            app,
            ["split", str(fake_video), "--dry-run", "--no-cache", "-v"],
        )
        assert result.exit_code == 0
        assert mock_run_split.call_args[1]["verbose"] is True
        # Config still holds the flag values.
        config = mock_run_split.call_args[0][1]
        assert config.dry_run is True
        assert config.no_cache is True
