"""Configuration management for Allagan Eye."""

from dataclasses import dataclass, field
from pathlib import Path

from allaganeye.exceptions import ConfigValidationError


@dataclass
class SplitConfig:
    """Configuration for the split command."""

    output_dir: Path = field(default_factory=lambda: Path("./output"))
    sample_interval: float = 1.0
    blackout_threshold: float = 15.0
    min_match_duration: float = 300.0
    dry_run: bool = False

    def __post_init__(self) -> None:
        if self.sample_interval <= 0:
            raise ConfigValidationError(
                f"--sample-interval must be positive, got {self.sample_interval}"
            )
        if not (0 <= self.blackout_threshold <= 255):
            raise ConfigValidationError(
                f"--blackout-threshold must be 0-255, got {self.blackout_threshold}"
            )
        if self.min_match_duration <= 0:
            raise ConfigValidationError(
                f"--min-match-duration must be positive, got {self.min_match_duration}"
            )


SUPPORTED_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov"}
