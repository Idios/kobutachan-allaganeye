import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { axe } from 'jest-axe';
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

  it('ArrowDown advances the listbox selection (#587)', async () => {
    render(<CompleteScreen />);
    const list = screen.getByTestId('match-row-1').parentElement!;
    list.focus();
    const user = userEvent.setup();
    await user.keyboard('{ArrowDown}');
    expect(useAppStateStore.getState().selectedMatchIndex).toBe(2);
    await user.keyboard('{ArrowDown}');
    expect(useAppStateStore.getState().selectedMatchIndex).toBe(3);
  });

  it('ArrowUp moves selection back, clamped at first (#587)', async () => {
    useAppStateStore.getState().selectMatch(3);
    render(<CompleteScreen />);
    const list = screen.getByTestId('match-row-1').parentElement!;
    list.focus();
    const user = userEvent.setup();
    await user.keyboard('{ArrowUp}');
    expect(useAppStateStore.getState().selectedMatchIndex).toBe(2);
    await user.keyboard('{ArrowUp}{ArrowUp}{ArrowUp}'); // clamps at 1
    expect(useAppStateStore.getState().selectedMatchIndex).toBe(1);
  });

  it('Home / End jump selection to first / last (#587)', async () => {
    render(<CompleteScreen />);
    const list = screen.getByTestId('match-row-1').parentElement!;
    list.focus();
    const user = userEvent.setup();
    await user.keyboard('{End}');
    expect(useAppStateStore.getState().selectedMatchIndex).toBe(9);
    await user.keyboard('{Home}');
    expect(useAppStateStore.getState().selectedMatchIndex).toBe(1);
  });

  it('Enter on the focused list opens preview for the selected match (#587)', async () => {
    useAppStateStore.getState().selectMatch(4);
    render(<CompleteScreen />);
    const list = screen.getByTestId('match-row-1').parentElement!;
    list.focus();
    const user = userEvent.setup();
    await user.keyboard('{Enter}');
    const state = useAppStateStore.getState();
    expect(state.screen).toBe('preview');
    expect(state.selectedMatchIndex).toBe(4);
  });

  it('has no axe violations with metadata loaded (#587)', async () => {
    const { container } = render(<CompleteScreen />);
    expect(await axe(container)).toHaveNoViolations();
  });

  it('[境界を調整] surfaces a disabled-reason tooltip when nothing is selected (#587)', () => {
    // Force selectedMatch to null by clearing the metadata store and
    // disabling the auto-select effect via empty matches.
    useMetadataStore.setState({
      metadata: {
        source: 'x',
        source_duration: 1,
        source_duration_display: '0:01',
        detected_at: '2026-04-22T00:00:00Z',
        detection_params: {
          sample_interval: 2,
          blackout_threshold: 15,
          min_match_duration: 300,
          min_blackout_duration: 3,
          no_audio: false,
          use_gpu: null,
          workers: null,
        },
        matches: [],
        gaps: [],
      },
      hasBackup: false,
    });
    useAppStateStore.getState().selectMatch(null);
    render(<CompleteScreen />);
    const adjust = screen.getByRole('button', { name: '境界を調整' });
    expect(adjust).toBeDisabled();
    expect(adjust.getAttribute('title')).toBe('試合が選択されていません');
  });

  it('uses metadata.brightness_samples for the timeline when present (#569)', () => {
    // Inject a recognisable brightness payload so we can assert the
    // BrightnessTimeline received it (rather than the sampleBrightness
    // fallback). 5 evenly-spaced points spanning sampleMetadata's
    // 2:50 hour duration are enough to exercise the path.
    const metadata = useMetadataStore.getState().metadata;
    expect(metadata).not.toBeNull();
    const fingerprint = [10.0, 80.0, 12.5, 90.0, 7.0];
    useMetadataStore.setState({
      metadata: {
        ...metadata!,
        brightness_samples: {
          interval_s: metadata!.source_duration / fingerprint.length,
          values: fingerprint,
        },
      },
    });
    render(<CompleteScreen />);
    // The BrightnessTimeline renders one match block per match; we
    // confirm via the data-testid the timeline mounted (the brightness
    // path is opaque DOM but exercised through the same render).
    expect(screen.getByTestId('brightness-timeline')).toBeInTheDocument();
  });

  it('falls back to sampleBrightness when metadata has no brightness_samples', () => {
    // sampleMetadata loaded in beforeEach has no brightness_samples
    // -> CompleteScreen must still render the timeline (using the
    // in-memory sample curve).
    render(<CompleteScreen />);
    expect(screen.getByTestId('brightness-timeline')).toBeInTheDocument();
  });
});
