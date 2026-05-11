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

  it('shows a no-backup reason tooltip when hasBackup=false (#587)', () => {
    useMetadataStore.setState({ filePath: '/x', hasBackup: false });
    render(<RestoreButton />);
    const button = screen.getByRole('button', { name: '元に戻す' });
    expect(button.getAttribute('title')).toBe('バックアップが存在しません');
  });

  it('shows a "復元中" reason tooltip while restoring (#587)', () => {
    useMetadataStore.setState({
      filePath: '/x',
      hasBackup: true,
      restoring: true,
    });
    render(<RestoreButton />);
    const button = screen.getByRole('button', { name: '元に戻す' });
    expect(button.getAttribute('title')).toBe('復元中です');
  });

  it('drops the title attribute when enabled (#587)', () => {
    useMetadataStore.setState({ filePath: '/x', hasBackup: true });
    render(<RestoreButton />);
    const button = screen.getByRole('button', { name: '元に戻す' });
    expect(button.hasAttribute('title')).toBe(false);
  });

  it('shows sample mode reason when filePath=null && metadata=non-null', async () => {
    // sample mode setup: loadSample で metadata 設定後 hasBackup=false に
    useMetadataStore.getState().clear();
    useMetadataStore.getState().loadSample();
    useMetadataStore.setState({ hasBackup: false, restoring: false });

    render(<RestoreButton />);
    const btn = screen.getByRole('button', { name: /元に戻す/ });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute('title', 'サンプル動画では保存できません');
    // inline hint も表示される (§1.2 主要 CTA 規約)
    // DisabledTooltip の inline hint span に reason 文字列が出る
    // title 属性は DOM textContent に現れないため getAllByText は inline hint span のみ検出
    const hints = screen.getAllByText('サンプル動画では保存できません');
    expect(hints.length).toBeGreaterThanOrEqual(1); // inline hint span
  });

  it('prefers restoring reason over sample mode', () => {
    useMetadataStore.getState().clear();
    useMetadataStore.getState().loadSample();
    useMetadataStore.setState({ hasBackup: true, restoring: true });

    render(<RestoreButton />);
    const btn = screen.getByRole('button', { name: /元に戻す/ });
    expect(btn).toHaveAttribute('title', '復元中です');
  });

  // #663 — Phase 4: render the AppError hint as a 2nd line after the
  // existing inline error message so the user sees both the failure and
  // the recommended next step. Hint stays inside the role="alert"
  // wrapper to avoid double-announcement by screen readers.
  describe('hint rendering (#663)', () => {
    it('renders restoreErrorHint as 2nd line when present', () => {
      useMetadataStore.setState({
        filePath: '/x',
        hasBackup: true,
        restoring: false,
        restoreError: 'backup not found',
        restoreErrorHint: 'create backup first',
      });
      render(<RestoreButton />);
      expect(screen.getByText('backup not found')).toBeInTheDocument();
      expect(screen.getByText(/create backup first/)).toBeInTheDocument();
    });

    it('does not render hint when restoreErrorHint is null', () => {
      useMetadataStore.setState({
        filePath: '/x',
        hasBackup: true,
        restoring: false,
        restoreError: 'plain message',
        restoreErrorHint: null,
      });
      render(<RestoreButton />);
      expect(screen.getByText('plain message')).toBeInTheDocument();
      expect(screen.queryByText(/💡/)).not.toBeInTheDocument();
    });

    it('hint stays inside the role="alert" wrapper for screen-reader continuity (#663)', () => {
      useMetadataStore.setState({
        filePath: '/x',
        hasBackup: true,
        restoring: false,
        restoreError: 'backup not found',
        restoreErrorHint: 'create backup first',
      });
      render(<RestoreButton />);
      const alert = screen.getByRole('alert');
      // Both message and hint should be DOM-descendants of the same alert region,
      // so the screen reader announces them as one update.
      expect(alert).toHaveTextContent('backup not found');
      expect(alert).toHaveTextContent(/create backup first/);
    });
  });
});
