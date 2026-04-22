import { fmtPreciseTime } from '../utils/time';
import styles from './FrameStrip.module.css';

export interface FrameStripProps {
  /** The (assumed) boundary timestamp. */
  boundaryT: number;
  /** Half-window in seconds. */
  windowSec: number;
  /** Number of frames to render. Default 12. */
  count?: number;
  /** Called when the user clicks a candidate frame. Receives the frame's timestamp. */
  onSelectFrame?: (t: number) => void;
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
export function FrameStrip({
  boundaryT,
  windowSec,
  count = 12,
  onSelectFrame,
}: FrameStripProps) {
  const frames = synthesizeFrames(boundaryT, windowSec, count);
  return (
    <div className={styles.strip} data-testid="frame-strip">
      {frames.map((f, i) => (
        <button
          key={i}
          type="button"
          onClick={() => onSelectFrame?.(f.t)}
          className={`${styles.cell}${f.isBoundary ? ` ${styles.cellBoundary}` : ''}`}
          aria-label={`frame ${fmtPreciseTime(f.t)}`}
          data-boundary={f.isBoundary ? 'true' : 'false'}
        >
          <div
            className={styles.shimmer}
            style={{
              background: `radial-gradient(ellipse at ${40 + i * 3}% ${50 + (i % 3) * 10}%, rgba(232, 196, 122, ${f.brightness * 0.6}), transparent 60%)`,
              backgroundColor: `rgba(var(--ae-gold-rgb), ${f.brightness * 0.4})`,
            }}
          />
          {f.brightness < 0.15 && <div className={styles.blackOverlay} />}
          {f.isBoundary && <div className={styles.boundaryBar} />}
          <div className={styles.label}>
            {fmtPreciseTime(f.t).split('.')[0].split(':').slice(-2).join(':')}
          </div>
        </button>
      ))}
    </div>
  );
}
