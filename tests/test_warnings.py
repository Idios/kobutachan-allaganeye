"""Tests for #518 warnings scaffold (allaganeye/detection/warnings.py)."""

from __future__ import annotations

from allaganeye.detection.warnings import (
    WARNING_CODES,
    build_warnings,
)


def test_build_warnings_is_empty_by_default():
    assert build_warnings() == []


def test_warning_codes_registry_is_a_mapping():
    # Initial revision ships an empty registry, but the type contract is
    # dict[str, str]. Future PRs append entries here.
    assert isinstance(WARNING_CODES, dict)


def test_build_warnings_returns_new_list_each_call():
    # Isolation: one caller's mutation must not leak into the next.
    a = build_warnings()
    a.append({"code": "x"})  # type: ignore[arg-type]
    b = build_warnings()
    assert b == []
