export function isSuppressedShortcut(e: KeyboardEvent): boolean {
  const reloadKey = e.key === 'F5';
  const ctrlReload = e.ctrlKey && (e.key === 'r' || e.key === 'R');
  const ctrlShiftReload = e.ctrlKey && e.shiftKey && (e.key === 'R' || e.key === 'F5');
  const devtools =
    e.key === 'F12' ||
    (e.ctrlKey && e.shiftKey && (e.key === 'I' || e.key === 'J' || e.key === 'C'));
  const viewSource = e.ctrlKey && (e.key === 'u' || e.key === 'U');
  const print = e.ctrlKey && (e.key === 'p' || e.key === 'P');
  return reloadKey || ctrlReload || ctrlShiftReload || devtools || viewSource || print;
}

export function installBrowserShortcutSuppressor(win: Window = window): () => void {
  const keydownHandler = (e: KeyboardEvent) => {
    if (isSuppressedShortcut(e)) {
      e.preventDefault();
      e.stopPropagation();
    }
  };
  const contextMenuHandler = (e: Event) => e.preventDefault();
  win.addEventListener('keydown', keydownHandler);
  win.addEventListener('contextmenu', contextMenuHandler);
  return () => {
    win.removeEventListener('keydown', keydownHandler);
    win.removeEventListener('contextmenu', contextMenuHandler);
  };
}
