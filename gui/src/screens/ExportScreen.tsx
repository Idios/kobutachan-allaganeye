import { invoke } from '@tauri-apps/api/core';
import { useEffect, useReducer, useState } from 'react';

import { useAppStateStore } from '../state/appStateStore';
import { useMetadataStore } from '../state/metadataStore';
import { fmtTime } from '../utils/time';
import { exportReducer } from './reducers/export';
import type { ExportPhase } from './types';
import styles from './ExportScreen.module.css';

const TICK_MS = 80;
const TICKS_TO_COMPLETE = 100;

type Codec = 'copy' | 'h264';

const CODECS: { v: Codec; l: string; sub: string }[] = [
  { v: 'copy', l: '無損失 copy', sub: '高速 / 前 I フレーム吸着' },
  { v: 'h264', l: 'H.264 再エンコード', sub: '遅い / 正確な秒指定' },
];

/**
 * Phase 2 export screen. UI skeleton + dummy progress interval.
 * Phase 4 (#466) replaces the dummy interval with real ffmpeg invocation via
 * a tauri command, keeping the reducer events the same.
 *
 * Shell.open (used by [✓ フォルダを開く]) is invoked through the tauri-plugin-shell
 * permission already declared in capabilities/default.json.
 */
export function ExportScreen() {
  const metadata = useMetadataStore((s) => s.metadata);
  const navigate = useAppStateStore((s) => s.navigate);

  const [phase, dispatch] = useReducer(exportReducer, 'idle' as ExportPhase);
  const [outDir, setOutDir] = useState('./output');
  const [codec, setCodec] = useState<Codec>('copy');
  const [namePattern, setNamePattern] = useState('match_{idx:03}.mp4');
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

  // cancelling auto-confirms (no real ffmpeg in Phase 2); Phase 4 #523 will
  // replace this with an async process.kill() before dispatching CANCEL_CONFIRMED.
  function handleCancelClicked() {
    dispatch({ type: 'CANCEL_CLICKED' });
    setProgress(0);
    dispatch({ type: 'CANCEL_CONFIRMED' });
  }

  async function handleOpenFolder() {
    try {
      await invoke('plugin:shell|open', { path: outDir });
    } catch {
      // fallback — in tests / non-tauri env the invoke call will be mocked
    }
    navigate('complete');
  }

  function formatName(index: number, type: string): string {
    return namePattern
      .replace('{idx:03}', String(index).padStart(3, '0'))
      .replace('{idx}', String(index))
      .replace('{type}', type)
      .replace('{start}', String(index))
      .replace('{date}', '2026-04-08');
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

  return (
    <div className={styles.screen} data-testid="export-screen" data-phase={phase}>
      <div className={styles.header}>
        <button
          type="button"
          className={styles.backButton}
          disabled={running || phase === 'cancelling'}
          onClick={() => navigate('preview')}
        >
          ◀ プレビュー
        </button>
        <div>
          <div className={styles.caption}>エクスポート</div>
          <div className={styles.title}>
            {metadata.matches.length} 試合を書き出す
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
              />
              <button type="button" className={styles.pickButton}>
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
                書き出しに失敗しました (Phase 2 dummy)
              </div>
            )}

            {(running || completed) && (
              <div className={styles.progressBox}>
                <div className={styles.progressHeader}>
                  <span className={styles.progressLabel}>
                    {running ? '分割・書き出し中' : '完了'}
                  </span>
                  <span>
                    {Math.min(
                      metadata.matches.length,
                      Math.floor(
                        (progress / 100) * metadata.matches.length,
                      ) + (running ? 1 : 0),
                    )}{' '}
                    / {metadata.matches.length} files
                    <span style={{ marginLeft: 12 }}>
                      {Math.round(progress)}%
                    </span>
                  </span>
                </div>
                <div className={styles.progressBar}>
                  <div
                    className={`${styles.progressFill}${completed ? ` ${styles.progressFillDone}` : ''}`}
                    style={{ width: `${progress}%` }}
                  />
                </div>
                <div className={styles.progressHeader}>
                  <span>経過 {fmtTime(progress * 1.2)}</span>
                  <span>残り {running ? fmtTime((100 - progress) * 1.2) : '—'}</span>
                </div>
              </div>
            )}

            {!completed && !error && (
              <button
                type="button"
                className={styles.primaryButton}
                onClick={() => {
                  setProgress(0);
                  dispatch({ type: 'START_CLICKED' });
                }}
                disabled={running || phase === 'cancelling'}
              >
                {running
                  ? '書き出し中…'
                  : phase === 'cancelling'
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
                onClick={handleOpenFolder}
              >
                ✓ 完了 — フォルダを開く
              </button>
            )}

            {completed && (
              <button
                type="button"
                className={styles.cancelButton}
                onClick={() => dispatch({ type: 'RESTART' })}
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
            書き出し一覧 ⸱ {metadata.matches.length} ファイル
          </div>
          <ul className={styles.listBody}>
            {metadata.matches.map((m) => {
              const pct = running
                ? Math.max(
                    0,
                    Math.min(100, progress - (m.index - 1) * (100 / metadata.matches.length)),
                  )
                : completed
                  ? 100
                  : 0;
              const done = (running || completed) && pct >= 100;
              return (
                <li key={m.index} className={styles.listItem}>
                  <span
                    className={`${styles.listMark}${done ? ` ${styles.listMarkDone}` : ''}`}
                  >
                    {done ? '✓' : pct > 0 ? '●' : '○'}
                  </span>
                  <span className={styles.listName}>
                    {formatName(m.index, m.type)}
                  </span>
                  <span className={styles.listDur}>{m.duration_display}</span>
                  {(running || completed) && (
                    <div className={styles.listProgress}>
                      <div
                        className={`${styles.listProgressFill}${done ? ` ${styles.listProgressFillDone}` : ''}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
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
