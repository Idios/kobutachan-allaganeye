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
  // spec §7.1 で「blockquote 内も grep される、現状仕様と同等」と明記されている
  const body = `
## 受け入れ条件

> - [ ] このブロッククォート内の項目はカウントされる
`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
});
