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

**既消化合計**: Wave 0 全期間 23 issue CLOSED + 3 pending close (11 lane row、うち Lane IV-b' は Group G #458 と Group J で 2 row 占有 = 10 logical lane)。本日までの 2 日間 delta は 14 件 CLOSED + 3 件 pending close (詳細は次節「2026-05-11 plan からの主要進捗」)。

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
- [ ] 着手 group 内に `gui/src/screens/PreviewScreen.tsx` 共有 issue があれば直列順を確認 (Lane II-a' = Group C 残 #677)
- [ ] **Lane V Phase 2 (#694) を着手する場合、Lane II-b' #680 (ExportScreen) の merge 完了を確認** (file 衝突 matrix §3-bis 参照)
- [ ] **Lane III (#676 横断 file path) を着手する場合、Lane V Phase 2 (#694) の merge 完了を確認** (5 screen 横断衝突回避)
- [ ] **★ Group G ext (Lane IV-b'') 着手時、#458 が既に実装完了 (pending /close-issue、Wave 2 handoff) であることを念頭に #728 (main branch 配置) を独立 task として扱う**
