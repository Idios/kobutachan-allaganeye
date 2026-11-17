/**
 * ClipRangeView -- クリップ範囲の調整画面 (#1139)。
 *
 * #1139 の指摘: クリップ範囲を詰めるために preview を開いても、画面は**試合境界**
 * のエディタのままで、初期値も試合の開始 / 終了だった。どの状態の画面か読めない。
 *
 * そこで**状態を完全に分ける**: この component は
 * `appStateStore.clipRange`（イベント単位の絶対秒）だけを編集し、試合境界の
 * 編集バッファ (`startT` / `endT`) には一切触らない。動画ペインとタイムコード入力は
 * `TimecodePane`（共通部品）を流用する。
 *
 * 保存すると `metadata.events[position].clip_start` / `clip_end` が更新され
 * (`metadataStore.setEventClipRange`)、既存の `apply()` で metadata.json に書く。
 * `allaganeye clips` はこの区間で切り抜く（metadata が SSoT, #1139）。
 */
import { invoke } from '@tauri-apps/api/core';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import pathStyles from '../styles/path-display.module.css';

import { TimecodePane } from '../components/TimecodePane';
import { useAppStateStore } from '../state/appStateStore';
import { useMetadataStore } from '../state/metadataStore';
import { DEFAULT_FPS } from '../types/metadata.schema';
import { splitPath } from '../utils/path';
import { fmtClockTime } from '../utils/time';
import { signalLabel } from './IndicatorsScreen';
import styles from './ClipRangeView.module.css';

export function ClipRangeView() {
  const clipRange = useAppStateStore((s) => s.clipRange);
  const setClipRange = useAppStateStore((s) => s.setClipRange);
  const navigate = useAppStateStore((s) => s.navigate);

  const metadata = useMetadataStore((s) => s.metadata);
  const filePath = useMetadataStore((s) => s.filePath);
  const dirty = useMetadataStore((s) => s.dirty);
  const applying = useMetadataStore((s) => s.applying);
  const applyErrorState = useMetadataStore((s) => s.applyErrorState);
  const setEventClipRange = useMetadataStore((s) => s.setEventClipRange);
  const apply = useMetadataStore((s) => s.apply);

  const position = clipRange?.position ?? null;
  const event = useMemo(() => {
    if (position === null) return null;
    return metadata?.events?.[position - 1] ?? null;
  }, [metadata, position]);

  // 画面を開いた時点の clipRange を初期値にする。以降はこの画面の local state が
  // 正で、[保存] したときだけ metadata に書き戻す（試合境界の編集とは独立）。
  const [startT, setStartT] = useState(clipRange?.start ?? 0);
  const [endT, setEndT] = useState(clipRange?.end ?? 0);
  const [editing, setEditing] = useState<'start' | 'end'>('start');

  const videoSource = useMetadataStore((s) => s.metadata?.source ?? null);
  const selectedVideoPath = useAppStateStore((s) => s.selectedVideoPath);
  const source = selectedVideoPath ?? videoSource;
  const fps =
    metadata?.source_fps && metadata.source_fps > 0
      ? metadata.source_fps
      : DEFAULT_FPS;

  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [videoError, setVideoError] = useState<string | null>(null);
  useEffect(() => {
    if (!source) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await invoke<{ url: string }>('register_video', {
          path: source,
        });
        // codex review 2026-11-17 (P1): `register_video` は axum が配信する
        // **HTTP URL** を返す。`convertFileSrc(url, 'asset')` に通すと asset
        // プロトコルへ書き換えられ、ペインに動画が映らない (範囲を目視できない)。
        if (!cancelled) setVideoUrl(res.url);
      } catch (e) {
        if (!cancelled) setVideoError(String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [source]);

  const inVideoRef = useRef<HTMLVideoElement | null>(null);
  const outVideoRef = useRef<HTMLVideoElement | null>(null);

  // IN / OUT の編集値をペインの再生位置に反映する（再生中は触らない）。
  useEffect(() => {
    const v = inVideoRef.current;
    if (v && v.paused && Math.abs(v.currentTime - startT) > 0.001) {
      try {
        v.currentTime = startT;
      } catch {
        // メタデータ未ロード時は無視
      }
    }
  }, [startT, videoUrl]);

  useEffect(() => {
    const v = outVideoRef.current;
    if (v && v.paused && Math.abs(v.currentTime - endT) > 0.001) {
      try {
        v.currentTime = endT;
      } catch {
        // 同上
      }
    }
  }, [endT, videoUrl]);

  // `position === null` は metadata に保存されていないイベント (未適用の検出結果)。
  // 保存できないだけでなく、時間の編集も閉じる (codex review 2026-11-17 P2:
  // 注意書きが「編集できません」と言っているのに、動画の再生や nudge で値が
  // 動いていた)。
  const editable = position !== null;

  // 非有限値 (極端に長い時間フィールド等) は**入力ごと捨てる**。既存の
  // `parseTimecode` 失敗時と同じ扱いで、直前の有効値を保つ。
  // codex review 2026-11-17 (P2): 素通しすると `Infinity` が保存され、JSON 化で
  // `null` になった `clip_end` が metadata に書かれる。
  const applyStart = useCallback(
    (next: number) => {
      if (!editable || !Number.isFinite(next)) return;
      setStartT(Math.max(0, Math.min(next, endT - 0.01)));
    },
    [editable, endT],
  );
  const applyEnd = useCallback(
    (next: number) => {
      if (!editable || !Number.isFinite(next)) return;
      setEndT(Math.max(next, startT + 0.01));
    },
    [editable, startT],
  );

  // 一覧の行から開いた直後は、IN ペインを **イベントの発生時刻** に置く (#1139
  // 受け入れ条件: シーク位置はイベント開始)。TC はクリップの IN のまま (編集
  // バッファは動かさない) で、KO の瞬間を見せる。nudge / 入力すると以降は
  // 上の sync effect が IN の位置を反映する。
  const seekedToEventRef = useRef(false);
  useEffect(() => {
    if (seekedToEventRef.current) return;
    const v = inVideoRef.current;
    if (!v || videoUrl === null) return;
    const target = event?.timestamp;
    if (typeof target !== 'number' || !Number.isFinite(target)) return;
    try {
      v.currentTime = target;
    } catch {
      // メタデータ未ロード時の seek 失敗は無視
    }
    seekedToEventRef.current = true;
  }, [videoUrl, event]);

  const nudge = useCallback(
    (edge: 'start' | 'end', delta: number) => {
      if (edge === 'start') applyStart(startT + delta);
      else applyEnd(endT + delta);
    },
    [applyStart, applyEnd, startT, endT],
  );

  // 境界エディタと同じキーボードショートカット (Idios 指摘 2026-11-17)。
  // Space = active ペインの再生 / 停止、←→ = ±1s、Shift = ±10s、Alt = ±1 frame。
  // 矢印は **active な端**(`editing`) だけを動かし、TC 入力中は横取りしない。
  const activeVideoRef = editing === 'start' ? inVideoRef : outVideoRef;
  useEffect(() => {
    const interactiveTags = new Set(['INPUT', 'TEXTAREA', 'SELECT']);
    function handleKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      if (target && interactiveTags.has(target.tagName)) return;

      if (e.key === ' ') {
        const v = activeVideoRef.current;
        if (v) {
          if (v.paused) void v.play().catch(() => undefined);
          else v.pause();
        }
        e.preventDefault();
        return;
      }
      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
        const sign = e.key === 'ArrowLeft' ? -1 : 1;
        const step = e.altKey ? 1 / fps : e.shiftKey ? 10 : 1;
        nudge(editing, sign * step);
        e.preventDefault();
      }
    }
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [activeVideoRef, editing, fps, nudge]);

  const manual = event !== null && event.clip_start !== undefined;
  const changed =
    clipRange !== null &&
    (Math.abs(startT - clipRange.start) > 0.005 ||
      Math.abs(endT - clipRange.end) > 0.005);
  const canSave =
    editable &&
    filePath !== null &&
    !applying &&
    Number.isFinite(startT) &&
    Number.isFinite(endT) &&
    endT - startT >= 0.01;

  async function handleSave() {
    if (clipRange === null || position === null) return;
    if (!Number.isFinite(startT) || !Number.isFinite(endT)) return;
    setEventClipRange(position, { start: startT, end: endT });
    setClipRange({
      start: startT,
      end: endT,
      matchIndex: clipRange.matchIndex,
      position: clipRange.position,
    });
    await apply();
  }

  if (clipRange === null) {
    // 直接この画面に来た (dev switcher 等) 場合は preview に戻す。
    return (
      <div className={styles.screen} data-testid="clip-range-view">
        <div className={styles.note}>クリップ範囲が選択されていません。</div>
        <button
          type="button"
          className={styles.secondaryButton}
          onClick={() => navigate('clips')}
        >
          ◀ クリップ一覧へ
        </button>
      </div>
    );
  }

  const { fileName, parentDir } = splitPath(source ?? '');
  const kind = event ? (signalLabel(event.signal_id) ?? event.signal_id) : 'クリップ';

  return (
    <div className={styles.screen} data-testid="clip-range-view">
      <div className={styles.header}>
        <button
          type="button"
          className={styles.backButton}
          onClick={() => navigate('clips')}
        >
          ◀ クリップ一覧へ
        </button>
        <div>
          {source && (
            <div className={pathStyles.pathDisplay} title={source}>
              <div className={styles.headerFileName}>{fileName || '(video)'}</div>
              {parentDir && <div className={pathStyles.pathSecondary}>{parentDir}</div>}
            </div>
          )}
          <div className={styles.caption}>クリップ範囲 ⸱ CLIP RANGE</div>
          <div className={styles.title}>{kind} の切り抜き範囲</div>
          <div className={styles.purpose}>
            IN / OUT がクリップの開始 / 終了です（試合の境界ではありません）。
            前後を詰めて [この範囲を保存] すると、クリップ一覧と
            <code> allaganeye clips </code> がこの区間で切り抜きます。
          </div>
        </div>
      </div>

      {position === null && (
        <div className={styles.note} role="status" data-testid="clip-range-unlinked">
          このイベントは metadata.json に保存されていないため、範囲を保存できません。
          先に KO / ASSIST 検出を [適用] してください。
        </div>
      )}
      {manual && (
        <div className={styles.note} data-testid="clip-range-manual">
          手動指定の範囲です（プレビューで保存済み）。
        </div>
      )}

      <div className={styles.panes}>
        <TimecodePane
          label="IN (clip start)"
          active={editing === 'start'}
          t={startT}
          onActivate={() => setEditing('start')}
          onTChange={applyStart}
          videoUrl={videoUrl}
          videoError={videoError}
          videoRef={inVideoRef}
          fps={fps}
          disabled={!editable}
          disabledReason="metadata に保存されていないイベントは編集できません"
        />
        <TimecodePane
          label="OUT (clip end)"
          active={editing === 'end'}
          t={endT}
          onActivate={() => setEditing('end')}
          onTChange={applyEnd}
          videoUrl={videoUrl}
          videoError={videoError}
          videoRef={outVideoRef}
          fps={fps}
          disabled={!editable}
          disabledReason="metadata に保存されていないイベントは編集できません"
        />
      </div>

      <div className={styles.stepRow}>
        {[
          { edge: 'start', delta: -10, label: '−10s' },
          { edge: 'start', delta: -1, label: '−1s' },
          { edge: 'start', delta: 1, label: '+1s' },
          { edge: 'start', delta: 10, label: '+10s' },
        ].map((step) => (
          <button
            key={`in-${step.label}`}
            type="button"
            className={styles.stepButton}
            onClick={() => nudge(step.edge as 'start', step.delta)}
            aria-label={`clip in ${step.label}`}
            disabled={!editable}
          >
            {step.label}
          </button>
        ))}
        <span className={styles.duration} data-testid="clip-range-duration">
          {`${Math.max(0, endT - startT).toFixed(1)} 秒`}
          {` (${fmtClockTime(startT)} - ${fmtClockTime(endT)})`}
        </span>
        {[
          { delta: -10, label: '−10s' },
          { delta: -1, label: '−1s' },
          { delta: 1, label: '+1s' },
          { delta: 10, label: '+10s' },
        ].map((step) => (
          <button
            key={`out-${step.label}`}
            type="button"
            className={styles.stepButton}
            onClick={() => nudge('end', step.delta)}
            aria-label={`clip out ${step.label}`}
            disabled={!editable}
          >
            {step.label}
          </button>
        ))}
      </div>

      {/* キーボードショートカットの可視化 (境界エディタと同じ row、#1139) */}
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

      <div className={styles.actions}>
        <button
          type="button"
          className={styles.primaryButton}
          onClick={() => void handleSave()}
          disabled={!canSave}
          aria-label="この範囲を保存"
        >
          {applying ? '保存中…' : '⬦ この範囲を保存'}
        </button>
        {(changed || dirty) && (
          <span className={styles.dirty} data-testid="clip-range-dirty">
            ● 未保存の変更
          </span>
        )}
        <button
          type="button"
          className={styles.secondaryButton}
          onClick={() => navigate('clips')}
        >
          保存せず戻る
        </button>
      </div>

      {applyErrorState && (
        <div className={styles.errorMessage} role="alert">
          {applyErrorState.message}
          {applyErrorState.hint && <span className={styles.errorHint}>{applyErrorState.hint}</span>}
        </div>
      )}
    </div>
  );
}
