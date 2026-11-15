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
import math
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
SUPPORTED_KINDS = frozenset({"ko", "assist"})


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


def _require_number(path: Path, label: str, value: object, *, minimum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path.name}: {label} must be a number, got {value!r}")
    number = float(value)
    if not math.isfinite(number) or number < minimum:
        raise ValueError(
            f"{path.name}: {label} must be finite and >= {minimum}, got {value!r}"
        )
    return number


def _require_spans(path: Path, label: str, raw: object) -> list[tuple[float, float]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"{path.name}: {label} must be a list of [start, end]")
    spans = []
    for index, span in enumerate(raw):
        if not isinstance(span, (list, tuple)) or len(span) != 2:
            raise ValueError(f"{path.name}: {label}[{index}] must be [start, end]")
        start = _require_number(path, f"{label}[{index}][0]", span[0], minimum=0.0)
        end = _require_number(path, f"{label}[{index}][1]", span[1], minimum=0.0)
        if end <= start:
            raise ValueError(f"{path.name}: {label}[{index}] end must be > start")
        spans.append((start, end))
    return spans


def _load_cases() -> list[GtCase]:
    """GT を読み、壊れた点は**収集時に落とす**（fail-open にしない）。"""
    cases = []
    for path in sorted(GT_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw_events = payload.get("events")
        if not isinstance(raw_events, list) or not raw_events:
            raise ValueError(f"{path.name}: events must be a non-empty list")
        events = []
        seen: set[tuple[str, float]] = set()
        for index, event in enumerate(raw_events):
            kind = event.get("kind")
            if kind not in SUPPORTED_KINDS:
                raise ValueError(
                    f"{path.name}: events[{index}] has unsupported kind {kind!r} "
                    f"(expected one of {sorted(SUPPORTED_KINDS)})"
                )
            start = _require_number(
                path, f"events[{index}].start", event.get("start"), minimum=0.0
            )
            key = (kind, round(start, 2))
            if key in seen:
                raise ValueError(f"{path.name}: duplicate GT event {key}")
            seen.add(key)
            events.append(GtEvent(kind=kind, start=start, note=event.get("note", "")))
        windows = _require_spans(path, "windows", payload.get("windows")) or None
        cases.append(
            GtCase(
                label=payload["label"],
                video_env=payload["video_env"],
                video_rel=payload["video_rel"],
                duration=float(payload["duration"]),
                provenance=payload.get("provenance", ""),
                windows=windows,
                no_detect_windows=_require_spans(
                    path, "no_detect_windows", payload.get("no_detect_windows")
                ),
                events=events,
            )
        )
    if not cases:
        raise ValueError(f"no GT fixtures found in {GT_DIR}")
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


def _merge_spans(spans: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """重なる区間を 1 つにまとめる（重複走査で同じ検出を二重に数えない）。"""
    merged: list[tuple[float, float]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _scan(
    video: Path,
    layout: IndicatorLayout,
    frame_size: tuple[int, int],
    spans: list[tuple[float, float]],
) -> list[IndicatorEvent]:
    events: list[IndicatorEvent] = []
    for start, end in _merge_spans(spans):
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


def _maximum_matching(
    gt: list[GtEvent], detected: list[IndicatorEvent]
) -> tuple[list[tuple[int, int]], set[int], set[int]]:
    """同 kind かつ開始差 <= 許容の組を**最大基数**で対応づける。

    「距離が小さい順の貪欲」だと、隣接する表示（例: 70.7 秒と 71.1 秒の GT に対し
    検出が 70.3 / 70.8）で 1 組しか取れず、recall を過小評価する。
    増加道法 (Kuhn) で基数を最大化し、距離は同点の判断にだけ使う。
    """
    adjacency = [
        [
            det_index
            for det_index, detection in enumerate(detected)
            if detection.kind == gt_event.kind
            and abs(detection.start - gt_event.start) <= TOLERANCE_SECONDS
        ]
        for gt_event in gt
    ]
    match_det: dict[int, int] = {}

    def augment(gt_index: int, visited: set[int]) -> bool:
        for det_index in adjacency[gt_index]:
            if det_index in visited:
                continue
            visited.add(det_index)
            if det_index not in match_det or augment(match_det[det_index], visited):
                match_det[det_index] = gt_index
                return True
        return False

    for gt_index in range(len(gt)):
        augment(gt_index, set())

    matched = sorted((g, d) for d, g in match_det.items())
    used_gt = {g for g, _ in matched}
    used_det = set(match_det)
    return matched, used_gt, used_det


def _scores(
    kind: str, gt: list[GtEvent], detected: list[IndicatorEvent]
) -> tuple[float, float, list[GtEvent], list[IndicatorEvent]]:
    gt_kind = [event for event in gt if event.kind == kind]
    det_kind = [event for event in detected if event.kind == kind]
    matched, used_gt, used_det = _maximum_matching(gt_kind, det_kind)
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
    # 静かな区間（未知表示だけの区間）も**走査対象に含める**。含めないと
    # 「検出なし」の assert が vacuous になる。
    spans = (case.windows or [(0.0, case.duration)]) + case.no_detect_windows
    detected = _scan(video, layout, frame_size, spans)

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
