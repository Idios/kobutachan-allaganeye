# L-δ Codex 統合運用化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** retro spec の L-δ (Codex 統合運用化) を 2 PR で実装。C5 (superpowers subagent → Codex 直列構成 doc) / C1 運用化最終文書を完成させ、Codex 関連の整合性 (Pre-flight Step 5 / Codex fallback / CLAUDE.md §Codex 運用) を polish する。L-β β-4 / β-5 で skill 側の組み込みは完了済、本 Lane は doc の最終 polish と直列構成の視覚化が中心。

**Architecture:** 2 PR は独立 reviewable。δ-1 で C5 直列構成 doc を新設し flow を ascii / mermaid 図で示す、δ-2 で C1 / C2 / C3 / C4 / C6 の整合性 polish (相互参照リンク強化、example 追加、漏れがあれば補正)。

**Tech Stack:** Markdown + ASCII art / mermaid + markdownlint-cli2

**Spec reference:** [docs/superpowers/specs/2026-05-17-v020-v021-retro-codex-integration-design.md](../specs/2026-05-17-v020-v021-retro-codex-integration-design.md) §C1 / §C5

**Worktree:** `E:\projects\kobutachan-tools\kobutachan-allaganeye\.claude\worktrees\nervous-hoover-464244` (branch: `claude/nervous-hoover-464244`, base: `develop-0.3.0`)

---

## File Structure

| 種別 | path | 担当 Task |
| --- | --- | --- |
| 更新 | `docs/l2-workflow.md` (§subagent + Codex 直列構成 新設) | Task 1 (δ-1) |
| 更新 | `CLAUDE.md` (§Codex 運用 と他 § の整合確認、漏れ polish) | Task 2 (δ-2) |
| 更新 | `docs/l2-workflow.md` (§Codex fallback の example 追加) | Task 2 (δ-2) |
| 更新 | `.claude/skills/release/SKILL.md` (Step 0c の Track B 連携への明示) | Task 2 (δ-2、必要な場合のみ) |

---

## Pre-flight (実装開始前に 1 回)

- [ ] **Step 0.1: base 同期**

```bash
git fetch origin develop-0.3.0
git status
```

- [ ] **Step 0.2: Codex 関連 § の現状確認**

```bash
echo "--- CLAUDE.md §Codex 運用 ---"
grep -n "^## Codex\|^### " CLAUDE.md | head -20
echo "--- docs/l2-workflow.md Codex sections ---"
grep -n "Codex" docs/l2-workflow.md
echo "--- review-pr Codex sections ---"
grep -n "codex\|Codex" .claude/skills/review-pr/SKILL.md
```

L-β β-4 / β-5 で組み込まれた既存記述を確認し、δ-1 / δ-2 で追加すべき差分を把握。

---

## Task 1 (PR δ-1, C5): superpowers subagent → Codex 直列構成 doc

**Files:**

- Modify: `docs/l2-workflow.md` (§subagent + Codex 直列構成 新設、`§Codex fallback` の直後)

### 設計判断

spec §C5 の通り、superpowers `subagent-driven-development` で fresh subagent が実装した後、controller が Codex `/codex:review` で adversarial pass を行う直列ワークフローを doc 化する。**並列ではなく直列**推奨 (Codex 自身に fix させない、Iron Law 整合)。Iron Law 6 Pre-flight Step 5 (C2 で導入) とは別の用途 — こちらは PR の review 段階 (review-pr) での deep-dive。

flow 図 (ASCII art) で 4 ステップを視覚化:

1. superpowers subagent が実装 + 2-stage review (spec + code quality)
2. controller (Claude main) が subagent commit を branch HEAD に到達確認 (M6 と整合)
3. `/codex:review` で adversarial pass
4. Codex finding を triage

### 実装手順

- [ ] **Step 1.1: docs/l2-workflow.md の `§Codex fallback` の直後に §subagent + Codex 直列構成 を新設**

`.docs/l2-workflow.md` の §Codex fallback 末尾 (fallback の限界の直後) に以下を追加:

```markdown
## subagent + Codex 直列構成 (C5)

大規模実装 / 重要 PR では superpowers `subagent-driven-development` (Claude 内 fresh subagent) と Codex `/codex:review` (GPT-5.4) を **直列**で組み合わせる。並列ではなく直列にする理由: Codex 自身に fix させない (Iron Law 3 / 5 整合)。

### Flow

\`\`\`text
┌─────────────────────────────────────────────────────────────┐
│ Stage 1: Claude 内 fresh subagent が実装                     │
│         (superpowers:subagent-driven-development)            │
│         - per-task subagent dispatch                         │
│         - 2-stage review (spec reviewer + code quality)      │
│         - HARD-GATE: scope を超える発見 → BLOCKED 報告       │
└─────────────────────────────────────────────────────────────┘
                            ↓ commit on claude/<branch>
┌─────────────────────────────────────────────────────────────┐
│ Stage 2: controller (Claude main) が到達確認 (M6 整合)        │
│         git log <branch> --oneline -5 | grep <SHA>           │
│         orphan commit 検出 → cherry-pick で復旧               │
└─────────────────────────────────────────────────────────────┘
                            ↓ branch HEAD が想定 SHA を含む
┌─────────────────────────────────────────────────────────────┐
│ Stage 3: /codex:review (Codex GPT-5.4) で adversarial pass    │
│         独立 model の second opinion                          │
│         focus 文字列で project 固有焦点                       │
│         Codex 自身に commit させない (M3 整合)                │
│         fail 時は §Codex fallback (C6) に従う                 │
└─────────────────────────────────────────────────────────────┘
                            ↓ Codex finding (read-only)
┌─────────────────────────────────────────────────────────────┐
│ Stage 4: controller + Idios で triage                         │
│         /review-pr Step 5b の (A) / (B) / (C) 分類            │
│         Codex finding は 出所 = codex:review として統合        │
└─────────────────────────────────────────────────────────────┘
\`\`\`

### Iron Law 6 Pre-flight Step 5 との違い

| 軸 | Iron Law 6 Pre-flight Step 5 (C2) | subagent + Codex 直列構成 (C5、本節) |
| --- | --- | --- |
| 起動タイミング | PR 作成**直前** (Step 0-4 通過後) | `/review-pr` 段階の **deep-dive** (Step 5a) |
| Codex command | `/codex:adversarial-review` (approve させない姿勢) | `/codex:review` (code quality 一般) |
| 必須 / オプション | **必須** (Pre-flight ゲート) | optional (起動条件: 大規模 PR / 過去 root cause 複数 / L1 core) |
| 直前 stage | Step 4 並行 PR 重複再確認 | superpowers subagent 実装 + reachability 確認 |

### 並列ではなく直列にする理由

- Codex に fix させると Iron Law 3 (scope creep) / Iron Law 5 (independent judgment) の衝突リスク
- superpowers subagent (Claude 思考体) と Codex (GPT-5.4) を並列起動しても finding が重複するだけで bias は減らない
- 直列で「実装 → reachability → adversarial review → triage」と段階化すると、各 stage で人 (Idios) が介入できる checkpoint が確保される

### Fallback (Codex fail 時)

Stage 3 で Codex CLI が token 枯渇 / network failure 等で fail した場合は §Codex fallback (C6) に従い、superpowers `requesting-code-review` subagent を Stage 3 の代替として起動する。Stage 4 triage は同様に実施し、fallback notice を report に必須記載する。
```

- [ ] **Step 1.2: markdownlint check**

```bash
npx --prefix gui markdownlint-cli2 docs/l2-workflow.md
```

Expected: 0 error。

- [ ] **Step 1.3: PR δ-1 commit**

```bash
git add docs/l2-workflow.md
git commit -m "$(cat <<'EOF'
docs(workflow): subagent + Codex 直列構成を codify (Refs spec L-δ C5)

retro spec §C5 の実装。superpowers subagent-driven-development (Claude 内
fresh subagent) と Codex /codex:review (GPT-5.4) を直列で組み合わせる flow
を docs/l2-workflow.md §subagent + Codex 直列構成 として codify。

4 stage flow (ASCII art):
1. Claude 内 fresh subagent が実装 (HARD-GATE: BLOCKED 報告)
2. controller が到達確認 (M6 整合、orphan commit 検出 + cherry-pick 復旧)
3. /codex:review で adversarial pass (Codex 自身に commit させない、M3 整合)
4. controller + Idios で triage (/review-pr Step 5b に統合)

並列ではなく直列にする理由 (Iron Law 3 / 5 衝突回避) を明記。Iron Law 6
Pre-flight Step 5 (C2、PR 作成直前 / 必須) との違い table 追記。fail 時は
§Codex fallback (C6) に倒れる連携も明示。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2 (PR δ-2, C1 + 整合 polish): Codex 関連 doc の最終 polish

**Files:**

- Modify: `CLAUDE.md` (§Codex 運用 の最終 polish、過不足補正)
- Modify: `docs/l2-workflow.md` (§Codex fallback の example 追加、§subagent + Codex 直列構成 への相互参照)
- Modify: `.claude/skills/release/SKILL.md` (Step 0c → Track B 連携の明示、必要な場合のみ)

### 設計判断

L-β β-4 / β-5 で skill 側は組み込み済。L-δ δ-2 では:

1. CLAUDE.md §Codex 運用 を Read で確認し、L-β で書いた内容を最終 polish (重複削除 / 漏れ補正)
2. docs/l2-workflow.md §Codex fallback に具体 example (stderr keyword match の擬似コード) を追加
3. spec §C1-§C6 の cross-reference が CLAUDE.md / docs / skill 全体で整合しているか最終 audit

C1 は「review gate は OFF のまま、`/review-pr` `/iterate-review` 経由 invocation」が確定値 (spec O1 (b))。L-β β-4 で skill / docs / CLAUDE.md に既に書かれているため、本 PR では polish のみ。

### 実装手順

- [ ] **Step 2.1: CLAUDE.md §Codex 運用 を Read で確認**

```bash
sed -n '/^## Codex 運用/,/^## /p' CLAUDE.md | head -50
```

L-β β-4 で書いた内容を確認。

- [ ] **Step 2.2: docs/l2-workflow.md §Codex fallback に擬似コード example を追加**

§Codex fallback の検出条件 table の直後に以下を追加:

```markdown
### 検出 + fallback の擬似コード (skill 内実装イメージ)

`/review-pr` Step 5a / `/iterate-review` Round 2.1 等で Codex を invoke した後の処理イメージ:

\`\`\`text
result = invoke("/codex:review --base develop-0.3.0 --focus '...'")

if result.exit_code != 0:
    stderr = result.stderr.lower()
    if matches_any(stderr, ["rate", "quota", "429", "usage_limit"]):
        fallback_reason = "token 枯渇"
        invoke_fallback("superpowers:requesting-code-review")
    elif matches_any(stderr, ["auth", "unauthorized", "401", "403", "api"]):
        fallback_reason = "認証失敗"
        invoke_fallback("superpowers:requesting-code-review")
        notify_user("Codex auth failed; check token / api key")
    elif matches_any(stderr, ["timeout", "EHOSTUNREACH", "ENETUNREACH", "ECONNRESET"]):
        fallback_reason = "network failure"
        invoke_fallback("superpowers:requesting-code-review")
    else:
        # 曖昧 → user 判断
        ask_user_question(["再試行", "Claude fallback", "abort"])
elif result.stdout.empty() or not parseable(result.stdout):
    fallback_reason = "応答異常"
    ask_user_question(["再試行", "Claude fallback", "abort"])
else:
    integrate_findings(result.stdout)

if fallback_invoked:
    report.append(format_fallback_notice(fallback_reason, result.stderr[:200]))
\`\`\`

実装は skill prompt 側 (review-pr / iterate-review SKILL.md の Step 5a / Step 2.1) で行う。Codex CLI のラッパー (`codex-companion.mjs`) との連携詳細は plugin doc を参照。
```

- [ ] **Step 2.3: docs/l2-workflow.md §Codex fallback から §subagent + Codex 直列構成 へのリンクを追加**

§Codex fallback の冒頭 paragraph に「Stage 3 が fail した場合の fallback として機能する」と明記済 (δ-1 で追加した直列構成の Stage 3)。L-δ δ-2 で確認のみ、必要なら cross-reference を補強。

- [ ] **Step 2.4: CLAUDE.md §Codex 運用 を最終 polish**

L-β β-4 で書いた §Codex 運用 の内容を確認し、以下の polish を実施:

- §C5 (直列構成) への参照リンクを §Codex 運用 内に追加 (δ-1 で新設したため)
- §C6 fallback の参照リンクが正しく `docs/l2-workflow.md#codex-fallback` を指しているか確認
- §review/adversarial-review (C2/C3) / §rescue (C4) / §Token 枯渇時の fallback (C6) の連携が筋道立てて書かれているか read で確認

不備があれば編集 (微修正のみ、内容は変えない)。

- [ ] **Step 2.5: spec §C1-§C6 の cross-reference を最終 audit**

```bash
grep -rnE "spec L-β|spec L-δ|spec L-γ|C1|C2|C3|C4|C5|C6" .claude/skills/ CLAUDE.md docs/l2-workflow.md 2>&1 | head -30
```

各 spec § への参照リンクが正しく設置されているか確認。リンク先 anchor が正しいかを `npx markdownlint --check` 含めて確認。

- [ ] **Step 2.6: /release SKILL.md Step 0c から Track B 連携の明示を強化 (必要な場合のみ)**

L-β β-3 で /release SKILL.md に Step 0c が追加済。Track B PR への連携が明示されているか確認。docs/release-process.md §Patch release の Track 構造 (A2、L-γ γ-2 で追加) との cross-reference が正しいか read で確認。問題なければ編集不要。

- [ ] **Step 2.7: 最終 markdownlint + commit**

```bash
npx --prefix gui markdownlint-cli2 CLAUDE.md docs/l2-workflow.md .claude/skills/release/SKILL.md 2>&1 | tail -3
```

Expected: 0 error。

```bash
git add CLAUDE.md docs/l2-workflow.md .claude/skills/release/SKILL.md
# (release SKILL.md は変更なしの可能性あり、その場合は add しない)
git commit -m "$(cat <<'EOF'
docs: Codex 統合運用の最終 polish (Refs spec L-δ C1 / 整合 audit)

retro spec L-δ の最終 polish。L-β β-4 / β-5 で skill / docs に組み込んだ
Codex 統合の整合性を audit し、不足を補正。

docs/l2-workflow.md:
- §Codex fallback に検出 + fallback の擬似コード example 追加 (skill prompt
  実装イメージとして)
- §subagent + Codex 直列構成 (δ-1) との cross-reference 確認

CLAUDE.md:
- §Codex 運用 の polish: §C5 (直列構成) への参照リンク追加、C2/C3/C4/C6
  の連携が筋道立てて読めるよう微修正

C1 (review gate OFF 維持、/review-pr /iterate-review 経由 invocation) は
L-β β-4 で skill / docs / CLAUDE.md に組み込み済。本 PR で運用化文書を確定。

L-γ / L-α / L-β / L-δ 全 Lane 完了で retro spec の機構化を実装完遂。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Lane 完了後の最終確認

- [ ] **Step 3.1: branch HEAD に 2 commit (δ-1 / δ-2)**

```bash
git log --oneline -15
```

- [ ] **Step 3.2: 全 markdownlint + pytest hooks pass**

```bash
bash scripts/check-markdownlint.sh
python -m pytest tests/hooks/ -q
```

- [ ] **Step 3.3: retro spec 全 Lane 完了確認**

L-γ (3 PR) + L-α (3 PR) + L-β (5 PR) + L-δ (2 PR) = **13 PR 完了**。retro spec §5 Lane 表の合計 PR 数 (約 13 PR) と一致することを確認。

- [ ] **Step 3.4: PR 化の最終判断**

全 Lane 完了したため、ブランチを develop-0.3.0 base の PR として提出する。

---

## 受け入れ基準 (L-δ 全体)

spec §C1 / §C5 の docs / 運用化が完成:

- [x] `docs/l2-workflow.md` §subagent + Codex 直列構成 が存在 (Flow 図 + Iron Law 6 Pre-flight Step 5 との違い table) (C5)
- [x] `docs/l2-workflow.md` §Codex fallback に擬似コード example が追加
- [x] CLAUDE.md §Codex 運用 が L-β β-4 で書かれた内容 + L-δ δ-1 の C5 リンクで完結
- [x] spec §C1-§C6 の cross-reference が CLAUDE.md / docs / skill 全体で整合

## リスクと緩和策

| # | リスク | 緩和 |
| --- | --- | --- |
| RL1 | δ-1 の ASCII art が markdownlint code block で誤判定される | code block 内は lint 対象外、確認は markdownlint pass で十分 |
| RL2 | δ-2 が「変更なし PR」になる (L-β β-4 で書かれた内容で十分な場合) | δ-2 は polish PR、変更が少なくとも完了価値あり。最低限 §Codex fallback の擬似コード example だけは追加する |

---

## 次の Lane plan は無し (L-δ で retro spec 全 Lane 完了)
