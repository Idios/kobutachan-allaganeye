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
import sys
import threading
from pathlib import Path
from typing import Annotated

import typer

from allaganeye.exceptions import (
    AllaganEyeError,
    ConfigValidationError,
)
from allaganeye.export.encoder import enumerate_h264_encoders
from allaganeye.export.pool import (
    ExportMatch,
    export_matches,
    resolve_export_output_paths,
)
from allaganeye.export.schema import ExportSummary, ProgressEvent
from allaganeye.export.wire import WireWriter
from allaganeye.detection.metadata_writer import (
    read_metadata,
    resolve_source_path,
    write_metadata_atomic,
)
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
        exclude: Annotated[
            str | None,
            typer.Option(
                "--exclude",
                help="Comma-separated 1-based match indexes to skip.",
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
        json_mode: Annotated[
            bool,
            typer.Option(
                "--json",
                help="Emit JSON Lines on stdout (GUI subprocess mode).",
            ),
        ] = False,
        expected_mtime: Annotated[
            int | None,
            typer.Option(
                "--expected-mtime",
                help=(
                    "Compare-and-swap guard (GUI subprocess mode): abort with "
                    "exit 6 if metadata.json mtime (ms) differs at write time."
                ),
            ),
        ] = None,
    ) -> None:
        """Detect / crop the minimap (area-map) window per match (#481)."""
        # P2-7: lazy import the shared error reporters to avoid circular import
        from allaganeye.cli import _report_app_error, _report_unexpected_error
        from allaganeye.commands.export import _parse_indexes_csv
        from allaganeye.video.capture_region import CaptureRegion

        if json_mode and quiet:
            raise typer.BadParameter("--json and --quiet are mutually exclusive")

        # ------ 1. read_metadata -----------------------------------------------
        try:
            metadata = read_metadata(metadata_path)
        except AllaganEyeError as e:
            _report_app_error(e, verbose=False, quiet=quiet, show_hint=False)
            raise typer.Exit(code=e.exit_code) from None

        # ------ 2. source + probe ----------------------------------------------
        try:
            # #930 B2: source 解決は 3 経路 (split --from-metadata / export /
            # minimap) 共通の helper に集約する。相対値は metadata.json の
            # ディレクトリ起点 (cwd 起点ではない) で解決するので、同じ
            # metadata から 3 経路が必ず同じ動画に着弾する。source 不在は
            # InputFileError = exit 2 で報告する (以前は ffprobe まで落ちて
            # exit 3 になっていた)。
            source_video = resolve_source_path(metadata, metadata_path)
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
            exclude_set = _parse_indexes_csv(exclude) or set()
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
                if idx in exclude_set:
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
            if json_mode:
                if hasattr(sys.stdout, "reconfigure"):
                    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
                writer = WireWriter(stream=sys.stdout)
                for mr in results:
                    r = mr.region
                    if r is None:
                        region_px = None
                        confidence = 0.0
                    else:
                        region_px = {
                            "x": round(r.x * frame_w),
                            "y": round(r.y * frame_h),
                            "w": round(r.w * frame_w),
                            "h": round(r.h * frame_h),
                        }
                        confidence = r.confidence
                    writer.emit(
                        ProgressEvent.proposal(
                            match_index=mr.match_index,
                            region=region_px,
                            confidence=confidence,
                            scattered=mr.scattered,
                        )
                    )
                raise typer.Exit(code=4)
            # else: 既存の plain-text 表示ブロック
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
                    if r is None:
                        typer.echo(
                            f"match {mr.match_index}: "
                            "領域を自動検出できませんでした "
                            "(--region X,Y,W,H で手動指定してください)"
                        )
                        continue
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

        # 出力先は sandbox 判定の基準になるので name guard より前に確定させる
        eff_output_dir = (
            output_dir if output_dir is not None else metadata_path.parent / "minimap"
        )

        # filename 衝突 guard (export と同実装) + B1 sandbox guard
        #
        # B1 (データ損失): `eff_output_dir / rendered` は -o の外へ出られる
        # (".." / 絶対パス / drive 相対 / metadata 由来の {type} 値)。minimap は
        # crop 付き再エンコードなので escape すると ffmpeg が無関係のファイルを
        # truncate してから失敗し、0 byte (moov atom not found) を残す。判定は
        # pattern 文字列ではなく解決後のパスで行う (resolve_export_output_paths)。
        # ここ (preflight) は write-back / mkdir / ffmpeg より前に落とすため、
        # export_matches 側の同じ検査は preflight を通らない caller (GUI 等) 向けの
        # 最終防壁。どちらも省略しない。
        #
        # 衝突判定も同じ「解決後パス」で行う。旧実装は sandbox を解決後パスで、
        # 衝突を rendered 文字列で判定していたため、文字列は違うが同一ファイルを
        # 指す 2 名 (Windows の大小文字違い / '..' 混じり) が両方通過し、後勝ちで
        # 片方が silent に消えていた。
        export_matches_list: list[ExportMatch] = [
            ExportMatch(
                index=idx,
                start=start_t,
                end=end_t,
                type_label=type_label,
                video_filter=crop_filter,
            )
            for idx, start_t, end_t, type_label in filtered_tuples
        ]
        try:
            resolve_export_output_paths(
                export_matches_list,
                name_pattern,
                output_dir=eff_output_dir,
                source_video=source_video,
            )
        except ConfigValidationError as e:
            _report_app_error(e, verbose=False, quiet=quiet, show_hint=False)
            raise typer.Exit(code=e.exit_code) from None

        # ------ 7. write-back (encode / mkdir 失敗でも座標は残す) -----------------
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
        # CAS guard (#893, Codex critical): re-stat right before the atomic
        # write. floor-ms must match Rust file_mtime_ms (as_millis). On mismatch
        # abort WITHOUT writing so an external edit between our read and write
        # is never clobbered (#514 class). exit 6 -> GUI ConflictModal.
        if expected_mtime is not None:
            try:
                current_mtime = metadata_path.stat().st_mtime_ns // 1_000_000
            except OSError:
                current_mtime = -1
            if current_mtime != expected_mtime:
                typer.echo(
                    "conflict: metadata.json was modified externally "
                    f"(expected mtime {expected_mtime}, got {current_mtime}); "
                    "not writing",
                    err=True,
                )
                raise typer.Exit(code=6)
        try:
            write_metadata_atomic(metadata_path, payload)
        except AllaganEyeError as e:
            _report_app_error(e, verbose=False, quiet=quiet, show_hint=False)
            raise typer.Exit(code=e.exit_code) from None

        # ------ 8. encode-prep: output_dir mkdir ------------------------------
        # mkdir runs AFTER write_metadata_atomic so that a mkdir failure still
        # leaves the minimap coordinates persisted on disk (R2-2: coordinates-
        # persist invariant: "encode 失敗でも座標は残す" applies equally to mkdir
        # failures). mkdir also runs after the CAS check so a conflict exit-6
        # never creates an empty output directory as a side-effect (F1 fix,
        # Round 1). mkdir failure surfaces as exit 1 (same convention as
        # export.py).
        try:
            eff_output_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            _report_unexpected_error(verbose=False, quiet=quiet, show_hint=False)
            raise typer.Exit(code=1) from None

        cancel_event = threading.Event()

        def _sigint_handler(signum: int, frame: object) -> None:
            cancel_event.set()

        original_handler = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, _sigint_handler)

        # Round 1 FIX 4 規約: except Exception の中では typer.Exit / typer.BadParameter
        # を raise しない。cancelled / failure の Exit は try の外で。
        summary: ExportSummary
        writer: WireWriter | None = None
        if json_mode:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
            writer = WireWriter(stream=sys.stdout)
        try:
            if json_mode:

                def progress_cb(ev: ProgressEvent) -> None:
                    assert writer is not None
                    writer.emit(ev)

            elif quiet:

                def progress_cb(ev: ProgressEvent) -> None:
                    pass

            else:

                def progress_cb(ev: ProgressEvent) -> None:
                    if ev.payload["type"] == "result":
                        # Mirrors export: wire payload stays posix for the GUI,
                        # the human line uses the platform's own separators.
                        shown = Path(str(ev.payload["output_path"]))
                        typer.echo(
                            f"[OK] match {ev.payload['match_index']:03d} "
                            f"-> {shown} ({ev.payload['encoder_used']})"
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

        if json_mode and writer is not None:
            writer.emit(ProgressEvent.summary(summary))

        # ------ 9. summary ------------------------------------------------------
        # Round 1 FIX 4: typer.Exit は P2-7 フレームの外で raise
        if summary.cancelled:
            raise typer.Exit(code=130)
        if summary.failure > 0:
            raise typer.Exit(code=1)
