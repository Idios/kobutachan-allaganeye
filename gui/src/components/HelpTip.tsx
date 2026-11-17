import { useEffect, useRef, useState, type ReactNode } from 'react';

import styles from './HelpTip.module.css';

/**
 * #1135 -- 設定項目の help 表示 (docs/ui-interaction-spec.md §1.7)。
 *
 * 値の意味・既定値・変えたときの効果が画面上のラベルだけでは分からない
 * control の隣に「?」トリガーを置き、hover / キーボード focus / click で
 * 説明を出す。
 *
 * - マウス専用にしない: focus でも開くので Tab だけで読める (§1.7)
 * - Escape で閉じ、その場で focus を外して Tab で戻れば再表示される
 * - scope policy: screen reader 専用属性は追加しない。トリガーは visible text を
 *   持たない icon-only button なので `aria-label` のみ付与する
 *   (docs/a11y-policy.md の axe button-name 例外)
 */
export interface HelpTipProps {
  /** Accessible name for the icon-only trigger (axe button-name). */
  label: string;
  /** Explanation text shown in the popover. */
  children: ReactNode;
  /** Base test id: `${testId}-trigger` / `${testId}-popover`. */
  testId?: string;
}

/** 上向きに反転するかの閾値 (px)。§1.7 の「配置」。 */
const POPOVER_FLIP_THRESHOLD_PX = 220;

/** trigger の位置から popover の向きを決める。viewport 下端の残りだけを見る。 */
function computePlacement(el: HTMLElement | null): 'below' | 'above' {
  if (el === null) return 'below';
  const rect = el.getBoundingClientRect();
  return window.innerHeight - rect.bottom < POPOVER_FLIP_THRESHOLD_PX
    ? 'above'
    : 'below';
}

export function HelpTip({ label, children, testId }: HelpTipProps) {
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [placement, setPlacement] = useState<'below' | 'above'>('below');
  const wrapperRef = useRef<HTMLSpanElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);

  // DropScreen のルートは `overflow: auto` なので、trigger が画面下端に近いと
  // 下向き固定の popover はスクロール領域に切られてしまう (z-index では
  // overflow を越えられない)。開く直前に残り高さを見て上向きに反転させる。
  function openFrom() {
    setPlacement(computePlacement(wrapperRef.current));
  }

  // Escape は hover / focus の状態も落とさないと、blur 直後に開き直る
  // (focus が残っている間は `open` が true のままになる)。
  const open = pinned || hovered || focused;

  // DropScreen の SelectedCard は document レベルの Escape で自分を閉じる
  // (useEscapeKey)。open 中の Escape は help を閉じるためだけに消費する。
  // hover だけでも開くので、trigger ではなく **document の capture で** 拾う
  // (trigger の onKeyDown は focus が trigger にあるときしか発火しない)。
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key !== 'Escape') return;
      e.stopPropagation();
      e.preventDefault();
      setPinned(false);
      setHovered(false);
      setFocused(false);
      if (document.activeElement === triggerRef.current) {
        triggerRef.current?.blur();
      }
    }
    document.addEventListener('keydown', onKey, true);
    return () => document.removeEventListener('keydown', onKey, true);
  }, [open]);

  // 開いたまま resize / scroll されると、開いた瞬間の向きが古くなる
  // (pinned で開いたまま window を縦に縮めると再び切られる)。
  useEffect(() => {
    if (!open) return;
    function reposition() {
      setPlacement(computePlacement(wrapperRef.current));
    }
    reposition();
    window.addEventListener('resize', reposition);
    document.addEventListener('scroll', reposition, true);
    return () => {
      window.removeEventListener('resize', reposition);
      document.removeEventListener('scroll', reposition, true);
    };
  }, [open]);

  return (
    <span className={styles.wrapper} ref={wrapperRef}>
      <button
        type="button"
        ref={triggerRef}
        className={styles.trigger}
        aria-label={label}
        onMouseEnter={() => {
          openFrom();
          setHovered(true);
        }}
        onMouseLeave={() => setHovered(false)}
        onFocus={() => {
          openFrom();
          setFocused(true);
        }}
        onBlur={() => {
          setFocused(false);
          setPinned(false);
        }}
        onClick={() => {
          openFrom();
          setPinned((v) => !v);
        }}
        data-testid={testId === undefined ? undefined : `${testId}-trigger`}
      >
        ?
      </button>
      {open && (
        <span
          className={`${styles.popover}${placement === 'above' ? ` ${styles.popoverAbove}` : ''}`}
          data-placement={placement}
          data-testid={testId === undefined ? undefined : `${testId}-popover`}
        >
          {children}
        </span>
      )}
    </span>
  );
}
