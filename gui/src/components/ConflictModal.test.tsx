import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { axe } from 'jest-axe';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { invokeMock } = vi.hoisted(() => ({ invokeMock: vi.fn() }));

vi.mock('@tauri-apps/api/core', () => ({
  invoke: invokeMock,
}));

import { useMetadataStore } from '../state/metadataStore';
import type { Metadata } from '../types/metadata';
import { ConflictModal } from './ConflictModal';

function seedMetadata(): Metadata {
  return {
    source: 'C:/videos/src.mkv',
    source_duration: 100,
    source_duration_display: '1:40',
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
        end_time: 50,
        start_display: '00:00',
        end_display: '00:50',
        duration: 50,
        duration_display: '50s',
        type: 'fl_match',
        output_file: 'match_001.mp4',
      },
    ],
    gaps: [],
  };
}

beforeEach(() => {
  invokeMock.mockReset();
  useMetadataStore.getState().clear();
});

describe('ConflictModal', () => {
  it('renders nothing when conflictError is null', () => {
    const { container } = render(<ConflictModal />);
    expect(container.firstChild).toBeNull();
  });

  it('renders dialog + 3 action buttons when conflictError is set', () => {
    // #663: structured AppError 化以後、conflictError には raw message
    // (prefix 無し) が入る。
    useMetadataStore.setState({
      conflictError: 'external modification detected',
    });
    render(<ConflictModal />);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText(/external modification/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '上書き' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'リロード' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'キャンセル' })).toBeInTheDocument();
  });

  it('cancel dismisses the modal without side effects', async () => {
    useMetadataStore.setState({
      conflictError: 'x',
      dirty: true,
    });
    render(<ConflictModal />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'キャンセル' }));
    const state = useMetadataStore.getState();
    expect(state.conflictError).toBeNull();
    expect(state.dirty).toBe(true);
    expect(invokeMock).not.toHaveBeenCalled();
  });

  it('overwrite invokes apply_changes with expectedMtimeMs=null', async () => {
    useMetadataStore.setState({
      conflictError: 'x',
      metadata: seedMetadata(),
      filePath: '/tmp/metadata.json',
      loadedMtimeMs: 1700,
    });
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'apply_changes') return Promise.resolve(2500);
      if (cmd === 'check_backup_exists') return Promise.resolve(false);
      return Promise.reject(new Error(`unmocked: ${cmd}`));
    });
    render(<ConflictModal />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '上書き' }));
    await waitFor(() => {
      expect(useMetadataStore.getState().conflictError).toBeNull();
    });
    const applyCall = invokeMock.mock.calls.find((c) => c[0] === 'apply_changes');
    expect(applyCall).toBeDefined();
    const args = applyCall![1] as { expectedMtimeMs: number | null };
    expect(args.expectedMtimeMs).toBeNull();
  });

  it('reload re-invokes load_metadata + get_metadata_mtime', async () => {
    useMetadataStore.setState({
      conflictError: 'x',
      metadata: seedMetadata(),
      filePath: '/tmp/metadata.json',
      loadedMtimeMs: 1700,
      dirty: true,
    });
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'load_metadata') return Promise.resolve(seedMetadata());
      if (cmd === 'get_metadata_mtime') return Promise.resolve(1900);
      if (cmd === 'check_backup_exists') return Promise.resolve(false);
      return Promise.reject(new Error(`unmocked: ${cmd}`));
    });
    render(<ConflictModal />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'リロード' }));
    await waitFor(() => {
      expect(useMetadataStore.getState().loadedMtimeMs).toBe(1900);
    });
    expect(useMetadataStore.getState().conflictError).toBeNull();
    expect(useMetadataStore.getState().dirty).toBe(false);
  });

  it('Escape dismisses the modal (#587)', async () => {
    useMetadataStore.setState({ conflictError: 'x' });
    render(<ConflictModal />);
    const user = userEvent.setup();
    await user.keyboard('{Escape}');
    expect(useMetadataStore.getState().conflictError).toBeNull();
    expect(invokeMock).not.toHaveBeenCalled();
  });

  it('focus is trapped inside the modal panel (#587)', async () => {
    useMetadataStore.setState({ conflictError: 'x' });
    render(<ConflictModal />);
    const dialog = screen.getByRole('dialog');
    // After mount, focus must have moved into the panel.
    expect(dialog.contains(document.activeElement)).toBe(true);
  });

  it('has no axe violations when shown (#587)', async () => {
    useMetadataStore.setState({ conflictError: 'x' });
    const { container } = render(<ConflictModal />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
