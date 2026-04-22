import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { FrameStrip } from './FrameStrip';

describe('FrameStrip', () => {
  it('renders `count` frames (default 12)', () => {
    render(<FrameStrip boundaryT={100} windowSec={3} />);
    const strip = screen.getByTestId('frame-strip');
    expect(strip.children.length).toBe(12);
  });

  it('renders the requested number of frames when count is overridden', () => {
    render(<FrameStrip boundaryT={100} windowSec={3} count={6} />);
    expect(screen.getByTestId('frame-strip').children.length).toBe(6);
  });

  it('marks a boundary frame via data-boundary attribute', () => {
    render(<FrameStrip boundaryT={100} windowSec={3} count={6} />);
    const cells = screen.getByTestId('frame-strip').querySelectorAll('button');
    const boundaryCells = Array.from(cells).filter(
      (c) => c.dataset.boundary === 'true',
    );
    expect(boundaryCells.length).toBeGreaterThan(0);
  });

  it('fires onSelectFrame with the clicked cell timestamp', async () => {
    const onSelect = vi.fn();
    render(
      <FrameStrip
        boundaryT={100}
        windowSec={3}
        count={6}
        onSelectFrame={onSelect}
      />,
    );
    const cells = screen.getByTestId('frame-strip').querySelectorAll('button');
    const user = userEvent.setup();
    await user.click(cells[0] as Element);
    expect(onSelect).toHaveBeenCalledTimes(1);
    // First cell t = 100 - 3 + 0 = 97
    expect(onSelect.mock.calls[0][0]).toBeCloseTo(97, 5);
  });
});
