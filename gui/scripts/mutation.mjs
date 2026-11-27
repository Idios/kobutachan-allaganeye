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
//   npm run test:mutation -- --reporter simplify  # 見るだけ (台帳は更新しない)
//   MUTATION_FULL=1 npm run test:mutation         # marker があっても full
//   MUTATION_SINCE=origin/main npm run test:mutation  # 差分の基準を変える
//   npm run test:mutation -- --include 'src/utils/*.ts'  # 部分実行 (marker は触らない)
//
// 計測台帳 (`gui/mutation-baseline.json`) を更新してよいのは「全ソースを測った
// ことが確かな run」だけ。次のどれかに当たるときは台帳を書かない
// (codex review 2026-11-19 の P1 群はすべてこの 1 本の規則の穴だった):
//   - 部分実行 / 明示指定 (`--include` / `--since` / `--runner` など)
//   - `--reporter` 付きの差分 run (ゲートを挟まずに測るため)
//   - 変更ソースに survivor が残って `--fail-on-survived` で止まった run
//   - 差分の基準 (`--since`) が「前回の計測以降の変更」を網羅していない run
//
// Windows でも `npx` のシェル差異を踏まないよう、CLI の JS を node で直接起動する。
//
// wrapper 自身のメッセージは **stderr** に出す。stdout は `--reporter agent` の
// JSON など機械可読な出力に譲る (`> .mutator/agent.json` でそのまま保存できるように)。
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import {
  existsSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  readlinkSync,
  writeFileSync,
} from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const stateDir = join(root, '.mutator');
const markerPath = join(stateDir, 'full-run.json');
// コミットする台帳。CI はこれだけを見て「計測済みか」を判定する
// (`.mutator/` は gitignore された実行キャッシュなので CI には存在しない)。
const baselinePath = join(root, 'mutation-baseline.json');

// 差分の基準。既定は **前回の計測時点の commit** (台帳 / marker の `head`)。
// そこからの差分だけを測れば「前回の計測 + 今回の差分 = 全ソース計測済み」が
// 保たれるので、base が前進 (develop 取り込み) しても full を強いない。
// 上書きは MUTATION_SINCE で行う (値は `coverageOf()` が git で検証する)。
const DEFAULT_SINCE = 'origin/develop-0.4.0';
const requestedSince = process.env.MUTATION_SINCE ?? null;
let since = requestedSince ?? DEFAULT_SINCE;

const argv = process.argv.slice(2);
const forceFull = process.env.MUTATION_FULL === '1' || argv.includes('--full');

// wrapper が自分で組み立てる指定。利用者が渡しても二重に付けないよう取り除く。
// `--no-fail-on-survived` は差分モードのゲートを消せてしまうので受理しない
// (fail-closed)。
const MANAGED_FLAGS = new Set([
  '--fail-on-survived',
  '--no-fail-on-survived',
  '--include-test-changes',
]);
const requestedNoGate = argv.includes('--no-fail-on-survived');
const requestedGate = argv.includes('--fail-on-survived');
const passthrough = argv.filter((arg) => arg !== '--full' && !MANAGED_FLAGS.has(arg));

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
// .ts/.tsx (テスト含む。killer が変わるのも計測結果が変わる要因)。
//
// 設定は 2 種類に分ける。
//   CONFIG_FILES: 「何を測るか」、または**測った結果を変えうる**入力。変わったら
//                 **全ソースを測り直す** (marker を無効化する)。
//   INPUT_FILES:  計測結果を変えない記録物。`entries` にだけ入れて変更を検出し、
//                 次の差分 run で台帳を更新する (full run の 40 分超を強制しない)。
const CONFIG_FILES = [
  'mutator.config.ts',
  'vite.config.ts',
  'package.json',
  'package-lock.json',
  'tsconfig.json',
  // テストが読む入力 (生成型の元データ)。変わると zod / 型検査系テストの
  // kill 結果が変わりうるので full 側に入れる (codex review 2026-11-19 P2)。
  join('..', 'schemas', 'metadata.schema.json'),
];

//   - mutator.accepted.json: accept の追加は計測結果を変えない (判定の上書き)。
//     日常的に変わるので full を強制しない
//   - scripts/mutation.mjs: どの範囲を測るかの判定ロジック。差分範囲の妥当性は
//     `coverageOf()` が git で検証する
const INPUT_FILES = ['mutator.accepted.json', join('scripts', 'mutation.mjs')];

// CRLF を LF に正規化してハッシュする file (それ以外は byte のまま)。
const TEXT_FILE = /\.(ts|tsx|js|jsx|mjs|cjs|json|css|html|md|txt|yml|yaml|svg)$/;

function walkSources(dir, out) {
  if (!existsSync(dir)) return out;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === '.mutator') continue;
      walkSources(path, out);
    } else {
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
    // checkout の改行変換 (Windows CRLF / Linux LF) でハッシュが変わらないよう
    // テキストは LF に正規化してから食う。これがないと CI が常に STALE になる。
    // テキスト判定を拡張子で行うのは、バイナリを UTF-8 に変換すると
    // 不正バイトが U+FFFD に潰れて別内容が同じハッシュになるため (codex review
    // 2026-11-19 P2)。
    const raw = readFileSync(path);
    // symlink は **リンク文字列** をハッシュする。リンク先の内容を読むと、git から
    // 見て無変更なのにハッシュが変わる (dirty 判定と commit 同定の穴になる。
    // codex review 2026-11-19 P2)。
    const isLink = lstatSync(path).isSymbolicLink();
    const bytes = isLink ? Buffer.from(readlinkSync(path), 'utf-8') : raw;
    const content =
      !isLink && TEXT_FILE.test(path)
        ? Buffer.from(bytes.toString('utf-8').replace(/\r\n/g, '\n'), 'utf-8')
        : bytes;
    const digest = createHash('sha256').update(content).digest('hex');
    entries.push({ path: rel, sha256: digest });
    hash.update(rel).update('\0').update(digest).update('\n');
  }
  return { hash: hash.digest('hex'), entries };
}

function currentSources() {
  // mutation の対象 (.ts/.tsx) と、freshness の追跡対象 (src 配下の全 file) を
  // 分ける。テストが直接読む file (CSS / JSON fixture 等) も追跡しないと、
  // それを変えただけで `FRESH` を返してしまう (codex review 2026-11-19 P2)。
  const trackedSrc = walkSources(join(root, 'src'), []);
  const sourceFiles = trackedSrc.filter((path) => /\.(ts|tsx)$/.test(path));
  const existing = (names) =>
    names.map((name) => join(root, name)).filter((path) => existsSync(path));
  const sources = hashFiles(sourceFiles);
  // `entries` は src 全部 + 設定 + 入力。どれが変わったかを `--status` で
  // 1 file 単位に出すため。`config.hash` は CONFIG_FILES だけを対象にする
  // (marker の有効性判定用)。
  const tracked = hashFiles([...trackedSrc, ...existing(CONFIG_FILES), ...existing(INPUT_FILES)]);
  return {
    sources: { count: sources.entries.length, hash: sources.hash },
    config: { hash: hashFiles(existing(CONFIG_FILES)).hash },
    entries: tracked.entries,
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

/**
 * marker の中身を検証する。**存在チェックだけでは不十分** (codex review
 * 2026-11-19 P1): 壊れた / 旧形式の marker を掴むと「全ソースを測っていない」
 * のに差分モードに入り、未計測のまま台帳を書いてしまう。
 */
function isValidMarker(marker) {
  if (marker === null || typeof marker !== 'object') return false;
  if (!Number.isInteger(marker.version) || marker.version < 2) return false;
  if (typeof marker.completedAt !== 'string') return false;
  if (!marker.sources || !Number.isInteger(marker.sources.count)) return false;
  if (typeof marker.sources.hash !== 'string') return false;
  if (!marker.config || typeof marker.config.hash !== 'string') return false;
  if (!Array.isArray(marker.entries)) return false;
  return marker.entries.every(
    (entry) =>
      entry !== null &&
      typeof entry === 'object' &&
      typeof entry.path === 'string' &&
      typeof entry.sha256 === 'string',
  );
}

function readBaseline() {
  if (!existsSync(baselinePath)) return null;
  try {
    return JSON.parse(readFileSync(baselinePath, 'utf-8'));
  } catch {
    return null;
  }
}

/** 台帳の形式。entries の構成 (設定 / 入力も含む) を変えたら bump する。 */
const LEDGER_SCHEMA_VERSION = 2;

/**
 * `base` (git ref) の差分に含まれるファイルを集める。git が使えない / ref が
 * 解決できないときは null。未追跡ファイルを含めるのは mutator の `--since` と
 * 揃えるため (mutator は未追跡 file を丸ごと計測対象にする)。
 */
function changedSince(base) {
  const diff = spawnSync('git', ['diff', '--name-only', '--no-renames', '--relative', base, '--'], {
    cwd: root,
    encoding: 'utf-8',
  });
  if (diff.error || diff.status !== 0) return null;
  const files = new Set();
  const untracked = spawnSync('git', ['ls-files', '--others', '--exclude-standard'], {
    cwd: root,
    encoding: 'utf-8',
  });
  const text = `${diff.stdout}\n${untracked.status === 0 ? untracked.stdout : ''}`;
  for (const line of text.split('\n')) {
    const rel = line.trim();
    if (rel) files.add(rel.split(sep).join('/'));
  }
  return files;
}

/**
 * 計測対象に symlink が含まれるか。含まれると committed-state を保証できない
 * (git が管理するのはリンク文字列だけ、テストが読むのはリンク先の内容)。
 * この repo の `gui/src` に symlink は無いので、あれば台帳を書かずに止める
 * (codex review 2026-11-19 P2)。
 */
function hasSymlinkedInput(current) {
  return current.entries.some((entry) => {
    const full = join(root, entry.path);
    return existsSync(full) && lstatSync(full).isSymbolicLink();
  });
}

/**
 * 計測した内容を指す commit (HEAD)。計測対象に未コミットの変更があると null。
 *
 * 台帳は CI に対する証明なので、「ある commit の内容を測った」と言えるときだけ
 * 書く。dirty な tree を測った内容はどの commit にも存在せず、差分の基準にも
 * できない。さらに、「dirty で計測 → その変更を revert して別 hunk を編集」の
 * 順で進むと、revert した範囲が未計測のまま差分範囲外になる
 * (codex review 2026-11-19 P1)。
 *
 * 台帳 / marker 自身は計測対象ではないので、未コミットでも構わない (毎回
 * 「計測 → 台帳を commit」の順で回す通常運用が成り立つ)。
 */
function measurementHead(current) {
  const res = spawnSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf-8' });
  if (res.error || res.status !== 0) return null;
  const headSha = (res.stdout ?? '').trim();
  if (!/^[0-9a-f]{40}$/.test(headSha)) return null;
  const paths = current.entries.map((entry) => entry.path);
  // 追跡 file (index + working tree) の変更
  const diff = spawnSync('git', ['diff', '--quiet', 'HEAD', '--', ...paths], {
    cwd: root,
    encoding: 'utf-8',
  });
  if (diff.error || diff.status !== 0) return null;
  // 未追跡 / ignore された file も拾う (`--exclude-standard` を付けない)。
  // gitignore された file を計測対象に入れてしまうと、HEAD に含まれない内容を
  // 「HEAD を測った」と記録することになる (codex review 2026-11-19 P2)。
  // pathspec は entries に限るので node_modules 等は入らない。
  const others = spawnSync('git', ['ls-files', '--others', '--', ...paths], {
    cwd: root,
    encoding: 'utf-8',
  });
  if (others.error || others.status !== 0) return null;
  return others.stdout.trim() === '' ? headSha : null;
}

/** `base` が `ref` の祖先 (または同一) か。判定できなければ null。 */
function isAncestor(base, ref) {
  const res = spawnSync('git', ['merge-base', '--is-ancestor', base, ref], {
    cwd: root,
    encoding: 'utf-8',
  });
  if (res.error) return null;
  if (res.status === 0) return true;
  if (res.status === 1) return false;
  return null; // 128: ref が解決できない
}

/** `base` と HEAD の merge-base。求められなければ null。 */
function mergeBaseWithHead(base) {
  const res = spawnSync('git', ['merge-base', base, 'HEAD'], { cwd: root, encoding: 'utf-8' });
  if (res.error || res.status !== 0) return null;
  const sha = (res.stdout ?? '').trim();
  return /^[0-9a-f]{40}$/.test(sha) ? sha : null;
}

/** mutation の対象になる file (src 配下の .ts/.tsx)。 */
const MUTATABLE = /^src\/.*\.(ts|tsx)$/;

/**
 * `base` が「前回の計測以降に変わったソース」をすべて含むかを調べる。
 *
 * 差分 run の結果で台帳を書いてよいのは、この条件が成り立つときだけ
 * (codex review 2026-11-19 P1)。`MUTATION_SINCE=HEAD` のように狭すぎる基準を
 * 指定すると差分が空になり、未計測のまま台帳が全ファイル現行ハッシュで埋まる。
 *
 * 判定は 3 段。**mutator が `git diff <since>` ではなく
 * `git diff <merge-base(since, HEAD)>` で mutant を選ぶ**ことに合わせる:
 *   1) **履歴**: 前回計測の commit が今の HEAD の履歴にあるか。別ブランチ /
 *      別 worktree の台帳をコピーしてきた場合、その commit は HEAD の祖先ではなく、
 *      差分は fork 点から計算されるので「計測していない部分」が差分外に残る。
 *   2) **merge-base**: `merge-base(base, HEAD)` が前回計測の commit 以前か。
 *      それより新しいと、計測時点から merge-base までの変更が差分に入らない。
 *   3) **作業ツリー**: 前回計測から内容が変わった計測対象が全部差分に入るか。
 */
function coverageOf(base, previous, current) {
  if (!previous || !Array.isArray(previous.entries)) {
    return { ok: false, reason: '前回の計測記録 (台帳) がない' };
  }
  const measuredAt = previous.head;
  if (typeof measuredAt !== 'string' || measuredAt === '') {
    return {
      ok: false,
      reason: '前回の計測がどの commit で行われたか台帳に記録がない (当時のソースを特定できない)',
    };
  }
  const inHistory = isAncestor(measuredAt, 'HEAD');
  if (inHistory === null) {
    return {
      ok: false,
      reason: `前回計測 (${measuredAt.slice(0, 7)}) が HEAD の履歴にあるか判定できない`,
    };
  }
  if (!inHistory) {
    return {
      ok: false,
      reason: `前回計測 (${measuredAt.slice(0, 7)}) が HEAD の履歴にない (別ブランチ / 別 worktree の台帳?)`,
    };
  }
  const mergeBase = mergeBaseWithHead(base);
  if (mergeBase === null) {
    return { ok: false, reason: `\`${base}\` と HEAD の merge-base を求められない` };
  }
  const baseBehind = isAncestor(mergeBase, measuredAt);
  if (baseBehind !== true) {
    return {
      ok: false,
      reason: `\`${base}\` の差分は ${mergeBase.slice(0, 7)} からで、前回計測 (${measuredAt.slice(0, 7)}) より新しい区間を含まない`,
    };
  }
  const files = changedSince(mergeBase);
  if (files === null) {
    return { ok: false, reason: `\`${base}\` を git の ref として解決できない` };
  }
  const before = new Map(previous.entries.map((entry) => [entry.path, entry.sha256]));
  const changed = current.entries
    .filter((entry) => MUTATABLE.test(entry.path) && before.get(entry.path) !== entry.sha256)
    .map((entry) => entry.path);
  if (changed.length === 0) return { ok: true, reason: '前回の計測以降に変わったソースはない' };
  const missing = changed.filter((path) => !files.has(path));
  if (missing.length > 0) {
    return {
      ok: false,
      reason: `差分に含まれない変更が ${missing.length} 件ある (例: ${missing[0]})`,
    };
  }
  return { ok: true, reason: '' };
}

/** 台帳 (baseline) と現状を比べる。fresh なら再計測不要。 */
function freshness() {
  const baseline = readBaseline();
  if (baseline === null) {
    return {
      fresh: false,
      reason: 'gui/mutation-baseline.json がない (計測結果がコミットされていない)',
      changes: [],
    };
  }
  if (baseline.schemaVersion !== LEDGER_SCHEMA_VERSION) {
    return {
      fresh: false,
      reason: `台帳の形式が想定外 (schemaVersion ${JSON.stringify(
        baseline.schemaVersion,
      )}、期待 ${LEDGER_SCHEMA_VERSION})`,
      changes: [],
      baseline,
    };
  }
  if (
    !baseline.sources ||
    !baseline.config ||
    typeof baseline.config.hash !== 'string' ||
    !Array.isArray(baseline.entries)
  ) {
    return {
      fresh: false,
      reason: 'baseline が旧形式 (計測対象のハッシュなし)',
      changes: [],
      baseline,
    };
  }
  // 計測時点の commit がなければ、次の差分の基準を検証できない。CI が green でも
  // 次の run が full に落ちるのは契約の不一致なので、ここで STALE にする
  // (codex review 2026-11-19 P2)。commit の存在までは見ない (shallow clone で
  // 落ちるため)。
  if (typeof baseline.head !== 'string' || !/^[0-9a-f]{40}$/.test(baseline.head)) {
    return {
      fresh: false,
      reason: '台帳に計測時点の commit (head) がない / 不正 (差分の基準を検証できない)',
      changes: [],
      baseline,
    };
  }
  const current = currentSources();
  if (baseline.config.hash !== current.config.hash) {
    return {
      fresh: false,
      reason: 'ランナー / 設定 / 依存が変わった (config を変えると計測対象が変わる)',
      changes: [],
      baseline,
    };
  }
  const previous = new Map(baseline.entries.map((entry) => [entry.path, entry.sha256]));
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
    baseline,
  };
}

function printStatus() {
  const state = freshness();
  const baseline = state.baseline ?? readBaseline();
  if (baseline) {
    const full = baseline.fullRun;
    const totals = full
      ? ` / 全ソース ${full.mutants} mutants (${full.survived ?? '?'} survived)`
      : '';
    console.error(
      `[mutation] 計測済みの範囲: ${baseline.completedAt} (${String(baseline.head ?? '?').slice(0, 7)}) mode=${baseline.mode ?? 'full'} (status ${baseline.status}${totals})`,
    );
  }
  console.error(`[mutation] 判定: ${state.fresh ? 'FRESH' : 'STALE'} — ${state.reason}`);
  if (state.fresh) return 0;
  if (state.changes.length > 0) {
    for (const line of state.changes.slice(0, 40)) console.error(`  ${line}`);
    if (state.changes.length > 40) console.error(`  … ${state.changes.length - 40} more`);
  }
  console.error('[mutation] 次にやること: cd gui && npm run test:mutation');
  console.error(
    '  (差分だけ計測し、計測結果を gui/mutation-baseline.json に書き戻します。commit してください)',
  );
  console.error(
    '  (変更したソースに検出されない mutant が残っていると --fail-on-survived で止まり、台帳も更新されません)',
  );
  return 1;
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
// これらが付いた run は **台帳も marker も書かない** (そのまま mutator へ渡す)。
// `--time-budget` / `--mutants-per-line` / `--shard` を入れるのは重要: これらを
// 付けた full run は mutant を Pending のまま残すので、「全ソースを測った」
// 証拠にならない (codex review 2026-11-19 P1)。
// `--config-file` (制限が設定側に書かれうる) と `--root` (別 project を測る) は
// 実効スコープを argv から確定できないので、保守的に marker を書かない
// (codex review 2026-11-19 P2)。
// テストランナー / mutator 集合 / 計測粒度を差し替える指定も「何を測るか」を
// 変えるので同じ扱い (codex review 2026-11-19 P1)。
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
  '--runner',
  '--config',
  '--jest-config',
  '--playwright-config',
  '--exclude-mutator',
  '--plugin',
  '--scope',
  '--experimental-callgraph',
  '--full-dry-run',
  '--shared-cache',
  '--no-arid',
  '--arid-callee',
  '--no-weak-mutation',
  '--typecheck',
  '--no-typecheck',
  '--critical',
  '--threshold-break',
];
const scoped = partialFlags.some(hasFlag);

// 現状のハッシュは 1 回だけ取る (run 後に取り直すと「測った時点のソース」を
// 記録できない)。
const current = currentSources();
// 計測対象に未コミットの変更がないかは run の前に見る (30 分の full run を
// 回してから「証明できない」と分かるのを避ける)。
const measuredHead = measurementHead(current);
const ledger = readBaseline();
const markerState = readMarker();
const markerValid = isValidMarker(markerState);
// 設定 (ランナー / include scope / 依存 / テスト入力) が変わっていたら
// 差分では足りない。未計測 / 再計測が必要な file が増えるので full に戻す。
const configChanged = markerValid && markerState.config.hash !== current.config.hash;

// 差分の基準の既定値 = **前回の計測時点の commit** (台帳 > marker の順)。
// そこからの差分だけを測れば「前回の計測 + 今回の差分 = 全ソース計測済み」が
// 成り立つ。release base を基準にすると、base が前進 (develop の取り込み) した
// ときに「base の変更が差分に入らない」ため full が避けられない (codex review
// 2026-11-19 P1)。
const measuredAt =
  [ledger?.head, markerState?.head].find((head) => typeof head === 'string' && head !== '') ?? null;
const fallbackSince = measuredAt ?? DEFAULT_SINCE;
if (requestedSince === null) since = fallbackSince;
const previousState = ledger ?? markerState;

// 差分モードの条件を 1 か所で決める。台帳に「全ソース計測済み」と書けるのは
// 次のすべてを満たすときだけ:
//   a) 部分実行 / 明示指定ではない
//   b) この端末に **検証済みの**全ソース marker がある (壊れた marker を掴まない)
//   c) 計測対象を決める設定が変わっていない
//   d) 差分の基準 (`--since`) が前回の計測以降の変更を網羅している
//      (MUTATION_SINCE の狭すぎる基準を拒否する。codex review 2026-11-19 P1)
let diffMode = false;
let fallbackNotice = null;
let fullReason = null;
if (!scoped && !forceFull) {
  if (!markerValid) {
    fullReason = markerState === null ? null : 'marker が壊れている / 旧形式';
  } else if (configChanged) {
    fullReason = '設定 / 依存 / テスト入力が変わった (未計測の mutant が増えうる)';
  } else {
    const coverage = coverageOf(since, previousState, current);
    if (coverage.ok) {
      diffMode = true;
    } else if (requestedSince !== null && since !== fallbackSince) {
      // 明示された基準が使えない場合、前回計測時点で覆えるならそちらを使う
      // (いきなり 40 分超の全ソース run に落ちないように)。
      const fallback = coverageOf(fallbackSince, previousState, current);
      if (fallback.ok) {
        diffMode = true;
        fallbackNotice = `MUTATION_SINCE=${requestedSince} は計測範囲を網羅しないため ${fallbackSince.slice(0, 7)} (前回計測時点) を基準にします (${coverage.reason})`;
        since = fallbackSince;
      } else {
        fullReason = `差分の基準を決められない: ${fallback.reason}`;
      }
    } else {
      fullReason = `差分の基準が計測範囲を網羅しない: ${coverage.reason}`;
    }
  }
}

// 差分モードは **2 pass** 回す:
//   1) 変更したソースの殺し漏れをゲート: `--since <base> --fail-on-survived`
//      ここで survivor が残ると **完走扱いにせず台帳も書かない** ので、
//      kill / accept するまで CI も通らない。
//   2) 変更したテストがカバーする範囲も計測して台帳を更新:
//      `--since <base> --include-test-changes`
//      （1 pass だけで済ませるとテスト変更が 0 件になる。逆に pass 1 に
//        `--include-test-changes` を入れると、変えたテストが触る関数の
//        **既存** survivor までゲート対象になる。この repo では 125 件あり、
//        無関係なテスト編集を止めてしまう。ゲートは「今回変えたソース」に限定する）
//
// `--reporter` を明示されたら 1 pass で回す。`--reporter agent` は stdout に
// JSON を 1 つだけ吐く前提なので、2 pass にすると JSON が 2 つ並んで壊れる。
// ただし **ゲートなしで回る**ので、この run では台帳を書かない (書くと
// `--reporter` を付けるだけでゲートを迂回できてしまう。codex review 2026-11-19 P1)。
const reporterExplicit = hasFlag('--reporter');
const certifying = !informational && !scoped && !(diffMode && reporterExplicit);
const runs = diffMode
  ? reporterExplicit
    ? [['--since', since, '--include-test-changes']]
    : [
        ['--since', since, '--fail-on-survived'],
        ['--since', since, '--include-test-changes'],
      ]
  : [[...(requestedGate && !requestedNoGate ? ['--fail-on-survived'] : [])]];

if (informational) {
  console.error('[mutation] 引数を表示/検証するだけで実行しません');
} else if (scoped) {
  console.error('[mutation] 部分実行 / 明示指定: そのまま渡します (計測台帳は更新しません)');
} else if (forceFull) {
  console.error('[mutation] 全ソースを対象にします (MUTATION_FULL / --full)');
} else if (!markerValid) {
  console.error(
    markerState === null
      ? '[mutation] 初回実行: 全ソースを対象にします'
      : '[mutation] 全ソース run の記録 (.mutator/full-run.json) が壊れている / 旧形式なので、全ソースを対象にします',
  );
} else if (!diffMode) {
  console.error(`[mutation] 全ソースを対象にします — ${fullReason}`);
} else {
  if (fallbackNotice !== null) console.error(`[mutation] ${fallbackNotice}`);
  if (reporterExplicit) {
    console.error(
      `[mutation] 差分のみ (--reporter 明示、計測台帳は更新しません): --since ${since} --include-test-changes`,
    );
  } else {
    console.error(`[mutation] 差分のみ (2 pass): 1) --since ${since} --fail-on-survived`);
    console.error(`[mutation]                    2) --since ${since} --include-test-changes`);
  }
}
if (!informational && !scoped && diffMode && requestedNoGate) {
  console.error(
    '[mutation] 差分モードのゲート (--fail-on-survived) は無効化できません (--no-fail-on-survived は無視します)',
  );
}

// `--plan`: 実行せずに「どのモードで何を測るか」だけを表示する。
// モード判定 (marker 検証 / config 変更 / 差分基準の網羅性) のデバッグと、
// docs に載せる検証用 (gate の判定を実行せずに確かめられる)。
if (argv.includes('--plan')) {
  console.error(
    `[mutation] plan: mode=${diffMode ? 'incremental' : 'full'} certify=${certifying} since=${since} runs=${JSON.stringify(runs)}`,
  );
  process.exit(0);
}

// 台帳は「ある commit の内容を測った」証明なので、証明できない状態のままでは
// run する前に止める (30 分の full run を回してから諦めるのを避ける)。
if (certifying && hasSymlinkedInput(current)) {
  console.error(
    '[mutation] 計測対象に symlink が含まれるため、計測台帳を更新できません (リンク先の内容は git が管理しない)',
  );
  console.error('  symlink を実 file に置き換えるか、計測対象から外してください');
  process.exit(1);
}
if (certifying && measuredHead === null) {
  console.error(
    '[mutation] 計測対象に未コミットの変更があるため、計測しても台帳を更新できません。commit してから実行してください',
  );
  console.error(
    '  (台帳は CI に対する証明なので、commit された内容に対してだけ書きます。台帳自身は計測対象外なので未コミットで構いません)',
  );
  process.exit(1);
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

let status = 0;
let gateFailed = false;
for (const [index, extra] of runs.entries()) {
  const result = spawnSync(process.execPath, [cli, ...extra, ...passthrough], {
    cwd: root,
    stdio: 'inherit',
  });
  if (result.error) {
    console.error(`[mutation] 起動に失敗しました: ${result.error.message}`);
    process.exit(1);
  }
  status = result.status ?? 1;
  // 4 = mutant 無しでテストが落ちる / 1 = 設定不正: どちらの pass でも中断
  if (status === 1 || status === 4) break;
  // 1 pass 目 (変更ソースのゲート) が survivor で落ちたら 2 pass 目は回さない
  if (diffMode && index === 0 && status === 2) {
    gateFailed = true;
    break;
  }
}
// marker は **スコープ制限のない、完走した full run** でのみ書く。
// - 0 = ok / 2 = quality gate (survived / critical) は「完走」とみなす
// - 4 (mutant 無しでテストが落ちる) や 1 (設定不正) は書かない
// - `--time-budget` / `--mutants-per-line` / `--shard` 付きは Pending が残るので
//   書かない (書くと次の run が差分モードに入り、未計測のファイルが永久に
//   測られなくなる)。codex review 2026-11-19 P1。
// - `--help` / `--version` は何も測っていないので書かない (P2)。
// - 差分モードで 1 pass 目 (--fail-on-survived) が落ちた場合も書かない
//   (変更ソースに未トリアージの survivor が残っている = 計測完了ではない)。
const completed = (status === 0 || status === 2) && !gateFailed;

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
    return {
      mutants: total,
      killed: counts.Killed ?? 0,
      survived: counts.Survived ?? 0,
      ...counts,
    };
  } catch {
    return null;
  }
}

// 完走した run は **計測台帳 (`gui/mutation-baseline.json`)** を必ず更新する。
// 差分 run でも更新するのは、「前回の台帳 + 今回の差分 = 全ソース計測済み」が
// 成り立つため (cache は関数単位。docs/testing-guide.md 参照)。
// local の marker (`.mutator/full-run.json`) は **全ソース run のときだけ** 書く。
// これは「この端末の cache が全ソース分揃っている」の印で、差分の基準に使う。
//
// `certifying` が false の run (`--reporter` 付きの差分 / 部分実行 / 表示のみ)
// は台帳を書かない。ここを緩めると「ゲートを通らずに certified にする」
// 迂回路ができてしまう。
if (certifying && completed) {
  const thisRun = readTotals();
  const runMode = diffMode ? 'incremental' : 'full';
  // 完走の証拠を確かめる。snapshot が読めない / full run なのに Pending が残る
  // (config の timeBudget / mutantsPerLine 等で打ち切られた) なら台帳を書かない
  // (codex review 2026-11-19 P1)。config 側の制限は `configChanged` で full に
  // 戻るので、full run の Pending を見れば diff mode の汚染も防げる
  // (汚染された config は marker / 台帳に記録されないため、以後も full のまま)。
  const pending = thisRun?.Pending ?? 0;
  const incomplete =
    thisRun === null
      ? 'カバレッジ結果 (.mutator/snapshot.json) を読めない'
      : runMode === 'full' && pending > 0
        ? `全ソース run なのに Pending が ${pending} 件残った (config の timeBudget / mutantsPerLine 等の制限?)`
        : JSON.stringify(currentSources().entries) !== JSON.stringify(current.entries)
          ? '計測中に計測対象が変わった (run 開始時の内容を測っていない)'
          : null;
  const completedAt = new Date().toISOString();
  const previous = readBaseline();
  const previousFull = previous?.fullRun ?? null;
  // 台帳がまだ無い場合 (初回) は、この端末の全ソース marker の集計を引き継ぐ。
  const markerFull =
    markerState?.totals && markerState.sources && markerState.completedAt
      ? { completedAt: markerState.completedAt, ...markerState.totals }
      : null;
  // 集計値 (mutants / killed / survived) は **直近の全ソース run** のもの。
  // 差分 run の snapshot は「その run のスコープ」しか含まないので、
  // 集計を差分で上書きすると意味のない小さい数字になる。
  const fullRun =
    runMode === 'full' ? { completedAt, ...(thisRun ?? {}) } : (previousFull ?? markerFull ?? null);
  if (incomplete !== null) {
    console.error(`[mutation] 完走した証拠にならないため計測台帳は更新しません: ${incomplete}`);
  } else {
    try {
      writeFileSync(
        baselinePath,
        `${JSON.stringify(
          {
            schemaVersion: LEDGER_SCHEMA_VERSION,
            completedAt,
            // 計測時点の commit。差分の基準 (`--since`) がこの commit の祖先かを
            // `coverageOf()` が検証する (差分範囲の妥当性の根拠)。dirty な tree では
            // 台帳を書かないので、この commit の内容 = 計測した内容。
            head: measuredHead,
            mode: runMode,
            status,
            sources: current.sources,
            config: current.config,
            entries: current.entries,
            // 直近の全ソース計測の集計 (差分 run では前回の値を引き継ぐ)
            fullRun,
            // 差分 run のときは「どこから引き継いだか」を残す (監査用)。
            carriedFrom: runMode === 'incremental' ? (previous?.completedAt ?? null) : null,
          },
          null,
          2,
        )}\n`,
        'utf-8',
      );
      console.error(
        `[mutation] 計測台帳を更新しました (gui/mutation-baseline.json: mode=${runMode}, ${current.sources.count} files, sha256 ${current.sources.hash.slice(0, 12)}…)`,
      );
      console.error(
        '[mutation] このファイルを commit すると CI の mutation-baseline job が通ります',
      );
    } catch (error) {
      console.warn(`[mutation] 台帳を書けませんでした: ${error.message}`);
    }

    if (runMode === 'full') {
      try {
        mkdirSync(stateDir, { recursive: true });
        writeFileSync(
          markerPath,
          `${JSON.stringify(
            {
              // marker の形式。v2 で sources / config / entries / totals を追加した。
              version: 2,
              completedAt,
              head: measuredHead,
              status,
              totals: thisRun,
              sources: current.sources,
              config: current.config,
              entries: current.entries,
            },
            null,
            2,
          )}\n`,
          'utf-8',
        );
        console.error('[mutation] 全ソース run を記録しました (.mutator/full-run.json)');
      } catch (error) {
        console.warn(`[mutation] marker を書けませんでした: ${error.message}`);
      }
    }
  }
} else if (!informational && !(certifying && completed)) {
  if (gateFailed) {
    console.error(
      '[mutation] 変更したソースに検出されていない mutant が残っています (--fail-on-survived)。',
    );
    console.error(
      '  1) 詳細を見る: npx mutator --since ' + `${since} --reporter agent > .mutator/agent.json`,
    );
    console.error(
      '  2) トリアージ: テストを追加して殺す / デッドコードなら消す / equivalent なら accept',
    );
    console.error(
      '  3) もう一度 npm run test:mutation (通ると台帳が更新されます。skill `mutation-test-loop` も使えます)',
    );
  }
  if (diffMode && reporterExplicit) {
    console.error(
      '[mutation] --reporter 付きの差分 run はゲートを挟まないため、計測台帳を更新しません',
    );
    console.error(
      '  台帳を更新するには --reporter を外して npm run test:mutation を実行してください',
    );
  } else {
    console.error(
      '[mutation] 部分実行 / 未完走のため計測台帳は更新しません (完走するまで CI の mutation-baseline は red のまま)',
    );
  }
}

process.exit(status);
