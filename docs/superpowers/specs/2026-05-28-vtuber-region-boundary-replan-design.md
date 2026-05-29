# L3: VTuber 領域・境界検出 再アーキテクチャ (re-plan) 設計 (2026-05-28)

> **Status**: brainstorming 完了 (分解レベル) / 各サブプロジェクトは個別に spec → plan
> **Parent**: [#753](https://github.com/Idios/kobutachan-allaganeye/issues/753)
> **Supersedes (approach)**: #809 の領域 auto-detection 手法 (S3 uniform-sampling + near-black dark_thresh)。#809 の wiring コードは P3 で再利用
> **基づく**: Codex rescue (2026-05-28) の知見 + #809 Wave F 実機検証
> **関連 spec**: [2026-05-26-vtuber-capture-region-detection-design.md](2026-05-26-vtuber-capture-region-detection-design.md) (Phase 2a) / [2026-05-27-vtuber-pass1-region-wiring-design.md](2026-05-27-vtuber-pass1-region-wiring-design.md) (#809) / [2026-05-18-v030-l3-redefinition-design.md](2026-05-18-v030-l3-redefinition-design.md) (上位 L3)

## 1. 背景: #809 Wave F で判明したこと

本 issue #809 (VTuber Pass1 領域輝度 wiring) を実装し gyawa 2h43m VOD で実機検証した結果:

- ✅ **wiring は健全**: 検出領域で crop した輝度を Pass1/Pass2/GPU に通す経路 + OBS は FULL_FRAME 縮退で detect 出力 bit-exact (5 baseline FULL_FRAME + OBS+GPU detect が baseline と MATCH)。
- ✅ **crop が Pass1 を解錠** (finding #4 実証): spike で full-frame recover 0/5 → 領域 crop recover 4/5 start + drop 5/5 end。
- ⚠️ **領域 auto-detection が脆い**: 全 VOD 一様 sampling → S3 (per-pixel max/min) は overlay/avatar の時間変動も拾い full-width 誤検出。near-black `dark_thresh=3` で gyawa は IoU 0.976 に改善したが **sampling 密度依存 + gyawa 1-source 過学習** (R6)。黒画面の深さは encoder/overlay 輝度依存で multi-source 不安定。
- ⚠️ **production の clean な試合分割は未達**: `detect_match_boundaries` を VTuber crop に回すと 8 境界が出て GT の ~4/10。原因は (a) OBS 調整の `_expand_regions_with_transitions` (閾値 55, lobby ~51 向け) が VTuber crop の lobby 輝度 50-86 を過剰 merge し実境界を失う、(b) scorebar 分類が OBS 絶対座標前提で VTuber inset 内の scorebar を誤分類 (#480 未対応)。

## 2. アーキテクチャの転換: scorebar を上流 anchor に

Codex rescue の核心: **FL scorebar の HUD 幾何はコンテンツ固定**で encoder/overlay に依存しない。よって領域検出の anchor と境界分類の両方に使える共有基盤になる。これは依存順序を**反転**させる。

| | 旧 (#807/#809) | 新 (本再計画) |
| --- | --- | --- |
| scorebar | 領域検出の**下流** (#480 が領域を消費) | **上流 anchor** (領域も分類も scorebar 局在化を消費) |
| 領域検出 | S3 uniform-sampling + near-black dark (黒深度依存・脆い) | scorebar 幾何 anchor + S3 extent の **consensus** (幾何固定・頑健) |
| 鶏卵 (領域↔暗転) | S3 が暗転フレームを必要 (uniform sampling で代替→汚染) | scorebar は試合中フレームで局在化 → 暗転時刻不要で解消 |

## 3. サブプロジェクト分解と依存順

| # | サブプロジェクト | 内容 | 依存 | issue 対応 |
| --- | --- | --- | --- | --- |
| **P1** | **robust scorebar 局在化 (anchor)** | 任意フレームで FL scorebar を HUD signature (GC 紋章 3 点 AND + span) で位置特定。game inset 位置非依存・OBS/VTuber 統一・confidence 付き。Phase 2a の S2 (`detect_region_scorebar_band`) / 絶対座標 `_has_scorebar_v2` を一般化 | — | #480 内包 or 新規 (Iron Law 2 で起票時確定。案: #480 を localization+classification に再定義) |
| **P2** | **scorebar-anchored 領域検出** | scorebar 幾何 + S3 extent の consensus + 幾何/aspect/area サニティ + confidence gate → game 矩形。低信頼/不一致は FULL_FRAME。`detect_coarse_region` の dark_thresh=3 を置換 | P1 | #809 detect_coarse_region 再設計 |
| **P3** | **領域 crop 輝度 wiring** | crop→Pass1/Pass2/GPU + `effective_threshold` + OBS bit-exact。#809 の検証済みコードを再利用 | P2 | #809 wiring コード再利用 |
| **P4** | **region-aware 境界分類 (#480)** | 局在化した scorebar (P1) で inset 内 scorebar を読み `match_boundary`/`in_match`/`non_fl` 分類。clean end-to-end の鍵 | P1, P2 | #480 |
| **P5** | **adaptive transition expansion** | inset 検出時は crop 輝度分布から transition 閾値を動的導出。FULL_FRAME は現行 55 維持 | P3 | 新規 |
| **P6** | **metadata 領域フィールド** | coarse region (+ per-segment) を metadata.json 永続化 | P2 | #810 (既存) |

依存順: **P1 → P2 → {P3, P4} → P5**、P6 は P2 後に並行。#481 (minimap) は別レイヤーで P1/P2 の領域を消費。

## 4. #809 の処遇

- **#809 branch (`claude/l3-809-pass1-region-wiring`, 22 commits) は park** (PR せず)。
- **再利用**: P3 wiring コード (capture_region.py の `is_full_frame`/`region_mean`、detector.py の crop 分岐 + `effective_threshold` + GPU crop、bit-exact 機構) は新計画下で cherry-pick / 再適用。
- **置換**: `detect_coarse_region` (uniform-sampling + dark_thresh=3) は P2 の consensus 検出器で置換。`_REGION_DARK_THRESH` は廃止。
- #809 の spec (2026-05-27) は「approach は本再計画で supersede、wiring は再利用」と注記する。

## 5. 検証前提 (multi-source data 未確定)

- multi-source VTuber source の入手は**現時点で未確定** (別途確認)。
- よって本再計画は「**設計・実装はするが robustness 検証はデータ待ち**」を前提とする: P1/P2/P5 は当面 gyawa 1-source + 合成テストで検証し、multi-source robustness は追加ソース (guard verify 通過) 入手後の data-gated follow-up とする。
- **OBS bit-exact は全 P で hard gate 維持** (FULL_FRAME 縮退で v0.3.0 baseline と bit-exact)。新 VTuber ロジックは「non-full-frame かつ high-confidence」gate の内側に閉じ込め、OBS 回帰を構造的に防ぐ。

## 6. サブプロジェクト・スケッチ (各 P は個別 spec で詳細化)

- **P1 (最初に spec 化)**: 入力=単フレーム (RGB)。出力=scorebar span/位置/confidence または None。OBS (全幅 HUD) と VTuber (inset 内 HUD) を統一的に扱う。GC 紋章 3 点 AND の HUD スケール耐性、全 y 走査コスト、confidence スコアリング、試合外フレームでの None 返却が論点。Phase 2a の S2 が原型。
- **P2**: P1 を試合中らしい複数フレームで実行 → scorebar 幾何の median/consensus → game 上端・幅。S3 extent で下端・左右を補完。幾何サニティ (aspect/area) + confidence gate。OBS は FULL_FRAME。
- **P3**: #809 wiring を P2 の region で駆動。bit-exact 機構そのまま。
- **P4 (#480)**: P1 の局在化 scorebar を inset 座標で読み分類。`filter_blackouts_with_scorebar` に CaptureRegion を渡す。
- **P5**: crop Pass1 brightness の percentile クラスタから transition 閾値推定。
- **P6 (#810)**: `RegionTimeline.to_dict` を metadata.json schema に。

## 7. リスク

| # | リスク | 緩和 |
| --- | --- | --- |
| R1 | OBS bit-exact 回帰 | FULL_FRAME 縮退 + confidence gate + 全 P で baseline 回帰テスト hard gate |
| R2 | gyawa 1-source 過学習 (multi-source 未確定) | 幾何ベース (scorebar) で原理的頑健化 + multi-source 検証を data-gated follow-up に明示 |
| R3 | P1 が試合中フレームを十分得られない (短い VOD / 試合少) | 疎 sampling + 複数フレーム consensus + 取得失敗時 FULL_FRAME fallback |
| R4 | scorebar が overlay 装飾 (シアン帯等) と誤検出 | GC 紋章 3 点 AND (Phase 2a 検証済機構) を流用 |
| R5 | 大きめスコープでの統合コスト | P1→P2→… の段階導入、各 P 独立 spec/plan/PR |

## 8. 決定ログ (本再計画ブレスト)

| 論点 | 決定 |
| --- | --- |
| アーキテクチャ | **scorebar 局在化を上流 anchor に**転換 (領域・分類の共有基盤) |
| #809 | **branch park** (PR せず)、wiring コードは P3 で再利用、detect_coarse_region は P2 で置換 |
| 分解 | P1 scorebar 局在化 → P2 領域検出 → {P3 wiring, P4 分類#480} → P5 transition、P6 metadata 並行 |
| 最初の spec 対象 | **P1 robust scorebar 局在化** |
| multi-source 検証 | データ未確定 → 設計・実装は進め、robustness 検証は data-gated follow-up。gyawa 1-source + 合成で当面検証 |
| OBS bit-exact | 全 P で hard gate 維持 |

## 9. 次のステップ

1. 本 overview を user レビュー。
2. **P1 (robust scorebar 局在化) を個別 brainstorming → spec → writing-plans → 実装**。
3. 以降 P2→… を順に。issue 再構成 (P1 を #480 に内包、P5 新規起票等) は Iron Law 2 で user 承認後に実施。

## 10. 参照

- #809 spec: [2026-05-27-vtuber-pass1-region-wiring-design.md](2026-05-27-vtuber-pass1-region-wiring-design.md) (§10 Wave F 実測)
- Phase 2a spec: [2026-05-26-vtuber-capture-region-detection-design.md](2026-05-26-vtuber-capture-region-detection-design.md) (§6.3.1 実測選定: S2 上端 15.7px / S3 IoU 0.851)
- 現行コード: `allaganeye/video/capture_region.py` (`detect_region_scorebar_band`=S2, `detect_region_blackout_overlap`=S3), `allaganeye/video/detector.py` (`_has_scorebar_v2` 絶対座標, `_find_scorebar_horizontal_range`, `_expand_regions_with_transitions`), `allaganeye/video/scorebar.py` (`filter_blackouts_with_scorebar`)
- 既存 issue: #480 (scorebar ROI 適応。本再計画で P1+P4 に再定義する案), #481 (minimap), #810 (metadata 領域フィールド)
- Codex rescue (2026-05-28): consensus 検出器 / region-aware scorebar / adaptive transition / BLOCKED (multi-source 必要)
