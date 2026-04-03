# マルチエージェント連携プロトコル

## 概要

kobutachan-allaganeye では複数の Claude Code セッションが異なるロールを担当し、Git worktree と GitHub Issue/PR を介して連携する。

## ロール一覧

| ロール | 責務 | 権限 |
|---|---|---|
| Director | 戦略的意思決定、プロセス管理 | PR マージ、リリース承認 |
| Lead Engineer | 設計、コードレビュー、技術的判断 | PR マージ、設計決定 |
| Engineer | 実装、リファクタリング、テスト作成 | PR 作成、Issue 対応 |
| Tester | テスト実行、品質検証、エッジケース発見 | テスト報告、Issue 作成 |

## Worktree 運用

各ロール・セッションは独自の worktree で作業する。

### ディレクトリ命名規則

```
kobutachan-allaganeye-eng1        # Engineer 1
kobutachan-allaganeye-eng2        # Engineer 2
kobutachan-allaganeye-lead        # Lead Engineer 1
kobutachan-allaganeye-tester      # Tester 1
kobutachan-allaganeye-director    # Director 1
```

### ブランチ命名規則

```
engineer-1/work
engineer-2/work
lead-1/work
tester-1/work
director-1/work
```

### ROLE ファイル

各 worktree のルートに `ROLE` ファイルを配置。内容はロール名のみ（例: `engineer`）。
SessionStart hook がこのファイルを読み、ロール適用を促す。

## GitHub Issue ワークフロー

### 着手

Issue に着手する際、コメントを追加:
```
着手: <session-id>
```

### 完了

作業完了時、PR を作成しコメントを追加:
```
完了: <session-id> → PR #<番号>
```

### ラベルとロールの対応

| Issue プレフィックス | 推奨ロール | ラベル |
|---|---|---|
| `[bug]` | lead-engineer | `bug`, `role:lead-engineer` |
| `[task]` | engineer | `enhancement`, `role:engineer` |
| `[doc]` | engineer | `documentation`, `role:engineer` |
| `[refactor]` | engineer | `enhancement`, `role:engineer` |
| `[question]` | lead-engineer | `question`, `role:lead-engineer` |
| `[risk]` | director | `question`, `role:director` |

## PR ワークフロー

### PR 作成時

- タイトルに変更内容を簡潔に記述
- 関連 Issue があれば `Closes #N` を本文に含める
- チェックリストを本文に含める
- ロールに応じたレビューワラベルを付与

### レビューワラベル

| 作成者ロール | レビューワラベル |
|---|---|
| Engineer | `role:lead-engineer` |
| Lead Engineer | `role:director` |
| Tester | `role:lead-engineer` |

### テスト完了確認

マージ前に、テスト担当者が以下のコメントを追加:
```
テスト完了: <session-id>
```

### マージ権限

- **Director**: すべての PR をマージ可能
- **Lead Engineer**: Engineer / Tester の PR をマージ可能
- **Engineer / Tester**: マージ権限なし

## セッション ID

各セッションは一意の ID を持つ: `<ロール名>-<番号>`（例: `engineer-1`, `lead-2`）

Issue コメントや PR に session-id を記録することで、どのセッションが何を行ったかを追跡可能にする。
