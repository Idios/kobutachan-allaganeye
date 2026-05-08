// .github/scripts/check-pr-checklist.js
function countAcceptanceCriteriaCheckboxes(body) {
  // `## ` heading で section 分割。最初の heading 前は捨てる
  const sections = body.split(/^##\s+/m).slice(1);
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

async function checkPrChecklist({ github, context, core }) {
  const body = context.payload.pull_request.body || '';
  const { unchecked, checked, hasAnySection } = countAcceptanceCriteriaCheckboxes(body);
  if (!hasAnySection) {
    core.info('No `## 受け入れ条件` / `## Acceptance criteria` section found, skipping.');
    return;
  }
  if (unchecked > 0) {
    core.setFailed(
      `PR has ${unchecked} unchecked acceptance criteria item(s) in \`## 受け入れ条件\` section. Please complete all items before merging.`
    );
    return;
  }
  core.info(`All ${checked} acceptance criteria item(s) are checked.`);
}

module.exports = checkPrChecklist;
module.exports.countAcceptanceCriteriaCheckboxes = countAcceptanceCriteriaCheckboxes;
