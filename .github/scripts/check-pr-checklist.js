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
//   blockquote 内 heading / U+2011 ハイフンを含む heading text /
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
// require するだけの stdlib-only)。誤りの向きは **false-red 側に倒す** (黙って通す false-green より、
// メッセージが見えて自己修正できる false-red のほうが安全)。
//
// この gate が見ていない / 近似している集合の**要約**。
// **完全な一覧と根拠数値は docs/l2-workflow.md §「Self-Test Report 規約」が SSoT** で、ここはその要約 +
// ポインタである (doc だけに置くと次の実装者に届かないため要約を置くが、「同内容」と書くと片方だけ
// 更新されたときに嘘になるので同一性は主張しない):
//
// - **節と項目の存在は強制される (fail-closed、#967 修正方針 6)**。`Self-Test Report` 節が認識できない、
//   または節内に checkbox が 1 件も無い場合は skip せず `core.setFailed` で落とす。heading 形式の
//   認識漏れ (bold 疑似見出し / 全角空白区切り / setext / 絵文字前置 / 改名 / plain bullet 化) は
//   すべて red 側に倒れる。bot 作成 PR (`user.type === "Bot"`) だけは存在要求を skip する。
//   `受け入れ条件` 節は**必須にしていない** (直近 merged PR 200 本のうち完全一致 heading を持つのは
//   16 本だけ = 184 本が suffix 形。必須化すると大量に red になる)
// - bold 疑似見出しや全角空白区切りの見出しは GitHub 側でも heading にならないため上記と同じ扱い
// - インデント 4 以上の解釈は「開いている list の最も浅いインデント」で近似する。list item の
//   content indent を超える深い入れ子 (6-8 space 等) は GitHub が code とするのに数える (false-red)
// - 未閉鎖の fence / 行頭 `<!--` は **開いた container の終端まで** 読み飛ばす。root で開いた場合は
//   文書末まで (GitHub と一致)、list / blockquote 内で開いた場合はその container の終端で閉じる
// - HTML block は type 1 (`pre` / `script` / `style` / `textarea`、閉じタグまで) と type 6
//   (ブロック要素タグ、空行まで) のみ扱う。type 7 (任意タグ単独行) は近似していない (false-red)
// - raw HTML の `<h2>` 等は heading として節を閉じない (HTML block として読み飛ばすだけ)
// - heading text は Unicode ハイフン類と NBSP 類のみ ASCII に畳む。link 化した heading
//   (`## [受け入れ条件](#ac)`) は完全一致に落ちるため対象外
// - 受け入れ条件節の heading は完全一致のため suffix 付きは対象外 (#936 Q5 (A) で凍結)
// - **既知の false-green (節は認識されるので fail-closed では拾えない形)**: 折り返し行 (lazy
//   continuation) の直後に 4 space 入れ子の項目を置く形 / 継続行を左端に流した形 / list item 配下に
//   字下げした小見出しを置く形 / Self-Test 節を blockquote で引用しただけの本文。realism と
//   既知の false-red も含めた完全な一覧は doc 側を参照
// - **setext heading (`見出し` + `---` / `===`) は認識しない。** GitHub は setext を heading に
//   するが、実測で「setext を使う本文は 31 本中 0 件 / `---` 区切りを含む本文は 3 件」であり、
//   段落直後の `---` を setext と解釈すると**偽の heading が対象節を打ち切る false-green** が出る
//   (実在 PR #943 の本文に `---` を 1 行足すと exit 1 → exit 0 に反転した)。得るもの 0 / 害 3 なので
//   認識しない側に倒した。代償として setext 形の対象節は gate 対象外になる

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
const REQUIRED_SECTION_PATTERNS = [
  { kind: 'acceptance', re: /^(受け入れ条件|acceptance\s+criteria)\s*$/i },
  { kind: 'selfTest', re: /^self[-\s]?test\s+report\b/i },
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
 * box の中身は **1 文字の空白 (ASCII space / tab / 全角空白 / NBSP など) または `x` / `X`**。
 * GFM は Unicode 空白 1 文字でも未消化として描画するので、ASCII space 固定にすると日本語 IME の
 * 全角空白や copy-paste の NBSP で**可視の未消化が素通り**する (renderer 実測)。
 *
 * `[ ]` の**直後に空白 (または行末) を要求する** — GFM の task list item はそう定義されており、
 * `- [ ]項目` は通常の list item として描画される。空白を要求しないと GitHub 上に checkbox が
 * 無いのに数える false-red になる (renderer 実測で確認)。
 */
const TASK_ITEM_RE = /^(?:[-*+]|\d+[.)])[ \t]+\[([xX]|\s)\](?=[ \t]|$)/;

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

/**
 * HTML block (CommonMark §4.6 type 1)。`<pre>` / `<script>` / `<style>` / `<textarea>` は
 * **閉じタグまで**続き、空行では終わらない。Self-Test Report にログを貼るとき `<pre>` を使うと、
 * 中の checkbox 記法を数える false-red になる (renderer 実測で確認)。
 */
const HTML_TYPE1_START_RE = /^<(pre|script|style|textarea)(?:[ 	>]|$)/i;

/**
 * type 1 HTML block の終了条件 (CommonMark §4.6): 行が `</pre>` / `</script>` / `</style>` /
 * `</textarea>` を**文字列として含む**こと。空白を挟んだ `</pre >` では閉じず、`</pres>` のような
 * near-miss でも閉じない (どちらも renderer で GitHub の挙動を確認済み)。
 */
function hasType1CloseTag(content, tag) {
  return content.toLowerCase().includes('</' + tag.toLowerCase() + '>');
}

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

  const sectionStack = []; // 対象節の入れ子を保持する ({ level, kind })。入れ子が閉じたら外側へ復帰する
  let found = false;
  let selfTestFound = false; // Self-Test Report 節が存在したか (fail-closed の判定に使う)
  let selfTestItems = 0; // Self-Test Report 節内の checkbox 件数 (0 件も red にする)
  const selfTestRows = []; // Self-Test Report 節内の task 行本文 (#945 の Fable 行走査に使う)
  let unchecked = 0;
  let checked = 0;

  let fenceMarker = null; // fence 内なら開始マーカー文字列
  let fenceQuoteDepth = 0; // fence を開いた行の blockquote 深さ (引用境界で fence を閉じるため)
  let fenceIndent = 0; // fence を開いた行のインデント (container 終端で fence を閉じるため)
  let fenceInList = false; // fence を list container 内で開いたか (top level の indent 付き fence と区別)
  let inComment = false;
  let inHtmlBlock = false; // HTML block (type 6) 内。空行まで markdown として解釈しない
  let htmlType1Tag = null; // HTML block (type 1) 内なら tag 名。閉じタグまで解釈しない
  let lastListIndent = null; // 直近の list item のインデント (list 文脈の追跡)

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
      } else if (isFenceClose(content, fenceMarker)) {
        fenceMarker = null;
        continue;
      } else if (fenceInList && !ASCII_BLANK_LINE_RE.test(content) && indent < fenceIndent) {
        // fence を開いた list container が終わればその中の code block も終わる。
        // **list 内で開いた fence にのみ適用する** — top level の 0-3 space インデント fence は
        // 中の列 0 行も code 内容なので、ここで閉じると誤爆する (renderer 実測で確認)。
        // 閉じ忘れた fence が EOF まで残ると、後続の対象節ごと読み飛ばして
        // `hasAnySection=false` で gate が丸ごと skip される (実測した regression)。
        // GitHub は列が浅くなった行で container と code block を閉じる。この行は通常処理へ落とす。
        fenceMarker = null;
      } else {
        continue;
      }
    }

    // 2. HTML block (type 1) の継続。閉じタグまで markdown として解釈しない (空行では終わらない)
    if (htmlType1Tag !== null) {
      if (hasType1CloseTag(content, htmlType1Tag)) htmlType1Tag = null;
      continue;
    }

    // 3. HTML コメントブロックの継続
    if (inComment) {
      const end = content.indexOf('-->');
      if (end === -1) continue;
      inComment = false;
      // `-->` 以降の残りは HTML block の一部で markdown として描画されないため捨てる
      continue;
    }

    // 4. 行頭が `<!--` の行は HTML block。閉じるまで読み飛ばす
    if (content.startsWith('<!--')) {
      if (content.indexOf('-->', 4) === -1) inComment = true;
      continue;
    }

    // 5. 行中の閉じたコメントは除去 (`- [x] item <!-- note -->` 等)。
    //    **行中で開いたまま閉じないコメントは後続行を飲み込まない** — 行頭 `<!--` は HTML block を
    //    開始するが、行中の `<!--` は inline HTML なので次行の list item 等のブロック構造は
    //    そのまま描画される (renderer 実測: `- [x] a <!-- note` の次行の `- [ ] b` は
    //    Incomplete task として見える)。ここで inComment を立てると可視の項目を読み飛ばす
    //    false-green になる。
    content = stripInlineComments(content).content;

    if (ASCII_BLANK_LINE_RE.test(content)) {
      // 空行は HTML block を終わらせる
      inHtmlBlock = false;
      continue;
    }

    // 6. HTML block (type 1) の開始
    const type1 = HTML_TYPE1_START_RE.exec(content);
    if (type1) {
      if (!hasType1CloseTag(content, type1[1])) htmlType1Tag = type1[1];
      continue;
    }

    // 7. HTML block (type 6) は空行まで markdown として解釈されない
    if (inHtmlBlock) continue;
    if (HTML_BLOCK_START_RE.test(content)) {
      inHtmlBlock = true;
      continue;
    }

    // 8. インデント 4 以上は list 文脈でなければ indented code block
    const inListContext = lastListIndent !== null && indent >= lastListIndent + 2;
    if (indent >= INDENTED_CODE_WIDTH && !inListContext) {
      lastListIndent = null;
      continue;
    }

    // 9. fence 開始
    const fenceOpen = matchFenceOpen(content);
    if (fenceOpen !== null) {
      fenceMarker = fenceOpen;
      fenceQuoteDepth = quoteDepth;
      fenceIndent = indent;
      fenceInList = inListContext;
      continue;
    }

    // 10. ATX heading
    const atx = ATX_HEADING_RE.exec(content);
    if (atx) {
      const text = normalizeHeadingText((atx[2] || '').replace(ATX_CLOSING_HASHES_RE, ''));
      const level = atx[1].length;
      // 同レベル以下の heading に到達した節は閉じる。stack なので**入れ子が閉じたら外側へ復帰**する
      // (入れ子の対象節を親に吸収すると selfTestFound が立たず false-red になり、逆に単純に
      //  置き換えると入れ子の後で外側の節に戻れず数え落ちる。Codex adversarial-review [medium])
      while (sectionStack.length && level <= sectionStack[sectionStack.length - 1].level) {
        sectionStack.pop();
      }
      const hit = REQUIRED_SECTION_PATTERNS.find((pattern) => pattern.re.test(text));
      if (hit) {
        sectionStack.push({ level, kind: hit.kind });
        found = true;
        if (hit.kind === 'selfTest') selfTestFound = true;
      }
      if (!inListContext) lastListIndent = null;
      continue;
    }

    // 11. list item / task list item
    if (LIST_ITEM_RE.test(content)) {
      // **最も浅い** list インデントを保持する。入れ子項目で値を上げてしまうと、直後の
      // 同じインデントの**兄弟**が `indent >= lastListIndent + 2` を満たさず indented code
      // 扱いで落ちる (GitHub 上に見える未消化項目を落とす実測 regression)。
      lastListIndent = lastListIndent === null ? indent : Math.min(lastListIndent, indent);
      const task = TASK_ITEM_RE.exec(content);
      if (task && sectionStack.length) {
        if (/[xX]/.test(task[1])) checked += 1;
        else unchecked += 1;
        // Self-Test 節の**子孫**にある項目も Self-Test の項目として数える。先頭フレームだけで
        // 判定すると、`## Self-Test Report` 配下に `### Acceptance criteria` を入れ子にした本文で
        // 件数が 0 になり、全部 [x] なのに fail-closed が red にする false-red が出る
        // (Codex adversarial-review round 2 [medium]、renderer 実測で確認)。
        if (sectionStack.some((frame) => frame.kind === 'selfTest')) {
          selfTestItems += 1;
          selfTestRows.push(content);
        }
      }
      continue;
    }

    // 12. 段落行
    if (!inListContext) lastListIndent = null;
  }

  return { unchecked, checked, found, selfTestFound, selfTestItems, selfTestRows };
}

/**
 * 対象 section (受け入れ条件 / Acceptance criteria / Self-Test Report) 内の checkbox を数える。
 * 関数名は既存 doc (docs/superpowers/plans/2026-05-08-lane-iv-b-group-g-implementation.md 等) からの
 * 参照があるため #936 の scope 拡大後も維持している。
 */
function countAcceptanceCriteriaCheckboxes(body) {
  const { unchecked, checked, found, selfTestFound, selfTestItems, selfTestRows } =
    scanRequiredSections(body);
  return {
    unchecked,
    checked,
    hasAnySection: found,
    hasSelfTestSection: selfTestFound,
    selfTestItems,
    selfTestRows,
  };
}

const FABLE_LABEL_RE = /Fable[ 	　]*俯瞰レビュー/;
// 未記入 placeholder の検出は **既知のトークンのみ**を見る。
// 「山括弧が 1 組でもあれば未記入」とすると、正当な回答に含まれる <URL> や型名まで
// 弾いて false-red になる (Codex adversarial-review round 2 [low])。
const FABLE_PLACEHOLDER_RE = /finding[ 	]*N|消化[ 	]*M|残[ 	]*K|理由:[ 	]*\.\.\.|置き換える/;

function isDocPath(p) {
  // `.claude/skills/**/*.md` のような**振る舞いを規定する prompt** も documentation 側に含める。
  // Fable の担当は「文書・方針・プロセス」(CLAUDE.md §Fable と Codex の棲み分け) であり、
  // skill prompt の改訂はまさにその対象。したがって拡張子 .md は一律 doc として扱う (#945 で明示)。
  return p.startsWith('docs/') || p.toLowerCase().endsWith('.md');
}

function isSpecOrPlanPath(p) {
  return p.startsWith('docs/superpowers/specs/') || p.startsWith('docs/superpowers/plans/');
}

/** 起動条件: (a) doc-only PR / (b) specs・plans への新規ファイル追加 */
function launchConditionApplies(files) {
  if (!Array.isArray(files) || files.length === 0) return false;
  const docOnly = files.every((f) => isDocPath(f.filename));
  const addedSpecOrPlan = files.some((f) => f.status === 'added' && isSpecOrPlanPath(f.filename));
  return docOnly || addedSpecOrPlan;
}

/**
 * Fable 俯瞰レビュー行の semantic 検査 (#945)。
 *
 * **走査対象は Self-Test Report 節の task 行だけ** (`selfTestRows`)。本文全体から
 * 最初に見つかった 1 行を見る実装では、節の外に準拠した decoy 行を置いたり、
 * 行ごと削除したりで gate を無効化できた (Codex adversarial-review round 2 [high])。
 * 節内に**ちょうど 1 本**を必須とし、不在・重複・未記入はすべて red にする。
 *
 * `files` は「完全に取得できた変更ファイル一覧」。取得できなかった場合は **fail-closed**
 * (呼び出し側が red にする)。required status check で silent skip は false-green だから
 * (同 round 2 [medium])。
 *
 * @returns {{ ok: true } | { ok: false, reason: string }}
 */
function validateFableRow(selfTestRows, files) {
  const rows = (selfTestRows || []).filter((r) => FABLE_LABEL_RE.test(r));

  // 行の不在は **起動条件に該当する PR でのみ** red。該当しない PR にまで行の存在を
  // 強制すると、Fable と無関係な PR が本欄の有無で落ちる。
  // 該当 PR での削除は塞がる = round 2 [high] の bypass は閉じている。
  if (rows.length === 0) {
    if (launchConditionApplies(files)) {
      return {
        ok: false,
        reason:
          'Fable 俯瞰レビューの起動条件に該当する PR ですが、Self-Test Report 節に ' +
          '`Fable 俯瞰レビュー` の行がありません。テンプレートの行を削除・改変しないでください ' +
          '(節の外に置いた行は数えません)。',
      };
    }
    return { ok: true };
  }
  if (rows.length > 1) {
    return {
      ok: false,
      reason: `Self-Test Report 節に \`Fable 俯瞰レビュー\` の行が ${rows.length} 本あります。1 本にしてください。`,
    };
  }
  const row = rows[0];

  if (FABLE_PLACEHOLDER_RE.test(row)) {
    return {
      ok: false,
      reason:
        'Fable 俯瞰レビュー行が未記入です (テンプレートの placeholder が残っています)。' +
        '`実施 (finding <実数> 件 / 消化 <実数> 件 / 残 <実数> 件)` か `非実施 (理由: ...)` に置き換えてください。',
    };
  }

  if (/未実施|未実行/.test(row)) {
    return {
      ok: false,
      reason:
        'Fable 俯瞰レビュー行に `未実施` / `未実行` と書かれています。' +
        '本欄の語彙は `実施` または `非実施` の 2 つだけです (`非実施` は起動条件に該当しなかったことを意味します)。',
    };
  }

  const declaredHijisshi = /非実施/.test(row);
  const declaredJisshi = !declaredHijisshi && /実施/.test(row);
  if (!declaredJisshi && !declaredHijisshi) {
    return { ok: false, reason: 'Fable 俯瞰レビュー行が `実施` / `非実施` のどちらでもありません。' };
  }

  if (declaredJisshi) {
    const nums = row.match(/(?:finding|消化|残)[^0-9]{0,8}(\d+)[ 	]*件/g) || [];
    if (nums.length < 3) {
      return {
        ok: false,
        reason:
          '`実施` と記入されていますが finding / 消化 / 残 の 3 数値が整数で揃っていません。' +
          '実際にレビューを実行して実数を記入してください。',
      };
    }
    return { ok: true };
  }

  // 非実施 — 起動条件に該当していないことを変更ファイルで裏取りする (files は完全前提)
  const docOnly = files.every((f) => isDocPath(f.filename));
  const addedSpecOrPlan = files.some((f) => f.status === 'added' && isSpecOrPlanPath(f.filename));
  if (docOnly || addedSpecOrPlan) {
    const which = [docOnly ? '(a) doc-only PR' : null, addedSpecOrPlan ? '(b) specs/plans への新規追加' : null]
      .filter(Boolean)
      .join(' / ');
    return {
      ok: false,
      reason:
        `Fable 俯瞰レビューの起動条件 ${which} に該当していますが \`非実施\` と記入されています。` +
        '`Agent(subagent_type=allaganeye-fable-consult)` を実行し ' +
        '`実施 (finding N 件 / 消化 M 件 / 残 K 件)` を実数で記入してください。',
    };
  }
  return { ok: true };
}

// async は actions/github-script@v7 caller (`await checker({github, context, core})`) との
// 互換のため維持。内部に await はないが、yml 側 `await` を可能にするため Promise 返却が必要。
async function checkPrChecklist({ github, context, core }) {
  const pr = context.payload.pull_request;
  const body = pr.body || '';
  const isBot = Boolean(pr.user && pr.user.type === 'Bot');
  const { unchecked, checked, hasSelfTestSection, selfTestItems, selfTestRows } =
    countAcceptanceCriteriaCheckboxes(body);

  if (unchecked > 0) {
    core.setFailed(
      `PR has ${unchecked} unchecked item(s) in \`受け入れ条件\` / \`Acceptance criteria\` / \`Self-Test Report\` section(s). ` +
        'Please complete all items before merging. ' +
        'machine-unverifiable な項目は checkbox ではなく plain bullet `-` で書くこと (docs/l2-workflow.md §Self-Test Report 規約)。'
    );
    return;
  }

  // fail-closed (#967 修正方針 6): 節が認識できない / 項目が 1 件も無い場合は skip せず落とす。
  // heading 形式の認識漏れ (絵文字前置 / bold 疑似見出し / 全角空白区切り / setext / 改名) は
  // 従来ここで silent pass になっており、gate が黙って無効化される false-green の温床だった。
  //
  // **bot 例外は「節が存在しない」場合だけに限る。** 2 条件を 1 つの分岐にまとめると、節が
  // 認識できているのに項目ゼロという状態まで bot がすり抜ける (Codex adversarial-review [high])。
  if (!hasSelfTestSection && isBot) {
    // bot 作成 PR (dependabot 等) に template 遵守は求められない。未消化 checkbox があれば
    // 上の分岐で既に落ちているので、ここで skip しても gate は弱くならない。
    core.info(`Bot-authored PR (${pr.user.login}): skipping Self-Test Report presence check.`);
    return;
  }
  if (!hasSelfTestSection || selfTestItems === 0) {
    const detail = !hasSelfTestSection
      ? 'No `Self-Test Report` section was recognized in the PR body.'
      : 'The `Self-Test Report` section contains no checkbox items.';
    core.setFailed(
      `${detail} ` +
        'PR 本文に `#### Self-Test Report ...` 節を置き、実行した自動チェックを `- [x] ...` で列挙してください。 ' +
        '認識される形: ATX heading (`#` 1-6 個 + ASCII space/tab)、0-3 space インデント、blockquote 内、閉じ ATX。 ' +
        '認識されない形: bold 疑似見出し (`**Self-Test Report**`)、`#` の直後が全角空白、setext (下線 `---`)、heading 先頭に絵文字などの前置文字。 ' +
        '詳細は docs/l2-workflow.md §「Self-Test Report 規約」を参照。'
    );
    return;
  }

  // #945: Fable 行の semantic 検査。checkbox の消化だけでは「実行せずに緑」を防げない。
  // **files が完全に取れなければ fail-closed**。required status check で silent skip は
  // false-green (Codex adversarial-review round 2 [medium])。workflow 側で
  // `permissions: pull-requests: read` を宣言済み。
  let files = null;
  let fileError = null;
  try {
    if (!github || !github.rest || !github.rest.pulls || !context.repo || !pr.number) {
      fileError = 'GitHub API client unavailable';
    } else {
      const params = {
        owner: context.repo.owner,
        repo: context.repo.repo,
        pull_number: pr.number,
        per_page: 100,
      };
      if (typeof github.paginate === 'function') {
        files = await github.paginate(github.rest.pulls.listFiles, params);
      } else {
        const res = await github.rest.pulls.listFiles(params);
        const page = (res && res.data) || [];
        // paginate 不可 + 1 page 満杯 = 続きがあるかもしれない。部分リストで判定しない。
        if (page.length >= params.per_page) fileError = 'file list may be truncated (no paginate)';
        else files = page;
      }
    }
  } catch (e) {
    fileError = e.message;
  }
  if (!files || files.length === 0) {
    core.setFailed(
      `PR の変更ファイル一覧を取得できませんでした (${fileError || 'empty file list'})。` +
        'Fable 俯瞰レビュー欄の検査が成立しないため fail-closed で落としています。' +
        'job を再実行するか、workflow の `permissions: pull-requests: read` を確認してください。'
    );
    return;
  }
  const fable = validateFableRow(selfTestRows, files);
  if (!fable.ok) {
    core.setFailed(
      `${fable.reason} 詳細は .claude/skills/review-pr/SKILL.md §「optional 俯瞰レビュー」を参照。`
    );
    return;
  }

  core.info(`All ${checked} required checklist item(s) are checked.`);
}

module.exports = checkPrChecklist;
module.exports.countAcceptanceCriteriaCheckboxes = countAcceptanceCriteriaCheckboxes;
module.exports.validateFableRow = validateFableRow;
// #946: `check-preflight-freshness.js` が「GitHub が隠す範囲」の判定を共有するために使う。
// 同じ近似を 2 本持つと、片方だけ renderer 実測に追従して乖離する (#967 が潰した乖離 14 件と
// 同じ構図)。判定は 1 箇所に置く。
module.exports.stripInlineComments = stripInlineComments;
