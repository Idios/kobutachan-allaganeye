import type { ReactNode } from 'react';
import styles from './DisabledTooltip.module.css';

/**
 * #587 / docs/ui-interaction-spec.md §1.2: surface the *reason* a button
 * (or other interactive element) is disabled.
 *
 * - tooltip via the native `title` attribute (mouse hover) — handled by
 *   spreading the props the render prop returns.
 * - optional inline hint rendered below the wrapped element in the
 *   muted aether-text-dim color, used for primary CTAs (per §1.2).
 *
 * scope policy: this component is for sighted + mouse users. We do
 * NOT add `aria-describedby` or other screen-reader markup; the FL
 * video editor does not target screen reader users (see
 * docs/a11y-policy.md).
 */

export interface DisabledTooltipProps {
  /** When true, the wrapped element is in a disabled state and the reason should be surfaced. */
  disabled: boolean;
  /**
   * Canonical reason text (used for the title tooltip and the optional
   * inline hint). Should include a forward action ("実際の動画を選択
   * してください") rather than a bare negative ("選択されていません").
   */
  reason: string;
  /** When true, also render the reason as a small visible hint below the element. */
  inlineHint?: boolean;
  /**
   * Render-prop receiving the props that must be spread onto the wrapped
   * element. When `disabled === true` this includes a non-empty `title`;
   * when `disabled === false` both fields are `undefined` so the wrapped
   * element gets no native tooltip.
   */
  children: (injected: { title: string | undefined }) => ReactNode;
}

export function DisabledTooltip({
  disabled,
  reason,
  inlineHint = false,
  children,
}: DisabledTooltipProps) {
  const title = disabled && reason ? reason : undefined;
  return (
    <span className={styles.wrapper}>
      {children({ title })}
      {disabled && inlineHint && reason && (
        <span className={styles.inlineHint}>{reason}</span>
      )}
    </span>
  );
}
