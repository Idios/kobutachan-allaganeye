---
name: create-task
description: issue-policy.md に沿って GitHub issue を対話的に作成する（全 prefix: bug/doc/refactor/task/question/risk 対応）
user-invocable: true
argument-hint: <タスクの概要（自然言語）>
---

ユーザーの指示に基づいて GitHub Issue を作成する。`docs/issue-policy.md` のルールに従うこと。

## 手順

1. ユーザーの指示（`$ARGUMENTS`）からタスクの内容を把握する
2. 適切な prefix を選択する（`[bug]`, `[doc]`, `[refactor]`, `[question]`, `[risk]`, `[task]`）
3. `docs/issue-policy.md` §3 の対応テンプレートに沿ってタイトルと本文を作成する
4. 重複チェック: `gh issue list --search "<主題を表す名詞 2-3 個>" --state all --repo Idios/kobutachan-allaganeye` を実行し、類似 issue がないか確認する（キーワードはタイトルから名詞を優先抽出、必要なら本文から補足）
5. 作成前にユーザーに以下の要素を提示して確認を得る:
   - タイトル（文字数表示付き、例: "33/40 文字"）
   - assignee / ラベル一覧（スコープラベル・優先度ラベル含む）
   - 重複チェック結果（ヒット件数と代表 issue）
   - 本文全文
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

## Patch release 関連の issue 起票 (#L-γ A2 / M9)

v0.M.N → v0.M.(N+1) の patch release で吸収する issue を起票する場合は、[`docs/release-process.md` §Patch release の Track 構造](../../../docs/release-process.md#patch-release-の-track-構造) (Track A-D 並列化) を参照し、対応する prefix label / scope label を判定:

- **Track A** (security / dependency): prefix `[task]` or `[refactor]`、scope `l2-workflow` (security/CI 系) or 該当 scope
- **Track B** (deferred UX 吸収): `/release` skill Step 0c で (a) 次 release 吸収と判定された issue 群 (新規起票は通常不要、既存 deferred issue が対象)
- **Track C** (CI / build gate): prefix `[task]`、scope `l2-workflow` or `l2-ci`
- **Track D** (version bump + CHANGELOG): `/release` skill が自動生成、`/create-task` は通常使わない

新規起票時に「次 patch で吸収する」と確定済みなら、issue 本文の冒頭にどの Track 候補かを明記すると `/release` Step 0c での分類が容易になる。
