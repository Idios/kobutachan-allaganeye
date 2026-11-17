/**
 * L4 の信号 (signal_id) の表示ラベル (#127)。
 *
 * 元は `IndicatorsScreen.tsx` にあり、`ClipsScreen` / `ClipRangeView` が
 * screen をまたいで import していた (#1139 で重複を解消)。**未知の signal_id は
 * null** を返し、呼び出し側は行ごと描画しない (互換ルール §4-3: 未知信号は
 * 既定で無視する。新しい信号が増えても既存画面は素通りさせる)。
 */

/** `signal_id` の人間向け表示。未知なら null。 */
export function signalLabel(signalId: string): string | null {
  if (signalId === 'ko_indicator') return 'KO';
  if (signalId === 'assist_indicator') return 'ASSIST';
  return null;
}
