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
    pub backtrace: String,
    pub timestamp: String,
    pub location: String,
}

/// Install a global panic hook. Writes panic info to the install-dir log file
/// (`<install_dir>/logs/error-YYYYMMDD.log`) with a `PANIC_MARKER` token, then
/// best-effort emits a `panic` Tauri event to the frontend (may not arrive if
/// WebView2 has died — file log is the source of truth).
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
        let backtrace = std::backtrace::Backtrace::force_capture();
        let backtrace_str = format!("{}", backtrace);
        let timestamp = logging::current_timestamp_iso();
        let body = format!(
            "PANIC_MARKER ts={} loc={} payload={} backtrace={}",
            timestamp, location, payload_str, backtrace_str
        );

        eprintln!("[panic_hook] payload={} loc={}", payload_str, location);
        match logging::write_error_line("PANIC", &body) {
            Ok(()) => eprintln!("[panic_hook] log write OK"),
            Err(e) => eprintln!("[panic_hook] log write failed: {}", e),
        }

        if let Some(handle) = app_handle.as_ref() {
            let panic_payload = PanicPayload {
                message: payload_str.clone(),
                backtrace: backtrace_str.clone(),
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

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;
    use tempfile::TempDir;

    static TEST_MUTEX: Mutex<()> = Mutex::new(());

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

    #[test]
    fn panic_hook_writes_to_log_file() {
        let _guard = TEST_MUTEX.lock().unwrap_or_else(|e| e.into_inner());
        let temp = TempDir::new().expect("tempdir");
        logging::set_log_dir_override(Some(temp.path().to_path_buf()));

        // Install hook with no app handle (best-effort emit skipped)
        install_panic_hook(None);

        // Trigger a panic in a child thread to avoid aborting the test process
        let result = std::panic::catch_unwind(|| {
            panic!("test panic from panic_hook_writes_to_log_file");
        });
        assert!(result.is_err());

        // Find the dated log file
        let date = logging::current_ymd_compact();
        let log_path = temp.path().join(format!("error-{}.log", date));
        assert!(
            log_path.exists(),
            "log file should exist after panic: {:?}",
            log_path
        );

        let content = std::fs::read_to_string(&log_path).expect("read log");
        assert!(
            content.contains("PANIC_MARKER"),
            "log should contain PANIC_MARKER: {}",
            content
        );
        assert!(
            content.contains("test panic from panic_hook_writes_to_log_file"),
            "log should contain panic message: {}",
            content
        );

        // Cleanup
        logging::set_log_dir_override(None);
        // Restore default panic hook so other tests are unaffected
        let _ = std::panic::take_hook();
    }
}
