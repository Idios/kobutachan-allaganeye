# #911 version-check の全バージョン保持箇所ハード化 設計

- 作成日: 2026-07-31
- 対象 issue: [#911](https://github.com/Idios/kobutachan-allaganeye/issues/911)
- 出自: [#862](https://github.com/Idios/kobutachan-allaganeye/issues/862) Task 18 レビューのスコープ外指摘

## 1. 問題

`.github/workflows/release.yml` の `version-check` job は tag と `pyproject.toml` の
`version` だけを突合する。他のバージョン保持箇所がズレていても CI は緑のまま通る。
`pyproject.toml` だけをバンプして release すると、Tauri bundle に旧バージョンが刻印
されたまま出荷される。

本 project が繰り返し摘出している「弱いガード / 存在しないガードが不整合を silent に
通す」クラスと同型。

## 2. 設計時に判明した前提の誤り

issue 本文と `docs/versioning.md` はバージョン保持箇所を **3 箇所**と宣言していたが、
実測では **6 箇所 (7 フィールド)** あった。

| # | ファイル | フィールド | 消費経路 | 旧宣言 |
| --- | --- | --- | --- | --- |
| 1 | `pyproject.toml` | `project.version` | CLI `allaganeye --version` | 有 |
| 2 | `gui/src-tauri/tauri.conf.json` | `version` | Tauri bundle metadata / exe ファイルバージョン | 有 |
| 3 | `gui/package.json` | `version` | npm package metadata | 有 |
| 4 | `gui/src-tauri/Cargo.toml` | `package.version` | `env!("CARGO_PKG_VERSION")` → `probe_environment_info().allaganeye_version` → GUI 環境情報表示 | **無** |
| 5 | `gui/package-lock.json` | `version` / `packages[""].version` | npm が package.json から同期 | **無** |
| 6 | `gui/src-tauri/Cargo.lock` | `package[name=allaganeye-gui].version` | cargo が Cargo.toml から同期 | **無** |

`#4` は runtime にユーザーへ露出する。issue 本文が被害シナリオとして挙げた「GUI の
表示が CLI と食い違う」に最も直結する箇所が、宣言リストから漏れていた。

つまり **SSoT と称していた doc 自体が silent に古びていた**。これは #911 が潰そうと
している問題の同型再帰であり、ガードの対象を 3 箇所に限ると同じ穴を残す。

`#6` は実装途中に repo 全体を洗い直して発見した (`#5` と対になる lockfile)。
`docs/versioning.md` を 5 箇所へ是正した直後に §3.3 の doc 突合テストが赤になり、
自分の書いた doc の漏れを検知した。ガードが設計どおり働いた実例として記録しておく。

`Cargo.lock` は固定 key path では辿れない点に注意が要る:

- 全依存クレートが `[[package]]` 配列に並ぶので、パッケージ名で要素を選ぶ必要がある
- root 直下の `version = 4` は **lockfile フォーマット版**であってリリースバージョン
  ではない。素朴に `("version",)` を辿ると別物を読む

そのため `VersionLocation` に `select = (配列 key, 一致フィールド, 期待値)` を持たせる。
該当要素が 0 個 / 2 個以上のときは「検査対象を特定できない」として exit 2 に倒す。

## 3. 方針

### 3.1 箇所リストの正は実装側に置く

[`docs/coding-conventions.md`](../../coding-conventions.md) §ドキュメント SSoT 規約
(#818) の「管轄が重なる場合は実装を canonical」に従い、機械可読な正を
`scripts/check_version_consistency.py` の `VERSION_LOCATIONS` 定数に置く。
`docs/versioning.md` は人間向けの一覧を保持しつつ、機械可読な正が script 側である旨を
明記する。両者の乖離は §3.3 の突合テストで検知する。

### 3.2 検証スクリプト

```text
python scripts/check_version_consistency.py [--tag vX.Y.Z] [--github-output]
  exit 0 : 全箇所一致 (--tag 指定時は tag とも一致)
  exit 1 : バージョン不一致
  exit 2 : 構造エラー (ファイル欠損 / パース不能 / フィールド欠損)
```

設計上のポイント:

- **全件読んでから判定する**。最初の不一致で即座に抜けず、ズレている箇所を 1 回の
  ログですべて提示する (バンプ漏れが複数箇所にまたがるのが典型のため)
- **exit 1 と exit 2 を分ける**。「ズレている」と「検査自体が壊れた」は CI ログ上で
  区別できる必要がある。特に後者を 0 で通さないことが重要 (検査の自己崩壊を green で
  見逃すのは、ガードが無いより有害)
- GitHub Actions 向けに不一致行を `::error::` 注釈で出力する

### 3.3 テスト (発火する側の実証)

`tests/scripts/test_check_version_consistency.py` に以下を置く。保護機構は不発でも
green になるため、**違反を注入して exit code の生値を観測する**形にする。

| テスト | 意図 |
| --- | --- |
| 全 6 箇所一致 → exit 0 | 正常系 |
| 6 箇所を 1 つずつズラす (parametrize) → exit 1 | 箇所ごとに個別に発火することの実証 |
| `package-lock.json` の `packages[""].version` だけズラす → exit 1 | 同一ファイル内の 2 フィールド目も見ている実証 |
| `Cargo.lock` の lockfile 版 / 依存クレート版を拾わない | 素朴な version 行スキャンでないことの実証 |
| `Cargo.lock` のパッケージ名不一致 → exit 2 | 「特定できない」を 0 で通さない |
| tag 不一致 → exit 1 / tag 一致 → exit 0 | tag 突合の発火 |
| ファイル欠損 / フィールド欠損 / パース不能 → exit 2 | 検査の自己崩壊を green で通さない |
| 実 repo root に対して exit 0 | 現在の repo 状態を恒久 gate する pin test |
| `docs/versioning.md` の表 ↔ `VERSION_LOCATIONS` の集合一致 | §2 の doc drift 再発防止 |

合成 fixture は `tmp_path` に 6 ファイルを生成する。`Cargo.lock` だけは実物の構造
(lockfile フォーマット版 + 別バージョンの依存クレート) を再現しないと上記 2 件の
罠テストが罠として機能しないため、そこだけ忠実に作る。実 repo を見るのは pin test と
doc 突合テストのみ。

発火の証拠は `::error::` 行に限定して観測する。スクリプトは常に全箇所の一覧を stdout
へ出すため、出力全体に対して path の存在を assert すると**ガードが不発でも通る**
vacuous green になる。

### 3.4 workflow と手順書

- `release.yml` の `version-check` job: インライン python 一行を script 呼び出しへ置換。
  tag push 時のみ `--tag` を渡し、それ以外の起動 (PR / `workflow_dispatch` / branch
  push) では箇所間の相互一致だけを検証する。`version_override` の既存挙動は維持
- `release.yml` の `pull_request` paths filter に `scripts/check_version_consistency.py`
  を追加する。既存の release critical script (`build-portable-zip.ps1` /
  `extract_release_notes.py`) と同様、単独変更でも PR で実際に走らせないと
  「ガードが壊れたまま merge される」経路が残るため
- `docs/release-process.md` のバンプ手順・チェックリスト: `pyproject.toml` の名指しを
  やめ、`docs/versioning.md` §バージョン管理場所 への参照に置き換える (値も箇所数も
  複製しない)

## 4. スコープ外

- `docs/versioning.md` 以外の doc に散在するバージョン言及の一掃 (本 issue の対象外)
- `/release` skill の Step 3 バンプ手順。既に 3 箇所を `grep` で拾う記述があり、
  本 PR の doc 参照化とは独立に機能している

## 5. 受け入れ条件との対応

| #911 の受け入れ条件 | 対応 |
| --- | --- |
| `version-check` が 3 箇所すべてを tag と突合し、1 つでも不一致なら fail | §3.2 (対象は実測に基づき 6 箇所へ拡張。3 → 5 は Idios 承認済み、5 → 6 は実装中に発見した `Cargo.lock` を同じ方針で追加) |
| ガードが発火する側で実証されている | §3.3 の parametrize 発火テスト |
| `docs/release-process.md` が 3 箇所すべてを挙げる (値は複製せず `docs/versioning.md` を正として参照) | §3.4。箇所数の複製も避けるため参照のみとする |
