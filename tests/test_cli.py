"""Tests for CLI entry point."""

from pathlib import Path
from unittest.mock import patch

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
    assert config.use_gpu is False
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
