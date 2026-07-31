# VTuber timeline 分割検出 P3 (GT 拡充 + 精度 gate + hidden 解除) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Task 2/4 の目視裁定と Task 4/6 の AskUserQuestion checkpoint は controller (主セッション) が実施する** (subagent へ委譲しない)。

**Goal:** 6 source GT を整備して timeline 検出を ±15s 精度 gate + 共通パラメータ recall gate で検証し、snap 精度改善を data-driven で実施、性能退行実測と doc 同期を経て `--vtuber` hidden 解除判断に至る。

**Architecture:** GT は既存 `vtuber-primary-ground-truth.json` 形式を multi-source 化 (`tests/baselines/v0.3.0/vtuber-gt/<label>.json`)。突合は新 slow test (`tests/test_vtuber_gt_regression.py`) で matched/missed/spurious + 境界誤差を判定。精度改善は Task 3 の 6 source 測定結果を見て #895 P3 comments の候補から選択 (AskUserQuestion checkpoint)。

**Tech Stack:** Python 3.11+ / 既存 PoC スクリプト (`tests/scripts/poc_vtuber_timeline/`) / pytest slow markers / PowerShell detached 実行 (長時間 gate)。

> **Erratum (PR #915 review round 1)**: 本 plan 中の `_VTUBER_ALGO_VERSION` 値 (「現在 3 -> 4」等) は
> 起草当時の履歴記録であり、その後の review round で追加 bump された。**値の正は常に実装**
> (`allaganeye/commands/split_matches.py` の `_VTUBER_ALGO_VERSION` + pin test) 側にある。
> 同じく GT 試合数は実データで **67 試合** (gyawa 6 / kyuma 11 / meteor 14 / shikke 16 /
> shinryu 12 / shirurori 8) が正 (一部 doc にあった「76 試合」は誤記、同 round で訂正)。

## Global Constraints

- **共通パラメータ原則 (spec §2.1、R6)**: per-source チューニング禁止。6 source 全部を同一パラメータで通す。精度改善もパラメータ/ロジックは全 source 共通
- **GT 規約 (spec §3.2)**: zone-in 基準 (staging 開始 = 試合 start、リザルト終端/presence 崩壊 = end)。tolerance_sec は GT ファイルに明記
- **gate 値 (spec §3.2)**: gyawa 6 + きゅま 11 で matched/missed/spurious = 全/0/0 + 境界誤差 ≤ ±15s。残り 4 source は recall 100% / spurious 0 (境界 ±15s は 6 source 共通目標)。OBS bit-exact (Class A 4 + Class B 1) / masked 3 サンプル出力不変 / 非 VTuber 性能 wall-time ±10%
- **OBS/masked 非接触**: production 変更は `vtuber_timeline.py` (+ 必要なら `--vtuber` gate 内) のみ。検出ロジックを変えたら `_VTUBER_ALGO_VERSION` bump (現在 3 → 4) + 実機 gate 再実行 (feedback_detection_flag_cache_key / logic 変更は実動画 gate 必須)
- **GT/動画の保全**: 新 GT ファイルと参照動画は `tests/baselines/source-videos.sha256.json` 台帳に SHA-256 + size を追記 (docs/testing-guide.md §保全方針 #869)
- 長時間 job (detect ~10-20 分/本 ×6) は detached Start-Process + log + `--no-cache` + `ALLAGANEYE_INTEGRITY_SKIP=1` (feedback_long_gpu_job_detached_execution)
- cp932 非安全記号禁止 / lint 個別実行 (pipeline masking 注意) / コミットは task ごと + Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>

---

### Task 1: GT スキーマ multi-source 化 + 突合 harness (slow test)

**Files:**

- Create: `tests/baselines/v0.3.0/vtuber-gt/kyuma.json` (PoC report §7.2 の 11 試合を正式化)
- Create: `tests/baselines/v0.3.0/vtuber-gt/gyawa.json` (既存 primary GT の再注釈: 漏れ試合 260-1240 追加 + zone-in 基準化。既存 `vtuber-primary-ground-truth.json` は後方互換のため残置し、header comment で新ファイルへ誘導)
- Create: `tests/test_vtuber_gt_regression.py`
- Modify: `tests/baselines/source-videos.sha256.json` (きゅま VOD の SHA-256 + size 追記。gyawa は台帳済みか確認し、なければ追記)

**Interfaces:**

- Produces: GT JSON スキーマ (全 source 共通):

```json
{
  "source_file": "<ファイル名>",
  "source_size_bytes": 0,
  "source_dir_label": "vtuber-samples",
  "source_env_var": "ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER",
  "ground_truth_provider": "agent (PoC 2026-07-17 + P3 目視裁定)",
  "ground_truth_provided_at": "2026-07-20",
  "convention": "zone-in",
  "tolerance_sec": 15,
  "matches": [
    {"index": 1, "start_time": 0, "end_time": 0, "type": "fl_match"}
  ]
}
```

- Produces: `compare_detection_to_gt(detected: list[dict], gt_matches: list[dict], tolerance_sec: float) -> dict` (in `tests/test_vtuber_gt_regression.py`、pure) — returns `{"matched": N, "missed": [...], "spurious": [...], "boundary_errors": [(idx, ds, de), ...], "max_abs_error": float}`。matched 判定 = 区間 overlap 最大の 1:1 対応、境界誤差 = 対応 pair の |ds|/|de|

- [ ] **Step 1: Write the failing test**

```python
# tests/test_vtuber_gt_regression.py
"""VTuber timeline GT 突合 (P3, #895)。

GT ファイル (tests/baselines/v0.3.0/vtuber-gt/*.json) と `--vtuber` detect
出力を突合する。slow test は実 VOD 必須 (ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER)。
compare_detection_to_gt は pure なので unit でも検証する。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_GT_DIR = Path(__file__).parent / "baselines" / "v0.3.0" / "vtuber-gt"


def compare_detection_to_gt(
    detected: list[dict], gt_matches: list[dict], tolerance_sec: float
) -> dict:
    """検出 segment と GT の 1:1 突合 (overlap 最大対応)。"""
    unmatched_det = list(range(len(detected)))
    matched_pairs: list[tuple[int, int]] = []
    for gi, g in enumerate(gt_matches):
        best = None
        for di in unmatched_det:
            d = detected[di]
            ov = min(d["end_time"], g["end_time"]) - max(
                d["start_time"], g["start_time"]
            )
            if ov > 0 and (best is None or ov > best[1]):
                best = (di, ov)
        if best is not None:
            matched_pairs.append((gi, best[0]))
            unmatched_det.remove(best[0])
    missed = [
        g["index"]
        for gi, g in enumerate(gt_matches)
        if gi not in [p[0] for p in matched_pairs]
    ]
    spurious = [detected[di]["start_time"] for di in unmatched_det]
    errors = []
    for gi, di in matched_pairs:
        g, d = gt_matches[gi], detected[di]
        errors.append(
            (
                g["index"],
                d["start_time"] - g["start_time"],
                d["end_time"] - g["end_time"],
            )
        )
    max_abs = max((max(abs(ds), abs(de)) for _, ds, de in errors), default=0.0)
    return {
        "matched": len(matched_pairs),
        "missed": missed,
        "spurious": spurious,
        "boundary_errors": errors,
        "max_abs_error": max_abs,
    }


class TestCompareUnit:
    def test_exact_match(self):
        det = [{"start_time": 100.0, "end_time": 500.0}]
        gt = [{"index": 1, "start_time": 100.0, "end_time": 500.0}]
        r = compare_detection_to_gt(det, gt, 15.0)
        assert r["matched"] == 1 and not r["missed"] and not r["spurious"]
        assert r["max_abs_error"] == 0.0

    def test_missed_and_spurious(self):
        det = [{"start_time": 2000.0, "end_time": 2400.0}]
        gt = [{"index": 1, "start_time": 100.0, "end_time": 500.0}]
        r = compare_detection_to_gt(det, gt, 15.0)
        assert r["missed"] == [1] and len(r["spurious"]) == 1

    def test_boundary_error_signs(self):
        det = [{"start_time": 90.0, "end_time": 520.0}]
        gt = [{"index": 1, "start_time": 100.0, "end_time": 500.0}]
        r = compare_detection_to_gt(det, gt, 15.0)
        (_, ds, de) = r["boundary_errors"][0]
        assert ds == -10.0 and de == 20.0

    def test_one_to_one_matching(self):
        # 1 検出が 2 GT を二重 match しない
        det = [{"start_time": 100.0, "end_time": 900.0}]
        gt = [
            {"index": 1, "start_time": 100.0, "end_time": 400.0},
            {"index": 2, "start_time": 500.0, "end_time": 900.0},
        ]
        r = compare_detection_to_gt(det, gt, 15.0)
        assert r["matched"] == 1 and len(r["missed"]) == 1


def _gt_files():
    return sorted(_GT_DIR.glob("*.json")) if _GT_DIR.exists() else []


@pytest.mark.slow
@pytest.mark.slow_detect
@pytest.mark.parametrize("gt_path", _gt_files(), ids=lambda p: p.stem)
def test_vtuber_gt_match(gt_path, tmp_path):
    """実 VOD で --vtuber detect し GT と突合 (matched/missed/spurious + 境界誤差)。"""
    gt = json.loads(gt_path.read_text(encoding="utf-8"))
    base = Path(
        os.environ.get("ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER", "E:/allaganeye-samples")
    )
    video = (
        base / gt["source_file"]
        if gt.get("source_dir_label") == "vtuber-samples"
        else None
    )
    if gt.get("source_dir_label") == "gyawa_vatos":
        video = Path("E:/videos/gyawa_vatos") / gt["source_file"]
    if video is None or not video.exists():
        pytest.skip(f"sample video not found: {gt['source_file']}")
    out = tmp_path / gt_path.stem
    env = {**os.environ, "PYTHONUTF8": "1", "ALLAGANEYE_INTEGRITY_SKIP": "1"}
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "allaganeye",
            "detect",
            str(video),
            "--vtuber",
            "--no-cache",
            "-o",
            str(out),
        ],
        capture_output=True,
        text=True,
        timeout=3600,
        env=env,
    )
    assert r.returncode == 0, r.stderr[-2000:]
    meta = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
    result = compare_detection_to_gt(
        meta["matches"], gt["matches"], gt["tolerance_sec"]
    )
    assert result["matched"] == len(gt["matches"]), result
    assert not result["missed"] and not result["spurious"], result
    assert result["max_abs_error"] <= gt["tolerance_sec"], result["boundary_errors"]
```

- [ ] **Step 2: Run unit part to verify** — `PYTHONUTF8=1 python -m pytest tests/test_vtuber_gt_regression.py::TestCompareUnit -v` → 4 passed (pure 関数は先に GREEN、slow 側は GT ファイル作成後に collect される)
- [ ] **Step 3: きゅま GT 正式化** — `tests/baselines/v0.3.0/vtuber-gt/kyuma.json` を作成。matches は PoC report §7.2 の 11 区間だが、**P2 gate r2 実測 (`E:/allaganeye-samples/_p2_gate/kyuma_r2/metadata.json`) と PoC dense 計測に基づき zone-in 基準へ精緻化する** (例: M1 start は PoC の 45 ± 目視、M5 end は 5710 (振り返り除外)、M8 end は 9710 (queue 除外))。controller が dense CSV (`_poc_vtuber_retry/`) を参照して数値確定し、曖昧 boundary は contact sheet で目視裁定。tolerance_sec: 15
- [ ] **Step 4: gyawa GT 再注釈** — `vtuber-gt/gyawa.json`: 既存 5 試合 + 漏れ試合 (260-1240 目視確認済み) を zone-in 基準で。dense w1/w2 計測 (M2 zone-in blackout ~2620 等) を根拠に確定。`source_dir_label: "gyawa_vatos"`
- [ ] **Step 5: SHA-256 台帳追記** — きゅま/gyawa VOD の SHA-256 + size を `tests/baselines/source-videos.sha256.json` に追記 (既登録は skip)。PowerShell: `Get-FileHash -Algorithm SHA256`
- [ ] **Step 6: Lint + commit**

```bash
python -m ruff check .
python -m ruff format --check .
python -m pyright
PYTHONUTF8=1 python -m pytest tests/test_vtuber_gt_regression.py::TestCompareUnit -q
git add tests/test_vtuber_gt_regression.py tests/baselines/
git commit -m "feat(l3): VTuber GT 突合 harness + きゅま/gyawa 正式 GT (zone-in 基準) (Refs #895)"
```

---

### Task 2: 残り 4 source の境界 GT 注釈 (controller 主導)

**Files:**

- Create: `tests/baselines/v0.3.0/vtuber-gt/{shirurori,meteor,shinryu,shikke}.json`
- Modify: `tests/baselines/source-videos.sha256.json` (4 VOD 追記)

**Interfaces:**

- Consumes: PoC 資産 (`E:/allaganeye-samples/_poc_vtuber_retry/<label>_full_atanchor_10s.csv` + rule B segments) / `tests/scripts/poc_vtuber_timeline/contact_sheet.py` / `dense_window.py`
- Produces: 4 GT JSON (Task 1 スキーマ、`source_dir_label: "vtuber-samples"`)

手順 (per source、PoC report §7.2 のコンタクトシート法):

- [ ] **Step 1**: PoC の rule B segments (シルロリ 7 / メテオ 14 / Shinryu 12 / 湿気 16) を候補とし、各境界 gap の contact sheet (60s stride) + 必要に応じ dense probe を生成
- [ ] **Step 2**: controller が目視裁定 — 特に要確認: シルロリの 34.7min segment (2 試合マージ or 長コンテンツ) / メテオの 5.5-7min 短 segment (途中参加 or 非試合) / 各 source の振り返り・非 FL content の有無 (きゅま §7.4 の replay 類)
- [ ] **Step 3**: 確定した matches で GT JSON 4 本を作成 (tolerance_sec 15。目視裁定で ±15s を確定できない boundary は dense probe (1s) で presence 崩壊/回復点を実測して確定)
- [ ] **Step 4**: SHA-256 台帳追記 (4 VOD)
- [ ] **Step 5: Commit** — `feat(l3): 残り 4 source の境界 GT 注釈 (Refs #895)`

---

### Task 3: 6 source 一斉測定 (現行 P2 コード)

**Files:** なし (測定のみ。結果は `.superpowers/sdd/p3-measurement.md` に記録)

- [ ] **Step 1**: 6 source を detached で順次 `--vtuber --no-cache` detect (`E:/allaganeye-samples/_p3_gate/<label>/`)。きゅま/gyawa は P2 gate r2 出力を再利用可 (コード不変なら)
- [ ] **Step 2**: 各 source の metadata.json を GT と突合 (`compare_detection_to_gt` を script 実行) し、per-source per-boundary の誤差表を作成
- [ ] **Step 3**: 結果を分類: (a) 全 gate PASS → Task 4 skip 判断へ (b) 境界誤差 > ±15s のみ → snap 改善候補の適用範囲を確定 (c) missed/spurious あり → 裁定ロジック known-risk (リスポーン暗転 veto / edge probe バイアス) の該当を分析
- [ ] **Step 4 (controller)**: **AskUserQuestion checkpoint** — 測定結果 + 改善候補 (#895 P3 comments の 6 点: frozen-probe 除外 / adjacency N 秒制限 / long-gap 窓交差 / リスポーン暗転 min run / edge probe 除外 / progress 表示) から実施セットを Idios と確定

---

### Task 4: 精度改善 (data-driven、Task 3 checkpoint の決定に従う)

**Files:**

- Modify: `allaganeye/video/vtuber_timeline.py` (承認された改善のみ)
- Modify: `allaganeye/commands/split_matches.py` (`_VTUBER_ALGO_VERSION` 3 → 4、検出出力が変わる場合のみ)
- Test: `tests/test_vtuber_timeline.py` (改善ごとに unit + 境界ケース)

改善候補の実装草案 (checkpoint で採否決定。採用分のみ実装):

1. **snap frozen-probe 除外**: `snap_segment_edges` の presence run 走査で `band_mad < FROZEN_MAX` の probe を present 扱いしない (frozen-present = result/replay を試合に含めない)。きゅま #5 の +83s 解消見込み
2. **blackout snap の隣接 N 秒制限**: 「run より前/後に present」条件を「run エッジから 30s 以内に present」へ強化。きゅま #8 の +229s (queue 跨ぎ) 解消見込み
3. **リスポーン暗転 min run**: `adjudicate_gap` の blackout marker に最小連続長 (例 3 probes = 3s 超のみ marker) — Task 3 で該当事例が出た場合のみ
4. **edge probe 除外**: `probe_gap` の先頭 probe (= prev segment 末尾) を rate 分母から除外 — 同上

- [ ] **Step 1**: 採用改善ごとに TDD (RED: 合成系列で現行の誤差を再現する test → GREEN)
- [ ] **Step 2**: `_VTUBER_ALGO_VERSION` bump (検出出力変更時) + version pin test 更新
- [ ] **Step 3**: フルスイート + lint
- [ ] **Step 4**: 6 source 再測定 (Task 3 と同手順、`_p3_gate_r2/`) → **全 gate PASS を確認** (未達なら Task 3 Step 4 に戻る。2 周で未達なら発散として Idios へ)
- [ ] **Step 5: Commit** — `feat(l3): snap/裁定の精度改善 (6 source ±15s gate) (Refs #895)`

---

### Task 5: 実機 gate 一式 (回帰 + 性能)

**Files:** なし (検証のみ、結果は PR body Self-Test へ)

- [ ] **Step 1: OBS bit-exact** (detached): `pytest tests/test_v030_baseline_regression.py::test_class_a_bit_exact tests/test_v030_baseline_regression.py::test_class_b_regenerated -m slow -v` → 5/5 PASSED
- [ ] **Step 2: masked 3 サンプル出力不変**: `$ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER/20250527-29/20250527-29/` の MKV 3 本を head で `--masked --no-cache` detect し、**merge-base (P3 適用前 = f10457b) で同条件 detect した出力と matches[] が一致**することを確認 (双方 detached、boundaries JSON 比較 script)
- [ ] **Step 3: 非 VTuber 性能退行実測**: OBS baseline 1 本 (obs-20260209 = 57min、最小) を **pre-timeline commit (41655d7 = spec merge 直後、timeline 未導入) と P3 head** でそれぞれ flag なし `--no-cache` detect し、wall-time を 2 回ずつ計測 → 平均差 ±10% 以内を確認 (spec §3.2「経路非接触だからゼロ影響のはず」を無検証にしない)。checkout は一時 worktree (`git worktree add`) で行い、計測後に削除
- [ ] **Step 4: 6 source GT gate (最終)**: Task 4 Step 4 の結果を正とする (コード変更がなければ再実行不要)。`pytest tests/test_vtuber_gt_regression.py -m slow_detect -v` が全 6 source PASS することを確認 (detached、~1-2h)

---

### Task 6: hidden 解除判断 + doc 同期 + PR

**Files:**

- Modify: `allaganeye/cli.py` (`--vtuber` の hidden 解除 + help 文言 — **Idios 承認時のみ**)
- Modify: `docs/cli-spec.md` / `docs/output-spec.md` / `docs/detection-map.md` / `CLAUDE.md` / `docs/design-overview.md` (timeline 検出の記述同期)
- Modify: `docs/superpowers/specs/2026-07-17-vtuber-timeline-detection-design.md` (P3 実測値の erratum/追記があれば)

- [ ] **Step 1 (controller)**: **AskUserQuestion** — 全 gate 結果を提示し `--vtuber` hidden 解除 (help 表示化) の可否を Idios 判断。解除時は help 文言も確定 (現行の「Under-detects」注記を削除し timeline 検出の説明へ)
- [ ] **Step 2: doc 同期** — 各 doc の `--vtuber` / VTuber 記述を timeline 検出 (V0-V4) に更新: CLAUDE.md モジュール表に `video/vtuber_timeline.py` 行追加 / detection-map の VTuber フロー更新 / cli-spec・output-spec の `--vtuber` 挙動 (縮退 3 trigger / verbose 統計 / 進捗 2 周) 記載 / design-overview の L3 行更新
- [ ] **Step 3**: markdownlint + フルスイート + lint 一式
- [ ] **Step 4: PR 作成** — Pre-flight Step 0-4 → PR (base develop-0.3.0) → Self-Test Report (Task 5 の全実測値) → `/iterate-review` 自走。**#895 の全 checkbox 消化後、merge を経て `/close-issue 895` へ handoff** (受け入れ条件のマージ後実測再検証 → Idios 承認 → close)

---

## Self-Review 記録

- 引数 scope ①〜⑤ の被覆: ① = Task 1/2、② = Task 3、③ = Task 4 (checkpoint 付き)、④ = Task 5、⑤ = Task 6。全項目に task あり
- data-driven 部 (Task 4) は候補 4 種の実装草案 + 採否 checkpoint + 再測定 loop (2 周 cap) で「TBD」を回避しつつ先回り実装を防ぐ (R6)
- 型整合: `compare_detection_to_gt` の返り値 dict は Task 3/5 の測定 script と Task 1 の slow test で共用
- GT tolerance 15s は gate 値と同値。GT 注釈自体の精度が ±15s を下回れない boundary は dense probe 実測で確定する手順を Task 2 Step 3 に明記
- 実機 gate の long-run はすべて detached + log 手順 (Global Constraints) に従う
