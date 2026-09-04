# CI: Security Audit Workflow

`.github/workflows/security-audit.yml` の運用 note。

## 目的

PR を `develop-x.x.x` や `main` にマージする前に、cargo audit + npm audit を自動実行し、Dependabot より早く脆弱性を検出する。

ただし本 workflow は Dependabot の**上位互換ではない**。参照 DB と閾値の差により、green でも Dependabot alert が残るケースが構造的に存在する (§[Dependabot との関係](#dependabot-との関係) 参照)。

## 発火条件

- `pull_request` trigger
- paths: `gui/src-tauri/Cargo.lock`, `gui/src-tauri/Cargo.toml`, `gui/package-lock.json`, `gui/package.json`, `pyproject.toml`, `constraints.txt`, `scripts/installer/requirements-pyinstaller.txt`, `.github/workflows/security-audit.yml`, `.github/dependabot.yml`
- `schedule: cron` (daily `17 3 * * *` UTC、#950)
- `workflow_dispatch` で手動実行も可能

Python manifest は #868 で追加した。それ以前は Python 依存だけを変更する PR で本 workflow 自体が起動せず、pip の advisory が PR 段階でまったく検査されていなかった。

`schedule` は #950 で追加した。PR が 1 本も来ない期間でも既定ブランチの依存状態を時間軸で監視するため。**`schedule` は既定ブランチ (`main`) 上の workflow ファイルでしか有効にならない** (GitHub の仕様) ので、`develop-*` へ merge しただけでは定期実行は始まらない。

## ジョブ

| ジョブ | コマンド | fail 条件 |
| --- | --- | --- |
| cargo-audit | `cargo audit` (default) | vulnerability (CVE 相当) 検出のみ fail。warning (unmaintained / unsound) は通過 |
| pip-audit | `pip-audit` (install 済み環境を監査) | **severity を問わず advisory に 1 件でも当たれば fail** (#868) |
| npm-audit | `npm audit --audit-level=high` | high 以上の advisory 検出。dev-only の moderate/low は warning として通過 |
| dependency-review | `actions/dependency-review-action@v5.0.0` (`fail-on-severity: moderate`) | **base→head で追加された**依存が moderate 以上の GitHub Advisory に該当したら fail (Refs #862) |

### pip-audit を追加した理由と、manifest を静的に読まない理由 (#868)

**GitHub の dependency graph は Python について実用にならない。** 2026-08-20 に `gh api repos/Idios/kobutachan-allaganeye/dependency-graph/sbom` を実測した結果:

| manifest | graph への登録 | resolved version |
| --- | --- | --- |
| `scripts/installer/requirements-pyinstaller.txt` (exact pin) | される | **あり** (`pyinstaller 6.20.0` / `pyinstaller-hooks-contrib 2026.5`) |
| `pyproject.toml` (`dependencies` / dev extras) | される | **なし** (`typer` / `click` / `numpy` / `scipy` / `opencv-python-headless` / `pytest` / `ruff` / `pyright` / `jsonschema` / `setuptools` / `datamodel-code-generator` はすべて version が `-`) |
| `constraints.txt` (exact pin) | **されない** | — (`black` / `isort` / `rich` は graph に 1 件も存在しない) |

advisory の突合には resolved version が要るため、**Dependabot alert も `dependency-review` job も、Python 依存についてはほぼ原理的に発火しない**。実際 Dependabot alert 28 件の内訳は npm 24 / rust 4 で、**pip は 1 件も出たことがない**。

したがって `pull_request.paths` に `pyproject.toml` を足すだけでは、workflow は起動するが走る 3 job のどれも変更された Python 依存を見ないまま緑になる = **false-green を作るだけ**になる。実環境を監査する pip-audit を同時に入れて初めて穴が塞がる。

導入時点の実測では該当ゼロ (`pytest 9.0.2` の GHSA-6w46-j5rx-g56g medium が唯一の候補だが、`pyproject.toml` は `pytest>=8` で pin していないため CI は patched の 9.0.3 以降を引く)。恒久 red にはならない。

#### 誤検知・対応不能な advisory が出たときの許容ルール

pip-audit は severity 閾値を持たないため、`npm audit --audit-level=high` のような「低い severity は素通し」ができない。対応不能な advisory が出た場合は `security-audit.yml` の pip-audit step に `--ignore-vuln GHSA-xxxx-xxxx-xxxx` を追記し、**同じ箇所に (1) なぜ対応できないか (2) いつ見直すか を必ずコメントで書く**。理由の無い ignore は禁止 (恒久 ignore が既成事実化して gate が黙るため)。

#### 監査対象の内訳 (2 invocation ある理由)

pip-audit は 2 回呼ぶ。**1 回では `pull_request.paths` に載せた Python manifest を全部はカバーできない。**

| invocation | 監査対象 | カバーする manifest |
| --- | --- | --- |
| `pip-audit` (引数なし) | `pip install -e ".[dev]" -c constraints.txt` した実環境 | `pyproject.toml` (`dependencies` + dev extras) / `constraints.txt` |
| `pip-audit -r scripts/installer/requirements-pyinstaller.txt` | requirements を解決した結果 (install はしない) | `scripts/installer/requirements-pyinstaller.txt` |

**2 つ目が要るのは、`pyinstaller` / `pyinstaller-hooks-contrib` が `pyproject.toml` の dev extras に入っていないため** (`pip install -e ".[dev]"` した環境に `pip show pyinstaller` すると `Package(s) not found` を返すことを実測)。同ファイルを paths filter に載せておきながら監査しないと、「trigger は塞いだが中身は誰も見ていない」という false-green になる。Portable ZIP は PyInstaller で frozen application を作るので、この依存は**出荷物に直接効く**。

#### OS matrix にしている理由

本 job は `ubuntu-latest` と `windows-latest` の **両方**で走る。Python の依存解決は環境マーカーで OS ごとに変わるため、ubuntu だけで監査すると**出荷物にしか入らない Windows 限定の transitive が永久に無検査**になる。

| 依存経路 | Windows 限定 transitive |
| --- | --- |
| `pyinstaller` | `pefile` / `pywin32-ctypes` |
| `typer` → `click` | `colorama` |

Portable ZIP は windows runner でビルドするので、**出荷物の依存集合は windows 側が正**である。2026-08-20 時点では上記いずれにも advisory は存在しない (GitHub Advisory DB を `affects=<pkg>` で実測、全バージョンで 0 件) が、「今ゼロ」は「今後もゼロ」を意味しない。

なお step の `shell:` に `${{ matrix.* }}` を書くと phantom run 化するため、shell は job の `defaults` に静的値で逃がしてある (#786 / #788 の教訓)。

**Windows leg には `PYTHONUTF8=1` が必須である。** `pip-audit -r` が内部で使う `pip_requirements_parser.auto_decode()` は、BOM も PEP 263 の coding cookie も持たないファイルを **locale の既定エンコーディング**で decode する。windows runner の既定は cp1252 なので、`requirements-pyinstaller.txt` の UTF-8 日本語コメントで落ちる。

```text
UnicodeDecodeError: 'charmap' codec can't decode byte 0x81 in position 137:
character maps to <undefined>
```

(2026-08-20 に実 runner で観測。matrix 導入前は ubuntu でしか走っていなかったため表面化していなかった。)

UTF-8 mode (PEP 540) にすると `locale.getpreferredencoding(False)` が UTF-8 を返すので解決する。**出荷物のビルド入力である requirements ファイル自体は書き換えない** — pip / PyInstaller 側の読み取り挙動に影響を与えないため。ローカルの Windows で `pip-audit -r` を叩く場合も同じ env が要る。これは [`AGENTS.md` §encoding boundary audit checklist](../AGENTS.md) の 3 層目 (OS code page) に該当する。

#### この job が見ていない集合

- dev extras を含む実環境全体を監査するので、配布物 (Portable ZIP) に同梱されない dev 依存の advisory でも fail する
- PyPI に無い依存 (ffmpeg 等の OS バイナリ) は対象外
- `-c constraints.txt` で固定していない依存は「その日の最新」を監査するため、**同じ commit でも実行日によって結果が変わりうる**
- `--strict` を付けていないため、editable install した本体は skip される (PyPI 由来でないので監査対象にならない)
- **監査するのは `ubuntu-latest` / `windows-latest` の 2 つだけ。** macOS 限定の依存は対象外だが、本プロジェクトは Windows のみ対応なので実害はない
- **ZIP ビルド時に PyInstaller が frozen application へ取り込む内容までは見ない。** 監査対象は PyPI パッケージの版であって、bundle された成果物ではない

### dependency review を追加した理由 (v0.3.0)

`cargo audit` / `npm audit` はそれぞれ RustSec / npm registry を参照するため、GitHub Advisory Database にしか無い advisory を構造的に検出できない (下記 §「本 workflow が green でも Dependabot alert が出るケース」 の 1)。本 job は Dependabot と同じ GitHub Advisory Database を参照するので、この差を PR 段階で埋める。

閾値を `moderate` にしたのは、動機となった `serde_with` GHSA-7gcf-g7xr-8hxj が medium (= GHSA の `moderate`) であり `high` では取りこぼすため。`npm audit --audit-level=high` より厳しいが、本 workflow は manifest を変更した PR でしか起動しないので、影響は依存を触る PR に限定される。

`fail-on-scope` は既定 (`runtime, development`) が **`unknown` を除外する**ため、`runtime, development, unknown` を明示している。現状の依存グラフは cargo=runtime / npm=development / pip=runtime で `unknown` は 0 件だが、scope を解決できない依存が将来現れたときに silent に素通りさせないための予防。

本 job は base / head を持つイベントでしか動かないため `if: github.event_name == 'pull_request'` を付けている。これが無いと本 workflow の `workflow_dispatch` 手動実行が常に fail する (`cargo-audit` / `npm-audit` は従来どおり手動実行できる)。

本 action は moving major tag (`v4` / `v5` 等) を発行しておらず `v5.0.0` のような完全版タグしか存在しないため、バージョンは exact pin で、更新は手動 bump が必要。

#### この job が no-op でないことの実証 (Refs #862)

保護機構は「不発でも green」なので、発火する側を実測した。action が消費するのと同じ dependency review API を、設定と同じ閾値 (`fail-on-severity: moderate` / `fail-on-scope: runtime, development, unknown`) で、脆弱バージョンが実際に導入された履歴コミット対 (v0.2.0 リリース merge `dc9e24f...22031f6`) に対して評価したところ、**追加依存 22 件が gate に該当**した。その中には

```text
('cargo', 'serde_with', '3.18.0', 'runtime', 'moderate', 'GHSA-7gcf-g7xr-8hxj')
```

すなわち **`cargo audit` が exit 0 を返す当の依存**が含まれる。

```bash
# 再現手順 (base は head の祖先である必要がある。`base...head` は merge base 基準)
gh api "repos/Idios/kobutachan-allaganeye/dependency-graph/compare/<base>...<head>" \
  | jq '[.[] | select(.change_type=="added") | . as $d | (.vulnerabilities // [])[]
         | select(.severity as $s | ["critical","high","moderate"] | index($s))
         | [$d.ecosystem, $d.name, $d.version, $d.scope, .severity, .advisory_ghsa_id]] | unique'
```

### cargo audit を default 設定にした理由 (v0.2.1 Track C)

`--deny warnings` で実行すると、現状 19 件の deferred warnings (tauri 2.11 系の transitive で残る `rand 0.7.3` / `glib 0.18.5` / `atk` 等 gtk-rs GTK3 bindings unmaintained) で fail する。これらは:

- 配布物 (Windows Portable ZIP) には影響しない (build-dep のみ or Linux/macOS 専用)
- tauri 上流が phf_generator / kuchikiki 等を新版へ移行するのを待つ deferred 判断 (`docs/superpowers/specs/2026-05-16-security-alerts-response-design.md` §4 Track A)

CI が常時 fail する状態を避けるため、本 workflow では default 設定 (vulnerability のみ fail) で運用する。warning は log 出力で確認可能。

### npm audit の閾値を `high` のまま据え置く判断 (v0.3.1、#933 §A)

`npm audit --audit-level=high` が moderate / low を素通しする点 (下記 §本 workflow が green でも Dependabot alert が出るケース の項目 2) について、**閾値を下げるかを実測して決めた**。

**実測 (2026-08-11、`develop-0.3.1` @ 15e0c17、`cd gui && npm audit --json`)**:

| severity | 件数 |
| --- | --- |
| critical | 0 |
| high | **1** |
| moderate | 0 |
| low | 0 |
| info | 0 |

**判断: 閾値は `high` のまま据え置く。** 理由は「下げても今日は何も変わらない」こと — moderate / low が 0 件なので、`--audit-level=moderate` に下げても**新規 finding は 0 件**である。閾値を下げる動機は「素通しされている実害があること」だが、それが現時点で存在しない。ノイズ量の実測もできないまま閾値だけ厳しくすると、最初に moderate が 1 件出た日に「なぜ厳しくしたか」を誰も説明できない状態で CI が赤くなる。

なお moderate の取りこぼしは dependency-review job (`fail-on-severity: moderate`) が別経路で拾うため、閾値を据え置いても素通しするのは **low のみ**である (項目 2 に既述)。

**唯一の high (要対応、本 doc の判断とは別件)**: `nanoid` 3.3.16 (`gui/package-lock.json`、`"dev": true` の推移的依存)。advisory は GHSA-2v37-7h3g-55p8「custom generators can loop indefinitely when size is zero」で、影響範囲は `<3.3.17`、`fixAvailable: true`。**lockfile のみの bump で解消できる**。dev 依存でありビルド成果物には入らないため出荷をブロックしないが、次に `gui/package-lock.json` を触る PR で解消する。

**再現コマンド**:

```bash
cd gui && npm audit --json
```

### tauri 2.11 transitive 制約 (PR #760 v0.2.1 Track A)

tauri 2.10.3 → 2.11.1 bump (PR #760) を実施したが、以下の transitive 依存は新版へ解決できなかった:

- **rand 0.7.3** (build-dep): `tauri 2.11.1 → tauri-utils 2.9.1 → kuchikiki 0.8.8-speedreader → selectors 0.24.0 → phf_codegen 0.8.0 → phf_generator 0.8.0` の chain で `rand = "^0.7"` を strict pin。`cargo update -p rand@0.7.3 --precise 0.8.6` で fail
- **glib 0.18.5** (Linux/macOS GTK): Windows ビルドで未使用 (`cargo tree -i glib` 出力空)

**経緯**: Dependabot alerts #4 (glib GHSA-wrw7-89jp-8q8g) と #5 (rand GHSA-cq8v-f236-94qc) を解消したかったが、tauri 上流が kuchikiki (HTML parser) を使い続ける限り解決不可能。両者とも配布物 (Windows Portable ZIP の `allaganeye-gui.exe`) に runtime 影響なし (rand は build-dep のみ、glib は Linux/macOS 専用)、Idios 2026-05-16 判断で deferred。

**運用**: v0.2.x 系で security alert を消化する際、`rand 0.7.3 / glib 0.18.5` は tauri 上流が phf_generator / kuchikiki を新版へ移行するまで残る前提で計画する。状態確認は `gui/src-tauri/Cargo.lock` で `name = "rand"` / `name = "glib"` の version、および `cargo audit` の warning summary。上流動向は follow-up issue で追跡。

## 失敗時の対応

1. PR 作者は失敗 log を確認し、影響のある依存を特定
2. 該当依存の patched version を確認 (cargo upgrade / npm install)
3. 本 PR 内で修正 commit を追加、または別 PR で先に hotfix
4. medium/low で warning のみの場合は警告として report し、本 PR では (1) 修正、(2) deferred 起票、(3) ignore 理由を本 PR 本文に明記、のいずれか

## Dependabot との関係

- Dependabot: 既存依存の脆弱性を post-merge で検出 (auto PR で patch を提案)
- 本 workflow: PR 提案 (Dependabot or 手動) を merge する**前**に検証

両者は補完関係だが、**参照している advisory database が別物**である点に注意する。

| | 参照 DB | 検出範囲 |
| --- | --- | --- |
| `cargo audit` | [RustSec advisory-db](https://github.com/rustsec/advisory-db) | RustSec に登録された crate のみ |
| `npm audit` | npm registry advisory (GitHub Advisory Database 由来) | 閾値 `--audit-level` 以上のみ |
| `pip-audit` | [PyPI Advisory DB (OSV)](https://github.com/pypa/advisory-database) | install 済み Python 環境全体、severity 問わず全件 |
| `dependency-review` | [GitHub Advisory Database](https://github.com/advisories) | Rust / npm 双方、moderate 以上。ただし**当該 PR が追加・変更した依存のみ**。**pip は resolved version が無いため実質対象外** (§pip-audit を追加した理由) |
| Dependabot | [GitHub Advisory Database](https://github.com/advisories) | Rust / npm 双方、severity 問わず全件。ただし**既定ブランチのみ**。**pip は同上の理由で実質対象外** |

### repo 側の Dependabot 設定 (#868)

| 設定 | 状態 | 所在 |
| --- | --- | --- |
| Dependabot alerts | 有効 (`gh api repos/.../vulnerability-alerts` が 204) | repo 設定 (repo 外) |
| Dependabot security updates (脆弱性修復 PR の自動作成) | 有効 (`gh api repos/.../automated-security-fixes` が `{"enabled":true,"paused":false}`) | repo 設定 (repo 外) |
| Dependabot version updates (定期 bump PR) | 有効 (npm / pip / github-actions の 3 ecosystem) | [`.github/dependabot.yml`](../.github/dependabot.yml) |

**`dependabot.yml` が担うのは 3 行目だけ**である。alert と security updates は repo 設定側にあり、`dependabot.yml` の有無とは独立に動く。

> **`dependabot.yml` は既定ブランチ (`main`) からしか読まれない。** `schedule: cron` と同じ制約で、`develop-*` へ merge しただけでは version updates は 1 度も起動しない (GitHub の仕様)。2026-08-20 時点で `gh api repos/.../contents/.github/dependabot.yml?ref=main` は **404**、`?ref=develop-0.3.1` は 200 を返す = **まだ有効になっていない**。
>
> 有効化の確認は v0.3.1 のリリース PR が `main` へ渡った後に行う。`gh api repos/Idios/kobutachan-allaganeye/contents/.github/dependabot.yml?ref=main` が 200 を返し、かつ Insights > Dependency graph > Dependabot に 3 ecosystem が並べば有効。**「ファイルを追加したので効いている」と読まないこと。**

`dependabot.yml` に `ignore` 条件を 1 つも書いていないのは意図的である。`ignore` は version updates だけでなく **security updates にも効く**ため、「semver-minor を一律 ignore」のような書き方をすると、v0.3.0 で実際に踏んだ undici 7.28.0 → 7.29.0 (minor bump) のような**脆弱性修正 PR まで黙って抑止される**。ノイズは `open-pull-requests-limit: 3` で量的に抑え、採否は PR ごとに人間が判断する。

**over-bump PR の扱い** (#836 で確立した規約): 直接依存は「最小 patch を exact-pin で直接編集」が正。Dependabot は latest minor まで上げる PR を出すことがある (実例: vite 8.0.16 → 8.1.0 は #836 で却下)。そういう PR は **close して、必要な分だけ手で当てる**。Dependabot の提案は「上流に更新が出た」という通知として読み、diff をそのまま採用する義務はない。とくに `pyproject.toml` の上限 (`typer<0.25` / `click<8.4` / `opencv-python-headless<5`) と `constraints.txt` の exact pin は**遅れではなく確定済みの方針** (#863 / #916 裁定 D8) なので、これを超える PR は原則 close する。

### 本 workflow が green でも Dependabot alert が出るケース

**「advisory DB の更新タイミング差」だけが原因ではない。以下は構造的なギャップであり、待っても解消しない。**

1. **RustSec に存在しない advisory は `cargo audit` が永久に検出しない。**
   実例 (v0.3.0 リリース作業中、Refs #862): Dependabot alert #22 `serde_with < 3.21.0`
   (GHSA-7gcf-g7xr-8hxj、medium) は GitHub Advisory Database には登録されているが、
   RustSec advisory-db に `crates/serde_with/` ディレクトリ自体が存在しない。
   当該 alert が指すのと同一の `Cargo.lock` (serde_with 3.18.0) に対して
   `cargo audit -f <Cargo.lock>` を実行しても **exit 0 (green)** が返る。
   → **v0.3.0 で追加した dependency-review job がこの差を埋める** (同じ GitHub
   Advisory Database を参照するため)。ただし下記 3 の限界は残る。

2. **`npm audit --audit-level=high` は medium / low を素通しする。**
   Dependabot は severity を問わず全件 alert を上げるため、medium / low の
   advisory は本 workflow を green のまま通過する。
   → dependency-review job (`fail-on-severity: moderate`) が moderate を拾うので、
   素通しするのは **low のみ**に縮んだ。

3. **dependency-review は「その PR が追加・変更した依存」しか見ない。**
   base→head の依存グラフ差分を評価する action なので、**変更されていない既存依存に
   対して後から advisory が公開された場合、どの PR も fail しない**。この経路を
   拾えるのは Dependabot 本体だけである。同じ理由で、依存を触らない PR
   (paths filter で本 workflow 自体が起動しない) も当然素通りする。

したがって **「security-audit.yml が green だから脆弱性なし」とは依然として言えない。**
リリース前には Dependabot alert 一覧を直接確認すること:

```bash
gh api repos/Idios/kobutachan-allaganeye/dependabot/alerts --paginate \
  -q '.[] | select(.state=="open") | [.number, .security_advisory.severity, .dependency.package.name, (.security_vulnerability.first_patched_version.identifier // "NONE")] | @tsv'
```

なお Dependabot が scan するのは**既定ブランチ (`main`) のみ**である。
release ブランチ上で lockfile を修正しても、`main` に merge されるまで alert は open のまま残る
(v0.3.0 では npm 18 件がこの状態だった)。

この確認は [`release` SKILL.md](../.agents/skills/release/SKILL.md) §Step 5 が
タグ打ちの直前に実行する工程として規定している (#950)。

#### `?state=all` を付けてはいけない (実測 2026-08-20、#950 O-1 の決着)

上のコマンドが `state` を絞らず jq 側で `select(.state=="open")` しているのは意図的である。

`state` の有効値は `open` / `fixed` / `dismissed` / `auto_dismissed` の 4 つで、
**`all` は有効値ではない**。そして本 API は無効値に対して 422 を返さず、
**HTTP 200 + 空配列**を返す。実測:

```text
gh api 'repos/Idios/kobutachan-allaganeye/dependabot/alerts'                     -> 200, 28 件
gh api 'repos/Idios/kobutachan-allaganeye/dependabot/alerts?state=open'          -> 200,  0 件
gh api 'repos/Idios/kobutachan-allaganeye/dependabot/alerts?state=fixed'         -> 200, 25 件
gh api 'repos/Idios/kobutachan-allaganeye/dependabot/alerts?state=dismissed'     -> 200,  2 件
gh api 'repos/Idios/kobutachan-allaganeye/dependabot/alerts?state=auto_dismissed'-> 200,  1 件
gh api 'repos/Idios/kobutachan-allaganeye/dependabot/alerts?state=all'           -> 200,  0 件
gh api 'repos/Idios/kobutachan-allaganeye/dependabot/alerts?state=bogusvalue'    -> 200,  0 件
```

`state=all` と `state=bogusvalue` の挙動が完全に一致する。つまり
**typo でも無効値でも「alert ゼロ」に見える緑が作れる。**

これは
[spec 2026-08-05-v031-patch-design.md](superpowers/specs/2026-08-05-v031-patch-design.md)
§8.2 O-1 が「トークンに `security_events` scope が無いのか、release merge 後に
全件 close されたのか」として未決にしていた点の答えでもある。**どちらでもなく、
クエリが無効だった。** 権限は正常 (無指定なら 28 件返る) で、alert も
0 件ではない (open が 0 件なだけ)。

## 参照

- spec: `docs/superpowers/specs/2026-05-16-security-alerts-response-design.md` §2.5 / §4 Track C
- plan: `docs/superpowers/plans/2026-05-16-v0.2.1-track-c-audit-ci.md`
- Track A audit log baseline: `docs/audit-logs/2026-05-16-v0.2.1-audit.log`
