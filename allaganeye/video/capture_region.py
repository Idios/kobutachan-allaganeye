"""Game capture region detection for overlay-heavy (VTuber) recordings (#753).

Normalized-coordinate region contract + geometry helpers + candidate
detectors (S1 variance / S2 scorebar-band / S3 blackout-overlap).
On standard OBS recordings every detector resolves to ``FULL_FRAME`` so
downstream brightness/scorebar behavior is unchanged (v0.3.0 baseline
bit-exact; see spec §3.4 / M4).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CaptureRegion:
    """Game capture rectangle in normalized [0,1] frame coordinates."""

    x: float
    y: float
    w: float
    h: float
    confidence: float = 1.0
    source: str = "fallback"  # "tierA" | "tierB" | "fallback"

    def clamp(self) -> CaptureRegion:
        x = min(max(self.x, 0.0), 1.0)
        y = min(max(self.y, 0.0), 1.0)
        w = min(max(self.w, 0.0), 1.0 - x)
        h = min(max(self.h, 0.0), 1.0 - y)
        return CaptureRegion(x, y, w, h, self.confidence, self.source)

    def to_dict(self) -> dict:
        return {
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "confidence": self.confidence,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict) -> CaptureRegion:
        return cls(
            d["x"],
            d["y"],
            d["w"],
            d["h"],
            d.get("confidence", 1.0),
            d.get("source", "fallback"),
        )


FULL_FRAME = CaptureRegion(0.0, 0.0, 1.0, 1.0, confidence=1.0, source="fallback")


@dataclass
class RegionTimeline:
    """Coarse region (Pass 1) + per-segment precise regions (#480/#481)."""

    coarse: CaptureRegion
    segments: list[tuple[tuple[float, float], CaptureRegion]] = field(
        default_factory=list
    )

    def to_dict(self) -> dict:
        return {
            "coarse": self.coarse.to_dict(),
            "segments": [
                {"time_range": [t0, t1], "region": r.to_dict()}
                for (t0, t1), r in self.segments
            ],
        }


_SNAP_FULL_FRAME_WH = 0.92
"""w と h が共にこの比率以上なら FULL_FRAME に snap。

OBS 録画では game = frame 全体のため検出器は frame 全域に近い矩形を返す。
わずかな端の欠けで IoU<1.0 になり baseline を壊すのを防ぐため full-frame
に snap し、Pass 1 輝度を現行と数値一致させる (spec §3.4 / M4)。
"""


def iou(a: CaptureRegion, b: CaptureRegion) -> float:
    ax2, ay2 = a.x + a.w, a.y + a.h
    bx2, by2 = b.x + b.w, b.y + b.h
    ix1, iy1 = max(a.x, b.x), max(a.y, b.y)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    union = a.w * a.h + b.w * b.h - inter
    return inter / union if union > 0 else 0.0


def top_edge_error_px(a: CaptureRegion, b: CaptureRegion, frame_h: int) -> float:
    return abs(a.y - b.y) * frame_h


def _maybe_snap_full_frame(region: CaptureRegion) -> CaptureRegion:
    if region.w >= _SNAP_FULL_FRAME_WH and region.h >= _SNAP_FULL_FRAME_WH:
        return FULL_FRAME
    return region
