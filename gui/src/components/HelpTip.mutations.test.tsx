// #1164: mutation testing (mutator) の undetected を潰すための網羅。
// 既存 `HelpTip.test.tsx` は挙動を押さえているので、ここでは
// (a) placement 計算の閾値、(b) リスナの登録/解除の完全一致、
// (c) Escape の伝播制御、(d) click の pin 固定、(e) className / testId を pin する。
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { HelpTip } from './HelpTip';
import styles from './HelpTip.module.css';

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

describe('HelpTip (mutation coverage, #1164)', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('keeps the default placement exactly at the flip threshold', async () => {
    // 残り高さ == 220 は「反転しない」側 (閾値は < で判定)
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue(
      rectWithBottom(window.innerHeight - 220),
    );
    render(
      <HelpTip label="説明" testId="help">
        説明本文
      </HelpTip>,
    );
    await userEvent.setup().hover(screen.getByTestId('help-trigger'));
    expect(screen.getByTestId('help-popover')).toHaveAttribute('data-placement', 'below');
  });

  it('computes the placement when opening and again on resize', async () => {
    const spy = vi
      .spyOn(HTMLElement.prototype, 'getBoundingClientRect')
      .mockReturnValue(rectWithBottom(window.innerHeight - 10));
    render(
      <HelpTip label="説明" testId="help">
        説明本文
      </HelpTip>,
    );
    const before = spy.mock.calls.length;
    await userEvent.setup().hover(screen.getByTestId('help-trigger'));
    // open 時の handler (openFrom) と open 後の effect (reposition) で 2 回
    expect(spy.mock.calls.length - before).toBeGreaterThanOrEqual(2);
    const afterOpen = spy.mock.calls.length;
    fireEvent(window, new Event('resize'));
    expect(spy.mock.calls.length).toBe(afterOpen + 1);
  });

  it('computes the placement when opening by focus and by click', async () => {
    const spy = vi
      .spyOn(HTMLElement.prototype, 'getBoundingClientRect')
      .mockReturnValue(rectWithBottom(100));
    render(
      <>
        <HelpTip label="説明" testId="help">
          説明本文
        </HelpTip>
        <button type="button">next</button>
      </>,
    );
    const before = spy.mock.calls.length;
    await userEvent.setup().tab();
    // focus 時 handler (openFrom) と effect (reposition) で 2 回
    expect(spy.mock.calls.length - before).toBeGreaterThanOrEqual(2);
  });

  it('leaves Escape alone while closed', () => {
    const onBubble = vi.fn();
    document.addEventListener('keydown', onBubble);
    try {
      render(
        <HelpTip label="説明" testId="help">
          説明本文
        </HelpTip>,
      );
      fireEvent.keyDown(document.body, { key: 'Escape' });
      // 閉じているときは capture で横取りしない
      expect(onBubble).toHaveBeenCalledTimes(1);
    } finally {
      document.removeEventListener('keydown', onBubble);
    }
  });

  it('prevents the default action of the Escape that closes it', async () => {
    render(
      <HelpTip label="説明" testId="help">
        説明本文
      </HelpTip>,
    );
    await userEvent.setup().click(screen.getByTestId('help-trigger'));
    // dispatchEvent は preventDefault されると false を返す
    const notPrevented = fireEvent.keyDown(screen.getByTestId('help-trigger'), {
      key: 'Escape',
    });
    expect(notPrevented).toBe(false);
  });

  it('registers and removes the reposition listeners with the same options', async () => {
    const addWindow = vi.spyOn(window, 'addEventListener');
    const removeWindow = vi.spyOn(window, 'removeEventListener');
    const addDocument = vi.spyOn(document, 'addEventListener');
    const removeDocument = vi.spyOn(document, 'removeEventListener');
    render(
      <HelpTip label="説明" testId="help">
        説明本文
      </HelpTip>,
    );
    const names = (spy: { mock: { calls: unknown[][] } }) => spy.mock.calls.map((call) => call[0]);

    // 閉じている間は resize / scroll を購読しない
    expect(names(addWindow)).not.toContain('resize');
    expect(names(addDocument)).not.toContain('scroll');
    expect(names(addDocument)).not.toContain('keydown');

    await userEvent.setup().click(screen.getByTestId('help-trigger'));
    expect(names(addWindow)).toContain('resize');
    const scrollCall = addDocument.mock.calls.find((c) => c[0] === 'scroll');
    expect(scrollCall?.[2]).toBe(true);
    const keyCall = addDocument.mock.calls.find((c) => c[0] === 'keydown');
    expect(keyCall?.[2]).toBe(true);

    fireEvent.keyDown(document.body, { key: 'Escape' });
    expect(names(removeWindow)).toContain('resize');
    const offScroll = removeDocument.mock.calls.find((c) => c[0] === 'scroll');
    expect(offScroll?.[2]).toBe(true);
    const offKey = removeDocument.mock.calls.find((c) => c[0] === 'keydown');
    expect(offKey?.[2]).toBe(true);
  });

  it('toggles the pinned state on click', () => {
    const spy = vi
      .spyOn(HTMLElement.prototype, 'getBoundingClientRect')
      .mockReturnValue(rectWithBottom(100));
    render(
      <HelpTip label="説明" testId="help">
        説明本文
      </HelpTip>,
    );
    const trigger = screen.getByTestId('help-trigger');
    const before = spy.mock.calls.length;
    // fireEvent.click は pointer イベントを伴わない (hover で開いたままにしない)
    fireEvent.click(trigger);
    expect(screen.getByTestId('help-popover')).toBeInTheDocument();
    // click でも開く瞬間に placement を計算する (handler + effect で 2 回)
    expect(spy.mock.calls.length - before).toBeGreaterThanOrEqual(2);
    fireEvent.click(trigger);
    expect(screen.queryByTestId('help-popover')).toBeNull();
  });

  it('renders no test ids when testId is omitted', async () => {
    render(<HelpTip label="説明">説明本文</HelpTip>);
    expect(document.querySelector('[data-testid]')).toBeNull();
    await userEvent.setup().click(screen.getByRole('button', { name: '説明' }));
    const popover = screen.getByText('説明本文');
    expect(popover.hasAttribute('data-testid')).toBe(false);
  });

  it('marks the popover class only when it is flipped above', async () => {
    const spy = vi
      .spyOn(HTMLElement.prototype, 'getBoundingClientRect')
      .mockReturnValue(rectWithBottom(100));
    render(
      <HelpTip label="説明" testId="help">
        説明本文
      </HelpTip>,
    );
    const user = userEvent.setup();
    await user.click(screen.getByTestId('help-trigger'));
    const below = screen.getByTestId('help-popover');
    expect(below.className).toContain(styles.popover);
    expect(below.className).not.toContain(styles.popoverAbove);
    // above 以外で余計な文字列を混ぜない
    expect(below.className).not.toContain('Stryker');

    spy.mockReturnValue(rectWithBottom(window.innerHeight - 10));
    fireEvent(window, new Event('resize'));
    const above = screen.getByTestId('help-popover');
    expect(above.className).toContain(styles.popover);
    expect(above.className).toContain(styles.popoverAbove);
  });
});
