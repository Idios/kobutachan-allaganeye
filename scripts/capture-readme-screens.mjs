// One-shot screenshot capture for README's "5 つの観測フェーズ" section.
//
// Drives the vite dev build (port 1420) headless via Playwright. For each
// phase, navigates via the Zustand stores exposed during dev, captures a
// PNG, and writes it to image/0N-name.png.
//
// Run from worktree root with vite dev already up:
//   node scripts/capture-readme-screens.mjs

import { chromium } from 'playwright';
import { writeFileSync, mkdirSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..');
const IMAGE_DIR = resolve(ROOT, 'image');
mkdirSync(IMAGE_DIR, { recursive: true });

const VITE_URL = 'http://127.0.0.1:1420/';
const VIEWPORT = { width: 1600, height: 1000 };

// Inline replica of @tauri-apps/api/mocks (mockIPC + mockWindows +
// mockConvertFileSrc). Must run in addInitScript BEFORE any React module
// loads, so we cannot import the helper module — install __TAURI_INTERNALS__
// directly.
const TAURI_INIT_SCRIPT = `
(() => {
  const callbacks = new Map();
  const listeners = new Map();
  window.__MOCK_LISTENERS__ = listeners;
  const handleCmd = (cmd, args) => {
    if (cmd === 'plugin:event|listen') {
      const list = listeners.get(args.event) || [];
      list.push(args.handler);
      listeners.set(args.event, list);
      return args.handler;
    }
    if (cmd === 'plugin:event|emit') return null;
    if (cmd === 'plugin:event|unlisten') return null;
    if (cmd === 'check_backup_exists') return false;
    if (cmd === 'get_metadata_mtime') return null;
    if (cmd === 'read_recent') return [];
    if (cmd === 'add_recent' || cmd === 'clear_recent') return null;
    if (cmd === 'select_h264_encoder_for_export') {
      return { encoder: 'libx264', vendor: null };
    }
    if (cmd === 'register_video') {
      return { url: 'about:blank', token: 'mock-token' };
    }
    if (cmd === 'generate_match_thumbnails') return [];
    if (cmd === 'probe_video') {
      return { width: 1920, height: 1080, fps: 60, codec: 'h264', duration_s: 10228 };
    }
    if (cmd === 'probe_environment_info') {
      return { os: 'windows', cpu: 'mock', gpu_vendors_available: [] };
    }
    if (cmd === 'is_process_running') return false;
    if (cmd === 'get_log_dir') return 'C:/mock/log';
    if (cmd === 'read_error_log_tail') return '';
    if (cmd === 'load_draft') return null;
    if (cmd === 'clear_draft' || cmd === 'save_draft') return null;
    if (cmd === 'force_exit_app' || cmd === 'kill_tracked_processes' ||
        cmd === 'open_folder_in_explorer') {
      return null;
    }
    // Long-running commands: leave pending forever so the UI sits in its
    // initial in-flight state.
    if (cmd === 'load_metadata' || cmd === 'apply_changes' ||
        cmd === 'restore_from_original' || cmd === 'export_match' ||
        cmd === 'start_detect') {
      return new Promise(() => {});
    }
    return null;
  };
  window.__TAURI_INTERNALS__ = {
    metadata: {
      currentWindow: { label: 'main' },
      currentWebview: { windowLabel: 'main', label: 'main' },
    },
    convertFileSrc: (filePath, protocol = 'asset') =>
      \`http://\${protocol}.localhost/\${encodeURIComponent(filePath)}\`,
    invoke: async (cmd, args) => handleCmd(cmd, args),
    transformCallback: (callback, once = false) => {
      const id = window.crypto.getRandomValues(new Uint32Array(1))[0];
      callbacks.set(id, (data) => {
        if (once) callbacks.delete(id);
        if (callback) callback(data);
      });
      return id;
    },
    unregisterCallback: (id) => callbacks.delete(id),
    runCallback: (id, data) => {
      const cb = callbacks.get(id);
      if (cb) cb(data);
    },
    callbacks,
    postMessage: () => {},
  };
  window.__TAURI_EVENT_PLUGIN_INTERNALS__ = {
    unregisterListener: (event, id) => callbacks.delete(id),
  };
  window.__TAURI__ = { event: { listen: async () => () => {} } };
})();
`;

// Sample mode helpers. Importing vite-served module URLs lets us reach the
// Zustand stores from page.evaluate. The /src/ path matches Vite's default
// devserver route mapping.
async function navigateTo(page, screen, { withSample = true, selectMatch = null } = {}) {
  await page.evaluate(
    async ({ screen, withSample, selectMatch }) => {
      const meta = await import('/src/state/metadataStore.ts');
      const app = await import('/src/state/appStateStore.ts');
      if (withSample) meta.useMetadataStore.getState().loadSample();
      if (selectMatch !== null) app.useAppStateStore.getState().selectMatch(selectMatch);
      app.useAppStateStore.getState().navigate(screen);
    },
    { screen, withSample, selectMatch }
  );
  // Allow React to flush and any css transitions to settle.
  await page.waitForTimeout(700);
}

async function hideDevSwitcher(page) {
  // The StateSwitcher floating pill is dev-only and not part of the final
  // product. Hide it for the screenshots so the README shows the real UI.
  await page.addStyleTag({
    content: `[aria-label="screen switcher (dev)"] { display: none !important; }`,
  });
}

async function capture(page, name) {
  const file = resolve(IMAGE_DIR, name);
  await page.screenshot({ path: file, fullPage: false });
  console.log(`  wrote ${file}`);
}

const browser = await chromium.launch();
try {
  const context = await browser.newContext({ viewport: VIEWPORT });
  await context.addInitScript(TAURI_INIT_SCRIPT);
  const page = await context.newPage();
  page.on('pageerror', (err) => console.warn('  pageerror:', err.message));
  page.on('console', (msg) => {
    if (msg.type() === 'error') console.warn('  console.error:', msg.text());
  });

  await page.goto(VITE_URL, { waitUntil: 'networkidle' });
  await page.waitForSelector('[aria-label="screen switcher (dev)"]', { timeout: 10_000 });
  await hideDevSwitcher(page);

  console.log('drop');
  await navigateTo(page, 'drop', { withSample: false });
  await capture(page, '01-drop.png');

  console.log('detecting');
  // For detecting we need a non-null selectedVideoPath so the
  // sample-fallback branch in DetectingScreen does NOT auto-redirect
  // us to "complete". invoke('start_detect') is pending-forever in the
  // mock, so the screen subscribes to 'detect-progress' events — we
  // then fire a synthetic sequence so the UI renders Detecting + Refining
  // progress bars, probe meta, and a log strip.
  await page.evaluate(async () => {
    const app = await import('/src/state/appStateStore.ts');
    app.useAppStateStore
      .getState()
      .setSelectedVideoPath('E:/videos/2026-04-08 21-14-05.mkv');
  });
  await navigateTo(page, 'detecting', { withSample: false });
  // Give DetectingScreen a moment to register its detect-progress listener.
  await page.waitForTimeout(300);
  await page.evaluate(() => {
    const internals = window.__TAURI_INTERNALS__;
    const listeners = window.__MOCK_LISTENERS__;
    if (!listeners || !listeners.has('detect-progress')) return;
    const fire = (payload) => {
      for (const id of listeners.get('detect-progress')) {
        internals.runCallback(id, { event: 'detect-progress', payload, id: 0 });
      }
    };
    fire({ phase: 'probing', meta: { width: 1920, height: 1080, fps: 60, codec: 'h264', duration_s: 10228.7 } });
    fire({ phase: 'scan', percent: 48.0, log: '[02:34] scan 1228 / 2557 (48.0%)' });
    fire({ phase: 'scan', percent: 64.0, log: '[03:02] scan 1636 / 2557 (64.0%)' });
    fire({ phase: 'scan', percent: 78.0, log: '[03:48] scan 1994 / 2557 (78.0%)' });
    fire({ phase: 'refine', percent: 12.0, log: '[04:12] refine 1 / 9' });
  });
  await page.waitForTimeout(400);
  await capture(page, '02-detecting.png');

  console.log('complete');
  await navigateTo(page, 'complete', { withSample: true });
  await capture(page, '03-complete.png');

  console.log('preview');
  await navigateTo(page, 'preview', { withSample: true, selectMatch: 4 });
  await capture(page, '04-preview.png');

  console.log('export');
  await navigateTo(page, 'export', { withSample: true });
  await capture(page, '05-export.png');

  console.log('done');
} finally {
  await browser.close();
}
