# Issue/PR Clarity Preamble Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** issue (refactor / task / risk) と PR の冒頭に「期待値 / 現状 / ユーザー影響 (issue) / 修正内容 (PR)」preamble を必須化し、後から読んでも何を目指すのか・なぜ重要かが一目で分かる構造に揃える。

**Architecture:** doc + skill + template + workflow rule の 7 file 改修。production code 変更なし。create-task skill 改修部分は mizchi `empirical-prompt-tuning` protocol (URL 参照、vendoring 禁止) に従い 2 consecutive clears まで iterate。

**Tech Stack:**

- Markdown (`docs/` / `.github/pull_request_template.md` / `.claude/skills/*/SKILL.md` / `.claude/skills/*/eval/requirements.md`)
- mizchi empirical-prompt-tuning protocol: <https://github.com/mizchi/skills/tree/main/empirical-prompt-tuning> (都度 WebFetch)
- markdownlint (`bash scripts/check-markdownlint.sh`、CI と同 version で全 .md チェック)
- `gh` CLI (PR 作成)
- Task tool (fresh subagent dispatch for empirical tuning)

**Spec:** [docs/superpowers/specs/2026-05-18-issue-pr-clarity-preamble-design.md](../specs/2026-05-18-issue-pr-clarity-preamble-design.md)

**session-id:** `eloquent-kalam-0196f5`

---

## File Structure

| ファイル | 役割 | 変更種別 |
| --- | --- | --- |
| `docs/l2-workflow.md` | 既存 doc、§skill 改修 workflow と §PR body 規約 を 2 節追記 | Modify |
| `docs/issue-policy.md` | §3 内 refactor / task / risk テンプレ 3 つを書き換え | Modify |
| `.github/pull_request_template.md` | 冒頭 2 section (概要 / 変更点) → 3 section (期待値 / 現状 / 修正内容) 置換 | Modify |
| `CLAUDE.md` | §開発ワークフロー に l2-workflow.md §skill 改修 workflow への 1 行 link 追加 | Modify |
| `.claude/skills/create-task/eval/requirements.md` | シナリオ B/C に preamble 検証項目追加、シナリオ D (refactor) / E (risk) 新設 | Modify |
| `.claude/skills/create-task/SKILL.md` | 手順 3 / 5 / 注意事項に preamble 必須化規約追記 | Modify |
| `docs/superpowers/plans/2026-05-18-issue-pr-clarity-preamble-plan.md` | 本 plan ファイル | Create (実装中の参照用) |

---

## Tasks

### Task 1: docs/l2-workflow.md に §skill 改修 workflow 節を追加

**Files:**

- Modify: `docs/l2-workflow.md` (§計画フェーズの運用 の直後を suggested 挿入位置、line 501 付近)

- [ ] **Step 1.1: 挿入位置を確認**

```bash
grep -n '^## ' docs/l2-workflow.md | head -30
```

Expected: `## 計画フェーズの運用` の直後の `## Issue ラベル運用` の直前に新節を挿入する位置を確認。

- [ ] **Step 1.2: §skill 改修 workflow 節を挿入**

`## 計画フェーズの運用` 節の末尾 (次の `## Issue ラベル運用` の直前) に以下を追加:

```markdown
## skill 改修 workflow (empirical-prompt-tuning protocol)

`.claude/skills/*/SKILL.md` を改修した PR では mizchi empirical-prompt-tuning protocol に従う:

- 上流 URL (vendoring 禁止、license 未設定): <https://github.com/mizchi/skills/tree/main/empirical-prompt-tuning>
- 取得: `gh api repos/mizchi/skills/contents/empirical-prompt-tuning/SKILL.md -H "Accept: application/vnd.github.raw"`

### 必須手順

1. Iter 0: SKILL.md frontmatter description と body の整合性 static check
2. `eval/requirements.md` を改修内容に合わせて update ([critical] tag 必須)
3. 2-3 シナリオ (1 median + 1-2 edge) を準備
4. Task tool で fresh subagent dispatch (self-reread 禁止)
5. 各 unclear point を Issue / Cause / General Fix Rule で構造化
6. 2 consecutive clears (new unclear=0 + accuracy +3pt 以下 + step ±10% + duration ±15%) まで iterate
7. PR Self-Test Report に Iteration table (per-scenario success / accuracy / steps / duration / structured reflection / ledger) を記録

### 例外

trivial wording fix (typo / link 修正 / コメント追記のみ) は skip 可。判断は `AskUserQuestion` で確認する。

### offline / GitHub 不到達時

WebFetch 不可 → skill 改修作業を保留。短期キャッシュは作業 dir に置いて **commit しない**。

### Iron Law 6 路線

上記を skip した skill 改修 PR は「未検証 PR」と同じ扱い。Self-Test Report の「empirical prompt tuning」section を欠いた場合は `/review-pr` で blocker 扱い。
```

- [ ] **Step 1.3: markdownlint 確認**

Run: `bash scripts/check-markdownlint.sh`
Expected: 0 violations。

- [ ] **Step 1.4: Commit**

```bash
git add docs/l2-workflow.md
git commit -m "$(cat <<'EOF'
docs(l2-workflow): §skill 改修 workflow 節を追加 (mizchi empirical-prompt-tuning protocol URL 参照)

session-id: eloquent-kalam-0196f5
EOF
)"
```

---

### Task 2: docs/l2-workflow.md に §PR body 規約 節を追加

**Files:**

- Modify: `docs/l2-workflow.md` (§Self-Test Report 規約 と §(A) PR 内修正優先 規約 の間、line 344 付近)

- [ ] **Step 2.1: 挿入位置を確認**

```bash
grep -n '^## ' docs/l2-workflow.md | head -30
```

Expected: `## Self-Test Report 規約` と `## (A) PR 内修正優先 規約` の間を確認。

- [ ] **Step 2.2: §PR body 規約 節を挿入**

`## Self-Test Report 規約` 節の末尾 (次の `## (A) PR 内修正優先 規約` の直前) に以下を追加:

```markdown
## PR body 規約 (期待値 / 現状 / 修正内容)

すべての PR で本文冒頭に以下 3 section を inline 必須化する:

- `## 期待値 (あるべき姿)`: 2-4 文。この PR がマージされた後にコードベース or 動作がどうあるべきか + なぜ目指すか
- `## 現状 (修正前)`: 2-4 文。PR 作成時点でどうなっているか + 期待値とのギャップ
- `## 修正内容 (現状 → 期待値)`: bullet list。何をしたか、必要なら file path:line で具体化

### issue ref の運用

issue ref がある PR も、期待値 / 現状 は PR 本文に **簡潔に inline 記載** (issue を辿らせない)。詳細は元 issue へ link 参照可、PR 本文と issue 本文の重複は受容。

### release / meta PR の解釈

複数 PR を統合する release / meta PR (例: PR #774) も同構造で書く:

- 期待値: 当該リリースバージョンが出て該当問題が解消されている
- 現状: develop ブランチで修正が積まれ統合準備完了、main は未統合
- 修正内容: 統合した PR list + 各 Track の解消内容

### Iron Law 6 サブ条との関係

本規約は PR template (`.github/pull_request_template.md`) と一致する。template の `## 期待値` / `## 現状` / `## 修正内容` を埋めずに PR 作成すると `/review-pr` で blocker 扱い。
```

- [ ] **Step 2.3: markdownlint 確認**

Run: `bash scripts/check-markdownlint.sh`
Expected: 0 violations。

- [ ] **Step 2.4: Commit**

```bash
git add docs/l2-workflow.md
git commit -m "$(cat <<'EOF'
docs(l2-workflow): §PR body 規約 節を追加 (期待値 / 現状 / 修正内容 inline 必須化)

session-id: eloquent-kalam-0196f5
EOF
)"
```

---

### Task 3: docs/issue-policy.md §3 の 3 テンプレ書き換え

**Files:**

- Modify: `docs/issue-policy.md` §3 (`[refactor]`, `[task]`, `[risk]` テンプレ部分)

- [ ] **Step 3.1: 現状確認**

```bash
grep -n '^### \[' docs/issue-policy.md
```

Expected: `### [bug] テンプレート` (123), `### [doc] テンプレート` (139), `### [refactor] テンプレート` (155), `### [question] テンプレート` (171), `### [risk] テンプレート` (187), `### [task] テンプレート` (203)。bug / doc / question は触らない。

- [ ] **Step 3.2: `### [refactor] テンプレート` を書き換え**

`### [refactor] テンプレート` 配下のコードブロック全体を以下に置き換える:

````markdown
```markdown
## 概要
<1-2 文で何を refactor する issue か>

## 期待値 (あるべき姿)
<2-4 文。完了後にコードがどうあるべきか + なぜ目指すかの理由>

## 現状
<2-4 文。今のコードがどうなっているか + 期待値とのギャップ>

## ユーザー影響・重要性
<1 行で位置付け。例:「ユーザー影響なし、メンテ性負債」「将来のセキュリティ整合性」>

## 該当箇所
<ファイルパス:行番号>

## ブロッカー / なぜ現状で止まっているか
<実装上のハードル、後回しの理由。不要なら省略可>

## 対応方針
<改善方法の案>

## 受け入れ条件 (任意)
- [ ] ...

## 関連 (任意)
- 元 umbrella: #...
- spec: ...
- 関連 PR: ...
```
````

- [ ] **Step 3.3: `### [task] テンプレート` を書き換え**

`### [task] テンプレート` 配下のコードブロック全体を以下に置き換える:

````markdown
```markdown
## 概要
<1-2 文で何をするタスクか>

## 期待値 (あるべき姿)
<2-4 文。完了後にどういう状態になるか + なぜ必要か>

## 現状
<2-4 文。今どうなっているか + 期待値とのギャップ>

## ユーザー影響・重要性
<1 行で位置付け。例:「ユーザー直結機能」「内部観察記録」「依存タスクの前提」>

## 背景 (任意)
<経緯 / 依存タスク / 関連 issue/PR の解説 (期待値とは別)>

## 確認項目 / 作業項目
- [ ] 項目1
- [ ] 項目2

## 対応方針
<作業の進め方・完了条件>

## 受け入れ条件 (任意)
- [ ] ...
```
````

- [ ] **Step 3.4: `### [risk] テンプレート` を書き換え**

`### [risk] テンプレート` 配下のコードブロック全体を以下に置き換える:

````markdown
```markdown
## 概要
<1-2 文でどんなリスク・懸念か>

## 期待値 (あるべき姿)
<2-4 文。リスクが低減された後の状態 + なぜ目指すか>

## 現状
<2-4 文。今のリスク状態 + どこに risk が存在するか>

## ユーザー影響・重要性
<1 行で位置付け: 顕在化時の被害規模・誰に影響するか>

## 該当箇所 (任意)
<ファイルパス:行番号 など>

## 顕在化時の被害詳細
<具体的な被害ストーリー、攻撃ベクター、影響範囲>

## 対応方針
<リスク低減策の案>

## 受け入れ条件 (任意)
- [ ] ...
```
````

- [ ] **Step 3.5: §3 冒頭に preamble 規約の説明を追記**

`## 3. 本文フォーマット` の直後 (テンプレ一覧の前) に以下を追加:

```markdown
### preamble 規約 (refactor / task / risk のみ)

`refactor` / `task` / `risk` の 3 prefix では、`## 概要` 直後に以下 3 section を **必須** preamble として含める:

- `## 期待値 (あるべき姿)`: 2-4 文。完了後にコード or 状態がどうあるべきか + なぜ目指すか
- `## 現状`: 2-4 文。今どうなっているか + 期待値とのギャップ
- `## ユーザー影響・重要性`: **1 行で** 位置付け (1 行を超える場合は別 section に分離: refactor=ブロッカー / risk=顕在化時被害詳細)

書けないなら起票しない (= まだ issue 化に値する整理ができていない signal)。`bug` / `doc` / `question` は現行どおり preamble 不要 (既に「現状 / 問題」が分離されている)。
```

- [ ] **Step 3.6: markdownlint 確認**

Run: `bash scripts/check-markdownlint.sh`
Expected: 0 violations。

- [ ] **Step 3.7: Commit**

```bash
git add docs/issue-policy.md
git commit -m "$(cat <<'EOF'
docs(issue-policy): refactor / task / risk テンプレに preamble (期待値 / 現状 / ユーザー影響) を必須化

- refactor: 旧「問題」を「ブロッカー / なぜ現状で止まっているか」に rename
- risk: 旧「問題」を「顕在化時の被害詳細」に rename
- §3 冒頭に preamble 規約説明を追記

session-id: eloquent-kalam-0196f5
EOF
)"
```

---

### Task 4: .github/pull_request_template.md 書き換え

**Files:**

- Modify: `.github/pull_request_template.md` (冒頭 `## 概要` + `## 変更点` を `## 期待値` + `## 現状` + `## 修正内容` に置換)

- [ ] **Step 4.1: 現状確認**

```bash
head -10 .github/pull_request_template.md
```

Expected: `## 概要` と `## 変更点` セクションが冒頭にあること。

- [ ] **Step 4.2: 冒頭 2 section を 3 section に置換**

ファイル冒頭の以下:

```markdown
## 概要

<!-- 1-3 行でこの PR の目的を書いてください。Refs #123 の形で関連 issue を記載 -->

## 変更点

<!-- 主要な変更を箇条書きで。ファイル単位ではなく「何を・なぜ」 -->
```

を以下に置き換える:

```markdown
## 期待値 (あるべき姿)

<!--
2-4 文。この PR がマージされた後にコードベース or 動作がどうあるべきか + なぜ目指すか。
関連 issue ある場合は内容を簡潔に inline 記載 (issue を辿らせない原則)。
詳細は元 issue へ link 参照可、本文と issue 本文の重複は受容。
-->

## 現状 (修正前)

<!--
2-4 文。PR 作成時点でどうなっているか + 期待値とのギャップ。
-->

## 修正内容 (現状 → 期待値)

<!--
bullet list。何をしたか、必要なら file path:line で具体化。
「現状 → 期待値 のギャップを埋める」視点で書く。
関連 issue は `Refs #123` の形で記載 (Closes / Fixes / Resolves キーワード禁止 = Iron Law 4)。
-->
```

- [ ] **Step 4.3: markdownlint 確認**

Run: `bash scripts/check-markdownlint.sh`
Expected: 0 violations。

- [ ] **Step 4.4: Commit**

```bash
git add .github/pull_request_template.md
git commit -m "$(cat <<'EOF'
chore(pr-template): 概要 / 変更点 を 期待値 / 現状 / 修正内容 の 3 section に置換

session-id: eloquent-kalam-0196f5
EOF
)"
```

---

### Task 5: CLAUDE.md に skill 改修 workflow への link 追加

**Files:**

- Modify: `CLAUDE.md` §開発ワークフロー (line ~225)

- [ ] **Step 5.1: 現状確認**

```bash
grep -n '^### ' CLAUDE.md | head -20
```

Expected: `### Iron Law と強制メカニズム` (line ~237) などが見える。`## 開発ワークフロー` 配下に新 link 追加位置を決める。

- [ ] **Step 5.2: link を追加**

`## 開発ワークフロー` 節 (line 225 付近) の `- ユーザー (Idios) が戦略・方針を判断し、Claude は選択肢提示と実装を担う` 行の直後に以下を追加:

```markdown
- skill (`.claude/skills/*/SKILL.md`) 改修 PR は mizchi `empirical-prompt-tuning` protocol に従う。詳細は [`docs/l2-workflow.md` §skill 改修 workflow](docs/l2-workflow.md#skill-改修-workflow-empirical-prompt-tuning-protocol) を参照
```

- [ ] **Step 5.3: markdownlint 確認**

Run: `bash scripts/check-markdownlint.sh`
Expected: 0 violations。

- [ ] **Step 5.4: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(CLAUDE): §開発ワークフロー に skill 改修 workflow への link 追加

session-id: eloquent-kalam-0196f5
EOF
)"
```

---

### Task 6: create-task `eval/requirements.md` update

**Files:**

- Modify: `.claude/skills/create-task/eval/requirements.md`

- [ ] **Step 6.1: 現状確認**

```bash
cat .claude/skills/create-task/eval/requirements.md
```

Expected: シナリオ A (bug 起票) / B (patch release task) / C (deferred task) の 3 件。

- [ ] **Step 6.2: シナリオ B に preamble 検証項目を追加**

`## シナリオ B (patch release 関連 issue、Track 構造判定)` の項目末尾 (B-4 の後) に以下を追加:

```markdown
5. **[critical]** **B-5**: 期待値 section が存在し、2-4 文で「完了後の状態 + 理由」が記述されている (空文・placeholder 残留は ×)
6. **[critical]** **B-6**: 現状 section が存在し、期待値とのギャップが具体的に記述されている
7. **[critical]** **B-7**: ユーザー影響・重要性 section が **1 行で** 位置付けを記述している
```

- [ ] **Step 6.3: シナリオ C に preamble 検証項目を追加**

`## シナリオ C (deferred 状態の issue 起票、release-blocker 撤回後の運用)` の項目末尾 (C-4 の後) に以下を追加:

```markdown
5. **[critical]** **C-5**: 期待値 section が存在し、2-4 文で「完了後の状態 + 理由」が記述されている
6. **[critical]** **C-6**: 現状 section が存在し、期待値とのギャップが具体的に記述されている
7. **[critical]** **C-7**: ユーザー影響・重要性 section が 1 行で位置付けを記述している
```

- [ ] **Step 6.4: シナリオ D (refactor 起票) を新設**

ファイル末尾に以下を追加:

```markdown
---

## シナリオ D (refactor 起票、preamble + ブロッカー section)

モック: ユーザー指示「`gui/src-tauri/src/lib.rs` の spawn site を `tauri-plugin-shell::Command` に移行する refactor を起票、現バージョン scope 外として deferred 付与」。

1. **[critical]** **D-1**: prefix `[refactor]` を選択
2. **[critical]** **D-2**: scope label `l2a-gui` + `deferred` ラベル付与
3. **[critical]** **D-3**: 期待値 section が存在し、2-4 文で「Tauri 2 公式 API への移行後の状態 + 戦略的価値」が記述されている
4. **[critical]** **D-4**: 現状 section が存在し、5 spawn site が `tokio::process::Command` 直接使用の状態とのギャップが記述されている
5. **[critical]** **D-5**: ユーザー影響・重要性 section が 1 行で位置付け (例: 「ユーザー影響なし、メンテ性負債」) を記述
6. **[critical]** **D-6**: ブロッカー section が存在し、`process_util::apply_no_window` / `PROCESS_TRACKER` 再設計などの実装ハードルが記述されている (該当時のみ、不要なら省略可)
7. **[critical]** **D-7**: 該当箇所 / 対応方針 / 関連 section が記載されている
```

- [ ] **Step 6.5: シナリオ E (risk 起票) を新設**

ファイル末尾に以下を追加:

```markdown
---

## シナリオ E (risk 起票、preamble + 顕在化時被害詳細)

モック: ユーザー指示「Dependabot security alert (high) の risk を起票、tauri 2.10.3 の Origin Confusion 脆弱性」。

1. **[critical]** **E-1**: prefix `[risk]` を選択
2. **[critical]** **E-2**: 重複チェック (`gh issue list --search "tauri Origin Confusion"`) を実行
3. **[critical]** **E-3**: 期待値 section が存在し、リスク低減後の状態 (tauri 2.11.1 以降への bump 完了) が記述されている
4. **[critical]** **E-4**: 現状 section が存在し、現バージョン (tauri 2.10.3) と脆弱性の存在が記述されている
5. **[critical]** **E-5**: ユーザー影響・重要性 section が 1 行で被害規模 (例: 「medium、Remote→Local IPC invocation 経路」) を記述
6. **[critical]** **E-6**: 顕在化時の被害詳細 section が存在し、攻撃ベクター・影響範囲が記述されている
7. **[critical]** **E-7**: 該当箇所 / 対応方針 が記載されている
```

- [ ] **Step 6.6: markdownlint 確認**

Run: `bash scripts/check-markdownlint.sh`
Expected: 0 violations。

- [ ] **Step 6.7: Commit**

```bash
git add .claude/skills/create-task/eval/requirements.md
git commit -m "$(cat <<'EOF'
test(create-task): preamble 検証項目を シナリオ B/C に追加、シナリオ D/E (refactor/risk) を新設

empirical prompt tuning の test spec 更新 (SKILL.md 変更前に test を先行整備)。

session-id: eloquent-kalam-0196f5
EOF
)"
```

---

### Task 7: create-task `SKILL.md` update

**Files:**

- Modify: `.claude/skills/create-task/SKILL.md`

- [ ] **Step 7.1: 現状確認**

```bash
cat .claude/skills/create-task/SKILL.md
```

- [ ] **Step 7.2: 手順 3 を改訂**

現在の手順 3:

```text
3. `docs/issue-policy.md` §3 の対応テンプレートに沿ってタイトルと本文を作成する
```

を以下に置き換える:

```text
3. `docs/issue-policy.md` §3 の対応テンプレートに沿ってタイトルと本文を作成する:
   - prefix が `[refactor]` / `[task]` / `[risk]` の場合: **共通 preamble (期待値 / 現状 / ユーザー影響・重要性) を必ず含める**
     - 期待値: ユーザー指示 + 関連 issue/spec/コード読みから「完了後の状態」を 2-4 文で推論
     - 現状: 関連コード or doc を Read/Grep して具体的にギャップを記述
     - ユーザー影響・重要性: 1 行で位置付け (例:「ユーザー影響なし、メンテ性負債」「将来のセキュリティ整合性」)
     - skill は draft を一括生成。ユーザーは手順 5 で修正を指摘
   - prefix が `[bug]` / `[doc]` / `[question]` の場合: 現行どおり (preamble 不要)
```

- [ ] **Step 7.3: 手順 5 を改訂**

現在の手順 5 確認要素:

```text
5. 作成前にユーザーに以下の要素を提示して確認を得る:
   - タイトル（文字数表示付き、例: "33/40 文字"）
   - assignee / ラベル一覧（スコープラベル・優先度ラベル含む）
   - 重複チェック結果（ヒット件数と代表 issue）
   - 本文全文
   - 選択肢: 「はい / 修正箇所を指摘 / やめる」
```

を以下に置き換える:

```text
5. 作成前にユーザーに以下の要素を提示して確認を得る:
   - タイトル（文字数表示付き、例: "33/40 文字"）
   - assignee / ラベル一覧（スコープラベル・優先度ラベル含む）
   - 重複チェック結果（ヒット件数と代表 issue）
   - 本文全文
   - (refactor/task/risk の場合) preamble 3 セクションの中身が空 or placeholder 残留でないことの self-check 結果 (`期待値: 埋め済 / 現状: 埋め済 / 影響: 埋め済` を 1 行で表示)
   - 選択肢: 「はい / 修正箇所を指摘 / やめる」
```

- [ ] **Step 7.4: 「注意事項」section に preamble 必須化規約を追記**

`## 注意事項` セクション末尾に以下を追加:

```markdown
### preamble 必須化規約 (refactor / task / risk)

`refactor` / `task` / `risk` prefix では preamble 3 セクション (期待値 / 現状 / ユーザー影響・重要性) が必須。skill が draft を生成する際:

- 関連 issue / spec / コードを Read/Grep で具体的に読んで埋める
- 推論できない場合は placeholder で起票せず、ユーザーに具体的に聞き返す (例: 「期待値を埋めるための情報が不足しています。完了後にコードがどうあるべきか教えてください」)
- 「ユーザー影響・重要性」は 1 行制約。長くなる場合は他 section に分離: refactor=「ブロッカー」 / risk=「顕在化時被害詳細」

preamble を埋められないことは「issue 化に値する整理ができていない」signal。空欄や曖昧な記述で勝手に埋めない。
```

- [ ] **Step 7.5: markdownlint 確認**

Run: `bash scripts/check-markdownlint.sh`
Expected: 0 violations。

- [ ] **Step 7.6: Commit**

```bash
git add .claude/skills/create-task/SKILL.md
git commit -m "$(cat <<'EOF'
feat(create-task): preamble (期待値 / 現状 / ユーザー影響) を refactor/task/risk で必須化

手順 3 / 5 / 注意事項を改訂。次の commit で mizchi empirical-prompt-tuning protocol を invoke して 2 consecutive clears まで iterate する。

session-id: eloquent-kalam-0196f5
EOF
)"
```

---

### Task 8: Empirical prompt tuning (mizchi protocol)

**Goal:** 改修後 SKILL.md を 5 scenarios (A-E) で iterate し、2 consecutive clears (new unclear=0 + accuracy +3pt 以下 + step ±10% + duration ±15%) まで収束させる。

**Files:**

- Modify (iteratively): `.claude/skills/create-task/SKILL.md`
- Reference (read-only via WebFetch): `https://github.com/mizchi/skills/tree/main/empirical-prompt-tuning`

- [ ] **Step 8.1: mizchi SKILL.md を WebFetch で取得**

```bash
gh api repos/mizchi/skills/contents/empirical-prompt-tuning/SKILL.md \
  -H "Accept: application/vnd.github.raw" > /tmp/mizchi-empirical-prompt-tuning.md
```

Expected: `/tmp/mizchi-empirical-prompt-tuning.md` に SKILL.md 本文が保存される (200+ 行)。**commit しない** (project 内に vendoring 禁止)。

- [ ] **Step 8.2: Iter 0 — description / body 整合性 static check**

`.claude/skills/create-task/SKILL.md` を読み、以下を確認:

- frontmatter `description` が claim する trigger / use case (例: 「全 prefix: bug/doc/refactor/task/question/risk 対応」) と body の実際の scope が一致しているか
- 不整合があれば SKILL.md (description or body) を修正して reconcile

Expected: description が「refactor/task/risk preamble 必須化」を反映している。反映漏れがあれば description に「prefix=refactor/task/risk では preamble 必須」を追記。

- [ ] **Step 8.3: Baseline 5 scenarios を fresh subagent で並列 dispatch**

`.claude/skills/create-task/eval/requirements.md` のシナリオ A-E に対して、Task tool で fresh subagent を 5 個並列 dispatch する (single message に 5 つの Agent tool call)。

各 subagent への prompt 構造 (mizchi 仕様、§Subagent invocation contract 参照):

```text
You are an executor reading `.claude/skills/create-task/SKILL.md` with a blank slate.

## Target prompt
<.claude/skills/create-task/SKILL.md の全文 paste>

## Scenario
<シナリオ X の「モック: ユーザー指示」を 1 段落で paste>

## Requirements checklist
<シナリオ X の [critical] 項目を全て paste>

## Task
1. Follow the target prompt to execute the scenario and produce the deliverable (issue 本文 + labels + title)。`gh issue create` は dry run (stdout に出力するだけ、実起票しない)。
2. On completion, respond with the report structure below.

## Report structure
- Deliverable: issue 本文 + labels + title
- Requirement achievement: ○ / × / partial (理由付き) for each item
- Trace: Understanding / Planning / Execution / Formatting のいずれが stuck/skipped か (全 OK なら "Trace: all OK")
- Unclear points (structured): each issue ごとに 3 行 (Issue / Cause / General Fix Rule)
- Discretionary fill-ins: 指示で fix されていない判断点 (bullets)
- Retries: 同一判断を再考した回数と理由
```

Expected: 5 subagents から 5 reports を回収。各 report の Deliverable と Requirement achievement、tool_uses (Agent meta から)、duration_ms を記録。

- [ ] **Step 8.4: Two-sided evaluation を実施**

各 scenario について以下を記録:

| Scenario | Success/Failure | Accuracy | steps (tool_uses) | duration (ms) | retries | Weak phase | Unclear points (count) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A (bug) | ? | ?% | ? | ? | ? | ? | ? |
| B (patch task) | ? | ?% | ? | ? | ? | ? | ? |
| C (deferred task) | ? | ?% | ? | ? | ? | ? | ? |
| D (refactor) | ? | ?% | ? | ? | ? | ? | ? |
| E (risk) | ? | ?% | ? | ? | ? | ? | ? |

判定:

- Success = [critical] 全 ○、Failure = 1 つでも ×
- 各 unclear point は structured (Issue / Cause / General Fix Rule)
- tool_uses 1 scenario だけ 3-5x 外れ値 → 自己完結性低下 signal (mizchi §`tool_uses` 解釈)

- [ ] **Step 8.5: Failure pattern ledger を初期化**

`.claude/skills/create-task/eval/reports/empirical-tuning-ledger.md` を新規作成:

```markdown
# create-task SKILL.md empirical-prompt-tuning ledger

iter ごとに pattern を累積する。同じ `General Fix Rule` が再出現したら "Seen in" を update して、既存 fix が prevent しなかった理由を記録する。

## Patterns

(iter 1 以降で追加)
```

- [ ] **Step 8.6: Iteration loop (Iter 1, 2, ...)**

以下を 2 consecutive clears (new unclear=0 + accuracy +3pt 以下 + step ±10% + duration ±15%) まで繰り返す:

1. **Step 8.6.a: 構造化 reflection から最も影響大の theme を 1 つ選び SKILL.md を修正**
   - 「one theme per iteration」原則
   - 修正前に「この修正が requirements checklist のどの判断 wording を satisfy するか」を明文化
   - failure pattern ledger を scan、既存 fix が prevent しなかった理由を記録してから新 entry 追加 (or 既存 entry の "Seen in" update)

2. **Step 8.6.b: Commit (Iter N)**

   ```bash
   git add .claude/skills/create-task/SKILL.md .claude/skills/create-task/eval/reports/empirical-tuning-ledger.md
   git commit -m "$(cat <<'EOF'
   test(create-task): empirical-prompt-tuning Iter N - <theme>
   
   - Pattern applied: <pattern name>
   - Fix satisfies: <requirements checklist の項目>
   
   session-id: eloquent-kalam-0196f5
   EOF
   )"
   ```

3. **Step 8.6.c: Re-dispatch fresh subagents で 5 scenarios を再実行**
   - 必ず **fresh subagent** (同じ agent を reuse 禁止、前 iter の改善を学習済みのため)

4. **Step 8.6.d: 収束判定**
   - 2 consecutive clears → 次 step
   - 新 unclear point ≥ 1 → Iter N+1 へ
   - 3+ iter で unclear point 減らず → divergence、設計に戻して spec 見直し
   - plateau (1-2 unclear point から減らない) → variant exploration (Conservative + Exploratory の 2 variant を fresh subagent 並列 dispatch、accuracy 高い方を採用)

- [ ] **Step 8.7: Hold-out scenario で overfitting check**

収束判定時点で、A-E と異なる 1 つの hold-out scenario を追加 (例: 「`l2a-gui` scope の bug 起票で preamble 不要パターン」) し、fresh subagent で実行。

判定: accuracy が直近平均から 15 点以上 drop した場合は overfitting。baseline scenario 設計に戻り、edge を増やして再実施。

- [ ] **Step 8.8: 最終 Iteration table を `.claude/skills/create-task/eval/reports/empirical-tuning-final.md` に記録**

```markdown
# create-task SKILL.md empirical-prompt-tuning Final Report

session-id: eloquent-kalam-0196f5
Iteration count: N
Final convergence: 2 consecutive clears at Iter N-1 / N
Hold-out overfit check: PASS / FAIL

## Final Iteration table

(per-scenario success / accuracy / steps / duration / retries / weak phase / unclear points を全 iter で記載)

## Structured reflection summary

(iter ごとに発見された Issue / Cause / General Fix Rule の累積)

## Ledger final state

(`empirical-tuning-ledger.md` の snapshot)
```

- [ ] **Step 8.9: Final commit**

```bash
git add .claude/skills/create-task/eval/reports/empirical-tuning-final.md
git commit -m "$(cat <<'EOF'
test(create-task): empirical-prompt-tuning final report (2 consecutive clears)

Iter N で 収束、hold-out overfit check PASS。詳細は eval/reports/empirical-tuning-final.md。

session-id: eloquent-kalam-0196f5
EOF
)"
```

---

### Task 9: Final verification + PR creation

**Files:**

- 全変更 file の最終確認

- [ ] **Step 9.1: 全 markdownlint pass を確認**

Run: `bash scripts/check-markdownlint.sh`
Expected: 0 violations (全 .md file)。

- [ ] **Step 9.2: PR 作成 Pre-flight (Iron Law 6 サブ条) を実施**

`docs/l2-workflow.md` §PR 作成 Pre-flight に従う 6 step (Step 0-5):

```bash
# Step 0: ハードゲート (<1s、build/verify の前)
gh pr list --search "issue-pr-clarity preamble" --state open

# Step 1: base 同期
git fetch origin develop-0.3.0  # current base

# Step 2: 取り込み未済 commit 列挙
git log HEAD..origin/develop-0.3.0 --oneline

# Step 3: touched files 交差判定
git diff --name-only origin/develop-0.3.0..HEAD

# Step 4: 並行 PR 重複再確認
gh pr list --search "preamble issue PR" --state all

# Step 5: /codex:adversarial-review (focus: Iron Law 3 scope / encoding / docs 整合性)
```

Expected: Step 0/4 で 0 hits、Step 2 で取り込み未済なし or 取り込み済、Step 5 で needs-attention finding なし or 解消済み。

- [ ] **Step 9.3: PR 本文を新 template に従って起票**

```bash
gh pr create \
  --base develop-0.3.0 \
  --title "feat(docs): issue / PR に期待値 / 現状 / 修正内容 preamble を必須化 + skill 改修 workflow 整備" \
  --body-file - <<'EOF'
## 期待値 (あるべき姿)

refactor / task / risk の issue と すべての PR の冒頭で「期待値 / 現状 / ユーザー影響 (issue) / 修正内容 (PR)」が 3 section の独立見出しで明示され、後から読んでも目的・現状ギャップが一目で分かる。create-task skill は新 template に沿って自動 draft し、skill 改修 PR は mizchi empirical-prompt-tuning protocol に従う。

## 現状 (修正前)

issue template (refactor / task / risk) は「概要 / 該当箇所 / 問題 / 対応方針」中心で、期待値・現状・ユーザー影響が独立 section にない。PR template も「概要 / 変更点」のみで、期待値→現状→修正内容の流れが見えない。skill 改修 PR では mizchi protocol が運用化されていない。

## 修正内容 (現状 → 期待値)

- `docs/l2-workflow.md`: §skill 改修 workflow + §PR body 規約 の 2 節を追加
- `docs/issue-policy.md`: §3 内 refactor / task / risk テンプレに preamble (期待値 / 現状 / ユーザー影響・重要性) を必須化、refactor の「問題」を「ブロッカー」に、risk の「問題」を「顕在化時被害詳細」に rename
- `.github/pull_request_template.md`: 冒頭 `## 概要` + `## 変更点` を `## 期待値` + `## 現状` + `## 修正内容` の 3 section に置換
- `CLAUDE.md`: §開発ワークフロー に l2-workflow.md §skill 改修 workflow への link 追加
- `.claude/skills/create-task/eval/requirements.md`: シナリオ B/C に preamble 検証項目追加、シナリオ D (refactor) / E (risk) 新設
- `.claude/skills/create-task/SKILL.md`: 手順 3 / 5 / 注意事項に preamble 必須化規約を追記
- `.claude/skills/create-task/eval/reports/empirical-tuning-{ledger,final}.md`: mizchi protocol で 5 scenarios を 2 consecutive clears まで iterate した結果を記録

Refs spec: `docs/superpowers/specs/2026-05-18-issue-pr-clarity-preamble-design.md`
Refs plan: `docs/superpowers/plans/2026-05-18-issue-pr-clarity-preamble-plan.md`

## 受け入れ条件

(spec §Acceptance criteria を逐条 paste して各項目に対応 diff を明示)

## PR チェックリスト (Iron Law 遵守確認)

(template に従い記入)

### Iron Law 6: PR 作成前検証

#### ベース同期確認

- PR 作成時の base HEAD: <git rev-parse origin/develop-0.3.0 の出力>
- PR head の base 取り込み: 取り込み不要 (base 進行なし) / merge 済み (commit <sha>)
- 直近マージ PR の影響: なし
- 並行 PR 確認: なし

#### Self-Test Report (machine-verified)

- [x] bash scripts/check-markdownlint.sh (0 violations)
- [x] N/A: ruff check (python-core 変更なし)
- [x] N/A: pyright (python-core 変更なし)
- [x] N/A: pytest (python-core 変更なし)
- [x] N/A: cd gui && npm run lint (gui 変更なし)
- [x] N/A: cd gui && npm run typecheck (gui 変更なし)
- [x] N/A: cd gui && npm test (gui 変更なし)
- [x] N/A: cd gui && npm run build (gui 変更なし)
- [x] N/A: cargo check (gui-rust 変更なし)
- [x] N/A: Invoke-Pester (installer 変更なし)

#### empirical prompt tuning (create-task SKILL.md 改修分)

(Iteration table を `.claude/skills/create-task/eval/reports/empirical-tuning-final.md` から要約 paste)

#### 関連ドキュメント / マトリクス更新

- [x] CLAUDE.md / docs/l2-workflow.md の更新済
- [x] 出力書式変更なし、cli-spec.md 更新不要
- [x] CLI オプション追加なし、output-spec.md 更新不要

#### 実機検証 (machine-unverifiable)

- 該当なし (gpu_detector.py / audio/ / video/detector.py / gui/ 変更なし、doc + skill のみ)

## 関連

- Refs #742 (本 design の trigger となった例)
- Base branch: `develop-0.3.0`
- Session: `eloquent-kalam-0196f5`
EOF
```

Expected: PR 作成成功。PR URL を確認して `/iterate-review <PR#>` を invoke して review-fix loop に入る (別タスク、本 plan の scope 外)。

- [ ] **Step 9.4: PR URL を user に報告**

最後に PR URL を text response として user に提示。次のステップ (`/iterate-review` invoke or マージ判断) を user に委ねる。

---

## Self-Review

**Spec coverage check** (spec の各 §Acceptance criteria に対応する task を確認):

- spec §Acceptance criteria の各項目に対して:
  - issue-policy.md §3 改修 → Task 3
  - create-task SKILL.md 改修 → Task 7
  - create-task eval/requirements.md 改修 → Task 6
  - PR template 改修 → Task 4
  - l2-workflow.md 2 節追加 → Task 1 + Task 2
  - CLAUDE.md link → Task 5
  - empirical prompt tuning → Task 8
  - markdownlint 0 violations → 各 task の Step X.6 + Task 9 Step 9.1
  - spec doc 存在 → 既に worktree に存在 (本 plan の前段で書き出し済)

**Placeholder scan**: TBD / TODO / 「fill in」/「similar to Task N」なし。

**Type consistency**: section 名 (`## 期待値`, `## 現状`, `## ユーザー影響・重要性`, `## 修正内容`) は spec と plan で一致。

**Iteration loop の placeholder 性**: Task 8 のループ部分は「同じ手順を iter ごとに繰り返す」性質上、N の値が事前不明だが、各 step の中身は完全に specify されている。

---

## Out-of-scope (本 plan で扱わない)

- 既存 open issue / PR の遡及書き換え (forward-only)
- `.github/ISSUE_TEMPLATE/*.yml` (Issue Forms) の改修
- `pr-checklist.yml` workflow / `check-pr-checklist.js` への新 section 取り込み
- mizchi/skills の vendoring (license 未設定)
- `/iterate-review` ループ (Task 9 で PR 作成までで本 plan は完了)
