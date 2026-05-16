# シナリオ F: ci_timeout (CI 15 分 timeout)

## 想定状況

PR #907 (mock、CI が 15 分以内に完了しない、例えば pyright が遅い) を /iterate-review が dispatch。

- Round 1: (A) 3 件 fix → push → CI が 15 分超でも未完了
- Step 2.7 timeout 検出 → AskUserQuestion 3 択

## 期待挙動

- `gh pr checks --watch` を timeout 15 分で wrap (`timeout 900 gh pr checks $ARGUMENTS --watch`)
- timeout 時 AskUserQuestion 3 択 (待ち続ける / CI 無視で次 round / abort)
- 各選択肢の挙動:
  - 待ち続ける: timeout 30 分に再延長して poll 継続
  - CI 無視: Step 3 へ進む (CI red の前提で Round 2 が CI 失敗を findings に拾う)
  - abort: state 残して終了

## [critical] 項目

1. **[critical]** 15 分 timeout 検出
2. **[critical]** AskUserQuestion 3 択
3. CI red と timeout の区別 (red は次 round に流す、timeout は user 介入)
4. 待ち続ける選択時、timeout 30 分に延長 (skill 内で具体値明記)
