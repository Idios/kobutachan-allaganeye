import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { MicroTimeline } from './MicroTimeline';

describe('MicroTimeline', () => {
  const samples = Array.from({ length: 100 }, (_, i) => {
    // simulate: bright (200) → blackout (5) at center → bright (200)
    if (i >= 45 && i <= 55) return 5;
    return 200;
  });

  it('renders SVG with viewBox', () => {
    const { container } = render(
      <MicroTimeline samples={samples} windowSeconds={10} threshold={15} />,
    );
    const svg = container.querySelector('svg');
    expect(svg).toHaveAttribute('viewBox');
  });

  it('renders threshold line', () => {
    const { container } = render(
      <MicroTimeline samples={samples} windowSeconds={10} threshold={15} />,
    );
    const thresholdLine = container.querySelector('[data-testid="threshold-line"]');
    expect(thresholdLine).not.toBeNull();
  });

  it('renders boundary marker at center', () => {
    const { container } = render(
      <MicroTimeline samples={samples} windowSeconds={10} threshold={15} />,
    );
    const marker = container.querySelector('[data-testid="boundary-marker"]');
    expect(marker).not.toBeNull();
  });

  it('renders blackout band for samples below threshold', () => {
    const { container } = render(
      <MicroTimeline samples={samples} windowSeconds={10} threshold={15} />,
    );
    const bands = container.querySelectorAll('[data-testid="blackout-band"]');
    expect(bands.length).toBeGreaterThanOrEqual(1);
  });

  it('renders axis labels (-5s / 0 / +5s)', () => {
    render(
      <MicroTimeline samples={samples} windowSeconds={10} threshold={15} />,
    );
    expect(screen.getByText('-5s')).toBeInTheDocument();
    expect(screen.getByText('0')).toBeInTheDocument();
    expect(screen.getByText('+5s')).toBeInTheDocument();
  });

  it('renders waveform path', () => {
    const { container } = render(
      <MicroTimeline samples={samples} windowSeconds={10} threshold={15} />,
    );
    const path = container.querySelector('[data-testid="waveform-path"]');
    expect(path).not.toBeNull();
    expect(path).toHaveAttribute('d');
  });
});
