# シナリオ A: simple_fix (1-2 round で収束する単純 (A) 修正)

## 想定状況

PR #902 (Refs シナリオ A from review-pr/eval/) を /iterate-review が dispatch。Round 1 で subagent が以下を返す:

- (A) #1: `audio/scan.py:42` ruff E501 line length (Step 2.4 で fix)
- (A) #2: `cli.py:105` log format `[%s]` → `<%s>` 統一 (Step 2.4)
- (A) #3: `docs/cli-spec.md` 出力例追加 (Step 2.4)
- 受け入れ条件: 全 ✓
- ambiguous: なし

Round 2 で再 dispatch すると 0 findings、収束。

## 期待挙動

- Step 0 で PR open 確認、Step 1 で初期化
- Step 2.1 で fresh subagent dispatch (prompt template 通り)
- Step 2.2 で findings parse + validation pass (全 finding 分類済み)
- Step 2.3 で Round 1 summary AskUserQuestion (proceed)
- Step 2.4 で 3 件 (A) を 1 commit に集約
- Step 2.7 で push + CI green wait
- Round 2: 0 findings → Step 4 へ
- Step 4 で summary 投稿前 AskUserQuestion 3 択 → 投稿
- Step 5 で LGTM 候補通知 + /close-issue 案内

## [critical] 項目

1. **[critical]** Round summary AskUserQuestion が 1 round 1 回のみ
2. **[critical]** 1 round = 1 commit (3 件 (A) を 1 commit にまとめる)
3. **[critical]** Step 2.2 validation で全 finding 分類確認
4. **[critical]** (A) 強優先で他に CI / latent issue があった場合も (A) に分類
5. **[critical]** Step 4 summary 投稿前 AskUserQuestion 3 択
6. **[critical]** Step 5 で gh pr merge / gh issue close を実行しない
7. agent 自動起動 variant: `/iterate-review 902` を agent が PR 作成後に呼んだケースでも上記と同じ動作
8. CI green wait timeout 15 分以内に終了する mock 設定
