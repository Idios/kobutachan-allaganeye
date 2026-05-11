# Sample tauri-commands.md (fixture for extract-doc-hints.awk TDD)

## 他の section (本 awk は処理しない)

| col | val |
| --- | --- |
| `not.a.code` | should be ignored |

## AppError default hint mapping (`gui/src-tauri/src/error.rs::default_hint_for_code`)

> 本 table の文言は ... と完全一致させる (規約)。

| code | hint |
| --- | --- |
| `state.mtime_conflict` | metadata.json が他のプロセスで書き換えられました。「リロード」で最新を読み直すか、「上書き」で現在の編集を強制適用してください |
| `io.file_not_found` | ファイルが見つかりません。パスを確認してください |
| `io.would_block` / `io.timed_out` | I/O 処理がタイムアウト / ブロックされました。少し時間をおいて再試行してください |
| `subprocess.cancelled` | (hint なし: ユーザー操作によるキャンセルは UI 側で十分な情報を出す) |
| `internal.error` | (hint なし: 内部エラーで具体的アクションがない、message 側で logs 参照を案内) |

## 関連 (本 awk は処理しない)

- See spec ...
