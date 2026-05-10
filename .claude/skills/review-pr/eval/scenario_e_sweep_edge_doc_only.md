# シナリオ E-3: sweep edge — doc-only PR の PR body 複数セクション追従漏れ

参考事例: #661 (GUI クラッシュ・エラー伝搬ハンドリング、PR body 複数セクション追従漏れ、Round 3 で LGTM)

## 設定

**仮想 PR 番号**: #953

**タイトル**: `docs: l2-workflow.md の Self-Test Report 規約 v2 化 (Refs #944)`

**関連 issue #944**:

```markdown
## 概要

l2-workflow.md の Self-Test Report 規約を v2 に更新する。
v2 の変更点:
- `Self-Test Report` セクションの必須項目に `sweep_grep_commands` フィールドを追加
- 「Step 5c sweep 完了確認」を必須チェックリスト項目として追記
- `review-pr/SKILL.md` / `review-pr/eval/requirements.md` / `CLAUDE.md` の参照箇所を同期

## 受け入れ条件

- [ ] `docs/l2-workflow.md` §Self-Test Report 規約 v2 化を完了
- [ ] `docs/l2-workflow.md` 内の全 Self-Test Report 参照箇所で v2 用語に統一
- [ ] `docs/superpowers/specs/` 内の関連 spec が v2 用語に追従
- [ ] `CLAUDE.md` の関連記述が v2 用語に追従
- [ ] markdownlint check green
```

---

## モック PR #953

**タイトル**: `docs: l2-workflow.md の Self-Test Report 規約 v2 化 (Refs #944)`

**baseRefName**: `develop-0.2.0`

**labels**: `[doc]`, `l2-workflow`

### モック PR 本文

```markdown
## 概要

#944 の受け入れ条件を満たす doc-only 修正。

- `docs/l2-workflow.md` §Self-Test Report 規約を v2 に更新
  - `sweep_grep_commands` フィールドを必須項目として追加
  - 「Step 5c sweep 完了確認」チェックリスト項目を追記

## 主な変更ファイル

- `docs/l2-workflow.md`: v2 規約本体 (+34 / -12)

## 受け入れ条件確認

- [x] `docs/l2-workflow.md` §Self-Test Report 規約 v2 化を完了
- [x] `docs/l2-workflow.md` 内の全 Self-Test Report 参照箇所で v2 用語に統一
- [x] `docs/superpowers/specs/` 内の関連 spec が v2 用語に追従
- [x] `CLAUDE.md` の関連記述が v2 用語に追従
- [x] markdownlint check green

## 動作確認

`bash scripts/check-markdownlint.sh` ローカル実行で 0 errors。
```

---

## モック diff

```diff
--- a/docs/l2-workflow.md
+++ b/docs/l2-workflow.md
@@ -211,8 +211,19 @@
 ### Self-Test Report 規約

-PR 本文末尾に Self-Test Report セクションを設ける。
+PR 本文末尾に Self-Test Report セクション (v2) を設ける。
+
+v2 必須項目:
+
+- `sweep_grep_commands`: Step 5c で実行した grep コマンド全件をリスト
+- `sweep_hits_total`: grep 全件 sweep で検出した hits 合計数
+- `step5c_completed`: `true` / `false` (sweep 未実施の場合は `false` と明記)

 必須チェックリスト:

 - [ ] CI (lint / pytest / vitest) green
+- [ ] Step 5c sweep 完了確認 (`step5c_completed: true`)
 - [ ] 受け入れ条件全件 ○
 - [ ] スコープ外変更なし (または (B) issue 起票済み)
@@ -245,3 +256,3 @@
-Self-Test Report サンプルテンプレート (v1):
+Self-Test Report サンプルテンプレート (v2):

 \`\`\`markdown
@@ -252,0 +264,4 @@
+sweep_grep_commands:
+  - grep -rn 'old_literal' .
+sweep_hits_total: 0
+step5c_completed: true
 \`\`\`
```

---

## hits 分布表 (旧用語 `Self-Test Report v1` / `v1 必須項目` の残存)

PR diff は `docs/l2-workflow.md` のみ変更。他ファイルへの波及は diff に現れない:

| ファイル | hits 数 | 残存パターン |
| --- | --- | --- |
| `docs/l2-workflow.md` | 0 | diff で修正済み |
| `docs/superpowers/specs/2026-05-08-lane-iv-b-group-g-design.md` | 3 | `Self-Test Report v1` / `step5c_completed 未定義` / `sweep_grep_commands` 未記載 |
| `docs/superpowers/plans/2026-05-08-lane-iv-b-group-g-implementation.md` | 2 | `v1 テンプレート参照` / `sweep_hits_total` 未定義 |
| `CLAUDE.md` | 2 | §PR 作成ルール内で `l2-workflow.md 各 §` 参照 — v2 フィールド未言及 |
| `.claude/skills/review-pr/eval/requirements.md` | 3 | `sweep 規約` 記述が旧仕様のまま (Step 5c 参照なし) |
| `.claude/skills/review-pr/SKILL.md` | 2 | §Step 5b 末尾に Step 5c 参照なし / Red flags 表に sweep flag 未追記 |

**合計: 12 hits** が diff に含まれない残存として散在。

---

## 意図的に仕込んだ要素 (subagent が摘出できるか試す)

1. **sweep 失敗トリガー**: PR 本文 AC §2-4 はすべて `[x]` だが、diff は `l2-workflow.md` のみ。
   他 4 ファイル 12 hits への波及が diff から見えず、grep sweep なしでは「AC 全件 ○」と
   誤判断するリスク。

2. **grep 全件 sweep で実行すべきコマンド**:

   ```bash
   grep -rn 'Self-Test Report v1\|v1 必須項目\|v1 テンプレート' \
     docs/ CLAUDE.md .claude/skills/review-pr/
   ```

   または用語の新旧を直接比較:

   ```bash
   grep -rn 'sweep_grep_commands\|step5c_completed\|sweep_hits_total' \
     docs/superpowers/ CLAUDE.md .claude/skills/review-pr/
   ```

3. **doc-only でも sweep は必須**: 「コード変更なし = 影響限定的」という誤認識が
   「軽微な doc 修正だから一部対応で OK」の Red Flag につながる。
   PR #661 Round 2 と同構造。

4. **AC §2-4 の確認手段が不明確**: PR 本文で全 [x] とされているが、
   diff を見ると `l2-workflow.md` しか変更されていない。
   AC §2 (specs/ 追従) / §3 (CLAUDE.md 追従) / §4 (markdownlint) は diff で確認不可 →
   grep / markdownlint 実行で実測すべき。

5. **markdownlint CI 波及**: doc-only PR の CI は markdownlint のみ。
   残存する旧用語の `requirements.md` が markdownlint 違反を含む場合、
   §D 環境制約の doc-only CI 波及検証として摘出対象。

---

## 期待されるレビュー観点

### Step 5 (課題摘出) で検出すべき観点

- diff が `docs/l2-workflow.md` のみで、AC §2-4 の「他ファイル追従」が
  diff から確認できない → grep / markdownlint 実行で実測すべき

### Step 5a (grep 全件 sweep) で実行すべきコマンド

```bash
grep -rn 'v1 必須項目\|Self-Test Report v1\|sweep_grep_commands' \
  docs/superpowers/ CLAUDE.md .claude/skills/review-pr/
```

期待結果:

- `docs/superpowers/specs/...design.md` 3 hits
- `docs/superpowers/plans/...implementation.md` 2 hits
- `CLAUDE.md` 2 hits
- `.claude/skills/review-pr/eval/requirements.md` 3 hits
- `.claude/skills/review-pr/SKILL.md` 2 hits

**合計 12 hits**

### Step 5b (トリアージ表) に転記すべき全件

| # | ファイル | root cause | 分類 | 対応 |
| --- | --- | --- | --- | --- |
| 1-3 | `docs/superpowers/specs/...design.md` | v2 用語追従漏れ | (A) | PR 内修正 |
| 4-5 | `docs/superpowers/plans/...implementation.md` | v2 用語追従漏れ | (A) | PR 内修正 |
| 6-7 | `CLAUDE.md` | v2 フィールド未言及 | (A) | PR 内修正 |
| 8-10 | `.claude/skills/review-pr/eval/requirements.md` | Step 5c 参照なし | (A) | PR 内修正 |
| 11-12 | `.claude/skills/review-pr/SKILL.md` | sweep flag 未追記 | (A) | PR 内修正 |

### 期待される出力と挙動

#### Step 6 (レビュー報告)

- Step 5c で実行した grep コマンドと 12 hits 全件を **報告 markdown 内のトリアージ表**に転記すること
- `AskUserQuestion` は呼ばない。`gh pr comment` 等の **PR コメント投稿は一切行わない**
- 「修正依頼本文に grep コマンドと hits を同梱して PR コメント投稿する」は新方針に反する — 報告 markdown 内に含めるのが正しい

#### Step 7 (次のアクション提案)

- 次のアクション提案テンプレートを user に提示する:
  - 判定: 修正依頼 ((A) 課題が 12 件残っているため)
  - **`/iterate-review $ARGUMENTS` 起動推奨**を明記
  - `/iterate-review` が主セッションで (A) 修正を実施し、全件解消後に summary コメント 1 個を投稿してマージ準備まで自動化

### Red Flag (不合格判定)

以下のいずれかが発生したら sweep 規約未適用:

- 「doc-only 修正だから影響は限定的」と判断して grep sweep を省略
- `docs/l2-workflow.md` の変更のみ確認して AC 全件 ○ と判定
- 「軽微な用語統一だから一部ファイルのみ追従で OK」と判断してトリアージ表を省略
- markdownlint が `l2-workflow.md` のみの green を「全体 green」と誤認
- `gh pr comment` で per-finding 修正依頼を投稿する (新方針違反)

### 検証環境情報

- CI: `docs/l2-workflow.md` の markdownlint は green。
  `requirements.md` / `SKILL.md` への波及は CI が自動検知しない (glob 対象外の可能性)
- 紐づく issue: #944 (1:1)
- `/enforce-acceptance-criteria` gate: AC §2-4 の grep 実測なしでは PASS 不可
- 環境制約 §D doc-only CI 波及: `bash scripts/check-markdownlint.sh` で全 .md をスキャンし、
  残存ファイルの markdown lint 状態を実測すること
