// .github/scripts/check-preflight-freshness.js
//
// PR 作成 Pre-flight (Iron Law 6 サブ条) の **鮮度** を機械検証する gate (#946)。
// PR 本文が宣言した「Pre-flight 時点の open PR 集合」と、CI 側で再サンプリングした
// 「自 PR 作成時点 (T0) で open だった集合」の差分を取り、宣言に無い PR が 1 件でもあれば落とす。
//
// ## なぜ base OID 一致比較ではないのか (最重要の設計制約)
//
// 事象 E2 (PR #939) では Pre-flight 実行 13:07 UTC → PR 作成 14:13 UTC の **66 分間、
// base `release/v0.3.0` の HEAD は 1 度も動いていない** (直前の merge は 12:34:52 の #930、
// 次は 14:21:12 の #938)。したがって「Pre-flight 時の base OID と PR 作成時の OID が一致するか」
// を検査しても **green になる**。本件を捕まえられるのは **open-PR 集合の再サンプリング**だけ。
// OID 比較は実装が楽なので、この制約を落とすと「対策済み」の false-green が出来上がる。
// `pull_request_template.md` の `- PR 作成時の base HEAD:` 欄は別目的として残してよいが、
// **それを検証しても本件には無力**である。
//
// ## なぜ「今 open な集合」ではなく「T0 時点で open だった集合」なのか
//
// job は `opened` だけでなく `edited` でも走る。「今」を基準にすると、自 PR より後に open した
// PR が再サンプリングに混入して **false-red** になり、本文を編集するたびに結果が変わる
// (非決定的な gate はすぐに無視されるようになる)。そこで `created_at` / `closed_at` から
// **T0 時点の open 集合を再構成**し、いつ job を再実行しても同じ答えになるようにしている。
// 宣言時刻 T_preflight <= T0 なので、その間に open した PR は「実集合にあって宣言に無い」side に
// 落ちる = 検出したいものがちょうど検出される。
//
// ## この gate が見ていない集合 (false-green。**この節を落とすと「網羅している」と誤読される**)
//
// - **宣言フィールドは自己申告**。「#938 も宣言済み」と後から書けば緑になる。ただし宣言した
//   時点で「見落とし」ではなくなり、握り潰しには PR body の改竄が必要 = **監査可能**である
//   (これが `PreToolUse` hook 案より弱くない根拠。hook 案は bypass 4 経路がある — #946 参照)。
//   **「監査可能」は宣言が 1 箇所に定まっていて初めて成立する。** 本文のどこかに decoy 宣言を
//   仕込んで可視のテンプレート欄を `なし` のまま残せると、レビュアが見る欄と gate が読む欄が
//   食い違い監査可能性そのものが壊れる。そのため宣言は **行頭の list item に限り**、同じ label が
//   2 本以上あれば採用せず fail-closed にする (Codex adversarial-review [high])。
//   fenced code block / HTML コメント (行頭ブロック・行中の閉じたもの) の中身は読まない。
//   **「読む / 読まない」の境界は推測ではなく `gh api markdown` の実測に合わせてある** —
//   詳細と実測結果は `visibleLines` の docstring を参照。判定関数は `check-pr-checklist.js` と
//   共有する (近似を 2 本持つと片方だけ実測に追従して乖離する)
// - **宣言が実集合の superset でも通す**。Pre-flight 後に閉じた PR を宣言に残したケースを
//   false-red にしないための意図的な片側検査であり、「実在しない PR 番号を並べて緑にする」
//   経路は塞いでいない
// - **`Refs #N` 記法に依存する**。`Refs` を書かない PR (release PR 等) では same-issue 側の
//   実集合が空になり、その半分は実質 no-op になる。same-base 側は base 名だけで決まるので生きる
// - **同 issue の判定は title / body の `#N` 言及**で行う。issue を本文に書かずに作業した PR は
//   同 issue 集合に入らない
// - **bot 作成 PR (`user.type === "Bot"`) は宣言を要求しない**。dependabot 等に template 遵守を
//   求めないため。bot PR 自身は他 PR の実集合には引き続き現れる
// - **API 失敗は fail-closed**。retry を尽くして取れなければ落とす。fail-open にすると
//   権限剥奪や rate limit で **常時 no-op** になり、gate が静かに死ぬ
// - 走査には**ページ上限**がある。上限に達したら「取り切れなかった」として fail-closed に
//   する (部分リストで「差分なし」と判定しない)
// - `pulls.list` の応答も untrusted 境界として扱い、`number` / `created_at` / `closed_at` /
//   `updated_at` / `base.ref` が壊れていたら **候補を捨てずに落とす**。filter で捨てると
//   競合 PR が実集合から消えて緑になる (Codex adversarial-review [medium])
// - **`Refs` の抽出は fence / コメントを区別しない** (宣言側とは非対称)。誤って多く拾う方向は
//   「宣言すべき PR が増える」= false-red 側なので、意図的に緩いままにしている

'use strict';

// 「GitHub が隠す範囲」の判定は `check-pr-checklist.js` と共有する (下記 `visibleLines` 参照)。
const { stripInlineComments } = require('./check-pr-checklist.js');

const SAME_ISSUE_LABEL = 'Pre-flight 時点の同 issue open PR';
const SAME_BASE_LABEL = 'Pre-flight 時点の同 base open PR';

/** PR 走査のページ上限。超えたら fail-closed (部分リストで緑にしない)。 */
const MAX_PAGES = 20;
const PER_PAGE = 100;
/** API 失敗時の明示的な retry。fail-open にはしない。 */
const RETRY_DELAYS_MS = [250, 500];

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** 全角コロン・NBSP・全角空白を ASCII へ畳んでから行を読む。 */
function normalizeLine(line) {
  return line
    .replace(/[   　]/g, ' ')
    .replace(/[：]/g, ':')
    .replace(/[‐-―−－]/g, '-');
}

/**
 * fenced code block / HTML コメントの中身を落とし、**GitHub 上で可視な文字列だけ**を返す。
 *
 * これが無いと `docs/l2-workflow.md` の記入例をそのまま PR 本文へ貼った本文が
 * 「`#938, #940` を宣言済み」と読まれて緑になる (false-green)。blockquote は可視なので
 * 落とさない — 引用された宣言は「書いてある」ものとして扱う。
 *
 * **行中の閉じたコメントの除去は `check-pr-checklist.js` の `stripInlineComments` を共有する。**
 * 同じ近似を 2 本持つと片方だけ renderer 実測に追従して乖離するため (#967 が潰した乖離 14 件と
 * 同じ構図)、「GitHub が隠す範囲」の判定は 1 箇所に置く。
 *
 * 期待値は `gh api markdown` (mode=gfm) の実測に合わせてある:
 *
 * - `- decl: <!-- #938 -->なし` → `<li>decl: なし</li>` = **`#938` は不可視**。数えない。
 *   数えると、レビュアが「なし」と読む欄で gate だけ `#938` 宣言済みと判定し、superset 扱いで
 *   緑になる (可視性の分裂)
 * - `note <!--` の**次行**の list item → `<p>note &lt;!--</p>` + `<li>...` = **可視**。読む。
 *   行中で開いたまま閉じないコメントは後続行を飲み込まない。ここで飲み込むと「可視なのに
 *   数えない」= #967 が潰した false-green の再導入になる
 * - **行頭** `<!--` は HTML block なので `-->` まで丸ごと不可視。読み飛ばす
 *
 * **これは Markdown parser ではなく近似である** (`check-pr-checklist.js` と同じ方針)。
 * 判断が付かない行は「宣言ではない」= fail-closed 側に倒す。既知の近似:
 *
 * - blockquote prefix を先に剥がすため、**引用の中で開いた fence が引用の外まで残る**。
 *   GitHub は引用境界で fence を閉じるので、その後ろの宣言行は本来可視。ここでは
 *   「宣言が見つからない」= red に倒れる (`check-pr-checklist.js` は quote 深さを追って
 *   この差を吸収しているが、本 gate は宣言 2 行を読むだけなので同じ精度を必要としない)
 * - indented code block (4 space) / HTML block type 1・type 6 は解釈しない。テンプレートの
 *   宣言行はいずれの文脈にも置かれないため、実害は「宣言でない行を宣言と読む」方向のみで、
 *   それは重複検出か値の parse 失敗で fail-closed に落ちる
 */
function visibleLines(body) {
  const out = [];
  let fence = null; // { char, len }
  let inComment = false;
  for (const rawLine of String(body || '').split(/\r?\n/)) {
    const line = rawLine.replace(/^(\s*>)+\s?/, ''); // blockquote prefix を剥がす
    if (inComment) {
      if (line.includes('-->')) inComment = false;
      continue;
    }
    const fenceMatch = line.match(/^ {0,3}(`{3,}|~{3,})(.*)$/);
    if (fenceMatch) {
      const char = fenceMatch[1][0];
      const len = fenceMatch[1].length;
      if (fence === null) {
        fence = { char, len };
        continue;
      }
      // 閉じ fence は同じ文字で開き以上の長さ、かつ info string を持たない。
      if (char === fence.char && len >= fence.len && fenceMatch[2].trim() === '') {
        fence = null;
        continue;
      }
    }
    if (fence !== null) continue;
    // 行頭 `<!--` は HTML block。`-->` まで不可視。
    if (/^\s*<!--/.test(line)) {
      if (!line.includes('-->')) inComment = true;
      continue;
    }
    out.push(stripInlineComments(line).content);
  }
  return out;
}

/**
 * 宣言行 (`- <label>: <value>`) を読む。
 *
 * @returns {{found: boolean, valid: boolean, numbers: number[], raw: string, reason: string}}
 *   `found` = 行が存在するか / `valid` = 値が宣言として読めるか。
 *   未編集の placeholder (`[#N,...] (または なし)`) と空値は **invalid** = fail-closed。
 */
function parseDeclaredPrSet(body, label) {
  const normalizedLabel = normalizeLine(label);
  // **行頭アンカー + 重複拒否** (Codex adversarial-review [high])。
  // 部分一致の先勝ちにすると、本文のどこかに decoy 宣言を 1 行仕込んで可視のテンプレート欄を
  // `なし` のまま残す、という緑化が通ってしまう。宣言は「行頭の list item」に限り、
  // 同じ label が 2 本以上見つかったら採用せず fail-closed にする。
  const matches = [];
  for (const rawLine of visibleLines(body)) {
    const line = normalizeLine(rawLine);
    const head = line.match(/^\s*(?:[-*+]\s*)?/)[0];
    if (!line.startsWith(head + normalizedLabel)) continue;
    const after = line.slice(head.length + normalizedLabel.length);
    const m = after.match(/^\s*:\s*(.*)$/);
    if (!m) continue;
    matches.push(m[1].trim());
  }

  if (matches.length === 0) {
    return { found: false, valid: false, numbers: [], raw: '', reason: '宣言行が見つかりません' };
  }
  if (matches.length > 1) {
    return {
      found: true,
      valid: false,
      numbers: [],
      raw: matches.join(' | '),
      reason: `宣言行が ${matches.length} 本あります (どれが正か決まらないため採用しません)`,
    };
  }

  const raw = matches[0];
  // placeholder 検出: `#N` (リテラルの N) / `または` を含む形はテンプレート未編集とみなす。
  if (/#N\b/i.test(raw) || raw.includes('または')) {
    return {
      found: true,
      valid: false,
      numbers: [],
      raw,
      reason: 'テンプレートの placeholder が未編集のまま残っています',
    };
  }
  // 数字量詞は上限付き。PR 本文は誰でも書けるため、入れ子量詞の backtracking で
  // job を張り付かせられないようにする。
  const numbers = [...raw.matchAll(/#(\d{1,7})/g)].map((x) => Number(x[1]));
  const unique = [...new Set(numbers)].sort((a, b) => a - b);
  if (unique.length > 0) return { found: true, valid: true, numbers: unique, raw, reason: '' };
  const stripped = raw.replace(/[[\]()（）`\s]/g, '');
  if (/^(なし|無し|none|n\/a)$/i.test(stripped)) {
    return { found: true, valid: true, numbers: [], raw, reason: '' };
  }
  return {
    found: true,
    valid: false,
    numbers: [],
    raw,
    reason: raw === '' ? '値が空です' : `値 "${raw}" を PR 番号の列挙として読めません`,
  };
}

/**
 * `Refs #862` / `Refs: #862, #934` 形から issue 番号を抽出する (重複は畳む)。
 *
 * 数字量詞に上限を置いているのは ReDoS 対策。`(?:#\d+[\s,、]*)+` の形は入れ子量詞なので、
 * 数万桁の数字列を含む本文で backtracking が二次オーダーに膨らみ job を張り付かせられる。
 * issue 番号は 7 桁で十分。
 */
function extractReferencedIssues(body) {
  const text = String(body || '');
  const out = [];
  for (const m of text.matchAll(/\brefs\b\s*:?\s*((?:#\d{1,7}[\s,、]*)+)/gi)) {
    for (const n of m[1].matchAll(/#(\d{1,7})/g)) out.push(Number(n[1]));
  }
  return [...new Set(out)];
}

/**
 * `pulls.list` の応答 1 件を検証する。**壊れた候補を黙って捨てない** (Codex [medium])。
 *
 * 候補側の malformed を filter で落とすと、競合 PR が実集合から消えて緑になる
 * (schema drift / 応答の切り詰め / proxy の書き換えで起きうる false-green)。
 * 呼び出し側は throw させて fail-closed に倒す。
 *
 * @returns {string|null} 問題があれば理由、無ければ null
 */
function validateCandidate(pr) {
  if (!pr || typeof pr !== 'object') return 'PR オブジェクトではありません';
  if (!Number.isInteger(pr.number)) return `number が整数ではありません (${pr && pr.number})`;
  if (!Number.isFinite(Date.parse(pr.created_at))) {
    return `#${pr.number}: created_at を解釈できません (${pr.created_at})`;
  }
  if (pr.closed_at != null && !Number.isFinite(Date.parse(pr.closed_at))) {
    return `#${pr.number}: closed_at を解釈できません (${pr.closed_at})`;
  }
  if (!Number.isFinite(Date.parse(pr.updated_at))) {
    return `#${pr.number}: updated_at を解釈できません (${pr.updated_at})`;
  }
  if (!pr.base || typeof pr.base.ref !== 'string' || pr.base.ref === '') {
    return `#${pr.number}: base.ref がありません`;
  }
  return null;
}

/** title / body に `#<n>` の独立した言及があるか (`#86` が `#862` に誤ヒットしない)。 */
function mentionsIssue(pr, issueNumbers) {
  const text = `${pr.title || ''}\n${pr.body || ''}`;
  return issueNumbers.some((n) => new RegExp(`(?<![#\\w])#${n}(?!\\d)`).test(text));
}

/**
 * `created_at` / `closed_at` から **T0 時点で open だった集合**を再構成する。
 * 自 PR は除外する。
 */
function reconstructOpenAt(prs, t0Iso, selfNumber) {
  const t0 = Date.parse(t0Iso);
  return (prs || []).filter((pr) => {
    if (!pr || pr.number === selfNumber) return false;
    const created = Date.parse(pr.created_at);
    if (!Number.isFinite(created) || created > t0) return false;
    if (!pr.closed_at) return true;
    const closed = Date.parse(pr.closed_at);
    return !Number.isFinite(closed) || closed > t0;
  });
}

/** API 呼び出しを明示的に retry する。尽きたら throw (呼び出し側で fail-closed)。 */
async function withRetry(fn, core) {
  let lastError;
  for (let attempt = 0; attempt <= RETRY_DELAYS_MS.length; attempt += 1) {
    try {
      return await fn();
    } catch (e) {
      lastError = e;
      if (attempt < RETRY_DELAYS_MS.length) {
        if (core && core.warning) {
          core.warning(`GitHub API 呼び出しに失敗しました (retry ${attempt + 1}): ${e.message}`);
        }
        await sleep(RETRY_DELAYS_MS[attempt]);
      }
    }
  }
  throw lastError;
}

/**
 * T0 時点で open だった可能性のある PR を集める。
 *
 * - open: 現在 open な全件 (T0 より後に作られたものは後段で落とす)
 * - closed: `updated_at` 降順に走査し、`updated_at < T0` に達したら打ち切る
 *   (`closed_at <= updated_at` なので、T0 より後に閉じた PR は必ずこの範囲に入る)
 */
async function collectCandidatePrs({ github, context, core, t0Iso }) {
  const t0 = Date.parse(t0Iso);
  const listPrs = (params) =>
    withRetry(
      () =>
        github.rest.pulls.list({
          owner: context.repo.owner,
          repo: context.repo.repo,
          per_page: PER_PAGE,
          ...params,
        }),
      core
    );

  const collected = [];
  const push = (data) => {
    for (const pr of data) {
      const problem = validateCandidate(pr);
      if (problem) throw new Error(`pulls.list の応答を検証できませんでした — ${problem}`);
      collected.push(pr);
    }
  };

  for (let page = 1; page <= MAX_PAGES; page += 1) {
    const res = await listPrs({ state: 'open', sort: 'created', direction: 'desc', page });
    const data = (res && res.data) || [];
    push(data);
    if (data.length < PER_PAGE) break;
    if (page === MAX_PAGES) {
      throw new Error(`open PR が ${MAX_PAGES} ページを超えました (走査打ち切り)`);
    }
  }

  // closed は `updated_at` 降順に走査し、`updated_at < T0` に達したら打ち切る。
  // `closed_at <= updated_at` なので、T0 より後に閉じた PR は必ずこの範囲に入る。
  for (let page = 1; page <= MAX_PAGES; page += 1) {
    const res = await listPrs({ state: 'closed', sort: 'updated', direction: 'desc', page });
    const data = (res && res.data) || [];
    push(data);
    if (data.length < PER_PAGE) break;
    const lastUpdated = Date.parse(data[data.length - 1].updated_at);
    if (lastUpdated < t0) break;
    if (page === MAX_PAGES) {
      throw new Error(
        `closed PR を ${MAX_PAGES} ページ走査しても T0 (${t0Iso}) に到達しませんでした`
      );
    }
  }

  return collected;
}

function formatSet(numbers) {
  return numbers.length === 0 ? 'なし' : numbers.map((n) => `#${n}`).join(', ');
}

async function checkPreflightFreshness({ github, context, core }) {
  const pr = context.payload.pull_request;
  if (!pr) {
    core.info('Not a pull_request event; skipping.');
    return;
  }

  const body = pr.body || '';
  const isBot = Boolean(pr.user && pr.user.type === 'Bot');

  const declared = {
    [SAME_ISSUE_LABEL]: parseDeclaredPrSet(body, SAME_ISSUE_LABEL),
    [SAME_BASE_LABEL]: parseDeclaredPrSet(body, SAME_BASE_LABEL),
  };

  if (isBot && !declared[SAME_ISSUE_LABEL].found && !declared[SAME_BASE_LABEL].found) {
    core.info(
      `Bot-authored PR (${(pr.user && pr.user.login) || 'bot'}): skipping Pre-flight freshness check.`
    );
    return;
  }

  const problems = [];
  for (const [label, result] of Object.entries(declared)) {
    if (!result.found) {
      problems.push(`\`- ${label}: ...\` の行が PR 本文にありません`);
    } else if (!result.valid) {
      problems.push(`\`${label}\` の宣言を読めません (${result.reason})`);
    }
  }
  if (problems.length > 0) {
    core.setFailed(
      `Pre-flight 宣言フィールドの検査に失敗しました:\n- ${problems.join('\n- ')}\n` +
        `PR テンプレート §「ベース同期確認」の 2 行に、Pre-flight 実行時点で観測した open PR 集合を ` +
        `\`#938, #940\` 形式 (無ければ \`なし\`) で記入してください。` +
        `詳細は docs/l2-workflow.md §「PR 作成 Pre-flight」を参照。`
    );
    return;
  }

  const t0Iso = pr.created_at;
  if (!t0Iso || !Number.isFinite(Date.parse(t0Iso))) {
    core.setFailed(
      `自 PR の created_at を取得できませんでした (${t0Iso})。再サンプリングの基準時刻が決まらないため fail-closed で落としています。`
    );
    return;
  }

  let candidates;
  try {
    candidates = await collectCandidatePrs({ github, context, core, t0Iso });
  } catch (e) {
    core.setFailed(
      `open PR 集合を取得できませんでした (${e.message})。` +
        `retry を尽くしても取得できないため fail-closed で落としています ` +
        `(fail-open にすると gate が常時 no-op になる)。` +
        `job を再実行するか、workflow の \`permissions: pull-requests: read\` を確認してください。`
    );
    return;
  }

  const openAtT0 = reconstructOpenAt(candidates, t0Iso, pr.number);
  const issueNumbers = extractReferencedIssues(body);
  const baseRef = (pr.base && pr.base.ref) || '';

  const actual = {
    [SAME_ISSUE_LABEL]:
      issueNumbers.length === 0 ? [] : openAtT0.filter((p) => mentionsIssue(p, issueNumbers)),
    [SAME_BASE_LABEL]: openAtT0.filter((p) => p.base && p.base.ref === baseRef),
  };

  if (issueNumbers.length === 0) {
    core.info(
      '本文に `Refs #N` が無いため same-issue 側の実集合は空です (この PR では当該検査は no-op)。'
    );
  }

  const missing = [];
  for (const [label, prs] of Object.entries(actual)) {
    const declaredSet = new Set(declared[label].numbers);
    const undeclared = prs.map((p) => p.number).filter((n) => !declaredSet.has(n));
    if (undeclared.length > 0) {
      missing.push(
        `**${label}**: 宣言 = ${formatSet(declared[label].numbers)} / ` +
          `再サンプリング = ${formatSet([...new Set(prs.map((p) => p.number))].sort((a, b) => a - b))} / ` +
          `宣言漏れ = ${formatSet([...new Set(undeclared)].sort((a, b) => a - b))}`
      );
    }
  }

  if (missing.length > 0) {
    core.setFailed(
      `Pre-flight 実行時点の宣言に無い open PR が見つかりました (基準時刻 T0 = ${t0Iso}):\n` +
        `${missing.map((m) => `- ${m}`).join('\n')}\n` +
        `Pre-flight (Step 0 / Step 4) の結果が PR 作成時点より古い可能性があります。` +
        `docs/l2-workflow.md §「PR 作成 Pre-flight」に従って Step 0-4 を回し直し、` +
        `touched files の交差を再判定したうえで宣言フィールドを更新してください。`
    );
    return;
  }

  core.info(
    `Pre-flight freshness OK (T0 = ${t0Iso}, base = ${baseRef}, refs = ${formatSet(issueNumbers)}).`
  );
}

module.exports = checkPreflightFreshness;
module.exports.parseDeclaredPrSet = parseDeclaredPrSet;
module.exports.extractReferencedIssues = extractReferencedIssues;
module.exports.reconstructOpenAt = reconstructOpenAt;
module.exports.SAME_ISSUE_LABEL = SAME_ISSUE_LABEL;
module.exports.SAME_BASE_LABEL = SAME_BASE_LABEL;
