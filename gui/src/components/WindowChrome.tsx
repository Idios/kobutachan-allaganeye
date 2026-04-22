import styles from './WindowChrome.module.css';

export interface WindowChromeProps {
  title: string;
}

/**
 * The macOS-inspired window title bar used at the top of the shell.
 * Mirror of WindowChrome in docs/design/bundle/project/shared/common.jsx.
 * Uses -webkit-app-region: drag to make the bar draggable in Tauri.
 */
export function WindowChrome({ title }: WindowChromeProps) {
  return (
    <div className={styles.chrome} data-testid="window-chrome">
      <div className={styles.trafficLights} aria-hidden="true">
        <div className={`${styles.dot} ${styles.dotClose}`} />
        <div className={`${styles.dot} ${styles.dotMin}`} />
        <div className={`${styles.dot} ${styles.dotMax}`} />
      </div>
      <div className={styles.title}>{title}</div>
      <div className={styles.spacer} />
    </div>
  );
}
