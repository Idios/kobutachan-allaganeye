import { beforeEach, describe, expect, it } from 'vitest';

import { useAppStateStore } from './appStateStore';

beforeEach(() => {
  useAppStateStore.getState().reset();
});

describe('useAppStateStore.navigate', () => {
  it('switches the current screen', () => {
    useAppStateStore.getState().navigate('complete');
    expect(useAppStateStore.getState().screen).toBe('complete');
  });

  it('keeps selectedMatchIndex and selectedVideoPath intact when navigating', () => {
    useAppStateStore.getState().selectMatch(3);
    useAppStateStore.getState().setSelectedVideoPath('C:/video.mkv');
    useAppStateStore.getState().navigate('preview');
    const state = useAppStateStore.getState();
    expect(state.screen).toBe('preview');
    expect(state.selectedMatchIndex).toBe(3);
    expect(state.selectedVideoPath).toBe('C:/video.mkv');
  });
});

describe('useAppStateStore.selectMatch', () => {
  it('sets and clears the selected match index', () => {
    useAppStateStore.getState().selectMatch(5);
    expect(useAppStateStore.getState().selectedMatchIndex).toBe(5);
    useAppStateStore.getState().selectMatch(null);
    expect(useAppStateStore.getState().selectedMatchIndex).toBeNull();
  });
});

describe('useAppStateStore.openPreviewFor', () => {
  it('sets selectedMatchIndex and moves to preview in one action', () => {
    useAppStateStore.getState().openPreviewFor(7);
    const state = useAppStateStore.getState();
    expect(state.selectedMatchIndex).toBe(7);
    expect(state.screen).toBe('preview');
  });
});

describe('useAppStateStore.setSelectedVideoPath', () => {
  it('records and clears the selected video path', () => {
    useAppStateStore.getState().setSelectedVideoPath('D:/clip.mp4');
    expect(useAppStateStore.getState().selectedVideoPath).toBe('D:/clip.mp4');
    useAppStateStore.getState().setSelectedVideoPath(null);
    expect(useAppStateStore.getState().selectedVideoPath).toBeNull();
  });
});

describe('useAppStateStore.reset', () => {
  it('returns the store to the initial drop screen state', () => {
    useAppStateStore.setState({
      screen: 'export',
      selectedMatchIndex: 4,
      selectedVideoPath: '/tmp/foo.mkv',
    });
    useAppStateStore.getState().reset();
    const state = useAppStateStore.getState();
    expect(state.screen).toBe('drop');
    expect(state.selectedMatchIndex).toBeNull();
    expect(state.selectedVideoPath).toBeNull();
  });
});
