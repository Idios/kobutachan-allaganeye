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

    with patch("click.progressbar") as mock_bar:
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
    """Progress bars enable ETA and percent display (#329).

    Guards the contract from issue #329: the user must be able to tell
    that the time shown is ETA, via ``show_eta=True`` on click.progressbar.
    """
    mock_probe.return_value = PROBE_RESULT
    mock_detect.return_value = BOUNDARIES
    mock_split.return_value = _output_files(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)

    with patch("click.progressbar") as mock_bar:
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

    with patch("click.progressbar") as mock_bar:
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

    with patch("click.progressbar") as mock_bar:
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

    with patch("click.progressbar") as mock_bar:
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
    """Codec-based GPU/CPU auto-selection (#334)."""

    def test_explicit_gpu_true(self):
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        assert _resolve_gpu_mode(True, "av1", show=False, verbose=False) is True

    def test_explicit_gpu_false(self):
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        assert _resolve_gpu_mode(False, "h264", show=False, verbose=False) is False

    def test_auto_h264_selects_gpu(self):
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        assert _resolve_gpu_mode(None, "h264", show=False, verbose=False) is True

    def test_auto_hevc_selects_gpu(self):
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        assert _resolve_gpu_mode(None, "hevc", show=False, verbose=False) is True

    def test_auto_av1_selects_cpu(self):
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        assert _resolve_gpu_mode(None, "av1", show=False, verbose=False) is False

    def test_auto_vp9_selects_cpu(self):
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        assert _resolve_gpu_mode(None, "vp9", show=False, verbose=False) is False

    def test_auto_unknown_codec_selects_cpu(self):
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        assert _resolve_gpu_mode(None, None, show=False, verbose=False) is False

    def test_auto_verbose_shows_message(self, capsys):
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        _resolve_gpu_mode(None, "h264", show=True, verbose=True)
        out = capsys.readouterr().out
        assert "Auto-selected GPU mode" in out
        assert "h264" in out

    def test_auto_cpu_verbose_shows_cpu_message(self, capsys):
        """CPU auto-selection also emits a verbose notice (#334).

        Guards the else-branch of the mode resolution -- users on
        AV1/VP9 recordings need to see that CPU mode was chosen
        intentionally (not just because GPU failed).
        """
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        _resolve_gpu_mode(None, "av1", show=True, verbose=True)
        out = capsys.readouterr().out
        assert "Auto-selected CPU mode" in out
        assert "av1" in out

    def test_auto_non_verbose_suppresses_message(self, capsys):
        """Non-verbose auto selection is silent (#334)."""
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        _resolve_gpu_mode(None, "h264", show=True, verbose=False)
        out = capsys.readouterr().out
        assert "Auto-selected" not in out

    def test_auto_quiet_suppresses_message(self, capsys):
        """--quiet (show=False) silences auto-selection message even with verbose (#334)."""
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        _resolve_gpu_mode(None, "h264", show=False, verbose=True)
        out = capsys.readouterr().out
        assert "Auto-selected" not in out

    def test_auto_codec_matching_is_case_insensitive(self):
        """Codec name matching is case-insensitive (#334).

        ffprobe normally returns lowercase codec_name, but downstream
        callers or manual ProbeResult construction may pass "H264" /
        "HEVC".  The set is compared via ``.lower()``; guards against a
        future refactor dropping that normalization.
        """
        from allaganeye.commands.split_matches import _resolve_gpu_mode

        assert _resolve_gpu_mode(None, "H264", show=False, verbose=False) is True
        assert _resolve_gpu_mode(None, "HEVC", show=False, verbose=False) is True
        assert _resolve_gpu_mode(None, "Hevc", show=False, verbose=False) is True


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


def test_display_cache_hit_params_swallows_corrupt_cache(tmp_path, capsys):
    """Helper does not raise if the cache file is unreadable (#380).

    _load_cache already validated the file, but a race or mid-flight
    corruption shouldn't abort the split.  Missing params dict -> silent.
    """
    from allaganeye.commands.split_matches import _display_cache_hit_params

    cache_path = tmp_path / ".detection_cache.json"
    cache_path.write_text("not json at all", encoding="utf-8")

    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    # Must not raise.
    _display_cache_hit_params(cache_path, config)
    out = capsys.readouterr().out
    assert out == "", f"expected silent return, got: {out!r}"


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
