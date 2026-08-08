// .github/scripts/check-pr-checklist.js
//
// PR 本文の checkbox gate (`validate-checklist` job)。対象節 (受け入れ条件 / Acceptance criteria /
// Self-Test Report) に未消化 checkbox が残っていると `core.setFailed` で job を落とす。
//
// #967 で **1 パスの行スキャナ**に置き換えた。それ以前は「fence 除去 → HTML コメント除去 →
// heading 分割 → checkbox を regex で数える」という多段 replace で、以下の 14 件が GitHub の
// 実レンダリングと乖離していた (すべて `gh api markdown` の出力で可視性を確認済み):
//
// - false-green (可視の未消化があるのに数えない): 0-3 space インデント heading / h1 / h5 / h6 /
//   blockquote 内 heading / U+2011 ハイフンを含む heading text / setext heading /
//   U+3000 区切りの兄弟行が節を打ち切る / HTML コメント内の孤立 fence が節を丸ごと消す
// - false-red (GitHub 上に未消化が無いのに数える): blockquote 内の fence / list 配下 4 space
//   インデントの fence / root の indented code block / U+3000 区切り行を heading と誤認
//
// 多段 replace は「除去の順序」と「heading 側と項目側でインデント・blockquote の許容が非対称」
// という 2 つの構造的な穴を持っていた。軸ごとに regex を足すとモグラ叩きになるため、
// blockquote prefix を剥がした view を 1 本作り、fence / コメント / heading / task item の判定で
// 共有する形に統合した。
//
// **これは Markdown parser ではなく近似である。** 依存は追加しない (`actions/github-script` から
// require するだけの stdlib-only)。近似が見ていない集合は docs/l2-workflow.md
// §「Self-Test Report 規約」 に列挙する。誤りの向きは **false-red 側に倒す** (黙って通す
// false-green より、メッセージが見えて自己修正できる false-red のほうが安全)。

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

/** blockquote prefix (`> ` の連なり)。GitHub は引用内の heading / task item も普通に描画する。 */
const BLOCKQUOTE_PREFIX_RE = /^(?:[ \t]{0,3}>[ \t]?)+/;

/**
 * ATX heading。`#` の直後は **ASCII の space / tab のみ**許容する。
 * CommonMark は全角空白 (U+3000) を区切りとして認めないため、`####　見出し` は GitHub 上では
 * 段落テキストになる。`\s` で許容すると「GitHub には heading が無いのに節を打ち切る」
 * false-green になる (renderer 実測で確認)。
 */
const ATX_HEADING_RE = /^(#{1,6})(?:[ \t]+(.*?))?[ \t]*$/;

/** ATX heading の閉じ側 hashes (`#### 見出し ####`)。GitHub は heading text から落とす。 */
const ATX_CLOSING_HASHES_RE = /[ \t]+#+$/;

/** setext heading の下線。直前が段落行のときだけ heading になる。 */
const SETEXT_UNDERLINE_RE = /^(=+|-+)[ \t]*$/;

/**
 * fenced code block の開始 (CommonMark §4.5)。インデントは list 文脈判定側で扱う。
 *
 * **backtick fence の info string は backtick を含められない** — 含む場合 fence は開かず、
 * 後続行は通常の markdown として描画される。`^```` だけを見て fence 開始とみなすと、
 * ` ``` ` + backtick 入り info string の直後にある**可視の** checkbox を読み飛ばす
 * false-green になる (Codex adversarial-review [high]、renderer 実測で確認)。
 * tilde fence にはこの制約がない。
 */
const FENCE_OPEN_BACKTICK_RE = /^(`{3,})([^`]*)$/;
const FENCE_OPEN_TILDE_RE = /^(~{3,})(.*)$/;

/**
 * fenced code block の終了 (CommonMark §4.5)。
 *
 * **閉じ fence は後続に空白 / tab のみ許す。** `` ``` still code `` のような行は code 内容であって
 * fence を閉じないため、marker prefix だけで閉じると code block を早期に抜けて中の checkbox を
 * 数える false-red になる (Codex adversarial-review [medium]、renderer 実測で確認)。
 */
function isFenceClose(content, marker) {
  const re = new RegExp('^' + marker[0].replace(/[`~]/, '\\$&') + '{' + marker.length + ',}[ \\t]*$');
  return re.test(content);
}

/** fence 開始なら marker 文字列を返す。開始でなければ null。 */
function matchFenceOpen(content) {
  const backtick = FENCE_OPEN_BACKTICK_RE.exec(content);
  if (backtick) return backtick[1];
  const tilde = FENCE_OPEN_TILDE_RE.exec(content);
  if (tilde) return tilde[1];
  return null;
}

/** list item (task list でないものも含む)。list 文脈の追跡に使う。 */
const LIST_ITEM_RE = /^(?:[-*+]|\d+[.)])(?:[ \t]+|$)/;

/**
 * GFM task list item。marker は `-` / `*` / `+` / `1.` / `1)` を許容する。
 *
 * `[ ]` の**直後に空白 (または行末) を要求する** — GFM の task list item はそう定義されており、
 * `- [ ]項目` は通常の list item として描画される。空白を要求しないと GitHub 上に checkbox が
 * 無いのに数える false-red になる (renderer 実測で確認)。
 */
const TASK_ITEM_RE = /^(?:[-*+]|\d+[.)])[ \t]+\[([ xX])\](?=[ \t]|$)/;

/**
 * HTML block (CommonMark §4.6 type 6) の開始タグ。空行まで続き、中身は markdown として
 * 解釈されない。`<details>` / `<div>` を使う PR 本文で、ブロック内の checkbox 記法を
 * 数えてしまう false-red があった (renderer 実測で確認)。
 *
 * 空行を挟めば HTML block は終わるため、`<details>` の後に空行を置いた本文の checkbox は
 * 従来どおり数える (GitHub もそう描画する)。
 */
const HTML_BLOCK_TAGS =
  'address|article|aside|base|basefont|blockquote|body|caption|center|col|colgroup|dd|details|' +
  'dialog|dir|div|dl|dt|fieldset|figcaption|figure|footer|form|frame|frameset|h[1-6]|head|header|' +
  'hr|html|iframe|legend|li|link|main|menu|menuitem|nav|noframes|ol|optgroup|option|p|param|' +
  'search|section|summary|table|tbody|td|tfoot|th|thead|title|tr|track|ul';
const HTML_BLOCK_START_RE = new RegExp('^</?(?:' + HTML_BLOCK_TAGS + ')(?:[ \\t>/]|$)', 'i');

/** インデントがこの値以上で、かつ list 文脈でなければ indented code block とみなす。 */
const INDENTED_CODE_WIDTH = 4;

/** heading text の正規化: Unicode ハイフン類と NBSP 類を ASCII に畳む。 */
const HYPHEN_LIKE_RE = /[‐-―−]/g;
const SPACE_LIKE_RE = /[   ]/g;

function normalizeHeadingText(text) {
  return text.replace(HYPHEN_LIKE_RE, '-').replace(SPACE_LIKE_RE, ' ').trim();
}

/**
 * 行頭の ASCII 空白 (space / tab) のみを「インデント」として扱う (#967 Codex round 3 [high])。
 *
 * JS の `trimStart()` / `trim()` は NBSP や全角空白まで落とすが、CommonMark はそれらを
 * インデントと認めない。`trimStart()` を使うと GitHub 上では**段落テキスト**の行が
 * heading / task item に化け、偽の兄弟 heading が節を打ち切る false-green や、
 * 段落なのに task item として数える false-red になる (renderer 実測で確認)。
 */
const ASCII_INDENT_RE = /^[ \t]*/;
const ASCII_BLANK_LINE_RE = /^[ \t]*$/;

/** 先頭の空白幅 (tab は 4 として数える)。 */
function measureIndent(line) {
  let width = 0;
  for (const ch of line) {
    if (ch === ' ') width += 1;
    else if (ch === '\t') width += 4;
    else break;
  }
  return width;
}

/**
 * 行内の閉じた HTML コメントを除去する。閉じていない `<!--` があれば以降を切り落とし、
 * `openComment: true` を返す (次行以降は `-->` まで読み飛ばす)。
 */
function stripInlineComments(content) {
  let out = '';
  let rest = content;
  for (;;) {
    const start = rest.indexOf('<!--');
    if (start === -1) return { content: out + rest, openComment: false };
    out += rest.slice(0, start);
    const end = rest.indexOf('-->', start + 4);
    if (end === -1) return { content: out, openComment: true };
    rest = rest.slice(end + 3);
  }
}

/**
 * 本文を 1 パスで走査し、対象 section 内の task list item を数える (#967)。
 *
 * section は「自分と同じか浅いレベルの次 heading」で終わる (#936)。したがって
 * - `## 受け入れ条件` は配下の `### 小見出し` を吸収する (実在 PR #956 の形)
 * - `#### Self-Test Report` は兄弟の `#### 関連ドキュメント` で終わる (D9 の 10 box に収まる)
 * - `## Self-Test Report` + `### machine-verified` の形 (実在 PR #909 / #924 / #927) も拾える
 *
 * インデント 4 以上の行の意味は文脈で変わる (renderer 実測):
 * - 直前に list があれば list item の継続 → heading や task item として描画される
 * - そうでなければ indented code block → GitHub は code として描画する
 */
function scanRequiredSections(body) {
  const lines = String(body).split(/\r?\n/);

  let activeLevel = 0; // 0 = 対象 section の外 / >0 = 収集中の section の heading level
  let found = false;
  let unchecked = 0;
  let checked = 0;

  let fenceMarker = null; // fence 内なら開始マーカー文字列
  let fenceQuoteDepth = 0; // fence を開いた行の blockquote 深さ (引用境界で fence を閉じるため)
  let inComment = false;
  let inHtmlBlock = false; // HTML block (type 6) 内。空行まで markdown として解釈しない
  let lastListIndent = null; // 直近の list item のインデント (list 文脈の追跡)
  let paragraphCandidate = null; // 直前の段落行 (setext heading の text 候補)

  for (const raw of lines) {
    const quotePrefix = BLOCKQUOTE_PREFIX_RE.exec(raw);
    const quoteDepth = quotePrefix ? (quotePrefix[0].match(/>/g) || []).length : 0;
    const line = raw.replace(BLOCKQUOTE_PREFIX_RE, '');
    const indent = measureIndent(line);
    let content = line.slice(ASCII_INDENT_RE.exec(line)[0].length);

    // 1. fence 内は何も解釈しない (コメントも heading も code として描画される)
    if (fenceMarker !== null) {
      // 引用が終われば中の fenced block も終わる。blockquote prefix を一律に剥がすだけだと
      // fence が引用境界を越えて残り、引用の外にある**可視の** checkbox を読み飛ばす
      // false-green になる (renderer 実測で確認)。この行は通常処理へ落とす。
      if (quoteDepth < fenceQuoteDepth) {
        fenceMarker = null;
      } else {
        if (isFenceClose(content, fenceMarker)) fenceMarker = null;
        continue;
      }
    }

    // 2. HTML コメントブロックの継続
    if (inComment) {
      const end = content.indexOf('-->');
      if (end === -1) continue;
      inComment = false;
      // `-->` 以降の残りは HTML block の一部で markdown として描画されないため捨てる
      continue;
    }

    // 3. 行頭が `<!--` の行は HTML block。閉じるまで読み飛ばす
    if (content.startsWith('<!--')) {
      if (content.indexOf('-->', 4) === -1) inComment = true;
      paragraphCandidate = null;
      continue;
    }

    // 4. 行中の閉じたコメントは除去 (`- [x] item <!-- note -->` 等)。
    //    **行中で開いたまま閉じないコメントは後続行を飲み込まない** — 行頭 `<!--` は HTML block を
    //    開始するが、行中の `<!--` は inline HTML なので次行の list item 等のブロック構造は
    //    そのまま描画される (renderer 実測: `- [x] a <!-- note` の次行の `- [ ] b` は
    //    Incomplete task として見える)。ここで inComment を立てると可視の項目を読み飛ばす
    //    false-green になる。
    content = stripInlineComments(content).content;

    if (ASCII_BLANK_LINE_RE.test(content)) {
      // 空行は HTML block を終わらせる
      inHtmlBlock = false;
      paragraphCandidate = null;
      continue;
    }

    // 5. HTML block (type 6) は空行まで markdown として解釈されない
    if (inHtmlBlock) continue;
    if (HTML_BLOCK_START_RE.test(content)) {
      inHtmlBlock = true;
      paragraphCandidate = null;
      continue;
    }

    // 6. インデント 4 以上は list 文脈でなければ indented code block
    const inListContext = lastListIndent !== null && indent >= lastListIndent + 2;
    if (indent >= INDENTED_CODE_WIDTH && !inListContext) {
      lastListIndent = null;
      paragraphCandidate = null;
      continue;
    }

    // 7. fence 開始
    const fenceOpen = matchFenceOpen(content);
    if (fenceOpen !== null) {
      fenceMarker = fenceOpen;
      fenceQuoteDepth = quoteDepth;
      paragraphCandidate = null;
      continue;
    }

    // 8. setext heading (直前が段落行のときのみ)
    const setext = SETEXT_UNDERLINE_RE.exec(content);
    if (setext && paragraphCandidate !== null) {
      const level = setext[1][0] === '=' ? 1 : 2;
      ({ activeLevel, found } = enterHeading(paragraphCandidate, level, activeLevel, found));
      // list 継続内の heading なら list はまだ閉じていない (後続の入れ子項目を code と誤認しないため)
      if (!inListContext) lastListIndent = null;
      paragraphCandidate = null;
      continue;
    }

    // 9. ATX heading
    const atx = ATX_HEADING_RE.exec(content);
    if (atx) {
      const text = normalizeHeadingText((atx[2] || '').replace(ATX_CLOSING_HASHES_RE, ''));
      ({ activeLevel, found } = enterHeading(text, atx[1].length, activeLevel, found));
      if (!inListContext) lastListIndent = null;
      paragraphCandidate = null;
      continue;
    }

    // 10. list item / task list item
    if (LIST_ITEM_RE.test(content)) {
      lastListIndent = indent;
      paragraphCandidate = null;
      const task = TASK_ITEM_RE.exec(content);
      if (task && activeLevel) {
        if (task[1] === ' ') unchecked += 1;
        else checked += 1;
      }
      continue;
    }

    // 11. 段落行
    if (!inListContext) lastListIndent = null;
    paragraphCandidate = content;
  }

  return { unchecked, checked, found };
}

/** heading に到達したときの section 状態遷移。 */
function enterHeading(text, level, activeLevel, found) {
  // 同レベル以下の heading に到達したら現在の section は終わり
  let nextActive = activeLevel && level <= activeLevel ? 0 : activeLevel;
  let nextFound = found;
  if (!nextActive && REQUIRED_SECTION_HEADINGS.some((re) => re.test(text))) {
    nextActive = level;
    nextFound = true;
  }
  return { activeLevel: nextActive, found: nextFound };
}

/**
 * 対象 section (受け入れ条件 / Acceptance criteria / Self-Test Report) 内の checkbox を数える。
 * 関数名は既存 doc (docs/superpowers/plans/2026-05-08-lane-iv-b-group-g-implementation.md 等) からの
 * 参照があるため #936 の scope 拡大後も維持している。
 */
function countAcceptanceCriteriaCheckboxes(body) {
  const { unchecked, checked, found } = scanRequiredSections(body);
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
