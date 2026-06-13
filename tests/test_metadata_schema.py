"""JSON Schema validity tests via `jsonschema` (#612).

Mirrors gui/src/types/__tests__/schema-validity.test.ts so the Python
CI job catches the same drift without needing a Node runtime.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "schemas" / "metadata.schema.json"


def _load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _valid_sample() -> dict[str, Any]:
    return {
        "schema_version": "1",
        "source": "C:/videos/sample.mkv",
        "source_duration": 7200,
        "source_duration_display": "02:00:00",
        "source_fps": 60,
        "detected_at": "2026-04-28T00:00:00Z",
        "detection_started_at": "2026-04-28T00:00:00Z",
        "detection_completed_at": "2026-04-28T00:01:30Z",
        "detection_params": {
            "sample_interval": 2.0,
            "blackout_threshold": 15,
            "min_match_duration": 300,
            "min_blackout_duration": 1.5,
            "no_audio": False,
            "use_gpu": None,
            "workers": None,
            # optional provenance fields (#821): writer は常に出力、読み込みは
            # 欠落許容 (pre-#821 metadata)。masked = request flag、
            # masked_fallback_used = resolved path (auto-fallback 含む)。
            "vtuber": False,
            "masked": False,
            "masked_fallback_used": False,
        },
        "matches": [
            {
                "index": 1,
                "start_time": 60,
                "end_time": 1200,
                "start_display": "01:00",
                "end_display": "20:00",
                "duration": 1140,
                "duration_display": "19m00s",
                "type": "fl_match",
                "output_file": "match_001.mp4",
            }
        ],
        "gaps": [],
        "warnings": [],
        "system_info": {
            "gpu_vendors_available": ["nvidia"],
            "gpu_vendor_used": "nvidia",
            "vendor_preference": ["nvidia", "amd", "intel"],
        },
    }


def test_schema_is_valid_draft_2020_12():
    """The schema itself must conform to the draft-2020-12 meta-schema."""
    schema = _load_schema()
    Draft202012Validator.check_schema(schema)


def test_valid_sample_passes():
    schema = _load_schema()
    Draft202012Validator(schema).validate(_valid_sample())


def test_missing_required_source_rejected():
    schema = _load_schema()
    broken = _valid_sample()
    del broken["source"]
    validator = Draft202012Validator(schema)
    assert not validator.is_valid(broken)


def test_invalid_match_type_rejected():
    schema = _load_schema()
    broken = _valid_sample()
    broken["matches"][0]["type"] = "fanfare_only"
    validator = Draft202012Validator(schema)
    assert not validator.is_valid(broken)


def test_optional_fields_omitted_accepted():
    """pre-#515 / pre-#586 / pre-#591 metadata.json must still validate."""
    schema = _load_schema()
    minimal = _valid_sample()
    for key in (
        "schema_version",
        "source_fps",
        "warnings",
        "system_info",
        "detection_started_at",
        "detection_completed_at",
    ):
        del minimal[key]
    Draft202012Validator(schema).validate(minimal)


@pytest.mark.parametrize(
    "use_gpu_value",
    [True, False, 1, 0, None],
)
def test_use_gpu_accepts_number_boolean_null(use_gpu_value):
    """`use_gpu` must accept the union from docs/metadata-spec.md."""
    schema = _load_schema()
    sample = _valid_sample()
    sample["detection_params"]["use_gpu"] = use_gpu_value
    Draft202012Validator(schema).validate(sample)


def test_unknown_root_field_rejected():
    """Writer contract: extra top-level keys must be rejected."""
    schema = _load_schema()
    broken = _valid_sample()
    broken["unknown_root_field"] = "x"
    validator = Draft202012Validator(schema)
    assert not validator.is_valid(broken)


def test_unknown_match_field_rejected():
    """Writer contract: GUI-only edit fields (name / type_override / edited)
    must never reach metadata.json proper (#612). zod's `.passthrough()`
    keeps them in metadata.draft.json only."""
    schema = _load_schema()
    broken = _valid_sample()
    broken["matches"][0]["name"] = "GUI-only edit field"
    validator = Draft202012Validator(schema)
    assert not validator.is_valid(broken)


def test_unknown_detection_params_field_rejected():
    schema = _load_schema()
    broken = _valid_sample()
    broken["detection_params"]["future_param"] = 1
    validator = Draft202012Validator(schema)
    assert not validator.is_valid(broken)


def test_warning_context_accepts_arbitrary_keys():
    """`MetadataWarning.context` is intentionally permissive so emitters
    can attach diagnostic payloads without bumping the schema."""
    schema = _load_schema()
    sample = _valid_sample()
    sample["warnings"] = [
        {
            "code": "audio_skipped",
            "severity": "info",
            "context": {"reason": "no_audio_track", "frame": 12345},
        }
    ]
    Draft202012Validator(schema).validate(sample)
