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
| `self` | **継続中**。prompt は context loss 時の保険文書 | 何もしない (origin が走る)。context loss を検知した場合のみ手動 dispatch | (通常は受け取らない)。受け取った場合 = origin が context loss した想定 → `gh pr list --search "<元 issue#>" --state all` で origin 痕跡確認 → `AskUserQuestion` で「(A) origin 痕跡なしで仕切り直し / (B) 当 prompt は誤 dispatch、abort [Recommended]」を提示 (Iron Law 5「Recommended 付き 2-4 択標準」整合) |
| `dispatch` | **abort 済み** | 新規 session に dispatch | origin が abort 済 = fresh start。Iron Law 6 Pre-flight 通常実施 |

### 生成側 (origin session) のルール

1. prompt 生成 **時点で** どちらの mode かを明示的に決定
2. dispatch mode で生成した直後、origin session は当該 PR 作成 / 実装作業を **stop** する (= abort confirmation)
3. self mode 生成は user 透過の contingency 文書として扱い、origin は実行を継続
4. 1 session が同一 issue について self と dispatch の **両方** の prompt を user に提示することはしない (PR #721 race condition の原因)

### 受信側 (dispatch された fresh session) のルール

1. 受け取った prompt の 1 行目を上記正規表現で parse
2. parse fail → `AskUserQuestion` で「(A) legacy prompt として扱う (handoff 規約適用前と仮定して着手) / (B) prompt 不正のため当 session を abort、user に prompt 再生成を依頼 [Recommended]」 (Iron Law 5「Recommended 付き 2-4 択標準」整合)
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

PR 作成前に base 最新化と並行 worktree PR 重複を必ず確認する。`feedback_pr_review_base_merge_regression.md` (PR #627 Round 4 で発覚した base 取り込み機能 regression) と `feedback_concurrent_worktree_pr_check.md` (#646 / PR #647 並行作業重複) の skill / 規約昇格として運用化 (2026-04-29 #659)。2026-05-13 #722 で Step 0 ハードゲートを追加 (build/verify 前に `gh pr list --search "<元issue#>" --state open` を <1s で実行、PR #721 で発生した 49s redundant work 再発を防止)。2026-05-17 L-β β-4 で Step 5 (Codex adversarial-review、agent 実行は tier 1 = companion script) を追加 (C2)。Step 0 と Step 4 は検出 window が異なるため両方とも実施する。

> **checkbox 表記 convention**: Self-Test Report (machine-verified) は `- [x]` (CI ゲート対象)、実機検証 (machine-unverifiable) は plain bullet `-` (CI ゲート対象外) で書き分ける。詳細は本 doc §「Self-Test Report 規約」 を参照。

### 6 ステップ手順 (Step 0-5)

```bash
# 0. ★ ハードゲート (#722 で追加): <1s で実行、build/verify の前に置く
gh pr list --search "<元issue#>" --state open \
  --json number,headRefName,state,createdAt
# hit ≥ 1 件 → 即時 abort、AskUserQuestion で
#   (A) 当該 PR を review/iterate に切替 [Recommended]
#   (B) 別 worktree のため当 session abort
#   (C) ユーザー判断 (詳細確認)
# hit 0 件 → Step 1 へ

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

# 4. 並行 worktree 同 issue PR 重複確認 (Step 0 と検出 window が異なるため再実行必須)
gh pr list --search "<元issue#>" --state all \
  --json number,headRefName,state,createdAt

# 5. Codex adversarial-review (Codex 統合、C2、L-β β-4 で追加)
# Step 0-4 通過後、PR 作成直前に Codex GPT-5.4 で adversarial pass。
# invocation path は 3-tier (#795、下記 §Step 5 の invocation path 参照)。
# default (tier 1) は companion script 直接呼び出し:
#   # <version> は placeholder。実行直前に ls で実パスを解決してから代入する (#856)
#   ls "$HOME/.claude/plugins/cache/openai-codex/codex/"
#   # 代入は必ず「独立した文」で行う。`VAR=... node "$VAR/..."` の 1 行結合形は
#   # $VAR が代入前に展開されて空になり、MSYS が裸の /scripts/... を
#   # C:\Program Files\Git\scripts\... へ書き換えて MODULE_NOT_FOUND になる (実測)
#   export CLAUDE_PLUGIN_ROOT="$HOME/.claude/plugins/cache/openai-codex/codex/<解決した version>"
#   node "$CLAUDE_PLUGIN_ROOT/scripts/codex-companion.mjs" adversarial-review \
#     [--wait|--background] --base <base> "<focus 文字列 (ASCII)>"
#   # 注意: `... | tee log` で受けると tee の exit code が返るため Codex の失敗を
#   #       見逃す。rc は ${PIPESTATUS[0]} で確認する (本 PR で実際に見逃した)
# focus 文字列は固定の例示から選ぶのではなく本 PR の diff から導出する。
# 手順は下記 §「Step 5 の focus 導出手順」 に従う (省略不可)。
# 出力の finding は Claude が triage し (A) PR 内修正 / (B)(C) handoff のいずれかへ振り分け。
# Codex 自身に commit させない (M3 整合)。Codex CLI が fail した場合は
# `docs/l2-workflow.md` §Codex fallback (L-β β-5 で追加) に従う (tier 2)。
```

#### Step 5 の focus 導出手順 (Refs #935 P2-1)

focus は**固定の例示リストから選ぶのではなく、本 PR の diff から導出する**。過去の失敗例を並べた固定リストは「その数種類だけを見る」検出器になり、新しい欠陥クラスに対しては検出力を持たない。PR #930 の要因分析がこの点を実証している — 「security」「入力境界」という抽象語の観点は既に skill に存在したうえで、`/iterate-review` 6 ラウンド (30 findings) を含む 5 層のレビューが不可逆データ損失を 1 件も検出できなかった。**検出力は具体列挙にのみ宿る。**

**focus に必ず含める 1 項目**: 本 PR が新設・変更した**外部入力境界**と、そこから到達する**不可逆操作**の対応ペア。

以下のコマンドは **`CODE` に code path だけを入れて実行する** (doc を含めると、本節が grep パターン自身を含むため self-hit する):

```bash
CODE="allaganeye/** gui/src/** gui/src-tauri/** scripts/** .github/scripts/**"
```

1. **外部入力境界を列挙する** (CLI option / metadata field / GUI 自由入力 / 環境変数):

   ```bash
   git diff origin/<base>...HEAD -U0 -- $CODE \
     | grep -nE '^\+.*(typer\.Option|Annotated\[|os\.environ|std::env::|process\.env|invoke\()'
   git diff --name-only origin/<base>...HEAD \
     | grep -E 'schemas/.*\.json|metadata_types\.py|gui/src/screens/.*\.tsx'
   ```

2. **各境界から到達する不可逆操作を列挙する** (上書き / 削除 / truncate)。**2a と 2b の両方を実行する**:

   ```bash
   # 2a. 直接の不可逆書込 (Python / Rust の write API)
   git diff origin/<base>...HEAD -U0 -- $CODE \
     | grep -nE '^\+.*(open\([^)]*["'"'"']w|write_text|write_bytes|unlink|rmtree|os\.remove|truncate|os\.replace|Remove-Item|fs::remove|fs::write)'

   # 2b. subprocess 経由の書込 (出力先パスの決定 + プロセス起動)
   git diff origin/<base>...HEAD -U0 -- $CODE \
     | grep -nE '^\+.*(subprocess\.(run|Popen)|Command::new|output_path|output_dir|out_path|_output_path|-y\b)'
   ```

   > **2b を省略すると本規約は機能しない (実測)**: 本 codebase の不可逆書込の**大半は ffmpeg subprocess が行う**ため、Python/Rust の write API を見る 2a だけでは捕まらない。#930 の diff に対する実測値は **2a = 0 hit (production code。hit するのはコメント 2 行のみ) / 2b = 30 hit**。つまり 2a だけでは、本規約が防ごうとしている当の欠陥 (`--name-pattern` が決めた出力先へ ffmpeg が書く) を**検出できない**。

3. **(1) × (2) の到達ペアを ASCII 1 文ずつで focus に書く。** 「どの入力の値が、どの書込先の決定に使われるか」の形にする (例: `--name-pattern value decides the export output path; verify it cannot escape -o`)。
4. **ペアがゼロなら、ゼロであることを focus に明記する** (`no new external input boundary reaches an irreversible write in this diff`)。無言の省略は「導出してゼロだった」と「導出しなかった」を事後に区別できなくする (§「規約・ガード導入の 3 点セット」②)。

> **なぜ例示リストを残さないか**: 固定 3 項目 (Iron Law 3 / encoding / GPU fallback) を残したまま 4 つ目として本手順を足すと、実行者は列挙が容易な固定項目だけを埋めて終わり、「過去の失敗リストへの最適化」がそのまま残る。#935 P2-1 が要求するのは**置換**であって追加ではない。本手順で導出した結果として encoding / GPU fallback が挙がるのは正しい (導出の産物であり、事前の固定リストではない)。

同じトリガー語 (「本 PR が**新設・変更した**外部入力境界と、**そこから**到達する不可逆操作」) で `CLAUDE.md` §「destructive write boundary audit checklist」 が発火する。Step 5 の focus 導出と CLAUDE.md の audit 4 問は**対**であり、片方だけを実施したら他方も実施する。

#### Step 5 の invocation path (3-tier、#795)

openai-codex plugin の `commands/adversarial-review.md` frontmatter には **`disable-model-invocation: true`** が明示されており、agent (Claude) が slash command `/codex:adversarial-review` を autonomous に invoke することは plugin spec レベルで禁止されている (出典: `~/.claude/plugins/cache/openai-codex/codex/<version>/commands/adversarial-review.md`、公式仕様は <https://code.claude.com/docs/en/agent-sdk/slash-commands> / <https://code.claude.com/docs/en/agent-sdk/plugins>、PR #792 で発覚)。この制約は **slash command の model-invocation のみ**を縛るため、Step 5 は以下の 3-tier で運用する:

| tier | path | trigger | 実行者 |
| --- | --- | --- | --- |
| 1 (default) | **companion script 直接呼び出し**: `node "$CLAUDE_PLUGIN_ROOT/scripts/codex-companion.mjs" adversarial-review [--wait\|--background] --base <base> "<focus>"` を Bash 経由で実行。本物の Codex GPT-5.4 review が agent 一気通貫で回る (PR #823 / #850 / #851 / #852 実績。focus は ASCII 推奨、`--background` + `run_in_background` で長時間 review を非同期化可) | 常時 (Pre-flight Step 5 必須実行) | agent |
| 2 (fallback) | superpowers `requesting-code-review` subagent。**Codex CLI が rate-limit / quota / network / auth 等で fail した場合のみ** (検出条件・重要 PR 判定・「Codex fallback notice」必須記載は §Codex fallback (C6) に従う) | tier 1 の Codex CLI fail | agent |
| 3 (escalation) | Idios 自身が `/codex:adversarial-review` を直接 invoke し、結果を agent に share して PR 本文に追記 | Idios が tier 1/2 の review 内容・結果に不足ありと判断した場合 | Idios |

tier 1 が成功している限り「Codex review 実施済」の記載は正当 (Iron Law 5 整合)。tier 2 で代替した場合は Codex fallback notice を必ず記載し、Codex review 済と誤認させない。

> **歴史記録の扱い (#854 R2 確定)**: 実行済み dated plans/specs (`docs/superpowers/plans/` / `docs/superpowers/specs/`) 内の slash 表記 (`/codex:review` 等) は当時の実行記録 (historical record) であり、本 3-tier への遡及書き換えは行わない。sweep で検出しても対応不要 (living doc = CLAUDE.md / 本 doc / skill / hook / 現行 roadmap (現時点は `docs/superpowers/specs/2026-06-29-v030-l3-roadmap.md`。roadmap 交代時は本注記も更新する) のみが整合対象)。

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
| 「Step 0 で 0 件だったから Step 4 skip」 | Step 0 と Step 4 は検出 window が異なる。両 step 間に別 worktree が PR 提出する race window あり (PR #721 事例)。両 step とも必須 |

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

### 実施中に観測した想定外の挙動 (Refs #935 P2-3)

**手動ゲート実施中に観測した想定外の挙動は、そのゲートの pass / fail 判定と独立に必ず記録する。説明がつくまで当該ゲートを `pass` と記録しない。**

- **記録先**: Self-Test Report の `### 実機検証 (machine-unverifiable)` 節。plain bullet で `- 観測: <挙動> / 説明: <ついた説明 または 未説明>` の形で書く
- **「主目的は達成した」は pass の根拠にならない。** 観測された異常は主目的の成否とは**別の軸**である。両方を書く
- 異常を別 issue へ切り離す判断自体は可 (Iron Law 3)。ただし**切り離した事実と切り離し先を同じ 1 行に残す**。記録のない切り離しは握り潰しと事後に区別できない
- 未説明のまま PR を出す場合、当該ゲートは `pass` ではなく **`観測あり・未説明`** と記録する
- **観測ゼロだったなら「観測ゼロ」と 1 行書く** (§「規約・ガード導入の 3 点セット」②)。無記載は「異常がなかった」と「記録しなかった」を区別できない

**レビュー側の発火点**: [`/review-pr`](../.claude/skills/review-pr/SKILL.md) Step 5a の long-running / integration 検証観点が、実機検証の記録に `観測:` 行または「観測ゼロ」の記載があるかを確認する。未記載なら Step 5b トリアージ表へ計上する。

> **なぜこの規約が要るか (PR #930 の経緯)**: 手動ゲート M1 (export 実機確認) で「出力パスの表示がおかしい」という異常は**実際に観測されていた**。しかし「export 自体は正常 (3/3 が NVENC で完走)」を根拠にゲートは pass と記録され、パス表示の件は別件として切り離された。後にパス処理を全経路 audit したところ、その表示異常と同じ根 (入力パスの解決規則) からデータ損失を含む blocker が 3 件見つかった。**異常は観測されていた — 記録されなかっただけである。** なお本件は v0.3.0 タグ打ち**前**に `release/v0.3.0` へ merge されており、公開リリースには載っていない。「観測されたが pass と記録された」という事実こそが本規約の根拠である。

### 注意

- Claude セッション側に GPU・録画ファイルへのアクセスが保証されているわけではない。**実機テストの代行実行はしない**。依頼と結果記録のみが Claude の責務
- trigger 表に該当しない場合は実機検証不要。Self-Test Report に「該当なし (gpu_detector.py / audio/ / video/detector.py / gui/ 変更なし)」を 1 行書いて未実施を明示

## Self-Test Report 規約 (validate-checklist CI ゲート)

> originally from `feedback_pr_validate_checklist.md`, absorbed 2026-05-01

PR 本文の checkbox のうち **`受け入れ条件` / `Acceptance criteria` / `Self-Test Report` 節の中にあるもの**を `validate-checklist` ジョブが counting し、`unchecked > 0` で job を fail させる (#936 / #967 で実測)。

**それ以外の節の checkbox は counting されない。** 実物テンプレートでは 22 box のうち gate 対象は 12 box (受け入れ条件 2 + Self-Test Report 10) で、Iron Law 1 群 2 / Iron Law 3 群 2 / Iron Law 4 群 1 / 関連ドキュメント群 5 = 計 10 box は未消化でも job は通る (「該当なしなら `[x]` + 理由付記」と書かれている項目も CI では強制されない)。

**job が red でもマージは構造的にブロックされない。** repo に required status check が設定されていないため (`main` は branch protection ありだが `required_status_checks` は未設定、`develop-*` は無保護、ruleset なし)、`validate-checklist` の red は「気づくための信号」であってマージ阻止機構ではない。required status check 化の判断は #947 で扱う。

### Why

ユーザーが Self-Test Report を消化せずにマージするのを防ぐ品質ゲート。ただし「レビュー時に実機で確認する項目」も `- [ ]` で書くと「Claude が消化していない実機検証項目」までゲートで止まり、PR 提出時に CI fail する。

### 構成

PR 本文を以下の構成で書き分ける (PR #615 / PR #625 修正で確立、PR template `.github/pull_request_template.md` で運用):

- **「## Self-Test Report (本 PR 提出前にローカルで実行済)」セクション** (PR template では `#### Self-Test Report (machine-verified — 全件 [x] で validate-checklist 通過)` h4 として配置): 自分が PR 提出前に実行した自動チェック (lint / typecheck / test / cargo check / build) のみを `- [x] ...` で列挙。全件チェック済が前提
- **「## 実機検証 (machine-unverifiable)」セクション** (PR template では `#### 実機検証 (machine-unverifiable — plain bullet で書く)` h4): `npm run tauri dev` での手動操作、UI 目視確認、レビュー時にユーザーが実施する項目を **plain bullet `-`** (checkbox なし) で列挙

`- [ ]` を残すと PR 提出直後の CI で fail する。`gh pr edit <N> --body-file -` で書き直せば validate-checklist は再実行され直ちに pass する (commit 不要)。

### この gate が見ていない集合 (#967 で実測、checker は Markdown parser ではなく近似)

checker (`.github/scripts/check-pr-checklist.js`) は GitHub のレンダリングに寄せた 1 パスの行スキャナだが、完全一致ではない。誤りの向きは **false-red 側に倒す** 方針 (黙って通す false-green より、メッセージが見えて自己修正できる false-red のほうが安全)。以下は gate が見ていない / 近似している集合:

- **節と項目の存在自体は強制しない**。`Self-Test Report` 節を書かなければ (削除 / 改名 / 項目を plain bullet に落とす) job は通る。証跡ゼロでも green になるため、これは**自己申告 gate**である
- `**Self-Test Report**` のような bold 疑似見出しや、`####` の直後を全角空白で区切った見出しは GitHub 側でも heading にならないため節として成立しない = 上記と同じ扱いになる
- インデント 4 以上の行の解釈は「**開いている list の最も浅いインデント**」で近似している (list 継続なら task item / list が無ければ indented code block)。list item の content indent を超える深い入れ子 (6-8 space 等) は GitHub が code とするのに数える (false-red)
- 未閉鎖の fence / 行頭 `<!--` は「**開いた container の終端まで**」読み飛ばす。root で開いた場合は文書末まで (GitHub と一致)、list / blockquote 内で開いた場合はその container の終端で閉じる
- HTML block は **type 1** (`pre` / `script` / `style` / `textarea`、閉じタグまで) と **type 6** (ブロック要素タグ、空行まで) のみ扱う。type 7 (任意タグ単独行) は近似していない (false-red)。raw HTML の `<h2>` 等は読み飛ばすだけで heading としての節閉じ効果は持たない
- heading text は Unicode ハイフン類と NBSP 類を ASCII に畳んでから照合する。それ以外の異体字 (全角英字など) は畳まない
- 受け入れ条件節の heading は**完全一致**のため `## 受け入れ条件 (追加)` のような suffix 付きは対象外 (凍結済み仕様)

- heading を link 化した形 (`## [受け入れ条件](#ac)`) は heading text が完全一致に落ちるため対象外
- **setext heading (`見出し` + `---` / `===`) は認識しない**。GitHub は heading にするが、実測で「setext を使う本文は 31 本中 0 件 / `---` 区切りを含む本文は 3 件」で、段落直後の `---` を setext と解釈すると偽の heading が対象節を打ち切る false-green が出る (実在 PR #943 の本文に `---` を 1 行足すと exit 1 → exit 0 に反転)。得るもの 0 / 害 3 なので認識しない側に倒した
- **以下は既知の false-green として残っている** (#967 で計測済み、いずれも「GitHub 上には未消化 checkbox が見えるのに gate は通る」形):
  - 折り返し行 (lazy continuation) の直後に 4 space 入れ子の項目を置く形
  - heading text の先頭に絵文字などが付く形 (`#### ✅ Self-Test Report`) — prefix 一致に落ちる
  - list marker の直後で改行し box を次行に置く形 (`-` 改行 `  [ ] ...`)

同じ集合を `.github/scripts/check-pr-checklist.js` 冒頭のコメントにも記録している (doc だけに置くと次の実装者に届かないため)。期待値の決め方と再現材料は #967 / PR #970 の renderer 突合表 (`gh api markdown` の `aria-label="Incomplete task"` 個数と checker の counting を突き合わせたもの) を参照。**新しい角を見つけたら推測で直さず、まず renderer に通して期待値を決めること。**

## PR body 規約 (期待値 / 現状 / 修正内容)

すべての PR で本文冒頭に以下 3 section を inline 必須化する:

- `## 期待値 (あるべき姿)`: 2-4 文。この PR がマージされた後にコードベース or 動作がどうあるべきか + なぜ目指すか
- `## 現状 (修正前)`: 2-4 文。PR 作成時点でどうなっているか + 期待値とのギャップ
- `## 修正内容 (現状 → 期待値)`: bullet list。何をしたか、必要なら file path:line で具体化

### issue ref の運用

issue ref がある PR も、期待値 / 現状 は PR 本文に **簡潔に inline 記載** (issue を辿らせない)。詳細は元 issue へ link 参照可、PR 本文と issue 本文の重複は受容。

### release / meta PR の解釈

複数 PR を統合する release / meta PR (例: PR #774) も同構造で書く:

- 期待値: 当該リリースバージョンが出て該当問題が解消されている
- 現状: develop ブランチで修正が積まれ統合準備完了、main は未統合
- 修正内容: 統合した PR list + 各 Track の解消内容

### Iron Law 6 サブ条との関係

本規約は PR template (`.github/pull_request_template.md`) と一致する。template の `## 期待値` / `## 現状` / `## 修正内容` を埋めずに PR 作成すると `/review-pr` で blocker 扱い。

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
2. 各 reference が target doc の `##` または `###` 見出しと文字列一致するか確認 (`grep -nE "^### ?<セクション名>" docs/<target>.md` 等)。**partial-string match 許容**: 見出し末尾の注釈 (例: `(#428 / #405 matrix v2)`、`(#440 / PR #632)`) は section name に含めず、本体名 (例: `click-level option-parse error`) のみで一致を判定する (PR #784 で明文化)
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

### triage / roadmap 策定時の入力 4 系統 (Refs #870)

**上記 1-3 は「次の 1 件を選ぶ」手順であって、triage / roadmap 策定の入力ではない。** release triage や roadmap 更新で作業対象を洗い出すときは、以下の **4 系統すべて**を入力に含める。

> **なぜ open issue だけでは足りないか**: 2026-06-29 の v0.3.0 roadmap triage は「open 48 件を triage」= 入力が open issue のみだった。この方式では**台帳に載っていない残タスクが構造的に漏れる**。2026-07-06 の sweep で実際に 13 件が漏れており #860-#869 ほかとして起票された。漏れた記録場所が下表 (2)-(4) の 3 系統である。

| 系統 | 入力 | 漏れた実例 (2026-07-06 sweep) |
| --- | --- | --- |
| (1) | open issues | — (現行どおり) |
| (2) | 直近監査 spec の未起票表・棚卸し表の**未決着行** | `2026-06-10-audit-remediation-design.md` Wave 3 表 (wmic / hwaccel / typer pin がいずれも未起票だった) |
| (3) | 直近 close issue (NOT_PLANNED / 残タスク宣言付き COMPLETED) の**後継 issue 実在確認** | #327 (AUDIO_FROZEN 解凍条件) / #762 (decode hwaccel 後継) |
| (4) | docs の「別 issue」「follow-up」「削除予定」宣言のうち**実在 issue 番号を伴わないもの** | `docs/detection-map.md` の「legacy fps filter path 別 issue で撤去」(当時は行き先 issue が不在。現 #864) |

**実行コマンド** (4 系統とも実行し、hit を triage 表へ転記する):

```bash
# (1) open issues
gh issue list --state open --limit 200 --json number,title,labels

# (2) 監査 spec の未起票表・棚卸し表 -- hit 行の「対応」列が未決着なら triage 入力
grep -rniE '未起票|棚卸し|未決着' docs/superpowers/specs/*.md

# (3a) NOT_PLANNED で閉じた issue -- 後継が要るのに不在でないか
#      --limit は必ず全 closed issue を覆う値にする。gh の並びは createdAt DESC で
#      closedAt 順ではないため、窓を絞ると「古く作られて最近閉じた」issue が落ちる
gh issue list --state closed --limit 400 --json number,title,stateReason \
  --jq '.[] | select(.stateReason=="NOT_PLANNED") | "\(.number)\t\(.title)"'

# (3b) COMPLETED だが本文に残タスク宣言がある issue -- 宣言先の実在を確認
#      (3a) と二重計上しないよう COMPLETED に絞る
gh issue list --state closed --limit 400 --json number,title,body,stateReason \
  --jq '.[] | select(.stateReason=="COMPLETED") | select(.body | test("別 issue|follow-?up|後継|残タスク")) | "\(.number)\t\(.title)"'

# (4) docs の先送り宣言を全件出す。末尾の grep -v は本コマンド自身が本節に
#     マッチする self-hit を落とすためだけのもの
grep -rnE '(別 ?issue|別途 ?issue|後続 ?issue|follow-?up issue)[^#]*(で|にて)(撤去|削除|対応|追跡|実装|検討|移行)|(削除|撤去|廃止)予定|(今後|将来)実装|追加予定' \
  docs/*.md CLAUDE.md README.md | grep -v 'grep -rnE'
```

> **(4) で `| grep -vE '#[0-9]{3,}'` による自動免除を使わないこと (Refs #966 の実測)**。「同一行に 3 桁の `#` があれば追跡済み」という判定は、**その `#` が当の先送りの追跡先とは限らない**ため leak を素通りさせる。実例: `docs/detection-map.md:61` は「#576 で新 path を default 化 … v0.3.x で**削除予定**」で、撤去の追跡先は #576 ではなく **#864**。無関係な #576 のせいで行ごと免除され、#870 が対象とする当の leak クラスを落としていた。**免除ありで 7 hit / 免除なしで 13 hit** — 差の 6 件を人が仕分ける方が、leak を見逃すより安い。各 hit は「行内の `#NNN` が本当にこの先送りを追跡しているか」を 1 件ずつ確認する。

**hit の扱い**: (2)-(4) の hit は**違反ではなく triage 候補**である。各 hit を「実在 issue を伴う宣言か / 単なる process 記述か / 起票漏れか」で仕分け、起票漏れのみ [`/create-task`](../.claude/skills/create-task/SKILL.md) へ回す。特に (4) は process を説明する散文 (「(B) 別 issue 起票」等) も拾うため、**仕分け前提の粗い網**であることを承知して使う。網を細くして取りこぼすより、粗く拾って仕分ける方を選んでいる。

**非実施時の記録義務**: 4 系統のうち実施しなかったものがあれば、triage 結果に `triage 入力 (N): 未実施 (理由: <1 行>)` を残す (§「規約・ガード導入の 3 点セット」②)。無記載は「実施して 0 件」と「実施しなかった」を区別できない。

**close 時の点検との関係**: #817 で `/close-issue` と `/release` に入れた追跡切れ防止チェックは **close 時点の点検**、本節は **triage 時点の総点検**であり相補関係にある。片方があれば他方が不要になるものではない (close 時に見落とした宣言を triage が拾い、triage の後に閉じた issue を close 時チェックが拾う)。

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

## 規約・ガード導入の 3 点セット (G1-1)

規約 / ガード / チェックを**新設**するときは次の 3 点を必ず揃える。1 つでも欠けると「導入したが 1 度も赤を出していない機構」になり、規約だけが増えて風化する。

> **なぜ 1 本の条文にするか**: #918 item3 / #912 / #910 / #658 / #876 / #934 の **6 件が同じ要求を別々に書いていた**。「新ガードは発火実証まで」という同一の規律が issue ごとに書き直されていたため本節へ集約する。以降の PR / issue は個別に書き直さず**本節を参照する**。

1. **発火点をファイルと行で指定する** — skill step / CI job / hook のいずれかを、**ファイル名と行番号**で書く。**「doc に書いた」だけでは発火点にならない。** doc は読まれるかもしれない散文であって、実行される機構ではない
2. **非実施時の 1 行記録義務** — 実施しなかった場合に理由を 1 行残す義務を課す。これがないと「意図的に skip したのか / 忘れたのか」が事後追跡できない (Iron Law 5 整合)。既存 reference は [`.claude/skills/review-pr/SKILL.md`](../.claude/skills/review-pr/SKILL.md) §「起動条件不該当時の明示記録」 の `Codex review 起動: 非対象 (理由: ...)` 形式
3. **発火側の red 実証** — 違反を**一時注入**して **exit code の生値**で発火を観測し、その観測を pin test として同梱する。「テストが green」は機構が動いた証拠にならない (no-op でも green になる)

### なぜ ③ が最も落ちやすいか

保護機構は**不発でも green のまま**なので、CI が no-op を mask する。実例: `pytest` 9 では `addopts` 内の `--strict-markers` が silent no-op になり、ini option `strict_markers = true` が正だった (PR #819 R4→R5 で発覚)。「追加した」だけでは動作証拠にならない。

**red 実証の最小手順**:

```bash
# 1. 違反を一時注入する (checkbox を 1 件 unchecked に戻す / 偽の日付を入れる / 宣言を 1 件抜く 等)
# 2. ゲートを直接起動し exit code を生値で観測する (|| true や -q で握り潰さない)
node .github/scripts/<gate>.js <fixture>; echo "exit=$?"   # 非ゼロを期待
# 3. 注入を戻して exit 0 に復帰することを確認する (false-red でないことの確認)
# 4. 1-3 を pin test 化して同梱する (次の改修で silent に no-op へ戻るのを防ぐ)
```

### 参照契機 (誰がいつ引くか)

| 契機 | 何をするか |
| --- | --- |
| [`/review-pr`](../.claude/skills/review-pr/SKILL.md) Step 5 | PR が CI job / hook / skill step を**新設**している場合、本節の 3 点に照らして逐条検証し、欠けていれば Step 5b トリアージ表に計上する |
| [`/create-task`](../.claude/skills/create-task/SKILL.md) §ガード / 規約 / チェックを追加する issue の受け入れ条件 | 「ガードを追加する」issue を起票する際、`## 受け入れ条件` に 3 点セットを反映する |
| [`CLAUDE.md`](../CLAUDE.md) §開発ワークフロー | 発見可能性の確保のため 1 行リンクを置く |
| `superpowers:brainstorming` | **規律のみ (コード上の発火点ではない)。** plugin skill は本 repo に存在せず編集できないため、再発防止機構を設計する creative work で本節を引くのは実行者の規律に依存する。**この行を「実装済みの発火点」と数えない** |

### Red Flags

| 浮かんだ思考 | 実態 |
| --- | --- |
| 「doc に規約を書いたから導入完了」 | ①未達。doc は発火点ではない。skill step / CI job / hook のどれに載るかを行で示す |
| 「テストが green だから機構は動いている」 | ③未達。no-op でも green になる。違反を注入して非ゼロ exit を観測するまで動作証拠はない |
| 「実施しなかったが自明なので記録は不要」 | ②未達。意図的な skip と失念が事後に区別できなくなる |
| 「文章だけ足しておいて機械検査は次の PR で」 | 3 点セットは分割不可。①だけ先行させた規約は次の PR まで no-op で、その間に風化する |

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

- **AND 1 (merged)**: 最新 (`sort -V`) の `origin/develop-*` または `origin/main` の祖先 (`git merge-base --is-ancestor`。#816 で develop-0.2.0 固定から一般化。stale な旧 develop ref を merge 根拠にしないため最新のみを採用)、**または** local branch tip の OID が `gh pr list --state merged` の head commit OID (`headRefOid`) 集合に一致する (#827)。本 repo の PR は `--squash` マージのため branch tip が base の祖先にならず is-ancestor では永遠に not-merged 扱いになる。この構造的不整合を gh の merged head OID で OR 補完する。**OID 同一性で照合する**ため、PR merge 後に同名 branch を再作成し未 merge の新 commit を積んでも local tip OID が一致せず kept になり、不可逆 data-loss を構造的に防ぐ (codex HIGH)。gh または `timeout` が不在 / 非ゼロ exit / timeout 発火時は集合を空に倒し is-ancestor のみに fallback する (安全側)
- **AND 2 (active 参照なし)**: `git worktree list --porcelain` の `branch refs/heads/...` 集合に含まれない
- **AND 3 (24h cooldown)**: 最終 commit (`git log -1 --format=%ct`) が 24h 以上前
- **prefix 限定**: `claude/` のみ (= `feature/xxx` 等の手動 branch は対象外)

**評価順序**: AND 2 → AND 1 → AND 3 (cost-efficient: AND 2 は local hash lookup で安価、AND 1 / AND 3 は git subprocess を spawn するため後回し)。最初に fail した条件が `kept <branch> (reason: not-merged | active | cooldown)` の reason として記録される。gh merged 判定 (#827) は `command -v gh` + `command -v timeout` の両方が揃うときのみループ前に 1 回だけ `timeout 10 gh pr list` を呼ぶ (network 依存だが必ず bound される)。判定経路は start event の `gh_merged_lookup` (`ok` / `unavailable` / `error`) と deleted / would_delete event の `merged_via` (`ancestor` / `gh`) で可視化される。

最新の `origin/develop-*` / `origin/main` が未 fetch だと `merge-base --is-ancestor` が false に倒れて keep される = 安全側。`git fetch` は hook 内で実行せず、user の通常運用 (`git pull`) を前提とする。gh merged 判定も同様に、gh 未認証 / network 不通 / `timeout` 不在なら fallback して is-ancestor のみで判定するため、オフライン環境でも安全に (かつ実行時間を bound して) 動作する。OID 同一性照合により、gh が報告する merged head と local branch tip が同一 commit のときのみ削除するため、名前衝突による誤削除は発生しない (#827 codex HIGH 対応)。

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

`cleanup-claude-branches.sh` も同様に明示的に安全な AND 3 条件 (merged + active 参照なし + 24h cooldown) + `claude/` prefix 限定下でのみ `git branch -D` を実行し、merged 保証により data loss しない。最新の `origin/develop-*` / `origin/main` が未 fetch なら `is-ancestor` false に倒れて keep する設計のため、fetch されていない開発環境でも安全に動作する。

## brainstorming sweep 規約 (#746 教訓)

brainstorming で「stale 参照 X を post-Y に更新する」「dangling reference を sweep する」のようなスコープ確定を行うとき、`Read` で個別箇所を見るだけでは sweep に漏れが出る。**Q1 で sweep 範囲を提示する直前に repo-wide grep を実行**し、結果を全件 inventory する。

### Why

PR #746 (Lane V Phase 3 / Group I, issue #699) で「dangling `appErrorMessage` / `appErrorHint` 参照を sweep」と確定したが、brainstorming で 3 箇所と list した一方、実装中の Phase C scan で 2 file 追加発見 (`ui-interaction-spec.md:693`, `tauri-commands.md` lines 10/58/65/73) した。結果 user の AskUserQuestion を再度発火させ、scope expansion 承認を得て Phase D で PR 内 fix した。brainstorming で `git grep` していれば最初から正しい sweep 範囲を Q1 に提示でき、Phase D は不要だった。

### How to apply

- brainstorming Q1 で sweep 範囲を提示する直前に `git grep -nE "<symbol>" -- ':!docs/superpowers/' ':!docs/archive/'` を実行 (Bash tool 1 回で済む)
- 結果を全件 inventory して spec §5 詳細設計 / §8 受け入れ条件 に列挙
- spec §8 AC で「repo 全体で残っていない」と書くなら、その AC を sweep 確定時点で grep 検証する (AC 文言と実 sweep の食い違いを防ぐ)
- 対象が `appError*` のように複数の関連 symbol で構成される場合は `git grep -nE "(appErrorMessage|appErrorHint|appErrorCodeIs)"` のように同類をまとめて grep する

## subagent 起動規約 (#746 Phase C / #741 Task 5 教訓)

実装 / scan / refactor task で限定スコープを subagent に dispatch するとき、prompt に**必ず**以下の HARD-GATE を含める。これがないと subagent が独断 fix を進めて Iron Law 3 (scope creep) や Iron Law 5 (independent judgment) を踏む。

### Stop-on-scope-creep (subagent prompt に必須記述)

subagent prompt の `## Stop conditions` セクションに以下を含める:

- 「Predefined scope を超える発見 (新 file の dangling ref / 想定外の修正候補 等) → STOP, report BLOCKED with finding details」
- 「想定外 finding に対して独断 fix することは禁止 (scope expansion は controller + user の判断)」
- `## Self-review` または `## Report` セクションに「scope 外の独断行動なし」項目を追加し、subagent に self-confirm を要求

#### Why

PR #746 Phase C で「repo-wide dangling-ref scan」を dispatch した subagent が、scan で見つけた `ui-interaction-spec.md:693` の dangling ref を独断で fix commit (`a752fc0`) し、別 file の `tauri-commands.md` 4 件は「out-of-scope」と判定した。fix-vs-flag の境界判断を subagent が独断したことが Iron Law 5 違反。本来 STOP/escalate して controller (= main session) が判断すべき。事後の整合作業 (Phase D での PR body 修復含む) が発生した。

### Orphan commit 防止 (controller 側 verification)

subagent-driven-development の Task 実装で、subagent が `git checkout <SHA>` 等で detached HEAD に入ってから commit すると、新 commit は元の branch HEAD ではなく detached state の上に作られる。subagent が戻る (checkout branch) 際に reattach しないと、commit は orphan 化 (`git show <SHA>` では見えるが branch から到達不能) する。

controller (main session) は subagent dispatch 後に以下を**必ず**実行:

```bash
# 1. branch HEAD への到達性確認 (reviewer subagent の verification には依存しない)
git log <branch> --oneline -5 | grep <expected-SHA>

# 2. PR 作成前 (push 前) に PR に乗る予定の commit 一覧を最終確認
git log origin/<base>..HEAD --oneline
```

想定 commit 数 (例: 5 Task = 5 commit) と一致しなければ orphan commit が発生している。

#### 検知時の修正

```bash
git cherry-pick <orphaned-SHA>
```

現 HEAD 上に同内容の新 commit を作り直す。Push 済 PR は force push 不要 (新 SHA で追加 commit として乗る)。

PR #741 (2026-05-13 Lane II-b' Group D 残) で Task 5 docs commit (`cda0f8e`) が parent=9ce2565 (old base) 上の orphan になっていた事例。final reviewer の subagent が「Head: cda0f8e」claim と PR 実 head bf083f3 の食い違いを指摘して発覚、`git cherry-pick cda0f8e` で 252de72 として再生成し push して解決。

### AskUserQuestion で scope 拡大選択肢を出さない (#732 教訓)

controller (主セッション) が subagent reviewer の判定を受けて AskUserQuestion を組み立てる時、**subagent reviewer が scope 外 ((B) or (A) re-run 推奨) と判定した finding に対して「本 PR 内修正 (scope 拡大)」を選択肢に追加しない**。subagent recommendation を第一の選択肢 (Recommended) に置き、他は subagent が挙げた選択肢のみ提示する。user が `Other` で明示提案するまで scope 拡大は出さない。

詳細は `.claude/skills/iterate-review/SKILL.md` §AskUserQuestion 設計規約を参照。

## skill 改修ワークフロー (empirical-prompt-tuning)

skill を**大幅改訂** (新節追加 / frontmatter description 書き換え相当) する際は、書き手が自覚できない曖昧さ・欠落を **bias-free な subagent による empirical 評価**で炙り出す。自己再読では構造的欠陥に到達できない。

### 適用対象

- skill 新規作成
- frontmatter description 書き換え + 新節追加を伴う大幅改訂

typo fix / リンク更新では過剰。`/iterate-review` のような中核 skill の改訂で特に有効。

### 上流参照 (mizchi protocol を直接読む)

上流 SKILL.md を **vendoring せず** (license 未設定のため)、改修者が都度参照する:

- URL: <https://github.com/mizchi/skills/tree/main/meta/empirical-prompt-tuning>
- raw 取得: `gh api repos/mizchi/skills/contents/meta/empirical-prompt-tuning/SKILL.md -H "Accept: application/vnd.github.raw"`
- offline / GitHub 不到達時は WebFetch / `gh api` 不可 → skill 改修作業を保留。短期キャッシュは作業 dir に置いて **commit しない**

### How to apply

1. **前段階の事例調査**: 指摘ラウンドが多かった実在 PR を 3 本ピックアップし、Explore agent 並列で指摘パターンを抽出してからモック設計へ
2. **モック設計**: 中央値 1 + edge 2 (束ね PR / 孤立 PR / doc-only 等) を `.claude/skills/<skill-name>/eval/scenario_*.md` に書き出す
3. **要件チェックリスト**: `[critical]` タグ付きで事前固定。`eval/requirements.md` に集約
4. **subagent dispatch**: `general-purpose` を `model: sonnet`、3 並列・`run_in_background: true` で起動
5. **empirical 規範遵守**: Iteration 1 再評価では必ず**新規 subagent** (empirical Red Flag「同じ subagent を使い回そう」に該当するため同一 agent は不可)
6. **打ち切り基準**: 2 consecutive clears (new unclear=0 + accuracy +3pt 以下 + step ±10% + duration ±15%) で打ち切り。または構造的欠陥 (新節欠落 / 判定基準不在レベル) が解消された時点で打ち切り可。残る細部不明瞭点は deferred issue として追跡

### Iron Law 6 路線 / Self-Test Report integration

本 workflow を skip した skill 改修 PR は「未検証 PR」と同じ扱い。

- PR Self-Test Report に `### empirical prompt tuning` セクションを設け、Iteration table (per-scenario success / accuracy / steps (tool_uses) / duration / structured reflection / ledger updates) を記録する
- 例外: trivial wording fix (typo / link 修正 / コメント追記のみ) は skip 可、判断は `AskUserQuestion` で確認
- Self-Test Report の `### empirical prompt tuning` section を欠いた skill 改修 PR は `/review-pr` で blocker 扱い (Iron Law 6 違反)

### 経緯

2026-04-24 `/review-pr` skill 改修で実証済み (PR #537 / #562)。Iteration 0 baseline で構造的欠陥 6 件 (環境制約節欠落、Round N 記法不在、処置分類判定基準の弱さ、束ね PR 独立検証の明示不在、孤立 PR 手順不在、doc-only CI 波及観点なし) を検出し、Iteration 1 で全件解消。精度 0.98 → 1.00、[critical] 3/3 成功。書き手自身の自己レビューでは構造的欠陥に到達できなかった。参考: <https://github.com/mizchi/skills/tree/main/meta/empirical-prompt-tuning>

## Codex fallback (C6、Codex token 枯渇 / failure 時)

Codex CLI (`codex-companion.mjs` runtime) が以下のいずれかで fail した場合、Claude Code 側で同等処理を fallback 実行する。Iron Law 1 / 6 違反 (受け入れ条件検証 / Pre-flight ゲート不通過のまま進行) を防ぐ。

### 検出条件

| 検出条件 | 判定 |
| --- | --- |
| exit code 非ゼロ + stderr に `rate.?limit`, `quota`, `429`, `usage_limit` のいずれか | **token 枯渇 (明確)** → 自動 fallback |
| exit code 非ゼロ + stderr に `auth`, `unauthorized`, `401`, `403`, `api.?key` | **認証失敗 (明確)** → 自動 fallback + user notify |
| exit code 非ゼロ + stderr に `timeout`, `EHOSTUNREACH`, `ENETUNREACH`, `ECONNRESET` | **network failure (明確)** → 自動 fallback |
| exit code 非ゼロ + 上記いずれにも該当しない stderr | **曖昧** → user に AskUserQuestion (再試行 / Claude fallback / abort) |
| exit code 0 + stdout が空 / parse 不能 | **応答異常** → user に AskUserQuestion |

### 検出 + fallback の擬似コード (skill 内実装イメージ)

`/review-pr` Step 5a / `/iterate-review` Round 2.1 等で Codex を invoke した後の処理イメージ。agent からの通常実行は companion script 直接呼び出し (§Step 5 の invocation path (3-tier、#795) の tier 1。`review` / `adversarial-review` とも slash command は `disable-model-invocation: true` のため agent invoke 不可、slash 形式は tier 3 = Idios 専用)。**subcommand と focus の対応に注意**: `review` は focus positional を受けず非空 focus を reject する。project 固有 focus を渡す場合は `adversarial-review` を使う:

```text
result = run_bash('node "$CLAUDE_PLUGIN_ROOT/scripts/codex-companion.mjs" adversarial-review --base develop-0.3.0 "<focus>"')

if result.exit_code != 0:
    stderr_lower = result.stderr.lower()
    if matches_any(stderr_lower, ["rate", "quota", "429", "usage_limit"]):
        fallback_reason = "token 枯渇"
        invoke_fallback("superpowers:requesting-code-review")
    elif matches_any(stderr_lower, ["auth", "unauthorized", "401", "403", "api"]):
        fallback_reason = "認証失敗"
        invoke_fallback("superpowers:requesting-code-review")
        notify_user("Codex auth failed; check token / api key")
    elif matches_any(stderr_lower, ["timeout", "ehostunreach", "enetunreach", "econnreset"]):
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
```

実装は skill prompt 側 (`/review-pr` SKILL.md Step 5a / `/iterate-review` SKILL.md Step 2.1) で行う。Codex CLI のラッパー (`codex-companion.mjs`) との連携詳細は openai-codex plugin doc を参照。

### Fallback 戦略

| Codex 実行 (agent の通常 path) | 通常用途 | Fallback 内容 |
| --- | --- | --- |
| `codex-companion.mjs review` (C3 で `/review-pr` Step 5a に Bash 実行。focus positional 不可 — project 固有 focus を渡す場合は `adversarial-review` subcommand を使う。slash `/codex:review` は tier 3 = Idios 専用) | code quality adversarial pass | superpowers `requesting-code-review` subagent を起動して同等の adversarial review。focus 文字列は Codex に渡した (渡す予定だった) ものと同じ |
| `codex-companion.mjs adversarial-review` (C2 で Iron Law 6 Step 5 に Bash 実行 = tier 1。slash `/codex:adversarial-review` は tier 3 = Idios 専用) | Pre-flight 第 5 ゲート | superpowers `requesting-code-review` subagent + project 固有 focus を起動。`<grounding_rules>` 相当で「adversarial / approve させない姿勢」を明示 |
| `/codex:rescue` (C4 で root-cause 調査時に invoke。`disable-model-invocation` なし = agent invoke 可、`codex:codex-rescue` subagent 経由) | bug 根本原因 + 類似バグ探索 | Claude main + superpowers `systematic-debugging` skill で自力調査。`/scope-guard` 規約は維持 (独断 fix 禁止) |

### Fallback 実行時の必須記載 (Iron Law 5 整合)

skill report (`/review-pr` Step 6 レビュー報告 / `/iterate-review` **Final summary comment (Step 4)**) に以下を**必ず明示**:

```text
> **Codex fallback notice**: 本 review は Codex CLI が <検出条件> で fail したため、
> Claude Code (superpowers:<skill-name>) で代替実行しました。
> Codex 側の review は次セッションで再試行を推奨します。
> stderr 要約: <stderr の先頭 200 字>
```

これがないと Idios が Codex review 済と誤認するリスクがある (Iron Law 5 衝突回避)。

### Fallback の限界 (明示)

- Codex は GPT-5.4 (独立 model) の second opinion。Claude Code fallback は同一 model の self-review に近く、bias 構造が同じになる
- 重要 PR (release 直前 / 大規模 refactor) で Codex fallback が trigger した場合、user に AskUserQuestion で「Codex 復旧待ち / Claude fallback で push」の 3 択を提示
- fallback report には「fallback で実行済」を明示することで、後日 Codex 復旧時に再 review が要否を判断可能にする

## subagent + Codex 直列構成 (C5)

大規模実装 / 重要 PR では superpowers `subagent-driven-development` (Claude 内 fresh subagent) と Codex review (GPT-5.4) を **直列**で組み合わせる。並列ではなく直列にする理由: Codex 自身に fix させない (Iron Law 3 / 5 整合)。agent からの Codex 実行は §Step 5 の invocation path (3-tier、#795) と同じく companion script 直接呼び出し (`codex-companion.mjs review`)。slash `/codex:review` は `disable-model-invocation: true` のため Idios 専用 (本 § の Flow 図・表では `codex:review` を出所 label / subcommand 名として用いる)。

### Flow

```text
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
│ Stage 3: Codex review (tier 1, GPT-5.4) で adversarial pass   │
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
```

### Iron Law 6 Pre-flight Step 5 との違い

| 軸 | Iron Law 6 Pre-flight Step 5 (C2) | subagent + Codex 直列構成 (C5、本節) |
| --- | --- | --- |
| 起動タイミング | PR 作成**直前** (Step 0-4 通過後) | `/review-pr` 段階の **deep-dive** (Step 5a) |
| Codex command | `adversarial-review` subcommand (approve させない姿勢、tier 1 = companion script) | `review` subcommand (code quality 一般、同) |
| 必須 / オプション | **必須** (Pre-flight ゲート) | optional (起動条件: 大規模 PR / 過去 root cause 複数 / L1 core) |
| 直前 stage | Step 4 並行 PR 重複再確認 | superpowers subagent 実装 + reachability 確認 |

### 並列ではなく直列にする理由

- Codex に fix させると Iron Law 3 (scope creep) / Iron Law 5 (independent judgment) の衝突リスク
- superpowers subagent (Claude 思考体) と Codex (GPT-5.4) を並列起動しても finding が重複するだけで bias は減らない
- 直列で「実装 → reachability → adversarial review → triage」と段階化すると、各 stage で人 (Idios) が介入できる checkpoint が確保される

### Fallback (Codex fail 時)

Stage 3 で Codex CLI が token 枯渇 / network failure 等で fail した場合は §Codex fallback (C6、本 doc 内) に従い、superpowers `requesting-code-review` subagent を Stage 3 の代替として起動する。Stage 4 triage は同様に実施し、fallback notice を report に必須記載する。

## 外部依存規約 (#649/#651/#703/#721 教訓)

外部依存 (Python / npm / cargo / OS binary tarball 等) の**版を固定する**。3 つの形がある。

1. **DL URL は immutable にする** — `master` / `main` / `latest` / `raw HEAD` を含む URL は禁止
2. **依存 manifest には上限を付ける** — `>=X` (上限なし) は新 major を無検証で招き入れる
3. **再現が要る版は exact pin する** — 範囲指定は「範囲内の最新」に解決されるので再現環境にはならない

### Why

PR #649 → #651 (get-pip.py SHA pin) → #703 (versioned tag URL 切替) → #721 (BtbN monthly snapshot) の 3 hotfix 連発 (F2)。最初から immutable URL ルールがあれば 1 PR で完結した。BtbN daily の retention 14 日 / get-pip.py master の breaking change 等、上流側の breaking が DL URL に影響する。

Python 依存側でも同型が起きた (#916)。`opencv-python-headless>=4.8` (上限なし) が CI と配布物で **5.x** に解決される一方、検出精度の bit-exact baseline は 4.13.0 でしか検証されていなかった。`rich` は上限なしの transitive のまま 15 系へ上がり、`assert "--vtuber" not in result.stdout` 形の pin を **CI で常に真 = false-green** 化していた (#915 で実測)。「上限がない = 上流のリリース判断がそのまま本 repo の検証前提になる」。

### 受け入れ可能なソース

| ソース | 形式 | 例 |
| --- | --- | --- |
| PyPA versioned tag | `https://github.com/pypa/<repo>/raw/<tag>/...` | get-pip.py |
| BtbN monthly snapshot | `https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-YYYY-MM-{28,29,30,31}-*/...` | FFmpeg n8.1 |
| npm registry version pin | `package.json` の `dependencies` で `"^X.Y.Z"` (transitive は package-lock.json で fix) | tauri / vite |
| cargo registry version pin | `Cargo.toml` の `tauri = "2.11"` (transitive は Cargo.lock で fix) | tauri-utils |
| SHA-pinned download | `https://.../...-<commit-hash>.tar.gz` + SHA256 checksum | FFmpeg checksum |
| pip manifest version pin | `pyproject.toml` の dependencies / optional-dependencies で**上限付き** (`>=X,<Y`)。直接 import するものだけを宣言する | opencv-python-headless / typer / click |
| pip exact pin (再現環境) | `constraints.txt` の `name==version`。**repo 内の再現専用**で、直接依存にしたくない transitive (rich / black / isort) の固定にも使う | cv2 / numpy / scipy / codegen chain |

### 禁止パターン

| パターン | 理由 |
| --- | --- |
| `https://.../master/...` | upstream master の breaking が即影響 |
| `https://.../main/...` | 同上 |
| `https://.../latest/...` | retention / 互換性が保証されない |
| `https://raw.githubusercontent.com/.../HEAD/...` | HEAD は git ref として可変 |
| `npm install <pkg>` (version 未指定) | semver caret semantics で意図せぬ major up に脱する |
| `pyproject.toml` の `>=X` (上限なし) | 新 major が CI と配布物へ無検証で流入する (#916: cv2 が 4.x 前提の baseline のまま 5.x に解決されていた) |
| 範囲指定を「再現環境の pin」と見なす | `>=4.8,<5` は実測で 4.14.0.94 に解決する。範囲は**互換性の宣言**であって再現ではない。再現は `constraints.txt` の `==` が担う |

### 検証手順

`scripts/build-portable-zip.ps1` / `.github/workflows/*.yml` / 任意の install script を編集する場合:

1. 該当行のコメントに「must be immutable (versioned tag / SHA pinned)」と記載
2. Pester regression (`scripts/tests/build-portable-zip.Tests.ps1`) で URL に `master`, `main`, `latest`, `HEAD` の literal が含まれていないことを assert
3. `/review-pr` skill が installer / workflow PR を review するときに本 § を引いて URL 規約適合を Step 5b トリアージで逐条検証

`pyproject.toml` / `constraints.txt` を編集する場合 (#916):

1. `constraints.txt` に行を足したら **`pytest tests/test_dependency_pins.py` が赤 → 緑になることを確認する**。pip は constraints file の**未使用行を無言で無視する** (依存グラフに現れない名前を書いても警告が出ない) ため、「pin したつもり」が no-op 化していても pip 自身は気づかせてくれない
2. 新しい `pip install` を足したら `-c constraints.txt` を付ける。**付け忘れると同一 workflow / build 内に constraints 非適用の解決が 1 本残る**。`scripts/build-portable-zip.ps1` 側は Pester の `Dependency constraints wiring (#916)` が statement 数と call-form を pin している
3. 検出出力に影響する依存 (cv2 / numpy / scipy) を bump する場合は **bit-exact baseline の再取得が必要**。手順は [`docs/developer-setup.md`](developer-setup.md) §9 を参照

**`-c` の射程外 (既知の残余)**: constraints は PEP 517 の分離ビルド環境へ伝播しないため、`[build-system] requires` の `setuptools` は `constraints.txt` では固定できない。`pip` 自身の版も固定していない (`--upgrade pip` が CI / 配布 build にある)。また constraints は **本 repo の install 経路専用**で、第三者の `pip install kobutachan-allaganeye` には効かない (そちらは `pyproject.toml` の範囲だけが効く)。

## 参考

- [code.claude.com/docs/en/skills](https://code.claude.com/docs/en/skills) — skill 設計ガイド
- [code.claude.com/docs/en/best-practices](https://code.claude.com/docs/en/best-practices) — 単一セッション推奨
- `docs/release-process.md` — ブランチ戦略と手動リリース手順
- `docs/issue-policy.md` — Issue 起票ルール (role:* 節を削除済み)
- `plans/deffere-issue-l2-deffered-1-l1-issue-2-graceful-clover.md` — L2 移行計画全体
