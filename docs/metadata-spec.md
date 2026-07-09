# metadata.json 仕様

`metadata.json` は CLI (`allaganeye`) と GUI (L2a Tauri) の間の**唯一の契約**。#463 Phase 1 で確立。

## SSoT 二層構造 (#612, 2026-04-28 確定)

スキーマ定義は二層で SSoT を分担する:

| 層 | 役割 | ファイル |
| --- | --- | --- |
| 機械可読の正 | draft-2020-12 JSON Schema。型生成と writer 検証の根拠 | [`schemas/metadata.schema.json`](../schemas/metadata.schema.json) |
| 人間可読の正 | フィールドの意味、書き込み契約、編集契約、ユーザー手動編集の挙動 | 本 doc |

各言語の型は JSON Schema から自動生成する:

| 言語 | 出力 | ツール | コマンド |
| --- | --- | --- | --- |
| Python | [`allaganeye/metadata_types.py`](../allaganeye/metadata_types.py) (`TypedDict`) | `datamodel-code-generator` | `python scripts/codegen/generate.py --py` |
| TypeScript | [`gui/src/types/metadata.generated.ts`](../gui/src/types/metadata.generated.ts) (`interface`) | `json-schema-to-typescript` | `python scripts/codegen/generate.py --ts` (または `cd gui && npm run generate-types`) |
| Rust | (生成しない) | — | `gui/src-tauri/src/lib.rs` は `serde_json::Value` で passthrough |

zod schema ([`gui/src/types/metadata.schema.ts`](../gui/src/types/metadata.schema.ts)) は手書き継続。zod でしか表現できない refine 制約 (`end_time >= start_time` 等) があるため。zod の field set / required は CI の `zod-schema-integrity.test.ts` (#612) が JSON Schema と照合する。

`gui/src/types/metadata.ts` は generated.ts からの re-export shim。GUI 編集フィールド (`name` / `type_override` / `edited`) は shim 側の `Match` interface で extend し、`normalizeForPersistence` (`metadataStore.ts`) が永続化前に剥がす。

### JSON Schema は strict、reader は緩い (passthrough は別レイヤ)

JSON Schema は writer 契約として strict (additional properties は受け付けない)。一方、読み取り側の前方互換性 (legacy `note` / 未知フィールドを落とさない) は reader レイヤで担保する:

- GUI: zod の `.passthrough()` (root と Match)
- CLI: Python `dict` は素通し (jsonschema validate は `tests/test_metadata_schema.py` でのみ実施、runtime read は dict のまま)

この二層により、機械的契約の厳密性と運用上の forward-compat を両立する。

### 編集ワークフロー

1. `schemas/metadata.schema.json` を編集
2. 必要に応じて本 doc (`docs/metadata-spec.md`) を更新
3. `python scripts/codegen/generate.py` で両言語を再生成
4. zod schema (`metadata.schema.ts`) の field set / required を JSON Schema に揃える (CI が integrity test で検出する)
5. 生成物 (`metadata.generated.ts` / `metadata_types.py`) を commit

詳細は [`docs/l2-workflow.md`](l2-workflow.md) §schema 編集ワークフロー を参照。

## 概要

- **役割**: 検知結果 (match boundaries) とパラメータを構造化 JSON として保存。CLI `split --from-metadata` と GUI 双方が読み取り元とする。
- **生成者**: `allaganeye detect <video>` と `allaganeye split <video>` (legacy パス)
- **消費者**: `allaganeye split --from-metadata <metadata.json>` と GUI
- **更新者**: GUI の `[適用]` ボタン (加えて `allaganeye detect <video>` の再実行は上書き)

## スキーマ定義 (schema v1)

ルートは JSON オブジェクト。以下のフィールドを持つ。

| フィールド | 型 | 必須 | 意味 | 範囲 / 形式 |
| --- | --- | --- | --- | --- |
| `schema_version` | string | 新規書き込みは ✓ / 読み込み時は欠落許容 | ペイロードのスキーマ版数 (#515) | 現行は `"1"`。欠落時は v1 として解釈 |
| `source` | string | ✓ | 元動画ファイルの絶対パス (OS 表記そのまま) | 非空 |
| `source_duration` | number | ✓ | 元動画の総秒数 | > 0 |
| `source_duration_display` | string | ✓ | 人間可読な長さ表示 | `HH:MM:SS` または `MM:SS` |
| `source_fps` | number | 新規書き込みは ✓ / 読み込み時は欠落許容 | 録画フレームレート (#465) | > 0。欠落時は GUI が `DEFAULT_FPS=60` で代替 |
| `detected_at` | string | ✓ | 検知パイプライン開始直前のタイムスタンプ (`detection_started_at` と同値、後方互換のため維持) | ISO 8601 (例: `2026-04-22T00:00:00Z`) |
| `detection_started_at` | string | 新規書き込みは ✓ / 読み込み時は欠落許容 (#586) | 検知パイプライン開始直前のタイムスタンプ。`detected_at` と同値 (案 B 命名) | ISO 8601 |
| `detection_completed_at` | string | 新規書き込みは ✓ / 読み込み時は欠落許容 (#586) | metadata.json 書き込み直前のタイムスタンプ。GUI CompleteScreen の「所要」表示に `completed - started` で使う | ISO 8601 |
| `detection_params` | object | ✓ | 検知に使われたパラメータ (後述) | (object) |
| `matches` | array | ✓ | 試合セグメント列 (0 件可) | |
| `gaps` | array | ✓ | 試合間の空白区間列 (0 件可) | |
| `warnings` | array | 新規書き込みは ✓ (デフォルト `[]`) / 読み込み時は欠落許容 | 構造化警告一覧 (#518) | 個々のエントリは §warnings 参照 |
| `system_info` | object | 新規書き込みは ✓ / 読み込み時は欠落許容 (#591) | GPU vendor probe スナップショット | 後述 §system_info 参照 |
| `brightness_samples` | object | 新規書き込みは Pass 1 が走った場合のみ ✓ / 読み込み時は欠落許容 (#569) | GUI complete 画面用の輝度タイムライン | 後述 §brightness_samples 参照 |
| `capture_regions` | object | 新規検知では ✓ / cache-hit は記録があれば ✓ / 読み込み時は欠落許容 (#810) | 検出が解決した capture region timeline (coarse + segments + 縮退 provenance) | 後述 §capture_regions 参照 |

### `detection_params` オブジェクト

| フィールド | 型 | 意味 |
| --- | --- | --- |
| `sample_interval` | number | Pass 1 サンプリング間隔 (秒) |
| `blackout_threshold` | number | 暗転判定輝度閾値 (0-255) |
| `min_match_duration` | number | 最小試合長 (秒) |
| `min_blackout_duration` | number | 最小暗転長 (秒) |
| `no_audio` | boolean | 音声昇格無効化フラグ |
| `use_gpu` | number \| boolean \| null | GPU モード (null = auto 判定) |
| `workers` | number \| null | 並列ワーカー数 (null = auto) |
| `vtuber` | boolean | `--vtuber` flag の値 (#821。VTuber path は auto-trigger しないため request = resolved)。新規書き込みは常に出力 / 読み込み時は欠落許容 (欠落 = false、#821 導入前の出力) |
| `masked` | boolean | `--masked` flag の値 (request、#821)。fallback は 0-blackout で auto-trigger もするため、resolved path は `masked_fallback_used` を参照。新規書き込みは常に出力 / 読み込み時は欠落許容 (欠落 = false) |
| `masked_fallback_used` | boolean | mask-free 領域 fallback が実際にこの結果を生成したか (明示 `--masked` / 0-blackout auto-trigger とも true、#821)。新規書き込みは常に出力 / 読み込み時は欠落許容 (欠落 = false) |

### `Match` オブジェクト (`matches[]`)

| フィールド | 型 | 必須 | 意味 |
| --- | --- | --- | --- |
| `index` | integer | ✓ | 1 始まりの順序番号 |
| `start_time` | number | ✓ | 試合開始秒 (>= 0) |
| `end_time` | number | ✓ | 試合終了秒 (>= start_time) |
| `start_display` | string | ✓ | 開始表示 (MM:SS / H:MM:SS) |
| `end_display` | string | ✓ | 終了表示 |
| `duration` | number | ✓ | 長さ (秒) |
| `duration_display` | string | ✓ | 長さ表示 (例: `15m15s`) |
| `type` | string | ✓ | `fl_match` または `unknown` |
| `output_file` | string | — (NotRequired) | 出力 MP4 ファイル名 (相対パス、metadata.json と同ディレクトリ想定)。通常 match は常に存在する。`post_match: true` の match は MP4 を生成しないため本フィールドを持たない |
| `post_match` | boolean | — (NotRequired) | post-match trailing 非破壊フラグ (#805 段階2)。`true` のとき試合後 trailing (lobby/city) を表す非破壊フラグ。default split 出力 (MP4) からも `allaganeye export` (CLI / GUI 共通経路) からも**機能的に除外**されるが metadata には保持される。GUI `[適用]` (`normalizeForPersistence`) でもフラグは保持される。absent/false = 通常 match。視覚的な差分化 (badge / dimmed) と ExportScreen の選択不可 UX は Phase 2 |

### `system_info` オブジェクト (#591)

GPU vendor probe スナップショット。`probe_gpu_vendors()` の結果と、`_VENDOR_PREFERENCE` のスナップショット、実際 detect 経路で使った vendor を保存する。GUI export 画面が H.264 再エンコードのエンコーダ選択 (NVENC / QSV / AMF / libx264 fallback) に使用する。

| フィールド | 型 | 必須 | 意味 |
| --- | --- | --- | --- |
| `gpu_vendors_available` | array of string | ✓ | probe で検出された vendor 識別子の集合。`{"nvidia","amd","intel"}` の subset。空配列はその環境に GPU が無い (CPU only) |
| `gpu_vendor_used` | string \| null | ✓ | 実際 detect で使った vendor。CPU 強制 (`--no-gpu`) / cache hit / `split --from-metadata` では `null` |
| `vendor_preference` | array of string | ✓ | `gpu_detector._VENDOR_PREFERENCE` のスナップショット。現状 `["nvidia","amd","intel"]` |
| `gpu` | array of string | — (NotRequired) | `get_gpu_info_lines()` が返す GPU モデル名文字列のリスト。GUI の `enumerate_h264_encoders` が NVENC SKU ルックアップに使用 (#761)。空配列 = GPU 無し / 未取得 |

書き込みパス:

- `allaganeye detect`: detect 経路で probe → vendor_used = 採用した vendor (CPU 強制なら null)
- `allaganeye split <video>` (legacy): cache miss なら detect と同じ / cache hit は probe を実行し vendor_used = null
- `allaganeye split --from-metadata`: probe を実行し vendor_used = null (split 時点では vendor を選ばないため)

GUI export 画面は `system_info.gpu_vendors_available` / `vendor_preference` / `gpu` を `enumerate_h264_encoders` Tauri コマンドに渡し、H.264 エンコーダスロット一覧 (`EncoderSlotJson[]`) を取得する。`system_info` を持たない pre-#591 metadata.json は libx264 にフォールバックする。

#### `system_info` の GPU field のみ (OS/CPU/Memory は対象外)

`metadata.json` の `system_info` は **GPU field のみ** (`gpu_vendors_available` / `gpu_vendor_used` / `vendor_preference` / `gpu`) を保持する。Python 側の `allaganeye/system_info.py` には他にも CPU info / OS info / memory / disk 等を取得する helpers があるが、それらは **CLI `-v` verbose header 用**で、`metadata.json` には書き込まれない。

GUI 側で OS/CPU/Memory/Disk 等の環境情報が必要な場合 (例: bug_report.yml `environment` placeholder format) は metadata から取らずに **Tauri 側で別途 probe** する (例: `probe_environment_info` + `sysinfo` crate、#669 PR #726 で実装)。metadata.system_info を OS/CPU 等で拡張するのは schema 互換性を切る big change のため避ける。

### `brightness_samples` オブジェクト (#569)

GUI complete 画面の輝度タイムライン (`BrightnessTimeline` SVG) 用の事前計算済み輝度配列。Pass 1 のサンプリング結果 (timestamp → 平均輝度) を最大 512 点までダウンサンプルして埋め込む。GUI は metadata.json を読むだけでタイムラインを描画でき、`debug-brightness` を再実行する必要が無い。

| フィールド | 型 | 必須 | 意味 |
| --- | --- | --- | --- |
| `interval_s` | number | ✓ | 配列の各要素が表す秒間隔 (例: `25.0` なら `values[i]` は `i * 25` 秒の輝度) |
| `values` | array of number | ✓ | 平均輝度 (0-255 の float) を時系列順に並べたもの。最大 512 要素 |

**書き込みパス別の挙動 (#569 + #644)**:

| 経路 | 書き込み |
| --- | --- |
| `allaganeye detect` (Pass 1 走行) | ✓ 書く (#569) |
| `allaganeye split` (新規検知、Pass 1 走行) | ✓ 書く (#644 で `brightness_callback` 配線) |
| `allaganeye split` (cache hit、Pass 1 skip) | ✗ 欠落 (cache に brightness を含めない設計) |
| `allaganeye split --from-metadata` | 元 metadata から **preserve** (元が欠落なら欠落、PR #626 detection_started_at と同パターン) |

cache hit / Pass 1 未実行の場合は key 自体を省略する (`null` ではなく key 不在)。GUI 側は欠落許容済 (#569) のため、欠落時は `sampleBrightness()` 固定波形 fallback で描画する。`allaganeye split --no-cache` を使えば常に Pass 1 を走らせて書ける。

GUI complete 画面は `metadata.brightness_samples?.values` を読み、欠落時はサンプルデータ (`buildSampleBrightness`) にフォールバックする。

### `capture_regions` オブジェクト (#810)

検出が解決した game capture 領域 (`allaganeye/video/capture_region.py::RegionTimeline` の
serialize 形)。consumer (Pass 1 wiring #809 / scorebar ROI #480 / minimap #481 / GUI) が
一貫参照する共有スキーマ。矩形は解像度非依存の正規化座標 `[0,1]`。

| フィールド | 型 | 必須 | 意味 |
| --- | --- | --- | --- |
| `coarse` | CaptureRegion | ✓ | **その run の Pass 1 輝度計測に実際に使われた領域**。標準 OBS = FULL_FRAME (`{0,0,1,1}`, source=`"fallback"`) / `--vtuber` = scorebar 帯 ROI (source=`"band"`、**game 全矩形ではない**) / masked fallback 採用 run = mask-free game 矩形 (source=`"tierA"`) |
| `segments` | array of RegionSegment | ✓ | Tier B per-segment 精密領域 (`{"time_range": [t0, t1], "region": CaptureRegion}`)。**現状は常に `[]`** (#480 P4 が埋める) |
| `fallback_reason` | string \| null | ✓ (nullable) | band anchor 縮退の provenance。`"anchor_error"` (Stage 0 例外) / `"consensus_miss"` (consensus 不成立) / `null` (縮退なし)。free string: 読み手は unknown 値を受容 |

CaptureRegion は `{x, y, w, h, confidence: number [0,1], source: string}`。`source` の文書化値:
`"fallback"` (FULL_FRAME) / `"band"` (scorebar 帯 ROI) / `"tierA"` (game 矩形) / `"tierB"`
(将来 precise)。free string のため読み手は unknown 値を受容すること。

masked の縮退 (mask 不発見で標準 path に defer) は本フィールドではなく既存の
`detection_params.masked` / `masked_fallback_used` フラグ対から導出する
(`masked=true` かつ `masked_fallback_used=false`)。

**書き込みパス別の挙動**:

| 経路 | 書き込み |
| --- | --- |
| `allaganeye detect` / `allaganeye split` (新規検知) | ✓ 常に書く (OBS は coarse=FULL_FRAME) |
| cache hit | cache 記録があれば ✓ / pre-#810 cache は標準 path 確定 (vtuber=false かつ masked_fallback_used=false) なら FULL_FRAME を合成、vtuber / **masked fallback 採用 run** なら ✗ 欠落 (領域不明を偽装しない)。判定述語は resolved flag (`masked_fallback_used`) であり request flag (`masked`) ではない: masked 要求でも fallback 不採用なら標準 path が FULL_FRAME で計測しているため合成が正 |
| `allaganeye split --from-metadata` | 元 metadata から **preserve** (元が欠落なら欠落)。`split --from-metadata` と cache 読出しの preserve 値は shape 検証 (sanitize) され、malformed 値は warning とともに省略される (#810 codex F1) |

cache には `.detection_cache.json` top-level (`masked_fallback_used` と同型、cache key 非対象)
で保存される。GUI は読み取り時 zod `CaptureRegionsSchema` (optional) で検証し、`[適用]`
(`normalizeForPersistence`) でも保持する (GUI 側 consumer は未実装、round-trip のみ)。

### `Gap` オブジェクト (`gaps[]`)

試合間の 5 分以上の空白 (5 分未満は含まれない、`min_gap=300.0` による)。

| フィールド | 型 | 必須 | 意味 |
| --- | --- | --- | --- |
| `start_time` | number | ✓ | 空白開始秒 |
| `end_time` | number | ✓ | 空白終了秒 |
| `start_display` | string | ✓ | 開始表示 |
| `end_display` | string | ✓ | 終了表示 |
| `duration` | number | ✓ | 長さ (秒) |
| `duration_display` | string | ✓ | 長さ表示 |

### 未知のトップレベルフィールド

読み手は **未知のトップレベルフィールドを捨てず pass-through する**こと (zod では `.passthrough()`、Python は `dict` をそのまま保持)。これにより:

- 古い CLI が書いた `note` フィールド (#463 以前) を新 GUI が落とさない
- 将来 `schema_version` 等を足した際の下方互換性を確保

GUI は読み取った未知フィールドを書き戻しで保持する義務はない (参考情報扱い)。

## 生成契約

### `allaganeye detect <video>`

- probe → cache check → detect → cache save → `metadata.json` atomic write
- 出力: `<output_dir>/metadata.json` のみ (MP4 は作らない)
- `matches[].output_file` は `match_NNN.mp4` のプレースホルダ (split 時に生成される実ファイル名)。**`post_match: true` の match は `output_file` を持たない** (active match のみプレースホルダが付く)
- 既存 `metadata.json` は**上書き** (GUI の `metadata.original.json` バックアップには触らない)

### `allaganeye split <video>` (legacy)

- detect + split を一気通貫 (後方互換)
- probe → detect → split (ffmpeg -c copy) → `metadata.json` atomic write
- `matches[].output_file` は実際に書き出された MP4 のパス。**`post_match: true` の match は MP4 を生成せず `output_file` を持たない** (metadata には保持)

### `allaganeye split --from-metadata <metadata.json>`

- `metadata.json` を source of truth として読む (detection は走らない)
- `source` フィールドで元動画を解決 (相対パスは `metadata.json` のディレクトリ起点)
- split → `metadata.json` を **`config.output_dir`** に**書き直し**
- 書き直し時に未知フィールド (legacy `note` 等) は**落ちる**。GUI で保持したい情報は GUI 側 state に保つ
- **`post_match: true` の match は MP4 を生成せず `output_file` を持たない** (detect / split と一貫)。3 経路すべてで post_match match は MP4 除外 + metadata 保持の動作が統一されている
- **`detection_started_at` / `detection_completed_at` の保持** (#586): 再検知してないので元 metadata の値を pass-through し、GUI「所要」表示が「検知時の所要」を維持する。pre-#586 metadata (両フィールド欠落) では fresh capture (started=`detected_at` / completed=書き込み直前) で fallback し post-#586 形式に揃える

## 書き込み方針

- **原子的書き込み**: temp ファイル (`.tmp` サフィックス) に書いてから `os.replace` で対象にリネーム。中断時の破損なし
- **エンコーディング**: UTF-8 / BOM なし / `ensure_ascii=false` / `indent=2`
- **改行**: LF (JSON 仕様上問題ないが、ツール側は特に気にしない)
- **ファイル名**: `metadata.json` 固定 (GUI 編集時のバックアップは `metadata.original.json`)

## GUI 編集契約

GUI は以下のフィールドを in-memory で編集し、`[適用]` 時に `metadata.json` へ書き戻す。

### 編集可フィールド

| GUI の一時フィールド | 書き戻し時の反映先 |
| --- | --- |
| `Match.edited.start_time` | `Match.start_time` に上書き (`edited` 自体は落とす) |
| `Match.edited.end_time` | `Match.end_time` に上書き |
| `Match.type_override: fl_match` \| `unknown` | `Match.type` に上書き |
| `Match.type_override: skip` | **書き戻さない** (export 時に除外する GUI ローカル情報) |
| `Match.name` | **書き戻さない** (GUI 表示専用、metadata.json には持たない) |

### 読み取り専用

以下は GUI では絶対に書き戻さない (CLI の観測記録として保全):

- `source`, `source_duration`, `source_duration_display`, `source_fps`
- `detected_at`, `detection_started_at`, `detection_completed_at`, `detection_params`
- `gaps` (CLI が計算、GUI は表示のみ)

### 同一性保証

書き戻し後の `matches[]` は以下の形: GUI 編集フィールド (`edited` / `type_override` / `name`) は完全に除去され、スキーマ v1 の純粋形になる。

```ts
{ index, start_time, end_time, start_display, end_display,
  duration, duration_display, type, output_file?, post_match? }
```

> **`normalizeForPersistence` の `output_file` / `post_match` 挙動 (#805 段階2)**
>
> - `output_file` は **定義されているときのみ**書き出す (defined-only)。
>   `post_match: true` の match は `output_file` を持たないため、当該キーは
>   書き戻し後の object から省略される (Match 表の NotRequired と整合。
>   `output_file: undefined` というキーは emit しない)。
> - `post_match` フィールドは **passthrough する** (`...(m.post_match ? { post_match: true } : {})`)。
>   `[適用]` 実行後も `post_match: true` の match は非破壊フラグを保持し、
>   次回 split / export で MP4 化されない (除外 invariant を GUI 経路でも維持)。
>   truthy-only で書き出すため通常 match は flag-free のまま (`post_match: false`/
>   `undefined` は emit しない。detector / split / from-metadata の payload 規約と一致)。

## `metadata.original.json` policy

GUI による初回 `[適用]` 時のみ作成。

| トリガー | 動作 |
| --- | --- |
| GUI 初回 `[適用]` | `metadata.json` が存在し `metadata.original.json` が存在しない場合、前者を後者にコピーしてから書き戻す |
| GUI 2 回目以降 `[適用]` | `metadata.original.json` には触らない (初回時の純粋な detect 結果を保持) |
| `allaganeye detect` 再実行 | `metadata.json` を上書き、`metadata.original.json` には触らない (注: この場合 `.original` は古い状態のまま残り、ユーザーが手動管理) |
| GUI `[元に戻す]` (#516 完了、Phase 2 で実装) | `metadata.original.json` の内容で `metadata.json` を atomic 上書き。`.original` は読み取りのみで保持 |

## ユーザー手動編集シナリオ

| シナリオ | 期待動作 |
| --- | --- |
| metadata.json を削除 | GUI load でファイル未存在エラー。GUI は "No metadata. Run detect first." を表示 |
| 不正な JSON (parse error) | GUI load で zod が fail → error 表示。CLI `split --from-metadata` は `InputFileError` で exit code 2 |
| root が JSON object でない (array / 文字列等) | Rust `load_metadata` / Python `read_metadata` ともに "must be a JSON object" エラーで拒否 (挙動統一、#521) |
| 必須フィールド欠落 (source / matches 等) | zod validation で拒否、GUI はエラー表示。CLI は `InputFileError` |
| 意味不正 (negative time, end < start 等) | zod `.refine()` が検知 (GUI)、CLI は `float()` キャスト失敗で `InputFileError` |
| source ファイル移動・削除 | CLI は `InputFileError` (`source video not found`) / GUI は `[書き出し]` 時に同様エラー |
| 未知のトップレベルフィールド (legacy `note` 等) | 無視して load 成功 (`.passthrough()`)、ただし次回 CLI 書き直しで落ちる |

## schema_version (#515)

ペイロードのスキーマ版数を宣言して将来の breaking change に対する migration 基盤を提供する。

### 版数の表

| version | 状態 | 概要 |
| --- | --- | --- |
| (欠落) | 読み込み時に v1 として解釈 | pre-#515 の出力。自動で v1 扱い、ファイルは書き換えない |
| `"1"` | 現行 | `allaganeye detect` / `allaganeye split` が書き込む |
| `"2"` 以降 | 未定義 | 将来のスキーマ拡張用。未実装版を読み込むと `InputFileError` で拒否 |

### migration policy

- **Python 側** (`allaganeye/detection/migrations.py`):
  - `CURRENT_SCHEMA_VERSION` が現在の版 (`"1"`)
  - `MIGRATIONS: dict[str, Callable]` に `from_version -> fn` を登録
  - `check_schema_version(payload, source)` が read_metadata から呼ばれ、未知の version を `InputFileError` で拒否 / 既知 legacy は accept
  - `apply_migrations(payload)` で登録済みチェーンを辿って現行版に昇格 (現状 v1 のみなので no-op)
- **GUI 側** (`gui/src/types/metadata.schema.ts`):
  - zod: `schema_version: z.literal(SCHEMA_VERSION).optional()` — 欠落 or `"1"` のみ accept、それ以外は reject
  - 新規書き込み時 (GUI 単体では行わないが、CLI の apply 後に自動付与)
- **読み込み挙動の一致**: Python `read_metadata` と GUI zod は両方とも「欠落 ok、`"1"` ok、他は error」で統一

### 新しい版を追加する手順

1. `CURRENT_SCHEMA_VERSION` を `"2"` に更新 (`allaganeye/detection/migrations.py`)
2. `MIGRATIONS["1"] = migrate_v1_to_v2` を追加 (v1 payload を v2 に変換する関数)
3. `_build_metadata_payload` の `"schema_version": "1"` を `"2"` に更新 (`allaganeye/commands/split_matches.py`)
4. zod の `SCHEMA_VERSION` を `"2"` に更新 (`gui/src/types/metadata.schema.ts`)
5. 本 doc の版数の表を更新
6. テスト: `tests/test_migrations.py` に migration 関数単体 + end-to-end 読み込みテスト

## 排他管理 (mtime 検知、#514)

GUI が `load_metadata` した瞬間のファイル mtime を `metadataStore.loadedMtimeMs` に保存し、`apply_changes` 呼び出し時に Rust 側へ `expectedMtimeMs` として渡す。Rust 側は `fs::metadata(path).modified()` から現在の mtime を取得し、渡された値と一致しなければ `conflict: ...` で拒否する。

- **検知単位**: epoch ms (u64)。Windows / Linux / macOS いずれも `fs::Metadata::modified()` が返す `SystemTime` を ms に丸めて比較
- **挙動**: 不一致時は Rust が `conflict: external modification detected ...` を返し、GUI は `conflictError` state に格納して `ConflictModal` を表示
- **ユーザー選択肢**:
  - **上書き** → `metadataStore.applyOverwrite()` で `expectedMtimeMs=null` 再送 (check bypass)
  - **リロード** → `metadataStore.reloadAfterConflict()` で metadata.json を再読み込み (GUI 編集は破棄)
  - **キャンセル** → `metadataStore.dismissConflict()` でモーダルのみ閉じる (編集は保持、ディスクに触らない)
- **新規書き込み** (target が未存在): mtime check 対象外。`expectedMtimeMs` が指定されても skip し通常書き込み
- **Rust command**: `get_metadata_mtime(path) -> Option<u64>` を追加。`apply_changes` の戻り値は書き込み後の mtime (`u64`) に変更され、GUI 側 `loadedMtimeMs` を自動更新

## draft auto save (#517)

GUI の編集バッファを `metadata.draft.json` に自動保存し、WebView のリロードやアプリクラッシュ時にも編集内容を復元できるようにする。

- **保存先**: `metadata.json` と同ディレクトリの `metadata.draft.json`。atomic write (`.tmp` → rename)
- **保存タイミング**: `metadataStore.updateMatch` 呼び出し後の debounce (デフォルト 500ms)。`setDraftSaveDelay(ms)` でテスト時短縮可能。**debounce 発火前に異常終了した場合、直近 500ms 以内の編集は失われる (データロス上限 = debounce 間隔)**
- **保存内容**: in-memory の Metadata そのまま (編集フィールド `name` / `type_override` / `edited` も含む)。zod の `MatchSchema.passthrough()` で load 時に pass-through
- **復元フロー**: `metadataStore.load` 成功後に自動で `loadDraft` を呼び、存在すれば `pendingDraft` にセット。`DraftRestoreModal` (App.tsx に global 配置) が「復元 / 破棄」を提示
- **metadata.json load 失敗時の挙動**: `metadata.json` が不正 / 不存在 / 破損で load が失敗した場合、`loadDraft` は呼ばれず (`metadata` が null のため早期 return)、復元 modal も表示されない。ユーザーは `metadata.json` を復旧してから再 load することで、残存する draft が復元候補として提示される。`metadata.draft.json` のみ単独で存在する状態での復元は対象外
- **source 不一致チェック**: draft の `source` が現在 load した metadata の `source` と異なる場合、stale draft として自動削除 (modal は出さない)。比較は Windows 前提で separator (`\\` ↔ `/`) と大文字小文字を正規化した上で行う (`normalizeSourcePath`)
- **source 以外のドリフト** (matches 数・detection_params・source_duration 等): 検知対象外。source が一致する限り draft は有効と見なす。metadata.json を CLI で再生成した場合の検知は §排他管理 (#514) で別途実装されている (mtime mismatch → `ConflictModal`)。本機能と排他管理は独立したレイヤ: mtime check が metadata 本体の同期を担当し、draft は GUI 編集バッファの保全を担当する。両者の相互作用は §排他管理と draft の相互作用 参照
- **apply 成功後**: `metadataStore.apply` が成功すると `clearDraft` を呼び、`metadata.draft.json` をディスクから削除
- **save 失敗の可視化**: `save_draft` 呼び出しが失敗 (disk full / permission denied / atomic rename 失敗等) すると `metadataStore.draftSaveError` に格納される。`scheduleDraftSave` は fire-and-forget だが state 経由で UI が検知可能 (toast / status bar 表示は Phase 3 以降で拡張予定)。次回 save 成功時に自動クリア
- **Rust commands**: `save_draft(path, draft)` / `load_draft(path) -> Option<Value>` / `clear_draft(path)` — すべて atomic、clear は no-op-when-missing
- **クラッシュ時のアトミック性**: `save_draft` は `write_metadata_atomic` ヘルパー (`.tmp` → atomic rename) を使用する。save 中のクラッシュでは `metadata.draft.json` は書き換え前の状態で残る (partial 書き込みは発生しない)。`metadata.draft.json.tmp` が残存することがあるが、次回 save で上書きされる / 次回 load で読み込み対象外のため cleanup は不要

### ユーザー選択肢 (DraftRestoreModal)

| ボタン | 動作 |
| --- | --- |
| 復元 | `pendingDraft` を `metadata` に適用し `dirty=true`。ディスクには触らない (ユーザーが [適用] で永続化) |
| 破棄 | `clearDraft()` を呼んで `metadata.draft.json` を削除し、`pendingDraft=null` |

draft の zod parse に失敗した場合は error-only modal を出し「破棄」のみ提示する。

### 排他管理 (#514) と draft (#517) の相互作用

GUI が `load` / `apply` / `reloadAfterConflict` を実行するとき、排他管理 (mtime) と draft (in-memory buffer) が同時に state を更新する。両者の契約を以下に固定:

- **`load` 順序**: `load_metadata` → `get_metadata_mtime` → set state → `refreshBackupStatus` → `loadDraft`。mtime 記録が完了してから draft 検査を行う
- **Modal 優先順位**: `conflictError` が非 null の場合、`DraftRestoreModal` は描画されない。`ConflictModal` (3 択: 上書き / リロード / キャンセル) を先に解消してから draft restore を提示
- **`apply` 成功時の順序**: `loadedMtimeMs` 更新 → `refreshBackupStatus` → `cancelDraftSave` → `clearDraft`。mtime を確実に更新した後に draft clear
- **`applyOverwrite` と draft**: `applyOverwrite` は `apply` と共通 helper (`runApply`) 経由なので、上書き成功後も draft clear が発火する
- **`reloadAfterConflict` 後の draft**: `reloadAfterConflict` は `load(filePath)` を呼ぶため、source 一致な draft があれば `DraftRestoreModal` が再提示される (ユーザー編集の救済として意図された挙動)

## warnings (#518)

検知 / scorebar / audio が発行する構造化警告の scaffold。v1 時点では常に空配列を書き出し、具体的な warning コードは後続 PR で追加する。

### エントリの形 (`Warning` / `MetadataWarning`)

```ts
interface MetadataWarning {
  code: string;            // 必須。コードキー (例: "audio_skipped")
  message_en?: string;     // 英語メッセージ。省略時は reader が WARNING_CODES で lookup
  severity?: 'info' | 'warn' | 'error';
  context?: Record<string, unknown>;  // コード固有の追加情報
}
```

### 読み書き契約

- **新規書き込み**: `allaganeye detect` / `allaganeye split` は常に `warnings` 配列を emit する。通常は空配列 (#805 段階2 以降は `post_match_trailing_dropped` も emit しない — 後述 §既知の warning コード一覧 参照)
- **読み込み**: `warnings` が欠落していても error にしない (pre-#518 の legacy metadata.json を許容)。GUI の zod schema は `optional`
- **pass-through**: 未知の `code` を reader が reject してはならない (forward compat)
- **emitter の責務** (後続 PR): `allaganeye/detection/warnings.py::WARNING_CODES` にコードキーを登録し、`build_warnings` で該当箇所から push

### 新しいコードを追加する手順

1. `allaganeye/detection/warnings.py::WARNING_CODES` に `"your_code": "english message"` を追加
2. 発行箇所から `MetadataWarning(code=..., severity=..., context=...)` を生成
3. `build_warnings` (または呼び出し経路) に集約
4. `docs/metadata-spec.md` § 既知の warning コード一覧 (以下) に行を追加

### 既知の warning コード一覧

| code | severity | context | 意味 | 備考 |
| --- | --- | --- | --- | --- |
| `post_match_trailing_dropped` | `warn` | `{start, end}` (秒) | 試合後の trailing セグメント (ロビー / 市街) が、早期候補ウィンドウで scorebar を検出できなかったため削除された ([#805](https://github.com/Idios/kobutachan-allaganeye/issues/805))。`context.start` / `context.end` が削除された区間の境界 | **【段階2 で emission 停止・deprecated】** #805 段階2 で `post_match` フラグ (#805 段階2) に置換され、`build_warnings` はこの code を **emit しなくなった**。フレッシュな detect / split 実行では本エントリは生成されない。ただし code は `WARNING_CODES` registry に残置されており (後方互換)、旧 metadata.json に含まれる本エントリを `sanitize_warnings` で引き続き読み取れる。旧フォーマット (本警告を含む metadata.json) を `split --from-metadata` で読んだ場合でも crash しない (forward-compat reader が pass-through) |

## `minimap_regions` フィールド (#481)

`allaganeye minimap --region X,Y,W,H` (crop モード) が書き込む、エリアマップ window の切り抜き座標リスト。

### セマンティクス

| フィールド | 型 | 必須 | 意味 |
| --- | --- | --- | --- |
| `minimap_regions` | array of MinimapRegionEntry | — (NotRequired) | フィールド自体が欠落 = `allaganeye minimap --region` を一度も実行していない。空配列は対象 match が 0 件だったことを意味する |

#### `MinimapRegionEntry` オブジェクト

| フィールド | 型 | 必須 | 意味 |
| --- | --- | --- | --- |
| `match_index` | integer | ✓ | 対象 match の `matches[].index` (1 始まり) |
| `region` | CaptureRegion | ✓ | 切り抜き領域（正規化座標 [0,1]） |

`CaptureRegion` は `{x, y, w, h, confidence: number [0,1], source: string}` の共通スキーマ（[§`capture_regions` オブジェクト](#capture_regions-オブジェクト-810) 参照）。

#### `source` フィールドの値

crop モードでは `source: "manual"` のみが書き込まれる。`--region X,Y,W,H` はユーザーが指定したピクセル座標を正規化した値であることを示す。

> 将来的に自動検出の結果を write-back する経路が追加された場合は別の `source` 値が使われる予定だが、現時点では `"manual"` のみ。

#### 座標値の意味

`x`, `y`, `w`, `h` は `[0, 1]` の正規化座標。内部で mod-2 調整（`yuv420p` の codec 要求に合わせて `w` / `h` を偶数化）した後に正規化しているため、元の `--region` 指定ピクセル値から `w` / `h` が 1 ピクセル以下小さくなる場合がある。

### 部分実行 (--include) と既存 entry の保全

`allaganeye minimap --region X,Y,W,H --include 2` のように特定 match だけを再実行した場合、
既に書き込まれている他の match の entry は **match_index merge** によって保全される。
対象 match の entry のみ新しい region で上書きし、最後に `match_index` 昇順で sort して書き戻す。
malformed な entry (dict でない / `match_index` 欠落) も黙って捨てずにそのまま保全する (round-trip 哲学)。

### 書き込みパス別の挙動

| 経路 | 書き込み |
| --- | --- |
| `allaganeye minimap --region X,Y,W,H` (crop モード) | ✓ 必ず書く。決定的 preflight (filename 衝突検査 + output_dir 作成) が成功した後、エンコード開始**前**に atomic write-back するため、エンコード失敗時も座標は保持される |
| `allaganeye minimap --region ... --include N` (部分再実行) | ✓ 書く。対象外 match の既存 entry は match_index merge で保全される |
| `allaganeye minimap` (提案モード、`--region` 未指定) | ✗ 書かない (read-only、exit 4) |
| `allaganeye detect` / `allaganeye split` | ✗ 書かない (minimap の関知外) |
| `allaganeye split --from-metadata` | 元 metadata から **preserve**（元が欠落なら欠落） |

### GUI ConflictModal との関係

`minimap_regions` は CLI の atomic write-back により `metadata.json` を更新するため、GUI が同ファイルを開いたまま CLI を実行すると mtime 変化を検知して ConflictModal が表示される。これは既存の排他管理（`metadata.json` §排他管理、#514）が期待通りに機能していることを意味する。

## 将来の拡張 (Phase 1 スコープ外)

以下は派生 issue で追跡する (本 Phase 1 では実装せず、設計余地だけ確保)。

> **#373 互換性 (forward-compat 設計メモ)**: [#373](https://github.com/Idios/kobutachan-allaganeye/issues/373) では `dropped:{leading,trailing}` セクションを **metadata.json のトップレベル** (root) に将来追加する計画がある。これは `$defs/Match` への `post_match` フィールド追加 (#805 段階2) とは独立した別機構であり互換。`additionalProperties:false` は root / Match 双方で維持したまま、root へ `dropped` section を追加できる設計を確保している。#373 は未実装 — 本メモは将来実装時に本 spec の変更を壊さないことを確認した記録。

| 拡張 | 追跡 issue | 内容 |
| --- | --- | --- |
| ~~排他管理 (mtime 検知 / 同時編集警告)~~ | [#514](https://github.com/Idios/kobutachan-allaganeye/issues/514) (実装済み、上記 §排他管理 参照) | GUI load 時の mtime 記録、save 時の外部変更検知 UX |
| ~~schema_version フィールド~~ | [#515](https://github.com/Idios/kobutachan-allaganeye/issues/515) (実装済み、上記 §schema_version 参照) | 明示的な版数管理 + migration 基盤 |
| ~~`[元に戻す]` 機能~~ | [#516](https://github.com/Idios/kobutachan-allaganeye/issues/516) (Phase 2 で実装済み) | `metadata.original.json` → `metadata.json` 復元ボタン (Rust `restore_from_original` + `metadataStore.restore`) |
| ~~draft auto save~~ | [#517](https://github.com/Idios/kobutachan-allaganeye/issues/517) (実装済み、上記 §draft auto save 参照) | GUI 一時編集を `metadata.draft.json` に定期保存 (リロード耐性) |
| ~~`warnings: Warning[]` 構造化 (scaffold)~~ | [#518](https://github.com/Idios/kobutachan-allaganeye/issues/518) (scaffold 実装済み、上記 §warnings 参照。実際の warning code 追加は派生 PR) | legacy `note` の後継。`{code, message, severity}` 配列 |

## 関連 issue / doc

- [#463](https://github.com/Idios/kobutachan-allaganeye/issues/463) Phase 1 data 層 (本仕様の起票元)
- [#482](https://github.com/Idios/kobutachan-allaganeye/issues/482) Zustand 採用決定
- [docs/cli-spec.md](cli-spec.md) — CLI コマンド仕様
- [docs/design/README.md](design/README.md) — GUI 設計仕様
- [gui/src/types/metadata.ts](../gui/src/types/metadata.ts) — GUI 側 TS 型定義
- [gui/src/types/metadata.schema.ts](../gui/src/types/metadata.schema.ts) — zod schema
- [allaganeye/detection/metadata_writer.py](../allaganeye/detection/metadata_writer.py) — Python 側 read/write
