"""Tests for ``allaganeye.system_info`` (#377).

Heavy focus on the fallback / error paths because the helpers are only
used in ``-v`` verbose output -- they must never raise and must always
return a sane string.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

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


@patch(
    "allaganeye.system_info._detect_cpu_models",
    return_value=["AMD Ryzen 9 9950X3D"],
)
@patch("allaganeye.system_info._detect_physical_cores", return_value=16)
@patch("allaganeye.system_info.os.cpu_count", return_value=32)
def test_get_cpu_info_includes_physical_and_logical_counts(
    _logical, _physical, _models
):
    result = get_cpu_info()
    assert result == "AMD Ryzen 9 9950X3D (16C/32T)"


@patch("allaganeye.system_info._detect_cpu_models", return_value=["Apple M1"])
@patch("allaganeye.system_info._detect_physical_cores", return_value=8)
@patch("allaganeye.system_info.os.cpu_count", return_value=8)
def test_get_cpu_info_collapses_when_physical_equals_logical(
    _logical, _physical, _models
):
    """When physical == logical, show only one count (``8T``) to reduce noise."""
    result = get_cpu_info()
    assert result == "Apple M1 (8T)"


@patch("allaganeye.system_info._detect_cpu_models", return_value=None)
@patch("allaganeye.system_info.os.cpu_count", return_value=None)
def test_get_cpu_info_unavailable_when_nothing_works(_models, _cores):
    assert get_cpu_info() == _UNAVAILABLE


@patch("allaganeye.system_info._detect_cpu_models", return_value=None)
@patch("allaganeye.system_info._detect_physical_cores", return_value=None)
@patch("allaganeye.system_info.os.cpu_count", return_value=8)
def test_get_cpu_info_uses_fallback_model_when_unknown(_logical, _physical, _models):
    result = get_cpu_info()
    assert "(unknown CPU)" in result
    assert "(8T)" in result


# --- #435: multi-CPU aggregation ---


@patch(
    "allaganeye.system_info._detect_cpu_models",
    return_value=["AMD EPYC 7763 64-Core Processor", "AMD EPYC 7763 64-Core Processor"],
)
@patch("allaganeye.system_info._detect_physical_cores", return_value=128)
@patch("allaganeye.system_info.os.cpu_count", return_value=256)
def test_get_cpu_info_dual_socket_same_model(_logical, _physical, _models):
    """Dual-socket same model uses xN notation (#435)."""
    result = get_cpu_info()
    assert result == "AMD EPYC 7763 64-Core Processor x2 (128C/256T)"


@patch(
    "allaganeye.system_info._detect_cpu_models",
    return_value=["Intel Xeon Gold 6154", "AMD EPYC 7763"],
)
@patch("allaganeye.system_info._detect_physical_cores", return_value=92)
@patch("allaganeye.system_info.os.cpu_count", return_value=128)
def test_get_cpu_info_mixed_models_uses_plus_join(_logical, _physical, _models):
    """Mixed-model multi-CPU joins with ' + ' (#435)."""
    result = get_cpu_info()
    assert result == "Intel Xeon Gold 6154 + AMD EPYC 7763 (92C/128T)"


@patch("allaganeye.system_info._detect_cpu_models", return_value=["AMD EPYC 7763"])
@patch("allaganeye.system_info._detect_physical_cores", return_value=64)
@patch("allaganeye.system_info.os.cpu_count", return_value=128)
def test_get_cpu_info_single_socket_uses_bare_name(_logical, _physical, _models):
    """Single-socket retains the bare model + (CC/TT) format (#435 regression guard)."""
    result = get_cpu_info()
    assert result == "AMD EPYC 7763 (64C/128T)"


@patch("allaganeye.system_info.platform.system", return_value="Windows")
def test_detect_cpu_models_windows_returns_all_sockets(_system):
    """Windows wmic returns every CPU package, not just the first (#435)."""
    from allaganeye.system_info import _detect_cpu_models

    wmic_output = (
        "Name\nAMD EPYC 7763 64-Core Processor\nAMD EPYC 7763 64-Core Processor\n"
    )
    with patch("allaganeye.system_info._run_text", return_value=wmic_output):
        result = _detect_cpu_models()
    assert result == [
        "AMD EPYC 7763 64-Core Processor",
        "AMD EPYC 7763 64-Core Processor",
    ]


@patch("allaganeye.system_info.platform.system", return_value="Windows")
def test_detect_physical_cores_windows_sums_all_sockets(_system):
    """Windows wmic NumberOfCores is summed across packages (#435)."""
    from allaganeye.system_info import _detect_physical_cores

    wmic_output = "NumberOfCores\n64\n64\n"
    with patch("allaganeye.system_info._run_text", return_value=wmic_output):
        result = _detect_physical_cores()
    assert result == 128


@patch("allaganeye.system_info.platform.system", return_value="Linux")
def test_detect_cpu_models_linux_dedups_per_socket(_system):
    """Linux /proc/cpuinfo with two physical IDs returns both socket models (#435)."""
    from allaganeye.system_info import _detect_cpu_models

    cpuinfo = (
        "processor\t: 0\n"
        "physical id\t: 0\n"
        "model name\t: AMD EPYC 7763 64-Core Processor\n"
        "\n"
        "processor\t: 1\n"
        "physical id\t: 0\n"
        "model name\t: AMD EPYC 7763 64-Core Processor\n"
        "\n"
        "processor\t: 64\n"
        "physical id\t: 1\n"
        "model name\t: AMD EPYC 7763 64-Core Processor\n"
        "\n"
        "processor\t: 65\n"
        "physical id\t: 1\n"
        "model name\t: AMD EPYC 7763 64-Core Processor\n"
        "\n"
    )
    with patch("builtins.open", mock_open(read_data=cpuinfo)):
        result = _detect_cpu_models()
    # One entry per physical socket, both identical -> caller renders x2.
    assert result == [
        "AMD EPYC 7763 64-Core Processor",
        "AMD EPYC 7763 64-Core Processor",
    ]


@patch("allaganeye.system_info.platform.system", return_value="Linux")
def test_detect_cpu_models_linux_mixed_sockets(_system):
    """Linux /proc/cpuinfo with mixed-model sockets is supported (#435)."""
    from allaganeye.system_info import _detect_cpu_models

    cpuinfo = (
        "processor\t: 0\n"
        "physical id\t: 0\n"
        "model name\t: Intel Xeon Gold 6154\n"
        "\n"
        "processor\t: 18\n"
        "physical id\t: 1\n"
        "model name\t: AMD EPYC 7763\n"
        "\n"
    )
    with patch("builtins.open", mock_open(read_data=cpuinfo)):
        result = _detect_cpu_models()
    # Order is by physical_id ascending so the display is deterministic.
    assert result == ["Intel Xeon Gold 6154", "AMD EPYC 7763"]


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
    ("cpu", "gpus", "mem", "disk", "expected_gpu_line"),
    [
        (
            "AMD Ryzen 9 (16C/32T)",
            ["NVIDIA RTX 5090 (32GB VRAM)"],
            "64.0 GB",
            "142.5 / 931.5 GB free on E:",
            "GPU: NVIDIA RTX 5090 (32GB VRAM)",
        ),
        (_UNAVAILABLE, [], _UNAVAILABLE, _UNAVAILABLE, "GPU: (unavailable)"),
    ],
)
def test_print_environment_header_emits_hw_lines(
    cpu, gpus, mem, disk, expected_gpu_line, tmp_path, capsys
):
    """_print_environment_header emits 4 HW lines including on fallback (#377, #436)."""
    from allaganeye.commands.split_matches import _print_environment_header

    with (
        patch("allaganeye.system_info.get_cpu_info", return_value=cpu),
        patch("allaganeye.system_info.get_gpu_info_lines", return_value=gpus),
        patch("allaganeye.system_info.get_memory_info", return_value=mem),
        patch("allaganeye.system_info.get_disk_info", return_value=disk),
    ):
        _print_environment_header(tmp_path)

    out = capsys.readouterr().out
    assert f"CPU: {cpu}" in out
    assert expected_gpu_line in out
    assert f"Memory: {mem}" in out
    assert f"Disk: {disk}" in out


# --- #436: multi-GPU listing ---


@patch("allaganeye.system_info._run_text")
def test_get_gpu_info_lines_multiple_nvidia(mock_run):
    """nvidia-smi multi-line CSV is parsed into multiple GPU entries (#436)."""
    from allaganeye.system_info import get_gpu_info_lines

    def side_effect(cmd, **_kwargs):
        if cmd[:1] == ["nvidia-smi"]:
            return "NVIDIA GeForce RTX 5090, 32768\nNVIDIA GeForce RTX 4090, 24576\n"
        return None

    mock_run.side_effect = side_effect
    result = get_gpu_info_lines()
    assert result == [
        "NVIDIA GeForce RTX 5090 (32GB VRAM)",
        "NVIDIA GeForce RTX 4090 (24GB VRAM)",
    ]


@patch("allaganeye.system_info.platform.system", return_value="Windows")
@patch("allaganeye.system_info._run_text")
def test_get_gpu_info_lines_dgpu_plus_igpu_windows(mock_run, _system):
    """dGPU (NVIDIA) + iGPU (Intel) returns both with NVIDIA showing VRAM (#436).

    The platform-probe duplicate of the NVIDIA card is deduped via
    :func:`_gpu_signature` so the list never shows the same card twice.
    """
    from allaganeye.system_info import get_gpu_info_lines

    def side_effect(cmd, **_kwargs):
        if cmd[:1] == ["nvidia-smi"]:
            return "NVIDIA GeForce RTX 5090, 32768\n"
        if cmd[:1] == ["wmic"]:
            return "Name\nNVIDIA GeForce RTX 5090\nIntel UHD Graphics 770\n"
        return None

    mock_run.side_effect = side_effect
    result = get_gpu_info_lines()
    assert result == [
        "NVIDIA GeForce RTX 5090 (32GB VRAM)",
        "Intel UHD Graphics 770",
    ]


@patch("allaganeye.system_info.platform.system", return_value="Windows")
@patch("allaganeye.system_info._run_text")
def test_get_gpu_info_lines_no_nvidia_windows(mock_run, _system):
    """When nvidia-smi is unavailable, wmic provides every GPU (#436)."""
    from allaganeye.system_info import get_gpu_info_lines

    def side_effect(cmd, **_kwargs):
        if cmd[:1] == ["nvidia-smi"]:
            return None
        if cmd[:1] == ["wmic"]:
            return "Name\nAMD Radeon RX 7900 XTX\nIntel UHD Graphics\n"
        return None

    mock_run.side_effect = side_effect
    result = get_gpu_info_lines()
    assert result == ["AMD Radeon RX 7900 XTX", "Intel UHD Graphics"]


@patch("allaganeye.system_info._run_text", return_value=None)
def test_get_gpu_info_lines_returns_empty_when_no_probe_succeeds(_run):
    """No probe success -> empty list (caller should display unavailable)."""
    from allaganeye.system_info import get_gpu_info_lines

    assert get_gpu_info_lines() == []


@patch("allaganeye.system_info.platform.system", return_value="Linux")
@patch("allaganeye.system_info._run_text")
def test_probe_gpu_names_platform_strips_lspci_bus_prefix(mock_run, _system):
    """Linux lspci output strips bus address + category prefix (#436)."""
    from allaganeye.system_info import _probe_gpu_names_platform

    mock_run.return_value = (
        "00:02.0 VGA compatible controller: Intel Corporation UHD Graphics\n"
        "01:00.0 3D controller: NVIDIA Corporation GA107M [GeForce RTX 3050]\n"
    )
    result = _probe_gpu_names_platform()
    assert result == [
        "Intel Corporation UHD Graphics",
        "NVIDIA Corporation GA107M [GeForce RTX 3050]",
    ]


def test_print_environment_header_renders_multi_gpu_as_multi_line(tmp_path, capsys):
    """Multi-GPU systems emit a multi-line ``GPU:`` block with bullet entries (#436)."""
    from allaganeye.commands.split_matches import _print_environment_header

    with (
        patch("allaganeye.system_info.get_cpu_info", return_value="X"),
        patch(
            "allaganeye.system_info.get_gpu_info_lines",
            return_value=["NVIDIA RTX 5090 (32GB VRAM)", "Intel UHD Graphics"],
        ),
        patch("allaganeye.system_info.get_memory_info", return_value="64.0 GB"),
        patch("allaganeye.system_info.get_disk_info", return_value="1 GB"),
    ):
        _print_environment_header(tmp_path)

    out = capsys.readouterr().out
    assert "  GPU:\n" in out
    assert "    - NVIDIA RTX 5090 (32GB VRAM)" in out
    assert "    - Intel UHD Graphics" in out
    # Single-line "GPU: NVIDIA ..." must NOT appear when multi-GPU rendering kicks in.
    assert "  GPU: NVIDIA" not in out


# --- Non-Windows parser coverage (#377 follow-up) ---
#
# The existing suite mocks the ``_detect_*`` functions end-to-end, which
# leaves the actual Linux / Darwin parser logic untested.  These tests feed
# realistic fixture strings through the real parser code so a broken regex
# or partition sequence surfaces here instead of silently downgrading a
# Linux/macOS user's verbose header to ``(unavailable)``.


# --- G1: _detect_cpu_models Linux /proc/cpuinfo (single-socket fallback) ---


@patch("allaganeye.system_info.platform.system", return_value="Linux")
def test_detect_cpu_models_linux_parses_proc_cpuinfo_without_physical_id(_system):
    """Containers / qemu often omit 'physical id'; we still extract the model."""
    from allaganeye.system_info import _detect_cpu_models

    cpuinfo = (
        "processor\t: 0\n"
        "vendor_id\t: AuthenticAMD\n"
        "model name\t: AMD Ryzen 9 9950X3D 16-Core Processor\n"
        "cache size\t: 512 KB\n"
        "\n"
        "processor\t: 1\n"
        "model name\t: AMD Ryzen 9 9950X3D 16-Core Processor\n"
    )
    with patch("builtins.open", mock_open(read_data=cpuinfo)):
        result = _detect_cpu_models()
    assert result == ["AMD Ryzen 9 9950X3D 16-Core Processor"]


@patch("allaganeye.system_info.platform.system", return_value="Linux")
@patch("allaganeye.system_info.platform.processor", return_value="")
def test_detect_cpu_models_linux_falls_back_when_no_model_name(_proc, _system):
    """Linux branch returns None when /proc/cpuinfo lacks 'model name'."""
    from allaganeye.system_info import _detect_cpu_models

    cpuinfo = "processor\t: 0\nvendor_id\t: AuthenticAMD\n"
    with patch("builtins.open", mock_open(read_data=cpuinfo)):
        result = _detect_cpu_models()
    # With no model line AND platform.processor() returning empty, we
    # must surface None so the caller can mark CPU as unknown.
    assert result is None


# --- G2: _detect_physical_cores Linux physical id / core id aggregation ---


@patch("allaganeye.system_info.platform.system", return_value="Linux")
def test_detect_physical_cores_linux_counts_unique_pairs(_system):
    """Linux branch counts unique (physical_id, core_id) pairs.

    2 physical packages, each with 2 cores, each with 2 HT threads
    -> 4 unique physical cores, 8 logical threads.
    """
    from allaganeye.system_info import _detect_physical_cores

    def block(proc_id: int, phys: int, core: int) -> str:
        return f"processor\t: {proc_id}\nphysical id\t: {phys}\ncore id\t: {core}\n\n"

    # 8 logical threads -> 4 unique (phys, core) pairs.
    cpuinfo = (
        block(0, 0, 0)
        + block(1, 0, 0)  # duplicate pair (0,0) - same core, different HT
        + block(2, 0, 1)
        + block(3, 0, 1)  # duplicate pair (0,1)
        + block(4, 1, 0)
        + block(5, 1, 0)  # duplicate pair (1,0)
        + block(6, 1, 1)
        + block(7, 1, 1)  # duplicate pair (1,1)
    )
    with patch("builtins.open", mock_open(read_data=cpuinfo)):
        result = _detect_physical_cores()
    assert result == 4


@patch("allaganeye.system_info.platform.system", return_value="Linux")
def test_detect_physical_cores_linux_returns_none_on_empty_file(_system):
    """Linux branch returns None when no (physical id, core id) pair is seen."""
    from allaganeye.system_info import _detect_physical_cores

    with patch("builtins.open", mock_open(read_data="")):
        result = _detect_physical_cores()
    assert result is None


# --- G3: get_gpu_info Linux lspci ---


@patch("allaganeye.system_info.platform.system", return_value="Linux")
@patch("allaganeye.system_info._run_text")
def test_get_gpu_info_linux_parses_lspci_vga_line(mock_run, _system):
    """Linux branch extracts the GPU name from a 'VGA compatible controller' line.

    `_detect_all_gpus_nvidia`'s strict CSV parser rejects the lspci-shaped
    mock output (no comma + digit), so no separate ``_detect_gpu_nvidia``
    patch is needed (#436 review).
    """
    mock_run.return_value = (
        "00:00.0 Host bridge: Intel Corporation 12th Gen Core Host Bridge\n"
        "01:00.0 VGA compatible controller: "
        "NVIDIA Corporation GA102 [GeForce RTX 3090] (rev a1)\n"
        "02:00.0 Audio device: Intel Corporation ...\n"
    )
    result = get_gpu_info()
    assert "NVIDIA Corporation GA102 [GeForce RTX 3090] (rev a1)" in result


@patch("allaganeye.system_info.platform.system", return_value="Linux")
@patch("allaganeye.system_info._run_text")
def test_get_gpu_info_linux_parses_lspci_3d_controller_line(mock_run, _system):
    """Linux branch also matches '3D controller' lines (common on laptops)."""
    mock_run.return_value = (
        "00:02.0 VGA compatible controller: Intel Corporation UHD Graphics\n"
        "01:00.0 3D controller: NVIDIA Corporation GA107M [GeForce RTX 3050 Mobile]\n"
    )
    result = get_gpu_info()
    # Either line may match first; both should parse to a non-default value.
    # The first hit wins per the implementation's loop, so Intel should win.
    assert "Intel Corporation UHD Graphics" in result


# --- G4: get_gpu_info Darwin system_profiler ---


@patch("allaganeye.system_info.platform.system", return_value="Darwin")
@patch("allaganeye.system_info._run_text")
def test_get_gpu_info_darwin_parses_chipset_model(mock_run, _system):
    """Darwin branch extracts 'Chipset Model: X' via regex."""
    mock_run.return_value = (
        "Graphics/Displays:\n\n"
        "    Apple M1 Pro:\n\n"
        "      Chipset Model: Apple M1 Pro\n"
        "      Type: GPU\n"
        "      Bus: Built-In\n"
    )
    assert get_gpu_info() == "Apple M1 Pro"


@patch("allaganeye.system_info.platform.system", return_value="Darwin")
@patch("allaganeye.system_info._run_text")
def test_get_gpu_info_darwin_unavailable_when_no_chipset_line(mock_run, _system):
    """Darwin branch falls back when system_profiler output lacks Chipset Model."""
    mock_run.return_value = "Graphics/Displays:\n\n    (info missing)\n"
    assert get_gpu_info() == _UNAVAILABLE


# --- G5: _detect_total_memory_bytes Linux /proc/meminfo ---


@patch("allaganeye.system_info.platform.system", return_value="Linux")
def test_detect_total_memory_bytes_linux_parses_proc_meminfo(_system):
    """Linux branch extracts MemTotal from /proc/meminfo and converts kB -> bytes."""
    from allaganeye.system_info import _detect_total_memory_bytes

    meminfo = (
        "MemTotal:       16334364 kB\n"
        "MemFree:         1234567 kB\n"
        "Buffers:          123456 kB\n"
    )
    with patch("builtins.open", mock_open(read_data=meminfo)):
        result = _detect_total_memory_bytes()
    assert result == 16334364 * 1024


@patch("allaganeye.system_info.platform.system", return_value="Linux")
def test_detect_total_memory_bytes_linux_returns_none_when_missing(_system):
    """Linux branch returns None if /proc/meminfo has no MemTotal line."""
    from allaganeye.system_info import _detect_total_memory_bytes

    with patch("builtins.open", mock_open(read_data="Buffers: 123 kB\n")):
        result = _detect_total_memory_bytes()
    assert result is None
