import type { CSSProperties, ReactNode } from 'react';

import { AllaganCorner } from './AllaganCorner';
import styles from './AllaganFrame.module.css';

export interface AllaganFrameProps {
  children: ReactNode;
  style?: CSSProperties;
  /** If false, omit the 4 corner ornaments. Default true. */
  corners?: boolean;
  cornerSize?: number;
  /** Class merged onto the wrapping div for additional styling. */
  className?: string;
}

/**
 * Positioned wrapper that places an AllaganCorner at each of the 4 corners.
 * Mirror of AllaganFrame in docs/design/bundle/project/variants/aether.jsx.
 */
export function AllaganFrame({
  children,
  style,
  corners = true,
  cornerSize = 20,
  className,
}: AllaganFrameProps) {
  const wrapperClass = className
    ? `${styles.frame} ${className}`
    : styles.frame;
  return (
    <div className={wrapperClass} style={style}>
      {corners && (
        <>
          <AllaganCorner size={cornerSize} style={{ position: 'absolute', top: 0, left: 0 }} />
          <AllaganCorner
            size={cornerSize}
            style={{ position: 'absolute', top: 0, right: 0, transform: 'rotate(90deg)' }}
          />
          <AllaganCorner
            size={cornerSize}
            style={{ position: 'absolute', bottom: 0, left: 0, transform: 'rotate(-90deg)' }}
          />
          <AllaganCorner
            size={cornerSize}
            style={{ position: 'absolute', bottom: 0, right: 0, transform: 'rotate(180deg)' }}
          />
        </>
      )}
      {children}
    </div>
  );
}
