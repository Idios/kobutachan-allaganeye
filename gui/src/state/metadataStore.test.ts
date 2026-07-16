import { beforeEach, describe, expect, it, vi } from 'vitest';

const { invokeMock } = vi.hoisted(() => ({ invokeMock: vi.fn() }));

vi.mock('@tauri-apps/api/core', () => ({
  invoke: invokeMock,
}));

import { useMetadataStore } from './metadataStore';
import type { ErrorState } from '../lib/appError';
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
 * #694 round 1 fix: typed fixture builder for `ErrorState`. Existing tests
 * use object literals `{ message, hint, code }` whose shape is inferred from
 * the store's setState argument type. This helper makes the intent explicit
 * (`ErrorState` import is used here) and trims call-site boilerplate where
 * tests need many ErrorState fixtures.
 */
function mkErrorState(
  message: string,
  hint: string | null = null,
  code: string | null = null,
): ErrorState {
  return { message, hint, code };
}

/**
 * Set up an invoke mock that dispatches per command name. Tests can override
 * specific commands via .mockImplementationOnce(...) or by configuring this
 * map further.
 *
 * #663: `*_error` fields accept arbitrary reject values (Error instances or
 * AppError-shaped objects `{ code, message, hint? }`) so tests can simulate
 * the structured error path that Tauri uses post PR #665.
 */
interface MockConfig {
  load_metadata?: unknown;
  load_metadata_error?: unknown;
  get_metadata_mtime?: number | null;
  get_metadata_mtime_error?: unknown;
  apply_changes?: number;
  apply_changes_error?: unknown;
  restore_from_original?: unknown;
  restore_from_original_error?: unknown;
  check_backup_exists?: boolean;
  check_backup_exists_error?: unknown;
  // #517
  save_draft?: unknown;
  save_draft_error?: unknown;
  load_draft?: unknown;
  load_draft_error?: unknown;
  clear_draft?: unknown;
  clear_draft_error?: unknown;
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
    expect(state.loadErrorState).toBeNull();
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

  it('sets loadErrorState when invoke rejects', async () => {
    configureInvoke({ load_metadata_error: new Error('nope') });
    await useMetadataStore.getState().load('C:/missing/metadata.json');
    const state = useMetadataStore.getState();
    expect(state.metadata).toBeNull();
    expect(state.loadErrorState?.message).toContain('nope');
    expect(state.hasBackup).toBe(false);
  });

  it('sets loadErrorState when schema validation fails', async () => {
    configureInvoke({ load_metadata: { bogus: true } });
    await useMetadataStore.getState().load('x');
    expect(useMetadataStore.getState().metadata).toBeNull();
    expect(useMetadataStore.getState().loadErrorState).toBeTruthy();
  });

  // #834 -- mtime は内容 read より前に取得する (TOCTOU を silent overwrite では
  // なく conflict 検出側に倒す)。
  it('captures mtime before reading metadata content (#834)', async () => {
    const order: string[] = [];
    invokeMock.mockImplementation((cmd: string) => {
      order.push(cmd);
      if (cmd === 'get_metadata_mtime') return Promise.resolve(1700);
      if (cmd === 'load_metadata') return Promise.resolve(validMetadata());
      if (cmd === 'check_backup_exists') return Promise.resolve(false);
      if (cmd === 'load_draft') return Promise.resolve(null);
      return Promise.resolve(null);
    });
    await useMetadataStore.getState().load('p');
    const mIdx = order.indexOf('get_metadata_mtime');
    const lIdx = order.indexOf('load_metadata');
    expect(mIdx).toBeGreaterThanOrEqual(0);
    expect(lIdx).toBeGreaterThanOrEqual(0);
    expect(mIdx).toBeLessThan(lIdx);
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
    expect(state.applyErrorState).toBeNull();
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

  // #805 Phase 1 (Codex HIGH 1) -- normalizeForPersistence must passthrough the
  // post_match non-destructive flag. Without it, ANY [適用] strips post_match
  // from the written metadata.json -> on the next split/export the trailing
  // segment is treated as a normal match and gets an MP4, reversing the
  // exclusion invariant. The flag is truthy-only (normal matches stay
  // flag-free), and a post_match match never carries output_file.
  it('preserves post_match (truthy-only) and omits output_file for post_match matches on apply (#805)', async () => {
    const meta = validMetadata();
    // matches[1] becomes a post_match trailing segment: flag set, no output_file.
    meta.matches[1] = {
      index: 2,
      start_time: 1000,
      end_time: 1800,
      start_display: '16:40',
      end_display: '30:00',
      duration: 800,
      duration_display: '13m20s',
      type: 'unknown',
      post_match: true,
    };
    configureInvoke({
      load_metadata: meta,
      apply_changes: undefined,
      check_backup_exists: false,
    });
    await useMetadataStore.getState().load('p');
    // Apply an unrelated edit to the normal match so this exercises the full
    // normalize/apply path (not a no-op apply).
    useMetadataStore.getState().updateMatch(1, { name: 'Round 1' });
    await useMetadataStore.getState().apply();

    const applyCall = invokeMock.mock.calls.find((c) => c[0] === 'apply_changes');
    expect(applyCall).toBeDefined();
    const persisted = (applyCall![1] as { metadata: Metadata }).metadata.matches;

    // Normal match: GUI-only fields stripped on persist (name was set above via
    // updateMatch; normalizeForPersistence must remove it before apply_changes).
    expect(persisted[0].index).toBe(1);
    expect(persisted[0].output_file).toBe('match_001.mp4');
    expect(persisted[0]).not.toHaveProperty('post_match');
    expect(persisted[0]).not.toHaveProperty('name');
    expect(persisted[0]).not.toHaveProperty('edited');
    expect(persisted[0]).not.toHaveProperty('type_override');

    // post_match match: flag preserved as true, output_file omitted.
    expect(persisted[1].index).toBe(2);
    expect(persisted[1].post_match).toBe(true);
    expect(persisted[1]).not.toHaveProperty('output_file');
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

  it('sets applyErrorState when invoke rejects', async () => {
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
    expect(state.applyErrorState?.message).toContain('write failed');
    expect(state.dirty).toBe(true);
  });

  it('no-ops when metadata is not loaded', async () => {
    configureInvoke({});
    await useMetadataStore.getState().apply();
    expect(invokeMock).not.toHaveBeenCalled();
  });

  // #814 (AC1) -- end <= start must be blocked before apply_changes is invoked.
  it('blocks apply when a match has end_time < start_time (#814)', async () => {
    configureInvoke({
      load_metadata: validMetadata(),
      get_metadata_mtime: 1700,
      check_backup_exists: false,
    });
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, {
      edited: { start_time: 900, end_time: 100 },
    });
    await useMetadataStore.getState().apply();
    const state = useMetadataStore.getState();
    expect(
      invokeMock.mock.calls.find((c) => c[0] === 'apply_changes'),
    ).toBeUndefined();
    expect(state.applyErrorState?.code).toBe('validation.boundary_invalid');
    expect(state.applying).toBe(false);
    // edits retained so the user can fix them
    expect(state.dirty).toBe(true);
  });

  it('blocks apply when a match has end_time === start_time (zero duration, #814)', async () => {
    configureInvoke({
      load_metadata: validMetadata(),
      check_backup_exists: false,
    });
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, {
      edited: { start_time: 500, end_time: 500 },
    });
    await useMetadataStore.getState().apply();
    expect(
      invokeMock.mock.calls.find((c) => c[0] === 'apply_changes'),
    ).toBeUndefined();
    expect(useMetadataStore.getState().applyErrorState?.code).toBe(
      'validation.boundary_invalid',
    );
  });

  // #814 (AC4) -- *_display strings are regenerated from the edited numbers so
  // the persisted file never shows a timestamp that disagrees with the value.
  it('regenerates *_display from edited numeric boundaries on apply (#814)', async () => {
    configureInvoke({
      load_metadata: validMetadata(),
      apply_changes: 2000,
      check_backup_exists: false,
    });
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, {
      edited: { start_time: 65, end_time: 3725 },
    });
    await useMetadataStore.getState().apply();
    const applyCall = invokeMock.mock.calls.find((c) => c[0] === 'apply_changes');
    const m = (applyCall![1] as { metadata: Metadata }).metadata.matches[0];
    expect(m.start_time).toBe(65);
    expect(m.end_time).toBe(3725);
    expect(m.start_display).toBe('01:05'); // fmtTime(65)
    expect(m.end_display).toBe('1:02:05'); // fmtTime(3725)
    expect(m.duration).toBe(3660);
    expect(m.duration_display).toBe('1h01m'); // fmtMatchDuration(3660)
    // in-memory store metadata also reflects the regenerated strings
    expect(useMetadataStore.getState().metadata?.matches[0].start_display).toBe(
      '01:05',
    );
  });

  // #834 (P2-18) -- name/type_override は apply 後も in-memory に残る (UI 表示維持)。
  // 一方 metadata.json (apply_changes payload) には書き戻さない (契約維持)。
  it('retains name and type_override in-memory after apply but strips them from disk (#834)', async () => {
    configureInvoke({
      load_metadata: validMetadata(),
      apply_changes: 2000,
      check_backup_exists: false,
    });
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, {
      name: 'highlight reel',
      type_override: 'skip',
    });
    await useMetadataStore.getState().apply();

    const m = useMetadataStore
      .getState()
      .metadata!.matches.find((x) => x.index === 1)!;
    expect(m.name).toBe('highlight reel');
    expect(m.type_override).toBe('skip');

    const applyCall = invokeMock.mock.calls.find((c) => c[0] === 'apply_changes');
    const persisted = (applyCall![1] as { metadata: Metadata }).metadata
      .matches[0];
    expect(persisted.name).toBeUndefined();
    expect(persisted.type_override).toBeUndefined();
  });
});

describe('useMetadataStore.clear', () => {
  it('resets the store to its initial empty state including #514/#516 fields', () => {
    useMetadataStore.setState({
      metadata: validMetadata(),
      filePath: '/tmp/x/metadata.json',
      dirty: true,
      loadErrorState: mkErrorState('prev error'),
      applying: true,
      applyErrorState: mkErrorState('prev apply error'),
      hasBackup: true,
      restoring: true,
      restoreErrorState: mkErrorState('prev restore error'),
      loadedMtimeMs: 12345,
      conflictErrorState: mkErrorState('prev conflict'),
    });

    useMetadataStore.getState().clear();

    const s = useMetadataStore.getState();
    expect(s.metadata).toBeNull();
    expect(s.filePath).toBeNull();
    expect(s.dirty).toBe(false);
    expect(s.loadErrorState).toBeNull();
    expect(s.applying).toBe(false);
    expect(s.applyErrorState).toBeNull();
    expect(s.hasBackup).toBe(false);
    expect(s.restoring).toBe(false);
    expect(s.restoreErrorState).toBeNull();
    expect(s.loadedMtimeMs).toBeNull();
    expect(s.conflictErrorState).toBeNull();
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
    expect(state.restoreErrorState).toBeNull();
    expect(state.dirty).toBe(false);
    // metadata was reloaded fresh (no longer dirty name)
    expect(state.metadata?.matches[0].name).toBeUndefined();
    const restoreCall = invokeMock.mock.calls.find(
      (c) => c[0] === 'restore_from_original',
    );
    expect(restoreCall?.[1]).toEqual({ path: 'p' });
  });

  it('sets restoreErrorState when the invoke rejects', async () => {
    configureInvoke({
      load_metadata: validMetadata(),
      restore_from_original_error: new Error('no backup'),
      check_backup_exists: false,
    });
    await useMetadataStore.getState().load('p');
    await useMetadataStore.getState().restore();
    const state = useMetadataStore.getState();
    expect(state.restoring).toBe(false);
    expect(state.restoreErrorState?.message).toContain('no backup');
  });

  it('no-ops when filePath is null (e.g. after loadSample)', async () => {
    configureInvoke({});
    useMetadataStore.getState().loadSample();
    await useMetadataStore.getState().restore();
    // only loadSample should have run — no invoke calls at all
    expect(invokeMock).not.toHaveBeenCalled();
  });

  // #814 (AC3) -- a restore whose reload fails must not report success.
  it('surfaces a reload failure as restoreErrorState (#814)', async () => {
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'restore_from_original') return Promise.resolve(undefined);
      if (cmd === 'load_metadata') {
        return Promise.reject({
          code: 'parse.json_invalid',
          message: 'restored metadata is corrupt',
          hint: 'restore from a different backup',
        });
      }
      if (cmd === 'get_metadata_mtime') return Promise.resolve(null);
      if (cmd === 'check_backup_exists') return Promise.resolve(false);
      return Promise.resolve(null);
    });
    useMetadataStore.setState({ filePath: 'p' });
    await useMetadataStore.getState().restore();
    const state = useMetadataStore.getState();
    expect(state.restoring).toBe(false);
    expect(state.restoreErrorState?.message).toContain('corrupt');
    expect(state.restoreErrorState?.code).toBe('parse.json_invalid');
    expect(state.metadata).toBeNull();
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
    expect(state.conflictErrorState).toBeNull();
    expect(state.pendingDraft).toBeNull();
    expect(state.draftLoadErrorState).toBeNull();
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
    expect(state.conflictErrorState).toBeNull();
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
    expect(useMetadataStore.getState().conflictErrorState).toBeNull();
  });

  it('surfaces conflict errors in conflictErrorState, not applyErrorState', async () => {
    // #663: PR #665 で全 23 commands が AppError 化済のため、conflict は
    // structured AppError ({ code: 'state.mtime_conflict', ... }) として届く。
    configureInvoke({
      load_metadata: validMetadata(),
      get_metadata_mtime: 1700,
      apply_changes_error: {
        code: 'state.mtime_conflict',
        message:
          'external modification detected (expected mtime 1700, got 1800)',
      },
      check_backup_exists: false,
    });
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, { name: 'x' });
    await useMetadataStore.getState().apply();

    const state = useMetadataStore.getState();
    expect(state.applying).toBe(false);
    expect(state.applyErrorState).toBeNull();
    expect(state.conflictErrorState?.message).toContain('external modification');
    // Store retains dirty edits so the user can choose to overwrite.
    expect(state.dirty).toBe(true);
  });

  it('routes non-conflict errors to applyErrorState and leaves conflictErrorState null', async () => {
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
    expect(state.applyErrorState?.message).toContain('disk full');
    expect(state.conflictErrorState).toBeNull();
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
    // First load with mtime 1700, then `conflictErrorState` is set.
    // #663: structured AppError ({ code: 'state.mtime_conflict', ... }) で reject
    configureInvoke({
      load_metadata: validMetadata(),
      get_metadata_mtime: 1700,
      apply_changes_error: { code: 'state.mtime_conflict', message: 'stale' },
      check_backup_exists: false,
    });
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, { name: 'dirty' });
    await useMetadataStore.getState().apply();
    expect(useMetadataStore.getState().conflictErrorState?.message).toContain('stale');

    // Reload now returns a fresh validMetadata (no `name` edit) + new mtime.
    configureInvoke({
      load_metadata: validMetadata(),
      get_metadata_mtime: 1900,
      check_backup_exists: false,
    });
    await useMetadataStore.getState().reloadAfterConflict();

    const state = useMetadataStore.getState();
    expect(state.conflictErrorState).toBeNull();
    expect(state.loadedMtimeMs).toBe(1900);
    expect(state.metadata?.matches[0].name).toBeUndefined();
    expect(state.dirty).toBe(false);
  });

  it('reloadAfterConflict is a no-op when filePath is null (sample mode)', async () => {
    // #695: conflictErrorState pair atomicity (Round 1 fix c929aae).
    // sample mode (filePath === null) では load() を呼べず、conflictErrorState を直接 null reset する。
    useMetadataStore.setState({
      conflictErrorState: { message: 'stale', hint: 'stale hint', code: null },
    });
    await useMetadataStore.getState().reloadAfterConflict();
    const state = useMetadataStore.getState();
    expect(state.conflictErrorState).toBeNull();
  });

  it('dismissConflict clears the modal state without reloading or reapplying', () => {
    useMetadataStore.setState({
      conflictErrorState: { message: 'x', hint: null, code: null },
      dirty: true,
    });
    useMetadataStore.getState().dismissConflict();
    const state = useMetadataStore.getState();
    expect(state.conflictErrorState).toBeNull();
    expect(state.dirty).toBe(true); // edits are retained
  });

  it('load that fails clears loadedMtimeMs and conflictErrorState', async () => {
    // Seed with prior state
    // #695: conflictErrorState pair atomicity (Round 1 fix c929aae).
    // load() 失敗時は file-state リセットの一部として conflictErrorState を null reset。
    useMetadataStore.setState({
      loadedMtimeMs: 999,
      conflictErrorState: { message: 'stale', hint: 'stale hint', code: null },
    });
    configureInvoke({ load_metadata_error: new Error('io error') });
    await useMetadataStore.getState().load('p');
    const state = useMetadataStore.getState();
    expect(state.loadedMtimeMs).toBeNull();
    expect(state.conflictErrorState).toBeNull();
    expect(state.loadErrorState?.message).toContain('io error');
  });

  // Review 指摘 3: end-to-end recovery — conflict → reload → re-apply succeeds.
  // Current `reloadAfterConflict re-loads...` test stops at the reload; this one
  // proves the next apply completes with the rotated mtime (regression guard).
  it('conflict → reload → apply completes the full recovery flow', async () => {
    // Step 1: initial load + apply triggers conflict.
    // #663: structured AppError ({ code: 'state.mtime_conflict', ... }) で reject
    configureInvoke({
      load_metadata: validMetadata(),
      get_metadata_mtime: 1700,
      apply_changes_error: {
        code: 'state.mtime_conflict',
        message: 'external modification detected (expected 1700, got 1800)',
      },
      check_backup_exists: false,
    });
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, { name: 'pending-edit' });
    await useMetadataStore.getState().apply();
    expect(useMetadataStore.getState().conflictErrorState?.message).toContain('external');

    // Step 2: reload → fresh mtime, conflictErrorState cleared.
    configureInvoke({
      load_metadata: validMetadata(),
      get_metadata_mtime: 1900,
      check_backup_exists: false,
    });
    await useMetadataStore.getState().reloadAfterConflict();
    expect(useMetadataStore.getState().loadedMtimeMs).toBe(1900);
    expect(useMetadataStore.getState().conflictErrorState).toBeNull();

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
    expect(useMetadataStore.getState().conflictErrorState).toBeNull();
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

  it('legacy raw-string Error("conflict: ...") routes to applyErrorState, not conflictErrorState (#663)', async () => {
    configureInvoke({
      load_metadata: validMetadata(),
      get_metadata_mtime: 1700,
      apply_changes_error: new Error('conflict: legacy raw string'),
      check_backup_exists: false,
    });
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, { name: 'x' });
    await useMetadataStore.getState().apply();
    const s = useMetadataStore.getState();
    expect(s.conflictErrorState).toBeNull();
    expect(s.applyErrorState?.message).toContain('conflict:');
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
    expect(state.draftLoadErrorState).toBeNull();
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

  it('loadDraft sets draftLoadErrorState on parse failure', async () => {
    configureInvoke({
      load_metadata: validMetadata(),
      check_backup_exists: false,
      load_draft: { bogus: true }, // won't pass zod
    });
    await useMetadataStore.getState().load('p');
    await useMetadataStore.getState().loadDraft();
    const state = useMetadataStore.getState();
    expect(state.pendingDraft).toBeNull();
    expect(state.draftLoadErrorState).toBeTruthy();
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
    expect(state.draftLoadErrorState).toBeNull();
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
      draftLoadErrorState: { message: 'prev', hint: null, code: null },
      draftSaving: true,
      draftSaveErrorState: { message: 'prev-save-err', hint: null, code: null },
    });
    useMetadataStore.getState().clear();
    const state = useMetadataStore.getState();
    expect(state.pendingDraft).toBeNull();
    expect(state.draftLoadErrorState).toBeNull();
    expect(state.draftSaving).toBe(false);
    expect(state.draftSaveErrorState).toBeNull();
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

  // Review 指摘 B: schema_version unknown → draft parse fails → draftLoadErrorState.
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
    expect(state.draftLoadErrorState).toBeTruthy();
  });

  // Review 指摘 F1: saveDraft failures must surface via draftSaveErrorState.
  // scheduleDraftSave calls saveDraft fire-and-forget, so without this guard
  // disk-full / permission-denied failures would be silent unhandled
  // rejections. A save that never landed breaks the "restore after crash"
  // contract — users need a way to detect it.
  it('saveDraft surfaces invoke errors via draftSaveErrorState state', async () => {
    configureInvoke({
      load_metadata: validMetadata(),
      check_backup_exists: false,
      save_draft_error: new Error('disk full'),
    });
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, { name: 'x' });
    await useMetadataStore.getState().saveDraft();
    const state = useMetadataStore.getState();
    expect(state.draftSaveErrorState?.message).toContain('disk full');
    expect(state.draftSaving).toBe(false);
  });

  it('saveDraft clears previous draftSaveErrorState on next success', async () => {
    configureInvoke({
      load_metadata: validMetadata(),
      check_backup_exists: false,
      save_draft_error: new Error('transient'),
    });
    await useMetadataStore.getState().load('p');
    await useMetadataStore.getState().saveDraft();
    expect(useMetadataStore.getState().draftSaveErrorState).toBeTruthy();

    // Next save succeeds → error cleared.
    configureInvoke({
      load_metadata: validMetadata(),
      check_backup_exists: false,
    });
    await useMetadataStore.getState().saveDraft();
    expect(useMetadataStore.getState().draftSaveErrorState).toBeNull();
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
    useMetadataStore.setState({
      conflictErrorState: { message: 'external', hint: null, code: null },
    });
    await useMetadataStore.getState().reloadAfterConflict();
    expect(useMetadataStore.getState().pendingDraft?.matches[0].name).toBe(
      'rescued',
    );
    expect(useMetadataStore.getState().conflictErrorState).toBeNull();
  });

  // 4-4: state 層では conflictErrorState と pendingDraft が共存できる。排他制御は
  // UI 層 (DraftRestoreModal が conflictErrorState 非 null 時に return null) が担う。
  // store に排他条件を入れると「conflict 解消後に draft modal が復活する」
  // 挙動を壊してしまう。
  it('conflictErrorState and pendingDraft can coexist in state (resolved at render layer)', async () => {
    const meta = validMetadata();
    configureInvoke({
      load_metadata: meta,
      check_backup_exists: false,
      load_draft: meta,
    });
    await useMetadataStore.getState().load('p');
    expect(useMetadataStore.getState().pendingDraft).not.toBeNull();
    useMetadataStore.setState({
      conflictErrorState: { message: 'external', hint: null, code: null },
    });
    expect(useMetadataStore.getState().conflictErrorState).toBeTruthy();
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

// #663 — AppError hint pair. Each error-state field gains a sibling `*Hint`
// that carries the AppError.hint when the underlying invoke rejected with a
// structured AppError object. legacy raw Error rejection keeps the hint null.
// #694 — *ErrorState form: *Error + *ErrorHint collapsed into single *ErrorState object.
describe('AppError hint pair (#663 / #694 *ErrorState)', () => {
  beforeEach(() => {
    useMetadataStore.getState().clear();
  });

  it('apply path: applyErrorState carries message + hint when AppError carries hint', async () => {
    invokeMock.mockImplementation(async (cmd) => {
      if (cmd === 'apply_changes') {
        // Tauri rejects with the AppError-shaped object directly
        throw {
          code: 'io.write_failed',
          message: 'disk full',
          hint: 'check free disk space',
        };
      }
      throw new Error(`unexpected invoke: ${cmd}`);
    });
    useMetadataStore.setState({
      metadata: { source: 'x', matches: [] } as never,
      filePath: '/tmp/m.json',
      loadedMtimeMs: 1000,
    });
    await useMetadataStore.getState().apply();
    const s = useMetadataStore.getState();
    expect(s.applyErrorState).toEqual({
      message: 'disk full',
      hint: 'check free disk space',
      code: 'io.write_failed',
    });
  });

  it('load path: loadErrorState carries message + hint when AppError carries hint', async () => {
    invokeMock.mockImplementation(async () => {
      throw {
        code: 'io.file_not_found',
        message: 'no such file',
        hint: 'check path',
      };
    });
    await useMetadataStore.getState().load('/tmp/missing.json');
    const s = useMetadataStore.getState();
    expect(s.loadErrorState).toEqual({
      message: 'no such file',
      hint: 'check path',
      code: 'io.file_not_found',
    });
  });

  it('restore path: restoreErrorState carries message + hint', async () => {
    invokeMock.mockImplementation(async (cmd) => {
      if (cmd === 'restore_from_original') {
        throw {
          code: 'io.backup_failed',
          message: 'no backup',
          hint: 'create backup first',
        };
      }
      throw new Error(`unexpected invoke: ${cmd}`);
    });
    useMetadataStore.setState({ filePath: '/tmp/m.json' });
    await useMetadataStore.getState().restore();
    const s = useMetadataStore.getState();
    expect(s.restoreErrorState).toEqual({
      message: 'no backup',
      hint: 'create backup first',
      code: 'io.backup_failed',
    });
  });

  it('saveDraft path: draftSaveErrorState carries message + hint', async () => {
    invokeMock.mockImplementation(async (cmd) => {
      if (cmd === 'save_draft') {
        throw {
          code: 'io.write_failed',
          message: 'disk full',
          hint: 'free space',
        };
      }
      throw new Error(`unexpected invoke: ${cmd}`);
    });
    useMetadataStore.setState({
      filePath: '/tmp/m.json',
      metadata: { source: 'x', matches: [] } as never,
    });
    await useMetadataStore.getState().saveDraft();
    const s = useMetadataStore.getState();
    expect(s.draftSaveErrorState).toEqual({
      message: 'disk full',
      hint: 'free space',
      code: 'io.write_failed',
    });
  });

  it('loadDraft path: draftLoadErrorState carries message + hint', async () => {
    invokeMock.mockImplementation(async (cmd) => {
      if (cmd === 'load_draft') {
        throw {
          code: 'parse.json_invalid',
          message: 'bad json',
          hint: 'corrupt draft',
        };
      }
      throw new Error(`unexpected invoke: ${cmd}`);
    });
    useMetadataStore.setState({
      filePath: '/tmp/m.json',
      metadata: { source: 'x', matches: [] } as never,
    });
    await useMetadataStore.getState().loadDraft();
    const s = useMetadataStore.getState();
    expect(s.draftLoadErrorState).toEqual({
      message: 'bad json',
      hint: 'corrupt draft',
      code: 'parse.json_invalid',
    });
  });

  it('legacy raw-Error reject keeps hint null and code null', async () => {
    invokeMock.mockImplementation(async () => {
      throw new Error('plain error string');
    });
    await useMetadataStore.getState().load('/tmp/x.json');
    const s = useMetadataStore.getState();
    expect(s.loadErrorState).toEqual({
      message: 'plain error string',
      hint: null,
      code: null,
    });
  });
});

describe('#691: catch path lifecycle pinning', () => {
  beforeEach(() => {
    // Reset to clean state
    useMetadataStore.setState({
      metadata: null,
      filePath: null,
      dirty: false,
      loadErrorState: null,
      applying: false,
      applyErrorState: null,
      hasBackup: false,
      restoring: false,
      restoreErrorState: null,
      loadedMtimeMs: null,
      conflictErrorState: null,
      pendingDraft: null,
      draftLoadErrorState: null,
      draftSaving: false,
      draftSaveErrorState: null,
    });
  });

  it('案 X: load() catch sets loadErrorState only, leaves apply/restore/draft *ErrorState untouched', async () => {
    // pre-condition: 全 path の *ErrorState が non-null
    useMetadataStore.setState({
      applyErrorState: { message: 'old apply error', hint: 'old apply hint', code: null },
      restoreErrorState: { message: 'old restore error', hint: 'old restore hint', code: null },
      draftLoadErrorState: { message: 'old draft load error', hint: 'old draft load hint', code: null },
      draftSaveErrorState: { message: 'old draft save error', hint: 'old draft save hint', code: null },
    });

    invokeMock.mockImplementation(async () => {
      throw {
        code: 'io.file_not_found',
        message: 'file not found',
        hint: 'check path',
      };
    });

    await useMetadataStore.getState().load('/non-existent');

    const state = useMetadataStore.getState();
    // self set
    expect(state.loadErrorState).toEqual({
      message: 'file not found',
      hint: 'check path',
      code: 'io.file_not_found',
    });
    // 案 X: other paths' *ErrorState untouched
    expect(state.applyErrorState).toEqual({ message: 'old apply error', hint: 'old apply hint', code: null });
    expect(state.restoreErrorState).toEqual({ message: 'old restore error', hint: 'old restore hint', code: null });
    expect(state.draftLoadErrorState).toEqual({ message: 'old draft load error', hint: 'old draft load hint', code: null });
    expect(state.draftSaveErrorState).toEqual({ message: 'old draft save error', hint: 'old draft save hint', code: null });
  });

  it('runApply() non-conflict catch sets applyErrorState only', async () => {
    useMetadataStore.setState({
      metadata: { source: '/test.mp4', matches: [] } as never,
      filePath: '/test.mp4',
      loadedMtimeMs: 1000,
      loadErrorState: { message: 'old load error', hint: 'old load hint', code: null },
      restoreErrorState: { message: 'old restore error', hint: 'old restore hint', code: null },
    });

    invokeMock.mockImplementation(async (cmd) => {
      if (cmd === 'apply_changes') {
        throw {
          code: 'io.permission_denied',
          message: 'denied',
          hint: 'check write permission',
        };
      }
      throw new Error(`unexpected invoke: ${cmd}`);
    });

    await useMetadataStore.getState().apply();

    const state = useMetadataStore.getState();
    expect(state.applyErrorState).toEqual({
      message: 'denied',
      hint: 'check write permission',
      code: 'io.permission_denied',
    });
    expect(state.loadErrorState).toEqual({ message: 'old load error', hint: 'old load hint', code: null });
    expect(state.restoreErrorState).toEqual({ message: 'old restore error', hint: 'old restore hint', code: null });
  });

  it('runApply() conflict catch sets conflictErrorState only, leaves *ErrorState untouched', async () => {
    useMetadataStore.setState({
      metadata: { source: '/test.mp4', matches: [] } as never,
      filePath: '/test.mp4',
      loadedMtimeMs: 1000,
      applyErrorState: { message: 'old apply error', hint: 'old apply hint', code: null },
      loadErrorState: { message: 'old load error', hint: 'old load hint', code: null },
    });

    invokeMock.mockImplementation(async (cmd) => {
      if (cmd === 'apply_changes') {
        throw {
          code: 'state.mtime_conflict',
          message: 'mtime conflict',
          hint: 'reload or overwrite',
        };
      }
      throw new Error(`unexpected invoke: ${cmd}`);
    });

    await useMetadataStore.getState().apply();

    const state = useMetadataStore.getState();
    expect(state.conflictErrorState).toEqual({
      message: 'mtime conflict',
      hint: 'reload or overwrite',
      code: 'state.mtime_conflict',
    });
    // runApply initial set clears applyErrorState/conflictErrorState before invoke
    // conflict catch then only sets { applying: false, conflictErrorState: errorState }
    // so applyErrorState is null from the initial set (not 'old' anymore)
    expect(state.loadErrorState).toEqual({ message: 'old load error', hint: 'old load hint', code: null });
  });

  it('restore() catch sets restoreErrorState only', async () => {
    useMetadataStore.setState({
      filePath: '/test.mp4',
      loadErrorState: { message: 'old load error', hint: 'old load hint', code: null },
      applyErrorState: { message: 'old apply error', hint: 'old apply hint', code: null },
    });

    invokeMock.mockImplementation(async (cmd) => {
      if (cmd === 'restore_from_original') {
        throw {
          code: 'io.backup_failed',
          message: 'backup failed',
          hint: 'check disk',
        };
      }
      throw new Error(`unexpected invoke: ${cmd}`);
    });

    await useMetadataStore.getState().restore();

    const state = useMetadataStore.getState();
    expect(state.restoreErrorState).toEqual({
      message: 'backup failed',
      hint: 'check disk',
      code: 'io.backup_failed',
    });
    expect(state.loadErrorState).toEqual({ message: 'old load error', hint: 'old load hint', code: null });
    expect(state.applyErrorState).toEqual({ message: 'old apply error', hint: 'old apply hint', code: null });
  });

  it('saveDraft() catch sets draftSaveErrorState only', async () => {
    useMetadataStore.setState({
      metadata: { source: '/test.mp4', matches: [] } as never,
      filePath: '/test.mp4',
      loadErrorState: { message: 'old load error', hint: 'old load hint', code: null },
    });

    invokeMock.mockImplementation(async (cmd) => {
      if (cmd === 'save_draft') {
        throw {
          code: 'io.write_failed',
          message: 'write failed',
          hint: 'check space',
        };
      }
      throw new Error(`unexpected invoke: ${cmd}`);
    });

    await useMetadataStore.getState().saveDraft();

    const state = useMetadataStore.getState();
    expect(state.draftSaveErrorState).toEqual({
      message: 'write failed',
      hint: 'check space',
      code: 'io.write_failed',
    });
    expect(state.loadErrorState).toEqual({ message: 'old load error', hint: 'old load hint', code: null });
  });

  it('loadDraft() catch sets draftLoadErrorState only', async () => {
    useMetadataStore.setState({
      metadata: { source: '/test.mp4', matches: [] } as never,
      filePath: '/test.mp4',
      applyErrorState: { message: 'old apply error', hint: 'old apply hint', code: null },
    });

    invokeMock.mockImplementation(async (cmd) => {
      if (cmd === 'load_draft') {
        throw {
          code: 'parse.json_invalid',
          message: 'json invalid',
          hint: 'restore from backup',
        };
      }
      throw new Error(`unexpected invoke: ${cmd}`);
    });

    await useMetadataStore.getState().loadDraft();

    const state = useMetadataStore.getState();
    expect(state.draftLoadErrorState).toEqual({
      message: 'json invalid',
      hint: 'restore from backup',
      code: 'parse.json_invalid',
    });
    expect(state.applyErrorState).toEqual({ message: 'old apply error', hint: 'old apply hint', code: null });
  });

  it('clear() resets all *ErrorState to null', () => {
    useMetadataStore.setState({
      loadErrorState: { message: 'a', hint: 'A', code: null },
      applyErrorState: { message: 'b', hint: 'B', code: null },
      restoreErrorState: { message: 'c', hint: 'C', code: null },
      draftLoadErrorState: { message: 'd', hint: 'D', code: null },
      draftSaveErrorState: { message: 'e', hint: 'E', code: null },
    });

    useMetadataStore.getState().clear();

    const state = useMetadataStore.getState();
    expect(state.loadErrorState).toBeNull();
    expect(state.applyErrorState).toBeNull();
    expect(state.restoreErrorState).toBeNull();
    expect(state.draftLoadErrorState).toBeNull();
    expect(state.draftSaveErrorState).toBeNull();
  });

  it('loadSample() resets all *ErrorState to null', () => {
    useMetadataStore.setState({
      loadErrorState: { message: 'a', hint: 'A', code: null },
      applyErrorState: { message: 'b', hint: 'B', code: null },
      restoreErrorState: { message: 'c', hint: 'C', code: null },
      draftLoadErrorState: { message: 'd', hint: 'D', code: null },
      draftSaveErrorState: { message: 'e', hint: 'E', code: null },
    });

    useMetadataStore.getState().loadSample();

    const state = useMetadataStore.getState();
    expect(state.loadErrorState).toBeNull();
    expect(state.applyErrorState).toBeNull();
    expect(state.restoreErrorState).toBeNull();
    expect(state.draftLoadErrorState).toBeNull();
    expect(state.draftSaveErrorState).toBeNull();
  });
});

describe('normalizeForPersistence capture_regions round-trip (#810)', () => {
  it('normalizeForPersistence preserves capture_regions (#810)', async () => {
    // top-level spread で保持される契約を pin する (欠落で GUI 適用時に領域が消えると
    // #481 minimap 等の consumer が cached 情報を失う)
    const meta = validMetadata();
    const captureRegions = {
      coarse: { x: 0, y: 0, w: 1, h: 1, confidence: 1, source: 'fallback' },
      segments: [],
      fallback_reason: null,
    };
    // Metadata now has capture_regions?: CaptureRegions (from generated types)
    const metaWithRegions = { ...meta, capture_regions: captureRegions };
    configureInvoke({
      load_metadata: metaWithRegions,
      apply_changes: 2000,
      check_backup_exists: false,
    });
    await useMetadataStore.getState().load('p');
    // Need a dirty edit to trigger apply
    useMetadataStore.getState().updateMatch(1, { name: 'x' });
    await useMetadataStore.getState().apply();
    const applyCall = invokeMock.mock.calls.find((c) => c[0] === 'apply_changes');
    expect(applyCall).toBeDefined();
    const persisted = (applyCall![1] as { metadata: Metadata }).metadata;
    expect(persisted.capture_regions).toEqual(captureRegions);
  });
});

describe('useMetadataStore.reloadFromDisk (#893)', () => {
  it('reloadFromDisk refreshes metadata + mtime and clears conflict', async () => {
    const fresh = { ...validMetadata(), minimap_regions: [{ match_index: 1, region: { x: 0.01, y: 0.02, w: 0.15, h: 0.2, confidence: 1, source: 'manual' } }] };
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'get_metadata_mtime') return Promise.resolve(999);
      if (cmd === 'load_metadata') return Promise.resolve(fresh);
      return Promise.resolve(null);
    });
    useMetadataStore.setState({ filePath: 'C:/x/metadata.json', loadedMtimeMs: 1, conflictErrorState: { code: 'x', message: 'y', hint: null } });

    await useMetadataStore.getState().reloadFromDisk();

    const s = useMetadataStore.getState();
    expect(s.metadata?.minimap_regions?.[0].match_index).toBe(1);
    expect(s.loadedMtimeMs).toBe(999);
    expect(s.conflictErrorState).toBeNull();
  });

  it('reloadFromDisk is a no-op without filePath (sample mode)', async () => {
    useMetadataStore.setState({ filePath: null });
    await expect(useMetadataStore.getState().reloadFromDisk()).resolves.toBeUndefined();
  });
});

describe('normalizeForPersistence minimap_regions round-trip (#481)', () => {
  it('normalizeForPersistence preserves minimap_regions (#481)', async () => {
    // minimap_regions must survive load -> edit -> apply intact so the
    // minimap consumer can read the cached crop region after a GUI round-trip.
    const meta = validMetadata();
    const minimapRegions = [
      {
        match_index: 1,
        region: { x: 0.01, y: 0.02, w: 0.28, h: 0.35, confidence: 1.0, source: 'manual' },
      },
    ];
    const metaWithMinimap = { ...meta, minimap_regions: minimapRegions };
    configureInvoke({
      load_metadata: metaWithMinimap,
      apply_changes: 2000,
      check_backup_exists: false,
    });
    await useMetadataStore.getState().load('p');
    // Need a dirty edit to trigger apply
    useMetadataStore.getState().updateMatch(1, { name: 'x' });
    await useMetadataStore.getState().apply();
    const applyCall = invokeMock.mock.calls.find((c) => c[0] === 'apply_changes');
    expect(applyCall).toBeDefined();
    const persisted = (applyCall![1] as { metadata: Metadata }).metadata;
    expect(persisted.minimap_regions).toEqual(minimapRegions);
  });
});

describe('#695: conflictErrorState lifecycle (#694 *ErrorState form)', () => {
  beforeEach(() => {
    useMetadataStore.setState({
      metadata: null,
      filePath: null,
      dirty: false,
      loadErrorState: null,
      applying: false,
      applyErrorState: null,
      hasBackup: false,
      restoring: false,
      restoreErrorState: null,
      loadedMtimeMs: null,
      conflictErrorState: null,
      pendingDraft: null,
      draftLoadErrorState: null,
      draftSaving: false,
      draftSaveErrorState: null,
    });
  });

  it('runApply() catch (conflict) sets conflictErrorState with hint', async () => {
    useMetadataStore.setState({
      metadata: { source: '/test.mp4', matches: [] } as never,
      filePath: '/test.mp4',
    });

    invokeMock.mockImplementation(async (cmd: string) => {
      if (cmd === 'apply_changes') {
        throw {
          code: 'state.mtime_conflict',
          message: 'metadata.json was modified',
          hint: 'リロード or 上書き',
        };
      }
      throw new Error(`unexpected: ${cmd}`);
    });

    await useMetadataStore.getState().apply();

    const state = useMetadataStore.getState();
    expect(state.conflictErrorState).toEqual({
      message: 'metadata.json was modified',
      hint: 'リロード or 上書き',
      code: 'state.mtime_conflict',
    });
  });

  it('dismissConflict() clears conflictErrorState', () => {
    useMetadataStore.setState({
      conflictErrorState: { message: 'msg', hint: 'hint', code: null },
    });

    useMetadataStore.getState().dismissConflict();

    const state = useMetadataStore.getState();
    expect(state.conflictErrorState).toBeNull();
  });

  it('clear() resets conflictErrorState', () => {
    useMetadataStore.setState({
      conflictErrorState: { message: 'msg', hint: 'hint', code: null },
    });

    useMetadataStore.getState().clear();

    const state = useMetadataStore.getState();
    expect(state.conflictErrorState).toBeNull();
  });

  it('loadSample() resets conflictErrorState', () => {
    useMetadataStore.setState({
      conflictErrorState: { message: 'msg', hint: 'hint', code: null },
    });

    useMetadataStore.getState().loadSample();

    const state = useMetadataStore.getState();
    expect(state.conflictErrorState).toBeNull();
  });

  it('applyOverwrite() success path resets conflictErrorState', async () => {
    // applyOverwrite calls runApply(true) which clears conflictErrorState
    // in the initial set({ applying: true, ... }) before invoking apply_changes.
    useMetadataStore.setState({
      metadata: { source: '/test.mp4', matches: [] } as never,
      filePath: '/test.mp4',
      conflictErrorState: { message: 'prev conflict', hint: 'prev hint', code: null },
    });

    invokeMock.mockImplementation(async (cmd: string) => {
      if (cmd === 'apply_changes') return 12345; // new mtime ms
      if (cmd === 'check_backup_exists') return true;
      if (cmd === 'clear_draft') return undefined;
      throw new Error(`unexpected: ${cmd}`);
    });

    await useMetadataStore.getState().applyOverwrite();

    const state = useMetadataStore.getState();
    expect(state.conflictErrorState).toBeNull();
  });
});
