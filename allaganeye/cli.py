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
        typer.Option("--version", callback=version_callback, is_eager=True),
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
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Detect only, do not split")
    ] = False,
    verbose: Annotated[
        bool, typer.Option("-v", "--verbose", help="Verbose output")
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
        )

        from allaganeye.commands.split_matches import run_split

        run_split(video_path, config, verbose=verbose)

    except AllaganEyeError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=e.exit_code) from None
    except Exception as e:
        typer.echo(f"Unexpected error: {e}", err=True)
        raise typer.Exit(code=1) from None
