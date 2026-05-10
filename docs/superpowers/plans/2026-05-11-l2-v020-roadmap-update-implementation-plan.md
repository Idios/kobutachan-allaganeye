# L2 v0.2.0 roadmap update — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** L2 v0.2.0 roadmap (`docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md`) を Wave 0 完走 + post-#663 cleanup 12 件追加を反映した新版 (`docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md`) に更新し、旧 plan に Superseded ヘッダを追記する。

**Architecture:** docs-only change (markdown 2 file の create / 1 file の edit、本 plan 自体を含めれば 3 create + 1 edit)。旧 plan は audit trail のため残置 + Superseded ヘッダで誘導。新 plan は spec §4 の構造 (11 group / 3 wave / 6 lane / file 衝突 matrix / 9 brainstorming entry point) を完全表現。実装段階のチェックは markdownlint のみ (コード変更ゼロ)。

**Tech Stack:** Markdown (markdownlint-cli2 v0.18+ 経由 lint) / git / gh CLI

**Spec:** [docs/superpowers/specs/2026-05-11-l2-v020-roadmap-update-design.md](../specs/2026-05-11-l2-v020-roadmap-update-design.md)

---

## File Structure

| path | action | size (approx) | role |
| --- | --- | --- | --- |
| `docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md` | edit (3 行 insert) | +3 lines | 旧 plan 冒頭に Superseded ヘッダ追加 (audit trail 保全) |
| `docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md` | create | ~310 lines | 更新後 roadmap 本体 (11 group / 3 wave / 6 lane) |
| `docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update-implementation-plan.md` | create (本 file) | ~600 lines | 本 implementation plan (writing-plans 出力) |
| `docs/superpowers/specs/2026-05-11-l2-v020-roadmap-update-design.md` | (already created in commit `c41fb6c`) | 262 lines | 原 spec (brainstorming 出力) |

---

## Phase 1: docs 更新 + lint + PR 提出

### Task 1: 旧 plan に Superseded ヘッダ追加

**Files:**

- Modify: `docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md` (1-3 行目の間に挿入)

- [ ] **Step 1: 旧 plan の冒頭 10 行を読んで挿入点を確認**

Use Read tool:

```text
file_path: docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md
limit: 10
```

Expected: 1 行目 `# L2 (v0.2.0) 残作業 roadmap — 8 brainstorming groups`、3 行目 `> **Status**: v0.2.0 release ゲート向け、open issue 棚卸しと再編成`

- [ ] **Step 2: title 行と Status 行の間に Superseded ブロックを挿入**

Use Edit tool:

- `file_path`: `docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md`
- `old_string`:

```text
# L2 (v0.2.0) 残作業 roadmap — 8 brainstorming groups

> **Status**: v0.2.0 release ゲート向け、open issue 棚卸しと再編成
```

- `new_string`:

```text
# L2 (v0.2.0) 残作業 roadmap — 8 brainstorming groups

> **⚠️ Superseded (2026-05-11)**: 本 plan は `docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md` で更新されています。Wave 0 完走 + post-#663 cleanup 12 件追加 (Group I/J/K) + Lane V 新設 + Lane IV 拡張を反映。本ファイルは history (2026-05-07 時点の判断) として保存。

> **Status**: v0.2.0 release ゲート向け、open issue 棚卸しと再編成
```

- [ ] **Step 3: 挿入結果を確認 (冒頭 10 行 read)**

Use Read tool:

```text
file_path: docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md
limit: 10
```

Expected: 1 行目 title、3 行目 `> **⚠️ Superseded (2026-05-11)**: ...`、5 行目 `> **Status**: ...`

- [ ] **Step 4: 個別コミット**

Use Bash tool (HEREDOC 経由で UTF-8 安全に渡す、memory `feedback_gh_command_ja_heredoc.md` 準拠):

```bash
git add docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md
git commit -F - <<'EOF'
docs: 旧 L2 v0.2.0 roadmap (2026-05-07) に Superseded ヘッダ追加

2026-05-11 作成の更新版 (docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md)
への誘導。本文は audit trail として維持。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

Expected: `[claude/affectionate-pare-1619e2 <SHA>] docs: 旧 L2 v0.2.0 roadmap ...` の 1 commit、`1 file changed, 2 insertions(+)`

---

### Task 2: 新 roadmap (2026-05-11 update) を作成

**Files:**

- Create: `docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md`

- [ ] **Step 1: Write tool で新 roadmap を作成**

Use Write tool:

- `file_path`: `docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md`
- `content`: 以下の markdown を **そのまま** Write tool に渡す。spec §4 + 旧 plan §1-§6 構造を踏襲済。

````markdown
# L2 (v0.2.0) 残作業 roadmap (2026-05-11 update) — 11 brainstorming groups (A-K)

> **Status**: v0.2.0 release ゲート向け、Wave 0 完走 + post-#663 cleanup 12 件追加に伴う再編成
> **作成**: 2026-05-11 / session `affectionate-pare-1619e2`
> **Supersedes**: [docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md](2026-05-07-l2-v020-roadmap.md)
> **Spec**: [docs/superpowers/specs/2026-05-11-l2-v020-roadmap-update-design.md](../specs/2026-05-11-l2-v020-roadmap-update-design.md)
> **Scope**: L2 (v0.2.0) 残 OPEN 23 issue / 11 group (8 既存 + 3 新規) / 3 wave / 最大 6 lane 並行

## 1. 完了済 (Wave 0 / 旧 plan からの履歴消化、本 plan の対象外)

### Wave 0 lanes (2026-05-08〜10 完走)

| lane | group | 状態 | merge PR |
| --- | --- | --- | --- |
| Lane I-A | Group A (#663 AppError migration) | ✅ DONE | [PR #689](https://github.com/Idios/kobutachan-allaganeye/pull/689) (2026-05-08) |
| Lane IV-a | Group F (#617 #616 #668 #681 配布) | ✅ DONE | [PR #686](https://github.com/Idios/kobutachan-allaganeye/pull/686) (#616) / [PR #701](https://github.com/Idios/kobutachan-allaganeye/pull/701) (#617) / [PR #702](https://github.com/Idios/kobutachan-allaganeye/pull/702) (#668) / [PR #703](https://github.com/Idios/kobutachan-allaganeye/pull/703) (#681) |
| Lane IV-b | Group G partial (#624 #682) | ✅ DONE | [PR #688](https://github.com/Idios/kobutachan-allaganeye/pull/688) (#624) / [PR #706](https://github.com/Idios/kobutachan-allaganeye/pull/706) (#682) |
| Lane IV-c | Group H (#643 #365) | ✅ DONE | [PR #684](https://github.com/Idios/kobutachan-allaganeye/pull/684) (#643) / [PR #687](https://github.com/Idios/kobutachan-allaganeye/pull/687) (#365) |

### 旧 plan からの主要進捗

- 旧 plan 「Group A AppError 起点」(Lane I-A) が DONE。Group B (Lane I-B) は `with_default_hint()` chain 経由で AppError 経路に乗る前提が成立
- 旧 plan 「Group F l2b 配布 4 件」全件 DONE。`allaganeye.bat` GUI 起動 / portable ZIP versioned 名 / 同梱物 integrity check / `get-pip.py` SHA pin が production
- 旧 plan 「Group G workflow 3 件」のうち 2 件 DONE。残 #458 (bug_report.yml) は本 plan で Lane IV-b' に統合
- 旧 plan 「Group H lint/CLI 2 件」DONE。ESLint window.confirm/alert/prompt block + CLI 進捗バー ETA 表示改善が production
- 旧 plan 注釈「[#365](https://github.com/Idios/kobutachan-allaganeye/issues/365) は v0.2.0 内取り込み disposition」消化済 (#365 closed via PR #687)
- 旧 plan 「[#106](https://github.com/Idios/kobutachan-allaganeye/issues/106) ゼロ環境構築配布親 issue」CLOSED (Wave 0 期間中に handle 済)

## 2. v0.2.0 残作業 — 11 brainstorming groups (A-K)

合計 **23 OPEN issue / 11 groups (8 既存 A-H + 3 新規 I/J/K)**。各 group は 1 spec / 1-7 章で扱える独立 scope。

### Group B: lib.rs 系 backend bugs (3 件、Wave 1 直列)

| # | priority | 概要 |
| --- | --- | --- |
| #679 | P2 (bug) | production build の detect で CMD 窓表示 — `Command::creation_flags(CREATE_NO_WINDOW)` |
| #648 | P3 (bug) | `parse_detect_progress_line` の silent skip — `log::warn` + 既知 prefix doc 化 |
| #644 | P3 (bug) | `run_split` で brightness_samples が metadata.json に書かれない — 出力 + docs 整合 |

**並行安全度**: low (`gui/src-tauri/src/lib.rs` 共有 → 直列必須) / **brainstorming 単位**: 1 spec / 3 章
**直列順**: #679 → #648 → #644 (PR #689 Group A AppError 経路に乗る)

### Group C: PreviewScreen / sample mode UX (3 件、直列推奨)

| # | priority | 概要 |
| --- | --- | --- |
| #633 | P2 | sample mode 全画面 read-only 化 (#589 派生) |
| #645 | P3 | preview 微細タイムライン (±5s 輝度波形) — #465 派生 |
| #677 | P3 (bug) | SideRail のアイコンが選択 UI に見えるが機能なし |

**並行安全度**: mid (PreviewScreen + 5 screen 横断) / **brainstorming 単位**: 1 spec / 3 章
**直列順**: #633 (排他ガード先行) → #645 (編集 UX 拡張後続) / #677 (独立だが画面 UI 系で同 PR 化可)

### Group D: ErrorModal / Export エラー UX (4 件、PR #661 継続 + #696 fold)

| # | priority | 概要 |
| --- | --- | --- |
| #678 | P2 (bug) | Export 失敗時 [object Object] 表示 — error mapping 整理 |
| #669 | P3 | ErrorModal の bug_report テンプレ自動埋込 (#458 連動) |
| #680 | P3 (bug) | Export 出力先 default が存在しないフォルダ — ExportScreen 局所 |
| **#696** | **P3** | **ErrorModal に catch 漏れ AppError fallback 統合 (Refs #614 #663) — `'tauri-command' errorCategory` 実装** ← 新規 fold |

**並行安全度**: low (ExportScreen + ErrorModal 共有 → 直列推奨) / **brainstorming 単位**: 1 spec / 4 章
**直列順**: #678 (error mapping 整える) → #669 (テンプレ埋込) → #680 (default folder) → #696 (AppError fallback、#678 の error mapping 整理が前提)

### Group E: 横断 UI bugs (1 件、Wave 2)

| # | priority | 概要 |
| --- | --- | --- |
| #676 | P3 (bug) | GUI 全画面で file path 表示が不揃い — CSS / token 統一 |

**並行安全度**: low (全画面 path レイアウト) / **brainstorming 単位**: 1 spec / 1 章
**注**: #680 は Group D に fold 済 (旧 plan 「Group E #680」)

### Group G: l2-workflow 残 (1 件、Lane IV-b' で Group J と統合)

| # | priority | 概要 |
| --- | --- | --- |
| #458 | P2 | bug_report.yml (同意チェック付き) 新設 — 外部ユーザー受け入れ準備 |

**並行安全度**: high (`.github/ISSUE_TEMPLATE/bug_report.yml` 独立) / **brainstorming 単位**: Lane IV-b' で Group J と統合 (1 spec / 3 章)

### Group I: post-#663 GUI cleanup (7 件、新規、Lane V 3 phase)

| # | priority | 概要 |
| --- | --- | --- |
| #694 | P3 (refactor) | `*Error` / `*ErrorHint` 並列構造を unified `*ErrorState: AppError|null` に集約 |
| #691 | P3 (refactor) | metadataStore catch path の hint clear 範囲整理 (5 catch path) |
| #693 | P3 | hint UI の `💡` emoji prefix を 5 site 共通化 (`InlineErrorHint` 案) |
| #695 | P3 | ConflictModal で `state.mtime_conflict` の AppError hint 表示 |
| #697 | P3 | DraftRestoreModal に `draftLoadErrorHint` 表示 UI 追加 (dead state 解消) |
| #698 | P3 | DropScreen で recentStore error を user 向け notice 表示 |
| #699 | P3 (doc) | AppError 関連 stale docstring を post-#663 状態に更新 |

**並行安全度**: phase 内 high (5 件 batch、各 file 独立) / phase 間 low (#694 ↔ Phase 1 / Phase 3 直列)
**brainstorming 単位**: 1 spec / 7 章 (3 phase 構成)
**Phase 構成**:

- Phase 1 (Wave 1 main と並行 OK): #691 // #693 // #695 // #697 // #698 (PR 並行可)
- Phase 2 (Wave 1 main 3 lanes merge 後): #694 unified ErrorState refactor (5 screen + 3 modal consumer 一括 refactor)
- Phase 3 (#694 merge 後): #699 docstring (refactor 結果反映)

### Group J: post-#663 workflow polish (2 件、新規、Lane IV-b' 統合)

| # | priority | 概要 |
| --- | --- | --- |
| #692 | P3 | error.rs hint table drift check job 追加 (CI で `error.rs::default_hint_for_code` 22 entries と `docs/tauri-commands.md` の文言一致を保証) |
| #700 | P3 (bug) | markdownlint ignore で nested `gui/node_modules` を除外 (`.markdownlint-cli2.yaml`) |

**並行安全度**: high (CI yml + markdownlint config 独立) / **brainstorming 単位**: Lane IV-b' で Group G #458 と統合 (1 spec / 3 章)

### Group K: l2b cleanup (2 件、新規、Lane IV-e)

| # | priority | 概要 |
| --- | --- | --- |
| #704 | P3 (bug) | Pester PS5.1 + BOM 不在で parse 失敗 (`scripts/tests/build-portable-zip.Tests.ps1`) |
| #705 | P3 | BtbN autobuild URL 陳腐化対策 — release 版 fallback / preflight check |

**並行安全度**: high (Pester scripts と installer ps1 file 独立) / **brainstorming 単位**: 1 spec / 2 章 (PR 並行可)

## 3. 推奨着手順 (依存最小、並行最大)

```text
═══════════════════════════════════════════════════════════════════════════
WAVE 0  (DONE 2026-05-08〜10)
═══════════════════════════════════════════════════════════════════════════
  ✓ Lane I-A    Group A (#663)                     PR #689
  ✓ Lane IV-a   Group F (#617 #616 #668 #681)      PR #686 #701 #702 #703
  ✓ Lane IV-b   Group G partial (#624 #682)        PR #688 #706
  ✓ Lane IV-c   Group H (#643 #365)                PR #684 #687

═══════════════════════════════════════════════════════════════════════════
WAVE 1  (CURRENT — 最大 6 lane 並行可、bandwidth に応じて選択)
═══════════════════════════════════════════════════════════════════════════
  ── Main lanes (P2 含む、新規機能変更) ──

  Lane I-B    Group B (#679 P2 → #648 → #644)
              直列、lib.rs 共有、Group A AppError 経路に乗る
              1 spec / 3 章

  Lane II-a   Group C (#633 P2 → #645 → #677)
              直列、PreviewScreen 共有
              1 spec / 3 章

  Lane II-b   Group D + #696 (#678 P2 → #669 → #680 → #696)
              直列、ExportScreen + ErrorModal + globalErrorListener 共有
              1 spec / 4 章

  ── Polish lanes (P3-low 中心、独立 file) ──

  Lane V      Group I 3-phase (post-#663 GUI cleanup)
              Phase 1 (Wave 1 main と並行 OK):
                #691 // #693 // #695 // #697 // #698 (5 件 batch、PR 並行可)
              Phase 2 (Wave 1 main 3 lanes merge 後):
                #694 unified ErrorState refactor (5 screen + 3 modal consumer 一括)
              Phase 3 (#694 merge 後):
                #699 docstring 更新 (refactor 結果反映)
              1 spec / 7 章 (3 phase 構成)

  Lane IV-b'  Group G remainder + Group J 統合 (workflow / CI / docs polish)
              #458 (P2、bug_report.yml) // #692 (error.rs hint drift CI) // #700 (markdownlint nested ignore)
              file 完全独立、PR 並行可
              1 spec / 3 章

  Lane IV-e   Group K (l2b cleanup)
              #704 (Pester PS5.1 BOM) // #705 (BtbN URL 陳腐化対策、旧 plan 「5 章目」消化)
              file 独立、PR 並行可
              1 spec / 2 章

═══════════════════════════════════════════════════════════════════════════
WAVE 2  (Wave 1 完走後、1 lane)
═══════════════════════════════════════════════════════════════════════════
  Lane III    Group E #676 (横断 file path 表示統一)
              全画面 path レイアウト調整、Wave 1 で screen 編集が安定後
              1 spec / 1 章

═══════════════════════════════════════════════════════════════════════════
WAVE 3  (release gate)
═══════════════════════════════════════════════════════════════════════════
  - docs/l2-e2e-checklist.md 全項目 PASS (Idios 実機検証)
  - 全 PR マージ確認 + base sync
  - /release skill で v0.2.0 タグ + GitHub Release
═══════════════════════════════════════════════════════════════════════════
```

### 各 lane の brainstorming 入り口 (Wave 1: 8 + Wave 2: 1 = 9 entry)

```text
# Wave 1 main (3 lane、P2 含む、即時並行可)
/superpowers:brainstorming Lane I-B: Group B の問題を解決したい (#679 → #648 → #644 lib.rs 直列、Group A AppError 経路)
/superpowers:brainstorming Lane II-a: Group C の問題を解決したい (#633 P2 → #645 → #677 PreviewScreen UX)
/superpowers:brainstorming Lane II-b: Group D + #696 統合 (#678 P2 → #669 → #680 → #696 ExportScreen + ErrorModal)

# Wave 1 polish - Lane V (3 phase、Group I)
/superpowers:brainstorming Lane V Phase 1: Group I 5 件 batch (#691 #693 #695 #697 #698 post-#663 hint UI)
/superpowers:brainstorming Lane V Phase 2: Group I #694 unified ErrorState refactor (Wave 1 main merge 後)
/superpowers:brainstorming Lane V Phase 3: Group I #699 docstring 更新 (#694 merge 後)

# Wave 1 polish - Lane IV (workflow / CI / installer)
/superpowers:brainstorming Lane IV-b': Group G #458 + Group J #692 #700 (workflow / CI / docs polish)
/superpowers:brainstorming Lane IV-e: Group K の問題を解決したい (#704 #705 l2b cleanup)

# Wave 2 (Wave 1 完走後)
/superpowers:brainstorming Lane III: Group E #676 (横断 file path 表示統一)
```

## 3-bis. Lane 構造 (複数セッション並行運用)

複数の Claude Code session を立ち上げて並行作業する場合の lane 設計。各 lane は独立した worktree (`.claude/worktrees/<auto-name>/`) で動かし、ファイル衝突を回避できる単位を `Lane I-B` / `Lane V` 等の lane id で区別する。

### file 共有 matrix (衝突回避の根拠)

| lane | lib.rs | metadataStore | PreviewScreen | ExportScreen | ErrorModal | 5 screens 横断 | ConflictModal | DraftRestoreModal | DropScreen | recentStore | error.rs | CI yml | issue template | markdownlint | Pester | installer ps1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| I-B (Group B) | ✓ | | | | | | | | | | | | | | | |
| II-a (Group C) | | | ✓ | | | (#633) | | | (#633) | | | | | | | |
| II-b (Group D+#696) | | | | ✓ | ✓ | | | | | | | | | | | |
| V Phase 1 (5 件) | | ✓ #691 | | | | | ✓ #695 | ✓ #697 | ✓ #698 | | | | | | | |
| V Phase 2 (#694) | | ✓ refactor | (consumer) | (consumer) | | (consumer) | (consumer) | (consumer) | (consumer) | ✓ refactor | | | | | | |
| V Phase 3 (#699) | | | | | | | | | | | | | | | | (docstring) |
| IV-b' (#458 #692 #700) | | | | | | | | | | | ✓ #692 | ✓ #692 | ✓ #458 | ✓ #700 | | |
| IV-e (#704 #705) | | | | | | | | | | | | | | | ✓ #704 | ✓ #705 |
| III (#676) | | | (path) | (path) | | 全画面 path | | | (path) | | | | | | | |

### 衝突注意点

- **Lane V Phase 2 (#694) ↔ Lane II-a / II-b**: #694 は 5 screen + ConflictModal + DraftRestoreModal + DropScreen の **consumer 一括 refactor**。II-a / II-b の screen 編集が Wave 1 main で進行中なので、**#694 は main 3 lane の merge 後** に着手する (Phase 2 timing)
- **Lane II-a #633 ↔ Lane V Phase 1 #698**: 両方 DropScreen 触る。merge 順序 = 先着優先 + rebase
- **Lane V Phase 1 内 5 件**: 各 file 独立 (metadataStore / shared component / 3 modal / DropScreen)、PR 並行可
- **Lane IV-b' / IV-e 内**: 各々 file 完全独立、PR 並行可
- **Lane III ↔ Wave 1 全 lane**: file path 表示は全画面横断のため、Wave 1 で screen 編集が安定後 (Wave 2) に着手

### 各 wave の同時並行 worktree 数

| wave | 並行 worktree 数 | 主目的 |
| --- | --- | --- |
| wave 0 | 4 (DONE) | A 起点 + F / G / H 独立 polish |
| wave 1 | **6 (max)** | I-B (Rust) + II-a (Preview) + II-b (Export+ErrorModal) + V (post-#663) + IV-b' (workflow) + IV-e (l2b cleanup) |
| wave 2 | 1 | 横断 UI cleanup (Lane III) |
| wave 3 | — | release gate (Idios 実機 + /release) |

最大並行度 = **6 (wave 1)**。bandwidth に応じて 1〜6 lane を選んで並行実行する。

### 並行運用の実務ガイド (各セッションで)

1. **Iron Law 6 PR Pre-flight** を毎回実施
   - `git fetch origin develop-0.2.0` + 取り込み未済 commit 確認
   - `gh pr list --state open --search "claude/"` で他 lane の進捗確認 (並行 6 worktree のため特に重要)
2. **base 同期**: 他 lane が先に merge された場合、`git merge origin/develop-0.2.0` で取り込み後 CI 再実行 (`docs/l2-workflow.md` §PR 作成 Pre-flight 適用)
3. **session-id**: 各 worktree path の最終ディレクトリ名を session-id として PR 本文に記載
4. **bulk 操作禁止**: lane を跨いだ一括 close / 一括 label 付与は AskUserQuestion 必須 (Iron Law 2)
5. **Lane V Phase 2 (#694) gating**: Wave 1 main 3 lane (I-B / II-a / II-b) の **PR merge 完了後**に着手 (file 衝突 matrix 参照)。Phase 1 (5 件 batch) は並行 OK
6. **Lane V Phase 1 #698 / Lane II-a #633 の DropScreen 衝突**: 先着優先 + rebase で吸収

## 4. deferred / v0.2.0 対象外

### v0.2.0 外確定 (deferred ラベル維持、6 件)

| # | 概要 |
| --- | --- |
| #518 | note → warnings: Warning[] 構造化 (将来検討) |
| #635 | PR Test plan checkbox convention 明文化 |
| #670 | 動画 HTTP server 改善 (#618 派生) |
| #671 | E2E test 自動化 feasibility (#484 派生) |
| #432 | Permission denied 全体見直し |
| #374 | metadata.json note AV1 codec 不正確 |

### L1 residual (v0.2.0 外、L1 メンテ pool、6 件)

issue: #412 / #576 / #634 / #652 / #654 / #658 — `l1-residual` ラベル付与済 (旧 plan 注釈「[#365](https://github.com/Idios/kobutachan-allaganeye/issues/365) は v0.2.0 内取り込み」は Group H DONE で消化済、本 plan で l1-residual 残としては扱わない)

### L3+ 将来 layer (多数)

issue: #28 / #32 / #63 / #125-#137 / #139-#152 / #326 / #372-#373 / #376 / #479-#481 — L3 OCR / L4 ML / L5 自動編集 / 拡張 layer (旧 plan の [#106](https://github.com/Idios/kobutachan-allaganeye/issues/106) ゼロ環境構築配布親 issue は CLOSED)

## 5. 関連 doc / Iron Law 整合

### 関連 doc

- [`docs/l2-workflow.md`](../l2-workflow.md) — PR Pre-flight / Self-Test Report / (A) PR 内修正優先 / 実機検証 trigger
- [`docs/system-architecture.md`](../system-architecture.md) — #527 別 exe 方式 / dispatch 表 / Tauri bundle 方針
- [`docs/ui-architecture.md`](../ui-architecture.md) — 画面 5 + phase SM / 排他管理 / エラーハンドリング §4
- [`docs/release-process.md`](../release-process.md) §v0.2.0 固有項目 — release 判定基準
- [`docs/axum-video-server.md`](../axum-video-server.md) (#618 / PR #672) — Tier 0 spec
- [`docs/l2-e2e-checklist.md`](../l2-e2e-checklist.md) (#484 / PR #672) — release gate
- [`docs/tauri-commands.md`](../tauri-commands.md) — Group J #692 (hint table drift check) の対象 (新規参照)
- [`docs/superpowers/specs/2026-05-11-l2-v020-roadmap-update-design.md`](../specs/2026-05-11-l2-v020-roadmap-update-design.md) — 本 plan の原 spec (採用方針 / リスク表 / 受け入れ条件)

### Iron Law 整合 (`.claude/hooks/session-start.sh`)

- **Iron Law 1**: 各 issue の受け入れ条件全項目を逐条検証 — group 内の各章で担保
- **Iron Law 2**: 3 件以上の bulk 操作 (label 変更 / 一括 close / 一括 close 候補追加) は AskUserQuestion 必須
- **Iron Law 3**: scope creep 禁止 — group 内でも 1 PR = 1 章 (= 1 issue) を原則
- **Iron Law 4**: PR / commit に Closes / Fixes / Resolves 禁止、`Refs #N` のみ。マージ後 `/close-issue` で実測再検証
- **Iron Law 6**: PR 作成 Pre-flight (`git fetch origin develop-0.2.0` + 取り込み未済 commit 確認 + 並行 worktree PR 重複確認) 必須

### Memory feedback

- `feedback_gh_command_ja_heredoc.md` — gh CLI 日本語本文は `printf | --body-file -` または HEREDOC
- `feedback_skill_revision_empirical.md` — skill 大幅改訂時は empirical-prompt-tuning 推奨
- `feedback_taskstop_child_process_leak.md` — `run_in_background` + TaskStop の子プロセス残留に注意
- `feedback_powershell_native_redirect.md` — GitHub Actions pwsh で native command 扱う 3 罠 (PR #689 / #688 で実証)
- `feedback_msys_path_conv_git_show.md` — Bash tool 経由 `git show <rev>:<path>` で path 変換 fail (`MSYS_NO_PATHCONV=1` 回避)

## 6. 着手前 Pre-flight チェックリスト

各 group 着手時に再確認:

- [ ] `gh issue view <num>` で受け入れ条件をフルコピー (Iron Law 1)
- [ ] `git fetch origin develop-0.2.0 && git log HEAD..origin/develop-0.2.0 --oneline` で取り込み未済 commit 確認 (Iron Law 6)
- [ ] `gh pr list --search "<元 issue#>" --state all` で並行 worktree PR 重複確認 (Iron Law 6)
- [ ] 着手 group 内に `gui/src-tauri/src/lib.rs` 共有 issue があれば直列順を確認 (Lane I-B = Group B 内直列)
- [ ] 着手 group 内に `gui/src/screens/PreviewScreen.tsx` 共有 issue があれば直列順を確認 (Lane II-a = Group C 内直列)
- [ ] **Lane V Phase 2 (#694) を着手する場合、Wave 1 main 3 lane (I-B / II-a / II-b) の merge 完了を確認** (file 衝突 matrix §3-bis 参照)
- [ ] **Lane V Phase 1 #698 と Lane II-a #633 を並行する場合、`gui/src/screens/DropScreen.tsx` の rebase 順序 (先着優先) を合意済か確認**
````

- [ ] **Step 2: 作成結果を確認 (冒頭 20 行)**

Use Read tool:

```text
file_path: docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md
limit: 20
```

Expected: 1 行目 title `# L2 (v0.2.0) 残作業 roadmap (2026-05-11 update) — 11 brainstorming groups (A-K)`、続いて 5 行の `> **Status**` / `> **作成**` / `> **Supersedes**` / `> **Spec**` / `> **Scope**` ヘッダブロック

- [ ] **Step 3: 末尾を確認 (offset で末尾 20 行)**

Use Read tool:

```text
file_path: docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md
offset: 280
limit: 30
```

Expected: §6 Pre-flight checklist の 7 項目 (うち末尾 2 項目が新規)

- [ ] **Step 4: 必須セクション存在確認 (Grep)**

Use Grep tool:

```text
pattern: ^## [0-9]
path: docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md
output_mode: content
```

Expected (7 セクション、`## 1` から `## 6` + `## 3-bis`):

```text
## 1. 完了済 (Wave 0 / 旧 plan からの履歴消化、本 plan の対象外)
## 2. v0.2.0 残作業 — 11 brainstorming groups (A-K)
## 3. 推奨着手順 (依存最小、並行最大)
## 3-bis. Lane 構造 (複数セッション並行運用)
## 4. deferred / v0.2.0 対象外
## 5. 関連 doc / Iron Law 整合
## 6. 着手前 Pre-flight チェックリスト
```

- [ ] **Step 5: 全 8 group (B/C/D/E/G/I/J/K) 列挙確認 (Grep)**

Use Grep tool:

```text
pattern: ^### Group [BCDEGIJK]
path: docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md
output_mode: content
```

Expected (8 行):

```text
### Group B: lib.rs 系 backend bugs (3 件、Wave 1 直列)
### Group C: PreviewScreen / sample mode UX (3 件、直列推奨)
### Group D: ErrorModal / Export エラー UX (4 件、PR #661 継続 + #696 fold)
### Group E: 横断 UI bugs (1 件、Wave 2)
### Group G: l2-workflow 残 (1 件、Lane IV-b' で Group J と統合)
### Group I: post-#663 GUI cleanup (7 件、新規、Lane V 3 phase)
### Group J: post-#663 workflow polish (2 件、新規、Lane IV-b' 統合)
### Group K: l2b cleanup (2 件、新規、Lane IV-e)
```

注: Group A / F / H は §1 完了済として表で言及、§2 では `### Group X:` heading が出ないので Grep 結果に含まれない (期待動作)

- [ ] **Step 6: 個別コミット**

```bash
git add docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md
git commit -F - <<'EOF'
docs: L2 v0.2.0 roadmap update (2026-05-11、11 group / 3 wave / 6 lane)

2026-05-07 plan を Wave 0 完走 + post-#663 cleanup 12 件追加に伴い更新。

主な変更:
- 11 group 構造 (8 既存 A-H 中 A/F/H は完了、新 I/J/K 追加)
- 23 OPEN issue を v0.2.0 scope (P3-low cleanup も吸収)
- Wave 1 = 6 lane 最大並行 (I-B / II-a / II-b / V / IV-b' / IV-e)
- Group D に #696 fold (ErrorModal 共有のため)
- Group I は 3 phase (Phase 1: 5 件 batch / Phase 2: #694 / Phase 3: #699)
- Lane V Phase 2 (#694) は Wave 1 main 3 lane merge 後に sequencing
- file 衝突 matrix を §3-bis に再掲、Pre-flight checklist に 2 項目追加

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

Expected: `[claude/affectionate-pare-1619e2 <SHA>] docs: L2 v0.2.0 roadmap update ...` の 1 commit、`1 file changed, ~310 insertions(+)`

---

### Task 3: 本 implementation plan 自体をコミット

**Files:**

- (already created via Write tool at start of writing-plans skill execution)

- [ ] **Step 1: 個別コミット**

本 file は writing-plans skill の出力として既に作成済。git で追加してコミット:

```bash
git add docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update-implementation-plan.md
git commit -F - <<'EOF'
docs: L2 v0.2.0 roadmap update implementation plan (writing-plans 出力)

brainstorming spec (commit c41fb6c) → writing-plans 出力。
新 roadmap 作成 (Task 2) + 旧 plan supersede (Task 1) + lint (Task 4)
+ PR 作成 (Task 5/6) を docs-only で完結する 5 task 構成。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

Expected: `[claude/affectionate-pare-1619e2 <SHA>] docs: L2 v0.2.0 roadmap update implementation plan ...` の 1 commit

---

### Task 4: markdownlint 検証

**Files:**

- Verify: 4 files (旧 plan / 新 plan / 本 implementation plan / spec)

- [ ] **Step 1: 変更 file のみ markdownlint 実行**

Use Bash tool:

```bash
npx --yes markdownlint-cli2 \
  docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md \
  docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md \
  docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update-implementation-plan.md \
  docs/superpowers/specs/2026-05-11-l2-v020-roadmap-update-design.md
```

Expected: exit 0 / `Summary: 0 error(s)` (4 file 全て pass)

注 1: project 全体の `bash scripts/check-markdownlint.sh` は #700 (markdownlint ignore で nested gui/node_modules 未対応) のためローカルで noise が多い。本 plan では変更 file 限定でチェックする。
注 2: `markdownlint-cli2` は cwd の `.markdownlint-cli2.yaml` を自動検出し、当 project の段階導入 config (MD013 / MD041 / MD036 disable / MD024 siblings_only / MD022 / MD031 / MD032 / MD040 / MD029 / MD038 / MD028 enabled) を適用する。

- [ ] **Step 2: error がある場合は修正**

If exit ≠ 0:

- error 内容を読み (file:line:rule format)、該当 file を Edit で修正
- 典型的な問題と修正方針:
  - **MD040** (fenced-code-language): code block を ` ``` ` で開始するときに言語タグ追加 (例: ` ```text ` / ` ```bash ` / ` ```markdown `)
  - **MD022** (blanks-around-headings): 見出しの前後に空行を追加
  - **MD031** (blanks-around-fences): code block の前後に空行を追加
  - **MD032** (blanks-around-lists): list の前後に空行を追加
  - **MD029** (ol-prefix): ordered list の番号を `1. 2. 3.` 連番に統一
- Step 1 を再実行して 0 error 確認
- 修正があれば一括コミット:

```bash
git add docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update-implementation-plan.md docs/superpowers/specs/2026-05-11-l2-v020-roadmap-update-design.md
git commit -F - <<'EOF'
docs: markdownlint fix (roadmap update 関連 4 file)

Task 4 Step 1 で検出された markdownlint 違反を修正。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

If exit = 0: skip directly to Task 5.

---

### Task 5: PR 作成 Pre-flight (Iron Law 6)

**Files:** (なし、git / gh CLI 操作のみ)

- [ ] **Step 1: develop-0.2.0 base sync 確認**

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline
```

Expected: 取り込み未済 commit が 0 件 (もしくはあれば次 step で取り込み判定)

- [ ] **Step 2: 取り込み未済 commit がある場合の対応**

If 取り込み未済 commit がある:

- 各 commit が touch する file を確認:

  ```bash
  git log HEAD..origin/develop-0.2.0 --name-only --format='---%n%H %s'
  ```

- 当 PR の touched files (4 file: 旧 plan / 新 plan / 本 implementation plan / spec) と交差する commit があるなら:

  ```bash
  git merge origin/develop-0.2.0
  ```

  続けて Task 4 Step 1 (markdownlint) を再実行
- 交差しないなら fetch 結果のみ記録して進む

If 取り込み未済 commit が 0 件: そのまま Step 3 へ進む

- [ ] **Step 3: 並行 worktree PR 重複確認**

```bash
gh pr list --state open --search "claude/" --json number,title,headRefName --jq '.[] | "PR#\(.number) [\(.headRefName)] \(.title)"'
```

Expected: roadmap update を扱う他 PR が表示されない (本 PR が唯一のはず。L2 lane 系の他 PR が並行している場合は表示されるが、touched files が交差しなければ問題なし)

If 同じ docs (`docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md` 等) を編集している他 PR がある場合: 即時停止して `AskUserQuestion` でユーザー判断を仰ぐ (Iron Law 6 違反回避)

- [ ] **Step 4: branch を origin に push**

```bash
git push -u origin claude/affectionate-pare-1619e2
```

Expected: branch が remote に反映、`gh pr create` が使える状態

---

### Task 6: PR 作成

**Files:** (なし、gh CLI のみ)

- [ ] **Step 1: PR 本文を draft (Iron Law 4 遵守: Closes/Fixes/Resolves 禁止)**

PR body の全文 (markdown):

````markdown
## 概要

L2 v0.2.0 roadmap (`docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md`、2026-05-07 作成) を Wave 0 完走 + post-#663 cleanup 12 件追加に伴い更新する。新規 plan file (`docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md`) を作成し、旧 plan に Superseded ヘッダを追記する。

## 変更内容

- **(新規)** `docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md`
  - 11 group (8 既存 A-H + 新規 I/J/K) / 3 wave / 6 lane 最大並行の更新後 roadmap
  - 23 OPEN issue を v0.2.0 scope (Wave 1 残)
  - file 衝突 matrix 再掲、Pre-flight checklist に 2 項目追加
- **(新規)** `docs/superpowers/specs/2026-05-11-l2-v020-roadmap-update-design.md`
  - 本 PR の brainstorming 設計 (採用方針 / 受け入れ条件 / リスク表)
- **(新規)** `docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update-implementation-plan.md`
  - 本 PR の implementation plan (writing-plans 出力)
- **(編集)** `docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md`
  - 冒頭に Superseded ヘッダ追加 (本文維持、audit trail 保全)

## 主な決定事項 (spec §2 で確定)

- **v0.2.0 scope** = 全 23 件 (新規 12 件 P3-low cleanup も吸収) — release 直前の品質一段上を優先
- **Group I/J/K 新設** + **#696 を Group D に fold** (ErrorModal 共有のため file 衝突回避)
- **Wave 1 = 最大 6 lane 並行** (file isolation 根拠: §3-bis matrix)、bandwidth に応じて 1-6 lane を選択
- **Lane V Phase 2 (#694) は Wave 1 main 3 lane merge 後に sequencing** (5 screen + 3 modal consumer 一括 refactor のため)

## Self-Test Report (docs-only)

- [x] markdownlint 4 file 全て pass (Task 4)
- [x] 新 plan の必須セクション 7 個 (`## 1` `## 2` `## 3` `## 3-bis` `## 4` `## 5` `## 6`) を Grep で確認 (Task 2 Step 4)
- [x] 新 plan の Group A-K のうち §2 列挙対象 8 group (B/C/D/E/G/I/J/K) を Grep で確認 (Task 2 Step 5)
- [x] Iron Law 6 PR Pre-flight (base sync / 並行 worktree PR) 実施 (Task 5)
- [x] Iron Law 4 (Closes/Fixes/Resolves 禁止) 遵守 — 本 PR は doc 更新のみで issue close なし

## 関連 issue (Refs のみ、Closes は使用しない)

本 PR は roadmap doc 更新のみで、いずれの issue も close しない。本 plan が参照する 23 OPEN issue:

- Group B: #679 #648 #644
- Group C: #633 #645 #677
- Group D: #678 #669 #680 #696
- Group E: #676
- Group G: #458
- Group I: #691 #693 #694 #695 #697 #698 #699
- Group J: #692 #700
- Group K: #704 #705

session-id: `affectionate-pare-1619e2`
````

注: `Closes` / `Fixes` / `Resolves` キーワードは Iron Law 4 で禁止。本 PR は doc 更新のみで issue close しないため、当然 `Closes` 不要。

- [ ] **Step 2: gh pr create で PR を作成 (`--body-file -` で stdin 経由、UTF-8 安全)**

PR body を heredoc で stdin に流し、`gh pr create --body-file -` で受ける (memory `feedback_gh_command_ja_heredoc.md` 準拠):

```bash
gh pr create \
  --base develop-0.2.0 \
  --title "docs: L2 v0.2.0 roadmap update (2026-05-11、11 group / 6 lane)" \
  --body-file - <<'EOF'
## 概要

L2 v0.2.0 roadmap (`docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md`、2026-05-07 作成) を Wave 0 完走 + post-#663 cleanup 12 件追加に伴い更新する。新規 plan file (`docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md`) を作成し、旧 plan に Superseded ヘッダを追記する。

## 変更内容

- **(新規)** `docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md`
  - 11 group (8 既存 A-H + 新規 I/J/K) / 3 wave / 6 lane 最大並行の更新後 roadmap
  - 23 OPEN issue を v0.2.0 scope (Wave 1 残)
  - file 衝突 matrix 再掲、Pre-flight checklist に 2 項目追加
- **(新規)** `docs/superpowers/specs/2026-05-11-l2-v020-roadmap-update-design.md`
  - 本 PR の brainstorming 設計 (採用方針 / 受け入れ条件 / リスク表)
- **(新規)** `docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update-implementation-plan.md`
  - 本 PR の implementation plan (writing-plans 出力)
- **(編集)** `docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md`
  - 冒頭に Superseded ヘッダ追加 (本文維持、audit trail 保全)

## 主な決定事項 (spec §2 で確定)

- **v0.2.0 scope** = 全 23 件 (新規 12 件 P3-low cleanup も吸収) — release 直前の品質一段上を優先
- **Group I/J/K 新設** + **#696 を Group D に fold** (ErrorModal 共有のため file 衝突回避)
- **Wave 1 = 最大 6 lane 並行** (file isolation 根拠: §3-bis matrix)、bandwidth に応じて 1-6 lane を選択
- **Lane V Phase 2 (#694) は Wave 1 main 3 lane merge 後に sequencing** (5 screen + 3 modal consumer 一括 refactor のため)

## Self-Test Report (docs-only)

- [x] markdownlint 4 file 全て pass
- [x] 新 plan の必須セクション 7 個 (`## 1` `## 2` `## 3` `## 3-bis` `## 4` `## 5` `## 6`) を Grep で確認
- [x] 新 plan の Group A-K のうち §2 列挙対象 8 group (B/C/D/E/G/I/J/K) を Grep で確認
- [x] Iron Law 6 PR Pre-flight (base sync / 並行 worktree PR) 実施
- [x] Iron Law 4 (Closes/Fixes/Resolves 禁止) 遵守 — 本 PR は doc 更新のみで issue close なし

## 関連 issue (Refs のみ、Closes は使用しない)

本 PR は roadmap doc 更新のみで、いずれの issue も close しない。本 plan が参照する 23 OPEN issue:

- Group B: #679 #648 #644
- Group C: #633 #645 #677
- Group D: #678 #669 #680 #696
- Group E: #676
- Group G: #458
- Group I: #691 #693 #694 #695 #697 #698 #699
- Group J: #692 #700
- Group K: #704 #705

session-id: `affectionate-pare-1619e2`
EOF
```

Expected: `https://github.com/Idios/kobutachan-allaganeye/pull/<NEW_PR>` が出力される

- [ ] **Step 3: PR 番号を取得し動作確認**

```bash
gh pr view --json number,url,title --jq '"PR#\(.number): \(.title)\n\(.url)"'
```

Expected: PR 番号 + URL を取得、`gh pr checks` で CI が回り始めているか確認

- [ ] **Step 4: ユーザーに完了報告**

Markdown 形式で:

- 作成 PR 番号 + URL (clickable)
- 含まれる変更 (4 file: 新 plan / spec / 本 implementation plan / 旧 plan supersede)
- 次の lane (Wave 1 brainstorming entry の 1 つ) を提案 (例: Lane I-B が `#679` P2 含むので最優先候補)

---

## Self-Review Checklist (本 plan の)

writing-plans skill 完了直前に実施 (本 plan を書いた人 = AI 自身):

- [x] **Spec coverage**: spec §1-§10 各章を一通り読み、対応する task を確認
  - §1 背景 → Goal + Architecture で吸収
  - §2 採用方針 → Task 2 の content + PR body の「主な決定事項」で表現
  - §3 成果物 (file 構成) → File Structure 表 + Task 1-3
  - §3.3 Superseded ヘッダ文言 → Task 1 Step 2 の `new_string` で完全一致
  - §4 更新後 roadmap 構造 → Task 2 Step 1 の embedded markdown で完全表現
  - §5 deferred / §6 関連 doc / §7 Pre-flight → Task 2 Step 1 content の §4-§6 で網羅
  - §8 受け入れ条件 → 本 plan 末尾の「受け入れ条件」セクションで対応
  - §9 非ゴール → 本 plan の scope に含めない (Iron Law 整合)
  - §10 リスク / 対応 → Task 5 (Pre-flight) + Pre-flight checklist 2 項目で吸収
- [x] **Placeholder scan**: 本 plan 内に `TBD` / `TODO` / `implement later` / `add appropriate error handling` 等のプレースホルダなし
- [x] **Type consistency**: file path は全 task で同一文字列 (`docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md` 等)、commit hash 参照は `c41fb6c` (spec commit) のみ言及、PR 番号参照は #689 / #686 / #687 / #688 / #701 / #702 / #703 / #706 のみ (実在確認済)
- [x] **Iron Law 整合**: Task 1 / Task 2 / Task 3 の commit message は Closes / Fixes / Resolves キーワード不使用、Task 6 の PR body も同様、Task 5 で base sync 確認、Task 4 で markdownlint 強制

---

## 受け入れ条件 (本 plan execution の)

実行完了時、以下が満たされること (spec §8 を踏襲):

- [ ] 新規 plan file `docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md` が spec §4 完全表現済 (Group A-K / Wave 0-3 / 6 lane / 9 entry / 衝突 matrix / Pre-flight 7 項目)
- [ ] 旧 plan file `docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md` の冒頭に Superseded ブロック挿入済 (本文維持)
- [ ] 本 implementation plan file `docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update-implementation-plan.md` が commit 済
- [ ] 全 4 file が markdownlint pass (Task 4 Step 1 で `Summary: 0 error(s)`)
- [ ] PR が `develop-0.2.0` base で作成され、本文に Closes/Fixes/Resolves キーワード 0 個、session-id `affectionate-pare-1619e2` 記載あり
- [ ] PR の base sync (Iron Law 6 Pre-flight) 実施済 (Task 5 Step 1-3)
- [ ] PR URL がユーザーに報告済
