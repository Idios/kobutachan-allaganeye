import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "vtuber_region_experiment",
    Path(__file__).resolve().parents[2] / "scripts" / "vtuber_region_experiment.py",
)
assert _SPEC is not None and _SPEC.loader is not None
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)  # type: ignore[union-attr]


def test_format_comparison_table_marks_best_iou():
    rows = [
        {"candidate": "S1", "mean_iou": 0.81, "mean_top_err_px": 30.0, "cost_s": 5.0},
        {"candidate": "S2", "mean_iou": 0.94, "mean_top_err_px": 8.0, "cost_s": 9.0},
    ]
    out = mod.format_comparison_table(rows)
    assert "S2" in out and "0.94" in out
    assert mod.pick_winner(rows)["candidate"] == "S2"


def test_pick_winner_requires_obs_passing():
    rows = [
        {
            "candidate": "S1",
            "mean_iou": 0.99,
            "mean_top_err_px": 2.0,
            "obs_full_frame": False,
        },
        {
            "candidate": "S2",
            "mean_iou": 0.90,
            "mean_top_err_px": 9.0,
            "obs_full_frame": True,
        },
    ]
    assert mod.pick_winner(rows)["candidate"] == "S2"


def test_region_metrics_identical_is_perfect():
    from allaganeye.video.capture_region import CaptureRegion

    r = CaptureRegion(0.13, 0.09, 0.87, 0.87)
    m = mod.region_metrics(r, r, 1080)
    assert m["iou"] == 1.0 and m["top_err_px"] == 0.0


def test_region_metrics_none_detection_is_worst_case():
    from allaganeye.video.capture_region import CaptureRegion

    truth = CaptureRegion(0.13, 0.09, 0.87, 0.87)
    m = mod.region_metrics(None, truth, 1080)
    assert m["iou"] == 0.0 and m["top_err_px"] == 1080.0
