import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { MatchThumb } from './MatchThumb';

describe('MatchThumb', () => {
  it('labels the thumbnail with the match index', () => {
    const { getByLabelText } = render(<MatchThumb index={3} />);
    expect(getByLabelText('match 3 thumbnail')).toBeInTheDocument();
  });

  it('produces a different hue per index (deterministic)', () => {
    const { getByTestId, rerender } = render(<MatchThumb index={1} />);
    const hue1 = getByTestId('match-thumb').getAttribute('data-hue');
    rerender(<MatchThumb index={2} />);
    const hue2 = getByTestId('match-thumb').getAttribute('data-hue');
    expect(hue1).not.toBe(hue2);
  });

  it('accepts numeric and string dimensions', () => {
    const { getByTestId, rerender } = render(<MatchThumb index={1} width={120} height={68} />);
    const n = getByTestId('match-thumb') as HTMLElement;
    expect(n.style.width).toBe('120px');
    expect(n.style.height).toBe('68px');
    rerender(<MatchThumb index={1} width="100%" height="100%" />);
    expect(n.style.width).toBe('100%');
    expect(n.style.height).toBe('100%');
  });
});
