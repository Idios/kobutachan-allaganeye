"""KO / ASSIST 検出のパイプライン統合 (#1141).

`detect --indicators` / `split --indicators` が

* 境界とイベントを **1 回の atomic write** で書く
* 検出に失敗しても境界の結果を失わず `warnings[]` に記録する
* `--progress-format json` に `phase: "indicators"` を出す
* `split --from-metadata` で `indicator_layout` / `events` を落とさない

を pin する。走査そのもの (実フレーム) は `test_indicators*.py` が見る。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from allaganeye.cli import app as cli_app
from allaganeye.commands.detect import run_detect
from allaganeye.commands.split_matches import run_split, run_split_from_metadata
from allaganeye.config import SplitConfig
from allaganeye.detection.indicator_stage import IndicatorRun, StageNotice
from allaganeye.exceptions import DetectionError
from allaganeye.video.detector import MatchBoundary
from allaganeye.video.probe import ProbeResult

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
    {"start": 0.0, "end": 600.0, "type": "fl_match"},
    {"start": 610.0, "end": 1200.0, "type": "fl_match"},
]

LAYOUT = {
    "anchor_x": 0.32,
    "anchor_y": 0.57,
    "scale": 1.0,
    "support": 6,
    "confidence": 0.95,
    "source": "anchor",
}

EVENTS = [
    {
        "signal_id": "ko_indicator",
        "timestamp": 100.0,
        "end": 101.0,
        "score": 0.91,
        "evidence": {"samples": 3},
        "match_index": 1,
    },
    {
        "signal_id": "assist_indicator",
        "timestamp": 200.0,
        "end": 201.0,
        "score": 0.88,
        "evidence": {"samples": 4},
        "match_index": 1,
    },
]

MODULE_DETECT = "allaganeye.commands.detect"
MODULE_SPLIT = "allaganeye.commands.split_matches"
MODULE_STAGE = "allaganeye.detection.indicator_stage"

runner = CliRunner()


def _run(events: list[dict[str, object]] | None = None) -> IndicatorRun:
    return IndicatorRun(layout=dict(LAYOUT), events=[dict(e) for e in (events or EVENTS)])


def _fake_stage(result: IndicatorRun | None = None, *, notices: bool = True):
    """`detect_indicator_events` の差し替え。実フレームを読まずに結線だけ見る。"""
    run = result if result is not None else _run()

    def fake(
        source: Path,
        payload: dict[str, object],
        *,
        notice=None,
        progress=None,
        **_kwargs,
    ):
        if notices:
            if notice is not None:
                notice(StageNotice(kind="calibrating"))
                notice(
                    StageNotice(
                        kind="progress", processed_s=900.0, total_s=1800.0, eta_s=12.0
                    )
                )
            if progress is not None:
                progress("reused indicator_layout from metadata.json")
        return run

    return fake


@pytest.fixture(autouse=True)
def _mock_audio_scan():
    with patch(f"{MODULE_SPLIT}._run_audio_scan", return_value=None) as m:
        yield m


def _read(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))


# --- detect -----------------------------------------------------------------


def test_detect_without_indicators_writes_no_event_fields(tmp_path):
    """既定 (OFF) では events / indicator_layout を書かない。"""
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    with (
        patch(f"{MODULE_DETECT}.probe_video", return_value=PROBE_RESULT),
        patch(f"{MODULE_DETECT}._run_detection", return_value=BOUNDARIES),
        patch(f"{MODULE_STAGE}.detect_indicator_events", side_effect=AssertionError),
    ):
        run_detect(Path("input.mp4"), config, quiet=True)

    payload = _read(tmp_path)
    assert "events" not in payload
    assert "indicator_layout" not in payload


def test_detect_indicators_writes_layout_and_events_in_one_write(tmp_path):
    """境界とイベントが同じ payload / 同じ 1 回の write に載る (受け入れ条件 2)。"""
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    writes: list[dict] = []
    real_write = __import__(
        "allaganeye.detection.metadata_writer", fromlist=["write_metadata_atomic"]
    ).write_metadata_atomic

    def spy(path: Path, payload: dict) -> None:
        writes.append(dict(payload))
        real_write(path, payload)

    with (
        patch(f"{MODULE_DETECT}.probe_video", return_value=PROBE_RESULT),
        patch(f"{MODULE_DETECT}._run_detection", return_value=BOUNDARIES),
        patch(f"{MODULE_STAGE}.detect_indicator_events", new=_fake_stage()),
        patch(f"{MODULE_DETECT}.write_metadata_atomic", side_effect=spy),
    ):
        run_detect(Path("input.mp4"), config, quiet=True, indicators=True)

    assert len(writes) == 1, "metadata.json は 1 回だけ書く (atomic write 1 回)"
    assert writes[0]["events"] == EVENTS
    assert writes[0]["indicator_layout"] == LAYOUT
    assert len(writes[0]["matches"]) == len(BOUNDARIES)
    assert _read(tmp_path)["events"] == EVENTS


def test_detect_indicators_failure_keeps_boundaries_and_records_warning(tmp_path):
    """検出に失敗しても境界は残し、warnings[] に記録する (受け入れ条件 3)。"""
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    with (
        patch(f"{MODULE_DETECT}.probe_video", return_value=PROBE_RESULT),
        patch(f"{MODULE_DETECT}._run_detection", return_value=BOUNDARIES),
        patch(
            f"{MODULE_STAGE}.detect_indicator_events",
            side_effect=DetectionError("calibration failed"),
        ),
    ):
        run_detect(Path("input.mp4"), config, quiet=True, indicators=True)

    payload = _read(tmp_path)
    assert len(payload["matches"]) == len(BOUNDARIES)
    assert "events" not in payload
    codes = [warning["code"] for warning in payload["warnings"]]
    assert codes == ["indicators_failed"]
    assert payload["warnings"][0]["severity"] == "warn"


def test_detect_indicators_emits_json_phase(capsys, tmp_path):
    """`--progress-format json` に `phase: "indicators"` と eta_s を出す。"""
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    with (
        patch(f"{MODULE_DETECT}.probe_video", return_value=PROBE_RESULT),
        patch(f"{MODULE_DETECT}._run_detection", return_value=BOUNDARIES),
        patch(f"{MODULE_STAGE}.detect_indicator_events", new=_fake_stage()),
    ):
        run_detect(
            Path("input.mp4"),
            config,
            quiet=True,
            progress_format="json",
            indicators=True,
        )

    lines = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("{")
    ]
    indicator_lines = [line for line in lines if line.get("phase") == "indicators"]
    assert indicator_lines, "phase=indicators の行が出ていない"
    assert indicator_lines[0]["completed"] == 0
    assert indicator_lines[0]["total"] == int(PROBE_RESULT["duration"])
    progress_lines = [line for line in indicator_lines if line.get("eta_s")]
    assert progress_lines[0]["completed"] == 900
    assert progress_lines[0]["eta_s"] == 12.0


@pytest.mark.parametrize(("use_gpu", "expected"), [(True, True), (False, False)])
def test_detect_indicators_passes_explicit_gpu_only(tmp_path, use_gpu, expected):
    """GPU は明示指定 (--gpu) のときだけステージへ渡す (opt-in)。"""
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0, use_gpu=use_gpu)
    seen: dict[str, object] = {}

    def fake(source, payload, **kwargs):
        seen.update(kwargs)
        return _run()

    with (
        patch(f"{MODULE_DETECT}.probe_video", return_value=PROBE_RESULT),
        patch(f"{MODULE_DETECT}._run_detection", return_value=BOUNDARIES),
        patch(
            f"{MODULE_DETECT}._resolve_gpu_mode_with_probe",
            return_value=(use_gpu, "nvidia" if use_gpu else None, ["nvidia"]),
        ),
        patch("allaganeye.system_info.probe_gpu_vendors", return_value=["nvidia"]),
        patch(f"{MODULE_STAGE}.detect_indicator_events", new=fake),
    ):
        run_detect(Path("input.mp4"), config, quiet=True, indicators=True)

    assert seen["gpu"] is expected


# --- split ------------------------------------------------------------------


@pytest.fixture
def split_mocks():
    with (
        patch(f"{MODULE_SPLIT}.probe_video", return_value=PROBE_RESULT),
        patch(f"{MODULE_SPLIT}.detect_match_boundaries", return_value=BOUNDARIES),
        patch(
            f"{MODULE_SPLIT}.split_video",
            return_value=[Path("match_001.mp4"), Path("match_002.mp4")],
        ),
    ):
        yield


def test_split_indicators_writes_events(tmp_path, split_mocks):
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    with patch(f"{MODULE_STAGE}.detect_indicator_events", new=_fake_stage()):
        run_split(Path("input.mp4"), config, quiet=True, indicators=True)

    payload = _read(tmp_path)
    assert payload["events"] == EVENTS
    assert payload["indicator_layout"] == LAYOUT


def test_split_without_indicators_writes_no_event_fields(tmp_path, split_mocks):
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    run_split(Path("input.mp4"), config, quiet=True)

    payload = _read(tmp_path)
    assert "events" not in payload
    assert "indicator_layout" not in payload


def test_split_from_metadata_preserves_events_and_layout(tmp_path):
    """`detect --indicators` の結果を `--from-metadata` が落とさない。"""
    source = tmp_path / "input.mp4"
    source.write_bytes(b"")
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "source": str(source),
                "source_duration": PROBE_RESULT["duration"],
                "source_fps": PROBE_RESULT["fps"],
                "detected_at": "2026-11-18T00:00:00Z",
                "matches": [
                    {
                        "index": 1,
                        "start_time": 0.0,
                        "end_time": 600.0,
                        "duration": 600.0,
                        "type": "fl_match",
                        "output_file": "match_001.mp4",
                    }
                ],
                "gaps": [],
                "warnings": [],
                "indicator_layout": LAYOUT,
                "events": EVENTS,
            }
        ),
        encoding="utf-8",
    )
    config = SplitConfig(output_dir=tmp_path / "out", min_match_duration=60.0)
    with (
        patch(f"{MODULE_SPLIT}.probe_video", return_value=PROBE_RESULT),
        patch(
            f"{MODULE_SPLIT}.split_video",
            return_value=[tmp_path / "out" / "match_001.mp4"],
        ),
    ):
        run_split_from_metadata(metadata_path, config, quiet=True)

    fresh = json.loads((tmp_path / "out" / "metadata.json").read_text("utf-8"))
    assert fresh["events"] == EVENTS
    assert fresh["indicator_layout"] == LAYOUT


# --- CLI --------------------------------------------------------------------


def test_cli_rejects_indicators_with_from_metadata(tmp_path):
    meta = tmp_path / "metadata.json"
    meta.write_text("{}", encoding="utf-8")
    result = runner.invoke(
        cli_app,
        ["split", "--from-metadata", str(meta), "--indicators"],
    )
    assert result.exit_code == 5
    assert "--indicators is not compatible with --from-metadata" in result.output


def test_cli_detect_accepts_both_indicator_flags():
    """`--indicators` / `--no-indicators` の両形がヘルプに載る (既定 OFF)。"""
    result = runner.invoke(cli_app, ["detect", "--help"])
    assert result.exit_code == 0
    assert "--indicators" in result.output
    assert "--no-indicators" in result.output


# --- Codex adversarial-review (2026-11-18) の P2 3 件の regression pin --------


def test_detect_emits_writing_metadata_after_the_indicator_stage(capsys, tmp_path):
    """`writing_metadata` は走査の**後**に出す (codex P2 #1)。

    先に出すと GUI の進捗が 99% で頭打ちになり、indicators 帯 (97-99%) の
    更新が捨てられる (bar は単調増加)。
    """
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    with (
        patch(f"{MODULE_DETECT}.probe_video", return_value=PROBE_RESULT),
        patch(f"{MODULE_DETECT}._run_detection", return_value=BOUNDARIES),
        patch(f"{MODULE_STAGE}.detect_indicator_events", new=_fake_stage()),
    ):
        run_detect(
            Path("input.mp4"),
            config,
            quiet=True,
            progress_format="json",
            indicators=True,
        )

    phases = [
        json.loads(line)["phase"]
        for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("{")
    ]
    assert "indicators" in phases and "writing_metadata" in phases
    assert phases.index("writing_metadata") > max(
        index for index, phase in enumerate(phases) if phase == "indicators"
    )


def test_detect_counts_the_indicator_scan_in_detection_completed_at(tmp_path):
    """走査の所要を `detection_completed_at` に含める (codex P2 #3)。"""
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    stamps = [
        "2026-11-18T00:00:00Z",  # detected_at
        "2026-11-18T00:00:01Z",  # payload 組み立て時
        "2026-11-18T00:05:00Z",  # 走査後 (これが書かれる)
    ]
    with (
        patch(f"{MODULE_DETECT}.probe_video", return_value=PROBE_RESULT),
        patch(f"{MODULE_DETECT}._run_detection", return_value=BOUNDARIES),
        patch(f"{MODULE_DETECT}._iso_utc_now", side_effect=stamps),
        patch(f"{MODULE_STAGE}.detect_indicator_events", new=_fake_stage()),
    ):
        run_detect(Path("input.mp4"), config, quiet=True, indicators=True)

    payload = _read(tmp_path)
    assert payload["detection_started_at"] == stamps[0]
    assert payload["detection_completed_at"] == stamps[2]


def test_split_counts_the_indicator_scan_in_detection_completed_at(
    tmp_path, split_mocks
):
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    stamps = [
        "2026-11-18T00:00:00Z",  # detected_at
        "2026-11-18T00:00:01Z",  # payload 組み立て時
        "2026-11-18T00:05:00Z",  # 走査後 (これが書かれる)
    ]
    with (
        patch(f"{MODULE_SPLIT}._iso_utc_now", side_effect=stamps),
        patch(f"{MODULE_STAGE}.detect_indicator_events", new=_fake_stage()),
    ):
        run_split(Path("input.mp4"), config, quiet=True, indicators=True)

    payload = _read(tmp_path)
    assert payload["detection_completed_at"] == stamps[2]


def test_split_from_metadata_drops_malformed_indicator_fields(tmp_path):
    """壊れた `events` / `indicator_layout` は新ファイルに持ち込まない (codex P2 #2)。

    1 フィールドの不正で GUI の zod が metadata.json 全体を拒否し、健全な
    境界結果まで読めなくなるため、preserve 時に sanitize する。
    """
    source = tmp_path / "input.mp4"
    source.write_bytes(b"")
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "source": str(source),
                "source_duration": PROBE_RESULT["duration"],
                "source_fps": PROBE_RESULT["fps"],
                "detected_at": "2026-11-18T00:00:00Z",
                "matches": [
                    {
                        "index": 1,
                        "start_time": 0.0,
                        "end_time": 600.0,
                        "duration": 600.0,
                        "type": "fl_match",
                        "output_file": "match_001.mp4",
                    }
                ],
                "gaps": [],
                "warnings": [],
                "indicator_layout": {},
                "events": [{}, {"signal_id": "ko_indicator"}],
            }
        ),
        encoding="utf-8",
    )
    config = SplitConfig(output_dir=tmp_path / "out", min_match_duration=60.0)
    with (
        patch(f"{MODULE_SPLIT}.probe_video", return_value=PROBE_RESULT),
        patch(
            f"{MODULE_SPLIT}.split_video",
            return_value=[tmp_path / "out" / "match_001.mp4"],
        ),
    ):
        run_split_from_metadata(metadata_path, config, quiet=True)

    fresh = json.loads((tmp_path / "out" / "metadata.json").read_text("utf-8"))
    assert "indicator_layout" not in fresh
    assert "events" not in fresh
    assert len(fresh["matches"]) == 1
