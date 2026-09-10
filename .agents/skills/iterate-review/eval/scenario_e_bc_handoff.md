# シナリオ E: bc_handoff ((B)/(C) handoff + 再 flag 防止)

## 想定状況

PR #906 (mock、複数モジュール touch する複雑 PR) を /iterate-review が dispatch。

- Round 1:
  - (A) 2 件 (本 PR scope 内)
  - (B) 3 件 (別領域 audio module security review、別 layer GUI a11y、外部依存 ffmpeg upgrade、それぞれ 3 条件 AND を満たす)
  - (C) 1 件 (既存 issue #680 と同テーマ)
  - bulk (B) 3 件以上 → AskUserQuestion 1 件 sample + 全件 OK / 個別 / やめる の 3 択
- Round 2: (A) 0 件、(B) 0 件 (前 round で起票済み topic は exclude されて再 flag されない)、(C) 0 件 → 収束

## 期待挙動

- Round 1 (B) 3 件で Iron Law 2 bulk AskUserQuestion 発動
- (B) 起票後 handoff_state に追加、PR body deferred block 更新
- (C) 既存 issue へ gh issue comment + handoff_state 追加
- Round 2 subagent prompt の deferred-list に Round 1 (B)/(C) topic が含まれる → 再 flag されない

## [critical] 項目

1. **[critical]** (B) 3 件で bulk AskUserQuestion 発動
2. **[critical]** (B) 各件が 3 条件 AND 満たすことを確認 (1 条件のみなら (A) に再分類)
3. **[critical]** PR body deferred block が更新される (`<!-- iterate-review:deferred:start --> ... <!-- iterate-review:deferred:end -->`)
4. **[critical]** Round 2 subagent prompt に Round 1 deferred topics が exclusion として渡される
5. **[critical]** 再 flag 防止: Round 2 で同 topic の findings が出ない (subagent が exclusion を尊重)
6. (C) 既存 issue 追記の HEREDOC + body-file - 形式
7. handoff_state に round 番号 + classification + issue_number が記録される
