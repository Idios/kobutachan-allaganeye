import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import reactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';

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

      // #643: Tauri 2 WebView2 disables window.confirm/alert/prompt as no-op.
      // Catch both bare global calls and `window.X` member access.
      // See docs/ui-interaction-spec.md §1.3.
      'no-restricted-globals': [
        'error',
        {
          name: 'confirm',
          message:
            'Tauri 2 WebView2 disables window.confirm. Use `import { ask } from "@tauri-apps/plugin-dialog"` instead. See docs/ui-interaction-spec.md §1.3.',
        },
        {
          name: 'alert',
          message:
            'Tauri 2 WebView2 disables window.alert. Use `import { message } from "@tauri-apps/plugin-dialog"` instead. See docs/ui-interaction-spec.md §1.3.',
        },
        {
          name: 'prompt',
          message:
            'Tauri 2 WebView2 disables window.prompt. Use plugin-dialog equivalents instead. See docs/ui-interaction-spec.md §1.3.',
        },
      ],
      'no-restricted-properties': [
        'error',
        {
          object: 'window',
          property: 'confirm',
          message:
            'Tauri 2 WebView2 disables window.confirm. Use `import { ask } from "@tauri-apps/plugin-dialog"` instead. See docs/ui-interaction-spec.md §1.3.',
        },
        {
          object: 'window',
          property: 'alert',
          message:
            'Tauri 2 WebView2 disables window.alert. Use `import { message } from "@tauri-apps/plugin-dialog"` instead. See docs/ui-interaction-spec.md §1.3.',
        },
        {
          object: 'window',
          property: 'prompt',
          message:
            'Tauri 2 WebView2 disables window.prompt. Use plugin-dialog equivalents instead. See docs/ui-interaction-spec.md §1.3.',
        },
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
