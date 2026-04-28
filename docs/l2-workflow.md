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
|---|---|---|
| 計画立案 | Plan モード + AskUserQuestion + TodoWrite | タスクの分解、リスク・曖昧点の事前洗い出し、実装前の計画合意 |
| 実装 | Claude の通常ツール (Edit/Write/Bash) + TodoWrite | 実装 + unit/integration テスト + 実機検証 (long-running / GPU / audio 統合は mock 不可) + PR 作成。スコープ逸脱時は Plan モードに戻る |
| PR レビュー | `/review-pr` | PR レビュー + #367 受け入れ基準チェックリスト検証 + マージ判断 |
| issue 起票 | `/create-task` | issue 起票 (定型テンプレート適用) |
| issue クローズ | `/close-issue` | マージ後の受け入れ条件実測再検証 + 残タスクトリアージ + `gh issue close` 実行 (Iron Law 4 担保ルート、#594 で `/review-pr` から責務分離、#607 で `Refs #N` fallback 対応 / #606 で eval/reports 構造整理) |
| リリース | `/release` | リリースタグ、CHANGELOG、main へのマージ |

権限境界 (close 操作、コード変更操作等) は**人間 = ユーザーが判断**する責任とする。Claude は曖昧点を `AskUserQuestion` でユーザーに確認する。

反復利用される手順があれば、実運用でパターンが固まった時点で新規 skill を追加する (事前に空の skill は作らない)。

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
|---|---|---|---|
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
|---|---|---|
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
- **レビュー専用セッション (セッション先頭で `/review-pr` のみ実行) の場合**: PR ブランチへの `git checkout` / `Edit` / `commit` / `push` は一切行わず、PR コメントで PR 作成セッションに具体的な修正指示を依頼する。PR 作成セッションが修正 commit & push した後、別セッション or 同レビューセッションで `/review-pr` を再実行して受け入れ条件を再確認する。詳細は `.claude/skills/review-pr/SKILL.md` §「修正依頼コメント投稿」を参照。

## worktree メンテナンス (#477)

Claude Code のセッション用 worktree はセッション終了時に `git worktree remove` されるが、`.claude/worktrees/<name>/` 自体のディレクトリが空のまま残ることがある (#477 で観測)。残骸は **Stop hook で自動 sweep** される。手動での sweep も可能。

### 自動実行 (Stop hook)

セッション終了時に `.claude/hooks/stop.sh` が `scripts/cleanup-worktrees.sh --apply` を起動し、空ディレクトリを rmdir で除去する。`rmdir` のみを使うため未保存ファイルを含むディレクトリは絶対に削除されず、セッション中の作業が消失することはない。

設定箇所: `.claude/settings.json` の `hooks.Stop` セクション。

### 手動実行

区切りで一斉掃除したい場合や、hook を介さず状態を確認したい場合:

```bash
# 削除候補を表示するだけ (dry-run, デフォルト)
scripts/cleanup-worktrees.sh

# 実際に rmdir を実行 (非空ディレクトリは触らない)
scripts/cleanup-worktrees.sh --apply
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

## 参考

- [code.claude.com/docs/en/skills](https://code.claude.com/docs/en/skills) — skill 設計ガイド
- [code.claude.com/docs/en/best-practices](https://code.claude.com/docs/en/best-practices) — 単一セッション推奨
- `docs/release-process.md` — ブランチ戦略と手動リリース手順
- `docs/issue-policy.md` — Issue 起票ルール (role:* 節を削除済み)
- `plans/deffere-issue-l2-deffered-1-l1-issue-2-graceful-clover.md` — L2 移行計画全体
