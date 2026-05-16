import { useMetadataStore } from '../state/metadataStore';
import styles from './SampleModeBanner.module.css';

/**
 * #633 / docs/ui-interaction-spec.md §1.4: sample mode 起動時の上部 inline banner.
 *
 * sample mode = `metadataStore.loadSample()` 経由で in-memory metadata がロード
 * された状態 (`filePath === null && metadata !== null`)。初期 idle (metadata=null)
 * と通常 file (filePath=path) は banner 非表示。
 */
export function SampleModeBanner() {
  const isSample = useMetadataStore(
    (s) => s.filePath === null && s.metadata !== null,
  );
  if (!isSample) return null;
  return (
    <div className={styles.banner}>
      サンプル動画です。実際の動画を選択すると保存できます。
    </div>
  );
}
