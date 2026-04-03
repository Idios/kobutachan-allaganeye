"""Video metadata extraction using ffprobe."""

import json
import subprocess
from pathlib import Path

from allaganeye.exceptions import InputFileError, VideoProcessingError


def probe_video(video_path: Path) -> dict:
    """Extract video metadata using ffprobe.

    Returns dict with keys: duration, width, height, fps, codec, audio_codec.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as e:
        raise VideoProcessingError(
            "ffprobe not found. Please install ffmpeg and ensure it is in PATH."
        ) from e
    except subprocess.CalledProcessError as e:
        raise VideoProcessingError(f"ffprobe failed: {e.stderr}") from e

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise VideoProcessingError("ffprobe returned invalid JSON") from e

    video_stream = None
    audio_stream = None
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video" and video_stream is None:
            video_stream = stream
        elif stream.get("codec_type") == "audio" and audio_stream is None:
            audio_stream = stream

    if video_stream is None:
        raise InputFileError("No video stream found in file")

    # Parse FPS from r_frame_rate (e.g., "30/1" or "60000/1001")
    fps_str = video_stream.get("r_frame_rate", "0/1")
    try:
        num, den = fps_str.split("/")
        fps = float(num) / float(den)
    except (ValueError, ZeroDivisionError):
        fps = 0.0

    duration = float(data.get("format", {}).get("duration", 0))

    return {
        "duration": duration,
        "width": int(video_stream.get("width", 0)),
        "height": int(video_stream.get("height", 0)),
        "fps": fps,
        "codec": video_stream.get("codec_name", "unknown"),
        "audio_codec": audio_stream.get("codec_name", "unknown")
        if audio_stream
        else None,
    }
