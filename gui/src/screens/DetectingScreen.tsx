import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';
import { useEffect, useReducer, useRef, useState } from 'react';

import { AllaganSigil } from '../components/AllaganSigil';
import { DisabledTooltip } from '../components/DisabledTooltip';
import { useAppStateStore } from '../state/appStateStore';
import { useMetadataStore } from '../state/metadataStore';
import { toStartDetectParams } from '../utils/detection';
import {
  deriveDetectOutputDir,
  metadataPathFor,
} from '../utils/detectOutputDir';
import { fmtTime } from '../utils/time';
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
  const detectionParams = useAppStateStore((s) => s.detectionParams);
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
  // #569 review Round 1 課題 1: probing event payload を保持して
  // header meta 行を実 ffprobe 結果で render する。
  const [probeInfo, setProbeInfo] = useState<ProbeInfo | null>(null);
  // can compute their relative timestamp inside render. Updated only
  // from the [再試行] handler so a retried detect resets its elapsed
  // timer baseline to "now". The lazy initialiser sidesteps the
  // react-hooks/set-state-in-effect rule for the initial assignment.
  const [startedAt, setStartedAt] = useState<number>(() => Date.now());
  // #646 review Round 2 課題 2 -- bumping `runCount` is the dep change
  // that re-fires the start_detect / listen effect for [再試行].
  const [runCount, setRunCount] = useState(0);
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
          params: toStartDetectParams(detectionParams),
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
    // store-bound and stable; we re-run only when `runCount` bumps from
    // the [再試行] handler (#646 review Round 2 課題 2). Initial mount
    // also goes through this effect (runCount = 0).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runCount]);

  // completed → navigate to complete (load happened above)
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
  // #569 review Round 1 課題 1: probing event 受信後は実 ffprobe 結果を
  // 表示。受信前 (起動直後の数百 ms) は暫定で `phase: ...` を出して
  // 「meta 行が空」状態を回避する。
  const metaText = probeInfo ? formatProbeMeta(probeInfo) : `phase: ${phaseLabel}`;

  // #646 -- error phase は detect 進行 UI を捨てて専用 error view に
  // 切り替える。Rust Err 内容 (start_detect の failure message や
  // CLI が emit した phase=error event の message) を `<pre>` で
  // 改行保持して表示し、ユーザーが [再試行] / [drop へ戻る] を明示
  // 操作するまでは画面遷移しない。
  // Round 2 課題 2 / 課題 3: retry / auto-focus / Esc handler を
  // 切り出した DetectingErrorView 内で実装する。
  function handleRetry(): void {
    setError(null);
    setProgress(0);
    setLog([]);
    setProbeInfo(null);
    setPhaseLabel('start');
    setElapsed(0);
    setStartedAt(Date.now());
    dispatch({ type: 'RETRY' });
    setRunCount((c) => c + 1);
  }

  if (phase === 'error') {
    return (
      <DetectingErrorView
        error={error}
        displayFile={displayFile}
        onRetry={handleRetry}
        onBack={() => navigate('drop')}
      />
    );
  }

  return (
    <div className={styles.screen} data-testid="detecting-screen">
      <div className={styles.header}>
        <AllaganSigil size={84} rotating={phase === 'running'} />
        <div className={styles.headerText}>
          <div className={styles.caption}>観測中</div>
          <div className={styles.fileName}>{displayFile}</div>
          <div className={styles.meta} data-testid="detecting-meta">
            {metaText}
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
              onClick={() => dispatch({ type: 'CANCEL_CLICKED' })}
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
  displayFile: string;
  onRetry: () => void;
  onBack: () => void;
}

function DetectingErrorView({
  error,
  displayFile,
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
        e.preventDefault();
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
      <div className={styles.errorFile}>{displayFile}</div>
      <pre className={styles.errorMessage} data-testid="detecting-error-message">
        {error ?? 'unknown error'}
      </pre>
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
