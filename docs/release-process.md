# リリース戦略

## バージョニング

SemVer に従い、各レイヤーを minor バージョンで区切る。

### コアレイヤー（L1〜L6）

| レイヤー | バージョン | タグ | 目標日 |
| --- | --- | --- | --- |
| L1: 試合分割 | 0.1.x | `v0.1.0-preview` (2026-04-17), `v0.1.1` (2026-04-20) | リリース済み |
| L2: 配布・統合 | 0.2.0 | `v0.2.0` | 2026-04-26 |
| L3 (new): 配信形式対応 + 性能改善 | 0.3.0 | `v0.3.0` | TBD |
| L4 (former L3): メタデータ化 | 0.4.0 | `v0.4.0` | TBD |
| L5 (former L4): 価値評価 | 0.5.0 | `v0.5.0` | TBD |
| L6 (former L5): 自動編集 | 0.6.0 | `v0.6.0` | TBD |

L2 は以下のスコープを 1 リリースに統合する:

- GUI サポート (#105)
- ゼロ環境構築配布 (#106)
- 開発プロセス刷新 (L2-0: ハイブリッド skill 方式への移行、レビュープロセス改善)
- allaganeye-guard の運用連携ドキュメント整備 (#458 / #459 — プログラム結合は行わない、`docs/guard-integration.md` 参照)

### 拡張レイヤー（L7）

L2 完了後の拡張フェーズ。L3 (new)〜L6 (former L5) の開発で新たな課題が判明した場合、スコープを見直す。

| レイヤー | バージョン | タグ | 目標日 | 主な内容 |
| --- | --- | --- | --- | --- |
| L7 (former L6): プライバシー・精密分割 | 0.7.0 | `v0.7.0` | TBD | プレイヤー名ぼかし (#63)、再エンコード分割 (#28) |

> L7 (former L6) は暫定計画。L6 (former L5) リリース時に deferred issue を全件レビューし、スコープを確定する。

パッチ（バグ修正）は `0.x.1`, `0.x.2` で対応。

## ブランチ戦略

`develop-x.x.x` を日常の統合先とし、`main` はリリース時のみ更新する。L2 以降は単一ワークツリー + 作業ブランチで運用する (詳細は `docs/l2-workflow.md` 参照)。

```text
main (リリースタグ時のみ更新、L1: v0.1.0-preview / v0.1.1 / L2: v0.2.0 / v0.2.1 タグ済み)
 ├── release/vX.Y.Z (リリース PR の head。develop-X.Y.0 から分岐し、CHANGELOG / version bump / 出荷ブロッカー fix を載せる)
 └── develop-0.3.0 (L3 開発の統合先)
      ├── claude/l3-minimap-*        ← minimap 切抜き (#481, parent #753)
      ├── claude/l3-perf-*           ← export 並列 (#761 #762) / detect 高速化 (#576)
      ├── claude/l3-vtuber-*         ← VTuber 動画対応 (2026-07-17 再開 #895 timeline 再設計。release 割当は /release Step 0c 判断)
      └── claude/<issue-N>-<slug>    ← 個別 issue 消化
```

### ルール

1. **`main` は保護ブランチ** — リリース時の `release/vX.Y.Z → main` マージのみ (`release/vX.Y.Z` は `develop-X.Y.0` から分岐。v0.2.x までは `develop-x.x.x → main` を直接使用していた)
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

- リリース判断後、`/release` skill が `develop-x.x.0` から `release/v<新バージョン>` を切り、`release/v<新バージョン> → main` の PR を作成・マージする (実例: v0.3.0 = PR [#924](https://github.com/Idios/kobutachan-allaganeye/pull/924))
- `main` の HEAD にタグを打つ
- タグ形式: `v<major>.<minor>.<patch>`
- **CHANGELOG 見出し日付 = タグを打つ日 (JST)** — `CHANGELOG.md` の `## [x.y.z] - YYYY-MM-DD` の日付は、そのバージョンの**タグを打つ日**を `Asia/Tokyo` で表した値とする (裁定 D6、#948)
  - 基準タイムゾーンは `Asia/Tokyo` に**ハードコードする**。GitHub Actions runner は既定 UTC なので、明示変換しない実装は JST 深夜のタグ打ちで 1 日ずれた日付を「正」として比較してしまう。過去 4 タグ中 2 件が該当する (v0.1.1 = 2026-04-20 02:55 JST / v0.2.1 = 2026-05-17 08:43 JST の 2 件は UTC 日付が前日になる)
  - **00:00-09:00 JST のタグ打ちは許容する** (spec §8.2 O-5 の決着)。運用側で時間帯を縛らず、検査側の `Asia/Tokyo` 変換で吸収する
  - タグを打つ直前に見出し日付を当日へ更新し、**リリース PR の head (`release/vX.Y.Z`) へ commit する** (`main` は保護ブランチなのでマージ後には直せない)。手順は [`.claude/skills/release/SKILL.md`](../.claude/skills/release/SKILL.md) §Step 4
  - 機械検査は [`scripts/check_version_consistency.py`](../scripts/check_version_consistency.py) の `--tag` 指定時のみ発火する。基準日は **annotated tag の `taggerdate` のみ**を `--changelog-date-from` で渡す。`head_commit.timestamp` へ fallback しない — あれは「タグが指す commit の日時」であってタグを打った日時ではなく、commit とタグ push が日を跨ぐと規約とズレた値を「正」として通してしまうため。`taggerdate` が取れない場合 (lightweight tag) は fail させ、`git tag -a` で打ち直す
  - **検査対象外の集合**は同スクリプトの `check_changelog_heading()` docstring に列挙してある
- コマンド: `git tag -a v0.x.0 -m "Release v0.x.0: <レイヤー名>"` (**annotated tag**。`taggerdate` が日付検査の第一基準になるため lightweight tag は使わない)
- `git push origin v0.x.0` すると [`.github/workflows/release.yml`](../.github/workflows/release.yml) が発火し、Windows Portable ZIP (`allaganeye-v<version>-windows.zip`) のビルドと GitHub Release への成果物自動添付を実行する (#461)
  - ビルドは [`scripts/build-portable-zip.ps1`](../scripts/build-portable-zip.ps1) で PyInstaller `--onedir` により Python interpreter + 全依存 (numpy / scipy / opencv-python-headless / typer / allaganeye 本体) を frozen application 化 (`scripts/installer/requirements-pyinstaller.txt` で pyinstaller / hooks-contrib version pin、CI `actions/setup-python@v5` で Python 3.11.9 pin) し、FFmpeg LGPLv3 shared (BtbN FFmpeg-Builds win64-lgpl-shared、libdav1d 入り) を同梱する (#752)
    - ダウンロードする外部バイナリ (FFmpeg) はスクリプト内に **SHA256 ダイジェストをハードコードして検証** する。ダイジェスト不一致時はビルドを fail。FFmpeg は BtbN の **monthly snapshot タグ** (`autobuild-YYYY-MM-{28,29,30,31}-*`、~24 ヶ月 retention) と特定アセット名を URL にピン留めして再現性を確保する (`latest` タグは日次更新の可動ポインタなので不可、daily 中間タグは ~14 日で GC されるため不可。詳細 #705)
      - PyInstaller bundle の bump 手順は [`docs/developer-setup.md` §「PyInstaller フローでの version pin (#752 以降)」](developer-setup.md) を参照
    - 外部バイナリを更新する場合はスクリプト先頭の `$FFmpegBuildTag` / `$FFmpegAssetName` / `$*Sha256` 定数を更新する
  - Release 本文は [`scripts/extract_release_notes.py`](../scripts/extract_release_notes.py) が CHANGELOG.md から該当バージョンのセクションを抽出する
  - タグ名と[バージョン保持箇所](versioning.md#バージョン管理場所)が 1 つでも一致しない場合、workflow の `version-check` job は fail する (#911)。突合対象の正は [`scripts/check_version_consistency.py`](../scripts/check_version_consistency.py) の `VERSION_LOCATIONS`
  - 同 job は tag push 時に **CHANGELOG 見出し日付**と**バンプ方向** (直前のリリースより新しいこと) も検査する (#948 / #918)。いずれも `--tag` 指定時のみ発火するため、**PR / `workflow_dispatch` / branch push では 1 度も走らない**
- 手動で dry-run ビルドを確認したい場合は、Actions タブから `Release` workflow を `workflow_dispatch` で起動する (Release は作成されず ZIP artifact のみ)
- `/release` スキルは develop → main PR 作成・CHANGELOG 更新の支援に使う (Release 作成自体は上記 workflow が担う)

## CHANGELOG entry の記述規約 (#952)

`CHANGELOG.md` の version セクションは、[`scripts/extract_release_notes.py`](../scripts/extract_release_notes.py) が**丸ごと抽出して GitHub Release の本文にする**。つまり CHANGELOG の書き方はそのまま公開リリースノートの品質になる。読者は FF14 プレイヤーであってメンテナではない。

### 掲載範囲 — 何を書き、何を書かないか

**書く**: 利用者から見た振る舞いが変わったもの。

- 新しいコマンド / オプション / GUI 画面、既存の出力や既定値の変化
- 利用者が踏みうる不具合の修正、性能の変化、非互換 (breaking change)
- **配布物 (Portable ZIP) の中身の変化** — 同梱依存の版、同梱 README の内容など

**書かない (entry 不要、裁定 R7 / 2026-08-11)**: 利用者から見た振る舞いが変わらないもの。

- CI job / ガード / チェックスクリプトの新設・変更
- 開発者向け doc (`docs/developer-setup.md` / `docs/l2-workflow.md` 等)、skill (`.claude/skills/**`)、hook
- テスト、lint / 型チェックの版 pin、内部 refactor

これらの記録は **PR 本文と issue** に残る。CHANGELOG に重複させない。`### Internal` 節は過去バージョン (0.1.1 / 0.2.0 / 0.3.0) の歴史記録として残すが、**新規バージョンでは使わない** — 上記のとおり Release 本文に丸ごと出てしまい、読者には意味を持たないため。

> **判断の分かれ目は「利用者の環境で観測できるか」**。例: lint ツールの pin は観測できないので書かない。配布 ZIP に同梱される cv2 の版は検出結果の再現性として観測できるので書く。

### 書き方 — 3 部構成

1 entry は **(a) 太字の機能名 + issue 番号 → (b) 使い方 2-3 行 → (c) 詳細リンク** の 3 部で書く。

```markdown
- **<太字の機能名>** ([#N](https://github.com/Idios/kobutachan-allaganeye/issues/N)):
  <利用者の語彙で「何ができるようになったか / 何が変わったか」を 2-3 行>
  詳細は [<リンク名>](<spec / doc への相対パス>) を参照。
```

- **(a) 太字の機能名は必須**。`### Added` の太字機能名は機能告知 drift 検査 (spec §5.2 G2-2 / #944) が機能名集合を抽出する SSoT でもあるため、**太字を外すとその機能が検査対象から静かに消える**
- **(b) は利用者の語彙で 2-3 行**。設計の説明を CHANGELOG 側に書かない
- **(c) 詳細は spec / doc へのリンクで送る**

**spec 側へ寄せる語彙 (CHANGELOG に出さない)**:

| 分類 | 例 |
| --- | --- |
| 内部アルゴリズム名・段階名 | `V0`-`V4` / `quorum` / `anchor` / `presence` / `tri-state` / 内部 fallback の段階名 |
| GT・テスト名 | ground truth データセット名、`tests/baselines/**` のパス、pytest marker 名 (`slow_detect` 等)、baseline / GT 突合ハーネスの名前 |
| tolerance 値・しきい値 | 境界許容秒数、quorum 比率、輝度しきい値などの数値。利用者が調整できる CLI オプションの既定値は**除く** (それは利用者から見える振る舞い) |

利用者はこれらの語で自分の症状を検索しない。`(#N)` の issue / PR 番号は常に添える。

### 発火点 (規約が読まれる場所)

本規約は宣言だけでは発火しないので、以下の 3 箇所に紐づける。

1. **[`.claude/skills/release/SKILL.md`](../.claude/skills/release/SKILL.md) §Step 3 項目 2** — `## [Unreleased]` を `## [<新バージョン>] - YYYY-MM-DD` へ改名する手順に、本節への参照と `check_changelog_style.py` の実行を含める。**改名を飛ばすと `check_version_consistency.py --tag` が「該当版の節がありません」で落ちる**ので、この手順は避けて通れない
2. **[`.github/pull_request_template.md`](../.github/pull_request_template.md) §関連ドキュメント / マトリクス更新** — PR 作成時に「CHANGELOG entry の要否を判断した」ことを記録する。**この box は CI の counting 対象外である** (#936 / #967 で確定した blast radius は `## 受け入れ条件` と `#### Self-Test Report` の 2 群のみ)。したがってこれは**人手ゲート**であり、未記入でも `validate-checklist` は赤にならない
3. **機械検査**: [`scripts/check_changelog_style.py`](../scripts/check_changelog_style.py) — CI (`ci.yml` の `changelog-style` job) が走査対象セクションを検査する。**3 点セットの ③ (発火側の red 実証) を担うのはこれだけ**で、1 と 2 は読まれる場所の確保にすぎない

### 非実施時の記録義務

**内部変更のみの PR で entry を書かなかった場合、PR 本文に 1 行残す**:

```text
CHANGELOG entry: 不要 (内部専用 — <CI ガード / 開発 doc / skill / テスト / 版 pin のいずれか>)
```

無記載では「判断して不要と決めた」と「書き忘れた」が区別できない。**Track D (version bump) は、この行を持たない PR が当該リリースに含まれていないことを確認する。**

### 機械検査が見ていない集合

`scripts/check_changelog_style.py` は形と語彙しか見ない。以下は構造的に検査外である。

- **entry の内容が正しいか** — 書かれた振る舞いが実装と一致するかは見ない
- **書くべき entry が欠けているか** — 「利用者に見える変更なのに entry が無い」は検出できない。これは上記「非実施時の記録義務」の 1 行と Track D の確認で担保する人手ゲートである
- **既リリース済みセクション** — `## [Unreleased]` と最新 version セクション以外は走査しない (裁定 D7 の既リリース節不可侵。v0.3.0 の `### Added` には内部用語が 14 箇所あり、遡って直さない方針のため scope を切らないと恒久 red になる)
- **禁止語のリスト漏れ** — 語彙リストは人手で維持する。新しい内部段階名が生まれても自動では追加されない

## ブランチ保護と required status checks (#947)

CI の起動条件 (workflow の `on:`) と、**red を実際にマージ阻止へ変換する機構** (repository ruleset) は別物である。前者だけでは「赤いまま Merge ボタンを押せる」状態が残るため、両方を揃えて初めてゲートになる。

**ruleset は repo 外設定 (GitHub の Settings > Rules) にあり、リポジトリのファイルとして版管理されない。** そのため本節を SSoT とし、設定を変更したときは本節も同時に更新する。

### 現行の ruleset (2026-08-20 投入)

| 項目 | 値 |
| --- | --- |
| ruleset 名 | `required-status-checks` |
| enforcement | `active` |
| 対象 ref | `refs/heads/main` / `refs/heads/release/*` (下記 §対象 ref の選び方 を参照) |
| rule | `required_status_checks` |
| strict (branch up-to-date 要求) | `false` (無関係な PR のマージのたびに全 PR の rebase を強いるため) |
| `do_not_enforce_on_create` | **`true`** — これが無いと `release/vX.Y.Z` ブランチの**作成そのもの**が拒否される (下記実測表) |
| bypass actors | なし (repository admin も required 緑まで手動マージできない) |

required に指定する check は以下の 8 件。

| check 名 | 定義元 | 役割 |
| --- | --- | --- |
| `python` | `.github/workflows/ci.yml` | ruff / pyright / pytest |
| `gui-frontend` | `.github/workflows/ci.yml` | eslint / tsc / vitest / vite build |
| `gui-rust` | `.github/workflows/ci.yml` | cargo check |
| `installer-pester` | `.github/workflows/ci.yml` | installer スクリプトの Pester テスト |
| `markdownlint` | `.github/workflows/markdownlint.yml` | markdownlint-cli2 |
| `validate-checklist` | `.github/workflows/pr-checklist.yml` | PR 本文の Self-Test Report / チェックボックス |
| `feature-announcement` | `.github/workflows/ci.yml` | 出荷 CLI サブコマンドが入口 doc で告知されているか (#944) |
| `screenshot-freshness` | `.github/workflows/ci.yml` | README スクショが現行 GUI ソースから撮られているか (#944) |

**required に入れる check は「全 PR で必ず report される」ものに限る。** GitHub は workflow が paths filter で丸ごと skip された場合その check を report しないため、条件付き起動の workflow を required にすると、条件に当たらない PR が `Expected — waiting for status` のまま恒久的にマージ不能になる。`markdownlint` を required にするにあたり [`markdownlint.yml`](../.github/workflows/markdownlint.yml) の paths filter を撤去したのはこのため。

### 対象 ref の選び方 (実測、2026-08-20)

**`required_status_checks` は PR のマージだけでなく、対象 ref への `git push` すべてに適用される。** 保護対象を増やす前に、その ref へ**直接 push する手順が残っていないか**を必ず確認すること。使い捨て ruleset (対象 `refs/heads/rulesetprobe/*`、required 8 件、後片付け済) での実測は以下のとおり。

| 操作 | `do_not_enforce_on_create` | 結果 |
| --- | --- | --- |
| 新規ブランチ作成 (`git push origin <sha>:refs/heads/rulesetprobe/creation`) | `false` | **reject** — `GH013: Repository rule violations found` / `8 of 8 required status checks are expected` |
| 同上 | `true` | 通る (exit 0) |
| 既存ブランチへの追加 push | `true` | **reject** (同じ `GH013`)。`do_not_enforce_on_create` は**作成時しか免除しない** |

**この 3 行目が効く箇所が [`/release` SKILL.md](../.claude/skills/release/SKILL.md) §Step 4 (CHANGELOG 見出し日付の commit) である。** 初版 (2026-08-20) では対象を `main` のみに絞ってこれを回避していたが、**Step 4 を PR 経由へ改めたうえで `release/*` を保護対象へ加えた** (Idios 判断 2026-08-20)。`do_not_enforce_on_create: true` はブランチ作成 (`git push -u origin release/vX.Y.Z`) を通すために必須。

`develop-*` は**まだ保護していない**。裁定 D4 により patch release のリリース PR head は `develop-<version>` であり、そこへの Step 4 の直接 commit が現行手順として残っているため。`develop-*` も保護する場合は、**Step 4 を patch release でも PR 経由に統一するのが前提**になる。

### 変更手順 (順序厳守)

1. **先に workflow 側を直す** — 新しい base パターンを足す場合は `ci.yml` / `markdownlint.yml` の `pull_request.branches` を先に更新し、その変更が対象ブランチへマージされていること
2. **その後に ruleset を更新する** — 逆順にすると、workflow が起動しない組み合わせで check が never-reported になりマージ不能に陥る

### 確認コマンド

```bash
gh api 'repos/Idios/kobutachan-allaganeye/rulesets?includes_parents=true'
```

`[]` が返るなら **保護は 1 つも効いていない** (本節の記述と実態が乖離している)。個別 ruleset の中身は `gh api repos/Idios/kobutachan-allaganeye/rulesets/<id>` で確認する。

### この機構が見ていない集合

- **`develop-*` 宛の PR は 1 本もマージ阻止されない。** 保護対象は `main` と `release/*` なので、**日常の開発 PR (base=`develop-*`) は CI が red のままでも手動マージできる**。この機構が実際に止めるのは「`release/*` へ入る瞬間」と「`main` へ入る瞬間」の 2 箇所だけで、それ以前の全 PR で CI は「気づくための信号」に留まる。これは上記 §対象 ref の選び方 で意図的に受け入れた縮退である (解消には Step 4 の patch release 側も PR 経由へ統一するのが前提)
- **v0.3.1 では `release/*` の保護が 1 度も発火しない。** 裁定 D4 により v0.3.1 は `release/v0.3.1` を作らず `develop-0.3.1` 直行のため、`release/*` を base とする PR も、`release/*` への push も存在しない。**次の minor release が最初の実発火**になる
- **check が report されたかしか見ない。** paths filter で skip された job の妥当性も、job の中身が実際に何を検査しているかも見ない
- **required の 8 件を report できるのは、head 側が現行の workflow を持つ PR だけ。** `pull_request` の workflow は merge ref (base + head) から読まれるため、`develop-*` / `release/*` から出す通常のリリース PR は問題ない。一方 **`main` から直接切った branch を head にする PR (hotfix 等) は、`main` 上の workflow にまだ無い job が never-reported になり恒久的にマージ不能になる**。実例: 2026-08-20 時点の `main` の `ci.yml` には `doc-code-refs` / `feature-announcement` / `screenshot-freshness` が無く、`markdownlint.yml` も paths filter を持ったままである (v0.3.1 のリリース PR で解消する)
- **required の 8 件以外は red でもマージを止めない。** `hook-test` / `doc-tauri-commands-drift` / `doc-error-hint-drift` / `doc-code-refs` / `shellcheck` / `version-check` / `cargo audit` / `npm audit` / `dependency review` は informational
- **対象 ref に列挙しないブランチは無保護。** 将来 `hotfix/*` 等を切る場合は本節と workflow の両方を更新しないと素通りする
- **ruleset は repo 外設定なので、GitHub 側で誰かが無効化しても diff に現れない。** 上記の確認コマンドを `/release` Step 0 で実行することが唯一の検知経路

## レイヤーリリース受け入れゲート

各リリース (minor / patch) (`release/vX.Y.Z → main`) の実行前に、本節のチェックリストを全件達成する。共通項目はすべてのリリース (minor / patch) に適用、レイヤー固有項目は対応するバージョンで適用する。`/release` skill の Step 0 で本節を参照する (`.claude/skills/release/SKILL.md`)。

> **patch release にも適用する** (裁定 D5)。本節は当初「minor リリース」限定の文面だったため、patch release (v0.M.N → v0.M.(N+1)) では §共通項目 が 1 度も読まれない状態だった。§Patch release の Track 構造 で patch を正式運用に組み込んだ以上、共通項目は minor / patch の双方で達成する。

### 共通項目 (全リリース: minor / patch)

- [ ] `develop-x.x.0` 上で対象スコープの全 PR がマージ済み
- [ ] CI 全ジョブ (Python / GUI frontend / GUI Rust / Pester) が**リリース PR の HEAD** (`release/vX.Y.Z` tip) で緑 — develop tip は release ブランチに載せた出荷直前 commit を含まないため基準にしない
- [ ] **タグ打ち直前の security 再チェックを実施した** ([`/release` SKILL.md](../.claude/skills/release/SKILL.md) §Step 5) — `security-audit.yml` の 3 job (`cargo audit` / `pip audit` / `npm audit`) が**リリース PR の HEAD** で緑、かつ Dependabot の open alert がゼロまたは Idios が既知として了承済み。実施しなかった場合はリリース PR 本文に `security 再チェック: 非実施 (理由: …)` を 1 行残す。**この工程が見ていない集合**は同 §Step 5 に列挙してある (再チェックからタグまでの窓は 0 にできない / alert は既定ブランチしか scan しない / cron は最悪 24h 遅延) (#950)
- [ ] required status checks の ruleset が生きている (`gh api 'repos/Idios/kobutachan-allaganeye/rulesets?includes_parents=true'` が非空で、[§ブランチ保護と required status checks](#ブランチ保護と-required-status-checks-947) の 8 件を含む) — ruleset は repo 外設定で diff に現れないため、無効化を検知できるのはこの確認だけ (#947)
- [ ] [バージョン保持箇所](versioning.md#バージョン管理場所)が**全箇所**`x.y.0` に更新されている (`python scripts/check_version_consistency.py` が exit 0)
- [ ] `CHANGELOG.md` に対象バージョンセクションが存在 (**日付 = タグ打ち日 JST** (§タグ運用) / 主要変更点 / breaking changes)
- [ ] 対象バージョンセクションの entry が **§CHANGELOG entry の記述規約 に適合**している — 掲載範囲が利用者から見た振る舞いの変化に限られ、3 部構成 (太字機能名 + issue 番号 / 使い方 2-3 行 / 詳細リンク) で書かれ、内部用語が spec 側へ寄せられていること (`python scripts/check_changelog_style.py` が exit 0。ただし同 script は**語彙と節の形しか見ず、entry の欠落や内容の正しさは見ない**ので、読者視点の適合はここで人が確認する)
- [ ] `deferred` ラベル付き issue を全件レビュー済 (close、または次バージョン `deferred` 維持判断、または当該バージョンに引き取り)
- [ ] 対象レイヤースコープの `P1-high` issue 全 close + `P2-medium` issue 全 close または `deferred` ラベル付与

### v0.2.0 (L2: GUI サポート + ゼロ環境構築配布) 固有項目

- [ ] [#484](https://github.com/Idios/kobutachan-allaganeye/issues/484) L2 E2E 統合テストチェックリスト全 PASS ([`docs/l2-e2e-checklist.md`](./l2-e2e-checklist.md) を Idios 実機で全件実施)
- [ ] [`docs/axum-video-server.md`](./axum-video-server.md) 新設 + 内容確認 (Range / token / async lifecycle / 脅威モデルの記述完備)
- [ ] [`docs/l2-e2e-checklist.md`](./l2-e2e-checklist.md) 新設 + 全 PASS 確認 (Idios 実機実施、smoke / E2E / 性能 / 配布物検証)
- [ ] Portable ZIP (`allaganeye-v0.2.0-windows.zip`) の手動 smoke は [`docs/l2-e2e-checklist.md §3 T1`](./l2-e2e-checklist.md) を参照 (CLI / GUI 起動確認は同チェックリストに集約済)
- [ ] `l1-residual` ラベル全件 ([#412](https://github.com/Idios/kobutachan-allaganeye/issues/412) / [#413](https://github.com/Idios/kobutachan-allaganeye/issues/413) / [#433](https://github.com/Idios/kobutachan-allaganeye/issues/433) / [#434](https://github.com/Idios/kobutachan-allaganeye/issues/434) / [#435](https://github.com/Idios/kobutachan-allaganeye/issues/435) / [#436](https://github.com/Idios/kobutachan-allaganeye/issues/436) / [#440](https://github.com/Idios/kobutachan-allaganeye/issues/440) / [#553](https://github.com/Idios/kobutachan-allaganeye/issues/553) / [#576](https://github.com/Idios/kobutachan-allaganeye/issues/576)) の deferred 判断完了 (close または `deferred` ラベル付与)
- [ ] `l2a-gui` / `l2b-installer` / `l2-workflow` スコープラベルの open issue で `P1-high` がゼロ
- [ ] `docs/guard-integration.md` §5 「外部動画データの検査」運用が成立 (allaganeye-guard 独立リポジトリの最新版が利用可能)

### v0.3.0 (L3: 配信形式対応 + 性能改善) 固有項目

- [ ] 2026-06-10 full audit の監査 P1 対応 ([audit-remediation spec](./superpowers/specs/2026-06-10-audit-remediation-design.md) Wave 1) が全クローズ: [#812](https://github.com/Idios/kobutachan-allaganeye/issues/812) / [#813](https://github.com/Idios/kobutachan-allaganeye/issues/813) / [#814](https://github.com/Idios/kobutachan-allaganeye/issues/814) / [#815](https://github.com/Idios/kobutachan-allaganeye/issues/815) / [#816](https://github.com/Idios/kobutachan-allaganeye/issues/816) / [#817](https://github.com/Idios/kobutachan-allaganeye/issues/817) / [#818](https://github.com/Idios/kobutachan-allaganeye/issues/818)。G4 は [#805](https://github.com/Idios/kobutachan-allaganeye/issues/805) の段階1 (metadata 痕跡) で消化済みのため、#805 自体の close は本ゲートの対象外 (残 scope は #805 を参照)

§v0.3.0 以降のレイヤー固有ゲート枠組み の表が挙げていた v0.3.0 の想定ゲート項目を、リリース PR [#924](https://github.com/Idios/kobutachan-allaganeye/pull/924) で以下のとおり確定した (同節末尾の「確定後は本 doc に追記して恒久化する」に従う)。

**自動ゲート (G)** — リリース PR の HEAD を独立ワークツリーに checkout して実行する。実行前後で `HEAD` が一致することを guard で確認し、実行中に flip した場合は結果を無効として再実行する ([worktree の branch flip は長時間ゲートを silent に無効化する](l2-workflow.md))。各ゲートは **collect 件数が 0 でないこと**も確認する (`pyproject.toml` の `addopts = "-m 'not slow and not baseline_regen'"` により、marker 指定を省いたコマンドは全件 deselect されて「0 件実行のまま緑」になる)。

- [ ] **G1: OBS baseline bit-exact 回帰** — `pytest -m "slow_detect and not baseline_regen" tests/test_v030_baseline_regression.py`。5 本の OBS 録画 (obs-20260116 / 118 / 119 / 127 / 209) の検知結果が pin 済み baseline と一致すること。**本ゲートに masked / VTuber の動画は含まれない** (`_CLASS_A_BASELINES` は OBS のみ)。§v0.3.0 以降のレイヤー固有ゲート枠組み の表にある「masked baseline 検知 ground truth 一致」という当初想定の表現は実態と異なるため、masked の根拠は下記の注記を参照
- [ ] **G2: minimap 領域提案の回帰** — `pytest -m "slow_detect and not baseline_regen" tests/test_areamap_slow.py`。エリアマップ window の seed 検出と per-match consensus の提案精度を検証する。**crop / encode 経路は対象外**で、切り抜き映像そのものの妥当性は M3 で目視確認する。**9 件が collect され、SKIP ゼロで PASS することを確認する** (marker を省くと `pyproject.toml` の `addopts = "-m 'not slow and not baseline_regen'"` により全件 deselect され、無検証のままゲートが通る)。GT 動画が実機から欠けている場合、該当ケースは hard fail ではなく SKIP になる ([#992](https://github.com/Idios/kobutachan-allaganeye/issues/992))。SKIP が出たときは検証されていない GT があるということなので、`tests/baselines/source-videos.sha256.json` の台帳から動画を復元して再実行する (§サンプル動画/GT データの保全 は [`docs/testing-guide.md`](testing-guide.md) 参照)。欠落を許容する判断をした場合のみ `tests/test_areamap_slow.py` の `_KNOWN_MISSING_GT_IDS` に理由付きで記録し、その旨をリリース PR 本文に残す
- [ ] **G3: VTuber timeline GT 回帰** — `pytest -m "slow_detect and not baseline_regen" tests/test_vtuber_gt_regression.py`。6 配信者 / GT 67 試合に対する recall と spurious を検証する。`--vtuber` を当該リリースで公開扱いにする場合は必須 (`/release` Step 0c で判断)。**検出ロジック / GT データ / ハーネスのいずれかを触った commit の後は再実行する**。`allaganeye/commands/split_matches.py` の `_VTUBER_ALGO_VERSION` の bump が再実行要否の目印になる

> **masked 検出の根拠 (v0.3.0 時点)**: masked は専用の baseline ゲートを持たない。根拠は PR [#915](https://github.com/Idios/kobutachan-allaganeye/pull/915) で実施した 3 サンプルの不変性確認 (masked fallback 発動時の segment 数が再実行間で一致) に留まり、**出力の正しさは検証していない**。G1 と同形の pin 済み baseline への置き換えは [#925](https://github.com/Idios/kobutachan-allaganeye/issues/925) で追跡する。

**手動検証 (M)** — GPU / 長時間動画 / GUI / 配布物は mock 不可のため Idios 実機で実施する (Iron Law 6)。PR 本文には machine-unverifiable として plain bullet で記録する。

- [ ] **M1: export 並列の encoder 出力 visual spot check** — `--codec h264` で並列書き出しした MP4 を再生し、映像 / 音声 / 尺に破綻がないことを確認する
- [ ] **M2: Portable ZIP 起動回帰** — 配布 ZIP を展開し、`allaganeye.bat` の引数なしダブルクリック (GUI 起動) と `allaganeye.bat --version` (CLI 起動) の両方を確認する。タグ push 前はリリース PR の CI artifact、タグ push 後は Release 添付の本番 ZIP で二段確認する
- [ ] **M3: minimap crop の目視確認** — `minimap --region` で切り抜いた MP4 を再生し、エリアマップが意図した領域に収まっていることを確認する (G2 は提案モードのみを検証するため、crop 経路はここでしか担保されない)

### v0.3.0 以降のレイヤー固有ゲート枠組み

各レイヤー固有のチェックリストは「v0.x.0 (L?) 固有項目」節として §レイヤーリリース受け入れゲート 配下に追加していく。各レイヤー特有の品質ゲートを当該リリース直前のレビューで確定する。

| バージョン | レイヤー | 想定ゲート項目 |
| --- | --- | --- |
| v0.3.0 | L3 (new): 配信形式対応 + 性能改善 | **確定済 → 前節「v0.3.0 (L3) 固有項目」の G1-G3 / M1-M3 を参照**。当初の想定は「masked baseline 検知 ground truth 一致 + minimap 切抜き検証 + export 並列で encoder 出力 visual spot check + Portable ZIP 起動回帰」だったが、確定時に masked baseline が未整備であること (→ [#925](https://github.com/Idios/kobutachan-allaganeye/issues/925)) と minimap の自動ゲートが提案モードのみを覆うことが判明し、実態に合わせて再定義した |
| v0.4.0 | L4 (former L3): メタデータ化 | キルログ OCR / 音声認識統合の精度ベンチ、metadata schema 拡張の互換性検証 |
| v0.5.0 | L5 (former L4): 価値評価 | ローカル ML model 評価指標、サンプル動画群での評価分布 |
| v0.6.0 | L6 (former L5): 自動編集 | クリップ生成成功率、投稿提案の妥当性レビュー |

各レイヤー固有のゲート項目は、当該リリース PR の PR 本文または「v0.x.0 (L?) 固有項目」節で確定する。確定後は本 doc に追記して恒久化する。

## レイヤー間の移行手順

各レイヤー完了時:

1. **§レイヤーリリース受け入れゲート** のチェックリストを全件達成 (共通項目 + 当該レイヤー固有項目)
2. `develop-x.x.0` から `release/vX.Y.Z` を切り、`release/vX.Y.Z → main` のリリース PR を作成・マージ
3. `main` にタグを打つ (`v0.x.0`)
4. GitHub Release を作成（変更内容サマリ付き、`release.yml` 自動 or `docs/release-process.md` §手動リリース手順）
5. `main` から次バージョンの `develop-x.x.0` ブランチを作成し、その時点で[バージョン保持箇所](versioning.md#バージョン管理場所)を**全箇所**まとめて `x.y.0` に更新（`.dev` 等の pre-release 識別子は付けない。PyPI 未公開のため不要）。更新後に `python scripts/check_version_consistency.py` で全箇所一致を確認する
6. 次レイヤーの Issue を作成し、作業開始

## 手動リリース手順 (CI 迂回)

通常のリリースは `git push origin v<x.y.z>` をトリガーに [`.github/workflows/release.yml`](../.github/workflows/release.yml) が自動実行する (上記 §タグ運用 参照)。本節は CI が一時的に使えない場合 (GitHub Actions 障害、`release.yml` 自体の不具合など) の代替手順として、手動でビルド + Release 作成を行う方法を記載する (#461)。

### 前提

- ローカル環境に Python 3.11.9 + PowerShell (Windows PowerShell 5.1 以上 or pwsh 7+) + Git がインストール済み ([Developer Setup](developer-setup.md) §1)
- `develop-x.x.x` で全テスト pass、`release/vX.Y.Z → main` PR マージ済み
- 公開対象バージョン (`x.y.z`) と[バージョン保持箇所](versioning.md#バージョン管理場所)が**全箇所**一致していること (`python scripts/check_version_consistency.py --tag vx.y.z` が exit 0。CI を迂回する手順のため `version-check` job の代わりに手元で実行する)

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

   `dist/allaganeye-vx.y.z-windows.zip` が生成される (PyInstaller `--onedir` で frozen 化した CLI (`allaganeye/` 配下に Python interpreter + 全依存を内包、#752) + BtbN LGPLv3 FFmpeg n8.1 + 各 LICENSE 同梱。FFmpeg は SHA256 検証付き)。

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

## Patch release の Track 構造

v0.M.N → v0.M.(N+1) の patch release を **Track A-D 構造**で並列化する。v0.2.1 (PR #759-#774) で確立した運用パターン。

### 適用条件

- security alert / Dependabot patch
- deferred UX 吸収 (`/release` skill Step 0c (M9) で「次 patch 吸収」と判定された issue 群)
- CI / build gate 追加
- 緊急 bug fix の集約

minor release (v0.M.0 → v0.(M+1).0) や major refactor は本 Track 構造の対象外、別 plan で扱う。

### Track 規約

| Track | 内容 | 並列性 | reference (v0.2.1) |
| --- | --- | --- | --- |
| Track 0 | spec PR (`docs/superpowers/specs/<date>-v0.M.N+1-patch-design.md`) | 直列 (最初) | #759 |
| Track A | security / dependency (Dependabot / cargo audit / npm audit) | 並列可 | #760 |
| Track B | deferred UX 吸収 (Step 0c で取り込み判定された issue 群) | 並列可 | #764 / #766 / #768 / #772 |
| Track C | CI / build gate 追加 (security-audit.yml 等) | 並列可 | #763 |
| Track D | version bump + CHANGELOG | 直列 (最後) | #773 |

Track A / B / C は worktree 別 / 並列着手可能。Track D は他全 Track のマージ後に直列実行する (version bump が他 PR と base 衝突しないようにするため)。

### `/release` skill との連携

Step 0a 受け入れゲート → Step 0b deferred 全件取得 → Step 0c 1 件ずつ (a) 次release吸収 / (b) deferred 継続 / (c) close 分類。Step 0c で (a) と分類された issue 群が **Track B 吸収候補** となり、spec PR (Track 0) の table に記録される。

詳細な Step 0c 運用は [`.claude/skills/release/SKILL.md`](../.claude/skills/release/SKILL.md) を参照。

### 参考: v0.2.1 patch release (2026-05-16)

v0.2.0 release 後の patch として、4 Track + spec を計 10 PR (#759 spec / #760 Track A / #763 Track C / #764, #766, #768, #772 Track B / #769, #771 Track C 軽量化 / #773 Track D) で完結した実例。
