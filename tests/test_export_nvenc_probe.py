"""Tests for NVENC engine count probe (#761).

SKU table from spec §4.2. Codex review #9 enforces fallback=1 for
unknown NVIDIA cards.
"""

from __future__ import annotations

import pytest

from allaganeye.export.nvenc_probe import probe_nvenc_engine_count


# --- SKU table lookups ---


def test_rtx_5090_returns_3():
    assert probe_nvenc_engine_count(["NVIDIA GeForce RTX 5090 (32GB VRAM)"]) == 3


def test_rtx_5090_case_insensitive():
    assert probe_nvenc_engine_count(["nvidia geforce rtx 5090"]) == 3


def test_rtx_4090_returns_2():
    assert probe_nvenc_engine_count(["NVIDIA GeForce RTX 4090 (24GB VRAM)"]) == 2


def test_rtx_4080_returns_2():
    assert probe_nvenc_engine_count(["NVIDIA GeForce RTX 4080 (16GB VRAM)"]) == 2


def test_rtx_4070_returns_2():
    assert probe_nvenc_engine_count(["NVIDIA GeForce RTX 4070"]) == 2


def test_rtx_4060_returns_1():
    assert probe_nvenc_engine_count(["NVIDIA GeForce RTX 4060 (8GB VRAM)"]) == 1


def test_rtx_5080_returns_2():
    assert probe_nvenc_engine_count(["NVIDIA GeForce RTX 5080"]) == 2


def test_rtx_5070_returns_2():
    assert probe_nvenc_engine_count(["NVIDIA GeForce RTX 5070"]) == 2


def test_rtx_5060_returns_1():
    assert probe_nvenc_engine_count(["NVIDIA GeForce RTX 5060"]) == 1


# --- Fallback ---


def test_unknown_nvidia_falls_back_to_1():
    """Codex review #9: 不明 NVIDIA は保守的に 1 (default は 1-engine 想定)."""
    assert probe_nvenc_engine_count(["NVIDIA GeForce GTX 1660"]) == 1


def test_empty_list_falls_back_to_1():
    assert probe_nvenc_engine_count([]) == 1


def test_non_nvidia_falls_back_to_1():
    """vendor 選択ロジック側で NVENC が選ばれた前提なのでここに来るのは異例。
    多くの環境では nvidia-smi 検出済みのはずだが、想定外も 1 で fallback。"""
    assert probe_nvenc_engine_count(["AMD Radeon RX 7900 XT"]) == 1


# --- env override ---


def test_env_override_takes_precedence(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ALLAGANEYE_EXPORT_CONCURRENCY", "5")
    assert probe_nvenc_engine_count(["NVIDIA GeForce RTX 5090"]) == 5


def test_env_override_invalid_falls_through(monkeypatch: pytest.MonkeyPatch):
    """Non-digit env value is ignored — SKU table consulted normally."""
    monkeypatch.setenv("ALLAGANEYE_EXPORT_CONCURRENCY", "auto")
    assert probe_nvenc_engine_count(["NVIDIA GeForce RTX 5090"]) == 3


def test_env_override_zero_falls_through(monkeypatch: pytest.MonkeyPatch):
    """0 is invalid (would mean no workers) — fall back to SKU table."""
    monkeypatch.setenv("ALLAGANEYE_EXPORT_CONCURRENCY", "0")
    assert probe_nvenc_engine_count(["NVIDIA GeForce RTX 5090"]) == 3


def test_env_override_empty_falls_through(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ALLAGANEYE_EXPORT_CONCURRENCY", "")
    assert probe_nvenc_engine_count(["NVIDIA GeForce RTX 5090"]) == 3


# --- Multi-GPU conservative min (Codex review #12) ---


def test_multi_gpu_takes_minimum_engine_count():
    """RTX 5090 (3 engine) + RTX 4060 (1 engine) → 1 (conservative)."""
    assert (
        probe_nvenc_engine_count(
            [
                "NVIDIA GeForce RTX 5090",
                "NVIDIA GeForce RTX 4060",
            ]
        )
        == 1
    )


def test_multi_gpu_with_unknown_uses_min_of_known():
    """RTX 4090 (2) + unknown card → 2 (unknown doesn't pollute the table match)."""
    assert (
        probe_nvenc_engine_count(
            [
                "NVIDIA GeForce RTX 4090",
                "Future Unknown Card 9000",
            ]
        )
        == 2
    )


def test_multi_same_sku_returns_same_count():
    """2x RTX 5090 → 3 (matches present but min == 3)."""
    assert (
        probe_nvenc_engine_count(
            [
                "NVIDIA GeForce RTX 5090",
                "NVIDIA GeForce RTX 5090",
            ]
        )
        == 3
    )
