"""Tests for scripts/compare-baseline.py (v0.3.0 L3 baseline comparison)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

# Import the module under test (scripts/compare-baseline.py -- hyphenated name
# requires importlib.util.spec_from_file_location)
SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
_spec = importlib.util.spec_from_file_location(
    "compare_baseline", SCRIPTS_DIR / "compare-baseline.py"
)
assert _spec is not None and _spec.loader is not None
compare_baseline = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(compare_baseline)


def test_normalize_projects_to_matches_and_gaps_only() -> None:
    """normalize_metadata must project to spec section 8.2 baseline surface (matches + gaps).

    Excludes `detected_at` and all other non-baseline top-level fields
    (e.g., `source`, `detection_params`, `system_info`).
    """
    raw = {
        "source": "video.mp4",
        "source_duration": 7303.0,
        "detected_at": "2026-05-18T12:34:56Z",
        "detection_params": {"sample_interval": 2.0},
        "matches": [{"index": 1, "start_time": 0, "end_time": 100}],
        "gaps": [{"start_time": 200, "end_time": 300}],
    }
    result = compare_baseline.normalize_metadata(raw)
    assert set(result.keys()) == {"matches", "gaps"}
    assert result["matches"] == raw["matches"]
    assert result["gaps"] == raw["gaps"]


def test_main_returns_0_on_identical_metadata(tmp_path: Path) -> None:
    """main() must return 0 when baseline and current are identical (modulo detected_at)."""
    baseline = {
        "source": "video.mp4",
        "detected_at": "2026-01-01T00:00:00Z",
        "matches": [{"index": 1, "start_time": 0, "end_time": 100}],
    }
    current = {
        "source": "video.mp4",
        "detected_at": "2026-05-18T12:34:56Z",
        "matches": [{"index": 1, "start_time": 0, "end_time": 100}],
    }

    baseline_path = tmp_path / "baseline.json"
    current_path = tmp_path / "current.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    current_path.write_text(json.dumps(current), encoding="utf-8")

    exit_code = compare_baseline.main([str(baseline_path), str(current_path)])
    assert exit_code == 0


def test_main_returns_1_on_match_diff(tmp_path: Path) -> None:
    """main() must return 1 when match list differs."""
    baseline = {
        "source": "video.mp4",
        "matches": [{"index": 1, "start_time": 0, "end_time": 100}],
    }
    current = {
        "source": "video.mp4",
        "matches": [{"index": 1, "start_time": 5, "end_time": 100}],
    }

    baseline_path = tmp_path / "baseline.json"
    current_path = tmp_path / "current.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    current_path.write_text(json.dumps(current), encoding="utf-8")

    exit_code = compare_baseline.main([str(baseline_path), str(current_path)])
    assert exit_code == 1


def test_main_returns_2_on_missing_file(tmp_path: Path) -> None:
    """main() must return 2 when baseline file doesn't exist."""
    nonexistent = tmp_path / "nope.json"
    current = tmp_path / "current.json"
    current.write_text("{}", encoding="utf-8")

    exit_code = compare_baseline.main([str(nonexistent), str(current)])
    assert exit_code == 2


def test_main_returns_2_on_invalid_json(tmp_path: Path) -> None:
    """main() must return 2 when JSON parse fails."""
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    good = tmp_path / "good.json"
    good.write_text("{}", encoding="utf-8")

    exit_code = compare_baseline.main([str(bad), str(good)])
    assert exit_code == 2


def test_main_returns_0_when_only_non_baseline_fields_differ(tmp_path: Path) -> None:
    """main() must return 0 when only non-baseline top-level fields differ.

    Spec section 8.2 defines baseline as `matches` + `gaps`. Other top-level fields
    (e.g., `source`, `detection_params`, `system_info`) may evolve independently
    and must NOT trigger a regression alarm.
    """
    baseline = {
        "source": "video.mp4",
        "source_duration": 7303.0,
        "detection_params": {"sample_interval": 2.0},
        "matches": [{"index": 1, "start_time": 0, "end_time": 100}],
        "gaps": [],
    }
    current = {
        "source": "video-renamed.mp4",  # source changed
        "source_duration": 7303.5,  # source_duration changed
        "detection_params": {"sample_interval": 1.5},  # detection_params changed
        "system_info": {"gpu_vendor_used": "nvidia"},  # new field added
        "matches": [{"index": 1, "start_time": 0, "end_time": 100}],  # SAME
        "gaps": [],  # SAME
    }

    baseline_path = tmp_path / "baseline.json"
    current_path = tmp_path / "current.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    current_path.write_text(json.dumps(current), encoding="utf-8")

    exit_code = compare_baseline.main([str(baseline_path), str(current_path)])
    assert exit_code == 0
