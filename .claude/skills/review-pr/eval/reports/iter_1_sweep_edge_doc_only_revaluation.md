# Iteration 1 (revaluation): シナリオ E-3 (sweep edge — doc-only literal 散在) review

> **評価モード**: Iteration 1 revaluation。**NEW subagent** — Iteration 0 結果は参照しない。
> 改訂済み SKILL.md (commit `fc37237`、Step 5c 同種パターン sweep 規約追加) に従って評価する。

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

**PR 本文要約**: #944 受け入れ条件を満たす doc-only 修正。変更は `docs/l2-workflow.md` のみ。AC §2-4 (specs/ / CLAUDE.md / markdownlint) も `[x]` とされているが diff が `l2-workflow.md` のみのため確認不可。

---

## Step 2: ベースブランチ同期確認

**2.1 形式確認**: `baseRefName = develop-0.2.0` — `develop-x.x.x` 形式。OK。

**2.2 base 最新化と直近マージ PR**:
シナリオに明示情報なし。影響候補 PR なし相当。

**2.3 同期判定**: skip (影響候補なし)

**2.4 並行 worktree PR 重複確認**: 検出ゼロ相当。

---

## Step 3: 受け入れ条件チェック

**issue #944 受け入れ条件** (フォールバック §B: `/enforce-acceptance-criteria` 実行不可のため手動逐条検証):

| # | 受け入れ条件 | 実証 (diff / test / log) | 判定 |
| --- | --- | --- | --- |
| 1 | `docs/l2-workflow.md` §Self-Test Report 規約 v2 化を完了 | diff: v2 必須項目 (`sweep_grep_commands` / `sweep_hits_total` / `step5c_completed`) 追加、チェックリスト更新 | ○ |
| 2 | `docs/l2-workflow.md` 内の全 Self-Test Report 参照箇所で v2 用語に統一 | diff で一部確認 (`Self-Test Report サンプルテンプレート (v1):` → `(v2):`)。ただし diff 外参照箇所は未確認 | 部分的 |
| 3 | `docs/superpowers/specs/` 内の関連 spec が v2 用語に追従 | diff に含まれない。PR 本文 `[x]` だが確認不可 | 部分的 |
| 4 | `CLAUDE.md` の関連記述が v2 用語に追従 | diff に含まれない。PR 本文 `[x]` だが確認不可 | 部分的 |
| 5 | markdownlint check green | PR 本文: 「`bash scripts/check-markdownlint.sh` ローカル実行で 0 errors」 | ○ |

**着目点**: AC §2-4 がすべて `[x]` だが diff が `l2-workflow.md` のみ。AC §2-4 の確認根拠が diff 外にあり、grep 実測と markdownlint 全件スキャンが必要。

**受け入れ条件判定**: AC §3 / §4 が確認不可 → 部分的 FAIL。

---

## Step 4: CI / Lint ステータス

シナリオ記載: 「CI: `docs/l2-workflow.md` の markdownlint は green。`requirements.md` / `SKILL.md` への波及は CI が自動検知しない」

**CI 判定**: markdownlint は green だが全ファイルスキャン範囲が不明。環境制約 §D 適用 → 全 .md に対して `bash scripts/check-markdownlint.sh` で実測が必要。

---

## Step 5: ロジック / ドキュメントレビュー

### 5.0 code quality (subagent 委譲)

doc-only PR のためサブエージェント委譲は省略。doc 整合性確認を本 step で実施する。

### 5.1 project 固有 doc 整合性確認

**ドキュメント変更 PR の観点**:

1. **doc 内容と issue 要件の整合**:
   - diff で追加された `sweep_grep_commands` / `sweep_hits_total` / `step5c_completed` フィールドは AC §1 の v2 規約要件に合致。
   - `Step 5c sweep 完了確認` チェックリスト項目も追加されている。
   - AC §1: ○

2. **AC §2: `docs/l2-workflow.md` 内の全参照箇所で v2 用語に統一**:
   - diff では `Self-Test Report サンプルテンプレート (v1):` → `(v2):` の変更が確認できる。
   - ただし同ファイル内の他箇所に `v1` 表記が残存していないかは diff 外。

3. **AC §3 / §4: 他ファイル追従**:
   - `docs/superpowers/specs/` / `CLAUDE.md` / `.claude/skills/review-pr/` への波及は diff に現れない。
   - PR 本文「主な変更ファイル: `docs/l2-workflow.md` (+34 / -12)」から他ファイルの変更がないことを示す。
   - **root cause 識別**: PR diff は `l2-workflow.md` のみで、AC §3 / §4 の他ファイル追従が実際に行われたか確認不可。grep 実測が必須。

4. **環境制約 §D 適用**:
   - 用語変更 (`Self-Test Report v1` → `v2`、`sweep_grep_commands` 等の新フィールド) を含む doc PR → §D Step 1: grep で確認が必要。
   - 「純粋な文章のみ」ではなく識別子・用語の変更を含むため、他ファイルへの波及確認は必須。

**Step 5c 適用**: root cause (旧用語 literal の他ファイル残存) を識別したため、**Step 5c 同種パターン全件 sweep 規約** に従い、grep 全件 sweep を実施する。

**重要**: 「doc-only 修正だから sweep 不要」という判断は **Red Flag** (SKILL.md §Red flags 表参照)。doc-only でも用語変更は他ファイルに波及する。

---

## Step 5a: ギャップ分析 (Step 5c: grep 全件 sweep)

| 軸 | 内容 |
| --- | --- |
| カバレッジ | AC §2-4 の確認が diff 外。`docs/superpowers/` / `CLAUDE.md` / `.claude/skills/review-pr/` に旧用語残存の可能性 |
| 観点 | doc-only PR でも用語変更は他ファイルに波及する。SKILL.md §D 適用必須 / Step 5c 適用必須 |
| エッジケース | `requirements.md` 旧用語残存が markdownlint 違反を含む場合は §D CI 波及検証で摘出対象 |
| 優先度 | AC §3 / §4 確認不可: P1 / §D 全件確認: P1 |

**Step 5c 実施: 旧用語 literal 全件 sweep**

```bash
grep -rn 'Self-Test Report v1\|v1 必須項目\|v1 テンプレート' \
  docs/ CLAUDE.md .claude/skills/review-pr/
```

または新フィールドの追従確認:

```bash
grep -rn 'sweep_grep_commands\|step5c_completed\|sweep_hits_total' \
  docs/superpowers/ CLAUDE.md .claude/skills/review-pr/
```

**hits 分布 (シナリオ提供の hits 分布表より)**:

| ファイル | hits 数 | 残存パターン |
| --- | --- | --- |
| `docs/l2-workflow.md` | 0 | diff で修正済み |
| `docs/superpowers/specs/2026-05-08-lane-iv-b-group-g-design.md` | 3 | `Self-Test Report v1` / `step5c_completed 未定義` / `sweep_grep_commands` 未記載 |
| `docs/superpowers/plans/2026-05-08-lane-iv-b-group-g-implementation.md` | 2 | `v1 テンプレート参照` / `sweep_hits_total` 未定義 |
| `CLAUDE.md` | 2 | §PR 作成ルール内で `l2-workflow.md 各 §` 参照 — v2 フィールド未言及 |
| `.claude/skills/review-pr/eval/requirements.md` | 3 | `sweep 規約` 記述が旧仕様のまま (Step 5c 参照なし) |
| `.claude/skills/review-pr/SKILL.md` | 2 | §Step 5b 末尾に Step 5c 参照なし / Red flags 表に sweep flag 未追記 |
| **合計** | **12** | diff に含まれない残存 |

**全件リスト** (Step 5b に転記する):

| hit # | ファイル | 残存パターン | 内容 |
| --- | --- | --- | --- |
| 1 | `docs/superpowers/specs/...design.md` | `Self-Test Report v1` | v2 用語追従漏れ hit 1 |
| 2 | `docs/superpowers/specs/...design.md` | `step5c_completed 未定義` | v2 フィールド未記載 hit 2 |
| 3 | `docs/superpowers/specs/...design.md` | `sweep_grep_commands` 未記載 | v2 フィールド未記載 hit 3 |
| 4 | `docs/superpowers/plans/...implementation.md` | `v1 テンプレート参照` | v2 用語追従漏れ hit 4 |
| 5 | `docs/superpowers/plans/...implementation.md` | `sweep_hits_total` 未定義 | v2 フィールド未記載 hit 5 |
| 6 | `CLAUDE.md` | v2 フィールド未言及 (§PR 作成ルール) | `l2-workflow.md 各 §` 参照が v2 対応なし hit 6 |
| 7 | `CLAUDE.md` | v2 フィールド未言及 | 同上 hit 7 |
| 8 | `.claude/skills/review-pr/eval/requirements.md` | `sweep 規約` 旧仕様 | Step 5c 参照なし hit 8 |
| 9 | `.claude/skills/review-pr/eval/requirements.md` | Step 5c 参照なし | hit 9 |
| 10 | `.claude/skills/review-pr/eval/requirements.md` | Step 5c 参照なし | hit 10 |
| 11 | `.claude/skills/review-pr/SKILL.md` | §Step 5b 末尾 Step 5c 参照なし | hit 11 |
| 12 | `.claude/skills/review-pr/SKILL.md` | Red flags 表に sweep flag 未追記 | hit 12 |

**sweep 規約確認**: Step 5b トリアージ表には全 12 hits を転記する。「軽微な doc 修正だから一部対応で OK」「diff にない他ファイルは手動で順次反映で OK」は Red Flag (Step 5c §2-3 + SKILL.md §Red flags)。

**環境制約 §D: markdownlint 全件スキャン**

```bash
bash scripts/check-markdownlint.sh
```

シナリオ記載: `requirements.md` / `SKILL.md` への波及は CI が自動検知しない。旧用語残存が markdownlint 違反を含む可能性があるため、全 .md をスキャンして残存ファイルの markdownlint 状態を実測する必要がある。

---

## Step 5b: 摘出課題トリアージ (全 12 hits + 追加課題)

Step 5c sweep 規約に従い、grep hits 全 12 件を各行に列挙する。

| # | 摘出内容 | 出所 | 処置 | 根拠 |
| --- | --- | --- | --- | --- |
| 1 | `docs/superpowers/specs/...design.md` hit 1: `Self-Test Report v1` 旧用語残存 | 受け入れ条件 #3 / 5c grep hit 1 | (A) PR コメント | AC §3 直結。specs/ の v2 用語追従漏れ |
| 2 | `docs/superpowers/specs/...design.md` hit 2: `step5c_completed` 未定義 | 5c grep hit 2 | (A) PR コメント | v2 フィールドが spec に未反映。PR スコープに含まれる更新漏れ |
| 3 | `docs/superpowers/specs/...design.md` hit 3: `sweep_grep_commands` 未記載 | 5c grep hit 3 | (A) PR コメント | v2 フィールドが spec に未反映 |
| 4 | `docs/superpowers/plans/...implementation.md` hit 4: `v1 テンプレート参照` 旧用語残存 | 受け入れ条件 #3 / 5c grep hit 4 | (A) PR コメント | AC §3 直結。plans/ の v2 用語追従漏れ |
| 5 | `docs/superpowers/plans/...implementation.md` hit 5: `sweep_hits_total` 未定義 | 5c grep hit 5 | (A) PR コメント | v2 フィールドが plans に未反映 |
| 6 | `CLAUDE.md` hit 6: v2 フィールド未言及 (§PR 作成ルール) | 受け入れ条件 #4 / 5c grep hit 6 | (A) PR コメント | AC §4 直結。CLAUDE.md の v2 用語追従漏れ |
| 7 | `CLAUDE.md` hit 7: v2 フィールド未言及 (別箇所) | 受け入れ条件 #4 / 5c grep hit 7 | (A) PR コメント | AC §4 直結 |
| 8 | `.claude/skills/review-pr/eval/requirements.md` hit 8: `sweep 規約` 旧仕様 (Step 5c 参照なし) | 5c grep hit 8 | (A) PR コメント | 旧用語の残存。本 PR スコープに含まれる追従漏れ |
| 9 | `.claude/skills/review-pr/eval/requirements.md` hit 9: Step 5c 参照なし | 5c grep hit 9 | (A) PR コメント | 同上 |
| 10 | `.claude/skills/review-pr/eval/requirements.md` hit 10: Step 5c 参照なし | 5c grep hit 10 | (A) PR コメント | 同上 |
| 11 | `.claude/skills/review-pr/SKILL.md` hit 11: §Step 5b 末尾 Step 5c 参照なし | 5c grep hit 11 | (A) PR コメント | SKILL.md への v2 関連追従漏れ |
| 12 | `.claude/skills/review-pr/SKILL.md` hit 12: Red flags 表に sweep flag 未追記 | 5c grep hit 12 | (A) PR コメント | SKILL.md への v2 関連追従漏れ |
| 13 | markdownlint 全件スキャン未実施 (`requirements.md` / `SKILL.md` への波及が CI で自動検知されない) | §D CI 波及検証 | (A) PR コメント | `bash scripts/check-markdownlint.sh` 実行結果を PR に追記すること |

---

## Step 6: レビュー結果 (Review Round 1)

**ベース同期確認 (Step 2)**:

- 形式 (2.1): develop-0.2.0 (develop-x.x.x 形式 OK)
- base 最新化と直近マージ PR (2.2): 影響候補 PR なし相当
- 同期判定 (2.3): skip
- 並行 worktree PR (2.4): 検出ゼロ

**受け入れ条件チェック (逐条)**:

| # | 条件 | 実証 | 判定 |
| --- | --- | --- | --- |
| 1 | l2-workflow.md §Self-Test Report v2 化 | diff: v2 必須項目・チェックリスト追加 ○ | ○ |
| 2 | l2-workflow.md 内の全参照で v2 用語統一 | diff で一部確認。diff 外 0 hits (修正済み) | 部分的 |
| 3 | docs/superpowers/specs/ が v2 用語に追従 | diff 未含。grep sweep で 3 hits 残存確認 | × |
| 4 | CLAUDE.md が v2 用語に追従 | diff 未含。grep sweep で 2 hits 残存確認 | × |
| 5 | markdownlint check green | PR 本文: ローカル 0 errors (全 .md スキャン確認要) | 部分的 |

**ギャップ分析 (Step 5a — Step 5c sweep 規約適用)**:

- カバレッジ: 旧用語 literal が 5 ファイルに 12 hits 残存 (specs/ 3 + plans/ 2 + CLAUDE.md 2 + requirements.md 3 + SKILL.md 2)
- 観点: doc-only PR でも用語変更は他ファイルに波及する (Red Flag: 「doc だから sweep 不要」を排除)
- エッジケース: requirements.md / SKILL.md 旧用語が markdownlint 違反を含む可能性 (§D CI 波及)

**摘出課題トリアージ (Step 5b — Step 5c sweep 規約: 全 12 hits + markdownlint 確認)**:

grep コマンド (修正依頼本文に同梱):

```text
grep -rn 'v1 必須項目\|v1 テンプレート' docs/ CLAUDE.md .claude/skills/review-pr/
grep -rn 'sweep_grep_commands\|step5c_completed\|sweep_hits_total' docs/superpowers/ CLAUDE.md .claude/skills/review-pr/
```

| # | 摘出内容 | 出所 | 処置 | 根拠 |
| --- | --- | --- | --- | --- |
| 1-3 | docs/superpowers/specs/...design.md: v2 用語追従漏れ 3 hits | 5c hit 1-3 / AC §3 | (A) PR コメント | AC §3 直結 |
| 4-5 | docs/superpowers/plans/...implementation.md: v2 用語追従漏れ 2 hits | 5c hit 4-5 / AC §3 | (A) PR コメント | AC §3 直結 |
| 6-7 | CLAUDE.md: v2 フィールド未言及 2 hits | 5c hit 6-7 / AC §4 | (A) PR コメント | AC §4 直結 |
| 8-10 | requirements.md: Step 5c 参照なし 3 hits | 5c hit 8-10 | (A) PR コメント | 追従漏れ |
| 11-12 | SKILL.md: v2 関連追従漏れ 2 hits | 5c hit 11-12 | (A) PR コメント | 追従漏れ |
| 13 | markdownlint 全件スキャン未確認 (§D CI 波及) | §D | (A) PR コメント | bash scripts/check-markdownlint.sh 実行・結果 PR 追記 |

**検証推奨**:

- 自動 (CI): `bash scripts/check-markdownlint.sh` (全 .md スキャン)
- 手動検証: `grep -rn 'v1 必須項目' docs/ CLAUDE.md .claude/skills/review-pr/` で残存ゼロを確認

**判定**: 修正依頼 — AC §3 / §4 が grep sweep で 12 hits 残存。全件 PR 内修正を要求する。
「doc-only だから sweep 不要」は Red Flag — 本 PR でも Step 5c sweep は必須。LGTM 不可。

マージ後 issue クローズは `/close-issue 944` で実測再検証してから実施してください
(本セッションでは close を実行しません)。

---

## 要件チェックリスト評価 (シナリオ E3 — 改訂 SKILL.md Step 5c 適用)

| # | 要件 | 評価 | 根拠 |
| --- | --- | --- | --- |
| 1 | [critical] doc-only でも root cause (旧用語 literal の他ファイル残存) を Step 5 で識別している (「doc だから sweep 不要」と判定していない) | ○ | Step 5.1 で「root cause 識別: PR diff は l2-workflow.md のみで AC §3/§4 の他ファイル追従が確認不可」を識別。「doc-only 修正だから sweep 不要 = Red Flag」と明示。Step 5c 適用を宣言 |
| 2 | [critical] `grep -rn` 全件 sweep コマンドを Step 5a で提示している (5 ファイルに散在する 12 hits を全件捕捉) | ○ | Step 5a で `grep -rn 'Self-Test Report v1\|v1 必須項目\|v1 テンプレート' docs/ CLAUDE.md .claude/skills/review-pr/` および `grep -rn 'sweep_grep_commands\|step5c_completed\|sweep_hits_total' ...` の 2 コマンドを提示 |
| 3 | [critical] 12 hits を Step 5b トリアージ表に全件列挙している (`docs/superpowers/specs/` 3 + `docs/superpowers/plans/` 2 + `CLAUDE.md` 2 + `eval/requirements.md` 3 + `SKILL.md` 2) | ○ | Step 5b トリアージ表に hit 1-12 を個別列挙。ファイル・パターン・内容を明記 |
| 4 | [critical] 「軽微な doc 修正だから一部対応で OK」「diff にない他ファイルは手動で順次反映で OK」のような握り潰しを Red Flag として識別している | ○ | Step 5.1 末尾「doc-only 修正だから sweep 不要 = Red Flag (SKILL.md §Red flags 表参照)」を明示。Step 5b トリアージ表に「「doc-only だから sweep 不要」は Red Flag」と判定コメントを含めた |
| 5 | 環境制約 §D に従って `bash scripts/check-markdownlint.sh` で全 .md をスキャンし、残存ファイルの markdownlint 状態を実測している | ○ | Step 5a で「§D CI 波及検証: `bash scripts/check-markdownlint.sh` 実行が必要」と明示。Step 5b hit 13 として `(A) PR コメント` で「bash scripts/check-markdownlint.sh 実行・結果 PR 追記」を要求 |
| 6 | LGTM ではなく修正依頼を出している | ○ | Step 6 で「修正依頼: AC §3/§4 が grep sweep で 12 hits 残存」判定 |

## [critical] 達成率

**4 / 4** (○ 4 / [critical] 4 件中)

- 達成: 要件 #1 (doc-only でも root cause 識別 + Red Flag 明示) / #2 (grep コマンド 2 個提示) / #3 (12 hits 全件列挙) / #4 (握り潰し Red Flag 識別)

## 構造的欠陥 解消状況

Iteration 0 で識別された構造的欠陥:

1. **§D 適用の認識と grep 実行の間にギャップがある** → Step 5c 適用により解消。Step 5.1 で root cause 識別 → 「Step 5c 適用」を宣言 → Step 5a で grep コマンド提示 → Step 5b に 12 hits 全件転記のパイプラインが一貫して機能した。
2. **doc-only PR への sweep mandate が明文化されていない** → Step 5c (改訂 SKILL.md) により明文化。本 Iteration では「doc-only 修正だから sweep 不要 = Red Flag」と明示的に識別し、sweep を実施した。
3. **12 hits の特定が PR 作成者に委ねられる** → Step 5b に 12 hits を個別列挙し、修正依頼コメントに grep コマンドを引用したため、PR 作成者が一部対応のみで再提出するパターン (Round divergence) を防いだ。
4. **requirements.md / SKILL.md の旧用語残存が見落とされやすい** → grep sweep で全件捕捉 (hit 8-12)。eval 資料・SKILL.md も sweep 対象に含め、explicit な見落としを防いだ。
