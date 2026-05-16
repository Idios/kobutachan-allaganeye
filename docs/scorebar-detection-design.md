# スコアバー検知の設計と判断根拠

## 背景

FL（フロントライン）の試合境界検知において、スコアバー UI の有無でフレームの分類を行う。`_has_scorebar()` は 320x180 RGB フレームのスコアバー ROI（上部 4%、中央 30%）を分析し、FL 試合中か否かを判定する。

### 解決すべき問題

| Issue | 症状 | 根本原因 |
| --- | --- | --- |
| #201 | ローディング画面が scorebar ありと誤判定 | ROI 内の風景画像が ch_std > 15.0 を満たす |
| #200 | ロビー画面のボーダーライン偽陽性がマージを阻害 | ch_std ≈ 14.1 が ffmpeg シーク非決定性で 15.0 超に変動 |

## 検討したアプローチ

### A. `_has_scorebar` を強化するアプローチ（採用検討）

| # | 手法 | 原理 | 追加コスト | 評価 |
| --- | --- | --- | --- | --- |
| **A1** | **多チャンネル std** | FL 3GC 色帯は全チャンネルで高 std。ローディング画面は 1 チャンネルのみ | ほぼゼロ（既存データ利用） | **採用** |
| **A2** | **水平エッジ密度** | 色帯境界の鮮明なピクセル遷移を検出 | ほぼゼロ（既存データ利用） | **採用** |
| A3 | HSV 色相範囲 | H チャンネルで黄/赤/青を直接判定 | RGB→HSV 変換 | A1 と本質的に同等。RGB 空間で十分 |
| A4 | 色ヒストグラム比較 | ROI 色分布を参照と比較（Swain & Ballard, 1991） | 参照データ管理が必要 | 96x7px では情報量不足 |
| A5 | SSIM テンプレートマッチ | 構造的類似度で参照スコアバーと比較 | 複数テンプレート管理 | 戦績ゲージ変動で複数テンプレ必要 |
| A6 | 色相シグネチャ（Gemini 提案2） | セクション別の色支配パターン検証 | ほぼゼロ | 有効だが A1 で代替可能。GC 配色の順序変動に注意 |

### B. アーキテクチャ変更アプローチ（将来検討）

| # | 手法 | 概要 | 評価 |
| --- | --- | --- | --- |
| B1 | セグメントレベル分類 | 暗転の両側ではなくセグメント内部を直接サンプル | 根本的改善だが大規模リファクタ。L1 成熟後に検討 |
| B2 | カスケード検知 | Pass1=高速判定、Pass2=曖昧ケースのみ精密分析 | 有効だが現時点では過剰設計 |
| B3 | フルフレーム文脈 | ROI 以外の UI 配置（ミニマップ等）も活用 | 320x180 での信頼性が不明。要調査 |

### C. 時間的一貫性アプローチ

| # | 手法 | 概要 | 評価 |
| --- | --- | --- | --- |
| C1 | 時間的静止判定 | 連続フレーム間 MAD で静的画面を検出 | **実装済み**（defense-in-depth） |
| C2 | 多数決厳格化 | 2/3 → 3/3 | 正検出も落ちるリスク |
| C3 | 副次 ROI（ミニマップ） | 右上 ROI でミニマップ存在を確認 | 320x180 での見え方が不明。要調査 |

### D. 学術・OSS の知見

- **PySceneDetect**: HSV ヒストグラム差分。映画向け、ゲーム UI 検知ではない
- **esports highlight detection** (Chen et al., 2018): CNN ベース。本ツールの AI 不使用方針と不適合
- **共通知見**: 単一特徴量は脆い。2-3 特徴量の AND ゲートが定石

## 採用した方式: A1 + A2（多特徴量 AND ゲート）

### 判断基準

1. **追加コストがほぼゼロ**: 既にプローブ済みのフレームデータから計算可能
2. **直交する特徴量**: A1 は「色の多様性」、A2 は「構造の鮮明さ」を独立に検証
3. **偽陽性の根本解決**: `_has_scorebar` 自体の精度向上により、下流のマージ緩和等のワークアラウンドが不要

### 4 条件の AND ゲート

```text
ROI brightness ∈ (20, 140)          ... 暗転・白飛びを排除
  AND max(channel_stds) > 15.0      ... ロビー・キューを排除
  AND sorted(channel_stds)[-2] > 12.0  ... 1チャンネルのみ高stdのローディング画面を排除 (A1)
  AND max(per-channel h_edge) > 8.0    ... 滑らかなグラデーションを排除 (A2)
→ True (FL scorebar detected)
```

### 閾値の根拠

| 定数 | 値 | FL 実測 | 非FL 実測 | マージン |
| --- | --- | --- | --- | --- |
| `_SCOREBAR_CHANNEL_STD_THRESHOLD` | 15.0 | 26-48 | lobby ~5, queue ~8.8 | 6.2 (queue→thr) |
| `_SCOREBAR_MIN_SECONDARY_STD` | 12.0 | 26-48（全チャンネル） | ローディング 2nd ch < 5 | 7.0 (non-FL→thr) |
| `_SCOREBAR_EDGE_THRESHOLD` | 8.0 | 20-60（バンド境界） | グラデーション < 5 | 3.0 (gradient→thr) |

## 将来の進化パス

1. **閾値のデータ駆動チューニング**: `debug-brightness --roi-mode scorebar-detail` で実データの A1/A2 値を収集し、閾値を最適化
2. **時間的静止判定の再導入 (C1)**: A1+A2 でカバーできないエッジケース（ローディング画面が A1+A2 を通過する場合）が発見された場合、`_is_static_from_frames()` を defense-in-depth として再導入する。実装は git history から復元可能
3. **セグメントレベル分類 (B1)**: 暗転分類から直接セグメント判定への移行
4. **副次 ROI (C3)**: ミニマップ ROI の 320x180 での有効性を調査

## V2: GC-emblem 3-point AND と動的 scorebar 外輪郭検出 (#307, #522)

### 背景

V1 (`_has_scorebar`) は 320x180 低解像度 ROI での色特徴量判定を行うが、ロビー背景や GC 配色の順序変動で偽陽性が発生しうる。PR #313 で V2 (`_has_scorebar_v2`) を導入し、1920x1080 高解像度フレームの 3 GC emblem 位置で HSV saturation と Sobel edge density の AND を取ることで構造的に FP を排除した。

### 動的 emblem 位置 (#522)

V2 導入時の `_EMBLEM_POSITIONS` は 1920x1080 絶対座標の hardcode で、1080p OBS 録画で validated された。しかし 4K Game DVR 録画 (Windows/Xbox) では FF14 HUD scale が異なり scorebar が画面中央寄りに描画されるため、絶対座標の left/right 位置が scorebar 外 (ゲーム背景) にヒットする FP 問題が発生した。

解決策として **two-path OR semantics** を採用。Primary は pre-#522 validated の absolute `_EMBLEM_POSITIONS`、Rescue は scorebar span 動的検出 + `_EMBLEM_RELATIVE_POSITIONS` 相対比で HUD scale 差異を吸収する。

1. `_find_scorebar_horizontal_range(raw_rgb)`: 画面上部 y=0..45 の HSV saturation mask で saturated 列の最長 run を scorebar span として返す。run 幅 < 500px は None (lobby UI 誤検出排除)
2. `_EMBLEM_RELATIVE_POSITIONS`: 1080p OBS validated set 13 frames の実測 median 相対比
   - left: `cx_rel=0.0455, half_width_rel=0.0453`
   - center: `cx_rel=0.3427, half_width_rel=0.0237`
   - right: `cx_rel=0.9638, half_width_rel=0.0384`
3. `_has_scorebar_v2` (two-path OR):
   - **Primary**: `_EMBLEM_POSITIONS` (absolute) で 3-point AND check → pass なら True (short-circuit)
   - **Rescue**: Primary fail 時のみ span 検出 → 相対位置で emblem 絶対座標計算 → 3-point AND check → pass なら True
   - 両 path fail で False、`raw_rgb is None` / opencv 未インストール時のみ None → V1 (`_has_scorebar`) fallback
4. `_emblem_and_check` helper で両 path の AND 評価を共通化

OR 結合により、1080p OBS validated set は Primary で完結 (FP 耐性保持)、4K Game DVR の HUD-scaled scorebar は Rescue で救済。初版 (dynamic primary) で発覚した 20260219 (5h+ 長時間録画) の Match 6/16 結合退行 (33-41min 超長 match) は two-path 化で解消。

### 閾値定数 (V2 動的検出)

| 定数 | 値 | 役割 |
| --- | --- | --- |
| `_SCOREBAR_SCAN_Y_START` / `_Y_END` | 0 / 45 | 画面上部 scan ROI |
| `_SCOREBAR_SCAN_SAT_THRESHOLD` | 80.0 | saturated pixel 閾値 (lobby 背景 66-79 を超え、scorebar バンド >= 150 の中間) |
| `_SCOREBAR_SCAN_VAL_THRESHOLD` | 60.0 | 暗フレーム排除 |
| `_SCOREBAR_SCAN_COL_RATIO` | 0.30 | 行の 30% 以上が saturated であれば該当列を qualifying |
| `_SCOREBAR_SCAN_MIN_WIDTH_PX` | 500 | scorebar と認める最小幅 (1080p 712+, 4K DVR 613+, lobby 409 FP 排除) |
| `_SCOREBAR_SCAN_MAX_GAP_PX` | 80 | scorebar 中央 timer/score 部のギャップを bridge |

### 検証サマリー

- 1080p OBS 4 録画 (20260116/20260118/20260119/20260219) で改修前と match_count / boundary 時刻・types 完全一致 (境界差 <0.5s)。初版 dynamic primary で発覚した 20260219 Match 6/16 結合退行 (33-41min 超長 match) は two-path 化で解消
- 4K Game DVR file 1: Path 1 absolute fail → Path 2 dynamic rescue (span=652..1272) で in-match True 復帰、lobby は両 path fail で False (FP なし)
- emblem 位置の追従は 1080p / 4K 両方で可視化確認済み
- ただし 4K Game DVR の試合境界完全回復は Pass 2 region 幅が狭く classify post probes が暗転 fade-in 中に hit する別問題で未達 (#524 で follow-up)

### 残課題 (follow-up)

- 4K Game DVR の長めの UI fade-in (~2-3s) に対応するため、classify_blackout の post probe offset を動的に調整する (別 issue)
