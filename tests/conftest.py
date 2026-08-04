"""Shared test fixtures for Allagan Eye."""

import os
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.detection_cache import (
    clear_cache,
    compute_source_file_hashes,
    get_cache_dir,
)

_TESTS_ROOT = Path(__file__).parent
_REPO_ROOT = _TESTS_ROOT.parent

# Computed once per session in pytest_sessionstart
_session_source_hashes: dict[str, str] = {}


# --- pytest hooks ---


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register detection cache options."""
    parser.addoption(
        "--no-test-cache",
        action="store_true",
        default=False,
        help="Skip reading detection cache (still writes for next run).",
    )
    parser.addoption(
        "--clear-test-cache",
        action="store_true",
        default=False,
        help="Delete detection cache directory before running.",
    )


def pytest_sessionstart(session: pytest.Session) -> None:
    """Compute source hashes and handle cache options at session start."""
    global _session_source_hashes
    _session_source_hashes = compute_source_file_hashes(_REPO_ROOT)

    cache_dir = get_cache_dir(_TESTS_ROOT)

    if session.config.getoption("--clear-test-cache", default=False):
        clear_cache(cache_dir)
        print(f"\n[cache] Cleared {cache_dir}")
        return

    _warn_if_stale(cache_dir, _session_source_hashes)


def _warn_if_stale(cache_dir: Path, current_hashes: dict[str, str]) -> None:
    """Check a cache file and warn if source hashes differ."""
    import json as _json

    cache_files = list(cache_dir.glob("*.json"))
    if not cache_files:
        return
    try:
        data = _json.loads(cache_files[0].read_text(encoding="utf-8"))
    except Exception:
        return
    cached_hashes = data.get("source_hashes", {})
    if cached_hashes != current_hashes:
        changed = [
            k for k in current_hashes if current_hashes[k] != cached_hashes.get(k)
        ]
        print(
            f"\n[cache] WARNING: Detection cache may be stale "
            f"-- source files changed: {changed}"
        )
        print("[cache] Run with --clear-test-cache to regenerate.")


# --- cache context fixture ---


@pytest.fixture(scope="session")
def _cache_context(request: pytest.FixtureRequest) -> dict:
    """Provide cache state to slow fixtures."""
    return {
        "cache_dir": get_cache_dir(_TESTS_ROOT),
        "source_hashes": _session_source_hashes,
        "no_cache": request.config.getoption("--no-test-cache", default=False),
    }


# --- existing fixtures ---


@pytest.fixture
def sample_video_dir() -> Path:
    """Path to sample video data directory.

    Reads from ALLAGANEYE_SAMPLE_VIDEO_DIR environment variable.
    Skips the test if the variable is not set or the directory does not exist.
    """
    env_path = os.environ.get("ALLAGANEYE_SAMPLE_VIDEO_DIR")
    if not env_path:
        pytest.skip("ALLAGANEYE_SAMPLE_VIDEO_DIR not set")
    path = Path(env_path)
    if not path.is_dir():
        pytest.skip(f"Sample video directory not found: {path}")
    return path


@pytest.fixture
def tmp_output_dir(tmp_path: Path) -> Path:
    """Temporary output directory for test results."""
    output = tmp_path / "output"
    output.mkdir()
    return output


@pytest.fixture
def fake_video(tmp_path: Path) -> Path:
    """Create a zero-byte .mp4 file that passes CLI validation."""
    video = tmp_path / "test_video.mp4"
    video.write_bytes(b"")
    return video


@pytest.fixture(autouse=True)
def _ffmpeg_interval(request: pytest.FixtureRequest) -> Iterator[None]:
    """Insert 1s interval after slow-marked tests to prevent GPU deadlock.

    Repeated ffmpeg calls can cause NVIDIA driver unresponsiveness due to
    GPU memory fragmentation.  A 1s cooldown between tests mitigates this.
    """
    yield
    if request.node.get_closest_marker("slow"):
        time.sleep(1)


@pytest.fixture(autouse=True)
def _clear_allaganeye_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear ALLAGANEYE_DETECT_FPS_FILTER for every test (#576 S6 / R6).

    The env var is a transitional rollback switch (will be deleted in
    v0.3.x). Tests that need to exercise the legacy path must opt-in by
    calling ``monkeypatch.setenv("ALLAGANEYE_DETECT_FPS_FILTER", "1")``
    inside the test body.  This fixture prevents CI pollution where a
    shell-set env var would silently make every test run the legacy code
    path.
    """
    monkeypatch.delenv("ALLAGANEYE_DETECT_FPS_FILTER", raising=False)


# --- slow_* submarker convention enforcement ---

# pyproject.toml [tool.pytest.ini_options].markers に登録した slow_* と一致させること
_SLOW_SUBMARKERS = frozenset({"slow_probe", "slow_detect", "slow_pipeline", "slow_gpu"})


def slow_submarker_violations(marker_names_by_nodeid: dict[str, set[str]]) -> list[str]:
    """slow_* サブマーカーを持つのに slow を持たない nodeid を返す.

    testing-guide.md の「slow はサブマーカーのスーパーセット」契約を機械化する
    (audit 2026-06-10 P1-3: 違反すると documented コマンドから test が漏れる)。
    """
    return sorted(
        nodeid
        for nodeid, names in marker_names_by_nodeid.items()
        if names & _SLOW_SUBMARKERS and "slow" not in names
    )


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """collection 時に slow マーカー契約違反を即エラーにする.

    tryfirst で builtin の -m deselection より前に全 item を検査する
    (deselect 後では addopts で除外された違反が素通りするため)。
    """
    mapping = {item.nodeid: {m.name for m in item.iter_markers()} for item in items}
    violations = slow_submarker_violations(mapping)
    if violations:
        raise pytest.UsageError(
            "slow_* submarker without 'slow' (testing-guide.md の slow スーパーセット契約違反):\n"
            + "\n".join(f"  {nid}  -> @pytest.mark.slow を追加" for nid in violations)
        )
