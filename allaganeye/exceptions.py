"""Error classes with exit code mapping."""

from typing import Any

STDERR_TAIL_BYTES = 2000


class AllaganEyeError(Exception):
    """Base exception for Allagan Eye.

    ``context`` carries optional diagnostic key/value pairs that are shown
    only when the CLI runs with ``--verbose`` (issue #351).  Non-verbose
    output stays short; verbose adds command lines, stderr tails, pipeline
    stats, and similar details needed for bug reports.
    """

    exit_code: int = 1

    def __init__(self, message: str, *, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.context = context or {}

    def verbose_detail(self) -> str:
        """Return a multi-line detail string for verbose mode, or ``""``.

        Each context entry is rendered as ``  key: value`` on its own line.
        Multi-line string values (e.g. ffmpeg stderr tails) are indented
        further so they visually belong to their key.
        """
        if not self.context:
            return ""
        lines: list[str] = []
        for key, value in self.context.items():
            text = str(value)
            if "\n" in text:
                indented = "\n".join(f"    {ln}" for ln in text.splitlines())
                lines.append(f"  {key}:\n{indented}")
            else:
                lines.append(f"  {key}: {text}")
        return "\n".join(lines)


class InputFileError(AllaganEyeError):
    """Input file does not exist or is unsupported format."""

    exit_code = 2


class VideoProcessingError(AllaganEyeError):
    """FFmpeg / ffprobe processing failed."""

    exit_code = 3


class ConfigValidationError(AllaganEyeError):
    """Invalid configuration parameter."""

    exit_code = 5


class DetectionError(AllaganEyeError):
    """No match boundaries detected in the video."""

    exit_code = 4
