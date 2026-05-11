import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { InlineErrorHint } from './InlineErrorHint';

describe('InlineErrorHint', () => {
  it('renders hint with 💡 prefix when hint is provided', () => {
    render(<InlineErrorHint hint="ファイルを確認してください" />);
    expect(screen.getByText('💡 ファイルを確認してください')).toBeInTheDocument();
  });

  it('renders nothing when hint is null', () => {
    const { container } = render(<InlineErrorHint hint={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when hint is undefined', () => {
    const { container } = render(<InlineErrorHint hint={undefined} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when hint is empty string', () => {
    const { container } = render(<InlineErrorHint hint="" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('does not carry role attribute (parent role="alert" must remain authoritative)', () => {
    render(<InlineErrorHint hint="some hint" />);
    const el = screen.getByText(/💡/);
    expect(el).not.toHaveAttribute('role');
  });
});
