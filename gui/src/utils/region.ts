export interface RegionPx { x: number; y: number; w: number; h: number }

/** element 座標系の選択矩形 sel を、object-fit:contain の letterbox を補正して
 *  source pixel に変換する。displayRect = video 要素の表示ボックス。 */
export function elementRectToSourcePx(
  sel: { x: number; y: number; w: number; h: number },
  displayRect: { width: number; height: number },
  videoW: number,
  videoH: number,
): RegionPx {
  const fitScale = Math.min(displayRect.width / videoW, displayRect.height / videoH);
  const shownW = videoW * fitScale;
  const shownH = videoH * fitScale;
  const barX = (displayRect.width - shownW) / 2;
  const barY = (displayRect.height - shownH) / 2;
  const toSrcX = (ex: number) => (ex - barX) / fitScale;
  const toSrcY = (ey: number) => (ey - barY) / fitScale;
  const x = Math.round(toSrcX(sel.x));
  const y = Math.round(toSrcY(sel.y));
  const w = Math.round(sel.w / fitScale);
  const h = Math.round(sel.h / fitScale);
  return {
    x: Math.max(0, Math.min(x, videoW)),
    y: Math.max(0, Math.min(y, videoH)),
    w: Math.max(0, Math.min(w, videoW)),
    h: Math.max(0, Math.min(h, videoH)),
  };
}

/** CLI `_parse_region` と同じ境界を検証。error message (日本語) or null。 */
export function validateRegionPx(r: RegionPx, frameW: number, frameH: number): string | null {
  if ([r.x, r.y, r.w, r.h].some((n) => !Number.isFinite(n) || n < 0)) {
    return '座標は 0 以上で指定してください';
  }
  if (r.w < 16) return '幅 (W) は 16px 以上にしてください';
  if (r.h < 16) return '高さ (H) は 16px 以上にしてください';
  if (r.x + r.w > frameW) return `X+W (${r.x + r.w}) がフレーム幅 (${frameW}) を超えています`;
  if (r.y + r.h > frameH) return `Y+H (${r.y + r.h}) がフレーム高さ (${frameH}) を超えています`;
  return null;
}
