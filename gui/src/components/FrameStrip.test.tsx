import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { FrameStrip } from './FrameStrip';
import styles from './FrameStrip.module.css';

describe('FrameStrip', () => {
  it('renders `count` frames (default 12)', () => {
    render(<FrameStrip boundaryT={100} windowSec={3} />);
    const strip = screen.getByTestId('frame-strip');
    expect(strip.children.length).toBe(12);
  });

  it('renders the requested number of frames when count is overridden', () => {
    render(<FrameStrip boundaryT={100} windowSec={3} count={6} />);
    expect(screen.getByTestId('frame-strip').children.length).toBe(6);
  });

  it('marks a boundary frame via data-boundary attribute', () => {
    render(<FrameStrip boundaryT={100} windowSec={3} count={6} />);
    const cells = screen.getByTestId('frame-strip').querySelectorAll('button');
    const boundaryCells = Array.from(cells).filter((c) => c.dataset.boundary === 'true');
    expect(boundaryCells.length).toBeGreaterThan(0);
  });

  it('fires onSelectFrame with the clicked cell timestamp', async () => {
    const onSelect = vi.fn();
    render(<FrameStrip boundaryT={100} windowSec={3} count={6} onSelectFrame={onSelect} />);
    const cells = screen.getByTestId('frame-strip').querySelectorAll('button');
    const user = userEvent.setup();
    await user.click(cells[0] as Element);
    expect(onSelect).toHaveBeenCalledTimes(1);
    // First cell t = 100 - 3 + 0 = 97
    expect(onSelect.mock.calls[0][0]).toBeCloseTo(97, 5);
  });

  // #645 Chapter 2 (overlay pivot): brightness samples + threshold + blackout
  // bands + waveform path render as an absolutely-positioned SVG overlay on
  // top of the thumbnail buttons. Decorative (aria-hidden) and pointer-events
  // none — clicks still pass through to the buttons.
  it('renders brightness overlay when brightnessSamples is provided', () => {
    const samples = Array.from({ length: 60 }, (_, i) => (i >= 25 && i <= 35 ? 5 : 200));
    render(
      <FrameStrip
        boundaryT={100}
        windowSec={3}
        brightnessSamples={samples}
        brightnessThreshold={15}
        brightnessWindowSeconds={6}
      />,
    );
    const overlay = screen.getByTestId('frame-strip-brightness-overlay');
    expect(overlay).toBeInTheDocument();
    expect(overlay.getAttribute('aria-hidden')).toBe('true');
    // threshold line + waveform path + at least one blackout band
    expect(overlay.querySelector('[data-testid="threshold-line"]')).not.toBeNull();
    expect(overlay.querySelector('[data-testid="waveform-path"]')).not.toBeNull();
    expect(overlay.querySelectorAll('[data-testid="blackout-band"]').length).toBeGreaterThanOrEqual(
      1,
    );
  });

  it('does not render brightness overlay when brightnessSamples is omitted', () => {
    render(<FrameStrip boundaryT={100} windowSec={3} />);
    expect(screen.queryByTestId('frame-strip-brightness-overlay')).toBeNull();
  });
});

// #1164: mutation testing (mutator) の undetected を潰すための境界値・分岐網羅。
// 期待値はすべて synthesizeFrames の式（count / windowSec / boundaryT）から
// 手計算できる値で pin する（マジックナンバーではなく式の帰結であることを
// コメントに残す）。
describe('FrameStrip (mutation coverage, #1164)', () => {
  const cells = () =>
    Array.from(screen.getByTestId('frame-strip').querySelectorAll('button')) as HTMLElement[];
  const shimmers = () =>
    Array.from(
      screen.getByTestId('frame-strip').querySelectorAll(`.${styles.shimmer}`),
    ) as HTMLElement[];
  const styleOf = (el: HTMLElement) => `${el.getAttribute('style') ?? ''} ${el.style.cssText}`;

  it('lays out frames from boundaryT - windowSec to boundaryT + windowSec', async () => {
    // count=6, windowSec=3 → step = (windowSec * 2) / (count - 1) = 1.2
    const onSelect = vi.fn();
    render(<FrameStrip boundaryT={100} windowSec={3} count={6} onSelectFrame={onSelect} />);
    const user = userEvent.setup();
    const all = cells();
    expect(all).toHaveLength(6);
    await user.click(all[0]);
    await user.click(all[5]);
    expect(onSelect.mock.calls[0][0]).toBeCloseTo(97, 6);
    expect(onSelect.mock.calls[1][0]).toBeCloseTo(103, 6);
  });

  it('renders no frames for count <= 0', () => {
    const { unmount } = render(<FrameStrip boundaryT={100} windowSec={3} count={0} />);
    expect(cells()).toHaveLength(0);
    unmount();
    render(<FrameStrip boundaryT={100} windowSec={3} count={-2} />);
    expect(cells()).toHaveLength(0);
  });

  it('renders a single frame at the window start for count === 1', async () => {
    // count === 1 の denom は 1（count - 1 にすると 0 除算で NaN になる）
    const onSelect = vi.fn();
    render(<FrameStrip boundaryT={100} windowSec={3} count={1} onSelectFrame={onSelect} />);
    const all = cells();
    expect(all).toHaveLength(1);
    await userEvent.setup().click(all[0]);
    expect(onSelect.mock.calls[0][0]).toBeCloseTo(97, 6);
    expect(all[0].dataset.boundary).toBe('true');
  });

  it('marks exactly the frame closest to boundaryT as the boundary', () => {
    // 97, 98.2, 99.4, 100.6, 101.8, 103 → 100 に最も近いのは index 2 (99.4)
    render(<FrameStrip boundaryT={100} windowSec={3} count={6} />);
    const all = cells();
    expect(all.map((c) => c.dataset.boundary)).toEqual([
      'false',
      'false',
      'true',
      'false',
      'false',
      'false',
    ]);
  });

  it('keeps the first frame when two frames are equidistant from boundaryT', () => {
    // 97.5 / 102.5 → 中心 100 と等距離 (2.5) のときは先勝ち (index 0)
    render(<FrameStrip boundaryT={100} windowSec={2.5} count={2} />);
    expect(cells().map((c) => c.dataset.boundary)).toEqual(['true', 'false']);
  });

  it('treats |d| == 1.2 as the middle band (strict <)', () => {
    // windowSec=1.2, boundaryT=0 → 先頭 frame は -1.2 (距離は double の 1.2 ちょうど)。
    // `d < 1.2` を `<=` にすると 0.08 帯になり黒 overlay が 1 枚増える。
    render(<FrameStrip boundaryT={0} windowSec={1.2} count={3} />);
    expect(
      screen.getByTestId('frame-strip').querySelectorAll(`.${styles.blackOverlay}`),
    ).toHaveLength(1);
    // 0.35 帯 (alpha 0.35 * 0.6 = 0.21) であることを pin する
    expect(styleOf(shimmers()[0])).toContain('0.21');
  });

  it('treats |d| == 2.5 as the outer band (strict <)', () => {
    // windowSec=2.5, boundaryT=0 → 両端の距離は 2.5 ちょうど。
    // `d < 2.5` を `<=` にすると 0.85 帯が 0.35 帯 (0.51 → 0.21) に変わる。
    render(<FrameStrip boundaryT={0} windowSec={2.5} count={3} />);
    const gradients = shimmers().map((el) => styleOf(el));
    expect(gradients[0]).toContain('0.51');
    expect(gradients[2]).toContain('0.51');
  });

  it('classifies brightness by distance to boundaryT (0.85 / 0.35 / 0.08)', () => {
    render(<FrameStrip boundaryT={100} windowSec={3} count={6} />);
    const gradients = shimmers().map((el) => styleOf(el));
    // i=0: |d|=3 → 0.85 / gradient origin 40% 50% / alpha 0.85*0.6=0.51
    expect(gradients[0]).toContain('40% 50%');
    expect(gradients[0]).toContain('0.51');
    // i=1: |d|=1.8 → 0.35 / 40+3=43% 50+(1%3)*10=60% / alpha 0.21
    expect(gradients[1]).toContain('43% 60%');
    expect(gradients[1]).toContain('0.21');
    // i=2: |d|=0.6 → 0.08 / 46% 70% / alpha 0.048
    expect(gradients[2]).toContain('46% 70%');
    expect(gradients[2]).toContain('0.048');
    // backgroundColor 側 (0.4 係数) も 0.08 由来の値になる
    expect(styleOf(shimmers()[2])).toContain('0.032');
    // i=5: 40+5*3=55% / 50+(5%3)*10=70% / alpha 0.51
    expect(gradients[5]).toContain('55% 70%');
    expect(gradients[5]).toContain('0.51');
  });

  it('renders the black overlay only for dark frames without a thumbnail', () => {
    render(<FrameStrip boundaryT={100} windowSec={3} count={6} />);
    const dark = Array.from(
      screen.getByTestId('frame-strip').querySelectorAll(`.${styles.blackOverlay}`),
    );
    // brightness 0.08 (< 0.15) は index 2 / 3 のみ
    expect(dark).toHaveLength(2);
  });

  it('skips the black overlay on a dark frame that has a thumbnail', () => {
    render(
      <FrameStrip
        boundaryT={100}
        windowSec={3}
        count={6}
        thumbs={[
          { t: 99.4, url: '/thumb-a.webp' },
          { t: 100.6, url: '/thumb-b.webp' },
        ]}
      />,
    );
    const darkOverlays = screen
      .getByTestId('frame-strip')
      .querySelectorAll(`.${styles.blackOverlay}`);
    expect(darkOverlays).toHaveLength(0);
  });

  it('renders thumbnails for the nearest cached timestamp', () => {
    render(
      <FrameStrip
        boundaryT={100}
        windowSec={3}
        count={6}
        thumbs={[
          { t: 97, url: '/a.webp' },
          { t: 100, url: '/b.webp' },
          { t: 103, url: '/c.webp' },
        ]}
      />,
    );
    const images = Array.from(
      screen.getByTestId('frame-strip').querySelectorAll('img'),
    ) as HTMLImageElement[];
    expect(images).toHaveLength(6);
    // 97 → a, 98.2 → a (1.2 < 1.8), 99.4/100.6 → b, 101.8/103 → c
    expect(images.map((img) => img.getAttribute('src'))).toEqual([
      '/a.webp',
      '/a.webp',
      '/b.webp',
      '/b.webp',
      '/c.webp',
      '/c.webp',
    ]);
    expect(images[0].getAttribute('draggable')).toBe('false');
  });

  it('prefers the first of two equidistant thumbnails', () => {
    // t=97 は 100 / 94 から等距離 (3) → 先勝ち（`d < bestDist` を `<=` にすると後勝ち）
    render(
      <FrameStrip
        boundaryT={100}
        windowSec={3}
        count={6}
        thumbs={[
          { t: 100, url: '/first.webp' },
          { t: 94, url: '/second.webp' },
        ]}
      />,
    );
    const images = Array.from(
      screen.getByTestId('frame-strip').querySelectorAll('img'),
    ) as HTMLImageElement[];
    expect(images[0].getAttribute('src')).toBe('/first.webp');
  });

  it('falls back to the synthetic shimmer when thumbs is empty', () => {
    render(<FrameStrip boundaryT={100} windowSec={3} count={3} thumbs={[]} />);
    expect(screen.getByTestId('frame-strip').querySelectorAll('img')).toHaveLength(0);
    expect(shimmers()).toHaveLength(3);
  });

  it('labels each cell with mm:ss and a precise aria-label', () => {
    render(<FrameStrip boundaryT={100} windowSec={3} count={6} />);
    const all = cells();
    expect(all[0].getAttribute('aria-label')).toBe('frame 0:01:37.00');
    expect(all[0].querySelector(`.${styles.label}`)?.textContent).toBe('01:37');
  });

  it('drops the hour from the label but keeps it in the aria-label', () => {
    // 1 時間超でも label は末尾 2 要素 (mm:ss) だけを出す
    render(<FrameStrip boundaryT={3700} windowSec={3} count={6} />);
    const all = cells();
    expect(all[0].querySelector(`.${styles.label}`)?.textContent).toBe('01:37');
    expect(all[0].getAttribute('aria-label')).toBe('frame 1:01:37.00');
  });

  it('applies the boundary class and bar to the boundary cell only', () => {
    render(<FrameStrip boundaryT={100} windowSec={3} count={6} />);
    const all = cells();
    expect(all[2].className).toContain(styles.cell);
    expect(all[2].className).toContain(styles.cellBoundary);
    expect(all[0].className).toBe(styles.cell);
    expect(all[2].querySelectorAll(`.${styles.boundaryBar}`)).toHaveLength(1);
    expect(all[0].querySelectorAll(`.${styles.boundaryBar}`)).toHaveLength(0);
  });

  it('disables every cell with the reason as tooltip when disabled', () => {
    render(
      <FrameStrip
        boundaryT={100}
        windowSec={3}
        count={3}
        disabled
        disabledReason="実際の動画を選択してください"
      />,
    );
    const all = cells();
    expect(all.every((c) => c.hasAttribute('disabled'))).toBe(true);
    expect(all.map((c) => c.getAttribute('title'))).toEqual([
      '実際の動画を選択してください',
      '実際の動画を選択してください',
      '実際の動画を選択してください',
    ]);
  });

  it('has no tooltip when disabled without a reason', () => {
    render(<FrameStrip boundaryT={100} windowSec={3} count={3} disabled />);
    expect(cells()[0].hasAttribute('title')).toBe(false);
  });

  it('maps the threshold line onto the 200x36 overlay box', () => {
    const samples = [200, 200, 200];
    render(
      <FrameStrip
        boundaryT={100}
        windowSec={3}
        count={3}
        brightnessSamples={samples}
        brightnessThreshold={51}
        brightnessWindowSeconds={4}
      />,
    );
    const overlay = screen.getByTestId('frame-strip-brightness-overlay');
    expect(overlay.getAttribute('viewBox')).toBe('0 0 200 36');
    const line = overlay.querySelector('[data-testid="threshold-line"]');
    // 36 - (51 / 255) * 36 = 28.8
    expect(line?.getAttribute('y1')).toBe('28.8');
    expect(line?.getAttribute('y2')).toBe('28.8');
    expect(line?.getAttribute('x2')).toBe('200');
  });

  it('maps blackout bands with the explicit window seconds', () => {
    // n=9, duration=4 → t = i * 0.5。i=2..3 が黒 → region {start:1, end:2}
    const samples = [200, 200, 10, 10, 200, 200, 200, 200, 200];
    render(
      <FrameStrip
        boundaryT={100}
        windowSec={3}
        count={3}
        brightnessSamples={samples}
        brightnessWindowSeconds={4}
      />,
    );
    const bands = screen
      .getByTestId('frame-strip-brightness-overlay')
      .querySelectorAll('[data-testid="blackout-band"]');
    expect(bands).toHaveLength(1);
    // x1 = (1 / 4) * 200 = 50, x2 = (2 / 4) * 200 = 100
    expect(bands[0].getAttribute('x')).toBe('50');
    expect(bands[0].getAttribute('width')).toBe('50');
    expect(bands[0].getAttribute('height')).toBe('36');
  });

  it('defaults the overlay window to 2 * windowSec', () => {
    // brightnessWindowSeconds 省略 → overlayWindowSeconds = 3 * 2 = 6
    const samples = [200, 10, 10, 200, 200];
    render(<FrameStrip boundaryT={100} windowSec={3} count={3} brightnessSamples={samples} />);
    const band = screen
      .getByTestId('frame-strip-brightness-overlay')
      .querySelector('[data-testid="blackout-band"]');
    // t = i * (6 / 4) = i * 1.5 → i=1..2 が黒、end は次の sample (i=3) の t
    // region {start:1.5, end:4.5} → x1 = (1.5 / 6) * 200 = 50, x2 = 150
    expect(band?.getAttribute('x')).toBe('50');
    expect(band?.getAttribute('width')).toBe('100');
  });

  it('keeps a minimum band width of 1.5 for a single-sample blackout', () => {
    const samples = Array.from({ length: 200 }, (_, i) => (i === 100 ? 0 : 200));
    render(
      <FrameStrip
        boundaryT={100}
        windowSec={3}
        count={3}
        brightnessSamples={samples}
        brightnessWindowSeconds={10}
      />,
    );
    const band = screen
      .getByTestId('frame-strip-brightness-overlay')
      .querySelector('[data-testid="blackout-band"]');
    // 1 sample 分の幅 = 200 / 199 ≈ 1.005 < 1.5 → 下限に張り付く
    expect(band?.getAttribute('width')).toBe('1.5');
  });

  it('recomputes the overlay when the samples change', () => {
    const { rerender } = render(
      <FrameStrip
        boundaryT={100}
        windowSec={3}
        count={3}
        brightnessSamples={[200, 200, 200, 200, 200]}
        brightnessWindowSeconds={4}
      />,
    );
    const firstPath = screen.getByTestId('waveform-path').getAttribute('d');
    expect(
      screen
        .getByTestId('frame-strip-brightness-overlay')
        .querySelectorAll('[data-testid="blackout-band"]'),
    ).toHaveLength(0);

    rerender(
      <FrameStrip
        boundaryT={100}
        windowSec={3}
        count={3}
        brightnessSamples={[200, 0, 0, 200, 200]}
        brightnessWindowSeconds={4}
      />,
    );
    expect(screen.getByTestId('waveform-path').getAttribute('d')).not.toBe(firstPath);
    expect(
      screen
        .getByTestId('frame-strip-brightness-overlay')
        .querySelectorAll('[data-testid="blackout-band"]'),
    ).toHaveLength(1);
  });
});
