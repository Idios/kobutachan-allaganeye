/**
 * Phase enums for each screen's internal state machine.
 * See docs/ui-architecture.md for the full phase transition diagrams.
 *
 * These are kept separate from the screen name (AppScreen in appStateStore)
 * because screens internally go through several sub-states while the
 * top-level screen value stays constant.
 */

export type DropPhase =
  | 'idle'
  | 'selecting'
  | 'probing'
  | 'selected'
  | 'probeError';

export type DetectingPhase =
  | 'running'
  | 'cancelling'
  | 'cancelled'
  | 'completed'
  | 'error';

export type ExportPhase =
  | 'idle'
  | 'running'
  | 'cancelling'
  | 'completed'
  | 'error';

/**
 * Metadata returned by a (Phase 3: real) ffprobe call on a selected video.
 * Phase 2 fills this with dummy values after a simulated probe delay.
 */
export interface VideoProbeInfo {
  path: string;
  fileName: string;
  sizeBytes: number;
  durationSeconds: number;
  width: number;
  height: number;
  fps: number;
  codec: string;
}
