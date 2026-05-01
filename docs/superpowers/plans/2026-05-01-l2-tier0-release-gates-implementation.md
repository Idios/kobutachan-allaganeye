# L2 Tier 0 Release Gate Docs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** L2 (v0.2.0) リリースゲート blocking docs 2 件 (#618 `docs/axum-video-server.md` / #484 `docs/l2-e2e-checklist.md`) を新設し、既存 doc 3 件 (`release-process.md` / `system-architecture.md` / `ui-architecture.md`) に相互参照リンクを追加する。さらに、E2E 自動化検討の deferred follow-up issue を 1 件起票する。

**Architecture:** Spec で定義した 1 spec / 2 章独立構造をそのまま 2 doc 新設 + 既存 doc 更新 + deferred 自動化 issue 起票として展開。実装は doc only で完結し、コード変更は Task 8 で発見された軽微不備の fix のみに限定 (重大不備は別 issue で追跡し本 PR 対象外)。

**Tech Stack:** Markdown / markdownlint (`bash scripts/check-markdownlint.sh`) / GitHub CLI (`gh`) / git

**Spec reference:** [docs/superpowers/specs/2026-05-01-l2-tier0-release-gates-design.md](../specs/2026-05-01-l2-tier0-release-gates-design.md) (commit `0fd8f82`)

**Worktree:** `E:\projects\kobutachan-tools\kobutachan-allaganeye\.claude\worktrees\dazzling-mestorf-10914f` (branch: `claude/dazzling-mestorf-10914f`, base: `develop-0.2.0`)

---

## File Structure

| 種別 | path | 担当 Task |
| --- | --- | --- |
| 新規 | `docs/axum-video-server.md` | Tasks 3-7 |
| 新規 | `docs/l2-e2e-checklist.md` | Tasks 9-12 |
| 更新 | `docs/release-process.md` (§94 / §97) | Task 13 |
| 更新 | `docs/system-architecture.md` (§2.4) | Task 13 |
| 更新 | `docs/ui-architecture.md` (§5 preview) | Task 13 |
| オプション | `gui/src-tauri/src/lib.rs:42-859` (軽微 fix のみ) | Task 8 |
| External | 新 issue (E2E 自動化検討 deferred) | Task 15 |
| External (条件付き) | 新 issue (#618 重大不備) | Task 8 |

---

## Tasks

### Task 1: 既存実装 (`gui/src-tauri/src/lib.rs`) を Read で章ごとに把握

**Goal:** `docs/axum-video-server.md` 9 章に対応する材料を実装から抽出する (Tasks 3-7 の入力)。

**Files:**

- Read: `gui/src-tauri/src/lib.rs:42-100`
- Read: `gui/src-tauri/src/lib.rs:560-620`
- Read: `gui/src-tauri/src/lib.rs:800-870`
- Read: `gui/src-tauri/src/lib.rs:3500-3650`

- [ ] **Step 1:** Read `gui/src-tauri/src/lib.rs:42-100` で `VideoServer` struct + `VIDEO_SERVER: OnceLock<Mutex<VideoServer>>` static の定義を把握。memo: フィールド名 / 型 / 担当責務を抽出 (`bound_port`, `tokens` HashMap など)。

- [ ] **Step 2:** Read `gui/src-tauri/src/lib.rs:560-620` で `register_video` Tauri command 実装を把握。memo: 入力 (`path: String`) / 戻り値 (`RegisteredVideo`) / 内部の lock 取得 + `register_video_sync` 呼び出し / canonical path 検証経路を抽出。

- [ ] **Step 3:** Read `gui/src-tauri/src/lib.rs:800-870` で `register_video_sync` / axum router 構築 / `axum::serve` / `serve_video` route handler の実装を把握。memo: token 発行 (`Uuid::new_v4()` 系) / route path (`/video/{token}`) / `axum::serve(listener, app)` の `tokio::spawn` か直接 await かの判定 / bind address (`127.0.0.1` 確認)。

- [ ] **Step 4:** Read `gui/src-tauri/src/lib.rs:3500-3650` で 既存 Rust テスト (`register_video_rejects_missing_file`, `register_video_rejects_directory`, `register_video_returns_distinct_tokens_for_two_registrations`, `register_video_same_file_twice_yields_distinct_tokens`) を把握。memo: spec の §3 章 3 token lifecycle / §3 章 5 path allowlist で test references として使う。

- [ ] **Step 5:** 把握した情報を Task 3-7 の章執筆メモとして整理 (commit なし、内部メモのみ)。コード変更 / commit は本 Task では行わない。

---

### Task 2: spec を再読し plan との Task 対応を確認

**Goal:** spec の各章が plan の Task でカバーされていることを確認 (Skill 指示 §"Self-Review §1 Spec coverage" を Task 1-2 段階でも先行実施)。

**Files:**

- Read: `docs/superpowers/specs/2026-05-01-l2-tier0-release-gates-design.md`

- [ ] **Step 1:** spec §1 Background / §2 Goals を Read で確認。memo: 各 Task の出力 doc / 担当範囲が一致していること。

- [ ] **Step 2:** spec §3 (axum-video-server.md design / 9 章 + 脅威モデル節 + spec 化中の不備対応ルート) を Read で確認。memo: Tasks 3-7 がそれぞれ章 1-9 + 脅威モデル節 + 不備チェックをカバーしていることを check。

- [ ] **Step 3:** spec §4 (l2-e2e-checklist.md design / 8 章 + T1 詳細フォーマット + T2 障害注入 (a)) を Read で確認。memo: Tasks 9-12 が章 1-8 + T1 fmt + T2 (a) をカバーしていること。

- [ ] **Step 4:** spec §5 (Cross-cutting / 既存 doc 更新範囲 + Deferred follow-up issue) を Read で確認。memo: Task 13 が既存 doc 更新を、Task 15 が deferred issue 起票を担うこと。

- [ ] **Step 5:** spec §6 (Verification / machine-verifiable + machine-unverifiable + Cross-issue link) を Read で確認。memo: Task 14 (markdownlint) と Task 16 (PR 作成 / Refs #618 #484) が verification 項目を満たすこと。

- [ ] **Step 6:** ギャップが見つかれば本 plan に **task を追加** してから先に進む (skill 指示 §Self-Review)。ギャップなしなら Task 3 へ。本 Task では commit なし。

---

### Task 3: `docs/axum-video-server.md` を新設し §1 Overview + §2 Architecture を執筆

**Goal:** spec §3.1 章 1 + 章 2 の内容を実装する。

**Files:**

- Create: `docs/axum-video-server.md`

- [ ] **Step 1:** Write tool で `docs/axum-video-server.md` を新規作成し、ヘッダ + §1 Overview + §2 Architecture を記述する。

  内容指針 (spec §3.1 章 1-2 を展開):

  ```markdown
  # axum 局所 HTTP 動画サーバ仕様

  > **Status**: v0.2.0 リリースゲート blocking spec
  > **対象実装**: `gui/src-tauri/src/lib.rs:42-859` (VideoServer 系、#465 / PR #540 で landed)
  > **本 doc の用途**: 後続 PR (#589 / #645 等) のレビュー判断基準。preview 関連変更時は本 spec との適合確認を行う

  ## §1 Overview

  ### 目的
  `allaganeye-gui.exe` (Tauri bundle) の preview 画面で、ローカルにある動画ファイルを `<video>` 要素で frame seek 可能にするため、Rust 側に axum ベースの局所 HTTP video server を起動する。

  ### Scope
  - Range request 仕様 / token 機構 / path allowlist / bind / async lifecycle / 想定負荷見積を確定する
  - 後続 preview 関連 PR のレビュー時、本 spec との適合確認を行う

  ### 既存実装位置
  - `gui/src-tauri/src/lib.rs:42-99` — `VideoServer` struct + `VIDEO_SERVER` static
  - `gui/src-tauri/src/lib.rs:562-620` — `register_video` Tauri command
  - `gui/src-tauri/src/lib.rs:805-820` — `register_video_sync` testable helper
  - `gui/src-tauri/src/lib.rs:820-870` — axum router + `serve_video` route handler

  ### 関連
  - 実装 PR: [#540](https://github.com/Idios/kobutachan-allaganeye/pull/540) (landed)
  - 親 issue: [#465](https://github.com/Idios/kobutachan-allaganeye/issues/465) (Phase 3 preview 本物化)
  - 後続 issue: [#589](https://github.com/Idios/kobutachan-allaganeye/issues/589) (PreviewScreen state flow)、[#645](https://github.com/Idios/kobutachan-allaganeye/issues/645) (preview 微細タイムライン)

  ## §2 Architecture

  ### コンポーネント構成

  | 要素 | 役割 | 実装位置 |
  | --- | --- | --- |
  | `VideoServer` struct | 単一インスタンスで bind 状態 + tokens を保持 | `lib.rs:42-99` |
  | `VIDEO_SERVER: OnceLock<Mutex<VideoServer>>` | プロセス内グローバル共有 | `lib.rs:56-60` |
  | `register_video` Tauri command | frontend から path 登録、token 発行 | `lib.rs:562-620` |
  | `register_video_sync` | testable な registration helper | `lib.rs:805-820` |
  | axum router (`/video/{token}` GET) | `serve_video` を route 配下に置く | `lib.rs:848` 付近 |
  | `serve_video` route handler | token から path を解決し動画 byte を Range response で返す | `lib.rs:852+` |

  ### 起動シーケンス
  (Task 1 Step 3 で確認した実装内容を順次記述)
  ```

  Task 1 のメモから具体値を埋め、上記 sketch を実装する。

- [ ] **Step 2:** ファイル末尾の table of contents は不要、ただし section 階層は `##` 開始で markdown lint clean を保つ。

- [ ] **Step 3:** Bash で markdownlint を実行: `bash scripts/check-markdownlint.sh docs/axum-video-server.md` (個別ファイル指定が不可な場合は `bash scripts/check-markdownlint.sh` 全体実行)。

  Expected: pass (エラーなし)。エラー出たら指摘行を fix → 再実行。

- [ ] **Step 4:** commit:

  ```bash
  git add docs/axum-video-server.md
  git commit -m "$(cat <<'EOF'
  docs: axum-video-server.md §1 Overview + §2 Architecture を新設

  L2 Tier 0 release gate spec doc の最初の chunk。VideoServer struct と
  register_video / register_video_sync / serve_video の実装位置を整理。

  Refs #618

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 4: `docs/axum-video-server.md` に §3 Token + §4 Range request を追記

**Goal:** spec §3.1 章 3 + 章 4 の内容を実装する。token lifecycle と Range 仕様。

**Files:**

- Modify: `docs/axum-video-server.md` (Task 3 で作成済)

- [ ] **Step 1:** Edit tool で `docs/axum-video-server.md` の §2 Architecture の末尾の後に §3 + §4 を追加する。

  内容指針 (spec §3.1 章 3-4 を展開):

  ```markdown
  ## §3 Token フォーマット + lifecycle

  ### Token 形式
  - 型: `Uuid` (v4)
  - 発行ルール: `register_video_sync` 呼び出しごとに `Uuid::new_v4()` で生成
  - 同一 path で複数回 `register_video` を呼んだ場合、毎回 distinct token が発行される (Task 1 Step 4 で確認: `register_video_same_file_twice_yields_distinct_tokens` テスト)

  ### lifecycle
  - 失効ルール: **GUI セッション中は保持、明示失効 API 無し** (現状実装)
  - 不備として認識: GUI セッション内で生成した token は process 終了まで残るため、長時間実行時の memory 増加リスクあり (Task 8 で軽微 / 重大を判定)
  - frontend → backend 受け渡し: `register_video` の戻り値 (`RegisteredVideo` struct: token + URL) を frontend が受け、`<video src={url}>` に組み立てる

  ### tokens HashMap 構造
  - `tokens: HashMap<Uuid, PathBuf>` で token → 解決 path をマップ (Task 1 Step 1 で確認)
  - lookup は `serve_video` route handler 内で実施

  ## §4 Range request 仕様

  ### 準拠
  - RFC 7233 Range Requests に準拠
  - axum の既定 implementation を活用 (Task 1 Step 3 で確認した serve_video 内の実装方針を記述)

  ### chunk size / partial content
  - HTML5 `<video>` 要素の seek パターン: 任意 byte range を要求
  - 本 server は要求 byte range をそのまま partial content (HTTP 206) で返す
  - chunk size の上限制限は無し (memory 圧迫リスクは preview 用途では実害ない領域)

  ### EOF 扱い
  - 範囲が file 終端を超える場合は `Range Not Satisfiable` (HTTP 416) または file 末尾までの partial content を返す (実装に従う、Task 1 で確認した挙動を記述)
  ```

  Task 1 メモから具体実装を埋める。

- [ ] **Step 2:** markdownlint check: `bash scripts/check-markdownlint.sh`。Expected: pass。

- [ ] **Step 3:** commit:

  ```bash
  git add docs/axum-video-server.md
  git commit -m "$(cat <<'EOF'
  docs: axum-video-server.md §3 Token + §4 Range request を追記

  Uuid v4 token / GUI セッション中保持 / RFC 7233 partial content。
  失効 API 無しは Task 8 で軽微 / 重大を判定。

  Refs #618

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 5: `docs/axum-video-server.md` に §5 Path allowlist + §6 Bind/port を追記

**Goal:** spec §3.1 章 5 + 章 6 + spec §3.2 脅威モデル節 (path traversal / 外部 IF 攻撃) を実装する。

**Files:**

- Modify: `docs/axum-video-server.md`

- [ ] **Step 1:** Edit tool で §4 の末尾後に §5 + §6 を追加する。

  内容指針 (spec §3.1 章 5-6 + §3.2 を展開):

  ```markdown
  ## §5 Path allowlist 機構

  ### allowlist 構造
  - `register_video` で登録された path のみ serve 対象
  - 内部構造: `tokens: HashMap<Uuid, PathBuf>` (token → canonical path)
  - 未登録 path への直接アクセス経路は無い (token 経由のみ)

  ### canonical path 検証
  - `register_video` 内で `std::fs::canonicalize` 呼び出しを行い、symbolic link / `..` を解決した絶対 path を `tokens` に格納 (Task 1 Step 2 で実装確認、Task 8 で実装済かどうかを再 check)
  - 既存 Rust テスト `register_video_rejects_missing_file` / `register_video_rejects_directory` で不正 path の reject を検証

  ### 脅威モデル — Path traversal
  - 攻撃シナリオ: 外部 origin から `/video/{token}/../../etc/passwd` のような traversal を試行
  - 防御: token 経由のみで path を解決するため、URL path に traversal 文字が含まれても serve_video の token lookup は影響を受けない。token から取得する `PathBuf` は登録時の canonical path に固定

  ### 脅威モデル — Token leak
  - GUI セッション内保持 + 外部に出ない前提
  - Uuid v4 の予測困難性 (122-bit entropy) により総当たり推測は実用上不可能
  - frontend が `<video src={url}>` で組み立てた URL は WebView2 内でのみ参照され、外部送信経路は無い

  ## §6 Bind + port

  ### Bind address
  - **`127.0.0.1` 必須** — 外部 NIC への bind は禁止 (Task 1 Step 3 で確認)
  - IPv6 loopback `::1` の扱い: 現状実装で IPv4 loopback のみか dual stack かを Task 1 で確認、結果を記述

  ### Port 動的割当
  - `bound_port: Option<u16>` フィールドに保持 (`VideoServer` struct)
  - 起動時に OS から空き port を取得 (TCP listener bind に `0` を指定する方式)
  - 単一インスタンス起動順序: `OnceLock` + 初回 `register_video` 呼び出し時に lazy init

  ### 脅威モデル — 外部 IF 経由攻撃
  - 127.0.0.1 bind により回避
  - 同一マシン内の他 user / 他プロセスからは loopback 経由でアクセス可能だが、token を知らなければ実害なし (Uuid v4 entropy + GUI セッション内保持)
  ```

- [ ] **Step 2:** markdownlint check: `bash scripts/check-markdownlint.sh`。Expected: pass。

- [ ] **Step 3:** commit:

  ```bash
  git add docs/axum-video-server.md
  git commit -m "$(cat <<'EOF'
  docs: axum-video-server.md §5 Path allowlist + §6 Bind/port を追記

  canonical path 検証 + Uuid v4 entropy + 127.0.0.1 bind の脅威モデル節を含む。

  Refs #618

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 6: `docs/axum-video-server.md` に §7 Async lifecycle + §8 想定負荷見積を追記

**Goal:** spec §3.1 章 7 + 章 8 の内容を実装する。tauri::Manager 連動 + 想定負荷見積。

**Files:**

- Modify: `docs/axum-video-server.md`

- [ ] **Step 1:** Edit tool で §6 末尾後に §7 + §8 を追加する。

  内容指針 (spec §3.1 章 7-8 を展開):

  ```markdown
  ## §7 Async lifecycle

  ### tauri::Manager 連動
  - `axum::serve(listener, app)` は `tokio::spawn` で背景実行 (Task 1 Step 3 で実装確認)
  - GUI 終了時の graceful shutdown 動作:
    - 現状実装: tauri ウィンドウ close → process 終了 → spawn された tokio task は OS による強制終了 (graceful shutdown signal を server に送る経路は明示されていない可能性、Task 8 で確認)
    - 推奨: tauri::Manager の `on_window_event` / `RunEvent::Exit` で server に shutdown signal を送る経路の整備 (重大不備なら別 issue 起票)

  ### 単一インスタンス前提
  - `VIDEO_SERVER: OnceLock<Mutex<VideoServer>>` により process 内で 1 つだけ
  - 複数 register_video 呼び出しは同 server に token を追加するのみ

  ## §8 想定負荷見積

  ### 想定 scenario
  - preview 画面で 2:50:28 録画 (h264 1080p / ~30 Mbps) を loopback 経由で seek + frame 送信
  - 同時 2 stream の seek を想定 (preview 微細タイムライン #645 で導入予定)

  ### 見積もり値

  | 項目 | 想定値 | 計測有無 |
  | --- | --- | --- |
  | 1 stream bandwidth (peak) | ~30 Mbps | 推測値 (h264 1080p 60fps の典型 bitrate) |
  | 同時 2 stream bandwidth | ~60 Mbps | 推測値 |
  | loopback 帯域 | ~10 Gbps (Windows 標準) | OS 仕様 |
  | 余裕度 | 約 170 倍 | 実用上 bottleneck にならない |

  ### 注記
  - **「TBD」「後日計測」だけの placeholder は禁止** (本 spec の規約)
  - 上記は推測値。実機計測を実施した時点で本 doc に値を上書きする。**v0.3.0 で再計測**
  - 計測手段: Windows リソースモニタ + `<video>` element の `currentTime` 移動回数 / 秒
  ```

- [ ] **Step 2:** markdownlint check: `bash scripts/check-markdownlint.sh`。Expected: pass。

- [ ] **Step 3:** commit:

  ```bash
  git add docs/axum-video-server.md
  git commit -m "$(cat <<'EOF'
  docs: axum-video-server.md §7 Async lifecycle + §8 想定負荷見積 を追記

  graceful shutdown 整備の有無は Task 8 で確認。負荷見積は推測値 +
  v0.3.0 再計測注記。

  Refs #618

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 7: `docs/axum-video-server.md` に §9 References を追記し doc 完成

**Goal:** spec §3.1 章 9 References を実装し、`docs/axum-video-server.md` を完成させる。

**Files:**

- Modify: `docs/axum-video-server.md`

- [ ] **Step 1:** Edit tool で §8 末尾後に §9 References を追加する。

  内容指針:

  ```markdown
  ## §9 References

  ### Cross-references
  - [`docs/system-architecture.md` §2.4 GUI 内の video 配信](./system-architecture.md) — 配布物視点での位置付け
  - [`docs/ui-architecture.md` §5 preview](./ui-architecture.md) — preview 画面 UI 状態機械

  ### 関連 PR
  - [#540](https://github.com/Idios/kobutachan-allaganeye/pull/540) — 実装本体 (landed)
  - [#623](https://github.com/Idios/kobutachan-allaganeye/pull/623) — Phase 2.5 detecting/complete 本物化 (preview 遷移経路)

  ### 関連 issue
  - [#465](https://github.com/Idios/kobutachan-allaganeye/issues/465) — Phase 3 preview 本物化 (親 issue)
  - [#589](https://github.com/Idios/kobutachan-allaganeye/issues/589) — PreviewScreen state mutation flow (closed)
  - [#645](https://github.com/Idios/kobutachan-allaganeye/issues/645) — preview 微細タイムライン (open / 本 spec の Phase 3 拡張余地)

  ### 既存テスト (回帰検出)
  - `gui/src-tauri/src/lib.rs:3517` — `register_video_rejects_missing_file`
  - `gui/src-tauri/src/lib.rs:3532` — `register_video_rejects_directory`
  - `gui/src-tauri/src/lib.rs:3557` — `register_video_returns_distinct_tokens_for_two_registrations`
  - `gui/src-tauri/src/lib.rs:3577` — `register_video_same_file_twice_yields_distinct_tokens`
  ```

- [ ] **Step 2:** doc 全体を Read で再読し、§1-9 + 脅威モデル節が揃っていることを確認。spec §3.1 + §3.2 と項目漏れがないか check。

- [ ] **Step 3:** markdownlint check: `bash scripts/check-markdownlint.sh`。Expected: pass。

- [ ] **Step 4:** commit:

  ```bash
  git add docs/axum-video-server.md
  git commit -m "$(cat <<'EOF'
  docs: axum-video-server.md §9 References を追記し doc 完成

  cross-references / 関連 PR / 関連 issue / 既存 Rust テスト位置を網羅。

  Refs #618

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 8: spec 化中の不備チェック + トリアージ (#618 受け入れ条件 spec §3.3)

**Goal:** Tasks 3-7 で発見した実装不備を classify (軽微 / 重大) し、軽微は本 PR で fix、重大は別 issue 起票。

**Files:**

- Read: `gui/src-tauri/src/lib.rs:42-870`
- (条件付き) Modify: `gui/src-tauri/src/lib.rs` (軽微 fix のみ)

- [ ] **Step 1:** Tasks 3-7 で書いた `docs/axum-video-server.md` を再読し、「Task 8 で確認」と書いた箇所を全件抽出する。具体的には:

  - §3 Token failure rule: 失効 API 無し → 軽微 / 重大 の判定
  - §6 Bind: IPv6 loopback `::1` 扱い → 現状実装の確認
  - §7 Async lifecycle: tauri::Manager の `RunEvent::Exit` 経路の整備有無 → 軽微 / 重大 の判定
  - §5 Path allowlist: `std::fs::canonicalize` の現状実装確認

- [ ] **Step 2:** 各項目を Read で実装確認:

  - `gui/src-tauri/src/lib.rs:42-100` (`VideoServer` struct のフィールド構成)
  - `gui/src-tauri/src/lib.rs:560-620` (`register_video` の canonical path 処理)
  - `gui/src-tauri/src/lib.rs:820-870` (axum::serve + tokio::spawn パターン + bind addr)
  - `gui/src-tauri` 内で `RunEvent::Exit` / `on_window_event` 検索 (Grep): `Grep pattern="RunEvent::Exit|on_window_event" path="gui/src-tauri/src"`

- [ ] **Step 3:** 各項目を classify:

  - **軽微** = コメント追加 / typo fix / docstring 改善 / 既存 fn の rename 等で、既存 API 互換を破らない
  - **重大** = 脅威モデル抵触 (canonical path 検証漏れ / 外部 IF への意図せぬ bind / token 失効 API 完全不在で長時間実行時にメモリ leak 等) / 既存 API 変更が必要 / 設計判断必要

- [ ] **Step 4:** 軽微 fix がある場合のみ Edit tool で `gui/src-tauri/src/lib.rs` を修正。

  - 修正前: `cargo check` で現状 pass を確認
  - 修正後: `cd gui/src-tauri && cargo check && cargo test --lib` で regression 無し確認

- [ ] **Step 5:** 重大不備があれば AskUserQuestion で「別 issue 起票してよいか」確認 → 承認後 `/create-task` skill を呼ぶ。

  - title 例: `[bug] L2a: axum video server の <具体的不備> (#618 派生)`
  - label: `bug` / `l2a-gui` / `P1-high` or `P2-medium` / 関連: parent = `#618`
  - 軽微のみ / 重大ゼロなら本 step skip

- [ ] **Step 6:** `docs/axum-video-server.md` の対応箇所を最終 update (現状実装の確認結果を反映、推測値の verify 結果を記入)。

- [ ] **Step 7:** 軽微 fix + doc final update を 1 commit にまとめる:

  ```bash
  git add docs/axum-video-server.md gui/src-tauri/src/lib.rs
  git commit -m "$(cat <<'EOF'
  docs+fix: axum video server spec 化中の軽微 fix 反映

  Task 8 不備チェックで発見した <軽微項目> を fix し、doc に現状実装
  確認結果を反映。重大不備 (もしあれば) は別 issue #XXX で追跡。

  Refs #618

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

  軽微 fix が 0 件なら doc final update のみ commit、重大ゼロかつ doc 最終 update も無しなら本 step skip。

---

### Task 9: `docs/l2-e2e-checklist.md` を新設し §1 Overview + §2 前提環境 を執筆

**Goal:** spec §4.1 章 1 + 章 2 の内容を実装する。

**Files:**

- Create: `docs/l2-e2e-checklist.md`

- [ ] **Step 1:** Write tool で `docs/l2-e2e-checklist.md` を新規作成し、ヘッダ + §1 + §2 を記述する。

  内容指針 (spec §4.1 章 1-2 を展開):

  ```markdown
  # L2 E2E Checklist (v0.2.0 リリース品質ゲート)

  > **Status**: v0.2.0 リリース直前に Idios が手動実施
  > **本 doc の用途**: 2 スコープ (GUI / installer) 合流後のリグレッション検出。`docs/release-process.md §94` v0.2.0 固有項目から本 doc を必須参照
  > **CI 自動化方針**: 本セッション (2026-05-01 brainstorming) で **手動 checklist 主体** に確定。Playwright / Tauri mock driver の feasibility 検討は別 issue (#XXX deferred、Task 15 で起票予定) で v0.3.0+ に follow-up

  ## §1 Overview

  ### 目的
  L2 (v0.2.0) の 2 スコープ (`l2a-gui` / `l2b-installer`) が合流したリリース成果物 (Portable ZIP) で、ユーザーが体験する E2E フロー (動画 drop → detect → preview 編集 → export) のリグレッションを手動検出する。

  ### 位置付け
  - `docs/release-process.md §94 v0.2.0 (L2: GUI サポート + ゼロ環境構築配布) 固有項目` のチェックリストから本 doc が必須参照される
  - 既存 §97 Portable ZIP smoke test を本 doc §3 T1 に置換 (集約)
  - 自動化は v0.2.0 範囲外、別 issue で deferred

  ### 成功条件
  - T1 (基本フロー): 全 step expected 通過
  - T2 (エラーリカバリ): 全 step expected 通過
  - パフォーマンス目安: 検知 ≤ 10 min / export ≤ 3 min / GUI seek p95 ≤ 200 ms
  - screenshot + evidence log が `logs/qa/v0.2.0/` 配下に保存

  ## §2 前提環境

  | 項目 | 値 |
  | --- | --- |
  | OS | Windows 10/11 |
  | サンプル動画 | `$ALLAGANEYE_SAMPLE_VIDEO_DIR/2026-04-08 21-14-05.mkv` (9 試合含む録画を default 推奨) |
  | Portable ZIP | `allaganeye-v0.2.0-windows.zip` 展開済 |
  | 同梱バイナリ健全性 | [#668](https://github.com/Idios/kobutachan-allaganeye/issues/668) のチェックが PASS していること (前提) |
  | ffmpeg | 同梱 BtbN LGPL ビルドを使用、PATH に追加されていなくてもよい |

  ### 環境 variable
  - `ALLAGANEYE_SAMPLE_VIDEO_DIR`: ローカル録画ディレクトリの絶対 path
  - 起動時に未設定なら T1 step 3 を skip し、Idios 環境でのみ実施

  ### 出力先
  - screenshot: `logs/qa/v0.2.0/T<N>-step<M>-<label>.png`
  - evidence log: `logs/qa/v0.2.0/T<N>-step<M>-<label>.log`
  ```

- [ ] **Step 2:** markdownlint check: `bash scripts/check-markdownlint.sh`。Expected: pass。

- [ ] **Step 3:** commit:

  ```bash
  git add docs/l2-e2e-checklist.md
  git commit -m "$(cat <<'EOF'
  docs: l2-e2e-checklist.md §1 Overview + §2 前提環境 を新設

  L2 Tier 0 release gate の手動 smoke test。手動 checklist 主体方針、
  自動化は別 issue で deferred follow-up。

  Refs #484

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 10: `docs/l2-e2e-checklist.md` に §3 T1 (基本フロー) 詳細 を追記

**Goal:** spec §4.1 章 3 + spec §4.2 T1 step 詳細化フォーマットを使い、issue #484 本文の 6 step を expected + screenshot + evidence 込みで展開。

**Files:**

- Modify: `docs/l2-e2e-checklist.md`

- [ ] **Step 1:** Edit tool で §2 末尾後に §3 T1 を追加する。

  内容指針 (spec §4.2 フォーマットで T1.1 〜 T1.6 を全展開):

  ````markdown
  ## §3 T1: 基本フロー (正常系)

  ### T1.1 Portable ZIP 展開

  **操作:**
  1. `allaganeye-v0.2.0-windows.zip` を任意のディレクトリに展開
  2. 展開後ディレクトリに `allaganeye.bat` / `allaganeye-gui.exe` / `bin/ffmpeg.exe` などが揃っていることを確認

  **Expected:**
  - 同梱物の存在を visual で確認
  - `#668` 同梱物健全性チェックが PASS する状態 (T1.2 で起動時 check)

  **Evidence:**
  - screenshot: `logs/qa/v0.2.0/T1-step1-extracted.png` (展開後ディレクトリ)
  - log: なし

  ### T1.2 GUI 起動

  **操作:**
  1. `allaganeye-gui.exe` をダブルクリックで起動

  **Expected:**
  - Tauri ウィンドウが開く (DropScreen 表示)
  - `#668` 健全性 check が PASS した状態でモーダル表示なし
  - `logs/error-YYYYMMDD.log` にエラー記録なし

  **Evidence:**
  - screenshot: `logs/qa/v0.2.0/T1-step2-launched.png` (起動直後の DropScreen)
  - log: `allaganeye-gui.exe` 起動直後の `logs/error-YYYYMMDD.log` を copy → `logs/qa/v0.2.0/T1-step2-startup.log`

  ### T1.3 サンプル動画 drop → detecting → complete

  **操作:**
  1. GUI ウィンドウに `$ALLAGANEYE_SAMPLE_VIDEO_DIR/2026-04-08 21-14-05.mkv` を drag & drop (または `[参照...]` ボタンで選択)

  **Expected:**
  - DropScreen → DetectingScreen に即時遷移
  - フェーズバー (Detecting / Refining) が進行
  - ライブログ panel に CLI stdout が行単位で stream
  - 検知時間: ≤ 10 min (GPU mode、§5 パフォーマンス目安)
  - 検知完了後 CompleteScreen に自動遷移
  - 試合一覧に 9 件のカードが表示される

  **Evidence:**
  - screenshot: `logs/qa/v0.2.0/T1-step3-detecting.png`, `T1-step3-complete.png`
  - log: CLI stdout 全文 + 検知時間記録 → `logs/qa/v0.2.0/T1-step3-detect.log`

  ### T1.4 preview で境界 ±5s 調整

  **操作:**
  1. CompleteScreen で 1 試合のカードを double-click
  2. PreviewScreen に遷移
  3. 開始 / 終了境界を ±5s 範囲で調整
  4. `[適用]` ボタンで保存

  **Expected:**
  - PreviewScreen で動画が再生可能 (axum video server 経由)
  - 境界調整後 `metadata.json` に変更が反映される
  - `[元に戻す]` で `metadata.original.json` から復元可能 (スコープ外、本 step では確認のみ)

  **Evidence:**
  - screenshot: `logs/qa/v0.2.0/T1-step4-preview.png`, `T1-step4-applied.png`
  - log: `metadata.json` の diff → `logs/qa/v0.2.0/T1-step4-metadata-diff.log`

  ### T1.5 export で 9 試合 MP4 書き出し

  **操作:**
  1. ExportScreen に遷移
  2. `[全試合書き出し]` をクリック
  3. 進捗が完了するまで待つ

  **Expected:**
  - 9 試合分の MP4 が `output/` 配下に生成
  - export 時間: ≤ 3 min (copy mode、§5 パフォーマンス目安)
  - GPU encoder auto-select 表示が NVIDIA / Intel / AMD いずれかで反映 (環境依存)

  **Evidence:**
  - screenshot: `logs/qa/v0.2.0/T1-step5-exporting.png`, `T1-step5-done.png`
  - log: ExportScreen 内部ログ + 出力 MP4 一覧 → `logs/qa/v0.2.0/T1-step5-export.log`

  ### T1.6 出力検証 (合計時間 ±1s)

  **操作:**
  1. 出力された 9 試合 MP4 の duration を `ffprobe` で取得:

     ```bash
     for f in output/*.mp4; do
       ffprobe -v error -show_entries format=duration -of csv=p=0 "$f"
     done
     ```

  1. 合計時間を計算
  1. 元動画の試合領域 timestamp 合計 (metadata.json から) と差分計算

  **Expected:**
  - 差分 ≤ 1s (合計時間ベース)

  **Evidence:**

  - log: `ffprobe` 結果 + 差分計算結果 → `logs/qa/v0.2.0/T1-step6-duration-check.log`

  ````

- [ ] **Step 2:** markdownlint check: `bash scripts/check-markdownlint.sh`。Expected: pass。

- [ ] **Step 3:** commit:

  ```bash
  git add docs/l2-e2e-checklist.md
  git commit -m "$(cat <<'EOF'
  docs: l2-e2e-checklist.md §3 T1 (基本フロー) 6 step を追記

  issue #484 本文の T1 を expected + screenshot + evidence 込みの形式で
  展開。サンプル動画は 2026-04-08 録画を default 推奨。

  Refs #484

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 11: `docs/l2-e2e-checklist.md` に §4 T2 (エラーリカバリ) 詳細 を追記

**Goal:** spec §4.3 で確定した障害注入 (a) export 中に Tauri × ボタン process kill を採用し、issue #484 本文の T2 3 step を expected + evidence 込みで展開。

**Files:**

- Modify: `docs/l2-e2e-checklist.md`

- [ ] **Step 1:** Edit tool で §3 末尾後に §4 を追加する。

  内容指針 (spec §4.3 を展開):

  ```markdown
  ## §4 T2: エラーリカバリ

  > **障害注入手段**: 本 spec で **(a) export 中に Tauri × ボタンで process kill** を採用 (再現性高、`#523` と動作定義が連動)。別 (b) read-only path / (c) input 削除 は OS 依存で除外 (spec §4.3)
  >
  > **前提**: `#523` (ffmpeg 中断と graceful kill) の実装が前提。**`#523` 完了前は T2 を skip 可、ただし checklist 本体には記述しておく** (将来の T2 enable 時にすぐ実施可能)

  ### T2.1 障害注入: export 中に Tauri × ボタンで process kill

  **操作:**
  1. T1.5 と同じ手順で export を開始 (9 試合の書き出し)
  2. **5 試合目以降の出力中** で Tauri ウィンドウの × ボタンをクリック
  3. confirm dialog (`#523` 実装) で `[OK]` を選択
  4. アプリが graceful kill → 終了

  **Expected:**
  - confirm dialog が表示される
  - `[OK]` で子 ffmpeg process が graceful kill (SIGTERM 相当)
  - アプリがクラッシュなく終了 (Rust panic / JS error なし)

  **Evidence:**
  - screenshot: `logs/qa/v0.2.0/T2-step1-confirm-dialog.png`, `T2-step1-cancelled.png`
  - log: `logs/error-YYYYMMDD.log` を copy → `logs/qa/v0.2.0/T2-step1-error.log` (panic / 例外なし確認)

  ### T2.2 完成 MP4 の保護

  **操作:**
  1. `output/` ディレクトリを開く
  2. 既に書き出し完了済の MP4 (kill 直前まで完成していた試合) を確認

  **Expected:**
  - 完成済 MP4 (4-5 試合分相当) は破損なく残る
  - kill 時に出力中だった 1 試合分の MP4 は incomplete または 0 byte の可能性あり (許容)
  - 未着手の試合は `output/` に MP4 ファイルが存在しない

  **Evidence:**
  - log: `output/*.mp4` 一覧 + 各 MP4 の duration (`ffprobe`) → `logs/qa/v0.2.0/T2-step2-output-state.log`

  ### T2.3 失敗試合のエラー表示 UI 検証

  **操作:**
  1. アプリを再起動 (`allaganeye-gui.exe` 再実行)
  2. 前回 metadata.json が自動 restore (#574 で実装予定、未実装なら手動で再 drop)
  3. ExportScreen を確認

  **Expected:**
  - 前回 export の状態が CompleteScreen / ExportScreen に反映される (`#574` 実装後)
  - 失敗 / 未完了試合に notice / fallback マーカーが表示される (#591 fallback notice + 本 spec の error UI 拡張)
  - ユーザーが失敗試合のみ再 export 可能

  **Evidence:**
  - screenshot: `logs/qa/v0.2.0/T2-step3-restored.png`, `T2-step3-error-ui.png`
  - log: `logs/error-YYYYMMDD.log` の最新 + 再起動後の起動 log → `logs/qa/v0.2.0/T2-step3-restart.log`

  ### T2 skip 条件
  - `#523` 未マージ時は T2 全 step を skip し、checklist には「`#523` mar マージ後に実施」と注記
  - `#574` 未マージ時は T2.3 expected の「自動 restore」を「手動 drop で代替」と注記

  ### T2 障害注入 (b) (c) を採用しない理由 (spec §4.3 抜粋)
  - (b) read-only path: OS / FS 依存 (NTFS read-only attribute, Windows ACL) で再現性低
  - (c) input 削除中: Windows FS lock により export 中の削除が拒否される可能性、再現困難
  ```

- [ ] **Step 2:** markdownlint check: `bash scripts/check-markdownlint.sh`。Expected: pass。

- [ ] **Step 3:** commit:

  ```bash
  git add docs/l2-e2e-checklist.md
  git commit -m "$(cat <<'EOF'
  docs: l2-e2e-checklist.md §4 T2 (エラーリカバリ) を追記

  障害注入 (a) process kill を採用、#523 マージ後に T2 enable。

  Refs #484 #523

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 12: `docs/l2-e2e-checklist.md` に §5-§8 (パフォーマンス + 成功基準 + CI 方針 + References) を追記

**Goal:** spec §4.1 章 5-8 を実装し doc を完成させる。

**Files:**

- Modify: `docs/l2-e2e-checklist.md`

- [ ] **Step 1:** Edit tool で §4 末尾後に §5 + §6 + §7 + §8 を追加する。

  内容指針 (spec §4.1 章 5-8 を展開):

  ```markdown
  ## §5 パフォーマンス目安

  | 計測対象 | 目安 | 計測手段 |
  | --- | --- | --- |
  | 検知時間 (GPU mode) | ≤ 10 min | DetectingScreen の経過時間表示 + CLI verbose 出力 |
  | 9 試合 export (copy mode) | ≤ 3 min | ExportScreen 進捗 + CLI verbose |
  | GUI seek p95 | ≤ 200 ms | DevTools Performance タブで `<video>` element の `seeked` event 計測 |

  ### 計測の record
  - 各値を `logs/qa/v0.2.0/perf-summary.log` に記載
  - 目安超過時は **目安充足ラインまでパフォーマンス改善** または **目安を緩和する根拠を Idios 判断で記録**

  ## §6 成功基準

  - [ ] T1.1-T1.6 全て expected 通過
  - [ ] T2.1-T2.3 全て expected 通過 (`#523` 未マージ時は skip 注記)
  - [ ] §5 パフォーマンス目安 全項目を実測値で satisfy
  - [ ] 9 試合 MP4 が全て `output/` に生成
  - [ ] `logs/qa/v0.2.0/` 配下に screenshot + evidence log が保存される
  - [ ] T1.6 合計時間差分 ≤ 1s

  ## §7 CI 自動化方針

  ### v0.2.0 方針 (本 spec で確定)
  - **手動 checklist 主体** (本 doc) のみ
  - CI 実行は対象外
  - Idios 実機 (Windows + ALLAGANEYE_SAMPLE_VIDEO_DIR 設定済) で実施

  ### v0.3.0+ で feasibility 検討 (deferred follow-up issue で追跡)
  - **Playwright** (Tauri webview 対応): browser context で assertion 可、cross-platform 制約あり
  - **Tauri mock driver** (公式提供): Phase 0 で feasibility 検証必要、frontend のみ vitest e2e に近い
  - 詳細: 別 issue [#XXX](https://github.com/Idios/kobutachan-allaganeye/issues/XXX) (Task 15 で起票後、本 doc に番号を upd)

  ## §8 References

  - [`docs/release-process.md` §94 v0.2.0 (L2: GUI サポート + ゼロ環境構築配布) 固有項目](./release-process.md) — 本 doc を必須参照
  - [`docs/l2-workflow.md` §実機検証 trigger 表](./l2-workflow.md) — 実機検証ルール
  - [`docs/ui-architecture.md` §5 preview](./ui-architecture.md) — preview 画面の状態機械
  - [`docs/axum-video-server.md`](./axum-video-server.md) — preview 画面の動画配信仕様 (T1.4 関連)
  - [#668](https://github.com/Idios/kobutachan-allaganeye/issues/668) — Portable ZIP 同梱バイナリ健全性 (本 doc 前提)
  - [#523](https://github.com/Idios/kobutachan-allaganeye/issues/523) — ffmpeg 実行中の安全な中断 (T2 障害注入 (a) の実装前提)
  - [#574](https://github.com/Idios/kobutachan-allaganeye/issues/574) — 前回 metadata 自動再現 (T2.3 expected の前提)
  - [#591](https://github.com/Idios/kobutachan-allaganeye/issues/591) — H.264 GPU encoder auto-select / fallback notice (T1.5 / T2.3 関連)
  ```

- [ ] **Step 2:** doc 全体を Read で再読し、§1-8 + 障害注入の説明が揃っていることを確認。spec §4.1 + §4.2 + §4.3 と項目漏れがないか check。

- [ ] **Step 3:** markdownlint check: `bash scripts/check-markdownlint.sh`。Expected: pass。

- [ ] **Step 4:** commit:

  ```bash
  git add docs/l2-e2e-checklist.md
  git commit -m "$(cat <<'EOF'
  docs: l2-e2e-checklist.md §5-§8 を追記し doc 完成

  パフォーマンス目安 / 成功基準 / CI 方針 (手動主体) / References を網羅。
  Task 15 で起票する deferred 自動化検討 issue 番号は後で本 doc に back-fill。

  Refs #484

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 13: 既存 doc 3 件を update (相互参照リンク追加)

**Goal:** spec §5.1 で定義した既存 doc 更新範囲を実装する。

**Files:**

- Modify: `docs/release-process.md` (§94 / §97)
- Modify: `docs/system-architecture.md` (§2.4)
- Modify: `docs/ui-architecture.md` (§5 preview)

- [ ] **Step 1:** `docs/release-process.md` の §94 v0.2.0 固有項目に以下チェックボックスを追加 (line 94-104 の範囲内):

  - [ ] `docs/axum-video-server.md` 新設の確認
  - [ ] `docs/l2-e2e-checklist.md` 全 PASS の確認 (Idios 実機実施)

  さらに既存 §97 Portable ZIP smoke test 記述を `[docs/l2-e2e-checklist.md §3 T1 を参照](./l2-e2e-checklist.md)` に置換。

  Edit tool で具体的な置換は実施前に Read で現状確認 → 該当行を identify → Edit で置換。

- [ ] **Step 2:** `docs/system-architecture.md` の §2.4 GUI 内の video 配信 (line 74 起点) に相互参照リンクを追加:

  ```markdown
  > 詳細仕様: [docs/axum-video-server.md](./axum-video-server.md) (Range / token / async lifecycle / 脅威モデル)
  ```

  既存記述の冒頭または末尾に補足する形 (Edit tool で挿入)。

- [ ] **Step 3:** `docs/ui-architecture.md` の §5 preview (line 170+) に相互参照リンクを追加:

  ```markdown
  > 動画配信の axum HTTP server 仕様: [docs/axum-video-server.md](./axum-video-server.md)
  ```

  Edit tool で適切な位置に挿入。

- [ ] **Step 4:** markdownlint check: `bash scripts/check-markdownlint.sh`。Expected: pass。

- [ ] **Step 5:** commit:

  ```bash
  git add docs/release-process.md docs/system-architecture.md docs/ui-architecture.md
  git commit -m "$(cat <<'EOF'
  docs: 既存 doc 3 件に Tier 0 release gate doc への相互参照を追加

  release-process.md §94 (新 doc 2 件チェック追加 + §97 を l2-e2e-checklist.md
  に置換) / system-architecture.md §2.4 + ui-architecture.md §5 に
  axum-video-server.md への参照リンク追加。

  Refs #618 #484

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 14: markdownlint + lint 全体 check (PR 作成前 verification)

**Goal:** L2 workflow §PR 作成 path 別自動チェック の docs path に該当する markdownlint を pass させる。

**Files:** (確認のみ、変更なし)

- [ ] **Step 1:** markdownlint 全体実行:

  ```bash
  bash scripts/check-markdownlint.sh
  ```

  Expected: 全 .md ファイルが pass。

- [ ] **Step 2:** 失敗時は指摘 file / 行 を Edit で fix → 再実行 → pass まで繰り返す。

- [ ] **Step 3:** Bash で `git status` と `git log --oneline -10` を確認し、Tasks 3-13 の commit が全て完了していることを check。

- [ ] **Step 4:** Verification commit (中身がない場合は本 step skip。fix が発生した場合のみ commit):

  ```bash
  git add <fixed files>
  git commit -m "$(cat <<'EOF'
  docs: markdownlint pass のための軽微 fix

  Tier 0 release gate doc の lint clean を担保。

  Refs #618 #484

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 15: Deferred follow-up issue 起票 (E2E 自動化検討、`/create-task` 経由)

**Goal:** spec §5.2 で定義した deferred 自動化検討 issue を 1 件起票し、`docs/l2-e2e-checklist.md §7` の `[#XXX]` を実 issue 番号に back-fill。

**Files:**

- (External) GitHub issue 1 件起票
- Modify: `docs/l2-e2e-checklist.md` (issue 番号 back-fill)

- [ ] **Step 1:** AskUserQuestion で起票内容の最終確認:

  - title: `[task] L2a: E2E test 自動化 feasibility 検討 (Playwright / Tauri mock driver)`
  - label: `task` / `l2a-gui` / `deferred` / `P3-low`
  - 関連: parent = `#484`
  - 本文骨子: spec §5.2 を引用

  選択肢: `はい起票` / `修正したい (Other)` / `skip`

- [ ] **Step 2:** 承認後、重複チェック:

  ```bash
  gh issue list --repo Idios/kobutachan-allaganeye --search "E2E 自動化 Playwright" --state all --limit 10
  ```

- [ ] **Step 3:** `gh issue create` で起票 (printf | --body-file - で日本語破損回避):

  ```bash
  printf '%s\n' '## 概要

  L2 (v0.2.0) リリースで `docs/l2-e2e-checklist.md` を **手動 checklist 主体** で確定したため、E2E test の自動化は v0.3.0+ で feasibility を検証する deferred 課題として記録する。

  ## 背景

  v0.2.0 brainstorming (2026-05-01) で以下が確定:
  - 手動 checklist (`docs/l2-e2e-checklist.md`) を v0.2.0 リリースゲートに採用
  - Playwright (Tauri webview 対応) / Tauri mock driver (公式) の自動化候補は v0.3.0+ で検証

  ## 確認項目 / 作業項目

  - [ ] Playwright + Tauri webview の組合せで E2E test 実行可能か feasibility 検証
  - [ ] Tauri mock driver の Phase 0 機能評価 (frontend のみ vitest e2e に近い形)
  - [ ] CI 実行コスト (Windows runner / 試合動画 fixture) を見積
  - [ ] 既存 vitest と切り分けた spec / scope を定義
  - [ ] 採用案決定後、別 issue で実装着手

  ## 対応方針

  - v0.3.0 リリース計画段階で再評価
  - Playwright / Tauri mock driver の各 PoC を並行で実施することも検討
  - 採用後、`docs/l2-e2e-checklist.md` の §7 CI 自動化方針 を更新

  ## 関連
  - parent: [#484](https://github.com/Idios/kobutachan-allaganeye/issues/484) (L2 E2E 統合テスト)
  - 参照 doc: `docs/l2-e2e-checklist.md` §7

  作成: dazzling-mestorf-10914f' | gh issue create \
    --repo Idios/kobutachan-allaganeye \
    --title "[task] L2a: E2E test 自動化 feasibility 検討 (Playwright / Tauri mock driver)" \
    --body-file - \
    --assignee "Idios" \
    --label "task" \
    --label "l2a-gui" \
    --label "deferred" \
    --label "P3-low"
  ```

  Expected: `https://github.com/Idios/kobutachan-allaganeye/issues/<番号>` を取得。

- [ ] **Step 4:** Edit tool で `docs/l2-e2e-checklist.md` の §7 内 `[#XXX]` を **取得した実 issue 番号** に置換 (例: `#670`)。

- [ ] **Step 5:** markdownlint check: `bash scripts/check-markdownlint.sh`。Expected: pass。

- [ ] **Step 6:** commit:

  ```bash
  git add docs/l2-e2e-checklist.md
  git commit -m "$(cat <<'EOF'
  docs: l2-e2e-checklist.md §7 に E2E 自動化検討 issue 番号 back-fill

  Task 15 で起票した #<番号> を §7 CI 自動化方針セクションに記載。

  Refs #484 #<番号>

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 16: PR Pre-flight + PR 作成 (Iron Law 6 担保)

**Goal:** L2 workflow §PR 作成 Pre-flight に従い base 同期 + 並行 worktree PR 重複確認を行ってから PR を作成。Iron Law 4 (Closes 禁止) + Iron Law 6 (Pre-flight) 整合。

**Files:** (確認のみ、変更なし)

- [ ] **Step 1:** Iron Law 6 Pre-flight Step 1: base ブランチ最新化確認:

  ```bash
  git fetch origin develop-0.2.0
  git log HEAD..origin/develop-0.2.0 --oneline
  ```

  Expected: 出力 0 行 (最新化済) または develop-0.2.0 に最近 commit が入っている場合は内容を確認。

- [ ] **Step 2:** 取り込み未済 commit が存在し、当 PR の touched files (`docs/release-process.md` / `docs/system-architecture.md` / `docs/ui-architecture.md` / 場合により `gui/src-tauri/src/lib.rs`) と交差する場合のみ:

  ```bash
  git merge origin/develop-0.2.0
  ```

  → conflict 解決 → Tasks 14 の自動チェック (markdownlint) を再実行。

  交差しない場合は merge 不要。

- [ ] **Step 3:** Iron Law 6 Pre-flight Step 2: 並行 worktree PR 重複確認:

  ```bash
  gh pr list --repo Idios/kobutachan-allaganeye --search "618 OR 484" --state open
  ```

  Expected: 重複 PR なし。あれば内容確認 → ユーザーに報告 → 進行可否判断。

- [ ] **Step 4:** ローカル commit を origin に push:

  ```bash
  git push -u origin claude/dazzling-mestorf-10914f
  ```

  Expected: push 成功。

- [ ] **Step 5:** PR 作成 (Iron Law 4: Closes/Fixes/Resolves 禁止、`Refs #618 #484` のみ):

  ```bash
  gh pr create \
    --repo Idios/kobutachan-allaganeye \
    --base develop-0.2.0 \
    --head claude/dazzling-mestorf-10914f \
    --title "docs: L2 Tier 0 release gate (axum video server spec + E2E checklist) を新設 (Refs #618 #484)" \
    --body "$(cat <<'EOF'
  ## Summary

  L2 (v0.2.0) リリースゲート blocking docs 2 件を新設し、既存 doc 3 件に相互参照を追加。E2E 自動化検討の deferred follow-up issue 1 件を起票済。

  - `docs/axum-video-server.md` 新設 (#618): VideoServer 仕様 9 章 + 脅威モデル節
  - `docs/l2-e2e-checklist.md` 新設 (#484): 手動 checklist 8 章 + T1/T2 詳細
  - `docs/release-process.md` / `docs/system-architecture.md` / `docs/ui-architecture.md` に相互参照追加
  - deferred follow-up issue 起票 (E2E 自動化検討、`#<Task15で取得した番号>`)

  ## Spec

  - [docs/superpowers/specs/2026-05-01-l2-tier0-release-gates-design.md](docs/superpowers/specs/2026-05-01-l2-tier0-release-gates-design.md) (commit 0fd8f82)

  ## Refs

  Refs #618 #484 #<Task15 番号> #<Task8 で重大不備があれば追加>

  ## Self-Test Report

  ### machine-verifiable
  - [x] markdownlint: `bash scripts/check-markdownlint.sh` → pass
  - [x] `docs/axum-video-server.md` 新設 (§1-9 + 脅威モデル節)
  - [x] `docs/l2-e2e-checklist.md` 新設 (§1-8 + T1/T2 詳細 + 障害注入 (a))
  - [x] 既存 doc 3 件 update (相互参照リンク + §97 置換)
  - [x] deferred follow-up issue 起票完了
  - [x] Iron Law 6 Pre-flight: develop-0.2.0 fetch + 交差確認 + 並行 worktree PR 重複確認 完了

  ### machine-unverifiable (本 PR スコープ外)
  - 実機 T1/T2 実施は v0.2.0 リリース直前に Idios が別段階で実施 (本 doc を checklist として使用)
  - #618 spec 化中の不備チェック (Task 8) で **重大不備 0 件 / 軽微 fix <件数>** (Task 8 の最終結果を記入)

  🤖 Generated with [Claude Code](https://claude.com/claude-code)
  EOF
  )"
  ```

  Expected: PR URL を取得。

- [ ] **Step 6:** PR 起票後 issue にコメント追記 (`docs/issue-policy.md §7 完了時` に従う):

  ```bash
  gh issue comment 618 --repo Idios/kobutachan-allaganeye --body "完了: dazzling-mestorf-10914f → PR #<番号>
  axum-video-server.md 新設 (9 章 + 脅威モデル節) + 既存 doc 相互参照 + Task 8 不備チェック (重大 0 件 / 軽微 <件数>)"

  gh issue comment 484 --repo Idios/kobutachan-allaganeye --body "完了: dazzling-mestorf-10914f → PR #<番号>
  l2-e2e-checklist.md 新設 (8 章 + T1/T2 詳細) + 既存 release-process.md §94/§97 update + 自動化検討 deferred issue #<番号> 起票"
  ```

---

## Self-Review

(本 plan 著者である writing-plans skill による self-review。skill 指示 §"Self-Review" 準拠)

### 1. Spec coverage

| spec section | 担当 Task |
| --- | --- |
| §1 Background | Task 2 (確認) |
| §2 Goals | Task 2 (確認) |
| §3.1 章 1-2 (axum Overview/Architecture) | Task 3 |
| §3.1 章 3-4 (Token/Range) | Task 4 |
| §3.1 章 5-6 (Path allowlist/Bind) | Task 5 |
| §3.1 章 7-8 (Async lifecycle/負荷見積) | Task 6 |
| §3.1 章 9 (References) | Task 7 |
| §3.2 脅威モデル節 | Tasks 5, 6 (各章内に展開) |
| §3.3 不備対応ルート | Task 8 |
| §4.1 章 1-2 (e2e Overview/前提環境) | Task 9 |
| §4.1 章 3 / §4.2 T1 詳細 | Task 10 |
| §4.1 章 4 / §4.3 T2 障害注入 (a) | Task 11 |
| §4.1 章 5-8 (パフォーマンス/成功基準/CI/References) | Task 12 |
| §5.1 既存 doc 更新 | Task 13 |
| §5.2 deferred follow-up issue 起票 | Task 15 |
| §6 Verification machine-verifiable | Tasks 14, 16 |
| §6 Verification machine-unverifiable (本 PR スコープ外) | Task 16 (PR body の記載のみ) |
| §6 Cross-issue link | Task 16 (PR body 内 Refs) |

ギャップなし。全 spec section が Task でカバー。

### 2. Placeholder scan

- "TBD" / "TODO" / "implement later" / "fill in details" → なし
- "Add appropriate error handling" / "handle edge cases" → なし
- "Write tests for the above" → なし (本 plan は doc only)
- "Similar to Task N" → なし (各 Task の内容指針は独立)
- 「Task X で取得した番号」記述あり (Task 15 で起票した issue 番号を Task 12 / Task 16 で back-fill する形) — これは placeholder ではなく **依存関係の明示** なので OK

### 3. Type consistency

- 章番号 (§1-§9) は spec と plan で一致
- ファイル path (`docs/axum-video-server.md` / `docs/l2-e2e-checklist.md`) は全 Task で固定
- gh CLI 引数 (`--repo Idios/kobutachan-allaganeye` / `--label` / `--assignee`) は全 step で一致
- commit message format (`docs: <内容> (Refs #N)`) は全 commit step で一致

### 4. Ambiguity check

- T2 障害注入 (a) process kill 採用 → 明示済 (spec §4.3)
- サンプル動画 default = `2026-04-08 21-14-05.mkv` → 明示済 (spec §4.1 章 2)
- 想定負荷見積の placeholder 禁止 + v0.3.0 再計測注記 → 明示済 (spec §3.1 章 8)
- Task 8 の軽微 / 重大 classify 基準 → 明示済 (Task 8 Step 3)
- Task 15 の起票内容 → 明示済 (Task 15 Step 1)
- `#523` 未マージ時の T2 skip 注記 → 明示済 (Task 11 Step 1 内 § skip 条件)

ambiguity ゼロ。

---

## Execution Handoff

(writing-plans skill 完了後、ユーザーに実行方式を選んでもらう)

**Plan complete and saved to `docs/superpowers/plans/2026-05-01-l2-tier0-release-gates-implementation.md`. Two execution options:**

1. **Subagent-Driven (recommended)**: 各 Task を fresh subagent に dispatch、Task 間で 2-stage review、高い並行性
2. **Inline Execution**: 本セッション内で `superpowers:executing-plans` を使い batch 実行 + checkpoint

**Which approach?**
