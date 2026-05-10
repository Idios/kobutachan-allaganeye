---
name: iterate-review
description: PR 作成後の review-fix ループを subagent dispatch で自動化する。`/review-pr` を fresh subagent で実行し findings を構造化 return させ、主セッションが (A) 修正 / (B)(C) handoff / push / CI wait を行い、Step 5b 表が全ゼロまたは Round 5 / 発散検知まで繰り返す。収束時は summary コメント 1 個を投稿。`/review-pr` の per-finding comment 投稿は本 skill が代替する形で廃止する。
user-invocable: true
argument-hint: <PR番号>
---

PR 作成後の review → fix → review ループを自動化する。指定された PR をレビューと修正のループで収束させ、最終的に summary コメントを投稿する。

## 起動経路 (2 系統)

- **user 手動**: `/iterate-review <PR#>` を Idios が直接 invoke
- **agent 自動**: PR 作成セッション (= 実装した主セッション) が PR 作成完了直後に `/iterate-review <PR#>` を skill として自走呼出。Iron Law 6 Pre-flight 通過後に呼ぶ前提

## 主要フロー (overview)

1. Step 0: Pre-flight (PR open / base sync / 並行 worktree PR)
2. Step 1: ループ初期化 (Round=1, handoff_state=[], findings_history={}, divergence_counter=0)
3. Step 2: Round N 実行 (subagent dispatch → parse → AskUserQuestion → fix/handoff → push → CI wait)
4. Step 3: 判定 (収束 / 発散 / 打ち切り)
5. Step 4: Final summary comment (HEREDOC で投稿、AskUserQuestion 3 択で承認)
6. Step 5: LGTM 候補通知 (user merge → /close-issue handoff)

詳細仕様: [docs/superpowers/specs/2026-05-10-iterate-review-and-review-pr-redesign.md](../../docs/superpowers/specs/2026-05-10-iterate-review-and-review-pr-redesign.md)

