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
