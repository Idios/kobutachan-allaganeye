"""Test detection cache — persists detection results across pytest sessions.

Caches the output of expensive ``detect_match_boundaries`` calls so that
``pytest -m slow`` can skip re-detection when neither source video files
nor detection algorithm code have changed.

Cache directory: ``tests/.detection_cache/``
"""

import hashlib
import json
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

_CACHE_VERSION = 1

CACHE_DIR_NAME = ".detection_cache"

_CACHE_SENSITIVE_FILES = [
    "allaganeye/video/detector.py",
    "allaganeye/video/gpu_detector.py",
    "allaganeye/video/scorebar.py",
]


def get_cache_dir(tests_root: Path) -> Path:
    """Return the cache directory path, creating it if needed."""
    cache_dir = tests_root / CACHE_DIR_NAME
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def compute_source_file_hashes(repo_root: Path) -> dict[str, str]:
    """Compute SHA256 hex digests for each cache-sensitive file.

    Returns a dict mapping relative path (forward slashes) to hex digest.
    Missing files get an empty string.
    """
    hashes: dict[str, str] = {}
    for rel_path in _CACHE_SENSITIVE_FILES:
        full_path = repo_root / Path(rel_path)
        if full_path.is_file():
            hashes[rel_path] = hashlib.sha256(full_path.read_bytes()).hexdigest()
        else:
            hashes[rel_path] = ""
    return hashes


def _make_cache_filename(video_path: Path) -> str:
    """Build cache filename from video path.

    Format: ``{video_stem}_{8-char md5 of resolved path}.json``
    """
    resolved = str(video_path.resolve())
    path_hash = hashlib.md5(resolved.encode()).hexdigest()[:8]  # noqa: S324
    return f"{video_path.stem}_{path_hash}.json"


def _read_cache_file(cache_dir: Path, video_path: Path) -> dict | None:
    """Read and parse a cache file. Returns None on any failure."""
    path = cache_dir / _make_cache_filename(video_path)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.debug("Cache file unreadable: %s", path)
        return None


def _write_cache_file(cache_dir: Path, video_path: Path, data: dict) -> None:
    """Write cache data to the JSON file."""
    path = cache_dir / _make_cache_filename(video_path)
    try:
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        logger.debug("Failed to write cache: %s", path)


def _validate_cache_entry(
    data: dict,
    video_path: Path,
    fixture_name: str,
    detection_params: dict,
    source_hashes: dict[str, str],
) -> dict | None:
    """Validate a cache file and return the fixture result, or None."""
    if data.get("cache_version") != _CACHE_VERSION:
        return None

    resolved = str(video_path.resolve())
    if data.get("source") != resolved:
        return None

    try:
        stat = video_path.stat()
    except OSError:
        return None

    if data.get("source_size") != stat.st_size:
        return None
    if data.get("source_mtime") != round(stat.st_mtime, 6):
        return None

    cached_hashes = data.get("source_hashes", {})
    if cached_hashes != source_hashes:
        changed = [k for k in source_hashes if source_hashes[k] != cached_hashes.get(k)]
        logger.warning("Cache stale — source files changed: %s", changed)
        return None

    fixtures = data.get("fixtures", {})
    entry = fixtures.get(fixture_name)
    if entry is None:
        return None

    if entry.get("params") != detection_params:
        return None

    return entry.get("result")


def read_fixture_cache(
    cache_dir: Path,
    video_path: Path,
    fixture_name: str,
    detection_params: dict,
    source_hashes: dict[str, str],
) -> dict | None:
    """Load and validate a cache entry for a specific fixture + video.

    Returns the cached ``result`` dict, or None on miss / invalid.
    """
    data = _read_cache_file(cache_dir, video_path)
    if data is None:
        return None
    return _validate_cache_entry(
        data, video_path, fixture_name, detection_params, source_hashes
    )


def write_fixture_cache(
    cache_dir: Path,
    video_path: Path,
    fixture_name: str,
    detection_params: dict,
    source_hashes: dict[str, str],
    result: dict,
) -> None:
    """Write a cache entry, merging with existing file if present."""
    stat = video_path.stat()

    # Read existing file to merge fixtures
    existing = _read_cache_file(cache_dir, video_path)
    if existing is None or existing.get("source_hashes") != source_hashes:
        # Start fresh if source hashes changed
        existing = {
            "cache_version": _CACHE_VERSION,
            "source": str(video_path.resolve()),
            "source_size": stat.st_size,
            "source_mtime": round(stat.st_mtime, 6),
            "source_hashes": source_hashes,
            "fixtures": {},
        }
    else:
        # Update file metadata in case mtime changed
        existing["source_size"] = stat.st_size
        existing["source_mtime"] = round(stat.st_mtime, 6)

    existing["fixtures"][fixture_name] = {
        "params": detection_params,
        "result": result,
    }

    _write_cache_file(cache_dir, video_path, existing)


def clear_cache(cache_dir: Path) -> None:
    """Delete all cache files and recreate the directory."""
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
