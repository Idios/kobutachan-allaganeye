import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { invokeMock } = vi.hoisted(() => ({ invokeMock: vi.fn() }));

vi.mock('@tauri-apps/api/core', () => ({
  invoke: invokeMock,
}));

import { useMetadataStore } from '../state/metadataStore';
import { RestoreButton } from './RestoreButton';

beforeEach(() => {
  invokeMock.mockReset();
  useMetadataStore.getState().clear();
});

describe('RestoreButton', () => {
  it('is disabled when hasBackup=false', () => {
    useMetadataStore.setState({ filePath: '/x', hasBackup: false });
    render(<RestoreButton />);
    const button = screen.getByRole('button', { name: '元に戻す' });
    expect(button).toBeDisabled();
  });

  it('is enabled when hasBackup=true', () => {
    useMetadataStore.setState({ filePath: '/x', hasBackup: true });
    render(<RestoreButton />);
    expect(
      screen.getByRole('button', { name: '元に戻す' }),
    ).not.toBeDisabled();
  });

  it('calls restore + onRestored after confirm OK', async () => {
    useMetadataStore.setState({ filePath: '/x', hasBackup: true });
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'restore_from_original') return Promise.resolve();
      if (cmd === 'load_metadata') {
        return Promise.resolve({
          source: 'x',
          source_duration: 1,
          source_duration_display: '0:01',
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
          matches: [],
          gaps: [],
        });
      }
      if (cmd === 'check_backup_exists') return Promise.resolve(true);
      return Promise.reject(new Error(`unmocked: ${cmd}`));
    });
    const onRestored = vi.fn();
    const confirmFn = vi.fn(() => true);
    render(<RestoreButton onRestored={onRestored} confirmFn={confirmFn} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '元に戻す' }));
    await waitFor(() => {
      expect(onRestored).toHaveBeenCalledTimes(1);
    });
    expect(confirmFn).toHaveBeenCalled();
    expect(invokeMock).toHaveBeenCalledWith('restore_from_original', {
      path: '/x',
    });
  });

  it('does nothing when confirm is cancelled', async () => {
    useMetadataStore.setState({ filePath: '/x', hasBackup: true });
    const onRestored = vi.fn();
    const confirmFn = vi.fn(() => false);
    render(<RestoreButton onRestored={onRestored} confirmFn={confirmFn} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '元に戻す' }));
    expect(onRestored).not.toHaveBeenCalled();
    expect(invokeMock).not.toHaveBeenCalled();
  });

  it('renders an alert when restoreError is set in the store', () => {
    useMetadataStore.setState({
      filePath: '/x',
      hasBackup: true,
      restoreError: 'disk full',
    });
    render(<RestoreButton />);
    expect(screen.getByRole('alert')).toHaveTextContent('disk full');
  });
});
