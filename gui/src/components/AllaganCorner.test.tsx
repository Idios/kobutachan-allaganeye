import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { AllaganCorner } from './AllaganCorner';

describe('AllaganCorner', () => {
  it('renders an SVG with default 20x20 size', () => {
    const { container } = render(<AllaganCorner />);
    const svg = container.querySelector('svg');
    expect(svg).not.toBeNull();
    expect(svg?.getAttribute('width')).toBe('20');
    expect(svg?.getAttribute('height')).toBe('20');
  });

  it('applies custom size', () => {
    const { container } = render(<AllaganCorner size={40} />);
    const svg = container.querySelector('svg');
    expect(svg?.getAttribute('width')).toBe('40');
    expect(svg?.getAttribute('height')).toBe('40');
  });

  it('applies custom color to stroke and circle', () => {
    const { container } = render(<AllaganCorner color="#ff0000" />);
    expect(container.querySelector('path')?.getAttribute('stroke')).toBe('#ff0000');
    expect(container.querySelector('circle')?.getAttribute('fill')).toBe('#ff0000');
  });

  it('is hidden from a11y tree by default', () => {
    const { container } = render(<AllaganCorner />);
    expect(container.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true');
  });

  it('exposes aria-label when provided', () => {
    const { getByLabelText } = render(<AllaganCorner aria-label="corner decoration" />);
    expect(getByLabelText('corner decoration')).toBeInTheDocument();
  });
});
