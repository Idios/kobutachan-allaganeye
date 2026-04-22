import { useState } from 'react';

import { FrameStrip } from '../components/FrameStrip';
import { MatchThumb } from '../components/MatchThumb';
import { RestoreButton } from '../components/RestoreButton';
import { useAppStateStore } from '../state/appStateStore';
import { useMetadataStore } from '../state/metadataStore';
import type { MatchType, TypeOverride } from '../types/metadata';
import { fmtPreciseTime } from '../utils/time';
import styles from './PreviewScreen.module.css';

/**
 * Phase 2 preview screen — A1 Dual IN/OUT variant.
 *
 * Local state:
 * - active 'start' | 'end' (which pane/timestamp is being edited)
 * - startT / endT (editable copies of the match boundaries)
 * - matchName / matchType (editable copies of the name and type override)
 *
 * On mount the local state is seeded from the store's current match (honoring
 * any prior `edited` / `name` / `type_override` patch). [適用] writes back via
 * updateMatch + apply. [一覧へ] navigates back (confirming if dirty). [元に戻す]
 * (#516) fires the restore flow and navigates back to complete.
 *
 * Phase 3 (#465) will replace the <MatchThumb> with a real `<video>` player
 * fed by the axum HTTP server, and the FrameStrip with real decoded thumbnails.
 */
export function PreviewScreen() {
  const metadata = useMetadataStore((s) => s.metadata);
  const dirty = useMetadataStore((s) => s.dirty);
  const applying = useMetadataStore((s) => s.applying);
  const applyError = useMetadataStore((s) => s.applyError);
  const filePath = useMetadataStore((s) => s.filePath);
  const updateMatch = useMetadataStore((s) => s.updateMatch);
  const apply = useMetadataStore((s) => s.apply);

  const selectedMatchIndex = useAppStateStore((s) => s.selectedMatchIndex);
  const navigate = useAppStateStore((s) => s.navigate);

  const match = metadata?.matches.find((m) => m.index === selectedMatchIndex);

  // All local draft state is initialized from the current match on first
  // render. Resetting the draft on match change is handled by `key=` in the
  // parent App.tsx (React remounts → fresh useState values), per the React 19
  // "Avoid setState in effect" guidance.
  const [editing, setEditing] = useState<'start' | 'end'>('start');
  const [startT, setStartT] = useState<number>(
    match ? (match.edited?.start_time ?? match.start_time) : 0,
  );
  const [endT, setEndT] = useState<number>(
    match ? (match.edited?.end_time ?? match.end_time) : 0,
  );
  const [matchName, setMatchName] = useState<string>(
    match
      ? (match.name ?? `match_${String(match.index).padStart(3, '0')}`)
      : '',
  );
  const [matchType, setMatchType] = useState<TypeOverride>(
    match ? (match.type_override ?? match.type) : 'fl_match',
  );

  if (!match) {
    return (
      <div className={styles.screen} data-testid="preview-screen">
        <div className={styles.emptyNote}>No match selected.</div>
      </div>
    );
  }

  const currentT = editing === 'start' ? startT : endT;
  const setCurrentT = editing === 'start' ? setStartT : setEndT;
  const nudge = (sec: number) =>
    setCurrentT((t: number) => Math.max(0, t + sec));

  async function handleApply() {
    updateMatch(match!.index, {
      name: matchName,
      type_override: matchType,
      edited: { start_time: startT, end_time: endT },
    });
    if (filePath) {
      await apply();
    }
  }

  function handleBack() {
    if (dirty) {
      const ok = window.confirm(
        '未適用の変更があります。破棄して戻りますか？',
      );
      if (!ok) return;
    }
    navigate('complete');
  }

  function handleExport() {
    if (dirty) {
      const ok = window.confirm(
        '未適用の変更があります。破棄して書き出しに進みますか？',
      );
      if (!ok) return;
    }
    navigate('export');
  }

  const selectable: MatchType[] = ['fl_match', 'unknown'];

  return (
    <div className={styles.screen} data-testid="preview-screen">
      <div className={styles.header}>
        <button
          type="button"
          className={styles.backButton}
          onClick={handleBack}
        >
          ◀ 一覧へ
        </button>
        <div className={styles.headerInfo}>
          <div className={styles.caption}>境界調整 ⸱ BOUNDARY CALIBRATION</div>
          <div className={styles.nameRow}>
            <input
              className={styles.nameInput}
              value={matchName}
              onChange={(e) => setMatchName(e.target.value)}
              aria-label="match name"
            />
            <span className={styles.meta}>
              #{String(match.index).padStart(3, '0')} · of{' '}
              {metadata!.matches.length}
            </span>
          </div>
        </div>
        <select
          className={styles.typeSelect}
          value={matchType}
          onChange={(e) => setMatchType(e.target.value as TypeOverride)}
          aria-label="match type"
        >
          {selectable.map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
          <option value="skip">skip</option>
        </select>
      </div>

      <div className={styles.panes}>
        <Pane
          label="IN (start)"
          active={editing === 'start'}
          t={startT}
          onClick={() => setEditing('start')}
          onTChange={(v) => setStartT(v)}
          index={match.index}
        />
        <Pane
          label="OUT (end)"
          active={editing === 'end'}
          t={endT}
          onClick={() => setEditing('end')}
          onTChange={(v) => setEndT(v)}
          index={match.index}
        />
      </div>

      <div className={styles.stepRow}>
        {[-10, -1, -1 / 60, 1 / 60, 1, 10].map((step, i) => {
          const label =
            Math.abs(step) === 1 / 60
              ? step > 0
                ? '+1F'
                : '−1F'
              : step > 0
                ? `+${step}s`
                : `${step}s`;
          return (
            <button
              key={i}
              type="button"
              className={styles.stepButton}
              onClick={() => nudge(step)}
              aria-label={`nudge ${label}`}
            >
              {label}
            </button>
          );
        })}
      </div>

      <div className={styles.strip}>
        <div className={styles.stripCaption}>候補フレーム ⸱ CANDIDATE FRAMES</div>
        <FrameStrip
          boundaryT={currentT}
          windowSec={3}
          count={12}
          onSelectFrame={(t) => setCurrentT(t)}
        />
      </div>

      <div className={styles.actionsRow}>
        <button
          type="button"
          className={styles.primaryButton}
          onClick={handleApply}
          disabled={applying || !filePath}
          aria-label="apply"
        >
          {applying ? '適用中…' : '⬦ 適用'}
        </button>
        {dirty && <span className={styles.dirty}>● 未保存の変更</span>}
        {applyError && (
          <span className={styles.applyError} role="alert">
            {applyError}
          </span>
        )}
        <RestoreButton onRestored={() => navigate('complete')} />
        <button
          type="button"
          className={styles.secondaryButton}
          onClick={handleExport}
        >
          書き出し →
        </button>
      </div>
    </div>
  );
}

interface PaneProps {
  label: string;
  active: boolean;
  t: number;
  onClick: () => void;
  onTChange: (v: number) => void;
  index: number;
}

function Pane({ label, active, t, onClick, onTChange, index }: PaneProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`${styles.pane}${active ? ` ${styles.paneActive}` : ''}`}
      aria-pressed={active}
    >
      <div className={styles.paneCaption}>{label}</div>
      <div className={styles.paneVideo}>
        <MatchThumb index={index} width="100%" height="100%" />
      </div>
      <input
        className={styles.tcInput}
        value={fmtPreciseTime(t)}
        onChange={(e) => {
          const parsed = parseTimecode(e.target.value);
          if (parsed !== null) onTChange(parsed);
        }}
        aria-label={`${label} timecode`}
        onClick={(e) => e.stopPropagation()}
      />
    </button>
  );
}

/** Parse H:MM:SS.FF back into seconds. Returns null on malformed input. */
function parseTimecode(value: string): number | null {
  const match = value.trim().match(/^(-)?(\d+):(\d{1,2}):(\d{1,2})(?:\.(\d{1,3}))?$/);
  if (!match) return null;
  const [, sign, h, m, s, f] = match;
  const frames = f ? parseInt(f, 10) / 60 : 0;
  let total = parseInt(h, 10) * 3600 + parseInt(m, 10) * 60 + parseInt(s, 10) + frames;
  if (sign === '-') total = -total;
  return total;
}
