import { beforeEach, describe, expect, it, vi } from 'vitest';

const { invokeMock, listenMock, unlistenMock, captured } = vi.hoisted(() => {
  const captured: Array<(event: { payload: unknown }) => void> = [];
  const unlistenMock = vi.fn(() => {});
  return {
    captured,
    unlistenMock,
    invokeMock: vi.fn(),
    listenMock: vi.fn(
      async (
        _name: string,
        cb: (event: { payload: unknown }) => void,
      ): Promise<UnlistenFn> => {
        captured.push(cb);
        return unlistenMock;
      },
    ),
  };
});

vi.mock('@tauri-apps/api/core', () => ({
  invoke: invokeMock,
}));

vi.mock('@tauri-apps/api/event', () => ({
  listen: listenMock,
}));

import type { UnlistenFn } from '@tauri-apps/api/event';

import {
  IndicatorsRunActiveError,
  useIndicatorsStore,
  type IndicatorsLayout,
  type IndicatorsResult,
} from './indicatorsStore';

const LAYOUT: IndicatorsLayout = {
  anchor_x: 0.0729,
  anchor_y: 0.0648,
  scale: 1,
  support: 6,
  confidence: 0.92,
  source: 'anchor',
};

function completeResult(): IndicatorsResult {
  return {
    metadata: 'C:/videos/metadata.json',
    layout: LAYOUT,
    recalibrated: true,
    events: [
      {
        kind: 'ko',
        start: 12.3,
        end: 13,
        score: 0.88,
        samples: 3,
        match_index: 1,
      },
    ],
    wrote_metadata: true,
  };
}

/** 現在の run の progress listener に 1 件 event を流す。 */
function emit(payload: unknown): void {
  const handler = captured[captured.length - 1];
  if (!handler) throw new Error('no indicators-progress listener registered');
  handler({ payload });
}

/** store の async 継続 (listen → invoke の段) を 1 tick 進める。 */
function flush(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

beforeEach(() => {
  captured.length = 0;
  invokeMock.mockReset();
  // 既定は成功 (個別テストが必要な戻り値 / reject を上書きする)。
  invokeMock.mockResolvedValue(undefined);
  listenMock.mockClear();
  unlistenMock.mockClear();
  // reset() は走行中に throw するので、前のテストが running を残していても
  // 初期化できるよう先に idle へ落としてから reset する。
  useIndicatorsStore.setState({ status: 'idle' });
  useIndicatorsStore.getState().reset();
});

describe('indicatorsStore (#1106 Phase 1)', () => {
  it('初期状態は idle で、listener はまだ張られていない', () => {
    const s = useIndicatorsStore.getState();
    expect(s.status).toBe('idle');
    expect(s.phase).toBeNull();
    expect(s.events).toEqual([]);
    expect(s.error).toBeNull();
    expect(listenMock).not.toHaveBeenCalled();
  });

  it('start は running へ遷移し progress を反映したあと complete で events を入れる', async () => {
    // invoke の解決を手動で制御し、running の間の状態を観察する。
    let resolveInvoke!: (value: IndicatorsResult) => void;
    invokeMock.mockReturnValue(
      new Promise<IndicatorsResult>((resolve) => {
        resolveInvoke = resolve;
      }),
    );

    const promise = useIndicatorsStore
      .getState()
      .start({ metadataPath: 'C:/videos/metadata.json' });
    await flush();

    expect(listenMock).toHaveBeenCalledWith(
      'indicators-progress',
      expect.any(Function),
    );
    expect(invokeMock).toHaveBeenCalledWith('start_indicators', {
      req: { metadataPath: 'C:/videos/metadata.json' },
    });
    expect(useIndicatorsStore.getState().status).toBe('running');

    emit({ phase: 'calibrating' });
    expect(useIndicatorsStore.getState().phase).toBe('calibrating');
    expect(useIndicatorsStore.getState().layout).toBeNull();

    // scanning 開始行 (layout 通知) → 進捗行の順に来る
    emit({ phase: 'scanning', layout: LAYOUT });
    emit({ phase: 'scanning', processed_s: 30, total_s: 944 });

    const during = useIndicatorsStore.getState();
    expect(during.phase).toBe('scanning');
    expect(during.layout).toEqual(LAYOUT);
    expect(during.processedSeconds).toBe(30);
    expect(during.totalSeconds).toBe(944);

    resolveInvoke(completeResult());
    const result = await promise;

    const done = useIndicatorsStore.getState();
    expect(result).toEqual(completeResult());
    expect(done.status).toBe('complete');
    expect(done.phase).toBeNull();
    expect(done.events).toEqual(result.events);
    expect(done.layout).toEqual(LAYOUT);

    // 完了時に購読を畳む (event listener leak 防止)
    expect(unlistenMock).toHaveBeenCalledTimes(1);
  });

  it('invoke が reject すると status=error になり AppError の code を保持する', async () => {
    invokeMock.mockRejectedValue({
      code: 'state.mtime_conflict',
      message: 'conflict: metadata.json was modified externally',
      hint: 'リロードしてください',
    });

    await expect(
      useIndicatorsStore.getState().start({ metadataPath: 'm.json' }),
    ).rejects.toMatchObject({ code: 'state.mtime_conflict' });

    const s = useIndicatorsStore.getState();
    expect(s.status).toBe('error');
    expect(s.error).toEqual({
      code: 'state.mtime_conflict',
      message: 'conflict: metadata.json was modified externally',
      hint: 'リロードしてください',
    });
    // 失敗時も購読は外れる
    expect(unlistenMock).toHaveBeenCalledTimes(1);
  });

  it('reset は idle に戻し events / layout / error を消す', async () => {
    invokeMock.mockResolvedValue(completeResult());
    const promise = useIndicatorsStore
      .getState()
      .start({ metadataPath: 'm.json' });
    await flush();
    emit({ phase: 'scanning', layout: LAYOUT });
    await promise;

    expect(useIndicatorsStore.getState().status).toBe('complete');

    useIndicatorsStore.getState().reset();

    const s = useIndicatorsStore.getState();
    expect(s.status).toBe('idle');
    expect(s.phase).toBeNull();
    expect(s.processedSeconds).toBeNull();
    expect(s.totalSeconds).toBeNull();
    expect(s.layout).toBeNull();
    expect(s.events).toEqual([]);
    expect(s.error).toBeNull();
  });

  // -- 走行中の再入拒否 (run の重なり防止) ---------------------------------

  it('走行中に start を呼ぶと拒否し、2 本目の CLI を spawn しない', async () => {
    let resolveFirst!: (value: IndicatorsResult) => void;
    invokeMock.mockReturnValue(
      new Promise<IndicatorsResult>((resolve) => {
        resolveFirst = resolve;
      }),
    );

    const first = useIndicatorsStore.getState().start({ metadataPath: 'a.json' });
    await flush();
    expect(useIndicatorsStore.getState().status).toBe('running');

    await expect(
      useIndicatorsStore.getState().start({ metadataPath: 'b.json' }),
    ).rejects.toMatchObject({ code: 'indicators.busy' });
    // 2 本目は spawn されない (invoke は 1 本目の 1 回だけ)
    expect(invokeMock).toHaveBeenCalledTimes(1);
    expect(invokeMock).toHaveBeenCalledWith('start_indicators', {
      req: { metadataPath: 'a.json' },
    });
    // 1 本目はそのまま生きている
    expect(useIndicatorsStore.getState().status).toBe('running');

    resolveFirst(completeResult());
    await first;
    expect(useIndicatorsStore.getState().status).toBe('complete');
  });

  it('走行中の reset は拒否し、state を初期化しない', async () => {
    // 走行を終わらせない (決して解決しない invoke)
    invokeMock.mockReturnValue(new Promise(() => {}));
    void useIndicatorsStore.getState().start({ metadataPath: 'a.json' });
    await flush();
    emit({ phase: 'scanning', processed_s: 12, total_s: 100 });
    expect(useIndicatorsStore.getState().processedSeconds).toBe(12);

    expect(() => useIndicatorsStore.getState().reset()).toThrow(
      IndicatorsRunActiveError,
    );

    const s = useIndicatorsStore.getState();
    expect(s.status).toBe('running');
    expect(s.processedSeconds).toBe(12);
    // 購読も外していない (orphan 化させない)
    expect(unlistenMock).not.toHaveBeenCalled();
  });

  it('前の run の listener が遅延して発火しても新しい run の state を汚さない', async () => {
    invokeMock.mockResolvedValue(completeResult());
    await useIndicatorsStore.getState().start({ metadataPath: 'a.json' });
    const staleHandler = captured[0];

    let resolveSecond!: (value: IndicatorsResult) => void;
    invokeMock.mockReturnValue(
      new Promise<IndicatorsResult>((resolve) => {
        resolveSecond = resolve;
      }),
    );
    const second = useIndicatorsStore.getState().start({ metadataPath: 'b.json' });
    await flush();

    // run A の handler が遅れて発火しても run B の progress を書き換えない
    staleHandler({ payload: { phase: 'scanning', processed_s: 99, total_s: 100 } });
    expect(useIndicatorsStore.getState().processedSeconds).toBeNull();
    expect(useIndicatorsStore.getState().phase).toBeNull();

    resolveSecond(completeResult());
    await second;
    expect(useIndicatorsStore.getState().status).toBe('complete');
  });

  // -- listener 登録失敗 ---------------------------------------------------

  it('listen の登録が失敗すると error に遷移し、CLI を起動しない', async () => {
    listenMock.mockImplementationOnce(() =>
      Promise.reject(new Error('listener unavailable')),
    );

    await expect(
      useIndicatorsStore.getState().start({ metadataPath: 'm.json' }),
    ).rejects.toThrow('listener unavailable');

    const s = useIndicatorsStore.getState();
    expect(s.status).toBe('error');
    expect(s.error).toEqual({
      message: 'listener unavailable',
      hint: null,
      code: null,
    });
    expect(invokeMock).not.toHaveBeenCalled();
  });

  // -- spawn 前の cancel ---------------------------------------------------

  it('spawn 前に cancel すると CLI を起動せず、subprocess.cancelled で確定する', async () => {
    let resolveListen!: (unlisten: UnlistenFn) => void;
    listenMock.mockImplementationOnce(
      () =>
        new Promise<UnlistenFn>((resolve) => {
          resolveListen = resolve;
        }),
    );

    const promise = useIndicatorsStore.getState().start({ metadataPath: 'm.json' });
    expect(useIndicatorsStore.getState().status).toBe('running');

    // 購読がまだ解決していない = CLI 未起動。ここで cancel する。
    useIndicatorsStore.getState().cancel();
    expect(invokeMock).toHaveBeenCalledWith('kill_tracked_processes');

    resolveListen(unlistenMock);
    await expect(promise).rejects.toMatchObject({
      code: 'subprocess.cancelled',
    });

    // start_indicators は呼ばれていない (metadata / レポートを書き戻さない)
    expect(invokeMock).not.toHaveBeenCalledWith(
      'start_indicators',
      expect.anything(),
    );
    // 登録済みの購読は畳む
    expect(unlistenMock).toHaveBeenCalledTimes(1);

    const s = useIndicatorsStore.getState();
    expect(s.status).toBe('error');
    expect(s.error?.code).toBe('subprocess.cancelled');
  });

  // -- cancel --------------------------------------------------------------

  it('cancel は running 中に kill_tracked_processes を best effort で呼ぶ', () => {
    invokeMock.mockResolvedValue(undefined);
    useIndicatorsStore.setState({ status: 'running' });

    useIndicatorsStore.getState().cancel();

    expect(invokeMock).toHaveBeenCalledWith('kill_tracked_processes');
    // status は呼び出し側で変えない (走行中の start() の reject が受ける)
    expect(useIndicatorsStore.getState().status).toBe('running');
  });

  it('cancel は idle では何もしない', () => {
    useIndicatorsStore.getState().cancel();
    expect(invokeMock).not.toHaveBeenCalled();
  });
});
