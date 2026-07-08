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
    # refs may be empty -> stage-1 fallback is intended
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
        if crop.size == 0:
            continue
        scale = A_REF_WIDTH / crop.shape[1]
        crop = cv2.resize(crop, (A_REF_WIDTH, max(1, int(crop.shape[0] * scale))))
        acc.setdefault(case.map_name, []).append(crop.astype(np.float32))
    refs: dict[str, np.ndarray] = {}
    for name, crops in acc.items():
        hmin = min(c.shape[0] for c in crops)
        stacked = np.stack([c[:hmin, :] for c in crops])
        refs[name] = stacked.mean(axis=0).astype(np.uint8)
    return refs


# ---- Candidate B: window frame edge/line detection ----
B_CANNY = (40, 120)
B_HOUGH_THRESH = 120
B_MIN_LINE_FRAC = 0.12  # min line length (frame width frac)
B_MAX_GAP_PX = 8
B_ANGLE_TOL_DEG = 3.0
B_SIZE_RANGE = (0.15, 0.6)  # window w as frame-width frac
B_AR_RANGE = (0.6, 2.0)
B_SUPPORT_MIN = 0.35  # perimeter edge support floor


def detect_candidate_b(
    frames: list[np.ndarray],
) -> tuple[float, float, float, float, str | None, float] | None:
    import cv2

    if len(frames) < 3:
        return None
    med, _std = _temporal_stack(frames)
    h_img, w_img = med.shape
    edges = cv2.Canny(med.astype(np.uint8), *B_CANNY)
    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=B_HOUGH_THRESH,
        minLineLength=int(B_MIN_LINE_FRAC * w_img),
        maxLineGap=B_MAX_GAP_PX,
    )
    if lines is None:
        return None
    horiz, vert = [], []
    for x1, y1, x2, y2 in lines[:, 0]:
        ang = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
        if ang < B_ANGLE_TOL_DEG or ang > 180 - B_ANGLE_TOL_DEG:
            horiz.append((min(x1, x2), max(x1, x2), (y1 + y2) // 2))
        elif abs(ang - 90) < B_ANGLE_TOL_DEG:
            vert.append((min(y1, y2), max(y1, y2), (x1 + x2) // 2))
    best = None  # (score, x, y, w, h)
    for hx0, hx1, hy in horiz:  # top edge candidate
        for hx0b, hx1b, hyb in horiz:  # bottom edge candidate
            hgt = hyb - hy
            if hgt <= 0:
                continue
            wid = min(hx1, hx1b) - max(hx0, hx0b)
            if not (B_SIZE_RANGE[0] * w_img <= wid <= B_SIZE_RANGE[1] * w_img):
                continue
            if not (B_AR_RANGE[0] <= wid / hgt <= B_AR_RANGE[1]):
                continue
            x0, x1_ = max(hx0, hx0b), min(hx1, hx1b)
            # vertical support: 両側に縦線があるか
            lsup = any(
                abs(vx - x0) < 12 and vy0 < hy + hgt / 2 < vy1 for vy0, vy1, vx in vert
            )
            rsup = any(
                abs(vx - x1_) < 12 and vy0 < hy + hgt / 2 < vy1 for vy0, vy1, vx in vert
            )
            if not (lsup and rsup):
                continue
            # perimeter edge support
            rect_edges = edges[hy : hyb + 1, x0 : x1_ + 1]
            per = (
                float((rect_edges[0, :] > 0).mean())
                + float((rect_edges[-1, :] > 0).mean())
                + float((rect_edges[:, 0] > 0).mean())
                + float((rect_edges[:, -1] > 0).mean())
            ) / 4.0
            if per < B_SUPPORT_MIN:
                continue
            if best is None or per > best[0]:
                best = (per, x0, hy, wid, hgt)
    if best is None:
        return None
    score, x, y, w, h = best
    return (x / w_img, y / h_img, w / w_img, h / h_img, None, float(score))


def cmd_build_refs(args: argparse.Namespace) -> None:
    refs = build_refs(load_manifest(Path(args.manifest)))
    out = Path(args.out) / "areamap_refs.npz"
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(str(out), **refs)  # type: ignore[call-arg]  # numpy stubs mis-type **kwds
    print(f"[ok] {out}: {sorted(refs)}")


def cmd_run(args: argparse.Namespace) -> None:
    """1 case on 1 candidate -- writes overlay PNG to --out dir."""
    import cv2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(Path(args.manifest))
    cases = iter_cases(manifest)
    target = [c for c in cases if c.video_id == args.case_id]
    if not target:
        raise SystemExit(f"case not found: {args.case_id}")
    case = target[0]
    ts_list = case_sample_times(case.t)
    print(f"[run] fetching {len(ts_list)} frames for {case.video_id} t={case.t}...")
    frames = fetch_frames(case.video, ts_list)
    print(f"[run] got {len(frames)} frames")

    if args.candidate == "a":
        refs = build_refs(manifest, exclude_video_id=case.video_id)
        result = detect_candidate_a(frames, refs)
        label = "A"
    elif args.candidate == "b":
        result = detect_candidate_b(frames)
        label = "B"
    else:
        raise SystemExit(f"unknown candidate: {args.candidate}")

    # draw overlay
    main_frame = frames[len(frames) // 2]
    img = cv2.cvtColor(main_frame, cv2.COLOR_RGB2BGR)
    if result is not None:
        rx, ry, rw, rh, rname, rscore = result
        pt1 = (int(rx * FRAME_W), int(ry * FRAME_H))
        pt2 = (int((rx + rw) * FRAME_W), int((ry + rh) * FRAME_H))
        cv2.rectangle(img, pt1, pt2, (0, 0, 255), 3)
        cv2.putText(
            img,
            f"{label}: {rname or 'None'} s={rscore:.3f}",
            (pt1[0], max(pt1[1] - 8, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 255),
            2,
        )
    if case.bbox is not None:
        gx, gy, gw, gh = case.bbox
        gpt1 = (int(gx * FRAME_W), int(gy * FRAME_H))
        gpt2 = (int((gx + gw) * FRAME_W), int((gy + gh) * FRAME_H))
        cv2.rectangle(img, gpt1, gpt2, (0, 255, 0), 2)
    p = out / f"run_{label}_{case.video_id}_t{int(case.t)}.png"
    cv2.imwrite(str(p), img)
    iou = 0.0
    if result is not None and case.bbox is not None:
        iou = iou_xywh(result[:4], case.bbox)  # type: ignore[arg-type]
    print(f"[ok] {p}  result={result}  IoU={iou:.3f}")


def cmd_compare(args: argparse.Namespace) -> None:
    """Full A-vs-B comparison vs GT -> stdout markdown table."""
    manifest = load_manifest(Path(args.manifest))
    cases = iter_cases(manifest)
    refs = build_refs(manifest)
    rows = []
    for case in cases:
        ts_list = case_sample_times(case.t)
        frames = fetch_frames(case.video, ts_list)
        ra = detect_candidate_a(frames, refs)
        rb = detect_candidate_b(frames)
        iou_a = iou_xywh(ra[:4], case.bbox) if ra and case.bbox else 0.0  # type: ignore[index]
        iou_b = iou_xywh(rb[:4], case.bbox) if rb and case.bbox else 0.0  # type: ignore[index]
        rows.append((case.video_id, case.t, case.visible, iou_a, iou_b))
    print("| video_id | t | visible | IoU_A | IoU_B |")
    print("|---|---|---|---|---|")
    for vid, t, vis, ia, ib in rows:
        print(f"| {vid} | {t} | {vis} | {ia:.3f} | {ib:.3f} |")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in [
        ("extract", cmd_extract),
        ("render-gt", cmd_render_gt),
        ("build-refs", cmd_build_refs),
    ]:
        sp = sub.add_parser(name)
        sp.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
        sp.add_argument("--out", default=str(DEFAULT_OUT))
        sp.set_defaults(fn=fn)
    # run subcommand
    sp_run = sub.add_parser("run")
    sp_run.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    sp_run.add_argument("--out", default=str(DEFAULT_OUT))
    sp_run.add_argument("--candidate", default="b", choices=["a", "b"])
    sp_run.add_argument("--case-id", default="obs-20260116-1")
    sp_run.set_defaults(fn=cmd_run)
    # compare subcommand
    sp_cmp = sub.add_parser("compare")
    sp_cmp.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    sp_cmp.add_argument("--out", default=str(DEFAULT_OUT))
    sp_cmp.set_defaults(fn=cmd_compare)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
