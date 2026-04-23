"""Tests for #515 schema_version policy (allaganeye/detection/migrations.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from allaganeye.detection.migrations import (
    CURRENT_SCHEMA_VERSION,
    MIGRATIONS,
    apply_migrations,
    check_schema_version,
)
from allaganeye.exceptions import InputFileError


def _minimal_payload(version: object | None = "no_key") -> dict:
    """Build a minimal payload; pass ``version=None`` to omit the field."""
    base = {"source": "a.mkv", "matches": [], "gaps": []}
    if version == "no_key":
        return base
    if version is None:
        return base
    base["schema_version"] = version
    return base


class TestCheckSchemaVersion:
    def test_missing_version_is_treated_as_v1(self):
        payload = _minimal_payload(version=None)
        # Should not raise -- pre-#515 files are forward-compat as v1.
        check_schema_version(payload, source=Path("test.json"))

    def test_current_version_is_accepted(self):
        payload = _minimal_payload(version=CURRENT_SCHEMA_VERSION)
        check_schema_version(payload, source=Path("test.json"))

    def test_unknown_future_version_is_rejected(self):
        payload = _minimal_payload(version="99")
        with pytest.raises(InputFileError, match="unsupported schema_version"):
            check_schema_version(payload, source=Path("test.json"))

    def test_non_string_version_is_rejected(self):
        payload = _minimal_payload(version=1)  # int, not "1"
        with pytest.raises(InputFileError, match="non-string schema_version"):
            check_schema_version(payload, source=Path("test.json"))

    def test_boolean_version_is_rejected(self):
        payload = _minimal_payload(version=True)
        with pytest.raises(InputFileError, match="non-string schema_version"):
            check_schema_version(payload, source=Path("test.json"))

    def test_known_legacy_version_with_migration_is_accepted(self, monkeypatch):
        # Simulate a future world where v1 is legacy and we migrate to v2.
        def fake_v1_to_v2(payload: dict) -> dict:
            return {**payload, "schema_version": "2"}

        monkeypatch.setitem(MIGRATIONS, "0", fake_v1_to_v2)
        payload = _minimal_payload(version="0")
        # check_schema_version alone does NOT mutate -- just approves.
        check_schema_version(payload, source=Path("t.json"))


class TestApplyMigrations:
    def test_current_version_is_noop(self):
        payload = _minimal_payload(version=CURRENT_SCHEMA_VERSION)
        result = apply_migrations(payload)
        assert result["schema_version"] == CURRENT_SCHEMA_VERSION
        # All other fields preserved.
        assert result["source"] == payload["source"]

    def test_missing_version_is_treated_as_current(self):
        payload = _minimal_payload(version=None)
        result = apply_migrations(payload)
        assert result["schema_version"] == CURRENT_SCHEMA_VERSION

    def test_non_string_version_raises(self):
        payload = _minimal_payload(version=42)
        with pytest.raises(InputFileError, match="schema_version must be a string"):
            apply_migrations(payload)

    def test_missing_migration_path_raises(self):
        # A legacy version we never registered.
        payload = _minimal_payload(version="0")
        with pytest.raises(InputFileError, match="no migration path"):
            apply_migrations(payload)

    def test_registered_migration_upgrades_payload(self, monkeypatch):
        def v0_to_v1(payload: dict) -> dict:
            return {**payload, "schema_version": "1", "migrated": True}

        monkeypatch.setitem(MIGRATIONS, "0", v0_to_v1)
        payload = _minimal_payload(version="0")
        result = apply_migrations(payload)
        assert result["schema_version"] == "1"
        assert result["migrated"] is True

    def test_migration_that_does_not_advance_version_raises(self, monkeypatch):
        def noop_migration(payload: dict) -> dict:
            return {**payload, "schema_version": "0"}  # stays at "0"

        monkeypatch.setitem(MIGRATIONS, "0", noop_migration)
        payload = _minimal_payload(version="0")
        with pytest.raises(InputFileError, match="did not advance"):
            apply_migrations(payload)

    def test_does_not_mutate_input(self):
        payload = _minimal_payload(version=None)
        apply_migrations(payload)
        # Input payload must not be mutated.
        assert "schema_version" not in payload
