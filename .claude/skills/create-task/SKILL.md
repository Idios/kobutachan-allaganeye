---
name: create-task
description: issue-policy.md に沿って GitHub issue を対話的に作成する（全 prefix: bug/doc/refactor/task/question/risk 対応）
user-invocable: true
argument-hint: <タスクの概要（自然言語）>
---

ユーザーの指示に基づいて GitHub Issue を作成する。`docs/issue-policy.md` のルールに従うこと。

## 手順

1. ユーザーの指示（`$ARGUMENTS`）からタスクの内容を把握する
2. 適切な prefix を選択する（`[bug]`, `[doc]`, `[refactor]`, `[question]`, `[risk]`, `[task]`）
3. `docs/issue-policy.md` §3 の対応テンプレートに沿ってタイトルと本文を作成する
4. 重複チェック: `gh issue list --search "<主題を表す名詞 2-3 個>" --state all --repo Idios/kobutachan-allaganeye` を実行し、類似 issue がないか確認する（キーワードはタイトルから名詞を優先抽出、必要なら本文から補足）
5. 作成前にユーザーに以下の要素を提示して確認を得る:
   - タイトル（文字数表示付き、例: "33/40 文字"）
   - assignee / ラベル一覧（スコープラベル・優先度ラベル含む）
   - 重複チェック結果（ヒット件数と代表 issue）
   - 本文全文
   - 選択肢: 「はい / 修正箇所を指摘 / やめる」
6. ユーザーが承認したら以下のコマンドで作成する（Windows + Git Bash での日本語本文破損回避のため `printf | --body-file -` 方式）:

   ```bash
   printf '%s\n' "<本文>" | gh issue create \
     --repo Idios/kobutachan-allaganeye \
     --title "<prefix> <概要>" \
     --body-file - \
     --assignee "Idios" \
     --label "<prefix に対応するラベル（該当する場合）>" \
     --label "<スコープラベル（l2a-gui / l2b-installer / l2c-guard / l2-workflow / l2-decision / l1-residual 等、該当する場合）>"
   ```

## 注意事項

- 1 issue = 1 つの問題・タスク。複数の問題をまとめない
- ラベルは prefix に応じて設定する（`[risk]` は prefix ラベルなし）
- 対応スコープが明確な場合はスコープラベル（`l2a-gui` / `l2b-installer` / `l2c-guard` / `l2-workflow` / `l2-decision` / `l1-residual` 等）を付ける（`docs/issue-policy.md` §2 参照）
- 優先度が明確な場合は `P1-high` / `P2-medium` / `P3-low` ラベルを付ける（`docs/issue-policy.md` §2 参照）
- タイトルは日本語で 40 文字以内
- 本文の末尾に `作成: <session-id>` を記載する
- `Closes` / `Fixes` / `Resolves` キーワードは本文中で使わない（クローズは手動）
