import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { useEscapeKey } from './useEscapeKey';

function fireKey(key: string) {
  const ev = new KeyboardEvent('keydown', {
    key,
    bubbles: true,
    cancelable: true,
  });
  document.dispatchEvent(ev);
  return ev;
}

describe('useEscapeKey', () => {
  it('fires the handler on Escape when active', () => {
    const handler = vi.fn();
    renderHook(() => useEscapeKey(true, handler));
    act(() => {
      fireKey('Escape');
    });
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it('does not fire when active is false', () => {
    const handler = vi.fn();
    renderHook(() => useEscapeKey(false, handler));
    act(() => {
      fireKey('Escape');
    });
    expect(handler).not.toHaveBeenCalled();
  });

  it('ignores non-Escape keys', () => {
    const handler = vi.fn();
    renderHook(() => useEscapeKey(true, handler));
    act(() => {
      fireKey('Enter');
      fireKey(' ');
      fireKey('a');
    });
    expect(handler).not.toHaveBeenCalled();
  });

  it('prevents the default Escape action while active', () => {
    const handler = vi.fn();
    renderHook(() => useEscapeKey(true, handler));
    let ev: KeyboardEvent | undefined;
    act(() => {
      ev = fireKey('Escape');
    });
    expect(ev?.defaultPrevented).toBe(true);
  });

  it('removes its listener on unmount', () => {
    const handler = vi.fn();
    const { unmount } = renderHook(() => useEscapeKey(true, handler));
    unmount();
    act(() => {
      fireKey('Escape');
    });
    expect(handler).not.toHaveBeenCalled();
  });

  it('updates when active toggles from true to false', () => {
    const handler = vi.fn();
    const { rerender, unmount } = renderHook(
      ({ active }: { active: boolean }) => useEscapeKey(active, handler),
      { initialProps: { active: true } },
    );
    act(() => {
      fireKey('Escape');
    });
    expect(handler).toHaveBeenCalledTimes(1);
    rerender({ active: false });
    act(() => {
      fireKey('Escape');
    });
    expect(handler).toHaveBeenCalledTimes(1);
    unmount();
  });
});
