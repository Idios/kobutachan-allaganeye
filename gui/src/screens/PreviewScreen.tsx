import { convertFileSrc, invoke } from '@tauri-apps/api/core';
import { ask } from '@tauri-apps/plugin-dialog';
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { FrameStrip, type FrameStripThumb } from '../components/FrameStrip';
import { InlineErrorHint } from '../components/InlineErrorHint';
import { RestoreButton } from '../components/RestoreButton';
import { useAppStateStore } from '../state/appStateStore';
import {
  useMetadataStore,
  type MatchEditPatch,
} from '../state/metadataStore';
import type { MatchType, TypeOverride } from '../types/metadata';
import { DEFAULT_FPS } from '../types/metadata.schema';
import { fmtPreciseTime } from '../utils/time';
import styles from './PreviewScreen.module.css';

/**
 * #589: debounce window for scheduling `updateMatch` after a local-state edit.
 * ui-interaction-spec.md §1.1 prescribes 200ms — short enough that the
 * `● 未保存の変更` badge feels immediate, long enough to coalesce keystroke
 * bursts on the matchName input. Independent from the 500ms draft auto-save
 * inside metadataStore.
 */
const UPDATE_DEBOUNCE_MS = 200;

interface RegisteredVideo {
  url: string;
  token: string;
}

interface ThumbnailEntry {
  t_seconds: number;
  file_path: string;
}

/**
 * #465 review: 1 フレームの step / TC display は録画固有の fps に従う。
 * `metadata.source_fps` を最優先で読み、欠落時 (legacy metadata.json or
 * sample mode) のみ {@link DEFAULT_FPS} (60) にフォールバック。
 */
function resolveFps(sourceFps: number | undefined): number {
  if (sourceFps && sourceFps > 0) return sourceFps;
  return DEFAULT_FPS;
}

/**
 * Phase 3 preview screen -- video playback + keyboard seek + thumbnails.
 *
 * Adds over Phase 2:
 * - Real `<video>` elements for IN and OUT panes, fed by the axum-backed
 *   `register_video` Tauri command (#465).
 * - Keyboard shortcuts: ArrowLeft/Right = +-1s, Shift+arrow = +-10s,
 *   Alt+arrow = +-1 frame at the recording's source_fps (60 / 120 / 240
 *   are all handled correctly via metadata.source_fps; legacy files
 *   fall back to {@link DEFAULT_FPS}). Space = play/pause on the active
 *   pane.
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
  // #663 — corrective hint rendered as a 2nd line under `applyError` so
  // the user sees both the failure and the recommended next step.
  const applyErrorHint = useMetadataStore((s) => s.applyErrorHint);
  const filePath = useMetadataStore((s) => s.filePath);
  const updateMatch = useMetadataStore((s) => s.updateMatch);
  const apply = useMetadataStore((s) => s.apply);
  const discardEdits = useMetadataStore((s) => s.discardEdits);

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

  // #589: debounced commit of matchName / startT / endT to the store. The
  // schedule effect below depends on these state values, so its closure
  // captures the freshest snapshot on every keystroke; the prior pending
  // timer is cleared before a new one starts, so coalescence is automatic.
  // matchType is committed eagerly in its onChange handler (single-select
  // per ui-interaction-spec.md §1.1 example).
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingPatchRef = useRef<MatchEditPatch | null>(null);
  // Suppress on initial mount and on selection-driven resync so neither path
  // schedules a redundant updateMatch (which would flip dirty for a no-op).
  const suppressScheduleRef = useRef(true);

  // Resync local state when the selected match changes. We use the
  // setState-in-render pattern (React docs: "you-might-not-need-an-effect"
  // → adjusting state when a prop changes) so the new TC values appear in
  // the same render that picks up the new selectedMatchIndex. Ref cleanup
  // (timer + pending patch + schedule suppression) is kept in the effect
  // below — touching refs during render is disallowed.
  const matchIndex = match?.index;
  const [prevMatchIndex, setPrevMatchIndex] = useState<number | undefined>(
    matchIndex,
  );
  if (matchIndex !== prevMatchIndex) {
    setPrevMatchIndex(matchIndex);
    if (match) {
      setStartT(match.edited?.start_time ?? match.start_time);
      setEndT(match.edited?.end_time ?? match.end_time);
      setMatchName(
        match.name ?? `match_${String(match.index).padStart(3, '0')}`,
      );
      setMatchType(match.type_override ?? match.type);
    }
  }

  // Reset debounce machinery when the selection changes. Declared before the
  // schedule effect so it lands first on the same commit, ensuring the
  // schedule effect that follows sees suppressScheduleRef === true and skips
  // commiting the just-resynced values back into the store as if they were
  // user edits.
  useEffect(() => {
    suppressScheduleRef.current = true;
    if (debounceTimerRef.current !== null) {
      clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }
    pendingPatchRef.current = null;
  }, [matchIndex]);

  useEffect(() => {
    if (matchIndex === undefined) return;
    if (suppressScheduleRef.current) {
      suppressScheduleRef.current = false;
      return;
    }
    pendingPatchRef.current = {
      ...pendingPatchRef.current,
      name: matchName,
      edited: { start_time: startT, end_time: endT },
    };
    if (debounceTimerRef.current !== null) clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => {
      if (pendingPatchRef.current) {
        updateMatch(matchIndex, pendingPatchRef.current);
        pendingPatchRef.current = null;
      }
      debounceTimerRef.current = null;
    }, UPDATE_DEBOUNCE_MS);
  }, [startT, endT, matchName, matchIndex, updateMatch]);

  const flushUpdate = useCallback(() => {
    if (debounceTimerRef.current !== null) {
      clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }
    if (pendingPatchRef.current && matchIndex !== undefined) {
      updateMatch(matchIndex, pendingPatchRef.current);
      pendingPatchRef.current = null;
    }
  }, [matchIndex, updateMatch]);

  // Flush on unmount so a debounced edit isn't lost when the user navigates
  // away through a path that doesn't go through handleBack/Export/Apply.
  useEffect(() => () => flushUpdate(), [flushUpdate]);

  // #465 review: source-aware frame rate. Read once from metadata; legacy
  // metadata.json (no `source_fps`) or sample mode falls back to DEFAULT_FPS.
  const fps = resolveFps(metadata?.source_fps);

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

  // #465 review (C): drop で確定した実 path を最優先 source-of-truth として
  // 使用する。sample mode (selectedVideoPath = null) では sampleMetadata.source
  // にフォールバック、実フローでは drop が確定した実 path で
  // register_video / generate_match_thumbnails を発行する。
  const selectedVideoPath = useAppStateStore((s) => s.selectedVideoPath);
  const videoSource = selectedVideoPath ?? metadata?.source ?? null;

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

  // #465 review: frame-grid snap で 1F step を確実に進める。`t + 1/fps` は
  // IEEE 754 の丸めで `Math.floor((t' - floor(t')) * fps)` が増分しない
  // ことがある (例: 2438.75 + 1/120 → frame 表示 .90 のまま)。frame 番号
  // ベースで step してから秒に戻すと丸め誤差を回避できる。
  const nudgeFrame = useCallback(
    (frames: number) => {
      setCurrentT((t: number) => {
        const currentFrame = Math.round(t * fps);
        const nextFrame = Math.max(0, currentFrame + frames);
        return nextFrame / fps;
      });
    },
    [setCurrentT, fps],
  );

  // #465: keyboard shortcuts. ArrowLeft/Right = +-1s, Shift = +-10s,
  // Alt = +-1 frame at fps (frame-grid snap), Space = play/pause on the
  // active pane.
  useEffect(() => {
    const interactiveTags = new Set(['INPUT', 'TEXTAREA', 'SELECT']);
    function handleKey(e: KeyboardEvent) {
      // Let the TC input and other fields own their typing.
      const target = e.target as HTMLElement | null;
      if (target && interactiveTags.has(target.tagName)) return;

      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
        const sign = e.key === 'ArrowLeft' ? -1 : 1;
        if (e.altKey) {
          nudgeFrame(sign);
        } else {
          const magnitude = e.shiftKey ? 10 : 1;
          nudge(sign * magnitude);
        }
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
  }, [nudge, nudgeFrame, activeVideoRef]);

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
    // #589: edits already live in the store via the debounced updateMatch
    // path. Flush any timer that hasn't fired yet, then persist to disk.
    flushUpdate();
    if (filePath) {
      await apply();
    }
  }

  // ui-interaction-spec.md §1.3: confirm-OK on a dirty preview must clear
  // store edits via discardEdits() before navigating, so the destination
  // screen sees the last persisted state. flushUpdate() runs first so any
  // un-fired debounce contributes to the dirty check. Tauri 2's WebView2
  // disables window.confirm() for security, so we go through plugin-dialog's
  // `ask` (yes/no modal).
  async function confirmAndNavigate(
    target: 'complete' | 'export',
    confirmMsg: string,
  ) {
    flushUpdate();
    if (!useMetadataStore.getState().dirty) {
      navigate(target);
      return;
    }
    const confirmed = await ask(confirmMsg, {
      title: '未保存の変更',
      kind: 'warning',
    });
    if (!confirmed) return;
    await discardEdits();
    navigate(target);
  }

  function handleBack() {
    void confirmAndNavigate(
      'complete',
      '未保存の変更があります。破棄して一覧へ戻りますか？',
    );
  }

  function handleExport() {
    void confirmAndNavigate(
      'export',
      '未保存の変更があります。破棄して書き出しへ進みますか？',
    );
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
          onChange={(e) => {
            const v = e.target.value as TypeOverride;
            setMatchType(v);
            // ui-interaction-spec.md §1.1 example: single-select inputs commit
            // immediately rather than going through the 200ms debounce. Flush
            // any pending matchName/startT/endT patch first so we don't fire
            // two updateMatch calls back-to-back.
            flushUpdate();
            if (matchIndex !== undefined) {
              updateMatch(matchIndex, { type_override: v });
            }
          }}
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
          fps={fps}
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
          fps={fps}
        />
      </div>

      <div className={styles.stepRow}>
        {(
          [
            { kind: 'sec', value: -10 },
            { kind: 'sec', value: -1 },
            { kind: 'frame', value: -1 },
            { kind: 'frame', value: 1 },
            { kind: 'sec', value: 1 },
            { kind: 'sec', value: 10 },
          ] as const
        ).map((step, i) => {
          const isFrame = step.kind === 'frame';
          const isTenSec = step.kind === 'sec' && Math.abs(step.value) === 10;
          const label = isFrame
            ? step.value > 0
              ? '+1F'
              : '−1F'
            : step.value > 0
              ? `+${step.value}s`
              : `${step.value}s`;
          // #465 review: ツールチップでキーボード等価操作を明示 (UX item 3)。
          const keyHint = isFrame
            ? step.value > 0
              ? 'Alt + →'
              : 'Alt + ←'
            : isTenSec
              ? step.value > 0
                ? 'Shift + →'
                : 'Shift + ←'
              : step.value > 0
                ? '→'
                : '←';
          return (
            <button
              key={i}
              type="button"
              className={styles.stepButton}
              onClick={() => {
                // #465 review: frame ボタンは frame-grid snap、秒 step は累積
                if (isFrame) nudgeFrame(step.value);
                else nudge(step.value);
              }}
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
            {applyErrorHint && (
              <span className={styles.applyErrorHint}>
                <InlineErrorHint hint={applyErrorHint} />
              </span>
            )}
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
  /** #465 review: fps for TC formatting / parsing on this pane. */
  fps: number;
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
  fps,
}: PaneProps) {
  // #587: data-pane drives the active border color (cyan for IN, gold
  // for OUT) via CSS attribute selectors. The label is the single source
  // of truth for which pane this is.
  const paneKind = label.startsWith('IN') ? 'in' : 'out';
  return (
    <button
      type="button"
      onClick={onActivate}
      className={`${styles.pane}${active ? ` ${styles.paneActive}` : ''}`}
      aria-pressed={active}
      data-pane={paneKind}
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
        value={fmtPreciseTime(t, fps)}
        onChange={(e) => {
          const parsed = parseTimecode(e.target.value, fps);
          if (parsed !== null) onTChange(parsed);
        }}
        aria-label={`${label} timecode`}
        onClick={(e) => e.stopPropagation()}
      />
    </button>
  );
}

/**
 * Parse H:MM:SS.FF back into seconds. Returns null on malformed input.
 *
 * #465 review: fps is required so 120 / 240 fps recordings parse the `.FF`
 * portion as actual frame numbers in their respective denominator.
 */
function parseTimecode(value: string, fps: number): number | null {
  const match = value
    .trim()
    .match(/^(-)?(\d+):(\d{1,2}):(\d{1,2})(?:\.(\d{1,3}))?$/);
  if (!match) return null;
  const [, sign, h, m, s, f] = match;
  const frames = f ? parseInt(f, 10) / fps : 0;
  let total =
    parseInt(h, 10) * 3600 + parseInt(m, 10) * 60 + parseInt(s, 10) + frames;
  if (sign === '-') total = -total;
  return total;
}
