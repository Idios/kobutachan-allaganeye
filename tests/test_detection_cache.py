"""Tests for test detection cache (tests/detection_cache.py)."""

import pytest

from tests.detection_cache import (
    _CACHE_VERSION,
    _make_cache_filename,
    _validate_cache_entry,
    clear_cache,
    compute_source_file_hashes,
    read_fixture_cache,
    write_fixture_cache,
)

# --- Helpers ---

FIXTURE_NAME = "detection_with_scorebar"
DETECTION_PARAMS = {"sample_interval": 1.0, "blackout_threshold": 15.0}
RESULT = {"boundaries": [{"start": 0.0, "end": 600.0, "type": "fl_match"}]}


@pytest.fixture
def cache_dir(tmp_path):
    d = tmp_path / ".detection_cache"
    d.mkdir()
    return d


@pytest.fixture
def video_file(tmp_path):
    v = tmp_path / "test_video.mkv"
    v.write_bytes(b"\x00" * 2048)
    return v


@pytest.fixture
def source_hashes():
    return {
        "allaganeye/video/detector.py": "abc123",
        "allaganeye/video/gpu_detector.py": "def456",
        "allaganeye/video/scorebar.py": "ghi789",
    }


def _build_cache_data(video_file, source_hashes, **overrides):
    """Build valid cache data dict."""
    stat = video_file.stat()
    data = {
        "cache_version": _CACHE_VERSION,
        "source": str(video_file.resolve()),
        "source_size": stat.st_size,
        "source_mtime": round(stat.st_mtime, 6),
        "source_hashes": source_hashes,
        "fixtures": {
            FIXTURE_NAME: {
                "params": DETECTION_PARAMS,
                "result": RESULT,
            }
        },
    }
    data.update(overrides)
    return data


# --- _make_cache_filename ---


class TestMakeCacheFilename:
    def test_idempotent(self, video_file):
        """Same path produces same filename."""
        assert _make_cache_filename(video_file) == _make_cache_filename(video_file)

    def test_different_paths_differ(self, tmp_path):
        """Different video paths produce different filenames."""
        v1 = tmp_path / "video_a.mkv"
        v2 = tmp_path / "video_b.mkv"
        v1.touch()
        v2.touch()
        assert _make_cache_filename(v1) != _make_cache_filename(v2)

    def test_contains_stem(self, video_file):
        """Filename includes the video stem for readability."""
        assert video_file.stem in _make_cache_filename(video_file)


# --- _validate_cache_entry ---


class TestValidateCacheEntry:
    def test_valid_entry(self, video_file, source_hashes):
        """Valid cache returns result."""
        data = _build_cache_data(video_file, source_hashes)
        result = _validate_cache_entry(
            data, video_file, FIXTURE_NAME, DETECTION_PARAMS, source_hashes
        )
        assert result == RESULT

    def test_version_mismatch(self, video_file, source_hashes):
        """Wrong cache_version returns None."""
        data = _build_cache_data(video_file, source_hashes, cache_version=999)
        assert (
            _validate_cache_entry(
                data, video_file, FIXTURE_NAME, DETECTION_PARAMS, source_hashes
            )
            is None
        )

    def test_source_path_mismatch(self, video_file, source_hashes):
        """Wrong source path returns None."""
        data = _build_cache_data(video_file, source_hashes, source="/wrong/path")
        assert (
            _validate_cache_entry(
                data, video_file, FIXTURE_NAME, DETECTION_PARAMS, source_hashes
            )
            is None
        )

    def test_size_mismatch(self, video_file, source_hashes):
        """Wrong source_size returns None."""
        data = _build_cache_data(video_file, source_hashes, source_size=999)
        assert (
            _validate_cache_entry(
                data, video_file, FIXTURE_NAME, DETECTION_PARAMS, source_hashes
            )
            is None
        )

    def test_mtime_mismatch(self, video_file, source_hashes):
        """Wrong source_mtime returns None."""
        data = _build_cache_data(video_file, source_hashes, source_mtime=0.0)
        assert (
            _validate_cache_entry(
                data, video_file, FIXTURE_NAME, DETECTION_PARAMS, source_hashes
            )
            is None
        )

    def test_source_hashes_mismatch(self, video_file, source_hashes):
        """Changed source file hashes returns None."""
        data = _build_cache_data(video_file, source_hashes)
        changed_hashes = {**source_hashes, "allaganeye/video/detector.py": "changed"}
        assert (
            _validate_cache_entry(
                data, video_file, FIXTURE_NAME, DETECTION_PARAMS, changed_hashes
            )
            is None
        )

    def test_fixture_not_found(self, video_file, source_hashes):
        """Missing fixture name returns None."""
        data = _build_cache_data(video_file, source_hashes)
        assert (
            _validate_cache_entry(
                data, video_file, "nonexistent_fixture", DETECTION_PARAMS, source_hashes
            )
            is None
        )

    def test_params_mismatch(self, video_file, source_hashes):
        """Wrong detection params returns None."""
        data = _build_cache_data(video_file, source_hashes)
        different_params = {"sample_interval": 2.0, "blackout_threshold": 20.0}
        assert (
            _validate_cache_entry(
                data, video_file, FIXTURE_NAME, different_params, source_hashes
            )
            is None
        )


# --- write / read round-trip ---


class TestWriteReadRoundTrip:
    def test_roundtrip(self, cache_dir, video_file, source_hashes):
        """Write then read returns the same result."""
        write_fixture_cache(
            cache_dir,
            video_file,
            FIXTURE_NAME,
            DETECTION_PARAMS,
            source_hashes,
            RESULT,
        )
        got = read_fixture_cache(
            cache_dir, video_file, FIXTURE_NAME, DETECTION_PARAMS, source_hashes
        )
        assert got == RESULT

    def test_merge_fixtures(self, cache_dir, video_file, source_hashes):
        """Writing a second fixture merges into the same file."""
        write_fixture_cache(
            cache_dir,
            video_file,
            FIXTURE_NAME,
            DETECTION_PARAMS,
            source_hashes,
            RESULT,
        )
        other_result = {"boundaries": []}
        write_fixture_cache(
            cache_dir,
            video_file,
            "other_fixture",
            {"param": "value"},
            source_hashes,
            other_result,
        )
        # Both fixtures should be readable
        assert (
            read_fixture_cache(
                cache_dir, video_file, FIXTURE_NAME, DETECTION_PARAMS, source_hashes
            )
            == RESULT
        )
        assert (
            read_fixture_cache(
                cache_dir,
                video_file,
                "other_fixture",
                {"param": "value"},
                source_hashes,
            )
            == other_result
        )

    def test_source_hash_change_resets(self, cache_dir, video_file, source_hashes):
        """Source hash change wipes all fixtures."""
        write_fixture_cache(
            cache_dir,
            video_file,
            FIXTURE_NAME,
            DETECTION_PARAMS,
            source_hashes,
            RESULT,
        )
        new_hashes = {**source_hashes, "allaganeye/video/detector.py": "changed"}
        new_result = {"boundaries": [{"start": 10.0, "end": 500.0, "type": "fl_match"}]}
        write_fixture_cache(
            cache_dir,
            video_file,
            FIXTURE_NAME,
            DETECTION_PARAMS,
            new_hashes,
            new_result,
        )
        # Old hashes should miss
        assert (
            read_fixture_cache(
                cache_dir, video_file, FIXTURE_NAME, DETECTION_PARAMS, source_hashes
            )
            is None
        )
        # New hashes should hit
        assert (
            read_fixture_cache(
                cache_dir, video_file, FIXTURE_NAME, DETECTION_PARAMS, new_hashes
            )
            == new_result
        )

    def test_read_missing_file(self, cache_dir, video_file, source_hashes):
        """Read with no cache file returns None."""
        assert (
            read_fixture_cache(
                cache_dir, video_file, FIXTURE_NAME, DETECTION_PARAMS, source_hashes
            )
            is None
        )

    def test_read_corrupted_file(self, cache_dir, video_file, source_hashes):
        """Corrupted JSON returns None."""
        cache_file = cache_dir / _make_cache_filename(video_file)
        cache_file.write_text("not valid json{{{", encoding="utf-8")
        assert (
            read_fixture_cache(
                cache_dir, video_file, FIXTURE_NAME, DETECTION_PARAMS, source_hashes
            )
            is None
        )


# --- clear_cache ---


class TestClearCache:
    def test_clears_files(self, cache_dir, video_file, source_hashes):
        """clear_cache removes all files and recreates directory."""
        write_fixture_cache(
            cache_dir,
            video_file,
            FIXTURE_NAME,
            DETECTION_PARAMS,
            source_hashes,
            RESULT,
        )
        assert any(cache_dir.iterdir())
        clear_cache(cache_dir)
        assert cache_dir.exists()
        assert not any(cache_dir.iterdir())

    def test_clears_nonexistent_dir(self, tmp_path):
        """clear_cache on nonexistent dir creates it."""
        new_dir = tmp_path / "nonexistent_cache"
        clear_cache(new_dir)
        assert new_dir.exists()


# --- compute_source_file_hashes ---


class TestComputeSourceFileHashes:
    def test_returns_hashes_for_existing_files(self, tmp_path):
        """Computes SHA256 for files that exist."""
        # Create fake source files
        for rel_path in [
            "allaganeye/video/detector.py",
            "allaganeye/video/gpu_detector.py",
            "allaganeye/video/scorebar.py",
        ]:
            p = tmp_path / rel_path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f"content of {rel_path}", encoding="utf-8")

        hashes = compute_source_file_hashes(tmp_path)
        assert len(hashes) == 3
        assert all(len(v) == 64 for v in hashes.values())  # SHA256 hex length

    def test_missing_file_returns_empty_string(self, tmp_path):
        """Missing source files get empty string hash."""
        hashes = compute_source_file_hashes(tmp_path)
        assert all(v == "" for v in hashes.values())
