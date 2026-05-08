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
