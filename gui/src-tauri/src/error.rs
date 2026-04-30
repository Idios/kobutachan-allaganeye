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

    pub fn with_hint(mut self, hint: impl Into<String>) -> Self {
        self.hint = Some(hint.into());
        self
    }

    #[allow(dead_code)]
    pub fn with_stacktrace(mut self, stacktrace: impl Into<String>) -> Self {
        self.stacktrace = Some(stacktrace.into());
        self
    }

    /// Serialize to a JSON string. Used when interfacing with `Result<T, String>`
    /// signature-bound APIs (legacy-shaped Err values). For Tauri commands that
    /// declare `Result<T, AppError>` directly, Tauri's auto-serialize via the
    /// `Serialize` derive is preferred — `to_wire_string` is unnecessary there.
    #[allow(dead_code)]
    pub fn to_wire_string(&self) -> String {
        serde_json::to_string(self).unwrap_or_else(|_| self.message.clone())
    }
}

impl fmt::Display for AppError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "[{}] {}", self.code, self.message)
    }
}

impl std::error::Error for AppError {}

/// `?` 演算子で `std::io::Error` を AppError に自動変換する。code は default
/// `io.error`、message は `e.to_string()`。call site で context-specific code
/// に上書きしたい場合は `.map_err(|e| AppError::new("io.specific", e.to_string()))`
/// を使う。
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
        AppError::new(code, e.to_string())
    }
}

/// `?` 演算子で `serde_json::Error` を AppError に自動変換する。code は
/// `parse.json_invalid` 固定。message は `e.to_string()` で line/column 情報を含む。
impl From<serde_json::Error> for AppError {
    fn from(e: serde_json::Error) -> Self {
        AppError::new("parse.json_invalid", e.to_string())
    }
}

/// 既存 `Err("...".to_string())` / `format!(...)` ベースの呼び出し箇所での後方互換 +
/// `?` 演算子で String error を AppError として propagate するための From impl。
/// code は `internal.error` 固定。call site が message に code を組み込むケース
/// (例 `format!("io.read_failed: {}", e)`) は使わず、`AppError::new("io.read_failed", ...)`
/// で構造化することを推奨。
impl From<String> for AppError {
    fn from(message: String) -> Self {
        AppError::new("internal.error", message)
    }
}

impl From<&str> for AppError {
    fn from(message: &str) -> Self {
        AppError::new("internal.error", message.to_string())
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
        let e = AppError::new("io.read_failed", "could not read file")
            .with_hint("check file permissions");
        let s = e.to_wire_string();
        let parsed: serde_json::Value = serde_json::from_str(&s).expect("valid json");
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
}
