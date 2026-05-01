# /close-issue Iter 2 再評価レポート

**日時**: 2026-04-28
**対象 skill**: `.claude/skills/close-issue/SKILL.md` (Iter 1 → Iter 2 改修反映後、Refs #607 で `Refs #N` fallback 機能追加)
**subagent model**: sonnet
**dispatch 方式**: 新規 subagent 3 体を並列 `run_in_background: true` (memory `feedback_skill_revision_empirical.md` Red Flag「同じ subagent を使い回そう」回避)

---

## サマリ

| シナリオ | 精度 | [critical] | tool_uses | duration_ms | 再試行 |
| --- | --- | --- | --- | --- | --- |
| A (中央値 1:1) | 10/10 = 1.00 | 8/8 ○ | 4 | 101,763 | 0 |
| B (束ね PR) | 10/10 = 1.00 | 7/7 ○ | 3 | 97,619 | 0 |
| C (Phase 分割) | 10/10 = 1.00 | 8/8 ○ | 3 | 106,144 | 0 |

**集計値**:

- 平均精度: **1.00** (Iter 0 / Iter 1 と維持)
- [critical] 成功率: **3/3** シナリオ全件 (新 [critical] 9 番 = `Refs #N` fallback 動作も全件 ○)
- tool_uses 合計: 10 (Iter 1 の 11 から -9%、改修後の skill 記述が systematic で迷いが減少)
- duration 合計 (実測 ms): 305,526 (Iter 1 の 457,335 から **-33%**、Step 1 fallback / Step 2 ケース B fallback の手順がコマンド例付きで明示されているため subagent の判断が高速化)
- 新規不明瞭点 件数: **9** (詳細詰め不足のみ、構造的欠陥ゼロ)

精度は Iter 0 / Iter 1 / Iter 2 とも全シナリオで満点 (1.00)。Iter 2 では fallback 関連の新 [critical] 9 (各シナリオ最重要項目: Hybrid fallback / ケース B fallback / Phase fallback) が 3 シナリオ全 ○ となり、Iron Law 4 (`Closes` 禁止 → `closedByPullRequestsReferences` 通常空) と整合する skill 動作が確認された。

duration 短縮 (-33%) は改修後の skill 記述 (Step 1 fallback サブセクション / Step 2 各ケース fallback の bash コマンド例) が systematic で、subagent が「迷う」工程を削減できたシグナル。

---

## シナリオ A (中央値 1:1) — Iter 2

- **agent_id**: `a5b4b5c9992a570f5`
- **判定**: close 提案前まで進む。`closedByPullRequestsReferences: []` から Hybrid fallback (timeline API + `gh search prs`) で PR #921 を列挙、`closingIssuesReferences: []` から PR 本文 `Refs #911` 抽出でケース A 確定。受け入れ条件 5 項目を 4 (静的/動的) + 1 (実測必要) に分類、参照先 PR #923 不在 → (B) 残タスク化、未消化チェックボックス摘出。Step 7 で `AskUserQuestion` 発行後 stop
- **変化**: Iter 1 で構造的欠陥ゼロだったが、Iter 2 では新 [critical] 9 + [important] 10 (fallback 関連) も追加で ○。fallback ルートを能動的に経由する判断が systematic に行われた

### Iter 1 で解消済み欠陥の継続確認

| Iter 1 で解消した欠陥 | Iter 2 状態 |
| --- | --- |
| session-id 取得 / 空欄時フォールバック | ○ 維持 (Step 1 末尾の手順を能動参照) |
| `AskUserQuestion` 強制 (Step 7 冒頭) | ○ 維持 (Step 7 で発行、close 未実行で stop) |
| CI green は補助根拠扱い、静的検証必須 | ○ 維持 (静的 grep を各受け入れ条件で実行) |
| `/test-pr` 既実施記録のアクセス不可ルート | ○ 維持 (項目 5 で AskUserQuestion 経由) |
| 参照先 PR/issue の実在確認 + (B) 残タスク化 | ○ 維持 (#923 不在 → (B) 起票方針) |

### Iter 2 で追加検証された fallback 動作

| 新 [critical] / [important] 項目 | 検証結果 |
| --- | --- |
| [critical] 9: Hybrid fallback で PR #921 列挙 | ○ — timeline API (state=closed) + gh search prs (state=merged) を両段実行、search merged を真値採用 |
| [important] 10: dedupe ポリシー明示 | ○ — timeline `closed` は近似情報、search `merged` を真値、PR 番号で重複排除 |

### Iter 2 新出不明瞭点 (詳細詰め不足、deferred)

1. AskUserQuestion の発行タイミングが 2 箇所 (Step 5 `/test-pr` 既実施確認 + Step 7 close 承認) になる場合、ユーザーへの事前告知 UX
2. PR 本文に書かれた参照先番号 (#923) の実在確認をどのタイミングで実施するか (Step 5b 内での優先順序明記の余地)
3. items の (B) 起票を Step 6 で「起票予定」のままにするか Step 7 前に実際に起票するか

---

## シナリオ B (束ね PR) — Iter 2

- **agent_id**: `ab4adebaab31b06ff`
- **判定**: close 保留。Step 1 fallback で PR #915 を列挙、Step 2 ケース B fallback (PR 本文 `Refs #905 #906` 抽出) で 2 件 issue 機械判定 → ケース B 確定。#905 受け入れ条件 4 項目のうち項目 2 (180 分動画 wave=2 確認) が long-running → 実測必要 → `/test-pr` 既実施確認のため AskUserQuestion 発行。Step 7 で「#906 close は別途 `/close-issue 906`」を明記して stop
- **変化**: Iter 1 で解消した「動的検証 vs 実測必要 の境界」「受け入れ条件外 diff の仕分け」「ファイル内 section 粒度」が Iter 2 でも systematic に動作。fallback 関連の新項目も全 ○

### Iter 1 で解消済み欠陥の継続確認

| Iter 1 で解消した欠陥 | Iter 2 状態 |
| --- | --- |
| 動的検証 vs 実測必要 の判定境界 | ○ 維持 (項目 2 を実測必要、項目 1/3/4 を静的+動的に分類) |
| 受け入れ条件外 diff の仕分け | ○ 維持 (#906 用変更を補記欄に分離) |
| ファイル内 section 粒度 (CLAUDE.md §GPU モード vs §デバッグ) | ○ 維持 (§GPU モードのみ #905 対応として参照) |

### Iter 2 で追加検証された fallback 動作

| 新 [critical] / [important] 項目 | 検証結果 |
| --- | --- |
| [critical] 9: ケース B fallback (PR 本文 Refs 抽出) で 2 件 issue 機械判定 | ○ — `gh pr view 915 --json body --jq '.body' \| grep -oE '#[0-9]+' \| sort -u` で `#905, #906` 抽出、ケース B 機械判定 |
| [important] 10: 本 issue (#905) のみ独立検証 | ○ — Step 4 以降で #905 受け入れ条件のみ参照、#906 用変更を混入させていない |

### Iter 2 新出不明瞭点 (詳細詰め不足、deferred)

1. Step 5 における `/test-pr` 実施記録確認の「コメント取得不可」扱いと「コメント取得成功・記録ゼロ件」の区別が SKILL.md でやや曖昧 (現状 `AskUserQuestion` 経由で両方カバーできるが、ケース別記述の余地)
2. CLAUDE.md の同時更新に対するセクション粒度分離の具体コマンド (`grep -n "^## " CLAUDE.md`) を SKILL.md に 1 行追記すると誤適用を防ぎやすい
3. Step 2 ケース B fallback の `grep -oE '#[0-9]+'` ノイズリスク — PR 本文内の `#123 のようなコードサンプル` も抽出される潜在性。`Refs` 行を優先抽出する形 (`grep -oE 'Refs (#[0-9]+ ?)+' | grep -oE '#[0-9]+'`) への補強の余地

---

## シナリオ C (Phase 分割) — Iter 2

- **agent_id**: `a9906227e097a5c94`
- **判定**: close 提案前まで進む。Step 1 fallback で PR 2 件 (#917, #918) を timeline API + search の両段で取得、search merged を真値採用。両 PR を `gh pr view` ループで MERGED 確認 → ケース C 確定。受け入れ条件 4 項目を全 PR 統合状態 (`origin/develop-0.2.0`) で検証、PR #917 の CLAUDE.md +18 を補記欄分離。Step 7 で `AskUserQuestion` 発行 (close コメントテンプレに #917 + #918 明記) して stop
- **変化**: Iter 1 で構造的欠陥ゼロだったが、Iter 2 では fallback 経由の PR 件数取得が systematic に行われ、`closedByPullRequestsReferences` 空 → 即「PR なし」の即断回避 + 「Phase 1 マージで close 可」の独断回避が両立した

### Iter 1 で解消済み欠陥の継続確認

| Iter 1 で解消した欠陥 / Iter 0 で課題ゼロ判定 | Iter 2 状態 |
| --- | --- |
| 動的検証 vs 実測必要 の判定境界 | ○ 維持 (項目 1-4 を静的/動的に分類) |
| 受け入れ条件外 diff の仕分け (CLAUDE.md +18 補記欄) | ○ 維持 (Step 4 補記欄で分離) |
| 全 PR の MERGED 確認ループ | ○ 維持 (#917 + #918 を両方 `gh pr view`) |

### Iter 2 で追加検証された fallback 動作

| 新 [critical] / [important] 項目 | 検証結果 |
| --- | --- |
| [critical] 9: Step 1 fallback の timeline API で PR 2 件列挙 + 各 PR 本文 `Refs #907` 確認 | ○ — timeline API レスポンス {917, 918} + search レスポンス両件 merged 確認、ケース C 機械判定の根拠を fallback 由来として明示 |
| [important] 10: 全 PR MERGED 確認に fallback 取得一覧を使い、ループで 1 件ずつ確認 | ○ — fallback 取得 [#917, #918] を Step 3 で 1 件ずつ `gh pr view` で MERGED 確認 |

### Iter 2 新出不明瞭点 (詳細詰め不足、deferred)

1. 「各 PR 本文 `Refs #N` 確認」の手順が SKILL.md に明示されていない (Step 1 fallback の第 1 段は cross-referenced-event の PR 列挙だが、各 PR 本文での `Refs #N` 検証ステップが暗黙)
2. ケース C で受け入れ条件が PR 間で分散している場合の「全 PR 統合状態」検証方法の表現補強 (Step 5 の `git log` だけでは Step 4 → Step 5 の橋渡しがやや暗黙)
3. mock データの `/test-pr` 記録不在 (詳細詰めの余地、本 PR スコープ外)

---

## 収束判定

memory `feedback_skill_revision_empirical.md` の打ち切り基準: 構造的欠陥が解消された時点で打ち切り可。Iter 2 で:

- 新 [critical] 9 (fallback 動作) が 3 シナリオ全 ○
- 既存 [critical] 全 ○ 維持 (Iter 1 で解消した 7 件構造的欠陥が後退していない)
- 新出不明瞭点 9 件はいずれも詳細詰め不足レベル (skill 構造ではなく細部判断基準)

→ **本 skill 改修サイクル (Iter 2) は収束**。

新出不明瞭点 9 件は **deferred 候補** として後続 issue で追跡可能 (P3-low、現状運用で機能しており構造的欠陥ではない)。

---

## 参考

- [`iter_0_baseline.md`](iter_0_baseline.md) — Iter 0 詳細 (3 シナリオ + 7 件構造的欠陥検出 + 8 件失敗パターン台帳)
- [`iter_1_revaluation.md`](iter_1_revaluation.md) — Iter 1 詳細 (構造的欠陥 7 件全件解消)
- [`summary.md`](summary.md) — Iter 0 → Iter 1 → Iter 2 メトリクス比較サマリ
- [`../scenario_a_central.md`](../scenario_a_central.md) — モックシナリオ A (中央値 1:1)
- [`../scenario_b_bundled.md`](../scenario_b_bundled.md) — モックシナリオ B (束ね PR)
- [`../scenario_c_phase.md`](../scenario_c_phase.md) — モックシナリオ C (Phase 分割)
- [`../requirements.md`](../requirements.md) — [critical] 付き要件チェックリスト ([critical] 9 + [important] 10 を Iter 2 で追加)
- memory `feedback_skill_revision_empirical.md` — empirical-prompt-tuning 運用手順
- 親 issue: #594 (review-pr の issue クローズ責務分離) / #602 (Iter 0/1 反映 PR)
- Iter 2 改修反映 PR: 本 PR (Refs #607 #606)
- 先行事例: `.claude/skills/review-pr/eval/` (#511 で実施、Iter 2 まで実行の実績)
