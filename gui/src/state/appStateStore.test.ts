import { beforeEach, describe, expect, it } from 'vitest';

import { DEFAULT_DETECTION_PARAMS, useAppStateStore } from './appStateStore';

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

  // #545 review (2026-04-25): Tauri が Windows で返す `\\?\` extended-length
  // path prefix を保存前に正規化する。
  it('strips Windows \\\\?\\ extended-length prefix before storing', () => {
    useAppStateStore
      .getState()
      .setSelectedVideoPath('\\\\?\\E:\\videos\\clip.mkv');
    expect(useAppStateStore.getState().selectedVideoPath).toBe(
      'E:\\videos\\clip.mkv',
    );
  });

  it('converts \\\\?\\UNC\\ prefix into the standard \\\\ form', () => {
    useAppStateStore
      .getState()
      .setSelectedVideoPath('\\\\?\\UNC\\server\\share\\clip.mkv');
    expect(useAppStateStore.getState().selectedVideoPath).toBe(
      '\\\\server\\share\\clip.mkv',
    );
  });

  it('passes through paths without the prefix unchanged', () => {
    useAppStateStore.getState().setSelectedVideoPath('E:\\videos\\clip.mkv');
    expect(useAppStateStore.getState().selectedVideoPath).toBe(
      'E:\\videos\\clip.mkv',
    );
    useAppStateStore.getState().setSelectedVideoPath('/home/user/file.mkv');
    expect(useAppStateStore.getState().selectedVideoPath).toBe(
      '/home/user/file.mkv',
    );
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

  // #613: detect parameters tuned on the drop screen reset back to defaults.
  it('resets detectionParams back to defaults', () => {
    useAppStateStore
      .getState()
      .setDetectionParams({ blackoutThreshold: 30, gpu: false });
    useAppStateStore.getState().reset();
    expect(useAppStateStore.getState().detectionParams).toEqual(
      DEFAULT_DETECTION_PARAMS,
    );
  });
});

// #613
describe('useAppStateStore.detectionParams', () => {
  it('starts at the default values', () => {
    expect(useAppStateStore.getState().detectionParams).toEqual(
      DEFAULT_DETECTION_PARAMS,
    );
  });

  it('setDetectionParams patches a single field without touching others', () => {
    useAppStateStore.getState().setDetectionParams({ blackoutThreshold: 22 });
    const dp = useAppStateStore.getState().detectionParams;
    expect(dp.blackoutThreshold).toBe(22);
    expect(dp.workers).toBe(DEFAULT_DETECTION_PARAMS.workers);
    expect(dp.gpu).toBe(DEFAULT_DETECTION_PARAMS.gpu);
  });

  it('setDetectionParams supports multiple fields in one call', () => {
    useAppStateStore
      .getState()
      .setDetectionParams({ workers: 8, gpu: true });
    const dp = useAppStateStore.getState().detectionParams;
    expect(dp.workers).toBe(8);
    expect(dp.gpu).toBe(true);
  });

  it('resetDetectionParams restores defaults without touching the rest of state', () => {
    useAppStateStore.getState().setSelectedVideoPath('C:/video.mkv');
    useAppStateStore
      .getState()
      .setDetectionParams({ blackoutThreshold: 30, gpu: false });
    useAppStateStore.getState().resetDetectionParams();
    const state = useAppStateStore.getState();
    expect(state.detectionParams).toEqual(DEFAULT_DETECTION_PARAMS);
    // selectedVideoPath must NOT be cleared by resetDetectionParams.
    expect(state.selectedVideoPath).toBe('C:/video.mkv');
  });
});
