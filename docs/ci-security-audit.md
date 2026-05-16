# CI: Security Audit Workflow

`.github/workflows/security-audit.yml` の運用 note。

## 目的

PR を `develop-x.x.x` や `main` にマージする前に、cargo audit + npm audit を自動実行し、Dependabot より早く脆弱性を検出する。

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

## 失敗時の対応

1. PR 作者は失敗 log を確認し、影響のある依存を特定
2. 該当依存の patched version を確認 (cargo upgrade / npm install)
3. 本 PR 内で修正 commit を追加、または別 PR で先に hotfix
4. medium/low で warning のみの場合は警告として report し、本 PR では (1) 修正、(2) deferred 起票、(3) ignore 理由を本 PR 本文に明記、のいずれか

## Dependabot との関係

- Dependabot: 既存依存の脆弱性を post-merge で検出 (auto PR で patch を提案)
- 本 workflow: PR 提案 (Dependabot or 手動) を merge する**前**に検証

両者は補完関係。本 workflow が green でも Dependabot alert は別途出る可能性 (advisory DB の更新タイミング差)。

## 参照

- spec: `docs/superpowers/specs/2026-05-16-security-alerts-response-design.md` §2.5 / §4 Track C
- plan: `docs/superpowers/plans/2026-05-16-v0.2.1-track-c-audit-ci.md`
- Track A audit log baseline: `docs/audit-logs/2026-05-16-v0.2.1-audit.log`
