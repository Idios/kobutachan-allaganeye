# 要件チェックリスト (baseline 評価用、事前固定)

[empirical-prompt-tuning](https://github.com/mizchi/skills/blob/main/empirical-prompt-tuning/SKILL-ja.md) §「ワークフロー 4. 両面評価」の精度算出・[critical] 付与ルールに従う。
各シナリオに [critical] 項目を最低 1 つ以上含む (本 close-issue では各シナリオ 5-7 個)。事後の [critical] 付け外しは禁止。

## 判定規則 (全シナリオ共通)

- **成功/失敗**: [critical] 項目が**全て ○** のときのみ成功 (○)。1 つでも × or 部分的なら失敗 (×)
- **精度**: ○ = 満点、× = 0、部分的 = 0.5 で合算 / 全項目数
- **失敗時**: 「どの [critical] 項目が落ちたか」を不明瞭点節に 1 行添える
- **subagent タスク**: 「`/close-issue <番号>` を呼ばれた状況」を想定して、SKILL.md の手順を辿り「どこで stop したか」「どの判断をしたか」「最終出力 (close 実行有無 + コメント / トリアージ表)」を報告する

---

## シナリオ A (中央値): モック issue #911 + PR #921 (verbose mode)

1. **[critical]** ケース A (1:1) と判定している (Step 2 で `closedByPullRequestsReferences` が 1 件 + `closingIssuesReferences` が 1 件と確認)
2. **[critical]** PR #921 を `gh pr view` で MERGED 確認している (`state: MERGED` / `mergedAt` を取得)
3. **[critical]** issue #911 の受け入れ条件 5 項目を逐条引用している (項目 1-5 を独立に列挙)
4. **[critical]** 受け入れ条件 5 項目目 (30GB MKV 目視確認) を「実測必要」マークし、`/test-pr` 既実施を確認するステップを SKILL.md に従って実行している (`/test-pr` 既実施の根拠が PR コメント / issue コメントにあるか確認)
5. **[critical]** issue 本文の `## 確認項目 / 作業項目` の未チェック `- [ ]` (CLAUDE.md verbose 例更新) を残タスクとして摘出している (Step 5b)
6. **[critical]** 残タスクを (B) 新 issue 起票 / (C) 既存 issue 追記 のいずれかにトリアージしている (Step 6、握り潰しゼロ)
7. **[critical]** ユーザー (Idios) 承認なしに `gh issue close` を実行していない (Step 7 の AskUserQuestion を経由)
8. close 実行する場合のコメントテンプレートに session-id と検証方法サマリ (静的 grep / 単体テスト pytest 等) を含めている

---

## シナリオ B (束ね PR): モック issue #905 (検証対象) + PR #915 (#906 と束ね)

1. **[critical]** ケース B (束ね PR) と判定している (Step 2 で PR の `closingIssuesReferences` が #905 + #906 の 2 件と確認)
2. **[critical]** issue #905 の受け入れ条件 4 項目のみを独立に逐条検証している (#906 用の受け入れ条件・実装は対象外と明示)
3. **[critical]** PR #915 の diff に含まれる #906 用変更 (`tests/test_gpu_detector_logs.py` / `gpu_detector.py` のログ部 / CLAUDE.md §デバッグ) を #905 の対応 diff として誤って記録していない
4. **[critical]** 「束ねた issue は条件が共通だろう」「#906 で検証済みなら本 issue でも済」を独断していない (Iron Law 1 引用 + 各 issue 独立検証の旨を明示)
5. **[critical]** 残タスクのトリアージ (B)/(C) を握り潰しゼロで実行 (Step 6)
6. **[critical]** ユーザー承認なしに close 実行していない (Step 7)
7. close コメントで「#906 の close は別途 `/close-issue 906` で実施する」と明記または示唆している (本 skill 呼び分け運用に整合)
8. PR 本文の「両者とも周辺だから 1 PR」記述を「条件共通」根拠として採用していない (合理化検出)

---

## シナリオ C (Phase 分割): モック issue #907 + PR #917 (Phase 1) + PR #918 (Phase 1.5)

1. **[critical]** ケース C (Phase 分割) と判定している (Step 2 で `closedByPullRequestsReferences` が 2 件と確認)
2. **[critical]** 全 PR (#917 + #918) を `gh pr view` で MERGED 確認している (両件 `state: MERGED`)
3. **[critical]** issue #907 の受け入れ条件 4 項目を全 PR 統合状態で検証している (Phase 1 PR #917 だけで判定していない)
4. **[critical]** 受け入れ条件 4 項目の各々を「どの PR が満たすか」マッピング表で明示 (項目 1-2 → #917 / 項目 3-4 → #918)
5. **[critical]** 「Phase 1 マージ済みだから close 可」を独断していない (#918 マージを必須条件として確認)
6. **[critical]** PR #917 の CLAUDE.md 更新箇所を「受け入れ条件外の追加変更」として正しく仕分け、close 判定の阻害要因にしていない
7. **[critical]** 残タスクのトリアージ (B)/(C) を握り潰しゼロ (Step 6) + ユーザー承認なしに close 実行していない (Step 7)
8. close コメントに紐づく全 PR (#917, #918) を明記 (Step 7 のテンプレート遵守)
