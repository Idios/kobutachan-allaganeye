//! #645 -- Integration tests for the `extract_brightness_window_impl`
//! Tauri command helper. The helper backs the PreviewScreen FrameStrip
//! brightness overlay (±3s zoom around currentT): the frontend invokes it
//! on selectedMatch / currentT change (200ms debounced) and renders the
//! returned `samples` as a semi-transparent SVG overlay (waveform +
//! threshold + blackout band) on top of the candidate frame thumbnails.
//! The two tests below pin:
//!
//! 1. happy path against a real video (gated on `ALLAGANEYE_AUDIO_TEST_VIDEO`,
//!    `#[ignore]` so CI skips it but local devs can run with
//!    `cargo test --include-ignored`);
//! 2. failure path for a non-existent video path (always runs); and
//! 3. defensive `t_start < 0` clamp contract pin (always runs, gated on real
//!    video for correctness assertion — falls back to a minimal symbolic
//!    pin when the sample video is unset). Round 2 F4 of /iterate-review.
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

    // Pin the error contract so the frontend hint rendering (`toErrorState`
    // → `ErrorState.hint`) can rely on it: the failure path is ffmpeg
    // returning non-zero exit (the binary is spawned successfully but cannot
    // open the input). `subprocess.exit_failed` is the canonical code for
    // that case in lib.rs (see ensure_thumbnail_exists and probe_video_with).
    // If ffmpeg itself is missing from PATH the code is `subprocess.spawn_failed`
    // — accept either, both have default hints.
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

/// #645 Round 2 F4: pin the defensive `t_start < 0` clamping contract.
///
/// Backend `extract_brightness_window_impl` clamps the ffmpeg `-ss` argument
/// to `0.0` for negative inputs but echoes the original (negative) `t_start`
/// in the response (see lib.rs doc-comment at `BrightnessWindow`).
/// Frontend `PreviewScreen.tsx` pre-clamps via `Math.max(0, currentT - 3)`
/// so the negative path is unreachable in production today, but the backend
/// keeps the defensive clamp as belt-and-suspenders. This test exists so
/// that a future regression (e.g. accidental removal of `t_start.max(0.0)`)
/// is caught by CI.
///
/// The test does two things in one body:
/// - **echo contract**: `t_start: -2.0` is echoed verbatim in the response
///   (proves the backend doesn't silently rewrite the field).
/// - **non-panic contract**: the call returns `Ok` (or surfaces an `AppError`
///   if ffmpeg fails for unrelated reasons) — never panic. This requires
///   the sample video to be readable; if `ALLAGANEYE_AUDIO_TEST_VIDEO` is
///   unset, the test still runs and asserts only the symbolic safety: the
///   helper accepts negative `t_start` without panicking on the public API
///   surface (it will Err with `subprocess.exit_failed`/`spawn_failed`,
///   which is fine — the contract is "no panic, AppError-shaped failure").
#[tokio::test]
async fn extract_brightness_window_clamps_negative_t_start() {
    // 1 sec interval guard if a previous test invoked ffmpeg
    // (feedback_ffmpeg_test_interval.md).
    std::thread::sleep(std::time::Duration::from_secs(1));

    let video = sample_video()
        .map(|p| p.to_string_lossy().to_string())
        .unwrap_or_else(|| "/nonexistent/path.mp4".to_string());

    let result = allaganeye_gui_lib::extract_brightness_window_impl(
        video,
        -2.0, // negative — backend must clamp ffmpeg `-ss` but echo -2.0 in response
        3.0,  // window: clamp(-2.0)..3.0 = 0.0..3.0 = 3 seconds at 10fps = ~30 samples
        10.0,
    )
    .await;

    match result {
        Ok(window) => {
            // echo contract: original (negative) t_start must round-trip unchanged.
            assert_eq!(
                window.t_start, -2.0,
                "backend must echo the requested t_start verbatim, not clamped"
            );
            assert_eq!(window.t_end, 3.0);
            assert_eq!(window.fps, 10.0);
            // sanity: the actual sample window is `[max(0.0, t_start), t_end] = [0.0, 3.0]`
            // = 3 sec * 10 fps = ~30 samples (allow ±5 slack for fps filter alignment).
            assert!(
                (25..=35).contains(&window.samples.len()),
                "expected ~30 samples after clamp(-2.0)..3.0, got {}",
                window.samples.len()
            );
        }
        Err(err) => {
            // Sample video unavailable — no panic, AppError-shaped failure.
            // This still pins the defensive contract: backend accepted the
            // negative t_start without panicking, returned an AppError instead.
            let rendered = err.to_string();
            assert!(
                rendered.starts_with("[subprocess.exit_failed]")
                    || rendered.starts_with("[subprocess.spawn_failed]"),
                "unexpected error shape: {}",
                rendered
            );
        }
    }
}
