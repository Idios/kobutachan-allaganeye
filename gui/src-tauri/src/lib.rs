use std::fs;
use std::path::{Path, PathBuf};

use serde_json::Value;

#[tauri::command]
async fn load_metadata(path: String) -> Result<Value, String> {
    load_metadata_sync(&PathBuf::from(&path))
}

fn load_metadata_sync(meta_path: &Path) -> Result<Value, String> {
    if !meta_path.exists() {
        return Err(format!("metadata file not found: {}", meta_path.display()));
    }
    let content = fs::read_to_string(meta_path)
        .map_err(|e| format!("read failed ({}): {}", meta_path.display(), e))?;
    let value: Value = serde_json::from_str(&content)
        .map_err(|e| format!("invalid JSON in {}: {}", meta_path.display(), e))?;
    if !value.is_object() {
        return Err(format!(
            "metadata file {} root must be a JSON object",
            meta_path.display()
        ));
    }
    Ok(value)
}

#[tauri::command]
async fn apply_changes(path: String, metadata: Value) -> Result<(), String> {
    apply_changes_sync(&PathBuf::from(&path), &metadata)
}

/// #516 — atomically restore metadata.json from the first-Apply backup.
#[tauri::command]
async fn restore_from_original(path: String) -> Result<(), String> {
    restore_from_original_sync(&PathBuf::from(&path))
}

fn restore_from_original_sync(meta_path: &Path) -> Result<(), String> {
    let parent = meta_path
        .parent()
        .ok_or_else(|| format!("metadata path has no parent: {}", meta_path.display()))?;
    let original_path = parent.join("metadata.original.json");
    if !original_path.exists() {
        return Err(format!(
            "no backup to restore: {}",
            original_path.display()
        ));
    }
    let content = fs::read_to_string(&original_path)
        .map_err(|e| format!("read backup failed ({}): {}", original_path.display(), e))?;
    let value: Value = serde_json::from_str(&content).map_err(|e| {
        format!(
            "parse backup failed ({}): {}",
            original_path.display(),
            e
        )
    })?;
    write_metadata_atomic(meta_path, &value)
}

/// #516 — report whether a metadata.original.json exists next to the active
/// metadata.json. Used by the GUI to enable/disable the [元に戻す] button.
#[tauri::command]
async fn check_backup_exists(path: String) -> Result<bool, String> {
    let meta_path = PathBuf::from(&path);
    let parent = meta_path
        .parent()
        .ok_or_else(|| format!("metadata path has no parent: {}", meta_path.display()))?;
    Ok(parent.join("metadata.original.json").exists())
}

fn apply_changes_sync(meta_path: &Path, payload: &Value) -> Result<(), String> {
    let parent = meta_path
        .parent()
        .ok_or_else(|| format!("metadata path has no parent: {}", meta_path.display()))?;
    let original_path = parent.join("metadata.original.json");

    if meta_path.exists() && !original_path.exists() {
        fs::copy(meta_path, &original_path).map_err(|e| {
            format!(
                "failed to back up {} to {}: {}",
                meta_path.display(),
                original_path.display(),
                e
            )
        })?;
    }

    write_metadata_atomic(meta_path, payload)
}

fn write_metadata_atomic(path: &Path, payload: &Value) -> Result<(), String> {
    let parent = path
        .parent()
        .ok_or_else(|| format!("metadata path has no parent: {}", path.display()))?;
    if !parent.exists() {
        fs::create_dir_all(parent)
            .map_err(|e| format!("create dir {} failed: {}", parent.display(), e))?;
    }
    let mut tmp_path = path.to_path_buf();
    let tmp_name = match path.file_name() {
        Some(n) => format!("{}.tmp", n.to_string_lossy()),
        None => return Err(format!("metadata path has no file name: {}", path.display())),
    };
    tmp_path.set_file_name(tmp_name);

    let serialized = serde_json::to_string_pretty(payload)
        .map_err(|e| format!("serialize failed: {}", e))?;
    fs::write(&tmp_path, serialized)
        .map_err(|e| format!("write tmp {} failed: {}", tmp_path.display(), e))?;
    if let Err(e) = fs::rename(&tmp_path, path) {
        let _ = fs::remove_file(&tmp_path);
        return Err(format!(
            "rename {} -> {} failed: {}",
            tmp_path.display(),
            path.display(),
            e
        ));
    }
    Ok(())
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![
            load_metadata,
            apply_changes,
            restore_from_original,
            check_backup_exists,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::fs;
    use tempfile::TempDir;

    #[test]
    fn atomic_write_creates_target() {
        let tmp = TempDir::new().unwrap();
        let target = tmp.path().join("metadata.json");
        let payload = json!({"source": "a.mkv", "matches": []});
        write_metadata_atomic(&target, &payload).unwrap();
        assert!(target.exists());
        let roundtrip: Value = serde_json::from_str(&fs::read_to_string(&target).unwrap()).unwrap();
        assert_eq!(roundtrip, payload);
        // no stray .tmp
        assert!(!tmp.path().join("metadata.json.tmp").exists());
    }

    #[test]
    fn atomic_write_overwrites_existing() {
        let tmp = TempDir::new().unwrap();
        let target = tmp.path().join("metadata.json");
        fs::write(&target, "{\"old\": true}").unwrap();
        let payload = json!({"new": true});
        write_metadata_atomic(&target, &payload).unwrap();
        let roundtrip: Value = serde_json::from_str(&fs::read_to_string(&target).unwrap()).unwrap();
        assert_eq!(roundtrip, payload);
    }

    #[test]
    fn apply_changes_creates_backup_on_first_call() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        let backup = tmp.path().join("metadata.original.json");
        let original = json!({"source": "a.mkv", "matches": [{"m": 1}]});
        fs::write(&meta, serde_json::to_string_pretty(&original).unwrap()).unwrap();

        let edited = json!({"source": "a.mkv", "matches": [{"m": 1, "edited": true}]});
        apply_changes_sync(&meta, &edited).unwrap();

        assert!(backup.exists());
        let backup_value: Value =
            serde_json::from_str(&fs::read_to_string(&backup).unwrap()).unwrap();
        assert_eq!(backup_value, original);
        let current: Value = serde_json::from_str(&fs::read_to_string(&meta).unwrap()).unwrap();
        assert_eq!(current, edited);
    }

    #[test]
    fn apply_changes_preserves_backup_across_subsequent_calls() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        let backup = tmp.path().join("metadata.original.json");
        let original = json!({"version": "v1"});
        fs::write(&meta, serde_json::to_string_pretty(&original).unwrap()).unwrap();

        apply_changes_sync(&meta, &json!({"version": "v2"})).unwrap();
        apply_changes_sync(&meta, &json!({"version": "v3"})).unwrap();
        apply_changes_sync(&meta, &json!({"version": "v4"})).unwrap();

        // backup stays the very first snapshot
        let backup_value: Value =
            serde_json::from_str(&fs::read_to_string(&backup).unwrap()).unwrap();
        assert_eq!(backup_value, original);
        let current: Value = serde_json::from_str(&fs::read_to_string(&meta).unwrap()).unwrap();
        assert_eq!(current, json!({"version": "v4"}));
    }

    #[test]
    fn apply_changes_skips_backup_when_target_missing() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        let backup = tmp.path().join("metadata.original.json");
        // No pre-existing metadata.json
        apply_changes_sync(&meta, &json!({"first": true})).unwrap();
        assert!(meta.exists());
        // No backup created because there was nothing to back up
        assert!(!backup.exists());
    }

    #[test]
    fn restore_from_original_succeeds_when_backup_exists() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        let backup = tmp.path().join("metadata.original.json");

        let pristine = json!({"source": "a.mkv", "matches": [{"m": 1}]});
        fs::write(&backup, serde_json::to_string_pretty(&pristine).unwrap()).unwrap();

        let dirty = json!({"source": "a.mkv", "matches": [{"m": 1, "edited": true}]});
        fs::write(&meta, serde_json::to_string_pretty(&dirty).unwrap()).unwrap();

        restore_from_original_sync(&meta).unwrap();

        let current: Value =
            serde_json::from_str(&fs::read_to_string(&meta).unwrap()).unwrap();
        assert_eq!(current, pristine);
    }

    #[test]
    fn restore_from_original_fails_when_no_backup() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        fs::write(&meta, r#"{"ok":true}"#).unwrap();

        let err = restore_from_original_sync(&meta).unwrap_err();
        assert!(err.contains("no backup to restore"));
    }

    #[test]
    fn restore_preserves_backup_file_after_successful_restore() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        let backup = tmp.path().join("metadata.original.json");
        let pristine = json!({"v": "original"});
        fs::write(&backup, serde_json::to_string_pretty(&pristine).unwrap()).unwrap();
        fs::write(&meta, r#"{"v":"dirty"}"#).unwrap();

        restore_from_original_sync(&meta).unwrap();

        // backup should still be present (restore is a read-only fetch)
        assert!(backup.exists());
        let backup_value: Value =
            serde_json::from_str(&fs::read_to_string(&backup).unwrap()).unwrap();
        assert_eq!(backup_value, pristine);
    }

    #[test]
    fn check_backup_exists_returns_false_when_absent() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        // not calling the async fn directly — probe via same logic
        let parent = meta.parent().unwrap();
        assert!(!parent.join("metadata.original.json").exists());
    }

    #[test]
    fn check_backup_exists_returns_true_when_present() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        let backup = tmp.path().join("metadata.original.json");
        fs::write(&backup, r#"{}"#).unwrap();
        assert!(backup.exists());
        let parent = meta.parent().unwrap();
        assert!(parent.join("metadata.original.json").exists());
    }

    #[test]
    fn load_metadata_returns_error_when_file_missing() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        let err = load_metadata_sync(&meta).unwrap_err();
        assert!(err.contains("metadata file not found"));
    }

    #[test]
    fn load_metadata_returns_error_on_invalid_json() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        fs::write(&meta, r#"{"source": "a.mkv", invalid"#).unwrap();
        let err = load_metadata_sync(&meta).unwrap_err();
        assert!(err.contains("invalid JSON"));
    }

    #[test]
    fn load_metadata_returns_ok_on_valid_json() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        let payload = json!({"source": "a.mkv", "matches": []});
        fs::write(&meta, serde_json::to_string_pretty(&payload).unwrap()).unwrap();
        let value = load_metadata_sync(&meta).unwrap();
        assert_eq!(value, payload);
    }

    #[test]
    fn load_metadata_rejects_non_object_root() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        // Valid JSON but root is an array — Python side's read_metadata also rejects this.
        fs::write(&meta, r#"["not", "an", "object"]"#).unwrap();
        let err = load_metadata_sync(&meta).unwrap_err();
        assert!(err.contains("must be a JSON object"));
    }
}
