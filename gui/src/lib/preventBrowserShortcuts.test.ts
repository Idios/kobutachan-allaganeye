import { describe, it, expect, vi, afterEach } from 'vitest';
import {
  isSuppressedShortcut,
  installBrowserShortcutSuppressor,
} from './preventBrowserShortcuts';

function mkKeyEvent(props: Partial<KeyboardEvent>): KeyboardEvent {
  return {
    key: '',
    ctrlKey: false,
    shiftKey: false,
    altKey: false,
    metaKey: false,
    preventDefault: () => {},
    stopPropagation: () => {},
    ...props,
  } as KeyboardEvent;
}

describe('isSuppressedShortcut', () => {
  const suppressed: Array<[string, Partial<KeyboardEvent>]> = [
    ['F5', { key: 'F5' }],
    ['Ctrl+R (lower)', { ctrlKey: true, key: 'r' }],
    ['Ctrl+R (upper)', { ctrlKey: true, key: 'R' }],
    ['Ctrl+Shift+R', { ctrlKey: true, shiftKey: true, key: 'R' }],
    ['Ctrl+Shift+F5', { ctrlKey: true, shiftKey: true, key: 'F5' }],
    ['F12', { key: 'F12' }],
    ['Ctrl+Shift+I', { ctrlKey: true, shiftKey: true, key: 'I' }],
    ['Ctrl+Shift+J', { ctrlKey: true, shiftKey: true, key: 'J' }],
    ['Ctrl+Shift+C', { ctrlKey: true, shiftKey: true, key: 'C' }],
    ['Ctrl+U (lower)', { ctrlKey: true, key: 'u' }],
    ['Ctrl+U (upper)', { ctrlKey: true, key: 'U' }],
    ['Ctrl+P (lower)', { ctrlKey: true, key: 'p' }],
    ['Ctrl+P (upper)', { ctrlKey: true, key: 'P' }],
  ];

  const allowed: Array<[string, Partial<KeyboardEvent>]> = [
    ['a (plain letter)', { key: 'a' }],
    ['Enter', { key: 'Enter' }],
    ['Escape', { key: 'Escape' }],
    ['Ctrl+A (select all)', { ctrlKey: true, key: 'a' }],
    ['Ctrl+C (copy)', { ctrlKey: true, key: 'c' }],
    ['Ctrl+V (paste)', { ctrlKey: true, key: 'v' }],
    ['Ctrl+Z (undo)', { ctrlKey: true, key: 'z' }],
    ['F1 (unrelated)', { key: 'F1' }],
    ['F11 (fullscreen)', { key: 'F11' }],
    ['Shift+R (no ctrl)', { shiftKey: true, key: 'R' }],
    ['Ctrl+I (no shift, not devtools shortcut)', { ctrlKey: true, key: 'i' }],
  ];

  it.each(suppressed)('suppresses %s', (_label, props) => {
    expect(isSuppressedShortcut(mkKeyEvent(props))).toBe(true);
  });

  it.each(allowed)('allows %s', (_label, props) => {
    expect(isSuppressedShortcut(mkKeyEvent(props))).toBe(false);
  });
});

describe('installBrowserShortcutSuppressor', () => {
  let disposer: (() => void) | null = null;

  afterEach(() => {
    if (disposer) {
      disposer();
      disposer = null;
    }
  });

  it('calls preventDefault + stopPropagation on suppressed keydown', () => {
    disposer = installBrowserShortcutSuppressor(window);
    const preventDefault = vi.fn();
    const stopPropagation = vi.fn();
    const ev = new KeyboardEvent('keydown', { key: 'F5', cancelable: true });
    Object.defineProperty(ev, 'preventDefault', { value: preventDefault });
    Object.defineProperty(ev, 'stopPropagation', { value: stopPropagation });
    window.dispatchEvent(ev);
    expect(preventDefault).toHaveBeenCalledTimes(1);
    expect(stopPropagation).toHaveBeenCalledTimes(1);
  });

  it('does not prevent default on non-suppressed keydown', () => {
    disposer = installBrowserShortcutSuppressor(window);
    const preventDefault = vi.fn();
    const ev = new KeyboardEvent('keydown', { key: 'a', cancelable: true });
    Object.defineProperty(ev, 'preventDefault', { value: preventDefault });
    window.dispatchEvent(ev);
    expect(preventDefault).not.toHaveBeenCalled();
  });

  it('prevents default on contextmenu', () => {
    disposer = installBrowserShortcutSuppressor(window);
    const preventDefault = vi.fn();
    const ev = new Event('contextmenu', { cancelable: true });
    Object.defineProperty(ev, 'preventDefault', { value: preventDefault });
    window.dispatchEvent(ev);
    expect(preventDefault).toHaveBeenCalledTimes(1);
  });

  it('disposer removes listeners', () => {
    const dispose = installBrowserShortcutSuppressor(window);
    dispose();
    const preventDefault = vi.fn();
    const ev = new KeyboardEvent('keydown', { key: 'F5', cancelable: true });
    Object.defineProperty(ev, 'preventDefault', { value: preventDefault });
    window.dispatchEvent(ev);
    expect(preventDefault).not.toHaveBeenCalled();
  });
});
