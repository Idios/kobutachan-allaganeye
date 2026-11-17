"""`allaganeye clips` の CLI テスト (#135 / #1050 Phase A)。

ffmpeg は起動せず、`export_matches` をスタブして「計画 -> 書き出し呼び出し」の
契約（出力先・範囲・codec・name pattern sandbox・exit code）だけを固定する。
実際のエンコードは `export` 側のテストと slow 検証が担う。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import typer
from typer.testing import CliRunner

from allaganeye.commands import clips as clips_cmd
from allaganeye.export.schema import ExportSummary, ProgressEvent

runner = CliRunner()

SOURCE_NAME = "recording.mp4"


@pytest.fixture
def app() -> typer.Typer:
    a = typer.Typer()

    @a.callback()
    def _() -> None:
        pass

    clips_cmd.register(a)
    return a


def _metadata(tmp_path: Path, events: list[dict[str, Any]] | None = None) -> Path:
    source = tmp_path / SOURCE_NAME
    source.write_bytes(b"not a real video")
    payload = {
        "schema_version": "1",
        "source": str(source),
        "source_duration": 900.0,
        "source_duration_display": "15:00",
        "detected_at": "2026-11-16T00:00:00Z",
        "detection_params": {"sample_interval": 2.0},
        "matches": [
            {"index": 1, "start_time": 100.0, "end_time": 400.0},
            {"index": 2, "start_time": 500.0, "end_time": 800.0},
        ],
        "gaps": [],
        "events": events
        if events is not None
        else [
            {
                "signal_id": "ko_indicator",
                "timestamp": 200.0,
                "end": 201.5,
                "score": 0.9,
                "evidence": {"samples": 15},
                "match_index": 1,
            },
            {
                "signal_id": "assist_indicator",
                "timestamp": 203.0,
                "end": 204.5,
                "score": 0.8,
                "evidence": {"samples": 15},
                "match_index": 1,
            },
            {
                "signal_id": "ko_indicator",
                "timestamp": 700.0,
                "end": 701.5,
                "score": 0.95,
                "evidence": {"samples": 15},
                "match_index": 2,
            },
        ],
    }
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class _Call:
    def __init__(self) -> None:
        self.matches: list[Any] = []
        self.output_dir: Path | None = None
        self.codec: str | None = None
        self.name_pattern: str | None = None
        self.slots: list[Any] = []
        self.source_video: Path | None = None


@pytest.fixture
def export_stub(monkeypatch: pytest.MonkeyPatch) -> _Call:
    call = _Call()

    def fake_export_matches(
        matches: list[Any],
        slots: list[Any],
        *,
        source_video: Path,
        output_dir: Path,
        codec: str,
        name_pattern: str,
        progress_cb: Any,
        cancel_event: Any,
    ) -> ExportSummary:
        call.matches = list(matches)
        call.slots = list(slots)
        call.output_dir = output_dir
        call.codec = codec
        call.name_pattern = name_pattern
        call.source_video = source_video
        for match in matches:
            progress_cb(
                ProgressEvent.result(
                    match.index,
                    output_dir / f"clip_{match.index:03d}.mp4",
                    12,
                    "copy" if codec == "copy" else "libx264",
                )
            )
        return ExportSummary(success=len(matches))

    monkeypatch.setattr(clips_cmd, "export_matches", fake_export_matches)
    return call


def test_clips_writes_one_clip_per_merged_group(
    app: typer.Typer, tmp_path: Path, export_stub: _Call
) -> None:
    metadata = _metadata(tmp_path)
    result = runner.invoke(app, ["clips", str(metadata)])
    assert result.exit_code == 0, result.output

    # 200 と 203 は gap 5 秒以内 -> 1 本、700 は別試合 -> 1 本
    assert [(m.start, m.end) for m in export_stub.matches] == [
        (190.0, 214.5),
        (690.0, 711.5),
    ]
    assert [m.type_label for m in export_stub.matches] == ["assist_ko", "ko"]
    assert export_stub.output_dir == metadata.parent / "clips"
    assert export_stub.codec == "copy"
    assert export_stub.name_pattern == clips_cmd.DEFAULT_NAME_PATTERN
    assert export_stub.source_video == tmp_path / SOURCE_NAME
    # copy は 1 スロットに絞る
    assert len(export_stub.slots) == 1
    assert "[OK] clip 001" in result.output
    assert "00:03:10-00:03:34" in result.output


def test_clips_respects_pre_post_and_gap(
    app: typer.Typer, tmp_path: Path, export_stub: _Call
) -> None:
    metadata = _metadata(tmp_path)
    result = runner.invoke(
        app,
        ["clips", str(metadata), "--pre", "2", "--post", "3", "--gap", "100"],
    )
    assert result.exit_code == 0, result.output
    # gap 100 で同一試合の 2 件が 1 本、前後は指定値
    first = export_stub.matches[0]
    assert (first.start, first.end) == (198.0, 207.5)


def test_clips_output_dir_override(
    app: typer.Typer, tmp_path: Path, export_stub: _Call
) -> None:
    metadata = _metadata(tmp_path)
    out = tmp_path / "custom"
    result = runner.invoke(app, ["clips", str(metadata), "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert export_stub.output_dir == out


def test_clips_codec_h264_keeps_all_slots(
    app: typer.Typer, tmp_path: Path, export_stub: _Call
) -> None:
    metadata = _metadata(tmp_path)
    result = runner.invoke(
        app, ["clips", str(metadata), "--codec", "h264", "--concurrency", "2"]
    )
    assert result.exit_code == 0, result.output
    assert export_stub.codec == "h264"
    assert len(export_stub.slots) >= 1


def test_clips_requires_events(app: typer.Typer, tmp_path: Path) -> None:
    metadata = _metadata(tmp_path, events=[])
    result = runner.invoke(app, ["clips", str(metadata)])
    assert result.exit_code == 2
    assert "has no events" in result.output


def test_clips_missing_metadata_exits_2(app: typer.Typer, tmp_path: Path) -> None:
    result = runner.invoke(app, ["clips", str(tmp_path / "nope.json")])
    assert result.exit_code == 2


@pytest.mark.parametrize(
    "flags",
    [["--pre", "-1"], ["--post", "nan"], ["--gap", "inf"]],
)
def test_clips_rejects_invalid_numbers(
    app: typer.Typer, tmp_path: Path, export_stub: _Call, flags: list[str]
) -> None:
    metadata = _metadata(tmp_path)
    result = runner.invoke(app, ["clips", str(metadata), *flags])
    assert result.exit_code == 5
    assert export_stub.matches == []


def test_clips_rejects_unknown_codec(
    app: typer.Typer, tmp_path: Path, export_stub: _Call
) -> None:
    metadata = _metadata(tmp_path)
    result = runner.invoke(app, ["clips", str(metadata), "--codec", "av1"])
    assert result.exit_code == 5
    assert export_stub.matches == []


def test_clips_rejects_name_pattern_escape(
    app: typer.Typer, tmp_path: Path, export_stub: _Call
) -> None:
    metadata = _metadata(tmp_path)
    result = runner.invoke(
        app, ["clips", str(metadata), "--name-pattern", "../victim.mp4"]
    )
    assert result.exit_code == 5
    assert export_stub.matches == []


def test_clips_skips_events_outside_matches(
    app: typer.Typer, tmp_path: Path, export_stub: _Call
) -> None:
    metadata = _metadata(
        tmp_path,
        events=[
            {
                "signal_id": "ko_indicator",
                "timestamp": 50.0,
                "end": 51.0,
                "score": 0.9,
                "evidence": {},
                "match_index": None,
            },
            {
                "signal_id": "ko_indicator",
                "timestamp": 200.0,
                "end": 201.0,
                "score": 0.9,
                "evidence": {},
                "match_index": 1,
            },
        ],
    )
    result = runner.invoke(app, ["clips", str(metadata)])
    assert result.exit_code == 0, result.output
    assert "outside every match" in result.output
    assert len(export_stub.matches) == 1


def test_clips_reports_merged_events(
    app: typer.Typer, tmp_path: Path, export_stub: _Call
) -> None:
    metadata = _metadata(tmp_path)
    result = runner.invoke(app, ["clips", str(metadata)])
    assert result.exit_code == 0, result.output
    assert "merged into a neighbouring clip" in result.output


def test_clips_no_clip_runs_summary_without_export(
    app: typer.Typer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = False

    def fake_export_matches(*args: Any, **kwargs: Any) -> ExportSummary:
        nonlocal called
        called = True
        return ExportSummary()

    monkeypatch.setattr(clips_cmd, "export_matches", fake_export_matches)
    metadata = _metadata(
        tmp_path,
        events=[
            {
                "signal_id": "ko_indicator",
                "timestamp": 50.0,
                "end": 51.0,
                "score": 0.9,
                "evidence": {},
                "match_index": None,
            }
        ],
    )
    result = runner.invoke(app, ["clips", str(metadata)])
    assert result.exit_code == 0, result.output
    assert "no clips to write" in result.output
    assert called is False


def test_clips_json_mode_emits_wire_lines(
    app: typer.Typer, tmp_path: Path, export_stub: _Call
) -> None:
    metadata = _metadata(tmp_path)
    result = runner.invoke(app, ["clips", str(metadata), "--json"])
    assert result.exit_code == 0, result.output
    lines = [json.loads(line) for line in result.output.splitlines() if line.strip()]
    assert [line["type"] for line in lines] == ["result", "result", "summary"]
    assert lines[0]["match_index"] == 1
    assert lines[-1]["success"] == 2


def test_clips_failure_exits_1(
    app: typer.Typer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_export_matches(*args: Any, **kwargs: Any) -> ExportSummary:
        return ExportSummary(success=1, failure=1)

    monkeypatch.setattr(clips_cmd, "export_matches", fake_export_matches)
    metadata = _metadata(tmp_path)
    result = runner.invoke(app, ["clips", str(metadata)])
    assert result.exit_code == 1


def test_clips_cancel_exits_130(
    app: typer.Typer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_export_matches(*args: Any, **kwargs: Any) -> ExportSummary:
        return ExportSummary(success=0, cancelled=True)

    monkeypatch.setattr(clips_cmd, "export_matches", fake_export_matches)
    metadata = _metadata(tmp_path)
    result = runner.invoke(app, ["clips", str(metadata)])
    assert result.exit_code == 130


def test_clips_json_and_quiet_conflict(
    app: typer.Typer, tmp_path: Path, export_stub: _Call
) -> None:
    metadata = _metadata(tmp_path)
    result = runner.invoke(app, ["clips", str(metadata), "--json", "--quiet"])
    assert result.exit_code == 2
    assert export_stub.matches == []


def test_clips_rejects_non_list_matches(
    app: typer.Typer, tmp_path: Path, export_stub: _Call
) -> None:
    """`matches: 1` のような壊れた metadata は入力エラー (exit 2) にする。"""
    metadata = _metadata(tmp_path)
    payload = json.loads(metadata.read_text(encoding="utf-8"))
    payload["matches"] = 1
    metadata.write_text(json.dumps(payload), encoding="utf-8")
    result = runner.invoke(app, ["clips", str(metadata)])
    assert result.exit_code == 2
    assert "'matches' must be a list" in result.output
    assert export_stub.matches == []


def test_clips_ignores_non_mapping_system_info(
    app: typer.Typer, tmp_path: Path, export_stub: _Call
) -> None:
    metadata = _metadata(tmp_path)
    payload = json.loads(metadata.read_text(encoding="utf-8"))
    payload["system_info"] = "junk"
    metadata.write_text(json.dumps(payload), encoding="utf-8")
    result = runner.invoke(app, ["clips", str(metadata)])
    assert result.exit_code == 0, result.output
    assert export_stub.matches


def test_clips_refuses_to_overwrite_existing_outputs(
    app: typer.Typer, tmp_path: Path, export_stub: _Call
) -> None:
    """再実行で前回のクリップを黙って壊さない (Codex review 2026-11-16)。"""
    metadata = _metadata(tmp_path)
    out = tmp_path / "clips"
    out.mkdir()
    (out / "clip_001_assist_ko_03-10.mp4").write_bytes(b"previous run")

    result = runner.invoke(app, ["clips", str(metadata)])

    assert result.exit_code == 5
    assert "--overwrite" in result.output
    assert export_stub.matches == []
    # 既存ファイルはそのまま残る
    assert (out / "clip_001_assist_ko_03-10.mp4").read_bytes() == b"previous run"


def test_clips_overwrite_flag_allows_replacement(
    app: typer.Typer, tmp_path: Path, export_stub: _Call
) -> None:
    metadata = _metadata(tmp_path)
    out = tmp_path / "clips"
    out.mkdir()
    (out / "clip_001_assist_ko_03-10.mp4").write_bytes(b"previous run")

    result = runner.invoke(app, ["clips", str(metadata), "--overwrite"])

    assert result.exit_code == 0, result.output
    assert export_stub.matches


@pytest.mark.parametrize(
    "system_info",
    [
        {"gpu_vendors_available": 1},
        {"gpu": [None]},
        {"vendor_preference": "nvidia"},
    ],
)
def test_clips_tolerates_malformed_system_info(
    app: typer.Typer, tmp_path: Path, export_stub: _Call, system_info: dict[str, Any]
) -> None:
    """壊れた `system_info` でもクラッシュせず計画どおり書き出す (Codex review)。"""
    metadata = _metadata(tmp_path)
    payload = json.loads(metadata.read_text(encoding="utf-8"))
    payload["system_info"] = system_info
    metadata.write_text(json.dumps(payload), encoding="utf-8")
    result = runner.invoke(app, ["clips", str(metadata), "--codec", "copy"])
    assert result.exit_code == 0, result.output
    assert export_stub.matches


def test_clips_reports_output_dir_creation_failure(
    app: typer.Typer, tmp_path: Path, export_stub: _Call
) -> None:
    """`-o` が既存ファイルを指すとき traceback ではなく exit 5 にする。"""
    metadata = _metadata(tmp_path)
    blocker = tmp_path / "not-a-dir"
    blocker.write_bytes(b"x")
    result = runner.invoke(app, ["clips", str(metadata), "-o", str(blocker)])
    assert result.exit_code == 5
    assert "cannot create output directory" in result.output
    assert export_stub.matches == []
