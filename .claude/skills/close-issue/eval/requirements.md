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

1. **[critical]** ケース A (1:1) と判定している (Step 2 で 1 PR (Step 1 取得) + 1 issue (`closingIssuesReferences` または PR 本文 `Refs #911` 抽出) と確認)
2. **[critical]** PR #921 を `gh pr view` で MERGED 確認している (`state: MERGED` / `mergedAt` を取得)
3. **[critical]** issue #911 の受け入れ条件 5 項目を逐条引用している (項目 1-5 を独立に列挙)
4. **[critical]** 受け入れ条件 5 項目目 (30GB MKV 目視確認) を「実測必要」マークし、`/test-pr` 既実施を確認するステップを SKILL.md に従って実行している (`/test-pr` 既実施の根拠が PR コメント / issue コメントにあるか確認)
5. **[critical]** issue 本文の `## 確認項目 / 作業項目` の未チェック `- [ ]` (CLAUDE.md verbose 例更新) を残タスクとして摘出している (Step 5b)
6. **[critical]** 残タスクを (B) 新 issue 起票 / (C) 既存 issue 追記 のいずれかにトリアージしている (Step 6、握り潰しゼロ)
7. **[critical]** ユーザー (Idios) 承認なしに `gh issue close` を実行していない (Step 7 の AskUserQuestion を経由)
8. close 実行する場合のコメントテンプレートに session-id と検証方法サマリ (静的 grep / 単体テスト pytest 等) を含めている
9. **[critical]** `closedByPullRequestsReferences` 空の状態から Step 1 fallback (`gh api repos/.../issues/911/timeline` cross-referenced-event + `gh search prs '"Refs #911"'`) を経由して PR #921 を列挙している (両 fallback 段の挙動を明示的に言及。`closedByPullRequestsReferences` 空 → 「PR なし」の即断は失格)
10. **[important]** Hybrid fallback の dedupe ポリシーを明示している (timeline の `state==closed` と search の `state==merged` が両方ヒットした場合は search の `merged` を真値として採用、または PR 番号で重複排除)

---

## シナリオ B (束ね PR): モック issue #905 (検証対象) + PR #915 (#906 と束ね)

1. **[critical]** ケース B (束ね PR) と判定している (Step 2 で PR #915 が 2 issue (`closingIssuesReferences` または PR 本文 `Refs #905 #906` 抽出) を close する束ね PR と確認)
2. **[critical]** issue #905 の受け入れ条件 4 項目のみを独立に逐条検証している (#906 用の受け入れ条件・実装は対象外と明示)
3. **[critical]** PR #915 の diff に含まれる #906 用変更 (`tests/test_gpu_detector_logs.py` / `gpu_detector.py` のログ部 / CLAUDE.md §デバッグ) を #905 の対応 diff として誤って記録していない
4. **[critical]** 「束ねた issue は条件が共通だろう」「#906 で検証済みなら本 issue でも済」を独断していない (Iron Law 1 引用 + 各 issue 独立検証の旨を明示)
5. **[critical]** 残タスクのトリアージ (B)/(C) を握り潰しゼロで実行 (Step 6)
6. **[critical]** ユーザー承認なしに close 実行していない (Step 7)
7. close コメントで「#906 の close は別途 `/close-issue 906` で実施する」と明記または示唆している (本 skill 呼び分け運用に整合)
8. PR 本文の「両者とも周辺だから 1 PR」記述を「条件共通」根拠として採用していない (合理化検出)
9. **[critical]** `closingIssuesReferences` 空の状態から Step 2 ケース B fallback (PR #915 本文の `Refs #905 #906` を `gh pr view 915 --json body --jq '.body' | grep -oE '#[0-9]+' | sort -u` 等で抽出) を経由して #905, #906 の 2 件を列挙し、束ね PR (ケース B) と機械判定している (`closingIssuesReferences` 空 → ケース A 即断は失格)
10. **[important]** PR 本文 `Refs #N` 抽出ルートで取得した issue 一覧に対し、本 issue (#905) のみ独立検証していることを明示 (#906 用変更を本 issue 検証に混入させていない)

---

## シナリオ C (Phase 分割): モック issue #907 + PR #917 (Phase 1) + PR #918 (Phase 1.5)

1. **[critical]** ケース C (Phase 分割) と判定している (Step 2 で 2 PR (Step 1 取得) が同一 issue を close する Phase 分割と確認)
2. **[critical]** 全 PR (#917 + #918) を `gh pr view` で MERGED 確認している (両件 `state: MERGED`)
3. **[critical]** issue #907 の受け入れ条件 4 項目を全 PR 統合状態で検証している (Phase 1 PR #917 だけで判定していない)
4. **[critical]** 受け入れ条件 4 項目の各々を「どの PR が満たすか」マッピング表で明示 (項目 1-2 → #917 / 項目 3-4 → #918)
5. **[critical]** 「Phase 1 マージ済みだから close 可」を独断していない (#918 マージを必須条件として確認)
6. **[critical]** PR #917 の CLAUDE.md 更新箇所を「受け入れ条件外の追加変更」として正しく仕分け、close 判定の阻害要因にしていない
7. **[critical]** 残タスクのトリアージ (B)/(C) を握り潰しゼロ (Step 6) + ユーザー承認なしに close 実行していない (Step 7)
8. close コメントに紐づく全 PR (#917, #918) を明記 (Step 7 のテンプレート遵守)
9. **[critical]** Step 1 fallback の timeline API (`gh api repos/.../issues/907/timeline`) で PR #917, #918 の 2 件を列挙 + 各 PR 本文 `Refs #907` 確認でケース C と判定している (`closedByPullRequestsReferences` 空でも独断ケース A に倒れない、PR 件数=2 を fallback ルート由来で取得していることを明示)
10. **[important]** 全 PR (#917, #918) のマージ済み確認に Step 1 fallback で取得した PR 一覧を使い、`gh pr view` ループで各 PR を 1 件ずつ MERGED 確認している (どちらか 1 件しか確認しないでケース C 判定する誤りをしていない)
