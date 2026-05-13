# L2 開発ワークフロー

L2 では**単一ワークツリー + skill ベースディスパッチ**で開発する。

## 背景

L2 の複数スコープ並行開発 (GUI / インストーラ + 周辺プロセス改善) では以下を満たす設計が必要:

- 単一ワークツリーでブランチ・コンフリクト管理を簡素化する
- #367 で顕在化した PR 不完全修正問題への対策として、レビュー受け入れ基準を明文化する
- 他 Anthropic ベストプラクティス (code.claude.com/docs/en/best-practices) の「単一セッション + 明確な計画」推奨に整合する

## アーキテクチャ

### 単一ワークツリー + skill ディスパッチ

```text
E:/projects/kobutachan-tools/kobutachan-allaganeye/  ← 唯一の worktree (main or develop-x.x.x)
    ├── .claude/hooks/
    │   ├── session-start.sh         ← Iron Law を毎セッション先頭に注入 (superpowers 方式)
    │   ├── preuse.py                ← Bash 実行前の確認ゲート (#401 由来)
    │   └── post-merge-reload.sh     ← マージ後のリロード
    ├── .claude/skills/
    │   ├── review-pr/               ← PR レビュー (#367 対策強化版)
    │   ├── enforce-acceptance-criteria/  ← 受け入れ条件逐条検証ゲート (Iron Law 1)
    │   ├── scope-guard/             ← スコープ逸脱検知 (Iron Law 3)
    │   ├── create-task/             ← issue 起票
    │   └── release/                 ← リリース作業
    └── docs/knowledge/              ← セッション横断の知見蓄積
```

ユーザーは**単一セッション**で作業する。既存 skill は上記 5 件。計画立案・実装・PR 提出前の実機検証等は本ドキュメント (§タスク種別と進め方) の手順に従い、AskUserQuestion や Agent 呼び出し、TodoWrite で構成する。

新規 skill の追加は**実際に反復利用されることが判明した時点**で行う (L2 実装開始後、同じプレイブックを 2-3 回使った段階等)。事前に空の skill ファイルは作らない。

### 複数スコープ並行開発のブランチ戦略

L2 は `develop-0.2.0` を統合先とする。複数スコープは**単一ブランチの統合**で運用する:

```text
main (リリースタグのみ)
 └── develop-0.2.0 (L2 統合先)
      ├── claude/l2-gui-*            ← GUI 関連作業ブランチ (#105 子)
      ├── claude/l2-installer-*      ← インストーラ作業 (#106 子)
      ├── claude/l2-workflow-*       ← L2-0 プロセス系 + guard 運用連携 doc
      └── claude/l1-residual-*       ← L1 残課題消化 (#412-#440)
```

**ブランチ命名規則**: `claude/<scope>-<short-description>` または `claude/<issue-N>-<slug>`

**PR ベース**: 全て `develop-0.2.0`。作業ブランチ間の依存は rebase で解消し、`develop-0.2.0` マージ前に最新状態に揃える。

**リリース時**: `develop-0.2.0 → main` をマージ → `v0.2.0` タグ。

## タスク種別と進め方

タスクを「種別ごと」に skill + CLAUDE.md / 本ドキュメントのガイダンスへ振り分ける。粒度は役割ではなくアクションで分ける。

| タスク種別 | 対応 skill / 手段 | 責務 |
| --- | --- | --- |
| 計画立案 | Plan モード + AskUserQuestion + TodoWrite | タスクの分解、リスク・曖昧点の事前洗い出し、実装前の計画合意 |
| 実装 | Claude の通常ツール (Edit/Write/Bash) + TodoWrite | 実装 + unit/integration テスト + 実機検証 (long-running / GPU / audio 統合は mock 不可) + PR 作成。スコープ逸脱時は Plan モードに戻る |
| PR review-fix loop | `/iterate-review` | PR 作成後の review-fix ループ自動化 (Round cap 5、(A) 強優先、握り潰し防止 validation、収束時 summary コメント 1 個投稿) |
| PR レビュー | `/review-pr` | PR レビュー + #367 受け入れ基準チェックリスト検証 + マージ判断 |
| issue 起票 | `/create-task` | issue 起票 (定型テンプレート適用) |
| issue クローズ | `/close-issue` | マージ後の受け入れ条件実測再検証 + 残タスクトリアージ + `gh issue close` 実行 (Iron Law 4 担保ルート、#594 で `/review-pr` から責務分離、#607 で `Refs #N` fallback 対応 / #606 で eval/reports 構造整理) |
| リリース | `/release` | リリースタグ、CHANGELOG、main へのマージ |

権限境界 (close 操作、コード変更操作等) は**人間 = ユーザーが判断**する責任とする。Claude は曖昧点を `AskUserQuestion` でユーザーに確認する。

**`/iterate-review` の起動経路**: user 手動 (`/iterate-review <PR#>`) と agent 自動 (PR 作成セッションが PR 作成後に skill として呼ぶ) の両方をサポート。Iron Law 6 Pre-flight 通過後に呼ぶこと。

反復利用される手順があれば、実運用でパターンが固まった時点で新規 skill を追加する (事前に空の skill は作らない)。

## resume-plan handoff protocol (Iron Law 6 サブ条、#722)

> 2026-05-13 #722 で導入。PR #721 (#705 BtbN monthly pin) で発生した race condition の再発防止。

session が contingency 用 resume task prompt を生成して user に提示する際は、prompt の **1 行目** に EXECUTOR ディレクティブを必ず記述する。書式は固定で、機械パース可能・人間も即座に判別可能とする。

### EXECUTOR ディレクティブ書式

```text
EXECUTOR: self (origin=<session-id>, generated=<ISO-8601>)
EXECUTOR: dispatch (origin=<session-id>, generated=<ISO-8601>)
```

| field | 意味 | 例 |
| --- | --- | --- |
| `EXECUTOR` | `self` または `dispatch` | `dispatch` |
| `origin` | prompt 生成 session の worktree dir 名 (session-id 相当) | `exciting-northcutt-a3f7b8` |
| `generated` | prompt 生成時刻 (ISO-8601 + tz、`date -Iseconds` 出力) | `2026-05-13T22:14:33+09:00` |

正規表現 (受信側 parse 用): `^EXECUTOR: (self|dispatch) \(origin=([^,]+), generated=(.+)\)$`

### self / dispatch のセマンティクス

| mode | origin session の状態 | user の期待 action | 受信した session の振る舞い |
| --- | --- | --- | --- |
| `self` | **継続中**。prompt は context loss 時の保険文書 | 何もしない (origin が走る)。context loss を検知した場合のみ手動 dispatch | (通常は受け取らない)。受け取った場合 = origin が context loss した想定 → `gh pr list --search "<元 issue#>" --state all` で origin 痕跡確認 → `AskUserQuestion` で「(A) origin 痕跡なしで仕切り直し / (B) 当 prompt は誤 dispatch、abort」を提示 |
| `dispatch` | **abort 済み** | 新規 session に dispatch | origin が abort 済 = fresh start。Iron Law 6 Pre-flight 通常実施 |

### 生成側 (origin session) のルール

1. prompt 生成 **時点で** どちらの mode かを明示的に決定
2. dispatch mode で生成した直後、origin session は当該 PR 作成 / 実装作業を **stop** する (= abort confirmation)
3. self mode 生成は user 透過の contingency 文書として扱い、origin は実行を継続
4. 1 session が同一 issue について self と dispatch の **両方** の prompt を user に提示することはしない (PR #721 race condition の原因)

### 受信側 (dispatch された fresh session) のルール

1. 受け取った prompt の 1 行目を上記正規表現で parse
2. parse fail → `AskUserQuestion` で「(A) legacy prompt として扱う (handoff 規約適用前と仮定して着手) / (B) prompt 不正のため当 session を abort、user に prompt 再生成を依頼」
3. `EXECUTOR: dispatch` → そのまま着手
4. `EXECUTOR: self` → 上記「self / dispatch のセマンティクス」表の self 行のフローを実行 (`gh pr list --search` で origin 痕跡確認 → AskUserQuestion)

### prompt template 例

```text
EXECUTOR: dispatch (origin=exciting-northcutt-a3f7b8, generated=2026-05-13T22:14:33+09:00)

# Resume: <タスク表題> (issue #<N>)

## Context
<原 issue 状況、関連 PR、最終決定事項を 5-10 行>

## Acceptance criteria
<受け入れ条件をフルコピー>

## Plan
<手順を箇条書き、最後の "STOP and ask user" 点を明示>
```

template 内の各節は既存実装と整合する位置取り。Iron Law 4 (Closes 禁止) 適用。

## PR 作成 Pre-flight (Iron Law 6 サブ条)

PR 作成前に base 最新化と並行 worktree PR 重複を必ず確認する。`feedback_pr_review_base_merge_regression.md` (PR #627 Round 4 で発覚した base 取り込み機能 regression) と `feedback_concurrent_worktree_pr_check.md` (#646 / PR #647 並行作業重複) の skill / 規約昇格として運用化 (2026-04-29 #659)。

### 4 ステップ手順

```bash
# 1. base 最新化 (read-only fetch)
git fetch origin <base>            # <base> = develop-0.2.0 等

# 2. 取り込み未済 commit 列挙
git log HEAD..origin/<base> --oneline

# 3. touched files 交差判定 (取り込み未済 commit が当 PR と同 path を触っていないか)
#    - 当 PR の touched files
git diff --name-only origin/<base>
#    - 取り込み未済 commit の touched files
git diff --name-only HEAD origin/<base>
#    両者の交差ありなら、base 取り込み (merge or rebase) + 検証再実行が必要

# 4. 並行 worktree 同 issue PR 重複確認
gh pr list --search "<元issue#>" --state all \
  --json number,headRefName,state,createdAt
```

### 判定

- **取り込み未済 commit ゼロ**: そのまま PR 作成
- **取り込み未済 commit あり、touched files 交差なし**: 取り込み不要、PR 作成 (base HEAD は Pre-flight 実施時点を記録)
- **取り込み未済 commit あり、touched files 交差あり**: `git merge origin/<base>` (または rebase) で取り込み → Iron Law 6 自動チェック (`ruff` / `pyright` / `pytest` / `npm run lint`/`typecheck`/`test`/`build` / `cargo check` 等、変更 path に応じて) を再実行 → PR 作成
- **並行 PR 検出**: 各 PR の状態 (open / merged) を確認。重複なら計画見直し or `AskUserQuestion` でユーザー判断

確認結果は **PR テンプレート §「ベース同期確認」** (4 項目を plain bullet で) に記録する。validate-checklist は plain bullet を無視するため CI ゲートは増設しないが、レビュー時に `/review-pr` Step 2 が `gh pr view` 経由で機械的に再確認するため、握り潰しは禁止。

### Red Flags

| 浮かんだ思考 | 実態 |
| --- | --- |
| 「コンフリクト出ないから OK」 | merge 可否 (CONFLICT 不在) と機能 regression は別軸。base / head の同ファイル grep 対比が必要 |
| 「最近 fetch したから OK」 | 数分でも別 PR がマージされうる。PR 作成直前に再 fetch する |
| 「並行 PR は計画段階で確認したから skip」 | 計画後に別 worktree が PR を提出するケースあり (#646 / PR #647)。PR 作成時にも実施 |
| 「Pre-flight で path 交差なしと判定したから自動チェック skip」 | path 交差判定と Iron Law 6 自動チェックは独立軸。Iron Law 6 は変更 path 別に毎 PR 作成時に実施 |

### 機能 regression 検出手順 (base 取り込み時 / レビュー時)

> originally from `feedback_pr_review_base_merge_regression.md`, absorbed 2026-05-01

**CI green は内部整合性のみを保証し、機能 regression の防御線にはならない**。base 取り込み merge commit を見たら、以下の手順で base / PR head の同ファイル比較を実施する (PR 作成時 + `/review-pr` Step 2.3 で実施)。

#### 検証手順

1. **base head sha 確認**:

   ```bash
   gh api repos/<owner>/<repo>/branches/<base>
   ```

2. **base / PR head 双方の同ファイル取得**:

   ```bash
   gh api "repos/<owner>/<repo>/contents/<path>?ref=<base>"        # base 側
   gh api "repos/<owner>/<repo>/contents/<path>?ref=<PR-branch>"   # PR head 側
   ```

   または ローカルで `git show <base>:<path>` と `git show <PR-branch>:<path>` で取得して `diff` 比較。

3. **重要な変更の保持確認** (`git log --oneline <base>..<PR-branch>` 起点に grep で対比):
   - 新フィールド (例: metadata schema 追加項目)
   - 関数引数 (例: `_build_metadata_payload` の新引数)
   - schema 変更 (例: JSON Schema `properties` 追加)
   - 新規エクスポート (例: 新型定義の `__all__` 追加)

4. **特に注意すべきファイル**: メタデータ・schema・型定義 (`allaganeye/commands/split_matches.py` / `schemas/metadata.schema.json` / `docs/metadata-spec.md` / `gui/src/types/*.ts` / `allaganeye/metadata_types.py` 等) で base 側追加が PR head に保持されているか必ず確認。

#### 例 (PR #627 Round 4 で発覚した規範ケース)

base develop-0.2.0 が PR #626 でマージされ `_build_metadata_payload(detection_started_at, detection_completed_at)` 引数追加を含んでいた。本 PR (#627) は merge conflict 解消時にこの引数追加を取り込み忘れたが、test fixture / schema / 実装が内部整合性で揃っていたため CI 全 8 ジョブ pass。検出されないままマージしていれば GUI CompleteScreen「所要」列の元データが失われていた。

→ 「CI green = OK」と即断せず、上記 grep 対比を実施することで機能 regression を捕捉する。

> 注: 並行 worktree PR 重複確認 (step 4) は **計画立案セッションの Phase 1 Explore でも実施** する。`gh pr list --search "<issue#>" --state all` を Bash 並列起動の 1 つに含める。`git log --all` で別 worktree branch の commit が見えても、PR として open かどうかは別 — `gh pr list` が一次情報源。

## PR 作成 path 別自動チェック (Iron Law 6 main 条)

> originally from `feedback_pr_pre_creation_checks.md`, absorbed 2026-05-01

PR 作成前のローカル自動チェックは、変更ファイル path に応じて **必要 job をすべて実行する**。「軽微だから skip」「Python のみだから GUI 側不要」は Iron Law 6 違反 / 失敗パターン A 再発。

### path 分類表

| 種別 | 判定パターン | 実行する自動チェック |
| --- | --- | --- |
| **python-core** | `allaganeye/**/*.py`, `tests/**/*.py`, `pyproject.toml` | `ruff check .` / `ruff format --check .` / `pyright` / `pytest` (slow 除外) |
| **gui-frontend** | `gui/src/**`, `gui/package.json`, `gui/tsconfig.json`, `gui/vite.config.ts`, `gui/eslint.config.js` | `cd gui && npm run lint` / `npm run typecheck` / `npm test` / `npm run build` |
| **gui-rust** | `gui/src-tauri/**` | `cargo check --manifest-path gui/src-tauri/Cargo.toml` |
| **installer-pester** | `scripts/**/*.ps1`, `scripts/tests/**` | `Invoke-Pester -Path scripts/tests/` (Windows 上で) |
| **docs-only** | `docs/**/*.md`, `README.md`, `CHANGELOG.md`, `CLAUDE.md` のみ。コードファイル 0 件 | `bash scripts/check-markdownlint.sh` (CI と同 version の markdownlint-cli2) + 本 doc §「doc 節参照健全性確認」: §「<旧名>」grep で残骸ゼロ確認 |

### 複合判定ルール

- 上記の複数種別にまたがれば **すべて実行** (例: python + gui-frontend なら 8 個の lint/test ジョブ全部)
- 完全 docs-only でも path 識別子変更を含むなら `.github/workflows/` と `allaganeye/` への波及確認 (`/review-pr` の §D doc-only PR 検証手順と整合)
- `.claude/hooks/`, `.claude/skills/`, `.claude/settings*.json` 変更は **メタ変更** として「skill 自体の eval が必要か」を `AskUserQuestion` で確認

### fail 時の対応

`(A) PR 内修正優先 規約` (本 doc §) に従い、`AskUserQuestion` で 3 択提示:

- **(A) [Recommended]** 同セッションで修正して再実行
- (B) PR 作成を中断して plan モードに戻る (大きな修正が必要と判明)
- (C) 強制 skip (Self-Test Report の `[ ]` を残し validate-checklist で fail させる、Iron Law 6 違反の自覚を促す)

### 例外

- 既に同セッションで全 job pass している (rebase / 修正後の再実行不要) → skip 可
- フィードバック自体への変更 (本 doc の編集) → 循環依存を避けるため `AskUserQuestion` でユーザー判断

## 実機検証 trigger 表 (Iron Law 6 main 条)

> originally from `feedback_user_realmachine_test_request.md`, absorbed 2026-05-01

ロジック変更を含む PR では mock 不可領域 (GPU / audio / 長時間動画 / GUI Tauri 起動) をユーザー (Idios) に実機検証依頼する。「mock テスト pass = 全体 OK」は Iron Law 6 違反 / Red Flag。

### trigger 表

| 変更パス / 内容 | 必要な実機検証 | 根拠 / mock 不可理由 |
| --- | --- | --- |
| `allaganeye/video/gpu_detector.py`, `system_info.py` | `pytest -m slow_gpu` (NVIDIA GPU 必須環境) | GPU 初期化 / hwaccel が mock 不可。CI は ubuntu-latest で GPU なし |
| `allaganeye/audio/scan.py`, `audio/matcher.py`, `audio/features.py` | `pytest -m slow tests/test_audio_integration.py` (`ALLAGANEYE_AUDIO_TEST_VIDEO` 必須) | Fanfare 検出は 39GB 録画ファイルが必要 |
| `allaganeye/video/detector.py` Pass 1 / scorebar 関連 | `pytest -m slow_detect` または `pytest -m "slow or baseline_regen"` | 実動画 baseline 検証 |
| `allaganeye/commands/split_matches.py` パイプライン変更 | `pytest -m slow_pipeline` | 全パイプライン統合動作 |
| `gui/src-tauri/**` Tauri command 追加・変更 | `cd gui && npm run tauri dev` での手動 GUI 起動 + 該当 command の UI 操作確認 | ヘッドレスで Tauri 起動はできるが、ユーザーが GUI 操作で確認するのが本来の検証 |
| `gui/src/screens/**` UI 変更 | `npm run tauri dev` + 画面 5 種 (drop / detecting / complete / preview / export) の目視確認 + スクリーンショット添付推奨 | `enforce-acceptance-criteria/SKILL.md` Step 3 と整合 |
| `gui/src-tauri/src/commands/export*.rs` H.264 エンコーダ選択 | 実機 export (NVENC / QSV / AMF / libx264) | GPU encoder fallback は実機 stderr 依存 |
| `.github/workflows/**` 変更 | (任意) act / 該当 job のドライラン | CI 動作の事前検証、必須ではないが推奨 |
| `scripts/**/*.ps1` インストーラ変更 | Windows 上で `Invoke-Pester -Path scripts/tests/` 実行 | Linux runner 上では PowerShell 挙動が一部違う |

### 該当時の AskUserQuestion テンプレ (Iron Law 5「Recommended 付き 2-4 択」標準)

```text
question: "本 PR には GPU 関連変更 (gpu_detector.py, system_info.py) が含まれます。
以下のテストを実機 (Windows + NVIDIA GPU) で実行する必要があります:

  pytest -m slow_gpu tests/test_gpu_detector.py
  pytest -m slow tests/test_system_info.py::test_probe_gpu_vendors_real

どう進めますか?"

options:
  A: "今すぐ実機で実行して結果を貼り付ける [Recommended]"
     description: "PR 提出前に実機テスト pass を確認するのが本来。コマンド出力 (PASS/FAIL + 末尾 30 行) を次の AskUserQuestion 回答で貼ってください"
  B: "実機テスト未実施で PR 作成 (Self-Test Report に plain bullet 明記)"
     description: "ユーザーがレビュー時に実機検証する前提。Self-Test Report の machine-unverifiable 節に '- pytest -m slow_gpu (PR 提出時点では未実施 / レビュー時に実機確認)' と書く"
  C: "PR 作成を中断して実機準備を整える"
     description: "実機環境にアクセスできない / セッション中断が必要"
```

### 結果記録

- **A の場合**: ユーザー (Idios) がコマンド実行 → 結果サマリ (PASS/FAIL + 末尾 30 行) を AskUserQuestion 回答に貼る → Self-Test Report の `### 実機検証 (machine-unverifiable)` 節に plain bullet で「PR 提出時点で実施済 (環境情報 + 結果概要)」と書く
- **B の場合**: Self-Test Report の `### 実機検証 (machine-unverifiable)` 節に plain bullet で「PR 提出時点では未実施 / レビュー時に実機確認」と明記。`Self-Test Report 規約` (本 doc §) により plain bullet は CI ゲートで block されない
- **C の場合**: PR 作成自体を中止 (Iron Law 6 違反を避ける)

### 注意

- Claude セッション側に GPU・録画ファイルへのアクセスが保証されているわけではない。**実機テストの代行実行はしない**。依頼と結果記録のみが Claude の責務
- trigger 表に該当しない場合は実機検証不要。Self-Test Report に「該当なし (gpu_detector.py / audio/ / video/detector.py / gui/ 変更なし)」を 1 行書いて未実施を明示

## Self-Test Report 規約 (validate-checklist CI ゲート)

> originally from `feedback_pr_validate_checklist.md`, absorbed 2026-05-01

PR 本文の checkbox (`- [ ]` / `- [x]`) は `validate-checklist` ジョブが counting している (`unchecked > 0` で fail)。マージ前ゲートで unchecked 項目があるとブロックされる。

### Why

ユーザーが Self-Test Report を消化せずにマージするのを防ぐ品質ゲート。ただし「レビュー時に実機で確認する項目」も `- [ ]` で書くと「Claude が消化していない実機検証項目」までゲートで止まり、PR 提出時に CI fail する。

### 構成

PR 本文を以下の構成で書き分ける (PR #615 / PR #625 修正で確立、PR template `.github/pull_request_template.md` で運用):

- **「## Self-Test Report (本 PR 提出前にローカルで実行済)」セクション** (PR template では `#### Self-Test Report (machine-verified — 全件 [x] で validate-checklist 通過)` h4 として配置): 自分が PR 提出前に実行した自動チェック (lint / typecheck / test / cargo check / build) のみを `- [x] ...` で列挙。全件チェック済が前提
- **「## 実機検証 (machine-unverifiable)」セクション** (PR template では `#### 実機検証 (machine-unverifiable — plain bullet で書く)` h4): `npm run tauri dev` での手動操作、UI 目視確認、レビュー時にユーザーが実施する項目を **plain bullet `-`** (checkbox なし) で列挙

`- [ ]` を残すと PR 提出直後の CI で fail する。`gh pr edit <N> --body-file -` で書き直せば validate-checklist は再実行され直ちに pass する (commit 不要)。

## (A) PR 内修正優先 規約

> originally from `feedback_pr_internal_fix_policy.md`, absorbed 2026-05-01

レビューで摘出した課題は、原則として該当 PR 内で全て対策する。`/review-pr` のトリアージ表で (B) 新規 issue 起票 / (C) 既存 issue 追記 を選びたくなる場面でも、まず (A) 本 PR 内修正を第一候補にする。

### Why

2026-04-27 PR #615 (Tauri bundle 有効化) のレビュー時、ユーザー (Idios) が方針確定。「PR で挙がった問題は原則そのPRですべて対策する」。レビュー側 SKILL のデフォルト判定ロジック (本 PR 受け入れ条件直結でない → (B) 別 issue) では分離する判断になっていたが、ユーザー方針はスコープ拡大による一括対応を優先する。

### How to apply

- `/review-pr` Step 5b トリアージ表で (B) 新規 issue / (C) 既存 issue 追記 を考えた瞬間、まず「本 PR 内で対応できないか」を検討する
- 例外: スコープ逸脱が明らかに大きい (別レイヤー実装変更 / GPU 統合等で工数 1 セッション超 / 別担当領域) 場合のみ (B) を提案。その場合も `AskUserQuestion` で「(A) 本 PR 拡大 / (B) 別 issue」の選択肢を提示し、ユーザーに判断を委ねる
- `AskUserQuestion` で (A) only / (A)+(B) 混合 / 個別調整 の選択肢を提示する場合、(A) only を **「Recommended」** として提示する
- 例外的に (B) になる典型: 別 issue が既に存在し、まだクローズされていない場合 (重複防止) / scope-guard skill が「同 PR で対応すると Iron Law 3 違反」と判定した場合

## PR 規約 (develop ベース / Closes 禁止 / exit_code 衝突 / 1 PR = 1 scope / session-id)

> originally from `feedback_pr_rules.md`, absorbed 2026-05-01

### develop-x.x.x ベース

PR は `develop-x.x.x` ベースで作成する。`main` ベースは不可。

- **Why**: `docs/release-process.md` に「各 PR は develop-x.x.x にマージする」と明記。`main` はリリース時のみ
- **How**: `gh pr create --base develop-0.2.0` で作成。CI トリガーにも `develop-*` を含める

### Closes / Fixes / Resolves キーワード禁止

PR 本文・コミットメッセージに `Closes` / `Fixes` / `Resolves` キーワードを書かない。

- **Why**: `docs/issue-policy.md` §「Issue のライフサイクル管理」 で禁止。クローズはマージ実行者が手動で行う (Iron Law 4)
- **How**: PR 本文では `Refs #N` で参照のみ。コミットメッセージにも `#N` 参照のみ

### exit_code 衝突回避

新しい exit_code を追加する際は既存コードと衝突しないか確認する。

- **Why**: 過去に `ConfigValidationError(exit_code=2)` が `InputFileError(exit_code=2)` と衝突してレビューで差し戻された
- **How**: `allaganeye/exceptions.py` と CLAUDE.md の Exit Codes テーブルを確認し、未使用のコードを割り当てる

### 1 PR = 1 scope

進行中の PR にスコープ外の変更を追加しない。

- **Why**: 過去に 9 件の Issue を 1 PR に詰め込んでレビューで分割を指示された
- **How**: 計画段階で PR 分割を決め、各 PR のスコープを超えるコミットは別 PR にする (`scope-guard` skill 連携)

### コミットメッセージ session-id

コミットメッセージの末尾に `[<session-id>]` を含める。

- **Why**: `docs/release-process.md` のコミットルールに明記
- **How**: 全コミットに `[<session-id>]` を付与 (例: `[admiring-gates-fcda42]`)

## doc 節参照健全性確認 (§「セクション名」grep)

> originally from `feedback_doc_section_ref_check.md`, absorbed 2026-05-01

doc の節構造を変える PR、**または `git merge` で他 skill / doc を取り込む PR** では、参照側 (`.claude/skills/`, `docs/`) から `§「<旧セクション名>」` を grep して残骸ゼロを確認し、加えて新 doc に対応する `##` / `###` 見出しが存在することまで verify する。

### Why

2026-04-26 PR #597 (旧ロール用語 sweep) で `docs/l2-workflow.md` の節構造を再編 (旧 §「ユーザー確認ルール」 + §「強制メカニズム」 → 新 §「ルールと強制メカニズム」 に統合) した際、Self-Test Report (当時の名称: Test plan) に「相互参照は破綻していない」と report した。しかし `.claude/skills/scope-guard/SKILL.md` が旧見出しを参照したまま残っており、レビューで指摘された。検証が「参照箇所が `docs/l2-workflow.md` を mention しているか」のファイル名一致レベルにとどまり、セクション名一致まで遡及していなかったのが原因。

2026-04-27 PR #597 Round 3 では `git merge origin/develop-0.2.0` により取り込んだ `.claude/skills/close-issue/SKILL.md` の pre-existing broken reference を見落とし、Idios から再指摘。受け入れ条件「相互参照は破綻していない」は **merge 後の状態で** を意味するので、「pre-existing だから対象外」は厳密読みで違反になる。

### How to apply

doc の節構造を変える PR、または merge 取り込み PR では以下を実行:

1. `git grep -oE '§「[^」]+」' .claude/ docs/ | sort -u` で全 section reference を抽出
2. 各 reference が target doc の `##` または `###` 見出しと文字列一致するか確認 (`grep -nE "^### ?<セクション名>" docs/<target>.md` 等)
3. 旧セクション名が確実に消えたら `git grep -n "<旧セクション名>"` で残骸ゼロを確認

「相互参照は破綻していない」と PR Self-Test Report に書く前に、上記 3 ステップを実施する。ファイル名 mention の grep だけでは不十分 (l2-workflow.md という mention は残るが、参照している節が統合・廃止されていることを検出できない)。

### merge で取り込んだ「自分が書いていない」skill / doc も対象

`git merge` 経由で取り込んだ pre-existing broken reference も含める。「pre-existing だから対象外」は厳密読みで違反。確認テンプレ:

```bash
# 全 section reference を抽出
git grep -oE '§「[^」]+」' .claude/ docs/ | sort -u

# 抽出結果の各 §「<名前>」が現行 doc に実在するか 1 件ずつ突き合わせる
# (auto-merge で取り込んだ全ファイル含む)
```

### content-level の inner reference も対象 (本 PR で内容を移動した時)

`§「<親セクション>」` までは grep で機械的に追跡できるが、`§「<親>」の「<子>」要件参照` のような **content-level inner reference** (鉤括弧 + section prefix なし) は §「<...>」grep に引っかからない。本 PR で content を別 doc へ移動した場合、移動元 doc の同名ラベルが残骸 reference として stale になることがある (PR #667 Issue C で発覚)。

確認手段:

```bash
# 本 PR で内容が移動した section / 概念のラベル (例: 「PR 作成前」要件) を grep
git grep -nE 'の「PR 作成前」|の「<旧概念>」' .claude/ docs/ .github/ CLAUDE.md
```

該当ラベルが移動元 doc を pointing したまま残っていれば、移動先 doc / 新ラベルへ書き換える。move 完了の commit 前にこの grep を必ず実施する (move された時点で立ち枯れる stale reference を検出)。

## レビュー受け入れ基準 (#367 対策)

PR #343 のような「複数 Issue が不完全修正のままクローズされる」事故を防ぐため、`/review-pr` skill は以下を自動検証する:

### 検証項目 (マージ前必須)

- [ ] **受け入れ条件の全項目が満たされているか**: 元 issue の `## 受け入れ条件` チェックボックスを PR 本文で反映、テストで検証
- [ ] **実装内容が PR 説明と一致しているか**: 変更差分と PR body の乖離検出
- [ ] **テスト存在**: 変更行に対応する test ケースがあるか (contract test + baseline FAIL 検証)
- [ ] **UI/出力変更の実証**: CLI 出力・GUI スクリーンショット等の実サンプルを PR 本文に添付
- [ ] **複数 issue 束ね時の合理性**: 1 PR で複数 issue を閉じる場合、束ねる理由を PR 本文に明記
- [ ] **Phase 分割時の子 issue 起票**: 「Phase 2 は別途」等で残タスクを先送りする場合、子 issue 番号を親 issue に記載
- [ ] **CI 全通過**: `gh pr checks <PR>` で全 green
- [ ] **ruff / ruff format / pytest 全通過**

### Issue クローズルール

- PR マージ = 自動クローズではない (`Closes`, `Fixes` キーワード**禁止**)
- `Refs #N` 形式が正規記法 (PR タイトル + 本文)。`/close-issue` Step 1 は `closedByPullRequestsReferences` 空時に `gh api repos/.../issues/<N>/timeline` (cross-referenced-event) + `gh search prs '"Refs #N"'` の Hybrid fallback で紐づく PR を列挙し、Step 2 ケース B fallback は `gh pr view <PR#> --json body --jq '.body' | grep -oE '#[0-9]+'` で N 件 issue を抽出する (#607)
- `/review-pr` (レビューセッション) では `gh issue close` を実行しない (#594 で責務分離。レビュー専用セッションは「観察・指摘・依頼」に徹する原則と整合)
- マージ後の issue クローズは専用 skill **`/close-issue <issue番号>`** で実施する。本 skill は Iron Law 4 (マージ後実測再検証) を担保する唯一のルート
- `/close-issue` の責務:
  1. 紐づく PR を全件マージ済み確認 (`closedByPullRequestsReferences` または `Refs #N` fallback 経由で取得、1:1 / 束ね PR / Phase 分割 の各ケース判定)
  2. 受け入れ条件をマージ後 base ブランチ (main / develop-x.x.x) で実測再検証 (静的 grep + 短時間単体テスト + `/test-pr` 既実施確認)
  3. issue 本文の未チェック `- [ ]` 全消化確認
  4. 残タスクは (B) 新 issue 起票 / (C) 既存 issue 追記 にトリアージ (握り潰し禁止、Iron Law 1, 3)
  5. ユーザー (Idios) 承認後に `gh issue close <番号> --comment "実測再検証完了 ... [<session-id>]"`
- 運用フロー: `/review-pr` (レビュー & LGTM) → `gh pr merge --squash` → `/close-issue <番号>` (実測再検証 & クローズ)
- **束ね PR** (1 PR で N issue close) は issue 単位で `/close-issue <番号>` を呼び分ける (各 issue の受け入れ条件を独立検証、Iron Law 1)
- **Phase 分割** (N PR で 1 issue close) は最終 PR マージ後に 1 回呼び出す (全 PR 統合状態で受け入れ条件再検証。最終 PR 未マージなら close 不可)
- 残タスクが判明した場合は (B) 新 issue 起票して親 issue に link、または (C) 既存 issue にコメント追記してから本 issue をクローズ
- 詳細手順: `.claude/skills/close-issue/SKILL.md`

## タスク発見

新規タスクは以下の手順で発見する:

1. `gh issue list --state open --assignee Idios --sort updated` で最近更新された issue を確認
2. スコープラベル (`l2a-gui`, `l2b-installer`, `l2-workflow`) でフィルタし、優先度 (`P1-high`) 順に並べる
3. 着手対象が選ばれたら `/plan` を呼んで実装前の計画を固める

ユーザーが「次に何する?」と聞いた場合、Claude は上記を実施し `AskUserQuestion` で候補提示する。

## 計画フェーズの運用

実装着手前の曖昧点洗い出しを標準化する。Claude Code の plan モード (ExitPlanMode ツール) を活用し、以下を必ず出力する:

1. **現状理解**: 対象 issue の本文を要約、依存 issue / 関連 PR の一覧
2. **リスクと曖昧点**: 実装時に発生しうる不確実性 (API 選定、互換性、パフォーマンス、外部依存等) をリスト化
3. **実装ステップ案**: タスクを 2-5 個のサブステップに分解
4. **判断ポイント**: ユーザーに確認すべき方針選択肢を `AskUserQuestion` で提示

ユーザーが方針承認後に実装へ移る。計画段階で未決事項が残る場合は plan mode を維持。

## Issue ラベル運用

`role:*` ラベルは**廃止**。代替として以下を使う:

### prefix ラベル (既存維持)

- `[bug]` — バグ修正
- `[doc]` — ドキュメント
- `[refactor]` — リファクタリング
- `[task]` — 通常タスク (enhancement 含む)
- `[question]` — 方針判断が必要
- `[risk]` — リスク顕在化

### スコープラベル (新設)

- `l2a-gui` — GUI 関連 (#105 系)
- `l2b-installer` — インストーラ関連 (#106 系)
- `l2-workflow` — 開発プロセス改善 + allaganeye-guard 運用連携 doc 整備 (#458 / #459)
- `l2-decision` — 方針決定 issue
- `l1-residual` — L1 残課題 (#412-#440 系)

> `l2c-guard` ラベルは 2026-04-21 廃止 (guard との program integration 構想を破棄したため)。関連 doc 整備は `l2-workflow` で追跡。

### 優先度ラベル (既存維持)

- `P1-high` — 後続の前提条件
- `P2-medium` — 通常
- `P3-low` — 見直し時に再検討

## Memory 階層化

3 層構造で知見を管理する:

| 層 | 場所 | 寿命 | 内容 |
| --- | --- | --- | --- |
| L1 | `CLAUDE.md`, `MEMORY.md` | 恒久 | プロジェクト規約、skill 索引、ワークフロー要約 |
| L2 | `~/.claude/projects/<project>/memory/feedback_*.md` | 中期 | ユーザー指摘の蓄積、判断基準のチューニング |
| L3 | `docs/knowledge/*.md` | 恒久 (プロジェクト共有) | セッション横断の調査結果、トラブルシュート |

**L2 → L3 昇格**: feedback が複数セッションで再利用される汎用知見に育ったら `docs/knowledge/` へ移動し、memory からは削除。

## schema 編集ワークフロー (#612)

`metadata.json` のスキーマは [`schemas/metadata.schema.json`](../schemas/metadata.schema.json) (draft-2020-12) を機械可読の正、[`docs/metadata-spec.md`](metadata-spec.md) を人間可読の正とする二層 SSoT 構造。フィールドを追加・変更する際は以下の手順で進める。

### 編集手順

1. **JSON Schema を編集**: `schemas/metadata.schema.json` の `properties` / `required` / `$defs` を更新
2. **doc 同期**: 必要なら `docs/metadata-spec.md` のテーブル / 説明を更新
3. **再生成**: `python scripts/codegen/generate.py` で `allaganeye/metadata_types.py` (TypedDict) と `gui/src/types/metadata.generated.ts` (interface) を一括再生成
4. **zod 同期**: [`gui/src/types/metadata.schema.ts`](../gui/src/types/metadata.schema.ts) の field set / required / nullable を JSON Schema と完全一致させる (refine 制約は zod 側のみで残す)
5. **payload builder 修正**: [`allaganeye/commands/split_matches.py`](../allaganeye/commands/split_matches.py) の `_build_metadata_payload` を新しい必須フィールドに合わせて更新 (pyright が型レベルで検出する)
6. **生成物 commit**: `metadata_types.py` / `metadata.generated.ts` を必ず commit する。CI が `git diff --exit-code` で差分があれば fail する

### CI ガード

`.github/workflows/ci.yml`:

- `python` ジョブ: `python scripts/codegen/generate.py --py` 実行 → `git diff --exit-code allaganeye/metadata_types.py`
- `gui-frontend` ジョブ: `node gui/scripts/generate-ts.mjs` 実行 → `git diff --exit-code gui/src/types/metadata.generated.ts`

差分が検出された場合は「JSON Schema を編集したら `python scripts/codegen/generate.py` を再実行して commit してください」のメッセージで build fail する。

### refine 制約の扱い

`end_time >= start_time` 等のセマンティック制約は JSON Schema では表現せず、zod (GUI) と CLI 側 InputFileError で個別に enforce する。reader 側の前方互換 (legacy `note` / 未知フィールドの passthrough) も同様で、JSON Schema は strict、zod が `.passthrough()` で緩く受ける二層構造になっている。

### 関連ファイル

- [`schemas/metadata.schema.json`](../schemas/metadata.schema.json) — 機械可読の正
- [`scripts/codegen/generate.py`](../scripts/codegen/generate.py) — orchestrator
- [`scripts/codegen/README.md`](../scripts/codegen/README.md) — 詳細手順とトラブルシューティング
- [`gui/scripts/generate-ts.mjs`](../gui/scripts/generate-ts.mjs) — Node generator (TS)

## ルールと強制メカニズム

本プロジェクトの基本ルールは **Iron Law** としてセッション開始時に全て注入される (`.claude/hooks/session-start.sh`)。詳細な条文はそのファイルを正とし、本ドキュメントでは重複記載しない。

### 強制メカニズム

[obra/superpowers](https://github.com/obra/superpowers) の「Iron Law / Red Flags / Gate Function」パターンに倣い、ルールを書くだけでなく**エージェントが自己抑制せざるを得ない語彙と構造**を配置する。

| 層 | 実装 | 役割 |
| --- | --- | --- |
| 1 | `SessionStart` hook (`.claude/hooks/session-start.sh`) | セッション開始・`/clear`・compact 時に Iron Law + Red Flags を `<EXTREMELY_IMPORTANT>` で会話先頭に注入 |
| 2 | `enforce-acceptance-criteria` skill | `/review-pr` から呼ばれる Gate Function。受け入れ条件の逐条検証 |
| 3 | `scope-guard` skill | スコープ逸脱検知で AskUserQuestion を強制 |
| 4 | `/review-pr` skill | PR レビューのオーケストレーション。上記 2 を必ず呼び出す |
| 5 | `PreToolUse` hook (`.claude/hooks/preuse.py`, #401 由来) | Bash 実行時の確認ゲート |
| 6 | PR テンプレート (`.github/pull_request_template.md`) | Iron Law 1/3/4 の逐条チェックリスト |
| 7 | ユーザー最終承認 | マージは全て Idios が実行、未達 PR は差し戻し |

**ハードゲートの実装**: `.claude/hooks/preuse.py` が `PreToolUse` で `gh` bulk 操作・PR マージ等をインターセプトし、#559 以降は `permissionDecision=ask` を返して Claude Code の permission prompt を出す (旧: #401 の exit 2 block + bypass prefix 運用)。GitHub Action でのマージブロックは将来候補。

#### PreToolUse hook の gate 運用 (#485 / #513 / #559)

`preuse.py` は gate 発動時に **exit 0 + stdout JSON (`permissionDecision: "ask"`)** を出力し、Claude Code 本体の permission prompt でユーザーが allow / deny を選ぶ (#559)。allow なら同一 tool invocation でそのまま実行、deny ならキャンセルされる。旧来の `ALLAGANEYE_PREUSE_BYPASS=1 <command>` prefix は **非対話環境向けの escape hatch** として維持 (自動化スクリプト等で permission prompt が出せない場合 / 旧 exit 2 方式の hook と互換したい場合)。

運用手順 (主フロー, #559 以降):

1. Claude が `gh` コマンドを発行 → hook が bulk 閾値 (3 件 / 60s) または always gate (PR マージ等) を判定
2. gate 発動時、hook は `{"hookSpecificOutput": {"permissionDecision": "ask", "permissionDecisionReason": ...}}` を stdout に出力して exit 0
3. Claude Code 本体が permission prompt を表示 (reason にコマンド先頭数百文字と Iron Law 解説が含まれる)
4. ユーザーが allow すればそのまま実行、deny すればツール呼び出しがキャンセルされる

escape hatch (非対話環境等):

```bash
ALLAGANEYE_PREUSE_BYPASS=1 gh issue close 123
```

prefix は strip されて `gh issue close 123` が実行される。`[preuse:bypass]` 監査ログが stderr に出力される。

重要ポイント:

- **主フローは Claude Code の permission prompt**。Claude が `AskUserQuestion` で別途確認する必要はない (permission prompt 自体が確認動作を兼ねる)
- bypass prefix は escape hatch のみ。非対話環境では 1 コマンドごとに個別付与する (1 回分のみ bypass の仕様)
- **ask / bypass されたコマンドは state に記録されない** (#513 挙動を #559 以降も維持)。permission prompt で deny された場合や prefix 付き実行 (`[preuse:bypass]`) では counter が累積膨張せず、以降の bulk 判定に影響を与えない
- `ALLAGANEYE_PREUSE_BYPASS=0` 等は認識されない (prefix 正規表現は `=1` 固定)
- `.claude/settings.local.json` で `"pretooluse_gate": false` を設定すると gate 全体を無効化できる (緊急避難用、通常は true = デフォルト)

## タスクフロー

**単一セッションが順次タスクを実行**するため、フェーズ間のハンドオフは不要:

```text
Plan モードで計画合意 → 実装 (TodoWrite で進捗管理) → PR 作成 → /review-pr → (修正あれば再実装) → テスト実行 → ユーザー承認 → ユーザーがマージ
```

各フェーズの完了時点で次フェーズに渡すコンテキストを明示する (PR 番号、テスト結果等)。

修正が必要な場合の扱いは起動コンテキストで分ける:

- **PR 作成と同一セッションで `/review-pr` を呼んだ場合**: 同セッション内で PR ブランチに追加コミットを積み、再度 `/review-pr` を呼び出す。
- **レビュー専用セッション (セッション先頭で `/review-pr` のみ実行) の場合**: PR ブランチへの **書き込み系操作 (`Edit` / `commit` / `push`) は一切行わず**、PR コメントで PR 作成セッションに具体的な修正指示を依頼する (`git checkout` 自体は read 目的なら可。詳細は `.claude/skills/review-pr/SKILL.md` 冒頭「重要」節参照)。PR 作成セッションが修正 commit & push した後、別セッション or 同レビューセッションで `/review-pr` を再実行して受け入れ条件を再確認する。詳細は `.claude/skills/review-pr/SKILL.md` §「修正依頼コメント投稿」を参照。

## worktree メンテナンス (#477)

Claude Code のセッション用 worktree はセッション終了時に `git worktree remove` されるが、`.claude/worktrees/<name>/` 自体のディレクトリが空のまま残ることがある (#477 で観測)。残骸は **Stop hook で自動 sweep** される。手動での sweep も可能。

### 自動実行 (Stop hook)

セッション終了時に `.claude/hooks/stop.sh` が **2 つの cleanup script を順次起動**する:

1. `scripts/cleanup-worktrees.sh --apply` — 空ディレクトリを `rmdir` で除去 (非空 dir は touch しない)
2. `scripts/cleanup-claude-branches.sh --apply` — 安全 AND 条件を満たす `claude/*` ローカルブランチを `git branch -D` (#708)

両 script とも明示的に安全な条件下のみ操作するため、未保存ファイルや作業中ブランチが誤って消失することはない。

設定箇所: `.claude/settings.json` の `hooks.Stop` セクション。

### branch cleanup の安全条件 (AND)

`scripts/cleanup-claude-branches.sh --apply` が `git branch -D` で削除する条件 (#708):

- **AND 1 (merged)**: `origin/develop-0.2.0` または `origin/main` の祖先 (`git merge-base --is-ancestor`)
- **AND 2 (active 参照なし)**: `git worktree list --porcelain` の `branch refs/heads/...` 集合に含まれない
- **AND 3 (24h cooldown)**: 最終 commit (`git log -1 --format=%ct`) が 24h 以上前
- **prefix 限定**: `claude/` のみ (= `feature/xxx` 等の手動 branch は対象外)

**評価順序**: AND 2 → AND 1 → AND 3 (cost-efficient: AND 2 は local hash lookup で安価、AND 1 / AND 3 は git subprocess を spawn するため後回し)。最初に fail した条件が `kept <branch> (reason: not-merged | active | cooldown)` の reason として記録される。

`origin/develop-0.2.0` / `origin/main` が未 fetch だと `merge-base --is-ancestor` が false に倒れて keep される = 安全側。`git fetch` は hook 内で実行せず、user の通常運用 (`git pull`) を前提とする。

### 手動実行

区切りで一斉掃除したい場合や、hook を介さず状態を確認したい場合:

```bash
# 削除候補を表示するだけ (dry-run, デフォルト)
scripts/cleanup-worktrees.sh
scripts/cleanup-claude-branches.sh

# 実際に rmdir / branch -D を実行 (安全条件を満たすもののみ)
scripts/cleanup-worktrees.sh --apply
scripts/cleanup-claude-branches.sh --apply
```

### 動作

1. `git worktree prune` で git 側メタデータをクリーンアップ (stale worktree の記録を消す)
2. `.claude/worktrees/` 直下のサブディレクトリを走査
3. `.git` 参照を持たない (= 現在アクティブではない) 空ディレクトリを `rmdir` で削除

### 自セッションの残骸が sweep されるタイミング (2 段階設計)

Stop hook は**自セッションのディレクトリを sweep しない**。これは 2 つの理由による:

1. **`.git` 参照で skip される**: 自セッションのワーキングツリーには `.git` ファイル (linked worktree の gitdir 参照) が存在するため、`cleanup-worktrees.sh` はアクティブ worktree とみなし skip する。
2. **Windows のディレクトリハンドル保持問題** (#477 コメント): Windows では Claude Code ランタイムが自セッションの initial cwd のハンドルを握り続けるため、Stop hook 実行中に自セッション自身のディレクトリを削除しようとしても OS レベルで失敗する可能性が高い。

このため、自セッションの残骸 (セッション終了後にディレクトリだけが残るパターン) は、**次回以降のセッション終了時の Stop hook** が空ディレクトリとして rmdir する 2 段階設計になっている:

- t0: セッション A 終了 → A の Stop hook は A 自身を skip (`.git` 参照ありまたはハンドル保持中)
- t1: `git worktree remove` 完了後、A のディレクトリは空のまま残る (= 残骸化)
- t2: 次にセッション B が起動・終了 → B の Stop hook が A のディレクトリを「`.git` 無し + 空」と判定して rmdir

つまり **残骸は最長で 1 セッションぶん残存しうる**が、次セッション終了時点で解消される。単独セッションでの E2E 検証はできないため、動作確認は `scripts/cleanup-worktrees.sh --apply` の手動実行および dry-run 出力で行う (#477 対応 PR #493 で 4 件の候補が正しく skip されることを確認済み)。

### 安全性

`rmdir` のみを使用するため、アクティブな worktree や何らかのファイルが残っているディレクトリは**削除されない**。想定外のファイルが残っているディレクトリは出力で明示されるため、必要に応じて手動で確認する。Stop hook が起動中のセッションのアクティブ worktree は `.git` 参照で保護されるため安全に skip される。Windows のディレクトリハンドル保持問題 (#477 コメント) は上記 2 段階設計により回避している。

`cleanup-claude-branches.sh` も同様に明示的に安全な AND 3 条件 (merged + active 参照なし + 24h cooldown) + `claude/` prefix 限定下でのみ `git branch -D` を実行し、merged 保証により data loss しない。`origin/develop-0.2.0` / `origin/main` が未 fetch なら `is-ancestor` false に倒れて keep する設計のため、fetch されていない開発環境でも安全に動作する。

## 参考

- [code.claude.com/docs/en/skills](https://code.claude.com/docs/en/skills) — skill 設計ガイド
- [code.claude.com/docs/en/best-practices](https://code.claude.com/docs/en/best-practices) — 単一セッション推奨
- `docs/release-process.md` — ブランチ戦略と手動リリース手順
- `docs/issue-policy.md` — Issue 起票ルール (role:* 節を削除済み)
- `plans/deffere-issue-l2-deffered-1-l1-issue-2-graceful-clover.md` — L2 移行計画全体
