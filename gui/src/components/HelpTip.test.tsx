import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { HelpTip } from './HelpTip';

/**
 * #1135 -- 設定項目の hover / focus help。
 * docs/ui-interaction-spec.md §1.7 が挙動の正。
 */
describe('HelpTip (#1135)', () => {
  it('renders only the trigger until it is opened', () => {
    render(
      <HelpTip label="検知しきい値の説明" testId="help">
        説明本文
      </HelpTip>,
    );
    expect(screen.getByTestId('help-trigger')).toHaveAccessibleName(
      '検知しきい値の説明',
    );
    expect(screen.queryByTestId('help-popover')).toBeNull();
  });

  it('opens on hover and closes when the pointer leaves', async () => {
    const user = userEvent.setup();
    render(
      <HelpTip label="説明" testId="help">
        説明本文
      </HelpTip>,
    );
    const trigger = screen.getByTestId('help-trigger');
    await user.hover(trigger);
    expect(screen.getByTestId('help-popover')).toHaveTextContent('説明本文');
    expect(screen.getByTestId('help-popover')).toHaveAttribute(
      'data-placement',
      'below',
    );
    await user.unhover(trigger);
    expect(screen.queryByTestId('help-popover')).toBeNull();
  });

  it('flips above when the trigger is near the bottom of the viewport', async () => {
    const user = userEvent.setup();
    const rect = {
      top: window.innerHeight - 25,
      bottom: window.innerHeight - 10,
      left: 0,
      right: 15,
      width: 15,
      height: 15,
      x: 0,
      y: window.innerHeight - 25,
      toJSON: () => ({}),
    } as DOMRect;
    const spy = vi
      .spyOn(HTMLElement.prototype, 'getBoundingClientRect')
      .mockReturnValue(rect);
    try {
      render(
        <HelpTip label="説明" testId="help">
          説明本文
        </HelpTip>,
      );
      await user.hover(screen.getByTestId('help-trigger'));
      // DropScreen の `.screen` は overflow: auto なので、下向き固定だと
      // 下端で切られる。開く前に残り高さを見て上向きへ反転する。
      expect(screen.getByTestId('help-popover')).toHaveAttribute(
        'data-placement',
        'above',
      );
    } finally {
      spy.mockRestore();
    }
  });

  it('recalculates placement when the viewport is resized while open', async () => {
    const user = userEvent.setup();
    function rectWithBottom(bottom: number): DOMRect {
      return {
        top: bottom - 15,
        bottom,
        left: 0,
        right: 15,
        width: 15,
        height: 15,
        x: 0,
        y: bottom - 15,
        toJSON: () => ({}),
      } as DOMRect;
    }
    const spy = vi
      .spyOn(HTMLElement.prototype, 'getBoundingClientRect')
      .mockReturnValue(rectWithBottom(window.innerHeight - 10));
    try {
      render(
        <HelpTip label="説明" testId="help">
          説明本文
        </HelpTip>,
      );
      const trigger = screen.getByTestId('help-trigger');
      await user.hover(trigger);
      expect(screen.getByTestId('help-popover')).toHaveAttribute(
        'data-placement',
        'above',
      );
      // hover のままで window を広げる (= trigger の下に余白ができる)。
      spy.mockReturnValue(rectWithBottom(100));
      act(() => {
        window.dispatchEvent(new Event('resize'));
      });
      expect(screen.getByTestId('help-popover')).toHaveAttribute(
        'data-placement',
        'below',
      );
    } finally {
      spy.mockRestore();
    }
  });

  it('opens on keyboard focus so the text is reachable without a mouse', async () => {
    const user = userEvent.setup();
    render(
      <HelpTip label="説明" testId="help">
        説明本文
      </HelpTip>,
    );
    await user.tab();
    expect(screen.getByTestId('help-trigger')).toHaveFocus();
    expect(screen.getByTestId('help-popover')).toHaveTextContent('説明本文');
  });

  it('closes on Escape and keeps the trigger focusable afterwards', async () => {
    const user = userEvent.setup();
    render(
      <HelpTip label="説明" testId="help">
        説明本文
      </HelpTip>,
    );
    await user.tab();
    expect(screen.getByTestId('help-popover')).toBeInTheDocument();
    await user.keyboard('{Escape}');
    expect(screen.queryByTestId('help-popover')).toBeNull();
    // Escape must not leave a stuck-open state: refocusing re-opens it.
    await user.tab();
    expect(screen.getByTestId('help-popover')).toHaveTextContent('説明本文');
  });

  it('keeps Escape away from document-level handlers (dialog dismiss)', async () => {
    const user = userEvent.setup();
    const onDocumentEscape = vi.fn();
    function onDocumentKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onDocumentEscape();
    }
    document.addEventListener('keydown', onDocumentKey);
    try {
      render(
        <HelpTip label="説明" testId="help">
          説明本文
        </HelpTip>,
      );
      await user.tab();
      await user.keyboard('{Escape}');
      // DropScreen の SelectedCard は document の Escape で選択を解除する
      // (useEscapeKey)。help を閉じる Escape がそこへ抜けると退行になる。
      expect(onDocumentEscape).not.toHaveBeenCalled();
      expect(screen.queryByTestId('help-popover')).toBeNull();
    } finally {
      document.removeEventListener('keydown', onDocumentKey);
    }
  });

  it('keeps Escape away from document-level handlers when opened by hover alone', async () => {
    const user = userEvent.setup();
    const onDocumentEscape = vi.fn();
    function onDocumentKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onDocumentEscape();
    }
    document.addEventListener('keydown', onDocumentKey);
    try {
      render(
        <>
          <HelpTip label="説明" testId="help">
            説明本文
          </HelpTip>
          <button type="button">next</button>
        </>,
      );
      // focus は trigger に無い (hover だけで open している) 状態を作る。
      (screen.getByRole('button', { name: 'next' }) as HTMLButtonElement).focus();
      await user.hover(screen.getByTestId('help-trigger'));
      expect(screen.getByTestId('help-popover')).toBeInTheDocument();
      await user.keyboard('{Escape}');
      expect(onDocumentEscape).not.toHaveBeenCalled();
      expect(screen.queryByTestId('help-popover')).toBeNull();
    } finally {
      document.removeEventListener('keydown', onDocumentKey);
    }
  });

  it('closes when focus moves to the next control', async () => {
    const user = userEvent.setup();
    render(
      <>
        <HelpTip label="説明" testId="help">
          説明本文
        </HelpTip>
        <button type="button">next</button>
      </>,
    );
    await user.tab();
    expect(screen.getByTestId('help-popover')).toBeInTheDocument();
    await user.tab();
    expect(screen.queryByTestId('help-popover')).toBeNull();
  });
});
