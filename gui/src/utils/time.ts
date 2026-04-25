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
 * - **#465 review**: 120 / 240 fps もサポート。frame portion の桁数は
 *   `String(fps - 1).length` で動的決定 (60fps → 2 digit, 120/240fps →
 *   3 digit)。total frames を `Math.round(abs * fps)` で 1 度に丸めることで
 *   IEEE 754 誤差で frame が 1 つ少なく見える問題を回避する。
 */
export function fmtPreciseTime(seconds: number, fps = 60): string {
  if (!Number.isFinite(seconds)) {
    seconds = 0;
  }
  const sign = seconds < 0 ? '-' : '';
  const abs = Math.abs(seconds);
  const fpsInt = Math.round(fps);
  const h = Math.floor(abs / 3600);
  const m = Math.floor((abs % 3600) / 60);
  const sec = Math.floor(abs % 60);
  // floor を保つ (truncation セマンティクスは既存) が、frame-grid 上の値で
  // IEEE 754 誤差により 1 frame 少なく見えるのを epsilon で吸収する。
  // 例: 91/120 sec は (sub - 2438) * 120 = 90.99999996... だが、+1e-9 で
  // floor が正しく 91 を返す。
  const frames = Math.floor((abs - Math.floor(abs)) * fpsInt + 1e-9);
  // 桁数は最大 frame 番号 (fps - 1) を表せるだけ確保 (60fps → 2 桁、120fps
  // → 3 桁、240fps → 3 桁)。
  const frameWidth = String(Math.max(fpsInt - 1, 0)).length;
  return (
    `${sign}${h}:` +
    `${String(m).padStart(2, '0')}:` +
    `${String(sec).padStart(2, '0')}.` +
    `${String(frames).padStart(frameWidth, '0')}`
  );
}

/**
 * Format seconds as `{m}m{ss}s` or `{h}h{mm}m` — mirror of CLI
 * `_format_duration` in `allaganeye/commands/split_matches.py`.
 *
 * - <1h: `{m}m{ss:02}s` — e.g. `15m15s`, `5m49s`, `43m02s`
 * - >=1h: `{h}h{mm:02}m` — e.g. `1h05m`, `2h30m`
 *
 * Negative / NaN input clamps to 0 (mirroring fmtTime). Used by ExportScreen
 * list to recompute duration when `m.edited?.start_time` / `end_time` differ
 * from the CLI-provided `m.duration_display` (#466 review, boundary
 * propagation bug).
 */
export function fmtMatchDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) {
    seconds = 0;
  }
  const total = Math.floor(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) {
    return `${h}h${String(m).padStart(2, '0')}m`;
  }
  return `${m}m${String(s).padStart(2, '0')}s`;
}
