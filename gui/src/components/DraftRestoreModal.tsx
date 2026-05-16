import { useMetadataStore } from '../state/metadataStore';
import styles from './DraftRestoreModal.module.css';
import { InlineErrorHint } from './InlineErrorHint';

/**
 * #517: modal offered on mount / after load when a `metadata.draft.json`
 * exists for the current metadata file. User chooses whether to apply the
 * draft to the in-memory buffer (then 適用 to persist) or discard it.
 *
 * Global modal — rendered once in App.tsx regardless of the current screen.
 */
export function DraftRestoreModal() {
  const pendingDraft = useMetadataStore((s) => s.pendingDraft);
  const draftLoadErrorState = useMetadataStore((s) => s.draftLoadErrorState);
  const conflictErrorState = useMetadataStore((s) => s.conflictErrorState);
  const restoreDraft = useMetadataStore((s) => s.restoreDraft);
  const discardDraft = useMetadataStore((s) => s.discardDraft);

  // #517 × #514: ConflictModal は metadata 本体の同期が優先。draft restore は
  // conflict 解消後に提示する (Modal 同時表示による UX 崩壊を回避)。
  if (conflictErrorState) return null;
  if (!pendingDraft && !draftLoadErrorState) return null;

  if (draftLoadErrorState) {
    // Draft existed but could not be parsed — offer discard only.
    return (
      <div
        className={styles.backdrop}
        role="dialog"
        aria-modal="true"
        aria-labelledby="ae-draft-error-title"
      >
        <div className={styles.panel}>
          <h2 id="ae-draft-error-title" className={styles.title}>
            draft を読み取れませんでした
          </h2>
          <p className={styles.message}>{draftLoadErrorState.message}</p>
          <InlineErrorHint hint={draftLoadErrorState.hint} />
          <p className={styles.hint}>
            metadata.draft.json が破損しているか schema が一致しません。破棄して続行します。
          </p>
          <div className={styles.actions}>
            <button
              type="button"
              className={styles.button}
              onClick={() => {
                void discardDraft();
              }}
            >
              破棄
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className={styles.backdrop}
      role="dialog"
      aria-modal="true"
      aria-labelledby="ae-draft-restore-title"
    >
      <div className={styles.panel}>
        <h2 id="ae-draft-restore-title" className={styles.title}>
          編集中の draft を復元しますか?
        </h2>
        <p className={styles.hint}>
          前回の編集内容が metadata.draft.json に保存されています。「復元」で編集バッファに適用 (適用ボタンで metadata.json に反映)、「破棄」で draft を削除して現行の metadata.json を使用します。
        </p>
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.button}
            onClick={() => restoreDraft()}
          >
            復元
          </button>
          <button
            type="button"
            className={styles.button}
            onClick={() => {
              void discardDraft();
            }}
          >
            破棄
          </button>
        </div>
      </div>
    </div>
  );
}
