"""Tests for CLI entry point."""

from typer.testing import CliRunner

from allaganeye.cli import app

runner = CliRunner()


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


def test_split_negative_sample_interval(tmp_path):
    fake_file = tmp_path / "video.mp4"
    fake_file.write_bytes(b"\x00")
    result = runner.invoke(app, ["split", str(fake_file), "--sample-interval", "-1"])
    assert result.exit_code == 2


def test_split_zero_sample_interval(tmp_path):
    fake_file = tmp_path / "video.mp4"
    fake_file.write_bytes(b"\x00")
    result = runner.invoke(app, ["split", str(fake_file), "--sample-interval", "0"])
    assert result.exit_code == 2


def test_split_blackout_threshold_over_255(tmp_path):
    fake_file = tmp_path / "video.mp4"
    fake_file.write_bytes(b"\x00")
    result = runner.invoke(
        app, ["split", str(fake_file), "--blackout-threshold", "300"]
    )
    assert result.exit_code == 2


def test_split_negative_min_match_duration(tmp_path):
    fake_file = tmp_path / "video.mp4"
    fake_file.write_bytes(b"\x00")
    result = runner.invoke(app, ["split", str(fake_file), "--min-match-duration", "-1"])
    assert result.exit_code == 2
