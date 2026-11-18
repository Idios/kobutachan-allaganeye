import {
  DEFAULT_DETECTION_PARAMS,
  type DetectionParams,
} from '../state/appStateStore';

/**
 * #613: Convert the DropScreen-tuned `DetectionParams` to the args object
 * passed to the Rust `start_detect` Tauri command (#569).
 *
 * Rust side `DetectParams` fields are all `Option<T>` and any `None` simply
 * leaves the corresponding `--flag` off the CLI argv. We adopt the same
 * convention here:
 *
 * - `workers: 0` (the "auto" sentinel in our UI) maps to `null` so Rust
 *   omits `--workers`; any positive int passes through.
 * - `gpu: null` (the "auto" tri-state in our UI) maps to `null` for the
 *   same reason; `true` -> `--gpu`, `false` -> `--no-gpu`.
 * - `blackoutThreshold` is always sent — the user always sees a concrete
 *   value on the slider, and the CLI default (15.0) is harmless when
 *   echoed back.
 * - `detectionPath` (#1136) is **omitted entirely** for `'standard'`, so the
 *   "標準" path keeps the pre-#1136 argv byte-for-byte. `'masked'` sends
 *   `masked: true`, `'vtuber'` sends `vtuber: true`; the two are mutually
 *   exclusive by construction (single enum, not two booleans), which the
 *   CLI enforces with exit 5 and `start_detect` re-checks before spawning.
 *
 * NOTE: `noAudio` is intentionally not in `DetectionParams` (audio module
 * frozen -- `AUDIO_FROZEN` in `allaganeye/audio/__init__.py`, which skips the
 * Fanfare *scan* regardless of the flag's value; the flag still participates
 * in the detection cache key and in `metadata.json`, so it is not inert
 * end-to-end). The freeze is indefinite with no scheduled review date (#865,
 * still open); #327 is closed and will never "ship", so this is not a pending
 * item. Re-add the flag here and to the panel UI only if that decision is
 * reversed.
 */
export function toStartDetectParams(p: DetectionParams): Record<string, unknown> {
  const args: Record<string, unknown> = {
    blackoutThreshold: p.blackoutThreshold,
    workers: p.workers > 0 ? p.workers : null,
    gpu: p.gpu,
  };
  if (p.detectionPath === 'masked') {
    args.masked = true;
  } else if (p.detectionPath === 'vtuber') {
    args.vtuber = true;
  }
  // #1141: OFF のときはキー自体を送らない (Rust 側も `Some(false)` では flag を
  // 載せない)。これで従来の argv が 1 バイトも変わらない。
  if (p.indicators) {
    args.indicators = true;
  }
  return args;
}

/**
 * Returns true when the supplied params differ from {@link DEFAULT_DETECTION_PARAMS}.
 * Used by the panel's [リセット] button to enable/disable itself.
 */
export function isDetectionParamsModified(p: DetectionParams): boolean {
  return (
    p.blackoutThreshold !== DEFAULT_DETECTION_PARAMS.blackoutThreshold ||
    p.workers !== DEFAULT_DETECTION_PARAMS.workers ||
    p.gpu !== DEFAULT_DETECTION_PARAMS.gpu ||
    p.detectionPath !== DEFAULT_DETECTION_PARAMS.detectionPath ||
    p.indicators !== DEFAULT_DETECTION_PARAMS.indicators
  );
}
