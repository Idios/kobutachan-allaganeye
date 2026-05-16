# L2 (v0.2.0) roadmap 更新 design (2026-05-11)

> **Status**: design (brainstorming 完了、writing-plans 入り口)
> **作成**: 2026-05-11 / session `affectionate-pare-1619e2`
> **目的**: 2026-05-07 作成の L2 roadmap (`docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md`) を、Wave 0 完走 + post-#663 cleanup 12 件追加に伴い更新する設計

## 1. 背景

2026-05-07 時点の L2 v0.2.0 roadmap (8 group / 20 issue / 4 wave) は、4 日後の 2026-05-11 時点で以下のドリフトが発生している:

- **Wave 0 完走** (4 lane / 9 issue 完了): Lane I-A (Group A) / Lane IV-a (Group F 4 件) / Lane IV-b 部分 (Group G 2/3) / Lane IV-c (Group H 2 件) が merge 済 (PR #684 #686 #687 #688 #689 #701 #702 #703 #706)
- **post-#663 cleanup 12 件発生** (PR #689 review 派生): Group I (post-#663 GUI cleanup, 当初 8 件 → §2 採用方針 (a) で #696 を Group D に fold した結果 7 件) / Group J (post-#663 workflow polish, 2 件) / Group K (l2b cleanup, 2 件) が新規 issue として登録済 ([#691](https://github.com/Idios/kobutachan-allaganeye/issues/691) [#692](https://github.com/Idios/kobutachan-allaganeye/issues/692) [#693](https://github.com/Idios/kobutachan-allaganeye/issues/693) [#694](https://github.com/Idios/kobutachan-allaganeye/issues/694) [#695](https://github.com/Idios/kobutachan-allaganeye/issues/695) [#696](https://github.com/Idios/kobutachan-allaganeye/issues/696) [#697](https://github.com/Idios/kobutachan-allaganeye/issues/697) [#698](https://github.com/Idios/kobutachan-allaganeye/issues/698) [#699](https://github.com/Idios/kobutachan-allaganeye/issues/699) [#700](https://github.com/Idios/kobutachan-allaganeye/issues/700) [#704](https://github.com/Idios/kobutachan-allaganeye/issues/704) [#705](https://github.com/Idios/kobutachan-allaganeye/issues/705))
- **Wave 1 未着手**: 旧 plan の Wave 1 (Lane I-B / II-a / II-b、main 3 lane) は未開始
- **Group G 残**: [#458](https://github.com/Idios/kobutachan-allaganeye/issues/458) (P2、bug_report.yml 同意チェック付き) が OPEN のまま — 更新後 plan で Lane IV-b' から scope-out (実装完了済、release gate 後 handoff)

更新後の roadmap は 23 件 / 11 group / 3 wave / 最大 6 lane 並行の構造を採る。

## 2. 採用方針 (brainstorming で決定)

| 論点 | 選択肢 | 採用 | 根拠 |
| --- | --- | --- | --- |
| v0.2.0 scope | (a) 旧 11 件のみ (b) 全 23 件 (c) ハイブリッド | **(b) 全 23 件** | 新規 12 件はすべて P3-low cleanup。release 直前のひとまとめ消化が品質一段上、blocker 化なし |
| ドキュメント運用 | (a) 新規 file + 旧 Superseded (b) 旧 file in-place 編集 (c) 新規 + 旧削除 | **(a) 新規 + Superseded** | 2026-05-07 判断の audit trail (Wave 0 完走根拠 / BtbN URL 予告等) を保全 |
| Group 構造 | (a) 新 I/J/K + #696 を D に fold (b) I に 8 件統合 (c) 単一 I に 12 件 | **(a) 新 I/J/K + #696 fold** | ErrorModal.tsx の file 衝突回避 (Group D #678 と #696 同 file)、l2a-gui / l2-workflow / l2b-installer のラベル分類とも整合 |
| Wave 1 構造 | (a) max parallel 6 lane (b) Wave 1.5 split (c) file-affinity merge | **(a) max parallel 6** | file isolation matrix が clean、bandwidth 別運用 (1-6 lane) を許容、lane V Phase 2 のみ main 3 merge 後 sequencing |

## 3. 成果物

### 3.1 新規作成ファイル

| path | 内容 | 担当 |
| --- | --- | --- |
| `docs/superpowers/specs/2026-05-11-l2-v020-roadmap-update-design.md` (本 file) | brainstorming 結果の design | 本セッション |
| `docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md` | 更新後の roadmap (23 件 / 11 group / 3 wave / 6 lane) | writing-plans skill |

### 3.2 編集ファイル

| path | 変更 |
| --- | --- |
| `docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md` | 冒頭に Superseded ヘッダ追加 (本文維持) |

### 3.3 Superseded ヘッダ文言

旧 plan 冒頭 (title 直後) に以下を挿入:

```markdown
> **⚠️ Superseded (2026-05-11)**: 本 plan は `docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md` で更新されています。Wave 0 完走 + post-#663 cleanup 12 件追加 (Group I/J/K) + Lane V 新設 + Lane IV 拡張を反映。本ファイルは history (2026-05-07 時点の判断) として保存。
```

## 4. 更新後 roadmap 構造

### 4.1 Group 一覧 (11 group / 23 OPEN issue)

| Group | scope | 件数 | 状態 | issue 番号 |
| --- | --- | --- | --- | --- |
| A | AppError migration | 1 | ✅ DONE | [#663](https://github.com/Idios/kobutachan-allaganeye/issues/663) |
| **B** | **lib.rs backend bugs** | **3** | OPEN | [#679](https://github.com/Idios/kobutachan-allaganeye/issues/679) (P2) → [#648](https://github.com/Idios/kobutachan-allaganeye/issues/648) → [#644](https://github.com/Idios/kobutachan-allaganeye/issues/644) |
| **C** | **PreviewScreen UX** | **3** | OPEN | [#633](https://github.com/Idios/kobutachan-allaganeye/issues/633) (P2) → [#645](https://github.com/Idios/kobutachan-allaganeye/issues/645) → [#677](https://github.com/Idios/kobutachan-allaganeye/issues/677) |
| **D** | **ErrorModal / Export UX (拡張)** | **4** | OPEN | [#678](https://github.com/Idios/kobutachan-allaganeye/issues/678) (P2) → [#669](https://github.com/Idios/kobutachan-allaganeye/issues/669) → [#680](https://github.com/Idios/kobutachan-allaganeye/issues/680) → **[#696](https://github.com/Idios/kobutachan-allaganeye/issues/696) (新規 fold)** |
| **E** | **横断 UI bugs** | **1** | OPEN | [#676](https://github.com/Idios/kobutachan-allaganeye/issues/676) ([#680](https://github.com/Idios/kobutachan-allaganeye/issues/680) は D に fold 済) |
| F | l2b 配布 | 4 | ✅ DONE | [#617](https://github.com/Idios/kobutachan-allaganeye/issues/617) [#616](https://github.com/Idios/kobutachan-allaganeye/issues/616) [#668](https://github.com/Idios/kobutachan-allaganeye/issues/668) [#681](https://github.com/Idios/kobutachan-allaganeye/issues/681) |
| **G** | **l2-workflow 残** | **1** | OPEN | [#458](https://github.com/Idios/kobutachan-allaganeye/issues/458) (P2) — Lane IV-b' から scope-out (release gate 後 handoff) |
| H | lint / CLI polish | 2 | ✅ DONE | [#643](https://github.com/Idios/kobutachan-allaganeye/issues/643) [#365](https://github.com/Idios/kobutachan-allaganeye/issues/365) |
| **★ I** | **post-#663 GUI cleanup** | **7** | OPEN (新規) | Phase 1: [#691](https://github.com/Idios/kobutachan-allaganeye/issues/691) // [#693](https://github.com/Idios/kobutachan-allaganeye/issues/693) // [#695](https://github.com/Idios/kobutachan-allaganeye/issues/695) // [#697](https://github.com/Idios/kobutachan-allaganeye/issues/697) // [#698](https://github.com/Idios/kobutachan-allaganeye/issues/698) → Phase 2: [#694](https://github.com/Idios/kobutachan-allaganeye/issues/694) → Phase 3: [#699](https://github.com/Idios/kobutachan-allaganeye/issues/699) |
| **★ J** | **post-#663 workflow polish** | **2** | OPEN (新規) | [#692](https://github.com/Idios/kobutachan-allaganeye/issues/692) // [#700](https://github.com/Idios/kobutachan-allaganeye/issues/700) |
| **★ K** | **l2b cleanup** | **2** | OPEN (新規) | [#704](https://github.com/Idios/kobutachan-allaganeye/issues/704) // [#705](https://github.com/Idios/kobutachan-allaganeye/issues/705) |

**v0.2.0 残 OPEN 合計** = 3 (B) + 3 (C) + 4 (D) + 1 (E) + 1 (G) + 7 (I) + 2 (J) + 2 (K) = **23 件**

### 4.2 Wave / Lane 構造 (3 wave / 最大 6 lane 並行)

```text
═══════════════════════════════════════════════════════════════════════════
WAVE 0  (DONE 2026-05-08〜10)
═══════════════════════════════════════════════════════════════════════════
  Lane I-A   ✅ Group A (#663)                            PR #689
  Lane IV-a  ✅ Group F (#617 #616 #668 #681)             PR #686 #701 #702 #703
  Lane IV-b  ✅ Group G partial (#624 #682)               PR #688 #706
  Lane IV-c  ✅ Group H (#643 #365)                       PR #684 #687

═══════════════════════════════════════════════════════════════════════════
WAVE 1  (CURRENT — 最大 6 lane 並行可)
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
              #704 (Pester PS5.1 BOM) // #705 (BtbN URL 陳腐化対策、旧 plan 「5 章目」)
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

### 4.3 file 衝突 matrix (Wave 1 並行性根拠)

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

**衝突注意点**:

- **Lane V Phase 2 (#694) ↔ Lane II-a / II-b**: #694 は 5 screen + ConflictModal + DraftRestoreModal + DropScreen の **consumer 一括 refactor**。II-a / II-b の screen 編集が Wave 1 main で進行中なので、**#694 は main 3 lane の merge 後** に着手する (Phase 2 timing)
- **Lane II-a #633 ↔ Lane V Phase 1 #698**: 両方 DropScreen を触る。merge 順序 = 先着優先 + rebase
- **Lane V Phase 1 内 5 件**: 各 file 独立 (metadataStore / shared component / 3 modal / DropScreen)、PR 並行可
- **Lane IV-b' / IV-e 内**: 各々 file 完全独立、PR 並行可

### 4.4 Group I 内 sub-ordering の根拠

[#694](https://github.com/Idios/kobutachan-allaganeye/issues/694) は metadataStore (5 pair → 5 unified `*ErrorState: AppError|null`) / recentStore (2 pair → 2 unified) の **type 変更 refactor** で、consumer は 5 screen + RestoreButton + ConflictModal + DraftRestoreModal。

- 5 件 batch ([#691](https://github.com/Idios/kobutachan-allaganeye/issues/691) [#693](https://github.com/Idios/kobutachan-allaganeye/issues/693) [#695](https://github.com/Idios/kobutachan-allaganeye/issues/695) [#697](https://github.com/Idios/kobutachan-allaganeye/issues/697) [#698](https://github.com/Idios/kobutachan-allaganeye/issues/698)) は既存の `*Error / *ErrorHint` 並列 API でも実装可能 (UI 追加・小整理が中心)。先行で消化可
- [#694](https://github.com/Idios/kobutachan-allaganeye/issues/694) は Wave 1 main 3 lane が screen を編集している間に走らせると merge conflict 大規模化するので main merge 後
- [#699](https://github.com/Idios/kobutachan-allaganeye/issues/699) docstring は最終形を反映するので #694 後

→ **Phase 1 (5 件 batch、Wave 1 main と並行可) → Phase 2 ([#694](https://github.com/Idios/kobutachan-allaganeye/issues/694)、main 3 lane merge 後) → Phase 3 ([#699](https://github.com/Idios/kobutachan-allaganeye/issues/699)、#694 後)** の 3 phase

### 4.5 Group D の #696 fold 順序

[#678](https://github.com/Idios/kobutachan-allaganeye/issues/678) (Export error mapping P2) → [#669](https://github.com/Idios/kobutachan-allaganeye/issues/669) (テンプレ自動埋込 P3) → [#680](https://github.com/Idios/kobutachan-allaganeye/issues/680) (Export default folder P3) → **[#696](https://github.com/Idios/kobutachan-allaganeye/issues/696) (ErrorModal AppError fallback)**。理由: [#678](https://github.com/Idios/kobutachan-allaganeye/issues/678) の error mapping 整理が [#696](https://github.com/Idios/kobutachan-allaganeye/issues/696) の `'tauri-command' errorCategory` 設計を楽にする。

### 4.6 brainstorming 入り口 (Wave 1: 8 + Wave 2: 1 = 9 entry)

```text
# Wave 1 main (3 lane、P2 含む、即時並行可)
/superpowers:brainstorming Lane I-B: Group B の問題を解決したい (#679 → #648 → #644 lib.rs 直列、Group A AppError 経路)
/superpowers:brainstorming Lane II-a: Group C の問題を解決したい (#633 P2 → #645 → #677 PreviewScreen UX)
/superpowers:brainstorming Lane II-b: Group D + #696 統合 (#678 P2 → #669 → #680 → #696 ExportScreen + ErrorModal)

# Wave 1 polish - Lane V (3 phase)
/superpowers:brainstorming Lane V Phase 1: Group I 5 件 batch (#691 #693 #695 #697 #698 post-#663 hint UI)
/superpowers:brainstorming Lane V Phase 2: Group I #694 unified ErrorState refactor (Wave 1 main merge 後)
/superpowers:brainstorming Lane V Phase 3: Group I #699 docstring 更新 (#694 merge 後)

# Wave 1 polish - Lane IV (workflow / CI / installer)
/superpowers:brainstorming Lane IV-b': Group J #692 #700 (workflow / CI / docs polish、#458 は scope-out)
/superpowers:brainstorming Lane IV-e: Group K の問題を解決したい (#704 #705 l2b cleanup)

# Wave 2 (Wave 1 完走後)
/superpowers:brainstorming Lane III: Group E #676 (横断 file path 表示統一)
```

## 5. deferred / v0.2.0 対象外 (旧 plan から変更なし)

- **v0.2.0 外確定** (deferred 維持、6 件): [#518](https://github.com/Idios/kobutachan-allaganeye/issues/518) [#635](https://github.com/Idios/kobutachan-allaganeye/issues/635) [#670](https://github.com/Idios/kobutachan-allaganeye/issues/670) [#671](https://github.com/Idios/kobutachan-allaganeye/issues/671) [#432](https://github.com/Idios/kobutachan-allaganeye/issues/432) [#374](https://github.com/Idios/kobutachan-allaganeye/issues/374)
- **L1 residual** (l1-residual ラベル、6 件): [#412](https://github.com/Idios/kobutachan-allaganeye/issues/412) [#576](https://github.com/Idios/kobutachan-allaganeye/issues/576) [#634](https://github.com/Idios/kobutachan-allaganeye/issues/634) [#652](https://github.com/Idios/kobutachan-allaganeye/issues/652) [#654](https://github.com/Idios/kobutachan-allaganeye/issues/654) [#658](https://github.com/Idios/kobutachan-allaganeye/issues/658)。注: 旧 plan 注釈「[#365](https://github.com/Idios/kobutachan-allaganeye/issues/365) は v0.2.0 内取り込み」は Group H DONE で消化済
- **L3+ 将来 layer** (deferred、多数): [#28](https://github.com/Idios/kobutachan-allaganeye/issues/28) [#32](https://github.com/Idios/kobutachan-allaganeye/issues/32) [#63](https://github.com/Idios/kobutachan-allaganeye/issues/63) [#125-#137](https://github.com/Idios/kobutachan-allaganeye/issues/125) [#139-#152](https://github.com/Idios/kobutachan-allaganeye/issues/139) [#326](https://github.com/Idios/kobutachan-allaganeye/issues/326) [#372-#376](https://github.com/Idios/kobutachan-allaganeye/issues/372) [#479-#481](https://github.com/Idios/kobutachan-allaganeye/issues/479)。注: 旧 plan の [#106](https://github.com/Idios/kobutachan-allaganeye/issues/106) を「CLOSED」と記述しているが、本 PR review (PR #709 Round 1) で fact 確認の結果 OPEN (P2-medium) と判明、本 plan では誤記を継承しない

## 6. 関連 doc / Iron Law 整合 (旧 plan からほぼ変更なし)

### 関連 doc

- [`docs/l2-workflow.md`](../../l2-workflow.md) — PR Pre-flight / Self-Test Report / (A) PR 内修正優先 / 実機検証 trigger
- [`docs/system-architecture.md`](../../system-architecture.md) — #527 別 exe 方式 / dispatch 表 / Tauri bundle 方針
- [`docs/ui-architecture.md`](../../ui-architecture.md) — 画面 5 + phase SM / 排他管理 / エラーハンドリング §4
- [`docs/release-process.md`](../../release-process.md) §v0.2.0 固有項目 — release 判定基準
- [`docs/axum-video-server.md`](../../axum-video-server.md) (#618 / PR #672) — Tier 0 spec
- [`docs/l2-e2e-checklist.md`](../../l2-e2e-checklist.md) (#484 / PR #672) — release gate
- [`docs/tauri-commands.md`](../../tauri-commands.md) — Group J #692 (hint table drift check) の対象 (新規参照)

### Iron Law 整合

- **Iron Law 1**: 各 issue の受け入れ条件全項目を逐条検証 — group 内の各章で担保
- **Iron Law 2**: 3 件以上の bulk 操作 (label 変更 / 一括 close / 一括 close 候補追加) は AskUserQuestion 必須
- **Iron Law 3**: scope creep 禁止 — group 内でも 1 PR = 1 章 (= 1 issue) を原則
- **Iron Law 4**: PR / commit に Closes / Fixes / Resolves 禁止、`Refs #N` のみ。マージ後 `/close-issue` で実測再検証
- **Iron Law 6**: PR 作成 Pre-flight (`git fetch origin develop-0.2.0` + 取り込み未済 commit 確認 + 並行 worktree PR 重複確認) 必須

### Memory feedback

- `feedback_gh_command_ja_heredoc.md` — gh CLI 日本語本文は `printf | --body-file -` または HEREDOC
- `feedback_skill_revision_empirical.md` — skill 大幅改訂時は empirical-prompt-tuning 推奨
- `feedback_taskstop_child_process_leak.md` — `run_in_background` + TaskStop の子プロセス残留に注意

## 7. Pre-flight checklist (旧 plan に 2 項目追加)

各 group 着手時に再確認:

- [ ] `gh issue view <num>` で受け入れ条件をフルコピー (Iron Law 1)
- [ ] `git fetch origin develop-0.2.0 && git log HEAD..origin/develop-0.2.0 --oneline` で取り込み未済 commit 確認 (Iron Law 6)
- [ ] `gh pr list --search "<元 issue#>" --state all` で並行 worktree PR 重複確認 (Iron Law 6)
- [ ] 着手 group 内に `gui/src-tauri/src/lib.rs` 共有 issue があれば直列順を確認 (Group A → B)
- [ ] 着手 group 内に `gui/src/screens/PreviewScreen.tsx` 共有 issue があれば直列順を確認 (Group C)
- [ ] **Lane V Phase 2 (#694) を着手する場合、Wave 1 main 3 lane (I-B / II-a / II-b) の merge 完了を確認 (file 衝突 matrix §4.3 参照)** ← 新規
- [ ] **Lane V Phase 1 #698 と Lane II-a #633 を並行する場合、`gui/src/screens/DropScreen.tsx` の rebase 順序 (先着優先) を合意済か確認** ← 新規

## 8. 受け入れ条件 (本 design の)

本 design に基づく writing-plans 実行で、以下が満たされること:

- [ ] 新規 plan file `docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md` が作成され、§4 構造 (11 group / 3 wave / 6 lane / file 衝突 matrix) を完全に表現している
- [ ] 旧 plan file `docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md` の冒頭に §3.3 の Superseded ヘッダが追加され、本文は維持されている
- [ ] 新規 plan に Group A-K の全 11 group / 23 OPEN issue が漏れなく列挙され、各 issue の優先度 (P2 / P3-low) が明記されている
- [ ] 新規 plan に Wave 1 brainstorming 入り口 8 entry (Lane I-B / II-a / II-b / V Phase 1 / V Phase 2 / V Phase 3 / IV-b' / IV-e) + Wave 2 brainstorming 入り口 1 entry (Lane III) = 計 9 entry が列挙されている
- [ ] file 衝突 matrix が wave 1 全 lane × 主要 file path で記載され、Lane V Phase 2 ↔ II-a / II-b の衝突注意点が明記されている
- [ ] deferred / L1 residual / L3+ の §4 が旧 plan からの変更点 ([#365](https://github.com/Idios/kobutachan-allaganeye/issues/365) DONE) を反映 + [#106](https://github.com/Idios/kobutachan-allaganeye/issues/106) は OPEN 維持 (旧 plan の CLOSED 主張を本 PR review で fact 訂正) を明記している
- [ ] Pre-flight checklist が §7 の 2 項目追加版になっている
- [ ] 本 design file (`docs/superpowers/specs/2026-05-11-l2-v020-roadmap-update-design.md`) と新規 plan / 旧 plan supersede の 3 file が同一 PR で commit される

## 9. 非ゴール

- 各 lane の brainstorming 内容 (各 group の実装 spec): 本 design では扱わない。各 lane の brainstorming 入り口を提示するに留める
- v0.3.0 / v0.2.1 等の将来 release 計画: deferred 6 件 + L1 residual 6 件 の post-v0.2.0 取り扱いは別途
- Iron Law / l2-workflow.md 本体の更新: 本 design では既存条文への参照のみ
- skill (`/iterate-review` / `/review-pr` 等) の改訂: 本 design 対象外

## 10. リスク / 対応

| リスク | 影響 | 対応 |
| --- | --- | --- |
| Lane V Phase 2 (#694) と Lane II-a / II-b の screen consumer 衝突 | 大規模 merge conflict、refactor 工数増 | Pre-flight checklist §7 で main 3 lane merge 後の Phase 2 着手を強制 |
| Lane II-a #633 ↔ Lane V Phase 1 #698 の DropScreen 衝突 | 小規模 rebase | Pre-flight checklist §7 で先着優先 + rebase 合意 |
| 6 lane 同時運用時の bandwidth 枯渇 | session 管理コスト増 | roadmap で「最大 6、bandwidth 別運用 (1-6)」を明記、強制しない |
| 新規 12 件 (P3-low) を v0.2.0 に含める判断が release を遅らせる | release timing | brainstorming で確定 (§2)。release 直前の品質一段上を優先 |
| Group I 5 件 batch の DropScreen / 共有 component 内部衝突 | 小規模 PR conflict | Lane V Phase 1 内は各 issue file 独立、PR 並行で問題なし (file matrix §4.3 で確認) |
