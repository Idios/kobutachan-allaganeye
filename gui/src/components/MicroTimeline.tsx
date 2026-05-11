import { useMemo } from 'react';

import { buildBrightnessPath, findBlackoutRegions } from '../utils/brightness';
import styles from './MicroTimeline.module.css';

export interface MicroTimelineProps {
  samples: readonly number[];
  windowSeconds: number;
  threshold: number;
}

/**
 * #645: ±5s zoom of brightness around a match boundary.
 *
 * - waveform path (gold)
 * - threshold line (danger color, dashed)
 * - blackout band (cyan, samples below threshold)
 * - boundary marker (vertical white dashed line at center)
 * - axis labels (-5s / 0 / +5s)
 *
 * Display-only (Q6 = A、no scrubbing). Reuses utils/brightness.ts.
 */
export function MicroTimeline({
  samples,
  windowSeconds,
  threshold,
}: MicroTimelineProps) {
  const W = 200;
  const H = 36;
  const axisOffset = H + 6;

  const path = useMemo(
    () => buildBrightnessPath(samples, W, H),
    [samples, W, H],
  );
  const blackouts = useMemo(
    () => findBlackoutRegions(samples, windowSeconds, threshold),
    [samples, windowSeconds, threshold],
  );
  const thresholdY = H - (threshold / 255) * H;

  return (
    <svg
      viewBox={`0 0 ${W} ${axisOffset + 8}`}
      className={styles.timeline}
      preserveAspectRatio="none"
      data-testid="micro-timeline"
    >
      {/* threshold line */}
      <line
        x1={0}
        x2={W}
        y1={thresholdY}
        y2={thresholdY}
        className={styles.thresholdLine}
        data-testid="threshold-line"
      />

      {/* blackout bands */}
      {blackouts.map((r, i) => {
        const x1 = (r.start / windowSeconds) * W;
        const x2 = (r.end / windowSeconds) * W;
        return (
          <rect
            key={i}
            x={x1}
            y={0}
            width={Math.max(1.5, x2 - x1)}
            height={H}
            className={styles.blackoutBand}
            data-testid="blackout-band"
          />
        );
      })}

      {/* waveform path */}
      {path && (
        <path
          d={path}
          className={styles.waveformPath}
          data-testid="waveform-path"
        />
      )}

      {/* boundary marker (center vertical line) */}
      <line
        x1={W / 2}
        x2={W / 2}
        y1={0}
        y2={H}
        className={styles.boundaryMarker}
        data-testid="boundary-marker"
      />

      {/* axis labels */}
      <text x={2} y={axisOffset + 6} fontSize="6" className={styles.axisLabel}>
        -5s
      </text>
      <text
        x={W / 2}
        y={axisOffset + 6}
        fontSize="6"
        textAnchor="middle"
        className={styles.axisLabel}
      >
        0
      </text>
      <text
        x={W - 2}
        y={axisOffset + 6}
        fontSize="6"
        textAnchor="end"
        className={styles.axisLabel}
      >
        +5s
      </text>
    </svg>
  );
}
