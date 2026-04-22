/**
 * Format seconds as H:MM:SS or MM:SS (no sub-second precision).
 * Mirror of fmtTime in docs/design/bundle/project/shared/common.jsx.
 *
 * - Negative or NaN input is clamped to 0.
 * - >= 1h produces H:MM:SS, otherwise MM:SS.
 */
export function fmtTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) {
    seconds = 0;
  }
  const s = Math.floor(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) {
    return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
  }
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
}

/**
 * Format seconds as HH:MM:SS.ff (frame-accurate timecode).
 * Mirror of fmtPreciseTime in docs/design/bundle/project/variants/aether-preview.jsx.
 *
 * - Negative input emits a leading minus sign.
 * - `fps` controls the frame denominator (default 60fps to match Phase 0 recording targets).
 */
export function fmtPreciseTime(seconds: number, fps = 60): string {
  if (!Number.isFinite(seconds)) {
    seconds = 0;
  }
  const sign = seconds < 0 ? '-' : '';
  const abs = Math.abs(seconds);
  const h = Math.floor(abs / 3600);
  const m = Math.floor((abs % 3600) / 60);
  const sec = Math.floor(abs % 60);
  const frames = Math.floor((abs - Math.floor(abs)) * fps);
  return (
    `${sign}${h}:` +
    `${String(m).padStart(2, '0')}:` +
    `${String(sec).padStart(2, '0')}.` +
    `${String(frames).padStart(2, '0')}`
  );
}
