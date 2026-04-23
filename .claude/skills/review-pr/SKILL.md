---
name: review-pr
description: PR をレビュー（base ブランチ確認・受け入れ条件ゲート・CI・ロジック/ドキュメント整合性・ギャップ分析）し、懸念があれば PR コメントで修正依頼、なければ LGTM とマージ提案、マージ後は紐づく issue を処理する。レビュー専用セッションのため PR ブランチへの編集・commit・push は行わない
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

補足: `/enforce-acceptance-criteria` は受け入れ条件の逐条検証、Step 5a は補足ギャップ分析 (カバレッジ・観点・エッジケース) を担う。両者は排他ではなく、受け入れ条件で読めない未テスト分岐や未考慮観点を Step 5a で拾う責務分担。

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

### 5a. ギャップ分析 (明示指示不要で自動実施)

Step 3 (受け入れ条件) / Step 5 (ロジック・ドキュメント) が拾いきれない未テスト分岐・未考慮観点を洗い出す。`/review-pr` 呼び出し時は指示の有無に関わらず標準業務として実施する (#511)。

**列挙プロセス (軸ごとに列挙し優先度付け)**

| 軸 | 取り方 | シグナル |
|---|---|---|
| カバレッジ | 変更行のうち test が hit しない分岐を洗い出す | 未テスト分岐残数 |
| 観点 | happy path / error path / edge case を網羅 | 観点欠落 |
| エッジケース | 入力境界 (空 / null / 巨大) / 並行性 / resource 枯渇 | 想定外入力 |
| 優先度 | 受け入れ条件関連 = P1 必須、nice-to-have = P3 推奨 | ブロッカー判定 |

**long-running / integration 検証観点**

- 長時間動画 (2 時間以上) / GPU mode / audio 統合 / 大規模入力 等は mock 不可
- レビュー側は「手動検証が必要」と明示し、PR 作成セッションに `/test-pr` 実施を依頼する (`docs/l2-workflow.md` §「タスク種別と進め方」の "PR テスト" 行参照)
- 自動 CI で担保できる範囲と、手動検証が必須な範囲の境界を明示してユーザー / PR 作成セッションに伝達する

### 6. レビュー結果をユーザーに報告

`AskUserQuestion` で以下を提示する:

- **LGTM (問題なし)**: ユーザーに `--squash` マージを提案
- **修正依頼**: 具体的な指摘内容を表示し、PR コメントに投稿するかユーザー確認
- **テスト不足**: 追加テスト実行を提案
- **スコープ逸脱**: 別 issue 起票を提案

**レビュー報告テンプレート** (PR コメントまたはユーザー提示時の推奨構造):

````markdown
## 受け入れ条件チェック (逐条)

| # | 条件 | 実証 (diff / test / log) | 判定 |
|---|---|---|---|
| 1 | <条件 1> | `path/to/file.py:123` / `test_xxx` / CI log | ○ / × / 部分的 |
| 2 | ... | ... | ... |

## ギャップ分析 (Step 5a)

- **カバレッジ**: <未テスト分岐 / 観点欠落 / なし>
- **観点**: <happy path / error path / edge case の抜け / なし>
- **エッジケース**: <入力境界 / 並行性 / resource 枯渇 / なし>

## 検証推奨

- **自動 (CI)**: `pytest tests/test_xxx.py::test_yyy` / `ruff check .`
- **手動 (/test-pr)**: <long-running / GPU / audio 統合 の具体手順>

## 判定

<LGTM / 修正依頼 / ブロッカー>

[<session-id>]
````

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

## Red flags (レビュー中に浮かんだら STOP)

Iron Law Red Flags と呼応。以下の合理化が浮かんだら LGTM 寸前でも止まる。

| 出てくる合理化 | 実態 |
|---|---|
| 「受け入れ条件は大体満たしてる」 | Iron Law 1 違反。逐条引用 + diff / test の対応付けが必須 |
| 「明らかな diff だからレビュー簡略化でよい」 | Step 5a ギャップ分析 skip は NG。明示指示不要で自動実施 |
| 「unit test pass だから手動検証不要」 | GPU / audio / 長時間動画は mock 不可。PR 作成セッションに `/test-pr` 依頼 |
| 「観察コメントだけ残して別 issue にしない」 | #399 B 違反。観察で止めず、別 issue 起票または scope-guard で escalate |
| 「PR ブランチを checkout して自分で修正した方が速い」 | レビュー専用セッション違反。PR コメントで PR 作成セッションに依頼 (本ファイル冒頭「重要」節参照) |

## よくある失敗

- **受け入れ条件の逐条引用を飛ばす**: 「全項目 OK」のサマリで済ませる → Iron Law 1 違反。`/enforce-acceptance-criteria` の出力を再確認し、条件 1 つずつに diff / test / log を対応付ける
- **ギャップ分析を自然言語コメントだけで書く**: 「テスト不足ぎみ」等の印象コメント → Step 5a の軸 (カバレッジ / 観点 / エッジケース) に紐付けて具体化し、軸ごとに「未テスト箇所 X」「欠落観点 Y」で列挙する
- **long-running 検証を自己判断で OK とする**: unit test pass = 全部 OK と誤解。GPU / 長時間動画 / audio 統合は mock 不可のため、PR 作成セッションに `/test-pr` 実施を明示依頼する
- **提示フォーマットを無視して口語で書く**: レビュー結果が PR コメントに混在して追跡困難 → Step 6 の「レビュー報告テンプレート」構造で投稿

## 参考

- `docs/l2-workflow.md` §「レビュー受け入れ基準 (#367 対策)」 / §「タスク種別と進め方」の "PR テスト" 行
- `docs/issue-policy.md` — issue ラベル・ライフサイクル
- #367 — レビュープロセス改善の経緯
- #511 — 本 skill への #475 memory 由来 3 観点 + [mizchi empirical-prompt-tuning](https://github.com/mizchi/chezmoi-dotfiles/blob/main/dot_claude/skills/empirical-prompt-tuning/SKILL.md) 参考ブラッシュアップ
