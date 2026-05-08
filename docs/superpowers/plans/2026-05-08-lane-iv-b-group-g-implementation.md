# Lane IV-b: Group G (workflow / CI / docs) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** v0.2.0 release gate に向けて workflow / CI / docs まわりの 3 件 (#624 / #458 / #682) を 1 PR で統合実装する。

**Architecture:**

- `pr-checklist.yml` の inline script を `.github/scripts/check-pr-checklist.js` に切り出し、`## 受け入れ条件` allowlist で section-aware 化 (Node.js native test runner で unit test)。
- `bug_report.yml` を field id 凍結 + #669 連動先取りで微修正 (placeholder / description / 上部 markdown 案内に ErrorModal 自動埋込 note 追加)。
- `review-pr` SKILL.md に「同種パターン全件 sweep 規約」節を新規追加 + Red Flag 表更新 + 「よくある失敗」表に PR #675 事例追記。empirical-prompt-tuning (general-purpose / sonnet / 3 並列 / 中央値 1 + edge 2) で 2 Iteration 検証。

**Tech Stack:** GitHub Actions (`actions/github-script@v7` + `actions/checkout@v4`) / Node.js native test runner (`node --test`) / GitHub Issue Forms YAML / Claude Skill markdown / empirical-prompt-tuning subagent dispatch (general-purpose, model: sonnet)

**Spec:** [`docs/superpowers/specs/2026-05-08-lane-iv-b-group-g-design.md`](../specs/2026-05-08-lane-iv-b-group-g-design.md)

**着手順序根拠 (spec §8.2):** #682 SKILL.md sweep 規約を**先**に整備することで、本 PR 自身の `/review-pr` が新しい規約で動作し、同種パターン sweep を本 PR の review にも適用できる状態にする。

---

## File Structure

### 新規 file

| path | 責務 |
| --- | --- |
| `.github/scripts/check-pr-checklist.js` | section-aware checker 本体 (`countAcceptanceCriteriaCheckboxes` 関数 + module export) |
| `.github/scripts/check-pr-checklist.test.js` | Node.js native test runner (`node --test`) で 7 ケース検証 |
| `.github/workflows/check-pr-checklist-test.yml` | CI で `node --test` を走らせる workflow |
| `.claude/skills/review-pr/eval/scenario_e_sweep_central.md` | sweep 中央値シナリオ (単一 root cause 散在) |
| `.claude/skills/review-pr/eval/scenario_e_sweep_edge_mixed.md` | sweep edge 1 シナリオ (複数 root cause 混在、PR #675 再現) |
| `.claude/skills/review-pr/eval/scenario_e_sweep_edge_doc_only.md` | sweep edge 2 シナリオ (doc-only 内の literal 散在) |
| `.claude/skills/review-pr/eval/reports/iter_0_sweep_central_baseline.md` | Iteration 0 baseline 結果 (中央値) |
| `.claude/skills/review-pr/eval/reports/iter_0_sweep_edge_mixed_baseline.md` | Iteration 0 baseline 結果 (edge mixed) |
| `.claude/skills/review-pr/eval/reports/iter_0_sweep_edge_doc_only_baseline.md` | Iteration 0 baseline 結果 (edge doc-only) |
| `.claude/skills/review-pr/eval/reports/iter_1_sweep_central_revaluation.md` | Iteration 1 revaluation 結果 (中央値、新規 subagent) |
| `.claude/skills/review-pr/eval/reports/iter_1_sweep_edge_mixed_revaluation.md` | Iteration 1 revaluation 結果 (edge mixed、新規 subagent) |
| `.claude/skills/review-pr/eval/reports/iter_1_sweep_edge_doc_only_revaluation.md` | Iteration 1 revaluation 結果 (edge doc-only、新規 subagent) |
| `.claude/skills/review-pr/eval/reports/summary_sweep.md` | Iteration 0/1 比較サマリ (`[critical]` 達成率) |

### 修正 file

| path | 修正概要 |
| --- | --- |
| `.github/workflows/pr-checklist.yml` | inline script → `actions/checkout@v4` + `require('./.github/scripts/check-pr-checklist.js')` 化 |
| `.github/ISSUE_TEMPLATE/bug_report.yml` | 上部 markdown 案内に ErrorModal note 1 行追加、`actual` / `log_file_attachment` の description 微修正 (合計 5-10 行未満の diff) |
| `.claude/skills/review-pr/SKILL.md` | 「同種パターン sweep 規約」節を Step 5b 内 or 直後に新規追加、Red Flag 表 (line 504) と 「よくある失敗」表 (line 522) に追記 |
| `.claude/skills/review-pr/eval/requirements.md` | シナリオ E / E2 / E3 の `[critical]` 要件群を追記 (既存 シナリオ A-D の format に倣う) |

---

## Task 1: #682 前段階事例調査 (Explore agent 3 並列)

**目的:** memory `feedback_skill_revision_empirical.md` の「指摘ラウンドが多かった実在 PR を 3 本ピックアップし、Explore agent 並列で指摘パターンを抽出してからモック設計」原則に従う。

**Files:**

- Create: `.claude/skills/review-pr/eval/scenario_e_sweep_research.md` (research メモ)

- [ ] **Step 1: Explore agent 3 並列 dispatch (1 message で 3 tool call、相互依存なし)**

3 Agent を独立 task として 1 message で同時 dispatch (Explore は read 中心のため `run_in_background: false` で短時間完結):

**Agent A** — 過去 PR の round 数集計:

```yaml
subagent_type: Explore
description: "PR review round count survey"
prompt: |
  目的: review-pr で Round 2+ に divergence した過去 PR の特定。

  手順:
  1. `gh pr list --base develop-0.2.0 --state all --limit 30 --json number,title,url,createdAt`
     で develop-0.2.0 ベースの過去 30 PR を取得。
  2. 各 PR について `gh pr view <num> --comments --json comments` を実行し、
     review コメント本文に "Round 2" / "Round 3" / "再レビュー" / "Round N" のいずれかが
     含まれる PR を抽出。
  3. 抽出された PR から PR #675 を除いて Round 数の多い上位 3 本を特定。

  出力: 上位 3 本の PR 番号、title、Round 数、URL を表形式で返す。
```

**Agent B** — PR #675 round 詳細精読:

```yaml
subagent_type: Explore
description: "PR #675 round detail extraction"
prompt: |
  目的: PR #675 の Round 1 / 2 / 3 で抽出された root cause を整理。

  手順:
  1. `gh pr view 675 --comments --json comments` で全コメントを取得。
  2. コメント本文を Round 1 / Round 2 / Round 3 ごとにグルーピング。
  3. 各 Round で指摘された root cause (literal mismatch / 旧 API / DCE 誇張表現 等) を抽出。
  4. 各 Round で explicit に列挙された箇所数 vs 見落とされた箇所数を集計。

  出力: Round x root cause x (列挙数 / 見落とし数) のクロス表、および root cause 別 file 散在状況。
```

**Agent C** — review-pr SKILL.md 構造把握 (Task 5 で改訂対象の挿入位置を再確認):

```yaml
subagent_type: Explore
description: "SKILL.md current structure"
prompt: |
  目的: .claude/skills/review-pr/SKILL.md の現状節構造を把握し、Task 5 で改訂対象となる
        line 番号と heading text を確定する。

  手順:
  1. `grep -nE "^#{1,4} " .claude/skills/review-pr/SKILL.md` で全 heading の line 番号一覧を取得。
  2. 以下の 3 箇所の line 番号と heading 完全一致 text を返す:
     - "Step 5b" (摘出課題のトリアージ) の `### ` 行 line 番号
     - "Red flags" 表の `## ` 行 line 番号
     - "よくある失敗" 表の `## ` 行 line 番号
  3. それぞれの直後に挿入される予定の新節 (Step 5c sweep 規約) の挿入候補 line を提示。

  出力: line 番号一覧 + heading text + 挿入候補 line の表。
```

- [ ] **Step 2: Agent 3 件の結果を `scenario_e_sweep_research.md` に統合**

`scenario_e_sweep_research.md` 構造:

```markdown
# sweep 規約検証 — 前段階事例調査メモ

## 調査対象 PR (3 本)

| PR | round 数 | root cause 種類 | 散在 file 数 | Round 1 で見落とした箇所数 |
| --- | --- | --- | --- | --- |
| #675 | 3 | literal mismatch + 旧 API + DCE 誇張表現 | 2-3 | 各 root cause 4 箇所 |
| #XXX | N | ... | N | N |
| #YYY | N | ... | N | N |

## 抽出パターン

- パターン 1: ...
- パターン 2: ...

## モック設計への影響

- 中央値シナリオは「単一 root cause が複数 file に 4-5 箇所散在」を採用 (PR #YYY ベース)
- edge シナリオ 1 は「複数 root cause 混在」を採用 (PR #675 再現)
- edge シナリオ 2 は「doc-only PR で literal 散在」を採用 (PR #XXX ベース)
```

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/review-pr/eval/scenario_e_sweep_research.md
git commit -m "docs(review-pr): sweep 規約検証の前段階事例調査メモ追加 (Refs #682)"
```

---

## Task 2: モック設計 — 3 シナリオ作成

**目的:** memory 「中央値 1 + edge 2」原則に従い、3 シナリオを `eval/scenario_e_sweep_*.md` に書き出す。既存の `scenario_a_central.md` / `scenario_b_bundled.md` 等の format を踏襲。

**Files:**

- Create: `.claude/skills/review-pr/eval/scenario_e_sweep_central.md`
- Create: `.claude/skills/review-pr/eval/scenario_e_sweep_edge_mixed.md`
- Create: `.claude/skills/review-pr/eval/scenario_e_sweep_edge_doc_only.md`

- [ ] **Step 1: 既存 scenario file の format を Read で確認**

```bash
cat .claude/skills/review-pr/eval/scenario_a_central.md | head -100
```

scenario file の構造を把握 (モック PR タイトル / モック PR 本文 / モック diff / 期待されるレビュー観点 等)。

- [ ] **Step 2: `scenario_e_sweep_central.md` 作成 (既存 `scenario_a_central.md` と同構造)**

scenario_a_central.md の構造 (`# シナリオ A` / `## 設定` / `## モック PR 本文` / `## モック diff` / `## 期待されるレビュー観点`) を踏襲し、以下のテンプレートで埋める:

```markdown
# シナリオ E (sweep 中央値): モック PR #951

## 設定

仮想 PR: `feat(audio): WR 検出失敗時の fallback テスト追加` (#951)。

PR 著者は `scan_fanfare_peaks` 関数を `scan_audio_peaks` にリネームしたが、docstring /
関連 doc / commit message に **旧名が 4 file × 4-5 箇所 = 計 18 hits 残存** している
(single root cause = literal mismatch)。

| file | 残存 hits | 該当箇所 |
| --- | --- | --- |
| `allaganeye/audio/scan.py` | 4 (line 12, 45, 78, 89) | docstring |
| `tests/audio/test_scan.py` | 4 (line 3, 22, 56, 88) | comment |
| `docs/audio-detection.md` | 5 (line 18, 34, 50, 67, 82) | reference |
| `CHANGELOG.md` | 5 (line 15, 17, 19, 25, 30) | bullet |

(具体的な line 番号は Task 1 の Agent A/B 研究メモから 1 PR を base に実値を採用、
fictional PR としてリアリティを保つ)

## モック PR 本文

(scenario_a_central.md と同じく、`## 概要` / `## 受け入れ条件` / `## Test plan` セクションを
構造化したモック PR body を 30-50 行で記述。受け入れ条件 5 項目は全て [x] 設定)

## モック diff

(リネーム後の正常 diff を 30-50 行示す。docstring / comment / doc / CHANGELOG の旧名残存は
diff には現れず、`grep` で初めて検出される構造にする)

## 期待されるレビュー観点 (Step 5 / 5a / 5b で実施されるべき項目)

- root cause = 「`scan_fanfare_peaks` literal mismatch」を Step 5 (ロジック・ドキュメントレビュー)
  または Step 5a (ギャップ分析) で識別
- `grep -nE 'scan_fanfare_peaks' allaganeye/ tests/ docs/ CHANGELOG.md` で全件 sweep し 18 hits 取得
- 18 hits を Step 5b トリアージ表に **全件 1 行ずつ** 列挙 (file:line + 該当 literal + 処置分類)
- 修正依頼コメントに `grep -nE 'scan_fanfare_peaks'` コマンドと hits を同梱
- 「4 file の代表箇所のみ列挙」「sample 5 箇所のみ修正依頼」のような部分対応は Red Flag に該当
```

- [ ] **Step 3: `scenario_e_sweep_edge_mixed.md` 作成 (PR #675 再現)**

```markdown
# シナリオ E2 (sweep 複数 root cause 混在): モック PR #952

## 設定

仮想 PR: `fix(gui): StateSwitcher の dev only gating + 関連 doc 整合` (#952、PR #675 同型)。

3 種類の root cause が並存:

1. **literal mismatch**: spec/plan doc 内の literal「関数本体先頭」が改訂後の表現と不一致。
   docs/superpowers/specs/ + plans/ の 2 file × 4-5 箇所 = 計 9 hits
2. **旧 API 残存**: test code 内 `vi.stubEnv('DEV', '')` が新 API `vi.stubEnv('DEV', 'true')` に
   未更新。tests/components/ の 3 file × 各 1-2 箇所 = 計 5 hits
3. **DCE 誇張表現**: PR 本文 / commit message 内「production build で完全削除される」表現が
   過剰断定 (実際は esbuild 保守的温存の可能性あり)。3 箇所

## モック PR 本文

(scenario_b_bundled.md と類似の構造で、3 root cause が 1 PR 内に混在することを示す
モック PR body を 30-50 行で記述)

## モック diff

(literal mismatch を 2 file 計 9 箇所に埋め込んだ diff を示す)

## 期待されるレビュー観点

- 3 種類の root cause を Step 5 / 5a で個別に識別
- 各 root cause について `grep -nE` 全件 sweep を提示 (3 個の grep コマンド):
  - `grep -nE '関数本体先頭' docs/superpowers/`
  - `grep -nE "stubEnv\\('DEV', ''\\)" tests/`
  - `grep -nE 'production build で完全削除' .`
- 計 17 hits (9 + 5 + 3) を Step 5b トリアージ表に全件転記
- PR #675 同種事例を「よくある失敗」表から引用
- 「explicit 5 箇所のみ列挙」のような部分対応は Red Flag (Round 2/3 への divergence 原因)
```

- [ ] **Step 4: `scenario_e_sweep_edge_doc_only.md` 作成 (doc-only)**

```markdown
# シナリオ E3 (sweep doc-only literal 散在): モック PR #953

## 設定

仮想 PR: `docs: l2-workflow.md の Self-Test Report 規約 v2 化` (#953)。

doc-only PR (コード変更ゼロ、.md のみ) で literal mismatch が 5 file × 計 12 箇所散在。

| file | 残存 hits | 該当箇所 |
| --- | --- | --- |
| `docs/superpowers/specs/2026-04-XX-XXX-design.md` | 3 (line 25, 80, 142) | spec 内引用 |
| `docs/superpowers/plans/2026-04-XX-XXX-implementation.md` | 3 (line 50, 110, 200) | plan 内引用 |
| `.claude/skills/review-pr/SKILL.md` | 2 (line 240, 280) | skill 規約引用 |
| `.claude/skills/release/SKILL.md` | 2 (line 50, 90) | skill 規約引用 |
| `CLAUDE.md` | 2 (line 130, 175) | プロジェクト規約引用 |

旧 literal: `Self-Test Report`、新 literal: `PR Self-Test 規約` (本シナリオで仮定)。

## モック PR 本文

(scenario_c_isolated.md と類似の構造、doc-only PR の典型 body を 30-50 行で記述。
受け入れ条件は「l2-workflow.md の Self-Test Report 規約 v2 化を完了」など)

## モック diff

(l2-workflow.md の Self-Test Report → PR Self-Test 規約 の rename diff のみ示す。
他 file への波及は diff には現れない)

## 期待されるレビュー観点

- doc-only でも root cause (literal mismatch) を Step 5 で識別する (環境制約 §D doc-only PR)
- `grep -nE 'Self-Test Report' docs/ .claude/ CLAUDE.md` で 12 hits 全件 sweep
- 12 hits を Step 5b トリアージ表に全件列挙
- 「軽微な doc 修正だから一部対応で OK」「spec / plan は手動で順次反映で OK」のような
  握り潰しを Red Flag として識別
- markdownlint pass や CI 波及 (関連 doc 整合性) を §D doc-only CI 波及検証として実施
```

- [ ] **Step 5: 3 ファイル一括 commit**

```bash
git add .claude/skills/review-pr/eval/scenario_e_sweep_*.md
git commit -m "docs(review-pr): sweep 規約検証用モック 3 シナリオ追加 (Refs #682)"
```

---

## Task 3: 要件チェックリスト追加 (`requirements.md` への追記)

**目的:** memory 「`[critical]` タグ付きで事前固定」「事後の `[critical]` 付け外し禁止」に従い、3 シナリオ分の要件を `[critical]` タグ付きで `requirements.md` に追記する。

**Files:**

- Modify: `.claude/skills/review-pr/eval/requirements.md` (末尾に追記)

- [ ] **Step 1: 既存 requirements.md を Read で確認**

`requirements.md` の format (シナリオ A-D の `[critical]` 付与パターン、判定規則) を確認。

- [ ] **Step 2: シナリオ E / E2 / E3 を末尾追記**

```markdown
---

## シナリオ E (sweep 中央値): モック PR #951 (feat(audio): WR 検出失敗時の fallback テスト追加)

1. **[critical]** root cause (`scan_fanfare_peaks` literal mismatch) を Step 5 / 5a で識別している
2. **[critical]** `grep -nE 'scan_fanfare_peaks'` 全件 sweep を提示している
3. **[critical]** 18 hits 全件を Step 5b トリアージ表に列挙している (explicit N 箇所のみ列挙ではない)
4. **[critical]** Red Flag 表の新項目 (「explicit N 箇所だけ列挙して全件 grep を要求しない」) を引用している
5. Round 1 で全件捕捉している (Round 2/3 への分散がない)
6. 摘出課題を Step 5b トリアージ表に (A)/(B)/(C) で分類している (既存ベース要件)
7. CI / Lint ステータスを確認している
8. PR ブランチへの commit/push をしていない (レビュー専用セッション契約)

---

## シナリオ E2 (sweep 複数 root cause 混在): モック PR #952 (PR #675 再現相当)

1. **[critical]** 3 種類の root cause (literal mismatch / 旧 API / DCE 誇張表現) を識別している
2. **[critical]** 各 root cause について `grep` 全件 sweep を提示している (3 個の grep コマンド)
3. **[critical]** PR #675 同種事例の引用または「よくある失敗」表参照を含む
4. **[critical]** 全 hits を Step 5b トリアージ表に列挙し握り潰しゼロ
5. Round 1 で全件捕捉している (Round 2/3 への分散がない)
6. LGTM ではなく修正依頼を出している

---

## シナリオ E3 (sweep doc-only): モック PR #953 (docs literal 散在)

1. **[critical]** doc-only でも root cause (literal mismatch) を Step 5 で識別している (「doc だから sweep 不要」と判定していない)
2. **[critical]** `grep -nE '...'` 全件 sweep を提示している
3. **[critical]** 12 hits 全件を Step 5b トリアージ表に列挙している
4. **[critical]** 「軽微な doc 修正だから一部対応で OK」のような握り潰しを Red Flag として識別している
5. doc-only PR の CI 波及 (markdownlint / 関連 doc 整合性) を環境制約 §D に従って確認している
```

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/review-pr/eval/requirements.md
git commit -m "docs(review-pr): requirements.md にシナリオ E/E2/E3 (sweep 規約) を追記 (Refs #682)"
```

---

## Task 4: Iteration 0 (baseline) — 改訂前 SKILL.md で 3 並列 dispatch

**目的:** memory 「`general-purpose` + `model: sonnet` + 3 並列 + `run_in_background: true`」に従い、改訂**前**の SKILL.md で 3 シナリオを評価。期待: Round 1 で全件 sweep されない (現状再現)。

**Files:**

- Create: `.claude/skills/review-pr/eval/reports/iter_0_sweep_central_baseline.md`
- Create: `.claude/skills/review-pr/eval/reports/iter_0_sweep_edge_mixed_baseline.md`
- Create: `.claude/skills/review-pr/eval/reports/iter_0_sweep_edge_doc_only_baseline.md`

- [ ] **Step 1: subagent 3 並列 dispatch (1 message で 3 tool call)**

各 Agent prompt の構造:

```text
subagent_type: general-purpose
model: sonnet
run_in_background: true
description: "iter 0 sweep <scenario> baseline"
prompt: |
  あなたは review-pr skill (current SKILL.md) を実行する subagent です。
  シナリオ E / E2 / E3 のいずれかを与えられ、モック PR をレビューします。

  シナリオ file: .claude/skills/review-pr/eval/scenario_e_sweep_<central|edge_mixed|edge_doc_only>.md
  要件チェックリスト: .claude/skills/review-pr/eval/requirements.md

  手順:
  1. SKILL.md の現状版 (本セッション開始時点) を Read
  2. シナリオ file を Read してモック PR の内容を把握
  3. SKILL.md に従ってレビューを実行 (Step 1 から Step 6 まで)
  4. 各 Step の結果を構造化して報告
  5. 要件チェックリスト各項目について ○ / 部分的 / × を評価
  6. 結果を `eval/reports/iter_0_sweep_<scenario>_baseline.md` に保存
```

3 Agent (central / edge_mixed / edge_doc_only) を 1 message で同時 dispatch。

- [ ] **Step 2: 3 Agent 完了通知を待つ**

`run_in_background: true` の Agent 群は並列実行され、完了通知が届く。3 件すべて完了したら Step 3 へ。

- [ ] **Step 3: 各 report を check (要件 ○ / 部分的 / × 集計)**

```bash
ls .claude/skills/review-pr/eval/reports/iter_0_sweep_*_baseline.md
```

各 report の冒頭に `[critical] X / Y` 形式のサマリが含まれることを確認。

期待: Iteration 0 では `[critical]` 達成率が低い (改訂前 SKILL.md には sweep 規約がないため、Round 1 で全件 sweep されないことを再現する)。

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/review-pr/eval/reports/iter_0_sweep_*_baseline.md
git commit -m "docs(review-pr): Iteration 0 baseline reports (sweep 規約検証 3 シナリオ、Refs #682)"
```

---

## Task 5: SKILL.md 改訂 (sweep 規約節 + Red Flag + 「よくある失敗」 + Step 5b 改定)

**目的:** issue #682 受け入れ条件 1, 2, 3 を満たす。Red Flag 表 (line 504) / 「よくある失敗」表 (line 522) / Step 5b (line 186) の正確な節名は `grep` で確認済 (writing-plans Task 5 直前 grep 結果)。

**Files:**

- Modify: `.claude/skills/review-pr/SKILL.md` (line 186 後 / line 504 内 / line 522 内)

- [ ] **Step 1: SKILL.md の Step 5b 直後に「同種パターン sweep 規約」節を新規追加**

挿入位置: line 244 (Step 5b 末尾) と line 245 (`### 6. レビュー結果をユーザーに報告`) の間に新節を入れる。

新節の構造:

```markdown
### 5c. 同種パターン全件 sweep 規約 (Refs #682)

Step 5 / 5a / 5b で root cause (literal mismatch / 古い API 残存 / DCE 誇張表現 等) を識別したら、explicit な N 箇所だけを列挙して implementer に依頼するのは **Red Flag** (PR #675 で 3 round 分散の実害)。以下を必須化する:

1. **全件 grep 提示**: `grep -nE 'pattern1|pattern2|...'` で repo 全体から hits を抽出
2. **トリアージ表に grep hits を全件転記**: Step 5b の表に各 hit を 1 行ずつ記載 (file:line + 該当パターン + 処置分類)
3. **修正依頼本文に grep コマンドと hits を同梱**: PR コメントの修正依頼にも grep コマンドを引用

「explicit な 4 箇所」を依頼すると implementer が同 file 内の他 hits を見落とし、Round 2/3 で再指摘するパターンが発生する (#682 issue 本文 PR #675 経緯参照)。
```

- [ ] **Step 2: Red Flag 表 (line 504-520) に 1 行追記**

挿入位置: line 515 直後の新行に追加。既存表は line 504 から始まる:

```markdown
| 「explicit N 箇所だけ列挙して全件 grep を要求しない」 | divergence 原因。1 round で完了せず Round 2/3 に分散する。root cause 識別時は `grep -nE 'pattern'` 全件 sweep が必須 (Step 5c 参照、PR #675 で 3 round 必要だった失敗パターン) |
```

- [ ] **Step 3: 「よくある失敗」表 (line 522-) に PR #675 事例追記**

挿入位置: line 526 (`- **摘出課題を「PR スコープ外」と自己判断して握り潰す**:` の段落) の前または後に新項目を追加:

```markdown
- **explicit N 箇所だけ列挙して全件 grep を要求しない (PR #675 Round 1/3 divergence)**: PR #675 で literal「関数本体先頭」訂正 + 旧 API `vi.stubEnv('DEV', '')` + DCE 誇張表現 の 3 種類の root cause が複数 file に散在していたが、各 Round で explicit な N 箇所のみ列挙したため Round 1 → 2 → 3 と divergence 発生。Round 1 で `grep -nE '関数本体先頭|stubEnv.*DEV|DCE で完全削除'` 全件 sweep していれば 1 Round で完了していた → Step 5c (同種パターン sweep 規約) に従う。
```

- [ ] **Step 4: Step 5b 内に Step 5c への参照を追記**

挿入位置: line 188-244 の Step 5b 本文中、トリアージ表テンプレートの直前 (line 237 周辺) に sweep 必須化の文言を 1-2 行追加:

```markdown
**root cause 識別時は Step 5c (同種パターン sweep 規約) に従う**: explicit N 箇所のみ列挙ではなく、`grep -nE '...'` 全件 sweep の hits を本表に転記すること。
```

- [ ] **Step 5: SKILL.md の自身の section 番号 (5c) が他箇所と矛盾しないか grep 確認**

```bash
grep -nE "^### [0-9]" .claude/skills/review-pr/SKILL.md
```

Step 5b の次が `### 6` であることを確認 (Step 5c 挿入後は `### 5b → ### 5c → ### 6` の順)。

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/review-pr/SKILL.md
git commit -m "feat(review-pr): SKILL.md に Step 5c (同種パターン sweep 規約) + Red Flag + 失敗事例追加 (Refs #682)"
```

---

## Task 6: Iteration 1 (revaluation) — 改訂版 SKILL.md で 3 並列 dispatch (新規 subagent 必須)

**目的:** memory 「Iteration 1 再評価では必ず**新規** subagent (empirical Red Flag『同じ subagent を使い回そう』に該当するため同一 agent は不可)」を厳守。

**Files:**

- Create: `.claude/skills/review-pr/eval/reports/iter_1_sweep_central_revaluation.md`
- Create: `.claude/skills/review-pr/eval/reports/iter_1_sweep_edge_mixed_revaluation.md`
- Create: `.claude/skills/review-pr/eval/reports/iter_1_sweep_edge_doc_only_revaluation.md`
- Create: `.claude/skills/review-pr/eval/reports/summary_sweep.md`

- [ ] **Step 1: 新規 subagent 3 並列 dispatch (1 message で 3 tool call)**

Task 4 と同じ prompt 構造だが、SKILL.md は **改訂後** を Read させ、保存先を `iter_1_sweep_<scenario>_revaluation.md` に変更。

**重要**: Task 4 で使った subagent と**異なる subagent インスタンス**を使う (memory Red Flag 該当)。Task 4 の Agent と Task 6 の Agent はそれぞれ別 dispatch なので自然と新規になるが、prompt 内で「あなたは新規 subagent です。前回 (Iteration 0) の評価結果は参照しないでください」と明示する。

- [ ] **Step 2: 3 Agent 完了通知を待つ**

- [ ] **Step 3: summary_sweep.md 作成 (Iteration 0/1 比較)**

`summary_sweep.md` 構造:

```markdown
# sweep 規約検証 — Iteration 0/1 比較サマリ

## [critical] 達成率

| シナリオ | Iteration 0 (baseline) | Iteration 1 (revaluation) | 改善 |
| --- | --- | --- | --- |
| E (中央値) | X / Y | X' / Y | +Δ |
| E2 (混在) | X / Y | X' / Y | +Δ |
| E3 (doc-only) | X / Y | X' / Y | +Δ |

## 構造的欠陥の解消

- 改訂前で見られた構造的欠陥 (例: sweep 規約節の不在 / Red Flag の不存在 / 「よくある失敗」事例の欠如) が改訂後に解消されているかを確認
- 各 [critical] 要件について Iteration 0 → 1 の差分を記載

## 打ち切り判定

- [critical] 全要件が Iteration 1 で ○ → 打ち切り (Task 7 で確認)
- 部分的 / × が残る → Iteration 2 へ (Task 7 で再改訂)
```

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/review-pr/eval/reports/iter_1_sweep_*.md \
        .claude/skills/review-pr/eval/reports/summary_sweep.md
git commit -m "docs(review-pr): Iteration 1 revaluation reports + summary (Refs #682)"
```

---

## Task 7: 打ち切り判定 (Iteration N+1 が必要か)

**目的:** memory 「構造的欠陥が解消された時点で打ち切り可」「残る細部不明瞭点は deferred issue」に従う。

**Files (条件分岐あり):**

- (打ち切る場合) なし
- (Iteration 2 が必要な場合) `.claude/skills/review-pr/SKILL.md` (再改訂) + `iter_2_sweep_*_revaluation.md` 3 件 + `summary_sweep.md` 更新

- [ ] **Step 1: `summary_sweep.md` の `[critical]` 達成率を Read**

```bash
cat .claude/skills/review-pr/eval/reports/summary_sweep.md
```

- [ ] **Step 2: 判定**

判定基準:

- **打ち切り条件**: 3 シナリオすべてで Iteration 1 の `[critical]` 全要件が ○
- **Iteration 2 へ移行**: 1 つでも ○ 以外 (`部分的` / `×`) の `[critical]` 要件あり

- [ ] **Step 3a: 打ち切る場合 — Task 8 へ進む**

「Iteration 2 不要」を `summary_sweep.md` 末尾に明記して commit:

```markdown
## 打ち切り

Iteration 1 で全 [critical] 要件 ○ を達成。empirical 検証完了 (memory「構造的欠陥が解消された時点で打ち切り可」適用)。
```

- [ ] **Step 3b: Iteration 2 が必要な場合 — SKILL.md 再改訂 → Iteration 2**

落ちた `[critical]` 要件を分析し、SKILL.md を再改訂 (Step 5c の文言追加 / Red Flag 表の追加項目 / 「よくある失敗」事例の補強)。

その後、新規 subagent で Iteration 2 を実施し、再度 Task 7 へループする (max 3 Iteration を目安、それ以降は構造的欠陥がないとみなして deferred issue 化)。

- [ ] **Step 4: Commit (打ち切り or 再改訂結果)**

```bash
# 打ち切り
git add .claude/skills/review-pr/eval/reports/summary_sweep.md
git commit -m "docs(review-pr): empirical 検証完了 (Iteration 1 で打ち切り、Refs #682)"

# Iteration 2 後の場合
git add .claude/skills/review-pr/SKILL.md \
        .claude/skills/review-pr/eval/reports/iter_2_sweep_*.md \
        .claude/skills/review-pr/eval/reports/summary_sweep.md
git commit -m "feat(review-pr): SKILL.md 再改訂 + Iteration 2 で empirical 検証完了 (Refs #682)"
```

---

## Task 8: #624-A `check-pr-checklist.js` 切り出し (TDD)

**目的:** spec §3.3 の `countAcceptanceCriteriaCheckboxes` 関数を TDD で実装。

**Files:**

- Create: `.github/scripts/check-pr-checklist.js`
- Create: `.github/scripts/check-pr-checklist.test.js`

- [ ] **Step 1: 失敗テストを書く** (`.github/scripts/check-pr-checklist.test.js`)

```javascript
// .github/scripts/check-pr-checklist.test.js
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { countAcceptanceCriteriaCheckboxes } = require('./check-pr-checklist.js');

test('counts unchecked items only inside ## 受け入れ条件 section', () => {
  const body = `
## 概要

(略)

## 受け入れ条件

- [ ] 項目 1
- [x] 項目 2

## Test plan

- [ ] レビューで実機検証
- [ ] 確認 2
`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
  assert.equal(result.checked, 1);
  assert.equal(result.hasAnySection, true);
});
```

- [ ] **Step 2: テスト実行 → 失敗を確認**

```bash
node --test .github/scripts/check-pr-checklist.test.js
```

期待: `Cannot find module './check-pr-checklist.js'` で fail。

- [ ] **Step 3: 最小実装** (`.github/scripts/check-pr-checklist.js`)

```javascript
// .github/scripts/check-pr-checklist.js
function countAcceptanceCriteriaCheckboxes(body) {
  // `## ` heading で section 分割。最初の heading 前は捨てる
  const sections = body.split(/^##\s+/m).slice(1);
  // 受け入れ条件 / Acceptance criteria heading に該当する section のみ抽出
  const acceptanceText = sections
    .filter((s) => {
      const heading = (s.split(/\r?\n/)[0] || '').trim();
      return /^(受け入れ条件|acceptance\s+criteria)\s*$/i.test(heading);
    })
    .join('\n');
  const unchecked = (acceptanceText.match(/- \[ \]/g) || []).length;
  const checked = (acceptanceText.match(/- \[x\]/gi) || []).length;
  return { unchecked, checked, hasAnySection: acceptanceText.length > 0 };
}

async function checkPrChecklist({ github, context, core }) {
  const body = context.payload.pull_request.body || '';
  const { unchecked, checked, hasAnySection } = countAcceptanceCriteriaCheckboxes(body);
  if (!hasAnySection) {
    core.info('No `## 受け入れ条件` / `## Acceptance criteria` section found, skipping.');
    return;
  }
  if (unchecked > 0) {
    core.setFailed(
      `PR has ${unchecked} unchecked acceptance criteria item(s) in \`## 受け入れ条件\` section. Please complete all items before merging.`
    );
    return;
  }
  core.info(`All ${checked} acceptance criteria item(s) are checked.`);
}

module.exports = checkPrChecklist;
module.exports.countAcceptanceCriteriaCheckboxes = countAcceptanceCriteriaCheckboxes;
```

- [ ] **Step 4: テスト実行 → pass を確認**

```bash
node --test .github/scripts/check-pr-checklist.test.js
```

期待: 1 test passing。

- [ ] **Step 5: Commit**

```bash
git add .github/scripts/check-pr-checklist.js .github/scripts/check-pr-checklist.test.js
git commit -m "feat(workflow): check-pr-checklist.js を切り出し + 基本 unit test (Refs #624)"
```

---

## Task 9: #624-B 追加テストケース (PR #621 / #622 / 英語別名 / blockquote / skip)

**目的:** spec §7.1 の 7 ケースをすべて実装し、issue #624 受け入れ条件 1, 2, 3 を unit test で担保。

**Files:**

- Modify: `.github/scripts/check-pr-checklist.test.js`

- [ ] **Step 1: PR #621 構造再現テスト追加**

```javascript
test('PR #621 structure passes (Test plan with - [ ] does not fail)', () => {
  // PR #621 は Test plan section に - [ ] が複数あり、受け入れ条件は全件 [x] だった
  const body = `
## 受け入れ条件

- [x] 受け入れ条件 1
- [x] 受け入れ条件 2

## Test plan

- [ ] レビュー時に実機検証
- [ ] レビューで GUI 起動確認
`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 0);
  assert.equal(result.checked, 2);
});
```

- [ ] **Step 2: PR #622 構造再現テスト追加**

```javascript
test('PR #622 structure passes (Self-Test Report with - [ ] does not fail)', () => {
  const body = `
## 受け入れ条件

- [x] 受け入れ条件 1

## Self-Test Report (本 PR 提出前にローカルで実行済)

- [x] ruff check
- [x] pyright

### 実機検証 (machine-unverifiable)

- [ ] レビュー時に Idios 実機確認
`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 0);
  assert.equal(result.checked, 1);
});
```

- [ ] **Step 3: 英語別名テスト追加**

```javascript
test('counts unchecked items inside ## Acceptance criteria (English variant, case-insensitive)', () => {
  const body = `
## Acceptance criteria

- [ ] Item A
- [x] Item B

## Test plan

- [ ] Manual check
`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
  assert.equal(result.checked, 1);
});

test('counts unchecked items inside ## ACCEPTANCE CRITERIA (uppercase)', () => {
  const body = `
## ACCEPTANCE CRITERIA

- [ ] Uppercase heading
`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
});
```

- [ ] **Step 4: 受け入れ条件 unchecked が残っているケース (Iron Law 1 自動執行 = #367 対策維持) テスト追加**

```javascript
test('FAILS when unchecked items remain in 受け入れ条件 section', () => {
  const body = `
## 受け入れ条件

- [ ] 未消化項目
- [x] 完了項目
`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
  // この場合 workflow script の checkPrChecklist が core.setFailed を呼ぶことが期待値
});
```

- [ ] **Step 5: 受け入れ条件 section が存在しない (skip ケース) テスト追加**

```javascript
test('hasAnySection is false when no 受け入れ条件 / Acceptance criteria section', () => {
  const body = `
## 概要

これは spec 議論用 PR です。

## Test plan

- [ ] レビュー
`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.hasAnySection, false);
});
```

- [ ] **Step 6: blockquote 内 (現状仕様: blockquote 内の `- [ ]` も match する) テスト追加**

```javascript
test('blockquote-inner - [ ] inside 受け入れ条件 is currently counted (spec note)', () => {
  // spec §7.1 で「blockquote 内も grep される、現状仕様と同等」と明記されている
  const body = `
## 受け入れ条件

> - [ ] このブロッククォート内の項目はカウントされる
`;
  const result = countAcceptanceCriteriaCheckboxes(body);
  assert.equal(result.unchecked, 1);
});
```

- [ ] **Step 7: 全テスト実行 → pass 確認**

```bash
node --test .github/scripts/check-pr-checklist.test.js
```

期待: 7 tests passing (Step 1 の基本テスト + Step 1-6 の追加 6 テスト)。

- [ ] **Step 8: Commit**

```bash
git add .github/scripts/check-pr-checklist.test.js
git commit -m "test(workflow): check-pr-checklist の追加 6 ケース (PR #621/#622/英語/skip/blockquote、Refs #624)"
```

---

## Task 10: #624-C `pr-checklist.yml` の require 化

**目的:** spec §3.3 の `pr-checklist.yml` 改修。inline script → `actions/checkout@v4` + `require('./.github/scripts/check-pr-checklist.js')`。

**Files:**

- Modify: `.github/workflows/pr-checklist.yml`

- [ ] **Step 1: pr-checklist.yml を新形式に書き換え**

```yaml
name: PR Checklist Validation

on:
  pull_request:
    types: [opened, edited, synchronize]

jobs:
  validate-checklist:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Check PR checklist
        uses: actions/github-script@v7
        with:
          script: |
            const checker = require('./.github/scripts/check-pr-checklist.js');
            await checker({ github, context, core });
```

- [ ] **Step 2: yml syntax check**

```bash
# yamllint があれば
yamllint .github/workflows/pr-checklist.yml
# なければ Python の yaml 標準ライブラリで syntax check
python -c "import yaml; yaml.safe_load(open('.github/workflows/pr-checklist.yml'))"
```

期待: syntax error なし。

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/pr-checklist.yml
git commit -m "refactor(workflow): pr-checklist.yml を require 化 + section-aware 化 (Refs #624)"
```

---

## Task 11: #624-D `check-pr-checklist-test.yml` workflow 追加

**目的:** spec §7.1 で言及した「CI で `node --test` を走らせる job」を新規 workflow で追加。

**Files:**

- Create: `.github/workflows/check-pr-checklist-test.yml`

- [ ] **Step 1: 新 workflow を作成**

```yaml
name: check-pr-checklist unit tests

on:
  pull_request:
    paths:
      - '.github/scripts/check-pr-checklist.js'
      - '.github/scripts/check-pr-checklist.test.js'
      - '.github/workflows/check-pr-checklist-test.yml'
  push:
    branches: [develop-0.2.0, main]
    paths:
      - '.github/scripts/check-pr-checklist.js'
      - '.github/scripts/check-pr-checklist.test.js'

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - name: Run check-pr-checklist unit tests
        run: node --test .github/scripts/check-pr-checklist.test.js
```

- [ ] **Step 2: yml syntax check**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/check-pr-checklist-test.yml'))"
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/check-pr-checklist-test.yml
git commit -m "ci(workflow): check-pr-checklist の Node.js native test runner job 追加 (Refs #624)"
```

---

## Task 12: #458 `bug_report.yml` 微修正

**目的:** spec §4.2 の最小修正 (上部 markdown 案内に ErrorModal note 1 行追加 + `actual` / `log_file_attachment` description 微修正)。

**Files:**

- Modify: `.github/ISSUE_TEMPLATE/bug_report.yml`

- [ ] **Step 1: 上部 markdown 案内に ErrorModal note 追加**

既存 line 8-15 (markdown ブロック) に 1 行追加:

```yaml
  - type: markdown
    attributes:
      value: |
        バグ報告ありがとうございます。以下のフォームに従って情報を記入してください。

        動画ファイルを添付する場合は、プライバシー・機密情報の混入がないことを事前にご確認ください (下のチェックボックス参照)。

        ErrorModal の `[GitHub Issue を作成]` ボタンを使うと一部項目 (実際の動作 / 環境情報 / ログファイル) が自動入力されます (公開後)。

        詳細は [`docs/bug-report-guide.md`](../../blob/develop-0.2.0/docs/bug-report-guide.md) を参照してください (公開までしばらくお待ちください)。
```

- [ ] **Step 2: `actual` の description 微修正**

既存 line 36-42 の `actual` textarea で description を修正:

```yaml
  - type: textarea
    id: actual
    attributes:
      label: 実際の動作
      description: エラーメッセージ全文やログがあれば貼り付けてください (ErrorModal から自動入力される場合あり)
    validations:
      required: true
```

- [ ] **Step 3: `log_file_attachment` の description 微修正**

既存 line 59-67 の `log_file_attachment` textarea で description に追記:

```yaml
  - type: textarea
    id: log_file_attachment
    attributes:
      label: ログファイル (GUI クラッシュ時のみ)
      description: |
        GUI でクラッシュ・ErrorModal が出た場合、アプリのインストール先 (`allaganeye-gui.exe` があるフォルダ) の `logs/error-YYYYMMDD.log` の関連箇所を貼り付けるか、ファイルを添付してください。ErrorModal の `[ログフォルダを開く]` ボタンからも辿れます。

        ErrorModal から自動入力される場合は末尾抜粋のみ。完全なログファイルが必要な場合は手動添付してください。
      render: text
    validations:
      required: false
```

- [ ] **Step 4: yml syntax check**

```bash
python -c "import yaml; yaml.safe_load(open('.github/ISSUE_TEMPLATE/bug_report.yml'))"
```

- [ ] **Step 5: field id rename されていないことを確認 (凍結確認)**

```bash
grep -nE "^\s*id:\s*" .github/ISSUE_TEMPLATE/bug_report.yml
```

期待出力: `reproduction` / `expected` / `actual` / `environment` / `log_file_attachment` / `consent` (全 6 件、PR #497 と同一)。

- [ ] **Step 6: Commit**

```bash
git add .github/ISSUE_TEMPLATE/bug_report.yml
git commit -m "docs(issue-template): bug_report.yml に ErrorModal 自動埋込 note 追加 + description 微修正 (Refs #458)"
```

---

## Task 13: 全体 markdownlint pass 確認

**目的:** 本 PR で touch した全 .md (spec / SKILL.md / scenario / report 等) が markdownlint clean。

**Files:** (検証のみ、変更なし)

- [ ] **Step 1: markdownlint 全体実行**

```bash
bash scripts/check-markdownlint.sh
```

期待: `Summary: 0 error(s)`。

- [ ] **Step 2: error がある場合のみ修正**

各 error について該当 file を `Edit` で修正し、再度 step 1 を実行。

- [ ] **Step 3: 全件 clean になったら Commit (修正があった場合のみ)**

```bash
git add <修正 file>
git commit -m "docs: markdownlint clean (Refs #624 #458 #682)"
```

(修正なしならこの step は skip)

---

## Task 14: PR Pre-flight + PR 作成 (Iron Law 6)

**目的:** Iron Law 6 PR Pre-flight (`docs/l2-workflow.md` §「PR 作成 Pre-flight」) の 4 項目を実施し、PR を base = develop-0.2.0 に作成。

**Files:** (検証 + PR 作成、commit なし)

- [ ] **Step 1: base 最新化 + 取り込み未済 commit 確認**

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline
```

期待: 取り込み未済 commit が 0 件、または影響なしの commit のみ。

- [ ] **Step 2: 影響候補ファイル交差判定**

取り込み未済 commit がある場合:

```bash
# 当 PR の touched files
git diff --name-only origin/develop-0.2.0...HEAD

# 取り込み未済 commit の touched files
git diff --name-only HEAD...origin/develop-0.2.0
```

両者を交差判定。交差ありなら Step 3、なしなら Step 4 へ。

- [ ] **Step 3: 必要なら base 取り込み + 自動チェック再実行**

```bash
git merge origin/develop-0.2.0
# コンフリクト解消 (発生時)
node --test .github/scripts/check-pr-checklist.test.js
bash scripts/check-markdownlint.sh
```

- [ ] **Step 4: 並行 worktree PR 重複確認**

```bash
gh pr list --search "624" --state all --json number,headRefName,state
gh pr list --search "458" --state all --json number,headRefName,state
gh pr list --search "682" --state all --json number,headRefName,state
gh pr list --search "Group G" --state all --json number,headRefName,state
```

期待: 自分の branch (`claude/friendly-fermi-b81bbe`) 以外に同 issue を参照する open PR がない。

ある場合は AskUserQuestion で 3 択:

- (A) 重複扱いで close 提案 (Recommended、明らかな機能重複時)
- (B) スコープ分担で並走
- (C) 既マージ済みで対象外

- [ ] **Step 5: branch を origin に push**

```bash
git push origin claude/friendly-fermi-b81bbe
```

- [ ] **Step 6: PR body を HEREDOC で作成 (memory `feedback_gh_command_ja_heredoc.md` 準拠)**

```bash
gh pr create --base develop-0.2.0 --head claude/friendly-fermi-b81bbe \
  --title "feat(workflow): Group G workflow / CI / docs 仕上げ (Refs #624 #458 #682)" \
  --body-file - <<'EOF'
## スコープ

Lane IV-b (Group G) として workflow / CI / docs 仕上げの 3 件を統合実装。
3 件は file 衝突なし (`.github/workflows/pr-checklist.yml` /
`.github/ISSUE_TEMPLATE/bug_report.yml` / `.claude/skills/review-pr/SKILL.md`)、
目的は v0.2.0 release gate 仕上げで一貫。

Refs #624, Refs #458, Refs #682

## 受け入れ条件

### #624 (workflow section-aware 化)

- [x] pr-checklist.yml の script を改修し、CLAUDE.md template に従って PR を作成しても誤検出しないこと
- [x] PR #621 / #622 相当の構造で validate-checklist が pass する (unit test で再現)
- [x] `## 受け入れ条件` の未消化 `- [ ]` は引き続き fail を返すこと (#367 対策維持、unit test で確認)
- [x] CLAUDE.md PR template / docs/l2-workflow.md PR template 例とテストの整合性が取れている

### #458 (bug_report.yml field id 凍結 + #669 連動先取り)

- [x] field id (reproduction/expected/actual/environment/log_file_attachment/consent) を本 spec で凍結
- [x] placeholder / description / 上部 markdown 案内に ErrorModal 自動埋込 note を追加
- [x] field id を Group D #669 の URL parameter 名として確定したことを spec に記述
- (deferred) New issue UI からテンプレ選択可能 (L3 初期 UI 実測、release gate 後に別途実施、本 PR scope 外)

### #682 (review-pr sweep 規約追加)

- [x] SKILL.md に「同種パターン sweep 規約」節 (Step 5c) を追加
- [x] Red Flag 表に「explicit N 箇所だけ列挙 → divergence」を追加
- [x] 「よくある失敗」表に PR #675 Round 1/3 経緯事例追記
- [x] empirical-prompt-tuning で検証 (PR #675 同種シナリオ mock で 2 Iteration、eval/ 配下にアーティファクト同梱)

## Self-Test Report (本 PR 提出前にローカルで実行済)

- [x] `node --test .github/scripts/check-pr-checklist.test.js` (全 7 test pass)
- [x] `python -c "import yaml; yaml.safe_load(open('.github/workflows/pr-checklist.yml'))"` (syntax error なし)
- [x] `python -c "import yaml; yaml.safe_load(open('.github/workflows/check-pr-checklist-test.yml'))"` (同上)
- [x] `python -c "import yaml; yaml.safe_load(open('.github/ISSUE_TEMPLATE/bug_report.yml'))"` (同上)
- [x] `bash scripts/check-markdownlint.sh` (Summary: 0 error(s))
- [x] field id 凍結確認 (`grep id: bug_report.yml` で reproduction/expected/actual/environment/log_file_attachment/consent の 6 件)

### 実機検証 (machine-unverifiable)

- 該当なし (workflow / issue template / skill md / spec doc / eval reports のみの変更、
  gpu_detector.py / audio/ / video/detector.py / gui/src-tauri/ への touch なし)

## session-id

friendly-fermi-b81bbe

## 関連 doc

- spec: [docs/superpowers/specs/2026-05-08-lane-iv-b-group-g-design.md](docs/superpowers/specs/2026-05-08-lane-iv-b-group-g-design.md)
- plan: [docs/superpowers/plans/2026-05-08-lane-iv-b-group-g-implementation.md](docs/superpowers/plans/2026-05-08-lane-iv-b-group-g-implementation.md)
- roadmap: [docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md](docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md) §Group G

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
```

- [ ] **Step 7: PR URL を確認**

```bash
gh pr view --json number,url,title
```

PR 番号と URL を記録 (後続の `/review-pr` / `/close-issue` で参照)。

---

## Self-Review チェックポイント

### 1. Spec coverage

| spec section | 対応 task |
| --- | --- |
| §1 Overview | 全 task で 3 issue 横断対応 |
| §2 Goals (#624 / #458 / #682) | Task 8-11 / 12 / 1-7 で各々 |
| §3 #624 workflow section-aware 化 | Task 8 (TDD impl) / Task 9 (追加テスト) / Task 10 (yml require 化) / Task 11 (CI workflow) |
| §3.5 #624 受け入れ条件 4 項目 | Task 9 で 7 unit test ケースで担保 |
| §3.6 docs 整合確認 | (本 PR で docs 変更なし、既存 l2-workflow.md / CLAUDE.md は spec で「変更不要」と確認済) |
| §4 #458 bug_report.yml 仕上げ | Task 12 |
| §4.2 上部案内 + actual + log_file_attachment 修正 | Task 12 Step 1-3 |
| §4.3 受け入れ条件 5/6 完了 + 1 deferred | Task 12 Step 5 で field id 凍結確認、deferred は PR 本文で plain bullet |
| §5 #682 SKILL.md sweep 規約 | Task 1 (事例調査) / Task 2 (mock) / Task 3 (要件) / Task 4 (Iter 0) / Task 5 (改訂) / Task 6 (Iter 1) / Task 7 (打ち切り) |
| §5.3 empirical 2 Iteration | Task 4 (Iter 0) + Task 6 (Iter 1) + Task 7 (Iter 2 trigger) |
| §6 PR 統合方針 | Task 14 (PR 作成、3 issue Refs) |
| §6.2 受け入れ条件統合 | Task 14 Step 6 PR body |
| §6.3 chicken-and-egg 回避 | Task 14 Step 6 PR body で受け入れ条件は全件 [x]、deferred は plain bullet |
| §7 Test 戦略 | Task 9 (unit test) / Task 11 (CI) / Task 13 (markdownlint) / 各 Task の commit 単位で local verify |
| §8 Rollout 順序 | Task 順 (#682 → #624 → #458 → PR) と一致 |

ギャップなし。

### 2. Placeholder scan

- [x] TBD / TODO なし (全 task に exact code or 操作)
- [x] 「TODO: implement later」なし
- [x] 「Add appropriate error handling」のような vague 表現なし
- [x] 「similar to Task N」のような参照のみではなく、各 step に実コード掲載
- [x] section 番号は 5b → 5c → 6 の順で SKILL.md 内に存在することを Task 5 Step 5 の grep で再確認する手順あり

### 3. Type consistency

- `countAcceptanceCriteriaCheckboxes` 関数名は Task 8 / 9 で一貫 (export と test で同一)
- 戻り値構造 `{ unchecked, checked, hasAnySection }` は Task 8 / 9 で一貫
- field id (`reproduction` / `expected` / `actual` / `environment` / `log_file_attachment` / `consent`) は Task 12 全 step / Task 14 PR body で同一
- scenario file 名 (`scenario_e_sweep_central.md` / `scenario_e_sweep_edge_mixed.md` / `scenario_e_sweep_edge_doc_only.md`) は Task 2 / 4 / 6 で同一
- report file 名 (`iter_0_sweep_<scenario>_baseline.md` / `iter_1_sweep_<scenario>_revaluation.md` / `summary_sweep.md`) は Task 4 / 6 / 7 で同一

不整合なし。
