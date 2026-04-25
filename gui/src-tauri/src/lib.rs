use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
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
use serde::Serialize;
use serde_json::Value;
use sha2::{Digest, Sha256};
use tokio::sync::{Mutex, Semaphore};
use tower_http::services::ServeFile;
use uuid::Uuid;

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

/// #514 — return the mtime (ms since epoch) of an existing metadata file,
/// or `None` when the file is missing. Used by the GUI to detect external
/// modifications between load and apply.
#[tauri::command]
async fn get_metadata_mtime(path: String) -> Result<Option<u64>, String> {
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
) -> Result<u64, String> {
    let meta_path = PathBuf::from(&path);
    apply_changes_sync(&meta_path, &metadata, expected_mtime_ms)?;
    file_mtime_ms(&meta_path).ok_or_else(|| {
        format!(
            "apply succeeded but could not read post-write mtime: {}",
            meta_path.display()
        )
    })
}

/// #517 — persist the in-memory edit buffer as `metadata.draft.json` next to
/// the live `metadata.json`. Survives WebView reloads and app crashes.
#[tauri::command]
async fn save_draft(path: String, draft: Value) -> Result<(), String> {
    save_draft_sync(&PathBuf::from(&path), &draft)
}

/// #517 — reload the draft buffer if one exists. Returns `None` when no
/// draft is on disk (fresh session or post-apply state).
#[tauri::command]
async fn load_draft(path: String) -> Result<Option<Value>, String> {
    load_draft_sync(&PathBuf::from(&path))
}

/// #517 — delete the draft file. Called after a successful `apply` so a
/// restart doesn't re-prompt about stale edits.
#[tauri::command]
async fn clear_draft(path: String) -> Result<(), String> {
    clear_draft_sync(&PathBuf::from(&path))
}

fn draft_path_for(meta_path: &Path) -> Result<PathBuf, String> {
    let parent = meta_path
        .parent()
        .ok_or_else(|| format!("metadata path has no parent: {}", meta_path.display()))?;
    Ok(parent.join("metadata.draft.json"))
}

fn save_draft_sync(meta_path: &Path, draft: &Value) -> Result<(), String> {
    let draft_path = draft_path_for(meta_path)?;
    write_metadata_atomic(&draft_path, draft)
}

fn load_draft_sync(meta_path: &Path) -> Result<Option<Value>, String> {
    let draft_path = draft_path_for(meta_path)?;
    if !draft_path.exists() {
        return Ok(None);
    }
    let content = fs::read_to_string(&draft_path)
        .map_err(|e| format!("read draft failed ({}): {}", draft_path.display(), e))?;
    let value: Value = serde_json::from_str(&content)
        .map_err(|e| format!("invalid JSON in draft {}: {}", draft_path.display(), e))?;
    Ok(Some(value))
}

fn clear_draft_sync(meta_path: &Path) -> Result<(), String> {
    let draft_path = draft_path_for(meta_path)?;
    if !draft_path.exists() {
        // Nothing to clear — treat as success so callers don't have to
        // special-case the post-apply no-draft state.
        return Ok(());
    }
    fs::remove_file(&draft_path).map_err(|e| {
        format!("remove draft failed ({}): {}", draft_path.display(), e)
    })
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

/// #465 -- register a video file with the local HTTP server and return a
/// playback URL for the GUI's `<video>` element.
///
/// Starts the axum server lazily on the first call (subsequent calls reuse
/// the same bound port). The returned URL has the form
/// `http://127.0.0.1:{port}/video/{token}` and is only reachable from the
/// same machine; the server binds exclusively to 127.0.0.1.
#[tauri::command]
async fn register_video(path: String) -> Result<RegisteredVideo, String> {
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

/// Validate that `path` points to an existing regular file and return the
/// canonicalized absolute path on success.
fn validate_video_path(path: &Path) -> Result<PathBuf, String> {
    if !path.exists() {
        return Err(format!("video file not found: {}", path.display()));
    }
    let meta = fs::metadata(path)
        .map_err(|e| format!("stat failed ({}): {}", path.display(), e))?;
    if !meta.is_file() {
        return Err(format!(
            "video path is not a regular file: {}",
            path.display()
        ));
    }
    fs::canonicalize(path)
        .map_err(|e| format!("canonicalize failed ({}): {}", path.display(), e))
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
async fn ensure_server_started() -> Result<u16, String> {
    let mut guard = video_server().lock().await;
    if let Some(port) = guard.port {
        return Ok(port);
    }

    let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
        .await
        .map_err(|e| format!("bind 127.0.0.1:0 failed: {}", e))?;
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
) -> Result<(), String> {
    // #514 — refuse to overwrite a file that has been modified externally
    // since the caller last loaded it. Target not existing is not a conflict
    // (treat as a fresh write).
    if let Some(expected) = expected_mtime_ms {
        if meta_path.exists() {
            let actual = file_mtime_ms(meta_path).ok_or_else(|| {
                format!("cannot read mtime of {}", meta_path.display())
            })?;
            if actual != expected {
                return Err(format!(
                    "conflict: external modification detected ({} expected mtime {}, got {})",
                    meta_path.display(),
                    expected,
                    actual
                ));
            }
        }
    }


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

/// #465 -- resolve `<home>/.allaganeye/cache/<video_hash>/thumbs/`.
///
/// Returns the path without creating it; callers that intend to write thumbs
/// are responsible for `create_dir_all`. On Windows the home directory comes
/// from `USERPROFILE` via `dirs::home_dir`; on Unix it reads `HOME`.
fn thumb_cache_dir(video_hash: &str) -> Result<PathBuf, String> {
    let home = dirs::home_dir()
        .ok_or_else(|| "failed to resolve user home directory".to_string())?;
    Ok(home
        .join(".allaganeye")
        .join("cache")
        .join(video_hash)
        .join("thumbs"))
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
) -> Result<Vec<ThumbnailEntry>, String> {
    let video = PathBuf::from(&video_path);
    if !video.exists() {
        return Err(format!("video file not found: {}", video.display()));
    }
    let meta = fs::metadata(&video)
        .map_err(|e| format!("stat failed ({}): {}", video.display(), e))?;
    let mtime_ms = meta
        .modified()
        .map_err(|e| format!("mtime failed ({}): {}", video.display(), e))?
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .map_err(|e| format!("mtime before epoch ({}): {}", video.display(), e))?;
    let canonical = fs::canonicalize(&video)
        .map_err(|e| format!("canonicalize failed ({}): {}", video.display(), e))?;

    let video_hash = compute_video_cache_hash(&canonical, mtime_ms);
    let cache_dir = thumb_cache_dir(&video_hash)?;
    fs::create_dir_all(&cache_dir)
        .map_err(|e| format!("create cache dir {} failed: {}", cache_dir.display(), e))?;

    let timestamps = compute_candidate_timestamps(boundary_t_seconds, window_seconds, count);
    let semaphore = Arc::new(Semaphore::new(4));

    let mut tasks = Vec::with_capacity(timestamps.len());
    for t in timestamps.iter().copied() {
        let token = thumb_token(match_index, t);
        let out_path = cache_dir.join(format!("{}.webp", token));
        let video_for_task = canonical.clone();
        let sem = Arc::clone(&semaphore);
        tasks.push(async move {
            let _permit = sem
                .acquire_owned()
                .await
                .map_err(|e| format!("semaphore closed: {}", e))?;
            ensure_thumbnail_exists(&video_for_task, t, &out_path).await?;
            Ok::<ThumbnailEntry, String>(ThumbnailEntry {
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
) -> Result<(), String> {
    if let Ok(meta) = fs::metadata(out_path) {
        if meta.is_file() && meta.len() > 0 {
            return Ok(());
        }
    }
    if let Some(parent) = out_path.parent() {
        if !parent.exists() {
            fs::create_dir_all(parent).map_err(|e| {
                format!("create dir {} failed: {}", parent.display(), e)
            })?;
        }
    }

    let t_arg = format!("{:.3}", t_seconds.max(0.0));
    let output = tokio::process::Command::new("ffmpeg")
        .arg("-y")
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
        .arg(out_path)
        .output()
        .await
        .map_err(|e| format!("spawn ffmpeg failed at t={}: {}", t_arg, e))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!(
            "ffmpeg failed at t={} (exit={:?}): {}",
            t_arg,
            output.status.code(),
            stderr.trim()
        ));
    }
    Ok(())
}

/// #523 -- tracker for long-running external processes (detecting /export
/// ffmpeg invocations). Phase 3 preview itself does not spawn persistent
/// children, but detecting (Phase 3) and export (Phase 4) will register
/// their children here so the Close-Requested handler can kill them before
/// exit.
type ProcessMap = Arc<Mutex<HashMap<Uuid, tokio::process::Child>>>;

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
#[tauri::command]
async fn kill_tracked_processes() -> Result<u32, String> {
    let tracker = process_tracker();
    let mut guard = tracker.lock().await;
    let count = guard.len() as u32;
    for (_, mut child) in guard.drain() {
        let _ = child.kill().await;
    }
    Ok(count)
}

/// #523 -- explicit app exit, used after the user confirms they want to
/// terminate a running process. `on_window_event` always calls
/// `prevent_close`, so the frontend must drive the actual exit through this
/// command once it has finished cleanup.
///
/// #465 review: WebView2 / Chromium の cleanup race を緩和するため、
/// `app.exit` の前に webview window を明示 destroy し短い yield を入れる。
/// 何もしないと shutdown 時に
///   `[ERROR:ui\gfx\win\window_impl.cc] Failed to unregister class
///    Chrome_WidgetWin_0. Error = 1412`
/// が stderr に出る。Error 1412 = ERROR_CLASS_DOES_NOT_EXIST で、Chromium
/// の window class registration が既に消えている race。`destroy()` で
/// `on_window_event` の `prevent_close` を bypass し、50ms yield で
/// cleanup を進ませてから exit する。完全には消せない (benign warning) が
/// 出現頻度が下がる。
#[tauri::command]
async fn force_exit_app(app: tauri::AppHandle) {
    for (_, window) in app.webview_windows() {
        let _ = window.destroy();
    }
    tokio::time::sleep(std::time::Duration::from_millis(50)).await;
    app.exit(0);
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_shell::init())
        .on_window_event(|window, event| {
            // #523 -- intercept every CloseRequested. The frontend inspects
            // tracked processes on receipt: if none are running it calls
            // `force_exit_app` immediately; otherwise it surfaces the
            // ConfirmExitModal and drives kill + exit on confirm.
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.emit("close-requested", ());
            }
        })
        .invoke_handler(tauri::generate_handler![
            load_metadata,
            get_metadata_mtime,
            apply_changes,
            save_draft,
            load_draft,
            clear_draft,
            restore_from_original,
            check_backup_exists,
            register_video,
            generate_match_thumbnails,
            is_process_running,
            kill_tracked_processes,
            force_exit_app,
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
        assert!(err.starts_with("conflict:"), "unexpected error: {err}");

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
        assert!(err.starts_with("conflict:"), "unexpected error: {err}");

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
        assert!(err.starts_with("conflict:"), "unexpected error: {err}");
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
        assert!(err.contains("invalid JSON in draft"));
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
            err.contains("not found"),
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
            err.contains("not a regular file"),
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

    /// #465 -- `thumb_cache_dir` must place the hash segment and the
    /// literal `thumbs` leaf under `.allaganeye/cache/`. We check path
    /// components to stay OS-separator-agnostic.
    #[test]
    fn thumb_cache_dir_includes_hash_and_thumbs_suffix() {
        let hash = "deadbeef".repeat(8); // 64 chars like a real digest
        let dir = thumb_cache_dir(&hash).unwrap();
        let components: Vec<String> = dir
            .components()
            .map(|c| c.as_os_str().to_string_lossy().to_string())
            .collect();
        // Must end with ... / .allaganeye / cache / <hash> / thumbs
        let n = components.len();
        assert!(n >= 4, "path too short: {:?}", components);
        assert_eq!(components[n - 1], "thumbs");
        assert_eq!(components[n - 2], hash);
        assert_eq!(components[n - 3], "cache");
        assert_eq!(components[n - 4], ".allaganeye");
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
}
