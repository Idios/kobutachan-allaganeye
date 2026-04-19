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
            check=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        logger.debug("system_info probe failed: %s", cmd, exc_info=True)
        return None
    return result.stdout


def get_cpu_info() -> str:
    """Return CPU model + core/thread layout, e.g. ``"AMD Ryzen 9 (16C/32T)"``.

    Falls back to ``platform.processor()`` + ``os.cpu_count()`` when
    platform-specific probes fail.  Returns ``"(unavailable)"`` only when
    no useful information can be extracted at all.
    """
    model = _detect_cpu_model()
    logical = os.cpu_count()
    physical = _detect_physical_cores()

    if model is None and logical is None:
        return _UNAVAILABLE

    model_str = model or "(unknown CPU)"
    if logical is None:
        return model_str
    if physical is not None and physical != logical:
        return f"{model_str} ({physical}C/{logical}T)"
    return f"{model_str} ({logical}T)"


def _detect_cpu_model() -> str | None:
    system = platform.system()
    if system == "Windows":
        stdout = _run_text(["wmic", "cpu", "get", "name"])
        if stdout:
            lines = [line.strip() for line in stdout.splitlines() if line.strip()]
            # First line is the "Name" header; subsequent lines are values.
            if len(lines) >= 2:
                return lines[1]
        # Fall back to platform.processor() which on Windows returns
        # the CPU brand via registry lookup.
        proc = platform.processor()
        return proc.strip() or None

    if system == "Linux":
        try:
            with open("/proc/cpuinfo", encoding="utf-8") as fh:
                for raw in fh:
                    if raw.startswith("model name"):
                        _, _, value = raw.partition(":")
                        return value.strip()
        except OSError:
            logger.debug("cannot read /proc/cpuinfo", exc_info=True)
        return platform.processor() or None

    if system == "Darwin":
        stdout = _run_text(["sysctl", "-n", "machdep.cpu.brand_string"])
        if stdout:
            return stdout.strip() or None
        return platform.processor() or None

    # Unknown platform: best-effort
    return platform.processor() or None


def _detect_physical_cores() -> int | None:
    """Return physical (not logical) core count, or None if unknown."""
    system = platform.system()
    if system == "Windows":
        stdout = _run_text(["wmic", "cpu", "get", "NumberOfCores"])
        if stdout:
            for line in stdout.splitlines():
                line = line.strip()
                if line.isdigit():
                    return int(line)
        return None
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
    """Return GPU model (+ VRAM if known), e.g. ``"NVIDIA RTX 4090 (24GB VRAM)"``.

    Prefers ``nvidia-smi`` for the common case; falls back to ``wmic``
    (Windows), ``lspci`` (Linux), or ``system_profiler`` (macOS).  Returns
    ``"(unavailable)"`` when no probe succeeds.
    """
    nvidia = _detect_gpu_nvidia()
    if nvidia is not None:
        return nvidia

    system = platform.system()
    if system == "Windows":
        stdout = _run_text(["wmic", "path", "win32_VideoController", "get", "name"])
        if stdout:
            lines = [line.strip() for line in stdout.splitlines() if line.strip()]
            if len(lines) >= 2:
                # Return the first non-header GPU; multi-GPU is rare on
                # Windows gaming rigs and the verbose header stays terse.
                return lines[1]
    elif system == "Linux":
        stdout = _run_text(["lspci"])
        if stdout:
            for line in stdout.splitlines():
                lowered = line.lower()
                if "vga" in lowered or "3d controller" in lowered:
                    # "01:00.0 VGA compatible controller: NVIDIA ..."
                    _, _, value = line.partition(":")
                    _, _, value = value.partition(":")
                    return value.strip() or line.strip()
    elif system == "Darwin":
        stdout = _run_text(["system_profiler", "SPDisplaysDataType"])
        if stdout:
            match = re.search(r"Chipset Model:\s*(.+)", stdout)
            if match:
                return match.group(1).strip()

    return _UNAVAILABLE


def _detect_gpu_nvidia() -> str | None:
    stdout = _run_text(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total",
            "--format=csv,noheader,nounits",
        ]
    )
    if not stdout:
        return None
    first = stdout.splitlines()[0].strip()
    if not first:
        return None
    parts = [p.strip() for p in first.split(",")]
    if len(parts) == 2 and parts[1].isdigit():
        # Memory is reported in MiB; round to nearest GB for readability.
        gb = round(int(parts[1]) / 1024)
        return f"{parts[0]} ({gb}GB VRAM)"
    return parts[0] or None


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
