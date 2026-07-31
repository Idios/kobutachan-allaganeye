# バージョニング

## セマンティックバージョニング

`MAJOR.MINOR.PATCH` 形式を採用。

| 種別 | 条件 | 例 |
| --- | --- | --- |
| MAJOR | 破壊的変更（CLI引数の変更、出力形式の変更） | 1.0.0 → 2.0.0 |
| MINOR | 新機能追加（新コマンド、新検知方式） | 0.1.0 → 0.2.0 |
| PATCH | バグ修正、ドキュメント更新 | 0.1.0 → 0.1.1 |

## バージョン管理場所

以下の 3 箇所。`/release` のバージョンバンプはこの 3 つをまとめて更新する。

| ファイル | フィールド |
| --- | --- |
| `pyproject.toml` | `version` |
| `gui/src-tauri/tauri.conf.json` | `version` |
| `gui/package.json` | `version` |

## リリースフロー

1. `/release [patch|minor|major]` でバージョンバンプ PR を作成
2. メンテナ (Idios) がレビュー・マージ
3. main ブランチに git tag を作成: `v<バージョン>`
