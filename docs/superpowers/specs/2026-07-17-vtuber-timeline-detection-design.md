# VTuber 試合分割 再設計: presence×motion timeline segmentation (2026-07-17)

> **Status**: design (Idios 承認 2026-07-17: PoC 先行 / 段階式 6 source 検証 / 案 1 timeline segmentation / issue 整理 = 新 issue 1 本 + 既存へ経緯 comment)
> **Supersedes**: [two-signal spec](2026-05-31-l3-detection-rearchitecture-two-signal-design.md) §8 Phase 3-4 の VTuber 部分 (「Stage 2 分類器 + motion AND 配線」による blackout-candidate 起点の VTuber 検出)。OBS/masked に関する同 spec の決定 (brightness 主軸・v2 温存・`--vtuber` 明示 flag) はすべて**維持**する。
> **根拠データ**: [2026-07-17 PoC 計測レポート](2026-07-17-vtuber-timeline-detection-poc-report.md) (6 source、gyawa 6/6 + きゅま 11/11 再構成)
> **関連 issue**: #480 (P4) / #809 / #866 (Phase 3-4 追跡) — 本設計が supersede、経緯 comment を各 issue に記録。実装追跡は新 issue (起票時に spec リンク)。

## 1. 問題の再定義

失敗 3 連鎖の教訓 (詳細は PoC レポート冒頭):

| # | 失敗 | 教訓 (本設計への反映) |
| --- | --- | --- |
| ① | presence 全置換が OBS で破綻 (リザルト画面の紋章で連続試合マージ) | OBS path には一切触れない。リザルト対策として motion を presence に AND する |
| ② | auto layout 判別が OBS bit-exact を破壊 | `--vtuber` 明示 flag を維持 (auto 推論は導入しない) |
| ③ | `--vtuber` band-crop blackout generator が under-detect (4h01m で ~11 試合 → 5 segment) | **境界候補 generator 自体を転換**: blackout 起点 → timeline 起点。PoC で境界 blackout は 1-3s しかなく sample 格子をすり抜けると実証 |

核心: VTuber VOD では「暗転」が境界の主信号ではない。**「試合中である」ことの連続的な証拠 (scorebar presence ∧ 画面運動) の timeline を作り、その連続区間を試合として切り出す**方が、変則的な遷移の「型」への依存を断てる。

## 2. アーキテクチャ: V0-V4 (すべて `--vtuber` gate 内)

```text
入力動画 (--vtuber 指定時のみ。OBS default / --masked は現行 path 完全不変)
  │
  ├─ V0: anchor 解決        consensus_scorebar_localization (#822 資産) を VTuber 専用
  │                          パラメータで呼ぶ: 48 samples / conf 事前フィルタ 0.5 / min hits 5。
  │                          masked の 24 / 0.7 / 5 は流用しない (Onsal の true hit は
  │                          median conf 0.589 で 0.7 filter に届かず anchor が枯れる、PoC §3)
  │                          失敗時: 現行 band-crop blackout path へ縮退 + warning
  │                          (= 現状の --vtuber 挙動が floor。#824 縮退契約に従う)
  │
  ├─ V1: timeline scan      10s stride で全域 probe。probe = 1920x1080 フレーム 1 対 (Δ0.5s):
  │                          at-anchor presence (localize_scorebar_at_anchor、conf gate なし)
  │                          + band MAD (anchor 帯)。probe データモデルは (t, present, band_mad)
  │                          (band brightness は PoC 診断用でモデル外。V3 blackout snap は自前 dense probe で測る)
  │
  ├─ V2: 粗分割             probe evidence = present ∧ band_mad ≥ MAD_MIN
  │                          rolling window W=9 probes、quorum K=2 → in-match run 抽出
  │                          → min_match_duration (300s、既存 config) 未満を除外
  │
  ├─ V3: 境界精緻化 + merge 裁定
  │                          (a) 隣接 segment 間 gap ≤ 300s を 1s stride で dense re-probe:
  │                              anchor rate ≥ MERGE_RATE (初期値 10%) → 偽分割 → merge
  │                              ~0% → 真の境界として確定
  │                              gap 内に凍結 run (band_mad < FROZEN_MAX 持続) または band blackout
  │                              があれば merge 禁止 (positive marker 優先)
  │                          (b) 境界 snap: 確定境界の gap 内に band blackout があれば
  │                              0.25-0.5s 精度で blackout エッジへ snap (Pass 2 相当の局所 probe)。
  │                              なければ presence 崩壊点/回復点 (refine_boundary 二分探索) へ
  │
  └─ V4: segment 検証        masked L2 と同型 (scan_presence 15 点 quorum、sample_fn = at-anchor)
                             + fail-safe: 全 segment 削除になる場合は全件 keep + warning
                             + 30min 超 segment に低信頼フラグ (result-merge 型見逃しの可視化)
                             → metadata.json (matches[] 現行 schema + capture_regions #810)
```

> **erratum (2026-07-19, P2 実装)**: V3 (b) の「presence 崩壊点/回復点 (refine_boundary 二分探索)」は
> **gap dense 系列 (1s) のエッジ検出に置換**した。at-anchor presence は per-frame に非単調
> (Onsal 40-60%) で二分探索の単調性前提が成立しないため。1s 系列の先頭/末尾 present run
> エッジで +-1-2s 精度を得る (実装: `snap_segment_edges`)。
> **blackout snap も同じ 1s 系列に対して行う**: 「0.25-0.5s 精度」の局所再 probe は
> +-15s gate (sec.3.2) に対して over-engineering のため不採用 (P2 final review で
> dead constant SNAP_STRIDE を撤去)。

### 2.1 パラメータ (初期値と根拠)

| パラメータ | 初期値 | 根拠 (PoC) | 校正方針 |
| --- | --- | --- | --- |
| V1 stride | 10s | 6 source で試合構造を再現。4h VOD ≈ 1450 probes ≈ 3-6 分 (CPU 16 workers、§3.2 の性能突合基準と同値) | 固定 |
| MAD_MIN | 1.5 | 試合中最低 band_mad ≥ 2.2 vs 凍結画面 ≤ 0.83 (きゅま)。湿気で rule A の 61min 誤マージを解消 | Phase 3 で 6 source 分布から再確認 |
| W / K | 9 probes / 2 | Onsal 弱 presence (20s bucket 最低 25%) を bridge しつつ lobby (~1%) を弾く | 同上 |
| MERGE_RATE | 10% | FN run ~24% vs 真 lobby ~1.5% (1s stride、15 倍分離) | 同上 |
| FROZEN_MAX | 1.0 | 凍結 staging/リザルト静止部 band_mad 0.13-0.83 | 同上 |
| merge 対象 gap 上限 | 300s | 観測された FN run 最大 ~250s。300s 超 gap は真の境界のみ (gyawa lobby 600s 等) | 固定 (min_match_duration と同値) |
| V0 anchor (samples / conf / min hits) | 48 / 0.5 / 5 | Onsal true hit 率 ~21% (conf≥0.5) で期待 ~10 hits。conf 0.7 (masked 値) は true hit median 0.589 を殺す (PoC §3) | Phase 3 で 6 source 縮退率を確認 |

**共通パラメータ原則 (R6 対策)**: per-source チューニングは禁止。6 source 全部を同一パラメータで通すことを gate とする。conf gate は使わない (PoC 結果 2: ソース非可搬)。

### 2.2 変更しないもの (構造保証)

- OBS default path / `--masked` path / `_flag_post_match_trailing` / v2 分類器: **コード経路として一切非接触**。`--vtuber` 分岐の内側だけを差し替える (二重 gate: flag なし = 現行 path が構造的に保証される。教訓 ①②)。
- V0 縮退時の floor = 現行 `--vtuber` band-crop blackout path (現状より悪化しない)。
- 音声: 不採用 (PoC 結果 5)。`AUDIO_FROZEN` に変更なし。
- VTuber の post_match trailing flag (#797/#805): 現行どおり非適用のまま (two-signal §8.1 P2-d の gate-off を timeline path も踏襲。早期 return により構造的に非適用)。導入判断は P3 / scope 外。
- fps filter 非使用: V1/V3 はすべて `-ss` 単発 probe (#575 制約の影響を受けない)。

### 2.3 実装配置

- 新規: `allaganeye/video/vtuber_timeline.py` (V0-V3 オーケストレーション + パラメータ定数)。V0/V4 は既存 primitive (`capture_region.py` / `presence.py`) を呼ぶ。
- `detector.py` の `--vtuber` 分岐: **分岐先頭で V0 (timeline 専用 anchor consensus、48/0.5/5) を試行**し、成功時は V1-V2 (timeline path) の結果を返す。V0 不成立 / probe 過半 UNKNOWN / **V2 産出 segment ゼロ** のときのみ、既存 Stage 0 (`_resolve_detect_region`) + band-crop blackout path へ縮退する (既存 Stage 0 の consensus は timeline の gate ではない — 別物の consensus であることに注意)。空 segment を authoritative にすると legacy 検出の機会を奪い floor が破れるため、空 = timeline 不能として扱う (Codex adversarial-review 2026-07-18 HIGH の反映。detector 側にも空 boundaries 拒否の defense-in-depth gate を置く)。
- **cache key**: 新 param `vtuber_algo` (`_VTUBER_ALGO_VERSION`、masked_algo と同型の algo バージョン識別子) を `_save_cache` / `_load_cache` / verbose の 3 箇所に追加 (`feedback_detection_flag_cache_key` 遵守。#823/#830 で 2 回摘出された死角)。legacy `--vtuber` cache は識別子欠落 → miss として再検知。
- metadata: `matches[]` 現行 schema 不変。`capture_regions.coarse` は band (現行どおり)。V4 の低信頼フラグ・merge/削除統計は `warnings` / stats に記録 (#805 の痕跡記録と同型)。

## 3. 検証戦略

### 3.1 unit (動画不要)

- V2 粗分割: 合成 evidence 列 → 期待 segment (FN run bridge / lobby バースト除外 / duration prior)。
- V3 merge 裁定: 合成 dense 系列 (FN run 型 / lobby 型 / 凍結 marker 型) → merge/keep 判定表。
- V3 snap: blackout あり → エッジ snap、なし → presence 境界。
- V4 fail-safe: 全滅 → keep + warning。
- cache key: mode-switch / legacy 後方互換 (既存テストパターン踏襲)。

### 3.2 実機 gate (Phase 3、slow)

- **OBS 5 baseline bit-exact**: flag なし実行で現行完全一致 (構造保証の実測確認)。
- **masked 3 サンプル**: 現行出力不変。
- **非 VTuber 性能退行の実測**: OBS baseline 1 本以上で detect wall-time を現行 (本 spec 適用前 commit) と比較し、差がノイズ範囲 (±10% 目安) であることを確認。「経路非接触だからゼロ影響のはず」を無検証にしない (import コスト・分岐追加を含む実測)。VTuber 実行時間も PoC 見積もり (4h VOD ≈ 3-6 分 / CPU) と乖離しないことを記録。
- **VTuber GT 突合**: gyawa 6 試合 (GT 漏れ分を追加注釈) + きゅま 11 試合で matched/missed/spurious = 全一致/0/0、境界誤差 ≤ ±15s (zone-in 基準、10s stride + snap 後)。
- **残り 4 source**: 境界 GT を注釈し (コンタクトシート法、PoC レポート §7.2 の手順)、同一パラメータで recall 100% / spurious 0 を確認。
- GT 規約: zone-in 基準に統一 (PoC レポート §7.3)。gyawa 既存 GT は Phase 3 で再注釈 (漏れ試合追加 + 基準統一。ファイル更新は `docs/testing-guide.md` の SHA-256 台帳更新を伴う)。

## 4. リスク

| # | リスク | 緩和 |
| --- | --- | --- |
| R-a | 未知レイアウトで anchor 不成立 (V0 失敗) | 現行 path へ縮退 + warning (floor 保証)。縮退率を stats で可視化 |
| R-b | 試合中 FN run が 300s 超 → merge 裁定の対象外で偽分割残存 | 6 source 実測最大 ~250s。残存時は V4 の隣接 segment 低信頼フラグで可視化 (silent 誤りにしない) |
| R-c | inset 位置が VOD 内で移動 | きゅま (移動が疑われた唯一の source) の実測で非発生 (PoC §7.5)、他 5 source は per-video anchor 解決 + 全域 segmentation 成立 (PoC §1/§4) で間接確認。将来 per-segment anchor (#810 `segments[]`) で拡張 |
| R-d | リザルト/staging が present∧moving に見えて連続試合がマージ | motion AND + blackout snap + 30min 低信頼フラグの三重防御。gyawa/きゅま実測ではマージ 0 |
| R-e | 非 FL コンテンツ (CC 等) の誤検出 | at-anchor は emblem 3 点 AND (FL 特異)。V4 quorum が backstop。非 Onsal マップ分布は Phase 3 で確認 |
| R-f | V1 の計算コスト (8h VOD ≈ 3000 probes ×2 frames) | PoC 実測 6-10 分 (CPU)。現行 3s 格子 Pass1 より probe 数は少ない。GPU 化は将来最適化 (scope 外) |
| R-g | 10s stride が短時間コンテンツ (途中参加の数分試合) を取り逃す | min_match_duration 300s が下限を規定 (仕様として文書化)。300s 未満の部分試合は対象外 |
| R-h | 振り返り/replay パート (試合 footage の再生) が偽試合化 | きゅま実測 (PoC レポート §7.4): 静止表示は frozen で棄却、再生 footage は縮小/オフセットで at-anchor を外れ棄却 → evidence 0/27 で正しく除外。**ほぼ 1:1 スケール・無停止・300s 超の再生は原理的に騙されうる** (既知の限界として文書化。Phase 3 GT 注釈時に各 source の振り返り有無を記録し、発生時は V4 低信頼フラグ相当の可視化を検討) |

## 5. Phase 分解 (各 1 PR、TDD)

| Phase | 内容 | gate |
| --- | --- | --- |
| **P1** | `vtuber_timeline.py` V0-V2 (anchor + scan + 粗分割) + detector 配線 + cache key + unit | OBS bit-exact (flag なし) + gyawa/きゅま粗分割が PoC 模擬と一致 |
| **P2** | V3 (merge 裁定 + 境界 snap) + V4 (L2 検証流用 + フラグ) + unit | きゅま 11/11 (偽分割解消) + gyawa 6/6 |
| **P3** | 6 source GT 注釈 + 実機 gate 一式 + `--vtuber` hidden 解除判断 + doc (cli-spec / output-spec / detection-map / CLAUDE.md) | §3.2 全 gate + Idios 実機確認 |

PoC 計測スクリプトは本 spec と同一 PR の `tests/scripts/poc_vtuber_timeline/` に含まれる (レポートの再現経路)。

## 6. 未確定 (実装時に AskUserQuestion)

- `--vtuber` hidden 解除 (help 文言変更) のタイミング: P3 gate 通過後を想定、リリース判断は Idios。
- gyawa 再注釈 GT の部分試合 (250-1250、録画開始時点で進行中) の期待挙動: 検出対象とするか除外規約とするか。
- GUI (L2) への `--vtuber` トグル露出: 本 spec scope 外 (別 issue)。
- gyawa さんへの協力打診 (#866 記載のトリガー): VTuber 対応の実装着手をもって「再開」とするかは Idios 判断。

## 7. Erratum (P3 実装由来)

### 7.1 MERGE_RATE: 0.10 -> 0.15 (P3 4周目)

当初値 0.10 は FN run ~24% vs 真 lobby ~1.5% の 15 倍分離を根拠に設定した (§2.1)。
P3 実機 gate で shirurori の meteor replay gap (presence rate ~0.137) が merge 側に
倒れることを実測。gap 内に物理的な試合境界 (zone-in blackout) が実在するにもかかわらず
merge が発生したため、Idios 承認 (2026-07-21) の下 0.15 に引き上げた。
FN run vs lobby の分離は引き上げ後も十分 (0.24 vs 0.015 の 16 倍)。

### 7.2 blackout-peek unmerge override の追加 (P3 4周目)

§2 V3 (a) は「gap 内に凍結 run または band blackout があれば merge 禁止」と記述したが、
P3 実機で merge 裁定が行われた後に gap 後半 (中点以降) または直後 45s の zone-in
blackout run (>=2 probe、band brightness <= 30) を検出して merge を取り消す
**blackout-peek override** が追加された。
根拠: 次試合の zone-in 暗転 = 物理境界の実在を示す正の証拠であり、presence rate
の弱い信号より信頼性が高い。この override により MERGE_RATE 引き上げと組み合わせて
偽 merge を構造的に解消した。

### 7.3 snap 規則の再設計: start=zone-in blackout 明け優先 / end=evidence collapse 専用 (P3 2周目)

spec §2 V3 (b) の snap 規則を以下の通り改訂した:

- **start 側**: gap 内の境界 blackout run (zone-in 暗転) の明け (= blackout 末尾) を
  優先採用する。in-match 瞬断 blackout (前後 5s または 10s に evidence が近接) は除外する。
  blackout がない場合は evidence run 先頭 + gap 中点制約にフォールバック。
  probe 窓は前方 45s (EDGE_EXT_S)、長 gap では後方 120s (LONG_GAP_START_BACK_S)。
- **end 側**: evidence run 末尾 (collapse) のみを使用する。in-match 瞬断 blackout が
  end 方向にも存在するため、blackout を end snap に使うと試合終了を誤って早める。
  probe 窓は後方 120s (EDGE_EXT_END_S)。

「なければ presence 崩壊点/回復点 (refine_boundary 二分探索)」は P2 実装時点 (P2
erratum §2 冒頭) で既に gap dense 系列のエッジ検出に置換済みであり、本改訂は
start/end の非対称化と blackout 優先の明文化である。

### 7.4 GT gate の非対称 tolerance 化 (P3 実機 gate)

spec §3.2 の「境界誤差 +-15s」対称 tolerance を以下の非対称 gate に改訂した
(Idios 承認 2026-07-22):

- **損失方向** (start が GT より遅い / end が GT より早い = 試合内容の欠落): tolerance **15s**。
- **余分方向** (ロビー / result 画面が混入): tolerance **300s**。

設計根拠: 製品 invariant = 「試合内容の損失ゼロ」を直接符号化する。ロビー混入は
ユーザーが手動でトリムできるが、試合内容の欠落は取り戻せない。

6 source / GT 67 試合での実測結果: recall 100% (67/67、missed 0) / spurious 0。
内訳: gyawa 6 / kyuma 11 / meteor 14 / shikke 16 / shinryu 12 / shirurori 8
(SSoT = `tests/baselines/v0.3.0/vtuber-gt/*.json` の `matches[]` 総数)。

### 7.5 V2 hard-gap break は不採用: 短 gap known-limitation として残存 (P3)

試合間 gap が ~70s 未満の場合、V2 rolling window (TIMELINE_WINDOW=9、stride 10s) が
構造的に橋渡しし 2 試合が 1 segment に結合されうる (6 source 中 1 境界で実測)。
当初 V2 に hard-gap break を追加する案を検討したが、Onsal マップのダウンタイム (FN
run 120s+) が誤 break を引き起こす副作用があり採用しなかった。
GT 側に `expected_merge_with_next` 注釈を付与して既知 limitation として管理する。
