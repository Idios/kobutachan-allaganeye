import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';
import { useEffect, useReducer, useState } from 'react';

import { AllaganSigil } from '../components/AllaganSigil';
import { useAppStateStore } from '../state/appStateStore';
import { useMetadataStore } from '../state/metadataStore';
import {
  deriveDetectOutputDir,
  metadataPathFor,
} from '../utils/detectOutputDir';
import { detectingReducer } from './reducers/detecting';
import type { DetectingPhase } from './types';
import styles from './DetectingScreen.module.css';

/**
 * #569 -- payload shape emitted by Rust `start_detect` on channel
 * `detect-progress`. The fields mirror the JSON schema written by
 * `allaganeye/detection/progress_emitter.py`. Optional fields are
 * present only when the CLI included them (skip_serializing_if drops
 * `None` at the source).
 */
interface DetectProgressEvent {
  phase: string;
  completed?: number;
  total?: number;
  elapsed_s?: number;
  eta_s?: number;
  blackout_frames?: number;
  metadata_path?: string;
  matches?: number;
  message?: string;
  duration_s?: number;
  width?: number;
  height?: number;
  fps?: number;
  codec?: string;
  chunks?: number;
  boundaries?: number;
}

interface DetectResult {
  metadata_path: string;
  matches: number;
}

/**
 * Phase weight map used to compute the overall percent (the CLI emits
 * per-phase `(completed, total)` so the detecting bar can advance even
 * within a phase). Tuned to match the rough wall-clock breakdown on
 * a 2:50 hour 1080p recording: Pass 1 dominates, scorebar lasts a few
 * seconds, metadata write is essentially instant.
 *
 * Each entry is `[start_pct, end_pct]`. Phases that arrive out of
 * order (e.g. cache_hit replacing scan/refine) snap straight to their
 * window's end so the bar never reverses.
 */
const PHASE_WINDOWS: Record<string, [number, number]> = {
  start: [0, 1],
  probing: [1, 3],
  chunk_dispatch: [3, 5],
  chunk: [5, 30],
  scan: [3, 70],
  refine: [70, 88],
  scorebar: [88, 97],
  audio: [3, 60],
  cache_hit: [0, 99],
  writing_metadata: [99, 100],
  done: [100, 100],
  error: [0, 0],
};

function computeOverallPercent(event: DetectProgressEvent): number {
  const window = PHASE_WINDOWS[event.phase];
  if (!window) return 0;
  const [start, end] = window;
  const range = end - start;
  if (
    range <= 0 ||
    event.total === undefined ||
    event.completed === undefined ||
    event.total <= 0
  ) {
    return start;
  }
  const inner = Math.min(1, Math.max(0, event.completed / event.total));
  return start + range * inner;
}

interface LogEntry {
  ts: number;
  text: string;
}

function buildLogText(event: DetectProgressEvent): string | null {
  switch (event.phase) {
    case 'start':
      return 'detect 開始';
    case 'probing':
      if (event.duration_s && event.codec) {
        return `probe: duration=${event.duration_s.toFixed(1)}s codec=${event.codec} ${event.width ?? '?'}x${event.height ?? '?'}@${(event.fps ?? 0).toFixed(2)}fps`;
      }
      return 'ffprobe 完了';
    case 'cache_hit':
      return `キャッシュヒット (${event.boundaries ?? '?'} boundaries)`;
    case 'chunk_dispatch':
      return `チャンク分割: ${event.chunks ?? '?'} 個を並列デコード`;
    case 'chunk':
      if (event.completed !== undefined && event.total !== undefined) {
        return `チャンク完了 ${event.completed}/${event.total}`;
      }
      return null;
    case 'scan':
      // Skip very chatty per-sample updates -- only log every 10%.
      if (
        event.completed !== undefined &&
        event.total !== undefined &&
        event.total > 0
      ) {
        const pct = (event.completed / event.total) * 100;
        if (pct % 10 < 0.5 || event.completed === event.total) {
          return `Pass 1 scan: ${event.completed}/${event.total} (${pct.toFixed(0)}%)`;
        }
      }
      return null;
    case 'refine':
      if (event.completed !== undefined && event.total !== undefined) {
        return `Pass 2 refine: ${event.completed}/${event.total}`;
      }
      return 'Pass 2 refine 開始';
    case 'scorebar':
      if (event.completed !== undefined && event.total !== undefined) {
        return `scorebar 分類: ${event.completed}/${event.total}`;
      }
      return 'scorebar 分類';
    case 'audio':
      return 'audio Fanfare scan';
    case 'writing_metadata':
      return 'metadata.json 書き込み中…';
    case 'done':
      return `完了: ${event.matches ?? '?'} matches`;
    case 'error':
      return `エラー: ${event.message ?? 'unknown'}`;
    default:
      return null;
  }
}

const MAX_LOG_LINES = 80;

function fmtElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

function computeEta(percent: number, elapsed: number): number | null {
  if (percent <= 0 || percent >= 100) return null;
  const total = elapsed * (100 / percent);
  const remaining = total - elapsed;
  return remaining > 0 ? remaining : null;
}

/**
 * #569 Phase 2.5 — DetectingScreen real implementation.
 *
 * Spawns ``allaganeye detect --progress-format json`` via the Rust
 * ``start_detect`` Tauri command, listens to ``detect-progress``
 * events, and drives the same DetectingPhase reducer the Phase 2
 * dummy used. On the terminal "done" event we load metadata.json
 * via the existing metadataStore.load() and navigate to complete.
 *
 * Cancel button: dispatches ``CANCEL_CLICKED`` so the reducer enters
 * ``cancelling``. The actual ffmpeg/process kill arrives in #523's PR
 * (next PR in the alpha group); for this PR the running subprocess is
 * left to finish on its own and the user sees the cancellation echoed
 * in the UI.
 */
export function DetectingScreen() {
  const navigate = useAppStateStore((s) => s.navigate);
  const selectedVideoPath = useAppStateStore((s) => s.selectedVideoPath);
  const loadMetadata = useMetadataStore((s) => s.load);
  const loadSample = useMetadataStore((s) => s.loadSample);

  const [phase, dispatch] = useReducer(
    detectingReducer,
    'running' as DetectingPhase,
  );
  const [progress, setProgress] = useState(0);
  const [phaseLabel, setPhaseLabel] = useState<string>('start');
  const [log, setLog] = useState<LogEntry[]>([]);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  // Captured once on first mount via lazy initialiser so log entries
  // can compute their relative timestamp inside render. We never need
  // to update this value -- the screen unmounts when navigating away,
  // and a fresh detect run remounts the component (App.tsx routes by
  // screen). Avoids the react-hooks/set-state-in-effect lint warning
  // a setState-in-effect initialiser would trip.
  const [startedAt] = useState<number>(() => Date.now());

  // Wall-clock elapsed timer -- ticks once per second so the UI can
  // show "経過 00:42 / 残り ~01:30" without depending on event cadence.
  useEffect(() => {
    if (phase !== 'running') return;
    const id = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => clearInterval(id);
  }, [phase, startedAt]);

  // Subscribe to detect-progress, kick off start_detect.
  useEffect(() => {
    let unlisten: UnlistenFn | undefined;
    let cancelled = false;

    async function run() {
      // Sample mode: no real video, fall through to the dummy data so
      // the StateSwitcher dev tab still works.
      if (!selectedVideoPath) {
        loadSample();
        navigate('complete');
        return;
      }

      const outputDir = deriveDetectOutputDir(selectedVideoPath);

      try {
        unlisten = await listen<DetectProgressEvent>(
          'detect-progress',
          (event) => {
            if (cancelled) return;
            const payload = event.payload;
            setPhaseLabel(payload.phase);

            const text = buildLogText(payload);
            if (text !== null) {
              setLog((prev) => {
                const next = [...prev, { ts: Date.now(), text }];
                return next.length > MAX_LOG_LINES
                  ? next.slice(next.length - MAX_LOG_LINES)
                  : next;
              });
            }

            if (payload.phase === 'error') {
              setError(payload.message ?? 'unknown error');
              dispatch({ type: 'DETECT_ERROR' });
              return;
            }

            const pct = computeOverallPercent(payload);
            // Bar is monotonic -- never reverse on out-of-order events
            // (e.g. cache_hit firing after a probing event).
            setProgress((prev) => (pct > prev ? pct : prev));
          },
        );

        const result = await invoke<DetectResult>('start_detect', {
          videoPath: selectedVideoPath,
          outputDir,
          params: {},
        });
        if (cancelled) return;

        setProgress(100);
        const metaPath = result.metadata_path || metadataPathFor(outputDir);
        await loadMetadata(metaPath);
        dispatch({ type: 'PROGRESS_COMPLETE' });
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
        dispatch({ type: 'DETECT_ERROR' });
      }
    }

    void run();
    return () => {
      cancelled = true;
      if (unlisten) unlisten();
    };
    // selectedVideoPath / loadMetadata / loadSample / navigate are
    // store-bound and stable; we re-run only if the user re-enters the
    // screen with a different video, which already remounts via the
    // App.tsx screen switch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // completed → navigate to complete (load happened above)
  useEffect(() => {
    if (phase === 'completed') {
      navigate('complete');
    }
  }, [phase, navigate]);

  // cancelled / error → back to drop
  useEffect(() => {
    if (phase === 'cancelled' || phase === 'error') {
      navigate('drop');
    }
  }, [phase, navigate]);

  // Cancel button: phase transition only. Real ffmpeg kill ships in
  // #523's PR via kill_tracked_processes; this PR keeps the issue's
  // explicit scope ("UI phase transition only").
  useEffect(() => {
    if (phase === 'cancelling') {
      dispatch({ type: 'CANCEL_CONFIRMED' });
    }
  }, [phase]);

  const pct1 = Math.min(100, progress * (100 / 70)); // scan finishes at 70%
  const pct2 = Math.max(0, Math.min(100, ((progress - 70) * 100) / 18)); // refine fills 70-88

  const displayFile = selectedVideoPath?.split(/[/\\]/).pop() ?? '(video)';
  const eta = computeEta(progress, elapsed);

  return (
    <div className={styles.screen} data-testid="detecting-screen">
      <div className={styles.header}>
        <AllaganSigil size={84} rotating={phase === 'running'} />
        <div className={styles.headerText}>
          <div className={styles.caption}>観測中</div>
          <div className={styles.fileName}>{displayFile}</div>
          <div className={styles.meta}>
            phase: {phaseLabel}
            {error ? ` · error: ${error}` : ''}
          </div>
        </div>
        <div className={styles.progressBadge}>
          <div className={styles.progressNum}>{Math.round(progress)}%</div>
          <div className={styles.progressTiming}>
            経過 {fmtElapsed(elapsed)}
            {eta !== null && ` · 残り ~${fmtElapsed(eta)}`}
          </div>
        </div>
      </div>

      <div className={styles.divider} />

      <div className={styles.phases}>
        <PhaseRow name="Detecting" jp="粗スキャン" pct={pct1} sub="scan" />
        <PhaseRow name="Refining" jp="精密計測" pct={pct2} sub="refine" />
      </div>

      <div className={styles.divider} />

      <div className={styles.log} role="log" aria-label="detect log">
        {log.length === 0 && (
          <div>
            <span className={styles.logTime}>[--:--]</span> 起動中…
          </div>
        )}
        {log.map((entry, idx) => {
          const tsRel = entry.ts - startedAt;
          const tsLabel = fmtElapsed(Math.max(0, Math.floor(tsRel / 1000)));
          const isLast = idx === log.length - 1;
          return (
            <div key={`${entry.ts}-${idx}`}>
              <span
                className={
                  isLast ? styles.logTimeActive : styles.logTime
                }
              >
                [{tsLabel}]
              </span>{' '}
              {entry.text}
            </div>
          );
        })}
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

// Re-export pure helpers so unit tests can exercise them without
// mounting the React component or stubbing Tauri.
export {
  computeOverallPercent,
  computeEta,
  buildLogText,
  PHASE_WINDOWS,
};
