/**
 * MinimapScreen — video pane + match scrubber for minimap region proposal.
 * (#893 Phase 2 minimap crop GUI integration)
 *
 * Shows the source video seeked to the midpoint of the selected eligible
 * match, with a <select> to switch between matches.
 */
import { invoke } from '@tauri-apps/api/core';
import { useEffect, useRef, useState } from 'react';

import { SampleModeBanner } from '../components/SampleModeBanner';
import { useAppStateStore } from '../state/appStateStore';
import { useMetadataStore } from '../state/metadataStore';
import styles from './MinimapScreen.module.css';

export function MinimapScreen() {
  const metadata = useMetadataStore((s) => s.metadata);
  const navigate = useAppStateStore((s) => s.navigate);
  const selectedVideoPath = useAppStateStore((s) => s.selectedVideoPath);
  const videoSource = selectedVideoPath ?? metadata?.source ?? null;

  const eligible = (metadata?.matches ?? []).filter(
    (m) => !m.post_match && m.type_override !== 'skip',
  );

  const [frameMatchIndex, setFrameMatchIndex] = useState<number | null>(
    eligible[0]?.index ?? null,
  );
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  // Register the video source with the Tauri backend (same pattern as PreviewScreen:266-293)
  useEffect(() => {
    if (!videoSource) return;
    let cancelled = false;
    (async () => {
      try {
        const reg = await invoke<{ url: string; token: string }>('register_video', {
          path: videoSource,
        });
        if (!cancelled) setVideoUrl(reg.url);
      } catch {
        if (!cancelled) setVideoUrl(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [videoSource]);

  // Seek to the midpoint of the selected match whenever it or the URL changes
  useEffect(() => {
    const v = videoRef.current;
    const m = eligible.find((x) => x.index === frameMatchIndex);
    if (v && m) {
      const start = m.edited?.start_time ?? m.start_time;
      const end = m.edited?.end_time ?? m.end_time;
      const mid = (start + end) / 2;
      try {
        v.currentTime = mid;
      } catch {
        // jsdom video has no real currentTime — ignore in tests
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frameMatchIndex, videoUrl]);

  return (
    <div className={styles.screen} data-testid="minimap-screen">
      <SampleModeBanner />
      <button type="button" onClick={() => navigate('complete')}>
        ◀ 一覧へ
      </button>
      <div className={styles.videoPane}>
        {videoUrl ? (
          <video
            ref={videoRef}
            src={videoUrl}
            data-testid="minimap-video"
            preload="metadata"
            playsInline
          />
        ) : (
          <div className={styles.loading}>loading video…</div>
        )}
      </div>
      <select
        aria-label="frame match"
        value={frameMatchIndex ?? ''}
        onChange={(e) => setFrameMatchIndex(Number(e.target.value))}
      >
        {eligible.map((m) => (
          <option key={m.index} value={m.index}>
            {`match ${String(m.index).padStart(3, '0')}`}
          </option>
        ))}
      </select>
    </div>
  );
}
