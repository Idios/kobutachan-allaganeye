"""Video splitting using FFmpeg copy mode."""

import subprocess
from pathlib import Path

from allaganeye.exceptions import VideoProcessingError


def split_video(
    video_path: Path,
    boundaries: list[dict],
    output_dir: Path,
) -> list[Path]:
    """Split video into segments using FFmpeg copy mode.

    Returns list of output file paths.
    """
    output_files: list[Path] = []

    for i, boundary in enumerate(boundaries, 1):
        output_file = output_dir / f"match_{i:03d}.mp4"
        _ffmpeg_split(
            video_path,
            start=boundary["start"],
            end=boundary["end"],
            output=output_file,
        )
        output_files.append(output_file)

    return output_files


def _ffmpeg_split(
    input_path: Path,
    *,
    start: float,
    end: float,
    output: Path,
) -> None:
    """Run FFmpeg to extract a segment with copy mode (no re-encoding)."""
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(input_path),
                "-ss",
                str(start),
                "-to",
                str(end),
                "-c",
                "copy",
                "-avoid_negative_ts",
                "make_zero",
                str(output),
            ],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as e:
        raise VideoProcessingError(
            "ffmpeg not found. Please install ffmpeg and ensure it is in PATH."
        ) from e

    if result.returncode != 0:
        raise VideoProcessingError(
            f"ffmpeg split failed for {output.name}: {result.stderr[-500:]}"
        )
