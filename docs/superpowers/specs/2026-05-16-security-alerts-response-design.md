# v0.2.1 Security Hotfix Response Design

- 日付: 2026-05-16
- 作成者: Claude (brainstorming skill, with Idios)
- 対象リリース: v0.2.1 (L2 ホットフィックス)
- ベース: `main` (タグ `v0.2.0`)

## 1. Overview / Goal

v0.2.0 リリース後に GitHub 上で open 状態の Dependabot security alert 5 件と Dependabot PR 1 件 ([#758](https://github.com/Idios/kobutachan-allaganeye/pull/758)) を、単一の v0.2.1 ホットフィックスリリースで解消する。配布バイナリ (Portable ZIP) を rebuild して medium severity 以下の脆弱性を消し、`main` + 新規 cut の `develop-0.3.0` 両方に反映する。

## 2. Context

### Open Dependabot alerts (5 件)

| # | Package | Severity | Manifest | Vulnerable | Patched | 配布物影響 | GHSA |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 6 | tauri | medium | gui/src-tauri/Cargo.lock | `=2.10.3` (現状), `<= 2.11.0` | 2.11.1 | あり (runtime) | GHSA-7gmj-67g7-phm9 (Origin Confusion → Remote→Local IPC invocation) |
| 4 | glib | medium | gui/src-tauri/Cargo.lock | `0.18.5` (現状), `< 0.20.0` | 0.20.0 | なし (Windows ビルド未使用、GTK 系 Linux/macOS deps) | GHSA-wrw7-89jp-8q8g (`VariantStrIter` unsoundness) |
| 5 | rand | low | gui/src-tauri/Cargo.lock | `0.7.3` (現状), `< 0.8.6` | 0.8.6 | build-dep のみ (runtime 不含) | GHSA-cq8v-f236-94qc (custom logger + `rand::rng()` unsoundness) |
| 3 | fast-uri | high | gui/package-lock.json | `<= 3.1.1` | 3.1.2 | なし (dev-only: ajv via devDeps) | GHSA-v39h-62p7-jpjc (host confusion via percent-encoded authority delimiters) |
| 2 | fast-uri | high | gui/package-lock.json | `<= 3.1.0` | 3.1.1 | 同上 | GHSA-q3j6-qgpj-74h6 (path traversal via percent-encoded dot segments) |

### Dependabot PR

- [#758](https://github.com/Idios/kobutachan-allaganeye/pull/758) `chore(deps): bump fast-uri from 3.1.0 to 3.1.2 in /gui in the npm_and_yarn group`
  - alert #2 + #3 両方を解決
  - base = `main` (default branch)
  - 当 repo の `develop-x.x.x` 統合先規約と齟齬

### 配布物影響の評価

- **runtime (`.exe` に同梱)**: tauri (medium)
- **runtime (transitive build only, .exe 不含)**: rand (low)
- **Windows 配布物に未含 (Linux/macOS GTK 系)**: glib (medium)
- **dev environment のみ**: fast-uri (high x 2、`ajv` via `devDependencies`)

high severity (fast-uri) は dev-only のため配布ユーザーへの影響なし。runtime ユーザー観点で最重要は tauri (Origin Confusion)。

## 3. Decisions

| 判断点 | 選択 | 理由 |
| --- | --- | --- |
| Q1: 対応単位とリリース戦略 | **(A) v0.2.1 ホットフィックスで全 5 件対応** | 配布物の medium 脆弱性を一気に消す。Iron Law 1 / 4 の手動レビュー・close フローと整合 |
| Q2: PR 構造 | **(C) 1 PR 統合・細粒度 commit 分割** | 単一 PR で `main` への security hotfix を完結。各 alert と commit の対応をトレース可能にする。`cargo update` を 1 段で実行しつつ commit を 5 本に分けて意図を明示 |

## 4. Scope

### In scope

1. Cargo.lock / package-lock.json の脆弱な依存を patched 版に置き換え
2. `Cargo.toml` direct dep の tauri を `=2.11.1` へ pin 更新
3. tauri 2.11 系と互換性のある tauri-build / tauri-plugin-* への bump
4. version bump (0.2.0 → 0.2.1) を 4 ファイル (`pyproject.toml`, `gui/package.json`, `gui/src-tauri/Cargo.toml`, `gui/src-tauri/tauri.conf.json`) に適用
5. `CHANGELOG.md` に v0.2.1 セクション追加 (5 alert + GHSA リンク + 配布物影響説明)
6. PR `claude/security-v0.2.1 → main` 作成、レビュー、マージ
7. v0.2.1 タグ → [release.yml](.github/workflows/release.yml) による Portable ZIP 自動 build + GitHub Release 作成
8. `main` から `develop-0.3.0` 新規 cut + version 0.3.0 bump (release-process.md §ブランチ戦略 ルール 4)

### Out of scope (別議論 / 別 issue 起票検討)

- `cargo audit` を CI workflow に統合する仕組み (継続的検出体制、follow-up issue 起票候補)
- Dependabot grouped update 設定の見直し (Rust 側も group 化するか)
- v0.2.0 配布バイナリの差し戻し or 公開警告 (v0.2.0 リリースから日が浅いため、v0.2.1 ZIP 公開で対応十分と判断)
- L3 (v0.3.0) スコープへの security 関連機能追加 (本リリースは hotfix に専念)

## 5. Branch Strategy

`docs/release-process.md` §ブランチ戦略 ルール 5 (ホットフィックス) に従う。

```text
main (タグ v0.2.0)
 └── claude/security-v0.2.1 (本作業ブランチ、main から派生)
       └── PR → main
              ├── マージ + git tag v0.2.1 + git push origin v0.2.1
              │       └── release.yml 発火 → allaganeye-v0.2.1-windows.zip 自動生成 + GitHub Release
              └── main から develop-0.3.0 を新規 cut + version 0.3.0 bump
```

### 作業ブランチ名

- 候補 (a): 現 worktree branch `claude/crazy-swirles-bed20b` を流用 (低コスト、命名規約からは外れる)
- 候補 (b): 新規に `claude/security-v0.2.1` を main から切り直し、worktree 内の git branch を切り替え (規約準拠だが手間)

→ writing-plans 段階で確定。(a) で進めると軽量、(b) で進めるとレビュー視認性が高い。

## 6. Update Plan (5 commit 構造)

### Commit 1: `chore(deps): bump fast-uri 3.1.0 → 3.1.2 (#2, #3)`

- `cd gui && npm install fast-uri@3.1.2 --package-lock-only`
- 影響ファイル: `gui/package-lock.json` のみ
- 検証: `gui/package.json` の direct deps は不変、`ajv` (devDeps) の transitive のみ更新されることを確認
- 解決 alert: #2, #3

### Commit 2: `chore(deps): bump tauri 2.10.3 → 2.11.1 + tauri-build (#6)`

- `gui/src-tauri/Cargo.toml`:
  - `tauri = "=2.11.1"` (現 `=2.10.3`、`first_patched: 2.11.1`、2.11.0 ではまだ脆弱なので 2.11.1 まで上げる必要あり)
  - `tauri-build = "=2.6.0"` (現 `=2.5.6`、tauri 2.11.0 release notes で `tauri-build@2.6.0` への bump が記載)
- `cd gui/src-tauri && cargo update -p tauri --precise 2.11.1`
- 影響ファイル: `gui/src-tauri/Cargo.toml`, `gui/src-tauri/Cargo.lock`
- 検証: `cargo check` で compile pass、tauri 系 entries が 2.11 系に揃う
- 解決 alert: #6

### Commit 3: `chore(deps): align tauri-plugin-* with tauri 2.11`

- `tauri-plugin-dialog` / `-fs` / `-shell` の tauri 2.11 互換 latest 版を plan 段階で確認後 bump
  - 現状: 2.7.0 / 2.5.0 / 2.3.5
  - これらは tauri-plugins-workspace の独自 release cadence のため、tauri version とは別系列
- 影響ファイル: `gui/src-tauri/Cargo.toml`, `gui/src-tauri/Cargo.lock`
- 検証: `cargo check`, `cargo test`
- 解決 alert: なし (互換性整合のための支援 commit)

### Commit 4: `chore(deps): verify transitive rand 0.8.6 / glib 0.20.0 (#4, #5)`

- Commit 2-3 後の `Cargo.lock` を確認、transitive で解決されていれば commit 内容は意図表明 (CHANGELOG メモ) のみ
- 未解決の場合のみ個別 `cargo update -p rand@0.7.3 --precise 0.8.6` / `cargo update -p glib --precise 0.20.0` を実行
- 影響ファイル: `gui/src-tauri/Cargo.lock` (該当時のみ)
- 検証: GitHub 上で Dependabot alert #4 / #5 が auto-resolve されることを PR マージ後に確認
- 解決 alert: #4, #5

### Commit 5: `chore: bump version 0.2.0 → 0.2.1 + CHANGELOG`

- version bump (4 ファイル):
  - `pyproject.toml`
  - `gui/package.json`
  - `gui/src-tauri/Cargo.toml`
  - `gui/src-tauri/tauri.conf.json`
- `CHANGELOG.md` に新規セクション追加:

  ```markdown
  ## v0.2.1 - 2026-05-?? - Security hotfix

  ### Security

  - tauri 2.10.3 → 2.11.1 (medium: Origin Confusion, GHSA-7gmj-67g7-phm9)
  - glib transitive → 0.20.0 (medium: VariantStrIter unsoundness, GHSA-wrw7-89jp-8q8g, Windows build 未使用)
  - rand transitive 0.7.3 → 0.8.6 (low: rng() unsoundness, GHSA-cq8v-f236-94qc, build-dep のみ)
  - fast-uri 3.1.0 → 3.1.2 (high: GHSA-v39h-62p7-jpjc / GHSA-q3j6-qgpj-74h6, dev-only deps)

  ### Notes

  - Portable ZIP (`allaganeye-v0.2.1-windows.zip`) は GUI runtime (tauri) のみ実効的に更新される。Python CLI 側に変更なし
  ```

- 影響ファイル: 4 + 1 = 5 ファイル

## 7. Verification (Iron Law 6 準拠)

### 自動チェック (PR 作成前に local + CI 両方で pass)

| 範囲 | コマンド |
| --- | --- |
| Python | `ruff check . / ruff format --check . / pyright / pytest` |
| GUI frontend | `cd gui && npm run lint / typecheck / test / build` |
| GUI Rust | `cd gui/src-tauri && cargo check / cargo test` |
| docs | `bash scripts/check-markdownlint.sh` (CHANGELOG 更新分) |

### 実機検証 (Idios 依頼、Iron Law 6 で必須)

`gui/src-tauri/**` (Cargo.toml + Cargo.lock) の変更により tauri runtime の動作に影響あり。以下を Idios の Windows 実機で確認:

- Tauri GUI 起動 (`cd gui && npm run tauri dev` または build 済 `.exe`)
- Golden path: drop → detecting → complete → preview → export
- Export 時の H.264 エンコーダ自動選択 (NVENC / QSV / AMF / libx264 fallback) — `select_h264_encoder_for_export` の動作確認
- 既存 `recent.json` の load (`<install dir>/recent.json` 配置、#571)

### ローカル Portable ZIP smoke (任意)

`pwsh ./scripts/build-portable-zip.ps1 -Version 0.2.1` を local で実行し、ZIP 生成成功と `docs/l2-e2e-checklist.md §3 T1` smoke を実施。

### 受け入れ条件 (Iron Law 1 準拠)

- [ ] Dependabot alert #2, #3, #4, #5, #6 が PR マージ後 24h 以内に auto-resolve される (or 手動 close)
- [ ] [release.yml](.github/workflows/release.yml) が `allaganeye-v0.2.1-windows.zip` を artifact + Release に添付
- [ ] Portable ZIP の `allaganeye-gui.exe` が起動し、export まで通る (Idios 実機検証)
- [ ] `main` から `develop-0.3.0` が cut され、version が 0.3.0 に bump
- [ ] PR #758 が PR `claude/security-v0.2.1 → main` マージ後 24h 以内に Dependabot により auto-close される。auto-close されない場合は手動 close (reason: "superseded by v0.2.1 hotfix")

## 8. Release Flow

1. PR `claude/security-v0.2.1 → main` をマージ
2. `main` HEAD にタグ: `git tag -a v0.2.1 -m "Release v0.2.1: Security hotfix"` + `git push origin v0.2.1`
3. [release.yml](.github/workflows/release.yml) が以下を自動実行:
   - Portable ZIP build (`scripts/build-portable-zip.ps1 -Version 0.2.1`)
   - SHA256 verify (Python embed / get-pip / FFmpeg)
   - GitHub Release 作成 (`extract_release_notes.py 0.2.1` で CHANGELOG から抽出)
4. PR 作者 (Claude or Idios) が以下を手動確認:
   - Dependabot alerts 5 件の auto-close 状態
   - PR #758 の close 状態
   - GitHub Release ページに ZIP + release notes が掲載
5. `main` から `develop-0.3.0` 新規 cut + version 0.3.0 bump コミット

## 9. References

### Project docs

- [docs/release-process.md](../../release-process.md) §ブランチ戦略 / §タグ運用 / §レイヤーリリース受け入れゲート
- [docs/l2-workflow.md](../../l2-workflow.md) §「PR 作成 Pre-flight」 / §「Self-Test Report 規約」
- [docs/l2-e2e-checklist.md](../../l2-e2e-checklist.md) §3 T1 (Portable ZIP smoke)
- [CLAUDE.md](../../../CLAUDE.md) §Iron Law / §PR 作成ルール

### Security advisories

- [GHSA-7gmj-67g7-phm9](https://github.com/advisories/GHSA-7gmj-67g7-phm9) — tauri Origin Confusion
- [GHSA-wrw7-89jp-8q8g](https://github.com/advisories/GHSA-wrw7-89jp-8q8g) — glib VariantStrIter unsoundness
- [GHSA-cq8v-f236-94qc](https://github.com/advisories/GHSA-cq8v-f236-94qc) — rand custom logger unsoundness
- [GHSA-v39h-62p7-jpjc](https://github.com/advisories/GHSA-v39h-62p7-jpjc) — fast-uri host confusion
- [GHSA-q3j6-qgpj-74h6](https://github.com/advisories/GHSA-q3j6-qgpj-74h6) — fast-uri path traversal

### GitHub artifacts

- [PR #758](https://github.com/Idios/kobutachan-allaganeye/pull/758) — Dependabot fast-uri 3.1.2 PR
- [Release v0.2.0](https://github.com/Idios/kobutachan-allaganeye/releases/tag/v0.2.0)
