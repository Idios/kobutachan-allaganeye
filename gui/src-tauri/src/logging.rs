use std::path::PathBuf;
use std::sync::{Mutex, OnceLock};

const PANIC_MARKER: &str = "PANIC_MARKER";

static LOG_DIR_OVERRIDE: OnceLock<Mutex<Option<PathBuf>>> = OnceLock::new();

fn override_slot() -> &'static Mutex<Option<PathBuf>> {
    LOG_DIR_OVERRIDE.get_or_init(|| Mutex::new(None))
}

#[allow(dead_code)] // used by `error.rs::tests::panic_hook_writes_to_log_file` (cross-module test)
pub fn set_log_dir_override(path: Option<PathBuf>) {
    *override_slot().lock().unwrap() = path;
}

pub fn log_dir() -> std::io::Result<PathBuf> {
    if let Some(p) = override_slot().lock().unwrap().as_ref() {
        return Ok(p.clone());
    }
    if let Ok(override_path) = std::env::var("LOG_DIR_OVERRIDE") {
        return Ok(PathBuf::from(override_path));
    }
    let exe = std::env::current_exe()?;
    let parent = exe.parent().ok_or_else(|| {
        std::io::Error::new(std::io::ErrorKind::Other, "current_exe has no parent")
    })?;
    Ok(parent.join("logs"))
}

pub fn ensure_log_dir() -> std::io::Result<PathBuf> {
    let dir = log_dir()?;
    std::fs::create_dir_all(&dir)?;
    Ok(dir)
}

fn days_to_ymd(days_since_epoch: i64) -> (i32, u32, u32) {
    let z = days_since_epoch + 719468;
    let era = if z >= 0 { z / 146097 } else { (z - 146096) / 146097 };
    let doe = (z - era * 146097) as u64;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let mut y = (yoe as i64) + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    if m <= 2 {
        y += 1;
    }
    (y as i32, m as u32, d as u32)
}

fn now_unix_secs() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

pub fn current_ymd_compact() -> String {
    let now = now_unix_secs();
    let days = (now / 86400) as i64;
    let (y, m, d) = days_to_ymd(days);
    format!("{:04}{:02}{:02}", y, m, d)
}

pub fn current_timestamp_iso() -> String {
    let now = now_unix_secs();
    let days = (now / 86400) as i64;
    let (y, mo, d) = days_to_ymd(days);
    let rem = now % 86400;
    let h = rem / 3600;
    let mi = (rem % 3600) / 60;
    let se = rem % 60;
    format!(
        "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}Z",
        y, mo, d, h, mi, se
    )
}

pub fn write_error_line(category: &str, body: &str) -> std::io::Result<()> {
    let dir = ensure_log_dir()?;
    let date = current_ymd_compact();
    let path = dir.join(format!("error-{}.log", date));
    let timestamp = current_timestamp_iso();
    let escaped_body = body.replace('\n', "\\n");
    let line = format!("[{}] [{}] {}\n", timestamp, category, escaped_body);

    use std::io::Write;
    let mut f = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)?;
    f.write_all(line.as_bytes())?;
    Ok(())
}

pub fn rotate_old_logs(retention_days: u64) -> std::io::Result<u32> {
    let dir = match log_dir() {
        Ok(d) => d,
        Err(_) => return Ok(0),
    };
    if !dir.exists() {
        return Ok(0);
    }
    let now = std::time::SystemTime::now();
    let threshold_secs = retention_days * 86400;
    let mut removed = 0u32;
    for entry in std::fs::read_dir(&dir)? {
        let entry = entry?;
        let name = entry.file_name().to_string_lossy().to_string();
        if !name.ends_with(".log") {
            continue;
        }
        let metadata = match entry.metadata() {
            Ok(m) => m,
            Err(_) => continue,
        };
        let mtime = match metadata.modified() {
            Ok(t) => t,
            Err(_) => continue,
        };
        if let Ok(elapsed) = now.duration_since(mtime) {
            if elapsed.as_secs() > threshold_secs && std::fs::remove_file(entry.path()).is_ok() {
                removed += 1;
            }
        }
    }
    Ok(removed)
}

/// Window in which a recent PANIC_MARKER counts as "the previous session
/// crashed". Set to 24 hours so the warning surfaces on the next user-driven
/// startup regardless of how long they took to relaunch (manual rebuild,
/// restart-after-coffee-break, etc.). The 7-day rotation removes the file
/// itself eventually, so this can never resurface a panic from "weeks ago".
const PANIC_DETECT_WINDOW_SECS: u64 = 24 * 60 * 60;

pub fn detect_panic_from_previous_session() -> Option<String> {
    let dir = log_dir().ok()?;
    if !dir.exists() {
        return None;
    }
    let mut entries: Vec<_> = std::fs::read_dir(&dir)
        .ok()?
        .filter_map(|e| e.ok())
        .filter(|e| {
            let name = e.file_name();
            let s = name.to_string_lossy();
            s.starts_with("error-") && s.ends_with(".log")
        })
        .collect();
    entries.sort_by_key(|e| e.metadata().and_then(|m| m.modified()).ok());
    let latest = entries.last()?;
    let mtime = latest.metadata().ok()?.modified().ok()?;
    let now = std::time::SystemTime::now();
    let elapsed = now.duration_since(mtime).ok()?;
    if elapsed.as_secs() > PANIC_DETECT_WINDOW_SECS {
        return None;
    }
    let content = std::fs::read_to_string(latest.path()).ok()?;
    content
        .lines()
        .rev()
        .find(|l| l.contains(PANIC_MARKER))
        .map(|l| l.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;
    use tempfile::TempDir;

    static TEST_MUTEX: Mutex<()> = Mutex::new(());

    fn with_temp_log_dir<F: FnOnce(&std::path::Path)>(f: F) {
        let _guard = TEST_MUTEX.lock().unwrap_or_else(|e| e.into_inner());
        let temp = TempDir::new().expect("create tempdir");
        set_log_dir_override(Some(temp.path().to_path_buf()));
        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            f(temp.path());
        }));
        set_log_dir_override(None);
        if let Err(e) = result {
            std::panic::resume_unwind(e);
        }
    }

    #[test]
    fn write_error_line_appends_to_dated_file() {
        with_temp_log_dir(|dir| {
            write_error_line("TEST", "hello world").expect("write 1");
            write_error_line("TEST", "second line").expect("write 2");
            let date = current_ymd_compact();
            let path = dir.join(format!("error-{}.log", date));
            let content = std::fs::read_to_string(&path).expect("read log");
            assert!(content.contains("hello world"));
            assert!(content.contains("second line"));
            assert_eq!(content.lines().count(), 2);
        });
    }

    #[test]
    fn write_error_line_escapes_newlines() {
        with_temp_log_dir(|dir| {
            write_error_line("TEST", "line1\nline2").expect("write");
            let date = current_ymd_compact();
            let path = dir.join(format!("error-{}.log", date));
            let content = std::fs::read_to_string(&path).expect("read log");
            assert_eq!(content.lines().count(), 1);
            assert!(content.contains("line1\\nline2"));
        });
    }

    #[test]
    fn rotate_old_logs_removes_files_older_than_retention() {
        with_temp_log_dir(|dir| {
            let old = dir.join("error-19990101.log");
            std::fs::write(&old, "old").expect("write old");
            let old_mtime = std::time::SystemTime::now()
                - std::time::Duration::from_secs(8 * 86400);
            let f = std::fs::File::options()
                .write(true)
                .open(&old)
                .expect("open old");
            f.set_modified(old_mtime).expect("set old mtime");
            drop(f);

            let new = dir.join("error-29990101.log");
            std::fs::write(&new, "new").expect("write new");

            let removed = rotate_old_logs(7).expect("rotate");
            assert_eq!(removed, 1);
            assert!(!old.exists());
            assert!(new.exists());
        });
    }

    #[test]
    fn rotate_old_logs_keeps_recent_files() {
        with_temp_log_dir(|dir| {
            let recent = dir.join("error-recent.log");
            std::fs::write(&recent, "recent").expect("write recent");
            let removed = rotate_old_logs(7).expect("rotate");
            assert_eq!(removed, 0);
            assert!(recent.exists());
        });
    }

    #[test]
    fn detect_panic_marker_returns_recent() {
        with_temp_log_dir(|dir| {
            let date = current_ymd_compact();
            let path = dir.join(format!("error-{}.log", date));
            std::fs::write(
                &path,
                "[ts] [INFO] regular line\n[ts] [PANIC] PANIC_MARKER something happened\n",
            )
            .expect("write");
            let result = detect_panic_from_previous_session();
            assert!(result.is_some());
            assert!(result.unwrap().contains("PANIC_MARKER"));
        });
    }

    #[test]
    fn detect_panic_marker_returns_none_when_old() {
        with_temp_log_dir(|dir| {
            let date = current_ymd_compact();
            let path = dir.join(format!("error-{}.log", date));
            std::fs::write(&path, "[ts] [PANIC] PANIC_MARKER old crash\n").expect("write");
            // 25 hours ago: outside the 24-hour PANIC_DETECT_WINDOW_SECS
            let old_mtime = std::time::SystemTime::now()
                - std::time::Duration::from_secs(25 * 60 * 60);
            let f = std::fs::File::options()
                .write(true)
                .open(&path)
                .expect("open");
            f.set_modified(old_mtime).expect("set mtime");
            drop(f);
            let result = detect_panic_from_previous_session();
            assert!(result.is_none());
        });
    }

    #[test]
    fn current_ymd_compact_format() {
        let s = current_ymd_compact();
        assert_eq!(s.len(), 8);
        assert!(s.chars().all(|c| c.is_ascii_digit()));
    }

    #[test]
    fn days_to_ymd_known_values() {
        // 2026-04-29 = 20577 days since 1970-01-01
        // Compute from a known date: 2026-01-01 epoch = 1767225600 / 86400 = 20454 days
        // 2026-04-29 = 20454 + 31 + 28 + 31 + 28 = 20572 days
        // Actually 2026 is not leap, so Jan(31) + Feb(28) + Mar(31) + Apr(28 = 29-1) = 118 days from Jan 1
        // 20454 + 118 = 20572
        let (y, m, d) = days_to_ymd(20572);
        assert_eq!((y, m, d), (2026, 4, 29));
    }
}
