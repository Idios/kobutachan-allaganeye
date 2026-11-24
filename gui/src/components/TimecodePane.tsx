/*
 * TimecodePane -- IN / OUT の動画ペイン + タイムコード入力 (#465 review)。
 *
 * 元は PreviewScreen 内のローカル component だったが、#1139 で
 * 「クリップ範囲の調整」画面からも同じ部品を使うため common component へ移した。
 * 状態は持たない (t / onTChange は呼び出し側が所有する) ので、試合境界の編集と
 * クリップ範囲の編集で **状態は完全に別**、見た目と操作だけを共有する。
 */
import { DisabledTooltip } from './DisabledTooltip';
import { fmtPreciseTime } from '../utils/time';
import styles from './TimecodePane.module.css';

export interface TimecodePaneProps {
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
  /** When true, the timecode input is read-only (sample mode). */
  disabled?: boolean;
  /** Tooltip reason shown on the timecode input when disabled. */
  disabledReason?: string;
}

/**
 * Parse H:MM:SS.FF back into seconds. Returns null on malformed input.
 *
 * #465 review: fps is required so 120 / 240 fps recordings parse the `.FF`
 * portion as actual frame numbers in their respective denominator.
 */
export function parseTimecode(value: string, fps: number): number | null {
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

export function TimecodePane({
  label,
  active,
  t,
  onActivate,
  onTChange,
  videoUrl,
  videoError,
  videoRef,
  fps,
  disabled = false,
  disabledReason = '',
}: TimecodePaneProps) {
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
      <DisabledTooltip disabled={disabled} reason={disabledReason}>
        {(p) => (
          <input
            className={styles.tcInput}
            value={fmtPreciseTime(t, fps)}
            onChange={(e) => {
              const parsed = parseTimecode(e.target.value, fps);
              if (parsed !== null) onTChange(parsed);
            }}
            aria-label={`${label} timecode`}
            onClick={(e) => e.stopPropagation()}
            // #1156: 入力にフォーカスしたらそのペインを操作対象にする。
            // クリックの stopPropagation は維持する (pane button の click が
            // 二重に発火しないため)。これが無いと OUT の TC を編集した直後の
            // ←→ が IN を動かす。
            onFocus={onActivate}
            disabled={disabled}
            {...p}
          />
        )}
      </DisabledTooltip>
    </button>
  );
}
