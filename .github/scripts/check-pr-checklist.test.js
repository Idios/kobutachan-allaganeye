// .github/scripts/check-pr-checklist.test.js
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { countAcceptanceCriteriaCheckboxes } = require('./check-pr-checklist.js');

const CHECKER_PATH = path.join(__dirname, 'check-pr-checklist.js');
const TEMPLATE_PATH = path.join(__dirname, '..', 'pull_request_template.md');

/**
 * actions/github-script 経由の実行を子プロセスで再現し、**生の exit code** を観測する (#936)。
 * `core.setFailed` は @actions/core と同じく `process.exitCode = 1` を立てる実装にしてある。
 * カウント関数の戻り値を assert するだけでは「gate が実際に CI を red にするか」を検証できないため、
 * 発火実証はこのハーネス経由で行う。
 */
const CHILD_SOURCE = `
const checker = require(process.env.CHECKER_PATH);
const core = {
  info: (m) => process.stdout.write('[info] ' + m + '\\n'),
  setFailed: (m) => { process.stdout.write('::error::' + m + '\\n'); process.exitCode = 1; },
};
const context = { payload: { pull_request: { body: process.env.PR_BODY } } };
checker({ github: {}, context, core }).catch((e) => {
  process.stdout.write('[throw] ' + e.message + '\\n');
  process.exitCode = 2;
});
`;

function runCheckerProcess(body) {
  const result = spawnSync(process.execPath, ['-e', CHILD_SOURCE], {
    env: { ...process.env, CHECKER_PATH, PR_BODY: body },
    encoding: 'utf8',
  });
  return { status: result.status, stdout: result.stdout || '', stderr: result.stderr || '' };
}

/**
 * 現行 `.github/pull_request_template.md` と同じ heading 階層を持つ本文を組み立てる。
 * Self-Test Report 節の中身だけを差し替えられるようにしてある。
 */
function templateShapedBody(selfTestItems) {
  return `
## 受け入れ条件

- [x] 条件 1 — 対応 diff: \`foo.py:1\`

## PR チェックリスト (Iron Law 遵守確認)

### Iron Law 1: 受け入れ条件検証

- [ ] 元 issue の \`## 受け入れ条件\` を上記で逐条検証した
- [ ] UI/出力変更の場合、実サンプルを本文に添付した

### Iron Law 3: スコープ遵守 (scope-guard)

- [ ] 変更ファイルがすべて元 issue のスコープ内であることを確認した
- [ ] スコープ外変更がある場合、理由と子 issue 番号を記載した

### Iron Law 4: クローズキーワード禁止

- [ ] 本文・コミットメッセージにクローズキーワードが含まれていない

### Iron Law 6: PR 作成前検証

#### ベース同期確認 (Pre-flight)

- PR 作成時の base HEAD: \`b5de787\`

#### Self-Test Report (machine-verified — 全件 \`[x]\` で validate-checklist 通過)

${selfTestItems}

#### 関連ドキュメント / マトリクス更新

- [ ] 関連ドキュメント更新 — 該当なしなら \`[x]\` + 理由付記
- [ ] CLAUDE.md / \`docs/l2-workflow.md\` の更新要否確認

#### 実機検証 (machine-unverifiable — plain bullet で書く)

- 該当なし (gpu_detector.py / audio/ / video/detector.py / gui/ 変更なし)
`;
}

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

// --- #936: Self-Test Report を CI 強制対象に含める ---------------------------

test('#936: Self-Test Report 節の - [ ] はカウントされる (旧 pin test の反転)', () => {
  // 反転前 (#622 当時の pin): 「Self-Test Report に `- [ ]` があっても fail しない」
  // 反転後 (#936): Self-Test Report は machine-verified 限定の節なので `- [ ]` は CI red にする。
  // なお h2 `## Self-Test Report` は配下の h3 小見出しを本文として吸収するため、
  // machine-unverifiable な項目は checkbox ではなく plain bullet `-` で書く (テンプレート規約)。
  const body = `
## 受け入れ条件

- [x] 受け入れ条件 1

## Self-Test Report (本 PR 提出前にローカルで実行済)

- [x] ruff check
- [ ] pyright
`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
  assert.equal(result.checked, 2);
  assert.equal(result.hasAnySection, true);
});

test('#936: 括弧書き suffix 付き h4 heading が prefix match で拾われる', () => {
  // 実物の heading は `#### Self-Test Report (machine-verified — 全件 [x] で validate-checklist 通過)`。
  // 受け入れ条件側の完全一致 regex ではこの形を拾えないため prefix match が要る。
  const body = templateShapedBody(
    ['- [x] `ruff check .`', '- [ ] `pytest` (python-core 変更時、slow 除外)'].join('\n')
  );
  const result = countAcceptanceCriteriaCheckboxes(body);
  // 受け入れ条件 1 件 [x] + Self-Test 1 件 [x] = 2 checked、Self-Test の未消化 1 件のみ unchecked
  assert.equal(result.unchecked, 1);
  assert.equal(result.checked, 2);
});

test('#936 D9: Iron Law 1/3/4 群と関連ドキュメント群の - [ ] はカウントされない', () => {
  // blast radius を回帰から守る pin。Self-Test Report を全件 [x] にすれば、
  // Iron Law 1 (2) / Iron Law 3 (2) / Iron Law 4 (1) / 関連ドキュメント (2) に
  // `- [ ]` が残っていても green でなければならない。
  const body = templateShapedBody(['- [x] `ruff check .`', '- [x] `pytest`'].join('\n'));
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 0);
  assert.equal(result.checked, 3); // 受け入れ条件 1 + Self-Test 2
});

test('#936 D9: Self-Test Report 節は次の兄弟 h4 で終わる (関連ドキュメントを飲み込まない)', () => {
  // `#### Self-Test Report` の直後に `#### 関連ドキュメント` が来る構造で、
  // 後者の `- [ ]` が Self-Test 節に混入しないことを固定する。
  const body = templateShapedBody('- [x] `ruff check .`');
  const withExtraUnchecked = body.replace(
    '- [ ] 関連ドキュメント更新',
    '- [ ] 関連ドキュメント更新 (増設分)'
  );
  const result = countAcceptanceCriteriaCheckboxes(withExtraUnchecked);
  assert.equal(result.unchecked, 0);
});

test('#936: h2 Self-Test Report + h3 machine-verified 小見出し配下もカウントされる', () => {
  // 実在 PR (#909 / #924 / #927 等) の形。h2 節が配下の h3 を吸収しないと gate が無発火になる。
  const body = `
## Self-Test Report

### machine-verified

- [x] \`ruff check .\`
- [ ] \`pytest\`

### machine-unverifiable

- doc の記述が実装と一致しているかは reviewer が逐条確認した
`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
  assert.equal(result.checked, 1);
  assert.equal(result.hasAnySection, true);
});

test('#936: 受け入れ条件 節は配下の h3 小見出しを吸収する (既存 gate を縮小しない)', () => {
  // 実在 PR #956 の形。`## 受け入れ条件` の中に `###` 小見出しを置く本文は実際に使われており、
  // heading level を見ずに h2-h4 で素朴に split すると、この 13 box 相当が丸ごと gate 対象外になる。
  const body = `
## 受け入れ条件

- [x] 前段の条件

### 実装計画 PR-A2 の受け入れゲート

- [x] ゲート 1
- [ ] ゲート 2

## PR チェックリスト (Iron Law 遵守確認)

### Iron Law 1: 受け入れ条件検証

- [ ] 逐条検証した
`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1); // 小見出し配下の未消化が見える
  assert.equal(result.checked, 2);
});

test('#936: Self-Test Report だけの本文でも gate が有効 (skip しない)', () => {
  // `## 受け入れ条件` が無い本文 (実在 PR #909 等) は従来 hasAnySection=false で全 skip だった。
  const body = `
## Summary

- 変更概要

## Self-Test Report

- [ ] \`pytest\`
`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.hasAnySection, true);
  assert.equal(result.unchecked, 1);
});

test('#936 D9: 実テンプレートは 22 box 中 12 box のみが gate 対象', () => {
  // 実物の `.github/pull_request_template.md` を通した end-to-end の blast radius 固定。
  // 内訳: 受け入れ条件 2 + Self-Test Report 10 = 12 (required)
  //       Iron Law 1 が 2 / Iron Law 3 が 2 / Iron Law 4 が 1 / 関連ドキュメント 5 = 10 (非対象)
  // テンプレートの checkbox を増減したらこの数値を更新すること (意図的な tripwire)。
  const template = fs.readFileSync(TEMPLATE_PATH, 'utf8');
  const totalUnchecked = (template.match(/- \[ \]/g) || []).length;
  const result = countAcceptanceCriteriaCheckboxes(template);
  assert.equal(totalUnchecked, 22, 'テンプレート全体の - [ ] 総数');
  assert.equal(result.unchecked, 12, 'gate 対象となる - [ ] の数 (受け入れ条件 2 + Self-Test 10)');
});

// --- #936: 発火実証 (生の exit code) ----------------------------------------

test('#936 発火実証: Self-Test Report に - [ ] が 1 件残ると非ゼロ exit', () => {
  const body = templateShapedBody(
    ['- [x] `ruff check .`', '- [ ] `pytest` (未実施)'].join('\n')
  );
  const { status, stdout } = runCheckerProcess(body);
  assert.equal(status, 1, `exit code が 1 でない (stdout: ${stdout})`);
  assert.match(stdout, /::error::/);
});

test('#936 発火実証: 全件 [x] なら exit 0 (false-red がないことの対照実験)', () => {
  const body = templateShapedBody(['- [x] `ruff check .`', '- [x] `pytest`'].join('\n'));
  const { status, stdout } = runCheckerProcess(body);
  assert.equal(status, 0, `exit code が 0 でない (stdout: ${stdout})`);
  assert.doesNotMatch(stdout, /::error::/);
});

test('#936 発火実証: 受け入れ条件の未消化は従来どおり非ゼロ exit', () => {
  const { status } = runCheckerProcess('## 受け入れ条件\n\n- [ ] 未消化\n');
  assert.equal(status, 1);
});

// --- 既存挙動の pin ---------------------------------------------------------

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

test('hasAnySection is false when no 受け入れ条件 / Acceptance criteria / Self-Test Report section', () => {
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

test('fenced code block 内の #### Self-Test Report も除外される', () => {
  // #936 で対象 heading が増えたため、code block 内の Self-Test Report 抜粋でも誤 match しないことを固定。
  const body = `
## 受け入れ条件

- [x] item 1

\`\`\`markdown
#### Self-Test Report (machine-verified)

- [ ] template 抜粋なのでカウントされない
\`\`\`
`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 0);
  assert.equal(result.checked, 1);
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

test('`### Iron Law 1: 受け入れ条件検証` は受け入れ条件 heading と誤認されない', () => {
  // 完全一致 regex のため prefix/suffix 付きの Iron Law 見出しは対象外 (D9 の前提)。
  const body = `
### Iron Law 1: 受け入れ条件検証

- [ ] 逐条検証した
`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.hasAnySection, false);
  assert.equal(result.unchecked, 0);
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
