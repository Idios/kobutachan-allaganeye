import styles from './MatchThumb.module.css';

export interface MatchThumbProps {
  index: number;
  width?: number | string;
  height?: number | string;
}

/**
 * Decorative match thumbnail placeholder used until Phase 3 provides real
 * frame captures. Deterministic pseudo-art derived from the match index.
 *
 * Mirror of MatchThumb in docs/design/bundle/project/shared/common.jsx.
 */
export function MatchThumb({ index, width = 96, height = 54 }: MatchThumbProps) {
  const hue = (index * 47) % 360;
  const shimmerX = 30 + (index * 13) % 40;
  const shimmerY = 40 + (index * 7) % 20;
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
