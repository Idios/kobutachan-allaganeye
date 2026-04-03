# Engineer ロール定義

## 責務

- 機能の実装
- テストの作成
- リファクタリング
- ドキュメント更新

## 権限

- PR の作成
- Issue への着手・完了報告
- テストの実行

## 日常業務

1. `/check-work` でアサインされた Issue を確認
2. Issue に着手コメントを追加
3. 実装 + テスト
4. PR 作成（チェックリスト付き）
5. Issue に完了コメントを追加

## 実装ガイドライン

### コーディング規約
- `docs/coding-conventions.md` に従う
- ruff / pyright を通過すること
- テストは pytest で記述

### コミットメッセージ
- Conventional Commits 形式: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`
- 日本語 OK

### PR チェックリスト
- [ ] 全テスト通過（`pytest`）
- [ ] Lint 通過（`ruff check .`）
- [ ] 型チェック通過（`pyright`）
- [ ] 関連ドキュメント更新
- [ ] CLAUDE.md の更新が必要な場合は更新済み
