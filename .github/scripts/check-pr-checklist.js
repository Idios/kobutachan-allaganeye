// .github/scripts/check-pr-checklist.js

/**
 * Fenced code block (` ``` ... ``` ` / `~~~ ... ~~~`) を空文字で除去する。
 * PR 本文に skill spec / template 抜粋を貼ると本文中の `## 受け入れ条件` 等が
 * code block 内 heading として扱われる場合があるため、heading 検出前に除去する。
 *
 * CommonMark §4.5 fenced code blocks に準拠 (PR #688 R2-1 / R2-2 対応):
 * - backtick fence (3+ 個) と tilde fence (3+ 個) の両方に対応
 * - 0-3 space indent (list 内 fence 等) を許容
 * - 4+ space indent は CommonMark で「indented code block」扱いになるため対象外
 *
 * non-greedy + multiline で行頭フェンス対のみ対象 (closed fence のみ除去、
 * 不対称な open fence は残す)。
 */
function stripFencedBlocks(body) {
  return body
    .replace(/^[ ]{0,3}```[\s\S]*?^[ ]{0,3}```/gm, '')   // backtick fence (0-3 space indent)
    .replace(/^[ ]{0,3}~~~[\s\S]*?^[ ]{0,3}~~~/gm, '');  // tilde fence (0-3 space indent)
}

/**
 * `[x]` を CI で要求する section の heading (#936)。
 *
 * - 受け入れ条件 / Acceptance criteria: **完全一致**。suffix 付き (`## 受け入れ条件 (追加)`) は
 *   対象外として凍結済み (spec 2026-05-08-lane-iv-b-group-g-design.md Q5 (A))
 * - Self-Test Report: **prefix match**。実物の heading は
 *   `#### Self-Test Report (machine-verified — 全件 [x] で validate-checklist 通過)` と
 *   括弧書きが付くため、完全一致では拾えない
 *
 * `### Iron Law 1: 受け入れ条件検証` のような prefix/suffix 付き heading は完全一致側で弾かれる
 * (D9 の blast radius: Iron Law 1/3/4 群と関連ドキュメント群は gate 対象外のまま)。
 */
const REQUIRED_SECTION_HEADINGS = [
  /^(受け入れ条件|acceptance\s+criteria)\s*$/i,
  /^self[-\s]?test\s+report\b/i,
];

/** section 開始として認識する heading level。h1 と h5 以下は開始とみなさない (実在 PR 本文は h2-h4 のみ)。 */
const MIN_SECTION_LEVEL = 2;
const MAX_SECTION_LEVEL = 4;

const HEADING_RE = /^(#{1,6})\s+(.*)$/;

/**
 * 対象 section の本文を heading level 準拠で抽出する (#936)。
 *
 * section は「自分と同じか浅いレベルの次 heading」で終わる。したがって
 * - `## 受け入れ条件` は配下の `### 小見出し` を本文として吸収する (実在 PR #956 の形。
 *   heading level を見ずに h2-h4 で素朴に split すると、この形で既存 gate が丸ごと無効化される)
 * - `#### Self-Test Report` は兄弟の `#### 関連ドキュメント` で終わる (D9 の 10 box に収まる)
 * - `## Self-Test Report` + `### machine-verified` の形 (実在 PR #909 / #924 / #927) も拾える
 *
 * heading 行自体は本文に含めない。
 */
function extractRequiredSections(body) {
  const lines = stripHtmlComments(stripFencedBlocks(body)).split(/\r?\n/);
  const collected = [];
  let activeLevel = 0; // 0 = 収集していない / >0 = 収集中の section の heading level
  let found = false;

  for (const line of lines) {
    const match = HEADING_RE.exec(line);
    if (!match) {
      if (activeLevel) collected.push(line);
      continue;
    }
    const level = match[1].length;
    const heading = match[2].trim();

    // 同レベル以下の heading に到達したら現在の section は終わり
    if (activeLevel && level <= activeLevel) activeLevel = 0;

    const isSectionStart =
      !activeLevel &&
      level >= MIN_SECTION_LEVEL &&
      level <= MAX_SECTION_LEVEL &&
      REQUIRED_SECTION_HEADINGS.some((re) => re.test(heading));
    if (isSectionStart) {
      activeLevel = level;
      found = true;
      continue;
    }
    // section 配下の深い heading は本文として吸収する
    if (activeLevel) collected.push(line);
  }
  return { text: collected.join('\n'), found };
}

/**
 * 対象 section (受け入れ条件 / Acceptance criteria / Self-Test Report) 内の checkbox を数える。
 * 関数名は既存 doc (docs/superpowers/plans/2026-05-08-lane-iv-b-group-g-implementation.md 等) からの
 * 参照があるため #936 の scope 拡大後も維持している。
 */
/**
 * HTML コメント (`<!-- ... -->`) を除去する (#936 Codex adversarial-review round 1 [high])。
 *
 * GitHub 上でレンダリングされないコメント行が heading とみなされて section を打ち切り、
 * その後ろにある**可視の** `- [ ]` が数えられない false-green があった (base 実装からの既存穴。
 * `## 受け入れ条件` 節でも同じ入力で再現する)。テンプレート抜粋をコメントで貼る本文で実際に起きる。
 *
 * 逆向きに、コメント内の `- [ ]` (記入例など) も数えなくなる。不可視の項目で CI を red に
 * するほうが不当なので、これは意図した挙動である。
 *
 * fence 内に `<!--` が現れる場合を避けるため fence 除去の後に適用する。
 * 閉じていない `<!--` は除去しない (閉じフェンスのみ除去する `stripFencedBlocks` の方針に合わせる)。
 */
function stripHtmlComments(text) {
  return text.replace(/<!--[\s\S]*?-->/g, '');
}

function countAcceptanceCriteriaCheckboxes(body) {
  const { text, found } = extractRequiredSections(body);
  const unchecked = (text.match(/- \[ \]/g) || []).length;
  const checked = (text.match(/- \[x\]/gi) || []).length;
  return { unchecked, checked, hasAnySection: found };
}

// async は actions/github-script@v7 caller (`await checker({github, context, core})`) との
// 互換のため維持。内部に await はないが、yml 側 `await` を可能にするため Promise 返却が必要。
async function checkPrChecklist({ github, context, core }) {
  const body = context.payload.pull_request.body || '';
  const { unchecked, checked, hasAnySection } = countAcceptanceCriteriaCheckboxes(body);
  if (!hasAnySection) {
    core.info(
      'No `受け入れ条件` / `Acceptance criteria` / `Self-Test Report` section found, skipping.'
    );
    return;
  }
  if (unchecked > 0) {
    core.setFailed(
      `PR has ${unchecked} unchecked item(s) in \`受け入れ条件\` / \`Acceptance criteria\` / \`Self-Test Report\` section(s). ` +
        'Please complete all items before merging. ' +
        'machine-unverifiable な項目は checkbox ではなく plain bullet `-` で書くこと (docs/l2-workflow.md §Self-Test Report 規約)。'
    );
    return;
  }
  core.info(`All ${checked} required checklist item(s) are checked.`);
}

module.exports = checkPrChecklist;
module.exports.countAcceptanceCriteriaCheckboxes = countAcceptanceCriteriaCheckboxes;
