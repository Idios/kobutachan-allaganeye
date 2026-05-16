//! Windows Job Object wrapper for killing process trees on drop (#756).
//!
//! `ProcessJob::new` creates a Job Object configured with
//! `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`. `assign(raw_handle)` adds a process
//! HANDLE to the Job. When the `ProcessJob` value is dropped (= the Job
//! handle is closed via `CloseHandle`), Windows terminates the assigned
//! process **and every descendant it spawned** in one kernel-side operation.
//! The same cleanup happens automatically if our own process terminates
//! abnormally (panic / crash), because the kernel releases all handles
//! held by the dying process.
//!
//! ## Why this is needed
//!
//! `start_detect` spawns the `allaganeye detect` Python CLI; when GPU
//! detection is enabled the Python process in turn spawns up to 32 ffmpeg
//! children (see `gpu_detector.py`). On Windows, `tokio::process::Child::kill`
//! ultimately calls `TerminateProcess`, which only kills the direct child --
//! the Python process -- and leaves the ffmpeg children running as orphans
//! that continue to chew CPU and disk until the user notices them in Task
//! Manager. Job Objects give us a kernel-enforced "kill the whole tree"
//! primitive.
//!
//! Other spawn sites in `lib.rs` (`probe_video_with` /
//! `ensure_thumbnail_exists` / `extract_brightness_window_impl` /
//! `run_ffmpeg_export_attempt`) invoke ffmpeg/ffprobe directly with no
//! descendants and therefore do not need Job Objects;
//! `open_folder_in_explorer` intentionally detaches explorer.exe so the
//! user's file manager outlives the GUI. See
//! `docs/process-tree-orphan-audit.md` (#743) for the per-site rationale.

#![cfg(windows)]

use std::os::windows::io::RawHandle;

use windows::Win32::Foundation::{CloseHandle, HANDLE};
use windows::Win32::System::JobObjects::{
    AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
    SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
};

/// RAII wrapper around a Windows Job Object handle.
///
/// Closes the Job handle (and therefore kills every process inside it) on
/// drop. The wrapper itself is `Send + Sync` because `HANDLE` is a raw
/// pointer alias that is safe to move between threads (Windows kernel
/// handles are process-global).
pub struct ProcessJob {
    handle: HANDLE,
}

// SAFETY: `HANDLE` is a `*mut c_void` wrapper around an opaque kernel
// handle. Kernel handles are process-global (not thread-affinity); the
// `windows` crate does not implement `Send`/`Sync` for `HANDLE` by default
// because the underlying pointer type is `!Send`/`!Sync`, but for our
// usage (storing a Job handle on a struct that lives in the global
// PROCESS_TRACKER `Mutex` and is dropped on cancel) the handle can be
// safely sent across threads.
unsafe impl Send for ProcessJob {}
unsafe impl Sync for ProcessJob {}

impl ProcessJob {
    /// Create a new Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`
    /// set so that closing the returned handle (or letting it drop) kills
    /// every assigned process and its descendants.
    ///
    /// Returns `Err` if either `CreateJobObjectW` or `SetInformationJobObject`
    /// fails. On failure the partially-created handle (if any) is closed
    /// before returning so we never leak a kernel handle into the error
    /// path.
    pub fn new() -> std::io::Result<Self> {
        // CreateJobObjectW(None, None) returns an unnamed Job with default
        // security attributes. The `windows` crate's 0.61 binding returns
        // `Result<HANDLE>` and validates that the handle is non-NULL /
        // non-INVALID before yielding `Ok`.
        let handle = unsafe { CreateJobObjectW(None, None) }
            .map_err(|e| std::io::Error::other(e.to_string()))?;

        let mut info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
        info.BasicLimitInformation.LimitFlags |= JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;

        // SAFETY: `info` is a stack-allocated `JOBOBJECT_EXTENDED_LIMIT_INFORMATION`
        // owned by this scope; we pass its address and explicit byte size
        // to SetInformationJobObject, which only reads `cbjobobjectinformationlength`
        // bytes. `handle` is the freshly-created Job from CreateJobObjectW.
        let result = unsafe {
            SetInformationJobObject(
                handle,
                JobObjectExtendedLimitInformation,
                &info as *const _ as *const _,
                std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            )
        };
        if let Err(e) = result {
            // SetInformationJobObject failure leaves the Job alive but
            // without KILL_ON_JOB_CLOSE -- close it explicitly so we
            // never leak a handle on this error path.
            unsafe {
                let _ = CloseHandle(handle);
            }
            return Err(std::io::Error::other(format!(
                "SetInformationJobObject failed: {e}"
            )));
        }

        Ok(Self { handle })
    }

    /// Assign a process (identified by its Windows `HANDLE` from
    /// `tokio::process::Child::raw_handle()`) to this Job. After assignment,
    /// any descendant the process spawns will inherit Job membership
    /// unless it sets `JOB_OBJECT_LIMIT_BREAKAWAY_OK` (which neither
    /// Python nor ffmpeg does).
    ///
    /// Returns `Err` if `AssignProcessToJobObject` fails. The caller is
    /// expected to keep the spawned process alive on `Err` (Job
    /// assignment failure does not abort the child); the caller may log
    /// the failure and continue without tree-kill protection.
    pub fn assign(&self, process_handle: RawHandle) -> std::io::Result<()> {
        // `RawHandle` is `*mut c_void`; convert to the `windows` crate's
        // `HANDLE` newtype.
        let process_handle = HANDLE(process_handle.cast());
        unsafe { AssignProcessToJobObject(self.handle, process_handle) }
            .map_err(|e| std::io::Error::other(e.to_string()))
    }
}

impl Drop for ProcessJob {
    fn drop(&mut self) {
        // CloseHandle triggers KILL_ON_JOB_CLOSE inside the kernel,
        // terminating every assigned process and its descendants. We
        // discard the Result because there is no useful recovery: the
        // value is being dropped, and if CloseHandle fails the OS will
        // reclaim the handle when our process exits.
        unsafe {
            let _ = CloseHandle(self.handle);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Smoke test: creating + dropping a Job with no assigned processes
    /// is a no-op and must not panic. Pins the `CreateJobObjectW` +
    /// `SetInformationJobObject` happy path against a Windows API
    /// regression.
    #[test]
    fn process_job_new_then_drop_does_not_panic() {
        let job = ProcessJob::new().expect("CreateJobObject should succeed");
        drop(job);
    }

    /// Assigning a freshly-spawned `cmd /c exit 0` child to the Job and
    /// then dropping the Job must terminate it cleanly. We don't observe
    /// the kill directly (process exits on its own anyway) but we pin
    /// that `assign` + drop sequence compiles and runs.
    #[tokio::test]
    async fn process_job_assign_real_child_drop_kills_it() {
        let mut spawn = tokio::process::Command::new("cmd");
        spawn.args(["/c", "exit", "0"]);
        let child = spawn.spawn().expect("spawn cmd child");

        let job = ProcessJob::new().expect("CreateJobObject should succeed");
        if let Some(raw) = child.raw_handle() {
            job.assign(raw).expect("AssignProcessToJobObject should succeed");
        }
        drop(job);
        // Don't await the child: drop already requested termination via
        // KILL_ON_JOB_CLOSE; the OS may report either a normal `exit 0`
        // exit code or a kill code depending on timing.
    }
}
