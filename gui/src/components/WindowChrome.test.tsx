import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { WindowChrome } from './WindowChrome';

describe('WindowChrome', () => {
  it('renders the given title', () => {
    const { getByText } = render(<WindowChrome title="Allagan Eye" />);
    expect(getByText('Allagan Eye')).toBeInTheDocument();
  });

  it('renders the 3 traffic-light dots as decorative (aria-hidden)', () => {
    const { getByTestId } = render(<WindowChrome title="x" />);
    const chrome = getByTestId('window-chrome');
    const dots = chrome.querySelectorAll('div > div');
    // 3 dots inside the traffic-lights wrapper
    const wrapper = chrome.children[0];
    expect(wrapper.getAttribute('aria-hidden')).toBe('true');
    expect(wrapper.children.length).toBe(3);
    expect(dots.length).toBeGreaterThanOrEqual(3);
  });
});
