---
name: create-task
description: issue-policy.md に沿ったタスク issue を対話的に作成する
user-invocable: true
argument-hint: <タスクの概要（自然言語）>
---

ユーザーの指示に基づいて GitHub Issue を作成する。`docs/issue-policy.md` のルールに従うこと。

## 手順

1. ユーザーの指示（`$ARGUMENTS`）からタスクの内容を把握する
2. 適切な prefix を選択する（`[bug]`, `[doc]`, `[refactor]`, `[question]`, `[risk]`, `[task]`）
3. `docs/issue-policy.md` §3 の対応テンプレートに沿って本文を作成する
4. 作成前にユーザーにタイトルと本文を提示し、確認を得る
5. ユーザーが承認したら `gh issue create` で作成する:
   ```bash
   gh issue create \
     --title "<prefix> <概要>" \
     --body "<テンプレートに沿った本文>" \
     --assignee "Idios" \
     --label "<prefix に対応するラベル（該当する場合）>" \
     --label "<対応ロールの role:* ラベル（該当する場合）>"
   ```

## 注意事項

- 1 issue = 1 つの問題・タスク。複数の問題をまとめない
- 作成前に `gh issue list` で重複がないか確認する
- ラベルは prefix に応じて設定する（`[risk]` は prefix ラベルなし）
- `[task]` issue には対応ロールの `role:*` ラベルを必ず付ける（`docs/issue-policy.md` §2 参照）
- `[question]` issue には回答を求めるロールの `role:*` ラベルを付ける
- 優先度が明確な場合は `P1-high` / `P2-medium` / `P3-low` ラベルを付ける（`docs/issue-policy.md` §2 参照）
- タイトルは日本語で 40 文字以内
- 本文の末尾に `作成: <session-id>` を記載する
