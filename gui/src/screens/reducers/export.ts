import type { ExportPhase } from '../types';

/**
 * Pure transitions for the export screen phase state machine.
 * See docs/ui-architecture.md §export.
 *
 * Phase 2: the export screen mounts with `idle`, transitions via the same
 * events the Phase 4 real-ffmpeg driver will emit.
 */
export type ExportEvent =
  | { type: 'START_CLICKED' }
  | { type: 'CANCEL_CLICKED' }
  | { type: 'CANCEL_CONFIRMED' }
  | { type: 'PROGRESS_COMPLETE' }
  | { type: 'EXPORT_ERROR' }
  | { type: 'RESTART' }
  | { type: 'DISMISS_ERROR' };

export function exportReducer(
  phase: ExportPhase,
  event: ExportEvent,
): ExportPhase {
  switch (phase) {
    case 'idle':
      if (event.type === 'START_CLICKED') return 'running';
      return phase;

    case 'running':
      if (event.type === 'CANCEL_CLICKED') return 'cancelling';
      if (event.type === 'PROGRESS_COMPLETE') return 'completed';
      if (event.type === 'EXPORT_ERROR') return 'error';
      return phase;

    case 'cancelling':
      // #837 (P2-14) -- export が中断完了前に終わった race。出力は揃って
      // いるので completed を表示する (cancelling 滞留=永久スタックを防ぐ)。
      if (event.type === 'PROGRESS_COMPLETE') return 'completed';
      if (event.type === 'CANCEL_CONFIRMED') return 'idle';
      if (event.type === 'EXPORT_ERROR') return 'idle';
      return phase;

    case 'completed':
      if (event.type === 'RESTART') return 'idle';
      return phase;

    case 'error':
      if (event.type === 'DISMISS_ERROR') return 'idle';
      if (event.type === 'RESTART') return 'idle';
      return phase;
  }
}
