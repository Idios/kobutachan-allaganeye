import { useMemo } from 'react';

import { DisabledTooltip } from './DisabledTooltip';
import { buildBrightnessPath, findBlackoutRegions } from '../utils/brightness';
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
  /**
   * When true, all frame buttons are disabled (sample mode). Default false.
   * Backward-compat: omitting this prop leaves all buttons enabled.
   */
  disabled?: boolean;
  /**
   * Tooltip reason shown on each frame button when disabled.
   * Only relevant when disabled=true.
   */
  disabledReason?: string;
  /**
   * #645 Chapter 2 (overlay pivot): brightness samples for the strip's
   * time span (typically ±windowSec around boundaryT). Optional — when
   * omitted, the SVG overlay is not rendered (back-compat with existing
   * call sites).
   *
   * Samples are expected to be in [0, 255] (255 = bright, 0 = black) and
   * evenly distributed across `brightnessWindowSeconds`.
   */
  brightnessSamples?: readonly number[];
  /**
   * #645 Chapter 2: detection threshold (brightness ≤ threshold = blackout).
   * Default 15. Drawn as a dashed horizontal line across the overlay.
   */
  brightnessThreshold?: number;
  /**
   * #645 Chapter 2: total seconds the brightness samples span (= 2 *
   * windowSec usually). Used for blackout band x-axis mapping.
   */
  brightnessWindowSeconds?: number;
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
  disabled = false,
  disabledReason = '',
  brightnessSamples,
  brightnessThreshold = 15,
  brightnessWindowSeconds,
}: FrameStripProps) {
  const frames = synthesizeFrames(boundaryT, windowSec, count);

  // #645 Chapter 2 (overlay pivot): SVG overlay geometry. viewBox 0 0 200 36
  // is identical to the previous standalone MicroTimeline so the same
  // brightness/threshold/blackout helpers can be reused unchanged. The SVG
  // uses preserveAspectRatio="none" + width:100% so the X axis stretches to
  // fill the strip; only lines / paths / rects are rendered (text would
  // distort horizontally — see the deleted MicroTimeline comment for
  // background) and pointer-events: none on the overlay class lets clicks
  // pass through to the underlying thumbnail buttons.
  const overlayWidth = 200;
  const overlayHeight = 36;
  const overlayWindowSeconds = brightnessWindowSeconds ?? windowSec * 2;
  const overlayPath = useMemo(
    () =>
      brightnessSamples
        ? buildBrightnessPath(brightnessSamples, overlayWidth, overlayHeight)
        : '',
    [brightnessSamples],
  );
  const overlayBlackouts = useMemo(
    () =>
      brightnessSamples
        ? findBlackoutRegions(
            brightnessSamples,
            overlayWindowSeconds,
            brightnessThreshold,
          )
        : [],
    [brightnessSamples, overlayWindowSeconds, brightnessThreshold],
  );
  const overlayThresholdY =
    overlayHeight - (brightnessThreshold / 255) * overlayHeight;

  return (
    <div className={styles.strip} data-testid="frame-strip">
      {frames.map((f, i) => {
        const thumbUrl = nearestThumbUrl(thumbs, f.t);
        return (
          <div key={i} className={styles.cellSlot}>
            <DisabledTooltip disabled={disabled} reason={disabledReason}>
              {(p) => (
                <button
                  type="button"
                  onClick={() => onSelectFrame?.(f.t)}
                  className={`${styles.cell}${f.isBoundary ? ` ${styles.cellBoundary}` : ''}`}
                  aria-label={`frame ${fmtPreciseTime(f.t)}`}
                  data-boundary={f.isBoundary ? 'true' : 'false'}
                  disabled={disabled}
                  {...p}
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
              )}
            </DisabledTooltip>
          </div>
        );
      })}
      {brightnessSamples && (
        <svg
          className={styles.brightnessOverlay}
          viewBox={`0 0 ${overlayWidth} ${overlayHeight}`}
          preserveAspectRatio="none"
          data-testid="frame-strip-brightness-overlay"
          aria-hidden="true"
        >
          {/* threshold line。`vector-effect="non-scaling-stroke"` で viewBox stretch
              による線の細り化を回避し、CSS stroke-width 通りの px 太さを保つ。 */}
          <line
            x1={0}
            x2={overlayWidth}
            y1={overlayThresholdY}
            y2={overlayThresholdY}
            className={styles.thresholdLine}
            vectorEffect="non-scaling-stroke"
            data-testid="threshold-line"
          />

          {/* blackout bands */}
          {overlayBlackouts.map((r, i) => {
            const x1 = (r.start / overlayWindowSeconds) * overlayWidth;
            const x2 = (r.end / overlayWindowSeconds) * overlayWidth;
            return (
              <rect
                key={i}
                x={x1}
                y={0}
                width={Math.max(1.5, x2 - x1)}
                height={overlayHeight}
                className={styles.blackoutBand}
                data-testid="blackout-band"
              />
            );
          })}

          {/* waveform path */}
          {overlayPath && (
            <path
              d={overlayPath}
              className={styles.waveformPath}
              vectorEffect="non-scaling-stroke"
              data-testid="waveform-path"
            />
          )}
        </svg>
      )}
    </div>
  );
}
