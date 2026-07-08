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

## 3. 全体像

- **CLI**: `allaganeye minimap <metadata.json> [-o <dir>] [--region X,Y,W,H] [--include 1,3]`
  — detect / split 済みの metadata.json を入力に、試合ごとにエリアマップ領域を on-demand 検出
  → 座標を metadata に write-back → crop + h264 再エンコードで試合ごとの MP4 を出力
- **v0.3.0 対象入力**: 標準 OBS full-frame + masked 録画。VTuber inset は v0.4.0 期 (#866)。
  検出・記録は frame 正規化座標 (0–1) で行い、将来 `capture_regions` の game 矩形と合成できる
  forward-compat を確保する (位置合成のみ。v1 実装は full-frame 前提)
- **検出は毎回 fresh 実行** (detection cache 非使用)。detect param を追加しないため cache key
  3 箇所問題 (`feedback_detection_flag_cache_key`) は構造的に発生しない

## 4. コンポーネント構成

| モジュール | 責務 |
| --- | --- |
| `allaganeye/video/areamap.py` (新規) | エリアマップ window 検出。PoC 勝者アルゴリズム + 試合単位 multi-frame consensus (`detect_scorebar_band_region` と同型設計)。**detector.py / scorebar.py 非接触** |
| `allaganeye/commands/minimap.py` (新規) | command orchestration: metadata 読込 → source 動画解決 → 試合ごと検出 → atomic write-back (`detection/metadata_writer` 再利用) → crop encode → 進捗表示 |
| `allaganeye/export/` (再利用) | `enumerate_h264_encoders` の slot 決定 + GPU init 失敗時の libx264 retry (#761 `_GPU_ENCODER_FAILURE_PATTERNS`) を流用。crop filter (`-vf crop=…`) を通す手段 (export encode 関数の optional 拡張 or 兄弟関数) は plan で確定 |
| `scripts/areamap_poc.py` (新規) | PoC: 両検出案の実サンプル比較 (`vtuber_region_experiment.py` 前例) |

## 5. データフロー / metadata schema

```text
metadata.json (detect/split 済) → allaganeye minimap
  → 試合ごと: 試合中フレーム N 枚 sample → areamap 検出 → consensus で領域確定
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
                "confidence": 0.89, "source": "auto" },  // $defs CaptureRegion 再利用
    "map_name": "onsal_hakair"        // string | null (map 照合案勝利時の副産物)
  }
]
```

- `region` は `$defs.CaptureRegion` を再利用 (正規化座標 0–1)。`source` は `"auto"` /
  `"manual"` (`--region` 指定時)。free string + 文書化 (#810 の forward-compat 哲学)
- `map_name` は required nullable。値は free string (現行候補: `"onsal_hakair"` /
  `"seal_rock"` / `"fields_of_glory"` / `"borderland_ruins"`)。edge 案勝利時は常に null
- 検出失敗した match は **entry を作らない** (欠落 = 未検出。領域不明を偽装しない、#810 同方針)
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

## 7. 出力仕様

- **出力先**: `-o <dir>`。省略時は metadata.json と同じディレクトリの `minimap/` サブディレクトリ
- **ファイル名**: export の `_format_filename` token 実装を流用し、default
  `{idx:03}_minimap_{start}.mp4`
- **対象試合**: default split と同じ集合 (type=match、`post_match: true` 除外)。
  `--include 1,3,5` (export と同形式、matches[].index 基準) で絞り込み可
- **crop encode**: 正規化座標 → pixel 変換時に mod-2 丸め (h264 yuv420p 制約)。
  encode 品質設定は export h264 と同一。音声は source stream copy で保持
- **`--region X,Y,W,H`**: source 解像度の **pixel 指定** (ユーザーが screenshot で測りやすい)。
  内部で正規化して全試合に適用、検出は skip (`source: "manual"`)
- **進捗表示**: export と同型 (rich text bar / `--quiet`)。`--json` (GUI subprocess mode) は
  v1 では実装しない (GUI 統合は別 issue)

## 8. エラー処理

| 状況 | 挙動 |
| --- | --- |
| ある試合で consensus 不成立 (window 閉 / 高透過) | warning + その試合の MP4 skip (metadata entry なし)。partial success は exit 0 |
| 全試合で検出失敗 | exit 4 (検知失敗) + `--region` 手動指定の案内を表示 |
| `--region` が範囲外・不正 | exit 5 (設定値不正) |
| source 動画欠落 / ffmpeg 失敗 | exit 2 / exit 3 (既存 exit code 表のまま、新設なし) |
| GPU encoder init 失敗 | libx264 retry (#761 パターン踏襲) + notice |
| 試合中の window 移動疑い (sample 間ばらつき大) | 多数派領域を採用 + warning、`confidence` に反映 (動的追跡はしない) |

## 9. テスト計画 (TDD)

1. `areamap.py` 検出 unit: 合成フレーム (静的 overlay + 動的背景) で検出 / consensus /
   ばらつき warning — red first
2. mod-2 丸め / 正規化⇄pixel 変換 / `--region` parse・validation (境界値)
3. schema 適合: `test_metadata_schema.py` / `test_metadata_types.py` に `minimap_regions`
   ケース追加 (valid / 範囲外 / source 空文字 reject / map_name null)
4. write-back: atomic write + 既存 field 保全 (brightness_samples / capture_regions が
   消えないこと)。`--from-metadata` 経路の preserve は対象外 (minimap は split 後段の別 command)
5. crop encode: ffmpeg 引数組み立て (crop filter / slot / fallback) を mock で検証
6. slow 実機: OBS baseline 5 本 + masked サンプルで検出成功率 + PoC GT と IoU 突合
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
- GUI 統合 (実行ボタン / 領域 overlay 表示 / `--json` mode) — 別 issue 起票候補として PR 後に提示
- 拠点・部隊座標のデータ抽出 (L4+ メタデータ化の領域)
- `minimap <video>` 直接一気通貫 (detect 内蔵はしない。metadata.json 前提)

## 12. Doc 更新 (#818 SSoT gate 準拠)

- `docs/cli-spec.md`: 新 command 構文 + 「実体はエリアマップ window」の用語注記
- `docs/output-spec.md`: minimap 出力のマトリクス追加
- `docs/metadata-spec.md`: `minimap_regions` field (semantics / source / map_name / 欠落規約)
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
