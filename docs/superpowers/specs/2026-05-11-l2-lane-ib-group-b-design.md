# L2 Lane I-B: Group B lib.rs / Python 系 backend bugs 設計

> **Status**: v0.2.0 リリースゲート Lane I-B (Group B) — wave 1 main lane (Lane I-A merge 後の継続)
> **Scope**: [#679](https://github.com/Idios/kobutachan-allaganeye/issues/679) + [#648](https://github.com/Idios/kobutachan-allaganeye/issues/648) + [#644](https://github.com/Idios/kobutachan-allaganeye/issues/644) (1 spec / 3 章 / 3 PR 直列)
> **Roadmap**: [docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md](../plans/2026-05-11-l2-v020-roadmap-update.md) Group B
> **依存元 PR**: [#689](https://github.com/Idios/kobutachan-allaganeye/pull/689) (Lane I-A AppError migration 完遂、本 spec の前提として merge 済)
> **session**: `magical-hoover-a632bf` (2026-05-11 brainstorming、Idios + Claude Opus 4.7)

## §0 関連 issue / PR の状態整理

| 参照先 | 状態 | 本 spec への関与 |
| --- | --- | --- |
| [#679](https://github.com/Idios/kobutachan-allaganeye/issues/679) | OPEN (P2-medium, bug) | **本 spec §5 (章 1) で対応** — production build CMD 窓表示 / `CREATE_NO_WINDOW` |
| [#648](https://github.com/Idios/kobutachan-allaganeye/issues/648) | OPEN (P3-low, bug) | **本 spec §6 (章 2) で対応** — `parse_detect_progress_line` silent skip |
| [#644](https://github.com/Idios/kobutachan-allaganeye/issues/644) | OPEN (P3-low, bug) | **本 spec §7 (章 3) で対応** — `run_split` brightness_samples 欠落 |
| [#663](https://github.com/Idios/kobutachan-allaganeye/issues/663) | CLOSED (PR #689 で完了) | AppError migration 完遂、本 spec は spawn / parse / I/O 失敗時に既存 `.with_default_hint()` 経路を**そのまま継承** (新規 AppError code 追加なし) |
| [#647](https://github.com/Idios/kobutachan-allaganeye/pull/647) | MERGED | DetectingScreen の error UI 実装、本 spec **章 2 では非接続** (silent skip → `eprintln!` warn 軽量化方針、roadmap で `phase=error` 化を却下済) |
| [#626](https://github.com/Idios/kobutachan-allaganeye/pull/626) | MERGED | `--from-metadata` で `detection_started_at` / `detection_completed_at` を preserve、本 spec **章 3 で `brightness_samples` も同パターンで preserve** |
| [#569](https://github.com/Idios/kobutachan-allaganeye/issues/569) | CLOSED | `brightness_samples` 仕様の元実装、本 spec **章 3 は detect 経路で動いている配線を split 経路に拡張**するだけ |

## §1 Background

### 1.1 #679 — production build で CMD 窓が表示される (P2-medium, bug)

GUI Tauri アプリの release bundle (`cargo tauri build`) で detect / export を実行すると、Allagan Eye 本体ウィンドウとは別に **コマンドプロンプト風の黒窓が表示される**。Idios の実機 UAT で発見。dev build では再現しない。

**根本原因**:

- [`gui/src-tauri/src/main.rs:1`](../../gui/src-tauri/src/main.rs#L1) で `#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]` により release では親プロセスから console を切り離している
- 親が `windows_subsystem = "windows"` の場合、子プロセスを `Command::spawn` する際 **Windows 側が新規 console window を割り当てる** (`CREATE_NO_WINDOW` flag を明示しない限り回避できない)
- dev build では親が console subsystem (`windows_subsystem` default は `console`) なので新規 console は作られず、ユーザー視点で「production だけ出る」となる

**影響 spawn 箇所** (issue 本文の調査):

| 関数 | 行 (issue 本文時点の調査値、現行 develop-0.2.0 では差異あり) | spawn 対象 |
| --- | --- | --- |
| `start_detect` | `lib.rs:~2409` | allaganeye CLI (Python) |
| `probe_video_with` | `lib.rs:~624` | ffprobe |
| `generate_match_thumbnails` | `lib.rs:~1197` | ffmpeg (thumbnail) |
| `export_match` | `lib.rs:~1798` | ffmpeg (export) |
| `open_folder_in_explorer` | `lib.rs:~1644` | **除外** (`std::process::Command` で `explorer.exe` 起動、Windows UI を開くため意図通り) |

> 上表の line 番号は issue 起票時の調査スナップショットで、現行 develop-0.2.0 では一部 drift 済。実装適用先 (= ffmpeg を実際に spawn している関数) と最新 line 番号は §5.2 の table を参照すること。hyperlink を付けないのは drift により broken link 化するのを避けるため。

### 1.2 #648 — parse_detect_progress_line の silent skip (P3-low, bug)

[`gui/src-tauri/src/lib.rs:~2285-2291`](../../gui/src-tauri/src/lib.rs#L2285) の `parse_detect_progress_line` は CLI が `--progress-format json` で emit した stdout 各行を JSON parse するが、parse 失敗 (malformed JSON / debug print 混入等) を `serde_json::from_str(line).ok()` で `None` 化して **silent skip** する:

```rust
fn parse_detect_progress_line(line: &str) -> Option<DetectProgress> {
    let line = line.trim();
    if line.is_empty() {
        return None;
    }
    serde_json::from_str(line).ok()
}
```

(spec §1.2 の本 snippet は lib.rs:2285-2291 の実装と一致。authoritative な Find/Replace 用 snippet は plan Task 2.2 を参照。)

呼び出し側 ([lib.rs:~2586](../../gui/src-tauri/src/lib.rs#L2586)) は `Option::None` を読み飛ばして次の行へ進むため、CLI 側に schema 不整合があった場合に GUI 側に何も伝わらず、開発者の troubleshooting 手段がない。

**設計選択**: issue 本文 Option 1 (Recommended) では `phase=error` 化 + PR #647 error UI 経路への接続を提案していたが、Roadmap 2026-05-11 update では「`log::warn` + 既知 prefix doc 化」(より軽量) に方針を確定。本 spec はこの roadmap 方針を採用 (Lane I-B brainstorming 2026-05-11 で再確認済)。

### 1.3 #644 — L2a: run_split 経路で brightness_samples が metadata.json に書かれない (P3-low, bug)

[`docs/metadata-spec.md`](../../docs/metadata-spec.md) の `brightness_samples` 仕様 (#569) は次の通り:

> `brightness_samples` | object | 新規書き込みは Pass 1 が走った場合のみ ✓ / 読み込み時は欠落許容 (#569) | GUI complete 画面用の輝度タイムライン

[`allaganeye/commands/detect.py:230-260`](../../allaganeye/commands/detect.py#L230) の `run_detect` (= `allaganeye detect`) は Pass 1 走行時に `captured_brightness` を確保し `build_brightness_samples()` 経由で metadata.json に書く。一方 [`allaganeye/commands/split_matches.py:54`](../../allaganeye/commands/split_matches.py#L54) の `run_split` (= `allaganeye split` の一気通貫経路) では `_run_detection` 呼び出しで `brightness_callback` を渡しておらず、`_split_and_write_metadata` 経由で `_build_metadata_payload` に `brightness_samples` も渡していない。結果、`allaganeye split` 経路で生成された metadata.json には `brightness_samples` キーが欠落。

**発現条件**: CLI で `allaganeye split <video> -o <dir>` を実行 → 生成された metadata.json を GUI で load → CompleteScreen の BrightnessTimeline が `metadata.brightness_samples?.values` 欠落を検知し、in-memory `sampleBrightness()` (固定波形ダミーデータ) にフォールバック → ユーザーには実 brightness ではなく **サンプル波形が描画される**。

GUI のメインフロー (`start_detect` → `run_detect`) は問題なし。**CLI 直接利用 → GUI で metadata.json を後から load** の組合せでのみ顕在化する。

**既存 helper の状況** (本 spec 着手時の調査):

- `_run_detection` ([split_matches.py:684-696](../../allaganeye/commands/split_matches.py#L684)) には **既に `brightness_callback: Callable[..., None] \| None = None` 引数が存在**
- `_build_metadata_payload` ([split_matches.py:1235-1249](../../allaganeye/commands/split_matches.py#L1235)) には **既に `brightness_samples: BrightnessSamples \| None = None` 引数と payload セット (line 1339-1340) が存在**
- `build_brightness_samples` ([split_matches.py:1355](../../allaganeye/commands/split_matches.py#L1355)) ヘルパーも実装済
- 不足: `_split_and_write_metadata` ([split_matches.py:1153](../../allaganeye/commands/split_matches.py#L1153)) には `brightness_samples` 引数がない、`run_split` 内で配線していない

つまり **配線するだけ** で動く (issue 本文の修正案通り)。

## §2 Goals

1. **#679**: Windows production build で 4 spawn 箇所 (`start_detect` / `probe_video_with` / `generate_match_thumbnails` / `export_match`) に `CREATE_NO_WINDOW` flag を一律適用し、子プロセスの console window が表示されないようにする。Iron Law 6 実機検証 (Idios) で release bundle の挙動を確認する。
2. **#648**: `parse_detect_progress_line` の silent skip を `eprintln!` ベースの warn 出力に格上げし、開発者が dev console で parse 失敗を観察できるようにする。`parse_detect_progress_line` の公開 signature と呼び出し側は不変、UX への影響なし。
3. **#644**: `run_split` (一気通貫) 経路で Pass 1 走行時に `brightness_samples` が metadata.json に書かれるよう配線。cache hit / `--from-metadata` の各経路の挙動を `docs/metadata-spec.md` に明文化。GUI CompleteScreen が `allaganeye split` 経由 metadata で **実 brightness を描画**することを Iron Law 6 で確認。
4. 3 章を 1 spec / 3 章 / **3 PR 直列**で進め、`gui/src-tauri/src/lib.rs` の merge conflict を避ける (#679 → #648 順に lib.rs を触り、#644 は Python 側のため独立だが順序は roadmap 通り直列)。

## §3 Non-goals (scope 外明記)

### 3.1 #679 関連 scope 外

- `open_folder_in_explorer` の `std::process::Command` 化 / `tokio::process::Command` 統一化 (本 spec では除外、UI 起動意図維持)
- `tauri-plugin-shell::Command` 経由の spawn 統一化 (Tauri 2 公式 API 移行、大規模 refactor として別 issue)
- dev build 経路の挙動変更 (dev は console subsystem で現状通り)

### 3.2 #648 関連 scope 外

- `phase=error` 化 (issue 本文 Option 1、roadmap で却下、UX 過剰)
- `tauri-plugin-log` 導入 (release file log、別 issue 候補。本章は dev console 観察のみ)
- parse 失敗が連続 N 回で `phase=error` 化 (hybrid 案、複雑性に見合わず)
- CLI 側 stdout schema validation の自動 integration test (CLI ↔ GUI test、別 issue)

### 3.3 #644 関連 scope 外

- cache に brightness map を含める拡張 (cache hit でも書く / cache schema migration、cache file 肥大化、P3 に見合わず)
- BrightnessTimeline UI 改善 (描画密度・色) は別 issue
- `--from-metadata` で boundaries が変わった場合の brightness 再計測 (preserve のみ採用)
- `schemas/metadata.schema.json` 改定 (既存 schema で対応可、再生成不要)

### 3.4 共通 scope 外

- 新規 AppError code の追加 (既存 `subprocess.spawn_failed` / `parse.json_invalid` 等の Lane I-A 経路をそのまま継承)
- [docs/superpowers/specs/2026-05-08-l2-appError-migration-completion-design.md](2026-05-08-l2-appError-migration-completion-design.md) 改定 (Lane I-A の決定を本 spec で覆さない)

## §4 Architecture (Lane I-B 全体構造)

```text
┌─────────────────────────────────────────────────────────────────────────┐
│  Lane I-B Group B (1 spec / 3 章 / 3 PR 直列)                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  章 1: #679 [P2-medium] production build CMD 窓                       │
│    ┌──────────────────────────────────────────────────────────┐         │
│    │ gui/src-tauri/src/process_util.rs (新設)                   │         │
│    │   apply_no_window(cmd: &mut tokio::process::Command)        │         │
│    │     Windows:     cmd.creation_flags(0x0800_0000)             │         │
│    │     non-Windows: no-op                                       │         │
│    └──────────────────────────────────────────────────────────┘         │
│      ↓ apply at 4 spawn sites in lib.rs                                 │
│    start_detect / probe_video_with /                                    │
│    generate_match_thumbnails / export_match                             │
│    (open_folder_in_explorer は除外、std::process::Command の explorer)  │
│                                                                          │
│      ↓ PR merge (lib.rs に最小編集、章 2 と直列)                        │
│                                                                          │
│  章 2: #648 [P3-low] parse_detect_progress_line silent skip            │
│    ┌──────────────────────────────────────────────────────────┐         │
│    │ lib.rs:2285 parse_detect_progress_line を分離              │         │
│    │   fn parse_detect_progress_line(line: &str)                │         │
│    │     -> Option<DetectProgress>  (signature 不変、private)    │         │
│    │   fn parse_detect_progress_line_with_warn(                 │         │
│    │     line: &str, on_warn: impl FnMut(&str))                 │         │
│    │     -> Option<DetectProgress>  (test target)               │         │
│    │   fn truncate_and_escape(line: &str, max: usize) -> String │         │
│    └──────────────────────────────────────────────────────────┘         │
│      ↓ eprintln! (dev stderr、release は windows_subsystem で消失)      │
│      ↓ docs/tauri-commands.md の start_detect 節に doc 化               │
│                                                                          │
│      ↓ PR merge (lib.rs に新規 helper、章 3 と独立)                     │
│                                                                          │
│  章 3: #644 [P3-low] run_split brightness_samples 欠落                 │
│    ┌──────────────────────────────────────────────────────────┐         │
│    │ allaganeye/commands/split_matches.py                       │         │
│    │   run_split (line 54):                                     │         │
│    │     captured_brightness: dict[float, float] = {}           │         │
│    │     _run_detection(..., brightness_callback=...)           │         │
│    │     brightness_samples = build_brightness_samples(...)     │         │
│    │   _split_and_write_metadata (line 1153):                   │         │
│    │     新引数 brightness_samples (pass-through)                │         │
│    │   run_split_from_metadata (line 258):                      │         │
│    │     元 metadata の brightness_samples を preserve            │         │
│    └──────────────────────────────────────────────────────────┘         │
│      ↓ docs/metadata-spec.md に書き込みパス別の挙動表追記               │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**並行安全度**: low (章 1 と章 2 は `gui/src-tauri/src/lib.rs` を共有 → 直列必須)。章 3 は Python 側のみ触るため章 1/2 と並行可能だが、roadmap 方針 (1 spec / 直列 PR) に従い章 1 → 章 2 → 章 3 順に PR を作成・マージする。

## §5 章 1: #679 production build CMD 窓 — design

### 5.1 配置・signature

- 新規 module: [`gui/src-tauri/src/process_util.rs`](../../gui/src-tauri/src/process_util.rs) (新設)
- [`gui/src-tauri/src/lib.rs`](../../gui/src-tauri/src/lib.rs) 冒頭に `mod process_util;` を declare
- 単一 helper 関数:

```rust
// gui/src-tauri/src/process_util.rs

#[cfg(target_os = "windows")]
pub(crate) fn apply_no_window(
    cmd: &mut tokio::process::Command,
) -> &mut tokio::process::Command {
    // CREATE_NO_WINDOW = 0x0800_0000 (winbase.h)
    // 親が windows_subsystem = "windows" の release で子プロセスに
    // console window を割り当てないようにする
    cmd.creation_flags(0x0800_0000)
}

#[cfg(not(target_os = "windows"))]
pub(crate) fn apply_no_window(
    cmd: &mut tokio::process::Command,
) -> &mut tokio::process::Command {
    cmd  // no-op on non-Windows
}
```

- `tokio::process::Command::creation_flags(u32)` は tokio 1.x で `std::os::windows::process::CommandExt::creation_flags` 相当の専用 method を提供 ([tokio 1.52 docs](https://docs.rs/tokio/1.52.1/tokio/process/struct.Command.html#method.creation_flags))
- `std::process::Command` 版は **YAGNI** で実装しない (`open_folder_in_explorer` は除外、現状他の `std::process::Command` 使用箇所なし)

### 5.2 適用 site (4 箇所、`explorer.exe` のみ除外)

| 関数 | 行 | spawn 対象 | 修正 |
| --- | --- | --- | --- |
| `start_detect` | [lib.rs:~2484](../../gui/src-tauri/src/lib.rs#L2484) | allaganeye CLI (Python) | `Command::new(...).args(...)` chain の **`spawn()` 直前**に `process_util::apply_no_window(&mut cmd);` |
| `probe_video_with` | [lib.rs:~651](../../gui/src-tauri/src/lib.rs#L651) | ffprobe | 同上 |
| `ensure_thumbnail_exists` (`generate_match_thumbnails` から呼出) | [lib.rs:~1259](../../gui/src-tauri/src/lib.rs#L1259) | ffmpeg (thumbnail) | 同上 |
| `run_ffmpeg_export_attempt` (`export_match` から呼出) | [lib.rs:~1871](../../gui/src-tauri/src/lib.rs#L1871) | ffmpeg (export) | 同上 |
| ~~`open_folder_in_explorer`~~ | [lib.rs:~1644](../../gui/src-tauri/src/lib.rs#L1644) | **除外** (`std::process::Command`、`explorer.exe`) | **変更なし** |

§1.1 の調査表 (issue 本文 POV) では `generate_match_thumbnails` / `export_match` を spawn site として挙げているが、実 spawn は内部で呼び出される `ensure_thumbnail_exists` / `run_ffmpeg_export_attempt` で行われる (`tokio::process::Command::new("ffmpeg")` の chain 配置位置)。本表は実装適用先 (= ffmpeg を実際に spawn している関数) を示す。

### 5.3 data flow / error handling

- Windows / 非 Windows 分岐は **compile-time** で完結 (`#[cfg(target_os)]`)。runtime overhead なし
- spawn 失敗 path の AppError code (`subprocess.spawn_failed` 等) は PR #689 で `.with_default_hint()` 済、本章で **error path 不変**
- `creation_flags` 適用後の `spawn()` 失敗は既存 path と同じ AppError 経路に乗る

### 5.4 testing

- **unit test** (`process_util.rs` 内 `#[cfg(test)] mod tests`):
  - Windows: `apply_no_window` 適用後 Command が **chain で同 mutable reference を返す** (smoke test、`creation_flags` の read API は public でないため副作用直接検証不可、helper の **chain 化 / 引数受け取り** を pinning)
  - 非 Windows: 同様に identity 返却の no-op smoke test
- **call-site adoption check** (将来の merge で適用漏れを検知する目的):
  - Option a (Recommended、本 spec 採用): `process_util.rs` 内 `#[cfg(test)]` で `include_str!("lib.rs")` (process_util.rs と同階層) で lib.rs 全体を文字列取り込みし、実 spawn を行う 4 関数名 (`probe_video_with` / `ensure_thumbnail_exists` / `run_ffmpeg_export_attempt` / `start_detect`) 直近に `apply_no_window` 文字列が現れることを assert
  - Option b: 各 spawn site を小さな helper 関数に extract し、unit test で helper 単独に `apply_no_window` 呼び出しを pinning
  - Option c: テストでカバーせず PR review + Iron Law 6 実機確認に委ねる (本章 P2-medium につき非推奨)
  - 本 spec は **Option a を採用** (b は採用せず、c は非推奨)。実装手順は plan Task 1.7 を参照
- **Iron Law 6 実機検証 (Idios)**:
  - [ ] `cd gui && cargo tauri build` で release bundle 作成
  - [ ] release exe 起動 → DropScreen で動画選択 → detect 実行 → **CMD 窓非表示**
  - [ ] PreviewScreen → export 実行 → **CMD 窓非表示**
  - [ ] PreviewScreen → folder open in explorer → 通常通り explorer 起動 (除外確認)

### 5.5 派生 issue 候補 (本章 scope 外)

- `open_folder_in_explorer` の tokio::process::Command 統一化 (`std::process::Command` 排除)
- `tauri-plugin-shell::Command` 経由 spawn 統一化 (Tauri 2 公式 API 移行)
- Windows process group attach / detach の挙動精査

## §6 章 2: #648 parse_detect_progress_line silent skip — design

### 6.1 log mechanism: `eprintln!` (依存追加なし)

3 候補比較:

| Option | 依存追加 | dev console | release log | 工数 |
| --- | --- | --- | --- | --- |
| **A: `eprintln!`** (採用) | なし | ✓ stderr → dev console | ✗ `windows_subsystem = "windows"` で stderr 失われる | 最小 |
| B: `tauri-plugin-log v2` | 大 (+ frontend 設定) | ✓ | ✓ file 出力 | 中 |
| C: `log` crate + env_logger | 中 (+ 2 crate) | ✓ | △ (logger 設定次第) | 中 |

**採用: Option A (`eprintln!`)**。

- Roadmap が言う「log::warn + 既知 prefix doc 化」の意図は「**軽量な warn 出力 + silent skip の許容パターン明文化**」であり、特定の log crate 採用を強制しない。本 spec はこの意図を `eprintln!` (依存追加なし) で実装する
- parse 失敗自体が稀 (CLI ↔ GUI が同一リポジトリで schema 同期されている前提)
- dev console で観察できれば troubleshooting 用途は満たす
- release 観察が必要となった場合は **別 issue で `tauri-plugin-log` 導入を検討** (post-Lane I-B、本章 scope 外)
- P3 に見合う最小工数

### 6.2 parse 失敗の分類

| 分類 | 例 | 対応 |
| --- | --- | --- |
| 空行 (許容) | `""` | silent skip 維持 (LF flush 等で発生し得る) |
| 想定外 (malformed JSON / debug print 混入) | `not json`, `[DEBUG] foo` | `eprintln!` で warn 出力 |

「既知 prefix」(将来 CLI 側で debug print が混入したケース等) は **当面想定なし** で扱い、許容パターンは「空行のみ」とする。

### 6.3 truncate / escape ルール

- 失敗 line は **先頭 64 char** で truncate (Unicode-safe boundary、長過ぎる line で log 溢れ防止)
- control char (`\x00`-`\x1F` のうち TAB/LF/CR 以外) は `\xNN` escape (terminal 制御文字注入防止)
- 書式: `[parse_detect_progress_line] malformed JSON (len={N}): "{escaped_truncated}"`

### 6.4 testable な構造 (dependency injection)

`eprintln!` 直書きだと cargo test で stderr capture が貧弱なため、closure injection で testability 確保:

```rust
// 既存 API (signature 不変、可視性 (private fn) も不変、呼び出し側無変更)
fn parse_detect_progress_line(line: &str) -> Option<DetectProgress> {
    parse_detect_progress_line_with_warn(line, |msg| eprintln!("{}", msg))
}

// test target
fn parse_detect_progress_line_with_warn(
    line: &str,
    mut on_warn: impl FnMut(&str),
) -> Option<DetectProgress> {
    if line.is_empty() {
        return None;
    }
    match serde_json::from_str(line) {
        Ok(p) => Some(p),
        Err(_) => {
            let escaped = truncate_and_escape(line, 64);
            on_warn(&format!(
                "[parse_detect_progress_line] malformed JSON (len={}): \"{}\"",
                line.len(),
                escaped,
            ));
            None
        }
    }
}

fn truncate_and_escape(line: &str, max_chars: usize) -> String {
    line.chars()
        .take(max_chars)
        .map(|c| match c {
            '\t' | '\n' | '\r' => c.to_string(),
            c if (c as u32) < 0x20 => format!("\\x{:02X}", c as u32),
            c => c.to_string(),
        })
        .collect()
}
```

- 公開 signature `parse_detect_progress_line(line: &str) -> Option<DetectProgress>` **不変**
- 呼び出し側 ([lib.rs:~2586](../../gui/src-tauri/src/lib.rs#L2586)) **無変更**
- UX 改変なし (`phase=error` 化しない、roadmap 通り)

### 6.5 doc 化

[`docs/tauri-commands.md`](../../docs/tauri-commands.md) の `start_detect` 節に subsection 追加:

- `--progress-format json` の stdout schema (line per JSON、UTF-8、LF separator)
- 許容パターン: 空行 (LF flush) は silent skip
- 想定外: malformed JSON は **stderr に warn 出力** (dev console で観察、release では `windows_subsystem = "windows"` で失われる)
- 別案 (本章 scope 外): release file log は `tauri-plugin-log` 導入で対応 (post-Lane I-B 別 issue)

### 6.6 testing

- **unit test** (5 + 7 = 12 ケース、詳細は plan Task 2.1 / 2.3 を参照):
  - `parse_detect_progress_line_with_warn` 経由 (closure で `Vec<String>` に push して warning capture):
    - 空行 → `None`、warn 呼ばれない
    - 空白のみ行 (`"   \n"`) → `None`、warn 呼ばれない
    - valid JSON → `Some(DetectProgress)`、warn 呼ばれない
    - malformed JSON (`"not json"`) → `None`、warn 1 回呼ばれ message が `malformed JSON` を含む
    - 制御文字含む長文 (>64 char + `\x01` 混入) → warn message に escape 済 + truncate 済 line が含まれる
  - `truncate_and_escape` の境界 test:
    - empty string → `""`
    - `max_chars = 0` → empty
    - short ASCII → verbatim 返却
    - 64 char より長い ASCII → char 数 64 で truncate
    - TAB / LF / CR は escape せず保持
    - その他 ASCII control (`\x01` / `\x1F` 等) → `\xNN` escape
    - multibyte char (日本語) で boundary が char boundary に揃う
- **regression**: `cargo test --lib` で全 test pass、既存 171 件 (うち `parse_detect_progress_line_*` 6 件) と整合

### 6.7 AppError 統合

- parse 失敗は引き続き silent (`None` 返却) → error event 発火せず
- 既存 `subprocess.*` AppError code 経路への影響なし
- 本章 scope では新規 AppError code 追加なし

### 6.8 派生 issue 候補 (本章 scope 外)

- `tauri-plugin-log` 導入による release log file 出力
- parse 失敗が **連続 N 回** で `phase=error` 化 (元 issue Option 3 hybrid 案)
- CLI 側 stdout schema validation の自動 integration test

## §7 章 3: #644 run_split brightness_samples 欠落 — design

### 7.1 配線 (3 関数の変更)

| 関数 | 行 (develop-0.2.0) | 変更内容 |
| --- | --- | --- |
| `run_split` | [split_matches.py:54](../../allaganeye/commands/split_matches.py#L54) | `captured_brightness: dict[float, float] = {}` ローカル変数 + `_on_brightness` callback 追加、`_run_detection(..., brightness_callback=_on_brightness)` で配線、後続で `brightness_samples = build_brightness_samples(captured_brightness)` を計算し `_split_and_write_metadata` に渡す (`build_brightness_samples` は empty dict で `None` を返す。`detect.py:239` の `run_detect` と同パターン) |
| `_split_and_write_metadata` | [split_matches.py:1153](../../allaganeye/commands/split_matches.py#L1153) | signature に `brightness_samples: BrightnessSamples \| None = None` 引数追加、`_build_metadata_payload(..., brightness_samples=brightness_samples)` に pass-through |
| `run_split_from_metadata` | [split_matches.py:258](../../allaganeye/commands/split_matches.py#L258) | 元 metadata.json から `brightness_samples` を読み取り、`_split_and_write_metadata(brightness_samples=preserved)` に渡す (preserve 方針、PR #626 の `detection_started_at` preserve と同パターン) |

既存 helper (`build_brightness_samples` line 1355、`_build_metadata_payload` の `brightness_samples` 引数 line 1249 + payload セット line 1339-1340) は **既に揃っている** ため再利用のみ。

### 7.2 配線 pattern (`detect.py` の `run_detect` と同一)

[`allaganeye/commands/detect.py:230-260`](../../allaganeye/commands/detect.py#L230) のパターンを `run_split` でも踏襲:

```python
# allaganeye/commands/split_matches.py run_split 内 (_run_detection 呼び出し直前)
captured_brightness: dict[float, float] = {}


def _on_brightness(samples: dict[float, float]) -> None:
    captured_brightness.update(samples)


boundaries = _run_detection(
    video_path,
    metadata,
    effective_interval,
    config,
    audio_hits=audio_hits,
    quiet=quiet,
    stats=detect_stats,
    use_gpu=use_gpu,
    gpu_vendor=gpu_vendor,
    brightness_callback=_on_brightness,  # ← 追加 (1 行)
)

# ... boundary 処理後、_split_and_write_metadata 呼び出し直前
# build_brightness_samples は empty dict で None を返す
# (split_matches.py:1373-1374 `if not raw_brightness: return None`)。
# detect.py:239 (run_detect) と同パターン: guard なしで呼び、None なら
# _build_metadata_payload が brightness_samples キーを skip する。
brightness_samples = build_brightness_samples(captured_brightness)
```

### 7.3 cache hit 挙動

- `run_split` 内 cache hit パス: Pass 1 が走らないため `captured_brightness` は空
- `brightness_samples = None` を `_split_and_write_metadata` に渡す → `_build_metadata_payload` が `None` で skip し metadata.json にキーを含めない
- 結果: **cache hit metadata.json に `brightness_samples` キー欠落** (既存 doc「Pass 1 が走った場合のみ」と整合)
- GUI 側は欠落許容済 (#569) → sample fallback 描画 (本章では現状維持)

### 7.4 `--from-metadata` 挙動 (preserve)

- `run_split_from_metadata` 内で元 metadata.json から `brightness_samples` を読み取り
- そのまま `_split_and_write_metadata(brightness_samples=preserved)` で pass-through
- 元 metadata に含まれていなければ欠落のまま (新 metadata も欠落)
- PR #626 の `detection_started_at` / `detection_completed_at` preserve と同パターン

### 7.5 doc 化 ([docs/metadata-spec.md](../../docs/metadata-spec.md))

既存記述「Pass 1 が走った場合のみ ✓ / 読み込み時は欠落許容 (#569)」は正しい。`brightness_samples` subsection に **書き込みパス別の挙動表** を追記:

| 経路 | 書き込み |
| --- | --- |
| `allaganeye detect` (Pass 1 走行) | ✓ 書く (既存) |
| `allaganeye split` (新規検知、Pass 1 走行) | ✓ 書く ← **#644 で対応** |
| `allaganeye split` (cache hit、Pass 1 skip) | ✗ 欠落 (cache に brightness を含めない設計) |
| `allaganeye split --from-metadata` | 元 metadata から **preserve** (元が欠落なら欠落) |

### 7.6 testing

- **pytest** (`tests/test_split_matches.py` 追加 4 ケース):
  - `test_run_split_writes_brightness_samples`: 新規 split で metadata.json に `brightness_samples` キー存在 (mock detector で `brightness_callback` を 1+ 回呼ばせる)
  - `test_run_split_cache_hit_omits_brightness_samples`: cache hit 経路で `brightness_samples` キー欠落
  - `test_run_split_from_metadata_preserves_brightness_samples`: `--from-metadata` で元 metadata の `brightness_samples` が新 metadata に preserve
  - `test_run_split_from_metadata_without_brightness_samples`: `--from-metadata` で元に無ければ新も無し
- mock 戦略: `_run_detection` を monkeypatch して `brightness_callback` を fixture から call (実 detector は重いため避ける)
- **Iron Law 6 実機検証 (Idios)**:
  - [ ] `allaganeye split <video> -o <dir>` (新規、`--no-cache` 併用) 実行 → metadata.json に `brightness_samples` キー存在 (`jq .brightness_samples.values | head` で確認)
  - [ ] 同 metadata を GUI で load → CompleteScreen の BrightnessTimeline が **実 brightness 描画** (sample 波形と異なることを波形特徴で目視確認、dev tools で `metadata.brightness_samples.values` を inspect)
  - [ ] 同動画で `allaganeye split <video> -o <dir2>` (cache hit) → metadata.json に `brightness_samples` 欠落
  - [ ] `allaganeye split --from-metadata <metadata.json> -o <dir3>` (元 metadata に brightness_samples あり) → 新 metadata.json に preserve

### 7.7 schema 影響

- `brightness_samples` は既に [schemas/metadata.schema.json](../../schemas/metadata.schema.json) で定義済 (#569)
- 既存 generated type (`metadata_types.py` / `metadata.generated.ts`) も既存 → 再生成不要
- zod schema (`metadata.schema.ts`) も既存

### 7.8 派生 issue 候補 (本章 scope 外)

- cache に brightness map を含める拡張 (cache hit でも書く、cache schema migration)
- BrightnessTimeline UI 改善 (描画密度・色)
- `--from-metadata` で boundaries が変わった場合の brightness 再計測 (現状は preserve のみ)

## §8 PR 構成 / 直列順 / branch 戦略

### 8.1 PR 直列 (#679 → #648 → #644)

| PR | issue | base branch | scope | merge 順 |
| --- | --- | --- | --- | --- |
| 1 | #679 | develop-0.2.0 | `gui/src-tauri/src/process_util.rs` 新設 + lib.rs 4 spawn site への helper 適用 + unit test + Iron Law 6 | 1 番目 (P2-medium 優先) |
| 2 | #648 | develop-0.2.0 (#679 merge 後 rebase) | `lib.rs` の `parse_detect_progress_line` refactor + `eprintln!` + unit test + `docs/tauri-commands.md` 追記 | 2 番目 (#679 merge 後 lib.rs 取り込み) |
| 3 | #644 | develop-0.2.0 (#648 merge 後 rebase) | `allaganeye/commands/split_matches.py` 配線 + pytest + `docs/metadata-spec.md` 追記 | 3 番目 (Python 側、lib.rs 干渉なしだが roadmap 順守) |

各 PR は独立した branch (例 `claude/679-no-window-flag` / `claude/648-parse-warn-log` / `claude/644-brightness-samples-split`) を develop-0.2.0 から派生させる。後続 PR は base 同期 (`git fetch origin develop-0.2.0 && git rebase origin/develop-0.2.0`) を merge 前に確認する。

### 8.2 spec doc PR

本 spec ([docs/superpowers/specs/2026-05-11-l2-lane-ib-group-b-design.md](2026-05-11-l2-lane-ib-group-b-design.md)) と plan (writing-plans 段階で別途作成) は **3 PR とは独立した spec PR** で先行マージする (Lane I-A の PR #689 が spec + 実装を 1 PR にまとめた経緯に対し、本 Lane では spec 単独 PR + 章ごと実装 PR の分割を採用、レビュー範囲を明確化)。

### 8.3 base 同期ポリシー

各実装 PR の作成前・マージ前に以下を実施:

```text
git fetch origin develop-0.2.0
git rebase origin/develop-0.2.0
# conflict なし確認
ruff check . && ruff format --check . && pyright && pytest                 # Python 側
cd gui/src-tauri && cargo check && cargo test --lib                       # Rust 側
cd gui && npm run lint && npm run typecheck && npm test -- --run && npm run build  # Frontend 側
```

`pr-checklist` CI job が PASS することを確認後 `gh pr merge --squash` でマージ。

## §9 検証戦略 (Iron Law 6)

各 PR で実施する確認の総まとめ。

### 9.1 Machine-verified (CI / local 自動)

| 確認 | コマンド | 該当章 |
| --- | --- | --- |
| Rust build | `cd gui/src-tauri && cargo check` | 1, 2 |
| Rust test | `cd gui/src-tauri && cargo test --lib` | 1, 2 |
| Frontend lint / typecheck / test / build | `cd gui && npm run lint && npm run typecheck && npm test -- --run && npm run build` | 1, 2 (regression なし確認) |
| Python lint / format / typecheck / test | `ruff check . && ruff format --check . && pyright && pytest` | 3 |
| markdownlint | `bash scripts/check-markdownlint.sh` (修正 docs について 0 errors) | 1, 2, 3 |

### 9.2 Machine-unverifiable (Iron Law 6 実機検証 — 失敗パターン B 防止、Idios)

#### 9.2.1 章 1 (#679)

- [ ] `cd gui && cargo tauri build` で release bundle 生成
- [ ] release exe 起動 → DropScreen で動画選択 → detect 実行 → **CMD 窓非表示**
- [ ] PreviewScreen → export 実行 → **CMD 窓非表示**
- [ ] PreviewScreen → folder open in explorer → 通常通り explorer 起動 (除外確認)

#### 9.2.2 章 2 (#648)

- [ ] dev build 起動 + dev console (DevTools / terminal stderr) を開く
- [ ] CLI 側に意図的な debug print 混入を再現 (例: `allaganeye/commands/detect.py` に一時的に `print('debug')` 追加 + GUI から start_detect)
- [ ] dev console に `[parse_detect_progress_line] malformed JSON ...` warn が出力されることを確認
- [ ] `phase=error` UI に切り替わらないこと (silent skip の UX を維持していること) を確認
- [ ] 一時的な debug print を revert

#### 9.2.3 章 3 (#644)

- [ ] `allaganeye split <video> -o <dir> --no-cache` (新規) → metadata.json に `brightness_samples` キー存在
- [ ] 同 metadata を GUI で load → CompleteScreen の BrightnessTimeline が **実 brightness 描画** (sample 波形と異なる)
- [ ] 同動画で `allaganeye split <video> -o <dir2>` (cache hit) → metadata.json に `brightness_samples` 欠落
- [ ] `allaganeye split --from-metadata <metadata.json> -o <dir3>` → 新 metadata.json に preserve

## §10 Self-Test Report テンプレ (実装 PR で記入)

各 PR の body 末尾に以下構造で記入する (Lane I-A PR #689 の Self-Test Report 形式に準拠):

```markdown
## Self-Test Report

### Machine-verified

- [ ] `git fetch origin develop-0.2.0` + `git log HEAD..origin/develop-0.2.0` (取り込み未済 commit なし)
- [ ] `gh pr list --search "#<issue>"` 並行 worktree PR 重複なし
- [ ] `cd gui/src-tauri && cargo check`
- [ ] `cd gui/src-tauri && cargo test --lib`
- [ ] `cd gui && npm run lint && npm run typecheck && npm test -- --run && npm run build`
- [ ] `ruff check . && ruff format --check . && pyright && pytest`
- [ ] `bash scripts/check-markdownlint.sh` (修正 docs について 0 errors)

### Machine-unverifiable (Iron Law 6 実機検証 — Idios)

(§9.2 該当章の実機チェックリスト)
```

## 関連

Refs #679 #648 #644 #663 (Lane I-A 完了) #569 (`brightness_samples` 元実装) #626 (`--from-metadata` preserve パターン) #647 (DetectingScreen error UI、本章では非接続) [`docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md`](../plans/2026-05-11-l2-v020-roadmap-update.md)
