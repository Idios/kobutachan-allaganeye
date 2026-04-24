import { ConflictModal } from './components/ConflictModal';
import { DraftRestoreModal } from './components/DraftRestoreModal';
import { SideRail } from './components/SideRail';
import { StateSwitcher } from './components/StateSwitcher';
import { CompleteScreen } from './screens/CompleteScreen';
import { DetectingScreen } from './screens/DetectingScreen';
import { DropScreen } from './screens/DropScreen';
import { ExportScreen } from './screens/ExportScreen';
import { PreviewScreen } from './screens/PreviewScreen';
import { useAppStateStore } from './state/appStateStore';
import styles from './App.module.css';

/**
 * Root component. Wires the fixed shell (SideRail + StateSwitcher) and
 * switches the main content based on useAppStateStore.screen.
 *
 * The Tauri native Windows title bar is used as-is — no in-app chrome.
 *
 * See docs/ui-architecture.md for the full screen / phase state machines.
 */
export default function App() {
  const screen = useAppStateStore((s) => s.screen);
  const selectedMatchIndex = useAppStateStore((s) => s.selectedMatchIndex);

  // Note: we intentionally do NOT render a custom in-app title bar. Tauri
  // already provides the native Windows title bar (with the min/max/close
  // controls and the "Allagan Eye" title set in tauri.conf.json). The
  // macOS-style traffic-light chrome from the handoff prototype is removed
  // since the product is Windows-only (#451).
  return (
    <div className={styles.root}>
      <StateSwitcher />
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
      {/* #514 — global modal for metadata.json external-modification conflicts. */}
      <ConflictModal />
      {/* #517 — global modal for draft restore offers on mount/post-load. */}
      <DraftRestoreModal />
    </div>
  );
}
