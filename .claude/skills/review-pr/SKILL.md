---
name: review-pr
description: PR をレビューし、懸念点があればコメント、なければ LGTM してマージする
user-invocable: true
argument-hint: <PR番号>
---

指定された PR をレビューする。以下の手順で進めること:

1. `gh pr view $ARGUMENTS --json title,body,headRefName,baseRefName,files,commits,labels` で PR の概要を確認する
2. PR の `role:*` ラベルが正しいか確認する（`docs/roles/protocol.md` §「PR レビューとマージ」参照）。元 issue がある場合は issue 作成者ロールがレビュー担当。誤りがあれば `gh pr edit` で修正してからレビューに進む
3. `gh pr diff $ARGUMENTS` で差分を確認する
4. 以下の観点でレビューする:
   - 変更の意図が PR の説明と一致しているか
   - `docs/roles/protocol.md` のルールに違反していないか
   - 自ロールのレビュー権限範囲内か（protocol.md の「PR レビューとマージ」参照）
   - ドキュメント変更の場合: 既存のドキュメントとの整合性、矛盾がないか
   - コード変更の場合: アーキテクチャに沿っているか、セキュリティモデルが守られているか
5. コード変更が含まれる場合、テスト確認を行う:
   - PR コメントにテスターの `テスト完了: <session-id>` コメントがあるか確認する
   - **ない場合**: マージ不可。「テスター確認待ち」とユーザーに報告し、マージは行わない
   - **ある場合**: コメントに実行結果の要約（テスト件数・成否等）が含まれていることを確認し、問題なければマージ可と判断する
   - ドキュメントのみの PR はこのステップをスキップする
6. レビュー結果をユーザーに報告し、判断を仰ぐ:
   - 懸念があれば具体的に指摘し、PR コメントするかユーザーに確認する
   - 問題なければ LGTM コメントとマージの実施をユーザーに提案する
   - **修正を依頼する場合**: PR に修正依頼コメントを投稿し、`role:*` ラベルを PR 作成者のロールに付替える（protocol.md §「レビューでの修正依頼時」参照）
7. ユーザーが承認したら:
   - `gh pr comment $ARGUMENTS --body "LGTM. <簡潔な理由> [<session-id>]"` でコメント
   - **マージ権限の確認**: マージはリードエンジニアまたはディレクターのみ実行可能
     - 自セッションが lead/director の場合: `gh pr merge $ARGUMENTS --squash` でマージ
     - 自セッションが engineer/tester の場合: LGTM のみ行い、`role:*` ラベルを lead/director に付替え、マージは lead/director に委ねる旨をユーザーに伝える
8. マージ後、PR に紐づく issue がある場合:
   - `gh issue view <番号> --json body,comments` で issue 本文とコメントを取得する
   - 本文に未チェックのチェックボックス（`- [ ]`）がないか確認する
   - **未完了項目なし**: `gh issue close <番号> --comment "マージ確認: <session-id> ← PR #番号"` でクローズする
   - **未完了項目あり**: PR の変更内容とコメントを照合し、実際に作業が完了しているか判断する
     - **作業完了だがチェック漏れ**: `gh issue edit <番号> --body "..."` でチェックボックスを更新してからクローズする
     - **実際に未完了の残作業あり**: クローズせず、issue 作成者のロールにラベルを付替える（`作成: <session-id>` から判定: `director-*` → `role:director`、`lead-*` → `role:lead-engineer`、`engineer-*` → `role:engineer`、`tester-*` → `role:tester`）

> **注意**: `gh pr review --approve` は使用しない（全ロールが同一アカウントのため self-approve 不可。`docs/roles/protocol.md` 参照）。
