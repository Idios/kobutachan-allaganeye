"""L4 イベント出力フォーマットの契約テスト (#127 / #1106 作業項目 4)。

形の正は `schemas/metadata.schema.json` の `$defs/HighlightEvent`、設計の正は
`docs/superpowers/specs/2026-11-16-l4-event-output-format-design.md`。ここが固定するのは:

1. producer (`allaganeye/video/indicators.py::event_to_payload`) の出力が schema に適合する
2. 互換ルール（未知フィールド許容 / `signal_id` は enum でない / 未知 `signal_id` を
   読み手が無視できる）が **schema 側で** 守られている
3. codegen に載せた結果（`metadata_types.HighlightEvent`）が schema とずれていない
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from allaganeye.metadata_types import HighlightEvent
from allaganeye.video.indicators import IndicatorEvent, event_to_payload

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "schemas" / "metadata.schema.json"

DEF_NAME = "HighlightEvent"


def _schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _event_schema() -> dict[str, Any]:
    return _schema()["$defs"][DEF_NAME]


def _validator() -> Draft202012Validator:
    # `$ref` を解決するため `$defs` を引き継いだ**検証専用の root** を作る。
    # metadata の root をそのまま使うと `additionalProperties: false` が効いて
    # イベント 1 件を検証できない。
    root = _schema()
    schema = {
        "$schema": root.get("$schema"),
        "$defs": root["$defs"],
        "$ref": f"#/$defs/{DEF_NAME}",
    }
    return Draft202012Validator(schema)


def _payload(**overrides: Any) -> dict[str, Any]:
    base = event_to_payload(
        IndicatorEvent(kind="ko", start=493.4, end=494.9, score=0.93, samples=15),
        match_index=1,
    )
    return {**base, **overrides}


# ---------------------------------------------------------------------------
# 1. producer の出力が schema に適合する
# ---------------------------------------------------------------------------


def test_producer_payload_matches_schema() -> None:
    _validator().validate(_payload())


def test_producer_maps_kind_to_signal_id() -> None:
    ko = event_to_payload(
        IndicatorEvent(kind="ko", start=1.0, end=2.0, score=0.9, samples=10),
        match_index=1,
    )
    assist = event_to_payload(
        IndicatorEvent(kind="assist", start=1.0, end=2.0, score=0.9, samples=10),
        match_index=None,
    )
    assert ko["signal_id"] == "ko_indicator"
    assert assist["signal_id"] == "assist_indicator"
    assert assist["match_index"] is None


def test_producer_rounds_time_and_score() -> None:
    payload = event_to_payload(
        IndicatorEvent(kind="ko", start=1.2345, end=2.3456, score=0.12345, samples=3),
        match_index=2,
    )
    assert payload["timestamp"] == pytest.approx(1.23)
    assert payload["end"] == pytest.approx(2.35)
    assert payload["score"] == pytest.approx(0.123)
    assert payload["evidence"] == {"samples": 3}


def test_producer_emits_exactly_the_documented_keys() -> None:
    assert set(_payload()) == set(_event_schema()["required"])


def test_events_at_root_are_wired_to_the_def() -> None:
    root = _schema()
    events = root["properties"]["events"]
    assert events["type"] == "array"
    assert events["items"] == {"$ref": f"#/$defs/{DEF_NAME}"}
    # 未検出の recording は持たないので optional。
    assert "events" not in root["required"]


# ---------------------------------------------------------------------------
# 2. 互換ルール（#127 の 4 節）
# ---------------------------------------------------------------------------


def test_unknown_field_is_allowed() -> None:
    """producer はフィールドを足せる（schema 違反にしない）。"""
    assert _event_schema()["additionalProperties"] is True
    _validator().validate(_payload(future_field={"anything": [1, 2, 3]}))


def test_signal_id_is_not_an_enum() -> None:
    """`signal_id` を enum にすると信号追加が破壊的変更になる。"""
    signal_id = _event_schema()["properties"]["signal_id"]
    assert signal_id["type"] == "string"
    assert "enum" not in signal_id
    # 未知の signal_id を持つイベントも schema は通す（読み手が無視する）。
    _validator().validate(_payload(signal_id="kill_feed"))


def test_unknown_evidence_keys_are_allowed() -> None:
    _validator().validate(_payload(evidence={"samples": 4, "template": "ko.v2"}))


def test_match_index_may_be_null_but_not_below_one() -> None:
    _validator().validate(_payload(match_index=None))
    with pytest.raises(ValidationError):
        _validator().validate(_payload(match_index=0))


@pytest.mark.parametrize("missing", sorted(_event_schema()["required"]))
def test_required_field_cannot_be_dropped(missing: str) -> None:
    payload = _payload()
    payload.pop(missing)
    with pytest.raises(ValidationError):
        _validator().validate(payload)


# ---------------------------------------------------------------------------
# 3. codegen の pin（`schemas/**` -> `metadata_types.py`）
# ---------------------------------------------------------------------------


def test_generated_typeddict_tracks_schema() -> None:
    """生成型のキー集合が schema のフィールド集合と一致する（#612 codegen）。"""
    assert set(HighlightEvent.__annotations__) == set(_event_schema()["properties"])


def test_root_typeddict_has_events() -> None:
    from allaganeye.metadata_types import Metadata

    assert "events" in Metadata.__annotations__
