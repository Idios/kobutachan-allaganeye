"""Resolve ffmpeg/ffprobe binary paths with auto-discovery."""

import glob
import os
import shutil
import sys
from functools import lru_cache
from pathlib import Path

from allaganeye.exceptions import VideoProcessingError

_ENV_VAR = "ALLAGANEYE_FFMPEG"


@lru_cache(maxsize=1)
def find_ffmpeg() -> str:
    """Find the ffmpeg binary path.

    Resolution order:
    1. shutil.which("ffmpeg") -- works if PATH is set
    2. ALLAGANEYE_FFMPEG env var -- user-specified directory containing ffmpeg
    3. Windows known paths -- winget typical install location
    4. Error with setup instructions
    """
    return _find_binary("ffmpeg")


@lru_cache(maxsize=1)
def find_ffprobe() -> str:
    """Find the ffprobe binary path. Same resolution order as find_ffmpeg."""
    return _find_binary("ffprobe")


def _find_binary(name: str) -> str:
    # 1. PATH lookup
    found = shutil.which(name)
    if found:
        return found

    # 2. Environment variable
    env_dir = os.environ.get(_ENV_VAR)
    if env_dir:
        candidate = _check_dir(Path(env_dir), name)
        if candidate:
            return candidate

    # 3. OS-specific known paths
    if sys.platform == "win32":
        candidate = _search_windows_known_paths(name)
        if candidate:
            return candidate
    elif sys.platform == "darwin":
        candidate = _search_macos_known_paths(name)
        if candidate:
            return candidate

    # 4. Error
    raise VideoProcessingError(_error_message(name))


def _check_dir(directory: Path, name: str) -> str | None:
    """Check if a binary exists in the given directory."""
    for ext in ("", ".exe"):
        candidate = directory / f"{name}{ext}"
        if candidate.is_file():
            return str(candidate)
    return None


def _search_windows_known_paths(name: str) -> str | None:
    """Search common Windows installation paths for ffmpeg/ffprobe."""
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if not local_app_data:
        return None

    # winget: Gyan.FFmpeg package
    pattern = os.path.join(
        local_app_data,
        "Microsoft",
        "WinGet",
        "Packages",
        "Gyan.FFmpeg*",
        "ffmpeg-*",
        "bin",
        f"{name}.exe",
    )
    matches = glob.glob(pattern)
    if matches:
        # Use the most recently modified match
        matches.sort(key=os.path.getmtime, reverse=True)
        return matches[0]

    return None


def _search_macos_known_paths(name: str) -> str | None:
    """Search common macOS installation paths for ffmpeg/ffprobe."""
    # Homebrew: Apple Silicon (/opt/homebrew) and Intel (/usr/local)
    for prefix in ("/opt/homebrew/bin", "/usr/local/bin"):
        candidate = Path(prefix) / name
        if candidate.is_file():
            return str(candidate)
    return None


def _error_message(name: str) -> str:
    lines = [
        f"{name} not found. Install ffmpeg and ensure it is accessible.",
        "",
        "Options:",
        "  1. Add ffmpeg to PATH",
        f"  2. Set {_ENV_VAR} environment variable to the directory containing {name}",
    ]
    if sys.platform == "win32":
        lines.append(
            "  3. Install via winget: winget install Gyan.FFmpeg (auto-discovered)"
        )
    elif sys.platform == "darwin":
        lines.append("  3. Install via Homebrew: brew install ffmpeg (auto-discovered)")
    return "\n".join(lines)
