/**
 * ClipsScreen — KO / ASSIST の前後秒数を指定して 1 件ずつ切り抜く (#1131 Phase B2)。
 *
 * L4 の切り抜きは「イベント (KO / ASSIST の表示) の前 `pre` 秒〜後 `post` 秒」を
 * 元録画から切り出す。L7 (#135) の「自動で価値の高いシーンを判別して切り抜く」
 * とは別物で、こちらは**ユーザーが範囲を指定する**画面。
 *
 * 一覧は `metadata.events` (#127) から復元する。`indicatorsStore` の結果ではなく
 * **metadata.json を SSoT** にするので、アプリを再起動しても候補が残る。ただし
 * CLI (`allaganeye clips`) は **disk の metadata.json** を読むため、未適用の編集が
 * ある (`metadataStore.dirty`) 間は切り抜きを実行しない。
 *
 * 行ごとの操作は 2 つ:
 *
 * - [この範囲を確認] — `clipRange` と `pendingSeekSeconds` を appStateStore に積んで
 *   preview へ遷移する (PreviewScreen が範囲バナーと先頭 / 末尾シークを出す)
 * - [切り抜く] — `useClipsStore.start()` で `start_clips` を invoke する
 *   (`--event-index` に `metadata.events` の 1 始まり位置を渡す = 1 件ずつ)
 *
 * 実行は直列 (store が走行中の再入を拒否する)。既存出力があると CLI が exit 5 で
 * 拒否するので、そのときだけ [上書きして切り抜く] を出す (#1132 の緩和)。
 */
import { invoke } from '@tauri-apps/api/core';
import { useMemo, useState } from 'react';

import pathStyles from '../styles/path-display.module.css';

import { AllaganFrame } from '../components/AllaganFrame';
import { SampleModeBanner } from '../components/SampleModeBanner';
import { toErrorState } from '../lib/appError';
import { useAppStateStore } from '../state/appStateStore';
import { useClipsStore, type ClipsRequest } from '../state/clipsStore';
import { useMetadataStore } from '../state/metadataStore';
import type { HighlightEvent } from '../types/metadata.generated';
import {
  DEFAULT_GAP_SECONDS,
  DEFAULT_MARGIN_SECONDS,
  overrideWindowFor,
  planClipWindows,
} from '../utils/clipWindow';
import { splitPath } from '../utils/path';
import { signalLabel } from '../utils/signals';
import { fmtClockTime } from '../utils/time';
import styles from './ClipsScreen.module.css';

// ── Constants ───────────────────────────────────────────────────────────────

// 範囲算出の規則は `../utils/clipWindow.ts` (CLI `plan_clips` の鏡)。
export { DEFAULT_GAP_SECONDS, DEFAULT_MARGIN_SECONDS, planClipWindows };

const SECONDS_RE = /^\d+(\.\d+)?$/;

/** CLI が既存出力を拒否したときの文言 (allaganeye/commands/clips.py)。 */
const ALREADY_EXISTS_MARKER = 'already exist';

/** 切り抜き候補が 0 件のときの理由 (#1141)。 */
export type ClipEmptyReason =
  | 'indicator-failed'
  | 'indicator-skipped'
  | 'not-scanned'
  | 'no-events'
  | 'no-usable-events';

export interface ClipEmptyState {
  reason: ClipEmptyReason;
  message: string;
  /** 補足 (失敗理由 / OFF の可能性等)。表示しないときは null。 */
  detail: string | null;
  /** 次の行動を促すボタンの可視名 (`isSample` のときは描画しない)。 */
  actionLabel: string;
}

/**
 * 候補 0 件の原因を 1 つに潰さず切り分ける (#1141)。
 *
 * 「イベントが無い」には ① 検出が失敗した ② 詳細設定で OFF のまま検出した
 * ③ まだ検出していない ④ 検出したが 0 件 ⑤ 検出したが全部使えない
 * の 5 通りがあり、どれも「先に KO / ASSIST を検出してください」では誤誘導になる
 * (②③ は詳細設定の場所、① は失敗の事実を伝える必要がある)。
 */
export function describeEmptyCandidates(args: {
  /** `metadata.events` が配列として存在するか (キー欠落と空配列を区別する)。 */
  eventsKeyPresent: boolean;
  eventCount: number;
  indicatorStatus: 'detected' | 'skipped' | 'failed' | null;
  /** `warnings[]` の `indicators_failed.context.error` (あれば)。 */
  failureDetail: string | null;
}): ClipEmptyState {
  const {
    eventsKeyPresent,
    eventCount,
    indicatorStatus,
    failureDetail,
  } = args;
  if (!eventsKeyPresent && indicatorStatus === 'failed') {
    return {
      reason: 'indicator-failed',
      message: 'KO / ASSIST の検出に失敗しました（試合の分割は完了しています）。',
      detail: failureDetail,
      actionLabel: '⬦ KO / ASSIST を検出',
    };
  }
  if (!eventsKeyPresent && indicatorStatus === 'skipped') {
    return {
      reason: 'indicator-skipped',
      message:
        '詳細設定で KO / ASSIST 検出を OFF のまま検出したため、イベントがありません。',
      detail: 'ここから検出すると metadata.json に結果が書き込まれます。',
      actionLabel: '⬦ KO / ASSIST を検出',
    };
  }
  if (!eventsKeyPresent) {
    return {
      reason: 'not-scanned',
      message: 'まだ KO / ASSIST を検出していません。',
      detail:
        'この metadata.json は KO / ASSIST の結果を持っていません（詳細設定で OFF のまま検出した場合もここに出ます）。',
      actionLabel: '⬦ KO / ASSIST を検出',
    };
  }
  if (eventCount === 0) {
    return {
      reason: 'no-events',
      message: 'KO / ASSIST は検出されませんでした（0 件）。',
      detail:
        '戦意値ゲージが映っていない区間だけだった可能性があります。再検出できます。',
      actionLabel: '⬦ KO / ASSIST を再検出',
    };
  }
  return {
    reason: 'no-usable-events',
    message: '切り抜ける KO / ASSIST がありません。',
    detail: '検出されたイベントはすべて試合区間の外か、未対応の種類です。',
    actionLabel: '⬦ KO / ASSIST の一覧を見る',
  };
}

// ── Pure helpers (exported for tests) ───────────────────────────────────────

export interface ClipCandidate {
  event: HighlightEvent;
  /**
   * `metadata.events` の **1 始まりの位置**。CLI `--event-index` にそのまま渡す
   * (絞り込んでもクリップ番号は振り直されない)。
   */
  position: number;
}

export interface ClipCandidateGroup {
  matchIndex: number;
  candidates: ClipCandidate[];
}

/**
 * `metadata.events` から切り抜き候補を作る。
 *
 * - 未知の `signal_id` は落とす (#127 §4-3: 未知信号は既定で無視)
 * - `match_index` が null の区間は落とす (CLI も試合区間へクランプできないため対象外)
 * - **`position` は元の並びのまま** (描画順で振り直さない)
 */
export function collectClipCandidates(
  events: readonly HighlightEvent[] | undefined,
): ClipCandidate[] {
  if (!events) return [];
  const out: ClipCandidate[] = [];
  events.forEach((event, index) => {
    if (signalLabel(event.signal_id) === null) return;
    if (event.match_index === null) return;
    out.push({ event, position: index + 1 });
  });
  return out;
}

/** 候補を `match_index` ごとにまとめる (試合 index 昇順、各グループ内は時刻順)。 */
export function groupClipCandidates(
  candidates: readonly ClipCandidate[],
): ClipCandidateGroup[] {
  const byMatch = new Map<number, ClipCandidate[]>();
  for (const candidate of candidates) {
    const matchIndex = candidate.event.match_index;
    if (matchIndex === null) continue;
    const bucket = byMatch.get(matchIndex);
    if (bucket) bucket.push(candidate);
    else byMatch.set(matchIndex, [candidate]);
  }
  return [...byMatch.keys()]
    .sort((a, b) => a - b)
    .map((matchIndex) => ({
      matchIndex,
      candidates: [...(byMatch.get(matchIndex) ?? [])].sort(
        (a, b) => a.event.timestamp - b.event.timestamp,
      ),
    }));
}

/**
 * CLI (`allaganeye/export/clips.py` の `plan_clips` + `filter_clips`) と同じ規則で
 * **実際に書き出される区間** を求める。
 *
 * 規則の正は Python 側で、ここはその鏡。プレビューや行の表示が「書かれるクリップと
 * 違う範囲」を見せないために必要 (codex review 2026-11-17):
 *
 * 1. 試合内のイベントを `timestamp` 昇順に並べ、`次の start - 現在の end <= gap`
 *    なら同じグループへ束ねる (未知の `signal_id` も CLI は束ね対象に含む)
 * 2. グループの区間を `[イベント開始 - pre, イベント終端 + post]` にして
 *    `[0, 試合開始, 試合終了]` でクランプする
 * 3. クランプ後に `end <= start` になるグループはクリップにならない
 *
 * **四捨五入はしない**代わりに、**0.01 秒未満の区間はクリップにしない**。CLI は
 * argv / `-ss` の精度のために `round(..., 2)` してから 0 幅を判定する。JS の
 * half-up と Python の half-even を完全に再現するより、「丸めたら潰れる幅」を
 * 先に落とすほうが単純で、CLI が書かないクリップを GUI が提供しないことを保証できる
 * (codex review 2026-11-17)。0.01 秒以上の区間では表示 (秒切り捨て) が変わらない。
 *
 * 戻り値は **`metadata.events` の 1 始まり位置 -> 区間**。
 */
/**
 * 前後秒数フォームの client-side 検証。CLI は 0 以上の有限値しか受け付けない
 * (負値 / nan / inf は exit 5)。問題なければ null。
 */
export function validateMargins(
  preText: string,
  postText: string,
): string | null {
  for (const [label, text] of [
    ['前', preText],
    ['後', postText],
  ] as const) {
    if (!SECONDS_RE.test(text.trim())) {
      return `${label} は 0 以上の秒数で入力してください (例: 10)`;
    }
  }
  return null;
}

/** 検証済みの入力を数値にする。 */
export function parseMargins(
  preText: string,
  postText: string,
): { pre: number; post: number } {
  return { pre: Number(preText.trim()), post: Number(postText.trim()) };
}

/**
 * 表示用の寛容なパース。入力途中 (`""` / `"-"` など) でも行の表示を壊さないよう、
 * 不正値は 0 として扱う (実行時は `validateMargins` が先に弾く)。
 */
function parseMarginsSafe(
  preText: string,
  postText: string,
): { pre: number; post: number } {
  const read = (text: string) =>
    SECONDS_RE.test(text.trim()) ? Number(text.trim()) : 0;
  return { pre: read(preText), post: read(postText) };
}

function isAlreadyExistsError(message: string | undefined): boolean {
  return typeof message === 'string' && message.includes(ALREADY_EXISTS_MARKER);
}

// ── Component ───────────────────────────────────────────────────────────────

export function ClipsScreen() {
  const metadata = useMetadataStore((s) => s.metadata);
  const filePath = useMetadataStore((s) => s.filePath);
  const dirty = useMetadataStore((s) => s.dirty);

  const selectedVideoPath = useAppStateStore((s) => s.selectedVideoPath);
  const navigate = useAppStateStore((s) => s.navigate);
  const setPendingSeekSeconds = useAppStateStore((s) => s.setPendingSeekSeconds);
  const setClipRange = useAppStateStore((s) => s.setClipRange);
  const openPreviewFor = useAppStateStore((s) => s.openPreviewFor);

  const status = useClipsStore((s) => s.status);
  const runMetadataPath = useClipsStore((s) => s.metadataPath);
  const progress = useClipsStore((s) => s.progress);
  const result = useClipsStore((s) => s.result);
  const error = useClipsStore((s) => s.error);
  const start = useClipsStore((s) => s.start);
  const cancel = useClipsStore((s) => s.cancel);

  const [preText, setPreText] = useState(String(DEFAULT_MARGIN_SECONDS));
  const [postText, setPostText] = useState(String(DEFAULT_MARGIN_SECONDS));
  const [codec, setCodec] = useState<'copy' | 'h264'>('copy');
  const [marginsError, setMarginsError] = useState<string | null>(null);
  /** 直近の実行対象 (上書き再実行のために覚えておく)。 */
  const [lastPosition, setLastPosition] = useState<number | null>(null);
  /** 実行直前に metadata.json の外部変更を検知して読み直したときの通知。 */
  const [staleNote, setStaleNote] = useState<string | null>(null);

  const videoSource = selectedVideoPath ?? metadata?.source ?? null;
  const isSample = filePath === null;

  const allEvents = metadata?.events;
  const candidates = useMemo(
    () => collectClipCandidates(allEvents),
    [allEvents],
  );
  const groups = useMemo(() => groupClipCandidates(candidates), [candidates]);
  const outsideCount = useMemo(() => {
    const events = allEvents ?? [];
    return events.filter(
      (e) => signalLabel(e.signal_id) !== null && e.match_index === null,
    ).length;
  }, [allEvents]);

  // #1141 -- 候補 0 件の理由を切り分ける材料。`indicator_status` はこの
  // フィールドを書く writer (0.4.0+) の metadata にだけ入る。
  const indicatorStatus = metadata?.indicator_status ?? null;
  const eventsKeyPresent = Array.isArray(allEvents);
  const indicatorWarning = (metadata?.warnings ?? []).find(
    (warning) => warning.code === 'indicators_failed',
  );
  const indicatorFailureDetail =
    typeof indicatorWarning?.context?.error === 'string'
      ? indicatorWarning.context.error
      : null;
  const emptyState = describeEmptyCandidates({
    eventsKeyPresent,
    eventCount: allEvents?.length ?? 0,
    indicatorStatus,
    failureDetail: indicatorFailureDetail,
  });

  // 走行中の run が別ファイル向けなら、その進捗も結果も見せない (§2.8.0 前提 4)。
  // 画面は idle 扱いにし、[⬦ 切り抜く] を disabled + 理由 + [中断] で逃げ道を出す
  // (indicators の §2.7.11 と同じ規則)。
  const runIsForThisFile =
    runMetadataPath !== null && runMetadataPath === filePath;
  const runningElsewhere = status === 'running' && !runIsForThisFile;
  const displayedStatus = runIsForThisFile ? status : 'idle';
  const cancelled =
    displayedStatus === 'error' && error?.code === 'subprocess.cancelled';
  // 「既存出力あり」で止まったときだけ上書き再実行を出す (それ以外の exit 5 は
  // 秒数の入力ミス等なので、勝手に overwrite を立てない)。
  const canOverwriteRetry =
    displayedStatus === 'error' && isAlreadyExistsError(error?.message);

  const margins = validateMargins(preText, postText);
  const runDisabledReason = isSample
    ? 'サンプル動画では切り抜きを実行できません'
    : dirty
      ? '未適用の編集があります。先に [適用] してから切り抜いてください'
      : runningElsewhere
        ? '別の動画の切り抜きが進行中です。完了を待つか [中断] で停止してください'
        : margins;
  const runDisabled = runDisabledReason !== null && displayedStatus !== 'running';

  // 実際に書き出される区間 (CLI の `plan_clips` + クランプの鏡)。
  // pre / post を編集したら再計算するので、表示とプレビューが常に一致する。
  const windows = useMemo(() => {
    const { pre, post } = parseMarginsSafe(preText, postText);
    return planClipWindows(allEvents, metadata?.matches ?? [], pre, post);
  }, [allEvents, metadata, preText, postText]);

  /** 行の「実際の区間」。クランプの結果 0 幅なら null (クリップにならない)。 */
  function windowFor(position: number): { start: number; end: number } | null {
    return windows.get(position) ?? null;
  }

  const percent =
    progress === null ? null : Math.max(0, Math.min(100, progress.percent));

  /**
   * 1 件だけ切り抜く。`overwrite` は「既存出力あり」で一度止まった後の再実行でだけ
   * true にする (無確認の truncate をしない)。
   *
   * spawn の直前に **disk の mtime を照合**する: CLI は disk の metadata.json を
   * 読むので、load 後に外から `events[]` が書き換わっていたら位置が別のイベントを
   * 指し、上書き再実行では無関係のクリップを潰し得る (codex review 2026-11-17)。
   * 変わっていたら reload して 1 度止め、ユーザーに再クリックさせる。
   */
  async function cutOne(position: number, overwrite: boolean): Promise<void> {
    const path = filePath;
    if (path === null || dirty) {
      // ボタンは disabled だが、再実行ボタン経由の呼び出しもここで止める。
      return;
    }
    const message = validateMargins(preText, postText);
    setMarginsError(message);
    if (message !== null) return;

    setStaleNote(null);
    const knownMtime = useMetadataStore.getState().loadedMtimeMs;
    let diskMtime: number | null;
    try {
      diskMtime = await invoke<number | null>('get_metadata_mtime', { path });
    } catch {
      diskMtime = null;
    }
    if (diskMtime === null || knownMtime === null || diskMtime !== knownMtime) {
      // 照合できない / 変わっている: 実行しない (位置が古い可能性がある)。
      try {
        await useMetadataStore.getState().refreshFromDiskPreservingEdits();
        setStaleNote(
          'metadata.json が外部で更新されていたため、候補を読み直しました。内容を確認してもう一度切り抜いてください。',
        );
      } catch {
        setStaleNote(
          'metadata.json を読み直せませんでした。一覧へ戻って読み込み直してください。',
        );
      }
      return;
    }

    const { pre, post } = parseMargins(preText, postText);
    setLastPosition(position);
    const request: ClipsRequest = {
      metadataPath: path,
      pre,
      post,
      codec,
      eventIndexes: [position],
      overwrite,
      // read-time CAS: 読み取り直前に CLI が同じ mtime を見ることを強制する
      // (上の mtime 照合と spawn の間に外部変更が入っても、CLI 側で exit 6 になる)。
      expectedMtime: knownMtime,
    };
    try {
      await start(request);
    } catch {
      // store が error を保持する (画面は status / error だけを見る)。
    }
  }

  /** 行の [この範囲を確認] — 実際に書かれる区間を積んで preview へ。 */
  function confirmRange(candidate: ClipCandidate): void {
    const message = validateMargins(preText, postText);
    setMarginsError(message);
    if (message !== null) return;
    const range = windowFor(candidate.position);
    const matchIndex = candidate.event.match_index;
    if (range === null || matchIndex === null) return;
    setClipRange({ ...range, matchIndex, position: candidate.position });
    setPendingSeekSeconds(range.start);
    openPreviewFor(matchIndex);
  }

  if (!metadata) {
    return (
      <div className={styles.screen} data-testid="clips-screen" data-status="idle">
        <div className={styles.emptyNote} role="status" data-testid="clips-metadata-missing">
          metadata.json が読み込まれていません。先に検出を実行してください。
        </div>
        <button
          type="button"
          className={styles.backButton}
          onClick={() => navigate('complete')}
        >
          ◀ 一覧へ
        </button>
      </div>
    );
  }

  return (
    <div className={styles.screen} data-testid="clips-screen" data-status={displayedStatus}>
      <SampleModeBanner />

      <div className={styles.header}>
        <button
          type="button"
          className={styles.backButton}
          onClick={() => navigate('complete')}
        >
          ◀ 一覧へ
        </button>
        <div>
          {videoSource &&
            (() => {
              const { fileName, parentDir } = splitPath(videoSource);
              return (
                <div
                  className={pathStyles.pathDisplay}
                  title={videoSource}
                  data-testid="clips-path"
                >
                  <div className={styles.headerFileName}>{fileName || '(video)'}</div>
                  {parentDir && (
                    <div className={pathStyles.pathSecondary}>{parentDir}</div>
                  )}
                </div>
              );
            })()}
          <div className={styles.caption}>CLIPS</div>
          <div className={styles.title}>KO / ASSIST の前後を切り抜く</div>
          <div className={styles.purpose}>
            KO / ASSIST が表示された時刻の前後を秒数で指定して、元録画から
            クリップを切り出します。1 件ずつ範囲を確認しながら切り抜けます。
          </div>
        </div>
      </div>

      <AllaganFrame className={styles.panel}>
        <div className={styles.controls}>
          <label className={styles.controlField}>
            <span>前 (秒)</span>
            <input
              type="number"
              min={0}
              step={1}
              value={preText}
              aria-label="前 (秒)"
              onChange={(e) => {
                setPreText(e.target.value);
                setMarginsError(null);
              }}
            />
          </label>
          <label className={styles.controlField}>
            <span>後 (秒)</span>
            <input
              type="number"
              min={0}
              step={1}
              value={postText}
              aria-label="後 (秒)"
              onChange={(e) => {
                setPostText(e.target.value);
                setMarginsError(null);
              }}
            />
          </label>
          <label className={styles.controlField}>
            <span>形式</span>
            <select
              value={codec}
              aria-label="形式"
              onChange={(e) => setCodec(e.target.value === 'h264' ? 'h264' : 'copy')}
            >
              <option value="copy">無劣化 (copy)</option>
              <option value="h264">再エンコード (h264)</option>
            </select>
          </label>
        </div>
        {marginsError !== null && (
          <div className={styles.fieldError} role="alert" data-testid="clips-margins-error">
            {marginsError}
          </div>
        )}
        {runDisabled && (
          <div className={styles.note} role="status" data-testid="clips-run-disabled">
            {runDisabledReason}
          </div>
        )}
        {runningElsewhere && (
          <button
            type="button"
            className={styles.cancelButton}
            onClick={cancel}
            data-testid="clips-other-file-cancel"
          >
            中断
          </button>
        )}
        {outsideCount > 0 && (
          <div className={styles.note} data-testid="clips-outside-note">
            {outsideCount} 件は試合区間の外にあるため切り抜けません。
          </div>
        )}
        {staleNote !== null && (
          <div className={styles.note} role="status" data-testid="clips-stale-note">
            {staleNote}
          </div>
        )}

        {displayedStatus === 'running' && (
          <div className={styles.stateBlock} data-testid="clips-progress">
            <div className={styles.progressBox} role="status">
              <div className={styles.progressHeader}>
                <span className={styles.progressLabel}>切り抜き中</span>
                <span className={styles.progressTime}>
                  clip {progress === null ? '—' : String(progress.match_index).padStart(3, '0')}
                  {progress === null
                    ? ''
                    : ` ・ ${Math.round(percent ?? 0)}% ・ ${progress.stage}`}
                </span>
              </div>
              <div className={styles.progressBar}>
                <div
                  className={styles.progressFill}
                  style={{ width: `${percent ?? 0}%` }}
                />
              </div>
              {progress?.message !== undefined && progress.message !== '' && (
                <div className={styles.progressMessage}>{progress.message}</div>
              )}
            </div>
            <button type="button" className={styles.cancelButton} onClick={cancel}>
              中断
            </button>
          </div>
        )}

        {displayedStatus === 'complete' && result !== null && (
          <div className={styles.stateBlock} data-testid="clips-result">
            <div className={styles.summary} role="status">
              <span className={styles.summaryOk}>成功 {result.success}</span>
              <span className={styles.summaryDivider} aria-hidden="true">
                /
              </span>
              <span className={styles.summaryFail}>失敗 {result.failure}</span>
            </div>
            {result.output_paths.length > 0 && (
              <ul className={styles.outputList}>
                {result.output_paths.map((outputPath) => (
                  <li key={outputPath} className={styles.outputItem}>
                    <span className={styles.outputPath} title={outputPath}>
                      {outputPath}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {displayedStatus === 'error' && (
          <div className={styles.stateBlock} data-testid="clips-error">
            {cancelled ? (
              <div className={styles.note} role="status" data-testid="clips-cancelled">
                切り抜きを中断しました。
              </div>
            ) : (
              <div className={styles.errorMessage} role="alert">
                <span>{error?.message ?? toErrorState(error).message}</span>
                {error?.hint !== null && error?.hint !== undefined && (
                  <span className={styles.errorHint}>{error.hint}</span>
                )}
                {canOverwriteRetry && lastPosition !== null && (
                  <button
                    type="button"
                    className={styles.secondaryButton}
                    onClick={() => void cutOne(lastPosition, true)}
                    disabled={runDisabled}
                    data-testid="clips-overwrite-retry"
                  >
                    上書きして切り抜く
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        {candidates.length === 0 ? (
          <div className={styles.emptyBlock}>
            <div
              className={styles.emptyNote}
              data-testid="clips-empty"
              data-reason={emptyState.reason}
            >
              {emptyState.message}
            </div>
            {emptyState.detail !== null && (
              <div className={styles.note} data-testid="clips-empty-detail">
                {emptyState.detail}
              </div>
            )}
            {!isSample && (
              <button
                type="button"
                className={styles.secondaryButton}
                onClick={() => navigate('indicators')}
              >
                {emptyState.actionLabel}
              </button>
            )}
          </div>
        ) : (
          <div className={styles.groups}>
            {groups.map((group) => (
              <div
                key={group.matchIndex}
                className={styles.group}
                data-testid={`clips-group-${group.matchIndex}`}
              >
                <div className={styles.groupHeading}>
                  {`MATCH_${String(group.matchIndex).padStart(3, '0')}`}
                </div>
                <ul className={styles.candidateList}>
                  {group.candidates.map((candidate) => {
                    const { event, position } = candidate;
                    const kindLabel = signalLabel(event.signal_id) ?? event.signal_id;
                    // 実際に書き出される区間 (束ね + 試合区間クランプ済)。
                    const range = windowFor(position);
                    const manual = overrideWindowFor(event) !== null;
                    const duration =
                      range === null ? 0 : Math.max(0, range.end - range.start);
                    return (
                      <li
                        key={`${event.signal_id}-${event.timestamp}-${position}`}
                        className={styles.candidateItem}
                        data-testid={`clips-candidate-${position}`}
                      >
                        <span className={styles.kindBadge} data-kind={event.signal_id}>
                          {kindLabel}
                        </span>
                        <span className={styles.timeRange}>
                          {`${fmtClockTime(event.timestamp)} - ${fmtClockTime(event.end)}`}
                        </span>
                        <span className={styles.clipRange}>
                          {range === null
                            ? '範囲外'
                            : `範囲 ${fmtClockTime(range.start)} - ${fmtClockTime(range.end)} ・ ${duration.toFixed(1)} 秒`}
                        </span>
                        {manual && (
                          <span
                            className={styles.manualBadge}
                            title="プレビューで指定したクリップ範囲"
                            data-testid={`clips-manual-${position}`}
                          >
                            手動
                          </span>
                        )}
                        <button
                          type="button"
                          className={styles.secondaryButton}
                          onClick={() => confirmRange(candidate)}
                          disabled={range === null}
                          aria-label={`${kindLabel} ${fmtClockTime(event.timestamp)} の範囲をプレビューで確認`}
                          data-testid={`clips-preview-${position}`}
                        >
                          この範囲を確認
                        </button>
                        <button
                          type="button"
                          className={styles.cutButton}
                          onClick={() => void cutOne(position, false)}
                          disabled={runDisabled || range === null}
                          aria-label={`${kindLabel} ${fmtClockTime(event.timestamp)} を切り抜く`}
                          data-testid={`clips-cut-${position}`}
                        >
                          ⬦ 切り抜く
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>
        )}
      </AllaganFrame>
    </div>
  );
}
