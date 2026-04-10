# リリース戦略

## バージョニング

SemVer に従い、各レイヤーを minor バージョンで区切る。

### コアレイヤー（L1〜L5）

| レイヤー | バージョン | タグ | 目標日 |
|---|---|---|---|
| L1: 試合分割 | 0.1.0 | `v0.1.0` | 2026-04-11 |
| L2: GUI | 0.2.0 | `v0.2.0` | TBD |
| L3: メタデータ化 | 0.3.0 | `v0.3.0` | TBD |
| L4: 価値評価 | 0.4.0 | `v0.4.0` | TBD |
| L5: 自動編集 | 0.5.0 | `v0.5.0` | TBD |

### 拡張レイヤー（L6〜L8）

L5 完了後の拡張フェーズ。L2〜L5 の開発で新たな課題が判明した場合、スコープを見直す。

| レイヤー | バージョン | タグ | 目標日 | 主な内容 |
|---|---|---|---|---|
| L6: guard 連携 | 0.6.0 | `v0.6.0` | TBD | allaganeye-guard 統合 (`--verify`)、exit code 6 追加 |
| L7: 配布 | 0.7.0 | `v0.7.0` | TBD | ゼロ環境構築配布 (#106) |
| L8: プライバシー・精密分割 | 0.8.0 | `v0.8.0` | TBD | プレイヤー名ぼかし (#63)、再エンコード分割 (#28) |

> L6〜L8 は暫定計画。L5 リリース時に deferred issue を全件レビューし、スコープを確定する。

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
2. `deferred` ラベル付き issue を全件レビューし、次バージョンのスコープに含めるか判断する
3. `pyproject.toml` の `version` を更新する PR を `develop-x.x.0` に作成・マージ
4. `develop-x.x.0 → main` のリリース PR を作成・マージ
5. `main` にタグを打つ (`v0.x.0`)
6. GitHub Release を作成（変更内容サマリ付き）
7. `main` から次バージョンの `develop-x.x.0` ブランチを作成
8. 次レイヤーの Issue を作成し、作業開始
