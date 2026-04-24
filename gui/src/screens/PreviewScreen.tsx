import { convertFileSrc, invoke } from '@tauri-apps/api/core';
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { FrameStrip, type FrameStripThumb } from '../components/FrameStrip';
import { RestoreButton } from '../components/RestoreButton';
import { useAppStateStore } from '../state/appStateStore';
import { useMetadataStore } from '../state/metadataStore';
import type { MatchType, TypeOverride } from '../types/metadata';
import { fmtPreciseTime } from '../utils/time';
import styles from './PreviewScreen.module.css';

interface RegisteredVideo {
  url: string;
  token: string;
}

interface ThumbnailEntry {
  t_seconds: number;
  file_path: string;
}

/** Default assumption for ±1 frame stepping. Real fps would come from probe
 *  metadata, but Phase 3 keeps this as a simple constant until we expose fps
 *  through the metadata contract. */
const ASSUMED_FPS = 60;

/**
 * Phase 3 preview screen -- video playback + keyboard seek + thumbnails.
 *
 * Adds over Phase 2:
 * - Real `<video>` elements for IN and OUT panes, fed by the axum-backed
 *   `register_video` Tauri command (#465).
 * - Keyboard shortcuts: ArrowLeft/Right = +-1s, Shift+arrow = +-10s,
 *   Alt+arrow = +-1 frame, Space = play/pause on the active pane.
 * - The active pane's video.currentTime follows the editable start/end,
 *   giving frame-accurate seek preview.
 * - Click on the video toggles play/pause on the active pane (UX item 4).
 * - TC display follows `video.currentTime` during playback (UX review
 *   追加). Paused 中は nudge / manual input が t の source、playback 中は
 *   video 側が source。境界の最終値 (edited.start_time / end_time) は
 *   停止時の currentTime になる。
 * - FrameStrip still serves a cache of thumbnails around the boundary; the
 *   Rust side generates them through `generate_match_thumbnails`.
 *
 * ## Playback architecture (#465 review item 7)
 *
 * Preview uses **axum direct file serving** (HTML5 `<video>` + range
 * request against the token-gated `127.0.0.1:random` endpoint) — not
 * ffmpeg transcoding. As a consequence:
 * - No ffmpeg subprocess is spawned while the user browses the preview
 *   screen. `PROCESS_TRACKER` stays empty until export runs (#466).
 * - The × close confirmation flow (#523) guards against in-flight
 *   *export* ffmpeg processes, not preview. Verifying the flow requires
 *   the export screen (#545 Phase 4).
 * - Thumbnails are generated eagerly on pane mount via
 *   `generate_match_thumbnails`; those ffmpeg calls exit before the user
 *   interacts and are not tracked in `PROCESS_TRACKER`.
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

  // #465: per-mount video URL fetched from the axum server. One registration
  // covers both panes (HTMLVideoElement instances can share the same URL).
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [videoError, setVideoError] = useState<string | null>(null);

  // #465: thumbnail cache fetched from the Rust `generate_match_thumbnails`
  // command (via ffmpeg). Keyed per boundary side; falls back to [] while
  // the request is in-flight or when register_video failed.
  const [inThumbs, setInThumbs] = useState<readonly FrameStripThumb[]>([]);
  const [outThumbs, setOutThumbs] = useState<readonly FrameStripThumb[]>([]);

  const inVideoRef = useRef<HTMLVideoElement>(null);
  const outVideoRef = useRef<HTMLVideoElement>(null);

  const videoSource = metadata?.source ?? null;

  useEffect(() => {
    if (!videoSource) return;
    let cancelled = false;
    (async () => {
      try {
        const registered = await invoke<RegisteredVideo>('register_video', {
          path: videoSource,
        });
        if (!cancelled) {
          setVideoUrl(registered.url);
          setVideoError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setVideoUrl(null);
          setVideoError(e instanceof Error ? e.message : String(e));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [videoSource]);

  // Keep each video's currentTime in sync with the edit buffer so a keyboard
  // nudge immediately seeks the frame preview. We only seek when the numeric
  // value actually changes to avoid feedback loops with timeupdate events.
  //
  // #465 review 追加: `v.paused` guard で playback 中は seek しない。再生中の
  // onTimeUpdate が setStartT/setEndT を呼ぶため、もし guard が無いと
  //   timeupdate → setStartT(cur) → effect 実行中に cur が advance →
  //   effect は差分 > 0.001 を検出し backward seek
  // というループで再生が揺れる。paused 中のみ state → video を反映する。
  useEffect(() => {
    const v = inVideoRef.current;
    if (
      v &&
      v.paused &&
      !Number.isNaN(startT) &&
      Math.abs(v.currentTime - startT) > 0.001
    ) {
      try {
        v.currentTime = startT;
      } catch {
        // ignore seek failure during initial load
      }
    }
  }, [startT, videoUrl]);

  useEffect(() => {
    const v = outVideoRef.current;
    if (
      v &&
      v.paused &&
      !Number.isNaN(endT) &&
      Math.abs(v.currentTime - endT) > 0.001
    ) {
      try {
        v.currentTime = endT;
      } catch {
        // ignore
      }
    }
  }, [endT, videoUrl]);

  // #465: fetch candidate-frame thumbnails around the start boundary. Runs
  // when the boundary moves by more than ~0.5s so ffmpeg calls aren't
  // spammed on each single-frame nudge (cache hits handle the rest anyway).
  useEffect(() => {
    if (!videoSource || !videoUrl || !match) return;
    let cancelled = false;
    (async () => {
      try {
        const entries = await invoke<ThumbnailEntry[]>(
          'generate_match_thumbnails',
          {
            videoPath: videoSource,
            matchIndex: match.index,
            boundaryTSeconds: match.edited?.start_time ?? match.start_time,
            windowSeconds: 3,
            count: 12,
          },
        );
        if (!cancelled) {
          setInThumbs(
            entries.map((e) => ({
              t: e.t_seconds,
              url: convertFileSrc(e.file_path),
            })),
          );
        }
      } catch {
        if (!cancelled) setInThumbs([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [videoSource, videoUrl, match]);

  useEffect(() => {
    if (!videoSource || !videoUrl || !match) return;
    let cancelled = false;
    (async () => {
      try {
        const entries = await invoke<ThumbnailEntry[]>(
          'generate_match_thumbnails',
          {
            videoPath: videoSource,
            matchIndex: match.index,
            boundaryTSeconds: match.edited?.end_time ?? match.end_time,
            windowSeconds: 3,
            count: 12,
          },
        );
        if (!cancelled) {
          setOutThumbs(
            entries.map((e) => ({
              t: e.t_seconds,
              url: convertFileSrc(e.file_path),
            })),
          );
        }
      } catch {
        if (!cancelled) setOutThumbs([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [videoSource, videoUrl, match]);

  const currentT = editing === 'start' ? startT : endT;
  const setCurrentT = editing === 'start' ? setStartT : setEndT;
  const activeVideoRef = editing === 'start' ? inVideoRef : outVideoRef;

  const nudge = useCallback(
    (sec: number) => {
      setCurrentT((t: number) => Math.max(0, t + sec));
    },
    [setCurrentT],
  );

  // #465: keyboard shortcuts. ArrowLeft/Right = +-1s, Shift = +-10s,
  // Alt = +-1 frame at ASSUMED_FPS, Space = play/pause on the active pane.
  useEffect(() => {
    const interactiveTags = new Set(['INPUT', 'TEXTAREA', 'SELECT']);
    function handleKey(e: KeyboardEvent) {
      // Let the TC input and other fields own their typing.
      const target = e.target as HTMLElement | null;
      if (target && interactiveTags.has(target.tagName)) return;

      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
        const sign = e.key === 'ArrowLeft' ? -1 : 1;
        const magnitude = e.shiftKey ? 10 : e.altKey ? 1 / ASSUMED_FPS : 1;
        nudge(sign * magnitude);
        e.preventDefault();
        return;
      }
      if (e.key === ' ') {
        const v = activeVideoRef.current;
        if (v) {
          if (v.paused) void v.play().catch(() => undefined);
          else v.pause();
        }
        e.preventDefault();
      }
    }
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [nudge, activeVideoRef]);

  const matchLabel = useMemo(
    () => (match ? `match_${String(match.index).padStart(3, '0')}` : ''),
    [match],
  );

  if (!match) {
    return (
      <div className={styles.screen} data-testid="preview-screen">
        <div className={styles.emptyNote}>No match selected.</div>
      </div>
    );
  }

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
              placeholder={matchLabel}
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
          onActivate={() => setEditing('start')}
          onTChange={(v) => setStartT(v)}
          videoUrl={videoUrl}
          videoError={videoError}
          videoRef={inVideoRef}
        />
        <Pane
          label="OUT (end)"
          active={editing === 'end'}
          t={endT}
          onActivate={() => setEditing('end')}
          onTChange={(v) => setEndT(v)}
          videoUrl={videoUrl}
          videoError={videoError}
          videoRef={outVideoRef}
        />
      </div>

      <div className={styles.stepRow}>
        {[-10, -1, -1 / ASSUMED_FPS, 1 / ASSUMED_FPS, 1, 10].map((step, i) => {
          const isFrame =
            Math.abs(step - 1 / ASSUMED_FPS) < 1e-6 ||
            Math.abs(step + 1 / ASSUMED_FPS) < 1e-6;
          const isTenSec = Math.abs(step) === 10;
          const label = isFrame
            ? step > 0
              ? '+1F'
              : '−1F'
            : step > 0
              ? `+${step}s`
              : `${step}s`;
          // #465 review: ツールチップでキーボード等価操作を明示 (UX item 3)。
          const keyHint = isFrame
            ? step > 0
              ? 'Alt + →'
              : 'Alt + ←'
            : isTenSec
              ? step > 0
                ? 'Shift + →'
                : 'Shift + ←'
              : step > 0
                ? '→'
                : '←';
          return (
            <button
              key={i}
              type="button"
              className={styles.stepButton}
              onClick={() => nudge(step)}
              aria-label={`nudge ${label}`}
              title={`${label} (${keyHint})`}
            >
              {label}
            </button>
          );
        })}
      </div>

      {/* #465 review: キーボードショートカット可視化 (UX item 3)。stepRow 下に
       *  インライン hint を出し、はじめてのユーザーにも操作方法が伝わる。 */}
      <div className={styles.keyHint} role="note" aria-label="keyboard shortcuts">
        <span className={styles.keyHintItem}>
          <kbd className={styles.kbd}>←</kbd>
          <kbd className={styles.kbd}>→</kbd> 1s
        </span>
        <span className={styles.keyHintItem}>
          <kbd className={styles.kbd}>Shift</kbd>+<kbd className={styles.kbd}>←→</kbd> 10s
        </span>
        <span className={styles.keyHintItem}>
          <kbd className={styles.kbd}>Alt</kbd>+<kbd className={styles.kbd}>←→</kbd> 1F
        </span>
        <span className={styles.keyHintItem}>
          <kbd className={styles.kbd}>Space</kbd> / クリック: 再生/停止
        </span>
      </div>

      <div className={styles.strip}>
        <div className={styles.stripCaption}>候補フレーム ⸱ CANDIDATE FRAMES</div>
        <FrameStrip
          boundaryT={currentT}
          windowSec={3}
          count={12}
          onSelectFrame={(t) => setCurrentT(t)}
          thumbs={editing === 'start' ? inThumbs : outThumbs}
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
  onActivate: () => void;
  onTChange: (v: number) => void;
  videoUrl: string | null;
  videoError: string | null;
  videoRef: React.RefObject<HTMLVideoElement | null>;
}

function Pane({
  label,
  active,
  t,
  onActivate,
  onTChange,
  videoUrl,
  videoError,
  videoRef,
}: PaneProps) {
  return (
    <button
      type="button"
      onClick={onActivate}
      className={`${styles.pane}${active ? ` ${styles.paneActive}` : ''}`}
      aria-pressed={active}
    >
      <div className={styles.paneCaption}>{label}</div>
      <div className={styles.paneVideo}>
        {videoUrl ? (
          <video
            ref={videoRef}
            src={videoUrl}
            preload="metadata"
            playsInline
            controls={false}
            className={styles.paneVideoEl}
            aria-label={`${label} video`}
            title="クリックで再生/停止 (Space キーでも同じ)"
            // #465 review: クリックで再生・停止 (UX item 4)。stopPropagation で
            // Pane の activate 遷移は抑え、pane はすでに active な状態で
            // play/pause を切り替える。inactive pane をクリックした場合は
            // activate を先に呼ぶため、もう一度クリックで play/pause できる。
            onClick={(e) => {
              e.stopPropagation();
              if (!active) {
                onActivate();
                return;
              }
              const v = videoRef.current;
              if (v) {
                if (v.paused) void v.play().catch(() => undefined);
                else v.pause();
              }
            }}
            // #465 review 追加: 再生中は TC 表示 (onTChange) を video.currentTime
            // に同期させる (UX 追加: ユーザー期待)。paused 中は nudge / 手入力
            // した t を残したいので guard。paused 状態の最終 timeupdate も読む
            // ので、pause 後の TC は「停止したフレームの時刻」になる。
            // 逆方向の sync (t → video.currentTime) は外側の useEffect が 0.001
            // 閾値付きで担当しており feedback loop は起きない。
            onTimeUpdate={(e) => {
              const v = e.currentTarget;
              if (!v.paused) {
                onTChange(v.currentTime);
              }
            }}
          />
        ) : videoError ? (
          <div className={styles.paneVideoError} role="alert">
            {videoError}
          </div>
        ) : (
          <div className={styles.paneVideoLoading}>loading video…</div>
        )}
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
  const match = value
    .trim()
    .match(/^(-)?(\d+):(\d{1,2}):(\d{1,2})(?:\.(\d{1,3}))?$/);
  if (!match) return null;
  const [, sign, h, m, s, f] = match;
  const frames = f ? parseInt(f, 10) / ASSUMED_FPS : 0;
  let total =
    parseInt(h, 10) * 3600 + parseInt(m, 10) * 60 + parseInt(s, 10) + frames;
  if (sign === '-') total = -total;
  return total;
}
