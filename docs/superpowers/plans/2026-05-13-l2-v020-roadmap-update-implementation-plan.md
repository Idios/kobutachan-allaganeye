# L2 v0.2.0 roadmap 再更新 — implementation plan (2026-05-13)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** L2 v0.2.0 roadmap (`docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md`、PR #709 で merge 済) を Wave 1 lanes の大半完走 + 新規 4 件 (Group G ext + Group L + Group M) + #458 scope-out 確定に伴い再更新する。新版 (`docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md`) を作成し、旧 plan に chain 方式 Superseded ヘッダを追記する。

**Architecture:** docs-only change (markdown 3 file の create + 1 file の edit)。chain 方式で 2026-05-07 → 2026-05-11 → 2026-05-13 の audit trail を保ち、各 plan は immediate successor を指す Supersede header を持つ。新 plan は spec §4 (13 group / 3 wave / 8 lane wave 1 / file 衝突 matrix / 8 brainstorming entry / Pre-flight 8 項目) を完全表現。実装段階のチェックは markdownlint のみ。

**Tech Stack:** Markdown (markdownlint-cli2 経由 lint) / git / gh CLI / Bash HEREDOC (日本語 UTF-8 安全)

**Spec:** [docs/superpowers/specs/2026-05-13-l2-v020-roadmap-update-design.md](../specs/2026-05-13-l2-v020-roadmap-update-design.md)

---

## File Structure

| path | action | size (approx) | role |
| --- | --- | --- | --- |
| `docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md` | edit (3 行 insert) | +3 lines | 旧 plan 冒頭に Superseded ヘッダ追加 (audit trail 保全、chain 方式) |
| `docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md` | create | ~320 lines | 更新後 roadmap 本体 (13 group / 3 wave / 8 lane wave 1) |
| `docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update-implementation-plan.md` | create (本 file) | ~650 lines | 本 implementation plan (writing-plans 出力) |
| `docs/superpowers/specs/2026-05-13-l2-v020-roadmap-update-design.md` | (already committed: `78d639c` → `47fbfc6` → `5980e60`) | 302 lines | 原 spec (brainstorming 出力) |

---

## Phase 1: docs 更新 + lint + PR 提出

### Task 1: 旧 plan (2026-05-11) に Superseded ヘッダ追加

**Files:**

- Modify: `docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md` (title 行と Status 行の間に挿入)

- [ ] **Step 1: 旧 plan の冒頭 10 行を読んで挿入点を確認**

Use Read tool:

```text
file_path: docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md
limit: 10
```

Expected: 1 行目 `# L2 (v0.2.0) 残作業 roadmap (2026-05-11 update) — 11 brainstorming groups (A-K)`、3 行目 `> **Status**: v0.2.0 release ゲート向け、Wave 0 完走 + post-#663 cleanup 12 件追加に伴う再編成`

- [ ] **Step 2: title 行と Status 行の間に Superseded ブロックを挿入**

Use Edit tool:

- `file_path`: `docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md`
- `old_string`:

```text
# L2 (v0.2.0) 残作業 roadmap (2026-05-11 update) — 11 brainstorming groups (A-K)

> **Status**: v0.2.0 release ゲート向け、Wave 0 完走 + post-#663 cleanup 12 件追加に伴う再編成
```

- `new_string` (markdownlint MD028 回避のため `>` で blockquote 連結):

```text
# L2 (v0.2.0) 残作業 roadmap (2026-05-11 update) — 11 brainstorming groups (A-K)

> **⚠️ Superseded (2026-05-13)**: 本 plan は `docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md` で更新されています。Wave 1 lanes の大半完走 (旧 plan 23 件中 14 件 CLOSED + 3 件 pending close 含 #458 scope-out) + 新規 4 件 (Group G ext + Group L + Group M) 追加を反映。本ファイルは history (2026-05-11 時点の判断) として保存。
>
> **Status**: v0.2.0 release ゲート向け、Wave 0 完走 + post-#663 cleanup 12 件追加に伴う再編成
```

- [ ] **Step 3: 挿入結果を確認 (冒頭 10 行 read)**

Use Read tool:

```text
file_path: docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md
limit: 10
```

Expected: 1 行目 title、3 行目 `> **⚠️ Superseded (2026-05-13)**: ...`、5 行目 `> **Status**: ...`

- [ ] **Step 4: 個別コミット (HEREDOC で UTF-8 安全に渡す)**

```bash
git add docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md
git commit -F - <<'EOF'
docs: 2026-05-11 L2 roadmap に Superseded ヘッダ追加

2026-05-13 作成の更新版 (docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md)
への誘導。本文は audit trail として維持。chain 方式で 2026-05-07 → 2026-05-11 → 2026-05-13。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

Expected: `[claude/affectionate-pare-1619e2 <SHA>] docs: 2026-05-11 L2 roadmap ...` の 1 commit、`1 file changed, 2 insertions(+)`

---

### Task 2: 新 roadmap (2026-05-13 update) を作成

**Files:**

- Create: `docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md`

- [ ] **Step 1: Write tool で新 roadmap を作成**

Use Write tool:

- `file_path`: `docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md`
- `content`: 以下の markdown を **そのまま** Write tool に渡す。spec §4 + 2026-05-11 plan の §1-§6 構造を踏襲、markdownlint MD028 / MD056 を事前回避済。

````markdown
# L2 (v0.2.0) 残作業 roadmap (2026-05-13 update) — 13 brainstorming groups (A-M)

> **Status**: v0.2.0 release ゲート向け、Wave 1 lanes 大半完走 + 新規 4 件 + #458 scope-out 確定に伴う再々編成
> **作成**: 2026-05-13 / session `affectionate-pare-1619e2`
> **Supersedes**: [docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md](2026-05-11-l2-v020-roadmap-update.md)
> **Spec**: [docs/superpowers/specs/2026-05-13-l2-v020-roadmap-update-design.md](../specs/2026-05-13-l2-v020-roadmap-update-design.md)
> **Scope**: L2 (v0.2.0) 残 13 issue in scope (10 OPEN active + 3 pending /close-issue) / 13 group (11 既存 A-K + 2 新規 L/M) / 3 wave / max 5 lane 並行

## 1. 完了済 (Wave 0 全消化 + Wave 1 大半完走、2026-05-08〜13)

### Wave 0 lanes (全消化)

| lane | group | 状態 | merge PR |
| --- | --- | --- | --- |
| Lane I-A | Group A (#663 AppError migration) | ✅ DONE | [PR #689](https://github.com/Idios/kobutachan-allaganeye/pull/689) |
| Lane I-B | Group B (#679 ✓ / #648 ⏳ / #644 ⏳) | ✅ 完走 (1/3 CLOSED、2/3 pending /close-issue) | [PR #720](https://github.com/Idios/kobutachan-allaganeye/pull/720) / [PR #731](https://github.com/Idios/kobutachan-allaganeye/pull/731) / [PR #734](https://github.com/Idios/kobutachan-allaganeye/pull/734) |
| Lane II-a Phase 1 | Group C 2/3 (#633 / #645) | ✅ DONE | [PR #719](https://github.com/Idios/kobutachan-allaganeye/pull/719) / [PR #735](https://github.com/Idios/kobutachan-allaganeye/pull/735) |
| Lane II-b Phase 1 | Group D 2/4 (#678 / #669) | ✅ DONE | [PR #718](https://github.com/Idios/kobutachan-allaganeye/pull/718) / [PR #726](https://github.com/Idios/kobutachan-allaganeye/pull/726) |
| Lane IV-a | Group F (4/4) | ✅ DONE | [PR #686](https://github.com/Idios/kobutachan-allaganeye/pull/686) / [PR #701](https://github.com/Idios/kobutachan-allaganeye/pull/701) / [PR #702](https://github.com/Idios/kobutachan-allaganeye/pull/702) / [PR #703](https://github.com/Idios/kobutachan-allaganeye/pull/703) |
| Lane IV-b | Group G partial (#624 / #682) | ✅ DONE | [PR #688](https://github.com/Idios/kobutachan-allaganeye/pull/688) / [PR #706](https://github.com/Idios/kobutachan-allaganeye/pull/706) |
| Lane IV-b' (Group G #458) | Group G #458 (scope-out 確定) | ✅ 実装完了 ⏳ pending /close-issue | [PR #497](https://github.com/Idios/kobutachan-allaganeye/pull/497) / [PR #688](https://github.com/Idios/kobutachan-allaganeye/pull/688) |
| Lane IV-b' (Group J) | Group J (2/2) | ✅ DONE | [PR #715](https://github.com/Idios/kobutachan-allaganeye/pull/715) / [PR #717](https://github.com/Idios/kobutachan-allaganeye/pull/717) |
| Lane IV-c | Group H (2/2) | ✅ DONE | [PR #684](https://github.com/Idios/kobutachan-allaganeye/pull/684) / [PR #687](https://github.com/Idios/kobutachan-allaganeye/pull/687) |
| Lane V Phase 1 | Group I 5/7 (#691 / #693 / #695 / #697 / #698) | ✅ DONE | [PR #714](https://github.com/Idios/kobutachan-allaganeye/pull/714) / [PR #716](https://github.com/Idios/kobutachan-allaganeye/pull/716) / [PR #725](https://github.com/Idios/kobutachan-allaganeye/pull/725) / [PR #730](https://github.com/Idios/kobutachan-allaganeye/pull/730) / [PR #733](https://github.com/Idios/kobutachan-allaganeye/pull/733) |
| Lane IV-e | Group K (2/2) | ✅ DONE | [PR #713](https://github.com/Idios/kobutachan-allaganeye/pull/713) / [PR #721](https://github.com/Idios/kobutachan-allaganeye/pull/721) |

**既消化合計**: 10 lane / 14 issue CLOSED + 3 pending close

### 2026-05-11 plan からの主要進捗

- Lane I-B (Group B 3 件) 完走、[#679](https://github.com/Idios/kobutachan-allaganeye/issues/679) closed (2026-05-12)、[#648](https://github.com/Idios/kobutachan-allaganeye/issues/648) / [#644](https://github.com/Idios/kobutachan-allaganeye/issues/644) PR merged で /close-issue 待ち
- Lane II-a (Group C) のうち [#633](https://github.com/Idios/kobutachan-allaganeye/issues/633) / [#645](https://github.com/Idios/kobutachan-allaganeye/issues/645) closed、残 [#677](https://github.com/Idios/kobutachan-allaganeye/issues/677) のみ → Lane II-a' へ
- Lane II-b (Group D) のうち [#678](https://github.com/Idios/kobutachan-allaganeye/issues/678) / [#669](https://github.com/Idios/kobutachan-allaganeye/issues/669) closed、残 [#680](https://github.com/Idios/kobutachan-allaganeye/issues/680) / [#696](https://github.com/Idios/kobutachan-allaganeye/issues/696) → Lane II-b' へ
- Lane V Phase 1 完走 (5/5 closed)、Phase 2-3 残 → Lane V Phase 2 (#694) / Phase 3 (#699)
- Group J (Lane IV-b' part) 2/2 closed、Lane IV-e (Group K) 2/2 closed
- **Group G #458 が scope-out 確定** — 修正版 2026-05-11 plan で確認、PR #497 / PR #688 で実装完了、Wave 1 active scope から除外、Wave 2 で /close-issue handoff
- 新規 4 件追加: [#710](https://github.com/Idios/kobutachan-allaganeye/issues/710) [#722](https://github.com/Idios/kobutachan-allaganeye/issues/722) [#727](https://github.com/Idios/kobutachan-allaganeye/issues/727) [#728](https://github.com/Idios/kobutachan-allaganeye/issues/728) → Group L (新) / Group M (新) / Group G ext (#728 単件)

## 2. v0.2.0 残作業 — 13 brainstorming groups (A-M)

合計 **13 issue in scope (10 OPEN active + 3 pending /close-issue) / 13 groups (11 既存 A-K + 2 新規 L/M)**。各 group は 1 spec / 1-7 章で扱える独立 scope。

### Group B: lib.rs 系 backend bugs (Wave 0 完走 + Wave 2 /close-issue)

| # | priority | 概要 | 状態 |
| --- | --- | --- | --- |
| #679 | P2 (bug) | production build の detect で CMD 窓表示 | ✅ CLOSED (2026-05-12) |
| #648 | P3 (bug) | `parse_detect_progress_line` の silent skip | ⏳ pending close (PR #731 merged) |
| #644 | P3 (bug) | `run_split` で brightness_samples が metadata.json に書かれない | ⏳ pending close (PR #734 merged) |

**Wave 2 で `/close-issue` 経由で #648 / #644 を実測再検証してから手動クローズ**。

### Group C: PreviewScreen UX (1 件残、Lane II-a')

| # | priority | 概要 |
| --- | --- | --- |
| #677 | P3 (bug) | SideRail のアイコンが選択 UI に見えるが機能なし |

**並行安全度**: high (SideRail.tsx 独立、5 screen 触らない) / **brainstorming 単位**: 1 spec / 1 章
**Wave 1**: Lane II-a' (initial parallel batch)

### Group D: ErrorModal / Export UX 残 (2 件、Lane II-b')

| # | priority | 概要 |
| --- | --- | --- |
| #680 | P3 (bug) | Export 出力先 default が存在しないフォルダ |
| #696 | P3 | ErrorModal に catch 漏れ AppError fallback 統合 |

**並行安全度**: low (ExportScreen + ErrorModal 共有 → 直列推奨) / **brainstorming 単位**: 1 spec / 2 章
**直列順**: #680 (ExportScreen default folder) → #696 (ErrorModal AppError fallback、#678 closed の error mapping 整理を前提)
**Wave 1**: Lane II-b' (initial parallel batch)

### Group E: 横断 UI bugs (1 件、Lane III、Wave 1 後段)

| # | priority | 概要 |
| --- | --- | --- |
| #676 | P3 (bug) | GUI 全画面で file path 表示が不揃い |

**並行安全度**: low (全画面 path レイアウト、5 screen 横断) / **brainstorming 単位**: 1 spec / 1 章
**Wave 1**: Lane III (V Phase 2 merge 後に着手、5 screen 編集の安定後)

### Group G: l2-workflow (extended、1 active + 1 pending close)

| # | priority | 概要 | 状態 |
| --- | --- | --- | --- |
| #458 | P2 (task) | bug_report.yml (同意チェック付き) 新設 | ⏳ pending close (実装 PR #497 / #688 で完了済、Wave 2 で /close-issue) |
| #728 | P2 (bug) | bug_report.yml が main 不在で template ロード失敗 | OPEN (Wave 1 active、Lane IV-b'') |

**Wave 1 active**: #728 のみ (single-issue lane、main branch deployment 修正)
**並行安全度**: high (`.github/ISSUE_TEMPLATE/bug_report.yml` 独立、cherry-pick / branch promotion 等) / **brainstorming 単位**: 1 spec / 1 章
**Wave 1**: Lane IV-b'' (initial parallel batch)

### Group I: post-#663 GUI cleanup (Phase 2-3 残、Lane V Phase 2 / V Phase 3)

| # | priority | 概要 | 状態 |
| --- | --- | --- | --- |
| #694 | P3 (refactor) | `*Error` / `*ErrorHint` 並列構造を unified `*ErrorState: AppError\|null` に集約 | OPEN (Phase 2) |
| #699 | P3 (doc) | AppError 関連 stale docstring を post-#663 状態に更新 | OPEN (Phase 3) |

**Wave 1 active**: Phase 2 (#694) → Phase 3 (#699) 直列、Phase 1 (5/5) は Wave 0 で完走済
**並行安全度**: low (#694 は metadataStore / recentStore type 変更 + 5 screen + 3 modal consumer 一括 refactor、ErrorModal は scope 外)
**brainstorming 単位**: 1 spec / 1 章 per Phase
**直列順**: Phase 2 #694 (Lane II-b' #680 merge 後) → Phase 3 #699 (#694 merge 後)
**Wave 1**: Lane V Phase 2 (mid) / Lane V Phase 3 (late)

### ★ Group L: workflow infra 続き (2 件新規、Lane VI)

| # | priority | 概要 |
| --- | --- | --- |
| #710 | P3 (task) | hook script の自動テスト infra + 構造化 cleanup output (PR #707 / #732 後段) |
| #722 | P2 (task) | resume-plan handoff 規約 (PR 重複防止、PR #721 事例から) |

**並行安全度**: high (`.claude/hooks/*` と `docs/l2-workflow.md` 独立 file、PR 並行可) / **brainstorming 単位**: 1 spec / 2 章
**Wave 1**: Lane VI (initial parallel batch)

### ★ Group M: gui spawn 統一 (1 件新規、Lane VII)

| # | priority | 概要 |
| --- | --- | --- |
| #727 | P3 (refactor) | gui spawn 統一 (lib.rs 5 spawn site を tokio::process::Command 系で統一、#679 派生 §5.5) |

**並行安全度**: high (`gui/src-tauri/src/lib.rs` 独立、Group B 完走済) / **brainstorming 単位**: 1 spec / 1 章
**Wave 1**: Lane VII (initial parallel batch)

## 3. 推奨着手順 (依存最小、並行最大)

```text
═══════════════════════════════════════════════════════════════════════════
WAVE 0  (DONE 2026-05-08〜13)
═══════════════════════════════════════════════════════════════════════════
  ✓ Lane I-A           Group A (#663)                  PR #689
  ✓ Lane I-B           Group B (3/3 完走、1/3 CLOSED)  PR #720 / #731 / #734
                       └ #648 / #644 manual close 待ち (Wave 2 で /close-issue)
  ✓ Lane II-a Phase 1  Group C 2/3 (#633 / #645)       PR #719 / #735
  ✓ Lane II-b Phase 1  Group D 2/4 (#678 / #669)       PR #718 / #726
  ✓ Lane IV-a          Group F (4/4)                   PR #686 / #701 / #702 / #703
  ✓ Lane IV-b          Group G partial (#624 / #682)   PR #688 / #706
  ✓ Lane IV-b' (G #458) Group G #458 実装完了 (scope-out) PR #497 / #688
                       └ /close-issue handoff のみ残 (Wave 2)
  ✓ Lane IV-c          Group H (2/2)                   PR #684 / #687
  ✓ Lane V Phase 1     Group I 5/7                     PR #714 / #716 / #725 / #730 / #733
  ✓ Lane IV-b' (J)     Group J (2/2)                   PR #715 / #717
  ✓ Lane IV-e          Group K (2/2)                   PR #713 / #721

  既消化合計: 10 lane / 14 issue CLOSED + 3 pending close

═══════════════════════════════════════════════════════════════════════════
WAVE 1  (CURRENT — 残 10 OPEN active issue / 8 lane / max 5 並行 + sub-ordering)
═══════════════════════════════════════════════════════════════════════════
  ── Initial parallel batch (5 lane、即時並行可) ──

  Lane II-a'   Group C 残 (#677 SideRail icon)
               1 spec / 1 章

  Lane II-b'   Group D 残 (#680 → #696)
               #680 (Export default folder) → #696 (ErrorModal AppError fallback)
               ExportScreen / ErrorModal serial
               1 spec / 2 章

  Lane IV-b''  Group G ext (#728 単件)
               #728 (bug_report.yml main branch deployment fix)
               #458 は実装完了済 (pending /close-issue、Wave 2 handoff)
               1 spec / 1 章

  Lane VI      ★ Group L (#710 // #722)
               #710 P3 (.claude/hooks test infra) // #722 P2 (docs/l2-workflow.md
               resume-plan handoff 規約)、file 独立で PR 並行可
               1 spec / 2 章

  Lane VII     ★ Group M (#727)
               lib.rs 5 spawn site を tokio::process::Command 系で統一 refactor
               1 spec / 1 章

  ── Mid (Lane II-b' #680 merge 後) ──

  Lane V P2    Group I Phase 2 (#694 unified ErrorState refactor)
               metadataStore / recentStore type 変更 + 5 screen + 3 modal
               consumer 一括 refactor (ErrorModal は範囲外)
               ExportScreen 共有のため Lane II-b' #680 merge 後に着手
               1 spec / 1 章

  ── Late (Lane V Phase 2 merge 後) ──

  Lane V P3    Group I Phase 3 (#699 docstring 更新)
               #694 後に refactor 結果を反映
               1 spec / 1 章

  Lane III     Group E (#676 横断 file path 表示統一)
               全画面 path レイアウト、V Phase 2 で 5 screen 編集が安定後
               1 spec / 1 章

═══════════════════════════════════════════════════════════════════════════
WAVE 2  (release gate)
═══════════════════════════════════════════════════════════════════════════
  - manual close pending 3 件 (#648 / #644 / #458) を /close-issue で実測再検証
  - docs/l2-e2e-checklist.md 全項目 PASS (Idios 実機検証)
  - 全 PR マージ確認 + base sync
  - /release skill で v0.2.0 タグ + GitHub Release
═══════════════════════════════════════════════════════════════════════════
```

### 各 lane の brainstorming 入り口 (Wave 1: 8 entry)

```text
# Initial parallel batch (5 lane、即時並行可)
/superpowers:brainstorming Lane II-a': Group C 残 (#677 SideRail icon)
/superpowers:brainstorming Lane II-b': Group D 残 (#680 Export default folder → #696 ErrorModal AppError fallback)
/superpowers:brainstorming Lane IV-b'': Group G ext (#728 bug_report.yml main 不在 fix、#458 は実装完了済 Wave 2 で /close-issue)
/superpowers:brainstorming Lane VI: Group L (#710 hook test infra // #722 resume-plan handoff 規約)
/superpowers:brainstorming Lane VII: Group M (#727 gui spawn 統一、#679 派生)

# Mid (Lane II-b' #680 merge 後)
/superpowers:brainstorming Lane V Phase 2: Group I (#694 unified ErrorState refactor)

# Late (Lane V Phase 2 merge 後、2 lane 並行可)
/superpowers:brainstorming Lane V Phase 3: Group I (#699 docstring 更新)
/superpowers:brainstorming Lane III: Group E (#676 横断 file path 表示統一)
```

## 3-bis. Lane 構造 (複数セッション並行運用)

複数の Claude Code session を立ち上げて並行作業する場合の lane 設計。各 lane は独立した worktree (`.claude/worktrees/<auto-name>/`) で動かす。

### file 共有 matrix (衝突回避の根拠)

| lane | ExportScreen | ErrorModal | 5 screens 横断 | SideRail | bug_report.yml | hook scripts | l2-workflow.md | lib.rs | metadataStore | recentStore |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| II-a' (#677) | | | | ✓ | | | | | | |
| II-b' (#680) | ✓ | | | | | | | | | |
| II-b' (#696) | | ✓ | | | | | | | | |
| IV-b'' (#728) | | | | | ✓ | | | | | |
| VI #710 | | | | | | ✓ | | | | |
| VI #722 | | | | | | | ✓ | | | |
| VII (#727) | | | | | | | | ✓ | | |
| V Phase 2 (#694) | (consumer) | | (consumer 5 screens) | | | | | | ✓ | ✓ |
| V Phase 3 (#699) | | | | | | | | | | (docstring) |
| III (#676) | (path) | | 全画面 path | | | | | | | |

### 衝突注意点

- **Lane V Phase 2 (#694) ↔ Lane II-b' #680**: 両方 ExportScreen 触る → V Phase 2 は II-b' #680 merge 後
- **Lane V Phase 2 (#694) ↔ Lane III (#676)**: 両方 5 screen 横断 → Lane III は V Phase 2 merge 後
- **Lane II-b' 内 #680 → #696**: ExportScreen / ErrorModal 別 file だが、Group D 全体の error mapping 一貫性のため #680 先行推奨
- **Lane VI (Group L) 内 #710 // #722**: hook scripts vs l2-workflow.md、file 独立で PR 並行可
- **その他**: II-a' (#677) / IV-b'' / VI / VII は wave 1 main lane と衝突なし

### 各 wave の同時並行 worktree 数

| wave | 並行 worktree 数 | 主目的 |
| --- | --- | --- |
| wave 0 | 10 (DONE 累計) | A-K 各 lane で逐次消化 |
| wave 1 | **5 (max)** initial batch + 1-2 sequential | II-a' + II-b' + IV-b'' + VI + VII 並行、V Phase 2/3 + Lane III は sequential |
| wave 2 | — | release gate (/close-issue + /release) |

最大並行度 = **5 (Wave 1 initial batch)**。bandwidth に応じて 1〜5 lane を選んで並行実行する。

### 並行運用の実務ガイド (各セッションで)

1. **Iron Law 6 PR Pre-flight** を毎回実施
2. **base 同期**: 他 lane が先に merge された場合、`git merge origin/develop-0.2.0` で取り込み後 CI 再実行
3. **session-id**: 各 worktree path の最終ディレクトリ名を session-id として PR 本文に記載
4. **bulk 操作禁止**: lane を跨いだ一括 close / 一括 label 付与は AskUserQuestion 必須 (Iron Law 2)
5. **Lane V Phase 2 (#694) gating**: Wave 1 Lane II-b' #680 merge 完了後に着手
6. **Lane V Phase 3 (#699) gating**: Lane V Phase 2 merge 完了後に着手
7. **Lane III (#676) gating**: Lane V Phase 2 merge 完了後に着手 (5 screen 横断衝突回避)

## 4. deferred / v0.2.0 対象外 (2026-05-11 plan から変更なし)

### v0.2.0 外確定 (deferred ラベル維持、6 件)

| # | 概要 |
| --- | --- |
| #518 | note → warnings: Warning[] 構造化 (将来検討) |
| #635 | PR Test plan checkbox convention 明文化 |
| #670 | 動画 HTTP server 改善 (#618 派生) |
| #671 | E2E test 自動化 feasibility (#484 派生) |
| #432 | Permission denied 全体見直し |
| #374 | metadata.json note AV1 codec 不正確 |

### L1 residual (v0.2.0 外、l1-residual ラベル、6 件)

issue: #412 / #576 / #634 / #652 / #654 / #658

### L3+ 将来 layer (多数)

issue: #28 / #32 / #63 / #125-#137 / #139-#152 / #326 / #372-#376 / #479-#481 — L3 OCR / L4 ML / L5 自動編集 / 拡張 layer

注: [#106](https://github.com/Idios/kobutachan-allaganeye/issues/106) (P2-medium、OPEN) は Group F (Wave 0) で substantial portion 消化済の parent issue、release gate 通過後に状態確認

## 5. 関連 doc / Iron Law 整合

### 関連 doc

- [`docs/l2-workflow.md`](../l2-workflow.md) — PR Pre-flight / Self-Test Report / (A) PR 内修正優先 / 実機検証 trigger (Lane VI #722 編集対象)
- [`docs/system-architecture.md`](../system-architecture.md) — #527 別 exe 方式 / dispatch 表 / Tauri bundle 方針
- [`docs/ui-architecture.md`](../ui-architecture.md) — 画面 5 + phase SM / 排他管理 / エラーハンドリング §4
- [`docs/release-process.md`](../release-process.md) §v0.2.0 固有項目 — release 判定基準
- [`docs/axum-video-server.md`](../axum-video-server.md) (#618 / PR #672) — Tier 0 spec
- [`docs/l2-e2e-checklist.md`](../l2-e2e-checklist.md) (#484 / PR #672) — release gate (Wave 2)
- [`docs/tauri-commands.md`](../tauri-commands.md) — error.rs hint drift check 対象 (Wave 0 で消化済 Group J #692)
- [`docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md`](2026-05-11-l2-v020-roadmap-update.md) — 前回 roadmap (本 plan が supersede)
- [`docs/superpowers/specs/2026-05-13-l2-v020-roadmap-update-design.md`](../specs/2026-05-13-l2-v020-roadmap-update-design.md) — 本 plan の原 spec

### Iron Law 整合 (`.claude/hooks/session-start.sh`)

- **Iron Law 1**: 各 issue の受け入れ条件全項目を逐条検証
- **Iron Law 2**: 3 件以上の bulk 操作は AskUserQuestion 必須
- **Iron Law 3**: scope creep 禁止
- **Iron Law 4**: PR / commit に Closes / Fixes / Resolves 禁止、`Refs #N` のみ。マージ後 `/close-issue` で実測再検証 (Wave 2 で #648 / #644 / #458 に適用)
- **Iron Law 6**: PR 作成 Pre-flight 必須

### Memory feedback

- `feedback_gh_command_ja_heredoc.md` — gh CLI 日本語本文は `printf | --body-file -` または HEREDOC
- `feedback_skill_revision_empirical.md` — skill 大幅改訂時は empirical-prompt-tuning 推奨
- `feedback_taskstop_child_process_leak.md` — `run_in_background` + TaskStop の子プロセス残留に注意
- `feedback_powershell_native_redirect.md` — GitHub Actions pwsh で native command 扱う 3 罠
- `feedback_msys_path_conv_git_show.md` — Bash tool 経由 `git show <rev>:<path>` で path 変換 fail
- `feedback_markdownlint_typical_fixes.md` — MD028 (連続 blockquote 空行) / MD056 (table cell `|` escape)
- **★ `project_github_issue_forms_no_prefill.md`** — bug_report.yml の custom textarea field は URL query で pre-fill されない (Lane IV-b'' Group G ext の前提)
- **★ `project_system_info_schema_gap.md`** — metadata.system_info は GPU 3 field のみ (Lane V P2 で metadata 形式触る際の前提)
- **★ `feedback_iterate_review_no_scope_creep_option.md`** — `/iterate-review` AskUserQuestion で scope 拡大選択肢を含めない (本 plan execution 時の選択肢設計に反映)

## 6. 着手前 Pre-flight チェックリスト

各 group 着手時に再確認:

- [ ] `gh issue view <num>` で受け入れ条件をフルコピー (Iron Law 1)
- [ ] `git fetch origin develop-0.2.0 && git log HEAD..origin/develop-0.2.0 --oneline` で取り込み未済 commit 確認 (Iron Law 6)
- [ ] `gh pr list --search "<元 issue#>" --state all` で並行 worktree PR 重複確認 (Iron Law 6)
- [ ] 着手 group 内に `gui/src-tauri/src/lib.rs` 共有 issue があれば直列順を確認 (Lane VII = Group M、Group B 完走済)
- [ ] 着手 group 内に `gui/src/screens/PreviewScreen.tsx` 共有 issue があれば直列順を確認 (Lane II-a' = Group C 残のみ)
- [ ] **Lane V Phase 2 (#694) を着手する場合、Lane II-b' #680 (ExportScreen) の merge 完了を確認** (file 衝突 matrix §3-bis 参照)
- [ ] **Lane III (#676 横断 file path) を着手する場合、Lane V Phase 2 (#694) の merge 完了を確認** (5 screen 横断衝突回避)
- [ ] **★ Group G ext (Lane IV-b'') 着手時、#458 が既に実装完了 (pending /close-issue、Wave 2 handoff) であることを念頭に #728 (main branch 配置) を独立 task として扱う**
````

- [ ] **Step 2: 作成結果を確認 (冒頭 20 行)**

Use Read tool:

```text
file_path: docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md
limit: 20
```

Expected: 1 行目 title `# L2 (v0.2.0) 残作業 roadmap (2026-05-13 update) — 13 brainstorming groups (A-M)`、ヘッダ 5 行 (`> **Status**` / `> **作成**` / `> **Supersedes**` / `> **Spec**` / `> **Scope**`)

- [ ] **Step 3: 末尾を確認 (Pre-flight checklist)**

Use Bash tool:

```bash
tail -n 15 docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md
wc -l docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md
```

Expected: §6 Pre-flight checklist の 8 項目 (うち末尾 3 項目が「Lane V Phase 2 / Lane III / Group G ext gating」)、line count ~320

- [ ] **Step 4: 必須セクション存在確認 (Grep)**

Use Grep tool:

```text
pattern: ^## [0-9]
path: docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md
output_mode: content
```

Expected (7 セクション、`## 1` から `## 6` + `## 3-bis`):

```text
## 1. 完了済 (Wave 0 全消化 + Wave 1 大半完走、2026-05-08〜13)
## 2. v0.2.0 残作業 — 13 brainstorming groups (A-M)
## 3. 推奨着手順 (依存最小、並行最大)
## 3-bis. Lane 構造 (複数セッション並行運用)
## 4. deferred / v0.2.0 対象外 (2026-05-11 plan から変更なし)
## 5. 関連 doc / Iron Law 整合
## 6. 着手前 Pre-flight チェックリスト
```

- [ ] **Step 5: 全 7 active group (B/C/D/E/G/I/L/M) 列挙確認 (Grep)**

Use Grep tool:

```text
pattern: ^### Group [BCDEGILM]
path: docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md
output_mode: content
```

Expected (8 行):

```text
### Group B: lib.rs 系 backend bugs (Wave 0 完走 + Wave 2 /close-issue)
### Group C: PreviewScreen UX (1 件残、Lane II-a')
### Group D: ErrorModal / Export UX 残 (2 件、Lane II-b')
### Group E: 横断 UI bugs (1 件、Lane III、Wave 1 後段)
### Group G: l2-workflow (extended、1 active + 1 pending close)
### Group I: post-#663 GUI cleanup (Phase 2-3 残、Lane V Phase 2 / V Phase 3)
### Group L: workflow infra 続き (2 件新規、Lane VI)
### Group M: gui spawn 統一 (1 件新規、Lane VII)
```

注: Group A / F / H / J / K は §1 完了済として表で言及、§2 では `### Group X:` heading が出ない。Group B は Wave 0 完走だが §2 に Wave 2 /close-issue 言及あり

- [ ] **Step 6: 個別コミット**

```bash
git add docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md
git commit -F - <<'EOF'
docs: L2 v0.2.0 roadmap update (2026-05-13、13 group / 3 wave / 8 lane wave 1)

2026-05-11 plan を Wave 1 lanes 大半完走 + 新規 4 件 (#710 #722 #727 #728) +
#458 scope-out 確定に伴い再々更新。

主な変更:
- 13 group 構造 (11 既存 A-K 中 J/K 完走、新 L/M 追加、Group G ext = #728)
- 13 issue in scope (10 OPEN active + 3 pending /close-issue 含 #458)
- Wave 1 = 8 lane / max 5 並行 (II-a' / II-b' / IV-b'' / VI / VII + V P2 / V P3 / III)
- V Phase 2 (#694) は Lane II-b' #680 merge 後 / V Phase 3 (#699) は V P2 後
- Lane III (#676) は V Phase 2 merge 後 (5 screen 横断衝突回避)
- Pre-flight checklist 8 項目 (前回 7 + 新規 Group G ext gating)
- 旧 plan に Superseded ヘッダ追加 (chain 方式 2026-05-07 → 2026-05-11 → 2026-05-13)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

Expected: `[claude/affectionate-pare-1619e2 <SHA>] docs: L2 v0.2.0 roadmap update ...` の 1 commit、`1 file changed, ~320 insertions(+)`

---

### Task 3: 本 implementation plan 自体をコミット

**Files:**

- (already created via Write tool at start of writing-plans skill execution)

- [ ] **Step 1: 個別コミット**

本 file は writing-plans skill の出力として既に作成済 (working tree に untracked)。git で追加してコミット:

```bash
git add docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update-implementation-plan.md
git commit -F - <<'EOF'
docs: L2 v0.2.0 roadmap 再更新 implementation plan (writing-plans 出力)

brainstorming spec (commits 78d639c / 47fbfc6 / 5980e60) → writing-plans 出力。
新 roadmap 作成 (Task 2) + 旧 plan supersede (Task 1) + lint (Task 4)
+ PR 作成 (Task 5/6) を docs-only で完結する 6 task 構成。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

Expected: `[claude/affectionate-pare-1619e2 <SHA>] docs: L2 v0.2.0 roadmap 再更新 implementation plan ...` の 1 commit

---

### Task 4: markdownlint 検証

**Files:**

- Verify: 4 files (旧 plan / 新 plan / 本 implementation plan / spec)

- [ ] **Step 1: 変更 file のみ markdownlint 実行**

Use Bash tool:

```bash
npx --yes markdownlint-cli2 \
  docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md \
  docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md \
  docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update-implementation-plan.md \
  docs/superpowers/specs/2026-05-13-l2-v020-roadmap-update-design.md
```

Expected: exit 0 / `Summary: 0 error(s)` (4 file 全て pass)

注 1: project 全体の `bash scripts/check-markdownlint.sh` は #700 (markdownlint ignore で nested gui/node_modules) が修正済だが、本 task では変更 file 限定でチェックする

注 2: `markdownlint-cli2` は cwd の `.markdownlint-cli2.yaml` を自動検出

注 3: 既知の typical violation を事前に回避済:

- MD028 (連続 blockquote 空行) → 旧 plan supersede header は `>` 行で連結 (Task 1 Step 2 の `new_string` 内)
- MD056 (table cell `|` を separator として誤解釈) → Group I #694 row の `AppError\|null` 等で `\|` escape 適用済

- [ ] **Step 2: error がある場合は修正**

If exit ≠ 0:

- error 内容を読み (file:line:rule format)、該当 file を Edit で修正
- 典型的な問題と修正方針 (memory `feedback_markdownlint_typical_fixes.md` 準拠):
  - **MD040** (fenced-code-language): code block を ` ``` ` で開始するときに言語タグ追加 (例: ` ```text ` / ` ```bash ` / ` ```markdown `)
  - **MD022** (blanks-around-headings): 見出しの前後に空行を追加
  - **MD031** (blanks-around-fences): code block の前後に空行を追加
  - **MD032** (blanks-around-lists): list の前後に空行を追加
- Step 1 を再実行して 0 error 確認
- 修正があれば一括コミット:

```bash
git add docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update-implementation-plan.md docs/superpowers/specs/2026-05-13-l2-v020-roadmap-update-design.md
git commit -F - <<'EOF'
docs: markdownlint fix (roadmap update 関連 file)

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

Expected: 取り込み未済 commit が 0 件 (本 worktree は本 session 開始時に `git reset --hard origin/develop-0.2.0` 実施済、HEAD = 72f0560)

- [ ] **Step 2: 取り込み未済 commit がある場合の対応**

If 取り込み未済 commit がある (本 session が長時間化して他 PR が merge された場合):

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

Expected: roadmap update を扱う他 PR が表示されない (本 PR が唯一)

If 同じ docs (`docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md` 等) を編集している他 PR がある場合: 即時停止して `AskUserQuestion` でユーザー判断を仰ぐ (Iron Law 6 違反回避)

- [ ] **Step 4: branch を origin に push**

```bash
git push -u origin claude/affectionate-pare-1619e2
```

Expected: branch が remote に反映、`gh pr create` が使える状態
(注: 前回 PR #709 merge 後に remote branch は GitHub の "Delete branch on merge" で削除済、本 push が新規 branch 作成)

---

### Task 6: PR 作成

**Files:** (なし、gh CLI のみ)

- [ ] **Step 1: PR 本文を draft (Iron Law 4 遵守: Closes/Fixes/Resolves 禁止)**

PR body の全文 (markdown):

````markdown
## 概要

L2 v0.2.0 roadmap (`docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md`、PR #709 で merge 済) を Wave 1 lanes 大半完走 + 新規 4 件追加 + #458 scope-out 確定に伴い再々更新する。新版 (`docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md`) を作成し、旧 plan に chain 方式 Superseded ヘッダを追記する。

## 変更内容

- **(新規)** `docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md`
  - 13 group (11 既存 A-K + 新規 L/M) / 3 wave / 8 lane wave 1 / max 5 並行
  - 13 issue in scope (10 OPEN active + 3 pending /close-issue 含 #458)
  - file 衝突 matrix 再掲、Pre-flight checklist 8 項目
- **(新規)** `docs/superpowers/specs/2026-05-13-l2-v020-roadmap-update-design.md`
  - 本 PR の brainstorming 設計 (採用方針 / 受け入れ条件 / リスク表)
- **(新規)** `docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update-implementation-plan.md`
  - 本 PR の implementation plan (writing-plans 出力)
- **(編集)** `docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md`
  - 冒頭に Superseded ヘッダ追加 (chain 方式 audit trail、2026-05-07 → 2026-05-11 → 2026-05-13)

## 主な決定事項 (spec §2 で確定)

- **v0.2.0 scope** = 全 13 件 (active 10 + pending close 3) — 2026-05-11 plan の「P3-low も release 直前に消化」方針を踏襲
- **Group I/J/K 既存** に **新規 Group L/M + Group G ext (#728)** を追加 (3 group 分割)
- **Wave 1 = 8 lane / max 5 並行** (file isolation 根拠: §3-bis matrix)、bandwidth 別運用
- **Lane V Phase 2 (#694) は Lane II-b' #680 merge 後 / Lane III は V Phase 2 merge 後** (5 screen 横断衝突回避)
- **#458 scope-out 確定**: 修正版 2026-05-11 plan で #458 が「実装完了済 PR #497 / #688、pending /close-issue」扱いと判明、Wave 2 で /close-issue handoff

## Self-Test Report (docs-only)

- [x] markdownlint 4 file 全て pass (`npx markdownlint-cli2`、変更 file 限定 scan で 0 error)
- [x] 新 plan の必須セクション 7 個 (`## 1` `## 2` `## 3` `## 3-bis` `## 4` `## 5` `## 6`) を Grep で確認
- [x] 新 plan の §2 列挙対象 8 group (B/C/D/E/G/I/L/M) を Grep で確認
- [x] Iron Law 6 PR Pre-flight (base sync 済 / 並行 worktree PR 重複なし) 実施
- [x] Iron Law 4 (Closes/Fixes/Resolves 禁止) 遵守 — 本 PR は doc 更新のみで issue close なし
- [x] markdownlint MD028 / MD056 を事前回避 (連続 blockquote `>` 連結 / table cell `|` escape)

## 関連 issue (Refs のみ、Closes は使用しない)

本 PR は roadmap doc 更新のみで、いずれの issue も close しない。本 plan が参照する issue:

### Wave 0 pending /close-issue (Wave 2 で /close-issue handoff)

- Group B: #648 / #644
- Group G: #458 (scope-out 確定、実装 PR #497 / #688)

### Wave 1 active (10 件)

- Group C 残: #677
- Group D 残: #680 / #696
- Group E: #676
- Group G ext: #728 (新規、#458 の main branch deployment fix)
- Group I Phase 2-3: #694 / #699
- ★ Group L (新): #710 / #722
- ★ Group M (新): #727

session-id: `affectionate-pare-1619e2`
````

注: `Closes` / `Fixes` / `Resolves` キーワードは Iron Law 4 で禁止。本 PR は doc 更新のみで issue close しないため、当然 `Closes` 不要。

- [ ] **Step 2: gh pr create で PR を作成 (`--body-file -` で stdin 経由、UTF-8 安全)**

PR body を heredoc で stdin に流し、`gh pr create --body-file -` で受ける (memory `feedback_gh_command_ja_heredoc.md` 準拠):

```bash
gh pr create \
  --base develop-0.2.0 \
  --title "docs: L2 v0.2.0 roadmap update (2026-05-13、13 group / 8 lane wave 1)" \
  --body-file - <<'EOF'
## 概要

L2 v0.2.0 roadmap (`docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md`、PR #709 で merge 済) を Wave 1 lanes 大半完走 + 新規 4 件追加 + #458 scope-out 確定に伴い再々更新する。新版 (`docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md`) を作成し、旧 plan に chain 方式 Superseded ヘッダを追記する。

## 変更内容

- **(新規)** `docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md`
  - 13 group (11 既存 A-K + 新規 L/M) / 3 wave / 8 lane wave 1 / max 5 並行
  - 13 issue in scope (10 OPEN active + 3 pending /close-issue 含 #458)
  - file 衝突 matrix 再掲、Pre-flight checklist 8 項目
- **(新規)** `docs/superpowers/specs/2026-05-13-l2-v020-roadmap-update-design.md`
  - 本 PR の brainstorming 設計 (採用方針 / 受け入れ条件 / リスク表)
- **(新規)** `docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update-implementation-plan.md`
  - 本 PR の implementation plan (writing-plans 出力)
- **(編集)** `docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md`
  - 冒頭に Superseded ヘッダ追加 (chain 方式 audit trail、2026-05-07 → 2026-05-11 → 2026-05-13)

## 主な決定事項 (spec §2 で確定)

- **v0.2.0 scope** = 全 13 件 (active 10 + pending close 3) — 2026-05-11 plan の「P3-low も release 直前に消化」方針を踏襲
- **Group I/J/K 既存** に **新規 Group L/M + Group G ext (#728)** を追加 (3 group 分割)
- **Wave 1 = 8 lane / max 5 並行** (file isolation 根拠: §3-bis matrix)、bandwidth 別運用
- **Lane V Phase 2 (#694) は Lane II-b' #680 merge 後 / Lane III は V Phase 2 merge 後** (5 screen 横断衝突回避)
- **#458 scope-out 確定**: 修正版 2026-05-11 plan で #458 が「実装完了済 PR #497 / #688、pending /close-issue」扱いと判明、Wave 2 で /close-issue handoff

## Self-Test Report (docs-only)

- [x] markdownlint 4 file 全て pass
- [x] 新 plan の必須セクション 7 個 (`## 1` `## 2` `## 3` `## 3-bis` `## 4` `## 5` `## 6`) を Grep で確認
- [x] 新 plan の §2 列挙対象 8 group (B/C/D/E/G/I/L/M) を Grep で確認
- [x] Iron Law 6 PR Pre-flight (base sync 済 / 並行 worktree PR 重複なし) 実施
- [x] Iron Law 4 (Closes/Fixes/Resolves 禁止) 遵守 — 本 PR は doc 更新のみで issue close なし
- [x] markdownlint MD028 / MD056 を事前回避 (連続 blockquote `>` 連結 / table cell `|` escape)

## 関連 issue (Refs のみ、Closes は使用しない)

本 PR は roadmap doc 更新のみで、いずれの issue も close しない。本 plan が参照する issue:

### Wave 0 pending /close-issue (Wave 2 で /close-issue handoff)

- Group B: #648 / #644
- Group G: #458 (scope-out 確定、実装 PR #497 / #688)

### Wave 1 active (10 件)

- Group C 残: #677
- Group D 残: #680 / #696
- Group E: #676
- Group G ext: #728 (新規、#458 の main branch deployment fix)
- Group I Phase 2-3: #694 / #699
- ★ Group L (新): #710 / #722
- ★ Group M (新): #727

session-id: `affectionate-pare-1619e2`
EOF
```

Expected: `https://github.com/Idios/kobutachan-allaganeye/pull/<NEW_PR>` が出力される

- [ ] **Step 3: PR 番号を取得し動作確認**

```bash
gh pr view --json number,url,title --jq '"PR#\(.number): \(.title)\n\(.url)"'
gh pr checks 2>&1 | head -10
```

Expected: PR 番号 + URL を取得、CI が回り始める (validate-checklist / markdownlint / etc 各 job pending → 順次 pass)

- [ ] **Step 4: ユーザーに完了報告**

Markdown 形式で:

- 作成 PR 番号 + URL (clickable)
- 含まれる変更 (4 file: 新 plan / spec / 本 implementation plan / 旧 plan supersede)
- 次の lane (Wave 1 initial parallel batch の 1 つ) を提案 (例: Lane II-b' が P3 main、もしくは Lane VI Group L #722 P2 が最優先候補)

---

## Self-Review Checklist (本 plan の)

writing-plans skill 完了直前に実施 (本 plan を書いた人 = AI 自身):

- [x] **Spec coverage**: spec §1-§10 各章を一通り読み、対応する task を確認
  - §1 背景 (Wave 1 大半完走 + 新規 4 件 + #458 scope-out) → Goal + Architecture で吸収
  - §2 採用方針 (4 件) → Task 2 content + PR body の「主な決定事項」で表現
  - §3 成果物 (file 構成 + supersede header) → File Structure 表 + Task 1-3
  - §4 更新後 roadmap 構造 (13 group / 3 wave / 8 lane / matrix / 8 entry / Pre-flight 8 項目) → Task 2 Step 1 の embedded markdown で完全表現
  - §5 deferred (6 + 6 + L3+) → Task 2 content の §4 で網羅
  - §6 関連 doc + Iron Law + Memory feedback (3 件追加) → Task 2 content の §5 で網羅
  - §7 Pre-flight checklist (8 項目) → Task 2 content の §6 で網羅
  - §8 受け入れ条件 → 本 plan 末尾の「受け入れ条件」セクションで対応
  - §9 非ゴール → 本 plan の scope に含めない (Iron Law 整合)
  - §10 リスク / 対応 → Task 5 (Pre-flight) + Pre-flight checklist 3 項目 (V P2 / Lane III / G ext gating) で吸収
- [x] **Placeholder scan**: 本 plan 内に `TBD` / `TODO` / `implement later` / `add appropriate error handling` 等のプレースホルダなし。`<NEW_PR>` / `<num>` 等は将来 lane worker 用のテンプレ変数 (本 plan 実行者向け instruction ではない)
- [x] **Type consistency**: file path は全 task で同一文字列 (`docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md` 等)、commit hash 参照は spec の `78d639c` / `47fbfc6` / `5980e60` のみ言及、PR 番号参照は実在確認済 (#689 / #686-#688 / #701-#706 / #713-#735)
- [x] **Iron Law 整合**: Task 1 / Task 2 / Task 3 / Task 4 の commit message は Closes / Fixes / Resolves キーワード不使用、Task 6 の PR body も同様、Task 5 で base sync 確認、Task 4 で markdownlint 強制、MD028 / MD056 を事前回避

---

## 受け入れ条件 (本 plan execution の)

実行完了時、以下が満たされること (spec §8 を踏襲):

- [ ] 新規 plan file `docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md` が spec §4 完全表現済 (Group A-M / Wave 0-2 / 8 lane / 8 entry / 衝突 matrix / Pre-flight 8 項目)
- [ ] 旧 plan file `docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md` の冒頭に Superseded ブロック挿入済 (本文維持、chain 方式)
- [ ] 本 implementation plan file `docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update-implementation-plan.md` が commit 済
- [ ] 全 4 file が markdownlint pass (Task 4 Step 1 で `Summary: 0 error(s)`)
- [ ] PR が `develop-0.2.0` base で作成され、本文に Closes/Fixes/Resolves キーワード 0 個、session-id `affectionate-pare-1619e2` 記載あり
- [ ] PR の base sync (Iron Law 6 Pre-flight) 実施済 (Task 5 Step 1-3)
- [ ] PR URL がユーザーに報告済
