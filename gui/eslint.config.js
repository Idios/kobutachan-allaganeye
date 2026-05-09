import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import reactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';

// #643: Tauri 2 WebView2 disables window.confirm/alert/prompt as no-op.
// Generate identical messages for `no-restricted-globals` (bare global)
// and `no-restricted-properties` (`window.X` member access) from a single
// source so future updates to plugin-dialog suggestions or §1.3 reference
// don't drift across the 6 entries (3 globals × 2 rules).
const TAURI_DIALOG_RESTRICTIONS = [
  { name: 'confirm', suggestion: '`import { ask } from "@tauri-apps/plugin-dialog"`' },
  { name: 'alert', suggestion: '`import { message } from "@tauri-apps/plugin-dialog"`' },
  { name: 'prompt', suggestion: 'plugin-dialog equivalents' },
];

const tauriDialogMessage = ({ name, suggestion }) =>
  `Tauri 2 WebView2 disables window.${name}. Use ${suggestion} instead. See docs/ui-interaction-spec.md §1.3.`;

export default [
  {
    ignores: [
      'dist/',
      'src-tauri/target/',
      'node_modules/',
      '.vite/',
      // #612: generated from schemas/metadata.schema.json. Linting the
      // output is pointless because the generator owns formatting.
      'src/types/metadata.generated.ts',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: {
      globals: {
        ...globals.browser,
      },
    },
    plugins: { 'react-hooks': reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,

      // #643: Catch both bare global calls and `window.X` member access.
      // See docs/ui-interaction-spec.md §1.3.
      'no-restricted-globals': [
        'error',
        ...TAURI_DIALOG_RESTRICTIONS.map((r) => ({
          name: r.name,
          message: tauriDialogMessage(r),
        })),
      ],
      'no-restricted-properties': [
        'error',
        ...TAURI_DIALOG_RESTRICTIONS.map((r) => ({
          object: 'window',
          property: r.name,
          message: tauriDialogMessage(r),
        })),
      ],
    },
  },
  {
    // #612: codegen runner is a Node script (npm run generate-types /
    // CI gui-frontend job). Give it Node globals so `console` etc. are
    // recognised without a per-file eslint-env directive.
    files: ['scripts/**/*.{js,mjs}'],
    languageOptions: {
      globals: {
        ...globals.node,
      },
    },
  },
];
