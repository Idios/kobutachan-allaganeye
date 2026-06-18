use std::fmt;

use serde::Serialize;
use tauri::Emitter;

use crate::logging;

#[derive(Debug, Clone, Serialize)]
pub struct AppError {
    pub code: String,
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub hint: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub stacktrace: Option<String>,
}

impl AppError {
    pub fn new(code: impl Into<String>, message: impl Into<String>) -> Self {
        Self {
            code: code.into(),
            message: message.into(),
            hint: None,
            stacktrace: None,
        }
    }

    /// `hint` フィールドを明示的に設定する builder (per-call-site override 用)。
    ///
    /// production code は `with_default_hint()` 経由で code 別 default hint を
    /// 設定する (#663 で lib.rs 全 80+ site に適用済)。`with_hint` 自体は test
    /// (`serialize_app_error_roundtrips` /
    /// `with_default_hint_does_not_overwrite_explicit_hint`) と、将来 Approach C
    /// (per-call-site hint override) への hybrid 移行用 API として残す。
    /// `#[allow(dead_code)]` は production 非経由 (= test 専用 API) を示し、
    /// `cargo build` で dead-code warning を出さないためのもの。
    #[allow(dead_code)]
    pub fn with_hint(mut self, hint: impl Into<String>) -> Self {
        self.hint = Some(hint.into());
        self
    }

    #[allow(dead_code)]
    pub fn with_stacktrace(mut self, stacktrace: impl Into<String>) -> Self {
        self.stacktrace = Some(stacktrace.into());
        self
    }

    /// code に対する default hint を attach する。すでに hint が設定されている場合は
    /// 上書きせず保持する (call site で `.with_hint("...")` を先に書いた場合の override
    /// が効く設計、将来 Approach C への hybrid 移行時に必要)。
    pub fn with_default_hint(mut self) -> Self {
        if self.hint.is_some() {
            return self;
        }
        self.hint = default_hint_for_code(&self.code).map(String::from);
        self
    }

}

impl fmt::Display for AppError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "[{}] {}", self.code, self.message)
    }
}

impl std::error::Error for AppError {}

/// `?` 演算子で `std::io::Error` を AppError に自動変換する。code は
/// `ErrorKind` から派生 (`NotFound` → `io.file_not_found`、`PermissionDenied`
/// → `io.permission_denied` 等)、message は `e.to_string()`。
/// call site で context-specific code に上書きしたい場合は
/// `.map_err(|e| AppError::new("io.<specific_kind>", e.to_string()))`
/// (例: `io.read_failed`、`io.write_failed` 等の domain.error_kind 形式) を使う。
impl From<std::io::Error> for AppError {
    fn from(e: std::io::Error) -> Self {
        let code = match e.kind() {
            std::io::ErrorKind::NotFound => "io.file_not_found",
            std::io::ErrorKind::PermissionDenied => "io.permission_denied",
            std::io::ErrorKind::AlreadyExists => "io.already_exists",
            std::io::ErrorKind::WouldBlock => "io.would_block",
            std::io::ErrorKind::TimedOut => "io.timed_out",
            _ => "io.error",
        };
        AppError::new(code, e.to_string()).with_default_hint()
    }
}

/// `?` 演算子で `serde_json::Error` を AppError に自動変換する。code は
/// `parse.json_invalid` 固定。message は `e.to_string()` で line/column 情報を含む。
impl From<serde_json::Error> for AppError {
    fn from(e: serde_json::Error) -> Self {
        AppError::new("parse.json_invalid", e.to_string()).with_default_hint()
    }
}

/// `?` 演算子で `String` error を AppError として propagate するための impl。
/// 主に `Result<_, String>` を返す内部 helper (例 `untrack_child` 相当の
/// 内部ヘルパー) を `Result<_, AppError>` を返す Tauri command 内で `?` 経由で
/// 呼び出すケースで使われる。code は `internal.error` 固定。新規コードでは
/// call site で `AppError::new("domain.error_kind", message)` を構築するのが
/// 望ましい。
///
/// `.with_default_hint()` chain は future-proof のため (`From<io::Error>` /
/// `From<serde_json::Error>` と同 contract で integrity を保つ。現状
/// `internal.error` は hint None だが、将来 hint を追加した場合の silent
/// bypass を防ぐ)。lib.rs 全 80+ site の hint chain 規律と整合 (#663)。
impl From<String> for AppError {
    fn from(message: String) -> Self {
        AppError::new("internal.error", message).with_default_hint()
    }
}

/// AppError code に対する日本語 default hint を返す。未登録 code は None。
/// 25 codes (or-pattern `io.would_block | io.timed_out` を 2 codes に展開後、23 hint
/// + 2 None = 25)。現在の lib.rs inventory: io.* / parse.* / state.* / subprocess.* /
/// validation.* / path.* / platform.* / internal.*。
/// 文言は `docs/tauri-commands.md` の AppError default hint mapping table と一致させる
/// (本 fn が source of truth、docs は mirror、`.github/scripts/check-error-hint-drift.sh`
/// + ci.yml `doc-error-hint-drift` job で drift を CI で防ぐ #692)。
fn default_hint_for_code(code: &str) -> Option<&'static str> {
    match code {
        // state
        "state.mtime_conflict" => Some(
            "metadata.json が他のプロセスで書き換えられました。「リロード」で最新を読み直すか、「上書き」で現在の編集を強制適用してください"
        ),
        // io (manual call site)
        "io.file_not_found" => Some(
            "ファイルが見つかりません。パスを確認するか、allaganeye split を再実行してください"
        ),
        "io.read_failed" => Some(
            "ファイルの読み込みに失敗しました。ディスク状況・ファイルロック状態を確認してください"
        ),
        "io.write_failed" => Some(
            "ファイルの書き込みに失敗しました。空き容量と書き込み権限 (Portable ZIP の install dir が user-writable か) を確認してください"
        ),
        "io.delete_failed" => Some(
            "ファイル / フォルダの削除に失敗しました。他プロセスでロックされていないか確認してください"
        ),
        "io.backup_failed" => Some(
            "バックアップファイルの作成に失敗しました。allaganeye 出力フォルダの空き容量と書き込み権限を確認してください"
        ),
        // io (auto from std::io::Error::ErrorKind via From impl)
        "io.permission_denied" => Some(
            "ファイルへのアクセス権限がありません。Portable ZIP install dir が user-writable な場所か、ファイル / フォルダが読み取り専用でないか確認してください"
        ),
        "io.already_exists" => Some(
            "ファイルが既に存在します。出力先を変更するか既存ファイルを削除してください"
        ),
        "io.would_block" | "io.timed_out" => Some(
            "I/O 処理がタイムアウト / ブロックされました。少し時間をおいて再試行してください"
        ),
        "io.error" => Some(
            "I/O エラーが発生しました。詳細は logs フォルダを確認してください"
        ),
        // parse
        "parse.json_invalid" => Some(
            "JSON ファイルが破損しています。バックアップ (.bak) からの復元か allaganeye split のやり直しを検討してください"
        ),
        "parse.json_serialize_failed" => Some(
            "JSON 書き出しに失敗しました。同梱 issue テンプレートでバグ報告してください"
        ),
        "parse.schema_invalid" => Some(
            "metadata.json の構造が期待形式と異なります。allaganeye のバージョンと metadata 生成バージョンが一致しているか確認してください"
        ),
        "parse.ffprobe_output_invalid" => Some(
            "ffprobe の出力を解釈できませんでした。ffmpeg / ffprobe を最新の BtbN LGPL ビルドに更新してください"
        ),
        // subprocess
        "subprocess.spawn_failed" => Some(
            "外部プロセスの起動に失敗しました。ffmpeg / Python / 同梱 runtime が壊れていないか確認してください"
        ),
        "subprocess.exit_failed" => Some(
            "外部プロセスが異常終了しました。logs フォルダの最新ログから詳細を確認してください"
        ),
        "subprocess.cancelled" => None, // ユーザー操作によるキャンセルは hint 不要 (UI 側で「キャンセルされました」を表示で十分)
        // validation
        "validation.boundary_invalid" => Some(
            "試合の終了 (OUT) が開始 (IN) 以前になっています。終了が開始より後になるよう境界を調整してください"
        ),
        "validation.path_invalid" => Some(
            "入力されたパスが不正です。ファイル名と拡張子を確認してください (対応: mp4 / mkv / mov / m4v)"
        ),
        "validation.not_a_file" => Some(
            "指定されたパスはファイルではありません (フォルダや symlink ではなく動画ファイルを選択してください)"
        ),
        "validation.range_invalid" => Some(
            "入力された数値が許容範囲外です。フォーム下のヒント表示を確認してください"
        ),
        // path / platform / internal
        "path.install_dir_unresolved" => Some(
            "Portable ZIP の install dir を特定できませんでした。allaganeye-gui.exe を ZIP 展開後の元のフォルダ構成のまま起動してください"
        ),
        "platform.unsupported" => Some(
            "本機能は現在の OS では未対応です。Windows での起動が必要です"
        ),
        "internal.error" => None, // 内部エラーで具体的アクションがない (詳細は logs 参照を message 側で示す方針)
        _ => None,
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct PanicPayload {
    pub message: String,
    pub timestamp: String,
    pub location: String,
}

/// Install a global panic hook. Writes panic info to the install-dir log file
/// (`<install_dir>/logs/error-YYYYMMDD.log`) with a `PANIC_MARKER` token, then
/// best-effort emits a `panic` Tauri event to the frontend (may not arrive if
/// WebView2 has died — file log is the source of truth).
///
/// Backtrace deliberately omitted: `std::backtrace::Backtrace::force_capture()`
/// pulls Windows symbol-resolution dynamic-link symbols (dbghelp.dll surface)
/// into the test binary, which broke `cargo test --lib` on windows-latest CI
/// (`STATUS_ENTRYPOINT_NOT_FOUND`). The location (`file:line:column`) plus the
/// panic payload string provides enough context for bug reports — full
/// backtraces can be recovered from `RUST_BACKTRACE=1` stderr output of the
/// inner default panic handler.
pub fn install_panic_hook(app_handle: Option<tauri::AppHandle>) {
    let prev_hook = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        eprintln!("[panic_hook] panic intercepted");

        let payload_str = if let Some(s) = info.payload().downcast_ref::<&str>() {
            (*s).to_string()
        } else if let Some(s) = info.payload().downcast_ref::<String>() {
            s.clone()
        } else {
            "<panic payload not string>".to_string()
        };
        let location = info
            .location()
            .map(|loc| format!("{}:{}:{}", loc.file(), loc.line(), loc.column()))
            .unwrap_or_else(|| "<unknown location>".to_string());
        let timestamp = logging::current_timestamp_iso();
        let body = format!(
            "PANIC_MARKER ts={} loc={} payload={}",
            timestamp, location, payload_str
        );

        eprintln!("[panic_hook] payload={} loc={}", payload_str, location);
        match logging::write_error_line("PANIC", &body) {
            Ok(()) => eprintln!("[panic_hook] log write OK"),
            Err(e) => eprintln!("[panic_hook] log write failed: {}", e),
        }

        if let Some(handle) = app_handle.as_ref() {
            let panic_payload = PanicPayload {
                message: payload_str.clone(),
                timestamp: timestamp.clone(),
                location: location.clone(),
            };
            match handle.emit("panic", panic_payload) {
                Ok(()) => eprintln!("[panic_hook] emit OK"),
                Err(e) => eprintln!("[panic_hook] emit failed: {}", e),
            }
        }

        prev_hook(info);
    }));
}

// Note: `panic_hook_writes_to_log_file` was removed because invoking
// `install_panic_hook` and then triggering a real panic via `catch_unwind`
// in a unit test caused the Cargo test binary on `windows-latest` to abort
// at startup with `STATUS_ENTRYPOINT_NOT_FOUND` — the combination pulls
// Windows SEH unwind symbols into the test binary that aren't resolvable on
// GitHub Actions runners. The same logic is covered end-to-end by the
// `dev_force_panic` Tauri command (verified manually during PR #661 round 3:
// invoking `dev_force_panic` writes a `PANIC_MARKER` line to
// `<install_dir>/logs/error-YYYYMMDD.log` and emits a Tauri `panic` event).
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn serialize_app_error_roundtrips() {
        // Tauri が AppError を frontend に渡す時と同じ serde Serialize 経路を
        // 直接 test する (旧 to_wire_string は production 未使用で削除済)。
        let e = AppError::new("io.read_failed", "could not read file")
            .with_hint("check file permissions");
        let parsed = serde_json::to_value(&e).expect("valid json");
        assert_eq!(parsed["code"], "io.read_failed");
        assert_eq!(parsed["message"], "could not read file");
        assert_eq!(parsed["hint"], "check file permissions");
        assert!(parsed.get("stacktrace").is_none() || parsed["stacktrace"].is_null());
    }

    #[test]
    fn app_error_display_format() {
        let e = AppError::new("net.timeout", "request timed out");
        assert_eq!(format!("{}", e), "[net.timeout] request timed out");
    }

    #[test]
    fn default_hint_covers_all_known_codes() {
        let with_hint = [
            "state.mtime_conflict",
            "io.file_not_found", "io.read_failed", "io.write_failed",
            "io.delete_failed", "io.backup_failed",
            "io.permission_denied", "io.already_exists",
            "io.would_block", "io.timed_out", "io.error",
            "parse.json_invalid", "parse.json_serialize_failed",
            "parse.schema_invalid", "parse.ffprobe_output_invalid",
            "subprocess.spawn_failed", "subprocess.exit_failed",
            "validation.path_invalid", "validation.not_a_file", "validation.range_invalid",
            "validation.boundary_invalid",
            "path.install_dir_unresolved", "platform.unsupported",
        ];
        for code in with_hint {
            assert!(default_hint_for_code(code).is_some(), "missing hint for code: {}", code);
        }
        assert!(default_hint_for_code("subprocess.cancelled").is_none());
        assert!(default_hint_for_code("internal.error").is_none());
        assert!(default_hint_for_code("unknown.code").is_none());
    }

    #[test]
    fn with_default_hint_attaches_known_code() {
        let e = AppError::new("io.read_failed", "could not read").with_default_hint();
        assert!(e.hint.is_some());
        assert!(e.hint.unwrap().contains("ディスク状況"));
    }

    #[test]
    fn with_default_hint_does_not_overwrite_explicit_hint() {
        let e = AppError::new("io.read_failed", "msg")
            .with_hint("custom hint")
            .with_default_hint();
        assert_eq!(e.hint.as_deref(), Some("custom hint"));
    }

    #[test]
    fn with_default_hint_returns_no_hint_for_unknown_code() {
        let e = AppError::new("unknown.code", "msg").with_default_hint();
        assert!(e.hint.is_none());
    }

    #[test]
    fn from_io_error_attaches_default_hint() {
        let io_err = std::io::Error::new(std::io::ErrorKind::NotFound, "x");
        let e: AppError = io_err.into();
        assert_eq!(e.code, "io.file_not_found");
        assert!(e.hint.is_some());
    }

    #[test]
    fn from_serde_json_error_attaches_default_hint() {
        let json_err = serde_json::from_str::<serde_json::Value>("{ invalid").unwrap_err();
        let e: AppError = json_err.into();
        assert_eq!(e.code, "parse.json_invalid");
        assert!(e.hint.is_some());
    }
}
