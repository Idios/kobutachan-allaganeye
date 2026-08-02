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
 * **走査は fail closed**: コメント / 文字列リテラルの区別をせず、実装ファイル
 * 中の `var(--ae-*)` という**文字列すべて**を参照として数える。コメントを
 * 除去してから走査する版も検討したが、正規表現によるコメント除去は
 * 「文字列リテラル中の `/x` と後続コメントの `x/` に挟まれた実コードごと
 * 空白化してしまう」経路があり、guard が無音で緑になりうる (Codex
 * adversarial-review medium finding)。guard の誤検知 (安全側) より
 * 見逃し (危険側) を潰すことを優先する。
 *
 * 結果として **コメントに `var(--ae-未定義token)` と書くとこのテストが落ちる**。
 * 経緯説明でトークン名に言及したいときは `var(...)` 形を避けて
 * `--ae-accent` のように bare で書くこと。
 */

// environment: 'jsdom' では `import.meta.url` が http URL になり
// fileURLToPath が使えないため、vitest の cwd (= gui/) 起点で解決する。
const SRC_DIR = join(process.cwd(), 'src');
const TOKENS_CSS = join(SRC_DIR, 'styles', 'tokens.css');

const VAR_REFERENCE = /var\(\s*(--ae-[a-z0-9-]+)/g;

/** tokens.css の `--ae-foo: ...;` 定義行から token 名を集める。 */
function definedTokens(): Set<string> {
  const css = readFileSync(TOKENS_CSS, 'utf8');
  const names = new Set<string>();
  for (const m of css.matchAll(/^\s*(--ae-[a-z0-9-]+)\s*:/gm)) {
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
 * 構文解析は行わない (前述のとおり意図的に fail closed)。
 */
function scanText(text: string, label: string): Usage[] {
  const usages: Usage[] = [];
  text.split('\n').forEach((line, i) => {
    for (const m of line.matchAll(VAR_REFERENCE)) {
      usages.push({ token: m[1], location: `${label}:${i + 1}` });
    }
  });
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
    // Codex adversarial-review が指摘した回避経路の regression fixture:
    // 文字列リテラル中の `/*` と後続コメントの `*/` に挟まれた実参照。
    // コメント除去を挟む実装ではこの区間ごと空白化され、live な inline style が
    // 走査から消えていた。
    const sample = [
      "const glyph = '/*';",
      "const style = { color: 'var(--ae-missing)' };",
      '/* 経緯: 昔は var(--ae-legacy) だった */',
      'a { color: var(--ae-gold); }',
    ].join('\n');

    const tokens = scanText(sample, 'fixture').map((u) => u.token);
    // 文字列リテラル中の `/*` に続く実参照が生き残ること (無音化の否定)
    expect(tokens).toContain('--ae-missing');
    // コメント中の参照も数える = fail closed (見逃しより誤検知を選ぶ)
    expect(tokens).toContain('--ae-legacy');
    expect(tokens).toContain('--ae-gold');
    // 行番号がズレていないこと
    expect(scanText(sample, 'fixture')[0].location).toBe('fixture:2');
  });

  it('参照されている --ae-* は fallback の有無に関わらず全て tokens.css で定義済み', () => {
    const defined = definedTokens();
    const violations = collectUsages()
      .filter((u) => !defined.has(u.token))
      .map((u) => `${u.token}  ${u.location}`);

    expect(
      violations,
      'tokens.css に定義がない --ae-* が参照されている。' +
        'token を tokens.css に追加するか既存 token に寄せること。' +
        'コメント中で未定義 token に言及したい場合は var(...) 形を避け bare で書く。',
    ).toEqual([]);
  });
});
