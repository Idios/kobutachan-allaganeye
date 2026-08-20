import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

const isDebug = !!process.env.TAURI_ENV_DEBUG;

// #944 §D: GUI にバージョン表示が 1 つも無く、ユーザーが自分の版を知る手段が
// なかった。package.json の version を build 時定数として露出する。
// package.json は `scripts/check_version_consistency.py` が他 5 ファイルとの
// 一致を CI で強制している SSoT なので、PR-D1 の bump に自動追従する。
const pkgVersion: string = JSON.parse(
  readFileSync(fileURLToPath(new URL('./package.json', import.meta.url)), 'utf-8'),
).version;

export default defineConfig({
  define: {
    __APP_VERSION__: JSON.stringify(pkgVersion),
  },
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    host: '127.0.0.1',
  },
  envPrefix: ['VITE_', 'TAURI_ENV_*'],
  build: {
    target: 'chrome120',
    minify: !isDebug,
    sourcemap: isDebug,
  },
  test: {
    environment: 'jsdom',
    globals: false,
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    setupFiles: ['./src/test-setup.ts'],
  },
});
