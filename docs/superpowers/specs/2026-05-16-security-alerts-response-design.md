# v0.2.1 Patch Release Design (Security + UX + CI 強化)

- 日付: 2026-05-16
- 作成者: Claude (brainstorming skill, with Idios)
- 対象リリース: v0.2.1 (L2 patch)
- ベース: `main` (タグ `v0.2.0`)
- 統合ブランチ: `develop-0.2.1` (本 spec で main から新規 cut)

## 1. Overview / Goal

v0.2.0 リリース後に発生した課題を v0.2.1 patch リリースで一括解消する:

1. **Security alerts (Dependabot) 5 件** + Dependabot PR 1 件 ([#758](https://github.com/Idios/kobutachan-allaganeye/pull/758))
2. **UX 影響のある deferred bug / task 5 件** ([#374](https://github.com/Idios/kobutachan-allaganeye/issues/374) / [#458](https://github.com/Idios/kobutachan-allaganeye/issues/458) / [#743](https://github.com/Idios/kobutachan-allaganeye/issues/743) / [#749](https://github.com/Idios/kobutachan-allaganeye/issues/749) / [#756](https://github.com/Idios/kobutachan-allaganeye/issues/756))
3. **今後の GitHub security 指摘を PR マージ前に自前で検出する仕組み**: cargo audit + npm audit を CI workflow に組み込む

`main` から `develop-0.2.1` 統合ブランチを新規 cut し、Track 別作業ブランチからの PR を統合した後、`develop-0.2.1 → main` で v0.2.1 リリースする。

## 2. Context

### 2.1 Open Dependabot alerts (5 件)

| # | Package | Severity | Manifest | Vulnerable | Patched | 配布物影響 | GHSA |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 6 | tauri | medium | gui/src-tauri/Cargo.lock | `=2.10.3` (現状), `<= 2.11.0` | 2.11.1 | あり (runtime) | GHSA-7gmj-67g7-phm9 (Origin Confusion → Remote→Local IPC invocation) |
| 4 | glib | medium | gui/src-tauri/Cargo.lock | `0.18.5` (現状), `< 0.20.0` | 0.20.0 | なし (Windows ビルド未使用、GTK 系 Linux/macOS deps) | GHSA-wrw7-89jp-8q8g (`VariantStrIter` unsoundness) |
| 5 | rand | low | gui/src-tauri/Cargo.lock | `0.7.3` (現状), `< 0.8.6` | 0.8.6 | build-dep のみ (runtime 不含) | GHSA-cq8v-f236-94qc (custom logger + `rand::rng()` unsoundness) |
| 3 | fast-uri | high | gui/package-lock.json | `<= 3.1.1` | 3.1.2 | なし (dev-only: ajv via devDeps) | GHSA-v39h-62p7-jpjc (host confusion via percent-encoded authority delimiters) |
| 2 | fast-uri | high | gui/package-lock.json | `<= 3.1.0` | 3.1.1 | 同上 | GHSA-q3j6-qgpj-74h6 (path traversal via percent-encoded dot segments) |

### 2.2 Dependabot PR

- [#758](https://github.com/Idios/kobutachan-allaganeye/pull/758) `chore(deps): bump fast-uri from 3.1.0 to 3.1.2 in /gui in the npm_and_yarn group`
  - alert #2 + #3 両方を解決
  - base = `main` (default branch、当 repo の `develop-x.x.x` 統合先規約と齟齬)

### 2.3 配布物影響の評価 (Dependabot alerts)

- **runtime (`.exe` に同梱)**: tauri (medium)
- **runtime (transitive build only, .exe 不含)**: rand (low)
- **Windows 配布物に未含 (Linux/macOS GTK 系)**: glib (medium)
- **dev environment のみ**: fast-uri (high x 2、`ajv` via `devDependencies`)

high severity (fast-uri) は dev-only のため配布ユーザーへの影響なし。runtime ユーザー観点で最重要は tauri (Origin Confusion)。

### 2.4 取り込み対象 UX issue (5 件、すべて deferred)

| # | Severity | Scope | 概要 |
| --- | --- | --- | --- |
| 756 | P2-medium, bug | l2a-gui | detecting 中の GUI 終了で ffmpeg 子孫プロセスが残留 (Windows process tree orphan)。Python CLI 経由で spawn された ffmpeg が孫プロセスとして orphan 化し、CPU/disk リソースを消費し続ける |
| 458 | P2-medium, task | l2-workflow | bug_report.yml UI 動作確認 (L3 初期残作業) + `.github/ISSUE_TEMPLATE/bug_report.yml:18` の link を `../../blob/develop-0.2.0/...` から `../../blob/main/...` に修正 + 「(公開までしばらくお待ちください)」placeholder 削除 (v0.2.0 main マージで bug-report-guide.md は公開済) |
| 743 | P3-low, task | role:lead-engineer | Windows process group orphan 挙動 audit (#727 派生 (3))。6 spawn site の振る舞いを実機検証 + audit document 作成 |
| 374 | P3-low, bug | (none) | metadata.json の `note` フィールドが H.264 想定 (2s) で固定。AV1 等の codec で誤情報 |
| 749 | P3-low, doc | l2b-installer | Portable ZIP 内 `README.txt` が英語のまま。ターゲットユーザー (日本語話者) 向けに日本語化が必要 |

**#743 と #756 の関係**: #756 は #743 の audit 対象 (process orphan) の具体的 bug。#756 の fix で #743 の audit が完了する形にできる (1 Track 内で両方クローズ)。

**#458 の特殊性**: 既に PR #497 / #498 で実装本体は完了し develop-0.2.0 → main マージ済 (v0.2.0)。残作業は (a) bug_report.yml 内 link の `develop-0.2.0` → `main` 更新 + placeholder 削除、(b) GitHub UI での実測検証 (issue template 選択 / 必須項目 block / 自動付与 label / blank 経路併存) の 2 点。前者はコード修正、後者は Idios の実機検証で完了。

### 2.5 Pre-merge security check の現状

| 仕組み | 状態 | 検出範囲 |
| --- | --- | --- |
| Dependabot alerts | enabled | npm + Cargo の脆弱性 DB 照会、PR マージ後の post-hoc |
| Dependabot PRs | enabled (npm grouped, Cargo 個別) | 自動 PR 生成、main base |
| GitHub CodeQL | **未設定** (`no analysis found`) | - |
| GitHub Secret scanning | **disabled** | - |
| CI security audit job | **未実装** | - |
| cargo audit / npm audit (local) | 手動のみ | - |

→ **gap**: PR マージ前の自動検出がない。Dependabot は post-merge での発見が標準で、マージ前 review でも手動 audit が不要に放置されている。

### 2.6 既存 CI workflows (`.github/workflows/`)

- `ci.yml` (Python + GUI test)
- `markdownlint.yml`
- `pr-checklist.yml` / `check-pr-checklist-test.yml`
- `release.yml`

新規追加 (本 spec): `security-audit.yml` (cargo audit + npm audit を PR ごとに走らせる)

## 3. Decisions

| 判断点 | 選択 | 理由 |
| --- | --- | --- |
| Q1: 対応単位とリリース戦略 | **(A) v0.2.1 patch リリースで全部対応** | 配布物の medium 脆弱性 + UX deferred bug を同一 patch リリースで解消。Iron Law 1 / 4 の手動レビュー・close フローと整合 |
| Q2: Security 部分の PR 構造 | **(C) 細粒度 commit 分割** | 単一 PR (security Track) 内で commit を 5 本に分けて各 alert との対応をトレース可能にする。`cargo update` を 1 段で実行しつつ commit を分離 |
| Q3: UX 取り込み範囲 | **5 件 (#374 / #458 / #743 / #756 / #749)** | Idios が v0.2.1 に取り込むと判断した deferred bug / task。`docs/release-process.md` §共通項目 deferred ラベル全件レビューと整合。#458 は v0.2.0 main マージ後に link 更新と UI 検証残作業を実施 |
| Q4: Pre-merge check の仕組み | **cargo audit + npm audit を CI ジョブに追加** | 軽量、既存 Actions 拡張のみ、Dependabot と補完関係。CodeQL や Dependabot 設定見直しは後続検討に deferred |
| Q5: 統合ブランチ | **`develop-0.2.1` を main から新規 cut** | release-process.md §ブランチ戦略の `develop-x.x.x` 命名規約と整合。複数 Track の PR を統合する標準フロー |

## 4. Scope

### In scope (5 Track)

#### Track A: Security alerts 解消 (元 hotfix 設計)

- Cargo.lock / package-lock.json の脆弱な依存を patched 版に置き換え
- `Cargo.toml` direct dep の tauri を `=2.11.1` へ pin 更新
- tauri 2.11 系互換の tauri-build / tauri-plugin-* への bump
- 解決対象: Dependabot alerts #2, #3, #4, #5, #6 + PR #758

#### Track B-1: #374 metadata note codec 不正確 修正

- `allaganeye/commands/split_matches.py` (`_split_and_write_metadata`) の `note` 文字列定義を案 2 (codec 依存定数の削除) で更新
- 影響範囲: Python CLI のみ

#### Track B-2: #743 + #756 Windows process tree orphan 一括対応

- **#756 fix**: gui/src-tauri/src/lib.rs の Windows process tree kill 実装 (Option A: Job Object 推奨、または Option B: taskkill /T /F)
- **#743 audit**: 6 spawn site の振る舞いを実機検証 + `docs/` 配下に audit document 作成 (#756 fix を audit 成果として位置付け)
- 影響範囲: Tauri Rust + 検証 docs

#### Track B-3: #749 Portable ZIP 内 README.txt 日本語化

- `scripts/build-portable-zip.ps1` の `Format-ReadmeContent` 関数の text template を日本語化
- `scripts/tests/build-portable-zip.Tests.ps1` の Pester assertion を日本語見出しに更新
- 影響範囲: PS script + Pester test

#### Track B-4: #458 bug_report.yml link 修正 + UI 検証

- `.github/ISSUE_TEMPLATE/bug_report.yml:18` の link を `../../blob/develop-0.2.0/...` から `../../blob/main/...` に変更
- 「(公開までしばらくお待ちください)」placeholder を削除 (v0.2.0 main マージで bug-report-guide.md は公開済)
- L3 初期残作業の UI 動作確認チェックリスト (#458 §「L3 初期残作業」) を Idios 実機で実施し、結果を PR 本文に Self-Test Report として記載
- 影響範囲: GitHub Issue Template + 実機 UI 検証

#### Track C: Pre-merge security audit CI 追加

- `.github/workflows/security-audit.yml` を新規追加 (cargo audit + npm audit を PR ごとに実行)
- failure 条件: high severity 以上の脆弱性検出で job fail (medium 以下は warning として report)
- 取り込み trigger: pull_request (paths: `gui/src-tauri/Cargo.lock`, `gui/package-lock.json`)
- Track A の Cargo.lock / package-lock.json 更新後に発火し、green を確認できることが事前テスト

#### Track D: Version bump + CHANGELOG (リリース直前)

- version bump (4 ファイル): `pyproject.toml`, `gui/package.json`, `gui/src-tauri/Cargo.toml`, `gui/src-tauri/tauri.conf.json`
- `CHANGELOG.md` に v0.2.1 セクション追加 (Security / Fixed / Changed / CI)

### Out of scope (別議論 / 別 issue 起票検討)

- GitHub CodeQL workflow 新規有効化 (継続的 static analysis、本 patch では cargo/npm audit のみで開始)
- Dependabot grouped update 設定の見直し (Rust 側も group 化、schedule daily 化) — Q4 で deferred 判断、follow-up issue 候補
- Secret scanning 有効化
- v0.2.0 配布バイナリの差し戻し or 公開警告 (v0.2.0 リリースから日が浅いため、v0.2.1 ZIP 公開で対応十分と判断)
- L3 (v0.3.0) スコープへの security / UX 機能追加 (本リリースは patch に専念)
- third-party scanner (trivy / grype 等)、pre-commit hook の導入

## 5. Branch Strategy

`docs/release-process.md` §ブランチ戦略 に従い、`develop-x.x.x` 統合ブランチ + 作業ブランチの標準フローで運用する。

```text
main (タグ v0.2.0)
 └── develop-0.2.1 (本 spec で main から新規 cut、v0.2.1 統合ブランチ)
       ├── claude/<scope>-deps (Track A)            → PR → develop-0.2.1
       ├── claude/issue-374-codec-note (Track B-1)  → PR → develop-0.2.1
       ├── claude/issue-743-756-orphan (Track B-2)  → PR → develop-0.2.1
       ├── claude/issue-749-readme-ja (Track B-3)   → PR → develop-0.2.1
       ├── claude/issue-458-bug-template (Track B-4) → PR → develop-0.2.1
       ├── claude/ci-security-audit (Track C)       → PR → develop-0.2.1
       └── claude/release-v0.2.1 (Track D)          → PR → develop-0.2.1
              └── 全 Track 統合後 develop-0.2.1 → main PR
                     └── マージ + git tag v0.2.1
                            └── release.yml 発火 → Portable ZIP + GitHub Release
                                   └── main から develop-0.3.0 を新規 cut + version 0.3.0 bump
```

### 作業ブランチ名候補

- 現 worktree branch (`claude/crazy-swirles-bed20b`、HEAD = `d61b8fd` で main から 1 commit (spec) 先行) を **Track A の作業ブランチに転用**するか、それとも spec commit のみを保持して別 branch で Track A を進めるかは writing-plans 段階で確定
- 他 Track の作業ブランチは plan 段階で worktree 戦略 (単一 worktree で skill ベース dispatch / per-Track worktree) と合わせて確定

### #743 と #756 の Track 統合理由

両 issue は同じ原因 (Windows process tree orphan) を扱う。#756 が具体的 bug、#743 が audit task。両者を 1 PR で扱うことで:

- fix と audit document を同一 PR でレビュー可能 (前提・対策・検証の整合性確認が容易)
- `enforce-acceptance-criteria` skill が #743 受け入れ条件 (audit document 作成、kill_tracked_processes 実機検証、orphan risk fix 起票) と #756 受け入れ条件 (Windows tree kill 実装) を同時に検証可能

## 6. Update Plan

### Track A: Security alerts (1 PR、5 commit 構造)

#### Commit A-1: `chore(deps): bump fast-uri 3.1.0 → 3.1.2 (#2, #3)`

- `cd gui && npm install fast-uri@3.1.2 --package-lock-only`
- 影響: `gui/package-lock.json` のみ
- 解決 alert: #2, #3

#### Commit A-2: `chore(deps): bump tauri 2.10.3 → 2.11.1 + tauri-build (#6)`

- `gui/src-tauri/Cargo.toml`:
  - `tauri = "=2.11.1"` (現 `=2.10.3`、`first_patched: 2.11.1`、2.11.0 では未 fix)
  - `tauri-build = "=2.6.0"` (現 `=2.5.6`、tauri 2.11.0 release notes で bump 記載)
- `cd gui/src-tauri && cargo update -p tauri --precise 2.11.1`
- 影響: `gui/src-tauri/Cargo.toml`, `gui/src-tauri/Cargo.lock`
- 解決 alert: #6

#### Commit A-3: `chore(deps): align tauri-plugin-* with tauri 2.11`

- `tauri-plugin-dialog` / `-fs` / `-shell` の tauri 2.11 互換 latest 版を plan 段階で確認後 bump (現状 2.7.0 / 2.5.0 / 2.3.5)
- 影響: `gui/src-tauri/Cargo.toml`, `gui/src-tauri/Cargo.lock`
- 解決 alert: なし (互換性整合)

#### Commit A-4: `chore(deps): verify transitive rand 0.8.6 / glib 0.20.0 (#4, #5)`

- Commit A-2 / A-3 後の `Cargo.lock` を確認、transitive で解決されていれば commit 内容は CHANGELOG メモのみ
- 未解決の場合のみ個別 `cargo update -p rand@0.7.3 --precise 0.8.6` / `cargo update -p glib --precise 0.20.0`
- 影響: `gui/src-tauri/Cargo.lock` (該当時のみ)
- 解決 alert: #4, #5

#### Commit A-5: `chore(self-test): security audit local verification`

- `cd gui/src-tauri && cargo audit` で local audit 実行、output を PR 本文に貼付
- `cd gui && npm audit --omit=dev` (runtime のみ) / `npm audit` (full) の output を PR 本文に貼付
- Track C で追加する CI workflow との突合せ確認

### Track B-1: #374 metadata note codec 不正確

#### 修正内容

- `allaganeye/commands/split_matches.py` (`_split_and_write_metadata` の note 定義) を case 2 (codec 依存定数の削除) で更新
- 旧: `"Split times are approximate due to keyframe-aligned copy mode. Actual start/end may differ by up to the source keyframe interval (typically 2s for OBS recordings)."`
- 新: `"Split times are approximate due to keyframe-aligned copy mode. Actual start/end may differ by up to the source keyframe interval."`
- pytest unit test (該当 metadata 生成テスト) を更新

### Track B-2: #743 + #756 Windows process tree orphan

#### 修正内容 (#756)

- `gui/src-tauri/src/lib.rs` で Windows Job Object を用いた process tree kill を実装 (Option A 推奨):
  - `windows-rs` (または `winapi`) crate を deps に追加
  - `start_detect` 等の spawn site で `CreateJobObject` + `SetInformationJobObject` (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`) + `AssignProcessToJobObject` を実装
  - `kill_tracked_processes` で Job handle を drop することで子孫プロセスを一括 kill
- Option B (`taskkill /T /F /PID`) は fallback として保持 (Job Object 設定 fail 時用)

#### Audit document (#743)

- `docs/` 配下に `process-tree-orphan-audit.md` を新規追加:
  - 6 spawn site (`probe_video_with` / `ensure_thumbnail_exists` / `extract_brightness_window_impl` / `run_ffmpeg_export_attempt` / `start_detect` / `open_folder_in_explorer`) の振る舞いを記録
  - Job Object 適用前 (= 現状) と適用後の挙動差を実機検証で示す
  - `explorer.exe` 等の意図的 detach プロセスは Job 対象外として明記
- `enforce-acceptance-criteria` skill で #743 受け入れ条件全件を逐条検証 (1 PR 内に audit doc + fix が揃う)

### Track B-3: #749 Portable ZIP README.txt 日本語化

#### 修正内容

- `scripts/build-portable-zip.ps1` の `Format-ReadmeContent` 関数の text template を日本語化:
  - 見出し: `## 使い方` / `## ライセンス` / `## トラブルシューティング` 等
  - 法的引用 (MIT / LGPLv3 / PSF License 文言) は原文保持
- `scripts/tests/build-portable-zip.Tests.ps1` の Pester assertion を日本語見出しに更新

### Track C: cargo audit + npm audit CI workflow

#### 新規ファイル: `.github/workflows/security-audit.yml`

```yaml
name: Security Audit

on:
  pull_request:
    paths:
      - 'gui/src-tauri/Cargo.lock'
      - 'gui/src-tauri/Cargo.toml'
      - 'gui/package-lock.json'
      - 'gui/package.json'
      - '.github/workflows/security-audit.yml'
  workflow_dispatch:

jobs:
  cargo-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: actions-rust-lang/setup-rust-toolchain@v1
      - run: cargo install cargo-audit --locked
      - run: cd gui/src-tauri && cargo audit --deny warnings

  npm-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-node@v6
      - run: cd gui && npm ci
      - run: cd gui && npm audit --audit-level=high
```

- **fail 条件**:
  - `cargo audit --deny warnings`: medium 以上の advisory 検出で fail (Cargo の audit level)
  - `npm audit --audit-level=high`: high 以上で fail (dev-only の medium/low は warning として通過)
- 既存 `ci.yml` には touch せず、独立 workflow として追加 (ci.yml の規模を肥大化させない)
- pull_request trigger で manifest 変更のある PR にのみ実行 (CI 時間節約)

#### Track A との結合テスト

- Track C を Track A より先にマージすると、Track A の PR で security-audit.yml が走り、Cargo.lock / package-lock.json の更新が green になることを CI で確認できる
- 推奨マージ順: **Track C → Track A** (Track C で baseline 確立、Track A で確実に脆弱性消化を検証)

### Track D: Version bump + CHANGELOG (リリース直前)

#### Commit D-1: `chore(release): bump version 0.2.0 → 0.2.1`

- 4 ファイル: `pyproject.toml`, `gui/package.json`, `gui/src-tauri/Cargo.toml`, `gui/src-tauri/tauri.conf.json`

#### Commit D-2: `docs(changelog): add v0.2.1 section`

- `CHANGELOG.md` に新規セクション追加:

  ```markdown
  ## v0.2.1 - 2026-05-?? - Patch release

  ### Security

  - tauri 2.10.3 → 2.11.1 (medium: Origin Confusion, GHSA-7gmj-67g7-phm9)
  - glib transitive → 0.20.0 (medium: VariantStrIter unsoundness, GHSA-wrw7-89jp-8q8g, Windows build 未使用)
  - rand transitive 0.7.3 → 0.8.6 (low: rng() unsoundness, GHSA-cq8v-f236-94qc, build-dep のみ)
  - fast-uri 3.1.0 → 3.1.2 (high: GHSA-v39h-62p7-jpjc / GHSA-q3j6-qgpj-74h6, dev-only deps)

  ### Fixed

  - #756: detecting 中の GUI 終了で ffmpeg 子孫プロセスが残留する問題を Windows Job Object で解消
  - #374: metadata.json の `note` 文言から codec 依存定数を削除し誤情報を解消

  ### Changed

  - #749: Portable ZIP 内 `README.txt` を日本語化
  - #458: `.github/ISSUE_TEMPLATE/bug_report.yml` の `docs/bug-report-guide.md` link を `develop-0.2.0` から `main` に更新、未公開 placeholder を削除

  ### CI / Infrastructure

  - cargo audit + npm audit を `.github/workflows/security-audit.yml` で PR ごとに実行
  - #743: Windows process tree orphan audit を `docs/process-tree-orphan-audit.md` として整理
  - #458: GitHub Issue Template の UI 動作 (template 選択 / 必須項目 block / 自動付与 / blank 経路併存) を実機検証完了
  ```

## 7. Verification (Iron Law 6 準拠)

### 7.1 自動チェック (PR 作成前に local + CI 両方で pass)

| 範囲 | コマンド | 該当 Track |
| --- | --- | --- |
| Python | `ruff check . / ruff format --check . / pyright / pytest` | A (依存変更時のみ regression check) / B-1 / D |
| GUI frontend | `cd gui && npm run lint / typecheck / test / build` | A / D |
| GUI Rust | `cd gui/src-tauri && cargo check / cargo test` | A / B-2 / D |
| docs | `bash scripts/check-markdownlint.sh` | B-2 (audit doc) / B-3 (README 日本語) / D (CHANGELOG) |
| Pester | `pwsh scripts/tests/build-portable-zip.Tests.ps1` | B-3 |
| Security audit | `cargo audit` / `npm audit` (Track C の CI workflow も同等) | A / C |

### 7.2 実機検証 (Idios 依頼、Iron Law 6 で必須)

| Track | 検証項目 |
| --- | --- |
| A | Tauri GUI 起動 + golden path (drop → detecting → complete → preview → export) + H.264 エンコーダ自動選択動作 (`select_h264_encoder_for_export`) + 既存 `recent.json` の load |
| B-1 | 短い MKV (AV1 サンプルあれば) で split → metadata.json の note 文言確認 |
| B-2 | detecting 中に GUI を × で閉じて ffmpeg 子孫プロセスが Task Manager で 5 秒以内に全消去されることを実機確認。`open_folder_in_explorer` 経由で開いた Explorer は kill されないことも併せて確認 |
| B-3 | Portable ZIP build → 展開後 README.txt が日本語表示されることを Notepad で確認 |
| B-4 | `https://github.com/Idios/kobutachan-allaganeye/issues/new/choose` を開いて bug 報告テンプレ表示確認、必須 textarea / checkbox 未入力時の submit block、自動付与 (title prefix / labels / assignees)、blank 経路併存、`docs/bug-report-guide.md` link が 200 で開けることを実測 |
| D | local Portable ZIP build (`pwsh ./scripts/build-portable-zip.ps1 -Version 0.2.1`) で ZIP 生成 + `docs/l2-e2e-checklist.md §3 T1` smoke |

### 7.3 受け入れ条件 (Iron Law 1 準拠)

#### Security alerts (Track A)

- [ ] Dependabot alert #2, #3, #4, #5, #6 が PR マージ後 24h 以内に auto-resolve
- [ ] PR #758 が auto-close (or 手動 close、reason: "superseded by v0.2.1 Track A PR")

#### UX issues (Track B)

- [ ] #374 受け入れ条件: metadata.json の note から codec 依存定数 (`typically 2s for OBS recordings`) が削除され、AV1 サンプルで誤情報なし確認
- [ ] #743 受け入れ条件 (5 件): audit document 作成、kill_tracked_processes 実機検証、親 app crash 時の挙動確認、orphan risk fix を本 PR に統合 (= #756)、audit 結果を `docs/` 配下に記録
- [ ] #749 受け入れ条件: Portable ZIP README.txt が日本語、Pester assertion で日本語見出し検証
- [ ] #756 受け入れ条件: ffmpeg 子孫プロセスが GUI 終了時に Windows Task Manager で 5 秒以内に全消去
- [ ] #458 受け入れ条件: bug_report.yml の link が `main` を指し placeholder 削除済、L3 初期残作業チェックリスト (UI 動作確認 7 項目) すべて pass

#### CI 強化 (Track C)

- [ ] `.github/workflows/security-audit.yml` が PR ごとに cargo audit + npm audit を実行
- [ ] Track A の PR でこの workflow が green に通る (脆弱性消化の自己テスト)
- [ ] Track C の PR 自体でも workflow が green (現状の Cargo.lock / package-lock.json が green になっていること、または Track A マージ後に green になることを期待)

#### Release (Track D)

- [ ] [release.yml](.github/workflows/release.yml) が `allaganeye-v0.2.1-windows.zip` を artifact + Release に添付
- [ ] Portable ZIP の `allaganeye-gui.exe` が起動し、export まで通る (Idios 実機検証)
- [ ] `main` から `develop-0.3.0` が cut され、version が 0.3.0 に bump

## 8. Release Flow

1. main から `develop-0.2.1` を cut + push (`git checkout main && git pull && git checkout -b develop-0.2.1 && git push -u origin develop-0.2.1`)
2. 各 Track の作業ブランチ → PR → `develop-0.2.1` マージ (Track 並列実施可能。推奨順: **C → A → B-1 / B-2 / B-3 / B-4 (並列) → D**)
3. 全 Track 統合後、PR `develop-0.2.1 → main` を作成
4. PR `develop-0.2.1 → main` をマージ
5. `main` HEAD にタグ: `git tag -a v0.2.1 -m "Release v0.2.1: Patch release"` + `git push origin v0.2.1`
6. [release.yml](.github/workflows/release.yml) が以下を自動実行:
   - Portable ZIP build (`scripts/build-portable-zip.ps1 -Version 0.2.1`)
   - SHA256 verify (Python embed / get-pip / FFmpeg)
   - GitHub Release 作成 (`extract_release_notes.py 0.2.1` で CHANGELOG から抽出)
7. PR 作者 (Claude or Idios) が以下を手動確認:
   - Dependabot alerts 5 件の auto-close 状態
   - PR #758 の close 状態
   - UX issue 5 件 (#374 / #458 / #743 / #749 / #756) の close (`/close-issue` skill で受け入れ条件再検証 + 手動クローズ、Iron Law 4)
   - GitHub Release ページに ZIP + release notes が掲載
8. `main` から `develop-0.3.0` 新規 cut + version 0.3.0 bump コミット (release-process.md §レイヤー間移行手順)

## 9. References

### Project docs

- [docs/release-process.md](../../release-process.md) §ブランチ戦略 / §タグ運用 / §レイヤーリリース受け入れゲート (共通項目)
- [docs/l2-workflow.md](../../l2-workflow.md) §「PR 作成 Pre-flight」 / §「Self-Test Report 規約」 / §「(A) PR 内修正優先 規約」
- [docs/l2-e2e-checklist.md](../../l2-e2e-checklist.md) §3 T1 (Portable ZIP smoke)
- [CLAUDE.md](../../../CLAUDE.md) §Iron Law / §PR 作成ルール / §バグ修正時の方針

### Security advisories

- [GHSA-7gmj-67g7-phm9](https://github.com/advisories/GHSA-7gmj-67g7-phm9) — tauri Origin Confusion
- [GHSA-wrw7-89jp-8q8g](https://github.com/advisories/GHSA-wrw7-89jp-8q8g) — glib VariantStrIter unsoundness
- [GHSA-cq8v-f236-94qc](https://github.com/advisories/GHSA-cq8v-f236-94qc) — rand custom logger unsoundness
- [GHSA-v39h-62p7-jpjc](https://github.com/advisories/GHSA-v39h-62p7-jpjc) — fast-uri host confusion
- [GHSA-q3j6-qgpj-74h6](https://github.com/advisories/GHSA-q3j6-qgpj-74h6) — fast-uri path traversal

### GitHub artifacts

- [PR #758](https://github.com/Idios/kobutachan-allaganeye/pull/758) — Dependabot fast-uri 3.1.2 PR
- [Release v0.2.0](https://github.com/Idios/kobutachan-allaganeye/releases/tag/v0.2.0)
- [Issue #374](https://github.com/Idios/kobutachan-allaganeye/issues/374) — metadata.json note codec
- [Issue #458](https://github.com/Idios/kobutachan-allaganeye/issues/458) — bug_report.yml 同意 checkbox 付き UI 検証残作業
- [Issue #743](https://github.com/Idios/kobutachan-allaganeye/issues/743) — Windows process group orphan audit
- [Issue #749](https://github.com/Idios/kobutachan-allaganeye/issues/749) — Portable ZIP README.txt 日本語化
- [Issue #756](https://github.com/Idios/kobutachan-allaganeye/issues/756) — ffmpeg 子孫プロセス残留
- [docs/bug-report-guide.md](../../bug-report-guide.md) — Track B-4 link 先 (Idios 提供)
