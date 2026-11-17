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
import math
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import tempfile
from typing import Annotated, Any

import typer

from allaganeye.detection.format import format_hms
from allaganeye.detection.metadata_writer import (
    read_metadata,
    resolve_source_path,
    write_metadata_atomic,
)
from allaganeye.exceptions import (
    AllaganEyeError,
    ConfigValidationError,
    DetectionError,
    InputFileError,
    MetadataConflictError,
)
from allaganeye.video.frames import iter_gray_frames
from allaganeye.video.indicators import (
    IndicatorEvent,
    IndicatorLayout,
    calibrate_layout,
    detect_indicator,
    event_to_payload,
    group_detections,
    layout_from_bar_region,
    layout_from_payload,
    layout_to_payload,
    validate_layout_for_frame,
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
        region: Annotated[
            str | None,
            typer.Option(
                "--region",
                help=(
                    "Skip auto calibration and use this gauge-bar rectangle "
                    "`X,Y,W,H` (pixels). Fallback for unexpected HUD layouts."
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
                region=_parse_region(region),
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


def _parse_region(value: str | None) -> tuple[float, float, float, float] | None:
    """`--region X,Y,W,H` を数値に変換する（不正は exit 5 の例外にする）。"""
    if value is None:
        return None
    parts = value.split(",")
    if len(parts) != 4:
        raise ConfigValidationError(
            f"--region must be X,Y,W,H (4 comma-separated numbers), got {value!r}"
        )
    try:
        numbers = tuple(float(part) for part in parts)
    except ValueError as exc:
        raise ConfigValidationError(
            f"--region must contain numbers, got {value!r}"
        ) from exc
    return numbers  # type: ignore[return-value]


def calibration_timestamps(
    matches: list[dict[str, Any]],
    *,
    duration: float,
    samples: int = CALIBRATION_SAMPLES,
) -> list[float]:
    """Pick frame timestamps for calibration, preferring in-match moments.

    The battle-fervor gauge only renders during a match, so sampling the whole
    video uniformly pulls in lobby / loading frames where the anchor cannot
    match at all and the consensus collapses.

    Samples are distributed over the **total matched time**, not one per
    match: a recording split into per-match MP4s has exactly one match, and
    ``calibrate_layout`` needs at least two agreeing frames, so "one frame per
    match" would make every single-match file fail calibration.
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
        return [_inset(0.0, duration, step * (index + 1)) for index in range(samples)]

    spans = [(float(match["start_time"]), float(match["end_time"])) for match in usable]
    if len(spans) >= samples:
        stride = (len(spans) - 1) / (samples - 1) if samples > 1 else 0.0
        chosen = [spans[round(index * stride)] for index in range(samples)]
        return [_inset(start, end, (start + end) / 2) for start, end in chosen]

    total = sum(end - start for start, end in spans)
    timestamps: list[float] = []
    for index in range(samples):
        target = total * (index + 0.5) / samples
        offset = 0.0
        for start, end in spans:
            length = end - start
            if offset + length >= target:
                timestamps.append(_inset(start, end, start + (target - offset)))
                break
            offset += length
    return sorted(set(timestamps))


def _inset(start: float, end: float, timestamp: float, *, margin: float = 0.5) -> float:
    """内側に寄せる: 表示のフェード端や境界フレームを避ける。

    1 秒未満の短い区間では固定 0.5 秒の margin だと全サンプルが中点に潰れる
    (dedupe で 1 フレームになり、2 フレーム以上の合意を要求するキャリブレーションが
    失敗する)。区間長の 1/4 を上限にして、短い区間でも位置が分かれるようにする。
    """
    effective = min(margin, (end - start) / 4)
    return round(min(end - effective, max(start + effective, timestamp)), 3)


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
    try:
        validate_layout_for_frame(
            layout, frame_width=frame_size[0], frame_height=frame_size[1]
        )
    except InputFileError as exc:
        # 合意で見つけたアンカーがフレーム端に寄っていて、帯域がはみ出すケース。
        # 入力 metadata の不正ではなく解決失敗なので exit 4 に寄せる。
        raise DetectionError(f"探索領域を解決できませんでした: {exc}") from exc
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
    """内部イベントを wire 形式にする (`HighlightEvent`、#127)。"""
    return event_to_payload(event, match_index=_match_index(matches, event.start))


def _reject_output_aliasing_inputs(
    output: Path | None, metadata_path: Path, source: Path
) -> None:
    """`-o` が入力を潰す先を指していたら、何も書く前に拒否する。

    守る対象:

    - `metadata.json` 本体 (イベントレポートで置き換えてしまう)
    - 元動画 (録画を破壊する)
    - `metadata.json.tmp` (write_metadata_atomic の staging。ここに書いた
      レポートは直後の rename で消える)
    - `metadata.original.json` (GUI の `[元に戻す]` バックアップ。
      docs/metadata-spec.md sec.「metadata.original.json policy」)

    同一性は realpath と (両方実在する場合の) `samefile` で見る:
    シンボリックリンク・ハードリンク・Windows の大文字小文字差を名前比較だけで
    見逃さない。レポートは metadata の書込みより先に書かれるので、ここで
    落とせば部分的な書込みも起きない。
    """
    if output is None:
        return
    if output.exists() and output.is_dir():
        raise ConfigValidationError(
            f"-o must be a file path, but {output} is a directory"
        )
    staging = metadata_path.with_suffix(metadata_path.suffix + ".tmp")
    backup = metadata_path.parent / "metadata.original.json"
    protected = [
        ("metadata.json", metadata_path),
        ("source video", source),
        ("metadata write staging file", staging),
        ("GUI restore backup", backup),
    ]
    for label, other in protected:
        if _same_path(output, other):
            raise ConfigValidationError(
                f"-o must not point at the {label} ({other}); "
                "choose a separate output path"
            )


def _same_path(left: Path, right: Path) -> bool:
    """realpath 一致、または両方実在する場合の samefile 一致で判定する。"""
    try:
        if left.resolve() == right.resolve():
            return True
    except OSError:
        if left.absolute() == right.absolute():
            return True
    try:
        return left.exists() and right.exists() and left.samefile(right)
    except OSError:
        return False


def _reject_staging_aliasing_protected(metadata_path: Path, source: Path) -> None:
    """metadata write の staging が保護対象と同じ実体なら、何も書く前に拒否する。

    `write_metadata_atomic` は staging (`metadata.json.tmp`) に `write_text` する
    ので、staging がシンボリックリンク / ハードリンクで別の実体を指していると、
    write-back がそれを不可逆に破壊する。`-o` の alias 検査は `-o` が無い
    (既定の write-back だけの) 実行を守らないので、ここで別に見る。
    """
    staging = metadata_path.with_suffix(metadata_path.suffix + ".tmp")
    backup = metadata_path.parent / "metadata.original.json"
    for label, other in (
        ("source video", source),
        ("GUI restore backup", backup),
    ):
        if _same_path(staging, other):
            raise ConfigValidationError(
                f"metadata write staging file {staging} points at the {label} "
                f"({other}); remove it before writing metadata"
            )


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


def _stage_report(output: Path, payload: dict[str, Any]) -> Path:
    """レポートを出力先と同じディレクトリの staging に書く (公開はまだしない)。

    既存の `-o` を truncate しないための 2 段階化。書込みに失敗しても既存の
    レポートは元のまま残る。staging 名は `mkstemp` のランダム名にして、
    利用者の `events.json.tmp` のような既存ファイルを巻き込まない。
    """
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(
            dir=output.parent, prefix=output.name + ".", suffix=".tmp"
        )
    except OSError as e:
        raise AllaganEyeError(f"Cannot prepare the report path {output}: {e}") from e
    staging = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    except OSError as e:
        staging.unlink(missing_ok=True)
        raise AllaganEyeError(f"Cannot write the report to {output}: {e}") from e
    return staging


def _publish_report(staging: Path, output: Path) -> None:
    """staging を `os.replace` で公開する (どちらかが失敗しても中途半端にならない)。"""
    try:
        os.replace(staging, output)
    except OSError as e:
        staging.unlink(missing_ok=True)
        raise AllaganEyeError(f"Cannot write the report to {output}: {e}") from e


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
    region: tuple[float, float, float, float] | None = None,
) -> IndicatorReport:
    """Body of the command, kept free of typer so it can be unit-tested."""
    # NaN はすべての比較が False なので、下限比較より先に有限性を見る。
    # 素通りすると `fps=1/interval` が nan / 0.0 になり、ffmpeg に意味不明な値が渡る。
    if not math.isfinite(interval):
        raise ConfigValidationError(
            f"--interval must be a finite number, got {interval}"
        )
    if interval < MIN_INTERVAL:
        raise ConfigValidationError(
            f"--interval must be >= {MIN_INTERVAL}s (continuous KO updates arrive "
            f"every 0.15-0.35s); got {interval}"
        )
    payload = read_metadata(metadata_path)
    source = resolve_source_path(payload, metadata_path)
    _reject_output_aliasing_inputs(output, metadata_path, source)
    if write:
        _reject_staging_aliasing_protected(metadata_path, source)
    probe = probe_video(source)
    frame_size = (int(probe["width"]), int(probe["height"]))
    duration = float(probe["duration"])
    matches = [
        match for match in payload.get("matches") or [] if isinstance(match, dict)
    ]

    cached = payload.get("indicator_layout")
    recalibrated = False
    if region is not None:
        if recalibrate:
            raise ConfigValidationError(
                "--region and --recalibrate are mutually exclusive; "
                "--region already skips auto calibration"
            )
        try:
            layout = layout_from_bar_region(*region)
        except ValueError as exc:
            raise ConfigValidationError(f"--region: {exc}") from exc
        validate_layout_for_frame(
            layout, frame_width=frame_size[0], frame_height=frame_size[1]
        )
        progress("using --region (auto calibration skipped)")
    elif cached is not None and not recalibrate:
        layout = layout_from_payload(
            cached, frame_width=frame_size[0], frame_height=frame_size[1]
        )
        validate_layout_for_frame(
            layout, frame_width=frame_size[0], frame_height=frame_size[1]
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

    # どの書込みよりも先に CAS を確かめる: ここで落ちれば `-o` のファイルも作らない。
    if write:
        _guard_mtime(metadata_path, expected_mtime)

    # レポートは staging に書いて、metadata write-back の成功後に `os.replace` で公開する。
    # 先に公開すると、2 回目の CAS で衝突したときに既存レポートを置き換えてしまう。
    staged = _stage_report(output, report.to_payload()) if output is not None else None
    try:
        if write:
            _guard_mtime(metadata_path, expected_mtime)
            payload["indicator_layout"] = layout_payload
            # #127: イベントも同じ write に入れる。`indicator_layout` だけ更新されると
            # 「どの layout で出したイベントか」が読めなくなる。差分マージはしない
            # (検出条件が変われば結果集合ごと変わるため、全件置換が正)。
            #
            # #1139: ただしユーザーが決めた切り抜き範囲 (`clip_start` / `clip_end`) は
            # 検出の再実行で消してはいけない (再検出のたびに手作業が振り出しになる)。
            # `signal_id` + `timestamp` が一致するイベントにだけ引き継ぐ。
            payload["events"] = _with_clip_overrides(
                report.events, payload.get("events")
            )
            write_metadata_atomic(metadata_path, payload)
        if staged is not None and output is not None:
            _publish_report(staged, output)
            staged = None
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)

    emit(
        {
            "type": "complete",
            **report.to_payload(),
            "wrote_metadata": write,
        }
    )
    return report


_SIGNAL_LABELS: dict[str, str] = {
    "ko_indicator": "KO",
    "assist_indicator": "ASSIST",
}


def _with_clip_overrides(
    events: list[dict[str, Any]], previous: object
) -> list[dict[str, Any]]:
    """再検出の結果に、以前のユーザー指定クリップ範囲を引き継ぐ (#1139)。

    `events[]` は全件置換が正 (検出条件が変われば集合ごと変わる) だが、
    `clip_start` / `clip_end` は**ユーザーの手作業**なので、`signal_id` と
    `timestamp` が一致するイベントにだけコピーする。両方が有限値のときだけ
    引き継ぎ、片方だけ・逆転区間は捨てる (`plan_clips` の受理条件と揃える)。
    """
    if not isinstance(previous, list):
        return events
    saved: dict[tuple[str, float], dict[str, float]] = {}
    for old in previous:
        if not isinstance(old, dict):
            continue
        signal_id = old.get("signal_id")
        timestamp = old.get("timestamp")
        clip_start = old.get("clip_start")
        clip_end = old.get("clip_end")
        if not isinstance(signal_id, str) or not isinstance(timestamp, (int, float)):
            continue
        if isinstance(timestamp, bool):
            continue
        if not isinstance(clip_start, (int, float)) or isinstance(clip_start, bool):
            continue
        if not isinstance(clip_end, (int, float)) or isinstance(clip_end, bool):
            continue
        # 手編集された JSON は 401 桁整数などを含み得る。`float()` が
        # OverflowError を投げるので、ここで閉じ込めて無視する (既存の
        # `plan_clips` の `_finite_seconds` と同じ扱い)。
        try:
            start_value = float(clip_start)
            end_value = float(clip_end)
            timestamp_value = float(timestamp)
        except (OverflowError, ValueError):
            continue
        if not (math.isfinite(start_value) and math.isfinite(end_value)):
            continue
        if not math.isfinite(timestamp_value):
            continue
        if end_value <= start_value:
            continue
        saved[(signal_id, round(timestamp_value, 2))] = {
            "clip_start": start_value,
            "clip_end": end_value,
        }
    if not saved:
        return events
    merged: list[dict[str, Any]] = []
    for event in events:
        raw_timestamp = event.get("timestamp")
        try:
            timestamp_value = (
                float(raw_timestamp) if isinstance(raw_timestamp, (int, float)) else 0.0
            )
        except (OverflowError, ValueError):
            timestamp_value = 0.0
        key = (str(event.get("signal_id")), round(timestamp_value, 2))
        override = saved.get(key)
        if override is None:
            merged.append(event)
            continue
        merged.append({**event, **override})
    return merged


def print_summary(
    report: IndicatorReport, *, wrote_metadata: bool, output: Path | None
) -> None:
    """Human-readable summary (stdout; `--json` callers skip this)."""
    events = report.events
    ko = sum(1 for event in events if event["signal_id"] == "ko_indicator")
    assist = sum(1 for event in events if event["signal_id"] == "assist_indicator")
    typer.echo(f"KO: {ko} / ASSIST: {assist} ({len(events)} intervals)")
    for event in events:
        match = event["match_index"]
        where = f"match {match}" if match is not None else "outside matches"
        # 未知 signal_id は生の id を出す (既知分だけを人間向け表記にする)。
        label = _SIGNAL_LABELS.get(event["signal_id"], event["signal_id"])
        typer.echo(
            f"  {format_hms(event['timestamp'])} - "
            f"{format_hms(event['end'])}  "
            f"{label:6s} score={event['score']:.2f}  ({where})"
        )
    if output is not None:
        typer.echo(f"events written to {output}")
    if wrote_metadata:
        typer.echo(f"indicator_layout and events written to {report.metadata_path}")


__all__ = [
    "DEFAULT_INTERVAL",
    "MIN_INTERVAL",
    "IndicatorReport",
    "calibration_timestamps",
    "register",
    "resolve_indicator_layout",
    "run_indicators",
]
