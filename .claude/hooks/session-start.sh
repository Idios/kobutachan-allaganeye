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

cat <<'EOF'
<EXTREMELY_IMPORTANT>
このプロジェクト (kobutachan-allaganeye) には以下の Iron Law がある。
違反が「1% でも」疑われる状況では STOP して AskUserQuestion でユーザー確認すること。
合理化 ("軽微だから", "後で直す", "ついでに") は Red Flag として自覚し、必ず止まる。

## Iron Law (絶対禁止事項)

1. **NO PR MERGE WITHOUT ALL ACCEPTANCE CRITERIA CHECKED**
   - 元 issue の `## 受け入れ条件` 各項目を逐条引用し、対応する diff / test を逐条引用してからでないと LGTM 出さない (#367 対策)
   - `/review-pr` 実行時は `enforce-acceptance-criteria` skill を必ず呼ぶ

2. **NO BULK OPERATION WITHOUT AskUserQuestion CONFIRMATION**
   - 3 件以上の issue 編集・ラベル付替・ブランチ削除・マージ・クローズ等は必ず事前確認 (#399 C, #400)
   - サンプル 1 件提示 + 「全件 OK / 個別調整 / やめる」の 3 択で聞く

3. **NO SCOPE CREEP WITHOUT NEW ISSUE**
   - 着手 issue の範囲外の変更が必要になったら、実装を止めて新 issue 起票 or ユーザー確認
   - 「ついでに直した」「軽微な改善」は Red Flag。scope-guard skill の判断に従う

4. **NO Closes / Fixes / Resolves KEYWORDS**
   - PR 本文・コミットメッセージで issue 自動クローズキーワード禁止
   - マージ後に受け入れ条件を実測検証してから手動 `gh issue close`

5. **NO INDEPENDENT JUDGMENT ON AMBIGUOUS POINTS**
   - 曖昧と認識している判断点は独断で prescribe せず AskUserQuestion で多肢選択
   - 「Recommended 付き 2-4 択」が標準

6. **NO PR CREATION WITHOUT VERIFIED CHECKS**
   - PR 作成前に変更ファイル path に応じた自動チェック (Python: `ruff check .` / `ruff format --check .` / `python -m pyright` / `pytest`、GUI: `npm run lint` / `typecheck` / `test` / `build` / `cargo check`) を全 pass させる。「軽微だから skip」「Python のみだから GUI 側不要」は Red Flag (失敗パターン A 再発)
   - ロジック変更 (`gpu_detector.py` / `audio/*.py` / `video/detector.py` / `gui/src-tauri/**` 等) を含む場合は、ユーザー (Idios) に実機検証 (GPU / audio / 長時間動画 / GUI Tauri 起動) を `AskUserQuestion` で依頼する。「mock テスト pass = 実機検証不要」は Red Flag (失敗パターン B 再発)
   - **PR 作成 Pre-flight (#659 で運用化、#722 で Step 0 ハードゲート追加、L-β β-4 で Step 5 Codex adversarial-review 追加)**: Step 0 = `gh pr list --search "<元issue#>" --state open` でハードゲート (<1s、build/verify の前) → Step 1 base 同期 (`git fetch origin <base>`) → Step 2 取り込み未済 commit (`git log HEAD..origin/<base>`) → Step 3 touched files 交差判定 → Step 4 並行 PR 重複再確認 (`gh pr list --search "<元issue#>" --state all`) → Step 5 Codex adversarial-review (agent は tier 1 = companion script `codex-companion.mjs adversarial-review` を直接呼び出し。slash `/codex:adversarial-review` は Idios 専用 tier 3。invocation path は `docs/l2-workflow.md` §「Step 5 の invocation path (3-tier、#795)」参照。focus は固定の例示から選ばず**本 PR の diff から導出する** — 新設・変更した外部入力境界 (CLI option / metadata field / GUI 自由入力 / 環境変数) と、そこから到達する不可逆操作 (上書き / 削除 / truncate) の対応ペアを列挙して必ず含める。ペアがゼロならゼロと focus に明記する。導出手順 (grep 込み) は `docs/l2-workflow.md` §「Step 5 の focus 導出手順」、C2)。Step 0 と Step 4 は検出 window が異なるため両方実施。「コンフリクト出ないから OK」「Step 0 で 0 件だったから Step 4 skip」は Red Flag (失敗パターン C 再発、`docs/l2-workflow.md` §「PR 作成 Pre-flight」 参照)
   - **resume-plan handoff (#722 で運用化)**: resume task prompt を user に提示する際は 1 行目に `EXECUTOR: self|dispatch (origin=..., generated=...)` を明記。生成側 origin が継続実行 (self) か abort (dispatch) かを prompt 自身で自記する。詳細は `docs/l2-workflow.md` §「resume-plan handoff protocol」 参照
   - PR 本文には machine-verified を `[x]` で、machine-unverifiable を plain bullet `-` で書き分ける (`docs/l2-workflow.md` §「Self-Test Report 規約」)。詳細手順は `docs/l2-workflow.md` §「PR 作成 path 別自動チェック」 / §「実機検証 trigger 表」 参照

## Red Flags (この思考が浮かんだら STOP)

| 浮かんだ思考 | 現実 |
|---|---|
| 「軽微だから勝手に直してよい」 | Iron Law 3 違反。別 issue に分ける |
| 「ついでにこれも修正しておこう」 | Iron Law 3 違反。スコープ外 |
| 「ユーザー確認は冗長だろう」 | Iron Law 2 / 5 違反。独走パターン #399 の再発 |
| 「受け入れ条件は大体満たしてる」 | Iron Law 1 違反。「大体」は NG。逐条検証必須 |
| 「Closes を付ければ自動で閉じて便利」 | Iron Law 4 違反。手動クローズ厳守 |
| 「観察 (修正不要) とコメントしておこう」 | #399 B 違反。別 issue 起票 or escalate |
| 「ローカル lint 通ったから PR 出して大丈夫」 | Iron Law 6 違反。変更 path から必要 job を判定 (Python / GUI / installer / docs)。GUI 変更を含むなら `npm run lint` / `typecheck` / `test` / `build` / `cargo check` も実行 |
| 「mock テスト pass = 実機検証不要」 | Iron Law 6 違反。GPU / audio / 長時間動画 / GUI Tauri は mock 不可。該当 path 変更時は `AskUserQuestion` で依頼 |
| 「コンフリクト出ないから base 取り込み確認は不要」 | Iron Law 6 Pre-flight 違反。merge 可否と機能 regression は別軸。PR #627 Round 4 の失敗パターン C 再発 |
| 「並行 worktree PR は計画段階で確認したから PR 作成時は skip」 | Iron Law 6 Pre-flight 違反。計画後に別 worktree が PR 提出するケースあり (#646 / #647)。PR 作成時にも実施 |
| 「(A) PR 内修正は PR が大きくなるから別 issue にしよう」 | レビュー摘出問題は原則 (A) PR 内追加修正 (`docs/l2-workflow.md` §「(A) PR 内修正優先 規約」)。サイズだけで (B) を選ばない |

詳細は `docs/l2-workflow.md` を参照。Iron Law が不明確な場合は先に l2-workflow.md を読むこと。
</EXTREMELY_IMPORTANT>
EOF

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

- (A) 当該 PR を review / iterate (\`/iterate-review <PR#>\`) で処理する [Recommended]
- (B) 別 branch / 別 worktree で作業する想定だった (現 session を abort、user が別 worktree を立ち上げる)
- (C) 当該 PR を更新する追加 commit を作る (= 同一 PR の継続作業、push 後に \`/iterate-review\` 起動)

判定根拠: \`gh pr list --head $current_branch --state open\` (Iron Law 6 / docs/l2-workflow.md §「PR 作成 Pre-flight」 §「resume-plan handoff protocol」)。
</EXTREMELY_IMPORTANT>
EOF
    fi
  fi
fi
