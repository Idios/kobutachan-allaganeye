"""Tests for ``run_split_from_metadata`` (#463).

The legacy ``run_split(video)`` flow has separate coverage in
``test_split_matches.py``; the cases here focus on the new code path
where the entry point is a ``metadata.json`` and no detection runs.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from allaganeye.commands.split_matches import (
    _split_and_write_metadata,
    run_split_from_metadata,
)
from allaganeye.config import SplitConfig
from allaganeye.exceptions import InputFileError
from allaganeye.video.probe import ProbeResult

MODULE = "allaganeye.commands.split_matches"

PROBE_RESULT: ProbeResult = {
    "duration": 1800.0,
    "width": 1920,
    "height": 1080,
    "fps": 30.0,
    "fps_num": 30,
    "fps_den": 1,
    "codec": "h264",
    "audio_codec": "aac",
}


def _sample_metadata(source_path: str = "input.mp4") -> dict:
    return {
        "source": source_path,
        "source_duration": 1800.0,
        "source_duration_display": "30:00",
        "detected_at": "2026-04-22T00:00:00Z",
        "detection_params": {
            "sample_interval": 1.0,
            "blackout_threshold": 15.0,
            "min_match_duration": 300.0,
            "min_blackout_duration": 3.0,
            "no_audio": False,
            "use_gpu": None,
            "workers": None,
        },
        "matches": [
            {
                "index": 1,
                "start_time": 0.0,
                "end_time": 600.0,
                "start_display": "00:00",
                "end_display": "10:00",
                "duration": 600.0,
                "duration_display": "10m00s",
                "type": "fl_match",
                "output_file": "match_001.mp4",
            },
            {
                "index": 2,
                "start_time": 610.0,
                "end_time": 1200.0,
                "start_display": "10:10",
                "end_display": "20:00",
                "duration": 590.0,
                "duration_display": "09m50s",
                "type": "fl_match",
                "output_file": "match_002.mp4",
            },
        ],
        "gaps": [],
    }


def _write_metadata(tmp_path: Path, payload: dict) -> Path:
    meta_path = tmp_path / "metadata.json"
    meta_path.write_text(json.dumps(payload), encoding="utf-8")
    return meta_path


def test_run_split_from_metadata_skips_detection(tmp_path):
    source = tmp_path / "input.mp4"
    source.write_bytes(b"")  # existence check

    payload = _sample_metadata(str(source))
    meta_path = _write_metadata(tmp_path, payload)
    config = SplitConfig(output_dir=tmp_path / "out", min_match_duration=60.0)

    with (
        patch(f"{MODULE}.probe_video", return_value=PROBE_RESULT) as mock_probe,
        patch(f"{MODULE}.detect_match_boundaries") as mock_detect,
        patch(
            f"{MODULE}.split_video",
            return_value=[
                tmp_path / "out" / "match_001.mp4",
                tmp_path / "out" / "match_002.mp4",
            ],
        ) as mock_split,
    ):
        run_split_from_metadata(meta_path, config, quiet=True)

    mock_probe.assert_called_once_with(source)
    mock_detect.assert_not_called()
    mock_split.assert_called_once()
    args = mock_split.call_args[0]
    assert args[0] == source
    boundaries_arg = args[1]
    assert [b["start"] for b in boundaries_arg] == [0.0, 610.0]
    assert [b["end"] for b in boundaries_arg] == [600.0, 1200.0]


def test_run_split_from_metadata_preserves_detection_timestamps(tmp_path):
    """post-#586 metadata では元の started/completed が保持される (Round 1 #586).

    `--from-metadata` は再検知しないので、GUI「所要」表示が「検知時の所要」
    を維持し続けるよう、元 metadata の detection_started_at /
    detection_completed_at を pass-through する。
    """
    source = tmp_path / "input.mp4"
    source.write_bytes(b"")
    payload = {
        **_sample_metadata(str(source)),
        "detection_started_at": "2026-04-22T00:00:00Z",
        "detection_completed_at": "2026-04-22T00:04:27Z",
    }
    meta_path = _write_metadata(tmp_path, payload)
    config = SplitConfig(output_dir=tmp_path / "out", min_match_duration=60.0)

    with (
        patch(f"{MODULE}.probe_video", return_value=PROBE_RESULT),
        patch(
            f"{MODULE}.split_video",
            return_value=[
                tmp_path / "out" / "match_001.mp4",
                tmp_path / "out" / "match_002.mp4",
            ],
        ),
    ):
        run_split_from_metadata(meta_path, config, quiet=True)

    out_meta = tmp_path / "out" / "metadata.json"
    fresh = json.loads(out_meta.read_text("utf-8"))
    # 元の started/completed がそのまま再書き込みされる。
    assert fresh["detection_started_at"] == "2026-04-22T00:00:00Z"
    assert fresh["detection_completed_at"] == "2026-04-22T00:04:27Z"


def test_run_split_from_metadata_legacy_falls_back_to_fresh_capture(tmp_path):
    """pre-#586 metadata (両フィールド欠落) では fresh capture で fallback.

    legacy metadata.json (#586 以前に生成) には detection_started_at /
    detection_completed_at が無い。後方互換のため、_split_and_write_metadata
    の None fallback (started=detected_at / completed=_iso_utc_now()) で
    新規値を埋め、再書き込み後の metadata は post-#586 形式になる。
    """
    source = tmp_path / "input.mp4"
    source.write_bytes(b"")
    # _sample_metadata は detection_started_at / completed_at を含めない =
    # legacy 状態。detected_at だけある。
    payload = _sample_metadata(str(source))
    assert "detection_started_at" not in payload
    assert "detection_completed_at" not in payload
    meta_path = _write_metadata(tmp_path, payload)
    config = SplitConfig(output_dir=tmp_path / "out", min_match_duration=60.0)

    with (
        patch(f"{MODULE}.probe_video", return_value=PROBE_RESULT),
        patch(
            f"{MODULE}.split_video",
            return_value=[
                tmp_path / "out" / "match_001.mp4",
                tmp_path / "out" / "match_002.mp4",
            ],
        ),
    ):
        run_split_from_metadata(meta_path, config, quiet=True)

    out_meta = tmp_path / "out" / "metadata.json"
    fresh = json.loads(out_meta.read_text("utf-8"))
    # fallback: started = detected_at の値、completed = writer 直前の
    # _iso_utc_now() (= 'Z' 終端 + parseable)。
    assert fresh["detection_started_at"] == fresh["detected_at"]
    completed_at = fresh["detection_completed_at"]
    assert isinstance(completed_at, str) and completed_at.endswith("Z")


def test_run_split_from_metadata_rewrites_metadata_without_note(tmp_path):
    source = tmp_path / "input.mp4"
    source.write_bytes(b"")
    # Seed a legacy metadata file with a "note" to prove it doesn't
    # propagate into the fresh write.
    payload = {**_sample_metadata(str(source)), "note": "legacy caveat"}
    meta_path = _write_metadata(tmp_path, payload)
    config = SplitConfig(output_dir=tmp_path / "out", min_match_duration=60.0)

    with (
        patch(f"{MODULE}.probe_video", return_value=PROBE_RESULT),
        patch(
            f"{MODULE}.split_video",
            return_value=[
                tmp_path / "out" / "match_001.mp4",
                tmp_path / "out" / "match_002.mp4",
            ],
        ),
    ):
        run_split_from_metadata(meta_path, config, quiet=True)

    out_meta = tmp_path / "out" / "metadata.json"
    assert out_meta.exists()
    fresh = json.loads(out_meta.read_text("utf-8"))
    assert "note" not in fresh


def test_run_split_from_metadata_missing_source_raises(tmp_path):
    # Absolute path inside a fresh metadata file that does not exist.
    payload = _sample_metadata(str(tmp_path / "missing.mp4"))
    meta_path = _write_metadata(tmp_path, payload)
    config = SplitConfig(output_dir=tmp_path / "out", min_match_duration=60.0)

    with pytest.raises(InputFileError, match="source video"):
        run_split_from_metadata(meta_path, config, quiet=True)


def test_run_split_from_metadata_missing_matches_raises(tmp_path):
    source = tmp_path / "input.mp4"
    source.write_bytes(b"")
    payload = _sample_metadata(str(source))
    payload["matches"] = []
    meta_path = _write_metadata(tmp_path, payload)
    config = SplitConfig(output_dir=tmp_path / "out", min_match_duration=60.0)

    with pytest.raises(InputFileError, match="no match entries"):
        run_split_from_metadata(meta_path, config, quiet=True)


def test_run_split_from_metadata_nonexistent_file_raises(tmp_path):
    config = SplitConfig(output_dir=tmp_path / "out", min_match_duration=60.0)
    with pytest.raises(InputFileError, match="metadata file not found"):
        run_split_from_metadata(tmp_path / "nope.json", config, quiet=True)


def test_run_split_from_metadata_invalid_json_raises(tmp_path):
    meta_path = tmp_path / "metadata.json"
    meta_path.write_text("{ not valid json", encoding="utf-8")
    config = SplitConfig(output_dir=tmp_path / "out", min_match_duration=60.0)
    with pytest.raises(InputFileError, match="not valid JSON"):
        run_split_from_metadata(meta_path, config, quiet=True)


def test_split_and_write_metadata_has_no_note_field(tmp_path):
    """Regression: ``_split_and_write_metadata`` stopped emitting `note` in #463."""
    from allaganeye.video.detector import MatchBoundary

    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    boundaries: list[MatchBoundary] = [
        {"start": 0.0, "end": 120.0, "type": "fl_match"},
    ]

    with patch(
        f"{MODULE}.split_video",
        return_value=[tmp_path / "match_001.mp4"],
    ):
        _split_and_write_metadata(
            tmp_path / "input.mp4",
            boundaries,
            [],
            PROBE_RESULT,
            config,
            effective_interval=1.0,
            detected_at="2026-04-22T00:00:00Z",
            system_info={
                "gpu_vendors_available": [],
                "gpu_vendor_used": None,
                "vendor_preference": ["nvidia", "amd", "intel"],
            },
            quiet=True,
        )

    payload = json.loads((tmp_path / "metadata.json").read_text("utf-8"))
    assert "note" not in payload


def test_split_and_write_metadata_contains_schema_version(tmp_path):
    """#515: newly written metadata.json declares ``schema_version: "1"``."""
    from allaganeye.video.detector import MatchBoundary

    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    boundaries: list[MatchBoundary] = [
        {"start": 0.0, "end": 120.0, "type": "fl_match"},
    ]

    with patch(
        f"{MODULE}.split_video",
        return_value=[tmp_path / "match_001.mp4"],
    ):
        _split_and_write_metadata(
            tmp_path / "input.mp4",
            boundaries,
            [],
            PROBE_RESULT,
            config,
            effective_interval=1.0,
            detected_at="2026-04-22T00:00:00Z",
            system_info={
                "gpu_vendors_available": [],
                "gpu_vendor_used": None,
                "vendor_preference": ["nvidia", "amd", "intel"],
            },
            quiet=True,
        )

    payload = json.loads((tmp_path / "metadata.json").read_text("utf-8"))
    assert payload["schema_version"] == "1"


def test_split_and_write_metadata_emits_empty_warnings_array(tmp_path):
    """#518: metadata.json writer always emits a `warnings` field (default []).

    Locks in the schema for consumers so that once concrete codes ship in
    a later PR, readers already treat `warnings` as a known key.
    """
    from allaganeye.video.detector import MatchBoundary

    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    boundaries: list[MatchBoundary] = [
        {"start": 0.0, "end": 120.0, "type": "fl_match"},
    ]

    with patch(
        f"{MODULE}.split_video",
        return_value=[tmp_path / "match_001.mp4"],
    ):
        _split_and_write_metadata(
            tmp_path / "input.mp4",
            boundaries,
            [],
            PROBE_RESULT,
            config,
            effective_interval=1.0,
            detected_at="2026-04-22T00:00:00Z",
            system_info={
                "gpu_vendors_available": [],
                "gpu_vendor_used": None,
                "vendor_preference": ["nvidia", "amd", "intel"],
            },
            quiet=True,
        )

    payload = json.loads((tmp_path / "metadata.json").read_text("utf-8"))
    assert payload["warnings"] == []


def test_run_split_from_metadata_accepts_legacy_file_without_schema_version(
    tmp_path,
):
    """#515: pre-0.2.0 metadata.json files without schema_version still load."""
    meta = _sample_metadata(source_path=str(tmp_path / "input.mp4"))
    # legacy file explicitly has no schema_version
    assert "schema_version" not in meta
    meta_path = tmp_path / "metadata.json"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    (tmp_path / "input.mp4").write_bytes(b"")  # satisfies source path check

    out_dir = tmp_path / "out"
    config = SplitConfig(output_dir=out_dir, min_match_duration=60.0)
    with (
        patch(f"{MODULE}.probe_video", return_value=PROBE_RESULT),
        patch(
            f"{MODULE}.split_video",
            return_value=[
                out_dir / "match_001.mp4",
                out_dir / "match_002.mp4",
            ],
        ),
    ):
        run_split_from_metadata(meta_path, config, quiet=True)  # no raise


def test_run_split_from_metadata_rejects_future_schema_version(tmp_path):
    """#515: metadata.json with an unknown future schema_version is rejected."""
    meta = _sample_metadata(source_path=str(tmp_path / "input.mp4"))
    meta["schema_version"] = "99"
    meta_path = tmp_path / "metadata.json"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    config = SplitConfig(output_dir=tmp_path / "out", min_match_duration=60.0)
    with pytest.raises(InputFileError, match="unsupported schema_version"):
        run_split_from_metadata(meta_path, config, quiet=True)


# -- #644 brightness_samples preserve through --from-metadata --


def test_run_split_from_metadata_preserves_brightness_samples(tmp_path):
    """#644 -- --from-metadata 経路で元 metadata.json の brightness_samples
    が新 metadata.json に preserve されること (PR #626 の detection_started_at
    preserve と同パターン)。
    """
    source = tmp_path / "input.mp4"
    source.write_bytes(b"")
    original_samples = {
        "interval_s": 0.5,
        "values": [10.0, 12.5, 15.0, 17.5],
    }
    payload = {
        **_sample_metadata(str(source)),
        "brightness_samples": original_samples,
    }
    meta_path = _write_metadata(tmp_path, payload)
    config = SplitConfig(output_dir=tmp_path / "out", min_match_duration=60.0)

    with (
        patch(f"{MODULE}.probe_video", return_value=PROBE_RESULT),
        patch(
            f"{MODULE}.split_video",
            return_value=[
                tmp_path / "out" / "match_001.mp4",
                tmp_path / "out" / "match_002.mp4",
            ],
        ),
    ):
        run_split_from_metadata(meta_path, config, quiet=True)

    out_meta = tmp_path / "out" / "metadata.json"
    fresh = json.loads(out_meta.read_text("utf-8"))
    assert "brightness_samples" in fresh, (
        "--from-metadata は元 metadata の brightness_samples を新 metadata に "
        "preserve するはず (#644 / PR #626 同パターン)"
    )
    assert fresh["brightness_samples"] == original_samples


def test_run_split_from_metadata_omits_brightness_samples_when_source_lacks(tmp_path):
    """#644 -- --from-metadata 経路で元 metadata に brightness_samples が
    無い場合、新 metadata.json にも無いまま (legacy / cache hit 互換)。
    """
    source = tmp_path / "input.mp4"
    source.write_bytes(b"")
    # _sample_metadata はデフォルトで brightness_samples を含めない
    payload = _sample_metadata(str(source))
    assert "brightness_samples" not in payload
    meta_path = _write_metadata(tmp_path, payload)
    config = SplitConfig(output_dir=tmp_path / "out", min_match_duration=60.0)

    with (
        patch(f"{MODULE}.probe_video", return_value=PROBE_RESULT),
        patch(
            f"{MODULE}.split_video",
            return_value=[
                tmp_path / "out" / "match_001.mp4",
                tmp_path / "out" / "match_002.mp4",
            ],
        ),
    ):
        run_split_from_metadata(meta_path, config, quiet=True)

    out_meta = tmp_path / "out" / "metadata.json"
    fresh = json.loads(out_meta.read_text("utf-8"))
    assert "brightness_samples" not in fresh, (
        "元 metadata に brightness_samples が無いなら新 metadata にも書かない"
    )


# -- #805 段階1: post_match_trailing_dropped warning preserve through --from-metadata --


def test_run_split_from_metadata_preserves_trailing_drop_warning(tmp_path):
    """#805 段階1 -- --from-metadata 経路で元 metadata.json の
    post_match_trailing_dropped warning が新 metadata.json に preserve される。

    detect -> split --from-metadata -o <same dir> で記録済み warning を
    silent に上書きしないこと (brightness_samples #644 / timing #586 同パターン)。
    """
    source = tmp_path / "input.mp4"
    source.write_bytes(b"")
    original_warning = {
        "code": "post_match_trailing_dropped",
        "message_en": "A trailing post-match segment was dropped.",
        "severity": "warn",
        "context": {"start": 1000.0, "end": 1800.0},
    }
    payload = {
        **_sample_metadata(str(source)),
        "warnings": [original_warning],
    }
    meta_path = _write_metadata(tmp_path, payload)
    config = SplitConfig(output_dir=tmp_path / "out", min_match_duration=60.0)

    with (
        patch(f"{MODULE}.probe_video", return_value=PROBE_RESULT),
        patch(
            f"{MODULE}.split_video",
            return_value=[
                tmp_path / "out" / "match_001.mp4",
                tmp_path / "out" / "match_002.mp4",
            ],
        ),
    ):
        run_split_from_metadata(meta_path, config, quiet=True)

    out_meta = tmp_path / "out" / "metadata.json"
    fresh = json.loads(out_meta.read_text("utf-8"))
    assert fresh["warnings"] == [original_warning], (
        "--from-metadata は元 metadata の post_match_trailing_dropped warning を "
        "新 metadata に preserve するはず (#805 段階1)"
    )


def test_run_split_from_metadata_empty_warnings_when_source_lacks(tmp_path):
    """#805 段階1 -- 元 metadata が warning を持たない (or 非 dict entry) なら
    新 metadata の warnings は [] (preserve は code を持つ dict のみ拾う)。
    """
    source = tmp_path / "input.mp4"
    source.write_bytes(b"")
    # _sample_metadata はデフォルトで warnings を含めない (= 欠落)。
    payload = _sample_metadata(str(source))
    assert "warnings" not in payload
    meta_path = _write_metadata(tmp_path, payload)
    config = SplitConfig(output_dir=tmp_path / "out", min_match_duration=60.0)

    with (
        patch(f"{MODULE}.probe_video", return_value=PROBE_RESULT),
        patch(
            f"{MODULE}.split_video",
            return_value=[
                tmp_path / "out" / "match_001.mp4",
                tmp_path / "out" / "match_002.mp4",
            ],
        ),
    ):
        run_split_from_metadata(meta_path, config, quiet=True)

    out_meta = tmp_path / "out" / "metadata.json"
    fresh = json.loads(out_meta.read_text("utf-8"))
    assert fresh["warnings"] == []
