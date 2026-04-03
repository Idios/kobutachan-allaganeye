---
name: create-task
description: GitHub Issueとしてタスクを作成する
---

# タスク作成スキル

GitHub Issue としてタスクを作成します。

## 引数

`$ARGUMENTS` にタスクの概要を自然言語で指定。

## 手順

1. `docs/issue-policy.md` を読み、Issue 作成ルールを確認
2. 引数からタスク内容を解析し、以下を決定:
   - プレフィックス: `[bug]`, `[doc]`, `[refactor]`, `[task]`, `[question]`, `[risk]`
   - ラベル: `bug`, `documentation`, `enhancement`, `question` + ロールラベル
   - 担当ロール: タスク内容から適切なロールを推定
3. 重複チェック:
   ```bash
   gh issue list --repo Idios/kobutachan-allaganeye --state open --search "<キーワード>" --json number,title
   ```
4. 重複がなければ Issue を作成:
   ```bash
   gh issue create --repo Idios/kobutachan-allaganeye \
     --title "<プレフィックス> <タイトル>" \
     --body "<本文>" \
     --assignee Idios \
     --label "<ラベル1>,<ラベル2>"
   ```
5. ユーザーに Issue URL を報告
