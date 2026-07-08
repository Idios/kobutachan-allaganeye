"""Area-map window detection PoC (#481).

Subcommands:
    extract    -- decode GT-case frames to PNG for manual annotation
    render-gt  -- draw GT bboxes onto extracted frames (visual check)
    build-refs -- build per-map reference features (npz) from GT crops
    run        -- run one candidate on one case (debug)
    compare    -- full A-vs-B comparison vs GT -> markdown report

Usage: python scripts/areamap_poc.py <subcommand> [--manifest PATH] [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from allaganeye.video.detector import _probe_frame_rgb_hires

FRAME_W, FRAME_H = 1920, 1080
DEFAULT_MANIFEST = Path("tests/baselines/v0.3.0/areamap-gt.json")
DEFAULT_OUT = Path(".tmp-areamap-poc")


@dataclass(frozen=True)
class Case:
    video_id: str
    video: Path
    t: float
    bbox: tuple[float, float, float, float] | None  # normalized xywh
    map_name: str | None
    visible: bool


def _expand_env(path_str: str) -> Path:
    def sub(m: re.Match[str]) -> str:
        val = os.environ.get(m.group(1))
        if val is None:
            raise SystemExit(f"env var {m.group(1)} is not set (needed by manifest)")
        return val

    return Path(re.sub(r"\$\{([A-Z_]+)\}", sub, path_str))


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_cases(manifest: dict) -> list[Case]:
    out: list[Case] = []
    for v in manifest["videos"]:
        for c in v["cases"]:
            out.append(
                Case(
                    video_id=v["id"],
                    video=_expand_env(v["video"]),
                    t=float(c["t"]),
                    bbox=tuple(c["bbox"]) if c.get("bbox") else None,
                    map_name=c.get("map_name"),
                    visible=bool(c.get("visible", True)),
                )
            )
    return out


def fetch_frames(video: Path, ts_list: list[float]) -> list[np.ndarray]:
    frames: list[np.ndarray] = []
    for t in ts_list:
        raw = _probe_frame_rgb_hires(video, t)
        if raw is None:
            continue
        frames.append(np.frombuffer(raw, dtype=np.uint8).reshape(FRAME_H, FRAME_W, 3))
    return frames


def case_sample_times(t: float) -> list[float]:
    """5 frames around t, 4 s apart -- the temporal stack a candidate consumes."""
    return [t - 8.0, t - 4.0, t, t + 4.0, t + 8.0]


def iou_xywh(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> float:
    ax0, ay0, aw, ah = a
    bx0, by0, bw, bh = b
    ax1, ay1 = ax0 + aw, ay0 + ah
    bx1, by1 = bx0 + bw, by0 + bh
    ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = ix * iy
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def cmd_extract(args: argparse.Namespace) -> None:
    import cv2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for case in iter_cases(load_manifest(Path(args.manifest))):
        frames = fetch_frames(case.video, [case.t])
        if not frames:
            print(f"[skip] {case.video_id} t={case.t}: decode failed")
            continue
        p = out / f"{case.video_id}_t{int(case.t)}.png"
        cv2.imwrite(str(p), cv2.cvtColor(frames[0], cv2.COLOR_RGB2BGR))
        print(f"[ok] {p}")


def cmd_render_gt(args: argparse.Namespace) -> None:
    import cv2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for case in iter_cases(load_manifest(Path(args.manifest))):
        if case.bbox is None:
            continue
        frames = fetch_frames(case.video, [case.t])
        if not frames:
            continue
        img = cv2.cvtColor(frames[0], cv2.COLOR_RGB2BGR)
        x, y, w, h = case.bbox
        pt1 = (int(x * FRAME_W), int(y * FRAME_H))
        pt2 = (int((x + w) * FRAME_W), int((y + h) * FRAME_H))
        cv2.rectangle(img, pt1, pt2, (0, 255, 0), 3)
        p = out / f"gt_{case.video_id}_t{int(case.t)}.png"
        cv2.imwrite(str(p), img)
        print(f"[ok] {p}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in [
        ("extract", cmd_extract),
        ("render-gt", cmd_render_gt),
        # build-refs / run / compare are added in P2-P4
    ]:
        sp = sub.add_parser(name)
        sp.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
        sp.add_argument("--out", default=str(DEFAULT_OUT))
        sp.set_defaults(fn=fn)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
