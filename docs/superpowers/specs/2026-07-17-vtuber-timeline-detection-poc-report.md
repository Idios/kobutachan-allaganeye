# VTuber 試合分割 PoC 計測レポート: 境界信号の実測 (2026-07-17)

> **Status**: 計測完了 (session vigilant-allen)
> **目的**: #480 deferred コメント (2026-06) の「brightness-blackout 主軸では VTuber 試合境界を安定検出できない。静止画面 / UI 遷移ベースなど別アプローチの研究が必要」を受け、実 VOD 6 本で境界に存在する機械検出可能な信号を計測し、設計 ([2026-07-17 design spec](2026-07-17-vtuber-timeline-detection-design.md)) の根拠を確立する。
> **経緯**: 失敗 3 連鎖 = ①presence 全置換の OBS 破綻 ([presence spec](2026-05-29-presence-based-detection-engine-design.md) 付録 A) → ②auto layout 判別の OBS bit-exact 破綻 ([two-signal spec](2026-05-31-l3-detection-rearchitecture-two-signal-design.md) §3.6) → ③`--vtuber` band-anchor + blackout generator の under-detect (#480、hidden flag 化)。

## 1. 計測データ

| Source | ファイル | 長さ | anchor (y_top/conf) | GT |
| --- | --- | --- | --- | --- |
| gyawa | `E:\videos\gyawa_vatos\2772549129-*.mp4` | 2h43m | y=126 / 1.0 | 既存 5 試合 (tests/baselines/v0.3.0/vtuber-primary-ground-truth.json) + 本 PoC で 1 試合の GT 漏れを発見 (§7.1) |
| きゅま (邪竜眼) | `E:\allaganeye-samples\FF14 FL NEWきゅま*.mp4` | 4h01m | y=0 / 0.589 | 本 PoC で 11 試合を注釈 (§7.2)。#480 の under-detect 実測 VOD (5 segment 検出、実 ~11 試合) |
| シルロリ | 同ディレクトリ | 8h04m | y=24 | なし (segment 妥当性のみ) |
| メテオ | 同ディレクトリ | 5h33m | y=42 | なし (同上) |
| Shinryu | 同ディレクトリ | 4h14m | y=66 | なし (同上) |
| 湿気 | 同ディレクトリ | 4h16m | y=90 | なし (同上) |

計測生データ (timeline CSV / dense CSV / fanfare JSON / コンタクトシート / 裁定フレーム) は `E:\allaganeye-samples\_poc_vtuber_retry\` に保存。計測スクリプトは PoC PR の `tests/scripts/poc_vtuber_timeline/` を参照 (scan_timeline / dense_window / simulate_segmentation / analyze_* / contact_sheet / fanfare_scan / pipeline_source)。

計測 primitive はすべて develop-0.3.0 マージ済み資産: `localize_scorebar` (#811) / `localize_scorebar_at_anchor` + `consensus_scorebar_localization` (#822 PR #888) / `_probe_frame_rgb_hires` / `scan_fanfare_hits`。

## 2. 結果 1: blackout は境界信号として構造的に不足 (失敗原因の確定)

- 全域 sparse scan (10s stride、full-frame brightness): 非試合区間の brightness は **86-136** で、blackout_threshold 15 はもちろん band 補正閾値 30 にも一度も届かない。#480 記録の「~121 plateau」を全域で追認。
- 境界に blackout が「存在する」場合もあるが **~1-3 秒** (きゅま t≈1000 / 1165-1185 / 2600 / 3320-3335 / 3550 / 4240 等で band_b が 0 まで落ちる) で、`sample_interval=3s` + `min_blackout_duration=3s` の格子を系統的にすり抜ける。
- 境界遷移の実態はソースごとに変則的: リザルト表 (明るい静止テーブル、~30-90s) / Wolves' Den (群衆で動く) / キュー・メニューウィンドウ (半静止) / 凍結 staging 画面 (scorebar 可視のまま band_mad ~0.2 で 140s 凍結、きゅま 1020-1160) の組合せ。
- → **候補 generator を blackout に限定する限り、分類器の改善では救えない** (#480 の結論を定量確認)。

## 3. 結果 2: at-anchor presence × band motion の分離データ

dense 計測 (1s stride、frame pair Δ0.5s) より:

| 区間 (実態) | at-anchor hit 率 (gate なし) | conf≥0.5 率 | band_mad |
| --- | --- | --- | --- |
| gyawa 試合中 | 99% | **90%** (median 1.0) | 8.5-13.7 |
| gyawa lobby (Wolves' Den) | 22% (バースト 65-70%/20s) | **3%** | 10-25 (群衆で動く) |
| きゅま試合中 (Onsal 通常) | 43-99% | 1-14% (median 0.06-0.43) | 3.4-13.8 |
| きゅま試合中 FN run (AoE 密集) | ~24% | ~0% | 7-12 |
| きゅま lobby | **~1%** | 0% | 2.6-12 |
| きゅま凍結 staging (bar 可視) | 94% | 0% | **0.13-0.28** |
| きゅまリザルト表 (bar 可視) | ~100% | 0% | 3.75-4.07 (mad_full 2.1-2.8) |

読み取り:

1. **conf gate はソース非可搬**: gyawa では完璧 (90% vs 3%) だが、Onsal の 2 行バー光学 (`feedback_fl_scorebar_map_optics` / #822 erratum の 40-60% と整合) では真のバーごと殺す。単一 conf 閾値の全ソース適用は不可能。
2. **gate なし hit 率 + motion (band_mad) の組合せは全ソースで分離**: 試合中 = present∧moving、lobby = absent (hit ~1-22%)、凍結画面 = present∧frozen。
3. lobby の presence バーストは 60-120s の島で、duration prior (300s) の下では試合化しない。

## 4. 結果 3: timeline segmentation 模擬 (6 source)

rule B = probe evidence 「anchor hit ∧ band_mad ≥ 1.5」、rolling window 9 probes (90s) quorum 2、min 300s:

| Source | segments | 妥当性 |
| --- | --- | --- |
| gyawa | 6 (15.7-17.5min) | **GT 全一致** (漏れ試合含む)。境界誤差 dstart +7〜+16s、dend +13〜+28s (staging/リザルト込み。dstart −109/−234s の 2 件は GT が戦闘開始基準のため = staging 含み、OBS の blackout 分割と同じ意味論) |
| きゅま | 15 | 真 GT 11 試合を**全捕捉、見逃し 0、偽 segment 0**。試合中 presence FN run (40-250s、Onsal AoE 密集) による偽分割 4 箇所 → §5 の 1s 裁定で解消可能 |
| シルロリ | 7 (10.3-34.7min) | 概ね妥当。34.7min 1 本は要 spot check (2 試合マージ or 長時間コンテンツ) |
| メテオ | 14 (5.5-21min) | 概ね妥当。短 segment 2 本は途中参加の可能性 (参加型配信) |
| Shinryu | 12 (14.3-20.2min) | 全 segment が FL 試合長として自然 |
| 湿気 | 16 (10.3-17.2min) | **rule A (presence 単独) では 61.2min / 45min / 30.2min の異常マージが発生し、motion AND が構造的に必須なことを実証** |

## 5. 結果 4: 偽分割 (in-match FN run) と真の境界の 1s 判別

きゅまで偽分割を起こした FN run (2660-2960、実態は試合中) と真の lobby (2090-2220) を 1s stride で比較:

| | at-anchor hit 率 | band_mad |
| --- | --- | --- |
| 試合中 FN run | **~24%** (AoE の合間にバーが復帰) | 7-12 (常時戦闘) |
| 真の lobby | **~1.5%** | 2.6-12 |

→ 15 倍の分離。分割点 gap の dense re-probe (anchor rate ≥10% → merge / ~0% → 境界確定) で偽分割を裁定できる。真の境界には加えて positive marker (blackout / 凍結 run) が存在する (二重根拠)。

## 6. 結果 5: 音声 (fanfare 相関) の棄却

- きゅま (voice-over 濃): 試合中も非試合 gap 中も sim 0.5-0.72 で無差別に発火 (319 hits/4h)。既知の非試合区間 8080-8450 内でも sim 0.694。判別力なし。
- gyawa: 試合中 BGM が sim 0.70-0.75、非試合 0.51-0.61 と「逆向きに」分離するが、ソース依存 (きゅまで不成立) のため採用不可。
- → fanfare/BGM 相関は VTuber VOD の境界信号として不採用 (診断用途のみ)。`AUDIO_FROZEN` の扱いに影響なし。

## 7. 副次的発見

### 7.1 gyawa GT の試合漏れ

t=250-1250 に GT 未記載の実 FL 試合を確認 (t=600 フレームで 3 陣営スコア 899/569/647 per 2400、残り 15:09 を目視確認)。録画開始時点で進行中だった部分試合を GT 作成時に除外した可能性が高い。timeline 手法はこれを正しく検出した。**GT 更新は設計 spec の Phase 3 で扱う** (部分試合の期待挙動の定義を含む)。

### 7.2 きゅま 11 試合 GT (本 PoC 注釈)

コンタクトシート (60s stride) + 裁定フレーム (16 点) + dense 計測で注釈した境界 (±30s 精度、zone-in 基準):

45-810 / 1170-2100 / 2210-3350 / 3530-4610 / 4730-5710 / 5980-6950 / 7160-8090 / 8450-9710 / 9940-10850 / 11360-12630 / 12910-14110

issue #480 記録の「実際は ~11 試合」と一致。Phase 3 で正式 GT ファイル化する。

### 7.3 GT 規約の注意

gyawa 既存 GT は戦闘開始 (カウントダウン終了) 基準、timeline 分割は zone-in/staging 基準で始まる。OBS pipeline の blackout 分割も staging 込みなので、**分割意味論は zone-in 基準に統一し、GT を同基準で再注釈する** (Phase 3)。

### 7.4 きゅま inset 移動の実態

memory 記録「きゅま VOD は inset 位置が変動」に対し、実測では試合中 y_top は全 VOD を通じて 0-6px に安定 (90-120min 帯の y=324 集団は lobby 中の raw localize FP と判明)。per-segment anchor は本設計では不要、将来拡張として保留。

## 8. 制約・未消化

- シルロリ 34.7min segment / メテオ短 segment 2 本の目視裁定は未実施 (設計 Phase 3 の GT 注釈で消化)。
- 湿気・シルロリ・メテオ・Shinryu は境界単位の GT 突合を行っていない (segment 長の妥当性確認のみ)。
- 全計測は CPU `-ss` 単発 probe。GPU 経路・低スペック環境は未計測。
- マップ多様性: Onsal 中心 (きゅま/メテオ/湿気/Shinryu 後半)。制圧 (Shinryu 前半) / Seal Rock 系は gyawa のみ。他マップの band_mad 分布は Phase 3 gate で確認。
