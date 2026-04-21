import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const isDebug = !!process.env.TAURI_ENV_DEBUG;

export default defineConfig({
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
});
