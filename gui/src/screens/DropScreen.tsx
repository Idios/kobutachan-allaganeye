import { invoke } from '@tauri-apps/api/core';
import type { UnlistenFn } from '@tauri-apps/api/event';
import { getCurrentWebview } from '@tauri-apps/api/webview';
import { open } from '@tauri-apps/plugin-dialog';
import { useEffect, useReducer, useRef, useState } from 'react';

import { AllaganFrame } from '../components/AllaganFrame';
import { AllaganSigil } from '../components/AllaganSigil';
import { LoadingSpinner } from '../components/LoadingSpinner';
import { useEscapeKey } from '../hooks/useEscapeKey';
import { useFocusTrap } from '../hooks/useFocusTrap';
import { useAppStateStore } from '../state/appStateStore';
import {
  type RecentEntryView,
  useRecentStore,
} from '../state/recentStore';
import { DetectionParamsPanel } from './DetectionParamsPanel';
import { dropReducer } from './reducers/drop';
import type { DropPhase, VideoProbeInfo } from './types';
import styles from './DropScreen.module.css';

/**
 * #568: drop zone の drag state。Tauri webview の `onDragDropEvent` で
 * 更新される。`over-valid` は受付可能な拡張子、`over-invalid` は非対応形式。
 */
type DragState = 'idle' | 'over-valid' | 'over-invalid';

/**
 * Tauri 2 webview onDragDropEvent の payload 型。
 * `enter` と `drop` は `paths: string[]` (絶対 path) を含む。
 */
export type TauriDragDropEvent =
  | { type: 'enter'; paths: string[]; position: { x: number; y: number } }
  | { type: 'over'; position: { x: number; y: number } }
  | { type: 'drop'; paths: string[]; position: { x: number; y: number } }
  | { type: 'leave' };

export type DragSubscriber = (
  cb: (e: TauriDragDropEvent) => void,
) => Promise<UnlistenFn>;

const ACCEPTED_EXTENSIONS = ['.mp4', '.mkv', '.avi', '.mov'] as const;

function isAcceptedVideoExtension(name: string): boolean {
  const lower = name.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

function pickFirstAcceptedPath(paths: readonly string[]): string | null {
  for (const p of paths) {
    if (isAcceptedVideoExtension(p)) return p;
  }
  return null;
}

async function defaultDragSubscriber(
  cb: (e: TauriDragDropEvent) => void,
): Promise<UnlistenFn> {
  return getCurrentWebview().onDragDropEvent((event) => {
    cb(event.payload as TauriDragDropEvent);
  });
}

/** #571: format file size as GB with one decimal (mirrors SelectedCard). */
function formatSizeGB(bytes: number): string {
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`;
}

/**
 * #571: format the persisted mtime for the recent list. We display the
 * recording date (not addedAtMs) so users recognize entries by when the
 * video was made, not when they last opened it.
 */
function formatRecentDate(mtimeMs: number): string {
  if (!Number.isFinite(mtimeMs) || mtimeMs <= 0) return '';
  const d = new Date(mtimeMs);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/**
 * #465 review (B): drop で確定した path を Rust 側 `probe_video` Tauri
 * command (ffprobe) に渡し、実 metadata を取得する。Phase 2 の
 * `dummyProbeVideo` を置換した。
 *
 * テスト時は `DropScreen({ probeFn })` で別実装を inject できるので、
 * この関数自体は本物 (Tauri 必須) を保つ。
 */
export async function probeVideo(path: string): Promise<VideoProbeInfo> {
  return await invoke<VideoProbeInfo>('probe_video', { path });
}

export interface DropScreenProps {
  /** Injection hook for tests. Defaults to {@link probeVideo} (real ffprobe via Tauri). */
  probeFn?: (path: string) => Promise<VideoProbeInfo>;
  /** Injection hook for tests. Defaults to @tauri-apps/plugin-dialog open(). */
  openDialogFn?: () => Promise<string | null>;
  /**
   * Injection hook for tests. Defaults to subscribing the Tauri webview
   * `onDragDropEvent`. Tests pass a controllable subscriber that captures
   * the callback so they can synthesize drag-drop events.
   */
  dragSubscriber?: DragSubscriber;
}

export function DropScreen({
  probeFn,
  openDialogFn,
  dragSubscriber,
}: DropScreenProps = {}) {
  const navigate = useAppStateStore((s) => s.navigate);
  const setSelectedVideoPath = useAppStateStore((s) => s.setSelectedVideoPath);

  // #571: hydrate the recent-videos history once the screen mounts. The
  // store keeps `loaded` true after the first round-trip so subsequent
  // re-mounts (e.g. cancelled selection → return to drop_idle) do not refetch.
  const recentEntries = useRecentStore((s) => s.entries);
  const recentLoaded = useRecentStore((s) => s.loaded);
  const loadRecent = useRecentStore((s) => s.load);
  const addRecent = useRecentStore((s) => s.add);

  useEffect(() => {
    if (!recentLoaded) {
      void loadRecent();
    }
  }, [recentLoaded, loadRecent]);

  const [phase, dispatch] = useReducer(dropReducer, 'idle' as DropPhase);
  const [probeInfo, setProbeInfo] = useState<VideoProbeInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragState, setDragState] = useState<DragState>('idle');
  // #571: surfaced when the user clicks a recent-list entry whose backing
  // file has been moved or deleted. Flash for ~5s then clear.
  const [missingNotice, setMissingNotice] = useState<string | null>(null);

  async function probeAndDispatch(path: string): Promise<void> {
    setError(null);
    try {
      const info = await (probeFn ?? probeVideo)(path);
      setProbeInfo(info);
      dispatch({ type: 'PROBE_OK' });
      // #571: persist *after* probe succeeds so we don't pollute history
      // with paths that turned out to be unreadable.
      void addRecent(info.path);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      dispatch({ type: 'PROBE_FAIL' });
    }
  }

  // #571: handler shared between recent-list click and keyboard activation.
  function selectRecent(item: RecentEntryView) {
    if (phase !== 'idle') return;
    if (!item.exists) {
      setMissingNotice(`ファイルが見つかりません: ${item.fileName}`);
      // The notice clears itself after 5s so it doesn't linger when the
      // user moves on. (No toast library yet — inline status line.)
      window.setTimeout(() => setMissingNotice(null), 5000);
      return;
    }
    setMissingNotice(null);
    dispatch({ type: 'RECENT_PICKED' });
    void probeAndDispatch(item.path);
  }

  async function pickAndProbe() {
    dispatch({ type: 'BROWSE_CLICKED' });
    setError(null);
    let selected: string | null;
    try {
      selected = await (openDialogFn ?? defaultOpenDialog)();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      dispatch({ type: 'PROBE_FAIL' });
      return;
    }
    if (!selected) {
      dispatch({ type: 'DIALOG_CANCELLED' });
      return;
    }
    dispatch({ type: 'FILE_PICKED' });
    await probeAndDispatch(selected);
  }

  // #568: Tauri webview onDragDropEvent を購読し、drag-over の visual
  // フィードバックと drop での probing 遷移を実装する。`dragDropEnabled`
  // が default `true` のため OS-level drop は Tauri が intercept し
  // HTML5 onDrop は実機で発火しない。HTML5 handler は jsdom テスト用
  // fallback として併設している。
  useEffect(() => {
    const subscribe = dragSubscriber ?? defaultDragSubscriber;
    let unlisten: UnlistenFn | null = null;
    let cancelled = false;
    void (async () => {
      const u = await subscribe((e) => {
        // phase が idle 以外は drag を ignore (probing 中の干渉防止 +
        // probeError card 表示中に dragState が裏で更新されないように)。
        if (phase !== 'idle') {
          if (e.type === 'leave') setDragState('idle');
          return;
        }
        switch (e.type) {
          case 'enter':
            setDragState(
              pickFirstAcceptedPath(e.paths) ? 'over-valid' : 'over-invalid',
            );
            return;
          case 'over':
            // 'over' は paths を含まないことが多い (Tauri 2 仕様)。
            // 'enter' で決めた dragState を維持する。
            return;
          case 'leave':
            setDragState('idle');
            return;
          case 'drop': {
            const path = pickFirstAcceptedPath(e.paths);
            setDragState('idle');
            if (!path) return; // invalid drop は phase 遷移しない
            dispatch({ type: 'DND_DROPPED' });
            void probeAndDispatch(path);
            return;
          }
        }
      });
      if (cancelled) u();
      else unlisten = u;
    })();
    return () => {
      cancelled = true;
      unlisten?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dragSubscriber, phase]);

  function onDragOverHTML(e: React.DragEvent) {
    e.preventDefault();
    if (phase !== 'idle') return;
    const items = Array.from(e.dataTransfer?.items ?? []);
    const valid =
      items.length > 0 &&
      items.every(
        (it) =>
          it.kind === 'file' &&
          (it.type.startsWith('video/') || it.type === ''),
      );
    setDragState(valid ? 'over-valid' : 'over-invalid');
  }

  function onDragLeaveHTML() {
    if (phase !== 'idle') return;
    setDragState('idle');
  }

  function onDropHTML(e: React.DragEvent) {
    // 実機では Tauri が intercept するためここは発火しない。jsdom 上で
    // のみ発火する経路で、path が取れないので visual のリセットだけ行う。
    e.preventDefault();
    e.stopPropagation();
    setDragState('idle');
  }

  function confirm() {
    if (!probeInfo) return;
    setSelectedVideoPath(probeInfo.path);
    navigate('detecting');
  }

  function cancelSelection() {
    setProbeInfo(null);
    dispatch({ type: 'CANCEL_SELECTION' });
  }

  function dismissError() {
    setError(null);
    dispatch({ type: 'DISMISS_ERROR' });
  }

  return (
    <div
      className={styles.screen}
      data-testid="drop-screen"
      data-phase={phase}
    >
      <svg className={styles.etching}>
        <defs>
          <pattern
            id="ae-grid-a"
            width="40"
            height="40"
            patternUnits="userSpaceOnUse"
          >
            <path d="M40 0H0V40" stroke="var(--ae-gold)" strokeWidth="0.5" fill="none" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#ae-grid-a)" />
      </svg>

      <AllaganSigil size={140} rotating={false} />

      <div className={styles.heading}>
        <div className={styles.kicker}>Allagan Eye ⸱ 観測器</div>
        <div className={styles.title}>録画を捧げよ</div>
        <div className={styles.subtitle}>MP4 · MKV · AVI · MOV を受け入れます</div>
      </div>

      {phase === 'selected' && probeInfo ? (
        <SelectedCard info={probeInfo} onConfirm={confirm} onCancel={cancelSelection} />
      ) : phase === 'probeError' ? (
        <ErrorCard error={error} onDismiss={dismissError} onRetry={pickAndProbe} />
      ) : (
        <>
          <AllaganFrame style={{ width: '78%', padding: 2, zIndex: 2 }}>
            <div
              className={[
                styles.dropZone,
                dragState === 'over-valid' ? styles.dropZoneDragOverValid : '',
                dragState === 'over-invalid'
                  ? styles.dropZoneDragOverInvalid
                  : '',
              ]
                .filter(Boolean)
                .join(' ')}
              data-testid="drop-zone"
              data-drag-state={dragState}
              onDragOver={onDragOverHTML}
              onDragLeave={onDragLeaveHTML}
              onDrop={onDropHTML}
            >
              {dragState === 'over-invalid' ? (
                <>
                  <div className={styles.dropZoneIconReject} aria-hidden>
                    ⊘
                  </div>
                  <div className={styles.dropZoneRejectMessage}>
                    非対応形式 (.mp4 / .mkv / .avi / .mov のみ)
                  </div>
                </>
              ) : (
                <>
                  <div className={styles.dropZoneLabel}>
                    ⬦ ここに録画ファイルをドロップ
                  </div>
                  <div className={styles.dropZoneHint}>
                    or{' '}
                    <button
                      type="button"
                      className={styles.browseButton}
                      disabled={phase === 'selecting' || phase === 'probing'}
                      onClick={pickAndProbe}
                    >
                      参照…
                    </button>
                    {/* #587: replace plaintext "(選択中)/(解析中)" with the
                        spinning sigil + label so progress is conveyed by
                        motion, not just static parenthesized text. */}
                    {phase === 'selecting' && <LoadingSpinner label="選択中" />}
                    {phase === 'probing' && <LoadingSpinner label="解析中" />}
                  </div>
                </>
              )}
            </div>
          </AllaganFrame>

          <div className={styles.recent} data-testid="recent-list">
            <div className={styles.recentHeading}>──── 直近の録画 ────</div>
            {recentEntries.length === 0 ? (
              <div
                className={styles.recentEmpty}
                data-testid="recent-empty"
              >
                {recentLoaded
                  ? '履歴はまだありません'
                  : '読み込み中…'}
              </div>
            ) : (
              recentEntries.map((r) => (
                <button
                  key={r.path}
                  type="button"
                  className={[
                    styles.recentItem,
                    styles.recentItemButton,
                    !r.exists ? styles.recentItemMissing : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  onClick={() => selectRecent(r)}
                  disabled={phase !== 'idle'}
                  data-testid="recent-item"
                  data-missing={!r.exists}
                  aria-label={
                    r.exists
                      ? `直近の録画 ${r.fileName}`
                      : `直近の録画 ${r.fileName} (ファイルが見つかりません)`
                  }
                >
                  <span className={styles.recentMark} aria-hidden>
                    ◈
                  </span>
                  <span className={styles.recentName}>{r.fileName}</span>
                  <span className={styles.recentDur}>
                    {formatRecentDate(r.mtimeMs)}
                  </span>
                  <span className={styles.recentSize}>
                    {formatSizeGB(r.sizeBytes)}
                  </span>
                </button>
              ))
            )}
            {missingNotice && (
              <div
                className={styles.recentMissingNotice}
                role="status"
                data-testid="recent-missing-notice"
              >
                ⚠ {missingNotice}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

async function defaultOpenDialog(): Promise<string | null> {
  const result = await open({
    multiple: false,
    filters: [
      {
        name: 'Video',
        extensions: ['mp4', 'mkv', 'avi', 'mov'],
      },
    ],
  });
  if (Array.isArray(result)) return result[0] ?? null;
  return result;
}

interface SelectedCardProps {
  info: VideoProbeInfo;
  onConfirm: () => void;
  onCancel: () => void;
}

function SelectedCard({ info, onConfirm, onCancel }: SelectedCardProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  // #587: trap Tab focus inside the card and dismiss on Escape so the
  // user can complete the confirm flow with the keyboard alone.
  useFocusTrap(cardRef, true);
  useEscapeKey(true, onCancel);
  const sizeGB = (info.sizeBytes / 1024 / 1024 / 1024).toFixed(1);
  const durH = Math.floor(info.durationSeconds / 3600);
  const durM = Math.floor((info.durationSeconds % 3600) / 60);
  const durS = Math.floor(info.durationSeconds % 60);
  const durDisplay = durH
    ? `${durH}:${String(durM).padStart(2, '0')}:${String(durS).padStart(2, '0')}`
    : `${String(durM).padStart(2, '0')}:${String(durS).padStart(2, '0')}`;
  return (
    <div ref={cardRef} className={styles.selectedCard} data-testid="drop-selected-card">
      <div className={styles.selectedHeading}>検知対象の確認</div>
      <div className={styles.selectedName}>{info.fileName}</div>
      <div className={styles.selectedMetaTable}>
        <span className={styles.selectedMetaLabel}>解像度</span>
        <span>{info.width}×{info.height}</span>
        <span className={styles.selectedMetaLabel}>fps</span>
        <span>{info.fps}</span>
        <span className={styles.selectedMetaLabel}>長さ</span>
        <span>{durDisplay}</span>
        <span className={styles.selectedMetaLabel}>サイズ</span>
        <span>{sizeGB} GB</span>
        <span className={styles.selectedMetaLabel}>コーデック</span>
        <span>{info.codec}</span>
      </div>
      <DetectionParamsPanel />
      <div className={styles.actions}>
        <button type="button" className={styles.cancelButton} onClick={onCancel}>
          キャンセル
        </button>
        <button type="button" className={styles.okButton} onClick={onConfirm}>
          OK — 検知開始
        </button>
      </div>
    </div>
  );
}

interface ErrorCardProps {
  error: string | null;
  onDismiss: () => void;
  onRetry: () => void;
}

function ErrorCard({ error, onDismiss, onRetry }: ErrorCardProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  // #587: same dialog-like behavior as SelectedCard. Escape = dismiss.
  // We keep the existing role="alert" for backward compat with tests
  // and screen-reader announcement of the error text.
  useFocusTrap(cardRef, true);
  useEscapeKey(true, onDismiss);
  return (
    <div
      ref={cardRef}
      className={styles.selectedCard}
      role="alert"
      data-testid="drop-error-card"
    >
      <div className={styles.selectedHeading}>エラー</div>
      <div className={styles.error}>{error ?? 'probe failed'}</div>
      <div className={styles.actions}>
        <button type="button" className={styles.cancelButton} onClick={onDismiss}>
          閉じる
        </button>
        <button type="button" className={styles.okButton} onClick={onRetry}>
          再試行
        </button>
      </div>
    </div>
  );
}
