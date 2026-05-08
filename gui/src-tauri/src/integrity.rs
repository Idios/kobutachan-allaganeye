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

/// Schema for `integrity-manifest.json`.
#[allow(dead_code)] // used in Task 12+ (check/log/setup hook)
#[derive(Debug, Deserialize)]
pub struct Manifest {
    #[allow(dead_code)] // recorded for forward-compat; only `files` is used now
    pub version: u32,
    #[serde(default)]
    pub files: Vec<ManifestEntry>,
}

#[allow(dead_code)] // used in Task 12+ (check/log/setup hook)
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
#[allow(dead_code)] // used in Task 12+ (check/log/setup hook)
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct IntegrityErrorPayload {
    pub missing: Vec<String>,
    pub size_mismatch: Vec<SizeMismatch>,
    pub log_path: String,
}

#[allow(dead_code)] // used in Task 12+ (check/log/setup hook)
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SizeMismatch {
    pub path: String,
    pub expected: u64,
    pub actual: u64,
}

/// Load the manifest. Returns `Err(String)` describing the issue so callers
/// can route it through the same notification path as integrity failures.
#[allow(dead_code)] // used in Task 12+ (check/log/setup hook)
pub fn load_manifest(path: &Path) -> Result<Manifest, String> {
    let text = fs::read_to_string(path).map_err(|e| {
        format!("integrity manifest read failed ({}): {}", path.display(), e)
    })?;
    serde_json::from_str(&text).map_err(|e| {
        format!("integrity manifest invalid JSON ({}): {}", path.display(), e)
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
}
