#!/usr/bin/env node
// mutation testing の入口 (#1154)。
//
// **初回は全ソース、以後は差分だけ**。判定 (killed / survived) は関数単位で
// キャッシュされるので、変わっていないコードは再実行されない。
//
// 「全ソースを 1 回回した」ことは `.mutator/full-run.json` (marker) で管理する。
// snapshot の有無だけで判定しないのは、`--include` 付きの部分実行でも
// `.mutator/snapshot.json` が書かれるため (部分実行で差分モードに入ると、
// 未計測のファイルが永久に測られなくなる)。
//
// 使い方:
//   npm run test:mutation                         # 初回 full / 以後 diff
//   npm run test:mutation -- --reporter simplify  # 追加引数はそのまま渡す
//   MUTATION_FULL=1 npm run test:mutation         # marker があっても full
//   MUTATION_SINCE=origin/main npm run test:mutation  # 差分の基準を変える
//   npm run test:mutation -- --include 'src/utils/*.ts'  # 部分実行 (marker は触らない)
//
// Windows でも `npx` のシェル差異を踏まないよう、CLI の JS を node で直接起動する。
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const stateDir = join(root, '.mutator');
const markerPath = join(stateDir, 'full-run.json');

// 差分の基準。この repo の作業ブランチは release ごとに変わるので、
// 必要なら MUTATION_SINCE で上書きする (docs/testing-guide.md 参照)。
const since = process.env.MUTATION_SINCE ?? 'origin/develop-0.4.0';

const argv = process.argv.slice(2);
const forceFull = process.env.MUTATION_FULL === '1' || argv.includes('--full');
const passthrough = argv.filter((arg) => arg !== '--full');

const hasFlag = (name) =>
  passthrough.some((arg) => arg === name || arg.startsWith(`${name}=`));

// 実行しないコマンド (marker を書いてはいけない)。
const informational = ['--help', '-h', '--version', '-V'].some(hasFlag);

// 部分実行 / 明示的な差分指定。marker もモードも変えない (そのまま渡す)。
// `--time-budget` / `--mutants-per-line` / `--shard` を入れるのは重要: これらを
// 付けた full run は mutant を Pending のまま残すので、「全ソースを測った」
// 証拠にならない (codex review 2026-11-19 P1)。
const partialFlags = [
  '--include',
  '--exclude',
  '--only',
  '--since',
  '--time-budget',
  '--mutants-per-line',
  '--shard',
];
const scoped = partialFlags.some(hasFlag);

const hasFullRun = existsSync(markerPath);
const mode = scoped || forceFull || !hasFullRun ? [] : ['--since', since];

if (informational) {
  console.log('[mutation] 引数を表示/検証するだけで実行しません');
} else if (scoped || forceFull) {
  console.log(
    forceFull
      ? '[mutation] 全ソースを対象にします (MUTATION_FULL / --full)'
      : '[mutation] 部分実行 / 明示指定: そのまま渡します',
  );
} else if (hasFullRun) {
  console.log(`[mutation] 差分のみ: --since ${since}`);
} else {
  console.log('[mutation] 初回実行: 全ソースを対象にします');
}

const require = createRequire(import.meta.url);
let cli;
try {
  // `exports` がルートしか公開していないので、公開 entry から dist/cli.js を辿る。
  cli = join(dirname(require.resolve('@mizchi/mutator')), 'cli.js');
} catch {
  console.error(
    '[mutation] @mizchi/mutator が見つかりません。`cd gui && npm install` を実行してください。',
  );
  process.exit(1);
}

const result = spawnSync(process.execPath, [cli, ...mode, ...passthrough], {
  cwd: root,
  stdio: 'inherit',
});

if (result.error) {
  console.error(`[mutation] 起動に失敗しました: ${result.error.message}`);
  process.exit(1);
}

const status = result.status ?? 1;
// marker は **スコープ制限のない、完走した full run** でのみ書く。
// - 0 = ok / 2 = quality gate (survived / critical) は「完走」とみなす
// - 4 (mutant 無しでテストが落ちる) や 1 (設定不正) は書かない
// - `--time-budget` / `--mutants-per-line` / `--shard` 付きは Pending が残るので
//   書かない (書くと次の run が差分モードに入り、未計測のファイルが永久に
//   測られなくなる)。codex review 2026-11-19 P1。
// - `--help` / `--version` は何も測っていないので書かない (P2)。
const completed = status === 0 || status === 2;
if (!informational && !scoped && completed) {
  const head = spawnSync('git', ['rev-parse', 'HEAD'], {
    cwd: root,
    encoding: 'utf-8',
  });
  try {
    mkdirSync(stateDir, { recursive: true });
    writeFileSync(
      markerPath,
      `${JSON.stringify(
        {
          completedAt: new Date().toISOString(),
          head: (head.stdout ?? '').trim(),
          status,
        },
        null,
        2,
      )}\n`,
      'utf-8',
    );
    console.log('[mutation] 全ソースの初回実行を記録しました (.mutator/full-run.json)');
  } catch (error) {
    console.warn(`[mutation] marker を書けませんでした: ${error.message}`);
  }
} else if (!informational && (scoped || !completed)) {
  console.log(
    '[mutation] 部分実行 / 未完走のため marker は更新しません (次回も全ソースか、partial のまま)',
  );
}

process.exit(status);
