"""``allaganeye indicators`` Typer command (#1106 作業項目 9).

metadata.json を入力に、KO / ASSIST インジケータの発生区間を検出して出力する。
検出に使った探索領域 (`indicator_layout`) は既定で metadata.json に書き戻し、
次回以降のキャリブレーションを省略できるようにする (#1106 作業項目 5)。

設計の要点:

- **入力は metadata.json**（`export` / `minimap` と同じ系譜）。動画だけを渡す形にしないのは、
  試合区間と解決済みレイアウトの両方が metadata に載っており、両方を使うため
- **キャリブレーションは試合区間の中のフレーム**で行う。戦意値ゲージは試合中しか出ないので、
  動画全体から等間隔に抜くと試合外（ロビー等）を引いて合意が崩れる
- **走査は 0.1 秒刻み**。連続 KO の更新は 0.15-0.35 秒間隔なので、0.1 秒より粗いと取りこぼす
  (実測 note 4-9)
- キャリブレーション不能は**黙ってイベント 0 件にしない**。exit 4 で明示的に落とす
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import typer

from allaganeye.detection.metadata_writer import (
    read_metadata,
    resolve_source_path,
    write_metadata_atomic,
)
from allaganeye.exceptions import (
    AllaganEyeError,
    ConfigValidationError,
    DetectionError,
    MetadataConflictError,
)
from allaganeye.video.frames import iter_gray_frames
from allaganeye.video.indicators import (
    IndicatorEvent,
    IndicatorLayout,
    calibrate_layout,
    detect_indicator,
    group_detections,
    layout_from_payload,
    layout_to_payload,
)
from allaganeye.video.probe import probe_video

DEFAULT_INTERVAL = 0.1
"""走査間隔 (秒)。note 4-9 の「0.1 秒以下」を既定にする。"""

MIN_INTERVAL = 0.05
"""走査間隔の下限。20 Hz を超える走査は映像の情報量を増やさない。"""

CALIBRATION_SAMPLES = 6
"""キャリブレーションに使うフレーム数 (note 4-3 の 5-10 フレーム)。"""

PROGRESS_STEP_SECONDS = 30.0
"""進捗を出す動画時間の間隔。"""


@dataclass(frozen=True)
class IndicatorReport:
    """`-o` に書き出す JSON ドキュメント / `--json` 最終行の本体。"""

    layout: dict[str, Any]
    events: list[dict[str, Any]]
    metadata_path: Path
    recalibrated: bool

    def to_payload(self) -> dict[str, Any]:
        return {
            "metadata": str(self.metadata_path),
            "layout": self.layout,
            "recalibrated": self.recalibrated,
            "events": self.events,
        }


def register(app: typer.Typer) -> None:
    """Wire the indicators command onto ``app`` (called from cli.py)."""

    @app.command(name="indicators")
    def indicators(
        metadata_path: Annotated[
            Path,
            typer.Argument(
                exists=False,
                help="Path to metadata.json produced by `allaganeye detect`.",
            ),
        ],
        output: Annotated[
            Path | None,
            typer.Option(
                "--output",
                "-o",
                help="Also write the detected events as a JSON document to this path.",
            ),
        ] = None,
        json_output: Annotated[
            bool,
            typer.Option(
                "--json",
                help=(
                    "Emit JSON Lines on stdout (progress + a final complete line) "
                    "instead of the human-readable summary."
                ),
            ),
        ] = False,
        interval: Annotated[
            float,
            typer.Option(
                "--interval",
                help=(
                    f"Scan interval in seconds (default {DEFAULT_INTERVAL}, "
                    f"min {MIN_INTERVAL})."
                ),
            ),
        ] = DEFAULT_INTERVAL,
        recalibrate: Annotated[
            bool,
            typer.Option(
                "--recalibrate",
                help="Ignore a cached `indicator_layout` in metadata.json and resolve again.",
            ),
        ] = False,
        write: Annotated[
            bool,
            typer.Option(
                "--write/--no-write",
                help="Write the resolved layout back into metadata.json (default: write).",
            ),
        ] = True,
        expected_mtime: Annotated[
            int | None,
            typer.Option(
                "--expected-mtime",
                help=(
                    "Optimistic-lock guard for --write: exit 6 if metadata.json "
                    "mtime (ms) differs at write time."
                ),
            ),
        ] = None,
    ) -> None:
        """Detect KO / ASSIST indicator intervals in a detected recording."""

        def emit(payload: dict[str, Any]) -> None:
            if json_output:
                typer.echo(json.dumps(payload, ensure_ascii=False))

        def progress(message: str) -> None:
            if not json_output:
                typer.echo(message, err=True)

        try:
            report = run_indicators(
                metadata_path=metadata_path,
                output=output,
                interval=interval,
                recalibrate=recalibrate,
                write=write,
                expected_mtime=expected_mtime,
                emit=emit,
                progress=progress,
            )
        except AllaganEyeError as e:
            emit({"type": "error", "message": str(e)})
            progress(f"Error: {e}")
            raise typer.Exit(code=e.exit_code) from None
        except KeyboardInterrupt:
            emit({"type": "error", "message": "cancelled"})
            progress("Cancelled.")
            raise typer.Exit(code=130) from None
        if not json_output:
            print_summary(report, wrote_metadata=write, output=output)


def calibration_timestamps(
    matches: list[dict[str, Any]],
    *,
    duration: float,
    samples: int = CALIBRATION_SAMPLES,
) -> list[float]:
    """Pick frame timestamps for calibration, preferring in-match moments.

    The battle-fervor gauge only renders during a match, so sampling the whole
    video uniformly pulls in lobby / loading frames where the anchor cannot
    match at all and the consensus collapses. One frame per match, spread
    across the match list, keeps the samples inside the UI we look for.
    """
    usable = [
        match
        for match in matches
        if isinstance(match, dict)
        and isinstance(match.get("start_time"), (int, float))
        and isinstance(match.get("end_time"), (int, float))
        and float(match["end_time"]) > float(match["start_time"])
    ]
    if not usable:
        if duration <= 0:
            return []
        step = duration / (samples + 1)
        return [round(step * (index + 1), 3) for index in range(samples)]
    if len(usable) <= samples:
        chosen = usable
    else:
        stride = (len(usable) - 1) / (samples - 1)
        chosen = [usable[round(index * stride)] for index in range(samples)]
    timestamps = []
    for match in chosen:
        start = float(match["start_time"])
        end = float(match["end_time"])
        centre = (start + end) / 2
        # 0.5 秒だけ内側に寄せる: 表示のフェード端や境界フレームを避ける
        timestamps.append(round(min(end - 0.5, max(start + 0.5, centre)), 3))
    return timestamps


def resolve_indicator_layout(
    source: Path,
    payload: dict[str, Any],
    *,
    frame_size: tuple[int, int],
    duration: float,
) -> IndicatorLayout:
    """Calibrate from frames sampled inside the detected matches."""
    timestamps = calibration_timestamps(
        [match for match in payload.get("matches") or [] if isinstance(match, dict)],
        duration=duration,
    )
    frames = []
    for timestamp in timestamps:
        for _, frame in iter_gray_frames(
            source, fps=1.0, frame_size=frame_size, start=timestamp, duration=0.2
        ):
            frames.append(frame)
            break
    layout = calibrate_layout(frames)
    if layout is None:
        raise DetectionError(
            "インジケータの探索領域を解決できませんでした "
            f"({len(frames)} フレームの合意が取れず)。"
            "戦意値ゲージが映っていない録画か、HUD レイアウトが想定外の可能性があります。"
        )
    return layout


def _match_index(matches: list[dict[str, Any]], timestamp: float) -> int | None:
    for match in matches:
        start = match.get("start_time")
        end = match.get("end_time")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            continue
        if float(start) <= timestamp <= float(end):
            index = match.get("index")
            if isinstance(index, int):
                return index
    return None


def _event_payload(
    event: IndicatorEvent, matches: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "kind": event.kind,
        "start": round(event.start, 2),
        "end": round(event.end, 2),
        "score": round(event.score, 3),
        "samples": event.samples,
        "match_index": _match_index(matches, event.start),
    }


def _guard_mtime(metadata_path: Path, expected_mtime: int | None) -> None:
    if expected_mtime is None:
        return
    try:
        current = metadata_path.stat().st_mtime_ns // 1_000_000
    except OSError:
        current = -1
    if current != expected_mtime:
        raise MetadataConflictError(
            f"metadata.json changed on disk (expected mtime {expected_mtime}, "
            f"got {current}); re-run without --expected-mtime to accept the new file"
        )


def run_indicators(
    *,
    metadata_path: Path,
    output: Path | None,
    interval: float,
    recalibrate: bool,
    write: bool,
    expected_mtime: int | None,
    emit: Callable[[dict[str, Any]], None],
    progress: Callable[[str], None],
) -> IndicatorReport:
    """Body of the command, kept free of typer so it can be unit-tested."""
    if interval < MIN_INTERVAL:
        raise ConfigValidationError(
            f"--interval must be >= {MIN_INTERVAL}s (continuous KO updates arrive "
            f"every 0.15-0.35s); got {interval}"
        )
    payload = read_metadata(metadata_path)
    source = resolve_source_path(payload, metadata_path)
    probe = probe_video(source)
    frame_size = (int(probe["width"]), int(probe["height"]))
    duration = float(probe["duration"])
    matches = [
        match for match in payload.get("matches") or [] if isinstance(match, dict)
    ]

    cached = payload.get("indicator_layout")
    recalibrated = False
    if cached is not None and not recalibrate:
        layout = layout_from_payload(
            cached, frame_width=frame_size[0], frame_height=frame_size[1]
        )
        progress("reused indicator_layout from metadata.json")
    else:
        emit({"type": "progress", "phase": "calibrating"})
        progress("resolving indicator layout ...")
        layout = resolve_indicator_layout(
            source, payload, frame_size=frame_size, duration=duration
        )
        recalibrated = True

    layout_payload = layout_to_payload(
        layout, frame_width=frame_size[0], frame_height=frame_size[1]
    )
    emit({"type": "progress", "phase": "scanning", "layout": layout_payload})

    detections: list[tuple[float, str | None, float]] = []
    next_progress = PROGRESS_STEP_SECONDS
    for timestamp, frame in iter_gray_frames(
        source, fps=1.0 / interval, frame_size=frame_size, duration=duration
    ):
        hit = detect_indicator(frame, layout)
        detections.append(
            (timestamp, hit.kind if hit else None, hit.score if hit else 0.0)
        )
        if timestamp >= next_progress:
            emit(
                {
                    "type": "progress",
                    "phase": "scanning",
                    "processed_s": round(timestamp, 1),
                    "total_s": round(duration, 1),
                }
            )
            progress(f"  scanned {timestamp:.0f}s / {duration:.0f}s")
            next_progress += PROGRESS_STEP_SECONDS

    events = group_detections(detections, max_gap=interval * 1.2, min_samples=2)
    report = IndicatorReport(
        layout=layout_payload,
        events=[_event_payload(event, matches) for event in events],
        metadata_path=metadata_path,
        recalibrated=recalibrated,
    )

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report.to_payload(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    if write:
        _guard_mtime(metadata_path, expected_mtime)
        payload["indicator_layout"] = layout_payload
        write_metadata_atomic(metadata_path, payload)

    emit(
        {
            "type": "complete",
            **report.to_payload(),
            "wrote_metadata": write,
        }
    )
    return report


def print_summary(
    report: IndicatorReport, *, wrote_metadata: bool, output: Path | None
) -> None:
    """Human-readable summary (stdout; `--json` callers skip this)."""
    events = report.events
    ko = sum(1 for event in events if event["kind"] == "ko")
    assist = sum(1 for event in events if event["kind"] == "assist")
    typer.echo(f"KO: {ko} / ASSIST: {assist} ({len(events)} intervals)")
    for event in events:
        match = event["match_index"]
        where = f"match {match}" if match is not None else "outside matches"
        typer.echo(
            f"  {event['start']:8.2f}s - {event['end']:8.2f}s  "
            f"{event['kind']:6s} score={event['score']:.2f}  ({where})"
        )
    if output is not None:
        typer.echo(f"events written to {output}")
    if wrote_metadata:
        typer.echo(f"indicator_layout written to {report.metadata_path}")


__all__ = [
    "DEFAULT_INTERVAL",
    "MIN_INTERVAL",
    "IndicatorReport",
    "calibration_timestamps",
    "register",
    "resolve_indicator_layout",
    "run_indicators",
]
