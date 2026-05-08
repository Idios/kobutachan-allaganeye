# Lane IV-a / Group F: L2b 配布まわり 4 件 設計

> **Status**: design (brainstorming 確定、writing-plans 待ち)
> **作成**: 2026-05-08 / session `practical-wright-c6dae8`
> **対象 issue**: #616 / #681 / #617 / #668 (4 件、roadmap §3-bis Lane IV-a)
> **上位 plan**: [`docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md`](../plans/2026-05-07-l2-v020-roadmap.md)

## §0 概要

### Lane IV-a / Group F の目的

L2 (v0.2.0) リリース残作業のうち、**L2b 配布まわり** 4 件を 1 spec / 4 章 / 4 PR 独立で扱う。release blocker (#681 build-windows CI 再陳腐化) と外部ユーザー受け入れ準備 (#668 同梱物健全性チェック) を含む。

### 章順 (独立性順 = merge conflict リスク低い順)

| 章 | issue | priority | scope | 並行安全度 |
| --- | --- | --- | --- | --- |
| §1 | #616 | P3 | `.github/workflows/release.yml` 2 行修正 | high (yml 単独) |
| §2 | #681 | P2 | `scripts/build-portable-zip.ps1` 上部 hash pin (line 49-75) | high (line 範囲独立) |
| §3 | #617 | P2 | `scripts/build-portable-zip.ps1` `Get-LauncherTemplate` (line 200+) | mid (§2 と同 file) |
| §4 | #668 | P2 | Rust + Python + TS + build script + doc (横断) | mid (lib.rs touch、#663 と low risk) |

### 全体方針

- **1 spec / 4 章 / 4 PR**: roadmap §3-bis 推奨、各 PR = 1 issue scope (Iron Law 3)
- **PR 出順**: §1 → §2 → §3 → §4 (独立性順、§3 着手時は §2 を develop-0.2.0 に取り込み済の前提で `git merge` Pre-flight)
- **brainstorming 確定事項**: 各章の主要判断点 (Recommended 採用) は本 spec で確定。BtbN 等の調査依存事項は writing-plans フェーズに持ち越し
- **Lane 配置**: roadmap §3-bis Lane IV-a (wave 0)、並行 lane = Lane I-A (Group A AppError) / Lane IV-b (Group G workflow) / Lane IV-c (Group H lint+CLI)

### Iron Law 整合

- **Iron Law 1** (受け入れ条件): 各章で元 issue を逐条引用、各 PR review で `enforce-acceptance-criteria` skill を必ず呼ぶ
- **Iron Law 3** (scope): 1 PR = 1 issue。§2 #681 は roadmap 方針で受け入れ条件追記 (BtbN 統合) して扱うため、追記後の #681 が単一 scope (writing-plans 開始時に issue 本文編集を Idios 確認)
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

## §2 #681: get-pip.py 長期対応 + BtbN URL 陳腐化対策

### 背景

`scripts/build-portable-zip.ps1` の外部依存 fetch URL は 3 つ:

| 依存 | URL 形式 | 問題 |
| --- | --- | --- |
| Python embed | `python.org/ftp/python/3.11.9/...` (version pin) | 問題なし |
| **get-pip.py** | `bootstrap.pypa.io/get-pip.py` (URL 不変) | 内容のみ随時更新で固定 SHA pin が陳腐化 (#649 / PR #675 で 2 回 fix) |
| **BtbN FFmpeg** | `github.com/BtbN/FFmpeg-Builds/releases/download/<tag>/<asset>.zip` (tag pin) | URL 既に version 化済、ただし古い autobuild tag の retention 削除リスク |

#### 過去事例

- [#649](https://github.com/Idios/kobutachan-allaganeye/issues/649) (closed) — PR [#651](https://github.com/Idios/kobutachan-allaganeye/pull/651) で短期 fix (SHA pin 更新)
- PR [#675](https://github.com/Idios/kobutachan-allaganeye/pull/675) Round 2 #7 — 同 short-term fix (`106AE019...` → `66904BCC...`)
- 同パターンが v0.2.0 スコープ内で再発、未起票の長期対応が root cause

### 受け入れ条件

#### get-pip.py 部分 (元 issue #681 から)

- [ ] PyPA 側更新で `build-windows` CI が fail しない仕組みに切り替え
- [ ] 再発防止 regression test 含む (上流変更 simulate でも fail しない)
- [ ] [`scripts/build-portable-zip.ps1:54-61`](../../scripts/build-portable-zip.ps1) の comment block (PR #651 で追加された手順) を新方式に更新
- [ ] `installer-pester` CI が新方式で全 PASS

#### BtbN URL 部分 (本 spec 追記、roadmap §3-bis 方針反映)

- [ ] BtbN URL 陳腐化対策を採用 (writing-plans で確定した具体策を実装)
- [ ] BtbN tag retention で古い autobuild tag が削除された場合でも CI が build を継続できる仕組み
- [ ] 再発防止 regression test 含む (BtbN 取得失敗 simulate でも fail しない / fallback / mirror)

> **重要**: 上記 BtbN 受け入れ条件追記は GitHub issue #681 本文の編集を伴う。**writing-plans 開始時に Idios 確認 (AskUserQuestion) を取って issue 本文を更新** してから実装着手する手順を §6 に記載 (Iron Law 1 担保)。さらに具体的文言は writing-plans で確定する BtbN 採用案 (i/ii/iii/iv) に応じて再調整される (例: (i) `.sha256` sidecar のみ採用なら retention 直接対策の文言は外す、(ii) multi-tag fallback 採用なら fallback 試行回数を明記、等)。

### 設計

#### get-pip.py: versioned URL 切替 (確定)

- `$GetPipUrl` を `https://bootstrap.pypa.io/pip/<pip-version>/get-pip.py` に変更
- `$PipVersion` 変数を新設 (e.g., `'24.0'` または Python 3.11.9 bundled pip と整合する版)
- `$GetPipSha256` を versioned content の SHA に更新
- comment block (line 54-61) を「pip version bump 時の SHA 取得手順」に書き換え

#### BtbN URL: writing-plans で確定 (4 候補併記)

| 案 | 概要 | 利点 | 欠点 |
| --- | --- | --- | --- |
| (i) `.sha256` sidecar 動的検証 | BtbN 提供の `.sha256` で動的検証、固定 SHA pin 撤廃 | SHA pin 維持の運用負荷 0 | retention 直接対策にならない / 改竄保護弱化 (HTTPS+TOFU のみ) |
| (ii) multi-tag fallback chain | 新 tag → 旧 tag 順に試行 (直近 N tag) | retention 直接対策 | tag 列挙の運用 / CI 速度 ↓ |
| (iii) kobutachan 側 mirror | 自リポジトリ Releases に再ホスト | retention 完全制御 | LGPL 再配布対応 / 帯域 / メンテ負荷 |
| (iv) Renovate / dependabot で tag 自動更新 | 短期 SHA pin 更新の自動化 | 既存運用と互換 | 根本対策ではない / 単独だと不足、(i)-(iii) と併用前提 |

writing-plans フェーズで:

1. BtbN が `.sha256` sidecar を提供しているか **WebFetch で調査**
2. BtbN autobuild tag の retention 実績を調査 (現存する最古 tag の作成日)
3. (i)-(iv) を上記調査結果と合わせて評価し採用案決定 (組合せ可)

### 影響範囲

- `scripts/build-portable-zip.ps1` (line 49-62 の get-pip pin / comment、line 71-75 の BtbN pin)
- `scripts/tests/build-portable-zip.Tests.ps1` (Pester regression test 追加)
- `.github/workflows/release.yml` § build-windows (yml 修正は通常不要、CI test 追加要件次第)
- `docs/developer-setup.md` § 9 (BtbN sync 記載があれば更新)

### 実装方針

PR 1 つで 3 phase:

1. **Phase 1** (get-pip.py): `$GetPipUrl` / `$PipVersion` / `$GetPipSha256` 切替 + comment block 更新
2. **Phase 2** (BtbN): writing-plans 確定案を実装
3. **Phase 3** (test): `Invoke-WebRequest` を mock し、PyPA 内容更新 / BtbN tag 取得失敗 simulate で本 PR path が fail しないことを Pester で確認

### テスト方針

- ローカル `Invoke-Pester scripts/tests/build-portable-zip.Tests.ps1` 全 PASS
- CI `installer-pester` job 全 PASS
- 実 CI `build-windows` で `build-portable-zip.ps1` 完走
- regression test: PyPA 内容更新 / BtbN tag 取得失敗 simulate (Mock-based)
- **実機 (Idios) は不要** (PowerShell + CI で十分、GPU/audio/動画が絡まない build script のみ)

### リスク / トレードオフ

- **get-pip.py versioned URL** が PyPA で削除されるリスクは低いが 0 ではない (PyPA は通常 versioned content を不変運用)
- **PR size**: get-pip.py + BtbN を 1 PR にすると 2 つの sub-scope を含むが、roadmap で `#681` の受け入れ条件として統合する方針が確定 → Iron Law 3 違反ではない (1 PR = 1 issue scope = #681)
- **再陳腐化リスク**: pip version 自動追跡を Renovate 等で行わないと半年後に再陳腐化、ただし versioned URL では SHA pin が即陳腐化することはなく余裕あり

### 開放問題 (writing-plans 持ち越し)

- BtbN 対策の最終採用案 (i/ii/iii/iv or 組合せ)
- pip version の追跡方針 (Renovate / 手動 bump、頻度)
- BtbN `.sha256` sidecar 提供有無の調査結果反映
- BtbN autobuild tag retention 実績調査結果反映
- **issue #681 本文の受け入れ条件追記** (writing-plans 開始時に Idios 確認、AskUserQuestion)

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
2. **§2 #681** (`build-portable-zip.ps1` line 49-75、独立)
3. **§3 #617** (`build-portable-zip.ps1` `Get-LauncherTemplate`、§2 と同 file だが線が違う)
4. **§4 #668** (横断、最後で他 lane の影響吸収)

### 章間 dependency

- **§2 と §3 の `build-portable-zip.ps1` 共有**: §2 は line 49-75 (上部 hash pin)、§3 は line 200+ (`Get-LauncherTemplate`)。同 file だが範囲は独立。§3 着手時に §2 PR を develop-0.2.0 に取り込み済として `git merge` で同期する Pre-flight が必須 (Iron Law 6)
- **§4 と #663 (Lane I-A) の `lib.rs` 共有**: §4 は新規 fn 追加 (起動 hook 呼出)、#663 は既存 17 command の AppError migration。修正対象が別領域で low risk
- **並行 lane**: Lane I-A / IV-b / IV-c は別 worktree、本 spec の影響なし

### Iron Law 整合 (再掲)

- **Iron Law 1**: 各 PR review で `enforce-acceptance-criteria` skill を必ず呼ぶ (受け入れ条件逐条引用)
- **Iron Law 2**: 4 PR を一括 merge / 一括 close 候補に上げる場合は `AskUserQuestion` で Idios 確認 (3 件以上の bulk operation)
- **Iron Law 3**: 1 PR = 1 issue scope。§2 #681 は受け入れ条件追記版で BtbN を内包 → 単一 scope (issue 本文編集を writing-plans 開始時に Idios 確認)
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

- BtbN 対策の最終採用案 (i/ii/iii/iv or 組合せ)
- pip version の追跡方針 (Renovate / 手動 bump、頻度)
- BtbN `.sha256` sidecar 提供有無の WebFetch 調査
- BtbN autobuild tag retention 実績調査 (現存最古 tag の作成日)
- **issue #681 本文の受け入れ条件追記** (writing-plans 開始時に Idios `AskUserQuestion` で確認 → 採用案に応じた具体的文言で issue 本文編集 → 実装着手、Iron Law 1 担保)

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
