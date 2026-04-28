import { invoke } from '@tauri-apps/api/core';
import { open } from '@tauri-apps/plugin-dialog';
import { useReducer, useRef, useState } from 'react';

import { AllaganFrame } from '../components/AllaganFrame';
import { AllaganSigil } from '../components/AllaganSigil';
import { LoadingSpinner } from '../components/LoadingSpinner';
import { useEscapeKey } from '../hooks/useEscapeKey';
import { useFocusTrap } from '../hooks/useFocusTrap';
import { useAppStateStore } from '../state/appStateStore';
import { dropReducer } from './reducers/drop';
import type { DropPhase, VideoProbeInfo } from './types';
import styles from './DropScreen.module.css';

const RECENT_DUMMY = [
  { name: '2026-04-08 21-14-05.mkv', size: '38.2 GB', dur: '2:50:28' },
  { name: '2026-04-05 20-02-11.mkv', size: '24.1 GB', dur: '1:45:12' },
  { name: '2026-03-28 19-45-33.mkv', size: '52.8 GB', dur: '3:28:40' },
];

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
}

export function DropScreen({ probeFn, openDialogFn }: DropScreenProps = {}) {
  const navigate = useAppStateStore((s) => s.navigate);
  const setSelectedVideoPath = useAppStateStore((s) => s.setSelectedVideoPath);

  const [phase, dispatch] = useReducer(dropReducer, 'idle' as DropPhase);
  const [probeInfo, setProbeInfo] = useState<VideoProbeInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

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
    try {
      const info = await (probeFn ?? probeVideo)(selected);
      setProbeInfo(info);
      dispatch({ type: 'PROBE_OK' });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      dispatch({ type: 'PROBE_FAIL' });
    }
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
            <div className={styles.dropZone}>
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
                {phase === 'selecting' && <LoadingSpinner label="選択中" />}
                {phase === 'probing' && <LoadingSpinner label="解析中" />}
              </div>
            </div>
          </AllaganFrame>

          <div className={styles.recent}>
            <div className={styles.recentHeading}>──── 直近の録画 ────</div>
            {RECENT_DUMMY.map((r) => (
              <div key={r.name} className={styles.recentItem}>
                <span className={styles.recentMark}>◈</span>
                <span className={styles.recentName}>{r.name}</span>
                <span className={styles.recentDur}>{r.dur}</span>
                <span className={styles.recentSize}>{r.size}</span>
              </div>
            ))}
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
