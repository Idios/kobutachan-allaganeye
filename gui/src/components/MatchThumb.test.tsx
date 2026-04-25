import { render, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { invokeMock } = vi.hoisted(() => ({ invokeMock: vi.fn() }));

vi.mock('@tauri-apps/api/core', () => ({
  invoke: invokeMock,
  convertFileSrc: (p: string) => `asset://localhost/${p}`,
}));

import { MatchThumb } from './MatchThumb';

beforeEach(() => {
  invokeMock.mockReset();
});

describe('MatchThumb', () => {
  it('labels the thumbnail with the match index', () => {
    const { getByLabelText } = render(<MatchThumb index={3} />);
    expect(getByLabelText('match 3 thumbnail')).toBeInTheDocument();
  });

  it('produces a different hue per index (deterministic) when no videoPath provided', () => {
    const { getByTestId, rerender } = render(<MatchThumb index={1} />);
    const hue1 = getByTestId('match-thumb').getAttribute('data-hue');
    rerender(<MatchThumb index={2} />);
    const hue2 = getByTestId('match-thumb').getAttribute('data-hue');
    expect(hue1).not.toBe(hue2);
  });

  it('accepts numeric and string dimensions', () => {
    const { getByTestId, rerender } = render(<MatchThumb index={1} width={120} height={68} />);
    const n = getByTestId('match-thumb') as HTMLElement;
    expect(n.style.width).toBe('120px');
    expect(n.style.height).toBe('68px');
    rerender(<MatchThumb index={1} width="100%" height="100%" />);
    expect(n.style.width).toBe('100%');
    expect(n.style.height).toBe('100%');
  });

  // #465 review (A): real frame thumbnail integration

  it('renders the placeholder gradient (data-real=false) when videoPath is missing', () => {
    const { getByTestId } = render(<MatchThumb index={5} />);
    const el = getByTestId('match-thumb');
    expect(el.getAttribute('data-real')).toBe('false');
    expect(el.getAttribute('data-hue')).not.toBeNull();
  });

  it('renders a real frame (data-real=true) after generate_match_thumbnails resolves', async () => {
    invokeMock.mockResolvedValueOnce([
      { t_seconds: 12.5, file_path: 'C:/cache/match005_t12500.webp' },
    ]);
    const { getByTestId } = render(
      <MatchThumb
        index={5}
        videoPath="C:/videos/x.mkv"
        startTime={12.5}
      />,
    );
    await waitFor(() => {
      const el = getByTestId('match-thumb');
      expect(el.getAttribute('data-real')).toBe('true');
    });
    const el = getByTestId('match-thumb');
    expect(el.style.backgroundImage).toContain(
      'asset://localhost/C:/cache/match005_t12500.webp',
    );
    // invoke は generate_match_thumbnails を 1 frame 分 (count=1, window=0)
    // で呼ぶ
    expect(invokeMock).toHaveBeenCalledWith(
      'generate_match_thumbnails',
      expect.objectContaining({
        videoPath: 'C:/videos/x.mkv',
        matchIndex: 5,
        boundaryTSeconds: 12.5,
        windowSeconds: 0,
        count: 1,
      }),
    );
  });

  it('falls back to the gradient placeholder when generate_match_thumbnails rejects', async () => {
    invokeMock.mockRejectedValueOnce(new Error('ffmpeg not found'));
    const { getByTestId } = render(
      <MatchThumb
        index={5}
        videoPath="C:/videos/x.mkv"
        startTime={12.5}
      />,
    );
    // 初期値は false (placeholder) のまま、reject 後も placeholder のまま
    await waitFor(() => {
      expect(invokeMock).toHaveBeenCalled();
    });
    const el = getByTestId('match-thumb');
    expect(el.getAttribute('data-real')).toBe('false');
  });
});
