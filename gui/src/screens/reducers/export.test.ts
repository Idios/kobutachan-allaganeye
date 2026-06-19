import { describe, expect, it } from 'vitest';

import { exportReducer } from './export';

describe('exportReducer', () => {
  it('goes idle -> running on START_CLICKED', () => {
    expect(exportReducer('idle', { type: 'START_CLICKED' })).toBe('running');
  });

  it('goes running -> cancelling on CANCEL_CLICKED', () => {
    expect(exportReducer('running', { type: 'CANCEL_CLICKED' })).toBe(
      'cancelling',
    );
  });

  it('goes running -> completed on PROGRESS_COMPLETE', () => {
    expect(exportReducer('running', { type: 'PROGRESS_COMPLETE' })).toBe(
      'completed',
    );
  });

  it('goes running -> error on EXPORT_ERROR', () => {
    expect(exportReducer('running', { type: 'EXPORT_ERROR' })).toBe('error');
  });

  it('goes cancelling -> idle on CANCEL_CONFIRMED', () => {
    expect(exportReducer('cancelling', { type: 'CANCEL_CONFIRMED' })).toBe(
      'idle',
    );
  });

  it('goes cancelling -> idle on EXPORT_ERROR (treated as cancel-success)', () => {
    expect(exportReducer('cancelling', { type: 'EXPORT_ERROR' })).toBe('idle');
  });

  // #837 (P2-14) -- cancel 要求後に export が中断前に完了する race。出力は
  // 揃っているので completed が正。修正前は PROGRESS_COMPLETE 未処理で
  // cancelling に滞留し「中断中…」永久スタックだった。
  it('goes cancelling -> completed on PROGRESS_COMPLETE (#837)', () => {
    expect(exportReducer('cancelling', { type: 'PROGRESS_COMPLETE' })).toBe(
      'completed',
    );
  });

  it('goes completed -> idle on RESTART', () => {
    expect(exportReducer('completed', { type: 'RESTART' })).toBe('idle');
  });

  it('goes error -> idle on DISMISS_ERROR or RESTART', () => {
    expect(exportReducer('error', { type: 'DISMISS_ERROR' })).toBe('idle');
    expect(exportReducer('error', { type: 'RESTART' })).toBe('idle');
  });

  it('ignores events that do not apply to the current phase', () => {
    expect(exportReducer('idle', { type: 'CANCEL_CLICKED' })).toBe('idle');
    expect(exportReducer('completed', { type: 'CANCEL_CLICKED' })).toBe(
      'completed',
    );
  });
});
