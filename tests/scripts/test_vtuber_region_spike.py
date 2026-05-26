import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "vtuber_region_spike",
    Path(__file__).resolve().parents[2] / "scripts" / "vtuber_region_spike.py",
)
assert _SPEC is not None and _SPEC.loader is not None
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)  # type: ignore[union-attr]


def test_match_within_tolerance_all_hit():
    gt = [1433, 2624, 4253, 5684, 6609]
    detected = [1435, 2620, 4258, 5680, 6612]
    matched, misses = mod.match_within_tolerance(detected, gt, tol=10)
    assert matched == 5 and misses == []


def test_match_within_tolerance_reports_miss():
    gt = [1433, 2624]
    detected = [1435]
    matched, misses = mod.match_within_tolerance(detected, gt, tol=10)
    assert matched == 1 and misses == [2624]
