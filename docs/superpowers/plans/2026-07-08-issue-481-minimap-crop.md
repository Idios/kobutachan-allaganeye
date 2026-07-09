# minimap 切抜き (#481) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `allaganeye minimap <metadata.json>` 新 command で、試合ごとにエリアマップ window
領域を自動検出し、座標を `minimap_regions` として metadata に永続化し、crop + h264 再エンコードの
切抜き MP4 を出力する。

**Architecture:** spec
[2026-07-08-issue-481-minimap-crop-design.md](../specs/2026-07-08-issue-481-minimap-crop-design.md)。
検出アルゴリズムは Phase 0 PoC (候補 A: 時間安定性 + map 照合 / 候補 B: window 枠 edge) で
実サンプル比較して勝者を確定 (checkpoint で Idios 判断)。実装は新 module
`allaganeye/video/areamap.py` + `allaganeye/commands/minimap.py` に閉じ、encode は export 基盤
(#761) に optional `video_filter` を additive 追加して再利用する。**detector.py / scorebar.py /
detection cache は非接触** (read-only import のみ可)。

**Tech Stack:** Python 3 / numpy / OpenCV (`cv2`) / typer / pytest (slow marker) / JSON Schema
codegen (#612) / zod / ffmpeg crop filter + NVENC/QSV/AMF/libx264。

## Global Constraints

- 変更禁止: `allaganeye/video/detector.py` / `scorebar.py` / `gpu_detector.py` /
  `capture_region.py` / detection cache (`_save_cache` / `_load_cache`)。import は可
- detect param を追加しない (cache key 3 箇所問題を構造的に回避、spec §3)
- `schema_version` は `"1"` のまま (additive optional field、#810 前例)
- export の `video_filter=None` (default) 経路は **argv bit-same** (test で pin)
- TDD (red first)。commit は task ごと、`Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- PR 本文 / commit に Closes / Fixes / Resolves 禁止 (Iron Law 4)。`Refs #481` を使う
- PR base = develop (l2-workflow 規約)。branch: PR 1 = `claude/l3-minimap-poc`、
  PR 2 = `claude/l3-minimap-impl`
- 質問・報告は日本語 (feedback_ask_in_japanese)

## PR 分割 (refactor-pattern §1 考慮)

| PR | 内容 | 状態 gate |
| --- | --- | --- |
| **PR 1 (Phase 0)** | `scripts/areamap_poc.py` + GT + PoC report。production 挙動変更なし | P5 checkpoint (勝者確定) 後に作成 |
| **PR 2 (Phase 1+2)** | schema / export 拡張 / areamap.py / minimap command / docs | diff > ~1500 行に膨らむ場合は 2a (F1+F2 基盤) / 2b (D1-D4 本体) 分割を Idios に AskUserQuestion |

## File Structure

| ファイル | 責務 | 変更種別 |
| --- | --- | --- |
| `scripts/areamap_poc.py` | PoC: extract / render-gt / build-refs / run / compare subcommand | Create (PR 1) |
| `tests/baselines/v0.3.0/areamap-gt.json` | GT manifest (video + timestamp + 正規化 bbox + map_name + visible) | Create (PR 1) |
| `docs/superpowers/specs/2026-07-XX-issue-481-areamap-poc-report.md` | PoC 結果 report (比較表 + 勝者判定根拠) | Create (PR 1) |
| `.gitignore` | `.tmp-areamap-poc/` 追加 | Modify (PR 1) |
| `schemas/metadata.schema.json` | `minimap_regions` + `$defs.MinimapRegionEntry` | Modify (PR 2) |
| `allaganeye/metadata_types.py` / `gui/src/types/metadata.generated.ts` | codegen 再生成 | Modify (PR 2) |
| `gui/src/types/metadata.schema.ts` | zod `MinimapRegionEntrySchema` + optional 配線 | Modify (PR 2) |
| `allaganeye/export/pool.py` | `ExportMatch.video_filter` field (default None) | Modify (PR 2) |
| `allaganeye/export/ffmpeg_runner.py` | `run_export_attempt` / `_build_ffmpeg_args` に `video_filter` kwarg | Modify (PR 2) |
| `allaganeye/video/areamap.py` | A seed 検出 fn (temporal-stability のみ) + `resolve_match_regions` (試合単位 consensus)。**提案モード専用** | Create (PR 2) |
| `allaganeye/commands/minimap.py` | command orchestration | Create (PR 2) |
| `allaganeye/cli.py` | `_minimap_cmd.register(app)` (module 末尾、export 同型) | Modify (PR 2) |
| `tests/test_areamap.py` / `tests/test_minimap_command.py` / `tests/test_areamap_slow.py` | unit + slow | Create (PR 2) |
| `tests/test_export_*.py` (既存) | video_filter default 不変 pin + crop args | Modify (PR 2) |
| `docs/cli-spec.md` / `docs/output-spec.md` / `docs/metadata-spec.md` / `CLAUDE.md` | doc SSoT (#818) | Modify (PR 2) |

## 実装前に確認済みの事実 (2026-07-08 self-review)

- `matches[]` entry: `{index, start_time, end_time, type, output_file, ...}`。`type` は
  `"fl_match"` / `"unknown"` 等。`post_match` / `type_override` / `edited.{start_time,end_time}`
  は optional。**post_match 除外 → include/exclude → type_override=="skip" 除外 → edited 優先**の
  filter 順は `commands/export.py:178-228` が正 (minimap も同順を踏襲)
- metadata に解像度 field は無い → `allaganeye.video.probe.probe_video(path)` (`ProbeResult`
  TypedDict: width/height/duration/fps...) で取得。失敗は `VideoProcessingError` (exit 3)
- frame 取得: `allaganeye.video.detector._probe_frame_rgb_hires(video_path, timestamp)
  -> bytes | None` (1920x1080 rgb24 raw)。read-only import (detector 非変更)
- `ExportMatch` は frozen dataclass (index/start/end/type_label)。
  `run_export_attempt(video, start, end, output, codec, encoder, *, progress_cb, fallback_cb,
  cancel_event)`。`_build_ffmpeg_args` は `codec != "copy"` で `_DECODE_HWACCEL_ARGS[encoder]`
  を `-i` 前に挿入 (#791 NVDEC zero-copy = GPU frame のまま encoder へ渡す)
  → **CPU filter `crop` は GPU frame を受けられない**ため、`video_filter` 指定時は
  decode hwaccel を挿入しない (CPU decode → crop → NVENC は system-memory frame 受理で可)
- exceptions: `InputFileError` (2) / `VideoProcessingError` (3) / `DetectionError` (4) /
  `ConfigValidationError` (5)。CLI 報告は `allaganeye.cli._report_app_error` (export 同型の
  遅延 import)
- `read_metadata` / `write_metadata_atomic` は unknown field を round-trip 保全 (dict ベース)
- `schemas/metadata.schema.json` `$defs` に `CaptureRegion` あり (#810)。codegen は
  `python scripts/codegen/generate.py`
- package data: `[tool.setuptools.package-data] "allaganeye.audio.refs" = ["*.npz"]` 前例
- CLI 登録: `cli.py` 末尾で `_export_cmd.register(app)` 同型
- export の非 json/quiet 進捗は typer.echo の plain 1 行形式 (rich 不使用) — minimap も同型
- サンプル: `E:\royalstraightflesh\videos` (OBS、`20260116/20260116_1.mp4` 等の手動分割 MP4 +
  長尺 MKV + `2026-02-09 23-12-24_allaganeye/metadata.json`)。masked は
  `E:\allaganeye-samples` (`_masked_a_out` に検証 metadata)。エリアマップは実フレームで
  左上、円形ナビマップは右上を確認済み (2026-07-08、spec §1)

依存: **P1 → P2 → P3 → P4 → P5 (checkpoint) → PR 1** / **F1 ∥ F2 → D1 → D2 → D3 → D4 → D5 → PR 2**。
F1 と F2 は独立 (並行 dispatch 可)。

> **Phase 0 結果による改訂 (2026-07-08 checkpoint、spec §6.3)**: 両候補が IoU≥0.9 gate 不合格
> → **`--region` 手動 primary + A seed 提案モード**に縮小 (Idios 確定)。本改訂は F1/D1/D2/D3 の
> task 本文に反映済み。要点: (1) `map_name` field 撤回 (entry = match_index + region のみ)
> (2) refs npz 同梱・regen script・pyproject 変更は撤回 (A seed は temporal-stability のみ、
> `refs={}` の stage-1 fallback 経路) (3) `--region` なし = 提案表示 + exit 4 (crop なし・
> metadata write なし)。crop + write-back は `--region` 指定時のみ (`source: "manual"`)
> (4) slow test は「seed 局在性 (中心が GT 内) + 負例で提案なし」に変更 (IoU 0.9 gate は課さない)

---

## Phase 0 — PoC (PR 1、branch `claude/l3-minimap-poc`)

> PoC の性質上、**閾値パラメータの調整は plan 逸脱ではない** (deliverable は compare report)。
> アルゴリズム構造の変更 (Stage 追加/削除) は P5 checkpoint で報告する。

### Task P1: PoC scaffold + GT manifest + extract / render-gt

**Files:**

- Create: `scripts/areamap_poc.py`
- Create: `tests/baselines/v0.3.0/areamap-gt.json`
- Modify: `.gitignore` (`.tmp-areamap-poc/` 1 行追加)

**Interfaces:**

- Produces: `load_manifest(path) -> dict` / `iter_cases(manifest) -> list[Case]` /
  `fetch_frames(video, ts_list) -> list[np.ndarray]` (H,W,3 uint8 RGB 1920x1080) /
  `iou_xywh(a, b) -> float` (正規化 xywh tuple)。P2-P4 が import する
- GT manifest 形式 (下記)。`${ALLAGANEYE_SAMPLE_VIDEO_DIR}` / `${ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER}`
  を環境変数置換

- [ ] **Step 1: GT manifest skeleton を書く**

`tests/baselines/v0.3.0/areamap-gt.json` (bbox は正規化 xywh。annotate 前は `null` を置き、
P1 Step 4 で実測値に置換する):

```json
{
  "note": "areamap PoC / slow-test GT. bbox = normalized [x, y, w, h] of the area-map window incl. frame. visible=false means the window is closed at t.",
  "videos": [
    {
      "id": "obs-20260116-1",
      "video": "${ALLAGANEYE_SAMPLE_VIDEO_DIR}/20260116/20260116_1.mp4",
      "cases": [
        { "t": 300.0, "bbox": null, "map_name": "onsal_hakair", "visible": true },
        { "t": 700.0, "bbox": null, "map_name": "onsal_hakair", "visible": true }
      ]
    },
    {
      "id": "obs-20260118-2",
      "video": "${ALLAGANEYE_SAMPLE_VIDEO_DIR}/20260118/20260118_2.mp4",
      "cases": [
        { "t": 600.0, "bbox": null, "map_name": "seal_rock", "visible": true }
      ]
    }
  ]
}
```

> annotate 対象は最低: OBS 3 動画 x 2-3 case + masked 2 動画 x 2 case + visible=false 1-2 case。
> 動画 id / timestamp は手元サンプルの実在 match に合わせて P1 実行時に確定する。

- [ ] **Step 2: `scripts/areamap_poc.py` scaffold を書く**

```python
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
import sys
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
        frames.append(
            np.frombuffer(raw, dtype=np.uint8).reshape(FRAME_H, FRAME_W, 3)
        )
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
        # build-refs / run / compare は P2-P4 で追加
    ]:
        sp = sub.add_parser(name)
        sp.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
        sp.add_argument("--out", default=str(DEFAULT_OUT))
        sp.set_defaults(fn=fn)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: extract を実行してフレームを目視確認**

Run: `python scripts/areamap_poc.py extract`
Expected: `.tmp-areamap-poc/obs-20260116-1_t300.png` 等が生成される。
(サンプル動画へのアクセスに `ALLAGANEYE_SAMPLE_VIDEO_DIR` 必須。実在しない timestamp は
manifest を実サンプルに合わせて修正)

- [ ] **Step 4: GT bbox を annotate**

抽出 PNG を表示し、エリアマップ window (装飾ヘッダー含む window 全体) の bbox を
ffmpeg crop 試行 (`ffmpeg -i frame.png -vf crop=W:H:X:Y out.png`) で追い込み、正規化して
manifest の `bbox: null` を実測値に置換。masked 動画の case もここで追加する
(map window が閉じている case = `visible: false` も 1-2 件確保)。

- [ ] **Step 5: render-gt で overlay を生成し目視 + Idios spot-check 用に保存**

Run: `python scripts/areamap_poc.py render-gt`
Expected: 緑枠が window に一致した `gt_*.png` 一式

- [ ] **Step 6: lint / 型 / commit**

Run: `ruff check . && ruff format --check . && pyright`
Expected: 0 error (scripts/ も対象)

```bash
git add scripts/areamap_poc.py tests/baselines/v0.3.0/areamap-gt.json .gitignore
git commit -m "poc(#481): areamap PoC scaffold + GT manifest (extract/render-gt) (Refs #481)"
```

### Task P2: 候補 A — 時間安定性 + map 照合 (+ build-refs)

**Files:**

- Modify: `scripts/areamap_poc.py`

**Interfaces:**

- Produces: `detect_candidate_a(frames: list[np.ndarray], refs: dict[str, np.ndarray])
  -> tuple[float, float, float, float, str | None, float] | None`
  (正規化 xywh + map_name + score)。`build_refs(manifest, exclude_video_id=None)
  -> dict[str, np.ndarray]` (map_name -> grayscale ref 画像、leave-one-video-out 用 exclude)
- **注 (Phase 0 checkpoint 改訂)**: 上記 6-tuple (map_name 含む) は PoC script 内の歴史的
  interface としてそのまま残す。`map_name` は checkpoint で撤回済みのため、D1 の production
  port では `detect_areamap_seed` の 5-tuple `DetectResult = (x, y, w, h, score)` に縮小する
  (D1 Interfaces 参照)。PR 2 実装者は D1 定義を正とすること

- [ ] **Step 1: 候補 A + build-refs を実装**

`scripts/areamap_poc.py` に追加 (閾値は初期値、PoC 中の調整可):

```python
# ---- Candidate A: temporal stability + map reference matching ----
A_STD_THRESH = 12.0          # temporal std threshold (static mask)
A_MIN_AREA_FRAC = 0.03       # min component area (frame frac)
A_AR_RANGE = (0.6, 2.0)      # bbox aspect w/h range
A_MIN_EDGE_DENSITY = 0.05    # terrain texture floor inside candidate
A_REF_MATCH_MIN = 0.45       # TM_CCOEFF_NORMED floor
A_REF_WIDTH = 256            # ref image width (map crop resized)
A_SCALES = np.linspace(0.6, 1.6, 11)


def _temporal_stack(frames: list[np.ndarray]):
    import cv2

    grays = [
        cv2.cvtColor(f, cv2.COLOR_RGB2GRAY).astype(np.float32) for f in frames
    ]
    stack = np.stack(grays)
    return np.median(stack, axis=0), stack.std(axis=0)


def _static_components(med: np.ndarray, std: np.ndarray) -> list[tuple[int, int, int, int, float]]:
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
        # window 枠込みの static component と重なるならそちらの bbox を採用
        for x, y, w, h, _d in cands:
            comp_box = (x / w_img, y / h_img, w / w_img, h / h_img)
            if iou_xywh(ref_box, comp_box) >= 0.5:
                return (*comp_box, name, float(score))
        return (*ref_box, name, float(score))
    # Stage 2 不成立: 最大 edge density の static component (map_name なし、減点 score)
    x, y, w, h, d = max(cands, key=lambda c: c[4])
    return (x / w_img, y / h_img, w / w_img, h / h_img, None, float(d))


def build_refs(manifest: dict, exclude_video_id: str | None = None) -> dict[str, np.ndarray]:
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
    np.savez_compressed(out, **refs)
    print(f"[ok] {out}: {sorted(refs)}")
```

`main()` の subcommand 表に `("build-refs", cmd_build_refs)` を追加。

- [ ] **Step 2: 1 case で動作確認 (debug run)**

Run: `python scripts/areamap_poc.py build-refs` →
`python - <<'EOF'` で 1 case に `detect_candidate_a` をかけ bbox print、render-gt と同様に
overlay PNG を出して目視。
Expected: GT に近い bbox (この時点で IoU 数値までは問わない)

- [ ] **Step 3: lint / commit**

```bash
ruff check . && ruff format --check . && pyright
git add scripts/areamap_poc.py
git commit -m "poc(#481): candidate A (temporal stability + map ref matching) (Refs #481)"
```

### Task P3: 候補 B — window 枠 edge 検出

**Files:**

- Modify: `scripts/areamap_poc.py`

**Interfaces:**

- Produces: `detect_candidate_b(frames: list[np.ndarray])
  -> tuple[float, float, float, float, str | None, float] | None` (map_name は常に None)
- **注 (Phase 0 checkpoint 改訂)**: PoC script 内は上記 6-tuple のまま。production port 時の
  正は D1 の 5-tuple `DetectResult` (P2 Interfaces の注と同じ)

- [ ] **Step 1: 候補 B を実装**

```python
# ---- Candidate B: window frame edge/line detection ----
B_CANNY = (40, 120)
B_HOUGH_THRESH = 120
B_MIN_LINE_FRAC = 0.12     # min line length (frame width frac)
B_MAX_GAP_PX = 8
B_ANGLE_TOL_DEG = 3.0
B_SIZE_RANGE = (0.15, 0.6)  # window w as frame-width frac
B_AR_RANGE = (0.6, 2.0)
B_SUPPORT_MIN = 0.35        # perimeter edge support floor


def detect_candidate_b(frames):
    import cv2

    if len(frames) < 3:
        return None
    med, _std = _temporal_stack(frames)
    h_img, w_img = med.shape
    edges = cv2.Canny(med.astype(np.uint8), *B_CANNY)
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180, threshold=B_HOUGH_THRESH,
        minLineLength=int(B_MIN_LINE_FRAC * w_img), maxLineGap=B_MAX_GAP_PX,
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
    for hx0, hx1, hy in horiz:              # top edge candidate
        for hx0b, hx1b, hyb in horiz:       # bottom edge candidate
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
            lsup = any(abs(vx - x0) < 12 and vy0 < hy + hgt / 2 < vy1 for vy0, vy1, vx in vert)
            rsup = any(abs(vx - x1_) < 12 and vy0 < hy + hgt / 2 < vy1 for vy0, vy1, vx in vert)
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
```

- [ ] **Step 2: 1 case debug run + overlay 目視** (P2 Step 2 と同手順)
- [ ] **Step 3: lint / commit**

```bash
git add scripts/areamap_poc.py
git commit -m "poc(#481): candidate B (window frame edge detection) (Refs #481)"
```

### Task P4: compare runner + report 生成

**Files:**

- Modify: `scripts/areamap_poc.py`

**Interfaces:**

- Produces: `compare` subcommand → stdout 比較表 + `--out` に
  `areamap-poc-report.md` (case 別 IoU / 成功率 / 負例判定 / 勝者判定素案)

- [ ] **Step 1: compare を実装**

```python
IOU_SUCCESS = 0.9  # spec §6.2


def cmd_compare(args: argparse.Namespace) -> None:
    manifest = load_manifest(Path(args.manifest))
    rows = []
    for case in iter_cases(manifest):
        frames = fetch_frames(case.video, case_sample_times(case.t))
        refs = build_refs(manifest, exclude_video_id=case.video_id)  # LOVO
        ra = detect_candidate_a(frames, refs)
        rb = detect_candidate_b(frames)
        row = {"id": f"{case.video_id}@t{int(case.t)}", "visible": case.visible}
        for key, r in (("A", ra), ("B", rb)):
            if not case.visible:
                # 負例: None (未検出) が正解
                row[key] = "OK(reject)" if r is None else f"FP({r[5]:.2f})"
            elif r is None:
                row[key] = "MISS"
            else:
                iou = iou_xywh(case.bbox, r[:4])
                verdict = "OK" if iou >= IOU_SUCCESS else "LOW"
                row[key] = f"{verdict}(IoU={iou:.3f}, map={r[4]}, s={r[5]:.2f})"
        rows.append(row)
        print(row)
    # markdown report
    out = Path(args.out) / "areamap-poc-report.md"
    lines = ["# areamap PoC compare (#481)", "", "| case | visible | A | B |", "| --- | --- | --- | --- |"]
    for r in rows:
        lines.append(f"| {r['id']} | {r['visible']} | {r['A']} | {r['B']} |")
    for key in ("A", "B"):
        pos = [r for r in rows if r["visible"]]
        ok = sum(1 for r in pos if r[key].startswith("OK"))
        neg = [r for r in rows if not r["visible"]]
        rej = sum(1 for r in neg if r[key].startswith("OK"))
        lines.append("")
        lines.append(f"- **{key}**: positive {ok}/{len(pos)} / negative reject {rej}/{len(neg)}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[ok] {out}")
```

`main()` に `("compare", cmd_compare)` を追加 (`run` debug subcommand は任意)。

- [ ] **Step 2: lint / commit**

```bash
git add scripts/areamap_poc.py
git commit -m "poc(#481): A-vs-B compare runner + markdown report (Refs #481)"
```

### Task P5: PoC 実行 + 勝者確定 checkpoint + PR 1

- [ ] **Step 1: full compare 実行** — `python scripts/areamap_poc.py compare`。
  成功率が両案とも低い場合は閾値を 2-3 回まで調整して再実行 (調整履歴は report に残す)
- [ ] **Step 2: report を repo に取り込む** —
  `.tmp-areamap-poc/areamap-poc-report.md` を
  `docs/superpowers/specs/2026-07-XX-issue-481-areamap-poc-report.md` (実施日で置換) に整形
  (dataset 構成 / 調整履歴 / 勝者判定根拠 / spec §6.2 の STOP 条件判定を追記)
- [ ] **Step 3: CHECKPOINT (AskUserQuestion、Idios)** — 比較表を提示し
  「A 採用 / B 採用 / 両案不合格 → `--region` 手動 primary へ scope 縮小 (spec §6.2 STOP)」
  を確定。**結果を spec §6 に追記 commit**
- [ ] **Step 4: PR 1 作成** — Iron Law 6 Pre-flight (Step 0 `gh pr list --search "481"` →
  base develop 同期 → 交差判定 → Step 4 重複再確認 → Step 5
  `codex-companion.mjs adversarial-review` focus: "PoC script correctness, GT leakage
  (leave-one-video-out), Iron Law 3 scope") → PR 作成 (`Refs #481`、Self-Test Report 付き)
  → `/iterate-review` → 収束後 Idios に merge 依頼 (AskUserQuestion)

---

## Phase 1 — 基盤 (PR 2、branch `claude/l3-minimap-impl`、F1 ∥ F2 並行可)

### Task F1: metadata schema `minimap_regions` + codegen + zod

**Files:**

- Modify: `schemas/metadata.schema.json`
- Modify (regen): `allaganeye/metadata_types.py` / `gui/src/types/metadata.generated.ts`
- Modify: `gui/src/types/metadata.schema.ts`
- Test: `tests/test_metadata_schema.py` / `tests/test_metadata_types.py` /
  `gui/src/types/metadata.schema.test.ts` (既存ハーネスにケース追加)

**Interfaces:**

- Produces: schema 形状 (下記)。D2 の write-back と D1 の entry 生成が準拠する

- [ ] **Step 1: failing test** — `tests/test_metadata_schema.py` に追加:

```python
def test_minimap_regions_valid(schema_validator, minimal_metadata):
    minimal_metadata["minimap_regions"] = [
        {
            "match_index": 1,
            "region": {
                "x": 0.01, "y": 0.02, "w": 0.28, "h": 0.35,
                "confidence": 1.0, "source": "manual",
            },
        },
        {
            "match_index": 3,
            "region": {
                "x": 0.0, "y": 0.0, "w": 0.3, "h": 0.4,
                "confidence": 1.0, "source": "manual",
            },
        },
    ]
    schema_validator.validate(minimal_metadata)  # must not raise


def test_minimap_regions_rejects_bad_entries(schema_validator, minimal_metadata):
    for bad in [
        [{"match_index": 0, "region": _VALID_REGION}],                # index < 1
        [{"match_index": 1}],                                         # region 欠落
        [{"region": _VALID_REGION}],                                  # match_index 欠落
        [{"match_index": 1, "region": _VALID_REGION, "extra": 1}],    # additionalProperties
    ]:
        minimal_metadata["minimap_regions"] = bad
        with pytest.raises(jsonschema.ValidationError):
            schema_validator.validate(minimal_metadata)
```

(fixture 名は既存 test ファイルの実名に合わせる。`_VALID_REGION` は valid ケースと同 dict)

- [ ] **Step 2: fail 確認** — `pytest tests/test_metadata_schema.py -k minimap -v` → FAIL
- [ ] **Step 3: schema 追加** — `schemas/metadata.schema.json`:

`properties` に:

```json
"minimap_regions": {
  "type": "array",
  "description": "#481: per-match area-map crop region (normalized) actually used by `allaganeye minimap --region`. Missing entry for a match = not cropped. Field absent = minimap crop never ran.",
  "items": { "$ref": "#/$defs/MinimapRegionEntry" }
}
```

`$defs` に:

```json
"MinimapRegionEntry": {
  "type": "object",
  "properties": {
    "match_index": { "type": "integer", "minimum": 1 },
    "region": { "$ref": "#/$defs/CaptureRegion" }
  },
  "required": ["match_index", "region"],
  "additionalProperties": false
}
```

- [ ] **Step 4: codegen** — `python scripts/codegen/generate.py` → 生成 diff を確認 →
  `pytest tests/test_metadata_schema.py tests/test_metadata_types.py -v` PASS
- [ ] **Step 5: zod** — `gui/src/types/metadata.schema.ts` に `MinimapRegionEntrySchema`
  (CaptureRegionSchema 再利用、`match_index` + `region` の 2 field) +
  `minimap_regions: z.array(MinimapRegionEntrySchema).optional()`。
  vitest round-trip (metadataStore load→apply で field 保全) を追加 → red→green
- [ ] **Step 6: GUI 検査** — `cd gui && npm run lint && npm run typecheck && npm test` PASS
- [ ] **Step 7: commit**

```bash
git add schemas/metadata.schema.json allaganeye/metadata_types.py gui/src/types/ tests/
git commit -m "feat(#481): metadata schema に minimap_regions field を追加 (codegen + zod) (Refs #481)"
```

### Task F2: export 基盤に optional `video_filter` (default 挙動 bit-same)

**Files:**

- Modify: `allaganeye/export/pool.py` (`ExportMatch`) /
  `allaganeye/export/ffmpeg_runner.py` (`run_export_attempt` / `_build_ffmpeg_args`)
- Test: 既存 export test ファイル (`tests/` の `_build_ffmpeg_args` / pool を扱うもの) に追加

**Interfaces:**

- Produces: `ExportMatch(..., video_filter: str | None = None)`。
  `run_export_attempt(..., video_filter: str | None = None)`。
  semantics: `video_filter` 指定時は (a) `_DECODE_HWACCEL_ARGS` を挿入しない
  (NVDEC zero-copy の GPU frame は CPU `crop` に渡せない #791)、(b) `-vf <filter>` を
  `-c:v` の直前に挿入、(c) `codec=="copy"` との併用は `ValueError`

- [ ] **Step 1: failing tests**

```python
def test_build_args_default_unchanged_pin():
    # video_filter を省略した argv は従来と完全一致 (bit-same pin)
    args_h264 = _build_ffmpeg_args(
        "ffmpeg", Path("in.mkv"), 1.0, 2.0, Path("out.mp4"), "h264", H264Encoder.NVENC
    )
    assert "-vf" not in args_h264
    assert "-hwaccel" in args_h264  # NVDEC zero-copy 維持

def test_build_args_video_filter_inserts_vf_and_drops_hwaccel():
    args = _build_ffmpeg_args(
        "ffmpeg", Path("in.mkv"), 1.0, 2.0, Path("out.mp4"), "h264",
        H264Encoder.NVENC, video_filter="crop=534:392:24:22",
    )
    assert "-hwaccel" not in args
    i = args.index("-vf")
    assert args[i + 1] == "crop=534:392:24:22"
    assert args.index("-vf") < args.index("-c:v")

def test_run_export_attempt_rejects_filter_with_copy():
    with pytest.raises(ValueError):
        run_export_attempt(
            Path("in.mkv"), 0.0, 1.0, Path("o.mp4"), "copy", H264Encoder.LIBX264,
            progress_cb=lambda p, s: None, fallback_cb=None,
            cancel_event=threading.Event(), video_filter="crop=2:2:0:0",
        )
```

- [ ] **Step 2: fail 確認** → **Step 3: 実装**

`_build_ffmpeg_args(..., video_filter: str | None = None)`:

```python
if codec != "copy" and video_filter is None:
    args.extend(_DECODE_HWACCEL_ARGS[encoder])
...
else:
    if video_filter is not None:
        args.extend(["-vf", video_filter])
    args.extend(["-c:v", encoder.value])
```

`run_export_attempt(..., video_filter: str | None = None)`: 冒頭 guard
`if video_filter is not None and codec == "copy": raise ValueError(...)`、
1st attempt / libx264 retry の両 `_build_ffmpeg_args` 呼び出しに `video_filter=video_filter`。
`ExportMatch` に `video_filter: str | None = None`、pool worker の `run_export_attempt`
呼び出しに `video_filter=m.video_filter`。

- [ ] **Step 4: 既存 + 新規 test PASS** — `pytest tests/ -k "export or ffmpeg" -v`
- [ ] **Step 5: commit**

```bash
git add allaganeye/export/pool.py allaganeye/export/ffmpeg_runner.py tests/
git commit -m "feat(#481): export 基盤に optional video_filter (default 経路 bit-same pin 付き) (Refs #481)"
```

---

## Phase 2 — 本体 (PR 2 続き)

### Task D1: `areamap.py` — A seed port + 試合単位 consensus (提案モード専用)

**Files:**

- Create: `allaganeye/video/areamap.py`
- Test: `tests/test_areamap.py`

**Interfaces:**

- Consumes: `scripts/areamap_poc.py` の `detect_candidate_a` の temporal-stability 部分
  (`_temporal_stack` / `_static_components` / whole-frame guard `A_MAX_DIM_FRAC`)。
  **map 照合 (refs/Stage 2) は撤回済みなので移植しない** — `detect_areamap_seed` として
  refs なし単体化して areamap.py へ移植し、poc script は移植先を import する形に逆転して
  重複を消す
- Produces:

```python
@dataclass(frozen=True)
class MatchRegionResult:
    match_index: int
    region: CaptureRegion   # 正規化。source="auto" (seed 提案)、confidence=一致 window 率
    scattered: bool         # window 間で bbox が揺れた (warning 対象)

DetectResult = tuple[float, float, float, float, float] | None  # (x, y, w, h, score)
DetectFn = Callable[[list[np.ndarray]], DetectResult]
```

- **frame probe の private API 方針**: default probe は `detector._probe_frame_rgb_hires`
  (private helper) の **read-only import を継続**する。detector.py は変更禁止 (Global
  Constraints) のため公開 alias は追加できず、repo には cross-module private 利用の前例
  (scorebar.py ⟷ detector.py) がある。areamap.py の import 行に「detector 非変更の制約下での
  意図的な private 利用 (#481 plan D1)」の comment を 1 行付けること

```python

def resolve_match_regions(
    video_path: Path,
    matches: list[tuple[int, float, float]],   # (match_index, start_time, end_time)
    *,
    windows: int = 3,
    frames_per_window: int = 5,
    edge_margin: float = 60.0,
    iou_cluster: float = 0.75,
    probe: Callable[[Path, float], bytes | None] | None = None,  # DI (test 用)
    detect: DetectFn | None = None,                              # DI (test 用)
) -> tuple[list[MatchRegionResult], list[str]]:
    """試合ごとに windows 個の時間窓で検出し、IoU >= iou_cluster の多数派を採用。

    consensus 規約 (spec §8):
    - 多数派 cluster (>= ceil(windows/2)) の要素ごと中央値 bbox を採用
    - confidence = 多数派 window 数 / 検出成功 window 数
    - 非多数派 window が 1 つでもあれば scattered=True (warning)
    - 全 window 未検出 → その match は結果 list に含めない
    戻り値第 2 要素は表示用 warning 文字列 list。
    """
```

- [ ] **Step 1: failing tests (consensus を DI で検証、cv2 不要)**

```python
def _det_seq(results):
    it = iter(results)
    return lambda frames: next(it)

def test_consensus_majority_and_confidence():
    fake_probe = lambda v, t: b"\x00" * (1920 * 1080 * 3)
    box = (0.01, 0.02, 0.28, 0.35, 0.9)
    off = (0.50, 0.50, 0.20, 0.20, 0.5)  # IoU=0 の外れ window
    results, warns = resolve_match_regions(
        Path("v.mkv"), [(1, 100.0, 1100.0)],
        probe=fake_probe, detect=_det_seq([box, box, off]),
    )
    assert len(results) == 1
    r = results[0]
    assert r.match_index == 1 and r.region.source == "auto"
    assert r.scattered is True and abs(r.region.confidence - 2 / 3) < 1e-6
    assert warns  # 移動疑い warning

def test_all_windows_miss_drops_match():
    results, warns = resolve_match_regions(
        Path("v.mkv"), [(1, 100.0, 1100.0)],
        probe=lambda v, t: b"\x00" * (1920 * 1080 * 3),
        detect=lambda frames: None,
    )
    assert results == [] and any("1" in w for w in warns)

def test_short_match_uses_midpoint_samples():
    # end-start < 2*edge_margin でも sample が生成される (中央寄せ)
    seen = []
    def probe(v, t):
        seen.append(t)
        return b"\x00" * (1920 * 1080 * 3)
    resolve_match_regions(
        Path("v.mkv"), [(1, 0.0, 90.0)], probe=probe,
        detect=lambda f: (0.0, 0.0, 0.3, 0.3, 0.9),
    )
    assert all(0.0 <= t <= 90.0 for t in seen) and seen
```

- [ ] **Step 2: fail 確認** → **Step 3: 実装** — sampling:
  `usable = [start+edge_margin, end-edge_margin]`、幅が
  `windows*frames_per_window*2` 秒未満なら margin を捨て `[start, end]` を均等分割。
  各 window の `frames_per_window` timestamp を等間隔生成 → `probe` (default
  `detector._probe_frame_rgb_hires`) で decode → `detect` (default =
  `detect_areamap_seed`) → cluster (代表 = 要素ごと `statistics.median`) → `CaptureRegion(
  x, y, w, h, confidence=hits/valid, source="auto")`
- [ ] **Step 4: PASS 確認** → **Step 5: `detect_areamap_seed` の合成画像 unit** (静的明色
  矩形 overlay + 乱数背景 5 frame で bbox IoU ≥ 0.8 を assert。whole-frame guard の
  発火 unit も追加)。poc script 側を移植先 import に切替え、`python scripts/areamap_poc.py
  compare` が改修後も同一成績を出すことを確認 (回帰 pin)
- [ ] **Step 6: commit**

```bash
git add allaganeye/video/areamap.py scripts/areamap_poc.py tests/test_areamap.py
git commit -m "feat(#481): areamap.py (A seed 検出 + 試合単位 consensus、提案モード用) (Refs #481)"
```

### Task D2: `commands/minimap.py` + CLI 配線

**Files:**

- Create: `allaganeye/commands/minimap.py`
- Modify: `allaganeye/cli.py` (末尾に `from allaganeye.commands import minimap as
  _minimap_cmd` + `_minimap_cmd.register(app)`)
- Test: `tests/test_minimap_command.py` (typer.testing.CliRunner + monkeypatch)

**Interfaces:**

- Consumes: `resolve_match_regions` (D1) / `ExportMatch(video_filter=...)` +
  `export_matches` (F2) / `enumerate_h264_encoders` / `read_metadata` /
  `write_metadata_atomic` / `probe_video` / `_parse_indexes_csv` (commands/export.py から import)
- Produces: `allaganeye minimap <metadata.json> [-o DIR] [--region X,Y,W,H]
  [--include CSV] [--name-pattern PAT] [--quiet]`

- [ ] **Step 1: failing tests** (主要 6 系統。CliRunner + monkeypatch で
  `resolve_match_regions` / `export_matches` / `probe_video` を差し替え):

```python
def test_match_set_mirrors_export_rules(...):
    # post_match 除外が --include より先 / type_override=="skip" 除外 / edited 優先
def test_region_manual_pixel_parse_and_validation(...):
    # "24,22,534,392" -> 正規化 + source="manual" / 範囲外 (x+w>width)・w<16 は exit 5
def test_writeback_preserves_existing_fields(tmp_path, ...):
    # --region crop 実行時のみ write-back。capture_regions / brightness_samples /
    # 未知 field が write-back 後も残る。minimap_regions は match_index 昇順
def test_proposal_mode_exits_4_without_crop(...):
    # --region なし: resolve mock が提案を返す -> stdout に試合ごと
    # "--region X,Y,W,H" 形式の提案 + exit 4。metadata 不変・export_matches 未呼出
def test_proposal_mode_no_seed_still_exits_4(...):
    # resolve が ([], warns) -> 「提案なし」表示 + exit 4 + --region 案内
def test_region_crop_encode_failure_exit_1(...):
    # --region 指定で encode summary.failure>0 -> exit 1 (export 契約と同一)
def test_crop_filter_mod2_and_clamp(...):
    # 正規化 0.2781 * 1920 = 534.0 -> "crop=534:392:24:22" / 奇数は -1 で mod-2 化
    # x+w が frame を超えないよう clamp
```

- [ ] **Step 2: fail 確認** → **Step 3: 実装** — export.py の構造を踏襲:

```python
"""``allaganeye minimap`` Typer command (#481).

metadata.json を入力に、試合ごとにエリアマップ window (通称 minimap) 領域を
検出して minimap_regions に永続化し、crop + h264 の切抜き MP4 を出力する。
"""
# 実装骨子 (export.py:129-381 の pattern を踏襲、PoC checkpoint 改訂版):
# 1. read_metadata (InputFileError -> _report_app_error 経由 exit 2)
# 2. source 解決 + probe_video で width/height (VideoProcessingError -> exit 3)
# 3. match set: post_match -> include -> type_override -> edited (export と同順)
#    抽出形: (index, start, end) のリスト
# 4a. 提案モード (--region なし):
#    resolve_match_regions(video, match_tuples) -> (results, warns)
#    warns を typer.echo(err=True)。results を試合ごとに pixel 換算して
#    「match 3: --region 24,22,534,392 (confidence 0.67)」形式で表示
#    (そのまま貼れる形式)。results 空なら「提案なし」。crop なし・write-back なしで
#    常に DetectionError (exit 4、"crop の実行には --region X,Y,W,H を指定して
#    ください" hint) を raise
# 4b. crop モード (--region "X,Y,W,H"、source 解像度 pixel):
#    int parse 失敗/負値/はみ出し/w or h < 16 -> ConfigValidationError (exit 5)。
#    全 match に同一 region、source="manual", confidence=1.0
# 5. (crop モードのみ) write-back: payload = read_metadata の dict に
#    payload["minimap_regions"] = [entry...] (match_index 昇順、entry =
#    {match_index, region} の 2 field) を代入し write_metadata_atomic。
#    encode 失敗でも座標は残る (先に書く)
# 6. crop 文字列: px = round(r.x*W) 等 -> w -= w % 2, h -= h % 2,
#    x = min(x, W - w), y = min(y, H - h) で clamp -> f"crop={w}:{h}:{x}:{y}"
# 7. encode: slots = enumerate_h264_encoders(system_info 由来、export と同引数) ->
#    ExportMatch(index, start, end, type_label, video_filter=crop) ->
#    export_matches(codec="h264", name_pattern=..., output_dir=
#    (-o or metadata_path.parent / "minimap"), progress_cb=export と同 plain text)
#    filename 衝突 guard も export と同実装 (ConfigValidationError)
# 8. summary: failure > 0 -> exit 1 / cancelled -> exit 130 (SIGINT handler も export 同型)
```

- [ ] **Step 4: PASS 確認** — `pytest tests/test_minimap_command.py -v` +
  `allaganeye minimap --help` が出ること
- [ ] **Step 5: commit**

```bash
git add allaganeye/commands/minimap.py allaganeye/cli.py tests/test_minimap_command.py
git commit -m "feat(#481): allaganeye minimap command (検出 -> write-back -> crop encode) (Refs #481)"
```

### Task D3: slow 実機テスト

**Files:**

- Create: `tests/test_areamap_slow.py` (slow marker、`sample_video_dir` fixture 慣例に従う)

- [ ] **Step 1: test 実装** — GT manifest (`areamap-gt.json`) を読み、best-effort 契約で
  検証する (D3 2026-07-09 確定)。visible=true + bbox あり (5 case): 提案が出た場合は
  中心が GT bbox 内 (per-case) + 5 case 中 >=3 が提案を返す (集計)。visible=false
  (t=2354): 提案なし。visible=true + bbox null (t=1106): slow assert 対象外。
  IoU >= 0.9 gate は課さない (spec sec.6.3 縮小)。`ALLAGANEYE_SAMPLE_VIDEO_DIR` 未設定なら
  skip (既存慣例)
- [ ] **Step 2: 実行** — `pytest tests/test_areamap_slow.py -m slow -v` PASS (実機)
- [ ] **Step 3: E2E 手動 2 回** — 実 metadata.json に対し (a) `allaganeye minimap` (提案
  モード、exit 4 + 提案表示を確認) (b) 提案値を使った `--region` crop 実行で出力 MP4 を目視
  (マップが正しく切れているか) + metadata の `minimap_regions` 確認
- [ ] **Step 4: commit**

### Task D4: docs 更新 (#818 SSoT)

**Files:** `docs/cli-spec.md` / `docs/output-spec.md` / `docs/metadata-spec.md` / `CLAUDE.md`

- [ ] **Step 1**: cli-spec に `minimap` command § (構文 / オプション表 / exit code /
  「対象はエリアマップ window (通称 minimap)」の用語注記)。**追加前に
  `grep -n '^## '` で全 section 確認** (feedback_grep_full_doc_before_section_add)
- [ ] **Step 2**: output-spec に minimap 出力行 (`minimap/{idx:03}_minimap_{start}.mp4` +
  metadata write-back) を追加
- [ ] **Step 3**: metadata-spec に `minimap_regions` § (semantics / source ("manual" のみ
  write される旨) / entry 欠落 = 未 crop / field 欠落 = 未実行 / GUI ConflictModal との関係。
  `map_name` は checkpoint 撤回済みなので**書かない**)
- [ ] **Step 4**: CLAUDE.md モジュール表に `video/areamap.py` / `commands/minimap.py` 行 +
  コマンド例 `allaganeye minimap <metadata.json>` 1 行
- [ ] **Step 5**: `bash scripts/check-markdownlint.sh` PASS → commit

### Task D5: full checks + PR 2

- [ ] **Step 1: Python full** — `ruff check . && ruff format --check . && pyright && pytest`
- [ ] **Step 2: GUI full** — `cd gui && npm run lint && npm run typecheck && npm test &&
  npm run build` + `cd gui/src-tauri && cargo check` (codegen で generated.ts を touch するため)
- [ ] **Step 3: diff 規模判定** — PR 2 diff > ~1500 行なら 2a/2b 分割を AskUserQuestion
- [ ] **Step 4: PR 2 Pre-flight** — Step 0 → base develop 同期 → 交差 → Step 4 →
  Step 5 codex adversarial-review (focus: "released export path bit-same,
  metadata write-back field preservation, crop mod-2/clamp edge cases, GPU filter
  hwaccel interaction, Iron Law 3")
- [ ] **Step 5: PR 作成** — Self-Test Report (machine-verified `[x]` / unverifiable `-`)。
  **実機検証依頼を AskUserQuestion で Idios へ**: GPU crop encode (NVENC/QSV/AMF) +
  7h 動画クラスは detached Start-Process 手順を提示 (feedback_long_gpu_job_detached_execution)
- [ ] **Step 6**: `/iterate-review` で収束 → Idios に merge 依頼 → merge 後
  `/close-issue 481` は受け入れ条件実測後に別途

---

## Self-Review (2026-07-08、plan 執筆時)

1. **Spec coverage**: spec §3 (CLI/対象/座標系) = D2、§4 (構成) = D1/D2、§5 (schema) = F1、
   §6 (PoC) = P1-P5、§7 (出力) = D2、§8 (エラー) = D2 Step 1 テスト系統、§9 (テスト) =
   F1/F2/D1/D2/D3、§10 (実機検証) = D5 Step 5、§12 (docs) = D4。gap なし
2. **Placeholder scan**: PoC 閾値は「初期値 + 調整可」と明示 (PoC の deliverable は report)。
   D2 実装は export.py の実在 pattern への写像で全分岐を列挙済み
3. **Type consistency**: PoC (P2/P3) の候補 fn は 6-tuple (x,y,w,h,map_name,score)、
   production (D1) の `DetectResult` は checkpoint 縮小後の 5-tuple (x,y,w,h,score)。
   両形の境界は D1 port (`detect_areamap_seed`) で、P2/P3/D1 の各 Interfaces に注記済み。
   `MatchRegionResult.region` は `CaptureRegion` (#810 $defs) を再利用。
   `resolve_match_regions` の戻り値 (results, warnings) を D1 test / D2 実装で統一
