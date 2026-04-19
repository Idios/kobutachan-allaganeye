"""CLI entry point for Allagan Eye."""

from pathlib import Path
from typing import Annotated

import typer

from allaganeye import __version__
from allaganeye.config import SUPPORTED_EXTENSIONS, SplitConfig
from allaganeye.exceptions import (
    AllaganEyeError,
    ConfigValidationError,
    InputFileError,
)

app = typer.Typer(
    name="allaganeye",
    help="FF14 Frontline video auto-highlight extraction tool.",
    no_args_is_help=True,
)


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"allaganeye {__version__}")
        raise typer.Exit()


@app.callback()
def main(
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
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Detect only, do not split")
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
        # Mutual exclusion checks (#419). Raised before any file / config
        # validation so users get a single, deterministic error even when
        # their command would otherwise fail for other reasons too.
        if verbose and quiet:
            raise ConfigValidationError("--quiet and --verbose are mutually exclusive")
        if gpu and no_gpu:
            raise ConfigValidationError("--gpu and --no-gpu are mutually exclusive")

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
            workers=workers,
            no_cache=no_cache,
            no_audio=no_audio,
        )

        from allaganeye.commands.split_matches import run_split

        run_split(video_path, config, verbose=verbose, quiet=quiet)

    except AllaganEyeError as e:
        _report_app_error(e, verbose=verbose)
        raise typer.Exit(code=e.exit_code) from None
    except Exception:
        _report_unexpected_error(verbose=verbose)
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
        _report_app_error(e, verbose=False)
        raise typer.Exit(code=e.exit_code) from None
    except Exception:
        _report_unexpected_error(verbose=False)
        raise typer.Exit(code=1) from None


def _report_app_error(exc: AllaganEyeError, *, verbose: bool) -> None:
    """Render an ``AllaganEyeError`` to stderr, adding verbose detail (#351)."""
    typer.echo(f"Error: {exc}", err=True)
    if verbose:
        detail = exc.verbose_detail()
        if detail:
            typer.echo(detail, err=True)


def _report_unexpected_error(*, verbose: bool) -> None:
    """Render an unexpected (non-``AllaganEyeError``) exception (#351).

    Non-verbose: short one-liner.  Verbose: full traceback via
    ``traceback.print_exc`` so ``__cause__`` / ``__context__`` chains are
    preserved (we purposefully do not pass ``from None`` in this path).
    """
    if verbose:
        import traceback

        traceback.print_exc()
    else:
        import sys

        exc = sys.exc_info()[1]
        typer.echo(f"Unexpected error: {exc}", err=True)
