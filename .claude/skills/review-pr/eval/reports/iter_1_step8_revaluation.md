# review-pr Iter 1 revaluation (Scenario D / Step 8 ハンドオフ検証)

**実施日**: 2026-04-27
**対象 SKILL**: `.claude/skills/review-pr/SKILL.md` (Iter 0 後に Step 8 補足追記 X1-X4 を反映済み)
**dispatch**: 新規 subagent (general-purpose / model: sonnet) × 1 (run_in_background: true)
**シナリオ**: D (LGTM 後 Step 8 ハンドオフ、modal: マージ済み状態)

---

## メトリクス

| 指標 | Iter 0 | Iter 1 | 変化 |
|---|---|---|---|
| 精度 | 7.5/8 (0.9375) | **8/8 (1.00)** | +6.25pt |
| [critical] 成功率 | 5/5 | 5/5 | 維持 |
| tool_uses | 3 | 4 | +33% (X1-X4 改修箇所参照で能動化) |
| 推論 step 数 | 8 + 集約 | 8 + 集約 + Iter 0 解消確認 | 微増 |
| duration (subagent self-report) | 45s | (推論主体) | — |
| duration (実測 ms) | 135,639 | 137,814 | +1.6% (誤差範囲) |
| 新規不明瞭点 件数 | 5 (うち eval 制約由来 1) | 2 (軽微、deferred) | -60% |
| 失敗パターン台帳 件数 | 4 | 0 (新規) + 潜在リスク 1 (軽微) | 構造的失敗ゼロ化 |

**精度向上 +6.25pt** (要件 #8 が「部分的」→「○」に昇格)。これは X4 補足 (issue 番号特定方法) と X3 補足 (MERGED フォールバック) によって、subagent が `/enforce-acceptance-criteria` 経由の逐条引用と PR/issue 整合性確認を確実に実施できたため。

---

## Iter 0 不明瞭点 4 件 (X1-X4) の解消状況

| # | Iter 0 不明瞭点 | Iter 1 解消状況 | SKILL.md 上の参照箇所 | Iter 1 subagent の活用 |
|---|---|---|---|---|
| X1 | Step 8 第 3 項に「(= レビュー専用セッション契約に基づく)」理由接続文がなかった | **解消** | Step 8 第 3 項: 「= レビュー専用セッション契約に基づく。本 skill 内で close を実行すると、Iron Law 4 が要求する「マージ後の実測再検証」が `/close-issue` ルートを経由しないまま進むことになる」 | Step 8 で正しく引用 |
| X2 | ハンドオフコメントの「Step 6 末尾 vs 別 PR コメント」二択の曖昧さ (二重投稿リスク) | **解消** | Step 8 第 2 項: 「**Step 6 のレビュー報告本文末尾に含めることを優先** とする (二重投稿防止)。Step 6 本文末尾に含めた場合は別 PR コメント投稿は省略可」 | X2 適用で Step 6 統合コメント末尾にハンドオフ含む、別コメントは補足扱いと明示 |
| X3 | マージ済み状態での Step 7 LGTM コメント投稿 vs Step 8 単独ハンドオフのフロー乖離 | **解消** | Step 8 末尾「マージ済み状態で本 skill が呼ばれた場合のフォールバック」: Step 7 LGTM 省略可、Step 1-6 検証は通常通り、検証結果も同コメントに含める | Step 1 で `state: MERGED` 検出 → X3 フォールバック適用 |
| X4 | issue 番号特定方法 (`closingIssuesReferences` or PR 本文 `Refs #N`) | **解消** | Step 8 第 1 項: 「**issue 番号の特定**: `gh pr view --json closingIssuesReferences` で取得、または PR 本文の `Refs #N` / `#N` 参照から抽出する (両方確認して両者の差分があれば AskUserQuestion でユーザー確認)」 | Step 8 第 1 項で両者確認、差分なし → AskUserQuestion 不要と判断 |

**全 4 件解消** ○。

---

## Iter 1 で新出した不明瞭点 (軽微、deferred)

| # | 不明瞭点 | 性質 | 対応方針 |
|---|---|---|---|
| NQ1 | MERGED フォールバック時の AskUserQuestion 省略可否 | 軽微。「ユーザー承認後コメント投稿」vs「直接投稿」の境界 | deferred (MERGED は事後検証なので AskUserQuestion 省略可と運用で吸収可) |
| NQ2 | X2 の「優先」規則が MERGED フォールバック時にどう適用されるか (Step 6 統合 vs 別コメント) | 軽微。MERGED + X2 組み合わせの境界ケース | deferred (Iter 1 subagent は両形式を併記して回避済み、運用上は「同一コメント統合」で問題なし) |

両件とも「MERGED フォールバック × X2 優先規則」の境界ケース。基本フローには影響しない。

---

## 潜在リスク (Iter 1 検出、deferred)

| # | リスク | 評価 |
|---|---|---|
| R4 | Step 1 での MERGED 状態検出 → X3 フォールバック適用のトリガー接続が暗黙的 | 軽微残存。Step 1 末尾に「state == MERGED の場合は Step 8 フォールバックを適用」と 1 行追記すれば解消可能 |

---

## 収束判定

memory `feedback_skill_revision_empirical.md` の打ち切り基準:
- 構造的欠陥 (新節欠落・判定基準不在レベル) が解消された時点で打ち切り可
- 残る細部不明瞭点は deferred issue として追跡

判定: **Iter 1 で打ち切り**。

- Iter 0 不明瞭点 4 件 (X1-X4) → 全件解消
- Iter 1 新出 2 件 (NQ1, NQ2) + 潜在リスク 1 件 (R4) → 全て軽微 + 詳細詰め不足レベル → deferred
- 精度 1.00 / [critical] 全 ○ / CI green / 構造的欠陥ゼロ

本 #594 改修の Step 8 縮小に対する empirical-prompt-tuning は Iter 1 で収束。

---

## 参考

- [`iter_0_step8_baseline.md`](iter_0_step8_baseline.md) — Iter 0 詳細 (5 件不明瞭点 → 4 件 SKILL.md 反映 + 1 件 eval 制約由来)
- [`../scenario_d_step8_handoff.md`](../scenario_d_step8_handoff.md) — モックシナリオ D (LGTM 後 Step 8 ハンドオフ検証)
- [`../requirements.md`](../requirements.md) §シナリオ D — [critical] 付き要件
- 親 issue: #594 (review-pr の issue クローズ責務分離)
- memory: `feedback_skill_revision_empirical.md`
