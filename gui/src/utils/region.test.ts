import { describe, expect, it } from 'vitest';

import { elementRectToSourcePx, validateRegionPx } from './region';

describe('elementRectToSourcePx', () => {
  it('maps element rect to source px with horizontal letterbox', () => {
    // 1920x1080 video shown in a 1000x480 box
    // fitScale = min(1000/1920, 480/1080) = min(0.5208, 0.4444) = 0.4444
    // displayed video = 1920*0.4444=853.3 x 480, letterbox x-bar = (1000-853.3)/2=73.3
    const src = elementRectToSourcePx(
      { x: 73.3 + 0, y: 0, w: 853.3, h: 480 }, // full displayed video
      { width: 1000, height: 480 },
      1920, 1080,
    );
    expect(src.x).toBe(0);
    expect(src.y).toBe(0);
    expect(src.w).toBe(1920);
    expect(src.h).toBe(1080);
  });

  it('maps element rect to source px with vertical letterbox', () => {
    // 1920x1080 video shown in a 960x1000 box
    // fitScale = min(960/1920, 1000/1080) = min(0.5, 0.9259) = 0.5
    // displayed video = 960 x 1080*0.5=540, letterbox y-bar = (1000-540)/2=230
    const src = elementRectToSourcePx(
      { x: 0, y: 230, w: 960, h: 540 }, // full displayed video
      { width: 960, height: 1000 },
      1920, 1080,
    );
    expect(src.x).toBe(0);
    expect(src.y).toBe(0);
    expect(src.w).toBe(1920);
    expect(src.h).toBe(1080);
  });

  it('maps a partial selection correctly', () => {
    // 1920x1080 video shown at 1:1 scale (no letterbox)
    const src = elementRectToSourcePx(
      { x: 100, y: 200, w: 400, h: 300 },
      { width: 1920, height: 1080 },
      1920, 1080,
    );
    expect(src.x).toBe(100);
    expect(src.y).toBe(200);
    expect(src.w).toBe(400);
    expect(src.h).toBe(300);
  });
});

describe('validateRegionPx', () => {
  it('rejects width below 16', () => {
    expect(validateRegionPx({ x: 0, y: 0, w: 8, h: 100 }, 1920, 1080)).toMatch(/16/);
  });

  it('rejects height below 16', () => {
    expect(validateRegionPx({ x: 0, y: 0, w: 100, h: 8 }, 1920, 1080)).toMatch(/16/);
  });

  it('rejects out-of-frame (x+w)', () => {
    expect(validateRegionPx({ x: 1900, y: 0, w: 100, h: 100 }, 1920, 1080)).toMatch(/frame|超|exceed/i);
  });

  it('rejects out-of-frame (y+h)', () => {
    expect(validateRegionPx({ x: 0, y: 1000, w: 100, h: 100 }, 1920, 1080)).toMatch(/frame|超|exceed/i);
  });

  it('rejects negative coordinates', () => {
    expect(validateRegionPx({ x: -1, y: 0, w: 100, h: 100 }, 1920, 1080)).not.toBeNull();
  });

  it('accepts a valid region', () => {
    expect(validateRegionPx({ x: 10, y: 20, w: 300, h: 400 }, 1920, 1080)).toBeNull();
  });
});
