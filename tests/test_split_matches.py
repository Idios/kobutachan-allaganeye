"""Tests for split_matches pipeline orchestration."""

import json
import re
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from allaganeye.commands.split_matches import (
    _ETAProgressBar,
    _PROGRESS_LABEL_WIDTH,
    _auto_sample_interval,
    _eta_progressbar,
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
    "fps_num": 30,
    "fps_den": 1,
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
    # Auto-selected GPU for h264 codec (#334)
    assert detect_kwargs["use_gpu"] is True
    assert detect_kwargs["workers"] == config.workers
    assert detect_kwargs["src_resolution"] == (
        PROBE_RESULT["width"],
        PROBE_RESULT["height"],
    )
    mock_split.assert_called_once()
    split_args = mock_split.call_args
    assert split_args[0] == (video, BOUNDARIES, tmp_path)
    assert (tmp_path / "metadata.json").exists()


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_pipeline_threads_vtuber_default_false(
    mock_probe, mock_detect, mock_split, tmp_path
):
    """config.vtuber=False (default) reaches detect_match_boundaries (L3 B6)."""
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config)

    _, detect_kwargs = mock_detect.call_args
    assert detect_kwargs["vtuber"] is False


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_pipeline_threads_vtuber_true(mock_probe, mock_detect, mock_split, tmp_path):
    """config.vtuber=True is threaded into detect_kwargs (L3 B6)."""
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0, vtuber=True)

    run_split(Path("input.mp4"), config)

    _, detect_kwargs = mock_detect.call_args
    assert detect_kwargs["vtuber"] is True


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
    # #465 review: source_fps is propagated from probe -> metadata.json
    assert data["source_fps"] == 30.0
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
def test_match_list_marks_unknown_type(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """Match list marks unknown-type segments with '[unknown]' (#382).

    Users need to see at a glance which matches are uncertain (recording
    started/ended mid-match) vs full fl_match runs without opening
    metadata.json.  fl_match segments stay unmarked to avoid noise.
    """
    mixed: list[MatchBoundary] = [
        {"start": 0.0, "end": 917.0, "type": "unknown"},
        {"start": 1129.0, "end": 2091.0, "type": "fl_match"},
        {"start": 2437.5, "end": 3473.0, "type": "fl_match"},
    ]
    mock_probe.return_value = {**PROBE_RESULT, "duration": 4000.0}
    mock_detect.return_value = mixed
    mock_split.return_value = [tmp_path / f"match_{i:03d}.mp4" for i in range(1, 4)]
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config)
    out = capsys.readouterr().out

    # The unknown-type row must carry the marker; the fl_match rows must not.
    lines = [line for line in out.splitlines() if line.strip().startswith("Match ")]
    assert len(lines) == 3, f"expected 3 Match lines, got: {lines!r}"
    assert "[unknown]" in lines[0], f"Match 1 should be marked: {lines[0]!r}"
    assert "[unknown]" not in lines[1], f"Match 2 should be clean: {lines[1]!r}"
    assert "[unknown]" not in lines[2], f"Match 3 should be clean: {lines[2]!r}"


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_match_list_no_marker_when_all_fl_match(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """When every match is fl_match, no '[unknown]' markers appear (#382)."""
    all_fl: list[MatchBoundary] = [
        {"start": 0.0, "end": 600.0, "type": "fl_match"},
        {"start": 610.0, "end": 1200.0, "type": "fl_match"},
    ]
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = all_fl
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config)
    out = capsys.readouterr().out
    assert "[unknown]" not in out


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_match_list_handles_missing_type_key(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """Boundary dict without ``type`` key yields no marker and no error (#382).

    Legacy cache / older metadata payloads may ship MatchBoundary-shaped
    dicts that omit ``type``.  The display code uses ``b.get("type")``
    defensively; this test pins that contract so a future refactor to
    ``b["type"]`` fails loudly here rather than KeyError-ing at runtime.
    """
    no_type_boundaries: list[MatchBoundary] = [
        {"start": 0.0, "end": 600.0},  # type: ignore[typeddict-item]
        {"start": 610.0, "end": 1200.0},  # type: ignore[typeddict-item]
    ]
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = no_type_boundaries
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config)
    out = capsys.readouterr().out

    # No marker, no crash, and the Match lines still render.
    assert "[unknown]" not in out
    match_lines = [ln for ln in out.splitlines() if ln.strip().startswith("Match ")]
    assert len(match_lines) == 2


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_metadata_output_file_uses_posix_separator(
    mock_probe, mock_detect, mock_split, tmp_path
):
    """metadata.json output_file uses POSIX '/' separator on all platforms (#371).

    JSON is a cross-platform data-interchange format; backslashes in paths
    break Linux/macOS consumers of metadata.json (e.g. the L2/L3 pipeline).
    """
    nested = tmp_path / "sub" / "output"
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = [
        nested / "match_001.mp4",
        nested / "match_002.mp4",
    ]
    config = SplitConfig(output_dir=nested, min_match_duration=60.0)

    run_split(Path("input.mp4"), config)

    data = json.loads((nested / "metadata.json").read_text(encoding="utf-8"))
    for m in data["matches"]:
        assert "\\" not in m["output_file"], (
            f"output_file must not contain backslashes: {m['output_file']!r}"
        )
        assert "/" in m["output_file"], (
            f"output_file must contain forward slashes: {m['output_file']!r}"
        )


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_metadata_gaps_have_raw_seconds(mock_probe, mock_detect, mock_split, tmp_path):
    """metadata.json gaps carry raw start_time/end_time/duration (#369).

    L2/L3 pipelines need machine-readable raw seconds to avoid re-parsing
    display strings. Shape must match matches[] (raw + display pairs).
    """
    boundaries_with_gap: list[MatchBoundary] = [
        {"start": 0.0, "end": 600.0, "type": "unknown"},
        {"start": 1200.5, "end": 1800.0, "type": "unknown"},
    ]
    mock_probe.return_value = {**PROBE_RESULT, "duration": 2000.0}
    mock_detect.return_value = boundaries_with_gap
    mock_split.return_value = [
        tmp_path / "match_001.mp4",
        tmp_path / "match_002.mp4",
    ]
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config)

    data = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    assert len(data["gaps"]) == 1, "expected one significant gap >= 300s"
    gap = data["gaps"][0]

    for key in ("start_time", "end_time", "duration"):
        assert key in gap, f"gaps[] missing raw key {key!r}: {list(gap)!r}"
        assert isinstance(gap[key], float), (
            f"gaps[0].{key} must be float, got {type(gap[key]).__name__}"
        )

    # Raw fields must agree with display fields (same event, same value).
    assert gap["start_time"] == 600.0
    assert gap["end_time"] == 1200.5
    assert abs(gap["duration"] - (gap["end_time"] - gap["start_time"])) < 1e-6


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_metadata_gaps_preserve_display_fields(
    mock_probe, mock_detect, mock_split, tmp_path
):
    """gaps[] retains start_display / end_display / duration_display (#369).

    Adding raw fields must not silently remove display fields.  Callers
    rendering human-readable output rely on them.
    """
    boundaries: list[MatchBoundary] = [
        {"start": 0.0, "end": 600.0, "type": "unknown"},
        {"start": 1200.5, "end": 1800.0, "type": "unknown"},
    ]
    mock_probe.return_value = {**PROBE_RESULT, "duration": 2000.0}
    mock_detect.return_value = boundaries
    mock_split.return_value = [
        tmp_path / "match_001.mp4",
        tmp_path / "match_002.mp4",
    ]
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config)

    data = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    gap = data["gaps"][0]

    for key in ("start_display", "end_display", "duration_display"):
        assert key in gap, f"gaps[] missing display key {key!r}: {list(gap)!r}"
        assert isinstance(gap[key], str), (
            f"gaps[0].{key} must be str, got {type(gap[key]).__name__}"
        )
        assert gap[key], f"gaps[0].{key} must not be empty"


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_metadata_gaps_display_formatted_from_raw(
    mock_probe, mock_detect, mock_split, tmp_path
):
    """display strings are formatted from the paired raw values (#369).

    Guards against raw/display variable swaps where the pair ships the
    wrong time for one side.  Uses the actual formatters to compute the
    expected display values.
    """
    from allaganeye.commands.split_matches import (
        _format_duration,
        _format_timestamp,
    )

    boundaries: list[MatchBoundary] = [
        {"start": 0.0, "end": 600.0, "type": "unknown"},
        {"start": 1200.5, "end": 1800.0, "type": "unknown"},
    ]
    mock_probe.return_value = {**PROBE_RESULT, "duration": 2000.0}
    mock_detect.return_value = boundaries
    mock_split.return_value = [
        tmp_path / "match_001.mp4",
        tmp_path / "match_002.mp4",
    ]
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config)

    data = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    gap = data["gaps"][0]

    assert gap["start_display"] == _format_timestamp(gap["start_time"])
    assert gap["end_display"] == _format_timestamp(gap["end_time"])
    assert gap["duration_display"] == _format_duration(gap["duration"])


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_metadata_gaps_shape_consistent_across_multiple_gaps(
    mock_probe, mock_detect, mock_split, tmp_path
):
    """Every element of gaps[] shares the same raw+display shape (#369).

    Single-gap tests cannot catch shape drift introduced only for the
    first or last element.  Use 3 matches -> 2 gaps and iterate.
    """
    boundaries: list[MatchBoundary] = [
        {"start": 0.0, "end": 400.0, "type": "unknown"},
        {"start": 800.0, "end": 1200.0, "type": "unknown"},
        {"start": 1600.0, "end": 2000.0, "type": "unknown"},
    ]
    mock_probe.return_value = {**PROBE_RESULT, "duration": 2200.0}
    mock_detect.return_value = boundaries
    mock_split.return_value = [tmp_path / f"match_{i:03d}.mp4" for i in range(1, 4)]
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config)

    data = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    gaps = data["gaps"]
    assert len(gaps) == 2, f"expected 2 gaps between 3 matches, got {len(gaps)}"

    expected_keys = {
        "start_time",
        "end_time",
        "duration",
        "start_display",
        "end_display",
        "duration_display",
    }
    for i, gap in enumerate(gaps):
        assert set(gap.keys()) == expected_keys, (
            f"gaps[{i}] keys diverged: {sorted(gap.keys())!r}"
        )
        for key in ("start_time", "end_time", "duration"):
            assert isinstance(gap[key], float)
        for key in ("start_display", "end_display", "duration_display"):
            assert isinstance(gap[key], str) and gap[key]

    # Gaps must be in temporal order (sanity): 400->800 precedes 1200->1600.
    assert gaps[0]["start_time"] == 400.0
    assert gaps[0]["end_time"] == 800.0
    assert gaps[1]["start_time"] == 1200.0
    assert gaps[1]["end_time"] == 1600.0


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_metadata_detection_params_present(
    mock_probe, mock_detect, mock_split, tmp_path
):
    """metadata.json records detection_params and detected_at (#370)."""
    from datetime import UTC, datetime

    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(
        output_dir=tmp_path,
        sample_interval=1.5,
        blackout_threshold=20.0,
        min_match_duration=120.0,
        min_blackout_duration=4.0,
        no_audio=True,
        use_gpu=True,
        workers=8,
    )

    run_split(Path("input.mp4"), config)

    data = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))

    assert "detection_params" in data, "metadata.json missing detection_params"
    params = data["detection_params"]
    expected_keys = {
        "sample_interval",
        "blackout_threshold",
        "min_match_duration",
        "min_blackout_duration",
        "no_audio",
        "use_gpu",
        "workers",
    }
    assert set(params) == expected_keys, (
        f"detection_params keys mismatch: {set(params) ^ expected_keys}"
    )

    # Values must reflect runtime SplitConfig.  sample_interval is the
    # effective (post-auto-adjust) value to stay in sync with
    # .detection_cache.json params; with 1800s duration + 1.5s requested,
    # auto-adjust is a no-op so it equals the requested value.
    assert params["sample_interval"] == 1.5
    assert params["blackout_threshold"] == 20.0
    assert params["min_match_duration"] == 120.0
    assert params["min_blackout_duration"] == 4.0
    assert params["no_audio"] is True
    assert params["use_gpu"] is True
    assert params["workers"] == 8

    # detected_at is ISO 8601 UTC with 'Z' suffix and parseable.
    detected_at = data["detected_at"]
    assert isinstance(detected_at, str), "detected_at must be string"
    assert detected_at.endswith("Z"), f"detected_at must end with 'Z': {detected_at!r}"
    parsed = datetime.fromisoformat(detected_at.replace("Z", "+00:00"))
    offset = parsed.utcoffset()
    assert offset is not None and offset.total_seconds() == 0, (
        "detected_at must be UTC (offset 0)"
    )
    # Sanity: within one minute of wall clock.
    delta = abs((datetime.now(UTC) - parsed).total_seconds())
    assert delta < 60, f"detected_at drifted from now by {delta}s"

    # #586 -- detection_started_at / detection_completed_at are written
    # for the GUI elapsed column. started_at is the same value as
    # detected_at (legacy alias retained for backward compat); completed_at
    # is captured immediately before the writer flushes metadata.json.
    assert data["detection_started_at"] == detected_at
    completed_at = data["detection_completed_at"]
    assert isinstance(completed_at, str), "detection_completed_at must be string"
    assert completed_at.endswith("Z"), (
        f"detection_completed_at must end with 'Z': {completed_at!r}"
    )
    parsed_completed = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
    started_parsed = datetime.fromisoformat(detected_at.replace("Z", "+00:00"))
    assert parsed_completed >= started_parsed, (
        "detection_completed_at must be >= detection_started_at"
    )


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_metadata_detection_params_none_serializes_null(
    mock_probe, mock_detect, mock_split, tmp_path
):
    """None values (workers=auto, use_gpu=auto) serialize as JSON null (#370)."""
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(
        output_dir=tmp_path,
        min_match_duration=60.0,
        workers=None,
        use_gpu=None,  # type: ignore[arg-type]
    )

    run_split(Path("input.mp4"), config)

    data = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    assert data["detection_params"]["workers"] is None
    assert data["detection_params"]["use_gpu"] is None


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_metadata_detection_params_match_cache(
    mock_probe, mock_detect, mock_split, tmp_path
):
    """metadata.json detection_params match .detection_cache.json params (#370).

    Overlapping keys must have identical values so L3 consumers can treat
    cache and metadata interchangeably.
    """
    # _save_cache requires the source file to exist for stat().
    source = tmp_path / "input.mp4"
    source.write_bytes(b"")
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(
        output_dir=tmp_path,
        sample_interval=2.0,
        blackout_threshold=18.0,
        min_match_duration=180.0,
        min_blackout_duration=2.5,
        no_audio=False,
    )

    run_split(source, config)

    meta = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    cache = json.loads((tmp_path / ".detection_cache.json").read_text(encoding="utf-8"))

    shared_keys = (
        "sample_interval",
        "blackout_threshold",
        "min_match_duration",
        "min_blackout_duration",
        "no_audio",
    )
    for key in shared_keys:
        assert meta["detection_params"][key] == cache["params"][key], (
            f"detection_params/{key} diverges from cache/{key}"
        )


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


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_pipeline_dry_run_display(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """Dry-run shows early notice and no Splitting bar (#331)."""
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    config = SplitConfig(output_dir=tmp_path, dry_run=True, min_match_duration=60.0)

    run_split(Path("input.mp4"), config)

    output = capsys.readouterr().out
    assert "[dry-run]" in output
    assert "Splitting" not in output
    assert "Dry run: skipping split" in output


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_splitting_bar_shown_in_normal_run(
    mock_probe, mock_detect, mock_split, tmp_path
):
    """Normal (non-dry-run) run opens a Splitting progress bar (#331).

    Guards the UX contract from issue #331: split phase must have
    visible progress so the user isn't left wondering what's happening
    after Detected.
    """
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    with patch(f"{MODULE}._ETAProgressBar") as mock_bar:
        mock_bar.return_value.__enter__ = lambda s: s
        mock_bar.return_value.__exit__ = lambda s, *a: None
        mock_bar.return_value.update = lambda n: None
        run_split(Path("input.mp4"), config)

    labels = [call.kwargs.get("label", "") for call in mock_bar.call_args_list]
    assert any("Splitting" in label for label in labels), (
        f"Expected a Splitting progress bar, got labels: {labels}"
    )


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_progressbar_shows_eta_label(mock_probe, mock_detect, mock_split, tmp_path):
    """Progress bars enable ETA and percent display in CPU mode (#329).

    Guards the contract from issue #329: the user must be able to tell
    that the time shown is ETA, via ``show_eta=True`` on the
    ``_ETAProgressBar`` subclass (refactored from ``click.progressbar``
    factory in #365).
    GPU mode deliberately suppresses click's ETA on the Detecting bar
    (#438); that variant is covered by
    :func:`test_progressbar_suppresses_click_eta_on_detecting_in_gpu_mode`.
    """
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    # CPU mode explicitly -- avoid codec auto-select pulling in GPU path
    # (which would suppress click ETA on Detecting per #438).
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0, use_gpu=False)

    with patch(f"{MODULE}._ETAProgressBar") as mock_bar:
        mock_bar.return_value.__enter__ = lambda s: s
        mock_bar.return_value.__exit__ = lambda s, *a: None
        mock_bar.return_value.update = lambda n: None
        run_split(Path("input.mp4"), config)

    # Every bar created via _eta_progressbar must enable eta + percent
    assert mock_bar.call_count >= 1
    for call in mock_bar.call_args_list:
        assert call.kwargs.get("show_eta") is True, (
            f"Expected show_eta=True, got {call.kwargs}"
        )
        assert call.kwargs.get("show_percent") is True


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_progressbar_suppresses_click_eta_on_detecting_in_gpu_mode(
    mock_probe, mock_detect, mock_split, tmp_path
):
    """GPU mode sets ``show_eta=False`` on the Detecting bar only (#438).

    GPU chunk completion is non-linear (long stall, then burst) so
    click's rate estimator produces absurd ETAs like ``3d 08:08:52``.
    The Detecting bar supplies its own ETA in the label; click's
    built-in ETA must be off.  Refining / Scorebar / Splitting stay
    at ``show_eta=True`` because their progress is linear.
    """
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0, use_gpu=True)

    with patch(f"{MODULE}._ETAProgressBar") as mock_bar:
        mock_bar.return_value.__enter__ = lambda s: s
        mock_bar.return_value.__exit__ = lambda s, *a: None
        mock_bar.return_value.update = lambda n: None
        run_split(Path("input.mp4"), config)

    assert mock_bar.call_count >= 1

    # Partition bar creations by label prefix for cleaner assertions.
    detecting_calls = [
        c
        for c in mock_bar.call_args_list
        if c.kwargs.get("label", "").strip().startswith("Detecting")
    ]
    non_detecting_calls = [
        c
        for c in mock_bar.call_args_list
        if not c.kwargs.get("label", "").strip().startswith("Detecting")
    ]

    assert detecting_calls, "Detecting bar was not created"
    for call in detecting_calls:
        assert call.kwargs.get("show_eta") is False, (
            "GPU mode must disable click's built-in ETA on Detecting "
            f"(#438); got {call.kwargs}"
        )

    for call in non_detecting_calls:
        assert call.kwargs.get("show_eta") is True, (
            f"Non-Detecting bars keep click ETA even in GPU mode (got {call.kwargs})"
        )


def test_eta_progressbar_suppress_click_eta_flag():
    """_eta_progressbar(suppress_click_eta=True) toggles click's show_eta off (#438)."""
    from allaganeye.commands.split_matches import _eta_progressbar

    suppressed = _eta_progressbar(100, "Detecting", suppress_click_eta=True)
    default = _eta_progressbar(100, "Detecting")

    assert suppressed.show_eta is False
    assert default.show_eta is True


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_split_video_receives_progress_callback(
    mock_probe, mock_detect, mock_split, tmp_path
):
    """split_video is invoked with a progress_callback kwarg in normal mode (#331)."""
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config)

    mock_split.assert_called_once()
    # progress_callback is passed as kwarg so the Splitting bar advances
    assert "progress_callback" in mock_split.call_args.kwargs
    assert callable(mock_split.call_args.kwargs["progress_callback"])


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
    assert "Detecting" in output
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
    assert "Detecting" not in output
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

    def test_param_mismatch_vtuber(self, cache_video, cache_config, tmp_path):
        """標準 run の cache を vtuber run が再利用しない -> None (gate の cache bypass 防止)."""
        cache_path = tmp_path / "output" / ".detection_cache.json"
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, cache_config, CACHE_BOUNDARIES
        )
        vtuber_config = SplitConfig(output_dir=tmp_path / "output", vtuber=True)
        assert _load_cache(cache_path, cache_video, 1.0, vtuber_config) is None

    def test_param_mismatch_vtuber_reverse(self, cache_video, cache_config, tmp_path):
        """vtuber run の cache を標準 run が再利用しない -> None (released path 保護)."""
        cache_path = tmp_path / "output" / ".detection_cache.json"
        vtuber_config = SplitConfig(output_dir=tmp_path / "output", vtuber=True)
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, vtuber_config, CACHE_BOUNDARIES
        )
        assert _load_cache(cache_path, cache_video, 1.0, cache_config) is None

    def test_legacy_cache_without_vtuber_key(self, cache_video, cache_config, tmp_path):
        """vtuber key なし legacy cache: 標準 run は有効 (後方互換)、vtuber run は無効。

        --vtuber 導入前の cache はすべて標準 path の結果なので missing = False と
        同値に扱う (既存ユーザーの cache を無駄に invalidate しない)。
        """
        cache_path = tmp_path / "output" / ".detection_cache.json"
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, cache_config, CACHE_BOUNDARIES
        )
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        data["params"].pop("vtuber", None)
        cache_path.write_text(json.dumps(data), encoding="utf-8")
        assert (
            _load_cache(cache_path, cache_video, 1.0, cache_config) == CACHE_BOUNDARIES
        )
        vtuber_config = SplitConfig(output_dir=tmp_path / "output", vtuber=True)
        assert _load_cache(cache_path, cache_video, 1.0, vtuber_config) is None

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
    """Detecting progressbar length equals estimated_samples (#329, #331)."""
    mock_probe.return_value = {**PROBE_RESULT, "duration": 1800.0}
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    with patch(f"{MODULE}._ETAProgressBar") as mock_bar:
        mock_bar.return_value.__enter__ = lambda s: s
        mock_bar.return_value.__exit__ = lambda s, *a: None
        mock_bar.return_value.update = lambda n: None
        run_split(Path("input.mp4"), config)

    # First call is Detecting bar: interval=1.0 for 1800s -> 1800
    # Additional calls may include Splitting bar
    assert mock_bar.call_count >= 1
    detecting_call = mock_bar.call_args_list[0]
    assert detecting_call[1]["length"] == 1800


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_progressbar_tiny_video(mock_probe, mock_detect, mock_split, tmp_path):
    """Progressbar length is at least 1 for very short videos."""
    mock_probe.return_value = {**PROBE_RESULT, "duration": 0.5}
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    with patch(f"{MODULE}._ETAProgressBar") as mock_bar:
        mock_bar.return_value.__enter__ = lambda s: s
        mock_bar.return_value.__exit__ = lambda s, *a: None
        mock_bar.return_value.update = lambda n: None
        run_split(Path("input.mp4"), config)

    # int(0.5 / 1.0) = 0, max(1, 0) = 1
    assert mock_bar.call_count >= 1
    detecting_call = mock_bar.call_args_list[0]
    assert detecting_call[1]["length"] == 1


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_progressbar_auto_interval(mock_probe, mock_detect, mock_split, tmp_path):
    """Progressbar length uses auto-adjusted interval for long videos."""
    mock_probe.return_value = {**PROBE_RESULT, "duration": 7300.0}  # > 2h
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    with patch(f"{MODULE}._ETAProgressBar") as mock_bar:
        mock_bar.return_value.__enter__ = lambda s: s
        mock_bar.return_value.__exit__ = lambda s, *a: None
        mock_bar.return_value.update = lambda n: None
        run_split(Path("input.mp4"), config)

    # auto interval = 3.0 for > 2h, estimated_samples = int(7300/3.0) = 2433
    assert mock_bar.call_count >= 1
    detecting_call = mock_bar.call_args_list[0]
    assert detecting_call[1]["length"] == 2433


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


# --- Refine progress bar (#328) ---


class TestRefineProgressBar:
    """Refining progress bar behaviour (#328)."""

    def test_refine_callback_called_by_detector(self):
        """refine_progress_callback receives calls from detector."""
        from allaganeye.video.detector import detect_match_boundaries

        calls: list[tuple[int, int]] = []

        def on_refine(completed: int, total: int) -> None:
            calls.append((completed, total))

        def refine_side_effect(
            video_path,
            blackout_regions,
            blackout_threshold,
            duration_hint,
            workers,
            *,
            progress_callback=None,
            region=None,
        ):
            # Mimic Pass 2: publish total then advance per probe (#366)
            total_probes = 4
            if progress_callback is not None:
                progress_callback(0, total_probes)
                for i in range(1, total_probes + 1):
                    progress_callback(i, total_probes)
            return [(0.0, 5.0)]

        # Use a minimal mock: scan_cpu returns a blackout region so Pass 2 fires
        with (
            patch(
                "allaganeye.video.detector._scan_cpu",
                return_value={0.0: 1.0, 5.0: 1.0, 10.0: 100.0},
            ),
            patch(
                "allaganeye.video.detector._refine_blackout_regions",
                side_effect=refine_side_effect,
            ),
            patch(
                "allaganeye.video.scorebar.filter_blackouts_with_scorebar",
                return_value=([(0.0, 5.0)], ["match_boundary"]),
            ),
        ):
            detect_match_boundaries(
                Path("test.mp4"),
                duration_hint=100.0,
                min_match_duration=10.0,
                src_resolution=(1920, 1080),
                refine_progress_callback=on_refine,
            )

        assert len(calls) >= 1
        # Final call should have completed == total
        last_completed, last_total = calls[-1]
        assert last_completed == last_total

    def test_refine_total_matches_actual_calls(self):
        """Total reported to callback matches actual number of calls."""
        from allaganeye.video.detector import detect_match_boundaries

        calls: list[tuple[int, int]] = []

        def on_refine(completed: int, total: int) -> None:
            calls.append((completed, total))

        def refine_side_effect(
            video_path,
            blackout_regions,
            blackout_threshold,
            duration_hint,
            workers,
            *,
            progress_callback=None,
            region=None,
        ):
            # Mimic Pass 2: publish total then advance per probe (#366)
            total_probes = 6
            if progress_callback is not None:
                progress_callback(0, total_probes)
                for i in range(1, total_probes + 1):
                    progress_callback(i, total_probes)
            return [(0.0, 5.0), (15.0, 20.0), (25.0, 30.0)]

        # 2 blackout regions from Pass 1, 3 refined regions for scorebar
        with (
            patch(
                "allaganeye.video.detector._scan_cpu",
                return_value={0.0: 1.0, 5.0: 1.0, 20.0: 1.0, 25.0: 1.0, 50.0: 100.0},
            ),
            patch(
                "allaganeye.video.detector._refine_blackout_regions",
                side_effect=refine_side_effect,
            ),
            patch(
                "allaganeye.video.scorebar.filter_blackouts_with_scorebar",
                return_value=(
                    [(0.0, 5.0), (15.0, 20.0), (25.0, 30.0)],
                    ["match_boundary", "match_boundary", "match_boundary"],
                ),
            ) as mock_scorebar,
        ):
            # Simulate scorebar calling progress 3 times
            def scorebar_side_effect(
                vp,
                regions,
                dur,
                h,
                w,
                *,
                band_region=None,
                localize=False,
                audio_hits=None,
                stats=None,
                progress_callback=None,
            ):
                for i in range(len(regions)):
                    if progress_callback:
                        progress_callback(i + 1, len(regions))
                return (regions, ["match_boundary"] * len(regions))

            mock_scorebar.side_effect = scorebar_side_effect

            detect_match_boundaries(
                Path("test.mp4"),
                duration_hint=100.0,
                min_match_duration=10.0,
                src_resolution=(1920, 1080),
                refine_progress_callback=on_refine,
            )

        # completed should reach total exactly
        assert calls[-1][0] == calls[-1][1]

    @patch(f"{MODULE}.split_video")
    @patch(f"{MODULE}.detect_match_boundaries")
    @patch(f"{MODULE}.probe_video")
    def test_all_four_bars_displayed(
        self, mock_probe, mock_detect, mock_split, tmp_path, capsys
    ):
        """Detecting, Refining, Scorebar and Splitting bars all appear (#368, #393).

        Rewritten for the 3-phase detection progress model (was
        ``test_three_bars_displayed`` which asserted only 2 detection bars).
        """
        mock_probe.return_value = PROBE_RESULT
        mock_detect.return_value = BOUNDARIES
        mock_split.return_value = _output_files(tmp_path)

        # Simulate both detection-phase callbacks.
        def detect_side_effect(video_path, **kwargs):
            refine_cb = kwargs.get("refine_progress_callback")
            if refine_cb:
                refine_cb(1, 4)
                refine_cb(4, 4)
            sb_cb = kwargs.get("scorebar_progress_callback")
            if sb_cb:
                sb_cb(1, 2)
                sb_cb(2, 2)
            return BOUNDARIES

        mock_detect.side_effect = detect_side_effect
        config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

        run_split(Path("input.mp4"), config)

        output = capsys.readouterr().out
        assert "Detecting" in output
        assert "Refining" in output
        assert "Scorebar" in output
        assert "Splitting" in output


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_detecting_bar_is_not_overwritten_by_refining(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """Detecting row survives on the TTY once Refining opens (#368).

    Regression guard: previously Refining was opened inside Detecting's
    ``with`` block, so click's ``\\r`` rewrite erased Detecting.  With the
    manual-lifecycle redesign, Detecting is ``__exit__``-ed (emitting a
    newline) before Refining opens, so both labels persist in the output.
    """
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)

    def detect_side_effect(video_path, **kwargs):
        if kwargs.get("refine_progress_callback"):
            kwargs["refine_progress_callback"](1, 2)
            kwargs["refine_progress_callback"](2, 2)
        return BOUNDARIES

    mock_detect.side_effect = detect_side_effect
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config)

    output = capsys.readouterr().out
    # Detecting must appear strictly before Refining in the byte stream.
    det_pos = output.find("Detecting")
    ref_pos = output.find("Refining")
    assert det_pos >= 0, f"Detecting missing: {output!r}"
    assert ref_pos >= 0, f"Refining missing: {output!r}"
    assert det_pos < ref_pos, (
        "Detecting must appear before Refining in the stream "
        "(regression guard for #368)"
    )
    # And a newline must sit between them so the cursor moved off the
    # Detecting row before Refining began writing.
    between = output[det_pos:ref_pos]
    assert "\n" in between, (
        f"Detecting row not terminated with newline before Refining opens: {between!r}"
    )


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_refining_and_scorebar_bars_do_not_overlap(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """Scorebar opens on its own line after Refining closes (#393).

    Regression guard for the unit-mixing bug where Refining hit 100% on
    probe count and then reset to 99% when scorebar extended ``total``.
    With separate callbacks / separate bars, each phase's bar ends cleanly
    at 100% before the next opens.
    """
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)

    def detect_side_effect(video_path, **kwargs):
        if kwargs.get("refine_progress_callback"):
            kwargs["refine_progress_callback"](1, 2)
            kwargs["refine_progress_callback"](2, 2)
        if kwargs.get("scorebar_progress_callback"):
            kwargs["scorebar_progress_callback"](1, 2)
            kwargs["scorebar_progress_callback"](2, 2)
        return BOUNDARIES

    mock_detect.side_effect = detect_side_effect
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config)

    output = capsys.readouterr().out
    ref_pos = output.find("Refining")
    sb_pos = output.find("Scorebar")
    assert ref_pos < sb_pos, "Refining must appear before Scorebar in output stream"
    between = output[ref_pos:sb_pos]
    assert "\n" in between, (
        f"Refining row not terminated with newline before Scorebar opens: {between!r}"
    )


# --- multi-line eager phase display (#434) ---


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_eager_phases_off_by_default_in_non_tty(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """Non-TTY stdout (capsys default) skips eager placeholders (#434).

    Backwards-compat / log hygiene: redirected output and CI logs must
    not leak ANSI escape sequences or ``[waiting...]`` placeholder text.
    """
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config)

    output = capsys.readouterr().out
    assert "[waiting for Pass 1 to finish]" not in output
    assert "[waiting for Pass 2 to finish]" not in output
    # No ANSI cursor-up escape (\x1b[3A) when eager mode is off.
    assert "\x1b[3A" not in output


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_eager_phases_prints_waiting_placeholders_in_tty_mode(
    mock_probe, mock_detect, mock_split, tmp_path, capsys, monkeypatch
):
    """TTY stdout pre-prints Refining / Scorebar [waiting] placeholders (#434).

    User intent (issue body): "Detecting / Refining / Scorebar"
    visible from the start so the appearance of Refining mid-pipeline
    no longer feels like a phase materialising out of thin air.
    """
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    monkeypatch.setattr(
        f"{MODULE}._stdout_supports_eager_phases",
        lambda: True,
    )

    run_split(Path("input.mp4"), config)
    output = capsys.readouterr().out

    assert "Refining" in output
    assert "[waiting for Pass 1 to finish]" in output
    assert "Scorebar" in output
    assert "[waiting for Pass 2 to finish]" in output
    # Cursor-up ANSI moves the next bar render onto the Detecting line.
    assert "\x1b[3A" in output


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_eager_phases_marks_refining_skipped_when_pass2_empty(
    mock_probe, mock_detect, mock_split, tmp_path, capsys, monkeypatch
):
    """Pass 2 with no regions -> Refining placeholder updated to ``[skipped: no regions]`` (#434)."""
    mock_probe.return_value = PROBE_RESULT
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    def detect_side_effect(video_path, **kwargs):
        # Pass 2 yields zero callbacks (no regions to refine), but
        # scorebar still classifies whatever survived from Pass 1.
        sb_cb = kwargs.get("scorebar_progress_callback")
        if sb_cb:
            sb_cb(1, 2)
            sb_cb(2, 2)
        return BOUNDARIES

    mock_detect.side_effect = detect_side_effect
    monkeypatch.setattr(
        f"{MODULE}._stdout_supports_eager_phases",
        lambda: True,
    )

    run_split(Path("input.mp4"), config)
    output = capsys.readouterr().out

    assert "Refining   [skipped: no regions]" in output


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_eager_phases_clears_placeholders_on_pass1_exception(
    mock_probe, mock_detect, mock_split, tmp_path, capsys, monkeypatch
):
    """Pass 1 で例外発生時に Refining/Scorebar placeholder を ANSI clear する (#434 error path).

    Without cleanup, an exception during Pass 1 leaves stale
    ``[waiting...]`` lines hanging above the traceback because the
    Refining / Scorebar bars never opened to overwrite their
    placeholders.  Reviewer (#594) flagged this as an error-path UX
    regression of the multi-line layout introduced for #434.
    """
    mock_probe.return_value = PROBE_RESULT
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    # Simulate a failure during Pass 1 before any refine / scorebar
    # callback fires; the exception propagates out of run_split.
    mock_detect.side_effect = VideoProcessingError("simulated Pass 1 failure")
    monkeypatch.setattr(
        f"{MODULE}._stdout_supports_eager_phases",
        lambda: True,
    )

    with pytest.raises(VideoProcessingError):
        run_split(Path("input.mp4"), config)
    output = capsys.readouterr().out

    # Both placeholders printed initially (sanity).
    assert "[waiting for Pass 1 to finish]" in output
    assert "[waiting for Pass 2 to finish]" in output
    # Two cleanup escapes appended after the close calls so the
    # waiting placeholders don't dangle above the traceback.
    assert output.count("\x1b[2K\n") >= 2


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_eager_phases_clears_only_scorebar_placeholder_on_pass2_exception(
    mock_probe, mock_detect, mock_split, tmp_path, capsys, monkeypatch
):
    """Pass 2 中で例外発生時は Scorebar placeholder のみ cleanup する (#434 error path).

    By the time Pass 2 raises, the Refining bar has already replaced
    its waiting placeholder, so only the Scorebar placeholder needs
    erasing.  Refining is closed by ``_close_refine_if_open`` which
    advances the cursor onto the Scorebar waiting line.
    """
    mock_probe.return_value = PROBE_RESULT
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    def detect_side_effect(video_path, **kwargs):
        ref_cb = kwargs.get("refine_progress_callback")
        if ref_cb:
            ref_cb(1, 4)
        # Raise after Refining bar opened but before Scorebar fires.
        raise VideoProcessingError("simulated Pass 2 failure")

    mock_detect.side_effect = detect_side_effect
    monkeypatch.setattr(
        f"{MODULE}._stdout_supports_eager_phases",
        lambda: True,
    )

    with pytest.raises(VideoProcessingError):
        run_split(Path("input.mp4"), config)
    output = capsys.readouterr().out

    # Refining waiting placeholder was already replaced by the
    # Refining bar before the exception fired -> no cleanup needed
    # for it.  Scorebar waiting placeholder still on screen.
    assert "[waiting for Pass 2 to finish]" in output
    # Exactly one trailing cleanup escape (Scorebar).  ``output.count``
    # is more flexible than equality because click may emit additional
    # cursor controls during bar teardown; the regression we guard
    # against is "zero cleanups", not "more than one".
    assert output.count("\x1b[2K\n") >= 1


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_progress_bars_cleanup_on_exception(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """All three detection bars close even when detect_match_boundaries raises.

    Guards the ``try/finally`` wrapper in ``_run_detection`` (#368, #393).
    If a bar leaked, subsequent output would be mangled by an open bar's
    ``\\r`` rewrites; here we assert the exception propagates cleanly and
    no mid-phase ``%`` artifact lingers past the final line.
    """
    from allaganeye.exceptions import VideoProcessingError

    mock_probe.return_value = PROBE_RESULT
    mock_split.return_value = _output_files(tmp_path)

    def detect_side_effect(video_path, **kwargs):
        # Open Refining, then blow up -- the finally block should close it.
        if kwargs.get("refine_progress_callback"):
            kwargs["refine_progress_callback"](1, 5)
        raise VideoProcessingError("simulated ffmpeg failure")

    mock_detect.side_effect = detect_side_effect
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    with pytest.raises(VideoProcessingError):
        run_split(Path("input.mp4"), config)

    # The exception propagated, and the bars were closed in the finally
    # block.  A leaked bar would leave the cursor mid-line without a
    # trailing newline after the last '%' token.
    output = capsys.readouterr().out
    if "%" in output:
        last_percent = output.rfind("%")
        tail = output[last_percent:]
        assert "\n" in tail, (
            f"progress bar not terminated with newline on exception path: {tail!r}"
        )


# --- Audio scan integration (#288) ---


class TestDiskSpaceCheck:
    """Disk space check before splitting (#338)."""

    def test_estimate_output_size(self, tmp_path):
        """Output size estimation uses file size, duration ratio, and margin."""
        from allaganeye.commands.split_matches import _estimate_output_size

        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00" * 1_000_000)  # 1 MB

        boundaries: list[MatchBoundary] = [
            {"start": 0.0, "end": 500.0, "type": "unknown"},
        ]
        # 500s out of 1000s = 50%, plus 10% margin = 55%
        result = _estimate_output_size(video, boundaries, 1000.0)
        assert result == int(1_000_000 * 0.5 * 1.1)

    def test_check_disk_space_raises_on_insufficient(self, tmp_path):
        """Raises AllaganEyeError when free space is insufficient."""
        from allaganeye.commands.split_matches import _check_disk_space

        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00" * 1_000_000)
        boundaries: list[MatchBoundary] = [
            {"start": 0.0, "end": 900.0, "type": "unknown"},
        ]
        config = SplitConfig(output_dir=tmp_path / "output")

        # Mock disk_usage to report very low free space
        fake_usage = type(
            "Usage", (), {"total": 1_000_000, "used": 999_000, "free": 1_000}
        )
        with patch(
            "allaganeye.commands.split_matches.shutil.disk_usage",
            return_value=fake_usage,
        ):
            with pytest.raises(AllaganEyeError, match="Not enough disk space"):
                _check_disk_space(video, boundaries, 1000.0, config)

    def test_check_disk_space_passes_when_sufficient(self, tmp_path):
        """No error when free space is sufficient."""
        from allaganeye.commands.split_matches import _check_disk_space

        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00" * 1_000_000)
        boundaries: list[MatchBoundary] = [
            {"start": 0.0, "end": 500.0, "type": "unknown"},
        ]
        config = SplitConfig(output_dir=tmp_path / "output")

        fake_usage = type(
            "Usage", (), {"total": 100_000_000, "used": 50_000_000, "free": 50_000_000}
        )
        with patch(
            "allaganeye.commands.split_matches.shutil.disk_usage",
            return_value=fake_usage,
        ):
            # Should not raise
            _check_disk_space(video, boundaries, 1000.0, config)

    def test_check_disk_space_warns_on_tight(self, tmp_path, capsys):
        """Warns (but doesn't error) when space is tight."""
        from allaganeye.commands.split_matches import _check_disk_space

        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00" * 1_000_000)
        boundaries: list[MatchBoundary] = [
            {"start": 0.0, "end": 900.0, "type": "unknown"},
        ]
        config = SplitConfig(output_dir=tmp_path / "output")

        # estimated = 1M * 0.9 * 1.1 = 990_000; free = 1_100_000
        # estimated > free * 0.8 (880_000) -> warn
        fake_usage = type(
            "Usage", (), {"total": 2_000_000, "used": 900_000, "free": 1_100_000}
        )
        with patch(
            "allaganeye.commands.split_matches.shutil.disk_usage",
            return_value=fake_usage,
        ):
            _check_disk_space(video, boundaries, 1000.0, config, show=True)

        stderr = capsys.readouterr().err
        assert "Warning" in stderr

    @patch(f"{MODULE}.split_video")
    @patch(f"{MODULE}.detect_match_boundaries")
    @patch(f"{MODULE}.probe_video")
    def test_dry_run_skips_check(self, mock_probe, mock_detect, mock_split, tmp_path):
        """--dry-run does not check disk space."""
        mock_probe.return_value = PROBE_RESULT
        mock_detect.return_value = BOUNDARIES
        config = SplitConfig(output_dir=tmp_path, dry_run=True, min_match_duration=60.0)

        with patch(f"{MODULE}._check_disk_space") as mock_check:
            run_split(Path("input.mp4"), config)
            mock_check.assert_not_called()

    def test_error_message_includes_recovery_command(self, tmp_path):
        """Error message includes re-run command."""
        from allaganeye.commands.split_matches import _check_disk_space

        video = tmp_path / "my video.mp4"
        video.write_bytes(b"\x00" * 1_000_000)
        boundaries: list[MatchBoundary] = [
            {"start": 0.0, "end": 900.0, "type": "unknown"},
        ]
        config = SplitConfig(output_dir=tmp_path / "output")

        fake_usage = type(
            "Usage", (), {"total": 1_000_000, "used": 999_000, "free": 1_000}
        )
        with patch(
            "allaganeye.commands.split_matches.shutil.disk_usage",
            return_value=fake_usage,
        ):
            with pytest.raises(AllaganEyeError, match="allaganeye split") as exc_info:
                _check_disk_space(video, boundaries, 1000.0, config)
            # Path with space should be quoted
            assert '"' in str(exc_info.value)

    @patch(f"{MODULE}.split_video")
    @patch(f"{MODULE}.detect_match_boundaries")
    @patch(f"{MODULE}.probe_video")
    def test_match_list_displayed_before_disk_error(
        self, mock_probe, mock_detect, mock_split, tmp_path, capsys
    ):
        """Match list is displayed before disk space error is raised (#338).

        Core UX contract from issue #338: even when the split is aborted
        for insufficient space, the user must see the detection results
        first so they can confirm what was detected / was cached.
        """
        mock_probe.return_value = PROBE_RESULT
        mock_detect.return_value = BOUNDARIES
        config = SplitConfig(output_dir=tmp_path / "output", min_match_duration=60.0)

        fake_usage = type("Usage", (), {"total": 10_000, "used": 9_000, "free": 1_000})
        with (
            patch(
                "allaganeye.commands.split_matches.shutil.disk_usage",
                return_value=fake_usage,
            ),
            patch(
                f"{MODULE}._estimate_output_size",
                return_value=100_000_000_000,  # 100GB vs 1KB free -> raises
            ),
        ):
            with pytest.raises(AllaganEyeError, match="Not enough disk space"):
                run_split(Path("input.mp4"), config)

        output = capsys.readouterr().out
        # Detected header + both Match lines must appear before the raise
        assert "Detected 2 match(es)" in output
        assert "Match 1:" in output
        assert "Match 2:" in output
        # Split must not be attempted
        mock_split.assert_not_called()

    def test_quiet_suppresses_tight_space_warning(self, tmp_path, capsys):
        """show=False suppresses the tight-space warning (#338 + --quiet)."""
        from allaganeye.commands.split_matches import _check_disk_space

        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00" * 1_000_000)
        boundaries: list[MatchBoundary] = [
            {"start": 0.0, "end": 900.0, "type": "unknown"},
        ]
        config = SplitConfig(output_dir=tmp_path / "output")

        # Tight but sufficient: estimated 990_000, free 1_100_000 (>80% -> warn)
        fake_usage = type(
            "Usage", (), {"total": 2_000_000, "used": 900_000, "free": 1_100_000}
        )
        with patch(
            "allaganeye.commands.split_matches.shutil.disk_usage",
            return_value=fake_usage,
        ):
            _check_disk_space(video, boundaries, 1000.0, config, show=False)

        stderr = capsys.readouterr().err
        assert "Warning" not in stderr

    @patch(f"{MODULE}.split_video")
    @patch(f"{MODULE}.detect_match_boundaries")
    @patch(f"{MODULE}.probe_video")
    @patch(f"{MODULE}._load_cache")
    def test_cached_path_enforces_disk_check(
        self, mock_load, mock_probe, mock_detect, mock_split, tmp_path
    ):
        """Disk space check runs even when boundaries come from cache (#338).

        The cached re-run is the primary recovery path from an earlier
        disk-full failure; the check must re-validate that enough space
        is available before splitting.
        """
        mock_probe.return_value = PROBE_RESULT
        mock_load.return_value = BOUNDARIES  # simulate cache hit
        mock_split.return_value = _output_files(tmp_path)
        config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

        with patch(f"{MODULE}._check_disk_space") as mock_check:
            run_split(Path("input.mp4"), config)

        mock_check.assert_called_once()
        # detect_match_boundaries must not be invoked (cache hit)
        mock_detect.assert_not_called()


class TestResolveGpuMode:
    """Codec-based GPU/CPU auto-selection (#334) + vendor selection (#546)."""

    @pytest.fixture(autouse=True)
    def _mock_probe(self, monkeypatch):
        """Default: NVIDIA only so vendor auto-select is deterministic."""
        monkeypatch.setattr(
            "allaganeye.system_info.probe_gpu_vendors",
            lambda: ["nvidia"],
        )

    def test_explicit_gpu_true(self):
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        use_gpu, vendor = _resolve_gpu_mode(
            True, None, "av1", show=False, verbose=False
        )
        assert use_gpu is True
        assert vendor == "nvidia"

    def test_explicit_gpu_false(self):
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        use_gpu, _vendor = _resolve_gpu_mode(
            False, None, "h264", show=False, verbose=False
        )
        assert use_gpu is False

    def test_auto_h264_selects_gpu(self):
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        use_gpu, vendor = _resolve_gpu_mode(
            None, None, "h264", show=False, verbose=False
        )
        assert use_gpu is True
        assert vendor == "nvidia"

    def test_auto_hevc_selects_gpu(self):
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        use_gpu, _ = _resolve_gpu_mode(None, None, "hevc", show=False, verbose=False)
        assert use_gpu is True

    def test_auto_av1_selects_gpu(self):
        """AV1 auto-selects GPU (#414: NVDEC AV1 = RTX 30+ / QSV AV1 = Gen12+ / VCN 4.0+)."""
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        use_gpu, _ = _resolve_gpu_mode(None, None, "av1", show=False, verbose=False)
        assert use_gpu is True

    def test_auto_vp9_selects_gpu(self):
        """VP9 auto-selects GPU (#414: widely supported NVDEC Maxwell+)."""
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        use_gpu, _ = _resolve_gpu_mode(None, None, "vp9", show=False, verbose=False)
        assert use_gpu is True

    def test_auto_unknown_codec_selects_cpu(self):
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        use_gpu, vendor = _resolve_gpu_mode(None, None, None, show=False, verbose=False)
        assert use_gpu is False
        # vendor が probe で見つかっても CPU 選択時は None にして vendor 情報を
        # downstream (scan_gpu) に渡さない (GPU path を使わないため不要)
        assert vendor is None

    def test_auto_verbose_shows_message(self, capsys):
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        _resolve_gpu_mode(None, None, "h264", show=True, verbose=True)
        out = capsys.readouterr().out
        assert "Auto-selected GPU mode" in out
        assert "h264" in out

    def test_auto_cpu_verbose_shows_cpu_message(self, capsys):
        """CPU auto-selection also emits a verbose notice (#334).

        Guards the else-branch of the mode resolution -- users on
        legacy codecs (mpeg2video etc.) need to see that CPU mode was
        chosen intentionally (not just because GPU failed).
        """
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        _resolve_gpu_mode(None, None, "mpeg2video", show=True, verbose=True)
        out = capsys.readouterr().out
        assert "Auto-selected CPU mode" in out
        assert "mpeg2video" in out

    def test_auto_non_verbose_suppresses_message(self, capsys):
        """Non-verbose auto selection is silent (#334)."""
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        _resolve_gpu_mode(None, None, "h264", show=True, verbose=False)
        out = capsys.readouterr().out
        assert "Auto-selected" not in out

    def test_auto_quiet_suppresses_message(self, capsys):
        """--quiet (show=False) silences auto-selection message even with verbose (#334)."""
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        _resolve_gpu_mode(None, None, "h264", show=False, verbose=True)
        out = capsys.readouterr().out
        assert "Auto-selected" not in out

    def test_auto_codec_matching_is_case_insensitive(self):
        """Codec name matching is case-insensitive (#334)."""
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        assert (
            _resolve_gpu_mode(None, None, "H264", show=False, verbose=False)[0] is True
        )
        assert (
            _resolve_gpu_mode(None, None, "HEVC", show=False, verbose=False)[0] is True
        )
        assert (
            _resolve_gpu_mode(None, None, "Hevc", show=False, verbose=False)[0] is True
        )

    # ---- vendor selection (#546) ----

    def test_vendor_auto_prefers_nvidia_in_dual_gpu(self, monkeypatch):
        """Dual GPU 環境で auto は NVIDIA を優先選択 (_VENDOR_PREFERENCE 順)."""
        monkeypatch.setattr(
            "allaganeye.system_info.probe_gpu_vendors",
            lambda: ["nvidia", "amd"],
        )
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        _, vendor = _resolve_gpu_mode(None, None, "av1", show=False, verbose=False)
        assert vendor == "nvidia"

    def test_vendor_auto_selects_amd_when_only_amd(self, monkeypatch):
        """AMD iGPU のみ環境では vendor=amd を返し d3d11va 経路で動作する (#553).

        #546 時点では AMD は AMF decoder の filter pipeline 不整合で skip
        されていたが、#553 で d3d11va + hwdownload 経路を実装したことで
        auto 選択でも AMD が選ばれる。codec=av1 は ``_GPU_PREFERRED_CODECS``
        に含まれるため use_gpu=True。
        """
        monkeypatch.setattr(
            "allaganeye.system_info.probe_gpu_vendors",
            lambda: ["amd"],
        )
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        use_gpu, vendor = _resolve_gpu_mode(
            None, None, "av1", show=False, verbose=False
        )
        assert use_gpu is True
        assert vendor == "amd"

    def test_vendor_explicit_amd_resolves(self, monkeypatch):
        """AMD は #553 で d3d11va 経路として実装済み、explicit 要求も通る."""
        monkeypatch.setattr(
            "allaganeye.system_info.probe_gpu_vendors",
            lambda: ["nvidia", "amd"],
        )
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        use_gpu, vendor = _resolve_gpu_mode(
            None, "amd", "av1", show=False, verbose=False
        )
        assert use_gpu is True
        assert vendor == "amd"

    def test_vendor_explicit_unavailable_raises_config_error(self, monkeypatch):
        """--gpu-vendor で probe に無い vendor を要求すると exit 5 (#546).

        NVIDIA のみ実装済みなので nvidia の unavailability をテスト。
        """
        monkeypatch.setattr(
            "allaganeye.system_info.probe_gpu_vendors",
            lambda: ["amd"],
        )
        from allaganeye.commands.split_matches import _resolve_gpu_mode
        from allaganeye.exceptions import ConfigValidationError

        with pytest.raises(ConfigValidationError, match="--gpu-vendor nvidia"):
            _resolve_gpu_mode(None, "nvidia", "av1", show=False, verbose=False)

    def test_vendor_explicit_intel_succeeds_when_available(self, monkeypatch):
        """Intel は #550 で実装済み。explicit 要求 + available なら通る."""
        monkeypatch.setattr(
            "allaganeye.system_info.probe_gpu_vendors",
            lambda: ["intel", "nvidia"],
        )
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        use_gpu, vendor = _resolve_gpu_mode(
            None, "intel", "av1", show=False, verbose=False
        )
        assert use_gpu is True
        assert vendor == "intel"

    def test_vendor_explicit_intel_unavailable_raises(self, monkeypatch):
        """Intel 実装済みでも probe で見つからなければ exit 5 (#550)."""
        monkeypatch.setattr(
            "allaganeye.system_info.probe_gpu_vendors",
            lambda: ["nvidia"],
        )
        from allaganeye.commands.split_matches import _resolve_gpu_mode
        from allaganeye.exceptions import ConfigValidationError

        with pytest.raises(ConfigValidationError, match="--gpu-vendor intel"):
            _resolve_gpu_mode(None, "intel", "av1", show=False, verbose=False)

    def test_vendor_auto_picks_preference_order(self, monkeypatch):
        """auto 選択は `_VENDOR_PREFERENCE` (nvidia > amd > intel) 順で
        実装済み vendor を選ぶ (#546 / #553 / #550).

        nvidia / amd / intel の 3 つが available で、いずれも実装済み
        (nvidia=cuvid #546, amd=d3d11va #553, intel=qsv #550) のとき、
        preference 順に NVIDIA dGPU が最優先される。
        """
        monkeypatch.setattr(
            "allaganeye.system_info.probe_gpu_vendors",
            lambda: ["intel", "amd", "nvidia"],
        )
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        _, vendor = _resolve_gpu_mode(None, None, "av1", show=False, verbose=False)
        assert vendor == "nvidia"

    def test_vendor_auto_picks_amd_when_no_nvidia(self, monkeypatch):
        """NVIDIA 不在 + AMD + Intel 環境で auto は AMD を選ぶ (#553).

        preference = nvidia > amd > intel。NVIDIA が無く AMD と Intel が
        ある場合、preference 順で AMD が選ばれる (Intel iGPU を持つ AMD
        dGPU/iGPU 環境を想定)。
        """
        monkeypatch.setattr(
            "allaganeye.system_info.probe_gpu_vendors",
            lambda: ["amd", "intel"],
        )
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        use_gpu, vendor = _resolve_gpu_mode(
            None, None, "av1", show=False, verbose=False
        )
        assert use_gpu is True
        assert vendor == "amd"

    def test_vendor_auto_picks_intel_when_only_intel(self, monkeypatch):
        """Intel iGPU 単独環境で auto は intel を選ぶ (#550)."""
        monkeypatch.setattr(
            "allaganeye.system_info.probe_gpu_vendors",
            lambda: ["intel"],
        )
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        use_gpu, vendor = _resolve_gpu_mode(
            None, None, "av1", show=False, verbose=False
        )
        assert use_gpu is True
        assert vendor == "intel"

    def test_vendor_none_when_no_gpu_available(self, monkeypatch):
        """GPU probe が空でも codec match なら use_gpu=True (legacy path).

        vendor=None (probe 失敗 / Linux CI 等) でも scan_gpu の legacy
        path (-hwaccel auto) で動作する。ffmpeg 側で GPU decode 失敗
        した場合は CPU fallback (#334 既存挙動維持)。
        """
        monkeypatch.setattr(
            "allaganeye.system_info.probe_gpu_vendors",
            lambda: [],
        )
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        use_gpu, vendor = _resolve_gpu_mode(
            None, None, "av1", show=False, verbose=False
        )
        assert use_gpu is True
        assert vendor is None

    def test_vendor_auto_string_equivalent_to_none(self, monkeypatch):
        """--gpu-vendor auto は指定なし (None) と同等の挙動."""
        monkeypatch.setattr(
            "allaganeye.system_info.probe_gpu_vendors",
            lambda: ["nvidia", "amd"],
        )
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        _, none_vendor = _resolve_gpu_mode(None, None, "av1", show=False, verbose=False)
        _, auto_vendor = _resolve_gpu_mode(
            None, "auto", "av1", show=False, verbose=False
        )
        assert none_vendor == auto_vendor == "nvidia"


class TestResolveGpuModeWithProbe:
    """``_resolve_gpu_mode_with_probe`` returns the available vendor list (#591)."""

    def test_returns_available_vendors(self, monkeypatch):
        """probe で見つかった全 vendor が 3-tuple の 3 要素目に返る."""
        monkeypatch.setattr(
            "allaganeye.system_info.probe_gpu_vendors",
            lambda: ["nvidia", "amd"],
        )
        from allaganeye.commands.split_matches import _resolve_gpu_mode_with_probe

        use_gpu, vendor, available = _resolve_gpu_mode_with_probe(
            None, None, "av1", show=False, verbose=False
        )
        assert use_gpu is True
        assert vendor == "nvidia"
        assert available == ["nvidia", "amd"]

    def test_returns_empty_when_probe_fails(self, monkeypatch):
        """probe が空 list を返したら 3 要素目も空 list."""
        monkeypatch.setattr(
            "allaganeye.system_info.probe_gpu_vendors",
            lambda: [],
        )
        from allaganeye.commands.split_matches import _resolve_gpu_mode_with_probe

        use_gpu, vendor, available = _resolve_gpu_mode_with_probe(
            None, None, "av1", show=False, verbose=False
        )
        # codec match なので use_gpu=True、ただし vendor は None
        assert use_gpu is True
        assert vendor is None
        assert available == []

    def test_legacy_2tuple_wrapper_still_works(self, monkeypatch):
        """``_resolve_gpu_mode`` (2-tuple) はラッパとして機能する."""
        monkeypatch.setattr(
            "allaganeye.system_info.probe_gpu_vendors",
            lambda: ["intel"],
        )
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        result = _resolve_gpu_mode(None, None, "h264", show=False, verbose=False)
        assert len(result) == 2  # backward-compat 2-tuple
        use_gpu, vendor = result
        assert use_gpu is True
        assert vendor == "intel"


class TestBuildSystemInfo:
    """``_build_system_info`` constructs the metadata.json system_info dict (#591, extended #761)."""

    def test_basic_payload(self):
        from unittest.mock import patch

        from allaganeye.commands.split_matches import _build_system_info

        with patch(
            "allaganeye.system_info.get_gpu_info_lines",
            return_value=["NVIDIA GeForce RTX 5090 (32GB VRAM)"],
        ):
            info = _build_system_info(
                available_vendors=["nvidia", "amd"],
                vendor_used="nvidia",
            )
        assert info["gpu_vendors_available"] == ["nvidia", "amd"]
        assert info["gpu_vendor_used"] == "nvidia"
        assert info["vendor_preference"] == ["nvidia", "amd", "intel"]
        assert info.get("gpu") == ["NVIDIA GeForce RTX 5090 (32GB VRAM)"]

    def test_no_gpu_used_is_null(self):
        """CPU 強制 / cache hit / split-only path では vendor_used=None."""
        from unittest.mock import patch

        from allaganeye.commands.split_matches import _build_system_info

        with patch("allaganeye.system_info.get_gpu_info_lines", return_value=[]):
            info = _build_system_info(
                available_vendors=["nvidia"],
                vendor_used=None,
            )
        assert info["gpu_vendor_used"] is None
        assert info["gpu_vendors_available"] == ["nvidia"]
        assert info.get("gpu") == []

    def test_empty_available_vendors(self):
        """probe 失敗環境 (CPU only Linux CI など) でも payload を作れる."""
        from unittest.mock import patch

        from allaganeye.commands.split_matches import _build_system_info

        with patch("allaganeye.system_info.get_gpu_info_lines", return_value=[]):
            info = _build_system_info(
                available_vendors=[],
                vendor_used=None,
            )
        assert info["gpu_vendors_available"] == []
        assert info["gpu_vendor_used"] is None
        assert info["vendor_preference"] == ["nvidia", "amd", "intel"]
        assert info.get("gpu") == []

    def test_preference_matches_gpu_detector_module(self):
        """``vendor_preference`` は ``gpu_detector._VENDOR_PREFERENCE`` のスナップショット."""
        from unittest.mock import patch

        from allaganeye.commands.split_matches import _build_system_info
        from allaganeye.video.gpu_detector import _VENDOR_PREFERENCE

        with patch("allaganeye.system_info.get_gpu_info_lines", return_value=[]):
            info = _build_system_info(available_vendors=[], vendor_used=None)
        assert info["vendor_preference"] == list(_VENDOR_PREFERENCE)

    def test_gpu_models_included_in_payload(self):
        """``gpu`` field は ``get_gpu_info_lines()`` の結果を格納する (#761)."""
        from unittest.mock import patch

        from allaganeye.commands.split_matches import _build_system_info

        gpu_models = ["NVIDIA GeForce RTX 5090 (32GB VRAM)", "Intel Arc A770"]
        with patch(
            "allaganeye.system_info.get_gpu_info_lines", return_value=gpu_models
        ):
            info = _build_system_info(
                available_vendors=["nvidia"], vendor_used="nvidia"
            )
        assert info.get("gpu") == gpu_models


class TestBuildMetadataPayloadSystemInfo:
    """``_build_metadata_payload`` includes the system_info field (#591)."""

    def test_payload_includes_system_info(self, tmp_path):
        from allaganeye.commands.split_matches import _build_metadata_payload
        from allaganeye.config import SplitConfig
        from allaganeye.video.detector import MatchBoundary

        config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
        boundaries: list[MatchBoundary] = [
            {"start": 0.0, "end": 120.0, "type": "fl_match"},
        ]
        payload = _build_metadata_payload(
            video_path=tmp_path / "input.mp4",
            source_duration=120.0,
            source_fps=60.0,
            detected_at="2026-04-26T00:00:00Z",
            detection_started_at="2026-04-26T00:00:00Z",
            detection_completed_at="2026-04-26T00:00:05Z",
            effective_interval=1.0,
            config=config,
            boundaries=boundaries,
            output_files=[tmp_path / "match_001.mp4"],
            gaps=[],
            system_info={
                "gpu_vendors_available": ["nvidia"],
                "gpu_vendor_used": "nvidia",
                "vendor_preference": ["nvidia", "amd", "intel"],
            },
        )
        assert "system_info" in payload
        assert payload["system_info"]["gpu_vendors_available"] == ["nvidia"]
        assert payload["system_info"]["gpu_vendor_used"] == "nvidia"
        assert payload["system_info"]["vendor_preference"] == [
            "nvidia",
            "amd",
            "intel",
        ]


class TestBuildMetadataPayloadElapsedTimestamps:
    """``_build_metadata_payload`` records detection_started_at /
    detection_completed_at so GUI CompleteScreen can render the elapsed
    column (#586)."""

    def test_payload_includes_started_and_completed_timestamps(self, tmp_path):
        from allaganeye.commands.split_matches import _build_metadata_payload
        from allaganeye.config import SplitConfig
        from allaganeye.video.detector import MatchBoundary

        config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
        boundaries: list[MatchBoundary] = [
            {"start": 0.0, "end": 120.0, "type": "fl_match"},
        ]
        payload = _build_metadata_payload(
            video_path=tmp_path / "input.mp4",
            source_duration=120.0,
            source_fps=60.0,
            detected_at="2026-04-26T00:00:00Z",
            detection_started_at="2026-04-26T00:00:00Z",
            detection_completed_at="2026-04-26T00:00:42Z",
            effective_interval=1.0,
            config=config,
            boundaries=boundaries,
            output_files=[tmp_path / "match_001.mp4"],
            gaps=[],
            system_info={
                "gpu_vendors_available": [],
                "gpu_vendor_used": None,
                "vendor_preference": ["nvidia", "amd", "intel"],
            },
        )
        # Both new fields are present and serialised verbatim. Use .get() because
        # Metadata TypedDict marks them NotRequired (optional in JSON Schema for
        # pre-#586 metadata.json compat); pyright otherwise warns on direct
        # subscript access.
        assert payload.get("detection_started_at") == "2026-04-26T00:00:00Z"
        assert payload.get("detection_completed_at") == "2026-04-26T00:00:42Z"
        # Legacy detected_at stays for backward compat (#586 case 案 B).
        assert payload["detected_at"] == "2026-04-26T00:00:00Z"

    def test_started_at_equals_detected_at_for_new_writes(self, tmp_path):
        """検知開始時刻は detected_at と同値で書かれる (#586 案 B 後方互換)."""
        from allaganeye.commands.split_matches import _build_metadata_payload
        from allaganeye.config import SplitConfig
        from allaganeye.video.detector import MatchBoundary

        config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
        boundaries: list[MatchBoundary] = [
            {"start": 0.0, "end": 120.0, "type": "fl_match"},
        ]
        same_ts = "2026-04-28T01:23:45Z"
        payload = _build_metadata_payload(
            video_path=tmp_path / "input.mp4",
            source_duration=120.0,
            source_fps=60.0,
            detected_at=same_ts,
            detection_started_at=same_ts,
            detection_completed_at="2026-04-28T01:24:30Z",
            effective_interval=1.0,
            config=config,
            boundaries=boundaries,
            output_files=[tmp_path / "match_001.mp4"],
            gaps=[],
            system_info={
                "gpu_vendors_available": [],
                "gpu_vendor_used": None,
                "vendor_preference": ["nvidia", "amd", "intel"],
            },
        )
        assert payload["detected_at"] == payload.get("detection_started_at")


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
    def test_run_audio_scan_returns_none_when_frozen(self, tmp_path):
        """AUDIO_FROZEN=True skips scan without invoking scan_fanfare_hits (#327)."""
        from allaganeye.commands.split_matches import _run_audio_scan

        config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
        # AUDIO_FROZEN is True by default -- scan should be skipped
        result = _run_audio_scan(Path("input.mp4"), config, show=False, verbose=False)
        assert result is None

    @pytest.mark.real_audio_scan
    @patch("allaganeye.audio.scan.scan_fanfare_hits")
    def test_run_audio_scan_frozen_does_not_call_scan_fanfare_hits(
        self, mock_scan, tmp_path
    ):
        """Frozen path must short-circuit before invoking scan_fanfare_hits (#327).

        This guards the performance/side-effect contract: the whole point of
        freezing is that no ffmpeg audio extraction or correlation runs.
        Returning None alone would not catch a bug where the scan still
        executes but its result is discarded.
        """
        from allaganeye.commands.split_matches import _run_audio_scan

        # AUDIO_FROZEN True (default) AND no_audio False -- scan must still skip
        config = SplitConfig(
            output_dir=tmp_path, min_match_duration=60.0, no_audio=False
        )
        result = _run_audio_scan(Path("input.mp4"), config, show=False, verbose=False)
        assert result is None
        mock_scan.assert_not_called()

    @pytest.mark.real_audio_scan
    def test_run_audio_scan_frozen_suppresses_progress_message(self, tmp_path, capsys):
        """Frozen path must not print 'Scanning audio for Fanfare peaks' (#327).

        The freeze check sits before the typer.echo, so show=True should still
        produce silent output when frozen (no confusing message to the user).
        """
        from allaganeye.commands.split_matches import _run_audio_scan

        config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
        result = _run_audio_scan(Path("input.mp4"), config, show=True, verbose=True)
        captured = capsys.readouterr()
        assert result is None
        assert "Fanfare" not in captured.out
        assert "Scanning audio" not in captured.out

    def test_audio_frozen_flag_exported(self):
        """AUDIO_FROZEN is part of the public audio API (#327)."""
        import allaganeye.audio as audio_mod

        assert hasattr(audio_mod, "AUDIO_FROZEN")
        assert "AUDIO_FROZEN" in audio_mod.__all__
        # Default state: frozen until compound-signal integration ships
        assert audio_mod.AUDIO_FROZEN is True

    @pytest.mark.real_audio_scan
    @patch("allaganeye.audio.AUDIO_FROZEN", False)
    def test_run_audio_scan_returns_none_when_disabled(self, tmp_path):
        """config.no_audio=True skips audio scan without invoking scan_fanfare_hits."""
        from allaganeye.commands.split_matches import _run_audio_scan

        config = SplitConfig(
            output_dir=tmp_path, min_match_duration=60.0, no_audio=True
        )
        result = _run_audio_scan(Path("input.mp4"), config, show=False, verbose=False)
        assert result is None

    @pytest.mark.real_audio_scan
    @patch("allaganeye.audio.AUDIO_FROZEN", False)
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
    @patch("allaganeye.audio.AUDIO_FROZEN", False)
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


# --- Verbose output (issue #336 Phase 1) ---


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_verbose_emits_environment_header(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """Verbose mode prints allaganeye version + Python/OS header (issue #336)."""
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config, verbose=True)
    out = capsys.readouterr().out
    assert "allaganeye " in out
    assert "Python" in out


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_verbose_emits_codec_in_duration_line(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """Verbose probe line includes video codec (issue #336)."""
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config, verbose=True)
    out = capsys.readouterr().out
    assert "Codec: h264" in out


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_verbose_detecting_line_includes_params(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """Verbose 'Detecting' line shows detailed params (issue #336).

    Mode is shown in Pass 1 stats (post-detection) rather than in
    the Detecting line, so that GPU fallback is accurately reported.
    """
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(
        output_dir=tmp_path, min_match_duration=60.0, use_gpu=True, workers=8
    )

    # Force AUDIO_FROZEN=False so this test verifies the on/off branch of
    # _audio_status_str (the frozen branch is covered by a dedicated test
    # below).
    with patch("allaganeye.audio.AUDIO_FROZEN", False):
        run_split(Path("input.mp4"), config, verbose=True)
    out = capsys.readouterr().out
    assert "workers=8" in out
    assert "min_match=60.0s" in out
    assert "min_blackout=3.0s" in out
    assert "audio=on" in out


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_verbose_prints_pipeline_stats(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """Verbose mode emits Pass 1 / Pass 2 / Scorebar breakdown (issue #336)."""
    mock_probe.return_value = PROBE_RESULT

    def populate_stats(*args, **kwargs):
        stats = kwargs.get("stats")
        if stats is not None:
            stats["mode"] = "CPU"
            stats["pass1_samples"] = 1800
            stats["pass1_blackout_frames"] = 42
            stats["pass1_elapsed_s"] = 120.0
            stats["pass2_regions"] = 12
            stats["pass2_elapsed_s"] = 5.0
            stats["scorebar_match_boundary"] = 4
            stats["scorebar_in_match"] = 3
            stats["scorebar_non_fl"] = 2
            stats["scorebar_unknown"] = 0
            stats["audio_promotions"] = 1
        return BOUNDARIES

    mock_detect.side_effect = populate_stats
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config, verbose=True)
    out = capsys.readouterr().out
    assert "Pass 1 (CPU)" in out
    assert "1800 samples" in out
    assert "42 blackout frames" in out
    assert "Pass 2" in out
    assert "12 regions refined" in out
    assert "Scorebar" in out
    assert "4 match_boundary" in out
    assert "3 in_match" in out
    assert "2 non_fl" in out
    assert "Audio promotion: 1" in out
    assert "Total:" in out


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_verbose_scorebar_line_includes_elapsed(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """Scorebar line includes an elapsed-time token (#386).

    Pass 1 and Pass 2 already print elapsed; the scorebar line previously
    showed only counts, breaking symmetry and hiding scorebar-specific
    performance regressions from troubleshoot reports.
    """
    mock_probe.return_value = PROBE_RESULT

    def populate_stats(*args, **kwargs):
        stats = kwargs.get("stats")
        if stats is not None:
            stats["mode"] = "CPU"
            stats["pass1_samples"] = 100
            stats["pass1_blackout_frames"] = 5
            stats["pass1_elapsed_s"] = 10.0
            stats["pass2_regions"] = 3
            stats["pass2_elapsed_s"] = 2.0
            stats["scorebar_match_boundary"] = 2
            stats["scorebar_in_match"] = 1
            stats["scorebar_non_fl"] = 0
            stats["scorebar_unknown"] = 0
            stats["scorebar_elapsed_s"] = 12.0
        return BOUNDARIES

    mock_detect.side_effect = populate_stats
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config, verbose=True)
    out = capsys.readouterr().out

    scorebar_line = next(
        (line for line in out.splitlines() if line.strip().startswith("Scorebar:")),
        None,
    )
    assert scorebar_line is not None, f"Scorebar line missing in: {out!r}"
    # _format_duration(12.0) -> "0m12s"
    assert "0m12s" in scorebar_line, f"Scorebar line missing elapsed: {scorebar_line!r}"


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_verbose_scorebar_line_without_elapsed_still_prints(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """When scorebar_elapsed_s is absent, the line still renders counts (#386).

    Backwards-compat safety: downstream code (or an older detector) that
    doesn't populate the new key must not break the stats output.
    """
    mock_probe.return_value = PROBE_RESULT

    def populate_stats(*args, **kwargs):
        stats = kwargs.get("stats")
        if stats is not None:
            stats["mode"] = "CPU"
            stats["pass1_samples"] = 100
            stats["pass1_blackout_frames"] = 5
            stats["pass1_elapsed_s"] = 10.0
            stats["pass2_regions"] = 3
            stats["pass2_elapsed_s"] = 2.0
            stats["scorebar_match_boundary"] = 1
            stats["scorebar_in_match"] = 0
            stats["scorebar_non_fl"] = 0
            stats["scorebar_unknown"] = 0
            # intentionally NOT setting scorebar_elapsed_s
        return BOUNDARIES

    mock_detect.side_effect = populate_stats
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config, verbose=True)
    out = capsys.readouterr().out
    scorebar_line = next(
        (line for line in out.splitlines() if line.strip().startswith("Scorebar:")),
        None,
    )
    assert scorebar_line is not None
    assert "1 match_boundary" in scorebar_line


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_verbose_prints_filter_drop_breakdown(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """Verbose stats show Filter section with drop breakdown (#388).

    Troubleshoot scenario: Pass 2 refined 18 candidates, scorebar removed
    some, filter dropped 6 for min_match_duration -> only 8 final. Users
    need to see the drop counts to tune --min-match-duration.
    """
    mock_probe.return_value = PROBE_RESULT

    def populate_stats(*args, **kwargs):
        stats = kwargs.get("stats")
        if stats is not None:
            stats["mode"] = "CPU"
            stats["pass1_samples"] = 3410
            stats["pass1_blackout_frames"] = 31
            stats["pass1_elapsed_s"] = 350.0
            stats["pass2_regions"] = 18
            stats["pass2_elapsed_s"] = 63.0
            stats["scorebar_match_boundary"] = 15
            stats["scorebar_in_match"] = 2
            stats["scorebar_non_fl"] = 1
            stats["scorebar_unknown"] = 0
            stats["filter_candidates"] = 15
            stats["filter_drops"] = {
                "below_min_match_duration": 6,
                "other": 1,
            }
        return BOUNDARIES

    mock_detect.side_effect = populate_stats
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=300.0)

    run_split(Path("input.mp4"), config, verbose=True)
    out = capsys.readouterr().out

    lines = out.splitlines()
    filter_header = next(
        (line for line in lines if line.strip().startswith("Filter:")),
        None,
    )
    assert filter_header is not None, f"Filter: line missing in: {out!r}"
    # 15 candidates - (6 + 1) = 8 kept
    assert "15 candidates" in filter_header
    assert "8 matches" in filter_header

    # Breakdown lines appear as indented entries after the header.
    assert "6 dropped (below min_match_duration)" in out
    assert "1 dropped (other)" in out


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_verbose_filter_breakdown_hides_zero_categories(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """Zero-count drop categories stay hidden to keep output terse (#388)."""
    mock_probe.return_value = PROBE_RESULT

    def populate_stats(*args, **kwargs):
        stats = kwargs.get("stats")
        if stats is not None:
            stats["mode"] = "CPU"
            stats["pass1_samples"] = 100
            stats["pass1_blackout_frames"] = 3
            stats["pass1_elapsed_s"] = 5.0
            stats["pass2_regions"] = 2
            stats["pass2_elapsed_s"] = 1.0
            stats["filter_candidates"] = 2
            stats["filter_drops"] = {
                "below_min_match_duration": 0,
                "other": 0,
            }
        return BOUNDARIES

    mock_detect.side_effect = populate_stats
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config, verbose=True)
    out = capsys.readouterr().out

    assert "Filter: 2 candidates -> 2 matches" in out
    # No breakdown rows when every category is 0.
    assert "0 dropped" not in out


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_verbose_filter_breakdown_absent_when_stats_missing_keys(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """Legacy stats without filter_candidates / filter_drops render safely (#388).

    Backwards-compat: older detect fixtures (or tests that mock
    detect_match_boundaries) may not populate the new keys.  Filter
    section must simply be skipped rather than raising.
    """
    mock_probe.return_value = PROBE_RESULT

    def populate_stats(*args, **kwargs):
        stats = kwargs.get("stats")
        if stats is not None:
            stats["mode"] = "CPU"
            stats["pass1_samples"] = 100
            stats["pass1_blackout_frames"] = 3
            stats["pass1_elapsed_s"] = 5.0
            stats["pass2_regions"] = 2
            stats["pass2_elapsed_s"] = 1.0
            # intentionally NOT setting filter_candidates / filter_drops
        return BOUNDARIES

    mock_detect.side_effect = populate_stats
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config, verbose=True)
    out = capsys.readouterr().out
    assert "Filter:" not in out


# --- unknown match accounting (#433) ---


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_verbose_emits_unknown_match_line_singular(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """1 unknown segment -> ``+ 1 unknown match`` reconciliation line (#433).

    Reproduces the user-test scenario: ``Filter: 8 candidates -> 7 matches``
    with ``Detected 8 match(es)`` due to a recording starting mid-match.
    """
    mock_probe.return_value = PROBE_RESULT

    def populate_stats(*args, **kwargs):
        stats = kwargs.get("stats")
        if stats is not None:
            stats["mode"] = "CPU"
            stats["pass1_samples"] = 100
            stats["pass1_blackout_frames"] = 3
            stats["pass1_elapsed_s"] = 5.0
            stats["pass2_regions"] = 8
            stats["pass2_elapsed_s"] = 1.0
            stats["filter_candidates"] = 8
            stats["filter_drops"] = {
                "below_min_match_duration": 1,
                "other": 0,
            }
            stats["filter_unknown"] = 1
        return BOUNDARIES

    mock_detect.side_effect = populate_stats
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=300.0)

    run_split(Path("input.mp4"), config, verbose=True)
    out = capsys.readouterr().out

    assert "Filter: 8 candidates -> 7 matches" in out
    # Singular form for count==1.
    assert "+ 1 unknown match" in out
    assert "+ 1 unknown matches" not in out


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_verbose_emits_unknown_matches_line_plural(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """2+ unknown segments -> ``+ N unknown matches`` plural form (#433)."""
    mock_probe.return_value = PROBE_RESULT

    def populate_stats(*args, **kwargs):
        stats = kwargs.get("stats")
        if stats is not None:
            stats["mode"] = "CPU"
            stats["pass1_samples"] = 100
            stats["pass1_blackout_frames"] = 3
            stats["pass1_elapsed_s"] = 5.0
            stats["pass2_regions"] = 5
            stats["pass2_elapsed_s"] = 1.0
            stats["filter_candidates"] = 5
            stats["filter_drops"] = {
                "below_min_match_duration": 0,
                "other": 0,
            }
            stats["filter_unknown"] = 2
        return BOUNDARIES

    mock_detect.side_effect = populate_stats
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=300.0)

    run_split(Path("input.mp4"), config, verbose=True)
    out = capsys.readouterr().out

    assert "+ 2 unknown matches" in out


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_verbose_omits_unknown_line_when_zero(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """filter_unknown == 0 -> no unknown line (terse output, #433)."""
    mock_probe.return_value = PROBE_RESULT

    def populate_stats(*args, **kwargs):
        stats = kwargs.get("stats")
        if stats is not None:
            stats["mode"] = "CPU"
            stats["pass1_samples"] = 100
            stats["pass1_blackout_frames"] = 3
            stats["pass1_elapsed_s"] = 5.0
            stats["pass2_regions"] = 3
            stats["pass2_elapsed_s"] = 1.0
            stats["filter_candidates"] = 3
            stats["filter_drops"] = {
                "below_min_match_duration": 0,
                "other": 0,
            }
            stats["filter_unknown"] = 0
        return BOUNDARIES

    mock_detect.side_effect = populate_stats
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=300.0)

    run_split(Path("input.mp4"), config, verbose=True)
    out = capsys.readouterr().out

    assert "unknown match" not in out


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_verbose_unknown_line_absent_when_stat_missing(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """Legacy stats without filter_unknown render without unknown line (#433).

    Backwards-compat: older detect fixtures may not populate the new key
    (the verbose Filter section was added in #388, this counter in #433).
    """
    mock_probe.return_value = PROBE_RESULT

    def populate_stats(*args, **kwargs):
        stats = kwargs.get("stats")
        if stats is not None:
            stats["mode"] = "CPU"
            stats["pass1_samples"] = 100
            stats["pass1_blackout_frames"] = 3
            stats["pass1_elapsed_s"] = 5.0
            stats["pass2_regions"] = 3
            stats["pass2_elapsed_s"] = 1.0
            stats["filter_candidates"] = 3
            stats["filter_drops"] = {
                "below_min_match_duration": 0,
                "other": 0,
            }
            # intentionally NOT setting filter_unknown
        return BOUNDARIES

    mock_detect.side_effect = populate_stats
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=300.0)

    run_split(Path("input.mp4"), config, verbose=True)
    out = capsys.readouterr().out

    assert "unknown match" not in out


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_verbose_filter_section_skipped_on_whole_video_fallback(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """Whole-video fallback produces ``candidates=0, drops=0`` -> hide Filter (#388).

    When every refined region is removed at the scorebar stage, the
    filter function still returns one whole-video match via the fallback
    path.  Emitting ``Filter: 0 candidates -> 0 matches`` in that case
    would contradict the ``Detected 1 match(es)`` line and confuse users.
    """
    mock_probe.return_value = PROBE_RESULT

    def populate_stats(*args, **kwargs):
        stats = kwargs.get("stats")
        if stats is not None:
            stats["mode"] = "CPU"
            stats["pass1_samples"] = 100
            stats["pass1_blackout_frames"] = 3
            stats["pass1_elapsed_s"] = 5.0
            stats["pass2_regions"] = 2
            stats["pass2_elapsed_s"] = 1.0
            stats["filter_candidates"] = 0
            stats["filter_drops"] = {
                "below_min_match_duration": 0,
                "other": 0,
            }
        return BOUNDARIES

    mock_detect.side_effect = populate_stats
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config, verbose=True)
    out = capsys.readouterr().out
    assert "Filter:" not in out, (
        f"Filter: section should be hidden on whole-video fallback: {out!r}"
    )


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_non_verbose_does_not_print_stats(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """Default (non-verbose) run must NOT pass stats into detect (avoid overhead)."""
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config, verbose=False)
    _, detect_kwargs = mock_detect.call_args
    assert detect_kwargs["stats"] is None
    out = capsys.readouterr().out
    assert "Pass 1" not in out
    assert "Scorebar:" not in out
    # Environment header is a verbose-only feature too
    assert "Python" not in out


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_verbose_reports_gpu_fallback_mode(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """Verbose Pass 1 line distinguishes 'GPU' from 'CPU (GPU fallback)' (#336 / #335).

    This is the core motivation for #336 Phase 1 -- the mode string is
    what lets us diagnose the GPU/CPU +-2 discrepancy tracked in #335.
    A bug here (e.g. always reporting 'CPU') would silently hide
    whether the fallback actually fired.
    """
    mock_probe.return_value = PROBE_RESULT

    def populate_fallback(*args, **kwargs):
        stats = kwargs.get("stats")
        if stats is not None:
            stats["mode"] = "CPU (GPU fallback)"
            stats["pass1_samples"] = 100
            stats["pass1_blackout_frames"] = 0
            stats["pass1_elapsed_s"] = 1.0
        return BOUNDARIES

    mock_detect.side_effect = populate_fallback
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0, use_gpu=True)

    run_split(Path("input.mp4"), config, verbose=True)
    out = capsys.readouterr().out
    assert "Pass 1 (CPU (GPU fallback))" in out


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_verbose_detecting_line_shows_audio_off_when_no_audio(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """Verbose Detecting line reflects --no-audio (#336).

    Exercises the non-frozen branch of _audio_status_str (#384); with
    AUDIO_FROZEN=True in production, the frozen branch dominates, so this
    test patches it off to assert the config.no_audio-driven flip.
    """
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0, no_audio=True)

    with patch("allaganeye.audio.AUDIO_FROZEN", False):
        run_split(Path("input.mp4"), config, verbose=True)
    out = capsys.readouterr().out
    assert "audio=off" in out
    assert "audio=on" not in out


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_verbose_detecting_line_shows_audio_frozen_when_module_frozen(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """Verbose Detecting line shows 'audio=frozen' when AUDIO_FROZEN is True (#384).

    The audio module is currently frozen (#327), so regardless of the
    ``--no-audio`` flag the scan is skipped.  verbose output must reflect
    that reality instead of reading ``config.no_audio`` blindly, which
    previously printed misleading ``audio=on``.
    """
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)

    # no_audio=False would previously have produced audio=on; with
    # AUDIO_FROZEN=True we expect audio=frozen.
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0, no_audio=False)

    with patch("allaganeye.audio.AUDIO_FROZEN", True):
        run_split(Path("input.mp4"), config, verbose=True)
    out = capsys.readouterr().out
    assert "audio=frozen" in out, f"expected audio=frozen in: {out!r}"
    assert "audio=on" not in out
    assert "audio=off" not in out


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_verbose_audio_frozen_overrides_no_audio_flag(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """When frozen, the verbose status stays 'frozen' even with --no-audio (#384).

    Prevents regression to config.no_audio taking precedence over the
    frozen module state (the original bug).
    """
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0, no_audio=True)

    with patch("allaganeye.audio.AUDIO_FROZEN", True):
        run_split(Path("input.mp4"), config, verbose=True)
    out = capsys.readouterr().out
    assert "audio=frozen" in out
    assert "audio=off" not in out


def test_audio_status_str_helper_matches_run_audio_scan_contract():
    """_audio_status_str output stays in sync with _run_audio_scan behaviour (#384).

    Direct unit coverage of the helper.  If this test passes but the
    verbose output still shows wrong values, the helper isn't being called.
    """
    from allaganeye.commands.split_matches import _audio_status_str

    with patch("allaganeye.audio.AUDIO_FROZEN", True):
        assert _audio_status_str(no_audio=False) == "frozen"
        assert _audio_status_str(no_audio=True) == "frozen"

    with patch("allaganeye.audio.AUDIO_FROZEN", False):
        assert _audio_status_str(no_audio=False) == "on"
        assert _audio_status_str(no_audio=True) == "off"


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_verbose_emits_splitting_elapsed_with_match_count(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """Verbose mode emits 'Splitting: N matches, Xs' after split (#387).

    Pass 1 / Pass 2 / Scorebar already report elapsed; Splitting was the
    only hidden phase, forcing users to do arithmetic on Total to infer
    its cost.
    """
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES  # 2 matches
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config, verbose=True)
    out = capsys.readouterr().out

    splitting_line = next(
        (line for line in out.splitlines() if line.strip().startswith("Splitting:")),
        None,
    )
    assert splitting_line is not None, f"Splitting: line missing in: {out!r}"
    assert "2 matches" in splitting_line, (
        f"Splitting line should report count=2: {splitting_line!r}"
    )


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_non_verbose_does_not_emit_splitting_line(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """Splitting elapsed is verbose-only; default runs stay terse (#387)."""
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config, verbose=False)
    out = capsys.readouterr().out
    assert "Splitting:" not in out


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.probe_video")
def test_verbose_cache_hit_also_emits_splitting_line(
    mock_probe, mock_split, tmp_path, capsys
):
    """Cache-hit + split path also emits the Splitting line (#387).

    Symmetry with the non-cache path so users see the same breakdown
    whether or not Pass 1/2 ran.
    """
    source = tmp_path / "input.mp4"
    source.write_bytes(b"")
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    tmp_path.mkdir(parents=True, exist_ok=True)
    _save_cache(
        tmp_path / ".detection_cache.json",
        source,
        PROBE_RESULT,
        config.sample_interval,
        config,
        BOUNDARIES,
    )

    mock_probe.return_value = PROBE_RESULT
    mock_split.return_value = _output_files(tmp_path)

    run_split(source, config, verbose=True)
    out = capsys.readouterr().out
    assert "(cached)" in out
    assert "Splitting:" in out, f"cache+split path must show Splitting: {out!r}"


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_verbose_dry_run_emits_total(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """Verbose + dry-run still emits the Total: line (#336)."""
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    config = SplitConfig(output_dir=tmp_path, dry_run=True, min_match_duration=60.0)

    run_split(Path("input.mp4"), config, verbose=True)
    out = capsys.readouterr().out
    assert "Dry run: skipping split" in out
    assert "Total:" in out
    mock_split.assert_not_called()


def _seed_cache(source: Path, output_dir: Path, config: SplitConfig) -> None:
    """Write a .detection_cache.json entry matching ``config`` so ``_load_cache``
    hits.  Helper for cache-hit tests (#381)."""
    source.write_bytes(b"")
    output_dir.mkdir(parents=True, exist_ok=True)
    _save_cache(
        output_dir / ".detection_cache.json",
        source,
        PROBE_RESULT,
        config.sample_interval,
        config,
        BOUNDARIES,
    )


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.probe_video")
def test_verbose_cache_hit_split_emits_total(mock_probe, mock_split, tmp_path, capsys):
    """Verbose + cache-hit + split path must emit the Total: line (#381).

    Previously only the cache-miss paths emitted Total:, so users who ran
    repeatedly saw "split done, no timing" which broke the UX symmetry.
    """
    source = tmp_path / "input.mp4"
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    _seed_cache(source, tmp_path, config)

    mock_probe.return_value = PROBE_RESULT
    mock_split.return_value = _output_files(tmp_path)

    run_split(source, config, verbose=True)

    out = capsys.readouterr().out
    assert "(cached)" in out, "cache hit path expected"
    assert "Total:" in out, (
        f"verbose+cache+split must emit Total: line (#381)\n--- captured ---\n{out}"
    )


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.probe_video")
def test_verbose_cache_hit_dry_run_emits_total(
    mock_probe, mock_split, tmp_path, capsys
):
    """Verbose + cache-hit + dry-run path must also emit Total: (#381)."""
    source = tmp_path / "input.mp4"
    config = SplitConfig(output_dir=tmp_path, dry_run=True, min_match_duration=60.0)
    _seed_cache(source, tmp_path, config)

    mock_probe.return_value = PROBE_RESULT

    run_split(source, config, verbose=True)

    out = capsys.readouterr().out
    assert "Dry run: skipping split" in out
    assert "Total:" in out
    mock_split.assert_not_called()


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.probe_video")
def test_cache_hit_quiet_suppresses_total(mock_probe, mock_split, tmp_path, capsys):
    """Quiet mode suppresses Total: even on cache-hit split path (#381).

    _emit_total_time gates on both verbose and show, so quiet (show=False)
    must still hide Total: regardless of verbose setting.
    """
    source = tmp_path / "input.mp4"
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    _seed_cache(source, tmp_path, config)

    mock_probe.return_value = PROBE_RESULT
    mock_split.return_value = _output_files(tmp_path)

    run_split(source, config, verbose=True, quiet=True)

    out = capsys.readouterr().out
    assert "Total:" not in out


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.probe_video")
def test_verbose_cache_hit_prints_detection_params(
    mock_probe, mock_split, tmp_path, capsys
):
    """Verbose + cache-hit prints the cached detection params (#380).

    Previously the cache-hit path early-returned before the cache-miss
    path's ``Detecting match boundaries (...)`` summary printed, leaving
    verbose users without any parameter context.  The new
    ``_display_cache_hit_params`` helper reads the cache and echoes the
    same key/value tokens troubleshooters rely on.
    """
    source = tmp_path / "input.mp4"
    config = SplitConfig(
        output_dir=tmp_path,
        sample_interval=2.0,
        blackout_threshold=18.0,
        min_match_duration=240.0,
        min_blackout_duration=2.5,
        no_audio=False,
    )
    _seed_cache(source, tmp_path, config)

    mock_probe.return_value = PROBE_RESULT
    mock_split.return_value = _output_files(tmp_path)

    run_split(source, config, verbose=True)
    out = capsys.readouterr().out

    # Header line and the five tokens that match the cache-miss summary.
    assert "Cache hit: detection params from .detection_cache.json" in out
    assert "sample_interval=2.0s" in out
    assert "threshold=18.0" in out
    assert "min_match=240.0s" in out
    assert "min_blackout=2.5s" in out
    # AUDIO_FROZEN=True in production so the audio token is 'frozen'
    # (#384 contract: audio display is driven by the helper, not
    # config.no_audio directly).
    assert "audio=frozen" in out
    # vtuber provenance token (PR #823 R1): 検出 mode を表示に含める。
    assert "vtuber=off" in out


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.probe_video")
def test_non_verbose_cache_hit_suppresses_params_line(
    mock_probe, mock_split, tmp_path, capsys
):
    """Default (non-verbose) cache-hit must not print the params line (#380).

    Verbose-only output; the quiet path stays clean.
    """
    source = tmp_path / "input.mp4"
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    _seed_cache(source, tmp_path, config)

    mock_probe.return_value = PROBE_RESULT
    mock_split.return_value = _output_files(tmp_path)

    run_split(source, config, verbose=False)
    out = capsys.readouterr().out
    assert "Cache hit: detection params" not in out


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.probe_video")
def test_verbose_cache_hit_audio_line_matches_cache_miss_path(
    mock_probe, mock_split, tmp_path, capsys
):
    """Cache-hit audio token mirrors cache-miss helper output (#380 + #384).

    Guards the regression where the cache-hit summary could read
    config.no_audio directly instead of routing through
    ``_audio_status_str`` (which encodes AUDIO_FROZEN). Patching the
    module to False must flip the rendered token to 'on' in both paths.
    """
    source = tmp_path / "input.mp4"
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0, no_audio=False)
    _seed_cache(source, tmp_path, config)

    mock_probe.return_value = PROBE_RESULT
    mock_split.return_value = _output_files(tmp_path)

    with patch("allaganeye.audio.AUDIO_FROZEN", False):
        run_split(source, config, verbose=True)
    out = capsys.readouterr().out

    # The params summary sits on the line right after the header.
    header_idx = out.find("Cache hit:")
    assert header_idx >= 0
    tail = out[header_idx:]
    # When AUDIO_FROZEN=False and no_audio=False, audio=on.
    assert "audio=on" in tail, f"expected audio=on in cache hit summary: {tail[:400]!r}"


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.probe_video")
def test_verbose_cache_hit_prints_vtuber_on_token(
    mock_probe, mock_split, tmp_path, capsys
):
    """vtuber=True で生成した cache の hit 表示は vtuber=on (provenance 可視化).

    cache key fix (PR #823) で mode 混在 hit は不可能になったが、表示にも
    provenance を出して troubleshoot 報告から検出 mode を判別可能にする。
    """
    source = tmp_path / "input.mp4"
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0, vtuber=True)
    _seed_cache(source, tmp_path, config)

    mock_probe.return_value = PROBE_RESULT
    mock_split.return_value = _output_files(tmp_path)

    run_split(source, config, verbose=True)
    out = capsys.readouterr().out

    header_idx = out.find("Cache hit:")
    assert header_idx >= 0
    assert "vtuber=on" in out[header_idx:]


@patch(f"{MODULE}._run_detection")
@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.probe_video")
def test_verbose_cache_miss_summary_includes_vtuber_token(
    mock_probe, mock_split, mock_run_detection, tmp_path, capsys
):
    """cache-miss の Detecting summary に vtuber token が出る (provenance 可視化)."""
    source = tmp_path / "input.mp4"
    source.write_bytes(b"")
    mock_probe.return_value = PROBE_RESULT
    mock_split.return_value = _output_files(tmp_path)
    mock_run_detection.return_value = BOUNDARIES

    config = SplitConfig(output_dir=tmp_path, no_cache=True, vtuber=True)
    run_split(source, config, verbose=True)
    assert "vtuber=on" in capsys.readouterr().out

    config_off = SplitConfig(output_dir=tmp_path, no_cache=True)
    run_split(source, config_off, verbose=True)
    assert "vtuber=off" in capsys.readouterr().out


def test_display_cache_hit_params_malformed_json_emits_unavailable(tmp_path, capsys):
    """Malformed JSON emits header + (unavailable: ...) instead of silent (#380).

    Previously the helper returned silently on any read/parse failure,
    hiding verbose output even though the user explicitly asked for it.
    The helper now always emits the ``Cache hit: ...`` header so users
    can confirm verbose mode is active, and surfaces the specific
    failure reason so degraded cache state is diagnosable.
    """
    from allaganeye.commands.split_matches import _display_cache_hit_params

    cache_path = tmp_path / ".detection_cache.json"
    cache_path.write_text("not json at all", encoding="utf-8")

    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    # Must not raise.
    _display_cache_hit_params(cache_path, config)
    out = capsys.readouterr().out
    assert "Cache hit: detection params from .detection_cache.json" in out
    assert "(unavailable: cache file is not valid JSON)" in out


# ------------------------------------------------------------
# G1-G5 unavailable fallback gap tests (#380 review)
# ------------------------------------------------------------


def test_display_cache_hit_params_empty_params_dict_emits_unavailable(tmp_path, capsys):
    """G1: Empty ``params`` dict -> header + (unavailable: no params section)."""
    from allaganeye.commands.split_matches import _display_cache_hit_params

    cache_path = tmp_path / ".detection_cache.json"
    cache_path.write_text(json.dumps({"params": {}}), encoding="utf-8")

    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    _display_cache_hit_params(cache_path, config)
    out = capsys.readouterr().out
    assert "Cache hit: detection params from .detection_cache.json" in out
    assert "(unavailable: cache file has no params section)" in out


def test_display_cache_hit_params_missing_params_key_emits_unavailable(
    tmp_path, capsys
):
    """G2: Missing ``params`` key -> header + (unavailable: no params section)."""
    from allaganeye.commands.split_matches import _display_cache_hit_params

    cache_path = tmp_path / ".detection_cache.json"
    cache_path.write_text(json.dumps({"boundaries": []}), encoding="utf-8")

    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    _display_cache_hit_params(cache_path, config)
    out = capsys.readouterr().out
    assert "Cache hit: detection params from .detection_cache.json" in out
    assert "(unavailable: cache file has no params section)" in out


def test_display_cache_hit_params_non_dict_params_emits_unavailable(tmp_path, capsys):
    """G3: ``params`` is not a dict -> header + (unavailable: no params section).

    ``_load_cache`` validates top-level structure but not that ``params``
    itself is a dict, so a corrupt cache with ``{"params": "str"}`` can
    reach the helper.
    """
    from allaganeye.commands.split_matches import _display_cache_hit_params

    cache_path = tmp_path / ".detection_cache.json"
    cache_path.write_text(json.dumps({"params": "not a dict"}), encoding="utf-8")

    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    _display_cache_hit_params(cache_path, config)
    out = capsys.readouterr().out
    assert "Cache hit: detection params from .detection_cache.json" in out
    assert "(unavailable: cache file has no params section)" in out


def test_display_cache_hit_params_missing_individual_keys_use_placeholder(
    tmp_path, capsys
):
    """G4: Individual key absence falls back to ``?`` placeholder tokens.

    Legacy caches may lack newer keys (``no_audio`` introduced later).
    The helper must still emit a valid line with ``?`` in place of each
    missing value so the summary structure stays intact.
    """
    from allaganeye.commands.split_matches import _display_cache_hit_params

    cache_path = tmp_path / ".detection_cache.json"
    # Only one key present; every other shows ``?``.
    cache_path.write_text(
        json.dumps({"params": {"sample_interval": 3.0}}), encoding="utf-8"
    )

    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    _display_cache_hit_params(cache_path, config)
    out = capsys.readouterr().out
    assert "Cache hit: detection params from .detection_cache.json" in out
    assert "sample_interval=3.0s" in out
    assert "threshold=?" in out
    assert "min_match=?s" in out
    assert "min_blackout=?s" in out
    # audio= token driven by config.no_audio when cache key is absent.
    assert "audio=" in out


def test_display_cache_hit_params_oserror_emits_unavailable(tmp_path, capsys):
    """G5: OSError (permission / IO) -> header + (unavailable: OSError).

    Simulates a post-``_load_cache`` race where the file became
    unreadable (deletion, chmod, IO error) between validation and the
    helper call.
    """
    from allaganeye.commands.split_matches import _display_cache_hit_params

    cache_path = tmp_path / ".detection_cache.json"
    # File does not exist so read_text raises FileNotFoundError (OSError).
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    _display_cache_hit_params(cache_path, config)
    out = capsys.readouterr().out
    assert "Cache hit: detection params from .detection_cache.json" in out
    assert "(unavailable: cache file unreadable" in out
    # Concrete exception class name surfaced for diagnostics.
    assert "FileNotFoundError" in out


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_audio_promotion_line_suppressed_when_zero(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """Audio promotion line is hidden when no promotions happened (#336)."""
    mock_probe.return_value = PROBE_RESULT

    def populate_no_promo(*args, **kwargs):
        stats = kwargs.get("stats")
        if stats is not None:
            stats["mode"] = "CPU"
            stats["pass1_samples"] = 100
            stats["pass1_blackout_frames"] = 0
            stats["pass1_elapsed_s"] = 1.0
            stats["pass2_regions"] = 0
            stats["pass2_elapsed_s"] = 0.1
            stats["scorebar_match_boundary"] = 2
            stats["scorebar_in_match"] = 0
            stats["scorebar_non_fl"] = 0
            stats["scorebar_unknown"] = 0
            stats["audio_promotions"] = 0
        return BOUNDARIES

    mock_detect.side_effect = populate_no_promo
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config, verbose=True)
    out = capsys.readouterr().out
    assert "Scorebar:" in out  # scorebar line still shown
    assert "Audio promotion" not in out  # but promo line hidden


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_verbose_workers_auto_shows_resolved_count(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """Verbose summary resolves workers=auto to the actual count (#389).

    ``workers=auto`` alone doesn't let users diagnose CPU under-utilisation
    or hit the right number for their box; the resolved ``min(cpu_count,
    24)`` must be shown alongside.
    """
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0, workers=None)

    run_split(Path("input.mp4"), config, verbose=True)
    out = capsys.readouterr().out

    # Line must contain "workers=auto (<number>)" with the number >= 1.
    import re as _re

    m = _re.search(r"workers=auto \((\d+)\)", out)
    assert m is not None, f"expected 'workers=auto (<n>)' in: {out!r}"
    assert int(m.group(1)) >= 1


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_verbose_workers_explicit_shows_plain_number(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """Explicit workers=N is printed as the number without '(auto)' (#389)."""
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0, workers=8)

    run_split(Path("input.mp4"), config, verbose=True)
    out = capsys.readouterr().out
    assert "workers=8" in out
    assert "workers=auto" not in out
    assert "(auto)" not in out  # no parentheses suffix for explicit values


def test_workers_summary_str_helper_contract():
    """_workers_summary_str unit coverage (#389).

    Ensures future changes to _resolve_workers fallback (e.g. cpu_count
    detection tweaks) stay reflected in the verbose output.
    """
    from allaganeye.commands.split_matches import _workers_summary_str

    assert _workers_summary_str(1) == "1"
    assert _workers_summary_str(16) == "16"

    with patch("allaganeye.video.detector._resolve_workers", return_value=12):
        assert _workers_summary_str(None) == "auto (12)"


def test_probe_ffmpeg_version_returns_unknown_on_failure():
    """ffmpeg -version failure yields '(unknown)' without raising (#336)."""
    import subprocess

    from allaganeye.commands.split_matches import _probe_ffmpeg_version

    with patch("subprocess.run", side_effect=subprocess.SubprocessError("boom")):
        result = _probe_ffmpeg_version()
    assert result == "(unknown)"


# --- ffmpeg version string trimming (#383) ---


@pytest.mark.parametrize(
    ("raw_first_line", "expected"),
    [
        # Windows Gyan full build: the original #383 reproduction
        (
            "ffmpeg version 8.1-full_build-www.gyan.dev Copyright (c) 2000-2025",
            "8.1",
        ),
        # Linux distribution build with Ubuntu patch metadata
        (
            "ffmpeg version 4.4.2-0ubuntu0.22.04.1 Copyright (c) 2000-2021",
            "4.4.2",
        ),
        # BtbN 'n' prefix (common on nightly CI builds)
        ("ffmpeg version n7.1 Copyright (c) 2000-2024", "7.1"),
        # BtbN LGPL autobuild (shipped with Portable ZIP since #508 / #531;
        # date matches $FFmpegBuildTag = autobuild-2026-04-22-13-15)
        (
            "ffmpeg version n8.1-10-g7f5c90f77e-20260422 Copyright (c) 2000-2026",
            "8.1",
        ),
        # essentials_build variant
        ("ffmpeg version 6.0-essentials_build-www.gyan.dev", "6.0"),
        # Bare version (macOS Homebrew style)
        ("ffmpeg version 5.1.4 Copyright (c) 2000-2023", "5.1.4"),
    ],
)
def test_probe_ffmpeg_version_trims_build_metadata(raw_first_line, expected):
    """_probe_ffmpeg_version returns major.minor[.patch] only (#383)."""
    from unittest.mock import MagicMock

    from allaganeye.commands.split_matches import _probe_ffmpeg_version

    mock_result = MagicMock(stdout=raw_first_line + "\n")
    with patch("subprocess.run", return_value=mock_result):
        result = _probe_ffmpeg_version()
    assert result == expected


def test_probe_ffmpeg_version_falls_back_to_raw_when_regex_misses():
    """Unparseable tokens return raw string rather than (unknown) (#383)."""
    from unittest.mock import MagicMock

    from allaganeye.commands.split_matches import _probe_ffmpeg_version

    # "git-" style dev build has no numeric prefix after the regex.
    mock_result = MagicMock(stdout="ffmpeg version git-2023-01-01-abcdef Copyright\n")
    with patch("subprocess.run", return_value=mock_result):
        result = _probe_ffmpeg_version()
    assert result == "git-2023-01-01-abcdef"


def test_probe_ffmpeg_version_unknown_when_format_unexpected():
    """Malformed first line (no 'ffmpeg version' prefix) yields (unknown)."""
    from unittest.mock import MagicMock

    from allaganeye.commands.split_matches import _probe_ffmpeg_version

    mock_result = MagicMock(stdout="not ffmpeg output at all\n")
    with patch("subprocess.run", return_value=mock_result):
        result = _probe_ffmpeg_version()
    assert result == "(unknown)"


@pytest.mark.parametrize(
    ("raw_first_line", "expected"),
    [
        # 'v' prefix is less common than 'n' but the regex supports both.
        # Pin this so a future regex narrowing to ``^n?`` surfaces here.
        ("ffmpeg version v7.0 Copyright (c) 2000-2024", "7.0"),
        ("ffmpeg version v6.1.1-custom Copyright (c) 2000-2023", "6.1.1"),
    ],
)
def test_probe_ffmpeg_version_handles_v_prefix(raw_first_line, expected):
    """'v' prefix variant is trimmed just like 'n' (#383).

    The parametric coverage in the PR focuses on ``n`` (BtbN nightly style)
    and bare numerics.  ``^[nv]?`` in the regex also accepts ``v`` -- pin
    that explicitly so a narrowing to ``^n?`` would fail loudly.
    """
    from unittest.mock import MagicMock

    from allaganeye.commands.split_matches import _probe_ffmpeg_version

    mock_result = MagicMock(stdout=raw_first_line + "\n")
    with patch("subprocess.run", return_value=mock_result):
        result = _probe_ffmpeg_version()
    assert result == expected


# --- ETA formatter (issue #333) ---


def test_format_eta_seconds():
    from allaganeye.commands.split_matches import _format_eta

    assert _format_eta(5) == "5s"
    assert _format_eta(59) == "59s"


def test_format_eta_minutes():
    from allaganeye.commands.split_matches import _format_eta

    assert _format_eta(60) == "1m00s"
    assert _format_eta(125) == "2m05s"


def test_format_eta_hours():
    from allaganeye.commands.split_matches import _format_eta

    assert _format_eta(3600) == "1h00m"
    assert _format_eta(3700) == "1h01m"


# --- Quiet strict-silent (#418) ---
#
# Per user-confirmed matrix v2 spec, ``-q`` (quiet) emits ONLY the output
# file listing (``Output:`` / filenames / ``Metadata:``) on stdout.  Every
# dry-run / cache notice / verbose line must stay hidden, on every branch
# (cache-hit vs cache-miss, dry-run vs split).  The regression was that
# ``Dry run: skipping split`` was echoed without a ``show`` gate so
# ``-q --dry-run`` leaked the notice on both paths.


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_quiet_dry_run_cache_miss_stdout_empty(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """-q --dry-run (cache-miss) emits nothing on stdout (#418 L)."""
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    config = SplitConfig(output_dir=tmp_path, dry_run=True, min_match_duration=60.0)

    run_split(Path("input.mp4"), config, quiet=True)

    captured = capsys.readouterr()
    assert captured.out == "", f"stdout leaked under -q --dry-run: {captured.out!r}"
    mock_split.assert_not_called()


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.probe_video")
def test_quiet_dry_run_cache_hit_stdout_empty(mock_probe, mock_split, tmp_path, capsys):
    """-q --dry-run (cache-hit) emits nothing on stdout (#418 L)."""
    source = tmp_path / "input.mp4"
    config = SplitConfig(output_dir=tmp_path, dry_run=True, min_match_duration=60.0)
    _seed_cache(source, tmp_path, config)

    mock_probe.return_value = PROBE_RESULT

    run_split(source, config, quiet=True)

    captured = capsys.readouterr()
    assert captured.out == "", (
        f"stdout leaked under -q --dry-run cache-hit: {captured.out!r}"
    )
    mock_split.assert_not_called()


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.probe_video")
def test_quiet_cache_hit_only_output_listing(mock_probe, mock_split, tmp_path, capsys):
    """-q cache-hit emits ONLY the output listing -- no '(cached)' (#418 M)."""
    source = tmp_path / "input.mp4"
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    _seed_cache(source, tmp_path, config)

    mock_probe.return_value = PROBE_RESULT
    mock_split.return_value = _output_files(tmp_path)

    run_split(source, config, quiet=True)

    out = capsys.readouterr().out
    assert "(cached)" not in out
    assert "Probing:" not in out
    assert "Detected" not in out
    assert "Dry run" not in out
    assert f"Output: {tmp_path}" in out
    assert "match_001.mp4" in out
    assert "Metadata:" in out


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_quiet_no_cache_only_output_listing(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """-q --no-cache emits ONLY the output listing (#418)."""
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0, no_cache=True)

    run_split(Path("input.mp4"), config, quiet=True)

    out = capsys.readouterr().out
    assert "Probing:" not in out
    assert "Detected" not in out
    assert "Dry run" not in out
    assert "(cached)" not in out
    assert f"Output: {tmp_path}" in out
    assert "match_001.mp4" in out
    assert "Metadata:" in out


# ============================================================
# #365: progress bar ETA ラベル付与の format 検証
# ============================================================

_ETA_LINE_PATTERN = re.compile(r"\b\d{1,3}%\s+ETA:\s+(?:\d+d\s+)?\d+:\d{2}:\d{2}\b")


def _drive_to_known_eta(bar: _ETAProgressBar, completed: int) -> None:
    """Force eta_known by simulating elapsed time + progress.

    click ProgressBar は ``start`` / ``last_eta`` が現在時刻で初期化され、
    ``make_step`` 内の ``time.time() - self.last_eta < 1.0`` 条件が True の
    間は ``eta_known`` が更新されない。テストでは ``start`` と ``last_eta``
    を 10 秒前に巻き戻した上で update() し、``make_step`` 内の条件を
    満たして ``eta_known=True`` にする。
    """
    past = time.time() - 10.0  # 10s 前から動いていた体
    bar.start = past
    bar.last_eta = past
    bar.update(completed)


@pytest.mark.parametrize("label", ["Detecting", "Refining", "Scorebar", "Splitting"])
def test_eta_progressbar_label_present_for_all_bars(label: str) -> None:
    """4 bar 全てで 'ETA: H:MM:SS' label を出すこと (#365)."""
    bar = _eta_progressbar(100, label)
    _drive_to_known_eta(bar, 50)

    line = bar.format_progress_line()

    assert line.startswith(label.ljust(_PROGRESS_LABEL_WIDTH))
    assert "ETA: " in line, f"missing 'ETA: ' label in: {line!r}"
    assert _ETA_LINE_PATTERN.search(line), f"format mismatch: {line!r}"


def test_eta_progressbar_suppresses_eta_in_gpu_mode() -> None:
    """suppress_click_eta=True (GPU mode #438) では ETA tail を出さず percent のみ."""
    bar = _eta_progressbar(100, "Detecting", suppress_click_eta=True)
    _drive_to_known_eta(bar, 50)

    line = bar.format_progress_line()

    assert "ETA: " not in line
    assert re.search(r"\b\d{1,3}%\s*$", line.rstrip()), line


def test_eta_progressbar_placeholder_eta_before_first_update() -> None:
    """update 前 (eta_known=False) は 'ETA: --:--:--' placeholder を出す (#365 Idios feedback)."""
    bar = _eta_progressbar(100, "Detecting")
    # _drive_to_known_eta を呼ばない -- eta_known=False のまま (start は初期化済みだが update 未実行で eta_known は False)

    line = bar.format_progress_line()

    assert "ETA: --:--:--" in line, f"missing placeholder in: {line!r}"
    assert "0%" in line


def test_eta_progressbar_gpu_dispatching_label_with_eta_placeholder() -> None:
    """GPU mode dispatching 段階の label に 'ETA: --:--:--' を含む format を verify (#365).

    Caller (on_chunk_dispatch) が更新する label の expected string を bar に
    直接設定し、format_progress_line() 出力に 'ETA: --:--:--' が含まれる
    + subclass は ETA tail を出さない (show_eta=False) ことを確認する。
    chunk 1 完了後は on_chunk が label を上書きするため、この ETA は
    dispatching 段階にのみ表示される。
    """
    bar = _eta_progressbar(100, "Detecting", suppress_click_eta=True)
    # caller (on_chunk_dispatch) が更新する label 文字列の expected
    bar.label = "Detecting [dispatching 32 chunks, ETA: --:--:--]".ljust(
        _PROGRESS_LABEL_WIDTH
    )

    line = bar.format_progress_line()

    # caller label 内の placeholder を確認
    assert "ETA: --:--:--" in line, f"caller label placeholder missing in: {line!r}"
    # subclass は show_eta=False で ETA tail を出さない (二重表示防止 #438)
    # ETA は label 内 1 つのみ
    assert line.count("ETA:") == 1, f"expected single ETA occurrence in: {line!r}"


def test_eta_progressbar_bar_visual_uses_dashes_and_36_width() -> None:
    """bar visual (empty_char='-' + width=36) が click.progressbar() factory baseline を維持すること (#365).

    `_eta_progressbar` を `click.progressbar()` factory から `_ETAProgressBar(...)`
    class 直接インスタンス化に refactor した際、factory と class の defaults 差異
    (empty_char='-' vs ' '、width=36 vs 30) で silent visual regression が起きうる。
    issue #365 期待動作 `Detecting  ####---  93% ETA: 0:00:22` の `####---` 部分
    (dash empty char) を保持するための regression test (PR #687 review feedback #3 対応)。
    """
    bar = _eta_progressbar(100, "Detecting")
    _drive_to_known_eta(bar, 50)

    line = bar.format_progress_line()

    # empty char が '-' (issue #365 期待動作 ####--- に整合)
    assert "-" in line, f"expected '-' as empty char in: {line!r}"
    # width=36 で 50% 進捗 -> 18 fill + 18 empty
    assert "#" * 18 in line, f"expected 18 fills (width=36, 50%): {line!r}"
    assert "-" * 18 in line, f"expected 18 dashes (width=36, 50%): {line!r}"


def test_eta_progressbar_finished_no_eta_tail() -> None:
    """100% 完了時 (finished=True) は 'ETA: ' tail を出さない (commit 9bc3788 仕様、#365、PR #687 review feedback #6 対応)."""
    bar = _eta_progressbar(100, "Splitting")
    _drive_to_known_eta(bar, 100)  # 100% で finished=True

    line = bar.format_progress_line()

    assert "ETA:" not in line, f"100% で ETA tail が残存: {line!r}"
    assert "100%" in line


# -- #644 brightness_samples wiring through run_split (一気通貫) --

# `MODULE` / `PROBE_RESULT` / `BOUNDARIES` / `_mock_audio_scan` (autouse)
# は file 冒頭で既定義。`mock_pipeline` fixture は `detect_match_boundaries`
# を mock するが、本ケースは `_run_detection` を直接 patch して
# `brightness_callback` の wiring を assert したいため、`mock_pipeline` は
# 使わず個別に patch する。


@patch(f"{MODULE}._run_detection")
@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.probe_video")
def test_run_split_writes_brightness_samples_when_callback_fires(
    mock_probe, mock_split, mock_run_detection, tmp_path
):
    """#644 -- run_split (一気通貫) で Pass 1 が走ったら brightness_samples
    が metadata.json に書かれること。`_run_detection` に渡される
    `brightness_callback` を fake_run_detection から call して輝度 sample
    を注入し、最終 metadata.json に payload が現れることを assert する。
    """
    mock_probe.return_value = PROBE_RESULT

    def fake_run_detection(*args, **kwargs):
        cb = kwargs.get("brightness_callback")
        assert cb is not None, (
            "run_split must pass brightness_callback to _run_detection (#644)"
        )
        cb({0.0: 10.5, 0.5: 12.3, 1.0: 14.1})
        return BOUNDARIES

    mock_run_detection.side_effect = fake_run_detection

    output_dir = tmp_path / "out"
    mock_split.return_value = [
        output_dir / "match_001.mp4",
        output_dir / "match_002.mp4",
    ]

    video = tmp_path / "input.mp4"
    video.write_bytes(b"")
    config = SplitConfig(output_dir=output_dir, min_match_duration=60.0)

    run_split(video, config, verbose=False, quiet=True)

    metadata_path = output_dir / "metadata.json"
    assert metadata_path.exists()
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert "brightness_samples" in payload, (
        "run_split で Pass 1 が走った時 brightness_samples が metadata.json に "
        "書かれているはず (#644)"
    )
    samples = payload["brightness_samples"]
    assert isinstance(samples, dict)
    assert "values" in samples and isinstance(samples["values"], list)
    assert len(samples["values"]) > 0


@patch(f"{MODULE}._run_detection")
@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.probe_video")
def test_run_split_omits_brightness_samples_when_callback_silent(
    mock_probe, mock_split, mock_run_detection, tmp_path
):
    """#644 -- `_run_detection` が callback を呼ばない (例: cache hit 経路と
    同じ意味の no-op detection) 場合は brightness_samples キーを書かない。
    """
    mock_probe.return_value = PROBE_RESULT

    def fake_run_detection(*args, **kwargs):
        # callback を呼ばない (Pass 1 走っていない想定)
        return BOUNDARIES

    mock_run_detection.side_effect = fake_run_detection

    output_dir = tmp_path / "out2"
    mock_split.return_value = [
        output_dir / "match_001.mp4",
        output_dir / "match_002.mp4",
    ]

    video = tmp_path / "input.mp4"
    video.write_bytes(b"")
    config = SplitConfig(output_dir=output_dir, min_match_duration=60.0)

    run_split(video, config, verbose=False, quiet=True)

    metadata_path = output_dir / "metadata.json"
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert "brightness_samples" not in payload, (
        "callback が silent (Pass 1 skip / cache hit 相当) なら "
        "brightness_samples キーは書かないはず"
    )


@patch("allaganeye.system_info.probe_gpu_vendors", return_value=[])
@patch(f"{MODULE}._run_detection")
@patch(f"{MODULE}._load_cache")
@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.probe_video")
def test_run_split_cache_hit_omits_brightness_samples(
    mock_probe,
    mock_split,
    mock_load_cache,
    mock_run_detection,
    mock_probe_gpu,
    tmp_path,
):
    """#644 -- cache hit 経路では Pass 1 が走らず brightness_samples キー
    が metadata.json から欠落する (cache に brightness を含めない設計と整合)。

    run_split: cache hit early-return branch (line 100-146) を直接 exercise し、
    `_run_detection` が呼ばれないこと + metadata.json に key 不在を assert。
    Round 1 F1 (subagent finding): callback_silent test では `_run_detection`
    レベルで mock するため cache hit branch そのものを exercise せず、ここで
    補完する。
    """
    mock_probe.return_value = PROBE_RESULT
    mock_load_cache.return_value = BOUNDARIES  # cache hit -> Pass 1 skip

    output_dir = tmp_path / "out_cache_hit"
    mock_split.return_value = [
        output_dir / "match_001.mp4",
        output_dir / "match_002.mp4",
    ]

    video = tmp_path / "input.mp4"
    video.write_bytes(b"")
    config = SplitConfig(output_dir=output_dir, min_match_duration=60.0)

    run_split(video, config, verbose=False, quiet=True)

    # cache hit branch は _run_detection を skip するはず
    mock_run_detection.assert_not_called()

    metadata_path = output_dir / "metadata.json"
    assert metadata_path.exists()
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert "brightness_samples" not in payload, (
        "cache hit 経路では Pass 1 を skip するため brightness_samples キー"
        "は欠落するはず (#644、metadata-spec.md 書き込みパス表と整合)"
    )
