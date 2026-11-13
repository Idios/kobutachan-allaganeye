"""Slow real-video test: KO / ASSIST インジケータ検出の GT 突合 (#1106)。

GT の正: `docs/superpowers/specs/2026-11-12-l4-ko-assist-indicator-appearance.md`

  - `20260116_1.mp4` 493.2 秒 KO / 206.4 秒 ASSIST (参照レイアウト)
  - `20260116_5.mp4` 788.4 秒 KO (2 桁)
  - 他プレイヤー VOD 762.4 秒 KO / 670 秒 ASSIST / 357 秒 BOOSTED (別 HUD 配置)

GT は「申告時刻の前後 0.1 秒刻みの目視」なので許容は +/-0.5 秒。検出区間の開始が
その範囲に入っていることを要求する。BOOSTED は既知テンプレートに一致しないので
`other` として無視される (誤検知しないこと) を確認する。

Missing-video policy: サンプル動画ディレクトリが無い環境では skip。
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import numpy as np
import pytest

from allaganeye.ffmpeg_path import find_ffmpeg
from allaganeye.video.indicators import (
    IndicatorEvent,
    IndicatorLayout,
    resolve_layout,
    scan_indicators,
)

pytestmark = pytest.mark.slow

FRAME_HEIGHT = 1080
FRAME_WIDTH = 1920
SCAN_FPS = 10.0
CALIBRATION_SAMPLES = 6
GT_TOLERANCE_SECONDS = 0.5

# 参照レイアウト (1080p / 4K 表示を FHD 録画)。実測 note 3.3 / 4-4 の値。
REFERENCE_ORIGIN = (618.0, 614.0)
OTHER_HUD_ORIGIN = (621.0, 289.0)
OTHER_HUD_SCALE = 0.80


def _sample_root() -> Path:
    env = os.environ.get("ALLAGANEYE_SAMPLE_VIDEO_DIR")
    if not env:
        pytest.skip("ALLAGANEYE_SAMPLE_VIDEO_DIR not set")
    root = Path(env)
    if not root.is_dir():
        pytest.skip(f"sample video directory not found: {root}")
    return root


def _other_hud_vod() -> Path:
    env = os.environ.get("ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER", "E:/allaganeye-samples")
    root = Path(env)
    video = root / "2772549129-151803977-da21c691-9ed6-4068-9a8b-4726a8a519a8.mp4"
    if not video.is_file():
        pytest.skip(f"other-HUD sample VOD not found: {video}")
    return video


def _video(name: str) -> Path:
    path = _sample_root() / "20260116" / name
    if not path.is_file():
        pytest.skip(f"sample video not found: {path}")
    return path


def _read_frames(
    video: Path, start: float, duration: float, fps: float
) -> list[tuple[float, np.ndarray]]:
    """ffmpeg で区間をデコードし `(時刻, グレースケールフレーム)` を返す。

    `-ss` は `-i` の前 (入力シーク)、`-t` は `-i` の後 (出力長) に置く。
    `-t` を入力側に置くと出力タイムスタンプがずれるので順序を変えないこと。
    """
    command = [
        str(find_ffmpeg()),
        "-v",
        "error",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(video),
        "-t",
        f"{duration:.3f}",
        "-vf",
        f"fps={fps}",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "-",
    ]
    proc = subprocess.run(command, capture_output=True, check=True)
    size = FRAME_HEIGHT * FRAME_WIDTH
    count = len(proc.stdout) // size
    return [
        (
            start + index / fps,
            np.frombuffer(
                proc.stdout[index * size : (index + 1) * size], np.uint8
            ).reshape(FRAME_HEIGHT, FRAME_WIDTH),
        )
        for index in range(count)
    ]


_LAYOUT_CACHE: dict[str, IndicatorLayout] = {}


def _layout(video: Path, key: str) -> IndicatorLayout:
    if key in _LAYOUT_CACHE:
        return _LAYOUT_CACHE[key]
    span = 900.0
    frames = [
        frame
        for _, frame in _read_frames(video, 40.0, span, CALIBRATION_SAMPLES / span)
    ]
    assert len(frames) >= 3, f"expected >=3 calibration frames, got {len(frames)}"
    layout = resolve_layout(frames)
    assert layout is not None, "layout should be resolved from the video"
    _LAYOUT_CACHE[key] = layout
    return layout


def _events_around(
    video: Path, layout: IndicatorLayout, centre: float
) -> list[IndicatorEvent]:
    frames = _read_frames(video, max(0.0, centre - 2.0), 4.0, SCAN_FPS)
    return scan_indicators(frames, layout)


def _assert_event(events: list[IndicatorEvent], kind: str, centre: float) -> None:
    matching = [
        event
        for event in events
        if event.kind == kind and abs(event.start - centre) <= GT_TOLERANCE_SECONDS
    ]
    assert matching, (
        f"expected {kind} near {centre}s, got "
        f"{[(event.kind, round(event.start, 1)) for event in events]}"
    )


# ---------------------------------------------------------------------------
# キャリブレーション (動画ごとに 1 回)
# ---------------------------------------------------------------------------


def test_calibrate_reference_layout() -> None:
    """参照動画では スケール 1.0 / アンカー (618, 614) が復元される。"""
    layout = _layout(_video("20260116_1.mp4"), "ref1")
    assert layout.scale == pytest.approx(1.0, abs=0.08)
    assert layout.x == pytest.approx(REFERENCE_ORIGIN[0], abs=12)
    assert layout.y == pytest.approx(REFERENCE_ORIGIN[1], abs=12)
    assert layout.support >= 3
    assert layout.confidence >= 0.7


def test_calibrate_other_hud_layout() -> None:
    """別プレイヤーの VOD (別 HUD 配置 + 0.8 倍) でもアンカーが解決できる。"""
    layout = _layout(_other_hud_vod(), "other")
    assert layout.scale == pytest.approx(OTHER_HUD_SCALE, abs=0.08)
    assert layout.x == pytest.approx(OTHER_HUD_ORIGIN[0], abs=12)
    assert layout.y == pytest.approx(OTHER_HUD_ORIGIN[1], abs=12)
    assert layout.support >= 3


# ---------------------------------------------------------------------------
# 検出 (0.1 秒刻み)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("video_name", "cache_key", "kind", "centre"),
    [
        ("20260116_1.mp4", "ref1", "ko", 493.2),
        ("20260116_1.mp4", "ref1", "assist", 206.4),
        ("20260116_5.mp4", "ref5", "ko", 788.4),
    ],
)
def test_reference_video_events(
    video_name: str, cache_key: str, kind: str, centre: float
) -> None:
    """参照レイアウトの録画で KO / ASSIST を拾う (2 桁 KO を含む)。"""
    video = _video(video_name)
    layout = _layout(video, cache_key)
    _assert_event(_events_around(video, layout, centre), kind, centre)


@pytest.mark.parametrize(("kind", "centre"), [("ko", 762.4), ("assist", 670.0)])
def test_other_hud_events(kind: str, centre: float) -> None:
    """別 HUD 配置の VOD でも KO / ASSIST を拾う。"""
    video = _other_hud_vod()
    layout = _layout(video, "other")
    _assert_event(_events_around(video, layout, centre), kind, centre)


def test_boosted_is_ignored() -> None:
    """BOOSTED! (戦意値上昇) は既知テンプレートに一致しないので拾わない。"""
    video = _other_hud_vod()
    layout = _layout(video, "other")
    events = _events_around(video, layout, 357.0)
    assert events == [], [(event.kind, round(event.start, 1)) for event in events]


def test_quiet_window_has_no_events() -> None:
    """インジケータが出ていない区間では何も返さない。"""
    video = _video("20260116_1.mp4")
    layout = _layout(video, "ref1")
    assert _events_around(video, layout, 400.0) == []


def test_iter_gray_frames_feeds_the_detector() -> None:
    """実フレーム読み出し経路 (frame reader -> detector) が 0.1 秒刻みで機能する。

    単体テストは ffmpeg 引数の順序しか見ていない。ここでは実際に動画から
    10 Hz でフレームを取り、KO 表示区間 (493.2-494.7 秒) を拾えることを確認する。
    """
    from allaganeye.video.frames import iter_gray_frames
    from allaganeye.video.indicators import detect_indicator

    video = _video("20260116_1.mp4")
    layout = _layout(video, "ref1")
    hits = []
    for timestamp, frame in iter_gray_frames(
        video,
        fps=SCAN_FPS,
        frame_size=(FRAME_WIDTH, FRAME_HEIGHT),
        start=493.0,
        duration=2.0,
    ):
        hit = detect_indicator(frame, layout)
        if hit is not None:
            hits.append((round(timestamp, 1), hit.kind, round(hit.score, 2)))
    assert hits, "expected at least one KO detection inside the display window"
    assert {kind for _, kind, _ in hits} == {"ko"}
    assert min(timestamp for timestamp, _, _ in hits) <= 493.7
