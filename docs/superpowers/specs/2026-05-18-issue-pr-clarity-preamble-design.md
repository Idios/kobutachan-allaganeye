# Issue/PR Clarity Preamble Design

- **Date**: 2026-05-18
- **Status**: spec (brainstorming 完了 → writing-plans へ)
- **Author**: Idios (brainstorm with Claude)
- **Worktree / session-id**: `eloquent-kalam-0196f5`

## 1. Background

`#742` ([refactor] 5 spawn site を tauri-plugin-shell::Command に移行) について「期待値に対して現状どうなっているか」をユーザーが説明要求し、Claude が以下の構造で再構成して説明したところ「これが望ましい issue/PR の形」と認識された:

1. **期待値 (あるべき姿)** — 完了後のコード or 状態がどうあるべきか、なぜ目指すか
2. **現状** — 今どうなっているか、期待値とのギャップ
3. **ユーザー影響・重要性** — 1 行で位置付け
4. **(refactor のみ) ブロッカー** — なぜ現状で止まっているか

既存 issue template (`docs/issue-policy.md` §3) と PR template (`.github/pull_request_template.md`) は「概要 / 該当箇所 / 問題 / 対応方針 / Self-Test Report」中心で、期待値・現状・ユーザー影響 が独立 section にない。結果、技術的内容に終始し、後から読んだとき「何を目指すのか・なぜ重要か」が一目で分からない。

PR 側も同構造の問題があり、「期待値に対する現状と、現状に対する修正内容が一目で分からない」とユーザーから指摘あり。

## 2. Goals

- **G1**: `refactor` / `task` / `risk` の 3 prefix の issue template に「期待値 / 現状 / ユーザー影響・重要性」共通 preamble を必須化
- **G2**: すべての PR で「期待値 / 現状 / 修正内容」3 section preamble を本文 inline 必須化 (issue ref ありでも本文に簡潔記載、issue を辿らせない)
- **G3**: `create-task` skill が新 template に沿って自動 draft (Claude 推論で埋め、ユーザーが手順 5 で修正)
- **G4**: skill 改修 PR で mizchi `empirical-prompt-tuning` protocol を必須適用 (project standing rule、URL 参照のみ、vendoring しない)

## 3. Non-goals

- `bug` / `doc` / `question` template の改修 (既に「現状 / 問題」が分離されている)
- 既存 open issue / PR の遡及書き換え (forward-only)
- `.github/ISSUE_TEMPLATE/*.yml` (GitHub Issue Forms) の改修
- `pr-checklist.yml` workflow / `check-pr-checklist.js` への新 section 取り込み (ヒューマンレビュー前提)
- mizchi/skills の vendoring (license 未設定のため URL 参照のみ)

## 4. Design

### 4.1 Issue template (`docs/issue-policy.md` §3)

**共通 preamble (refactor / task / risk すべて必須、概要直後に挿入)**:

```markdown
## 期待値 (あるべき姿)

<2-4 文。完了後にコード or 状態がどうあるべきか + なぜそれを目指すかの理由>

## 現状

<2-4 文。今どうなっているか + 期待値とのギャップ>

## ユーザー影響・重要性

<1 行で位置付け。例:「ユーザー影響なし、メンテ性負債」「ユーザー直結機能の前提条件」>
```

**refactor 全体構造**:

| 順 | 旧 | 新 | 変更 |
| --- | --- | --- | --- |
| 1 | 概要 | 概要 (1-2 文) | 規約明文化 |
| 2 | 該当箇所 | **期待値 (あるべき姿)** | 新規 |
| 3 | 問題 | **現状** | 新規 |
| 4 | 対応方針 | **ユーザー影響・重要性** | 新規 |
| 5 | — | 該当箇所 | 移動 |
| 6 | — | **ブロッカー / なぜ現状で止まっているか** | 旧「問題」を rename + 役割変更 (実装ハードル・後回し理由)、不要なら省略可 |
| 7 | — | 対応方針 | 維持 |
| 8 | — | 受け入れ条件 (任意) | 維持 |
| 9 | — | 関連 (任意、umbrella / spec / 関連 PR) | 新規 |

**task 全体構造**:

| 順 | 旧 | 新 | 変更 |
| --- | --- | --- | --- |
| 1 | 概要 | 概要 (1-2 文) | — |
| 2 | 背景 | **期待値 (あるべき姿)** | 新規 |
| 3 | 確認項目 | **現状** | 新規 |
| 4 | 対応方針 | **ユーザー影響・重要性** | 新規 |
| 5 | — | 背景 (任意) | 役割明確化: 経緯 / 依存タスク / 関連 issue (期待値とは別) |
| 6 | — | 確認項目 / 作業項目 | 維持 |
| 7 | — | 対応方針 | 維持 |
| 8 | — | 受け入れ条件 (任意) | 維持 |

**risk 全体構造**:

| 順 | 旧 | 新 | 変更 |
| --- | --- | --- | --- |
| 1 | 概要 | 概要 (1-2 文) | — |
| 2 | 現状 | **期待値 (あるべき姿)** | 新規 (リスク低減後の状態) |
| 3 | 問題 | **現状** | 既存「現状」を統合・拡張 |
| 4 | 対応方針 | **ユーザー影響・重要性** | 新規 (1 行 summary of 被害) |
| 5 | — | 該当箇所 (任意) | 新規 |
| 6 | — | **顕在化時の被害詳細** | 旧「問題」を rename (具体的被害ストーリー、攻撃ベクター) |
| 7 | — | 対応方針 | 維持 |
| 8 | — | 受け入れ条件 (任意) | 維持 |

**必須 / 任意の規約**:

- 「期待値」「現状」「ユーザー影響・重要性」の 3 つは **必須**。書けないなら起票しない (= issue 化に値する整理ができていない signal)
- 「ユーザー影響・重要性」は必ず **1 行**。長くなる場合は別 section に分離 (refactor=ブロッカー / risk=顕在化時被害詳細)
- 「ブロッカー」「該当箇所」「関連」「受け入れ条件」「背景」は **任意**。該当しなければ省略可

### 4.2 `create-task` skill (`.claude/skills/create-task/SKILL.md`)

**手順 3 (テンプレ適用) の改訂**:

- prefix が `refactor` / `task` / `risk` の場合: 共通 preamble (期待値 / 現状 / ユーザー影響・重要性) を必ず含める
  - 期待値: ユーザー指示 + 関連 issue/spec/コード読みから「完了後の状態」を 2-4 文で推論
  - 現状: 関連コード or doc を Read/Grep して具体的にギャップを記述
  - ユーザー影響・重要性: 1 行で位置付け
  - skill は draft を一括生成。ユーザーは手順 5 で修正を指摘
- prefix が `bug` / `doc` / `question` の場合: 現行どおり (preamble 不要)

**手順 5 (確認) の改訂**:

- 既存要素に追加: `refactor`/`task`/`risk` の場合 preamble 3 セクションの中身が空 or placeholder 残留でないことを self-check
- skill が情報不足で埋められない場合は、ユーザーに具体的に聞き返す (placeholder のまま起票しないゲート)

**注意事項 追記**:

```text
注意: refactor/task/risk prefix では preamble 3 セクション (期待値 / 現状 / ユーザー影響・重要性) が必須。
これらを埋められない場合は「issue 化に値する整理ができていない」signal なので、ユーザーに
情報補完を依頼する (自分で空欄や曖昧な記述で埋めない)。
```

### 4.3 eval/requirements.md (`.claude/skills/create-task/eval/requirements.md`)

**既存シナリオの拡張**:

- シナリオ A (bug 起票): 変更なし (regression check)
- シナリオ B (patch release task): preamble 3 section [critical] 検証項目を追加 (B-5/B-6/B-7)
- シナリオ C (deferred task): 同上 (C-5/C-6/C-7)

**新シナリオ**:

- シナリオ D (refactor 起票): preamble 3 section + ブロッカー section (該当時) + 該当箇所 + 対応方針 + 関連
- シナリオ E (risk 起票): preamble 3 section + 顕在化時の被害詳細 + 対応方針

**[critical] 項目の例**:

- 期待値 section が存在し、2-4 文で「完了後の状態 + 理由」が記述されている (空文・placeholder 残留は ×)
- 現状 section が存在し、期待値とのギャップが具体的に記述されている
- ユーザー影響・重要性 section が **1 行で** 位置付けを記述している

### 4.4 PR template (`.github/pull_request_template.md`)

`## 概要` + `## 変更点` の 2 section を **`## 期待値` / `## 現状` / `## 修正内容` の 3 section** に置き換え。

新構造:

```markdown
## 期待値 (あるべき姿)

<!-- 2-4 文。この PR がマージされた後にコードベース or 動作がどうあるべきか + なぜ目指すか。
     関連 issue ある場合は内容を簡潔に inline 記載 (issue を辿らせない原則)。 -->

## 現状 (修正前)

<!-- 2-4 文。PR 作成時点でどうなっているか + 期待値とのギャップ。 -->

## 修正内容 (現状 → 期待値)

<!-- bullet list。何をしたか、必要なら file path:line で具体化。
     既存「変更点」と同じ位置付けだが「現状 → 期待値 のギャップを埋める」視点で書く。 -->

## 受け入れ条件

(以下既存: PR チェックリスト / 関連 / 備考)
```

**issue ref 運用**:

- 関連 issue がある場合も期待値 / 現状 を PR 本文に**簡潔に inline 記載** (issue を辿らせない)
- 詳細は issue link で参照可、PR 本文と issue 本文の重複は受容

**release / meta PR の解釈例** (PR #774 のようなケース):

```markdown
## 期待値 (あるべき姿)
v0.2.1 patch release が出て、security alerts 5 件と deferred UX issue 5 件が解消されている。

## 現状 (修正前)
develop-0.2.1 で 10 PRs 分の修正が積まれ統合準備完了、main は未統合のため security alerts が露呈状態。

## 修正内容 (現状 → 期待値)
- Track A: Dependabot security alerts 3 件解消 (#760) + 2 件 deferred
- Track B-1/B-2/B-3/B-4: 各 UX issue 解消
- Track C: security-audit.yml CI gate 追加
- Track D: version bump + CHANGELOG
```

### 4.5 docs/l2-workflow.md

**追記する 2 節**:

#### 4.5.1 PR body 規約 (期待値 / 現状 / 修正内容)

既存「PR 作成ルール」付近に新節を追加:

```text
## PR body 規約 (期待値 / 現状 / 修正内容)

すべての PR で本文冒頭に以下 3 section を inline 必須化する:

- ## 期待値 (あるべき姿): 2-4 文
- ## 現状 (修正前): 2-4 文
- ## 修正内容 (現状 → 期待値): bullet list

issue ref がある PR も、期待値 / 現状 は PR 本文に簡潔に inline 記載 (issue を辿らせない)。
詳細は元 issue へ link 参照可、重複は受容。

release / meta PR (複数 PR 統合) も同構造で解釈する。
```

#### 4.5.2 skill 改修ワークフロー (既存節を enhance、mizchi protocol URL 参照)

**実装時の発見と修正**: 当初は「新節追加」を計画していたが、`docs/l2-workflow.md` 既存の `## skill 改修ワークフロー (empirical-prompt-tuning)` 節と完全に重複することが Task 1 spec review で発覚 (commit `8fb584e` revert → `ec6950f` で既存節 enhance に方針変更)。本 §は実装後の実態に合わせて記述。

既存節 `## skill 改修ワークフロー (empirical-prompt-tuning)` に以下 4 点を enhance:

A. 経緯 section の mizchi URL を chezmoi-dotfiles 旧パスから `mizchi/skills` 新パスへ修正
B. 新 sub-section `### 上流参照 (mizchi protocol を直接読む)` を 適用対象 と How to apply の間に挿入 (gh api 取得 command + offline ハンドリング)
C. How to apply Step 6「打ち切り基準」を mizchi 規範の定量 threshold (2 consecutive clears + accuracy +3pt 以下 + step ±10% + duration ±15%) に拡張
D. 新 sub-section `### Iron Law 6 路線 / Self-Test Report integration` を How to apply と 経緯 の間に挿入 (Self-Test Report Iteration table 必須、trivial wording fix の例外、`/review-pr` blocker 扱い)

vendoring は禁止 (license 未設定)、改修者が都度 WebFetch / gh api で参照する運用とする。

### 4.6 CLAUDE.md

§開発ワークフロー or §PR 作成ルール に skill 改修 workflow への 1 行 link 追記のみ (内容本体は l2-workflow.md):

```text
詳細 skill 改修 workflow は `docs/l2-workflow.md` §「skill 改修 workflow」 を参照。
```

## 5. Empirical Prompt Tuning Protocol (mizchi 由来 URL 参照)

本 spec の create-task skill 改修部分は、mizchi protocol に従って fresh subagent dispatch で iterate する。

**Protocol 概要** (上流の SKILL.md 全文を WebFetch で参照):

- Iter 0: description / body 整合性 static check
- baseline: 2-3 シナリオ準備 ([critical] tag 必須)
- fresh subagent dispatch (Task tool、self-reread 禁止)
- two-sided evaluation: 構造化 reflection (Issue / Cause / General Fix Rule) + 定量 metric (tool_uses / duration_ms / retry count)
- one theme per iteration
- 2 consecutive clears で stop
- failure pattern ledger 累積

**本 spec の閉ループ適用**:

- 改修後の SKILL.md を 5 scenarios (A-E) で iterate
- 2 consecutive clears まで
- 結果を PR Self-Test Report の「empirical prompt tuning」section に Iteration table で記録

## 6. Migration & Rollout

- **forward-only**: 本 PR マージ後の新規 issue / 新規 PR のみ新形式適用
- 既存 open issue / PR は touched しない (Iron Law 2 の bulk 操作コストが効果に見合わない)
- 手動 `gh issue create` / `gh pr create` は新 template に従う「自己責任」運用、強制機構は持たない
- create-task skill 経由起票は自動で新 template になる
- 新旧形式 PR の混在期は許容、移行日を docs/l2-workflow.md に明記

## 7. Verification

| チェック | 対象 | コマンド |
| --- | --- | --- |
| markdownlint | 全 .md 変更 | `bash scripts/check-markdownlint.sh` |
| empirical prompt tuning | create-task SKILL.md 改修 (4.2/4.3 通り) | WebFetch で mizchi protocol 参照 → fresh subagent で 5 scenarios → 2 consecutive clears |
| 機械検証なし | issue-policy.md / l2-workflow.md / CLAUDE.md / PR template 改修 (doc のみ) | markdownlint pass + 設計レビュー |

実機検証 (Iron Law 6) 不要 (Python / GUI / installer ロジック変更なし、doc + skill のみ)。

## 8. Risks

| Risk | 対策 |
| --- | --- |
| skill が期待値を推測で埋めたとき、ユーザーがずれに気づかず起票 | empirical prompt tuning で「placeholder 残留 / 中身空」検出を [critical] 化 |
| 古い template の issue と新 template の issue が混在し、読み手が混乱 | l2-workflow.md に移行日と適用範囲を明記 |
| mizchi/skills 上流が変更されると protocol が変わる | PR ごとに WebFetch 参照、protocol diff が大きい場合は AskUserQuestion で確認 |
| PR 本文の期待値・現状記載が issue と重複し冗長になる | user 決定で重複を受容 (一目で分かる優先) |

## 9. Touched files (planning hint、実装 plan で精緻化)

| ファイル | 種別 | 規模 |
| --- | --- | --- |
| `docs/issue-policy.md` | 改修 (§3 内 3 template 書き換え) | 中 (40-80 行) |
| `.claude/skills/create-task/SKILL.md` | 改修 (手順 3 / 5 / 注意事項) | 小 (10-20 行) |
| `.claude/skills/create-task/eval/requirements.md` | 改修 (B/C に追加 + D/E 新設) | 中 (30-50 行) |
| `.github/pull_request_template.md` | 改修 (冒頭 2 section → 3 section 置換) | 小 (10-20 行) |
| `docs/l2-workflow.md` | 改修 (2 節追記) | 中 (40-60 行) |
| `CLAUDE.md` | 改修 (link 追加のみ) | 極小 (1-2 行) |
| `docs/superpowers/specs/2026-05-18-issue-pr-clarity-preamble-design.md` | 新規 (本 doc) | 中 (本ファイル) |
| `docs/superpowers/plans/2026-05-18-issue-pr-clarity-preamble-plan.md` | 新規 (writing-plans で生成) | 中 |

## 10. Phase 分割の検討

`docs/refactor-pattern.md` §1 適用条件 (touched files > 30 / diff > 1000 line) との照合:

- touched files: 7 file (含 design / plan)
- diff 規模: 中 (200-400 行想定)
- → **単一 PR で十分、Phase 分割不要**

## 11. Open questions (writing-plans 段階で確定)

- create-task SKILL.md の AskUserQuestion option list / placeholder 文言の具体化
- l2-workflow.md の節挿入位置 (どの既存節の前後に置くか)
- empirical prompt tuning iteration 中の SKILL.md 修正粒度 (1 iter 1 fix vs 関連 micro-fix bundling)
- 既存 open issue で「気になる代表例」をユーザー判断で個別に書き直すか (forward-only 例外)

## Related

- Issue [#742](https://github.com/Idios/kobutachan-allaganeye/issues/742) (本 design の trigger となった例)
- mizchi/skills empirical-prompt-tuning: <https://github.com/mizchi/skills/tree/main/empirical-prompt-tuning>
- `docs/refactor-pattern.md` (Phase 分割条件 reference)
- `docs/l2-workflow.md` (PR 作成 Pre-flight / Self-Test Report 規約)
- `.claude/hooks/session-start.sh` Iron Law (1-6)

## Acceptance criteria

- [ ] `docs/issue-policy.md` §3 の refactor / task / risk テンプレが §4.1 表どおりに更新されている
- [ ] `.claude/skills/create-task/SKILL.md` の手順 3 / 5 / 注意事項が §4.2 のとおり更新されている
- [ ] `.claude/skills/create-task/eval/requirements.md` にシナリオ B/C 拡張 + D/E 新設が含まれている (§4.3)
- [ ] `.github/pull_request_template.md` の冒頭 2 section が §4.4 の 3 section に置き換わっている
- [ ] `docs/l2-workflow.md` に §4.5.1 (PR body 規約) と §4.5.2 (skill 改修 workflow) が追加されている
- [ ] `CLAUDE.md` から l2-workflow.md §skill 改修 workflow への link が張られている
- [ ] empirical prompt tuning が create-task skill 改修部分で 5 scenarios A-E で 2 consecutive clears まで iterate され、PR Self-Test Report に Iteration table が記録されている
- [ ] markdownlint が全 .md 変更で 0 violations
- [ ] 本 spec doc が `docs/superpowers/specs/2026-05-18-issue-pr-clarity-preamble-design.md` に存在

作成: eloquent-kalam-0196f5
