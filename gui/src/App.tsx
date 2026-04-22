import { SideRail } from './components/SideRail';
import { StateSwitcher } from './components/StateSwitcher';
import { WindowChrome } from './components/WindowChrome';
import { CompleteScreen } from './screens/CompleteScreen';
import { DetectingScreen } from './screens/DetectingScreen';
import { DropScreen } from './screens/DropScreen';
import { ExportScreen } from './screens/ExportScreen';
import { PreviewScreen } from './screens/PreviewScreen';
import { useAppStateStore } from './state/appStateStore';
import styles from './App.module.css';

/**
 * Root component. Wires the fixed shell (WindowChrome + SideRail +
 * StateSwitcher) and switches the main content based on useAppStateStore.screen.
 *
 * See docs/ui-architecture.md for the full screen / phase state machines.
 */
export default function App() {
  const screen = useAppStateStore((s) => s.screen);
  const selectedMatchIndex = useAppStateStore((s) => s.selectedMatchIndex);

  return (
    <div className={styles.root}>
      <StateSwitcher />
      <WindowChrome title="Allagan Eye" />
      <div className={styles.body}>
        <SideRail />
        <main className={styles.main}>
          {screen === 'drop' && <DropScreen />}
          {screen === 'detecting' && <DetectingScreen />}
          {screen === 'complete' && <CompleteScreen />}
          {/* key={selectedMatchIndex} ensures PreviewScreen's local draft
              state resets each time the user opens a different match. */}
          {screen === 'preview' && (
            <PreviewScreen key={selectedMatchIndex ?? 'none'} />
          )}
          {screen === 'export' && <ExportScreen />}
        </main>
      </div>
    </div>
  );
}
