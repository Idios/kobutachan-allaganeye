/*
 * KeyboardHints -- 編集画面のキーボードショートカット案内 (#465 review / #1139)。
 *
 * 試合境界エディタ (PreviewScreen) とクリップ範囲の画面 (ClipRangeView) は
 * 同じ割当 (←→ 1s / Shift 10s / Alt 1F / Space 再生・停止) を使うので、
 * 案内も 1 箇所に置く。
 */
import styles from './KeyboardHints.module.css';

export function KeyboardHints() {
  return (
    <div className={styles.keyHint} role="note" aria-label="keyboard shortcuts">
      <span className={styles.keyHintItem}>
        <kbd className={styles.kbd}>←</kbd>
        <kbd className={styles.kbd}>→</kbd> 1s
      </span>
      <span className={styles.keyHintItem}>
        <kbd className={styles.kbd}>Shift</kbd>+<kbd className={styles.kbd}>←→</kbd> 10s
      </span>
      <span className={styles.keyHintItem}>
        <kbd className={styles.kbd}>Alt</kbd>+<kbd className={styles.kbd}>←→</kbd> 1F
      </span>
      <span className={styles.keyHintItem}>
        <kbd className={styles.kbd}>Space</kbd> / クリック: 再生/停止
      </span>
    </div>
  );
}
