import { describe, expect, it } from 'vitest';

import { detectingReducer } from './detecting';

describe('detectingReducer', () => {
  it('goes running -> cancelling on CANCEL_CLICKED', () => {
    expect(
      detectingReducer('running', { type: 'CANCEL_CLICKED' }),
    ).toBe('cancelling');
  });

  it('goes running -> completed on PROGRESS_COMPLETE', () => {
    expect(
      detectingReducer('running', { type: 'PROGRESS_COMPLETE' }),
    ).toBe('completed');
  });

  it('goes running -> error on DETECT_ERROR', () => {
    expect(detectingReducer('running', { type: 'DETECT_ERROR' })).toBe('error');
  });

  it('goes cancelling -> cancelled on CANCEL_CONFIRMED', () => {
    expect(
      detectingReducer('cancelling', { type: 'CANCEL_CONFIRMED' }),
    ).toBe('cancelled');
  });

  it('goes cancelling -> cancelled even if DETECT_ERROR fires during cancel', () => {
    expect(
      detectingReducer('cancelling', { type: 'DETECT_ERROR' }),
    ).toBe('cancelled');
  });

  it('leaves terminal states alone', () => {
    expect(
      detectingReducer('completed', { type: 'CANCEL_CLICKED' }),
    ).toBe('completed');
    expect(
      detectingReducer('cancelled', { type: 'PROGRESS_COMPLETE' }),
    ).toBe('cancelled');
    expect(
      detectingReducer('error', { type: 'CANCEL_CLICKED' }),
    ).toBe('error');
  });

  // #646 review Round 2 課題 2 -- RETRY action transitions error → running.
  it('goes error -> running on RETRY', () => {
    expect(detectingReducer('error', { type: 'RETRY' })).toBe('running');
  });

  it('ignores RETRY in non-error states', () => {
    // RETRY should be a no-op anywhere except error to avoid restarting
    // detection from inside a running / cancelling / cancelled / completed flow.
    expect(detectingReducer('running', { type: 'RETRY' })).toBe('running');
    expect(detectingReducer('cancelling', { type: 'RETRY' })).toBe('cancelling');
    expect(detectingReducer('cancelled', { type: 'RETRY' })).toBe('cancelled');
    expect(detectingReducer('completed', { type: 'RETRY' })).toBe('completed');
  });
});
