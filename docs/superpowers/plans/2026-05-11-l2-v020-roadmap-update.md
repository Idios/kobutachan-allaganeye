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
- 旧 plan 「Group G workflow 3 件」のうち 2 件 DONE。残 #458 (bug_report.yml) は当初 Lane IV-b' に統合予定だったが本 plan 確定時に scope-out (実装完了済、release gate 後 handoff)
- 旧 plan 「Group H lint/CLI 2 件」DONE。ESLint window.confirm/alert/prompt block + CLI 進捗バー ETA 表示改善が production
- 旧 plan 注釈「[#365](https://github.com/Idios/kobutachan-allaganeye/issues/365) は v0.2.0 内取り込み disposition」消化済 (#365 closed via PR #687)

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

### Group G: l2-workflow 残 (1 件、Lane IV-b' から scope-out)

| # | priority | 概要 |
| --- | --- | --- |
| #458 | P2 | bug_report.yml (同意チェック付き) 新設 — 外部ユーザー受け入れ準備 |

**本 release (v0.2.0) Wave 1 での実装作業なし** — §4 参照 (実装完了済 PR #497 + PR #688、残作業は release gate 後の `/close-issue` handoff のみ)。

**並行安全度**: high (`.github/ISSUE_TEMPLATE/bug_report.yml` 独立) / **brainstorming 単位**: Lane IV-b' から scope-out。Lane IV-b' は Group J 単独 (1 spec / 2 章)

### Group I: post-#663 GUI cleanup (7 件、新規、Lane V 3 phase)

| # | priority | 概要 |
| --- | --- | --- |
| #694 | P3 (refactor) | `*Error` / `*ErrorHint` 並列構造を unified `*ErrorState: AppError\|null` に集約 |
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

### Group J: post-#663 workflow polish (2 件、新規、Lane IV-b' 単独)

| # | priority | 概要 |
| --- | --- | --- |
| #692 | P3 | error.rs hint table drift check job 追加 (CI で `error.rs::default_hint_for_code` 24 codes (or-pattern 展開後) と `docs/tauri-commands.md` の文言一致を保証) |
| #700 | P3 (bug) | markdownlint ignore で nested `gui/node_modules` を除外 (`.markdownlint-cli2.yaml`) |

**並行安全度**: high (CI yml + markdownlint config 独立) / **brainstorming 単位**: Lane IV-b' 単独 (1 spec / 2 章、#458 は scope-out)

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

  Lane IV-b'  Group J 単独 (workflow / CI / docs polish)
              #692 (error.rs hint drift CI) // #700 (markdownlint nested ignore)
              file 完全独立、PR 並行可
              1 spec / 2 章

              ※ Group G #458 は本 lane から scope-out (実装完了済、release gate 後 /close-issue handoff)

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
/superpowers:brainstorming Lane IV-b': Group J #692 #700 (workflow / CI / docs polish、#458 は scope-out)
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
| IV-b' (#692 #700) | | | | | | | | | | | ✓ #692 | ✓ #692 | | ✓ #700 | | |
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

### Group G #458 — Lane IV-b' から scope-out (handoff)

[#458](https://github.com/Idios/kobutachan-allaganeye/issues/458) (P2、bug_report.yml) は本 plan 公開時点で実装作業完了済 (PR #497 + PR #688)、残る受け入れ条件 1 件「New issue UI からテンプレ選択可能」は L2 release (`develop-0.2.0 → main` マージ) 後に main 反映済みの環境で実測する必要があるため、Lane IV-b' (Wave 1) から scope-out した。

release gate (Wave 3) 後、L3 初期に `/close-issue` skill で実測 → close する handoff path で運用する。

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

issue: #28 / #32 / #63 / #125-#137 / #139-#152 / #326 / #372-#373 / #376 / #479-#481 — L3 OCR / L4 ML / L5 自動編集 / 拡張 layer

注: 旧 plan は [#106](https://github.com/Idios/kobutachan-allaganeye/issues/106) を「Wave 0 で CLOSED」と記述しているが、本 PR の review (PR #709 Round 1) で fact 確認した結果 OPEN (P2-medium、closedAt: null) と判明。Group F (Wave 0) の 4 件で実質的に substantial portion が消化済だが parent issue は未 close のため、本 PR では旧 plan の誤記を継承せず削除した。

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
