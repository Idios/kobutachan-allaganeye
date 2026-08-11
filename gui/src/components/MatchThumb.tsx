import { convertFileSrc, invoke } from '@tauri-apps/api/core';
import { useEffect, useState } from 'react';

import styles from './MatchThumb.module.css';

interface ThumbnailEntry {
  t_seconds: number;
  file_path: string;
}

export interface MatchThumbProps {
  index: number;
  /**
   * #465 review (A): video file path used to generate a real WebP thumbnail
   * via the Rust `generate_match_thumbnails` Tauri command. When omitted
   * (sample mode without a real video, or before the user picks a file),
   * MatchThumb renders the deterministic gradient fallback so the layout
   * stays identical.
   */
  videoPath?: string | null;
  /**
   * Boundary timestamp in seconds. When `videoPath` is provided this is the
   * frame captured for the thumbnail (default: 0). Ignored without
   * `videoPath`.
   */
  startTime?: number;
  width?: number | string;
  height?: number | string;
}

/**
 * Match thumbnail. Phase 3 (#465) attempts to render a real WebP frame
 * captured by ffmpeg via `generate_match_thumbnails`; the gradient
 * placeholder (mirrored from `docs/design/bundle/project/shared/common.jsx`)
 * is kept as a fallback for sample mode and any failure path so the layout
 * never collapses.
 *
 * Hits the existing thumbnail cache (`<install dir>/cache/<hash>/thumbs/`,
 * resolved by `thumb_cache_dir()` on the Rust side from `current_exe().parent()`
 * -- not the user profile, per the Portable ZIP philosophy; dev =
 * `target/debug/cache/...`),
 * so repeat renders re-use generated frames without re-spawning ffmpeg.
 */
export function MatchThumb({
  index,
  videoPath,
  startTime,
  width = 96,
  height = 54,
}: MatchThumbProps) {
  const [thumbUrl, setThumbUrl] = useState<string | null>(null);

  useEffect(() => {
    // videoPath が無い (sample mode) / 初期化前の場合は何もせず placeholder
    // 描画に任せる。state を直接 reset すると `set-state-in-effect` ESLint
    // が立つので、early return で処理しない。
    if (!videoPath) return;
    const t = startTime ?? 0;
    let cancelled = false;
    (async () => {
      try {
        const result = await invoke<ThumbnailEntry[]>(
          'generate_match_thumbnails',
          {
            videoPath,
            matchIndex: index,
            boundaryTSeconds: t,
            windowSeconds: 0,
            count: 1,
          },
        );
        if (cancelled) return;
        if (result.length > 0) {
          setThumbUrl(convertFileSrc(result[0].file_path));
        }
      } catch {
        // Fall back to placeholder; list の描画を止めないよう error は飲む
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [videoPath, index, startTime]);

  if (thumbUrl) {
    return (
      <div
        className={styles.thumb}
        style={{
          width,
          height,
          backgroundImage: `url(${thumbUrl})`,
          backgroundSize: 'cover',
          backgroundPosition: 'center',
        }}
        role="img"
        aria-label={`match ${index} thumbnail`}
        data-testid="match-thumb"
        data-real="true"
      />
    );
  }

  // Fallback: deterministic pseudo-art derived from the match index.
  // Mirrors the original Phase 2 placeholder so layout stays identical.
  const hue = (index * 47) % 360;
  const shimmerX = 30 + ((index * 13) % 40);
  const shimmerY = 40 + ((index * 7) % 20);
  return (
    <div
      className={styles.thumb}
      style={{
        width,
        height,
        backgroundImage: `linear-gradient(135deg, oklch(0.25 0.08 ${hue}), oklch(0.15 0.05 ${hue + 60}))`,
      }}
      role="img"
      aria-label={`match ${index} thumbnail`}
      data-testid="match-thumb"
      data-hue={hue}
      data-real="false"
    >
      <div className={styles.hudBar} />
      <div className={styles.hudDot} />
      <div className={styles.hudRow}>
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className={styles.hudCell} />
        ))}
      </div>
      <div
        className={styles.shimmer}
        style={{
          background: `radial-gradient(circle at ${shimmerX}% ${shimmerY}%, rgba(255, 220, 100, 0.35), transparent 40%)`,
        }}
      />
    </div>
  );
}
