# シナリオ G: subagent_mode (/review-pr subagent mode 連携)

## 想定状況

/iterate-review が Step 2.1 で /review-pr subagent dispatch。本シナリオは /review-pr の subagent mode 動作を /iterate-review 視点で検証 (= 連携の整合性確認)。

詳細: /review-pr eval scenario_f_subagent_mode.md と対称。

## 期待挙動 (連携部分)

- /iterate-review が prompt 内に `__ITERATE_REVIEW_SUBAGENT_MODE__` を埋める
- /review-pr が subagent mode に切り替わり 5 セクション final message を return
- /iterate-review Step 2.2 が parse + validation を pass

## [critical] 項目

1. **[critical]** prompt template に `__ITERATE_REVIEW_SUBAGENT_MODE__` マーカーが含まれる
2. **[critical]** 5 セクション (acceptance_criteria_status / findings_table / ambiguous_judgments / recommendation / meta) で受け取れる
3. **[critical]** ambiguous_judgments セクションが空でも parse 通る
4. /review-pr が gh pr comment を呼ばない
5. handoff_state を prompt に正しく埋める
