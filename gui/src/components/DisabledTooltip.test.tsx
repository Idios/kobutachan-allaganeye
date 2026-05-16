import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { DisabledTooltip } from './DisabledTooltip';

describe('DisabledTooltip', () => {
  it('injects title=reason on the wrapped element when disabled', () => {
    render(
      <DisabledTooltip disabled reason="押せない理由">
        {(p) => (
          <button type="button" {...p}>
            click me
          </button>
        )}
      </DisabledTooltip>,
    );
    const btn = screen.getByRole('button', { name: 'click me' });
    expect(btn.getAttribute('title')).toBe('押せない理由');
  });

  it('does not inject title when not disabled', () => {
    render(
      <DisabledTooltip disabled={false} reason="押せない理由">
        {(p) => (
          <button type="button" {...p}>
            click me
          </button>
        )}
      </DisabledTooltip>,
    );
    const btn = screen.getByRole('button', { name: 'click me' });
    expect(btn.hasAttribute('title')).toBe(false);
  });

  it('does not inject title when reason is an empty string', () => {
    render(
      <DisabledTooltip disabled reason="">
        {(p) => (
          <button type="button" {...p}>
            click me
          </button>
        )}
      </DisabledTooltip>,
    );
    const btn = screen.getByRole('button', { name: 'click me' });
    expect(btn.hasAttribute('title')).toBe(false);
  });

  it('renders inline hint text when disabled and inlineHint is true', () => {
    render(
      <DisabledTooltip disabled reason="動画を選択してください" inlineHint>
        {(p) => (
          <button type="button" {...p}>
            開始
          </button>
        )}
      </DisabledTooltip>,
    );
    expect(screen.getByText('動画を選択してください')).toBeInTheDocument();
  });

  it('does not render inline hint when inlineHint is false', () => {
    render(
      <DisabledTooltip disabled reason="動画を選択してください">
        {(p) => (
          <button type="button" {...p}>
            開始
          </button>
        )}
      </DisabledTooltip>,
    );
    // The reason should not appear as visible text outside the title
    // attribute. queryAllByText returns only nodes where the visible
    // textContent matches; the title attribute is not visible text.
    expect(screen.queryByText('動画を選択してください')).toBeNull();
  });

  it('does not render inline hint when not disabled even if inlineHint is true', () => {
    render(
      <DisabledTooltip disabled={false} reason="動画を選択してください" inlineHint>
        {(p) => (
          <button type="button" {...p}>
            開始
          </button>
        )}
      </DisabledTooltip>,
    );
    expect(screen.queryByText('動画を選択してください')).toBeNull();
  });
});
