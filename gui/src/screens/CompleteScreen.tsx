import { useEffect, useMemo } from 'react';

import { AllaganFrame } from '../components/AllaganFrame';
import { BrightnessTimeline } from '../components/BrightnessTimeline';
import { MatchThumb } from '../components/MatchThumb';
import { RestoreButton } from '../components/RestoreButton';
import { sampleBrightness } from '../data/sampleMetadata';
import { useAppStateStore } from '../state/appStateStore';
import { useMetadataStore } from '../state/metadataStore';
import styles from './CompleteScreen.module.css';

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
        <div className={styles.emptyNote}>No metadata. Run detect first.</div>
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

  return (
    <div className={styles.screen} data-testid="complete-screen">
      <div className={styles.topBar}>
        <div className={styles.statusDot} aria-hidden="true" />
        <div className={styles.sourceBox}>
          <div className={styles.sourceCaption}>観測完了</div>
          <div className={styles.sourceName}>{metadata.source}</div>
        </div>
        <div className={styles.stats}>
          <div>
            <div className={styles.statLabel}>試合数</div>
            <div className={styles.statValue}>{metadata.matches.length}</div>
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
          <button
            type="button"
            className={styles.adjustButton}
            onClick={() =>
              selectedMatch ? openPreviewFor(selectedMatch.index) : undefined
            }
            disabled={!selectedMatch}
            aria-label="境界を調整"
          >
            ⬦ 境界を調整
          </button>
          <button
            type="button"
            className={styles.exportAllButton}
            onClick={() => navigate('export')}
          >
            ⬦ 全試合書き出し
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
        />
      </AllaganFrame>

      <div className={styles.bottom}>
        <div className={styles.listCol}>
          <div className={styles.listHeader}>試合一覧 ⸱ MATCHES</div>
          <ul className={styles.listBody}>
            {metadata.matches.map((m) => {
              const isSel = m.index === selectedMatch?.index;
              return (
                <li
                  key={m.index}
                  onClick={() => selectMatch(m.index)}
                  onDoubleClick={() => openPreviewFor(m.index)}
                  className={`${styles.listItem}${isSel ? ` ${styles.listItemActive}` : ''}`}
                  data-testid={`match-row-${m.index}`}
                  data-selected={isSel ? 'true' : 'false'}
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
