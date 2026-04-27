import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn().mockResolvedValue(undefined),
}));

import { CompleteScreen } from './CompleteScreen';
import { useAppStateStore } from '../state/appStateStore';
import { useMetadataStore } from '../state/metadataStore';

beforeEach(() => {
  useAppStateStore.getState().reset();
  useMetadataStore.getState().clear();
  useMetadataStore.getState().loadSample();
  useAppStateStore.getState().navigate('complete');
});

describe('CompleteScreen', () => {
  it('renders empty state when metadata is null', () => {
    useMetadataStore.getState().clear();
    render(<CompleteScreen />);
    expect(screen.getByText(/No metadata/i)).toBeInTheDocument();
  });

  it('displays source and match count from the store', () => {
    render(<CompleteScreen />);
    expect(screen.getByText(/2026-04-08 21-14-05.mkv/)).toBeInTheDocument();
    // sampleMetadata contains 9 matches
    expect(screen.getByText('9')).toBeInTheDocument();
  });

  it('renders a row per match', () => {
    render(<CompleteScreen />);
    for (let i = 1; i <= 9; i++) {
      expect(screen.getByTestId(`match-row-${i}`)).toBeInTheDocument();
    }
  });

  it('clicking a match row updates selectedMatchIndex', async () => {
    render(<CompleteScreen />);
    const user = userEvent.setup();
    await user.click(screen.getByTestId('match-row-3'));
    expect(useAppStateStore.getState().selectedMatchIndex).toBe(3);
  });

  it('double-click navigates to preview with that match', async () => {
    render(<CompleteScreen />);
    const user = userEvent.setup();
    await user.dblClick(screen.getByTestId('match-row-4'));
    const state = useAppStateStore.getState();
    expect(state.screen).toBe('preview');
    expect(state.selectedMatchIndex).toBe(4);
  });

  it('[境界を調整] button navigates to preview with the selected match', async () => {
    render(<CompleteScreen />);
    const user = userEvent.setup();
    // Select match 3 first
    await user.click(screen.getByTestId('match-row-3'));
    // Then click the header [境界を調整] button
    await user.click(screen.getByRole('button', { name: '境界を調整' }));
    const state = useAppStateStore.getState();
    expect(state.screen).toBe('preview');
    expect(state.selectedMatchIndex).toBe(3);
  });

  it('[全試合書き出し] navigates to export', async () => {
    render(<CompleteScreen />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /全試合書き出し/ }));
    expect(useAppStateStore.getState().screen).toBe('export');
  });

  it('[× 閉じる] clears store and navigates to drop', async () => {
    render(<CompleteScreen />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '閉じる' }));
    expect(useMetadataStore.getState().metadata).toBeNull();
    expect(useAppStateStore.getState().screen).toBe('drop');
  });

  it('auto-selects the first match on mount when none is selected', () => {
    render(<CompleteScreen />);
    expect(useAppStateStore.getState().selectedMatchIndex).toBe(1);
  });

  // #586: 「所要」(elapsed) 列の追加 + legacy fallback。
  describe('elapsed (所要) column', () => {
    it('displays 試合数 / 所要 / 総尺 in three-column stats from sampleMetadata', () => {
      render(<CompleteScreen />);
      // sibling lookup keeps assertions tied to the stats column even when
      // sample listItem rows happen to render the same value text (e.g.
      // 2:50:28 also appears as match-9 end_display).
      const matchesValue = screen.getByText('試合数').nextSibling as HTMLElement;
      expect(matchesValue.textContent).toBe('9');
      const elapsedValue = screen.getByText('所要').nextSibling as HTMLElement;
      // sampleMetadata の started=12:34:56 / completed=12:39:23 (= 267s)
      // → fmtTime で "04:27"
      expect(elapsedValue.textContent).toBe('04:27');
      const totalValue = screen.getByText('総尺').nextSibling as HTMLElement;
      expect(totalValue.textContent).toBe('2:50:28');
    });

    it('formats elapsed as H:MM:SS when >= 1 hour', () => {
      const meta = useMetadataStore.getState().metadata;
      if (!meta) throw new Error('expected sample metadata loaded');
      // started = 2026-04-19T12:34:56Z, completed = +1h05m43s
      useMetadataStore.setState({
        metadata: {
          ...meta,
          detection_started_at: '2026-04-19T12:34:56Z',
          detection_completed_at: '2026-04-19T13:40:39Z',
        },
      });
      render(<CompleteScreen />);
      expect(screen.getByText('1:05:43')).toBeInTheDocument();
    });

    it('shows "—" when detection_completed_at is missing (legacy)', () => {
      const meta = useMetadataStore.getState().metadata;
      if (!meta) throw new Error('expected sample metadata loaded');
      useMetadataStore.setState({
        metadata: {
          ...meta,
          detection_started_at: '2026-04-19T12:34:56Z',
          detection_completed_at: undefined,
        },
      });
      render(<CompleteScreen />);
      // Find the 所要 cell and assert its sibling shows the fallback dash.
      const label = screen.getByText('所要');
      const valueDiv = label.nextSibling as HTMLElement | null;
      expect(valueDiv?.textContent).toBe('—');
    });

    it('shows "—" when detection_started_at is missing (deeper legacy)', () => {
      const meta = useMetadataStore.getState().metadata;
      if (!meta) throw new Error('expected sample metadata loaded');
      useMetadataStore.setState({
        metadata: {
          ...meta,
          detection_started_at: undefined,
          detection_completed_at: '2026-04-19T12:39:23Z',
        },
      });
      render(<CompleteScreen />);
      const label = screen.getByText('所要');
      const valueDiv = label.nextSibling as HTMLElement | null;
      expect(valueDiv?.textContent).toBe('—');
    });
  });
});
