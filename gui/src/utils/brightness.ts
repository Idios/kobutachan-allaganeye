/**
 * Build an SVG path (M … L … L …) from a brightness sample array.
 * Mirror of buildBrightnessPath in docs/design/bundle/project/shared/common.jsx.
 *
 * - `samples[i]` is expected to be in [0, 255] (255 = bright, 0 = black).
 * - The path is mapped into a (width × height) box where y=0 is the top.
 * - `yScale` optionally stretches the vertical axis (default 1 = full box).
 *
 * The function is pure and produces deterministic output — it is used both
 * for SVG rendering and for snapshot tests.
 */
export function buildBrightnessPath(
  samples: readonly number[],
  width: number,
  height: number,
  yScale = 1,
): string {
  const n = samples.length;
  if (n === 0) return '';
  if (n === 1) {
    const y = (height - (samples[0] / 255) * height * yScale).toFixed(2);
    return `M0 ${y}`;
  }
  let d = '';
  for (let i = 0; i < n; i++) {
    const x = ((i / (n - 1)) * width).toFixed(2);
    const y = (height - (samples[i] / 255) * height * yScale).toFixed(2);
    d += (i === 0 ? 'M' : 'L') + x + ' ' + y + ' ';
  }
  return d.trimEnd();
}

export interface BlackoutRegion {
  start: number;
  end: number;
}

/**
 * Find contiguous regions whose brightness is below `threshold`.
 * Mirror of findBlackoutRegions in docs/design/bundle/project/shared/common.jsx.
 *
 * - Times are derived by evenly distributing the samples across `duration`
 *   (sample i = t = (i / (n-1)) * duration).
 * - Adjacent below-threshold samples are merged into a single region.
 * - If the samples end while still below threshold, a region extends to `duration`.
 */
export function findBlackoutRegions(
  samples: readonly number[],
  duration: number,
  threshold = 15,
): BlackoutRegion[] {
  const regions: BlackoutRegion[] = [];
  if (samples.length === 0 || duration <= 0) return regions;
  let start: number | null = null;
  for (let i = 0; i < samples.length; i++) {
    const t = samples.length === 1 ? 0 : (i / (samples.length - 1)) * duration;
    if (samples[i] < threshold) {
      if (start === null) start = t;
    } else if (start !== null) {
      regions.push({ start, end: t });
      start = null;
    }
  }
  if (start !== null) regions.push({ start, end: duration });
  return regions;
}

/**
 * Generate a plausible per-second brightness signal around a boundary point.
 * Mirror of buildLocalBrightness in docs/design/bundle/project/variants/aether-preview.jsx.
 *
 * - `centerT` — the (assumed) boundary seconds value.
 * - `windowSec` — half-window in seconds. Returned array spans [centerT-window, centerT+window).
 * - `sampleHz` — samples per second (default 2).
 *
 * Phase 2 uses this to drive the preview screen's fine-grained timeline;
 * it is purely synthetic and deterministic-ish (depends on Math.random for
 * low-amplitude noise only — tests therefore assert structural properties
 * rather than exact values).
 */
export interface LocalBrightnessSample {
  t: number;
  b: number;
}

export function buildLocalBrightness(
  centerT: number,
  windowSec: number,
  sampleHz = 2,
): LocalBrightnessSample[] {
  const count = Math.max(0, windowSec * 2 * sampleHz);
  const out: LocalBrightnessSample[] = [];
  for (let i = 0; i < count; i++) {
    const t = centerT - windowSec + i / sampleHz;
    const distFromEdge = Math.abs(t - centerT);
    let b: number;
    if (distFromEdge < 1.2) {
      b = 4 + Math.random() * 6;
    } else if (distFromEdge < 2.5) {
      b = 20 + Math.random() * 30;
    } else {
      // In-match / pre-match gameplay: modulated sine with jitter
      b =
        85 +
        Math.sin(t * 0.4) * 18 +
        Math.sin(t * 1.3) * 10 +
        (Math.random() - 0.5) * 14;
    }
    out.push({ t, b: Math.max(0, Math.min(255, b)) });
  }
  return out;
}
