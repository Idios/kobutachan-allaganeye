import { useMetadataStore } from '../state/metadataStore';
import styles from './ConflictModal.module.css';

/**
 * #514: modal surfaced when `apply_changes` returns a conflict error because
 * metadata.json was modified externally between load and apply.
 *
 * Three exits:
 * - 上書き: re-run apply with the mtime check bypassed (external edits lost).
 * - リロード: discard in-memory edits and re-load metadata.json from disk.
 * - キャンセル: close the modal without touching disk (edits stay in store).
 *
 * Global modal — rendered once in App.tsx regardless of the current screen.
 */
export function ConflictModal() {
  const conflictError = useMetadataStore((s) => s.conflictError);
  const applying = useMetadataStore((s) => s.applying);
  const applyOverwrite = useMetadataStore((s) => s.applyOverwrite);
  const reloadAfterConflict = useMetadataStore((s) => s.reloadAfterConflict);
  const dismissConflict = useMetadataStore((s) => s.dismissConflict);

  if (!conflictError) return null;

  return (
    <div
      className={styles.backdrop}
      role="dialog"
      aria-modal="true"
      aria-labelledby="ae-conflict-title"
    >
      <div className={styles.panel}>
        <h2 id="ae-conflict-title" className={styles.title}>
          metadata.json が外部で変更されました
        </h2>
        <p className={styles.message}>{conflictError}</p>
        <p className={styles.hint}>
          「上書き」で外部変更を破棄し GUI の編集を適用、「リロード」で最新の metadata.json を読み直し (編集は破棄)、「キャンセル」で何もせずこのモーダルを閉じます。
        </p>
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.button}
            onClick={() => {
              void applyOverwrite();
            }}
            disabled={applying}
          >
            上書き
          </button>
          <button
            type="button"
            className={styles.button}
            onClick={() => {
              void reloadAfterConflict();
            }}
            disabled={applying}
          >
            リロード
          </button>
          <button
            type="button"
            className={styles.button}
            onClick={() => dismissConflict()}
            disabled={applying}
          >
            キャンセル
          </button>
        </div>
      </div>
    </div>
  );
}
