import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';
import { open as openDialog } from '@tauri-apps/plugin-dialog';
import { useEffect, useReducer, useRef, useState } from 'react';

import { useAppStateStore } from '../state/appStateStore';
import { useMetadataStore } from '../state/metadataStore';
import { stripExtendedPathPrefix } from '../utils/path';
import { fmtMatchDuration, fmtTime } from '../utils/time';
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
 *
 * ## review 反映 (2026-04-25)
 *
 * - **#1**: per-match の include/exclude チェックボックス (ad-hoc)。
 *   `excludedIndexes` ローカル state が制御。`type_override === 'skip'`
 *   (preview で永続設定) は強制 disable で別軸。
 * - **#2**: 出力先 default は `<dirname(videoSource)>/output`
 *   ({@link deriveDefaultOutDir})。videoSource は
 *   `selectedVideoPath ?? metadata.source`。
 * - **#3**: 参照ボタンは `@tauri-apps/plugin-dialog` の `open({directory})`
 *   経由 (`dialog:allow-open` permission を `capabilities/default.json` に
 *   明示)。
 * - **#4**: 出力先親ディレクトリが存在しない場合は Rust 側で error。以前の
 *   `create_dir_all` (silent mkdir) は廃止 (タイポ事故防止)。
 * - **#5**: 「フォルダを開く」は `shell.open` のみで完了画面に navigate
 *   しない。失敗時は `openFolderError` で UI に表示。
 * - **#6 (再書き出し)**: 「設定変更して再書き出し」は同じ metadata を別設定
 *   (出力先 / 命名 / コーデック / 試合選択) で再実行する用途。既存ファイル
 *   は ffmpeg `-y` で silent overwrite される。
 * - **#7 (boundary)**: `m.edited?.start_time ?? m.start_time` を
 *   `export_match` の `startSeconds` に渡す (`end_time` も同様)。preview で
 *   調整した境界が export に反映される。
 *
 * ## 2026-04-25 追加修正 (#545 実機テスト)
 *
 * - **filePath 早期 return 廃止**: 旧実装は `if (!metadata || !filePath)
 *   return` だったが、Phase 3 dummy detect が `loadSample()` のみで
 *   `filePath = null` のまま preview/export に来るため、書き出し開始ボタンが
 *   常に disable + クリックしても無反応になっていた。`export_match` invoke
 *   は `filePath` (metadata.json の path) を必要とせず `videoSource` (実
 *   video の path) だけで動くため、ガードを `!videoSource` に変更。
 * - **list duration の edited 反映**: 旧実装は `m.duration_display` を
 *   そのまま表示していたため、preview で `m.edited.end_time` を変えても
 *   一覧の duration が CLI 初期値のまま固定だった。`m.edited` がある場合は
 *   `effectiveEnd - effectiveStart` を {@link fmtMatchDuration} で再 format
 *   して表示する (CLI `_format_duration` と同一フォーマット)。
 */
export function ExportScreen() {
  const metadata = useMetadataStore((s) => s.metadata);
  const navigate = useAppStateStore((s) => s.navigate);

  // #466 review (C): drop で確定した実 path を最優先で使用する。sample mode
  // (selectedVideoPath = null) では metadata.source にフォールバック。
  const selectedVideoPath = useAppStateStore((s) => s.selectedVideoPath);
  const videoSource = selectedVideoPath ?? metadata?.source ?? null;

  const [phase, dispatch] = useReducer(exportReducer, 'idle' as ExportPhase);
  // #466 review #2: default 出力先は source video の親ディレクトリ +
  // `/output`。ファイルピックなしで動かしても物が散らばらない場所に出る。
  // videoSource が無い場合 (sample mode で何も load してない等) は空文字列
  // にしておき、ユーザーに必須選択させる。
  const [outDir, setOutDir] = useState<string>(() => deriveDefaultOutDir(videoSource));
  const [codec, setCodec] = useState<Codec>('copy');
  const [namePattern, setNamePattern] = useState('match_{idx:03}.mp4');
  const [matchStates, setMatchStates] = useState<Record<number, MatchState>>({});
  // #466 review #1: per-match の選択 (default: 全選択 = 全試合書き出し)。
  // ユーザーは個別行のチェックボックスで除外でき、「1 試合だけ書き出す」
  // ような ad-hoc な選択も可能。type_override === 'skip' (preview で永続
  // 設定済み) は強制 exclude (UI でも切替不可)。本 set は ad-hoc な exclude
  // のみ追跡。
  const [excludedIndexes, setExcludedIndexes] = useState<ReadonlySet<number>>(
    () => new Set(),
  );
  const cancelRequestedRef = useRef(false);
  // #545 review #7 (2026-04-25): progress bar 下の「経過 / 残り」時間表示用。
  // START_CLICKED 時の wall-clock を記録し、`elapsedSec` / `remainingSec` を
  // 描画ループで更新する。残り時間は `(elapsed / done) * remaining` の線形
  // 推定 (done=0 のときは null = 「-」表示)。
  const [exportStartMs, setExportStartMs] = useState<number | null>(null);
  const [nowMs, setNowMs] = useState<number>(() => Date.now());

  // 1 秒間隔の wall-clock tick (running 中のみ)。完了 / 中断 / idle に
  // なれば clearInterval。
  useEffect(() => {
    if (exportStartMs === null) return;
    if (phase !== 'running') return;
    const iv = setInterval(() => {
      setNowMs(Date.now());
    }, 1000);
    return () => clearInterval(iv);
  }, [exportStartMs, phase]);

  function toggleMatchExclusion(matchIndex: number) {
    setExcludedIndexes((prev) => {
      const next = new Set(prev);
      if (next.has(matchIndex)) {
        next.delete(matchIndex);
      } else {
        next.add(matchIndex);
      }
      return next;
    });
  }

  /**
   * #545 review #3 (2026-04-25): 一覧の全選択 / 全解除トグル。
   * `type_override === 'skip'` (preview で永続 skip 設定済) は対象外
   * (UI でも個別 checkbox が disabled なので、bulk からも除外する)。
   *
   * - select-all: excludedIndexes から bulk 対象 index を全 remove
   * - deselect-all: bulk 対象 index を全 add
   */
  function toggleSelectAll(selectAll: boolean) {
    if (!metadata) return;
    setExcludedIndexes((prev) => {
      const next = new Set(prev);
      for (const m of metadata.matches) {
        if (m.type_override === 'skip') continue;
        if (selectAll) {
          next.delete(m.index);
        } else {
          next.add(m.index);
        }
      }
      return next;
    });
  }

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
    // #545 review #8 (2026-04-25): {start} は MM-SS / H-MM-SS 形式
    // (design mock の `m.start_display.replace(/:/g, '-')` 準拠)。
    // 旧実装は秒数 0 埋め (例: '0915') だったが、ユーザー視点で start_display
    // (mm:ss) との対応が取れず混乱の元。Windows filename で `:` は使えない
    // ので `-` 置換版を採用。
    const startDisplay = formatStartForFilename(startSec);
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
    // 2026-04-25 修正: filePath は metadata.json の path であり、
    // export_match invoke 自体は videoSource (実 video path) だけで動く。
    // dummy detect で loadSample() のみ走った場合 filePath は null のため、
    // 旧 `!filePath` early return + button disabled 条件は誤検知になる。
    if (!metadata) return;
    if (!videoSource) return;
    cancelRequestedRef.current = false;

    // Initialize per-match state. Skip = `type_override === 'skip'` (永続)
    // または excludedIndexes に含まれる (ad-hoc UI 選択、#466 review #1)。
    const nextStates: Record<number, MatchState> = {};
    const queue: typeof metadata.matches = [];
    for (const m of metadata.matches) {
      if (m.type_override === 'skip' || excludedIndexes.has(m.index)) {
        nextStates[m.index] = { status: 'skipped', percent: 0 };
      } else {
        nextStates[m.index] = { status: 'pending', percent: 0 };
        queue.push(m);
      }
    }
    setMatchStates(nextStates);
    // #545 review #7: 経過 / 残り時間計測の起点。
    const startMs = Date.now();
    setExportStartMs(startMs);
    setNowMs(startMs);
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

  // #466 review #5: 旧実装は shell.open 後に navigate('complete') を必ず
  // 呼んでおり、Explorer が開く前に画面遷移してしまう (実態として開いて
  // いないように見える) 不具合があった。新実装は shell.open のみで
  // 画面遷移は行わない。`完了` ステータスは画面に残す。
  //
  // #545 review #6 (2026-04-25): shell.open は default scope が URL
  // (`mailto:` / `tel:` / `https?://`) しか許可せず、ローカル path で
  // `Scoped command argument failed regex validation` を返していた。
  // Rust 側に `open_folder_in_explorer` 独自 command を追加して explorer.exe
  // を直接 spawn する形に変更。
  const [openFolderError, setOpenFolderError] = useState<string | null>(null);

  async function handleOpenFolder() {
    setOpenFolderError(null);
    try {
      await invoke('open_folder_in_explorer', { path: outDir });
    } catch (e) {
      setOpenFolderError(e instanceof Error ? e.message : String(e));
    }
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

  // #466 review #1: counted = 永続 skip 除外 + ad-hoc exclude 除外
  const countedMatches = metadata.matches.filter(
    (m) => m.type_override !== 'skip' && !excludedIndexes.has(m.index),
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

  // #545 review #7: 経過 / 残り時間 (秒)。
  // - 経過: `nowMs - exportStartMs` (running 中は 1s tick で更新)
  // - 残り: `(elapsed / done) * remaining` の線形推定。done=0 のとき null
  //   (= 表示は `—`)。完了 / 中断時も null。
  const elapsedSec =
    exportStartMs === null ? null : Math.max(0, (nowMs - exportStartMs) / 1000);
  const remainingCount = Math.max(0, countedMatches.length - doneCount);
  const remainingSec =
    !running || elapsedSec === null || doneCount === 0
      ? null
      : (elapsedSec / doneCount) * remainingCount;

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
                {/* #545 review #7: 経過 / 残り時間 (design mock 準拠)。
                    完了時は残りは `—` で固定、cancelling は経過のみ表示。 */}
                {elapsedSec !== null && (
                  <div className={styles.progressTime}>
                    <span>経過 {fmtTime(elapsedSec)}</span>
                    <span>
                      残り{' '}
                      {remainingSec !== null ? fmtTime(remainingSec) : '—'}
                    </span>
                  </div>
                )}
              </div>
            )}

            {!completed && !error && (
              <button
                type="button"
                className={styles.primaryButton}
                onClick={() => {
                  void handleStartExport();
                }}
                disabled={running || cancelling || !videoSource}
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
            {completed && openFolderError && (
              <div className={styles.errorMessage} role="alert">
                フォルダを開けませんでした: {openFolderError}
              </div>
            )}
            {completed && (
              <button
                type="button"
                className={styles.cancelButton}
                title={
                  '同じ metadata を別設定 (出力先 / 命名 / コーデック / 試合選択) で再書き出しします。' +
                  '既に出力先に同名ファイルがある場合は ffmpeg `-y` で上書きされます。'
                }
                onClick={() => {
                  setMatchStates({});
                  setOpenFolderError(null);
                  dispatch({ type: 'RESTART' });
                }}
              >
                設定変更して再書き出し
              </button>
            )}

            {error && (
              <button
                type="button"
                className={styles.primaryButton}
                title={
                  '出力先 / 命名 / コーデック / 試合選択 を変更してから ' +
                  '再度書き出しを試行します。'
                }
                onClick={() => {
                  setMatchStates({});
                  setOpenFolderError(null);
                  dispatch({ type: 'DISMISS_ERROR' });
                }}
              >
                設定変更して再試行
              </button>
            )}
          </div>
        </div>

        <div className={styles.listPanel}>
          <div className={styles.listHeaderRow}>
            <div className={styles.listCaption}>
              書き出し一覧 ⸱ {countedMatches.length} ファイル
            </div>
            {/* #545 review #3 (2026-04-25): 全選択 / 全解除トグル。
                preview で永続 skip 設定済 (type_override === 'skip') の試合は
                bulk 対象から除外。export 中は disable。 */}
            <div className={styles.listBulkActions}>
              <button
                type="button"
                className={styles.listBulkButton}
                disabled={running || cancelling}
                onClick={() => toggleSelectAll(true)}
                aria-label="select all matches"
              >
                全選択
              </button>
              <button
                type="button"
                className={styles.listBulkButton}
                disabled={running || cancelling}
                onClick={() => toggleSelectAll(false)}
                aria-label="deselect all matches"
              >
                全解除
              </button>
            </div>
          </div>
          <ul className={styles.listBody}>
            {metadata.matches.map((m) => {
              const s = matchStates[m.index] ?? {
                status: 'pending' as MatchStatus,
                percent: 0,
              };
              // 2026-04-25 修正: preview で調整した境界 (m.edited) を一覧
              // duration にも反映する。m.duration_display は CLI 初期値で
              // 固定なので、edited がある場合は再計算した duration を表示。
              const effectiveStart = m.edited?.start_time ?? m.start_time;
              const effectiveEnd = m.edited?.end_time ?? m.end_time;
              const durationDisplay = m.edited
                ? fmtMatchDuration(effectiveEnd - effectiveStart)
                : m.duration_display;
              const name = formatName(m.index, m.type, effectiveStart);
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
              // #466 review #1: 永続 skip は変更不可、ad-hoc exclude は
              // checkbox で個別 toggle 可能。export 中は disabled。
              const isPersistSkip = m.type_override === 'skip';
              const isAdHocExcluded = excludedIndexes.has(m.index);
              const isIncluded = !isPersistSkip && !isAdHocExcluded;
              return (
                <li key={m.index} className={styles.listItem}>
                  <input
                    type="checkbox"
                    className={styles.listCheckbox}
                    checked={isIncluded}
                    disabled={isPersistSkip || running || cancelling}
                    onChange={() => toggleMatchExclusion(m.index)}
                    aria-label={`include match ${m.index}`}
                    title={
                      isPersistSkip
                        ? 'preview 画面で skip 設定済 (変更不可)'
                        : '書き出し対象から除外/復帰'
                    }
                  />
                  <span className={`${styles.listMark} ${markClass}`}>
                    {mark}
                  </span>
                  <span className={styles.listName}>{name}</span>
                  <span className={styles.listDur}>{durationDisplay}</span>
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

/**
 * #545 review #8 (2026-04-25): filename 用の `{start}` 変数を `MM-SS` /
 * `H-MM-SS` 形式に format する。`fmtTime` の `:` を `-` に置換した形と等価
 * (Windows filename で `:` が使えないため)。
 *
 * 例:
 * - 0       → `00-00`
 * - 915.5   → `15-15`
 * - 5021.5  → `1-23-41`
 */
export function formatStartForFilename(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) {
    seconds = 0;
  }
  const total = Math.floor(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) {
    return `${h}-${String(m).padStart(2, '0')}-${String(s).padStart(2, '0')}`;
  }
  return `${String(m).padStart(2, '0')}-${String(s).padStart(2, '0')}`;
}

function joinPath(dir: string, name: string): string {
  const separator =
    dir.includes('\\') && !dir.includes('/') ? '\\' : '/';
  if (dir.endsWith('/') || dir.endsWith('\\')) return dir + name;
  return dir + separator + name;
}

/**
 * #466 review #2: source video の親ディレクトリ + `/output` を default に。
 * `videoSource` から `dirname` 相当を抽出する (Windows は `\\` も許容)。
 *
 * #545 review #2 (2026-04-25): Windows の `\\?\` extended-length path prefix
 * は `stripExtendedPathPrefix` で取り除いてから親 dir を切り出す。
 * (なお Tauri 側からの flow としては `appStateStore.setSelectedVideoPath`
 * が pipeline 上の strip ポイントなので通常 prefix は来ないが、defense-in-depth
 * として deriveDefaultOutDir 内でも適用しておく。)
 */
export function deriveDefaultOutDir(videoSource: string | null): string {
  if (!videoSource) return '';
  const normalized = stripExtendedPathPrefix(videoSource);
  const sep = normalized.includes('\\') && !normalized.includes('/') ? '\\' : '/';
  const idx = Math.max(
    normalized.lastIndexOf('/'),
    normalized.lastIndexOf('\\'),
  );
  if (idx <= 0) return '';
  const parent = normalized.slice(0, idx);
  return `${parent}${sep}output`;
}
