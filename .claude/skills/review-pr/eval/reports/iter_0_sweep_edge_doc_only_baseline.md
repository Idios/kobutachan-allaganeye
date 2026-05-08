# Iteration 0 (baseline): シナリオ E-3 review

> **評価モード**: Iteration 0 baseline。現行 SKILL.md (sweep 規約 / Step 5c なし) に忠実に動作する。
> doc-only PR に対し grep 全件 sweep を強制する規約が current SKILL.md にないため、[critical] 要件 #2 / #3 での失敗が期待される。

---

## Step 1: PR 概要

```text
PR #953: docs: l2-workflow.md の Self-Test Report 規約 v2 化 (Refs #944)
baseRefName: develop-0.2.0
labels: [doc], l2-workflow
```

**変更ファイル**:

- `docs/l2-workflow.md` — §Self-Test Report 規約を v2 に更新 (+34 / -12)
- (その他ファイルの変更は diff に含まれない)

**PR 本文要約**: #944 受け入れ条件を満たす doc-only 修正。`docs/l2-workflow.md` のみ変更と主張。受け入れ条件 AC §2-4 (specs/ / CLAUDE.md / markdownlint) も `[x]` とされているが、diff が `l2-workflow.md` のみ。

---

## Step 2: ベースブランチ同期確認

**2.1 形式確認**: `baseRefName = develop-0.2.0` — `develop-x.x.x` 形式。OK。

**2.2 base 最新化と直近マージ PR**:
シナリオに明示情報なし。影響候補 PR なし相当。

**2.3 同期判定**: skip (影響候補なし)

**2.4 並行 worktree PR 重複確認**: 検出ゼロ相当。

---

## Step 3: 受け入れ条件チェック

**issue #944 受け入れ条件** (フォールバック: 手動逐条検証):

| # | 受け入れ条件 | 実証 | 判定 |
| --- | --- | --- | --- |
| 1 | `docs/l2-workflow.md` §Self-Test Report 規約 v2 化を完了 | diff: §Self-Test Report 規約に v2 必須項目追加、チェックリスト更新 | ○ |
| 2 | `docs/l2-workflow.md` 内の全 Self-Test Report 参照箇所で v2 用語に統一 | diff 確認: v1→v2 の明示変更あり。ただし他ファイルへの波及は diff に現れない | 部分的 |
| 3 | `docs/superpowers/specs/` 内の関連 spec が v2 用語に追従 | diff に含まれない。PR 本文 `[x]` だが確認不可 | 部分的 |
| 4 | `CLAUDE.md` の関連記述が v2 用語に追従 | diff に含まれない。PR 本文 `[x]` だが確認不可 | 部分的 |
| 5 | markdownlint check green | PR 本文: 「`bash scripts/check-markdownlint.sh` ローカル実行で 0 errors」 | ○ |

**着目点**: AC §2-4 がすべて `[x]` だが diff が `l2-workflow.md` のみ。AC §2-4 の確認手段が PR 本文に記載されていない。grep 実測または変更ファイルの追加が必要。

**受け入れ条件判定**: AC §3 / §4 が確認不可 → 部分的 FAIL。

---

## Step 4: CI / Lint ステータス

シナリオ記載: 「CI: `docs/l2-workflow.md` の markdownlint は green。`requirements.md` / `SKILL.md` への波及は CI が自動検知しない」

**CI 判定**: markdownlint は green だが全ファイルスキャン範囲が不明。次へ (AC §5 は ○)。

---

## Step 5: ロジック / ドキュメントレビュー

### 5.1 doc 整合性確認

**ドキュメント変更 PR の観点**:

1. **doc 内容と issue 要件の整合**:
   - diff で追加された `sweep_grep_commands` / `sweep_hits_total` / `step5c_completed` フィールドは AC §1 の v2 規約要件に合致。
   - `Step 5c sweep 完了確認` チェックリスト項目も追加されている。
   - AC §1: ○

2. **AC §2: `docs/l2-workflow.md` 内の全参照箇所で v2 用語に統一**:
   - diff を見ると `Self-Test Report v1` → `v2` の変更 / `サンプルテンプレート (v1):` → `(v2):` の変更が含まれている。
   - 同ファイル内の他箇所に `v1` 表記が残存していないか diff 外では確認できない。

3. **AC §3 / §4: 他ファイル追従**:
   - `docs/superpowers/specs/` / `CLAUDE.md` / `.claude/skills/review-pr/` への波及は diff に現れない。
   - PR 本文「主な変更ファイル: `docs/l2-workflow.md` (+34 / -12)」と記載されており、他ファイルの変更は diff に含まれていない。
   - **root cause 識別**: AC §2-4 の確認根拠が diff 外にあり、grep 実測なしでは「PR 本文の `[x]` を信頼するしかない」状態。
   - 環境制約 §D (doc-only PR の CI 波及検証) に従い、パス・識別子変更 (`Self-Test Report v1` → v2 用語) が他ファイルに及ぶか確認が必要。

**current SKILL.md §D 適用判定**:
`docs/l2-workflow.md` の変更は「純粋な文章のみ」ではなく、用語 (`Self-Test Report v1` → `v2`、`sweep_grep_commands` 等) の変更を含む → §D Step 1: grep で確認が必要。

→ `grep -rn 'Self-Test Report v1\|v1 必須項目\|v1 テンプレート' docs/ CLAUDE.md .claude/skills/review-pr/` を実施すべき。

**ただし**: current SKILL.md Step 5a に「grep 全件 sweep コマンドを提示する」という明示規約はなく、§D は「grep で確認が必要」と述べているが、全件リストを Step 5b に転記することを強制していない。

---

## Step 5a: ギャップ分析

| 軸 | 内容 |
| --- | --- |
| カバレッジ | AC §2-4 の確認が diff 外。`docs/superpowers/specs/` (3 hits) / `plans/` (2 hits) / `CLAUDE.md` (2 hits) / `requirements.md` (3 hits) / `SKILL.md` (2 hits) に旧用語残存の可能性 |
| 観点 | doc-only PR でも用語変更は他ファイルに波及する。SKILL.md §D 適用必須 |
| エッジケース | `requirements.md` の旧用語残存が markdownlint 違反を含む場合、CI 波及検証 §D で摘出対象 |
| 優先度 | AC §3 / §4 の確認不可: P1 (受け入れ条件未達に相当) |

**環境制約 §D 適用**:
パス・識別子変更 (用語変更) を含む doc PR → grep 確認が必須。

**current SKILL.md の挙動 (sweep 規約なし)**:
§D の適用は認識できる。「grep で確認すべき」という一般指摘が Step 5a に出力されるが、**grep コマンドを Step 5a で具体的に提示し、結果を全件 Step 5b に転記する規約 (Step 5c) は現行 SKILL.md にない**。

結果: 「他ファイルへの波及を grep で確認してください」という (A) PR コメントになり、hits 数 (12 件) と具体ファイル列挙はなし。

---

## Step 5b: トリアージ表

| # | 摘出内容 | 出所 | 処置 | 根拠 |
| --- | --- | --- | --- | --- |
| 1 | AC §3: `docs/superpowers/specs/` の関連 spec が v2 用語に追従しているか diff 外で確認不可。grep 実測または diff への追加が必要 | 受け入れ条件 #3 | (A) PR コメント | AC 直結。grep で `Self-Test Report v1` 等を検索し追従漏れを確認の上、PR 内修正を要求 |
| 2 | AC §4: `CLAUDE.md` の v2 用語追従が diff 外で確認不可。grep 実測または diff への追加が必要 | 受け入れ条件 #4 | (A) PR コメント | AC 直結。同上 |
| 3 | 環境制約 §D: 用語変更 (`Self-Test Report v1` → v2、`sweep_grep_commands` 等) が他 doc ファイルに波及していないか全件 grep 確認が必要。`docs/superpowers/` / `.claude/skills/review-pr/` / `CLAUDE.md` を対象に実施すること | 5 ドキュメント / §D CI 波及 | (A) PR コメント | doc-only でも用語変更は他ファイルに波及する。§D Step 1 適用 |

**注**: 「他ファイルに波及している可能性がある」という一般的指摘で 3 行に整理したが、hits 分布表に記載された 12 hits の個別列挙 (specs/ 3 + plans/ 2 + CLAUDE.md 2 + requirements.md 3 + SKILL.md 2) はできていない。current SKILL.md に全件列挙規約がないため。

---

## Step 6: レビュー結果

```markdown
# Review Round 1

## ベース同期確認 (Step 2)

- **形式 (2.1)**: develop-0.2.0 (OK)
- **base 最新化と直近マージ PR (2.2)**: 影響候補 PR なし相当
- **同期判定 (2.3)**: skip
- **並行 worktree PR (2.4)**: 検出ゼロ

## 受け入れ条件チェック (逐条)

| # | 条件 | 実証 | 判定 |
|---|---|---|---|
| 1 | l2-workflow.md §Self-Test Report v2 化 | diff: v2 必須項目追加・チェックリスト更新 ○ | ○ |
| 2 | l2-workflow.md 内の全参照で v2 用語統一 | diff で一部確認。他箇所は diff 外 | 部分的 |
| 3 | docs/superpowers/specs/ が v2 用語に追従 | diff 未含 → 確認不可 | 部分的 |
| 4 | CLAUDE.md が v2 用語に追従 | diff 未含 → 確認不可 | 部分的 |
| 5 | markdownlint check green | PR 本文: ローカル 0 errors | ○ |

## ギャップ分析 (Step 5a)

- **カバレッジ**: AC §2-4 の確認が diff 外。他ファイルに旧用語残存の可能性 (最大 12 hits)
- **観点**: doc-only PR でも §D 適用 — grep 確認必須
- **エッジケース**: requirements.md 旧用語が markdownlint 違反を含む可能性

## 摘出課題トリアージ (Step 5b)

| # | 摘出内容 | 出所 | 処置 | 根拠 |
|---|---|---|---|---|
| 1 | AC §3: specs/ の v2 追従が diff 外で未確認 | 受け入れ条件 #3 | (A) PR コメント | AC 直結 |
| 2 | AC §4: CLAUDE.md の v2 追従が diff 外で未確認 | 受け入れ条件 #4 | (A) PR コメント | AC 直結 |
| 3 | §D CI 波及: 用語変更が docs/superpowers/ / .claude/skills/ / CLAUDE.md に波及している可能性 → grep 全件確認を要求 | §D ドキュメント | (A) PR コメント | doc-only でも用語変更は波及する |

## 判定

**修正依頼**: AC §3 / §4 確認不可。grep 実測結果を PR に追加するよう要求。
LGTM 不可。
```

---

## 要件チェックリスト評価 (シナリオ E3)

| # | 要件 | 評価 | 根拠 |
| --- | --- | --- | --- |
| 1 | [critical] doc-only でも root cause (旧用語 literal の他ファイル残存) を Step 5 で識別している | ○ | Step 5.1 で「AC §2-4 の確認が diff 外」「環境制約 §D 適用必須」を識別。「grep で確認すべき」と明示 |
| 2 | [critical] `grep -rn` 全件 sweep コマンドを Step 5a で提示している | × | grep コマンドの具体的文字列を Step 5a に提示していない。「grep 確認を要求」という (A) PR コメントの指示にとどまる |
| 3 | [critical] 12 hits を Step 5b トリアージ表に全件列挙している | × | 3 行の一般的指摘にとどまり、specs/ 3 + plans/ 2 + CLAUDE.md 2 + requirements.md 3 + SKILL.md 2 の 12 hits を個別ファイル列挙できていない |
| 4 | [critical] 「軽微な doc 修正だから一部対応で OK」のような握り潰しを Red Flag として識別している | 部分的 | 「grep 実測を要求する」という姿勢は取れているが、「この種の握り潰し = Red Flag」という明示的な識別・言及はしていない |
| 5 | 環境制約 §D に従って全 .md をスキャンし、残存ファイルの markdownlint 状態を実測している | × | §D 適用の認識はあるが、実際の `bash scripts/check-markdownlint.sh` 実行には至っていない (「requirements.md が markdownlint 違反の可能性がある」とエッジケースで言及のみ) |
| 6 | LGTM ではなく修正依頼を出している | ○ | Step 6 で修正依頼判定 |

## [critical] 達成率

**1 / 4** (○ 1 / [critical] 4 件中)

- 達成: 要件 #1 (root cause 識別 — doc-only でも sweep 必要と認識)
- 未達: 要件 #2 (grep コマンド非提示) / #3 (12 hits 非列挙) / #4 (部分的 — Red Flag 明示識別なし)

## 不明瞭点 / 構造的欠陥

1. **§D 適用の認識と grep 実行の間にギャップがある**: current SKILL.md §D は「grep で確認が必要」と述べているが、「Step 5a でコマンドを提示し結果を全件 Step 5b に転記する」までは強制されていない。結果として「grep してください」という (A) コメントになり、PR 作成者が部分的に対応→再レビューで残存発覚という Round divergence が生じうる。

2. **doc-only PR への sweep mandate が明文化されていない**: 「コード変更ではないから sweep は不要」という Red Flag 思考を防ぐ明示規約が current SKILL.md にない。§D は「パス・識別子変更を含む doc PR は grep 確認必須」と書いているが、全件列挙を Step 5b に転記する強制がない。

3. **12 hits の特定が PR 作成者に委ねられる**: 「grep で確認して PR に追加してください」という指示では、PR 作成者が一部ファイルのみ対応して再提出することになり、Round 2 / Round 3 で残存が順次発覚するパターン (#661 Round 3 と同構造) が再現する。

4. **requirements.md / SKILL.md の旧用語残存が見落とされやすい**: `docs/superpowers/` 以下のファイルは「仕様書」という認識で diff 外として見逃されやすく、`.claude/skills/review-pr/SKILL.md` と `eval/requirements.md` はさらに「eval 資料」として見逃されやすい。full sweep mandate があれば一括摘出できたが、current SKILL.md では explicit な指摘のみになる。
