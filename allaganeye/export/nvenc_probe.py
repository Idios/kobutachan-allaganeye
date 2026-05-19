"""NVENC physical engine count probe via SKU table (#761).

See spec sections 4.2/9 for design rationale (live nvidia-smi probe rejected).
Codex review #9 sets fallback=1; review #12 enforces conservative min for
multi-GPU.
"""

from __future__ import annotations

import os

# (GPU model substring (lowercased), NVENC engine count)
# Based on official NVIDIA spec sheets. Update this table when adding new SKUs.
_SKU_TABLE: tuple[tuple[str, int], ...] = (
    # RTX 50 series
    ("rtx 5090", 3),
    ("rtx 5080", 2),
    ("rtx 5070", 2),
    ("rtx 5060", 1),
    # RTX 40 series
    ("rtx 4090", 2),
    ("rtx 4080", 2),
    ("rtx 4070", 2),
    ("rtx 4060", 1),
)

_DEFAULT_NVENC_COUNT = 1
"""Codex review #9: unknown NVIDIA cards default to 1 (conservative; avoids
subprocess setup overhead for 1-engine cards). Use env override for higher N."""


def probe_nvenc_engine_count(gpu_models: list[str]) -> int:
    """Determine NVENC engine count from the SKU table.

    Priority:
    1. env var ``ALLAGANEYE_EXPORT_CONCURRENCY`` if a positive integer -> use directly
       (escape hatch for manual override, e.g. during OBS recording contention)
    2. any entry in ``gpu_models`` matches a SKU table substring
       -> minimum of all matched counts (Codex review #12: conservative for multi-GPU)
    3. fallback -> ``_DEFAULT_NVENC_COUNT`` (= 1)
    """
    override = os.environ.get("ALLAGANEYE_EXPORT_CONCURRENCY", "").strip()
    if override.isdigit() and int(override) > 0:
        return int(override)

    lc = [m.lower() for m in gpu_models]
    matched_counts: list[int] = []
    for needle, count in _SKU_TABLE:
        if any(needle in m for m in lc):
            matched_counts.append(count)
    if matched_counts:
        return min(matched_counts)
    return _DEFAULT_NVENC_COUNT
