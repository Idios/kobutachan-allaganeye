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
  ClipsRunActiveError,
  useClipsStore,
  type ClipsProgressPayload,
  type ClipsResult,
} from './clipsStore';

function clipsResult(): ClipsResult {
  return {
    success: 1,
    failure: 0,
    skipped: 0,
    cancelled: false,
    output_paths: ['C:/out/clips/clip_001_ko_00-03-10.mp4'],
  };
}

/** 現在の run の progress listener に 1 件 event を流す。 */
function emit(payload: ClipsProgressPayload): void {
  const handler = captured[captured.length - 1];
  if (!handler) throw new Error('no clips-progress listener registered');
  handler({ payload });
}

/** store の async 継続 (listen -> invoke の段) を 1 tick 進める。 */
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
  useClipsStore.setState({ status: 'idle' });
  useClipsStore.getState().reset();
});

describe('clipsStore (#1131 Phase B1)', () => {
  it('初期状態は idle で、listener はまだ張られていない', () => {
    const s = useClipsStore.getState();
    expect(s.status).toBe('idle');
    expect(s.metadataPath).toBeNull();
    expect(s.progress).toBeNull();
    expect(s.result).toBeNull();
    expect(s.error).toBeNull();
    expect(listenMock).not.toHaveBeenCalled();
  });

  it('start は running へ遷移し progress を反映したあと complete で result を入れる', async () => {
    let resolveInvoke!: (value: ClipsResult) => void;
    invokeMock.mockReturnValue(
      new Promise<ClipsResult>((resolve) => {
        resolveInvoke = resolve;
      }),
    );

    const promise = useClipsStore.getState().start({
      metadataPath: 'C:/videos/metadata.json',
      eventIndexes: [3],
      pre: 5,
      post: 5,
    });
    await flush();

    expect(listenMock).toHaveBeenCalledWith(
      'clips-progress',
      expect.any(Function),
    );
    expect(invokeMock).toHaveBeenCalledWith('start_clips', {
      req: {
        metadataPath: 'C:/videos/metadata.json',
        eventIndexes: [3],
        pre: 5,
        post: 5,
      },
    });
    expect(useClipsStore.getState().status).toBe('running');

    emit({ match_index: 1, percent: 42.5, stage: 'encoding' });
    expect(useClipsStore.getState().progress).toEqual({
      match_index: 1,
      percent: 42.5,
      stage: 'encoding',
    });

    emit({ match_index: 1, percent: 100, stage: 'done' });
    expect(useClipsStore.getState().progress?.stage).toBe('done');

    resolveInvoke(clipsResult());
    const result = await promise;

    const done = useClipsStore.getState();
    expect(result).toEqual(clipsResult());
    expect(done.status).toBe('complete');
    expect(done.result?.output_paths).toEqual([
      'C:/out/clips/clip_001_ko_00-03-10.mp4',
    ]);
    // 完了時に購読を畳む (event listener leak 防止)
    expect(unlistenMock).toHaveBeenCalledTimes(1);
  });

  it('invoke が reject すると status=error になり AppError の code を保持する', async () => {
    invokeMock.mockRejectedValue({
      code: 'validation.range_invalid',
      message: '1 clip output(s) already exist; pass --overwrite to replace them',
      hint: '入力された数値が許容範囲外です。フォーム下のヒント表示を確認してください',
    });

    await expect(
      useClipsStore.getState().start({ metadataPath: 'm.json' }),
    ).rejects.toMatchObject({ code: 'validation.range_invalid' });

    const s = useClipsStore.getState();
    expect(s.status).toBe('error');
    expect(s.error?.code).toBe('validation.range_invalid');
    expect(s.error?.message).toContain('pass --overwrite');
    // 失敗時も購読は外れる
    expect(unlistenMock).toHaveBeenCalledTimes(1);
  });

  it('reset は idle に戻し progress / result / error を消す', async () => {
    invokeMock.mockResolvedValue(clipsResult());
    const promise = useClipsStore.getState().start({ metadataPath: 'm.json' });
    await flush();
    emit({ match_index: 1, percent: 100, stage: 'done' });
    await promise;

    expect(useClipsStore.getState().status).toBe('complete');

    useClipsStore.getState().reset();

    const s = useClipsStore.getState();
    expect(s.status).toBe('idle');
    expect(s.metadataPath).toBeNull();
    expect(s.progress).toBeNull();
    expect(s.result).toBeNull();
    expect(s.error).toBeNull();
  });

  it('start は対象 metadata.json を metadataPath に記録し、complete 後も保持する', async () => {
    invokeMock.mockResolvedValue(clipsResult());
    await useClipsStore
      .getState()
      .start({ metadataPath: 'C:/a/metadata.json' });

    const s = useClipsStore.getState();
    expect(s.status).toBe('complete');
    expect(s.metadataPath).toBe('C:/a/metadata.json');
  });

  it('error に落ちても metadataPath は保持する (同じ対象で再実行できる)', async () => {
    invokeMock.mockRejectedValue(
      new Error('python clips subprocess exited unexpectedly'),
    );
    await expect(
      useClipsStore.getState().start({ metadataPath: 'C:/b/metadata.json' }),
    ).rejects.toThrow();

    const s = useClipsStore.getState();
    expect(s.status).toBe('error');
    expect(s.metadataPath).toBe('C:/b/metadata.json');
  });

  // -- 走行中の再入拒否 (run の重なり防止) ---------------------------------

  it('走行中に start を呼ぶと拒否し、2 本目の CLI を spawn しない', async () => {
    let resolveFirst!: (value: ClipsResult) => void;
    invokeMock.mockReturnValue(
      new Promise<ClipsResult>((resolve) => {
        resolveFirst = resolve;
      }),
    );

    const first = useClipsStore.getState().start({ metadataPath: 'a.json' });
    await flush();
    expect(useClipsStore.getState().status).toBe('running');

    await expect(
      useClipsStore.getState().start({ metadataPath: 'b.json' }),
    ).rejects.toMatchObject({ code: 'clips.busy' });
    expect(invokeMock).toHaveBeenCalledTimes(1);
    expect(useClipsStore.getState().status).toBe('running');

    resolveFirst(clipsResult());
    await first;
    expect(useClipsStore.getState().status).toBe('complete');
  });

  it('走行中の reset は拒否し、state を初期化しない', async () => {
    invokeMock.mockReturnValue(new Promise(() => {}));
    void useClipsStore.getState().start({ metadataPath: 'a.json' });
    await flush();
    emit({ match_index: 2, percent: 10, stage: 'encoding' });
    expect(useClipsStore.getState().progress?.match_index).toBe(2);

    expect(() => useClipsStore.getState().reset()).toThrow(ClipsRunActiveError);

    const s = useClipsStore.getState();
    expect(s.status).toBe('running');
    expect(s.progress?.match_index).toBe(2);
    // 購読も外していない (orphan 化させない)
    expect(unlistenMock).not.toHaveBeenCalled();
  });

  it('前の run の listener が遅延して発火しても新しい run の state を汚さない', async () => {
    invokeMock.mockResolvedValue(clipsResult());
    await useClipsStore.getState().start({ metadataPath: 'a.json' });
    const staleHandler = captured[0];

    let resolveSecond!: (value: ClipsResult) => void;
    invokeMock.mockReturnValue(
      new Promise<ClipsResult>((resolve) => {
        resolveSecond = resolve;
      }),
    );
    const second = useClipsStore.getState().start({ metadataPath: 'b.json' });
    await flush();

    staleHandler({
      payload: { match_index: 9, percent: 99, stage: 'encoding' },
    });
    expect(useClipsStore.getState().progress).toBeNull();

    resolveSecond(clipsResult());
    await second;
    expect(useClipsStore.getState().status).toBe('complete');
  });

  // -- listener 登録失敗 ---------------------------------------------------

  it('listen の登録が失敗すると error に遷移し、CLI を起動しない', async () => {
    listenMock.mockImplementationOnce(() =>
      Promise.reject(new Error('listener unavailable')),
    );

    await expect(
      useClipsStore.getState().start({ metadataPath: 'm.json' }),
    ).rejects.toThrow('listener unavailable');

    const s = useClipsStore.getState();
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

    const promise = useClipsStore.getState().start({ metadataPath: 'm.json' });
    expect(useClipsStore.getState().status).toBe('running');

    // 購読がまだ解決していない = CLI 未起動。ここで cancel する。
    useClipsStore.getState().cancel();
    expect(invokeMock).toHaveBeenCalledWith('kill_tracked_processes');

    resolveListen(unlistenMock);
    await expect(promise).rejects.toMatchObject({
      code: 'subprocess.cancelled',
    });

    // start_clips は呼ばれていない (クリップを書き出さない)
    expect(invokeMock).not.toHaveBeenCalledWith(
      'start_clips',
      expect.anything(),
    );
    expect(unlistenMock).toHaveBeenCalledTimes(1);

    const s = useClipsStore.getState();
    expect(s.status).toBe('error');
    expect(s.error?.code).toBe('subprocess.cancelled');
  });

  // -- cancel --------------------------------------------------------------

  it('cancel は running 中に kill_tracked_processes を best effort で呼ぶ', () => {
    invokeMock.mockResolvedValue(undefined);
    useClipsStore.setState({ status: 'running' });

    useClipsStore.getState().cancel();

    expect(invokeMock).toHaveBeenCalledWith('kill_tracked_processes');
    // status は呼び出し側で変えない (走行中の start() の reject が受ける)
    expect(useClipsStore.getState().status).toBe('running');
  });

  it('cancel は idle では何もしない', () => {
    useClipsStore.getState().cancel();
    expect(invokeMock).not.toHaveBeenCalled();
  });
});
