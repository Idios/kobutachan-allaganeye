//! Cross-platform process-related helpers.
//!
//! Currently the only inhabitant is [`apply_no_window`] (#679), which sets
//! Windows' `CREATE_NO_WINDOW` flag on a `tokio::process::Command` so that
//! the `windows_subsystem = "windows"` release bundle doesn't spawn a
//! console window for each ffmpeg / ffprobe / allaganeye child.

/// Apply `CREATE_NO_WINDOW` (`0x0800_0000`) on Windows so that the spawned
/// child doesn't get its own console window. No-op on other platforms.
///
/// Returns the mutable reference so the caller can chain. Designed to be
/// inserted into existing builder chains just before `.spawn()` /
/// `.output()` / `.status()`.
///
/// #679: `windows_subsystem = "windows"` 親プロセスが console を持たない
/// release で、子プロセスを spawn する際 Windows が自動で console window
/// を割り当てる挙動を抑止する。`CREATE_NO_WINDOW` は winbase.h 由来の定数
/// (0x0800_0000)。`tokio::process::Command::creation_flags(u32)` は tokio
/// 1.x で `std::os::windows::process::CommandExt::creation_flags` 相当の
/// 専用 method を提供している ([tokio 1.52 docs](https://docs.rs/tokio/1.52.1/tokio/process/struct.Command.html#method.creation_flags))。
#[cfg(target_os = "windows")]
pub(crate) fn apply_no_window(
    cmd: &mut tokio::process::Command,
) -> &mut tokio::process::Command {
    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    cmd.creation_flags(CREATE_NO_WINDOW)
}

#[cfg(not(target_os = "windows"))]
pub(crate) fn apply_no_window(
    cmd: &mut tokio::process::Command,
) -> &mut tokio::process::Command {
    cmd
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn apply_no_window_does_not_panic_on_default_command() {
        // Smoke test: helper must not panic when applied to a freshly
        // constructed Command. Helper's `&mut Command -> &mut Command`
        // return type (= chain support) is enforced by the type system
        // at call sites such as `process_util::apply_no_window(&mut cmd);`
        // followed by `cmd.arg(...)`. On Windows the helper calls
        // `cmd.creation_flags(CREATE_NO_WINDOW)`; on non-Windows it's a
        // no-op identity. We pin the compilable + non-panicking smoke
        // here; the `lib_rs_applies_apply_no_window_at_all_four_spawn_sites`
        // test below pins adoption at the call sites.
        let mut cmd = tokio::process::Command::new("true");
        apply_no_window(&mut cmd);
    }

    #[test]
    fn apply_no_window_does_not_panic_on_realistic_invocation() {
        // Verify the helper can be applied to a typical Command chain
        // without panicking. Exit status is irrelevant -- we only need
        // the configuration call to succeed.
        let mut cmd = tokio::process::Command::new("ffprobe");
        cmd.arg("-version");
        apply_no_window(&mut cmd);
        // Don't actually spawn (might not exist in CI); just confirm
        // the builder accepted the configuration mutation.
    }

    /// #679 spec §5.4 Option a: adoption の retention を CI で pin する。
    /// 将来の merge で各 spawn site のいずれかから `apply_no_window`
    /// 呼び出しが落ちると、本 test が source 文字列マッチで気付ける。
    ///
    /// 各 spawn 経路の **関数名直後** ~ **`.spawn()` / `.output()`**
    /// の間に `apply_no_window` 文字列が現れることを assert する。
    /// 関数定義の境界判定は次の関数定義 `fn NAME(` まで、または `}\n\n`
    /// など緩い heuristic ではなく、関数名の出現位置から固定 window
    /// (5000 char) を見ることで誤検出を避ける。
    ///
    /// #645 で `extract_brightness_window_impl` を 5 番目の spawn site
    /// として追加。`impl` 関数は `pub` (integration test から呼ぶため)
    /// なので `pub async fn ...` で match する。
    #[test]
    fn lib_rs_applies_apply_no_window_at_all_spawn_sites() {
        let src = include_str!("lib.rs");
        for func in [
            "fn probe_video_with",
            "async fn ensure_thumbnail_exists",
            "async fn run_ffmpeg_export_attempt",
            "async fn start_detect",
            "pub async fn extract_brightness_window_impl",
        ] {
            let pos = src
                .find(func)
                .unwrap_or_else(|| panic!("function `{}` not found in lib.rs", func));
            // Look at the next 5000 chars after the fn header.
            let window_end = (pos + 5000).min(src.len());
            let window = &src[pos..window_end];
            assert!(
                window.contains("apply_no_window"),
                "function `{}` no longer calls `apply_no_window` within \
                 its first 5000 chars. #679 fix has regressed -- re-apply \
                 the helper at the spawn site.",
                func
            );
        }
    }
}
