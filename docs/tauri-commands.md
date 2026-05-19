# Tauri Commands リファレンス

`gui/src-tauri/src/lib.rs` 内の全 `#[tauri::command]` の master 一覧。frontend (TypeScript) と backend (Rust) の error contract と invoke 経路を確定する doc。

## エラー型 (migration 完了)

- 戻り値型: **全 26 command が `Result<T, AppError>` または `bool` / 値直接 (`is_process_running` / `probe_environment_info`) を返す** (PR [#665](https://github.com/Idios/kobutachan-allaganeye/pull/665) で legacy `Result<T, String>` から完全 migration 済、PR #669 で `read_error_log_tail` / `probe_environment_info` 追加、PR #787 で `enumerate_h264_encoders` / `start_export` 追加・`export_match` / `select_h264_encoder_for_export` 削除)
- `AppError` 構造体 (`gui/src-tauri/src/error.rs`、PR [#661](https://github.com/Idios/kobutachan-allaganeye/pull/661) Refs [#614](https://github.com/Idios/kobutachan-allaganeye/issues/614) で導入) のフィールド: `code: String` (domain-specific identifier、例 `io.file_not_found`) / `message: String` / `hint: Option<String>` / `stacktrace: Option<String>`
- `From<std::io::Error>` / `From<serde_json::Error>` / `From<String>` / `From<&str>` impl があり、`?` 演算子で自動変換される (PR #665 で追加)。`std::io::Error` は `ErrorKind` から domain code を派生 (例 `NotFound` → `io.file_not_found`)
- frontend 側 narrowing: `gui/src/lib/appError.ts` の `toErrorState(e)` / `appErrorCodeIs(e, code)` / `isAppError(e)` ヘルパーを使う。Tauri は `AppError` を JSON object として frontend に渡し、invoke 失敗時 Promise.reject 値が AppError instance になる
- 本 doc の「想定エラーケース / AppError code」列は実装と整合する domain.error_kind 命名 (例: `io.file_not_found`、`parse.json_invalid`、`state.mtime_conflict`)

## 分類タグ

| タグ | 説明 |
| --- | --- |
| `pure` | 入力から決定的に出力を計算、副作用なし |
| `I/O` | ファイル読み書き / metadata 取得 |
| `subprocess` | ffmpeg / ffprobe / python CLI / explorer 等の外部プロセス起動 |
| `state-mutating` | in-memory registry 更新 / app exit / panic 誘発 等の副作用 |

複数該当する場合は `+` で結合 (例: `subprocess + state-mutating`)。

## 全 command 一覧

| # | command | params | Result type | 分類 | 想定エラーケース | AppError code |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `load_metadata` | `path: String` | `Result<Value, AppError>` | I/O | (a) ファイル不在、(b) JSON parse 失敗、(c) 読み取り権限なし、(d) JSON root が object でない | (a) `io.file_not_found`、(b) `parse.json_invalid`、(c) `io.permission_denied`、(d) `parse.schema_invalid` |
| 2 | `get_metadata_mtime` | `path: String` | `Result<Option<u64>, AppError>` | I/O | (a) ファイル不在 (= None で返却)、(b) 読み取り権限なし | (b) `io.permission_denied` |
| 3 | `apply_changes` | `path: String, metadata: Value, expected_mtime_ms: Option<u64>` | `Result<u64, AppError>` | I/O + state-mutating | (a) mtime conflict (外部書き換え検出)、(b) backup 作成失敗、(c) atomic write 失敗、(d) JSON serialize 失敗、(e) post-apply mtime 取得失敗 (extreme case、書き込み直後にファイルが消失/権限変更等) | (a) `state.mtime_conflict`、(b) `io.backup_failed`、(c) `io.write_failed`、(d) `parse.json_serialize_failed`、(e) `io.read_failed` |
| 4 | `save_draft` | `path: String, draft: Value` | `Result<(), AppError>` | I/O + state-mutating | (a) sibling `.draft.json` への書き込み失敗 | (a) `io.write_failed` |
| 5 | `load_draft` | `path: String` | `Result<Option<Value>, AppError>` | I/O | (a) draft ファイル不在 (= None で返却)、(b) JSON parse 失敗 | (b) `parse.json_invalid` |
| 6 | `clear_draft` | `path: String` | `Result<(), AppError>` | I/O + state-mutating | (a) draft 削除失敗 (権限等) | (a) `io.delete_failed` |
| 7 | `restore_from_original` | `path: String` | `Result<(), AppError>` | I/O + state-mutating | (a) backup 不在、(b) backup → original copy 失敗 | (a) `io.file_not_found`、(b) `io.copy_failed` |
| 8 | `check_backup_exists` | `path: String` | `Result<bool, AppError>` | I/O | (常に bool で返却、エラーケースほぼなし) | - |
| 9 | `read_recent` | (なし) | `Result<Vec<RecentEntry>, AppError>` | I/O | (a) `recent.json` parse 失敗、(b) 読み取り失敗 | (a) `parse.json_invalid`、(b) `io.read_failed` |
| 10 | `add_recent` | `path: String` | `Result<Vec<RecentEntry>, AppError>` | I/O + state-mutating | (a) `recent.json` 書き込み失敗、(b) パス validate 失敗 | (a) `io.write_failed`、(b) `validation.path_invalid` |
| 11 | `clear_recent` | (なし) | `Result<(), AppError>` | I/O + state-mutating | (a) `recent.json` 書き込み失敗 | (a) `io.write_failed` |
| 12 | `register_video` | `path: String` | `Result<RegisteredVideo, AppError>` | state-mutating | (a) 動画ファイル不在、(b) directory pass、(c) 読み取り権限なし | (a) `io.file_not_found`、(b) `validation.not_a_file`、(c) `io.permission_denied` |
| 13 | `probe_video` | `path: String` | `Result<VideoProbeInfo, AppError>` | subprocess | (a) ffprobe 不在、(b) ffprobe 起動失敗、(c) ffprobe 出力 parse 失敗 | (a) `ffmpeg.not_found`、(b) `subprocess.spawn_failed`、(c) `parse.ffprobe_output_invalid` |
| 14 | `generate_match_thumbnails` | `video_path: String, match_index: u32, boundary_t_seconds: f64, window_seconds: f64, count: u32` | `Result<Vec<ThumbnailEntry>, AppError>` | subprocess + I/O | (a) ffmpeg 不在、(b) seek 範囲外、(c) thumbnail 書き込み失敗 | (a) `ffmpeg.not_found`、(b) `validation.range_invalid`、(c) `io.write_failed` |
| 15 | `is_process_running` | (なし) | `bool` | pure | (返り値は bool 直接、エラーなし) | - |
| 16 | `kill_tracked_processes` | (なし) | `Result<u32, AppError>` | subprocess + state-mutating | (a) kill コマンド失敗 | (a) `process.kill_failed` |
| 17 | `force_exit_app` | `app: tauri::AppHandle` | (返り値なし) | state-mutating | (即時 app exit、エラーケースなし) | - |
| 18 | `open_folder_in_explorer` | `path: String` | `Result<(), AppError>` | subprocess | (a) フォルダ不在、(b) explorer 起動失敗 | (a) `io.file_not_found`、(b) `subprocess.spawn_failed` |
| 19 | `enumerate_h264_encoders` | `req: { vendors: string[], preference: string[], gpuModels: string[] }` (camelCase) | `Result<Vec<EncoderSlotJson>, AppError>` | subprocess | (a) python CLI 不在、(b) encoder-slots 異常終了、(c) JSON parse 失敗 | (a) `python.not_found`、(b) `subprocess.exit_failed`、(c) `parse.json_invalid` |
| 20 | `start_export` | `req: { metadataJson: object, outputDir: string, codec: "copy"\|"h264", namePattern: string, excludedIndexes: number[] }` | `Result<ExportSummary, AppError>` | subprocess + I/O | (a) python CLI 不在、(b) export 異常終了 (per-match error は `export-progress` event 経由)、(c) output dir 書き込み失敗 | (a) `python.not_found`、(b) `subprocess.exit_failed`、(c) `io.write_failed` |
| 21 | `start_detect` | `app: AppHandle, video_path: String, output_dir: String, params: DetectParams` | `Result<DetectResult, AppError>` | subprocess | (a) python CLI 不在、(b) python -m fallback 失敗、(c) detect 実行中エラー | (a) `python.not_found`、(b) `subprocess.spawn_failed`、(c) `subprocess.exit_failed` |
| 22 | `get_log_dir` | (なし) | `Result<String, AppError>` | pure | (a) install_dir 取得失敗 (極端ケース) | (a) `path.install_dir_unresolved` |
| 23 | `read_error_log_tail` | `line_count: usize` | `Result<String, AppError>` | I/O | (a) install_dir 取得失敗、(b) log file の open / read 失敗 | (a) `path.install_dir_unresolved`、(b) `io.read_failed` |
| 24 | `probe_environment_info` | (なし) | `EnvironmentProbe` | pure | (常に struct で返却、エラーケースなし — 個別 field は `None` で degrade) | - |
| 25 | `extract_brightness_window` | `video_path: String, t_start: f64, t_end: f64, fps: f64` | `Result<BrightnessWindow, AppError>` | subprocess | (a) ffmpeg 不在/起動失敗、(b) ffmpeg 異常終了 | (a) `subprocess.spawn_failed`、(b) `subprocess.exit_failed` |
| 26 | `dev_force_panic` | (なし) | `Result<(), AppError>` | state-mutating | **意図的 panic** (`#[cfg(debug_assertions)]` 限定、PR #661 E2E 検証用) | - (panic で異常終了が期待動作) |

## 補足

- すべての command は async / sync 問わず Tauri runtime で execute される
- **frontend (TypeScript) 側の error narrowing**: `gui/src/lib/appError.ts` の `toErrorState(e)` / `appErrorCodeIs(e, code)` / `isAppError(e)` ヘルパーを使う。Tauri が `AppError` を JSON object として serialize するため、invoke 失敗時の Promise.reject 値は `{ code, message, hint?, stacktrace? }` の object になる
- **`AppError` 構造**: `code: String` (domain-specific identifier) / `message: String` / `hint: Option<String>` / `stacktrace: Option<String>`。enum ではなく struct で、code 値は domain.error_kind 形式の自由文字列 (例: `io.file_not_found`、`parse.json_invalid`、`state.mtime_conflict`)
- **`?` 演算子の自動変換**: Rust 側 `error.rs` に `From<std::io::Error>` / `From<serde_json::Error>` / `From<String>` / `From<&str>` impl があり、各 helper の error を `?` で AppError に variant-aware に自動変換できる。例: `std::io::Error::NotFound` → `AppError { code: "io.file_not_found" }`

frontend narrowing の使用例:

```ts
import { appErrorCodeIs, toErrorState } from '../lib/appError';

try {
  await invoke('apply_changes', { path, metadata, expectedMtimeMs });
} catch (e) {
  if (appErrorCodeIs(e, 'state.mtime_conflict')) {
    // 競合専用の UI 分岐
  } else {
    showError(toErrorState(e).message);
  }
}
```

## #669 -- ErrorModal Issue 本文クリップボード関連 command

PR #669 で追加した 2 command (`read_error_log_tail` / `probe_environment_info`) は ErrorModal の `[Issue 本文をコピー]` button が `bug_report.yml` form 用 Markdown 本文を組み立てるために使う。両方 best-effort (失敗してもコピー処理自体は継続、対応 section が `formatSystemInfo` の sentinel `(unknown)` / `(none detected)` / `(no environment info)` または log section の省略 (空文字列) で graceful degrade する)。

> **設計上の経緯**: 初期実装では GitHub Issue Forms (`.yml`) の URL query string pre-fill (`?actual=...&environment=...&log_file_attachment=...`) を狙ったが、PR #669 の実機検証で form が空のまま開く現象を確認。**真の原因は `bug_report.yml` が repository default branch (`main`) に不在で template 自体がロードされておらず、`?template=bug_report.yml` URL が free-form ページに silently fallback していた点** ([#728](https://github.com/Idios/kobutachan-allaganeye/issues/728) で追跡)。GitHub Issue Forms が custom textarea field の URL pre-fill を honor するかどうかは template が rendered な状態で再検証が必要 (公式仕様の解説については GitHub Community discussion <https://github.com/orgs/community/discussions/22335> を参照)。Plan B (clipboard 経由のコピー & ペースト方式、`navigator.clipboard.writeText`) は template 状態に依存せず動作する robust 設計のため、#728 の解決を待たずに採用。生成された Markdown 本文を user が form の `実際の動作` textarea にそのまま貼り付ける運用。

### `read_error_log_tail`

- **用途**: clipboard body の「ログファイル (末尾抜粋)」section を埋めるため、`<install_dir>/logs/error-YYYYMMDD.log` の末尾 N 行を取得
- **Fallback 規則**:
  - 当日 (YYYYMMDD) の log file が存在しない / 空 → 前日 log にフォールバック (1 日のみ)
  - 前日 log も存在しない / 空 → 空文字列 (`""`) を返す (エラーでなく、frontend 側で「ログ section を省略」)
  - `line_count == 0` → 空文字列を即返す (loop 暴走防止)
- **frontend caller**: `gui/src/components/ErrorModal.tsx::handleCopyIssueBody` (button click 時)

### `probe_environment_info`

- **用途**: clipboard body の「環境情報」section を埋めるため、OS / CPU / Memory / Disk 情報を `sysinfo` crate 経由で probe
- **戻り値**: `EnvironmentProbe { allaganeye_version, os_name, cpu_info, memory_total_gb, disk_free_gb, disk_total_gb, disk_drive }` (snake_case で frontend 側 `gui/src/lib/systemInfo.ts` の type と一致)
- **設計理由**: 既存 `metadata.system_info` (Python `_build_system_info` 由来) は GPU 3 field のみ書く。bug_report.yml `environment` placeholder の format (`allaganeye 0.2.0 (Windows 11) / CPU: ... / Memory: ...`) を満たすため Tauri 側で live probe する (PR #669 の plan 修正、Option B 採用)
- **frontend 側 helper**: `gui/src/lib/systemInfo.ts` `formatSystemInfo(probe, metadata.system_info)` で probe + GPU vendor list を結合し environment 文字列を組み立てる
- **Disk metrics**: install dir (`<exe-parent>`) を含む disk を `mount_point` の longest prefix で選択。マッチしない場合は disk_* fields 全て `None`

## `start_detect` stdout schema と parse 失敗時の挙動 (#648)

`start_detect` が spawn する `allaganeye detect --progress-format json` の stdout は **1 行 1 JSON object の stream** (UTF-8、LF separator)。GUI 側は `parse_detect_progress_line` で 1 行ずつ deserialize する。

**許容パターン (silent skip)**:

- 空行 (改行のみの LF flush 等)
- 空白のみ行

**想定外パターン (warn 出力)**:

- malformed JSON (debug print 混入、schema 不整合)
- 上記の場合、`parse_detect_progress_line` は `eprintln!` で
  `[parse_detect_progress_line] malformed JSON (len=N): "<escaped truncated line>"`
  形式の warn を stderr に出力する。先頭 64 文字で truncate、制御文字 (TAB/LF/CR 以外) は `\xNN` escape

**観察可能範囲**:

- **dev build** (`cargo tauri dev`): `windows_subsystem` が default = `console` のため、`eprintln!` は terminal stderr に届く
- **release build** (`cargo tauri build`): `windows_subsystem = "windows"` で console を切り離しているため、`eprintln!` は **失われる** (Windows OS が stderr を dev null 相当に向ける)。release で観察可能にしたい場合は `tauri-plugin-log` 導入 (post-Lane I-B 別 issue) で file output 化する

**設計選択 (#648 spec)**: `phase=error` event 発火による DetectingScreen の error UI 接続は採用していない (UX 過剰、roadmap で却下)。silent skip → warn 化のみで UX に影響なし。

## CI による doc 整合性検査

`.github/workflows/ci.yml` の `doc-tauri-commands-drift` job が `gui/src-tauri/src/lib.rs` 内の `#[tauri::command]` 数と本 doc の table 行数を比較し、不一致時に CI を fail させる (本 doc 漏れ防止、issue [#619](https://github.com/Idios/kobutachan-allaganeye/issues/619) 受け入れ条件 2)。command を追加・削除した場合は本 doc の table 行も同時に更新すること。

## AppError default hint mapping (`gui/src-tauri/src/error.rs::default_hint_for_code`)

> 本 table の文言は `gui/src-tauri/src/error.rs` の `default_hint_for_code()` と
> 完全一致させる (CI integrity check は `.github/scripts/check-error-hint-drift.sh`
> および `doc-error-hint-drift` job で自動保証されている (#692)。文言変更時は両方を
> 同 PR で更新する規約)。

| code | hint |
| --- | --- |
| `state.mtime_conflict` | metadata.json が他のプロセスで書き換えられました。「リロード」で最新を読み直すか、「上書き」で現在の編集を強制適用してください |
| `io.file_not_found` | ファイルが見つかりません。パスを確認するか、allaganeye split を再実行してください |
| `io.read_failed` | ファイルの読み込みに失敗しました。ディスク状況・ファイルロック状態を確認してください |
| `io.write_failed` | ファイルの書き込みに失敗しました。空き容量と書き込み権限 (Portable ZIP の install dir が user-writable か) を確認してください |
| `io.delete_failed` | ファイル / フォルダの削除に失敗しました。他プロセスでロックされていないか確認してください |
| `io.backup_failed` | バックアップファイルの作成に失敗しました。allaganeye 出力フォルダの空き容量と書き込み権限を確認してください |
| `io.permission_denied` | ファイルへのアクセス権限がありません。Portable ZIP install dir が user-writable な場所か、ファイル / フォルダが読み取り専用でないか確認してください |
| `io.already_exists` | ファイルが既に存在します。出力先を変更するか既存ファイルを削除してください |
| `io.would_block` / `io.timed_out` | I/O 処理がタイムアウト / ブロックされました。少し時間をおいて再試行してください |
| `io.error` | I/O エラーが発生しました。詳細は logs フォルダを確認してください |
| `parse.json_invalid` | JSON ファイルが破損しています。バックアップ (.bak) からの復元か allaganeye split のやり直しを検討してください |
| `parse.json_serialize_failed` | JSON 書き出しに失敗しました。同梱 issue テンプレートでバグ報告してください |
| `parse.schema_invalid` | metadata.json の構造が期待形式と異なります。allaganeye のバージョンと metadata 生成バージョンが一致しているか確認してください |
| `parse.ffprobe_output_invalid` | ffprobe の出力を解釈できませんでした。ffmpeg / ffprobe を最新の BtbN LGPL ビルドに更新してください |
| `subprocess.spawn_failed` | 外部プロセスの起動に失敗しました。ffmpeg / Python / 同梱 runtime が壊れていないか確認してください |
| `subprocess.exit_failed` | 外部プロセスが異常終了しました。logs フォルダの最新ログから詳細を確認してください |
| `subprocess.cancelled` | (hint なし: ユーザー操作によるキャンセルは UI 側で十分な情報を出す) |
| `validation.path_invalid` | 入力されたパスが不正です。ファイル名と拡張子を確認してください (対応: mp4 / mkv / mov / m4v) |
| `validation.not_a_file` | 指定されたパスはファイルではありません (フォルダや symlink ではなく動画ファイルを選択してください) |
| `validation.range_invalid` | 入力された数値が許容範囲外です。フォーム下のヒント表示を確認してください |
| `path.install_dir_unresolved` | Portable ZIP の install dir を特定できませんでした。allaganeye-gui.exe を ZIP 展開後の元のフォルダ構成のまま起動してください |
| `platform.unsupported` | 本機能は現在の OS では未対応です。Windows での起動が必要です |
| `internal.error` | (hint なし: 内部エラーで具体的アクションがない、message 側で logs 参照を案内) |

## 関連

- 派生元: [#619](https://github.com/Idios/kobutachan-allaganeye/issues/619) 本 doc 新設 + 全 23 command の AppError migration (PR #665)
- AppError 型定義: `gui/src-tauri/src/error.rs` (PR [#661](https://github.com/Idios/kobutachan-allaganeye/pull/661), Refs [#614](https://github.com/Idios/kobutachan-allaganeye/issues/614))
- frontend narrowing helper: `gui/src/lib/appError.ts` (PR #665 で新設)
- frontend invoke の主な利用箇所: `gui/src/state/metadataStore.ts` / `gui/src/state/recentStore.ts` / `gui/src/lib/globalErrorListener.ts`
- 関連実装 PR: [#465](https://github.com/Idios/kobutachan-allaganeye/issues/465) (`register_video` / `probe_video` / `generate_match_thumbnails`) / [#523](https://github.com/Idios/kobutachan-allaganeye/issues/523) (`kill_tracked_processes`) / [#569](https://github.com/Idios/kobutachan-allaganeye/issues/569) (`start_detect`) / [#571](https://github.com/Idios/kobutachan-allaganeye/issues/571) (`read_recent` / `add_recent` / `clear_recent`) / [#787](https://github.com/Idios/kobutachan-allaganeye/pull/787) (`enumerate_h264_encoders` / `start_export`、旧 `export_match` / `select_h264_encoder_for_export` 削除)
