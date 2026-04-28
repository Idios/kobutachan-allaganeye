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
 * - `noAudio` is always sent — it is a plain boolean and the Rust side
 *   only emits `--no-audio` when `Some(true)`.
 */
export function toStartDetectParams(p: DetectionParams): Record<string, unknown> {
  return {
    blackoutThreshold: p.blackoutThreshold,
    workers: p.workers > 0 ? p.workers : null,
    noAudio: p.noAudio,
    gpu: p.gpu,
  };
}

/**
 * Returns true when the supplied params differ from {@link DEFAULT_DETECTION_PARAMS}.
 * Used by the panel's [リセット] button to enable/disable itself.
 */
export function isDetectionParamsModified(p: DetectionParams): boolean {
  return (
    p.blackoutThreshold !== DEFAULT_DETECTION_PARAMS.blackoutThreshold ||
    p.workers !== DEFAULT_DETECTION_PARAMS.workers ||
    p.noAudio !== DEFAULT_DETECTION_PARAMS.noAudio ||
    p.gpu !== DEFAULT_DETECTION_PARAMS.gpu
  );
}
