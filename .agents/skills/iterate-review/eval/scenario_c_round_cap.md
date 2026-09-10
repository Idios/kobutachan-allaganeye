# シナリオ C: round_cap (Round 5 で cap gate)

## 想定状況

PR #904 (mock) を /iterate-review が dispatch。

- Round 1-4: (A) は減少していくが、毎 round 新出 (A) も増えるため未収束 (例: 残 5 → 4 → 3 → 2)
- Round 5: 残 (A) = 1、しかし新出も 1 件発生し counter は 1
- Round 5 終了で cap 到達 → user gate 発動

## 期待挙動

- Round 5 完了時点で未収束 (= (A)/(B)/(C) any > 0) なら user gate
- AskUserQuestion 2 択 (発散と同じ)
- 「ROUND 6 でもう 1 回」は **不可** (skill 規定)

## [critical] 項目

1. **[critical]** Round 5 で cap 発動
2. **[critical]** 2 択 (発散と共通)
3. **[critical]** Round 6 への進行が **不可**
4. divergence と cap は別 trigger だが gate は同一 (2 択共通)
