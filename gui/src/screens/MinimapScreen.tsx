/**
 * MinimapScreen — video pane + match scrubber for minimap region proposal,
 * plus settings / include checkboxes / crop execution / progress / dirty guard
 * / reload / ConflictModal. (#893 Phase 2 minimap crop GUI integration)
 *
 * Shows the source video seeked to the midpoint of the selected eligible
 * match, with a <select> to switch between matches, a drag-select overlay
 * to pick the region visually, and 4 numeric X/Y/W/H inputs.
 *
 * Execution side mirrors ExportScreen (start_export → start_minimap,
 * export-progress → minimap-progress, same race guards + dirty guard).
 */
import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';
import { open as openDialog } from '@tauri-apps/plugin-dialog';
import { useEffect, useMemo, useReducer, useRef, useState } from 'react';

import pathStyles from '../styles/path-display.module.css';

import { DisabledTooltip } from '../components/DisabledTooltip';
import { SampleModeBanner } from '../components/SampleModeBanner';
import { useEscapeKey } from '../hooks/useEscapeKey';
import { useFocusTrap } from '../hooks/useFocusTrap';
import { isAppError } from '../lib/appError';
import { useAppStateStore } from '../state/appStateStore';
import { useMetadataStore } from '../state/metadataStore';
import { NamePatternWarnings } from '../components/NamePatternWarnings';
import { fmtMatchDuration, fmtTime } from '../utils/time';
import { formatMatchFilename } from '../utils/filename';
import { computeNamePatternIssues } from '../utils/namePatternSandbox';
import { splitPath, stripExtendedPathPrefix } from '../utils/path';
import { elementRectToSourcePx, validateRegionPx, type RegionPx } from '../utils/region';
import { deriveDefaultOutDir } from './ExportScreen';
import { minimapReducer } from './reducers/minimap';
import styles from './MinimapScreen.module.css';

// ── Types ───────────────────────────────────────────────────────────────────

type MatchStatus = 'pending' | 'running' | 'done' | 'error' | 'skipped';

interface MatchState {
  status: MatchStatus;
  percent: number;
  error?: string;
  /** #899 -- NVENC 失敗で libx264 へ retry したときの per-match notice。 */
  fallbackNotice?: string;
}

interface MinimapProgressPayload {
  match_index: number;
  percent: number;
  stage: 'encoding' | 'done' | 'error' | 'fallback';
  message?: string;
  /** #899 -- e.g. `"h264_nvenc -> libx264"`. Present when stage === 'fallback'. */
  fallback_from?: string;
}

// ── Component ────────────────────────────────────────────────────────────────

export function MinimapScreen() {
  const metadata = useMetadataStore((s) => s.metadata);
  const filePath = useMetadataStore((s) => s.filePath);
  const navigate = useAppStateStore((s) => s.navigate);
  const selectedVideoPath = useAppStateStore((s) => s.selectedVideoPath);
  const lastExportOutputDir = useAppStateStore((s) => s.lastExportOutputDir);
  const videoSource = selectedVideoPath ?? metadata?.source ?? null;

  // Sample mode: metadata loaded but no backing file on disk
  const isSample = filePath === null && metadata !== null;
  const sampleReason = 'サンプル動画では保存できません';

  const eligible = useMemo(
    () => (metadata?.matches ?? []).filter((m) => !m.post_match && m.type_override !== 'skip'),
    [metadata],
  );

  const [frameMatchIndex, setFrameMatchIndex] = useState<number | null>(
    eligible[0]?.index ?? null,
  );
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  // Region state
  const [region, setRegion] = useState<RegionPx | null>(null);
  const [regionError, setRegionError] = useState<string | null>(null);

  // Drag state (element-space client coords and overlay-relative rect)
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null);
  const [dragCur, setDragCur] = useState<{ x: number; y: number } | null>(null);
  // Overlay-relative rect for visual rubber band (updated in onMouseMove)
  const [dragRect, setDragRect] = useState<{ left: number; top: number; width: number; height: number } | null>(null);

  // Auto-detect state
  const [detecting, setDetecting] = useState(false);
  const [detectNotice, setDetectNotice] = useState<string | null>(null);

  // ── Settings ──────────────────────────────────────────────────────────────

  // #893 R2: default to lastExportOutputDir (the dir used in the last export).
  //
  // #928: the fallback derives from `videoSource`, not from the metadata.json
  // path. The GUI detect flow always writes metadata.json to
  // "<video dir>/<stem>_allaganeye/" (deriveDetectOutputDir), so deriving the
  // fallback from filePath put minimap output in the metadata folder instead of
  // next to the match videos -- the opposite of #902's intent, even though the
  // old comment claimed it matched ExportScreen. Sharing ExportScreen's
  // deriveDefaultOutDir keeps the two screens on one basis by construction.
  const [outDir, setOutDir] = useState<string>(
    () => lastExportOutputDir ?? deriveDefaultOutDir(videoSource),
  );
  const [namePattern, setNamePattern] = useState('{idx:03}_{type}_{start}_minimap.mp4');

  // Per-match include checkboxes (ad-hoc exclude set, same as ExportScreen)
  const [excluded, setExcluded] = useState<ReadonlySet<number>>(() => new Set());

  // Crop execution phase
  const [phase, dispatch] = useReducer(minimapReducer, 'idle');
  const [matchStates, setMatchStates] = useState<Record<number, MatchState>>({});
  const [cropStartMs, setCropStartMs] = useState<number | null>(null);
  const [nowMs, setNowMs] = useState<number>(() => Date.now());

  // ConflictModal for mtime conflict
  const [showConflict, setShowConflict] = useState(false);
  // #587: focus trap + Escape for the local conflict modal (same hooks as shared ConflictModal)
  const conflictPanelRef = useRef<HTMLDivElement>(null);
  useFocusTrap(conflictPanelRef, showConflict);
  useEscapeKey(showConflict, () => setShowConflict(false));

  // Open-folder error
  const [openFolderError, setOpenFolderError] = useState<string | null>(null);

  const running = phase === 'running';
  const completed = phase === 'completed';
  const cancelling = phase === 'cancelling';
  const error = phase === 'error';

  // 1s wall-clock tick while running
  useEffect(() => {
    if (cropStartMs === null) return;
    if (phase !== 'running') return;
    const iv = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(iv);
  }, [cropStartMs, phase]);

  // minimap-progress event listener — mirror ExportScreen's export-progress listener
  // with same race guard (disposed flag) and post_match stray-event guard.
  useEffect(() => {
    let unlisten: UnlistenFn | null = null;
    // Unmount-before-listen-resolves race guard (#837 / #813 same pattern)
    let disposed = false;
    const warnedStray = new Set<number>();
    (async () => {
      const u = await listen<MinimapProgressPayload>('minimap-progress', (event) => {
        const p = event.payload;
        // Drop stray events for post_match rows (same as ExportScreen review R1 #2)
        const strayTarget = useMetadataStore
          .getState()
          .metadata?.matches.find((mm) => mm.index === p.match_index);
        if (strayTarget?.post_match === true) {
          if (!warnedStray.has(p.match_index)) {
            warnedStray.add(p.match_index);
            console.warn(
              '[minimap] dropped stray minimap-progress event for post_match match',
              p.match_index,
            );
          }
          return;
        }
        setMatchStates((prev) => {
          const prior = prev[p.match_index] ?? { status: 'pending' as MatchStatus, percent: 0 };
          let status: MatchStatus = prior.status;
          if (p.stage === 'encoding') status = 'running';
          else if (p.stage === 'done') status = 'done';
          else if (p.stage === 'error') status = 'error';
          // #899 -- `-vf crop` 経路の NVENC encode 失敗で libx264 へ retry した
          // とき、Rust 側は stage="fallback" / percent=0 を emit する。通知を
          // per-match に刻み「なぜ巻き戻って遅くなったのか」を UI から辿れる
          // ようにする (libx264 で encode がやり直しになるので percent が 0 に
          // 戻ること自体は正しい)。
          //
          // status も running へ倒す: NVENC の初期化失敗は 1 frame も encode
          // せずに落ちるため fallback がその match の最初の event になるのが
          // 通常ケースで、prior (= pending) を保つと「○ (未着手) なのに
          // libx264 で再試行中と書いてある」矛盾表示になる。
          else if (p.stage === 'fallback') status = 'running';
          const fallbackNotice =
            p.stage === 'fallback'
              ? (p.message ?? `${p.fallback_from ?? 'GPU encoder'} 失敗、libx264 で再試行`)
              : prior.fallbackNotice;
          return {
            ...prev,
            [p.match_index]: {
              ...prior,
              status,
              percent: p.percent,
              error: p.stage === 'error' ? p.message : prior.error,
              fallbackNotice,
            },
          };
        });
      });
      if (disposed) {
        u();
        return;
      }
      unlisten = u;
    })();
    return () => {
      disposed = true;
      unlisten?.();
    };
  }, []);

  // Register the video source with the Tauri backend (same pattern as PreviewScreen:266-293)
  useEffect(() => {
    if (!videoSource) return;
    let cancelled = false;
    (async () => {
      try {
        const reg = await invoke<{ url: string; token: string }>('register_video', {
          path: videoSource,
        });
        if (!cancelled) setVideoUrl(reg.url);
      } catch {
        if (!cancelled) setVideoUrl(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [videoSource]);

  // Seek to the midpoint of the selected match whenever it or the URL changes
  useEffect(() => {
    const v = videoRef.current;
    const m = eligible.find((x) => x.index === frameMatchIndex);
    if (v && m) {
      const start = m.edited?.start_time ?? m.start_time;
      const end = m.edited?.end_time ?? m.end_time;
      const mid = (start + end) / 2;
      try {
        v.currentTime = mid;
      } catch {
        // jsdom video has no real currentTime — ignore in tests
      }
    }
  }, [frameMatchIndex, videoUrl, eligible]);

  /** Get frame dimensions from the video element intrinsic size (0 until loaded). */
  const getFrameDims = (): { frameW: number; frameH: number } => {
    const v = videoRef.current;
    if (v && v.videoWidth > 0 && v.videoHeight > 0) {
      return { frameW: v.videoWidth, frameH: v.videoHeight };
    }
    return { frameW: 0, frameH: 0 };
  };

  const onOverlayMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    e.preventDefault();
    const overlayRect = e.currentTarget.getBoundingClientRect();
    const start = { x: e.clientX, y: e.clientY };
    setDragStart(start);
    setDragCur(start);
    setDragRect({
      left: e.clientX - overlayRect.left,
      top: e.clientY - overlayRect.top,
      width: 0,
      height: 0,
    });
  };

  const onOverlayMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!dragStart) return;
    const overlayRect = e.currentTarget.getBoundingClientRect();
    setDragCur({ x: e.clientX, y: e.clientY });
    setDragRect({
      left: Math.min(dragStart.x, e.clientX) - overlayRect.left,
      top: Math.min(dragStart.y, e.clientY) - overlayRect.top,
      width: Math.abs(e.clientX - dragStart.x),
      height: Math.abs(e.clientY - dragStart.y),
    });
  };

  const onOverlayMouseUp = () => {
    const v = videoRef.current;
    if (!v || !dragStart || !dragCur) {
      setDragStart(null);
      setDragCur(null);
      setDragRect(null);
      return;
    }
    const rect = v.getBoundingClientRect();
    const sel = {
      x: Math.min(dragStart.x, dragCur.x) - rect.left,
      y: Math.min(dragStart.y, dragCur.y) - rect.top,
      w: Math.abs(dragCur.x - dragStart.x),
      h: Math.abs(dragCur.y - dragStart.y),
    };
    const px = elementRectToSourcePx(sel, { width: rect.width, height: rect.height }, v.videoWidth, v.videoHeight);
    const { frameW, frameH } = getFrameDims();
    setRegion(px);
    if (frameW > 0 && frameH > 0) {
      setRegionError(validateRegionPx(px, frameW, frameH));
    }
    setDragStart(null);
    setDragCur(null);
    setDragRect(null);
  };

  /** Update a single numeric field from the inputs */
  const onFieldChange = (field: keyof RegionPx, rawValue: string) => {
    const num = parseInt(rawValue, 10);
    const value = Number.isFinite(num) ? num : 0;
    const next: RegionPx = { ...(region ?? { x: 0, y: 0, w: 0, h: 0 }), [field]: value };
    setRegion(next);
    const { frameW, frameH } = getFrameDims();
    if (frameW > 0 && frameH > 0) {
      setRegionError(validateRegionPx(next, frameW, frameH));
    } else {
      // No frame dims yet — only validate what we can
      setRegionError(validateRegionPx(next, Infinity, Infinity));
    }
  };

  // ── Auto-detect ───────────────────────────────────────────────────────────

  async function handleAutoDetect() {
    if (!filePath) return;
    setDetecting(true);
    setDetectNotice(null);
    try {
      const proposals = await invoke<Array<{
        matchIndex: number;
        region: RegionPx | null;
        confidence: number;
        scattered: boolean;
      }>>('detect_minimap_regions', {
        req: {
          metadataPath: filePath,
          // Use real excluded set (wired in Task 11)
          excludedIndexes: Array.from(excluded),
        },
      });
      const withRegion = proposals.filter((p) => p.region !== null);
      const current = withRegion.find((p) => p.matchIndex === frameMatchIndex);
      const best = current ?? [...withRegion].sort((a, b) => b.confidence - a.confidence)[0];
      if (best?.region) {
        setRegion(best.region);
        const v = videoRef.current;
        setRegionError(
          v && v.videoWidth > 0 && v.videoHeight > 0
            ? validateRegionPx(best.region, v.videoWidth, v.videoHeight)
            : null,
        );
        if (best.scattered) {
          setDetectNotice('警告: 試合中に領域が揺れています。手動で微調整してください。');
        }
      } else {
        setDetectNotice('自動検出できませんでした。動画を見ながら手動で範囲を指定してください。');
      }
    } catch {
      setDetectNotice('自動検出に失敗しました。手動で範囲を指定してください。');
    } finally {
      setDetecting(false);
    }
  }

  function handleCancelDetect() {
    void invoke('kill_tracked_processes').catch(() => undefined);
  }

  // ── Settings helpers ──────────────────────────────────────────────────────

  async function handlePickDir() {
    const picked = await openDialog({ directory: true, multiple: false });
    if (typeof picked === 'string') {
      setOutDir(stripExtendedPathPrefix(picked));
    }
  }

  function toggleMatchExclusion(matchIndex: number) {
    setExcluded((prev) => {
      const next = new Set(prev);
      if (next.has(matchIndex)) {
        next.delete(matchIndex);
      } else {
        next.add(matchIndex);
      }
      return next;
    });
  }

  function toggleSelectAll(selectAll: boolean) {
    if (!metadata) return;
    setExcluded((prev) => {
      const next = new Set(prev);
      for (const m of metadata.matches) {
        if (m.type_override === 'skip' || m.post_match) continue;
        if (selectAll) {
          next.delete(m.index);
        } else {
          next.add(m.index);
        }
      }
      return next;
    });
  }

  // ── Crop execution ────────────────────────────────────────────────────────

  /**
   * Main crop handler.
   *
   * #893 R2 (Codex HIGH): overwrite is an EXPLICIT intent flag.
   * Normal path = overwrite:false + real mtime (guarded).
   * Post-ConflictModal overwrite = handleStartCrop(true) → overwrite:true + omit mtime.
   * start_minimap fail-closed rejects overwrite:false + missing mtime.
   *
   * INVARIANT-CRITICAL: finally always calls reloadFromDisk(), even on
   * reject, because write-back precedes encode in the Python subprocess.
   */
  async function handleStartCrop(overwrite = false) {
    // Dirty guard: unsaved preview edits would be silently lost after
    // minimap write-back reloads metadata. Force user to apply/discard first.
    if (useMetadataStore.getState().dirty) {
      setDetectNotice('未保存の変更があります。先にプレビューで適用/破棄してください。');
      return;
    }
    if (!filePath || !region || regionError) return;

    dispatch({ type: 'START_CLICKED' });

    // Initialize per-match states
    const nextStates: Record<number, MatchState> = {};
    if (metadata) {
      for (const m of metadata.matches) {
        if (m.type_override === 'skip' || m.post_match || excluded.has(m.index)) {
          nextStates[m.index] = { status: 'skipped', percent: 0 };
        } else {
          nextStates[m.index] = { status: 'pending', percent: 0 };
        }
      }
    }
    setMatchStates(nextStates);
    const startMs = Date.now();
    setCropStartMs(startMs);
    setNowMs(startMs);

    const regionStr = `${region.x},${region.y},${region.w},${region.h}`;
    try {
      const summary = await invoke<{ success: number; failure: number; skipped: number; cancelled: boolean }>(
        'start_minimap',
        {
          req: {
            metadataPath: filePath,
            region: regionStr,
            outputDir: outDir,
            namePattern,
            excludedIndexes: Array.from(excluded),
            // #893 R2: explicit mtime CAS guard. Normal path passes the real
            // loaded mtime; overwrite path omits it (undefined = bypass).
            expectedMtimeMs: overwrite
              ? undefined
              : (useMetadataStore.getState().loadedMtimeMs ?? undefined),
            overwrite,
          },
        },
      );
      if (summary.cancelled) {
        dispatch({ type: 'CANCEL_CONFIRMED' });
      } else if (summary.success === 0 && summary.failure > 0) {
        dispatch({ type: 'EXPORT_ERROR' });
      } else {
        dispatch({ type: 'PROGRESS_COMPLETE' });
      }
    } catch (e) {
      if (isAppError(e) && e.code === 'state.mtime_conflict') {
        // Surface ConflictModal — user can choose overwrite or just close
        // (finally has already reloaded from disk).
        setShowConflict(true);
        // CONFLICT_RESOLVED: running → idle so the button re-enables and
        // the user can retry (or choose 上書き which calls handleStartCrop(true)).
        // CANCEL_CONFIRMED is a no-op in the running phase (only handled by
        // cancelling), so we use the dedicated CONFLICT_RESOLVED action.
        dispatch({ type: 'CONFLICT_RESOLVED' });
      } else {
        dispatch({ type: 'EXPORT_ERROR' });
      }
    } finally {
      // #893 Codex HIGH: reload on EVERY terminal outcome (resolve OR reject)
      // once spawned, because Python write-back precedes encode.
      await useMetadataStore.getState().reloadFromDisk();
    }
  }

  function handleCancelCrop() {
    dispatch({ type: 'CANCEL_CLICKED' });
    void invoke('kill_tracked_processes').catch(() => undefined);
  }

  async function handleOpenFolder() {
    setOpenFolderError(null);
    try {
      await invoke('open_folder_in_explorer', { path: outDir });
    } catch (e) {
      setOpenFolderError(isAppError(e) ? e.message : String(e));
    }
  }

  // ── Derived state ─────────────────────────────────────────────────────────

  const countedMatches = (metadata?.matches ?? []).filter(
    (m) => m.type_override !== 'skip' && !m.post_match && !excluded.has(m.index),
  );

  const doneCount = countedMatches.filter(
    (m) => matchStates[m.index]?.status === 'done',
  ).length;
  const errorCount = countedMatches.filter(
    (m) => matchStates[m.index]?.status === 'error',
  ).length;
  const totalPercentSum = countedMatches.reduce((acc, m) => {
    const s = matchStates[m.index];
    if (!s) return acc;
    if (s.status === 'done') return acc + 100;
    if (s.status === 'running') return acc + s.percent;
    return acc;
  }, 0);
  const overallPercent = countedMatches.length === 0
    ? 0
    : Math.round(totalPercentSum / countedMatches.length);

  const elapsedSec = cropStartMs === null ? null : Math.max(0, (nowMs - cropStartMs) / 1000);

  // #964: name-pattern プレビュー sandbox 警告。行は実際に CLI へ渡る集合
  // (countedMatches) と同一の値 (境界調整済み start / {type}) で展開する。
  const namePatternIssues = computeNamePatternIssues({
    pattern: namePattern,
    outputDir: outDir,
    sourceVideo: videoSource,
    rows: countedMatches.map((m) => ({
      index: m.index,
      type: m.type,
      startSec: m.edited?.start_time ?? m.start_time,
    })),
  });
  const totalProgressUnits = totalPercentSum / 100;
  const remainingUnits = Math.max(0, countedMatches.length - totalProgressUnits);
  const remainingSec =
    !running || elapsedSec === null || totalProgressUnits === 0
      ? null
      : (elapsedSec / totalProgressUnits) * remainingUnits;

  // Button disable condition: isSample | detecting | running | !region | regionError | 0 eligible
  const startDisabled =
    isSample || detecting || running || cancelling || !region || regionError !== null || countedMatches.length === 0;
  const startReason = isSample
    ? sampleReason
    : detecting
      ? '自動検出中です'
      : !region
        ? '領域を指定してください'
        : regionError
          ? `領域エラー: ${regionError}`
          : countedMatches.length === 0
            ? '切り抜き対象が 0 件です'
            : running
              ? '切り抜き中です'
              : cancelling
                ? '中断処理中です'
                : '';

  const r = region ?? { x: 0, y: 0, w: 0, h: 0 };

  return (
    <div className={styles.screen} data-testid="minimap-screen" data-phase={phase}>
      <SampleModeBanner />

      {/* ── ConflictModal (minimap-local) ────────────────────────────────── */}
      {showConflict && (
        <div
          data-testid="conflict-modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="ae-minimap-conflict-title"
          className={styles.conflictBackdrop}
        >
          <div ref={conflictPanelRef} className={styles.conflictPanel}>
            <h2 id="ae-minimap-conflict-title" className={styles.conflictTitle}>metadata.json が外部で変更されました</h2>
            <p className={styles.conflictMessage}>
              切り抜き開始後に metadata.json が変更されました。上書きして続行しますか？
            </p>
            <div className={styles.conflictActions}>
              <button
                type="button"
                className={styles.conflictButton}
                onClick={() => {
                  setShowConflict(false);
                  void handleStartCrop(true);
                }}
              >
                上書きして再実行
              </button>
              <button
                type="button"
                className={styles.conflictButton}
                onClick={() => setShowConflict(false)}
              >
                閉じる（既にリロード済み）
              </button>
            </div>
          </div>
        </div>
      )}

      {/* #944 §D: 他 5 画面は冒頭に画面名を出すが、本画面だけ無かったため
          [⬦ ミニマップ切抜き] を押したユーザーが何をする画面か知れなかった。
          入力ファイル path の表示 (他 5 画面にはある) も同時に追加する。 */}
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
                  data-testid="minimap-path"
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
          <div className={styles.caption}>ミニマップ切抜き</div>
          <div className={styles.title}>エリアマップの領域を切り出す</div>
          <div className={styles.purpose}>
            試合映像からエリアマップ（ミニマップ）部分だけを切り抜き、H.264
            で保存します。領域は自動検出するか、映像上をドラッグして指定できます。
          </div>
        </div>
      </div>

      <div className={styles.videoPane}>
        {videoUrl ? (
          <div className={styles.videoWrapper}>
            <video
              ref={videoRef}
              src={videoUrl}
              data-testid="minimap-video"
              preload="metadata"
              playsInline
            />
            {/* Drag-select overlay */}
            <div
              className={styles.dragOverlay}
              onMouseDown={onOverlayMouseDown}
              onMouseMove={onOverlayMouseMove}
              onMouseUp={onOverlayMouseUp}
              onMouseLeave={onOverlayMouseUp}
              aria-hidden="true"
            >
              {dragRect && (
                <div
                  className={styles.dragRect}
                  style={{
                    left: dragRect.left,
                    top: dragRect.top,
                    width: dragRect.width,
                    height: dragRect.height,
                  }}
                />
              )}
            </div>
          </div>
        ) : (
          <div className={styles.loading}>loading video…</div>
        )}
      </div>

      <select
        aria-label="frame match"
        value={frameMatchIndex ?? ''}
        onChange={(e) => setFrameMatchIndex(Number(e.target.value))}
      >
        {eligible.map((m) => (
          <option key={m.index} value={m.index}>
            {`match ${String(m.index).padStart(3, '0')}`}
          </option>
        ))}
      </select>

      {/* Numeric region inputs */}
      <div className={styles.regionInputs}>
        <label className={styles.regionField}>
          <span>X</span>
          <input
            type="number"
            aria-label="region x"
            value={r.x}
            min={0}
            step={1}
            onChange={(e) => onFieldChange('x', e.target.value)}
          />
        </label>
        <label className={styles.regionField}>
          <span>Y</span>
          <input
            type="number"
            aria-label="region y"
            value={r.y}
            min={0}
            step={1}
            onChange={(e) => onFieldChange('y', e.target.value)}
          />
        </label>
        <label className={styles.regionField}>
          <span>W</span>
          <input
            type="number"
            aria-label="region width"
            value={r.w}
            min={0}
            step={1}
            onChange={(e) => onFieldChange('w', e.target.value)}
          />
        </label>
        <label className={styles.regionField}>
          <span>H</span>
          <input
            type="number"
            aria-label="region height"
            value={r.h}
            min={0}
            step={1}
            onChange={(e) => onFieldChange('h', e.target.value)}
          />
        </label>
      </div>
      {regionError && (
        <div className={styles.regionError} role="alert">
          {regionError}
        </div>
      )}

      {/* Auto-detect controls */}
      <div className={styles.autoDetectRow}>
        <button
          type="button"
          onClick={() => void handleAutoDetect()}
          disabled={detecting || isSample || phase === 'running' || phase === 'cancelling'}
        >
          自動検出を試す
        </button>
        {detecting && (
          <>
            <button type="button" onClick={handleCancelDetect}>
              中止
            </button>
            <span className={styles.detectingText}>自動検出中…</span>
          </>
        )}
      </div>
      {detectNotice && (
        <div className={styles.detectNotice} role="status">
          {detectNotice}
        </div>
      )}

      {/* ── Settings ────────────────────────────────────────────────────── */}
      <div className={styles.settingsSection}>
        <div className={styles.settingsCaption}>切り抜き設定</div>

        <div>
          <div className={styles.settingsLabel}>出力先</div>
          <div className={styles.outDirRow}>
            <DisabledTooltip disabled={isSample} reason={sampleReason} inlineHint>
              {(p) => (
                <input
                  className={styles.outDirInput}
                  value={outDir}
                  onChange={(e) => setOutDir(e.target.value)}
                  aria-label="output directory"
                  disabled={isSample || running || cancelling}
                  {...p}
                />
              )}
            </DisabledTooltip>
            <DisabledTooltip
              disabled={running || cancelling}
              reason="切り抜き中は出力先を変更できません"
            >
              {(p) => (
                <button
                  type="button"
                  className={styles.pickButton}
                  onClick={handlePickDir}
                  disabled={running || cancelling}
                  {...p}
                >
                  参照…
                </button>
              )}
            </DisabledTooltip>
          </div>
        </div>

        <div>
          <div className={styles.settingsLabel}>命名規則</div>
          <DisabledTooltip disabled={isSample} reason={sampleReason} inlineHint>
            {(p) => (
              <input
                className={styles.nameInput}
                value={namePattern}
                onChange={(e) => setNamePattern(e.target.value)}
                aria-label="name pattern"
                disabled={isSample || running || cancelling}
                {...p}
              />
            )}
          </DisabledTooltip>
          <div className={styles.nameHint}>
            {/* #932: `{date}` は cli-spec.md §minimap でも ExportScreen でも
                サポート済トークンだが、この hint だけ取りこぼしていた */}
            変数: {'{idx}'} {'{idx:03}'} {'{start}'} {'{type}'} {'{date}'}
          </div>
          {/* #964: CLI が exit 5 で拒否する名前をプレビュー時点で警告する
              (pool.py 層 1 の mirror)。切り抜きはブロックしない。 */}
          <NamePatternWarnings issues={namePatternIssues} />
        </div>
      </div>

      {/* ── Execute + progress ───────────────────────────────────────────── */}
      <div className={styles.executeSection}>
        {error && (
          <div className={styles.errorMessage} role="alert">
            切り抜きが失敗しました
          </div>
        )}

        {(running || completed || cancelling) && (
          <div className={styles.progressBox}>
            <div className={styles.progressHeader}>
              <span className={styles.progressLabel}>
                {running ? '切り抜き中' : cancelling ? '中断中…' : '完了'}
              </span>
              <span>
                {doneCount} / {countedMatches.length} files
                {errorCount > 0 && (
                  <span style={{ marginLeft: 8, color: 'var(--ae-danger)' }}>
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
            {elapsedSec !== null && (
              <div className={styles.progressTime}>
                <span>経過 {fmtTime(elapsedSec)}</span>
                <span>残り {remainingSec !== null ? fmtTime(remainingSec) : '—'}</span>
              </div>
            )}
          </div>
        )}

        {!completed && !error && (
          <DisabledTooltip disabled={startDisabled} reason={startReason} inlineHint>
            {(p) => (
              <button
                type="button"
                className={styles.primaryButton}
                onClick={() => { void handleStartCrop(); }}
                disabled={startDisabled}
                aria-label="切抜き開始"
                {...p}
              >
                {running ? '切り抜き中…' : cancelling ? '中断中…' : '⬦ 切抜き開始'}
              </button>
            )}
          </DisabledTooltip>
        )}

        {running && (
          <button
            type="button"
            className={styles.cancelButton}
            onClick={handleCancelCrop}
          >
            中断
          </button>
        )}

        {completed && (
          <button
            type="button"
            className={styles.primaryButton}
            onClick={() => { void handleOpenFolder(); }}
          >
            ✓ 完了 — フォルダを開く
          </button>
        )}

        {openFolderError && (
          <div className={styles.errorMessage} role="alert">
            {openFolderError}
          </div>
        )}

        {completed && (
          <button
            type="button"
            className={styles.cancelButton}
            onClick={() => {
              setMatchStates({});
              setOpenFolderError(null);
              dispatch({ type: 'RESTART' });
            }}
          >
            再切り抜き
          </button>
        )}

        {error && (
          <button
            type="button"
            className={styles.primaryButton}
            onClick={() => {
              setMatchStates({});
              dispatch({ type: 'RESTART' });
            }}
          >
            再試行
          </button>
        )}
      </div>

      {/* ── Per-match list ───────────────────────────────────────────────── */}
      {metadata && (
        <div className={styles.listSection}>
          <div className={styles.listHeaderRow}>
            <div className={styles.listCaption}>
              切り抜き一覧 ⸱ {countedMatches.length} ファイル
            </div>
            <div className={styles.listBulkActions}>
              {(() => {
                const eligibleCount = metadata.matches.filter(
                  (mm) => mm.type_override !== 'skip' && !mm.post_match,
                ).length;
                const bulkDisabled = isSample || running || cancelling || eligibleCount === 0;
                const bulkReason = isSample
                  ? sampleReason
                  : running || cancelling
                    ? '切り抜き中は変更できません'
                    : '';
                return (
                  <>
                    <DisabledTooltip disabled={bulkDisabled} reason={bulkReason}>
                      {(p) => (
                        <button
                          type="button"
                          className={styles.listBulkButton}
                          disabled={bulkDisabled}
                          onClick={() => toggleSelectAll(true)}
                          aria-label="select all matches"
                          {...p}
                        >
                          全選択
                        </button>
                      )}
                    </DisabledTooltip>
                    <DisabledTooltip disabled={bulkDisabled} reason={bulkReason}>
                      {(p) => (
                        <button
                          type="button"
                          className={styles.listBulkButton}
                          disabled={bulkDisabled}
                          onClick={() => toggleSelectAll(false)}
                          aria-label="deselect all matches"
                          {...p}
                        >
                          全解除
                        </button>
                      )}
                    </DisabledTooltip>
                  </>
                );
              })()}
            </div>
          </div>
          <ul className={styles.listBody}>
            {metadata.matches.map((m) => {
              const s = matchStates[m.index] ?? { status: 'pending' as MatchStatus, percent: 0 };
              const effectiveStart = m.edited?.start_time ?? m.start_time;
              const effectiveEnd = m.edited?.end_time ?? m.end_time;
              const durationDisplay = m.edited
                ? fmtMatchDuration(effectiveEnd - effectiveStart)
                : m.duration_display;
              // #932: CLI (`minimap.py` の `--name-pattern`) が実際に書く名前と
              // 一致させる。旧実装は `match_NNN_minimap.mp4` を決め打ちしており、
              // 命名規則を変えても一覧が追従せず実ファイル名とも食い違っていた。
              const name = formatMatchFilename(
                namePattern,
                m.index,
                m.type,
                effectiveStart,
              );
              const isPostMatch = m.post_match === true;
              const mark = isPostMatch
                ? '—'
                : s.status === 'done'
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
              const isPersistSkip = m.type_override === 'skip';
              const isAdHocExcluded = excluded.has(m.index);
              const isIncluded = !isPersistSkip && !isPostMatch && !isAdHocExcluded;
              return (
                <li
                  key={m.index}
                  className={`${styles.listItem}${isPostMatch ? ` ${styles.listItemPostMatch}` : ''}`}
                  data-testid={`minimap-row-${m.index}`}
                  {...(isPostMatch ? { 'data-post-match': 'true' } : {})}
                >
                  <DisabledTooltip
                    disabled={isSample || isPersistSkip || isPostMatch}
                    reason={
                      isSample
                        ? sampleReason
                        : isPostMatch
                          ? '試合後の映像のため切り抜き対象外です'
                          : 'preview で skip に設定されています'
                    }
                  >
                    {(p) => (
                      <input
                        type="checkbox"
                        className={styles.listCheckbox}
                        checked={isIncluded}
                        disabled={
                          isSample || isPersistSkip || isPostMatch || running || cancelling
                        }
                        onChange={() => toggleMatchExclusion(m.index)}
                        aria-label={`include match ${m.index}`}
                        title={p.title ?? '切り抜き対象から除外/復帰'}
                      />
                    )}
                  </DisabledTooltip>
                  <span className={`${styles.listMark} ${markClass}`}>{mark}</span>
                  <span className={styles.listName}>{name}</span>
                  {isPostMatch && (
                    <span className={styles.postMatchBadge}>試合後</span>
                  )}
                  <span className={styles.listDur}>{durationDisplay}</span>
                  {(running || completed || s.status === 'done' || s.status === 'error') && (
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
                  {/* #932: ExportScreen から mirror した `--ae-accent` は
                      tokens.css に存在しない token だった (IACVT で宣言ごと
                      `unset` → class の赤も失われる)。ExportScreen 側も同時修正。 */}
                  {s.fallbackNotice && (
                    <span
                      className={styles.listError}
                      role="status"
                      data-testid={`minimap-fallback-notice-${m.index}`}
                      style={{ color: 'var(--ae-gold-bright)' }}
                    >
                      {s.fallbackNotice}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
