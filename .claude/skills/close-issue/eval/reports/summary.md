# /close-issue skill 改修 — empirical-prompt-tuning 検証サマリ

**実施日**: 2026-04-27 (Iter 0 / Iter 1) → 2026-04-28 (Iter 2)
**対象**: `.claude/skills/close-issue/SKILL.md` (#594 新設、#607 で `Refs #N` fallback 追加、#606 で eval/reports 構造整理)
**参照プロセス**: [mizchi empirical-prompt-tuning SKILL-ja.md](https://github.com/mizchi/skills/blob/main/empirical-prompt-tuning/SKILL-ja.md)
**先行事例**: `.claude/skills/review-pr/eval/` (#511 関連、Iter 2 まで実行の実績)

---

## 全体フロー

```text
Iter 0 (baseline)              Iter 1 (revaluation)            Iter 2 (revaluation)
  ↓ 3 並列 dispatch              ↓ 新規 subagent 3 並列            ↓ 新規 subagent 3 並列
  ↓ 不明瞭点抽出                  ↓ 構造的欠陥解消確認              ↓ Refs #N fallback 検証
  ↓ (構造的欠陥 7 件 検出)         ↓ (構造的欠陥 7 件 全件解消)        ↓ (新 [critical] 9 全 ○)
  ↓ SKILL.md 改修 (修正 1-7)      ↓ Iter 1 新出 11 件 = deferred    ↓ Iter 2 新出 9 件 = deferred
                                                                    ↓
                                                                    収束: Iter 2 で打ち切り
```

memory `feedback_skill_revision_empirical.md` の打ち切り基準: 構造的欠陥が解消された時点で打ち切り可。Iter 2 で新 [critical] 9 (fallback) も全件 ○、構造的欠陥ゼロのため収束。

---

## Iter 0 → Iter 1 → Iter 2 メトリクス比較

| 指標 | Iter 0 | Iter 1 | Iter 2 | 変化 (0→2) |
| --- | --- | --- | --- | --- |
| **平均精度** | 1.00 | 1.00 | **1.00** | 維持 |
| **[critical] 成功率** | 3/3 | 3/3 | 3/3 | 維持 |
| Scenario A 精度 | 8/8 (1.00) | 8/8 (1.00) | 10/10 (1.00) | 項目数 +2 (新 [critical] 9 + [important] 10) |
| Scenario B 精度 | 8/8 (1.00) | 8/8 (1.00) | 10/10 (1.00) | 同上 |
| Scenario C 精度 | 8/8 (1.00) | 8/8 (1.00) | 10/10 (1.00) | 同上 |
| tool_uses 合計 | 8 | 11 | **10** | -33% (Iter 1→2 で Step 1/2 fallback 手順の systematic 化により判断高速化) |
| duration 合計 (実測 ms) | 352,607 | 457,335 | **305,526** | -33% (Iter 1→2 で同様) |
| 新規不明瞭点 件数 | 14 (構造的欠陥 7 + 詳細不足 7) | 11 (詳細不足のみ) | 9 (詳細不足のみ) | 構造的欠陥ゼロ維持 |

**精度** は全 Iter で全シナリオ満点 (1.00)。改修の主目的は **構造的欠陥 (subagent が「迷う / 独断する」リスク領域) の除去** + **Iron Law 4 (`Closes` 禁止) と整合する fallback ルートの組込み**。

**duration の Iter 1 → Iter 2 で -33%** は、Step 1 / Step 2 fallback サブセクションが bash コマンド例 + dedupe ポリシーまで明示されており、subagent が「迷う」工程を削減できたシグナル。tool_uses も同時に -9% で「能動参照しつつ無駄なく到達」を実現。

---

## 収束判定

- **Iter 0 で検出した構造的欠陥 7 件**: Iter 1 で全件解消確認 (シナリオ A 5 件 / B 2 件 / C 0 件)
- **Iter 2 で追加した新 [critical] 9 (fallback 動作) + [important] 10 (dedupe)**: 3 シナリオ全 ○
- **Iter 1 / Iter 2 新出不明瞭点 (合計 20 件)**: いずれも詳細詰め不足レベル、skill 構造ではない

→ 本 skill 改修サイクルは **Iter 2 で収束**。

---

## deferred 候補 (本 PR スコープ外、後続 issue で追跡可)

### Iter 1 由来 (11 件)

- AskUserQuestion + 実測必要の統合タイミング / `/test-pr` 既実施確認の記録方法 / (B) 起票と close の順序
- テスト関連受け入れ条件の検証方法欄 (Step 4 表) を「Step 5 で決定」と仮判定で書くべきか
- 「実測必要 (要確認)」がある状態での AskUserQuestion タイミング (Step 5 即時 vs Step 7 一括)
- `/test-pr` 実施記録 URL の引用要件 / 束ね PR で「#906 分 diff が #905 動作に非干渉」の確認手順
- ケース C partial MERGED の AskUserQuestion 選択肢明示 / `/test-pr` 記録の最低限要件
- CLAUDE.md 更新が「受け入れ条件あり」ケースで section 粒度分離が複合する状況の eval 不在
- ケース C と B の複合形 (#907 と #908 を共に Phase 分割で close) の境界条件

### Iter 2 由来 (9 件)

- AskUserQuestion 2 段階 (Step 5 + Step 7) のユーザー UX
- PR 本文参照先番号の実在確認のタイミング (Step 5b 内優先順序)
- (B) 起票 vs close の前後関係明文化
- `/test-pr` 既実施確認のコメント取得「不可」と「成功・記録ゼロ件」の区別
- CLAUDE.md セクション粒度分離コマンド例 (`grep -n "^## "`)
- ケース B fallback `grep -oE '#[0-9]+'` のノイズリスク (`Refs` 行優先抽出への補強)
- 「各 PR 本文 `Refs #N` 確認」の手順明示
- ケース C の「全 PR 統合状態」検証方法の表現補強
- mock データの `/test-pr` 記録不在 (mock 追完の余地)

優先度は P3-low (現状運用で機能しており、構造的欠陥ではない)。後続 issue で追跡。

---

## 参考

- [`iter_0_baseline.md`](iter_0_baseline.md) — Iter 0 詳細 (構造的欠陥 7 件 + 失敗パターン台帳 8 件)
- [`iter_1_revaluation.md`](iter_1_revaluation.md) — Iter 1 詳細 (構造的欠陥全件解消、シナリオ A/B/C 個別ブロック)
- [`iter_2_revaluation.md`](iter_2_revaluation.md) — Iter 2 詳細 (Refs #N fallback 検証、新 [critical] 9 全 ○)
- [`../scenario_a_central.md`](../scenario_a_central.md) — モックシナリオ A (中央値 1:1)
- [`../scenario_b_bundled.md`](../scenario_b_bundled.md) — モックシナリオ B (束ね PR)
- [`../scenario_c_phase.md`](../scenario_c_phase.md) — モックシナリオ C (Phase 分割)
- [`../requirements.md`](../requirements.md) — [critical] 付き要件チェックリスト
- memory `feedback_skill_revision_empirical.md` — empirical-prompt-tuning 運用手順
- 親 issue: #594 (review-pr の issue クローズ責務分離)
- Iter 1 反映 PR: #602 / Iter 2 反映 PR: 本 PR (Refs #607 #606)
- 先行事例: `.claude/skills/review-pr/eval/` (#511、Iter 2 まで実行の実績)
