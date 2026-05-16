# L2 Lane VII: Group M gui spawn 統一 (#727) 設計

> **Status**: v0.2.0 リリースゲート Lane VII (Group M) — Wave 1 initial parallel batch
> **Scope**: [#727](https://github.com/Idios/kobutachan-allaganeye/issues/727) (1 spec / 1 章 / single PR)
> **Roadmap**: [docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md](../plans/2026-05-13-l2-v020-roadmap-update.md) Group M
> **依存元 PR**: [PR #720](https://github.com/Idios/kobutachan-allaganeye/pull/720) (#679 fix、`process_util.rs` + `apply_no_window` ヘルパ導入の前提)
> **session**: `fervent-brahmagupta-3f4c94` (2026-05-13 brainstorming、Idios + Claude Opus 4.7)

## §0 関連 issue / PR の状態整理

| 参照先 | 状態 | 本 spec への関与 |
| --- | --- | --- |
| [#727](https://github.com/Idios/kobutachan-allaganeye/issues/727) | OPEN (P3-low, refactor) | **本 spec で対応** — `open_folder_in_explorer` を `tokio::process::Command` に統一 |
| [#679](https://github.com/Idios/kobutachan-allaganeye/issues/679) | CLOSED (PR #720 で完了) | `apply_no_window` helper の前提として既存。本 spec は `open_folder_in_explorer` への適用は **行わない** (purpose alignment 理由、§3.3) |
| [#545](https://github.com/Idios/kobutachan-allaganeye/pull/545) | MERGED | `tauri-plugin-shell::open` → `std::process::Command::new("explorer.exe")` への切替経緯 (2026-04-25)。本 spec は std → tokio へさらに切り替え |
| [#523](https://github.com/Idios/kobutachan-allaganeye/issues/523) | CLOSED | CloseRequested flow + PROCESS_TRACKER の元実装。本 spec は `open_folder_in_explorer` で **PROCESS_TRACKER 非登録** 方針を維持 (§3.4) |
| [#663](https://github.com/Idios/kobutachan-allaganeye/issues/663) | CLOSED (Lane I-A) | AppError migration 完遂。本 spec は spawn 失敗の AppError 経路 (`subprocess.spawn_failed` + `.with_default_hint()`) を **そのまま継承** |
| [#645](https://github.com/Idios/kobutachan-allaganeye/issues/645) | CLOSED | `extract_brightness_window_impl` 追加で `process_util.rs` adoption test が 5 site に拡張された経緯。本 spec は 5 site のままで安定 |

### 派生候補 (本 spec scope 外、§3 / §5.7)

- 5 spawn site (`probe_video_with` / `ensure_thumbnail_exists` / `run_ffmpeg_export_attempt` / `start_detect` / `extract_brightness_window_impl`) の `tauri-plugin-shell::Command` 移行 = issue #727 (2)、post-v0.2.0 別 issue
- Windows process group orphan 挙動の精査 = issue #727 (3)、別 issue (audit task)

## §1 Background

### 1.1 #727 — gui spawn 統一 (P3-low, refactor)

[PR #720](https://github.com/Idios/kobutachan-allaganeye/pull/720) (#679 fix = production build CMD 窓抑止) の spec [docs/superpowers/specs/2026-05-11-l2-lane-ib-group-b-design.md](2026-05-11-l2-lane-ib-group-b-design.md) §5.5 で「派生 issue 候補」として挙げられた 3 項目の umbrella issue:

1. `open_folder_in_explorer` が `std::process::Command` のままで tokio 不統一
2. 5 spawn site が `tokio::process::Command` 直接使用 — Tauri 2 推奨 `tauri-plugin-shell::Command` 未適用
3. 子プロセスの Windows process group orphan 挙動未検証

本 spec は **(1) のみ scope** で扱う。理由:

- issue 本文の優先度 (2) > (1) > (3) は **Tauri 2 戦略的価値** の観点だが、(2) は `process_util.rs` の `apply_no_window` ヘルパ (`tokio::process::Command` 前提) / `PROCESS_TRACKER` (`tokio::process::Child` 前提) を全面再設計する必要があり、scope 拡大が大きい。1 spec / 1 章 / 並行安全度 high の roadmap 前提と矛盾
- roadmap [docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md](../plans/2026-05-13-l2-v020-roadmap-update.md) §3 Group M は「lib.rs 5 spawn site を `tokio::process::Command` 系で統一」と明記、現状の 5 site は既に tokio 化済 → 残る 1 spawn site (`open_folder_in_explorer`) の tokio 化で「統一」完成
- (2) は v0.2.0 release gate 後の post-v0.2.0 別 issue として扱う (§5.7 で記録)
- (3) は単発の audit で済むため別 issue (audit task) で扱い、必要なら fix issue 起票

brainstorming session (2026-05-13 `fervent-brahmagupta-3f4c94`、Idios + Claude Opus 4.7) で確認済:

- Q1 (scope): (1) tokio 統一のみ
- Q2 (`apply_no_window`): (A) 適用しない + purpose コメント
- Q3 (UAT 範囲): (α) dev + release 両方 + #679 regression 対照
- Q4 (approach): A. Direct minimal swap

### 1.2 現状コード ([gui/src-tauri/src/lib.rs:1842-1862](../../gui/src-tauri/src/lib.rs#L1842))

```rust
#[tauri::command]
fn open_folder_in_explorer(path: String) -> Result<(), AppError> {
    validate_open_folder_request(&path)?;

    #[cfg(target_os = "windows")]
    {
        use std::process::Command;
        Command::new("explorer.exe")
            .arg(&path)
            .spawn()
            .map_err(|e| {
                AppError::new(
                    "subprocess.spawn_failed",
                    format!("failed to launch explorer: {}", e),
                )
                .with_default_hint()
            })?;
    }

    Ok(())
}
```

- `std::process::Command` 使用 (sync API)
- `fn` (sync function、`#[tauri::command]` で frontend からは Promise 返却)
- Child は drop (Windows は zombie process model なし → 後始末は OS 任せで OK)
- AppError は `with_default_hint()` 経由で適切 (#663 Lane I-A 完了済)

### 1.3 他 5 spawn site の現状

| 関数 (fn def line) | spawn 行 | spawn 対象 | 現状 API | `apply_no_window` 適用 |
| --- | --- | --- | --- | --- |
| `probe_video_with` ([lib.rs:~638](../../gui/src-tauri/src/lib.rs#L638)) | [lib.rs:~652](../../gui/src-tauri/src/lib.rs#L652) | ffprobe | `tokio::process::Command` | ✓ |
| `ensure_thumbnail_exists` ([lib.rs:~1236](../../gui/src-tauri/src/lib.rs#L1236)) | [lib.rs:~1259](../../gui/src-tauri/src/lib.rs#L1259) | ffmpeg (thumbnail) | `tokio::process::Command` | ✓ |
| `extract_brightness_window_impl` ([lib.rs:~1348](../../gui/src-tauri/src/lib.rs#L1348)、#645 で追加) | [lib.rs:~1365](../../gui/src-tauri/src/lib.rs#L1365) | ffmpeg (brightness window) | `tokio::process::Command` | ✓ |
| `run_ffmpeg_export_attempt` ([lib.rs:~1997](../../gui/src-tauri/src/lib.rs#L1997)) | [lib.rs:~2004](../../gui/src-tauri/src/lib.rs#L2004) | ffmpeg (export) | `tokio::process::Command` | ✓ |
| `start_detect` ([lib.rs:~2629](../../gui/src-tauri/src/lib.rs#L2629)) | [lib.rs:~2659](../../gui/src-tauri/src/lib.rs#L2659) | allaganeye CLI (Python) | `tokio::process::Command` | ✓ |
| `open_folder_in_explorer` ([lib.rs:~1843](../../gui/src-tauri/src/lib.rs#L1843)) | (fn 内 1 行、`std::process::Command::new("explorer.exe")`) | explorer.exe | **`std::process::Command`** ← 本 spec で tokio 化 | **非適用** (本 spec で維持、§3.3) |

5/6 は tokio 化済、残り 1 (`open_folder_in_explorer`) のみ std。line 番号は 2026-05-13 時点の develop-0.2.0 (HEAD `9ce2565`) スナップショット、`~` prefix は将来の drift を許容するヘッジ。

### 1.4 frontend 呼び出し元

`invoke('open_folder_in_explorer', { path: <dir> })`:

- [gui/src/components/ErrorModal.tsx:139](../../gui/src/components/ErrorModal.tsx#L139) — ErrorModal の「ログフォルダを開く」
- [gui/src/screens/ExportScreen.tsx:424](../../gui/src/screens/ExportScreen.tsx#L424) 周辺 — ExportScreen 完了画面の「フォルダを開く」

`invoke` は impl 側が sync でも async でも Promise 返却で挙動同一 → frontend 側コード / `ExportScreen.test.tsx` の mock いずれも変更不要。

## §2 Goals

1. `open_folder_in_explorer` を `std::process::Command` から `tokio::process::Command` に切り替え、`gui/src-tauri/src/lib.rs` 内 **6 spawn site すべてを `tokio::process::Command` 系で統一** (gui spawn 統一の完成)
2. `fn` → `async fn` 化で他 5 spawn site (全て `async fn`) と convention 統一
3. doc comment に **#727 切替経緯** / **`apply_no_window` 非適用 (purpose alignment)** / **PROCESS_TRACKER 非登録 (UI 維持)** の 3 段落を追記し、将来の reader が意図を理解できるようにする
4. Iron Law 6 実機検証 (Idios) で dev / release 両方の explorer 起動を確認し、**#679 fix の regression が出ていない** ことを担保

## §3 Non-goals (scope 外明記)

### 3.1 (2) 5 spawn site の `tauri-plugin-shell::Command` 移行

- Tauri 2 公式 API 移行の戦略的価値はあるが、`process_util::apply_no_window` (`tokio::process::Command` 前提) / `PROCESS_TRACKER` (`tokio::process::Child` 前提) を全面再設計する必要があり scope 拡大が大きい
- 本 spec 後に **派生 issue (post-v0.2.0)** で扱う (§5.7)
- `shell:allow-open` scope を path 許可に拡張する設計検討も別 issue (#545 review で `tauri-plugin-shell::open` 経路は path reject されることが確認済)

### 3.2 (3) Windows process group orphan 挙動精査

- 親 Tauri app より子プロセスが長生きしたケース / 親 kill 時の子プロセスの挙動を audit する作業
- 単発の検証で済むため、本 spec 後に **派生 issue (audit task)** で扱い、必要なら CREATE_NEW_PROCESS_GROUP / job object 化等の fix を別 issue 起票 (§5.7)

### 3.3 `apply_no_window` の `open_folder_in_explorer` 適用

- `explorer.exe` は Win32 GUI subsystem、console window をそもそも生成しないため `apply_no_window` の purpose (`windows_subsystem = "windows"` 親で release 時の console 割当抑止 #679) と alignment が成立しない
- [`process_util.rs`](../../gui/src-tauri/src/process_util.rs) adoption test (`lib_rs_applies_apply_no_window_at_all_spawn_sites`) は 5 site のままで安定 (`open_folder_in_explorer` を 6 番目として追加しない)
- doc comment で意図 (Win32 GUI / purpose 不一致) を明記 (§5.3)

### 3.4 PROCESS_TRACKER への `open_folder_in_explorer` 登録

- `explorer.exe` はユーザーの file manager UI、`kill_tracked_processes` (CloseRequested flow #523) の対象外であるべき
- 本 spec は `track_child` を呼ばないことで未登録を維持 (現状と同じ挙動)
- doc comment で意図 (UI 残存) を明記 (§5.3)

### 3.5 helper extraction (Approach B 不採用)

- brainstorming Q4 で Approach A (Direct minimal swap) 採用、`process_util::spawn_detached_gui` のような generic helper を導入しない
- 単一 call site の refactor で over-engineering 回避
- 将来 2 つ目の detached GUI spawn site が登場した時点で helper 化を再評価

### 3.6 sync fn 維持 (Approach C 不採用)

- brainstorming Q4 で Approach A 採用、`async fn` 化で他 5 spawn site と convention 統一
- sync fn から tokio Command を呼ぶ場合、tokio runtime 要求の暗黙依存が生じるため明示的に async fn 化する

### 3.7 非 Windows 対応

- [CLAUDE.md](../../CLAUDE.md) 「対応プラットフォーム: Windows のみ」の前提を維持
- 将来 Linux / macOS 対応する際は `xdg-open` / `open` で分岐 (本 spec で touch しない)

### 3.8 新規 AppError code の追加

- 既存 `subprocess.spawn_failed` を継続利用 (Lane I-A #663 AppError migration 結果をそのまま継承)
- 新規 hint code 不要

### 3.9 関連 doc 改定

- [docs/tauri-commands.md](../../docs/tauri-commands.md) の `open_folder_in_explorer` 記載があれば spec 完了時に確認 (impl の見た目変化なし = behavior 不変、記載必要なら最小更新のみ)
- [docs/system-architecture.md](../../docs/system-architecture.md) は spawn API 詳細レベルで言及していないため touch しない

## §4 Architecture

```text
┌─────────────────────────────────────────────────────────────────────────┐
│  Lane VII Group M (1 spec / 1 章 / single PR)                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  gui/src-tauri/src/lib.rs:1842-1862  open_folder_in_explorer            │
│    ┌──────────────────────────────────────────────────────────┐         │
│    │  Before: fn open_folder_in_explorer(...) -> Result<...>    │         │
│    │          use std::process::Command;                         │         │
│    │          Command::new("explorer.exe")                       │         │
│    │            .arg(&path).spawn().map_err(...)?;               │         │
│    └──────────────────────────────────────────────────────────┘         │
│      ↓ refactor                                                          │
│    ┌──────────────────────────────────────────────────────────┐         │
│    │  After:  async fn open_folder_in_explorer(...) -> Result<...> │     │
│    │          tokio::process::Command::new("explorer.exe")        │         │
│    │            .arg(&path).spawn().map_err(...)?;                │         │
│    │  + doc comment 3 段落追記 (#727 / apply_no_window 非適用 /   │         │
│    │    PROCESS_TRACKER 非登録 理由)                              │         │
│    └──────────────────────────────────────────────────────────┘         │
│                                                                          │
│  Untouched (intentional):                                                │
│    - gui/src-tauri/src/process_util.rs (apply_no_window helper、        │
│      adoption test 5 site のまま、open_folder は追加しない)              │
│    - gui/src-tauri/src/lib.rs:1802-1828 (validate_open_folder_request、 │
│      既存 3 unit test 不変、regression 担保)                              │
│    - PROCESS_TRACKER (track_child を呼ばない、UI 残存維持)               │
│    - frontend: invoke('open_folder_in_explorer') が Promise 返却で       │
│      async impl でも sync impl でも挙動同一 (ErrorModal / ExportScreen)  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**並行安全度**: high — `gui/src-tauri/src/lib.rs:1842-1862` の極小領域のみ編集。Lane VII 単一 PR で完結、他 Wave 1 lane (II-a' / II-b' / IV-b'' / VI / V P2 / V P3 / III) と file 衝突なし (file 共有 matrix は roadmap §3-bis 参照)。

## §5 章 1: #727 open_folder_in_explorer の tokio 統一 — design

### 5.1 signature 変更

```rust
// Before (lib.rs:1843)
fn open_folder_in_explorer(path: String) -> Result<(), AppError>

// After
async fn open_folder_in_explorer(path: String) -> Result<(), AppError>
```

- `#[tauri::command]` は sync/async 両対応、frontend `invoke()` は Promise 返却で挙動同一
- 他 5 spawn site (全て `async fn`) と convention 統一

### 5.2 spawn body 変更

```rust
#[tauri::command]
async fn open_folder_in_explorer(path: String) -> Result<(), AppError> {
    validate_open_folder_request(&path)?;

    #[cfg(target_os = "windows")]
    {
        // #727 -- spawn explorer.exe via tokio::process::Command for parity
        // with the other 5 spawn sites (probe_video_with /
        // ensure_thumbnail_exists / run_ffmpeg_export_attempt / start_detect
        // / extract_brightness_window_impl). The returned Child is dropped
        // immediately: explorer.exe is the user's file manager UI and should
        // outlive this Tauri app; Windows has no zombie process model so
        // the drop is safe.
        tokio::process::Command::new("explorer.exe")
            .arg(&path)
            .spawn()
            .map_err(|e| {
                AppError::new(
                    "subprocess.spawn_failed",
                    format!("failed to launch explorer: {}", e),
                )
                .with_default_hint()
            })?;
    }

    Ok(())
}
```

差分:

- `use std::process::Command;` を削除
- `Command::new` → `tokio::process::Command::new` (フルパス参照、他 5 spawn site と同 idiom = `let mut cmd = tokio::process::Command::new(...);` 形式に近い書き方)
- `fn` → `async fn`
- inline comment 追加 (`#727 -- spawn explorer.exe via tokio ...`)
- error message / AppError code (`subprocess.spawn_failed`) は不変

### 5.3 doc comment 拡充 (3 段落追加、既存 #545 経緯保持)

```rust
/// `path` をプラットフォーム固有のファイルマネージャ (Windows: explorer.exe)
/// で開く。
///
/// 旧実装は `tauri-plugin-shell` の `open` を使っていたが、`shell:allow-open`
/// permission の default scope が URL (`mailto:` / `tel:` / `https?://`) しか
/// 許可せず、ローカル path は `Scoped command argument failed regex
/// validation` で reject される。`open` の scope を path 許可に拡張する代わ
/// りに、Windows の `explorer.exe` を直接 spawn する独自 command を用意して
/// 確実に動かす (#545 review、2026-04-25)。
///
/// **#727 (2026-05-13)**: 元 `std::process::Command` から `tokio::process::Command`
/// に切り替え、lib.rs 内 6 spawn site (probe_video_with / ensure_thumbnail_exists
/// / run_ffmpeg_export_attempt / start_detect / extract_brightness_window_impl
/// / 本関数) を `tokio::process::Command` 系で統一する refactor (gui spawn 統一)。
///
/// **apply_no_window 非適用**: explorer.exe は Win32 GUI subsystem アプリで
/// そもそも console window を生成しないため、`process_util::apply_no_window`
/// (= CREATE_NO_WINDOW flag) の purpose (windows_subsystem="windows" 親で
/// release 時の console 割当抑止) と一致しない。本関数は `process_util.rs`
/// adoption test (`lib_rs_applies_apply_no_window_at_all_spawn_sites`) の検査
/// 対象外として扱う。
///
/// **PROCESS_TRACKER 非登録**: explorer.exe はユーザーの file manager UI
/// であり、本 app が close されても残るべき。`track_child` を呼ばないことで
/// `kill_tracked_processes` (CloseRequested flow #523) の影響を受けない。
///
/// Windows のみ対応 (CLAUDE.md に「対応プラットフォーム: Windows のみ」と
/// 明記)。将来 Linux / macOS 対応する際は `xdg-open` / `open` で分岐する。
```

### 5.4 data flow / error handling

- path validation: [`validate_open_folder_request(&path)?`](../../gui/src-tauri/src/lib.rs#L1808) (不変) で existing 3 unit test (lib.rs:4752-4775) がそのまま regression を担保
- Windows / 非 Windows 分岐: `#[cfg(target_os = "windows")]` で **compile-time** 完結、非 Windows ではブロックごと no-op (既存挙動と同一)
- spawn 失敗 path: 既存 `subprocess.spawn_failed` AppError + `.with_default_hint()` 経路を継承 (Lane I-A PR #689 の AppError migration 結果)
- Child の lifecycle: `tokio::process::Command::spawn()` は `io::Result<Child>` を sync で返却、Child は即 drop。Windows は zombie process model なし → drop で OS が child handle を後始末

### 5.5 frontend / call site への影響

- [gui/src/components/ErrorModal.tsx:139](../../gui/src/components/ErrorModal.tsx#L139) の `invoke('open_folder_in_explorer', { path: logDir })` — Promise 返却で影響なし
- [gui/src/screens/ExportScreen.tsx:424](../../gui/src/screens/ExportScreen.tsx#L424) 周辺の `invoke('open_folder_in_explorer', ...)` — 同上
- [gui/src/screens/ExportScreen.test.tsx](../../gui/src/screens/ExportScreen.test.tsx) は `invoke` を mock しているため impl-side 変更は不可視 → regression なし

### 5.6 testing

#### 5.6.1 既存 unit test (不変、regression check)

- [`gui/src-tauri/src/lib.rs:4752-4775`](../../gui/src-tauri/src/lib.rs#L4752) `validate_open_folder_request_*` 3 件 (path 検証ロジック不変、100% pass 維持)
- [`gui/src-tauri/src/process_util.rs:80`](../../gui/src-tauri/src/process_util.rs#L80) `lib_rs_applies_apply_no_window_at_all_spawn_sites` (5 site のまま、`open_folder_in_explorer` を 6 番目として追加しない、pass 維持)
- `gui/src-tauri/src/lib.rs::tests::track_child_*` 系 (PROCESS_TRACKER テスト、`open_folder_in_explorer` は登録しないため不変、pass 維持)

#### 5.6.2 新規 unit test (なし、justification)

- spawn 部分は実機 `explorer.exe` 起動を伴うため CI で stable に test 困難
- `validate_open_folder_request` は既存 3 test で 100% カバー (path validation のみ)
- Approach A 採用、helper 抽出なし → spawn 部の testability 抽象を新規導入しない
- 正常系 (explorer 起動) / 異常系 (path validation error) は Iron Law 6 UAT で担保 (§7.2)

### 5.7 派生 issue 候補 (本章 scope 外、post-merge 起票)

- **(2) 5 spawn site の `tauri-plugin-shell::Command` 移行** — post-v0.2.0 別 issue
  - `process_util::apply_no_window` (`tokio::process::Command` 前提) / `PROCESS_TRACKER` (`tokio::process::Child` 前提) の全面再設計を含む
  - `shell:allow-open` scope を path 許可に拡張する設計検討
- **(3) Windows process group orphan 挙動 audit** — 別 issue (audit task)
  - 親 Tauri app より子プロセスが長生きしたケース / 親 kill 時の子プロセス group の挙動精査
  - 必要なら CREATE_NEW_PROCESS_GROUP / job object 化等の fix を別 issue 起票

## §6 PR 構成 / branch 戦略

### 6.1 single PR

| PR | issue | base branch | scope | merge 順 |
| --- | --- | --- | --- | --- |
| 1 | #727 | develop-0.2.0 | spec doc + impl (lib.rs:1842-1862 編集) + UAT 結果 | 単一 PR、Wave 1 Lane VII initial parallel batch |

- branch: 現 worktree `claude/fervent-brahmagupta-3f4c94`
- PR title 案: `refactor(gui): #727 open_folder_in_explorer を tokio::process::Command に統一 (gui spawn 統一、Lane VII)`
- commit message 案: `refactor(gui): open_folder_in_explorer を tokio::process::Command に統一 (Refs #727)` (Iron Law 4 で Closes/Fixes 禁止、`Refs #727` のみ)
- session-id: `fervent-brahmagupta-3f4c94` を PR 本文末尾に記載

### 6.2 base 同期ポリシー (Iron Law 6 Pre-flight)

```text
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline
# 取り込み未済 commit が gui/src-tauri/src/lib.rs を touch していれば
git merge origin/develop-0.2.0
# 自動チェック再実行
cd gui/src-tauri && cargo check && cargo test --lib
cd gui && npm run lint && npm run typecheck && npm test -- --run && npm run build
ruff check . && ruff format --check . && pyright && pytest
bash scripts/check-markdownlint.sh

gh pr list --search "#727" --state all  # 並行 worktree PR 重複確認
```

### 6.3 release timeline

- Wave 1 (current) 内で merge
- Wave 2 release gate で `/close-issue` 経由実測再検証 → 手動クローズ (`gh issue close 727`)

## §7 検証戦略 (Iron Law 6)

### 7.1 Machine-verified (CI / local 自動)

| 確認 | コマンド |
| --- | --- |
| Rust build | `cd gui/src-tauri && cargo check` |
| Rust unit test (既存) | `cd gui/src-tauri && cargo test --lib` (`process_util::tests::*` / `tests::validate_open_folder_request_*` / `tests::track_child_*` 不変 pass) |
| Frontend lint / typecheck / test / build | `cd gui && npm run lint && npm run typecheck && npm test -- --run && npm run build` |
| Python lint / format / typecheck / test | `ruff check . && ruff format --check . && pyright && pytest` |
| markdownlint | `bash scripts/check-markdownlint.sh` (修正 docs について 0 errors) |

### 7.2 Machine-unverifiable (Iron Law 6 実機検証 — Idios、選択 α)

#### 7.2.1 dev build (`cd gui && npm run tauri dev`)

- [ ] 動画 detect → PreviewScreen → ExportScreen → 完了画面で「フォルダを開く」 → explorer ウィンドウ正常表示
- [ ] ExportScreen エラー → ErrorModal → 「ログフォルダを開く」 → explorer ウィンドウ正常表示
- [ ] path validation エラー再現 (存在しないパス等) → AppError UI 経路で表示 (ErrorModal 表示)

#### 7.2.2 release bundle (`cd gui && cargo tauri build`)

- [ ] release exe (`gui/src-tauri/target/release/bundle/.../allaganeye-gui.exe`) 起動
- [ ] DropScreen で動画選択 → detect 実行 → **CMD 窓非表示** (#679 regression check)
- [ ] PreviewScreen → export 実行 → **CMD 窓非表示** (#679 regression check)
- [ ] export 完了 → 「フォルダを開く」クリック → explorer 正常表示 + **CMD 窓非表示** (本 refactor の確認 + #679 regression check)
- [ ] ErrorModal → 「ログフォルダを開く」 → explorer 正常表示 + CMD 窓非表示

## §8 Self-Test Report テンプレ (実装 PR で記入)

```markdown
## Self-Test Report

### Machine-verified

- [ ] `git fetch origin develop-0.2.0` + `git log HEAD..origin/develop-0.2.0` (取り込み未済 commit なし、または gui/src-tauri/src/lib.rs 非交差)
- [ ] `gh pr list --search "#727"` 並行 worktree PR 重複なし
- [ ] `cd gui/src-tauri && cargo check`
- [ ] `cd gui/src-tauri && cargo test --lib` (process_util / validate_open_folder_request_* / track_child_* 全 pass)
- [ ] `cd gui && npm run lint && npm run typecheck && npm test -- --run && npm run build`
- [ ] `ruff check . && ruff format --check . && pyright && pytest`
- [ ] `bash scripts/check-markdownlint.sh` (修正 docs について 0 errors)

### Machine-unverifiable (Iron Law 6 実機検証 — Idios)

(§7.2 dev/release UAT checklist を本 PR 本文にコピー)
```

## 関連

Refs [#727](https://github.com/Idios/kobutachan-allaganeye/issues/727) (本 spec 対応) [#679](https://github.com/Idios/kobutachan-allaganeye/issues/679) ([PR #720](https://github.com/Idios/kobutachan-allaganeye/pull/720) 完了、`apply_no_window` ヘルパの前提) [#545](https://github.com/Idios/kobutachan-allaganeye/pull/545) (`open_folder_in_explorer` の `tauri-plugin-shell::open` → `std::process::Command` 切替経緯) [#523](https://github.com/Idios/kobutachan-allaganeye/issues/523) (PROCESS_TRACKER / CloseRequested flow) [#663](https://github.com/Idios/kobutachan-allaganeye/issues/663) (Lane I-A AppError migration) [#645](https://github.com/Idios/kobutachan-allaganeye/issues/645) (`extract_brightness_window_impl` 追加で 5 site 拡張) [docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md](../plans/2026-05-13-l2-v020-roadmap-update.md) [docs/superpowers/specs/2026-05-11-l2-lane-ib-group-b-design.md](2026-05-11-l2-lane-ib-group-b-design.md) §5.5 (派生 issue 候補の元)
