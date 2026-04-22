import { useEffect, useReducer, useState } from 'react';

import { AllaganSigil } from '../components/AllaganSigil';
import { useAppStateStore } from '../state/appStateStore';
import { useMetadataStore } from '../state/metadataStore';
import { detectingReducer } from './reducers/detecting';
import type { DetectingPhase } from './types';
import styles from './DetectingScreen.module.css';

/** 80ms * 100 ticks = 8s simulated detect run (Phase 2 dummy). */
const TICK_MS = 80;
const TICKS_TO_COMPLETE = 100;

/**
 * Phase 2: pure UI + 8-second dummy progress driving detectingReducer.
 * On PROGRESS_COMPLETE, loadSample() is called so the complete screen has
 * data, then we navigate to complete. Phase 3 (#465) replaces the dummy
 * interval with real CLI stdout events.
 */
export function DetectingScreen() {
  const navigate = useAppStateStore((s) => s.navigate);
  const selectedVideoPath = useAppStateStore((s) => s.selectedVideoPath);
  const setSelectedVideoPath = useAppStateStore((s) => s.setSelectedVideoPath);
  const loadSample = useMetadataStore((s) => s.loadSample);

  const [phase, dispatch] = useReducer(detectingReducer, 'running' as DetectingPhase);
  const [progress, setProgress] = useState(0);

  // dummy progress interval
  useEffect(() => {
    if (phase !== 'running') return;
    const iv = setInterval(() => {
      setProgress((p) => {
        const next = p + 100 / TICKS_TO_COMPLETE;
        if (next >= 100) {
          clearInterval(iv);
          dispatch({ type: 'PROGRESS_COMPLETE' });
          return 100;
        }
        return next;
      });
    }, TICK_MS);
    return () => clearInterval(iv);
  }, [phase]);

  // completed → load sample data + move to complete
  useEffect(() => {
    if (phase === 'completed') {
      loadSample();
      setSelectedVideoPath(null);
      navigate('complete');
    }
  }, [phase, loadSample, navigate, setSelectedVideoPath]);

  // cancelled → back to drop
  useEffect(() => {
    if (phase === 'cancelled') {
      navigate('drop');
    }
  }, [phase, navigate]);

  // error → back to drop (Phase 3 will toast)
  useEffect(() => {
    if (phase === 'error') {
      navigate('drop');
    }
  }, [phase, navigate]);

  // Phase 2 auto-confirms the cancel immediately (no real process to kill).
  useEffect(() => {
    if (phase === 'cancelling') {
      dispatch({ type: 'CANCEL_CONFIRMED' });
    }
  }, [phase]);

  const pct1 = Math.min(100, Math.max(0, progress * 1.25)); // phase 1 finishes quickly
  const pct2 = Math.max(0, Math.min(100, (progress - 40) * 1.67));
  const displayFile = selectedVideoPath?.split(/[/\\]/).pop() ?? '(video)';

  return (
    <div className={styles.screen} data-testid="detecting-screen">
      <div className={styles.header}>
        <AllaganSigil size={84} rotating={phase === 'running'} />
        <div className={styles.headerText}>
          <div className={styles.caption}>観測中</div>
          <div className={styles.fileName}>{displayFile}</div>
          <div className={styles.meta}>dummy probe · Phase 2 skeleton</div>
        </div>
        <div className={styles.progressBadge}>
          <div className={styles.progressNum}>{Math.round(progress)}%</div>
          <div className={styles.progressTiming}>
            Phase 2 dummy
          </div>
        </div>
      </div>

      <div className={styles.divider} />

      <div className={styles.phases}>
        <PhaseRow
          name="Detecting"
          jp="粗スキャン"
          pct={pct1}
          sub="scan"
        />
        <PhaseRow
          name="Refining"
          jp="精密計測"
          pct={pct2}
          sub="refine"
        />
      </div>

      <div className={styles.divider} />

      <div className={styles.log} role="log" aria-label="detect log">
        <div>
          <span className={styles.logTime}>[00:00]</span> dummy detect started
        </div>
        {progress >= 30 && (
          <div>
            <span className={styles.logTime}>[00:02]</span> scan: samples…
          </div>
        )}
        {progress >= 60 && (
          <div>
            <span className={styles.logTimeActive}>[00:05]</span> refining
            boundaries…
          </div>
        )}
      </div>

      <div className={styles.actions}>
        <button
          type="button"
          className={styles.cancelButton}
          disabled={phase !== 'running'}
          onClick={() => dispatch({ type: 'CANCEL_CLICKED' })}
        >
          中断
        </button>
      </div>
    </div>
  );
}

interface PhaseRowProps {
  name: string;
  jp: string;
  pct: number;
  sub: string;
}

function PhaseRow({ name, jp, pct, sub }: PhaseRowProps) {
  const className =
    pct >= 100
      ? styles.phaseNameDone
      : pct > 0
        ? styles.phaseNameRunning
        : styles.phaseNamePending;
  const fillClass =
    pct >= 100 ? `${styles.barFill} ${styles.barFillDone}` : styles.barFill;
  return (
    <div className={styles.phaseRow}>
      <div className={styles.phaseLabel}>
        <span className={`${styles.phaseName} ${className}`}>{name}</span>
        <span className={styles.phaseJp}>{jp}</span>
        <span className={styles.spacer} />
        <span className={styles.phaseSub}>{sub}</span>
        <span className={styles.phaseTime}>{Math.round(pct)}%</span>
      </div>
      <div className={styles.bar}>
        <div className={fillClass} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
