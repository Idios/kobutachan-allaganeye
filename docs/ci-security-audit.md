# CI: Security Audit Workflow

`.github/workflows/security-audit.yml` の運用 note。

## 目的

PR を `develop-x.x.x` や `main` にマージする前に、cargo audit + npm audit を自動実行し、Dependabot より早く脆弱性を検出する。

ただし本 workflow は Dependabot の**上位互換ではない**。参照 DB と閾値の差により、green でも Dependabot alert が残るケースが構造的に存在する (§[Dependabot との関係](#dependabot-との関係) 参照)。

## 発火条件

- `pull_request` trigger
- paths: `gui/src-tauri/Cargo.lock`, `gui/src-tauri/Cargo.toml`, `gui/package-lock.json`, `gui/package.json`, `.github/workflows/security-audit.yml`
- `workflow_dispatch` で手動実行も可能

paths filter により、Python のみ変更の PR では本 workflow は走らない (CI 時間節約)。

## ジョブ

| ジョブ | コマンド | fail 条件 |
| --- | --- | --- |
| cargo-audit | `cargo audit` (default) | vulnerability (CVE 相当) 検出のみ fail。warning (unmaintained / unsound) は通過 |
| npm-audit | `npm audit --audit-level=high` | high 以上の advisory 検出。dev-only の moderate/low は warning として通過 |

### cargo audit を default 設定にした理由 (v0.2.1 Track C)

`--deny warnings` で実行すると、現状 19 件の deferred warnings (tauri 2.11 系の transitive で残る `rand 0.7.3` / `glib 0.18.5` / `atk` 等 gtk-rs GTK3 bindings unmaintained) で fail する。これらは:

- 配布物 (Windows Portable ZIP) には影響しない (build-dep のみ or Linux/macOS 専用)
- tauri 上流が phf_generator / kuchikiki 等を新版へ移行するのを待つ deferred 判断 (`docs/superpowers/specs/2026-05-16-security-alerts-response-design.md` §4 Track A)

CI が常時 fail する状態を避けるため、本 workflow では default 設定 (vulnerability のみ fail) で運用する。warning は log 出力で確認可能。

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
| Dependabot | [GitHub Advisory Database](https://github.com/advisories) | Rust / npm 双方、severity 問わず全件 |

### 本 workflow が green でも Dependabot alert が出るケース

**「advisory DB の更新タイミング差」だけが原因ではない。以下は構造的なギャップであり、待っても解消しない。**

1. **RustSec に存在しない advisory は `cargo audit` が永久に検出しない。**
   実例 (v0.3.0 リリース作業中、Refs #862): Dependabot alert #22 `serde_with < 3.21.0`
   (GHSA-7gcf-g7xr-8hxj、medium) は GitHub Advisory Database には登録されているが、
   RustSec advisory-db に `crates/serde_with/` ディレクトリ自体が存在しない。
   当該 alert が指すのと同一の `Cargo.lock` (serde_with 3.18.0) に対して
   `cargo audit -f <Cargo.lock>` を実行しても **exit 0 (green)** が返る。

2. **`npm audit --audit-level=high` は medium / low を素通しする。**
   Dependabot は severity を問わず全件 alert を上げるため、medium / low の
   advisory は本 workflow を green のまま通過する。

したがって **「security-audit.yml が green だから脆弱性なし」とは言えない。**
リリース前には Dependabot alert 一覧を直接確認すること:

```bash
gh api repos/Idios/kobutachan-allaganeye/dependabot/alerts --paginate \
  -q '.[] | select(.state=="open") | [.number, .security_advisory.severity, .dependency.package.name, (.security_vulnerability.first_patched_version.identifier // "NONE")] | @tsv'
```

なお Dependabot が scan するのは**既定ブランチ (`main`) のみ**である。
release ブランチ上で lockfile を修正しても、`main` に merge されるまで alert は open のまま残る
(v0.3.0 では npm 18 件がこの状態だった)。

## 参照

- spec: `docs/superpowers/specs/2026-05-16-security-alerts-response-design.md` §2.5 / §4 Track C
- plan: `docs/superpowers/plans/2026-05-16-v0.2.1-track-c-audit-ci.md`
- Track A audit log baseline: `docs/audit-logs/2026-05-16-v0.2.1-audit.log`
