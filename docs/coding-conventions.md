# コーディング規約

## 言語・バージョン

- Python 3.11+
- 型ヒント必須（pyright standard モード）

## フォーマッター / リンター

- **ruff**: lint + format
- **pyright**: 型チェック

```bash
ruff check .
ruff format --check .
pyright
```

## スタイル

- 関数名・変数名: `snake_case`
- クラス名: `PascalCase`
- 定数: `UPPER_SNAKE_CASE`
- インデント: 4 spaces
- 文字列: ダブルクォート `"` を優先
- 日本語コメント OK

## コミットメッセージ

Conventional Commits 形式:
- `feat:` — 新機能
- `fix:` — バグ修正
- `refactor:` — リファクタリング
- `test:` — テスト追加・修正
- `docs:` — ドキュメント
- `chore:` — ビルド・設定等
- 日本語 OK

## テスト

- pytest で記述
- テストファイル: `tests/test_<モジュール名>.py`
- fixture は `conftest.py` に集約
- 動画ファイルが必要なテストには `@pytest.mark.slow` を付与

## エラーハンドリング

- `allaganeye/exceptions.py` にエラークラスを定義
- 各エラーに exit code を対応付ける
- CLI レイヤーで例外をキャッチし、適切な exit code で終了
