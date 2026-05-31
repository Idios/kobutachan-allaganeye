"""VTuber scorebar 帯 anchor + 帯 crop の end-to-end 受け入れ (L3 Phase 1 D2).

slow_detect マーカー: 実 VTuber VOD 必須、CI default deselect。
VTuber サンプルは ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER (既定 E:/allaganeye-samples)。

本テストは Phase 1 の *wiring* (Stage 0 帯 anchor -> Stage 1 帯 crop brightness)
が実 VTuber VOD でクラッシュせず成立することを示す demonstrated-level 検証。
band anchor が localize できるか自体は Phase 2/3 の calibration 課題なので、
どの VOD でも localize しない場合は skip する (Phase 1 の wiring bug ではない)。
guard verify は大容量 VTuber VOD を FP で弾くため owner override 運用、PYTHONUTF8=1。
"""

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from allaganeye.video.capture_region import CaptureRegion

pytestmark = pytest.mark.slow_detect

_VTUBER_DIR = Path(
    os.environ.get("ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER", r"E:/allaganeye-samples")
)


def _vtuber_vods() -> list[Path]:
    if not _VTUBER_DIR.exists():
        return []
    return sorted(_VTUBER_DIR.glob("*.mp4"))


def _first_localizable_vod() -> "tuple[Path, CaptureRegion] | None":
    """band anchor が non-FULL_FRAME を返す最初の VOD と region を探す。

    見つからなければ None (全 VOD で localize 不成立 -> Phase 2/3 課題)。
    """
    from allaganeye.video import detector as det
    from allaganeye.video.probe import probe_video

    for vod in _vtuber_vods():
        try:
            meta = probe_video(vod)
            region = det._resolve_detect_region(vod, meta["duration"])
        except Exception:  # noqa: S112 - best-effort discovery; a bad VOD just skips
            continue
        if not region.is_full_frame():
            return vod, region
    return None


@pytest.mark.skipif(not _vtuber_vods(), reason="VTuber sample VOD not available")
def test_band_anchor_resolves_or_degrades_safely():
    """全 VTuber VOD で _resolve_detect_region がクラッシュせず CaptureRegion を返す。

    band anchor は (a) inset 帯を localize して non-FULL_FRAME を返すか、
    (b) localize 不成立で FULL_FRAME に安全縮退する。どちらでもクラッシュは不可。
    """
    from allaganeye.video import detector as det
    from allaganeye.video.capture_region import CaptureRegion
    from allaganeye.video.probe import probe_video

    vods = _vtuber_vods()
    for vod in vods:
        meta = probe_video(vod)
        region = det._resolve_detect_region(vod, meta["duration"])
        assert isinstance(region, CaptureRegion)
        # 帯 ROI なら source="band"、縮退なら FULL_FRAME (source="fallback")
        assert region.source in ("band", "fallback")


def test_band_crop_brightness_differs_from_full_frame_when_localized():
    """band anchor が localize できた VOD で、帯 crop 輝度と full-frame 輝度が
    実際に異なる ROI を測っていることを示す (帯限定が効いている証拠)。

    どの VOD でも localize しない場合は skip (Phase 2/3 calibration へ)。
    """
    found = _first_localizable_vod()
    if found is None:
        pytest.skip(
            "no VTuber VOD localized a scorebar band (Phase 2/3 calibration); "
            "Phase 1 wiring is exercised by test_band_anchor_resolves_or_degrades_safely"
        )
    vod, region = found
    from allaganeye.video import detector as det
    from allaganeye.video.capture_region import region_mean

    # probe one hi-res in-match frame at the VOD midpoint
    from allaganeye.video.probe import probe_video

    meta = probe_video(vod)
    raw = det._probe_frame_rgb_hires(vod, meta["duration"] / 2.0)
    assert raw is not None, "midpoint hi-res probe failed"

    import numpy as np

    frame = np.frombuffer(raw, dtype=np.uint8).reshape(
        det._SCOREBAR_V2_PROBE_HEIGHT, det._SCOREBAR_V2_PROBE_WIDTH, 3
    )
    # grayscale for brightness comparison (same as detector's gray decode intent)
    gray = frame.mean(axis=2)
    full = float(gray.mean())
    band = region_mean(gray, region)
    # band ROI is a thin top strip; on an in-match frame it should measure a
    # different mean than the whole frame (proves the crop targets a sub-region).
    assert band != full, (
        f"band crop ({band:.2f}) equals full-frame mean ({full:.2f}); "
        f"crop may not be targeting the scorebar band (region={region})"
    )
