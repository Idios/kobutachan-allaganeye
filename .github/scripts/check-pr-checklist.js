// .github/scripts/check-pr-checklist.js

/**
 * Fenced code block (` ``` ... ``` `) を空文字で除去する。
 * PR 本文に skill spec / template 抜粋を貼ると本文中の `## 受け入れ条件` 等が
 * code block 内 heading として扱われる場合があるため、heading 検出前に除去する。
 * non-greedy + multiline で行頭フェンス対のみ対象とする (closed fence のみ除去、
 * 不対称な open fence は残す)。
 */
function stripFencedBlocks(body) {
  return body.replace(/^```[\s\S]*?^```/gm, '');
}

function countAcceptanceCriteriaCheckboxes(body) {
  // fenced code blocks を除去してから heading 分割
  const stripped = stripFencedBlocks(body);
  // `## ` heading で section 分割。最初の heading 前は捨てる
  const sections = stripped.split(/^##\s+/m).slice(1);
  // 受け入れ条件 / Acceptance criteria heading に該当する section のみ抽出
  const acceptanceText = sections
    .filter((s) => {
      const heading = (s.split(/\r?\n/)[0] || '').trim();
      return /^(受け入れ条件|acceptance\s+criteria)\s*$/i.test(heading);
    })
    .join('\n');
  const unchecked = (acceptanceText.match(/- \[ \]/g) || []).length;
  const checked = (acceptanceText.match(/- \[x\]/gi) || []).length;
  return { unchecked, checked, hasAnySection: acceptanceText.length > 0 };
}

// async は actions/github-script@v7 caller (`await checker({github, context, core})`) との
// 互換のため維持。内部に await はないが、yml 側 `await` を可能にするため Promise 返却が必要。
async function checkPrChecklist({ github, context, core }) {
  const body = context.payload.pull_request.body || '';
  const { unchecked, checked, hasAnySection } = countAcceptanceCriteriaCheckboxes(body);
  if (!hasAnySection) {
    core.info('No `## 受け入れ条件` / `## Acceptance criteria` section found, skipping.');
    return;
  }
  if (unchecked > 0) {
    core.setFailed(
      `PR has ${unchecked} unchecked acceptance criteria item(s) in \`## 受け入れ条件\` / \`## Acceptance criteria\` section. Please complete all items before merging.`
    );
    return;
  }
  core.info(`All ${checked} acceptance criteria item(s) are checked.`);
}

module.exports = checkPrChecklist;
module.exports.countAcceptanceCriteriaCheckboxes = countAcceptanceCriteriaCheckboxes;
