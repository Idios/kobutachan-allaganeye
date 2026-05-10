# /review-pr post-redesign empirical-prompt-tuning Summary

実施日: 2026-05-XX / session: (session-id)

## 背景

`/review-pr` skill を `/iterate-review` 新規追加と整合させるための改訂 (Tasks 2-7):

- Step 6 AskUserQuestion 4 択 削除
- Step 7 per-finding comment 投稿 全廃
- Step 7a 再レビューラウンド管理 移管 note 化
- Step 8 MERGED state 限定にスリム化
- §G Subagent invocation mode 新設 (G.1 / G.2 / G.2.1 / G.3)
- Red Flags 表整理

## 経過

- iter_0 post-redesign baseline: 85.7% (38/49 [critical], 5 既知 Minor / 3 × 欠落)
  - 4 gaps 抽出 (D / E_edge_mixed / E_edge_doc_only / F)
  - 失敗 scenario: D, E_edge_mixed, F (3/8)
- iter_1 revaluation: 100% (49/49 [critical])
  - 4 gaps すべて解消
  - 全 8 scenario 成功
- iter_2: 不要

## 解消した 4 gaps

| GAP | scenario | iter_0 | iter_1 | 反映方法 |
| --- | --- | --- | --- | --- |
| 1 | D item 4 | × | ○ | Step 8 冒頭に責務分離原則明記 |
| 2 | E_edge_mixed item 1 | × | ○ | Step 5c 末尾「複数 root cause 混在時」追記 |
| 3 | E_edge_doc_only item 2 | △ | ○ | §D 末尾「doc-only PR 旧用語 sweep」追記 |
| 4 | F item 5 | × | ○ | §G.2.1 item 5「(A)*」記法明示 |

## 関連 commit

- iter_0 baseline: `f58da48`
- iter_0 → iter_1 fix: `975189d`
- iter_1 revaluation: `c698801`

## 結論

empirical-prompt-tuning iter_1 で完了。改訂後 /review-pr は新規 /iterate-review との contract (subagent invocation mode 等) を満たす状態に到達。

(既存 reports/iter_0_baseline.md, iter_1_revaluation.md, iter_2_revaluation.md, summary.md は initial review-pr 改修時の historical record として残存)
