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
 */

// environment: 'jsdom' では `import.meta.url` が http URL になり
// fileURLToPath が使えないため、vitest の cwd (= gui/) 起点で解決する。
const SRC_DIR = join(process.cwd(), 'src');
const TOKENS_CSS = join(SRC_DIR, 'styles', 'tokens.css');

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

/**
 * コメントを空白に潰す (行番号は保つ)。
 *
 * 「旧実装は var(--ae-xxx) を参照していた」という**説明**を違反として数えて
 * しまうと、修正の経緯をコードに残せなくなるため。逆に潰しすぎると実参照を
 * 見落として guard が無音化するので、`collectUsages` の総数を別テストで
 * 下限 assert している。
 */
function stripComments(text: string): string {
  // /* ... */ … CSS block comment / TS block comment / JSX の {/* ... */}
  let out = text.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, ' '));
  // // ... … 行コメント。`https://` 等を壊さないよう `:` 直後の `//` は除外
  out = out.replace(/(^|[^:])\/\/[^\n]*/g, (_full, lead: string) => lead);
  return out;
}

interface Usage {
  token: string;
  location: string;
}

/** src/ 実装ファイル中の `var(--ae-*)` 参照を (コメントを除いて) 集める。 */
function collectUsages(): Usage[] {
  const usages: Usage[] = [];
  for (const file of sourceFiles(SRC_DIR)) {
    const rel = relative(SRC_DIR, file).replace(/\\/g, '/');
    const lines = stripComments(readFileSync(file, 'utf8')).split('\n');
    lines.forEach((line, i) => {
      for (const m of line.matchAll(/var\(\s*(--ae-[a-z0-9-]+)/g)) {
        usages.push({ token: m[1], location: `${rel}:${i + 1}` });
      }
    });
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

  it('コメント除去後も実参照を取りこぼしていない (guard 無音化の検出)', () => {
    const usages = collectUsages();
    // 潰しすぎ (= 常に violations 0 の false green) をここで落とす
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

  it('コメント内の token 名は参照として数えない', () => {
    const sample = [
      '/* 旧実装は var(--ae-phantom-block) を参照していた */',
      '// 旧実装は var(--ae-phantom-line) を参照していた',
      'a { color: var(--ae-gold); background: url(https://example.invalid/a.png); }',
    ].join('\n');
    const stripped = stripComments(sample);
    expect(stripped).not.toContain('--ae-phantom-block');
    expect(stripped).not.toContain('--ae-phantom-line');
    // 実参照と URL の `//` は残ること + 行番号がズレないこと
    expect(stripped).toContain('var(--ae-gold)');
    expect(stripped).toContain('https://example.invalid/a.png');
    expect(stripped.split('\n')).toHaveLength(3);
  });

  it('参照されている --ae-* は fallback の有無に関わらず全て tokens.css で定義済み', () => {
    const defined = definedTokens();
    const violations = collectUsages()
      .filter((u) => !defined.has(u.token))
      .map((u) => `${u.token}  ${u.location}`);

    expect(violations).toEqual([]);
  });
});
