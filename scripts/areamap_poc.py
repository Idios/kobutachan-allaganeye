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
                    bbox=tuple(c["bbox"]) if c.get("bbox") is not None else None,
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


# ---- Candidate A: temporal stability + map reference matching ----
A_STD_THRESH = 12.0  # temporal std threshold (static mask)
A_MIN_AREA_FRAC = 0.03  # min component area (frame frac)
A_AR_RANGE = (0.6, 2.0)  # bbox aspect w/h range
A_MIN_EDGE_DENSITY = 0.05  # terrain texture floor inside candidate
A_REF_MATCH_MIN = 0.45  # TM_CCOEFF_NORMED floor
A_REF_WIDTH = 256  # ref image width (map crop resized)
A_SCALES = np.linspace(0.6, 1.6, 11)


def _temporal_stack(frames: list[np.ndarray]):
    import cv2

    grays = [cv2.cvtColor(f, cv2.COLOR_RGB2GRAY).astype(np.float32) for f in frames]
    stack = np.stack(grays)
    return np.median(stack, axis=0), stack.std(axis=0)


def _static_components(
    med: np.ndarray, std: np.ndarray
) -> list[tuple[int, int, int, int, float]]:
    """(x, y, w, h, edge_density) candidates from the static-overlay mask."""
    import cv2

    h_img, w_img = med.shape
    static = (std < A_STD_THRESH).astype(np.uint8)
    kernel = np.ones((9, 9), np.uint8)
    static = cv2.morphologyEx(static, cv2.MORPH_CLOSE, kernel)
    static = cv2.morphologyEx(static, cv2.MORPH_OPEN, kernel)
    n, _labels, stats, _ = cv2.connectedComponentsWithStats(static)
    out = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < A_MIN_AREA_FRAC * w_img * h_img:
            continue
        if not (A_AR_RANGE[0] <= w / max(h, 1) <= A_AR_RANGE[1]):
            continue
        roi = med[y : y + h, x : x + w].astype(np.uint8)
        edges = cv2.Canny(roi, 50, 150)
        density = float((edges > 0).mean())
        if density < A_MIN_EDGE_DENSITY:
            continue
        out.append((x, y, w, h, density))
    return out


def detect_candidate_a(frames, refs):
    import cv2

    if len(frames) < 3:
        return None
    med, std = _temporal_stack(frames)
    h_img, w_img = med.shape
    cands = _static_components(med, std)
    if not cands:
        return None
    med_u8 = med.astype(np.uint8)
    best = None  # (score, x, y, w, h, name)
    for name, ref in refs.items():
        for scale in A_SCALES:
            t = cv2.resize(ref, None, fx=scale, fy=scale)
            th, tw = t.shape
            if th >= h_img or tw >= w_img:
                continue
            res = cv2.matchTemplate(med_u8, t, cv2.TM_CCOEFF_NORMED)
            _, maxv, _, maxloc = cv2.minMaxLoc(res)
            if best is None or maxv > best[0]:
                best = (maxv, maxloc[0], maxloc[1], tw, th, name)
    if best is not None and best[0] >= A_REF_MATCH_MIN:
        score, bx, by, bw, bh, name = best
        ref_box = (bx / w_img, by / h_img, bw / w_img, bh / h_img)
        # window 枠込みの static component に ref の中心点が含まれるならそちらの bbox を採用
        # (ref は map テクスチャ部分のみで window より小さいため IoU でなく中心点包含で判定)
        rcx = ref_box[0] + ref_box[2] / 2
        rcy = ref_box[1] + ref_box[3] / 2
        for x, y, w, h, _d in cands:
            cx0, cy0 = x / w_img, y / h_img
            cx1, cy1 = (x + w) / w_img, (y + h) / h_img
            if cx0 <= rcx <= cx1 and cy0 <= rcy <= cy1:
                return (
                    *(x / w_img, y / h_img, w / w_img, h / h_img),
                    name,
                    float(score),
                )
        return (*ref_box, name, float(score))
    # Stage 2 不成立: 最大 edge density の static component (map_name なし、減点 score)
    x, y, w, h, d = max(cands, key=lambda c: c[4])
    return (x / w_img, y / h_img, w / w_img, h / h_img, None, float(d))


def build_refs(
    manifest: dict, exclude_video_id: str | None = None
) -> dict[str, np.ndarray]:
    """GT crop から map_name ごとの参照 grayscale 画像 (幅 A_REF_WIDTH) を作る。"""
    import cv2

    acc: dict[str, list[np.ndarray]] = {}
    for case in iter_cases(manifest):
        if not case.visible or case.bbox is None or case.map_name is None:
            continue
        if exclude_video_id is not None and case.video_id == exclude_video_id:
            continue
        frames = fetch_frames(case.video, case_sample_times(case.t))
        if len(frames) < 3:
            continue
        med, _std = _temporal_stack(frames)
        x, y, w, h = case.bbox
        crop = med[
            int(y * FRAME_H) : int((y + h) * FRAME_H),
            int(x * FRAME_W) : int((x + w) * FRAME_W),
        ]
        scale = A_REF_WIDTH / crop.shape[1]
        crop = cv2.resize(crop, (A_REF_WIDTH, max(1, int(crop.shape[0] * scale))))
        acc.setdefault(case.map_name, []).append(crop.astype(np.float32))
    refs: dict[str, np.ndarray] = {}
    for name, crops in acc.items():
        hmin = min(c.shape[0] for c in crops)
        stacked = np.stack([c[:hmin, :] for c in crops])
        refs[name] = stacked.mean(axis=0).astype(np.uint8)
    return refs


def cmd_build_refs(args: argparse.Namespace) -> None:
    refs = build_refs(load_manifest(Path(args.manifest)))
    out = Path(args.out) / "areamap_refs.npz"
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(str(out), **refs)  # type: ignore[call-arg]  # numpy stubs mis-type **kwds
    print(f"[ok] {out}: {sorted(refs)}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in [
        ("extract", cmd_extract),
        ("render-gt", cmd_render_gt),
        ("build-refs", cmd_build_refs),
        # run / compare are added in P3-P4
    ]:
        sp = sub.add_parser(name)
        sp.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
        sp.add_argument("--out", default=str(DEFAULT_OUT))
        sp.set_defaults(fn=fn)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
