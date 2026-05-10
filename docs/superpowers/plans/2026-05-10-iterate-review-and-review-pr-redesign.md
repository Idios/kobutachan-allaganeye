# `/iterate-review` skill 新規 + `/review-pr` 機能整理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PR 作成後の review-fix ループを `/iterate-review` 新規 skill で自動化し、`/review-pr` の per-finding コメント投稿と再レビューラウンド管理を `/iterate-review` 側に集約。両 skill を empirical-prompt-tuning + post-tuning skill boundary audit で抜け漏れ・冗長を構造的除去。

**Architecture:** 主セッション (orchestrator) が `/iterate-review <PR#>` を invoke (user 手動 or PR 作成 agent 自走) → 各 round で fresh subagent に `/review-pr` (subagent invocation mode) を dispatch → 構造化 findings (acceptance_criteria_status / findings_table / ambiguous_judgments / recommendation / meta) を return → 主セッションが `(A)` 修正 / `(B)`/`(C)` handoff / push / CI wait を実施 → Step 5b 表全ゼロまで繰返し → 収束時 1 PR コメントで summary 投稿。 `(A)` 強優先 + `(B)` 厳格 3 条件 AND + 握り潰し防止 validation (subagent return の全 finding 分類必須) で issue 数収束を構造的に担保。

**Tech Stack:**

- Markdown (`.claude/skills/<name>/SKILL.md` instructional skill)
- Markdown eval files (`.claude/skills/<name>/eval/{requirements,scenario_*,reports/*}.md`)
- `Agent` tool (general-purpose subagent) for `/review-pr` dispatch
- `gh` CLI (`gh pr view` / `gh pr edit` / `gh pr comment` / `gh pr checks --watch` / `gh issue comment`)
- HEREDOC + `--body-file -` (Windows + Git Bash UTF-8 対策、`feedback_gh_command_ja_heredoc.md`)
- 既存 skills: `/review-pr` / `/enforce-acceptance-criteria` / `/scope-guard` / `/create-task` / `/close-issue`

**spec 参照**: 全タスクで [`docs/superpowers/specs/2026-05-10-iterate-review-and-review-pr-redesign.md`](../specs/2026-05-10-iterate-review-and-review-pr-redesign.md) を参照。本 plan ではタスク単位の手順を示し、詳細仕様は spec の §章番号でリンクする。

---

## Phase A: `/review-pr` 改訂 + eval 更新

### Task 1: Pre-flight (Iron Law 6 base sync + 並行 PR)

**Files:** なし (`git` / `gh` CLI のみ)

- [ ] **Step 1: develop-0.2.0 を最新化 + 取り込み未済 commit 確認**

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline
```

Expected: 取り込み未済 commit list (空 or 数件)。`.claude/skills/review-pr/**` を touch する commit があれば Step 3 で merge。

- [ ] **Step 2: 並行 worktree PR の重複確認**

```bash
gh pr list --search ".claude/skills/review-pr" --state all --limit 10
gh pr list --state open --base develop-0.2.0 --json number,title,headRefName,files
```

Expected: 既存 PR が `.claude/skills/review-pr/` または `.claude/skills/iterate-review/` を扱っていない。重複あれば作業中止して Idios に AskUserQuestion で確認。

- [ ] **Step 3: 取り込み未済 commit が当 PR の touched files と交差すれば merge**

```bash
git log HEAD..origin/develop-0.2.0 --name-only | grep -E '\.claude/skills/(review-pr|iterate-review)|docs/l2-workflow\.md|CLAUDE\.md' || echo "no overlap"
git merge origin/develop-0.2.0 # overlap ありの場合のみ
```

Expected: overlap なし (echo "no overlap")。conflict あれば手動解決 + 各 SKILL.md / eval ファイル変更内容を見直し。

---

### Task 2: `/review-pr` SKILL.md - Step 6 改訂 (AskUserQuestion 削除)

**Files:**

- Modify: `.claude/skills/review-pr/SKILL.md` (Step 6 「レビュー結果報告」セクション)

spec §3.3 参照。

- [ ] **Step 1: 現状の Step 6 末尾の AskUserQuestion 4 択ブロックを特定**

`.claude/skills/review-pr/SKILL.md` line ~257-266 (現状) の `AskUserQuestion` で以下を提示する選択肢ブロック:

```text
- LGTM (摘出課題ゼロ): ...
- 修正依頼のみ: ...
- 修正依頼 + 派生 issue 起票: ...
- LGTM + 派生 issue 起票: ...
```

を読んで位置を確認。

- [ ] **Step 2: AskUserQuestion ブロックを削除し「報告 markdown 生成のみで完了」に変更**

Step 6 の節を以下の構造にする (テンプレート部分は維持):

```markdown
### 6. レビュー結果をユーザーに報告

Step 5b のトリアージ表を前提に、以下のテンプレート構造で**レビュー報告 markdown を生成して presenting する** (`AskUserQuestion` は呼ばない、PR コメント投稿もしない)。Step 7 / 8 へ自動進行する。

(レビュー報告テンプレート部分はそのまま維持)
```

「**重要**: 「課題はあるがスコープ外だから放置」の選択肢は存在しない。摘出課題は必ず表経由で (A)/(B)/(C) に振り分ける。」の文言は**維持**。

- [ ] **Step 3: 変更を verify (削除されたか + テンプレートが残っているか)**

```bash
grep -n "AskUserQuestion" .claude/skills/review-pr/SKILL.md | head
grep -n "レビュー報告テンプレート" .claude/skills/review-pr/SKILL.md
```

Expected: Step 6 配下から `AskUserQuestion` の言及が消えている (Step 2.3 / 2.4 / 5b の AskUserQuestion は subagent mode で skip されるが standalone では維持なのでそちらは残る)、レビュー報告テンプレートは残っている。

- [ ] **Step 4: コミット**

```bash
git add .claude/skills/review-pr/SKILL.md
git commit -m "refactor(review-pr): Step 6 の AskUserQuestion 4 択を削除 (報告 markdown 生成のみ)"
```

---

### Task 3: `/review-pr` SKILL.md - Step 7 整理 (per-finding comment 削除 + 推奨アクション提示)

**Files:**

- Modify: `.claude/skills/review-pr/SKILL.md` (Step 7 「ユーザー承認後のアクション」「修正依頼コメント投稿」セクション全体)

spec §3.4 参照。

- [ ] **Step 1: Step 7 を全面置換**

現状の Step 7 (「LGTM 承認」「修正依頼コメント投稿」サブ節含む)、line ~317-374 を以下に置換:

```markdown
### 7. 次のアクション提案 (PR コメント投稿は廃止)

本 skill は Step 6 のレビュー報告を user に提示するのみで、`gh pr comment` 等の **PR コメント投稿は一切行わない**。代わりに次のアクション提案を以下のテンプレートで user に提示する:

```markdown
## 次のアクション提案

判定: <LGTM / 修正依頼 / ブロッカー>

### 推奨フロー
- **(A) 修正依頼が残っている場合**: `/iterate-review $ARGUMENTS` で review-fix ループを起動し、最終 summary コメントを 1 個投稿してマージ準備まで自動化
- **(A) 課題ゼロかつ受け入れ条件 ✓**: ユーザーが `gh pr merge $ARGUMENTS --squash` で squash merge → 紐づく issue は `/close-issue <issue#>` でクローズ
- **発散・スコープ問題が疑われる場合**: scope-guard skill / 設計再検討
```

PR コメント投稿が必要な特殊ケース (例: 別レビュアーへ正式に依頼書を残したい) は **ユーザーが手動で行う**。skill が自動投稿することはない。

```

「補足: scope-guard 発動時の AskUserQuestion 投げ先」サブ節は**維持**。

- [ ] **Step 2: 旧サブ節「修正依頼コメント投稿」が完全削除されたか確認**

```bash
grep -n "修正依頼コメント投稿" .claude/skills/review-pr/SKILL.md
grep -n "gh pr comment" .claude/skills/review-pr/SKILL.md
```

Expected: 「修正依頼コメント投稿」section header が消えている。`gh pr comment` の登場は Step 8 の MERGED-state summary 任意投稿、または Red Flags 注意書きのみ (per-finding 投稿の指示は消えている)。

- [ ] **Step 3: コミット**

```bash
git add .claude/skills/review-pr/SKILL.md
git commit -m "refactor(review-pr): Step 7 per-finding comment 投稿を全廃 (推奨アクション提示のみ)"
```

---

### Task 4: `/review-pr` SKILL.md - Step 7a (再レビューラウンド管理) 削除

**Files:**

- Modify: `.claude/skills/review-pr/SKILL.md` (Step 7a 「再レビューラウンド管理 (Round 2+)」セクション全体)

spec §3.1 / §3.2 参照。Step 7a 全削除し、`/iterate-review` Step 3 に移管する旨の note のみ残す。

- [ ] **Step 1: Step 7a 全節を削除し、移管 note に置換**

現状の `### 7a. 再レビューラウンド管理 (Round 2+)` 節 (line ~376-400 程度) を以下に置換:

```markdown
### 7a. 再レビューラウンド管理 (`/iterate-review` に移管)

Round 2+ の再レビュー管理 (収束判定 / 発散判定 / 打ち切り判断) は `/iterate-review` skill (新規) に移管した。本 skill は単一 round の review エンジンとしてのみ動作する。

複数 round 自動実行が必要な場合は `/iterate-review <PR#>` を invoke すること。
```

- [ ] **Step 2: 削除確認**

```bash
grep -n "Round 1: 初回レビュー" .claude/skills/review-pr/SKILL.md
grep -n "発散判定" .claude/skills/review-pr/SKILL.md
grep -n "打ち切り判断" .claude/skills/review-pr/SKILL.md
```

Expected: 旧 Step 7a の本文 (Round の数え方 / 収束判定 / 発散判定 / 打ち切り判断) が削除されている。「`/iterate-review` skill (新規) に移管」と書かれた短い note のみ残る。

- [ ] **Step 3: コミット**

```bash
git add .claude/skills/review-pr/SKILL.md
git commit -m "refactor(review-pr): Step 7a 再レビューラウンド管理を /iterate-review に移管 (note のみ残す)"
```

---

### Task 5: `/review-pr` SKILL.md - Step 8 (MERGED state 限定にスリム化)

**Files:**

- Modify: `.claude/skills/review-pr/SKILL.md` (Step 8 「マージ後のハンドオフ」セクション全体)

spec §3.5 参照。

- [ ] **Step 1: 旧 Step 8 を spec §3.5 に従い置換**

現状の `### 8. マージ後のハンドオフ` 節を以下に置換:

```markdown
### 8. マージ後の close-issue handoff (PR が MERGED 状態の場合)

PR がマージ済みで本 skill が呼ばれた場合 (= 確認用の事後レビュー) のみ意味がある節。マージ前の課題ハンドオフは `/iterate-review` Step 5 (LGTM 候補通知) で吸収する。

#### 手順

1. 受け入れ条件最終検証 (Step 3) を実施
2. 紐づく issue 番号を抽出 (`gh pr view <PR#> --json closingIssuesReferences,body` + 本文 `Refs #N` 抽出)
3. ユーザーに `/close-issue <番号>` を案内 (本 skill では実行しない、Iron Law 4)
4. 検証結果を summary コメント (1 個) として PR に投稿することを user に提案 (`AskUserQuestion`「投稿する / 投稿しない」、フォーマットは `/iterate-review` Step 4 の summary template と同一 = `docs/superpowers/specs/2026-05-10-iterate-review-and-review-pr-redesign.md` §4.2 参照)

#### マージ前 (`OPEN` state) で本 skill が呼ばれた場合

通常フロー (Step 1-7) のみ実施し、本 Step 8 は skip する。残課題対応は `/iterate-review` 推奨を Step 7 で提示済み。

#### 孤立 PR (issue 紐付けなし) の場合

`/close-issue` 案内は省略可 (issue がないため)。Step 7 で提示した「次のアクション」に従う。
```

- [ ] **Step 2: 既存 Step 8 のサブ節 (孤立 PR の (B)/(C) 残処理確認 / マージ済みフォールバック) が削除/集約されたか確認**

```bash
grep -n "PR に紐づく issue がない場合" .claude/skills/review-pr/SKILL.md
grep -n "マージ済み状態で本 skill が呼ばれた場合のフォールバック" .claude/skills/review-pr/SKILL.md
grep -n "PR がマージ済みで本 skill が呼ばれた場合" .claude/skills/review-pr/SKILL.md
```

Expected: 旧サブ節が削除され、新しい簡略化された節構造 (MERGED state 主体 + 孤立 PR は省略可) に置換されている。

- [ ] **Step 3: コミット**

```bash
git add .claude/skills/review-pr/SKILL.md
git commit -m "refactor(review-pr): Step 8 を MERGED state 限定にスリム化 + summary 投稿任意化"
```

---

### Task 6: `/review-pr` SKILL.md - §G subagent invocation mode 新設

**Files:**

- Modify: `.claude/skills/review-pr/SKILL.md` (§F の直後に §G を追加)

spec §3.6 参照。§G.1 / §G.2 / §G.2.1 / §G.3 の 4 サブ節を含む。

- [ ] **Step 1: §F 直後の位置を特定**

```bash
grep -n "^### §F\." .claude/skills/review-pr/SKILL.md
grep -n "^## 呼び出し例" .claude/skills/review-pr/SKILL.md
```

Expected: §F セクションの末尾と、その直後の `## 呼び出し例` の位置が出る。§F 末尾と `## 呼び出し例` の間に §G を挿入する。

- [ ] **Step 2: §G 全体を挿入**

`§F` の直後に以下を追加:

```markdown
### §G. Subagent invocation mode

`/iterate-review` から subagent として呼ばれた場合の動作契約。

#### G.1 Mode 検出

呼び出し prompt に以下のマーカーが含まれている場合 subagent mode:

`__ITERATE_REVIEW_SUBAGENT_MODE__`

(`/iterate-review` Step 2.1 の prompt template に固定文字列として埋め込む)

#### G.2 動作差分

| 観点 | Standalone mode | Subagent mode |
| --- | --- | --- |
| Step 2.3 base sync AskUserQuestion | 通常通り | skip: 影響候補ありなら findings に「需 user 判断: base regression」と記載 |
| Step 2.4 並行 PR AskUserQuestion | 通常通り | skip: 検出されたら findings に記載 |
| Step 5b 摘出 AskUserQuestion (個別 (A)/(B)/(C)) | 通常通り | skip: skill 内基準で auto 分類、ambiguous case のみ findings の `ambiguous_judgments` に明示 |
| Step 6 報告 | conversation 内 presenting | final message に markdown で含める |
| Step 7 次のアクション提案 | user に提示 | skip: orchestrator (`/iterate-review`) が代行 |
| Step 8 マージ後 handoff | 必要なら実行 | skip |
| `gh pr comment` 投稿 | 一切しない (本 skill 改訂後) | 一切しない (subagent mode でも禁止) |

#### G.2.1 Subagent mode 自動分類規約 ((A) 強優先 + 握り潰し禁止)

Subagent mode で Step 5b の (A)/(B)/(C) 自動分類を行う際の厳格規約:

1. **すべての finding に必ず分類を付与する**: 観察コメントのみ・スコープ対象外と自己判断・軽微だから無視 は **すべて NG** (orchestrator 側 parse error として再 dispatch される)
2. **default は (A)**: 「指摘は原則すべて PR 内対応」を継承。CI failure / latent type error / 隣接ファイル lint 違反 / 古い API 残存 / 古い doc 記述 / 環境起因の問題 等は全部 (A)
3. **(B) は厳格 3 条件 AND**: `別領域・別機能` AND `1 セッション超の独立設計が必要` AND `本 PR 同梱で受け入れ条件検証が破綻` の **すべて満たす場合のみ** (B)。1 つでも欠ければ (A)。**サイズ単独 / scope-out 単独 / 受け入れ条件直結性単独では (B) 化不可**
4. **(C) は重複起票回避 trigger のみ**: 同テーマの既存 issue が存在する場合のみ。「新規 issue を作るべきだが既存に書いた方が綺麗」は不可
5. **判定に迷う finding**: `(A)` を default として置き、`ambiguous_judgments` セクションに該当 finding を記載 (orchestrator 側で user gate)
6. **rationale 列に判定根拠を必ず記載**: (B) を選ぶ場合は 3 条件 AND 該当根拠、(C) を選ぶ場合は既存 issue 番号、(A) は省略可

#### G.3 戻り値構造 (subagent → orchestrator)

final message に以下のセクションを順序固定で含める:

1. `## acceptance_criteria_status` (各条件 ✓/×/部分的 + evidence)
2. `## findings_table` (Step 5b トリアージ表 markdown、各行に分類必須)
3. `## ambiguous_judgments` (auto 判断できなかった点。空でもセクション自体は必須記載)
4. `## recommendation` (LGTM / fix-required / divergent)
5. `## meta` (mergeStateStatus / 並行 PR 状態 / CI 状態。round 番号は `/iterate-review` 側管理のため不要)
```

- [ ] **Step 3: §G が追加されたか確認**

```bash
grep -n "^### §G\." .claude/skills/review-pr/SKILL.md
grep -n "__ITERATE_REVIEW_SUBAGENT_MODE__" .claude/skills/review-pr/SKILL.md
grep -n "G.2.1 Subagent mode 自動分類規約" .claude/skills/review-pr/SKILL.md
```

Expected: §G / マーカー文字列 / G.2.1 規約が存在する。

- [ ] **Step 4: コミット**

```bash
git add .claude/skills/review-pr/SKILL.md
git commit -m "feat(review-pr): §G Subagent invocation mode 新設 ((A) 強優先 + 握り潰し禁止規約 含む)"
```

---

### Task 7: `/review-pr` SKILL.md - Red Flags 表整理 + 削除確認

**Files:**

- Modify: `.claude/skills/review-pr/SKILL.md` (Red Flags 表)

spec §3.8 参照。

- [ ] **Step 1: 旧 Red Flag「PR ブランチを checkout して自分で修正した方が速い」を削除**

`Red flags (レビュー中に浮かんだら STOP)` 表の行から「PR ブランチを checkout して自分で修正した方が速い」を削除 (本 skill 改訂で `/iterate-review` 経由標準フローに統一されたため)。

- [ ] **Step 2: 新規 Red Flag 2 行を追加**

同表の末尾に以下 2 行を追加:

```markdown
| 「standalone mode で findings を PR コメントで投稿しよう」 | 本 skill は comment 投稿しない契約 (改訂ルール)。投稿が必要な場合のみ user が手動で行う |
| 「subagent mode で AskUserQuestion を呼ぼう」 | `/iterate-review` には届かない。findings の `ambiguous_judgments` に記載するのが正しい (§G.3) |
```

- [ ] **Step 3: 確認**

```bash
grep -n "PR ブランチを checkout して自分で修正" .claude/skills/review-pr/SKILL.md
grep -n "standalone mode で findings を PR コメントで投稿" .claude/skills/review-pr/SKILL.md
grep -n "subagent mode で AskUserQuestion を呼ぼう" .claude/skills/review-pr/SKILL.md
```

Expected: 第 1 grep 結果なし (削除済み)。第 2/3 は存在する (新規追加済み)。

- [ ] **Step 4: コミット**

```bash
git add .claude/skills/review-pr/SKILL.md
git commit -m "refactor(review-pr): Red Flags 表に subagent mode 関連を追加 + 旧 checkout-and-fix 行を削除"
```

---

### Task 8: `/review-pr` eval - 既存 scenario 期待 output 更新

**Files:**

- Modify: `.claude/skills/review-pr/eval/scenario_a_central.md`
- Modify: `.claude/skills/review-pr/eval/scenario_b_bundled.md`
- Modify: `.claude/skills/review-pr/eval/scenario_c_isolated.md`
- Modify: `.claude/skills/review-pr/eval/scenario_d_step8_handoff.md`
- Modify: `.claude/skills/review-pr/eval/scenario_e_sweep_central.md`
- Modify: `.claude/skills/review-pr/eval/scenario_e_sweep_edge_doc_only.md`
- Modify: `.claude/skills/review-pr/eval/scenario_e_sweep_edge_mixed.md`

spec §5.3「既存ファイル更新」参照。

- [ ] **Step 1: scenario_a_central.md の期待 output を更新**

Read `.claude/skills/review-pr/eval/scenario_a_central.md`。期待 output セクション内で以下を更新:

- 「PR コメントで修正依頼を投稿」「per-finding comment」のような期待を **削除**
- 代わりに「Step 6 のレビュー報告 markdown を生成」「Step 7 で次のアクション提案を user に提示」「`/iterate-review` 推奨を含める」を **追記**

- [ ] **Step 2: scenario_b_bundled.md 同様に更新**

per-finding comment 投稿期待を削除し、報告 markdown 生成 + 推奨フロー提示に置換。

- [ ] **Step 3: scenario_c_isolated.md 同様に更新**

孤立 PR の §A fallback 適用挙動は維持しつつ、comment 投稿期待を削除。Step 8 が「孤立 PR では `/close-issue` 案内省略可」を反映。

- [ ] **Step 4: scenario_d_step8_handoff.md を MERGED state 限定にする**

PR が MERGED 状態 (= 事後レビュー) のシナリオに変更。期待挙動:

- Step 1-7 通常通り (Step 7 は推奨アクション提示)
- Step 8: 受け入れ条件再検証 + `/close-issue` 案内 + summary コメント投稿の AskUserQuestion (任意) を提示
- `gh pr comment` の per-finding 投稿は皆無

- [ ] **Step 5: scenario_e_sweep_central.md / scenario_e_sweep_edge_doc_only.md / scenario_e_sweep_edge_mixed.md を更新**

Step 5c 同種パターン全件 sweep の挙動 (grep 全件 + トリアージ表転記 + 修正依頼本文に grep 同梱) を維持しつつ、「修正依頼本文」を「報告 markdown 内のトリアージ表」に置換。`gh pr comment` 投稿期待は削除。

- [ ] **Step 6: 全 scenario の期待出力に「per-finding comment 投稿しない」「報告 markdown 生成のみ」が反映されているか確認**

```bash
grep -l "gh pr comment" .claude/skills/review-pr/eval/scenario_*.md
grep -l "報告 markdown" .claude/skills/review-pr/eval/scenario_*.md
```

Expected: 第 1 grep は MERGED-state Step 8 任意投稿の言及、または Red Flag 注意書きのみ。第 2 grep は全 scenario で hit する。

- [ ] **Step 7: コミット**

```bash
git add .claude/skills/review-pr/eval/scenario_*.md
git commit -m "test(review-pr): 既存 5 scenario の期待 output を comment 廃止 + 報告 markdown 生成に更新"
```

---

### Task 9: `/review-pr` eval - scenario_f_subagent_mode.md 新規追加

**Files:**

- Create: `.claude/skills/review-pr/eval/scenario_f_subagent_mode.md`

spec §5.3「新規追加」参照。

- [ ] **Step 1: 新規 scenario ファイルを作成**

以下の内容で新規作成:

````markdown
# シナリオ F: Subagent invocation mode (`/iterate-review` 連携)

参考事例: `/iterate-review` Round 1 の dispatch シミュレーション

## 紐づく issue (mock)

シナリオ A の #901 を流用 (音声昇格条件に WR 検出を追加)。

---

## モック PR (mock)

シナリオ A の #902 を流用 (feat(audio): WR 検出を音声昇格 (B) 条件として追加)。

---

## 入力

`/iterate-review` 主セッションが Agent tool で本 skill を subagent dispatch する prompt:

````text
__ITERATE_REVIEW_SUBAGENT_MODE__

PR #902 を review してください。`/review-pr` skill を invoke しますが、以下の特例を必ず適用してください:

1. Step 6 / Step 7 の AskUserQuestion / `gh pr comment` 投稿 を SKIP
2. Step 5b トリアージ表を markdown 表形式で final message に含める
3. 以下の deferred topics は findings から exclude:
   (なし)
4. PR body の `<!-- iterate-review:deferred:start --> ... <!-- iterate-review:deferred:end -->` ブロック内 topics も exclude
5. Step 3 の受け入れ条件逐条検証結果 (`/enforce-acceptance-criteria`) も final message に含める
6. (A) 強優先方針 + 握り潰し禁止 (G.2.1 規約 適用)
7. final message は以下の構造で return:
   ## acceptance_criteria_status / ## findings_table / ## ambiguous_judgments / ## recommendation / ## meta
````

---

## 期待 output

### G.1 Mode 検出

- prompt 内の `__ITERATE_REVIEW_SUBAGENT_MODE__` マーカーを検出
- subagent mode に切り替え

### G.2 動作差分

- Step 2.3 / 2.4 の AskUserQuestion を **skip** (`gh pr view`/`gh pr list` での確認のみ実施)
- Step 5b の (A)/(B)/(C) 個別振り分け AskUserQuestion を **skip**、§G.2.1 規約に従って自動分類
- Step 6 報告を final message に markdown で含める (conversation 内 presenting でなく)
- Step 7 / Step 8 を **skip** (orchestrator 代行)
- `gh pr comment` 呼び出し **皆無**

### G.2.1 自動分類規約適用

- 全 finding に分類 (A) / (B) / (C) / ambiguous のいずれかを付与 (なしは禁止)
- (A) を default、`関数リネーム他箇所影響調査痕跡欠如` 等は (A) に分類
- (B) は 3 条件 AND を rationale 列で根拠示し
- 「無視」「観察のみ」「対象外」キーワードを含む行は出力しない

### G.3 戻り値構造

- 5 セクション順序固定: acceptance_criteria_status / findings_table / ambiguous_judgments / recommendation / meta
- `ambiguous_judgments` セクションは空でも必ず記載
- meta に mergeStateStatus / 並行 PR 状態 / CI 状態を含める

---

## 不明瞭点 (失敗時に記入)

(失敗した [critical] 項目を 1 行で記録)

---

## [critical] 項目

1. **[critical]** prompt 内の `__ITERATE_REVIEW_SUBAGENT_MODE__` マーカーを検出して subagent mode に切替できる
2. **[critical]** Step 2.3 / 2.4 / 5b / 6 / 7 / 8 の AskUserQuestion / `gh pr comment` を一切呼ばない
3. **[critical]** final message に 5 セクションが順序固定で含まれる
4. **[critical]** §G.2.1 規約に従い全 finding に分類が付与される (未分類なし)
5. **[critical]** (A) 強優先方針が反映され、scope-out 単独は (A)、3 条件 AND 満たすときのみ (B)
6. **[critical]** ambiguous_judgments セクションが空でも必ず記載される
7. Step 3 受け入れ条件逐条検証 (`/enforce-acceptance-criteria` 経由) は subagent mode でも実行される
8. deferred-list に含まれた topic は findings から除外される

````

- [ ] **Step 2: ファイルが正しく作成されたか確認**

```bash
ls -la .claude/skills/review-pr/eval/scenario_f_subagent_mode.md
grep -n "\\[critical\\]" .claude/skills/review-pr/eval/scenario_f_subagent_mode.md | wc -l
```

Expected: ファイル存在、`[critical]` 項目が 6 つある (上記 1-6)。

- [ ] **Step 3: コミット**

```bash
git add .claude/skills/review-pr/eval/scenario_f_subagent_mode.md
git commit -m "test(review-pr): scenario_f_subagent_mode.md 新規追加 (G.1-G.3 + 自動分類規約検証)"
```

---

### Task 10: `/review-pr` eval - requirements.md 更新

**Files:**

- Modify: `.claude/skills/review-pr/eval/requirements.md`

spec §5.3「既存ファイル更新」参照。

- [ ] **Step 1: 旧項目 (Step 6 AskUserQuestion / Step 7 comment 投稿関連) に削除マークを付ける**

該当行を strikethrough (`~~...~~`) または「(削除済み: 改訂後不要)」注記で marked-out。完全削除でなく履歴を残す形で。

- [ ] **Step 2: 新項目 (Step 6 改訂 / Step 7 廃止 / Step 8 MERGED 限定 / §G subagent mode) を追加**

シナリオ F 用の項目セクションを追加:

```markdown
## シナリオ F (subagent mode): モック /iterate-review からの dispatch

1. **[critical]** `__ITERATE_REVIEW_SUBAGENT_MODE__` マーカーを検出して subagent mode に切り替える
2. **[critical]** Step 2.3 / 2.4 / 5b / 6 / 7 / 8 の AskUserQuestion を全 skip する
3. **[critical]** `gh pr comment` を一切呼ばない
4. **[critical]** final message に 5 セクション (acceptance_criteria_status / findings_table / ambiguous_judgments / recommendation / meta) を順序固定で含める
5. **[critical]** §G.2.1 自動分類規約: 全 finding に (A)/(B)/(C)/ambiguous のいずれか分類が付与される (未分類なし)
6. **[critical]** (A) 強優先方針: CI failure / latent issue / 隣接 lint 違反 等は (A)
7. **[critical]** (B) 厳格 3 条件 AND: 1 条件のみは (A) に再分類
8. ambiguous_judgments セクションは空でも必ず記載
```

また、シナリオ A-E の項目に「Step 6 でレビュー報告 markdown 生成 (AskUserQuestion 4 択は呼ばない)」「Step 7 で `gh pr comment` を呼ばない (推奨アクション提示のみ)」を [critical] として追記。

- [ ] **Step 3: 整合性確認**

```bash
grep -c "\\[critical\\]" .claude/skills/review-pr/eval/requirements.md
grep -n "シナリオ F" .claude/skills/review-pr/eval/requirements.md
grep -n "subagent mode" .claude/skills/review-pr/eval/requirements.md
```

Expected: [critical] 項目総数が増えている (旧 + 新)。シナリオ F 節と subagent mode 言及あり。

- [ ] **Step 4: コミット**

```bash
git add .claude/skills/review-pr/eval/requirements.md
git commit -m "test(review-pr): requirements.md 更新 (シナリオ F + 改訂項目 反映)"
```

---

## Phase B: `/iterate-review` SKILL.md 初版 + eval

### Task 11: `/iterate-review` skill ディレクトリ + frontmatter + 概要

**Files:**

- Create: `.claude/skills/iterate-review/SKILL.md`

spec §2.1 参照。

- [ ] **Step 1: ディレクトリ作成**

```bash
mkdir -p .claude/skills/iterate-review/eval/reports
```

- [ ] **Step 2: SKILL.md 初版に frontmatter + 概要を書く**

新規作成:

````markdown
---
name: iterate-review
description: PR 作成後の review-fix ループを subagent dispatch で自動化する。`/review-pr` を fresh subagent で実行し findings を構造化 return させ、主セッションが (A) 修正 / (B)(C) handoff / push / CI wait を行い、Step 5b 表が全ゼロまたは Round 5 / 発散検知まで繰り返す。収束時は summary コメント 1 個を投稿。`/review-pr` の per-finding comment 投稿は本 skill が代替する形で廃止する。
user-invocable: true
argument-hint: <PR番号>
---

PR 作成後の review → fix → review ループを自動化する。指定された PR をレビューと修正のループで収束させ、最終的に summary コメントを投稿する。

## 起動経路 (2 系統)

- **user 手動**: `/iterate-review <PR#>` を Idios が直接 invoke
- **agent 自動**: PR 作成セッション (= 実装した主セッション) が PR 作成完了直後に `/iterate-review <PR#>` を skill として自走呼出。Iron Law 6 Pre-flight 通過後に呼ぶ前提

## 主要フロー (overview)

1. Step 0: Pre-flight (PR open / base sync / 並行 worktree PR)
2. Step 1: ループ初期化 (Round=1, handoff_state=[], findings_history={}, divergence_counter=0)
3. Step 2: Round N 実行 (subagent dispatch → parse → AskUserQuestion → fix/handoff → push → CI wait)
4. Step 3: 判定 (収束 / 発散 / 打ち切り)
5. Step 4: Final summary comment (HEREDOC で投稿、AskUserQuestion 3 択で承認)
6. Step 5: LGTM 候補通知 (user merge → /close-issue handoff)

詳細仕様: [docs/superpowers/specs/2026-05-10-iterate-review-and-review-pr-redesign.md](../../docs/superpowers/specs/2026-05-10-iterate-review-and-review-pr-redesign.md)

````

- [ ] **Step 3: 作成確認**

```bash
ls -la .claude/skills/iterate-review/SKILL.md
head -20 .claude/skills/iterate-review/SKILL.md
```

Expected: ファイル存在、frontmatter (`name: iterate-review`、`user-invocable: true`) が見える。

- [ ] **Step 4: コミット**

```bash
git add .claude/skills/iterate-review/SKILL.md
git commit -m "feat(iterate-review): skill ディレクトリ + frontmatter + 概要 (初版 step 1)"
```

---

### Task 12: `/iterate-review` SKILL.md - Step 0 Pre-flight + Step 1 ループ初期化

**Files:**

- Modify: `.claude/skills/iterate-review/SKILL.md`

spec §2.3 / §2.4 参照。

- [ ] **Step 1: SKILL.md 末尾に Step 0 / Step 1 を追加**

```markdown
## 手順

### Step 0: Pre-flight

PR の状態を確認し、ループ可能か判定する。

```bash
gh pr view $ARGUMENTS --json state,isDraft,headRefName,baseRefName,closingIssuesReferences
```

判定:

- `state == CLOSED` または `state == MERGED` → 「ループ対象外」エラー終了
- `isDraft == true` → AskUserQuestion 3 択 (draft でも進める / draft 解除を待つ / abort)
- それ以外 (state == OPEN + isDraft == false) → Step 1 へ

#### Base sync + 並行 PR 確認

base 最新化 + 直近マージ PR + 並行 worktree PR 重複確認は `/review-pr` Step 2 を踏襲。本 skill では `/review-pr` Step 2 へリンクし、subagent dispatch (Step 2.1) 内で実行されることに依拠して再掲しない。Pre-flight 段階では `gh pr view` の取得のみで十分。

### Step 1: ループ初期化

会話 context 内で以下を保持:

- `Round = 1`
- `handoff_state = []` (要素: `{topic, classification, issue_number, round}`)
- `findings_history = {}` (key: round 番号, value: Step 5b 表)
- `divergence_counter = 0`

```

- [ ] **Step 2: 確認**

```bash
grep -n "^### Step 0" .claude/skills/iterate-review/SKILL.md
grep -n "^### Step 1" .claude/skills/iterate-review/SKILL.md
```

Expected: 両 Step ヘッダが存在。

- [ ] **Step 3: コミット**

```bash
git add .claude/skills/iterate-review/SKILL.md
git commit -m "feat(iterate-review): Step 0 Pre-flight + Step 1 ループ初期化を追加"
```

---

### Task 13: `/iterate-review` SKILL.md - Step 2.1 Subagent dispatch (prompt template)

**Files:**

- Modify: `.claude/skills/iterate-review/SKILL.md`

spec §2.5 Step 2.1 参照。subagent prompt template (固定文字列) を含む。

- [ ] **Step 1: SKILL.md 末尾に Step 2.1 を追加**

```markdown
### Step 2: Round N 実行

#### Step 2.1 Subagent dispatch

`Agent` tool (subagent_type: `general-purpose`) で fresh subagent を spawn。**毎ラウンド新しい subagent** を起動 (context 汚染回避)。

prompt template (固定):

````text
__ITERATE_REVIEW_SUBAGENT_MODE__

PR #<N> を review してください。`/review-pr` skill を invoke しますが、以下の特例を必ず適用してください:

1. Step 6 / Step 7 の AskUserQuestion / `gh pr comment` 投稿 を SKIP
2. Step 5b トリアージ表を markdown 表形式で final message に含める
3. 以下の deferred topics は findings から exclude:
   <handoff_state を箇条書き、空なら "(なし)">
4. PR body の `<!-- iterate-review:deferred:start --> ... <!-- iterate-review:deferred:end -->` ブロック内 topics も exclude
5. Step 3 の受け入れ条件逐条検証結果 (`/enforce-acceptance-criteria`) も final message に含める
6. **(A) 強優先方針 + 握り潰し禁止**:
   - **すべての finding に必ず分類 (A) / (B) / (C) / ambiguous のいずれかを付与**
   - **(A) を最優先**: CI failure / latent type error / 隣接ファイル lint 違反 等は全部 (A)
   - **(B) は厳格 3 条件 AND 必須**: `別領域・別機能` AND `1 セッション超の独立設計が必要` AND `本 PR 同梱で受け入れ条件検証が破綻`
   - **(C) は同テーマ既存 issue が存在する場合のみ**
   - 判定に迷う finding は `(A)` を default に置き、ambiguous_judgments に記載
7. final message は以下の構造で return:

   ```markdown
   ## acceptance_criteria_status
   | # | 条件 | 実証 | 判定 |

   ## findings_table
   | # | 摘出内容 | 出所 | 処置 | 根拠 |

   ## ambiguous_judgments
   - <subagent が auto 判断できなかった点。空でもセクション自体は必須記載>

   ## recommendation
   <LGTM / fix-required / divergent>

   ## meta
   - mergeStateStatus: <CLEAN/BEHIND/...>
   - 並行 PR: <検出ゼロ / [#X handled]>
   - CI status: <green/failing/pending>
   ```

````

`<N>` には PR 番号 ($ARGUMENTS) を埋める。`<handoff_state を箇条書き>` には Step 1 で初期化した `handoff_state` の内容 (空なら "(なし)") を埋める。
```

- [ ] **Step 2: 確認**

```bash
grep -n "Step 2.1 Subagent dispatch" .claude/skills/iterate-review/SKILL.md
grep -n "__ITERATE_REVIEW_SUBAGENT_MODE__" .claude/skills/iterate-review/SKILL.md
grep -n "(A) 強優先方針" .claude/skills/iterate-review/SKILL.md
```

Expected: 3 件すべて hit。

- [ ] **Step 3: コミット**

```bash
git add .claude/skills/iterate-review/SKILL.md
git commit -m "feat(iterate-review): Step 2.1 Subagent dispatch (prompt template + (A) 強優先規約)"
```

---

### Task 14: `/iterate-review` SKILL.md - Step 2.2 Findings parse + 握り潰し防止 validation

**Files:**

- Modify: `.claude/skills/iterate-review/SKILL.md`

spec §2.5 Step 2.2 参照。

- [ ] **Step 1: SKILL.md 末尾に Step 2.2 を追加**

```markdown
#### Step 2.2 Findings parse + 握り潰し防止 validation

Agent tool の戻り値 markdown から `## findings_table` セクションの表行を抽出。各行を `{round, n, finding, source, classification, rationale}` として `findings_history[round]` に蓄積。

**抽出時の必須 validation (握り潰し防止)**:

1. **全 finding に classification がある**: 各行の処置列が `(A)` / `(B)` / `(C)` / `ambiguous` のいずれか。空欄 / 「観察のみ」 / 「対象外」等は **parse error**
2. **(B) 主張行には trigger 根拠列がある**: rationale 列に「別領域・別機能 AND 1 セッション超 AND 受け入れ条件検証破綻」3 条件への該当言及があるか。1 条件のみの (B) は **parse error** (= subagent が誤分類)
3. **subagent return に「無視」「観察のみ」「スコープ対象外」のキーワードを単独で含む行がない**: 文字列 grep で検出、ヒットしたら **parse error**
4. **`ambiguous_judgments` セクションが存在する** (空でもセクション自体は必須): 不在は parse error

**parse error 時の対処**:

- 1 度目: 主セッションが subagent に対して具体的に欠陥を伝えて再 dispatch (Agent tool 再実行)。具体例: 「Step 5b 表 5 行目の (B) は trigger 根拠が `スコープ外` のみで 3 条件 AND 不成立。(A) に再分類して return せよ」
- 2 度目: AskUserQuestion で user に「subagent が分類規約を満たさない findings を返している。手動でトリアージするか abort するか」を提示
```

- [ ] **Step 2: 確認**

```bash
grep -n "Step 2.2 Findings parse" .claude/skills/iterate-review/SKILL.md
grep -n "握り潰し防止" .claude/skills/iterate-review/SKILL.md
grep -n "parse error" .claude/skills/iterate-review/SKILL.md
```

Expected: 3 件すべて hit。

- [ ] **Step 3: コミット**

```bash
git add .claude/skills/iterate-review/SKILL.md
git commit -m "feat(iterate-review): Step 2.2 Findings parse + 握り潰し防止 validation 4 項目"
```

---

### Task 15: `/iterate-review` SKILL.md - Step 2.3 Round summary AskUserQuestion

**Files:**

- Modify: `.claude/skills/iterate-review/SKILL.md`

spec §2.5 Step 2.3 参照。

- [ ] **Step 1: SKILL.md 末尾に Step 2.3 を追加**

```markdown
#### Step 2.3 Round summary AskUserQuestion (1 round 1 回のみ)

Round N の集計表示 + AskUserQuestion 2 択。Round 開始時に user 介入を集約する唯一の gate。

提示内容:

````text
Round N findings:
- (A): <件数>
- (B): <件数>
- (C): <件数>
- 受け入れ条件 (Step 3): <全 ✓ / 部分 / 全 ×>
- ambiguous_judgments: <件数> (詳細は別途展開)

選択:
- (i) proceed (本 round の findings を処理) (Recommended、ambiguous なし時)
- (ii) abort (loop 中断、現状で /create-task など手作業に切替)
````

`ambiguous_judgments` がある場合、追加 AskUserQuestion でユーザー判断を仰ぐ。1 AskUserQuestion call は最大 4 questions まで束ねられる仕様 (= AskUserQuestion tool 上限) を活用し、5 件以上は複数 call に分割。1 round あたりの AskUserQuestion 呼び出し総数は「Round summary 1 + ambiguous_judgments の必要分」を上限とする。

```

- [ ] **Step 2: 確認**

```bash
grep -n "Step 2.3 Round summary" .claude/skills/iterate-review/SKILL.md
grep -n "1 round 1 回" .claude/skills/iterate-review/SKILL.md
```

Expected: hit。

- [ ] **Step 3: コミット**

```bash
git add .claude/skills/iterate-review/SKILL.md
git commit -m "feat(iterate-review): Step 2.3 Round summary AskUserQuestion (2 択 + ambiguous_judgments 拡張)"
```

---

### Task 16: `/iterate-review` SKILL.md - Step 2.4 (A) findings 修正 (1 commit/round)

**Files:**

- Modify: `.claude/skills/iterate-review/SKILL.md`

spec §2.5 Step 2.4 参照。

- [ ] **Step 1: SKILL.md 末尾に Step 2.4 を追加**

```markdown
#### Step 2.4 (A) findings 修正

各 (A) に対し主セッションが:

1. 該当 path:line を Read で内容確認
2. Edit で修正
3. 変更 path に応じた local check (Iron Law 6 サブ条 = `docs/l2-workflow.md` §「PR 作成 path 別自動チェック」):
   - Python (`*.py`): `ruff check . && ruff format --check . && pyright && pytest`
   - GUI (`gui/src/**`, `gui/src-tauri/**`): `npm run lint && npm run typecheck && npm test && npm run build && cargo check`
   - Markdown (`docs/**.md`, `*.md`): `bash scripts/check-markdownlint.sh`
4. **1 round = 1 commit** で集約: 全 (A) を 1 つの commit にまとめる (round 単位の atomicity を確保、Round 別 SHA を summary コメントで参照しやすくするため)。message テンプレ: `fix(round-N): <要約> (Refs #<元 issue>)`。例外として、push 失敗で reset → 再 commit が必要な場合のみ複数 commit になる可能性を許容
```

- [ ] **Step 2: 確認**

```bash
grep -n "Step 2.4 (A) findings 修正" .claude/skills/iterate-review/SKILL.md
grep -n "1 round = 1 commit" .claude/skills/iterate-review/SKILL.md
```

Expected: hit。

- [ ] **Step 3: コミット**

```bash
git add .claude/skills/iterate-review/SKILL.md
git commit -m "feat(iterate-review): Step 2.4 (A) findings 修正 (1 round=1 commit + path 別 local check)"
```

---

### Task 17: `/iterate-review` SKILL.md - Step 2.5 (B) findings handoff (3 条件 AND)

**Files:**

- Modify: `.claude/skills/iterate-review/SKILL.md`

spec §2.5 Step 2.5 参照。

- [ ] **Step 1: SKILL.md 末尾に Step 2.5 を追加**

```markdown
#### Step 2.5 (B) findings handoff (新規 issue 起票、限定例外パス)

> **(B) 起票は限定例外**: 「指摘は原則すべて PR 内対応」(§1 (A) 強優先方針) に従い、ほとんどの finding は (A) で消化される。本 step に来るのは Step 2.2 validation を通過した「真に (B) trigger 3 条件 AND 該当」の finding のみ。スコープ単独・サイズ単独・受け入れ条件直結性単独で (B) 化された finding はここに到達しない (= validation で reject される)。

各 (B) に対し:

1. **(B) trigger 3 条件 AND 達成** を再確認: `別領域・別機能` AND `1 セッション超の独立設計が必要` AND `本 PR 同梱で受け入れ条件検証が破綻` の **すべて満たす** ことを rationale で確認。1 つでも欠ける場合は (A) に再分類して Step 2.4 へ戻す
2. **3 件以上の (B) は Iron Law 2 に従い AskUserQuestion で全件確認** (1 件 sample 提示 + 「全件 OK / 個別調整 / やめる」3 択)。3 件以上の (B) が一度に出るのは **設計疑い** のシグナルであり、user に「PR スコープが大きすぎる可能性」を提示
3. 2 件以下はそのまま `/create-task` で起票
4. 起票後の issue 番号を `handoff_state` に追加
5. PR body の deferred block を更新:

   ```bash
   gh pr edit $ARGUMENTS --body-file - <<'EOF'
   <既存 body>

   <!-- iterate-review:deferred:start -->
   ## Deferred Findings (managed by /iterate-review)

   - [B] Round 1: <topic 50 字以内> → deferred-to: #708 (新規)
   - [C] Round 2: <topic> → deferred-to: #680 (既存)

   <!-- iterate-review:deferred:end -->
   EOF
   ```

```

- [ ] **Step 2: 確認**

```bash
grep -n "Step 2.5 (B) findings handoff" .claude/skills/iterate-review/SKILL.md
grep -n "3 条件 AND" .claude/skills/iterate-review/SKILL.md
grep -n "iterate-review:deferred:start" .claude/skills/iterate-review/SKILL.md
```

Expected: 3 件 hit。

- [ ] **Step 3: コミット**

```bash
git add .claude/skills/iterate-review/SKILL.md
git commit -m "feat(iterate-review): Step 2.5 (B) handoff (3 条件 AND + 3+ bulk gate + deferred block)"
```

---

### Task 18: `/iterate-review` SKILL.md - Step 2.6 (C) findings handoff

**Files:**

- Modify: `.claude/skills/iterate-review/SKILL.md`

spec §2.5 Step 2.6 参照。

- [ ] **Step 1: SKILL.md 末尾に Step 2.6 を追加**

```markdown
#### Step 2.6 (C) findings handoff (既存 issue 追記)

1. 既存 issue へ `gh issue comment <既存 issue#> --body-file -` で方針記録 (HEREDOC、UTF-8 対策。`feedback_gh_command_ja_heredoc.md` 準拠):

   ```bash
   gh issue comment <既存 issue#> --body-file - <<'EOF'
   ## /iterate-review Round <N> 由来の追記

   PR #<PR#> をレビュー中に本 issue (#<既存 issue#>) と関連する課題を発見。
   
   - **finding**: <topic 50 字以内>
   - **本 PR スコープ判定**: (C) 既存 issue 追記 (重複起票回避)
   
   詳細は PR #<PR#> 内で議論。
   
   [<session-id>]
   EOF
   ```

1. `handoff_state` 追加 + PR body deferred block 更新 (Step 2.5 同様)

```

- [ ] **Step 2: 確認**

```bash
grep -n "Step 2.6 (C) findings handoff" .claude/skills/iterate-review/SKILL.md
grep -n "gh issue comment" .claude/skills/iterate-review/SKILL.md
```

Expected: hit。

- [ ] **Step 3: コミット**

```bash
git add .claude/skills/iterate-review/SKILL.md
git commit -m "feat(iterate-review): Step 2.6 (C) findings handoff (gh issue comment + HEREDOC)"
```

---

### Task 19: `/iterate-review` SKILL.md - Step 2.7 Push + CI wait

**Files:**

- Modify: `.claude/skills/iterate-review/SKILL.md`

spec §2.5 Step 2.7 参照。

- [ ] **Step 1: SKILL.md 末尾に Step 2.7 を追加**

```markdown
#### Step 2.7 Push + CI wait

- `git push origin <head-branch>`
- `gh pr checks $ARGUMENTS --watch` で CI 状態確定 (success / failure) を 15 分まで待機
- **CI green (success)**: 次 round へ進める
- **CI red (failure)**: 本 step では abort しない。次 round の `/review-pr` Step 4 が CI 失敗を findings に拾う前提 (`/review-pr` Step 4 「失敗あり: 失敗ジョブ名と概要を user に報告」を踏襲)。CI red が複数 round 連続で再発生する場合は §2.6 divergence 検知で打切り判定
- **timeout (15 分超)**: AskUserQuestion 3 択 (待ち続ける / CI 無視で次 round / abort)

実装ノート: `gh pr checks --watch` の timeout は CLI 側で直接制御できないため、`timeout` コマンド (Linux/macOS) または PowerShell の `Start-Job` + `Wait-Job -Timeout` で wrap する。Windows + Git Bash では `timeout 900 gh pr checks ...` で OK。
```

- [ ] **Step 2: 確認**

```bash
grep -n "Step 2.7 Push" .claude/skills/iterate-review/SKILL.md
grep -n "gh pr checks --watch" .claude/skills/iterate-review/SKILL.md
grep -n "15 分" .claude/skills/iterate-review/SKILL.md
```

Expected: hit。

- [ ] **Step 3: コミット**

```bash
git add .claude/skills/iterate-review/SKILL.md
git commit -m "feat(iterate-review): Step 2.7 Push + CI wait (green/red/timeout 3 ケース)"
```

---

### Task 20: `/iterate-review` SKILL.md - Step 3 収束/発散/打ち切り判定 (2 択 gate)

**Files:**

- Modify: `.claude/skills/iterate-review/SKILL.md`

spec §2.6 参照。

- [ ] **Step 1: SKILL.md 末尾に Step 3 (4 サブ節) を追加**

```markdown
### Step 3: 収束 / 発散 / 打ち切り判定

#### Step 3.1 収束 (success path)

(A)/(B)/(C) all 0 → Step 4 (Final summary comment) へ。

#### Step 3.2 発散検知

- `divergence_counter` 管理:
  - Round N の (A) 件数 `>=` 前 round の (A) 件数 (= 減少していない、増えた場合も含む) → `counter++`
  - Round N の (A) 件数 `<` 前 round の (A) 件数 (= 減少) → `counter = 0` にリセット
  - Round 1 (前 round 不在) の場合は counter 初期値 0 のまま
- `counter == 3` (= 3 round 連続で減少なし) → user gate 2 択

#### Step 3.3 ラウンドキャップ

Round == 5 + 未収束 → user gate 2 択。

#### Step 3.4 user gate 2 択 (発散・キャップ共通)

```text
- (i) PR 破棄 + scope 整理 + 再 PR (Recommended)
    → 現 PR を `gh pr close` (branch 維持、後続調査用に残す)
    → /scope-guard で残課題を整理し sub-PR に分割
    → /create-task で必要なら子 issue を整備
    → 各 sub-PR を順次作成 → /iterate-review で個別収束
    → user 主導の workflow、本 skill は abort して引き継ぐ
- (ii) abort (state を残して手動介入)
    → /iterate-review は終了、PR / branch は現状維持
    → user が手動で残 finding を判断 (merge する / 修正続行 / scope-guard 等)
```

> **(iii) 残 (A) 別 issue 化選択肢の不採用**: 「残 (A) を別 issue 化して merge」は issue 数収束方針 と矛盾するため**選択肢から除外**。Round 5 まで来たということは PR スコープが大きすぎたか実装方針が不適切のため、PR 単位での再構成 (i) が筋。

```

- [ ] **Step 2: 確認**

```bash
grep -n "^### Step 3:" .claude/skills/iterate-review/SKILL.md
grep -n "divergence_counter" .claude/skills/iterate-review/SKILL.md
grep -n "user gate 2 択" .claude/skills/iterate-review/SKILL.md
```

Expected: hit。

- [ ] **Step 3: コミット**

```bash
git add .claude/skills/iterate-review/SKILL.md
git commit -m "feat(iterate-review): Step 3 収束/発散/打ち切り判定 (2 択 gate + divergence_counter)"
```

---

### Task 21: `/iterate-review` SKILL.md - Step 4 Final summary comment

**Files:**

- Modify: `.claude/skills/iterate-review/SKILL.md`

spec §4 (summary コメント仕様) 参照。

- [ ] **Step 1: SKILL.md 末尾に Step 4 を追加**

```markdown
### Step 4: Final summary comment

(A)/(B)/(C) all 0 で収束したら、1 PR コメントを投稿する。

#### 4.1 投稿前 user 承認

AskUserQuestion 3 択:
- (i) 投稿する (Recommended)
- (ii) 微調整して投稿 (markdown を user に提示 → 修正 → 再承認)
- (iii) skip 投稿 (loop は終了、コメントは残さない)

#### 4.2 summary template

````markdown
# /iterate-review Summary

PR は <R> ラウンドの review-fix で収束。全 findings 解消完了。

## Findings by Round

| Round | (A) | (B) | (C) | 主な topic |
|---|---|---|---|---|
| 1 | <n> | <n> | <n> | <"; "区切り 30 字以内> |
| <R> | 0 | 0 | 0 | 収束 |

## Resolutions

### (A) PR 内修正
- Round <R> #<n>: `path:line` <topic 50 字以内> → `<commit SHA[:7]>`

### (B) 別 issue 起票
- Round <R>: <topic> → #<新規 issue#> (新規)

### (C) 既存 issue 追記
- Round <R>: <topic> → #<既存 issue#> (追記コメント link)

(各 section 該当なしなら "(なし)" のみ)

## Final 受け入れ条件 (acceptance criteria)

| # | 条件 | 実証 | 判定 |
|---|---|---|---|
| 1 | <条件> | `path:line` / `test_name` / CI log | ✓ |

## Final State

- CI: ✓ green (last commit `<SHA[:7]>`)
- 受け入れ条件: 全 ✓
- (A) 残: 0 / (B) handoff: <#N1, #N2 or なし> / (C) handoff: <#M1 or なし>
- 並行 PR: <検出ゼロ / [#X handled]>
- base sync: <CLEAN / 取り込み済み>

[<session-id>]
````

#### 4.3 投稿コマンド (HEREDOC + `--body-file -`)

```bash
gh pr comment <PR#> --body-file - <<'EOF'
# /iterate-review Summary
...
EOF
```

inline `--body "..."` は日本語が UTF-8 破損するため禁止 (`feedback_gh_command_ja_heredoc.md`)。

#### 4.4 length 対策

Round 数 5 + findings 多数で極端に長くなる場合:

- `<details>` で Round 詳細を折り畳み
- topic 文字数制限 (30 / 50 字)

`<details>` 適用例:

```markdown
<details>
<summary>Round 1 詳細 (4 件)</summary>

| # | Finding | Class | Resolution |
|---|---|---|---|
| 1 | ... | (A) | ... |

</details>
```

```

- [ ] **Step 2: 確認**

```bash
grep -n "^### Step 4:" .claude/skills/iterate-review/SKILL.md
grep -n "summary template" .claude/skills/iterate-review/SKILL.md
grep -n "HEREDOC" .claude/skills/iterate-review/SKILL.md
```

Expected: hit。

- [ ] **Step 3: コミット**

```bash
git add .claude/skills/iterate-review/SKILL.md
git commit -m "feat(iterate-review): Step 4 Final summary comment (template + HEREDOC + length 対策)"
```

---

### Task 22: `/iterate-review` SKILL.md - Step 5 + 環境制約 + Red Flags

**Files:**

- Modify: `.claude/skills/iterate-review/SKILL.md`

spec §2.8 / §2.9 / §2.10 参照。

- [ ] **Step 1: SKILL.md 末尾に Step 5 + 環境制約 + Red Flags + 呼び出し例を追加**

```markdown
### Step 5: 次の handoff

「LGTM 候補です。`gh pr merge $ARGUMENTS --squash` で merge してください。マージ後は `/close-issue <issue#>` で実測再検証してから手動クローズしてください」を user に提示。

本 skill 内で merge / close は実行しない (Iron Law 4 + 5 担保)。

## 環境制約・フォールバック

- **§A 孤立 PR (issue 紐付けなし)**: `/review-pr` §A を継承。subagent prompt に「孤立 PR fallback 適用」と明記
- **§B `/enforce-acceptance-criteria` 実行不可**: subagent 側で fallback、本 skill は subagent 結果に従う
- **session crash mid-loop**: state は会話 + PR body deferred block。再 invoke で deferred block + 残 commit から推論して継続可能 (PR body は永続)

## Red Flags (本 skill 固有、Iron Law Red Flags と呼応)

| 浮かんだ思考 | 実態 |
| --- | --- |
| 「subagent の findings を信じすぎず、自分で再判定」 | Iron Law 5 違反。subagent が Step 5b で出した分類は尊重する。再判定は user gate のみ |
| 「Round 6 で打ち切らずあと 1 回」 | divergence パターン。skill 規定の cap (5) を破らない |
| 「(A) 修正で副次的に (B) trigger 該当の変更が発生」 | scope-guard 案件。Step 2.4 中に追加 (B) 判定なら次 round へ持ち越さず即 handoff (ただし 3 条件 AND 厳格判定) |
| 「summary コメント前に LGTM コメントを別途投稿」 | 二重投稿。final summary が LGTM の役割も兼ねる |
| 「per-finding でコメント投稿した方が個別追跡しやすい」 | 仕様違反。per-finding 投稿は本設計で全廃 (ユーザー指示) |
| 「軽微な指摘だから observe 表記で済ませよう」 | **握り潰しパターン**。Step 2.2 validation で parse error。すべての finding は (A)/(B)/(C)/ambiguous のいずれかに必ず分類 |
| 「scope 外だから (B) 起票しよう」 | (A) 強優先方針違反。scope 外単独は (B) trigger 不成立。3 条件 AND を確認、満たさなければ (A) |
| 「CI が flaky / 環境起因だから無視で OK」 | 仕様違反。CI failure / latent issue / 環境起因問題はすべて (A) で PR 内対応 |
| 「Round 5 で残った 1 件くらい別 issue にしておこう」 | (iii) 不採用方針違反。残 (A) を別 issue に逃がさず、PR 破棄 (i) または手動 abort (ii) のいずれかで対応 |
| 「issue 数を増やしたくないが、本件は scope-out なので例外」 | (B) trigger 3 条件 AND を再確認。1 つでも欠ければ (A)。「例外」が頻発するのは判定基準のブレ |

## 呼び出し例

```text
/iterate-review 443
```

ユーザーが PR 番号を指定して呼び出す、または PR 作成セッションが skill として自走呼出する。

```

- [ ] **Step 2: 確認**

```bash
grep -n "^### Step 5:" .claude/skills/iterate-review/SKILL.md
grep -n "^## 環境制約" .claude/skills/iterate-review/SKILL.md
grep -n "^## Red Flags" .claude/skills/iterate-review/SKILL.md
grep -n "^## 呼び出し例" .claude/skills/iterate-review/SKILL.md
wc -l .claude/skills/iterate-review/SKILL.md
```

Expected: 4 件 hit、行数が ~280-380 行の range。

- [ ] **Step 3: コミット**

```bash
git add .claude/skills/iterate-review/SKILL.md
git commit -m "feat(iterate-review): Step 5 + 環境制約 + Red Flags 11 項目 + 呼び出し例 (SKILL.md 初版完成)"
```

---

### Task 23: `/iterate-review` eval/requirements.md (24 項目)

**Files:**

- Create: `.claude/skills/iterate-review/eval/requirements.md`

spec §5.2「requirements.md 主要 24 項目」参照。

- [ ] **Step 1: requirements.md を作成**

`.claude/skills/iterate-review/eval/requirements.md` を新規作成:

````markdown
# 要件チェックリスト (baseline 評価用、事前固定)

empirical-prompt-tuning §「ワークフロー 4. 両面評価」の精度算出・[critical] 付与ルールに従う。
各シナリオに [critical] 項目を最低 1 つ以上含む。事後の [critical] 付け外しは禁止。

## 判定規則 (全シナリオ共通)

- **成功/失敗**: [critical] 項目が**全て ○** のときのみ成功 (○)。1 つでも × or 部分的なら失敗 (×)
- **精度**: ○ = 満点、× = 0、部分的 = 0.5 で合算 / 全項目数
- **失敗時**: 「どの [critical] 項目が落ちたか」を 不明瞭点 節に 1 行添える

---

## グローバル要件 24 項目

| # | 要件 | 検証 scenario |
| --- | --- | --- |
| 1 | **[critical]** Step 0 で MERGED/CLOSED は abort、draft は 3 択 AskUserQuestion | a, d |
| 2 | **[critical]** Step 2.1 prompt template に必須要素 (gate skip / structured return / deferred-list / __ITERATE_REVIEW_SUBAGENT_MODE__ マーカー) | e, g |
| 3 | **[critical]** Step 2.3 Round summary AskUserQuestion = 1 round 1 回のみ | 全 |
| 4 | **[critical]** Step 2.5 (B) 3 件以上は bulk AskUserQuestion (Iron Law 2) | e |
| 5 | Step 2.7 push 後 CI green wait + 15 分 timeout で 3 択 escalate (CI red は次 round に流す) | f |
| 6 | **[critical]** Step 3.1 (A)/(B)/(C) 全ゼロ判定 | a, d |
| 7 | **[critical]** Step 3.2 divergence counter で 3 round 連続無進捗検知 → 2 択 gate (PR 破棄+再 PR / abort) | b |
| 8 | **[critical]** Step 3.3 Round 5 cap で 2 択 gate (同上) | c |
| 9 | **[critical]** Step 4 summary コメント 1 個 (HEREDOC) | h |
| 10 | summary template の必須 5 要素 (Round 表 / Resolutions / 受け入れ条件 / Final State / session-id) | h |
| 11 | summary 投稿前 AskUserQuestion 3 択 | h |
| 12 | (B)/(C) handoff 後 PR body deferred block 更新 | e |
| 13 | (B)/(C) handoff の subagent prompt exclusion 反映 | e |
| 14 | **[critical]** Step 2.2 握り潰し防止 validation: 全 finding 分類必須 / (B) 3 条件 AND 根拠必須 / 「無視」「観察のみ」キーワード弾き / ambiguous_judgments セクション必須 | a, e, i |
| 15 | **[critical]** (A) 強優先方針: CI failure / latent issue / 隣接 lint 違反は (A) 分類 | a, i |
| 16 | **[critical]** (B) 厳格 3 条件 AND: 1 条件のみは (A) に再分類 | i |
| 17 | Iron Law 1: マージ前に受け入れ条件全達成 | 全 |
| 18 | Iron Law 2: 3+ bulk 前 AskUserQuestion | e |
| 19 | Iron Law 3: scope-creep は (B)/(C) 振り分け (3 条件 AND 厳守) | a, e, i |
| 20 | Iron Law 4: skill 内で `gh pr merge` / `gh issue close` 実行禁止 | 全 |
| 21 | Iron Law 5: 曖昧点で AskUserQuestion (subagent `ambiguous_judgments` bubble) | a |
| 22 | Iron Law 6: push 前 local check pass + CI green wait | a, f |
| 23 | Red Flag 違反パターンが skill 文中に明記 (新規 11 項目含む) | static check |
| 24 | agent 自動起動 (PR 作成セッションが skill として呼ぶ) でも Standalone と同等動作 | scenario_a の agent-trigger variant |

---

## シナリオ別評価項目

### シナリオ A: simple_fix (1-2 round で収束する単純 (A) 修正)

(scenario_a_simple_fix.md で詳述)

[critical]: 1, 3, 6, 14, 15, 17, 19, 21

### シナリオ B: divergence (3 round 無進捗で divergence gate)

[critical]: 7, 14, 17, 23

### シナリオ C: round_cap (Round 5 で cap gate)

[critical]: 8, 14, 17, 23

### シナリオ D: lgtm_first (Round 1 で 0 findings 即収束)

[critical]: 1, 6, 14, 17

### シナリオ E: bc_handoff ((B)/(C) handoff + 再 flag 防止)

[critical]: 2, 4, 12, 13, 14, 18, 19

### シナリオ F: ci_timeout (CI 15 分 timeout)

[critical]: 5, 22

### シナリオ G: subagent_mode (`/review-pr` subagent mode 連携)

[critical]: 2, 14, 19

### シナリオ H: summary_format (summary コメント format 検証)

[critical]: 9, 10, 11

### シナリオ I: anti_sweep (握り潰し防止 validation + (A) 強優先 + (B) 3 条件 AND)

[critical]: 14, 15, 16, 19
````

- [ ] **Step 2: 確認**

```bash
grep -c "\\[critical\\]" .claude/skills/iterate-review/eval/requirements.md
ls -la .claude/skills/iterate-review/eval/requirements.md
```

Expected: [critical] 件数が 22+ (グローバル 13 + シナリオ別重複) ある。

- [ ] **Step 3: コミット**

```bash
git add .claude/skills/iterate-review/eval/requirements.md
git commit -m "test(iterate-review): eval/requirements.md (24 グローバル + 9 scenario 別)"
```

---

### Task 24: `/iterate-review` eval/scenario_a-d (4 ファイル新規)

**Files:**

- Create: `.claude/skills/iterate-review/eval/scenario_a_simple_fix.md`
- Create: `.claude/skills/iterate-review/eval/scenario_b_divergence.md`
- Create: `.claude/skills/iterate-review/eval/scenario_c_round_cap.md`
- Create: `.claude/skills/iterate-review/eval/scenario_d_lgtm_first.md`

各 scenario は spec §5.2 のファイル一覧に列挙された目的に基づく mock シナリオ。

- [ ] **Step 1: scenario_a_simple_fix.md を作成**

```markdown
# シナリオ A: simple_fix (1-2 round で収束する単純 (A) 修正)

## 想定状況

PR #902 (Refs シナリオ A from review-pr/eval/) を /iterate-review が dispatch。Round 1 で subagent が以下を返す:

- (A) #1: `audio/scan.py:42` ruff E501 line length (Step 2.4 で fix)
- (A) #2: `cli.py:105` log format `[%s]` → `<%s>` 統一 (Step 2.4)
- (A) #3: `docs/cli-spec.md` 出力例追加 (Step 2.4)
- 受け入れ条件: 全 ✓
- ambiguous: なし

Round 2 で再 dispatch すると 0 findings、収束。

## 期待挙動

- Step 0 で PR open 確認、Step 1 で初期化
- Step 2.1 で fresh subagent dispatch (prompt template 通り)
- Step 2.2 で findings parse + validation pass (全 finding 分類済み)
- Step 2.3 で Round 1 summary AskUserQuestion (proceed)
- Step 2.4 で 3 件 (A) を 1 commit に集約
- Step 2.7 で push + CI green wait
- Round 2: 0 findings → Step 4 へ
- Step 4 で summary 投稿前 AskUserQuestion 3 択 → 投稿
- Step 5 で LGTM 候補通知 + /close-issue 案内

## [critical] 項目

1. **[critical]** Round summary AskUserQuestion が 1 round 1 回のみ
2. **[critical]** 1 round = 1 commit (3 件 (A) を 1 commit にまとめる)
3. **[critical]** Step 2.2 validation で全 finding 分類確認
4. **[critical]** (A) 強優先で他に CI / latent issue があった場合も (A) に分類
5. **[critical]** Step 4 summary 投稿前 AskUserQuestion 3 択
6. **[critical]** Step 5 で gh pr merge / gh issue close を実行しない
7. agent 自動起動 variant: `/iterate-review 902` を agent が PR 作成後に呼んだケースでも上記と同じ動作
8. CI green wait timeout 15 分以内に終了する mock 設定
```

- [ ] **Step 2: scenario_b_divergence.md を作成**

```markdown
# シナリオ B: divergence (3 round 無進捗で divergence gate)

## 想定状況

PR #903 (mock) を /iterate-review が dispatch。

- Round 1: (A) 5 件 fix → push
- Round 2: (A) 5 件 (Round 1 fix が他箇所を壊した) → counter = 1
- Round 3: (A) 5 件 (同様に他箇所を壊し) → counter = 2
- Round 4: (A) 6 件 (むしろ増えた) → counter = 3 → divergence gate 発動

## 期待挙動

- divergence_counter が `(A) 件数 >= 前 round` で increment
- counter == 3 で AskUserQuestion 2 択 (PR 破棄+再 PR / abort)
- 「残課題を別 issue 化」選択肢は **存在しない**
- (i) 選択時: gh pr close + scope-guard 推奨 + abort
- (ii) 選択時: state 残して abort

## [critical] 項目

1. **[critical]** divergence_counter が `(A) 件数 >= 前 round` の条件で increment
2. **[critical]** counter == 3 で発動 (4 や 2 では発動しない)
3. **[critical]** AskUserQuestion 2 択のみ (3 択 / 4 択ではない)
4. **[critical]** 「残課題を別 issue 化」選択肢が存在しない
5. (i) 選択時 gh pr close を提案 (実行は user)
6. (ii) 選択時 state 残して終了
7. Red Flag 「Round 6 で打ち切らずあと 1 回」が skill 文中に存在
```

- [ ] **Step 3: scenario_c_round_cap.md を作成**

```markdown
# シナリオ C: round_cap (Round 5 で cap gate)

## 想定状況

PR #904 (mock) を /iterate-review が dispatch。

- Round 1-4: (A) は減少していくが、毎 round 新出 (A) も増えるため未収束 (例: 残 5 → 4 → 3 → 2)
- Round 5: 残 (A) = 1、しかし新出も 1 件発生し counter は 1
- Round 5 終了で cap 到達 → user gate 発動

## 期待挙動

- Round 5 完了時点で未収束 (= (A)/(B)/(C) any > 0) なら user gate
- AskUserQuestion 2 択 (発散と同じ)
- 「ROUND 6 でもう 1 回」は **不可** (skill 規定)

## [critical] 項目

1. **[critical]** Round 5 で cap 発動
2. **[critical]** 2 択 (発散と共通)
3. **[critical]** Round 6 への進行が **不可**
4. divergence と cap は別 trigger だが gate は同一 (2 択共通)
```

- [ ] **Step 4: scenario_d_lgtm_first.md を作成**

```markdown
# シナリオ D: lgtm_first (Round 1 で 0 findings、即収束)

## 想定状況

PR #905 (mock、軽微な doc 修正) を /iterate-review が dispatch。

- Round 1: subagent が `findings_table` 空、`recommendation = LGTM` を返す
- 受け入れ条件: 全 ✓
- 即 Step 4 へ

## 期待挙動

- Round 1 で (A)/(B)/(C) all 0 検出 → Step 3.1 → Step 4
- Round 2 を回さない (1 round で完結)
- summary template の Findings by Round 表は 1 行のみ ((R) 行)
- 投稿後 Step 5 で LGTM 候補通知

## [critical] 項目

1. **[critical]** 0 findings 即収束 (Round 2 回さない)
2. **[critical]** summary 投稿は実施 (skip しない、ただし AskUserQuestion 3 択は確認)
3. summary template Findings by Round 表が 1 行で OK
4. Step 5 で /close-issue 案内
```

- [ ] **Step 5: 確認**

```bash
ls -la .claude/skills/iterate-review/eval/scenario_*.md
grep -c "\\[critical\\]" .claude/skills/iterate-review/eval/scenario_a_simple_fix.md
grep -c "\\[critical\\]" .claude/skills/iterate-review/eval/scenario_b_divergence.md
grep -c "\\[critical\\]" .claude/skills/iterate-review/eval/scenario_c_round_cap.md
grep -c "\\[critical\\]" .claude/skills/iterate-review/eval/scenario_d_lgtm_first.md
```

Expected: 4 ファイル存在、各 [critical] が 3+ 個。

- [ ] **Step 6: コミット**

```bash
git add .claude/skills/iterate-review/eval/scenario_a_simple_fix.md \
        .claude/skills/iterate-review/eval/scenario_b_divergence.md \
        .claude/skills/iterate-review/eval/scenario_c_round_cap.md \
        .claude/skills/iterate-review/eval/scenario_d_lgtm_first.md
git commit -m "test(iterate-review): scenario a-d 新規 (simple_fix / divergence / round_cap / lgtm_first)"
```

---

### Task 25: `/iterate-review` eval/scenario_e-h (4 ファイル新規)

**Files:**

- Create: `.claude/skills/iterate-review/eval/scenario_e_bc_handoff.md`
- Create: `.claude/skills/iterate-review/eval/scenario_f_ci_timeout.md`
- Create: `.claude/skills/iterate-review/eval/scenario_g_subagent_mode.md`
- Create: `.claude/skills/iterate-review/eval/scenario_h_summary_format.md`

- [ ] **Step 1: scenario_e_bc_handoff.md を作成**

```markdown
# シナリオ E: bc_handoff ((B)/(C) handoff + 再 flag 防止)

## 想定状況

PR #906 (mock、複数モジュール touch する複雑 PR) を /iterate-review が dispatch。

- Round 1:
  - (A) 2 件 (本 PR scope 内)
  - (B) 3 件 (別領域 audio module security review、別 layer GUI a11y、外部依存 ffmpeg upgrade、それぞれ 3 条件 AND を満たす)
  - (C) 1 件 (既存 issue #680 と同テーマ)
  - bulk (B) 3 件以上 → AskUserQuestion 1 件 sample + 全件 OK / 個別 / やめる の 3 択
- Round 2: (A) 0 件、(B) 0 件 (前 round で起票済み topic は exclude されて再 flag されない)、(C) 0 件 → 収束

## 期待挙動

- Round 1 (B) 3 件で Iron Law 2 bulk AskUserQuestion 発動
- (B) 起票後 handoff_state に追加、PR body deferred block 更新
- (C) 既存 issue へ gh issue comment + handoff_state 追加
- Round 2 subagent prompt の deferred-list に Round 1 (B)/(C) topic が含まれる → 再 flag されない

## [critical] 項目

1. **[critical]** (B) 3 件で bulk AskUserQuestion 発動
2. **[critical]** (B) 各件が 3 条件 AND 満たすことを確認 (1 条件のみなら (A) に再分類)
3. **[critical]** PR body deferred block が更新される (`<!-- iterate-review:deferred:start --> ... <!-- iterate-review:deferred:end -->`)
4. **[critical]** Round 2 subagent prompt に Round 1 deferred topics が exclusion として渡される
5. **[critical]** 再 flag 防止: Round 2 で同 topic の findings が出ない (subagent が exclusion を尊重)
6. (C) 既存 issue 追記の HEREDOC + body-file - 形式
7. handoff_state に round 番号 + classification + issue_number が記録される
```

- [ ] **Step 2: scenario_f_ci_timeout.md を作成**

```markdown
# シナリオ F: ci_timeout (CI 15 分 timeout)

## 想定状況

PR #907 (mock、CI が 15 分以内に完了しない、例えば pyright が遅い) を /iterate-review が dispatch。

- Round 1: (A) 3 件 fix → push → CI が 15 分超でも未完了
- Step 2.7 timeout 検出 → AskUserQuestion 3 択

## 期待挙動

- `gh pr checks --watch` を timeout 15 分で wrap (`timeout 900 gh pr checks $ARGUMENTS --watch`)
- timeout 時 AskUserQuestion 3 択 (待ち続ける / CI 無視で次 round / abort)
- 各選択肢の挙動:
  - 待ち続ける: timeout 30 分に再延長して poll 継続
  - CI 無視: Step 3 へ進む (CI red の前提で Round 2 が CI 失敗を findings に拾う)
  - abort: state 残して終了

## [critical] 項目

1. **[critical]** 15 分 timeout 検出
2. **[critical]** AskUserQuestion 3 択
3. CI red と timeout の区別 (red は次 round に流す、timeout は user 介入)
4. 待ち続ける選択時、timeout 30 分に延長 (skill 内で具体値明記)
```

- [ ] **Step 3: scenario_g_subagent_mode.md を作成**

```markdown
# シナリオ G: subagent_mode (/review-pr subagent mode 連携)

## 想定状況

/iterate-review が Step 2.1 で /review-pr subagent dispatch。本シナリオは /review-pr の subagent mode 動作を /iterate-review 視点で検証 (= 連携の整合性確認)。

詳細: /review-pr eval scenario_f_subagent_mode.md と対称。

## 期待挙動 (連携部分)

- /iterate-review が prompt 内に `__ITERATE_REVIEW_SUBAGENT_MODE__` を埋める
- /review-pr が subagent mode に切り替わり 5 セクション final message を return
- /iterate-review Step 2.2 が parse + validation を pass

## [critical] 項目

1. **[critical]** prompt template に `__ITERATE_REVIEW_SUBAGENT_MODE__` マーカーが含まれる
2. **[critical]** 5 セクション (acceptance_criteria_status / findings_table / ambiguous_judgments / recommendation / meta) で受け取れる
3. **[critical]** ambiguous_judgments セクションが空でも parse 通る
4. /review-pr が gh pr comment を呼ばない
5. handoff_state を prompt に正しく埋める
```

- [ ] **Step 4: scenario_h_summary_format.md を作成**

```markdown
# シナリオ H: summary_format (summary コメント format 検証)

## 想定状況

PR #908 (mock、3 round で収束、各 round で findings がある) を /iterate-review が処理。Step 4 で summary 投稿。

- Round 1: (A) 3 件、(B) 1 件
- Round 2: (A) 1 件
- Round 3: 0 件 (収束)
- summary template に従い 1 PR コメント投稿

## 期待挙動

- Step 4 で summary template に従い markdown 生成
- 投稿前 AskUserQuestion 3 択 (投稿 / 微調整 / skip)
- HEREDOC + `--body-file -` で投稿
- Round 詳細を `<details>` で折り畳み (Round 数 ≥ 3 で trigger)
- topic 文字数制限 (30 / 50 字) 適用

## [critical] 項目

1. **[critical]** summary template の必須 5 要素 (Findings by Round / Resolutions / 受け入れ条件 / Final State / session-id)
2. **[critical]** 投稿前 AskUserQuestion 3 択
3. **[critical]** HEREDOC + `--body-file -` (UTF-8 対策)
4. Round 数 ≥ 3 で `<details>` 折り畳み trigger
5. topic 文字数制限 (30 / 50 字)
6. (B) handoff = #N (新規) / (C) handoff = #N (既存) と表記
7. session-id が末尾に `[<session-id>]` として記載
```

- [ ] **Step 5: 確認**

```bash
ls -la .claude/skills/iterate-review/eval/scenario_e_bc_handoff.md \
       .claude/skills/iterate-review/eval/scenario_f_ci_timeout.md \
       .claude/skills/iterate-review/eval/scenario_g_subagent_mode.md \
       .claude/skills/iterate-review/eval/scenario_h_summary_format.md
```

Expected: 4 ファイル存在。

- [ ] **Step 6: コミット**

```bash
git add .claude/skills/iterate-review/eval/scenario_e_bc_handoff.md \
        .claude/skills/iterate-review/eval/scenario_f_ci_timeout.md \
        .claude/skills/iterate-review/eval/scenario_g_subagent_mode.md \
        .claude/skills/iterate-review/eval/scenario_h_summary_format.md
git commit -m "test(iterate-review): scenario e-h 新規 (bc_handoff / ci_timeout / subagent_mode / summary_format)"
```

---

### Task 26: `/iterate-review` eval/scenario_i_anti_sweep (新規追加)

**Files:**

- Create: `.claude/skills/iterate-review/eval/scenario_i_anti_sweep.md`

spec §5.2 で新規追加した握り潰し防止 + (A) bias + (B) 3 条件 AND 検証用。

- [ ] **Step 1: scenario_i_anti_sweep.md を作成**

```markdown
# シナリオ I: anti_sweep (握り潰し防止 + (A) 強優先 + (B) 3 条件 AND)

## 想定状況

PR #909 (mock) を /iterate-review が dispatch。**subagent が意図的に握り潰しパターン / 誤分類 を出す状況** をシミュレート。

### Round 1 subagent return (悪意/ミス含む):

- (A) #1: `cli.py:42` ruff E501 → 修正 (正常)
- (A) #2: `audio/scan.py:100` ロギング不整合 → 修正 (正常)
- 観察コメントのみ #3: `docs/cli-spec.md` 微妙に古い記述あり (※分類欄空) ← validation #1 で reject
- (B) #4: `gui/src/screens/Detect.tsx:50` の不要 import → 「scope 外」のみ rationale ← validation #2 で reject (3 条件 AND 不成立)
- 「無視」キーワード行 #5: latent type warning は無視で OK ← validation #3 で reject
- ambiguous_judgments セクション欠落 ← validation #4 で reject

## 期待挙動

- Step 2.2 validation で 4 種類の parse error すべて検出
- 1 度目 parse error: 主セッションが具体的に欠陥を伝えて再 dispatch
- 再 dispatch では subagent が:
  - #3 を (A) に分類 (default (A))
  - #4 を (A) に再分類 (3 条件 AND 不成立、scope 単独は (B) 化不可)
  - #5 を (A) に分類 (latent issue は (A))
  - ambiguous_judgments セクション (空でも) を追加
- Round 1 final findings: 5 件すべて (A)
- Step 2.4 で 5 件を 1 commit に集約

## [critical] 項目

1. **[critical]** 分類欄空の行を parse error で reject
2. **[critical]** (B) で 3 条件 AND 不成立を parse error で reject
3. **[critical]** 「無視」「観察のみ」「対象外」キーワード単独行を parse error で reject
4. **[critical]** ambiguous_judgments セクション不在を parse error で reject
5. **[critical]** 再 dispatch 時に subagent が default (A) を採用
6. **[critical]** scope 外単独は (B) 化不可、(A) に再分類
7. **[critical]** latent issue / CI failure / 隣接 lint 違反は (A)
8. 1 度目 parse error で具体的指摘付き再 dispatch、2 度目失敗時のみ user gate
9. issue 数を増やさず PR 内消化が達成される
```

- [ ] **Step 2: 確認**

```bash
ls -la .claude/skills/iterate-review/eval/scenario_i_anti_sweep.md
grep -c "\\[critical\\]" .claude/skills/iterate-review/eval/scenario_i_anti_sweep.md
```

Expected: ファイル存在、[critical] 7 個。

- [ ] **Step 3: コミット**

```bash
git add .claude/skills/iterate-review/eval/scenario_i_anti_sweep.md
git commit -m "test(iterate-review): scenario_i_anti_sweep 新規 (validation 4 種 + (A) bias + (B) 3 条件 AND)"
```

---

## Phase C: Empirical Tuning Iter 0 → Iter 1

### Task 27: `/review-pr` iter_0 baseline 評価

**Files:**

- Create: `.claude/skills/review-pr/eval/reports/iter_0_post_redesign_baseline.md`

`feedback_skill_revision_empirical.md` 準拠で各 scenario を subagent dispatch でドライラン。

- [ ] **Step 1: iter_0 baseline を実施**

各 scenario (a, b, c, d, e_*, f) に対し以下を実施:

```bash
# 例: scenario A の dispatch
# 主セッション (本 plan 実装中) が一般 subagent (Agent tool, general-purpose) に対して:
# - scenario_a_central.md の mock PR data
# - 改訂後の review-pr/SKILL.md
# - requirements.md の [critical] 項目
# を渡し、「mock PR を review した場合の挙動を記述してください」と prompt
```

各 scenario の期待 vs 実際を比較し、ギャップを記録。

- [ ] **Step 2: iter_0_post_redesign_baseline.md を作成**

`.claude/skills/review-pr/eval/reports/iter_0_post_redesign_baseline.md` に以下構造で記録:

```markdown
# /review-pr post-redesign iter_0 Baseline

実施日: 2026-05-XX / session: <session-id>

## サマリ

- 全 scenario 数: 6 (A, B, C, D, E_central, E_edge_doc_only, E_edge_mixed, F)
- 成功 scenario 数: <数>
- 失敗 scenario 数: <数>

## シナリオ別結果

### シナリオ A
- [critical] 項目 X / Y 達成
- 不明瞭点: <落ちた [critical] と理由>

### シナリオ B
...

### シナリオ F (新規)
- [critical] 項目 X / Y 達成
- 不明瞭点: <落ちた [critical] と理由>

## ギャップ抽出

1. <gap 1: 例 - subagent mode 検出文字列が SKILL.md に記載されているが prompt 内検出ロジックが曖昧>
2. <gap 2: ...>

## 修正方針 (iter_1 で適用)

1. <gap 1 への修正案>
2. <gap 2 への修正案>
```

- [ ] **Step 3: コミット**

```bash
git add .claude/skills/review-pr/eval/reports/iter_0_post_redesign_baseline.md
git commit -m "test(review-pr): iter_0 post-redesign baseline 完了"
```

---

### Task 28: `/review-pr` iter_0 ギャップ反映 (SKILL.md 改善)

**Files:**

- Modify: `.claude/skills/review-pr/SKILL.md` (iter_0 で抽出されたギャップに応じて)

- [ ] **Step 1: iter_0_post_redesign_baseline.md の修正方針セクションを参照**

iter_0 で記録した修正方針を 1 つずつ SKILL.md に反映する。

- [ ] **Step 2: 各ギャップに対する修正を SKILL.md に適用**

例 (実際のギャップは iter_0 で確定):

- ギャップ「subagent mode 検出ロジックの曖昧さ」→ §G.1 に検出時の具体動作 (例: prompt 受信直後にマーカー grep する step) を追記
- ギャップ「Step 5b の自動分類規約が散らばっている」→ §G.2.1 内に集約

- [ ] **Step 3: 確認**

```bash
git diff .claude/skills/review-pr/SKILL.md | head -50
```

Expected: iter_0 ギャップに対応した修正が見える。

- [ ] **Step 4: コミット**

```bash
git add .claude/skills/review-pr/SKILL.md
git commit -m "refactor(review-pr): iter_0 ギャップ反映 (skill text 改善)"
```

---

### Task 29: `/review-pr` iter_1 revaluation

**Files:**

- Create: `.claude/skills/review-pr/eval/reports/iter_1_post_redesign_revaluation.md`

- [ ] **Step 1: iter_1 revaluation を実施**

iter_0 と同じ scenario set を再 dispatch し、修正後の挙動を記録。

- [ ] **Step 2: iter_1_post_redesign_revaluation.md を作成**

iter_0 と同じ構造で記録、ただし iter_0 ギャップが解消されているかを focus。

- [ ] **Step 3: pass / non-blocker のみであれば iteration 終了、structural gap が残れば iter_2 検討**

```markdown
## iter_1 結果サマリ
- 全 scenario pass: <YES / NO>
- 残存 gap: <なし / X 件 (詳細)>
- iter_2 必要性: <No / Yes>
```

- [ ] **Step 4: コミット**

```bash
git add .claude/skills/review-pr/eval/reports/iter_1_post_redesign_revaluation.md
git commit -m "test(review-pr): iter_1 post-redesign revaluation 完了"
```

---

### Task 30-32: `/iterate-review` iter_0 / 改善 / iter_1

**Files:**

- Create: `.claude/skills/iterate-review/eval/reports/iter_0_baseline.md`
- Modify: `.claude/skills/iterate-review/SKILL.md`
- Create: `.claude/skills/iterate-review/eval/reports/iter_1_revaluation.md`

`/review-pr` Task 27-29 と並行で同様の手順を /iterate-review に実施。

- [ ] **Step 1 (Task 30): /iterate-review iter_0 baseline**

9 scenario (a-i) を subagent dispatch でドライラン。各 [critical] 項目達成 / 不達成を記録。

`.claude/skills/iterate-review/eval/reports/iter_0_baseline.md` に Task 27 同様の構造で記録。

```bash
git add .claude/skills/iterate-review/eval/reports/iter_0_baseline.md
git commit -m "test(iterate-review): iter_0 baseline 完了"
```

- [ ] **Step 2 (Task 31): /iterate-review SKILL.md 改善**

iter_0 ギャップに基づき SKILL.md を修正。例:

- 「Step 2.2 validation の parse error 復帰手順が曖昧」→ 具体例を追加
- 「Step 3.2 divergence_counter の reset タイミングが不明確」→ counter リセット条件を強調

```bash
git add .claude/skills/iterate-review/SKILL.md
git commit -m "refactor(iterate-review): iter_0 ギャップ反映 (skill text 改善)"
```

- [ ] **Step 3 (Task 32): /iterate-review iter_1 revaluation**

修正後 SKILL.md で再 dispatch、`iter_1_revaluation.md` 作成。

```bash
git add .claude/skills/iterate-review/eval/reports/iter_1_revaluation.md
git commit -m "test(iterate-review): iter_1 revaluation 完了"
```

---

### Task 33: 両 skill summary レポート

**Files:**

- Create: `.claude/skills/iterate-review/eval/reports/summary.md`
- Create: `.claude/skills/review-pr/eval/reports/summary_post_redesign.md`

- [ ] **Step 1: 両 skill の最終結果を集約**

各 summary.md に iter_0 → iter_1 の改善幅、最終 pass 率、残存 gap (あれば) を記録。

- [ ] **Step 2: コミット**

```bash
git add .claude/skills/iterate-review/eval/reports/summary.md \
        .claude/skills/review-pr/eval/reports/summary_post_redesign.md
git commit -m "test(skills): 両 skill empirical tuning summary 完了"
```

---

## Phase D: Skill Boundary Audit

### Task 34: 4 観点で audit + skill_boundary_audit.md 作成

**Files:**

- Create: `.claude/skills/iterate-review/eval/skill_boundary_audit.md`

spec §5.5 参照。

- [ ] **Step 1: 4 観点 audit 実施**

`/iterate-review/SKILL.md` と `/review-pr/SKILL.md` を並べて読み、以下を Q&A 形式でチェック:

1. **冗長判定**: 同じことを 2 箇所で書いていないか?
2. **境界欠落判定**: ある操作の責務が両 skill にも `docs/l2-workflow.md` にも書いていないか?
3. **重複文章判定**: 共通ガイダンスが冗長に書かれていないか?
4. **誤誘導判定**: 一方の変更で他方が壊れる contract 不整合がないか? (特に subagent invocation mode の戻り値構造、マーカー文字列 `__ITERATE_REVIEW_SUBAGENT_MODE__` 一致)

- [ ] **Step 2: skill_boundary_audit.md を作成**

```markdown
# Skill Boundary Audit (post-tuning)

実施日: 2026-05-XX / session: <session-id>

## 4 観点 audit 結果

### 1. 冗長判定
- (検出された冗長項目を列挙、または「なし」)

### 2. 境界欠落判定
- (検出された欠落項目を列挙、または「なし」)

### 3. 重複文章判定
- (検出された重複文章を列挙、または「なし」)

### 4. 誤誘導判定
- (検出された contract 不整合を列挙、または「なし」)

## 修正アクション
- (audit で検出された問題への修正計画。iter_2 で適用するか、本 PR で修正するか)
```

- [ ] **Step 3: コミット**

```bash
git add .claude/skills/iterate-review/eval/skill_boundary_audit.md
git commit -m "audit: skill boundary 4 観点 audit 完了"
```

---

### Task 35: 必要なら iter_2 で修正

**Files:**

- Modify: 該当 SKILL.md (audit で検出された問題に応じて)

- [ ] **Step 1: audit.md の修正アクションを確認**

audit で「修正必要」と判定した項目があれば iter_2 として両 SKILL.md を修正。なければ skip。

- [ ] **Step 2: 修正後 audit.md に「修正済み」を追記**

```markdown
## iter_2 修正実施 (audit を受けて)
- (実施した修正の summary)
```

- [ ] **Step 3: コミット (修正があった場合のみ)**

```bash
git add .claude/skills/{review-pr,iterate-review}/SKILL.md \
        .claude/skills/iterate-review/eval/skill_boundary_audit.md
git commit -m "refactor(skills): audit 反映 (iter_2 修正)"
```

---

## Phase E: Docs Updates

### Task 36: docs/l2-workflow.md 更新

**Files:**

- Modify: `docs/l2-workflow.md` (skill 一覧 + 起動経路明記)

spec §6.2 参照。

- [ ] **Step 1: skill 一覧 table に `/iterate-review` を追加**

`docs/l2-workflow.md` の §「タスク種別と進め方」 にある skill 一覧 table を確認:

```bash
grep -n "/review-pr" docs/l2-workflow.md | head
grep -n "/close-issue" docs/l2-workflow.md | head
```

table 内 `/review-pr` の直前または直後に `/iterate-review` 行を追加:

```markdown
| PR review-fix loop | `/iterate-review` | PR 作成後の review-fix ループ自動化 (Round cap 5、(A) 強優先、握り潰し防止 validation、収束時 summary コメント 1 個投稿) |
```

- [ ] **Step 2: agent 自動起動経路の note 追記**

table 直下のテキストに以下を追加:

```markdown
**`/iterate-review` の起動経路**: user 手動 (`/iterate-review <PR#>`) と agent 自動 (PR 作成セッションが PR 作成後に skill として呼ぶ) の両方をサポート。Iron Law 6 Pre-flight 通過後に呼ぶこと。
```

- [ ] **Step 3: 確認**

```bash
grep -n "/iterate-review" docs/l2-workflow.md
```

Expected: 複数行で hit (table + note)。

- [ ] **Step 4: lint**

```bash
bash scripts/check-markdownlint.sh docs/l2-workflow.md
```

Expected: pass。

- [ ] **Step 5: コミット**

```bash
git add docs/l2-workflow.md
git commit -m "docs(l2-workflow): /iterate-review skill 追加 + 起動経路 (user 手動 / agent 自動) 明記"
```

---

### Task 37: CLAUDE.md 更新

**Files:**

- Modify: `CLAUDE.md` (コマンド section + skill 一覧 + Plugin との関係 + (A) 強優先方針)

spec §6.2 参照。

- [ ] **Step 1: 「コマンド」section に `/iterate-review` を追加**

`CLAUDE.md` の §コマンド section 内、L1/L2 etc. の skill 列挙箇所に `/iterate-review` を追加:

```markdown
- 既存 skill: `/review-pr`, `/iterate-review`, `/enforce-acceptance-criteria`, `/scope-guard`, `/create-task`, `/close-issue`, `/release`
```

(skill 一覧の正確な記述位置は CLAUDE.md の現状を確認して合わせる)

- [ ] **Step 2: §「開発ワークフロー」または §「Plugin との関係」 (該当箇所) に (A) 強優先方針を追記**

以下を追加:

```markdown
### `/iterate-review` workflow と (A) 強優先方針

PR 作成後は `/iterate-review <PR#>` で review-fix ループを自走させる (user 手動 or agent 自動)。本 skill は **「指摘は原則すべて PR 内対応」** の (A) 強優先方針 + (B) 厳格 3 条件 AND + 握り潰し防止 validation により、CI failure / latent issue / 隣接 lint 違反 等を当 PR 内で消化し、派生 issue 数を最小化する (issue 数収束)。
```

- [ ] **Step 3: 確認**

```bash
grep -n "/iterate-review" CLAUDE.md
grep -n "(A) 強優先方針" CLAUDE.md
```

Expected: 両方 hit。

- [ ] **Step 4: lint**

```bash
bash scripts/check-markdownlint.sh CLAUDE.md
```

Expected: pass。

- [ ] **Step 5: コミット**

```bash
git add CLAUDE.md
git commit -m "docs(CLAUDE.md): /iterate-review skill 追加 + (A) 強優先方針 + agent 自動起動 追記"
```

---

## Phase F: PR Creation

### Task 38: 全変更 review + commit organization

**Files:** なし (git 操作のみ)

- [ ] **Step 1: 全 commit log を確認**

```bash
git log --oneline origin/develop-0.2.0..HEAD
git diff --stat origin/develop-0.2.0
```

Expected: Phase A-E までの commit が時系列で並ぶ (~30+ commits)。意図しない変更がないか確認。

- [ ] **Step 2: 不要な commit / 修正漏れがないか軽く `gh pr create` 前に確認**

`.claude/skills/{review-pr,iterate-review}/SKILL.md` と `eval/` の重要ファイルが完成しているか:

```bash
ls .claude/skills/iterate-review/SKILL.md \
   .claude/skills/iterate-review/eval/requirements.md \
   .claude/skills/iterate-review/eval/scenario_a_simple_fix.md \
   .claude/skills/iterate-review/eval/scenario_i_anti_sweep.md \
   .claude/skills/iterate-review/eval/skill_boundary_audit.md \
   .claude/skills/review-pr/eval/scenario_f_subagent_mode.md
```

Expected: 全ファイル存在。

- [ ] **Step 3: ローカル check 全 pass 確認**

```bash
ruff check . && ruff format --check .  # Python 変更がなければ即 pass
bash scripts/check-markdownlint.sh
```

Expected: 全 pass。

---

### Task 39: PR Pre-flight (Iron Law 6) + PR 作成

**Files:** なし (`gh` CLI 操作)

- [ ] **Step 1: Iron Law 6 PR Pre-flight 再実行**

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline
gh pr list --search ".claude/skills" --state all --limit 10
gh pr list --state open --base develop-0.2.0 --json number,title,headRefName,files --limit 20
```

Expected: 取り込み未済 commit が当 PR の touched files (`.claude/skills/**`, `docs/l2-workflow.md`, `CLAUDE.md`, `docs/superpowers/{specs,plans}/2026-05-10-*`) と交差しない。並行 PR で同範囲を扱うものなし。

- [ ] **Step 2: 交差あれば merge + 各 SKILL.md / eval ファイル整合性再確認**

```bash
git merge origin/develop-0.2.0  # 必要時のみ
```

- [ ] **Step 3: PR 作成 (Closes/Fixes/Resolves キーワード禁止、Iron Law 4)**

PR 本文は spec / plan の要約 + Self-Test Report + 関連 issue 番号。skill の改修は通常 issue ベースではないため `Refs` キーワードのみ使用 (issue 番号は本機能改善 issue があれば使用、なければ「skill 改善 PR」として spec / plan link を記載)。

```bash
gh pr create \
  --base develop-0.2.0 \
  --title "feat(skills): /iterate-review 新規 + /review-pr 機能整理 (review-fix ループ自動化)" \
  --body-file - <<'EOF'
## 概要

PR 作成後の review-fix ループを `/iterate-review` 新規 skill で自動化し、`/review-pr` の per-finding コメント投稿と再レビューラウンド管理を `/iterate-review` 側に集約。両 skill を empirical-prompt-tuning + post-tuning skill boundary audit で抜け漏れ・冗長除去。

## 設計参照

- spec: [`docs/superpowers/specs/2026-05-10-iterate-review-and-review-pr-redesign.md`](docs/superpowers/specs/2026-05-10-iterate-review-and-review-pr-redesign.md)
- plan: [`docs/superpowers/plans/2026-05-10-iterate-review-and-review-pr-redesign.md`](docs/superpowers/plans/2026-05-10-iterate-review-and-review-pr-redesign.md)

## 主要変更

- **新規** `/iterate-review` skill (`.claude/skills/iterate-review/SKILL.md`) + eval 一式 (requirements 24 項目 / scenario a-i / iter_0/1 reports / boundary audit)
- **改訂** `/review-pr` skill: Step 6 AskUserQuestion 削除 / Step 7 per-finding comment 廃止 / Step 7a 移管 / Step 8 MERGED 限定 / §G subagent invocation mode 新設
- **更新** `/review-pr` eval: 既存 scenario の期待 output 更新 + scenario_f_subagent_mode 新規 + reports 追加
- **更新** `docs/l2-workflow.md` / `CLAUDE.md` (skill 一覧 + 起動経路 + (A) 強優先方針追記)

## Self-Test Report

### machine-verified
- [x] `bash scripts/check-markdownlint.sh` pass
- [x] `git log` で意図した commit のみ (Phase A-E)
- [x] 両 skill の `eval/reports/iter_1_*` で全 [critical] pass

### Idios 実機確認 (本 PR 自体の動作)
- 初回 PR 自体は `/iterate-review` がまだ deploy されていないため **手動 review** 対象。`/review-pr` の改訂版 (Step 1-5 + 6 報告生成) は動作確認の一部として使用可能
- 2 回目以降の PR で `/iterate-review` 実運用予定

## Iron Law 整合性

spec §7 で 6 項目すべて ✓ 検証済み。詳細は spec を参照。

## 影響範囲

新規ファイル: `.claude/skills/iterate-review/**` 全て
改訂ファイル: `.claude/skills/review-pr/SKILL.md` + `eval/**`
更新ファイル: `docs/l2-workflow.md`, `CLAUDE.md`

## Refs

(関連 issue 番号があれば記載、なければ skill 改善 PR として spec / plan link のみ)

[<session-id>]
EOF
```

注: `Closes` / `Fixes` / `Resolves` キーワードを **使わない** (Iron Law 4)。

Expected: PR 番号が return される。

---

### Task 40: 自己 review (初回限定、手動)

**Files:** なし (review 操作のみ)

spec §8「自己参照リスク」参照。本 PR は `/iterate-review` がまだ使えないため手動 review する。

- [ ] **Step 1: `/review-pr <PR#>` (改訂版) を invoke**

```text
/review-pr <PR#>
```

改訂版 `/review-pr` の Step 1-5 を回し、Step 6 で報告 markdown を確認。Step 7 は推奨アクション提示で完結。

- [ ] **Step 2: 改訂版 /review-pr 自体の動作確認 (検証目的)**

`/review-pr` がそれまでの per-finding comment 投稿を行わず、報告 markdown 生成のみで終了することを目視確認。

- [ ] **Step 3: 摘出された finding を手動で fix → push (loop manual emulation)**

Round 2-N を手動で繰り返し、すべての (A) を消化する。

- [ ] **Step 4: 全 finding 解消 + CI green 後、user 承認を得て gh pr merge --squash**

```bash
gh pr merge <PR#> --squash
```

- [ ] **Step 5: 紐づく issue があれば `/close-issue <issue#>` で実測再検証 + 手動 close**

(本 PR は skill 改善のため、紐づく issue は spec / plan の経緯から確定する。なければ skip 可)

---

## Self-Review (実装前 plan check)

writing-plans の self-review section に従い、以下を確認:

**1. Spec coverage**: spec §0-§10 の各 section を本 plan のどの Task が implement するか:

- §0 概要 → Plan goal + architecture
- §1 主要決定事項 → Phase A-E 全体で反映 (specific tasks)
- §2 /iterate-review skill 本体 → Phase B (Task 11-22)
- §3 /review-pr 機能整理 → Phase A (Task 2-7)
- §4 summary コメント仕様 → Task 21 で template 実装
- §5 empirical-prompt-tuning 計画 → Phase C (Task 27-33)
- §5.5 skill boundary audit → Phase D (Task 34-35)
- §6 影響範囲 → Phase E (Task 36-37) + Phase F (Task 39)
- §7 Iron Law 整合性 → Phase F PR 本文に Self-Test Report として反映
- §8 自己参照リスク → Phase F Task 40 (手動 review)
- §9 plan 段取り → 本 plan 自体
- §10 参考 → spec で完結 (plan で再掲不要)

すべて対応済み。

**2. Placeholder scan**: TODO / TBD / `<...>` などのプレースホルダーは:

- spec 参照 (`spec §X.Y 参照`) は意図的、これは「detailed content is in spec」を意味
- iter_0 ギャップ抽出は実行時にしか確定しないため Task 27-32 で「ギャップに応じて」と書いてあるのは適切 (空 placeholder ではない)

その他のプレースホルダーは無し。

**3. Type consistency**: 用語の一貫性:

- `__ITERATE_REVIEW_SUBAGENT_MODE__` マーカー: Task 6 (review-pr §G), Task 13 (iterate-review Step 2.1), Task 23-25 (eval scenarios) で一貫
- `handoff_state` / `findings_history` / `divergence_counter`: Task 12, 14, 17, 18, 20 で一貫
- 「(A) 強優先方針」 / 「(B) 厳格 3 条件 AND」: Phase A-B 全体で一貫
- 「2 択 gate」: Task 20, 24 (scenario b/c), Task 23 (requirements 7/8) で一貫
- summary template の 5 セクション: Task 21, 25 (scenario h), Task 23 (requirements 10) で一貫

すべて整合。

---

## 完了基準

- [ ] Phase A-E のすべての Task で commit 済み
- [ ] Phase D の skill_boundary_audit.md で「修正必要なし」または「iter_2 で修正済み」
- [ ] 両 skill の `eval/reports/iter_1_*` で全 [critical] pass
- [ ] PR が merge され、紐づく issue は `/close-issue` で手動クローズ済み (該当ある場合)
- [ ] 2 回目以降の PR で `/iterate-review` を実運用開始可能な状態
