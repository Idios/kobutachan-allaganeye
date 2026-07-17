import { describe, expect, it } from 'vitest';

import { minimapReducer } from './minimap';

describe('minimapReducer', () => {
  it('goes idle -> running on START_CLICKED', () => {
    expect(minimapReducer('idle', { type: 'START_CLICKED' })).toBe('running');
  });

  it('goes running -> cancelling on CANCEL_CLICKED', () => {
    expect(minimapReducer('running', { type: 'CANCEL_CLICKED' })).toBe('cancelling');
  });

  it('goes running -> completed on PROGRESS_COMPLETE', () => {
    expect(minimapReducer('running', { type: 'PROGRESS_COMPLETE' })).toBe('completed');
  });

  it('goes running -> error on EXPORT_ERROR', () => {
    expect(minimapReducer('running', { type: 'EXPORT_ERROR' })).toBe('error');
  });

  it('goes cancelling -> idle on CANCEL_CONFIRMED', () => {
    expect(minimapReducer('cancelling', { type: 'CANCEL_CONFIRMED' })).toBe('idle');
  });

  it('goes cancelling -> idle on EXPORT_ERROR (treated as cancel-success)', () => {
    expect(minimapReducer('cancelling', { type: 'EXPORT_ERROR' })).toBe('idle');
  });

  it('goes cancelling -> completed on PROGRESS_COMPLETE (race: subprocess finished before cancel)', () => {
    expect(minimapReducer('cancelling', { type: 'PROGRESS_COMPLETE' })).toBe('completed');
  });

  it('goes completed -> idle on RESTART', () => {
    expect(minimapReducer('completed', { type: 'RESTART' })).toBe('idle');
  });

  it('goes error -> idle on RESTART', () => {
    expect(minimapReducer('error', { type: 'RESTART' })).toBe('idle');
  });

  it('ignores events that do not apply to the current phase', () => {
    expect(minimapReducer('idle', { type: 'CANCEL_CLICKED' })).toBe('idle');
    expect(minimapReducer('completed', { type: 'CANCEL_CLICKED' })).toBe('completed');
  });

  // Fix 1 (#893 Task 11): CONFLICT_RESOLVED must move running → idle so the
  // crop button re-enables after an mtime conflict modal is dismissed.
  it('goes running -> idle on CONFLICT_RESOLVED', () => {
    expect(minimapReducer('running', { type: 'CONFLICT_RESOLVED' })).toBe('idle');
  });

  it('CONFLICT_RESOLVED is a no-op in idle/completed/error (not a spurious reset)', () => {
    expect(minimapReducer('idle', { type: 'CONFLICT_RESOLVED' })).toBe('idle');
    expect(minimapReducer('completed', { type: 'CONFLICT_RESOLVED' })).toBe('completed');
    expect(minimapReducer('error', { type: 'CONFLICT_RESOLVED' })).toBe('error');
  });
});
