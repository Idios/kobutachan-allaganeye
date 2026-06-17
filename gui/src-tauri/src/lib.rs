use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::sync::{Arc, OnceLock};
use std::time::{SystemTime, UNIX_EPOCH};

use axum::{
    extract::{Path as AxumPath, State},
    http::StatusCode,
    response::IntoResponse,
    routing::get,
    Router,
};
use tauri::{Emitter, Manager};
use futures::future::join_all;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::sync::{Mutex, Semaphore};
use tower_http::services::ServeFile;
use uuid::Uuid;

mod error;
mod integrity;
mod logging;
mod process_util;

use error::AppError;

/// #465 -- per-token mapping from opaque UUID to absolute video file path.
///
/// Shared between the axum server's handler state and the Tauri commands so
/// that `register_video` can insert and the handler can look up without
/// copying the whole map each request.
type TokenMap = Arc<Mutex<HashMap<Uuid, PathBuf>>>;

/// #465 -- process-global video-server handle.
///
/// Holds the bound port (`None` until the first `register_video` call starts
/// the server) and the shared token map. Wrapped in a `tokio::sync::Mutex`
/// so multiple concurrent Tauri async commands can await it safely.
struct VideoServer {
    port: Option<u16>,
    tokens: TokenMap,
}

impl VideoServer {
    fn new() -> Self {
        Self {
            port: None,
            tokens: Arc::new(Mutex::new(HashMap::new())),
        }
    }
}

static VIDEO_SERVER: OnceLock<Mutex<VideoServer>> = OnceLock::new();

fn video_server() -> &'static Mutex<VideoServer> {
    VIDEO_SERVER.get_or_init(|| Mutex::new(VideoServer::new()))
}

/// #465 -- payload returned to the GUI from `register_video`.
///
/// The frontend sets `url` as the `<video>` element's `src` and keeps `token`
/// around in case it later needs to unregister the file (future feature).
#[derive(Debug, Serialize)]
pub struct RegisteredVideo {
    pub url: String,
    pub token: String,
}

#[tauri::command]
async fn load_metadata(path: String) -> Result<Value, AppError> {
    load_metadata_sync(&PathBuf::from(&path))
}

fn load_metadata_sync(meta_path: &Path) -> Result<Value, AppError> {
    if !meta_path.exists() {
        return Err(AppError::new(
            "io.file_not_found",
            format!("metadata file not found: {}", meta_path.display()),
        )
        .with_default_hint());
    }
    let content = fs::read_to_string(meta_path).map_err(|e| {
        AppError::new(
            "io.read_failed",
            format!("read failed ({}): {}", meta_path.display(), e),
        )
        .with_default_hint()
    })?;
    let value: Value = serde_json::from_str(&content).map_err(|e| {
        AppError::new(
            "parse.json_invalid",
            format!("invalid JSON in {}: {}", meta_path.display(), e),
        )
        .with_default_hint()
    })?;
    if !value.is_object() {
        return Err(AppError::new(
            "parse.schema_invalid",
            format!(
                "metadata file {} root must be a JSON object",
                meta_path.display()
            ),
        )
        .with_default_hint());
    }
    Ok(value)
}

/// #514 — return the mtime (ms since epoch) of an existing metadata file,
/// or `None` when the file is missing. Used by the GUI to detect external
/// modifications between load and apply.
#[tauri::command]
async fn get_metadata_mtime(path: String) -> Result<Option<u64>, AppError> {
    Ok(file_mtime_ms(&PathBuf::from(&path)))
}

fn file_mtime_ms(path: &Path) -> Option<u64> {
    fs::metadata(path)
        .and_then(|m| m.modified())
        .ok()
        .and_then(|t: SystemTime| t.duration_since(UNIX_EPOCH).ok())
        .map(|d| d.as_millis() as u64)
}

#[tauri::command]
async fn apply_changes(
    path: String,
    metadata: Value,
    expected_mtime_ms: Option<u64>,
) -> Result<u64, AppError> {
    let meta_path = PathBuf::from(&path);
    apply_changes_sync(&meta_path, &metadata, expected_mtime_ms)?;
    file_mtime_ms(&meta_path).ok_or_else(|| {
        AppError::new(
            "io.read_failed",
            format!(
                "apply succeeded but could not read post-write mtime: {}",
                meta_path.display()
            ),
        )
        .with_default_hint()
    })
}

/// #517 — persist the in-memory edit buffer as `metadata.draft.json` next to
/// the live `metadata.json`. Survives WebView reloads and app crashes.
#[tauri::command]
async fn save_draft(path: String, draft: Value) -> Result<(), AppError> {
    save_draft_sync(&PathBuf::from(&path), &draft)
}

/// #517 — reload the draft buffer if one exists. Returns `None` when no
/// draft is on disk (fresh session or post-apply state).
#[tauri::command]
async fn load_draft(path: String) -> Result<Option<Value>, AppError> {
    load_draft_sync(&PathBuf::from(&path))
}

/// #517 — delete the draft file. Called after a successful `apply` so a
/// restart doesn't re-prompt about stale edits.
#[tauri::command]
async fn clear_draft(path: String) -> Result<(), AppError> {
    clear_draft_sync(&PathBuf::from(&path))
}

fn draft_path_for(meta_path: &Path) -> Result<PathBuf, AppError> {
    let parent = meta_path.parent().ok_or_else(|| {
        AppError::new(
            "validation.path_invalid",
            format!("metadata path has no parent: {}", meta_path.display()),
        )
        .with_default_hint()
    })?;
    Ok(parent.join("metadata.draft.json"))
}

fn save_draft_sync(meta_path: &Path, draft: &Value) -> Result<(), AppError> {
    let draft_path = draft_path_for(meta_path)?;
    write_metadata_atomic(&draft_path, draft)
}

fn load_draft_sync(meta_path: &Path) -> Result<Option<Value>, AppError> {
    let draft_path = draft_path_for(meta_path)?;
    if !draft_path.exists() {
        return Ok(None);
    }
    let content = fs::read_to_string(&draft_path).map_err(|e| {
        AppError::new(
            "io.read_failed",
            format!("read draft failed ({}): {}", draft_path.display(), e),
        )
        .with_default_hint()
    })?;
    let value: Value = serde_json::from_str(&content).map_err(|e| {
        AppError::new(
            "parse.json_invalid",
            format!("invalid JSON in draft {}: {}", draft_path.display(), e),
        )
        .with_default_hint()
    })?;
    Ok(Some(value))
}

fn clear_draft_sync(meta_path: &Path) -> Result<(), AppError> {
    let draft_path = draft_path_for(meta_path)?;
    if !draft_path.exists() {
        // Nothing to clear — treat as success so callers don't have to
        // special-case the post-apply no-draft state.
        return Ok(());
    }
    fs::remove_file(&draft_path).map_err(|e| {
        AppError::new(
            "io.delete_failed",
            format!("remove draft failed ({}): {}", draft_path.display(), e),
        )
        .with_default_hint()
    })
}

/// #516 — atomically restore metadata.json from the first-Apply backup.
#[tauri::command]
async fn restore_from_original(path: String) -> Result<(), AppError> {
    restore_from_original_sync(&PathBuf::from(&path))
}

fn restore_from_original_sync(meta_path: &Path) -> Result<(), AppError> {
    let parent = meta_path.parent().ok_or_else(|| {
        AppError::new(
            "validation.path_invalid",
            format!("metadata path has no parent: {}", meta_path.display()),
        )
        .with_default_hint()
    })?;
    let original_path = parent.join("metadata.original.json");
    if !original_path.exists() {
        return Err(AppError::new(
            "io.file_not_found",
            format!("no backup to restore: {}", original_path.display()),
        )
        .with_default_hint());
    }
    let content = fs::read_to_string(&original_path).map_err(|e| {
        AppError::new(
            "io.read_failed",
            format!("read backup failed ({}): {}", original_path.display(), e),
        )
        .with_default_hint()
    })?;
    let value: Value = serde_json::from_str(&content).map_err(|e| {
        AppError::new(
            "parse.json_invalid",
            format!("parse backup failed ({}): {}", original_path.display(), e),
        )
        .with_default_hint()
    })?;
    write_metadata_atomic(meta_path, &value)
}

/// #516 — report whether a metadata.original.json exists next to the active
/// metadata.json. Used by the GUI to enable/disable the [元に戻す] button.
#[tauri::command]
async fn check_backup_exists(path: String) -> Result<bool, AppError> {
    let meta_path = PathBuf::from(&path);
    let parent = meta_path.parent().ok_or_else(|| {
        AppError::new(
            "validation.path_invalid",
            format!("metadata path has no parent: {}", meta_path.display()),
        )
        .with_default_hint()
    })?;
    Ok(parent.join("metadata.original.json").exists())
}

/// #571 — single entry of the recent-videos history persisted at
/// `<home>/.allaganeye/recent.json`.
///
/// `path` is the absolute file path with the Windows extended-length `\\?\`
/// prefix already stripped (see `setSelectedVideoPath` on the TS side).
/// `mtime_ms` is the file's last-modified timestamp at insert time; the GUI
/// uses it to decide whether the cached `recent.json` entry still points at
/// the same content (subsequent edits to the same path bump mtime). The GUI
/// re-checks `Path::exists` on every load so deleted files are surfaced as
/// "not found" without us having to prune them eagerly.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct RecentEntry {
    pub path: String,
    #[serde(rename = "fileName")]
    pub file_name: String,
    #[serde(rename = "sizeBytes")]
    pub size_bytes: u64,
    #[serde(rename = "mtimeMs")]
    pub mtime_ms: u64,
    #[serde(rename = "addedAtMs")]
    pub added_at_ms: u64,
}

const RECENT_LIMIT: usize = 10;

/// #571 — strip the Windows extended-length path prefix (`\\?\` / `\\?\UNC\`).
///
/// Tauri's dialog and drag-drop sometimes hand back paths with the `\\?\`
/// prefix (Win32's "long path" form). Storing those verbatim makes the UI
/// inconsistent with normal `E:\…` rendering and breaks naive consumers
/// (e.g. `Path::exists` mis-resolution noted in PR #655 review). This
/// mirrors the TS-side `stripExtendedPathPrefix` (`gui/src/utils/path.ts`)
/// so both the recent-list (`add_recent`) and the export output dir
/// (`ExportScreen.handlePickDir`) end up with the same canonical form.
fn strip_extended_path_prefix(p: &str) -> String {
    if let Some(rest) = p.strip_prefix("\\\\?\\UNC\\") {
        format!("\\\\{}", rest)
    } else if let Some(rest) = p.strip_prefix("\\\\?\\") {
        rest.to_string()
    } else {
        p.to_string()
    }
}

/// #571 — resolve `<install dir>/recent.json` without creating it.
///
/// PR #655 Round 2 review: keep the recent-videos history alongside the
/// executable so the tool is fully self-contained — Portable ZIP philosophy
/// (extract = install, delete = uninstall, no leftover state in the user
/// profile). Production = `<bundle install dir>/recent.json`, dev =
/// `target/debug/recent.json` (gitignored). The same review also moved the
/// thumbnail cache (`thumb_cache_dir`, #465) to `<install dir>/cache/`
/// for the same philosophy.
fn recent_path() -> Result<PathBuf, AppError> {
    let exe = std::env::current_exe().map_err(|e| {
        AppError::new(
            "path.install_dir_unresolved",
            format!("failed to resolve current_exe: {}", e),
        )
        .with_default_hint()
    })?;
    let dir = exe.parent().ok_or_else(|| {
        AppError::new(
            "path.install_dir_unresolved",
            format!("current_exe has no parent: {}", exe.display()),
        )
        .with_default_hint()
    })?;
    Ok(dir.join("recent.json"))
}

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

/// #571 — load the persisted history. Returns an empty vec when the file is
/// missing (fresh install) or when the JSON cannot be parsed (treat corrupt
/// state as empty rather than blocking the drop screen).
fn read_recent_sync(path: &Path) -> Vec<RecentEntry> {
    if !path.exists() {
        return Vec::new();
    }
    let Ok(content) = fs::read_to_string(path) else {
        return Vec::new();
    };
    serde_json::from_str::<Vec<RecentEntry>>(&content).unwrap_or_default()
}

/// #571 — normalize a path string for the recent-list dedup key.
///
/// Two paths point at the same file on Windows when they differ only in
/// (a) letter case (`E:\` ≡ `e:\`) or (b) directory separator (`/` vs `\`,
/// the Tauri dialog usually returns `\` while D&D fixtures and CLI handoff
/// can produce `/`). We collapse both so the dedup logic doesn't miss
/// either form. Stays a private helper because the persisted entry keeps
/// the original separators — only the comparison key is normalized.
fn normalize_path_key(p: &str) -> String {
    p.to_lowercase().replace('/', "\\")
}

/// #571 — push `entry` to the front of the history, dedup by `path`, and
/// truncate to `RECENT_LIMIT`. Returns the post-write list so the caller
/// (Zustand store) can mirror it without an extra `read_recent` round trip.
fn add_recent_sync(path: &Path, entry: RecentEntry) -> Result<Vec<RecentEntry>, AppError> {
    let mut list = read_recent_sync(path);
    // Dedup via `normalize_path_key` (case-insensitive + separator-insensitive).
    // The drop happens before we push so the new entry's mtime / addedAt
    // overwrite the stale ones — selecting an existing recent moves it to
    // the top with refreshed metadata.
    let key = normalize_path_key(&entry.path);
    list.retain(|e| normalize_path_key(&e.path) != key);
    list.insert(0, entry);
    list.truncate(RECENT_LIMIT);
    write_recent_atomic(path, &list)?;
    Ok(list)
}

/// #571 — wipe the history (used by the GUI's "履歴をクリア" affordance and
/// by tests). Treats "file already absent" as success so callers don't have
/// to special-case the fresh-install state.
fn clear_recent_sync(path: &Path) -> Result<(), AppError> {
    if !path.exists() {
        return Ok(());
    }
    fs::remove_file(path).map_err(|e| {
        AppError::new(
            "io.delete_failed",
            format!("remove recent.json failed ({}): {}", path.display(), e),
        )
        .with_default_hint()
    })
}

fn write_recent_atomic(path: &Path, list: &[RecentEntry]) -> Result<(), AppError> {
    let parent = path.parent().ok_or_else(|| {
        AppError::new(
            "validation.path_invalid",
            format!("recent path has no parent: {}", path.display()),
        )
        .with_default_hint()
    })?;
    if !parent.exists() {
        fs::create_dir_all(parent).map_err(|e| {
            AppError::new(
                "io.write_failed",
                format!("create dir {} failed: {}", parent.display(), e),
            )
            .with_default_hint()
        })?;
    }
    let mut tmp_path = path.to_path_buf();
    let tmp_name = match path.file_name() {
        Some(n) => format!("{}.tmp", n.to_string_lossy()),
        None => {
            return Err(AppError::new(
                "validation.path_invalid",
                format!("recent path has no file name: {}", path.display()),
            )
            .with_default_hint())
        }
    };
    tmp_path.set_file_name(tmp_name);
    let serialized = serde_json::to_string_pretty(list).map_err(|e| {
        AppError::new(
            "parse.json_serialize_failed",
            format!("serialize recent failed: {}", e),
        )
        .with_default_hint()
    })?;
    fs::write(&tmp_path, serialized).map_err(|e| {
        AppError::new(
            "io.write_failed",
            format!("write tmp {} failed: {}", tmp_path.display(), e),
        )
        .with_default_hint()
    })?;
    if let Err(e) = fs::rename(&tmp_path, path) {
        let _ = fs::remove_file(&tmp_path);
        return Err(AppError::new(
            "io.write_failed",
            format!(
                "rename {} -> {} failed: {}",
                tmp_path.display(),
                path.display(),
                e
            ),
        )
        .with_default_hint());
    }
    Ok(())
}

/// #571 — drop entries whose backing file no longer exists.
///
/// PR #655 review (Round 2): the original design rendered missing entries
/// as grey-out + click → toast. The user feedback simplified that to "if
/// the file is gone, just drop it from the list" — so this prune runs on
/// every read and on every add. The cost is O(RECENT_LIMIT) `exists()`
/// syscalls per command which is negligible at the 10-item cap.
fn prune_missing(entries: Vec<RecentEntry>) -> Vec<RecentEntry> {
    entries
        .into_iter()
        .filter(|e| Path::new(&e.path).exists())
        .collect()
}

#[tauri::command]
async fn read_recent() -> Result<Vec<RecentEntry>, AppError> {
    let path = recent_path()?;
    let raw = read_recent_sync(&path);
    let original_len = raw.len();
    let pruned = prune_missing(raw);
    // Persist the prune so the user's `recent.json` doesn't keep accreting
    // dead entries — but only when something actually changed, to avoid
    // pointless mtime bumps on idle reads.
    if pruned.len() != original_len {
        write_recent_atomic(&path, &pruned)?;
    }
    Ok(pruned)
}

#[tauri::command]
async fn add_recent(path: String) -> Result<Vec<RecentEntry>, AppError> {
    let video_path = PathBuf::from(&path);
    if !video_path.exists() {
        return Err(AppError::new(
            "io.file_not_found",
            format!("file not found: {}", video_path.display()),
        )
        .with_default_hint());
    }
    let meta = fs::metadata(&video_path).map_err(|e| {
        AppError::new(
            "io.read_failed",
            format!("stat failed ({}): {}", video_path.display(), e),
        )
        .with_default_hint()
    })?;
    let size_bytes = meta.len();
    let mtime_ms = meta
        .modified()
        .ok()
        .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0);
    // PR #655 review (Round 2): strip the Windows `\\?\` extended-length
    // prefix before persisting. Tauri dialogs/drag-drop hand it to us but
    // the rest of the app (UI display, dedup, downstream consumers) wants
    // the canonical form. Mirrors `stripExtendedPathPrefix` on the TS side.
    let canonical_path = strip_extended_path_prefix(&path);
    let file_name = video_path
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_else(|| canonical_path.clone());
    let entry = RecentEntry {
        path: canonical_path,
        file_name,
        size_bytes,
        mtime_ms,
        added_at_ms: now_ms(),
    };
    let recent_p = recent_path()?;
    add_recent_with_prune(&recent_p, entry)
}

/// PR #655 Round 4 — wrapper around `add_recent_sync` that also prunes
/// stale neighbors before returning.
///
/// Round 3 verification surfaced a bug: when the user dragged in a fresh
/// video while the existing list already contained an entry whose file had
/// been moved/deleted, the stale neighbor stuck around. `read_recent`
/// pruned on every call but `add_recent` only called the un-pruned
/// `add_recent_sync`, so the just-returned list was the only thing the
/// frontend's `recentStore.add` saw — and it kept the stale entry.
///
/// Splitting the prune into a thin wrapper keeps the pure
/// `add_recent_sync` testable with synthetic paths (the existing 8 tests
/// use `make_recent_entry("E:\\videos\\a.mkv", …)` paths that don't exist
/// on disk; pruning inside `add_recent_sync` would empty the list out
/// from under them). The just-inserted entry is guaranteed to exist
/// (`add_recent` checks at the top), so it survives the prune.
fn add_recent_with_prune(
    path: &Path,
    entry: RecentEntry,
) -> Result<Vec<RecentEntry>, AppError> {
    let inserted = add_recent_sync(path, entry)?;
    let initial_len = inserted.len();
    let pruned = prune_missing(inserted);
    if pruned.len() != initial_len {
        write_recent_atomic(path, &pruned)?;
    }
    Ok(pruned)
}

#[tauri::command]
async fn clear_recent() -> Result<(), AppError> {
    clear_recent_sync(&recent_path()?)
}

/// #465 -- register a video file with the local HTTP server and return a
/// playback URL for the GUI's `<video>` element.
///
/// Starts the axum server lazily on the first call (subsequent calls reuse
/// the same bound port). The returned URL has the form
/// `http://127.0.0.1:{port}/video/{token}` and is only reachable from the
/// same machine; the server binds exclusively to 127.0.0.1.
#[tauri::command]
async fn register_video(path: String) -> Result<RegisteredVideo, AppError> {
    let file_path = PathBuf::from(&path);
    let canonical = validate_video_path(&file_path)?;

    let port = ensure_server_started().await?;
    let token = {
        let guard = video_server().lock().await;
        let mut tokens = guard.tokens.lock().await;
        register_video_sync(&canonical, &mut tokens)
    };

    Ok(RegisteredVideo {
        url: format!("http://127.0.0.1:{}/video/{}", port, token),
        token: token.to_string(),
    })
}

/// #465 review (B): drop で確定した video ファイルを ffprobe で読み、
/// duration / fps / width / height / codec / size を返す。Phase 2 で
/// `dummyProbeVideo` (固定値) を返していた経路をこの実装で置換する。
///
/// 実装は ffprobe を subprocess 起動し JSON で出力されるストリーム情報を
/// パースする。Python 側 (`allaganeye/video/probe.py`) と同じ ffprobe
/// 経路を踏襲しており、結果は detection 用 ProbeResult と概ね一致する
/// (audio_codec は Phase 3 GUI には不要なので返さない)。
#[derive(Serialize, Clone, Debug)]
struct VideoProbeInfo {
    path: String,
    #[serde(rename = "fileName")]
    file_name: String,
    #[serde(rename = "sizeBytes")]
    size_bytes: u64,
    #[serde(rename = "durationSeconds")]
    duration_seconds: f64,
    width: u32,
    height: u32,
    fps: f64,
    codec: String,
}

#[tauri::command]
async fn probe_video(path: String) -> Result<VideoProbeInfo, AppError> {
    let file_path = PathBuf::from(&path);
    let canonical = validate_video_path(&file_path)?;
    probe_video_with(&canonical, "ffprobe").await
}

/// Pure helper testable in cargo unit tests by injecting an ffprobe-like
/// command (e.g. a fixture-emitting shell script).
async fn probe_video_with(
    path: &Path,
    ffprobe: &str,
) -> Result<VideoProbeInfo, AppError> {
    let size_bytes = fs::metadata(path)
        .map_err(|e| {
            AppError::new(
                "io.read_failed",
                format!("stat failed ({}): {}", path.display(), e),
            )
            .with_default_hint()
        })?
        .len();

    let mut cmd = tokio::process::Command::new(ffprobe);
    cmd.arg("-v")
        .arg("quiet")
        .arg("-print_format")
        .arg("json")
        .arg("-show_format")
        .arg("-show_streams")
        .arg(path);
    process_util::apply_no_window(&mut cmd);
    let output = cmd.output().await.map_err(|e| {
        AppError::new(
            "subprocess.spawn_failed",
            format!("ffprobe spawn failed: {e}"),
        )
        .with_default_hint()
    })?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(AppError::new(
            "subprocess.exit_failed",
            format!(
                "ffprobe failed (exit {:?}): {}",
                output.status.code(),
                stderr.trim()
            ),
        )
        .with_default_hint());
    }

    let json: Value = serde_json::from_slice(&output.stdout).map_err(|e| {
        AppError::new(
            "parse.ffprobe_output_invalid",
            format!("ffprobe json parse failed: {e}"),
        )
        .with_default_hint()
    })?;

    let streams = json
        .get("streams")
        .and_then(|s| s.as_array())
        .ok_or_else(|| {
            AppError::new(
                "parse.ffprobe_output_invalid",
                "ffprobe output missing 'streams' array",
            )
            .with_default_hint()
        })?;
    let video_stream = streams
        .iter()
        .find(|s| s.get("codec_type").and_then(|v| v.as_str()) == Some("video"))
        .ok_or_else(|| {
            AppError::new(
                "parse.ffprobe_output_invalid",
                "no video stream in ffprobe output",
            )
            .with_default_hint()
        })?;

    let width = video_stream
        .get("width")
        .and_then(|v| v.as_u64())
        .ok_or_else(|| {
            AppError::new(
                "parse.ffprobe_output_invalid",
                "video stream missing width",
            )
            .with_default_hint()
        })? as u32;
    let height = video_stream
        .get("height")
        .and_then(|v| v.as_u64())
        .ok_or_else(|| {
            AppError::new(
                "parse.ffprobe_output_invalid",
                "video stream missing height",
            )
            .with_default_hint()
        })? as u32;
    let codec = video_stream
        .get("codec_name")
        .and_then(|v| v.as_str())
        .unwrap_or("unknown")
        .to_string();

    // Frame rate: prefer r_frame_rate (e.g. "60/1" or "60000/1001"), fall
    // back to avg_frame_rate. Mirrors Python's probe.py logic.
    let fps = parse_frame_rate_str(
        video_stream.get("r_frame_rate").and_then(|v| v.as_str()),
    )
    .or_else(|| {
        parse_frame_rate_str(
            video_stream.get("avg_frame_rate").and_then(|v| v.as_str()),
        )
    })
    .ok_or_else(|| {
        AppError::new(
            "parse.ffprobe_output_invalid",
            "cannot determine frame rate",
        )
        .with_default_hint()
    })?;

    let duration_seconds = json
        .get("format")
        .and_then(|f| f.get("duration"))
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())
        .ok_or_else(|| {
            AppError::new(
                "parse.ffprobe_output_invalid",
                "format.duration missing or unparseable",
            )
            .with_default_hint()
        })?;
    if duration_seconds <= 0.0 {
        return Err(AppError::new(
            "validation.range_invalid",
            "duration is non-positive",
        )
        .with_default_hint());
    }

    let file_name = path
        .file_name()
        .map(|n| n.to_string_lossy().to_string())
        .unwrap_or_default();

    Ok(VideoProbeInfo {
        path: path.to_string_lossy().to_string(),
        file_name,
        size_bytes,
        duration_seconds,
        width,
        height,
        fps,
        codec,
    })
}

/// Parse a frame rate string like "60/1" or "60000/1001". Returns None when
/// the string is missing, malformed, or evaluates to <= 0.
fn parse_frame_rate_str(s: Option<&str>) -> Option<f64> {
    let raw = s?;
    let (num, den) = raw.split_once('/')?;
    let num: f64 = num.parse().ok()?;
    let den: f64 = den.parse().ok()?;
    if den == 0.0 {
        return None;
    }
    let fps = num / den;
    if fps > 0.0 {
        Some(fps)
    } else {
        None
    }
}

/// Validate that `path` points to an existing regular file and return the
/// canonicalized absolute path on success.
fn validate_video_path(path: &Path) -> Result<PathBuf, AppError> {
    if !path.exists() {
        return Err(AppError::new(
            "io.file_not_found",
            format!("video file not found: {}", path.display()),
        )
        .with_default_hint());
    }
    let meta = fs::metadata(path).map_err(|e| {
        AppError::new(
            "io.read_failed",
            format!("stat failed ({}): {}", path.display(), e),
        )
        .with_default_hint()
    })?;
    if !meta.is_file() {
        return Err(AppError::new(
            "validation.not_a_file",
            format!("video path is not a regular file: {}", path.display()),
        )
        .with_default_hint());
    }
    fs::canonicalize(path).map_err(|e| {
        AppError::new(
            "io.read_failed",
            format!("canonicalize failed ({}): {}", path.display(), e),
        )
        .with_default_hint()
    })
}

/// Pure helper: mint a new UUID, insert `(token, path)` into the token map,
/// and return the token. Extracted so unit tests can exercise the
/// registration logic without starting an axum server.
fn register_video_sync(path: &Path, tokens: &mut HashMap<Uuid, PathBuf>) -> Uuid {
    let token = Uuid::new_v4();
    tokens.insert(token, path.to_path_buf());
    token
}

/// Ensure the local video server is listening on 127.0.0.1 and return the
/// bound port. Idempotent: re-uses the existing port on every call after the
/// first.
async fn ensure_server_started() -> Result<u16, AppError> {
    let mut guard = video_server().lock().await;
    if let Some(port) = guard.port {
        return Ok(port);
    }

    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.map_err(|e| {
        AppError::new(
            "subprocess.spawn_failed",
            format!("bind 127.0.0.1:0 failed: {}", e),
        )
        .with_default_hint()
    })?;
    let addr = listener
        .local_addr()
        .map_err(|e| format!("local_addr failed: {}", e))?;

    let tokens = guard.tokens.clone();
    let app = build_router(tokens);

    tokio::spawn(async move {
        if let Err(e) = axum::serve(listener, app).await {
            eprintln!("video server error: {}", e);
        }
    });

    guard.port = Some(addr.port());
    Ok(addr.port())
}

/// Build the axum `Router` that serves `GET /video/{token}` and dispatches
/// to `ServeFile` (which handles HTTP Range requests natively) when the
/// token resolves to a registered file.
fn build_router(tokens: TokenMap) -> Router {
    Router::new()
        .route("/video/{token}", get(serve_video))
        .with_state(tokens)
}

async fn serve_video(
    State(tokens): State<TokenMap>,
    AxumPath(token): AxumPath<String>,
    request: axum::extract::Request,
) -> axum::response::Response {
    let parsed = match Uuid::parse_str(&token) {
        Ok(t) => t,
        Err(_) => return (StatusCode::NOT_FOUND, "unknown token").into_response(),
    };

    let path = {
        let map = tokens.lock().await;
        map.get(&parsed).cloned()
    };

    match path {
        Some(p) => {
            // ServeFile handles Range, Content-Type sniffing, and If-Range.
            // Forward the original request so the Range header survives.
            let mut svc = ServeFile::new(p);
            match svc.try_call(request).await {
                Ok(resp) => resp.into_response(),
                Err(_) => (StatusCode::INTERNAL_SERVER_ERROR, "serve failed").into_response(),
            }
        }
        None => (StatusCode::NOT_FOUND, "unknown token").into_response(),
    }
}

fn apply_changes_sync(
    meta_path: &Path,
    payload: &Value,
    expected_mtime_ms: Option<u64>,
) -> Result<(), AppError> {
    // #814 -- reject any match whose boundaries would make metadata.json
    // unreadable on reload. The zod MatchSchema requires finite numeric
    // start_time/end_time on every match (and end >= start); we enforce strict
    // end > start on write. apply_changes takes arbitrary JSON, so this is the
    // last line of defense (audit P1-2): a frontend bug / stale caller / direct
    // invoke must not be able to persist a file the GUI can't read back. A
    // match missing a boundary, with a non-numeric boundary, or with
    // end <= start is rejected before any backup/write. (codex adversarial
    // review, #814)
    if let Some(matches) = payload.get("matches").and_then(Value::as_array) {
        for (i, m) in matches.iter().enumerate() {
            let start = m.get("start_time").and_then(Value::as_f64);
            let end = m.get("end_time").and_then(Value::as_f64);
            let valid = match (start, end) {
                (Some(s), Some(e)) => e > s,
                _ => false,
            };
            if !valid {
                return Err(AppError::new(
                    "validation.boundary_invalid",
                    format!(
                        "match at index {} has invalid boundaries (start_time/end_time must be finite numbers with end_time > start_time); got start_time={:?}, end_time={:?}",
                        i,
                        m.get("start_time"),
                        m.get("end_time")
                    ),
                )
                .with_default_hint());
            }
        }
    }

    // #514 — refuse to overwrite a file that has been modified externally
    // since the caller last loaded it. Target not existing is not a conflict
    // (treat as a fresh write).
    if let Some(expected) = expected_mtime_ms {
        if meta_path.exists() {
            let actual = file_mtime_ms(meta_path).ok_or_else(|| {
                AppError::new(
                    "io.read_failed",
                    format!("cannot read mtime of {}", meta_path.display()),
                )
                .with_default_hint()
            })?;
            if actual != expected {
                return Err(AppError::new(
                    "state.mtime_conflict",
                    format!(
                        "conflict: external modification detected ({} expected mtime {}, got {})",
                        meta_path.display(),
                        expected,
                        actual
                    ),
                )
                .with_default_hint());
            }
        }
    }


    let parent = meta_path.parent().ok_or_else(|| {
        AppError::new(
            "validation.path_invalid",
            format!("metadata path has no parent: {}", meta_path.display()),
        )
        .with_default_hint()
    })?;
    let original_path = parent.join("metadata.original.json");

    if meta_path.exists() && !original_path.exists() {
        fs::copy(meta_path, &original_path).map_err(|e| {
            AppError::new(
                "io.backup_failed",
                format!(
                    "failed to back up {} to {}: {}",
                    meta_path.display(),
                    original_path.display(),
                    e
                ),
            )
            .with_default_hint()
        })?;
    }

    write_metadata_atomic(meta_path, payload)
}

fn write_metadata_atomic(path: &Path, payload: &Value) -> Result<(), AppError> {
    let parent = path.parent().ok_or_else(|| {
        AppError::new(
            "validation.path_invalid",
            format!("metadata path has no parent: {}", path.display()),
        )
        .with_default_hint()
    })?;
    if !parent.exists() {
        fs::create_dir_all(parent).map_err(|e| {
            AppError::new(
                "io.write_failed",
                format!("create dir {} failed: {}", parent.display(), e),
            )
            .with_default_hint()
        })?;
    }
    let mut tmp_path = path.to_path_buf();
    let tmp_name = match path.file_name() {
        Some(n) => format!("{}.tmp", n.to_string_lossy()),
        None => {
            return Err(AppError::new(
                "validation.path_invalid",
                format!("metadata path has no file name: {}", path.display()),
            )
            .with_default_hint())
        }
    };
    tmp_path.set_file_name(tmp_name);

    let serialized = serde_json::to_string_pretty(payload).map_err(|e| {
        AppError::new(
            "parse.json_serialize_failed",
            format!("serialize failed: {}", e),
        )
        .with_default_hint()
    })?;
    fs::write(&tmp_path, serialized).map_err(|e| {
        AppError::new(
            "io.write_failed",
            format!("write tmp {} failed: {}", tmp_path.display(), e),
        )
        .with_default_hint()
    })?;
    if let Err(e) = fs::rename(&tmp_path, path) {
        let _ = fs::remove_file(&tmp_path);
        return Err(AppError::new(
            "io.write_failed",
            format!(
                "rename {} -> {} failed: {}",
                tmp_path.display(),
                path.display(),
                e
            ),
        )
        .with_default_hint());
    }
    Ok(())
}

/// #465 -- per-candidate thumbnail entry returned to the GUI.
///
/// `t_seconds` is the absolute timestamp (seconds from video start) where the
/// thumbnail was extracted; `file_path` is an absolute path to the cached
/// WebP file the frontend can read (via tauri_plugin_fs) or serve via the
/// video HTTP server in a later iteration.
#[derive(Debug, Serialize)]
pub struct ThumbnailEntry {
    pub t_seconds: f64,
    pub file_path: String,
}

/// #465 -- stable per-video cache key derived from the absolute path and the
/// file's last-modified time. Recreating the same video (even at the same
/// path) yields a different hash because mtime changes, forcing a fresh
/// thumbnail cache and preventing stale frames from being served.
fn compute_video_cache_hash(video_path: &Path, mtime_ms: u64) -> String {
    let mut hasher = Sha256::new();
    let key = format!("{}:{}", video_path.display(), mtime_ms);
    hasher.update(key.as_bytes());
    let digest = hasher.finalize();
    let mut hex = String::with_capacity(digest.len() * 2);
    for byte in digest.iter() {
        hex.push_str(&format!("{:02x}", byte));
    }
    hex
}

/// #465 -- resolve `<install dir>/cache/<video_hash>/thumbs/`.
///
/// Returns the path without creating it; callers that intend to write thumbs
/// are responsible for `create_dir_all`.
///
/// PR #655 Round 2: relocated from `~/.allaganeye/cache/...` to the exe
/// directory to match the Portable ZIP philosophy already adopted by
/// `recent.json` (#571). Tool deletion = folder deletion = no leftover
/// state in the user profile. Production = `<bundle install dir>/cache/...`,
/// dev = `target/debug/cache/...` (gitignored).
fn thumb_cache_dir(video_hash: &str) -> Result<PathBuf, AppError> {
    let exe = std::env::current_exe().map_err(|e| {
        AppError::new(
            "path.install_dir_unresolved",
            format!("failed to resolve current_exe: {}", e),
        )
        .with_default_hint()
    })?;
    let dir = exe.parent().ok_or_else(|| {
        AppError::new(
            "path.install_dir_unresolved",
            format!("current_exe has no parent: {}", exe.display()),
        )
        .with_default_hint()
    })?;
    Ok(dir.join("cache").join(video_hash).join("thumbs"))
}

/// #465 -- compute the evenly-spaced timestamps for a given boundary window.
///
/// Produces `count` samples covering
/// `[boundary - window_seconds, boundary + window_seconds]`, clamped at 0.
/// Pulled out for unit testing (no ffmpeg involvement).
fn compute_candidate_timestamps(
    boundary_t_seconds: f64,
    window_seconds: f64,
    count: u32,
) -> Vec<f64> {
    if count == 0 {
        return Vec::new();
    }
    if count == 1 {
        return vec![boundary_t_seconds.max(0.0)];
    }
    let start = boundary_t_seconds - window_seconds;
    let end = boundary_t_seconds + window_seconds;
    let step = (end - start) / f64::from(count - 1);
    let mut out = Vec::with_capacity(count as usize);
    for i in 0..count {
        let t = start + step * f64::from(i);
        out.push(t.max(0.0));
    }
    out
}

/// #465 -- filesystem-safe token for a single cached thumbnail.
///
/// Format: `match{match_index:03}_t{timestamp_ms}` so the filename carries
/// enough context to debug cache entries by eye (e.g. `match003_t452500`).
fn thumb_token(match_index: u32, t_seconds: f64) -> String {
    let t_ms = (t_seconds * 1000.0).round() as i64;
    let t_ms = t_ms.max(0) as u64;
    format!("match{:03}_t{}", match_index, t_ms)
}

/// #465 -- generate (or reuse cached) thumbnails for a match boundary window.
///
/// Spawns `ffmpeg` per missing frame with bounded concurrency. Returns one
/// entry per requested timestamp in order; any ffmpeg failure aborts the
/// whole call so the caller never sees a partially populated list.
#[tauri::command]
async fn generate_match_thumbnails(
    video_path: String,
    match_index: u32,
    boundary_t_seconds: f64,
    window_seconds: f64,
    count: u32,
) -> Result<Vec<ThumbnailEntry>, AppError> {
    let video = PathBuf::from(&video_path);
    if !video.exists() {
        return Err(AppError::new(
            "io.file_not_found",
            format!("video file not found: {}", video.display()),
        )
        .with_default_hint());
    }
    let meta = fs::metadata(&video).map_err(|e| {
        AppError::new(
            "io.read_failed",
            format!("stat failed ({}): {}", video.display(), e),
        )
        .with_default_hint()
    })?;
    let mtime_ms = meta
        .modified()
        .map_err(|e| {
            AppError::new(
                "io.read_failed",
                format!("mtime failed ({}): {}", video.display(), e),
            )
            .with_default_hint()
        })?
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .map_err(|e| {
            AppError::new(
                "io.read_failed",
                format!("mtime before epoch ({}): {}", video.display(), e),
            )
            .with_default_hint()
        })?;
    let canonical = fs::canonicalize(&video).map_err(|e| {
        AppError::new(
            "io.read_failed",
            format!("canonicalize failed ({}): {}", video.display(), e),
        )
        .with_default_hint()
    })?;

    let video_hash = compute_video_cache_hash(&canonical, mtime_ms);
    let cache_dir = thumb_cache_dir(&video_hash)?;
    fs::create_dir_all(&cache_dir).map_err(|e| {
        AppError::new(
            "io.write_failed",
            format!("create cache dir {} failed: {}", cache_dir.display(), e),
        )
        .with_default_hint()
    })?;

    let timestamps = compute_candidate_timestamps(boundary_t_seconds, window_seconds, count);
    let semaphore = Arc::new(Semaphore::new(4));

    let mut tasks = Vec::with_capacity(timestamps.len());
    for t in timestamps.iter().copied() {
        let token = thumb_token(match_index, t);
        let out_path = cache_dir.join(format!("{}.webp", token));
        let video_for_task = canonical.clone();
        let sem = Arc::clone(&semaphore);
        tasks.push(async move {
            let _permit = sem.acquire_owned().await.map_err(|e| {
                AppError::new(
                    "internal.error",
                    format!("semaphore closed: {}", e),
                )
                .with_default_hint()
            })?;
            ensure_thumbnail_exists(&video_for_task, t, &out_path).await?;
            Ok::<ThumbnailEntry, AppError>(ThumbnailEntry {
                t_seconds: t,
                file_path: out_path.to_string_lossy().to_string(),
            })
        });
    }

    let results = join_all(tasks).await;
    let mut entries = Vec::with_capacity(results.len());
    for r in results {
        entries.push(r?);
    }
    Ok(entries)
}

/// #465 -- spawn ffmpeg to materialise a single thumbnail unless the cache
/// file is already present and non-empty. On any non-zero exit, the stderr
/// is folded into the returned error so the GUI can surface it.
async fn ensure_thumbnail_exists(
    video_path: &Path,
    t_seconds: f64,
    out_path: &Path,
) -> Result<(), AppError> {
    if let Ok(meta) = fs::metadata(out_path) {
        if meta.is_file() && meta.len() > 0 {
            return Ok(());
        }
    }
    if let Some(parent) = out_path.parent() {
        if !parent.exists() {
            fs::create_dir_all(parent).map_err(|e| {
                AppError::new(
                    "io.write_failed",
                    format!("create dir {} failed: {}", parent.display(), e),
                )
                .with_default_hint()
            })?;
        }
    }

    let t_arg = format!("{:.3}", t_seconds.max(0.0));
    let mut cmd = tokio::process::Command::new("ffmpeg");
    cmd.arg("-y")
        .arg("-ss")
        .arg(&t_arg)
        .arg("-i")
        .arg(video_path)
        .arg("-frames:v")
        .arg("1")
        .arg("-vf")
        .arg("scale=160:90")
        .arg("-q:v")
        .arg("80")
        .arg("-f")
        .arg("webp")
        .arg("-loglevel")
        .arg("error")
        .arg(out_path);
    process_util::apply_no_window(&mut cmd);
    let output = cmd.output().await.map_err(|e| {
        AppError::new(
            "subprocess.spawn_failed",
            format!("spawn ffmpeg failed at t={}: {}", t_arg, e),
        )
        .with_default_hint()
    })?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(AppError::new(
            "subprocess.exit_failed",
            format!(
                "ffmpeg failed at t={} (exit={:?}): {}",
                t_arg,
                output.status.code(),
                stderr.trim()
            ),
        )
        .with_default_hint());
    }
    Ok(())
}

/// #645 -- response payload of `extract_brightness_window`. `samples` is the
/// per-frame average brightness in `[0.0, 255.0]` (gray plane byte averaged
/// across a 320x180 downscaled frame). `t_start` / `t_end` / `fps` echo the
/// **requested** values so the frontend can correlate the response with the
/// issuing FrameStrip overlay call site without trusting only the call ordering.
///
/// Note on the `t_start` echo: if the request had `t_start < 0` the helper
/// clamps the ffmpeg `-ss` argument to `0.0`, but the response still echoes
/// the original (negative) `t_start`. PreviewScreen passes the active
/// editing position (currentT) minus 3 seconds, so this only matters for
/// boundaries within the first 3 seconds of a video (rare for FL matches).
/// Consumers that may receive `t_start < 0` should treat the actual sample
/// window as `[max(0.0, t_start), t_end]`.
#[derive(Debug, Clone, Serialize)]
pub struct BrightnessWindow {
    pub samples: Vec<f64>,
    pub t_start: f64,
    pub t_end: f64,
    pub fps: f64,
}

/// #645 -- extract per-frame average brightness for a `[t_start, t_end]`
/// window of `video_path` at the requested `fps`. Used by the PreviewScreen
/// FrameStrip brightness overlay (±3s zoom around currentT): the frontend
/// invokes this on selectedMatch / currentT change (200ms debounced) and
/// renders the returned `samples` as a semi-transparent SVG overlay
/// (waveform + threshold + blackout band) on top of the candidate frame
/// thumbnails.
///
/// **Why on-demand instead of reading `metadata.brightness_samples`**:
/// the existing pipeline-wide samples cap at 512 for the entire video,
/// which is too sparse for a ±3s zoom (we need ~60 samples in 6 s).
/// Sampling on demand at 10 fps gives the right density without bloating
/// `metadata.json`.
///
/// **ffmpeg invocation**: `ffmpeg -ss {t_start} -i {video} -t {dur}
/// -vf fps={fps},scale=320:180,format=gray -f rawvideo -`. stdout is a
/// concatenation of `320 * 180 = 57600`-byte gray frames; we average each
/// frame's bytes to a single `f64`. Any trailing partial frame (stdout len
/// not a multiple of `FRAME_BYTES`) is implicitly dropped by the integer
/// chunk iteration.
///
/// `pub` (not `pub(crate)`) so the integration test under
/// `gui/src-tauri/tests/extract_brightness_window.rs` can invoke this
/// helper directly without going through the Tauri command runtime. The
/// Tauri command `extract_brightness_window` below stays private and is
/// registered via `tauri::generate_handler!`.
pub async fn extract_brightness_window_impl(
    video_path: String,
    t_start: f64,
    t_end: f64,
    fps: f64,
) -> Result<BrightnessWindow, AppError> {
    const WIDTH: usize = 320;
    const HEIGHT: usize = 180;
    const FRAME_BYTES: usize = WIDTH * HEIGHT; // 57600

    let t_start_clamped = t_start.max(0.0);
    let duration = (t_end - t_start_clamped).max(0.0);
    let ss_arg = format!("{:.3}", t_start_clamped);
    let dur_arg = format!("{:.3}", duration);
    let fps_arg = format!("{}", fps);
    let vf_arg = format!("fps={fps_arg},scale={WIDTH}:{HEIGHT},format=gray");

    let mut cmd = tokio::process::Command::new("ffmpeg");
    cmd.arg("-ss")
        .arg(&ss_arg)
        .arg("-i")
        .arg(&video_path)
        .arg("-t")
        .arg(&dur_arg)
        .arg("-vf")
        .arg(&vf_arg)
        .arg("-f")
        .arg("rawvideo")
        .arg("-loglevel")
        .arg("error")
        .arg("-")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    process_util::apply_no_window(&mut cmd);
    let output = cmd.output().await.map_err(|e| {
        AppError::new(
            "subprocess.spawn_failed",
            format!("ffmpeg spawn failed: {e}"),
        )
        .with_default_hint()
    })?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(AppError::new(
            "subprocess.exit_failed",
            format!(
                "ffmpeg failed (exit {:?}) extracting brightness window [{}, {}] @ {} fps: {}",
                output.status.code(),
                ss_arg,
                t_end,
                fps_arg,
                stderr.trim()
            ),
        )
        .with_default_hint());
    }

    let samples: Vec<f64> = output
        .stdout
        .chunks_exact(FRAME_BYTES)
        .map(|frame| {
            let sum: u64 = frame.iter().map(|&b| b as u64).sum();
            sum as f64 / FRAME_BYTES as f64
        })
        .collect();

    Ok(BrightnessWindow {
        samples,
        t_start,
        t_end,
        fps,
    })
}

/// #645 -- Tauri command wrapper around `extract_brightness_window_impl`.
/// Private; surface to the frontend through `tauri::generate_handler!` only.
#[tauri::command]
async fn extract_brightness_window(
    video_path: String,
    t_start: f64,
    t_end: f64,
    fps: f64,
) -> Result<BrightnessWindow, AppError> {
    extract_brightness_window_impl(video_path, t_start, t_end, fps).await
}

/// #523 -- tracker for long-running external processes (detecting /export
/// ffmpeg invocations). Phase 3 preview itself does not spawn persistent
/// children, but detecting (Phase 3) and export (Phase 4) will register
/// their children here so the Close-Requested handler can kill them before
/// exit.
///
/// #756 -- value type is [`TrackedChild`], which carries both the
/// `tokio::process::Child` and an optional Windows Job Object handle. The
/// Job is only populated for `start_detect` (the Python CLI spawns N
/// ffmpeg descendants that `TerminateProcess` cannot reach); other spawn
/// sites pass `job: None`. Dropping the `TrackedChild` (on
/// `kill_tracked_processes` drain) drops the Job handle, which fires
/// `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` and reaps the whole tree.
pub struct TrackedChild {
    pub child: tokio::process::Child,
    #[cfg(windows)]
    #[allow(dead_code)] // held purely for its Drop side effect
    pub job: Option<process_util::job_object::ProcessJob>,
}

impl TrackedChild {
    /// Wrap a freshly-spawned child with no Job Object association.
    /// Use this at spawn sites that have no descendants to reap (ffmpeg /
    /// ffprobe single invocations).
    pub fn no_job(child: tokio::process::Child) -> Self {
        Self {
            child,
            #[cfg(windows)]
            job: None,
        }
    }
}

type ProcessMap = Arc<Mutex<HashMap<Uuid, TrackedChild>>>;

static PROCESS_TRACKER: OnceLock<ProcessMap> = OnceLock::new();

fn process_tracker() -> &'static ProcessMap {
    PROCESS_TRACKER.get_or_init(|| Arc::new(Mutex::new(HashMap::new())))
}

/// #523 -- report whether any child process is currently being tracked.
/// Called by the frontend when it receives a `close-requested` event so it
/// can decide whether to show the confirm modal or let the window close.
#[tauri::command]
async fn is_process_running() -> bool {
    let tracker = process_tracker();
    let guard = tracker.lock().await;
    !guard.is_empty()
}

/// #523 -- kill every tracked child. Returns the number of processes that
/// were alive at kill time. Best-effort -- already-dead children are silently
/// skipped so partial kills don't block the exit flow.
///
/// #756 -- for entries whose [`TrackedChild`] carries a `Job` (currently
/// only `start_detect`), `child.kill().await` terminates the direct child
/// (Python CLI) and the implicit drop of the Job at the end of the loop
/// iteration fires `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, terminating every
/// ffmpeg descendant the Python CLI had spawned. Entries with `job =
/// None` (export ffmpeg, etc.) behave exactly as before.
#[tauri::command]
async fn kill_tracked_processes() -> Result<u32, AppError> {
    let tracker = process_tracker();
    let mut guard = tracker.lock().await;
    let count = guard.len() as u32;
    for (_, mut tracked) in guard.drain() {
        // Kill the direct child first; the Job handle drop below (when
        // `tracked` goes out of scope at the end of this loop iteration)
        // reaps the descendant tree on Windows. Doing both is intentional
        // belt-and-suspenders: `child.kill()` is platform-portable and
        // also handles the non-Windows case where `job` is absent.
        let _ = tracked.child.kill().await;
    }
    Ok(count)
}

/// #523 -- explicit app exit, used after the user confirms they want to
/// terminate a running process. `on_window_event` always calls
/// `prevent_close`, so the frontend must drive the actual exit through this
/// command once it has finished cleanup.
///
/// #465 review: WebView2 / Chromium の cleanup race を緩和するため、各
/// webview window の `WindowEvent::Destroyed` を oneshot で待ってから
/// `app.exit(0)` を呼ぶ。何もしないと shutdown 時に
///   `[ERROR:ui\gfx\win\window_impl.cc] Failed to unregister class
///    Chrome_WidgetWin_0. Error = 1412`
/// が stderr に出る (Error 1412 = ERROR_CLASS_DOES_NOT_EXIST、Chromium の
/// window class registration が既に消えている race)。`destroy()` で
/// `on_window_event` の `prevent_close` を bypass し、Tauri レベルの
/// `Destroyed` を確認してから exit する。
///
/// **限界**: Tauri レベルの `Destroyed` は WebView2 内部の window class
/// unregister 完了より先に fire するため、これを待っても 1412 を完全に
/// は防げない (Chromium 内部の race は依然残る)。ただし固定 sleep より
/// 厳密で、destroy 後の最低保証になる。500ms timeout fallback で永久
/// 待ちは回避する。
#[tauri::command]
async fn force_exit_app(app: tauri::AppHandle) {
    use std::sync::{Arc, Mutex};
    use tokio::sync::oneshot;

    let windows: Vec<_> = app.webview_windows().into_values().collect();
    if windows.is_empty() {
        app.exit(0);
        return;
    }

    let mut signals = Vec::with_capacity(windows.len());
    for window in &windows {
        let (tx, rx) = oneshot::channel::<()>();
        // `on_window_event` callback may be re-invoked, so wrap the sender
        // in `Option<Arc<Mutex>>` and `take()` it on first Destroyed.
        let tx = Arc::new(Mutex::new(Some(tx)));
        let tx_clone = Arc::clone(&tx);
        window.on_window_event(move |event| {
            if matches!(event, tauri::WindowEvent::Destroyed) {
                if let Ok(mut guard) = tx_clone.lock() {
                    if let Some(sender) = guard.take() {
                        let _ = sender.send(());
                    }
                }
            }
        });
        signals.push(rx);
    }

    for window in &windows {
        let _ = window.destroy();
    }

    // 500ms timeout で hang 回避。通常は数 ms 以内に Destroyed が fire する。
    let _ = tokio::time::timeout(
        std::time::Duration::from_millis(500),
        join_all(signals),
    )
    .await;

    app.exit(0);
}

/// #466 -- progress event emitted on channel `export-progress`. One event
/// per ffmpeg `out_time_ms` line during encoding, plus a terminal
/// `stage="done"` on success or `stage="error"` on failure.
///
/// #591 -- a `stage="fallback"` event is emitted exactly once when a GPU
/// encoder (NVENC / QSV / AMF) initialisation fails and the export
/// retries with libx264. `fallback_from` carries a human-readable trace
/// (e.g. `"h264_nvenc -> libx264"`) for the frontend notice.
#[derive(Debug, serde::Serialize, Clone)]
pub struct ExportProgress {
    pub match_index: u32,
    pub percent: f64,
    pub stage: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub fallback_from: Option<String>,
}

/// #466 review #4: 出力先の親ディレクトリが存在することを検証する。
///
/// 以前は `start_export` 内で `create_dir_all` を呼んでいたが、ユーザーが
/// タイポしたパスに静かにディレクトリツリーが作られて混乱を招くため、
/// 明示拒否に変更した。ディレクトリ作成はユーザーが事前に行う前提。
///
/// `output_path` がルート / 親なし (file_name only など) の場合は no-op で
/// Ok を返す (現在のディレクトリを意味すると解釈)。
///
/// `start_export` subprocess 経路に移行後、本関数の呼び出し元は tests のみ。
/// #[cfg(test)] で test ビルドのみに限定し dead_code 警告を抑止。
#[cfg(test)]
fn validate_output_parent_exists(output_path: &Path) -> Result<(), AppError> {
    if let Some(parent) = output_path.parent() {
        if !parent.as_os_str().is_empty() && !parent.exists() {
            return Err(AppError::new(
                "io.file_not_found",
                format!("output directory does not exist: {}", parent.display()),
            )
            .with_default_hint());
        }
    }
    Ok(())
}

/// `open_folder_in_explorer` の path 検証ロジックを spawn から分離した
/// 単体テスト用ヘルパ。
///
/// - 存在しない path は明示エラー
/// - 非 Windows 環境では unsupported エラー
/// - 上記をパスしたら Ok (caller は spawn を試みる)
fn validate_open_folder_request(path: &str) -> Result<(), AppError> {
    if !Path::new(path).exists() {
        return Err(AppError::new(
            "io.file_not_found",
            format!("path does not exist: {}", path),
        )
        .with_default_hint());
    }
    #[cfg(not(target_os = "windows"))]
    {
        return Err(AppError::new(
            "platform.unsupported",
            "open_folder_in_explorer is only supported on Windows",
        )
        .with_default_hint());
    }
    #[cfg(target_os = "windows")]
    {
        Ok(())
    }
}

/// `path` をプラットフォーム固有のファイルマネージャ (Windows: explorer.exe)
/// で開く。
///
/// 旧実装は `tauri-plugin-shell` の `open` を使っていたが、`shell:allow-open`
/// permission の default scope が URL (`mailto:` / `tel:` / `https?://`) しか
/// 許可せず、ローカル path は `Scoped command argument failed regex
/// validation` で reject される。`open` の scope を path 許可に拡張する代わ
/// りに、Windows の `explorer.exe` を直接 spawn する独自 command を用意して
/// 確実に動かす (#545 review、2026-04-25)。
///
/// **#727 (2026-05-13)**: 元 `std::process::Command` から `tokio::process::Command`
/// に切り替え、lib.rs 内 spawn site (probe_video_with / ensure_thumbnail_exists
/// / start_detect / start_export / enumerate_h264_encoders /
/// extract_brightness_window_impl / 本関数) を `tokio::process::Command` 系で
/// 統一する refactor (gui spawn 統一)。
///
/// **apply_no_window 非適用**: explorer.exe は Win32 GUI subsystem アプリで
/// そもそも console window を生成しないため、`process_util::apply_no_window`
/// (= CREATE_NO_WINDOW flag) の purpose (windows_subsystem="windows" 親で
/// release 時の console 割当抑止) と一致しない。本関数は `process_util/mod.rs`
/// adoption test (`lib_rs_applies_apply_no_window_at_all_spawn_sites`) の検査
/// 対象外として扱う。
///
/// **PROCESS_TRACKER 非登録**: explorer.exe はユーザーの file manager UI
/// であり、本 app が close されても残るべき。`track_child` を呼ばないことで
/// `kill_tracked_processes` (CloseRequested flow #523) の影響を受けない。
///
/// Windows のみ対応 (CLAUDE.md に「対応プラットフォーム: Windows のみ」と
/// 明記)。将来 Linux / macOS 対応する際は `xdg-open` / `open` で分岐する。
#[tauri::command]
async fn open_folder_in_explorer(path: String) -> Result<(), AppError> {
    validate_open_folder_request(&path)?;

    #[cfg(target_os = "windows")]
    {
        // #727 -- spawn explorer.exe via tokio::process::Command for parity
        // with the other spawn sites (probe_video_with /
        // ensure_thumbnail_exists / start_detect / start_export /
        // enumerate_h264_encoders / extract_brightness_window_impl). The
        // returned Child is dropped
        // immediately: explorer.exe is the user's file manager UI and should
        // outlive this Tauri app; Windows has no zombie process model so
        // the drop is safe.
        tokio::process::Command::new("explorer.exe")
            .arg(&path)
            .spawn()
            .map_err(|e| {
                AppError::new(
                    "subprocess.spawn_failed",
                    format!("failed to launch explorer: {}", e),
                )
                .with_default_hint()
            })?;
    }

    Ok(())
}

/// #466 -- insert a spawned ffmpeg child into the global PROCESS_TRACKER so
/// the CloseRequested flow (#523) can kill it on app exit. Returns the UUID
/// used as the map key; the caller must pass it back to `untrack_child` on
/// process completion.
///
/// #756 -- the value type is now [`TrackedChild`] (child + optional Job
/// Object handle). Callers that don't need tree-kill protection should
/// pass `TrackedChild::no_job(child)`; only `start_detect` builds a Job
/// and passes `TrackedChild { child, job: Some(job) }`.
async fn track_child(tracked: TrackedChild) -> Uuid {
    let tracker = process_tracker();
    let mut guard = tracker.lock().await;
    let id = Uuid::new_v4();
    guard.insert(id, tracked);
    id
}

/// #466 -- remove a tracked child from PROCESS_TRACKER. Returns the child
/// so the caller can still `.wait()` / `.kill()` it outside the tracker
/// lock. Returns None if the entry was already drained (e.g. by
/// `kill_tracked_processes`).
///
/// #756 -- discards the Job Object handle (if any) when extracting the
/// child. On the **happy path** (process completed normally and we now
/// want to `.wait()` it) the Python CLI has already exited, so the Job is
/// empty and dropping the handle is a no-op. On the **cancellation path**
/// `untrack_child` returns `None` because `kill_tracked_processes` has
/// already drained the tracker (dropping both the child and the Job),
/// fire-ing tree kill via `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`.
async fn untrack_child(id: Uuid) -> Option<tokio::process::Child> {
    let tracker = process_tracker();
    let mut guard = tracker.lock().await;
    guard.remove(&id).map(|tracked| tracked.child)
}

/// #466 -- parse a single ffmpeg `-progress` line. ffmpeg emits key=value
/// lines once per second (out_time, out_time_ms, speed, bitrate, ...) and
/// a terminal `progress=end` or `progress=continue`. We only care about
/// `out_time_ms` (for the percent bar) and `progress=end` (for the terminal
/// event). Returns None for every other key.
///
/// Task 12 で `run_ffmpeg_export_attempt` を削除後、呼び出し元は tests のみ。
/// #[cfg(test)] で test ビルドのみに限定し dead_code 警告を抑止。
#[cfg(test)]
fn parse_progress_line(line: &str) -> Option<ProgressSignal> {
    let line = line.trim();
    if let Some(rest) = line.strip_prefix("out_time_ms=") {
        rest.trim().parse::<i64>().ok().map(ProgressSignal::OutTimeMs)
    } else if let Some(rest) = line.strip_prefix("out_time_us=") {
        // Newer ffmpeg builds emit out_time_us instead of out_time_ms even
        // though the unit is still microseconds. Accept both so we don't
        // miss progress on future releases.
        rest.trim().parse::<i64>().ok().map(ProgressSignal::OutTimeMs)
    } else if line == "progress=end" {
        Some(ProgressSignal::End)
    } else {
        None
    }
}

/// #466 -- internal enum for parsed progress lines.
///
/// Task 12 で `run_ffmpeg_export_attempt` を削除後、参照元は tests のみ。
/// #[cfg(test)] で test ビルドのみに限定し dead_code 警告を抑止。
#[cfg(test)]
#[derive(Debug, PartialEq)]
enum ProgressSignal {
    /// ffmpeg's `out_time_ms` is actually in microseconds (the name is a
    /// historical artifact). Caller must divide by 1_000_000 to get seconds.
    OutTimeMs(i64),
    End,
}

/// #466 -- keep the last `max_bytes` bytes of `buf` as a UTF-8 lossy
/// string. Used so the error message returned to the frontend stays
/// bounded even if ffmpeg dumps pages of diagnostics.
///
/// Task 12 で `run_ffmpeg_export_attempt` を削除後、呼び出し元は tests のみ。
/// #[cfg(test)] で test ビルドのみに限定し dead_code 警告を抑止。
#[cfg(test)]
fn tail_string(buf: &[u8], max_bytes: usize) -> String {
    let start = buf.len().saturating_sub(max_bytes);
    String::from_utf8_lossy(&buf[start..]).trim().to_string()
}

/// #569 -- detect command parameters surfaced from the GUI's drop screen.
///
/// All fields are optional so the frontend can pass only the controls
/// the user adjusted; missing values are translated into "use the CLI
/// default" by leaving the corresponding `--option` off the argv.
#[derive(Debug, Default, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DetectParams {
    pub blackout_threshold: Option<f64>,
    pub min_blackout_duration: Option<f64>,
    pub min_match_duration: Option<f64>,
    pub workers: Option<u32>,
    pub no_audio: Option<bool>,
    pub no_cache: Option<bool>,
    /// `Some(true)` -> `--gpu`, `Some(false)` -> `--no-gpu`, `None` -> auto.
    pub gpu: Option<bool>,
    pub gpu_vendor: Option<String>,
}

/// #569 -- one progress event emitted on channel `detect-progress`.
///
/// The shape mirrors the CLI's JSON-line schema (see
/// `allaganeye/detection/progress_emitter.py`).  Optional fields are
/// `None` when the CLI omitted them from the wire payload (the emitter
/// drops `None`-valued extras at the source so the frontend doesn't
/// have to disambiguate `null` vs absent).
#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct DetectProgress {
    pub phase: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub completed: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub total: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub elapsed_s: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub eta_s: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub blackout_frames: Option<u64>,
    /// On the terminal `phase="done"` event the CLI sets this to the
    /// path of the freshly-written metadata.json so the frontend can
    /// `load_metadata` it without deriving the path itself.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub metadata_path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub matches: Option<u64>,
    /// Free-form context (e.g. CLI stderr tail on `phase="error"`).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message: Option<String>,
    /// Probing phase: video duration in seconds.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub duration_s: Option<f64>,
    /// Probing phase: video width in pixels.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub width: Option<u32>,
    /// Probing phase: video height in pixels.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub height: Option<u32>,
    /// Probing phase: video frame rate.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub fps: Option<f64>,
    /// Probing phase: video codec (h264 / hevc / ...).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub codec: Option<String>,
    /// `chunk_dispatch` phase: number of decode chunks pending.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub chunks: Option<u32>,
    /// `cache_hit` phase: number of boundaries restored from cache.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub boundaries: Option<u32>,
    /// `start` phase: source video path (echoes the request).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub source: Option<String>,
    /// #813 -- detect run identifier echoed back to the frontend on every
    /// event so the listener can fence out stragglers from a previous
    /// (cancelled) run. The CLI never emits this; `start_detect` injects it
    /// via `stamp_run_id` on every `detect-progress` emit.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub run_id: Option<String>,
}

/// #569 -- terminal payload returned to the frontend when detect finishes.
///
/// The frontend reads `metadata_path` and calls `load_metadata` to populate
/// the complete screen.
#[derive(Debug, Clone, Serialize)]
pub struct DetectResult {
    pub metadata_path: String,
    pub matches: u64,
}

/// #648 -- truncate `line` to at most `max_chars` Unicode chars and escape
/// non-printable control characters (except `\t` / `\n` / `\r`) as `\xNN`
/// so they don't inject terminal escape sequences into stderr.
fn truncate_and_escape(line: &str, max_chars: usize) -> String {
    line.chars()
        .take(max_chars)
        .map(|c| match c {
            '\t' | '\n' | '\r' => c.to_string(),
            c if (c as u32) < 0x20 => format!("\\x{:02X}", c as u32),
            c => c.to_string(),
        })
        .collect()
}

/// #569 -- pure parser for one JSON-lines progress event.  Returns
/// `None` for blank lines or lines that fail to deserialize so a stray
/// stdout write from the CLI doesn't break the overall stream.
///
/// #648 -- malformed JSON (non-empty / non-whitespace lines that fail to
/// deserialize) は silent skip ではなく `eprintln!` で warn 出力するよう
/// 拡張済。空行 / 空白のみ行 (LF flush 等で発生) は引き続き silent skip。
/// public signature は変えていない (戻り値も呼び出し側も既存通り)。
fn parse_detect_progress_line(line: &str) -> Option<DetectProgress> {
    parse_detect_progress_line_with_warn(line, |msg| eprintln!("{}", msg))
}

/// #648 -- testable variant: takes a `on_warn` closure to capture warn
/// output, so cargo test can assert on the warning content without
/// touching the real stderr stream. Production wrapper above passes
/// `eprintln!`.
fn parse_detect_progress_line_with_warn(
    line: &str,
    mut on_warn: impl FnMut(&str),
) -> Option<DetectProgress> {
    let trimmed = line.trim();
    if trimmed.is_empty() {
        return None;
    }
    match serde_json::from_str(trimmed) {
        Ok(p) => Some(p),
        Err(_) => {
            let escaped = truncate_and_escape(trimmed, 64);
            on_warn(&format!(
                "[parse_detect_progress_line] malformed JSON (len={}): \"{}\"",
                trimmed.len(),
                escaped,
            ));
            None
        }
    }
}

/// #646 -- how to invoke the `allaganeye` CLI from Rust.
///
/// Wraps the executable plus any prefix arguments (e.g. `-m allaganeye`
/// when the executable is `python`) plus an optional working directory
/// (e.g. the worktree root for the `python -m` fallback so the
/// development checkout's `allaganeye/` package is on `sys.path`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AllaganeyeCommand {
    pub program: String,
    pub prefix_args: Vec<String>,
    pub cwd: Option<PathBuf>,
}

/// #569 / #646 -- resolve how to invoke the `allaganeye` CLI.
///
/// Resolution order:
/// 1. `ALLAGANEYE_BIN` env var (override / escape hatch). Single
///    executable path, no prefix args, no cwd.
/// 2. `<bundle_resource_dir>/allaganeye.bat` (Portable ZIP production
///    path, #615). Resource dir is the directory the Tauri bundle
///    extracted to; we look for the same `allaganeye.bat` the ZIP
///    layout ships with.
/// 3. `python -m allaganeye` fallback so `npm run tauri dev` works
///    in a fresh worktree without `pip install -e .` and without
///    setting `ALLAGANEYE_BIN`. `cwd` is the nearest ancestor of
///    `current_dir()` that contains `pyproject.toml`, ensuring the
///    worktree's `allaganeye/` package is the first match on
///    `sys.path[0]` (cwd injected by Python `-m`).
fn resolve_allaganeye_command(app: &tauri::AppHandle) -> AllaganeyeCommand {
    if let Some(cmd) = resolve_from_env(std::env::var("ALLAGANEYE_BIN").ok()) {
        return cmd;
    }
    if let Ok(resource_dir) = app.path().resource_dir() {
        if let Some(cmd) = resolve_from_resource_dir(&resource_dir) {
            return cmd;
        }
    }
    resolve_python_fallback(find_worktree_root(std::env::current_dir().ok()))
}

/// Test helper: resolve from the `ALLAGANEYE_BIN` env var value (if any).
/// Returns `None` for missing / empty env var so the caller can fall
/// through to the next stage.
fn resolve_from_env(env_value: Option<String>) -> Option<AllaganeyeCommand> {
    let path = env_value?;
    if path.is_empty() {
        return None;
    }
    Some(AllaganeyeCommand {
        program: path,
        prefix_args: vec![],
        cwd: None,
    })
}

/// Test helper: resolve from a Tauri bundle resource directory by
/// looking for `allaganeye.bat`. Returns `None` when the bat is
/// absent so dev builds fall through to the python fallback.
fn resolve_from_resource_dir(resource_dir: &Path) -> Option<AllaganeyeCommand> {
    let bat = resource_dir.join("allaganeye.bat");
    if bat.exists() {
        Some(AllaganeyeCommand {
            program: bat.to_string_lossy().to_string(),
            prefix_args: vec![],
            cwd: None,
        })
    } else {
        None
    }
}

/// Test helper: build the `python -m allaganeye` fallback command.
/// `cwd` is whatever the caller decided is the worktree root (or
/// `None` if no anchor was found, in which case Python's import
/// machinery still finds globally-installed packages).
fn resolve_python_fallback(cwd: Option<PathBuf>) -> AllaganeyeCommand {
    AllaganeyeCommand {
        program: "python".to_string(),
        prefix_args: vec!["-m".to_string(), "allaganeye".to_string()],
        cwd,
    }
}

/// Test helper: walk the ancestors of `start` looking for the
/// directory that holds `pyproject.toml`. Returns `None` for
/// missing `start` or no anchor in the chain (e.g. when invoked
/// outside the worktree, in which case the python fallback runs
/// without `cwd` override).
fn find_worktree_root(start: Option<PathBuf>) -> Option<PathBuf> {
    let start = start?;
    for ancestor in start.ancestors() {
        if ancestor.join("pyproject.toml").exists() {
            return Some(ancestor.to_path_buf());
        }
    }
    None
}

/// #813 -- stamp the active detect run's id onto a progress event before
/// emitting it. Centralises the injection so every `detect-progress` emit
/// in `start_detect` carries the run id and the frontend can drop
/// stragglers from a previous run (audit P1-1).
fn stamp_run_id(mut progress: DetectProgress, run_id: &str) -> DetectProgress {
    progress.run_id = Some(run_id.to_string());
    progress
}

/// #813 (iterate-review #4) -- the single sink for `detect-progress` events
/// out of `start_detect`. Routing every emit through here guarantees the run
/// id is stamped exactly once, so a future emit path can't silently bypass
/// the frontend's run-id fence (the same "new code path forgets a required
/// wiring step" failure class that bit detection cache keys). Do NOT call
/// `app.emit("detect-progress", ...)` directly -- always use this.
fn emit_detect_progress(app: &tauri::AppHandle, run_id: &str, progress: DetectProgress) {
    let _ = app.emit("detect-progress", stamp_run_id(progress, run_id));
}

/// #569 -- assemble argv for `allaganeye detect --progress-format json`.
/// Pulled out of `start_detect` so unit tests can pin flag ordering and
/// the plumbing of optional `DetectParams` -> CLI flags without spawning
/// a subprocess.
fn detect_command_args(
    video_path: &str,
    output_dir: &str,
    params: &DetectParams,
) -> Vec<String> {
    let mut args: Vec<String> = vec![
        "detect".to_string(),
        video_path.to_string(),
        "-o".to_string(),
        output_dir.to_string(),
        "--progress-format".to_string(),
        "json".to_string(),
    ];
    if let Some(v) = params.blackout_threshold {
        args.push("--blackout-threshold".to_string());
        args.push(format!("{v}"));
    }
    if let Some(v) = params.min_blackout_duration {
        args.push("--min-blackout-duration".to_string());
        args.push(format!("{v}"));
    }
    if let Some(v) = params.min_match_duration {
        args.push("--min-match-duration".to_string());
        args.push(format!("{v}"));
    }
    if let Some(v) = params.workers {
        args.push("--workers".to_string());
        args.push(format!("{v}"));
    }
    if params.no_audio.unwrap_or(false) {
        args.push("--no-audio".to_string());
    }
    if params.no_cache.unwrap_or(false) {
        args.push("--no-cache".to_string());
    }
    match params.gpu {
        Some(true) => args.push("--gpu".to_string()),
        Some(false) => args.push("--no-gpu".to_string()),
        None => {}
    }
    if let Some(vendor) = params.gpu_vendor.as_deref() {
        if !vendor.is_empty() {
            args.push("--gpu-vendor".to_string());
            args.push(vendor.to_string());
        }
    }
    args
}

/// #569 -- spawn `allaganeye detect --progress-format json` and stream
/// progress events to the frontend.
///
/// The child is registered with [`process_tracker`] so the
/// `CloseRequested` window-close flow (#523) and the user-pressed cancel
/// button on the detecting screen (#813) can kill it.  On cancel the
/// frontend invokes `kill_tracked_processes`, which drains the tracker and
/// drops this child's Job handle (tree-killing the Python CLI + ffmpeg
/// descendants, #756); the `untrack_child` below then returns `None`, so we
/// emit a `cancelled` event and return `subprocess.cancelled`.
#[tauri::command]
async fn start_detect(
    app: tauri::AppHandle,
    video_path: String,
    output_dir: String,
    params: DetectParams,
    run_id: String,
) -> Result<DetectResult, AppError> {
    let video = PathBuf::from(&video_path);
    if !video.exists() {
        return Err(AppError::new(
            "io.file_not_found",
            format!("video file not found: {}", video.display()),
        )
        .with_default_hint());
    }
    let output_buf = PathBuf::from(&output_dir);
    if let Err(e) = fs::create_dir_all(&output_buf) {
        return Err(AppError::new(
            "io.write_failed",
            format!(
                "create output dir failed ({}): {}",
                output_buf.display(),
                e
            ),
        )
        .with_default_hint());
    }

    let cmd_spec = resolve_allaganeye_command(&app);
    let detect_args = detect_command_args(&video_path, &output_dir, &params);

    let mut cmd = tokio::process::Command::new(&cmd_spec.program);
    for a in &cmd_spec.prefix_args {
        cmd.arg(a);
    }
    for a in &detect_args {
        cmd.arg(a);
    }
    // #646 review Round 4 補足 #8 -- cwd は `python -m allaganeye`
    // fallback のみで `Some(...)` になり、`find_worktree_root` で見つけた
    // worktree root を anchor して `sys.path[0]` 経由で `allaganeye` パッケージ
    // を import 可能にするためだけに設定する。Python 側 (allaganeye/ 配下)
    // は video_path / output_dir を絶対 path で受けるため現状は cwd 非依存
    // で動く。将来 Python 側で cwd-relative path 解決を追加する場合は、
    // 本 fallback のときだけ cwd が worktree root になり挙動が静かに変わる
    // 可能性があるので注意。env / bundle 経路では `cwd = None` なので
    // OS デフォルト cwd で起動する。
    if let Some(cwd) = &cmd_spec.cwd {
        cmd.current_dir(cwd);
    }
    // #656 -- Windows の Python は default で `sys.stdout.encoding=cp932`
    // になるため、日本語含む path を JSON-line stream に乗せて出力すると
    // Rust 側 (UTF-8 前提の reader) で decode 失敗する。`PYTHONIOENCODING`
    // を `utf-8:replace` に固定して CLI 側 stdout/stderr を UTF-8 強制し、
    // encode 不能 byte は U+FFFD で置換する (PR #657 Python 側
    // `errors="replace"` と対称)。
    cmd.env("PYTHONIOENCODING", "utf-8:replace");
    cmd.stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    process_util::apply_no_window(&mut cmd);

    // #646 -- spawn failure messages need to surface the resolved
    // program (e.g. "python -m allaganeye") so the GUI error display
    // can hint at which stage of the resolution chain failed.
    let resolved_label = if cmd_spec.prefix_args.is_empty() {
        cmd_spec.program.clone()
    } else {
        format!("{} {}", cmd_spec.program, cmd_spec.prefix_args.join(" "))
    };
    let mut child = cmd
        .spawn()
        .map_err(|e| format!("spawn allaganeye failed ({}): {}", resolved_label, e))?;
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "failed to capture allaganeye stdout".to_string())?;
    let stderr = child
        .stderr
        .take()
        .ok_or_else(|| "failed to capture allaganeye stderr".to_string())?;

    // #756 -- attach Windows Job Object so cancelling detect reaps the
    // Python CLI plus the N ffmpeg children spawned by the GPU detector
    // (`gpu_detector.py`). On non-Windows this is a no-op (`job = None`).
    // Failure to create/assign the Job is downgraded to a warning: detect
    // proceeds without tree-kill protection rather than failing outright,
    // matching the existing `apply_no_window` defensive posture.
    #[cfg(windows)]
    let job: Option<process_util::job_object::ProcessJob> = {
        match process_util::job_object::ProcessJob::new() {
            Ok(j) => {
                if let Some(raw) = child.raw_handle() {
                    if let Err(e) = j.assign(raw) {
                        eprintln!(
                            "warning: AssignProcessToJobObject failed: {} \
                             (detect descendants may be orphaned on cancel)",
                            e
                        );
                    }
                } else {
                    // #756 review #2: surface unexpected None so a tokio
                    // contract change does not silently disable tree kill.
                    eprintln!(
                        "warning: child.raw_handle() returned None for detect \
                         spawn (detect descendants may be orphaned on cancel)"
                    );
                }
                Some(j)
            }
            Err(e) => {
                eprintln!(
                    "warning: CreateJobObject failed: {} \
                     (detect descendants may be orphaned on cancel)",
                    e
                );
                None
            }
        }
    };
    let tracked_id = track_child(TrackedChild {
        child,
        #[cfg(windows)]
        job,
    })
    .await;

    // Stderr drains in parallel into a bounded tail buffer so the OS
    // pipe doesn't fill up if the CLI is chatty under -v / verbose.
    // #656 -- avoid `lines()` for the same UTF-8 強制 reason as stdout
    // above. The tail is exposed only when the child exits non-zero, so
    // line semantics are not load-bearing -- we just need the trailing
    // bytes intact for the GUI error display.
    let stderr_handle = tokio::spawn(async move {
        let max_tail = 2048usize;
        let mut tail: Vec<u8> = Vec::with_capacity(4096);
        let mut reader = BufReader::new(stderr);
        let mut buf: Vec<u8> = Vec::with_capacity(1024);
        loop {
            buf.clear();
            match reader.read_until(b'\n', &mut buf).await {
                Ok(0) => break,
                Ok(_) => {
                    tail.extend_from_slice(&buf);
                    if tail.len() > max_tail * 2 {
                        let drop = tail.len() - max_tail;
                        tail.drain(0..drop);
                    }
                }
                Err(_) => break,
            }
        }
        tail
    });

    let mut metadata_path: Option<String> = None;
    let mut total_matches: u64 = 0;
    // #656 -- `AsyncBufReadExt::lines()` returns `String` and therefore
    // imposes strict UTF-8 decoding on the Python child's stdout. On
    // Windows the child's `sys.stdout.encoding` defaults to cp932 (or any
    // ANSI code page), so a JSON-line stream containing 日本語 path bytes
    // would kill the reader with `InvalidData`. We read raw bytes per
    // newline and apply `String::from_utf8_lossy` so any stray non-UTF-8
    // byte becomes U+FFFD instead of aborting the stream. `PYTHONIOENCODING
    // = utf-8:replace` set above is the primary fix; this is the defensive layer.
    let mut reader = BufReader::new(stdout);
    let mut line_buf: Vec<u8> = Vec::with_capacity(1024);

    loop {
        line_buf.clear();
        match reader.read_until(b'\n', &mut line_buf).await {
            Ok(0) => break,
            Ok(_) => {
                while matches!(line_buf.last(), Some(b'\n') | Some(b'\r')) {
                    line_buf.pop();
                }
                let line = String::from_utf8_lossy(&line_buf);
                if let Some(progress) = parse_detect_progress_line(&line) {
                    if progress.phase == "done" {
                        if let Some(ref p) = progress.metadata_path {
                            metadata_path = Some(p.clone());
                        }
                        if let Some(m) = progress.matches {
                            total_matches = m;
                        }
                    }
                    emit_detect_progress(&app, &run_id, progress);
                }
            }
            Err(e) => {
                // stdout pipe hiccup -- still try to wait the child so
                // we don't leak a zombie.  The error path below sets the
                // error event.
                let msg = format!("stdout read error: {e}");
                emit_detect_progress(
                    &app,
                    &run_id,
                    DetectProgress {
                        phase: "error".to_string(),
                        message: Some(msg.clone()),
                        ..Default::default()
                    },
                );
                break;
            }
        }
    }

    let mut child = match untrack_child(tracked_id).await {
        Some(c) => c,
        None => {
            // Drained by `kill_tracked_processes` -- treat as user cancel.
            emit_detect_progress(
                &app,
                &run_id,
                DetectProgress {
                    phase: "cancelled".to_string(),
                    ..Default::default()
                },
            );
            return Err(AppError::new("subprocess.cancelled", "detect cancelled").with_default_hint());
        }
    };

    let status = child
        .wait()
        .await
        .map_err(|e| format!("wait allaganeye failed: {e}"))?;
    let stderr_tail = stderr_handle.await.unwrap_or_default();

    if !status.success() {
        let tail = String::from_utf8_lossy(&stderr_tail).trim().to_string();
        let msg = if tail.is_empty() {
            format!("allaganeye exited with status {:?}", status.code())
        } else {
            format!(
                "allaganeye exited with status {:?}: {}",
                status.code(),
                tail
            )
        };
        emit_detect_progress(
            &app,
            &run_id,
            DetectProgress {
                phase: "error".to_string(),
                message: Some(msg.clone()),
                ..Default::default()
            },
        );
        return Err(AppError::new("subprocess.exit_failed", msg).with_default_hint());
    }

    let metadata_path = metadata_path.ok_or_else(|| {
        AppError::new(
            "internal.error",
            "detect completed but no metadata_path was emitted",
        )
        .with_default_hint()
    })?;

    Ok(DetectResult {
        metadata_path,
        matches: total_matches,
    })
}

/// #614 -- Returns the install-directory log path (`<install_dir>/logs`) so the
/// frontend ErrorModal can show the user where crash logs are written.
#[tauri::command]
fn get_log_dir() -> Result<String, AppError> {
    logging::log_dir()
        .map(|p| p.to_string_lossy().to_string())
        .map_err(|e| {
            AppError::new(
                "path.install_dir_unresolved",
                format!("could not resolve log dir: {}", e),
            )
            .with_default_hint()
        })
}

/// #614 -- Dev-only command that triggers a panic. Used by the frontend smoke
/// test (DevTools console: `await window.__aeInvoke('dev_force_panic')`) to
/// verify the panic hook + ErrorModal end-to-end. Symbol is absent in release
/// builds.
///
/// Must be `async`: a sync `tauri::command` runs through an `extern "C"`
/// boundary that does not allow unwinding, so a panic inside a sync command
/// triggers a secondary "panic in a function that cannot unwind" abort that
/// kills the process before the frontend can render the ErrorModal. async
/// commands run on the tokio runtime which catches the panic at the task
/// boundary, letting the WebView keep running.
#[cfg(debug_assertions)]
#[tauri::command]
async fn dev_force_panic() -> Result<(), AppError> {
    panic!("dev_force_panic invoked from frontend");
}

/// #669 -- Snapshot of `probe_environment_info` output. Sent to the frontend
/// where `formatSystemInfo()` (`gui/src/lib/systemInfo.ts`) renders it as the
/// `## 環境情報` section of the Markdown body that the ErrorModal
/// `[Issue 本文をコピー]` button writes to the clipboard. Combined with
/// `metadata.system_info` GPU vendor data at render time.
///
/// Snake-case field names match the existing `metadata.system_info` JSON
/// convention (see `gui/src/types/metadata.generated.ts::SystemInfo`).
///
/// Why a separate Tauri probe: the original spec/plan assumed
/// `metadata.system_info` already contained OS/CPU/Memory/Disk; in reality
/// the Python side only writes 3 GPU fields there (#669 plan revision).
#[derive(Debug, Clone, serde::Serialize)]
pub struct EnvironmentProbe {
    pub allaganeye_version: String,
    pub os_name: String,
    pub cpu_info: String,
    pub memory_total_gb: Option<f64>,
    pub disk_free_gb: Option<f64>,
    pub disk_total_gb: Option<f64>,
    pub disk_drive: Option<String>,
}

/// #669 -- Probes OS / CPU / Memory / Disk info via the `sysinfo` crate so
/// the ErrorModal `[Issue 本文をコピー]` button can fill the `bug_report.yml`
/// `## 環境情報` Markdown section with values matching the form's placeholder
/// format (`allaganeye 0.2.0 (Windows 11) / CPU: ... / Memory: ... GB`).
///
/// Disk metrics come from the disk that contains the install dir
/// (`<exe-parent>`). When that disk cannot be matched, all `disk_*` fields
/// are `None` (graceful — the caller renders a partial `environment` block).
///
/// Always succeeds (returns the struct directly, never `Result`); individual
/// optional fields fall back to `None` rather than failing the whole probe.
#[tauri::command]
fn probe_environment_info() -> EnvironmentProbe {
    probe_environment_info_inner()
}

/// Pure inner function (no Tauri wrapping) for unit testing.
fn probe_environment_info_inner() -> EnvironmentProbe {
    use sysinfo::{CpuRefreshKind, Disks, MemoryRefreshKind, RefreshKind, System};

    let allaganeye_version = env!("CARGO_PKG_VERSION").to_string();

    // OS name: prefer long_os_version() ("Microsoft Windows 11 ..."), then
    // fall back to "<name> <version>", then to std::env::consts::OS.
    let os_name = match System::long_os_version() {
        Some(s) if !s.trim().is_empty() => s.trim().to_string(),
        _ => match (System::name(), System::os_version()) {
            (Some(n), Some(v)) => format!("{} {}", n.trim(), v.trim())
                .trim()
                .to_string(),
            (Some(n), None) => n.trim().to_string(),
            _ => std::env::consts::OS.to_string(),
        },
    };

    // CPU + Memory
    let mut sys = System::new_with_specifics(
        RefreshKind::nothing()
            .with_cpu(CpuRefreshKind::nothing())
            .with_memory(MemoryRefreshKind::nothing().with_ram()),
    );
    sys.refresh_cpu_list(CpuRefreshKind::nothing());
    sys.refresh_memory();

    let cpus = sys.cpus();
    let logical = cpus.len();
    let cpu_brand = cpus.first().map(|c| c.brand().trim().to_string());
    let physical = System::physical_core_count();
    let cpu_info = match cpu_brand.as_deref() {
        Some(brand) if !brand.is_empty() => match physical {
            Some(p) if p != logical && logical > 0 => format!("{} ({}C/{}T)", brand, p, logical),
            _ if logical > 0 => format!("{} ({}T)", brand, logical),
            _ => brand.to_string(),
        },
        _ if logical > 0 => format!("{} threads", logical),
        _ => "(unknown CPU)".to_string(),
    };

    let total_mem_bytes = sys.total_memory();
    let memory_total_gb = if total_mem_bytes > 0 {
        Some(bytes_to_gb(total_mem_bytes))
    } else {
        None
    };

    // Disk: pick the disk whose mount_point is the longest prefix of the install dir
    let install_dir = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(std::path::Path::to_path_buf));
    let disks = Disks::new_with_refreshed_list();

    let (disk_free_gb, disk_total_gb, disk_drive) = match install_dir {
        Some(install) => {
            let best = disks
                .iter()
                .filter(|d| install.starts_with(d.mount_point()))
                .max_by_key(|d| d.mount_point().as_os_str().len());
            match best {
                Some(d) => (
                    Some(bytes_to_gb(d.available_space())),
                    Some(bytes_to_gb(d.total_space())),
                    Some(strip_trailing_separator(
                        &d.mount_point().to_string_lossy(),
                    )),
                ),
                None => (None, None, None),
            }
        }
        None => (None, None, None),
    };

    EnvironmentProbe {
        allaganeye_version,
        os_name,
        cpu_info,
        memory_total_gb,
        disk_free_gb,
        disk_total_gb,
        disk_drive,
    }
}

#[inline]
fn bytes_to_gb(bytes: u64) -> f64 {
    (bytes as f64) / (1024.0 * 1024.0 * 1024.0)
}

/// Strip a trailing `/` or `\` from a path string. Used for disk_drive so the
/// frontend can render `"E:"` (matching `bug_report.yml` placeholder `on E:`)
/// instead of the OS-native `"E:\\"`.
fn strip_trailing_separator(s: &str) -> String {
    let trimmed = s.trim_end_matches(['\\', '/']);
    if trimmed.is_empty() { s.to_string() } else { trimmed.to_string() }
}

/// #669 -- Returns the tail of the install-dir log file
/// (`<install_dir>/logs/error-YYYYMMDD.log`). Falls back to previous day's log
/// if today's is missing or empty. Returns `""` when neither today nor
/// yesterday has a log (not an error).
///
/// Used by the frontend ErrorModal's `[Issue 本文をコピー]` button to fill
/// the `## ログファイル (末尾抜粋)` section of the Markdown body it writes
/// to the clipboard.
#[tauri::command]
fn read_error_log_tail(line_count: usize) -> Result<String, AppError> {
    let log_dir = logging::log_dir().map_err(|e| {
        AppError::new(
            "path.install_dir_unresolved",
            format!("could not resolve log dir: {}", e),
        )
        .with_default_hint()
    })?;
    read_error_log_tail_inner(&log_dir, line_count)
}

/// Defense-in-depth upper bound for `read_error_log_tail`'s `line_count`
/// argument. The only current caller (`ErrorModal.tsx::LOG_TAIL_LINE_COUNT`)
/// hardcodes 300, so this cap is unreachable today, but it prevents future
/// callers (or a malicious extension reaching the Tauri IPC) from triggering
/// an allocation panic via `VecDeque::with_capacity(usize::MAX)`. The chosen
/// ceiling (10000) is far above any practical "log tail" use case yet small
/// enough to fit comfortably in memory.
const MAX_TAIL_LINES: usize = 10000;

/// Pure inner function for unit testing without log_dir() side effects. Tries
/// today's log first, then falls back to yesterday's. Returns `""` when both
/// are missing or empty (not an error). `line_count == 0` short-circuits to
/// `""` (avoids unbounded growth of the tail buffer); `line_count` greater
/// than `MAX_TAIL_LINES` is silently capped.
fn read_error_log_tail_inner(
    log_dir: &std::path::Path,
    line_count: usize,
) -> Result<String, AppError> {
    use std::collections::VecDeque;
    use std::io::{BufRead, BufReader};

    if line_count == 0 {
        return Ok(String::new());
    }
    // #669 -- /iterate-review Round 2 #2: defense-in-depth cap to avoid
    // `VecDeque::with_capacity(usize::MAX)` allocation panic if a future
    // caller forgets to bound the input.
    let line_count = line_count.min(MAX_TAIL_LINES);

    let today = logging::current_ymd_compact();
    let yesterday = logging::ymd_compact_yesterday();

    for date in [today, yesterday].iter() {
        let path = log_dir.join(format!("error-{}.log", date));
        if !path.exists() {
            continue;
        }
        let file = std::fs::File::open(&path).map_err(|e| {
            AppError::new("io.read_failed", format!("read log failed: {}", e))
                .with_default_hint()
        })?;
        let reader = BufReader::new(file);
        let mut tail: VecDeque<String> = VecDeque::with_capacity(line_count);
        for line in reader.lines() {
            let line = line.map_err(|e| {
                AppError::new("io.read_failed", format!("read line failed: {}", e))
                    .with_default_hint()
            })?;
            if tail.len() == line_count {
                tail.pop_front();
            }
            tail.push_back(line);
        }
        if !tail.is_empty() {
            let joined: Vec<String> = tail.into_iter().collect();
            return Ok(joined.join("\n"));
        }
        // empty file → try next date
    }
    Ok(String::new())
}

/// #761 -- Encoder slot returned from Python `allaganeye encoder-slots`.
///
/// `encoder_kind` is the title-cased enum variant name (`"Nvenc"`,
/// `"Libx264"`, `"Qsv"`, `"Amf"`) that the frontend renders as the
/// encoder badge ("NVENC x3" etc.).
#[derive(Debug, serde::Serialize, serde::Deserialize)]
pub struct EncoderSlotJson {
    pub slot_index: u32,
    pub encoder_kind: String,
    pub display_label: String,
}

/// #761 -- Request shape for `enumerate_h264_encoders`. Frontend supplies
/// the metadata.json `system_info` slice.
#[derive(Debug, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct EnumerateEncodersRequest {
    pub vendors: Vec<String>,
    pub preference: Vec<String>,
    pub gpu_models: Vec<String>,
}

/// #761 -- Spawn `python -m allaganeye encoder-slots --vendors=... \
/// --preference=... --gpu-models=...` and parse the JSON array on stdout.
///
/// Codex review #2: enforce `PYTHONIOENCODING=utf-8:replace` to match
/// `start_detect` cp932 mitigation pattern.
#[tauri::command]
async fn enumerate_h264_encoders(
    app: tauri::AppHandle,
    req: EnumerateEncodersRequest,
) -> Result<Vec<EncoderSlotJson>, AppError> {
    let cmd_spec = resolve_allaganeye_command(&app);
    let mut cmd = tokio::process::Command::new(&cmd_spec.program);
    for a in &cmd_spec.prefix_args {
        cmd.arg(a);
    }
    cmd.arg("encoder-slots")
        .arg("--vendors").arg(req.vendors.join(","))
        .arg("--preference").arg(req.preference.join(","))
        .arg("--gpu-models").arg(req.gpu_models.join(","))
        .env("PYTHONIOENCODING", "utf-8:replace")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    if let Some(cwd) = &cmd_spec.cwd {
        cmd.current_dir(cwd);
    }
    process_util::apply_no_window(&mut cmd);

    let output = cmd.output().await.map_err(|e| {
        AppError::new("subprocess.spawn_failed", format!("encoder-slots spawn: {}", e))
            .with_default_hint()
    })?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr).to_string();
        return Err(AppError::new(
            "subprocess.exit_failed",
            format!("encoder-slots exit {}: {}", output.status, stderr),
        )
        .with_default_hint());
    }
    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    serde_json::from_str::<Vec<EncoderSlotJson>>(&stdout).map_err(|e| {
        AppError::new(
            "subprocess.parse_failed",
            format!("encoder-slots stdout parse: {} (raw={})", e, stdout),
        )
        .with_default_hint()
    })
}

/// #761 -- Discriminated union of JSON-line events emitted by
/// `python -m allaganeye export --json`. See spec section 5.
#[derive(Debug, serde::Deserialize)]
#[serde(tag = "type")]
pub enum WireEvent {
    #[serde(rename = "progress")]
    Progress { match_index: u32, percent: f64, stage: String },
    #[serde(rename = "fallback")]
    Fallback {
        match_index: u32,
        fallback_from: String,
        fallback_to: String,
        message: String,
    },
    #[serde(rename = "result")]
    Result {
        match_index: u32,
        output_path: String,
        duration_ms: u64,
        encoder_used: String,
    },
    #[serde(rename = "error")]
    Error {
        match_index: u32,
        error_kind: String,
        error_message: String,
        error_hint: Option<String>,
    },
    #[serde(rename = "summary")]
    Summary {
        success: u32,
        failure: u32,
        skipped: u32,
        cancelled: bool,
    },
    #[serde(other)]
    Unknown,
}

/// #761 -- Parse one ndjson line into `WireEvent`. `None` for empty / malformed.
fn parse_wire_event(line: &str) -> Option<WireEvent> {
    let trimmed = line.trim();
    if trimmed.is_empty() {
        return None;
    }
    serde_json::from_str(trimmed).ok()
}

/// #761 -- Request shape for `start_export` Tauri command.
#[derive(Debug, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct StartExportRequest {
    /// Full metadata JSON content (in-memory edited state). Passed via
    /// stdin to Python so sample mode (filePath=null) + unsaved edits
    /// are supported.
    pub metadata_json: serde_json::Value,
    pub output_dir: String,
    pub codec: String, // "copy" | "h264"
    pub name_pattern: String,
    pub excluded_indexes: Vec<u32>,
}

/// #761 -- Aggregate returned to frontend after Python exits.
#[derive(Debug, serde::Serialize)]
pub struct ExportSummary {
    pub success: u32,
    pub failure: u32,
    pub skipped: u32,
    pub cancelled: bool,
}

#[tauri::command]
async fn start_export(
    app: tauri::AppHandle,
    req: StartExportRequest,
) -> Result<ExportSummary, AppError> {
    let cmd_spec = resolve_allaganeye_command(&app);
    let mut cmd = tokio::process::Command::new(&cmd_spec.program);
    for arg in &cmd_spec.prefix_args {
        cmd.arg(arg);
    }
    let exclude_arg = req
        .excluded_indexes
        .iter()
        .map(|i| i.to_string())
        .collect::<Vec<_>>()
        .join(",");
    cmd.arg("export")
        .arg("--stdin").arg("--json")
        .arg("--output-dir").arg(&req.output_dir)
        .arg("--codec").arg(&req.codec)
        .arg("--name-pattern").arg(&req.name_pattern);
    if !exclude_arg.is_empty() {
        cmd.arg("--exclude").arg(&exclude_arg);
    }
    if let Some(cwd) = &cmd_spec.cwd {
        cmd.current_dir(cwd);
    }
    cmd.env("PYTHONIOENCODING", "utf-8:replace")
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped());
    process_util::apply_no_window(&mut cmd);

    let mut child = cmd.spawn().map_err(|e| {
        AppError::new("subprocess.spawn_failed", format!("start_export spawn: {}", e))
            .with_default_hint()
    })?;

    // Write metadata JSON to stdin, then close
    {
        let mut stdin = child.stdin.take().ok_or_else(|| {
            AppError::new("subprocess.stdin_unavailable", "stdin missing on spawn")
                .with_default_hint()
        })?;
        use tokio::io::AsyncWriteExt;
        let serialized = serde_json::to_vec(&req.metadata_json).map_err(|e| {
            AppError::new("subprocess.serialize_failed", format!("metadata serialize: {}", e))
                .with_default_hint()
        })?;
        stdin.write_all(&serialized).await.map_err(|e| {
            AppError::new(
                "subprocess.stdin_write_failed",
                format!("metadata stdin write: {}", e),
            )
            .with_default_hint()
        })?;
        // stdin dropped here -> EOF to Python
    }

    // Track via PROCESS_TRACKER. Export spawns a single Python process
    // (which itself spawns N ffmpeg children). Use Job Object on Windows
    // (same as start_detect) so cancelling export reliably reaps all
    // ffmpeg descendants. Failure to create/assign the Job is downgraded
    // to a warning (export proceeds without tree-kill protection).
    #[cfg(windows)]
    let job: Option<process_util::job_object::ProcessJob> = {
        match process_util::job_object::ProcessJob::new() {
            Ok(j) => {
                if let Some(raw) = child.raw_handle() {
                    if let Err(e) = j.assign(raw) {
                        eprintln!(
                            "warning: AssignProcessToJobObject failed: {} \
                             (export descendants may be orphaned on cancel)",
                            e
                        );
                    }
                } else {
                    eprintln!(
                        "warning: child.raw_handle() returned None for export \
                         spawn (export descendants may be orphaned on cancel)"
                    );
                }
                Some(j)
            }
            Err(e) => {
                eprintln!(
                    "warning: CreateJobObject failed: {} \
                     (export descendants may be orphaned on cancel)",
                    e
                );
                None
            }
        }
    };
    let tracked = TrackedChild {
        child,
        #[cfg(windows)]
        job,
    };
    let tracked_id = track_child(tracked).await;

    // Capture stdout reader BEFORE the lock is released
    let stdout = {
        let map = process_tracker();
        let mut guard = map.lock().await;
        let tc = guard.get_mut(&tracked_id).expect("tracked just inserted");
        tc.child.stdout.take()
    };

    let mut summary_capture: Option<ExportSummary> = None;
    if let Some(stdout) = stdout {
        use tokio::io::{AsyncBufReadExt, BufReader};
        // #761 / #656 -- defensive byte-level read with lossy UTF-8 decode
        // to mirror start_detect's pattern. PYTHONIOENCODING=utf-8:replace
        // (above) is the primary guarantee; this defensive layer catches the
        // case where the env var fails to apply (e.g. exotic Python launcher).
        let mut reader = BufReader::new(stdout);
        let mut line_buf: Vec<u8> = Vec::with_capacity(1024);

        loop {
            line_buf.clear();
            match reader.read_until(b'\n', &mut line_buf).await {
                Ok(0) => break,
                Ok(_) => {
                    while matches!(line_buf.last(), Some(b'\n') | Some(b'\r')) {
                        line_buf.pop();
                    }
                    let line = String::from_utf8_lossy(&line_buf);
                    match parse_wire_event(&line) {
                        Some(WireEvent::Progress { match_index, percent, stage }) => {
                            let _ = app.emit(
                                "export-progress",
                                ExportProgress {
                                    match_index,
                                    percent,
                                    stage,
                                    message: None,
                                    fallback_from: None,
                                },
                            );
                        }
                        Some(WireEvent::Fallback { match_index, fallback_from, fallback_to, message }) => {
                            let _ = app.emit(
                                "export-progress",
                                ExportProgress {
                                    match_index,
                                    percent: 0.0,
                                    stage: "fallback".to_string(),
                                    message: Some(message),
                                    fallback_from: Some(format!("{} -> {}", fallback_from, fallback_to)),
                                },
                            );
                        }
                        Some(WireEvent::Result { match_index, .. }) => {
                            let _ = app.emit(
                                "export-progress",
                                ExportProgress {
                                    match_index,
                                    percent: 100.0,
                                    stage: "done".to_string(),
                                    message: None,
                                    fallback_from: None,
                                },
                            );
                        }
                        Some(WireEvent::Error { match_index, error_kind: _, error_message, error_hint }) => {
                            let _ = app.emit(
                                "export-progress",
                                ExportProgress {
                                    match_index,
                                    percent: 0.0,
                                    stage: "error".to_string(),
                                    message: Some(if let Some(hint) = error_hint {
                                        format!("{} ({})", error_message, hint)
                                    } else {
                                        error_message
                                    }),
                                    fallback_from: None,
                                },
                            );
                        }
                        Some(WireEvent::Summary { success, failure, skipped, cancelled }) => {
                            summary_capture = Some(ExportSummary { success, failure, skipped, cancelled });
                        }
                        Some(WireEvent::Unknown) | None => {
                            // forward-compat: ignore unknown / non-JSON lines
                        }
                    }
                }
                Err(_) => break,
            }
        }
    }

    let mut child = match untrack_child(tracked_id).await {
        Some(c) => c,
        None => {
            return Ok(ExportSummary {
                success: 0,
                failure: 0,
                skipped: 0,
                cancelled: true,
            });
        }
    };
    let status = child.wait().await.map_err(|e| {
        AppError::new("subprocess.wait_failed", format!("python subprocess wait: {}", e))
            .with_default_hint()
    })?;

    if let Some(summary) = summary_capture {
        return Ok(summary);
    }

    // summary_capture is None — Python exited without emitting a summary line.
    // In practice, Python's export_matches always emits a summary line via
    // WireWriter even for empty queues (see allaganeye/commands/export.py
    // where summary is emitted in --json mode regardless of filtered list size).
    // This fallback path is defensive against:
    // - Python crash before reaching the summary emit
    // - stdout pipe broken / buffer not flushed (uncommon)
    // - extreme races (cancellation between last result and summary emit)
    if status.success() {
        // Exit 0 + no summary = Python normal exit with no output (unlikely but defensive).
        // Treat as zero-work success, NOT cancelled (avoids false CANCEL_CONFIRMED on
        // empty-include / all-excluded scenarios).
        eprintln!(
            "[start_export] WARNING: Python subprocess exited cleanly without summary line; \
             returning zero-work success. Inspect Python stdout flushing if this recurs."
        );
        return Ok(ExportSummary {
            success: 0,
            failure: 0,
            skipped: 0,
            cancelled: false,
        });
    }

    // Non-zero exit + no summary = Python crashed
    Err(AppError::new(
        "subprocess.exit_failed",
        format!(
            "python export subprocess exited unexpectedly (status: {:?}) without emitting summary",
            status.code()
        ),
    )
    .with_default_hint())
}

pub fn run() {
    // #614 -- Rotate stale panic logs (>7 days) and detect unclean shutdown
    // from the previous session, BEFORE the Tauri builder runs so the
    // restart-detected event is queued before any frontend listener attaches.
    match logging::rotate_old_logs(7) {
        Ok(removed) => eprintln!("[startup] rotated {} stale log(s)", removed),
        Err(e) => eprintln!("[startup] warning: failed to rotate old logs: {}", e),
    }
    let restart_panic_msg = logging::detect_panic_from_previous_session();
    eprintln!(
        "[startup] previous-session panic detected: {}",
        restart_panic_msg.is_some()
    );

    // #668 -- Integrity check (release builds only). The check itself runs
    // synchronously here so the result is captured for the setup hook to
    // emit after the webview is ready. Debug builds always get None so
    // `npm run tauri dev` works without a built payload.
    //
    // PR #702 review #3: use a runtime `cfg!()` guard rather than a
    // compile-time `#[cfg(...)]` so clippy on debug builds still considers
    // every integrity item "used" (the call site is a real expression in
    // both branches). Compiler optimises the dead branch out in debug.
    let integrity_failure: Option<integrity::IntegrityErrorPayload> = if cfg!(not(debug_assertions)) {
        integrity::check_install_dir()
    } else {
        None
    };
    eprintln!(
        "[startup] integrity-check failure: {}",
        integrity_failure.is_some()
    );

    let builder = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_shell::init())
        .setup(move |app| {
            // #614 -- Install panic hook now that we have an AppHandle for
            // best-effort emit. File log is the source of truth (panic emit
            // may not arrive if WebView2 has died).
            error::install_panic_hook(Some(app.handle().clone()));

            // #614 -- If the previous session crashed within the last 60s,
            // emit a warning event after webview is ready (small delay).
            if let Some(panic_line) = restart_panic_msg.clone() {
                let app_handle = app.handle().clone();
                tauri::async_runtime::spawn(async move {
                    tokio::time::sleep(std::time::Duration::from_millis(150)).await;
                    let _ = app_handle.emit("panic-from-previous-session", panic_line);
                });
            }

            // #668 -- emit integrity-error after the webview has had a
            // chance to attach its listener (same 150ms idiom as the
            // panic-from-previous-session emit above).
            if let Some(payload) = integrity_failure.clone() {
                let app_handle = app.handle().clone();
                tauri::async_runtime::spawn(async move {
                    tokio::time::sleep(std::time::Duration::from_millis(150)).await;
                    let _ = app_handle.emit("integrity-error", payload);
                });
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            // #523 -- intercept every CloseRequested. The frontend inspects
            // tracked processes on receipt: if none are running it calls
            // `force_exit_app` immediately; otherwise it surfaces the
            // ConfirmExitModal and drives kill + exit on confirm.
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.emit("close-requested", ());
            }
        });

    // #614: dev-only `dev_force_panic` is gated by `#[cfg(debug_assertions)]`.
    // `tauri::generate_handler!` does not accept `#[cfg]` attributes on its
    // arguments, so we build the handler list twice and pick at compile time.
    #[cfg(debug_assertions)]
    let builder = builder.invoke_handler(tauri::generate_handler![
        enumerate_h264_encoders,
        start_export,
        load_metadata,
        get_metadata_mtime,
        apply_changes,
        save_draft,
        load_draft,
        clear_draft,
        restore_from_original,
        check_backup_exists,
        register_video,
        probe_video,
        generate_match_thumbnails,
        extract_brightness_window,
        is_process_running,
        kill_tracked_processes,
        force_exit_app,
        open_folder_in_explorer,
        start_detect,
        read_recent,
        add_recent,
        clear_recent,
        get_log_dir,
        read_error_log_tail,
        probe_environment_info,
        dev_force_panic,
    ]);
    #[cfg(not(debug_assertions))]
    let builder = builder.invoke_handler(tauri::generate_handler![
        enumerate_h264_encoders,
        start_export,
        load_metadata,
        get_metadata_mtime,
        apply_changes,
        save_draft,
        load_draft,
        clear_draft,
        restore_from_original,
        check_backup_exists,
        register_video,
        probe_video,
        generate_match_thumbnails,
        extract_brightness_window,
        is_process_running,
        kill_tracked_processes,
        force_exit_app,
        open_folder_in_explorer,
        start_detect,
        read_recent,
        add_recent,
        clear_recent,
        get_log_dir,
        read_error_log_tail,
        probe_environment_info,
    ]);

    builder
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

    // #814 -- write-boundary guard: end_time must be strictly > start_time so
    // a boundary the zod schema would reject on reload never reaches disk.
    #[test]
    fn apply_changes_rejects_end_before_start() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        let payload = json!({
            "source": "a.mkv",
            "matches": [{ "start_time": 900.0, "end_time": 100.0 }]
        });
        let err = apply_changes_sync(&meta, &payload, None).unwrap_err();
        assert_eq!(err.code, "validation.boundary_invalid");
        // nothing is written when the guard rejects
        assert!(!meta.exists());
    }

    #[test]
    fn apply_changes_rejects_zero_duration_boundary() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        let payload = json!({
            "source": "a.mkv",
            "matches": [{ "start_time": 500.0, "end_time": 500.0 }]
        });
        let err = apply_changes_sync(&meta, &payload, None).unwrap_err();
        assert_eq!(err.code, "validation.boundary_invalid");
        assert!(!meta.exists());
    }

    #[test]
    fn apply_changes_accepts_valid_boundaries() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        let payload = json!({
            "source": "a.mkv",
            "matches": [{ "start_time": 0.0, "end_time": 100.0 }]
        });
        apply_changes_sync(&meta, &payload, None).expect("valid boundaries accepted");
        assert!(meta.exists());
    }

    #[test]
    fn apply_changes_rejects_match_missing_start_time() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        let payload = json!({ "matches": [{ "end_time": 100.0 }] });
        let err = apply_changes_sync(&meta, &payload, None).unwrap_err();
        assert_eq!(err.code, "validation.boundary_invalid");
        assert!(!meta.exists());
    }

    #[test]
    fn apply_changes_rejects_match_missing_end_time() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        let payload = json!({ "matches": [{ "start_time": 0.0 }] });
        let err = apply_changes_sync(&meta, &payload, None).unwrap_err();
        assert_eq!(err.code, "validation.boundary_invalid");
        assert!(!meta.exists());
    }

    #[test]
    fn apply_changes_rejects_match_non_numeric_boundary() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        let payload = json!({ "matches": [{ "start_time": "0", "end_time": "100" }] });
        let err = apply_changes_sync(&meta, &payload, None).unwrap_err();
        assert_eq!(err.code, "validation.boundary_invalid");
        assert!(!meta.exists());
    }

    #[test]
    fn apply_changes_creates_backup_on_first_call() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        let backup = tmp.path().join("metadata.original.json");
        let original = json!({"source": "a.mkv", "matches": [{"m": 1, "start_time": 0.0, "end_time": 100.0}]});
        fs::write(&meta, serde_json::to_string_pretty(&original).unwrap()).unwrap();

        let edited = json!({"source": "a.mkv", "matches": [{"m": 1, "edited": true, "start_time": 0.0, "end_time": 100.0}]});
        apply_changes_sync(&meta, &edited, None).unwrap();

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

        apply_changes_sync(&meta, &json!({"version": "v2"}), None).unwrap();
        apply_changes_sync(&meta, &json!({"version": "v3"}), None).unwrap();
        apply_changes_sync(&meta, &json!({"version": "v4"}), None).unwrap();

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
        apply_changes_sync(&meta, &json!({"first": true}), None).unwrap();
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
        assert!(err.message.contains("no backup to restore"));
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

    // #571 — recent.json history persistence.

    fn make_recent_entry(path: &str, file_name: &str) -> RecentEntry {
        RecentEntry {
            path: path.to_string(),
            file_name: file_name.to_string(),
            size_bytes: 1024,
            mtime_ms: 1_700_000_000_000,
            added_at_ms: 1_700_000_000_000,
        }
    }

    #[test]
    fn read_recent_returns_empty_when_file_missing() {
        let tmp = TempDir::new().unwrap();
        let recent = tmp.path().join("recent.json");
        let list = read_recent_sync(&recent);
        assert!(list.is_empty());
    }

    #[test]
    fn read_recent_returns_empty_when_file_is_corrupt_json() {
        // A garbled file should not block the drop screen — corrupt history is
        // treated as "no history" so the user can still drop a new video.
        let tmp = TempDir::new().unwrap();
        let recent = tmp.path().join("recent.json");
        fs::write(&recent, "this is not json {[").unwrap();
        let list = read_recent_sync(&recent);
        assert!(list.is_empty());
    }

    #[test]
    fn add_recent_creates_file_and_returns_single_entry() {
        let tmp = TempDir::new().unwrap();
        let recent = tmp.path().join("recent.json");
        let entry = make_recent_entry("E:\\videos\\a.mkv", "a.mkv");
        let list = add_recent_sync(&recent, entry.clone()).unwrap();
        assert_eq!(list.len(), 1);
        assert_eq!(list[0], entry);
        // Persisted to disk.
        let on_disk = read_recent_sync(&recent);
        assert_eq!(on_disk, list);
    }

    #[test]
    fn add_recent_dedups_same_path_case_insensitive() {
        // Windows treats `E:\videos\a.mkv` and `e:\Videos\A.mkv` as the same
        // file. The second add must collapse into one entry — and the new
        // metadata (mtime / addedAt) must win because the user just touched
        // the file.
        let tmp = TempDir::new().unwrap();
        let recent = tmp.path().join("recent.json");
        add_recent_sync(&recent, make_recent_entry("E:\\videos\\a.mkv", "a.mkv")).unwrap();
        let mut second = make_recent_entry("e:\\Videos\\A.mkv", "A.mkv");
        second.added_at_ms = 1_800_000_000_000;
        let list = add_recent_sync(&recent, second.clone()).unwrap();
        assert_eq!(list.len(), 1);
        assert_eq!(list[0].added_at_ms, 1_800_000_000_000);
        assert_eq!(list[0].path, "e:\\Videos\\A.mkv");
    }

    #[test]
    fn add_recent_dedups_same_path_with_mixed_separators() {
        // PR #655 review (Item 1): the Tauri dialog hands us `\` while D&D
        // fixtures and the CLI handoff can produce `/`. Both forms refer to
        // the same Windows file, so dedup must collapse them. Without
        // separator normalization the second add silently produces a
        // 2-entry list where `read_recent` returns the same recording twice.
        let tmp = TempDir::new().unwrap();
        let recent = tmp.path().join("recent.json");
        add_recent_sync(&recent, make_recent_entry("E:\\videos\\a.mkv", "a.mkv")).unwrap();
        let mut second = make_recent_entry("E:/Videos/A.mkv", "A.mkv");
        second.added_at_ms = 1_800_000_000_000;
        let list = add_recent_sync(&recent, second.clone()).unwrap();
        assert_eq!(list.len(), 1);
        assert_eq!(list[0].added_at_ms, 1_800_000_000_000);
        // The new entry's original separators are preserved on disk —
        // only the key was normalized for comparison.
        assert_eq!(list[0].path, "E:/Videos/A.mkv");
    }

    #[test]
    fn normalize_path_key_collapses_case_and_separator() {
        // Pinning the helper directly so a future refactor can't silently
        // drop one of the two normalizations.
        assert_eq!(
            normalize_path_key("E:\\videos\\a.mkv"),
            normalize_path_key("e:/Videos/A.mkv"),
        );
        assert_eq!(
            normalize_path_key("C:/path/with/forward.mkv"),
            "c:\\path\\with\\forward.mkv",
        );
    }

    #[test]
    fn add_recent_moves_existing_entry_to_top() {
        // Re-adding an existing path must move it to position 0 even when
        // there are intervening entries — the user just selected it again
        // and expects to see it at the top of the list.
        let tmp = TempDir::new().unwrap();
        let recent = tmp.path().join("recent.json");
        add_recent_sync(&recent, make_recent_entry("E:\\a.mkv", "a.mkv")).unwrap();
        add_recent_sync(&recent, make_recent_entry("E:\\b.mkv", "b.mkv")).unwrap();
        add_recent_sync(&recent, make_recent_entry("E:\\c.mkv", "c.mkv")).unwrap();
        // Re-add `a.mkv` — it should jump from position 2 to position 0.
        let list = add_recent_sync(&recent, make_recent_entry("E:\\a.mkv", "a.mkv")).unwrap();
        assert_eq!(list.len(), 3);
        assert_eq!(list[0].path, "E:\\a.mkv");
        assert_eq!(list[1].path, "E:\\c.mkv");
        assert_eq!(list[2].path, "E:\\b.mkv");
    }

    #[test]
    fn add_recent_truncates_to_limit() {
        // Inserting RECENT_LIMIT+5 distinct paths must keep exactly RECENT_LIMIT
        // entries with the most recent at position 0 and the oldest at the
        // bottom — the eldest 5 fall off the end.
        let tmp = TempDir::new().unwrap();
        let recent = tmp.path().join("recent.json");
        for i in 0..(RECENT_LIMIT as u32 + 5) {
            let p = format!("E:\\video_{:02}.mkv", i);
            let n = format!("video_{:02}.mkv", i);
            add_recent_sync(&recent, make_recent_entry(&p, &n)).unwrap();
        }
        let list = read_recent_sync(&recent);
        assert_eq!(list.len(), RECENT_LIMIT);
        // Newest first.
        assert_eq!(list[0].path, format!("E:\\video_{:02}.mkv", RECENT_LIMIT + 4));
        // Oldest still kept (5 fell off the bottom).
        assert_eq!(list[RECENT_LIMIT - 1].path, "E:\\video_05.mkv");
    }

    #[test]
    fn add_recent_creates_parent_dir_when_missing() {
        // Fresh install: ~/.allaganeye/ doesn't exist yet. add_recent must
        // create it so the very first drop doesn't error out.
        let tmp = TempDir::new().unwrap();
        let recent = tmp.path().join(".allaganeye").join("recent.json");
        assert!(!recent.parent().unwrap().exists());
        add_recent_sync(&recent, make_recent_entry("E:\\a.mkv", "a.mkv")).unwrap();
        assert!(recent.exists());
    }

    #[test]
    fn clear_recent_removes_existing_file() {
        let tmp = TempDir::new().unwrap();
        let recent = tmp.path().join("recent.json");
        add_recent_sync(&recent, make_recent_entry("E:\\a.mkv", "a.mkv")).unwrap();
        assert!(recent.exists());
        clear_recent_sync(&recent).unwrap();
        assert!(!recent.exists());
    }

    #[test]
    fn clear_recent_succeeds_when_file_missing() {
        // Idempotent — a fresh install has no recent.json, calling clear must
        // not blow up.
        let tmp = TempDir::new().unwrap();
        let recent = tmp.path().join("recent.json");
        assert!(!recent.exists());
        clear_recent_sync(&recent).unwrap();
    }

    #[test]
    fn add_recent_no_stray_tmp_file() {
        // The atomic-rename helper must clean up the .tmp sidecar on success
        // (mirrors the metadata.json invariant).
        let tmp = TempDir::new().unwrap();
        let recent = tmp.path().join("recent.json");
        add_recent_sync(&recent, make_recent_entry("E:\\a.mkv", "a.mkv")).unwrap();
        assert!(!tmp.path().join("recent.json.tmp").exists());
    }

    #[test]
    fn prune_missing_drops_entries_whose_files_are_gone() {
        // PR #655 Round 2: replaces the old `with_existence` flag-based
        // approach. Entries whose backing file is gone must be removed
        // from the returned list (they'll also be persisted out by
        // `read_recent` on the next call).
        let tmp = TempDir::new().unwrap();
        let real_path = tmp.path().join("real.mkv");
        fs::write(&real_path, b"x").unwrap();
        let real_str = real_path.to_string_lossy().into_owned();
        let entries = vec![
            RecentEntry {
                path: real_str.clone(),
                file_name: "real.mkv".into(),
                size_bytes: 1,
                mtime_ms: 1,
                added_at_ms: 1,
            },
            RecentEntry {
                path: tmp.path().join("ghost.mkv").to_string_lossy().into_owned(),
                file_name: "ghost.mkv".into(),
                size_bytes: 1,
                mtime_ms: 1,
                added_at_ms: 1,
            },
        ];
        let pruned = prune_missing(entries);
        assert_eq!(pruned.len(), 1);
        assert_eq!(pruned[0].file_name, "real.mkv");
    }

    #[test]
    fn add_recent_with_prune_drops_stale_siblings_after_insert() {
        // PR #655 Round 4 regression: dragging in a fresh video while the
        // list already had an entry pointing at a moved/deleted file used
        // to leave the stale entry visible (the pre-fix `add_recent`
        // command went through the un-pruning `add_recent_sync` only).
        let tmp = TempDir::new().unwrap();
        let recent = tmp.path().join("recent.json");

        // Pre-populate with a "ghost" — its backing file does not exist.
        let ghost_path = tmp
            .path()
            .join("ghost.mkv")
            .to_string_lossy()
            .into_owned();
        add_recent_sync(
            &recent,
            make_recent_entry(&ghost_path, "ghost.mkv"),
        )
        .unwrap();
        assert_eq!(read_recent_sync(&recent).len(), 1);

        // Now add a real file via the prune-aware wrapper.
        let real_path = tmp.path().join("real.mkv");
        fs::write(&real_path, b"x").unwrap();
        let real_str = real_path.to_string_lossy().into_owned();
        let result = add_recent_with_prune(
            &recent,
            make_recent_entry(&real_str, "real.mkv"),
        )
        .unwrap();

        // Ghost dropped, only the real entry remains, persisted and in-memory.
        assert_eq!(result.len(), 1);
        assert_eq!(result[0].file_name, "real.mkv");
        let on_disk = read_recent_sync(&recent);
        assert_eq!(on_disk, result);
    }

    #[test]
    fn add_recent_with_prune_preserves_just_inserted_entry() {
        // Belt-and-suspenders: the just-inserted entry is exists-checked
        // upstream by `add_recent`, but make sure `prune_missing` doesn't
        // over-eagerly drop it when the wrapper runs.
        let tmp = TempDir::new().unwrap();
        let recent = tmp.path().join("recent.json");
        let real_path = tmp.path().join("only.mkv");
        fs::write(&real_path, b"x").unwrap();
        let real_str = real_path.to_string_lossy().into_owned();
        let result = add_recent_with_prune(
            &recent,
            make_recent_entry(&real_str, "only.mkv"),
        )
        .unwrap();
        assert_eq!(result.len(), 1);
        assert_eq!(result[0].file_name, "only.mkv");
    }

    #[test]
    fn prune_missing_keeps_all_when_every_file_exists() {
        let tmp = TempDir::new().unwrap();
        let a = tmp.path().join("a.mkv");
        let b = tmp.path().join("b.mkv");
        fs::write(&a, b"x").unwrap();
        fs::write(&b, b"x").unwrap();
        let entries = vec![
            RecentEntry {
                path: a.to_string_lossy().into_owned(),
                file_name: "a.mkv".into(),
                size_bytes: 1,
                mtime_ms: 1,
                added_at_ms: 1,
            },
            RecentEntry {
                path: b.to_string_lossy().into_owned(),
                file_name: "b.mkv".into(),
                size_bytes: 1,
                mtime_ms: 1,
                added_at_ms: 1,
            },
        ];
        assert_eq!(prune_missing(entries).len(), 2);
    }

    // PR #655 Round 2: Windows `\\?\` extended-length prefix strip — the
    // recent-list `add_recent` and (TS-side) export output-dir picker
    // both saw the prefix leak through into displayed paths.

    #[test]
    fn strip_extended_path_prefix_strips_drive_form() {
        assert_eq!(
            strip_extended_path_prefix("\\\\?\\E:\\videos\\a.mkv"),
            "E:\\videos\\a.mkv",
        );
    }

    #[test]
    fn strip_extended_path_prefix_strips_unc_form() {
        assert_eq!(
            strip_extended_path_prefix("\\\\?\\UNC\\server\\share\\a.mkv"),
            "\\\\server\\share\\a.mkv",
        );
    }

    #[test]
    fn strip_extended_path_prefix_passes_through_when_absent() {
        assert_eq!(
            strip_extended_path_prefix("E:\\videos\\a.mkv"),
            "E:\\videos\\a.mkv",
        );
        assert_eq!(
            strip_extended_path_prefix("/home/user/a.mkv"),
            "/home/user/a.mkv",
        );
    }

    #[test]
    fn load_metadata_returns_error_when_file_missing() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        let err = load_metadata_sync(&meta).unwrap_err();
        assert!(err.message.contains("metadata file not found"));
    }

    #[test]
    fn load_metadata_returns_error_on_invalid_json() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        fs::write(&meta, r#"{"source": "a.mkv", invalid"#).unwrap();
        let err = load_metadata_sync(&meta).unwrap_err();
        assert!(err.message.contains("invalid JSON"));
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
        assert!(err.message.contains("must be a JSON object"));
    }

    // #514 — mtime-based exclusive control for apply_changes.

    #[test]
    fn apply_changes_succeeds_when_expected_mtime_matches() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        fs::write(&meta, r#"{"v":1}"#).unwrap();
        let current = file_mtime_ms(&meta).expect("mtime exists for newly written file");

        apply_changes_sync(&meta, &json!({"v": 2}), Some(current)).unwrap();

        let after: Value =
            serde_json::from_str(&fs::read_to_string(&meta).unwrap()).unwrap();
        assert_eq!(after, json!({"v": 2}));
    }

    #[test]
    fn apply_changes_returns_conflict_when_expected_mtime_mismatches() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        fs::write(&meta, r#"{"v":1}"#).unwrap();
        // An obviously stale mtime — `1 ms after epoch` is decades before any
        // real-world file write, so the comparison is deterministic.
        let stale: u64 = 1;

        let err = apply_changes_sync(&meta, &json!({"v": 2}), Some(stale)).unwrap_err();
        assert!(err.message.starts_with("conflict:"), "unexpected error: {err}");

        // Conflict must not overwrite the file.
        let current: Value =
            serde_json::from_str(&fs::read_to_string(&meta).unwrap()).unwrap();
        assert_eq!(current, json!({"v": 1}));
    }

    #[test]
    fn apply_changes_skips_check_when_expected_mtime_is_none() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        fs::write(&meta, r#"{"v":1}"#).unwrap();

        // None → check is bypassed even though the file already exists.
        apply_changes_sync(&meta, &json!({"v": 2}), None).unwrap();
        let after: Value =
            serde_json::from_str(&fs::read_to_string(&meta).unwrap()).unwrap();
        assert_eq!(after, json!({"v": 2}));
    }

    #[test]
    fn apply_changes_skips_check_when_target_missing() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        // First write: no existing file to conflict against, so expected_mtime
        // must not block the write.
        apply_changes_sync(&meta, &json!({"first": true}), Some(12345)).unwrap();
        assert!(meta.exists());
    }

    #[test]
    fn file_mtime_ms_returns_none_for_missing_file() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("missing.json");
        assert!(file_mtime_ms(&meta).is_none());
    }

    #[test]
    fn file_mtime_ms_returns_some_for_existing_file() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        fs::write(&meta, r#"{}"#).unwrap();
        assert!(file_mtime_ms(&meta).is_some());
    }

    /// Integration test: simulate an external process writing the file after
    /// GUI load. The fresh mtime must differ from the cached one, and
    /// `apply_changes_sync` must refuse the stale handle with a conflict error
    /// while leaving the external write intact. Review指摘 3 (#514 再見直し).
    #[test]
    fn apply_changes_detects_conflict_after_real_external_write() {
        use std::thread::sleep;
        use std::time::Duration;

        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        fs::write(&meta, r#"{"v":1}"#).unwrap();
        let initial_mtime = file_mtime_ms(&meta).expect("initial mtime");

        // Simulate an external writer (another process) replacing the file.
        // 20ms sleep comfortably exceeds NTFS (100ns) / ext4 (ns) / APFS (ns)
        // mtime resolutions so the second write produces a strictly newer
        // timestamp. macOS HFS+ (1s granularity) is out of CI scope.
        sleep(Duration::from_millis(20));
        fs::write(&meta, r#"{"external":true}"#).unwrap();
        let after_external = file_mtime_ms(&meta).expect("post-external mtime");
        assert!(
            after_external > initial_mtime,
            "external write must advance mtime ({after_external} > {initial_mtime})",
        );

        // apply_changes_sync with the stale initial mtime must refuse the write.
        let err = apply_changes_sync(&meta, &json!({"v": 2}), Some(initial_mtime))
            .unwrap_err();
        assert!(err.message.starts_with("conflict:"), "unexpected error: {err}");

        // File still reflects the external write (not overwritten).
        let current: Value =
            serde_json::from_str(&fs::read_to_string(&meta).unwrap()).unwrap();
        assert_eq!(current, json!({"external": true}));
    }

    /// Integration test: consecutive applies must rotate the mtime correctly.
    /// After apply 1, the caller holds a fresh mtime; apply 2 with that fresh
    /// mtime succeeds, and a subsequent apply with the original stale mtime
    /// must fail. This detects the regression where a GUI self-write would
    /// immediately conflict on its own next apply. Review指摘 3 (#514 再見直し).
    #[test]
    fn consecutive_applies_rotate_mtime_correctly() {
        use std::thread::sleep;
        use std::time::Duration;

        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        fs::write(&meta, r#"{"v":1}"#).unwrap();
        let m1 = file_mtime_ms(&meta).unwrap();

        sleep(Duration::from_millis(20));
        apply_changes_sync(&meta, &json!({"v": 2}), Some(m1)).unwrap();
        let m2 = file_mtime_ms(&meta).unwrap();
        assert!(m2 > m1, "mtime must advance after apply ({m2} > {m1})");

        sleep(Duration::from_millis(20));
        apply_changes_sync(&meta, &json!({"v": 3}), Some(m2)).unwrap();
        let m3 = file_mtime_ms(&meta).unwrap();
        assert!(m3 > m2, "mtime must advance again ({m3} > {m2})");

        // The original m1 is now stale — attempting to apply with it must fail
        // (regression guard: prevents accepting pre-first-apply handles).
        let err = apply_changes_sync(&meta, &json!({"v": 4}), Some(m1)).unwrap_err();
        assert!(err.message.starts_with("conflict:"), "unexpected error: {err}");
    }

    // #517 — draft auto-save tests.

    #[test]
    fn save_draft_creates_sibling_draft_file() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        let draft_file = tmp.path().join("metadata.draft.json");
        let draft = json!({"source": "a.mkv", "matches": []});

        save_draft_sync(&meta, &draft).unwrap();

        assert!(draft_file.exists());
        let roundtrip: Value =
            serde_json::from_str(&fs::read_to_string(&draft_file).unwrap()).unwrap();
        assert_eq!(roundtrip, draft);
    }

    #[test]
    fn save_draft_overwrites_existing_draft() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        let draft_file = tmp.path().join("metadata.draft.json");
        fs::write(&draft_file, r#"{"old": true}"#).unwrap();

        let new_draft = json!({"new": true});
        save_draft_sync(&meta, &new_draft).unwrap();

        let roundtrip: Value =
            serde_json::from_str(&fs::read_to_string(&draft_file).unwrap()).unwrap();
        assert_eq!(roundtrip, new_draft);
    }

    #[test]
    fn load_draft_returns_none_when_file_missing() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        let result = load_draft_sync(&meta).unwrap();
        assert!(result.is_none());
    }

    #[test]
    fn load_draft_returns_parsed_value_when_present() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        let draft_file = tmp.path().join("metadata.draft.json");
        let draft = json!({"source": "a.mkv", "matches": [{"m": 1}]});
        fs::write(&draft_file, serde_json::to_string_pretty(&draft).unwrap()).unwrap();

        let result = load_draft_sync(&meta).unwrap();
        assert_eq!(result, Some(draft));
    }

    #[test]
    fn load_draft_returns_err_on_invalid_json() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        let draft_file = tmp.path().join("metadata.draft.json");
        fs::write(&draft_file, r#"{"broken": invalid"#).unwrap();

        let err = load_draft_sync(&meta).unwrap_err();
        assert!(err.message.contains("invalid JSON in draft"));
    }

    #[test]
    fn clear_draft_removes_existing_file() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        let draft_file = tmp.path().join("metadata.draft.json");
        fs::write(&draft_file, r#"{}"#).unwrap();
        assert!(draft_file.exists());

        clear_draft_sync(&meta).unwrap();
        assert!(!draft_file.exists());
    }

    #[test]
    fn clear_draft_is_noop_when_file_missing() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        // No draft on disk — should still succeed.
        clear_draft_sync(&meta).unwrap();
    }

    #[test]
    fn save_and_load_draft_roundtrip() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        let draft = json!({"source": "a.mkv", "matches": [{"index": 1}]});

        save_draft_sync(&meta, &draft).unwrap();
        let loaded = load_draft_sync(&meta).unwrap();
        assert_eq!(loaded, Some(draft));
    }

    #[test]
    fn draft_lives_alongside_metadata_not_backup() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        let backup = tmp.path().join("metadata.original.json");
        let draft_file = tmp.path().join("metadata.draft.json");

        save_draft_sync(&meta, &json!({"m": 1})).unwrap();

        assert!(draft_file.exists());
        // Draft must not touch the backup file.
        assert!(!backup.exists());
    }

    /// Review 指摘 F3: save_draft must complete correctly even when a stale
    /// `metadata.draft.json.tmp` is left over from a previous crash. This
    /// pins the atomic-write contract for the draft file: the rename is not
    /// blocked by pre-existing tmp artifacts and the final file reflects the
    /// new payload regardless of prior state.
    #[test]
    fn save_draft_succeeds_when_stale_tmp_file_exists() {
        let tmp = TempDir::new().unwrap();
        let meta = tmp.path().join("metadata.json");
        let draft_file = tmp.path().join("metadata.draft.json");
        let tmp_file = tmp.path().join("metadata.draft.json.tmp");
        // Simulate a crash that left a stale .tmp file behind.
        fs::write(&tmp_file, r#"{"corrupt": true}"#).unwrap();
        assert!(tmp_file.exists());

        let draft = json!({"source": "a.mkv", "matches": []});
        save_draft_sync(&meta, &draft).unwrap();

        // Final file must have the new content regardless of prior .tmp state.
        assert!(draft_file.exists());
        let roundtrip: Value =
            serde_json::from_str(&fs::read_to_string(&draft_file).unwrap()).unwrap();
        assert_eq!(roundtrip, draft);
    }

    /// #465 -- a non-existent path must be rejected before any token is
    /// minted or the server is touched.
    #[test]
    fn register_video_rejects_missing_file() {
        let tmp = TempDir::new().unwrap();
        let missing = tmp.path().join("does_not_exist.mp4");
        let err = validate_video_path(&missing).unwrap_err();
        assert!(
            err.message.contains("not found"),
            "expected 'not found' in error, got: {}",
            err
        );
    }

    /// #465 -- directories are not valid video sources; we only allow
    /// regular files. This prevents a caller from accidentally registering
    /// a folder and serving its contents.
    #[test]
    fn register_video_rejects_directory() {
        let tmp = TempDir::new().unwrap();
        let err = validate_video_path(tmp.path()).unwrap_err();
        assert!(
            err.message.contains("not a regular file"),
            "expected 'not a regular file' in error, got: {}",
            err
        );
    }

    /// #465 -- accepting a regular file returns a canonicalized absolute
    /// path suitable for the token map.
    #[test]
    fn validate_video_path_accepts_regular_file() {
        let tmp = TempDir::new().unwrap();
        let video = tmp.path().join("clip.mp4");
        fs::write(&video, b"fake mp4 bytes").unwrap();
        let canonical = validate_video_path(&video).unwrap();
        assert!(canonical.is_absolute());
        assert!(canonical.exists());
    }

    /// #465 -- two consecutive registrations must yield distinct tokens and
    /// leave both entries in the map.
    #[test]
    fn register_video_returns_distinct_tokens_for_two_registrations() {
        let tmp = TempDir::new().unwrap();
        let a = tmp.path().join("a.mp4");
        let b = tmp.path().join("b.mp4");
        fs::write(&a, b"aaa").unwrap();
        fs::write(&b, b"bbb").unwrap();

        let mut tokens: HashMap<Uuid, PathBuf> = HashMap::new();
        let token_a = register_video_sync(&a, &mut tokens);
        let token_b = register_video_sync(&b, &mut tokens);

        assert_ne!(token_a, token_b, "tokens must be distinct");
        assert_eq!(tokens.len(), 2);
        assert_eq!(tokens.get(&token_a).unwrap(), &a);
        assert_eq!(tokens.get(&token_b).unwrap(), &b);
    }

    /// #465 -- registering the same file twice also yields distinct tokens
    /// (each registration is an independent handle; no deduplication).
    #[test]
    fn register_video_same_file_twice_yields_distinct_tokens() {
        let tmp = TempDir::new().unwrap();
        let video = tmp.path().join("clip.mp4");
        fs::write(&video, b"same file").unwrap();

        let mut tokens: HashMap<Uuid, PathBuf> = HashMap::new();
        let t1 = register_video_sync(&video, &mut tokens);
        let t2 = register_video_sync(&video, &mut tokens);

        assert_ne!(t1, t2);
        assert_eq!(tokens.len(), 2);
        assert_eq!(tokens.get(&t1).unwrap(), &video);
        assert_eq!(tokens.get(&t2).unwrap(), &video);
    }

    /// #465 -- same path + same mtime must produce the same hash across
    /// invocations (cache hits rely on this).
    #[test]
    fn compute_video_cache_hash_is_deterministic() {
        let path = Path::new("C:/videos/sample.mp4");
        let h1 = compute_video_cache_hash(path, 1_700_000_000_000);
        let h2 = compute_video_cache_hash(path, 1_700_000_000_000);
        assert_eq!(h1, h2);
        assert_eq!(h1.len(), 64, "SHA256 hex is 64 chars");
    }

    /// #465 -- mtime deltas invalidate the cache so re-encoded videos at the
    /// same path never serve stale thumbnails.
    #[test]
    fn compute_video_cache_hash_changes_with_mtime() {
        let path = Path::new("C:/videos/sample.mp4");
        let h1 = compute_video_cache_hash(path, 1_700_000_000_000);
        let h2 = compute_video_cache_hash(path, 1_700_000_000_001);
        assert_ne!(h1, h2);
    }

    /// #465 -- different paths never collide, even with identical mtimes.
    #[test]
    fn compute_video_cache_hash_changes_with_path() {
        let mtime = 1_700_000_000_000u64;
        let h1 = compute_video_cache_hash(Path::new("C:/videos/a.mp4"), mtime);
        let h2 = compute_video_cache_hash(Path::new("C:/videos/b.mp4"), mtime);
        assert_ne!(h1, h2);
    }

    /// #465 / PR #655 Round 2 -- `thumb_cache_dir` must place the hash
    /// segment and the literal `thumbs` leaf under `<install dir>/cache/`.
    /// We check path components to stay OS-separator-agnostic. Relocated
    /// from `~/.allaganeye/cache/...` to the exe directory in PR #655 Round
    /// 2 (Portable ZIP philosophy).
    #[test]
    fn thumb_cache_dir_includes_hash_and_thumbs_suffix() {
        let hash = "deadbeef".repeat(8); // 64 chars like a real digest
        let dir = thumb_cache_dir(&hash).unwrap();
        let components: Vec<String> = dir
            .components()
            .map(|c| c.as_os_str().to_string_lossy().to_string())
            .collect();
        // Must end with ... / cache / <hash> / thumbs (no `.allaganeye`
        // segment anymore — it lives next to the exe now).
        let n = components.len();
        assert!(n >= 3, "path too short: {:?}", components);
        assert_eq!(components[n - 1], "thumbs");
        assert_eq!(components[n - 2], hash);
        assert_eq!(components[n - 3], "cache");
        // Sanity: the dir must be sibling-of-exe, so its parent of
        // `cache` should match the exe's parent.
        let exe = std::env::current_exe().unwrap();
        let exe_parent = exe.parent().unwrap();
        let cache_parent = dir
            .ancestors()
            .nth(3) // dir / thumbs / hash / cache → exe parent
            .expect("cache parent");
        assert_eq!(cache_parent, exe_parent);
    }

    /// #465 -- timestamp grid is centred on the boundary, spans the full
    /// window, and contains exactly `count` samples.
    #[test]
    fn compute_candidate_timestamps_centres_window() {
        let ts = compute_candidate_timestamps(100.0, 2.0, 5);
        assert_eq!(ts.len(), 5);
        assert!((ts[0] - 98.0).abs() < 1e-9);
        assert!((ts[2] - 100.0).abs() < 1e-9);
        assert!((ts[4] - 102.0).abs() < 1e-9);
    }

    /// #465 -- the grid must never produce negative timestamps (ffmpeg
    /// rejects `-ss <0`); clamp at 0.
    #[test]
    fn compute_candidate_timestamps_clamps_below_zero() {
        let ts = compute_candidate_timestamps(1.0, 3.0, 5);
        for t in &ts {
            assert!(*t >= 0.0, "negative t: {}", t);
        }
        assert!((ts[0] - 0.0).abs() < 1e-9);
    }

    /// #465 -- single-sample requests return exactly the boundary.
    #[test]
    fn compute_candidate_timestamps_single_sample() {
        let ts = compute_candidate_timestamps(42.5, 1.0, 1);
        assert_eq!(ts, vec![42.5]);
    }

    /// #465 -- the token format carries the match index (3-digit pad) and
    /// the ms timestamp so cached files are self-describing.
    #[test]
    fn thumb_token_formats_index_and_ms() {
        assert_eq!(thumb_token(3, 452.5), "match003_t452500");
        assert_eq!(thumb_token(0, 0.0), "match000_t0");
        assert_eq!(thumb_token(999, 1.001), "match999_t1001");
    }

    // #465 review (B): probe_video の frame rate parser

    #[test]
    fn parse_frame_rate_str_handles_simple_ratio() {
        assert!((parse_frame_rate_str(Some("60/1")).unwrap() - 60.0).abs() < 1e-9);
        assert!((parse_frame_rate_str(Some("30/1")).unwrap() - 30.0).abs() < 1e-9);
    }

    #[test]
    fn parse_frame_rate_str_handles_ntsc_ratio() {
        // 60000/1001 ≒ 59.94
        let fps = parse_frame_rate_str(Some("60000/1001")).unwrap();
        assert!((fps - 59.94).abs() < 1e-2);
    }

    #[test]
    fn parse_frame_rate_str_returns_none_for_zero_denominator() {
        assert_eq!(parse_frame_rate_str(Some("60/0")), None);
    }

    #[test]
    fn parse_frame_rate_str_returns_none_for_zero_numerator() {
        // 0 fps は invalid (>0 でない)
        assert_eq!(parse_frame_rate_str(Some("0/1")), None);
    }

    #[test]
    fn parse_frame_rate_str_returns_none_for_malformed() {
        assert_eq!(parse_frame_rate_str(Some("garbage")), None);
        assert_eq!(parse_frame_rate_str(Some("60")), None); // no slash
        assert_eq!(parse_frame_rate_str(Some("a/b")), None);
        assert_eq!(parse_frame_rate_str(None), None);
    }

    /// #465 review (B): `probe_video_with` を inject 可能な ffprobe path で
    /// 起動し、JSON 出力のパース → VideoProbeInfo マッピングを検証する。
    /// 実 ffprobe の代わりに stdout に固定 JSON を出すスクリプト
    /// (Windows なので cmd.exe + echo or python -c) を用意するのは複雑な
    /// ので、ここでは ffprobe が無いケース (spawn 失敗 → エラー) のみを
    /// 確認する。frame rate / JSON parse のロジックは parse_frame_rate_str
    /// + serde_json の組み合わせとしてカバー済み。
    #[tokio::test]
    async fn probe_video_with_returns_error_when_ffprobe_missing() {
        let tmp = TempDir::new().unwrap();
        let video = tmp.path().join("dummy.mp4");
        std::fs::write(&video, b"not a real video").unwrap();
        let result = probe_video_with(&video, "this-binary-does-not-exist").await;
        assert!(result.is_err());
        let err = result.unwrap_err();
        assert!(
            err.message.contains("ffprobe spawn failed") || err.message.contains("ffprobe failed"),
            "unexpected error: {}",
            err
        );
    }

    /// ExportProgress::fallback_from が serde で正しく往復する。
    #[test]
    fn export_progress_fallback_from_serde_roundtrip() {
        let progress = ExportProgress {
            match_index: 1,
            percent: 0.0,
            stage: "fallback".to_string(),
            message: Some("NVENC failed".to_string()),
            fallback_from: Some("h264_nvenc -> libx264".to_string()),
        };
        let json = serde_json::to_string(&progress).expect("serialize");
        assert!(json.contains("\"fallback_from\":\"h264_nvenc -> libx264\""));
        assert!(json.contains("\"stage\":\"fallback\""));
    }

    /// fallback_from が None のときは JSON にフィールドが出ない (skip_serializing_if)。
    #[test]
    fn export_progress_omits_fallback_from_when_none() {
        let progress = ExportProgress {
            match_index: 2,
            percent: 50.0,
            stage: "encoding".to_string(),
            message: None,
            fallback_from: None,
        };
        let json = serde_json::to_string(&progress).expect("serialize");
        assert!(!json.contains("fallback_from"));
        assert!(!json.contains("message"));
    }


    /// #466 review #4: 出力先親ディレクトリが存在しなければエラー。
    /// 以前の `create_dir_all` (silent mkdir) は廃止されたので、存在しない
    /// パスを渡すと「does not exist」エラーを返す。
    #[test]
    fn validate_output_parent_exists_rejects_missing_parent() {
        let tmp = TempDir::new().unwrap();
        let nested = tmp.path().join("nope").join("clip.mp4");
        let err = validate_output_parent_exists(&nested).unwrap_err();
        assert!(err.message.contains("does not exist"), "got: {}", err);
    }

    /// #466 review #4: 親ディレクトリが存在すれば Ok。
    #[test]
    fn validate_output_parent_exists_accepts_existing_parent() {
        let tmp = TempDir::new().unwrap();
        let target = tmp.path().join("clip.mp4");
        validate_output_parent_exists(&target).unwrap();
    }

    /// #466 review #4: 親なしパス (filename だけ) は Ok (現在のディレクトリ)。
    #[test]
    fn validate_output_parent_exists_accepts_bare_filename() {
        validate_output_parent_exists(Path::new("clip.mp4")).unwrap();
    }

    /// #545 review #6: 存在しないパスを渡したら明示エラー (explorer 起動前に
    /// validate)。spawn を含まない validator の単体テスト。
    #[test]
    fn validate_open_folder_request_rejects_missing_path() {
        let tmp = TempDir::new().unwrap();
        let bogus = tmp.path().join("does-not-exist");
        let err = validate_open_folder_request(&bogus.to_string_lossy()).unwrap_err();
        assert!(err.message.contains("does not exist"), "got: {}", err);
    }

    /// #545 review #6: 存在するディレクトリは accept (Windows のみ Ok、
    /// 非 Windows は unsupported エラー)。spawn 副作用なしで分岐確認。
    #[test]
    #[cfg(target_os = "windows")]
    fn validate_open_folder_request_accepts_existing_dir_on_windows() {
        let tmp = TempDir::new().unwrap();
        validate_open_folder_request(&tmp.path().to_string_lossy()).unwrap();
    }

    /// #545 review #6: 非 Windows 環境では path が存在しても unsupported
    /// エラーを返す。CI (Linux) でも安定して走る回帰テスト。
    #[test]
    #[cfg(not(target_os = "windows"))]
    fn validate_open_folder_request_returns_unsupported_on_non_windows() {
        let tmp = TempDir::new().unwrap();
        let err =
            validate_open_folder_request(&tmp.path().to_string_lossy()).unwrap_err();
        assert!(err.message.contains("Windows"), "got: {}", err);
    }

    /// #545 mystifying-ptolemy-d112b5 review (2026-04-25): track_child →
    /// untrack_child の往復で正しく Some が返ること。`start_export` の
    /// happy-path cleanup の core ロジック。
    ///
    /// Windows 用 dummy プロセスとして `cmd /c rem` を spawn (即終了 no-op)、
    /// 非 Windows は `true` を spawn する。spawn 直後に track → untrack して
    /// Some を確認、最後に kill して残留を防ぐ。
    #[tokio::test]
    async fn track_child_then_untrack_returns_some() {
        // PROCESS_TRACKER は process-global の OnceCell なので、別 test の
        // 残留を念のため drain。失敗しても無害。
        let _ = kill_tracked_processes().await;

        let mut spawn = if cfg!(target_os = "windows") {
            tokio::process::Command::new("cmd")
        } else {
            tokio::process::Command::new("true")
        };
        if cfg!(target_os = "windows") {
            spawn.args(["/c", "rem"]);
        }
        let child = spawn.spawn().expect("spawn dummy child failed");

        let id = track_child(TrackedChild::no_job(child)).await;
        let recovered = untrack_child(id).await;
        assert!(
            recovered.is_some(),
            "untrack_child should return Some right after track"
        );
        // recovered Child は drop で OS 側に handle が返るが、念のため明示
        // wait しておく (zombie 防止)。
        if let Some(mut c) = recovered {
            let _ = c.wait().await;
        }
    }

    /// #545 mystifying-ptolemy-d112b5 review (2026-04-25): track_child のあと
    /// `kill_tracked_processes` が drain した場合、untrack_child は None を
    /// 返す。`start_export` の cancel 検出 (`untrack` 結果が None なら
    /// 既に kill された = 中断) のセマンティクス確認。
    #[tokio::test]
    async fn untrack_child_after_kill_tracked_returns_none() {
        // 別 test の残留があれば drain。
        let _ = kill_tracked_processes().await;

        let mut spawn = if cfg!(target_os = "windows") {
            tokio::process::Command::new("cmd")
        } else {
            tokio::process::Command::new("true")
        };
        if cfg!(target_os = "windows") {
            spawn.args(["/c", "rem"]);
        }
        let child = spawn.spawn().expect("spawn dummy child failed");

        let id = track_child(TrackedChild::no_job(child)).await;
        // kill_tracked_processes が tracker を drain して全 child を kill する
        let _killed = kill_tracked_processes().await.unwrap();
        let recovered = untrack_child(id).await;
        assert!(
            recovered.is_none(),
            "untrack_child should return None after kill_tracked_processes drained the tracker"
        );
    }

    /// #466 -- `out_time_ms=` (actually microseconds per the ffmpeg
    /// `-progress` contract) parses to the numeric value. Leading/trailing
    /// whitespace and a trailing `\r` (Windows line endings) are handled.
    #[test]
    fn parse_progress_line_accepts_out_time_ms() {
        assert_eq!(
            parse_progress_line("out_time_ms=1500000"),
            Some(ProgressSignal::OutTimeMs(1_500_000))
        );
        assert_eq!(
            parse_progress_line("  out_time_ms=42  "),
            Some(ProgressSignal::OutTimeMs(42))
        );
        // Newer ffmpeg builds use out_time_us
        assert_eq!(
            parse_progress_line("out_time_us=2000000"),
            Some(ProgressSignal::OutTimeMs(2_000_000))
        );
    }

    /// #466 -- `progress=end` is the terminal signal; everything else
    /// (bitrate, speed, fps, ...) must return None so we don't emit noise.
    #[test]
    fn parse_progress_line_detects_end_and_ignores_others() {
        assert_eq!(parse_progress_line("progress=end"), Some(ProgressSignal::End));
        assert_eq!(parse_progress_line("progress=continue"), None);
        assert_eq!(parse_progress_line("bitrate=512.0kbits/s"), None);
        assert_eq!(parse_progress_line("speed=1.5x"), None);
        assert_eq!(parse_progress_line(""), None);
        assert_eq!(parse_progress_line("random unrelated line"), None);
    }

    /// #466 -- `tail_string` must bound the returned length at `max_bytes`.
    /// Exercising with a string larger than the bound ensures we always
    /// drop the oldest bytes, never the newest (the tail is what matters
    /// for error diagnostics).
    #[test]
    fn tail_string_respects_max_bytes() {
        let big: Vec<u8> = (0..5000).map(|i| b'a' + (i % 26) as u8).collect();
        let tail = tail_string(&big, 100);
        assert!(tail.len() <= 100, "tail too long: {}", tail.len());
        assert!(tail.ends_with(big[big.len() - 1] as char), "tail lost end");
    }

    /// #466 -- `tail_string` returns the whole buffer when it already fits
    /// under the limit, with leading/trailing whitespace trimmed.
    #[test]
    fn tail_string_returns_whole_buffer_when_small() {
        let buf = b"  short message\n";
        assert_eq!(tail_string(buf, 2048), "short message");
    }

    // -- #813 run-id stamping (越境イベント遮断) ---------------------------

    #[test]
    fn stamp_run_id_sets_field() {
        let p = DetectProgress {
            phase: "scan".to_string(),
            ..Default::default()
        };
        let stamped = stamp_run_id(p, "run-abc");
        assert_eq!(stamped.run_id.as_deref(), Some("run-abc"));
    }

    #[test]
    fn stamp_run_id_serializes_into_payload() {
        let stamped = stamp_run_id(
            DetectProgress {
                phase: "done".to_string(),
                ..Default::default()
            },
            "run-xyz",
        );
        let json = serde_json::to_string(&stamped).expect("serialize");
        assert!(
            json.contains("\"run_id\":\"run-xyz\""),
            "run_id missing from emitted payload: {json}"
        );
    }

    #[test]
    fn detect_progress_omits_run_id_when_unset() {
        // skip_serializing_if pin: 未 stamp の event は run_id を wire に
        // 載せない (forward-compat、CLI が将来 run_id を持たない前提)。
        let p = DetectProgress {
            phase: "scan".to_string(),
            ..Default::default()
        };
        let json = serde_json::to_string(&p).expect("serialize");
        assert!(!json.contains("run_id"), "run_id leaked when unset: {json}");
    }

    // -- #569 detect progress streaming -----------------------------------

    #[test]
    fn parse_detect_progress_line_handles_basic_event() {
        let line = r#"{"phase":"scan","completed":12,"total":100,"elapsed_s":1.25}"#;
        let parsed = parse_detect_progress_line(line).expect("should parse");
        assert_eq!(parsed.phase, "scan");
        assert_eq!(parsed.completed, Some(12));
        assert_eq!(parsed.total, Some(100));
        assert_eq!(parsed.elapsed_s, Some(1.25));
    }

    #[test]
    fn parse_detect_progress_line_handles_done_with_metadata_path() {
        let line = r#"{"phase":"done","metadata_path":"C:/out/metadata.json","matches":3,"elapsed_s":42.5}"#;
        let parsed = parse_detect_progress_line(line).expect("should parse");
        assert_eq!(parsed.phase, "done");
        assert_eq!(
            parsed.metadata_path.as_deref(),
            Some("C:/out/metadata.json")
        );
        assert_eq!(parsed.matches, Some(3));
    }

    #[test]
    fn parse_detect_progress_line_returns_none_for_blank_line() {
        assert!(parse_detect_progress_line("").is_none());
        assert!(parse_detect_progress_line("   \n").is_none());
    }

    #[test]
    fn parse_detect_progress_line_returns_none_for_non_json() {
        assert!(parse_detect_progress_line("Probing: video.mkv").is_none());
        assert!(parse_detect_progress_line("not even close").is_none());
    }

    #[test]
    fn parse_detect_progress_line_ignores_unknown_extra_fields() {
        // Unknown extras must not abort parsing -- the CLI is allowed to
        // grow new optional fields without breaking the GUI.
        let line = r#"{"phase":"scan","completed":1,"total":2,"future_field":"hello"}"#;
        let parsed = parse_detect_progress_line(line).expect("should parse");
        assert_eq!(parsed.phase, "scan");
    }

    #[test]
    fn parse_detect_progress_line_handles_probing_metadata() {
        let line = r#"{"phase":"probing","duration_s":600.0,"width":1920,"height":1080,"fps":60.0,"codec":"h264","elapsed_s":0.4}"#;
        let parsed = parse_detect_progress_line(line).expect("should parse");
        assert_eq!(parsed.phase, "probing");
        assert_eq!(parsed.duration_s, Some(600.0));
        assert_eq!(parsed.width, Some(1920));
        assert_eq!(parsed.fps, Some(60.0));
        assert_eq!(parsed.codec.as_deref(), Some("h264"));
    }

    // -- #648 truncate_and_escape (parse_detect_progress_line warn 出力前処理)

    #[test]
    fn truncate_and_escape_empty_returns_empty() {
        assert_eq!(truncate_and_escape("", 64), "");
    }

    #[test]
    fn truncate_and_escape_zero_max_returns_empty() {
        assert_eq!(truncate_and_escape("hello", 0), "");
    }

    #[test]
    fn truncate_and_escape_short_ascii_returned_verbatim() {
        assert_eq!(truncate_and_escape("hello", 64), "hello");
    }

    #[test]
    fn truncate_and_escape_truncates_long_input_at_char_boundary() {
        let long = "a".repeat(128);
        assert_eq!(truncate_and_escape(&long, 64).chars().count(), 64);
    }

    #[test]
    fn truncate_and_escape_preserves_tab_newline_cr() {
        assert_eq!(truncate_and_escape("a\tb\nc\rd", 64), "a\tb\nc\rd");
    }

    #[test]
    fn truncate_and_escape_escapes_other_control_chars() {
        assert_eq!(truncate_and_escape("a\x01b", 64), "a\\x01b");
        assert_eq!(truncate_and_escape("a\x1Fb", 64), "a\\x1Fb");
    }

    #[test]
    fn truncate_and_escape_handles_multibyte_char_boundary() {
        // "まったく" は 4 chars (各 3 bytes UTF-8 = 12 bytes)。
        // max_chars=3 で 3 chars 取得・byte boundary で panic しないことを確認。
        assert_eq!(truncate_and_escape("まったく", 3).chars().count(), 3);
    }

    // -- #648 parse_detect_progress_line_with_warn (DI variant)

    #[test]
    fn parse_with_warn_empty_line_no_warn() {
        let mut warns: Vec<String> = Vec::new();
        let result = parse_detect_progress_line_with_warn("", |m| warns.push(m.to_string()));
        assert!(result.is_none());
        assert!(warns.is_empty());
    }

    #[test]
    fn parse_with_warn_whitespace_only_no_warn() {
        let mut warns: Vec<String> = Vec::new();
        let result =
            parse_detect_progress_line_with_warn("   \n", |m| warns.push(m.to_string()));
        assert!(result.is_none());
        assert!(warns.is_empty());
    }

    #[test]
    fn parse_with_warn_valid_json_no_warn() {
        let mut warns: Vec<String> = Vec::new();
        let line = r#"{"phase":"scan","completed":12,"total":100,"elapsed_s":1.25}"#;
        let result =
            parse_detect_progress_line_with_warn(line, |m| warns.push(m.to_string()));
        assert!(result.is_some());
        assert!(warns.is_empty());
    }

    #[test]
    fn parse_with_warn_malformed_json_emits_warn() {
        let mut warns: Vec<String> = Vec::new();
        let result =
            parse_detect_progress_line_with_warn("not json", |m| warns.push(m.to_string()));
        assert!(result.is_none());
        assert_eq!(warns.len(), 1);
        assert!(warns[0].contains("malformed JSON"));
        assert!(warns[0].contains("\"not json\""));
        assert!(warns[0].contains("len=8"));
    }

    #[test]
    fn parse_with_warn_long_malformed_json_truncated_and_escaped() {
        let mut warns: Vec<String> = Vec::new();
        // 67 chars (63 x + 制御文字 \x01 + 3 y) を作り、64 char truncate と
        // \x01 → \\x01 escape の両方が warn message に現れることを確認する
        let line = format!("{}{}", "x".repeat(63), "\x01yyy");
        let result =
            parse_detect_progress_line_with_warn(&line, |m| warns.push(m.to_string()));
        assert!(result.is_none());
        assert_eq!(warns.len(), 1);
        // 64 char truncate (\x01 escape の 4 char を含む、x 63 + control の 1 char = 64 char、escape は format 後に 4 char に膨れる)
        // よって warn message 内には `\\x01` が現れる
        assert!(
            warns[0].contains("\\x01"),
            "expected escaped control char in warn message: {}",
            warns[0]
        );
        // 元 len は 67 (63 + 4)
        assert!(
            warns[0].contains(&format!("len={}", line.len())),
            "expected original length in warn message: {}",
            warns[0]
        );
    }

    #[test]
    fn detect_command_args_includes_required_flags() {
        let args = detect_command_args(
            "C:/videos/in.mkv",
            "C:/out/run-01",
            &DetectParams::default(),
        );
        assert_eq!(args[0], "detect");
        assert_eq!(args[1], "C:/videos/in.mkv");
        assert_eq!(args[2], "-o");
        assert_eq!(args[3], "C:/out/run-01");
        assert!(args.iter().any(|a| a == "--progress-format"));
        assert!(args.iter().any(|a| a == "json"));
    }

    #[test]
    fn detect_command_args_omits_optional_flags_when_unset() {
        let args = detect_command_args(
            "in.mkv",
            "out",
            &DetectParams::default(),
        );
        let joined = args.join(" ");
        assert!(!joined.contains("--blackout-threshold"));
        assert!(!joined.contains("--no-audio"));
        assert!(!joined.contains("--no-cache"));
        assert!(!joined.contains("--gpu"));
        assert!(!joined.contains("--no-gpu"));
        assert!(!joined.contains("--workers"));
    }

    #[test]
    fn detect_command_args_emits_blackout_threshold_when_provided() {
        let args = detect_command_args(
            "in.mkv",
            "out",
            &DetectParams {
                blackout_threshold: Some(20.0),
                ..Default::default()
            },
        );
        let idx = args
            .iter()
            .position(|a| a == "--blackout-threshold")
            .expect("flag missing");
        assert_eq!(args[idx + 1], "20");
    }

    #[test]
    fn detect_command_args_translates_gpu_tristate() {
        // Some(true) -> --gpu
        let args_on = detect_command_args(
            "in.mkv",
            "out",
            &DetectParams {
                gpu: Some(true),
                ..Default::default()
            },
        );
        assert!(args_on.iter().any(|a| a == "--gpu"));
        assert!(!args_on.iter().any(|a| a == "--no-gpu"));

        // Some(false) -> --no-gpu
        let args_off = detect_command_args(
            "in.mkv",
            "out",
            &DetectParams {
                gpu: Some(false),
                ..Default::default()
            },
        );
        assert!(args_off.iter().any(|a| a == "--no-gpu"));
        assert!(!args_off.iter().any(|a| a == "--gpu"));

        // None -> neither flag (CLI auto-selects)
        let args_auto = detect_command_args(
            "in.mkv",
            "out",
            &DetectParams::default(),
        );
        assert!(!args_auto.iter().any(|a| a == "--gpu" || a == "--no-gpu"));
    }

    #[test]
    fn detect_command_args_emits_no_audio_only_when_true() {
        let args_on = detect_command_args(
            "in.mkv",
            "out",
            &DetectParams {
                no_audio: Some(true),
                ..Default::default()
            },
        );
        assert!(args_on.iter().any(|a| a == "--no-audio"));

        let args_off = detect_command_args(
            "in.mkv",
            "out",
            &DetectParams {
                no_audio: Some(false),
                ..Default::default()
            },
        );
        assert!(!args_off.iter().any(|a| a == "--no-audio"));
    }

    #[test]
    fn detect_command_args_includes_workers_when_provided() {
        let args = detect_command_args(
            "in.mkv",
            "out",
            &DetectParams {
                workers: Some(8),
                ..Default::default()
            },
        );
        let idx = args
            .iter()
            .position(|a| a == "--workers")
            .expect("flag missing");
        assert_eq!(args[idx + 1], "8");
    }

    #[test]
    fn detect_command_args_includes_gpu_vendor_when_provided() {
        let args = detect_command_args(
            "in.mkv",
            "out",
            &DetectParams {
                gpu_vendor: Some("nvidia".to_string()),
                ..Default::default()
            },
        );
        let idx = args
            .iter()
            .position(|a| a == "--gpu-vendor")
            .expect("flag missing");
        assert_eq!(args[idx + 1], "nvidia");
    }

    #[test]
    fn detect_command_args_skips_empty_gpu_vendor() {
        let args = detect_command_args(
            "in.mkv",
            "out",
            &DetectParams {
                gpu_vendor: Some(String::new()),
                ..Default::default()
            },
        );
        assert!(!args.iter().any(|a| a == "--gpu-vendor"));
    }

    // -- #646 resolve_allaganeye_command parts -----------------------------

    /// Custom path via env var wins.
    #[test]
    fn resolve_from_env_returns_path_when_set() {
        let cmd = resolve_from_env(Some("C:/custom/path/allaganeye.exe".to_string()))
            .expect("non-empty env should resolve");
        assert_eq!(cmd.program, "C:/custom/path/allaganeye.exe");
        assert!(cmd.prefix_args.is_empty());
        assert!(cmd.cwd.is_none());
    }

    /// Empty / missing env var falls through (returns None) so the
    /// caller can move on to the next resolution stage.
    #[test]
    fn resolve_from_env_returns_none_for_empty_or_missing() {
        assert!(resolve_from_env(None).is_none());
        assert!(resolve_from_env(Some(String::new())).is_none());
    }

    /// Bundle resource dir resolves to `<dir>/allaganeye.bat` when the
    /// bat exists. Mirrors the Portable ZIP layout produced by #615.
    #[test]
    fn resolve_from_resource_dir_picks_bundled_bat() {
        let tmp = TempDir::new().unwrap();
        let bat = tmp.path().join("allaganeye.bat");
        fs::write(&bat, "@echo off\r\n").unwrap();

        let cmd = resolve_from_resource_dir(tmp.path())
            .expect("bat present should resolve");
        assert_eq!(cmd.program, bat.to_string_lossy().to_string());
        assert!(cmd.prefix_args.is_empty());
        assert!(cmd.cwd.is_none());
    }

    /// Resource dir without the bat returns None (dev / non-bundled
    /// build) so the python fallback runs.
    #[test]
    fn resolve_from_resource_dir_returns_none_when_missing() {
        let tmp = TempDir::new().unwrap();
        assert!(resolve_from_resource_dir(tmp.path()).is_none());
    }

    /// Python fallback always builds `python -m allaganeye` regardless
    /// of cwd.
    #[test]
    fn resolve_python_fallback_uses_minus_m_allaganeye() {
        let cmd = resolve_python_fallback(None);
        assert_eq!(cmd.program, "python");
        assert_eq!(cmd.prefix_args, vec!["-m".to_string(), "allaganeye".to_string()]);
        assert!(cmd.cwd.is_none());

        let tmp = TempDir::new().unwrap();
        let cmd = resolve_python_fallback(Some(tmp.path().to_path_buf()));
        assert_eq!(cmd.cwd.as_deref(), Some(tmp.path()));
    }

    /// `find_worktree_root` walks ancestors looking for the directory
    /// that holds `pyproject.toml`. The dev fallback uses this to
    /// anchor `cwd` so `python -m allaganeye` finds the worktree's
    /// `allaganeye/` package.
    #[test]
    fn find_worktree_root_locates_pyproject_anchor() {
        let tmp = TempDir::new().unwrap();
        // Layout: <root>/pyproject.toml + <root>/sub/<deeper>
        fs::write(tmp.path().join("pyproject.toml"), b"").unwrap();
        let deeper = tmp.path().join("sub").join("deeper");
        fs::create_dir_all(&deeper).unwrap();

        let canonical_root = fs::canonicalize(tmp.path()).unwrap();
        let canonical_deeper = fs::canonicalize(&deeper).unwrap();

        let found = find_worktree_root(Some(canonical_deeper))
            .expect("anchor should be found");
        let canonical_found = fs::canonicalize(&found).unwrap();
        assert_eq!(canonical_found, canonical_root);
    }

    /// `find_worktree_root` returns None when no anchor exists in the
    /// ancestor chain (callers fall back to a cwd-less command spec).
    #[test]
    fn find_worktree_root_returns_none_without_anchor() {
        let tmp = TempDir::new().unwrap();
        // Bare directory with no pyproject.toml at any ancestor.
        let nested = tmp.path().join("a").join("b");
        fs::create_dir_all(&nested).unwrap();
        // Note: the test process's parent ancestors might still contain
        // a real `pyproject.toml` (e.g. when run from inside this repo)
        // so we rely on the helper's None branch via Option::None
        // input instead of trusting tmp ancestry.
        assert!(find_worktree_root(None).is_none());
    }

    #[test]
    fn detect_progress_skips_none_fields_in_json_serde() {
        // Reuse the wire format in case some integration consumer
        // round-trips the struct via JSON instead of the Tauri event
        // bridge -- skip_serializing_if must drop None entries so we
        // mirror the Python side's compact format.
        let progress = DetectProgress {
            phase: "scan".to_string(),
            completed: Some(1),
            total: Some(10),
            ..Default::default()
        };
        let serialized = serde_json::to_string(&progress).unwrap();
        assert!(serialized.contains("\"phase\":\"scan\""));
        assert!(serialized.contains("\"completed\":1"));
        assert!(!serialized.contains("metadata_path"));
        assert!(!serialized.contains("\"matches\""));
        assert!(!serialized.contains("\"message\""));
    }

    /// #656 review Round 1 摘出 #3 -- detect 経路 stdout reader
    /// (`start_detect` 内 `read_until` + 改行 trim + `from_utf8_lossy`)
    /// の core logic を bytes 入力で再現し、invalid UTF-8 byte は U+FFFD
    /// に置換され、CRLF は両方 trim されることを確認する。production
    /// code は inline (関数抽出未) のため同型ロジックを test 内で再構築。
    #[tokio::test]
    async fn stdout_decode_replaces_invalid_utf8_and_trims_crlf() {
        // 0x83, 0x84 は単独で UTF-8 invalid (continuation byte 領域)。
        // cp932 では multi-byte の前半 byte で日本語 path に頻出する。
        let raw: &[u8] = &[
            b'h', b'i', 0x83, 0x84, b'\n', b'b', b'y', b'e', b'\r', b'\n',
        ];
        let mut reader = BufReader::new(raw);
        let mut buf: Vec<u8> = Vec::new();

        // line 1: invalid byte は from_utf8_lossy で U+FFFD に置換
        let n = reader.read_until(b'\n', &mut buf).await.unwrap();
        assert!(n > 0);
        while matches!(buf.last(), Some(b'\n') | Some(b'\r')) {
            buf.pop();
        }
        let line = String::from_utf8_lossy(&buf);
        assert_eq!(line, "hi\u{FFFD}\u{FFFD}");

        // line 2: CRLF (\r\n) は while ループで両方 pop
        buf.clear();
        let n = reader.read_until(b'\n', &mut buf).await.unwrap();
        assert!(n > 0);
        while matches!(buf.last(), Some(b'\n') | Some(b'\r')) {
            buf.pop();
        }
        let line = String::from_utf8_lossy(&buf);
        assert_eq!(line, "bye");

        // EOF: read_until returns Ok(0)
        buf.clear();
        let n = reader.read_until(b'\n', &mut buf).await.unwrap();
        assert_eq!(n, 0);
    }

    // ----------------------------------------------------------------
    // #669 -- read_error_log_tail
    // ----------------------------------------------------------------

    #[test]
    fn read_error_log_tail_returns_last_n_lines() {
        use std::io::Write;
        let tmp = TempDir::new().expect("tempdir");
        let log_dir = tmp.path();
        let date = logging::current_ymd_compact();
        let log_path = log_dir.join(format!("error-{}.log", date));
        {
            let mut f = std::fs::File::create(&log_path).unwrap();
            for i in 0..500 {
                writeln!(f, "line {}", i).unwrap();
            }
        }
        let result = read_error_log_tail_inner(log_dir, 300).unwrap();
        let lines: Vec<&str> = result.lines().collect();
        assert_eq!(lines.len(), 300);
        assert_eq!(lines[0], "line 200");
        assert_eq!(lines[299], "line 499");
    }

    #[test]
    fn read_error_log_tail_returns_full_log_when_shorter_than_count() {
        use std::io::Write;
        let tmp = TempDir::new().expect("tempdir");
        let log_dir = tmp.path();
        let date = logging::current_ymd_compact();
        let log_path = log_dir.join(format!("error-{}.log", date));
        {
            let mut f = std::fs::File::create(&log_path).unwrap();
            for i in 0..50 {
                writeln!(f, "line {}", i).unwrap();
            }
        }
        let result = read_error_log_tail_inner(log_dir, 300).unwrap();
        let lines: Vec<&str> = result.lines().collect();
        assert_eq!(lines.len(), 50);
        assert_eq!(lines[0], "line 0");
        assert_eq!(lines[49], "line 49");
    }

    #[test]
    fn read_error_log_tail_falls_back_to_previous_day() {
        use std::io::Write;
        let tmp = TempDir::new().expect("tempdir");
        let log_dir = tmp.path();
        let yesterday = logging::ymd_compact_yesterday();
        let log_path = log_dir.join(format!("error-{}.log", yesterday));
        {
            let mut f = std::fs::File::create(&log_path).unwrap();
            writeln!(f, "yesterday line").unwrap();
        }
        // 当日 log は存在しない → 前日 log にフォールバック
        let result = read_error_log_tail_inner(log_dir, 300).unwrap();
        assert!(result.contains("yesterday line"));
    }

    #[test]
    fn read_error_log_tail_skips_empty_today_to_yesterday() {
        use std::io::Write;
        let tmp = TempDir::new().expect("tempdir");
        let log_dir = tmp.path();
        // 当日 log は空 (0 byte)
        let today = logging::current_ymd_compact();
        std::fs::File::create(log_dir.join(format!("error-{}.log", today))).unwrap();
        // 前日 log は内容あり
        let yesterday = logging::ymd_compact_yesterday();
        {
            let mut f = std::fs::File::create(log_dir.join(format!("error-{}.log", yesterday)))
                .unwrap();
            writeln!(f, "yesterday line").unwrap();
        }
        let result = read_error_log_tail_inner(log_dir, 300).unwrap();
        assert!(result.contains("yesterday line"));
    }

    #[test]
    fn read_error_log_tail_returns_empty_for_missing_log() {
        let tmp = TempDir::new().expect("tempdir");
        let log_dir = tmp.path();
        // 当日も前日も log なし → 空文字列 (エラーでなく)
        let result = read_error_log_tail_inner(log_dir, 300).unwrap();
        assert_eq!(result, "");
    }

    // ----------------------------------------------------------------
    // #669 -- probe_environment_info
    // ----------------------------------------------------------------

    #[test]
    fn probe_environment_info_returns_non_empty_basics() {
        let probe = probe_environment_info_inner();
        assert_eq!(probe.allaganeye_version, env!("CARGO_PKG_VERSION"));
        assert!(!probe.os_name.is_empty(), "os_name should be non-empty");
        assert!(!probe.cpu_info.is_empty(), "cpu_info should be non-empty");
        // memory_total_gb は実機 (CI / dev) では必ず >0 になるはず
        assert!(
            probe.memory_total_gb.is_some_and(|m| m > 0.0),
            "memory_total_gb should be Some(>0.0), got {:?}",
            probe.memory_total_gb
        );
    }

    #[test]
    fn probe_environment_info_cpu_info_contains_thread_count() {
        let probe = probe_environment_info_inner();
        // cpu_info は "<brand> (<N>C/<M>T)" or "<brand> (<N>T)" or "<N> threads" format
        assert!(
            probe.cpu_info.contains('T') || probe.cpu_info.contains("threads"),
            "cpu_info should mention thread count, got '{}'",
            probe.cpu_info
        );
    }

    #[test]
    fn probe_environment_info_serializes_with_snake_case_keys() {
        // Frontend (TS) expects snake_case (matches metadata.generated.ts SystemInfo pattern)
        let probe = EnvironmentProbe {
            allaganeye_version: "0.2.0".to_string(),
            os_name: "Test OS 11".to_string(),
            cpu_info: "Test CPU (16C/32T)".to_string(),
            memory_total_gb: Some(64.0),
            disk_free_gb: Some(100.0),
            disk_total_gb: Some(500.0),
            disk_drive: Some("E:".to_string()),
        };
        let json = serde_json::to_value(&probe).unwrap();
        assert_eq!(json["allaganeye_version"], "0.2.0");
        assert_eq!(json["os_name"], "Test OS 11");
        assert_eq!(json["cpu_info"], "Test CPU (16C/32T)");
        assert_eq!(json["memory_total_gb"], 64.0);
        assert_eq!(json["disk_drive"], "E:");
    }

    #[test]
    fn probe_environment_info_disk_drive_strips_trailing_separator() {
        // Windows sysinfo の mount_point は "C:\\" 形式。disk_drive は trailing
        // separator なし ("C:") であること (bug_report.yml placeholder の "on E:" 形式)。
        let probe = probe_environment_info_inner();
        if let Some(drive) = probe.disk_drive {
            assert!(
                !drive.ends_with('\\') && !drive.ends_with('/'),
                "disk_drive should not end with separator, got '{}'",
                drive
            );
        }
    }

    #[test]
    fn read_error_log_tail_zero_lines_returns_empty() {
        use std::io::Write;
        let tmp = TempDir::new().expect("tempdir");
        let log_dir = tmp.path();
        let date = logging::current_ymd_compact();
        let log_path = log_dir.join(format!("error-{}.log", date));
        {
            let mut f = std::fs::File::create(&log_path).unwrap();
            writeln!(f, "line").unwrap();
        }
        // line_count=0 を要求された場合は空文字列を返す (loop 暴走防止)
        let result = read_error_log_tail_inner(log_dir, 0).unwrap();
        assert_eq!(result, "");
    }

    #[test]
    fn read_error_log_tail_caps_at_max_tail_lines() {
        // /iterate-review Round 2 #2: line_count が MAX_TAIL_LINES (10000) を
        // 超えても allocation panic せず、ファイル全行 (実際は MAX 以下) を
        // 返すことを確認 (defense-in-depth)。
        use std::io::Write;
        let tmp = TempDir::new().expect("tempdir");
        let log_dir = tmp.path();
        let date = logging::current_ymd_compact();
        let log_path = log_dir.join(format!("error-{}.log", date));
        {
            let mut f = std::fs::File::create(&log_path).unwrap();
            // 500 行のみ書く (MAX=10000 より少ない、cap 適用 path を確認しつつ
            // 全行返却を assert)
            for i in 0..500 {
                writeln!(f, "line {}", i).unwrap();
            }
        }
        // 巨大な line_count を渡しても panic せず 500 行返る (= ファイル全体)
        let result = read_error_log_tail_inner(log_dir, usize::MAX).unwrap();
        let lines: Vec<&str> = result.lines().collect();
        assert_eq!(lines.len(), 500);
        assert_eq!(lines[0], "line 0");
        assert_eq!(lines[499], "line 499");
    }
}

#[cfg(test)]
mod enumerate_h264_encoders_tests {
    use super::*;

    #[test]
    fn parses_python_json_array_output() {
        let raw = r#"[
            {"slot_index": 0, "encoder_kind": "Nvenc", "display_label": "NVENC #1"},
            {"slot_index": 1, "encoder_kind": "Nvenc", "display_label": "NVENC #2"}
        ]"#;
        let parsed: Vec<EncoderSlotJson> = serde_json::from_str(raw).unwrap();
        assert_eq!(parsed.len(), 2);
        assert_eq!(parsed[0].encoder_kind, "Nvenc");
    }

    #[test]
    fn empty_array_is_valid() {
        let raw = r#"[]"#;
        let parsed: Vec<EncoderSlotJson> = serde_json::from_str(raw).unwrap();
        assert!(parsed.is_empty());
    }
}

#[cfg(test)]
mod start_export_wire_tests {
    use super::*;

    #[test]
    fn parses_progress_line() {
        let line = r#"{"type":"progress","match_index":2,"percent":33.5,"stage":"encoding"}"#;
        let ev = parse_wire_event(line).expect("parse");
        match ev {
            WireEvent::Progress { match_index, percent, stage } => {
                assert_eq!(match_index, 2);
                assert!((percent - 33.5).abs() < 0.001);
                assert_eq!(stage, "encoding");
            }
            _ => panic!("expected Progress"),
        }
    }

    #[test]
    fn parses_summary_line() {
        let line = r#"{"type":"summary","success":3,"failure":1,"skipped":0,"cancelled":false}"#;
        let ev = parse_wire_event(line).expect("parse");
        match ev {
            WireEvent::Summary { success, failure, skipped, cancelled } => {
                assert_eq!(success, 3);
                assert_eq!(failure, 1);
                assert_eq!(skipped, 0);
                assert!(!cancelled);
            }
            _ => panic!("expected Summary"),
        }
    }

    #[test]
    fn ignores_unknown_type() {
        let line = r#"{"type":"future_unknown","extra":"foo"}"#;
        assert!(matches!(parse_wire_event(line), Some(WireEvent::Unknown)));
    }

    #[test]
    fn ignores_malformed_json() {
        assert!(parse_wire_event("not json {").is_none());
    }

    #[test]
    fn ignores_empty_line() {
        assert!(parse_wire_event("").is_none());
    }
}
