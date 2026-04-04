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
    """Run FFmpeg to extract a segment with copy mode (no re-encoding).

    Design notes:
    - `-y` overwrites without prompting; safe because output filenames are
      auto-generated (match_NNN.mp4), not user-specified paths.
    - `-ss` is placed before `-i` for input seeking (fast, keyframe-based).
      With `-c copy`, precision is keyframe-level regardless of `-ss` position,
      so input seeking avoids decoding from file start to seek point.
    - `-to` specifies duration (relative to seek point) when `-ss` is before `-i`.
    - On failure, stderr is truncated to 500 chars to keep error messages
      readable (ffmpeg can produce very long diagnostic output).
    """
    duration = end - start
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                str(start),
                "-i",
                str(input_path),
                "-to",
                str(duration),
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
