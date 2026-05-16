import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { AllaganSigil } from './AllaganSigil';

describe('AllaganSigil', () => {
  it('renders three SVG layers', () => {
    const { container } = render(<AllaganSigil />);
    expect(container.querySelectorAll('svg').length).toBe(3);
  });

  it('respects the size prop', () => {
    const { container } = render(<AllaganSigil size={60} />);
    const svgs = container.querySelectorAll('svg');
    svgs.forEach((svg) => {
      expect(svg.getAttribute('width')).toBe('60');
      expect(svg.getAttribute('height')).toBe('60');
    });
  });

  it('exposes img role with label for a11y', () => {
    const { getByLabelText } = render(<AllaganSigil />);
    expect(getByLabelText('Allagan observation sigil')).toBeInTheDocument();
  });

  it('removes rotation classes when rotating=false', () => {
    const { container } = render(<AllaganSigil rotating={false} />);
    const svgs = container.querySelectorAll('svg');
    svgs.forEach((svg) => {
      const cls = svg.getAttribute('class') ?? '';
      expect(cls).not.toMatch(/rotate/);
    });
  });
});
