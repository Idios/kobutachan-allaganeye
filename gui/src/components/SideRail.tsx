import styles from './SideRail.module.css';

const ICONS = ['◈', '◇', '◆', '⎊'];

/**
 * Vertical side rail with the ALLAGAN wordmark and 4 (decorative) icons.
 * Mirror of the inline rail in AetherApp (docs/design/bundle/project/variants/aether.jsx lines 438-453).
 */
export function SideRail() {
  return (
    <nav className={styles.rail} aria-label="Allagan Eye navigation">
      <div className={styles.label}>ALLAGAN</div>
      <div className={styles.spacer} />
      {ICONS.map((c, i) => (
        <div
          key={i}
          className={`${styles.icon} ${i === 0 ? styles.iconActive : styles.iconInactive}`}
          aria-hidden="true"
        >
          {c}
        </div>
      ))}
    </nav>
  );
}
