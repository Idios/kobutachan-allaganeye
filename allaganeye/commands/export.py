"""``allaganeye export`` Typer command (#761).

Reads metadata.json (positional or --stdin), enumerates encoder slots,
runs ``export_matches`` (parallel), and emits progress.

Mode:
- default        rich text progress bars (single-line replace)
- --json         JSON Lines on stdout (used by GUI Tauri subprocess)
- --quiet        suppress all progress output
"""

from __future__ import annotations

import json
import signal
import sys
import threading
from pathlib import Path
from typing import Annotated

import typer

from allaganeye.export.encoder import enumerate_h264_encoders
from allaganeye.export.pool import ExportMatch, export_matches
from allaganeye.export.schema import ProgressEvent
from allaganeye.export.wire import WireWriter


def _parse_indexes_csv(value: str | None) -> set[int] | None:
    if value is None or not value.strip():
        return None
    out: set[int] = set()
    for tok in value.split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            out.add(int(tok))
        except ValueError as e:
            raise typer.BadParameter(f"invalid index token: {tok!r}") from e
    return out


def _load_metadata(metadata_path: Path | None, use_stdin: bool) -> dict:
    if use_stdin:
        if metadata_path is not None:
            raise typer.BadParameter("--stdin is mutually exclusive with metadata_path")
        return json.load(sys.stdin)
    if metadata_path is None:
        raise typer.BadParameter("metadata_path is required unless --stdin is set")
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def register(app: typer.Typer) -> None:
    """Wire the export command onto ``app`` (called from cli.py)."""

    @app.command(name="export")
    def export(
        metadata_path: Annotated[
            Path | None,
            typer.Argument(
                exists=False, help="Path to metadata.json. Omit with --stdin."
            ),
        ] = None,
        stdin: Annotated[
            bool,
            typer.Option(
                "--stdin", help="Read metadata JSON from stdin (GUI subprocess mode)."
            ),
        ] = False,
        output_dir: Annotated[
            Path,
            typer.Option(
                "--output-dir", "-o", help="Output directory for split MP4 files."
            ),
        ] = ...,  # type: ignore[assignment]
        codec: Annotated[
            str,
            typer.Option(
                "--codec", help="Codec mode: 'copy' (no re-encode) or 'h264'."
            ),
        ] = "copy",
        concurrency: Annotated[
            int | None,
            typer.Option(
                "--concurrency",
                help="Override slot count (default: auto from SKU table).",
            ),
        ] = None,
        name_pattern: Annotated[
            str,
            typer.Option(
                "--name-pattern",
                help="Output filename pattern. Tokens: {idx} {idx:03} {type} {start} {date}.",
            ),
        ] = "{idx:03}_{type}_{start}.mp4",
        quiet: Annotated[
            bool,
            typer.Option("--quiet", help="Suppress progress output."),
        ] = False,
        json_mode: Annotated[
            bool,
            typer.Option(
                "--json", help="Emit JSON Lines on stdout (GUI subprocess mode)."
            ),
        ] = False,
        include: Annotated[
            str | None,
            typer.Option(
                "--include",
                help="Comma-separated match indexes to include (others skipped).",
            ),
        ] = None,
        exclude: Annotated[
            str | None,
            typer.Option("--exclude", help="Comma-separated match indexes to skip."),
        ] = None,
    ) -> None:
        """Parallel H.264 / copy export from metadata.json."""
        if codec not in ("copy", "h264"):
            raise typer.BadParameter(f"--codec must be 'copy' or 'h264', got {codec!r}")
        if json_mode and quiet:
            raise typer.BadParameter("--json and --quiet are mutually exclusive")

        try:
            metadata = _load_metadata(metadata_path, stdin)
        except (OSError, json.JSONDecodeError) as e:
            typer.echo(f"error: cannot read metadata: {e}", err=True)
            raise typer.Exit(code=2) from e

        source_video = Path(metadata["source"])
        sys_info = metadata.get("system_info") or {}
        vendors = list(sys_info.get("gpu_vendors_available") or [])
        preference = list(
            sys_info.get("vendor_preference") or ["nvidia", "amd", "intel"]
        )
        gpu_models = list(sys_info.get("gpu") or [])

        # Filter matches per include/exclude
        include_set = _parse_indexes_csv(include)
        exclude_set = _parse_indexes_csv(exclude) or set()
        all_matches = metadata.get("matches") or []
        filtered: list[ExportMatch] = []
        for raw in all_matches:
            idx = int(raw["index"])
            if include_set is not None and idx not in include_set:
                continue
            if idx in exclude_set:
                continue
            if raw.get("type_override") == "skip":
                continue
            filtered.append(
                ExportMatch(
                    index=idx,
                    start=float(
                        raw.get("edited", {}).get("start_time") or raw["start_time"]
                    ),
                    end=float(raw.get("edited", {}).get("end_time") or raw["end_time"]),
                    type_label=str(raw.get("type", "match")),
                )
            )

        slots = enumerate_h264_encoders(
            vendors=vendors, preference=preference, gpu_models=gpu_models
        )
        if concurrency is not None and concurrency > 0:
            slots = slots[:concurrency]

        # Cancel: SIGINT (Ctrl+C) → cancel_event set → workers stop
        cancel_event = threading.Event()

        def _sigint_handler(signum: int, frame: object) -> None:
            cancel_event.set()

        signal.signal(signal.SIGINT, _sigint_handler)

        # Progress callback wiring — construct WireWriter once for json_mode.
        # writer is always assigned when json_mode=True (initialized to None otherwise
        # to satisfy the type checker; the second use is guarded by the same condition).
        writer: WireWriter | None = None
        if json_mode:
            writer = WireWriter(stream=sys.stdout)

            def progress_cb(ev: ProgressEvent) -> None:
                assert writer is not None
                writer.emit(ev)

        elif quiet:

            def progress_cb(ev: ProgressEvent) -> None:
                pass

        else:
            # Plain text mode: 1 line per match start/done; no rich here to keep deps light
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
            matches=filtered,
            slots=slots,
            source_video=source_video,
            output_dir=output_dir,
            codec=codec,
            name_pattern=name_pattern,
            progress_cb=progress_cb,
            cancel_event=cancel_event,
        )

        # Emit summary as last JSON line; reuse the writer constructed above
        if json_mode and writer is not None:
            writer.emit(ProgressEvent.summary(summary))

        if summary.cancelled:
            raise typer.Exit(code=130)
        if summary.failure > 0:
            raise typer.Exit(code=1)
