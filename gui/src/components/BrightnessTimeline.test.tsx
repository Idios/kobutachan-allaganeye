import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { Match } from '../types/metadata';
import { BrightnessTimeline } from './BrightnessTimeline';

function sampleMatches(): Match[] {
  return [
    {
      index: 1,
      start_time: 0,
      end_time: 100,
      start_display: '0:00',
      end_display: '1:40',
      duration: 100,
      duration_display: '1m40s',
      type: 'fl_match',
      output_file: 'match_001.mp4',
    },
    {
      index: 2,
      start_time: 200,
      end_time: 300,
      start_display: '3:20',
      end_display: '5:00',
      duration: 100,
      duration_display: '1m40s',
      type: 'unknown',
      output_file: 'match_002.mp4',
    },
  ];
}

describe('BrightnessTimeline', () => {
  it('renders a path for brightness samples', () => {
    render(
      <BrightnessTimeline
        samples={[100, 50, 20, 200]}
        duration={400}
        matches={[]}
        selectedIndex={null}
      />,
    );
    const svg = screen.getByTestId('brightness-timeline');
    expect(svg.querySelector('path')).not.toBeNull();
  });

  it('renders one match block per match', () => {
    render(
      <BrightnessTimeline
        samples={[100, 100]}
        duration={400}
        matches={sampleMatches()}
        selectedIndex={null}
      />,
    );
    expect(screen.getByTestId('match-block-1')).toBeInTheDocument();
    expect(screen.getByTestId('match-block-2')).toBeInTheDocument();
  });

  it('calls onSelectMatch when a block is clicked', async () => {
    const onSelect = vi.fn();
    render(
      <BrightnessTimeline
        samples={[100, 100]}
        duration={400}
        matches={sampleMatches()}
        selectedIndex={null}
        onSelectMatch={onSelect}
      />,
    );
    const user = userEvent.setup();
    await user.click(screen.getByTestId('match-block-2'));
    expect(onSelect).toHaveBeenCalledWith(2);
  });

  it('highlights the selected match with stroke', () => {
    render(
      <BrightnessTimeline
        samples={[100, 100]}
        duration={400}
        matches={sampleMatches()}
        selectedIndex={2}
      />,
    );
    const selRect = screen
      .getByTestId('match-block-2')
      .querySelector('rect');
    const otherRect = screen
      .getByTestId('match-block-1')
      .querySelector('rect');
    expect(selRect?.getAttribute('stroke')).toBe('var(--ae-gold-bright)');
    expect(otherRect?.getAttribute('stroke')).toBe('none');
  });

  it('uses custom threshold when provided', () => {
    render(
      <BrightnessTimeline
        samples={[5, 5]}
        duration={100}
        matches={[]}
        selectedIndex={null}
        threshold={10}
      />,
    );
    const label = screen
      .getByTestId('brightness-timeline')
      .querySelector('text');
    expect(label?.textContent).toBe('threshold=10');
  });
});
