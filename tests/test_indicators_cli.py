"""Tests for `allaganeye indicators` (#1106 作業項目 9)."""

from __future__ import annotations

import json
import os
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
from allaganeye.exceptions import MetadataConflictError
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


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_indicators_rejects_non_finite_interval(
    app: typer.Typer, metadata_path: Path, fake_video, value: str
):
    """NaN / inf は `interval < MIN_INTERVAL` が False になるので別途弾く。

    素通りすると `fps=1/interval` が nan / 0.0 になり、ffmpeg の引数として
    意味不明な値が渡る (NaN はすべての比較が False なので下限判定をすり抜ける)。
    """
    result = runner.invoke(
        app, ["indicators", str(metadata_path), "--interval", value, "--no-write"]
    )
    assert result.exit_code == 5
    assert "--interval" in result.output


def test_indicators_reports_output_write_failure(
    app: typer.Typer, metadata_path: Path, fake_video, tmp_path: Path
):
    """`-o` の親がファイルで書けないとき、traceback ではなく exit 1 + メッセージ。"""
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    result = runner.invoke(
        app,
        ["indicators", str(metadata_path), "--no-write", "-o", str(blocker / "e.json")],
    )
    assert result.exit_code == 1
    assert "Cannot" in result.output


def test_indicators_cas_conflict_keeps_existing_report(
    app: typer.Typer,
    metadata_path: Path,
    fake_video,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """レポート公開前の 2 回目の CAS で落ちたら、既存レポートを置き換えない。

    公開を metadata write-back の後に回しているのはこのため。staging も残さない。
    """
    out = tmp_path / "events.json"
    out.write_text("KEEP\n", encoding="utf-8")
    calls = {"count": 0}

    def guard(_path: Path, _expected: int | None) -> None:
        calls["count"] += 1
        if calls["count"] >= 2:
            raise MetadataConflictError("metadata.json changed on disk")

    monkeypatch.setattr(indicators_cmd, "_guard_mtime", guard)
    result = runner.invoke(
        app,
        [
            "indicators",
            str(metadata_path),
            "-o",
            str(out),
            "--expected-mtime",
            "1",
        ],
    )
    assert result.exit_code == 6
    assert out.read_text(encoding="utf-8") == "KEEP\n"
    assert list(tmp_path.glob("events.json.*")) == []


def test_indicators_writes_report_atomically(
    app: typer.Typer, metadata_path: Path, fake_video, tmp_path: Path
):
    """正常路では staging を経てレポートが公開され、staging は残らない。"""
    out = tmp_path / "events.json"
    result = runner.invoke(
        app, ["indicators", str(metadata_path), "--no-write", "-o", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(out.read_text(encoding="utf-8"))["events"]
    assert list(tmp_path.glob("events.json.*")) == []


def test_indicators_rejects_staging_aliasing_source(
    app: typer.Typer, metadata_path: Path, fake_video
):
    """`metadata.json.tmp` が元動画と同じ実体なら write-back 前に拒否する。

    `write_metadata_atomic` は staging に `write_text` する (truncate)。
    staging がハードリンク / シンボリックで録画を指していると、write-back が
    録画を不可逆に破壊する。
    """
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    source = Path(payload["source"])
    staging = metadata_path.with_suffix(metadata_path.suffix + ".tmp")
    os.link(source, staging)
    result = runner.invoke(app, ["indicators", str(metadata_path)])
    assert result.exit_code == 5
    assert "source video" in result.output
    assert source.read_bytes() == b""


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
    """サンプルは必ず試合区間の内側に落ちる (試合間のロビーを引かない)。"""
    matches = [
        {"start_time": 10.0, "end_time": 20.0},
        {"start_time": 100.0, "end_time": 200.0},
    ]
    timestamps = calibration_timestamps(matches, duration=300.0)
    assert len(timestamps) == 6
    for value in timestamps:
        assert 10.0 <= value <= 20.0 or 100.0 <= value <= 200.0
    # 長い試合のほうに多くのサンプルが割り当たる
    assert sum(1 for value in timestamps if value > 50.0) > 3


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


# ---------------------------------------------------------------------------
# レビュー指摘の回帰テスト (Codex adversarial-review)
# ---------------------------------------------------------------------------


def test_calibration_timestamps_spreads_within_a_single_match() -> None:
    """試合が 1 つでもサンプル数ぶんの時刻を返す。

    `calibrate_layout` は 2 フレーム以上の合意を要求するので、ここが 1 点だと
    1 試合だけの録画 (試合分割後の MP4 はまさにこれ) が必ず exit 4 になる。
    """
    timestamps = calibration_timestamps(
        [{"start_time": 0.0, "end_time": 900.0}], duration=900.0, samples=6
    )
    assert len(timestamps) == 6
    assert len(set(timestamps)) == 6
    assert all(0.5 <= value <= 899.5 for value in timestamps)
    assert timestamps == sorted(timestamps)


def test_calibration_timestamps_distributes_over_short_matches() -> None:
    """試合数がサンプル数より少ないときは各試合の中に配分する。"""
    matches = [
        {"start_time": 100.0, "end_time": 160.0},
        {"start_time": 400.0, "end_time": 460.0},
    ]
    timestamps = calibration_timestamps(matches, duration=1000.0, samples=6)
    assert len(timestamps) == 6
    inside = [
        100.5 <= value <= 159.5 or 400.5 <= value <= 459.5 for value in timestamps
    ]
    assert all(inside)


def test_calibration_timestamps_handles_very_short_match() -> None:
    """1 秒未満の試合でも内側の 1 点を返す (境界で負の範囲を作らない)。"""
    timestamps = calibration_timestamps(
        [{"start_time": 10.0, "end_time": 10.6}], duration=20.0, samples=2
    )
    assert all(10.0 <= value <= 10.6 for value in timestamps)


def test_indicators_rejects_output_aliasing_metadata(
    app: typer.Typer, metadata_path: Path, fake_video
):
    """`-o` が入力 metadata.json 自身なら書く前に落とす (入力を潰さない)。"""
    before = metadata_path.read_text(encoding="utf-8")
    result = runner.invoke(
        app, ["indicators", str(metadata_path), "--no-write", "-o", str(metadata_path)]
    )
    assert result.exit_code == 5
    assert "-o" in result.output
    assert metadata_path.read_text(encoding="utf-8") == before


def test_indicators_rejects_output_aliasing_source(
    app: typer.Typer, metadata_path: Path, fake_video
):
    """`-o` が元動画なら書く前に落とす (録画を破壊しない)。"""
    video = Path(json.loads(metadata_path.read_text(encoding="utf-8"))["source"])
    result = runner.invoke(
        app, ["indicators", str(metadata_path), "--no-write", "-o", str(video)]
    )
    assert result.exit_code == 5
    assert "-o" in result.output


def test_indicators_conflict_leaves_no_output(
    app: typer.Typer, metadata_path: Path, fake_video, tmp_path: Path
):
    """CAS 衝突 (exit 6) のときは `-o` のファイルも作らない。"""
    out = tmp_path / "events.json"
    result = runner.invoke(
        app,
        [
            "indicators",
            str(metadata_path),
            "--expected-mtime",
            "1",
            "-o",
            str(out),
        ],
    )
    assert result.exit_code == 6
    assert not out.exists()


def test_calibration_timestamps_keeps_short_match_samples_distinct() -> None:
    """1 秒未満の試合でもサンプルが 1 点に潰れない。

    全点が中点に潰れると dedupe で 1 フレームになり、2 フレーム以上の合意を
    要求するキャリブレーションが失敗する。
    """
    timestamps = calibration_timestamps(
        [{"start_time": 10.0, "end_time": 10.6}], duration=20.0, samples=3
    )
    assert len(timestamps) == 3
    assert len(set(timestamps)) == 3
    assert all(10.0 <= value <= 10.6 for value in timestamps)


@pytest.mark.parametrize("suffix", [".tmp", ".original.json"])
def test_indicators_rejects_output_colliding_with_reserved_paths(
    app: typer.Typer, metadata_path: Path, fake_video, suffix: str
):
    """`-o` が atomic write の staging や GUI のバックアップを指したら拒否する。"""
    reserved = metadata_path.parent / (
        metadata_path.name + ".tmp" if suffix == ".tmp" else "metadata.original.json"
    )
    result = runner.invoke(
        app, ["indicators", str(metadata_path), "--no-write", "-o", str(reserved)]
    )
    assert result.exit_code == 5
    assert "-o" in result.output


def test_indicators_rejects_cached_layout_outside_frame(
    app: typer.Typer, metadata_path: Path, fake_video
):
    """キャッシュされた layout が枠外を指すなら走査前に exit 2 で落とす。

    そのまま走査すると `detect_indicator` の ValueError が traceback として出る。
    """
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload["indicator_layout"].update({"anchor_x": 0.0, "anchor_y": 0.0, "scale": 1.0})
    metadata_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    result = runner.invoke(app, ["indicators", str(metadata_path), "--no-write"])
    assert result.exit_code == 2
    assert "収まっていません" in result.output
