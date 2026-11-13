"""Tests for `allaganeye indicators` (#1106 作業項目 9)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import typer
from typer.testing import CliRunner

from allaganeye.commands import indicators as indicators_cmd
from allaganeye.commands.indicators import (
    DEFAULT_INTERVAL,
    IndicatorReport,
    calibration_timestamps,
    register,
)
from allaganeye.video.indicators import IndicatorLayout, layout_to_payload
from allaganeye.video.refs import load_templates

runner = CliRunner()

LAYOUT = IndicatorLayout(
    scale=1.0, x=618.0, y=614.0, support=6, confidence=0.95, source="anchor"
)
FRAME_SIZE = (1920, 1080)
DURATION = 3.0


@pytest.fixture
def app() -> typer.Typer:
    a = typer.Typer()

    @a.callback()
    def _() -> None:
        pass

    register(a)
    return a


@pytest.fixture
def metadata_path(tmp_path: Path) -> Path:
    """metadata.json + 実在する空の source video。"""
    video = tmp_path / "in.mp4"
    video.write_bytes(b"")
    payload = {
        "source": str(video),
        "source_duration": DURATION,
        "matches": [
            {
                "index": 1,
                "start_time": 0.0,
                "end_time": DURATION,
                "start_display": "0:00",
                "end_display": "0:03",
                "duration": DURATION,
                "duration_display": "0:03",
                "type": "frontline",
            }
        ],
        "indicator_layout": layout_to_payload(
            LAYOUT, frame_width=FRAME_SIZE[0], frame_height=FRAME_SIZE[1]
        ),
    }
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _frames_with_assist(
    times: list[float], *, hit_from: float, hit_to: float
) -> list[tuple[float, np.ndarray]]:
    """Build synthetic frames; paste the ASSISTED! template inside the hit window."""
    band = LAYOUT.text_band()
    template = load_templates()["assist"]
    frames = []
    for index, timestamp in enumerate(times):
        frame = np.random.default_rng(index).integers(
            0, 40, size=(1080, 1920), dtype=np.uint8
        )
        if hit_from <= timestamp <= hit_to:
            x = round(band.x0) + 60
            y = round(band.y0) + 6
            frame[y : y + template.shape[0], x : x + template.shape[1]] = template
        frames.append((timestamp, frame))
    return frames


@pytest.fixture
def fake_video(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        indicators_cmd,
        "probe_video",
        lambda _path: {
            "duration": DURATION,
            "width": FRAME_SIZE[0],
            "height": FRAME_SIZE[1],
            "fps": 30.0,
        },
    )
    times = [round(index * DEFAULT_INTERVAL, 2) for index in range(30)]
    frames = _frames_with_assist(times, hit_from=1.0, hit_to=1.4)
    monkeypatch.setattr(
        indicators_cmd, "iter_gray_frames", lambda *a, **k: iter(frames)
    )


def test_indicators_reports_events(app: typer.Typer, metadata_path: Path, fake_video):
    """キャッシュ済みレイアウトで走査し、ASSIST 区間を 1 件返す。"""
    result = runner.invoke(app, ["indicators", str(metadata_path), "--no-write"])
    assert result.exit_code == 0, result.output
    assert "KO: 0 / ASSIST: 1" in result.output
    assert "match 1" in result.output


def test_indicators_writes_events_json(
    app: typer.Typer, metadata_path: Path, fake_video, tmp_path: Path
):
    out = tmp_path / "events.json"
    result = runner.invoke(
        app, ["indicators", str(metadata_path), "--no-write", "-o", str(out)]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["recalibrated"] is False
    assert payload["events"][0]["kind"] == "assist"
    assert payload["events"][0]["match_index"] == 1
    assert payload["layout"]["anchor_x"] == pytest.approx(618.0 / 1920)


def test_indicators_json_mode_emits_lines(
    app: typer.Typer, metadata_path: Path, fake_video
):
    """`--json` は stdout に JSON Lines だけを出し、最後に complete を返す。"""
    result = runner.invoke(
        app, ["indicators", str(metadata_path), "--no-write", "--json"]
    )
    assert result.exit_code == 0, result.output
    lines = [json.loads(line) for line in result.output.splitlines() if line.strip()]
    assert lines[-1]["type"] == "complete"
    assert lines[-1]["events"][0]["kind"] == "assist"
    assert any(line.get("phase") == "scanning" for line in lines if "phase" in line)


def test_indicators_writes_layout_back(
    app: typer.Typer, metadata_path: Path, fake_video
):
    result = runner.invoke(app, ["indicators", str(metadata_path)])
    assert result.exit_code == 0, result.output
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert payload["indicator_layout"]["scale"] == pytest.approx(1.0)
    assert payload["indicator_layout"]["support"] == 6


def test_indicators_no_write_keeps_metadata_untouched(
    app: typer.Typer, metadata_path: Path, fake_video
):
    before = metadata_path.read_text(encoding="utf-8")
    result = runner.invoke(app, ["indicators", str(metadata_path), "--no-write"])
    assert result.exit_code == 0, result.output
    assert metadata_path.read_text(encoding="utf-8") == before


def test_indicators_calibrates_when_layout_missing(
    app: typer.Typer, metadata_path: Path, fake_video, monkeypatch: pytest.MonkeyPatch
):
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    del payload["indicator_layout"]
    metadata_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    monkeypatch.setattr(indicators_cmd, "calibrate_layout", lambda _frames: LAYOUT)
    result = runner.invoke(app, ["indicators", str(metadata_path), "--no-write"])
    assert result.exit_code == 0, result.output
    assert "ASSIST: 1" in result.output


def test_indicators_fails_when_calibration_fails(
    app: typer.Typer, metadata_path: Path, fake_video, monkeypatch: pytest.MonkeyPatch
):
    """解決できないときは「イベント 0 件」ではなく exit 4 で落とす。"""
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    del payload["indicator_layout"]
    metadata_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    monkeypatch.setattr(indicators_cmd, "calibrate_layout", lambda _frames: None)
    result = runner.invoke(app, ["indicators", str(metadata_path), "--no-write"])
    assert result.exit_code == 4
    assert "解決できませんでした" in result.output


def test_indicators_recalibrate_ignores_cache(
    app: typer.Typer, metadata_path: Path, fake_video, monkeypatch: pytest.MonkeyPatch
):
    calls = []

    def fake_calibrate(frames):
        calls.append(len(list(frames)))
        return LAYOUT

    monkeypatch.setattr(indicators_cmd, "calibrate_layout", fake_calibrate)
    result = runner.invoke(
        app, ["indicators", str(metadata_path), "--no-write", "--recalibrate"]
    )
    assert result.exit_code == 0, result.output
    assert calls


def test_indicators_rejects_invalid_interval(
    app: typer.Typer, metadata_path: Path, fake_video
):
    result = runner.invoke(
        app, ["indicators", str(metadata_path), "--interval", "0.01"]
    )
    assert result.exit_code == 5
    assert "--interval" in result.output


def test_indicators_missing_metadata_exits_2(app: typer.Typer, tmp_path: Path):
    result = runner.invoke(app, ["indicators", str(tmp_path / "nope.json")])
    assert result.exit_code == 2


def test_indicators_conflicting_mtime_exits_6(
    app: typer.Typer, metadata_path: Path, fake_video
):
    result = runner.invoke(
        app, ["indicators", str(metadata_path), "--expected-mtime", "1"]
    )
    assert result.exit_code == 6
    assert "changed on disk" in result.output


def test_indicators_rejects_corrupt_layout(
    app: typer.Typer, metadata_path: Path, fake_video
):
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload["indicator_layout"]["scale"] = 0
    metadata_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    result = runner.invoke(app, ["indicators", str(metadata_path), "--no-write"])
    assert result.exit_code == 2
    assert "scale" in result.output


# ---------------------------------------------------------------------------
# calibration_timestamps (pure)
# ---------------------------------------------------------------------------


def test_calibration_timestamps_prefers_match_centres() -> None:
    matches = [
        {"start_time": 10.0, "end_time": 20.0},
        {"start_time": 100.0, "end_time": 200.0},
    ]
    assert calibration_timestamps(matches, duration=300.0) == [15.0, 150.0]


def test_calibration_timestamps_caps_sample_count() -> None:
    matches = [
        {"start_time": float(index * 100), "end_time": float(index * 100 + 60)}
        for index in range(20)
    ]
    timestamps = calibration_timestamps(matches, duration=2000.0, samples=6)
    assert len(timestamps) == 6
    assert timestamps == sorted(timestamps)
    assert timestamps[0] < timestamps[-1]


def test_calibration_timestamps_falls_back_to_even_spacing() -> None:
    assert calibration_timestamps([], duration=700.0, samples=7) == [
        87.5,
        175.0,
        262.5,
        350.0,
        437.5,
        525.0,
        612.5,
    ]


def test_calibration_timestamps_skips_malformed_matches() -> None:
    matches = [{"start_time": 10.0}, {"start_time": 5.0, "end_time": 4.0}, "junk"]
    assert calibration_timestamps(matches, duration=100.0, samples=1) == [50.0]


def test_indicator_report_payload_shape() -> None:
    report = IndicatorReport(
        layout={"scale": 1.0},
        events=[{"kind": "ko"}],
        metadata_path=Path("metadata.json"),
        recalibrated=True,
    )
    payload = report.to_payload()
    assert payload["metadata"] == "metadata.json"
    assert payload["recalibrated"] is True
    assert payload["events"] == [{"kind": "ko"}]
