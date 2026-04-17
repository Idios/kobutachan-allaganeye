"""CLI entry point for Allagan Eye."""

from pathlib import Path
from typing import Annotated

import typer

from allaganeye import __version__
from allaganeye.config import SUPPORTED_EXTENSIONS, SplitConfig
from allaganeye.exceptions import AllaganEyeError, InputFileError

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
        bool | None,
        typer.Option(
            "--gpu/--no-gpu",
            help="Use GPU-accelerated detection. "
            "Default: auto-select based on codec (H.264/HEVC -> GPU, others -> CPU). "
            "Falls back to CPU if GPU is unavailable.",
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
            use_gpu=gpu,
            workers=workers,
            no_cache=no_cache,
            no_audio=no_audio,
        )

        from allaganeye.commands.split_matches import run_split

        run_split(video_path, config, verbose=verbose, quiet=quiet)

    except AllaganEyeError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=e.exit_code) from None
    except Exception as e:
        typer.echo(f"Unexpected error: {e}", err=True)
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
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=e.exit_code) from None
    except Exception as e:
        typer.echo(f"Unexpected error: {e}", err=True)
        raise typer.Exit(code=1) from None
