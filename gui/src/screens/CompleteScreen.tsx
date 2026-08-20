import { useEffect, useMemo, type KeyboardEvent } from 'react';

import { AllaganFrame } from '../components/AllaganFrame';
import { BrightnessTimeline } from '../components/BrightnessTimeline';
import { DisabledTooltip } from '../components/DisabledTooltip';
import { InlineErrorHint } from '../components/InlineErrorHint';
import { MatchThumb } from '../components/MatchThumb';
import { RestoreButton } from '../components/RestoreButton';
import { SampleModeBanner } from '../components/SampleModeBanner';
import { sampleBrightness } from '../data/sampleMetadata';
import { useAppStateStore } from '../state/appStateStore';
import { useMetadataStore } from '../state/metadataStore';
import { splitPath } from '../utils/path';
import { fmtTime } from '../utils/time';
import pathStyles from '../styles/path-display.module.css';
import styles from './CompleteScreen.module.css';

/**
 * Render the elapsed detection wall-clock as a M:SS / H:MM:SS string,
 * falling back to "—" when either timestamp is missing or unparseable
 * (#586 受け入れ条件 #586-3 legacy fallback). Pure function: no store
 * access, no side-effects, exported only for testing convenience.
 */
export function formatElapsed(
  startedAt: string | undefined,
  completedAt: string | undefined,
): string {
  if (!startedAt || !completedAt) return '—';
  const startMs = Date.parse(startedAt);
  const endMs = Date.parse(completedAt);
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs < startMs) {
    return '—';
  }
  return fmtTime((endMs - startMs) / 1000);
}

/**
 * Phase 2 complete screen. Uses metadataStore for the list of matches and
 * appStateStore.selectedMatchIndex for the currently highlighted match.
 *
 * Phase 3/4 will replace the sampleBrightness with real per-video brightness
 * extraction from the detect run.
 */
export function CompleteScreen() {
  const metadata = useMetadataStore((s) => s.metadata);
  const clear = useMetadataStore((s) => s.clear);
  const loadErrorState = useMetadataStore((s) => s.loadErrorState);

  const selectedMatchIndex = useAppStateStore((s) => s.selectedMatchIndex);
  const selectMatch = useAppStateStore((s) => s.selectMatch);
  const openPreviewFor = useAppStateStore((s) => s.openPreviewFor);
  const navigate = useAppStateStore((s) => s.navigate);
  const appReset = useAppStateStore((s) => s.reset);

  // #465 review (A,C): drop で確定した実 path を MatchThumb に渡し、
  // generate_match_thumbnails で実フレーム WebP を表示する。sample mode
  // (selectedVideoPath = null) では metadata.source にフォールバック。
  const selectedVideoPath = useAppStateStore((s) => s.selectedVideoPath);
  const thumbVideoPath = selectedVideoPath ?? metadata?.source ?? null;

  // On mount, if nothing is selected and matches exist, select first.
  useEffect(() => {
    if (metadata && metadata.matches.length > 0 && selectedMatchIndex === null) {
      selectMatch(metadata.matches[0].index);
    }
  }, [metadata, selectedMatchIndex, selectMatch]);

  // #569 -- prefer the pre-rendered brightness timeline written by
  // `allaganeye detect` (Pass 1 sampling), fall back to the in-memory
  // sample curve only when metadata.json doesn't carry the field
  // (sample mode after `loadSample()`, or detect cache hit before
  // re-detection, or pre-#569 metadata files).
  const brightness = useMemo(() => {
    if (metadata?.brightness_samples?.values?.length) {
      return metadata.brightness_samples.values;
    }
    return sampleBrightness();
  }, [metadata?.brightness_samples]);

  if (!metadata) {
    return (
      <div className={styles.screen} data-testid="complete-screen">
        {loadErrorState ? (
          <div
            className={styles.emptyNote}
            role="alert"
            data-testid="complete-load-error"
          >
            <div>metadata.json の読み込みに失敗しました</div>
            <div>{loadErrorState.message}</div>
            <InlineErrorHint hint={loadErrorState.hint} />
          </div>
        ) : (
          <div className={styles.emptyNote}>No metadata. Run detect first.</div>
        )}
      </div>
    );
  }

  const selectedMatch =
    metadata.matches.find((m) => m.index === selectedMatchIndex) ??
    metadata.matches[0];

  function handleClose() {
    clear();
    appReset();
    navigate('drop');
  }

  // #944 §D: post_match は default split / export の対象外なので、complete の
  // 「試合数」(全件) と export 見出しの件数がずれる。内訳表示に使う。
  const postMatchCount = metadata.matches.filter((m) => m.post_match).length;
  // #944 §D: masked fallback は 0 暗転時に自動発火するが、GUI へは何も伝えて
  // いなかった (`masked_fallback_used` は schema にあるのにどこにも描画されて
  // いない)。ユーザーは通常経路との違いを知る手段が無かった。
  const maskedFallbackUsed =
    metadata.detection_params?.masked_fallback_used === true;

  return (
    <div className={styles.screen} data-testid="complete-screen">
      <SampleModeBanner />
      {maskedFallbackUsed && (
        <div
          className={styles.fallbackNotice}
          role="status"
          data-testid="complete-masked-fallback-notice"
        >
          通常の検知で暗転が見つからなかったため、<b>マスク録画向けの経路</b>
          （CLI の <code>--masked</code> 相当）に自動で切り替えて検知しました。
          結果が期待と違う場合は、CLI で <code>--masked</code> や{' '}
          <code>--vtuber</code> を明示して再検知してください。
        </div>
      )}
      <div className={styles.topBar}>
        <div className={styles.statusDot} aria-hidden="true" />
        <div className={styles.sourceBox}>
          <div className={styles.sourceCaption}>観測完了</div>
          {(() => {
            // #676 / iterate-review Round 1: ローカル名を videoSource に統一
            // (PreviewScreen.tsx:261 / ExportScreen.tsx:126 の `videoSource` と同名)
            const videoSource = selectedVideoPath ?? metadata.source;
            const { fileName, parentDir } = splitPath(videoSource);
            return (
              <div
                className={pathStyles.pathDisplay}
                title={videoSource}
                data-testid="complete-path"
              >
                <div className={styles.sourceName}>{fileName || '(video)'}</div>
                {parentDir && (
                  <div className={pathStyles.pathSecondary}>{parentDir}</div>
                )}
              </div>
            );
          })()}
        </div>
        <div className={styles.stats}>
          <div>
            <div className={styles.statLabel}>試合数</div>
            <div className={styles.statValue}>{metadata.matches.length}</div>
            {/* #944 §D: この数は post_match を含むが、export 画面の見出しは
                含まない件数を出すため「数が食い違う」と読めた。内訳を出して
                どちらも正しいことが分かるようにする (数自体は変えない)。 */}
            {postMatchCount > 0 && (
              <div
                className={styles.statNote}
                data-testid="complete-post-match-note"
              >
                うち {postMatchCount} 件は試合後
              </div>
            )}
          </div>
          <div>
            <div className={styles.statLabel}>所要</div>
            <div className={styles.statValue}>
              {formatElapsed(
                metadata.detection_started_at,
                metadata.detection_completed_at,
              )}
            </div>
          </div>
          <div>
            <div className={styles.statLabel}>総尺</div>
            <div className={styles.statValue}>
              {metadata.source_duration_display}
            </div>
          </div>
        </div>
        <div className={styles.actions}>
          <RestoreButton />
          {/* #587 §2.3.5: explain why [境界を調整] is disabled when nothing is selected. */}
          <DisabledTooltip
            disabled={!selectedMatch}
            reason="試合が選択されていません"
            inlineHint
          >
            {(p) => (
              <button
                type="button"
                className={styles.adjustButton}
                onClick={() =>
                  selectedMatch ? openPreviewFor(selectedMatch.index) : undefined
                }
                disabled={!selectedMatch}
                aria-label="境界を調整"
                {...p}
              >
                ⬦ 境界を調整
              </button>
            )}
          </DisabledTooltip>
          <button
            type="button"
            className={styles.exportAllButton}
            onClick={() => navigate('export')}
          >
            ⬦ 全試合書き出し
          </button>
          <button
            type="button"
            className={styles.exportAllButton}
            onClick={() => navigate('minimap')}
            disabled={metadata.matches.length === 0}
            aria-label="ミニマップ切抜き"
          >
            ⬦ ミニマップ切抜き
          </button>
          <button
            type="button"
            className={styles.closeButton}
            aria-label="閉じる"
            onClick={handleClose}
          >
            × 閉じる
          </button>
        </div>
      </div>

      <AllaganFrame className={styles.timelinePane}>
        <div className={styles.timelineCaption}>輝度 ⸱ BRIGHTNESS TIMELINE</div>
        <BrightnessTimeline
          samples={brightness}
          duration={metadata.source_duration}
          matches={metadata.matches}
          selectedIndex={selectedMatch?.index ?? null}
          onSelectMatch={(i) => selectMatch(i)}
          // #588: 検知時に使用された閾値で暗転帯を描画。legacy metadata
          // (detection_params 無し) では 15 (BrightnessTimeline 既定) に
          // フォールバックする。
          threshold={metadata.detection_params?.blackout_threshold ?? 15}
        />
      </AllaganFrame>

      <div className={styles.bottom}>
        <div className={styles.listCol}>
          <div className={styles.listHeader}>試合一覧 ⸱ MATCHES</div>
          {/* #587: keyboard nav for the match list. ↑↓ shifts the
              selection, Home/End jump to ends, Enter/Space opens preview. */}
          <ul
            className={styles.listBody}
            tabIndex={0}
            onKeyDown={(e: KeyboardEvent<HTMLUListElement>) => {
              if (!metadata) return;
              const matches = metadata.matches;
              if (matches.length === 0) return;
              const idx = matches.findIndex(
                (mm) => mm.index === selectedMatch?.index,
              );
              if (e.key === 'ArrowDown') {
                e.preventDefault();
                const next = matches[Math.min(matches.length - 1, idx + 1)];
                selectMatch(next.index);
              } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                const prev = matches[Math.max(0, idx - 1)];
                selectMatch(prev.index);
              } else if (e.key === 'Home') {
                e.preventDefault();
                selectMatch(matches[0].index);
              } else if (e.key === 'End') {
                e.preventDefault();
                selectMatch(matches[matches.length - 1].index);
              } else if (e.key === 'Enter' || e.key === ' ') {
                if (selectedMatch) {
                  e.preventDefault();
                  openPreviewFor(selectedMatch.index);
                }
              }
            }}
          >
            {metadata.matches.map((m) => {
              const isSel = m.index === selectedMatch?.index;
              // #805 Phase 2: post_match trailing は default split/export の
              // 対象外 (機能除外は Phase 1 済)。一覧では dimmed + badge で区別。
              const isPostMatch = m.post_match === true;
              return (
                <li
                  key={m.index}
                  onClick={() => selectMatch(m.index)}
                  onDoubleClick={() => openPreviewFor(m.index)}
                  className={`${styles.listItem}${isSel ? ` ${styles.listItemActive}` : ''}${isPostMatch ? ` ${styles.listItemPostMatch}` : ''}`}
                  data-testid={`match-row-${m.index}`}
                  data-selected={isSel ? 'true' : 'false'}
                  {...(isPostMatch ? { 'data-post-match': 'true' } : {})}
                >
                  <MatchThumb
                    index={m.index}
                    videoPath={thumbVideoPath}
                    startTime={m.start_time}
                    width={48}
                    height={27}
                  />
                  <div className={styles.listItemBody}>
                    <div className={styles.listItemTitle}>
                      {m.name ?? `MATCH_${String(m.index).padStart(3, '0')}`}
                    </div>
                    <div className={styles.listItemSub}>
                      {m.start_display} → {m.end_display} · {m.duration_display}
                    </div>
                  </div>
                  {isPostMatch && (
                    <div
                      className={`${styles.typeBadge} ${styles.postMatchBadge}`}
                      title="試合終了後のロビー・街と判定された区間です。metadata.json には残りますが、既定では MP4 に書き出されません（CLI の --keep-trailing で出力できます）。"
                    >
                      試合後
                    </div>
                  )}
                  <div
                    className={`${styles.typeBadge}${m.type === 'fl_match' ? ` ${styles.typeBadgeFl}` : ` ${styles.typeBadgeUnknown}`}`}
                  >
                    {m.type === 'fl_match' ? 'FL' : '?'}
                  </div>
                </li>
              );
            })}
          </ul>
        </div>

        {selectedMatch && (
          <div className={styles.previewPane}>
            <AllaganFrame className={styles.previewFrame}>
              <div className={styles.previewInner}>
                <MatchThumb
                  index={selectedMatch.index}
                  videoPath={thumbVideoPath}
                  startTime={selectedMatch.start_time}
                  width="100%"
                  height="100%"
                />
                <div className={styles.previewPlayOverlay}>
                  <div className={styles.previewPlayBadge} aria-hidden="true">
                    ▶
                  </div>
                </div>
              </div>
            </AllaganFrame>
            <div className={styles.previewMeta}>
              <div className={styles.previewMetaTitle}>
                match_{String(selectedMatch.index).padStart(3, '0')}.mp4
              </div>
              <div className={styles.previewMetaRow}>
                <span className={styles.previewMetaLabel}>開始</span>
                <span>{selectedMatch.start_display}</span>
              </div>
              <div className={styles.previewMetaRow}>
                <span className={styles.previewMetaLabel}>終了</span>
                <span>{selectedMatch.end_display}</span>
              </div>
              <div className={styles.previewMetaRow}>
                <span className={styles.previewMetaLabel}>長さ</span>
                <span>{selectedMatch.duration_display}</span>
              </div>
              <div className={styles.previewMetaRow}>
                <span className={styles.previewMetaLabel}>分類</span>
                <span>{selectedMatch.type}</span>
              </div>
            </div>
            {/* 境界を調整 action was moved to the top action bar (#464 review
                feedback — the pane button could scroll below the fold on
                shorter viewports). */}
          </div>
        )}
      </div>
    </div>
  );
}
