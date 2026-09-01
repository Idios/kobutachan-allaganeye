"""Phase 2 受け入れ (slow / sample-gated): VTuber 過分割解消 + OBS v2/localize parity.

実機データ依存 (Idios verify、PYTHONUTF8=1)。CI では sample 未設定で skip。
parity は production に入れない harness 計測 (spec section 8.1 P2-b)。
"""

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow


def _vtuber_sample() -> Path | None:
    base = (
        os.environ.get("ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER") or r"E:/allaganeye-samples"
    )
    cands = list(Path(base).glob("*オンサル*")) if Path(base).exists() else []
    return cands[0] if cands else None


@pytest.mark.slow_detect
@pytest.mark.skipif(_vtuber_sample() is None, reason="VTuber sample not available")
def test_vtuber_split_removes_in_match_overspilt():
    from allaganeye.video.probe import probe_video
    from allaganeye.video import detector as det

    video = _vtuber_sample()
    assert video is not None  # guaranteed by skipif; narrows Path | None -> Path
    meta = probe_video(video)
    res = (meta["width"], meta["height"])
    # vtuber=True path: classifier removes in-match band-crop blackouts.
    matches_vtuber = det.detect_match_boundaries(
        video,
        duration_hint=meta["duration"],
        src_resolution=res,
        vtuber=True,
        # #864: this call does not raise today because vtuber=True branches into
        # the timeline path before the CPU chunk decode. It is still wrong to
        # omit the fps: when the timeline path degrades to the band-crop path it
        # reaches the decode, and production always supplies these.
        source_fps=meta["fps"],
        source_fps_num=meta["fps_num"],
        source_fps_den=meta["fps_den"],
    )
    # Phase 1 over-split baseline (vtuber=True without Phase 2 classify) split far
    # more; here we assert the classified result is a sane, small match count.
    assert 0 < len(matches_vtuber) <= 12, (
        f"VTuber split should be practical, got {len(matches_vtuber)} matches"
    )


def _obs_sample() -> Path | None:
    base = os.environ.get("ALLAGANEYE_SAMPLE_VIDEO_DIR")
    if not base or not Path(base).exists():
        return None
    cands = list(Path(base).glob("*.mkv"))
    return cands[0] if cands else None


@pytest.mark.skipif(_obs_sample() is None, reason="OBS sample not available")
def test_obs_v2_vs_localize_presence_parity(caplog):
    """v2 (authoritative) と localize の scorebar-present を時間グリッドで突合。

    production には入れない harness 専用計測 (spec section 8.1 P2-b)。一様グリッドで
    v2-present と localize-present を比較し、不一致を per-sample ログ化する。long
    非試合区間 (lobby/result) を含む全域で v2/localize の FP/FN 差を可観測にする
    (Codex #3)。assert は緩く「不一致が極端でない」のみ (閾値校正は Phase 3)。
    """
    import logging

    from allaganeye.video.probe import probe_video
    from allaganeye.video import detector as det
    from allaganeye.video import scorebar as sb
    from allaganeye.video.probe_state import PresenceState

    video = _obs_sample()
    assert video is not None  # guaranteed by skipif; narrows Path | None -> Path
    meta = probe_video(video)
    duration = meta["duration"]

    # Uniform interior grid (avoid the very edges).
    n = 40
    times = [duration * (i + 1) / (n + 1) for i in range(n)]

    agree = 0
    disagree = 0
    with caplog.at_level(logging.INFO):
        for t in times:
            raw = det._probe_frame_rgb_hires(video, t)
            v2 = det._has_scorebar_v2(raw)
            loc = sb._localize_present_from_raw(raw)
            # v2=None means opencv absent; loc=UNKNOWN means probe failure
            if v2 is None or loc is PresenceState.UNKNOWN:
                continue
            loc_bool = loc is PresenceState.PRESENT
            if v2 == loc_bool:
                agree += 1
            else:
                disagree += 1
                logging.getLogger(__name__).info(
                    "PARITY_DIFF t=%.1f v2=%s localize=%s", t, v2, loc
                )
        total = agree + disagree
        logging.getLogger(__name__).info(
            "PARITY summary: %d/%d agree (%d diffs)", agree, total, disagree
        )

    assert total > 0, "no valid probes -- check sample video / opencv"
    # localize should broadly agree with v2 on OBS (the position-independent
    # localizer finds the same full-screen scorebar). A wildly low agreement
    # signals a regression worth Idios investigating; calibration is Phase 3.
    assert agree / total >= 0.6, f"v2/localize parity too low: {agree}/{total}"
