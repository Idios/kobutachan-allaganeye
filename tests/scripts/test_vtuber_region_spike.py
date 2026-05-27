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


def test_crop_region_mean_isolates_dark_inset():
    import numpy as np

    f = np.full((180, 320), 200, dtype=np.uint8)
    f[int(0.20 * 180) : int(0.70 * 180), int(0.30 * 320) : int(0.70 * 320)] = 5
    full = mod.crop_region_mean(f, (0.0, 0.0, 1.0, 1.0))
    inset = mod.crop_region_mean(f, (0.30, 0.20, 0.40, 0.50))
    assert inset < 20.0 and full > inset


def test_blackout_boundary_candidates_detects_transitions():
    # bright .. bright | dark dark | bright bright  -> drop@4, recover@8
    samples = [(0, 200), (2, 200), (4, 5), (6, 5), (8, 200), (10, 200)]
    recovers, drops = mod.blackout_boundary_candidates(samples, threshold=15.0)
    assert drops == [4] and recovers == [8]


def test_blackout_boundary_candidates_no_blackout_is_empty():
    samples = [(0, 200), (2, 180), (4, 190)]
    recovers, drops = mod.blackout_boundary_candidates(samples, threshold=15.0)
    assert recovers == [] and drops == []
