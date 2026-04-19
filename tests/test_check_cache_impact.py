"""Tests for tests/check_cache_impact.py -- git error handling (#300)."""

import subprocess
from unittest.mock import patch

import pytest

from tests.check_cache_impact import _get_changed_files, _run_git


class TestRunGit:
    """_run_git raises SystemExit on non-zero returncode."""

    def test_success_returns_stdout(self) -> None:
        """Normal git output -> returned as string."""
        fake = subprocess.CompletedProcess(
            args=["git", "status"], returncode=0, stdout="ok\n", stderr=""
        )
        with patch("tests.check_cache_impact.subprocess.run", return_value=fake):
            assert _run_git("status") == "ok\n"

    def test_nonzero_returncode_raises_system_exit(self) -> None:
        """Non-zero returncode -> SystemExit(2)."""
        fake = subprocess.CompletedProcess(
            args=["git", "diff"],
            returncode=128,
            stdout="",
            stderr="fatal: not a git repository",
        )
        with patch("tests.check_cache_impact.subprocess.run", return_value=fake):
            with pytest.raises(SystemExit, match="2"):
                _run_git("diff", "--cached", "--name-only")

    def test_nonzero_stderr_printed(self, capsys: pytest.CaptureFixture[str]) -> None:
        """stderr from git is printed to stderr."""
        fake = subprocess.CompletedProcess(
            args=["git", "diff"],
            returncode=1,
            stdout="",
            stderr="fatal: bad revision",
        )
        with patch("tests.check_cache_impact.subprocess.run", return_value=fake):
            with pytest.raises(SystemExit):
                _run_git("diff")
        captured = capsys.readouterr()
        assert "fatal: bad revision" in captured.err


class TestGetChangedFiles:
    """_get_changed_files propagates git failures."""

    def test_git_failure_propagates(self) -> None:
        """Git failure in _get_changed_files -> SystemExit."""
        fake = subprocess.CompletedProcess(
            args=["git", "diff"],
            returncode=128,
            stdout="",
            stderr="fatal: not a git repository",
        )
        with patch("tests.check_cache_impact.subprocess.run", return_value=fake):
            with pytest.raises(SystemExit):
                _get_changed_files()

    def test_success_returns_files(self) -> None:
        """Normal output -> list of file paths."""
        fake = subprocess.CompletedProcess(
            args=["git", "diff"],
            returncode=0,
            stdout="file_a.py\nfile_b.py\n",
            stderr="",
        )
        with patch("tests.check_cache_impact.subprocess.run", return_value=fake):
            result = _get_changed_files()
        assert result == ["file_a.py", "file_b.py"]
