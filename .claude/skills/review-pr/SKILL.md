---
name: review-pr
description: PR をレビューし、受け入れ条件チェックリストで検証。懸念点があればコメント、なければ LGTM してユーザーにマージを提案
user-invocable: true
argument-hint: <PR番号>
---

指定された PR をレビューする。`docs/l2-workflow.md` §「レビュー受け入れ基準」に従う。

## 手順

### 1. PR 概要取得

```bash
gh pr view $ARGUMENTS --json title,body,headRefName,baseRefName,files,commits,labels
gh pr diff $ARGUMENTS
```

### 2. ベースブランチ確認

- `baseRefName` が `develop-x.x.x` 形式であることを確認 (`main` 直接は通常禁止)
- 例外はホットフィックス PR のみ

### 3. 受け入れ条件チェックリスト (#367 対策)

PR body と diff を突き合わせ、以下を検証する:

- [ ] **受け入れ条件の全項目が満たされているか**: 元 issue の `## 受け入れ条件` のチェックボックスが PR 本文で反映され、対応する diff / test がある
- [ ] **実装内容が PR 説明と一致**: 差分と PR body の乖離を検出 (例: PR body に書かれていない無関係な変更がないか)
- [ ] **テスト存在**: 変更行に対応する test ケースがあるか
  - 新規関数・メソッド: 単体テスト必須
  - バグ修正: baseline FAIL → FIX 検証テストが望ましい
  - UI/出力変更: スナップショットテストまたは contract テスト
- [ ] **UI/出力変更の実証**: CLI 出力・GUI スクリーンショット等の実サンプルが PR 本文に添付されているか
- [ ] **複数 issue 束ね時の合理性**: 1 PR で複数 issue を閉じる場合、束ねる理由が PR 本文に明記されているか
- [ ] **Phase 分割時の子 issue 起票**: 「Phase 2 は別途」等で残タスクを先送りする場合、子 issue 番号が親 issue に記載されているか
- [ ] **`Closes` / `Fixes` / `Resolves` キーワードが使われていない**: issue クローズは手動で行う

### 4. CI / Lint / Test ステータス確認

```bash
gh pr checks $ARGUMENTS
```

- 全 green: 次へ
- 失敗あり: 失敗ジョブ名と概要をユーザーに報告し、修正依頼コメントを投稿
- 未完了: 完了を待つ or ユーザーに判断を仰ぐ

### 5. ロジックレビュー

以下の観点でコード品質を確認する:

- 変更の意図が PR の説明と一致しているか
- アーキテクチャに沿っているか (`CLAUDE.md` §モジュール構成、`docs/design-overview.md`)
- セキュリティモデルが守られているか (特に外部入力処理、subprocess 呼び出し)
- ドキュメント変更の場合: 既存のドキュメントとの整合性、矛盾がないか

### 6. レビュー結果をユーザーに報告

`AskUserQuestion` で以下を提示する:

- **LGTM (問題なし)**: ユーザーに `--squash` マージを提案
- **修正依頼**: 具体的な指摘内容を表示し、PR コメントに投稿するかユーザー確認
- **テスト不足**: `/test-pr` skill 呼び出しを提案
- **スコープ逸脱**: 別 issue 起票を提案

### 7. ユーザー承認後のアクション

- **LGTM 承認**: `gh pr comment $ARGUMENTS --body "LGTM. <簡潔な理由> [<session-id>]"` → ユーザーが `gh pr merge $ARGUMENTS --squash` 実行
- **修正依頼**: `gh pr comment $ARGUMENTS --body "<修正依頼内容> [<session-id>]"` → 修正後に再レビュー

### 8. マージ後のフォローアップ

PR に紐づく issue がある場合:

1. `gh issue view <番号> --comments` で現状確認
2. 本文に未チェックの `- [ ]` がないか確認
3. **未完了項目なし** かつ**受け入れ条件全満たし**: `gh issue close <番号> --comment "マージ確認: <session-id> ← PR #番号"` でクローズ
4. **未完了項目あり**: クローズせず、残タスクを継続。別スコープなら子 issue を起票 (`/create-task`)

## 呼び出し例

```
/review-pr 443
```

ユーザーが PR 番号を指定して呼び出す。Claude は自動的に段階を進め、要所で `AskUserQuestion` により判断を仰ぐ。

## 参考

- `docs/l2-workflow.md` §「レビュー受け入れ基準 (#367 対策)」
- `docs/issue-policy.md` — issue ラベル・ライフサイクル
- #367 — レビュープロセス改善の経緯
