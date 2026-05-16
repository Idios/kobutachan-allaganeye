# シナリオ D: lgtm_first (Round 1 で 0 findings、即収束)

## 想定状況

PR #905 (mock、軽微な doc 修正) を /iterate-review が dispatch。

- Round 1: subagent が `findings_table` 空、`recommendation = LGTM` を返す
- 受け入れ条件: 全 ✓
- 即 Step 4 へ

## 期待挙動

- Round 1 で (A)/(B)/(C) all 0 検出 → Step 3.1 → Step 4
- Round 2 を回さない (1 round で完結)
- summary template の Findings by Round 表は 1 行のみ ((R) 行)
- 投稿後 Step 5 で LGTM 候補通知

## [critical] 項目

1. **[critical]** 0 findings 即収束 (Round 2 回さない)
2. **[critical]** summary 投稿は実施 (skip しない、ただし AskUserQuestion 3 択は確認)
3. summary template Findings by Round 表が 1 行で OK
4. Step 5 で /close-issue 案内
