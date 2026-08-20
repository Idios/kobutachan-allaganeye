/// <reference types="vite/client" />

/**
 * gui/package.json の version を build 時に埋め込んだ定数 (#944 §D)。
 * 定義は `gui/vite.config.ts` の `define`。
 */
declare const __APP_VERSION__: string;
