# review-pr Iter 0 baseline (Scenario D / Step 8 ハンドオフ検証)

**実施日**: 2026-04-27
**対象 SKILL**: `.claude/skills/review-pr/SKILL.md` (Step 8 を #594 で縮小済み)
**dispatch**: subagent (general-purpose / model: sonnet) × 1 (run_in_background: true)
**シナリオ**: D (LGTM 後 Step 8 ハンドオフ、modal: マージ済み状態)

---

## メトリクス

| 指標 | Scenario D |
|---|---|
| 精度 | 7.5/8 (0.9375) |
| [critical] 成功率 | 5/5 |
| tool_uses | 3 |
| 推論 step 数 | 8 (Step 1-8 全実行) + 集約 |
| duration (subagent self-report) | 45s |
| duration (実測 ms) | 135,639 |
| 不明瞭点 件数 | 5 (うち 1 件は eval 制約由来) |
| 失敗パターン台帳 件数 | 4 |

**[critical] 全 ○ で成功**。ただし要件 #8 (`/enforce-acceptance-criteria` 経由の逐条引用) は eval シナリオ上 mock で代替したため「部分的」判定。これは scenario / requirements 側の調整課題で、SKILL.md 修正では解消しない。

---

## Iter 0 で検出された不明瞭点と修正反映方針

### Iter 1 前に SKILL.md に反映する補足追記 (4 件)

| 修正 # | 不明瞭点 | 対象節 | 反映内容 |
|---|---|---|---|
| X1 | 「レビュー専用セッション契約」と Step 8 縮小の接続文が SKILL.md にない | Step 8 第 2 項 | 「`gh issue close` 実行しない (= レビュー専用セッション契約と整合)」と括弧書き追記 |
| X2 | ハンドオフコメントの「Step 6 末尾 vs 別 PR コメント」二択の曖昧さ | Step 8 第 1 項 | 「Step 6 報告本文末尾に含めた場合は別 PR コメント投稿は省略可」明記、二重投稿防止 |
| X3 | マージ済み状態での Step 7 LGTM コメント投稿フローが不明確 | Step 8 末尾 | 「PR が既にマージ済みの場合のフォールバック」追記。Step 7 LGTM コメント省略 + Step 8 ハンドオフのみ |
| X4 | issue 番号の特定方法 (`closingIssuesReferences` or PR 本文 `Refs #N`) | Step 8 第 1 項冒頭 | 「issue 番号は `gh pr view --json closingIssuesReferences` または PR 本文 `Refs #N` 参照から特定する」明記 |

### eval 側の調整課題 (deferred 候補)

- **不明瞭点 #4**: 要件 #8 「`/enforce-acceptance-criteria` 経由」が eval 制約 (subagent から skill 呼び出しできない) 上で常に「部分的」になりやすい。requirements.md の §シナリオ D #8 を「`/enforce-acceptance-criteria` 呼び出し宣言 + 結果引用 (mock 可)」に緩める形で対応可能。本 PR では deferred 候補として `summary.md` に記録、本 PR スコープ外

### 失敗パターン台帳 (Iter 0 検出、Iter 1 前修正反映候補)

| # | Pattern | 反映先修正 # |
|---|---|---|
| 1 | Step 8 で close を実行してしまう (旧挙動引きずり) | X1 (理由接続文 + Red Flags 表強調) |
| 2 | Step 6 と Step 8 でハンドオフ文を二重投稿 | X2 |
| 3 | `/enforce-acceptance-criteria` 呼び出しを省略して逐条引用を手動代替 | (既存記述 OK、強調のみ) |
| 4 | マージ済み PR に対して LGTM コメントを事後投稿 | X3 |

---

## 次ステップ (Iter 1 前)

1. `.claude/skills/review-pr/SKILL.md` Step 8 に修正 X1-X4 を反映 (本セッション内で実施)
2. **新規 subagent** を 1 件 dispatch して Iter 1 再評価 (memory `feedback_skill_revision_empirical.md` の Red Flag「同じ subagent を使い回そう」回避)
3. Iter 1 で精度向上 + 構造的欠陥候補 4 件すべて解消されているかを確認
4. 残った詳細詰め不足は deferred 候補として `summary.md` に記録
