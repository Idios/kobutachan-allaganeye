import styles from './LoadingSpinner.module.css';

/**
 * #587: visible loading indicator used in DropScreen (and reusable).
 *
 * Replaces inline text like "(選択中)" / "(解析中)" with a spinning
 * sigil + label so that the user gets motion feedback that something
 * is in progress, not just static parenthesized text.
 *
 * scope policy: motion + visible text only. We do NOT add role="status"
 * / aria-live; the FL video editor does not target screen reader users
 * (see docs/a11y-policy.md). The keyframes are defined in
 * gui/src/styles/a11y.css and gated by prefers-reduced-motion.
 */

export interface LoadingSpinnerProps {
  /** Visible label rendered next to the spinner. */
  label: string;
}

export function LoadingSpinner({ label }: LoadingSpinnerProps) {
  return (
    <span className={styles.wrap}>
      <span className={styles.spin} aria-hidden="true">
        ⟳
      </span>
      <span className={styles.label}>{label}</span>
    </span>
  );
}
