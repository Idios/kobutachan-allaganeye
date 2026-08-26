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
//   (これが `PreToolUse` hook 案より弱くない根拠。hook 案は bypass 4 経路がある — #946 参照)
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
// - closed PR の走査には**ページ上限**がある。上限に達したら「取り切れなかった」として
//   fail-closed にする (部分リストで「差分なし」と判定しない)

'use strict';

const SAME_ISSUE_LABEL = 'Pre-flight 時点の同 issue open PR';
const SAME_BASE_LABEL = 'Pre-flight 時点の同 base open PR';

/** closed PR 走査のページ上限。超えたら fail-closed (部分リストで緑にしない)。 */
const MAX_CLOSED_PAGES = 20;
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
 * 宣言行 (`- <label>: <value>`) を読む。
 *
 * @returns {{found: boolean, valid: boolean, numbers: number[], raw: string, reason: string}}
 *   `found` = 行が存在するか / `valid` = 値が宣言として読めるか。
 *   未編集の placeholder (`[#N,...] (または なし)`) と空値は **invalid** = fail-closed。
 */
function parseDeclaredPrSet(body, label) {
  const lines = String(body || '').split(/\r?\n/);
  const normalizedLabel = normalizeLine(label);
  for (const rawLine of lines) {
    const line = normalizeLine(rawLine);
    const idx = line.indexOf(normalizedLabel);
    if (idx < 0) continue;
    const after = line.slice(idx + normalizedLabel.length);
    const m = after.match(/^\s*:\s*(.*)$/);
    if (!m) continue;
    const raw = m[1].trim();
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
    const numbers = [...raw.matchAll(/#(\d+)/g)].map((x) => Number(x[1]));
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
  return { found: false, valid: false, numbers: [], raw: '', reason: '宣言行が見つかりません' };
}

/** `Refs #862` / `Refs: #862, #934` 形から issue 番号を抽出する (重複は畳む)。 */
function extractReferencedIssues(body) {
  const text = String(body || '');
  const out = [];
  for (const m of text.matchAll(/\brefs\b\s*:?\s*((?:#\d+[\s,、]*)+)/gi)) {
    for (const n of m[1].matchAll(/#(\d+)/g)) out.push(Number(n[1]));
  }
  return [...new Set(out)];
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

  for (let page = 1; page <= MAX_CLOSED_PAGES; page += 1) {
    const res = await listPrs({ state: 'open', sort: 'created', direction: 'desc', page });
    const data = (res && res.data) || [];
    collected.push(...data);
    if (data.length < PER_PAGE) break;
    if (page === MAX_CLOSED_PAGES) {
      throw new Error(`open PR が ${MAX_CLOSED_PAGES} ページを超えました (走査打ち切り)`);
    }
  }

  for (let page = 1; page <= MAX_CLOSED_PAGES; page += 1) {
    const res = await listPrs({ state: 'closed', sort: 'updated', direction: 'desc', page });
    const data = (res && res.data) || [];
    collected.push(...data);
    if (data.length < PER_PAGE) break;
    const last = data[data.length - 1];
    const lastUpdated = Date.parse(last && last.updated_at);
    if (Number.isFinite(lastUpdated) && lastUpdated < t0) break;
    if (page === MAX_CLOSED_PAGES) {
      throw new Error(
        `closed PR を ${MAX_CLOSED_PAGES} ページ走査しても T0 (${t0Iso}) に到達しませんでした`
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
