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
  - Root present but an individual GT video absent (or unusable: a directory,
    a zero-byte placeholder) -> that case is skipped (per-case) and the
    aggregate rate gate scales its requirement to the cases that are actually
    available.  Skips alone would let a shrinking GT set hide in green, so
    test_areamap_gt_video_availability pins both the missing set
    (_KNOWN_MISSING_GT_IDS) and the manifest shape (_EXPECTED_GT_CASES).

VTuber (masked) cases are skipped when ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER is absent.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

import pytest

from allaganeye.video.areamap import _probe_frame_rgb_hires, resolve_match_regions

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

# GT manifest の形そのものの pin (#992 / Codex adversarial-review round 1 finding 2)。
# id -> その entry が持つ case の t (sorted)。欠落ファイルの監査は manifest を
# 正として行うため、**manifest 自体が縮んだら監査対象ごと消える**。entry や case
# を消しても現状は `next(...)` の StopIteration (メッセージ空) が偶発的に拾うだけで、
# root 不在の環境では何も拾わない。ここで期待形を独立に pin して、GT を減らす
# 変更が必ず「pin を書き換える」という明示的な判断を通るようにする。
#
# **これは manifest の「形」の pin であって test 被覆の保証ではない** (Codex round 2
# finding 1)。pin された case が存在し decode できても、その case に assert する
# test があるとは限らない (例: obs-20260209-mkv t=1106 は bbox null で assert する
# 対象が無く、module docstring のとおり意図的に slow assertion から外している)。
# 「pin された全 case に assert がある」ことの強制は本 pin の役目ではなく、
# #997 で追跡する。
_EXPECTED_GT_CASES: dict[str, tuple[float, ...]] = {
    "obs-20260116-1": (300.0, 700.0),
    "obs-20260118-2": (600.0,),
    "masked-a29-m001": (200.0, 400.0),
    "obs-20260209-mkv": (1106.0, 2354.0),
}

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


def _gt_video_unusable_reason(video_path: Path) -> str | None:
    """None when the GT video is usable, otherwise a short reason.

    `Path.exists()` alone is not a sufficient availability predicate (#992,
    Codex adversarial-review finding 1).  A directory, a placeholder, or a
    zero-byte file left by an interrupted copy all pass `exists()`; the per-case
    test would then probe it, get no frames back, and **pass** under the
    best-effort "no proposal is acceptable" contract.  Measured before the fix:
    a 0-byte `20260116_1.mp4` turned the 2 seed-locality cases and the
    availability guard green (`3 passed`) with that GT case never verified.

    NOT covered: a non-empty but truncated / corrupt file.  Detecting that needs
    the SHA-256 ledger (tests/baselines/source-videos.sha256.json), i.e. a
    multi-GB read per video per run -- too expensive for a per-run predicate.
    Use the checksum procedure in docs/testing-guide.md when corruption is
    suspected.
    """
    try:
        if not video_path.exists():
            return "not found"
        if not video_path.is_file():
            return "not a regular file"
        size = video_path.stat().st_size
    except OSError as exc:  # permission / IO error -> treat as unusable
        return f"stat failed: {exc}"
    if size == 0:
        return "zero-byte file"
    return None


def _gt_video_available(video_entry: dict) -> bool:
    return _gt_video_unusable_reason(_expand_env(video_entry["video"])) is None


def _undecodable_gt_case_times(video_entry: dict) -> list[float]:
    """Pinned case timestamps at which no frame decodes (#992, Codex round 2).

    A stat-only predicate cannot separate a real recording from a non-empty but
    truncated / garbage file.  Measured: a 5 MB random-bytes `20260116_1.mp4`
    left both seed-locality cases *and* the availability guard green
    (`3 passed`) -- the probe returns None and the per-case contract accepts
    "no proposal", so the GT case was never actually verified.

    Probing one frame per pinned timestamp with the **same probe the production
    path uses** (`_probe_frame_rgb_hires`, i.e. `resolve_match_regions`'s default)
    makes "decodable" mean here exactly what it means there.  Measured cost on
    the real GT set: ~10s for all 7 pinned cases; corrupt input is rejected in
    ~0.14s.  Only the guard pays this -- the per-case skip predicate stays stat
    -only, and a corrupt video therefore surfaces as a red guard rather than a
    green run.
    """
    video_path = _expand_env(video_entry["video"])
    return [
        t
        for t in _EXPECTED_GT_CASES.get(video_entry["id"], ())
        if _probe_frame_rgb_hires(video_path, t) is None
    ]


def _require_gt_video(video_entry: dict) -> Path:
    """Resolve a GT entry's video path, skipping the test when it is absent (#992).

    The dir-level skipif guards only prove the sample root exists; an individual
    video can still be missing (deleted, not yet restored from backup) or
    unusable (see `_gt_video_unusable_reason`).  That is an environment gap, not
    a detector regression, so it must skip rather than fail.
    test_areamap_gt_video_availability keeps the gap visible.
    """
    video_path = _expand_env(video_entry["video"])
    reason = _gt_video_unusable_reason(video_path)
    if reason is not None:
        pytest.skip(
            f"GT video unusable ({reason}, id={video_entry['id']}): {video_path}."
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
        video_entry = _gt_entry(gt, video_id)
        if not _gt_video_available(video_entry):
            missing_ids.append(video_id)
            continue
        available.append((_expand_env(video_entry["video"]), t))

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
        video_entry = _gt_entry(gt, video_id)
        if not _gt_video_available(video_entry):
            missing_ids.append(video_id)
            continue
        available.append((_expand_env(video_entry["video"]), t))

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

    欠落監査の前に GT manifest の形そのものを _EXPECTED_GT_CASES と突合する。
    欠落は manifest を正として見るので、manifest が縮めば監査対象ごと消える。

    最後に pin 済み case の t で 1 フレーム decode できることを確かめる。stat だけ
    では「非ゼロだが中身が壊れている」を見抜けず、per-case は「提案なしも可」契約
    なので全緑になってしまう (実測済み)。
    """
    gt = _load_gt()
    manifest_ids = [v["id"] for v in gt["videos"]]
    all_ids = set(manifest_ids)
    pinned = set(_KNOWN_MISSING_GT_IDS)

    # --- Manifest 整合性: ファイルシステムに依存しないので root の有無に関わらず見る ---
    duplicates = sorted({vid for vid in manifest_ids if manifest_ids.count(vid) > 1})
    assert not duplicates, (
        f"GT manifest has duplicate ids: {duplicates}."
        " _gt_entry() silently resolves to the first match, so a duplicate makes"
        " the per-case tests and this guard disagree about which entry is meant."
    )

    assert all_ids == set(_EXPECTED_GT_CASES), (
        "GT manifest id set drifted from _EXPECTED_GT_CASES.\n"
        f"added (not pinned): {sorted(all_ids - set(_EXPECTED_GT_CASES))}\n"
        f"removed (pinned but gone): {sorted(set(_EXPECTED_GT_CASES) - all_ids)}\n"
        "Shrinking the manifest removes GT coverage from the audit itself, so it"
        " must be an explicit decision: update _EXPECTED_GT_CASES in the same"
        " change and say why in the PR body.\n"
        "NOTE: updating this pin records the manifest's shape -- it does NOT mean"
        " a test asserts on the case.  Check that yourself when adding one."
    )

    actual_cases = {
        v["id"]: tuple(sorted(float(c["t"]) for c in v["cases"])) for v in gt["videos"]
    }
    expected_cases = {vid: tuple(sorted(ts)) for vid, ts in _EXPECTED_GT_CASES.items()}
    assert actual_cases == expected_cases, (
        "GT manifest case timestamps drifted from _EXPECTED_GT_CASES.\n"
        f"actual:   {actual_cases}\n"
        f"expected: {expected_cases}\n"
        "A dropped case is coverage lost -- update the pin deliberately."
    )

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
    unusable = {
        v["id"]: reason
        for v in auditable
        if (reason := _gt_video_unusable_reason(_expand_env(v["video"]))) is not None
    }
    missing = set(unusable)
    expected_missing = pinned & auditable_ids

    newly_missing = sorted(missing - expected_missing)
    restored = {
        vid: _KNOWN_MISSING_GT_IDS[vid] for vid in sorted(expected_missing - missing)
    }
    detail = {
        v["id"]: f"{unusable[v['id']]}: {_expand_env(v['video'])}"
        for v in auditable
        if v["id"] in missing
    }

    assert missing == expected_missing, (
        "areamap GT video availability drifted from _KNOWN_MISSING_GT_IDS.\n"
        f"newly missing (restore, or record in _KNOWN_MISSING_GT_IDS): {newly_missing}\n"
        f"restored but still pinned (drop from _KNOWN_MISSING_GT_IDS): {restored}\n"
        f"audited ids (root present): {sorted(auditable_ids)}\n"
        f"unusable: {detail}\n"
        "Restore procedure + ledger: docs/testing-guide.md"
        " / tests/baselines/source-videos.sha256.json"
    )

    # --- Decodability: stat では「非ゼロだが中身が壊れている」を見抜けない ---
    # ここまでの assert を通った = 存在して非ゼロ、という状態。pin 済み case の t で
    # 実際に 1 フレーム decode できることまで確かめて初めて「その GT は検証しうる」
    # と言える (実測: 5MB のランダムバイト列は stat を通り抜けて全緑になった)。
    # pin 済み = 検証しない判断をした id は probe しない。
    undecodable = {
        v["id"]: failed
        for v in auditable
        if v["id"] not in missing
        and v["id"] not in pinned
        and (failed := _undecodable_gt_case_times(v))
    }
    assert not undecodable, (
        "GT video present but no frame decodes at the pinned case timestamps.\n"
        f"undecodable (id -> t): {undecodable}\n"
        "The file is truncated, corrupt, or not a video.  A stat-only check"
        " cannot see this, and the per-case tests would pass anyway because"
        ' "no proposal" is acceptable under the best-effort contract -- so this'
        " GT case would be silently unverified.\n"
        "Verify the file against tests/baselines/source-videos.sha256.json and"
        " restore it (docs/testing-guide.md)."
    )
