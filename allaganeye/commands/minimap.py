"""``allaganeye minimap`` Typer command (#481).

metadata.json を入力に、試合ごとにエリアマップ window (通称 minimap) 領域を
検出して minimap_regions に永続化し、crop + h264 の切抜き MP4 を出力する。

Mode:
- 提案モード (--region 未指定): resolve_match_regions で領域を検出し
  ``--region X,Y,W,H`` 形式のコピペ可能な提案を表示する。常に exit 4。
- crop モード (--region "X,Y,W,H"): 指定領域で全試合を切り抜いて MP4 出力する。
"""

from __future__ import annotations

import signal
import threading
from pathlib import Path
from typing import Annotated

import typer

from allaganeye.exceptions import (
    AllaganEyeError,
    ConfigValidationError,
)
from allaganeye.export.encoder import enumerate_h264_encoders
from allaganeye.export.pool import ExportMatch, _format_filename, export_matches
from allaganeye.export.schema import ExportSummary, ProgressEvent
from allaganeye.video.areamap import resolve_match_regions
from allaganeye.video.probe import probe_video


def register(app: typer.Typer) -> None:
    """Wire the minimap command onto ``app`` (called from cli.py)."""

    @app.command(name="minimap")
    def minimap(
        metadata_path: Annotated[
            Path,
            typer.Argument(
                exists=False,
                help="Path to metadata.json produced by `allaganeye detect`.",
            ),
        ],
        output_dir: Annotated[
            Path | None,
            typer.Option(
                "--output-dir",
                "-o",
                help=(
                    "Output directory for minimap MP4 files. "
                    "Default: <metadata dir>/minimap."
                ),
            ),
        ] = None,
        region: Annotated[
            str | None,
            typer.Option(
                "--region",
                help=(
                    "Minimap region as pixel coordinates: X,Y,W,H "
                    "(top-left origin). When omitted, runs in proposal mode "
                    "(detects and prints the region; does not encode)."
                ),
            ),
        ] = None,
        include: Annotated[
            str | None,
            typer.Option(
                "--include",
                help=(
                    "Comma-separated 1-based match indexes to include "
                    "(same semantics as `allaganeye export --include`)."
                ),
            ),
        ] = None,
        name_pattern: Annotated[
            str,
            typer.Option(
                "--name-pattern",
                help=(
                    "Output filename pattern. "
                    "Tokens: {idx} {idx:03} {type} {start} {date}."
                ),
            ),
        ] = "{idx:03}_{type}_{start}_minimap.mp4",
        quiet: Annotated[
            bool,
            typer.Option("--quiet", help="Suppress progress output."),
        ] = False,
    ) -> None:
        """Detect / crop the minimap (area-map) window per match (#481)."""
        # P2-7: lazy import the shared error reporters to avoid circular import
        from allaganeye.cli import _report_app_error, _report_unexpected_error
        from allaganeye.commands.export import _parse_indexes_csv
        from allaganeye.detection.metadata_writer import (
            read_metadata,
            write_metadata_atomic,
        )
        from allaganeye.video.capture_region import CaptureRegion

        # ------ 1. read_metadata -----------------------------------------------
        try:
            metadata = read_metadata(metadata_path)
        except AllaganEyeError as e:
            _report_app_error(e, verbose=False, quiet=quiet, show_hint=False)
            raise typer.Exit(code=e.exit_code) from None

        # ------ 2. source + probe ----------------------------------------------
        try:
            source_value = metadata.get("source")
            if not source_value:
                typer.echo(
                    "error: metadata.json missing required 'source' field", err=True
                )
                raise typer.Exit(code=2)
            source_video = Path(source_value)
            sys_info = metadata.get("system_info") or {}
            vendors = list(sys_info.get("gpu_vendors_available") or [])
            preference = list(
                sys_info.get("vendor_preference") or ["nvidia", "amd", "intel"]
            )
            gpu_models = list(sys_info.get("gpu") or [])

            probe = probe_video(source_video)
            frame_w: int = probe["width"]
            frame_h: int = probe["height"]

            # ------ 3. match filter (export と同順) ----------------------------
            include_set = _parse_indexes_csv(include)
            all_matches = metadata.get("matches") or []
            filtered_tuples: list[tuple[int, float, float, str]] = []
            # (index, start, end, type_label) for filtered matches
            for raw in all_matches:
                idx = int(raw["index"])
                # post_match は無条件除外 (include より優先、#805 Phase 1 契約)
                if raw.get("post_match"):
                    if include_set is not None and idx in include_set:
                        typer.echo(
                            f"warning: --include index {idx} is a post-match trailing "
                            f"segment (excluded from minimap output, #805)",
                            err=True,
                        )
                    continue
                if include_set is not None and idx not in include_set:
                    continue
                if raw.get("type_override") == "skip":
                    continue
                edited = raw.get("edited") or {}
                edited_start = edited.get("start_time")
                edited_end = edited.get("end_time")
                start_t = float(
                    edited_start if edited_start is not None else raw["start_time"]
                )
                end_t = float(edited_end if edited_end is not None else raw["end_time"])
                type_label = str(raw.get("type", "match"))
                filtered_tuples.append((idx, start_t, end_t, type_label))

        except AllaganEyeError as e:
            _report_app_error(e, verbose=False, quiet=quiet, show_hint=False)
            raise typer.Exit(code=e.exit_code) from None
        except (KeyError, ValueError, TypeError) as e:
            typer.echo(f"error: invalid metadata content: {e}", err=True)
            raise typer.Exit(code=2) from e

        # ------ 4a. 提案モード (--region なし) ----------------------------------
        if region is None:
            try:
                match_tuples = [(idx, s, e) for idx, s, e, _ in filtered_tuples]
                results, warns = resolve_match_regions(source_video, match_tuples)
            except AllaganEyeError as e:
                _report_app_error(e, verbose=False, quiet=quiet, show_hint=False)
                raise typer.Exit(code=e.exit_code) from None
            for w in warns:
                typer.echo(w, err=True)
            if not results:
                typer.echo(
                    "提案なし: ミニマップ領域を自動検出できませんでした。", err=False
                )
                typer.echo(
                    "hint: --region X,Y,W,H を指定して手動でクロップ領域を指定してください。",
                    err=False,
                )
            else:
                for mr in results:
                    r = mr.region
                    # pixel 換算 (そのまま --region に貼れる値)
                    px = round(r.x * frame_w)
                    py = round(r.y * frame_h)
                    pw = round(r.w * frame_w)
                    ph = round(r.h * frame_h)
                    line = (
                        f"match {mr.match_index}: "
                        f"--region {px},{py},{pw},{ph} "
                        f"(confidence {r.confidence:.2f})"
                    )
                    if mr.scattered:
                        line += " [警告: 試合中に領域が揺れています]"
                    typer.echo(line)
                typer.echo(
                    "\nhint: crop の実行には --region X,Y,W,H を指定してください。",
                    err=False,
                )
            # 提案モードは常に DetectionError (exit 4)
            # Round 1 FIX 4 規約: typer.Exit は except Exception の外で raise
            raise typer.Exit(code=4)

        # ------ 4b. crop モード (--region "X,Y,W,H") ---------------------------
        # validation エラーは ConfigValidationError (exit 5) として処理
        def _parse_region(
            region_str: str, fw: int, fh: int
        ) -> tuple[int, int, int, int]:
            """--region "X,Y,W,H" を parse + validation。失敗時は ConfigValidationError。"""
            parts = region_str.split(",")
            if len(parts) != 4:
                raise ConfigValidationError(
                    f"--region must be X,Y,W,H (4 integers), got {region_str!r}"
                )
            try:
                rx_, ry_, rw_, rh_ = (int(p) for p in parts)
            except ValueError as exc:
                raise ConfigValidationError(
                    f"--region values must be integers: {exc}"
                ) from exc
            if rx_ < 0 or ry_ < 0 or rw_ < 0 or rh_ < 0:
                raise ConfigValidationError(
                    f"--region values must be non-negative, got {region_str!r}"
                )
            if rw_ < 16:
                raise ConfigValidationError(f"--region width must be >= 16, got {rw_}")
            if rh_ < 16:
                raise ConfigValidationError(f"--region height must be >= 16, got {rh_}")
            if rx_ + rw_ > fw:
                raise ConfigValidationError(
                    f"--region x+w ({rx_}+{rw_}={rx_ + rw_}) exceeds frame width ({fw})"
                )
            if ry_ + rh_ > fh:
                raise ConfigValidationError(
                    f"--region y+h ({ry_}+{rh_}={ry_ + rh_}) exceeds frame height ({fh})"
                )
            return rx_, ry_, rw_, rh_

        try:
            rx, ry, rw, rh = _parse_region(region, frame_w, frame_h)
        except ConfigValidationError as e:
            _report_app_error(e, verbose=False, quiet=quiet, show_hint=False)
            raise typer.Exit(code=e.exit_code) from None

        # ------ 5. crop 文字列生成 (mod-2 化 + clamp) --------------------------
        # mod-2 化: codec が yuv420p を要求するため
        crop_w = rw - (rw % 2)
        crop_h = rh - (rh % 2)
        # clamp: x+w がフレームを超えないよう
        crop_x = min(rx, frame_w - crop_w)
        crop_y = min(ry, frame_h - crop_h)
        crop_filter = f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y}"

        # ------ 6. encode -------------------------------------------------------
        slots = enumerate_h264_encoders(
            vendors=vendors, preference=preference, gpu_models=gpu_models
        )

        # filename 衝突 guard (export と同実装)
        seen_names: dict[str, int] = {}
        export_matches_list: list[ExportMatch] = []
        for idx, start_t, end_t, type_label in filtered_tuples:
            em = ExportMatch(
                index=idx,
                start=start_t,
                end=end_t,
                type_label=type_label,
                video_filter=crop_filter,
            )
            name = _format_filename(em, name_pattern)
            seen_names[name] = seen_names.get(name, 0) + 1
            export_matches_list.append(em)

        collisions = [n for n, c in seen_names.items() if c > 1]
        if collisions:
            collision_err = ConfigValidationError(
                "name pattern produces duplicate output filenames "
                f"(e.g. {collisions[0]!r}); add {{idx}} or {{idx:03}} to the "
                "--name-pattern"
            )
            _report_app_error(
                collision_err, verbose=False, quiet=quiet, show_hint=False
            )
            raise typer.Exit(code=collision_err.exit_code) from None

        eff_output_dir = (
            output_dir if output_dir is not None else metadata_path.parent / "minimap"
        )

        # ------ 7. preflight: output_dir mkdir --------------------------------
        # Finding 2 fix: 決定的 preflight (collision check 済み) を write より前に実行
        # mkdir 失敗は except Exception で exit 1 になる (export.py と同規約)
        try:
            eff_output_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            from allaganeye.cli import _report_unexpected_error

            _report_unexpected_error(verbose=False, quiet=quiet, show_hint=False)
            raise typer.Exit(code=1) from None

        # ------ 8. write-back (encode 失敗でも座標は残す) ----------------------
        # Finding 1 fix: filtered set の entry は上書き、対象外の既存 entry は保全
        # (match_index merge)。malformed entry (dict でない / match_index 欠落) も
        # 黙って捨てずにそのまま保全する (round-trip 哲学)。
        norm_region = CaptureRegion(
            x=rx / frame_w,
            y=ry / frame_h,
            w=crop_w / frame_w,
            h=crop_h / frame_h,
            confidence=1.0,
            source="manual",
        )
        # filtered の match_index -> 新 entry dict
        new_entries_by_idx: dict[int, dict] = {
            idx: {"match_index": idx, "region": norm_region.to_dict()}
            for idx, _, _, _ in filtered_tuples
        }
        filtered_idx_set: set[int] = set(new_entries_by_idx)
        # 既存 minimap_regions を読んでマージ
        existing_regions: list = list(metadata.get("minimap_regions") or [])
        preserved: list[dict] = []
        for entry in existing_regions:
            if isinstance(entry, dict):
                try:
                    midx = int(entry["match_index"])
                except (KeyError, TypeError, ValueError):
                    # match_index 取得不能: malformed として保全
                    preserved.append(entry)
                    continue
                if midx not in filtered_idx_set:
                    # 対象外 match: 既存 entry を保全
                    preserved.append(entry)
                # 対象 match は new_entries_by_idx で上書きするためここでは追加しない
            else:
                # dict でない malformed entry: そのまま保全
                preserved.append(entry)  # type: ignore[arg-type]

        # merge: 保全 entry + 新 entry を match_index 昇順に並べる
        # (malformed は先頭に集める: dict かつ int match_index を持つものだけで昇順)
        def _sort_key(e: object) -> tuple[int, int]:
            if isinstance(e, dict):
                try:
                    return (1, int(e["match_index"]))
                except (KeyError, TypeError, ValueError):
                    pass
            return (0, 0)

        minimap_entries: list = sorted(
            preserved + list(new_entries_by_idx.values()),
            key=_sort_key,
        )
        payload = dict(metadata)
        payload["minimap_regions"] = minimap_entries
        try:
            write_metadata_atomic(metadata_path, payload)
        except AllaganEyeError as e:
            _report_app_error(e, verbose=False, quiet=quiet, show_hint=False)
            raise typer.Exit(code=e.exit_code) from None

        cancel_event = threading.Event()

        def _sigint_handler(signum: int, frame: object) -> None:
            cancel_event.set()

        original_handler = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, _sigint_handler)

        # Round 1 FIX 4 規約: except Exception の中では typer.Exit / typer.BadParameter
        # を raise しない。cancelled / failure の Exit は try の外で。
        summary: ExportSummary
        try:
            if quiet:

                def progress_cb(ev: ProgressEvent) -> None:
                    pass

            else:

                def progress_cb(ev: ProgressEvent) -> None:
                    if ev.payload["type"] == "result":
                        typer.echo(
                            f"[OK] match {ev.payload['match_index']:03d} "
                            f"-> {ev.payload['output_path']} ({ev.payload['encoder_used']})"
                        )
                    elif ev.payload["type"] == "error":
                        typer.echo(
                            f"[FAIL] match {ev.payload['match_index']:03d}: "
                            f"{ev.payload['error_message']}",
                            err=True,
                        )
                    elif ev.payload["type"] == "fallback":
                        typer.echo(
                            f"[fallback] match {ev.payload['match_index']:03d}: "
                            f"{ev.payload['fallback_from']} -> {ev.payload['fallback_to']}",
                            err=True,
                        )

            summary = export_matches(
                matches=export_matches_list,
                slots=slots,
                source_video=source_video,
                output_dir=eff_output_dir,
                codec="h264",
                name_pattern=name_pattern,
                progress_cb=progress_cb,
                cancel_event=cancel_event,
            )
        except AllaganEyeError as e:
            _report_app_error(e, verbose=False, quiet=quiet, show_hint=False)
            raise typer.Exit(code=e.exit_code) from None
        except Exception:
            _report_unexpected_error(verbose=False, quiet=quiet, show_hint=False)
            raise typer.Exit(code=1) from None
        finally:
            signal.signal(signal.SIGINT, original_handler)

        # ------ 8. summary ------------------------------------------------------
        # Round 1 FIX 4: typer.Exit は P2-7 フレームの外で raise
        if summary.cancelled:
            raise typer.Exit(code=130)
        if summary.failure > 0:
            raise typer.Exit(code=1)
