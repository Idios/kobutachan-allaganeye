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

> **以下 2 表は閾値の「現在値」を持たない**（#913 / #818 doc SSoT 規約）。値の正は実装の
> module-level 定数 1 箇所のみで、表に載るのは **校正当時の実測記録と採用理由**である。
> 行ごとの分類は下記 §表の分類方針 を参照。
> （本 § より前の擬似コードと §背景 には現在値と一致する数値が残っている。そちらは
> アルゴリズムの説明であって値の正ではない — 突合するなら実装を読むこと。）

| 定数 | FL 実測 | 非FL 実測 | 校正当時のマージン |
| --- | --- | --- | --- |
| [detector.py](../allaganeye/video/detector.py) の `_SCOREBAR_CHANNEL_STD_THRESHOLD` | 26-48 | lobby ~5, queue ~8.8 | 6.2 (queue→閾値) |
| [detector.py](../allaganeye/video/detector.py) の `_SCOREBAR_MIN_SECONDARY_STD` | 26-48（全チャンネル） | ローディング 2nd ch < 5 | 7.0 (non-FL→閾値) |
| [detector.py](../allaganeye/video/detector.py) の `_SCOREBAR_EDGE_THRESHOLD` | 20-60（バンド境界） | グラデーション < 5 | 3.0 (gradient→閾値) |

「マージン」列は**校正を行った時点の値に対する余裕**であり、実装値を変えたら当然ズレる。
現在値との突合が要るときは実装を読むこと（この列を根拠に現在の余裕を語ってはならない）。

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

1. `_find_scorebar_horizontal_range(raw_rgb)`: 画面上部 y=0..45 の HSV saturation mask で saturated 列の run を構築し、**画面中央 (x=960) を跨ぐ run** を scorebar span として返す (#803)。FL scorebar は水平中央に配置されるため、**最長 run を選ぶと**より長い off-center / 過大幅のバンド (右側チャットパネル、post-match の色鮮やかな屋内など) が有効な中央 scorebar を隠してしまい、rescue path が支えるはずの 4K / HUD-scaled layout を false-negative にする。中央を跨ぐ run が無い場合、および span 幅が 500px 未満 / 1440px 超の場合は None
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

こちらも値は持たない。正は同名の module-level 定数。

| 定数 | 役割と採用理由 |
| --- | --- |
| [detector.py](../allaganeye/video/detector.py) の `_SCOREBAR_SCAN_Y_START` / [detector.py](../allaganeye/video/detector.py) の `_SCOREBAR_SCAN_Y_END` | 画面上部 scan ROI |
| [detector.py](../allaganeye/video/detector.py) の `_SCOREBAR_SCAN_SAT_THRESHOLD` | saturated pixel 閾値。lobby 背景の実測 66-79 を超え、scorebar バンドの実測 >= 150 を下回る中間に置く |
| [detector.py](../allaganeye/video/detector.py) の `_SCOREBAR_SCAN_VAL_THRESHOLD` | 暗フレーム排除 |
| [detector.py](../allaganeye/video/detector.py) の `_SCOREBAR_SCAN_COL_RATIO` | 列のうち saturated が占める割合の下限。超えた列を qualifying とする |
| [detector.py](../allaganeye/video/detector.py) の `_SCOREBAR_SCAN_MIN_WIDTH_PX` | scorebar と認める最小幅。実測 1080p 712+ / 4K DVR 613+ を通し、lobby 409 の FP を排除する |
| [detector.py](../allaganeye/video/detector.py) の `_SCOREBAR_SCAN_MAX_WIDTH_PX` | scorebar と認める最大幅 (#803)。実測上限 1080p OBS ~1090px / 4K DVR ~620px に対し、post-match の全幅近い彩度バンド (実測 ~1912px) を排除する。probe 幅 1920px に対する割合として決めた |
| [detector.py](../allaganeye/video/detector.py) の `_SCOREBAR_SCAN_MAX_GAP_PX` | scorebar 中央 timer/score 部のギャップを bridge する許容幅 |

### 表の分類方針 (#913)

doc SSoT 規約 (#818。同じ仕様値を複数 doc に書かない／管轄が重なる場合は**実装を canonical** とする) に従い、上 2 表の各セルを次の 3 種に分類し、**仕様主張だけを参照化**した。

| 分類 | 扱い | 上表での該当 |
| --- | --- | --- |
| **仕様主張**（「この定数の値は X である」） | 実装が正。doc からは**値を削除**し、定数名 + 実装リンクで突合先を一意にする | 旧「値」列（両表とも削除済み） |
| **検証当時の実測記録**（「FL では 26-48 だった」） | doc が正。実装からは復元できない一次データなので**残す** | 「FL 実測」「非FL 実測」列、役割欄の実測値 |
| **採用理由**（「lobby 背景を超え scorebar バンドを下回る中間に置く」） | doc が正。**残す**。値が変わっても理由は生き続ける | 「役割と採用理由」列 |

「校正当時のマージン」列だけは実測記録と仕様主張の**混合**（当時の値に依存する派生量）なので、当時の記録であることを明示したうえで残している。

突合先が一意であることの担保は機械側にもある: 上表の `[detector.py](../allaganeye/video/detector.py) の \`定数名\`` 形は `scripts/check_doc_code_refs.py` の symbol 検査対象で、定数が改名・削除されたら CI が赤くなる。

### 検証サマリー

- 1080p OBS 4 録画 (20260116/20260118/20260119/20260219) で改修前と match_count / boundary 時刻・types 完全一致 (境界差 <0.5s)。初版 dynamic primary で発覚した 20260219 Match 6/16 結合退行 (33-41min 超長 match) は two-path 化で解消
- 4K Game DVR file 1: Path 1 absolute fail → Path 2 dynamic rescue (span=652..1272) で in-match True 復帰、lobby は両 path fail で False (FP なし)
- emblem 位置の追従は 1080p / 4K 両方で可視化確認済み
- ただし 4K Game DVR の試合境界完全回復は Pass 2 region 幅が狭く classify post probes が暗転 fade-in 中に hit する別問題で未達 (#524 で follow-up)

### post-match trailing の flagging (#797 / #805)

末尾セグメントが動画終端まで続き `type == "unknown"` の場合、試合ではなく
post-match コンテンツ (ロビー / 街) の可能性がある。`_flag_post_match_trailing`
は候補試合ウィンドウ (`start` .. `start + min_match_duration`) を
`_TRAILING_PROBE_STRIDE` (60s) 間隔 + ウィンドウ終端で scorebar probe し、

- 1 回でも hit (`True`) → 試合映像あり → そのまま残す
- 1 回でも probe 失敗 / opencv 不在 (`None`) → 安全側でそのまま残す
- 全 probe が確定 miss (`False`) → `post_match: true` を付与して**残す**

判定は #805 段階2 で**非破壊**になった。旧 #797 はセグメントを削除していたが、
scorebar false-negative が実試合を silent に消しうるため、フラグ付与 +
default split (MP4) からの除外 + metadata 保持に置き換えられている。
セグメントが 1 個しかない場合 (blackout が 1 つも残らなかった fail-open) は
常に無変更で、「境界が見つからない」が試合ゼロに崩れることはない。

### 位置独立な scorebar 局在化 (#811)

`video/capture_region.py` の `localize_scorebar` は、上記の絶対 / 相対 2 path とは
別に、**位置を仮定しない** scorebar 局在化を提供する (L3 Phase 1 の基盤)。
saturated column run を width-gate で全件取り出し、各候補に対し 3 点 emblem AND を
評価して最も margin の大きいものを採用する。`--vtuber` gate 内および masked
fallback の at-anchor primitive (`localize_scorebar_at_anchor`、#822) として使われ、
OBS 通常 path の分類ロジックは変更しない。検出 subsystem 全体の現状 map は
[`docs/detection-map.md`](detection-map.md) を参照。

### 残課題 (follow-up)

- 4K Game DVR の長めの UI fade-in (~2-3s) に対応するため、classify_blackout の post probe offset を動的に調整する (別 issue)
