import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { LoadingSpinner } from './LoadingSpinner';

describe('LoadingSpinner', () => {
  it('renders the visible label', () => {
    render(<LoadingSpinner label="解析中" />);
    expect(screen.getByText('解析中')).toBeInTheDocument();
  });

  it('renders the spinning sigil hidden from a11y', () => {
    const { container } = render(<LoadingSpinner label="選択中" />);
    const decoratives = container.querySelectorAll('[aria-hidden="true"]');
    expect(decoratives.length).toBeGreaterThan(0);
  });

  it('does not add screen-reader markup (no role=status, no aria-live)', () => {
    // a11y-policy.md: motion + visible text only.
    const { container } = render(<LoadingSpinner label="解析中" />);
    expect(container.querySelector('[role="status"]')).toBeNull();
    expect(container.querySelector('[aria-live]')).toBeNull();
  });
});
