#!/usr/bin/env bash
# Inject project Iron Laws at session start / clear / compact.
# Inspired by obra/superpowers pattern: prompt-weighted self-restraint.

# 前セッションで stop.sh が記録した orphan commit があれば Iron Law inject の前に警告表示 (M6 / F7)。
# heuristic で false positive を許容するため、user が log を rm することで dismiss できる運用。
ORPHAN_LOG="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}/.claude/state/orphan-commits.log"
if [[ -f "$ORPHAN_LOG" ]] && [[ -s "$ORPHAN_LOG" ]]; then
  cat <<EOF
⚠️ 前セッションで orphan commit が検出されました (M6 / F7、PR #741 教訓):

\`\`\`
$(head -10 "$ORPHAN_LOG")
\`\`\`

復旧手順:
- 該当 commit が必要なら: \`git cherry-pick <SHA>\` で現 HEAD 上に再生成
- ノイズ (Claude Opus co-author trailer 持ち正常 commit 等) なら: \`rm "$ORPHAN_LOG"\` で警告クリア

本警告は false positive を許容する heuristic です (詳細は \`docs/l2-workflow.md\` §subagent 起動規約 参照)。

EOF
fi

# Iron Law 本文の正は AGENTS.md (#1079 Phase 3)。hook は実行時に抽出する。
# 同一本文を 2 spot に置くと、AGENTS.md だけを更新したときに注入内容が古いままになる
# (`scripts/check_declarations.py` の `iron-law` gate が複製を禁止する)。
AGENTS_MD="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}/AGENTS.md"
if [[ -f "$AGENTS_MD" ]]; then
  echo '<EXTREMELY_IMPORTANT>'
  awk '/^## Iron Law/{flag=1} flag{print} /^詳細は /{if(flag){exit}}' "$AGENTS_MD"
  echo '</EXTREMELY_IMPORTANT>'
else
  echo "⚠️ AGENTS.md が見つからないため Iron Law を注入できませんでした: ${AGENTS_MD}" >&2
fi

# NEW (#722): worktree-as-PR-head 自動検出
# 現在の worktree branch が既に open PR の head である場合に
# system reminder block を inject し、Claude に AskUserQuestion 提示を促す。
# Iron Law 6 / docs/l2-workflow.md §「PR 作成 Pre-flight」 §「resume-plan handoff protocol」

if command -v gh >/dev/null 2>&1 && command -v git >/dev/null 2>&1; then
  current_branch=$(git -C "${CLAUDE_PROJECT_DIR:-.}" branch --show-current 2>/dev/null || echo "")
  if [[ -n "$current_branch" ]] && [[ "$current_branch" =~ ^claude/ ]]; then
    if command -v timeout >/dev/null 2>&1; then
      matched=$(timeout 5 gh pr list --head "$current_branch" --state open \
                  --json number,title,headRefName 2>/dev/null || echo "")
    else
      matched=$(gh pr list --head "$current_branch" --state open \
                  --json number,title,headRefName 2>/dev/null || echo "")
    fi
    if [[ -n "$matched" ]] && [[ "$matched" != "[]" ]]; then
      cat <<EOF
<EXTREMELY_IMPORTANT>
## worktree-as-PR-head 検出 (#722)

現在のセッション worktree は既に open PR の head branch (\`$current_branch\`) です。

\`\`\`
$matched
\`\`\`

このセッションを開始した目的を確認してください。AskUserQuestion で以下 3 択を提示すること:

- (A) 当該 PR を review / iterate (\`iterate-review <PR#>\`) で処理する [Recommended]
- (B) 別 branch / 別 worktree で作業する想定だった (現 session を abort、user が別 worktree を立ち上げる)
- (C) 当該 PR を更新する追加 commit を作る (= 同一 PR の継続作業、push 後に \`iterate-review\` 起動)

判定根拠: \`gh pr list --head $current_branch --state open\` (Iron Law 6 / docs/l2-workflow.md §「PR 作成 Pre-flight」 §「resume-plan handoff protocol」)。
</EXTREMELY_IMPORTANT>
EOF
    fi
  fi
fi
