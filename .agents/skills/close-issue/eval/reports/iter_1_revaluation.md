# /close-issue Iter 1 再評価レポート

**日時**: 2026-04-27
**対象 skill**: `.claude/skills/close-issue/SKILL.md` (Iter 0 → Iter 1 改修反映後)
**subagent model**: sonnet
**dispatch 方式**: 新規 subagent 3 体を並列 `run_in_background: true` (memory `feedback_skill_revision_empirical.md` Red Flag「同じ subagent を使い回そう」回避)

---

## サマリ

| シナリオ | 精度 | [critical] | tool_uses | duration_ms (実測平均) | 再試行 |
| --- | --- | --- | --- | --- | --- |
| A (中央値 1:1) | 8/8 = 1.00 | 7/7 ○ | ~4 | ~152,500 | 0 |
| B (束ね PR) | 8/8 = 1.00 | 6/6 ○ | ~4 | ~152,500 | 0 |
| C (Phase 分割) | 8/8 = 1.00 | 7/7 ○ | ~3 | ~152,500 | 0 |

**集計値** (`summary.md` 統合計測):

- 平均精度: **1.00** (Iter 0 と維持)
- [critical] 成功率: **3/3** シナリオ全件
- tool_uses 合計: 11 (Iter 0 の 8 から +37%、改修箇所参照で能動化)
- duration 合計 (実測 ms): 457,335 (Iter 0 の 352,607 から +30%、改修確認のため精読時間が増加)
- duration 合計 (subagent self-report): 393s (Iter 0 の 210s から +87%)
- 新規不明瞭点 件数: **11** (詳細詰め不足のみ。Iter 0 の 14 = 構造的欠陥 7 + 詳細不足 7 から **構造的欠陥ゼロ化**)

> Iter 1 は 3 シナリオ別の `agent_id` および個別 duration を `summary.md` 集約形式でしか保持していない (本ファイルへの分離は #606 で実施)。個別シナリオ duration は合計値を 3 分割した推定値。

精度は Iter 0 / Iter 1 とも全シナリオで満点 (1.00)。本シナリオ群は要件設計が成熟しており、改修前から要件レベルでは問題なかった。改修の主目的は **構造的欠陥 (subagent が「迷う / 独断する」リスク領域) の除去**。

duration 増加は subagent が改修箇所 (新節 / 追記) を能動的に参照したため (tool_uses +37%)。これは Iter 1 が改修内容に「迷わず到達できた」シグナルであり、構造改善の品質向上として記録。

---

## シナリオ A (中央値 1:1) — Iter 1

- **agent_id**: 未記録 (summary.md 集約のみ、#606 で個別分離扱い)
- **判定**: close 提案前まで進む。受け入れ条件 5 項目を 4 (静的/動的検証可) + 1 (long-running、`/test-pr` 既実施確認) に分類、参照先 PR #923 不在 → (B) 残タスク化、未消化チェックボックス摘出。Step 7 でユーザー承認待ち
- **変化**: Iter 0 で裁量補完だった「session-id 取得」「`AskUserQuestion` 強制」「CI green の扱い」「`/test-pr` 既実施記録のアクセス不可ルート」「動的検証 vs 実測必要 の判定基準」「受け入れ条件外 diff の仕分け」「参照先実在確認」が、Iter 1 では明示的な節 / 表 を能動参照して判断するようになった

### Iter 0 不明瞭点の解消状況

| Iter 0 不明瞭点 | Iter 1 で効いた改修 | 解消確認 |
| --- | --- | --- |
| session-id 取得方法 (`pwd` 経由) と issue 本文の `作成:` 空欄時のフォールバック | Step 1 末尾「本 skill 実行 session-id の取得」 + 空欄時「言及省略可」明記 | **完全解消** |
| AskUserQuestion 強制 (Step 7 冒頭の絶対条件) | Step 7 冒頭「重要 (close 実行前の絶対条件)」 + Iron Law 4+5 違反明記 | **完全解消** |
| CI green は補助根拠扱い、静的検証必須 | Step 5 「CI green の扱い」: 「Iron Law 4 実測再検証の代替にはならない」明記 | **完全解消** |
| `/test-pr` 既実施記録の取得手順 (PR/issue コメント) とアクセス不可時の AskUserQuestion ルート | Step 5「`/test-pr` 既実施記録の取得とアクセス不可時の対応」3 段フロー (PR コメント → issue コメント → AskUserQuestion) | **完全解消** |
| 参照先 PR/issue の実在確認 + 不在時の (B) 残タスク化 | Step 5b「参照先 PR/issue の実在確認」3 分岐処置明記 | **完全解消** |

### Iter 1 新出不明瞭点 (詳細詰め不足、deferred)

1. AskUserQuestion + 実測必要の統合タイミング (複数保留理由を 1 回にまとめるか別々に発行するか)
2. `/test-pr` 既実施確認の記録方法 (ユーザー口頭「はい」回答だけで OK か、コメント URL 引用必須か)
3. (B) 起票と close の順序の明文化 (close 前に起票完了させるか、close 後でも可か)

---

## シナリオ B (束ね PR) — Iter 1

- **agent_id**: 未記録 (summary.md 集約のみ、#606 で個別分離扱い)
- **判定**: close 提案前まで進む。#905 の受け入れ条件 4 項目を独立検証、#906 用 diff (test_gpu_detector_logs.py / gpu_detector.py ログ部 / CLAUDE.md §デバッグ) は対象外として除外。Step 7 でユーザー承認待ち
- **変化**: Iter 0 で裁量補完だった「動的検証 vs 実測必要 の判定基準」「受け入れ条件外 diff の仕分け」「ファイル内 section 粒度 (CLAUDE.md §GPU モード vs §デバッグ)」が Iter 1 では明示的な境界線で判断

### Iter 0 不明瞭点の解消状況

| Iter 0 不明瞭点 | Iter 1 で効いた改修 | 解消確認 |
| --- | --- | --- |
| 動的検証 vs 実測必要 の判定境界 (slow マーカー / GPU / 30 秒等) | Step 5「動的検証 vs 実測必要 の判定基準」境界明示 | **完全解消** |
| 受け入れ条件外の追加変更 (CLAUDE.md 等) を close 判定からどう仕分けるか | Step 4「受け入れ条件外の追加変更の扱い」「ファイル内 section 粒度の分離」明記 | **完全解消** |

### Iter 1 新出不明瞭点 (詳細詰め不足、deferred)

1. テスト関連受け入れ条件の検証方法欄 (Step 4 マッピング表) を「Step 5 で決定」と仮判定で書くべきか
2. 「実測必要 (要確認)」がある状態での AskUserQuestion タイミング (Step 5 即時 vs Step 7 一括)
3. AskUserQuestion 「はい」回答時に `/test-pr` 実施記録の URL を引用する明示要件
4. ケース B で「束ね PR の #906 分 diff が #905 動作に非干渉」の確認手順

---

## シナリオ C (Phase 分割) — Iter 1

- **agent_id**: 未記録 (summary.md 集約のみ、#606 で個別分離扱い)
- **判定**: close 提案前まで進む。受け入れ条件 4 項目を全 PR 統合状態で検証 (Phase 1 #917 だけでは不可)、項目 1-2 → #917 / 項目 3-4 → #918 のマッピング表を明示。CLAUDE.md +18 行を「受け入れ条件外」として補記欄に分離。Step 7 でユーザー承認待ち
- **変化**: Iter 0 で課題ゼロだったが、改修後は Step 4 のマッピング表説明と Step 5 の境界基準でより systematic に判断するようになった (tool_uses +0、duration 維持)

### Iter 0 不明瞭点の解消状況

本シナリオは Iter 0 で構造的欠陥候補ゼロ件を計上 (失敗パターン台帳 #6 + #8 のみだが既存記述で対応可と判定)。Iter 1 では Step 5 の境界明示と Step 4 マッピング表の補強で systematic な判断ロジックに昇格。

### Iter 1 新出不明瞭点 (現実発生候補、Iter 1 自己評価では新出 0 件、deferred)

1. ケース C で partial MERGED (途中 PR) の AskUserQuestion 選択肢明示
2. `/test-pr` 既実施記録の最低限要件 (1 行記述で OK か詳細ログ必須か)
3. CLAUDE.md 更新が「受け入れ条件あり」ケースで section 粒度分離が複合する状況の eval 不在
4. ケース C と B の複合形 (#907 と #908 を共に Phase 分割で close する) の境界条件

---

## 収束判定

memory `feedback_skill_revision_empirical.md` の打ち切り基準: 構造的欠陥が解消された時点で打ち切り可。Iter 1 で Iter 0 検出の構造的欠陥 7 件が全件解消確認 (シナリオ A 5 件 / B 2 件 / C 0 件) のため、本 skill 改修サイクルは Iter 1 で収束。

Iter 1 で新出した 11 件の不明瞭点は **詳細詰め不足レベル** (skill 構造ではなく細部判断基準)。memory「リソース打ち切り」基準で deferred 追跡可能、本 PR スコープ外 (P3-low)。

---

## 参考

- [`iter_0_baseline.md`](iter_0_baseline.md) — Iter 0 詳細 (3 シナリオ + 7 件構造的欠陥検出 + 8 件失敗パターン台帳)
- [`iter_2_revaluation.md`](iter_2_revaluation.md) — Iter 2 (本 PR の Refs #N fallback 検証)
- [`summary.md`](summary.md) — Iter 0 → Iter 1 → Iter 2 メトリクス比較サマリ
- [`../scenario_a_central.md`](../scenario_a_central.md) — モックシナリオ A (中央値 1:1)
- [`../scenario_b_bundled.md`](../scenario_b_bundled.md) — モックシナリオ B (束ね PR)
- [`../scenario_c_phase.md`](../scenario_c_phase.md) — モックシナリオ C (Phase 分割)
- [`../requirements.md`](../requirements.md) — [critical] 付き要件チェックリスト
- memory `feedback_skill_revision_empirical.md` — empirical-prompt-tuning 運用手順
- 親 issue: #594 (review-pr の issue クローズ責務分離)
- Iter 1 改修反映 PR: #602
- 先行事例: `.claude/skills/review-pr/eval/` (#511 で実施、6 件構造的欠陥を Iter 1 で全件解消の実績)
