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
| `--list-paths` が重複なし・宣言順で出る | `git add --` にそのまま渡せる形の担保 |
| `--list-paths` はファイル欠損時も exit 0 | バンプ途中に呼ぶ mode なので値を読まないことの実証 |
| `--list-paths` の生バイト列に `\r` が無い | Windows CRLF で `git add` が exit 128 になる回帰の防止 |

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

### 3.5 `/release` skill の Step 3 バンプ手順

当初はスコープ外としていたが、実装後に **新ガードと衝突する latent break** であることが
判明したため PR 内で直す (Idios 判断、(A) PR 内修正優先)。

Step 3-2 は保持箇所を
`grep -r '<旧バージョン>' --include='*.py' --include='*.toml' --include='*.json'` で
拾う手順だった。`Cargo.lock` / `package-lock.json` はこの glob のどれにも載らない
(`*.lock` / `package-lock.json` は `*.json` に一致するが `Cargo.lock` は一致しない)。
つまり次のバンプで `Cargo.lock` だけが旧バージョンのまま残り、§3.2 のガードが
リリースを hard fail させる。ガードを足した PR が、そのガードに引っかかる手順書を
放置する形になっていた。

置換方針は §3.1 と同じで、箇所リストを skill 側に複製せず
`docs/versioning.md` §バージョン管理場所 を参照し、更新後に
`python scripts/check_version_consistency.py --tag v<新バージョン>` で検証させる
(手順書が守れたかどうかを人間の目視ではなく exit code で判定させる)。
Step 3-4 の `git add pyproject.toml` も、stage 漏れが同じ fail を招くため
`git add -- $(python scripts/check_version_consistency.py --list-paths)` に変更する。

`--list-paths` は値を読まずに検査対象 path を 1 行 1 件・重複なしで出す mode。
出力は機械消費されるため**改行を LF に固定する**。Windows の text-mode stdout が
"\n" を CRLF へ変換する一方、bash の既定 IFS は "\r" を区切りに含めないので、
素直に `print` すると path 末尾に "\r" が残り
`fatal: pathspec 'pyproject.toml?' did not match any files` (exit 128) になる。
この不具合は §6 の 5 回目の実行で実測された (`capsys` は改行変換を挟まないため
捕捉できず、subprocess の生バイト列を見るテストが必要だった)。
バンプ「途中」(まだ全箇所が一致していない状態) で呼ぶため、不一致や欠損があっても
path 一覧は返す。これがないと実行者が `VERSION_LOCATIONS` の 7 フィールドを
6 path へ手で畳む必要があり、保持箇所が増えたときに取りこぼす経路が残る
(§3.1 と同じ「箇所リストを人間が複製する」問題の再発)。

## 4. スコープ外

- `docs/versioning.md` 以外の doc に散在するバージョン言及の一掃 (本 issue の対象外)

## 5. 受け入れ条件との対応

| #911 の受け入れ条件 | 対応 |
| --- | --- |
| `version-check` が 3 箇所すべてを tag と突合し、1 つでも不一致なら fail | §3.2 (対象は実測に基づき 6 箇所へ拡張。3 → 5 は Idios 承認済み、5 → 6 は実装中に発見した `Cargo.lock` を同じ方針で追加) |
| ガードが発火する側で実証されている | §3.3 の parametrize 発火テスト |
| `docs/release-process.md` が 3 箇所すべてを挙げる (値は複製せず `docs/versioning.md` を正として参照) | §3.4。箇所数の複製も避けるため参照のみとする |

## 6. `/release` skill 改修の empirical-prompt-tuning 記録

`.claude/skills/` の改修は
[`docs/l2-workflow.md`](../../l2-workflow.md) §skill 改修ワークフロー に従い
mizchi `empirical-prompt-tuning` protocol で iterate した。

手法: 毎回 **fresh subagent** を dispatch し (自己再読では著者バイアスが混入する)、
Step 3-2 / 3-4 だけを実行させて「実行結果 + フェーズ自己申告 + 不明瞭点」を報告させる。
critical 条件は「7 フィールド全部を更新」「検証コマンドを実行し exit 0 を報告」の 2 つ。

| # | シナリオ | critical | 新規に摘出された不明瞭点 (スコープ内) | 対処 |
| --- | --- | --- | --- | --- |
| 1 | minor `0.3.0`→`0.4.0` | 達成 | 「箇所」がファイル単位かフィールド単位か / lockfile の直接編集と再同期の選択基準なし / `git status --short` の合格条件未定義 | 数量表記を廃しフィールド単位を明示 / 直接編集を既定に確定 / 合格条件を明記 |
| 2 | patch `0.3.0`→`0.3.1` | 達成 | `git add` placeholder の展開規則 (フィールド 7 → path 6 の畳み込み) が未記載 | 重複 path 除去を明記 |
| 3 | major `0.3.0`→`1.0.0` | 達成 | `docs/versioning.md` の `version` / `packages[""].version` のスラッシュが and/or 両読み | 「両方」と明記 |
| 4 | minor `0.3.0`→`0.4.0` | 達成 | path 畳み込みを実行者が手でやる構造が残っている (保持先が増えたら取りこぼす) | `--list-paths` を追加し `git add` を機械化 |
| 5 | patch `0.3.0`→`0.3.1` | 達成 | **`--list-paths` の CRLF で `git add` が exit 128** / cwd 前提が未記載 | 改行を LF 固定 + 生バイト列テスト |
| 6 | major `0.3.0`→`1.0.0` | 達成 | なし (既出 / スコープ外 / 許容済みのみ) | — |
| 7 | minor `0.3.0`→`0.4.0` | 達成 | worktree 運用で「repo root」がどのツリーを指すか未確定 | cwd を明示 |
| 8 | patch `0.3.0`→`0.3.1` | 達成 | 他作業の差分が同居する場合、`git status --short` を「空であること」と読む余地 | 「空である必要はない」を明記 |
| 9 | major `0.3.0`→`1.0.0` | 達成 | なし (既出 / スコープ外 / 許容済みのみ) | — |
| 10 | minor `0.3.0`→`0.4.0` | 達成 | **7 回目で足した cwd 注記の因果説明が実装と不一致** (スクリプトは cwd 非依存で、cwd に依存するのは `git add` 側) / 「箇所」が Step 3-2 では 7 フィールド・Step 3-4 では 6 ファイルを指す / lockfile 一括置換の誤爆 (`0.3.0` に対する `30.3.0`) への注意なし | 手順から「箇所」を排除し「フィールド」「ファイル」に統一 / 因果を `git add` 側に訂正 / 一括置換禁止を明記 |
| 11 | patch `0.3.0`→`0.3.1` | 達成 | なし (既出 / スコープ外 / 許容済みのみ) | — |
| 12 | major `0.3.0`→`1.0.0` | 達成 | なし (既出 / スコープ外 / 許容済みのみ) | — |

11 / 12 回目が連続クリア (新規のスコープ内不明瞭点ゼロ) で収束と判定した。
critical (7 フィールド全部を更新 / 検証コマンド exit 0) は **12 回すべてで 100% 達成**。

判定基準を明記しておく。「クリア」= *新規かつスコープ内の* 不明瞭点がゼロ、である。
手順書を初見で読む fresh subagent は毎回なにかしら観察を返すので、
「観察がゼロ」を停止条件にすると原理的に収束しない。既出の反復・スコープ外・
後述の許容済み finding は、収束判定では新規に数えない。

5 回目の CRLF と 10 回目の cwd 因果ミスは、いずれも**私が前の指摘に応えて足した
記述そのものが壊れていた**という finding だった。特に 5 回目は、実行者が
「失敗したので `git add pyproject.toml` に退避」すれば #911 が潰したはずの事故経路に
そのまま戻る性質のもの。自己再読では出ない類であり、fresh subagent に実際に
実行させる意味が出た箇所。

10 回目で「7 回目の修正が新たな finding を生む」形になったため、個別 patch の
もぐら叩きと判断して打ち切り、散文を足すのをやめて**用語レベル**で直した
(手順書から多義語「箇所」を排除し、フィールド / ファイルに統一)。
以降 2 回は新規指摘ゼロで、この判断は妥当だったと考える。

許容した finding (修正せず、根拠を残す):

- `git add -- $(...)` は unquoted なので path にスペースが入ると壊れる
  (6 / 12 回目)。現行の保持先にスペース入り path は無く、
  仮に入れば `git add` が pathspec エラーで落ちるので silent failure にはならない
- フィールド総数 (6 ファイル / 7 フィールド) を手順書に書いてほしい (11 回目)。
  **意図的に書かない**。数を doc 側へ複製するのは §3.1 で排したのと同じ drift 源で、
  #911 の原因そのもの。総数の確認は検証スクリプトの exit code が担う
- 検証スクリプトの日本語出力が Windows コンソールで cp932 mojibake になる
  (5 / 6 / 9 回目)。判定は exit code なので実害なし。UTF-8 を強制すると
  実際に cp932 なコンソールを壊すため入れない
- Step 3-2 の主節が `docs/versioning.md`、括弧内が「機械可読な正は実装」という
  語順が doc 優位に読める (11 / 12 回目)。両回とも実装側を正として正しく解決しており
  出力に影響していない。語順の入れ替えは #818 の SSoT 規約と整合する改善だが、
  ここで編集すると 11 / 12 回目が「出荷する文面」を検証したことにならなくなるため
  見送り、記録に留める

スコープ外として残した finding (別 issue 化):

- Step 2-4 の minor/major ベースブランチ `develop-<新バージョン>` が、
  バンプ前には存在しないブランチ名を指しうる (1 / 3 / 4 / 5 / 6 回目で反復摘出)。
  major bump では `pyproject.toml` のコメント内 `develop-0.3.0` を
  書き換えたくなる誘惑にもつながる (12 回目)
- Step 3-6 の PR 本文テンプレートが存在しない「Step 1」を参照している
  (実体は Step 0c、1 / 5 / 8 / 12 回目で摘出)
- バンプ「方向」(新 > 旧) を検証する手順が無い (3 / 6 回目)
