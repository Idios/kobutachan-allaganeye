// Minimal fixture for extract-rust-hints.awk TDD.
// Includes: single-line hint, multi-line hint, or-pattern, None entry, catch-all.

fn default_hint_for_code(code: &str) -> Option<&'static str> {
    match code {
        "state.mtime_conflict" => Some(
            "metadata.json が他のプロセスで書き換えられました。「リロード」で最新を読み直すか、「上書き」で現在の編集を強制適用してください"
        ),
        "io.file_not_found" => Some(
            "ファイルが見つかりません。パスを確認してください"
        ),
        "io.would_block" | "io.timed_out" => Some(
            "I/O 処理がタイムアウト / ブロックされました。少し時間をおいて再試行してください"
        ),
        "subprocess.cancelled" => None,
        "internal.error" => None,
        _ => None,
    }
}
