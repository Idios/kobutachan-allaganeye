# v0.3.0 OBS baseline audit (#796)

> **Status**: Iteration 1 / 5 (obs-20260116 PoC)
> **Spec**: [docs/superpowers/specs/2026-05-19-v030-baseline-audit-design.md](superpowers/specs/2026-05-19-v030-baseline-audit-design.md)
> **PR #793 status**: draft (audit blocking)

## Cross-recording summary

(filled after all 5 baselines audited — Task 16)

## obs-20260116

- Source: `20260116/2026-01-16 22-12-57.mkv`
- Ground truth: 6 matches (Idios manual)
- Current baseline: 6 matches
- Tolerance: ±5s
- Findings: 0 silent_miss / 0 false_positive / 2 boundary_shift / 10 agreed

### Findings

| # | Type | Match | Boundary | Baseline ts | Ground truth ts | Delta | Classification |
|---|---|---|---|---|---|---|---|
| 1 | boundary_shift | 3 | end | 3367.125 | 3227.000 | -140.125 | (b) — fix in [PR #793](https://github.com/Idios/kobutachan-allaganeye/pull/793) (#576) |
| 2 | boundary_shift | 6 | end | 7303.488 | 6540.000 | -763.488 | (b) — new tuning issue (TBD) |
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
- 仮説: 試合終了暗転 (6540s) が legacy fps filter で miss されている可能性 — PR #793 後の detector で再検知するか実機検証が必要
- **分類: (b) detector tuning** — 新規 issue 起票候補 (Iteration 2 完了後の Task 17 で起票判断)

## Iteration 1 PoC retrospect (= Task 13 candidate)

PoC で発見した workflow / script の改善点:

1. **`PYTHONPATH=.` 必要**: `python scripts/audit-prepare.py` 単体実行で `allaganeye` package が見つからない (script 起動時 `sys.path[0] = scripts/`)。spec / plan / script 内 docstring に `PYTHONPATH=.` の note を追加する必要
2. **`PYTHONIOENCODING=utf-8` 必要**: `audit-compare.py` の stdout に含む `±` 文字が Windows cp932 で文字化け (`�}5s`)。`scripts/audit-compare.py` 内で `sys.stdout.reconfigure(encoding='utf-8')` を追加する候補
3. **spec §3.2 tolerance_sec の現実値**: spec で `tolerance_sec=1` と定めたが、Idios の minute-level 報告 (秒精度) + 試合終了暗転の複数フレーム不確定性で実値 `5` が妥当。spec を update する
4. **adjacent boundary の PNG file overwriting**: M3 end (3367.125) と M4 start (3367.125) が同 timestamp で sample frame PNG が overwrite される (12 boundary → 11 unique = 1 件不足)。重複時の handling を script に追加するかどうか (低 impact、Task 13 で判断)
