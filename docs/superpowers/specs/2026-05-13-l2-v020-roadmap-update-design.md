# L2 (v0.2.0) roadmap 再更新 design (2026-05-13)

> **Status**: design (brainstorming 完了、writing-plans 入り口)
> **作成**: 2026-05-13 / session `affectionate-pare-1619e2`
> **目的**: 2026-05-11 作成の L2 roadmap (`docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md`、PR #709 で merge 済) を、Wave 1 lanes の大半完走 + 2 日間の新規 issue 4 件追加に伴い再更新する設計

## 1. 背景

2026-05-11 時点の L2 v0.2.0 roadmap (11 group / 3 wave / 23 OPEN issue / 6 lane 並行) は、本 design 作成時点 (2026-05-13) で以下のドリフトが発生している:

### 2 日間の主要進捗

- **CLOSED 14 件** (旧 plan 23 件中、約 61% 消化):
  - Group A (#663) — 既消化 (PR #689)
  - Group B (Lane I-B): #679 ✓ CLOSED (2026-05-12、PR #720) / #648 PR #731 merged (manual close pending) / #644 PR #734 merged (manual close pending)
  - Group C (Lane II-a): #633 ✓ CLOSED (PR #719) / #645 ✓ CLOSED (2026-05-12、PR #735) / #677 OPEN
  - Group D (Lane II-b): #678 ✓ CLOSED (PR #718) / #669 ✓ CLOSED (PR #726) / #680 OPEN / #696 OPEN
  - Group F (Lane IV-a) — 既消化
  - Group H (Lane IV-c) — 既消化
  - Group I Phase 1 (Lane V Phase 1): 5/5 CLOSED (#691 ✓ / #693 ✓ / #695 ✓ / #697 ✓ / #698 ✓)
  - Group J (Lane IV-b' part): #692 ✓ / #700 ✓ CLOSED
  - Group K (Lane IV-e): #704 ✓ / #705 ✓ CLOSED
- **manual close pending 2 件**: [#648](https://github.com/Idios/kobutachan-allaganeye/issues/648) (PR #731 merged) / [#644](https://github.com/Idios/kobutachan-allaganeye/issues/644) (PR #734 merged) — Iron Law 4 /close-issue 待ち
- **truly OPEN 旧 plan 7 件**: [#677](https://github.com/Idios/kobutachan-allaganeye/issues/677) (Group C) / [#680](https://github.com/Idios/kobutachan-allaganeye/issues/680) [#696](https://github.com/Idios/kobutachan-allaganeye/issues/696) (Group D) / [#694](https://github.com/Idios/kobutachan-allaganeye/issues/694) [#699](https://github.com/Idios/kobutachan-allaganeye/issues/699) (Group I Phase 2-3) / [#458](https://github.com/Idios/kobutachan-allaganeye/issues/458) (Group G) / [#676](https://github.com/Idios/kobutachan-allaganeye/issues/676) (Group E)

### 新規 4 件の追加 (2026-05-10〜11 作成)

| # | priority | 概要 | 由来 |
| --- | --- | --- | --- |
| [#710](https://github.com/Idios/kobutachan-allaganeye/issues/710) | P3 (l2-workflow) | hook script の自動テスト infra + 構造化 cleanup output | PR #707 / #732 後段 |
| [#722](https://github.com/Idios/kobutachan-allaganeye/issues/722) | P2 (l2-workflow) | resume-plan handoff 規約 (PR 重複防止) | PR #721 事例 |
| [#727](https://github.com/Idios/kobutachan-allaganeye/issues/727) | P3 (refactor) | gui spawn 統一 (lib.rs 5 spawn site) | [#679](https://github.com/Idios/kobutachan-allaganeye/issues/679) PR #720 spec §5.5 派生 |
| [#728](https://github.com/Idios/kobutachan-allaganeye/issues/728) | P2 (l2-workflow) | bug_report.yml が main 不在で template ロード失敗 | [#458](https://github.com/Idios/kobutachan-allaganeye/issues/458) follow-up (同 file) |

更新後の roadmap は 13 group (A-M) / 3 wave / 13 OPEN issue (11 truly OPEN + 2 manual close pending) / 最大 5 lane 並行の構造を採る。

## 2. 採用方針 (brainstorming で決定)

| 論点 | 選択肢 | 採用 | 根拠 |
| --- | --- | --- | --- |
| v0.2.0 scope | (a) 全 15 件 (manual close 込) 吸収 (b) P2 のみ + P3 deferred (c) 個別評価 | **(a) 全 15 件 (→ 訂正後 13 件) 吸収** | 2026-05-11 plan の「P3-low も release 直前に消化」方針を踏襲、release 品質一段上を優先 |
| ドキュメント運用 | (a) 新規 file + chain 方式 Superseded (b) 旧 file in-place (c) 新規 + 旧削除 | **(a) chain 方式** | 2026-05-07 → 2026-05-11 → 2026-05-13 の audit trail 保全 (各 plan は immediate successor を指す) |
| 新規 4 件の Group 配置 | (a) Group G ext + L 新 + M 新 (3 group) (b) Group L mega (workflow 集約) + M (c) その他 | **(a) 3 group 分割** | bug_report.yml 同 file (#458 + #728 で Group G ext) / workflow infra 独立 (#710 + #722 = Group L) / Rust refactor (#727 = Group M) で file isolation matrix が clean、各 spec が 1-2 章で扱える |
| Wave 構造 | (a) 3-wave + sub-ordering note (b) 4-wave (Wave 1a/1b 分割) (c) 2-wave | **(a) 3-wave + sub-ordering** | Wave 0 = DONE / Wave 1 = remaining (sub-ordering を Pre-flight checklist で gating) / Wave 2 = release gate。シンプル、wave 番号も 3 で保つ |

## 3. 成果物

### 3.1 新規作成ファイル

| path | 内容 | 担当 |
| --- | --- | --- |
| `docs/superpowers/specs/2026-05-13-l2-v020-roadmap-update-design.md` (本 file) | brainstorming 結果の design | 本セッション |
| `docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md` | 更新後 roadmap (13 group / 3 wave / 13 OPEN / 5 lane 最大並行) | writing-plans skill |

### 3.2 編集ファイル

| path | 変更 |
| --- | --- |
| `docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md` | 冒頭に Superseded ヘッダ追加 (本文維持) |

### 3.3 Superseded ヘッダ文言

2026-05-11 plan 冒頭 (title 直後) に以下を挿入 (chain 方式、immediate successor を指す):

```markdown
> **⚠️ Superseded (2026-05-13)**: 本 plan は `docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md` で更新されています。Wave 1 lanes の大半完走 (旧 plan 23 件中 14 件 CLOSED + 2 件 pending close) + 新規 4 件 (Group G ext + Group L + Group M) 追加を反映。本ファイルは history (2026-05-11 時点の判断) として保存。
```

2026-05-07 旧 plan は不変 (既に 2026-05-11 への Superseded ヘッダ済、chain 構造で audit trail 維持)。

## 4. 更新後 roadmap 構造

### 4.1 Group 一覧 (13 group / 13 OPEN issue in scope)

| Group | scope | 件数 | 状態 | issue 番号 |
| --- | --- | --- | --- | --- |
| A | AppError migration | 1 | ✅ DONE | [#663](https://github.com/Idios/kobutachan-allaganeye/issues/663) |
| B | lib.rs backend bugs | 3 | ✅ 完走 (1/3 CLOSED、2/3 pending) | [#679](https://github.com/Idios/kobutachan-allaganeye/issues/679) ✓ / [#648](https://github.com/Idios/kobutachan-allaganeye/issues/648) ⏳ / [#644](https://github.com/Idios/kobutachan-allaganeye/issues/644) ⏳ |
| **C** | **PreviewScreen UX** | **3** | **部分完了 (2/3、1 OPEN)** | [#633](https://github.com/Idios/kobutachan-allaganeye/issues/633) ✓ / [#645](https://github.com/Idios/kobutachan-allaganeye/issues/645) ✓ / **[#677](https://github.com/Idios/kobutachan-allaganeye/issues/677) OPEN** |
| **D** | **ErrorModal / Export UX** | **4** | **部分完了 (2/4、2 OPEN)** | [#678](https://github.com/Idios/kobutachan-allaganeye/issues/678) ✓ / [#669](https://github.com/Idios/kobutachan-allaganeye/issues/669) ✓ / **[#680](https://github.com/Idios/kobutachan-allaganeye/issues/680) OPEN** / **[#696](https://github.com/Idios/kobutachan-allaganeye/issues/696) OPEN** |
| **E** | **横断 UI bugs** | **1** | OPEN | **[#676](https://github.com/Idios/kobutachan-allaganeye/issues/676)** |
| F | l2b 配布 | 4 | ✅ DONE | (Wave 0) |
| **G** | **l2-workflow (extended)** | **2** (新規 [#728](https://github.com/Idios/kobutachan-allaganeye/issues/728) 統合) | OPEN | **[#458](https://github.com/Idios/kobutachan-allaganeye/issues/458) → [#728](https://github.com/Idios/kobutachan-allaganeye/issues/728)** (同 file 直列) |
| H | lint / CLI polish | 2 | ✅ DONE | (Wave 0) |
| **I** | **post-#663 GUI cleanup** | **7** | **部分完了 (Phase 1 5/5 完了、Phase 2-3 残)** | Phase 1: 5/5 ✓ / **Phase 2: [#694](https://github.com/Idios/kobutachan-allaganeye/issues/694) OPEN** / **Phase 3: [#699](https://github.com/Idios/kobutachan-allaganeye/issues/699) OPEN** |
| J | post-#663 workflow polish | 2 | ✅ DONE | (Wave 1 完走) |
| K | l2b cleanup | 2 | ✅ DONE | (Wave 1 完走) |
| **★ L** | **workflow infra 続き** | **2 (新)** | OPEN | **[#710](https://github.com/Idios/kobutachan-allaganeye/issues/710)** P3 // **[#722](https://github.com/Idios/kobutachan-allaganeye/issues/722)** P2 |
| **★ M** | **gui spawn 統一** | **1 (新)** | OPEN | **[#727](https://github.com/Idios/kobutachan-allaganeye/issues/727)** P3 |

**v0.2.0 残 OPEN**: 1 (C) + 2 (D) + 1 (E) + 2 (G ext) + 2 (I Phase 2-3) + 2 (L) + 1 (M) = **11 件** + manual close pending 2 (B) = **13 件 in scope**

### 4.2 Wave / Lane 構造 (3 wave / 最大 5 lane 並行)

```text
═══════════════════════════════════════════════════════════════════════════
WAVE 0  (DONE 2026-05-08〜13)
═══════════════════════════════════════════════════════════════════════════
  ✓ Lane I-A           Group A (#663)                  PR #689
  ✓ Lane I-B           Group B (3/3 完走、2/3 CLOSED)  PR #720 / #731 / #734
                       └ #648 / #644 manual close 待ち (Wave 2 で /close-issue)
  ✓ Lane II-a Phase 1  Group C 2/3 (#633 / #645)       PR #719 / #735
  ✓ Lane II-b Phase 1  Group D 2/4 (#678 / #669)       PR #718 / #726
  ✓ Lane IV-a          Group F (4/4)                   PR #686 / #701 / #702 / #703
  ✓ Lane IV-b          Group G partial (#624 / #682)   PR #688 / #706
  ✓ Lane IV-c          Group H (2/2)                   PR #684 / #687
  ✓ Lane V Phase 1     Group I 5/7                     PR #714 / #716 / #725 / #730 / #733
  ✓ Lane IV-b' Group J Group J (2/2)                   PR #715 / #717
  ✓ Lane IV-e          Group K (2/2)                   PR #713 / #721

  既消化合計: 10 lane / 14 issue CLOSED + 2 pending close

═══════════════════════════════════════════════════════════════════════════
WAVE 1  (CURRENT — 残 11 OPEN issue / 7 lane / max 5 並行 + sub-ordering)
═══════════════════════════════════════════════════════════════════════════
  ── Initial parallel batch (5 lane、即時並行可) ──

  Lane II-a'   Group C 残 (#677 SideRail icon)
               1 spec / 1 章

  Lane II-b'   Group D 残 (#680 → #696)
               #680 (Export default folder) → #696 (ErrorModal AppError fallback)
               ExportScreen / ErrorModal serial
               1 spec / 2 章

  Lane IV-b''  Group G ext (#458 → #728)
               #458 (bug_report.yml 作成) → #728 (main branch deployment)
               同 file (.github/ISSUE_TEMPLATE/bug_report.yml) serial
               1 spec / 2 章

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
               consumer 一括 refactor (#694 scope は 5 screen + RestoreButton +
               ConflictModal + DraftRestoreModal、ErrorModal は範囲外)
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
  - manual close pending 2 件 (#648 / #644) を /close-issue で実測再検証
  - docs/l2-e2e-checklist.md 全項目 PASS (Idios 実機検証)
  - 全 PR マージ確認 + base sync
  - /release skill で v0.2.0 タグ + GitHub Release
═══════════════════════════════════════════════════════════════════════════
```

### 4.3 file 衝突 matrix (Wave 1 並行性根拠)

| lane | ExportScreen | ErrorModal | 5 screens 横断 | SideRail | bug_report.yml | hook scripts | l2-workflow.md | lib.rs | metadataStore | recentStore |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| II-a' (#677) | | | | ✓ | | | | | | |
| II-b' (#680) | ✓ | | | | | | | | | |
| II-b' (#696) | | ✓ | | | | | | | | |
| IV-b'' (#458 #728) | | | | | ✓ | | | | | |
| VI #710 | | | | | | ✓ | | | | |
| VI #722 | | | | | | | ✓ | | | |
| VII (#727) | | | | | | | | ✓ | | |
| V Phase 2 (#694) | (consumer) | | (consumer 5 screens) | | | | | | ✓ | ✓ |
| V Phase 3 (#699) | | | | | | | | | | (docstring) |
| III (#676) | (path) | | 全画面 path | | | | | | | |

**衝突注意点**:

- **Lane V Phase 2 (#694) ↔ Lane II-b' #680**: 両方 ExportScreen 触る → V Phase 2 は II-b' #680 merge 後に着手
- **Lane V Phase 2 (#694) ↔ Lane III (#676)**: 両方 5 screen 横断 → Lane III は V Phase 2 merge 後
- **Lane II-b' 内 #680 → #696**: ExportScreen / ErrorModal 別 file だが、Group D 全体の error mapping 一貫性のため #680 先行推奨
- **Lane VI (Group L) 内 #710 // #722**: hook scripts vs l2-workflow.md、file 独立で PR 並行可
- **その他**: II-a' (#677) / IV-b'' / VI / VII は wave 1 main lane と衝突なし

### 4.4 brainstorming 入り口 (Wave 1: 8 entry)

```text
# Initial parallel batch (5 lane、即時並行可)
/superpowers:brainstorming Lane II-a': Group C 残 (#677 SideRail icon)
/superpowers:brainstorming Lane II-b': Group D 残 (#680 Export default folder → #696 ErrorModal AppError fallback)
/superpowers:brainstorming Lane IV-b'': Group G ext (#458 bug_report.yml 作成 → #728 main 不在 fix)
/superpowers:brainstorming Lane VI: Group L (#710 hook test infra // #722 resume-plan handoff 規約)
/superpowers:brainstorming Lane VII: Group M (#727 gui spawn 統一、#679 派生)

# Mid (Lane II-b' #680 merge 後)
/superpowers:brainstorming Lane V Phase 2: Group I (#694 unified ErrorState refactor)

# Late (Lane V Phase 2 merge 後、2 lane 並行可)
/superpowers:brainstorming Lane V Phase 3: Group I (#699 docstring 更新)
/superpowers:brainstorming Lane III: Group E (#676 横断 file path 表示統一)
```

### 4.5 bandwidth 別運用例

- 1 lane: P2 から順次 (#722 → #696 → #677 → #458 → #680 → #710 → #727 → #694 → #699 → #676 → #728)
- 3 lane: II-a' + II-b' + IV-b'' 並行
- 5 lane (max): 5 main 並行、V Phase 2 / Phase 3 / Lane III は後段
- ピーク = **5 (initial batch)**

## 5. deferred / v0.2.0 対象外 (2026-05-11 plan から変更なし)

- **v0.2.0 外確定** (deferred 維持、6 件): [#518](https://github.com/Idios/kobutachan-allaganeye/issues/518) [#635](https://github.com/Idios/kobutachan-allaganeye/issues/635) [#670](https://github.com/Idios/kobutachan-allaganeye/issues/670) [#671](https://github.com/Idios/kobutachan-allaganeye/issues/671) [#432](https://github.com/Idios/kobutachan-allaganeye/issues/432) [#374](https://github.com/Idios/kobutachan-allaganeye/issues/374)
- **L1 residual** (l1-residual ラベル、6 件): [#412](https://github.com/Idios/kobutachan-allaganeye/issues/412) [#576](https://github.com/Idios/kobutachan-allaganeye/issues/576) [#634](https://github.com/Idios/kobutachan-allaganeye/issues/634) [#652](https://github.com/Idios/kobutachan-allaganeye/issues/652) [#654](https://github.com/Idios/kobutachan-allaganeye/issues/654) [#658](https://github.com/Idios/kobutachan-allaganeye/issues/658)
- **L3+ 将来 layer** (deferred、多数): [#28](https://github.com/Idios/kobutachan-allaganeye/issues/28) [#32](https://github.com/Idios/kobutachan-allaganeye/issues/32) [#63](https://github.com/Idios/kobutachan-allaganeye/issues/63) [#125-#137](https://github.com/Idios/kobutachan-allaganeye/issues/125) [#139-#152](https://github.com/Idios/kobutachan-allaganeye/issues/139) [#326](https://github.com/Idios/kobutachan-allaganeye/issues/326) [#372-#376](https://github.com/Idios/kobutachan-allaganeye/issues/372) [#479-#481](https://github.com/Idios/kobutachan-allaganeye/issues/479)
- [#106](https://github.com/Idios/kobutachan-allaganeye/issues/106) (P2-medium、OPEN): Group F (Wave 0) で substantial portion 消化済の parent issue、release gate 通過後に状態確認

## 6. 関連 doc / Iron Law 整合

### 関連 doc

- [`docs/l2-workflow.md`](../../l2-workflow.md) — PR Pre-flight / Self-Test Report / (A) PR 内修正優先 / 実機検証 trigger (Lane VI #722 の編集対象)
- [`docs/system-architecture.md`](../../system-architecture.md) — #527 別 exe 方式 / dispatch 表 / Tauri bundle 方針
- [`docs/ui-architecture.md`](../../ui-architecture.md) — 画面 5 + phase SM / 排他管理 / エラーハンドリング §4
- [`docs/release-process.md`](../../release-process.md) §v0.2.0 固有項目 — release 判定基準
- [`docs/axum-video-server.md`](../../axum-video-server.md) (#618 / PR #672) — Tier 0 spec
- [`docs/l2-e2e-checklist.md`](../../l2-e2e-checklist.md) (#484 / PR #672) — release gate (Wave 2)
- [`docs/tauri-commands.md`](../../tauri-commands.md) — error.rs hint drift check 対象 (Wave 0 で消化済 Group J #692)
- [`docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md`](../plans/2026-05-11-l2-v020-roadmap-update.md) — 前回 roadmap (本 plan が supersede)
- [`docs/superpowers/specs/2026-05-11-l2-v020-roadmap-update-design.md`](2026-05-11-l2-v020-roadmap-update-design.md) — 前回 spec

### Iron Law 整合

- **Iron Law 1**: 各 issue の受け入れ条件全項目を逐条検証 — group 内の各章で担保
- **Iron Law 2**: 3 件以上の bulk 操作は AskUserQuestion 必須 (本 plan は doc 更新のみで bulk 操作なし)
- **Iron Law 3**: scope creep 禁止 — group 内でも 1 PR = 1 章 (= 1 issue) を原則
- **Iron Law 4**: PR / commit に Closes / Fixes / Resolves 禁止、`Refs #N` のみ。マージ後 `/close-issue` で実測再検証 (Wave 2 で #648 / #644 に適用)
- **Iron Law 6**: PR 作成 Pre-flight (`git fetch origin develop-0.2.0` + 取り込み未済 commit 確認 + 並行 worktree PR 重複確認) 必須

### Memory feedback (前回 + 3 件追加)

- `feedback_gh_command_ja_heredoc.md` — gh CLI 日本語本文は `printf | --body-file -` または HEREDOC
- `feedback_skill_revision_empirical.md` — skill 大幅改訂時は empirical-prompt-tuning 推奨
- `feedback_taskstop_child_process_leak.md` — `run_in_background` + TaskStop の子プロセス残留に注意
- `feedback_powershell_native_redirect.md` — GitHub Actions pwsh で native command 扱う 3 罠
- `feedback_msys_path_conv_git_show.md` — Bash tool 経由 `git show <rev>:<path>` で path 変換 fail (`MSYS_NO_PATHCONV=1` 回避)
- `feedback_markdownlint_typical_fixes.md` — MD028 (連続 blockquote の空行) / MD056 (table cell `|` の escape) (本 plan 編集時にも要適用)
- **★ `project_github_issue_forms_no_prefill.md` (新規)** — bug_report.yml の custom textarea field は URL query で pre-fill されない (Lane IV-b'' Group G ext の前提)
- **★ `project_system_info_schema_gap.md` (新規)** — metadata.system_info は GPU 3 field のみ (CLI 由来制約、Lane V P2 で metadata 形式触る際の前提)
- **★ `feedback_iterate_review_no_scope_creep_option.md` (新規)** — `/iterate-review` AskUserQuestion で scope 拡大選択肢を含めない (PR #732 で実証、本 plan execution 時の選択肢設計に反映)

## 7. Pre-flight checklist (前回 7 → 今回 +1 = 8 項目)

各 group 着手時に再確認:

- [ ] `gh issue view <num>` で受け入れ条件をフルコピー (Iron Law 1)
- [ ] `git fetch origin develop-0.2.0 && git log HEAD..origin/develop-0.2.0 --oneline` で取り込み未済 commit 確認 (Iron Law 6)
- [ ] `gh pr list --search "<元 issue#>" --state all` で並行 worktree PR 重複確認 (Iron Law 6)
- [ ] 着手 group 内に `gui/src-tauri/src/lib.rs` 共有 issue があれば直列順を確認 (Lane VII = Group M / 旧 Lane I-B 後続)
- [ ] 着手 group 内に `gui/src/screens/PreviewScreen.tsx` 共有 issue があれば直列順を確認 (Lane II-a' = Group C 残)
- [ ] **Lane V Phase 2 (#694) を着手する場合、Lane II-b' #680 (ExportScreen) の merge 完了を確認** (file 衝突 matrix §4.3 参照)
- [ ] **Lane III (#676 横断 file path) を着手する場合、Lane V Phase 2 (#694) の merge 完了を確認** (5 screen 横断衝突回避)
- [ ] **★ Group G ext 着手時、Lane IV-b'' 内 #458 → #728 の serial 順序を確認** (同 file bug_report.yml) ← 新規

## 8. 受け入れ条件 (本 design の)

本 design に基づく writing-plans 実行で、以下が満たされること:

- [ ] 新規 plan file `docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md` が作成され、§4 構造 (13 group / 3 wave / 7 lane wave 1 / file 衝突 matrix) を完全に表現している
- [ ] 旧 plan file `docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md` の冒頭に §3.3 の Superseded ヘッダが追加され、本文は維持されている
- [ ] 新規 plan に Group A-M の全 13 group が漏れなく列挙され、各 issue の状態 (✅ DONE / ⏳ pending close / OPEN) と優先度 (P2 / P3-low) が明記されている
- [ ] 新規 plan に Wave 1 brainstorming 入り口 8 entry (II-a' / II-b' / IV-b'' / VI / VII / V Phase 2 / V Phase 3 / III) が列挙されている
- [ ] file 衝突 matrix が wave 1 全 lane × 主要 file path で記載され、V Phase 2 ↔ II-b' #680 / Lane III 衝突注意点が明記されている
- [ ] deferred / L1 residual / L3+ §5 が 2026-05-11 plan からの変更点 (Group J/K 完走の反映) を反映している
- [ ] Pre-flight checklist が §7 の 8 項目版になっている
- [ ] 本 design file と新規 plan / 旧 plan supersede の 3 file が同一 PR で commit される

## 9. 非ゴール

- 各 lane の brainstorming 内容 (各 group の実装 spec): 本 design では扱わない。各 lane の brainstorming 入り口を提示するに留める
- v0.3.0 / v0.2.1 等の将来 release 計画: deferred 6 件 + L1 residual 6 件 の post-v0.2.0 取り扱いは別途
- Iron Law / l2-workflow.md 本体の更新: Lane VI #722 で扱うが本 design では既存条文への参照のみ
- skill (`/iterate-review` / `/review-pr` 等) の改訂: 本 design 対象外 (関連 memory feedback は §6 で記録のみ)
- manual close pending 2 件 (#648 / #644) の即時 close 実行: Wave 2 で /close-issue 経由、本 design execution の scope 外

## 10. リスク / 対応

| リスク | 影響 | 対応 |
| --- | --- | --- |
| Lane V Phase 2 (#694) と Lane II-b' #680 の ExportScreen 衝突 | merge conflict | Pre-flight checklist §7 で II-b' #680 merge 後の V Phase 2 着手を強制 |
| Lane V Phase 2 (#694) と Lane III (#676) の 5 screen 横断衝突 | merge conflict | Pre-flight checklist §7 で V Phase 2 merge 後の Lane III 着手を強制 |
| Lane IV-b'' (#458 + #728) で main branch deployment 失敗 | bug_report.yml が UI から見えない | #458 で template 内容確定後、#728 で main branch 配置確認 (cherry-pick or branch promotion) を Pre-flight に含める |
| 5 lane 同時運用時の bandwidth 枯渇 | session 管理コスト増 | roadmap で「最大 5、bandwidth 別運用 (1-5)」を明記、強制しない (2026-05-11 plan 同様) |
| Group M (#727 lib.rs spawn) と将来 Rust lane (なし、Group B 完走済) の file 衝突 | なし | Group B 全 PR merged 済、lib.rs に other Wave 1 lane 触らないため衝突なし |
| 新規 4 件 (#710/#722/#727/#728) を v0.2.0 に含めることで release が遅れる | release timing | brainstorming で確定 (§2 (a))。release 直前の品質一段上を優先 |
| 本 design 自体が再び 2-3 日で stale 化する可能性 | doc メンテコスト | chain 方式 Superseded で audit trail を保ちつつ、必要に応じて再 brainstorming する運用を許容 |
