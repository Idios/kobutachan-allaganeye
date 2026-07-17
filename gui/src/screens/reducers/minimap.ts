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
  | { type: 'RESTART' };

export function minimapReducer(state: MinimapPhase, action: MinimapAction): MinimapPhase {
  switch (state) {
    case 'idle':
      if (action.type === 'START_CLICKED') return 'running';
      return state;

    case 'running':
      if (action.type === 'CANCEL_CLICKED') return 'cancelling';
      if (action.type === 'PROGRESS_COMPLETE') return 'completed';
      if (action.type === 'EXPORT_ERROR') return 'error';
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
