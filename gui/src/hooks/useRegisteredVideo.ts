/**
 * `register_video` で動画 URL を取得する (#465 / #1139)。
 *
 * 元は 3 画面 (PreviewScreen / MinimapScreen / ClipRangeView) に同じ effect が
 * あった。**返るのは axum が配信する HTTP URL** なので、そのまま `<video src>` に
 * 渡す (`convertFileSrc` に通すと asset プロトコルへ書き換えられて読めない)。
 *
 * 失敗時は `toErrorState` を通した message を返す (#678: Tauri の AppError は
 * struct で返るので `String(e)` は "[object Object]" になる)。
 */
import { invoke } from '@tauri-apps/api/core';
import { useEffect, useState } from 'react';

import { toErrorState } from '../lib/appError';

/** `register_video` の戻り値 (Rust 側 `RegisteredVideo`)。 */
export interface RegisteredVideo {
  url: string;
  token?: string;
}

export interface RegisteredVideoState {
  videoUrl: string | null;
  videoError: string | null;
}

export function useRegisteredVideo(source: string | null): RegisteredVideoState {
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [videoError, setVideoError] = useState<string | null>(null);

  useEffect(() => {
    if (!source) return;
    let cancelled = false;
    (async () => {
      try {
        const registered = await invoke<RegisteredVideo>('register_video', {
          path: source,
        });
        if (!cancelled) {
          setVideoUrl(registered.url);
          setVideoError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setVideoUrl(null);
          setVideoError(toErrorState(e).message);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [source]);

  return { videoUrl, videoError };
}
