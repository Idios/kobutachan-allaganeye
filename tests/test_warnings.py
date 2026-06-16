"""Tests for #518 warnings scaffold (allaganeye/detection/warnings.py)."""

from __future__ import annotations

from allaganeye.detection.warnings import (
    WARNING_CODES,
    build_warnings,
    sanitize_warnings,
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


def test_post_match_trailing_dropped_code_registered():
    # #805 段階1: the trailing-drop warning code carries a human-readable
    # default message so readers can surface it from the code alone.
    assert "post_match_trailing_dropped" in WARNING_CODES
    assert "--keep-trailing" in WARNING_CODES["post_match_trailing_dropped"]


def test_build_warnings_emits_post_match_trailing_dropped():
    # One (start, end) drop -> exactly one structured warn entry recording
    # the lost segment span, so manual recovery is possible (#805 P1-4).
    result = build_warnings(trailing_drops=[(1000.0, 1800.0)])
    assert result == [
        {
            "code": "post_match_trailing_dropped",
            "message_en": WARNING_CODES["post_match_trailing_dropped"],
            "severity": "warn",
            "context": {"start": 1000.0, "end": 1800.0},
        }
    ]


def test_build_warnings_empty_trailing_drops_is_empty():
    # Explicit empty input keeps the backward-compatible empty result.
    assert build_warnings(trailing_drops=[]) == []
    assert build_warnings(trailing_drops=()) == []


# -- #805 段階1: sanitize_warnings (preserve hazard guard) --


def test_sanitize_warnings_strips_invalid_and_drops_codeless():
    # #805 段階1: warnings read from an existing metadata.json may carry
    # schema-violating entries (the writer doesn't validate). sanitize_warnings
    # drops non-dict / codeless / non-string-code entries and strips any optional
    # field whose value violates the schema, so only schema-valid entries survive
    # into a freshly written metadata.json.
    raw = [
        {"code": 123},  # non-str code -> dropped
        {"code": ""},  # empty code -> dropped
        {"code": "x", "severity": "bad"},  # invalid severity stripped
        {"code": "y", "context": "oops"},  # non-dict context stripped
        {"code": "z", "message_en": 5},  # non-str message_en stripped
        {
            "code": "ok",
            "severity": "warn",
            "context": {"start": 1.0},
            "message_en": "m",
        },  # fully valid -> preserved as-is
        42,  # non-dict -> dropped
        "s",  # non-dict -> dropped
        {"no_code": True},  # missing code -> dropped
    ]
    assert sanitize_warnings(raw) == [
        {"code": "x"},
        {"code": "y"},
        {"code": "z"},
        {
            "code": "ok",
            "severity": "warn",
            "context": {"start": 1.0},
            "message_en": "m",
        },
    ]


def test_sanitize_warnings_non_list_returns_empty():
    # A non-list value (scalar / dict / None) yields an empty list, matching
    # the pre-#805 "rebuild as []" behaviour for malformed sources.
    assert sanitize_warnings("oops") == []
    assert sanitize_warnings(None) == []
    assert sanitize_warnings({"code": "x"}) == []
    assert sanitize_warnings(42) == []
