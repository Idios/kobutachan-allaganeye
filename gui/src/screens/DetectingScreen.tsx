import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';
import { useEffect, useReducer, useRef, useState } from 'react';

import { AllaganSigil } from '../components/AllaganSigil';
import { DisabledTooltip } from '../components/DisabledTooltip';
import { InlineErrorHint } from '../components/InlineErrorHint';
import { toErrorState } from '../lib/appError';
import { useAppStateStore } from '../state/appStateStore';
import { useMetadataStore } from '../state/metadataStore';
import { toStartDetectParams } from '../utils/detection';
import {
  deriveDetectOutputDir,
  metadataPathFor,
} from '../utils/detectOutputDir';
import { splitPath } from '../utils/path';
import { fmtTime } from '../utils/time';
import { detectingReducer } from './reducers/detecting';
import type { DetectingPhase } from './types';
import pathStyles from '../styles/path-display.module.css';
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
  // #813 -- run identifier echoed by Rust `start_detect` on every event so
  // the listener can fence out stragglers from a previous (cancelled) run.
  // Absent only on synthetic / unit-test payloads.
  run_id?: string;
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

/**
 * #569 Phase 2.5 (review Round 1 課題 2) -- log entry severity for the
 * keyword colour-coding requirement. The CLI emits a `phase` string;
 * `buildLogText` maps it to one of these four severities so the live
 * log can highlight terminal / faulty / warned events without the user
 * having to read every line.
 *
 * - `info`: routine progress (start / probing / scan / refine / scorebar / chunk* / audio / writing_metadata)
 * - `done`: terminal success (`phase="done"`) -- styled cyan-bright
 * - `error`: terminal failure (`phase="error"`) -- styled `--ae-danger`
 * - `warn`: notable non-fatal events (`phase="cache_hit"` for now;
 *   future expansions: scorebar warnings, audio scan skips, etc.) --
 *   styled `--ae-gold-bright`
 */
type LogKind = 'info' | 'done' | 'error' | 'warn';

interface LogEntry {
  ts: number;
  text: string;
  kind: LogKind;
}

interface BuildLogResult {
  text: string;
  kind: LogKind;
}

function buildLogText(event: DetectProgressEvent): BuildLogResult | null {
  switch (event.phase) {
    case 'start':
      return { text: 'detect 開始', kind: 'info' };
    case 'probing':
      if (event.duration_s && event.codec) {
        return {
          text: `probe: duration=${event.duration_s.toFixed(1)}s codec=${event.codec} ${event.width ?? '?'}x${event.height ?? '?'}@${(event.fps ?? 0).toFixed(2)}fps`,
          kind: 'info',
        };
      }
      return { text: 'ffprobe 完了', kind: 'info' };
    case 'cache_hit':
      // cache_hit はエラーではないが、利用者には「Pass 1 / 2 を skip
      // した」ことが伝わるべき非自明な分岐なので warn 色で目立たせる。
      return {
        text: `キャッシュヒット (${event.boundaries ?? '?'} boundaries)`,
        kind: 'warn',
      };
    case 'chunk_dispatch':
      return {
        text: `チャンク分割: ${event.chunks ?? '?'} 個を並列デコード`,
        kind: 'info',
      };
    case 'chunk':
      if (event.completed !== undefined && event.total !== undefined) {
        return {
          text: `チャンク完了 ${event.completed}/${event.total}`,
          kind: 'info',
        };
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
          return {
            text: `Pass 1 scan: ${event.completed}/${event.total} (${pct.toFixed(0)}%)`,
            kind: 'info',
          };
        }
      }
      return null;
    case 'refine':
      if (event.completed !== undefined && event.total !== undefined) {
        return {
          text: `Pass 2 refine: ${event.completed}/${event.total}`,
          kind: 'info',
        };
      }
      return { text: 'Pass 2 refine 開始', kind: 'info' };
    case 'scorebar':
      if (event.completed !== undefined && event.total !== undefined) {
        return {
          text: `scorebar 分類: ${event.completed}/${event.total}`,
          kind: 'info',
        };
      }
      return { text: 'scorebar 分類', kind: 'info' };
    case 'audio':
      return { text: 'audio Fanfare scan', kind: 'info' };
    case 'writing_metadata':
      return { text: 'metadata.json 書き込み中…', kind: 'info' };
    case 'done':
      return { text: `完了: ${event.matches ?? '?'} matches`, kind: 'done' };
    case 'error':
      return {
        text: `エラー: ${event.message ?? 'unknown'}`,
        kind: 'error',
      };
    default:
      return null;
  }
}

/**
 * #569 review Round 1 課題 1 -- ffprobe metadata captured from the
 * `probing` event. Pre-#569 the meta line was a hard-coded "dummy
 * probe · Phase 2 skeleton" string; now it reflects the actual
 * resolution / fps / codec / duration the CLI just measured. `null`
 * before the `probing` event arrives, so the line falls back to a
 * `phase: ...` indicator in that brief window.
 */
interface ProbeInfo {
  width?: number;
  height?: number;
  fps?: number;
  codec?: string;
  duration_s?: number;
}

function formatProbeMeta(info: ProbeInfo): string {
  const parts: string[] = [];
  if (info.width !== undefined && info.height !== undefined) {
    parts.push(`${info.width}x${info.height}`);
  }
  if (info.fps !== undefined) {
    parts.push(`${info.fps.toFixed(2)}fps`);
  }
  if (info.codec) {
    parts.push(info.codec);
  }
  if (info.duration_s !== undefined) {
    parts.push(fmtTime(info.duration_s));
  }
  return parts.join(' · ');
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
 * #813 -- run id used to fence detect-progress events to the current run.
 * Prefers crypto.randomUUID, but falls back to a timestamp+random token so a
 * WebView runtime without crypto.randomUUID (old WebView2 / non-secure
 * context) can't make detect hang. The id only needs to be unique per run,
 * not cryptographically strong.
 */
function generateRunId(): string {
  try {
    if (
      typeof crypto !== 'undefined' &&
      typeof crypto.randomUUID === 'function'
    ) {
      return crypto.randomUUID();
    }
  } catch {
    // fall through to the non-crypto fallback below
  }
  return `run-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
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
 * ``cancelling``. The cancelling effect then invokes
 * ``kill_tracked_processes`` (#813) to reap the running detect (Python CLI
 * + ffmpeg children) before confirming the cancel, so no orphaned
 * processes survive.
 */
export function DetectingScreen() {
  const navigate = useAppStateStore((s) => s.navigate);
  const selectedVideoPath = useAppStateStore((s) => s.selectedVideoPath);
  const detectionParams = useAppStateStore((s) => s.detectionParams);
  const loadMetadata = useMetadataStore((s) => s.load);
  const loadSample = useMetadataStore((s) => s.loadSample);

  const [phase, dispatch] = useReducer(
    detectingReducer,
    'running' as DetectingPhase,
  );
  const [error, setError] = useState<string | null>(null);
  // #663 — AppError hint rendered as 2nd line under the primary message
  // in `DetectingErrorView`. Kept on the parent (alongside `error`) so the
  // child running view's `onError` callback can stamp both at once.
  const [errorHint, setErrorHint] = useState<string | null>(null);
  // #646 review Round 4 補足 #6 -- run-scoped state (progress / log /
  // probeInfo / phaseLabel / elapsed / startedAt) は `DetectingRunningView`
  // 内部に閉じ込め、retry 時は `key={runCount}` で remount して initial
  // 値に戻す。親が個別 setState を列挙する旧設計だと「将来 state 追加
  // で reset 漏れ」の visible regression を生むため、子 unmount で local
  // state がまとめて捨てられる構造に変えた。
  const [runCount, setRunCount] = useState(0);

  const displayPath = selectedVideoPath
    ? { ...splitPath(selectedVideoPath), full: selectedVideoPath }
    : { fileName: '(video)', parentDir: '', full: '' };

  // completed → navigate to complete (load happened in the running view)
  useEffect(() => {
    if (phase === 'completed') {
      navigate('complete');
    }
  }, [phase, navigate]);

  // #646 -- cancelled は即時 drop へ復帰、error は **手動操作** で復帰。
  // 以前は error も即時 navigate('drop') していたため、Rust 側 Err
  // (例: spawn allaganeye failed / video file not found) がユーザーに
  // 見えず silent で drop 画面に戻る挙動だった。今は error phase で
  // 専用 view を render し、ユーザーが [drop へ戻る] を押すまで画面
  // 遷移しない。
  useEffect(() => {
    if (phase === 'cancelled') {
      navigate('drop');
    }
  }, [phase, navigate]);

  // #813 -- cancel reaps the running detect: invoke kill_tracked_processes
  // (drains PROCESS_TRACKER + drops the Job handle so the Python CLI and its
  // ffmpeg children die, #756) before confirming the cancel. The in-flight
  // start_detect's untrack then returns None and rejects with
  // `subprocess.cancelled`, which the reducer folds into `cancelled`
  // (DETECT_ERROR during cancelling -> cancelled). Kill failure is
  // best-effort: log and still confirm so the UI never hangs.
  useEffect(() => {
    if (phase !== 'cancelling') return;
    let active = true;
    async function confirmCancel(): Promise<void> {
      try {
        await invoke('kill_tracked_processes');
      } catch (e) {
        console.error('detect cancel: kill_tracked_processes failed', e);
      }
      if (active) dispatch({ type: 'CANCEL_CONFIRMED' });
    }
    void confirmCancel();
    return () => {
      active = false;
    };
  }, [phase]);

  // #646 -- error phase は detect 進行 UI を捨てて専用 error view に
  // 切り替える。Rust Err 内容 (start_detect の failure message や
  // CLI が emit した phase=error event の message) を `<pre>` で
  // 改行保持して表示し、ユーザーが [再試行] / [drop へ戻る] を明示
  // 操作するまでは画面遷移しない。
  // Round 4 補足 #6: handleRetry は親 reducer の RETRY action と
  // runCount bump のみ。run-scoped state の reset は `key={runCount}`
  // による子 component remount で達成する。
  function handleRetry(): void {
    setError(null);
    setErrorHint(null);
    dispatch({ type: 'RETRY' });
    setRunCount((c) => c + 1);
  }

  if (phase === 'error') {
    return (
      <DetectingErrorView
        error={error}
        errorHint={errorHint}
        displayPath={displayPath}
        onRetry={handleRetry}
        onBack={() => navigate('drop')}
      />
    );
  }

  return (
    <DetectingRunningView
      key={runCount}
      phase={phase}
      selectedVideoPath={selectedVideoPath}
      displayPath={displayPath}
      detectionParams={detectionParams}
      loadMetadata={loadMetadata}
      loadSample={loadSample}
      navigate={navigate}
      onCancelClick={() => dispatch({ type: 'CANCEL_CLICKED' })}
      onError={(msg, hint) => {
        setError(msg);
        setErrorHint(hint);
        dispatch({ type: 'DETECT_ERROR' });
      }}
      onComplete={() => dispatch({ type: 'PROGRESS_COMPLETE' })}
    />
  );
}

interface DetectingRunningViewProps {
  phase: DetectingPhase;
  selectedVideoPath: string | null;
  displayPath: { fileName: string; parentDir: string; full: string };
  detectionParams: ReturnType<typeof useAppStateStore.getState>['detectionParams'];
  loadMetadata: ReturnType<typeof useMetadataStore.getState>['load'];
  loadSample: ReturnType<typeof useMetadataStore.getState>['loadSample'];
  navigate: ReturnType<typeof useAppStateStore.getState>['navigate'];
  onCancelClick: () => void;
  /**
   * #663 — `hint` is the AppError corrective hint (null when the error came
   * from a `phase=error` progress event or a non-AppError throw).
   */
  onError: (message: string, hint: string | null) => void;
  onComplete: () => void;
}

function DetectingRunningView({
  phase,
  selectedVideoPath,
  displayPath,
  detectionParams,
  loadMetadata,
  loadSample,
  navigate,
  onCancelClick,
  onError,
  onComplete,
}: DetectingRunningViewProps) {
  const [progress, setProgress] = useState(0);
  const [phaseLabel, setPhaseLabel] = useState<string>('start');
  const [log, setLog] = useState<LogEntry[]>([]);
  const [elapsed, setElapsed] = useState(0);
  // #569 review Round 1 課題 1: probing event payload を保持して
  // header meta 行を実 ffprobe 結果で render する。
  const [probeInfo, setProbeInfo] = useState<ProbeInfo | null>(null);
  // Captured once on first mount via lazy initialiser so log entries
  // can compute their relative timestamp inside render. The parent
  // remounts this component (via `key={runCount}`) on retry, so a new
  // run starts with a fresh `startedAt` baseline automatically.
  const [startedAt] = useState<number>(() => Date.now());
  // #639 — pin the live-log scroll viewport so we can pull it back to
  // the bottom whenever a new entry arrives. The DOM ref talks to an
  // external system (scrollTop is browser state, not React state), so
  // setting it inside an effect doesn't fall under the
  // react-hooks/set-state-in-effect rule.
  const logRef = useRef<HTMLDivElement | null>(null);

  // Wall-clock elapsed timer -- ticks once per second so the UI can
  // show "経過 00:42 / 残り ~01:30" without depending on event cadence.
  useEffect(() => {
    if (phase !== 'running') return;
    const id = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => clearInterval(id);
  }, [phase, startedAt]);

  // #639 — auto-scroll the log viewport to the bottom whenever a new
  // entry is appended so the most recent line is always visible. Scope
  // out: pausing auto-scroll while the user is actively scrolling up
  // (deferred per #639 §スコープ外).
  useEffect(() => {
    const el = logRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [log]);

  // #639 review (実機検証 3 回目) — window resize / 親 flex の高さ変動
  // で log pane の viewport だけ縮んだ場合、`[log]` 依存の auto-scroll
  // は再走しないため scrollTop が古い位置のまま残り「見切れ」が再発
  // する。ResizeObserver で log 自身のサイズ変化を監視して都度末尾に
  // 引き戻す。新エントリ追加経路と独立しているので 2 経路で末尾追従
  // が担保される。
  useEffect(() => {
    const el = logRef.current;
    if (!el) return;
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(() => {
      el.scrollTop = el.scrollHeight;
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Subscribe to detect-progress, kick off start_detect.
  // Mount-once effect: the parent remounts this component on retry
  // via `key={runCount}` so a new mount = a new detect run. No dep
  // chasing needed for re-invocation.
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
        // #813 -- per-run fence token, generated inside the try so a missing
        // crypto.randomUUID can never hang detect (generateRunId itself never
        // throws; this placement also keeps any future failure on the
        // catch-reported error path). Echoed by Rust on every detect-progress
        // event so a not-yet-reaped previous run can't bleed into this run's UI.
        const runId = generateRunId();
        unlisten = await listen<DetectProgressEvent>(
          'detect-progress',
          (event) => {
            if (cancelled) return;
            const payload = event.payload;
            // #813 -- drop events tagged with a different run's id. Rust
            // stamps run_id on every emit, so a non-matching id marks a
            // straggler from a previous run. Bare events (no run_id) only
            // occur in unit tests and pass through.
            if (payload.run_id !== undefined && payload.run_id !== runId) {
              return;
            }
            setPhaseLabel(payload.phase);

            // #569 review Round 1 課題 1: probing event の ffprobe 結果を
            // header meta 行用に保持。後続 phase でも維持されるので、
            // detect 中ずっと「1920x1080 · 60.00fps · h264 · 02:00:14」
            // のような実値が表示される。
            if (payload.phase === 'probing') {
              setProbeInfo({
                width: payload.width,
                height: payload.height,
                fps: payload.fps,
                codec: payload.codec,
                duration_s: payload.duration_s,
              });
            }

            const entry = buildLogText(payload);
            if (entry !== null) {
              setLog((prev) => {
                const next = [
                  ...prev,
                  { ts: Date.now(), text: entry.text, kind: entry.kind },
                ];
                return next.length > MAX_LOG_LINES
                  ? next.slice(next.length - MAX_LOG_LINES)
                  : next;
              });
            }

            if (payload.phase === 'error') {
              // #663 — progress events from the CLI carry no AppError hint
              // (`phase=error` only conveys `message`). Pass null so the
              // error view shows just the primary message.
              onError(payload.message ?? 'unknown error', null);
              return;
            }

            const pct = computeOverallPercent(payload);
            // Bar is monotonic -- never reverse on out-of-order events
            // (e.g. cache_hit firing after a probing event).
            setProgress((prev) => (pct > prev ? pct : prev));
          },
        );

        // #813 review (codex HIGH) -- if the component was cancelled/unmounted
        // while listen() was resolving, the cancel's kill already ran
        // (draining zero processes) and the effect cleanup couldn't unlisten
        // (unlisten was still undefined). Bail before spawning a detect the
        // cancel would miss, and tear down the listener we just registered.
        if (cancelled) {
          unlisten();
          return;
        }

        const result = await invoke<DetectResult>('start_detect', {
          videoPath: selectedVideoPath,
          outputDir,
          params: toStartDetectParams(detectionParams),
          runId,
        });
        if (cancelled) return;

        setProgress(100);
        const metaPath = result.metadata_path || metadataPathFor(outputDir);
        await loadMetadata(metaPath);
        // #814 (iterate-review) -- bail if the run was cancelled while
        // loadMetadata was in flight, mirroring the post-start_detect guard,
        // so onError/onComplete don't fire on a cancelled/unmounted run.
        if (cancelled) return;
        // #814 -- loadMetadata (metadataStore.load) swallows failures into
        // loadErrorState and never throws. A detect that finished but whose
        // metadata.json can't be read (zod reject / BOM / corruption) must
        // surface the error, not silently land on the empty complete screen.
        // Route the failure to the existing error view instead of onComplete().
        const loadErr = useMetadataStore.getState().loadErrorState;
        if (loadErr) {
          onError(loadErr.message, loadErr.hint);
          return;
        }
        onComplete();
      } catch (e) {
        if (cancelled) return;
        // #663 — AppError-shaped throws (Tauri command rejection) carry
        // a corrective hint that we render as the error view's 2nd line.
        const errorState = toErrorState(e);
        onError(errorState.message, errorState.hint);
      }
    }

    void run();
    return () => {
      cancelled = true;
      if (unlisten) unlisten();
    };
    // Mount-once: store-bound props are stable across the same mount
    // and a retry remounts the component (via parent's `key={runCount}`).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // #664 -- Refining bar は refine + scorebar を統合表示する。pct2 100%
  // = refine + scorebar 両方完了。refine 完了 (progress=88) で bar ~67%
  // 程度に達し、scorebar 進行で bar 67→100% に進む。PHASE_WINDOWS の
  // 重み (refine 18 : scorebar 9 ≒ 67:33) は維持し全体 %/ETA に regression
  // なし。定数二重管理を避けるため両 bar の終端を PHASE_WINDOWS から導出。
  const scanEnd = PHASE_WINDOWS.scan[1];
  const refineStart = PHASE_WINDOWS.refine[0];
  const refiningEnd = PHASE_WINDOWS.scorebar[1];
  const pct1 = Math.min(100, (progress * 100) / scanEnd);
  const pct2 = Math.max(
    0,
    Math.min(100, ((progress - refineStart) * 100) / (refiningEnd - refineStart)),
  );
  const refiningSub = phaseLabel === 'scorebar' ? '分類' : 'refine';

  const eta = computeEta(progress, elapsed);
  // #569 review Round 1 課題 1: probing event 受信後は実 ffprobe 結果を
  // 表示。受信前 (起動直後の数百 ms) は暫定で `phase: ...` を出して
  // 「meta 行が空」状態を回避する。
  const metaText = probeInfo ? formatProbeMeta(probeInfo) : `phase: ${phaseLabel}`;

  return (
    <div className={styles.screen} data-testid="detecting-screen">
      <div className={styles.header}>
        <AllaganSigil size={84} rotating={phase === 'running'} />
        <div className={styles.headerText}>
          <div className={styles.caption}>観測中</div>
          <div
            className={pathStyles.pathDisplay}
            title={displayPath.full}
            data-testid="detecting-path"
          >
            <div className={styles.fileName}>{displayPath.fileName}</div>
            {displayPath.parentDir && (
              <div className={pathStyles.pathSecondary}>{displayPath.parentDir}</div>
            )}
          </div>
          <div className={styles.meta} data-testid="detecting-meta">
            {metaText}
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
        <PhaseRow name="Refining" jp="精密計測" pct={pct2} sub={refiningSub} />
      </div>

      <div className={styles.divider} />

      <div
        ref={logRef}
        className={styles.log}
        role="log"
        aria-label="detect log"
      >
        {log.length === 0 && (
          <div>
            <span className={styles.logTime}>[--:--]</span> 起動中…
          </div>
        )}
        {log.map((entry, idx) => {
          const tsRel = entry.ts - startedAt;
          const tsLabel = fmtElapsed(Math.max(0, Math.floor(tsRel / 1000)));
          const isLast = idx === log.length - 1;
          // #569 review Round 1 課題 2: phase 別に行を色分けする。kind
          // は `done`/`error`/`warn`/`info` の 4 値で、CSS class に対応。
          // info は無 class (= デフォルト dim 色) を維持して既存の見た目
          // を変えない。
          const kindClass =
            entry.kind === 'done'
              ? styles.logEntryDone
              : entry.kind === 'error'
                ? styles.logEntryError
                : entry.kind === 'warn'
                  ? styles.logEntryWarn
                  : '';
          const lineClass = kindClass ? `${styles.logEntry} ${kindClass}` : styles.logEntry;
          return (
            <div
              key={`${entry.ts}-${idx}`}
              className={lineClass}
              data-kind={entry.kind}
            >
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
        {/* #587 §2.2.7: surface why [中断] is disabled while not actively running. */}
        <DisabledTooltip
          disabled={phase !== 'running'}
          reason="検知実行中のみ中断できます"
        >
          {(p) => (
            <button
              type="button"
              className={styles.cancelButton}
              disabled={phase !== 'running'}
              onClick={onCancelClick}
              {...p}
            >
              中断
            </button>
          )}
        </DisabledTooltip>
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
    <div
      className={styles.phaseRow}
      data-testid={`phase-row-${name.toLowerCase()}`}
    >
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

/**
 * #646 review Round 2 課題 2 / 課題 3 -- error view extracted into
 * its own component so we can attach focus management + an Escape
 * keyboard handler local to the error state without leaking listeners
 * into the running view.
 *
 * - Auto-focus the [drop へ戻る] button on mount so screen readers
 *   announce the error context and keyboard users land on a non-
 *   destructive action by default
 * - Escape returns to drop (the canonical "get me out" key on this
 *   terminal screen)
 * - Retry button restarts the detect run via the parent's `onRetry`,
 *   which clears local state and bumps the run effect's dep counter
 */
interface DetectingErrorViewProps {
  error: string | null;
  /**
   * #663 — corrective hint rendered as a 2nd line below the primary
   * error message. Sourced from AppError throw sites; null for legacy
   * progress-event errors and bare `Error` instances.
   */
  errorHint: string | null;
  displayPath: { fileName: string; parentDir: string; full: string };
  onRetry: () => void;
  onBack: () => void;
}

function DetectingErrorView({
  error,
  errorHint,
  displayPath,
  onRetry,
  onBack,
}: DetectingErrorViewProps) {
  const backButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    backButtonRef.current?.focus();
  }, []);

  useEffect(() => {
    function handler(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        onBack();
      }
    }
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onBack]);

  return (
    <div
      className={styles.errorScreen}
      data-testid="detecting-error"
      role="alert"
    >
      <div className={styles.errorHeading}>検知に失敗しました</div>
      <div
        className={pathStyles.pathDisplay}
        title={displayPath.full}
        data-testid="detecting-error-path"
      >
        <div className={styles.errorFile}>{displayPath.fileName}</div>
        {displayPath.parentDir && (
          <div className={pathStyles.pathSecondary}>{displayPath.parentDir}</div>
        )}
      </div>
      <pre className={styles.errorMessage} data-testid="detecting-error-message">
        {error ?? 'unknown error'}
      </pre>
      {errorHint && (
        <div data-testid="detecting-error-hint">
          <InlineErrorHint hint={errorHint} />
        </div>
      )}
      <div className={styles.actions}>
        <button
          type="button"
          className={styles.retryButton}
          onClick={onRetry}
          data-testid="detecting-error-retry"
        >
          ↻ 再試行
        </button>
        <button
          ref={backButtonRef}
          type="button"
          className={styles.cancelButton}
          onClick={onBack}
          data-testid="detecting-error-back"
        >
          ← drop へ戻る
        </button>
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
