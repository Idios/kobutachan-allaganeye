"""CLI entry point for Allagan Eye."""

import sys
import traceback
from pathlib import Path
from typing import Annotated

import click
import typer

from allaganeye import __version__
from allaganeye.config import SUPPORTED_EXTENSIONS, SplitConfig
from allaganeye.exceptions import (
    AllaganEyeError,
    ConfigValidationError,
    InputFileError,
    IntegrityError,
)

_VERBOSE_HINT = "  (Run with -v / --verbose for full details)"

app = typer.Typer(
    name="allaganeye",
    help="FF14 Frontline video auto-highlight extraction tool.",
    no_args_is_help=True,
)


def version_callback(value: bool) -> None:
    if not value:
        return
    # #668 -- verify bundled files before reporting version. Skipped via
    # ``ALLAGANEYE_INTEGRITY_SKIP=1`` for dev installs (handled inside
    # integrity.check). Production Portable ZIP runs the check and exits
    # with code 7 on bundled-file corruption / deletion.
    from allaganeye import integrity

    try:
        integrity.check()
    except IntegrityError as exc:
        typer.echo(f"error: {exc}", err=True)
        if exc.context:
            typer.echo(exc.verbose_detail(), err=True)
        raise typer.Exit(code=exc.exit_code) from None
    typer.echo(f"allaganeye {__version__}")
    raise typer.Exit()


@app.callback()
def _root_callback(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-V",
            callback=version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = None,
) -> None:
    """Allagan Eye - FF14 Frontline video auto-highlight extraction tool."""


@app.command()
def split(
    video_path: Annotated[
        Path | None,
        typer.Argument(
            help="Input video file (MP4/MKV/AVI/MOV). Mutually exclusive "
            "with --from-metadata."
        ),
    ] = None,
    from_metadata: Annotated[
        Path | None,
        typer.Option(
            "--from-metadata",
            help="Path to a metadata.json produced by `allaganeye detect`. "
            "When given, detection is skipped and only the ffmpeg split "
            "phase runs. Mutually exclusive with VIDEO_PATH (#463).",
        ),
    ] = None,
    output_dir: Annotated[
        Path, typer.Option("-o", "--output-dir", help="Output directory")
    ] = Path("./output"),
    sample_interval: Annotated[
        float, typer.Option(help="Frame sampling interval in seconds")
    ] = 1.0,
    blackout_threshold: Annotated[
        float, typer.Option(help="Blackout detection brightness threshold (0-255)")
    ] = 15.0,
    min_match_duration: Annotated[
        float, typer.Option(help="Minimum match duration in seconds")
    ] = 300.0,
    min_blackout_duration: Annotated[
        float,
        typer.Option(
            help="Minimum blackout duration to treat as match boundary (seconds). "
            "Shorter blackouts (e.g. respawn) are ignored."
        ),
    ] = 3.0,
    workers: Annotated[
        int | None,
        typer.Option(help="Number of parallel workers for detection (default: auto)"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Detect only, do not split. Consider using `allaganeye detect` "
            "instead (#463).",
        ),
    ] = False,
    gpu: Annotated[
        bool,
        typer.Option(
            "--gpu",
            help="Force GPU-accelerated detection. Falls back to CPU if "
            "GPU is unavailable. Mutually exclusive with --no-gpu.",
        ),
    ] = False,
    no_gpu: Annotated[
        bool,
        typer.Option(
            "--no-gpu",
            help="Force CPU detection, disabling GPU acceleration. "
            "Mutually exclusive with --gpu.",
        ),
    ] = False,
    gpu_vendor: Annotated[
        str | None,
        typer.Option(
            "--gpu-vendor",
            help="GPU vendor for hardware decode. Choices: auto / nvidia / amd / intel. "
            "All three vendors are implemented (nvidia=cuvid, amd=d3d11va, intel=qsv). "
            "Default: auto (probe-based, _VENDOR_PREFERENCE = nvidia > amd > intel). "
            "#546 / #553 / #550",
        ),
    ] = None,
    no_cache: Annotated[
        bool,
        typer.Option("--no-cache", help="Ignore cached detection results"),
    ] = False,
    no_audio: Annotated[
        bool,
        typer.Option(
            "--no-audio",
            help="Disable audio-based match boundary promotion (Fanfare scan). "
            "Currently frozen: audio scan is always skipped regardless of this flag.",
        ),
    ] = False,
    vtuber: Annotated[
        bool,
        typer.Option(
            "--vtuber",
            hidden=True,
            help="VTuber recording (game inset): use scorebar-band anchor for "
            "detection. Omit for OBS full-frame (default).",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "-v", "--verbose", help="Verbose output (metadata details, gap info)"
        ),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option(
            "-q", "--quiet", help="Suppress progress output (final result only)"
        ),
    ] = False,
) -> None:
    """Split a long recording into per-match video files."""
    try:
        # Mutual exclusion checks (#419 / #463). Raised before any file / config
        # validation so users get a single, deterministic error even when
        # their command would otherwise fail for other reasons too.
        if verbose and quiet:
            raise ConfigValidationError("--quiet and --verbose are mutually exclusive")
        if gpu and no_gpu:
            raise ConfigValidationError("--gpu and --no-gpu are mutually exclusive")
        if video_path is not None and from_metadata is not None:
            raise ConfigValidationError(
                "VIDEO_PATH and --from-metadata are mutually exclusive"
            )
        if video_path is None and from_metadata is None:
            raise ConfigValidationError(
                "One of VIDEO_PATH or --from-metadata must be provided"
            )
        if from_metadata is not None and dry_run:
            raise ConfigValidationError(
                "--dry-run is not compatible with --from-metadata "
                "(use `allaganeye detect` to regenerate metadata)"
            )

        # Collapse the two independent flags back into the tri-state
        # (True / False / None=auto) that SplitConfig.use_gpu expects.
        # The independent-flag split (vs Typer's "--gpu/--no-gpu" form) is
        # what lets us detect simultaneous specification above (#419).
        use_gpu: bool | None
        if gpu:
            use_gpu = True
        elif no_gpu:
            use_gpu = False
        else:
            use_gpu = None

        if from_metadata is not None:
            if not from_metadata.exists():
                raise InputFileError(f"Metadata file not found: {from_metadata}")
            config = SplitConfig(
                output_dir=output_dir,
                sample_interval=sample_interval,
                blackout_threshold=blackout_threshold,
                min_match_duration=min_match_duration,
                min_blackout_duration=min_blackout_duration,
                dry_run=False,
                use_gpu=use_gpu,
                workers=workers,
                no_cache=no_cache,
                no_audio=no_audio,
                vtuber=vtuber,
            )
            from allaganeye.commands.split_matches import run_split_from_metadata

            run_split_from_metadata(from_metadata, config, verbose=verbose, quiet=quiet)
            return

        assert video_path is not None  # for type-checker; mutex-checked above
        if not video_path.exists():
            raise InputFileError(f"File not found: {video_path}")

        if video_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise InputFileError(
                f"Unsupported format: {video_path.suffix}. "
                f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            )

        config = SplitConfig(
            output_dir=output_dir,
            sample_interval=sample_interval,
            blackout_threshold=blackout_threshold,
            min_match_duration=min_match_duration,
            min_blackout_duration=min_blackout_duration,
            dry_run=dry_run,
            use_gpu=use_gpu,
            gpu_vendor=gpu_vendor,
            workers=workers,
            no_cache=no_cache,
            no_audio=no_audio,
            vtuber=vtuber,
        )

        from allaganeye.commands.split_matches import run_split

        run_split(video_path, config, verbose=verbose, quiet=quiet)

    except AllaganEyeError as e:
        _report_app_error(e, verbose=verbose, quiet=quiet)
        raise typer.Exit(code=e.exit_code) from None
    except Exception:
        _report_unexpected_error(verbose=verbose, quiet=quiet)
        raise typer.Exit(code=1) from None


@app.command()
def detect(
    video_path: Annotated[
        Path, typer.Argument(help="Input video file (MP4/MKV/AVI/MOV)")
    ],
    output_dir: Annotated[
        Path, typer.Option("-o", "--output-dir", help="Output directory")
    ] = Path("./output"),
    sample_interval: Annotated[
        float, typer.Option(help="Frame sampling interval in seconds")
    ] = 1.0,
    blackout_threshold: Annotated[
        float, typer.Option(help="Blackout detection brightness threshold (0-255)")
    ] = 15.0,
    min_match_duration: Annotated[
        float, typer.Option(help="Minimum match duration in seconds")
    ] = 300.0,
    min_blackout_duration: Annotated[
        float,
        typer.Option(
            help="Minimum blackout duration to treat as match boundary (seconds). "
            "Shorter blackouts (e.g. respawn) are ignored."
        ),
    ] = 3.0,
    workers: Annotated[
        int | None,
        typer.Option(help="Number of parallel workers for detection (default: auto)"),
    ] = None,
    gpu: Annotated[
        bool,
        typer.Option(
            "--gpu",
            help="Force GPU-accelerated detection. Falls back to CPU if "
            "GPU is unavailable. Mutually exclusive with --no-gpu.",
        ),
    ] = False,
    no_gpu: Annotated[
        bool,
        typer.Option(
            "--no-gpu",
            help="Force CPU detection, disabling GPU acceleration. "
            "Mutually exclusive with --gpu.",
        ),
    ] = False,
    gpu_vendor: Annotated[
        str | None,
        typer.Option(
            "--gpu-vendor",
            help="GPU vendor for hardware decode. Choices: auto / nvidia / amd / intel. "
            "All three vendors are implemented (nvidia=cuvid, amd=d3d11va, intel=qsv). "
            "Default: auto (probe-based, _VENDOR_PREFERENCE = nvidia > amd > intel). "
            "#546 / #553 / #550",
        ),
    ] = None,
    no_cache: Annotated[
        bool,
        typer.Option("--no-cache", help="Ignore cached detection results"),
    ] = False,
    no_audio: Annotated[
        bool,
        typer.Option(
            "--no-audio",
            help="Disable audio-based match boundary promotion (Fanfare scan). "
            "Currently frozen: audio scan is always skipped regardless of this flag.",
        ),
    ] = False,
    vtuber: Annotated[
        bool,
        typer.Option(
            "--vtuber",
            hidden=True,
            help="VTuber recording (game inset): use scorebar-band anchor for "
            "detection. Omit for OBS full-frame (default).",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "-v", "--verbose", help="Verbose output (metadata details, gap info)"
        ),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option(
            "-q", "--quiet", help="Suppress progress output (final result only)"
        ),
    ] = False,
    progress_format: Annotated[
        str,
        typer.Option(
            "--progress-format",
            help="Progress output format. 'text' (default) renders human-"
            "readable click progress bars and typer status lines. 'json' "
            "emits one JSON object per line on stdout (phase / completed "
            "/ total / elapsed_s) for the Tauri GUI wrapper, and "
            "suppresses all human-readable text output (#569).",
        ),
    ] = "text",
) -> None:
    """Run detection only and write metadata.json (no split, #463).

    Subsequent ``allaganeye split --from-metadata <metadata.json>`` can use
    the output to produce match files without redetecting.
    """
    try:
        if verbose and quiet:
            raise ConfigValidationError("--quiet and --verbose are mutually exclusive")
        if gpu and no_gpu:
            raise ConfigValidationError("--gpu and --no-gpu are mutually exclusive")
        if progress_format not in ("text", "json"):
            raise ConfigValidationError(
                f"Invalid --progress-format: {progress_format!r}. "
                "Choices: 'text', 'json'."
            )

        use_gpu: bool | None
        if gpu:
            use_gpu = True
        elif no_gpu:
            use_gpu = False
        else:
            use_gpu = None

        if not video_path.exists():
            raise InputFileError(f"File not found: {video_path}")

        if video_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise InputFileError(
                f"Unsupported format: {video_path.suffix}. "
                f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            )

        config = SplitConfig(
            output_dir=output_dir,
            sample_interval=sample_interval,
            blackout_threshold=blackout_threshold,
            min_match_duration=min_match_duration,
            min_blackout_duration=min_blackout_duration,
            dry_run=False,
            use_gpu=use_gpu,
            gpu_vendor=gpu_vendor,
            workers=workers,
            no_cache=no_cache,
            no_audio=no_audio,
            vtuber=vtuber,
        )

        from allaganeye.commands.detect import run_detect

        run_detect(
            video_path,
            config,
            verbose=verbose,
            quiet=quiet,
            progress_format=progress_format,
        )

    except AllaganEyeError as e:
        _report_app_error(e, verbose=verbose, quiet=quiet)
        raise typer.Exit(code=e.exit_code) from None
    except Exception:
        _report_unexpected_error(verbose=verbose, quiet=quiet)
        raise typer.Exit(code=1) from None


@app.command(name="debug-brightness")
def debug_brightness(
    video_path: Annotated[
        Path, typer.Argument(help="Input video file (MP4/MKV/AVI/MOV)")
    ],
    start: Annotated[
        float, typer.Option("--start", help="Start time in seconds")
    ] = 0.0,
    end: Annotated[
        float | None,
        typer.Option("--end", help="End time in seconds (default: video duration)"),
    ] = None,
    interval: Annotated[
        float, typer.Option("--interval", help="Sampling interval in seconds")
    ] = 1.0,
    workers: Annotated[
        int | None,
        typer.Option(help="Number of parallel workers (default: auto)"),
    ] = None,
    roi_mode: Annotated[
        str | None,
        typer.Option(
            "--roi-mode", help="ROI analysis mode (scorebar, scorebar-detail)"
        ),
    ] = None,
) -> None:
    """Probe frame brightness at regular intervals (CSV output for threshold tuning)."""
    try:
        if not video_path.exists():
            raise InputFileError(f"File not found: {video_path}")

        if video_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise InputFileError(
                f"Unsupported format: {video_path.suffix}. "
                f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            )

        from allaganeye.commands.debug_brightness import run_debug_brightness

        run_debug_brightness(
            video_path,
            start=start,
            end=end,
            interval=interval,
            workers=workers,
            roi_mode=roi_mode,
        )

    except AllaganEyeError as e:
        # debug-brightness has no -v / -q, so it maps to matrix 19b's
        # "default" row but without a -v hint (the option doesn't exist
        # for this command).
        _report_app_error(e, verbose=False, quiet=False, show_hint=False)
        raise typer.Exit(code=e.exit_code) from None
    except Exception:
        _report_unexpected_error(verbose=False, quiet=False, show_hint=False)
        raise typer.Exit(code=1) from None


def _report_app_error(
    exc: AllaganEyeError,
    *,
    verbose: bool,
    quiet: bool = False,
    show_hint: bool = True,
) -> None:
    """Render an ``AllaganEyeError`` per matrix v2 19a/19b/19c (#428, #351).

    Note: 19d (click-level option-parse error such as ``allaganeye -version``)
    is handled separately in :func:`main` and never reaches this function.
    See ``docs/cli-spec.md`` section ``click-level option-parse error`` for details.


    - 19a (verbose=True):  ``Error: <msg>`` + ``verbose_detail()`` context
      lines + full traceback (exceptions are raised ``from None`` in the
      CLI handlers but the traceback is emitted here *before* re-raise,
      so the stack is still the original error's).
    - 19b (default):       ``Error: <msg>`` + one-line hint directing to
      ``-v``.  Suppressed when ``show_hint=False`` (commands with no
      verbose option, e.g. ``debug-brightness``, still take this branch
      but skip the misleading hint).
    - 19c (quiet=True):    ``Error: <msg>`` only.  No hint, no context,
      no traceback.  Keeps the -q contract of "error message only"
      intact even when verbose_detail would otherwise be available.
    """
    typer.echo(f"Error: {exc}", err=True)

    if quiet:
        return

    if verbose:
        detail = exc.verbose_detail()
        if detail:
            typer.echo(detail, err=True)
        tb = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        ).rstrip()
        typer.echo(tb, err=True)
        return

    if show_hint:
        typer.echo(_VERBOSE_HINT, err=True)


def _report_unexpected_error(
    *, verbose: bool, quiet: bool = False, show_hint: bool = True
) -> None:
    """Render an unexpected (non-``AllaganEyeError``) exception per matrix v2.

    - 19a (verbose=True):  full traceback via ``traceback.print_exc`` so
      ``__cause__`` / ``__context__`` chains are preserved (the CLI
      handlers deliberately skip ``from None`` for this path).
    - 19b (default):       ``Unexpected error: <exc>`` + -v hint (when
      ``show_hint=True``).  No traceback so the default noise level
      stays low.
    - 19c (quiet=True):    ``Unexpected error: <exc>`` only.
    """
    if verbose:
        traceback.print_exc()
        return

    exc = sys.exc_info()[1]
    typer.echo(f"Unexpected error: {exc}", err=True)

    if quiet:
        return

    if show_hint:
        typer.echo(_VERBOSE_HINT, err=True)


def _suggest_long_option_hint(argv: list[str]) -> str | None:
    """Return ``--<name>`` candidate when argv has a single-dash long-option typo (#440).

    typer / click parses ``-version`` as the short-option cluster
    ``-v -e -r -s -i -o -n`` and raises ``NoSuchOption`` for the first
    char.  We scan argv for a single-dash token of length >= 2 (e.g.
    ``-version``) that, with the leading dash doubled, matches a known
    long option of the typer app or any subcommand.  Returns ``None``
    when no suitable candidate exists so we don't volunteer misleading
    hints for unrelated typos.
    """
    cmd = typer.main.get_command(app)
    # ``--help`` is added by click at parse time (``add_help_option=True``)
    # so it is NOT in ``cmd.params``; seed the set so ``-help`` typos still
    # get a hint.
    known: set[str] = {"help"}
    for param in cmd.params:
        for opt in param.opts:
            if opt.startswith("--"):
                known.add(opt[2:])
    if isinstance(cmd, click.Group):
        for sub_cmd in cmd.commands.values():
            for param in sub_cmd.params:
                for opt in param.opts:
                    if opt.startswith("--"):
                        known.add(opt[2:])

    for token in argv:
        if not token.startswith("-") or token.startswith("--"):
            continue
        name = token.lstrip("-").split("=", 1)[0]
        if len(name) >= 2 and name in known:
            return f"--{name}"

    return None


# #761 -- register export + encoder-slots commands. Hidden commands stay
# out of `allaganeye --help` listings but remain dispatchable.
from allaganeye.commands import encoder_slots as _encoder_slots_cmd  # noqa: E402
from allaganeye.commands import export as _export_cmd  # noqa: E402

_export_cmd.register(app)
_encoder_slots_cmd.register(app)


def main() -> None:
    """Console-script entry point that adds a hint for single-dash long-option typos (#440).

    ``allaganeye -version`` parses as the cluster ``-v -e -r -s -i -o -n``
    and click raises ``NoSuchOption`` for the first char.  Without
    context the message ("No such option: -v") doesn't reveal that the
    user typed ``-version``; we catch the error, let click print its
    usual usage / boxed message via ``exc.show()``, and append a
    ``Did you mean --version?`` line when the pattern matches a real
    long option.

    Uses ``standalone_mode=False`` so click re-raises ``ClickException``
    subclasses for us to inspect (and converts ``Exit`` into a return
    value containing its exit code).  Always finishes with ``sys.exit``
    so the caller gets the same SystemExit semantics as the original
    ``app()`` entry point.
    """
    rv: int = 0
    try:
        result = app(standalone_mode=False)
        if isinstance(result, int):
            rv = result
    except click.exceptions.NoSuchOption as exc:
        exc.show()
        hint = _suggest_long_option_hint(sys.argv[1:])
        if hint:
            click.echo(f"Did you mean {hint}?", err=True)
        rv = exc.exit_code
    except click.exceptions.UsageError as exc:
        exc.show()
        rv = exc.exit_code
    except click.exceptions.ClickException as exc:
        exc.show()
        rv = exc.exit_code
    except click.exceptions.Abort:
        click.echo("Aborted!", err=True)
        rv = 1
    sys.exit(rv)
