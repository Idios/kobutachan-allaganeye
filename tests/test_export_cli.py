"""Tests for 'allaganeye export' CLI (#761)."""

from __future__ import annotations

import io
import json
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
    non_ascii_source = str(tmp_path / "録画" / "試合.mp4")
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


def test_export_warns_on_filename_collision(app: typer.Typer, tmp_path: Path):
    # P3 I-3: a name pattern without {idx}/{idx:03} maps every match to the same
    # filename, silently overwriting. export should warn on stderr.
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
                "{type}.mp4",  # no {idx}: both matches → "match.mp4" (collision)
                "--quiet",
            ],
        )
    # warning goes to stderr; command can still succeed
    assert result.exit_code == 0
    assert "warning" in result.output.lower() or "warning" in (result.stderr or "").lower()


def test_export_no_collision_warning_when_pattern_has_idx(app: typer.Typer, tmp_path: Path):
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
