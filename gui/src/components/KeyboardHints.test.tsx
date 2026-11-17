import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { KeyboardHints } from './KeyboardHints';

describe('KeyboardHints', () => {
  // 試合境界エディタ (PreviewScreen) とクリップ範囲の画面 (ClipRangeView) が
  // 同じ割当を案内するための共通部品 (#1139)。
  it('advertises the shared key bindings', () => {
    render(<KeyboardHints />);

    const hint = screen.getByRole('note', { name: 'keyboard shortcuts' });
    expect(hint.textContent).toContain('1s');
    expect(hint.textContent).toContain('10s');
    expect(hint.textContent).toContain('1F');
    expect(hint.textContent).toContain('Space');
    expect(hint.textContent).toContain('再生/停止');
  });
});
