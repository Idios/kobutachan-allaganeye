現在のロールに基づいて、担当すべき作業を発見・優先順位付けします。

## 前提条件

- ロールが設定済みであること（ROLE ファイルが存在する）
- ROLE ファイルが存在しない場合はエラーを返す

## 手順

1. ROLE ファイルからロール名を取得
2. GitHub Issue を検索:
   ```bash
   gh issue list --repo Idios/kobutachan-allaganeye --state open --label "role:<ロール名>" --json number,title,labels,assignees,body
   ```
3. GitHub PR を検索:
   ```bash
   gh pr list --repo Idios/kobutachan-allaganeye --state open --json number,title,labels,author,body,reviewDecision
   ```
4. ロール定義（`docs/roles/<role>.md`）に従い、以下の優先順位で作業を提示:

### Director
1. レビュー待ちの PR（`role:director` ラベル）
2. リスク・意思決定の Issue
3. プロセス改善の提案

### Lead Engineer
1. レビュー待ちの PR（`role:lead-engineer` ラベル）
2. 設計レビューの依頼
3. バグの調査 Issue

### Engineer
1. アサインされた Issue（`role:engineer` ラベル）
2. 未着手の実装・リファクタリング Issue
3. テスト不足の領域

### Tester
1. テスト実行の依頼
2. テスト不足の Issue（`role:tester` ラベル）
3. エッジケースの発見

## 出力

優先順位順に作業リストを報告。各項目に:
- Issue/PR 番号とタイトル
- 推奨アクション
- 関連ファイル（わかる場合）
