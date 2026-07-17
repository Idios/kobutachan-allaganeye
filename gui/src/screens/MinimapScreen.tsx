/**
 * MinimapScreen — video pane + match scrubber for minimap region proposal.
 * (#893 Phase 2 minimap crop GUI integration)
 *
 * Shows the source video seeked to the midpoint of the selected eligible
 * match, with a <select> to switch between matches, a drag-select overlay
 * to pick the region visually, and 4 numeric X/Y/W/H inputs.
 */
import { invoke } from '@tauri-apps/api/core';
import { useEffect, useMemo, useRef, useState } from 'react';

import { SampleModeBanner } from '../components/SampleModeBanner';
import { useAppStateStore } from '../state/appStateStore';
import { useMetadataStore } from '../state/metadataStore';
import { elementRectToSourcePx, validateRegionPx, type RegionPx } from '../utils/region';
import styles from './MinimapScreen.module.css';

export function MinimapScreen() {
  const metadata = useMetadataStore((s) => s.metadata);
  const navigate = useAppStateStore((s) => s.navigate);
  const selectedVideoPath = useAppStateStore((s) => s.selectedVideoPath);
  const videoSource = selectedVideoPath ?? metadata?.source ?? null;

  const eligible = useMemo(
    () => (metadata?.matches ?? []).filter((m) => !m.post_match && m.type_override !== 'skip'),
    [metadata],
  );

  const [frameMatchIndex, setFrameMatchIndex] = useState<number | null>(
    eligible[0]?.index ?? null,
  );
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  // Region state
  const [region, setRegion] = useState<RegionPx | null>(null);
  const [regionError, setRegionError] = useState<string | null>(null);

  // Drag state (element-space client coords and overlay-relative rect)
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null);
  const [dragCur, setDragCur] = useState<{ x: number; y: number } | null>(null);
  // Overlay-relative rect for visual rubber band (updated in onMouseMove)
  const [dragRect, setDragRect] = useState<{ left: number; top: number; width: number; height: number } | null>(null);

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
  }, [frameMatchIndex, videoUrl, eligible]);

  /** Get frame dimensions from the video element intrinsic size (0 until loaded). */
  const getFrameDims = (): { frameW: number; frameH: number } => {
    const v = videoRef.current;
    if (v && v.videoWidth > 0 && v.videoHeight > 0) {
      return { frameW: v.videoWidth, frameH: v.videoHeight };
    }
    return { frameW: 0, frameH: 0 };
  };

  const onOverlayMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    e.preventDefault();
    const overlayRect = e.currentTarget.getBoundingClientRect();
    const start = { x: e.clientX, y: e.clientY };
    setDragStart(start);
    setDragCur(start);
    setDragRect({
      left: e.clientX - overlayRect.left,
      top: e.clientY - overlayRect.top,
      width: 0,
      height: 0,
    });
  };

  const onOverlayMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!dragStart) return;
    const overlayRect = e.currentTarget.getBoundingClientRect();
    setDragCur({ x: e.clientX, y: e.clientY });
    setDragRect({
      left: Math.min(dragStart.x, e.clientX) - overlayRect.left,
      top: Math.min(dragStart.y, e.clientY) - overlayRect.top,
      width: Math.abs(e.clientX - dragStart.x),
      height: Math.abs(e.clientY - dragStart.y),
    });
  };

  const onOverlayMouseUp = () => {
    const v = videoRef.current;
    if (!v || !dragStart || !dragCur) return;
    const rect = v.getBoundingClientRect();
    const sel = {
      x: Math.min(dragStart.x, dragCur.x) - rect.left,
      y: Math.min(dragStart.y, dragCur.y) - rect.top,
      w: Math.abs(dragCur.x - dragStart.x),
      h: Math.abs(dragCur.y - dragStart.y),
    };
    const px = elementRectToSourcePx(sel, { width: rect.width, height: rect.height }, v.videoWidth, v.videoHeight);
    const { frameW, frameH } = getFrameDims();
    setRegion(px);
    if (frameW > 0 && frameH > 0) {
      setRegionError(validateRegionPx(px, frameW, frameH));
    }
    setDragStart(null);
    setDragCur(null);
    setDragRect(null);
  };

  /** Update a single numeric field from the inputs */
  const onFieldChange = (field: keyof RegionPx, rawValue: string) => {
    const num = parseInt(rawValue, 10);
    const value = Number.isFinite(num) ? num : 0;
    const next: RegionPx = { ...(region ?? { x: 0, y: 0, w: 0, h: 0 }), [field]: value };
    setRegion(next);
    const { frameW, frameH } = getFrameDims();
    if (frameW > 0 && frameH > 0) {
      setRegionError(validateRegionPx(next, frameW, frameH));
    } else {
      // No frame dims yet — only validate what we can
      setRegionError(validateRegionPx(next, Infinity, Infinity));
    }
  };

  const r = region ?? { x: 0, y: 0, w: 0, h: 0 };

  return (
    <div className={styles.screen} data-testid="minimap-screen">
      <SampleModeBanner />
      <button type="button" onClick={() => navigate('complete')}>
        ◀ 一覧へ
      </button>
      <div className={styles.videoPane}>
        {videoUrl ? (
          <div className={styles.videoWrapper}>
            <video
              ref={videoRef}
              src={videoUrl}
              data-testid="minimap-video"
              preload="metadata"
              playsInline
            />
            {/* Drag-select overlay */}
            <div
              className={styles.dragOverlay}
              onMouseDown={onOverlayMouseDown}
              onMouseMove={onOverlayMouseMove}
              onMouseUp={onOverlayMouseUp}
              onMouseLeave={onOverlayMouseUp}
              aria-hidden="true"
            >
              {dragRect && (
                <div
                  className={styles.dragRect}
                  style={{
                    left: dragRect.left,
                    top: dragRect.top,
                    width: dragRect.width,
                    height: dragRect.height,
                  }}
                />
              )}
            </div>
          </div>
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

      {/* Numeric region inputs */}
      <div className={styles.regionInputs}>
        <label className={styles.regionField}>
          <span>X</span>
          <input
            type="number"
            aria-label="region x"
            value={r.x}
            min={0}
            onChange={(e) => onFieldChange('x', e.target.value)}
          />
        </label>
        <label className={styles.regionField}>
          <span>Y</span>
          <input
            type="number"
            aria-label="region y"
            value={r.y}
            min={0}
            onChange={(e) => onFieldChange('y', e.target.value)}
          />
        </label>
        <label className={styles.regionField}>
          <span>W</span>
          <input
            type="number"
            aria-label="region width"
            value={r.w}
            min={0}
            onChange={(e) => onFieldChange('w', e.target.value)}
          />
        </label>
        <label className={styles.regionField}>
          <span>H</span>
          <input
            type="number"
            aria-label="region height"
            value={r.h}
            min={0}
            onChange={(e) => onFieldChange('h', e.target.value)}
          />
        </label>
      </div>
      {regionError && (
        <div className={styles.regionError} role="alert">
          {regionError}
        </div>
      )}
    </div>
  );
}
