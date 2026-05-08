# Lane IV-a §4 / #668: Portable ZIP 同梱物 起動時健全性チェック 設計 (詳細版)

> **Status**: design (brainstorming 確定、writing-plans 直前)
> **作成**: 2026-05-08 / session `funny-tereshkova-d355c8`
> **対象 issue**: [#668](https://github.com/Idios/kobutachan-allaganeye/issues/668)
> **上位 spec**: [`docs/superpowers/specs/2026-05-08-l2b-distribution-design.md`](2026-05-08-l2b-distribution-design.md) §4 (4 章 spec の §4 詳細版)
> **上位 plan**: [`docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md`](../plans/2026-05-07-l2-v020-roadmap.md) Lane IV-a wave 0 / Group F

## §0 概要

### 目的

Portable ZIP 配布版で、展開後にユーザー操作で同梱バイナリ (ffmpeg / ffprobe / 必要 dll / `audio/refs/fanfare.npz` / 他必須 ref ファイル) が欠落・破損するケースに対し、**起動時に整合性を check してわかりやすいエラーを表示** する仕組みを導入する。

### 期待効果

- 外部ユーザーの初期トラブルシュート負荷低減
- bug report 受付時に「再展開してください」レベルの誤報告を抑制
- 正しい再現環境かどうかを issue 受付前に切り分け

### Portable ZIP 哲学整合

- 展開 = インストール、削除 = アンインストール
- ツール側はユーザー環境を変更しない (レジストリ / homedir に書込まない)
- 検証失敗時の log は **`<install dir>/logs/`** (Portable ZIP 内) に書く

### スコープ境界

- 対象: ファイル存在 + size 範囲 check (起動時の高速 check、~50ms 以内)
- 対象外: SHA256 等の重い検査 / 改竄者対策 / smartScreen 連携 (#462 系)

## §1 受け入れ条件 (元 issue [#668](https://github.com/Idios/kobutachan-allaganeye/issues/668) 逐条)

各項目に PR Self-Test Report で `[x]` (machine-verified) または `-` bullet (Idios 実機) で対応する:

- [ ] `allaganeye-gui.exe` 起動時に同梱バイナリ (ffmpeg / ffprobe / 必要 dll / `audio/refs/fanfare.npz` / 他必須 ref ファイル) の存在 + サイズ範囲を高速 check (Idios 実機)
- [ ] 失敗時はエラーモーダル + 「再展開してください」案内 + ログ保存 (`logs/error-YYYYMMDD.log` への記録) (Idios 実機 + vitest)
- [ ] `allaganeye.bat --version` も同等チェックを行い CLI exit code で識別可能 (新規 exit code 7 = 同梱物欠損) (build-windows job E2E)
- [ ] チェック範囲は起動時の高速 check (ファイル存在 + サイズ範囲) に限定し、SHA256 等の重い検査は対象外 (実装方針)
- [ ] `docs/system-architecture.md` §配布 に健全性チェック仕様を追記 (PR diff)
- [ ] `docs/cli-spec.md` の exit code 表に新規 code を追記 (PR diff)
- [ ] 健全状態で起動遅延 ~50ms 以内 (Idios 実機体感確認)

## §2 アーキテクチャ概要

build 時に `scripts/build-portable-zip.ps1` が payload 構築完了後に **`integrity-manifest.json`** を生成し、payload root に同梱する。起動時に **GUI (Rust release build)** が `lib.rs` setup hook から `integrity::check()` を呼び、**CLI (`--version` callback)** が `integrity.check()` を呼ぶ。両者が同じ JSON を読んで file 存在 + size 範囲 check を行い、fail 時は GUI = blocking modal + log + exit / CLI = exit code 7 + log。

build 時に実 file から manifest を生成するため drift 0、両言語が同じ source を読む単一真値方式。

## §3 Manifest schema

```json
{
  "version": 1,
  "generated_at": "2026-05-08T12:34:56Z",
  "files": [
    { "path": "ffmpeg/ffmpeg.exe",                       "size": 12345678, "tolerance_bytes": 0 },
    { "path": "ffmpeg/ffprobe.exe",                      "size": 1234567,  "tolerance_bytes": 0 },
    { "path": "lib/allaganeye/audio/refs/fanfare.npz",   "size": 12345,    "tolerance_bytes": 0 },
    { "path": "python/python.exe",                       "size": 100000,   "tolerance_bytes": 0 },
    { "path": "python/python311.dll",                    "size": 5000000,  "tolerance_bytes": 0 },
    { "path": "allaganeye-gui.exe",                      "size": 5678901,  "tolerance_bytes": 0 }
  ]
}
```

> **Payload 構造**: build script (`scripts/build-portable-zip.ps1`) は以下を生成:
> - `python/` … Python 3.11 embeddable (python.exe / python311.dll / 標準 dll)
> - `lib/allaganeye/...` … `pip install --target lib` で site-packages を置く (allaganeye パッケージ + ref ファイル含む)
> - `ffmpeg/` … `ffmpeg.exe` / `ffprobe.exe` / dll / `LICENSE.txt` (bin/ サブディレクトリ無し、build script が直接コピー)
> - `allaganeye-gui.exe` … Tauri release build 結果
> - `allaganeye.bat` … 起動 launcher
> - `README.txt` … 説明書
> - `integrity-manifest.json` (本 spec で新設)

### フィールド規約

| field | 型 | 意味 |
| --- | --- | --- |
| `version` | int | schema version (現状 1)。将来非互換変更時にインクリメント |
| `generated_at` | string (ISO8601 UTC) | manifest 生成時刻 (デバッグ用) |
| `files` | array | 検証対象 file 配列 |
| `files[].path` | string | install dir からの相対 path (POSIX 区切り `/`) |
| `files[].size` | int | build 時実 size (bytes) |
| `files[].tolerance_bytes` | int (default 0) | 許容バイト数。`0` = 厳格一致 |

### 検証ロジック

```
for entry in manifest.files:
    actual = stat(install_dir / entry.path)
    if not actual.exists:
        record "missing"
    elif abs(actual.size - entry.size) > entry.tolerance_bytes:
        record "size_mismatch" with expected/actual
fail if any "missing" or "size_mismatch"
```

### tolerance_bytes 既定方針

- **default 0 (厳格一致)**: ffmpeg / Python embed / Tauri release build 等の binary は build 時固定 size、drift しない
- **個別 buffer 上書き**: 将来 fanfare.npz の numpy 形式 bump 等が起きた際の例外対応。現状は全 file `0` で開始
- **±5% 一律案は採用せず**: 全 file 一律 buffer は size 検証の意味を希薄化させるため

## §4 Component 一覧

| 種別 | path | 役割 |
| --- | --- | --- |
| build | `scripts/build-portable-zip.ps1` | payload 構築完了後に `integrity-manifest.json` 生成 step 追加 |
| build test | `scripts/tests/build-portable-zip.Tests.ps1` | manifest 生成 logic の Pester regression test |
| Python | `allaganeye/exceptions.py` | `IntegrityError(exit_code=7)` 追加 |
| Python | `allaganeye/integrity.py` (新規) | manifest load + 検証、env `ALLAGANEYE_INTEGRITY_SKIP=1` で skip |
| Python | `allaganeye/cli.py` | `version_callback` で `integrity.check()` 呼出 |
| Python test | `tests/test_integrity.py` (新規) | unit test (mock manifest + missing/oversized + env_skip) |
| Rust | `gui/src-tauri/src/integrity.rs` (新規) | manifest load + 検証 (serde_json)、`#[cfg(not(debug_assertions))]` 配下 |
| Rust | `gui/src-tauri/src/lib.rs` | 起動 hook で `integrity::check()`、fail 時 frontend に payload 送出 |
| TS | `gui/src/state/errorStore.ts` (修正) | `ErrorCategory` enum に `'integrity'` 追加 |
| TS | `gui/src/components/ErrorModal.tsx` (修正) | `errorCategory === 'integrity'` 時の表示分岐 (失敗 file 一覧 + 「再展開してください」案内) |
| TS | `gui/src/components/ErrorModal.test.tsx` (修正) | integrity category 用 vitest 追加 |
| TS | `gui/src/App.tsx` 等 (修正) | Tauri `integrity-error` event 受信 → `useErrorStore.showError({errorCategory:'integrity', isPanic:true, isRecoverable:false, logDir:...})` |
| doc | `docs/system-architecture.md` | §配布 に integrity 仕様追記 |
| doc | `docs/cli-spec.md` | exit code 表に `7` 追記 |
| CI | `.github/workflows/release.yml` | `build-windows` job に E2E step 追加 (zip 解凍 → file 削除 → CLI exit 7 assert) |

## §5 Data flow

```
┌─────────────────────────────────────────────────────────────────┐
│ build (CI / local)                                              │
│   build-portable-zip.ps1                                        │
│   ├─ payload 構築 (ffmpeg / Python embed / fanfare.npz / .exe)  │
│   └─ integrity-manifest.json 生成 (実 file の path + size を enum)│
└────────────────────────┬────────────────────────────────────────┘
                         │ ZIP に同梱
                         ▼
                    ZIP 配布
                         │ 展開 = インストール
                         ▼
                  user が起動
                         │
       ┌─────────────────┴─────────────────┐
       │                                    │
GUI (allaganeye-gui.exe)         CLI (allaganeye.bat --version)
release build                              │
       │                                    │
integrity::check()                  integrity.check()
(Rust serde_json)                   (Python json)
       │                                    │
   ┌───┴────┐                          ┌────┴────┐
success    fail                     success    fail
   │        │                          │         │
   │     Tauri event                   │      raise IntegrityError
   │     (payload: missing /           │       │
   │      size_mismatch)               │       ▼
   │        │                          │   stderr 短メッセージ
   ▼        ▼                          ▼   + log 書込 + exit 7
続行    IntegrityErrorModal           続行
            │
        ログ書込 + 閉じる時 exit
```

## §6 Error handling

### GUI 路

- **既存 `ErrorModal` を拡張** (DRY、PR #661 の useErrorStore + a11y / focus trap / Escape 処理を全 reuse)
- `ErrorCategory` enum (`gui/src/state/errorStore.ts`) に `'integrity'` 追加
- Rust `integrity::check()` 失敗 → Tauri event `integrity-error` を emit (payload: `{ missing: string[], size_mismatch: {path,expected,actual}[], log_path: string }`)
- frontend が event 受信 → `useErrorStore.showError({ errorCategory: 'integrity', errorTitle: '同梱物の検証に失敗しました', errorMessage: '<失敗 file 一覧>', errorHint: 'Portable ZIP を再展開してください。', isPanic: true, isRecoverable: false })` + `setLogDir('<install dir>/logs')`
- `ErrorModal` の表示: `isPanic: true` で **「アプリを終了」** ボタンが表示 (= `force_exit_app` Tauri command で exit)、`isRecoverable: false` で **「閉じる」** ボタンは非表示、`logDir` 設定で **「ログフォルダを開く」** ボタンが表示 (= `open_folder_in_explorer`)
- `errorCategory === 'integrity'` 時の専用挙動: errorMessage に missing / size_mismatch を区分整形した本文、errorHint に再展開案内
- 検証失敗状態でアプリ動作を許容しない (override option なし、blocking only)

### CLI 路

- `IntegrityError(exit_code=7)` raise → CLI 標準処理経路で stderr に短メッセージ + log 書込 + `sys.exit(7)`
- 短メッセージ例: `integrity check failed: 2 file(s) missing or size mismatch — see logs/error-YYYYMMDD.log`
- verbose mode (`-v`) では context dict (missing list / size_mismatch list) も stderr に出力

### Log

- path: `<install dir>/logs/error-YYYYMMDD.log` (Portable ZIP 内)
- format: plain text、append 形式
- record 例 (1 起動につき 1 行 append):
  ```
  2026-05-08T12:34:56Z [error] integrity check failed: missing=["audio/refs/fanfare.npz"]; size_mismatch=[]
  2026-05-08T12:35:42Z [error] integrity check failed: missing=[]; size_mismatch=[{"path":"ffmpeg/bin/ffmpeg.exe","expected":12345678,"actual":0}]
  2026-05-08T12:36:18Z [error] integrity check failed: missing=["audio/refs/fanfare.npz","ffmpeg/bin/ffmpeg.exe"]; size_mismatch=[{"path":"ffmpeg/bin/ffprobe.exe","expected":1234567,"actual":1000000}]
  ```
- record format: `{ISO8601 UTC} [error] integrity check failed: missing=<JSON array of paths>; size_mismatch=<JSON array of {path,expected,actual}>` (両 list は空でも `[]` 表記、JSON parse 可能な体)
- write 不可 (read-only install dir) 時の fallback は writing-plans で詳細化 (現状方針: log 書込失敗は silent でも modal/exit code は出す)

## §7 Dev mode skip 制御

| 言語 | 制御方法 | 理由 |
| --- | --- | --- |
| Rust | `#[cfg(not(debug_assertions))]` のみ。env 無視 | `cargo build` (debug) は常に skip、`cargo build --release` (production) は常に check。env 漏れによる release skip リスクを根絶 |
| Python | env `ALLAGANEYE_INTEGRITY_SKIP=1` で skip (default check) | pytest や開発時の CLI 実行で integrity check が邪魔になる場面がある (開発機の ffmpeg path が payload と異なる等) |

CI では **release profile build を CI 内で実走** することで Rust の fall-through を verify する (§9 参照)。

## §8 CLI 呼出方針

- **`--version` (`-V`) callback でのみ** integrity check を呼ぶ (元 spec §4 採用案維持)
- 全 command 開始前 check は採用せず: 軽量 command (`--help` 等) の遅延を避ける、CLI 開発時の env_skip 必要場面を限定
- 専用 subcommand `check-integrity` は新設しない: `--version` に統合することで surface area を最小化、bug report ガイドで「`allaganeye --version` で確認 → exit code 7 なら同梱物欠損」と統一案内可能

## §9 Testing

### Unit (CI で完結)

| level | tool | scope |
| --- | --- | --- |
| Pester | `scripts/tests/build-portable-zip.Tests.ps1` | manifest 生成 step が `integrity-manifest.json` を出力 + valid JSON + 必須 path 列挙 |
| pytest | `tests/test_integrity.py` | manifest load / missing detect / oversized detect / under-tolerance pass / env `ALLAGANEYE_INTEGRITY_SKIP=1` で no-op |
| cargo test | `gui/src-tauri/src/integrity.rs` | manifest load / missing detect / oversized detect / under-tolerance pass |
| vitest | `gui/src/components/IntegrityErrorModal.test.tsx` | render / props 反映 / 3 button click handler / accessibility (focus trap, Escape, label) |

### E2E (build-windows job、CI 自動)

`build-windows` job 内で zip 作成後に **新規 step** を追加。下記は概念例 (実際の path / artifact 名 / pwsh syntax は writing-plans で確定):

```yaml
- name: integrity-check fall-through (release build)
  shell: pwsh
  run: |
    # 概念例。実際の zip 名 / 解凍先 / Start-Process 呼出方は
    # writing-plans / 実装段階で確定する (PR #686 の artifact 名規則
    # 反映 / pwsh native command 罠回避テンプレ適用)
    # build-windows job では既に build/portable/allaganeye-v$version/ に
    # payload が展開されている (-SkipArchive 経由)。新たに verify-copy を作って
    # そこから 1 file 削除 → CLI 起動 → exit 7 を assert する流れ:
    Copy-Item -Recurse "build/portable/allaganeye-v$version" "verify/" -Force
    Remove-Item "verify/lib/allaganeye/audio/refs/fanfare.npz" -Force
    Push-Location verify
    try {
      $output = '' | & cmd.exe /c "allaganeye.bat --version 2>&1"
      $code = $LASTEXITCODE
      $LASTEXITCODE = 0  # release.yml 既存 idiom: native 戻り値を step 末尾の auto-exit に伝播させない
      if ($code -ne 7) { throw "integrity check did not produce exit code 7 (got $code)`n$output" }
    } finally {
      Pop-Location
    }
```

これで:
1. Rust release build (`cargo build --release` 経由 Tauri build) で `#[cfg(not(debug_assertions))]` が有効化
2. 同梱物 1 つ削除 → CLI `allaganeye.bat --version` 実走 → exit code 7 verify
3. release profile fall-through が CI で常時保証

GUI 側 (Tauri 起動 + modal 表示) は CI 自動化困難なため Idios 実機検証で覆う。

### Idios 実機検証 (Iron Law 6 trigger 必須)

`AskUserQuestion` で実装 PR 時に依頼する 3 シナリオ:

1. 同梱物 1 つ削除 → `allaganeye-gui.exe` 起動 → `IntegrityErrorModal` 表示 + 3 button 動作 + log 書込確認
2. 同梱物 1 つ削除 → `allaganeye.bat --version` → exit code 7 + stderr 短メッセージ + log 書込確認
3. 健全状態 → `allaganeye-gui.exe` 起動 → 起動遅延 ~50ms 以内 (体感)

## §10 Iron Law 整合 / Pre-flight

### Iron Law

- **Iron Law 1** (受け入れ条件): §1 の 7 項目を PR Self-Test Report で逐条 verify、`enforce-acceptance-criteria` skill を `/review-pr` で必ず呼ぶ
- **Iron Law 3** (scope): 1 PR = #668 のみ。他 issue を同 PR で処理しない
- **Iron Law 4** (close keyword): PR / commit `Refs #668` のみ、`Closes / Fixes / Resolves` 禁止。マージ後 `/close-issue` で実測再検証
- **Iron Law 6** (Pre-flight): PR 作成前に下記を実施

### PR 作成 Pre-flight (`docs/l2-workflow.md` §「PR 作成 Pre-flight」)

```
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline
# 取り込み未済 commit が touched files (lib.rs / cli.py / build-portable-zip.ps1 等) と交差すれば
git merge origin/develop-0.2.0
# 自動チェック再実行

gh pr list --search "668" --state all
# 並行 worktree PR 重複確認
```

### Path 別自動チェック (`docs/l2-workflow.md` §「PR 作成 path 別自動チェック」)

本 PR は **CLI Python + GUI TS + Rust + build script + docs** に touched するため:

```bash
# Python
ruff check .
ruff format --check .
pyright
pytest

# GUI (TS / Rust / build)
cd gui && npm run lint && npm run typecheck && npm test && npm run build
cd gui/src-tauri && cargo check
# Pester (Windows)
Invoke-Pester scripts/tests/build-portable-zip.Tests.ps1
```

### Self-Test Report 規約

- machine-verified: `[x]` checkbox (CI で確認可能なもの: ruff / pyright / pytest / cargo check / vitest / Pester / build-windows job E2E)
- machine-unverifiable: plain bullet `-` (Idios 実機検証 3 シナリオ)

## §11 Writing-plans 持ち越し事項

writing-plans skill で plan 内に直接記述する未確定項目 (本 spec 段階では持ち越し、plan 内で確定):

1. **検証対象 file list の確定 enum**
   - 採用方針: `build-portable-zip.ps1` が payload 構築完了時点で `Get-ChildItem -Recurse` で payload 全 file を列挙し、各 path / size を manifest に書く (固定 list ではなく自動 enum)
   - 必ず含むもの: `python/python.exe` / `python/python311.dll` / `ffmpeg/ffmpeg.exe` / `ffmpeg/ffprobe.exe` / `lib/allaganeye/__init__.py` / `lib/allaganeye/audio/refs/fanfare.npz` / `allaganeye-gui.exe` (存在時) / `allaganeye.bat`
   - 自動 enum で全 dll / 全 .py を含めるため build/run 一致が保証される

2. **`integrity-manifest.json` 生成 step の `build-portable-zip.ps1` 内位置**
   - 確定: `# 7. README` の後 + `# 8. Compress` の前 (payload 構築完了後、ZIP 圧縮前)
   - 自動 enum では `Get-ChildItem -Path $PayloadDir -Recurse -File` で全 file 取得 → relative path + size を manifest 化

3. **ffmpeg バージョン bump 時の挙動**
   - 確定: BtbN tag 変更 → CI 再走 → 自動 enum manifest 再生成 → drift 0
   - 開発 local build では Python `--version` が新 ffmpeg を見て一時的に fail する可能性 → `ALLAGANEYE_INTEGRITY_SKIP=1` で回避可能

4. **GUI Modal extension** (writing-plans で確定済、§6 GUI 路 参照)
   - 既存 `ErrorModal` 拡張、`ErrorCategory` に `'integrity'` 追加、`isPanic: true` + `isRecoverable: false` で動作

5. **Log 書込失敗時の fallback**
   - 採用方針: silent fail (modal/exit code は出す、log 書込失敗を理由に新たな modal を出さない)
   - 理由: log は補助情報、modal/exit code が一次 channel

6. **Tauri event payload schema** (writing-plans で確定済、§6 GUI 路 参照)
   - event 名: `integrity-error`
   - payload: `{ missing: string[], size_mismatch: {path: string, expected: number, actual: number}[], log_path: string }`

## §12 影響範囲

### 修正対象 file

```
allaganeye/exceptions.py        (修正、+ IntegrityError class、exit_code = 7)
allaganeye/integrity.py         (新規、manifest load + check + skip 判定)
allaganeye/cli.py               (修正、version_callback 内で integrity 呼出)
tests/test_integrity.py         (新規、unit tests)

gui/src-tauri/src/integrity.rs  (新規、manifest load + check)
gui/src-tauri/src/lib.rs        (修正、setup hook で integrity::check() + integrity-error event emit)
gui/src/state/errorStore.ts     (修正、ErrorCategory に 'integrity' 追加)
gui/src/components/ErrorModal.tsx        (修正、'integrity' category 用 表示分岐)
gui/src/components/ErrorModal.test.tsx   (修正、'integrity' category テスト追加)
gui/src/App.tsx 等              (修正、'integrity-error' Tauri event listener 追加)

scripts/build-portable-zip.ps1  (修正、# 7 と # 8 の間で manifest 生成 step 追加)
scripts/tests/build-portable-zip.Tests.ps1 (修正、manifest 生成 logic Pester test 追加)

.github/workflows/release.yml   (修正、build-windows job に integrity E2E step 追加)

docs/system-architecture.md     (修正、§配布 追記)
docs/cli-spec.md                (修正、exit code 表に 7 追記)
```

### 並行 lane との衝突

- **#663 (Lane I-A AppError migration、merged fc9fbdb)** との `lib.rs` 共有: 既に main にマージ済、本 PR は新規 fn 追加 + 起動 hook 拡張なので衝突 low
- **Lane IV-a §1 #616 (release.yml)** との衝突: §1 の修正は yml line 212 / 231 (artifact name)、本 PR は build-windows job 内 step 追加 → 衝突 low、§1 PR 取り込み後に `git merge` で base 同期 (Iron Law 6 Pre-flight)
- **Lane IV-a §2 #681 (build-portable-zip.ps1 line 49-75)** / **§3 #617 (`Get-LauncherTemplate`)**: 本 PR は build script 末尾近辺に manifest 生成 step 追加なので line 範囲別、衝突 low、ただし §2/§3 PR が先に merged なら base 同期必須

## §13 リスク / トレードオフ

| 項目 | リスク | mitigation |
| --- | --- | --- |
| manifest も改竄可能 | ZIP 改竄者は manifest も書換可 | 本 spec の目的 (展開後ユーザー操作起因の欠損検知) には十分。改竄対策は別 scope (将来の SmartScreen 対応 / コード署名等で扱う) |
| size 範囲 check の検出力 | SHA256 より弱い | 「~50ms 以内」と「ユーザー操作起因の欠損検知」目的に整合、SHA は意図的に対象外 (元 issue) |
| dev mode skip の Rust cfg 限定 | release で env による一時 skip 不可 | CI で release profile build を実走して fall-through を verify、debug は `cargo build` 経由で skip 可能 |
| log 書込失敗 (read-only install dir) | log が残らない bug report 困難化 | writing-plans で fallback (silent / stderr) を決定 |
| `ErrorModal` 拡張方針 | 既存 component の `ErrorCategory` enum 追加 + `errorCategory === 'integrity'` 分岐で対応。新 file 不要、a11y / focus trap / Escape 処理を全 reuse | writing-plans で確定済 (§6 GUI 路) |
| Tauri startup hook の error 経路 | hook 失敗が deadlock するリスク | Rust `integrity::check()` は I/O のみ (file stat + JSON parse)、panic 化させない設計 (Result return) |

## §14 参考 doc / 関連 issue

### 参考 doc

- [`docs/superpowers/specs/2026-05-08-l2b-distribution-design.md`](2026-05-08-l2b-distribution-design.md) §4 — 上位 spec (4 章 brainstorming 確定版)
- [`docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md`](../plans/2026-05-07-l2-v020-roadmap.md) — L2 v0.2.0 roadmap、Lane IV-a 配置
- [`docs/l2-workflow.md`](../../l2-workflow.md) — PR Pre-flight / Self-Test Report / 実機検証 trigger
- [`docs/system-architecture.md`](../../system-architecture.md) — #527 別 exe 方式 / 配布 dispatch
- [`docs/cli-spec.md`](../../cli-spec.md) — CLI 構文 / exit code 表
- `.claude/hooks/session-start.sh` — Iron Law 5 条 + Red Flags

### 関連 issue / PR

- 親: [#106](https://github.com/Idios/kobutachan-allaganeye/issues/106) (L2b ゼロ環境構築配布)
- 配布形式: PR [#527](https://github.com/Idios/kobutachan-allaganeye/pull/527) (別 exe 方式) / PR [#570](https://github.com/Idios/kobutachan-allaganeye/pull/570) / [#615](https://github.com/Idios/kobutachan-allaganeye/pull/615) (Portable ZIP)
- 前提: PR [#661](https://github.com/Idios/kobutachan-allaganeye/pull/661) (`ErrorModal` 実装)
- Lane I-A: [#663](https://github.com/Idios/kobutachan-allaganeye/issues/663) (AppError migration、merged fc9fbdb)
- Lane IV-a §1-§3: [#616](https://github.com/Idios/kobutachan-allaganeye/issues/616) / [#681](https://github.com/Idios/kobutachan-allaganeye/issues/681) / [#617](https://github.com/Idios/kobutachan-allaganeye/issues/617)
- 別系統 (本 spec 範囲外): [#462](https://github.com/Idios/kobutachan-allaganeye/issues/462) (closed、SmartScreen 対策)
