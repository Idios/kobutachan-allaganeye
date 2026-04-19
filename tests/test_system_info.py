"""Tests for ``allaganeye.system_info`` (#377).

Heavy focus on the fallback / error paths because the helpers are only
used in ``-v`` verbose output -- they must never raise and must always
return a sane string.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from allaganeye import system_info
from allaganeye.system_info import (
    _UNAVAILABLE,
    get_cpu_info,
    get_disk_info,
    get_gpu_info,
    get_memory_info,
)


# --- get_cpu_info ---


def test_get_cpu_info_returns_non_empty_string():
    """Smoke test: on any supported OS we should get a non-empty string."""
    result = get_cpu_info()
    assert isinstance(result, str)
    assert result != ""


@patch("allaganeye.system_info._detect_cpu_model", return_value="AMD Ryzen 9 9950X3D")
@patch("allaganeye.system_info._detect_physical_cores", return_value=16)
@patch("allaganeye.system_info.os.cpu_count", return_value=32)
def test_get_cpu_info_includes_physical_and_logical_counts(_logical, _physical, _model):
    result = get_cpu_info()
    assert result == "AMD Ryzen 9 9950X3D (16C/32T)"


@patch("allaganeye.system_info._detect_cpu_model", return_value="Apple M1")
@patch("allaganeye.system_info._detect_physical_cores", return_value=8)
@patch("allaganeye.system_info.os.cpu_count", return_value=8)
def test_get_cpu_info_collapses_when_physical_equals_logical(
    _logical, _physical, _model
):
    """When physical == logical, show only one count (``8T``) to reduce noise."""
    result = get_cpu_info()
    assert result == "Apple M1 (8T)"


@patch("allaganeye.system_info._detect_cpu_model", return_value=None)
@patch("allaganeye.system_info.os.cpu_count", return_value=None)
def test_get_cpu_info_unavailable_when_nothing_works(_model, _cores):
    assert get_cpu_info() == _UNAVAILABLE


@patch("allaganeye.system_info._detect_cpu_model", return_value=None)
@patch("allaganeye.system_info._detect_physical_cores", return_value=None)
@patch("allaganeye.system_info.os.cpu_count", return_value=8)
def test_get_cpu_info_uses_fallback_model_when_unknown(_logical, _physical, _model):
    result = get_cpu_info()
    assert "(unknown CPU)" in result
    assert "(8T)" in result


# --- get_gpu_info ---


def test_get_gpu_info_never_raises():
    """Smoke: must return a string without raising on any platform."""
    result = get_gpu_info()
    assert isinstance(result, str)
    assert result != ""


@patch("allaganeye.system_info._run_text")
def test_get_gpu_info_prefers_nvidia_smi(mock_run):
    def side_effect(cmd, **_kwargs):
        if cmd[:1] == ["nvidia-smi"]:
            return "NVIDIA GeForce RTX 5090, 32768\n"
        return None

    mock_run.side_effect = side_effect
    result = get_gpu_info()
    assert "NVIDIA GeForce RTX 5090" in result
    assert "32GB VRAM" in result


@patch("allaganeye.system_info.platform.system", return_value="Windows")
@patch("allaganeye.system_info._run_text")
def test_get_gpu_info_falls_back_to_wmic_on_windows(mock_run, _system):
    def side_effect(cmd, **_kwargs):
        if cmd[:1] == ["nvidia-smi"]:
            return None
        if cmd[:1] == ["wmic"]:
            return "Name\nIntel UHD Graphics 770\n"
        return None

    mock_run.side_effect = side_effect
    assert get_gpu_info() == "Intel UHD Graphics 770"


@patch("allaganeye.system_info._run_text", return_value=None)
def test_get_gpu_info_unavailable_when_all_probes_fail(_run):
    assert get_gpu_info() == _UNAVAILABLE


# --- get_memory_info ---


@patch(
    "allaganeye.system_info._detect_total_memory_bytes",
    return_value=64 * (1024**3),
)
def test_get_memory_info_formats_gb(_mem):
    assert get_memory_info() == "64.0 GB"


@patch("allaganeye.system_info._detect_total_memory_bytes", return_value=None)
def test_get_memory_info_unavailable_on_failure(_mem):
    assert get_memory_info() == _UNAVAILABLE


@patch("allaganeye.system_info._detect_total_memory_bytes", return_value=0)
def test_get_memory_info_unavailable_on_zero(_mem):
    """Zero bytes from probe is treated as 'unknown', not '0.0 GB'."""
    assert get_memory_info() == _UNAVAILABLE


# --- get_disk_info ---


def test_get_disk_info_real_path(tmp_path: Path):
    """Smoke: real disk_usage call against tmp_path should succeed."""
    result = get_disk_info(tmp_path)
    assert "GB free on" in result
    # Shape: "X.Y / Z.W GB free on <drive>"
    assert " / " in result


def test_get_disk_info_returns_unavailable_when_disk_usage_fails():
    with patch(
        "allaganeye.system_info.shutil.disk_usage",
        side_effect=OSError("bad path"),
    ):
        assert get_disk_info(Path("/nonexistent")) == _UNAVAILABLE


# --- _run_text error swallowing ---


def test_run_text_swallows_oserror():
    with patch(
        "allaganeye.system_info.subprocess.run",
        side_effect=OSError("command not found"),
    ):
        assert system_info._run_text(["nope"]) is None


def test_run_text_swallows_subprocess_error():
    with patch(
        "allaganeye.system_info.subprocess.run",
        side_effect=subprocess.CalledProcessError(1, "x"),
    ):
        assert system_info._run_text(["nope"]) is None


def test_run_text_swallows_timeout():
    with patch(
        "allaganeye.system_info.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="nope", timeout=1),
    ):
        assert system_info._run_text(["nope"]) is None


def test_run_text_returns_stdout_on_success():
    mock_result = MagicMock(stdout="hello\n")
    with patch(
        "allaganeye.system_info.subprocess.run",
        return_value=mock_result,
    ):
        assert system_info._run_text(["echo", "hello"]) == "hello\n"


# --- Integration: _print_environment_header surfaces all 4 lines ---


@pytest.mark.parametrize(
    ("cpu", "gpu", "mem", "disk"),
    [
        (
            "AMD Ryzen 9 (16C/32T)",
            "NVIDIA RTX 5090 (32GB VRAM)",
            "64.0 GB",
            "142.5 / 931.5 GB free on E:",
        ),
        (_UNAVAILABLE, _UNAVAILABLE, _UNAVAILABLE, _UNAVAILABLE),
    ],
)
def test_print_environment_header_emits_hw_lines(cpu, gpu, mem, disk, tmp_path, capsys):
    """_print_environment_header emits 4 HW lines including on fallback (#377)."""
    from allaganeye.commands.split_matches import _print_environment_header

    with (
        patch("allaganeye.system_info.get_cpu_info", return_value=cpu),
        patch("allaganeye.system_info.get_gpu_info", return_value=gpu),
        patch("allaganeye.system_info.get_memory_info", return_value=mem),
        patch("allaganeye.system_info.get_disk_info", return_value=disk),
    ):
        _print_environment_header(tmp_path)

    out = capsys.readouterr().out
    assert f"CPU: {cpu}" in out
    assert f"GPU: {gpu}" in out
    assert f"Memory: {mem}" in out
    assert f"Disk: {disk}" in out
