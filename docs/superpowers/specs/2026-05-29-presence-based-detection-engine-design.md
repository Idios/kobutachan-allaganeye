# presence ベース検出エンジン 設計 (2026-05-29)

> L3 VTuber 対応の再々設計。re-plan ([#753](https://github.com/Idios/kobutachan-allaganeye/issues/753)) の
> **P2「scorebar-anchored 領域検出」** から、2026-05-29 のブレストで
> **「scorebar 有無 (presence/absence) を OBS/VTuber 共通の唯一の検出信号とする core 検出エンジン置換」**
> へ方針転換した結果をまとめる。本 spec は re-plan の **P2 / P3 / P4 (#480) を統合し supersede** する。
> P1 (robust scorebar localization, PR #811 マージ済) を基盤として再利用する。

## 1. 背景と方針転換

### 1.1 出発点 (re-plan P2)

re-plan の依存鎖は **P1 (localize) → P2 (region 検出) → P3 (region crop で brightness 検出) → P4 (region-aware 分類 #480)** だった。
P2 は「scorebar 幾何を anchor に game 矩形を求め、その crop で brightness Pass1 を回して overlay 汚染を除く」ことを狙っていた。

### 1.2 ブレストでの転換

設計対話 (2026-05-29) で以下を順に確定し、P2 の前提自体が不要になった。

1. **エッジ導出 = scorebar のみ (案 A)**: game 矩形の左右・下端を脆い extent 信号 (S3) から導出しない。
2. **検出信号 = scorebar 有無に昇格**: 「scorebar present = FL 試合中」を直接の match-membership 信号にする。
   region crop も brightness Pass1 も不要になり、検出と分類 (#480) が 1 信号に統合される。lobby (明るいが scorebar 不在) も捕捉できる。
3. **OBS も全面 presence 化 + 再 baseline**: OBS/VTuber を統一パイプラインにし、現行の bit-exact hard gate を撤廃する。
4. **進め方 = GT 突合・検証先行カットオーバー**: released 経路を未検証コードで一括置換しないため、offline 検証ハーネスを先行させ、ground truth と突合してからカットオーバーする。

### 1.3 結論

brightness ベースの Pass1 検出を撤去し、`localize_scorebar` (P1) の present/absence を OBS/VTuber 共通の検出信号にする。
これは released・検証済みの中核アルゴリズム置換であり、**bit-exact 不変条件の意識的な override** を伴う。
よって「検証してから切替」を構造として spec に組み込む (§7 / §9)。

## 2. スコープと成果物

### 2.1 成果物

- presence ベース検出アルゴリズム (時系列 localize sampling → debounce segment 化 → fine-localize 境界精緻化)。
- offline 検証ハーネス (test 動画で presence 境界を GT / 現行と突合し metric を出す。production 非配線)。
- カットオーバー (brightness Pass1 撤去・再 baseline・bit-exact → GT-accuracy gate・#480 統合・実機検証)。

### 2.2 やらないこと (境界)

- **game region 検出 (原 P2 の game 矩形)**: presence 検出は region を必要としない。region は廃止する。
- **minimap 切抜き ([#481](https://github.com/Idios/kobutachan-allaganeye/issues/481))**: 別レイヤー。必要なら scorebar 幾何から改めて導出する (本 spec 範囲外)。
- **scorebar localization 自体の改良**: P1 で完了済。本 spec は P1 を consumer として使うだけ。
- **metadata schema 変更**: 出力は現行どおり match segments (`matches[]` / `boundaries`)。region フィールドは追加しない。

### 2.3 上位方針 (bit-exact → GT-accuracy)

- 現行の **OBS bit-exact hard gate** (re-plan §5 / P1 §7.1 / #809 等が non-negotiable と宣言) を **撤廃**し、
  **GT-accuracy gate (tolerance ベース)** に置換する。これは本 spec の前提であり、ブレストで明示的に承認された。
- 撤廃理由: bit-exact は「OBS 出力を一切変えない」ことを保証する一方、presence 検出が OBS でも現行以上に正しい場合に **改善を block** してしまう。
  そこで「現行 boundary との一致」ではなく「ground truth との一致」を gate にする。

## 3. 決定事項 (ブレスト 2026-05-29)

| 論点 | 決定 | 根拠 |
| --- | --- | --- |
| エッジ導出 (Q1) | **A: scorebar のみ** (extent から幅・edges を導出しない) | crop 不要化の布石。S3 extent は #809 Wave F で脆い |
| 検出信号 (Q2) | **scorebar 有無 (presence) を検出信号に昇格** | content-fixed・位置独立 (P1 で 5 source 実証)・lobby も捕捉・検出と分類を統合 |
| OBS bit-exact (Q3) | **全面 presence + 再 baseline** (bit-exact gate 撤廃) | 統一パイプライン。bit-exact は better algorithm を block する |
| scope / 検証 (Q4) | **進める + GT 突合・検証先行カットオーバー** | released 経路を未検証置換しない。offline 検証を先行 |
| scorebar 連続性 (domain) | **試合中に短時間消える場面あり** (死亡暗転 / 全画面 UI 等) | debounce / hysteresis 必須 |
| present 定義 (③) | **localize 非 None = present** | emblem-AND は zero-FP 検証済。confidence しきいは false-absent を招く |
| 境界 refinement (⑥) | **fine localize のみ** (brightness 完全排除) | presence 純化。timing は tolerance-based GT gate で吸収 |
| GT (validation) | **VTuber 5 source 全部に手動 GT**、OBS = 現行 baseline | 最強検証。GT-first 方針と整合 |

## 4. アルゴリズム

### 4.1 パイプライン

```text
① video 入力
② time grid (stride S) で probe frame 抽出 → 1920x1080 RGB に resize
③ localize_scorebar(frame) (P1) → 各 sample が present (非 None) / absent (None)
④ debounce / hysteresis (両方向): 短い absent gap と短い present spike を吸収
⑤ segment 化: present 連続 = 試合 / absent 連続 (>= T_gap) = 境界・lobby・非 FL
⑥ 境界 refinement: 各 present<->absent 遷移付近を fine localize (二分探索 / 細 grid) で精緻化 -> t_start / t_end
⑦ 出力: 試合 segment -> metadata.json (現行 schema 同一)。分類 (#480) は present=FL で統合
```

OBS・VTuber とも同一パイプラインを通る。probe frame は常に 1920x1080 RGB に正規化し、`localize_scorebar` が位置独立に scorebar を探す (P1 の契約)。

### 4.2 present 定義

- `localize_scorebar(frame)` が `ScorebarLocalization` を返したら **present**、`None` なら **absent**。
- emblem-AND (GC 紋章 3 点) は #803 negative で zero-FP 検証済のため、非 None 自体が強い present 信号。
- `confidence` は present/absent 判定には使わない。⑥ refinement と診断 / metric にのみ保持する。
- 利点: 背景が明るく emblem 彩度が一時的に下がる等の弱 present frame も拾い、false-absent を避ける。

### 4.3 debounce / hysteresis (両方向)

- **absent gap 吸収**: `T_gap` 未満の absent 連続は in-match として吸収する (試合中の死亡暗転 / 全画面 UI による短時間 None を救済)。
- **present spike 吸収**: `T_min_match` 未満の present 連続は試合とみなさず破棄する (試合外の偶発 present / FP を救済)。
- 実 boundary = `T_gap` 以上の absent run。実 match = `T_min_match` 以上の present run。

### 4.4 segment 化

- debounce 後、present run を試合 segment、absent run (>= T_gap) を非試合 (境界 / lobby / 非 FL) とする。
- 検出と分類が統合される: 「present = FL 試合中」が成立するため、従来 `filter_blackouts_with_scorebar` (#480) が担っていた match_boundary / in_match / non_fl 分類は presence 信号に吸収される。

### 4.5 境界 refinement (fine localize)

- coarse scan が present sample `t_i` と absent sample `t_{i+1}` の遷移を検出したら、`(t_i, t_{i+1})` 区間を fine localize (二分探索 or 細 grid) で再評価し、scorebar の出現 / 消失点を `T_tol` 精度で特定する。
- brightness は一切使わない。よって presence 遷移エッジは現行 brightness blackout エッジと厳密一致しない。
  splitting は keyframe + padding で数秒のスラックを吸収するため、`T_tol` 精度で実用十分 (§7.3 / §8)。

### 4.6 パラメータ (harness で校正)

| param | 意味 | 暫定 | 制約 |
| --- | --- | --- | --- |
| `S` | coarse grid stride | 3-5s (or Pass1 の adaptive `sample_interval` 流用) | `S < min 試合間 gap` (gap を 1-2 sample で捕捉) |
| `T_gap` | 境界とみなす最小 absent 長 | harness 校正 | `max mid-match 不在 < T_gap < min 試合間 gap` |
| `T_min_match` | 試合とみなす最小 present 長 | harness 校正 | 試合最短長より短く、FP spike より長い |
| `T_tol` | GT 突合の許容 boundary 誤差 | harness 校正 (秒オーダー) | split padding 内に収まる |

暫定値の根拠 (prior art): 現行 `min_blackout_duration` / `_REFINED_MIN_BLACKOUT` (短い in-match 暗転の除外しきい)。最終値は §7 ハーネスで実測校正する。

## 5. データ構造 / API

- **再利用 (P1)**: `localize_scorebar(frame: np.ndarray, *, stride, target_ratio) -> ScorebarLocalization | None` (`allaganeye/video/capture_region.py`)。
  入力は 1920x1080 RGB frame。`ScorebarLocalization(x_left, x_right, y_top, y_bottom, confidence)` は probe px。
- **新規 (本 spec)**: presence sampling → debounce → segment 化 → fine refinement を行う検出関数群。
  既存 `detect_match_boundaries` (brightness) と並置する新モジュール / 関数として Phase 1 で追加し (additive)、Phase 3 で production を切替える。
- **出力**: 試合 segment (start/end) のリスト = 現行 `boundaries` / `matches[]`。metadata.json schema は不変。

## 6. 性能

- `localize` は 1920x1080 RGB + OpenCV (HSV / Sobel / y-scan) で、現行 brightness Pass1 (320x180 grayscale 平均) より大幅に重い。長尺 (2-3h) では本処理がコスト主因。
- 緩和:
  - 試合は分オーダーに長いため coarse scan は中程度 stride `S` で十分。dense sampling は遷移付近の ⑥ refinement のみ。
  - decode を並列化 (現行 `ThreadPoolExecutor` 同様)。`gpu_detector.py` の chunked decode 基盤を 1920x1080 frame 取得に再利用可能。
  - 必要なら安価な pre-filter (例: 上部帯の彩度) で localize 呼び出しを間引く (YAGNI、harness で必要性判断)。
- ハーネスで実 wall-time をベンチし、`S` と pre-filter を性能レバーとする。

## 7. OBS / 検証 / カットオーバー

### 7.1 検証ハーネス (offline・production 非配線)

- test 動画ごとに presence 検出を実行し、検出 boundary を GT / 現行アルゴリズムと突合。
- metric: matched / missed / spurious match 数、boundary 誤差分布、localize recall/precision、wall-time。

### 7.2 GT (ground truth)

- **OBS**: 現行の検証済 5 baseline をそのまま GT に使う (release 済の正解 boundary)。
- **VTuber**: 5 source すべてに Idios が手動で match 境界 (各試合の start/end) を注釈する (`E:\allaganeye-samples`、guard verify は FP のため owner override 運用 / `PYTHONUTF8=1`)。
- GT 注釈はカットオーバー前に完了させる。

### 7.3 GT-accuracy gate (tolerance ベース)

- bit-exact gate を撤廃し、以下を gate とする:
  - **OBS**: 5 baseline の全 match を検出 (missed/spurious ゼロ)、各 boundary 誤差 <= `T_tol`。
  - **VTuber**: 手動 GT に対し match recall / precision が目標値 (harness で設定) を満たす。
- 「再 baseline」は新 presence エッジを GT として凍結する操作であり、missed/spurious ゼロ確認後にのみ行う (誤りを真値固定しない)。

### 7.4 カットオーバー手順

1. presence 検出で production の brightness Pass1 を置換。
2. 新 baseline を生成 (上記 gate 通過確認後に凍結)。
3. bit-exact 回帰テストを GT-accuracy (tolerance) テストに置換。
4. 分類 (#480) を presence 信号に統合 (`filter_blackouts_with_scorebar` の役割を整理)。
5. Idios の実機検証 (OBS + VTuber、Iron Law 6)。

## 8. テスト戦略 / 受け入れ条件

### 8.1 unit (動画不要)

- debounce / segment 化: 合成 present/absent 列 (短 gap / 短 spike / 通常 / lobby) → 期待 segment。純関数。
- 境界 refinement: 合成遷移 → 期待 t_start/t_end (`T_tol` 内)。

### 8.2 harness (slow・sample-gated)

- 全動画 presence 検出 vs GT。OBS 5 + VTuber 5。matched/missed/spurious、boundary 誤差、wall-time を出力。

### 8.3 受け入れ条件 (issue 化時の原型)

- presence (localize 非 None) + debounce + fine refinement で試合 segment を出力する。
- OBS: 現行 5 baseline の全 match を検出、missed/spurious ゼロ、boundary 誤差 <= `T_tol`。
- VTuber: 手動 GT に対し recall/precision が目標値以上。
- bit-exact gate を GT-accuracy (tolerance) gate に置換。
- brightness Pass1 を検出経路から撤去。
- Idios の実機検証 (OBS + VTuber) 完了。

## 9. 段階分解 (Phase 1-3)

| Phase | 内容 | production 影響 | gate |
| --- | --- | --- | --- |
| **1** | presence 検出アルゴリズム + offline ハーネス (additive・非配線)。OBS 即検証 (GT=現行 baseline) | なし (baseline 不変) | OBS GT-accuracy 通過 |
| **2** | VTuber GT 注釈 (5 source) + VTuber 検証。`T_gap`/`S`/`T_tol` 校正 | なし | VTuber GT-accuracy 通過 |
| **3** | カットオーバー (§7.4)。brightness Pass1 撤去・再 baseline・gate 置換・#480 統合・実機検証 | あり (検出エンジン置換) | 全 GT-accuracy + 実機検証 |

Phase 1/2 = 検証、Phase 3 = 切替。これがブレストの「検証してから切替」の構造実装。各 Phase は独立 PR。

## 10. リスク

| # | リスク | 緩和 |
| --- | --- | --- |
| R1 | bit-exact 撤廃で OBS regression を見逃す | GT-accuracy gate (現行 baseline=GT、missed/spurious ゼロ) + 実機検証。Phase 1 で OBS 即検証 |
| R2 | localize FN (検出漏れ) が `T_gap` を超え実試合を誤分割 | debounce で短 FN 救済。長 FN は harness で localize recall 実測し閾値 / pre-filter 調整 |
| R3 | localize FP (試合外 present) で false match | emblem-AND zero-FP + `T_min_match` spike 吸収。harness で precision 実測 |
| R4 | 性能 (localize 重い・長尺) | coarse stride + 並列 + GPU chunked decode 再利用。harness ベンチ |
| R5 | 再 baseline で誤りを真値固定 | GT-first (missed/spurious ゼロ確認後に凍結)。Idios 実機検証 |
| R6 | presence エッジ != brightness blackout エッジ (split padding 前提変化) | `T_tol` + keyframe/padding で吸収。harness で boundary 誤差分布確認 |
| R7 | post-match trailing ([#805](https://github.com/Idios/kobutachan-allaganeye/issues/805)) との関係 | presence では「scorebar 不在 = 試合外」が明示化され #805 の弱い否定信号問題が改善する可能性。逆に localize FN で実 trailing を切る risk は残る。harness で確認し #805 とリンク |

## 11. 未確定 (Iron Law 2 / 5 で user 承認後に確定)

- **issue 起票 / 編集**: 本件は re-plan の「#809 `detect_coarse_region` 再設計」ではなくなった。
  presence 検出エンジンの新 umbrella + Phase 1-3 の sub-issue を起票し、#480 (分類) を subsume、park 済 #809 を redefine / close する案。issue 操作を伴うため起票時に `AskUserQuestion` で確認する。
- **閾値の最終値** (`S` / `T_gap` / `T_min_match` / `T_tol`): harness 校正で確定。
- **VTuber GT 目標値** (recall/precision): harness 実測後に設定。

## 12. 参照

- re-plan overview: [2026-05-28-vtuber-region-boundary-replan-design.md](2026-05-28-vtuber-region-boundary-replan-design.md) (本 spec が P2/P3/P4 を supersede)
- P1 (基盤・マージ済): [2026-05-29-p1-robust-scorebar-localization-design.md](2026-05-29-p1-robust-scorebar-localization-design.md) (§8.7 multi-source 実証、localize API)
- Phase 2a: [2026-05-26-vtuber-capture-region-detection-design.md](2026-05-26-vtuber-capture-region-detection-design.md) (§6.3.1 注1 span→幅 不成立 / 注3 OBS↔inset 単フレーム不可)
- #809 wiring (park): [2026-05-27-vtuber-pass1-region-wiring-design.md](2026-05-27-vtuber-pass1-region-wiring-design.md)
- 現行コード: `allaganeye/video/capture_region.py` (`localize_scorebar` / `ScorebarLocalization`), `allaganeye/video/detector.py` (`detect_match_boundaries` / brightness Pass1 / emblem 定数), `allaganeye/video/scorebar.py` (`filter_blackouts_with_scorebar` = #480 分類), `allaganeye/commands/detect.py` (metadata 出力)
- 関連 issue: [#480](https://github.com/Idios/kobutachan-allaganeye/issues/480) (分類・本 spec が subsume), [#481](https://github.com/Idios/kobutachan-allaganeye/issues/481) (minimap・範囲外), [#805](https://github.com/Idios/kobutachan-allaganeye/issues/805) (post-match trailing), [#809](https://github.com/Idios/kobutachan-allaganeye/issues/809) (park・redefine 候補), [#753](https://github.com/Idios/kobutachan-allaganeye/issues/753) (re-plan umbrella)

## 付録: Phase 1 実機検証結果と Q3 決定の改訂 (2026-05-30 追記)

> Phase 1 (presence 検出アルゴリズム + offline 検証ハーネス) を実装し
> (branch `claude/l3-p2-region-detection`、presence.py + presence_harness.py、
> unit/lint/型/レビュー全 pass)、OBS 実動画で受け入れゲートを実行した結果、
> **本 spec の中核決定 (§3 Q3「brightness Pass-1 を撤去し presence 単独に全置換」)
> が OBS では不適切**と実証された。以下に記録し、アーキテクチャを再ブレストする。

### A.1 OBS gate 実機結果 (obs-20260209、20.6GB / 57min)

- **性能 OK**: `detect_matches_by_presence` (stride=4s, workers=8) が 3m16s で完走 (spec §6 の性能懸念クリア)。
- **精度 FAIL**: `ComparisonResult(matched=1, missed=2, spurious=1)`。検出できた 1 試合の境界誤差は 0.5–2.5s と高精度 (機構は正しい、**signal が不足**)。

### A.2 根本原因: リザルト画面の偽 presence (データ実証)

presence (scorebar 有無) は、試合直後の**リザルト/順位画面が同じ GC 紋章を表示する**ため、連続試合を分離できない。キャッシュ samples 解析 (再 probe なし):

| 区間 | present% | conf 中央値 |
| --- | --- | --- |
| GT1 試合 | 98% | 0.60 |
| inter 1→2 (リザルト画面) | **91%** | 0.42 ← 偽 presence |
| GT2 試合 | 94% | 1.00 |
| inter 2→3 (正常 lobby) | 13% | 0.06 |
| GT3 試合 | 99% | 0.92 |

- inter 1→2 の 91% present が GT1↔GT2 を橋渡し → 閾値スイープで GT1+GT2 が 1 ブロックにマージ。
- **confidence 閾値では分離不能** (GAP1→2 を下げる閾値で GT1 も崩壊、分布が重なる)。
- **absent gap 長でも分離不能** (試合間 gap ≈ mid-match 中断 ≈ 8–20s)。spec §4.3 の debounce 前提 (max mid-match 不在 < T_gap < min 試合間 gap) が実データで破れている。

### A.3 決定的データ: 既存 brightness 検出器は OBS で完璧

`tests/baselines/v0.3.0/obs-20260209.metadata.json` (既存 brightness Pass-1 + scorebar 分類) は同動画で 3 試合を**秒未満精度**で検出: M1 40.25..1076.125 / M2 1252.25..2324.5 / M3 2504.0..3370.75 (GT 40..1076 / 1252..2324 / 2504..3370)。**brightness blackout は真の試合境界 (リザルト画面の手前) に存在し、既存検出器はそれを正しく使えている**。presence がマージしたのは、この blackout 信号を持たないため。

### A.4 設計含意 (Q3 改訂方針)

- **Q3「brightness Pass-1 撤去・全置換」は OBS では不適切**。brightness 境界は撤去すべきでない。
- presence/localize_scorebar の真価は「全置換の検出器」ではなく、**位置独立で頑健な分類器 + VTuber 経路**にある。
- → re-plan #753 全体 (P1〜P6 の依存・presence の位置づけ) を改めて brainstorm し直す (本 addendum を起点)。

### A.5 Phase 1 コード資産の扱い

- `allaganeye/video/presence.py` + `tests/presence_harness.py` (+ 3 test files) は branch にコミット済・production 非配線。**revert 不要**。再アーキテクチャ下で資産として残す:
  - `localize_scorebar` 由来の presence 信号 = 頑健な分類器の核。
  - offline 検証ハーネス (`compare_segments` / GT 突合) = 今後の検証インフラ。
  - `segment_presence` / `refine_boundary` = blackout 境界と組む際に再利用候補。
- 新アーキテクチャの spec / plan は別ドキュメントで起こす。
