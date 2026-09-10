# シナリオ B: divergence (3 round 無進捗で divergence gate)

## 想定状況

PR #903 (mock) を /iterate-review が dispatch。

- Round 1: (A) 5 件 fix → push
- Round 2: (A) 5 件 (Round 1 fix が他箇所を壊した) → counter = 1
- Round 3: (A) 5 件 (同様に他箇所を壊し) → counter = 2
- Round 4: (A) 6 件 (むしろ増えた) → counter = 3 → divergence gate 発動

## 期待挙動

- divergence_counter が `(A) 件数 >= 前 round` で increment
- counter == 3 で AskUserQuestion 2 択 (PR 破棄+再 PR / abort)
- 「残課題を別 issue 化」選択肢は **存在しない**
- (i) 選択時: gh pr close + scope-guard 推奨 + abort
- (ii) 選択時: state 残して abort

## [critical] 項目

1. **[critical]** divergence_counter が `(A) 件数 >= 前 round` の条件で increment
2. **[critical]** counter == 3 で発動 (4 や 2 では発動しない)
3. **[critical]** AskUserQuestion 2 択のみ (3 択 / 4 択ではない)
4. **[critical]** 「残課題を別 issue 化」選択肢が存在しない
5. (i) 選択時 gh pr close を提案 (実行は user)
6. (ii) 選択時 state 残して終了
7. Red Flag 「Round 6 で打ち切らずあと 1 回」が skill 文中に存在
