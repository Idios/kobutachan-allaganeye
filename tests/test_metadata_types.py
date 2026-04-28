"""`_build_metadata_payload` conformance with JSON Schema and TypedDict (#612).

Bridges the Python builder and the schema/codegen pair:

* The dict literal returned by ``_build_metadata_payload`` validates
  against ``schemas/metadata.schema.json`` (runtime check via
  ``jsonschema``).
* The same payload covers every required key of the auto-generated
  ``Metadata`` TypedDict (so removing a JSON Schema property without
  updating the builder fails CI).

These complement the static pyright check on the builder's return type.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import NotRequired, get_origin, get_type_hints

from jsonschema import Draft202012Validator

from allaganeye.commands.split_matches import (
    _build_metadata_payload,
    _build_system_info,
)
from allaganeye.config import SplitConfig
from allaganeye.metadata_types import Metadata
from allaganeye.video.detector import MatchBoundary

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "schemas" / "metadata.schema.json"


def _build_payload(tmp_path: Path) -> Metadata:
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    boundaries: list[MatchBoundary] = [
        {"start": 60.0, "end": 1200.0, "type": "fl_match"},
        {"start": 1500.0, "end": 2400.0, "type": "unknown"},
    ]
    output_files = [Path("match_001.mp4"), Path("match_002.mp4")]
    system_info = _build_system_info(available_vendors=["nvidia"], vendor_used="nvidia")
    return _build_metadata_payload(
        video_path=tmp_path / "sample.mkv",
        source_duration=7200.0,
        source_fps=60.0,
        detected_at="2026-04-28T00:00:00Z",
        effective_interval=2.0,
        config=config,
        boundaries=boundaries,
        output_files=output_files,
        gaps=[],
        system_info=system_info,
    )


def test_payload_validates_against_json_schema(tmp_path: Path):
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    payload = _build_payload(tmp_path)
    Draft202012Validator(schema).validate(payload)


def test_payload_covers_required_typeddict_keys(tmp_path: Path):
    """Every required Metadata key (i.e. not NotRequired) is populated.

    We can't rely on ``Metadata.__required_keys__`` because
    ``from __future__ import annotations`` (emitted by
    ``datamodel-code-generator``) stringifies every annotation; the
    NotRequired markers are invisible to TypedDict's class-creation
    introspection, so every key shows up as required at the class
    level. Using ``get_type_hints`` re-resolves them to live ``typing``
    objects and ``get_origin(NotRequired[T])`` then identifies the
    optional keys correctly on Python 3.11+.
    """
    hints = get_type_hints(Metadata, include_extras=True)
    required = {
        key
        for key, annotation in hints.items()
        if get_origin(annotation) is not NotRequired
    }
    payload = _build_payload(tmp_path)
    missing = required - set(payload.keys())
    assert not missing, f"required Metadata keys missing from payload: {missing}"


def test_match_type_narrows_to_literal(tmp_path: Path):
    """Builder normalizes unknown MatchBoundary.type to 'unknown'."""
    payload = _build_payload(tmp_path)
    types = {m["type"] for m in payload["matches"]}
    assert types <= {"fl_match", "unknown"}


def test_legacy_unknown_type_is_normalized(tmp_path: Path):
    """A MatchBoundary carrying a stray classification falls back to 'unknown'."""
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    boundaries: list[MatchBoundary] = [
        {"start": 0.0, "end": 100.0, "type": "non_fl"},
    ]
    payload = _build_metadata_payload(
        video_path=tmp_path / "sample.mkv",
        source_duration=200.0,
        source_fps=60.0,
        detected_at="2026-04-28T00:00:00Z",
        effective_interval=2.0,
        config=config,
        boundaries=boundaries,
        output_files=[Path("match_001.mp4")],
        gaps=[],
        system_info=_build_system_info(available_vendors=[], vendor_used=None),
    )
    assert payload["matches"][0]["type"] == "unknown"
