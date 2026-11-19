// vitest 5 では `@types/jest-axe` の matcher 型 (jest 名前空間向け) が
// `expect(...).toHaveNoViolations()` に効かないため、vitest の Assertion に
// 明示的に足す (#1154。vitest 4.1.12 では不要だった)。
//
// 実行時の登録は `src/test-setup.ts` の `expect.extend(toHaveNoViolations)`。
// `export {}` は「このファイルを module にして、declare module を**置換ではなく
// 拡張**として扱わせる」ために必要 (無いと vitest の型を丸ごと上書きしてしまう)。
export {};

declare module 'vitest' {
  interface Assertion {
    toHaveNoViolations(): void;
  }
  interface AsymmetricMatchersContaining {
    toHaveNoViolations(): void;
  }
}
