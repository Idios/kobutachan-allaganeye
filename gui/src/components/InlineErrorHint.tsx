import type { JSX } from 'react';

import styles from './InlineErrorHint.module.css';

export interface InlineErrorHintProps {
  /** Hint text. When `null` / `undefined` / empty, the component renders nothing. */
  hint: string | null | undefined;
}

/**
 * #693: 5 既存 site (RestoreButton / DropScreen ErrorCard / DetectingScreen /
 * PreviewScreen / ExportScreen) + 新規 3 site (#695 ConflictModal / #697
 * DraftRestoreModal / #698 DropScreen recentNotice) で共有される、AppError
 * の `hint` を inline error の 2 行目に表示するための小さな component。
 *
 * - `💡` prefix は本 component で集中管理 (i18n / theme 切替時の修正点を 1 箇所に)
 * - a11y: 本 component 自身に `role` を付けない (consumer 側 `role="alert"` wrapper
 *   の内側に nest する規約、Phase 4 #689 で確立)
 * - 文字色 = `var(--ae-text-dim)`、サイズ・表示の細部は site-specific wrapper
 *   class で override 可能 (本 component は最小 layout のみ提供)
 */
export function InlineErrorHint({ hint }: InlineErrorHintProps): JSX.Element | null {
  if (!hint) return null;
  return <span className={styles.hint}>💡 {hint}</span>;
}
