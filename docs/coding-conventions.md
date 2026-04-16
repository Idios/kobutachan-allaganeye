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
- `feat:` -- 新機能
- `fix:` -- バグ修正
- `refactor:` -- リファクタリング
- `test:` -- テスト追加・修正
- `docs:` -- ドキュメント
- `chore:` -- ビルド・設定等
- 日本語 OK

## テスト

- pytest で記述
- テストファイル: `tests/test_<モジュール名>.py`
- fixture は `conftest.py` に集約
- 動画ファイルが必要なテストには `@pytest.mark.slow` を付与

## 文字エンコーディング

- `print()` / `logger.*()` の引数（実行時に出力される文字列）は **ASCII 範囲のみ** 使用する
- Windows のデフォルト `cp932` エンコーディングで `UnicodeEncodeError` を防止するため
- 置換ルール: `→` -> `->`, `—` -> `--`, `≈` -> `~=`, `≥` -> `>=`
- docstring・コメント内も同様に ASCII を推奨（pytest -v 等で出力される可能性があるため）
- 日本語テキストは引き続き OK（コメント・docstring 内）

## エラーハンドリング

- `allaganeye/exceptions.py` にエラークラスを定義
- 各エラーに exit code を対応付ける
- CLI レイヤーで例外をキャッチし、適切な exit code で終了
