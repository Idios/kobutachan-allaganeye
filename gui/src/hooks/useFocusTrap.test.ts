import { act, renderHook } from '@testing-library/react';
import { useRef } from 'react';
import { describe, expect, it } from 'vitest';

import { useFocusTrap } from './useFocusTrap';

function setupContainer(buttonCount: number): {
  container: HTMLDivElement;
  buttons: HTMLButtonElement[];
} {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const buttons: HTMLButtonElement[] = [];
  for (let i = 0; i < buttonCount; i++) {
    const b = document.createElement('button');
    b.textContent = `btn-${i}`;
    container.appendChild(b);
    buttons.push(b);
  }
  return { container, buttons };
}

function fireTab(shift = false) {
  const ev = new KeyboardEvent('keydown', {
    key: 'Tab',
    shiftKey: shift,
    bubbles: true,
    cancelable: true,
  });
  document.dispatchEvent(ev);
  return ev;
}

describe('useFocusTrap', () => {
  it('auto-focuses the first focusable when activated', () => {
    const { container, buttons } = setupContainer(3);
    const ref = { current: container };
    renderHook(() => useFocusTrap(ref, true));
    expect(document.activeElement).toBe(buttons[0]);
    container.remove();
  });

  it('does not yank focus if a child is already focused', () => {
    const { container, buttons } = setupContainer(3);
    const ref = { current: container };
    buttons[1].focus();
    renderHook(() => useFocusTrap(ref, true));
    expect(document.activeElement).toBe(buttons[1]);
    container.remove();
  });

  it('wraps Tab from the last focusable to the first', () => {
    const { container, buttons } = setupContainer(3);
    const ref = { current: container };
    renderHook(() => useFocusTrap(ref, true));
    buttons[2].focus();
    act(() => {
      fireTab(false);
    });
    expect(document.activeElement).toBe(buttons[0]);
    container.remove();
  });

  it('wraps Shift+Tab from the first focusable to the last', () => {
    const { container, buttons } = setupContainer(3);
    const ref = { current: container };
    renderHook(() => useFocusTrap(ref, true));
    buttons[0].focus();
    act(() => {
      fireTab(true);
    });
    expect(document.activeElement).toBe(buttons[2]);
    container.remove();
  });

  it('does not interfere when active is false', () => {
    const { container, buttons } = setupContainer(2);
    const outsider = document.createElement('button');
    document.body.appendChild(outsider);
    outsider.focus();
    const ref = { current: container };
    renderHook(() => useFocusTrap(ref, false));
    // The hook should NOT have moved focus.
    expect(document.activeElement).toBe(outsider);
    // And Tab should not be intercepted (we cannot easily assert browser
    // tab navigation in jsdom, but the listener must not be installed).
    act(() => {
      const ev = fireTab(false);
      expect(ev.defaultPrevented).toBe(false);
    });
    void buttons;
    container.remove();
    outsider.remove();
  });

  it('restores focus to the previously focused element on cleanup', () => {
    const opener = document.createElement('button');
    document.body.appendChild(opener);
    opener.focus();
    const { container } = setupContainer(2);
    const ref = { current: container };
    const { unmount } = renderHook(() => useFocusTrap(ref, true));
    // Focus has moved into the trap.
    expect(document.activeElement).not.toBe(opener);
    unmount();
    expect(document.activeElement).toBe(opener);
    container.remove();
    opener.remove();
  });

  it('handles a container with no focusables by preventing Tab from leaving', () => {
    const container = document.createElement('div');
    document.body.appendChild(container);
    const ref = { current: container };
    renderHook(() => useFocusTrap(ref, true));
    act(() => {
      const ev = fireTab(false);
      expect(ev.defaultPrevented).toBe(true);
    });
    container.remove();
  });

  it('updates when active toggles from true to false', () => {
    const { container, buttons } = setupContainer(2);
    const ref = { current: container };
    const { rerender, unmount } = renderHook(
      ({ active }: { active: boolean }) => useFocusTrap(ref, active),
      { initialProps: { active: true } },
    );
    expect(document.activeElement).toBe(buttons[0]);
    rerender({ active: false });
    // After switching off, Tab from the last button must NOT wrap.
    buttons[1].focus();
    act(() => {
      const ev = fireTab(false);
      expect(ev.defaultPrevented).toBe(false);
    });
    unmount();
    container.remove();
  });

  it('integrates with a React component using useRef', () => {
    function useHarness() {
      const ref = useRef<HTMLDivElement | null>(null);
      useFocusTrap(ref, true);
      return ref;
    }
    const { result } = renderHook(useHarness);
    expect(result.current.current).toBeNull();
  });
});
