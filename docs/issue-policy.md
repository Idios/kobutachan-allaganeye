# GitHub Issue 作成ルール

## プレフィックス

Issue タイトルには必ずプレフィックスを付ける:

| プレフィックス | 用途 | ラベル |
|---|---|---|
| `[bug]` | バグ報告 | `bug` |
| `[task]` | 実装タスク | `enhancement` |
| `[doc]` | ドキュメント | `documentation` |
| `[refactor]` | リファクタリング | `enhancement` |
| `[question]` | 質問・相談 | `question` |
| `[risk]` | リスク・懸念 | `question` |

## ロールラベル

タスクの担当ロールに応じてラベルを付与:

| プレフィックス | 推奨ロール | ラベル |
|---|---|---|
| `[bug]` | lead-engineer | `role:lead-engineer` |
| `[task]` | engineer | `role:engineer` |
| `[doc]` | engineer | `role:engineer` |
| `[refactor]` | engineer | `role:engineer` |
| `[question]` | lead-engineer | `role:lead-engineer` |
| `[risk]` | director | `role:director` |

## 必須事項

- **Assignee**: 常に `Idios`
- **重複チェック**: 作成前に既存 Issue を検索する
- **本文**: 背景、期待動作、再現手順（バグの場合）を含める

## ワークフロー

1. Issue 作成
2. 着手時にコメント: `着手: <session-id>`
3. 完了時にコメント: `完了: <session-id> → PR #<番号>`
4. PR マージで Issue 自動クローズ（`Closes #N`）
