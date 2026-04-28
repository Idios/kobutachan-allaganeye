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

/**
 * Set up an invoke mock that dispatches per command name. Tests can override
 * specific commands via .mockImplementationOnce(...) or by configuring this
 * map further.
 */
interface MockConfig {
  load_metadata?: unknown;
  load_metadata_error?: Error;
  get_metadata_mtime?: number | null;
  get_metadata_mtime_error?: Error;
  apply_changes?: number;
  apply_changes_error?: Error;
  restore_from_original?: unknown;
  restore_from_original_error?: Error;
  check_backup_exists?: boolean;
  check_backup_exists_error?: Error;
  // #517
  save_draft?: unknown;
  save_draft_error?: Error;
  load_draft?: unknown;
  load_draft_error?: Error;
  clear_draft?: unknown;
  clear_draft_error?: Error;
}

function configureInvoke(cfg: MockConfig) {
  invokeMock.mockImplementation((cmd: string) => {
    switch (cmd) {
      case 'load_metadata':
        if (cfg.load_metadata_error) return Promise.reject(cfg.load_metadata_error);
        return Promise.resolve(cfg.load_metadata);
      case 'get_metadata_mtime':
        if (cfg.get_metadata_mtime_error)
          return Promise.reject(cfg.get_metadata_mtime_error);
        return Promise.resolve(cfg.get_metadata_mtime ?? null);
      case 'apply_changes':
        if (cfg.apply_changes_error) return Promise.reject(cfg.apply_changes_error);
        // Rust side returns post-write mtime as u64. Default to a sentinel
        // so apply() can still update loadedMtimeMs when tests don't care.
        return Promise.resolve(cfg.apply_changes ?? 2000);
      case 'restore_from_original':
        if (cfg.restore_from_original_error)
          return Promise.reject(cfg.restore_from_original_error);
        return Promise.resolve(cfg.restore_from_original);
      case 'check_backup_exists':
        if (cfg.check_backup_exists_error)
          return Promise.reject(cfg.check_backup_exists_error);
        return Promise.resolve(cfg.check_backup_exists ?? false);
      case 'save_draft':
        if (cfg.save_draft_error) return Promise.reject(cfg.save_draft_error);
        return Promise.resolve(cfg.save_draft);
      case 'load_draft':
        if (cfg.load_draft_error) return Promise.reject(cfg.load_draft_error);
        return Promise.resolve(cfg.load_draft ?? null);
      case 'clear_draft':
        if (cfg.clear_draft_error) return Promise.reject(cfg.clear_draft_error);
        return Promise.resolve(cfg.clear_draft);
      default:
        return Promise.reject(new Error(`unmocked invoke: ${cmd}`));
    }
  });
}

beforeEach(() => {
  invokeMock.mockReset();
  useMetadataStore.getState().clear();
});

describe('useMetadataStore.load', () => {
  it('populates metadata + filePath + clears dirty on success', async () => {
    configureInvoke({ load_metadata: validMetadata(), check_backup_exists: false });
    await useMetadataStore.getState().load('C:/videos/out/metadata.json');
    const state = useMetadataStore.getState();
    expect(state.metadata).not.toBeNull();
    expect(state.filePath).toBe('C:/videos/out/metadata.json');
    expect(state.dirty).toBe(false);
    expect(state.loadError).toBeNull();
    expect(state.hasBackup).toBe(false);
    expect(invokeMock).toHaveBeenCalledWith('load_metadata', {
      path: 'C:/videos/out/metadata.json',
    });
    expect(invokeMock).toHaveBeenCalledWith('check_backup_exists', {
      path: 'C:/videos/out/metadata.json',
    });
  });

  it('sets hasBackup=true when backup exists after load', async () => {
    configureInvoke({ load_metadata: validMetadata(), check_backup_exists: true });
    await useMetadataStore.getState().load('p');
    expect(useMetadataStore.getState().hasBackup).toBe(true);
  });

  it('sets loadError when invoke rejects', async () => {
    configureInvoke({ load_metadata_error: new Error('nope') });
    await useMetadataStore.getState().load('C:/missing/metadata.json');
    const state = useMetadataStore.getState();
    expect(state.metadata).toBeNull();
    expect(state.loadError).toContain('nope');
    expect(state.hasBackup).toBe(false);
  });

  it('sets loadError when schema validation fails', async () => {
    configureInvoke({ load_metadata: { bogus: true } });
    await useMetadataStore.getState().load('x');
    expect(useMetadataStore.getState().metadata).toBeNull();
    expect(useMetadataStore.getState().loadError).toBeTruthy();
  });
});

describe('useMetadataStore.updateMatch', () => {
  it('applies name / type_override / edited and flips dirty', async () => {
    configureInvoke({ load_metadata: validMetadata(), check_backup_exists: false });
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
    configureInvoke({
      load_metadata: validMetadata(),
      apply_changes: undefined,
      check_backup_exists: true,
    });
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, {
      edited: { start_time: 10, end_time: 900 },
      type_override: 'unknown',
      name: 'My match',
    });
    await useMetadataStore.getState().apply();
    const state = useMetadataStore.getState();
    expect(state.dirty).toBe(false);
    expect(state.applyError).toBeNull();
    expect(state.hasBackup).toBe(true);
    const applyCall = invokeMock.mock.calls.find((c) => c[0] === 'apply_changes');
    expect(applyCall).toBeDefined();
    const persistedMatches = (applyCall![1] as { metadata: Metadata }).metadata
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
    configureInvoke({
      load_metadata: validMetadata(),
      apply_changes: undefined,
      check_backup_exists: true,
    });
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, { type_override: 'skip' });
    await useMetadataStore.getState().apply();
    const applyCall = invokeMock.mock.calls.find((c) => c[0] === 'apply_changes');
    const match = (applyCall![1] as { metadata: Metadata }).metadata.matches[0];
    expect(match.type).toBe('fl_match');
  });

  it('sets applyError when invoke rejects', async () => {
    configureInvoke({
      load_metadata: validMetadata(),
      apply_changes_error: new Error('write failed'),
      check_backup_exists: false,
    });
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, { name: 'x' });
    await useMetadataStore.getState().apply();
    const state = useMetadataStore.getState();
    expect(state.applying).toBe(false);
    expect(state.applyError).toContain('write failed');
    expect(state.dirty).toBe(true);
  });

  it('no-ops when metadata is not loaded', async () => {
    configureInvoke({});
    await useMetadataStore.getState().apply();
    expect(invokeMock).not.toHaveBeenCalled();
  });
});

describe('useMetadataStore.clear', () => {
  it('resets the store to its initial empty state including #514/#516 fields', () => {
    useMetadataStore.setState({
      metadata: validMetadata(),
      filePath: '/tmp/x/metadata.json',
      dirty: true,
      loadError: 'prev error',
      applying: true,
      applyError: 'prev apply error',
      hasBackup: true,
      restoring: true,
      restoreError: 'prev restore error',
      loadedMtimeMs: 12345,
      conflictError: 'prev conflict',
    });

    useMetadataStore.getState().clear();

    const s = useMetadataStore.getState();
    expect(s.metadata).toBeNull();
    expect(s.filePath).toBeNull();
    expect(s.dirty).toBe(false);
    expect(s.loadError).toBeNull();
    expect(s.applying).toBe(false);
    expect(s.applyError).toBeNull();
    expect(s.hasBackup).toBe(false);
    expect(s.restoring).toBe(false);
    expect(s.restoreError).toBeNull();
    expect(s.loadedMtimeMs).toBeNull();
    expect(s.conflictError).toBeNull();
  });
});

describe('useMetadataStore.reset', () => {
  it('only clears the dirty flag and preserves metadata + filePath', () => {
    const meta = validMetadata();
    useMetadataStore.setState({
      metadata: meta,
      filePath: '/tmp/x/metadata.json',
      dirty: true,
    });

    useMetadataStore.getState().reset();

    const s = useMetadataStore.getState();
    expect(s.metadata).not.toBeNull();
    expect(s.metadata).toEqual(meta);
    expect(s.filePath).toBe('/tmp/x/metadata.json');
    expect(s.dirty).toBe(false);
  });
});

describe('useMetadataStore.restore (#516)', () => {
  it('invokes restore_from_original and reloads metadata', async () => {
    configureInvoke({
      load_metadata: validMetadata(),
      restore_from_original: undefined,
      check_backup_exists: true,
    });
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, { name: 'dirty' });
    expect(useMetadataStore.getState().dirty).toBe(true);

    await useMetadataStore.getState().restore();

    const state = useMetadataStore.getState();
    expect(state.restoring).toBe(false);
    expect(state.restoreError).toBeNull();
    expect(state.dirty).toBe(false);
    // metadata was reloaded fresh (no longer dirty name)
    expect(state.metadata?.matches[0].name).toBeUndefined();
    const restoreCall = invokeMock.mock.calls.find(
      (c) => c[0] === 'restore_from_original',
    );
    expect(restoreCall?.[1]).toEqual({ path: 'p' });
  });

  it('sets restoreError when the invoke rejects', async () => {
    configureInvoke({
      load_metadata: validMetadata(),
      restore_from_original_error: new Error('no backup'),
      check_backup_exists: false,
    });
    await useMetadataStore.getState().load('p');
    await useMetadataStore.getState().restore();
    const state = useMetadataStore.getState();
    expect(state.restoring).toBe(false);
    expect(state.restoreError).toContain('no backup');
  });

  it('no-ops when filePath is null (e.g. after loadSample)', async () => {
    configureInvoke({});
    useMetadataStore.getState().loadSample();
    await useMetadataStore.getState().restore();
    // only loadSample should have run — no invoke calls at all
    expect(invokeMock).not.toHaveBeenCalled();
  });
});

describe('useMetadataStore.refreshBackupStatus (#516)', () => {
  it('updates hasBackup based on check_backup_exists', async () => {
    configureInvoke({ check_backup_exists: true });
    useMetadataStore.setState({ filePath: '/tmp/m.json' });
    await useMetadataStore.getState().refreshBackupStatus();
    expect(useMetadataStore.getState().hasBackup).toBe(true);
  });

  it('falls back to hasBackup=false when invoke errors', async () => {
    configureInvoke({ check_backup_exists_error: new Error('fs error') });
    useMetadataStore.setState({ filePath: '/tmp/m.json', hasBackup: true });
    await useMetadataStore.getState().refreshBackupStatus();
    expect(useMetadataStore.getState().hasBackup).toBe(false);
  });

  it('no-ops when filePath is null', async () => {
    configureInvoke({});
    useMetadataStore.setState({ filePath: null, hasBackup: true });
    await useMetadataStore.getState().refreshBackupStatus();
    expect(useMetadataStore.getState().hasBackup).toBe(false);
    expect(invokeMock).not.toHaveBeenCalled();
  });
});

describe('useMetadataStore.loadSample', () => {
  it('populates metadata with sample data and null filePath', () => {
    useMetadataStore.getState().loadSample();
    const state = useMetadataStore.getState();
    expect(state.metadata).not.toBeNull();
    expect(state.metadata?.matches.length).toBeGreaterThan(0);
    expect(state.filePath).toBeNull();
    expect(state.dirty).toBe(false);
    expect(state.hasBackup).toBe(false);
    expect(state.loadedMtimeMs).toBeNull();
    expect(state.conflictError).toBeNull();
    expect(state.pendingDraft).toBeNull();
    expect(state.draftLoadError).toBeNull();
  });
});

// #514 — mtime-based exclusive control for metadata.json edits.

describe('useMetadataStore (#514 mtime + conflict)', () => {
  it('records loadedMtimeMs from get_metadata_mtime after a successful load', async () => {
    configureInvoke({
      load_metadata: validMetadata(),
      get_metadata_mtime: 1700,
      check_backup_exists: false,
    });
    await useMetadataStore.getState().load('p');
    const state = useMetadataStore.getState();
    expect(state.loadedMtimeMs).toBe(1700);
    expect(state.conflictError).toBeNull();
    // get_metadata_mtime is called alongside load_metadata.
    expect(invokeMock).toHaveBeenCalledWith('get_metadata_mtime', { path: 'p' });
  });

  it('passes the recorded mtime as expectedMtimeMs when apply is called', async () => {
    configureInvoke({
      load_metadata: validMetadata(),
      get_metadata_mtime: 1700,
      apply_changes: 2500,
      check_backup_exists: false,
    });
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, { name: 'x' });
    await useMetadataStore.getState().apply();

    const applyCall = invokeMock.mock.calls.find((c) => c[0] === 'apply_changes');
    expect(applyCall).toBeDefined();
    const args = applyCall![1] as { expectedMtimeMs: number | null };
    expect(args.expectedMtimeMs).toBe(1700);

    // Post-apply mtime rotates forward so the next apply uses the fresh value.
    expect(useMetadataStore.getState().loadedMtimeMs).toBe(2500);
    expect(useMetadataStore.getState().conflictError).toBeNull();
  });

  it('surfaces conflict errors in conflictError, not applyError', async () => {
    configureInvoke({
      load_metadata: validMetadata(),
      get_metadata_mtime: 1700,
      apply_changes_error: new Error(
        'conflict: external modification detected (expected mtime 1700, got 1800)',
      ),
      check_backup_exists: false,
    });
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, { name: 'x' });
    await useMetadataStore.getState().apply();

    const state = useMetadataStore.getState();
    expect(state.applying).toBe(false);
    expect(state.applyError).toBeNull();
    expect(state.conflictError).toContain('conflict:');
    // Store retains dirty edits so the user can choose to overwrite.
    expect(state.dirty).toBe(true);
  });

  it('routes non-conflict errors to applyError and leaves conflictError null', async () => {
    configureInvoke({
      load_metadata: validMetadata(),
      get_metadata_mtime: 1700,
      apply_changes_error: new Error('write failed: disk full'),
      check_backup_exists: false,
    });
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, { name: 'x' });
    await useMetadataStore.getState().apply();

    const state = useMetadataStore.getState();
    expect(state.applyError).toContain('disk full');
    expect(state.conflictError).toBeNull();
  });

  it('applyOverwrite re-runs apply with expectedMtimeMs=null', async () => {
    configureInvoke({
      load_metadata: validMetadata(),
      get_metadata_mtime: 1700,
      apply_changes: 2500,
      check_backup_exists: false,
    });
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, { name: 'x' });
    await useMetadataStore.getState().applyOverwrite();

    const applyCalls = invokeMock.mock.calls.filter((c) => c[0] === 'apply_changes');
    const lastApply = applyCalls[applyCalls.length - 1];
    const args = lastApply[1] as { expectedMtimeMs: number | null };
    expect(args.expectedMtimeMs).toBeNull();
    expect(useMetadataStore.getState().loadedMtimeMs).toBe(2500);
  });

  it('reloadAfterConflict re-loads metadata.json from disk', async () => {
    // First load with mtime 1700, then `conflictError` is set.
    configureInvoke({
      load_metadata: validMetadata(),
      get_metadata_mtime: 1700,
      apply_changes_error: new Error('conflict: stale'),
      check_backup_exists: false,
    });
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, { name: 'dirty' });
    await useMetadataStore.getState().apply();
    expect(useMetadataStore.getState().conflictError).toContain('conflict');

    // Reload now returns a fresh validMetadata (no `name` edit) + new mtime.
    configureInvoke({
      load_metadata: validMetadata(),
      get_metadata_mtime: 1900,
      check_backup_exists: false,
    });
    await useMetadataStore.getState().reloadAfterConflict();

    const state = useMetadataStore.getState();
    expect(state.conflictError).toBeNull();
    expect(state.loadedMtimeMs).toBe(1900);
    expect(state.metadata?.matches[0].name).toBeUndefined();
    expect(state.dirty).toBe(false);
  });

  it('reloadAfterConflict is a no-op when filePath is null (sample mode)', async () => {
    useMetadataStore.setState({ conflictError: 'stale' });
    await useMetadataStore.getState().reloadAfterConflict();
    expect(useMetadataStore.getState().conflictError).toBeNull();
  });

  it('dismissConflict clears the modal state without reloading or reapplying', () => {
    useMetadataStore.setState({ conflictError: 'conflict: x', dirty: true });
    useMetadataStore.getState().dismissConflict();
    const state = useMetadataStore.getState();
    expect(state.conflictError).toBeNull();
    expect(state.dirty).toBe(true); // edits are retained
  });

  it('load that fails clears loadedMtimeMs and conflictError', async () => {
    // Seed with prior state
    useMetadataStore.setState({ loadedMtimeMs: 999, conflictError: 'stale' });
    configureInvoke({ load_metadata_error: new Error('io error') });
    await useMetadataStore.getState().load('p');
    const state = useMetadataStore.getState();
    expect(state.loadedMtimeMs).toBeNull();
    expect(state.conflictError).toBeNull();
    expect(state.loadError).toContain('io error');
  });

  // Review 指摘 3: end-to-end recovery — conflict → reload → re-apply succeeds.
  // Current `reloadAfterConflict re-loads...` test stops at the reload; this one
  // proves the next apply completes with the rotated mtime (regression guard).
  it('conflict → reload → apply completes the full recovery flow', async () => {
    // Step 1: initial load + apply triggers conflict.
    configureInvoke({
      load_metadata: validMetadata(),
      get_metadata_mtime: 1700,
      apply_changes_error: new Error(
        'conflict: external modification detected (expected 1700, got 1800)',
      ),
      check_backup_exists: false,
    });
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, { name: 'pending-edit' });
    await useMetadataStore.getState().apply();
    expect(useMetadataStore.getState().conflictError).toContain('conflict');

    // Step 2: reload → fresh mtime, conflictError cleared.
    configureInvoke({
      load_metadata: validMetadata(),
      get_metadata_mtime: 1900,
      check_backup_exists: false,
    });
    await useMetadataStore.getState().reloadAfterConflict();
    expect(useMetadataStore.getState().loadedMtimeMs).toBe(1900);
    expect(useMetadataStore.getState().conflictError).toBeNull();

    // Step 3: re-edit and re-apply with the fresh mtime → success.
    useMetadataStore.getState().updateMatch(1, { name: 'retry' });
    configureInvoke({
      load_metadata: validMetadata(),
      get_metadata_mtime: 1900,
      apply_changes: 2100,
      check_backup_exists: false,
    });
    await useMetadataStore.getState().apply();

    const applyCalls = invokeMock.mock.calls.filter((c) => c[0] === 'apply_changes');
    const lastApply = applyCalls[applyCalls.length - 1];
    const args = lastApply[1] as { expectedMtimeMs: number | null };
    expect(args.expectedMtimeMs).toBe(1900);
    expect(useMetadataStore.getState().conflictError).toBeNull();
    expect(useMetadataStore.getState().loadedMtimeMs).toBe(2100);
    expect(useMetadataStore.getState().dirty).toBe(false);
  });

  // Review 指摘 4: second apply must use the rotated mtime from the first apply
  // (not the original load mtime). Current `passes the recorded mtime...` test
  // only checks post-apply `loadedMtimeMs`; this one proves the next apply call
  // sends the rotated value as expectedMtimeMs — guards against the "self-write
  // then conflict on own next apply" regression.
  it('second apply uses the rotated mtime from the first apply, not the original', async () => {
    configureInvoke({
      load_metadata: validMetadata(),
      get_metadata_mtime: 1700,
      apply_changes: 2500,
      check_backup_exists: false,
    });
    await useMetadataStore.getState().load('p');

    // First apply: expectedMtimeMs=1700 → post-write mtime rotates to 2500.
    useMetadataStore.getState().updateMatch(1, { name: 'first' });
    await useMetadataStore.getState().apply();
    expect(useMetadataStore.getState().loadedMtimeMs).toBe(2500);

    // Second apply: swap apply_changes to return 3300, then assert the
    // expectedMtimeMs sent is the rotated 2500 (not the original 1700).
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'apply_changes') return Promise.resolve(3300);
      if (cmd === 'check_backup_exists') return Promise.resolve(false);
      return Promise.reject(new Error(`unmocked: ${cmd}`));
    });
    useMetadataStore.getState().updateMatch(1, { name: 'second' });
    await useMetadataStore.getState().apply();

    const applyCalls = invokeMock.mock.calls.filter((c) => c[0] === 'apply_changes');
    const args = applyCalls[applyCalls.length - 1][1] as {
      expectedMtimeMs: number | null;
    };
    expect(args.expectedMtimeMs).toBe(2500);
    expect(useMetadataStore.getState().loadedMtimeMs).toBe(3300);
  });
});

// #517 — draft auto-save.

describe('useMetadataStore (#517 draft)', () => {
  it('saveDraft invokes save_draft with the current metadata', async () => {
    configureInvoke({
      load_metadata: validMetadata(),
      check_backup_exists: false,
    });
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, { name: 'x' });
    await useMetadataStore.getState().saveDraft();

    const saveCall = invokeMock.mock.calls.find((c) => c[0] === 'save_draft');
    expect(saveCall).toBeDefined();
    expect(saveCall![1]).toMatchObject({ path: 'p' });
    // The draft payload carries the in-memory metadata (including name).
    const draft = (saveCall![1] as { draft: Metadata }).draft;
    expect(draft.matches[0].name).toBe('x');
  });

  it('saveDraft is a no-op when no filePath is set (sample mode)', async () => {
    useMetadataStore.getState().loadSample();
    await useMetadataStore.getState().saveDraft();
    expect(invokeMock).not.toHaveBeenCalled();
  });

  it('loadDraft populates pendingDraft when backing source matches', async () => {
    const meta = validMetadata();
    const draft = { ...meta, matches: meta.matches.map((m) => ({ ...m, name: 'restored' })) };
    configureInvoke({
      load_metadata: meta,
      check_backup_exists: false,
      load_draft: draft,
    });
    await useMetadataStore.getState().load('p');
    await useMetadataStore.getState().loadDraft();
    const state = useMetadataStore.getState();
    expect(state.pendingDraft).not.toBeNull();
    expect(state.pendingDraft?.matches[0].name).toBe('restored');
    expect(state.draftLoadError).toBeNull();
  });

  it('loadDraft discards drafts whose source does not match the loaded file', async () => {
    const meta = validMetadata();
    // Draft points at a different source video.
    const draft = { ...meta, source: 'C:/videos/DIFFERENT.mkv' };
    configureInvoke({
      load_metadata: meta,
      check_backup_exists: false,
      load_draft: draft,
    });
    await useMetadataStore.getState().load('p');
    await useMetadataStore.getState().loadDraft();
    const state = useMetadataStore.getState();
    expect(state.pendingDraft).toBeNull();
    // Stale draft is cleaned up on disk.
    const clearCall = invokeMock.mock.calls.find((c) => c[0] === 'clear_draft');
    expect(clearCall).toBeDefined();
  });

  it('loadDraft sets draftLoadError on parse failure', async () => {
    configureInvoke({
      load_metadata: validMetadata(),
      check_backup_exists: false,
      load_draft: { bogus: true }, // won't pass zod
    });
    await useMetadataStore.getState().load('p');
    await useMetadataStore.getState().loadDraft();
    const state = useMetadataStore.getState();
    expect(state.pendingDraft).toBeNull();
    expect(state.draftLoadError).toBeTruthy();
  });

  it('loadDraft is a no-op when no draft exists on disk', async () => {
    configureInvoke({
      load_metadata: validMetadata(),
      check_backup_exists: false,
      load_draft: null,
    });
    await useMetadataStore.getState().load('p');
    await useMetadataStore.getState().loadDraft();
    const state = useMetadataStore.getState();
    expect(state.pendingDraft).toBeNull();
    expect(state.draftLoadError).toBeNull();
  });

  it('restoreDraft applies pendingDraft to metadata and marks dirty', async () => {
    const meta = validMetadata();
    const draft = {
      ...meta,
      matches: meta.matches.map((m) => ({ ...m, name: 'from-draft' })),
    };
    configureInvoke({
      load_metadata: meta,
      check_backup_exists: false,
      load_draft: draft,
    });
    await useMetadataStore.getState().load('p');
    await useMetadataStore.getState().loadDraft();
    useMetadataStore.getState().restoreDraft();
    const state = useMetadataStore.getState();
    expect(state.metadata?.matches[0].name).toBe('from-draft');
    expect(state.dirty).toBe(true);
    expect(state.pendingDraft).toBeNull();
  });

  it('discardDraft removes the on-disk draft and clears pendingDraft', async () => {
    const meta = validMetadata();
    configureInvoke({
      load_metadata: meta,
      check_backup_exists: false,
      load_draft: meta,
    });
    await useMetadataStore.getState().load('p');
    await useMetadataStore.getState().loadDraft();
    expect(useMetadataStore.getState().pendingDraft).not.toBeNull();

    await useMetadataStore.getState().discardDraft();
    expect(useMetadataStore.getState().pendingDraft).toBeNull();
    const clearCall = invokeMock.mock.calls.find((c) => c[0] === 'clear_draft');
    expect(clearCall).toBeDefined();
  });

  it('clearDraft is a no-op when filePath is null', async () => {
    useMetadataStore.setState({ filePath: null, pendingDraft: null });
    // No mock for clear_draft — should still succeed because we skip invoke.
    await useMetadataStore.getState().clearDraft();
    expect(invokeMock).not.toHaveBeenCalled();
  });

  it('apply success triggers clearDraft', async () => {
    configureInvoke({
      load_metadata: validMetadata(),
      check_backup_exists: false,
      apply_changes: undefined,
    });
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, { name: 'x' });
    await useMetadataStore.getState().apply();
    const clearCall = invokeMock.mock.calls.find((c) => c[0] === 'clear_draft');
    expect(clearCall).toBeDefined();
  });

  it('updateMatch schedules a debounced saveDraft', async () => {
    const { setDraftSaveDelay } = await import('./metadataStore');
    setDraftSaveDelay(10); // speed up the debounce for the test
    try {
      configureInvoke({
        load_metadata: validMetadata(),
        check_backup_exists: false,
      });
      await useMetadataStore.getState().load('p');
      useMetadataStore.getState().updateMatch(1, { name: 'x' });
      // Not invoked yet — debounce in flight.
      expect(
        invokeMock.mock.calls.find((c) => c[0] === 'save_draft'),
      ).toBeUndefined();
      await new Promise((r) => setTimeout(r, 25));
      expect(
        invokeMock.mock.calls.find((c) => c[0] === 'save_draft'),
      ).toBeDefined();
    } finally {
      setDraftSaveDelay(500);
    }
  });

  it('clear() resets all draft state', () => {
    useMetadataStore.setState({
      pendingDraft: validMetadata(),
      draftLoadError: 'prev',
      draftSaving: true,
      draftSaveError: 'prev-save-err',
    });
    useMetadataStore.getState().clear();
    const state = useMetadataStore.getState();
    expect(state.pendingDraft).toBeNull();
    expect(state.draftLoadError).toBeNull();
    expect(state.draftSaving).toBe(false);
    expect(state.draftSaveError).toBeNull();
  });

  // Review 指摘 A: path normalization. Platform is Windows-only (CLAUDE.md),
  // so separator / case differences must not be read as different sources.
  // Without normalization the draft is silently discarded even though it's
  // the same file (regression on 受け入れ条件 #3).
  it('loadDraft treats source paths differing only in separator as equal', async () => {
    const meta = validMetadata();
    // Draft captured with backslashes, live metadata with forward slashes.
    const draft = { ...meta, source: meta.source.replace(/\//g, '\\') };
    configureInvoke({
      load_metadata: meta,
      check_backup_exists: false,
      load_draft: draft,
    });
    await useMetadataStore.getState().load('p');
    await useMetadataStore.getState().loadDraft();
    expect(useMetadataStore.getState().pendingDraft).not.toBeNull();
  });

  it('loadDraft treats source paths differing only in case as equal (Windows)', async () => {
    const meta = validMetadata();
    const draft = { ...meta, source: meta.source.toUpperCase() };
    configureInvoke({
      load_metadata: meta,
      check_backup_exists: false,
      load_draft: draft,
    });
    await useMetadataStore.getState().load('p');
    await useMetadataStore.getState().loadDraft();
    expect(useMetadataStore.getState().pendingDraft).not.toBeNull();
  });

  // Review 指摘 B: schema_version unknown → draft parse fails → draftLoadError.
  // Proves 受け入れ条件 #3 is exercised through the schema_version axis.
  // Guards against a silent regression when v2 migration is introduced.
  it('loadDraft surfaces an error when the draft schema_version is unknown', async () => {
    const meta = validMetadata();
    const draft = { ...meta, schema_version: '99' };
    configureInvoke({
      load_metadata: meta,
      check_backup_exists: false,
      load_draft: draft,
    });
    await useMetadataStore.getState().load('p');
    await useMetadataStore.getState().loadDraft();
    const state = useMetadataStore.getState();
    expect(state.pendingDraft).toBeNull();
    expect(state.draftLoadError).toBeTruthy();
  });

  // Review 指摘 F1: saveDraft failures must surface via draftSaveError.
  // scheduleDraftSave calls saveDraft fire-and-forget, so without this guard
  // disk-full / permission-denied failures would be silent unhandled
  // rejections. A save that never landed breaks the "restore after crash"
  // contract — users need a way to detect it.
  it('saveDraft surfaces invoke errors via draftSaveError state', async () => {
    configureInvoke({
      load_metadata: validMetadata(),
      check_backup_exists: false,
      save_draft_error: new Error('disk full'),
    });
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, { name: 'x' });
    await useMetadataStore.getState().saveDraft();
    const state = useMetadataStore.getState();
    expect(state.draftSaveError).toContain('disk full');
    expect(state.draftSaving).toBe(false);
  });

  it('saveDraft clears previous draftSaveError on next success', async () => {
    configureInvoke({
      load_metadata: validMetadata(),
      check_backup_exists: false,
      save_draft_error: new Error('transient'),
    });
    await useMetadataStore.getState().load('p');
    await useMetadataStore.getState().saveDraft();
    expect(useMetadataStore.getState().draftSaveError).toBeTruthy();

    // Next save succeeds → error cleared.
    configureInvoke({
      load_metadata: validMetadata(),
      check_backup_exists: false,
    });
    await useMetadataStore.getState().saveDraft();
    expect(useMetadataStore.getState().draftSaveError).toBeNull();
  });
});

// Review 指摘 4: #514 × #517 相互作用。各 Modal / action の順序契約と state
// 共存の妥当性を unit レベルで pin し、将来 refactor で silent regression が
// 発生しないよう保護する。
describe('useMetadataStore (#514 × #517 interaction)', () => {
  // 4-1: load は mtime 記録が終わってから loadDraft を呼ぶ。順序が入れ替わると
  // draft 検査時に metadata が未確定 or mtime 未記録になる。
  it('load invokes get_metadata_mtime before loadDraft', async () => {
    configureInvoke({
      load_metadata: validMetadata(),
      check_backup_exists: false,
      load_draft: null,
    });
    await useMetadataStore.getState().load('p');
    const calls = invokeMock.mock.calls.map((c) => c[0] as string);
    const mtimeIdx = calls.indexOf('get_metadata_mtime');
    const loadDraftIdx = calls.indexOf('load_draft');
    expect(mtimeIdx).toBeGreaterThanOrEqual(0);
    expect(loadDraftIdx).toBeGreaterThan(mtimeIdx);
  });

  // 4-2: applyOverwrite は apply と共通 helper (runApply) 経由なので、上書き
  // 成功後も clear_draft が発火することを保証する。
  it('applyOverwrite success triggers clearDraft via shared runApply', async () => {
    configureInvoke({
      load_metadata: validMetadata(),
      check_backup_exists: false,
      apply_changes: 9999,
    });
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, { name: 'x' });
    await useMetadataStore.getState().applyOverwrite();
    const clearCall = invokeMock.mock.calls.find((c) => c[0] === 'clear_draft');
    expect(clearCall).toBeDefined();
  });

  // 4-3: reloadAfterConflict は load(filePath) を呼ぶため、source 一致な draft
  // があれば pendingDraft が再設定される (ユーザー編集救済の意図挙動)。
  it('reloadAfterConflict re-triggers loadDraft via load', async () => {
    const meta = validMetadata();
    const draft = {
      ...meta,
      matches: meta.matches.map((m) => ({ ...m, name: 'rescued' })),
    };
    configureInvoke({
      load_metadata: meta,
      check_backup_exists: false,
      load_draft: draft,
    });
    await useMetadataStore.getState().load('p');
    // conflict 発火を simulate
    useMetadataStore.setState({ conflictError: 'conflict: external' });
    await useMetadataStore.getState().reloadAfterConflict();
    expect(useMetadataStore.getState().pendingDraft?.matches[0].name).toBe(
      'rescued',
    );
    expect(useMetadataStore.getState().conflictError).toBeNull();
  });

  // 4-4: state 層では conflictError と pendingDraft が共存できる。排他制御は
  // UI 層 (DraftRestoreModal が conflictError 非 null 時に return null) が担う。
  // store に排他条件を入れると「conflict 解消後に draft modal が復活する」
  // 挙動を壊してしまう。
  it('conflictError and pendingDraft can coexist in state (resolved at render layer)', async () => {
    const meta = validMetadata();
    configureInvoke({
      load_metadata: meta,
      check_backup_exists: false,
      load_draft: meta,
    });
    await useMetadataStore.getState().load('p');
    expect(useMetadataStore.getState().pendingDraft).not.toBeNull();
    useMetadataStore.setState({ conflictError: 'conflict: external' });
    expect(useMetadataStore.getState().conflictError).toBeTruthy();
    expect(useMetadataStore.getState().pendingDraft).not.toBeNull();
  });
});

// #589 — discardEdits action used by preview screen confirm-OK paths.

describe('useMetadataStore.discardEdits (#589)', () => {
  it('real mode: clears the on-disk draft and re-loads metadata.json (dirty=false)', async () => {
    configureInvoke({
      load_metadata: validMetadata(),
      get_metadata_mtime: 1700,
      check_backup_exists: false,
    });
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, {
      name: 'edited-then-discarded',
      edited: { start_time: 50, end_time: 800 },
    });
    expect(useMetadataStore.getState().dirty).toBe(true);

    // After discard, the next load returns the original metadata, so the
    // edit should disappear and dirty must reset.
    invokeMock.mockClear();
    configureInvoke({
      load_metadata: validMetadata(),
      get_metadata_mtime: 1900,
      check_backup_exists: false,
    });
    await useMetadataStore.getState().discardEdits();

    const state = useMetadataStore.getState();
    expect(state.dirty).toBe(false);
    expect(state.metadata?.matches[0].name).toBeUndefined();
    expect(state.metadata?.matches[0].edited).toBeUndefined();
    expect(state.loadedMtimeMs).toBe(1900);
    // clearDraft is called BEFORE load so the trailing loadDraft() inside
    // load() does not re-surface the discarded edits.
    const calls = invokeMock.mock.calls.map((c) => c[0]);
    const clearIdx = calls.indexOf('clear_draft');
    const loadIdx = calls.indexOf('load_metadata');
    expect(clearIdx).toBeGreaterThanOrEqual(0);
    expect(loadIdx).toBeGreaterThanOrEqual(0);
    expect(clearIdx).toBeLessThan(loadIdx);
  });

  it('sample mode: resets to the in-memory sample fixture (dirty=false)', async () => {
    useMetadataStore.getState().loadSample();
    // Mutate the sample to look "dirty"
    useMetadataStore.getState().updateMatch(1, { name: 'sample-edit' });
    expect(useMetadataStore.getState().dirty).toBe(true);

    invokeMock.mockClear();
    await useMetadataStore.getState().discardEdits();

    const state = useMetadataStore.getState();
    expect(state.dirty).toBe(false);
    expect(state.filePath).toBeNull();
    // No disk I/O in sample mode.
    expect(invokeMock).not.toHaveBeenCalled();
    // Sample fixture is restored — the previous name edit must be gone.
    const target = state.metadata?.matches.find((m) => m.index === 1);
    expect(target?.name).not.toBe('sample-edit');
  });

  it('real mode: tolerates clear_draft rejection and proceeds to load', async () => {
    configureInvoke({
      load_metadata: validMetadata(),
      get_metadata_mtime: 1700,
      check_backup_exists: false,
    });
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, { name: 'edit' });
    expect(useMetadataStore.getState().dirty).toBe(true);

    // Make clear_draft fail (e.g. file does not exist) — discardEdits must
    // still complete the load and reset dirty.
    configureInvoke({
      load_metadata: validMetadata(),
      get_metadata_mtime: 2000,
      check_backup_exists: false,
      clear_draft_error: new Error('ENOENT: draft missing'),
    });
    await useMetadataStore.getState().discardEdits();

    expect(useMetadataStore.getState().dirty).toBe(false);
    expect(useMetadataStore.getState().loadedMtimeMs).toBe(2000);
  });
});
