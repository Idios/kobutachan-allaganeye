import { describe, expect, it } from 'vitest';

import { signalLabel } from './signals';

describe('signalLabel', () => {
  it('maps the documented signal ids to their human labels (#127)', () => {
    expect(signalLabel('ko_indicator')).toBe('KO');
    expect(signalLabel('assist_indicator')).toBe('ASSIST');
  });

  // #127 §4-3: 未知の signal_id は null。呼び出し側は行ごと描画しない
  // (新しい信号が増えても既存画面は素通りさせるための前方互換ルール)。
  it('returns null for unknown ids so readers can ignore them', () => {
    expect(signalLabel('boosted_indicator')).toBeNull();
    expect(signalLabel('')).toBeNull();
  });
});
