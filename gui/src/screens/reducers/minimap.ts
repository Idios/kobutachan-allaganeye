/**
 * Pure transitions for the minimap screen phase state machine.
 * Mirrors reducers/export.ts — same events, same topology.
 * (#893 Phase 2 minimap crop GUI integration)
 */

export type MinimapPhase = 'idle' | 'running' | 'completed' | 'error' | 'cancelling';

export type MinimapAction =
  | { type: 'START_CLICKED' }
  | { type: 'PROGRESS_COMPLETE' }
  | { type: 'EXPORT_ERROR' }
  | { type: 'CANCEL_CLICKED' }
  | { type: 'CANCEL_CONFIRMED' }
  | { type: 'RESTART' }
  /**
   * Dispatched when an mtime conflict is detected during crop execution.
   * Moves running → idle so the user can retry (or choose overwrite via the
   * conflict modal) after the conflict modal closes.
   */
  | { type: 'CONFLICT_RESOLVED' };

export function minimapReducer(state: MinimapPhase, action: MinimapAction): MinimapPhase {
  switch (state) {
    case 'idle':
      if (action.type === 'START_CLICKED') return 'running';
      return state;

    case 'running':
      if (action.type === 'CANCEL_CLICKED') return 'cancelling';
      if (action.type === 'PROGRESS_COMPLETE') return 'completed';
      if (action.type === 'EXPORT_ERROR') return 'error';
      if (action.type === 'CONFLICT_RESOLVED') return 'idle';
      // Belt-and-suspenders: if kill_tracked_processes was called without going
      // through CANCEL_CLICKED (e.g. re-entrancy via auto-detect cancel path),
      // start_minimap still returns summary.cancelled → CANCEL_CONFIRMED arrives
      // from running. Without this guard phase would stay stuck at running forever.
      if (action.type === 'CANCEL_CONFIRMED') return 'idle';
      return state;

    case 'cancelling':
      // Mirror export reducer: if subprocess finishes before cancel completes,
      // treat as completed (prevents permanent stuck-in-cancelling state).
      if (action.type === 'PROGRESS_COMPLETE') return 'completed';
      if (action.type === 'CANCEL_CONFIRMED') return 'idle';
      if (action.type === 'EXPORT_ERROR') return 'idle';
      return state;

    case 'completed':
      if (action.type === 'RESTART') return 'idle';
      return state;

    case 'error':
      if (action.type === 'RESTART') return 'idle';
      return state;
  }
}
