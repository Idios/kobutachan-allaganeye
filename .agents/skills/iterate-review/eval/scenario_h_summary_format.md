# シナリオ H: summary_format (summary コメント format 検証)

## 想定状況

PR #908 (mock、3 round で収束、各 round で findings がある) を /iterate-review が処理。Step 4 で summary 投稿。

- Round 1: (A) 3 件、(B) 1 件
- Round 2: (A) 1 件
- Round 3: 0 件 (収束)
- summary template に従い 1 PR コメント投稿

## 期待挙動

- Step 4 で summary template に従い markdown 生成
- 投稿前 AskUserQuestion 3 択 (投稿 / 微調整 / skip)
- HEREDOC + `--body-file -` で投稿
- Round 詳細を `<details>` で折り畳み (Round 数 ≥ 3 で trigger)
- topic 文字数制限 (30 / 50 字) 適用

## [critical] 項目

1. **[critical]** summary template の必須 5 要素 (Findings by Round / Resolutions / 受け入れ条件 / Final State / session-id)
2. **[critical]** 投稿前 AskUserQuestion 3 択
3. **[critical]** HEREDOC + `--body-file -` (UTF-8 対策)
4. Round 数 ≥ 3 で `<details>` 折り畳み trigger
5. topic 文字数制限 (30 / 50 字)
6. (B) handoff = #N (新規) / (C) handoff = #N (既存) と表記
7. session-id が末尾に `[<session-id>]` として記載
