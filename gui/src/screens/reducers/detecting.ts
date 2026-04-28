import type { DetectingPhase } from '../types';

/**
 * Pure transitions for the detecting screen phase state machine.
 * See docs/ui-architecture.md §detecting.
 *
 * Phase 2 drives these transitions with a dummy progress interval; Phase 3
 * will replace the driver with real CLI stdout events but keep this reducer.
 */
export type DetectingEvent =
  | { type: 'CANCEL_CLICKED' }
  | { type: 'CANCEL_CONFIRMED' }
  | { type: 'PROGRESS_COMPLETE' }
  | { type: 'DETECT_ERROR' }
  // #646 review Round 2 課題 2 -- error view の [再試行] から発火。
  // error → running の唯一の自動遷移経路で、ユーザー操作起因 (drop
  // / refine 失敗 → 再試行 / done からの戻り等) のみ許可される。
  | { type: 'RETRY' };

export function detectingReducer(
  phase: DetectingPhase,
  event: DetectingEvent,
): DetectingPhase {
  switch (phase) {
    case 'running':
      if (event.type === 'CANCEL_CLICKED') return 'cancelling';
      if (event.type === 'PROGRESS_COMPLETE') return 'completed';
      if (event.type === 'DETECT_ERROR') return 'error';
      return phase;

    case 'cancelling':
      if (event.type === 'CANCEL_CONFIRMED') return 'cancelled';
      // Errors during cancel still route to cancelled (treat as done).
      if (event.type === 'DETECT_ERROR') return 'cancelled';
      return phase;

    case 'error':
      // #646 -- only RETRY transitions out of error; navigation to drop
      // is the caller's responsibility (DetectingScreen back button).
      if (event.type === 'RETRY') return 'running';
      return phase;

    // Terminal-within-screen states — transitions out are handled by the caller
    // via navigate('drop') / navigate('complete').
    case 'cancelled':
    case 'completed':
      return phase;
  }
}
