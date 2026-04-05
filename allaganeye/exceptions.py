"""Error classes with exit code mapping."""


class AllaganEyeError(Exception):
    """Base exception for Allagan Eye."""

    exit_code: int = 1


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
