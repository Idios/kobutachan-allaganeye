import { fmtPreciseTime } from '../utils/time';
import styles from './FrameStrip.module.css';

/**
 * #465: a single cached thumbnail entry from
 * `generate_match_thumbnails`. When supplied via `thumbs`, FrameStrip
 * renders the WebP at that timestamp instead of the synthetic shimmer.
 */
export interface FrameStripThumb {
  /** Absolute timestamp (seconds into the source video). */
  t: number;
  /** URL the browser can fetch to render the WebP (e.g. via convertFileSrc). */
  url: string;
}

export interface FrameStripProps {
  /** The (assumed) boundary timestamp. */
  boundaryT: number;
  /** Half-window in seconds. */
  windowSec: number;
  /** Number of frames to render. Default 12. */
  count?: number;
  /** Called when the user clicks a candidate frame. Receives the frame's timestamp. */
  onSelectFrame?: (t: number) => void;
  /**
   * #465: real thumbnails keyed by absolute timestamp. When omitted (Phase 2
   * sample mode) the strip falls back to the synthetic shimmer preview.
   */
  thumbs?: readonly FrameStripThumb[];
}

interface FrameCell {
  t: number;
  isBoundary: boolean;
  brightness: number;
}

function synthesizeFrames(
  centerT: number,
  windowSec: number,
  count: number,
): FrameCell[] {
  if (count <= 0) return [];
  const times: number[] = [];
  const denom = count === 1 ? 1 : count - 1;
  for (let i = 0; i < count; i++) {
    times.push(centerT - windowSec + (i / denom) * windowSec * 2);
  }
  // Mark the single frame whose timestamp is closest to `centerT` as the
  // boundary. This is more robust than a window-size threshold (which breaks
  // when windowSec and count don't divide cleanly — see #464 FrameStrip tests).
  let closestIdx = 0;
  let closestDist = Infinity;
  for (let i = 0; i < times.length; i++) {
    const d = Math.abs(times[i] - centerT);
    if (d < closestDist) {
      closestDist = d;
      closestIdx = i;
    }
  }
  return times.map((t, i) => {
    const d = Math.abs(t - centerT);
    const brightness = d < 1.2 ? 0.08 : d < 2.5 ? 0.35 : 0.85;
    return { t, isBoundary: i === closestIdx, brightness };
  });
}

/**
 * ±windowSec strip of candidate boundary frames. Used on the preview screen to
 * offer the user alternatives close to the detected boundary. Each cell emits
 * a timestamp on click so the parent can snap the IN / OUT point.
 *
 * Mirror of FrameStrip in docs/design/bundle/project/variants/aether-preview.jsx.
 */
function nearestThumbUrl(
  thumbs: readonly FrameStripThumb[] | undefined,
  t: number,
): string | null {
  if (!thumbs || thumbs.length === 0) return null;
  let bestIdx = 0;
  let bestDist = Infinity;
  for (let i = 0; i < thumbs.length; i++) {
    const d = Math.abs(thumbs[i].t - t);
    if (d < bestDist) {
      bestDist = d;
      bestIdx = i;
    }
  }
  return thumbs[bestIdx].url;
}

export function FrameStrip({
  boundaryT,
  windowSec,
  count = 12,
  onSelectFrame,
  thumbs,
}: FrameStripProps) {
  const frames = synthesizeFrames(boundaryT, windowSec, count);
  return (
    <div className={styles.strip} data-testid="frame-strip">
      {frames.map((f, i) => {
        const thumbUrl = nearestThumbUrl(thumbs, f.t);
        return (
          <button
            key={i}
            type="button"
            onClick={() => onSelectFrame?.(f.t)}
            className={`${styles.cell}${f.isBoundary ? ` ${styles.cellBoundary}` : ''}`}
            aria-label={`frame ${fmtPreciseTime(f.t)}`}
            data-boundary={f.isBoundary ? 'true' : 'false'}
          >
            {thumbUrl ? (
              <img
                className={styles.thumb}
                src={thumbUrl}
                alt=""
                loading="lazy"
                draggable={false}
              />
            ) : (
              <div
                className={styles.shimmer}
                style={{
                  background: `radial-gradient(ellipse at ${40 + i * 3}% ${50 + (i % 3) * 10}%, rgba(232, 196, 122, ${f.brightness * 0.6}), transparent 60%)`,
                  backgroundColor: `rgba(var(--ae-gold-rgb), ${f.brightness * 0.4})`,
                }}
              />
            )}
            {!thumbUrl && f.brightness < 0.15 && (
              <div className={styles.blackOverlay} />
            )}
            {f.isBoundary && <div className={styles.boundaryBar} />}
            <div className={styles.label}>
              {fmtPreciseTime(f.t).split('.')[0].split(':').slice(-2).join(':')}
            </div>
          </button>
        );
      })}
    </div>
  );
}
