"""``allaganeye clips`` Typer command (#135 / #1050 Phase A)。

`allaganeye indicators` が metadata.json に書いた `events[]` を、**前後マージン付きの
切り抜きクリップ**へ変換して元録画から書き出す。切り出しは ``export`` と同じ
`export_matches` (並列 / encoder fallback / path sandbox) を再利用する。

決定事項 (Idios 判断 2026-11-16):

- 既定は ``--codec copy`` (無劣化・キーフレーム丸め)。``--codec h264`` で再エンコード
- 近接イベントは `--gap` (既定 5 秒) 以内なら 1 本に束ねる
- 前後マージンは `--pre` / `--post` (既定 10 秒ずつ)
- 範囲は試合区間にクランプする
"""

from __future__ import annotations

import math
import signal
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Annotated, Any

import typer

from allaganeye.detection.format import format_hms
from allaganeye.detection.metadata_writer import read_metadata, resolve_source_path
from allaganeye.exceptions import (
    AllaganEyeError,
    ConfigValidationError,
    InputFileError,
)
from allaganeye.export.clips import (
    DEFAULT_GAP_SECONDS,
    DEFAULT_POST_SECONDS,
    DEFAULT_PRE_SECONDS,
    Clip,
    ClipPlan,
    plan_clips,
)
from allaganeye.export.encoder import enumerate_h264_encoders
from allaganeye.export.pool import ExportMatch, export_matches, resolve_output_paths
from allaganeye.export.schema import ExportSummary, ProgressEvent
from allaganeye.export.wire import WireWriter

DEFAULT_NAME_PATTERN = "clip_{idx:03}_{type}_{start}.mp4"
"""既定のファイル名。`{idx}` はクリップ番号 (1 始まり)。"""

CLIP_CODECS = ("copy", "h264")
"""`--codec` の受理値。"""


def _require_non_negative(name: str, value: float) -> float:
    if not math.isfinite(value) or value < 0:
        raise ConfigValidationError(
            f"{name} must be a finite number >= 0, got {value!r}"
        )
    return float(value)


def load_clip_plan(
    metadata_path: Path,
    *,
    pre: float,
    post: float,
    gap: float,
) -> tuple[dict[str, Any], ClipPlan]:
    """metadata.json を読み、クリップ計画まで作る (ffmpeg は起動しない)。"""
    _require_non_negative("--pre", pre)
    _require_non_negative("--post", post)
    _require_non_negative("--gap", gap)

    payload = read_metadata(metadata_path)
    events = payload.get("events")
    if not isinstance(events, list) or not events:
        raise InputFileError(
            f"{metadata_path} has no events; run "
            f"`allaganeye indicators {metadata_path}` first "
            "(L4 events are required to plan clips)"
        )
    matches = payload.get("matches")
    if matches is None:
        matches = []
    if not isinstance(matches, list):
        # 手編集された metadata。ここで弾かないと planner で TypeError になり
        # 入力エラー (exit 2) ではなく汎用失敗 (exit 1) に落ちる。
        raise InputFileError(
            f"{metadata_path}: 'matches' must be a list, got {type(matches).__name__}"
        )
    plan = plan_clips(events, matches, pre=pre, post=post, gap=gap)
    return payload, plan


def _clip_matches(clips: Sequence[Clip]) -> list[ExportMatch]:
    """クリップ計画を `export_matches` の入力へ写す。"""
    return [
        ExportMatch(
            index=clip.index,
            start=clip.start,
            end=clip.end,
            type_label=clip.type_label,
        )
        for clip in clips
    ]


def _string_list(value: object) -> list[str]:
    """metadata 由来の「文字列の配列」を安全に読む (壊れていれば空扱い)。

    `system_info` は GUI / 手編集で壊れうる。`list(1)` の TypeError や
    `None.lower()` の AttributeError をここで閉じ込める。
    """
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def run_clip_plan(
    plan: ClipPlan,
    payload: Mapping[str, Any],
    *,
    metadata_path: Path,
    output_dir: Path | None,
    codec: str,
    name_pattern: str,
    concurrency: int | None,
    overwrite: bool,
    emit: Callable[[dict[str, Any]], None],
    progress: Callable[[str], None],
    cancel_event: threading.Event,
) -> ExportSummary:
    """計画済みのクリップを書き出す。`AllaganEyeError` は呼び出し側が exit code に写す。"""
    if codec not in CLIP_CODECS:
        raise ConfigValidationError(
            f"--codec must be one of {', '.join(CLIP_CODECS)}, got {codec!r}"
        )
    if concurrency is not None and concurrency < 1:
        raise ConfigValidationError(f"--concurrency must be >= 1, got {concurrency!r}")

    source = resolve_source_path(payload, metadata_path)
    if plan.outside_events:
        progress(
            f"warning: {plan.outside_events} event(s) fall outside every match "
            "and were skipped (a clip range cannot be clamped to a match)"
        )
    if plan.merged_events:
        progress(f"{plan.merged_events} event(s) were merged into a neighbouring clip")
    if not plan.clips:
        progress("no clips to write (no events inside match intervals)")
        summary = ExportSummary()
        emit(ProgressEvent.summary(summary).payload)
        return summary

    target_dir = (
        output_dir if output_dir is not None else metadata_path.parent / "clips"
    )

    raw_sys_info = payload.get("system_info")
    sys_info = raw_sys_info if isinstance(raw_sys_info, Mapping) else {}
    slots = enumerate_h264_encoders(
        vendors=_string_list(sys_info.get("gpu_vendors_available")),
        preference=_string_list(sys_info.get("vendor_preference"))
        or ["nvidia", "amd", "intel"],
        gpu_models=_string_list(sys_info.get("gpu")),
    )
    if codec == "copy":
        # copy はエンコーダを使わない。並列にしても同じ入力の I/O を奪い合うだけ。
        slots = slots[:1]
    elif concurrency is not None:
        slots = slots[:concurrency]

    matches = _clip_matches(plan.clips)
    # ffmpeg を 1 本も起動する前に sandbox を検証する (export と同じ二段構え)。
    paths = resolve_output_paths(
        matches, name_pattern, output_dir=target_dir, source_video=source
    )
    # 既定では既存ファイルを置き換えない。共有 runner は ffmpeg `-y` で開いた
    # 瞬間に truncate するので、再実行が途中で失敗 / 中断すると前回のクリップが
    # 壊れたまま残る (export の既知の挙動)。新しい書込経路では既定で拒否する。
    existing = [path for path in paths if path.exists()]
    if existing and not overwrite:
        raise ConfigValidationError(
            f"{len(existing)} clip output(s) already exist (e.g. {existing[0]}); "
            "pass --overwrite to replace them, or choose another --output-dir. "
            "A re-run that fails halfway would otherwise destroy the clips "
            "written by the previous run"
        )
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        # `-o` が既存ファイル / 祖先がファイル / 書込み不可などは CLI の入力エラーに
        # 写す。ここで OSError を漏らすと traceback + exit 1 になり、`--json` の
        # 呼び手 (GUI) には何も返らない。
        raise ConfigValidationError(
            f"cannot create output directory {target_dir}: {exc}"
        ) from exc

    summary = export_matches(
        matches=matches,
        slots=slots,
        source_video=source,
        output_dir=target_dir,
        codec=codec,
        name_pattern=name_pattern,
        progress_cb=lambda event: emit(event.payload),
        cancel_event=cancel_event,
    )
    emit(ProgressEvent.summary(summary).payload)
    return summary


def register(app: typer.Typer) -> None:
    """Wire the clips command onto ``app`` (called from cli.py)."""

    @app.command(name="clips")
    def clips(
        metadata_path: Annotated[
            Path,
            typer.Argument(
                exists=False,
                help="Path to metadata.json that already has L4 `events`.",
            ),
        ],
        output_dir: Annotated[
            Path | None,
            typer.Option(
                "--output-dir",
                "-o",
                help="Directory for the clip files (default: <metadata dir>/clips).",
            ),
        ] = None,
        pre: Annotated[
            float,
            typer.Option(
                "--pre",
                help=f"Seconds before the event (default {DEFAULT_PRE_SECONDS}).",
            ),
        ] = DEFAULT_PRE_SECONDS,
        post: Annotated[
            float,
            typer.Option(
                "--post",
                help=f"Seconds after the event (default {DEFAULT_POST_SECONDS}).",
            ),
        ] = DEFAULT_POST_SECONDS,
        gap: Annotated[
            float,
            typer.Option(
                "--gap",
                help=(
                    "Merge events starting within this many seconds of the "
                    f"current clip end (default {DEFAULT_GAP_SECONDS})."
                ),
            ),
        ] = DEFAULT_GAP_SECONDS,
        codec: Annotated[
            str,
            typer.Option(
                "--codec",
                help=(
                    "'copy' (lossless, keyframe-snapped) or 'h264' "
                    "(re-encode, frame-exact boundaries)."
                ),
            ),
        ] = "copy",
        name_pattern: Annotated[
            str,
            typer.Option(
                "--name-pattern",
                help="Tokens: {idx}, {idx:03}, {type}, {start}, {date}.",
            ),
        ] = DEFAULT_NAME_PATTERN,
        concurrency: Annotated[
            int | None,
            typer.Option(
                "--concurrency",
                help="Max parallel encoders for --codec h264 (default: all slots).",
            ),
        ] = None,
        overwrite: Annotated[
            bool,
            typer.Option(
                "--overwrite",
                help=(
                    "Replace clips that already exist at the rendered paths. "
                    "Without this, an existing output aborts the run (exit 5)."
                ),
            ),
        ] = False,
        json_output: Annotated[
            bool,
            typer.Option(
                "--json",
                help="Emit JSON Lines on stdout (same wire shape as `export`).",
            ),
        ] = False,
        quiet: Annotated[
            bool,
            typer.Option("--quiet", help="Suppress progress output."),
        ] = False,
    ) -> None:
        """Cut highlight clips around L4 events (KO / ASSIST)."""

        if json_output and quiet:
            raise typer.BadParameter("--json and --quiet are mutually exclusive")

        writer: WireWriter | None = None
        if json_output:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
            writer = WireWriter(stream=sys.stdout)

        by_index: dict[int, Clip] = {}

        def emit(payload: dict[str, Any]) -> None:
            if writer is not None:
                writer.emit(ProgressEvent(payload))

        def progress(message: str) -> None:
            if not json_output and not quiet:
                typer.echo(message, err=True)

        def human_progress(payload: dict[str, Any]) -> None:
            if quiet:
                return
            kind = payload.get("type")
            if kind == "result":
                clip = by_index.get(payload["match_index"])
                where = ""
                if clip is not None:
                    where = (
                        f"{format_hms(clip.start)}-{format_hms(clip.end)} "
                        f"{clip.type_label} {clip.duration:.1f}s "
                    )
                typer.echo(
                    f"[OK] clip {payload['match_index']:03d} {where}"
                    f"-> {Path(str(payload['output_path']))} ({payload['encoder_used']})"
                )
            elif kind == "error":
                typer.echo(
                    f"[FAIL] clip {payload['match_index']:03d}: "
                    f"{payload['error_message']}",
                    err=True,
                )
            elif kind == "fallback":
                typer.echo(
                    f"[fallback] clip {payload['match_index']:03d}: "
                    f"{payload['fallback_from']} -> {payload['fallback_to']}",
                    err=True,
                )

        emitter = emit if json_output else human_progress

        cancel_event = threading.Event()
        original_handler = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, lambda signum, frame: cancel_event.set())
        summary: ExportSummary | None = None
        try:
            payload, plan = load_clip_plan(metadata_path, pre=pre, post=post, gap=gap)
            by_index.update({clip.index: clip for clip in plan.clips})
            summary = run_clip_plan(
                plan,
                payload,
                metadata_path=metadata_path,
                output_dir=output_dir,
                codec=codec,
                name_pattern=name_pattern,
                concurrency=concurrency,
                overwrite=overwrite,
                emit=emitter,
                progress=progress,
                cancel_event=cancel_event,
            )
        except AllaganEyeError as e:
            if writer is not None:
                writer.emit(ProgressEvent({"type": "error", "message": str(e)}))
            progress(f"Error: {e}")
            raise typer.Exit(code=e.exit_code) from None
        finally:
            signal.signal(signal.SIGINT, original_handler)

        if summary is None:  # pragma: no cover - AllaganEyeError path raises above
            raise typer.Exit(code=1)
        if summary.cancelled:
            raise typer.Exit(code=130)
        if summary.failure:
            raise typer.Exit(code=1)


__all__ = [
    "CLIP_CODECS",
    "DEFAULT_NAME_PATTERN",
    "load_clip_plan",
    "register",
    "run_clip_plan",
]
