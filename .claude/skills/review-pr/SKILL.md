---
name: review-pr
description: PR をレビュー（base ブランチ確認・受け入れ条件ゲート・CI・ロジック/ドキュメント整合性）し、懸念があれば PR コメントで修正依頼、なければ LGTM とマージ提案、マージ後は紐づく issue を処理する。レビュー専用セッションのため PR ブランチへの編集・commit・push は行わない
user-invocable: true
argument-hint: <PR番号>
---

指定された PR をレビューする。`docs/l2-workflow.md` §「レビュー受け入れ基準」に従う。

## 重要: このスキルは「レビュー専用セッション」として動作する

`/review-pr` で起動されたセッションは PR ブランチへの `git checkout` / `Edit` / `Write` / `git commit` / `git push` を一切行わない。指摘事項は PR コメントで PR 作成セッションに依頼する (ロール分離を維持する)。

背景: 2026-04-22 PR #490 / #495 レビュー時、レビューセッションが合意なく修正 commit & push を実施したため明示的な訂正を受けた。PR ブランチ・PR 本文は PR 作成セッションの作業領域で、レビューセッションは観察・指摘・依頼に徹する。

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
- **修正依頼**: 下記「修正依頼コメント投稿」に従う

### 修正依頼コメント投稿 (修正依頼時)

レビュー専用セッションは PR ブランチを編集せず、PR コメントで PR 作成セッションに修正を依頼する。**`git checkout <PR-branch>` / `Edit` / `Write` / `git commit` / `git push` は行わない**。

1. PR コメントで具体的な修正指示を記録する。コメント本文には次の要素を含める:

   - **該当ファイル・行**: `path/to/file.py:123` 形式
   - **現状**: 現在のコードや出力
   - **修正案**: 言語タグ付きコードブロックで提示 (下記サンプル参照)
   - **理由**: 受け入れ条件 X 未達 / ロジック誤り / ドキュメント不整合 等
   - **ローカル検証コマンド**: `pytest tests/test_xxx.py::test_yyy` 等
   - **セッション署名**: 本文末尾に `[セッションID]`

   日本語本文は HEREDOC で `--body-file -` に渡す (Windows + Git Bash で inline `--body` は UTF-8 破損するため)。

   コメント本文サンプル (外フェンスは 4 バッククォート、内側の修正案 fenced block は 3 バッククォート):

   ````markdown
   <指摘タイトル>

   - **該当ファイル・行**: `path/to/file.py:123`
   - **現状**: `<現在のコード片または出力>`
   - **修正案**:

     ```python
     <修正後のコード>
     ```

   - **理由**: <受け入れ条件 X 未達 / ロジック誤り / ドキュメント不整合 等>
   - **ローカル検証コマンド**: `pytest tests/test_xxx.py::test_yyy`

   [セッションID]
   ````

   送信コマンド:

   ```bash
   gh pr comment "$ARGUMENTS" --body-file - <<'EOF'
   (上記サンプル本文を貼る)
   EOF
   ```

2. PR 作成セッション側で修正 commit & push が行われた後、別セッション or 同レビューセッションで `/review-pr $ARGUMENTS` を再実行して受け入れ条件達成を検証する。

3. PR 本文 (`gh pr edit --body`) の書き換えは、修正完了を前提とする内容であれば慎重に。未達状態で「完了前提」に書き換えると不整合を生むため、現状維持が安全。

4. issue 側への方針記録コメント (受け入れ条件 #N の合意内容など) はレビューセッションで行って OK (PR コード編集とは別粒度のアクション)。

### 8. マージ後のフォローアップ

PR に紐づく issue がある場合:

1. `gh issue view <番号> --comments` で現状確認
2. 本文に未チェックの `- [ ]` がないか確認
3. **未完了項目なし** かつ**受け入れ条件全満たし**: `gh issue close <番号> --comment "マージ確認: <session-id> ← PR #番号"` でクローズ
4. **未完了項目あり**: クローズせず、残タスクを継続。別スコープなら子 issue を起票 (`/create-task`)

## 呼び出し例

```text
/review-pr 443
```

ユーザーが PR 番号を指定して呼び出す。Claude は自動的に段階を進め、要所で `AskUserQuestion` により判断を仰ぐ。

## 参考

- `docs/l2-workflow.md` §「レビュー受け入れ基準 (#367 対策)」
- `docs/issue-policy.md` — issue ラベル・ライフサイクル
- #367 — レビュープロセス改善の経緯
