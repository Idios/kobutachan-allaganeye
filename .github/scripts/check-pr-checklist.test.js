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
const context = {
  repo: { owner: 'Idios', repo: 'kobutachan-allaganeye' },
  payload: {
    pull_request: {
      number: 1,
      body: process.env.PR_BODY,
      user: process.env.PR_USER_TYPE ? { type: process.env.PR_USER_TYPE } : undefined,
    },
  },
};
// PR_FILES が与えられたときだけ listFiles を生やす。未指定なら github は空のままで、
// checker 側の「files 取得不可 → semantic 検査 skip」経路を通る (従来テストの挙動を保つ)。
const github = process.env.PR_FILES
  ? { rest: { pulls: { listFiles: async () => ({ data: JSON.parse(process.env.PR_FILES) }) } } }
  : {};
checker({ github, context, core }).catch((e) => {
  process.stdout.write('[throw] ' + e.message + '\\n');
  process.exitCode = 2;
});
`;

function runCheckerProcess(body, userType, files) {
  const env = { ...process.env, CHECKER_PATH, PR_BODY: body };
  if (userType) env.PR_USER_TYPE = userType;
  else delete env.PR_USER_TYPE;
  if (files) env.PR_FILES = JSON.stringify(files);
  else delete env.PR_FILES;
  const result = spawnSync(process.execPath, ['-e', CHILD_SOURCE], { env, encoding: 'utf8' });
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

// --- #967: GitHub のレンダリングとの整合 -------------------------------------
//
// 期待値は推測ではなく **GitHub 自身の GFM renderer** (`gh api markdown`) の出力から決めた。
// 各ケースは「未消化 checkbox が GitHub 上で何個見えるか」を測り、それと counter を一致させる。
// renderer の実測結果 (2026-08-08、`aria-label="Incomplete task"` の個数と heading tag):
//
//   ケース                          GitHub の描画                       期待 unchecked
//   ------------------------------- ----------------------------------- --------------
//   h4 (対照)                       <h4> + 未消化 1                     1
//   1 / 3 / 4 space インデント h4   <h4> + 未消化 1 (list 直後は h4)    1
//   h1 / h5 / h6                    <h1>/<h5>/<h6> + 未消化 1           1
//   blockquote 内 heading           <h4> + 未消化 1                     1
//   `####` + tab 区切り             <h4> + 未消化 1                     1
//   閉じ ATX (`#### ... ####`)      <h4> + 未消化 1                     1
//   U+2011 ハイフンの heading text  <h4> + 未消化 1                     1
//   `####` + U+3000 区切り          heading にならない (段落)           0
//   setext (`---` 下線)             <hr> になり heading にならない      0
//   `**bold**` 疑似見出し           heading にならない                  0
//   blockquote 内 fence             未消化 0 (code)                     0
//   list 配下 4 space の fence      未消化 0 (code)                     0
//   root の 4 space インデント行    未消化 0 (indented code block)      0
//   コメント内の孤立 fence          未消化 1 (節も普通に描画される)     1
//
// 「heading にならない」ケースで 0 なのは、GitHub 上にも Self-Test Report 節が存在しないため。
// 節と項目の存在自体を要求するか (自己申告 gate をやめるか) は #967 修正方針 6 で別途判断する。

// 実テンプレートと同じ「受け入れ条件節 → 介在 h2 → Self-Test 節」構造。
// **介在 h2 は load-bearing**: これが無いと Self-Test heading を認識できなくても項目が
// 受け入れ条件節に吸収されて数えられてしまい、gate としての差が出ない (テスト自体が false-green)。
const TPL_PREFIX = [
  '## 受け入れ条件',
  '',
  '- [x] 条件 1',
  '',
  '## PR チェックリスト (Iron Law 遵守確認)',
  '',
].join('\n');
const ST_TITLE = 'Self-Test Report (machine-verified)';

/** テンプレート構造 + Self-Test 節 (heading の形を差し替え) + 未消化 1 件 */
function stBody(headingLine, item = '- [ ] pytest') {
  return `${TPL_PREFIX}${headingLine}\n\n${item}\n`;
}

// [label, body, 期待 unchecked] — 期待値は上記 renderer 実測から導出
const RENDER_ORACLE_CASES = [
  // GitHub が Self-Test heading として描画する = 節として認識すべき (unchecked 1)
  ['h4 対照', stBody(`#### ${ST_TITLE}`), 1],
  ['1 space インデント h4', stBody(` #### ${ST_TITLE}`), 1],
  ['3 space インデント h4', stBody(`   #### ${ST_TITLE}`), 1],
  ['h1', stBody(`# ${ST_TITLE}`), 1],
  ['h5', stBody(`##### ${ST_TITLE}`), 1],
  ['h6', stBody(`###### ${ST_TITLE}`), 1],
  ['tab 区切り', stBody(`####\t${ST_TITLE}`), 1],
  ['閉じ ATX (trailing hashes)', stBody(`#### ${ST_TITLE} ####`), 1],
  ['U+2011 ハイフンの heading text', stBody('#### Self‑Test Report (machine-verified)'), 1],
  ['blockquote 内 heading', `${TPL_PREFIX}> #### ${ST_TITLE}\n>\n> - [ ] pytest\n`, 1],
  ['setext は heading として認識しない (下記のトレードオフ参照)', `${TPL_PREFIX}${ST_TITLE}\n---\n\n- [ ] pytest\n`, 0],

  // GitHub が heading として描画しない = 節が存在しない (unchecked 0)
  ['U+3000 区切りは heading でない', stBody(`####　${ST_TITLE}`), 0],
  ['bold 疑似見出しは heading でない', stBody(`**${ST_TITLE}**`), 0],
  ['4 space インデントは list 文脈が無ければ indented code block', stBody(`    #### ${ST_TITLE}`), 0],
];

for (const [label, body, expected] of RENDER_ORACLE_CASES) {
  test(`#967 heading 認識が GitHub の描画と一致する: ${label}`, () => {
    const result = countAcceptanceCriteriaCheckboxes(body);
    assert.equal(result.unchecked, expected, `body:\n${body}`);
  });
}

test('#967: 4 space インデント heading は list 文脈なら heading (renderer 実測)', () => {
  // 直前が list の場合、GitHub は 4 space インデントの `#### ...` を <h4> として描画する
  // (list item の継続扱い)。同じ 4 space でも文脈で意味が変わる。
  const body = `## 受け入れ条件\n\n- [x] 条件 1\n\n    #### ${ST_TITLE}\n\n    - [ ] pytest\n`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
});

// --- setext を認識しないトレードオフ (実測で決めた) ---------------------------
//
// GitHub は「段落 + `---`」を setext h2 として描画するので、素直に実装すると Self-Test 節を
// setext で書いた本文も拾える。しかし実測すると:
//   - 実在 31 本で setext 見出しを使った本文は **0 件**
//   - `---` 区切りを含む本文は **3 件** (表や引用の直後に置く形はこの repo の PR 本文で頻出)
// 後者では直前行が段落扱いになり、**偽の setext heading が対象節を打ち切る false-green** が出る
// (renderer 実測で確認。実在 PR #943 の本文に `---` を 1 行足すと exit 1 → exit 0 に反転した)。
// 得るものが 0 件で害が 3 件なので、setext は認識しない側に倒す。
// 代償として setext 形の Self-Test 節は gate 対象外になる (宣言済みの近似)。

test('#967: 表の直後の `---` は偽の heading を作らない (節を打ち切らない)', () => {
  const body = `${TPL_PREFIX}#### ${ST_TITLE}\n\n| 項目 | 結果 |\n| --- | --- |\n| pytest | pass |\n---\n\n- [ ] ruff\n`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
});

test('#967: 引用の直後の `---` も偽の heading を作らない', () => {
  const body = `${TPL_PREFIX}#### ${ST_TITLE}\n\n> 注記: GPU 実機は未検証\n---\n\n- [ ] pytest\n`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
});

// --- checkbox の box に入る Unicode 空白 --------------------------------------

for (const [label, ch] of [
  ['全角空白 (日本語 IME)', '\u3000'],
  ['NBSP (copy-paste)', '\u00a0'],
  ['tab', '\t'],
]) {
  test(`#967 false-green: box が ${label} でも未消化として数える`, () => {
    // GFM は box の中身が 1 文字の空白なら未消化 task item として描画する
    // (renderer 実測: Incomplete task 1 個)。ASCII space 固定だと日本語環境で素通りする。
    const body = `${TPL_PREFIX}#### ${ST_TITLE}\n\n- [x] ruff\n- [${ch}] pytest 未実施\n`;
    const result = countAcceptanceCriteriaCheckboxes(body);
    assert.equal(result.unchecked, 1);
  });
}

test('#967 false-green: U+3000 区切りの兄弟行は節を打ち切らない', () => {
  // GitHub は `####　関連ドキュメント` を heading にしないので Self-Test 節は続いており、
  // 未消化 1 件が描画される (renderer 実測: <h4> Self-Test + Incomplete task 1)。
  const body = `${TPL_PREFIX}#### ${ST_TITLE}\n\n####　関連ドキュメント\n\n- [ ] pytest\n`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
});

test('#967 false-red: blockquote 内の fenced code block は数えない', () => {
  const body = `${TPL_PREFIX}#### ${ST_TITLE}\n\n- [x] pytest\n\n> \`\`\`markdown\n> - [ ] 引用された未消化\n> \`\`\`\n`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 0);
  assert.equal(result.checked, 2);
});

test('#967 false-red: list 配下 4 space インデントの fence は数えない', () => {
  const body = `${TPL_PREFIX}#### ${ST_TITLE}\n\n- [x] pytest\n\n    抜粋:\n\n    \`\`\`markdown\n    - [ ] ruff check\n    \`\`\`\n`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 0);
  // `unchecked === 0` だけを見ると「何も数えない」退行実装でも通ってしまうので、
  // 節内の可視項目が数えられていること (positive control) も同時に固定する。
  assert.equal(result.checked, 2, 'fence 外の [x] は数える (受け入れ条件 1 + Self-Test 1)');
  assert.equal(result.selfTestItems, 1);
});

test('#967 false-red: root の 4 space インデント行は indented code block として数えない', () => {
  // renderer 実測: <pre> になり Incomplete task は 0 個。
  const body = `${TPL_PREFIX}#### ${ST_TITLE}\n\n- [x] pytest\n\n段落:\n\n    - [ ] インデントコードブロック内\n`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 0);
});

test('#967: list 配下 4 space インデントの入れ子 checkbox は数える', () => {
  // 上記の裏。同じ 4 space でも親 list があれば GitHub は task item として描画する。
  const body = `${TPL_PREFIX}#### ${ST_TITLE}\n\n- [x] 親\n    - [ ] 4 space の入れ子\n`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
});

test('#967 false-green: backtick fence の info string に backtick があると fence は開かない', () => {
  // CommonMark §4.5: backtick fence の info string は backtick を含めない。含む場合 fence は
  // 開かないため後続行は通常の markdown として描画される (renderer 実測: Incomplete task 1)。
  // Codex adversarial-review [high]。
  const body = `${TPL_PREFIX}#### ${ST_TITLE}\n\n\`\`\` \`pytest\`\n- [ ] pytest\n\`\`\`\n`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
});

test('#967: tilde fence の info string は backtick を含んでよい (対照)', () => {
  // tilde fence には backtick 制約がないため fence は開き、中身は code になる
  // (renderer 実測: Incomplete task 0)。上の修正でこちらを壊さないことを固定する。
  const body = `${TPL_PREFIX}#### ${ST_TITLE}\n\n~~~ \`pytest\`\n- [ ] inside tilde code\n~~~\n`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 0);
});

test('#967 false-red: 閉じ fence の後ろに文字がある行は fence を閉じない', () => {
  // CommonMark §4.5: 閉じ fence は空白 / tab のみを後続に許す。`\`\`\` still code` は
  // code 内容であり fence を閉じない (renderer 実測: Incomplete task 0)。
  // Codex adversarial-review [medium]。
  const body = `${TPL_PREFIX}#### ${ST_TITLE}\n\n\`\`\`markdown\n\`\`\` still code\n- [ ] not visible\n\`\`\`\n`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 0);
});

test('#967 false-green: 行中で開いた HTML コメントは後続行を飲み込まない', () => {
  // 行頭の `<!--` は HTML block を開始するが、**行中**の `<!--` は inline HTML であり
  // 後続行のブロック構造 (list item) を飲み込まない。GitHub は 2 行目を
  // Incomplete task として描画する (renderer 実測: Completed 2 / Incomplete 1)。
  const body = `${TPL_PREFIX}#### ${ST_TITLE}\n\n- [x] 済み <!-- note\n- [ ] コメント継続中に見える項目\n-->\n`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
  assert.equal(result.checked, 2);
});

// CommonMark のインデントは ASCII の space / tab のみ。JS の `trimStart()` / `trim()` は
// NBSP や全角空白まで落とすため、GitHub 上では段落テキストの行が heading / task item に
// 化けて gate の判定を狂わせる (Codex adversarial-review round 3 [high] + 自前 sweep)。
const NBSP = ' ';
const IDEOGRAPHIC_SPACE = '　';

for (const tag of ['pre', 'script', 'textarea']) {
  test(`#967 false-red: <${tag}> ブロック (CommonMark type 1) 内の行は数えない`, () => {
    // type 1 HTML block は**閉じタグまで**続き空行では終わらない。ログ貼り付けで
    // `<pre>` を使うと中の checkbox 記法を数えてしまう誤爆があった (renderer 実測: 0 個)。
    const body = `#### ${ST_TITLE}\n\n- [x] done\n\n<${tag}>\n- [ ] ${tag} 内\n</${tag}>\n`;
    const result = countAcceptanceCriteriaCheckboxes(body);
    assert.equal(result.unchecked, 0);
  });
}

test('#967: type 1 の終了条件は `</tag>` の完全一致 (`</pre >` では閉じない)', () => {
  // CommonMark §4.6 type 1 の終了条件は `</pre>` / `</script>` / `</style>` / `</textarea>` の
  // **文字列一致**で、空白を挟んだ `</pre >` では閉じない (renderer 実測: Incomplete task 0 個。
  // Codex は「閉じる」と予測したが GitHub は閉じなかった)。
  const body = `#### ${ST_TITLE}\n\n<pre>\nlog\n</pre >\n\n- [ ] pytest\n`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 0);
});

test('#967 false-red: `</pres>` のような near-miss で type 1 を閉じない', () => {
  // 閉じタグ判定を緩めると (regex の `\\s` エスケープ落ちで `s*` になっていた) `</pres>` が
  // 終了扱いになり、GitHub では code 内のままの checkbox を数える誤爆になる
  // (renderer 実測: Incomplete task 0 個)。
  const body = `#### ${ST_TITLE}\n\n<pre>\nlog\n</pres>\n\n- [ ] pytest\n`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 0);
});

test('#967: type 1 の閉じタグは大文字でも閉じる', () => {
  const body = `#### ${ST_TITLE}\n\n<pre>\nlog\n</PRE>\n\n- [ ] pytest\n`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
});

test('#967: type 1 ブロックが閉じた後の checkbox は数える (対照)', () => {
  const body = `#### ${ST_TITLE}\n\n<pre>\nlog\n</pre>\n\n- [ ] pre の後の項目\n`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
});

test('#967 regression: 4 space 入れ子 list の 2 件目以降の兄弟も数える', () => {
  // PR #970 の list 文脈判定 (`indent >= lastListIndent + 2`) は、入れ子項目が
  // lastListIndent を 4 に上げた直後の**同じインデントの兄弟**を弾いてしまい、
  // GitHub 上に見える未消化項目を落としていた (pre-#970 は正しく数えていた regression)。
  // renderer 実測: Incomplete task 1 個。
  const body = '## 受け入れ条件\n\n- [x] A\n    - [x] B1\n    - [ ] B2\n';
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
});

test('#967 regression: 閉じ忘れ fence が list container を抜けたら閉じる', () => {
  // list 配下 (indent 4) で開いた fence を閉じ忘れると、fence が EOF まで残って
  // 後続の対象節ごと読み飛ばし、`hasAnySection=false` で gate が丸ごと skip されていた。
  // GitHub は list container の終端 (列 0 の heading) で code block を閉じるため、
  // 受け入れ条件と Self-Test Report の未消化項目は普通に描画される (renderer 実測: 2 個)。
  const body =
    '## 修正内容\n\n- 変更点:\n\n    ```diff\n    -old\n    +new\n\n## 受け入れ条件\n\n- [ ] 条件 1\n\n' +
    '## PR チェックリスト\n\n#### Self-Test Report (machine-verified)\n\n- [ ] pytest\n';
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.hasAnySection, true);
  assert.equal(result.unchecked, 2);
});

test('#967 近似境界: list item の content indent を超える深い入れ子は数える (false-red、既知)', () => {
  // GitHub は list item 内の 6 space (content indent + 4) を indented code block として描画する
  // (renderer 実測: Incomplete task 0 個) が、checker は list 文脈と見て数える。
  // 誤りの向きが false-red なので許容し、docs/l2-workflow.md §「この gate が見ていない集合」
  // に記載済み。**これは未知の穴ではなく宣言済みの近似**であることを固定する。
  const body = `#### ${ST_TITLE}\n\n- 親\n\n      - [ ] 6 space インデント\n`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
});

test('#967: top level の 0-3 space インデント fence は列 0 行で閉じない (GitHub と同じ)', () => {
  // list の外で開いた fence は CommonMark の「0-3 space インデント fence」であり、
  // 中の列 0 行も code 内容 (renderer 実測: Incomplete task 0 個)。container 終端で
  // 閉じる規則は **list 内で開いた fence にのみ** 適用しないと誤爆する。
  const body = `#### ${ST_TITLE}\n\n- [x] done\n\n段落\n\n  \`\`\`text\n- [ ] 列 0 の行\n  \`\`\`\n`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 0);
});

test('#967: list 配下 fence 内の列 0 行は fence を抜ける (GitHub と同じ)', () => {
  // CommonMark では列 0 の行で list item が終わり code block も閉じるため、その行は
  // 新しい task item として描画される (renderer 実測: Incomplete task 1 個)。
  const body =
    '## 受け入れ条件\n\n- [x] 条件 1\n  ```diff\n- [ ] 列 0 の行\n  ```\n\n## PR チェックリスト\n\n- [x] 関係ない box\n';
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
});

test('#967: 列 0 で開いた fence は閉じ忘れても最後まで code (GitHub と同じ)', () => {
  // 逆方向の対照。top level の未閉鎖 fence は文書末まで code なので、以降の項目は
  // 数えない (GitHub もそう描画する)。indent scoping が過剰に働かないことを固定する。
  const body = '## 受け入れ条件\n\n- [x] 条件 1\n\n```diff\n- [ ] code のまま\n';
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 0);
});

test('#967 false-red: checkbox の直後に空白が無い行は task item でない', () => {
  // GFM の task list item は `[ ]` の後に空白を要求する。`- [ ]項目` は通常の list item
  // として描画される (renderer 実測: Incomplete task 0 個)。
  const body = `${TPL_PREFIX}#### ${ST_TITLE}\n\n- [ ]項目 (box の後に空白なし)\n`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 0);
});

test('#967 false-red: HTML ブロック内の行は markdown として解釈されない', () => {
  // `<div>` / `<details>` 等の HTML ブロックは空行まで続き、中身は markdown として
  // 解釈されない (renderer 実測: Incomplete task 0 個)。`<details>` を使う PR 本文で
  // 現実に起こる誤爆。
  const body = `${TPL_PREFIX}#### ${ST_TITLE}\n\n<div>\n- [ ] div 内\n</div>\n`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 0);
});

test('#967: HTML ブロックは空行で終わるので、その後の checkbox は数える', () => {
  // `<details>` の後に空行を入れた形は markdown として解釈され、checkbox が描画される。
  const body = `${TPL_PREFIX}#### ${ST_TITLE}\n\n<details>\n\n- [ ] details 内 (空行あり)\n\n</details>\n`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
});

test('#967 false-green: NBSP 始まりの行は heading でないので節を打ち切らない', () => {
  // renderer 実測: NBSP 行は段落。直近の heading は Self-Test の h4 なので節は継続し、
  // 未消化 1 件が節内に見える。
  const body = `${TPL_PREFIX}#### ${ST_TITLE}\n\n${NBSP}#### 関連ドキュメント\n\n- [ ] pytest\n`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
});

test('#967 false-green: 全角空白始まりの行も heading でない', () => {
  const body = `${TPL_PREFIX}#### ${ST_TITLE}\n\n${IDEOGRAPHIC_SPACE}#### 関連ドキュメント\n\n- [ ] pytest\n`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
});

test('#967 false-red: NBSP 始まりの行は task item でない', () => {
  // renderer 実測: Incomplete task 0 個 (段落テキストとして描画される)。
  const body = `${TPL_PREFIX}#### ${ST_TITLE}\n\n${NBSP}- [ ] NBSP インデント項目\n`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 0);
});

test('#967: NBSP 始まりの required heading は節を開始しない', () => {
  // renderer 実測: heading にならないため Self-Test 節が存在せず、後続項目は gate 対象外。
  const body = `## 受け入れ条件\n\n- [x] 条件 1\n\n## PR チェックリスト\n\n${NBSP}#### ${ST_TITLE}\n\n- [ ] pytest\n`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 0);
});

test('#967 false-green: blockquote 内で開いた fence は引用の外まで続かない', () => {
  // 引用が終われば中の fenced block も終わる。GitHub は引用の外の `- [ ]` を
  // Incomplete task として描画する (renderer 実測: Incomplete 1)。
  // blockquote prefix を一律に剥がすだけだと fence が引用境界を越えて残り、
  // 可視の未消化項目を読み飛ばす false-green になる。
  const body = `${TPL_PREFIX}#### ${ST_TITLE}\n\n> \`\`\`markdown\n- [ ] 引用の外\n\`\`\`\n`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
});

test('#967: fence の外側で開いた fence 内の引用行は code のまま (逆方向の対照)', () => {
  // 逆向き: top level で開いた fence の中に `>` 行があっても、それは code 内容。
  const body = `${TPL_PREFIX}#### ${ST_TITLE}\n\n\`\`\`markdown\n> - [ ] code 内の引用\n\`\`\`\n`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 0);
});

test('#967: hash のみの兄弟見出しは節を閉じる', () => {
  // `####` 単独も CommonMark では heading (GitHub 実測: 空の <h4>)。同レベルなので
  // Self-Test 節を閉じ、後続の未消化項目は gate 対象外になる。
  const body = `${TPL_PREFIX}#### ${ST_TITLE}\n\n####\n\n- [ ] 節の外の項目\n`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 0);
});

test('#967 false-green: HTML コメント内の孤立 fence が節を消さない', () => {
  // 2 段 replace (fence 除去 → コメント除去) では、コメント内の ``` が後続の実 code block と
  // ペアリングして間の節を丸ごと削除していた (lexer desync)。
  const body = `${TPL_PREFIX}<!--\n\`\`\`\n-->\n\n#### ${ST_TITLE}\n\n- [ ] pytest\n\n\`\`\`text\nsample\n\`\`\`\n`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
});

test('#967: 閉じ ATX heading の受け入れ条件節も認識する', () => {
  // GitHub は `## 受け入れ条件 ##` の trailing hashes を落として heading text にする。
  const result = countAcceptanceCriteriaCheckboxes('## 受け入れ条件 ##\n\n- [ ] 条件\n');
  assert.equal(result.unchecked, 1);
  assert.equal(result.hasAnySection, true);
});

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

test('#936 D9: 実テンプレートは 24 box 中 13 box のみが gate 対象', () => {
  // 実物の `.github/pull_request_template.md` を通した end-to-end の blast radius 固定。
  // 内訳: 受け入れ条件 2 + Self-Test Report 10 = 12 (required)
  //       Iron Law 1 が 2 / Iron Law 3 が 2 / Iron Law 4 が 1 / 関連ドキュメント 6 = 11 (非対象)
  // テンプレートの checkbox を増減したらこの数値を更新すること (意図的な tripwire)。
  //
  // 2026-08-11 (#952): 関連ドキュメント へ「CHANGELOG entry の要否を判断した」を
  // 1 box 追加したため総数 22 -> 23。**gate 対象は 12 のまま**であることが重要で、
  // これは新 box が counting 対象外の節に入った証拠になる (D9 の範囲を広げていない)。
  //
  // 2026-08-20 (#945): Self-Test Report へ「Fable 俯瞰レビュー」を 1 box 追加したため
  // 総数 23 -> 24、**gate 対象も 12 -> 13** に増えた。#952 の追加とは逆に、
  // こちらは counting 対象節に入れるのが目的なので gate 対象が増えるのが正しい。
  const template = fs.readFileSync(TEMPLATE_PATH, 'utf8');
  const totalUnchecked = (template.match(/- \[ \]/g) || []).length;
  const result = countAcceptanceCriteriaCheckboxes(template);
  assert.equal(totalUnchecked, 24, 'テンプレート全体の - [ ] 総数');
  assert.equal(result.unchecked, 13, 'gate 対象となる - [ ] の数 (受け入れ条件 2 + Self-Test 11)');
});

test('#945: Self-Test Report の Fable 欄が未記入なら validate-checklist が red (生 exit code)', () => {
  // 3 点セット ③ (発火側の red 実証)。カウント関数の戻り値ではなく、
  // actions/github-script 相当の子プロセスを通した **exit code の生値** を観測する。
  // これが 1 にならないなら、box を足しても gate は 1 度も赤を出さない no-op である。
  const fableLine =
    '- [ ] Fable 俯瞰レビュー (#945) — `実施 (finding N 件 / 消化 M 件 / 残 K 件)` または `非実施 (理由: <1 行>)`';
  const body = [
    '#### Self-Test Report (machine-verified)',
    '',
    '- [x] `ruff check .`',
    fableLine,
    '',
  ].join('\n');

  const red = runCheckerProcess(body);
  assert.equal(red.status, 1, 'Fable 欄が未記入なら exit 1 (red)');
  assert.match(red.stdout, /::error::/, 'core.setFailed が呼ばれている');

  // 対照: 同じ本文で Fable 欄だけを [x] にすると緑になる。
  // これが無いと「何を書いても赤い」だけの gate と区別できない。
  // placeholder を残したまま [x] にするのは「レビューせずに緑」なので実記入形へ置換する
  const filled = '- [x] Fable 俯瞰レビュー (#945): 非実施 (理由: doc-only でない)';
  const green = runCheckerProcess(body.replace(fableLine, filled));
  assert.equal(green.status, 0, 'Fable 欄を消化すれば exit 0 (green)');
});

test('#936: `*` / `+` / 番号付き list marker の checkbox も数える (false-green 修正)', () => {
  // Codex adversarial-review round 2 [medium]。GFM の task list は `-` 以外の marker でも
  // checkbox としてレンダリングされるため、`- ` 固定だと可視の未消化を見逃す。
  const body = `
## Self-Test Report

* [ ] pytest
+ [x] ruff
1. [ ] pyright
2) [x] markdownlint
`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 2);
  assert.equal(result.checked, 2);
});

test('#936: 行頭でない `- [ ]` (文中・コードスパン) は数えない (false-red 修正)', () => {
  // GitHub は行中の `- [ ]` を checkbox としてレンダリングしない。
  // checker 自身を説明する本文 (当 PR の本文がまさにそれ) が誤って red になるのを防ぐ。
  const body = `
## 受け入れ条件

- [x] Self-Test Report に \`- [ ]\` を 1 件残すと非ゼロ exit する — 対応 test: 発火実証
- [x] 文中に - [ ] と書いても checkbox にはならない
`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 0);
  assert.equal(result.checked, 2);
});

test('#936: 同じ本文を繰り返し渡しても結果が変わらない (module 級 /g regex の lastIndex 汚染なし)', () => {
  const body = '## 受け入れ条件\n\n- [ ] a\n- [x] b\n';
  const first = countAcceptanceCriteriaCheckboxes(body);
  for (let i = 0; i < 3; i++) {
    assert.deepEqual(countAcceptanceCriteriaCheckboxes(body), first);
  }
  assert.equal(first.unchecked, 1);
});

test('#936: 多段 blockquote 内の checkbox も数える', () => {
  const result = countAcceptanceCriteriaCheckboxes('## 受け入れ条件\n\n> > - [ ] nested quote\n');
  assert.equal(result.unchecked, 1);
});

test('#936: インデントされた入れ子の checkbox も数える', () => {
  const body = `
## 受け入れ条件

- [x] 親項目
  - [ ] 入れ子の未消化
`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
  assert.equal(result.checked, 1);
});

test('#936: HTML コメント内の heading は section を打ち切らない (false-green 修正)', () => {
  // Codex adversarial-review round 1 [high]。GitHub 上でレンダリングされないコメント行が
  // heading とみなされ、その後ろの**可視の** `- [ ]` が数えられない false-green があった。
  // テンプレート抜粋をコメントで貼る本文で実際に起こる。
  const body = '## Self-Test Report\n<!--\n## hidden template heading\n-->\n- [ ] pytest\n';
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
});

test('#936: 受け入れ条件 節でも同じ false-green が塞がれている (base からの既存穴)', () => {
  // 同じ入力を base 実装に通すと unchecked=0 になる (実測済み)。gate 拡大にあわせて既存穴も塞ぐ。
  const body = '## 受け入れ条件\n<!--\n## hidden\n-->\n- [ ] item\n';
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
});

test('#936: HTML コメント内の - [ ] はカウントされない (不可視の項目は gate 対象外)', () => {
  const body = `
## 受け入れ条件

<!-- 記入例: - [ ] (条件 1 を逐条記入) -->

- [x] 実際の条件
`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 0);
  assert.equal(result.checked, 1);
});

test('#936: CRLF 改行の本文でも heading / checkbox を認識する', () => {
  // GitHub の `pull_request.body` は CRLF で届く。行ベースの section 抽出が \r で崩れないことを固定。
  const body = templateShapedBody('- [ ] `pytest`').replace(/\n/g, '\r\n');
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
  assert.equal(result.checked, 1);
  assert.equal(result.hasAnySection, true);
});

// --- #967 修正方針 6: fail-closed (節と項目の存在を強制する) ----------------------
//
// heading 形式を認識できなかったとき、これまでは `hasAnySection=false` → skip → **green** だった。
// つまり絵文字前置 / bold 疑似見出し / 全角空白区切り / setext / 節の削除・改名 はすべて
// 「gate が黙って無効化される」false-green になっていた。認識漏れを **red 側に倒す** ことで
// このクラス全体を一括で閉じる (Idios 裁定)。
//
// 必須化の範囲は実測で決めた (実在 merged PR 本文 + テンプレート 29 本):
//   - Self-Test Report 節: 29/29 に存在 → **必須化しても blast radius ゼロ**
//   - 節内の checkbox: 最小 2 件 (0 件の本文は無い) → **1 件以上を必須化してもゼロ**
//   - `## 受け入れ条件` 節: **22/31 に存在しない** (`## 受け入れ条件 (issue #611) 最終判定` のような
//     suffix 形が多く、完全一致 regex では拾えない #936 Q5 (A) 凍結仕様) → **必須にしない**
//   - bot 作成 PR: 実在 1 件 (#831 dependabot) は heading 0 / checkbox 0 / `user.type=Bot`
//     → bot は除外する

test('#967 fail-closed: Self-Test Report 節が無い本文は非ゼロ exit', () => {
  const body = '## 概要\n\n変更の説明。\n\n## 受け入れ条件\n\n- [x] 条件 1\n';
  const { status, stdout } = runCheckerProcess(body);
  assert.equal(status, 1, `exit code が 1 でない (stdout: ${stdout})`);
  assert.match(stdout, /::error::/);
});

test('#967 fail-closed: 節はあるが checkbox が 1 件も無い本文は非ゼロ exit', () => {
  // 項目を plain bullet に落として証跡ゼロで通す bypass を塞ぐ
  const body = `#### ${ST_TITLE}\n\n- ruff check\n- pytest\n`;
  const { status, stdout } = runCheckerProcess(body);
  assert.equal(status, 1, `exit code が 1 でない (stdout: ${stdout})`);
});

test('#967 fail-closed: heading 認識漏れは red になる (絵文字前置)', () => {
  // GitHub は `#### ✅ Self-Test Report` を h4 として描画するが、prefix 一致に落ちる。
  // fail-closed なので「節が無い」と判定して red になり、作者が heading を直せる。
  const body = `## 受け入れ条件\n\n- [x] 条件 1\n\n#### ✅ ${ST_TITLE}\n\n- [ ] pytest\n`;
  const { status } = runCheckerProcess(body);
  assert.equal(status, 1);
});

for (const [label, heading] of [
  ['bold 疑似見出し', `**${ST_TITLE}**`],
  ['全角空白区切り', `####　${ST_TITLE}`],
  ['setext 形', `${ST_TITLE}\n---`],
]) {
  test(`#967 fail-closed: heading 認識漏れは red になる (${label})`, () => {
    const body = `## 受け入れ条件\n\n- [x] 条件 1\n\n${heading}\n\n- [x] pytest\n`;
    const { status } = runCheckerProcess(body);
    assert.equal(status, 1);
  });
}

test('#967 fail-closed: 節を削除しても red になる', () => {
  const body = '## 受け入れ条件\n\n- [x] 条件 1\n\n## 備考\n\n特になし。\n';
  const { status } = runCheckerProcess(body);
  assert.equal(status, 1);
});

test('#967 fail-closed: 受け入れ条件節が無くても Self-Test があれば pass', () => {
  // 実在 merged PR の 22/31 がこの形 (`## 受け入れ条件` の完全一致 heading を持たない)。
  // 受け入れ条件節を必須にすると大量に red になるため必須にしない。
  const body = `## Summary\n\n- 変更概要\n\n#### ${ST_TITLE}\n\n- [x] pytest\n- [x] ruff\n`;
  const { status, stdout } = runCheckerProcess(body);
  assert.equal(status, 0, `exit code が 0 でない (stdout: ${stdout})`);
});

test('#967 fail-closed: bot 作成の PR は節の存在を要求しない', () => {
  // 実在 #831 (dependabot) は heading 0 / checkbox 0。bot に template 遵守は求められない。
  const body = 'Bumps vite from 8.0.9 to 8.0.16.\n\nRelease notes ...\n';
  const asHuman = runCheckerProcess(body);
  const asBot = runCheckerProcess(body, 'Bot');
  assert.equal(asHuman.status, 1, '人間の PR なら red');
  assert.equal(asBot.status, 0, `bot の PR なら pass (stdout: ${asBot.stdout})`);
});

test('#967 fail-closed: bot でも未消化 checkbox があれば red', () => {
  // bot 例外は「節の存在要求」だけを免除する。実際に未消化があるなら落とす。
  const body = `#### ${ST_TITLE}\n\n- [ ] pytest\n`;
  const { status } = runCheckerProcess(body, 'Bot');
  assert.equal(status, 1);
});

test('#967 fail-closed: 実テンプレートを全件 [x] にした本文は pass (対照)', () => {
  const body = templateShapedBody(['- [x] `ruff check .`', '- [x] `pytest`'].join('\n'));
  const { status, stdout } = runCheckerProcess(body);
  assert.equal(status, 0, `exit code が 0 でない (stdout: ${stdout})`);
});

// --- Codex adversarial-review [high] / [medium] の消化 -------------------------

test('#967 fail-closed: bot でも節が認識できて checkbox 0 件なら red', () => {
  // bot 例外は「節の存在要求」だけを免除する。節が認識できているのに項目ゼロなら落とす
  // (Codex [high]: 2 条件を 1 つの分岐にまとめていたため bot が両方すり抜けていた)。
  const body = `#### ${ST_TITLE}\n\n- pytest not run\n`;
  const { status } = runCheckerProcess(body, 'Bot');
  assert.equal(status, 1);
});

test('#967: 対象節の入れ子 (AC 配下の Self-Test) を own kind として認識する', () => {
  // GitHub は両方 heading として描画する。入れ子を親の節に吸収すると selfTestFound が立たず
  // 「節が無い」と誤判定して false-red になる (Codex [medium])。
  const body = '## Acceptance criteria\n\n- [x] criterion\n\n### Self-Test Report\n\n- [x] pytest\n';
  const { status, stdout } = runCheckerProcess(body);
  assert.equal(status, 0, `exit code が 0 でない (stdout: ${stdout})`);
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.hasSelfTestSection, true);
  assert.equal(result.selfTestItems, 1);
  assert.equal(result.checked, 2);
});

test('#967: 入れ子の対象節が閉じたら外側の節が復帰する (数え落ちしない)', () => {
  // 入れ子節を own kind にするだけでは、閉じた後に外側の節へ戻れず後続項目を数え落とす。
  // section stack で外側へ復帰することを固定する。
  const body =
    '## 受け入れ条件\n\n- [x] a\n\n### Self-Test Report\n\n- [x] b\n\n### その他の条件\n\n- [ ] c\n';
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1, '外側の受け入れ条件節に戻って c を数える');
  assert.equal(result.checked, 2);
  assert.equal(result.selfTestItems, 1, 'b だけが Self-Test 節の項目');
});

test('#967 fail-closed: ST 配下に対象節が入れ子でも「項目ゼロ」にならない', () => {
  // `## Self-Test Report` の中に `### Acceptance criteria` を入れ子にすると、stack の先頭が
  // AC になるため「Self-Test 節の項目」を先頭フレームだけで数えると 0 になり、全部 [x] なのに
  // fail-closed で red になる false-red (Codex adversarial-review round 2 [medium])。
  // renderer 実測: Completed 1 / Incomplete 0 = 直すべきものは何も無い本文。
  const body = '## Self-Test Report\n\n### Acceptance criteria\n\n- [x] pytest\n';
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.selfTestItems, 1, 'Self-Test 節の子孫にある項目も Self-Test の項目として数える');
  const { status, stdout } = runCheckerProcess(body);
  assert.equal(status, 0, `exit code が 0 でない (stdout: ${stdout})`);
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

// --- #945: Fable 行の semantic 検査 (Codex adversarial-review [medium] 対応) ---------
//
// checkbox の消化だけを見る gate は「レビューを実行せずに緑」を防げない。
// 以下は **値の妥当性**で red が出ることを示す。従来の「未記入 → red」とは別のクラス。

const { validateFableRow } = require('./check-pr-checklist.js');

const FABLE_ROW_UNRUN = '- [x] Fable 俯瞰レビュー (#945) — 非実施 (理由: doc-only でない)';
const FABLE_ROW_RUN = '- [x] Fable 俯瞰レビュー (#945) — 実施 (finding 2 件 / 消化 2 件 / 残 0 件)';
const FABLE_ROW_PLACEHOLDER =
  '- [x] Fable 俯瞰レビュー (#945) — 実施 (finding N 件 / 消化 M 件 / 残 K 件)';

const DOC_ONLY_FILES = [
  { filename: 'docs/l2-workflow.md', status: 'modified' },
  { filename: 'docs/release-process.md', status: 'modified' },
];
const CODE_FILES = [
  { filename: 'allaganeye/export/pool.py', status: 'modified' },
  { filename: 'docs/cli-spec.md', status: 'modified' },
];
const SPEC_ADDED_FILES = [
  { filename: 'allaganeye/export/pool.py', status: 'modified' },
  { filename: 'docs/superpowers/specs/2026-08-21-x.md', status: 'added' },
];

test('#945 semantic: doc-only PR で `非実施` は red (起動条件 (a) 該当)', () => {
  const r = validateFableRow(FABLE_ROW_UNRUN, DOC_ONLY_FILES);
  assert.equal(r.ok, false);
  assert.match(r.reason, /doc-only/);
});

test('#945 semantic: spec 新規追加 PR で `非実施` は red (起動条件 (b) 該当、code file 混在でも)', () => {
  // code file を含むので doc-only ではない。(b) だけで発火することを示す。
  const r = validateFableRow(FABLE_ROW_UNRUN, SPEC_ADDED_FILES);
  assert.equal(r.ok, false);
  assert.match(r.reason, /specs\/plans/);
});

test('#945 semantic: 通常の code PR で `非実施` は green (対照)', () => {
  // 対照が無いと「何を書いても赤い」だけの gate と区別できない。
  const r = validateFableRow(FABLE_ROW_UNRUN, CODE_FILES);
  assert.equal(r.ok, true);
});

test('#945 semantic: `実施` は N/M/K がプレースホルダのままなら red', () => {
  const r = validateFableRow(FABLE_ROW_PLACEHOLDER, DOC_ONLY_FILES);
  assert.equal(r.ok, false);
  assert.match(r.reason, /整数/);
});

test('#945 semantic: `実施` + 実数 3 件は green', () => {
  const r = validateFableRow(FABLE_ROW_RUN, DOC_ONLY_FILES);
  assert.equal(r.ok, true);
});

test('#945 semantic: files 不明時は skip する (API 可用性で false-red にしない)', () => {
  assert.equal(validateFableRow(FABLE_ROW_UNRUN, null).ok, true);
  assert.equal(validateFableRow(FABLE_ROW_UNRUN, []).ok, true);
});

test('#945 semantic: 生 exit code — doc-only PR の誤った `非実施` で validate-checklist が red', () => {
  // 3 点セット ③。カウント関数ではなく子プロセスの **exit code の生値**で観測する。
  const body = [
    '#### Self-Test Report (machine-verified)',
    '',
    '- [x] `ruff check .`',
    FABLE_ROW_UNRUN,
    '',
  ].join('\n');
  const red = runCheckerProcess(body, undefined, DOC_ONLY_FILES);
  assert.equal(red.status, 1, '起動条件該当なのに非実施なら exit 1');
  assert.match(red.stdout, /::error::/);

  const green = runCheckerProcess(body.replace(FABLE_ROW_UNRUN, FABLE_ROW_RUN), undefined, DOC_ONLY_FILES);
  assert.equal(green.status, 0, '実施 + 実数なら exit 0');
});

// --- #945: 実テンプレートを corpus に使う (合成 fixture では届かなかった) ------------
//
// 上の semantic テストは短い合成行を使っており、**実テンプレート行では false-red が出た**。
// 実物の行は説明文として「実施」「非実施」の両方を含むため、素朴な文字列一致では
// 記入済みと誤認する。合成 fixture だけの発火実証は「実物に届かない gate」を通してしまう。

function realFableRow() {
  const tpl = fs.readFileSync(TEMPLATE_PATH, 'utf8');
  // **checkbox 行に限定する。** コメント内の記入ガイドにも同じ語が出るため、
  // 素朴な includes だと説明文を拾ってしまう (実際に踏んだ)。
  const line = tpl
    .split(/\r?\n/)
    .find((l) => /^[ \t]{0,3}[-*+][ \t]+\[[ xX]\]/.test(l) && l.includes('Fable 俯瞰レビュー'));
  assert.ok(line, 'テンプレートに Fable 行が存在する');
  return line;
}

test('#945 corpus: 実テンプレートの未記入 Fable 行 (placeholder のまま) は red', () => {
  // `[x]` にしただけで中身を置き換えていない = レビューしていない。これを緑にしてはいけない。
  const row = realFableRow().replace('- [ ]', '- [x]');
  const r = validateFableRow(row, DOC_ONLY_FILES);
  assert.equal(r.ok, false);
  assert.match(r.reason, /placeholder/);
});

test('#945 corpus: 実テンプレート行を `実施` + 実数へ置換したら green (false-red が無い)', () => {
  const row = '- [x] Fable 俯瞰レビュー (#945): 実施 (finding 2 件 / 消化 2 件 / 残 0 件)';
  assert.equal(validateFableRow(row, DOC_ONLY_FILES).ok, true);
});

test('#945 corpus: 実テンプレート行を `非実施` へ置換 — code PR なら green / doc-only なら red', () => {
  const row = '- [x] Fable 俯瞰レビュー (#945): 非実施 (理由: doc-only でなく specs/plans 新規追加もなし)';
  assert.equal(validateFableRow(row, CODE_FILES).ok, true, 'code PR では正当');
  assert.equal(validateFableRow(row, DOC_ONLY_FILES).ok, false, 'doc-only では不当');
});
