"""Configuration management for Allagan Eye."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SplitConfig:
    """Configuration for the split command."""

    output_dir: Path = field(default_factory=lambda: Path("./output"))
    sample_interval: float = 1.0
    blackout_threshold: float = 15.0
    min_match_duration: float = 300.0
    dry_run: bool = False


SUPPORTED_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov"}
