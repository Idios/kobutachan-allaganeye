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

Missing-video policy (#992):
  - Sample root absent -> the tests under that root skip (skipif guards).  The
    availability guard skips only when NO root is present, so a machine with
    just one root still audits that root.
  - Root present but an individual GT video absent -> that case is skipped
    (per-case) and the aggregate rate gate scales its requirement to the cases
    that are actually available.  Skips alone would let a shrinking GT set hide
    in green, so test_areamap_gt_video_availability pins the missing set.

VTuber (masked) cases are skipped when ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER is absent.
"""

from __future__ import annotations

import json
import math
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

# GT video ids that are knowingly absent from the local sample set, mapped to
# the reason they are not being restored (#992).  Keep EMPTY unless Idios has
# decided against restoring a video: every id parked here is GT coverage that is
# no longer verified, so the reason string is the required 1-line record of that
# decision.  test_areamap_gt_video_availability enforces both directions --
# adding an id silences the drift guard for that video, and leaving a restored
# id here turns the guard red as a stale pin.  Restore procedure:
# docs/testing-guide.md "サンプル動画/GT データの保全"
# (ledger: tests/baselines/source-videos.sha256.json).
_KNOWN_MISSING_GT_IDS: dict[str, str] = {}

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


def _gt_entry(gt: dict, video_id: str) -> dict:
    return next(v for v in gt["videos"] if v["id"] == video_id)


def _scaled_requirement(required: int, total: int, available: int) -> int:
    """Scale a `required`-of-`total` rate contract to the available subset (#992).

    Keeps the contract's ratio: 2-of-3 with 1 case available still demands 1.
    Never returns 0 for a non-empty subset, so a partially available GT set
    still gates something instead of passing vacuously.
    """
    return math.ceil(required * available / total)


# ---------------------------------------------------------------------------
# Skip guards
# ---------------------------------------------------------------------------


def _obs_dir_available() -> bool:
    return _OBS_DIR.is_dir()


def _vtuber_dir_available() -> bool:
    return _VTUBER_DIR.is_dir()


def _gt_root_available(video_entry: dict) -> bool:
    """Whether the sample root a GT entry lives under is present on this machine.

    A GT entry whose root is absent cannot be audited for file-level availability
    (everything under it looks "missing"), so it is excluded from the drift guard
    rather than reported.  An entry using an unrecognised placeholder is a
    manifest change the guard does not understand -- raise instead of silently
    dropping it from the audited set.
    """
    video_str = video_entry["video"]
    if "${ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER}" in video_str:
        return _vtuber_dir_available()
    if "${ALLAGANEYE_SAMPLE_VIDEO_DIR}" in video_str:
        return _obs_dir_available()
    raise AssertionError(
        f"GT entry {video_entry['id']!r} uses an unknown sample root: {video_str!r}."
        " Teach _gt_root_available about it, otherwise the availability drift"
        " guard would silently stop auditing this entry."
    )


def _require_gt_video(video_entry: dict) -> Path:
    """Resolve a GT entry's video path, skipping the test when it is absent (#992).

    The dir-level skipif guards only prove the sample root exists; an individual
    video can still be missing (deleted, not yet restored from backup).  That is
    an environment gap, not a detector regression, so it must skip rather than
    fail.  test_areamap_gt_video_availability keeps the gap visible.
    """
    video_path = _expand_env(video_entry["video"])
    if not video_path.exists():
        pytest.skip(
            f"GT video missing (id={video_entry['id']}): {video_path}."
            " Restore it (see docs/testing-guide.md)"
            " or record the id + reason in _KNOWN_MISSING_GT_IDS."
        )
    return video_path


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
    video_entry = _gt_entry(gt, "obs-20260116-1")
    gt_case = next(c for c in video_entry["cases"] if c["t"] == t)
    assert gt_case["visible"] is True

    video_path = _require_gt_video(video_entry)

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
    video_entry = _gt_entry(gt, "obs-20260118-2")
    gt_case = video_entry["cases"][0]  # t=600
    assert gt_case["visible"] is True

    t = gt_case["t"]
    video_path = _require_gt_video(video_entry)

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
    video_entry = _gt_entry(gt, "masked-a29-m001")
    gt_case = next(c for c in video_entry["cases"] if c["t"] == t)
    assert gt_case["visible"] is True

    video_path = _require_gt_video(video_entry)

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
    Requirement: >=2 of 3, scaled to the available cases when a GT video is
    missing (#992) -- with 1 of 3 available the requirement is still >=1, so a
    partial GT set narrows coverage without disabling the gate.
    """
    gt = _load_gt()

    obs_positive = [
        ("obs-20260116-1", 300.0),
        ("obs-20260116-1", 700.0),
        ("obs-20260118-2", 600.0),
    ]

    available: list[tuple[Path, float]] = []
    missing_ids: list[str] = []
    for video_id, t in obs_positive:
        video_path = _expand_env(_gt_entry(gt, video_id)["video"])
        if not video_path.exists():
            missing_ids.append(video_id)
            continue
        available.append((video_path, t))

    if not available:
        pytest.skip(
            f"all OBS positive GT videos missing: {sorted(set(missing_ids))}"
            " (see docs/testing-guide.md)"
        )

    required = _scaled_requirement(2, len(obs_positive), len(available))

    proposal_count = 0
    for video_path, t in available:
        matches = [(0, max(0.0, t - 90.0), t + 90.0)]
        results, _ = resolve_match_regions(video_path, matches)
        if results:
            proposal_count += 1

    assert proposal_count >= required, (
        f"Only {proposal_count}/{len(available)} available OBS positive cases "
        f"returned a proposal (need >={required}; base contract >=2 of "
        f"{len(obs_positive)}; missing GT videos: {sorted(set(missing_ids))})."
    )


@pytest.mark.skipif(
    not _vtuber_dir_available(),
    reason="ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER not set or directory not found",
)
def test_areamap_positive_proposal_rate_masked() -> None:
    """At least 1 out of 2 masked positive cases (bbox present) must return a proposal.

    Covers: masked-a29-m001 t=200, t=400.
    Requirement: >=1 of 2 (when VTuber dir exists), scaled to the available
    cases when a GT video is missing (#992).
    Skipped if ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER is absent.
    """
    gt = _load_gt()

    masked_positive = [
        ("masked-a29-m001", 200.0),
        ("masked-a29-m001", 400.0),
    ]

    available: list[tuple[Path, float]] = []
    missing_ids: list[str] = []
    for video_id, t in masked_positive:
        video_path = _expand_env(_gt_entry(gt, video_id)["video"])
        if not video_path.exists():
            missing_ids.append(video_id)
            continue
        available.append((video_path, t))

    if not available:
        pytest.skip(
            f"all masked positive GT videos missing: {sorted(set(missing_ids))}"
            " (see docs/testing-guide.md)"
        )

    required = _scaled_requirement(1, len(masked_positive), len(available))

    proposal_count = 0
    for video_path, t in available:
        matches = [(0, max(0.0, t - 90.0), t + 90.0)]
        results, _ = resolve_match_regions(video_path, matches)
        if results:
            proposal_count += 1

    assert proposal_count >= required, (
        f"Only {proposal_count}/{len(available)} available masked positive cases "
        f"returned a proposal (need >={required}; base contract >=1 of "
        f"{len(masked_positive)}; missing GT videos: {sorted(set(missing_ids))})."
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
    video_entry = _gt_entry(gt, "obs-20260209-mkv")
    gt_case = next(c for c in video_entry["cases"] if c["t"] == 2354.0)
    assert gt_case["visible"] is False

    t = 2354.0
    video_path = _require_gt_video(video_entry)

    matches = [(0, max(0.0, t - 90.0), t + 90.0)]
    results, _warns = resolve_match_regions(video_path, matches)

    match_indices = [r.match_index for r in results]
    assert 0 not in match_indices, (
        f"t={t}: visible=false but match_index=0 was detected. "
        f"det box: {[(r.region.x, r.region.y, r.region.w, r.region.h) for r in results if r.match_index == 0]}"
    )


# ---------------------------------------------------------------------------
# Drift guard: GT video availability (#992)
# ---------------------------------------------------------------------------


def test_areamap_gt_video_availability() -> None:
    """GT 動画の欠落集合が _KNOWN_MISSING_GT_IDS と完全一致する (#992).

    欠落した GT 動画は per-case では skip される。それだけだと「GT があるのに
    検証していない」状態が緑に埋もれるため、本テストが欠落集合を pin と
    双方向に突合し、以下の両方を赤にする:

    - 新たな欠落 (pin されていない GT 動画が消えた) -> 復元するか理由付きで pin
    - pin の陳腐化 (復元済み / 綴り間違い の id が pin に残っている) -> pin を外す

    片方向 (新規欠落のみ) だと pin が永久に残り、GT を復元しても被覆が
    戻ったことを誰も検知できなくなる。

    監査はサンプルルート単位で行う。root ごと無い環境ではその root の entry を
    監査対象から外すだけで、**他 root の監査は続ける** -- 「両 root 揃った環境
    でしか動かない guard」にすると、片方しか持たない環境で guard が丸ごと
    no-op になり、まさに埋もれさせたかった欠落を見逃す。
    """
    gt = _load_gt()
    all_ids = {v["id"] for v in gt["videos"]}
    pinned = set(_KNOWN_MISSING_GT_IDS)

    # Manifest 整合性はファイルシステムに依存しないので root の有無に関わらず見る。
    unknown_pins = sorted(pinned - all_ids)
    assert not unknown_pins, (
        f"_KNOWN_MISSING_GT_IDS pins ids that are not in the GT manifest:"
        f" {unknown_pins} (known ids: {sorted(all_ids)})."
        " A typo here would silence the drift guard for a video that is still"
        " expected to exist -- fix the id or drop the pin."
    )

    auditable = [v for v in gt["videos"] if _gt_root_available(v)]
    if not auditable:
        pytest.skip(
            "no sample root available"
            f" (ALLAGANEYE_SAMPLE_VIDEO_DIR={_OBS_DIR},"
            f" ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER={_VTUBER_DIR})"
        )

    auditable_ids = {v["id"] for v in auditable}
    missing = {v["id"] for v in auditable if not _expand_env(v["video"]).exists()}
    expected_missing = pinned & auditable_ids

    newly_missing = sorted(missing - expected_missing)
    restored = {
        vid: _KNOWN_MISSING_GT_IDS[vid] for vid in sorted(expected_missing - missing)
    }
    paths = {
        v["id"]: str(_expand_env(v["video"])) for v in auditable if v["id"] in missing
    }

    assert missing == expected_missing, (
        "areamap GT video availability drifted from _KNOWN_MISSING_GT_IDS.\n"
        f"newly missing (restore, or record in _KNOWN_MISSING_GT_IDS): {newly_missing}\n"
        f"restored but still pinned (drop from _KNOWN_MISSING_GT_IDS): {restored}\n"
        f"audited ids (root present): {sorted(auditable_ids)}\n"
        f"missing paths: {paths}\n"
        "Restore procedure + ledger: docs/testing-guide.md"
        " / tests/baselines/source-videos.sha256.json"
    )
