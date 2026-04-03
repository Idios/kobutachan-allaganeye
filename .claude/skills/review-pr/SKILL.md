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
4. レビュー結果をコメント:
   ```bash
   gh pr review $ARGUMENTS --repo Idios/kobutachan-allaganeye --comment --body "<レビュー内容>"
   ```
5. 問題がなければ LGTM:
   ```bash
   gh pr review $ARGUMENTS --repo Idios/kobutachan-allaganeye --approve
   ```

## マージ条件（Lead Engineer / Director のみ）

以下のすべてを満たす場合にマージ可能:
- チェックリストが全て完了
- テスト通過の確認コメントがある
- レビューが approve 済み
- マージコンフリクトがない

```bash
gh pr merge $ARGUMENTS --repo Idios/kobutachan-allaganeye --squash --delete-branch
```

## 関連 Issue のクローズ

PR に `Closes #N` が含まれている場合、マージ後に Issue が自動クローズされることを確認。
