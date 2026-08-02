import { readdirSync, readFileSync } from 'node:fs';
import { join, relative } from 'node:path';

import { describe, expect, it } from 'vitest';

/**
 * #932: 未定義の `--ae-*` custom property を参照していないかの構造的 guard。
 *
 * 未定義 custom property を **fallback なし** で参照すると、その宣言は
 * invalid-at-computed-value-time となり `unset` に計算される。`color` の
 * ような継承プロパティでは `inherit` 相当になり、しかも inline style は
 * cascade で class に勝つため「class 側の色ごと消える」。
 * ExportScreen の GPU fallback 通知が存在しない token を参照していて
 * v0.2.0 から地の文と同じ色で描画されていたのがこれ (MinimapScreen は
 * mirror 時にその欠陥ごと複製した)。
 *
 * fallback 付きの参照は描画自体はされるが、tokens.css のテーマから外れた色が
 * silent に紛れ込むので同じく違反扱いにする。
 *
 * ## 設計方針: 徹底して fail closed
 *
 * guard の誤検知 (安全側) より見逃し (危険側) を潰す。Codex
 * adversarial-review が 2 周で 2 本の false-green 経路を出したため、
 * 「賢く除外する」機構を持たない方向に倒してある。
 *
 * 1. **コメントを除去しない**。正規表現でのコメント除去は「文字列リテラル中の
 *    `/x` と後続コメントの `x/` に挟まれた実コードごと空白化する」経路があり、
 *    live な inline style が走査から消えても他ファイルの参照で件数 assert は
 *    満たされてしまう。結果として **コメントに `var(...)` 形で未定義 token を
 *    書くとこのテストが落ちる**。経緯説明でトークン名に言及したいときは
 *    `--ae-accent` のように bare で書くこと。
 * 2. **token 名を区切り文字まで丸ごと捕らえる**。`--ae-[a-z0-9-]+` で切ると
 *    `var(--ae-goldBright)` が定義済みの `--ae-gold` として記録され guard が
 *    緑のまま通る。捕らえた名前が命名規約 (小文字 + ハイフン) から外れていれば
 *    定義の有無を見るまでもなく違反とする。
 * 3. **行単位ではなく全文を走査する**。`var(` と token 名が改行で分かれた
 *    CSS を取りこぼさないため。
 */

// environment: 'jsdom' では `import.meta.url` が http URL になり
// fileURLToPath が使えないため、vitest の cwd (= gui/) 起点で解決する。
const SRC_DIR = join(process.cwd(), 'src');
const TOKENS_CSS = join(SRC_DIR, 'styles', 'tokens.css');

/**
 * `var(` に続く custom property 名を区切り (空白 / `,` / `)`) まで捕らえる。
 *
 * 毎回 `new RegExp` するのは `g` フラグ付き正規表現を module scope で使い回す
 * ときの `lastIndex` 依存を避けるため。
 */
const VAR_REFERENCE = String.raw`var\(\s*(--ae-[^\s,)]*)`;

/** tokens.css の定義行から名前を捕らえる (こちらも途中で切らない)。 */
const TOKEN_DEFINITION = String.raw`^[ \t]*(--ae-[^\s:;{}]*)[ \t]*:`;

/** 命名規約: 小文字英数をハイフンで繋いだ形のみ。 */
const CONVENTIONAL_NAME = /^--ae-[a-z0-9]+(?:-[a-z0-9]+)*$/;

/** tokens.css の `--ae-foo: ...;` 定義行から token 名を集める。 */
function definedTokens(): Set<string> {
  const css = readFileSync(TOKENS_CSS, 'utf8');
  const names = new Set<string>();
  for (const m of css.matchAll(new RegExp(TOKEN_DEFINITION, 'gm'))) {
    names.add(m[1]);
  }
  return names;
}

/** src/ 配下の実装ファイル (テストを除く) を列挙する。 */
function sourceFiles(dir: string, acc: string[] = []): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      sourceFiles(full, acc);
    } else if (
      /\.(css|ts|tsx)$/.test(entry.name) &&
      !/\.(test|spec)\.tsx?$/.test(entry.name)
    ) {
      acc.push(full);
    }
  }
  return acc;
}

interface Usage {
  token: string;
  location: string;
}

/**
 * テキスト中の `var(--ae-*)` 参照を行番号付きで集める。
 *
 * 構文解析は行わない (前述のとおり意図的に fail closed)。行番号は `var(` では
 * なく **token 名の開始位置** を指す (改行を挟む書き方でも読み手が追える)。
 */
function scanText(text: string, label: string): Usage[] {
  const usages: Usage[] = [];
  for (const m of text.matchAll(new RegExp(VAR_REFERENCE, 'g'))) {
    const tokenStart = (m.index ?? 0) + m[0].length - m[1].length;
    const line = text.slice(0, tokenStart).split('\n').length;
    usages.push({ token: m[1], location: `${label}:${line}` });
  }
  return usages;
}

/** src/ 実装ファイル中の `var(--ae-*)` 参照を集める。 */
function collectUsages(): Usage[] {
  const usages: Usage[] = [];
  for (const file of sourceFiles(SRC_DIR)) {
    const rel = relative(SRC_DIR, file).replace(/\\/g, '/');
    usages.push(...scanText(readFileSync(file, 'utf8'), rel));
  }
  return usages;
}

/** 命名規約から外れた名前、または tokens.css に定義がない名前を違反とする。 */
function violationsIn(usages: Usage[], defined: Set<string>): string[] {
  return usages
    .filter((u) => !CONVENTIONAL_NAME.test(u.token) || !defined.has(u.token))
    .map((u) => `${u.token}  ${u.location}`);
}

describe('#932 --ae-* CSS custom property の定義漏れ guard', () => {
  it('tokens.css から token 定義を読めている (guard 自体の健全性)', () => {
    const defined = definedTokens();
    // sentinel: よく使う token が拾えていなければ正規表現側の壊れを疑う
    expect(defined.has('--ae-gold')).toBe(true);
    expect(defined.has('--ae-danger')).toBe(true);
    expect(defined.size).toBeGreaterThan(20);
  });

  it('src/ の実装ファイルを走査できている (guard 自体の健全性)', () => {
    const files = sourceFiles(SRC_DIR);
    expect(files.length).toBeGreaterThan(30);
    // src/ 配下の拡張子は ts / tsx / css の 3 種のみ = 全て走査対象
    const extensions = new Set(files.map((f) => f.replace(/^.*\./, '')));
    expect([...extensions].sort()).toEqual(['css', 'ts', 'tsx']);
    // inline style / CSS Module 双方が走査対象に入っていること
    expect(files.some((f) => f.endsWith('ExportScreen.tsx'))).toBe(true);
    expect(files.some((f) => f.endsWith('MinimapScreen.module.css'))).toBe(true);
  });

  it('実参照を取りこぼしていない (guard 無音化の検出)', () => {
    const usages = collectUsages();
    // 走査が壊れて常に violations 0 になる false green をここで落とす
    expect(usages.length).toBeGreaterThan(100);
    // CSS Module / inline style の両系統が実際に拾えていること
    expect(
      usages.some(
        (u) =>
          u.token === '--ae-danger' &&
          u.location.startsWith('screens/ExportScreen.module.css:'),
      ),
    ).toBe(true);
    expect(
      usages.some(
        (u) =>
          u.token === '--ae-gold-bright' &&
          u.location.startsWith('screens/MinimapScreen.tsx:'),
      ),
    ).toBe(true);
  });

  it('コメント風の綴りで走査を回避できない (fail closed)', () => {
    // Codex adversarial-review round 1 が指摘した回避経路の regression fixture:
    // 文字列リテラル中の `/*` と後続コメントの `*/` に挟まれた実参照。
    // コメント除去を挟む実装ではこの区間ごと空白化され、live な inline style が
    // 走査から消えていた。
    const sample = [
      "const glyph = '/*';",
      "const style = { color: 'var(--ae-missing)' };",
      '/* 経緯: 昔は var(--ae-legacy) だった */',
      'a { color: var(--ae-gold); }',
    ].join('\n');

    const usages = scanText(sample, 'fixture');
    expect(usages).toEqual([
      // 文字列リテラル中の `/*` に続く実参照が生き残ること (無音化の否定)
      { token: '--ae-missing', location: 'fixture:2' },
      // コメント中の参照も数える = fail closed (見逃しより誤検知を選ぶ)
      { token: '--ae-legacy', location: 'fixture:3' },
      { token: '--ae-gold', location: 'fixture:4' },
    ]);
  });

  it('token 名を途中で切って定義済みに見せかけられない (fail closed)', () => {
    // Codex adversarial-review round 2 が指摘した truncation 経路の fixture。
    // `--ae-[a-z0-9-]+` で捕らえると `--ae-goldBright` が定義済みの
    // `--ae-gold` として記録され、guard が緑のまま通ってしまう。
    const sample = [
      'a { color: var(--ae-goldBright); }',
      'b { color: var(--ae-danger_primary); }',
      'c { color: var(--ae-gold); }',
      'd { color: var(--ae-gold-bright, #fff); }',
      'e { color: var(--ae-); }',
    ].join('\n');

    const usages = scanText(sample, 'fixture');
    expect(usages.map((u) => u.token)).toEqual([
      '--ae-goldBright',
      '--ae-danger_primary',
      '--ae-gold',
      '--ae-gold-bright',
      '--ae-',
    ]);
    // 規約外の綴りは定義の有無を見るまでもなく違反。正規の 2 件は通る。
    expect(violationsIn(usages, definedTokens())).toEqual([
      '--ae-goldBright  fixture:1',
      '--ae-danger_primary  fixture:2',
      '--ae-  fixture:5',
    ]);
  });

  it('改行を挟んだ var() 参照も取りこぼさない', () => {
    const sample = ['a {', '  color: var(', '    --ae-multiline-missing', '  );', '}'].join('\n');
    expect(scanText(sample, 'fixture')).toEqual([
      { token: '--ae-multiline-missing', location: 'fixture:3' },
    ]);
  });

  it('参照されている --ae-* は fallback の有無に関わらず全て tokens.css で定義済み', () => {
    const violations = violationsIn(collectUsages(), definedTokens());

    expect(
      violations,
      'tokens.css に定義がない (または命名規約から外れた) --ae-* が参照されている。' +
        'token を tokens.css に追加するか既存 token に寄せること。' +
        'コメント中で未定義 token に言及したい場合は var(...) 形を避け bare で書く。',
    ).toEqual([]);
  });
});
