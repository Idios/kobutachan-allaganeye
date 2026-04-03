# リリース戦略

## バージョニング

SemVer に従い、各レイヤーを minor バージョンで区切る。

| レイヤー | バージョン | タグ | 目標日 |
|---|---|---|---|
| L1: 試合分割 | 0.1.0 | `v0.1.0` | 2026-04-05 |
| L2: メタデータ化 | 0.2.0 | `v0.2.0` | 2026-04-07 |
| L3: 価値評価 | 0.3.0 | `v0.3.0` | 2026-04-09 |
| L4: 自動編集 | 0.4.0 | `v0.4.0` | 2026-04-11 |

パッチ（バグ修正）は `0.x.1`, `0.x.2` で対応。

## ブランチ戦略

`develop-x.x.x` を日常の統合先とし、`main` はリリース時のみ更新する。

```
main (リリースタグ時のみ更新)
 └── develop-0.1.0 (L1 開発中の統合先)
      ├── engineer-1/work   ← 実装作業
      ├── engineer-2/work   ← 実装作業
      ├── lead-1/work       ← 設計・レビュー
      ├── tester-1/work     ← テスト
      └── director-1/work   ← 戦略・プロセス
```

### ルール

1. **`main` は保護ブランチ** — リリース時の `develop-x.x.0 → main` マージのみ
2. **`develop-x.x.x`** が日常の統合先 — 開発対象のバージョンを明示（例: `develop-0.1.0`）
3. **ロール worktree ブランチ** (`<role>-<N>/work`) で作業し、PR を `develop-x.x.x` に出す
4. **リリース完了後** — 次バージョンの `develop-x.x.x` を `main` から作成
5. **ホットフィックス** — `main` からブランチを切り、`main` と `develop-x.x.x` 両方に PR

### PR フロー

```
engineer-1/work → PR → (lead-1 レビュー) → develop-0.1.0 へマージ
lead-1/work     → PR → (director-1 レビュー) → develop-0.1.0 へマージ
```

## タグ運用

- リリース判断後、`develop-x.x.0 → main` の PR を作成・マージ
- Director が `main` の HEAD にタグを打つ
- タグ形式: `v<major>.<minor>.<patch>`
- コマンド: `git tag -a v0.x.0 -m "Release v0.x.0: <レイヤー名>"`
- GitHub Release は `/release` スキルで作成

## レイヤー間の移行手順

各レイヤー完了時:

1. `develop-x.x.0` 上で全 PR がマージ済み、テスト通過を確認
2. `pyproject.toml` の `version` を更新する PR を `develop-x.x.0` に作成・マージ
3. `develop-x.x.0 → main` のリリース PR を作成・マージ
4. `main` にタグを打つ (`v0.x.0`)
5. GitHub Release を作成（変更内容サマリ付き）
6. `main` から次バージョンの `develop-x.x.0` ブランチを作成
7. 次レイヤーの Issue を作成し、作業開始
