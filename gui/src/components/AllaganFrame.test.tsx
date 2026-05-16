import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { AllaganFrame } from './AllaganFrame';

describe('AllaganFrame', () => {
  it('renders children', () => {
    const { getByText } = render(
      <AllaganFrame>
        <span>inner content</span>
      </AllaganFrame>,
    );
    expect(getByText('inner content')).toBeInTheDocument();
  });

  it('renders 4 corner SVG ornaments by default', () => {
    const { container } = render(
      <AllaganFrame>
        <div />
      </AllaganFrame>,
    );
    expect(container.querySelectorAll('svg').length).toBe(4);
  });

  it('omits corners when corners=false', () => {
    const { container } = render(
      <AllaganFrame corners={false}>
        <div />
      </AllaganFrame>,
    );
    expect(container.querySelectorAll('svg').length).toBe(0);
  });

  it('applies custom style to the wrapper', () => {
    const { container } = render(
      <AllaganFrame style={{ padding: 8 }}>
        <div />
      </AllaganFrame>,
    );
    const wrapper = container.firstElementChild as HTMLElement;
    expect(wrapper.style.padding).toBe('8px');
  });
});
