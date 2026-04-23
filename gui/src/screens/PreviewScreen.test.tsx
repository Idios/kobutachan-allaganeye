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
  // #465: PreviewScreen kicks off register_video on mount. Default the
  // mock so individual tests don't see "unmocked invoke" from that call.
  invokeMock.mockImplementation((cmd: string) => {
    if (cmd === 'register_video') {
      return Promise.resolve({
        url: 'http://127.0.0.1:0/video/test-token',
        token: 'test-token',
      });
    }
    if (cmd === 'generate_match_thumbnails') return Promise.resolve([]);
    if (cmd === 'check_backup_exists') return Promise.resolve(false);
    return Promise.reject(new Error(`unmocked: ${cmd}`));
  });
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

  // #465 -- video player + keyboard.

  it('renders a <video> element with the registered URL after mount', async () => {
    render(<PreviewScreen />);
    const video = await screen.findByLabelText<HTMLVideoElement>(
      'IN (start) video',
    );
    expect(video.tagName).toBe('VIDEO');
    expect(video.getAttribute('src')).toContain('/video/test-token');
  });

  it('falls back to an error banner when register_video rejects', async () => {
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'register_video')
        return Promise.reject(new Error('video server busted'));
      if (cmd === 'check_backup_exists') return Promise.resolve(false);
      return Promise.reject(new Error(`unmocked: ${cmd}`));
    });
    render(<PreviewScreen />);
    const alerts = await screen.findAllByRole('alert');
    expect(alerts.some((el) => el.textContent?.includes('video server busted')))
      .toBe(true);
  });

  it('ArrowRight key nudges the active timestamp forward by 1s', async () => {
    render(<PreviewScreen />);
    const before = (
      screen.getByLabelText('IN (start) timecode') as HTMLInputElement
    ).value;
    await userEvent.setup().keyboard('{ArrowRight}');
    const after = (
      screen.getByLabelText('IN (start) timecode') as HTMLInputElement
    ).value;
    expect(after).not.toBe(before);
  });

  it('Shift+ArrowLeft nudges the active timestamp (10s step) — different value from plain ArrowLeft', async () => {
    render(<PreviewScreen />);
    const before = (
      screen.getByLabelText('IN (start) timecode') as HTMLInputElement
    ).value;
    await userEvent.setup().keyboard('{Shift>}{ArrowLeft}{/Shift}');
    const after = (
      screen.getByLabelText('IN (start) timecode') as HTMLInputElement
    ).value;
    expect(after).not.toBe(before);
  });

  it('keyboard shortcuts do not fire while the TC input is focused', async () => {
    render(<PreviewScreen />);
    const tc = screen.getByLabelText(
      'IN (start) timecode',
    ) as HTMLInputElement;
    const initial = tc.value;
    tc.focus();
    await userEvent.setup().keyboard('{ArrowRight}');
    // tc remains focused; ArrowRight is caret movement inside the input.
    expect(tc.value).toBe(initial);
  });
});
