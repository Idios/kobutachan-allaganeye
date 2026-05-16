// Actual metadata.json content from output/metadata.json (9 matches, 2:50:28 source)
window.AE_META = {
  "source": "2026-04-08 21-14-05.mkv",
  "source_duration": 10228.735,
  "source_duration_display": "2:50:28",
  "detected_at": "2026-04-19T12:34:56Z",
  "detection_params": {
    "sample_interval": 2.0,
    "blackout_threshold": 15.0,
    "min_match_duration": 300.0,
    "min_blackout_duration": 3.0,
    "no_audio": false,
    "use_gpu": null,
    "workers": null
  },
  "matches": [
    { "index": 1, "start_time": 0.0,    "end_time": 915.5,    "start_display": "00:00", "end_display": "15:15",   "duration": 915.5,    "duration_display": "15m15s", "type": "unknown",  "output_file": "output/match_001.mp4" },
    { "index": 2, "start_time": 1129.5, "end_time": 2089.375, "start_display": "18:49", "end_display": "34:49",   "duration": 959.875,  "duration_display": "15m59s", "type": "fl_match", "output_file": "output/match_002.mp4" },
    { "index": 3, "start_time": 2089.375,"end_time": 2438.75, "start_display": "34:49", "end_display": "40:38",   "duration": 349.375,  "duration_display": "5m49s",  "type": "fl_match", "output_file": "output/match_003.mp4" },
    { "index": 4, "start_time": 2438.75,"end_time": 5021.25,  "start_display": "40:38", "end_display": "1:23:41", "duration": 2582.5,   "duration_display": "43m02s", "type": "fl_match", "output_file": "output/match_004.mp4" },
    { "index": 5, "start_time": 5021.5, "end_time": 5910.0,   "start_display": "1:23:41","end_display": "1:38:30","duration": 888.5,   "duration_display": "14m48s", "type": "fl_match", "output_file": "output/match_005.mp4" },
    { "index": 6, "start_time": 6037.25,"end_time": 7105.5,   "start_display": "1:40:37","end_display": "1:58:25","duration": 1068.25, "duration_display": "17m48s", "type": "fl_match", "output_file": "output/match_006.mp4" },
    { "index": 7, "start_time": 7186.5, "end_time": 8172.0,   "start_display": "1:59:46","end_display": "2:16:12","duration": 985.5,   "duration_display": "16m25s", "type": "fl_match", "output_file": "output/match_007.mp4" },
    { "index": 8, "start_time": 8179.5, "end_time": 9205.875, "start_display": "2:16:19","end_display": "2:33:25","duration": 1026.375,"duration_display": "17m06s", "type": "fl_match", "output_file": "output/match_008.mp4" },
    { "index": 9, "start_time": 9315.5, "end_time": 10228.735,"start_display": "2:35:15","end_display": "2:50:28","duration": 913.235, "duration_display": "15m13s", "type": "unknown",  "output_file": "output/match_009.mp4" }
  ],
  "gaps": []
};

// Pre-computed brightness signal (for timeline viz) — synthetic but plausible
// For a 2:50:28 recording with 9 matches. 512 samples across full duration.
(function generateBrightness() {
  const DUR = 10228.735;
  const N = 512;
  const matches = window.AE_META.matches;
  const samples = [];
  for (let i = 0; i < N; i++) {
    const t = (i / (N - 1)) * DUR;
    // Default: "in match" brightness 70-120 with noise
    let b = 85 + Math.sin(t * 0.003) * 15 + Math.sin(t * 0.011) * 8 + (Math.random() - 0.5) * 18;
    // Check if we're in a blackout (between matches)
    let inMatch = false;
    for (const m of matches) {
      if (t >= m.start_time && t <= m.end_time) { inMatch = true; break; }
    }
    if (!inMatch) {
      // Blackout region — very low brightness
      b = 6 + Math.random() * 8;
    }
    // Boundary transitions — dip briefly
    for (const m of matches) {
      const d1 = Math.abs(t - m.start_time);
      const d2 = Math.abs(t - m.end_time);
      if (d1 < 15 || d2 < 15) b = Math.min(b, 20 + Math.random() * 30);
    }
    samples.push(Math.max(0, Math.min(255, b)));
  }
  window.AE_BRIGHTNESS = samples;
})();
