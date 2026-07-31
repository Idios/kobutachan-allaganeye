# バージョニング

## セマンティックバージョニング

`MAJOR.MINOR.PATCH` 形式を採用。

| 種別 | 条件 | 例 |
| --- | --- | --- |
| MAJOR | 破壊的変更（CLI引数の変更、出力形式の変更） | 1.0.0 → 2.0.0 |
| MINOR | 新機能追加（新コマンド、新検知方式） | 0.1.0 → 0.2.0 |
| PATCH | バグ修正、ドキュメント更新 | 0.1.0 → 0.1.1 |

## バージョン管理場所

以下のとおり。`/release` のバージョンバンプはこれらをまとめて更新する。
`gui/package-lock.json` のように **1 ファイルが複数フィールドを持つ**箇所があるので、
ファイル単位で数えて満足しないこと (片方だけが古びる drift が実在する)。

この一覧の**機械可読な正**は [`scripts/check_version_consistency.py`](../scripts/check_version_consistency.py) の
`VERSION_LOCATIONS` 定数 ([`docs/coding-conventions.md`](coding-conventions.md) §ドキュメント SSoT 規約 の
「管轄が重なる場合は実装を canonical」)。本表と定数の乖離は
`tests/scripts/test_check_version_consistency.py` が検知する。

| ファイル | フィールド | 消費経路 |
| --- | --- | --- |
| `pyproject.toml` | `project.version` | CLI `allaganeye --version` |
| `gui/src-tauri/tauri.conf.json` | `version` | Tauri bundle metadata / exe ファイルバージョン |
| `gui/src-tauri/Cargo.toml` | `package.version` | `env!("CARGO_PKG_VERSION")` 経由で `probe_environment_info().allaganeye_version` (GUI の環境情報表示) |
| `gui/package.json` | `version` | npm package metadata |
| `gui/package-lock.json` | `version` / `packages[""].version` | npm が `package.json` から同期 |
| `gui/src-tauri/Cargo.lock` | `package[name=allaganeye-gui].version` | cargo が `Cargo.toml` から同期 |

タグ push 時は [`.github/workflows/release.yml`](../.github/workflows/release.yml) の `version-check` job が
全箇所と tag の一致を検証し、1 つでも不一致なら fail する (#911)。

## リリースフロー

1. `/release [patch|minor|major]` でバージョンバンプ PR を作成
2. メンテナ (Idios) がレビュー・マージ
3. main ブランチに git tag を作成: `v<バージョン>`
