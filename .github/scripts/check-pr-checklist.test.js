// .github/scripts/check-pr-checklist.test.js
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { countAcceptanceCriteriaCheckboxes } = require('./check-pr-checklist.js');

test('counts unchecked items only inside ## 受け入れ条件 section', () => {
  const body = `
## 概要

(略)

## 受け入れ条件

- [ ] 項目 1
- [x] 項目 2

## Test plan

- [ ] レビューで実機検証
- [ ] 確認 2
`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
  assert.equal(result.checked, 1);
  assert.equal(result.hasAnySection, true);
});

test('PR #621 structure passes (Test plan with - [ ] does not fail)', () => {
  const body = `
## 受け入れ条件

- [x] 受け入れ条件 1
- [x] 受け入れ条件 2

## Test plan

- [ ] レビュー時に実機検証
- [ ] レビューで GUI 起動確認
`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 0);
  assert.equal(result.checked, 2);
});

test('PR #622 structure passes (Self-Test Report with - [ ] does not fail)', () => {
  const body = `
## 受け入れ条件

- [x] 受け入れ条件 1

## Self-Test Report (本 PR 提出前にローカルで実行済)

- [x] ruff check
- [x] pyright

### 実機検証 (machine-unverifiable)

- [ ] レビュー時に Idios 実機確認
`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 0);
  assert.equal(result.checked, 1);
});

test('counts unchecked items inside ## Acceptance criteria (English variant, case-insensitive)', () => {
  const body = `
## Acceptance criteria

- [ ] Item A
- [x] Item B

## Test plan

- [ ] Manual check
`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
  assert.equal(result.checked, 1);
});

test('counts unchecked items inside ## ACCEPTANCE CRITERIA (uppercase)', () => {
  const body = `
## ACCEPTANCE CRITERIA

- [ ] Uppercase heading
`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
});

test('FAILS when unchecked items remain in 受け入れ条件 section', () => {
  const body = `
## 受け入れ条件

- [ ] 未消化項目
- [x] 完了項目
`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
});

test('hasAnySection is false when no 受け入れ条件 / Acceptance criteria section', () => {
  const body = `
## 概要

これは spec 議論用 PR です。

## Test plan

- [ ] レビュー
`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.hasAnySection, false);
});

test('blockquote-inner - [ ] inside 受け入れ条件 is currently counted (spec note)', () => {
  // 現状仕様: blockquote 内も grep される (spec docs/superpowers/specs/2026-05-08-lane-iv-b-group-g-design.md §7.1)
  const body = `
## 受け入れ条件

> - [ ] このブロッククォート内の項目はカウントされる
`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
});

test('fenced code blocks are excluded from heading detection', () => {
  // PR 本文に skill spec / template 抜粋を貼ると code block 内 heading が誤 match していた問題を修正 (PR #688 P2-1)
  const body = `
## 受け入れ条件

- [x] item 1

\`\`\`markdown
## 受け入れ条件

- [ ] this should NOT be counted (inside code block)
- [ ] another fake item inside code block
\`\`\`
`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  // code block 内の `## 受け入れ条件` は section として認識されない
  // また code block 内の `- [ ]` × 2 はカウントされない
  assert.equal(result.unchecked, 0);
  assert.equal(result.checked, 1);
  assert.equal(result.hasAnySection, true);
});

test('suffix-付き heading は skip される (e.g., `## 受け入れ条件 (追加)`)', () => {
  // spec で完全一致 regex を採用 (Q5 (A) 採択)。suffix 付き heading は対象外として凍結。
  const body = `
## 受け入れ条件 (追加)

- [ ] this should NOT be counted (suffix variant excluded)
- [x] also excluded

## 受け入れ条件

- [x] valid item
`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  // 完全一致のみ対象、suffix 付きは無視
  assert.equal(result.unchecked, 0);
  assert.equal(result.checked, 1);
  assert.equal(result.hasAnySection, true);
});

test('uppercase - [X] is counted as checked (case-insensitive gi flag)', () => {
  // spec で `gi` flag 採用、大文字 `[X]` も checked として認識される挙動を凍結
  const body = `
## 受け入れ条件

- [X] uppercase X
- [x] lowercase x
`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 0);
  assert.equal(result.checked, 2);
});

test('tilde fence (~~~) is stripped from heading detection', () => {
  // CommonMark §4.5 valid な tilde fence も strip 対象 (PR #688 R2-1)
  const body = `
## 受け入れ条件

- [x] outer item

~~~markdown
## 受け入れ条件

- [ ] tilde fence inside
~~~
`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 0);
  assert.equal(result.checked, 1);
  assert.equal(result.hasAnySection, true);
});

test('indented backtick fence (0-3 space indent within list) is stripped', () => {
  // list 内 fence (CommonMark §4.5 で 0-3 space indent 許容) も strip 対象 (PR #688 R2-2)
  const body = `
## 受け入れ条件

- [x] outer item

  \`\`\`markdown
  ## 受け入れ条件

  - [ ] indented fence inside
  - [ ] another inside
  \`\`\`
`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 0);
  assert.equal(result.checked, 1);
  assert.equal(result.hasAnySection, true);
});
