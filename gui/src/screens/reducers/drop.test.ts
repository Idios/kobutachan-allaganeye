import { describe, expect, it } from 'vitest';

import { dropReducer } from './drop';

describe('dropReducer', () => {
  it('goes idle -> selecting on BROWSE_CLICKED', () => {
    expect(dropReducer('idle', { type: 'BROWSE_CLICKED' })).toBe('selecting');
  });

  it('goes idle -> probing on DND_DROPPED', () => {
    expect(dropReducer('idle', { type: 'DND_DROPPED' })).toBe('probing');
  });

  // #571: clicking a recent-list item also goes idle -> probing, but via a
  // dedicated event so the reducer stays self-documenting.
  it('goes idle -> probing on RECENT_PICKED (#571)', () => {
    expect(dropReducer('idle', { type: 'RECENT_PICKED' })).toBe('probing');
  });

  it('goes selecting -> idle on DIALOG_CANCELLED', () => {
    expect(dropReducer('selecting', { type: 'DIALOG_CANCELLED' })).toBe('idle');
  });

  it('goes selecting -> probing on FILE_PICKED', () => {
    expect(dropReducer('selecting', { type: 'FILE_PICKED' })).toBe('probing');
  });

  it('goes probing -> selected on PROBE_OK', () => {
    expect(dropReducer('probing', { type: 'PROBE_OK' })).toBe('selected');
  });

  it('goes probing -> probeError on PROBE_FAIL', () => {
    expect(dropReducer('probing', { type: 'PROBE_FAIL' })).toBe('probeError');
  });

  it('goes selected -> idle on CANCEL_SELECTION', () => {
    expect(dropReducer('selected', { type: 'CANCEL_SELECTION' })).toBe('idle');
  });

  it('stays selected on CONFIRM_SELECTION (handoff is external)', () => {
    expect(dropReducer('selected', { type: 'CONFIRM_SELECTION' })).toBe('selected');
  });

  it('goes probeError -> idle on DISMISS_ERROR', () => {
    expect(dropReducer('probeError', { type: 'DISMISS_ERROR' })).toBe('idle');
  });

  it('allows retrying from probeError via BROWSE_CLICKED', () => {
    expect(dropReducer('probeError', { type: 'BROWSE_CLICKED' })).toBe('selecting');
  });

  it('ignores unknown events per state (no-op)', () => {
    expect(dropReducer('idle', { type: 'CONFIRM_SELECTION' })).toBe('idle');
    expect(dropReducer('probing', { type: 'BROWSE_CLICKED' })).toBe('probing');
  });
});
