"""GT 突合ハーネス (#1106 作業項目 6)。

設計の正: `docs/superpowers/specs/2026-11-12-l4-ko-assist-indicator-appearance.md` 7.8 節

GT ファイルは `tests/fixtures/indicators_gt/*.json`:

- `events[]`: `{kind, start, note}` の GT
- `windows`: `null` なら全区間、配列ならその窓だけ走査する（長尺 VOD 用）
- `no_detect_windows`: ここで 1 件でも検出したら fail（`BOOSTED!` 等の未知表示の混入検出）

**評価は切り抜き単位**（2026-11-14 Idios 判断）: 近接表示が分割 / 併合されても、
区間の開始が +/-0.5 秒以内なら一致とみなす。合否は KO / ASSIST 別に
recall >= 0.8 / precision >= 0.8（元 issue の初期案）。

GT の作り方（循環参照を避けるための手順）:

1. 既定しきい値より低い 0.40 で全編を走査し、**取りこぼし候補**を列挙する
2. 候補と検出済みイベントの差分を目視裁定して GT に追加 / 棄却する
3. KO は `K.O.` カウンタの連番を併用して全数を確認する（`20260116_5` は録画側に
   10 K.O. の表示が無いことを Idios が目視確認済み）

GT は「人間が裁定した表示の一覧」であり、検出器の出力そのものではない。ただし
ASSIST は全数の独立列挙が無いため、**低閾値走査で拾えなかった表示は GT にも入らない**
（残課題として PR / issue に明記する）。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import pytest

from allaganeye.video.frames import iter_gray_frames
from allaganeye.video.indicators import (
    IndicatorEvent,
    IndicatorLayout,
    resolve_layout,
    scan_indicators,
)
from allaganeye.video.probe import probe_video

pytestmark = pytest.mark.slow

GT_DIR = Path(__file__).parent / "fixtures" / "indicators_gt"
SCAN_FPS = 10.0
CALIBRATION_SAMPLES = 6
CALIBRATION_SPAN = 900.0
TOLERANCE_SECONDS = 0.5
MIN_RECALL = 0.8
MIN_PRECISION = 0.8


@dataclass(frozen=True)
class GtEvent:
    kind: str
    start: float
    note: str = ""


@dataclass(frozen=True)
class GtCase:
    label: str
    video_env: str
    video_rel: str
    duration: float
    provenance: str
    windows: list[tuple[float, float]] | None
    no_detect_windows: list[tuple[float, float]]
    events: list[GtEvent]

    def video(self) -> Path:
        root = os.environ.get(self.video_env)
        if not root:
            pytest.skip(f"{self.video_env} not set")
        path = Path(root) / self.video_rel
        if not path.is_file():
            pytest.skip(f"sample video not found: {path}")
        return path


def _load_cases() -> list[GtCase]:
    cases = []
    for path in sorted(GT_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        cases.append(
            GtCase(
                label=payload["label"],
                video_env=payload["video_env"],
                video_rel=payload["video_rel"],
                duration=float(payload["duration"]),
                provenance=payload.get("provenance", ""),
                windows=(
                    None
                    if payload.get("windows") is None
                    else [tuple(w) for w in payload["windows"]]
                ),
                no_detect_windows=[
                    tuple(w) for w in payload.get("no_detect_windows", [])
                ],
                events=[
                    GtEvent(
                        kind=e["kind"], start=float(e["start"]), note=e.get("note", "")
                    )
                    for e in payload["events"]
                ],
            )
        )
    return cases


CASES = _load_cases()


def _calibrate(video: Path, frame_size: tuple[int, int]) -> IndicatorLayout:
    """6 フレームの合意でレイアウトを解決する（試合区間の情報は使わない）。"""
    frames = []
    stride = CALIBRATION_SPAN / CALIBRATION_SAMPLES
    for index in range(CALIBRATION_SAMPLES):
        start = 40.0 + index * stride
        for _, frame in iter_gray_frames(
            video, fps=1.0, frame_size=frame_size, start=start, duration=0.2
        ):
            frames.append(frame)
            break
    layout = resolve_layout(frames)
    assert layout is not None, f"layout should be resolved for {video.name}"
    return layout


def _scan(
    video: Path,
    layout: IndicatorLayout,
    frame_size: tuple[int, int],
    duration: float,
    windows: list[tuple[float, float]] | None,
) -> list[IndicatorEvent]:
    spans = windows or [(0.0, duration)]
    events: list[IndicatorEvent] = []
    for start, end in spans:
        events.extend(
            scan_indicators(
                iter_gray_frames(
                    video,
                    fps=SCAN_FPS,
                    frame_size=frame_size,
                    start=start,
                    duration=end - start,
                ),
                layout,
            )
        )
    return events


def _match(
    gt: list[GtEvent], detected: list[IndicatorEvent]
) -> tuple[list[tuple[int, int]], set[int], set[int]]:
    """同 kind かつ開始差 <= 許容の組を、差が小さい順に 1:1 で対応づける。"""
    candidates = []
    for gt_index, gt_event in enumerate(gt):
        for det_index, detection in enumerate(detected):
            if detection.kind != gt_event.kind:
                continue
            delta = abs(detection.start - gt_event.start)
            if delta <= TOLERANCE_SECONDS:
                candidates.append((delta, gt_index, det_index))
    candidates.sort()
    matched: list[tuple[int, int]] = []
    used_gt: set[int] = set()
    used_det: set[int] = set()
    for _, gt_index, det_index in candidates:
        if gt_index in used_gt or det_index in used_det:
            continue
        used_gt.add(gt_index)
        used_det.add(det_index)
        matched.append((gt_index, det_index))
    return matched, used_gt, used_det


def _scores(
    kind: str, gt: list[GtEvent], detected: list[IndicatorEvent]
) -> tuple[float, float, list[GtEvent], list[IndicatorEvent]]:
    gt_kind = [event for event in gt if event.kind == kind]
    det_kind = [event for event in detected if event.kind == kind]
    matched, used_gt, used_det = _match(gt_kind, det_kind)
    recall = len(matched) / len(gt_kind) if gt_kind else 1.0
    precision = len(matched) / len(det_kind) if det_kind else 1.0
    missed = [event for index, event in enumerate(gt_kind) if index not in used_gt]
    extra = [event for index, event in enumerate(det_kind) if index not in used_det]
    return recall, precision, missed, extra


def _report(case: GtCase, gt: list[GtEvent], detected: list[IndicatorEvent]) -> str:
    lines = [f"[{case.label}] gt={len(gt)} detected={len(detected)}"]
    for kind in ("ko", "assist"):
        recall, precision, missed, extra = _scores(kind, gt, detected)
        lines.append(
            f"  {kind:6s} recall={recall:.3f} precision={precision:.3f} "
            f"gt={sum(1 for e in gt if e.kind == kind)} "
            f"detected={sum(1 for e in detected if e.kind == kind)}"
        )
        for event in missed:
            lines.append(f"    missed {event.start:.2f}s {event.note}")
        for event in extra:
            lines.append(f"    extra  {event.start:.2f}s score={event.score:.2f}")
    return "\n".join(lines)


@pytest.mark.parametrize("case", CASES, ids=[case.label for case in CASES])
def test_indicator_gt_matches_within_thresholds(case: GtCase) -> None:
    """GT に対して KO / ASSIST 別に recall / precision がしきい値を満たす。

    同じ走査結果で「未知表示だけの区間では検出しない」ことも確かめる
    (再走査すると 1 本あたり 4 分近くかかるため 1 テストにまとめる)。
    """
    video = case.video()
    probe = probe_video(video)
    frame_size = (int(probe["width"]), int(probe["height"]))
    layout = _calibrate(video, frame_size)
    detected = _scan(video, layout, frame_size, case.duration, case.windows)

    report = _report(case, case.events, detected)
    print(report)  # `-s` 付きで実測値を確認できるようにする
    for kind in ("ko", "assist"):
        recall, precision, _, _ = _scores(kind, case.events, detected)
        assert recall >= MIN_RECALL, (
            f"{kind} recall {recall:.3f} < {MIN_RECALL}\n{report}"
        )
        assert precision >= MIN_PRECISION, (
            f"{kind} precision {precision:.3f} < {MIN_PRECISION}\n{report}"
        )

    inside = [
        (event.kind, round(event.start, 2))
        for event in detected
        if any(start <= event.start <= end for start, end in case.no_detect_windows)
    ]
    assert inside == [], f"detected inside quiet windows: {inside}\n{report}"
