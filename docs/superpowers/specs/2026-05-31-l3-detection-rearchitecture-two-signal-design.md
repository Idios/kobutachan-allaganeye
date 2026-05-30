# L3 検出再アーキテクチャ: 2 信号 fusion 設計 (2026-05-31)

> L3 VTuber 対応の再々々設計。presence 単独全置換 spec
> ([2026-05-29-presence-based-detection-engine-design.md](2026-05-29-presence-based-detection-engine-design.md))
> が OBS 実機で破綻した (同 spec 付録 A) ことを起点に、re-plan
> ([#753](https://github.com/Idios/kobutachan-allaganeye/issues/753)) 全体を再ブレストした結果をまとめる。
> 本 spec は presence spec の中核決定 (§3 Q3「brightness Pass-1 撤去・presence 単独全置換」) を **supersede** し、
> re-plan の P1〜P6 を再定義する。P1 (`localize_scorebar`, PR #811 マージ済) を基盤として再利用する。
>
> **Status**: brainstorming 完了 / user 承認待ち (spec review gate)
> **Supersedes**: presence spec §3 Q3 (全置換) / re-plan P2-P4 の依存構造
> **基づく**: presence spec 付録 A (OBS 実機破綻) + 本セッションの実機データ検証 + Codex adversarial review (2026-05-30)

## 1. 背景: presence 全置換が OBS で破綻した

presence spec は「scorebar 有無 (present/absent) を OBS/VTuber 共通の唯一の検出信号とし、brightness Pass-1 を撤去する」方針だった。Phase 1 を実装し OBS 実機 (obs-20260209、20.6GB/57min) で受け入れゲートを実行した結果、**設計の中核が破綻**した (presence spec 付録 A):

- **性能 OK** (3m16s 完走) だが **精度 FAIL** (`matched=1, missed=2, spurious=1`)。
- 根本原因: 試合直後の**リザルト/順位画面が同じ GC 紋章を表示**するため、presence が連続試合をマージする。confidence 閾値でも absent-gap 長でも分離不能。
- **決定的データ**: 既存 brightness 検出器は同動画で 3 試合を秒未満精度で検出。**brightness blackout は真の試合境界 (リザルト画面の手前) に存在し、既存検出器はそれを正しく使えている**。presence がマージしたのは、この blackout 信号を持たないため。

→ 結論 (付録 A.4): **brightness 境界は撤去すべきでない。`localize_scorebar` の真価は「全置換の検出器」ではなく、位置独立で頑健な分類器 + VTuber 経路にある。**

## 2. 本セッションで確定した方針 (5 決定)

| # | 論点 | 決定 | 根拠 |
| --- | --- | --- | --- |
| Q1 | scope | **re-plan #753 全体を再設計** | presence の位置づけ・VTuber 境界の出し方を含めて作り直す |
| Q2 | VTuber 境界信号 | **scorebar anchor から inset 矩形を復元し crop** (#809 crop-brightness wiring 再利用) | #809 Wave F: full-frame では blackout を拾えないが inset crop で Pass1 が blackout を回復 (drop 5/5 end)。脆いのは region 検出 (S3) で crop-brightness 自体は有効 |
| Q3 | 分類器統一 | **localize に統一する方向。ただし OBS では v2 を authoritative に温存し localize を shadow 並走、parity 実証後に retire (provisional)** | VTuber inset は v2 絶対座標が効かず localize 必須。OBS は 5 baseline で拾えない regression risk があるため、Codex 推奨の incremental (parity 実証ゲート) に従う。**§3.4 / §11 で要再訪** |
| Q4 | localize の使い方 | **brightness 主 / localize+motion は分類器** (presence timeline は VTuber + 診断に従属) | A.3 実証: blackout = 境界。localize = 「その blackout が真の境界か」を判定する分類器。後述 Codex #2/#4 を自動解消 |
| Q5 | リザルト除去信号 | **動き/静止判定 (MAD) を分類の補助信号に昇格** | リザルト/順位画面=静止、FL 試合=常時動き。位置・encoder 非依存で OBS/VTuber 両方に効く。**brightness 主では二次補正に降格** (§3.3) |

## 3. アーキテクチャ: 2 信号 fusion (brightness 主)

### 3.1 核心

released 検出器を「全置換」せず、**位置独立な 2 信号を fusion** する。**brightness blackout を boundary 信号の主軸**とし、`localize_scorebar` + 動き判定を**分類器**に充てる。これは「現行 OBS pipeline は既に正しい hybrid であり壊すな」という付録 A の含意の構造化である。

**① boundary 信号 (主・どこに境界がありうるか)**

- 領域 crop の brightness 暗転。A.3 実証: OBS で真の試合境界に秒未満精度で存在。
- OBS = FULL_FRAME (現行と同じ全画面)。VTuber = scorebar anchor で復元した inset crop (#809 Wave F で blackout 回復を実証)。

**② 分類信号 (各 blackout が真の境界か)**

```text
classify(blackout) = localize_scorebar(flank_frame) is not None  AND  moving(flank_frame)
```

- `localize_scorebar` (P1, 位置独立) で blackout の前後フレームに scorebar があるか判定 → 現行 `classify_blackout` の `_has_scorebar_v2` 呼び出しを置換。
- `moving()` = scorebar 領域の MAD (既存 `_is_static_from_frames`) が閾値超。リザルト/順位画面 = present だが**静止** → 分類上 absent 扱い。
- 出力分類は現行同一: `match_boundary` / `in_match` / `non_fl`。#480 (region-aware 分類) はこの localize 化に subsume。

**③ 領域 (両信号を測る場所)**

- OBS → FULL_FRAME。VTuber → scorebar anchor から復元した inset 矩形 (P1 `localize_scorebar` の bbox + 16:9 で下端/左右を導出)。

### 3.2 データフロー (OBS / VTuber 統一)

```text
入力動画
  │
  ├─[Stage 0] 領域 anchor   : sparse in-match frame → localize consensus → game 矩形
  │                            OBS=FULL_FRAME / VTuber=inset rect          [re-plan P1✓ + P2]
  │
  ├─[Stage 1] boundary 信号 : 領域 crop で brightness Pass1/Pass2 → 暗転エッジ (主軸)
  │                            OBS=全画面(現行不変) / VTuber=inset crop(#809再利用)  [P3]
  │
  ├─[Stage 2] 分類          : 各 blackout の前後で localize+motion → match_boundary/in_match/non_fl
  │                            OBS は v2 が authoritative・localize を shadow 並走 (parity 計測) [P4 = #480]
  │
  └─[Stage 3] 抽出・後処理  : duration filter (backstop) → segment 抽出 → trailing 整理
                              → metadata.json (現行 schema 不変)
```

OBS・VTuber とも同一パイプライン。差は Stage 0 の領域 (FULL_FRAME / inset) と、それに伴う Stage 1 crop / Stage 2 座標のみ。**OBS 経路は分類器 primitive 差し替え + v2 並走のみで、構造は現行を保つ** (最小変更 = regression risk 最小)。

### 3.3 fusion 優先順位 (Codex #4 = 不一致時の真理値表)

brightness を主軸にすることで signal 不一致が構造的に減る。残る組合せの扱い:

| boundary (blackout) | 分類 (localize+motion) | 扱い |
| --- | --- | --- |
| あり | match_boundary | 境界として採用 (主経路) |
| あり | in_match (両側 present+moving) | 試合内暗転。短ければ除外、長ければ境界保持 (現行 `_IN_MATCH_MAX_DURATION` 流用) |
| あり | non_fl (両側 absent) | 非 FL。除外 (現行同一) |
| なし | (present 区間) | **boundary を作らない** = リザルト 91% present でも試合化しない (duration filter backstop)。これが presence 全置換との決定的差 |
| あり | static (present だが静止) | リザルト/順位画面。Q5 で absent 化 → non_fl 寄せ |

**brightness 主では Q5 (motion) は load-bearing でなく二次補正**: リザルト区間は blackout 間 gap が `min_match_duration` (default 300s) 未満なら duration filter で必ず落ちる (§3.5)。Q5 は gap が長いケースの保険。

### 3.4 Q3 provisional の扱い (v2 shadow guard)

Codex review (§4) と本セッションの実機検証で、**「v2 retire」は 5 baseline で拾えない OBS regression risk を持つ**ことが判明した。よって (用語: **authoritative** = production 出力を決める / **shadow** = 並走計測のみで出力に効かせない):

- localize に **API を統一**する (分類の呼び出し口を 1 本化) が、**OBS では v2 を authoritative に温存し、localize+motion を shadow で並走**させて両者の判定差分を harness で計測する。
- **bit-exact → GT-accuracy 置換は「加えて」**: GT-accuracy (tolerance) gate を新設しつつ、cutover 前の shadow 期間は baseline diff も維持する (Codex #7)。
- localize+motion が **long 非試合区間 (lobby/result) で v2 と OBS parity (FP/FN ゼロ差)** を実証してから、localize を authoritative に昇格し v2 retire を判断する (Phase 4)。
- `_drop_post_match_trailing` (#805) は v2 を直接プローブする hidden 第 2 分類器 (§4 Codex #6)。**当面 v2 のまま温存**し、membership 統一は #805 非破壊化と別 phase で扱う。

→ **Q3 の最終形 (v2 retire 可否) は §11 未確定として残す。** 本 spec では「API 統一 + shadow 並走」までを確定範囲とする。

### 3.5 既存パイプラインとの対応 (検証済み事実)

`detect_match_boundaries` 実フロー (`detector.py:267-421`): Pass1 brightness scan → `_group_blackout_regions` → `_expand_regions_with_transitions` → Pass2 `_refine_blackout_regions` → `filter_blackouts_with_scorebar` (#480 分類) → `_filter_and_extract_segments` (duration filter) → `_drop_post_match_trailing`。

- duration filter (`_filter_and_extract_segments:1851,1868`) は `seg_end - seg_start >= min_match_duration` (default 300、`detector.py:205`) で gate。
- **訂正記録**: 本セッション当初「v2 の位置特異性がリザルト除去に load-bearing」と述べたが、コード追跡の結果 **duration filter が backstop** であり、obs-20260209 の result gap (176s < 300s) は v2 の判定に関係なく落ちる。Codex #2 の指摘どおり。この事実が「brightness 主」決定を強く正当化する。

## 4. Codex adversarial review (2026-05-30) の反映

design-stage で Codex に「2 信号 fusion」案をレビューさせた (read-only)。主要 finding と本 spec での扱い:

| # | Codex finding | 本 spec での扱い |
| --- | --- | --- |
| P1-1 | `_is_static_from_frames` は primary 信号として未検証 (min MAD + ハード閾値 0.5、override 限定用途)。重複エンコード/防御静止/動くリザルトで失敗 | Q5 を brightness 主で**二次補正に降格** (§3.3)。MAD は per-source 分布を harness で収集し percentile/多数決化を検討 (§7)。R1 |
| P1-2 | 「v2 位置特異性が M1/M2 分離に必要」は誇張。duration filter (300s) が backstop | **採用・訂正** (§3.5)。brightness 主で自動解消 |
| P1-3 | v2 廃止は OBS 高特異度ガードを消す (ゼロ FP 文書化 vs localize リザルト 91% FP) | Q3 を provisional 化、v2 shadow guard 温存 (§3.4)。R2 |
| P2-4 | 不一致時の fusion 優先順位が未定義 | §3.3 真理値表で定義。OBS は brightness 優先 default |
| P2-5 | VTuber inset blackout 欠損時の「membership edge ± refine」フォールバックが危険 | 低信頼出力として metadata フラグ、境界 snap と同等扱いしない (§5)。R3 |
| P2-6 | `_drop_post_match_trailing` が v2 を直接プローブ = hidden 第 2 分類器、新 membership と競合 | v2 温存 + 別 phase (§3.4)。Phase 0 map 対象。R4 |
| P3-7 | GT-accuracy (tolerance) のみでは OBS regression ガードが弱い | shadow 期間は baseline diff も維持 (§3.4 / §7) |
| P3-8 | CPU/GPU/fps-filter パリティが cutover risk | 検証 matrix に CPU/GPU/legacy fps を含める (§7)。R5 |

Codex 提案順序 (production 不変のまま shadow trace → MAD calibrate → OBS を baseline-diff + GT-tolerance 両方で gate → VTuber GT 追加) を §8 Phase 構造に採用。

## 5. データ構造 / API

- **再利用 (P1, マージ済)**: `localize_scorebar(frame, *, stride, target_ratio) -> ScorebarLocalization | None` (`capture_region.py`)。入力 1920x1080 RGB、出力 probe px bbox + confidence。
- **再編 (#480)**: `filter_blackouts_with_scorebar` / `classify_blackout` の scorebar 検出 primitive を `_has_scorebar_v2` → `localize_scorebar` + `moving()` に差し替え。v2 は shadow guard として並走計測。classify/merge/duration ロジックは流用。
- **新規 (VTuber)**: Stage 0 領域 anchor (sparse localize consensus → inset 矩形)、Stage 1 inset crop wiring (#809 再利用)。
- **VTuber fallback フラグ**: inset blackout 欠損で membership edge にフォールバックした segment は metadata に低信頼フラグを付け、境界 snap と区別 (Codex #5)。
- **出力**: 試合 segment = 現行 `matches[]` / `boundaries`。metadata schema 不変 (region フィールドは P6 で別途検討、本 spec 範囲外)。

## 6. やらないこと (境界)

- **presence 全置換** (presence spec の方針): 撤回。brightness Pass-1 は boundary 主軸として存続。
- **minimap 切抜き** ([#481](https://github.com/Idios/kobutachan-allaganeye/issues/481)): 別レイヤー。
- **#805 非破壊化**: `_drop_post_match_trailing` の不可逆削除 → フラグ方式は別 phase / 別 issue。本 spec は v2 温存で competing しないことだけ担保。
- **metadata region フィールド** ([#810](https://github.com/Idios/kobutachan-allaganeye/issues/810)): P6、本 spec 範囲外。

## 7. 検証戦略

### 7.1 unit (動画不要)

- 分類差し替え: 合成フレームで localize+motion 分類 (present+moving / present+static / absent) → 期待ラベル。
- fusion 真理値表 (§3.3): 合成 blackout × 分類 → 期待 segment。
- VTuber fallback フラグ: inset blackout 欠損ケース → 低信頼フラグ立つ。

### 7.2 harness (slow・sample-gated、Phase 1 資産流用)

- `compare_segments` (Phase 1) で OBS 5 baseline + VTuber 5 source を GT 突合。matched/missed/spurious、boundary 誤差、wall-time。
- **v2 vs localize+motion の OBS parity** 計測 (Codex #3): long 非試合区間 (lobby/result) の FP/FN 差分を per-source 出力。
- **MAD 分布収集** (Codex #1): 真の試合/リザルト/ロビー/ローディングの per-source MAD を出し、閾値 calibrate。
- **CPU/GPU/legacy-fps parity** (Codex #8): 最低 1 OBS baseline を 3 モードで突合。

### 7.3 gate

- OBS: shadow 期間は baseline diff (現行不変) + GT-accuracy (missed/spurious ゼロ、誤差 ≤ tol) の**両方**。
- VTuber: 手動 GT に対し recall/precision 目標値 (harness 実測後設定)。
- v2 retire (§11): localize+motion が OBS parity (FP/FN ゼロ差) を実証してからのみ。

## 8. 段階分解 (Phase 0-4)

| Phase | 内容 | production 影響 | gate |
| --- | --- | --- | --- |
| **0** | 検出 subsystem の git 考古学 + 現状 map (ドキュメント化)。各 layer の load-bearing / cruft / 有害判定、`_drop_post_match_trailing`×v2×membership coupling を含む | なし (docs) | user レビュー |
| **1** | Stage 0 領域 anchor (P1 consensus → inset) + Stage 1 VTuber inset crop wiring (#809 再利用)。OBS=FULL_FRAME 縮退 | なし (VTuber 経路は gate 内) | OBS bit-exact 維持 + gyawa crop blackout 回復 |
| **2** | Stage 2 分類を localize+motion 化 (#480)。v2 shadow guard 並走。MAD calibrate | なし (v2 が production 判定、localize は shadow) | OBS parity 計測 + baseline diff |
| **3** | VTuber GT 注釈 (5 source) + VTuber 検証。fusion 真理値表 + fallback フラグ | なし | VTuber GT-accuracy |
| **4** | cutover: localize を production 判定に昇格 (v2 retire 可否は parity 実証後判断)。GT-accuracy gate 化 | あり (分類器置換) | 全 GT-accuracy + baseline diff + Idios 実機検証 |

Phase 0-3 = 検証・非破壊、Phase 4 = 切替。「検証してから切替」をデータ駆動で。各 Phase 独立 PR。

## 9. re-plan #753 P1-P6 の再定義

| re-plan | 旧定義 | 新定義 (本 spec) |
| --- | --- | --- |
| P1 | robust scorebar 局在化 (anchor) | **マージ済** (#811)。Stage 0/2 で consumer として再利用 |
| P2 | scorebar-anchored 領域検出 (S3 consensus) | Stage 0 領域 anchor。S3 extent は補助、scorebar geometry + 16:9 主軸に簡素化 |
| P3 | 領域 crop 輝度 wiring | Stage 1 (#809 再利用)。VTuber inset crop |
| P4 | region-aware 分類 (#480) | Stage 2 = localize+motion 分類。v2 shadow guard 並走 |
| P5 | adaptive transition expansion | VTuber crop 輝度分布から動的閾値。FULL_FRAME は現行 55 維持 (Phase 3+ で必要時) |
| P6 | metadata 領域フィールド (#810) | 本 spec 範囲外 (別途) |

依存: Phase 0 (map) → Phase 1 (region+crop) → Phase 2 (分類) → Phase 3 (VTuber 検証) → Phase 4 (cutover)。

## 10. Phase 1 (presence) コード資産の処遇

`presence.py` + `presence_harness.py` + 3 test files (branch `claude/l3-p2-region-detection`、commit 済・production 非配線) の再利用:

- `compare_segments` / GT 突合ハーネス → **存続** (§7 検証インフラの中核)。
- `localize_present_at` (frame source → localize bridge) → **存続** (Stage 2 分類で再利用)。
- `scan_presence` / `segment_presence` / `detect_matches_by_presence` (全域 presence timeline) → **VTuber + 診断専用に降格**。brightness 主では OBS production 経路に使わない。revert 不要、harness 資産として保持。
- `refine_boundary` (二分探索) → boundary 精緻化で再利用候補。

**branch 処遇**: park も land もせず、本再設計の Phase 1-2 実装ブランチとして**継続使用** (#811 ベース、develop-0.3.0)。

## 11. 未確定 (Iron Law 2 / 5 で user 承認後に確定)

- **Q3 最終形 (v2 retire 可否)**: §3.4。localize+motion の OBS parity 実証後に判断。本 spec は「API 統一 + shadow 並走」まで確定。
- **issue 起票 / 編集**: presence umbrella の再定義、#480 を Stage 2 に再マップ、#809 branch の扱い、#805 非破壊化との phase 分離。**起票時に AskUserQuestion** (Iron Law 2)。
- **閾値最終値**: MAD 静止閾値、`T_*`、領域 confidence gate、VTuber GT 目標値 → harness 校正。
- **MAD の昇格形** (Codex #1): min → percentile/多数決化するか harness 分布で判断。

## 12. リスク

| # | リスク | 緩和 |
| --- | --- | --- |
| R1 | MAD (motion) が試合/リザルトを誤判定 (Codex #1) | brightness 主で二次補正に降格。per-source 分布で calibrate、percentile/多数決化検討。短 blackout 限定 override から段階昇格 |
| R2 | v2 retire で 5 baseline 外の OBS regression (Codex #3) | Q3 provisional、v2 shadow guard 並走 + parity 実証ゲート。bit-exact baseline diff を shadow 期間維持 |
| R3 | VTuber inset blackout 欠損で実試合を誤分割 (Codex #5) | 低信頼フラグ、境界 snap と区別。harness で boundary 誤差確認 |
| R4 | `_drop_post_match_trailing` × v2 × 新 membership の hidden coupling (Codex #6、#805) | v2 温存、別 phase。Phase 0 map で coupling 明示 |
| R5 | CPU/GPU/legacy-fps パリティ崩れ (Codex #8、#575) | 検証 matrix に 3 モード。frame-index ベース新 path 前提 |
| R6 | gyawa 1-source 過学習 (VTuber multi-source) | 5 source 手動 GT + 幾何ベース anchor。data-gated |
| R7 | brightness 主で VTuber 境界を取り逃す (full-frame では blackout なし) | Stage 1 inset crop で blackout 回復 (#809 Wave F 実証)。領域 anchor が前提 |

## 13. 参照

- presence spec (supersede 対象): [2026-05-29-presence-based-detection-engine-design.md](2026-05-29-presence-based-detection-engine-design.md) (付録 A: OBS 実機破綻)
- re-plan overview: [2026-05-28-vtuber-region-boundary-replan-design.md](2026-05-28-vtuber-region-boundary-replan-design.md) (P1-P6)
- P1 (基盤・マージ済): [2026-05-29-p1-robust-scorebar-localization-design.md](2026-05-29-p1-robust-scorebar-localization-design.md)
- #809 wiring (再利用): [2026-05-27-vtuber-pass1-region-wiring-design.md](2026-05-27-vtuber-pass1-region-wiring-design.md)
- 現行コード: `allaganeye/video/detector.py` (`detect_match_boundaries` / brightness Pass1/2 / `_has_scorebar_v2` / `_filter_and_extract_segments` / `_drop_post_match_trailing`), `scorebar.py` (`filter_blackouts_with_scorebar` / `classify_blackout` / `_is_static_from_frames`), `capture_region.py` (`localize_scorebar` / S3), `presence.py` (Phase 1 資産)
- 関連 issue: [#480](https://github.com/Idios/kobutachan-allaganeye/issues/480) (分類・Stage 2 に再マップ), [#481](https://github.com/Idios/kobutachan-allaganeye/issues/481) (minimap・範囲外), [#805](https://github.com/Idios/kobutachan-allaganeye/issues/805) (trailing 非破壊化・別 phase), [#809](https://github.com/Idios/kobutachan-allaganeye/issues/809) (wiring 再利用), [#810](https://github.com/Idios/kobutachan-allaganeye/issues/810) (metadata region・P6), [#753](https://github.com/Idios/kobutachan-allaganeye/issues/753) (re-plan umbrella)
