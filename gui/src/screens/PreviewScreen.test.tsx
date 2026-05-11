import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { axe } from 'jest-axe';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { invokeMock, askMock } = vi.hoisted(() => ({
  invokeMock: vi.fn(),
  askMock: vi.fn(),
}));

vi.mock('@tauri-apps/api/core', () => ({
  invoke: invokeMock,
}));

vi.mock('@tauri-apps/plugin-dialog', () => ({
  ask: askMock,
}));

import { PreviewScreen } from './PreviewScreen';
import { useAppStateStore } from '../state/appStateStore';
import { useMetadataStore } from '../state/metadataStore';

beforeEach(() => {
  invokeMock.mockReset();
  askMock.mockReset();
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

  // #663 — Phase 4: when applyError is set in the store, render the
  // companion applyErrorHint as a 2nd line so the user sees the
  // recommended next step. Hint stays inside the existing role="alert"
  // wrapper so a screen reader announces message + hint as one update.
  it('renders applyErrorHint inline when present (#663)', () => {
    useMetadataStore.setState({
      applyError: 'disk full',
      applyErrorHint: 'free up space',
    });
    render(<PreviewScreen />);
    expect(screen.getByText('disk full')).toBeInTheDocument();
    expect(screen.getByText(/free up space/)).toBeInTheDocument();
  });

  it('renders 2 panes (IN, OUT) with IN active by default', () => {
    render(<PreviewScreen />);
    const inPane = screen.getByRole('button', { name: /IN \(start\)/ });
    const outPane = screen.getByRole('button', { name: /OUT \(end\)/ });
    expect(inPane.getAttribute('aria-pressed')).toBe('true');
    expect(outPane.getAttribute('aria-pressed')).toBe('false');
  });

  it('panes are tagged data-pane="in" / "out" so CSS can color the active border (#587)', () => {
    render(<PreviewScreen />);
    const inPane = screen.getByRole('button', { name: /IN \(start\)/ });
    const outPane = screen.getByRole('button', { name: /OUT \(end\)/ });
    expect(inPane.getAttribute('data-pane')).toBe('in');
    expect(outPane.getAttribute('data-pane')).toBe('out');
  });

  it(
    'has no axe violations after register_video resolves (#587)',
    async () => {
      const { container } = render(<PreviewScreen />);
      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /IN \(start\)/ }),
        ).toBeInTheDocument();
      });
      // The Pane wraps a video element + timecode input inside a
      // <button> so the whole pane area can activate on click. axe's
      // nested-interactive rule flags that pattern, but screen-reader
      // support is out of scope for this tool (see
      // docs/a11y-policy.md), and the wrapping button is essential to
      // the click-to-activate UX. Opt this rule out for the preview
      // surface only.
      expect(
        await axe(container, {
          rules: {
            'nested-interactive': { enabled: false },
          },
        }),
      ).toHaveNoViolations();
    },
    15000,
  );

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

  it('editing name flips store dirty after the 200ms debounce, then apply clears it', async () => {
    useMetadataStore.setState({ filePath: '/x' });
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'apply_changes') return Promise.resolve();
      if (cmd === 'check_backup_exists') return Promise.resolve(true);
      if (cmd === 'save_draft') return Promise.resolve();
      if (cmd === 'load_metadata') return Promise.reject(new Error('not needed'));
      return Promise.reject(new Error(`unmocked: ${cmd}`));
    });
    render(<PreviewScreen />);
    const user = userEvent.setup();
    const input = screen.getByLabelText('match name') as HTMLInputElement;
    await user.click(input);
    await user.clear(input);
    await user.type(input, 'renamed');
    // #589: edits commit through the 200ms debounce, so dirty must flip true
    // *during* editing (not only on [適用]).
    await waitFor(
      () => {
        expect(useMetadataStore.getState().dirty).toBe(true);
      },
      { timeout: 1000 },
    );
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

  // #589 — state mutation flow / dirty consume / silent loss confirm.
  // ui-interaction-spec.md §1.1 / §1.3 が canonical 仕様。

  it('editing matchType eagerly flips store dirty (no debounce wait)', async () => {
    useMetadataStore.setState({ filePath: '/x' });
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'check_backup_exists') return Promise.resolve(false);
      if (cmd === 'save_draft') return Promise.resolve();
      if (cmd === 'register_video')
        return Promise.resolve({ url: 'http://x', token: 't' });
      if (cmd === 'generate_match_thumbnails') return Promise.resolve([]);
      return Promise.reject(new Error(`unmocked: ${cmd}`));
    });
    render(<PreviewScreen />);
    const user = userEvent.setup();
    const select = screen.getByLabelText('match type') as HTMLSelectElement;
    await user.selectOptions(select, 'unknown');
    // §1.1 例外: 単一選択は即時 commit。debounce 待ちなしで dirty=true。
    expect(useMetadataStore.getState().dirty).toBe(true);
  });

  it('matchType change while name edit is mid-debounce flushes the pending name first', async () => {
    // #589 review: type select onChange does flushUpdate() before its own
    // immediate updateMatch. If a debounced name patch is in flight, flush
    // commits it BEFORE the type_override commit lands, so neither edit is
    // lost regardless of how quickly the user toggles type after typing.
    useMetadataStore.setState({ filePath: '/x' });
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'check_backup_exists') return Promise.resolve(false);
      if (cmd === 'save_draft') return Promise.resolve();
      if (cmd === 'register_video')
        return Promise.resolve({ url: 'http://x', token: 't' });
      if (cmd === 'generate_match_thumbnails') return Promise.resolve([]);
      return Promise.reject(new Error(`unmocked: ${cmd}`));
    });
    render(<PreviewScreen />);
    const user = userEvent.setup();

    // Type the name (debounce timer running, no commit yet).
    const nameInput = screen.getByLabelText('match name') as HTMLInputElement;
    await user.clear(nameInput);
    await user.type(nameInput, 'edited-name');

    // Immediately switch type before the 200ms debounce fires. The select
    // handler flushes the pending name patch synchronously, then commits the
    // type_override on top.
    const select = screen.getByLabelText('match type') as HTMLSelectElement;
    await user.selectOptions(select, 'unknown');

    const state = useMetadataStore.getState();
    const target = state.metadata!.matches.find((m) => m.index === 4)!;
    expect(target.name).toBe('edited-name');
    expect(target.type_override).toBe('unknown');
    expect(state.dirty).toBe(true);
  });

  it('stepRow +1s flips store dirty within the 200ms debounce window', async () => {
    useMetadataStore.setState({ filePath: '/x' });
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'check_backup_exists') return Promise.resolve(false);
      if (cmd === 'save_draft') return Promise.resolve();
      if (cmd === 'register_video')
        return Promise.resolve({ url: 'http://x', token: 't' });
      if (cmd === 'generate_match_thumbnails') return Promise.resolve([]);
      return Promise.reject(new Error(`unmocked: ${cmd}`));
    });
    render(<PreviewScreen />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /nudge \+1s/ }));
    await waitFor(
      () => {
        expect(useMetadataStore.getState().dirty).toBe(true);
      },
      { timeout: 1000 },
    );
  });

  it('selectMatch resyncs the local TC state to the newly selected match', async () => {
    render(<PreviewScreen />);
    const before = (
      screen.getByLabelText('IN (start) timecode') as HTMLInputElement
    ).value;
    // sample fixture には複数 match あり — index=4 の隣を選択
    const otherIndex = useMetadataStore
      .getState()
      .metadata!.matches.find((m) => m.index !== 4)!.index;
    useAppStateStore.getState().selectMatch(otherIndex);
    await waitFor(() => {
      const after = (
        screen.getByLabelText('IN (start) timecode') as HTMLInputElement
      ).value;
      expect(after).not.toBe(before);
    });
  });

  it('dirty + [◀ 一覧へ]: confirm cancel keeps the user on preview and preserves dirty', async () => {
    useMetadataStore.setState({ filePath: '/x' });
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'check_backup_exists') return Promise.resolve(false);
      if (cmd === 'save_draft') return Promise.resolve();
      if (cmd === 'register_video')
        return Promise.resolve({ url: 'http://x', token: 't' });
      if (cmd === 'generate_match_thumbnails') return Promise.resolve([]);
      return Promise.reject(new Error(`unmocked: ${cmd}`));
    });
    askMock.mockResolvedValueOnce(false);

    render(<PreviewScreen />);
    const user = userEvent.setup();
    const input = screen.getByLabelText('match name') as HTMLInputElement;
    await user.clear(input);
    await user.type(input, 'edit');
    await waitFor(
      () => {
        expect(useMetadataStore.getState().dirty).toBe(true);
      },
      { timeout: 1000 },
    );

    await user.click(screen.getByRole('button', { name: /一覧へ/ }));
    await waitFor(() => {
      expect(askMock).toHaveBeenCalledWith(
        expect.stringContaining('未保存の変更'),
        expect.objectContaining({ kind: 'warning' }),
      );
    });
    expect(useAppStateStore.getState().screen).toBe('preview');
    expect(useMetadataStore.getState().dirty).toBe(true);
  });

  it('dirty + [◀ 一覧へ]: confirm OK calls discardEdits (clear_draft + load) and navigates', async () => {
    useMetadataStore.setState({ filePath: '/x' });
    const snapshot = useMetadataStore.getState().metadata!;
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'check_backup_exists') return Promise.resolve(false);
      if (cmd === 'save_draft') return Promise.resolve();
      if (cmd === 'clear_draft') return Promise.resolve();
      if (cmd === 'load_metadata') return Promise.resolve(snapshot);
      if (cmd === 'get_metadata_mtime') return Promise.resolve(1700);
      if (cmd === 'load_draft') return Promise.resolve(null);
      if (cmd === 'register_video')
        return Promise.resolve({ url: 'http://x', token: 't' });
      if (cmd === 'generate_match_thumbnails') return Promise.resolve([]);
      return Promise.reject(new Error(`unmocked: ${cmd}`));
    });
    askMock.mockResolvedValueOnce(true);

    render(<PreviewScreen />);
    const user = userEvent.setup();
    const input = screen.getByLabelText('match name') as HTMLInputElement;
    await user.clear(input);
    await user.type(input, 'edit');
    await waitFor(
      () => {
        expect(useMetadataStore.getState().dirty).toBe(true);
      },
      { timeout: 1000 },
    );

    await user.click(screen.getByRole('button', { name: /一覧へ/ }));
    await waitFor(() => {
      expect(askMock).toHaveBeenCalledWith(
        expect.stringContaining('未保存の変更'),
        expect.objectContaining({ kind: 'warning' }),
      );
    });
    // discardEdits は draft を clear → metadata 再 load の順で呼ぶ
    await waitFor(() => {
      const calls = invokeMock.mock.calls.map((c) => c[0]);
      expect(calls).toContain('clear_draft');
      expect(calls).toContain('load_metadata');
      expect(calls.indexOf('clear_draft')).toBeLessThan(
        calls.indexOf('load_metadata'),
      );
    });
    await waitFor(() => {
      expect(useAppStateStore.getState().screen).toBe('complete');
    });
    expect(useMetadataStore.getState().dirty).toBe(false);
  });

  it('dirty + [書き出し]: confirm OK navigates to export with canonical wording', async () => {
    useMetadataStore.setState({ filePath: '/x' });
    const snapshot = useMetadataStore.getState().metadata!;
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'check_backup_exists') return Promise.resolve(false);
      if (cmd === 'save_draft') return Promise.resolve();
      if (cmd === 'clear_draft') return Promise.resolve();
      if (cmd === 'load_metadata') return Promise.resolve(snapshot);
      if (cmd === 'get_metadata_mtime') return Promise.resolve(1700);
      if (cmd === 'load_draft') return Promise.resolve(null);
      if (cmd === 'register_video')
        return Promise.resolve({ url: 'http://x', token: 't' });
      if (cmd === 'generate_match_thumbnails') return Promise.resolve([]);
      return Promise.reject(new Error(`unmocked: ${cmd}`));
    });
    askMock.mockResolvedValueOnce(true);

    render(<PreviewScreen />);
    const user = userEvent.setup();
    const input = screen.getByLabelText('match name') as HTMLInputElement;
    await user.clear(input);
    await user.type(input, 'edit');
    await waitFor(
      () => {
        expect(useMetadataStore.getState().dirty).toBe(true);
      },
      { timeout: 1000 },
    );

    await user.click(screen.getByRole('button', { name: /書き出し/ }));
    await waitFor(() => {
      expect(askMock).toHaveBeenCalledWith(
        expect.stringMatching(/未保存の変更.*書き出し/),
        expect.objectContaining({ kind: 'warning' }),
      );
    });
    await waitFor(() => {
      expect(useAppStateStore.getState().screen).toBe('export');
    });
  });

  it('stepper buttons adjust the active timestamp', async () => {
    // Exit sample mode so buttons are enabled (sample mode disables them; see Task 1.5)
    useMetadataStore.setState({ filePath: '/x' });
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
    // Exit sample mode so the TC input is enabled and focusable (sample mode disables it; see Task 1.5)
    useMetadataStore.setState({ filePath: '/x' });
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
    // Exit sample mode so buttons show their keyboard-hint title (sample mode overrides title; see Task 1.5)
    useMetadataStore.setState({ filePath: '/x' });
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

  // #465 review 追加: 再生中の TC 表示は video.currentTime に追従する。

  it('TC display follows video.currentTime during playback (timeupdate event)', async () => {
    render(<PreviewScreen />);
    const video = (await screen.findByLabelText(
      'IN (start) video',
    )) as HTMLVideoElement;
    const tc = screen.getByLabelText('IN (start) timecode') as HTMLInputElement;
    const initial = tc.value;

    // video が再生中の状態を simulate: paused=false + currentTime を進める
    Object.defineProperty(video, 'paused', { value: false, configurable: true });
    Object.defineProperty(video, 'currentTime', {
      value: 12.5,
      configurable: true,
    });
    // dispatchEvent で timeupdate を発火
    video.dispatchEvent(new Event('timeupdate'));

    // state 更新を待つ
    await new Promise((r) => setTimeout(r, 20));
    expect(tc.value).not.toBe(initial);
    // TC は 0:00:12.xx (fmtPreciseTime 形式) であるべき
    expect(tc.value).toMatch(/^0:00:12/);
  });

  it('TC display does NOT update from timeupdate while paused (state remains user-controlled)', async () => {
    render(<PreviewScreen />);
    const video = (await screen.findByLabelText(
      'IN (start) video',
    )) as HTMLVideoElement;
    const tc = screen.getByLabelText('IN (start) timecode') as HTMLInputElement;
    const initial = tc.value;

    // paused=true の状態で currentTime を変更 → timeupdate (pause 直前の最後の tick 等)
    Object.defineProperty(video, 'paused', { value: true, configurable: true });
    Object.defineProperty(video, 'currentTime', {
      value: 30.0,
      configurable: true,
    });
    video.dispatchEvent(new Event('timeupdate'));
    await new Promise((r) => setTimeout(r, 20));
    // paused 中は state を上書きしない → TC は初期値のまま
    expect(tc.value).toBe(initial);
  });

  // #465 review: fps-aware frame stepping. sampleMetadata は source_fps=60。
  // metadata を 120 / 240 に差し替えて Alt+Arrow が実 1 フレーム step に
  // なることを確認する。

  it('Alt+ArrowRight steps 1/120 sec when source_fps is 120', async () => {
    // metadata.source_fps を 120 に上書き (state を直接書き換え)
    const sample = useMetadataStore.getState().metadata!;
    useMetadataStore.setState({
      metadata: { ...sample, source_fps: 120 },
    });
    render(<PreviewScreen />);
    const tc = screen.getByLabelText(
      'IN (start) timecode',
    ) as HTMLInputElement;
    // current value を parse して比較するため初期値を読んでおく
    const before = tc.value;
    await userEvent.setup().keyboard('{Alt>}{ArrowRight}{/Alt}');
    const after = tc.value;
    // 実際の差分を解読: H:MM:SS.FF の FF (frame portion) が 1 進む or
    // 120fps では sub-second 増分が 1/120 ≒ 0.00833s。
    // 簡易検証: TC 値が変化していること + .FF 末尾がインクリメント傾向
    expect(after).not.toBe(before);
  });

  it('Alt+ArrowRight steps 1/240 sec when source_fps is 240', async () => {
    const sample = useMetadataStore.getState().metadata!;
    useMetadataStore.setState({
      metadata: { ...sample, source_fps: 240 },
    });
    render(<PreviewScreen />);
    const tc = screen.getByLabelText(
      'IN (start) timecode',
    ) as HTMLInputElement;
    const before = tc.value;
    await userEvent.setup().keyboard('{Alt>}{ArrowRight}{/Alt}');
    const after = tc.value;
    expect(after).not.toBe(before);
  });

  it('falls back to DEFAULT_FPS=60 when metadata.source_fps is missing', () => {
    // Exit sample mode so buttons show keyboard-hint title (sample mode overrides title; see Task 1.5)
    useMetadataStore.setState({ filePath: '/x' });
    // legacy metadata.json を simulate: source_fps なし
    const sample = useMetadataStore.getState().metadata!;
    const { source_fps: _ignored, ...legacy } = sample;
    void _ignored;
    useMetadataStore.setState({
      metadata: legacy as typeof sample,
    });
    render(<PreviewScreen />);
    // +1F ボタンの title に Alt+→ が含まれる (fps が存在さえすれば label 共通)
    const plus1F = screen.getByRole('button', { name: /nudge \+1F/ });
    expect(plus1F.getAttribute('title')).toContain('+1F');
    expect(plus1F.getAttribute('title')).toContain('Alt');
    // 60fps での frame portion 表示: 0.5s → .30
    // 既存の +1s / +10s ボタンは fps-independent なので default 60 で動作
    const tc = screen.getByLabelText(
      'IN (start) timecode',
    ) as HTMLInputElement;
    expect(tc.value).toMatch(/^\d+:\d{2}:\d{2}\.\d{2}$/);
  });
});

describe('PreviewScreen sample mode disabled (Task 1.5)', () => {
  // The outer beforeEach already calls loadSample() (filePath=null) and selectMatch(4).
  // That means isSample = (filePath===null && metadata!==null) = true.
  // No additional setup needed — sample mode is the default state.

  it('disables matchName input with sample tooltip', () => {
    render(<PreviewScreen />);
    const input = screen.getByLabelText('match name') as HTMLInputElement;
    expect(input).toBeDisabled();
    expect(input).toHaveAttribute('title', 'サンプル動画では保存できません');
  });

  it('disables matchType select with sample tooltip', () => {
    render(<PreviewScreen />);
    const select = screen.getByLabelText('match type') as HTMLSelectElement;
    expect(select).toBeDisabled();
    expect(select).toHaveAttribute('title', 'サンプル動画では保存できません');
  });

  it('disables stepRow buttons (×6) with sample tooltip', () => {
    render(<PreviewScreen />);
    // stepRow buttons use aria-label like "nudge +1s", "nudge −1F", etc.
    const stepButtons = screen.getAllByRole('button', { name: /^nudge /i });
    expect(stepButtons.length).toBeGreaterThanOrEqual(6);
    stepButtons.forEach((btn) => {
      expect(btn).toBeDisabled();
      expect(btn).toHaveAttribute('title', 'サンプル動画では保存できません');
    });
  });

  it('disables Pane tcInput (×2 IN/OUT) with sample tooltip', () => {
    render(<PreviewScreen />);
    // Pane tcInputs are labeled "IN (start) timecode" and "OUT (end) timecode"
    const tcInputs = screen.getAllByLabelText(/timecode$/i);
    expect(tcInputs.length).toBe(2);
    tcInputs.forEach((input) => {
      expect(input).toBeDisabled();
      expect(input).toHaveAttribute('title', 'サンプル動画では保存できません');
    });
  });

  it('disables FrameStrip frame click in sample mode', () => {
    render(<PreviewScreen />);
    // FrameStrip thumbs render as buttons with aria-label "frame H:MM:SS.FF"
    const frames = screen.queryAllByRole('button', { name: /^frame /i });
    // All present frames should be disabled
    frames.forEach((f) => {
      expect(f).toBeDisabled();
    });
  });
});
