import type { SystemInfo } from '../types/metadata.generated';

/**
 * #669 — Snapshot of OS / CPU / Memory / Disk info returned by the Tauri
 * `probe_environment_info` command. Combined with `metadata.system_info`
 * (GPU vendor list) by `formatSystemInfo()` to populate the `bug_report.yml`
 * `environment` field of the ErrorModal Issue 報告 link.
 *
 * Snake-case keys mirror the Rust `EnvironmentProbe` struct in
 * `gui/src-tauri/src/lib.rs` (Tauri serializes Rust struct field names
 * verbatim by default — no `#[serde(rename_all)]` is applied).
 *
 * Why a separate type vs. extending `SystemInfo`: the original spec/plan
 * assumed `metadata.system_info` already carried OS/CPU/Memory/Disk; in
 * reality the Python writer only puts 3 GPU fields there. Splitting the type
 * keeps `metadata.system_info` (= persisted on disk per video) cleanly
 * separate from `EnvironmentProbe` (= live-probed each ErrorModal open).
 */
export interface EnvironmentProbe {
  allaganeye_version: string;
  os_name: string;
  cpu_info: string;
  memory_total_gb: number | null;
  disk_free_gb: number | null;
  disk_total_gb: number | null;
  disk_drive: string | null;
}

/**
 * #669 — Renders the combined `EnvironmentProbe` (live Tauri probe) and
 * `SystemInfo` (metadata.json GPU vendors) into the `bug_report.yml`
 * `environment` placeholder format:
 *
 * ```text
 * allaganeye 0.2.0 (Microsoft Windows 11 (Build 22631))
 *   CPU: AMD Ryzen 9 9950X3D (16C/32T)
 *   GPU: nvidia, amd
 *   Memory: 61.6 GB
 *   Disk: 1359.5 / 3726.0 GB free on E:
 * ```
 *
 * Missing data degrades gracefully: nullable disk/memory fields skip their
 * line entirely; empty GPU vendor list shows `(none detected)`; a null
 * `systemInfo` shows `(unknown)`. When BOTH inputs are null the function
 * returns `(no environment info)` (an explicit sentinel so the URL builder
 * can still pre-fill *something* in the bug report).
 */
export function formatSystemInfo(
  probe: EnvironmentProbe | null,
  systemInfo: SystemInfo | null,
): string {
  if (!probe && !systemInfo) {
    return '(no environment info)';
  }

  const lines: string[] = [];

  // Header line: `allaganeye <ver> (<os_name>)`
  const version = probe?.allaganeye_version ?? '(unknown version)';
  const osName = probe?.os_name && probe.os_name.trim().length > 0
    ? probe.os_name
    : '(unknown OS)';
  lines.push(`allaganeye ${version} (${osName})`);

  // CPU
  if (probe?.cpu_info && probe.cpu_info.trim().length > 0) {
    lines.push(`  CPU: ${probe.cpu_info}`);
  } else {
    lines.push('  CPU: (unknown)');
  }

  // GPU (from systemInfo if present, else "(unknown)")
  const gpuLine = (() => {
    if (!systemInfo) return '(unknown)';
    if (!systemInfo.gpu_vendors_available || systemInfo.gpu_vendors_available.length === 0) {
      return '(none detected)';
    }
    return systemInfo.gpu_vendors_available.join(', ');
  })();
  lines.push(`  GPU: ${gpuLine}`);

  // Memory (skip line if null)
  if (probe && probe.memory_total_gb !== null && probe.memory_total_gb !== undefined) {
    lines.push(`  Memory: ${probe.memory_total_gb.toFixed(1)} GB`);
  }

  // Disk (skip line if any of the three fields is null)
  if (
    probe &&
    probe.disk_free_gb !== null &&
    probe.disk_free_gb !== undefined &&
    probe.disk_total_gb !== null &&
    probe.disk_total_gb !== undefined &&
    probe.disk_drive !== null &&
    probe.disk_drive !== undefined &&
    probe.disk_drive.length > 0
  ) {
    lines.push(
      `  Disk: ${probe.disk_free_gb.toFixed(1)} / ${probe.disk_total_gb.toFixed(1)} GB free on ${probe.disk_drive}`,
    );
  }

  return lines.join('\n');
}
