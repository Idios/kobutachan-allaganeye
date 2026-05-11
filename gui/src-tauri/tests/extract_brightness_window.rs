//! #645 -- Integration tests for the `extract_brightness_window_impl`
//! Tauri command helper. The helper backs the PreviewScreen MicroTimeline
//! (±5s zoom around a match boundary): the frontend invokes it on
//! selectedMatch change and renders the returned `samples` as a brightness
//! curve. The two tests below pin:
//!
//! 1. happy path against a real video (gated on `ALLAGANEYE_AUDIO_TEST_VIDEO`,
//!    `#[ignore]` so CI skips it but local devs can run with
//!    `cargo test --include-ignored`); and
//! 2. failure path for a non-existent video path (always runs).
//!
//! Crate name is `allaganeye_gui_lib` (matches the `[lib] name` in
//! `Cargo.toml`), not the package name `allaganeye-gui`.

use std::env;
use std::path::PathBuf;

/// Helper to skip the happy-path test if the sample video is not configured.
fn sample_video() -> Option<PathBuf> {
    env::var("ALLAGANEYE_AUDIO_TEST_VIDEO").ok().map(PathBuf::from)
}

#[tokio::test]
#[ignore] // requires real video file (set ALLAGANEYE_AUDIO_TEST_VIDEO)
async fn extract_brightness_window_returns_samples() {
    let Some(video) = sample_video() else {
        eprintln!("ALLAGANEYE_AUDIO_TEST_VIDEO not set, skipping");
        return;
    };
    // 1 sec interval guard (feedback_ffmpeg_test_interval.md)
    std::thread::sleep(std::time::Duration::from_secs(1));

    let result = allaganeye_gui_lib::extract_brightness_window_impl(
        video.to_string_lossy().to_string(),
        10.0, // t_start = 10s
        20.0, // t_end = 20s
        10.0, // fps = 10
    )
    .await
    .expect("should succeed");

    // 10 sec * 10 fps = 100 samples (allow ±10 slack for ffmpeg fps filter
    // boundary behaviour: the `fps` filter may emit one fewer / one more
    // frame depending on stream PTS alignment).
    assert!(
        (90..=110).contains(&result.samples.len()),
        "expected ~100 samples, got {}",
        result.samples.len()
    );
    // each sample is 0.0..=255.0 (gray plane byte → f64 average)
    for s in &result.samples {
        assert!((0.0..=255.0).contains(s), "sample out of range: {}", s);
    }
    // echoed input fields so the frontend can verify the call landed
    // on the expected window without trusting only the call site.
    assert_eq!(result.t_start, 10.0);
    assert_eq!(result.t_end, 20.0);
    assert_eq!(result.fps, 10.0);
}

#[tokio::test]
async fn extract_brightness_window_handles_missing_file() {
    let result = allaganeye_gui_lib::extract_brightness_window_impl(
        "/nonexistent/path.mp4".to_string(),
        0.0,
        10.0,
        10.0,
    )
    .await;
    assert!(result.is_err(), "missing file must surface as Err");

    // Pin the error contract so frontend `appErrorHint` can rely on it: the
    // failure path is ffmpeg returning non-zero exit (the binary is spawned
    // successfully but cannot open the input). `subprocess.exit_failed` is
    // the canonical code for that case in lib.rs (see ensure_thumbnail_exists
    // and probe_video_with). If ffmpeg itself is missing from PATH the code
    // is `subprocess.spawn_failed` — accept either, both have default hints.
    //
    // `AppError` Display fmt is `[code] message` (see error.rs `impl Display`),
    // so we match on the `[code]` prefix rather than reaching into private
    // struct fields across the integration-test crate boundary.
    let err = result.unwrap_err();
    let rendered = err.to_string();
    assert!(
        rendered.starts_with("[subprocess.exit_failed]")
            || rendered.starts_with("[subprocess.spawn_failed]"),
        "unexpected error: {}",
        rendered
    );
}
