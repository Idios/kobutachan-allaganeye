# v0.2.0 / v0.2.1 retrospective の機構化 + Codex 統合 設計書

- **作成日**: 2026-05-17
- **対象**: v0.2.0 / v0.2.1 開発サイクル (2026-04-20 ～ 2026-05-17)
- **目的**: 良かった実践の継続を仕組み化し、再発した摩擦を skill / hook / docs / CI に preventive メカニズムとして反映する。同時に新規導入した openai-codex プラグインを Iron Law と衝突しない形で workflow に組み込む。
- **位置付け**: v0.3.0 開発開始時の workflow ベースライン整備。実装は本 spec から派生する複数 issue / Lane で行う (本 spec 自体は実装を含まない)。

---

## 1. 背景

v0.2.0 サイクルでは 130+ PR をマージし、L2 (GUI Tauri + Portable ZIP 配布) を一から構築した上で v0.2.1 patch (security audit / CI 高速化 / Portable README ja / CHANGELOG) まで 1 ヶ月弱で到達した。Iron Law の 5→6 条化、`/iterate-review` 新設、AppError migration の Phase 分割等で workflow が顕著に成熟した一方、以下の摩擦パターンが繰り返し発生した:

- 同じ root cause を 2-3 PR で fix し直す (encoding / upstream URL drift / scorebar design churn)
- skill prompt に記載済の規律が実行時に逸脱する (scope creep / subagent 独断 fix / 到達性確認漏れ)
- 単一 OS / runtime で CI を組んだことで他環境の regression を mask (PS 5.1)
- deferred 判定漏れが patch release に持ち越される

また、本サイクル末期に openai-codex プラグイン (1.0.4) を導入した。`/codex:review`, `/codex:adversarial-review`, `/codex:rescue` 等の機能が利用可能になり、GPT-5.4 という別 model による second opinion を Claude Code workflow に統合する余地が生まれた。ただし `/codex:rescue` は `--write` default のため Iron Law 3 (scope creep 禁止) と衝突する可能性があり、運用ルールを設計する必要がある。

本 spec は (A) 継続する良い実践の codify、(B) 再発防止メカニズム M1-M10、(C) Codex 統合 C1-C5、を 4 Lane / 約 14 PR に分解する形で提案する。

## 2. 範囲・非範囲

### 範囲

- `.claude/hooks/`, `.claude/skills/`, `.claude/settings.json` の追加・改訂
- `CLAUDE.md`, `docs/l2-workflow.md`, `docs/issue-policy.md`, `docs/release-process.md` の規約追加
- `docs/refactor-pattern.md`, `docs/markdownlint-guide.md` の新設
- `.github/workflows/release.yml` への CI matrix 追加
- `openai-codex` プラグインの常用化 (review gate ON、Iron Law 6 Pre-flight への組み込み)

### 非範囲

- Iron Law 1-5 の本文書き換え (条文は session-start.sh の正本を維持、Iron Law 6 を Pre-flight Step 5 で拡張するのみ)
- 既存 skill (review-pr / iterate-review / close-issue / scope-guard / create-task / release / enforce-acceptance-criteria) の全面刷新 (改訂は局所的)
- L1 / L2 機能スコープの再定義 (本 spec は workflow 改善のみ)
- Codex CLI 本体の wrap / fork (プラグインを素のまま使う)
- memory feedback の新規作成 (実装 PR 単位で必要に応じて追加)

## 3. v0.2.0 / v0.2.1 retrospective サマリ

### 3.1 継続したい良い実践

| # | 実践 | 効いた事例 | 既存 codify 先 |
| --- | --- | --- | --- |
| G1 | **skill ベースディスパッチ + empirical-prompt-tuning loop** | `/review-pr` (#506 #537 #562 #674)、`/iterate-review` 新設 (#706)、`/close-issue` 分離 (#594 #602 #629)、5 skill empirical 改善 (#487) | `docs/l2-workflow.md` §開発ワークフロー、CLAUDE.md §Plugin との関係 |
| G2 | **Iron Law 6 条 + Red Flags 表 + PR Pre-flight Step 0-4** | Iron Law 6 新設 (#637)、Pre-flight base sync 運用化 (#660)、resume-plan handoff EXECUTOR (#722)、hook test infra (#744) | `.claude/hooks/session-start.sh`、`docs/l2-workflow.md` §「PR 作成 Pre-flight」 |
| G3 | **brainstorming → spec → plan → executor の四段分離** | `docs/superpowers/specs/` 配下に 17 spec、Lane 構成 (Lane I-VII) で並列開発が機能 | `docs/l2-workflow.md` §タスク種別、superpowers plugin |
| G4 | **大規模 refactor の Phase 分割パターン** | AppError migration (#663→#689→#714/716/725/730/733→#745→#746)、metadata schema (#515 #533 #627)、vendor probe 段階拡張 (#546 #553 #550 #582 #591 #596) | (未 codify、A1 で追加) |
| G5 | **deferred + Track A-D 構造化 patch release** | v0.2.1 が Track 0 (spec)/A (security)/B (UX)/C (CI gate)/D (version) を 10 PR で並列完結 (#759-#774) | (未 codify、A2 で追加) |

### 3.2 摩擦・再発した事象

| # | 事象 | 代表 PR / issue | 根本原因 | memory 蓄積 |
| --- | --- | --- | --- | --- |
| F1 | PS 5.1 vs pwsh エンコーディング差異 | #729 → #736 → #713 (BOM-less manifest, Tests.ps1 BOM) | pwsh 単独 CI で PS 5.1 silent regression を mask | ✓ `feedback_ps_setcontent_utf8_bom` (CI matrix 補強は既存 issue [#737](https://github.com/Idios/kobutachan-allaganeye/issues/737) で deferred、本 spec M1 で release-blocker 化を提案) |
| F2 | upstream URL drift hotfix 3 連発 | #649 → #651 → #703 → #721 (get-pip.py SHA、BtbN pin) | 外部依存 DL に immutable URL 強制ルール不在 | ★ 未蓄積 |
| F3 | scorebar V2 design churn | #522 → #525 → #552 (emblem 動的検出、対称 re-probe fallback) | 初版 dynamic-only が長尺で結合退行、OR semantics 提案が後追い | ★ 未蓄積 |
| F4 | encoding 二段防御 (Python→Rust audit 漏れ) | #656 / #657 → #662 (cp932 fix → UTF-8 stdout 強制) | 言語境界の audit checklist 不在 | ★ 未蓄積 |
| F5 | markdownlint ignores の穴塞ぎ | #494/500-502 → #717 → #724 (nested node_modules / build/**) | glob 仕様の理解不足、`**/<name>/**` パターン未統一 | ✓ `feedback_brainstorming_sweep_repo_wide_grep` (一部) / `feedback_markdownlint_typical_fixes` |
| F6 | scope creep / subagent 独断 fix の再発 | #732 commit 8eff1d2-ee77e37 (claude/* sweep) / #746 Phase C subagent (`:693` 独断 fix) | skill prompt 記載のみでは実行時逸脱が発生 | ✓ `feedback_iterate_review_no_scope_creep_option` / `feedback_subagent_dispatch_stop_on_scope_creep` |
| F7 | subagent orphaned commit (到達性確認漏れ) | #741 Task 5 (detached HEAD commit を cherry-pick で復旧) | controller の `git log <branch>` 確認が習慣化せず | ✓ `feedback_subagent_orphaned_commit` |
| F8 | deferred 判定漏れ → v0.2.1 持ち越し | #374 #458 #743 #749 #756 (Track B で吸収) | release gate が deferred 最終 sweep を強制せず、`release-blocker` ラベルも不在 | ★ 未蓄積 |

「未蓄積」は memory feedback が無く、機構化対象。「memory ✓」も実行時逸脱が発生したため、勧告だけでなく hook/CI による検出に昇格させる対象。

### 3.3 同 issue 複数 PR 検出 (= 1 回目根本未解決)

調査範囲: v0.2.0 / v0.2.1 サイクルでクローズされた 163 issue。代表例:

- **#656**: cp932 → UTF-8 二段 (F4)
- **#365**: ETA bar (#329 不完全) → #687 で再対応
- **#477**: worktree sweep (#493 script → #707 hook 診断で再発フォロー)
- **#681**: get-pip.py SHA (F2 系)
- **#700 / #717** + **#723 / #724**: markdownlint ignores (F5)
- **#522 / #525 / #552**: scorebar V2 (F3)

合計 23 件で同 issue を 2 回以上修正。一部 (#590 UI spec、#461 release workflow、#663 AppError、#508 BtbN 統一) は意図的な multi-PR 分割で健全だが、**意図せず 2 回目 fix が発生したケースは fix 直前に検出したい**。

## 4. 設計

### 4.1 継続項目 (codify、A シリーズ)

#### A1: `docs/refactor-pattern.md` 新設 — 大規模 refactor の Phase 分割パターン

**ドキュメント構成案**:

- §1 適用条件: 単一 PR で touched files > 30 file or 単一 PR で diff > 1000 line になりそうな refactor
- §2 Phase 設計原則:
  - Phase 0: 設計 spec + 影響範囲 inventory
  - Phase 1: data layer / 共通 helper / 型定義 (consumer 0 でも green)
  - Phase 2+: 個別 site migration (per-site が独立 reviewable)
  - Phase Final: legacy fallback 撤去、stale docstring sweep
- §3 reference: AppError migration (#663→#689→#714/716/725/730/733→#745→#746) を実例として詳細解説
- §4 Phase 切れ目の判定基準: 1 PR で「green / regression なし / consumer が選択的に乗り換え可能」が満たせる粒度

**参照契機 (誰がいつ引くか)**:

- **brainstorming skill** (superpowers): creative work の scope 評価で「touched files / diff lines が §1 適用条件閾値を超えそう」と判定した時点で本 doc を引き、Q1 Phase 分割提案を組み立てる
- **`/scope-guard` skill**: 実装中に scope 拡大を検知したケースで「単一 PR で吸収するか Phase 分割するか」の選択肢を提示する場面で本 doc の判定基準を引用
- **`/review-pr` skill** Step 5a (ギャップ分析): 大規模 PR を review する際、Phase 分割すべきだった事案を発見した場合に本 doc の §4 判定基準を引用して triage 表 (B) trigger 3 条件 AND 判定の補強根拠にする
- **CLAUDE.md** §プロジェクト概要 末尾 or §開発ワークフロー に「大規模 refactor の Phase 分割パターンは `docs/refactor-pattern.md` を参照」と 1 行リンクを置く (発見可能性確保)

参照契機を含む受け入れ基準: 上記 4 経路のうち少なくとも 3 経路から本 doc への明示リンクが docs/skills に存在する。

#### A2: `docs/release-process.md` に Track A-D 構造化 patch を追記

**追加 §「Patch release の Track 構造」**:

- §1 適用条件: v0.M.N → v0.M.(N+1) の patch release (security / UX 微調整 / CI fix / version)
- §2 Track 規約:
  - Track 0: spec PR (1 PR、`docs/superpowers/specs/<date>-v0.M.N+1-patch-design.md`)
  - Track A: security/dependency (Dependabot / cargo audit / npm audit)
  - Track B: deferred UX 吸収 (`/release` skill Step 0 (M9) で deferred 全件検証後に「次 patch 吸収」と判定された issue 群)
  - Track C: CI / build gate 追加 (security-audit.yml 等)
  - Track D: version bump + CHANGELOG
- §3 reference: v0.2.1 (#759-#774) を実例として明示
- §4 並列化規約: Track A/B/C は worktree 別、Track D は最後に直列

**参照契機 (誰がいつ引くか)**:

- **`/release` skill** Step 0 / Step 1: patch release を planning するとき本 § を起点に Track template を生成 (M9 と直結)
- **brainstorming skill**: v0.M.N から patch release が必要と判断した bug fix / security alert を計画する場面で本 § を引き、spec の Track 構造を組み立てる
- **`/create-task` skill**: patch release 用の spec PR / Track PR を起票する際、本 § §2 Track 規約に対応する prefix label / scope label を判定して付与
- **CLAUDE.md** §リリース戦略 から本 § へのリンクを既存リンクと並列で配置 (現状 `docs/release-process.md` 全体への 1 行参照のみのため、Track 構造の存在を明示する 1 行を追加)

参照契機を含む受け入れ基準: `/release` skill SKILL.md が本 § を明示参照 + CLAUDE.md §リリース戦略 から本 § (anchor 単位) へのリンクが存在。

### 4.2 再発防止メカニズム (M シリーズ)

#### M1: CI matrix に Windows PowerShell 5.1 job 追加

**ファイル**: `.github/workflows/release.yml`、`.github/workflows/build-windows.yml`

**変更内容**:

- 既存 pwsh (PowerShell 7+) job に加え、`shell: powershell` (Windows PowerShell 5.1) で同じ build script を回す matrix job を追加
- Pester smoke-test も dual shell で実行 (`feedback_ps_setcontent_utf8_bom` の hook 昇格)
- integrity-manifest.json のような encoding-sensitive な artifact は dual job で生成して比較する step を追加
- 既存 issue [#737](https://github.com/Idios/kobutachan-allaganeye/issues/737) (現在 P3-low / deferred) を v0.3.0 開始時に `release-blocker` 昇格し、本 Lane で吸収する

**受け入れ基準**:

- v0.3.0 release.yml が pwsh + PS 5.1 dual matrix で green
- BOM 違いの artifact が CI 上で diff として検出可能
- issue #737 が closed

#### M2: 外部依存 DL の immutable URL 強制ルール

**ファイル**: `scripts/build-portable-zip.ps1`、`docs/l2-workflow.md` §依存規約 (新設)

**変更内容**:

- `Invoke-WebRequest -Uri <url>` 等の外部 DL 行に「must be immutable (versioned tag / SHA pinned)」コメント必須
- Pester regression: 外部 DL URL が `master` / `main` / `latest` を含む場合 fail (`tests/installer/*.Tests.ps1`)
- `docs/l2-workflow.md` に「外部依存規約」§ 新設: 受け入れ可能なソース (PyPA versioned tag / BtbN monthly snapshot / npm registry version-pinned 等) と禁止パターン (latest, main, master, raw HEAD) を列挙

**参照契機 (誰がいつ引くか)**:

- **`/review-pr` skill** Step 5 (ロジック / docs 整合性): PR の touched files に `scripts/build-portable-zip.ps1` / `.github/workflows/*.yml` / installer 関連 .ps1 / Dockerfile 系の外部 DL コードを含む場合、本 § を引いて URL 規約適合を逐条検証 (Step 5b トリアージ表に違反を必ず計上)
- **Pester regression test**: `tests/installer/*.Tests.ps1` のテスト本文で本 § を URL 規約根拠として明示参照 (失敗時のメッセージから読者が辿れる)
- **brainstorming skill**: 新規 installer / build script を設計する creative work で本 § を読み、URL pin 戦略を Q1 に含める (forgetting curve 対策)
- **CLAUDE.md** §外部依存 (新設) に本 § へのリンクを 1 行配置 (発見可能性確保)

参照契機を含む受け入れ基準: `/review-pr` SKILL.md Step 5 に「installer / workflow 系 PR の URL 規約検証は `docs/l2-workflow.md` §依存規約を引く」を明記 + Pester test の comment から `docs/l2-workflow.md` §依存規約への参照リンクを設置。

**受け入れ基準**:

- `scripts/build-portable-zip.ps1` の外部 DL 全行に immutable URL コメント
- Pester テストが latest/main/master URL を検出して fail
- F2 (get-pip / BtbN) と同じパターンを次サイクルで起こさない

#### M3: subagent dispatch HARD-GATE template の規約化

**ファイル**: `docs/l2-workflow.md` §「subagent 起動規約」 (新設)、各 skill prompt template

**変更内容**:

- subagent 起動時の prompt に必ず含めるべき HARD-GATE template を docs 化:
  - `<action_safety>` セクション: 「scope を超える finding → 独断 fix 禁止、BLOCKED 報告のみ」「commit は controller の明示指示後のみ、それ以外は staging 留め」
  - `Stop conditions`: scope 外 path に手を伸ばそうとした瞬間に stop
  - `report_format`: BLOCKED の場合の構造化返却 (`status: BLOCKED, reason: ..., would_have_done: ...`)
- 既存 skill (`/review-pr` `/iterate-review` `/close-issue` `/scope-guard`) の subagent dispatch 行を全数 audit し、template が適用されているか確認
- F6 (#732 / #746 Phase C) と同型の独断 fix が次サイクルで発生しない

**受け入れ基準**:

- `docs/l2-workflow.md` に subagent 起動規約 § が存在
- 既存 skill 内の subagent dispatch 全箇所が template 準拠 (grep audit で確認)
- 新規 subagent dispatch を行う任意の skill / agent が template に準拠

#### M4: encoding boundary audit checklist

**ファイル**: `CLAUDE.md` § バグ修正時の方針

**変更内容**:

- 「バグ修正時の方針」§ の末尾に encoding boundary audit checklist を追加:
  - subprocess fix の場合、以下 3 層を必ず audit:
    1. Python 側: `subprocess.Popen(..., encoding=...)` / `sys.stdout.reconfigure(encoding='utf-8')`
    2. Rust 側 (Tauri): `Command::new(..)` stdin/stdout の encoding / OsString の handling
    3. OS code page: Windows なら `chcp 65001` 想定の動作、cp932 環境での fallback
- F4 (#656/#657/#662) と同型の二段防御漏れが次サイクルで発生しない

**受け入れ基準**:

- CLAUDE.md に encoding boundary audit checklist が記載されている
- (検証) 過去 PR の encoding bug fix を 1 件 sample 取り、checklist が当該事象をカバーしているか確認

#### M5: 同 issue 既存 PR 検出 step を `/review-pr` および `/iterate-review` に追加 (O2 (a) 確定: 警告のみ、block しない)

**ファイル**: `.claude/skills/review-pr/SKILL.md`、`.claude/skills/iterate-review/SKILL.md`

**変更内容** (O2 (a) 「警告のみ」):

- `/review-pr` Step 1 (PR 取得) で元 issue # を解決した直後に、`gh pr list --search "<issue#>" --state merged --limit 10` を実行
- 件数 ≥1 (本 PR 以外に同 issue を fix した merged PR が既存) の場合は Step 5b トリアージ表の冒頭に **警告行のみ** を追加 (block しない):
  - 内容: 「同 issue で過去に merged PR `<N>` 件あります (PR #..., #...)。前回 fix の root cause が今回の変更で完全解消しているか、Step 5 / 5a で重点的に確認してください」
  - 「意図的な multi-phase 分割」(例: AppError migration #663→#689→#714 系の Phase 分割) の場合は元 issue の本文/コメントで明示確認し、警告を「意図的分割と確認済」として処置
- 件数による block / threshold (例: ≥3 件で block) は **設けない**。警告 → user 判断 → review-fix loop で根本検証する責務分担
- 同警告を `/iterate-review` の review-fix ループでも併走 (subagent return 後に main session で表示)

**受け入れ基準**:

- `/review-pr` 起動時に対象 PR の元 issue # を解決し、同 issue の過去 merged PR 件数を表示
- 警告メッセージが console / レビュー本文に明示される
- F4 (#656 系)、F5 (markdownlint)、F2 (URL drift) と同型の reoccurring fix が次サイクルで事前検出される

#### M6: Stop hook に orphan commit 検出を追加

**ファイル**: `.claude/hooks/stop.sh`

**変更内容**:

- 既存の worktree cleanup / claude-branches cleanup の前に、`git fsck --unreachable --no-reflogs` で unreachable commit を検出
  - 検出された unreachable commit object のうち、author が `claude` (Claude Code commit) を含むものを抽出
  - 該当があれば警告ログを `.claude/state/stop-hook.log` に追記し、controller 側で次セッション開始時に提示 (session-start.sh で警告内容を出力)
- 検出条件は heuristic (誤検出は許容、false positive は warning のみで block しない)
- F7 (#741 Task 5) と同型の orphan commit が次サイクルで sweep される
- `preuse.py` の state 記録には現状 subagent dispatch 情報がない (検出は git-native のみで行う)

**受け入れ基準**:

- `.claude/hooks/stop.sh` に orphan commit 検出 step が存在
- session-start.sh が前セッションの orphan 警告を表示
- (検証) 意図的に detached HEAD で commit を作って Stop hook を発火させ、警告が次セッション冒頭に表示されることを確認

#### M7: TodoWrite scope 必須化 + diff 監視 (O4 (b) 確定: heuristic + AskUserQuestion)

**ファイル**: `.claude/hooks/preuse.py` (拡張)、`docs/issue-policy.md` § path↔scope 対応表 (新設)

**変更内容** (O4 (b) 「heuristic + AskUserQuestion」):

- `docs/issue-policy.md` に「path↔scope 対応表」§ を新設:
  - `allaganeye/` / `tests/` (Python) → scope ラベル `l1` / `l2-cli`
  - `gui/src/` → `l2a-gui`
  - `gui/src-tauri/` → `l2a-gui`
  - `scripts/` / `.github/workflows/` → `l2b-installer` / `l2-ci`
  - `.claude/` / `docs/` → `l2-workflow` / `l2-docs`
- preuse.py の Bash 監視を拡張: `git commit` 前に `git diff --staged --name-only` の touched files が、TodoWrite で in_progress の todo の scope (CLAUDE.md「ユーザー指示の短縮記法」の `is<N>` から推測) に対応する path 群に収まっているかを **heuristic 判定**
  - **判定方式 (heuristic)**: path↔scope 対応表 を参考に「明らかに別 scope」と判定できる場合のみ ask を発火させる (例: in_progress scope = `l2a-gui` で `allaganeye/video/detector.py` が staged された場合)
  - **path glob 完全一致は採用しない** (false negative リスク: 対応表に未登録の新規 path で必ず block するのは過剰)
  - 判定 ambiguous (= 対応表に未登録 path や複数 scope 跨ぎの可能性) な場合も ask を発火させる (false positive 寄りの safety 設計、Iron Law 5 整合)
- 外れる場合は `permissionDecision: ask` で AskUserQuestion を強制し、3 択提示
- F6 (scope creep) を実行時に検出

**受け入れ基準**:

- `docs/issue-policy.md` に path↔scope 対応表が存在
- preuse.py が `git commit` 前に heuristic scope check を実行
- 外れた path が含まれる場合に user に 3 択 (a) revert / (b) 別 issue / (c) scope 拡大 を提示
- 判定 ambiguous も ask に倒す (block しない、false positive 寄りで safety)
- (検証) 意図的に scope 外の file を staging し、hook が ask 判定を返すことを確認

#### M8: ~~release-blocker ラベル新設~~ **(撤回、2026-05-17 Idios 判断)**

> **撤回理由**: release 前に `/release` skill が deferred issue を**全件検証**する設計 (M9 再設計版) で、次 patch 吸収判定はその場で行う。事前ラベルで予約管理する必要がない。dual-label メンテのオーバーヘッドも避ける。
>
> 元の O3 判断 (v0.3.0 以降のみ適用) は M8 自体が撤回されたため moot。`release-blocker` label は作成しない。

本 M8 は実装対象から除外。F8 (deferred 持ち越し) の対策は M9 (再設計版) に一本化する。

#### M9: `/release` skill Step 0 強化 — deferred 全件検証 (再設計、2026-05-17)

**ファイル**: `.claude/skills/release/SKILL.md`、`docs/release-process.md` (M9 補強)

**変更内容** (M8 撤回後の再設計):

`/release` skill の Step 0 (現在は受け入れゲート確認) を **Step 0a / 0b / 0c** に分割:

- **Step 0a** (既存): `docs/release-process.md` レイヤーリリース受け入れゲート (既存)
- **Step 0b (新規)**: `gh issue list --label deferred --state open --limit 200` を実行し、**全件**を取得して user に提示
- **Step 0c (新規)**: 各 deferred issue を 1 件ずつ user に確認し、(a) 次 release で吸収 / (b) deferred 継続 / (c) close (won't fix / 再現不能等) の **3 択分類** を強制

##### Step 0c の運用

- 件数 ≤2 件: 1 件ずつ AskUserQuestion で確認
- 件数 ≥3 件: Iron Law 2 に従い「全件 OK / 個別調整 / やめる」の事前確認 + 個別調整選択時のみ 1 件ずつ確認 (bulk operation 規約)
- 確認結果は spec PR (Track 0) に「§deferred 全件検証結果」table として保存 (issue # / 分類 / 判断理由)
- (a) 分類された issue 群 = `docs/release-process.md` §Patch release Track 構造 (A2) の **Track B 吸収候補**

##### Step 0c で block する条件

- deferred 件数 > 0 かつ Step 0c の確認が完了していない → release PR 作成を block
- (a) 分類 issue 群が次 release scope に取り込まれる commit / PR plan を持たない → block (`/iterate-review` / `/create-task` で Track B の plan を先に作る)

##### M8 撤回との整合

`release-blocker` label は作成しない。代わりに **Step 0c の AskUserQuestion 結果を spec PR (Track 0) に table 化**することで、追跡可能性 (どの issue を次 release で吸収すると確定したか) を確保。Track B PR は spec PR の table をリンクで引く。

**参照契機 (誰がいつ引くか)**:

- **`/release` skill** Step 0b / 0c は本 spec 自身の手順
- **`/create-task` skill**: deferred 状態の issue を新規に追加する場面で「次 release タイミングで `/release` Step 0c に必ず再評価される」前提を意識する (issue 本文で `deferred` 理由を明示しないと Step 0c で判断材料が無い)
- **CLAUDE.md** §リリース戦略 から本 § (M9) へのリンク 1 行 (発見可能性)

**受け入れ基準**:

- `/release` skill SKILL.md に Step 0a / 0b / 0c が記載
- Step 0c の 3 択分類の prompt template が SKILL.md に明示
- v0.3.0 / v0.2.x の release 時に deferred 全件検証が行われた証跡 (spec PR の table) が残る
- F8 (deferred 持ち越し) と同型の事象が次サイクルで発生した場合、Step 0c の table から「(a) と分類された issue が Track B で取り込まれていない」ことが即特定可能

#### M10: `docs/markdownlint-guide.md` 新設

**ファイル**: `docs/markdownlint-guide.md` (新規)

**変更内容**:

- §1 強制パターン:
  - `**/<name>/**` (例: `**/node_modules/**`、`**/build/**`、`**/dist/**`)
  - 1 階層 path 直書きは禁止 (`node_modules/` のみは nested に効かない)
- §2 既存 ignore 一覧 (`.markdownlint-cli2.yaml`):
  - `**/node_modules/**`、`**/dist/**`、`**/build/**`、`gui/dist/**` 等の現状一覧と各 ignore の追加 PR # 記録
- §3 既知の glob 仕様:
  - markdownlint-cli2 が使う picomatch の動作 (`**` は 0 階層以上)
  - VS Code の glob と挙動差
- §4 typical fixes: MD028 / MD056 / MD040 etc. の修正パターン
- F5 と同型の 2 度追加 ignore を防止

**参照契機 (誰がいつ引くか)**:

- **`/review-pr` skill** Step 5b (トリアージ): markdownlint CI が fail / docs 変更を含む PR を review する際、違反 rule (MD028 / MD056 / MD060 等) の fix 方針を本 doc から引いて triage 表に対処案を記載
- **`/iterate-review` skill** Step 2.4 (A 修正): markdownlint fail を Round で fix するとき、典型的 violation の fix recipe を本 doc から引く
- **`.markdownlint-cli2.yaml`** ヘッダーコメント (新設): `# See docs/markdownlint-guide.md for ignore pattern rules and typical fixes`
- **`scripts/check-markdownlint.sh`** error 出力末尾に「See docs/markdownlint-guide.md」を付加 (lint failure 時の自然な参照導線)
- **CLAUDE.md** §コマンド (markdownlint コマンド行のすぐ下) に 1 行リンクを置く (発見可能性確保)
- 実装者が `docs/` 編集中に MD028 / MD056 で詰まったとき、上記 5 経路のいずれかから doc へ到達できる設計

参照契機を含む受け入れ基準: 上記 5 経路すべてから本 doc への明示リンクが存在する。

**受け入れ基準**:

- doc が存在し、`.markdownlint-cli2.yaml` のヘッダーコメントから参照されている
- 既存 ignore 全項目が doc にリストアップされている

### 4.3 Codex 統合 (C シリーズ)

設計原則: **Codex は Iron Law (特に 3 / 5 / 6) の補完**として使う。**Codex 自身に独断で fix させない** (Iron Law 3 衝突回避)。**Codex を adversarial second-opinion** として位置付け、最終判断は Claude + Idios。

#### C1: Codex review を `/review-pr` / `/iterate-review` 経由のみで invoke (O1 (b) 確定)

**ファイル**: `.claude/skills/review-pr/SKILL.md`、`.claude/skills/iterate-review/SKILL.md`、`CLAUDE.md`

**変更内容** (O1 (b) 「`/review-pr` `/iterate-review` 経由のみ ON」):

- `/codex:setup --enable-review-gate` は **OFF のまま** (全 turn 自動 invocation はしない)
- 代わりに `/review-pr` と `/iterate-review` の skill flow 内で `/codex:review` または `/codex:adversarial-review` を **明示的に invoke** する (C3 / C2 と統合)
- CLAUDE.md に「Codex review 運用」 § 新設:
  - 趣旨: Codex review は **skill 内で明示 invocation** のみで使う。Stop-time review gate (全 turn auto) は使わない (turn 終端の adversarial pass コストを毎 turn 負担しない設計)
  - BLOCK 相当の指摘の運用: **報告のみ**。Claude は finding を Idios に提示し、AskUserQuestion で「修正 / 無視 / 別 issue 起票」の 3 択を強制
  - **Claude が独断で auto-fix に走らない**ことを明示 (Iron Law 3 / 5 衝突回避)

**受け入れ基準**:

- `/codex:setup --status` で review-gate が **disabled** 表示 (項目変更を確認)
- `/review-pr` SKILL.md と `/iterate-review` SKILL.md に Codex review 統合 step が記載 (C2/C3 と整合)
- CLAUDE.md に運用 § が記載
- (検証) v0.3.0 サイクル最初の `/review-pr` 実行で Codex review が invoke された証跡が残る

#### C2: Iron Law 6 Pre-flight に Step 5 として `/codex:adversarial-review` 追加

**ファイル**: `.claude/hooks/session-start.sh` (Iron Law 6 本文)、`docs/l2-workflow.md` § PR 作成 Pre-flight

**変更内容**:

- 現在の Pre-flight Step 0 (重複 PR ハードゲート) → Step 1 (base 同期) → Step 2 (取り込み未済 commit) → Step 3 (touched files 交差) → Step 4 (並行 PR 重複再確認) の後に **Step 5: `/codex:adversarial-review`** を追加
- focus 文字列で project 固有焦点を渡す:
  - 「Iron Law 3 (scope creep) を疑え。touched files が元 issue の宣言 scope と整合するか」
  - 「ffmpeg / GPU fallback / encoding boundary を疑え (F1 / F4 再発を阻止)」
  - 「同 issue 過去 PR の root cause が今回も残っていないか (M5 と協調)」
- `/codex:adversarial-review` の finding は Claude が裁き、(A) 本 PR 修正 / (B)(C) handoff のどちらかに振り分け (`/review-pr` Step と同じ triage)
- 「BLOCK」相当の指摘でも Codex 自身に commit させない (M3 と整合)

**受け入れ基準**:

- session-start.sh Iron Law 6 本文に Step 5 が追記
- `docs/l2-workflow.md` § PR 作成 Pre-flight に Step 5 詳細が記載
- (検証) v0.3.0 サイクル最初の PR で Step 5 が実行された証跡

#### C3: `/review-pr` の code quality 部分に optional `/codex:review` を併走

**ファイル**: `.claude/skills/review-pr/SKILL.md`

**変更内容**:

- 既存 `/review-pr` の Step 構造 (現行):
  - Step 1: PR 取得 (タイトル / 本文 / diff) + M5 で元 issue 過去 PR 検出
  - Step 2: ベース同期確認 (2.1 base 最新化 / 2.2 影響候補 / 2.3 並行 PR)
  - Step 3: 受け入れ条件ゲート (`enforce-acceptance-criteria`)
  - Step 4: CI 確認
  - Step 5: ロジック / docs 整合性 (5a ギャップ分析 / 5b トリアージ / 5c sweep)
  - Step 6: レビュー報告 (markdown 生成)
  - Step 7: 次のアクション提案 (`/iterate-review` 起動)
  - Step 8: マージ (user 側)
- Step 5a (ギャップ分析) に optional として `/codex:review --base develop-X.Y.Z` を併走させる選択肢を追加
- 起動条件 (推奨基準):
  - PR diff が大きい (touched > 15 file or > 500 lines)、または
  - 過去 root cause が複数 (M5 警告 ≥2 件)、または
  - L1 (CLI / detector / GPU) の core ロジック変更を含む
- Codex の finding は Step 5b triage 表に「出所 = codex:review」と記載して統合
- Codex に直接 commit させない (M3 整合)

**受け入れ基準**:

- `/review-pr` SKILL.md の Step 5 に optional `/codex:review` 呼び出しが記載
- triage 統合の手順が明記

#### C4: `/codex:rescue` を root-cause 調査専用に絞り scope-guard で囲む (O5 (b) 確定)

**ファイル**: `.claude/skills/scope-guard/SKILL.md`、`CLAUDE.md` § バグ修正時の方針

**変更内容** (O5 (b) 「root-cause 専用」、常用しない):

- CLAUDE.md「バグ修正時の方針」§ に追記: 根本原因分析 / 類似バグ調査 phase で `/codex:rescue` を **限定的に併用** してよい。ただし以下を必須:
  - rescue prompt に `<action_safety>` で「scope を超える finding → 独断 fix 禁止、BLOCKED 報告」を明記 (M3 と完全整合)
  - `--write` default のままだが、Codex が write する場合は staging のみ、commit / push は controller (Claude + Idios) の明示指示後
  - rescue 完了後、Idios に finding を提示し、AskUserQuestion で「本 PR 修正 / 別 issue / 無視」の 3 択
- **常用は禁止**: 機能実装 / refactor / docs 改修等で `/codex:rescue` を default invocation するのは Iron Law 3 / 5 衝突リスク高、`/codex:review` (read-only adversarial) を優先
- `/scope-guard` skill の検査対象に Codex commit (`git log --author=...codex...`) を追加 (実装は heuristic)

**受け入れ基準**:

- CLAUDE.md に `/codex:rescue` 運用ルール (root-cause 専用、常用禁止) が記載
- `/scope-guard` の検査範囲に Codex commit が含まれる
- (検証) 意図的に scope 外の rescue を試み、scope-guard が detect することを確認

#### C5: superpowers subagent (実装) → `/codex:review` (adversarial pass) の直列構成

**ファイル**: `docs/l2-workflow.md` § subagent + Codex 直列構成 (新設)

**変更内容**:

- 直列ワークフローを doc 化:
  1. superpowers `subagent-driven-development` で Claude 内 fresh subagent が実装 + 2-stage review (spec + code quality)
  2. controller (Claude main) が subagent commit を branch HEAD に到達確認 (M6 と整合)
  3. `/codex:review` (Codex GPT-5.4) で adversarial pass
  4. Codex finding を triage (Claude + Idios)
- **並列ではなく直列推奨** (Codex 自身に fix させない、Iron Law 整合)
- Iron Law 6 Pre-flight の Step 5 (`/codex:adversarial-review`) とは別の用途 — こちらは review-pr 段階の deep-dive

**受け入れ基準**:

- `docs/l2-workflow.md` に直列構成 § が存在
- 図 (mermaid または ascii) で flow を視覚化

#### C6: Codex token 枯渇 / failure 時の Claude Code fallback (2026-05-17 Idios 指示で追加)

**ファイル**: `.claude/skills/review-pr/SKILL.md`、`.claude/skills/iterate-review/SKILL.md`、`docs/l2-workflow.md` § Codex fallback (新設)、`CLAUDE.md` § Codex 運用

##### 背景

Codex CLI は GPT-5.4 API quota / rate limit / network 等の理由で fail することがある。C1 (skill 内 invocation) / C2 (Iron Law 6 Step 5 adversarial-review) / C3 (`/review-pr` Step 5a optional) / C4 (`/codex:rescue` root-cause) / C5 (subagent → Codex 直列) のいずれの経路でも、Codex が応答できなくなる状況が起こり得る。Codex 不在を理由にレビュー / 調査 phase を skip するのは Iron Law 1 / 6 違反 (受け入れ条件検証 / Pre-flight ゲート不通過のまま進行) になるため、**Claude Code 側で同等処理を fallback 実行**する設計を入れる。

##### 検出方法

`scripts/codex-companion.mjs` (codex プラグイン runtime) の exit code / stderr / stdout last line を確認:

| 検出条件 | 判定 |
| --- | --- |
| exit code 非ゼロ + stderr に `rate.?limit`, `quota`, `429`, `usage_limit` のいずれか | **token 枯渇 (明確)** → 自動 fallback |
| exit code 非ゼロ + stderr に `auth`, `unauthorized`, `401`, `403`, `api.?key` | **認証失敗 (明確)** → 自動 fallback + user notify |
| exit code 非ゼロ + stderr に `timeout`, `EHOSTUNREACH`, `ENETUNREACH`, `ECONNRESET` | **network failure (明確)** → 自動 fallback |
| exit code 非ゼロ + 上記いずれにも該当しない stderr | **曖昧** → user に AskUserQuestion (再試行 / Claude fallback / abort) |
| exit code 0 + stdout が空 / parse 不能 | **応答異常** → user に AskUserQuestion |

##### Fallback 戦略 (Codex command 別)

| Codex command | 通常用途 | Fallback 内容 |
| --- | --- | --- |
| `/codex:review` (C3 で `/review-pr` Step 5a に invoke) | code quality adversarial pass | **superpowers `requesting-code-review` subagent** を起動して同等の adversarial review。focus 文字列 (Iron Law 3 / encoding / GPU fallback 等) は Codex 用と同じ |
| `/codex:adversarial-review` (C2 で Iron Law 6 Step 5 に invoke) | Pre-flight 第 5 ゲート | **superpowers `requesting-code-review` subagent + project 固有 focus** を起動。subagent prompt に「adversarial / approve させない姿勢」を `<grounding_rules>` 相当で明示 |
| `/codex:rescue` (C4 で root-cause 調査時に invoke) | bug 根本原因 + 類似バグ探索 | **Claude main + superpowers `systematic-debugging` skill** を起動して自力で根本原因調査。`/scope-guard` 規約は維持 (独断 fix 禁止) |

##### Fallback 実行時の必須記載

skill report (Step 6 レビュー報告 / Round summary comment) に以下を**必ず明示**:

```text
> **Codex fallback notice**: 本 review は Codex CLI が <検出条件> で fail したため、
> Claude Code (superpowers:<skill-name>) で代替実行しました。
> Codex 側の review は次セッションで再試行を推奨します。
> stderr 要約: <stderr の先頭 200 字>
```

これがないと Idios が Codex review 済と誤認するリスクがある (Iron Law 5 衝突回避)。

##### Fallback の限界 (明示)

- Codex は GPT-5.4 (独立 model) の second opinion。Claude Code fallback は同一 model の self-review に近く、bias 構造が同じになる
- 重要 PR (release 直前 / 大規模 refactor) で Codex fallback が trigger した場合、user に通知し「Codex 復旧後の再 review を待つか、Claude fallback で push するか」の AskUserQuestion 3 択を提示
- fallback report には「fallback で実行済」を明示することで、後日 Codex 復旧時に再 review が要否を判断可能にする

##### 参照契機

- **`/review-pr` skill** Step 5a (Codex 併走パート): Codex invocation 直後の return code 判定で本 § を引いて fallback 分岐
- **`/iterate-review` skill** Round 内の Codex invocation 直後で同様
- **`docs/l2-workflow.md`** § Codex fallback (新設) に検出条件 table + fallback 戦略 table + 必須記載 template を一本化、各 skill から参照

**受け入れ基準**:

- `docs/l2-workflow.md` に § Codex fallback が存在 (検出条件 / 戦略 / 必須記載 template)
- `/review-pr` `/iterate-review` SKILL.md に Codex invocation 後の return code 判定 + fallback 分岐が記載
- CLAUDE.md § Codex 運用に 1 行リンク
- (検証) 意図的に Codex を `--model invalid` 等で fail させ、Claude fallback で同等の review が完了し report に「Codex fallback notice」が記載されることを確認

## 5. 実装 Lane と issue 分解

| Lane | 内容 | 影響範囲 | 推定 PR 数 |
| --- | --- | --- | --- |
| **L-α** | CI/hook 補強 (M1 PS5.1, M6 Stop hook, M7 scope_issue) | `.github/workflows/`, `.claude/hooks/`, preuse.py | 3 |
| **L-β** | skill 改訂 (M3 subagent template, M5 同 issue 検出, M9 `/release` Step 0a/0b/0c (deferred 全件検証), C2/C3/C4/C6 Codex 統合 + fallback) | `.claude/skills/` | 5 |
| **L-γ** | docs codify (A1 refactor-pattern, A2 release-process Track 化, M2 依存規約, M4 encoding checklist, M10 markdownlint-guide) | `docs/`, `CLAUDE.md`, `docs/issue-policy.md` | 3 |
| **L-δ** | Codex 統合の運用化 (C1 review gate は OFF のまま、`/review-pr` `/iterate-review` 内で明示 invocation、CLAUDE.md に運用追記、C5 直列構成 doc、C6 fallback doc) | `CLAUDE.md`, `docs/l2-workflow.md` | 2 |

合計 **約 13 PR** (M8 削除で 14 → 13)。v0.2.0 サイクルの 130 PR と比較して軽量。v0.3.0 開発初期 (3-7 日想定) で完結させる。

### Lane 間依存

- L-γ A1/A2 は Lane 独立、最初に着手可能
- L-α M7 (scope check) は L-γ の path↔scope 対応表 (docs/issue-policy.md) を前提とするため、L-γ が先
- L-β M5 (同 issue 検出) / M9 (`/release` Step 0c) は単独で着手可能
- L-β C6 (Codex fallback) は L-δ の C1/C2/C3 と整合が必要なため、L-β 内では fallback skeleton まで、最終文言は L-δ と co-design
- L-δ C1/C5/C6 は L-β の C2/C3/C4 完了後 (運用化は skill 改訂後)

推奨着手順序: **L-γ → L-α → L-β → L-δ**

## 6. 受け入れ基準 (全体)

本 spec から派生する各 Lane / PR の受け入れ基準は §4 各 M / C / A の「受け入れ基準」を参照。全体としての受け入れ基準は以下:

- v0.3.0 サイクル最初の 5 PR で:
  - M1 PS5.1 dual matrix が CI で実行されている
  - M5 同 issue 検出警告が `/review-pr` 起動時に表示される
  - C2 Iron Law 6 Step 5 (`/codex:adversarial-review`) が Pre-flight で実行された証跡
  - M7 scope check が `git commit` 前に走った証跡
  - C6 Codex fallback が意図的 fail で発火し fallback notice が report に記載された証跡
- v0.3.0 リリース時点で:
  - L-α / L-β / L-γ / L-δ の全 PR がマージ済
  - F1-F8 のいずれかと同型の事象が再発した場合、検出メカニズムが trigger した証跡が残る
  - `/release` skill Step 0c で deferred 全件検証が行われた spec PR (Track 0) の table が残る
- 検証手順: v0.3.0 retrospective を本 spec のテンプレートで再実施し、F1-F8 の再発率が顕著に下がっていることを確認

## 7. リスクとオープン点

### リスク

| # | リスク | 影響 | 緩和策 |
| --- | --- | --- | --- |
| R1 | M7 (scope check) の path↔scope 対応表メンテ負荷 | 高 (新規 path 追加時に毎回 doc 更新) | issue policy で「新規 top-level dir 追加時は対応表更新必須」を明記。CI で対応表と repo の top-level dir 差分を検出する optional check (将来) |
| R2 | C1 (Codex review invocation) が `/review-pr` / `/iterate-review` セッションを遅延 | 低 (skill 内 invocation のみ、毎 turn では走らない) | O1 (b) 確定により Stop-time review gate (全 turn auto) は OFF のまま。skill 内 invocation は触る turn 数が限定されているため遅延も限定的 |
| R3 | C2/C3/C4 で Codex が独断 fix を実施 | 高 (Iron Law 3 衝突) | M3 subagent template と同じ `<action_safety>` を Codex prompt にも徹底。`/scope-guard` の検査範囲に Codex commit を含める (C4) |
| R4 | M5 同 issue 検出が false positive (意図的な multi-PR 分割) | 低 (警告のみで block しない) | 警告メッセージで「意図的分割なら明示確認」と促す。block ではなく ask 判定 |
| R5 | M1 PS5.1 dual matrix が CI 時間を大幅に増やす | 中 | release.yml のみ dual、PR CI は pwsh のみ。F1 系の事故は release 直前に検出できれば充分 |
| R6 | C6 Codex fallback で Claude self-review に倒れ、second-opinion bias が同一化 | 中 (重要 PR で Codex 復旧前に push) | fallback notice で「再 review 推奨」を明示。重要 PR (release 直前 / 大規模 refactor) は user に AskUserQuestion で push 可否を確認 |
| R7 | M9 Step 0c 全件検証が deferred 件数増加で重くなる | 中 (将来 deferred が 50+ 件になると 1 release で全件確認できない) | Step 0c で「件数 ≥3 は bulk 確認 + 個別調整」運用 (Iron Law 2 整合)。長期的に deferred を定期的に再評価する別 cadence を `/release` 外で導入する余地あり |

### 確定事項 (Idios 判断、2026-05-17)

| # | 判断点 | 確定 | 反映先 |
| --- | --- | --- | --- |
| O1 | Codex review gate を全 turn で ON にするか、特定 skill 経由のみ | **(b) `/review-pr` `/iterate-review` 経由のみ ON** (全 turn auto は使わない) | C1 / L-δ |
| O2 | M5 同 issue 検出を `/review-pr` 起動時警告のみとするか、block にするか | **(a) 警告のみ** (block / threshold は設けない、user 判断に委ねる) | M5 |
| O3 | ~~release-blocker label を v0.2.1 Track B 吸収済 issue に遡及付与するか~~ | **moot** (M8 が撤回されたため判断不要) | M8 撤回 |
| O4 | M7 scope check の判定基準を「path glob 完全一致」とするか「heuristic」とするか | **(b) heuristic + AskUserQuestion** (ambiguous も ask に倒す、false positive 寄り safety) | M7 |
| O5 | `/codex:rescue` を導入時期から常用するか、root-cause 専用に絞るか | **(b) root-cause 専用** (常用禁止、`/codex:review` を優先、Iron Law 整合) | C4 |

### 追加方針 (Idios 判断、2026-05-17 追補)

| # | 判断点 | 確定 | 反映先 |
| --- | --- | --- | --- |
| D1 | M8 `release-blocker` label を新設するか | **撤回 / 不要** (release 前に `/release` skill Step 0c で deferred 全件検証する設計で代替) | M8 削除、M9 再設計 |
| D2 | Codex token 枯渇 / failure 時の動作 | **Claude Code (superpowers:requesting-code-review / systematic-debugging) で fallback 実行、report に明示** | C6 新設 |
| D3 | 新設 doc (A1 / A2 / M2 / M10) の参照契機を明示するか | **必須** (各 doc が孤立した存在にならないよう skill / hook / CLAUDE.md から参照経路を 3-5 個明記) | A1 / A2 / M2 / M10 §参照契機 追加 |

確定後、各 Lane の実装 PR は本表の確定値で進める。

## 8. 関連リンク

- `CLAUDE.md` (project root) — Iron Law / バグ修正方針 / Plugin との関係
- [.claude/hooks/session-start.sh](.claude/hooks/session-start.sh) — Iron Law 6 条 + Pre-flight Step 0-4 の正本
- [docs/l2-workflow.md](docs/l2-workflow.md) — workflow 規約全般
- [docs/issue-policy.md](docs/issue-policy.md) — ラベル運用 / issue 規約
- [docs/release-process.md](docs/release-process.md) — レイヤーリリース受け入れゲート
- openai-codex プラグイン: `C:/Users/idios/.claude/plugins/cache/openai-codex/codex/1.0.4/`
- superpowers プラグイン: `C:/Users/idios/.claude/plugins/cache/claude-plugins-official/superpowers/`
- 参照 memory: `feedback_iterate_review_no_scope_creep_option`, `feedback_subagent_dispatch_stop_on_scope_creep`, `feedback_subagent_orphaned_commit`, `feedback_ps_setcontent_utf8_bom`, `feedback_brainstorming_sweep_repo_wide_grep`, `feedback_skill_revision_empirical`, `feedback_markdownlint_typical_fixes`

---

(本 spec は Idios review を経て承認された後、writing-plans skill により 4 Lane 単位の implementation plan に分解される。)
