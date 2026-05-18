"""Tests for scripts/generate-v030-baselines.py (#779 split.json schema)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

# Import the module under test (scripts/generate-v030-baselines.py -- hyphenated
# name requires importlib.util.spec_from_file_location)
SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
_spec = importlib.util.spec_from_file_location(
    "generate_v030_baselines", SCRIPTS_DIR / "generate-v030-baselines.py"
)
assert _spec is not None and _spec.loader is not None
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)


def _valid_payload() -> dict:
    return {
        "schema_version": "1",
        "label": "obs-20260116",
        "source_file": "20260116/2026-01-16 22-12-57.mkv",
        "source_size_bytes": 39721920176,
        "source_dir_label": "20260116",
        "generated_at": "2026-05-18T12:00:00Z",
        "splits": [
            {
                "index": 1,
                "output_file": "match_001.mp4",
                "size_bytes": 12345678,
                "sha256": "a" * 64,
            },
            {
                "index": 2,
                "output_file": "match_002.mp4",
                "size_bytes": 22222222,
                "sha256": "b" * 64,
            },
        ],
    }


def test_valid_payload_passes() -> None:
    """A fully valid payload must not raise."""
    gen.validate_split_baseline(_valid_payload())


@pytest.mark.parametrize(
    "missing_field",
    [
        "schema_version",
        "label",
        "source_file",
        "source_size_bytes",
        "source_dir_label",
        "generated_at",
        "splits",
    ],
)
def test_missing_required_top_level_field_raises(missing_field: str) -> None:
    """Each required top-level field is enforced."""
    payload = _valid_payload()
    del payload[missing_field]
    with pytest.raises(ValueError, match=missing_field):
        gen.validate_split_baseline(payload)


def test_unknown_schema_version_raises() -> None:
    """Reject future schema versions so consumers fail loudly on upgrade."""
    payload = _valid_payload()
    payload["schema_version"] = "2"
    with pytest.raises(ValueError, match="schema_version"):
        gen.validate_split_baseline(payload)


@pytest.mark.parametrize(
    "label",
    ["obs-1234567", "obs-202601167", "20260116", "obs_20260116", ""],
)
def test_invalid_label_pattern_raises(label: str) -> None:
    """Label must match ``obs-<YYYYMMDD>`` exactly."""
    payload = _valid_payload()
    payload["label"] = label
    with pytest.raises(ValueError, match="label"):
        gen.validate_split_baseline(payload)


def test_non_positive_source_size_raises() -> None:
    payload = _valid_payload()
    payload["source_size_bytes"] = 0
    with pytest.raises(ValueError, match="source_size_bytes"):
        gen.validate_split_baseline(payload)


def test_empty_splits_raises() -> None:
    """A baseline with zero splits has no signal -- reject."""
    payload = _valid_payload()
    payload["splits"] = []
    with pytest.raises(ValueError, match="splits"):
        gen.validate_split_baseline(payload)


@pytest.mark.parametrize(
    "missing_field",
    ["index", "output_file", "size_bytes", "sha256"],
)
def test_missing_required_split_field_raises(missing_field: str) -> None:
    payload = _valid_payload()
    del payload["splits"][0][missing_field]
    with pytest.raises(ValueError, match=missing_field):
        gen.validate_split_baseline(payload)


@pytest.mark.parametrize(
    "bad_sha256",
    [
        "a" * 63,  # too short
        "a" * 65,  # too long
        "g" * 64,  # non-hex
        "A" * 64,  # uppercase rejected (we normalise to lowercase)
        "",
    ],
)
def test_invalid_sha256_raises(bad_sha256: str) -> None:
    payload = _valid_payload()
    payload["splits"][0]["sha256"] = bad_sha256
    with pytest.raises(ValueError, match="sha256"):
        gen.validate_split_baseline(payload)


@pytest.mark.parametrize(
    "bad_output_file",
    [
        "match_1.mp4",  # not zero-padded to 3 digits
        "match_0001.mp4",  # too many digits
        "match_001.mkv",  # wrong extension
        "20260116_1.mp4",  # legacy naming
        "match_001",  # missing extension
        "match_abc.mp4",  # non-numeric
    ],
)
def test_invalid_output_file_pattern_raises(bad_output_file: str) -> None:
    """output_file must match ``match_NNN.mp4`` (placeholder names from detect)."""
    payload = _valid_payload()
    payload["splits"][0]["output_file"] = bad_output_file
    with pytest.raises(ValueError, match="output_file"):
        gen.validate_split_baseline(payload)


def test_non_positive_split_size_raises() -> None:
    payload = _valid_payload()
    payload["splits"][0]["size_bytes"] = 0
    with pytest.raises(ValueError, match="size_bytes"):
        gen.validate_split_baseline(payload)


def test_non_positive_index_raises() -> None:
    payload = _valid_payload()
    payload["splits"][0]["index"] = 0
    with pytest.raises(ValueError, match="index"):
        gen.validate_split_baseline(payload)


def test_index_must_be_sequential_starting_from_1() -> None:
    """splits[i].index must be 1, 2, 3, ... (mirrors ``allaganeye detect`` output)."""
    payload = _valid_payload()
    payload["splits"][0]["index"] = 1
    payload["splits"][1]["index"] = 3  # gap, not 2
    with pytest.raises(ValueError, match="index"):
        gen.validate_split_baseline(payload)


def test_load_and_validate_reads_json_file(tmp_path: Path) -> None:
    """``load_and_validate`` is the convenience reader used by the smoke test."""
    payload = _valid_payload()
    p = tmp_path / "obs-20260116.split.json"
    p.write_text(json.dumps(payload), encoding="utf-8")

    loaded = gen.load_and_validate(p)
    assert loaded == payload


def test_load_and_validate_propagates_validation_error(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["splits"][0]["sha256"] = "not-hex"
    p = tmp_path / "obs-20260116.split.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="sha256"):
        gen.load_and_validate(p)
