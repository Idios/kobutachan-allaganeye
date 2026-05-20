# v0.3.0 OBS baseline audit (#796)

> **Status**: complete (5/5 baselines audited)
> **Spec**: [docs/superpowers/specs/2026-05-19-v030-baseline-audit-design.md](superpowers/specs/2026-05-19-v030-baseline-audit-design.md)
> **PR #793 status**: draft (audit blocking)

## Cross-recording summary

### Totals (all 5 baselines, 52 boundaries)

| Category | Count |
| --- | --- |
| Agreed (within ±5s) | 49 |
| Silent miss | 0 |
| False positive | 0 |
| Boundary shift | 3 |
| **Total findings** | **3** |

### Findings classification

| Class | Count | Notes |
| --- | --- | --- |
| (a) baseline 修正 | 0 | — |
| (b) detector tuning | 3 | 2 件は [PR #793](https://github.com/Idios/kobutachan-allaganeye/pull/793) で fix される (F1 obs-20260116 M3 end + F4 obs-20260118 M2 end)、1 件は新規 [#797](https://github.com/Idios/kobutachan-allaganeye/issues/797) (obs-20260116 M6 end) |
| (c) 既知限界 | 0 | — |

### Decision input for #576 / PR #793 reexamination

- **PR #793 が cover する finding (2 件)** — PR #793 が ground truth に対して `tolerance_sec=5` 内に収束する見込み:
  - obs-20260116 M3 end: PR #793 後 `53:50` (3230.5) vs ground truth `53:47` (3227) → delta 3.5s, agreed
  - obs-20260118 M2 end: PR #793 後 `3926.7` (新 boundary `t=3925.3-3926.7`) vs ground truth `3926` → delta 0.7s, agreed
- **新規 finding (1 件)** — PR #793 で fix されない、別 detector tuning issue として起票する候補:
  - obs-20260116 M6 end: baseline `2:01:43.488` (7303.488s, `type: unknown`) vs ground truth `1:49:00` (6540s), delta -763.488s
- **audit 結論**: ground truth audit の結果、5 baseline 52 boundary のうち 49 は systematic visual verification で agreed、3 boundary_shift のうち 2 件は PR #793 fix、1 件は新規 tuning 対象
- **次のステップ**: PR #793 (#576 fps filter retirement) の merge / scope reduce / defer / abandon 判断は **別 brainstorming (reexamination spec)** で確定。本 audit はその input を揃えるところまで

## obs-20260116

- Source: `20260116/2026-01-16 22-12-57.mkv`
- Ground truth: 6 matches (Idios manual)
- Current baseline: 6 matches
- Tolerance: ±5s
- Findings: 0 silent_miss / 0 false_positive / 2 boundary_shift / 10 agreed

### Findings

| # | Type | Match | Boundary | Baseline ts | Ground truth ts | Delta | Classification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | boundary_shift | 3 | end | 3367.125 | 3227.000 | -140.125 | (b) — fix in [PR #793](https://github.com/Idios/kobutachan-allaganeye/pull/793) (#576) |
| 2 | boundary_shift | 6 | end | 7303.488 | 6540.000 | -763.488 | (b) — [#797](https://github.com/Idios/kobutachan-allaganeye/issues/797) |
| 3 | agreed | 1 | start | 49.125 | 49.000 | -0.125 | (agreed) |
| 4 | agreed | 1 | end | 1054.500 | 1054.000 | -0.500 | (agreed) |
| 5 | agreed | 2 | start | 1256.000 | 1256.000 | +0.000 | (agreed) |
| 6 | agreed | 2 | end | 2178.750 | 2178.000 | -0.750 | (agreed) |
| 7 | agreed | 3 | start | 2355.000 | 2355.000 | +0.000 | (agreed) |
| 8 | agreed | 4 | start | 3367.125 | 3367.000 | -0.125 | (agreed) |
| 9 | agreed | 4 | end | 4352.000 | 4352.000 | +0.000 | (agreed) |
| 10 | agreed | 5 | start | 4538.000 | 4538.000 | +0.000 | (agreed) |
| 11 | agreed | 5 | end | 5482.500 | 5482.000 | -0.500 | (agreed) |
| 12 | agreed | 6 | start | 5624.250 | 5624.000 | -0.250 | (agreed) |

### Discussion

**Finding #1 (M3 end, delta -140.125s)** — PR #793 で fix される F1 ケース

- 現 baseline (PR #793 前 legacy fps filter) は M3 end を `56:07` (= 3367.125s) と検出
- Idios 視覚確認: 試合終了暗転は `53:47` (= 3227s)、`56:07` は次試合 (M4) の開始
- これは PR #793 spec §journey の **F1** (`t=3227.4 の 3.6s blackout`、legacy fps filter が silent miss) と完全一致
- PR #793 (dual seek + A5 borderline extension) で M3 end = `53:50` (= 3230.5s、Idios の 3227 と差分 3.5s、tolerance_sec=5 内) と再検出される
- **分類: (b) detector tuning** — 修正は [PR #793](https://github.com/Idios/kobutachan-allaganeye/pull/793) (#576) で対応中
- 新規 issue 起票不要 (= 既存 PR が fix)

**Finding #2 (M6 end, delta -763.488s)** — 新規発見、PR #793 の言及外

- 現 baseline は M6 end を `2:01:43.488` (= 7303.488s、動画末尾) と検出、`type: unknown` 分類
- Idios 視覚確認: 試合終了暗転は `1:49:00` (= 6540s)
- 真の M6 = 5624 → 6540 (= 15m16s)、baseline は 27m59s と異常に長い → 動画末尾までの 12m44s non-match interval を試合内と誤分類
- PR #793 commit message には言及無し (F1-F4 のいずれにも該当しない)
- 仮説: 試合終了暗転 (6540s) が legacy fps filter で miss されている可能性 — PR #793 後の detector で再検知するか実機検証が必要 → 新規 issue の調査対象
- **分類: (b) detector tuning** — 新規 issue [#797](https://github.com/Idios/kobutachan-allaganeye/issues/797) として起票済 (P2-medium / refactor / l1-residual)

## obs-20260118

- Source: `20260118/2026-01-18 22-15-18.mkv`
- Ground truth: 5 matches (Idios manual)
- Current baseline: 5 matches
- Tolerance: ±5s
- Findings: 0 silent_miss / 0 false_positive / 1 boundary_shift / 9 agreed

### Findings

| # | Type | Match | Boundary | Baseline ts | Ground truth ts | Delta | Classification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | boundary_shift | 2 | end | 4195.750 | 3926.000 | -269.750 | (b) — fix in [PR #793](https://github.com/Idios/kobutachan-allaganeye/pull/793) (#576) |
| 2 | agreed | 1 | start | 177.250 | 177.000 | -0.250 | (agreed) |
| 3 | agreed | 1 | end | 2610.750 | 2610.000 | -0.750 | (agreed) |
| 4 | agreed | 2 | start | 2976.250 | 2976.000 | -0.250 | (agreed) |
| 5 | agreed | 3 | start | 4200.250 | 4200.000 | -0.250 | (agreed) |
| 6 | agreed | 3 | end | 5255.500 | 5255.000 | -0.500 | (agreed) |
| 7 | agreed | 4 | start | 5499.000 | 5499.000 | +0.000 | (agreed) |
| 8 | agreed | 4 | end | 6465.250 | 6465.000 | -0.250 | (agreed) |
| 9 | agreed | 5 | start | 7231.250 | 7231.000 | -0.250 | (agreed) |
| 10 | agreed | 5 | end | 8114.625 | 8114.000 | -0.625 | (agreed) |

### Discussion

**Finding #1 (M2 end, delta -269.750s)** — PR #793 で fix される F4 ケース

- 現 baseline (legacy) は M2 end を `01:09:55.750` (= 4195.750s) と検出 — 真の M3 start に当たる timestamp を誤って M2 end と分類
- Idios 視覚確認: M2 end (真) は `01:05:26` (= 3926s)、`01:09:55.750` は M3 start 近辺の境界
- これは PR #793 commit message の **F4** (`t=3925.3-3926.7` の 1.4s blackout、`brightness 1.6`、新 Match 3 end として新規検出) と完全一致
- PR #793 後の new baseline では M2 end = 3926.7 が新規 boundary として検出される (Idios の 3926 と差分 0.7s、tolerance_sec=5 内)
- **分類: (b) detector tuning** — 修正は [PR #793](https://github.com/Idios/kobutachan-allaganeye/pull/793) (#576) で対応中
- 新規 issue 起票不要

## obs-20260119

- Source: `20260119/2026-01-19 22-09-07.mkv`
- Ground truth: 9 matches (Idios manual)
- Current baseline: 9 matches
- Tolerance: ±5s
- Findings: 0 silent_miss / 0 false_positive / 0 boundary_shift / 18 agreed

全 18 boundary が agreed。`±5s` 内で baseline と ground truth が完全一致。

## obs-20260127

- Source: `20260127/2026-01-27 21-59-15.mkv`
- Ground truth: 3 matches (Idios manual)
- Current baseline: 3 matches
- Tolerance: ±5s
- Findings: 0 silent_miss / 0 false_positive / 0 boundary_shift / 6 agreed

全 6 boundary が agreed。

## obs-20260209

- Source: `2026-02-09 23-12-24.mkv`
- Ground truth: 3 matches (Idios manual)
- Current baseline: 3 matches
- Tolerance: ±5s
- Findings: 0 silent_miss / 0 false_positive / 0 boundary_shift / 6 agreed

全 6 boundary が agreed。

## Iteration 1 PoC retrospect (applied)

PoC で発見した workflow / script の改善点 (Iteration 1 終了時に fix 済):

1. **`PYTHONPATH=.` 不要化** ([2e2fd18](https://github.com/Idios/kobutachan-allaganeye/commit/2e2fd18)): 両 script が `sys.path` を自動設定するようになり、`python scripts/audit-prepare.py <label>` 単体で動作
2. **`PYTHONIOENCODING=utf-8` 不要化** ([2e2fd18](https://github.com/Idios/kobutachan-allaganeye/commit/2e2fd18)): `audit-compare.py` 内で `sys.stdout.reconfigure(encoding='utf-8')` を実行、Windows cp932 環境で `±` が文字化けしない
3. **`tolerance_sec` default 1 → 5** ([2e2fd18](https://github.com/Idios/kobutachan-allaganeye/commit/2e2fd18)): spec §3.2 を update、Idios の minute-level + 試合終了暗転の複数フレーム不確定性を踏まえた値
4. **adjacent boundary の PNG file overwriting** (未対応、低 impact): obs-20260116 M3 end (3367.125) と M4 start (3367.125) が同 timestamp で sample frame PNG が overwrite される (12 boundary → 11 unique = 1 件不足)。低 impact のため未対応、将来 (a/b/c) finding が発生した場合に script を見直す
