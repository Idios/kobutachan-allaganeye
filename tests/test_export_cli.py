"""Tests for 'allaganeye export' CLI (#761)."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from allaganeye.commands.export import register
from allaganeye.export.schema import ExportSummary

runner = CliRunner()


@pytest.fixture
def app() -> typer.Typer:
    a = typer.Typer()

    # Force group mode for single-command isolation testing (see Task 8 fixture)
    @a.callback()
    def _():
        pass

    register(a)
    return a


@pytest.fixture(autouse=True)
def _source_video_on_disk(tmp_path: Path) -> Path:
    """#930 B2: export preflights that ``source`` actually exists.

    Every fixture payload in this module points ``source`` at
    ``<tmp_path>/in.mp4``; materialise it so the tests exercise the export
    logic rather than the new missing-source guard (which has its own
    coverage in ``tests/test_split_matches.py``).
    """
    path = tmp_path / "in.mp4"
    path.write_bytes(b"")
    return path


def _make_metadata(tmp_path: Path) -> Path:
    """metadata.json on disk with 2 matches."""
    payload = {
        "schema_version": "1",
        "source": str(tmp_path / "in.mp4"),
        "matches": [
            {"index": 0, "start_time": 0.0, "end_time": 10.0, "type": "match"},
            {"index": 1, "start_time": 10.0, "end_time": 20.0, "type": "match"},
        ],
        "system_info": {
            "gpu_vendors_available": ["nvidia"],
            "vendor_preference": ["nvidia", "amd", "intel"],
            "gpu": ["NVIDIA GeForce RTX 5090"],
        },
    }
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@patch("allaganeye.commands.export.export_matches")
def test_export_positional_metadata_path(
    mock_export: MagicMock, app: typer.Typer, tmp_path: Path
):
    mock_export.return_value = ExportSummary(success=2, failure=0)
    metadata_path = _make_metadata(tmp_path)
    result = runner.invoke(
        app,
        [
            "export",
            str(metadata_path),
            "--output-dir",
            str(tmp_path),
            "--codec",
            "h264",
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    mock_export.assert_called_once()


@patch("allaganeye.commands.export.export_matches")
def test_export_stdin_mode(mock_export: MagicMock, app: typer.Typer, tmp_path: Path):
    mock_export.return_value = ExportSummary(success=1, failure=0)
    payload = json.dumps(
        {
            "source": str(tmp_path / "in.mp4"),
            "matches": [
                {"index": 0, "start_time": 0.0, "end_time": 5.0, "type": "match"}
            ],
            "system_info": {
                "gpu_vendors_available": [],
                "vendor_preference": ["nvidia"],
                "gpu": [],
            },
        }
    )
    result = runner.invoke(
        app,
        [
            "export",
            "--stdin",
            "--output-dir",
            str(tmp_path),
            "--codec",
            "copy",
            "--quiet",
        ],
        input=payload,
    )
    assert result.exit_code == 0
    mock_export.assert_called_once()


@patch("allaganeye.commands.export.export_matches")
def test_export_json_mode_emits_summary_line(
    mock_export: MagicMock, app: typer.Typer, tmp_path: Path
):
    """--json mode で stdout の最後の行が summary event."""
    mock_export.return_value = ExportSummary(success=1, failure=0, cancelled=False)
    metadata_path = _make_metadata(tmp_path)
    result = runner.invoke(
        app,
        [
            "export",
            str(metadata_path),
            "--output-dir",
            str(tmp_path),
            "--codec",
            "h264",
            "--json",
        ],
    )
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert lines, "expected at least one JSON line"
    last = json.loads(lines[-1])
    assert last["type"] == "summary"


@patch("allaganeye.commands.export.export_matches")
def test_export_exclude_filters_matches(
    mock_export: MagicMock, app: typer.Typer, tmp_path: Path
):
    mock_export.return_value = ExportSummary(success=1, failure=0)
    metadata_path = _make_metadata(tmp_path)
    result = runner.invoke(
        app,
        [
            "export",
            str(metadata_path),
            "--output-dir",
            str(tmp_path),
            "--codec",
            "h264",
            "--exclude",
            "1",
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    args, kwargs = mock_export.call_args
    # matches[] should have index 0 only after filter
    passed_matches = kwargs.get("matches") or args[0]
    assert [m.index for m in passed_matches] == [0]


def test_export_no_metadata_no_stdin_errors(app: typer.Typer):
    result = runner.invoke(app, ["export"])
    assert result.exit_code != 0  # Typer error: missing argument


@patch("allaganeye.commands.export.export_matches")
def test_export_returns_exit_1_on_failure(
    mock_export: MagicMock, app: typer.Typer, tmp_path: Path
):
    mock_export.return_value = ExportSummary(success=0, failure=2)
    metadata_path = _make_metadata(tmp_path)
    result = runner.invoke(
        app,
        [
            "export",
            str(metadata_path),
            "--output-dir",
            str(tmp_path),
            "--codec",
            "h264",
            "--quiet",
        ],
    )
    assert result.exit_code == 1


@patch("allaganeye.commands.export.export_matches")
def test_export_respects_edited_zero_start(
    mock_export: MagicMock, app: typer.Typer, tmp_path: Path
):
    """edited.start_time == 0.0 must be honored (not fall back to start_time)."""
    mock_export.return_value = ExportSummary(success=1, failure=0)
    payload = {
        "schema_version": "1",
        "source": str(tmp_path / "in.mp4"),
        "matches": [
            {
                "index": 0,
                "start_time": 5.0,
                "end_time": 10.0,
                "type": "match",
                "edited": {"start_time": 0.0, "end_time": 7.5},
            },
        ],
        "system_info": {
            "gpu_vendors_available": [],
            "vendor_preference": ["nvidia"],
            "gpu": [],
        },
    }
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "export",
            str(metadata_path),
            "--output-dir",
            str(tmp_path),
            "--codec",
            "copy",
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    _, kwargs = mock_export.call_args
    passed_matches = kwargs.get("matches")
    assert passed_matches[0].start == 0.0  # not 5.0
    assert passed_matches[0].end == 7.5


@patch("allaganeye.commands.export.export_matches")
def test_export_include_filters_matches(
    mock_export: MagicMock, app: typer.Typer, tmp_path: Path
):
    """--include keeps only listed indexes (others skipped)."""
    mock_export.return_value = ExportSummary(success=1, failure=0)
    metadata_path = _make_metadata(tmp_path)  # 2 matches: indexes 0, 1
    result = runner.invoke(
        app,
        [
            "export",
            str(metadata_path),
            "--output-dir",
            str(tmp_path),
            "--codec",
            "h264",
            "--include",
            "1",
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    _, kwargs = mock_export.call_args
    assert [m.index for m in kwargs.get("matches")] == [1]


@patch("allaganeye.commands.export.export_matches")
@patch("allaganeye.commands.export.enumerate_h264_encoders")
def test_export_concurrency_slices_slots(
    mock_enumerate: MagicMock, mock_export: MagicMock, app: typer.Typer, tmp_path: Path
):
    """--concurrency N truncates the slot list returned by enumerate_h264_encoders to first N."""
    from allaganeye.export.encoder import EncoderSlot, H264Encoder

    mock_enumerate.return_value = [
        EncoderSlot(
            slot_index=i,
            encoder_kind=H264Encoder.NVENC,
            display_label=f"NVENC #{i + 1}",
        )
        for i in range(3)
    ]
    mock_export.return_value = ExportSummary(success=2, failure=0)
    metadata_path = _make_metadata(tmp_path)
    result = runner.invoke(
        app,
        [
            "export",
            str(metadata_path),
            "--output-dir",
            str(tmp_path),
            "--codec",
            "h264",
            "--concurrency",
            "2",
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    _, kwargs = mock_export.call_args
    assert len(kwargs.get("slots")) == 2


@patch("allaganeye.commands.export.export_matches")
def test_export_include_minus_exclude(
    mock_export: MagicMock, app: typer.Typer, tmp_path: Path
):
    """--include and --exclude combined: effective set = include - exclude."""
    mock_export.return_value = ExportSummary(success=1, failure=0)
    # build metadata with 3 matches (indexes 0, 1, 2)
    payload = {
        "schema_version": "1",
        "source": str(tmp_path / "in.mp4"),
        "matches": [
            {"index": 0, "start_time": 0.0, "end_time": 10.0, "type": "match"},
            {"index": 1, "start_time": 10.0, "end_time": 20.0, "type": "match"},
            {"index": 2, "start_time": 20.0, "end_time": 30.0, "type": "match"},
        ],
        "system_info": {
            "gpu_vendors_available": [],
            "vendor_preference": ["nvidia"],
            "gpu": [],
        },
    }
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "export",
            str(metadata_path),
            "--output-dir",
            str(tmp_path),
            "--codec",
            "h264",
            "--include",
            "0,1,2",
            "--exclude",
            "1",
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    _, kwargs = mock_export.call_args
    assert [m.index for m in kwargs.get("matches")] == [0, 2]


@patch("allaganeye.commands.export.export_matches")
@patch("allaganeye.commands.export.enumerate_h264_encoders")
def test_export_copy_mode_uses_single_slot(
    mock_enumerate: MagicMock, mock_export: MagicMock, app: typer.Typer, tmp_path: Path
):
    """codec=copy should truncate slot list to 1 (parallel copy is wasteful)."""
    from allaganeye.export.encoder import EncoderSlot, H264Encoder

    mock_enumerate.return_value = [
        EncoderSlot(
            slot_index=i,
            encoder_kind=H264Encoder.NVENC,
            display_label=f"NVENC #{i + 1}",
        )
        for i in range(3)
    ]
    mock_export.return_value = ExportSummary(success=2, failure=0)
    metadata_path = _make_metadata(tmp_path)
    result = runner.invoke(
        app,
        [
            "export",
            str(metadata_path),
            "--output-dir",
            str(tmp_path),
            "--codec",
            "copy",
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    _, kwargs = mock_export.call_args
    assert len(kwargs.get("slots")) == 1


def test_export_creates_missing_output_dir(app: typer.Typer, tmp_path: Path):
    # P2-10: export did not mkdir output_dir (split/detect do), so a missing
    # -o dir made every match's ffmpeg fail to write and the run exited 1.
    out = tmp_path / "nested" / "out"  # does not exist yet
    captured: dict[str, object] = {}

    def fake_export_matches(**kwargs: object) -> ExportSummary:
        out_dir = kwargs["output_dir"]
        assert isinstance(out_dir, Path)
        captured["output_dir"] = out_dir
        captured["exists"] = out_dir.exists()
        return ExportSummary(success=1)

    metadata_path = _make_metadata(tmp_path)
    with patch(
        "allaganeye.commands.export.export_matches",
        side_effect=fake_export_matches,
    ):
        result = runner.invoke(
            app,
            [
                "export",
                str(metadata_path),
                "--output-dir",
                str(out),
                "--codec",
                "h264",
                "--quiet",
            ],
        )
    assert result.exit_code == 0, result.output
    assert captured["exists"] is True  # output_dir already existed when called


@patch("allaganeye.commands.export.export_matches")
def test_export_counts_skipped(
    mock_export: MagicMock, app: typer.Typer, tmp_path: Path
):
    # P2-9: ExportSummary.skipped was never incremented and stayed 0 regardless
    # of include/exclude/type_override=skip filtering. Verify the --json summary
    # reports the real filtered-out count.
    mock_export.return_value = ExportSummary(success=1, failure=0)
    payload = {
        "schema_version": "1",
        "source": str(tmp_path / "in.mp4"),
        "matches": [
            {"index": 0, "start_time": 0.0, "end_time": 10.0, "type": "match"},
            {"index": 1, "start_time": 10.0, "end_time": 20.0, "type": "match"},
            {
                "index": 2,
                "start_time": 20.0,
                "end_time": 30.0,
                "type": "match",
                "type_override": "skip",
            },
        ],
        "system_info": {
            "gpu_vendors_available": [],
            "vendor_preference": ["nvidia"],
            "gpu": [],
        },
    }
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "export",
            str(metadata_path),
            "--output-dir",
            str(tmp_path),
            "--codec",
            "h264",
            "--exclude",
            "1",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    # export target is index 0 only (index 1 excluded, index 2 skip-override)
    _, kwargs = mock_export.call_args
    assert [m.index for m in kwargs.get("matches")] == [0]
    # summary.skipped reflects the 2 filtered-out matches
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    last = json.loads(lines[-1])
    assert last["type"] == "summary"
    assert last["skipped"] == 2


@patch("allaganeye.commands.export.export_matches")
def test_export_skips_post_match_on_export_all(
    mock_export: MagicMock, app: typer.Typer, tmp_path: Path
):
    # #805 Phase 1 (Codex HIGH 2): a post_match trailing segment is the
    # non-destructive marker for a post-match (lobby/city) run -- the CLI
    # excludes it from MP4 output and retains it only in metadata. Export
    # (CLI and GUI share this code path) must NOT encode it even on
    # "export all" (no include/exclude). Verify the post_match match is
    # filtered out of the export set and counted as skipped, while the
    # active match is exported.
    mock_export.return_value = ExportSummary(success=1, failure=0)
    payload = {
        "schema_version": "1",
        "source": str(tmp_path / "in.mp4"),
        "matches": [
            {"index": 0, "start_time": 0.0, "end_time": 10.0, "type": "match"},
            {
                "index": 1,
                "start_time": 10.0,
                "end_time": 20.0,
                "type": "unknown",
                "post_match": True,
            },
        ],
        "system_info": {
            "gpu_vendors_available": [],
            "vendor_preference": ["nvidia"],
            "gpu": [],
        },
    }
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "export",
            str(metadata_path),
            "--output-dir",
            str(tmp_path),
            "--codec",
            "h264",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    # export target is the active match only (index 0); index 1 is post_match.
    _, kwargs = mock_export.call_args
    assert [m.index for m in kwargs.get("matches")] == [0]
    # summary.skipped reflects the 1 post_match match excluded from output.
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    last = json.loads(lines[-1])
    assert last["type"] == "summary"
    assert last["skipped"] == 1


@patch("allaganeye.commands.export.export_matches")
def test_export_post_match_excluded_even_when_explicitly_included(
    mock_export: MagicMock, app: typer.Typer, tmp_path: Path
):
    # Fix 1 lock test: post_match exclusion is UNCONDITIONAL -- even if the
    # caller explicitly names the post_match index in --include, the segment
    # must NOT be exported and must be counted as skipped. This locks the
    # guard-order invariant: moving the post_match check after the include
    # guard would break this (the included post_match would fall through to
    # append). The test must PASS against the current code (confirming
    # correctness) and FAIL if the guards are reordered.
    mock_export.return_value = ExportSummary(success=1, failure=0)
    payload = {
        "schema_version": "1",
        "source": str(tmp_path / "in.mp4"),
        "matches": [
            {"index": 1, "start_time": 0.0, "end_time": 10.0, "type": "match"},
            {
                "index": 2,
                "start_time": 10.0,
                "end_time": 20.0,
                "type": "unknown",
                "post_match": True,
            },
        ],
        "system_info": {
            "gpu_vendors_available": [],
            "vendor_preference": ["nvidia"],
            "gpu": [],
        },
    }
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")
    # Explicitly include BOTH the active match (1) and the post_match (2).
    # The post_match must still be excluded and not reach export_matches.
    result = runner.invoke(
        app,
        [
            "export",
            str(metadata_path),
            "--output-dir",
            str(tmp_path),
            "--codec",
            "h264",
            "--include",
            "1,2",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    # Only the active match (index 1) must be passed to export_matches.
    _, kwargs = mock_export.call_args
    assert [m.index for m in kwargs.get("matches")] == [1], (
        "post_match match reached export_matches despite --include; "
        "unconditional guard must fire before include check"
    )
    # The post_match match must appear in skipped count (1 skipped).
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    last = json.loads(lines[-1])
    assert last["type"] == "summary"
    assert last["skipped"] == 1, (
        f"expected skipped=1 (the post_match), got skipped={last['skipped']}"
    )


@patch("allaganeye.commands.export.export_matches")
def test_export_explicit_include_of_post_match_warns(
    mock_export: MagicMock, app: typer.Typer, tmp_path: Path
):
    # Round 1 (A): explicitly naming a post_match index in --include used to be a
    # silent no-op -- the post_match guard fires first and skips the segment, and
    # the "index not found" warning does NOT trigger because the index IS valid.
    # The user gets zero feedback that their requested index was dropped. Verify a
    # notice is printed (actionable visibility) WITHOUT changing the invariant:
    # the post_match must still never reach export_matches.
    mock_export.return_value = ExportSummary(success=1, failure=0)
    payload = {
        "schema_version": "1",
        "source": str(tmp_path / "in.mp4"),
        "matches": [
            {"index": 1, "start_time": 0.0, "end_time": 10.0, "type": "match"},
            {
                "index": 2,
                "start_time": 10.0,
                "end_time": 20.0,
                "type": "unknown",
                "post_match": True,
            },
        ],
        "system_info": {
            "gpu_vendors_available": [],
            "vendor_preference": ["nvidia"],
            "gpu": [],
        },
    }
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")
    # Explicitly include ONLY the post_match index (2).
    result = runner.invoke(
        app,
        [
            "export",
            str(metadata_path),
            "--output-dir",
            str(tmp_path),
            "--codec",
            "h264",
            "--include",
            "2",
            "--quiet",
        ],
    )
    assert result.exit_code == 0, result.output
    # (a) invariant intact: the post_match (index 2) must NOT reach export_matches.
    _, kwargs = mock_export.call_args
    assert 2 not in [m.index for m in kwargs.get("matches")], (
        "post_match match reached export_matches despite being post_match; "
        "unconditional exclusion invariant must hold"
    )
    # (b) a notice naming the explicitly-included post_match index must print.
    out = result.output.lower()
    assert "warning" in out, "expected a notice for explicit --include of post_match"
    assert "post-match" in out, "notice must explain the index is a post-match segment"
    assert "2" in result.output, "notice must name the requested index"


def test_export_json_reconfigures_stdout_utf8(app: typer.Typer, tmp_path: Path):
    # P2-8: --json emits non-ASCII (output_path / error_message) with
    # ensure_ascii=False but never reconfigured stdout to UTF-8, relying on the
    # Rust caller's PYTHONIOENCODING. On a cp932 console CLI-only this corrupts
    # output. Verify the command reconfigures stdout to utf-8.
    import click.testing as click_testing

    calls: list[dict[str, object]] = []

    def spy_reconfigure(self: io.TextIOWrapper, **kw: object) -> None:
        calls.append(kw)
        io.TextIOWrapper.reconfigure(self, **kw)  # type: ignore[arg-type]

    metadata_path = _make_metadata(tmp_path)
    with (
        patch.object(click_testing._NamedTextIOWrapper, "reconfigure", spy_reconfigure),
        patch(
            "allaganeye.commands.export.export_matches",
            return_value=ExportSummary(success=1),
        ),
    ):
        result = runner.invoke(
            app,
            [
                "export",
                str(metadata_path),
                "--output-dir",
                str(tmp_path),
                "--codec",
                "h264",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.output
    assert any(c.get("encoding") == "utf-8" for c in calls), calls


def test_export_stdin_reads_utf8_buffer(app: typer.Typer, tmp_path: Path):
    # P2-8: --stdin must read sys.stdin.buffer as bytes and decode UTF-8 so a
    # cp932 default stdin encoding (Windows console) can't corrupt a non-ASCII
    # source path. We model that by giving CliRunner a cp932 text layer over
    # UTF-8 bytes: the old json.load(sys.stdin) text path mis-decodes, the new
    # buffer path round-trips.
    cp932_runner = CliRunner(charset="cp932")
    non_ascii_video = tmp_path / "録画" / "試合.mp4"
    non_ascii_video.parent.mkdir(parents=True, exist_ok=True)
    non_ascii_video.write_bytes(b"")  # #930 B2: export preflights existence
    non_ascii_source = str(non_ascii_video)
    # ensure_ascii=False so the wire carries raw UTF-8 multibyte bytes. With the
    # old json.load(sys.stdin) cp932 text path those bytes mis-decode (mojibake);
    # only sys.stdin.buffer + UTF-8 decode round-trips. (ASCII-escaped JSON would
    # decode identically under any charset and would not discriminate.)
    payload = json.dumps(
        {
            "source": non_ascii_source,
            "matches": [
                {"index": 0, "start_time": 0.0, "end_time": 5.0, "type": "match"}
            ],
            "system_info": {
                "gpu_vendors_available": [],
                "vendor_preference": ["nvidia"],
                "gpu": [],
            },
        },
        ensure_ascii=False,
    )

    captured: dict[str, object] = {}

    def fake_export_matches(**kwargs: object) -> ExportSummary:
        captured["source_video"] = kwargs["source_video"]
        return ExportSummary(success=1)

    with patch(
        "allaganeye.commands.export.export_matches",
        side_effect=fake_export_matches,
    ):
        result = cp932_runner.invoke(
            app,
            [
                "export",
                "--stdin",
                "--output-dir",
                str(tmp_path),
                "--codec",
                "copy",
                "--quiet",
            ],
            input=payload.encode("utf-8"),
        )
    assert result.exit_code == 0, result.output
    assert str(captured["source_video"]) == non_ascii_source


def test_export_maps_allagan_error_to_exit_code(app: typer.Typer, tmp_path: Path):
    # P2-7: export alone did not catch AllaganEyeError -> raw traceback + exit 1.
    # It must map to the error's exit code with a clean stderr (no traceback),
    # like split/detect/debug-brightness.
    from allaganeye.exceptions import VideoProcessingError

    metadata_path = _make_metadata(tmp_path)
    with patch(
        "allaganeye.commands.export.export_matches",
        side_effect=VideoProcessingError("ffmpeg boom"),
    ):
        result = runner.invoke(
            app,
            [
                "export",
                str(metadata_path),
                "--output-dir",
                str(tmp_path),
                "--codec",
                "h264",
                "--quiet",
            ],
        )
    assert result.exit_code == 3  # VideoProcessingError.exit_code
    assert "Error: ffmpeg boom" in result.output
    assert "Traceback" not in result.output


def test_export_json_does_not_emit_summary_on_error(app: typer.Typer, tmp_path: Path):
    # P2-7: in --json mode a hard error must NOT emit a summary line. start_export
    # treats any summary line as success (lib.rs) and would mask the error in the
    # GUI. The terminal signal is a non-zero exit + stderr, never a summary.
    from allaganeye.exceptions import VideoProcessingError

    metadata_path = _make_metadata(tmp_path)
    with patch(
        "allaganeye.commands.export.export_matches",
        side_effect=VideoProcessingError("ffmpeg boom"),
    ):
        result = runner.invoke(
            app,
            [
                "export",
                str(metadata_path),
                "--output-dir",
                str(tmp_path),
                "--codec",
                "h264",
                "--json",
            ],
        )
    assert result.exit_code == 3
    # no summary line on stdout (stderr carries the error)
    assert '"type": "summary"' not in result.stdout
    assert '"type":"summary"' not in result.stdout


def _make_colliding_metadata(tmp_path: Path) -> Path:
    """metadata.json whose 2 matches collide under a pattern without {idx}."""
    payload = {
        "schema_version": "1",
        "source": str(tmp_path / "in.mp4"),
        "matches": [
            {"index": 0, "start_time": 0.0, "end_time": 10.0, "type": "match"},
            {"index": 1, "start_time": 10.0, "end_time": 20.0, "type": "match"},
        ],
        "system_info": {
            "gpu_vendors_available": [],
            "vendor_preference": ["nvidia"],
            "gpu": [],
        },
    }
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")
    return metadata_path


def test_export_collision_is_hard_error_exit5(app: typer.Typer, tmp_path: Path):
    # Finding 3: a name pattern without {idx}/{idx:03} maps every match to the
    # same filename (overwrite / parallel race / misleading success summary).
    # This is now a hard preflight error (ConfigValidationError -> exit 5)
    # raised BEFORE any ffmpeg work, not a warning.
    metadata_path = _make_colliding_metadata(tmp_path)
    with patch(
        "allaganeye.commands.export.export_matches",
        return_value=ExportSummary(success=2),
    ) as mock_export:
        result = runner.invoke(
            app,
            [
                "export",
                str(metadata_path),
                "--output-dir",
                str(tmp_path),
                "--codec",
                "copy",
                "--name-pattern",
                "{type}.mp4",  # no {idx}: both matches -> "match.mp4" (collision)
                "--quiet",
            ],
        )
    assert result.exit_code == 5  # ConfigValidationError.exit_code
    # export must NOT run (the error is raised before any ffmpeg work)
    mock_export.assert_not_called()
    assert "Traceback" not in result.output


def test_export_collision_json_emits_no_summary(app: typer.Typer, tmp_path: Path):
    # Finding 3 + P2-7: in --json mode the hard collision error must NOT emit a
    # summary line (start_export treats any summary line as success in lib.rs).
    metadata_path = _make_colliding_metadata(tmp_path)
    with patch(
        "allaganeye.commands.export.export_matches",
        return_value=ExportSummary(success=2),
    ) as mock_export:
        result = runner.invoke(
            app,
            [
                "export",
                str(metadata_path),
                "--output-dir",
                str(tmp_path),
                "--codec",
                "copy",
                "--name-pattern",
                "{type}.mp4",  # collision
                "--json",
            ],
        )
    assert result.exit_code == 5
    mock_export.assert_not_called()
    # no summary line on stdout (the error is the only wire signal)
    assert '"type": "summary"' not in result.stdout
    assert '"type":"summary"' not in result.stdout


def test_export_no_collision_warning_when_pattern_has_idx(
    app: typer.Typer, tmp_path: Path
):
    # P3 I-3: no warning when the pattern contains {idx} (all names are distinct).
    metadata_path = _make_metadata(tmp_path)
    with patch(
        "allaganeye.commands.export.export_matches",
        return_value=ExportSummary(success=2),
    ):
        result = runner.invoke(
            app,
            [
                "export",
                str(metadata_path),
                "--output-dir",
                str(tmp_path),
                "--codec",
                "copy",
                "--name-pattern",
                "{idx:03}_{type}.mp4",
                "--quiet",
            ],
        )
    assert result.exit_code == 0
    # no collision warning
    full_output = result.output + (result.stderr or "")
    assert "duplicate" not in full_output.lower()


def test_export_concurrency_zero_is_rejected(app: typer.Typer, tmp_path: Path):
    # P3 I-2: --concurrency 0 must be rejected with BadParameter (exit 2) before
    # any ffmpeg is launched. Negative values must be rejected too.
    metadata_path = _make_metadata(tmp_path)
    for bad_val in ("0", "-1", "-99"):
        result = runner.invoke(
            app,
            [
                "export",
                str(metadata_path),
                "--output-dir",
                str(tmp_path),
                "--codec",
                "h264",
                "--concurrency",
                bad_val,
                "--quiet",
            ],
        )
        assert result.exit_code == 2, (
            f"--concurrency {bad_val} should exit 2 (BadParameter), got {result.exit_code}"
        )


def test_export_include_help_mentions_1_based(app: typer.Typer):
    # P3 I-4 (a): --include/--exclude help text must mention 1-based indexes so
    # users don't confuse them with 0-based array positions.
    result = runner.invoke(app, ["export", "--help"])
    assert result.exit_code == 0
    help_text = result.output
    assert "1-based" in help_text


def test_export_include_out_of_range_warns(app: typer.Typer, tmp_path: Path):
    # P3 I-4 (b): --include 99 (no such match in metadata) should warn on stderr.
    metadata_path = _make_metadata(tmp_path)  # matches: index 0, 1
    with patch(
        "allaganeye.commands.export.export_matches",
        return_value=ExportSummary(success=0),
    ):
        result = runner.invoke(
            app,
            [
                "export",
                str(metadata_path),
                "--output-dir",
                str(tmp_path),
                "--codec",
                "copy",
                "--include",
                "99",  # no match has index 99
                "--quiet",
            ],
        )
    assert result.exit_code == 0  # warning only, not an error
    assert "warning" in result.output.lower()
    assert "99" in result.output


def test_export_exclude_out_of_range_warns(app: typer.Typer, tmp_path: Path):
    # P3 I-4 (b): --exclude 99 (no such match) should warn on stderr.
    metadata_path = _make_metadata(tmp_path)  # matches: index 0, 1
    with patch(
        "allaganeye.commands.export.export_matches",
        return_value=ExportSummary(success=2),
    ):
        result = runner.invoke(
            app,
            [
                "export",
                str(metadata_path),
                "--output-dir",
                str(tmp_path),
                "--codec",
                "copy",
                "--exclude",
                "99",  # no match has index 99
                "--quiet",
            ],
        )
    assert result.exit_code == 0  # warning only
    assert "warning" in result.output.lower()
    assert "99" in result.output


def test_load_metadata_stdin_invalid_utf8_raises_unicode_decode_error(
    monkeypatch: pytest.MonkeyPatch,
):
    # Round 1 FIX 1 (a): _load_metadata(--stdin) reads sys.stdin.buffer as bytes
    # and decodes UTF-8. Invalid bytes must raise UnicodeDecodeError (a ValueError
    # subclass, NOT OSError/JSONDecodeError) so the command can map it to exit 2.
    from allaganeye.commands.export import _load_metadata

    bad_bytes = b"\xff\xfe\x00\x80not utf-8"

    class _FakeStdin:
        buffer = io.BytesIO(bad_bytes)

    monkeypatch.setattr("allaganeye.commands.export.sys.stdin", _FakeStdin())
    with pytest.raises(UnicodeDecodeError):
        _load_metadata(None, use_stdin=True)


def test_export_stdin_invalid_utf8_exits_2(app: typer.Typer, tmp_path: Path):
    # Round 1 FIX 1 (a): the --stdin decode failure (UnicodeDecodeError) must map
    # to exit 2 with a clean stderr, NOT escape as a raw traceback / exit 1.
    bad_bytes = b"\xff\xfe\x00\x80not utf-8"
    result = runner.invoke(
        app,
        [
            "export",
            "--stdin",
            "--output-dir",
            str(tmp_path),
            "--codec",
            "copy",
            "--quiet",
        ],
        input=bad_bytes,
    )
    assert result.exit_code == 2, result.output
    assert "Traceback" not in result.output


def test_export_metadata_missing_index_exits_2(app: typer.Typer, tmp_path: Path):
    # Round 1 FIX 1 (b): a match missing the required "index" key raises KeyError
    # in the filter loop (which runs BEFORE the P2-7 frame). It must map to exit 2
    # with a clean stderr, not escape as a raw traceback / exit 1.
    payload = {
        "schema_version": "1",
        "source": str(tmp_path / "in.mp4"),
        "matches": [
            {"start_time": 0.0, "end_time": 10.0, "type": "match"},  # no "index"
        ],
        "system_info": {
            "gpu_vendors_available": [],
            "vendor_preference": ["nvidia"],
            "gpu": [],
        },
    }
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "export",
            str(metadata_path),
            "--output-dir",
            str(tmp_path),
            "--codec",
            "copy",
            "--quiet",
        ],
    )
    assert result.exit_code == 2, result.output
    assert "Traceback" not in result.output


def test_export_metadata_non_numeric_start_time_exits_2(
    app: typer.Typer, tmp_path: Path
):
    # Round 1 FIX 1 (b): a non-numeric "start_time" raises ValueError in the
    # filter loop (before the P2-7 frame). It must map to exit 2 with a clean
    # stderr, not escape as a raw traceback / exit 1.
    payload = {
        "schema_version": "1",
        "source": str(tmp_path / "in.mp4"),
        "matches": [
            {
                "index": 0,
                "start_time": "not-a-number",
                "end_time": 10.0,
                "type": "match",
            },
        ],
        "system_info": {
            "gpu_vendors_available": [],
            "vendor_preference": ["nvidia"],
            "gpu": [],
        },
    }
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "export",
            str(metadata_path),
            "--output-dir",
            str(tmp_path),
            "--codec",
            "copy",
            "--quiet",
        ],
    )
    assert result.exit_code == 2, result.output
    assert "Traceback" not in result.output


# ---------------------------------------------------------------------------
# B1: --name-pattern sandbox (data loss)
#
# Preflight layer: reject BEFORE mkdir / export_matches so a rejected run
# leaves the filesystem completely untouched. export_matches is mocked in these
# tests on purpose -- that bypasses the pool's own guard and therefore pins the
# CLI preflight itself (both layers are required; neither is redundant).
# ---------------------------------------------------------------------------


def _make_sandbox_metadata(
    tmp_path: Path, *, source: Path | None = None, type_label: str = "match"
) -> Path:
    src = source or (tmp_path / "in.mp4")
    if not src.exists():
        src.write_bytes(b"SOURCE")
    payload = {
        "schema_version": "1",
        "source": str(src),
        "matches": [
            {"index": 1, "start_time": 0.0, "end_time": 10.0, "type": type_label},
        ],
        "system_info": {
            "gpu_vendors_available": [],
            "vendor_preference": ["nvidia"],
            "gpu": [],
        },
    }
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")
    return metadata_path


@pytest.mark.parametrize(
    "pattern",
    ["../victim.mp4", "../../victim.mp4", "sub/../../victim.mp4"],
)
def test_export_rejects_name_pattern_escaping_output_dir(
    app: typer.Typer, tmp_path: Path, pattern: str
):
    metadata_path = _make_sandbox_metadata(tmp_path)
    victim = tmp_path / "victim.mp4"
    victim.write_bytes(b"VICTIM")
    out_dir = tmp_path / "outdir"
    with patch(
        "allaganeye.commands.export.export_matches",
        return_value=ExportSummary(success=1),
    ) as mock_export:
        result = runner.invoke(
            app,
            [
                "export",
                str(metadata_path),
                "--output-dir",
                str(out_dir),
                "--codec",
                "copy",
                "--name-pattern",
                pattern,
                "--quiet",
            ],
        )
    assert result.exit_code == 5, result.output
    mock_export.assert_not_called()
    assert victim.read_bytes() == b"VICTIM"
    # rejected before mkdir: no stray output dir left behind
    assert not out_dir.exists()
    assert "Traceback" not in result.output


def test_export_rejects_absolute_name_pattern(app: typer.Typer, tmp_path: Path):
    metadata_path = _make_sandbox_metadata(tmp_path)
    victim = tmp_path / "victim.mp4"
    victim.write_bytes(b"VICTIM")
    with patch(
        "allaganeye.commands.export.export_matches",
        return_value=ExportSummary(success=1),
    ) as mock_export:
        result = runner.invoke(
            app,
            [
                "export",
                str(metadata_path),
                "--output-dir",
                str(tmp_path / "outdir"),
                "--codec",
                "copy",
                "--name-pattern",
                str(victim),  # absolute -> ignores -o entirely
                "--quiet",
            ],
        )
    assert result.exit_code == 5, result.output
    mock_export.assert_not_called()
    assert victim.read_bytes() == b"VICTIM"


def test_export_rejects_name_pattern_hitting_source_video(
    app: typer.Typer, tmp_path: Path
):
    """-o pointed at the source's own directory must not overwrite the source."""
    source = tmp_path / "in.mp4"
    source.write_bytes(b"SOURCE")
    metadata_path = _make_sandbox_metadata(tmp_path, source=source)
    with patch(
        "allaganeye.commands.export.export_matches",
        return_value=ExportSummary(success=1),
    ) as mock_export:
        result = runner.invoke(
            app,
            [
                "export",
                str(metadata_path),
                "--output-dir",
                str(tmp_path),
                "--codec",
                "copy",
                "--name-pattern",
                "in.mp4",
                "--quiet",
            ],
        )
    assert result.exit_code == 5, result.output
    mock_export.assert_not_called()
    assert source.read_bytes() == b"SOURCE"


def test_export_rejects_escape_via_metadata_type_token(
    app: typer.Typer, tmp_path: Path
):
    """The escape can be supplied by metadata.json, not by the pattern.

    The {type} token is copied verbatim from metadata, so a pattern that
    carries {idx:03} and no separator still escapes -- pattern-string
    validation cannot see this.
    """
    metadata_path = _make_sandbox_metadata(tmp_path, type_label="../../../victim")
    with patch(
        "allaganeye.commands.export.export_matches",
        return_value=ExportSummary(success=1),
    ) as mock_export:
        result = runner.invoke(
            app,
            [
                "export",
                str(metadata_path),
                "--output-dir",
                str(tmp_path / "outdir"),
                "--codec",
                "copy",
                "--name-pattern",
                "{idx:03}_{type}.mp4",
                "--quiet",
            ],
        )
    assert result.exit_code == 5, result.output
    mock_export.assert_not_called()


def test_export_sandbox_reject_json_emits_no_summary(app: typer.Typer, tmp_path: Path):
    """--json: the rejection must NOT emit a summary line.

    lib.rs start_export treats any summary line as success, so emitting one
    here would show the GUI a successful export that never ran (same contract
    as the collision guard).
    """
    metadata_path = _make_sandbox_metadata(tmp_path)
    with patch(
        "allaganeye.commands.export.export_matches",
        return_value=ExportSummary(success=1),
    ) as mock_export:
        result = runner.invoke(
            app,
            [
                "export",
                str(metadata_path),
                "--output-dir",
                str(tmp_path / "outdir"),
                "--codec",
                "copy",
                "--name-pattern",
                "../victim.mp4",
                "--json",
            ],
        )
    assert result.exit_code == 5
    mock_export.assert_not_called()
    assert '"type": "summary"' not in result.stdout
    assert '"type":"summary"' not in result.stdout


def test_export_normal_name_pattern_still_allowed(app: typer.Typer, tmp_path: Path):
    """Reverse pin: an ordinary pattern is untouched by the sandbox guard."""
    metadata_path = _make_sandbox_metadata(tmp_path)
    out_dir = tmp_path / "outdir"
    with patch(
        "allaganeye.commands.export.export_matches",
        return_value=ExportSummary(success=1),
    ) as mock_export:
        result = runner.invoke(
            app,
            [
                "export",
                str(metadata_path),
                "--output-dir",
                str(out_dir),
                "--codec",
                "copy",
                "--name-pattern",
                "{idx:03}_{type}_{start}.mp4",
                "--quiet",
            ],
        )
    assert result.exit_code == 0, result.output
    mock_export.assert_called_once()
    assert out_dir.exists()


# --------------------------------------------------------------------------
# Output *identity* collisions (#930 follow-up).
#
# The sandbox guard above asks "does this land inside -o?". This section asks
# the separate question "do two matches land on the SAME file?". A string-keyed
# duplicate check answers it wrongly: two different strings can denote one
# file, so both matches were written and one was silently lost while the
# summary still reported success.
# --------------------------------------------------------------------------


def _make_identity_colliding_metadata(tmp_path: Path, type_a: str, type_b: str) -> Path:
    """2 matches whose ``{type}`` values render to one file under ``{type}.mp4``."""
    payload = {
        "schema_version": "1",
        "source": str(tmp_path / "in.mp4"),
        "matches": [
            {"index": 0, "start_time": 0.0, "end_time": 10.0, "type": type_a},
            {"index": 1, "start_time": 10.0, "end_time": 20.0, "type": type_b},
        ],
        "system_info": {
            "gpu_vendors_available": [],
            "vendor_preference": ["nvidia"],
            "gpu": [],
        },
    }
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _invoke_export_with_types(
    app: typer.Typer, tmp_path: Path, type_a: str, type_b: str, pattern: str
):
    metadata_path = _make_identity_colliding_metadata(tmp_path, type_a, type_b)
    with patch(
        "allaganeye.commands.export.export_matches",
        return_value=ExportSummary(success=2),
    ) as mock_export:
        result = runner.invoke(
            app,
            [
                "export",
                str(metadata_path),
                "--output-dir",
                str(tmp_path / "outdir"),
                "--codec",
                "copy",
                "--name-pattern",
                pattern,
                "--quiet",
            ],
        )
    return result, mock_export


@pytest.mark.skipif(
    sys.platform != "win32", reason="path identity is case-insensitive on Windows only"
)
def test_export_rejects_case_only_identity_collision(app: typer.Typer, tmp_path: Path):
    """'Clip.mp4' vs 'clip.mp4': distinct strings, one file on NTFS."""
    result, mock_export = _invoke_export_with_types(
        app, tmp_path, "Clip", "clip", "{type}.mp4"
    )
    assert result.exit_code == 5, result.output
    mock_export.assert_not_called()
    assert "Traceback" not in result.output


def test_export_rejects_dotdot_identity_collision(app: typer.Typer, tmp_path: Path):
    """'sub/../clip.mp4' stays inside -o yet denotes 'clip.mp4'."""
    result, mock_export = _invoke_export_with_types(
        app, tmp_path, "sub/../clip", "clip", "{type}.mp4"
    )
    assert result.exit_code == 5, result.output
    mock_export.assert_not_called()
    assert "Traceback" not in result.output


@pytest.mark.parametrize(
    ("type_a", "type_b"),
    [("Clip", "clip"), ("sub/../clip", "clip")],
)
def test_export_allows_identity_pairs_once_idx_disambiguates(
    app: typer.Typer, tmp_path: Path, type_a: str, type_b: str
):
    """Control: those ``{type}`` values are legal; only the collision is not.

    Without this the two tests above could be passing for an unrelated
    reason (a rejected token, a parse error) and would still be green on the
    unfixed code.
    """
    result, mock_export = _invoke_export_with_types(
        app, tmp_path, type_a, type_b, "{idx:03}_{type}.mp4"
    )
    assert result.exit_code == 0, result.output
    mock_export.assert_called_once()
