# リリース戦略

## バージョニング

SemVer に従い、各レイヤーを minor バージョンで区切る。

### コアレイヤー（L1〜L5）

| レイヤー | バージョン | タグ | 目標日 |
|---|---|---|---|
| L1: 試合分割 | 0.1.x | `v0.1.0-preview` (2026-04-17), `v0.1.1` (2026-04-20) | リリース済み |
| L2: 配布・統合 | 0.2.0 | `v0.2.0` | 2026-04-26 |
| L3: メタデータ化 | 0.3.0 | `v0.3.0` | 2026-05-03 |
| L4: 価値評価 | 0.4.0 | `v0.4.0` | 2026-05-10 |
| L5: 自動編集 | 0.5.0 | `v0.5.0` | 2026-05-17 |

L2 は以下のスコープを 1 リリースに統合する:
- GUI サポート (#105)
- ゼロ環境構築配布 (#106)
- 開発プロセス刷新 (L2-0: ハイブリッド skill 方式への移行、レビュープロセス改善)
- allaganeye-guard の運用連携ドキュメント整備 (#458 / #459 — プログラム結合は行わない、`docs/guard-integration.md` 参照)

### 拡張レイヤー（L6）

L2 完了後の拡張フェーズ。L3〜L5 の開発で新たな課題が判明した場合、スコープを見直す。

| レイヤー | バージョン | タグ | 目標日 | 主な内容 |
|---|---|---|---|---|
| L6: プライバシー・精密分割 | 0.6.0 | `v0.6.0` | 2026-05-24 | プレイヤー名ぼかし (#63)、再エンコード分割 (#28) |

> L6 は暫定計画。L5 リリース時に deferred issue を全件レビューし、スコープを確定する。

パッチ（バグ修正）は `0.x.1`, `0.x.2` で対応。

## ブランチ戦略

`develop-x.x.x` を日常の統合先とし、`main` はリリース時のみ更新する。L2 以降は単一ワークツリー + 作業ブランチで運用する (詳細は `docs/l2-workflow.md` 参照)。

```
main (リリースタグ時のみ更新、L1: v0.1.0-preview / v0.1.1 タグ済み)
 └── develop-0.2.0 (L2 開発の統合先)
      ├── claude/l2-gui-*            ← GUI 関連作業 (#105 系)
      ├── claude/l2-installer-*      ← インストーラ作業 (#106 系)
      ├── claude/l2-workflow-*       ← L2-0 プロセス系 + guard 運用連携 doc
      └── claude/l1-residual-*       ← L1 残課題消化 (#412-#440)
```

### ルール

1. **`main` は保護ブランチ** — リリース時の `develop-x.x.0 → main` マージのみ
2. **`develop-x.x.x`** が日常の統合先 — 開発対象のバージョンを明示（例: `develop-0.2.0`）
3. **作業ブランチ** (`claude/<scope>-<short-description>` または `claude/<issue-N>-<slug>`) で作業し、PR を `develop-x.x.x` に出す
4. **リリース完了後** — 次バージョンの `develop-x.x.x` を `main` から作成
5. **ホットフィックス** — `main` からブランチを切り、`main` と `develop-x.x.x` 両方に PR

### PR フロー

```
claude/<scope>-* → PR → /review-pr (受け入れ条件チェック) → /test-pr (実機検証) → develop-x.x.x へマージ
```

レビュー・テスト・マージは**単一セッション内で skill を呼び分けて**実施する。ロール間ハンドオフは不要 (詳細は `docs/l2-workflow.md`)。

## タグ運用

- リリース判断後、`develop-x.x.0 → main` の PR を作成・マージ
- `main` の HEAD にタグを打つ
- タグ形式: `v<major>.<minor>.<patch>`
- コマンド: `git tag -a v0.x.0 -m "Release v0.x.0: <レイヤー名>"`
- `git push origin v0.x.0` すると [`.github/workflows/release.yml`](../.github/workflows/release.yml) が発火し、Windows Portable ZIP (`allaganeye-v<version>-windows.zip`) のビルドと GitHub Release への成果物自動添付を実行する (#461)
  - ビルドは [`scripts/build-portable-zip.ps1`](../scripts/build-portable-zip.ps1) で Python 3.11 embeddable + FFmpeg LGPL essentials を同梱する
    - ダウンロードする外部バイナリ (Python embed / get-pip.py / FFmpeg) はスクリプト内に **SHA256 ダイジェストをハードコードして検証** する。ダイジェスト不一致時はビルドを fail。FFmpeg は特定バージョンタグを URL にピン留め (現在 `8.1`) して再現性を確保する
    - 外部バイナリを更新する場合はスクリプト先頭の `$FFmpegVersion` / `$*Sha256` 定数を更新する
  - Release 本文は [`scripts/extract_release_notes.py`](../scripts/extract_release_notes.py) が CHANGELOG.md から該当バージョンのセクションを抽出する
  - タグ名と `pyproject.toml` の `version` が一致しない場合、workflow は fail する
- 手動で dry-run ビルドを確認したい場合は、Actions タブから `Release` workflow を `workflow_dispatch` で起動する (Release は作成されず ZIP artifact のみ)
- `/release` スキルは develop → main PR 作成・CHANGELOG 更新の支援に使う (Release 作成自体は上記 workflow が担う)

## レイヤー間の移行手順

各レイヤー完了時:

1. `develop-x.x.0` 上で全 PR がマージ済み、テスト通過を確認
2. `deferred` ラベル付き issue を全件レビューし、次バージョンのスコープに含めるか判断する
3. `develop-x.x.0 → main` のリリース PR を作成・マージ
4. `main` にタグを打つ (`v0.x.0`)
5. GitHub Release を作成（変更内容サマリ付き）
6. `main` から次バージョンの `develop-x.x.0` ブランチを作成し、その時点で `pyproject.toml` の `version` を `x.y.0` に更新（`.dev` 等の pre-release 識別子は付けない。PyPI 未公開のため不要）
7. 次レイヤーの Issue を作成し、作業開始
