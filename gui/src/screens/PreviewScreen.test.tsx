import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { invokeMock } = vi.hoisted(() => ({ invokeMock: vi.fn() }));

vi.mock('@tauri-apps/api/core', () => ({
  invoke: invokeMock,
}));

import { PreviewScreen } from './PreviewScreen';
import { useAppStateStore } from '../state/appStateStore';
import { useMetadataStore } from '../state/metadataStore';

beforeEach(() => {
  invokeMock.mockReset();
  useAppStateStore.getState().reset();
  useMetadataStore.getState().clear();
  useMetadataStore.getState().loadSample();
  useAppStateStore.getState().selectMatch(4);
  useAppStateStore.getState().navigate('preview');
});

describe('PreviewScreen', () => {
  it('renders the current match name and index', () => {
    render(<PreviewScreen />);
    const input = screen.getByLabelText('match name') as HTMLInputElement;
    expect(input.value).toBe('match_004');
    expect(screen.getByText(/#004 · of 9/)).toBeInTheDocument();
  });

  it('renders 2 panes (IN, OUT) with IN active by default', () => {
    render(<PreviewScreen />);
    const inPane = screen.getByRole('button', { name: /IN \(start\)/ });
    const outPane = screen.getByRole('button', { name: /OUT \(end\)/ });
    expect(inPane.getAttribute('aria-pressed')).toBe('true');
    expect(outPane.getAttribute('aria-pressed')).toBe('false');
  });

  it('clicking OUT pane activates end editing', async () => {
    render(<PreviewScreen />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /OUT \(end\)/ }));
    const outPane = screen.getByRole('button', { name: /OUT \(end\)/ });
    expect(outPane.getAttribute('aria-pressed')).toBe('true');
  });

  it('[◀ 一覧へ] returns to complete when not dirty', async () => {
    render(<PreviewScreen />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /一覧へ/ }));
    expect(useAppStateStore.getState().screen).toBe('complete');
  });

  it('[書き出し] navigates to export when not dirty', async () => {
    render(<PreviewScreen />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /書き出し/ }));
    expect(useAppStateStore.getState().screen).toBe('export');
  });

  it('[適用] is disabled when not dirty', () => {
    render(<PreviewScreen />);
    const apply = screen.getByRole('button', { name: 'apply' });
    expect(apply).toBeDisabled();
  });

  it('editing name marks store dirty (via updateMatch)', async () => {
    useMetadataStore.setState({ filePath: '/x' });
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'apply_changes') return Promise.resolve();
      if (cmd === 'check_backup_exists') return Promise.resolve(true);
      if (cmd === 'load_metadata') return Promise.reject(new Error('not needed'));
      return Promise.reject(new Error(`unmocked: ${cmd}`));
    });
    render(<PreviewScreen />);
    const user = userEvent.setup();
    const input = screen.getByLabelText('match name') as HTMLInputElement;
    await user.click(input);
    await user.clear(input);
    await user.type(input, 'renamed');
    // No dirty yet — changes are local until [適用]
    expect(useMetadataStore.getState().dirty).toBe(false);
    await user.click(screen.getByRole('button', { name: 'apply' }));
    await waitFor(() => {
      expect(invokeMock).toHaveBeenCalledWith(
        'apply_changes',
        expect.any(Object),
      );
    });
    // After apply completes dirty flips back to false
    await waitFor(() => {
      expect(useMetadataStore.getState().dirty).toBe(false);
    });
  });

  it('stepper buttons adjust the active timestamp', async () => {
    render(<PreviewScreen />);
    const user = userEvent.setup();
    const initial = (
      screen.getByLabelText('IN (start) timecode') as HTMLInputElement
    ).value;
    await user.click(screen.getByRole('button', { name: /nudge \+1s/ }));
    const after = (
      screen.getByLabelText('IN (start) timecode') as HTMLInputElement
    ).value;
    expect(after).not.toBe(initial);
  });
});
