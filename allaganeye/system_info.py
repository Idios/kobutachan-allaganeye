"""Hardware/system info helpers for ``-v`` verbose header (#377).

Design notes:

- No heavy runtime dependencies (no ``psutil``).  Uses stdlib + platform
  subprocess tools (``wmic``, ``nvidia-smi``, ``lspci``,
  ``system_profiler``) opportunistically.
- Every public helper returns ``"(unavailable)"`` on any failure rather
  than raising.  The verbose header is informational; a failed probe
  must never abort ``allaganeye split``.
- Linux / macOS are best-effort (Windows is the primary platform).
"""

from __future__ import annotations

import logging
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_UNAVAILABLE = "(unavailable)"
_SUBPROCESS_TIMEOUT_S = 5.0
_PS_TIMEOUT_S = 10.0  # PowerShell cold start は wmic より遅い (#860)


def _run_text(cmd: list[str], *, timeout: float = _SUBPROCESS_TIMEOUT_S) -> str | None:
    """Run ``cmd`` capturing stdout as text.  Return stdout or None on failure.

    Swallows all exceptions (OSError / SubprocessError / TimeoutExpired) --
    callers decide the fallback string.  Logs at debug level so nothing
    lands on stderr for a failed probe.
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        logger.debug("system_info probe failed: %s", cmd, exc_info=True)
        return None
    return result.stdout


def get_cpu_info() -> str:
    """Return CPU model + core/thread layout, e.g. ``"AMD Ryzen 9 (16C/32T)"``.

    Multi-CPU (multi-socket) systems aggregate counts across all sockets and
    use the following display heuristics (#435):

    - Same model x N: ``"AMD EPYC 7763 x2 (128C/256T)"``
    - Mixed models:   ``"Intel Xeon ... + AMD EPYC ... (128C/256T)"``
    - Single socket:  unchanged (e.g. ``"AMD Ryzen 9 9950X3D (16C/32T)"``)

    Falls back to ``platform.processor()`` + ``os.cpu_count()`` when
    platform-specific probes fail.  Returns ``"(unavailable)"`` only when
    no useful information can be extracted at all.
    """
    models = _detect_cpu_models()
    logical = os.cpu_count()
    physical = _detect_physical_cores()

    if not models and logical is None:
        return _UNAVAILABLE

    if not models:
        model_str = "(unknown CPU)"
    elif len(models) == 1:
        model_str = models[0]
    elif all(m == models[0] for m in models):
        model_str = f"{models[0]} x{len(models)}"
    else:
        model_str = " + ".join(models)

    if logical is None:
        return model_str
    if physical is not None and physical != logical:
        return f"{model_str} ({physical}C/{logical}T)"
    return f"{model_str} ({logical}T)"


def _detect_cpu_models() -> list[str] | None:
    """Return CPU model names per socket (or single-element for one CPU).

    Multi-socket Windows / Linux systems return one entry per physical CPU
    package.  macOS is single-socket only (Apple silicon).  Returns ``None``
    if no model name can be extracted at all.
    """
    system = platform.system()
    if system == "Windows":
        stdout = _run_text(["wmic", "cpu", "get", "name"])
        if stdout:
            lines = [line.strip() for line in stdout.splitlines() if line.strip()]
            # First line is the "Name" header; subsequent lines are per-CPU.
            if len(lines) >= 2:
                return lines[1:]
        ps = _windows_ps_values("Win32_Processor", "Name")  # #860
        if ps:
            return ps
        # Fall back to platform.processor() which on Windows returns
        # the CPU brand via registry lookup.
        proc = platform.processor().strip()
        return [proc] if proc else None

    if system == "Linux":
        return _detect_cpu_models_linux()

    if system == "Darwin":
        stdout = _run_text(["sysctl", "-n", "machdep.cpu.brand_string"])
        if stdout and stdout.strip():
            return [stdout.strip()]
        proc = platform.processor().strip()
        return [proc] if proc else None

    # Unknown platform: best-effort
    proc = platform.processor().strip()
    return [proc] if proc else None


def _detect_cpu_models_linux() -> list[str] | None:
    """Linux helper: extract one model name per physical socket.

    /proc/cpuinfo blocks contain ``physical id`` + ``model name`` per logical
    CPU; we deduplicate by ``physical id`` so dual-socket hosts return both
    socket models even when both are identical.
    """
    models_by_socket: dict[str, str] = {}
    current_phys = ""
    current_model = ""
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as fh:
            for raw in fh:
                if raw.startswith("physical id"):
                    current_phys = raw.partition(":")[2].strip()
                elif raw.startswith("model name"):
                    current_model = raw.partition(":")[2].strip()
                elif raw.strip() == "":
                    if current_phys and current_model:
                        models_by_socket.setdefault(current_phys, current_model)
                    current_phys = ""
                    current_model = ""
            # Trailing block without final blank line.
            if current_phys and current_model:
                models_by_socket.setdefault(current_phys, current_model)
    except OSError:
        logger.debug("cannot read /proc/cpuinfo", exc_info=True)
        proc = platform.processor().strip()
        return [proc] if proc else None

    if not models_by_socket:
        # Single-socket containers / qemu often omit ``physical id`` entirely.
        # Fall back to the first ``model name`` we can find.
        try:
            with open("/proc/cpuinfo", encoding="utf-8") as fh:
                for raw in fh:
                    if raw.startswith("model name"):
                        value = raw.partition(":")[2].strip()
                        return [value] if value else None
        except OSError:
            pass
        proc = platform.processor().strip()
        return [proc] if proc else None

    try:
        sorted_keys = sorted(models_by_socket.keys(), key=int)
    except ValueError:
        sorted_keys = sorted(models_by_socket.keys())
    return [models_by_socket[pid] for pid in sorted_keys]


def _detect_physical_cores() -> int | None:
    """Return physical (not logical) core count summed across all sockets, or
    None if unknown (#435 -- Windows now aggregates instead of returning the
    first socket's count only)."""
    system = platform.system()
    if system == "Windows":
        stdout = _run_text(["wmic", "cpu", "get", "NumberOfCores"])
        if stdout:
            total = 0
            found = False
            for line in stdout.splitlines():
                line = line.strip()
                if line.isdigit():
                    total += int(line)
                    found = True
            if found:
                return total
        ps = _windows_ps_values("Win32_Processor", "NumberOfCores")  # #860
        total = 0
        found = False
        for value in ps:
            if value.isdigit():
                total += int(value)
                found = True
        return total if found else None
    if system == "Linux":
        try:
            cores: set[tuple[str, str]] = set()
            with open("/proc/cpuinfo", encoding="utf-8") as fh:
                physical_id = ""
                core_id = ""
                for raw in fh:
                    if raw.startswith("physical id"):
                        physical_id = raw.partition(":")[2].strip()
                    elif raw.startswith("core id"):
                        core_id = raw.partition(":")[2].strip()
                    elif raw.strip() == "":
                        if physical_id and core_id:
                            cores.add((physical_id, core_id))
                        physical_id = ""
                        core_id = ""
            return len(cores) or None
        except OSError:
            return None
    if system == "Darwin":
        stdout = _run_text(["sysctl", "-n", "hw.physicalcpu"])
        if stdout and stdout.strip().isdigit():
            return int(stdout.strip())
        return None
    return None


def get_gpu_info() -> str:
    """Return primary GPU model (+ VRAM if known), e.g. ``"NVIDIA RTX 4090 (24GB VRAM)"``.

    Convenience wrapper around :func:`get_gpu_info_lines` that returns the
    first detected GPU.  For multi-GPU listing (#436) use
    :func:`get_gpu_info_lines` instead.  Returns ``"(unavailable)"`` when
    no probe succeeds.
    """
    lines = get_gpu_info_lines()
    if not lines:
        return _UNAVAILABLE
    return lines[0]


def get_gpu_info_lines() -> list[str]:
    """Return all GPU model strings detected, one entry per device (#436).

    NVIDIA GPUs include VRAM (e.g. ``"NVIDIA RTX 5090 (32GB VRAM)"``) via
    ``nvidia-smi``.  Other vendors fall back to platform probes (``wmic`` on
    Windows, ``lspci`` on Linux, ``system_profiler`` on macOS).  Multi-GPU
    systems (e.g. iGPU + dGPU, dual NVIDIA) return one entry per device,
    deduplicated against the NVIDIA list so the same card never appears
    twice.  Returns ``[]`` when no probe succeeds; callers should display
    ``"(unavailable)"`` in that case.
    """
    nvidia_gpus = _detect_all_gpus_nvidia()
    platform_gpus = _probe_gpu_names_platform()

    result: list[str] = list(nvidia_gpus)
    nvidia_signatures = {_gpu_signature(name) for name in nvidia_gpus}
    for name in platform_gpus:
        if _gpu_signature(name) not in nvidia_signatures:
            result.append(name)
    return result


def _gpu_signature(name: str) -> str:
    """Return a canonical signature for matching duplicate GPU names.

    Strips the ``" (NN GB VRAM)"`` suffix and lowercases so an nvidia-smi
    entry matches its bare-name twin from ``wmic`` / ``lspci``.
    """
    base = name.split(" (")[0].strip()
    return base.lower()


def _detect_all_gpus_nvidia() -> list[str]:
    """Return all NVIDIA GPUs as ``"<name> (<gb>GB VRAM)"`` strings.

    Strict CSV parser: only entries that match nvidia-smi's
    ``--format=csv,noheader,nounits`` shape (``name, mib_int``) are
    returned.  Anything else is dropped so unrelated probe output (e.g.
    a globally-mocked ``_run_text`` returning ``lspci`` text) cannot
    pollute the GPU list.
    """
    stdout = _run_text(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total",
            "--format=csv,noheader,nounits",
        ]
    )
    if not stdout:
        return []
    result: list[str] = []
    for raw in stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 2 and parts[1].isdigit():
            # Memory is reported in MiB; round to nearest GB for readability.
            gb = round(int(parts[1]) / 1024)
            result.append(f"{parts[0]} ({gb}GB VRAM)")
    return result


def _detect_gpu_nvidia() -> str | None:
    """Return the first NVIDIA GPU name, or None if nvidia-smi is unavailable.

    Kept for :func:`probe_gpu_vendors` (which only needs a presence check).
    For full GPU listing use :func:`_detect_all_gpus_nvidia`.
    """
    gpus = _detect_all_gpus_nvidia()
    return gpus[0] if gpus else None


def get_memory_info() -> str:
    """Return ``"<total> GB"`` (total installed RAM) or ``"(unavailable)"``.

    Intentionally does NOT report used/free -- that changes between probe
    and split, and would require ``psutil``.  Total RAM alone is the bug-
    report signal users need.
    """
    total_bytes = _detect_total_memory_bytes()
    if total_bytes is None or total_bytes <= 0:
        return _UNAVAILABLE
    gb = total_bytes / (1024**3)
    return f"{gb:.1f} GB"


def _detect_total_memory_bytes() -> int | None:
    system = platform.system()
    if system == "Windows":
        stdout = _run_text(
            [
                "wmic",
                "ComputerSystem",
                "get",
                "TotalPhysicalMemory",
            ]
        )
        if stdout:
            for line in stdout.splitlines():
                line = line.strip()
                if line.isdigit():
                    return int(line)
        for value in _windows_ps_values("Win32_ComputerSystem", "TotalPhysicalMemory"):  # #860
            if value.isdigit():
                return int(value)
        return None
    if system == "Linux":
        try:
            with open("/proc/meminfo", encoding="utf-8") as fh:
                for raw in fh:
                    if raw.startswith("MemTotal:"):
                        match = re.search(r"(\d+)\s*kB", raw)
                        if match:
                            return int(match.group(1)) * 1024
        except OSError:
            return None
        return None
    if system == "Darwin":
        stdout = _run_text(["sysctl", "-n", "hw.memsize"])
        if stdout and stdout.strip().isdigit():
            return int(stdout.strip())
        return None
    return None


def get_disk_info(path: Path) -> str:
    """Return ``"<free> / <total> GB free on <root>"`` for the disk holding *path*.

    ``shutil.disk_usage`` raises on non-existent paths (default output dir
    may not exist yet when verbose header prints), so we walk up to the
    nearest existing parent first.
    """
    probe_path = _first_existing_ancestor(path)
    if probe_path is None:
        logger.debug("no existing ancestor for %s", path)
        return _UNAVAILABLE

    try:
        usage = shutil.disk_usage(probe_path)
    except OSError:
        logger.debug("disk_usage failed for %s", probe_path, exc_info=True)
        return _UNAVAILABLE

    free_gb = usage.free / (1024**3)
    total_gb = usage.total / (1024**3)
    drive = _drive_label(probe_path)
    return f"{free_gb:.1f} / {total_gb:.1f} GB free on {drive}"


def _first_existing_ancestor(path: Path) -> Path | None:
    """Return *path* or the nearest existing ancestor directory."""
    try:
        candidate = path.resolve(strict=False)
    except OSError:
        candidate = path
    while True:
        if candidate.exists():
            return candidate
        parent = candidate.parent
        if parent == candidate:
            return None
        candidate = parent


_VENDOR_KEYWORDS: dict[str, tuple[str, ...]] = {
    # Substring match (case-insensitive). Keywords are chosen to avoid
    # false positives from generic phrases (e.g. "ati" would match
    # "compATIble" in lspci output).
    "nvidia": ("nvidia", "geforce", "quadro", "tesla"),
    "amd": ("amd ", "radeon"),
    "intel": ("intel",),
}


def probe_gpu_vendors() -> list[str]:
    """Return GPU vendor identifiers detected on the system (#546).

    Elements are a subset of ``{"nvidia", "amd", "intel"}`` in the order
    they were first seen (NVIDIA is probed first via nvidia-smi because
    it's the most reliable signal, then platform probe fills in the
    rest).

    Best-effort: returns an empty list when no probe succeeds so callers
    can fall back to CPU mode gracefully.  Never raises.
    """
    vendors: list[str] = []

    # NVIDIA first -- nvidia-smi success = NVIDIA GPU present.
    if _detect_gpu_nvidia() is not None:
        vendors.append("nvidia")

    names = _probe_gpu_names_platform()
    for name in names:
        lowered = name.lower()
        for vendor, keywords in _VENDOR_KEYWORDS.items():
            if any(kw in lowered for kw in keywords) and vendor not in vendors:
                vendors.append(vendor)
                break

    return vendors


def gpu_vendor_probe_warning() -> str | None:
    """Return a warning when Windows GPU vendor detection found nothing (#860).

    wmic/PowerShell 両方の probe 失敗 (または真に GPU 無し) を verbose header
    で可視化し、GUI export が GPU エンコーダを提示できず libx264 へ silent
    degrade する事態にユーザーが気づけるようにする。Windows 以外、または
    vendor を 1 件以上検出できた場合は ``None``。
    """
    if platform.system() != "Windows":
        return None
    if probe_gpu_vendors():
        return None
    return (
        "GPU vendor を検出できませんでした (wmic 非搭載環境では PowerShell "
        "fallback も失敗した可能性)。GPU エンコーダ (NVENC/QSV/AMF) は提示されず "
        "export は libx264 になります。"
    )


def _windows_ps_values(cim_class: str, prop: str) -> list[str]:
    """Return ``prop`` values from ``Get-CimInstance <cim_class>`` via PowerShell.

    wmic-less (Win11 24H2+) fallback for Windows hw probes (#860).
    ``powershell.exe`` (Windows PowerShell 5.1) is in-box on Win10/11
    incl. 24H2/25H2 (only wmic etc. moved to Features on Demand).
    ``-ExpandProperty`` yields header-less output, one value per line.
    Returns ``[]`` on any failure (never raises).
    """
    stdout = _run_text(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            f"Get-CimInstance -ClassName {cim_class} "
            f"| Select-Object -ExpandProperty {prop}",
        ],
        timeout=_PS_TIMEOUT_S,
    )
    if not stdout:
        return []
    return [line.strip() for line in stdout.splitlines() if line.strip()]


def _probe_gpu_names_platform() -> list[str]:
    """Return GPU name strings from platform-specific probes.

    On Linux the leading ``"BB:DD.F VGA compatible controller: "`` prefix is
    stripped so the verbose header / multi-GPU listing (#436) shows just the
    GPU model.  Vendor keyword matching in :func:`probe_gpu_vendors` still
    works because vendor strings (NVIDIA / Intel / AMD) appear in the
    suffix.
    """
    system = platform.system()
    if system == "Windows":
        stdout = _run_text(["wmic", "path", "win32_VideoController", "get", "Name"])
        if stdout:
            names = [line.strip() for line in stdout.splitlines()[1:] if line.strip()]
            if names:
                return names
        return _windows_ps_values("Win32_VideoController", "Name")  # #860
    elif system == "Linux":
        stdout = _run_text(["lspci"])
        if stdout:
            result: list[str] = []
            for line in stdout.splitlines():
                if "vga" not in line.lower() and "3d controller" not in line.lower():
                    continue
                # "01:00.0 VGA compatible controller: NVIDIA Corporation ..."
                # Drop the bus address ("01:00.0") and category ("VGA ... :")
                _, _, after_bus = line.partition(":")
                _, _, after_category = after_bus.partition(":")
                cleaned = (after_category or line).strip()
                if cleaned:
                    result.append(cleaned)
            return result
    elif system == "Darwin":
        stdout = _run_text(["system_profiler", "SPDisplaysDataType"])
        if stdout:
            return re.findall(r"Chipset Model:\s*(.+)", stdout)
    return []


def _drive_label(path: Path) -> str:
    """Return a short label for the disk holding *path* (drive letter or mount)."""
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path

    if platform.system() == "Windows":
        drive = resolved.drive
        return drive or str(resolved)

    # POSIX: walk up until we hit the filesystem root or a mount point.
    # A full ``os.path.ismount`` walk risks OSError on broken paths, so we
    # just fall back to the topmost existing parent.
    cursor = resolved
    while cursor != cursor.parent and not cursor.exists():
        cursor = cursor.parent
    return str(cursor) or "/"
