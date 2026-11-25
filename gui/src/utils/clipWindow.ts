/**
 * 切り抜き範囲の算出 (#1131 / #1139)。
 *
 * 規則の正は CLI (`allaganeye/export/clips.py`) で、ここはその鏡:
 *
 * 1. `events[].clip_start` / `clip_end` が両方あれば **ユーザー指定の区間**。
 *    `--pre` / `--post` も近接束ねも適用せず、試合区間へクランプするだけ
 *    (#1139)。片方だけ / 逆転区間は無視する。
 * 2. それ以外は `timestamp` 昇順に並べ、`次の start - 現在の end <= gap` なら
 *    同じグループへ束ね、`[開始 - pre, 終端 + post]` を試合区間へクランプする。
 * 3. クランプ後に 0.01 秒未満になるグループはクリップにならない (CLI は
 *    `round(..., 2)` してから 0 幅を判定するため、丸めたら潰れる幅は書かれない)。
 *
 * **四捨五入はしない**。JS の half-up と Python の half-even は 0.005 秒の端で
 * 食い違い、GUI だけが「範囲外」と判定する差になる (codex review 2026-11-17)。
 */

import type { HighlightEvent } from '../types/metadata.generated';

/** CLI `clips` の `--pre` / `--post` 既定値。 */
export const DEFAULT_MARGIN_SECONDS = 10;

/** CLI `clips` の `--gap` 既定値。束ね判定に使う。 */
export const DEFAULT_GAP_SECONDS = 5;

/** クリップとして成立する最小幅 (秒)。CLI の `round(..., 2)` 後の 0 幅判定に合わせる。 */
export const MIN_WINDOW_SECONDS = 0.01;

export interface ClipWindow {
  start: number;
  end: number;
}

function finite(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

/**
 * イベントに保存された**ユーザー指定の区間** (#1139)。無効なら null。
 *
 * 両方が有限値で `end > start` のときだけ有効 (CLI の受理条件と同じ)。
 */
export function overrideWindowFor(
  event: Pick<HighlightEvent, 'clip_start' | 'clip_end'>,
): ClipWindow | null {
  const start = event.clip_start;
  const end = event.clip_end;
  if (!finite(start) || !finite(end) || end <= start) return null;
  return { start, end };
}

/**
 * イベント 1 件の「自動」区間 (`pre` / `post` 付き、0 秒でクランプ)。
 *
 * 表示やプレビューの初期値に使う。実際に書かれる区間は `planClipWindows`。
 */
export function eventClipWindow(
  event: Pick<HighlightEvent, 'timestamp' | 'end'>,
  pre: number = DEFAULT_MARGIN_SECONDS,
  post: number = DEFAULT_MARGIN_SECONDS,
): ClipWindow {
  const start = Math.max(0, event.timestamp - pre);
  const end = Math.max(start, event.end + post);
  return { start, end };
}

/**
 * 区間がクリップとして成立するか。
 *
 * - 自動区間 (束ね + pre/post): 幅 0.01 秒以上。CLI は `round(..., 2)` してから
 *   0 幅を判定するので、丸めたら潰れる幅は書かれない。
 * - ユーザー指定区間: CLI の判定 (`round(start,2) < round(end,2)`) に合わせて、
 *   幅が 0.01 秒未満でも丸めた両端が異なれば成立する
 *   (例: 100.004-100.011 は丸めで 100.00-100.01 になり書き出される)。
 *   丸めは half-up 近似 (厳密な half-even の差は 0.005 秒の端のみ)。
 */
function windowSurvives(start: number, end: number, explicit: boolean): boolean {
  if (end - start >= MIN_WINDOW_SECONDS) return true;
  if (!explicit) return false;
  return Math.round(end * 100) > Math.round(start * 100);
}

/** 実際に書き出される区間を `metadata.events` の 1 始まり位置で引く map を作る。 */
export function planClipWindows(
  events: readonly HighlightEvent[] | undefined,
  matches: readonly { index: number; start_time: number; end_time: number }[],
  pre: number,
  post: number,
  gap: number = DEFAULT_GAP_SECONDS,
): Map<number, ClipWindow> {
  return planClipWindowsDetailed(events, matches, pre, post, gap).windows;
}

/** 区間と、その区間を共有しているイベント数。 */
export interface ClipPlan {
  windows: Map<number, ClipWindow>;
  /** `position` -> その区間を共有するイベント数 (ユーザー指定区間は常に 1)。 */
  bundled: Map<number, number>;
}

/**
 * 実際に書き出される区間 + 束ね件数 (#1156)。
 *
 * 「自動範囲」の表示と、手動保存で束ねから外れる副作用の告知に使う。
 */
export function planClipWindowsDetailed(
  events: readonly HighlightEvent[] | undefined,
  matches: readonly { index: number; start_time: number; end_time: number }[],
  pre: number,
  post: number,
  gap: number = DEFAULT_GAP_SECONDS,
): ClipPlan {
  const spans = new Map<number, { start: number; end: number }>();
  for (const match of matches) {
    if (Number.isFinite(match.start_time) && Number.isFinite(match.end_time)) {
      spans.set(match.index, { start: match.start_time, end: match.end_time });
    }
  }

  interface Item {
    position: number;
    matchIndex: number;
    start: number;
    end: number;
  }
  const items: Item[] = [];
  const explicit: Item[] = [];
  (events ?? []).forEach((event, index) => {
    const matchIndex = event.match_index;
    if (matchIndex === null || !spans.has(matchIndex)) return;
    if (!Number.isFinite(event.timestamp) || !Number.isFinite(event.end)) return;
    const item: Item = {
      position: index + 1,
      matchIndex,
      start: event.timestamp,
      end: Math.max(event.end, event.timestamp),
    };
    const override = overrideWindowFor(event);
    if (override !== null) {
      // ユーザー指定区間は束ねない (明示した範囲を隣と合成しない)。
      explicit.push({ ...item, start: override.start, end: override.end });
      return;
    }
    items.push(item);
  });
  items.sort((a, b) =>
    a.matchIndex !== b.matchIndex
      ? a.matchIndex - b.matchIndex
      : a.start !== b.start
        ? a.start - b.start
        : a.end - b.end,
  );

  const windows = new Map<number, ClipWindow>();
  const bundled = new Map<number, number>();

  let group: Item & { positions: number[] } | null = null;
  const flush = () => {
    if (group === null) return;
    for (const position of group.positions) {
      const span = spans.get(group.matchIndex)!;
      const start = Math.max(0, span.start, group.start - pre);
      const end = Math.min(span.end, group.end + post);
      if (end - start >= MIN_WINDOW_SECONDS) {
        windows.set(position, { start, end });
        bundled.set(position, group.positions.length);
      }
    }
    group = null;
  };
  for (const item of items) {
    if (
      group !== null &&
      group.matchIndex === item.matchIndex &&
      item.start - group.end <= gap
    ) {
      group.end = Math.max(group.end, item.end);
      group.positions.push(item.position);
      continue;
    }
    flush();
    group = { ...item, positions: [item.position] };
  }
  flush();

  for (const item of explicit) {
    const span = spans.get(item.matchIndex)!;
    const start = Math.max(0, span.start, item.start);
    const end = Math.min(span.end, item.end);
    if (windowSurvives(start, end, true)) {
      windows.set(item.position, { start, end });
      bundled.set(item.position, 1);
    }
  }
  return { windows, bundled };
}

/** 「自動範囲」= 手動上書きを消したときに `planClipWindows` が返す区間 (#1156)。 */
export interface ClipBaseline extends ClipWindow {
  /** この区間を共有するイベント数 (1 は束ねなし)。 */
  bundled: number;
}

/**
 * イベント 1 件の「自動範囲」を引く (#1156)。
 *
 * 対象イベントの `clip_start` / `clip_end` を消したクローンで計画を引き直すので、
 * **近接イベントの束ね (`gap`) と試合区間へのクランプを含む実効値**になる。
 * イベント単体の `timestamp ± pre/post` ではない点が重要 (束ねを無視すると
 * 表示と実際のクリップが食い違う)。
 *
 * クランプで 0 幅になる (クリップにならない) 場合は null。
 */
export function planClipBaseline(
  events: readonly HighlightEvent[] | undefined,
  matches: readonly { index: number; start_time: number; end_time: number }[],
  pre: number,
  post: number,
  gap: number,
  position: number,
): ClipBaseline | null {
  const cleared = (events ?? []).map((event, index) => {
    if (index !== position - 1) return event;
    const next: Record<string, unknown> = { ...event };
    delete next.clip_start;
    delete next.clip_end;
    return next as HighlightEvent;
  });
  const plan = planClipWindowsDetailed(cleared, matches, pre, post, gap);
  const window = plan.windows.get(position);
  if (window === undefined) return null;
  return {
    start: window.start,
    end: window.end,
    bundled: plan.bundled.get(position) ?? 1,
  };
}
