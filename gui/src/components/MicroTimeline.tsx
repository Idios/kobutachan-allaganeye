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
 *
 * **layout note (実機検証 fix)**: SVG は `preserveAspectRatio="none"` で画面幅に
 * 水平 stretch するため、内部 `<text>` を置くと水平方向に大きく歪む
 * (e.g., 200×50 viewBox を 1900px 幅に伸ばすと文字が ~9.5x に引き伸ばされる)。
 * BrightnessTimeline は `height: auto` で aspect ratio を保つので問題に
 * ならないが、MicroTimeline は固定高さの compact widget なので同手法が
 * 使えない。対策として軸ラベルは SVG 外の HTML span で render し、scale
 * の影響を回避する。SVG 内部要素 (line / path / rect) は scale-invariant
 * (線の太さや形状は CSS で固定) なので horizontal stretch しても破綻しない。
 */
export function MicroTimeline({
  samples,
  windowSeconds,
  threshold,
}: MicroTimelineProps) {
  const W = 200;
  const H = 36;

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
    <div className={styles.wrap} data-testid="micro-timeline-wrap">
      <svg
        viewBox={`0 0 ${W} ${H}`}
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
      </svg>

      {/* axis labels (HTML、SVG 外で render することで preserveAspectRatio による
          水平 stretch の影響を回避) */}
      <div className={styles.axisLabels}>
        <span className={styles.axisLabel}>-5s</span>
        <span className={styles.axisLabel}>0</span>
        <span className={styles.axisLabel}>+5s</span>
      </div>
    </div>
  );
}
