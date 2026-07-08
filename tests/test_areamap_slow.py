"""Slow 実機テスト: resolve_match_regions の seed 局在性 + 負例 (Refs #481).

GT manifest: tests/baselines/v0.3.0/areamap-gt.json
assert 基準 (spec §6.3 縮小後):
  - visible=true  -> 検出 box の中心が GT bbox 内 (seed 局在性)
  - visible=false -> resolve_match_regions の結果に該当 match が含まれない

IoU >= 0.9 gate は課さない (§6.3 縮小後の合意)。

VTuber 系 case は ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER が存在しない場合は skip。
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
# Helpers (self-contained; tests/ から scripts/ は import しない)
# ---------------------------------------------------------------------------


def _expand_env(video_str: str) -> Path:
    """GT manifest の ${VAR} を展開して Path を返す。"""
    s = video_str.replace("${ALLAGANEYE_SAMPLE_VIDEO_DIR}", str(_OBS_DIR))
    s = s.replace("${ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER}", str(_VTUBER_DIR))
    return Path(s)


def _center_in_bbox(
    det: tuple[float, float, float, float],
    gt_bbox: tuple[float, float, float, float],
) -> bool:
    """検出 box の中心が GT bbox 内にあるか。

    det / gt_bbox は正規化 (x, y, w, h) で与える。
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
# Tests: OBS visible=true (obs-20260116-1)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _obs_dir_available(),
    reason="ALLAGANEYE_SAMPLE_VIDEO_DIR not set or directory not found",
)
@pytest.mark.parametrize("t", [300.0, 700.0])
def test_areamap_seed_locality_obs_20260116_1(t: float) -> None:
    """obs-20260116-1: 検出中心が GT bbox 内に収まること (seed 局在性)。

    GT: bbox [0.0, 0.0, 0.284, 0.403] (onsal_hakair, top-left)
    """
    gt = _load_gt()
    video_entry = next(v for v in gt["videos"] if v["id"] == "obs-20260116-1")
    gt_case = next(c for c in video_entry["cases"] if c["t"] == t)
    assert gt_case["visible"] is True

    video_path = _expand_env(video_entry["video"])
    assert video_path.exists(), f"動画が見つかりません: {video_path}"

    # 擬似 match: t を中心に ±90s の match を組む (edge_margin=60 適用後も余裕あり)
    matches = [(0, max(0.0, t - 90.0), t + 90.0)]
    results, _warns = resolve_match_regions(video_path, matches)

    assert results, (
        f"t={t}: resolve_match_regions が結果を返しませんでした "
        f"(visible=true なので少なくとも 1 件期待)"
    )
    det_region = results[0].region
    det_box = (det_region.x, det_region.y, det_region.w, det_region.h)
    gt_bbox = tuple(gt_case["bbox"])

    assert _center_in_bbox(det_box, gt_bbox), (  # type: ignore[arg-type]
        f"t={t}: 検出中心 ({det_box[0] + det_box[2] / 2:.3f}, {det_box[1] + det_box[3] / 2:.3f}) "
        f"が GT bbox {gt_bbox} の外。det={det_box}"
    )


# ---------------------------------------------------------------------------
# Tests: OBS visible=true (obs-20260118-2)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _obs_dir_available(),
    reason="ALLAGANEYE_SAMPLE_VIDEO_DIR not set or directory not found",
)
def test_areamap_seed_locality_obs_20260118_2() -> None:
    """obs-20260118-2: t=600 の検出中心が GT bbox 内に収まること。

    GT: bbox [0.0, 0.0, 0.191, 0.352] (seal_rock, top-left)
    """
    gt = _load_gt()
    video_entry = next(v for v in gt["videos"] if v["id"] == "obs-20260118-2")
    gt_case = video_entry["cases"][0]  # t=600
    assert gt_case["visible"] is True

    t = gt_case["t"]
    video_path = _expand_env(video_entry["video"])
    assert video_path.exists(), f"動画が見つかりません: {video_path}"

    matches = [(0, max(0.0, t - 90.0), t + 90.0)]
    results, _warns = resolve_match_regions(video_path, matches)

    assert results, (
        f"t={t}: resolve_match_regions が結果を返しませんでした "
        f"(visible=true なので少なくとも 1 件期待)"
    )
    det_region = results[0].region
    det_box = (det_region.x, det_region.y, det_region.w, det_region.h)
    gt_bbox = tuple(gt_case["bbox"])

    assert _center_in_bbox(det_box, gt_bbox), (  # type: ignore[arg-type]
        f"t={t}: 検出中心 ({det_box[0] + det_box[2] / 2:.3f}, {det_box[1] + det_box[3] / 2:.3f}) "
        f"が GT bbox {gt_bbox} の外。det={det_box}"
    )


# ---------------------------------------------------------------------------
# Tests: VTuber visible=true (masked-a29-m001)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _vtuber_dir_available(),
    reason="ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER not set or directory not found",
)
@pytest.mark.parametrize("t", [200.0, 400.0])
def test_areamap_seed_locality_masked_a29_m001(t: float) -> None:
    """masked-a29-m001: 検出中心が GT bbox 内に収まること。

    GT: bbox [0.0, 0.171, 0.151, 0.429] (left-side strip, ~±15px uncertainty)
    この動画は match_001.mp4 (clip) なので duration < 600s の場合は margin を調整する。
    """
    gt = _load_gt()
    video_entry = next(v for v in gt["videos"] if v["id"] == "masked-a29-m001")
    gt_case = next(c for c in video_entry["cases"] if c["t"] == t)
    assert gt_case["visible"] is True

    video_path = _expand_env(video_entry["video"])
    assert video_path.exists(), f"動画が見つかりません: {video_path}"

    # clip 動画は短い可能性: 90s 広窓で試みる。
    # resolve_match_regions の edge_margin=60 は matches span < min_usable_span
    # の場合自動縮退するので clip でもクラッシュしない。
    matches = [(0, max(0.0, t - 90.0), t + 90.0)]
    results, _warns = resolve_match_regions(video_path, matches)

    assert results, (
        f"t={t}: resolve_match_regions が結果を返しませんでした "
        f"(visible=true なので少なくとも 1 件期待)"
    )
    det_region = results[0].region
    det_box = (det_region.x, det_region.y, det_region.w, det_region.h)
    gt_bbox = tuple(gt_case["bbox"])

    assert _center_in_bbox(det_box, gt_bbox), (  # type: ignore[arg-type]
        f"t={t}: 検出中心 ({det_box[0] + det_box[2] / 2:.3f}, {det_box[1] + det_box[3] / 2:.3f}) "
        f"が GT bbox {gt_bbox} の外。det={det_box}"
    )


# ---------------------------------------------------------------------------
# Tests: visible=false (obs-20260209-mkv) — 提案なし (非検出)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _obs_dir_available(),
    reason="ALLAGANEYE_SAMPLE_VIDEO_DIR not set or directory not found",
)
@pytest.mark.parametrize("t", [1106.0, 2354.0])
def test_areamap_no_detection_when_invisible(t: float) -> None:
    """obs-20260209-mkv: visible=false の時刻では提案なし (結果に含まれない)。

    GT: visible=false (t=1106, 2354)。エリアマップが閉じているため未検出を期待する。
    visible=false case を assert するのは「提案なし」であること。
    detect の完全不在は保証しにくいため、実際に検出されても xfail ではなく
    skip ではなく WARN 付きで pass とする設計も考えられるが、
    spec §6.3 に従い「提案なし」を strict に assert する。
    """
    gt = _load_gt()
    video_entry = next(v for v in gt["videos"] if v["id"] == "obs-20260209-mkv")
    gt_case = next(c for c in video_entry["cases"] if c["t"] == t)
    assert gt_case["visible"] is False

    video_path = _expand_env(video_entry["video"])
    assert video_path.exists(), f"動画が見つかりません: {video_path}"

    matches = [(0, max(0.0, t - 90.0), t + 90.0)]
    results, _warns = resolve_match_regions(video_path, matches)

    # visible=false: resolve は当 match_index=0 を結果に含めてはならない
    match_indices = [r.match_index for r in results]
    assert 0 not in match_indices, (
        f"t={t}: visible=false だが match_index=0 が検出された。"
        f"検出 box: {[(r.region.x, r.region.y, r.region.w, r.region.h) for r in results if r.match_index == 0]}"
    )
