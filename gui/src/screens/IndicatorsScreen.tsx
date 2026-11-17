/**
 * IndicatorsScreen — `allaganeye indicators` の実行画面 (#1106 Phase 2)。
 *
 * 実行状態は `useIndicatorsStore` が全て持つ (Phase 1 で追加)。本画面は
 * 表示と invoke のトリガだけを担い、`listen` / `invoke` の後始末を持たない。
 * 構造は MinimapScreen に揃える (header + 戻る / AllaganFrame + 実行状態ごとの
 * ブロック / primary + secondary ボタン / `role="status"` の進捗)。
 *
 * 状態は 4 つ:
 *
 * - `idle` — 説明 + [⬦ 検出を開始] + [戻る]
 * - `running` — phase (calibrating / scanning) + 進捗 + [中断]
 * - `complete` — KO / ASSIST の件数 + `match_index` ごとにまとめた一覧
 * - `error` — 失敗理由 + (探索領域の解決失敗なら) 領域の手動指定フォーム
 *
 * `complete` の一覧行は「その発生時刻をプレビューで見る」導線で、押すと
 * `appStateStore.pendingSeekSeconds` に `start` を積んでから preview へ遷移する
 * (PreviewScreen が一度だけ消費する)。境界 (startT/endT) は動かさない。
 *
 * 中断 (`cancel()`) は store の契約上 `status='error'` + `subprocess.cancelled`
 * で着地する。ユーザー操作による中断を赤い失敗表示にしないため、その code だけ
 * 中立の「中断しました」+ 再開導線に分岐する。
 */
import { useMemo, useState } from 'react';

import pathStyles from '../styles/path-display.module.css';

import { AllaganFrame } from '../components/AllaganFrame';
import { DisabledTooltip } from '../components/DisabledTooltip';
import { InlineErrorHint } from '../components/InlineErrorHint';
import { SampleModeBanner } from '../components/SampleModeBanner';
import type { ErrorState } from '../lib/appError';
import { useAppStateStore } from '../state/appStateStore';
import {
  useIndicatorsStore,
  type IndicatorsEvent,
  type IndicatorsLayout,
  type IndicatorsRequest,
  type IndicatorsStatus,
} from '../state/indicatorsStore';
import { useMetadataStore } from '../state/metadataStore';
import {
  DEFAULT_MARGIN_SECONDS,
  eventClipWindow,
  overrideWindowFor,
} from '../utils/clipWindow';
import { splitPath } from '../utils/path';
import { signalLabel } from '../utils/signals';
import { fmtClockTime, fmtTime } from '../utils/time';
import styles from './IndicatorsScreen.module.css';

// ── Constants ───────────────────────────────────────────────────────────────

/**
 * CLI exit 4 (探索領域の解決失敗) の文言。Rust 側 `indicators_exit_error` は
 * exit 4 を専用 code に写さず `subprocess.exit_failed` にまとめるため、GUI は
 * `code` だけでは他の異常終了と区別できない。CLI が `{"type":"error"}` 行に
 * 載せる文言 (`allaganeye/commands/indicators.py` の `DetectionError`) で判定する。
 */
const LAYOUT_FAILURE_MARKER = '探索領域を解決できませんでした';

/**
 * CLI `layout_from_bar_region` の下限 (`_REGION_MIN_WIDTH_PX` /
 * `_REGION_MIN_HEIGHT_PX`)。ここで弾けば exit 5 で落ちる入力を送らない。
 */
const REGION_MIN_WIDTH_PX = 20;
const REGION_MIN_HEIGHT_PX = 2;

const INTEGER_RE = /^\d+$/;

// ── Pure helpers (exported for tests) ───────────────────────────────────────

/**
 * 失敗が「探索領域を解決できなかった」ことによるものか。
 *
 * exit 4 は Rust 側で `subprocess.exit_failed` に写像される (`code` では他の
 * 異常終了と区別できない) ので、CLI のメッセージ文言を併せて見る。領域の
 * 手動指定フォームを出すかどうかはこの判定が決める。
 */
export function isLayoutResolutionFailure(error: ErrorState | null): boolean {
  if (error === null) return false;
  if (error.code !== 'subprocess.exit_failed') return false;
  return error.message.includes(LAYOUT_FAILURE_MARKER);
}

/**
 * 録画先頭からの絶対秒を `hh:mm:ss` で表示する (#127)。
 *
 * 実体は `utils/time.ts` の `fmtClockTime` (#1131 でクリップ画面と共用)。
 * 保存値は 0.01 秒精度のままで、表示だけ 1 秒未満を切り捨てる。試合相対で読みたければ
 * `matches[i].start_time` を引けばよい。
 */
export function fmtEventTime(seconds: number): string {
  return fmtClockTime(seconds);
}

/**
 * `signal_id` の人間向け表示 (#127)。**未知の signal_id は null** を返し、
 * 呼び出し側は行ごと描画しない（互換ルール §4-3: 未知信号は既定で無視）。
 */
export interface EventGroup {
  /** 属する試合の index。どの試合にも入らない区間は null。 */
  matchIndex: number | null;
  events: IndicatorsEvent[];
}

/**
 * イベントを `match_index` ごとにまとめる。試合は index 昇順、試合外 (null) は
 * 末尾、各グループ内は開始時刻昇順。CLI の出力順には依存しない。
 */
export function groupEventsByMatch(
  events: readonly IndicatorsEvent[],
): EventGroup[] {
  const byMatch = new Map<number | null, IndicatorsEvent[]>();
  for (const event of events) {
    const bucket = byMatch.get(event.match_index);
    if (bucket) bucket.push(event);
    else byMatch.set(event.match_index, [event]);
  }
  const sortedKeys = [...byMatch.keys()].sort((a, b) => {
    if (a === null) return 1;
    if (b === null) return -1;
    return a - b;
  });
  return sortedKeys.map((matchIndex) => ({
    matchIndex,
    events: [...(byMatch.get(matchIndex) ?? [])].sort(
      (a, b) => a.timestamp - b.timestamp,
    ),
  }));
}

export interface RegionInputs {
  x: string;
  y: string;
  w: string;
  h: string;
}

export const EMPTY_REGION_INPUTS: RegionInputs = { x: '', y: '', w: '', h: '' };

/**
 * 領域フォームの client-side 検証。「0 以上の整数」だけを受け付け、CLI が
 * 即座に拒否する下限 (W/H) も先に弾く。問題なければ null。
 */
export function validateRegionInputs(values: RegionInputs): string | null {
  const fields: Array<{ key: keyof RegionInputs; label: string }> = [
    { key: 'x', label: 'X' },
    { key: 'y', label: 'Y' },
    { key: 'w', label: 'W' },
    { key: 'h', label: 'H' },
  ];
  for (const { key, label } of fields) {
    if (!INTEGER_RE.test(values[key].trim())) {
      return `${label} は 0 以上の整数 (px) で入力してください`;
    }
  }
  if (Number(values.w) < REGION_MIN_WIDTH_PX) {
    return `幅 (W) は ${REGION_MIN_WIDTH_PX}px 以上にしてください`;
  }
  if (Number(values.h) < REGION_MIN_HEIGHT_PX) {
    return `高さ (H) は ${REGION_MIN_HEIGHT_PX}px 以上にしてください`;
  }
  return null;
}

/** 検証済みの入力 (`validateRegionInputs` が null を返した前提) を `--region` の形にする。 */
export function parseRegionInputs(
  values: RegionInputs,
): [number, number, number, number] {
  return [
    Number(values.x.trim()),
    Number(values.y.trim()),
    Number(values.w.trim()),
    Number(values.h.trim()),
  ];
}

function layoutSourceLabel(layout: IndicatorsLayout | null): string {
  if (layout === null) return '不明';
  return layout.source === 'user'
    ? '手動指定 (--region)'
    : '自動解決 (anchor)';
}

function phaseLabel(phase: 'calibrating' | 'scanning' | null): string {
  if (phase === 'calibrating') return '探索領域を解決中';
  if (phase === 'scanning') return 'KO / ASSIST を走査中';
  return '準備中';
}

// ── Component ───────────────────────────────────────────────────────────────

export function IndicatorsScreen() {
  const metadata = useMetadataStore((s) => s.metadata);
  const filePath = useMetadataStore((s) => s.filePath);

  const selectedVideoPath = useAppStateStore((s) => s.selectedVideoPath);
  const navigate = useAppStateStore((s) => s.navigate);
  const setPendingSeekSeconds = useAppStateStore((s) => s.setPendingSeekSeconds);
  const setClipRange = useAppStateStore((s) => s.setClipRange);
  const openPreviewFor = useAppStateStore((s) => s.openPreviewFor);

  const status = useIndicatorsStore((s) => s.status);
  const runMetadataPath = useIndicatorsStore((s) => s.metadataPath);
  const phase = useIndicatorsStore((s) => s.phase);
  const processedSeconds = useIndicatorsStore((s) => s.processedSeconds);
  const totalSeconds = useIndicatorsStore((s) => s.totalSeconds);
  const etaSeconds = useIndicatorsStore((s) => s.etaSeconds);
  const layout = useIndicatorsStore((s) => s.layout);
  const events = useIndicatorsStore((s) => s.events);
  const error = useIndicatorsStore((s) => s.error);
  const start = useIndicatorsStore((s) => s.start);
  const cancel = useIndicatorsStore((s) => s.cancel);

  // 領域フォームは画面ローカルの状態 (§1.1 例外: match 編集ではないため store に
  // commit しない)。`regionAttempted` は「直前の run が --region 付きだったか」で、
  // 2 回目以降の失敗でもフォームを畳まないために持つ (値を直して再実行できる)。
  const [regionInputs, setRegionInputs] = useState<RegionInputs>(EMPTY_REGION_INPUTS);
  const [regionError, setRegionError] = useState<string | null>(null);
  const [regionAttempted, setRegionAttempted] = useState(false);

  const videoSource = selectedVideoPath ?? metadata?.source ?? null;
  const isSample = filePath === null;
  const runDisabled = isSample;
  const runDisabledReason = 'サンプル動画では検出を実行できません';

  // #127 §4-3: 未知の signal_id は描画しない (新しい信号が増えても既存画面は
  // 素通りさせる)。件数も既知分だけを数える。
  const knownEvents = useMemo(
    () => events.filter((e) => signalLabel(e.signal_id) !== null),
    [events],
  );
  const groups = useMemo(() => groupEventsByMatch(knownEvents), [knownEvents]);
  const koCount = knownEvents.filter((e) => e.signal_id === 'ko_indicator').length;
  const assistCount = knownEvents.filter(
    (e) => e.signal_id === 'assist_indicator',
  ).length;

  const percent =
    processedSeconds !== null && totalSeconds !== null && totalSeconds > 0
      ? Math.max(0, Math.min(100, (processedSeconds / totalSeconds) * 100))
      : null;
  const progressText =
    processedSeconds === null
      ? '—'
      : `${fmtTime(processedSeconds)} / ${totalSeconds === null ? '—' : fmtTime(totalSeconds)}`;

  /**
   * #1106 Phase 2 review R1: 結果は「どの metadata.json に対して出したか」で
   * スコープする。録画 A で検出した後 B を load して本画面を開くと、A の結果が
   * そのまま見えてしまい、行を押すと B に A の時刻 / match_index でシークする
   * (存在しない試合もあり得る)。
   *
   * - 走行中で他所のファイル向け: 進捗もその run のものなので専用ブロックに切替
   * - `complete` / `error` で他所のファイル向け: `idle` 扱いにし、結果を隠す
   *   (走行していないので新しい run を開始できる。Phase 1 store の重なり拒否は
   *   走行中のみなので衝突しない)
   */
  const runIsForThisFile =
    runMetadataPath !== null && runMetadataPath === filePath;
  const displayedStatus: IndicatorsStatus =
    status === 'running' ? 'running' : runIsForThisFile ? status : 'idle';
  const runningElsewhere = displayedStatus === 'running' && !runIsForThisFile;

  const cancelled =
    displayedStatus === 'error' && error?.code === 'subprocess.cancelled';
  const showRegionFallback =
    displayedStatus === 'error' &&
    !cancelled &&
    (regionAttempted || isLayoutResolutionFailure(error));

  /**
   * 検出を実行する。`region` を渡すと `--region` fallback 経路になる
   * (`--recalibrate` とは排他なので同時には渡さない)。
   *
   * `start()` は失敗時に store へ `status='error'` + error を立ててから reject
   * するので、ここでは握って二重表示を避ける (中断・busy も同経路)。
   *
   * 成功して CLI が metadata.json を書き換えた場合 (`wroteMetadata`) は、
   * 画面の store を disk に追従させる (review R1)。これをやらないと、次の
   * [再検出] が **自分の write を外部変更とみなして** exit 6 で失敗し、preview の
   * [適用] も偽の競合になる。
   */
  async function runIndicators(
    region?: [number, number, number, number],
  ): Promise<void> {
    const path = filePath;
    if (path === null) return;
    setRegionAttempted(region !== undefined);
    const request: IndicatorsRequest = { metadataPath: path };
    // MinimapScreen と同じく、load 時の mtime を CAS guard として渡す
    // (書込前に metadata.json が外部変更されていたら CLI が exit 6 で拒否する)。
    const mtime = useMetadataStore.getState().loadedMtimeMs;
    if (mtime !== null) request.expectedMtime = mtime;
    if (region !== undefined) request.region = region;
    try {
      const result = await start(request);
      if (result.wrote_metadata) {
        // 走行中に別の録画が load された場合 (画面は unmount 済みでも promise は
        // 生きている) は、そのファイルを A の write-back で refresh しない
        // (無関係な外部変更を黙って取り込まないため)。
        const metadataStore = useMetadataStore.getState();
        if (metadataStore.filePath === path) {
          await metadataStore.refreshFromDiskPreservingEdits();
        }
      }
    } catch {
      // store が error を保持する (画面は status / error だけを見る)。
    }
  }

  function handleRegionRetry(): void {
    const message = validateRegionInputs(regionInputs);
    setRegionError(message);
    if (message !== null) return;
    void runIndicators(parseRegionInputs(regionInputs));
  }

  function onRegionFieldChange(key: keyof RegionInputs, value: string): void {
    setRegionInputs((prev) => ({ ...prev, [key]: value }));
    setRegionError(null);
  }

  /**
   * #1139 -- 行クリックは「クリップ範囲の調整」モードでプレビューを開く。
   *
   * `metadata.events` の位置 (1 始まり) を `signal_id` + `timestamp` で引く。
   * `indicatorsStore.events` は CLI の出力そのもので `metadata.events` とは
   * 別オブジェクトなので、同一性ではなくキーで対応付ける。位置が見つからない
   * (未適用の検出結果など) 場合は位置なしで開き、範囲は参照のみになる。
   */
  function openEvent(event: IndicatorsEvent): void {
    if (event.match_index === null) return;
    const key = `${event.signal_id}@${Math.round(event.timestamp * 100)}`;
    const stored = (metadata?.events ?? []).findIndex(
      (candidate) =>
        `${candidate.signal_id}@${Math.round(candidate.timestamp * 100)}` === key,
    );
    const position = stored >= 0 ? stored + 1 : null;
    const override =
      stored >= 0 ? overrideWindowFor(metadata!.events![stored]) : null;
    const window = override ?? eventClipWindow(event, DEFAULT_MARGIN_SECONDS, DEFAULT_MARGIN_SECONDS);
    setClipRange({ ...window, matchIndex: event.match_index, position });
    setPendingSeekSeconds(event.timestamp);
    openPreviewFor(event.match_index);
  }

  if (!metadata) {
    return (
      <div className={styles.screen} data-testid="indicators-screen" data-status={displayedStatus}>
        <div className={styles.emptyNote} role="status" data-testid="indicators-metadata-missing">
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
    <div className={styles.screen} data-testid="indicators-screen" data-status={displayedStatus}>
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
                  data-testid="indicators-path"
                >
                  <div className={styles.headerFileName}>
                    {fileName || '(video)'}
                  </div>
                  {parentDir && (
                    <div className={pathStyles.pathSecondary}>{parentDir}</div>
                  )}
                </div>
              );
            })()}
          <div className={styles.caption}>KO / ASSIST 検出</div>
          <div className={styles.title}>試合中の KO / ASSIST を検出する</div>
          <div className={styles.purpose}>
            戦意値ゲージの表示を読み取り、KO / ASSIST が表示された時刻を
            0.1 秒刻みで検出します。結果は試合ごとにまとまり、行を選ぶと
            プレビューでその瞬間を開けます。
          </div>
        </div>
      </div>

      <AllaganFrame className={styles.panel}>
        {displayedStatus === 'idle' && (
          <div className={styles.stateBlock}>
            <div className={styles.stateLead} role="status" data-testid="indicators-idle">
              録画全体を走査するため、動画の長さに応じて数分かかることがあります。
            </div>
            <DisabledTooltip
              disabled={runDisabled}
              reason={runDisabledReason}
              inlineHint
            >
              {(p) => (
                <button
                  type="button"
                  className={styles.primaryButton}
                  onClick={() => void runIndicators()}
                  disabled={runDisabled}
                  aria-label="検出を開始"
                  {...p}
                >
                  ⬦ 検出を開始
                </button>
              )}
            </DisabledTooltip>
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={() => navigate('complete')}
            >
              戻る
            </button>
          </div>
        )}

        {displayedStatus === 'running' && runningElsewhere && (
          <div className={styles.stateBlock} data-testid="indicators-other-file-running">
            <div className={styles.stateLead} role="status">
              別の動画の検出が進行中です。完了を待つか、[中断] で停止してから
              この動画を検出してください。
            </div>
            <button
              type="button"
              className={styles.cancelButton}
              onClick={cancel}
            >
              中断
            </button>
          </div>
        )}

        {displayedStatus === 'running' && !runningElsewhere && (
          <div className={styles.stateBlock}>
            <div
              className={styles.progressBox}
              role="status"
              data-testid="indicators-progress"
            >
              <div className={styles.progressHeader}>
                <span className={styles.progressLabel}>{phaseLabel(phase)}</span>
                <span className={styles.progressTime}>{progressText}</span>
              </div>
              {/* #1140: 推定残り時間。算出は CLI (eta_s) が SSoT で、
                  GUI は表示するだけ (逐次走査だった頃の実測と混ざらない)。 */}
              {etaSeconds !== null && (
                <div className={styles.progressEta} data-testid="indicators-eta">
                  {`残り約 ${fmtTime(etaSeconds)}`}
                </div>
              )}
              <div className={styles.progressBar}>
                <div
                  className={styles.progressFill}
                  style={{ width: `${percent ?? 0}%` }}
                />
              </div>
            </div>
            <button
              type="button"
              className={styles.cancelButton}
              onClick={cancel}
            >
              中断
            </button>
          </div>
        )}

        {displayedStatus === 'complete' && (
          <div className={styles.stateBlock}>
            <div
              className={styles.summary}
              role="status"
              data-testid="indicators-summary"
            >
              <span className={styles.summaryKind} data-kind="ko_indicator">
                KO {koCount}
              </span>
              <span className={styles.summaryDivider} aria-hidden="true">
                /
              </span>
              <span className={styles.summaryKind} data-kind="assist_indicator">
                ASSIST {assistCount}
              </span>
            </div>
            <div
              className={styles.provenance}
              data-testid="indicators-layout-source"
            >
              探索領域: {layoutSourceLabel(layout)}
            </div>

            {events.length === 0 ? (
              <div className={styles.emptyNote} data-testid="indicators-empty">
                イベントは見つかりませんでした
              </div>
            ) : (
              <div className={styles.groups}>
                {groups.map((group) => (
                  <div
                    key={group.matchIndex ?? 'outside'}
                    className={styles.group}
                    data-testid={`indicators-group-${group.matchIndex ?? 'outside'}`}
                  >
                    <div className={styles.groupHeading}>
                      {group.matchIndex === null
                        ? '試合外'
                        : `MATCH_${String(group.matchIndex).padStart(3, '0')}`}
                    </div>
                    <ul className={styles.eventList}>
                      {group.events.map((event, i) => {
                        // knownEvents で絞り込み済みなので null にはならない。
                        const kindLabel = signalLabel(event.signal_id) ?? event.signal_id;
                        const range = `${fmtEventTime(event.timestamp)} - ${fmtEventTime(event.end)}`;
                        const body = (
                          <>
                            <span
                              className={styles.kindBadge}
                              data-kind={event.signal_id}
                            >
                              {kindLabel}
                            </span>
                            <span className={styles.timeRange}>{range}</span>
                            <span className={styles.score}>
                              {event.score.toFixed(2)}
                            </span>
                          </>
                        );
                        return (
                          <li
                            key={`${event.signal_id}-${event.timestamp}-${i}`}
                            className={styles.eventItem}
                          >
                            {group.matchIndex === null ? (
                              // 試合外の区間はプレビューの遷移先が無いため、
                              // 押せる見た目にしない (keyboard でも到達しない)。
                              <div
                                className={styles.eventRow}
                                data-navigable="false"
                                data-testid={`indicators-event-outside-${i}`}
                                title="試合外の区間のためプレビューを開けません"
                              >
                                {body}
                              </div>
                            ) : (
                              <button
                                type="button"
                                className={`${styles.eventRow} ${styles.eventRowButton}`}
                                onClick={() => openEvent(event)}
                                aria-label={`${kindLabel} ${range} のクリップ範囲をプレビューで調整`}
                                data-testid={`indicators-event-${group.matchIndex}-${i}`}
                              >
                                {body}
                              </button>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                ))}
              </div>
            )}

            <DisabledTooltip
              disabled={runDisabled}
              reason={runDisabledReason}
              inlineHint
            >
              {(p) => (
                <button
                  type="button"
                  className={styles.secondaryButton}
                  onClick={() => void runIndicators()}
                  disabled={runDisabled}
                  {...p}
                >
                  再検出
                </button>
              )}
            </DisabledTooltip>
            {/* #1131 Phase B2: 検出済みイベントをそのまま切り抜き画面へ渡す。 */}
            {knownEvents.length > 0 && (
              <button
                type="button"
                className={styles.secondaryButton}
                onClick={() => navigate('clips')}
                aria-label="クリップを切り抜く"
              >
                ⬦ クリップを切り抜く
              </button>
            )}
          </div>
        )}

        {displayedStatus === 'error' &&
          (cancelled ? (
            <div className={styles.stateBlock}>
              <div
                className={styles.cancelledNote}
                role="status"
                data-testid="indicators-cancelled"
              >
                検出を中断しました。
              </div>
              <DisabledTooltip
                disabled={runDisabled}
                reason={runDisabledReason}
                inlineHint
              >
                {(p) => (
                  <button
                    type="button"
                    className={styles.primaryButton}
                    onClick={() => void runIndicators()}
                    disabled={runDisabled}
                    aria-label="検出を開始"
                    {...p}
                  >
                    ⬦ 検出を開始
                  </button>
                )}
              </DisabledTooltip>
              <button
                type="button"
                className={styles.secondaryButton}
                onClick={() => navigate('complete')}
              >
                戻る
              </button>
            </div>
          ) : (
            <div className={styles.stateBlock}>
              <div
                className={styles.errorMessage}
                role="alert"
                data-testid="indicators-error"
              >
                <div>検出に失敗しました</div>
                <div>{error?.message}</div>
                <InlineErrorHint hint={error?.hint} />
              </div>

              {showRegionFallback && (
                <div className={styles.regionForm} data-testid="indicators-region-form">
                  <div className={styles.regionCaption}>
                    探索領域を手動で指定して再実行
                  </div>
                  <div className={styles.regionHint}>
                    戦意値ゲージのバー本体を囲む X / Y / W / H (px) を入力してください。
                  </div>
                  <div className={styles.regionInputs}>
                    <label className={styles.regionField}>
                      <span>X</span>
                      <input
                        type="number"
                        min={0}
                        step={1}
                        aria-label="region x"
                        value={regionInputs.x}
                        onChange={(e) => onRegionFieldChange('x', e.target.value)}
                      />
                    </label>
                    <label className={styles.regionField}>
                      <span>Y</span>
                      <input
                        type="number"
                        min={0}
                        step={1}
                        aria-label="region y"
                        value={regionInputs.y}
                        onChange={(e) => onRegionFieldChange('y', e.target.value)}
                      />
                    </label>
                    <label className={styles.regionField}>
                      <span>W</span>
                      <input
                        type="number"
                        min={0}
                        step={1}
                        aria-label="region width"
                        value={regionInputs.w}
                        onChange={(e) => onRegionFieldChange('w', e.target.value)}
                      />
                    </label>
                    <label className={styles.regionField}>
                      <span>H</span>
                      <input
                        type="number"
                        min={0}
                        step={1}
                        aria-label="region height"
                        value={regionInputs.h}
                        onChange={(e) => onRegionFieldChange('h', e.target.value)}
                      />
                    </label>
                  </div>
                  {regionError !== null && (
                    <div
                      className={styles.regionError}
                      role="alert"
                      data-testid="indicators-region-error"
                    >
                      <InlineErrorHint hint={regionError} />
                    </div>
                  )}
                  <button
                    type="button"
                    className={styles.primaryButton}
                    onClick={handleRegionRetry}
                    aria-label="この領域で再実行"
                  >
                    この領域で再実行
                  </button>
                </div>
              )}

              <div className={styles.actions}>
                <DisabledTooltip
                  disabled={runDisabled}
                  reason={runDisabledReason}
                  inlineHint
                >
                  {(p) => (
                    <button
                      type="button"
                      className={styles.secondaryButton}
                      onClick={() => void runIndicators()}
                      disabled={runDisabled}
                      {...p}
                    >
                      再試行
                    </button>
                  )}
                </DisabledTooltip>
                <button
                  type="button"
                  className={styles.secondaryButton}
                  onClick={() => navigate('complete')}
                >
                  戻る
                </button>
              </div>
            </div>
          ))}
      </AllaganFrame>
    </div>
  );
}
