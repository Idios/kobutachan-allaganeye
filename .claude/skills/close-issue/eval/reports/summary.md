# /close-issue skill 改修 — empirical-prompt-tuning 検証サマリ

**実施日**: 2026-04-27
**対象**: `.claude/skills/close-issue/SKILL.md` (新設、#594)
**参照プロセス**: [mizchi empirical-prompt-tuning SKILL-ja.md](https://github.com/mizchi/skills/blob/main/empirical-prompt-tuning/SKILL-ja.md)
**先行事例**: `.claude/skills/review-pr/eval/` (#511 関連)

---

## 全体フロー

```text
Iter 0 (baseline)                 Iter 1 (revaluation)
  ↓ 3 シナリオ並列 dispatch         ↓ 新規 subagent 3 並列 dispatch
  ↓ 不明瞭点 抽出                    ↓ 不明瞭点 抽出 + 構造的欠陥解消確認
  ↓ (構造的欠陥 7 件 検出)             ↓ (構造的欠陥 7 件 全件解消、新出は詳細詰め不足レベル)
  ↓                                 ↓
  ↓ SKILL.md 改修                   ↓ 収束判定: Iter 1 打ち切り
  (修正 1-7 反映)
```

memory `feedback_skill_revision_empirical.md` の打ち切り基準: 構造的欠陥が解消された時点で打ち切り可。Iter 1 で全件解消確認のため、本 skill 改修サイクルは Iter 1 で収束。

---

## Iter 0 → Iter 1 メトリクス比較

| 指標 | Iter 0 | Iter 1 | 変化 |
|---|---|---|---|
| **平均精度** | 1.00 | **1.00** | 維持 |
| **[critical] 成功率** | 3/3 (Scenario 全件) | 3/3 | 維持 |
| Scenario A 精度 | 8/8 (1.00) | 8/8 (1.00) | 同 |
| Scenario B 精度 | 8/8 (1.00) | 8/8 (1.00) | 同 |
| Scenario C 精度 | 8/8 (1.00) | 8/8 (1.00) | 同 |
| tool_uses 合計 | 8 | 11 | +37% (改修箇所参照で能動化) |
| duration 合計 (subagent self-report) | 210s | 393s | +87% (改修確認のため精読時間が増加) |
| duration 合計 (実測 ms) | 352,607 | 457,335 | +30% |
| 新規不明瞭点 件数 | 14 (構造的欠陥 7 + 詳細不足 7) | 11 (詳細詰め不足のみ) | -21% (構造的欠陥ゼロ化) |
| 失敗パターン台帳 件数 | 8 | 6 (Scenario A: 3 / B: 3 / C: 0) | 検出パターンの種類は重複あり |

**精度** は Iter 0 / Iter 1 とも全シナリオで満点 (1.00)。本シナリオ群は要件設計が成熟しており、改修前から要件レベルでは問題なかった。改修の主目的は **構造的欠陥 (subagent が「迷う / 独断する」リスク領域) の除去**。

**duration 増加** は subagent が改修箇所 (新節 / 追記) を能動的に参照したため (tool_uses +37%)。これは Iter 1 が改修内容に「迷わず到達できた」シグナルであり、構造改善の品質向上として記録。

---

## 構造的欠陥 7 件の解消状況 (Iter 0 検出 → Iter 1 で全件解消)

| # | Iter 0 構造的欠陥 | Iter 1 で効いた改修 | 解消確認 (Scenario A/B/C 自己評価) |
|---|---|---|---|
| 1 | session-id 取得方法 (`pwd` 経由) と issue 本文の `作成:` 空欄時のフォールバック | Step 1 末尾「本 skill 実行 session-id の取得」 + 空欄時「言及省略可」明記 | A/B/C 全件「完全解消」 |
| 2 | AskUserQuestion 強制 (Step 7 冒頭の絶対条件) | Step 7 冒頭「重要 (close 実行前の絶対条件)」 + Iron Law 4+5 違反明記 | A/B/C 全件「完全解消」 |
| 3 | CI green は補助根拠扱い、静的検証必須 | Step 5 「CI green の扱い」: 「Iron Law 4 実測再検証の代替にはならない」明記 | A/B/C 全件「完全解消」 |
| 4 | `/test-pr` 既実施記録の取得手順 (PR/issue コメント) とアクセス不可時の AskUserQuestion ルート | Step 5「`/test-pr` 既実施記録の取得とアクセス不可時の対応」3 段フロー (PR コメント → issue コメント → AskUserQuestion) | A/B/C 全件「完全解消」 |
| 5 | 動的検証 vs 実測必要 の判定基準 (slow マーカー / 30 秒目安 / GPU / audio) | Step 5「動的検証 vs 実測必要 の判定基準」境界明示 | A/B/C 全件「完全解消」 |
| 6 | 受け入れ条件外 diff の仕分け (補記欄、close 判定阻害禁止、ファイル内 section 粒度) | Step 4「受け入れ条件外の追加変更の扱い」「ファイル内 section 粒度の分離」明記 | A/B/C 全件「完全解消」 |
| 7 | 参照先 PR/issue の実在確認 + 不在時の (B) 残タスク化 | Step 5b「参照先 PR/issue の実在確認」3 分岐処置明記 | A/B/C 全件「完全解消」 |

**全 7 件解消** ○。

---

## Iter 1 で新出した不明瞭点 (詳細詰め不足、deferred)

いずれも **skill 構造ではなく細部判断基準レベル**。memory「リソース打ち切り」基準で deferred 追跡可能。

### Scenario A 由来 (3 件)

1. AskUserQuestion + 実測必要の統合タイミング (複数保留理由を 1 回にまとめるか別々に発行するか)
2. `/test-pr` 既実施確認の記録方法 (ユーザー口頭「はい」回答だけで OK か、コメント URL 引用必須か)
3. (B) 起票と close の順序の明文化 (close 前に起票完了させるか、close 後でも可か)

### Scenario B 由来 (4 件)

1. テスト関連受け入れ条件の検証方法欄 (Step 4 マッピング表) を「Step 5 で決定」と仮判定で書くべきか
2. 「実測必要 (要確認)」がある状態での AskUserQuestion タイミング (Step 5 即時 vs Step 7 一括)
3. AskUserQuestion 「はい」回答時に `/test-pr` 実施記録の URL を引用する明示要件
4. ケース B で「束ね PR の #906 分 diff が #905 動作に非干渉」の確認手順

### Scenario C 由来 (4 件、本シナリオでは新出 0 件と Iter 1 自己評価したが現実発生候補として記載)

1. ケース C で partial MERGED (途中 PR) の AskUserQuestion 選択肢明示
2. `/test-pr` 既実施記録の最低限要件 (1 行記述で OK か詳細ログ必須か)
3. CLAUDE.md 更新が「受け入れ条件あり」ケースで section 粒度分離が複合する状況の eval 不在
4. ケース C と B の複合形 (#907 と #908 を共に Phase 分割で close する) の境界条件

---

## deferred 候補 (本 PR スコープ外、後続 issue で追跡)

上記新出不明瞭点 11 件は本 PR では解消せず、運用で必要が生じた時点で skill 改善 issue として起票する。優先度は P3-low (現状運用で機能しており、構造的欠陥ではない)。

---

## 参考

- [`iter_0_baseline.md`](iter_0_baseline.md) — Iter 0 詳細 (3 シナリオ + 7 件構造的欠陥検出)
- [`../scenario_a_central.md`](../scenario_a_central.md) — モックシナリオ A (中央値 1:1)
- [`../scenario_b_bundled.md`](../scenario_b_bundled.md) — モックシナリオ B (束ね PR)
- [`../scenario_c_phase.md`](../scenario_c_phase.md) — モックシナリオ C (Phase 分割)
- [`../requirements.md`](../requirements.md) — [critical] 付き要件チェックリスト
- memory `feedback_skill_revision_empirical.md` — empirical-prompt-tuning 運用手順
- 親 issue: #594 (review-pr の issue クローズ責務分離)
- 先行事例: `.claude/skills/review-pr/eval/` (#511 で実施、6 件構造的欠陥を Iter 1 で全件解消の実績)
