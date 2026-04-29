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
    expect(state.loadError).toBeNull();
  });

  it('populates entries from read_recent and flips loaded=true', async () => {
    const fixture = [entry('E:/a.mkv', 'a.mkv'), entry('E:/b.mkv', 'b.mkv')];
    invokeMock.mockResolvedValueOnce(fixture);
    await useRecentStore.getState().load();
    const state = useRecentStore.getState();
    expect(state.entries).toEqual(fixture);
    expect(state.loaded).toBe(true);
    expect(state.loadError).toBeNull();
    expect(invokeMock).toHaveBeenCalledWith('read_recent');
  });

  it('keeps a previous error from blocking subsequent successful loads', async () => {
    invokeMock.mockRejectedValueOnce(new Error('disk read failed'));
    await useRecentStore.getState().load();
    expect(useRecentStore.getState().loadError).toBe('disk read failed');
    invokeMock.mockResolvedValueOnce([entry('E:/a.mkv', 'a.mkv')]);
    await useRecentStore.getState().load();
    const state = useRecentStore.getState();
    expect(state.entries).toHaveLength(1);
    expect(state.loadError).toBeNull();
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

  it('records addError when add_recent fails (e.g. file deleted)', async () => {
    invokeMock.mockRejectedValueOnce(new Error('file not found: E:/a.mkv'));
    await useRecentStore.getState().add('E:/a.mkv');
    expect(useRecentStore.getState().addError).toBe(
      'file not found: E:/a.mkv',
    );
    expect(useRecentStore.getState().entries).toEqual([]);
  });

  it('clears addError after a subsequent successful add', async () => {
    invokeMock.mockRejectedValueOnce(new Error('boom'));
    await useRecentStore.getState().add('E:/a.mkv');
    expect(useRecentStore.getState().addError).toBe('boom');
    invokeMock.mockResolvedValueOnce([entry('E:/b.mkv', 'b.mkv')]);
    await useRecentStore.getState().add('E:/b.mkv');
    expect(useRecentStore.getState().addError).toBeNull();
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
      loadError: 'old error',
      addError: 'old add error',
    });
    useRecentStore.getState().reset();
    const state = useRecentStore.getState();
    expect(state.entries).toEqual([]);
    expect(state.loaded).toBe(false);
    expect(state.loadError).toBeNull();
    expect(state.addError).toBeNull();
    // reset() must not call invoke (it's a pure in-memory operation).
    expect(invokeMock).not.toHaveBeenCalled();
  });
});
