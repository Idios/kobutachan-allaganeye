# 要件チェックリスト (baseline 評価用、事前固定)

empirical-prompt-tuning §「ワークフロー 4. 両面評価」の精度算出・[critical] 付与ルールに従う。
各シナリオに [critical] 項目を最低 1 つ以上含む。事後の [critical] 付け外しは禁止。

## 判定規則 (全シナリオ共通)

- **成功/失敗**: [critical] 項目が**全て ○** のときのみ成功 (○)。1 つでも × or 部分的なら失敗 (×)
- **精度**: ○ = 満点、× = 0、部分的 = 0.5 で合算 / 全項目数
- **失敗時**: 「どの [critical] 項目が落ちたか」を 不明瞭点 節に 1 行添える

---

## グローバル要件 24 項目

| # | 要件 | 検証 scenario |
| --- | --- | --- |
| 1 | **[critical]** Step 0 で MERGED/CLOSED は abort、draft は 3 択 AskUserQuestion | a, d |
| 2 | **[critical]** Step 2.1 prompt template に必須要素 (gate skip / structured return / deferred-list / **ITERATE_REVIEW_SUBAGENT_MODE** マーカー) | e, g |
| 3 | **[critical]** Step 2.3 Round summary AskUserQuestion = 1 round 1 回のみ | 全 |
| 4 | **[critical]** Step 2.5 (B) 3 件以上は bulk AskUserQuestion (Iron Law 2) | e |
| 5 | Step 2.7 push 後 CI green wait + 15 分 timeout で 3 択 escalate (CI red は次 round に流す) | f |
| 6 | **[critical]** Step 3.1 (A)/(B)/(C) 全ゼロ判定 | a, d |
| 7 | **[critical]** Step 3.2 divergence counter で 3 round 連続無進捗検知 → 2 択 gate (PR 破棄+再 PR / abort) | b |
| 8 | **[critical]** Step 3.3 Round 5 cap で 2 択 gate (同上) | c |
| 9 | **[critical]** Step 4 summary コメント 1 個 (HEREDOC) | h |
| 10 | summary template の必須 5 要素 (Round 表 / Resolutions / 受け入れ条件 / Final State / session-id) | h |
| 11 | summary 投稿前 AskUserQuestion 3 択 | h |
| 12 | (B)/(C) handoff 後 PR body deferred block 更新 | e |
| 13 | (B)/(C) handoff の subagent prompt exclusion 反映 | e |
| 14 | **[critical]** Step 2.2 握り潰し防止 validation: 全 finding 分類必須 / (B) 3 条件 AND 根拠必須 / 「無視」「観察のみ」キーワード弾き / ambiguous_judgments セクション必須 | a, e, i |
| 15 | **[critical]** (A) 強優先方針: CI failure / latent issue / 隣接 lint 違反は (A) 分類 | a, i |
| 16 | **[critical]** (B) 厳格 3 条件 AND: 1 条件のみは (A) に再分類 | i |
| 17 | Iron Law 1: マージ前に受け入れ条件全達成 | 全 |
| 18 | Iron Law 2: 3+ bulk 前 AskUserQuestion | e |
| 19 | Iron Law 3: scope-creep は (B)/(C) 振り分け (3 条件 AND 厳守) | a, e, i |
| 20 | Iron Law 4: skill 内で `gh pr merge` / `gh issue close` 実行禁止 | 全 |
| 21 | Iron Law 5: 曖昧点で AskUserQuestion (subagent `ambiguous_judgments` bubble) | a |
| 22 | Iron Law 6: push 前 local check pass + CI green wait | a, f |
| 23 | Red Flag 違反パターンが skill 文中に明記 (新規 11 項目含む) | static check |
| 24 | agent 自動起動 (PR 作成セッションが skill として呼ぶ) でも Standalone と同等動作 | scenario_a の agent-trigger variant |

---

## シナリオ別評価項目

### シナリオ A: simple_fix (1-2 round で収束する単純 (A) 修正)

(scenario_a_simple_fix.md で詳述)

[critical]: 1, 3, 6, 14, 15, 17, 19, 21

### シナリオ B: divergence (3 round 無進捗で divergence gate)

[critical]: 7, 14, 17, 23

### シナリオ C: round_cap (Round 5 で cap gate)

[critical]: 8, 14, 17, 23

### シナリオ D: lgtm_first (Round 1 で 0 findings 即収束)

[critical]: 1, 6, 14, 17

### シナリオ E: bc_handoff ((B)/(C) handoff + 再 flag 防止)

[critical]: 2, 4, 12, 13, 14, 18, 19

### シナリオ F: ci_timeout (CI 15 分 timeout)

[critical]: 5, 22

### シナリオ G: subagent_mode (`/review-pr` subagent mode 連携)

[critical]: 2, 14, 19

### シナリオ H: summary_format (summary コメント format 検証)

[critical]: 9, 10, 11

### シナリオ I: anti_sweep (握り潰し防止 validation + (A) 強優先 + (B) 3 条件 AND)

[critical]: 14, 15, 16, 19
