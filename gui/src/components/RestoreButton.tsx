import { useMetadataStore } from '../state/metadataStore';
import { DisabledTooltip } from './DisabledTooltip';
import styles from './RestoreButton.module.css';

export interface RestoreButtonProps {
  /** Called after a successful restore (e.g. to navigate to another screen). */
  onRestored?: () => void;
  /** Confirmation message. Defaults to a Japanese prompt matching the app locale. */
  confirmMessage?: string;
  /** Button label override. */
  label?: string;
  /**
   * Injection point for tests: confirm dialog. Defaults to window.confirm.
   * Replace in tests with a vi.fn() to avoid native dialogs.
   */
  confirmFn?: (message: string) => boolean;
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
    const confirmed = (confirmFn ?? window.confirm)(confirmMessage);
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
