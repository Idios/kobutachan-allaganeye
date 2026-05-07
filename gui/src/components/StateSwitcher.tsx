import { useAppStateStore } from '../state/appStateStore';
import type { AppScreen } from '../state/appStateStore';
import styles from './StateSwitcher.module.css';

const SCREEN_LABELS: Record<AppScreen, string> = {
  drop: 'インポート',
  detecting: '検知中',
  complete: '一覧',
  preview: '境界調整',
  export: '書出し',
};

const SCREENS: AppScreen[] = ['drop', 'detecting', 'complete', 'preview', 'export'];

/**
 * Dev-only screen switcher. Lets a developer jump between the 5 screens without
 * going through the real flow. Renders as a floating pill in the top-right.
 *
 * Mirror of FullStateSwitcher in docs/design/bundle/project/variants/aether-preview.jsx.
 */
export function StateSwitcher() {
  // #653 -- production build (Tauri bundle / Portable ZIP) では
  // render しない。CompleteScreen topBar との z-index 重複を原理的に
  // 解消する (spec 2026-05-03-l2-tier1-stateswitcher-dev-only-design.md §3)。
  // import.meta.env.DEV は Vite が build mode で `true` (dev) /
  // `false` (production) に inline 展開され、production build では
  // 本 component の return 後 JSX が dead code elimination で除去される。
  // 注: early return より前の hook subscription は esbuild が保守的に
  // 温存するが、App 直下に 1 回 mount されるだけなので実害なし
  // (callsite-level gating で完全 tree shake する代替案は spec §3 を参照)。
  const screen = useAppStateStore((s) => s.screen);
  const navigate = useAppStateStore((s) => s.navigate);
  if (!import.meta.env.DEV) return null;
  return (
    <div
      className={styles.switcher}
      role="group"
      aria-label="screen switcher (dev)"
    >
      {SCREENS.map((s) => (
        <button
          key={s}
          type="button"
          onClick={() => navigate(s)}
          aria-pressed={screen === s}
          className={`${styles.tab}${screen === s ? ` ${styles.tabActive}` : ''}`}
        >
          {SCREEN_LABELS[s]}
        </button>
      ))}
    </div>
  );
}
