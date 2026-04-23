import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';
import { open as openDialog } from '@tauri-apps/plugin-dialog';
import { useEffect, useReducer, useRef, useState } from 'react';

import { useAppStateStore } from '../state/appStateStore';
import { useMetadataStore } from '../state/metadataStore';
import { exportReducer } from './reducers/export';
import type { ExportPhase } from './types';
import styles from './ExportScreen.module.css';

type Codec = 'copy' | 'h264';

const CODECS: { v: Codec; l: string; sub: string }[] = [
  { v: 'copy', l: '無損失 copy', sub: '高速 / 前 I フレーム吸着' },
  { v: 'h264', l: 'H.264 再エンコード', sub: '遅い / 正確な秒指定' },
];

type MatchStatus = 'pending' | 'running' | 'done' | 'error' | 'skipped';

interface MatchState {
  status: MatchStatus;
  percent: number;
  error?: string;
  outputPath?: string;
}

interface ExportProgressPayload {
  match_index: number;
  percent: number;
  stage: 'encoding' | 'done' | 'error';
  message?: string;
}

interface ExportResult {
  match_index: number;
  output_path: string;
  duration_ms: number;
}

/**
 * #466 Phase 4 export screen. Real ffmpeg invocation driven by the Rust
 * `export_match` command; per-match progress arrives via the
 * `export-progress` Tauri event.
 */
export function ExportScreen() {
  const metadata = useMetadataStore((s) => s.metadata);
  const filePath = useMetadataStore((s) => s.filePath);
  const navigate = useAppStateStore((s) => s.navigate);

  const [phase, dispatch] = useReducer(exportReducer, 'idle' as ExportPhase);
  const [outDir, setOutDir] = useState('./output');
  const [codec, setCodec] = useState<Codec>('copy');
  const [namePattern, setNamePattern] = useState('match_{idx:03}.mp4');
  const [matchStates, setMatchStates] = useState<Record<number, MatchState>>({});
  const cancelRequestedRef = useRef(false);

  // #466 -- listen for per-match progress updates emitted by Rust.
  useEffect(() => {
    let unlisten: UnlistenFn | null = null;
    (async () => {
      unlisten = await listen<ExportProgressPayload>('export-progress', (event) => {
        const p = event.payload;
        setMatchStates((prev) => {
          const prior = prev[p.match_index] ?? {
            status: 'pending' as MatchStatus,
            percent: 0,
          };
          let status: MatchStatus = prior.status;
          if (p.stage === 'encoding') status = 'running';
          else if (p.stage === 'done') status = 'done';
          else if (p.stage === 'error') status = 'error';
          return {
            ...prev,
            [p.match_index]: {
              ...prior,
              status,
              percent: p.percent,
              error: p.stage === 'error' ? p.message : prior.error,
            },
          };
        });
      });
    })();
    return () => {
      unlisten?.();
    };
  }, []);

  function formatName(index: number, type: string, startSec: number): string {
    const startDisplay = Math.floor(startSec)
      .toString()
      .padStart(4, '0');
    const today = new Date().toISOString().slice(0, 10);
    return namePattern
      .replace(/\{idx:03\}/g, String(index).padStart(3, '0'))
      .replace(/\{idx\}/g, String(index))
      .replace(/\{type\}/g, type)
      .replace(/\{start\}/g, startDisplay)
      .replace(/\{date\}/g, today);
  }

  async function handlePickDir() {
    const picked = await openDialog({ directory: true, multiple: false });
    if (typeof picked === 'string') {
      setOutDir(picked);
    }
  }

  async function handleStartExport() {
    if (!metadata || !filePath) return;
    cancelRequestedRef.current = false;

    // Resolve source video path from metadata.source. Fall back to whatever
    // is there; Rust side validates existence.
    const videoSource = metadata.source;

    // Initialize per-match state (skip entries explicitly marked as skip).
    const nextStates: Record<number, MatchState> = {};
    const queue: typeof metadata.matches = [];
    for (const m of metadata.matches) {
      if (m.type_override === 'skip') {
        nextStates[m.index] = { status: 'skipped', percent: 0 };
      } else {
        nextStates[m.index] = { status: 'pending', percent: 0 };
        queue.push(m);
      }
    }
    setMatchStates(nextStates);
    dispatch({ type: 'START_CLICKED' });

    let successCount = 0;
    let failureCount = 0;
    for (const m of queue) {
      if (cancelRequestedRef.current) break;
      const name = formatName(m.index, m.type, m.edited?.start_time ?? m.start_time);
      const outputPath = joinPath(outDir, name);
      try {
        const result = await invoke<ExportResult>('export_match', {
          videoPath: videoSource,
          startSeconds: m.edited?.start_time ?? m.start_time,
          endSeconds: m.edited?.end_time ?? m.end_time,
          outputPath,
          codec,
          matchIndex: m.index,
        });
        successCount += 1;
        setMatchStates((prev) => ({
          ...prev,
          [m.index]: {
            status: 'done',
            percent: 100,
            outputPath: result.output_path,
          },
        }));
      } catch (e) {
        failureCount += 1;
        const msg = e instanceof Error ? e.message : String(e);
        setMatchStates((prev) => ({
          ...prev,
          [m.index]: { status: 'error', percent: 0, error: msg },
        }));
      }
    }

    if (cancelRequestedRef.current) {
      dispatch({ type: 'CANCEL_CONFIRMED' });
    } else if (successCount === 0 && failureCount > 0) {
      // Zero matches finished -- surface the error phase. If at least one
      // match succeeded we declare the run "completed" and keep per-match
      // errors inline for the user to review.
      dispatch({ type: 'EXPORT_ERROR' });
    } else {
      dispatch({ type: 'PROGRESS_COMPLETE' });
    }
  }

  function handleCancelClicked() {
    cancelRequestedRef.current = true;
    dispatch({ type: 'CANCEL_CLICKED' });
    // #523: kill any tracked ffmpeg child so the current export can't run
    // to completion after the user asked to stop.
    void invoke('kill_tracked_processes').catch(() => undefined);
  }

  async function handleOpenFolder() {
    try {
      await invoke('plugin:shell|open', { path: outDir });
    } catch {
      // non-tauri test env: swallow
    }
    navigate('complete');
  }

  if (!metadata) {
    return (
      <div className={styles.screen} data-testid="export-screen">
        <div className={styles.emptyNote}>No metadata loaded.</div>
      </div>
    );
  }

  const running = phase === 'running';
  const completed = phase === 'completed';
  const error = phase === 'error';
  const cancelling = phase === 'cancelling';

  const countedMatches = metadata.matches.filter(
    (m) => m.type_override !== 'skip',
  );
  const doneCount = countedMatches.filter(
    (m) => matchStates[m.index]?.status === 'done',
  ).length;
  const errorCount = countedMatches.filter(
    (m) => matchStates[m.index]?.status === 'error',
  ).length;
  const overallPercent = countedMatches.length === 0
    ? 0
    : Math.round((doneCount / countedMatches.length) * 100);

  return (
    <div className={styles.screen} data-testid="export-screen" data-phase={phase}>
      <div className={styles.header}>
        <button
          type="button"
          className={styles.backButton}
          disabled={running || cancelling}
          onClick={() => navigate('preview')}
        >
          ◀ プレビュー
        </button>
        <div>
          <div className={styles.caption}>エクスポート</div>
          <div className={styles.title}>
            {countedMatches.length} 試合を書き出す
          </div>
        </div>
      </div>

      <div className={styles.grid}>
        <div className={styles.panel}>
          <div className={styles.panelCaption}>設定</div>

          <div>
            <div className={styles.fieldLabel}>出力先</div>
            <div className={styles.outDirRow}>
              <input
                className={styles.outDirInput}
                value={outDir}
                onChange={(e) => setOutDir(e.target.value)}
                aria-label="output directory"
                disabled={running || cancelling}
              />
              <button
                type="button"
                className={styles.pickButton}
                onClick={handlePickDir}
                disabled={running || cancelling}
              >
                参照…
              </button>
            </div>
          </div>

          <div>
            <div className={styles.fieldLabel}>命名規則</div>
            <input
              className={styles.nameInput}
              value={namePattern}
              onChange={(e) => setNamePattern(e.target.value)}
              aria-label="name pattern"
              disabled={running || cancelling}
            />
            <div className={styles.nameHint}>
              変数: {'{idx}'} {'{idx:03}'} {'{start}'} {'{type}'} {'{date}'}
            </div>
          </div>

          <div>
            <div className={styles.fieldLabel}>コーデック</div>
            <div className={styles.codecRow}>
              {CODECS.map((c) => (
                <button
                  key={c.v}
                  type="button"
                  aria-pressed={codec === c.v}
                  onClick={() => setCodec(c.v)}
                  disabled={running || cancelling}
                  className={`${styles.codecButton}${codec === c.v ? ` ${styles.codecButtonActive}` : ''}`}
                >
                  <div className={styles.codecLabel}>{c.l}</div>
                  <div className={styles.codecSub}>{c.sub}</div>
                </button>
              ))}
            </div>
          </div>

          <div className={styles.bottomActions}>
            {error && (
              <div className={styles.errorMessage} role="alert">
                すべての試合の書き出しが失敗しました
              </div>
            )}
            {(running || completed || cancelling) && (
              <div className={styles.progressBox}>
                <div className={styles.progressHeader}>
                  <span className={styles.progressLabel}>
                    {running
                      ? '分割・書き出し中'
                      : cancelling
                        ? '中断中…'
                        : '完了'}
                  </span>
                  <span>
                    {doneCount} / {countedMatches.length} files
                    {errorCount > 0 && (
                      <span
                        style={{ marginLeft: 8, color: 'var(--ae-danger)' }}
                      >
                        ({errorCount} 失敗)
                      </span>
                    )}
                    <span style={{ marginLeft: 12 }}>{overallPercent}%</span>
                  </span>
                </div>
                <div className={styles.progressBar}>
                  <div
                    className={`${styles.progressFill}${completed ? ` ${styles.progressFillDone}` : ''}`}
                    style={{ width: `${overallPercent}%` }}
                  />
                </div>
              </div>
            )}

            {!completed && !error && (
              <button
                type="button"
                className={styles.primaryButton}
                onClick={() => {
                  void handleStartExport();
                }}
                disabled={running || cancelling || !filePath}
              >
                {running
                  ? '書き出し中…'
                  : cancelling
                    ? '中断中…'
                    : '⬦ 書き出し開始'}
              </button>
            )}

            {running && (
              <button
                type="button"
                className={styles.cancelButton}
                onClick={handleCancelClicked}
              >
                中断
              </button>
            )}

            {completed && (
              <button
                type="button"
                className={styles.primaryButton}
                onClick={() => {
                  void handleOpenFolder();
                }}
              >
                ✓ 完了 — フォルダを開く
              </button>
            )}
            {completed && (
              <button
                type="button"
                className={styles.cancelButton}
                onClick={() => {
                  setMatchStates({});
                  dispatch({ type: 'RESTART' });
                }}
              >
                もう一度書き出す
              </button>
            )}

            {error && (
              <button
                type="button"
                className={styles.cancelButton}
                onClick={() => dispatch({ type: 'DISMISS_ERROR' })}
              >
                閉じる
              </button>
            )}
          </div>
        </div>

        <div className={styles.listPanel}>
          <div className={styles.listCaption}>
            書き出し一覧 ⸱ {countedMatches.length} ファイル
          </div>
          <ul className={styles.listBody}>
            {metadata.matches.map((m) => {
              const s = matchStates[m.index] ?? {
                status: 'pending' as MatchStatus,
                percent: 0,
              };
              const name = formatName(
                m.index,
                m.type,
                m.edited?.start_time ?? m.start_time,
              );
              const mark =
                s.status === 'done'
                  ? '✓'
                  : s.status === 'running'
                    ? '●'
                    : s.status === 'error'
                      ? '!'
                      : s.status === 'skipped'
                        ? '—'
                        : '○';
              const markClass =
                s.status === 'done'
                  ? styles.listMarkDone
                  : s.status === 'error'
                    ? styles.listMarkError
                    : '';
              return (
                <li key={m.index} className={styles.listItem}>
                  <span className={`${styles.listMark} ${markClass}`}>
                    {mark}
                  </span>
                  <span className={styles.listName}>{name}</span>
                  <span className={styles.listDur}>{m.duration_display}</span>
                  {(running ||
                    completed ||
                    s.status === 'done' ||
                    s.status === 'error') && (
                    <div className={styles.listProgress}>
                      <div
                        className={`${styles.listProgressFill}${
                          s.status === 'done' ? ` ${styles.listProgressFillDone}` : ''
                        }`}
                        style={{ width: `${s.percent}%` }}
                      />
                    </div>
                  )}
                  {s.status === 'error' && s.error && (
                    <span className={styles.listError} role="alert">
                      {s.error.slice(0, 120)}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </div>
  );
}

function joinPath(dir: string, name: string): string {
  const separator =
    dir.includes('\\') && !dir.includes('/') ? '\\' : '/';
  if (dir.endsWith('/') || dir.endsWith('\\')) return dir + name;
  return dir + separator + name;
}
