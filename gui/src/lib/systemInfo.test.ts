import { describe, expect, it } from 'vitest';

import { formatSystemInfo, type EnvironmentProbe } from './systemInfo';
import type { SystemInfo } from '../types/metadata.generated';

const FULL_PROBE: EnvironmentProbe = {
  allaganeye_version: '0.2.0',
  os_name: 'Microsoft Windows 11 (Build 22631)',
  cpu_info: 'AMD Ryzen 9 9950X3D (16C/32T)',
  memory_total_gb: 61.6,
  disk_free_gb: 1359.5,
  disk_total_gb: 3726.0,
  disk_drive: 'E:',
};

const FULL_GPU: SystemInfo = {
  gpu_vendors_available: ['nvidia'],
  gpu_vendor_used: 'nvidia',
  vendor_preference: ['nvidia', 'amd', 'intel'],
};

describe('formatSystemInfo (#669)', () => {
  it('renders complete probe + GPU info in bug_report.yml placeholder format', () => {
    const out = formatSystemInfo(FULL_PROBE, FULL_GPU);
    // header line "allaganeye <ver> (<os>)"
    expect(out).toMatch(/^allaganeye 0\.2\.0 \(Microsoft Windows 11 \(Build 22631\)\)/);
    // body has CPU / GPU / Memory / Disk lines
    expect(out).toContain('CPU: AMD Ryzen 9 9950X3D (16C/32T)');
    expect(out).toContain('GPU: nvidia');
    expect(out).toContain('Memory: 61.6 GB');
    expect(out).toContain('Disk: 1359.5 / 3726.0 GB free on E:');
  });

  it('lists multiple GPU vendors comma-separated', () => {
    const multiGpu: SystemInfo = {
      ...FULL_GPU,
      gpu_vendors_available: ['nvidia', 'amd'],
    };
    const out = formatSystemInfo(FULL_PROBE, multiGpu);
    expect(out).toContain('GPU: nvidia, amd');
  });

  it('renders "GPU: (none detected)" when no GPU vendors available', () => {
    const noGpu: SystemInfo = { ...FULL_GPU, gpu_vendors_available: [] };
    const out = formatSystemInfo(FULL_PROBE, noGpu);
    expect(out).toContain('GPU: (none detected)');
  });

  it('renders "GPU: (unknown)" when systemInfo is null (e.g. metadata missing)', () => {
    const out = formatSystemInfo(FULL_PROBE, null);
    expect(out).toContain('GPU: (unknown)');
  });

  it('skips Disk line when probe disk fields are null', () => {
    const noDisk: EnvironmentProbe = {
      ...FULL_PROBE,
      disk_free_gb: null,
      disk_total_gb: null,
      disk_drive: null,
    };
    const out = formatSystemInfo(noDisk, FULL_GPU);
    expect(out).not.toContain('Disk:');
    // 他の行は残る
    expect(out).toContain('Memory: 61.6 GB');
  });

  it('skips Memory line when probe memory_total_gb is null', () => {
    const noMem: EnvironmentProbe = { ...FULL_PROBE, memory_total_gb: null };
    const out = formatSystemInfo(noMem, FULL_GPU);
    expect(out).not.toContain('Memory:');
    expect(out).toContain('CPU:');
  });

  it('returns "(no environment info)" when both probe and systemInfo are null', () => {
    expect(formatSystemInfo(null, null)).toBe('(no environment info)');
  });

  it('renders header with "(unknown OS)" when probe.os_name is empty', () => {
    const probeNoOs: EnvironmentProbe = { ...FULL_PROBE, os_name: '' };
    const out = formatSystemInfo(probeNoOs, FULL_GPU);
    expect(out).toMatch(/^allaganeye 0\.2\.0 \(\(unknown OS\)\)/);
  });

  it('formats memory and disk to 1 decimal place', () => {
    const probe: EnvironmentProbe = {
      ...FULL_PROBE,
      memory_total_gb: 61.62345,
      disk_free_gb: 100.456,
      disk_total_gb: 500.0,
    };
    const out = formatSystemInfo(probe, FULL_GPU);
    expect(out).toContain('Memory: 61.6 GB');
    expect(out).toContain('Disk: 100.5 / 500.0 GB free on E:');
  });

  it('renders GPU-only section when probe is null but systemInfo is present', () => {
    const out = formatSystemInfo(null, FULL_GPU);
    expect(out).toContain('GPU: nvidia');
    // header should be a degraded form
    expect(out).toMatch(/^allaganeye \(unknown version\)/);
  });
});
