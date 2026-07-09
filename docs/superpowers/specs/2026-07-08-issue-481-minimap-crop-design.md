# minimap 切抜き機能 (#481) design

- 日付: 2026-07-08
- 対象 issue: [#481](https://github.com/Idios/kobutachan-allaganeye/issues/481) (parent: #753)
- 前提: [2026-06-29 roadmap](2026-06-29-v030-l3-roadmap.md) §4 Phase 2 (2026-07-06 rescope #872 で
  un-defer、最初に再開する workstream) / [#810 capture_regions spec](2026-07-07-capture-regions-metadata-schema-design.md)
- 決定方式: brainstorming (AskUserQuestion 6 点 + design 2 部承認、2026-07-08)

## 1. 背景と目的

gyawa さん (#481 本文) の要望「ミニマップの切り抜きツールは編集技術がない人にとって画期的」に応え、
分割済み試合動画からマップ UI 領域を自動検出して切抜き MP4 を出力する。
[L3 redefinition spec](2026-05-18-v030-l3-redefinition-design.md) §未決事項 3 で「出力形式は
着手時 brainstorm で確定」と先送りされていた論点を本 design で確定する。

**重要な用語整理 (2026-07-08 実サンプル確認で確定)**: FL 録画には 2 種のマップ UI が映る。

1. **エリアマップ** — 戦場全体図の半透過 window (既定は左上想定だが HUD 配置可変)。拠点・
   アライアンス位置が見え、戦況分析・部隊移動の解説に使えるのはこちら
2. **円形ナビマップ** — 局所範囲の小型円形 minimap (既定右上)

**切抜き対象は (1) エリアマップ** (Idios 確定)。機能名・command 名は issue #481 / roadmap /
release gate の確立名「minimap」を維持し、実体がエリアマップ window である旨を cli-spec /
output-spec に明記して混同を防ぐ。

## 2. 決定ログ (brainstorming、2026-07-08)

| 論点 | 選択肢 | 決定 (Idios) |
| --- | --- | --- |
| 出力形式 | MP4+座標記録 / MP4 のみ / 座標のみ | **MP4 + 座標記録** (metadata.json に領域を永続化。記録コストほぼゼロ、将来の GUI・再現性に有用) |
| CLI surface | 新 command / export オプション / detect 組込み | **新 command `allaganeye minimap`** (released detect/split 経路と cache key に一切触れない) |
| 検出方式 | 自動+手動 override / 自動のみ / 手動のみ | **自動検出 + `--region` 手動 override** (escape hatch) |
| 試合中の移動/非表示 | 試合単位静的+warning / 動画単位 1 回 / 動的追跡 | **試合単位静的 + warning** (試合ごと multi-frame consensus。動的追跡はしない) |
| 切抜き対象 | エリアマップ / 円形ナビマップ / 両方 | **エリアマップ (左上全体図)** |
| 検出アルゴリズム | 時間安定性+map 照合 / window 枠 edge / PoC 比較 | **PoC で両案比較してから確定** (実装 plan の Phase 0) |
| **PoC checkpoint (2026-07-08)** | 手動 primary + A seed / 完全手動 / PoC 継続 / 基準緩和 | **手動 primary + A seed 提案** (両案 IoU≥0.9 gate 不合格 → §6.2 STOP 発動。A=1/5, B=0/5。[PoC report](2026-07-08-issue-481-areamap-poc-report.md) 参照)。crop は `--region` 手動指定を primary とし、`--region` 省略時は案 A (temporal-stability のみ、map 照合・refs 同梱は撤回) が**提案領域を表示するだけ** (crop せず exit 4 + 案内)。`map_name` field と `allaganeye/video/refs/` npz 同梱は不採用 |

## 3. 全体像

- **CLI**: `allaganeye minimap <metadata.json> [-o <dir>] [--region X,Y,W,H] [--include 1,3]`
  — detect / split 済みの metadata.json を入力に、`--region` (primary) の領域で crop + h264
  再エンコードの MP4 を出力し、座標を metadata に write-back する。`--region` 省略時は
  **提案モード**: 案 A seed 検出で試合ごとの提案領域を表示するだけで crop はしない
  (exit 4 + `--region` 案内。PoC checkpoint 決定、§2 決定ログ最終行)
- **v0.3.0 対象入力**: 標準 OBS full-frame + masked 録画。VTuber inset は v0.4.0 期 (#866)。
  検出・記録は frame 正規化座標 (0–1) で行い、将来 `capture_regions` の game 矩形と合成できる
  forward-compat を確保する (位置合成のみ。v1 実装は full-frame 前提)
- **検出は毎回 fresh 実行** (detection cache 非使用)。detect param を追加しないため cache key
  3 箇所問題 (`feedback_detection_flag_cache_key`) は構造的に発生しない

## 4. コンポーネント構成

| モジュール | 責務 |
| --- | --- |
| `allaganeye/video/areamap.py` (新規) | エリアマップ window の **seed 検出 (提案モード専用)**。案 A の temporal-stability 部分 + 試合単位 multi-frame consensus (`detect_scorebar_band_region` と同型設計)。**detector.py / scorebar.py 非接触** |
| `allaganeye/commands/minimap.py` (新規) | command orchestration: metadata 読込 → source 動画解決 → 試合ごと検出 → atomic write-back (`detection/metadata_writer` 再利用) → crop encode → 進捗表示 |
| `allaganeye/export/` (再利用) | `enumerate_h264_encoders` の slot 決定 + GPU init 失敗時の libx264 retry (#761 `_GPU_ENCODER_FAILURE_PATTERNS`) を流用。crop filter (`-vf crop=…`) を通す手段 (export encode 関数の optional 拡張 or 兄弟関数) は plan で確定 |
| `scripts/areamap_poc.py` (新規) | PoC: 両検出案の実サンプル比較 (`vtuber_region_experiment.py` 前例) |

## 5. データフロー / metadata schema

```text
metadata.json (detect/split 済) → allaganeye minimap
  ├─ --region なし (提案モード): 試合ごと N 枚 sample → A seed 検出 consensus
  │    → 提案領域を --region 形式で表示 → exit 4 (crop なし・write なし)
  └─ --region X,Y,W,H (crop モード):
       → metadata.json へ `minimap_regions` を atomic write-back
       → 試合ごと: ffmpeg crop + h264 encode (encoder slot 並列) → <out>/NNN_minimap_*.mp4
```

### 5.1 schema (SSoT = `schemas/metadata.schema.json`、#810 規約踏襲)

```jsonc
// top-level、optional (pre-#481 ファイルは欠落 = 後方互換)
"minimap_regions": [
  {
    "match_index": 1,                 // matches[].index と対応 (1-based)
    "region": { "x": 0.01, "y": 0.02, "w": 0.28, "h": 0.35,
                "confidence": 1.0, "source": "manual" }  // $defs CaptureRegion 再利用
  }
]
```

- `region` は `$defs.CaptureRegion` を再利用 (正規化座標 0–1)。`source` は free string +
  文書化 (#810 の forward-compat 哲学)。v1 で write されるのは `"manual"` (`--region` crop 実行時)
  のみ — **提案モードの seed 領域は永続化しない** (信頼度が実用水準でない座標を metadata に
  残さない。PoC checkpoint 決定)
- ~~`map_name`~~ は **PoC checkpoint で撤回** (map 照合が識別器として機能しなかったため。
  [PoC report](2026-07-08-issue-481-areamap-poc-report.md) §5 弱み 3)。entry は
  `{match_index, region}` の 2 field のみ
- crop 実行対象にならなかった match (--include 対象外等) は **entry を作らない**
  (欠落 = 未実行。領域不明を偽装しない、#810 同方針)
- `additionalProperties: false`。`schema_version` は `"1"` のまま (additive optional、
  #569 / #591 / #810 前例)
- codegen 再実行 → `allaganeye/metadata_types.py` + `gui/src/types/metadata.generated.ts`。
  zod (`metadata.schema.ts`) に `MinimapRegionsSchema` 明示追加 (#612 規約)。
  Rust `validate_metadata_for_write` は変更なし (optional field 非検証の前例に従う)
- write-back は `detection/metadata_writer` の atomic write。GUI 排他 (#514 mtime 検知) とは
  既存 ConflictModal 機構で整合 (CLI 外部変更として検知される、想定内)

## 6. 検出アルゴリズム PoC (plan Phase 0)

brainstorm では確定せず、実サンプル比較で勝者を選定する (scorebar 検出の「実験選定」方式)。

### 6.1 候補案

| 案 | 内容 | 事前評価 |
| --- | --- | --- |
| **A: 時間安定性 + map 照合** | Stage 1: 試合内 N フレームの temporal median/variance で「背景は動くが window は静的」な候補領域を絞る → Stage 2: 既知 FL マップの低解像度参照特徴量と multi-scale 照合で bbox 確定 + map 種別判定 | 半透過・リサイズに頑健。参照 asset 準備が必要 |
| **B: window 枠 edge 検出** | 装飾ヘッダー・窓枠の直線/コーナーを edge / line 検出で特定 | asset 不要だが半透過で edge が弱く、map window の表示モード差で破綻リスク |

- 案 A の参照 asset は生 screenshot を repo に置かず**派生特徴量 (npz)** で同梱する
  (`audio/refs/fanfare.npz` 前例)。生成元は Idios 自身の録画フレーム。再生成 script は
  `scripts/regen_audio_refs.py` 前例に倣う
- sampling 初期値 (PoC で調整): 試合ごとに `[start+60s, end-60s]` から等間隔 9 フレーム、
  IoU ≥ 0.8 で cluster し多数派 (≥ 5/9) を consensus 採用。hit 率を `confidence` に記録

### 6.2 判定基準

- dataset: OBS baseline 5 本 + masked サンプル (`E:\allaganeye-samples`) から抽出した
  試合フレーム + 手動 GT bbox アノテーション
- 勝者条件: GT IoU ≥ 0.9 の検出成功率が高い案。同等なら実装複雑度が低い案
- 両案とも成功率が実用水準に届かない場合は STOP し、`--region` 手動 primary への
  scope 縮小を AskUserQuestion で再判断する

### 6.3 結果 (2026-07-08 実施済)

**両案とも不合格 → STOP 発動、`--region` 手動 primary + A seed 提案へ縮小** (Idios checkpoint
確定)。A = 正例 1/5・負例 reject 1/2 / B = 正例 0/5・負例 reject 2/2。A の bbox 過小は構造的
(map 内部の blip が動くため static 判定されない)、map 照合は識別器として機能せず (lobby 負例の
ref score が正例を上回る)。詳細は [PoC report](2026-07-08-issue-481-areamap-poc-report.md)。
帰結: `map_name` / refs npz 同梱 (§6.1 案 A の Stage 2) は撤回。A seed は temporal-stability
のみ (`refs={}` の stage-1 fallback 経路) で「概略領域の提案」に用途限定

## 7. 出力仕様

- **出力先**: `-o <dir>`。省略時は metadata.json と同じディレクトリの `minimap/` サブディレクトリ
- **ファイル名**: export の `_format_filename` token 実装を流用し、default
  `{idx:03}_minimap_{start}.mp4`
- **対象試合**: default split と同じ集合 (type=match、`post_match: true` 除外)。
  `--include 1,3,5` (export と同形式、matches[].index 基準) で絞り込み可
- **crop encode**: 正規化座標 → pixel 変換時に mod-2 丸め (h264 yuv420p 制約)。
  encode 品質設定は export h264 と同一。音声は source stream copy で保持
- **`--region X,Y,W,H` (crop の primary、PoC checkpoint 決定)**: source 解像度の
  **pixel 指定** (ユーザーが screenshot で測りやすい)。内部で正規化して全試合に適用
  (`source: "manual"`)。crop 実行はこの flag 指定時のみ
- **提案モード (`--region` 省略時)**: 案 A seed (temporal-stability consensus) で試合ごとの
  提案領域を検出し、`--region X,Y,W,H` としてそのまま貼れる pixel 形式で表示する。
  **crop はせず metadata にも書かない**。提案の有無に関わらず exit 4 (検知失敗 = 自動確定
  不可) + `--region` 案内を表示。HUD 位置は録画者ごとに固定なので測定・調整は初回のみ。
  seed 提案は「出た提案は GT 中心精度で信頼できる・場面によっては出ない」という best-effort
  契約 (D3 実機検証 2026-07-09 で確定。calm 場面や配信者 overlay との merge では提案なし +
  warning になる)
- **進捗表示**: export と同型 (plain text 1 行形式 / `--quiet`)。`--json` (GUI subprocess mode)
  は v1 では実装しない (GUI 統合は別 issue)

## 8. エラー処理

| 状況 | 挙動 |
| --- | --- |
| 提案モード (`--region` なし) | 提案表示のみで常に exit 4 + `--region` 案内 (crop なし、metadata write なし)。seed が全試合で不成立なら「提案なし」の旨も表示 |
| 提案モードである試合の consensus 不成立 (window 閉 / 高透過) | その試合は「提案なし」表示 (warning) |
| `--region` が範囲外・不正 (parse 不能 / 負値 / frame はみ出し / 過小 w,h < 16px) | exit 5 (設定値不正) |
| source 動画欠落 / ffmpeg 失敗 | exit 2 / exit 3 (既存 exit code 表のまま、新設なし) |
| GPU encoder init 失敗 | libx264 retry (#761 パターン踏襲) + notice |
| `--region` crop の一部試合 encode 失敗 | export と同じ summary 契約 (failure > 0 → exit 1 / SIGINT cancel → exit 130) |

## 9. テスト計画 (TDD)

1. `areamap.py` seed 検出 unit: 合成フレーム (静的 overlay + 動的背景) で検出 / consensus /
   ばらつき warning — red first
2. mod-2 丸め / 正規化⇄pixel 変換 / `--region` parse・validation (境界値) / 提案モードの
   exit 4 + 表示契約
3. schema 適合: `test_metadata_schema.py` / `test_metadata_types.py` に `minimap_regions`
   ケース追加 (valid / 範囲外 / source 空文字 reject / 未知 field reject)
4. write-back: atomic write + 既存 field 保全 (brightness_samples / capture_regions が
   消えないこと)。`--from-metadata` 経路の preserve は対象外 (minimap は split 後段の別 command)
5. crop encode: ffmpeg 引数組み立て (crop filter / slot / fallback) を mock で検証
6. slow 実機: PoC GT を用いた seed 提案の検証。契約 = seed は best-effort
   (D3 2026-07-09 確定)。visible=true + bbox あり (5 case): 提案が出た場合は中心が GT bbox
   内 (誤誘導ゼロ) を per-case assert + 5 case 中 >=3 で提案が出ることを集計 assert。
   visible=false (t=2354): 提案なし assert。visible=true + bbox null (t=1106): slow
   assert 対象外 (city map window、提案モードは試合内 sample のみで発生しない)。
   IoU >= 0.9 の自動検出 gate は sec.6.3 縮小により**課さない**
7. GUI: zod parse + metadataStore round-trip (vitest) + `npm run typecheck`
   (vitest は型検査しない教訓)
8. codegen drift: `python scripts/codegen/generate.py` 後に diff ゼロ
9. released 経路非回帰: detector.py / scorebar.py / cache 非接触を PR diff で構造的に示す

## 10. 実機検証 (Iron Law 6)

- GPU crop encode (NVENC / QSV / AMF) は mock 不可 → PR 時に AskUserQuestion で Idios に依頼
- 7h 動画クラスの全試合 crop encode は detached Start-Process 手順
  (`feedback_long_gpu_job_detached_execution`) を検証手順書に含める

## 11. スコープ境界 (やらない)

- VTuber inset 対応 (v0.4.0 期 #866。正規化座標による forward-compat のみ確保)
- 円形ナビマップの切抜き (需要が出たら別 issue)
- 動的追跡 (試合内 region timeline)
- GUI 統合 (実行ボタン / 領域 overlay 表示 / `--json` mode) — 別 issue 起票候補として PR 後に提示。
  **preview 上の領域ドラッグ選択**は `--region` 初回測定ハードルの本命解消策として同 issue で扱う
- 拠点・部隊座標のデータ抽出 (L4+ メタデータ化の領域)
- `minimap <video>` 直接一気通貫 (detect 内蔵はしない。metadata.json 前提)
- **自動確定 crop (IoU 0.9 級の自動検出)** — §6.3 STOP により v1 スコープ外。アルゴリズム刷新
  (window chrome template matching 等) は需要と成算が揃ったら別 issue

## 12. Doc 更新 (#818 SSoT gate 準拠)

- `docs/cli-spec.md`: 新 command 構文 + 「実体はエリアマップ window」の用語注記
- `docs/output-spec.md`: minimap 出力のマトリクス追加
- `docs/metadata-spec.md`: `minimap_regions` field (semantics / source ("manual" のみ write) /
  欠落規約。`map_name` は §6.3 撤回済みなので書かない)
- `CLAUDE.md`: モジュール表 (`areamap.py` / `commands/minimap.py`) + コマンド例 1 行
- `docs/system-architecture.md` / `docs/detection-map.md`: 該当記述があれば整合 (実装時に
  再確認し、変更不要なら PR 本文で根拠を明記)

## 13. 参照

- issue: [#481](https://github.com/Idios/kobutachan-allaganeye/issues/481) / parent
  [#753](https://github.com/Idios/kobutachan-allaganeye/issues/753)
- roadmap: [2026-06-29-v030-l3-roadmap.md](2026-06-29-v030-l3-roadmap.md) §4 Phase 2 /
  rescope #872
- 基盤: [#810 capture_regions spec](2026-07-07-capture-regions-metadata-schema-design.md)
  (§4 に「coarse=band ROI を game 矩形と誤読しない」注意あり — 本 design は capture_regions を
  v1 では消費しない) / export encoder pool (#761 / #791)
- 前例: `audio/refs/` 派生特徴量同梱 (#306) / `vtuber_region_experiment.py` (PoC script) /
  `detect_scorebar_band_region` (multi-frame consensus)
- release gate: `docs/release-process.md` §v0.3.0 (minimap 切抜き検証)
