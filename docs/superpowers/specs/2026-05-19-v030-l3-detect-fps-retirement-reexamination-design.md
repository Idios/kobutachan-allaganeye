# v0.3.0 #576 ship 判断 + v0.3.x perf 最適化 design

**Date:** 2026-05-19
**Author:** Claude (with Codex `codex:codex-rescue` adversarial second-opinion)
**Related:** #576, PR #793, `docs/superpowers/specs/2026-05-18-v030-l3-detect-fps-filter-retirement-design.md`
**Status:** approved direction → v0.3.0 ship PR #793 as-is, v0.3.x perf optimization issues to be filed

## 0. 目的

PR #793 (`claude/recursing-lewin-4c5f9c`、29 commits / +7227 -1281 / 23 files) で実装された
#576 (ffmpeg `-vf fps=N` filter retirement) について、**accuracy zero regression と引き換えに
+1.7x perf cost (52 min vs legacy 31 min) が発生した最終状態**を踏まえ、ゼロベースで
再検討する。v0.3.0 ship 可否と、v0.3.x で取り組む後続作業を確定する。

本 doc は brainstorming skill から起動し、Codex の adversarial second-opinion を統合した
3-axis 評価 (trade-off 妥当性 / 代替アプローチ / ship 可否) の決定記録である。実装手順は
本 doc から派生する v0.3.x 用の別 spec / plan で扱う。

## 1. Journey 現在地 (要約)

1. **初期実装** (output seek 単独 + `select='not(mod(n,N))'`): 10x 遅延 (67 min vs legacy 31 min)。32 chunk
   それぞれが t=0 から chunk 末尾まで decode する duplicate decode が原因。
2. **Codex rescue Option 1 (commit `a864834`):** dual seek (`-ss <chunk_start - 5>` BEFORE `-i` +
   `-ss 5` AFTER `-i`)。container index jump + accurate chunk_start を両立し、~31 min legacy 同等に復帰。
3. **Accuracy regression 発見:** obs-20260116 t=2178 = 実試合境界 (Idios 視覚確認済)。実 blackout window は
   t=2175.7-2177.3 (~1.6s)、Pass 1 3s sample interval の谷に落ち、Pass 1 値=42.6 (transition 途中)
   が **A3 borderline 旧範囲 `[blackout_threshold=15, blackout_threshold*2=30)` の外側**で取りこぼし。
4. **A5 fix (commit `03e13f0`):** A3 borderline upper bound を `blackout_threshold * 2 = 30` →
   `_TRANSITION_THRESHOLD = 55` に拡張。Pass 2 refinement (0.25s) を活性化、accuracy regression zero へ。
5. **最終 cost:** 52 min (RTX 5090、5 OBS baseline 合計)、legacy 31 min から **+68% (1.7x slower)**。

## 2. 3-axis 再検討

### 2.1 Trade-off 妥当性 (perf vs accuracy)

**事実関係:**

- Legacy ~31 min vs 現状 ~52 min = **+21 min / +68%**
- Accuracy regression zero (obs-20260116 / 118 / 119 / 219 / 216 = 5 baseline)
- A5 救済の具体例:
  - **obs-20260116 t=2175.7-2177.3** (Idios 視覚確認済の実試合境界、~1.6s blackout)
- (Codex の追加指摘) 旧 fps filter path は **obs-20260116 t=3227.4 の 3.6s blackout も見逃していた** —
  これは spec の root-cause 調査 finding。「legacy parity に戻る」≠「正解状態に戻る」。

**評価:**

- 利用シナリオは「長時間録画を unattended batch 処理 → 試合 inventory 化」。
- Boundary silent miss は inventory 破損 = 手動再 detect / 編集 cost であり、+21 min wall time より高コスト。
- Codex 評価: *"correctness beats wall time if detection is usually unattended"* に整合。
- **結論:** trade-off は accept できる。

### 2.2 代替アプローチ評価

| 案 | v0.3.0 短期で採用可能か | Codex 評価 |
| --- | --- | --- |
| (a) Version-detect fps filter (known-good ffmpeg のみ filter 使用) | ❌ legacy も miss あり (obs-20260116 t=3227.4) | reject |
| (b) Packet PTS parsing (`ffprobe -show_packets`) | ❌ timing 情報のみで brightness 検知の代替不可 | reject |
| (c) Gradient-based adaptive sampling | ❌ 新アルゴリズム = 新 failure mode | v0.3.x defer |
| (d) Sub-interval interpolation (A5 をより narrow に) | △ "transition 中の sample のみ" 等の限定。t=2178 の 42.6 を救う evidence が要る | v0.3.x 検討余地 |
| (e) Revert A5 only (dual seek だけ ship) | ❌ obs-20260116 t=2175.7-2177.3 が silently miss | reject |

**結論:** v0.3.0 timeframe で `dual seek + select + A5` を超える短期案は存在しない。`(c) gradient-based`
は v0.3.x の本命だが現時点では選択肢ではない。

### 2.3 v0.3.0 ship 可否

- CHANGELOG `## [Unreleased]` で trade-off 明示済、spec §7.4 perf gate を 60 min/合計に revise 済。
- accuracy regression zero、5 baseline pass。
- 実機検証は PR review で AMD APU 等 vendor 確認 (Iron Law 6 経路)。
- Codex 推奨: **Ship as-is**。

## 3. Codex 評価のサマリ

Codex (`codex:codex-rescue` agent) の adversarial second-opinion 主旨:

1. **Trade-off:** 利用シナリオが unattended batch ならば +1.7x perf は painful but justified。
2. **代替案:** version-detect は legacy も broken なので不成立。packet PTS は brightness 検知の代替にならない。
   Gradient-based は best long-term だが v0.3.0 で取れる risk ではない。
3. **Ship:** **as-is**。`SEEK_LEAD_SECONDS = 5.0` は OBS keyframe (~2s) 前提の static heuristic で
   long-GOP 録画では脱落の余地あり、ただし correctness は維持され perf 約束のみ弱まる。
4. **Structural concerns (4 件):** v0.3.0 blocker ではないが、v0.3.x で audit / follow-up 対象:
   - (i) `SEEK_LEAD_SECONDS = 5.0` の OBS-shaped assumption
   - (ii) `_REFINEMENT_SAMPLE_INTERVAL` 名前の docstring / test 散在 (実定数は `_REFINE_INTERVAL = 0.25`)
   - (iii) VFR で `n_step = round(sample_interval * fps_num / fps_den)` の fixed cadence semantic drift
         (runtime emitted-frame-count check で gross mismatch は捕捉する)
   - (iv) `_borderline_pseudo_regions` の "no false-positive risk" docstring が too strong
         (Pass 2 strict 抽出で影響は限定的だが "no risk" は overstatement)
5. **Bottom-line:** Accept as-is, ship dual seek + A5 in v0.3.0, open a v0.3.x optimization issue
   for gradient/adaptive or narrower transition-triggered refinement.

## 4. 決定

### 4.1 v0.3.0 (PR #793)

**Ship as-is.** PR #793 を current state でマージ。コード変更なし。

CHANGELOG `## [Unreleased]` 既存記述で trade-off explained:

```
- v0.3.0 で detect 高速化 path に切替 (#576) で ~10x slowdown が発生していたが、Codex perf
  rescue Option 1 (dual seek) を commit `a864834` で実装し、perf を legacy 同等以下に復元。
- ただし dual seek 後の accuracy 検証で sub-sample-interval blackout を Pass 1 が取りこぼす
  ケースを発見。A3 borderline range を `[15, 30) -> [15, 55)` に拡張 (#576 A5) して Pass 2
  refinement を活性化、accuracy regression ゼロに到達。trade-off として Pass 2 probe 数増加で
  perf cost +1.7x。
- 実測 (RTX 5090): 5 OBS baseline 合計 **~52 min** (legacy ~31 min)。spec §7.4 perf gate を 60 min/合計に revise。
- v0.3.x で更なる最適化 (gradient-based trigger / packet PTS parse / single-process design) 検討
  (#576 spec §10 R12 defer)。
```

### 4.2 v0.3.x 後続作業 (新規 issue 起票)

| # | scope | 優先度 | source |
| --- | --- | --- | --- |
| **R12-a** | Gradient-based / adaptive Pass 1 trigger で stable region をスキップ、52→31 min 復帰を目指す | P1 候補 | spec §10 R12 + Codex 推奨 |
| **R12-b** | `SEEK_LEAD_SECONDS = 5.0` の long-GOP 録画 (keyframe interval > 5s) 耐性 audit + adaptive lead time (実測 keyframe interval ベース) | P2 候補 | Codex (i) |
| **R12-c** | (minor finding) `_REFINEMENT_SAMPLE_INTERVAL` 名前の docstring / test 散在チェック (実定数 `_REFINE_INTERVAL = 0.25` に統一) | P3 | Codex (ii) |
| **R12-d** | `_borderline_pseudo_regions` docstring を Pass 2 strict 抽出の risk 評価に整え直す ("no false-positive risk" の言い換え) | P3 | Codex (iv) |
| **R12-e** | (defer 確認) packet PTS pre-scan を ad-hoc tool として復活させ、VFR 検出 / chunk boundary diagnostic に使う (実装は不確実、要 feasibility) | P3 | Codex (b) defer 整理 |

R12-c / d は code-only minor fix なので、誰かが detect 周辺を触る PR に乗せて消化してよい
(scope-guard の判定に従う)。

## 5. v0.3.0 で受容する risk (明示記録)

- **Wall time:** 52 min (legacy 31 min から +68%)。長時間録画を batch 処理する unattended use case で許容。
- **SEEK_LEAD_SECONDS 5.0 静的値:** OBS keyframe (~2s) 前提。Long-GOP 録画では duplicate decode が増えて
  perf 弱化するが、correctness は維持される。R12-b で adaptive 化候補。
- **select filter 将来 ffmpeg drift:** `select='not(mod(n,N))'` は frame-index ベースで `fps=N` (PTS ベース)
  より drift しにくいが、ffmpeg 仕様変更耐性は完全ではない。validate-fps-retirement.py で監視継続。
- **VFR semantic drift:** `n_step` 固定 cadence は厳密 VFR で content と sample 不一致の余地あり。
  Runtime emitted-frame-count check で gross mismatch は捕捉。OBS 録画は CFR/NTSC が支配的のため
  本 release では問題顕在化しない見込み。

## 6. Validation

- 5 OBS baseline で accuracy regression zero confirmed (既存)
- Codex Pre-flight Step 5 adversarial-review 既実施 (commit `d18ab3c` で対応済)
- 実機検証 (AMD APU 等 vendor): PR review 時に AskUserQuestion 経路で Idios へ依頼 (Iron Law 6)
- Self-Test Report は PR #793 本文に既収載

## 7. なぜ B (A5 revert) / C (defer) を採らないか

### B (A5 revert) を採らない理由

- A5 は obs-20260116 t=2175.7-2177.3 のような sub-sample-interval blackout を Pass 1 で取りこぼす
  問題を直接 fix している。Revert すると **既知の試合境界が silently miss** に戻る。
- +21 min perf cost を惜しんで accuracy zero regression を捨てる根拠は、利用シナリオ
  (unattended batch) と合わない。
- Codex 評価: *"Reverting A5 only is not defensible unless v0.3.0 accepts known silent misses."*

### C (defer = v0.3.0 で legacy fps filter のまま ship) を採らない理由

- Legacy fps filter path は **obs-20260116 t=3227.4 の 3.6s blackout を見逃す**ことが root-cause
  調査で確認済 (spec §journey)。"defer = safe" は錯覚で、形態が違うだけの silent loss が発生する。
- 「現状の trade-off を確定して documented release にする」と「未確定の状態のまま legacy bug を
  抱え続ける」では、前者の方が ship 後の対応 (v0.3.x optimization) が明確。

## 8. 終結条件

本 doc が approved されれば、以下が次のアクション:

1. PR #793 を `/iterate-review 793` または `/review-pr 793` で最終 review → merge。
2. §4.2 の R12-a / R12-b / R12-c / R12-d / R12-e を GitHub issue として起票
   (Iron Law 2 — 3 件以上の bulk なので `AskUserQuestion` で sample 1 件提示 + 全件 OK / 個別 / やめる の 3 択確認)。
3. v0.3.0 release 後、R12-a (gradient-based) を v0.3.x の最初の取り組みとして brainstorming
   → spec → plan サイクルに乗せる。

本 doc は decision record として archive せず、v0.3.x perf 最適化 spec の起点として参照される。

## 9. 2026-05-19 User 決定: audit-first direction (§4 supersede)

§4 で「Ship PR #793 as-is」を推奨したが、Idios と協議の結果、**先に baseline 精度を
ground-truth audit で確定させ、その結果に基づいて #576 の扱いを再判定する**方針に変更。

### 9.1 理由

- §3 NOTE / §journey で報告された F1-F4 (obs-20260116 t=3227.4, t=2178, obs-20260118
  t=2610.75, 3 件短時間 blackout) は全て **偶発的発見**だった (Codex spec reading /
  Idios 視覚確認 / pre-A5 dual seek baseline regen 中の検出 等)
- 他 baseline (obs-20260119 / 20260127 / 20260209) や既 audit 済 baseline の未知箇所に
  F5+ が存在する可能性を排除できない
- ground truth 未確定の状態では trade-off (perf -68% vs accuracy zero regression) を
  定量的に正当化できない

### 9.2 新方針

1. **#796** (`[task] v0.3.0 OBS baseline 5 件の ground-truth audit`) を起票済
   (URL: https://github.com/Idios/kobutachan-allaganeye/issues/796)
2. PR #793 は draft に convert、`Blocked by #796` で PR comment 済
3. #796 audit 完了後、本 spec §4 の A/B/C 判断を再評価する

### 9.3 §4 (旧推奨) の位置づけ

§4 の「Ship A as-is」推奨は **audit 未実施の前提**に基づくものであり、本 §9 で superseded。
audit 結果次第で:

- baseline が ground truth とほぼ一致 → §4 / §7 の「B / C を採らない論理」が成立、A 推奨が確定
- 重大な silent miss / FP 発覚 → detector tuning 別 issue 起票後に再再評価
- audit 過剰 / 不要判定 → §4 推奨 (A) が直接生きる

### 9.4 §4.2 R12-a..e の扱い

R12-a (gradient-based) / R12-b (SEEK_LEAD_SECONDS adaptive) / R12-c..e (minor) の
v0.3.x 後続作業は #796 audit と独立に進行可能。ただし audit 結果次第で priority / scope
が変わる可能性があり、起票 timing は audit 完了後を推奨。

## 10. V6.2 attempt + V2 FP finding (reverted, #797 defer 確定)

§9 で audit-first direction を取り、PR #793 baseline 検証で **#797 (obs-20260116
M6 end miss)** が残課題と確定。user 選択 scope (D) に基づき PR #793 内で fix を試みた。

### 10.1 V6.2 attempt: scorebar HUD binary search

User suggestion (2026-05-21): 全フレーム scan ではなく**二分探索**で境界位置を絞る。

実装:

- `_check_scorebar_present_at` / `_find_match_end_via_scorebar` / `_refine_open_ended_unknown_matches`
  を `detector.py` に追加
- `detect_match_boundaries` の post-process で `type=unknown` & `end=total_duration`
  の match を refine
- 13 tests (`TestFindMatchEndViaScorebar` 7件 + `TestRefineOpenEndedUnknownMatches` 6件)
  を `tests/test_detector.py` に追加し全 PASS

Commit: `f7f8879` (subsequently reverted in `22c8979`)。

### 10.2 実機検証で発覚した V2 FP

`obs-20260116` で実機 detect を再実行:

- M6 type が `unknown` → `fl_match` に refined (V6.2 fired 確認)
- M6 end = **6898.25** (legacy 7303.488 から -405s 改善)
- ただし GT (Idios) は **6540** → **delta +358s** (±5s tolerance 大幅超過)

`_check_scorebar_present_at` を obs-20260116 の 18 timestamp で probe したところ、
**V2 が 5700-6850 全範囲で True を返し、true positive (in-match の 6520) と
false positive (post-match の 6700/6800/6850) を区別できていない**ことが判明。
Idios 視覚確認 (6898 付近の暗転は teleport / map 移動、scorebar はその前後にも存在しない)
と矛盾。

V6.2 の二分探索は V2 が確実に True/False に切り替わる前提だが、V2 の post-match FP に
より収束点が真の match end (6540) ではなく post-match content の次の "scene change"
(~6898 = teleport blackout 直前) になった。

### 10.3 Decision (2026-05-21): revert + defer

V6.2 を `git revert 22c8979` で undo (3 files / -594 / +1 line)。

理由:

- V6.2 の output (6898) は GT (6540) と一致しない wrong value
- 「不完全だが legacy より改善」(6898 < 7303) として ship する選択肢も検討したが、
  user GT が明確 (6540) なので shipping すべきでない
- V2 FP の根本修正は scope 大 (V2 改修 + 5 baseline regen + #522/#307 regression check)
  で v0.3.0 timeframe に合わない

### 10.4 Follow-up issues

- **#803** (新規、`bug` / `P2-medium` / `refactor`): scorebar V2 detection FP in
  post-match content。V2 の検出ロジック厳格化を扱う。本 issue が **#797 の
  scorebar-based fix path の blocker**。
- **#797**: scorebar-based fix は #803 解決待ち。並行で audio Fanfare 復活
  (#327 freeze 解除) による fix path も候補 (3 options が #797 comment に列挙)。

### 10.5 PR #793 への影響

PR #793 は #797 fix を含まずに ship:

- V6.2 implementation は `22c8979` で revert 済、detector.py / tests は f7f8879 以前の状態に復帰
- obs-20260116 M6 end は依然 7303.488 (video 末尾、type=unknown) のまま (legacy と同等動作)
- spec §9 の結論 (Ship as-is、ただし #797 は documented caveat) に戻る

### 10.6 残る scope (D) 項目

User 選択 scope (D) のうち V3 (obs-20260119/127/209 detect) は引き続き実施し、
PR #793 detector の他 baseline での regression 有無を確認する。

#797 fix は v0.3.x で本公式 fix (#803 or audio Fanfare unfreezing 経由)。
