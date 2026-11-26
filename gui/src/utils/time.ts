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
 * Format seconds as HH:MM:SS (no sub-second precision).
 *
 * `fmtTime` は 1 時間未満で MM:SS になるため、**録画先頭からの絶対秒**を
 * 並べると桁が揃わない。KO / ASSIST のイベント一覧 (#1106) とクリップ一覧
 * (#1131) は常に hh:mm:ss で揃える (Idios 判断 2026-11-16)。
 *
 * - Negative or NaN input is clamped to 0.
 * - 表示は 1 秒未満を切り捨てる (保存値は 0.01 秒精度のまま)。
 */
export function fmtClockTime(seconds: number): string {
  const clamped = Number.isFinite(seconds) && seconds > 0 ? seconds : 0;
  const total = Math.floor(clamped);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${pad(h)}:${pad(m)}:${pad(s)}`;
}

/**
 * Format seconds as HH:MM:SS.d (0.1 秒精度)。
 *
 * クリップ範囲エディタの「結果」行 (#1156) 用。TC 入力は `fmtPreciseTime`
 * (`H:MM:SS.FF`、**FF はフレーム番号**) なので、0.1 秒単位の比較表示はこの関数で行う。
 * 同じ瞬間を TC と結果で別の数字に見せないため、端点は **0.1 秒に丸める**
 * (切り捨てると 0.5 秒動かしても表示が変わらない = #1156 の症状 F)。
 *
 * - Negative / NaN input is clamped to 0.
 * - 丸めで 60.0 秒に上がる場合は繰り上げる (59.96 → `00:01:00.0`)。
 */
export function fmtClockTenths(seconds: number): string {
  const clamped = Number.isFinite(seconds) && seconds > 0 ? seconds : 0;
  const total = Math.round(clamped * 10);
  const h = Math.floor(total / 36000);
  const m = Math.floor((total % 36000) / 600);
  const s = Math.floor((total % 600) / 10);
  const tenth = total % 10;
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${pad(h)}:${pad(m)}:${pad(s)}.${tenth}`;
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
