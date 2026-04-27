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

```text
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

```text
claude/<scope>-* → 実機検証 → PR → /review-pr (受け入れ条件チェック) → develop-x.x.x へマージ
```

レビュー・マージは**単一セッション内で skill を呼び分けて**実施する。実機検証は PR 作成前に行う。セッション間ハンドオフは不要 (詳細は `docs/l2-workflow.md`)。

## タグ運用

- リリース判断後、`develop-x.x.0 → main` の PR を作成・マージ
- `main` の HEAD にタグを打つ
- タグ形式: `v<major>.<minor>.<patch>`
- コマンド: `git tag -a v0.x.0 -m "Release v0.x.0: <レイヤー名>"`
- `git push origin v0.x.0` すると [`.github/workflows/release.yml`](../.github/workflows/release.yml) が発火し、Windows Portable ZIP (`allaganeye-v<version>-windows.zip`) のビルドと GitHub Release への成果物自動添付を実行する (#461)
  - ビルドは [`scripts/build-portable-zip.ps1`](../scripts/build-portable-zip.ps1) で Python 3.11 embeddable + FFmpeg LGPLv3 shared (BtbN FFmpeg-Builds win64-lgpl-shared、libdav1d 入り) を同梱する
    - ダウンロードする外部バイナリ (Python embed / get-pip.py / FFmpeg) はスクリプト内に **SHA256 ダイジェストをハードコードして検証** する。ダイジェスト不一致時はビルドを fail。FFmpeg は BtbN の `autobuild-YYYY-MM-DD-HH-MM` タグと特定アセット名を URL にピン留めして再現性を確保する (`latest` タグは日次更新の可動ポインタなので不可)
    - 外部バイナリを更新する場合はスクリプト先頭の `$FFmpegBuildTag` / `$FFmpegAssetName` / `$*Sha256` 定数を更新する
  - Release 本文は [`scripts/extract_release_notes.py`](../scripts/extract_release_notes.py) が CHANGELOG.md から該当バージョンのセクションを抽出する
  - タグ名と `pyproject.toml` の `version` が一致しない場合、workflow は fail する
- 手動で dry-run ビルドを確認したい場合は、Actions タブから `Release` workflow を `workflow_dispatch` で起動する (Release は作成されず ZIP artifact のみ)
- `/release` スキルは develop → main PR 作成・CHANGELOG 更新の支援に使う (Release 作成自体は上記 workflow が担う)

## レイヤーリリース受け入れゲート

各 minor リリース (`develop-x.x.0 → main`) の実行前に、本節のチェックリストを全件達成する。共通項目はすべての minor リリースに適用、レイヤー固有項目は対応するバージョンで適用する。`/release` skill の Step 0 で本節を参照する (`.claude/skills/release/SKILL.md`)。

### 共通項目 (全 minor リリース)

- [ ] `develop-x.x.0` 上で対象スコープの全 PR がマージ済み
- [ ] CI 全ジョブ (Python / GUI frontend / GUI Rust / Pester) が直近の develop tip で緑
- [ ] `pyproject.toml` の `version` が `x.y.0` に更新されている
- [ ] `CHANGELOG.md` に対象バージョンセクションが存在 (日付 / 主要変更点 / breaking changes)
- [ ] `deferred` ラベル付き issue を全件レビュー済 (close、または次バージョン `deferred` 維持判断、または当該バージョンに引き取り)
- [ ] 対象レイヤースコープの `P1-high` issue 全 close + `P2-medium` issue 全 close または `deferred` ラベル付与

### v0.2.0 (L2: GUI サポート + ゼロ環境構築配布) 固有項目

- [ ] [#484](https://github.com/Idios/kobutachan-allaganeye/issues/484) L2 E2E 統合テストチェックリスト全 PASS (`docs/l2-e2e-checklist.md`)
- [ ] Portable ZIP (`allaganeye-v0.2.0-windows.zip`) の手動 smoke を実施:
  - `allaganeye.bat --version` (CLI 起動) で正しい version 表示
  - `allaganeye-gui.exe` (GUI 起動) でウィンドウ表示 + version 表示
- [ ] `l1-residual` ラベル全件 ([#412](https://github.com/Idios/kobutachan-allaganeye/issues/412) / [#413](https://github.com/Idios/kobutachan-allaganeye/issues/413) / [#433](https://github.com/Idios/kobutachan-allaganeye/issues/433) / [#434](https://github.com/Idios/kobutachan-allaganeye/issues/434) / [#435](https://github.com/Idios/kobutachan-allaganeye/issues/435) / [#436](https://github.com/Idios/kobutachan-allaganeye/issues/436) / [#440](https://github.com/Idios/kobutachan-allaganeye/issues/440) / [#553](https://github.com/Idios/kobutachan-allaganeye/issues/553) / [#576](https://github.com/Idios/kobutachan-allaganeye/issues/576)) の deferred 判断完了 (close または `deferred` ラベル付与)
- [ ] `l2a-gui` / `l2b-installer` / `l2-workflow` スコープラベルの open issue で `P1-high` がゼロ
- [ ] `docs/guard-integration.md` §5 「外部動画データの検査」運用が成立 (allaganeye-guard 独立リポジトリの最新版が利用可能)

### v0.3.0 以降のレイヤー固有ゲート枠組み

各レイヤー固有のチェックリストは本節以下に追加していく。各レイヤー特有の品質ゲートを当該リリース直前のレビューで確定する。

| バージョン | レイヤー | 想定ゲート項目 |
|---|---|---|
| v0.3.0 | L3: メタデータ化 | キルログ OCR / 音声認識統合の精度ベンチ、metadata schema 拡張の互換性検証 |
| v0.4.0 | L4: 価値評価 | ローカル ML model 評価指標、サンプル動画群での評価分布 |
| v0.5.0 | L5: 自動編集 | クリップ生成成功率、投稿提案の妥当性レビュー |

各レイヤー固有のゲート項目は、当該リリース PR の PR 本文または「v0.x.0 (L?) 固有項目」節で確定する。確定後は本 doc に追記して恒久化する。

## レイヤー間の移行手順

各レイヤー完了時:

1. **§レイヤーリリース受け入れゲート** のチェックリストを全件達成 (共通項目 + 当該レイヤー固有項目)
2. `develop-x.x.0 → main` のリリース PR を作成・マージ
3. `main` にタグを打つ (`v0.x.0`)
4. GitHub Release を作成（変更内容サマリ付き、`release.yml` 自動 or `docs/release-process.md` §手動リリース手順）
5. `main` から次バージョンの `develop-x.x.0` ブランチを作成し、その時点で `pyproject.toml` の `version` を `x.y.0` に更新（`.dev` 等の pre-release 識別子は付けない。PyPI 未公開のため不要）
6. 次レイヤーの Issue を作成し、作業開始

## 手動リリース手順 (CI 迂回)

通常のリリースは `git push origin v<x.y.z>` をトリガーに [`.github/workflows/release.yml`](../.github/workflows/release.yml) が自動実行する (上記 §タグ運用 参照)。本節は CI が一時的に使えない場合 (GitHub Actions 障害、`release.yml` 自体の不具合など) の代替手順として、手動でビルド + Release 作成を行う方法を記載する (#461)。

### 前提

- ローカル環境に Python 3.11.9 + PowerShell (Windows PowerShell 5.1 以上 or pwsh 7+) + Git がインストール済み ([Developer Setup](developer-setup.md) §1)
- `develop-x.x.x` で全テスト pass、`develop-x.x.0 → main` PR マージ済み
- 公開対象バージョン (`x.y.z`) と `pyproject.toml` の `version` が一致していること

### 手順

1. **main の最新化**:

   ```bash
   git checkout main
   git pull origin main
   ```

1. **ローカル Portable ZIP ビルド** ([`scripts/build-portable-zip.ps1`](../scripts/build-portable-zip.ps1) を直接呼び出し):

   ```powershell
   pwsh ./scripts/build-portable-zip.ps1 -Version 'x.y.z'
   ```

   `dist/allaganeye-vx.y.z-windows.zip` が生成される (Python 3.11.9 embed + BtbN LGPLv3 FFmpeg n8.1 + 各 LICENSE 同梱、SHA256 検証付き)。

1. **Release notes の抽出**:

   ```bash
   python scripts/extract_release_notes.py x.y.z release-notes.md
   ```

1. **タグ push 時に `release.yml` が誤発火しないよう Actions を一時無効化**:
   GitHub Web UI: `Settings > Actions > General > Actions permissions` → `Disable actions`。自動 Release 作成と手動 Release 作成の重複を防ぐため。

1. **タグを打って push**:

   ```bash
   git tag -a vx.y.z -m "Release vx.y.z: <レイヤー名>"
   git push origin vx.y.z
   ```

1. **GitHub Release を手動作成 + ZIP 添付**:

   ```bash
   gh release create vx.y.z dist/allaganeye-vx.y.z-windows.zip \
     --title "vx.y.z" \
     --notes-file release-notes.md
   ```

1. **Actions を再有効化**:
   GitHub Web UI: `Settings > Actions > General > Actions permissions` → `Allow all actions and reusable workflows`。

### 注意事項

- 手動リリース後、次回の通常 push で `release.yml` の `pull_request` トリガーや `python` ジョブが正常動作するか確認する (Actions タブから `Release` workflow を `workflow_dispatch` で dry-run 起動するのが確実)
- 同梱バイナリ (Python / FFmpeg) の更新は手動ビルドでも自動ビルドでも更新箇所が同じ ([`docs/developer-setup.md` §9](developer-setup.md) のチェックリストに従う)
- 手動 Release は通常時は不要。CI 復旧後は `release.yml` 経由に戻す
