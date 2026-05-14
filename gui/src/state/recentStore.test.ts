import { beforeEach, describe, expect, it, vi } from 'vitest';

const { invokeMock } = vi.hoisted(() => ({ invokeMock: vi.fn() }));

vi.mock('@tauri-apps/api/core', () => ({
  invoke: invokeMock,
}));

import { useRecentStore, type RecentEntry } from './recentStore';

function entry(path: string, fileName: string): RecentEntry {
  return {
    path,
    fileName,
    sizeBytes: 1024,
    mtimeMs: 1_700_000_000_000,
    addedAtMs: 1_700_000_000_000,
  };
}

beforeEach(() => {
  invokeMock.mockReset();
  useRecentStore.getState().reset();
});

describe('useRecentStore.load (#571)', () => {
  it('starts with empty entries and loaded=false', () => {
    const state = useRecentStore.getState();
    expect(state.entries).toEqual([]);
    expect(state.loaded).toBe(false);
    expect(state.loadErrorState).toBeNull();
  });

  it('populates entries from read_recent and flips loaded=true', async () => {
    const fixture = [entry('E:/a.mkv', 'a.mkv'), entry('E:/b.mkv', 'b.mkv')];
    invokeMock.mockResolvedValueOnce(fixture);
    await useRecentStore.getState().load();
    const state = useRecentStore.getState();
    expect(state.entries).toEqual(fixture);
    expect(state.loaded).toBe(true);
    expect(state.loadErrorState).toBeNull();
    expect(invokeMock).toHaveBeenCalledWith('read_recent');
  });

  it('keeps a previous error from blocking subsequent successful loads', async () => {
    invokeMock.mockRejectedValueOnce(new Error('disk read failed'));
    await useRecentStore.getState().load();
    expect(useRecentStore.getState().loadErrorState).toEqual({
      message: 'disk read failed',
      hint: null,
      code: null,
    });
    invokeMock.mockResolvedValueOnce([entry('E:/a.mkv', 'a.mkv')]);
    await useRecentStore.getState().load();
    const state = useRecentStore.getState();
    expect(state.entries).toHaveLength(1);
    expect(state.loadErrorState).toBeNull();
  });
});

describe('useRecentStore.add (#571)', () => {
  it('replaces entries with the post-write snapshot returned by add_recent', async () => {
    invokeMock.mockResolvedValueOnce([entry('E:/a.mkv', 'a.mkv')]);
    await useRecentStore.getState().add('E:/a.mkv');
    expect(invokeMock).toHaveBeenCalledWith('add_recent', { path: 'E:/a.mkv' });
    expect(useRecentStore.getState().entries).toEqual([
      entry('E:/a.mkv', 'a.mkv'),
    ]);
  });

  it('records addErrorState when add_recent fails (e.g. file deleted)', async () => {
    invokeMock.mockRejectedValueOnce(new Error('file not found: E:/a.mkv'));
    await useRecentStore.getState().add('E:/a.mkv');
    expect(useRecentStore.getState().addErrorState).toEqual({
      message: 'file not found: E:/a.mkv',
      hint: null,
      code: null,
    });
    expect(useRecentStore.getState().entries).toEqual([]);
  });

  it('clears addErrorState after a subsequent successful add', async () => {
    invokeMock.mockRejectedValueOnce(new Error('boom'));
    await useRecentStore.getState().add('E:/a.mkv');
    expect(useRecentStore.getState().addErrorState).toEqual({
      message: 'boom',
      hint: null,
      code: null,
    });
    invokeMock.mockResolvedValueOnce([entry('E:/b.mkv', 'b.mkv')]);
    await useRecentStore.getState().add('E:/b.mkv');
    expect(useRecentStore.getState().addErrorState).toBeNull();
  });
});

describe('useRecentStore.clear (#571)', () => {
  it('invokes clear_recent and empties entries in-memory', async () => {
    // Seed entries first.
    invokeMock.mockResolvedValueOnce([entry('E:/a.mkv', 'a.mkv')]);
    await useRecentStore.getState().load();
    expect(useRecentStore.getState().entries).toHaveLength(1);

    invokeMock.mockResolvedValueOnce(undefined);
    await useRecentStore.getState().clear();
    expect(invokeMock).toHaveBeenLastCalledWith('clear_recent');
    expect(useRecentStore.getState().entries).toEqual([]);
  });
});

describe('useRecentStore.reset (#571)', () => {
  it('discards in-memory state without invoking Tauri', () => {
    useRecentStore.setState({
      entries: [entry('E:/a.mkv', 'a.mkv')],
      loaded: true,
      loadErrorState: { message: 'old error', hint: null, code: null },
      addErrorState: { message: 'old add error', hint: null, code: null },
    });
    useRecentStore.getState().reset();
    const state = useRecentStore.getState();
    expect(state.entries).toEqual([]);
    expect(state.loaded).toBe(false);
    expect(state.loadErrorState).toBeNull();
    expect(state.addErrorState).toBeNull();
    // reset() must not call invoke (it's a pure in-memory operation).
    expect(invokeMock).not.toHaveBeenCalled();
  });
});

// #663 / #694 — AppError hint pair → ErrorState. `loadErrorState` / `addErrorState`
// fields populated from AppError.hint/code when invoke rejects with a structured
// AppError object.
describe('AppError ErrorState (#663 / #694)', () => {
  beforeEach(() => {
    useRecentStore.getState().reset();
  });

  it('load path: loadErrorState carries hint and code from AppError', async () => {
    invokeMock.mockImplementation(async () => {
      throw {
        code: 'io.read_failed',
        message: 'broken recent.json',
        hint: 'delete the file and restart',
      };
    });
    await useRecentStore.getState().load();
    const s = useRecentStore.getState();
    expect(s.loadErrorState).toEqual({
      message: 'broken recent.json',
      hint: 'delete the file and restart',
      code: 'io.read_failed',
    });
  });

  it('add path: addErrorState carries hint and code from AppError', async () => {
    invokeMock.mockImplementation(async () => {
      throw {
        code: 'io.write_failed',
        message: 'recent.json write failed',
        hint: 'check disk space',
      };
    });
    await useRecentStore.getState().add('/tmp/x.mp4');
    const s = useRecentStore.getState();
    expect(s.addErrorState).toEqual({
      message: 'recent.json write failed',
      hint: 'check disk space',
      code: 'io.write_failed',
    });
  });
});
