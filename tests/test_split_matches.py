"""Tests for split_matches pipeline orchestration."""

import json
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    from allaganeye.metadata_types import CaptureRegions

from allaganeye.commands.split_matches import (
    _CACHE_VERSION,
    _ETAProgressBar,
    _MASKED_ALGO_VERSION,
    _PROGRESS_LABEL_WIDTH,
    _VTUBER_ALGO_VERSION,
    _auto_sample_interval,
    _eta_progressbar,
    _format_region_token,
    _load_cache_hit,
    _save_cache,
    run_split,
    CacheHit,
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
        vtuber=True,
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
        "vtuber",
        "masked",
        "masked_fallback_used",
    }
    assert set(params) == expected_keys, (
        f"detection_params keys mismatch: {set(params) ^ expected_keys}"
    )

    # vtuber/masked provenance (PR #823 R1 deferred -> PR (b) で一括): metadata
    # からどの検出 path で生成されたかを判別可能にする。masked は request flag、
    # masked_fallback_used は resolved path (auto-fallback 含む) を表す。
    assert params["vtuber"] is True
    assert params["masked"] is False
    assert params["masked_fallback_used"] is False

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
        keep_trailing=True,
    )

    run_split(Path("input.mp4"), config)

    mock_detect.assert_called_once()
    _, detect_kwargs = mock_detect.call_args
    assert detect_kwargs["sample_interval"] == 2.0
    assert detect_kwargs["blackout_threshold"] == 20.0
    assert detect_kwargs["min_match_duration"] == 120.0
    assert detect_kwargs["min_blackout_duration"] == 3.0
    # #805 段階2: keep_trailing flag still reaches the detector through
    # _run_detection's detect_kwargs assembly. The trailing_drop_callback seam
    # is removed (W1: warning emission stopped, post_match flag replaces it).
    assert detect_kwargs["keep_trailing"] is True
    assert "trailing_drop_callback" not in detect_kwargs


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
        hit = _load_cache_hit(cache_path, cache_video, 1.0, cache_config)
        assert hit is not None
        assert hit.boundaries == CACHE_BOUNDARIES

    def test_size_mismatch(self, cache_video, cache_config, tmp_path):
        """source_size mismatch -> None."""
        cache_path = tmp_path / "output" / ".detection_cache.json"
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, cache_config, CACHE_BOUNDARIES
        )
        # Change file size
        cache_video.write_bytes(b"\x00" * 2048)
        assert _load_cache_hit(cache_path, cache_video, 1.0, cache_config) is None

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
        assert _load_cache_hit(cache_path, cache_video, 1.0, cache_config) is None

    def test_param_mismatch_threshold(self, cache_video, cache_config, tmp_path):
        """blackout_threshold mismatch -> None."""
        cache_path = tmp_path / "output" / ".detection_cache.json"
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, cache_config, CACHE_BOUNDARIES
        )
        different_config = SplitConfig(
            output_dir=tmp_path / "output", blackout_threshold=20.0
        )
        assert _load_cache_hit(cache_path, cache_video, 1.0, different_config) is None

    def test_param_mismatch_interval(self, cache_video, cache_config, tmp_path):
        """sample_interval mismatch -> None."""
        cache_path = tmp_path / "output" / ".detection_cache.json"
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, cache_config, CACHE_BOUNDARIES
        )
        assert _load_cache_hit(cache_path, cache_video, 2.0, cache_config) is None

    def test_param_mismatch_no_audio(self, cache_video, cache_config, tmp_path):
        """no_audio mismatch -> None (cache must be keyed to audio pipeline, #288)."""
        cache_path = tmp_path / "output" / ".detection_cache.json"
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, cache_config, CACHE_BOUNDARIES
        )
        different_config = SplitConfig(output_dir=tmp_path / "output", no_audio=True)
        assert _load_cache_hit(cache_path, cache_video, 1.0, different_config) is None

    def test_param_mismatch_vtuber(self, cache_video, cache_config, tmp_path):
        """標準 run の cache を vtuber run が再利用しない -> None (gate の cache bypass 防止)."""
        cache_path = tmp_path / "output" / ".detection_cache.json"
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, cache_config, CACHE_BOUNDARIES
        )
        vtuber_config = SplitConfig(output_dir=tmp_path / "output", vtuber=True)
        assert _load_cache_hit(cache_path, cache_video, 1.0, vtuber_config) is None

    def test_param_mismatch_vtuber_reverse(self, cache_video, cache_config, tmp_path):
        """vtuber run の cache を標準 run が再利用しない -> None (released path 保護)."""
        cache_path = tmp_path / "output" / ".detection_cache.json"
        vtuber_config = SplitConfig(output_dir=tmp_path / "output", vtuber=True)
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, vtuber_config, CACHE_BOUNDARIES
        )
        assert _load_cache_hit(cache_path, cache_video, 1.0, cache_config) is None

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
        _hit = _load_cache_hit(cache_path, cache_video, 1.0, cache_config)
        assert _hit is not None and _hit.boundaries == CACHE_BOUNDARIES
        vtuber_config = SplitConfig(output_dir=tmp_path / "output", vtuber=True)
        assert _load_cache_hit(cache_path, cache_video, 1.0, vtuber_config) is None

    def test_param_mismatch_masked(self, cache_video, cache_config, tmp_path):
        """標準 run の cache を masked run が再利用しない -> None (vtuber key と同型)."""
        cache_path = tmp_path / "output" / ".detection_cache.json"
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, cache_config, CACHE_BOUNDARIES
        )
        masked_config = SplitConfig(output_dir=tmp_path / "output", masked=True)
        assert _load_cache_hit(cache_path, cache_video, 1.0, masked_config) is None

    def test_param_mismatch_masked_reverse(self, cache_video, cache_config, tmp_path):
        """masked run の cache を標準 run が再利用しない -> None (released path 保護)."""
        cache_path = tmp_path / "output" / ".detection_cache.json"
        masked_config = SplitConfig(output_dir=tmp_path / "output", masked=True)
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, masked_config, CACHE_BOUNDARIES
        )
        assert _load_cache_hit(cache_path, cache_video, 1.0, cache_config) is None

    def test_legacy_cache_without_masked_key(self, cache_video, cache_config, tmp_path):
        """masked key なし legacy cache: 標準 run は有効、masked run は無効。

        --masked 導入前の cache はすべて標準 path の結果なので missing = False と
        同値に扱う (vtuber key と同じ後方互換規約)。
        """
        cache_path = tmp_path / "output" / ".detection_cache.json"
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, cache_config, CACHE_BOUNDARIES
        )
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        data["params"].pop("masked", None)
        cache_path.write_text(json.dumps(data), encoding="utf-8")
        _hit = _load_cache_hit(cache_path, cache_video, 1.0, cache_config)
        assert _hit is not None and _hit.boundaries == CACHE_BOUNDARIES
        masked_config = SplitConfig(output_dir=tmp_path / "output", masked=True)
        assert _load_cache_hit(cache_path, cache_video, 1.0, masked_config) is None

    def test_param_mismatch_keep_trailing(self, cache_video, cache_config, tmp_path):
        """default run の cache を --keep-trailing run が再利用しない -> None。

        keep_trailing は detect_match_boundaries の trailing-drop を skip して
        検出境界を変える (#805 段階1) ので、cache 済み境界 (drop 済み) を
        --keep-trailing run が再利用すると opt-out が silent に効かなくなる。
        vtuber / masked key と同型に cache key へ含める。
        """
        cache_path = tmp_path / "output" / ".detection_cache.json"
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, cache_config, CACHE_BOUNDARIES
        )
        keep_config = SplitConfig(output_dir=tmp_path / "output", keep_trailing=True)
        assert _load_cache_hit(cache_path, cache_video, 1.0, keep_config) is None

    def test_param_mismatch_keep_trailing_reverse(
        self, cache_video, cache_config, tmp_path
    ):
        """--keep-trailing run の cache を default run が再利用しない -> None。

        --keep-trailing cache (drop なし境界) を default path が再利用すると
        #797 の trailing drop が抑止され released-default が regress するため、
        reverse 方向も miss させる (vtuber/masked reverse と同型)。
        """
        cache_path = tmp_path / "output" / ".detection_cache.json"
        keep_config = SplitConfig(output_dir=tmp_path / "output", keep_trailing=True)
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, keep_config, CACHE_BOUNDARIES
        )
        assert _load_cache_hit(cache_path, cache_video, 1.0, cache_config) is None

    def test_keep_trailing_cache_hit(self, cache_video, tmp_path):
        """--keep-trailing 同士は hit する (round-trip)。"""
        cache_path = tmp_path / "output" / ".detection_cache.json"
        keep_config = SplitConfig(output_dir=tmp_path / "output", keep_trailing=True)
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, keep_config, CACHE_BOUNDARIES
        )
        _hit = _load_cache_hit(cache_path, cache_video, 1.0, keep_config)
        assert _hit is not None and _hit.boundaries == CACHE_BOUNDARIES

    def test_legacy_cache_without_keep_trailing_key(
        self, cache_video, cache_config, tmp_path
    ):
        """keep_trailing key なし legacy cache: default run は有効、keep run は無効。

        --keep-trailing 導入前の cache はすべて drop ON (= keep_trailing=False) の
        結果なので missing = False と同値に扱う (vtuber/masked key と同じ後方互換
        規約)。version bump 不要の根拠でもある。
        """
        cache_path = tmp_path / "output" / ".detection_cache.json"
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, cache_config, CACHE_BOUNDARIES
        )
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        data["params"].pop("keep_trailing", None)
        cache_path.write_text(json.dumps(data), encoding="utf-8")
        _hit = _load_cache_hit(cache_path, cache_video, 1.0, cache_config)
        assert _hit is not None and _hit.boundaries == CACHE_BOUNDARIES
        keep_config = SplitConfig(output_dir=tmp_path / "output", keep_trailing=True)
        assert _load_cache_hit(cache_path, cache_video, 1.0, keep_config) is None

    def test_legacy_v2_cache_rejected(self, cache_video, cache_config, tmp_path):
        """pre-#821 (v2) cache は version bump で全面 invalidate (Codex high finding).

        masked auto-fallback (flag なしでも 0-blackout で発火) の導入により
        「missing masked = False = 同一挙動」が成立しなくなった。v2 cache が
        hit し続けると masked 動画の誤結果 (全滅 1-match) が再利用され、新
        detector が永遠に走らないため、version で全面 invalidate する。
        """
        cache_path = tmp_path / "output" / ".detection_cache.json"
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, cache_config, CACHE_BOUNDARIES
        )
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        data["cache_version"] = 2
        for key in ("vtuber", "masked"):
            data["params"].pop(key, None)
        cache_path.write_text(json.dumps(data), encoding="utf-8")
        assert _load_cache_hit(cache_path, cache_video, 1.0, cache_config) is None

    def test_cache_version_is_4(self):
        """#805 段階2: detection output shape changed (post_match flag) -> v4."""
        assert _CACHE_VERSION == 4

    def test_legacy_v3_cache_rejected(self, cache_video, cache_config, tmp_path):
        """#805 段階2: pre-段階2 (v3) cache は version bump で invalidate される.

        旧 detector は post-match trailing を削除済み shape で cache した。新
        detector は post_match flag 付きで残すため、v3 cache が hit し続けると
        削除済み結果 (試合 1 本欠落) が silent に再利用される。version bump で
        確実に miss させ再 detect させる。
        """
        cache_path = tmp_path / "output" / ".detection_cache.json"
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, cache_config, CACHE_BOUNDARIES
        )
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        data["cache_version"] = 3
        cache_path.write_text(json.dumps(data), encoding="utf-8")
        assert _load_cache_hit(cache_path, cache_video, 1.0, cache_config) is None

    def test_version_mismatch(self, cache_video, cache_config, tmp_path):
        """cache_version mismatch -> None."""
        cache_path = tmp_path / "output" / ".detection_cache.json"
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, cache_config, CACHE_BOUNDARIES
        )
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        data["cache_version"] = 999
        cache_path.write_text(json.dumps(data), encoding="utf-8")
        assert _load_cache_hit(cache_path, cache_video, 1.0, cache_config) is None

    def test_path_mismatch(self, cache_video, cache_config, tmp_path):
        """source path mismatch -> None."""
        cache_path = tmp_path / "output" / ".detection_cache.json"
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, cache_config, CACHE_BOUNDARIES
        )
        other_video = tmp_path / "other.mp4"
        other_video.write_bytes(b"\x00" * 1024)
        assert _load_cache_hit(cache_path, other_video, 1.0, cache_config) is None

    def test_file_not_found(self, cache_video, cache_config, tmp_path):
        """Cache file doesn't exist -> None."""
        cache_path = tmp_path / "nonexistent" / ".detection_cache.json"
        assert _load_cache_hit(cache_path, cache_video, 1.0, cache_config) is None

    def test_corrupted_json(self, cache_video, cache_config, tmp_path):
        """Corrupted cache file -> None (no exception)."""
        cache_path = tmp_path / "output" / ".detection_cache.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text("not valid json{{{", encoding="utf-8")
        assert _load_cache_hit(cache_path, cache_video, 1.0, cache_config) is None


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


class TestMaskedAlgoCache:
    """#822: masked_algo cache key -- save/load/legacy OBS backward compat."""

    def test_save_cache_writes_masked_algo(self, cache_video, cache_config, tmp_path):
        """_save_cache always writes masked_algo == _MASKED_ALGO_VERSION."""
        cache_path = tmp_path / "output" / ".detection_cache.json"
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, cache_config, CACHE_BOUNDARIES
        )
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        assert data["params"]["masked_algo"] == _MASKED_ALGO_VERSION

    def test_cache_miss_on_masked_algo_mismatch(self, cache_video, tmp_path):
        """Legacy masked cache (masked_algo absent = 1) misses with new code (3).

        A cache saved by pre-#822 code with masked=True has no masked_algo key
        (defaults to 1). Loading with the current code (_MASKED_ALGO_VERSION=3)
        must return None -- the old masked-path result is stale.
        """
        masked_config = SplitConfig(
            output_dir=tmp_path / "output",
            sample_interval=1.0,
            blackout_threshold=15.0,
            min_match_duration=300.0,
            min_blackout_duration=3.0,
            masked=True,
        )
        cache_path = tmp_path / "output" / ".detection_cache.json"
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, masked_config, CACHE_BOUNDARIES
        )
        # Simulate legacy pre-#822 cache: remove masked_algo from params
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        data["params"].pop("masked_algo", None)
        cache_path.write_text(json.dumps(data), encoding="utf-8")
        # Must miss: masked=True run with old (missing) algo key vs new version
        assert _load_cache_hit(cache_path, cache_video, 1.0, masked_config) is None

    def test_cache_hit_for_legacy_obs_cache_without_masked_algo(
        self, cache_video, cache_config, tmp_path
    ):
        """OBS cache (fallback unused, masked off) hits even without masked_algo.

        Pre-#822 OBS caches have no masked_algo key. Since masked=False and
        masked_fallback_used=False, the run was never masked-affected.
        Legacy key absence == algo 1, and since it is not masked-affected,
        the mismatch check does not fire -- the cache must still hit.
        """
        cache_path = tmp_path / "output" / ".detection_cache.json"
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, cache_config, CACHE_BOUNDARIES
        )
        # Simulate legacy OBS cache: remove masked_algo key
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        data["params"].pop("masked_algo", None)
        # Ensure masked_fallback_used is absent/False (standard OBS run)
        data.pop("masked_fallback_used", None)
        cache_path.write_text(json.dumps(data), encoding="utf-8")
        # Must still hit: unaffected users must not be forced to re-detect
        _hit = _load_cache_hit(cache_path, cache_video, 1.0, cache_config)
        assert _hit is not None and _hit.boundaries == CACHE_BOUNDARIES

    def test_cache_miss_when_fallback_used_and_algo_stale(
        self, cache_video, cache_config, tmp_path
    ):
        """Auto-fallback run (masked=False but masked_fallback_used=True) misses
        when masked_algo key is absent (stale pre-#822 result).

        masked_fallback_used=True means the run took the masked code path
        regardless of the request flag, so the algo change invalidates it.
        """
        cache_path = tmp_path / "output" / ".detection_cache.json"
        # Save a cache that records auto-fallback was used
        _save_cache(
            cache_path,
            cache_video,
            PROBE_RESULT,
            1.0,
            cache_config,
            CACHE_BOUNDARIES,
            masked_fallback_used=True,
        )
        # Simulate legacy pre-#822 cache: remove masked_algo
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        data["params"].pop("masked_algo", None)
        cache_path.write_text(json.dumps(data), encoding="utf-8")
        # Must miss: fallback-used run with stale algo
        assert _load_cache_hit(cache_path, cache_video, 1.0, cache_config) is None

    def test_masked_algo_version_is_3(self):
        """Pin: _MASKED_ALGO_VERSION == 3 for #822 Onsal recalibration (15-probe quorum + zero-gap merge)."""
        assert _MASKED_ALGO_VERSION == 3


class TestVtuberAlgoCache:
    """#895: vtuber_algo cache key -- save/load/legacy OBS backward compat."""

    def test_save_cache_writes_vtuber_algo(self, cache_video, tmp_path):
        """_save_cache always writes vtuber_algo == _VTUBER_ALGO_VERSION."""
        vtuber_config = SplitConfig(
            output_dir=tmp_path / "output",
            sample_interval=1.0,
            blackout_threshold=15.0,
            min_match_duration=300.0,
            min_blackout_duration=3.0,
            vtuber=True,
        )
        cache_path = tmp_path / "output" / ".detection_cache.json"
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, vtuber_config, CACHE_BOUNDARIES
        )
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        assert data["params"]["vtuber_algo"] == _VTUBER_ALGO_VERSION

    def test_cache_miss_on_vtuber_algo_mismatch(self, cache_video, tmp_path):
        """Legacy vtuber cache (vtuber_algo absent = 1) misses with the current version.

        A cache saved by pre-#895 code with vtuber=True has no vtuber_algo key
        (defaults to 1). Loading with the current code (_VTUBER_ALGO_VERSION)
        must return None -- the old band-crop result is stale (timeline path
        was not yet implemented).
        """
        vtuber_config = SplitConfig(
            output_dir=tmp_path / "output",
            sample_interval=1.0,
            blackout_threshold=15.0,
            min_match_duration=300.0,
            min_blackout_duration=3.0,
            vtuber=True,
        )
        cache_path = tmp_path / "output" / ".detection_cache.json"
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, vtuber_config, CACHE_BOUNDARIES
        )
        # Simulate legacy pre-#895 cache: remove vtuber_algo from params
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        data["params"].pop("vtuber_algo", None)
        cache_path.write_text(json.dumps(data), encoding="utf-8")
        # Must miss: vtuber=True run with old (missing) algo key vs new version
        assert _load_cache_hit(cache_path, cache_video, 1.0, vtuber_config) is None

    def test_cache_hit_for_legacy_obs_cache_without_vtuber_algo(
        self, cache_video, cache_config, tmp_path
    ):
        """OBS cache (vtuber off) hits even without vtuber_algo.

        Pre-#895 OBS caches have no vtuber_algo key. Since vtuber=False,
        the run was never vtuber-affected. Legacy key absence == algo 1,
        and since it is not vtuber-affected, the mismatch check does not
        fire -- the cache must still hit (no needless re-detects for
        unaffected users).
        """
        cache_path = tmp_path / "output" / ".detection_cache.json"
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, cache_config, CACHE_BOUNDARIES
        )
        # Simulate legacy OBS cache: remove vtuber_algo key
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        data["params"].pop("vtuber_algo", None)
        cache_path.write_text(json.dumps(data), encoding="utf-8")
        # Must still hit: unaffected users must not be forced to re-detect
        _hit = _load_cache_hit(cache_path, cache_video, 1.0, cache_config)
        assert _hit is not None and _hit.boundaries == CACHE_BOUNDARIES

    def test_load_cache_broken_vtuber_algo_misses(self, cache_video, tmp_path):
        """Broken vtuber_algo (non-int string) in vtuber cache causes miss.

        When a vtuber-affected cache has a non-int vtuber_algo value the
        invalidation logic must treat it as a mismatch (miss direction) rather
        than raising or hitting incorrectly.
        """
        vtuber_config = SplitConfig(
            output_dir=tmp_path / "output",
            sample_interval=1.0,
            blackout_threshold=15.0,
            min_match_duration=300.0,
            min_blackout_duration=3.0,
            vtuber=True,
        )
        cache_path = tmp_path / "output" / ".detection_cache.json"
        _save_cache(
            cache_path, cache_video, PROBE_RESULT, 1.0, vtuber_config, CACHE_BOUNDARIES
        )
        # Inject a non-int vtuber_algo to simulate cache corruption
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        data["params"]["vtuber_algo"] = "x"
        cache_path.write_text(json.dumps(data), encoding="utf-8")

        result = _load_cache_hit(cache_path, cache_video, 1.0, vtuber_config)
        assert result is None, "broken vtuber_algo must cause cache miss, not hit"

    def test_vtuber_algo_version_is_3(self):
        """Pin: _VTUBER_ALGO_VERSION == 3 for #895 V3/V4 timeline integration."""
        assert _VTUBER_ALGO_VERSION == 3


def test_print_detection_stats_vtuber_timeline_section(capsys):
    """timeline stats keys present -> vtuber section shown (OBS no-impact pin)."""
    from allaganeye.commands.split_matches import _print_detection_stats

    _print_detection_stats(
        {
            "vtuber_timeline_probes": 1449,
            "vtuber_anchor_confidence": 0.589,
            "vtuber_gaps_tested": 8,
            "vtuber_gaps_merged": 4,
            "vtuber_v4_dropped": 0,
            "vtuber_low_confidence_segments": 0,
        }
    )
    out = capsys.readouterr().out
    assert "Timeline (vtuber): 1449 probes" in out
    assert "anchor conf 0.59" in out
    assert "8 gaps tested, 4 merged" in out
    assert "V4: 0 dropped, 0 low-confidence" in out


def test_print_detection_stats_vtuber_timeline_section_obs_no_impact(capsys):
    """OBS stats (vtuber key absent) must not emit the timeline section."""
    from allaganeye.commands.split_matches import _print_detection_stats

    _print_detection_stats(
        {"mode": "cpu", "pass1_samples": 0, "pass1_blackout_frames": 0}
    )
    out = capsys.readouterr().out
    assert "Timeline (vtuber)" not in out


class TestCaptureRegionsCache:
    """#810: capture_regions の cache 保存 / 引継 / legacy 合成。"""

    def _write_cache(self, cache_path, video_path, *, extra=None, params_extra=None):
        # 既存 cache fixture (cache_video / cache_config) 群のヘルパに合わせて、
        # _save_cache を直接使わず生 JSON を書いて legacy 形を再現する
        import json

        stat = video_path.resolve().stat()
        from allaganeye.commands.split_matches import _CACHE_VERSION

        data = {
            "cache_version": _CACHE_VERSION,
            "source": str(video_path.resolve()),
            "source_size": stat.st_size,
            "source_mtime": stat.st_mtime,
            "probe": {
                "duration": 100.0,
                "width": 1920,
                "height": 1080,
                "fps": 60.0,
                "codec": "h264",
            },
            "params": {
                "sample_interval": 2.0,
                "blackout_threshold": 15.0,
                "min_match_duration": 300.0,
                "min_blackout_duration": 3.0,
                "no_audio": False,
                "vtuber": False,
                "masked": False,
                "keep_trailing": False,
                **(params_extra or {}),
            },
            "masked_fallback_used": False,
            "boundaries": [{"start": 10.0, "end": 50.0, "type": "fl_match"}],
            **(extra or {}),
        }
        cache_path.write_text(json.dumps(data), encoding="utf-8")

    def test_save_cache_records_capture_regions(self, cache_video, tmp_path):
        from typing import cast as _cast

        from allaganeye.commands.split_matches import _save_cache
        from allaganeye.metadata_types import CaptureRegions
        import json

        cache_path = tmp_path / ".detection_cache.json"
        regions = _cast(
            CaptureRegions,
            {
                "coarse": {
                    "x": 0.0,
                    "y": 0.0,
                    "w": 1.0,
                    "h": 1.0,
                    "confidence": 1.0,
                    "source": "fallback",
                },
                "segments": [],
                "fallback_reason": None,
            },
        )
        _save_cache(
            cache_path,
            cache_video,
            {
                "duration": 100.0,
                "width": 1920,
                "height": 1080,
                "fps": 60.0,
                "fps_num": 60,
                "fps_den": 1,
                "codec": "h264",
                "audio_codec": "aac",
            },
            2.0,
            SplitConfig(output_dir=tmp_path),
            [{"start": 10.0, "end": 50.0, "type": "fl_match"}],
            capture_regions=regions,
        )
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        assert data["capture_regions"] == regions

    def test_save_cache_omits_capture_regions_when_none(self, cache_video, tmp_path):
        from allaganeye.commands.split_matches import _save_cache
        import json

        cache_path = tmp_path / ".detection_cache.json"
        _save_cache(
            cache_path,
            cache_video,
            {
                "duration": 100.0,
                "width": 1920,
                "height": 1080,
                "fps": 60.0,
                "fps_num": 60,
                "fps_den": 1,
                "codec": "h264",
                "audio_codec": "aac",
            },
            2.0,
            SplitConfig(output_dir=tmp_path),
            [{"start": 10.0, "end": 50.0, "type": "fl_match"}],
            capture_regions=None,
        )
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        # #810: None は key 省略 (null を書かない) -- metadata.json と同じ省略 semantics
        assert "capture_regions" not in data

    def test_read_cached_capture_regions_returns_recorded(self, cache_video, tmp_path):
        from allaganeye.commands.split_matches import _capture_regions_from_cache_data

        cache_path = tmp_path / ".detection_cache.json"
        regions = {
            "coarse": {
                "x": 0.1,
                "y": 0.0,
                "w": 0.76,
                "h": 0.042,
                "confidence": 0.9,
                "source": "band",
            },
            "segments": [],
            "fallback_reason": None,
        }
        self._write_cache(cache_path, cache_video, extra={"capture_regions": regions})
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        assert _capture_regions_from_cache_data(data) == regions

    def test_read_cached_capture_regions_legacy_standard_synthesizes_full_frame(
        self, cache_video, tmp_path
    ):
        # pre-#810 cache + 標準 path (vtuber=False / masked_fallback_used=False)
        # は FULL_FRAME 確定なので合成する
        from allaganeye.commands.split_matches import _capture_regions_from_cache_data

        cache_path = tmp_path / ".detection_cache.json"
        self._write_cache(cache_path, cache_video)
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        regions = _capture_regions_from_cache_data(data)
        assert regions is not None
        assert regions["coarse"]["source"] == "fallback"
        assert regions["coarse"]["x"] == 0.0 and regions["coarse"]["w"] == 1.0
        assert regions["fallback_reason"] is None

    def test_read_cached_capture_regions_legacy_vtuber_returns_none(
        self, cache_video, tmp_path
    ):
        # pre-#810 vtuber cache は band 領域が未知 -> 合成せず None (field 省略)
        from allaganeye.commands.split_matches import _capture_regions_from_cache_data

        cache_path = tmp_path / ".detection_cache.json"
        self._write_cache(cache_path, cache_video, params_extra={"vtuber": True})
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        assert _capture_regions_from_cache_data(data) is None

    def test_read_cached_capture_regions_legacy_masked_returns_none(
        self, cache_video, tmp_path
    ):
        from allaganeye.commands.split_matches import _capture_regions_from_cache_data

        cache_path = tmp_path / ".detection_cache.json"
        self._write_cache(cache_path, cache_video, extra={"masked_fallback_used": True})
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        assert _capture_regions_from_cache_data(data) is None

    def test_read_cached_capture_regions_masked_requested_but_declined_synthesizes(
        self, cache_video, tmp_path
    ):
        """round-2 codex 裁定 pin: masked=True (request) でも fallback 不採用
        (masked_fallback_used=False) なら標準 path が FULL_FRAME で Pass 1 計測
        しているため、FULL_FRAME 合成が意図した挙動。判定述語は resolved flag
        であり request flag ではない (params.masked を除外条件に加えない)。"""
        from allaganeye.commands.split_matches import _capture_regions_from_cache_data

        cache_path = tmp_path / ".detection_cache.json"
        self._write_cache(cache_path, cache_video, params_extra={"masked": True})
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        regions = _capture_regions_from_cache_data(data)
        assert regions is not None
        assert regions["coarse"]["source"] == "fallback"
        assert regions["coarse"]["x"] == 0.0 and regions["coarse"]["w"] == 1.0
        assert regions["fallback_reason"] is None

    def test_read_cached_capture_regions_unreadable_returns_none(
        self, cache_video, cache_config, tmp_path
    ):
        # IO エラー時の None は _load_cache_hit 経由で担保される (#879)
        cache_path = tmp_path / "missing_dir" / ".detection_cache.json"
        assert _load_cache_hit(cache_path, cache_video, 2.0, cache_config) is None

    def test_read_cached_capture_regions_nan_time_range_returns_none(
        self, cache_video, tmp_path
    ):
        """round-3 R3-1: NaN 混入 cache 値は sanitize で drop され、非標準 JSON
        token が metadata.json へ再 emit されない (合成 fall-through もしない)。"""
        from allaganeye.commands.split_matches import _capture_regions_from_cache_data

        cache_path = tmp_path / ".detection_cache.json"
        nan_regions = {
            "coarse": {
                "x": 0.1,
                "y": 0.0,
                "w": 0.76,
                "h": 0.042,
                "confidence": 0.9,
                "source": "band",
            },
            "segments": [
                {
                    "time_range": [0.0, float("nan")],
                    "region": {
                        "x": 0.1,
                        "y": 0.0,
                        "w": 0.76,
                        "h": 0.042,
                        "confidence": 0.9,
                        "source": "band",
                    },
                }
            ],
            "fallback_reason": None,
        }
        self._write_cache(
            cache_path, cache_video, extra={"capture_regions": nan_regions}
        )
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        assert _capture_regions_from_cache_data(data) is None

    def test_read_cached_capture_regions_malformed_returns_none_not_synthesized(
        self, cache_video, tmp_path
    ):
        """codex F1 -- cache read sanitize: malformed present value -> None (not FULL_FRAME).

        cache に capture_regions が present だが malformed (coarse に "confidence" 欠落)。
        sanitize で invalid -> None を返す。
        vtuber=False / masked_fallback_used=False でも FULL_FRAME 合成に fall through しない
        (present-but-garbage は "領域不明" であり、legacy 不在 = 標準 path 確定 とは異なる)。
        """
        from allaganeye.commands.split_matches import _capture_regions_from_cache_data

        cache_path = tmp_path / ".detection_cache.json"
        malformed_regions = {
            "coarse": {
                "x": 0.0,
                "y": 0.0,
                "w": 1.0,
                "h": 1.0,
                # "confidence" key missing -> invalid CaptureRegion
                "source": "fallback",
            },
            "segments": [],
            "fallback_reason": None,
        }
        self._write_cache(
            cache_path, cache_video, extra={"capture_regions": malformed_regions}
        )
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        result = _capture_regions_from_cache_data(data)
        assert result is None, (
            "present but malformed capture_regions (missing confidence) must return "
            "None -- must NOT synthesize FULL_FRAME"
        )

    def test_read_cached_capture_regions_null_value_treated_as_absent(
        self, cache_video, tmp_path
    ):
        """codex F1 -- cache read: explicit null is treated same as absent key (legacy compat).

        pre-fix builds wrote `"capture_regions": null` when the value was None.
        null should be treated as absent (key missing), triggering legacy synthesis
        for standard path (vtuber=False, masked_fallback_used=False) -> FULL_FRAME.
        This pins the null-tolerance so future refactors don't break legacy caches.
        """

        from allaganeye.commands.split_matches import _capture_regions_from_cache_data

        data = {
            "params": {
                "vtuber": False,
                "masked": False,
            },
            "masked_fallback_used": False,
            "capture_regions": None,  # explicit null -- legacy pre-fix behavior
        }

        result = _capture_regions_from_cache_data(data)
        # explicit null treated as absent -> standard path -> FULL_FRAME synthesized
        assert result is not None, (
            "explicit null capture_regions should be treated as absent, "
            "triggering FULL_FRAME synthesis for standard path"
        )
        assert result["coarse"]["source"] == "fallback"
        assert result["coarse"]["x"] == 0.0 and result["coarse"]["w"] == 1.0


# -- Direct unit tests for _sanitize_capture_regions --


class TestSanitizeCaptureRegions:
    """Unit tests for the new _sanitize_capture_regions helper (codex F1)."""

    def _valid_region(self) -> dict:
        return {
            "x": 0.1,
            "y": 0.0,
            "w": 0.76,
            "h": 0.042,
            "confidence": 0.9,
            "source": "band",
        }

    def _valid_regions(self) -> dict:
        return {
            "coarse": self._valid_region(),
            "segments": [],
            "fallback_reason": None,
        }

    def test_valid_full_shape_returns_as_is(self):
        from allaganeye.commands.split_matches import _sanitize_capture_regions

        regions = {
            "coarse": self._valid_region(),
            "segments": [
                {
                    "time_range": [0.0, 10.0],
                    "region": self._valid_region(),
                }
            ],
            "fallback_reason": "consensus_miss",
        }
        result = _sanitize_capture_regions(regions)
        assert result == regions

    def test_valid_minimal_returns_as_is(self):
        from allaganeye.commands.split_matches import _sanitize_capture_regions

        regions = self._valid_regions()
        result = _sanitize_capture_regions(regions)
        assert result == regions

    def test_bool_coordinate_returns_none(self):
        """bool is a subtype of int but must be rejected explicitly."""
        from allaganeye.commands.split_matches import _sanitize_capture_regions

        regions = self._valid_regions()
        regions["coarse"]["x"] = True  # bool must be rejected
        assert _sanitize_capture_regions(regions) is None

    def test_negative_confidence_returns_none(self):
        from allaganeye.commands.split_matches import _sanitize_capture_regions

        regions = self._valid_regions()
        regions["coarse"]["confidence"] = -0.1
        assert _sanitize_capture_regions(regions) is None

    def test_confidence_above_one_returns_none(self):
        from allaganeye.commands.split_matches import _sanitize_capture_regions

        regions = self._valid_regions()
        regions["coarse"]["confidence"] = 1.5
        assert _sanitize_capture_regions(regions) is None

    def test_empty_source_returns_none(self):
        from allaganeye.commands.split_matches import _sanitize_capture_regions

        regions = self._valid_regions()
        regions["coarse"]["source"] = ""
        assert _sanitize_capture_regions(regions) is None

    def test_time_range_of_length_one_returns_none(self):
        from allaganeye.commands.split_matches import _sanitize_capture_regions

        regions = {
            "coarse": self._valid_region(),
            "segments": [
                {
                    "time_range": [0.0],  # must be exactly 2 elements
                    "region": self._valid_region(),
                }
            ],
            "fallback_reason": None,
        }
        assert _sanitize_capture_regions(regions) is None

    @pytest.mark.parametrize(
        "bad_value",
        [float("nan"), float("inf"), float("-inf")],
        ids=["nan", "inf", "neg_inf"],
    )
    def test_time_range_non_finite_returns_none(self, bad_value):
        """round-3 R3-1: NaN / +-Infinity は json.dumps (allow_nan=True) が
        非標準 token を再 emit し strict reader (GUI serde_json / JSON.parse) が
        metadata.json 全体を reject するため、sanitize 側で reject する。
        (t < 0 比較は NaN で False になり素通りしていた regression の pin)"""
        from allaganeye.commands.split_matches import _sanitize_capture_regions

        regions = {
            "coarse": self._valid_region(),
            "segments": [
                {
                    "time_range": [0.0, bad_value],
                    "region": self._valid_region(),
                }
            ],
            "fallback_reason": None,
        }
        assert _sanitize_capture_regions(regions) is None

    def test_fallback_reason_non_str_non_none_returns_none(self):
        """fallback_reason must be str or None; e.g. int 1 is invalid."""
        from allaganeye.commands.split_matches import _sanitize_capture_regions

        regions = self._valid_regions()
        regions["fallback_reason"] = 1  # invalid -- must be str or None
        assert _sanitize_capture_regions(regions) is None

    def test_missing_top_level_key_returns_none(self):
        from allaganeye.commands.split_matches import _sanitize_capture_regions

        regions = self._valid_regions()
        del regions["fallback_reason"]
        assert _sanitize_capture_regions(regions) is None

    def test_extra_top_level_key_returns_none(self):
        from allaganeye.commands.split_matches import _sanitize_capture_regions

        regions = self._valid_regions()
        regions["extra_field"] = "unexpected"
        assert _sanitize_capture_regions(regions) is None

    def test_non_dict_returns_none(self):
        from allaganeye.commands.split_matches import _sanitize_capture_regions

        assert _sanitize_capture_regions("not a dict") is None
        assert _sanitize_capture_regions(None) is None
        assert _sanitize_capture_regions(42) is None


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
    @patch(f"{MODULE}._load_cache_hit")
    def test_cached_path_enforces_disk_check(
        self, mock_load, mock_probe, mock_detect, mock_split, tmp_path
    ):
        """Disk space check runs even when boundaries come from cache (#338).

        The cached re-run is the primary recovery path from an earlier
        disk-full failure; the check must re-validate that enough space
        is available before splitting.
        """
        mock_probe.return_value = PROBE_RESULT
        mock_load.return_value = CacheHit(
            boundaries=BOUNDARIES, masked_fallback_used=False, capture_regions=None
        )  # simulate cache hit
        mock_split.return_value = _output_files(tmp_path)
        config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

        with patch(f"{MODULE}._check_disk_space") as mock_check:
            run_split(Path("input.mp4"), config)

        mock_check.assert_called_once()
        # detect_match_boundaries must not be invoked (cache hit)
        mock_detect.assert_not_called()


class TestPartitionPostMatch:
    """`_partition_post_match` helper (#805 段階2)."""

    def test_partition_splits_active_and_post_match(self):
        """active (no post_match flag) and post_match are separated."""
        from allaganeye.commands.split_matches import _partition_post_match

        boundaries: list[MatchBoundary] = [
            {"start": 0.0, "end": 600.0, "type": "unknown"},
            {"start": 610.0, "end": 1200.0, "type": "unknown", "post_match": True},
        ]
        active, post_match = _partition_post_match(boundaries)

        assert active == [{"start": 0.0, "end": 600.0, "type": "unknown"}]
        assert post_match == [
            {"start": 610.0, "end": 1200.0, "type": "unknown", "post_match": True}
        ]

    def test_partition_is_order_preserving_and_total(self):
        """The two lists partition the input and preserve relative order."""
        from allaganeye.commands.split_matches import _partition_post_match

        boundaries: list[MatchBoundary] = [
            {"start": 0.0, "end": 100.0, "type": "unknown"},
            {"start": 200.0, "end": 300.0, "type": "unknown", "post_match": True},
            {"start": 400.0, "end": 500.0, "type": "unknown"},
            {"start": 600.0, "end": 700.0, "type": "unknown", "post_match": True},
        ]
        active, post_match = _partition_post_match(boundaries)

        # Order-preserving within each partition
        assert active == [
            {"start": 0.0, "end": 100.0, "type": "unknown"},
            {"start": 400.0, "end": 500.0, "type": "unknown"},
        ]
        assert post_match == [
            {"start": 200.0, "end": 300.0, "type": "unknown", "post_match": True},
            {"start": 600.0, "end": 700.0, "type": "unknown", "post_match": True},
        ]
        # Total: the two lists account for every input boundary
        assert len(active) + len(post_match) == len(boundaries)

    def test_partition_no_post_match_returns_all_active(self):
        """No post_match flag -> active is the full list (bit-exact), post empty."""
        from allaganeye.commands.split_matches import _partition_post_match

        active, post_match = _partition_post_match(BOUNDARIES)

        assert active == BOUNDARIES
        assert post_match == []

    def test_partition_empty(self):
        """Empty input -> two empty lists."""
        from allaganeye.commands.split_matches import _partition_post_match

        active, post_match = _partition_post_match([])

        assert active == []
        assert post_match == []

    def test_partition_post_match_false_is_active(self):
        """An explicit ``post_match: False`` boundary counts as active."""
        from allaganeye.commands.split_matches import _partition_post_match

        boundaries: list[MatchBoundary] = [
            {"start": 0.0, "end": 100.0, "type": "unknown", "post_match": False},
        ]
        active, post_match = _partition_post_match(boundaries)

        assert active == boundaries
        assert post_match == []


# Disk-budget regression fixtures (#805 段階2).
# Source: 1.8 MB / 1800 s (matches PROBE_RESULT["duration"]).
#   active  = 0-600s   -> ratio 1/3   -> est = 1.8M * (1/3) * 1.1 = 660_000
#   all     = 0-1700s  -> ratio 17/18 -> est = 1.8M * (17/18)*1.1 = 1_870_000
# free = 1_000_000:  est(active) <= free < est(active+post_match).
_ACTIVE_AND_POST: list[MatchBoundary] = [
    {"start": 0.0, "end": 600.0, "type": "unknown"},
    {"start": 600.0, "end": 1700.0, "type": "unknown", "post_match": True},
]
_POST_MATCH_FREE_BYTES = 1_000_000


def _post_match_fake_usage():
    return type(
        "Usage",
        (),
        {
            "total": 10_000_000,
            "used": 10_000_000 - _POST_MATCH_FREE_BYTES,
            "free": _POST_MATCH_FREE_BYTES,
        },
    )


class TestDiskSpacePostMatchBudget:
    """Disk check must budget only active (MP4-written) boundaries (#805 段階2).

    Regression for the Codex adversarial-review HIGH finding: a long
    post_match trailing segment is retained in ``boundaries`` but is *not*
    written to MP4.  Budgeting its duration in the pre-split disk check can
    raise a false "Not enough disk space" error even though the space free
    is sufficient for the matches that will actually be written.
    """

    @patch(f"{MODULE}.split_video")
    @patch(f"{MODULE}.detect_match_boundaries")
    @patch(f"{MODULE}.probe_video")
    def test_run_split_does_not_false_fail_on_post_match_tail(
        self, mock_probe, mock_detect, mock_split, tmp_path
    ):
        """run_split must not raise when only the post_match tail overflows."""
        mock_probe.return_value = PROBE_RESULT
        mock_detect.return_value = list(_ACTIVE_AND_POST)
        # Only the single active match is written.
        mock_split.return_value = [tmp_path / "match_001.mp4"]
        config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

        # Real _check_disk_space; mock the OS free-space probe.
        video = tmp_path / "input.mp4"
        video.write_bytes(b"\x00" * 1_800_000)  # 1.8 MB

        with patch(
            "allaganeye.commands.split_matches.shutil.disk_usage",
            return_value=_post_match_fake_usage(),
        ):
            # Must NOT raise: active estimate (660_000) fits in free (1_000_000).
            run_split(video, config)

        mock_split.assert_called_once()

    @patch(f"{MODULE}.split_video")
    @patch(f"{MODULE}.detect_match_boundaries")
    @patch(f"{MODULE}.probe_video")
    def test_run_split_passes_only_active_boundaries_to_disk_check(
        self, mock_probe, mock_detect, mock_split, tmp_path
    ):
        """The disk check is called with active boundaries only (not post_match)."""
        mock_probe.return_value = PROBE_RESULT
        mock_detect.return_value = list(_ACTIVE_AND_POST)
        mock_split.return_value = [tmp_path / "match_001.mp4"]
        config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

        with patch(f"{MODULE}._check_disk_space") as mock_check:
            run_split(Path("input.mp4"), config)

        mock_check.assert_called_once()
        passed_boundaries = mock_check.call_args.args[1]
        assert passed_boundaries == [
            {"start": 0.0, "end": 600.0, "type": "unknown"},
        ]
        assert all(not b.get("post_match") for b in passed_boundaries)

    @patch(f"{MODULE}.split_video")
    @patch(f"{MODULE}.detect_match_boundaries")
    @patch(f"{MODULE}.probe_video")
    @patch(f"{MODULE}._load_cache_hit")
    def test_cache_hit_does_not_false_fail_on_post_match_tail(
        self, mock_load, mock_probe, mock_detect, mock_split, tmp_path
    ):
        """cache-hit branch must also budget only active boundaries (#805).

        The v4 cache stores the post_match=True shape, and the cache-hit
        re-run is the documented recovery path from a disk-full failure, so
        the cache branch's disk check must exclude the post_match tail too.
        """
        mock_probe.return_value = PROBE_RESULT
        # Cache returns boundaries WITH a post_match tail.
        mock_load.return_value = CacheHit(
            boundaries=list(_ACTIVE_AND_POST),
            masked_fallback_used=False,
            capture_regions=None,
        )
        mock_split.return_value = [tmp_path / "match_001.mp4"]
        config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

        video = tmp_path / "input.mp4"
        video.write_bytes(b"\x00" * 1_800_000)  # 1.8 MB

        with patch(
            "allaganeye.commands.split_matches.shutil.disk_usage",
            return_value=_post_match_fake_usage(),
        ):
            run_split(video, config)

        # cache hit -> detect must not run; split happens for the active match.
        mock_detect.assert_not_called()
        mock_split.assert_called_once()


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
def test_verbose_masked_l2_drop_line_shown_when_nonzero(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """masked_segments_dropped > 0 -> verbose emits 'masked L2 validation' line (#822)."""
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
            stats["masked_segments_dropped"] = 2
        return BOUNDARIES

    mock_detect.side_effect = populate_stats
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config, verbose=True)
    out = capsys.readouterr().out

    assert "masked L2 validation: 2 segment(s) dropped" in out


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_verbose_masked_l2_drop_line_hidden_when_zero(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """masked_segments_dropped == 0 -> no masked L2 line (terse output, #822)."""
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
            stats["masked_segments_dropped"] = 0
        return BOUNDARIES

    mock_detect.side_effect = populate_stats
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config, verbose=True)
    out = capsys.readouterr().out

    assert "masked L2" not in out


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_verbose_masked_l2_zero_gap_merge_line_shown_when_nonzero(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """masked_l2_zero_gap_merges > 0 -> verbose emits 'masked L2 zero-gap merge' line (#822)."""
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
            stats["masked_l2_zero_gap_merges"] = 1
        return BOUNDARIES

    mock_detect.side_effect = populate_stats
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config, verbose=True)
    out = capsys.readouterr().out

    assert "masked L2 zero-gap merge: 1 pair(s) merged" in out


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.detect_match_boundaries")
@patch(f"{MODULE}.probe_video")
def test_verbose_masked_l2_zero_gap_merge_line_hidden_when_zero(
    mock_probe, mock_detect, mock_split, tmp_path, capsys
):
    """masked_l2_zero_gap_merges == 0 -> no zero-gap merge line in verbose output."""
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
            stats["masked_l2_zero_gap_merges"] = 0
        return BOUNDARIES

    mock_detect.side_effect = populate_stats
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    run_split(Path("input.mp4"), config, verbose=True)
    out = capsys.readouterr().out

    assert "zero-gap merge" not in out


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


def _seed_cache(
    source: Path,
    output_dir: Path,
    config: SplitConfig,
    *,
    capture_regions: dict | None = None,
) -> None:
    """Write a .detection_cache.json entry matching ``config`` so ``_load_cache``
    hits.  Helper for cache-hit tests (#381; capture_regions は #810 round-1)."""
    source.write_bytes(b"")
    output_dir.mkdir(parents=True, exist_ok=True)
    _save_cache(
        output_dir / ".detection_cache.json",
        source,
        PROBE_RESULT,
        config.sample_interval,
        config,
        BOUNDARIES,
        # malformed 値を意図的に seed するテスト (round-1 #1 pin) があるため
        # CaptureRegions に cast して writer の型契約を素通しする。
        capture_regions=cast("CaptureRegions | None", capture_regions),
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
    # vtuber/masked provenance token (PR #823 R1 / PR (b)): 検出 mode を表示に含める。
    assert "vtuber=off" in out
    assert "masked=off" in out


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


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.probe_video")
def test_verbose_cache_hit_prints_masked_on_token(
    mock_probe, mock_split, tmp_path, capsys
):
    """masked=True で生成した cache の hit 表示は masked=on (vtuber token と同型)."""
    source = tmp_path / "input.mp4"
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0, masked=True)
    _seed_cache(source, tmp_path, config)

    mock_probe.return_value = PROBE_RESULT
    mock_split.return_value = _output_files(tmp_path)

    run_split(source, config, verbose=True)
    out = capsys.readouterr().out

    header_idx = out.find("Cache hit:")
    assert header_idx >= 0
    assert "masked=on" in out[header_idx:]


class TestFormatRegionToken:
    """#810 round-1: verbose region token の tolerant contract を pin する。

    cache-hit 表示は raw cache 記録値 (無検証) を受けるため、malformed 入力でも
    crash せず "invalid" / "unknown" を返す契約。
    """

    def _regions(self, **coarse_overrides) -> dict:
        coarse = {
            "x": 0.0,
            "y": 0.0,
            "w": 1.0,
            "h": 1.0,
            "confidence": 1.0,
            "source": "fallback",
        }
        coarse.update(coarse_overrides)
        return {"coarse": coarse, "segments": [], "fallback_reason": None}

    def test_none_returns_unknown(self):
        assert _format_region_token(None) == "unknown"

    def test_non_dict_returns_unknown(self):
        assert _format_region_token("garbage") == "unknown"

    def test_missing_coarse_returns_unknown(self):
        assert _format_region_token({"segments": []}) == "unknown"

    def test_full_frame(self):
        assert _format_region_token(self._regions()) == "full_frame"

    def test_band_coordinates_formatted(self):
        regions = self._regions(
            x=0.1, y=0.0, w=0.76, h=0.042, confidence=0.9, source="band"
        )
        assert _format_region_token(regions) == "band(0.10,0.00,0.76,0.04)"

    def test_fallback_reason_suffix(self):
        regions = self._regions()
        regions["fallback_reason"] = "consensus_miss"
        assert _format_region_token(regions) == "full_frame, fallback=consensus_miss"

    def test_malformed_non_numeric_coordinate_returns_invalid(self):
        # round-1 #1: 非数値座標で :.2f が ValueError にならないこと (crash 防御)
        regions = self._regions(x="oops", source="band")
        assert _format_region_token(regions) == "invalid"

    def test_bool_coordinate_returns_invalid(self):
        regions = self._regions(x=True, source="band")
        assert _format_region_token(regions) == "invalid"

    def test_ansi_escape_in_source_is_neutralized(self):
        # round-3 R3-4: 改竄 cache 由来の制御文字を端末に素通ししない
        regions = self._regions(source="\x1b[31mevil\x1b[0m")
        token = _format_region_token(regions)
        assert "\x1b" not in token
        assert "evil" in token

    def test_overlong_source_is_capped(self):
        regions = self._regions(source="s" * 500)
        token = _format_region_token(regions)
        assert len(token) < 100

    def test_ansi_escape_in_fallback_reason_is_neutralized(self):
        regions = self._regions()
        regions["fallback_reason"] = "\x1b]0;pwn\x07"
        token = _format_region_token(regions)
        assert "\x1b" not in token
        assert "\x07" not in token


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.probe_video")
def test_verbose_cache_hit_prints_region_token(
    mock_probe, mock_split, tmp_path, capsys
):
    """cache-hit params 行に region= token が出る (#810 round-1 #2 表示 pin)."""
    source = tmp_path / "input.mp4"
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    band_regions = {
        "coarse": {
            "x": 0.1,
            "y": 0.0,
            "w": 0.76,
            "h": 0.042,
            "confidence": 0.9,
            "source": "band",
        },
        "segments": [],
        "fallback_reason": None,
    }
    _seed_cache(source, tmp_path, config, capture_regions=band_regions)

    mock_probe.return_value = PROBE_RESULT
    mock_split.return_value = _output_files(tmp_path)

    run_split(source, config, verbose=True)
    out = capsys.readouterr().out

    header_idx = out.find("Cache hit:")
    assert header_idx >= 0
    assert "region=band(0.10,0.00,0.76,0.04)" in out[header_idx:]


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.probe_video")
def test_verbose_cache_hit_malformed_region_does_not_crash(
    mock_probe, mock_split, tmp_path, capsys
):
    """malformed cached capture_regions で cache-hit verbose が crash しない
    (#810 round-1 #1 regression pin)。

    表示は raw cache 記録値を正とする設計のため、formatter が tolerant に
    "invalid" を出して run は正常続行する (metadata 側は sanitize 済みで省略)。
    """
    source = tmp_path / "input.mp4"
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    malformed = {
        "coarse": {
            "x": "oops",
            "y": 0.0,
            "w": 0.5,
            "h": 0.5,
            "confidence": 0.9,
            "source": "band",
        },
        "segments": [],
        "fallback_reason": None,
    }
    _seed_cache(source, tmp_path, config, capture_regions=malformed)

    mock_probe.return_value = PROBE_RESULT
    mock_split.return_value = _output_files(tmp_path)

    run_split(source, config, verbose=True)  # must not raise
    out = capsys.readouterr().out

    header_idx = out.find("Cache hit:")
    assert header_idx >= 0
    assert "region=invalid" in out[header_idx:]


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.probe_video")
def test_verbose_cache_hit_prints_keep_trailing_on_token(
    mock_probe, mock_split, tmp_path, capsys
):
    """keep_trailing=True で生成した cache の hit 表示は keep_trailing=on。

    cache key fix (#805 段階1) で mode 混在 hit は不可能になったが、表示にも
    provenance を出して troubleshoot 報告から keep_trailing を判別可能にする
    (vtuber/masked token と同型)。
    """
    source = tmp_path / "input.mp4"
    config = SplitConfig(
        output_dir=tmp_path, min_match_duration=60.0, keep_trailing=True
    )
    _seed_cache(source, tmp_path, config)

    mock_probe.return_value = PROBE_RESULT
    mock_split.return_value = _output_files(tmp_path)

    run_split(source, config, verbose=True)
    out = capsys.readouterr().out

    header_idx = out.find("Cache hit:")
    assert header_idx >= 0
    assert "keep_trailing=on" in out[header_idx:]


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


@patch(f"{MODULE}._run_detection")
@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.probe_video")
def test_verbose_cache_miss_summary_includes_masked_token(
    mock_probe, mock_split, mock_run_detection, tmp_path, capsys
):
    """cache-miss の Detecting summary に masked token が出る (vtuber と同型)."""
    source = tmp_path / "input.mp4"
    source.write_bytes(b"")
    mock_probe.return_value = PROBE_RESULT
    mock_split.return_value = _output_files(tmp_path)
    mock_run_detection.return_value = BOUNDARIES

    config = SplitConfig(output_dir=tmp_path, no_cache=True, masked=True)
    run_split(source, config, verbose=True)
    assert "masked=on" in capsys.readouterr().out

    config_off = SplitConfig(output_dir=tmp_path, no_cache=True)
    run_split(source, config_off, verbose=True)
    assert "masked=off" in capsys.readouterr().out


@patch(f"{MODULE}._run_detection")
@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.probe_video")
def test_run_split_records_masked_fallback_used(
    mock_probe, mock_split, mock_run_detection, tmp_path
):
    """auto masked fallback の resolved path が metadata と cache に記録される.

    Codex medium finding: gate は flag なしでも 0-blackout で fallback に入る
    ため、request flag (masked) と resolved path (masked_fallback_used) を
    分離して記録する。callback 配線は brightness_callback (#644) と同型。
    """
    source = tmp_path / "input.mp4"
    source.write_bytes(b"")
    mock_probe.return_value = PROBE_RESULT
    mock_split.return_value = _output_files(tmp_path)

    def fake_run_detection(*args, **kwargs):
        cb = kwargs.get("masked_fallback_callback")
        assert cb is not None, (
            "run_split must pass masked_fallback_callback to _run_detection"
        )
        cb()
        return BOUNDARIES

    mock_run_detection.side_effect = fake_run_detection
    config = SplitConfig(output_dir=tmp_path, no_cache=True)
    run_split(source, config)

    data = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    assert data["detection_params"]["masked"] is False
    assert data["detection_params"]["masked_fallback_used"] is True

    cache = json.loads((tmp_path / ".detection_cache.json").read_text(encoding="utf-8"))
    # resolved path は cache key (params) ではなく top-level に記録する
    # (auto-masked 動画の cache 再利用は request key で正しく機能させる)。
    assert cache["masked_fallback_used"] is True
    assert cache["params"]["masked"] is False


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.probe_video")
def test_verbose_cache_hit_prints_masked_fallback_token(
    mock_probe, mock_split, tmp_path, capsys
):
    """cache-hit 表示は resolved path (masked_fallback=on/off) も出す."""
    source = tmp_path / "input.mp4"
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    _seed_cache(source, tmp_path, config)
    cache_path = tmp_path / ".detection_cache.json"
    data = json.loads(cache_path.read_text(encoding="utf-8"))
    data["masked_fallback_used"] = True
    cache_path.write_text(json.dumps(data), encoding="utf-8")

    mock_probe.return_value = PROBE_RESULT
    mock_split.return_value = _output_files(tmp_path)

    run_split(source, config, verbose=True)
    out = capsys.readouterr().out

    header_idx = out.find("Cache hit:")
    assert header_idx >= 0
    assert "masked_fallback=on" in out[header_idx:]


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
@patch(f"{MODULE}._load_cache_hit")
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
    mock_load_cache.return_value = CacheHit(
        boundaries=BOUNDARIES, masked_fallback_used=False, capture_regions=None
    )  # cache hit -> Pass 1 skip

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


# -- #810 capture_regions wiring through run_split (一気通貫) --

# `MODULE` / `PROBE_RESULT` / `BOUNDARIES` / `_mock_audio_scan` (autouse)
# は file 冒頭で既定義。brightness_samples #644 と同じ decorator / fixture 構成。


@patch(f"{MODULE}._run_detection")
@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.probe_video")
def test_run_split_writes_capture_regions_when_callback_fires(
    mock_probe, mock_split, mock_run_detection, tmp_path
):
    """#810 -- run_split (一気通貫) で region_callback が発火したら
    capture_regions が metadata.json に書かれること。"""
    from allaganeye.video.capture_region import FULL_FRAME, RegionTimeline

    mock_probe.return_value = PROBE_RESULT

    def fake_run_detection(*args, **kwargs):
        cb = kwargs.get("region_callback")
        assert cb is not None, (
            "run_split must pass region_callback to _run_detection (#810)"
        )
        cb(RegionTimeline(coarse=FULL_FRAME))
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

    payload = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))
    assert payload["capture_regions"]["coarse"]["source"] == "fallback"
    assert payload["capture_regions"]["fallback_reason"] is None
    assert payload["capture_regions"]["coarse"]["x"] == 0.0
    assert payload["capture_regions"]["coarse"]["w"] == 1.0


@patch(f"{MODULE}._run_detection")
@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.probe_video")
def test_run_split_omits_capture_regions_when_callback_silent(
    mock_probe, mock_split, mock_run_detection, tmp_path
):
    """#810 -- callback が発火しない run では field を書かない
    (brightness_samples #644 と同型の防御契約)。"""
    mock_probe.return_value = PROBE_RESULT
    mock_run_detection.side_effect = lambda *a, **kw: BOUNDARIES

    output_dir = tmp_path / "out2"
    mock_split.return_value = [
        output_dir / "match_001.mp4",
        output_dir / "match_002.mp4",
    ]
    video = tmp_path / "input.mp4"
    video.write_bytes(b"")
    config = SplitConfig(output_dir=output_dir, min_match_duration=60.0)

    run_split(video, config, verbose=False, quiet=True)

    payload = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))
    assert "capture_regions" not in payload


@patch("allaganeye.system_info.probe_gpu_vendors", return_value=[])
@patch(f"{MODULE}._run_detection")
@patch(f"{MODULE}._load_cache_hit")
@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.probe_video")
def test_run_split_cache_hit_carries_capture_regions(
    mock_probe,
    mock_split,
    mock_load_cache,
    mock_run_detection,
    mock_probe_gpu,
    tmp_path,
):
    """#810 round-1 #3 -- run_split cache-hit 経路で cache 記録の capture_regions
    が metadata.json へ引き継がれる (detect 側 pin と対の integration test)。

    `_load_cache_hit` を patch して CacheHit (with capture_regions) を返す (#879)。
    """
    band_regions = {
        "coarse": {
            "x": 0.1,
            "y": 0.0,
            "w": 0.76,
            "h": 0.042,
            "confidence": 0.9,
            "source": "band",
        },
        "segments": [],
        "fallback_reason": None,
    }
    output_dir = tmp_path / "out_cache_hit_regions"
    output_dir.mkdir(parents=True, exist_ok=True)

    mock_probe.return_value = PROBE_RESULT
    mock_load_cache.return_value = CacheHit(
        boundaries=BOUNDARIES,
        masked_fallback_used=False,
        capture_regions=band_regions,
    )
    mock_split.return_value = [
        output_dir / "match_001.mp4",
        output_dir / "match_002.mp4",
    ]

    video = tmp_path / "input.mp4"
    video.write_bytes(b"")
    config = SplitConfig(output_dir=output_dir, min_match_duration=60.0)

    run_split(video, config, verbose=False, quiet=True)

    mock_run_detection.assert_not_called()
    payload = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))
    assert payload["capture_regions"] == band_regions


@patch(f"{MODULE}._run_detection")
@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.probe_video")
def test_verbose_cache_miss_prints_region_line(
    mock_probe, mock_split, mock_run_detection, tmp_path, capsys
):
    """fresh 検知の verbose に Region: 行が出る (#810 round-1 #2 表示 wiring pin)."""
    from allaganeye.video.capture_region import FULL_FRAME, RegionTimeline

    mock_probe.return_value = PROBE_RESULT

    def fake_run_detection(*args, **kwargs):
        cb = kwargs.get("region_callback")
        assert cb is not None
        cb(RegionTimeline(coarse=FULL_FRAME))
        return BOUNDARIES

    mock_run_detection.side_effect = fake_run_detection

    output_dir = tmp_path / "out_region_line"
    mock_split.return_value = [
        output_dir / "match_001.mp4",
        output_dir / "match_002.mp4",
    ]
    video = tmp_path / "input.mp4"
    video.write_bytes(b"")
    config = SplitConfig(output_dir=output_dir, min_match_duration=60.0)

    run_split(video, config, verbose=True, quiet=False)
    out = capsys.readouterr().out
    assert "Region: full_frame" in out


# -- #805 段階2: post_match_trailing_dropped warning emission stopped (W1) --

# trailing_drop_callback の wiring は除去されたため、`_run_detection` を直接
# patch して callback が渡されないこと + warnings が空のままなことを assert する
# (post_match flag が warning を代替、brightness_samples #644 と同型の検証)。


@patch(f"{MODULE}._run_detection")
@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.probe_video")
def test_run_split_does_not_pass_trailing_drop_callback(
    mock_probe, mock_split, mock_run_detection, tmp_path
):
    """#805 段階2 (W1) -- run_split (一気通貫) は trailing_drop_callback を
    `_run_detection` に渡さず、warnings は emit されない (空のまま)。

    post_match flag が first-class 代替になったため、旧 callback チェーンは
    除去された。callback kwarg が assemble されないこと + warnings が [] で
    あることを assert する。
    """
    mock_probe.return_value = PROBE_RESULT

    def fake_run_detection(*args, **kwargs):
        assert "trailing_drop_callback" not in kwargs, (
            "run_split must NOT pass trailing_drop_callback to _run_detection "
            "(#805 段階2: callback removed, post_match flag replaces it)"
        )
        return BOUNDARIES

    mock_run_detection.side_effect = fake_run_detection

    output_dir = tmp_path / "out_drop"
    mock_split.return_value = [
        output_dir / "match_001.mp4",
        output_dir / "match_002.mp4",
    ]

    video = tmp_path / "input.mp4"
    video.write_bytes(b"")
    config = SplitConfig(output_dir=output_dir, min_match_duration=60.0, no_cache=True)

    run_split(video, config, verbose=False, quiet=True)

    payload = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))
    assert payload["warnings"] == []


@patch(f"{MODULE}._run_detection")
@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.probe_video")
def test_run_split_no_trailing_drop_writes_empty_warnings(
    mock_probe, mock_split, mock_run_detection, tmp_path
):
    """#805 段階1 -- 何も drop されない (callback 不発) なら warnings は []。"""
    mock_probe.return_value = PROBE_RESULT

    def fake_run_detection(*args, **kwargs):
        # callback を呼ばない (trailing drop なし)
        return BOUNDARIES

    mock_run_detection.side_effect = fake_run_detection

    output_dir = tmp_path / "out_nodrop"
    mock_split.return_value = [
        output_dir / "match_001.mp4",
        output_dir / "match_002.mp4",
    ]

    video = tmp_path / "input.mp4"
    video.write_bytes(b"")
    config = SplitConfig(output_dir=output_dir, min_match_duration=60.0, no_cache=True)

    run_split(video, config, verbose=False, quiet=True)

    payload = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))
    assert payload["warnings"] == []


def test_build_metadata_payload_round_trips_warnings(tmp_path):
    """#805 -- `_build_metadata_payload(warnings=[...])` emits the list
    verbatim; default (no arg) keeps the historical `[]` for existing callers.

    The ``warnings`` param survives 段階2 (only the trailing_drop emission seam
    was removed), so a pre-built list still round-trips unchanged.
    """
    from allaganeye.commands.split_matches import _build_metadata_payload

    system_info = {
        "gpu_vendors_available": [],
        "gpu_vendor_used": None,
        "vendor_preference": ["nvidia", "amd", "intel"],
    }
    common = dict(
        video_path=tmp_path / "input.mp4",
        source_duration=1800.0,
        source_fps=30.0,
        detected_at="2026-06-16T00:00:00Z",
        detection_started_at="2026-06-16T00:00:00Z",
        detection_completed_at="2026-06-16T00:01:00Z",
        effective_interval=1.0,
        config=SplitConfig(output_dir=tmp_path / "out", min_match_duration=60.0),
        boundaries=BOUNDARIES,
        output_files=_output_files(tmp_path / "out"),
        gaps=[],
        system_info=system_info,
    )

    # Default: no warnings arg -> [] (existing callers/tests stay green).
    default_payload = _build_metadata_payload(**common)  # type: ignore[arg-type]
    assert default_payload.get("warnings") == []

    # A pre-built warnings list (any code) is forwarded verbatim, not rebuilt.
    warned = [
        {
            "code": "some_warning_code",
            "message_en": "example",
            "severity": "warn",
            "context": {"start": 1000.0, "end": 1800.0},
        }
    ]
    payload = _build_metadata_payload(**common, warnings=warned)  # type: ignore[arg-type]
    assert payload.get("warnings") == warned


def test_split_matches_format_helpers_are_detection_format_aliases():
    from allaganeye.commands import split_matches as sm
    from allaganeye.detection import format as fmt

    assert sm._format_timestamp is fmt.format_timestamp
    assert sm._format_duration is fmt.format_duration
    assert sm._iso_utc_now is fmt.iso_utc_now


# -- #805 段階2: post_match boundary 除外 + metadata 搬送 --


def _build_metadata_payload_common(tmp_path, boundaries, output_files):
    """共通 kwargs を組み立てるヘルパ (既存テストのパターンを踏襲)。"""
    from allaganeye.commands.split_matches import _build_metadata_payload
    from allaganeye.config import SplitConfig

    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    return _build_metadata_payload(  # type: ignore[arg-type]
        video_path=tmp_path / "input.mp4",
        source_duration=1800.0,
        source_fps=30.0,
        detected_at="2026-06-26T00:00:00Z",
        detection_started_at="2026-06-26T00:00:00Z",
        detection_completed_at="2026-06-26T00:01:00Z",
        effective_interval=1.0,
        config=config,
        boundaries=boundaries,
        output_files=output_files,
        gaps=[],
        system_info={
            "gpu_vendors_available": [],
            "gpu_vendor_used": None,
            "vendor_preference": ["nvidia", "amd", "intel"],
        },
    )


def test_build_metadata_payload_post_match_excluded_from_outputs(tmp_path):
    """#805 段階2 -- post_match boundary は output_file なし・index 連番で matches に残る。

    active (index 1) は output_file を持ち、post_match (index 2) は
    output_file を持たず post_match=True が付く。
    """
    active: list[MatchBoundary] = [{"start": 0.0, "end": 600.0, "type": "fl_match"}]
    post_match: list[MatchBoundary] = [
        {"start": 600.0, "end": 700.0, "type": "unknown"}
    ]
    output_files = [tmp_path / "match_001.mp4"]  # active 分のみ

    from allaganeye.commands.split_matches import _build_metadata_payload
    from allaganeye.config import SplitConfig

    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    payload = _build_metadata_payload(  # type: ignore[arg-type]
        video_path=tmp_path / "input.mp4",
        source_duration=1800.0,
        source_fps=30.0,
        detected_at="2026-06-26T00:00:00Z",
        detection_started_at="2026-06-26T00:00:00Z",
        detection_completed_at="2026-06-26T00:01:00Z",
        effective_interval=1.0,
        config=config,
        boundaries=active,
        post_match_boundaries=post_match,
        output_files=output_files,
        gaps=[],
        system_info={
            "gpu_vendors_available": [],
            "gpu_vendor_used": None,
            "vendor_preference": ["nvidia", "amd", "intel"],
        },
    )

    matches = payload["matches"]
    assert len(matches) == 2
    # active match: index 1, output_file あり, post_match フラグ無し
    assert matches[0]["index"] == 1
    output_file = matches[0].get("output_file")
    assert output_file is not None and "match_001.mp4" in output_file
    assert "post_match" not in matches[0]
    # post_match match: index 2, output_file なし, post_match=True
    assert matches[1]["index"] == 2
    assert matches[1].get("post_match") is True
    assert "output_file" not in matches[1]


def test_build_metadata_payload_no_post_match_is_bitexact(tmp_path):
    """#805 段階2 -- post_match_boundaries 省略時は元の挙動と bit-exact。

    weak assertion (len / index / key presence) だけでは値の swap や active list
    の取り違えを検出できない。全フィールドを pin して構造的等価を保証する。
    """
    from allaganeye.commands.split_matches import _format_duration, _format_timestamp

    boundaries: list[MatchBoundary] = [
        {"start": 0.0, "end": 600.0, "type": "fl_match"},
        {"start": 610.0, "end": 1200.0, "type": "unknown"},
    ]
    output_files = [tmp_path / "match_001.mp4", tmp_path / "match_002.mp4"]

    payload = _build_metadata_payload_common(tmp_path, boundaries, output_files)

    matches = payload["matches"]
    assert matches == [
        {
            "index": 1,
            "start_time": 0.0,
            "end_time": 600.0,
            "start_display": _format_timestamp(0.0),
            "end_display": _format_timestamp(600.0),
            "duration": 600.0,
            "duration_display": _format_duration(600.0),
            "type": "fl_match",
            "output_file": (tmp_path / "match_001.mp4").as_posix(),
        },
        {
            "index": 2,
            "start_time": 610.0,
            "end_time": 1200.0,
            "start_display": _format_timestamp(610.0),
            "end_display": _format_timestamp(1200.0),
            "duration": 590.0,
            "duration_display": _format_duration(590.0),
            "type": "unknown",
            "output_file": (tmp_path / "match_002.mp4").as_posix(),
        },
    ]


@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.probe_video")
def test_split_and_write_metadata_post_match_not_passed_to_split_video(
    mock_probe, mock_split, tmp_path
):
    """#805 段階2 -- post_match boundary は split_video に渡されない。

    active boundary のみが split_video の第 2 引数に渡されることを assert する。
    """
    from allaganeye.commands.split_matches import _split_and_write_metadata
    from allaganeye.config import SplitConfig

    active_b: MatchBoundary = {"start": 0.0, "end": 600.0, "type": "fl_match"}
    # post_match フラグを持つ boundary は detector.py が将来付与する (Task 3)。
    # Task 2 では dict として注入して routing ロジックを検証する。
    post_match_b = {"start": 600.0, "end": 700.0, "type": "unknown", "post_match": True}
    boundaries: list[MatchBoundary] = [active_b, post_match_b]  # type: ignore[list-item]

    output_dir = tmp_path / "out"
    output_dir.mkdir()
    # split_video は active 分 (1件) の output file だけ返す
    mock_split.return_value = [output_dir / "match_001.mp4"]

    config = SplitConfig(output_dir=output_dir, min_match_duration=60.0)

    _split_and_write_metadata(
        video_path=tmp_path / "input.mp4",
        boundaries=boundaries,
        gaps=[],
        metadata=PROBE_RESULT,
        config=config,
        effective_interval=1.0,
        detected_at="2026-06-26T00:00:00Z",
        system_info={  # type: ignore[arg-type]
            "gpu_vendors_available": [],
            "gpu_vendor_used": None,
            "vendor_preference": ["nvidia", "amd", "intel"],
        },
        quiet=True,
    )

    # split_video は active (post_match でない) boundary だけで呼ばれる
    assert mock_split.called
    call_boundaries = mock_split.call_args[0][1]  # 第 2 引数 = boundaries
    assert len(call_boundaries) == 1
    assert call_boundaries[0] == active_b
    # post_match boundary は渡されていない
    assert not any(b.get("post_match") for b in call_boundaries)

    # metadata.json に post_match match が出力_file なしで残っている
    payload = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))
    matches = payload["matches"]
    assert len(matches) == 2
    assert "output_file" in matches[0]
    assert matches[1].get("post_match") is True
    assert "output_file" not in matches[1]


# ===========================================================================
# B6-M1: _display_cache_hit_params masked_algo token (#822)
# ===========================================================================


def test_display_cache_hit_params_masked_affected_shows_masked_algo(tmp_path, capsys):
    """B6-M1: masked-affected cache-hit summary contains masked_algo token.

    When the cache records masked=True (or masked_fallback_used=True), the
    verbose cache-hit summary must include the masked_algo token so operators
    can distinguish pre-#822 (masked_algo=1), post-#822 v2 (masked_algo=2),
    and post-#822 v3 (masked_algo=3, 15-probe quorum + zero-gap merge)
    results without re-running detection.
    """
    from allaganeye.commands.split_matches import _display_cache_hit_params

    cache_path = tmp_path / ".detection_cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "params": {
                    "sample_interval": 1.0,
                    "blackout_threshold": 15.0,
                    "min_match_duration": 300.0,
                    "min_blackout_duration": 3.0,
                    "no_audio": False,
                    "masked": True,
                    "vtuber": False,
                    "keep_trailing": False,
                    "masked_algo": 2,
                }
            }
        ),
        encoding="utf-8",
    )

    config = SplitConfig(output_dir=tmp_path, min_match_duration=300.0)
    _display_cache_hit_params(cache_path, config)
    out = capsys.readouterr().out
    assert "masked_algo=2" in out, (
        "masked-affected cache hit must include masked_algo token"
    )


def test_display_cache_hit_params_non_masked_omits_masked_algo(tmp_path, capsys):
    """B6-M1 (negative): non-masked cache-hit summary must NOT contain masked_algo.

    For standard OBS cache hits (masked=False, no masked_fallback), the
    masked_algo token is irrelevant and must be absent to keep the summary
    concise.
    """
    from allaganeye.commands.split_matches import _display_cache_hit_params

    cache_path = tmp_path / ".detection_cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "params": {
                    "sample_interval": 1.0,
                    "blackout_threshold": 15.0,
                    "min_match_duration": 300.0,
                    "min_blackout_duration": 3.0,
                    "no_audio": False,
                    "masked": False,
                    "vtuber": False,
                    "keep_trailing": False,
                    "masked_algo": 2,
                }
            }
        ),
        encoding="utf-8",
    )

    config = SplitConfig(output_dir=tmp_path, min_match_duration=300.0)
    _display_cache_hit_params(cache_path, config)
    out = capsys.readouterr().out
    assert "masked_algo" not in out, (
        "non-masked cache hit must NOT include masked_algo token"
    )


# ===========================================================================
# B6-M2: broken cache masked_algo robustness (round-1 fix)
# ===========================================================================


def test_display_cache_hit_params_broken_masked_algo_shows_question_mark(
    tmp_path, capsys
):
    """B6-M2a: broken masked_algo (non-int string) emits '?' token, does not raise.

    A corrupted cache with masked_algo="x" must not crash the display helper.
    The token should fall back to masked_algo=? so operators see a diagnostic
    indicator rather than a silent gap.
    """
    from allaganeye.commands.split_matches import _display_cache_hit_params

    cache_path = tmp_path / ".detection_cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "params": {
                    "sample_interval": 1.0,
                    "blackout_threshold": 15.0,
                    "min_match_duration": 300.0,
                    "min_blackout_duration": 3.0,
                    "no_audio": False,
                    "masked": True,
                    "vtuber": False,
                    "keep_trailing": False,
                    "masked_algo": "x",
                }
            }
        ),
        encoding="utf-8",
    )

    config = SplitConfig(output_dir=tmp_path, min_match_duration=300.0)
    _display_cache_hit_params(cache_path, config)
    out = capsys.readouterr().out
    assert "masked_algo=?" in out, (
        "broken masked_algo must display '?' fallback, not raise"
    )


def test_load_cache_broken_masked_algo_misses(tmp_path, cache_video):
    """B6-M2b: broken masked_algo (non-int string) in masked cache causes miss.

    When a masked-affected cache has a non-int masked_algo value the invalidation
    logic must treat it as a mismatch (miss direction) rather than raising or
    hitting incorrectly.
    """
    masked_config = SplitConfig(
        output_dir=tmp_path / "output",
        sample_interval=1.0,
        blackout_threshold=15.0,
        min_match_duration=300.0,
        min_blackout_duration=3.0,
        masked=True,
    )
    cache_path = tmp_path / "output" / ".detection_cache.json"
    _save_cache(
        cache_path, cache_video, PROBE_RESULT, 1.0, masked_config, CACHE_BOUNDARIES
    )
    # Inject a non-int masked_algo to simulate cache corruption
    data = json.loads(cache_path.read_text(encoding="utf-8"))
    data["params"]["masked_algo"] = "x"
    cache_path.write_text(json.dumps(data), encoding="utf-8")

    result = _load_cache_hit(cache_path, cache_video, 1.0, masked_config)
    assert result is None, "broken masked_algo must cause cache miss, not hit"


# ===========================================================================
# B6-V1: _display_cache_hit_params vtuber_algo token (#895)
# ===========================================================================


def test_display_cache_hit_params_vtuber_shows_vtuber_algo(tmp_path, capsys):
    """B6-V1: vtuber cache-hit summary contains vtuber_algo token.

    When the cache records vtuber=True, the verbose cache-hit summary must
    include the vtuber_algo token so operators can distinguish pre-#895
    (vtuber_algo=1, band-crop) from post-#895 (vtuber_algo>=2, timeline)
    results without re-running detection.
    """
    from allaganeye.commands.split_matches import _display_cache_hit_params

    cache_path = tmp_path / ".detection_cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "params": {
                    "sample_interval": 1.0,
                    "blackout_threshold": 15.0,
                    "min_match_duration": 300.0,
                    "min_blackout_duration": 3.0,
                    "no_audio": False,
                    "masked": False,
                    "vtuber": True,
                    "keep_trailing": False,
                    "vtuber_algo": 2,
                }
            }
        ),
        encoding="utf-8",
    )

    config = SplitConfig(output_dir=tmp_path, min_match_duration=300.0)
    _display_cache_hit_params(cache_path, config)
    out = capsys.readouterr().out
    assert "vtuber_algo=2" in out, "vtuber cache hit must include vtuber_algo token"


def test_display_cache_hit_params_non_vtuber_omits_vtuber_algo(tmp_path, capsys):
    """B6-V1 (negative): non-vtuber cache-hit summary must NOT contain vtuber_algo.

    For standard OBS cache hits (vtuber=False), the vtuber_algo token is
    irrelevant and must be absent to keep the summary concise.
    """
    from allaganeye.commands.split_matches import _display_cache_hit_params

    cache_path = tmp_path / ".detection_cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "params": {
                    "sample_interval": 1.0,
                    "blackout_threshold": 15.0,
                    "min_match_duration": 300.0,
                    "min_blackout_duration": 3.0,
                    "no_audio": False,
                    "masked": False,
                    "vtuber": False,
                    "keep_trailing": False,
                    "vtuber_algo": 2,
                }
            }
        ),
        encoding="utf-8",
    )

    config = SplitConfig(output_dir=tmp_path, min_match_duration=300.0)
    _display_cache_hit_params(cache_path, config)
    out = capsys.readouterr().out
    assert "vtuber_algo" not in out, (
        "non-vtuber cache hit must NOT include vtuber_algo token"
    )


def test_display_cache_hit_params_broken_vtuber_algo_shows_question_mark(
    tmp_path, capsys
):
    """B6-V2: broken vtuber_algo (non-int string) emits '?' token, does not raise.

    A corrupted cache with vtuber_algo="x" must not crash the display helper.
    The token should fall back to vtuber_algo=? so operators see a diagnostic
    indicator rather than a silent gap.
    """
    from allaganeye.commands.split_matches import _display_cache_hit_params

    cache_path = tmp_path / ".detection_cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "params": {
                    "sample_interval": 1.0,
                    "blackout_threshold": 15.0,
                    "min_match_duration": 300.0,
                    "min_blackout_duration": 3.0,
                    "no_audio": False,
                    "masked": False,
                    "vtuber": True,
                    "keep_trailing": False,
                    "vtuber_algo": "x",
                }
            }
        ),
        encoding="utf-8",
    )

    config = SplitConfig(output_dir=tmp_path, min_match_duration=300.0)
    _display_cache_hit_params(cache_path, config)
    out = capsys.readouterr().out
    assert "vtuber_algo=?" in out, (
        "broken vtuber_algo must display '?' fallback, not raise"
    )


def test_print_detection_stats_empty_stats_no_crash(capsys):
    """P1 契約 pin (#895): vtuber timeline path は DetectionStats を埋めずに
    early return するため、`--vtuber -v` の verbose 表示は空 stats で呼ばれる。
    _print_detection_stats の全 section が key-guarded で、空 stats では
    crash せず何も出力しないことを固定する (P2 で timeline 固有統計を
    設計するまでの回帰防止)。
    """
    from allaganeye.commands.split_matches import _print_detection_stats

    _print_detection_stats({})
    assert capsys.readouterr().out == ""


# --- _sanitize_brightness_samples (#879) ---


def test_sanitize_brightness_samples_accepts_valid():
    from allaganeye.commands.split_matches import _sanitize_brightness_samples

    value = {"interval_s": 2.0, "values": [0.0, 128.0, 255.0]}
    assert _sanitize_brightness_samples(value) == value


def test_sanitize_brightness_samples_rejects_extra_key():
    from allaganeye.commands.split_matches import _sanitize_brightness_samples

    assert (
        _sanitize_brightness_samples({"interval_s": 2.0, "values": [], "x": 1}) is None
    )


def test_sanitize_brightness_samples_rejects_nonpositive_interval():
    from allaganeye.commands.split_matches import _sanitize_brightness_samples

    assert _sanitize_brightness_samples({"interval_s": 0.0, "values": [1.0]}) is None


def test_sanitize_brightness_samples_rejects_bool_interval():
    from allaganeye.commands.split_matches import _sanitize_brightness_samples

    assert _sanitize_brightness_samples({"interval_s": True, "values": [1.0]}) is None


def test_sanitize_brightness_samples_rejects_value_out_of_range():
    from allaganeye.commands.split_matches import _sanitize_brightness_samples

    assert _sanitize_brightness_samples({"interval_s": 2.0, "values": [256.0]}) is None


def test_sanitize_brightness_samples_rejects_nan_value():
    from allaganeye.commands.split_matches import _sanitize_brightness_samples

    assert (
        _sanitize_brightness_samples({"interval_s": 2.0, "values": [float("nan")]})
        is None
    )


def test_sanitize_brightness_samples_rejects_values_not_list():
    from allaganeye.commands.split_matches import _sanitize_brightness_samples

    assert _sanitize_brightness_samples({"interval_s": 2.0, "values": "abc"}) is None


def test_preserve_brightness_samples_warns_on_malformed(caplog):
    """The preserve wiring drops a present-but-malformed value with a warning (#879)."""
    from allaganeye.commands import split_matches

    with caplog.at_level("WARNING"):
        result = split_matches._preserve_brightness_samples(
            {"brightness_samples": {"interval_s": -1.0, "values": [999.0]}}
        )
    assert result is None
    assert "Dropping malformed brightness_samples" in caplog.text


def test_preserve_brightness_samples_valid_passthrough_no_warn(caplog):
    from allaganeye.commands import split_matches

    valid = {"interval_s": 2.0, "values": [1.0]}
    with caplog.at_level("WARNING"):
        result = split_matches._preserve_brightness_samples(
            {"brightness_samples": valid}
        )
    assert result == valid
    assert "Dropping malformed" not in caplog.text


def test_preserve_brightness_samples_absent_no_warn(caplog):
    from allaganeye.commands import split_matches

    with caplog.at_level("WARNING"):
        result = split_matches._preserve_brightness_samples({})
    assert result is None
    assert "Dropping malformed" not in caplog.text


def test_sanitize_brightness_samples_rejects_nan_interval(caplog):
    from allaganeye.commands.split_matches import _sanitize_brightness_samples

    assert (
        _sanitize_brightness_samples({"interval_s": float("nan"), "values": []}) is None
    )
    assert (
        _sanitize_brightness_samples({"interval_s": float("inf"), "values": []}) is None
    )


# ---------------------------------------------------------------------------
# Task 4: CacheHit + _load_cache_hit single-read (#879)
# ---------------------------------------------------------------------------


def _write_cache(tmp_path, video_path, *, interval=2.0, extra=None):
    """Minimal valid detection cache matching _load_cache_hit's key checks."""
    import json as _json

    from allaganeye.commands import split_matches

    stat = video_path.stat()
    data = {
        "cache_version": split_matches._CACHE_VERSION,
        "source": str(video_path.resolve()),
        "source_size": stat.st_size,
        "source_mtime": stat.st_mtime,
        "params": {
            "sample_interval": interval,
            "blackout_threshold": 15.0,
            "min_match_duration": 300.0,
            "min_blackout_duration": 3.0,
            "no_audio": False,
            # masked_algo は masked_affected になりうる cache で key mismatch miss を
            # 防ぐために _MASKED_ALGO_VERSION で pin する (#879 key validation)
            "masked_algo": split_matches._MASKED_ALGO_VERSION,
        },
        "boundaries": [[0.0, 100.0]],
    }
    if extra:
        data.update(extra)
    cache_path = tmp_path / ".detection_cache.json"
    cache_path.write_text(_json.dumps(data), encoding="utf-8")
    return cache_path


def _cache_config(tmp_path):
    from allaganeye.commands.split_matches import SplitConfig

    return SplitConfig(output_dir=tmp_path)


def test_load_cache_hit_reads_file_once(tmp_path, monkeypatch):
    """三重 read 解消の pin: cache-hit で read_text は 1 回だけ (#879)."""
    from allaganeye.commands import split_matches

    video = tmp_path / "v.mkv"
    video.write_bytes(b"x" * 10)
    cache_path = _write_cache(tmp_path, video, extra={"masked_fallback_used": True})

    calls = {"n": 0}
    real_read = split_matches.Path.read_text

    def counting_read(self, *a, **k):
        if self == cache_path:
            calls["n"] += 1
        return real_read(self, *a, **k)

    monkeypatch.setattr(split_matches.Path, "read_text", counting_read)
    hit = split_matches._load_cache_hit(cache_path, video, 2.0, _cache_config(tmp_path))
    assert hit is not None
    assert hit.boundaries == [[0.0, 100.0]]
    assert hit.masked_fallback_used is True
    assert calls["n"] == 1


def test_load_cache_hit_miss_returns_none(tmp_path):
    from allaganeye.commands import split_matches

    video = tmp_path / "v.mkv"
    video.write_bytes(b"x" * 10)
    cache_path = _write_cache(tmp_path, video)
    # interval mismatch -> miss
    assert (
        split_matches._load_cache_hit(cache_path, video, 999.0, _cache_config(tmp_path))
        is None
    )


def test_load_cache_hit_synthesizes_legacy_full_frame(tmp_path):
    """pre-#810 legacy cache (capture_regions 欠落, vtuber/masked off) は FULL_FRAME 合成 (#879 保持)."""
    from allaganeye.commands import split_matches
    from allaganeye.video.capture_region import FULL_FRAME, RegionTimeline

    video = tmp_path / "v.mkv"
    video.write_bytes(b"x" * 10)
    cache_path = _write_cache(tmp_path, video)
    hit = split_matches._load_cache_hit(cache_path, video, 2.0, _cache_config(tmp_path))
    assert hit is not None
    assert hit.capture_regions == RegionTimeline(coarse=FULL_FRAME).to_dict()


def test_capture_regions_from_cache_data_pure(tmp_path):
    from allaganeye.commands import split_matches

    valid = {
        "coarse": {
            "x": 0.0,
            "y": 0.0,
            "w": 1.0,
            "h": 1.0,
            "confidence": 1.0,
            "source": "full_frame",
        },
        "segments": [],
        "fallback_reason": None,
    }
    data = {"capture_regions": valid}
    assert split_matches._capture_regions_from_cache_data(data) == valid


def test_masked_fallback_from_cache_data_pure():
    from allaganeye.commands import split_matches

    assert (
        split_matches._masked_fallback_from_cache_data({"masked_fallback_used": True})
        is True
    )
    assert split_matches._masked_fallback_from_cache_data({}) is False
