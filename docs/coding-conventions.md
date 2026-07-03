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

## ドキュメント SSoT 規約 (#818)

同じ仕様値を複数 doc に書かない。**正 1 箇所 + 参照リンク** を原則とする。

### 規約

- 仕様値・定数・挙動説明の**正 (SSoT) は 1 箇所**に置く。正の置き場所は対象領域の spec doc または実装とし、代表は以下:
  - [`docs/cli-spec.md`](cli-spec.md) — CLI 構文・オプション・exit code
  - [`docs/metadata-spec.md`](metadata-spec.md) — `metadata.json` スキーマ (機械可読の正は `schemas/metadata.schema.json`。二層構造は同 doc §SSoT 二層構造 (#612) を参照)
  - 実装 docstring — spec doc の管轄外の内部定数・アルゴリズムパラメータ (例: worker 数上限、probe 間隔)
- 他の doc から同じ値に言及する場合は、**値を複製せず正へのリンクで参照**する
- `CLAUDE.md` は索引として**要約**してよい。数値を書く場合は出典リンクを併記する
- 既存 doc に複製値を見つけたら、その doc の修正時に正 1 箇所へ寄せて他をリンク化する (W6 doc 一括再同期でも本規約を適用する)

### 背景 (違反の代表事例)

workers 上限「24」が 6 doc 7 箇所に複製されたまま実装 (32) と drift した (2026-06-10 full audit P2-25)。同種の doc–実装 drift が P2-26〜P2-28 等でも反復しており、値の複製自体が drift の構造的な再発要因。詳細は [`docs/audits/2026-06-10-full-audit.md`](audits/2026-06-10-full-audit.md) および [audit-remediation spec §N3](superpowers/specs/2026-06-10-audit-remediation-design.md#n3-doc-ssot-規約の明文化--release-gate-追記) を参照。
