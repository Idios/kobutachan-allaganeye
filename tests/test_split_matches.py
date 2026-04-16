"""Tests for split_matches pipeline orchestration."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from allaganeye.commands.split_matches import (
    _auto_sample_interval,
    _load_cache,
    _save_cache,
    run_split,
)
from allaganeye.config import SplitConfig
from allaganeye.exceptions import AllaganEyeError, DetectionError, VideoProcessingError
from allaganeye.video.detector import MatchBoundary
from allaganeye.video.probe import ProbeResult

# Standard mock return values
PROBE_RESULT: ProbeResult = {
    "duration": 1800.0,
    "width": 1920,
    "height": 1080,
    "fps": 30.0,
    "codec": "h264",
    "audio_codec": "aac",
}

BOUNDARIES: list[MatchBoundary] = [
    {"start": 0.0, "end": 600.0, "type": "unknown"},
    {"start": 610.0, "end": 1200.0, "type": "unknown"},
]

MODULE = "allaganeye.commands.split_matches"


def _output_files(output_dir: Path) -> list[Path]:
    return [output_dir / "match_001.mp4", output_dir / "match_002.mp4"]


# --- Fixtures ---


@pytest.fixture(autouse=True)
def _mock_audio_scan(request):
    """Skip the real audio scan in every split_matches test by default.

    The audio pipeline requires a real video file with an audio track; the
    pipeline tests here use dummy paths, so the scan would fail with an
    ffmpeg error.  Tests that need to exercise the real ``_run_audio_scan``
    (e.g. to verify ``no_audio`` / error-handling branches) mark themselves
    with ``@pytest.mark.real_audio_scan`` to opt out.
    """
    if request.node.get_closest_marker("real_audio_scan") is not None:
        yield None
        return
    with patch(f"{MODULE}._run_audio_scan", return_value=None) as m:
        yield m


@pytest.fixture
def config(tmp_path):
    return SplitConfig(output_dir=tmp_path / "output", min_match_duration=60.0)


@pytest.fixture
def mock_pipeline():
    """Mock probe/detect/split for pipeline tests."""
    with (
        patch(f"{MODULE}.probe_video") as mock_probe,
        patch(f"{MODULE}.detect_match_boundaries") as mock_detect,
        patch(f"{MODULE}.split_video") as mock_split,
    ):
        mock_probe.return_value = PROBE_RESULT
        mock_detect.return_value = BOUNDARIES
        mock_split.return_value = [
            Path("output/match_001.mp4"),
            Path("output/match_002.mp4"),
        ]
        yield mock_probe, mock_detect, mock_split


# --- Pipeline happy path ---


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_pipeline_happy_path(mock_probe, mock_detect, mock_split, tmp_path):
    """Full pipeline calls probe, detect, split in order and writes metadata."""
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    video = Path("input.mp4")

    run_split(video, config)

    mock_probe.assert_called_once_with(video)
    mock_detect.assert_called_once()
    _, detect_kwargs = mock_detect.call_args
    assert detect_kwargs["duration_hint"] == PROBE_RESULT["duration"]
    assert detect_kwargs["sample_interval"] == config.sample_interval
    assert detect_kwargs["blackout_threshold"] == config.blackout_threshold
    assert detect_kwargs["min_match_duration"] == config.min_match_duration
    assert detect_kwargs["min_blackout_duration"] == config.min_blackout_duration
    assert detect_kwargs["use_gpu"] == config.use_gpu
    assert detect_kwargs["workers"] == config.workers
    assert detect_kwargs["src_resolution"] == (
        PROBE_RESULT["width"],
        PROBE_RESULT["height"],
    )
    mock_split.assert_called_once_with(video, BOUNDARIES, tmp_path)
    assert (tmp_path / "metadata.json").exists()


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_pipeline_metadata_json_content(mock_probe, mock_detect, mock_split, tmp_path):
    """metadata.json contains correct structure and values."""
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config)

    data = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    assert data["source"] == "input.mp4"
    assert data["source_duration"] == 1800.0
    assert len(data["matches"]) == 2
    m1 = data["matches"][0]
    assert m1["index"] == 1
    assert m1["start_time"] == 0.0
    assert m1["end_time"] == 600.0
    assert m1["duration"] == 600.0
    assert m1["type"] == "unknown"
    assert "match_001" in m1["output_file"]


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_pipeline_output_dir_created(mock_probe, mock_detect, mock_split, tmp_path):
    """Output directory is created if it doesn't exist."""
    output = tmp_path / "subdir" / "output"
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = [output / "match_001.mp4", output / "match_002.mp4"]
    config = SplitConfig(output_dir=output, min_match_duration=60.0)

    run_split(Path("input.mp4"), config)

    assert output.is_dir()


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_pipeline_dry_run(mock_probe, mock_detect, mock_split, tmp_path):
    """Dry-run mode skips split and metadata writing."""
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    config = SplitConfig(output_dir=tmp_path, dry_run=True, min_match_duration=60.0)

    run_split(Path("input.mp4"), config)

    mock_probe.assert_called_once()
    mock_detect.assert_called_once()
    mock_split.assert_not_called()
    assert not (tmp_path / "metadata.json").exists()


# --- Detection empty ---


def test_pipeline_no_boundaries():
    """Zero boundaries raises DetectionError."""
    with (
        patch(f"{MODULE}.probe_video") as mock_probe,
        patch(f"{MODULE}.detect_match_boundaries") as mock_detect,
    ):
        mock_probe.return_value = PROBE_RESULT
        mock_detect.return_value = []
        config = SplitConfig(min_match_duration=60.0)

        with pytest.raises(DetectionError, match="No match boundaries detected"):
            run_split(Path("input.mp4"), config)


# --- Error propagation ---


@patch(f"{MODULE}.probe_video")
def test_pipeline_probe_failure(mock_probe):
    """Probe failure propagates VideoProcessingError."""
    mock_probe.side_effect = VideoProcessingError("ffprobe failed")
    config = SplitConfig(min_match_duration=60.0)

    with pytest.raises(VideoProcessingError, match="ffprobe failed"):
        run_split(Path("input.mp4"), config)


@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_pipeline_detect_failure(mock_probe, mock_detect):
    """Detection failure propagates VideoProcessingError."""
    mock_probe.return_value = PROBE_RESULT
    mock_detect.side_effect = VideoProcessingError("Cannot open video")
    config = SplitConfig(min_match_duration=60.0)

    with pytest.raises(VideoProcessingError, match="Cannot open video"):
        run_split(Path("input.mp4"), config)


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_pipeline_split_failure(mock_probe, mock_detect, mock_split, tmp_path):
    """Split failure propagates VideoProcessingError."""
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.side_effect = VideoProcessingError("ffmpeg failed")
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    with pytest.raises(VideoProcessingError, match="ffmpeg failed"):
        run_split(Path("input.mp4"), config)


# --- Error handling (from PR #34) ---


class TestMkdirError:
    def test_mkdir_permission_error(self, config, mock_pipeline):
        with patch.object(
            Path, "mkdir", side_effect=PermissionError("Permission denied")
        ):
            with pytest.raises(AllaganEyeError, match="Cannot create output directory"):
                run_split(Path("video.mp4"), config)


class TestMetadataWriteError:
    def test_write_text_oserror(self, tmp_path, mock_pipeline):
        cfg = SplitConfig(output_dir=tmp_path / "output", min_match_duration=60.0)

        with patch.object(Path, "write_text", side_effect=OSError("Disk full")):
            with pytest.raises(AllaganEyeError, match="Cannot write metadata"):
                run_split(Path("video.mp4"), cfg)


# --- Verbose output ---


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_pipeline_verbose_output(mock_probe, mock_detect, mock_split, tmp_path, capsys):
    """Verbose mode prints probe details and gap info."""
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config, verbose=True)

    output = capsys.readouterr().out
    assert "Probing:" in output
    assert "Duration:" in output
    assert "Detecting match boundaries" in output
    assert "Match 1:" in output
    assert "Match 2:" in output


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_pipeline_default_output(mock_probe, mock_detect, mock_split, tmp_path, capsys):
    """Default mode prints probing status, match list, but not metadata details."""
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config)

    output = capsys.readouterr().out
    assert "Probing:" in output
    assert "Detected 2 match(es)" in output
    assert "Match 1:" in output
    assert "Match 2:" in output
    # Metadata details only in verbose
    assert "Duration:" not in output


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_pipeline_quiet_output(mock_probe, mock_detect, mock_split, tmp_path, capsys):
    """Quiet mode suppresses progress but still shows output files."""
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config, quiet=True)

    output = capsys.readouterr().out
    assert "Probing:" not in output
    assert "Detecting match boundaries" not in output
    assert "Match 1:" not in output
    # Output files still shown
    assert "Output:" in output


# --- Auto sample interval ---


class TestAutoSampleInterval:
    def test_short_video_unchanged(self):
        assert _auto_sample_interval(1800.0, 1.0) == 1.0

    def test_one_hour_boundary_unchanged(self):
        assert _auto_sample_interval(3600.0, 1.0) == 1.0

    def test_over_one_hour(self):
        assert _auto_sample_interval(3601.0, 1.0) == 2.0

    def test_two_hour_boundary(self):
        assert _auto_sample_interval(7200.0, 1.0) == 2.0

    def test_over_two_hours(self):
        assert _auto_sample_interval(7201.0, 1.0) == 3.0

    def test_custom_interval_not_adjusted(self):
        """User-specified interval is never auto-adjusted."""
        assert _auto_sample_interval(9000.0, 0.5) == 0.5
        assert _auto_sample_interval(9000.0, 2.0) == 2.0


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_pipeline_auto_interval_long_video(
    mock_probe, mock_detect, mock_split, tmp_path
):
    """Long video (>1h) auto-adjusts sample_interval from 1.0 to 2.0."""
    probe = {**PROBE_RESULT, "duration": 5400.0}  # 1.5h
    mock_probe.return_value = probe
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config)

    mock_detect.assert_called_once()
    _, detect_kwargs = mock_detect.call_args
    assert detect_kwargs["sample_interval"] == 2.0
    assert detect_kwargs["duration_hint"] == 5400.0


# --- Config forwarding ---


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_pipeline_config_params_forwarded(
    mock_probe, mock_detect, mock_split, tmp_path
):
    """Non-default config values are forwarded to detect_match_boundaries."""
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(
        output_dir=tmp_path,
        sample_interval=2.0,
        blackout_threshold=20.0,
        min_match_duration=120.0,
    )

    run_split(Path("input.mp4"), config)

    mock_detect.assert_called_once()
    _, detect_kwargs = mock_detect.call_args
    assert detect_kwargs["sample_interval"] == 2.0
    assert detect_kwargs["blackout_threshold"] == 20.0
    assert detect_kwargs["min_match_duration"] == 120.0
    assert detect_kwargs["min_blackout_duration"] == 3.0


# ============================================================
# Detection cache tests
# ============================================================


@pytest.fixture
def cache_video(tmp_path):
    """Create a real video file for cache tests."""
    video = tmp_path / "test.mp4"
    video.write_bytes(b"\x00" * 1024)
    return video


@pytest.fixture
def cache_config(tmp_path):
    return SplitConfig(
        output_dir=tmp_path / "output",
        sample_interval=1.0,
        blackout_threshold=15.0,
        min_match_duration=300.0,
        min_blackout_duration=3.0,
    )


CACHE_BOUNDARIES: list[MatchBoundary] = [
    {"start": 0.0, "end": 600.0, "type": "fl_match"},
    {"start": 700.0, "end": 1200.0, "type": "fl_match"},
]


class TestCacheRoundTrip:
    def test_save_and_load(self, cache_video, cache_config, tmp_path):
        """Save -> load round-trip restores boundaries."""
        cache_path = tmp_path / "output" / ".detection_cache.json"
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, cache_config, CACHE_BOUNDARIES
        )
        result = _load_cache(cache_path, cache_video, 1.0, cache_config)
        assert result == CACHE_BOUNDARIES

    def test_size_mismatch(self, cache_video, cache_config, tmp_path):
        """source_size mismatch -> None."""
        cache_path = tmp_path / "output" / ".detection_cache.json"
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, cache_config, CACHE_BOUNDARIES
        )
        # Change file size
        cache_video.write_bytes(b"\x00" * 2048)
        assert _load_cache(cache_path, cache_video, 1.0, cache_config) is None

    def test_mtime_mismatch(self, cache_video, cache_config, tmp_path):
        """source_mtime mismatch -> None."""
        cache_path = tmp_path / "output" / ".detection_cache.json"
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, cache_config, CACHE_BOUNDARIES
        )
        # Modify cache to have wrong mtime
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        data["source_mtime"] = 0.0
        cache_path.write_text(json.dumps(data), encoding="utf-8")
        assert _load_cache(cache_path, cache_video, 1.0, cache_config) is None

    def test_param_mismatch_threshold(self, cache_video, cache_config, tmp_path):
        """blackout_threshold mismatch -> None."""
        cache_path = tmp_path / "output" / ".detection_cache.json"
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, cache_config, CACHE_BOUNDARIES
        )
        different_config = SplitConfig(
            output_dir=tmp_path / "output", blackout_threshold=20.0
        )
        assert _load_cache(cache_path, cache_video, 1.0, different_config) is None

    def test_param_mismatch_interval(self, cache_video, cache_config, tmp_path):
        """sample_interval mismatch -> None."""
        cache_path = tmp_path / "output" / ".detection_cache.json"
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, cache_config, CACHE_BOUNDARIES
        )
        assert _load_cache(cache_path, cache_video, 2.0, cache_config) is None

    def test_param_mismatch_no_audio(self, cache_video, cache_config, tmp_path):
        """no_audio mismatch -> None (cache must be keyed to audio pipeline, #288)."""
        cache_path = tmp_path / "output" / ".detection_cache.json"
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, cache_config, CACHE_BOUNDARIES
        )
        different_config = SplitConfig(output_dir=tmp_path / "output", no_audio=True)
        assert _load_cache(cache_path, cache_video, 1.0, different_config) is None

    def test_version_mismatch(self, cache_video, cache_config, tmp_path):
        """cache_version mismatch -> None."""
        cache_path = tmp_path / "output" / ".detection_cache.json"
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, cache_config, CACHE_BOUNDARIES
        )
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        data["cache_version"] = 999
        cache_path.write_text(json.dumps(data), encoding="utf-8")
        assert _load_cache(cache_path, cache_video, 1.0, cache_config) is None

    def test_path_mismatch(self, cache_video, cache_config, tmp_path):
        """source path mismatch -> None."""
        cache_path = tmp_path / "output" / ".detection_cache.json"
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, cache_config, CACHE_BOUNDARIES
        )
        other_video = tmp_path / "other.mp4"
        other_video.write_bytes(b"\x00" * 1024)
        assert _load_cache(cache_path, other_video, 1.0, cache_config) is None

    def test_file_not_found(self, cache_video, cache_config, tmp_path):
        """Cache file doesn't exist -> None."""
        cache_path = tmp_path / "nonexistent" / ".detection_cache.json"
        assert _load_cache(cache_path, cache_video, 1.0, cache_config) is None

    def test_corrupted_json(self, cache_video, cache_config, tmp_path):
        """Corrupted cache file -> None (no exception)."""
        cache_path = tmp_path / "output" / ".detection_cache.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text("not valid json{{{", encoding="utf-8")
        assert _load_cache(cache_path, cache_video, 1.0, cache_config) is None


# --- Progressbar tests (PR #233 gap coverage) ---


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_progressbar_length(mock_probe, mock_detect, mock_split, tmp_path):
    """Progressbar length equals estimated_samples, not frame count."""
    mock_probe.return_value = {**PROBE_RESULT, "duration": 1800.0}
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    with patch("typer.progressbar") as mock_bar:
        mock_bar.return_value.__enter__ = lambda s: s
        mock_bar.return_value.__exit__ = lambda s, *a: None
        mock_bar.return_value.update = lambda n: None
        run_split(Path("input.mp4"), config)

    # interval=1.0 for 1800s -> estimated_samples = 1800
    mock_bar.assert_called_once()
    assert mock_bar.call_args[1]["length"] == 1800


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_progressbar_tiny_video(mock_probe, mock_detect, mock_split, tmp_path):
    """Progressbar length is at least 1 for very short videos."""
    mock_probe.return_value = {**PROBE_RESULT, "duration": 0.5}
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    with patch("typer.progressbar") as mock_bar:
        mock_bar.return_value.__enter__ = lambda s: s
        mock_bar.return_value.__exit__ = lambda s, *a: None
        mock_bar.return_value.update = lambda n: None
        run_split(Path("input.mp4"), config)

    # int(0.5 / 1.0) = 0, max(1, 0) = 1
    mock_bar.assert_called_once()
    assert mock_bar.call_args[1]["length"] == 1


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_progressbar_auto_interval(mock_probe, mock_detect, mock_split, tmp_path):
    """Progressbar length uses auto-adjusted interval for long videos."""
    mock_probe.return_value = {**PROBE_RESULT, "duration": 7300.0}  # > 2h
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    with patch("typer.progressbar") as mock_bar:
        mock_bar.return_value.__enter__ = lambda s: s
        mock_bar.return_value.__exit__ = lambda s, *a: None
        mock_bar.return_value.update = lambda n: None
        run_split(Path("input.mp4"), config)

    # auto interval = 3.0 for > 2h, estimated_samples = int(7300/3.0) = 2433
    mock_bar.assert_called_once()
    assert mock_bar.call_args[1]["length"] == 2433


class TestCachePipeline:
    @patch(f"{MODULE}.split_video")
    @patch(f"{MODULE}.detect_match_boundaries")
    @patch(f"{MODULE}.probe_video")
    def test_dry_run_saves_cache(self, mock_probe, mock_detect, mock_split, tmp_path):
        """dry-run saves .detection_cache.json."""
        video = tmp_path / "input.mp4"
        video.write_bytes(b"\x00" * 512)
        mock_probe.return_value = PROBE_RESULT
        mock_detect.return_value = BOUNDARIES
        config = SplitConfig(output_dir=tmp_path / "output", dry_run=True)
        run_split(video, config)
        assert (tmp_path / "output" / ".detection_cache.json").exists()

    @patch(f"{MODULE}.split_video")
    @patch(f"{MODULE}.detect_match_boundaries")
    @patch(f"{MODULE}.probe_video")
    def test_second_run_uses_cache(self, mock_probe, mock_detect, mock_split, tmp_path):
        """2nd run skips detection when cache is valid."""
        video = tmp_path / "input.mp4"
        video.write_bytes(b"\x00" * 512)
        mock_probe.return_value = PROBE_RESULT
        mock_detect.return_value = BOUNDARIES
        out = tmp_path / "output"
        mock_split.return_value = [out / "match_001.mp4", out / "match_002.mp4"]
        config = SplitConfig(output_dir=out, min_match_duration=60.0)
        # 1st run: detect is called
        run_split(video, config)
        assert mock_detect.call_count == 1
        # 2nd run: detect is NOT called (cached)
        mock_split.return_value = [out / "match_001.mp4", out / "match_002.mp4"]
        run_split(video, config)
        assert mock_detect.call_count == 1  # still 1

    @patch(f"{MODULE}.split_video")
    @patch(f"{MODULE}.detect_match_boundaries")
    @patch(f"{MODULE}.probe_video")
    def test_param_change_triggers_redetect(
        self, mock_probe, mock_detect, mock_split, tmp_path
    ):
        """Changed parameters invalidate cache -> re-detect."""
        video = tmp_path / "input.mp4"
        video.write_bytes(b"\x00" * 512)
        mock_probe.return_value = PROBE_RESULT
        mock_detect.return_value = BOUNDARIES
        config1 = SplitConfig(output_dir=tmp_path / "output", dry_run=True)
        run_split(video, config1)
        assert mock_detect.call_count == 1
        # 2nd run with different threshold
        config2 = SplitConfig(
            output_dir=tmp_path / "output", blackout_threshold=20.0, dry_run=True
        )
        run_split(video, config2)
        assert mock_detect.call_count == 2

    @patch(f"{MODULE}.split_video")
    @patch(f"{MODULE}.detect_match_boundaries")
    @patch(f"{MODULE}.probe_video")
    def test_no_cache_flag(self, mock_probe, mock_detect, mock_split, tmp_path):
        """--no-cache ignores existing cache."""
        video = tmp_path / "input.mp4"
        video.write_bytes(b"\x00" * 512)
        mock_probe.return_value = PROBE_RESULT
        mock_detect.return_value = BOUNDARIES
        config = SplitConfig(output_dir=tmp_path / "output", dry_run=True)
        run_split(video, config)
        assert mock_detect.call_count == 1
        # 2nd run with --no-cache
        config_no_cache = SplitConfig(
            output_dir=tmp_path / "output", dry_run=True, no_cache=True
        )
        run_split(video, config_no_cache)
        assert mock_detect.call_count == 2


# --- Audio scan integration (#288) ---


class TestAudioScanIntegration:
    """Audio scan pipeline wiring in run_split and _run_audio_scan (#288)."""

    @patch(f"{MODULE}.split_video")
    @patch(f"{MODULE}.detect_match_boundaries")
    @patch(f"{MODULE}.probe_video")
    def test_audio_hits_forwarded_to_detect(
        self, mock_probe, mock_detect, mock_split, tmp_path, _mock_audio_scan
    ):
        """Scan output is forwarded to detect_match_boundaries via audio_hits."""
        hits = [{"timestamp": 50.0, "similarity": 0.72}]
        _mock_audio_scan.return_value = hits
        mock_probe.return_value = PROBE_RESULT
        mock_detect.return_value = BOUNDARIES
        mock_split.return_value = _output_files(tmp_path)
        config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

        run_split(Path("input.mp4"), config)

        _, detect_kwargs = mock_detect.call_args
        assert detect_kwargs["audio_hits"] == hits

    @pytest.mark.real_audio_scan
    def test_run_audio_scan_returns_none_when_disabled(self, tmp_path):
        """config.no_audio=True skips audio scan without invoking scan_fanfare_hits."""
        from allaganeye.commands.split_matches import _run_audio_scan

        config = SplitConfig(
            output_dir=tmp_path, min_match_duration=60.0, no_audio=True
        )
        result = _run_audio_scan(Path("input.mp4"), config, show=False, verbose=False)
        assert result is None

    @pytest.mark.real_audio_scan
    @patch("allaganeye.audio.scan.scan_fanfare_hits")
    def test_run_audio_scan_returns_hits_on_success(self, mock_scan, tmp_path):
        """Successful scan returns hits verbatim."""
        from allaganeye.commands.split_matches import _run_audio_scan

        hits = [{"timestamp": 100.0, "similarity": 0.7}]
        mock_scan.return_value = hits
        config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

        result = _run_audio_scan(Path("input.mp4"), config, show=False, verbose=False)
        assert result == hits
        mock_scan.assert_called_once()

    @pytest.mark.real_audio_scan
    @patch("allaganeye.audio.scan.scan_fanfare_hits")
    def test_run_audio_scan_falls_back_on_video_processing_error(
        self, mock_scan, tmp_path
    ):
        """VideoProcessingError is caught; returns None instead of propagating."""
        from allaganeye.commands.split_matches import _run_audio_scan

        mock_scan.side_effect = VideoProcessingError("no audio track")
        config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

        result = _run_audio_scan(Path("input.mp4"), config, show=False, verbose=False)
        assert result is None
