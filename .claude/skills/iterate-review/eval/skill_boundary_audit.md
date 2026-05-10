# Skill Boundary Audit (post-tuning)

実施日: 2026-05-10 / session: quizzical-goldstine-f91cfb

## 評価対象

- `/iterate-review` SKILL.md (iter_1 後、commit 2a1b48c、367 行)
- `/review-pr` SKILL.md (iter_1 後、commit 975189d、531 行)

## 4 観点 audit 結果

### 1. 冗長判定

**検出: 冗長なし**

責務の分担は以下のとおり明確に定義されている。

| 操作 | 責務 | 根拠 |
| --- | --- | --- |
| PR state/isDraft 確認 | `/iterate-review` Step 0 (orchestrator) | iterate-review SKILL.md 行 32-39 |
| base sync / 直近マージ PR / 並行 worktree PR | `/review-pr` Step 2 (subagent 内) | iterate-review SKILL.md 行 42-43「subagent dispatch 内で実行されることに依拠して再掲しない」 |
| (A) 修正 / commit / push | `/iterate-review` Step 2.4-2.7 (orchestrator) | iterate-review SKILL.md 行 143-209 |
| findings 生成 / トリアージ | `/review-pr` Step 5b (subagent) | review-pr SKILL.md 行 186-245 |
| per-round AskUserQuestion gate | `/iterate-review` Step 2.3 (orchestrator) | iterate-review SKILL.md 行 119-138 |
| 収束/発散/キャップ判定 | `/iterate-review` Step 3 (orchestrator) | iterate-review SKILL.md 行 211-241 |
| summary コメント投稿 | `/iterate-review` Step 4 (orchestrator) | iterate-review SKILL.md 行 249-332 |

`/iterate-review` Step 0 が「base sync は Step 2 へリンクし、subagent dispatch 内で実行されることに依拠して再掲しない」と明示しているため、同一責務の二重記述は発生していない。

### 2. 境界欠落判定

**検出: 欠落なし**

以下の操作について責務の所在を確認した。

| 操作 | 責務の所在 | 根拠 |
| --- | --- | --- |
| (A) 修正後の local check | `/iterate-review` Step 2.4 item 3 | 行 147-151「変更 path に応じた local check」 |
| (B)(C) handoff 後の deferred block update | `/iterate-review` Step 2.5 item 5 / Step 2.6 item 2 | 行 163-177 / 行 199 |
| `divergence_counter` リセット条件 | `/iterate-review` Step 3.2 | 行 219-223「減少 → counter = 0 にリセット」 |
| Round 1 (前 round 不在) の counter 初期値 | `/iterate-review` Step 3.2 | 行 224「counter 初期値 0 のまま」 |
| post-fix 検証 (commit atomicity) | `/iterate-review` Step 2.4 item 4 | 行 152-153「1 round = 1 commit」 |
| 収束後の merge / close handoff | `/iterate-review` Step 5 | 行 334-337 (LGTM 候補通知のみ、merge は user) |
| session crash mid-loop 継続方法 | `/iterate-review` 環境制約 §session crash | 行 342-344 |

すべての state transition に「誰が責任を持つか」が一意に決まっている。

### 3. 重複文章判定

**検出: 許容範囲の重複 1 件 (軽微)**

**(B) trigger 条件記述の重複:**

`/iterate-review` Step 2.5 (行 160) と `/review-pr` §G.2.1 item 3 (行 470) は同内容の 3 条件 AND を記述している。ただし：

- `/iterate-review` Step 2.5 は **orchestrator 側の再確認ステップ** として配置されており、subagent が正しく分類したかを orchestrator 自身が再確認する目的
- `/review-pr` §G.2.1 は **subagent が分類時に参照するルール** として配置

役割が異なるため「同じことを 2 箇所に書いた冗長」ではなく「双方が自分の立場で参照するミラー定義」である。canonical 化によるリスク (一方の更新が他方に伝播しない) を避けるためには、両方に同内容を保持する現状が安全。

**Iron Law / Red Flags 表の重複:**

- `/iterate-review` Red Flags (行 348-359、10 項目) は orchestrator 固有のパターン
- `/review-pr` Red Flags (行 493-511、18 項目) は reviewer 固有のパターン

内容が異なる (orchestrator 視点 vs. reviewer 視点) ため重複ではない。

**結論:** 重複文章として canonical 化が必要な箇所はない。

### 4. 誤誘導判定

**検出: contract 不整合 2 件**

#### 不整合 C1: `(A)*` vs `ambiguous` トークン不一致 (HIGH)

**詳細:**

| 参照箇所 | 記述 |
| --- | --- |
| `/iterate-review` Step 2.1 prompt template 行 74 | 「すべての finding に必ず分類 **(A) / (B) / (C) / ambiguous** のいずれかを付与」 |
| `/iterate-review` Step 2.1 prompt template 行 79 | 「判定に迷う finding は `(A)` を default に置き、ambiguous_judgments に記載」 |
| `/iterate-review` Step 2.2 validation rule 1 (行 108) | 処置列が `(A)` / `(B)` / `(C)` / `ambiguous` のいずれか。空欄等は parse error |
| `/review-pr` §G.2.1 item 5 (行 472) | 「findings_table の処置列に **`(A)*`** と記載し (default は (A))、`ambiguous_judgments` セクションに詳述。findings_table に `ambiguous` **単独で記載することは禁止**」 |

**問題:** subagent (`/review-pr` §G.2.1) は「ambiguous を単独記載禁止、`(A)*` が正式記法」と規定しているが、orchestrator parser (`/iterate-review` Step 2.2 rule 1) は valid tokens として `(A)/(B)/(C)/ambiguous` を列挙しており `(A)*` を明示していない。subagent が `(A)*` を返した場合、parser の rule 1 チェック（「いずれかでなければ parse error」）の解釈次第で誤 parse error になりうる。

さらに `/iterate-review` Step 2.1 prompt template では「`(A)` を default に置き、ambiguous_judgments に記載」と指示しており、`(A)*` 記法についての言及がない。subagent は §G.2.1 で `(A)*` を使うよう指示されるが、prompt template では `(A)` と記載して ambiguous_judgments に書くよう指示されており、動作方針が矛盾している。

**修正方針:**

- `/iterate-review` Step 2.2 validation rule 1 の valid tokens リストに `(A)*` を追加: `(A)` / `(A)*` / `(B)` / `(C)` / `ambiguous` → ただし `(A)*` は ambiguous_judgments セクションとの cross-reference が必須と明記
- `/iterate-review` Step 2.1 prompt template の「判定に迷う finding は `(A)` を default に置き」を「`(A)*` と記載し ambiguous_judgments に詳述」に統一

---

#### 不整合 C2: (B) trigger OR vs AND — standalone vs. subagent の非対称 (MEDIUM)

**詳細:**

| 参照箇所 | 記述 |
| --- | --- |
| `/review-pr` Step 5b (行 195-198) | 「以下の trigger の**いずれか**に該当する課題のみ」として **3 つを OR 列挙**: (1) 別領域・別機能、(2) 大規模リファクタ、(3) **外部依存・側チケット調整が必要** |
| `/review-pr` §G.2.1 item 3 (行 470) | `別領域・別機能` AND `1 セッション超の独立設計が必要` AND `本 PR 同梱で受け入れ条件検証が破綻` の **すべて満たす場合のみ** (B) |
| `/iterate-review` Step 2.2 validation rule 2 (行 109) | 「別領域・別機能 AND 1 セッション超 AND 受け入れ条件検証破綻」**3 条件 AND** への該当言及が必要 |

**問題:** standalone mode で `/review-pr` を利用する場合、`外部依存・側チケット調整が必要` は単独でも (B) trigger として有効 (OR ロジック)。しかし subagent mode では §G.2.1 の AND 条件が適用されるため `外部依存` 単独では (B) にできない。

また orchestrator parser (rule 2) は AND 条件の根拠言及を要求するため、standalone モードで合理的だった `外部依存` 単独の (B) 分類は、subagent mode では validation で parse error になる。この non-symmetric behavior は `/review-pr` の `## 重要` 節 (行 10) で「レビュー専用セッション」と明示されているが、standalone vs. subagent で (B) 判定基準が異なることは明文化されていない。

**修正方針 (軽微):**

- `/review-pr` Step 5b 処置分類説明の冒頭に「subagent mode では §G.2.1 の 3 条件 AND が優先される」旨を 1 行追記
- または `/review-pr` Step 5b の (B) trigger 記述を §G.2.1 と統一 (AND 方式に揃える)

---

#### 確認済みの contract 整合

| contract | 確認結果 |
| --- | --- |
| `__ITERATE_REVIEW_SUBAGENT_MODE__` マーカー文字列 | 両 skill で一致 (iterate-review 行 63 / review-pr 行 447) — clean |
| `/review-pr` §G.3 戻り値 5 セクション順序 | `acceptance_criteria_status → findings_table → ambiguous_judgments → recommendation → meta` (review-pr 行 478-483) と iterate-review Step 2.1 prompt template (行 82-99) で完全一致 — clean |
| `/iterate-review` Step 2.2 validation 項目数 | 5 項目 (行 107-112) — review-pr §G.3 の 5 セクション要件と対応関係整合 — clean |
| spec §3.6 (新設 §G) と実装の一致 | spec §3.6 G.3 戻り値 5 セクション (spec 行 422-429) と review-pr SKILL.md §G.3 (行 477-483) は同一構造 — clean |
| summary template (spec §4.2 と iterate-review Step 4.2) | 内容・構造一致 — clean |

## 修正アクション

| 不整合 | 深刻度 | 修正 skill | 修正内容 |
| --- | --- | --- | --- |
| C1: `(A)*` vs `ambiguous` | HIGH | `/iterate-review` SKILL.md | Step 2.2 rule 1 に `(A)*` を valid token として追加 + Step 2.1 prompt template の ambiguous 記法を §G.2.1 に合わせて `(A)*` に統一 |
| C2: (B) trigger OR vs AND | MEDIUM | `/review-pr` SKILL.md | Step 5b (B) 説明に「subagent mode では §G.2.1 の 3 条件 AND 優先」注記を追加、または (B) trigger を AND 方式に揃える |

**適用タイミング:** 両件とも iter_2 として本 PR 内で修正する。C1 は parse error を引き起こす直接的な contract 不整合のため優先度 HIGH。C2 はドキュメント上の非対称だが、実際の subagent は §G.2.1 (AND) を参照するため動作上の影響は限定的。ただし混乱防止のため同時修正を推奨。

## 結論

audit 終了。境界整合性は **修正必要** (2 件: C1 HIGH + C2 MEDIUM)。

- 観点 1 (冗長): 冗長検出ゼロ — clean
- 観点 2 (欠落): 欠落検出ゼロ — clean
- 観点 3 (重複文章): 許容範囲の重複 1 件 (canonical 化不要と判断) — clean
- 観点 4 (誤誘導): contract 不整合 2 件 (C1 HIGH + C2 MEDIUM) — **修正必要**

iter_2 で C1・C2 を修正し、再確認する。
