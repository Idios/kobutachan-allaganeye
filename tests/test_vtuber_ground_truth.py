"""VTuber ground truth +-10s acceptance gate (P2-24, #809 prerequisite; #844 W5).

slow + slow_detect: real VTuber VOD required, CI deselect.
VOD dir: ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER (default E:/allaganeye-samples),
reusing the env var established by tests/test_vtuber_region_e2e.py.

Marked xfail(strict=False) until #809 wires production VTuber detection: the
gate documents the +-10s target and becomes a hard pass-gate (drop xfail) once
calibration lands. guard verify FP-rejects large VODs -> owner override, PYTHONUTF8=1.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.slow_detect]

_REPO_ROOT = Path(__file__).resolve().parent.parent
_GT_PATH = (
    _REPO_ROOT / "tests" / "baselines" / "v0.3.0" / "vtuber-primary-ground-truth.json"
)
_VTUBER_DIR = Path(
    os.environ.get("ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER") or r"E:/allaganeye-samples"
)


def _ground_truth() -> dict:
    return json.loads(_GT_PATH.read_text(encoding="utf-8"))


def _resolve_vod() -> Path | None:
    """Find the GT source VOD under the VTuber dir (top-level or one subdir)."""
    if not _VTUBER_DIR.exists():
        return None
    name = _ground_truth()["source_file"]
    direct = _VTUBER_DIR / name
    if direct.is_file():
        return direct
    for match in _VTUBER_DIR.glob(f"**/{name}"):
        if match.is_file():
            return match
    return None


@pytest.mark.xfail(
    reason="#809 VTuber detection calibration pending; drop this xfail once #809 merges",
    # strict=True: once detection passes (post-#809), XPASS fails the suite and
    # forces removing this marker -- the gate cannot silently stay non-gating.
    strict=True,
)
def test_vtuber_ground_truth_within_tolerance(tmp_output_dir):
    """Each GT FL match has a detected match with start+end within +-tolerance_sec."""
    vod = _resolve_vod()
    if vod is None:
        pytest.skip("VTuber GT VOD not found under ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER")
    gt = _ground_truth()
    tol = float(gt["tolerance_sec"])

    cmd = [
        sys.executable,
        "-m",
        "allaganeye",
        "detect",
        str(vod),
        "--vtuber",
        "-o",
        str(tmp_output_dir),
        "--no-cache",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    assert result.returncode == 0, f"detect failed: {result.stderr}"
    detected = json.loads(
        (tmp_output_dir / "metadata.json").read_text(encoding="utf-8")
    )["matches"]

    misses: list[str] = []
    for g in gt["matches"]:
        near = [
            d
            for d in detected
            if abs(float(d["start_time"]) - float(g["start_time"])) <= tol
            and abs(float(d["end_time"]) - float(g["end_time"])) <= tol
        ]
        if not near:
            misses.append(
                f"GT match {g['index']} ({g['start_time']}-{g['end_time']}s) "
                f"has no detected match within +-{tol:.0f}s"
            )
    assert not misses, "VTuber GT +-tol mismatch:\n" + "\n".join(misses)
