# L3: VTuber game capture 領域検出アルゴリズム設計 (Phase 2a) (2026-05-26)

> **Status**: brainstorming 完了 / implementation plan は writing-plans で別途作成
> **Parent**: [#753](https://github.com/Idios/kobutachan-allaganeye/issues/753)
> **上位 spec**: [docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md](2026-05-18-v030-l3-redefinition-design.md) §3 (Pillar 1+2), §8.4 (VTuber Ground Truth)
> **検証対象**: `tests/baselines/v0.3.0/vtuber-primary-ground-truth.json` (5 試合, ±10s)

## 1. 背景と目的

### 1.1 きっかけ

- L3 Pillar 1 (VTuber 配信動画対応) の最初の技術タスク (Phase 2a)。
- VTuber 配信動画は frame 内に overlay (webcam / 枠装飾 / alert / chat) と一緒に gameplay が小さく **inset** で映る。
- 現状 scorebar V2 検出 (`allaganeye/video/scorebar.py`, `allaganeye/video/detector.py` の `_has_scorebar_v2`) は 1920x1080 frame **全体**の固定/準固定座標を前提とし、overlay があると完全に break する。
  - Primary path `_EMBLEM_POSITIONS` は絶対 px 座標 (detector.py:928)。
  - Rescue path `_find_scorebar_horizontal_range` も走査行を `y=0..45` (`_SCOREBAR_SCAN_Y_START/END`, detector.py:986) に限定しており、frame 上端しか見ない。
- 本 issue は **gameplay 矩形 (game capture region) の自動検出アルゴリズム** を設計・実装・実験選定する。検出矩形は Pass 1 暗転検知 / scorebar (#480) / minimap (#481) が共有利用する。

### 1.2 前提

- Phase 1 (Pillar 3) 完了、`tests/baselines/v0.3.0/` baseline 確定済。
- primary benchmark: gyawa 提供 VTuber VOD
  `E:\videos\gyawa_vatos\2772549129-151803977-da21c691-9ed6-4068-9a8b-4726a8a519a8.mp4`
  (7,554,775,607 bytes, **H.264 1920x1080 60fps, 約 2h43m**)。guard は trusted 扱い (user 確認 2026-05-26)。
- ground truth: `tests/baselines/v0.3.0/vtuber-primary-ground-truth.json` (5 試合, `tolerance_sec=10`)。

### 1.3 scope guard

- 本 issue = **検出アルゴリズムの設計・実装・実験選定 + proxy 検証 + e2e spike** まで。
- 下流 (別 issue): scorebar 検出本体 (#480) / minimap 切抜き (#481) / Pass 1 本番 wiring / metadata.json 本番スキーマ確定。

## 2. 実証で確定した前提 (gyawa benchmark grounding)

2026-05-26、benchmark から代表フレーム (`t=300/1900/2361/2490/4700/6900`) を抽出して目視確認し、さらに輝度プローブを実行した。以降の設計はこの実測に基づく。

### 2.1 レイアウト観察 (frame 目視)

1. **ゲーム画面は inset 矩形、周囲は明るい overlay、黒帯なし。** シアン帯 (上, 全幅) / アバター webcam (左) / 装飾カード (右) / フォロワーバー (下) に囲まれる。
   → **letterbox / pillarbox 黒帯検出 (元案 a) は適用不可。**
2. **scorebar は帯の下** = ゲーム領域の上端にあり、frame 上端 `y=0..45` ではない。現 V2 両 path が break する直接原因。
3. **VOD 内でレイアウトが変化する。** 試合1 (`t=1900/2361`) は小さめ + 装飾多め、ウォームアップ (`t=300`) と試合3/5 (`t=4700/6900`) は大きめのゲーム領域。
   → 領域は時刻範囲に紐づく必要があり、単一の global 矩形は不適 (per-segment 再検出の根拠)。

### 2.2 輝度プローブ — Pass 1 の決定的問題 (finding #4)

window `[2330, 2670]` (試合1終 2361 / 試合2始 2624 を含む) を `fps=1, scale=320:180, format=gray` で抽出し、full-frame 平均と中央 crop (`x∈[30%,70%], y∈[15%,80%]`) 平均を比較:

| 区間 | 内容 | full-frame 平均 | 中央(game) 平均 |
| --- | --- | --- | --- |
| 2330–2360 | 試合中 | ≈128 | ≈164 |
| 2361–2363 | 試合1終 暗転 | **52–66** | **0.1–19** |
| 2370–2610 | results / lobby | 90–106 | 50–86 |
| 2615–2629 | 試合2 load-in 暗転 (~15s) | **52–55** | **0.0** |

**結論**: 実暗転中の full-frame 輝度下限は **≈52**。default `blackout_threshold = 15.0` ([config.py:15](../../../allaganeye/config.py)) の **3.5 倍**であり、Pass 1 (full-frame 輝度) は**境界を検出できない**。一方ゲーム領域だけなら **0.0** まで落ち、明確に検出可能。
→ **領域検出は scorebar/minimap だけでなく Pass 1 暗転検知そのものの前提条件**であり、当初スコープ ("scorebar + minimap の基盤") に無かった論点。再現スクリプトは §6 harness に取り込む。

### 2.3 candidate 評価 (実証ベース)

| 案 | 判定 | 根拠 |
| --- | --- | --- |
| (a) letterbox / pillarbox | ❌ | 黒帯が無い (§2.1-1) |
| (c) 汎用 FF14 UI テンプレート | ❌ | スケール未知で脆い。FL 固有アンカーは scorebar の方が確実 |
| (b-1) **時間分散** (S1) | ✅ | ゲーム=動き大 / overlay=静止。レイアウト非依存、OBS で frame 全体を覆う = fallback 安全 |
| (b-2) **暗転重なり** (S3) | ✅ | 遷移中に暗くなる画素 = ゲーム領域 (finding #4 を直接活用) |
| (d) **scorebar 帯アンカー** (S2) | ✅ | Rescue の y 走査を全 frame に拡張。FL 固有・精密だが試合中のみ |
| (e) **複合** | ✅ | 推奨 (S1 coarse + S2/S3 precise) |

## 3. アーキテクチャ

### 3.1 2-tier 領域モデル

「per-segment 再検出」かつ「Pass 1 が第一級利用者」という制約から領域を 2 層で扱う。

| Tier | 役割 | 利用者 | 性質 |
| --- | --- | --- | --- |
| **Tier A — coarse 領域** | Pass 1 が「領域内輝度」で暗転検出できる最小限の領域 | Pass 1 暗転検知 | レイアウト変化に保守的 (常に game な中央コア)。OBS では frame 全体に解決 |
| **Tier B — precise 領域 (per-segment)** | 各候補セグメント近傍の試合中フレームから再検出する精密矩形 | scorebar #480 / minimap #481 | 時刻範囲に紐づくタイムライン |

### 3.2 bootstrapping 順序 + data flow

「領域がないと暗転が取れない / 暗転がないとセグメントが分からない」を粗→精の段階適用で解く。

```text
video
  │
  ▼
[Tier A: coarse 領域検出]   ← overlay 有無を判定。OBS → frame 全体 / VTuber → 中央 inset
  │
  ▼
[Pass 1 暗転検知]            ← coarse 領域内の輝度で閾値判定 (full-frame ではなく)
  │
  ▼
候補セグメント / 境界
  │
  ▼
[Tier B: per-segment 精密領域 再検出]
  │
  ├──────────────┬───────────────┐
  ▼              ▼               ▼
Pass1 微調整    scorebar #480    minimap #481   ← 領域 contract の利用者
(任意)
```

### 3.3 検出器は spec で固定しない (実験選定)

Tier A/B の検出シグナルは spec で 1 案に確定せず、§6 の harness で候補 (S1 分散 / S2 scorebar 帯 / S3 暗転重なり / 複合) を benchmark + OBS で比較して選定する (決定ログ §11)。

### 3.4 fallback と回帰安全 (最重要制約)

- 低信頼 → **full-frame** (領域 = frame 全体)。
- **OBS では Tier A が必ず full-frame に解決し、Pass 1 輝度が現行と数値一致 = v0.3.0 baseline を bit-exact 維持**しなければならない。
- 誤って inset 判定すると baseline が壊れるため、Tier A は「inset 宣言」に強い保守バイアス (confidence gate) をかけ、harness の M4 で「OBS = 領域全体 & detect 出力 bit-exact」を hard gate として assert する。

## 4. 出力 contract (データモデル)

矩形は**解像度非依存の正規化座標** `[0,1]` で表現する。

```text
CaptureRegion  = { x, y, w, h: float[0,1], confidence: float[0,1], source: "tierB"|"tierA"|"fallback" }
RegionTimeline = {
    coarse:   CaptureRegion,                                       # Tier A (Pass 1 用)
    segments: [ { time_range: [t0, t1], region: CaptureRegion } ]  # Tier B (#480/#481 用)
}
```

- **本番 metadata.json への載せ方は本 issue では「契約スケッチ」止まり**。最終スキーマは Pass1 wiring / #480 / #481 と共有の関心事なので、それらと整合させて確定する (上位 spec §3 「metadata.json 拡張」を分担)。
- 実験・spike では metadata を確定させず、サイドカー JSON (`tests/baselines/v0.3.0/vtuber-primary-regions.json`) に領域を吐いて proxy メトリクスに使う。

## 5. 検出 candidate signals (実験対象)

| ID | シグナル | 概要 | 適用 Tier | 弱点 |
| --- | --- | --- | --- | --- |
| **S1** | 時間分散 | N 枚サンプルの画素分散マップ → 高分散の最大連結矩形 | A (coarse) | webcam/chat の動きが混入 |
| **S2** | scorebar 帯アンカー | `_find_scorebar_horizontal_range` を全 y 走査に拡張 → game 上端+幅+スケール。GC 紋章 3 点 AND (既存検証済) で FL 固有性を担保 | B (precise) | 試合中のみ・上端+幅のみ (全矩形でない) |
| **S3** | 暗転重なり | 遷移中に暗くなる画素の重なり = game 領域 (finding #4) | A/B | coarse bootstrap が必要 (chicken-egg) |
| **複合** | S1+S2 / S1+S3 等 | coarse は S1/S3、precise は S2 で上端・スケールを精緻化 | A+B | 実装量 |

- S2 は既存 `_has_scorebar_v2` の機構 (GC 紋章 3 点 AND) を**領域検出シグナルとして**流用する。#480 の「scorebar で暗転を分類する」用途とは目的が別 (重複しない)。

## 6. 実験 harness + メトリクス + 選定手順

### 6.1 harness

- 置き場所: `scripts/vtuber_region_experiment.py` (`scripts/compare-baseline.py` と同列の保守スクリプト。入力形式が増えたとき再実行できるよう残す)。
- やること: 候補 (S1/S2/S3/複合) を benchmark + OBS baseline に適用し、下記メトリクスを計測して比較表を出力 → 勝者選定。§2.2 の輝度プローブもここに取り込む。

### 6.2 メトリクス

| # | 指標 | 内容 | 暫定基準 (実験で調整) |
| --- | --- | --- | --- |
| M1 | 領域精度 | 検出矩形 vs 正解矩形の IoU、および**上端 px 誤差** (scorebar 用に最重要) | IoU ≥ 0.9 / 上端誤差 ≤ ~15px |
| M2 | コスト | detect への追加 wall-time | 現行 detect 比で許容範囲 |
| M3 | e2e (±10s) | crop→Pass1→scorebar spike が 5 試合を検出し start/end が ground truth ±10s・index 1-5 一致 | Phase 2b 完了基準と同値 |
| M4 | OBS 回帰 | OBS baseline で領域 = frame 全体 & detect 出力 bit-exact | 5 本すべて pass (**hard gate**) |

### 6.3 選定手順 (実測値は実験後に本 spec へ追記)

1. **M4 (OBS 回帰) pass を hard gate** — fail する候補は不採用。
2. VTuber 領域精度 (M1) 最大。
3. コスト (M2) 許容。
4. e2e (M3) ±10s 達成。

### 6.4 proxy ground truth (新規 annotation 成果物)

- 既存 `vtuber-primary-ground-truth.json` は「試合の時刻」、新規 `vtuber-primary-regions.json` は「ゲーム矩形」で別物・補完関係。
- 作り方: 抽出フレームを目視して各レイアウト (本ベンチは 2 種以上) の正解矩形を**初回推定 → user が確認・補正** → 確定。1 レイアウトにつき試合中フレーム数点 (計 5〜10 矩形) で十分。

## 7. 検証 / exit 基準 (本 issue)

1. **M1**: 両レイアウトの正解矩形に対し IoU 基準クリア。
2. **M4**: OBS baseline 5 本で領域 = 全体 + bit-exact 再現 (**最重要・hard gate**)。
3. **M3 spike**: crop→Pass1→scorebar で 5 試合 ±10s 検出を**実現可能性として実証** (本番 Pass1 wiring・#480・#481 は下流)。

## 8. スコープ境界と issue 分解

### 8.1 やる / やらない

- **やる**: Tier A/B 検出アルゴリズム (候補実装 + 実験選定) / 領域出力 contract (in-memory 型 + サイドカー JSON) / harness + メトリクス M1–M4 / proxy 検証 (annotation 含む) + e2e spike。
- **やらない (下流 issue)**: 本番 Pass 1 領域輝度 wiring / scorebar ROI 適応本体 (#480) / minimap 切抜き本体 (#481) / 本番 metadata.json スキーマ確定。

### 8.2 issue 分解 (#753 配下、Phase 2a 起点)

```text
#753 (parent: VTuber + minimap)
 ├─ [NEW] L3: game capture 領域検出アルゴリズム      ← 本 issue (Phase 2a)。下記を block
 ├─ [NEW] L3: Pass 1 暗転検知の領域輝度適応 (本番 wiring)  ← finding #4 由来、当初スコープ外
 ├─ #480  L3: scorebar ROI 適応化                  ← precise 領域を消費
 ├─ #481  L3: minimap 切抜き                       ← precise 領域を消費
 └─ (共有) metadata.json 領域フィールド確定          ← 上記 consumer と整合
```

- **Iron Law 2/3 注意**: 新規 child issue 作成は本ブレストでは**行わない**。3 件以上の issue 操作になり得るため、起票は別途 user 確認を取ってから (writing-plans 後など)。本 spec は分解案の記録に留める。

## 9. リスクと緩和

| # | リスク | 緩和 |
| --- | --- | --- |
| R1 | OBS を誤って inset 判定 → baseline 破壊 | Tier A に強保守バイアス + M4 で全体一致 & bit-exact を hard gate |
| R2 | S2 がシアン帯等の高彩度 overlay を誤検出 | FL 固有の GC 紋章 3 点 AND (検証済機構) を流用、単純帯は通さない |
| R3 | S1 分散に webcam/chat の動きが混入 | 最大連結成分 + FL アンカー (複合) で純化 |
| R4 | 試合中のシーン切替で領域が割れる | 再検出粒度を調整、セグメント内は安定領域を採用 |
| R5 | annotation の主観 (ゲーム端の取り方) | user 確認 + 許容誤差 (上端重視の px tolerance) |
| R6 | VTuber ベンチが gyawa 1 本のみ → 過学習 | レイアウト非依存シグナルで一般化、選定は 1 ソース検証と明記。追加 VTuber ソースは後続 |
| R7 | 将来の外部動画は guard 必須 | 新ベンチ追加時は `allaganeye-guard verify` 通過を前提に |
| R8 | Tier B per-segment のプローブ増でコスト増 | 既存プローブ基盤を再利用し M2 で上限監視 |

## 10. Open questions (writing-plans / 実装で解決)

1. **検出シグナルの最終選定**: §6 harness の実測後に確定 (本 spec へ追記)。
2. **再検出粒度**: per-blackout / per-segment / 固定時間窓 のいずれか (M2 コストと R4 のトレードオフで決定)。
3. **本番 metadata.json スキーマ**: consumer (Pass1 wiring / #480 / #481) と整合して別途確定。
4. **annotation tolerance の具体値**: M1 の IoU / 上端 px 閾値を実データで較正。

## 11. 決定ログ (本ブレストの選択)

| 論点 | 決定 |
| --- | --- |
| 領域の時間モデル | **per-segment / 再検出** (static global 矩形ではない) |
| 本 issue の検証 | **proxy metric (IoU/px) + thin e2e spike** (full wiring でも harness-only でもない) |
| Pass 1 の扱い | **第一級利用者として設計に含める + e2e spike で ±10s 実証** (別 issue 分離でも #480 統合でもない)。本番 wiring は別 child issue |
| 検出アルゴリズム | **spec で固定せず harness で実験選定** |
| guard | gyawa benchmark は trusted 扱い (user 確認 2026-05-26) |

## 12. 参照

- parent: [#753](https://github.com/Idios/kobutachan-allaganeye/issues/753) / 関連: #480 (scorebar ROI 適応化), #481 (minimap 切抜き)
- 上位 spec: [2026-05-18-v030-l3-redefinition-design.md](2026-05-18-v030-l3-redefinition-design.md) §3 / §8
- 現状コード: `allaganeye/video/scorebar.py`, `allaganeye/video/detector.py` (`_has_scorebar_v2` detector.py:1190, `_find_scorebar_horizontal_range` detector.py:1073, `_EMBLEM_POSITIONS` detector.py:928)
- baseline: `tests/baselines/v0.3.0/` (README.md / vtuber-primary-ground-truth.json) / 比較: `scripts/compare-baseline.py`
- testing: [docs/testing-guide.md](../../testing-guide.md) §baseline drift の判定
