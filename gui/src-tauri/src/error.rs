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
    /// Builder used by `#[allow(dead_code)]`-tagged constructors below — kept
    /// for the upcoming AppError migration of legacy commands (派生 issue).
    /// Until that migration lands, all accessors are unused in production
    /// (only the test module references them), hence the allowance.
    #[allow(dead_code)]
    pub fn new(code: impl Into<String>, message: impl Into<String>) -> Self {
        Self {
            code: code.into(),
            message: message.into(),
            hint: None,
            stacktrace: None,
        }
    }

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

    /// Serialize to a JSON string suitable for Tauri command `Result<T, String>` Err values.
    /// Frontend should `try { JSON.parse(msg) } catch` to detect structured vs legacy raw strings.
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
