// .github/scripts/check-preflight-freshness.test.js
//
// `check-preflight-freshness.js` の pin test (#946)。`check-pr-checklist.test.js` と同形式で、
// **生の exit code** を子プロセスで観測する発火実証を含む。
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const {
  parseDeclaredPrSet,
  extractReferencedIssues,
  reconstructOpenAt,
  SAME_ISSUE_LABEL,
  SAME_BASE_LABEL,
} = require('./check-preflight-freshness.js');

const CHECKER_PATH = path.join(__dirname, 'check-preflight-freshness.js');
const TEMPLATE_PATH = path.join(__dirname, '..', 'pull_request_template.md');
const PR_CHECKLIST_WORKFLOW = path.join(__dirname, '..', 'workflows', 'pr-checklist.yml');
const CI_WORKFLOW = path.join(__dirname, '..', 'workflows', 'ci.yml');

/**
 * actions/github-script 経由の実行を子プロセスで再現し、**生の exit code** を観測する。
 * `core.setFailed` は @actions/core と同じく `process.exitCode = 1` を立てる。
 *
 * `PR_LIST` は `{ open: [...], closed: [...] }` 形式で `github.rest.pulls.list` の応答を供給する。
 * `PR_FAIL_LIST` を立てると list が throw し、fail-closed の検証に使う。
 */
const CHILD_SOURCE = `
const checker = require(process.env.CHECKER_PATH);
const core = {
  info: (m) => process.stdout.write('[info] ' + m + '\\n'),
  warning: (m) => process.stdout.write('[warning] ' + m + '\\n'),
  setFailed: (m) => { process.stdout.write('::error::' + m + '\\n'); process.exitCode = 1; },
};
const self = JSON.parse(process.env.PR_SELF);
const context = {
  repo: { owner: 'Idios', repo: 'kobutachan-allaganeye' },
  payload: { pull_request: self },
};
const pool = process.env.PR_LIST ? JSON.parse(process.env.PR_LIST) : { open: [], closed: [] };
let calls = 0;
const list = async (params) => {
  calls += 1;
  if (process.env.PR_FAIL_LIST) throw new Error('simulated API failure');
  const bucket = pool[params.state] || [];
  const page = params.page || 1;
  const per = params.per_page || 100;
  return { data: bucket.slice((page - 1) * per, page * per) };
};
const github = { rest: { pulls: { list } } };
checker({ github, context, core })
  .then(() => process.stdout.write('[calls] ' + calls + '\\n'))
  .catch((e) => {
    process.stdout.write('[throw] ' + e.message + '\\n');
    process.exitCode = 2;
  });
`;

/** 既定の自 PR。T0 = 2026-08-02T14:13:05Z (事象 E2 の PR #939 作成時刻)。 */
function selfPr(overrides = {}) {
  return {
    number: 939,
    created_at: '2026-08-02T14:13:05Z',
    base: { ref: 'release/v0.3.0' },
    user: { login: 'Idios', type: 'User' },
    body: 'Refs #862\n',
    ...overrides,
  };
}

function runChecker({ self, body, pool, failList }) {
  const pr = { ...selfPr(self), ...(body === undefined ? {} : { body }) };
  const env = {
    ...process.env,
    CHECKER_PATH,
    PR_SELF: JSON.stringify(pr),
    PR_LIST: JSON.stringify(pool || { open: [], closed: [] }),
  };
  if (failList) env.PR_FAIL_LIST = '1';
  const res = spawnSync(process.execPath, ['-e', CHILD_SOURCE], { env, encoding: 'utf8' });
  return { status: res.status, stdout: res.stdout, stderr: res.stderr };
}

/** 宣言 2 行を含む最小の PR 本文を組み立てる。 */
function bodyWith({ issueDecl, baseDecl, refs = 'Refs #862' }) {
  return [
    '## 概要',
    '',
    refs,
    '',
    '#### ベース同期確認 (Pre-flight)',
    '',
    '- PR 作成時の base HEAD: `deadbeef`',
    `- ${SAME_ISSUE_LABEL}: ${issueDecl}`,
    `- ${SAME_BASE_LABEL}: ${baseDecl}`,
    '',
  ].join('\n');
}

// ---------------------------------------------------------------------------
// parseDeclaredPrSet
// ---------------------------------------------------------------------------

test('parseDeclaredPrSet: "なし" は妥当な空集合', () => {
  const r = parseDeclaredPrSet(bodyWith({ issueDecl: 'なし', baseDecl: 'なし' }), SAME_ISSUE_LABEL);
  assert.equal(r.found, true);
  assert.equal(r.valid, true);
  assert.deepEqual(r.numbers, []);
});

test('parseDeclaredPrSet: PR 番号の列挙を集合として読む', () => {
  const r = parseDeclaredPrSet(
    bodyWith({ issueDecl: '#938, #940', baseDecl: 'なし' }),
    SAME_ISSUE_LABEL
  );
  assert.equal(r.valid, true);
  assert.deepEqual(r.numbers, [938, 940]);
});

test('parseDeclaredPrSet: 角括弧つきの列挙も読む', () => {
  const r = parseDeclaredPrSet(
    bodyWith({ issueDecl: '[#938]', baseDecl: 'なし' }),
    SAME_ISSUE_LABEL
  );
  assert.deepEqual(r.numbers, [938]);
});

test('parseDeclaredPrSet: 未編集のテンプレート placeholder は invalid (fail-closed)', () => {
  const r = parseDeclaredPrSet(
    bodyWith({ issueDecl: '[#N,...] (または なし)', baseDecl: 'なし' }),
    SAME_ISSUE_LABEL
  );
  assert.equal(r.found, true);
  assert.equal(r.valid, false, 'placeholder を放置したまま緑になってはならない');
});

test('parseDeclaredPrSet: 宣言行が無ければ found=false', () => {
  const r = parseDeclaredPrSet('## 概要\n\n本文のみ\n', SAME_ISSUE_LABEL);
  assert.equal(r.found, false);
});

test('parseDeclaredPrSet: 値が空でも invalid (なし と書かせる)', () => {
  const r = parseDeclaredPrSet(bodyWith({ issueDecl: '', baseDecl: 'なし' }), SAME_ISSUE_LABEL);
  assert.equal(r.found, true);
  assert.equal(r.valid, false);
});

test('parseDeclaredPrSet: 同 base 行と同 issue 行を取り違えない', () => {
  const body = bodyWith({ issueDecl: 'なし', baseDecl: '#938' });
  assert.deepEqual(parseDeclaredPrSet(body, SAME_ISSUE_LABEL).numbers, []);
  assert.deepEqual(parseDeclaredPrSet(body, SAME_BASE_LABEL).numbers, [938]);
});

// ---------------------------------------------------------------------------
// extractReferencedIssues
// ---------------------------------------------------------------------------

test('extractReferencedIssues: Refs 記法から issue 番号を拾う', () => {
  assert.deepEqual(extractReferencedIssues('Refs #862\n'), [862]);
  assert.deepEqual(extractReferencedIssues('Refs #862, #934\n'), [862, 934]);
  assert.deepEqual(extractReferencedIssues('refs: #12 と Refs #12\n'), [12], '重複は畳む');
});

test('extractReferencedIssues: Refs が無ければ空 (same-issue 検査は no-op になる)', () => {
  assert.deepEqual(extractReferencedIssues('## 概要\n\nrelease PR\n'), []);
});

// ---------------------------------------------------------------------------
// reconstructOpenAt — 「T0 時点で open だった集合」の再構成
// ---------------------------------------------------------------------------

const T0 = '2026-08-02T14:13:05Z';

test('reconstructOpenAt: T0 より後に作られた PR は除外する (後発 PR で false-red にしない)', () => {
  const prs = [{ number: 941, created_at: '2026-08-02T15:00:00Z', closed_at: null }];
  assert.deepEqual(reconstructOpenAt(prs, T0, 939), []);
});

test('reconstructOpenAt: T0 より前に閉じた PR は除外する', () => {
  const prs = [
    { number: 930, created_at: '2026-08-02T10:00:00Z', closed_at: '2026-08-02T12:34:52Z' },
  ];
  assert.deepEqual(reconstructOpenAt(prs, T0, 939), []);
});

test('reconstructOpenAt: T0 時点で open だった PR を拾う (事象 E2 の #938)', () => {
  const prs = [
    { number: 938, created_at: '2026-08-02T13:50:50Z', closed_at: '2026-08-02T14:21:12Z' },
  ];
  assert.deepEqual(
    reconstructOpenAt(prs, T0, 939).map((p) => p.number),
    [938],
    'T0 より後に merge された PR も「T0 時点では open」なので検査対象'
  );
});

test('reconstructOpenAt: 自分自身は除外する', () => {
  const prs = [{ number: 939, created_at: T0, closed_at: null }];
  assert.deepEqual(reconstructOpenAt(prs, T0, 939), []);
});

// ---------------------------------------------------------------------------
// 発火実証 (raw exit code) — 受け入れ条件の中核
// ---------------------------------------------------------------------------

test('[発火実証] 宣言に無い open PR があれば exit 1', () => {
  const r = runChecker({
    body: bodyWith({ issueDecl: 'なし', baseDecl: 'なし' }),
    pool: {
      open: [],
      closed: [
        {
          number: 938,
          created_at: '2026-08-02T13:50:50Z',
          closed_at: '2026-08-02T14:21:12Z',
          updated_at: '2026-08-02T14:21:12Z',
          base: { ref: 'release/v0.3.0' },
          title: 'fix something',
          body: 'Refs #900',
        },
      ],
    },
  });
  assert.equal(r.status, 1, `expected exit 1, got ${r.status}\n${r.stdout}${r.stderr}`);
  assert.match(r.stdout, /938/);
});

test('[設計制約] base HEAD が不動でも宣言漏れを検出する (OID 比較では false-green)', () => {
  // 事象 E2 の再現: 13:07 の Pre-flight から 14:13 の PR 作成まで base HEAD は 1 度も動いていない。
  // OID 一致比較を実装しても緑になるため、集合差分でしか捕まらないことを pin する。
  const r = runChecker({
    body: bodyWith({ issueDecl: 'なし', baseDecl: 'なし' }),
    pool: {
      open: [],
      closed: [
        {
          number: 938,
          created_at: '2026-08-02T13:50:50Z',
          closed_at: '2026-08-02T14:21:12Z',
          updated_at: '2026-08-02T14:21:12Z',
          base: { ref: 'release/v0.3.0' },
          title: 'docs: cli-spec',
          body: 'Refs #900',
        },
      ],
    },
  });
  assert.equal(r.status, 1, 'base OID が不動でも fail しなければ本 issue の目的を果たさない');
  assert.match(r.stdout, new RegExp(SAME_BASE_LABEL));
});

test('[false-red なし] 宣言集合と実集合が一致すれば exit 0', () => {
  const r = runChecker({
    body: bodyWith({ issueDecl: 'なし', baseDecl: '#938' }),
    pool: {
      open: [],
      closed: [
        {
          number: 938,
          created_at: '2026-08-02T13:50:50Z',
          closed_at: '2026-08-02T14:21:12Z',
          updated_at: '2026-08-02T14:21:12Z',
          base: { ref: 'release/v0.3.0' },
          title: 'docs',
          body: 'Refs #900',
        },
      ],
    },
  });
  assert.equal(r.status, 0, `expected exit 0, got ${r.status}\n${r.stdout}`);
});

test('[false-red なし] 宣言が実集合の superset でも exit 0 (Pre-flight 後に閉じた PR)', () => {
  const r = runChecker({
    body: bodyWith({ issueDecl: 'なし', baseDecl: '#938, #937' }),
    pool: { open: [], closed: [] },
  });
  assert.equal(r.status, 0, `expected exit 0, got ${r.status}\n${r.stdout}`);
});

test('[false-red なし] 自 PR より後に open した PR では fail しない', () => {
  const r = runChecker({
    body: bodyWith({ issueDecl: 'なし', baseDecl: 'なし' }),
    pool: {
      open: [
        {
          number: 941,
          created_at: '2026-08-02T15:00:00Z',
          closed_at: null,
          updated_at: '2026-08-02T15:00:00Z',
          base: { ref: 'release/v0.3.0' },
          title: 'later pr',
          body: '',
        },
      ],
      closed: [],
    },
  });
  assert.equal(r.status, 0, `後発 PR で red になると edited 再実行のたびに churn する\n${r.stdout}`);
});

test('[same-issue] 同じ issue を Refs する別 base の PR も検出対象', () => {
  const r = runChecker({
    body: bodyWith({ issueDecl: 'なし', baseDecl: 'なし', refs: 'Refs #862' }),
    pool: {
      open: [
        {
          number: 944,
          created_at: '2026-08-02T13:00:00Z',
          closed_at: null,
          updated_at: '2026-08-02T13:00:00Z',
          base: { ref: 'develop-0.3.1' },
          title: 'another take',
          body: 'Refs #862',
        },
      ],
      closed: [],
    },
  });
  assert.equal(r.status, 1, 'base が違っても同 issue なら Step 0 / Step 4 の検出対象');
  assert.match(r.stdout, new RegExp(SAME_ISSUE_LABEL));
});

test('[same-issue] issue 番号の部分一致で誤検出しない (#86 と #862)', () => {
  const r = runChecker({
    body: bodyWith({ issueDecl: 'なし', baseDecl: 'なし', refs: 'Refs #86' }),
    pool: {
      open: [
        {
          number: 944,
          created_at: '2026-08-02T13:00:00Z',
          closed_at: null,
          updated_at: '2026-08-02T13:00:00Z',
          base: { ref: 'develop-0.3.1' },
          title: 'another take',
          body: 'Refs #862',
        },
      ],
      closed: [],
    },
  });
  assert.equal(r.status, 0, `#862 を #86 の言及として数えてはならない\n${r.stdout}`);
});

test('[fail-closed] gh API が失敗したら exit 1 (fail-open による常時 no-op を禁じる)', () => {
  const r = runChecker({
    body: bodyWith({ issueDecl: 'なし', baseDecl: 'なし' }),
    failList: true,
  });
  assert.equal(r.status, 1, `API 失敗を握り潰すと gate が常時 no-op になる\n${r.stdout}`);
  assert.match(r.stdout, /simulated API failure|取得できませんでした/);
});

test('[fail-closed] 宣言フィールドが無ければ exit 1', () => {
  const r = runChecker({ body: '## 概要\n\nRefs #862\n', pool: { open: [], closed: [] } });
  assert.equal(r.status, 1, `宣言欄を消せば緑、では gate にならない\n${r.stdout}`);
});

test('[fail-closed] placeholder を放置したら exit 1', () => {
  const r = runChecker({
    body: bodyWith({ issueDecl: '[#N,...] (または なし)', baseDecl: 'なし' }),
    pool: { open: [], closed: [] },
  });
  assert.equal(r.status, 1, `テンプレートのまま提出して緑になってはならない\n${r.stdout}`);
});

test('[bot 例外] bot 作成 PR は宣言を要求しない', () => {
  const r = runChecker({
    self: { user: { login: 'dependabot[bot]', type: 'Bot' } },
    body: '## 概要\n\nBumps foo from 1 to 2\n',
    pool: { open: [], closed: [] },
  });
  assert.equal(r.status, 0, `dependabot に template 遵守は求められない\n${r.stdout}`);
});

// ---------------------------------------------------------------------------
// 配置先 / テンプレートの pin
// ---------------------------------------------------------------------------

test('[配置先] job は pr-checklist.yml にあり ci.yml には無い', () => {
  const prChecklist = fs.readFileSync(PR_CHECKLIST_WORKFLOW, 'utf8');
  const ci = fs.readFileSync(CI_WORKFLOW, 'utf8');
  assert.match(
    prChecklist,
    /check-preflight-freshness\.js/,
    'branch filter を持たない pr-checklist.yml に置く (ci.yml は release/* base で 1 job も起動しない)'
  );
  assert.doesNotMatch(
    ci,
    /check-preflight-freshness/,
    'ci.yml は pull_request.branches が [main, develop-*] のため release/* base で no-op になる'
  );
});

test('[配置先] pr-checklist.yml が pull-requests: read を明示宣言している', () => {
  const prChecklist = fs.readFileSync(PR_CHECKLIST_WORKFLOW, 'utf8');
  assert.match(prChecklist, /permissions:/);
  assert.match(prChecklist, /pull-requests:\s*read/);
});

test('[テンプレート] 宣言フィールド 2 件が存在する', () => {
  const template = fs.readFileSync(TEMPLATE_PATH, 'utf8');
  assert.ok(template.includes(SAME_ISSUE_LABEL), `template に "${SAME_ISSUE_LABEL}" が無い`);
  assert.ok(template.includes(SAME_BASE_LABEL), `template に "${SAME_BASE_LABEL}" が無い`);
});

test('[テンプレート] 実テンプレートの宣言行が parser で読める (placeholder は invalid)', () => {
  const template = fs.readFileSync(TEMPLATE_PATH, 'utf8');
  for (const label of [SAME_ISSUE_LABEL, SAME_BASE_LABEL]) {
    const r = parseDeclaredPrSet(template, label);
    assert.equal(r.found, true, `${label} の行が parser に見つからない`);
    assert.equal(r.valid, false, `${label} の placeholder は未編集のまま緑にしてはならない`);
  }
});

test('[doc 整合] 「CI ゲートは増設しない」が本実装と矛盾したまま残っていない', () => {
  const l2 = fs.readFileSync(
    path.join(__dirname, '..', '..', 'docs', 'l2-workflow.md'),
    'utf8'
  );
  const template = fs.readFileSync(TEMPLATE_PATH, 'utf8');
  assert.doesNotMatch(l2, /CI ゲートは増設しない/, 'docs/l2-workflow.md の宣言を改訂すること');
  assert.doesNotMatch(template, /CI ゲート増設なし/, 'PR テンプレートのコメントも改訂すること');
});
