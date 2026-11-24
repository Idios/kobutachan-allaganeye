/**
 * ClipRangeView -- クリップ範囲の調整画面 (#1139 / #1156)。
 *
 * #1139 の指摘: クリップ範囲を詰めるために preview を開いても、画面は**試合境界**
 * のエディタのままで、初期値も試合の開始 / 終了だった。どの状態の画面か読めない。
 * #1156 の指摘: IN / OUT の区別が色だけ・nudge のラベルが同一・自動範囲との差が
 * 見えない・保存すると何が起きるか分からない。
 *
 * 設計は
 * `docs/superpowers/specs/2026-11-24-clip-range-editor-ux-design.md` が正:
 *
 * - 画面を「1 映像と操作対象 / 2 秒数の調整 / 3 結果」に分ける
 * - nudge は行見出しで端を束縛する（操作対象の選択は不要）
 * - 試合境界の編集バッファ (`startT` / `endT`) には一切触らない
 * - 「自動範囲」(= 手動上書きを消したときの実効区間、束ね + クランプ込み) を
 *   常時表示し、差分と [自動範囲に戻す] を同じ場所に置く
 * - 編集値も対象試合の区間へ clamp する (CLI の明示区間クランプと一致させる)
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import pathStyles from '../styles/path-display.module.css';

import { DisabledTooltip } from '../components/DisabledTooltip';
import { KeyboardHints } from '../components/KeyboardHints';
import { SampleModeBanner } from '../components/SampleModeBanner';
import { TimecodePane } from '../components/TimecodePane';
import { useRegisteredVideo } from '../hooks/useRegisteredVideo';
import { useAppStateStore } from '../state/appStateStore';
import { useMetadataStore } from '../state/metadataStore';
import { DEFAULT_FPS } from '../types/metadata.schema';
import { splitPath } from '../utils/path';
import { signalLabel } from '../utils/signals';
import { fmtClockTenths, fmtPreciseTime } from '../utils/time';
import styles from './ClipRangeView.module.css';

/** 境界の同値判定 (秒)。baseline との比較と `changed` で共通に使う。 */
const EPS = 0.005;

/** 浮動小数の累積誤差を保存値に残さない (0.1 秒ステップを 3 回押した等)。 */
function roundSeconds(value: number): number {
  return Math.round(value * 1e4) / 1e4;
}

/** `+1.2` / `−0.8` 形式 (差の符号規約: 自動範囲に対する増減)。 */
function fmtDelta(value: number): string {
  const rounded = Math.abs(value) < 0.05 ? 0 : value;
  return `${rounded < 0 ? '−' : '+'}${Math.abs(rounded).toFixed(1)}`;
}

const NUDGE_STEPS = [-10, -1, -0.1, 0.1, 1, 10] as const;

function stepLabel(value: number): string {
  return `${value > 0 ? '+' : '−'}${Math.abs(value)}s`;
}

interface NudgeRowProps {
  edge: 'start' | 'end';
  label: string;
  disabled: boolean;
  disabledReason: string;
  onNudge: (edge: 'start' | 'end', delta: number) => void;
}

/**
 * 端ごとの nudge 行。**行見出しで端を束縛する**ので、ボタン自体は短いラベルの
 * ままでよい (可視名と aria-label は `clip in +1s` / `clip out +1s`)。
 */
function NudgeRow({
  edge,
  label,
  disabled,
  disabledReason,
  onNudge,
}: NudgeRowProps) {
  return (
    <div className={styles.nudgeRow} data-testid={`clip-range-nudge-${edge}`}>
      <span className={styles.nudgeLabel}>{label}</span>
      <div className={styles.nudgeButtons}>
        {NUDGE_STEPS.map((delta) => (
          <DisabledTooltip
            key={delta}
            disabled={disabled}
            reason={disabledReason}
          >
            {(p) => (
              <button
                type="button"
                className={styles.stepButton}
                onClick={() => onNudge(edge, delta)}
                aria-label={`clip ${edge === 'start' ? 'in' : 'out'} ${stepLabel(delta)}`}
                disabled={disabled}
                {...p}
              >
                {stepLabel(delta)}
              </button>
            )}
          </DisabledTooltip>
        ))}
      </div>
    </div>
  );
}

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
  // sample mode = ファイルに書けない in-memory 状態 (#633 / docs/ui-interaction-spec.md §1.4)
  const isSample = useMetadataStore(
    (s) => s.filePath === null && s.metadata !== null,
  );

  const position = clipRange?.position ?? null;
  const event = useMemo(() => {
    if (position === null) return null;
    return metadata?.events?.[position - 1] ?? null;
  }, [metadata, position]);
  const match = useMemo(() => {
    const index = event?.match_index;
    if (index === null || index === undefined) return null;
    return metadata?.matches.find((m) => m.index === index) ?? null;
  }, [metadata, event]);

  const baseline = clipRange?.baseline ?? null;

  // 画面を開いた時点の clipRange を初期値にする。以降はこの画面の local state が
  // 正で、[保存] したときだけ metadata に書き戻す（試合境界の編集とは独立）。
  const [startT, setStartT] = useState(clipRange?.start ?? 0);
  const [endT, setEndT] = useState(clipRange?.end ?? 0);
  const [editing, setEditing] = useState<'start' | 'end'>('start');
  const [savedNotice, setSavedNotice] = useState<'saved' | 'removed' | null>(
    null,
  );

  // `[この範囲を保存]` は metadata 全体を書く (metadataStore.runApply)。入場時点で
  // 他の未保存編集があるときだけ、その旨を注記する (#1156)。
  const [otherEditsAtMount] = useState(
    () => useMetadataStore.getState().dirty,
  );

  const videoSource = useMetadataStore((s) => s.metadata?.source ?? null);
  const selectedVideoPath = useAppStateStore((s) => s.selectedVideoPath);
  const source = selectedVideoPath ?? videoSource;
  const fps =
    metadata?.source_fps && metadata.source_fps > 0
      ? metadata.source_fps
      : DEFAULT_FPS;

  // #1139: `register_video` の登録は `useRegisteredVideo` に集約
  // (PreviewScreen / MinimapScreen と共通)。
  const { videoUrl, videoError } = useRegisteredVideo(source);

  const inVideoRef = useRef<HTMLVideoElement | null>(null);
  const outVideoRef = useRef<HTMLVideoElement | null>(null);

  // IN / OUT の編集値をペインの再生位置に反映する（再生中は触らない）。
  // #1156: 初期表示もここで揃う (IN = クリップ IN)。イベントの瞬間は別行で示す。
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
  // 保存できないだけでなく、時間の編集も閉じる。**再生は許可**する (値を変える
  // 経路が無いため。#1156 の状態表)。
  const editable = position !== null && !isSample;
  const editDisabledReason = isSample
    ? 'サンプル動画では保存できません'
    : !editable
      ? 'metadata に保存されていないイベントは編集できません'
      : '';

  // 編集値を対象試合の区間へ clamp する。CLI は手動区間も試合区間に clamp し、
  // 潰れたらクリップごと捨てる (`allaganeye/export/clips.py`) ので、ここで揃えないと
  // 「画面の数字」と「出力される区間」が食い違う (#1156)。
  const lowerBound = Math.max(0, match?.start_time ?? 0);
  const upperBound =
    match?.end_time !== undefined && Number.isFinite(match.end_time)
      ? match.end_time
      : Number.POSITIVE_INFINITY;

  // 非有限値 (極端に長い時間フィールド等) は**入力ごと捨てる**。既存の
  // `parseTimecode` 失敗時と同じ扱いで、直前の有効値を保つ。
  const applyStart = useCallback(
    (next: number) => {
      if (!editable || !Number.isFinite(next)) return;
      const hi = Math.min(endT - 0.01, upperBound);
      if (hi < lowerBound) return;
      setStartT(roundSeconds(Math.min(Math.max(next, lowerBound), hi)));
      setSavedNotice(null);
    },
    [editable, endT, lowerBound, upperBound],
  );
  const applyEnd = useCallback(
    (next: number) => {
      if (!editable || !Number.isFinite(next)) return;
      const lo = Math.max(startT + 0.01, lowerBound);
      if (lo > upperBound) return;
      setEndT(roundSeconds(Math.max(Math.min(next, upperBound), lo)));
      setSavedNotice(null);
    },
    [editable, startT, lowerBound, upperBound],
  );

  const nudge = useCallback(
    (edge: 'start' | 'end', delta: number) => {
      if (edge === 'start') applyStart(startT + delta);
      else applyEnd(endT + delta);
    },
    [applyStart, applyEnd, startT, endT],
  );

  // 境界エディタと同じキーボードショートカット。
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
    (Math.abs(startT - clipRange.start) > EPS ||
      Math.abs(endT - clipRange.end) > EPS);
  const isAtBaseline =
    baseline !== null &&
    Math.abs(startT - baseline.start) <= EPS &&
    Math.abs(endT - baseline.end) <= EPS;
  const canSave =
    editable &&
    filePath !== null &&
    !applying &&
    Number.isFinite(startT) &&
    Number.isFinite(endT) &&
    endT - startT >= 0.01;
  const canReset = editable && baseline !== null && !isAtBaseline;
  const resetReason = isSample
    ? 'サンプル動画では保存できません'
    : !editable
      ? 'metadata に保存されていないイベントは編集できません'
      : baseline === null
        ? '自動範囲を計算できません'
        : 'すでに自動範囲です';

  function handleReset(): void {
    if (!canReset) return;
    setStartT(baseline!.start);
    setEndT(baseline!.end);
    setSavedNotice(null);
  }

  async function handleSave(): Promise<void> {
    if (clipRange === null || position === null) return;
    if (!Number.isFinite(startT) || !Number.isFinite(endT)) return;
    setSavedNotice(null);
    // 自動範囲と同じ値なら上書きを残さない (一覧に無意味な「手動」バッジを残さない)。
    setEventClipRange(
      position,
      isAtBaseline ? null : { start: startT, end: endT },
    );
    await apply();
    // `apply()` は失敗を catch して state に入れ、**例外を投げずに resolve する**
    // (`metadataStore.runApply`)。成否は store の状態で判定する。
    const state = useMetadataStore.getState();
    if (state.applyErrorState !== null || state.conflictErrorState !== null) {
      return;
    }
    // codex review 2026-11-24 (P2): 保存の完了を待つ間にユーザーが別のイベント /
    // 一覧へ移ることがある。その状態で古い選択を書き戻すと、表示中のイベントと
    // 保存先 (`position`) がずれるので、選択が変わっていないときだけ更新する。
    const current = useAppStateStore.getState().clipRange;
    if (
      current === null ||
      current.position !== position ||
      current.matchIndex !== clipRange.matchIndex
    ) {
      return;
    }
    // `baseline` を保持したまま新しい区間を積む。ここで組み立て直すと
    // 結果ブロックが消える (#1156 レビュー指摘 2)。
    setClipRange({ ...current, start: startT, end: endT });
    setSavedNotice(isAtBaseline ? 'removed' : 'saved');
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
  const duration = Math.max(0, endT - startT);
  const baselineDuration =
    baseline === null ? null : Math.max(0, baseline.end - baseline.start);

  return (
    <div className={styles.screen} data-testid="clip-range-view">
      <SampleModeBanner />
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
            この画面は「この 1 本のクリップ」の開始 / 終了を決める画面です。試合の境界は変わりません。
            決めた範囲は metadata.json に保存され、
            <code> allaganeye clips </code>
            がその範囲で切り抜きます。
          </div>
        </div>
      </div>

      {position === null && (
        <div className={styles.note} role="status" data-testid="clip-range-unlinked">
          このイベントは metadata.json に保存されていないため、範囲を保存できません。
          先に KO / ASSIST 検出を [適用] してください。
        </div>
      )}

      <div className={styles.sectionCaption}>1  映像と操作対象 ⸱ VIEW</div>
      <div className={styles.panes}>
        <TimecodePane
          label="IN ⸱ 開始"
          active={editing === 'start'}
          t={startT}
          onActivate={() => setEditing('start')}
          onTChange={applyStart}
          videoUrl={videoUrl}
          videoError={videoError}
          videoRef={inVideoRef}
          fps={fps}
          disabled={!editable}
          disabledReason={editDisabledReason}
        />
        <TimecodePane
          label="OUT ⸱ 終了"
          active={editing === 'end'}
          t={endT}
          onActivate={() => setEditing('end')}
          onTChange={applyEnd}
          videoUrl={videoUrl}
          videoError={videoError}
          videoRef={outVideoRef}
          fps={fps}
          disabled={!editable}
          disabledReason={editDisabledReason}
        />
      </div>

      <div className={styles.activeLine} data-testid="clip-range-active-edge">
        ● 操作対象: {editing === 'start' ? 'IN (開始)' : 'OUT (終了)'}
        {'  '}←→ キーはこの端を動かします（ペインをクリックで切り替え）
      </div>
      {event && (
        <div className={styles.eventLine} data-testid="clip-range-event-time">
          イベント発生 {fmtPreciseTime(event.timestamp, fps)}
        </div>
      )}

      <div className={styles.sectionCaption}>2  秒数の調整 ⸱ ADJUST</div>
      <div className={styles.sectionHint}>
        各ボタンは、その行の端だけを直接動かします（操作対象の選択は不要）。
      </div>
      <div className={styles.nudgeRows}>
        <NudgeRow
          edge="start"
          label="IN (開始)"
          disabled={!editable}
          disabledReason={editDisabledReason}
          onNudge={nudge}
        />
        <NudgeRow
          edge="end"
          label="OUT (終了)"
          disabled={!editable}
          disabledReason={editDisabledReason}
          onNudge={nudge}
        />
      </div>

      {/* キーボードショートカットの可視化 (境界エディタと共通部品、#1139) */}
      <KeyboardHints />
      <div className={styles.unitNote}>
        ※ 上の TC は H:MM:SS.FF（FF = フレーム番号）。結果は 0.1 秒刻みで表示。
      </div>
      <div className={styles.unitNote}>
        ※ 無劣化 (copy) で切り抜くときは最寄りのキーフレームに丸まります（形式は一覧で選択）。
      </div>

      <div className={styles.sectionCaption}>3  結果 ⸱ RESULT</div>
      <div className={styles.results}>
        <div className={styles.resultRow} data-testid="clip-range-duration">
          <span className={styles.resultLabel}>クリップ</span>
          <span className={styles.resultValue}>{duration.toFixed(1)} 秒</span>
          <span className={styles.resultRange}>
            {fmtClockTenths(startT)} → {fmtClockTenths(endT)}
          </span>
          {manual && (
            <span className={styles.tag} data-testid="clip-range-manual">
              手動指定
            </span>
          )}
        </div>

        {baseline !== null && baselineDuration !== null && (
          <div className={styles.resultRow} data-testid="clip-range-baseline">
            <span className={styles.resultLabel}>自動範囲</span>
            <span className={styles.resultValue}>
              {baselineDuration.toFixed(1)} 秒
            </span>
            <span className={styles.resultRange}>
              {fmtClockTenths(baseline.start)} → {fmtClockTenths(baseline.end)}
            </span>
            {isAtBaseline && (
              <span className={styles.tagMuted}>自動範囲のまま</span>
            )}
          </div>
        )}

        {baseline !== null && baseline.bundled > 1 && (
          <div className={styles.resultNote} data-testid="clip-range-bundled">
            近接 {baseline.bundled} 件の共通範囲。手動で保存するとこのイベントは分離されます。
          </div>
        )}

        {baseline !== null && baselineDuration !== null && !isAtBaseline && (
          <div className={styles.resultRow} data-testid="clip-range-diff">
            <span className={styles.resultLabel}>差</span>
            <span className={styles.resultValue}>
              長さ {fmtDelta(duration - baselineDuration)} 秒
            </span>
            <span className={styles.resultRange}>
              （開始 {fmtDelta(startT - baseline.start)} 秒 ／ 終了{' '}
              {fmtDelta(endT - baseline.end)} 秒）
            </span>
          </div>
        )}

        <div className={styles.resultActions}>
          <DisabledTooltip disabled={!canReset} reason={resetReason}>
            {(p) => (
              <button
                type="button"
                className={styles.secondaryButton}
                onClick={handleReset}
                disabled={!canReset}
                {...p}
              >
                自動範囲に戻す
              </button>
            )}
          </DisabledTooltip>
        </div>
      </div>

      <div className={styles.saveNote} data-testid="clip-range-save-note">
        このイベントの clip_start / clip_end を metadata.json に保存します。
        動画の切り抜きは [クリップ一覧] の [切り抜く] から実行します。
        {otherEditsAtMount && (
          <span className={styles.saveNoteWarn}>
            {' '}
            他の未保存の変更も一緒に保存されます。
          </span>
        )}
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
        {savedNotice !== null && (
          <span className={styles.saved} data-testid="clip-range-saved">
            {savedNotice === 'removed'
              ? '自動範囲と同じため、手動上書きを削除しました'
              : 'metadata.json にクリップ範囲を保存しました'}
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
