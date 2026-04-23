import type { Metadata } from '../types/metadata';

/**
 * TypeScript-typed sample metadata used as a stand-in until DropScreen is
 * hooked to real detect output. Sourced from docs/design/bundle/project/shared/metadata.js
 * (window.AE_META) -- 9 matches from a 2:50:28 recording.
 *
 * Phase 2 uses this via `useMetadataStore.loadSample()` when the dummy
 * detecting flow completes, so that the complete / preview / export screens
 * have data to display.
 *
 * #465: `source` points at the physical 2:50:28 recording kept on the
 * development machine (path from the ALLAGANEYE_AUDIO_TEST_VIDEO convention,
 * see docs/testing-guide.md). This lets `register_video` resolve a real
 * file so the preview screen's `<video>` tag actually plays during
 * `npm run tauri dev` smoke-tests. On machines without this path the
 * preview panes fall back to the "video file not found" banner, which is
 * the correct behaviour for that environment. Production builds do not
 * invoke `loadSample()`.
 */
export const sampleMetadata: Metadata = {
  schema_version: '1',
  source: 'E:/videos/2026-04-08 21-14-05.mkv',
  source_duration: 10228.735,
  source_duration_display: '2:50:28',
  detected_at: '2026-04-19T12:34:56Z',
  detection_params: {
    sample_interval: 2.0,
    blackout_threshold: 15.0,
    min_match_duration: 300.0,
    min_blackout_duration: 3.0,
    no_audio: false,
    use_gpu: null,
    workers: null,
  },
  matches: [
    {
      index: 1,
      start_time: 0.0,
      end_time: 915.5,
      start_display: '00:00',
      end_display: '15:15',
      duration: 915.5,
      duration_display: '15m15s',
      type: 'unknown',
      output_file: 'output/match_001.mp4',
    },
    {
      index: 2,
      start_time: 1129.5,
      end_time: 2089.375,
      start_display: '18:49',
      end_display: '34:49',
      duration: 959.875,
      duration_display: '15m59s',
      type: 'fl_match',
      output_file: 'output/match_002.mp4',
    },
    {
      index: 3,
      start_time: 2089.375,
      end_time: 2438.75,
      start_display: '34:49',
      end_display: '40:38',
      duration: 349.375,
      duration_display: '5m49s',
      type: 'fl_match',
      output_file: 'output/match_003.mp4',
    },
    {
      index: 4,
      start_time: 2438.75,
      end_time: 5021.25,
      start_display: '40:38',
      end_display: '1:23:41',
      duration: 2582.5,
      duration_display: '43m02s',
      type: 'fl_match',
      output_file: 'output/match_004.mp4',
    },
    {
      index: 5,
      start_time: 5021.5,
      end_time: 5910.0,
      start_display: '1:23:41',
      end_display: '1:38:30',
      duration: 888.5,
      duration_display: '14m48s',
      type: 'fl_match',
      output_file: 'output/match_005.mp4',
    },
    {
      index: 6,
      start_time: 6037.25,
      end_time: 7105.5,
      start_display: '1:40:37',
      end_display: '1:58:25',
      duration: 1068.25,
      duration_display: '17m48s',
      type: 'fl_match',
      output_file: 'output/match_006.mp4',
    },
    {
      index: 7,
      start_time: 7186.5,
      end_time: 8172.0,
      start_display: '1:59:46',
      end_display: '2:16:12',
      duration: 985.5,
      duration_display: '16m25s',
      type: 'fl_match',
      output_file: 'output/match_007.mp4',
    },
    {
      index: 8,
      start_time: 8179.5,
      end_time: 9205.875,
      start_display: '2:16:19',
      end_display: '2:33:25',
      duration: 1026.375,
      duration_display: '17m06s',
      type: 'fl_match',
      output_file: 'output/match_008.mp4',
    },
    {
      index: 9,
      start_time: 9315.5,
      end_time: 10228.735,
      start_display: '2:35:15',
      end_display: '2:50:28',
      duration: 913.235,
      duration_display: '15m13s',
      type: 'unknown',
      output_file: 'output/match_009.mp4',
    },
  ],
  gaps: [],
};

/**
 * Pre-computed brightness signal to feed BrightnessTimeline. 512 samples
 * spanning the 2:50:28 duration — in-match brightness sine-wobble, blackouts
 * near 0, and brief dips at match boundaries. Mirrors the IIFE at the
 * bottom of docs/design/bundle/project/shared/metadata.js.
 *
 * Deterministic (seeded) so tests / visuals are reproducible. See also
 * docs/design/README.md §データ契約.
 */
export function buildSampleBrightness(): number[] {
  const DUR = sampleMetadata.source_duration;
  const N = 512;
  // A tiny LCG so we don't depend on Math.random for repeatability.
  let seed = 1337;
  const rand = () => {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    return (seed & 0xffff) / 0x10000;
  };
  const samples: number[] = [];
  for (let i = 0; i < N; i++) {
    const t = (i / (N - 1)) * DUR;
    let b =
      85 +
      Math.sin(t * 0.003) * 15 +
      Math.sin(t * 0.011) * 8 +
      (rand() - 0.5) * 18;
    let inMatch = false;
    for (const m of sampleMetadata.matches) {
      if (t >= m.start_time && t <= m.end_time) {
        inMatch = true;
        break;
      }
    }
    if (!inMatch) b = 6 + rand() * 8;
    for (const m of sampleMetadata.matches) {
      const d1 = Math.abs(t - m.start_time);
      const d2 = Math.abs(t - m.end_time);
      if (d1 < 15 || d2 < 15) b = Math.min(b, 20 + rand() * 30);
    }
    samples.push(Math.max(0, Math.min(255, b)));
  }
  return samples;
}

/** Memoized brightness array so repeated access is O(1). */
let cachedBrightness: number[] | null = null;
export function sampleBrightness(): number[] {
  if (cachedBrightness === null) cachedBrightness = buildSampleBrightness();
  return cachedBrightness;
}
