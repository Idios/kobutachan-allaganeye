import { useMemo } from 'react';

import type { Match } from '../types/metadata';
import {
  buildBrightnessPath,
  findBlackoutRegions,
} from '../utils/brightness';
import { fmtTime } from '../utils/time';
import styles from './BrightnessTimeline.module.css';

export interface BrightnessTimelineProps {
  samples: readonly number[];
  duration: number;
  matches: readonly Match[];
  /** 1-based match index currently selected (null = none). */
  selectedIndex: number | null;
  /** Called when a match block is clicked. Receives the 1-based index. */
  onSelectMatch?: (index: number) => void;
  /** SVG viewBox width. Default 700. */
  viewboxWidth?: number;
  /** SVG viewBox height for the brightness graph portion. Default 100. */
  viewboxHeight?: number;
  /** Brightness threshold line. Default 15 (matches allaganeye detector default). */
  threshold?: number;
}

/**
 * Renders the complete-screen brightness timeline:
 * - gold line graph of brightness
 * - cyan bands where brightness is below threshold (blackout regions)
 * - gold rectangles under the graph, one per match block
 * - time axis with 0 / 25 / 50 / 75 / 100% tick labels
 *
 * Purely presentational; parent supplies samples, duration, matches, and
 * selection state. Click handling bubbles up via onSelectMatch.
 *
 * Mirror of the inline SVG in docs/design/bundle/project/variants/aether.jsx AetherComplete.
 */
export function BrightnessTimeline({
  samples,
  duration,
  matches,
  selectedIndex,
  onSelectMatch,
  viewboxWidth = 700,
  viewboxHeight = 100,
  threshold = 15,
}: BrightnessTimelineProps) {
  const W = viewboxWidth;
  const H = viewboxHeight;
  const axisOffset = H + 48;

  const path = useMemo(
    () => buildBrightnessPath(samples, W, H),
    [samples, W, H],
  );
  const blackouts = useMemo(
    () => findBlackoutRegions(samples, duration, threshold),
    [samples, duration, threshold],
  );

  const thresholdY = H - (threshold / 255) * H;

  return (
    <svg
      viewBox={`0 0 ${W} ${axisOffset}`}
      className={styles.timeline}
      preserveAspectRatio="none"
      data-testid="brightness-timeline"
    >
      {/* grid */}
      {[50, 100, 150, 200].map((y) => {
        const yy = H - (y / 255) * H;
        return <line key={y} x1={0} x2={W} y1={yy} y2={yy} className={styles.gridLine} />;
      })}
      <line x1={0} x2={W} y1={thresholdY} y2={thresholdY} className={styles.thresholdLine} />
      <text x={4} y={thresholdY - 2} fontSize="7" className={styles.thresholdLabel}>
        threshold={threshold}
      </text>

      {/* blackout bands */}
      {blackouts.map((r, i) => {
        const x1 = (r.start / duration) * W;
        const x2 = (r.end / duration) * W;
        return (
          <rect
            key={i}
            x={x1}
            y={0}
            width={Math.max(1.5, x2 - x1)}
            height={H}
            className={styles.blackoutBand}
          />
        );
      })}

      {/* brightness line + fill */}
      {path && <path d={path} className={styles.brightnessLine} />}
      {path && (
        <path
          d={`${path} L ${W} ${H} L 0 ${H} Z`}
          className={styles.brightnessFill}
        />
      )}

      {/* match blocks */}
      {matches.map((m) => {
        const x1 = (m.start_time / duration) * W;
        const x2 = (m.end_time / duration) * W;
        const isSel = m.index === selectedIndex;
        const labelKind = m.type === 'fl_match' ? 'FL' : '不明';
        // #587 a11y: each match block is interactive (click to select).
        // tabIndex+role+aria-label make it keyboard-reachable and give
        // axe a "button name" to satisfy. See docs/a11y-policy.md
        // "scope policy" for the icon-only-button exception.
        return (
          <g
            key={m.index}
            className={styles.matchBlock}
            onClick={() => onSelectMatch?.(m.index)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onSelectMatch?.(m.index);
              }
            }}
            tabIndex={0}
            role="button"
            aria-label={`match ${m.index} (${labelKind})`}
            data-testid={`match-block-${m.index}`}
          >
            <rect
              x={x1}
              y={H + 6}
              width={Math.max(2, x2 - x1)}
              height={18}
              fill={m.type === 'fl_match' ? 'var(--ae-gold)' : 'var(--ae-gold-dim)'}
              opacity={isSel ? 1 : 0.55}
              stroke={isSel ? 'var(--ae-gold-bright)' : 'none'}
              strokeWidth={isSel ? 1 : 0}
            />
            <text
              x={x1 + 2}
              y={H + 18}
              fontSize="7"
              className={styles.matchLabel}
            >
              {String(m.index).padStart(2, '0')}
            </text>
          </g>
        );
      })}

      {/* time axis */}
      {[0, 0.25, 0.5, 0.75, 1].map((p) => (
        <g key={p}>
          <line
            x1={p * W}
            x2={p * W}
            y1={H + 30}
            y2={H + 34}
            className={styles.tickMark}
          />
          <text
            x={p * W}
            y={H + 44}
            fontSize="7"
            className={styles.tickLabel}
            textAnchor={p === 0 ? 'start' : p === 1 ? 'end' : 'middle'}
          >
            {fmtTime(p * duration)}
          </text>
        </g>
      ))}
    </svg>
  );
}
