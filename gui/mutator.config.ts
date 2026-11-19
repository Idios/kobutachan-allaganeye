// mutation testing の設定 (#1154、@mizchi/mutator)。
//
// 実行は `npm run test:mutation` (scripts/mutation.mjs)。初回は snapshot が
// 無いので全ソース、2 回目以降は snapshot を再利用して差分 (`--since`) だけを
// 回す。ここでは「何を mutant にするか」だけを決め、閾値は意図的に緩めている。
//
// - スコアは KPI にしない: equivalent mutant で 100% にはならないため、
//   `break` を外して品質ゲートにしない (生存は 1 件ずつ
//   「テストを足す / コードを消す / `npx mutator accept` で理由を残す」で決着)。
// - テストファイルと生成物は対象外: `metadata.generated.ts` は
//   `schemas/metadata.schema.json` からの生成物で、手で直す対象ではない。
import { defineConfig } from '@mizchi/mutator';

export default defineConfig({
  include: ['src/**/*.ts', 'src/**/*.tsx'],
  exclude: [
    'src/**/*.test.ts',
    'src/**/*.test.tsx',
    'src/**/*.spec.ts',
    'src/**/*.spec.tsx',
    'src/test-setup.ts',
    'src/types/metadata.generated.ts',
    'src/vite-env.d.ts',
  ],
  runner: 'vitest',
  // テスト設定は vite.config.ts の `test` 節にある (vitest.config.ts は無い)。
  vitestConfig: 'vite.config.ts',
  reporters: ['text'],
  // high / low は表示ラベルだけ。`break` は外す (quality gate にしない)。
  thresholds: { high: 80, low: 60, break: null },
  failOnSurvived: false,
});
