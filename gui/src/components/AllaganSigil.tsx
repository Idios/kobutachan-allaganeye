import type { JSX } from 'react';

import styles from './AllaganSigil.module.css';

export interface AllaganSigilProps {
  size?: number;
  /** When false, the sigil is static (used on the drop screen). */
  rotating?: boolean;
}

function ring(r: number, segs: number, thickness = 0.4): JSX.Element[] {
  const els: JSX.Element[] = [];
  for (let i = 0; i < segs; i++) {
    const a1 = (i / segs) * Math.PI * 2;
    const a2 = ((i + 0.7) / segs) * Math.PI * 2;
    const x1 = 60 + Math.cos(a1) * r;
    const y1 = 60 + Math.sin(a1) * r;
    const x2 = 60 + Math.cos(a2) * r;
    const y2 = 60 + Math.sin(a2) * r;
    els.push(
      <path
        key={i}
        d={`M${x1} ${y1} A${r} ${r} 0 0 1 ${x2} ${y2}`}
        stroke="var(--ae-gold)"
        strokeWidth={thickness}
        fill="none"
      />,
    );
  }
  return els;
}

/**
 * The spinning Allagan magical sigil used as the detecting indicator.
 * Mirror of AllaganSigil in docs/design/bundle/project/variants/aether.jsx.
 * All colors reference CSS custom properties so the sigil respects theme changes.
 */
export function AllaganSigil({ size = 120, rotating = true }: AllaganSigilProps) {
  return (
    <div
      className={styles.sigil}
      style={{ width: size, height: size }}
      role="img"
      aria-label="Allagan observation sigil"
    >
      <svg
        viewBox="0 0 120 120"
        width={size}
        height={size}
        className={`${styles.layer}${rotating ? ` ${styles.rotateCw24s}` : ''}`}
      >
        {ring(55, 24, 0.5)}
        {ring(45, 12, 0.8)}
      </svg>
      <svg
        viewBox="0 0 120 120"
        width={size}
        height={size}
        className={`${styles.layer}${rotating ? ` ${styles.rotateCcw16s}` : ''}`}
      >
        {ring(35, 6, 1)}
        <polygon
          points="60,30 85,75 35,75"
          stroke="var(--ae-gold)"
          strokeWidth="0.8"
          fill="none"
          opacity="0.7"
        />
        <polygon
          points="60,90 35,45 85,45"
          stroke="var(--ae-cyan)"
          strokeWidth="0.6"
          fill="none"
          opacity="0.6"
        />
      </svg>
      <svg
        viewBox="0 0 120 120"
        width={size}
        height={size}
        className={`${styles.layer}${rotating ? ` ${styles.rotateCw10s}` : ''}`}
      >
        <circle
          cx="60"
          cy="60"
          r="22"
          stroke="var(--ae-gold)"
          strokeWidth="0.8"
          fill="none"
          opacity="0.8"
        />
        <circle
          cx="60"
          cy="60"
          r="12"
          stroke="var(--ae-cyan)"
          strokeWidth="1"
          fill="none"
        />
        <circle cx="60" cy="60" r="3" fill="var(--ae-gold-bright)" />
      </svg>
    </div>
  );
}
