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
import { createHash } from 'node:crypto';
import {
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  writeFileSync,
} from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join, relative, sep } from 'node:path';
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
  passthrough.some((arg) => arg === name || arg.startsWith(`${name}=`)) ||
  passthrough.includes(name);

// ── 「全ソースを測った」状態の管理 ───────────────────────────────────────────
// marker には実行時刻だけでなく**計測対象の内容ハッシュ**を残す。これで
//   npm run test:mutation:status
// が「今のソースは前回の full run で測ったものと同じか」を即答できる
// (ソースが変わらなければ測り直し不要、という運用の担保。
//  docs/testing-guide.md §GUI mutation testing)。
//
// ハッシュ対象は保守的に「mutation の対象になりうるもの全部」= src 配下の
// .ts/.tsx (テスト含む。killer が変わるのも計測結果が変わる要因) と、
// ランナー/設定 (config + vite + package)。設定が変わったら scope が
// 変わった可能性があるので **marker を無効化して full に戻す**。
const CONFIG_FILES = [
  'mutator.config.ts',
  'vite.config.ts',
  'package.json',
  'package-lock.json',
  'tsconfig.json',
];

function walkSources(dir, out) {
  if (!existsSync(dir)) return out;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === '.mutator') continue;
      walkSources(path, out);
    } else if (/\.(ts|tsx)$/.test(entry.name)) {
      out.push(path);
    }
  }
  return out;
}

function hashFiles(paths) {
  const hash = createHash('sha256');
  const entries = [];
  for (const path of [...paths].sort()) {
    const rel = relative(root, path).split(sep).join('/');
    const digest = createHash('sha256').update(readFileSync(path)).digest('hex');
    entries.push({ path: rel, sha256: digest });
    hash.update(rel).update('\0').update(digest).update('\n');
  }
  return { hash: hash.digest('hex'), entries };
}

function currentSources() {
  const sourceFiles = walkSources(join(root, 'src'), []);
  const configFiles = CONFIG_FILES.map((name) => join(root, name)).filter((p) =>
    existsSync(p),
  );
  const sources = hashFiles(sourceFiles);
  const config = hashFiles(configFiles);
  return {
    sources: { count: sources.entries.length, hash: sources.hash },
    config: { hash: config.hash },
    entries: sources.entries,
  };
}

function readMarker() {
  if (!existsSync(markerPath)) return null;
  try {
    return JSON.parse(readFileSync(markerPath, 'utf-8'));
  } catch {
    return null;
  }
}

/** marker と現状を比べる。fresh なら再実行不要。 */
function freshness() {
  const marker = readMarker();
  if (marker === null) {
    return { fresh: false, reason: 'marker がない (一度も全ソースを完走していない)', changes: [] };
  }
  if (!marker.sources || !marker.config) {
    return {
      fresh: false,
      reason: 'marker が旧形式 (計測対象のハッシュなし)。次回の full run で更新される',
      changes: [],
    };
  }
  const current = currentSources();
  if (marker.config.hash !== current.config.hash) {
    return {
      fresh: false,
      reason: 'ランナー / 設定 / 依存が変わった (config を変えると計測対象が変わる)',
      changes: [],
      marker,
    };
  }
  const previous = new Map(marker.entries.map((entry) => [entry.path, entry.sha256]));
  const changes = [];
  for (const entry of current.entries) {
    const before = previous.get(entry.path);
    if (before === undefined) changes.push(`A ${entry.path}`);
    else if (before !== entry.sha256) changes.push(`M ${entry.path}`);
  }
  for (const path of previous.keys()) {
    if (!current.entries.some((entry) => entry.path === path)) changes.push(`D ${path}`);
  }
  return {
    fresh: changes.length === 0,
    reason: changes.length === 0 ? '変更なし' : `${changes.length} ファイルが変わった`,
    changes,
    marker,
  };
}

function printStatus() {
  const state = freshness();
  const marker = readMarker();
  if (marker) {
    const totals = marker.totals ? ` / ${marker.totals.mutants} mutants` : '';
    console.log(`[mutation] 最後の全ソース計測: ${marker.completedAt} (status ${marker.status}${totals})`);
  }
  console.log(`[mutation] 判定: ${state.fresh ? 'FRESH' : 'STALE'} — ${state.reason}`);
  if (state.changes.length > 0) {
    for (const line of state.changes.slice(0, 40)) console.log(`  ${line}`);
    if (state.changes.length > 40) console.log(`  … ${state.changes.length - 40} more`);
    console.log('[mutation] 再計測: npm run test:mutation (差分のみ。キャッシュが効く)');
  }
  return state.fresh ? 0 : 1;
}

// `--status`: 計測をせずに「前回の全ソース計測が今のソースに対して有効か」だけを返す。
// fresh なら再実行不要 (exit 0) / stale なら再実行を促す (exit 1)。
if (argv.includes('--status')) {
  process.exit(printStatus());
}

// 実行しないコマンド (marker を書いてはいけない)。短縮形の version は `-v`
// (`-V` ではない。`mutator --help` の `-v, --version`)。
// 位置引数の subcommand (`init-skill` / `accept` / `select-tests`) も mutation を
// 実行しない (codex review 2026-11-19 P1)。
const SUBCOMMANDS = new Set(['init-skill', 'accept', 'select-tests']);
const positional = passthrough.find((arg) => !arg.startsWith('-'));
const informational =
  ['--help', '-h', '--version', '-v'].some(hasFlag) ||
  (positional !== undefined && SUBCOMMANDS.has(positional));

// 部分実行 / 明示的な差分指定 / 実効設定が argv から分からない指定。
// marker もモードも変えない (そのまま渡す)。
// `--time-budget` / `--mutants-per-line` / `--shard` を入れるのは重要: これらを
// 付けた full run は mutant を Pending のまま残すので、「全ソースを測った」
// 証拠にならない (codex review 2026-11-19 P1)。
// `--config-file` (制限が設定側に書かれうる) と `--root` (別 project を測る) は
// 実効スコープを argv から確定できないので、保守的に marker を書かない
// (codex review 2026-11-19 P2)。
const partialFlags = [
  '--include',
  '--exclude',
  '--only',
  '--since',
  '--time-budget',
  '--mutants-per-line',
  '--shard',
  '--root',
  '--config-file',
];
const scoped = partialFlags.some(hasFlag);

const hasFullRun = existsSync(markerPath);
const marker = readMarker();
// 設定 (ランナー / include scope / 依存) が変わっていたら差分では足りない。
// 未計測のファイルが増える可能性があるので full に戻す。
const configChanged =
  hasFullRun && marker?.config?.hash !== undefined
    ? marker.config.hash !== currentSources().config.hash
    : false;
const mode =
  scoped || forceFull || !hasFullRun || configChanged ? [] : ['--since', since];

if (informational) {
  console.log('[mutation] 引数を表示/検証するだけで実行しません');
} else if (scoped || forceFull) {
  console.log(
    forceFull
      ? '[mutation] 全ソースを対象にします (MUTATION_FULL / --full)'
      : '[mutation] 部分実行 / 明示指定: そのまま渡します',
  );
} else if (configChanged) {
  console.log(
    '[mutation] 設定 / 依存が変わったので全ソースを対象にします (計測対象が変わりうる)',
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

/** snapshot から mutant の内訳を読む (marker に残して status 表示に使う)。 */
function readTotals() {
  const snapshotPath = join(stateDir, 'snapshot.json');
  if (!existsSync(snapshotPath)) return null;
  try {
    const snapshot = JSON.parse(readFileSync(snapshotPath, 'utf-8'));
    const counts = {};
    for (const row of snapshot.rows ?? []) {
      const state = row[4];
      counts[state] = (counts[state] ?? 0) + 1;
    }
    const total = Object.values(counts).reduce((sum, n) => sum + n, 0);
    return { mutants: total, killed: counts.Killed ?? 0, survived: counts.Survived ?? 0, ...counts };
  } catch {
    return null;
  }
}

// `mode.length === 0` = この実行が **全ソース** を対象にしたことを意味する
// (marker があると自動で `--since` が入るので、差分 run で marker を
//  上書きしない。codex review 2026-11-19 P2)。
if (!informational && !scoped && mode.length === 0 && completed) {
  const head = spawnSync('git', ['rev-parse', 'HEAD'], {
    cwd: root,
    encoding: 'utf-8',
  });
  const current = currentSources();
  try {
    mkdirSync(stateDir, { recursive: true });
    writeFileSync(
      markerPath,
      `${JSON.stringify(
        {
          // marker の形式。v2 で sources / config / entries / totals を追加した。
          version: 2,
          completedAt: new Date().toISOString(),
          head: (head.stdout ?? '').trim(),
          status,
          totals: readTotals(),
          sources: current.sources,
          config: current.config,
          entries: current.entries,
        },
        null,
        2,
      )}\n`,
      'utf-8',
    );
    console.log(
      `[mutation] 全ソースの計測を記録しました (.mutator/full-run.json: ${current.sources.count} files, sha256 ${current.sources.hash.slice(0, 12)}…)`,
    );
    console.log('[mutation] 以後は `npm run test:mutation:status` で再実行の要否を確認できます');
  } catch (error) {
    console.warn(`[mutation] marker を書けませんでした: ${error.message}`);
  }
} else if (!informational && (scoped || !completed)) {
  console.log(
    '[mutation] 部分実行 / 未完走のため marker は更新しません (次回も全ソースか、partial のまま)',
  );
}

process.exit(status);
