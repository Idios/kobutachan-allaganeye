import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { invokeMock } = vi.hoisted(() => ({ invokeMock: vi.fn() }));

vi.mock('@tauri-apps/api/core', () => ({
  invoke: invokeMock,
}));

import { useMetadataStore } from '../state/metadataStore';
import type { Metadata } from '../types/metadata';
import { DraftRestoreModal } from './DraftRestoreModal';

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

describe('DraftRestoreModal', () => {
  it('renders nothing when no pendingDraft and no draftLoadError', () => {
    const { container } = render(<DraftRestoreModal />);
    expect(container.firstChild).toBeNull();
  });

  it('renders restore dialog with 2 buttons when pendingDraft is set', () => {
    useMetadataStore.setState({ pendingDraft: seedMetadata() });
    render(<DraftRestoreModal />);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(
      screen.getByText(/編集中の draft を復元しますか/),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '復元' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '破棄' })).toBeInTheDocument();
  });

  it('restore applies the draft to the store as a dirty edit', async () => {
    const draft = {
      ...seedMetadata(),
      matches: seedMetadata().matches.map((m) => ({ ...m, name: 'from-draft' })),
    };
    useMetadataStore.setState({
      metadata: seedMetadata(),
      pendingDraft: draft,
      filePath: '/tmp/metadata.json',
    });
    render(<DraftRestoreModal />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '復元' }));
    const state = useMetadataStore.getState();
    expect(state.metadata?.matches[0].name).toBe('from-draft');
    expect(state.dirty).toBe(true);
    expect(state.pendingDraft).toBeNull();
    // Restore is in-memory only — no disk I/O.
    expect(invokeMock).not.toHaveBeenCalled();
  });

  it('discard invokes clear_draft and removes the pending state', async () => {
    useMetadataStore.setState({
      pendingDraft: seedMetadata(),
      filePath: '/tmp/metadata.json',
    });
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'clear_draft') return Promise.resolve();
      return Promise.reject(new Error(`unmocked: ${cmd}`));
    });
    render(<DraftRestoreModal />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '破棄' }));
    await waitFor(() => {
      expect(useMetadataStore.getState().pendingDraft).toBeNull();
    });
    expect(invokeMock).toHaveBeenCalledWith('clear_draft', {
      path: '/tmp/metadata.json',
    });
  });

  it('shows error-only modal when draftLoadError is set', () => {
    useMetadataStore.setState({
      draftLoadError: 'parse error: invalid JSON',
      filePath: '/tmp/metadata.json',
    });
    render(<DraftRestoreModal />);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(
      screen.getByText(/draft を読み取れませんでした/),
    ).toBeInTheDocument();
    expect(screen.getByText(/parse error/)).toBeInTheDocument();
    // Only the discard button is offered in the error path.
    expect(screen.getByRole('button', { name: '破棄' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '復元' })).toBeNull();
  });
});
