# コーディング規約

## 言語・バージョン

- Python 3.11+
- 型ヒント必須（pyright standard モード）

## フォーマッター / リンター

- **ruff**: lint + format
- **pyright**: 型チェック
- **markdownlint-cli2**: Markdown ドキュメントの lint (CI)

```bash
ruff check .
ruff format --check .
pyright

# Markdown (Node.js 必須、ローカル実行は任意)
npx -y markdownlint-cli2@0.18.1
```

設定は [`.markdownlint-cli2.yaml`](../.markdownlint-cli2.yaml)。既存違反のあるルールを disable し、新規コミット時の違反を CI で捕捉する構成。段階的に disable を外す計画は `#474` 系の follow-up issue で管理する。

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

### subprocess.run の text=True と encoding (#656)

- `subprocess.run(text=True, ...)` を使う場合、**必ず** `encoding="utf-8", errors="replace"` を明示する
- 省略すると Python は `locale.getpreferredencoding(False)` (Windows = cp932) を使い、ffmpeg/ffprobe の UTF-8 stderr に日本語含む path が含まれると `UnicodeDecodeError` で `_readerthread` (subprocess.py) が死に process が exit 1 で終了する (#656)
- `errors="replace"` で異常 byte を U+FFFD で置換し reader thread の防御線とする
- `text=False` (binary mode) の場合は decode が走らないため対象外 (例: `audio/extract.py` / `video/detector.py` / `video/gpu_detector.py`)

## エラーハンドリング

- `allaganeye/exceptions.py` にエラークラスを定義
- 各エラーに exit code を対応付ける
- CLI レイヤーで例外をキャッチし、適切な exit code で終了
