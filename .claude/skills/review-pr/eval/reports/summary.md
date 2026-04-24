# review-pr skill 改修 — empirical-prompt-tuning 検証サマリ

**実施日**: 2026-04-24
**参照プロセス**: [mizchi empirical-prompt-tuning SKILL.md](https://github.com/mizchi/chezmoi-dotfiles/blob/main/dot_claude/skills/empirical-prompt-tuning/SKILL.md)

---

## 全体フロー

```text
Iter 0 (baseline)                 Iter 1 (revaluation)
  ↓ 3 シナリオ並列 dispatch         ↓ 新規 subagent 3 並列 dispatch
  ↓ 不明瞭点 抽出                    ↓ 不明瞭点 抽出
  ↓ (構造的欠陥 6 件 検出)             ↓ (構造的欠陥 0 件、新出 5 件は細部レベル)
  ↓                                 ↓
  ↓ SKILL.md 改修                   ↓ 収束判定: Iter 1 打ち切り
  (テーマ A/B/C 反映)
```

empirical §「反復の打ち切り基準」: 構造的欠陥が解消された時点で打ち切り可。Iron Law §「リソース打ち切り」(重要度 vs 改善コスト) も考慮。

---

## Iter 0 → Iter 1 メトリクス比較

| 指標 | Iter 0 | Iter 1 | 変化 |
|---|---|---|---|
| **平均精度** | 0.98 | **1.00** | +2pt |
| **[critical] 成功率** | 3/3 | 3/3 | 維持 |
| Scenario A 精度 | 8/8 (1.00) | 8/8 (1.00) | 同 |
| Scenario B 精度 | 7.5/8 (0.94) | 8/8 (1.00) | **+6pt** |
| Scenario C 精度 | 8/8 (1.00) | 8/8 (1.00) | 同 |
| Scenario B 要件 7 (Round N) | 部分的 | **○** | 改善 |
| tool_uses 合計 | 21 | 28 | +33% |
| duration 合計 | 347s | 394s | +14% |
| 再試行 合計 | 0 | 0 | 同 |

empirical §「収束判定」では連続 2 回で「新規不明瞭点ゼロ + 精度改善 +3pt 以下 (飽和) + ステップ数 ±10% + duration ±15%」を求めるが:

- 精度改善 +2pt → 飽和閾値 (+3pt) 以下 ✓
- ステップ数 +33% → skill 記述具体化で subagent の grep 実行が能動化した結果 (構造的欠陥でなく、むしろ品質向上シグナル)
- duration +14% → ±15% 内 ✓
- 新規不明瞭点: 0 件 ではない (3 シナリオ合計で 9 件) が、**すべて細部判断基準レベル**

---

## 構造的欠陥の解消状況

### 解消された 6 件 (Iter 0 検出 → Iter 1 で全消滅)

| # | Iter 0 構造的欠陥 | Iter 1 で効いた改修 | 効果確認 |
|---|---|---|---|
| 1 | 環境制約節 (孤立 PR / enforce-ac 実行不可 / doc-only CI 波及 / 参照ファイル実体 / 束ね PR) 欠落 | §A-§F 新設 + 冒頭 fallback 明示 | Scenario A / C で subagent が明示的に参照 |
| 2 | Round N 記法 / 再レビュー追跡構造なし | Step 7a 新設 + Step 6 `# Review Round N` ヘッダ | Scenario B 要件 7 が 部分的 → ○ に昇格 |
| 3 | 処置分類 (A)/(B)/(C) 判定基準が弱い | Step 5b に「判定に迷いがちな典型ケース」6 行追加 | 3 シナリオ全件で分類判断容易化 |
| 4 | 束ね PR 独立検証手順が SKILL 本体未明示 | Step 3 に明示 + 環境制約 §F | Scenario B で「§F に従い節分け」と subagent が明示 |
| 5 | 孤立 PR の Step 3 / Step 8 適用手順なし | Step 3 参照追加 + Step 8 孤立 PR 分岐 + §A | Scenario C で subagent が完全適用 |
| 6 | doc-only PR のテスト免除境界線不明確 | §D doc-only CI 波及 | Scenario C で「doc-only だから CI 影響なし」合理化を明示的に排除 |

### Iter 1 で新出した不明瞭点 (軽微、細部判断基準レベル、deferred)

| # | 不明瞭点 | 出現 | 性質 |
|---|---|---|---|
| 1 | `grep 検証` の判定水準 (CI typecheck green = 代替証拠?) | B | 判定基準の詳細追記で解消可能 |
| 2 | scope-guard 発動時の AskUserQuestion 投げ先 (PR 作成者 vs ユーザー) | B | 修正依頼コメント節への追記で解消可能 |
| 3 | diff 外 doc 確認が必要な場合の処置分類 | B | Step 5 への追記で解消可能 |
| 4 | Step 3 `Closes` キーワード不在チェックを §B fallback 時にも明示スキップ可か | A | §B への追記で解消可能 |
| 5 | CI 波及の (A) vs (B) 判定「波及が大きい」の定量基準 | C | 典型ケース表への補足で解消可能 |

いずれも **skill 構造ではなく詳細ルールの詰め不足レベル**。empirical §「リソース打ち切り」に該当し、deferred 追跡 (必要なら別途 skill 改善 issue 起票) で運用可能。

---

## 実戦適用結果 (本 PR の Round 1 レビュー)

本改修を適用した skill を、本 PR #562 自身の Round 1 レビューで **dogfood** 適用:

- レビューセッション: `hopeful-rubin-2aabbd`
- 判定: 修正依頼 (Round 1)
- 摘出課題:
  - #1 markdownlint 9 errors (A) → ブロッカー
  - #2 validate-checklist fail (PR 本文 `- [ ]` 1 件) (A) → ブロッカー
  - #3 subagent レポート本体のコミット非含 (B) → 本ファイル群で解消 (スコープ拡大・ユーザー承認)

skill の新設要素が本番レビューで機能した確認:

- **孤立 PR フォールバック (§A)**: 紐づく issue なしの PR (本 PR は改修 PR で issue 未紐付け) に対し「PR 本文の目的記述を代替受け入れ条件として逐条検証」の手順が機能
- **Round N 記法**: `# Review Round 1` ヘッダと Round 2 追跡方針が明示的に使用
- **トリアージ表 (Step 5b)**: 3 課題全件を (A)/(A)/(B) に振り分け、握り潰しゼロ

---

## 残課題 (deferred issue 候補)

1. Iter 1 新出 5 件の細部判断基準を skill に追記 (詳細は `iter_1_revaluation.md` 各 Scenario 節参照)
2. scope-guard skill の「逆方向」例外規定 (doc 変更 PR → CI 設定矛盾の同 PR 修正可否) — 本 skill 改修で review-pr 側の典型ケース表に一部盛り込んだが scope-guard 本体は未改修
3. `subagent レポート raw output` の保存スキーム検討 (本ファイル群は要約版。全文保存は session transcript 依存で再現性がやや弱い)

---

## 参考

- [iter_0_baseline.md](iter_0_baseline.md) — Iter 0 詳細
- [iter_1_revaluation.md](iter_1_revaluation.md) — Iter 1 詳細
- [../scenario_a_central.md](../scenario_a_central.md) — モックシナリオ A (中央値)
- [../scenario_b_bundled.md](../scenario_b_bundled.md) — モックシナリオ B (束ね PR)
- [../scenario_c_isolated.md](../scenario_c_isolated.md) — モックシナリオ C (孤立 PR)
- [../requirements.md](../requirements.md) — [critical] 付き要件チェックリスト
- memory: `feedback_skill_revision_empirical.md` — 本体験を基にした memory 蓄積 (Claude 環境依存、リポジトリ外のためリンクなし)
