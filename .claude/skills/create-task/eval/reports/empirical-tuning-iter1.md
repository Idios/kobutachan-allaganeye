# create-task SKILL.md empirical-prompt-tuning Iter 1 (baseline)

session-id: eloquent-kalam-0196f5
protocol: <https://github.com/mizchi/skills/tree/main/meta/empirical-prompt-tuning>

## Iter 1 結果 (5 scenarios fresh subagent 並列 dispatch、model: sonnet)

| Scenario | Success | Accuracy | tool_uses | duration_ms | retries | weak phase | unclear points |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A (bug 起票) | ○ | 100% (5/5 [critical] ○) | 14 | 94,774 | 0 | all OK | 1 (operational) |
| B (patch task) | ○ | 100% (7/7 [critical] ○) | 21 | 134,866 | 0 | all OK | 0 |
| C (deferred task) | ○ | 100% (7/7 [critical] ○) | 9 | 85,208 | 0 | all OK | 2 (workflow success: dup detected) |
| D (refactor) | ○ | 100% (7/7 [critical] ○) | 21 | 122,797 | 0 | all OK | 2 (scope label clarity, dup detected) |
| E (risk) | ○ | 100% (7/7 [critical] ○) | 9 | 84,655 | 0 | all OK | 1 (mock severity discrepancy) |

**集計**: 全 5 scenarios で [critical] 全 ○。`tool_uses` 範囲 9-21 (約 2.3x、mizchi が問題視する 3-5x には届かず正常)。duration 範囲 84-135 sec。

## 構造化 reflection (unclear points 分類)

### SKILL.md-actionable (改修候補)

- **A-UP1: label 存在 pre-check 不在**
  - Issue: A scenario subagent が `--label "l1-cli"` を使うが、当該ラベルが GitHub repo に存在するかは未確認 (gh label list を呼ばない)
  - Cause: SKILL.md 手順 4 (重複チェック) と 手順 6 (gh issue create) の間に label 存在確認 step がない
  - General Fix Rule: scope label を `--label` 指定する前に `gh label list --repo ... | grep <label>` で存在確認、未作成なら `gh label create` を先行
  - Status: Iter 2 で要修正?

### 非 SKILL.md (workflow success / mock issue / executor 自己解決)

- **C-UP1: L4 scope label の有無** — issue-policy.md が title prefix 規約で識別と明言、executor が正しく解釈、SKILL.md 側変更不要
- **C-UP2: #125 duplicate 検出** — workflow が正しく機能した結果、SKILL.md 手順 5 は AskUserQuestion で重複時の選択肢提示を既に規定
- **D-UP1: l2a-gui scope label の根拠** — executor 自身が解決 (path↔scope 表参照)
- **D-UP2: l1-residual dual-label 不要** — executor 自身が解決 (起源カテゴリ判定)
- **D 重複検出: #742** — 本 plan の trigger となった issue を skill が正しく検出。workflow success
- **E-UP1: severity 表記 (シナリオ "high" vs リポジトリ "medium")** — eval mock の不整合。SKILL.md 側に問題なし

## 収束判定

mizchi 規範: 2 consecutive clears (new unclear=0 + accuracy +3pt 以下 + step ±10% + duration ±15%) で convergence。

Iter 1 baseline 評価:

- 新 unclear points: **1 件 (A-UP1)**。SKILL.md actionable
- accuracy: 100% (改善余地ゼロ、+0pt)
- step / duration variation: baseline のため前 iter 比較なし

判定:

- [critical] 全 ○ 達成 (= ship-ready bar 通過)
- ただし 1 unclear point (A-UP1) が SKILL.md-actionable で残存
- mizchi 厳密適用なら Iter 2 で A-UP1 fix → 再 dispatch で 0 unclear 確認 → Iter 3 で 2 連続 clear 確認

**Resource cutoff 判断 (mizchi 認容)**: A-UP1 は operational nice-to-have で [critical] 違反ではない。skill の core deliverable (preamble 必須化 / 重複検出 / template 遵守) は全 5 scenarios で実証済み。Iter 2 で 1 line 追記 → 5 subagent 再 dispatch のコストは improvement size (99→100点 領域) に見合わない。

ただし A-UP1 fix 自体は短く完全 deterministic なので**追加コスト無しで実施可能**。次セクションで Iter 2 fix を minimal 1-line addition として実施し、subagent 再 dispatch は行わず hold-out check で代替検証する。
