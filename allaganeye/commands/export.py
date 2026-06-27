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

from allaganeye.exceptions import AllaganEyeError, ConfigValidationError
from allaganeye.export.encoder import enumerate_h264_encoders
from allaganeye.export.pool import ExportMatch, _format_filename, export_matches
from allaganeye.export.schema import ExportSummary, ProgressEvent
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
        # P2-8: read stdin as bytes and decode UTF-8 explicitly so a cp932
        # default stdin encoding (Windows) can't corrupt non-ASCII paths.
        raw = sys.stdin.buffer.read()
        return json.loads(raw.decode("utf-8"))
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
                help=(
                    "Comma-separated 1-based match indexes to include"
                    " (matches metadata 'index'; others skipped)."
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
    ) -> None:
        """Parallel H.264 / copy export from metadata.json."""
        if codec not in ("copy", "h264"):
            raise typer.BadParameter(f"--codec must be 'copy' or 'h264', got {codec!r}")
        if json_mode and quiet:
            raise typer.BadParameter("--json and --quiet are mutually exclusive")
        if concurrency is not None and concurrency <= 0:
            raise typer.BadParameter(f"--concurrency must be >= 1, got {concurrency}")

        try:
            metadata = _load_metadata(metadata_path, stdin)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
            # Round 1 FIX 1 (a): a --stdin payload of invalid bytes makes
            # sys.stdin.buffer.read().decode("utf-8") raise UnicodeDecodeError
            # (a ValueError subclass, NOT OSError/JSONDecodeError). Map it here
            # so the GUI --json --stdin path gets exit 2 + clean stderr instead
            # of a raw traceback / exit 1.
            typer.echo(f"error: cannot read metadata: {e}", err=True)
            raise typer.Exit(code=2) from e

        # Round 1 FIX 1 (b): the metadata-content parsing below (source field,
        # the include/exclude filter loop's int(raw["index"]) / float(...), and
        # the I-4 valid_indexes set comprehension) runs BEFORE the P2-7 frame and
        # can raise KeyError/ValueError/TypeError on malformed metadata. Wrap it
        # so a bad payload on the GUI --json --stdin path maps to exit 2 + clean
        # stderr instead of a raw traceback / exit 1. The existing
        # typer.Exit(code=2) (missing-source) and _parse_indexes_csv's
        # typer.BadParameter are NOT KeyError/ValueError/TypeError, so they keep
        # propagating with their own exit codes (2 / click usage).
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

            # Filter matches per include/exclude
            include_set = _parse_indexes_csv(include)
            exclude_set = _parse_indexes_csv(exclude) or set()
            all_matches = metadata.get("matches") or []
            filtered: list[ExportMatch] = []
            skipped_count = 0  # P2-9: count filtered-out matches for the summary
            for raw in all_matches:
                idx = int(raw["index"])
                # #805 Phase 1 (Codex HIGH 2): a post_match trailing segment is
                # non-destructive -- retained in metadata but EXCLUDED from MP4
                # output unconditionally. This exclusion is UNCONDITIONAL: a
                # post_match match is never exported regardless of --include or
                # --exclude, because it has no output_file and encoding it would
                # reverse the non-destructive contract. Placing this guard FIRST
                # (before include/exclude) makes the invariant explicit and
                # future-proofs against guard reordering.
                if raw.get("post_match"):
                    skipped_count += 1
                    continue
                if include_set is not None and idx not in include_set:
                    skipped_count += 1
                    continue
                if idx in exclude_set:
                    skipped_count += 1
                    continue
                if raw.get("type_override") == "skip":
                    skipped_count += 1
                    continue
                edited = raw.get("edited") or {}
                edited_start = edited.get("start_time")
                edited_end = edited.get("end_time")
                filtered.append(
                    ExportMatch(
                        index=idx,
                        start=float(
                            edited_start
                            if edited_start is not None
                            else raw["start_time"]
                        ),
                        end=float(
                            edited_end if edited_end is not None else raw["end_time"]
                        ),
                        type_label=str(raw.get("type", "match")),
                    )
                )

            # P3 I-4: warn for include/exclude indexes that match no actual match
            # (1-based). Helps catch off-by-one mistakes early.
            valid_indexes = {int(r["index"]) for r in all_matches}
            for label, given in (
                ("--include", include_set),
                ("--exclude", exclude_set),
            ):
                if given:
                    missing = sorted(given - valid_indexes)
                    if missing:
                        typer.echo(
                            f"warning: {label} index(es) not found in matches: "
                            f"{', '.join(map(str, missing))}",
                            err=True,
                        )
        except (KeyError, ValueError, TypeError) as e:
            typer.echo(f"error: invalid metadata content: {e}", err=True)
            raise typer.Exit(code=2) from e

        slots = enumerate_h264_encoders(
            vendors=vendors, preference=preference, gpu_models=gpu_models
        )
        if codec == "copy":
            # Copy mode (no re-encode) does not benefit from NVENC slots --
            # parallel ffmpeg -c copy of the same source would just thrash
            # disk I/O without throughput gain. Truncate to 1 slot.
            slots = slots[:1]
        elif concurrency is not None:
            slots = slots[:concurrency]

        # Cancel: SIGINT (Ctrl+C) -> cancel_event set -> workers stop
        cancel_event = threading.Event()

        def _sigint_handler(signum: int, frame: object) -> None:
            cancel_event.set()

        # P2-7: import the shared error reporters lazily. cli.py registers this
        # command from its module bottom (`_export_cmd.register(app)`), so a
        # top-level `from allaganeye.cli import ...` would be circular; a local
        # import matches how split/detect pull in their command impls.
        from allaganeye.cli import _report_app_error, _report_unexpected_error

        summary: ExportSummary
        original_handler = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, _sigint_handler)
        # Round 1 FIX 4 (regression guard): the `except Exception` below catches
        # ANY Exception subclass -- which includes typer.Exit (RuntimeError) and
        # typer.BadParameter (ClickException). NEVER raise either inside this
        # try: `except Exception` would swallow it and downgrade the intended
        # exit code to 1. That is why the cancelled (130) and failure (1)
        # typer.Exit raises, plus all preflight typer.Exit/typer.BadParameter,
        # live OUTSIDE (before/after) this frame -- keep them there.
        try:
            # Progress callback wiring -- construct WireWriter once for json_mode.
            # writer is always assigned when json_mode=True (initialized to None otherwise
            # to satisfy the type checker; the second use is guarded by the same condition).
            writer: WireWriter | None = None
            if json_mode:
                # P2-8: harden the wire's stdout encoding so non-ASCII output_path
                # / error_message survive a cp932 console without relying on the
                # Rust caller's PYTHONIOENCODING injection.
                if hasattr(sys.stdout, "reconfigure"):
                    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
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

            # Finding 3 (was P3 I-3 warning): a name pattern without {idx}/{idx:03}
            # maps every match to the same output file -- overwrite, parallel-write
            # race, and a misleading "success" summary. Fail hard BEFORE any ffmpeg
            # work (inside the P2-7 frame -> exit 5, clean stderr, no summary line).
            seen_names: dict[str, int] = {}
            for m in filtered:
                name = _format_filename(m, name_pattern)
                seen_names[name] = seen_names.get(name, 0) + 1
            collisions = [n for n, c in seen_names.items() if c > 1]
            if collisions:
                raise ConfigValidationError(
                    "name pattern produces duplicate output filenames "
                    f"(e.g. {collisions[0]!r}); add {{idx}} or {{idx:03}} to the "
                    "--name-pattern"
                )

            # P2-10: create the output dir up front (mirrors split/detect).
            # Without this every match's ffmpeg fails to write and the run
            # exits 1. The mkdir OSError rides the P2-7 error frame below.
            output_dir.mkdir(parents=True, exist_ok=True)
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
            # P2-9: reflect filtered-out matches in the summary (was always 0).
            summary.skipped = skipped_count
        except AllaganEyeError as e:
            # P2-7: do NOT emit a summary here -- start_export treats any summary
            # line as success (lib.rs) and would mask the error in the GUI. A
            # clean stderr + mapped non-zero exit is the correct wire signal for
            # a hard error.
            _report_app_error(e, verbose=False, quiet=quiet, show_hint=False)
            raise typer.Exit(code=e.exit_code) from None
        except Exception:
            _report_unexpected_error(verbose=False, quiet=quiet, show_hint=False)
            raise typer.Exit(code=1) from None
        finally:
            signal.signal(signal.SIGINT, original_handler)

        # Emit summary as last JSON line; reuse the writer constructed above
        if json_mode and writer is not None:
            writer.emit(ProgressEvent.summary(summary))

        # Round 1 FIX 4: these typer.Exit raises are intentionally OUTSIDE the
        # P2-7 try -- raising them inside would be swallowed by `except Exception`
        # and downgraded to exit 1 (130/1 would be lost).
        if summary.cancelled:
            raise typer.Exit(code=130)
        if summary.failure > 0:
            raise typer.Exit(code=1)
