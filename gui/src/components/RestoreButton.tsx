import { ask } from '@tauri-apps/plugin-dialog';

import { useMetadataStore } from '../state/metadataStore';
import { DisabledTooltip } from './DisabledTooltip';
import styles from './RestoreButton.module.css';

/**
 * Default confirm dialog used in production. Tauri 2's WebView2 disables
 * `window.confirm()` for security, so destructive actions must go through
 * the dialog plugin's `ask` (yes/no modal). The confirmFn prop lets tests
 * inject a sync stub.
 */
async function defaultConfirm(message: string): Promise<boolean> {
  return await ask(message, {
    title: '元に戻す',
    kind: 'warning',
  });
}

export interface RestoreButtonProps {
  /** Called after a successful restore (e.g. to navigate to another screen). */
  onRestored?: () => void;
  /** Confirmation message. Defaults to a Japanese prompt matching the app locale. */
  confirmMessage?: string;
  /** Button label override. */
  label?: string;
  /**
   * Injection point for tests: confirm dialog. Defaults to {@link defaultConfirm}
   * (Tauri plugin-dialog `ask`). Tests should pass `vi.fn(() => true|false)` or
   * an async equivalent to avoid spawning native modals.
   */
  confirmFn?: (message: string) => boolean | Promise<boolean>;
}

/**
 * #516: Button that restores metadata.json from metadata.original.json.
 *
 * Behavior:
 * - Disabled when no backup exists (metadataStore.hasBackup === false).
 * - Disabled while a restore is already in flight.
 * - Shows a confirmation dialog before performing the destructive operation.
 * - Displays the last restore error inline.
 * - After a successful restore, `onRestored` is invoked (used by PreviewScreen
 *   to navigate back to the complete screen).
 */
export function RestoreButton({
  onRestored,
  confirmMessage = '編集前の状態に戻しますか？ 適用後の変更は破棄されます。',
  label = '元に戻す',
  confirmFn,
}: RestoreButtonProps) {
  const hasBackup = useMetadataStore((s) => s.hasBackup);
  const restoring = useMetadataStore((s) => s.restoring);
  const restoreError = useMetadataStore((s) => s.restoreError);
  const restore = useMetadataStore((s) => s.restore);

  const disabled = !hasBackup || restoring;
  // #587 §2.3.4 + §2.4.13: surface why [元に戻す] is disabled. Same
  // RestoreButton is rendered from CompleteScreen and PreviewScreen, so
  // wrapping here covers both spec sections at once.
  const reason = !hasBackup
    ? 'バックアップが存在しません'
    : restoring
      ? '復元中です'
      : '';

  async function handleClick() {
    const confirmed = await (confirmFn ?? defaultConfirm)(confirmMessage);
    if (!confirmed) return;
    await restore();
    // Only call onRestored when the store reports no error.
    if (useMetadataStore.getState().restoreError === null && onRestored) {
      onRestored();
    }
  }

  return (
    <>
      <DisabledTooltip disabled={disabled} reason={reason}>
        {(p) => (
          <button
            type="button"
            className={`${styles.button}${restoring ? ` ${styles.busy}` : ''}`}
            disabled={disabled}
            onClick={handleClick}
            aria-label={label}
            {...p}
          >
            {restoring ? '…' : '⟲'} {label}
          </button>
        )}
      </DisabledTooltip>
      {restoreError && (
        <span className={styles.error} role="alert">
          {restoreError}
        </span>
      )}
    </>
  );
}
