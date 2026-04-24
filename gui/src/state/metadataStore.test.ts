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
