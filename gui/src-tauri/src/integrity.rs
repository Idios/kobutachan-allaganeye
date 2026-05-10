//! Bundled binary/asset integrity check (#668).
//!
//! Build script (`scripts/build-portable-zip.ps1`) generates
//! `integrity-manifest.json` at the payload root. The Tauri release build
//! reads that manifest at startup and emits an `integrity-error` event when
//! files are missing or sizes don't match -- which the frontend turns into a
//! blocking `ErrorModal` (`errorCategory='integrity'`).
//!
//! Mirror of `allaganeye/integrity.py`. The two MUST stay in sync on the
//! manifest schema (version, files[].path/size/tolerance_bytes).

use std::fs;
use std::path::Path;

use serde::{Deserialize, Serialize};

/// Schema for `integrity-manifest.json`. `version` is validated against
/// `SUPPORTED_MANIFEST_VERSION` in `load_manifest`.
#[derive(Debug, Deserialize)]
pub struct Manifest {
    pub version: u32,
    #[serde(default)]
    pub files: Vec<ManifestEntry>,
}
#[derive(Debug, Deserialize)]
pub struct ManifestEntry {
    pub path: String,
    pub size: u64,
    #[serde(default)]
    pub tolerance_bytes: u64,
}

/// Sent to the frontend via `integrity-error` Tauri event when `check`
/// reports failures. Field names are camelCase via serde rename so the
/// JS payload matches `useErrorStore.showError` consumer expectations.
///
/// `manifest_error` (PR #702 review #4) carries the diagnostic message
/// returned by `load_manifest` when the manifest itself is missing or
/// has malformed JSON. `None` for normal "files in the bundle were
/// missing or wrong size" failures. The frontend can show this to the
/// maintainer to disambiguate "fanfare.npz が消えた" from
/// "integrity-manifest.json が JSON parse 失敗".
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct IntegrityErrorPayload {
    pub missing: Vec<String>,
    pub size_mismatch: Vec<SizeMismatch>,
    pub log_path: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub manifest_error: Option<String>,
}
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SizeMismatch {
    pub path: String,
    pub expected: u64,
    pub actual: u64,
}

/// Schema version we know how to interpret. Bumping the manifest schema
/// in the future requires raising this and adding migration code in
/// `load_manifest`.
const SUPPORTED_MANIFEST_VERSION: u32 = 1;

/// Load the manifest. Returns `Err(String)` describing the issue so callers
/// can route it through the same notification path as integrity failures.
pub fn load_manifest(path: &Path) -> Result<Manifest, String> {
    let text = fs::read_to_string(path).map_err(|e| {
        format!("integrity manifest read failed ({}): {}", path.display(), e)
    })?;
    let manifest: Manifest = serde_json::from_str(&text).map_err(|e| {
        format!("integrity manifest invalid JSON ({}): {}", path.display(), e)
    })?;
    // PR #702 review #3 follow-up: validate the schema version so the
    // `Manifest.version` field is genuinely read (no allow(dead_code) needed)
    // and so future schema bumps fail-fast rather than silently mis-decoding.
    if manifest.version != SUPPORTED_MANIFEST_VERSION {
        return Err(format!(
            "integrity manifest version {} unsupported (expected {}): {}",
            manifest.version,
            SUPPORTED_MANIFEST_VERSION,
            path.display()
        ));
    }
    Ok(manifest)
}

use std::io::Write as _;
use std::time::{SystemTime, UNIX_EPOCH};

/// Convert seconds since UNIX epoch into (year, month, day, hour, min, sec).
///
/// Self-contained Gregorian calendar arithmetic so we don't pull in the
/// chrono / time crate just for log-file naming. Tested against known
/// Unix timestamps including leap years.
fn epoch_to_components(secs: u64) -> (u32, u32, u32, u32, u32, u32) {
    let sec = (secs % 60) as u32;
    let total_min = secs / 60;
    let min = (total_min % 60) as u32;
    let total_hour = total_min / 60;
    let hour = (total_hour % 24) as u32;
    let total_days = total_hour / 24;

    let mut year = 1970u32;
    let mut day_of_year = total_days as u32;
    loop {
        let dim = if is_leap(year) { 366 } else { 365 };
        if day_of_year < dim {
            break;
        }
        day_of_year -= dim;
        year += 1;
    }
    let mut month = 1u32;
    let mut day = day_of_year + 1;
    let months_days: [u32; 12] = if is_leap(year) {
        [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    } else {
        [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    };
    for &md in &months_days {
        if day <= md {
            break;
        }
        day -= md;
        month += 1;
    }
    (year, month, day, hour, min, sec)
}

fn is_leap(year: u32) -> bool {
    year.is_multiple_of(400) || (year.is_multiple_of(4) && !year.is_multiple_of(100))
}
fn now_components() -> (u32, u32, u32, u32, u32, u32) {
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    epoch_to_components(secs)
}
fn log_filename() -> String {
    let (y, mo, d, _, _, _) = now_components();
    format!("error-{:04}{:02}{:02}.log", y, mo, d)
}
fn iso8601_now() -> String {
    let (y, mo, d, h, mi, s) = now_components();
    format!(
        "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}Z",
        y, mo, d, h, mi, s
    )
}
fn log_path(install_dir: &Path) -> std::path::PathBuf {
    install_dir.join("logs").join(log_filename())
}

/// Append an integrity-failure record to <install dir>/logs/error-YYYYMMDD.log.
pub(crate) fn write_log(
    install_dir: &Path,
    missing: &[String],
    size_mismatch: &[SizeMismatch],
) -> std::io::Result<()> {
    let logs_dir = install_dir.join("logs");
    fs::create_dir_all(&logs_dir)?;
    let path = logs_dir.join(log_filename());
    let mut f = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)?;
    let now = iso8601_now();
    let missing_json = serde_json::to_string(missing).unwrap_or_else(|_| "[]".into());
    let size_json = serde_json::to_string(size_mismatch).unwrap_or_else(|_| "[]".into());
    writeln!(
        f,
        "{} [error] integrity check failed: missing={}; size_mismatch={}",
        now, missing_json, size_json
    )?;
    Ok(())
}

/// Production-side wrapper: resolves the install dir from `current_exe`,
/// runs `check`, writes the log on failure, and fills `log_path`.
///
/// Returns `None` on success / skip / when install dir cannot be resolved
/// (best-effort fallback so a misconfigured launcher doesn't deadlock the
/// app -- debug builds always go through this None path via the cfg gate
/// in `lib.rs::run`).
pub fn check_install_dir() -> Option<IntegrityErrorPayload> {
    let exe = std::env::current_exe().ok()?;
    let install_dir = exe.parent()?.to_path_buf();
    let manifest_path = install_dir.join("integrity-manifest.json");
    check_install_dir_with_paths(&manifest_path, &install_dir)
}

/// Test-friendly variant: explicit manifest_path / install_dir args so the
/// integration tests can drive the full path without invoking
/// `current_exe`.
pub(crate) fn check_install_dir_with_paths(
    manifest_path: &Path,
    install_dir: &Path,
) -> Option<IntegrityErrorPayload> {
    match check(manifest_path, install_dir) {
        Ok(()) => None,
        Err(mut payload) => {
            // Best-effort log write; failure does not change the outcome.
            let _ = write_log(install_dir, &payload.missing, &payload.size_mismatch);
            payload.log_path = log_path(install_dir).to_string_lossy().into_owned();
            Some(payload)
        }
    }
}

/// Run integrity check.
/// - `Ok(())` when all manifest entries match.
/// - `Err(IntegrityErrorPayload)` when any file is missing or its size is
///   outside `tolerance_bytes`. Aggregated payload lists every failure so
///   the modal can show all at once.
///
/// Manifest read failure (missing/malformed JSON) is also surfaced as an
/// error payload listing the manifest itself in `missing`. This lets the
/// frontend treat a corrupt manifest the same as a corrupt bundle.
pub fn check(manifest_path: &Path, install_dir: &Path) -> Result<(), IntegrityErrorPayload> {
    let manifest = match load_manifest(manifest_path) {
        Ok(m) => m,
        Err(msg) => {
            // PR #702 review #4: surface the load_manifest diagnostic so the
            // frontend can show the maintainer whether the manifest is
            // missing or has malformed JSON. Users still see the same
            // generic "再展開してください" hint either way.
            return Err(IntegrityErrorPayload {
                missing: vec![manifest_path.to_string_lossy().into_owned()],
                size_mismatch: vec![],
                // log_path is filled by check_install_dir wrapper (Task 13).
                // Empty here is acceptable for tests; production callers go
                // through the wrapper.
                log_path: String::new(),
                manifest_error: Some(msg),
            });
        }
    };

    let mut missing: Vec<String> = vec![];
    let mut size_mismatch: Vec<SizeMismatch> = vec![];
    for entry in &manifest.files {
        let target = install_dir.join(&entry.path);
        match fs::metadata(&target) {
            Err(_) => missing.push(entry.path.clone()),
            Ok(meta) => {
                let actual = meta.len();
                let expected = entry.size;
                let tol = entry.tolerance_bytes;
                if actual.abs_diff(expected) > tol {
                    size_mismatch.push(SizeMismatch {
                        path: entry.path.clone(),
                        expected,
                        actual,
                    });
                }
            }
        }
    }

    if missing.is_empty() && size_mismatch.is_empty() {
        return Ok(());
    }
    Err(IntegrityErrorPayload {
        missing,
        size_mismatch,
        log_path: String::new(),
        manifest_error: None,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::TempDir;

    fn write_manifest(dir: &TempDir, body: &str) -> std::path::PathBuf {
        let p = dir.path().join("integrity-manifest.json");
        let mut f = fs::File::create(&p).unwrap();
        f.write_all(body.as_bytes()).unwrap();
        p
    }

    #[test]
    fn load_manifest_parses_valid_json() {
        let dir = TempDir::new().unwrap();
        let path = write_manifest(
            &dir,
            r#"{"version": 1, "generated_at": "2026-05-08T00:00:00Z", "files": [{"path": "a.bin", "size": 100, "tolerance_bytes": 0}]}"#,
        );
        let m = load_manifest(&path).expect("should parse");
        assert_eq!(m.version, 1);
        assert_eq!(m.files.len(), 1);
        assert_eq!(m.files[0].path, "a.bin");
        assert_eq!(m.files[0].size, 100);
        assert_eq!(m.files[0].tolerance_bytes, 0);
    }

    #[test]
    fn load_manifest_returns_err_for_missing_file() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("no-such.json");
        let err = load_manifest(&path).unwrap_err();
        assert!(err.contains("read failed"));
    }

    #[test]
    fn load_manifest_returns_err_for_invalid_json() {
        let dir = TempDir::new().unwrap();
        let path = write_manifest(&dir, "not json");
        let err = load_manifest(&path).unwrap_err();
        assert!(err.contains("invalid JSON"));
    }

    #[test]
    fn manifest_entry_tolerance_bytes_defaults_to_zero() {
        let dir = TempDir::new().unwrap();
        let path = write_manifest(
            &dir,
            r#"{"version": 1, "generated_at": "2026-05-08T00:00:00Z", "files": [{"path": "a.bin", "size": 100}]}"#,
        );
        let m = load_manifest(&path).expect("should parse");
        assert_eq!(m.files[0].tolerance_bytes, 0);
    }

    #[test]
    fn check_happy_path_returns_ok() {
        let dir = TempDir::new().unwrap();
        let install = dir.path();
        let target = install.join("ffmpeg/ffmpeg.exe");
        fs::create_dir_all(target.parent().unwrap()).unwrap();
        fs::write(&target, vec![b'x'; 100]).unwrap();

        let manifest_path = write_manifest(
            &dir,
            r#"{"version": 1, "generated_at": "2026-05-08T00:00:00Z", "files": [{"path": "ffmpeg/ffmpeg.exe", "size": 100, "tolerance_bytes": 0}]}"#,
        );
        check(&manifest_path, install).expect("should pass");
    }

    #[test]
    fn check_detects_missing_file() {
        let dir = TempDir::new().unwrap();
        let install = dir.path();
        let manifest_path = write_manifest(
            &dir,
            r#"{"version": 1, "generated_at": "2026-05-08T00:00:00Z", "files": [{"path": "absent.bin", "size": 100, "tolerance_bytes": 0}]}"#,
        );
        let err = check(&manifest_path, install).unwrap_err();
        assert_eq!(err.missing, vec!["absent.bin".to_string()]);
        assert!(err.size_mismatch.is_empty());
    }

    #[test]
    fn check_detects_size_mismatch_outside_tolerance() {
        let dir = TempDir::new().unwrap();
        let install = dir.path();
        let target = install.join("tiny.bin");
        fs::write(&target, vec![b'x'; 50]).unwrap();
        let manifest_path = write_manifest(
            &dir,
            r#"{"version": 1, "generated_at": "2026-05-08T00:00:00Z", "files": [{"path": "tiny.bin", "size": 100, "tolerance_bytes": 0}]}"#,
        );
        let err = check(&manifest_path, install).unwrap_err();
        assert!(err.missing.is_empty());
        assert_eq!(err.size_mismatch.len(), 1);
        assert_eq!(err.size_mismatch[0].path, "tiny.bin");
        assert_eq!(err.size_mismatch[0].expected, 100);
        assert_eq!(err.size_mismatch[0].actual, 50);
    }

    #[test]
    fn check_passes_within_tolerance() {
        let dir = TempDir::new().unwrap();
        let install = dir.path();
        let target = install.join("buffered.bin");
        fs::write(&target, vec![b'x'; 105]).unwrap();
        let manifest_path = write_manifest(
            &dir,
            r#"{"version": 1, "generated_at": "2026-05-08T00:00:00Z", "files": [{"path": "buffered.bin", "size": 100, "tolerance_bytes": 10}]}"#,
        );
        check(&manifest_path, install).expect("within tolerance should pass");
    }

    #[test]
    fn epoch_to_components_handles_known_epoch_seconds() {
        // 2026-05-08T12:34:56Z = 1778243696 seconds since epoch
        let (y, mo, d, h, mi, s) = epoch_to_components(1778243696);
        assert_eq!((y, mo, d, h, mi, s), (2026, 5, 8, 12, 34, 56));
    }

    #[test]
    fn epoch_to_components_handles_leap_year_feb_29() {
        // 2024-02-29T00:00:00Z = 1709164800 seconds since epoch
        let (y, mo, d, _h, _mi, _s) = epoch_to_components(1709164800);
        assert_eq!((y, mo, d), (2024, 2, 29));
    }

    #[test]
    fn write_log_creates_logs_dir_and_appends_record() {
        let dir = TempDir::new().unwrap();
        let install = dir.path();
        let missing = vec!["absent.bin".to_string()];
        let size_mismatch = vec![];
        write_log(install, &missing, &size_mismatch).expect("should write");

        let logs = install.join("logs");
        assert!(logs.exists(), "logs dir should be created");
        let log_files: Vec<_> = fs::read_dir(&logs).unwrap().collect();
        assert_eq!(log_files.len(), 1);
        let path = log_files[0].as_ref().unwrap().path();
        let name = path.file_name().unwrap().to_string_lossy();
        assert!(
            name.starts_with("error-") && name.ends_with(".log"),
            "filename format: {}",
            name
        );
        let content = fs::read_to_string(&path).unwrap();
        assert!(content.contains("integrity check failed"));
        assert!(content.contains("\"absent.bin\""));
    }

    #[test]
    fn check_install_dir_returns_none_on_success() {
        // Mock install dir with manifest pointing to a file that exists
        let dir = TempDir::new().unwrap();
        let install = dir.path();
        let target = install.join("a.bin");
        fs::write(&target, b"x").unwrap();
        let manifest = install.join("integrity-manifest.json");
        fs::write(
            &manifest,
            r#"{"version": 1, "generated_at": "2026-05-08T00:00:00Z", "files": [{"path": "a.bin", "size": 1, "tolerance_bytes": 0}]}"#,
        )
        .unwrap();

        // We need to invoke through the wrapper, not check() directly, to
        // verify the wrapper routes through check() and back.
        let result = check_install_dir_with_paths(&manifest, install);
        assert!(result.is_none());
    }

    #[test]
    fn check_install_dir_returns_payload_with_log_path_on_failure() {
        let dir = TempDir::new().unwrap();
        let install = dir.path();
        let manifest = install.join("integrity-manifest.json");
        fs::write(
            &manifest,
            r#"{"version": 1, "generated_at": "2026-05-08T00:00:00Z", "files": [{"path": "absent.bin", "size": 1, "tolerance_bytes": 0}]}"#,
        )
        .unwrap();

        let payload = check_install_dir_with_paths(&manifest, install).expect("should fail");
        assert_eq!(payload.missing, vec!["absent.bin".to_string()]);
        assert!(
            payload.log_path.contains("logs"),
            "log_path should reference logs dir: {}",
            payload.log_path
        );
        // Bundle missing (not manifest), so manifest_error stays None.
        assert!(payload.manifest_error.is_none());
        // Log file should also exist on disk
        let logs = install.join("logs");
        assert!(logs.exists());
    }

    #[test]
    fn check_payload_carries_manifest_error_when_manifest_is_corrupt() {
        // PR #702 review #4: corrupt manifest must surface the load_manifest
        // diagnostic via IntegrityErrorPayload.manifest_error so frontend can
        // show "manifest が壊れた JSON" vs "bundle file が削除された".
        let dir = TempDir::new().unwrap();
        let install = dir.path();
        let manifest_path = write_manifest(&dir, "not json");

        let err = check(&manifest_path, install).expect_err("should fail on bad JSON");
        assert!(err.size_mismatch.is_empty());
        assert_eq!(err.missing.len(), 1);
        assert!(err.missing[0].ends_with("integrity-manifest.json"));
        let me = err.manifest_error.expect("manifest_error should be Some");
        assert!(me.contains("invalid JSON"), "got: {}", me);
    }

    #[test]
    fn check_payload_carries_manifest_error_when_manifest_is_missing() {
        let dir = TempDir::new().unwrap();
        let install = dir.path();
        let manifest_path = install.join("does-not-exist.json");

        let err = check(&manifest_path, install).expect_err("should fail on missing manifest");
        let me = err.manifest_error.expect("manifest_error should be Some");
        assert!(me.contains("read failed"), "got: {}", me);
    }
}
