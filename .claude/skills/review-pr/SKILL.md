---
name: review-pr
description: PR をレビュー（base ブランチ確認・受け入れ条件ゲート・CI・ロジック/ドキュメント整合性）し、懸念があれば修正依頼、なければ LGTM とマージ提案、マージ後は紐づく issue を処理する。修正は同セッションで継続
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

**まず `/enforce-acceptance-criteria $ARGUMENTS` を呼び出し**、Iron Law (全項目の逐条検証) によるゲートを通過させる。このスキルが未達と判定した場合、ここで処理を終了し修正依頼フローへ進む。

ゲート通過後、以下の補助チェックを行う:

- [ ] **実装内容が PR 説明と一致**: 差分と PR body の乖離を検出 (PR body に書かれていない無関係な変更がないか = scope-guard 観点)
- [ ] **テスト存在**: 変更行に対応する test ケースがあるか
  - 新規関数・メソッド: 単体テスト必須
  - バグ修正: baseline FAIL → FIX 検証テストが望ましい
  - UI/出力変更: スナップショットテストまたは contract テスト
- [ ] **複数 issue 束ね時の合理性**: 1 PR で複数 issue を閉じる場合、束ねる理由が PR 本文に明記されているか
- [ ] **Phase 分割時の子 issue 起票**: 「Phase 2 は別途」等で残タスクを先送りする場合、子 issue 番号が親 issue に記載されているか
- [ ] **`Closes` / `Fixes` / `Resolves` キーワードが使われていない**: issue クローズは手動で行う（`/enforce-acceptance-criteria` が verified を返していればこの項目は自動 PASS。二重チェックになるため明示スキップ可）

### 4. CI / Lint / Test ステータス確認

```bash
gh pr checks $ARGUMENTS
```

- 全 green: 次へ
- 失敗あり: 失敗ジョブ名と概要をユーザーに報告し、修正依頼コメントを投稿
- 未完了: 完了を待つ or ユーザーに判断を仰ぐ

### 5. ロジック / ドキュメントレビュー

PR の変更種別に応じて以下を確認する:

**共通観点**:
- 変更の意図が PR の説明と一致しているか
- アーキテクチャに沿っているか (`CLAUDE.md` §モジュール構成、`docs/design-overview.md`)
- セキュリティモデルが守られているか (特に外部入力処理、subprocess 呼び出し)

**ドキュメント変更 PR の場合**:
- doc 内容が元 issue の要件と一致しているか
- doc が言及するソースコード (関数名、ファイルパス、設定値) が現状と整合しているか
- 関連する既存 doc (`CLAUDE.md`, `docs/cli-spec.md`, `docs/design-overview.md`, `docs/l2-workflow.md` 等) との矛盾がないか
- doc が言及するテスト / CLI 出力サンプルが実装と一致しているか

**コード / テスト変更 PR の場合**:
- 関連ドキュメント (`docs/cli-spec.md`, `docs/design-overview.md`, `README.md`, `CLAUDE.md` 等) が更新されているか
- **特に CLAUDE.md / docs に「追加予定」「今後実装」等の予告記述があり、本 PR がその実装に該当する場合、予告文を実装済み記述に更新すること。更新漏れは Step 6 で修正依頼対象**
- コード変更がドキュメント記述と矛盾していないか
- 出力形式変更の場合、`docs/cli-spec.md` の出力例も更新されているか (#343 系の再発防止)

### 6. レビュー結果をユーザーに報告

`AskUserQuestion` で以下を提示する:

- **LGTM (問題なし)**: ユーザーに `--squash` マージを提案
- **修正依頼**: 具体的な指摘内容を表示し、PR コメントに投稿するかユーザー確認
- **テスト不足**: 追加テスト実行を提案
- **スコープ逸脱**: 別 issue 起票を提案

### 7. ユーザー承認後のアクション

- **LGTM 承認**: `gh pr comment $ARGUMENTS --body "LGTM. <簡潔な理由> [<session-id>]"` → ユーザーが `gh pr merge $ARGUMENTS --squash` 実行
- **修正依頼**: 下記「修正フロー」に従う

### 修正フロー (修正依頼時)

新ワークフローでは**単一セッションが続けて修正を行う**ため、旧 engineer ↔ lead-engineer の往復は発生しない:

1. `gh pr comment $ARGUMENTS --body "<修正依頼内容> [<session-id>]"` で PR に具体的な修正指示を記録
2. 同セッション内で PR の作業ブランチをチェックアウト (`git checkout <PR-branch>` または worktree 使用)
3. 修正を実装 (Edit / Write ツール、必要ならテスト追加)
4. `ruff check` / `pytest` 通過を確認
5. `git commit` + `git push` で同じ PR に追加コミット
6. `/review-pr $ARGUMENTS` を再実行して受け入れ条件を再確認

PR を別ブランチに切り直す必要はなし。修正コミットが積み重なることで履歴として残る。squash マージで最終的に 1 コミットに統合される。

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
