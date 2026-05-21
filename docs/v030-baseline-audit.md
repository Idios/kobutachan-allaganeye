# v0.3.0 OBS baseline audit (#796)

> **Status**: complete (5/5 baselines audited); PR #793 verification update appended 2026-05-21 (§PR #793 verification update)
> **Spec**: [docs/superpowers/specs/2026-05-19-v030-baseline-audit-design.md](superpowers/specs/2026-05-19-v030-baseline-audit-design.md)
> **Reexamination spec**: [docs/superpowers/specs/2026-05-19-v030-l3-detect-fps-retirement-reexamination-design.md](superpowers/specs/2026-05-19-v030-l3-detect-fps-retirement-reexamination-design.md) §9
> **PR #793 status**: in-progress on `claude/recursing-lewin-4c5f9c` (reexamination spec §9 の (D) scope を実施中、本 doc §PR #793 verification update も参照)

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
| (b) detector tuning | 3 | 2 件は [PR #793](https://github.com/Idios/kobutachan-allaganeye/pull/793) で対応中 (F1 obs-20260116 M3 end + F4 obs-20260118 M2 end、merge 後の実機検証は reexamination spec で確定)、1 件は新規 [#797](https://github.com/Idios/kobutachan-allaganeye/issues/797) (obs-20260116 M6 end、PR #793 言及外) |
| (c) 既知限界 | 0 | — |

### Decision input for #576 / PR #793 reexamination

本 audit が branch-local に確定した事実:

- **baseline と ground truth の boundary 別 diff** — 5 baseline 52 boundary に対して上記 §obs-* sections に boundary 単位で記録
- **3 boundary_shift の所在** — obs-20260116 M3 end (-140.125s)、obs-20260116 M6 end (-763.488s)、obs-20260118 M2 end (-269.750s)
- **3 boundary_shift の PR #793 言及状況** (PR #793 の commit message を参照した結果): obs-20260116 M3 end は F1 として、obs-20260118 M2 end は F4 として明示的に扱われている。obs-20260116 M6 end は PR #793 commit message に言及無し
- **新規 issue [#797](https://github.com/Idios/kobutachan-allaganeye/issues/797) 起票** — obs-20260116 M6 end (PR #793 で言及無し) を detector tuning 対象として独立した issue として記録済

reexamination spec で確定する判断点 (本 audit の scope 外):

- PR #793 merge 後の baseline regenerate で M3 end / M2 end が ground truth に対して `tolerance_sec=5` 内に収束するかの実機検証
- obs-20260116 M6 end が PR #793 後の detector でも残るか、解消するかの実機検証 ([#797](https://github.com/Idios/kobutachan-allaganeye/issues/797) で扱う)
- PR #793 (#576 fps filter retirement) の merge / scope reduce / defer / abandon 判断

本 audit はその input を揃えるところまでで、merge 判断や post-fix timestamp の projection は別 brainstorming で扱う。

## 2026-05-21 PR #793 verification update

PR #793 (`claude/recursing-lewin-4c5f9c`) で regenerate された baseline (obs-20260116 / obs-20260118) を
`scripts/audit-compare.py` で更新後の ground truth と直接比較。Idios の追加視覚確認 (2026-05-21) で
obs-20260118 の ground truth を 5→6 matches に修正。詳細経緯は
[reexamination spec](superpowers/specs/2026-05-19-v030-l3-detect-fps-retirement-reexamination-design.md)
§9 参照。

### Ground truth 修正

| File | 変更前 | 変更後 | 理由 |
| --- | --- | --- | --- |
| `tests/baselines/v0.3.0/ground-truth/obs-20260118.json` | 5 matches (M1 = 177-2610 単一) | 6 matches (M1 = 177-1221 + M2 = 1686-2610) | PR #793 detector が 1221-1686 間に新規 boundary を検出 (legacy / 初回 GT は miss)。Idios 視覚再確認 (2026-05-21) で real boundary 確定 |

obs-20260116 / 20260119 / 20260127 / 20260209 の ground truth は変更無し。

### Audit-compare results (PR #793 baseline, 2026-05-21)

#### obs-20260118 (PR #793 detector 出力 vs 修正後 6-match GT)

| Category | Count |
| --- | --- |
| Agreed (within ±5s) | 12 |
| Silent miss | 0 |
| False positive | 0 |
| Boundary shift | 0 |

全 12 boundary が agreed。PR #793 detector は更新後の ground truth と完全整合。F4 (legacy M2 end -269.75s)
と 新規 M1/M2 split が両方 fix。

#### obs-20260116 (PR #793 detector 出力 vs GT)

| Category | Count |
| --- | --- |
| Agreed (within ±5s) | 11 |
| Silent miss | 0 |
| False positive | 0 |
| Boundary shift | 1 |

| # | Type | Match | Boundary | Baseline ts | Ground truth ts | Delta | Classification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | boundary_shift | 6 | end | 7303.488 | 6540.000 | -763.488 | (b) — V6 として PR #793 内 fix scope に統合 |
| 2 | agreed | 1 | start | 49.125 | 49.000 | -0.125 | (agreed) |
| 3 | agreed | 1 | end | 1054.500 | 1054.000 | -0.500 | (agreed) |
| 4 | agreed | 2 | start | 1256.000 | 1256.000 | +0.000 | (agreed) |
| 5 | agreed | 2 | end | 2178.750 | 2178.000 | -0.750 | (agreed) |
| 6 | agreed | 3 | start | 2355.000 | 2355.000 | +0.000 | (agreed) |
| 7 | agreed | 3 | end | 3230.500 | 3227.000 | -3.500 | (agreed) F1 FIXED |
| 8 | agreed | 4 | start | 3365.000 | 3367.000 | +2.000 | (agreed) M3/M4 境界 disambiguation |
| 9 | agreed | 4 | end | 4352.000 | 4352.000 | +0.000 | (agreed) |
| 10 | agreed | 5 | start | 4538.000 | 4538.000 | +0.000 | (agreed) |
| 11 | agreed | 5 | end | 5482.500 | 5482.000 | -0.500 | (agreed) |
| 12 | agreed | 6 | start | 5624.250 | 5624.000 | -0.250 | (agreed) |

F1 (M3 end) fix 済、**#797 (M6 end -763.488s) は未解消**で V6 として PR #793 scope 内対応。

### Updated cross-recording summary (post-PR #793 verification, partial)

| Recording | Baseline | GT matches | Findings | Status |
| --- | --- | --- | --- | --- |
| obs-20260116 | PR #793 detector | 6 | 1 boundary_shift (M6 end #797) | V6 で対応中 |
| obs-20260118 | PR #793 detector | 6 (updated) | 0 | ✓ |
| obs-20260119 | legacy (未 regenerate) | 9 | 0 | △ V3 で再検証予定 |
| obs-20260127 | legacy (未 regenerate) | 3 | 0 | △ V3 で再検証予定 |
| obs-20260209 | legacy (未 regenerate) | 3 | 0 | △ V3 で再検証予定 |

### Findings classification (updated 2026-05-21)

| Class | Count | Notes |
| --- | --- | --- |
| (a) ground truth 修正 | 1 | obs-20260118 GT を 5→6 matches に修正 (PR #793 detection 経由で発見、Idios 視覚再確認 2026-05-21 で確定) |
| (b) detector tuning | 1 | #797 (obs-20260116 M6 end miss、PR #793 でも legacy と同じ値) — V6 として PR #793 内 fix |
| (c) 既知限界 | 0 | — |

2026-05-20 audit の (b) detector tuning 3 件のうち F1 / F4 は PR #793 で fix 完了確認。#797 のみ V6 scope で対応継続。

### Legacy baseline vs 修正後 GT (参考)

obs-20260118 GT 5→6 matches 修正の結果、legacy detector に対する findings は以下に変化:

- 修正前 (5-match GT): 1 boundary_shift (M2 end -269.75s)
- 修正後 (6-match GT): 1 silent_miss (新 M2 1686-2610 全体を legacy は検出していない) + 1 boundary_shift (M2 end -269.75s)

→ legacy は obs-20260118 で **boundary 2 件取りこぼし** (元の表記より 1 件多い)。PR #793 で両方 fix。

## obs-20260116

- Source: `20260116/2026-01-16 22-12-57.mkv`
- Ground truth: 6 matches (Idios manual)
- Current baseline: 6 matches
- Tolerance: ±5s
- Findings: 0 silent_miss / 0 false_positive / 2 boundary_shift / 10 agreed

### Findings

| # | Type | Match | Boundary | Baseline ts | Ground truth ts | Delta | Classification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | boundary_shift | 3 | end | 3367.125 | 3227.000 | -140.125 | (b) — 対応中 [PR #793](https://github.com/Idios/kobutachan-allaganeye/pull/793) (#576) |
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

**Finding #1 (M3 end, delta -140.125s)** — PR #793 で扱われている F1 ケース

- 現 baseline (PR #793 前 legacy fps filter) は M3 end を `56:07` (= 3367.125s) と検出
- Idios 視覚確認: 試合終了暗転は `53:47` (= 3227s)、`56:07` は次試合 (M4) の開始
- PR #793 spec §journey の **F1** (`t=3227.4 の 3.6s blackout`、legacy fps filter が silent miss) として明示的に扱われており、PR #793 の commit message にも該当 fix の言及あり
- **分類: (b) detector tuning** — 修正対応は [PR #793](https://github.com/Idios/kobutachan-allaganeye/pull/793) (#576) として既に存在
- 新規 issue 起票不要 (= 既存 PR が対応中)。merge 後の実機検証で ground truth `±5s` 内に収束するかは reexamination spec で確定

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
| 1 | boundary_shift | 2 | end | 4195.750 | 3926.000 | -269.750 | (b) — 対応中 [PR #793](https://github.com/Idios/kobutachan-allaganeye/pull/793) (#576) |
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

**Finding #1 (M2 end, delta -269.750s)** — PR #793 で扱われている F4 ケース

- 現 baseline (legacy) は M2 end を `01:09:55.750` (= 4195.750s) と検出 — 真の M3 start 近辺の timestamp を誤って M2 end と分類
- Idios 視覚確認: M2 end (真) は `01:05:26` (= 3926s)、`01:09:55.750` は M3 start 近辺の境界
- PR #793 commit message の **F4** (`t=3925.3-3926.7` の 1.4s blackout、`brightness 1.6`、新 Match 3 end として新規検出) として明示的に扱われている
- **分類: (b) detector tuning** — 修正対応は [PR #793](https://github.com/Idios/kobutachan-allaganeye/pull/793) (#576) として既に存在
- 新規 issue 起票不要 (= 既存 PR が対応中)。merge 後の実機検証で ground truth `±5s` 内に収束するかは reexamination spec で確定

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

## Codex round 3 follow-up (Issue #798, applied 2026-05-20)

PR #799 merge 後の Codex Round 3 finding 2 件を Issue #798 で消化:

1. **R3#1 source_size validation tightening** — `_REQUIRED_GROUND_TRUTH_FIELDS` に `source_size_bytes` を追加し REQUIRED 化。`audit-compare.py` main は video 未解決時に exit 3 で fail-close、operator escape は `--skip-source-size-check` flag 経由 (stderr に WARNING)。`validate_ground_truth_against_baseline` に `skip_source_size_check` parameter 追加
2. **R3#2 atomic re-run** — `audit-prepare.main()` を `<label>.new/` + `<label>.csv.new` 経由の atomic flow に書き直し。mid-run failure 時は旧 artifacts intact、success 時に rename / replace で swap、前 run crash 由来の stale `.new` も次 run の pre-cleanup で recover

### Known limitation (Issue #800) — RESOLVED 2026-05-21

`audit-prepare.main()` の step (3) atomic swap には 3-op (rmtree + rename + replace) で構成された crash window があったが、Issue #800 で `<label>.tx.json` sidecar (tx-state) を導入して検出 + 次 run auto-recover を実装した。

- W1 (`rmtree` 後 / `rename` 前) と W2 (`rename` 後 / `replace` 前) は次 `audit-prepare` 実行時に `state == "swapping"` が読み取られ、artifacts を全消去してから regenerate する
- tx-state 自身は `.tx.json.new` 経由の `os.replace` で single-file atomic 書き込み
- backwards-compat: tx.json 不在 (legacy baseline) / "consistent" は recovery skip

詳細仕様は `docs/superpowers/specs/2026-05-20-audit-prepare-tx-recovery-design.md`、実装は [PR #802](https://github.com/Idios/kobutachan-allaganeye/pull/802)。

なお Iteration 1 retrospect item 4 の "adjacent boundary PNG overwriting" は本 follow-up の scope 外 (低 impact + Iron Law 3 scope 維持、Issue #798 §7 out of scope 明記)。
