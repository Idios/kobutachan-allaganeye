import type { CSSProperties } from 'react';

export interface AllaganCornerProps {
  size?: number;
  color?: string;
  style?: CSSProperties;
  /** Screen-reader label; default: hidden from a11y tree. */
  'aria-label'?: string;
}

/**
 * Geometric 4-corner ornament used at the corners of AllaganFrame.
 * Sourced from docs/design/bundle/project/variants/aether.jsx (function AllaganCorner).
 */
export function AllaganCorner({
  size = 20,
  color = 'var(--ae-gold)',
  style,
  'aria-label': ariaLabel,
}: AllaganCornerProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 20 20"
      style={style}
      role={ariaLabel ? 'img' : undefined}
      aria-label={ariaLabel}
      aria-hidden={ariaLabel ? undefined : true}
    >
      <path
        d="M0 0 H10 M0 0 V10 M2 2 L7 2 L7 7 L2 7 Z"
        stroke={color}
        strokeWidth="0.8"
        fill="none"
        opacity="0.8"
      />
      <circle cx="10" cy="10" r="1.5" fill={color} opacity="0.4" />
    </svg>
  );
}
