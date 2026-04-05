---
name: review-pr
description: PRのレビューとマージを自動化する
---

# PR レビュースキル

指定された PR をレビューし、条件を満たせばマージします。

## 引数

`$ARGUMENTS` に PR 番号を指定（例: `42`）

## 手順

1. PR の情報を取得:
   ```bash
   gh pr view $ARGUMENTS --repo Idios/kobutachan-allaganeye --json number,title,body,labels,reviews,statusCheckRollup,mergeable,additions,deletions,files
   ```
2. PR の diff を取得:
   ```bash
   gh pr diff $ARGUMENTS --repo Idios/kobutachan-allaganeye
   ```
3. 以下の観点でレビュー:
   - コードの正確性・安全性
   - テストの有無と網羅性
   - CLAUDE.md / docs の更新必要性
   - コーディング規約への準拠
   - チェックリストの完了状態
4. レビュー結果を PR コメントで投稿:
   ```bash
   gh pr comment $ARGUMENTS --repo Idios/kobutachan-allaganeye --body "<レビュー内容>"
   ```

> **注意**: `gh pr review --approve` は使用しない（全ロールが同一アカウントのため self-approve 不可。`docs/roles/protocol.md` 参照）。レビュー結果はコメントで投稿する。

## マージ条件（Lead Engineer / Director のみ）

以下のすべてを満たす場合にマージ可能:
- チェックリストが全て完了
- コード変更を含む PR: テスターのテスト結果コメントがある
- ドキュメントのみの PR: レビューコメントで LGTM
- マージコンフリクトがない

```bash
gh pr merge $ARGUMENTS --repo Idios/kobutachan-allaganeye --squash
```

## 関連 Issue のクローズ

PR マージ後、関連 Issue は **手動でクローズ** する（`Closes` / `Fixes` / `Resolves` キーワードは使用禁止。`docs/issue-policy.md` 参照）。

```bash
gh issue close <番号> --repo Idios/kobutachan-allaganeye --comment "マージ確認: <session-id> ← PR #$ARGUMENTS"
```
