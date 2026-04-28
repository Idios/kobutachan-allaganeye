import { useEffect } from 'react';

/**
 * #587: fire `handler` when Escape is pressed while `active === true`.
 *
 * Used by dialog-like containers (DropScreen.SelectedCard, ErrorCard,
 * ConflictModal, ConfirmExitModal) to dismiss themselves with the
 * keyboard.
 *
 * Note: this hook does not check the focused element's tag. Modals
 * surface Escape even when an input inside them has focus — that
 * matches the modal convention (e.g. macOS sheets). Inputs that need
 * to consume Escape themselves can call `e.stopPropagation()` on their
 * own keydown handler.
 */
export function useEscapeKey(active: boolean, handler: () => void): void {
  useEffect(() => {
    if (!active) return;
    function onKey(e: KeyboardEvent) {
      if (e.key !== 'Escape') return;
      e.preventDefault();
      handler();
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [active, handler]);
}
