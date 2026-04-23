"""Tests for ffmpeg/ffprobe path resolution."""

import os
import sys
from unittest.mock import patch

import pytest

from allaganeye.exceptions import VideoProcessingError
from allaganeye.ffmpeg_path import (
    _ENV_VAR,
    _check_dir,
    _error_message,
    _find_binary,
    _search_macos_known_paths,
    _search_windows_known_paths,
    find_ffmpeg,
    find_ffprobe,
)


class TestFindBinary:
    """Tests for the 4-stage resolution logic."""

    def test_found_via_which(self):
        with patch(
            "allaganeye.ffmpeg_path.shutil.which", return_value="/usr/bin/ffmpeg"
        ):
            result = _find_binary("ffmpeg")
        assert result == "/usr/bin/ffmpeg"

    def test_found_via_env_var(self, tmp_path):
        ffmpeg_bin = tmp_path / "ffmpeg.exe"
        ffmpeg_bin.touch()
        with (
            patch("allaganeye.ffmpeg_path.shutil.which", return_value=None),
            patch.dict(os.environ, {_ENV_VAR: str(tmp_path)}),
            patch(
                "allaganeye.ffmpeg_path._search_windows_known_paths", return_value=None
            ),
        ):
            result = _find_binary("ffmpeg")
        assert result == str(ffmpeg_bin)

    def test_env_var_dir_missing_binary(self, tmp_path):
        """Env var dir exists but doesn't contain ffmpeg."""
        with (
            patch("allaganeye.ffmpeg_path.shutil.which", return_value=None),
            patch.dict(os.environ, {_ENV_VAR: str(tmp_path)}),
            patch(
                "allaganeye.ffmpeg_path._search_windows_known_paths", return_value=None
            ),
        ):
            with pytest.raises(VideoProcessingError, match="not found"):
                _find_binary("ffmpeg")

    def test_not_found_raises(self):
        with (
            patch("allaganeye.ffmpeg_path.shutil.which", return_value=None),
            patch.dict(os.environ, {}, clear=True),
            patch(
                "allaganeye.ffmpeg_path._search_windows_known_paths", return_value=None
            ),
        ):
            with pytest.raises(VideoProcessingError, match="not found"):
                _find_binary("ffmpeg")

    def test_error_message_includes_env_var(self):
        with (
            patch("allaganeye.ffmpeg_path.shutil.which", return_value=None),
            patch.dict(os.environ, {}, clear=True),
            patch(
                "allaganeye.ffmpeg_path._search_windows_known_paths", return_value=None
            ),
        ):
            with pytest.raises(VideoProcessingError, match=_ENV_VAR):
                _find_binary("ffmpeg")

    def test_priority_which_over_env(self, tmp_path):
        """shutil.which takes precedence over env var."""
        ffmpeg_bin = tmp_path / "ffmpeg.exe"
        ffmpeg_bin.touch()
        with (
            patch(
                "allaganeye.ffmpeg_path.shutil.which", return_value="/usr/bin/ffmpeg"
            ),
            patch.dict(os.environ, {_ENV_VAR: str(tmp_path)}),
        ):
            result = _find_binary("ffmpeg")
        assert result == "/usr/bin/ffmpeg"


class TestErrorMessage:
    """Tests for the install-instructions error message (#508)."""

    def test_generic_recommends_lgpl(self):
        msg = _error_message("ffmpeg")
        assert "LGPL" in msg
        assert _ENV_VAR in msg

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific guidance")
    def test_windows_recommends_btbn_lgpl_and_keeps_winget_fallback(self):
        """Windows message surfaces BtbN LGPL as primary and Gyan.FFmpeg as fallback.

        Distribution ships BtbN LGPLv3 since #508. Devs should match licensing,
        but existing winget `Gyan.FFmpeg` (GPL) installs are still auto-discovered
        so the message documents that path as a backward-compat fallback.
        """
        msg = _error_message("ffmpeg")
        assert "BtbN" in msg
        assert "win64-lgpl" in msg
        assert "Gyan.FFmpeg" in msg

    @pytest.mark.skipif(sys.platform != "darwin", reason="macOS-specific guidance")
    def test_macos_mentions_homebrew(self):
        msg = _error_message("ffmpeg")
        assert "brew install ffmpeg" in msg


class TestCheckDir:
    def test_finds_exe(self, tmp_path):
        (tmp_path / "ffmpeg.exe").touch()
        assert _check_dir(tmp_path, "ffmpeg") == str(tmp_path / "ffmpeg.exe")

    def test_finds_no_ext(self, tmp_path):
        (tmp_path / "ffmpeg").touch()
        assert _check_dir(tmp_path, "ffmpeg") == str(tmp_path / "ffmpeg")

    def test_not_found(self, tmp_path):
        assert _check_dir(tmp_path, "ffmpeg") is None


class TestSearchWindowsKnownPaths:
    def test_returns_none_without_localappdata(self):
        with patch.dict(os.environ, {}, clear=True):
            assert _search_windows_known_paths("ffmpeg") is None

    def test_returns_none_when_no_match(self, tmp_path):
        with patch.dict(os.environ, {"LOCALAPPDATA": str(tmp_path)}):
            assert _search_windows_known_paths("ffmpeg") is None


class TestSearchMacosKnownPaths:
    def test_finds_in_opt_homebrew(self, tmp_path):
        ffmpeg = tmp_path / "ffmpeg"
        ffmpeg.touch()
        with patch(
            "allaganeye.ffmpeg_path._search_macos_known_paths",
            wraps=_search_macos_known_paths,
        ):
            # Direct test with real tmp_path won't match /opt/homebrew,
            # so test the function with mocked Path.is_file
            from pathlib import Path

            with patch.object(Path, "is_file", side_effect=lambda: True):
                result = _search_macos_known_paths("ffmpeg")
        assert result is not None
        assert "ffmpeg" in result

    def test_returns_none_when_not_installed(self):
        with patch("pathlib.Path.is_file", return_value=False):
            assert _search_macos_known_paths("ffmpeg") is None


class TestCaching:
    def test_find_ffmpeg_is_cached(self):
        """find_ffmpeg returns cached result on second call."""
        find_ffmpeg.cache_clear()
        with patch(
            "allaganeye.ffmpeg_path._find_binary", return_value="/usr/bin/ffmpeg"
        ) as mock:
            result1 = find_ffmpeg()
            result2 = find_ffmpeg()
        assert result1 == result2
        mock.assert_called_once()
        find_ffmpeg.cache_clear()

    def test_find_ffprobe_is_cached(self):
        find_ffprobe.cache_clear()
        with patch(
            "allaganeye.ffmpeg_path._find_binary", return_value="/usr/bin/ffprobe"
        ) as mock:
            result1 = find_ffprobe()
            result2 = find_ffprobe()
        assert result1 == result2
        mock.assert_called_once()
        find_ffprobe.cache_clear()
