import { useEffect, type RefObject } from 'react';

/**
 * #587: keep keyboard Tab focus inside a container while it is "active"
 * (typically a dialog / card). On activate, focus jumps to the first
 * focusable inside the container; on deactivate / unmount, focus returns
 * to whichever element had focus before activation.
 *
 * scope policy: keyboard navigation only. We do not add aria-modal /
 * role="dialog" or other screen-reader markup here — the FL video editor
 * does not target screen reader users (see docs/a11y-policy.md).
 */

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

export function useFocusTrap(
  containerRef: RefObject<HTMLElement | null>,
  active: boolean,
): void {
  useEffect(() => {
    if (!active) return;
    const container = containerRef.current;
    if (!container) return;

    const previouslyFocused = document.activeElement as HTMLElement | null;

    const focusables = (): HTMLElement[] =>
      Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));

    // Auto-focus the first focusable when activated. If the container is
    // already focused (or has a child focused), leave the existing focus
    // alone so we don't yank focus mid-interaction.
    if (!container.contains(document.activeElement)) {
      focusables()[0]?.focus();
    }

    function handleKey(e: KeyboardEvent) {
      if (e.key !== 'Tab') return;
      const items = focusables();
      if (items.length === 0) {
        // Nothing focusable: prevent Tab from leaving the container.
        e.preventDefault();
        return;
      }
      const firstEl = items[0];
      const lastEl = items[items.length - 1];
      const activeEl = document.activeElement as HTMLElement | null;
      if (e.shiftKey && activeEl === firstEl) {
        e.preventDefault();
        lastEl.focus();
      } else if (!e.shiftKey && activeEl === lastEl) {
        e.preventDefault();
        firstEl.focus();
      } else if (activeEl && !container?.contains(activeEl)) {
        // Focus has somehow escaped the trap — pull it back. The
        // optional-chaining keeps TS happy across the closure boundary;
        // `container` itself is a stable const captured at effect start.
        e.preventDefault();
        firstEl.focus();
      }
    }

    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('keydown', handleKey);
      // Restore focus to the element that opened the trap, if it still
      // exists in the DOM. Guards against the trap closing because the
      // surrounding screen unmounted (in which case there's nothing to
      // restore to).
      if (previouslyFocused && document.contains(previouslyFocused)) {
        previouslyFocused.focus();
      }
    };
  }, [active, containerRef]);
}
