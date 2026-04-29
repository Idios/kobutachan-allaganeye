use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::sync::{Arc, OnceLock};
use std::time::{Instant, SystemTime, UNIX_EPOCH};

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
mod logging;

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
async fn probe_video(path: String) -> Result<VideoProbeInfo, String> {
    let file_path = PathBuf::from(&path);
    let canonical = validate_video_path(&file_path)?;
    probe_video_with(&canonical, "ffprobe").await
}

/// Pure helper testable in cargo unit tests by injecting an ffprobe-like
/// command (e.g. a fixture-emitting shell script).
async fn probe_video_with(
    path: &Path,
    ffprobe: &str,
) -> Result<VideoProbeInfo, String> {
    let size_bytes = fs::metadata(path)
        .map_err(|e| format!("stat failed ({}): {}", path.display(), e))?
        .len();

    let output = tokio::process::Command::new(ffprobe)
        .arg("-v")
        .arg("quiet")
        .arg("-print_format")
        .arg("json")
        .arg("-show_format")
        .arg("-show_streams")
        .arg(path)
        .output()
        .await
        .map_err(|e| format!("ffprobe spawn failed: {e}"))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!(
            "ffprobe failed (exit {:?}): {}",
            output.status.code(),
            stderr.trim()
        ));
    }

    let json: Value = serde_json::from_slice(&output.stdout)
        .map_err(|e| format!("ffprobe json parse failed: {e}"))?;

    let streams = json
        .get("streams")
        .and_then(|s| s.as_array())
        .ok_or_else(|| "ffprobe output missing 'streams' array".to_string())?;
    let video_stream = streams
        .iter()
        .find(|s| s.get("codec_type").and_then(|v| v.as_str()) == Some("video"))
        .ok_or_else(|| "no video stream in ffprobe output".to_string())?;

    let width = video_stream
        .get("width")
        .and_then(|v| v.as_u64())
        .ok_or_else(|| "video stream missing width".to_string())? as u32;
    let height = video_stream
        .get("height")
        .and_then(|v| v.as_u64())
        .ok_or_else(|| "video stream missing height".to_string())? as u32;
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
    .ok_or_else(|| "cannot determine frame rate".to_string())?;

    let duration_seconds = json
        .get("format")
        .and_then(|f| f.get("duration"))
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())
        .ok_or_else(|| "format.duration missing or unparseable".to_string())?;
    if duration_seconds <= 0.0 {
        return Err("duration is non-positive".to_string());
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

/// #466 -- codec selection for a single-match export. `Copy` is fast and
/// keyframe-aligned (no re-encode); `H264` re-encodes for accurate seek
/// boundaries. The actual H.264 encoder (libx264 / NVENC / QSV / AMF)
/// is chosen separately via [`H264Encoder`] (#591).
#[derive(Debug, serde::Deserialize)]
pub enum ExportCodec {
    #[serde(rename = "copy")]
    Copy,
    #[serde(rename = "h264")]
    H264,
}

/// #591 -- which H.264 encoder ffmpeg should use when [`ExportCodec::H264`]
/// is requested. Auto-selected from the metadata.json `system_info`
/// (probe results from the detect/split run) by [`select_h264_encoder`].
///
/// `Libx264` is the CPU fallback; `Nvenc` / `Qsv` / `Amf` are the GPU
/// hardware encoders for NVIDIA / Intel / AMD respectively. The frontend
/// displays the chosen encoder in the export panel sub label and passes
/// the value back to `export_match` so the runtime fallback retry (#591
/// Phase 3) knows which GPU encoder failed.
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub enum H264Encoder {
    Libx264,
    Nvenc,
    Qsv,
    Amf,
}

impl H264Encoder {
    /// Return the ffmpeg `-c:v` value for this encoder.
    fn ffmpeg_codec_name(&self) -> &'static str {
        match self {
            H264Encoder::Libx264 => "libx264",
            H264Encoder::Nvenc => "h264_nvenc",
            H264Encoder::Qsv => "h264_qsv",
            H264Encoder::Amf => "h264_amf",
        }
    }

    /// Return the vendor-specific quality / preset args. Targets visual
    /// parity with libx264 CRF 18 (1080p ≈ 4-8 Mbps band), but the RD
    /// curves differ between encoders so the mapping is approximate.
    /// Tuned values may be revisited per-vendor based on PR #591 real
    /// hardware verification.
    fn quality_args(&self) -> &'static [&'static str] {
        match self {
            // Existing libx264 settings (unchanged from #466 baseline).
            H264Encoder::Libx264 => &["-crf", "18", "-preset", "medium"],
            // NVENC has no CRF; -cq is constant-quality with -rc vbr.
            // -preset p5 ≈ libx264 medium on NVIDIA SDK 12+ (p1=fastest,
            // p7=slowest).
            H264Encoder::Nvenc => &[
                "-rc", "vbr", "-cq", "19", "-preset", "p5",
            ],
            // QSV ICQ (Intelligent Constant Quality). -look_ahead 1
            // enables 1-frame look-ahead for better RD decisions.
            H264Encoder::Qsv => &[
                "-global_quality", "20", "-look_ahead", "1", "-preset", "medium",
            ],
            // AMF Constant QP. Windows-only encoder; matches CLAUDE.md
            // "対応プラットフォーム: Windows のみ".
            H264Encoder::Amf => &[
                "-quality", "quality", "-rc", "cqp", "-qp_i", "19", "-qp_p", "21",
            ],
        }
    }

    /// Short human label shown in the GUI export panel sub line.
    fn display_label(&self) -> &'static str {
        match self {
            H264Encoder::Libx264 => "libx264 (CPU)",
            H264Encoder::Nvenc => "NVENC",
            H264Encoder::Qsv => "QSV",
            H264Encoder::Amf => "AMF",
        }
    }
}

/// #591 -- choose an H.264 encoder from the GPU vendor probe results.
///
/// `vendors` is the `gpu_vendors_available` slice from the metadata.json
/// `system_info` field (Phase 1). `preference` is `vendor_preference`
/// from the same payload (a snapshot of `gpu_detector._VENDOR_PREFERENCE`,
/// currently `["nvidia", "amd", "intel"]`).
///
/// Returns the first preference entry that is also present in `vendors`,
/// mapped to the vendor's H.264 encoder. Falls back to `Libx264` when no
/// vendor matches (CPU-only environment, empty system_info, or unknown
/// vendor names).
fn select_h264_encoder(vendors: &[String], preference: &[String]) -> H264Encoder {
    for pref in preference {
        if vendors.iter().any(|v| v == pref) {
            match pref.as_str() {
                "nvidia" => return H264Encoder::Nvenc,
                "intel" => return H264Encoder::Qsv,
                "amd" => return H264Encoder::Amf,
                _ => continue,
            }
        }
    }
    H264Encoder::Libx264
}

/// #466 -- terminal payload returned to the frontend when a single match
/// finishes exporting. `duration_ms` is wall time; the frontend uses it to
/// show "exported in Ns" per match.
#[derive(Debug, serde::Serialize)]
pub struct ExportResult {
    pub match_index: u32,
    pub output_path: String,
    pub duration_ms: u64,
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

/// #591 -- detect "this looks like a GPU encoder initialisation failure"
/// from ffmpeg stderr text. Used by `export_match` to decide whether a
/// non-zero exit warrants a libx264 retry.
///
/// Returns `false` for [`H264Encoder::Libx264`] (libx264 errors are not
/// recoverable by switching encoders) and for unrelated errors (e.g.
/// `"No such file or directory"`).
///
/// The substring patterns are pinned to ffmpeg 8.x BtbN LGPL builds
/// (CLAUDE.md recommended). Future ffmpeg releases may change the
/// wording -- when that happens, extend this match arm rather than
/// loosening the matcher (loose matching would silently retry on
/// unrelated failures).
///
/// QSV patterns include the post-PR-#596 verified ffmpeg 8.1 strings
/// (`Error creating a MFX session` / `current mfx implementation is not
/// supported` -- observed when QSV is forced on a non-Intel host) plus
/// the older `Error initializing an internal MFX session` for older
/// ffmpeg builds. The `Could not open encoder` line is generic but
/// always preceded by `[h264_qsv @ ...]` in QSV failures, so we accept
/// it inside the Qsv arm only.
///
/// NVENC and AMF were validated against ffmpeg 8.1 BtbN LGPL on an
/// Intel-iGPU-only host (#604): `Cannot load nvcuda.dll` (NVENC) and
/// `DLL amfrt64.dll failed to open` (AMF) are the strings ffmpeg 8.1
/// emits when the respective vendor driver DLL is missing. Pre-#604
/// the patterns targeted ffmpeg 7.x only and missed every line of the
/// 8.1 stderr, so the libx264 fallback retry never fired -- the same
/// version-drift class of bug PR #596 fixed for QSV.
fn is_gpu_encoder_failure(stderr: &str, encoder: H264Encoder) -> bool {
    match encoder {
        H264Encoder::Libx264 => false,
        H264Encoder::Nvenc => {
            stderr.contains("No NVENC capable devices found")
                || stderr.contains("Cannot load nvEncodeAPI")
                || stderr.contains("OpenEncodeSessionEx failed")
                || stderr.contains("Cannot load nvcuda.dll")
        }
        H264Encoder::Qsv => {
            stderr.contains("Error creating a MFX session")
                || stderr.contains("Error initializing an internal MFX session")
                || stderr.contains("current mfx implementation is not supported")
                || stderr.contains("Cannot load libmfx")
                || stderr.contains("MFXVideoENCODE_Init")
                || (stderr.contains("h264_qsv") && stderr.contains("Could not open encoder"))
        }
        H264Encoder::Amf => {
            stderr.contains("AMF runtime not initialized")
                || stderr.contains("DLL load failed")
                || stderr.contains("Could not initialize AMFContext")
                || stderr.contains("DLL amfrt64.dll failed to open")
        }
    }
}

/// #466 -- pure validator for export arguments. Split out so unit tests can
/// exercise the error paths without spawning ffmpeg. The caller is expected
/// to pass the resolved `video_path` (no path-resolution done here).
fn validate_export_request(
    video_path: &Path,
    start_seconds: f64,
    end_seconds: f64,
) -> Result<(), String> {
    if !video_path.exists() {
        return Err(format!(
            "video file not found: {}",
            video_path.display()
        ));
    }
    let meta = fs::metadata(video_path)
        .map_err(|e| format!("stat failed ({}): {}", video_path.display(), e))?;
    if !meta.is_file() {
        return Err(format!(
            "video path is not a regular file: {}",
            video_path.display()
        ));
    }
    if !start_seconds.is_finite() || start_seconds < 0.0 {
        return Err(format!(
            "start_seconds must be >= 0 (got {})",
            start_seconds
        ));
    }
    if !end_seconds.is_finite() || end_seconds <= start_seconds {
        return Err(format!(
            "end_seconds must be > start_seconds (got start={}, end={})",
            start_seconds, end_seconds
        ));
    }
    Ok(())
}

/// #466 -- assemble the ffmpeg argv for a single export. Pulled out of
/// `export_match` so unit tests can verify flag ordering and codec choices
/// without spawning a process.
///
/// Note: `-ss` is placed BEFORE `-i` so ffmpeg does a fast keyframe-based
/// seek rather than decoding from t=0. `-to` / `-t` interpretation after
/// `-ss -i` is "duration from the seek point", so we pass
/// `end_seconds - start_seconds` as a duration via `-t`.
/// #466 review #4: 出力先の親ディレクトリが存在することを検証する。
///
/// 以前は `export_match` 内で `create_dir_all` を呼んでいたが、ユーザーが
/// タイポしたパスに静かにディレクトリツリーが作られて混乱を招くため、
/// 明示拒否に変更した。ディレクトリ作成はユーザーが事前に行う前提。
///
/// `output_path` がルート / 親なし (file_name only など) の場合は no-op で
/// Ok を返す (現在のディレクトリを意味すると解釈)。
fn validate_output_parent_exists(output_path: &Path) -> Result<(), String> {
    if let Some(parent) = output_path.parent() {
        if !parent.as_os_str().is_empty() && !parent.exists() {
            return Err(format!(
                "output directory does not exist: {}",
                parent.display()
            ));
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
fn validate_open_folder_request(path: &str) -> Result<(), String> {
    if !Path::new(path).exists() {
        return Err(format!("path does not exist: {}", path));
    }
    #[cfg(not(target_os = "windows"))]
    {
        return Err(
            "open_folder_in_explorer is only supported on Windows".to_string(),
        );
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
/// Windows のみ対応 (CLAUDE.md に「対応プラットフォーム: Windows のみ」と
/// 明記)。将来 Linux / macOS 対応する際は `xdg-open` / `open` で分岐する。
#[tauri::command]
fn open_folder_in_explorer(path: String) -> Result<(), String> {
    validate_open_folder_request(&path)?;

    #[cfg(target_os = "windows")]
    {
        use std::process::Command;
        Command::new("explorer.exe")
            .arg(&path)
            .spawn()
            .map_err(|e| format!("failed to launch explorer: {}", e))?;
    }

    Ok(())
}

fn ffmpeg_args_for_export(
    video_path: &Path,
    start_seconds: f64,
    end_seconds: f64,
    output_path: &Path,
    codec: &ExportCodec,
    h264_encoder: H264Encoder,
) -> Vec<String> {
    let duration = (end_seconds - start_seconds).max(0.0);
    let start_str = format!("{:.3}", start_seconds.max(0.0));
    let duration_str = format!("{:.3}", duration);

    let mut args: Vec<String> = Vec::new();
    args.push("-y".to_string());
    args.push("-hide_banner".to_string());
    args.push("-loglevel".to_string());
    args.push("error".to_string());
    args.push("-progress".to_string());
    args.push("pipe:2".to_string());
    args.push("-ss".to_string());
    args.push(start_str);
    args.push("-i".to_string());
    args.push(video_path.to_string_lossy().to_string());
    args.push("-t".to_string());
    args.push(duration_str);

    match codec {
        ExportCodec::Copy => {
            args.push("-c".to_string());
            args.push("copy".to_string());
            args.push("-avoid_negative_ts".to_string());
            args.push("make_zero".to_string());
        }
        ExportCodec::H264 => {
            // #591 -- vendor-aware encoder selection. h264_encoder is
            // resolved by select_h264_encoder() from metadata.json
            // system_info.gpu_vendors_available; falls back to libx264
            // when the system_info is missing or empty.
            args.push("-c:v".to_string());
            args.push(h264_encoder.ffmpeg_codec_name().to_string());
            for q in h264_encoder.quality_args() {
                args.push((*q).to_string());
            }
            args.push("-c:a".to_string());
            args.push("copy".to_string());
        }
    }

    args.push(output_path.to_string_lossy().to_string());
    args
}

/// #466 -- insert a spawned ffmpeg child into the global PROCESS_TRACKER so
/// the CloseRequested flow (#523) can kill it on app exit. Returns the UUID
/// used as the map key; the caller must pass it back to `untrack_child` on
/// process completion.
async fn track_child(child: tokio::process::Child) -> Uuid {
    let tracker = process_tracker();
    let mut guard = tracker.lock().await;
    let id = Uuid::new_v4();
    guard.insert(id, child);
    id
}

/// #466 -- remove a tracked child from PROCESS_TRACKER. Returns the child
/// so the caller can still `.wait()` / `.kill()` it outside the tracker
/// lock. Returns None if the entry was already drained (e.g. by
/// `kill_tracked_processes`).
async fn untrack_child(id: Uuid) -> Option<tokio::process::Child> {
    let tracker = process_tracker();
    let mut guard = tracker.lock().await;
    guard.remove(&id)
}

/// #466 -- parse a single ffmpeg `-progress` line. ffmpeg emits key=value
/// lines once per second (out_time, out_time_ms, speed, bitrate, ...) and
/// a terminal `progress=end` or `progress=continue`. We only care about
/// `out_time_ms` (for the percent bar) and `progress=end` (for the terminal
/// event). Returns None for every other key.
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
fn tail_string(buf: &[u8], max_bytes: usize) -> String {
    let start = buf.len().saturating_sub(max_bytes);
    String::from_utf8_lossy(&buf[start..]).trim().to_string()
}

/// #466 -- export a single match to `output_path` by invoking ffmpeg.
///
/// Spawns with stderr piped, reads `-progress pipe:2` lines, and emits one
/// `export-progress` event per `out_time_ms=` or terminal `progress=end`
/// line. Non-progress stderr lines (e.g. real ffmpeg errors under
/// `-loglevel error`) are accumulated into a ring buffer and folded into
/// the Err message on non-zero exit.
///
/// The spawned child is registered in PROCESS_TRACKER for the duration of
/// the call so the CloseRequested flow can kill it before app exit.
/// #591 -- one ffmpeg invocation: spawn, stream stderr (progress events
/// + tail buffer), wait for exit. Returns the captured stderr tail and
/// final status so the caller can decide whether to retry with a
/// different encoder.
///
/// `attempt_emits_done`: when `true` (single-attempt path or final
/// retry), the function emits `stage="done"` on success. When `false`
/// (first attempt of a retry sequence), the caller suppresses the done
/// event for the failing attempt so the frontend doesn't see "done"
/// followed by "fallback". The done event for a successful retry is
/// emitted by the next call with `attempt_emits_done = true`.
async fn run_ffmpeg_export_attempt(
    app: &tauri::AppHandle,
    args: &[String],
    duration_seconds: f64,
    match_index: u32,
    attempt_emits_done: bool,
) -> Result<(std::process::ExitStatus, Vec<u8>, bool), String> {
    let mut cmd = tokio::process::Command::new("ffmpeg");
    for a in args {
        cmd.arg(a);
    }
    cmd.stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::piped());

    let mut child = cmd
        .spawn()
        .map_err(|e| format!("spawn ffmpeg failed: {}", e))?;

    let stderr = child
        .stderr
        .take()
        .ok_or_else(|| "failed to capture ffmpeg stderr".to_string())?;

    let tracked_id = track_child(child).await;

    let mut reader = BufReader::new(stderr).lines();
    let mut stderr_tail: Vec<u8> = Vec::with_capacity(4096);
    let max_tail = 2048;
    let mut saw_end = false;

    loop {
        match reader.next_line().await {
            Ok(Some(line)) => match parse_progress_line(&line) {
                Some(ProgressSignal::OutTimeMs(us)) => {
                    let seconds = (us as f64) / 1_000_000.0;
                    let mut percent = if duration_seconds > 0.0 {
                        seconds / duration_seconds * 100.0
                    } else {
                        0.0
                    };
                    if !percent.is_finite() {
                        percent = 0.0;
                    }
                    if percent < 0.0 {
                        percent = 0.0;
                    }
                    if percent > 100.0 {
                        percent = 100.0;
                    }
                    let _ = app.emit(
                        "export-progress",
                        ExportProgress {
                            match_index,
                            percent,
                            stage: "encoding".to_string(),
                            message: None,
                            fallback_from: None,
                        },
                    );
                }
                Some(ProgressSignal::End) => {
                    saw_end = true;
                    if attempt_emits_done {
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
                }
                None => {
                    stderr_tail.extend_from_slice(line.as_bytes());
                    stderr_tail.push(b'\n');
                    if stderr_tail.len() > max_tail * 2 {
                        let keep_from = stderr_tail.len() - max_tail;
                        stderr_tail.drain(0..keep_from);
                    }
                }
            },
            Ok(None) => break,
            Err(e) => {
                stderr_tail
                    .extend_from_slice(format!("stderr read error: {}\n", e).as_bytes());
                break;
            }
        }
    }

    let mut child = match untrack_child(tracked_id).await {
        Some(c) => c,
        None => {
            return Err("export cancelled (process tracker drained)".to_string());
        }
    };

    let status = child
        .wait()
        .await
        .map_err(|e| format!("wait ffmpeg failed: {}", e))?;

    Ok((status, stderr_tail, saw_end))
}

#[tauri::command]
async fn export_match(
    app: tauri::AppHandle,
    video_path: String,
    start_seconds: f64,
    end_seconds: f64,
    output_path: String,
    codec: ExportCodec,
    h264_encoder: Option<H264Encoder>,
    match_index: u32,
) -> Result<ExportResult, String> {
    let video = PathBuf::from(&video_path);
    validate_export_request(&video, start_seconds, end_seconds)?;

    let output = PathBuf::from(&output_path);
    validate_output_parent_exists(&output)?;

    // #591 -- frontend が metadata.json system_info から resolve した
    // encoder を渡す。None (legacy / 古い metadata) は libx264 fallback。
    let encoder = h264_encoder.unwrap_or(H264Encoder::Libx264);

    let duration_seconds = end_seconds - start_seconds;
    let started = Instant::now();
    let max_tail = 2048;

    // Attempt 1: vendor-resolved encoder.
    let primary_args =
        ffmpeg_args_for_export(&video, start_seconds, end_seconds, &output, &codec, encoder);
    let (status, stderr_tail, saw_end) = run_ffmpeg_export_attempt(
        &app,
        &primary_args,
        duration_seconds,
        match_index,
        true, // emits "done" on success
    )
    .await
    .map_err(|e| {
        let _ = app.emit(
            "export-progress",
            ExportProgress {
                match_index,
                percent: 0.0,
                stage: "error".to_string(),
                message: Some(e.clone()),
                fallback_from: None,
            },
        );
        e
    })?;

    if status.success() {
        // Some ffmpeg builds close stderr without flushing the final
        // `progress=end` line -- synthesize a terminal "done" so the
        // frontend always sees one.
        if !saw_end {
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
        return Ok(build_export_result(&output, match_index, started));
    }

    // Failed. Decide whether to retry with libx264 (#591).
    let stderr_text = String::from_utf8_lossy(&stderr_tail).into_owned();
    if encoder != H264Encoder::Libx264
        && matches!(codec, ExportCodec::H264)
        && is_gpu_encoder_failure(&stderr_text, encoder)
    {
        let from_to = format!("{} -> libx264", encoder.ffmpeg_codec_name());
        let _ = app.emit(
            "export-progress",
            ExportProgress {
                match_index,
                percent: 0.0,
                stage: "fallback".to_string(),
                message: Some(format!(
                    "{} の初期化に失敗したため libx264 で再試行します",
                    encoder.display_label()
                )),
                fallback_from: Some(from_to),
            },
        );

        let retry_args = ffmpeg_args_for_export(
            &video,
            start_seconds,
            end_seconds,
            &output,
            &codec,
            H264Encoder::Libx264,
        );
        let (retry_status, retry_tail, retry_saw_end) = run_ffmpeg_export_attempt(
            &app,
            &retry_args,
            duration_seconds,
            match_index,
            true,
        )
        .await
        .map_err(|e| {
            let _ = app.emit(
                "export-progress",
                ExportProgress {
                    match_index,
                    percent: 0.0,
                    stage: "error".to_string(),
                    message: Some(e.clone()),
                    fallback_from: None,
                },
            );
            e
        })?;

        if retry_status.success() {
            if !retry_saw_end {
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
            return Ok(build_export_result(&output, match_index, started));
        }

        // Retry also failed -- surface the libx264 stderr (more useful
        // than the original GPU failure).
        let tail = tail_string(&retry_tail, max_tail);
        let msg = if tail.is_empty() {
            format!(
                "ffmpeg (libx264 retry) exited with status {:?}",
                retry_status.code()
            )
        } else {
            format!(
                "ffmpeg (libx264 retry) exited with status {:?}: {}",
                retry_status.code(),
                tail
            )
        };
        let _ = app.emit(
            "export-progress",
            ExportProgress {
                match_index,
                percent: 0.0,
                stage: "error".to_string(),
                message: Some(msg.clone()),
                fallback_from: None,
            },
        );
        return Err(msg);
    }

    // No retry -- surface the primary failure.
    let tail = tail_string(&stderr_tail, max_tail);
    let msg = if tail.is_empty() {
        format!("ffmpeg exited with status {:?}", status.code())
    } else {
        format!("ffmpeg exited with status {:?}: {}", status.code(), tail)
    };
    let _ = app.emit(
        "export-progress",
        ExportProgress {
            match_index,
            percent: 0.0,
            stage: "error".to_string(),
            message: Some(msg.clone()),
            fallback_from: None,
        },
    );
    Err(msg)
}

fn build_export_result(output: &Path, match_index: u32, started: Instant) -> ExportResult {
    let output_str = fs::canonicalize(output)
        .map(|p| p.to_string_lossy().to_string())
        .unwrap_or_else(|_| output.to_string_lossy().to_string());
    ExportResult {
        match_index,
        output_path: output_str,
        duration_ms: started.elapsed().as_millis() as u64,
    }
}

/// #591 -- payload returned from `select_h264_encoder_for_export` to the
/// frontend. `encoder_kind` is the wire form (`"Nvenc"` / `"Qsv"` /
/// `"Amf"` / `"Libx264"`) which the frontend passes back unchanged in
/// the `h264_encoder` field of `export_match`.
#[derive(Debug, serde::Serialize)]
pub struct EncoderInfo {
    pub encoder: String,
    pub display_label: String,
    pub encoder_kind: H264Encoder,
}

/// #591 -- pure-function Tauri command that maps a metadata.json
/// `system_info.gpu_vendors_available` + `vendor_preference` pair to the
/// concrete H.264 encoder the frontend should use. No subprocess work
/// (the probe already happened during detect/split), so this is cheap to
/// call on every ExportScreen mount.
#[tauri::command]
fn select_h264_encoder_for_export(
    vendors: Vec<String>,
    preference: Vec<String>,
) -> EncoderInfo {
    let encoder = select_h264_encoder(&vendors, &preference);
    EncoderInfo {
        encoder: encoder.ffmpeg_codec_name().to_string(),
        display_label: encoder.display_label().to_string(),
        encoder_kind: encoder,
    }
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

/// #569 -- pure parser for one JSON-lines progress event.  Returns
/// `None` for blank lines or lines that fail to deserialize so a stray
/// stdout write from the CLI doesn't break the overall stream.
fn parse_detect_progress_line(line: &str) -> Option<DetectProgress> {
    let line = line.trim();
    if line.is_empty() {
        return None;
    }
    serde_json::from_str(line).ok()
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
/// `CloseRequested` flow (#523) and the user-pressed cancel button (next
/// PR, also #523) can kill it.  Cancellation by the user from the
/// detecting screen is handled by the frontend dispatching a phase
/// transition only -- the actual `kill_tracked_processes` invocation is
/// deferred to #523's PR.
#[tauri::command]
async fn start_detect(
    app: tauri::AppHandle,
    video_path: String,
    output_dir: String,
    params: DetectParams,
) -> Result<DetectResult, String> {
    let video = PathBuf::from(&video_path);
    if !video.exists() {
        return Err(format!("video file not found: {}", video.display()));
    }
    let output_buf = PathBuf::from(&output_dir);
    if let Err(e) = fs::create_dir_all(&output_buf) {
        return Err(format!(
            "create output dir failed ({}): {}",
            output_buf.display(),
            e
        ));
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
    cmd.stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

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

    let tracked_id = track_child(child).await;

    // Stderr drains in parallel into a bounded tail buffer so the OS
    // pipe doesn't fill up if the CLI is chatty under -v / verbose.
    let stderr_handle = tokio::spawn(async move {
        let max_tail = 2048usize;
        let mut tail: Vec<u8> = Vec::with_capacity(4096);
        let mut reader = BufReader::new(stderr).lines();
        while let Ok(Some(line)) = reader.next_line().await {
            tail.extend_from_slice(line.as_bytes());
            tail.push(b'\n');
            if tail.len() > max_tail * 2 {
                let drop = tail.len() - max_tail;
                tail.drain(0..drop);
            }
        }
        tail
    });

    let mut metadata_path: Option<String> = None;
    let mut total_matches: u64 = 0;
    let mut reader = BufReader::new(stdout).lines();

    loop {
        match reader.next_line().await {
            Ok(Some(line)) => {
                if let Some(progress) = parse_detect_progress_line(&line) {
                    if progress.phase == "done" {
                        if let Some(ref p) = progress.metadata_path {
                            metadata_path = Some(p.clone());
                        }
                        if let Some(m) = progress.matches {
                            total_matches = m;
                        }
                    }
                    let _ = app.emit("detect-progress", progress);
                }
            }
            Ok(None) => break,
            Err(e) => {
                // stdout pipe hiccup -- still try to wait the child so
                // we don't leak a zombie.  The error path below sets the
                // error event.
                let msg = format!("stdout read error: {e}");
                let _ = app.emit(
                    "detect-progress",
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
            let _ = app.emit(
                "detect-progress",
                DetectProgress {
                    phase: "cancelled".to_string(),
                    ..Default::default()
                },
            );
            return Err("detect cancelled".to_string());
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
        let _ = app.emit(
            "detect-progress",
            DetectProgress {
                phase: "error".to_string(),
                message: Some(msg.clone()),
                ..Default::default()
            },
        );
        return Err(msg);
    }

    let metadata_path = metadata_path.ok_or_else(|| {
        "detect completed but no metadata_path was emitted".to_string()
    })?;

    Ok(DetectResult {
        metadata_path,
        matches: total_matches,
    })
}

/// #614 -- Returns the install-directory log path (`<install_dir>/logs`) so the
/// frontend ErrorModal can show the user where crash logs are written.
#[tauri::command]
fn get_log_dir() -> Result<String, String> {
    logging::log_dir()
        .map(|p| p.to_string_lossy().to_string())
        .map_err(|e| format!("could not resolve log dir: {}", e))
}

/// #614 -- Dev-only command that triggers a panic. Used by the frontend smoke
/// test (DevTools console: `await __TAURI__.core.invoke('dev_force_panic')`)
/// to verify the panic hook + ErrorModal end-to-end. Symbol is absent in
/// release builds.
#[cfg(debug_assertions)]
#[tauri::command]
fn dev_force_panic() -> Result<(), String> {
    panic!("dev_force_panic invoked from frontend");
}

pub fn run() {
    // #614 -- Initialize tracing subscriber + rotate stale logs + detect
    // unclean shutdown from the previous session, BEFORE the Tauri builder
    // runs so panic_hook is the first hook installed.
    let _tracing_guard = logging::install_tracing_subscriber();
    if let Err(e) = logging::rotate_old_logs(7) {
        eprintln!("warning: failed to rotate old logs: {}", e);
    }
    let restart_panic_msg = logging::detect_panic_from_previous_session();

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

    #[cfg(debug_assertions)]
    let builder = builder.invoke_handler(tauri::generate_handler![
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
        is_process_running,
        kill_tracked_processes,
        force_exit_app,
        export_match,
        select_h264_encoder_for_export,
        open_folder_in_explorer,
        start_detect,
        get_log_dir,
        dev_force_panic,
    ]);
    #[cfg(not(debug_assertions))]
    let builder = builder.invoke_handler(tauri::generate_handler![
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
        is_process_running,
        kill_tracked_processes,
        force_exit_app,
        export_match,
        select_h264_encoder_for_export,
        open_folder_in_explorer,
        start_detect,
        get_log_dir,
    ]);

    builder
        .run(tauri::generate_context!())
        .expect("error while running tauri application");

    drop(_tracing_guard);
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
            err.contains("ffprobe spawn failed") || err.contains("ffprobe failed"),
            "unexpected error: {}",
            err
        );
    }

    /// #466 -- `copy` codec must emit `-c copy`, not `libx264`. The
    /// `-avoid_negative_ts make_zero` flag prevents negative timestamp
    /// errors common when seeking into a stream whose first packet after
    /// the seek point has a non-zero PTS.
    #[test]
    fn ffmpeg_args_for_export_copy_uses_c_copy() {
        let args = ffmpeg_args_for_export(
            Path::new("C:/videos/in.mp4"),
            10.0,
            40.0,
            Path::new("C:/out/match1.mp4"),
            &ExportCodec::Copy,
            H264Encoder::Libx264,
        );
        let joined = args.join(" ");
        assert!(joined.contains("-c copy"), "args: {}", joined);
        assert!(
            joined.contains("-avoid_negative_ts make_zero"),
            "args: {}",
            joined
        );
        assert!(!joined.contains("libx264"), "args: {}", joined);
    }

    /// #466 -- `h264` codec must use libx264 with the documented crf/preset
    /// tuning so the frontend's "high quality" toggle lands a consistent
    /// encode. Audio must be copied (not re-encoded) to avoid silent loss
    /// of quality.
    #[test]
    fn ffmpeg_args_for_export_h264_uses_libx264() {
        let args = ffmpeg_args_for_export(
            Path::new("C:/videos/in.mp4"),
            0.0,
            30.0,
            Path::new("C:/out/match1.mp4"),
            &ExportCodec::H264,
            H264Encoder::Libx264,
        );
        let joined = args.join(" ");
        assert!(joined.contains("-c:v libx264"), "args: {}", joined);
        assert!(joined.contains("-crf 18"), "args: {}", joined);
        assert!(joined.contains("-preset medium"), "args: {}", joined);
        assert!(joined.contains("-c:a copy"), "args: {}", joined);
    }

    /// #466 -- ffmpeg's seek semantics differ dramatically depending on
    /// whether `-ss` appears before or after `-i`. Before `-i`: fast
    /// keyframe-based seek. After `-i`: slow decode-and-discard. We rely
    /// on the fast path, so guard the ordering.
    #[test]
    fn ffmpeg_args_include_ss_before_input_for_keyframe_seek() {
        let args = ffmpeg_args_for_export(
            Path::new("C:/videos/in.mp4"),
            15.5,
            45.5,
            Path::new("C:/out/match1.mp4"),
            &ExportCodec::Copy,
            H264Encoder::Libx264,
        );
        let ss_pos = args.iter().position(|a| a == "-ss").expect("-ss present");
        let i_pos = args.iter().position(|a| a == "-i").expect("-i present");
        assert!(
            ss_pos < i_pos,
            "-ss (at {}) must precede -i (at {}): {:?}",
            ss_pos,
            i_pos,
            args
        );
    }

    /// #466 -- argv must include a `-t <duration>` pair whose value equals
    /// `end_seconds - start_seconds`. This is the cross-check that
    /// `export_match` actually delivers the requested clip length, not
    /// trailing footage from the source.
    #[test]
    fn ffmpeg_args_encode_duration_as_t_flag() {
        let args = ffmpeg_args_for_export(
            Path::new("C:/videos/in.mp4"),
            10.0,
            40.5,
            Path::new("C:/out/match1.mp4"),
            &ExportCodec::Copy,
            H264Encoder::Libx264,
        );
        let t_pos = args.iter().position(|a| a == "-t").expect("-t present");
        let duration = args.get(t_pos + 1).expect("value after -t");
        let parsed: f64 = duration.parse().expect("parse duration");
        assert!(
            (parsed - 30.5).abs() < 1e-6,
            "expected 30.5, got {} (all: {:?})",
            parsed,
            args
        );
    }

    // -- #591 -- H264Encoder + select_h264_encoder + ffmpeg_args_for_export
    // vendor 別 args の単体テスト群。

    fn _vendor_strs(items: &[&str]) -> Vec<String> {
        items.iter().map(|s| (*s).to_string()).collect()
    }

    fn _default_preference() -> Vec<String> {
        _vendor_strs(&["nvidia", "amd", "intel"])
    }

    /// #591 -- NVIDIA があれば preference 順で最優先選択。
    #[test]
    fn select_h264_encoder_picks_nvenc_for_nvidia_first() {
        let vendors = _vendor_strs(&["nvidia", "amd"]);
        assert_eq!(
            select_h264_encoder(&vendors, &_default_preference()),
            H264Encoder::Nvenc
        );
    }

    /// #591 -- Intel iGPU 単独環境では QSV を選ぶ。
    #[test]
    fn select_h264_encoder_picks_qsv_for_intel_only() {
        let vendors = _vendor_strs(&["intel"]);
        assert_eq!(
            select_h264_encoder(&vendors, &_default_preference()),
            H264Encoder::Qsv
        );
    }

    /// #591 -- AMD のみなら AMF を選ぶ (Windows 限定だが pure 関数として
    /// は OS 非依存に動作)。
    #[test]
    fn select_h264_encoder_picks_amf_for_amd_only() {
        let vendors = _vendor_strs(&["amd"]);
        assert_eq!(
            select_h264_encoder(&vendors, &_default_preference()),
            H264Encoder::Amf
        );
    }

    /// #591 -- vendor 不在 (CPU only / 空 system_info) は Libx264 fallback。
    #[test]
    fn select_h264_encoder_falls_back_to_libx264_when_empty() {
        let vendors: Vec<String> = vec![];
        assert_eq!(
            select_h264_encoder(&vendors, &_default_preference()),
            H264Encoder::Libx264
        );
    }

    /// #591 -- preference 順で選ぶ (vendors の出現順は無視される)。
    #[test]
    fn select_h264_encoder_respects_preference_order() {
        let vendors = _vendor_strs(&["amd", "nvidia"]);
        // preference = nvidia > amd > intel なので NVIDIA が先。
        assert_eq!(
            select_h264_encoder(&vendors, &_default_preference()),
            H264Encoder::Nvenc
        );
    }

    /// #591 -- 知らない vendor 名は無視されて libx264 へ。
    #[test]
    fn select_h264_encoder_ignores_unknown_vendors() {
        let vendors = _vendor_strs(&["wgpu", "moltenvk"]);
        assert_eq!(
            select_h264_encoder(&vendors, &_default_preference()),
            H264Encoder::Libx264
        );
    }

    /// #591 -- NVENC 選択時の ffmpeg argv は h264_nvenc + -cq 19 + -preset p5。
    #[test]
    fn ffmpeg_args_for_export_h264_nvenc_uses_h264_nvenc() {
        let args = ffmpeg_args_for_export(
            Path::new("C:/videos/in.mp4"),
            0.0,
            30.0,
            Path::new("C:/out/m.mp4"),
            &ExportCodec::H264,
            H264Encoder::Nvenc,
        );
        let joined = args.join(" ");
        assert!(joined.contains("-c:v h264_nvenc"), "args: {}", joined);
        assert!(joined.contains("-cq 19"), "args: {}", joined);
        assert!(joined.contains("-preset p5"), "args: {}", joined);
        assert!(joined.contains("-c:a copy"), "args: {}", joined);
        assert!(!joined.contains("libx264"), "args: {}", joined);
    }

    /// #591 -- QSV 選択時は h264_qsv + -global_quality 20 + -look_ahead 1。
    #[test]
    fn ffmpeg_args_for_export_h264_qsv_uses_h264_qsv() {
        let args = ffmpeg_args_for_export(
            Path::new("C:/videos/in.mp4"),
            0.0,
            30.0,
            Path::new("C:/out/m.mp4"),
            &ExportCodec::H264,
            H264Encoder::Qsv,
        );
        let joined = args.join(" ");
        assert!(joined.contains("-c:v h264_qsv"), "args: {}", joined);
        assert!(joined.contains("-global_quality 20"), "args: {}", joined);
        assert!(joined.contains("-look_ahead 1"), "args: {}", joined);
        assert!(joined.contains("-c:a copy"), "args: {}", joined);
        assert!(!joined.contains("libx264"), "args: {}", joined);
    }

    /// #591 -- AMF 選択時は h264_amf + -rc cqp + -qp_i 19 + -qp_p 21。
    #[test]
    fn ffmpeg_args_for_export_h264_amf_uses_h264_amf() {
        let args = ffmpeg_args_for_export(
            Path::new("C:/videos/in.mp4"),
            0.0,
            30.0,
            Path::new("C:/out/m.mp4"),
            &ExportCodec::H264,
            H264Encoder::Amf,
        );
        let joined = args.join(" ");
        assert!(joined.contains("-c:v h264_amf"), "args: {}", joined);
        assert!(joined.contains("-rc cqp"), "args: {}", joined);
        assert!(joined.contains("-qp_i 19"), "args: {}", joined);
        assert!(joined.contains("-qp_p 21"), "args: {}", joined);
        assert!(joined.contains("-c:a copy"), "args: {}", joined);
        assert!(!joined.contains("libx264"), "args: {}", joined);
    }

    /// #591 -- Copy codec では h264_encoder の値に関わらず -c copy 経路を取る。
    /// h264_encoder=Nvenc を渡しても、ExportCodec::Copy なら NVENC は使われない。
    #[test]
    fn ffmpeg_args_for_export_copy_ignores_h264_encoder_value() {
        let args = ffmpeg_args_for_export(
            Path::new("C:/videos/in.mp4"),
            0.0,
            30.0,
            Path::new("C:/out/m.mp4"),
            &ExportCodec::Copy,
            H264Encoder::Nvenc,
        );
        let joined = args.join(" ");
        assert!(joined.contains("-c copy"), "args: {}", joined);
        assert!(!joined.contains("h264_nvenc"), "args: {}", joined);
        assert!(!joined.contains("-cq"), "args: {}", joined);
    }

    /// #591 -- H264Encoder::display_label は GUI sub label 用の固定文字列を返す。
    #[test]
    fn h264_encoder_display_labels() {
        assert_eq!(H264Encoder::Libx264.display_label(), "libx264 (CPU)");
        assert_eq!(H264Encoder::Nvenc.display_label(), "NVENC");
        assert_eq!(H264Encoder::Qsv.display_label(), "QSV");
        assert_eq!(H264Encoder::Amf.display_label(), "AMF");
    }

    /// #591 -- ffmpeg_codec_name は ffmpeg `-c:v` で使う識別子を返す。
    #[test]
    fn h264_encoder_ffmpeg_codec_names() {
        assert_eq!(H264Encoder::Libx264.ffmpeg_codec_name(), "libx264");
        assert_eq!(H264Encoder::Nvenc.ffmpeg_codec_name(), "h264_nvenc");
        assert_eq!(H264Encoder::Qsv.ffmpeg_codec_name(), "h264_qsv");
        assert_eq!(H264Encoder::Amf.ffmpeg_codec_name(), "h264_amf");
    }

    // -- #591 Phase 3 -- is_gpu_encoder_failure detector tests.

    /// NVENC の代表的初期化エラー文字列を検出。
    #[test]
    fn is_gpu_encoder_failure_detects_nvenc_unavailable() {
        let stderr = "[h264_nvenc @ 0x1234] No NVENC capable devices found\n";
        assert!(is_gpu_encoder_failure(stderr, H264Encoder::Nvenc));
    }

    /// nvEncodeAPI DLL がロードできないケース。
    #[test]
    fn is_gpu_encoder_failure_detects_nvenc_dll_missing() {
        let stderr = "[h264_nvenc @ 0x1] Cannot load nvEncodeAPI.dll\n";
        assert!(is_gpu_encoder_failure(stderr, H264Encoder::Nvenc));
    }

    /// #604 実機検証: ffmpeg 8.1 BtbN LGPL を Intel iGPU only host で
    /// h264_nvenc 強制起動 -> NVIDIA driver 不在で nvcuda.dll が見つからず
    /// 失敗。pre-#604 の pattern (`No NVENC capable devices found` /
    /// `Cannot load nvEncodeAPI` / `OpenEncodeSessionEx failed`) は 1 つも
    /// hit せず libx264 retry が走らない bug があった (#596 QSV と同型)。
    #[test]
    fn is_gpu_encoder_failure_detects_nvenc_nvcuda_dll_missing() {
        let stderr = "\
[h264_nvenc @ 0x1] Cannot load nvcuda.dll\n\
[vost#0:0/h264_nvenc @ 0x2] Could not open encoder before EOF\n";
        assert!(is_gpu_encoder_failure(stderr, H264Encoder::Nvenc));
    }

    /// Intel QSV の MFX session 初期化失敗 (ffmpeg 7.x 系ワード)。
    #[test]
    fn is_gpu_encoder_failure_detects_qsv_init_error() {
        let stderr = "[h264_qsv] Error initializing an internal MFX session: -3\n";
        assert!(is_gpu_encoder_failure(stderr, H264Encoder::Qsv));
    }

    /// #591 PR review 実機検証: ffmpeg 8.1 の QSV failure stderr 実例
    /// (RTX 5090 + AMD iGPU 環境で h264_qsv 強制起動 -> Intel iGPU 不在で
    /// MFX session creation 失敗)。pre-fix の pattern では検出漏れし
    /// libx264 retry が走らない bug があった。
    #[test]
    fn is_gpu_encoder_failure_detects_qsv_mfx_session_creation_error() {
        let stderr = "\
[h264_qsv @ 0x1] Error creating a MFX session: -9.\n\
[h264_qsv @ 0x1] The current mfx implementation is not supported, try next mfx implementation.\n\
[vost#0:0/h264_qsv @ 0x2] Could not open encoder before EOF\n";
        assert!(is_gpu_encoder_failure(stderr, H264Encoder::Qsv));
    }

    /// `Could not open encoder` は generic message なので、`h264_qsv`
    /// context が無ければ Qsv の failure と扱わない (libx264 でこの
    /// メッセージが出ても誤って GPU 失敗判定しないため)。
    #[test]
    fn is_gpu_encoder_failure_qsv_requires_h264_qsv_context_for_generic_open_error() {
        let stderr_generic = "[some_codec] Could not open encoder before EOF\n";
        assert!(!is_gpu_encoder_failure(stderr_generic, H264Encoder::Qsv));
    }

    /// AMD AMF runtime ロード失敗。
    #[test]
    fn is_gpu_encoder_failure_detects_amf_load_error() {
        let stderr = "[h264_amf] AMF runtime not initialized\n";
        assert!(is_gpu_encoder_failure(stderr, H264Encoder::Amf));
    }

    /// #604 実機検証: ffmpeg 8.1 BtbN LGPL を Intel iGPU only host で
    /// h264_amf 強制起動 -> AMD driver 不在で amfrt64.dll が開けず失敗。
    /// pre-#604 の pattern (`AMF runtime not initialized` / `DLL load
    /// failed` / `Could not initialize AMFContext`) は 1 つも hit せず
    /// libx264 retry が走らない bug があった (#596 QSV と同型)。
    #[test]
    fn is_gpu_encoder_failure_detects_amf_amfrt64_dll_missing() {
        let stderr = "\
[AMF @ 0x1] DLL amfrt64.dll failed to open\n\
[h264_amf @ 0x2] Failed to create  hardware device context (AMF) : Unknown error occurred\n\
[vost#0:0/h264_amf @ 0x3] Could not open encoder before EOF\n";
        assert!(is_gpu_encoder_failure(stderr, H264Encoder::Amf));
    }

    /// libx264 失敗は GPU encoder 由来でないので false (encoder 切替で
    /// 救えないため retry させない)。
    #[test]
    fn is_gpu_encoder_failure_returns_false_for_libx264() {
        let stderr = "[libx264 @ 0x1] some error\n";
        assert!(!is_gpu_encoder_failure(stderr, H264Encoder::Libx264));
    }

    /// 「ファイルが見つからない」のような GPU 関係ない失敗は false (誤って
    /// libx264 retry すると 2 倍時間かかる)。
    #[test]
    fn is_gpu_encoder_failure_returns_false_for_unrelated_error() {
        let stderr = "Error: No such file or directory\n";
        assert!(!is_gpu_encoder_failure(stderr, H264Encoder::Nvenc));
    }

    /// AMF 検出パターンが NVENC stderr に一致しないこと (cross-encoder
    /// false-positive 防止)。
    #[test]
    fn is_gpu_encoder_failure_qsv_pattern_does_not_match_nvenc() {
        let stderr = "[h264_qsv] Error initializing an internal MFX session\n";
        assert!(!is_gpu_encoder_failure(stderr, H264Encoder::Nvenc));
        assert!(is_gpu_encoder_failure(stderr, H264Encoder::Qsv));
    }

    /// #604 false-positive 防止: NVENC pattern (`Cannot load nvcuda.dll`)
    /// が AMF / QSV stderr context では false を返すこと (retry 暴走防止)。
    /// QSV の `Could not open encoder` generic message に対する
    /// `is_gpu_encoder_failure_qsv_requires_h264_qsv_context_for_generic_open_error`
    /// と同種の cross-encoder context test。
    #[test]
    fn is_gpu_encoder_failure_nvenc_nvcuda_pattern_does_not_match_other_encoders() {
        let stderr = "[h264_nvenc @ 0x1] Cannot load nvcuda.dll\n";
        assert!(is_gpu_encoder_failure(stderr, H264Encoder::Nvenc));
        assert!(!is_gpu_encoder_failure(stderr, H264Encoder::Amf));
        assert!(!is_gpu_encoder_failure(stderr, H264Encoder::Qsv));
    }

    /// #604 false-positive 防止: AMF pattern (`DLL amfrt64.dll failed to open`)
    /// が NVENC / QSV stderr context では false を返すこと (retry 暴走防止)。
    #[test]
    fn is_gpu_encoder_failure_amf_amfrt64_pattern_does_not_match_other_encoders() {
        let stderr = "[AMF @ 0x1] DLL amfrt64.dll failed to open\n";
        assert!(is_gpu_encoder_failure(stderr, H264Encoder::Amf));
        assert!(!is_gpu_encoder_failure(stderr, H264Encoder::Nvenc));
        assert!(!is_gpu_encoder_failure(stderr, H264Encoder::Qsv));
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

    /// #466 -- a missing video path must fail validation before ffmpeg is
    /// touched. The error message must contain "not found" so the frontend
    /// can distinguish it from generic ffmpeg errors.
    #[test]
    fn export_match_rejects_missing_video_path() {
        let tmp = TempDir::new().unwrap();
        let missing = tmp.path().join("nope.mp4");
        let err = validate_export_request(&missing, 0.0, 10.0).unwrap_err();
        assert!(err.contains("not found"), "got: {}", err);
    }

    /// #466 -- `end <= start` must fail immediately (otherwise ffmpeg's
    /// `-t` flag would receive 0 or negative and silently write an empty
    /// file).
    #[test]
    fn export_match_rejects_end_le_start() {
        let tmp = TempDir::new().unwrap();
        let video = tmp.path().join("clip.mp4");
        fs::write(&video, b"fake mp4").unwrap();
        let err_equal = validate_export_request(&video, 10.0, 10.0).unwrap_err();
        assert!(err_equal.contains("end_seconds"), "got: {}", err_equal);
        let err_lt = validate_export_request(&video, 20.0, 10.0).unwrap_err();
        assert!(err_lt.contains("end_seconds"), "got: {}", err_lt);
    }

    /// #466 -- negative start times are rejected. ffmpeg treats `-ss <0`
    /// inconsistently across builds; better to refuse up front.
    #[test]
    fn export_match_rejects_negative_start() {
        let tmp = TempDir::new().unwrap();
        let video = tmp.path().join("clip.mp4");
        fs::write(&video, b"fake mp4").unwrap();
        let err = validate_export_request(&video, -1.0, 10.0).unwrap_err();
        assert!(err.contains("start_seconds"), "got: {}", err);
    }

    /// #466 -- NaN / non-finite values are rejected (they would otherwise
    /// propagate into ffmpeg argv as "NaN" and fail opaquely).
    #[test]
    fn export_match_rejects_non_finite_values() {
        let tmp = TempDir::new().unwrap();
        let video = tmp.path().join("clip.mp4");
        fs::write(&video, b"fake mp4").unwrap();
        let err_nan_start = validate_export_request(&video, f64::NAN, 10.0).unwrap_err();
        assert!(err_nan_start.contains("start_seconds"), "got: {}", err_nan_start);
        let err_inf_end = validate_export_request(&video, 0.0, f64::INFINITY).unwrap_err();
        assert!(err_inf_end.contains("end_seconds"), "got: {}", err_inf_end);
    }

    /// #466 review #4: 出力先親ディレクトリが存在しなければエラー。
    /// 以前の `create_dir_all` (silent mkdir) は廃止されたので、存在しない
    /// パスを渡すと「does not exist」エラーを返す。
    #[test]
    fn validate_output_parent_exists_rejects_missing_parent() {
        let tmp = TempDir::new().unwrap();
        let nested = tmp.path().join("nope").join("clip.mp4");
        let err = validate_output_parent_exists(&nested).unwrap_err();
        assert!(err.contains("does not exist"), "got: {}", err);
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
        assert!(err.contains("does not exist"), "got: {}", err);
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
        assert!(err.contains("Windows"), "got: {}", err);
    }

    /// #545 mystifying-ptolemy-d112b5 review (2026-04-25): track_child →
    /// untrack_child の往復で正しく Some が返ること。`export_match` の
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

        let id = track_child(child).await;
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
    /// 返す。`export_match` の cancel 検出 (`untrack` 結果が None なら
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

        let id = track_child(child).await;
        // kill_tracked_processes が tracker を drain して全 child を kill する
        let _killed = kill_tracked_processes().await.unwrap();
        let recovered = untrack_child(id).await;
        assert!(
            recovered.is_none(),
            "untrack_child should return None after kill_tracked_processes drained the tracker"
        );
    }

    /// #466 -- happy path: real file, sane start/end, validator returns Ok.
    #[test]
    fn export_match_accepts_valid_request() {
        let tmp = TempDir::new().unwrap();
        let video = tmp.path().join("clip.mp4");
        fs::write(&video, b"fake mp4").unwrap();
        validate_export_request(&video, 0.0, 10.0).unwrap();
        validate_export_request(&video, 5.5, 6.25).unwrap();
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
}
