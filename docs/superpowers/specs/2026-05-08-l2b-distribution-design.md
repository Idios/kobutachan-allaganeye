# Lane IV-a / Group F: L2b 配布まわり 4 件 設計

> **Status**: design (brainstorming 確定、writing-plans 待ち)
> **作成**: 2026-05-08 / session `practical-wright-c6dae8`
> **更新**: 2026-05-08 / session `agitated-tesla-f69df7` — §2 #681 を in-place rewrite (scope = get-pip.py 限定、approach = GitHub raw + version tag、empirical 検証で旧 §2 提案 URL の 404 を確認した上で代替案に確定)
> **対象 issue**: #616 / #681 / #617 / #668 (4 件、roadmap §3-bis Lane IV-a)
> **上位 plan**: [`docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md`](../plans/2026-05-07-l2-v020-roadmap.md)

## §0 概要

### Lane IV-a / Group F の目的

L2 (v0.2.0) リリース残作業のうち、**L2b 配布まわり** 4 件を 1 spec / 4 章 / 4 PR 独立で扱う。release blocker (#681 build-windows CI 再陳腐化) と外部ユーザー受け入れ準備 (#668 同梱物健全性チェック) を含む。

### 章順 (独立性順 = merge conflict リスク低い順)

| 章 | issue | priority | scope | 並行安全度 |
| --- | --- | --- | --- | --- |
| §1 | #616 | P3 | `.github/workflows/release.yml` 2 行修正 | high (yml 単独) |
| §2 | #681 | P2 | `scripts/build-portable-zip.ps1` get-pip pin (line 53-62) | high (line 範囲独立) |
| §3 | #617 | P2 | `scripts/build-portable-zip.ps1` `Get-LauncherTemplate` (line 200+) | mid (§2 と同 file) |
| §4 | #668 | P2 | Rust + Python + TS + build script + doc (横断) | mid (lib.rs touch、#663 と low risk) |

### 全体方針

- **1 spec / 4 章 / 4 PR**: roadmap §3-bis 推奨、各 PR = 1 issue scope (Iron Law 3)
- **PR 出順**: §1 → §2 → §3 → §4 (独立性順、§3 着手時は §2 を develop-0.2.0 に取り込み済の前提で `git merge` Pre-flight)
- **brainstorming 確定事項**: 各章の主要判断点 (Recommended 採用) は本 spec で確定。§4 (#668) の dev mode skip 制御方法等 minor 調査事項は writing-plans フェーズに持ち越し
- **Lane 配置**: roadmap §3-bis Lane IV-a (wave 0)、並行 lane = Lane I-A (Group A AppError) / Lane IV-b (Group G workflow) / Lane IV-c (Group H lint+CLI)

### Iron Law 整合

- **Iron Law 1** (受け入れ条件): 各章で元 issue を逐条引用、各 PR review で `enforce-acceptance-criteria` skill を必ず呼ぶ
- **Iron Law 3** (scope): 1 PR = 1 issue。§2 #681 は 2026-05-08 in-place rewrite で scope を get-pip.py 限定に確定 (旧 §2 で予定していた BtbN URL aging は別 issue 起票して Lane IV-a の 5 章目として扱う)
- **Iron Law 4** (close keyword): 全 PR で `Closes/Fixes/Resolves` 禁止、`Refs #N` のみ
- **Iron Law 6** (Pre-flight): 各 PR で `git fetch origin develop-0.2.0` + 取り込み未済 commit 確認 + 並行 worktree PR 重複確認

---

## §1 #616: CI artifact zip 名にバージョン番号付与

### 背景

- 現状 [`release.yml:212`](../../.github/workflows/release.yml) の `name: allaganeye-portable-windows` → PR Actions tab からダウンロードする CI artifact zip 名にバージョン番号無し
- 複数 PR の zip をローカル保管比較時に区別不可、リネームを強いられる
- リリース zip (`release` job、tag push 時生成) は `allaganeye-vX.Y.Z-windows.zip` で対応済 (変更不要)

### 受け入れ条件 (元 issue 逐条)

- [ ] PR Actions tab からダウンロードする CI artifact zip 名が `allaganeye-portable-windows-vX.Y.Z.zip` 形式
- [ ] release job の download-artifact が新 name と整合、tag push でのリリース zip (`allaganeye-vX.Y.Z-windows.zip`) は引き続き動作
- [ ] CI 全 jobs PASS

### 設計

- `release.yml:212` (`build-windows.upload-artifact.name`) を `allaganeye-portable-windows-v${{ needs.version-check.outputs.version }}` に変更
- `release.yml:231` (`release.download-artifact.name`) も同じ式で同期 (upload と一致)

### 影響範囲

- `.github/workflows/release.yml` line 212 / 231 (2 箇所、各 1 行)

### 実装方針

- 1 PR で 2 行修正
- `version-check` job が `outputs.version` を提供している前提を踏襲 (既存挙動)
- tag push の release zip 生成 path は別 step (`Create release archive` → `bash` で `zip -r ... allaganeye-v${{...}}` を直接呼ぶ) のため、download-artifact の name 変更でも生成 zip 名は不変

### テスト方針

- CI `build-windows` job が PASS = yml 構文 valid (実機検証)
- artifact 名は PR Actions tab で **Idios 目視** (machine-unverifiable、Self-Test Report で `-` bullet)
- release job は tag push でしか走らないため CI では検証不可、`v0.2.0` リリース時に確認

### リスク / トレードオフ

- 低リスク。download-artifact の name 変更でローカル zip 名も変わるが、CI 内部用 artifact なので外部影響なし

### 開放問題 (writing-plans 持ち越し)

なし (本 spec で受け入れ条件と設計が確定)

---

## §2 #681: get-pip.py SHA pin 陳腐化を versioned URL で構造的に解消

> **Note (2026-05-08 in-place rewrite)**: 本 §2 は session `agitated-tesla-f69df7` で内容更新。
> 旧 §2 (session `practical-wright-c6dae8`、commit `a3a4254`) は (i) get-pip.py + BtbN URL aging 包含 (option B)、(ii) `bootstrap.pypa.io/pip/<pip-version>/get-pip.py` URL pattern を提案していたが、empirical 検証 + scope 確定によりいずれも変更:
>
> 1. **scope を `(A) get-pip.py 限定` に確定** — Iron Law 3 (1 PR = 1 issue) 厳守。BtbN URL aging は別 issue 起票して Lane IV-a の 5 章目で扱う
> 2. **`bootstrap.pypa.io/pip/<pip-version>/get-pip.py` は empirical に 404 Not Found** — PyPA は `pip/<py-interpreter-version>/` (例: `3.9/`) のみ提供、pip-version 別 URL は未提供。代替に `https://raw.githubusercontent.com/pypa/get-pip/<release-tag>/public/get-pip.py` (例: tag `26.1.1`) は 200 OK、tag は immutable per release で SHA drift しない

### 背景

`scripts/build-portable-zip.ps1` の `$GetPipUrl = 'https://bootstrap.pypa.io/get-pip.py'` (unversioned) は PyPA が pip 新版を release するたびに content を上書きするため、固定 SHA pin が陳腐化し `build-windows` CI が定期的に fail する。

#### 過去事例

- [#649](https://github.com/Idios/kobutachan-allaganeye/issues/649) (closed) — PR [#651](https://github.com/Idios/kobutachan-allaganeye/pull/651) で短期 fix (SHA pin 更新)
- PR [#675](https://github.com/Idios/kobutachan-allaganeye/pull/675) Round 2 #7 — 同 short-term fix (`106AE019...` → `66904BCC...`)
- 同パターンが v0.2.0 スコープ内で再発、未起票の長期対応が root cause

### 受け入れ条件 (元 issue #681 から、AC 編集なし)

- [ ] PyPA 側更新で `build-windows` CI が fail しない仕組みに切り替え
- [ ] 再発防止 regression test 含む (上流変更 simulate でも fail しない)
- [ ] [`scripts/build-portable-zip.ps1:54-61`](../../scripts/build-portable-zip.ps1) の comment block (PR #651 で追加された手順) を新方式に更新
- [ ] `installer-pester` CI が新方式で全 PASS

### 設計

#### 採用案: option α (GitHub raw + version tag)

- `$GetPipUrl` を `https://raw.githubusercontent.com/pypa/get-pip/26.1.1/public/get-pip.py` に置換 (versioned tag、immutable per release)
- `$GetPipSha256` の値は **現値 `66904BCCB878E363DB6236EA900E6935E507DCB887E9F178F6212EDFE7F46A76` を維持** — 現 `bootstrap.pypa.io/get-pip.py` が serve する内容と pypa/get-pip tag `26.1.1` の SHA は byte-for-byte 一致 (本セッションで実測 verify 済み)。Portable ZIP の get-pip.py 取得結果は変更前後で完全同一 = build artifact ゼロ regression
- comment block (line 54-61) を新ピン方式 + bump 手順 + Pester verify 手順 で書き換え (`#681` を主参照、`#649` `#675` を背景として並記)
- 既存の `Invoke-Download` 関数 / `Invoke-WebRequest` / SHA256 verify 経路は **触らない** (URL 文字列のみ変更)

#### 不採用案

| 案 | 概要 | 不採用理由 |
| --- | --- | --- |
| (β) ベンダリング | `scripts/vendored/get-pip.py` を repo に commit | option α 単独で AC 構造的に充足、+2.2 MB の repo 膨大化を回避。GitHub 障害頻度が問題化したら再検討 |
| (γ) PyPI pip wheel 直接ダウンロード | `pip-X.Y-py3-none-any.whl` を bootstrap | get-pip.py のブートストラップ処理を再実装する engineering cost、現 AC を満たすために不要 |
| 旧 §2 案 (`bootstrap.pypa.io/pip/<pip-ver>/`) | PyPA versioned URL | empirical に 404 Not Found (PyPA 未提供)、roadmap 提案時の仮定が不正確 |

#### Why versioned URL 方式が AC #1 を構造的に satisfies するか

- `pypa/get-pip` repo の release tag (例: `26.1.1`) は immutable per tag (force-push は理論上可能だが SHA pin が defense-in-depth)
- PyPA が `bootstrap.pypa.io/get-pip.py` を更新しても、当 URL は影響を受けない = SHA drift 構造的に発生不可
- 将来 pip 新版を bundle したいときは tag + SHA を **同時に明示的に bump** (= 暗黙の SHA drift が消える、bump は git diff で auditable)
- `pypa/get-pip` repo の tag retention 実績: `2.6` 系まで全 tag 残存を実測確認 → 削除リスクは無視可能

#### 新コメントブロック (line 54-61 置換案)

```pwsh
$GetPipUrl = 'https://raw.githubusercontent.com/pypa/get-pip/26.1.1/public/get-pip.py'
# #681 -- Pin get-pip.py via the pypa/get-pip GitHub raw URL with a release
# tag (immutable per tag), not bootstrap.pypa.io/get-pip.py (unversioned;
# drifts whenever PyPA refreshes pip and breaks build-windows CI -- see
# #649 short-term fix and PR #675 Round 2 follow-up).
#
# To bump pip when a new release is required:
#   1. Pick a new tag from https://github.com/pypa/get-pip/tags (e.g. 26.1.2)
#   2. Update the URL above and the SHA below:
#        Invoke-WebRequest `
#          "https://raw.githubusercontent.com/pypa/get-pip/<tag>/public/get-pip.py" `
#          -OutFile get-pip.py
#        Get-FileHash get-pip.py -Algorithm SHA256
#   3. Verify the regression test still passes:
#        Invoke-Pester -Path scripts/tests/build-portable-zip.Tests.ps1
$GetPipSha256 = '66904BCCB878E363DB6236EA900E6935E507DCB887E9F178F6212EDFE7F46A76'
```

### 影響範囲

- `scripts/build-portable-zip.ps1` (line 53-62 の get-pip URL / pin / comment block、SHA value は維持)
- `scripts/tests/build-portable-zip.Tests.ps1` (新 `Describe 'GetPip pinning (#681)'` block を末尾 append)

### 実装方針

PR 1 つ、minimum-change:

1. `$GetPipUrl` の値を versioned tag URL に置換 (`bootstrap.pypa.io/get-pip.py` → `raw.githubusercontent.com/pypa/get-pip/26.1.1/public/get-pip.py`)
2. comment block (line 54-61) を新ピン方式の文言に書き換え (history note + bump 手順 + Pester verify 手順)
3. `scripts/tests/build-portable-zip.Tests.ps1` の末尾に新 `Describe 'GetPip pinning (#681)'` を append (URL pattern regex test + SHA format test)
4. `$GetPipSha256` value は維持 (tag `26.1.1` の SHA と一致するため変更なし)、BtbN や他の pin は touch しない

### テスト方針

#### Pester (CI で実行可)

新 `Describe 'GetPip pinning (#681)'` block (`scripts/tests/build-portable-zip.Tests.ps1` 末尾 append):

```pwsh
Describe 'GetPip pinning (#681)' {
  It 'pins $GetPipUrl to a versioned pypa/get-pip GitHub raw URL' {
    # bootstrap.pypa.io/get-pip.py is unversioned and PyPA refreshes it without
    # notice, drifting our hardcoded SHA pin and breaking build-windows CI
    # (#649, PR #675 Round 2). #681 pins the URL to a versioned pypa/get-pip
    # GitHub raw URL whose content is immutable per release tag.
    # This regression test guards against accidental rollback to the
    # unversioned bootstrap.pypa.io URL.
    $GetPipUrl | Should -Match '^https://raw\.githubusercontent\.com/pypa/get-pip/[\w.\-]+/public/get-pip\.py$'
  }

  It 'pins $GetPipSha256 to a syntactically valid SHA256' {
    # SHA256 verify (Invoke-Download) stays as defense-in-depth even with the
    # immutable URL: catches the (very unlikely) force-push scenario on the
    # upstream pypa/get-pip release tag.
    $GetPipSha256 | Should -Match '^[A-Fa-f0-9]{64}$'
  }
}
```

既存 `It 'throws when the downloaded SHA256 does not match'` (line 59-70) を再利用 — content tampering 経路 defense (重複追加しない)。

#### CI (自動)

- `installer-pester` job 全 `Describe` pass (新 `GetPip pinning (#681)` 含む)
- `build-windows` job が実 Portable ZIP build を完走 (新 URL 経由で get-pip.py を取得 + pip install 成功)
- `markdownlint` job が本 spec doc 更新を pass

#### 実機検証 (Idios)

- **不要** (Iron Law 6 trigger 表に該当する path に touch しない: `gpu_detector.py` / `audio/*.py` / `video/detector.py` / `gui/src-tauri/**` 全て無関与。PowerShell + CI で十分)

### リスク / トレードオフ

- **GitHub outage**: build 時 `Invoke-WebRequest` が throw → script fail。PyPA outage と同じ external dependency 障害類型、net new リスクなし
- **pinned tag が `pypa/get-pip` repo から削除**: 理論上のリスク。release tag は upstream 運用で削除されない (`2.6` 系まで全 tag 残存を実測)。発生時は SHA verify failure → 直近 stable tag に bump
- **GitHub raw URL の rate limit**: build per CI run 1 回の取得なので問題なし
- **SHA pin force-push 攻撃**: SHA mismatch を `Invoke-Download` が即 throw、defense-in-depth 維持
- **PR size**: scope を get-pip.py 限定にしたため small PR (touched files = 2)、Iron Law 3 整合

### 開放問題 (writing-plans 持ち越し)

- pip version bump 判断方針 (現 `26.1.1` を継続使用 / future 任意のタイミングで手動 bump / Renovate 等の自動化、いずれも本 PR 範囲外)
- BtbN URL aging は **本 §2 scope 外** (Iron Law 3)。Lane IV-a の 5 章目として新 issue 起票予定 (本セッション 2026-05-08 で scope 確定、起票時期は別途判断)
- **issue #681 AC は変更しない** (元 issue 本文の受け入れ条件 4 項を本 §2 で逐条充足するため、AC 編集の Idios 確認は不要 = roadmap §3-bis の "AC 追記" 経路を採らない方針に確定)

---

## §3 #617: allaganeye.bat ダブルクリックで GUI 起動

### 背景

- PR #615 で `allaganeye-gui.exe` を Portable ZIP に同梱済 (#570 issue)
- 現状 `Get-LauncherTemplate` (`scripts/build-portable-zip.ps1`) は引数なし → ヘルプ + pause で、Windows 一般的な「.bat ダブルクリック = アプリ起動」UX と乖離
- `.bat` 自体にカスタムアイコン埋込は Windows 仕様上不可 (元 issue Note)、本章は対象外

### 受け入れ条件 (元 issue 逐条)

- [ ] `allaganeye.bat` ダブルクリック → `allaganeye-gui.exe` 起動 (Idios 目視、cmd ウィンドウ残らない)
- [ ] `allaganeye.bat --help` / `-h` / `/?` でヘルプ表示
- [ ] `allaganeye.bat split <video>` 等の CLI 用法が従来通り (動画ドラッグ含む)
- [ ] CLI-only ZIP (GUI exe 未同梱) で `.bat` ダブルクリック → 従来通りヘルプ表示にフォールバック
- [ ] `Invoke-Pester scripts/tests/build-portable-zip.Tests.ps1` 全 PASS (新挙動 + 既存 #580 EXIT_CODE idiom regression)
- [ ] CI 全 jobs PASS

### 設計

`Get-LauncherTemplate` の `.bat` テンプレートを以下の **優先順位** で分岐 (上から順に判定、最初にマッチした分岐を実行):

| # | 条件 | 動作 |
| --- | --- | --- |
| 1 | 引数 = `--help` / `-h` / `/?` | ヘルプ表示 + pause (明示) |
| 2 | 引数 = 動画ファイル (`.mp4` / `.mkv` / `.avi` / `.mov`、ドラッグ) | `python -m allaganeye split %*` (旧挙動) |
| 3 | その他引数あり (`detect` / `split --from-metadata` / `debug-brightness` 等) | `python -m allaganeye %*` (旧挙動) |
| 4a | 引数なし、`allaganeye-gui.exe` 存在 | `start "" "%~dp0allaganeye-gui.exe"` → `exit /b 0` で bat 即終了 |
| 4b | 引数なし、`allaganeye-gui.exe` 不在 (CLI-only ZIP) | ヘルプ表示 + pause (旧 fallback) |

> 注: path 表記 (`%~dp0` か `%PAYLOAD%` か) は既存 `Get-LauncherTemplate` の idiom に合わせる (writing-plans 段階で確認)。
>
> **`--help` を引数なしより上位に置く理由**: ユーザーが `allaganeye.bat --help` と書いた場合に GUI が起動してしまう事故防止 (元 issue にも記載)。

### 影響範囲

- `scripts/build-portable-zip.ps1` の `Get-LauncherTemplate` 関数 (大半が修正対象)
- `scripts/tests/build-portable-zip.Tests.ps1` (Pester test 追加)
- `scripts/build-portable-zip.ps1` の `Format-ReadmeContent` 関数 (README.txt 案内文)

### 実装方針

1. `Get-LauncherTemplate` の `.bat` template を 4 分岐に書き換え
2. `start "" "..."` で GUI を非同期起動 → `exit /b 0` で bat 即終了 (cmd ウィンドウ残らない)
3. `if exist` で `allaganeye-gui.exe` 有無を確認、CLI-only ZIP fallback
4. 既存 EXIT_CODE 伝搬 idiom (`set EXIT_CODE=%ERRORLEVEL%` + `endlocal & exit /b %EXIT_CODE%`、PR #580 由来) は CLI 用法側 (分岐 2 / 3) で維持
5. ヘルプ文言に「ダブルクリックで GUI 起動」を **1 番目** に追記、CLI 用法は 2-3 番目
6. `Format-ReadmeContent` (README.txt) も同様に更新

### テスト方針

#### Pester (CI で実行可)

- 引数なし + GUI exe 存在の分岐に `start "" "..."` および `exit /b 0` を含む
- `if exist "...allaganeye-gui.exe"` 分岐を含む
- `--help` / `-h` / `/?` の 3 分岐を含む
- 既存 #580 EXIT_CODE 伝搬 idiom が CLI 用法側 (分岐 2/3) で残存 (regression test)

#### 実機検証 (Idios、Iron Law 6 trigger 必須)

- GUI 同梱 ZIP で `.bat` ダブルクリック → GUI 起動 + cmd ウィンドウ残らない
- CLI-only ZIP で `.bat` ダブルクリック → ヘルプ表示 + pause
- `--help` / 動画ドラッグ / `split` 引数指定の旧挙動が壊れていない
- writing-plans / 実装 PR で `AskUserQuestion` により Idios に依頼 (必須)

### リスク / トレードオフ

- `start ""` で起動した GUI は bat と独立、bat 終了後も GUI は動作 (Windows 標準挙動 OK)
- Portable ZIP の payload 構造 (`allaganeye-vX.Y.Z/allaganeye.bat` と同階層 `allaganeye-gui.exe`) を前提 — `Get-LauncherTemplate` の path 表記と整合確認 (writing-plans)
- 動画ドラッグの拡張子判定は case-insensitive 必須 (既存 idiom 確認)

### 開放問題 (writing-plans 持ち越し)

- `Get-LauncherTemplate` の既存 path 表記 (`%~dp0` / `%PAYLOAD%`) 確認
- 動画ドラッグの拡張子判定の既存実装確認 (case-insensitive 等)

---

## §4 #668: Portable ZIP 同梱物の起動時健全性チェック

### 背景

- 現状: 同梱物 (ffmpeg / fanfare.npz / dll 等) 欠損時は低レイヤーエラー (`ffmpeg not found` / `FileNotFoundError`) で原因切り分け困難
- 外部ユーザー受け入れ準備として「再展開してください」レベルの誤 bug report を防ぎ、初期トラブルシュート負荷を軽減
- 関連: 親 #106 / 配布形式 (PR #527 別 exe / PR #570 / #615 Portable ZIP) / ErrorModal 実装 (PR #661 を再利用)
- Portable ZIP 哲学 (展開=インストール、削除=アンインストール、ツール側はユーザー環境を変更しない) を維持

### 受け入れ条件 (元 issue 確認項目逐条)

- [ ] `allaganeye-gui.exe` 起動時に同梱バイナリ (ffmpeg / ffprobe / 必要 dll / `audio/refs/fanfare.npz` / その他必須 ref ファイル) の存在 + サイズ範囲を高速 check
- [ ] 失敗時はエラーモーダル + 「再展開してください」案内 + ログ保存 (`logs/error-YYYYMMDD.log`)
- [ ] `allaganeye.bat --version` も同等チェック、CLI exit code で識別可能 (新規 exit code 7 = 同梱物欠損)
- [ ] チェック範囲は起動時の高速 check (ファイル存在 + サイズ範囲) に限定、SHA256 等の重い検査は対象外
- [ ] `docs/system-architecture.md` §配布 に健全性チェック仕様を追記
- [ ] `docs/cli-spec.md` の exit code 表に code 7 を追記
- [ ] 健全な状態 → 起動遅延 ~50ms 以内 (元 issue 完了条件)

### 設計

#### 全体方針

build 時に同梱物 manifest を生成 → payload に同梱 → 起動時に Rust (GUI) / Python (CLI) が同 manifest を読んで check (build した実物を反映、drift 0)

#### 主要判断点と採用案

| # | 判断点 | 採用案 | 不採用候補 |
| --- | --- | --- | --- |
| 1 | manifest 管理方法 | **(a) build 時動的生成 + payload 同梱 (両言語が runtime read)** | (b) Python master / Rust mirror、(c) 個別 hard-code + CI diff |
| 2 | exit code 7 場所 | **`allaganeye/exceptions.py` 既存 enum 拡張** | 新規 module (overkill) |
| 3 | dev mode skip | **Rust: `#[cfg(not(debug_assertions))]` + Python: 環境変数 `ALLAGANEYE_INTEGRITY_SKIP=1`** | always-on (開発時 fail) |
| 4 | CLI 呼び出しタイミング | **`allaganeye --version` 時のみ** | 全サブコマンド呼出 (オーバーヘッド) |
| 5 | manifest フォーマット | **JSON: `{ "files": [{ "path", "size_min", "size_max" }] }`** | TOML、独自 text |
| 6 | size 範囲許容率 | **build 時実 size ± 5% (writing-plans で実証)** | 厳格一致 (ファイル微更新で fail) |
| 7 | UX | **`IntegrityErrorModal.tsx` (PR #661 `ErrorModal` extends、blocking)** | inline notification (致命的だから不可) |

#### 採用案 (a) 「build 時動的生成 + 両言語 runtime read」を選ぶ理由

- Portable ZIP 哲学 (build した実物を反映) と最も整合
- drift 0 (build 1 回で両言語が同じ source を読む)
- Python `json` / Rust `serde_json` (既に依存あり) で扱える
- 候補 (b) は build 工程が 2 段階 (Python 側を Rust に sync)、(c) は drift 検出 CI を追加で運用

#### manifest 配置 / 検証対象

- 配置: `<install dir>/integrity-manifest.json` (Portable ZIP payload root)
- 検証対象 (build 時に enum):
  - `ffmpeg.exe` / `ffprobe.exe` (BtbN bin/)
  - 必須 dll (avcodec / avfilter / avformat / ...)
  - `audio/refs/fanfare.npz`
  - Python embed (`python311.dll` / `python.exe` 等)
  - `allaganeye-gui.exe`
- 検証内容: ファイル存在 + size が range 内
- 速度目標: ~50ms 以内 (file system stat のみ、SHA 計算しない)

### 影響範囲

- `gui/src-tauri/src/lib.rs` (起動 hook で integrity check command を呼ぶ) — #663 と low risk 衝突
- `gui/src-tauri/src/integrity.rs` (新規、Rust 側 checker)
- `allaganeye/integrity.py` (新規、Python 側 checker)
- `allaganeye/exceptions.py` (exit code 7 追加)
- `allaganeye/cli.py` (`--version` で integrity check 呼出)
- `gui/src/components/IntegrityErrorModal.tsx` (新規、PR #661 ErrorModal extends)
- `gui/src/` 起動 hook (`App.tsx` 等で modal 表示)
- `scripts/build-portable-zip.ps1` (`integrity-manifest.json` 生成 step 追加)
- `scripts/tests/build-portable-zip.Tests.ps1` (manifest 生成 regression test)
- `docs/system-architecture.md` §配布 (仕様追記)
- `docs/cli-spec.md` (exit code 表に 7 追記)

### 実装方針

1 PR で全実装 (scope = #668 1 件、Iron Law 3 整合):

1. **build script**: `build-portable-zip.ps1` で payload 構築後に `integrity-manifest.json` を生成 (実 file の path + size を enum)
2. **Python**: `integrity.py` (manifest load + check)、`exceptions.py` exit code 7、`cli.py` `--version` フック
3. **Rust**: `integrity.rs` (manifest load + check、Python と同 JSON 仕様)、`lib.rs` 起動 hook
4. **TS**: `IntegrityErrorModal.tsx` (PR #661 ErrorModal extends)、起動時 modal 表示
5. **doc**: `system-architecture.md` / `cli-spec.md`
6. **test**: Pester / pytest / cargo test / vitest

### テスト方針

#### 自動 (CI で完結)

- `installer-pester`: `build-portable-zip.ps1` で `integrity-manifest.json` が生成され valid JSON、含むべき path 列挙
- Python pytest: `integrity.py` の単体 test (mock manifest + missing/oversized file)
- Rust cargo test: `integrity.rs` の単体 test (mock manifest)
- GUI vitest: `IntegrityErrorModal` 単体 test (#661 ErrorModal の拡張部分のみ)

#### 実機 (Idios、Iron Law 6 GUI 変更 trigger、必須)

- 同梱物 1 つ削除 → `allaganeye-gui.exe` 起動 → モーダル + log
- 同梱物 1 つ削除 → `allaganeye.bat --version` → exit code 7
- 健全 state → `allaganeye-gui.exe` 起動 → 50ms 以内 (体感確認)
- writing-plans / 実装 PR で `AskUserQuestion` により Idios に依頼

### リスク / トレードオフ

- **manifest 同梱**: build 時生成なので ZIP 改竄者が manifest も書換可。本 spec の目的 (展開後ユーザー操作で欠損検出) には十分、改竄対策は別問題
- **size 範囲 check**: SHA256 より弱いが「~50ms 以内」と「ユーザー操作起因の欠損検知」目的に整合
- **dev mode skip**: `npm run tauri dev` 環境では payload 構造が違うので integrity check が fail する → debug_assertions / 環境変数で skip。production fall-through 担保のため CI で release profile build を別途 verify
- **#663 (AppError migration) との衝突**: `lib.rs` に新規 fn 追加が中心、#663 修正対象とは別領域 → low risk

### 開放問題 (writing-plans 持ち越し)

- manifest JSON schema 詳細 (許容率 ±5% の妥当性、ffmpeg バージョン bump 時の挙動)
- `IntegrityErrorModal` の文言 / レイアウト / log フォーマット詳細
- 検証対象 file list (Python embed の必須 dll の確定列挙)
- dev mode skip の制御方法 (Rust `#[cfg]` のみ / 環境変数 `ALLAGANEYE_INTEGRITY_SKIP=1` のみ / 両方)
- CLI: `--version` 以外で integrity check を呼ぶ場面の有無 (現状方針: 呼ばない)
- production fall-through CI verification の仕組み (release profile build を CI で実走 → 同梱物 1 つ削除して exit code 7 確認)

---

## §5 章間 dependency / PR 出順 / l2-workflow Pre-flight

### PR 出順 (確定)

1. **§1 #616** (yml 単独、最も独立、merge conflict リスク最小)
2. **§2 #681** (`build-portable-zip.ps1` line 53-62、独立)
3. **§3 #617** (`build-portable-zip.ps1` `Get-LauncherTemplate`、§2 と同 file だが線が違う)
4. **§4 #668** (横断、最後で他 lane の影響吸収)

### 章間 dependency

- **§2 と §3 の `build-portable-zip.ps1` 共有**: §2 は line 53-62 (get-pip pin)、§3 は line 200+ (`Get-LauncherTemplate`)。同 file だが範囲は独立。§3 着手時に §2 PR を develop-0.2.0 に取り込み済として `git merge` で同期する Pre-flight が必須 (Iron Law 6)
- **§4 と #663 (Lane I-A) の `lib.rs` 共有**: §4 は新規 fn 追加 (起動 hook 呼出)、#663 は既存 17 command の AppError migration。修正対象が別領域で low risk
- **並行 lane**: Lane I-A / IV-b / IV-c は別 worktree、本 spec の影響なし

### Iron Law 整合 (再掲)

- **Iron Law 1**: 各 PR review で `enforce-acceptance-criteria` skill を必ず呼ぶ (受け入れ条件逐条引用)
- **Iron Law 2**: 4 PR を一括 merge / 一括 close 候補に上げる場合は `AskUserQuestion` で Idios 確認 (3 件以上の bulk operation)
- **Iron Law 3**: 1 PR = 1 issue scope。§2 #681 は 2026-05-08 rewrite で scope を get-pip.py 限定に確定 (BtbN URL aging は別 issue 起票予定 = Lane IV-a の 5 章目)
- **Iron Law 4**: 全 PR で `Closes/Fixes/Resolves` 禁止、`Refs #N` のみ
- **Iron Law 6**: PR 作成 Pre-flight (`git fetch origin develop-0.2.0` + 取り込み未済 commit 確認 + `gh pr list --search "<元issue#>" --state all` で並行 worktree PR 重複確認)

### l2-workflow Pre-flight

- 各 PR で実機検証 trigger 確認:
  - **§1 #616**: CI のみ (machine-verified)、Idios 目視 1 項目 (machine-unverifiable)
  - **§2 #681**: CI のみ (PowerShell + Pester、build-windows job)、実機不要
  - **§3 #617**: Idios 実機必須 (`.bat` ダブルクリック挙動、cmd ウィンドウ残らない、CLI-only fallback)
  - **§4 #668**: Idios 実機必須 (GUI Tauri 起動 + 同梱物欠損モーダル + CLI exit code 7)
- Self-Test Report 規約 (`docs/l2-workflow.md` §「Self-Test Report 規約」):
  - machine-verified: `[x]` checkbox
  - machine-unverifiable: plain bullet `-` (Idios 目視・実機検証項目)
- (A) PR 内修正優先 (`docs/l2-workflow.md` §「(A) PR 内修正優先 規約」): レビュー摘出問題は原則 PR 内追加修正、サイズだけで (B) 別 issue を選ばない

---

## §6 writing-plans 持ち越し事項 (まとめ)

### §1 #616

- なし (本 spec で確定)

### §2 #681

- pip version bump 判断方針 (現 `26.1.1` を継続使用 / future 任意のタイミングで手動 bump / Renovate 等の自動化、いずれも本 PR 範囲外)
- BtbN URL aging は別 issue 起票して Lane IV-a の 5 章目として扱う (本 §2 scope 外、Iron Law 3 厳守)
- **issue #681 AC は変更しない** (元 issue 本文の受け入れ条件 4 項を本 §2 で逐条充足するため、AC 編集の Idios 確認は不要)

### §3 #617

- `Get-LauncherTemplate` の既存 path 表記 (`%~dp0` / `%PAYLOAD%`) 確認
- 動画ドラッグの拡張子判定の既存実装確認 (case-insensitive 等)

### §4 #668

- manifest JSON schema 詳細 (許容率 ±5% の妥当性、ffmpeg バージョン bump 時の挙動)
- `IntegrityErrorModal` の文言 / レイアウト / log フォーマット詳細
- 検証対象 file list (Python embed の必須 dll の確定列挙)
- dev mode skip の制御方法 (Rust `#[cfg]` のみ / 環境変数 / 両方)
- CLI: `--version` 以外で integrity check を呼ぶ場面の有無
- production fall-through CI verification の仕組み (release profile build → 同梱物欠損 simulate → exit code 7)

---

## 参考 doc

- [`docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md`](../plans/2026-05-07-l2-v020-roadmap.md) — 上位 plan
- [`docs/l2-workflow.md`](../../l2-workflow.md) — PR Pre-flight / Self-Test Report / (A) PR 内修正優先 / 実機検証 trigger
- [`docs/release-process.md`](../../release-process.md) — v0.2.0 リリース判定
- [`docs/system-architecture.md`](../../system-architecture.md) — #527 別 exe 方式 / dispatch 表 / Tauri bundle 方針
- [`docs/cli-spec.md`](../../cli-spec.md) — CLI 構文 / exit code 表
- `.claude/hooks/session-start.sh` — Iron Law 5 条 + Red Flags

## 関連 issue

- 親: [#106](https://github.com/Idios/kobutachan-allaganeye/issues/106) (L2b ゼロ環境構築配布)
- §1: [#616](https://github.com/Idios/kobutachan-allaganeye/issues/616)
- §2: [#681](https://github.com/Idios/kobutachan-allaganeye/issues/681) (旧 [#649](https://github.com/Idios/kobutachan-allaganeye/issues/649) の長期対応)
- §3: [#617](https://github.com/Idios/kobutachan-allaganeye/issues/617) (前提: [#570](https://github.com/Idios/kobutachan-allaganeye/issues/570) / PR [#615](https://github.com/Idios/kobutachan-allaganeye/pull/615))
- §4: [#668](https://github.com/Idios/kobutachan-allaganeye/issues/668) (前提: PR [#661](https://github.com/Idios/kobutachan-allaganeye/pull/661) ErrorModal)
