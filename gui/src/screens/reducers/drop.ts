import type { DropPhase } from '../types';

/**
 * Pure transitions for the drop screen phase state machine.
 * See docs/ui-architecture.md §drop.
 *
 * These are pure functions so tests can exhaustively verify behavior and
 * Phase 3 can swap the side-effecting dispatcher without touching logic.
 */
export type DropEvent =
  | { type: 'BROWSE_CLICKED' }
  | { type: 'DIALOG_CANCELLED' }
  | { type: 'FILE_PICKED' }
  | { type: 'DND_DROPPED' }
  | { type: 'PROBE_OK' }
  | { type: 'PROBE_FAIL' }
  | { type: 'CANCEL_SELECTION' }
  | { type: 'CONFIRM_SELECTION' }
  | { type: 'DISMISS_ERROR' };

export function dropReducer(phase: DropPhase, event: DropEvent): DropPhase {
  switch (phase) {
    case 'idle':
      if (event.type === 'BROWSE_CLICKED') return 'selecting';
      if (event.type === 'DND_DROPPED') return 'probing';
      return phase;

    case 'selecting':
      if (event.type === 'DIALOG_CANCELLED') return 'idle';
      if (event.type === 'FILE_PICKED') return 'probing';
      return phase;

    case 'probing':
      if (event.type === 'PROBE_OK') return 'selected';
      if (event.type === 'PROBE_FAIL') return 'probeError';
      return phase;

    case 'selected':
      if (event.type === 'CANCEL_SELECTION') return 'idle';
      if (event.type === 'CONFIRM_SELECTION') return 'selected'; // handoff to detecting screen occurs externally
      return phase;

    case 'probeError':
      if (event.type === 'DISMISS_ERROR') return 'idle';
      if (event.type === 'BROWSE_CLICKED') return 'selecting';
      return phase;
  }
}
