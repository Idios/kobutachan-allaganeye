---
name: create-task
description: issue-policy.md に沿って GitHub issue を対話的に作成する。全 prefix 対応 (bug/doc/refactor/task/question/risk)、refactor/task/risk は preamble (期待値/現状/ユーザー影響・重要性) 必須
user-invocable: true
argument-hint: <タスクの概要（自然言語）>
---

ユーザーの指示に基づいて GitHub Issue を作成する。`docs/issue-policy.md` のルールに従うこと。

## 手順

1. ユーザーの指示（`$ARGUMENTS`）からタスクの内容を把握する
2. 適切な prefix を選択する（`[bug]`, `[doc]`, `[refactor]`, `[question]`, `[risk]`, `[task]`）
3. `docs/issue-policy.md` §3 の対応テンプレートに沿ってタイトルと本文を作成する:
   - prefix が `[refactor]` / `[task]` / `[risk]` の場合: **共通 preamble (期待値 / 現状 / ユーザー影響・重要性) を必ず含める**
     - 期待値: ユーザー指示 + 関連 issue/spec/コード読みから「完了後の状態」を 2-4 文で推論
     - 現状: 関連コード or doc を Read/Grep して具体的にギャップを記述
     - ユーザー影響・重要性: 1 行で位置付け (例:「ユーザー影響なし、メンテ性負債」「将来のセキュリティ整合性」)
     - skill は draft を一括生成。ユーザーは手順 5 で修正を指摘
   - prefix が `[bug]` / `[doc]` / `[question]` の場合: 現行どおり (preamble 不要)
4. 重複チェック + label 存在確認:
   - 重複チェック: `gh issue list --search "<主題を表す名詞 2-3 個>" --state all --repo Idios/kobutachan-allaganeye` を実行し、類似 issue がないか確認する（キーワードはタイトルから名詞を優先抽出、必要なら本文から補足）
   - label 存在確認: 付与予定の scope/優先度ラベルが repo に存在するか `gh label list --repo Idios/kobutachan-allaganeye | grep <label>` で確認。未作成のラベルがあれば `gh label create` を先行する (起票時の `--label` reject 回避)
5. 作成前にユーザーに以下の要素を提示して確認を得る:
   - タイトル（文字数表示付き、例: "33/40 文字"）
   - assignee / ラベル一覧（スコープラベル・優先度ラベル含む）
   - 重複チェック結果（ヒット件数と代表 issue）
   - 本文全文
   - (refactor/task/risk の場合) preamble 3 セクションの中身が空 or placeholder 残留でないことの self-check 結果 (`期待値: 埋め済 / 現状: 埋め済 / 影響: 埋め済` を 1 行で表示)
   - 選択肢: 「はい / 修正箇所を指摘 / やめる」
6. ユーザーが承認したら以下のコマンドで作成する（Windows + Git Bash での日本語本文破損回避のため `printf | --body-file -` 方式）:

   ```bash
   printf '%s\n' "<本文>" | gh issue create \
     --repo Idios/kobutachan-allaganeye \
     --title "<prefix> <概要>" \
     --body-file - \
     --assignee "Idios" \
     --label "<prefix に対応するラベル（該当する場合）>" \
     --label "<スコープラベル（l2a-gui / l2b-installer / l2c-guard / l2-workflow / l2-decision / l1-residual 等、該当する場合）>"
   ```

## 注意事項

issue 規約 (粒度 / prefix ラベル / スコープラベル / 優先度ラベル / タイトル文字数 / `作成: <session-id>` / `Closes`/`Fixes`/`Resolves` 禁止 等) は [`docs/issue-policy.md`](../../../docs/issue-policy.md) を参照する。本 skill は手順実装に専念し、規約は restate しない。

### preamble 必須化規約 (refactor / task / risk)

`refactor` / `task` / `risk` prefix では preamble 3 セクション (期待値 / 現状 / ユーザー影響・重要性) が必須。skill が draft を生成する際:

- 関連 issue / spec / コードを Read/Grep で具体的に読んで埋める
- 推論できない場合は placeholder で起票せず、ユーザーに具体的に聞き返す (例: 「期待値を埋めるための情報が不足しています。完了後にコードがどうあるべきか教えてください」)
- 「ユーザー影響・重要性」は 1 行制約。長くなる場合は他 section に分離: refactor=「ブロッカー」 / risk=「顕在化時被害詳細」

preamble を埋められないことは「issue 化に値する整理ができていない」signal。空欄や曖昧な記述で勝手に埋めない。

## Patch release 関連の issue 起票 (#L-γ A2 / M9)

v0.M.N → v0.M.(N+1) の patch release で吸収する issue を起票する場合は、[`docs/release-process.md` §Patch release の Track 構造](../../../docs/release-process.md#patch-release-の-track-構造) (Track A-D 並列化) を参照し、対応する prefix label / scope label を判定:

- **Track A** (security / dependency): prefix `[task]` or `[refactor]`、scope `l2-workflow` (security/CI 系) or 該当 scope
- **Track B** (deferred UX 吸収): `/release` skill Step 0c で (a) 次 release 吸収と判定された issue 群 (新規起票は通常不要、既存 deferred issue が対象)
- **Track C** (CI / build gate): prefix `[task]`、scope `l2-workflow` or `l2-ci`
- **Track D** (version bump + CHANGELOG): `/release` skill が自動生成、`/create-task` は通常使わない

新規起票時に「次 patch で吸収する」と確定済みなら、issue 本文の冒頭にどの Track 候補かを明記し、**Track 構造 doc への link を本文に含める** (例: `[Track 構造](docs/release-process.md#patch-release-の-track-構造) 参照`) と `/release` Step 0c での分類が容易になる。

## deferred 状態の issue 起票 (M8 撤回後の運用、2026-05-17 D1 確定)

現バージョン scope 外として `deferred` を付与する issue を起票する場合のフロー:

1. **`deferred` ラベル付与**: 現バージョン scope 外確定の issue には必ず `deferred` を付与 (`--label "deferred"`)
2. **`release-blocker` ラベルは使用しない**: M8 撤回 (2026-05-17 D1 確定、`docs/superpowers/specs/2026-05-17-v020-v021-retro-codex-integration-design.md` §M8 参照) により、`release-blocker` label は新設・付与しない。次 release 吸収判定は `/release` Step 0c で行う
3. **L1 残課題の場合**: `deferred` + `l1-residual` の dual-label を必ず付与 ([`docs/issue-policy.md`](../../../docs/issue-policy.md) §`l1-residual` + `deferred` dual-label 規約 参照)
4. **本文の必須要素**: 「次 release タイミングで `/release` Step 0c に再評価される前提」を明示。例:

   ```markdown
   ## scope 判定

   現 v0.M.x scope 外 (`deferred` 付与)。次 release タイミングで `/release` skill
   Step 0c の deferred 全件検証時に (a) 次 release 吸収 / (b) deferred 継続 /
   (c) close のいずれかに分類される。

   ## 判定理由

   <なぜ scope 外なのかを 1-2 文>
   ```

5. issue 本文に `[docs/release-process.md §Patch release Track 構造](../../docs/release-process.md#patch-release-の-track-構造)` への link を含めると、後日の Step 0c 評価で参照しやすくなる
