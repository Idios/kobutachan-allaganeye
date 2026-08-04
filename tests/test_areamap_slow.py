"""Slow real-device test: resolve_match_regions seed locality + negative (Refs #481).

GT manifest: tests/baselines/v0.3.0/areamap-gt.json

Contract (D3 2026-07-09 re-design, "seed is best-effort"):
  visible=true + bbox present (OBS 3 cases + masked 2 cases):
    - Per-case: if a proposal is returned, its center must lie inside the GT bbox
      (zero-misdirection assert).
    - Aggregate: OBS cases require >=2/3 proposals. Masked cases (when dir exists)
      require >=1/2 proposals.
  visible=false (t=2354 only):
    - resolve_match_regions must NOT include that match in results.
  visible=true + bbox null (t=1106):
    - Excluded from slow assertions (city map window; proposal-mode never samples
      out-of-match frames -- see GT note).

IoU >= 0.9 gate is NOT applied (spec sec.6.3 reduction agreed).

VTuber (masked) cases are skipped when ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER is absent.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from allaganeye.video.areamap import resolve_match_regions

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_WT = Path(__file__).parent.parent  # worktree root
_GT_PATH = _WT / "tests" / "baselines" / "v0.3.0" / "areamap-gt.json"

_OBS_DIR = Path(
    os.environ.get("ALLAGANEYE_SAMPLE_VIDEO_DIR") or r"E:/royalstraightflesh/videos"
)
_VTUBER_DIR = Path(
    os.environ.get("ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER") or r"E:/allaganeye-samples"
)

pytestmark = [pytest.mark.slow, pytest.mark.slow_detect]

# ---------------------------------------------------------------------------
# Helpers (self-contained; tests/ does not import from scripts/)
# ---------------------------------------------------------------------------


def _expand_env(video_str: str) -> Path:
    """Expand ${VAR} in GT manifest strings to Path."""
    s = video_str.replace("${ALLAGANEYE_SAMPLE_VIDEO_DIR}", str(_OBS_DIR))
    s = s.replace("${ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER}", str(_VTUBER_DIR))
    return Path(s)


def _center_in_bbox(
    det: tuple[float, float, float, float],
    gt_bbox: tuple[float, float, float, float],
) -> bool:
    """Return True if detected box center lies inside GT bbox.

    Both det and gt_bbox are normalized (x, y, w, h).
    """
    cx = det[0] + det[2] / 2.0
    cy = det[1] + det[3] / 2.0
    gx, gy, gw, gh = gt_bbox
    return gx <= cx <= gx + gw and gy <= cy <= gy + gh


def _load_gt() -> dict:
    return json.loads(_GT_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Skip guards
# ---------------------------------------------------------------------------


def _obs_dir_available() -> bool:
    return _OBS_DIR.is_dir()


def _vtuber_dir_available() -> bool:
    return _VTUBER_DIR.is_dir()


# ---------------------------------------------------------------------------
# Tests: OBS visible=true (obs-20260116-1) -- positive case, bbox present
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _obs_dir_available(),
    reason="ALLAGANEYE_SAMPLE_VIDEO_DIR not set or directory not found",
)
@pytest.mark.parametrize("t", [300.0, 700.0])
def test_areamap_seed_locality_obs_20260116_1(t: float) -> None:
    """obs-20260116-1: if detected, center must lie inside GT bbox (seed locality).

    GT: bbox [0.0, 0.0, 0.284, 0.403] (onsal_hakair, top-left).
    No proposal is also acceptable (best-effort contract).
    """
    gt = _load_gt()
    video_entry = next(v for v in gt["videos"] if v["id"] == "obs-20260116-1")
    gt_case = next(c for c in video_entry["cases"] if c["t"] == t)
    assert gt_case["visible"] is True

    video_path = _expand_env(video_entry["video"])
    assert video_path.exists(), f"video not found: {video_path}"

    # Pseudo-match: t +/- 90s window (edge_margin=60 leaves room inside)
    matches = [(0, max(0.0, t - 90.0), t + 90.0)]
    results, _warns = resolve_match_regions(video_path, matches)

    if not results:
        # No proposal is acceptable under best-effort contract
        return

    det_region = results[0].region
    det_box = (det_region.x, det_region.y, det_region.w, det_region.h)
    gt_bbox = tuple(gt_case["bbox"])

    assert _center_in_bbox(det_box, gt_bbox), (  # type: ignore[arg-type]
        f"t={t}: detected center ({det_box[0] + det_box[2] / 2:.3f},"
        f" {det_box[1] + det_box[3] / 2:.3f})"
        f" outside GT bbox {gt_bbox}. det={det_box}"
    )


# ---------------------------------------------------------------------------
# Tests: OBS visible=true (obs-20260118-2) -- positive case, bbox present
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _obs_dir_available(),
    reason="ALLAGANEYE_SAMPLE_VIDEO_DIR not set or directory not found",
)
def test_areamap_seed_locality_obs_20260118_2() -> None:
    """obs-20260118-2: t=600, if detected center must lie inside GT bbox.

    GT: bbox [0.0, 0.0, 0.191, 0.352] (seal_rock, top-left).
    No proposal is also acceptable (best-effort contract).
    """
    gt = _load_gt()
    video_entry = next(v for v in gt["videos"] if v["id"] == "obs-20260118-2")
    gt_case = video_entry["cases"][0]  # t=600
    assert gt_case["visible"] is True

    t = gt_case["t"]
    video_path = _expand_env(video_entry["video"])
    assert video_path.exists(), f"video not found: {video_path}"

    matches = [(0, max(0.0, t - 90.0), t + 90.0)]
    results, _warns = resolve_match_regions(video_path, matches)

    if not results:
        return

    det_region = results[0].region
    det_box = (det_region.x, det_region.y, det_region.w, det_region.h)
    gt_bbox = tuple(gt_case["bbox"])

    assert _center_in_bbox(det_box, gt_bbox), (  # type: ignore[arg-type]
        f"t={t}: detected center ({det_box[0] + det_box[2] / 2:.3f},"
        f" {det_box[1] + det_box[3] / 2:.3f})"
        f" outside GT bbox {gt_bbox}. det={det_box}"
    )


# ---------------------------------------------------------------------------
# Tests: VTuber visible=true (masked-a29-m001) -- positive cases, bbox present
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _vtuber_dir_available(),
    reason="ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER not set or directory not found",
)
@pytest.mark.parametrize("t", [200.0, 400.0])
def test_areamap_seed_locality_masked_a29_m001(t: float) -> None:
    """masked-a29-m001: if detected, center must lie inside GT bbox.

    GT: bbox [0.0, 0.171, 0.151, 0.429] (left-side strip, ~15px right-edge uncertainty).
    No proposal is also acceptable (best-effort contract).
    """
    gt = _load_gt()
    video_entry = next(v for v in gt["videos"] if v["id"] == "masked-a29-m001")
    gt_case = next(c for c in video_entry["cases"] if c["t"] == t)
    assert gt_case["visible"] is True

    video_path = _expand_env(video_entry["video"])
    assert video_path.exists(), f"video not found: {video_path}"

    # Clip video may be short: 90s window. resolve_match_regions degrades edge_margin
    # automatically when span < min_usable_span, so short clips won't crash.
    matches = [(0, max(0.0, t - 90.0), t + 90.0)]
    results, _warns = resolve_match_regions(video_path, matches)

    if not results:
        return

    det_region = results[0].region
    det_box = (det_region.x, det_region.y, det_region.w, det_region.h)
    gt_bbox = tuple(gt_case["bbox"])

    assert _center_in_bbox(det_box, gt_bbox), (  # type: ignore[arg-type]
        f"t={t}: detected center ({det_box[0] + det_box[2] / 2:.3f},"
        f" {det_box[1] + det_box[3] / 2:.3f})"
        f" outside GT bbox {gt_bbox}. det={det_box}"
    )


# ---------------------------------------------------------------------------
# Aggregate: at least 3/5 positive cases must return a proposal
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _obs_dir_available(),
    reason="ALLAGANEYE_SAMPLE_VIDEO_DIR not set or directory not found",
)
def test_areamap_positive_proposal_rate_obs() -> None:
    """At least 2 out of 3 OBS positive cases (bbox present) must return a proposal.

    Covers: obs-20260116-1 t=300, t=700 / obs-20260118-2 t=600.
    Requirement: >=2 of 3.
    """
    gt = _load_gt()

    obs_positive = [
        ("obs-20260116-1", 300.0),
        ("obs-20260116-1", 700.0),
        ("obs-20260118-2", 600.0),
    ]

    proposal_count = 0
    for video_id, t in obs_positive:
        video_entry = next(v for v in gt["videos"] if v["id"] == video_id)
        video_path = _expand_env(video_entry["video"])
        if not video_path.exists():
            continue
        matches = [(0, max(0.0, t - 90.0), t + 90.0)]
        results, _ = resolve_match_regions(video_path, matches)
        if results:
            proposal_count += 1

    assert proposal_count >= 2, (
        f"Only {proposal_count}/3 OBS positive cases returned a proposal "
        f"(need >=2 for best-effort contract)."
    )


@pytest.mark.skipif(
    not _vtuber_dir_available(),
    reason="ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER not set or directory not found",
)
def test_areamap_positive_proposal_rate_masked() -> None:
    """At least 1 out of 2 masked positive cases (bbox present) must return a proposal.

    Covers: masked-a29-m001 t=200, t=400.
    Requirement: >=1 of 2 (when VTuber dir exists).
    Skipped if ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER is absent.
    """
    gt = _load_gt()

    masked_positive = [
        ("masked-a29-m001", 200.0),
        ("masked-a29-m001", 400.0),
    ]

    proposal_count = 0
    for video_id, t in masked_positive:
        video_entry = next(v for v in gt["videos"] if v["id"] == video_id)
        video_path = _expand_env(video_entry["video"])
        if not video_path.exists():
            continue
        matches = [(0, max(0.0, t - 90.0), t + 90.0)]
        results, _ = resolve_match_regions(video_path, matches)
        if results:
            proposal_count += 1

    assert proposal_count >= 1, (
        f"Only {proposal_count}/2 masked positive cases returned a proposal "
        f"(need >=1 for best-effort contract)."
    )


# ---------------------------------------------------------------------------
# Tests: visible=false (obs-20260209-mkv t=2354 only) -- no proposal expected
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _obs_dir_available(),
    reason="ALLAGANEYE_SAMPLE_VIDEO_DIR not set or directory not found",
)
def test_areamap_no_detection_when_invisible_t2354() -> None:
    """obs-20260209-mkv t=2354: visible=false -> no proposal (READY CHECK, true negative).

    t=1106 is excluded from slow assertions (city map window, visible=true but bbox null;
    proposal-mode never samples out-of-match frames -- see GT note).
    """
    gt = _load_gt()
    video_entry = next(v for v in gt["videos"] if v["id"] == "obs-20260209-mkv")
    gt_case = next(c for c in video_entry["cases"] if c["t"] == 2354.0)
    assert gt_case["visible"] is False

    t = 2354.0
    video_path = _expand_env(video_entry["video"])
    assert video_path.exists(), f"video not found: {video_path}"

    matches = [(0, max(0.0, t - 90.0), t + 90.0)]
    results, _warns = resolve_match_regions(video_path, matches)

    match_indices = [r.match_index for r in results]
    assert 0 not in match_indices, (
        f"t={t}: visible=false but match_index=0 was detected. "
        f"det box: {[(r.region.x, r.region.y, r.region.w, r.region.h) for r in results if r.match_index == 0]}"
    )
