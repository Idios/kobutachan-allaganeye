import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { invokeMock } = vi.hoisted(() => ({ invokeMock: vi.fn() }));

vi.mock('@tauri-apps/api/core', () => ({ invoke: invokeMock }));

import { useRegisteredVideo } from './useRegisteredVideo';

beforeEach(() => {
  invokeMock.mockReset();
});

describe('useRegisteredVideo', () => {
  it('does not register anything without a source', () => {
    const { result } = renderHook(() => useRegisteredVideo(null));

    expect(invokeMock).not.toHaveBeenCalled();
    expect(result.current.videoUrl).toBeNull();
    expect(result.current.videoError).toBeNull();
  });

  it('exposes the HTTP URL returned by register_video', async () => {
    invokeMock.mockResolvedValue({
      url: 'http://127.0.0.1:0/video/token',
      token: 'token',
    });

    const { result } = renderHook(() => useRegisteredVideo('E:/v.mp4'));

    await waitFor(() =>
      expect(result.current.videoUrl).toBe('http://127.0.0.1:0/video/token'),
    );
    expect(invokeMock).toHaveBeenCalledWith('register_video', {
      path: 'E:/v.mp4',
    });
    expect(result.current.videoError).toBeNull();
  });

  // #678: Tauri の AppError は struct で返る。`String(e)` だと
  // "[object Object]" になるため、toErrorState を通した message を返す。
  it('normalises an AppError struct into its message (#678)', async () => {
    invokeMock.mockRejectedValue({
      code: 'io.read_failed',
      message: 'video not found',
      hint: 'check the path',
    });

    const { result } = renderHook(() => useRegisteredVideo('E:/missing.mp4'));

    await waitFor(() => expect(result.current.videoError).toBe('video not found'));
    expect(result.current.videoUrl).toBeNull();
  });

  it('falls back to the Error message for plain errors', async () => {
    invokeMock.mockRejectedValue(new Error('boom'));

    const { result } = renderHook(() => useRegisteredVideo('E:/v.mp4'));

    await waitFor(() => expect(result.current.videoError).toBe('boom'));
  });

  it('re-registers when the source changes', async () => {
    invokeMock
      .mockResolvedValueOnce({ url: 'http://127.0.0.1:0/video/one' })
      .mockResolvedValueOnce({ url: 'http://127.0.0.1:0/video/two' });

    const { result, rerender } = renderHook(
      ({ source }: { source: string }) => useRegisteredVideo(source),
      { initialProps: { source: 'E:/one.mp4' } },
    );
    await waitFor(() =>
      expect(result.current.videoUrl).toBe('http://127.0.0.1:0/video/one'),
    );

    rerender({ source: 'E:/two.mp4' });
    await waitFor(() =>
      expect(result.current.videoUrl).toBe('http://127.0.0.1:0/video/two'),
    );
    expect(invokeMock).toHaveBeenCalledTimes(2);
  });
});
