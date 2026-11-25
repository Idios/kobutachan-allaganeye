/**
 * クリップ範囲の計画 (#1156)。
 *
 * `planClipWindows` は CLI (`allaganeye/export/clips.py`) の鏡で、束ねと試合区間
 * クランプを含む。`planClipBaseline` はその「手動上書きを消したときの区間」で、
 * クリップ範囲エディタの [自動範囲に戻す] と差分表示の基準になる。
 */
import { describe, expect, it } from 'vitest';

import {
  planClipBaseline,
  planClipWindows,
  planClipWindowsDetailed,
} from './clipWindow';
import type { HighlightEvent } from '../types/metadata.generated';

const MATCHES = [{ index: 1, start_time: 100, end_time: 400 }];

function event(
  timestamp: number,
  end: number,
  extra: Partial<HighlightEvent> = {},
): HighlightEvent {
  return {
    signal_id: 'ko_indicator',
    timestamp,
    end,
    score: 0.9,
    evidence: { samples: 15 },
    match_index: 1,
    ...extra,
  };
}

describe('planClipWindowsDetailed (#1156)', () => {
  it('reports how many events share a bundled window', () => {
    const events = [event(200, 202), event(205, 207), event(300, 302)];

    const plan = planClipWindowsDetailed(events, MATCHES, 10, 10, 5);

    // e1 (200-202) と e2 (205-207) は gap 5 秒以内なので 1 本に束ねる。
    expect(plan.windows.get(1)).toEqual({ start: 190, end: 217 });
    expect(plan.windows.get(2)).toEqual({ start: 190, end: 217 });
    expect(plan.bundled.get(1)).toBe(2);
    expect(plan.bundled.get(2)).toBe(2);

    expect(plan.windows.get(3)).toEqual({ start: 290, end: 312 });
    expect(plan.bundled.get(3)).toBe(1);
  });

  it('treats a user override as a standalone (unbundled) clip', () => {
    const events = [event(200, 202, { clip_start: 191, clip_end: 195 }), event(205, 207)];

    const plan = planClipWindowsDetailed(events, MATCHES, 10, 10, 5);

    expect(plan.windows.get(1)).toEqual({ start: 191, end: 195 });
    expect(plan.bundled.get(1)).toBe(1);
    // 残った e2 は束ね相手がいないので自分の前後 10 秒になる。
    expect(plan.windows.get(2)).toEqual({ start: 195, end: 217 });
    expect(plan.bundled.get(2)).toBe(1);
  });

  it('exposes the same windows through planClipWindows', () => {
    const events = [event(200, 202), event(205, 207)];

    const windows = planClipWindows(events, MATCHES, 10, 10, 5);
    const plan = planClipWindowsDetailed(events, MATCHES, 10, 10, 5);

    expect(windows.size).toBe(plan.windows.size);
    expect(windows.get(1)).toEqual(plan.windows.get(1));
  });
});

describe('planClipBaseline (#1156)', () => {
  it('ignores a stored override and returns the automatic window', () => {
    const events = [event(200, 202, { clip_start: 191, clip_end: 195 }), event(205, 207)];

    expect(planClipBaseline(events, MATCHES, 10, 10, 5, 1)).toEqual({
      start: 190,
      end: 217,
      bundled: 2,
    });
  });

  it('clamps to the match span', () => {
    const events = [event(105, 106)];

    // 105 - 10 = 95 は試合開始 (100) より前 → 100 に clamp する。
    expect(planClipBaseline(events, MATCHES, 10, 10, 5, 1)).toEqual({
      start: 100,
      end: 116,
      bundled: 1,
    });
  });

  it('returns null when the window collapses to zero width', () => {
    const events = [event(300, 300)];

    expect(planClipBaseline(events, MATCHES, 0, 0, 5, 1)).toBeNull();
  });

  it('returns null when the event is outside any match', () => {
    const events = [event(200, 202, { match_index: null })];

    expect(planClipBaseline(events, MATCHES, 10, 10, 5, 1)).toBeNull();
  });
});
