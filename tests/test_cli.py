"""Tests for CLI entry point."""

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from allaganeye.cli import app
from allaganeye.exceptions import DetectionError, VideoProcessingError

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
    result = runner.invoke(
        app, ["split", str(fake_file), "--min-match-duration", "-1"]
    )
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
    assert config.dry_run is False
    assert kwargs["verbose"] is False


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
    result = runner.invoke(
        app, ["split", str(fake_video), "--sample-interval", "2.5"]
    )

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
def test_split_dry_run(mock_run_split, fake_video):
    """--dry-run flag sets config.dry_run=True."""
    result = runner.invoke(app, ["split", str(fake_video), "--dry-run"])

    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.dry_run is True


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
