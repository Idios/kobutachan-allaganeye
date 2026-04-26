# review-pr Step 8 縮小ブラッシュアップ — empirical-prompt-tuning 検証サマリ (#594)

**実施日**: 2026-04-27
**対象**: `.claude/skills/review-pr/SKILL.md` Step 8 (#594 で `/close-issue` 分離 + ハンドオフ専用化)
**参照プロセス**: [mizchi empirical-prompt-tuning SKILL-ja.md](https://github.com/mizchi/skills/blob/main/empirical-prompt-tuning/SKILL-ja.md)
**先行事例**: 本 skill の `summary.md` (#511 改修、6 件構造的欠陥を Iter 1 で全件解消)

> 本ファイルは #594 改修向けの empirical 検証サマリ。#511 改修のサマリは隣接の [`summary.md`](summary.md) を参照。

---

## 全体フロー

```text
Iter 0 (baseline)                       Iter 1 (revaluation)
  ↓ 1 シナリオ dispatch (scenario D)     ↓ 新規 subagent dispatch (scenario D)
  ↓ 不明瞭点 抽出                        ↓ 不明瞭点 抽出 + Iter 0 解消確認
  ↓ (4 件補足追記 X1-X4 が必要と検出)     ↓ (X1-X4 全件解消、新出は MERGED 境界の軽微ケース)
  ↓                                     ↓
  ↓ SKILL.md Step 8 改修 (X1-X4 反映)
                                        収束判定: Iter 1 打ち切り
```

memory `feedback_skill_revision_empirical.md` の打ち切り基準: 構造的欠陥が解消された時点で打ち切り可。Iter 1 で全件解消確認のため、本 #594 改修サイクルは Iter 1 で収束。

---

## Iter 0 → Iter 1 メトリクス比較

| 指標 | Iter 0 | Iter 1 | 変化 |
|---|---|---|---|
| **精度** | 7.5/8 (0.9375) | **8/8 (1.00)** | **+6.25pt** |
| **[critical] 成功率** | 5/5 | 5/5 | 維持 |
| 部分的判定数 | 1 件 (要件 #8 — eval 制約由来) | 0 件 | **解消** |
| tool_uses | 3 | 4 | +33% (X1-X4 改修箇所参照で能動化) |
| duration (実測 ms) | 135,639 | 137,814 | +1.6% (誤差範囲) |
| 新規不明瞭点 件数 | 5 (うち eval 制約由来 1、構造的欠陥 4) | 2 (軽微) | -60% |
| 失敗パターン台帳 件数 | 4 | 0 (新規) + 潜在リスク 1 (軽微) | 構造的失敗ゼロ化 |

精度 0.9375 → 1.00。要件 #8 (`/enforce-acceptance-criteria` 経由の逐条引用) が「部分的」→「○」に昇格。Iter 1 subagent は X4 補足 (issue 番号特定方法) と X3 補足 (MERGED フォールバック) によって PR/issue 整合性確認と Step 7/8 の境界判断を確実に実施できた。

empirical 「収束判定」の参照 (`feedback_skill_revision_empirical.md`):
- 精度改善 +6.25pt (飽和ではなく明確な改善) ✓
- 構造的欠陥: Iter 0 で 4 件検出 → Iter 1 で全件解消 ✓
- 新規不明瞭点: 5 件 → 2 件に減少 (うち 0 件が構造的、2 件が軽微境界) ✓
- 失敗パターン: 4 件 → 0 件 (新規)、潜在リスク 1 件 (軽微) ✓

---

## 構造的不明瞭点 4 件の解消状況 (Iter 0 検出 → Iter 1 全件解消)

| # | Iter 0 不明瞭点 | Iter 1 で効いた改修 (補足追記 X1-X4) | 解消確認 |
|---|---|---|---|
| X1 | 「`gh issue close` を実行しない」の理由接続文が不在 (なぜ close しないかが読者に伝わりにくい) | Step 8 第 3 項に「(= レビュー専用セッション契約に基づく。本 skill 内で close を実行すると、Iron Law 4 が要求する「マージ後の実測再検証」が `/close-issue` ルートを経由しないまま進むことになる)」追加 | 完全解消 (Iter 1 subagent が正確に引用) |
| X2 | ハンドオフコメントの「Step 6 末尾 vs 別 PR コメント」二択の曖昧さ (二重投稿リスク) | Step 8 第 2 項に「**Step 6 のレビュー報告本文末尾に含めることを優先** とする (二重投稿防止)。Step 6 本文末尾に含めた場合は別 PR コメント投稿は省略可」明記 | 完全解消 (Iter 1 subagent は X2 適用で Step 6 統合コメントにハンドオフ含む、別コメントは補足扱いと明示) |
| X3 | マージ済み状態での Step 7 LGTM コメント投稿 vs Step 8 単独ハンドオフのフロー乖離 | Step 8 末尾「マージ済み状態で本 skill が呼ばれた場合のフォールバック」追記 (LGTM 省略可、Step 1-6 検証通常実施、検証結果も同コメントに含める) | 完全解消 (Iter 1 subagent は Step 1 で MERGED 検出 → X3 フォールバック適用) |
| X4 | issue 番号特定方法 (`closingIssuesReferences` or PR 本文 `Refs #N`) | Step 8 第 1 項に「**issue 番号の特定**: `gh pr view --json closingIssuesReferences` で取得、または PR 本文の `Refs #N` / `#N` 参照から抽出する (両方確認して両者の差分があれば AskUserQuestion でユーザー確認)」明記 | 完全解消 (Iter 1 subagent は両者確認、差分なし → AskUserQuestion 不要と判断) |

---

## Iter 1 で新出した不明瞭点 (軽微、deferred)

いずれも MERGED フォールバック (X3) と X2 優先規則の組み合わせ境界で発生する軽微なケース。基本フローへの影響なし。

| # | 不明瞭点 | 性質 | 対応方針 |
|---|---|---|---|
| NQ1 | MERGED フォールバック時の AskUserQuestion 省略可否 | 軽微 (MERGED は事後検証のため省略可と運用で吸収できる) | deferred (本 PR スコープ外) |
| NQ2 | X2 の「優先」規則が MERGED フォールバック時にどう適用されるか (Step 6 統合 vs 別コメント) | 軽微 (Iter 1 subagent は両形式を併記して回避できた) | deferred (本 PR スコープ外) |

### 潜在リスク (Iter 1 検出)

| # | リスク | 対応方針 |
|---|---|---|
| R4 | Step 1 での MERGED 検出 → X3 フォールバック適用のトリガー接続が暗黙的 | deferred (Step 1 末尾に「state == MERGED の場合は Step 8 フォールバック適用」と 1 行追記で解消可能、本 PR では deferred) |

---

## deferred 候補 (本 PR スコープ外、後続 issue で追跡)

NQ1 / NQ2 / R4 は本 PR では解消せず、運用で必要が生じた時点で skill 改善 issue として起票する。優先度は P3-low (軽微 + 構造的欠陥ではない)。

---

## dogfood 適用予定

本 PR (#594) のレビューセッションは、改修済み review-pr SKILL.md (Step 8 ハンドオフ専用化) を初めて dogfood 適用する場となる。レビュー時に Step 8 が新仕様で動作するか実証する機会。

---

## 参考

- [`iter_0_step8_baseline.md`](iter_0_step8_baseline.md) — Iter 0 詳細
- [`iter_1_step8_revaluation.md`](iter_1_step8_revaluation.md) — Iter 1 詳細 (全 4 件解消確認 + 新出 2 件 + 潜在リスク 1 件)
- [`../scenario_d_step8_handoff.md`](../scenario_d_step8_handoff.md) — モックシナリオ D
- [`../requirements.md`](../requirements.md) §シナリオ D — [critical] 付き要件
- [`summary.md`](summary.md) — #511 改修の検証サマリ (先行事例)
- 親 issue: #594 (review-pr の issue クローズ責務分離)
- 関連 skill: [`../../close-issue/eval/reports/summary.md`](../../close-issue/eval/reports/summary.md) — `/close-issue` 新設の検証サマリ
- memory: `feedback_skill_revision_empirical.md`
