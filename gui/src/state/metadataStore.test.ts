import { beforeEach, describe, expect, it, vi } from 'vitest';

const { invokeMock } = vi.hoisted(() => ({ invokeMock: vi.fn() }));

vi.mock('@tauri-apps/api/core', () => ({
  invoke: invokeMock,
}));

import { useMetadataStore } from './metadataStore';
import type { Metadata } from '../types/metadata';

function validMetadata(): Metadata {
  return {
    source: 'C:/videos/2026-04-08.mkv',
    source_duration: 10200,
    source_duration_display: '2:50:00',
    detected_at: '2026-04-22T00:00:00Z',
    detection_params: {
      sample_interval: 2,
      blackout_threshold: 15,
      min_match_duration: 300,
      min_blackout_duration: 3,
      no_audio: false,
      use_gpu: null,
      workers: null,
    },
    matches: [
      {
        index: 1,
        start_time: 0,
        end_time: 915,
        start_display: '00:00',
        end_display: '15:15',
        duration: 915,
        duration_display: '15m15s',
        type: 'fl_match',
        output_file: 'match_001.mp4',
      },
      {
        index: 2,
        start_time: 1000,
        end_time: 1800,
        start_display: '16:40',
        end_display: '30:00',
        duration: 800,
        duration_display: '13m20s',
        type: 'fl_match',
        output_file: 'match_002.mp4',
      },
    ],
    gaps: [],
  };
}

beforeEach(() => {
  invokeMock.mockReset();
  useMetadataStore.getState().clear();
});

describe('useMetadataStore.load', () => {
  it('populates metadata + filePath + clears dirty on success', async () => {
    invokeMock.mockResolvedValueOnce(validMetadata());
    await useMetadataStore.getState().load('C:/videos/out/metadata.json');
    const state = useMetadataStore.getState();
    expect(state.metadata).not.toBeNull();
    expect(state.filePath).toBe('C:/videos/out/metadata.json');
    expect(state.dirty).toBe(false);
    expect(state.loadError).toBeNull();
    expect(invokeMock).toHaveBeenCalledWith('load_metadata', {
      path: 'C:/videos/out/metadata.json',
    });
  });

  it('sets loadError when invoke rejects', async () => {
    invokeMock.mockRejectedValueOnce(new Error('nope'));
    await useMetadataStore.getState().load('C:/missing/metadata.json');
    const state = useMetadataStore.getState();
    expect(state.metadata).toBeNull();
    expect(state.loadError).toContain('nope');
  });

  it('sets loadError when schema validation fails', async () => {
    invokeMock.mockResolvedValueOnce({ bogus: true });
    await useMetadataStore.getState().load('x');
    expect(useMetadataStore.getState().metadata).toBeNull();
    expect(useMetadataStore.getState().loadError).toBeTruthy();
  });
});

describe('useMetadataStore.updateMatch', () => {
  it('applies name / type_override / edited and flips dirty', async () => {
    invokeMock.mockResolvedValueOnce(validMetadata());
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, {
      name: 'Round 1',
      type_override: 'unknown',
      edited: { start_time: 5, end_time: 910 },
    });
    const state = useMetadataStore.getState();
    expect(state.dirty).toBe(true);
    const first = state.metadata!.matches[0];
    expect(first.name).toBe('Round 1');
    expect(first.type_override).toBe('unknown');
    expect(first.edited).toEqual({ start_time: 5, end_time: 910 });
    // untouched match stays as-is
    expect(state.metadata!.matches[1].name).toBeUndefined();
  });

  it('no-ops when metadata is not loaded', () => {
    useMetadataStore.getState().updateMatch(1, { name: 'x' });
    expect(useMetadataStore.getState().dirty).toBe(false);
  });
});

describe('useMetadataStore.apply', () => {
  it('normalizes edited/type_override into canonical fields and clears dirty', async () => {
    invokeMock.mockResolvedValueOnce(validMetadata());
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, {
      edited: { start_time: 10, end_time: 900 },
      type_override: 'unknown',
      name: 'My match',
    });
    invokeMock.mockResolvedValueOnce(undefined);
    await useMetadataStore.getState().apply();
    const state = useMetadataStore.getState();
    expect(state.dirty).toBe(false);
    expect(state.applyError).toBeNull();
    const sentArgs = invokeMock.mock.calls[invokeMock.mock.calls.length - 1];
    expect(sentArgs[0]).toBe('apply_changes');
    const persistedMatches = (sentArgs[1] as { metadata: Metadata }).metadata
      .matches;
    expect(persistedMatches[0].start_time).toBe(10);
    expect(persistedMatches[0].end_time).toBe(900);
    expect(persistedMatches[0].duration).toBe(890);
    expect(persistedMatches[0].type).toBe('unknown');
    expect(persistedMatches[0]).not.toHaveProperty('name');
    expect(persistedMatches[0]).not.toHaveProperty('edited');
    expect(persistedMatches[0]).not.toHaveProperty('type_override');
  });

  it('does not change canonical type when type_override is skip', async () => {
    invokeMock.mockResolvedValueOnce(validMetadata());
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, { type_override: 'skip' });
    invokeMock.mockResolvedValueOnce(undefined);
    await useMetadataStore.getState().apply();
    const sentArgs = invokeMock.mock.calls[invokeMock.mock.calls.length - 1];
    const match = (sentArgs[1] as { metadata: Metadata }).metadata.matches[0];
    expect(match.type).toBe('fl_match');
  });

  it('sets applyError when invoke rejects', async () => {
    invokeMock.mockResolvedValueOnce(validMetadata());
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, { name: 'x' });
    invokeMock.mockRejectedValueOnce(new Error('write failed'));
    await useMetadataStore.getState().apply();
    const state = useMetadataStore.getState();
    expect(state.applying).toBe(false);
    expect(state.applyError).toContain('write failed');
    expect(state.dirty).toBe(true);
  });

  it('no-ops when metadata is not loaded', async () => {
    await useMetadataStore.getState().apply();
    expect(invokeMock).not.toHaveBeenCalled();
  });
});
