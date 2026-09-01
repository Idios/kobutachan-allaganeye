import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { axe } from 'jest-axe';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn().mockResolvedValue(undefined),
}));

import { CompleteScreen, formatElapsed } from './CompleteScreen';
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

  // #814 (AC3) -- when load failed (metadata null + loadErrorState set), the
  // empty state shows the error instead of the generic "No metadata" line.
  it('shows the load error in the empty state instead of "No metadata" (#814)', () => {
    useMetadataStore.getState().clear();
    useMetadataStore.setState({
      loadErrorState: {
        message: 'metadata.json is corrupt',
        hint: 'rerun allaganeye split',
        code: 'parse.json_invalid',
      },
    });
    render(<CompleteScreen />);
    expect(screen.getByTestId('complete-load-error')).toBeInTheDocument();
    expect(screen.getByText(/metadata.json is corrupt/)).toBeInTheDocument();
    expect(
      screen.queryByText('No metadata. Run detect first.'),
    ).toBeNull();
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

  // #587: a11y polish (キーボードナビ / focus / axe / disabled tooltip)。
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

  // #586 Round 1: formatElapsed の defensive 分岐を直接検証。component
  // 結合テストは [3][4] で legacy fallback (undefined) をカバーしているが、
  // pure function として export されているため、不正 ISO 8601 / clock skew
  // も unit test レベルで保証する。
  describe('formatElapsed (pure function)', () => {
    it('returns "—" for unparseable ISO 8601 (NaN guard, started side)', () => {
      expect(formatElapsed('invalid-date', '2026-04-19T12:39:23Z')).toBe('—');
    });

    it('returns "—" for unparseable ISO 8601 (NaN guard, completed side)', () => {
      expect(formatElapsed('2026-04-19T12:34:56Z', 'not-a-date')).toBe('—');
    });

    it('returns "—" when completed_at < started_at (clock skew)', () => {
      expect(
        formatElapsed('2026-04-19T12:39:23Z', '2026-04-19T12:34:56Z'),
      ).toBe('—');
    });
  });

  // #588: BrightnessTimeline threshold が detection_params 連動。
  describe('BrightnessTimeline threshold wiring', () => {
    it('passes detection_params.blackout_threshold to BrightnessTimeline', () => {
      const meta = useMetadataStore.getState().metadata;
      if (!meta) throw new Error('expected sample metadata loaded');
      // 検知時に閾値 30 で再検知された metadata を再現。
      useMetadataStore.setState({
        metadata: {
          ...meta,
          detection_params: {
            ...meta.detection_params,
            blackout_threshold: 30,
          },
        },
      });
      render(<CompleteScreen />);
      // BrightnessTimeline は threshold ラベルを SVG <text> として描画する
      // ので、その内容を直接検査する (mock 不要)。
      const timeline = screen.getByTestId('brightness-timeline');
      expect(timeline.textContent).toMatch(/threshold=30/);
    });

    it('falls back to threshold=15 when detection_params is missing (legacy)', () => {
      const meta = useMetadataStore.getState().metadata;
      if (!meta) throw new Error('expected sample metadata loaded');
      // pre-#370 想定の legacy metadata を再現 (detection_params 無し)。
      // zod schema は required だが、in-memory state には defensive に
      // optional chaining + ?? 15 fallback を入れているので動作確認可能。
      const legacyMeta = { ...meta } as Partial<typeof meta>;
      delete legacyMeta.detection_params;
      useMetadataStore.setState({
        metadata: legacyMeta as typeof meta,
      });
      render(<CompleteScreen />);
      const timeline = screen.getByTestId('brightness-timeline');
      expect(timeline.textContent).toMatch(/threshold=15/);
    });
  });

  // #633: SampleModeBanner 統合。
  it('renders SampleModeBanner in sample mode', () => {
    useMetadataStore.getState().clear();
    useMetadataStore.getState().loadSample();
    render(<CompleteScreen />);
    expect(screen.getByText('サンプル動画です。実際の動画を選択すると保存できます。')).toBeInTheDocument();
  });

  it('does not render SampleModeBanner in real-file mode', () => {
    useMetadataStore.getState().clear();
    useMetadataStore.getState().loadSample();
    // override filePath to simulate real file mode (metadata still loaded but filePath !== null)
    useMetadataStore.setState({ filePath: '/some/path.mp4' });
    render(<CompleteScreen />);
    expect(screen.queryByText('サンプル動画です。実際の動画を選択すると保存できます。')).toBeNull();
  });

  // #569: brightness_samples 由来のタイムライン描画 / fallback。
  describe('brightness_samples integration', () => {
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
});

describe('#676 CompleteScreen topBar path display', () => {
  beforeEach(() => {
    useAppStateStore.getState().reset();
    useMetadataStore.getState().clear();
    useAppStateStore.getState().navigate('complete');
  });

  it('shows fileName primary and parentDir secondary with title (videoSource = selectedVideoPath)', async () => {
    const fullPath = 'E:\\videos\\20260116\\2026-01-16 21-14-05.mkv';
    useMetadataStore.setState({
      metadata: {
        source: 'C:\\different\\path.mkv',
        source_duration: 100,
        source_duration_display: '1:40',
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
    useAppStateStore.setState({ selectedVideoPath: fullPath });

    const { findByTestId } = render(<CompleteScreen />);

    const container = await findByTestId('complete-path');
    expect(container).toHaveAttribute('title', fullPath);
    expect(
      within(container).getByText('2026-01-16 21-14-05.mkv'),
    ).toBeInTheDocument();
    expect(
      within(container).getByText('E:\\videos\\20260116'),
    ).toBeInTheDocument();
  });

  it('falls back to metadata.source when selectedVideoPath is null (sample mode)', async () => {
    const metadataSource = 'C:\\sample\\demo.mkv';
    useMetadataStore.setState({
      metadata: {
        source: metadataSource,
        source_duration: 100,
        source_duration_display: '1:40',
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
    useAppStateStore.setState({ selectedVideoPath: null });

    const { findByTestId } = render(<CompleteScreen />);

    const container = await findByTestId('complete-path');
    expect(container).toHaveAttribute('title', metadataSource);
    expect(within(container).getByText('demo.mkv')).toBeInTheDocument();
    expect(within(container).getByText('C:\\sample')).toBeInTheDocument();
  });
});

// #893: minimap screen navigation from CompleteScreen.
describe('#893 CompleteScreen minimap entry', () => {
  beforeEach(() => {
    useAppStateStore.getState().reset();
    useMetadataStore.getState().clear();
    useMetadataStore.getState().loadSample();
    useAppStateStore.getState().navigate('complete');
  });

  it('navigates to minimap screen on ミニマップ切抜き click', async () => {
    render(<CompleteScreen />);
    const btn = screen.getByRole('button', { name: 'ミニマップ切抜き' });
    const user = userEvent.setup();
    await user.click(btn);
    expect(useAppStateStore.getState().screen).toBe('minimap');
  });

  it('ミニマップ切抜き button is disabled when matches is empty', () => {
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
    render(<CompleteScreen />);
    const btn = screen.getByRole('button', { name: 'ミニマップ切抜き' });
    expect(btn).toBeDisabled();
  });
});

// #805 Phase 1: post_match match no-crash guard.
// A metadata whose matches[] includes a post_match entry (output_file
// undefined, post_match: true) must load and render CompleteScreen without
// throwing. This test LOCKS the no-crash property so a future regression
// (e.g. a screen reading match.output_file with a non-null assertion) is
// caught immediately.
describe('#805 CompleteScreen post_match no-crash guard', () => {
  const baseMatch = {
    index: 1,
    start_time: 100,
    end_time: 1000,
    start_display: '01:40',
    end_display: '16:40',
    duration: 900,
    duration_display: '15m00s',
    type: 'fl_match' as const,
    output_file: 'match_001.mp4',
  };
  const postMatchEntry = {
    index: 2,
    start_time: 1000,
    end_time: 1120,
    start_display: '16:40',
    end_display: '18:40',
    duration: 120,
    duration_display: '2m00s',
    type: 'unknown' as const,
    // output_file deliberately absent -- post_match segment
    post_match: true as const,
  };
  const metaWithPostMatch = {
    source: 'C:\\videos\\rec.mkv',
    source_duration: 1200,
    source_duration_display: '20:00',
    detected_at: '2026-06-26T00:00:00Z',
    detection_params: {
      sample_interval: 2,
      blackout_threshold: 15,
      min_match_duration: 300,
      min_blackout_duration: 3,
      no_audio: false,
      use_gpu: null,
      workers: null,
    },
    matches: [baseMatch, postMatchEntry],
    gaps: [],
  };

  beforeEach(() => {
    useAppStateStore.getState().reset();
    useMetadataStore.getState().clear();
    useMetadataStore.setState({ metadata: metaWithPostMatch as never, hasBackup: false });
    useAppStateStore.getState().navigate('complete');
  });

  it('renders post_match match without crashing (no-crash lock #805)', () => {
    expect(() => render(<CompleteScreen />)).not.toThrow();
  });

  it('shows match count including post_match entry', () => {
    render(<CompleteScreen />);
    // 2 matches total (1 active + 1 post_match)
    const matchesValue = screen.getByText('試合数').nextSibling as HTMLElement;
    expect(matchesValue.textContent).toBe('2');
    // Both rows render
    expect(screen.getByTestId('match-row-1')).toBeInTheDocument();
    expect(screen.getByTestId('match-row-2')).toBeInTheDocument();
  });

  // Review P3-3: run the Phase 2 UI states (dimmed row + badge) through axe
  // once (docs/a11y-policy.md per-screen axe 方針)。
  it('has no axe violations with a post_match row (#805 Phase 2)', async () => {
    const { container } = render(<CompleteScreen />);
    expect(await axe(container)).toHaveNoViolations();
  });

  // #805 Phase 2: post_match rows are visually differentiated (badge + dimmed).
  it('marks the post_match row with 試合後 badge and data attribute (Phase 2)', () => {
    render(<CompleteScreen />);
    const row = screen.getByTestId('match-row-2');
    expect(row).toHaveAttribute('data-post-match', 'true');
    expect(within(row).getByText('試合後')).toBeInTheDocument();
    // review R2 #2: pin the dimming class so removing it fails the suite
    // (spec §8 deliverable "dimmed" would otherwise be a false-green).
    expect(row.className).toMatch(/listItemPostMatch/);
    const normalRow = screen.getByTestId('match-row-1');
    expect(normalRow).not.toHaveAttribute('data-post-match');
    expect(within(normalRow).queryByText('試合後')).toBeNull();
    expect(normalRow.className).not.toMatch(/listItemPostMatch/);
  });

  // #944 §D: 「試合数」(全件) と export 見出しの件数がずれて見える件の説明。
  it('shows the post_match breakdown next to 試合数 (#944)', () => {
    render(<CompleteScreen />);
    expect(screen.getByTestId('complete-post-match-note')).toHaveTextContent(
      'うち 1 件は試合後',
    );
  });

  // #944 §D: 試合後バッジに説明が無く、何を意味するか画面上から知れなかった。
  it('explains the 試合後 badge via a tooltip (#944)', () => {
    render(<CompleteScreen />);
    const badge = within(screen.getByTestId('match-row-2')).getByText('試合後');
    expect(badge).toHaveAttribute('title');
    expect(badge.getAttribute('title')).toMatch(/--keep-trailing/);
  });
});

// #944 §D: masked fallback は 0 暗転時に自動発火するが GUI へ何も伝えて
// いなかった (`masked_fallback_used` が schema にあるのに未描画)。
describe('#944 CompleteScreen masked fallback notice', () => {
  const match = {
    index: 1,
    start_time: 100,
    end_time: 1000,
    start_display: '01:40',
    end_display: '16:40',
    duration: 900,
    duration_display: '15m00s',
    type: 'fl_match' as const,
    output_file: 'match_001.mp4',
  };
  const baseParams = {
    sample_interval: 2,
    blackout_threshold: 15,
    min_match_duration: 300,
    min_blackout_duration: 3,
    no_audio: false,
    use_gpu: null,
    workers: null,
  };
  function metaWith(maskedFallbackUsed: boolean | undefined) {
    return {
      source: 'C:\\videos\\rec.mkv',
      source_duration: 1200,
      source_duration_display: '20:00',
      detected_at: '2026-06-26T00:00:00Z',
      detection_params:
        maskedFallbackUsed === undefined
          ? baseParams
          : { ...baseParams, masked_fallback_used: maskedFallbackUsed },
      matches: [match],
      gaps: [],
    };
  }

  function mount(maskedFallbackUsed: boolean | undefined) {
    useAppStateStore.getState().reset();
    useMetadataStore.getState().clear();
    useMetadataStore.setState({
      metadata: metaWith(maskedFallbackUsed) as never,
      hasBackup: false,
    });
    useAppStateStore.getState().navigate('complete');
    return render(<CompleteScreen />);
  }

  it('shows the notice when the masked fallback actually fired', () => {
    mount(true);
    expect(
      screen.getByTestId('complete-masked-fallback-notice'),
    ).toHaveTextContent('--masked');
  });

  it('stays silent when the fallback did not fire', () => {
    mount(false);
    expect(screen.queryByTestId('complete-masked-fallback-notice')).toBeNull();
  });

  it('stays silent on pre-#821 metadata that has no such field', () => {
    mount(undefined);
    expect(screen.queryByTestId('complete-masked-fallback-notice')).toBeNull();
  });
});
