# metadata.json 仕様

`metadata.json` は CLI (`allaganeye`) と GUI (L2a Tauri) の間の**唯一の契約**。#463 Phase 1 で確立。

## 概要

- **役割**: 検知結果 (match boundaries) とパラメータを構造化 JSON として保存。CLI `split --from-metadata` と GUI 双方が読み取り元とする。
- **生成者**: `allaganeye detect <video>` と `allaganeye split <video>` (legacy パス)
- **消費者**: `allaganeye split --from-metadata <metadata.json>` と GUI
- **更新者**: GUI の `[適用]` ボタン (加えて `allaganeye detect <video>` の再実行は上書き)

## スキーマ定義 (schema v1)

ルートは JSON オブジェクト。以下のフィールドを持つ。

| フィールド | 型 | 必須 | 意味 | 範囲 / 形式 |
|---|---|---|---|---|
| `schema_version` | string | 新規書き込みは ✓ / 読み込み時は欠落許容 | ペイロードのスキーマ版数 (#515) | 現行は `"1"`。欠落時は v1 として解釈 |
| `source` | string | ✓ | 元動画ファイルの絶対パス (OS 表記そのまま) | 非空 |
| `source_duration` | number | ✓ | 元動画の総秒数 | > 0 |
| `source_duration_display` | string | ✓ | 人間可読な長さ表示 | `HH:MM:SS` または `MM:SS` |
| `detected_at` | string | ✓ | 検知が実行された時刻 (UTC) | ISO 8601 (例: `2026-04-22T00:00:00Z`) |
| `detection_params` | object | ✓ | 検知に使われたパラメータ (後述) | (object) |
| `matches` | array | ✓ | 試合セグメント列 (0 件可) | |
| `gaps` | array | ✓ | 試合間の空白区間列 (0 件可) | |

### `detection_params` オブジェクト

| フィールド | 型 | 意味 |
|---|---|---|
| `sample_interval` | number | Pass 1 サンプリング間隔 (秒) |
| `blackout_threshold` | number | 暗転判定輝度閾値 (0-255) |
| `min_match_duration` | number | 最小試合長 (秒) |
| `min_blackout_duration` | number | 最小暗転長 (秒) |
| `no_audio` | boolean | 音声昇格無効化フラグ |
| `use_gpu` | number \| boolean \| null | GPU モード (null = auto 判定) |
| `workers` | number \| null | 並列ワーカー数 (null = auto) |

### `Match` オブジェクト (`matches[]`)

| フィールド | 型 | 必須 | 意味 |
|---|---|---|---|
| `index` | integer | ✓ | 1 始まりの順序番号 |
| `start_time` | number | ✓ | 試合開始秒 (>= 0) |
| `end_time` | number | ✓ | 試合終了秒 (>= start_time) |
| `start_display` | string | ✓ | 開始表示 (MM:SS / H:MM:SS) |
| `end_display` | string | ✓ | 終了表示 |
| `duration` | number | ✓ | 長さ (秒) |
| `duration_display` | string | ✓ | 長さ表示 (例: `15m15s`) |
| `type` | string | ✓ | `fl_match` または `unknown` |
| `output_file` | string | ✓ | 出力 MP4 ファイル名 (相対パス、metadata.json と同ディレクトリ想定) |

### `Gap` オブジェクト (`gaps[]`)

試合間の 5 分以上の空白 (5 分未満は含まれない、`min_gap=300.0` による)。

| フィールド | 型 | 必須 | 意味 |
|---|---|---|---|
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
- `matches[].output_file` は `match_NNN.mp4` のプレースホルダ (split 時に生成される実ファイル名)
- 既存 `metadata.json` は**上書き** (GUI の `metadata.original.json` バックアップには触らない)

### `allaganeye split <video>` (legacy)

- detect + split を一気通貫 (後方互換)
- probe → detect → split (ffmpeg -c copy) → `metadata.json` atomic write
- `matches[].output_file` は実際に書き出された MP4 のパス

### `allaganeye split --from-metadata <metadata.json>`

- `metadata.json` を source of truth として読む (detection は走らない)
- `source` フィールドで元動画を解決 (相対パスは `metadata.json` のディレクトリ起点)
- split → `metadata.json` を **`config.output_dir`** に**書き直し**
- 書き直し時に未知フィールド (legacy `note` 等) は**落ちる**。GUI で保持したい情報は GUI 側 state に保つ

## 書き込み方針

- **原子的書き込み**: temp ファイル (`.tmp` サフィックス) に書いてから `os.replace` で対象にリネーム。中断時の破損なし
- **エンコーディング**: UTF-8 / BOM なし / `ensure_ascii=false` / `indent=2`
- **改行**: LF (JSON 仕様上問題ないが、ツール側は特に気にしない)
- **ファイル名**: `metadata.json` 固定 (GUI 編集時のバックアップは `metadata.original.json`)

## GUI 編集契約

GUI は以下のフィールドを in-memory で編集し、`[適用]` 時に `metadata.json` へ書き戻す。

### 編集可フィールド

| GUI の一時フィールド | 書き戻し時の反映先 |
|---|---|
| `Match.edited.start_time` | `Match.start_time` に上書き (`edited` 自体は落とす) |
| `Match.edited.end_time` | `Match.end_time` に上書き |
| `Match.type_override: fl_match` \| `unknown` | `Match.type` に上書き |
| `Match.type_override: skip` | **書き戻さない** (export 時に除外する GUI ローカル情報) |
| `Match.name` | **書き戻さない** (GUI 表示専用、metadata.json には持たない) |

### 読み取り専用

以下は GUI では絶対に書き戻さない (CLI の観測記録として保全):

- `source`, `source_duration`, `source_duration_display`
- `detected_at`, `detection_params`
- `gaps` (CLI が計算、GUI は表示のみ)

### 同一性保証

書き戻し後の `matches[]` は以下の形: GUI 編集フィールド (`edited` / `type_override` / `name`) は完全に除去され、スキーマ v1 の純粋形になる。

```ts
{ index, start_time, end_time, start_display, end_display,
  duration, duration_display, type, output_file }
```

## `metadata.original.json` policy

GUI による初回 `[適用]` 時のみ作成。

| トリガー | 動作 |
|---|---|
| GUI 初回 `[適用]` | `metadata.json` が存在し `metadata.original.json` が存在しない場合、前者を後者にコピーしてから書き戻す |
| GUI 2 回目以降 `[適用]` | `metadata.original.json` には触らない (初回時の純粋な detect 結果を保持) |
| `allaganeye detect` 再実行 | `metadata.json` を上書き、`metadata.original.json` には触らない (注: この場合 `.original` は古い状態のまま残り、ユーザーが手動管理) |
| GUI `[元に戻す]` (#516 完了、Phase 2 で実装) | `metadata.original.json` の内容で `metadata.json` を atomic 上書き。`.original` は読み取りのみで保持 |

## ユーザー手動編集シナリオ

| シナリオ | 期待動作 |
|---|---|
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
|---|---|---|
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
- **source 不一致チェック**: draft の `source` が現在 load した metadata の `source` と異なる場合、stale draft として自動削除 (modal は出さない)。比較は Windows 前提で separator (`\\` ↔ `/`) と大文字小文字を正規化した上で行う (`normalizeSourcePath`)
- **source 以外のドリフト** (matches 数・detection_params・source_duration 等): 検知対象外。source が一致する限り draft は有効と見なす。metadata.json を CLI で再生成した場合の排他管理は別 issue (§将来の拡張「排他管理 (mtime 検知 / 同時編集警告)」参照) で対応予定
- **apply 成功後**: `metadataStore.apply` が成功すると `clearDraft` を呼び、`metadata.draft.json` をディスクから削除
- **Rust commands**: `save_draft(path, draft)` / `load_draft(path) -> Option<Value>` / `clear_draft(path)` — すべて atomic、clear は no-op-when-missing

### ユーザー選択肢 (DraftRestoreModal)

| ボタン | 動作 |
|---|---|
| 復元 | `pendingDraft` を `metadata` に適用し `dirty=true`。ディスクには触らない (ユーザーが [適用] で永続化) |
| 破棄 | `clearDraft()` を呼んで `metadata.draft.json` を削除し、`pendingDraft=null` |

draft の zod parse に失敗した場合は error-only modal を出し「破棄」のみ提示する。

## 将来の拡張 (Phase 1 スコープ外)

以下は派生 issue で追跡する (本 Phase 1 では実装せず、設計余地だけ確保):

| 拡張 | 追跡 issue | 内容 |
|---|---|---|
| ~~排他管理 (mtime 検知 / 同時編集警告)~~ | [#514](https://github.com/Idios/kobutachan-allaganeye/issues/514) (実装済み、上記 §排他管理 参照) | GUI load 時の mtime 記録、save 時の外部変更検知 UX |
| ~~schema_version フィールド~~ | [#515](https://github.com/Idios/kobutachan-allaganeye/issues/515) (実装済み、上記 §schema_version 参照) | 明示的な版数管理 + migration 基盤 |
| ~~`[元に戻す]` 機能~~ | [#516](https://github.com/Idios/kobutachan-allaganeye/issues/516) (Phase 2 で実装済み) | `metadata.original.json` → `metadata.json` 復元ボタン (Rust `restore_from_original` + `metadataStore.restore`) |
| ~~draft auto save~~ | [#517](https://github.com/Idios/kobutachan-allaganeye/issues/517) (実装済み、上記 §draft auto save 参照) | GUI 一時編集を `metadata.draft.json` に定期保存 (リロード耐性) |
| `warnings: Warning[]` 構造化 | (新規起票予定) | legacy `note` の後継。`{code, message, severity}` 配列 |

## 関連 issue / doc

- [#463](https://github.com/Idios/kobutachan-allaganeye/issues/463) Phase 1 data 層 (本仕様の起票元)
- [#482](https://github.com/Idios/kobutachan-allaganeye/issues/482) Zustand 採用決定
- [docs/cli-spec.md](cli-spec.md) — CLI コマンド仕様
- [docs/design/README.md](design/README.md) — GUI 設計仕様
- [gui/src/types/metadata.ts](../gui/src/types/metadata.ts) — GUI 側 TS 型定義
- [gui/src/types/metadata.schema.ts](../gui/src/types/metadata.schema.ts) — zod schema
- [allaganeye/detection/metadata_writer.py](../allaganeye/detection/metadata_writer.py) — Python 側 read/write
