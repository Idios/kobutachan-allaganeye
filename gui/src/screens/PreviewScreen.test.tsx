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

  // #465 review (UX items 3/4): tooltip + visible key hint + click-to-play.

  it('step buttons have tooltips with the keyboard equivalent', async () => {
    render(<PreviewScreen />);
    // ±1F / ±1s / ±10s ボタンそれぞれに対応するキー等価操作が title に含まれる
    const plus1F = screen.getByRole('button', { name: /nudge \+1F/ });
    expect(plus1F.getAttribute('title')).toContain('Alt');
    expect(plus1F.getAttribute('title')).toContain('→');

    const minus10s = screen.getByRole('button', { name: /nudge -10s/ });
    expect(minus10s.getAttribute('title')).toContain('Shift');
    expect(minus10s.getAttribute('title')).toContain('←');

    const plus1s = screen.getByRole('button', { name: /nudge \+1s/ });
    // ±1s は修飾キーなし
    expect(plus1s.getAttribute('title')).toContain('→');
    expect(plus1s.getAttribute('title')).not.toContain('Shift');
    expect(plus1s.getAttribute('title')).not.toContain('Alt');
  });

  it('renders a visible keyboard hint bar describing the shortcuts', () => {
    render(<PreviewScreen />);
    const hint = screen.getByRole('note', { name: /keyboard shortcuts/i });
    expect(hint).toBeInTheDocument();
    // 主要キー名が hint に出ていること (視認性確保)
    expect(hint.textContent).toMatch(/Shift/);
    expect(hint.textContent).toMatch(/Alt/);
    expect(hint.textContent).toMatch(/Space/);
    expect(hint.textContent).toMatch(/1s/);
    expect(hint.textContent).toMatch(/10s/);
    expect(hint.textContent).toMatch(/1F/);
  });

  it('clicking the video on the active pane toggles play/pause', async () => {
    render(<PreviewScreen />);
    const video = (await screen.findByLabelText(
      'IN (start) video',
    )) as HTMLVideoElement;
    // jsdom には play/pause のネイティブ実装が無いので spy を当てる
    const playSpy = vi.spyOn(video, 'play').mockResolvedValue();
    const pauseSpy = vi.spyOn(video, 'pause').mockImplementation(() => {});
    // IN pane は default で active → クリックで play が呼ばれる
    Object.defineProperty(video, 'paused', { value: true, configurable: true });
    await userEvent.setup().click(video);
    expect(playSpy).toHaveBeenCalledTimes(1);

    // 再度クリック: 今度は paused=false にして pause が呼ばれる
    Object.defineProperty(video, 'paused', { value: false, configurable: true });
    await userEvent.setup().click(video);
    expect(pauseSpy).toHaveBeenCalledTimes(1);
  });

  it('clicking the video on an INACTIVE pane activates it instead of play/pause', async () => {
    render(<PreviewScreen />);
    const outVideo = (await screen.findByLabelText(
      'OUT (end) video',
    )) as HTMLVideoElement;
    const playSpy = vi.spyOn(outVideo, 'play').mockResolvedValue();
    const pauseSpy = vi
      .spyOn(outVideo, 'pause')
      .mockImplementation(() => {});
    Object.defineProperty(outVideo, 'paused', {
      value: true,
      configurable: true,
    });
    // OUT は default で inactive → クリックで activate のみ。play は呼ばれない
    await userEvent.setup().click(outVideo);
    expect(playSpy).not.toHaveBeenCalled();
    expect(pauseSpy).not.toHaveBeenCalled();
    // 2 回目のクリックで now-active な OUT が play へ
    Object.defineProperty(outVideo, 'paused', {
      value: true,
      configurable: true,
    });
    await userEvent.setup().click(outVideo);
    expect(playSpy).toHaveBeenCalledTimes(1);
  });
});
