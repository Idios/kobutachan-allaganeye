"""NVENC physical engine count probe via SKU table (#761).

See spec §4.2 / §9 for design rationale (live nvidia-smi probe rejected).
Codex review #9 sets fallback=1; review #12 enforces conservative min for
multi-GPU.
"""

from __future__ import annotations

import os

# (GPU model substring (lowercased), NVENC engine count)
# NVIDIA 公式 spec sheet 基準。新 SKU 追加時は本テーブルを更新。
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
"""Codex review #9: 不明 NVIDIA カードは保守的に 1 (1-engine card の subprocess
setup overhead を避けるため)。user が高 N を望むなら env override で。"""


def probe_nvenc_engine_count(gpu_models: list[str]) -> int:
    """NVENC engine count を SKU table から決定する。

    優先順:
    1. env var ``ALLAGANEYE_EXPORT_CONCURRENCY`` が正の整数 → そのまま採用
       (OBS 録画中等の contention scenario に user が manual 設定するエスケープハッチ)
    2. ``gpu_models`` のいずれかが SKU table の substring に hit
       → 全 hit の **最小値** (Codex review #12: 複数 GPU 環境で弱い側に揃える)
    3. fallback → ``_DEFAULT_NVENC_COUNT`` (= 1)
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
