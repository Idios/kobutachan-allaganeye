# L2 (v0.2.0) Tier 0 Release Gate Docs Design

**Status**: Draft (brainstorming output, awaiting writing-plans)
**Date**: 2026-05-01
**Session**: dazzling-mestorf-10914f
**Scope**: GitHub issues [#618](https://github.com/Idios/kobutachan-allaganeye/issues/618) + [#484](https://github.com/Idios/kobutachan-allaganeye/issues/484)
**Decided in this session**:

- #484 CI 自動化方針 = **手動 checklist 主体** (自動化 = deferred / 別 issue で follow-up)
- #618 spec 化中の実装不備 = **軽微は本 PR / 重大は別 issue** (Iron Law 3 整合)
- Spec structure = **1 spec / 2 章独立** (Approach 1)

---

## §1 Background

L2 (v0.2.0) リリース blocking docs として 2 件:

- **#618 `docs/axum-video-server.md` (新設)**: Phase 3 preview の局所 HTTP video server を spec として確立。実装は `#465` / PR `#540` で `gui/src-tauri/src/lib.rs` に landed 済 (`VideoServer` struct: line 42 / `register_video` Tauri command: line 562 / `register_video_sync` testable helper: line 805 / `serve_video` route handler: line 852 / axum router `/video/{token}`: line 848 / `axum::serve`: line 834)。spec 不在のままなので脅威モデル / 後続 PR (`#645` micro brightness timeline 等) のレビュー判断基準が無い。
- **#484 `docs/l2-e2e-checklist.md` (新設)**: v0.2.0 リリース前手動 smoke test の標準化。本セッションで **手動 checklist 主体 + 自動化は別 issue で deferred 起票** に確定。`docs/release-process.md §94 v0.2.0 (L2: GUI サポート + ゼロ環境構築配布) 固有項目` (line 94-104、§97 Portable ZIP smoke test を含む) と整合させる。

両 doc とも v0.2.0 リリース受け入れゲートの前提であり、後続 PR (#523, #589, #645 等) のレビュー判断基準として機能する。

## §2 Goals

| 出力 | 種別 | 既存実装 / 参照 |
| --- | --- | --- |
| `docs/axum-video-server.md` (新規) | spec / 脅威モデル | `gui/src-tauri/src/lib.rs:42-859` の `VideoServer` 系を後追い文書化 |
| `docs/l2-e2e-checklist.md` (新規) | 手動 checklist | `docs/release-process.md §94` Portable ZIP smoke test を拡張 |
| `docs/system-architecture.md` §2.4 / `docs/ui-architecture.md` §preview / `docs/release-process.md §94` への相互参照リンク追加 | 既存 doc 更新 | 上記 2 doc への入口 |
| 自動化検討 deferred 用の別 issue (本 spec の §6 Verification 段階で `/create-task` 起票) | follow-up | v0.3.0+ で再評価 |

## §3 Section A: `docs/axum-video-server.md` design

### §3.1 章立て (9 章)

1. **Overview** — purpose / scope / v0.2.0 リリースゲート位置付け / 既存実装 path (`gui/src-tauri/src/lib.rs:42-859`)
2. **Architecture** — `VideoServer` struct の責務 / `VIDEO_SERVER: OnceLock<Mutex<VideoServer>>` 単一インスタンス前提 / `register_video` (Tauri command) と `register_video_sync` (testable helper) の分離 / axum router (`/video/{token}` GET → `serve_video`)
3. **Token フォーマット + lifecycle** — `Uuid` (v4) / per-registration 発行 (`register_video_sync` で同一 path でも distinct token) / 失効ルール (現状: GUI セッション中保持、明示失効 API なし — **不備として明示認識**) / frontend → backend 受け渡し経路 (Tauri command return → frontend で URL 組立)
4. **Range request 仕様** — RFC 7233 partial content / chunk size / EOF 扱い / preview frame seek パターン (`<video>` element の seek 挙動) / 既存実装の `axum` 既定 + 必要な custom range header
5. **Path allowlist 機構** — `register_video` で登録された path のみ serve / canonical path 化による traversal 防御 / `tokens: HashMap<Uuid, PathBuf>` 構造の役割
6. **Bind + port** — `127.0.0.1` 必須 (外部 IF 拒否) / port 動的割当 (`bound_port: Option<u16>`) / 単一インスタンス起動順序 / IPv6 loopback `::1` 扱いの明示
7. **Async lifecycle** — `tauri::Manager` 連動 / `axum::serve(listener, app)` の `tokio::spawn` 前提 / GUI 終了時の graceful shutdown (現状実装の確認 + 不備があれば軽微修正 / 重大は別 issue)
8. **想定負荷見積** — preview 2:50:28 録画で同時 2 stream の seek パターン
   - **計測方針**: Idios 環境で実測 → 取れない場合は **推測値 + 「v0.3.0 で再計測」注記** を必ず付ける ("TBD" / "後日計測" だけの placeholder は禁止)
   - 推測値の参考: 1 stream あたり 1080p / 60fps / h264 / ~30 Mbps を想定し、同時 2 stream で約 60 Mbps の loopback bandwidth (実環境で問題ない領域)
9. **References** — `docs/system-architecture.md §2.4` / `docs/ui-architecture.md §5-preview` への相互リンク + 関連 PR (#465, #540) / 関連 issue (#589, #645)

### §3.2 脅威モデル節 (章 5 + 7 の中で展開)

- **Path traversal**: canonical path 検証 (`std::fs::canonicalize`) + allowlist token gating で防御
- **Token leak**: GUI セッション内保持で外部出ない前提 / 別 origin 経由の token 推測攻撃の前提評価 (Uuid v4 の予測困難性)
- **外部 IF 経由攻撃**: `127.0.0.1` bind による回避 / IPv6 loopback `::1` 扱い (現状実装でどう扱われているかを確認の上で記述)

### §3.3 spec 化中の不備対応ルート

本セッション決定 (Approach 1):

- **軽微修正は本 PR 内**: コメント追加 / API 名修正 / docstring 改善 / typo 等
- **重大不備は別 issue 起票**: token 失効 API 不在 / async task 畳み込み漏れ / canonical path 検証漏れ / 等の脅威モデル抵触ケース
- 起票時は `task` / `l2a-gui` / `P1-high` or `P2-medium` / 関連: parent = `#618`

## §4 Section B: `docs/l2-e2e-checklist.md` design

### §4.1 章立て (8 章)

1. **Overview** — v0.2.0 リリース品質ゲート / **手動 checklist 主体** (本セッション決定) / `docs/release-process.md §94` (line 94-104) の v0.2.0 固有項目に組み込み / 自動化は別 issue で follow-up
2. **前提環境** — Windows / `ALLAGANEYE_SAMPLE_VIDEO_DIR` (Idios 環境の standard sample = `$ALLAGANEYE_SAMPLE_VIDEO_DIR/2026-04-08 21-14-05.mkv` など 9 試合含む録画を default 推奨) / Portable ZIP 展開済 / **#668 同梱バイナリ健全性チェック** が PASS していること (前提条件として cross-link)
3. **T1: 基本フロー** — issue #484 本文の 6 step を **expected result + screenshot 保存先 (`logs/qa/v0.2.0/T1-step{N}.png`) + evidence log (`logs/qa/v0.2.0/T1-step{N}.log`) を伴う形式に拡張**。出力検証 (合計時間 ±1s) は `ffprobe -v error -show_entries format=duration` 結果と元動画の試合領域 timestamp の差分計算で実施
4. **T2: エラーリカバリ** — 障害注入手段として **(a) export 中に Tauri × ボタンで process kill** を採用 (再現性高 / `#523` と動作定義が connection、別 (b) read-only path / (c) input 削除 は OS 依存で除外)。3 step を expected result 込みで記述
5. **パフォーマンス目安** — 検知 ≤ 10 min (GPU mode) / 9 試合 export ≤ 3 min (copy mode) / GUI seek p95 ≤ 200 ms。計測手段 = CLI verbose 出力 / GUI 内部計測ログ / DevTools Performance タブ
6. **成功基準** — T1-T2 全 PASS + パフォーマンス充足 + 9 試合 MP4 全出力 + screenshot / evidence log 保存
7. **CI 自動化方針** — 本セッション決定: v0.2.0 は手動のみ / Playwright / Tauri mock driver の feasibility 検討は **別 issue で deferred 起票** (本 spec の §6 Verification で起票手順明示)
8. **References** — `docs/release-process.md §94` / `docs/l2-workflow.md §実機検証 trigger 表` / `docs/ui-architecture.md §preview` / [#668](https://github.com/Idios/kobutachan-allaganeye/issues/668) (前提条件 cross-link)

### §4.2 T1 step 詳細化フォーマット (例)

issue #484 本文の 6 step を以下の形式で `docs/l2-e2e-checklist.md §3` に展開する:

```markdown
### T1.3 サンプル動画 drop → detecting → complete 画面遷移

**操作**:
1. GUI ウィンドウに `$ALLAGANEYE_SAMPLE_VIDEO_DIR/2026-04-08 21-14-05.mkv` を drag & drop
   (または `[参照...]` ボタンで選択)

**Expected**:
- DropScreen → DetectingScreen に即時遷移
- フェーズバー (Detecting / Refining) が進行
- ライブログ panel に CLI stdout が行単位で stream
- 検知完了後 CompleteScreen に自動遷移
- 試合一覧に 9 件のカードが表示される

**Evidence**:
- screenshot: `logs/qa/v0.2.0/T1-step3-detecting.png` / `T1-step3-complete.png`
- log: `logs/qa/v0.2.0/T1-step3-detect.log` (CLI stdout 全文 + 検知時間記録)
```

T1.1 〜 T1.6 + T2.1 〜 T2.3 を同形式で展開。

### §4.3 T2 障害注入手段 (a) 詳細

**T2.1 障害注入: export 中に Tauri × ボタンで process kill**

- export を開始 (5 試合目以降の出力中で実施を推奨)
- Tauri ウィンドウの × ボタンクリック → confirm dialog (`#523` で実装) で OK
- 子 ffmpeg process が graceful kill される
- 既に出力済みの試合 MP4 は残る、kill 時に出力中だった試合は incomplete

**Expected**:

- 残り未出力の 4-5 試合は処理されない (kill 後 GUI 終了のため)
- `output/` には 4-5 試合分の完成 MP4 + 1 試合分の incomplete (途中で kill された) または 0 件 (graceful kill が完成済 MP4 の保護を満たす)
- アプリ再起動 → metadata.json は restore (前回 state)、未完了の export は再実行可

**Evidence**:

- screenshot: `logs/qa/v0.2.0/T2-step1-cancelled.png`
- ffprobe 結果: 各 MP4 の duration 確認 log

`#523` (ffmpeg 中断と graceful kill) の実装が前提。**`#523` 完了前は T2 を skip 可、ただし checklist 本体には記述しておく** (将来の T2 enable のため)。

## §5 Cross-cutting concerns

### §5.1 既存 doc の更新範囲

| 既存 doc | 更新内容 |
| --- | --- |
| `docs/release-process.md §94 v0.2.0 固有項目` | (i) 本 doc 2 件の新設確認チェックを追加 (ii) 既存 §97 Portable ZIP smoke test を `docs/l2-e2e-checklist.md §3 T1` に置換 (内容は同 doc に集約) |
| `docs/system-architecture.md §2.4 配布` | `docs/axum-video-server.md` への相互参照リンク追加 |
| `docs/ui-architecture.md §5-preview` | `docs/axum-video-server.md` への相互参照リンク追加 |

### §5.2 Deferred follow-up issue 起票

本 spec を input とする実装 PR の中で、以下 1 件を `/create-task` で起票する:

- **title**: `[task] L2a: E2E test 自動化 feasibility 検討 (Playwright / Tauri mock driver)`
- **label**: `task` / `l2a-gui` / `deferred` / `P3-low`
- **本文骨子**: #484 親 issue で v0.2.0 は手動 checklist 主体に確定。v0.3.0 以降に Playwright (Tauri webview 対応) または Tauri 公式 mock driver の feasibility を検証し、E2E test の自動化を導入する判断を行う。検証項目: webview 操作可能性 / cross-platform 制約 / CI 実行コスト / 既存 vitest との切り分け
- **関連**: parent = `#484`
- **起票 timing**: 本 spec 実装 PR 内で実施 (Iron Law 2 = 1 件は bulk 該当せず、AskUserQuestion で 1 回確認の上)

## §6 Verification

本 spec を input とする実装 PR (writing-plans の出力 plan を実行する PR) は以下を満たす:

### machine-verifiable

- [ ] `docs/axum-video-server.md` 新設 (§3 章立て 9 章 + 脅威モデル節)
- [ ] `docs/l2-e2e-checklist.md` 新設 (§4 章立て 8 章 + T1/T2 詳細 + 障害注入 (a))
- [ ] 既存 doc 更新 (release-process.md §94 / system-architecture.md §2.4 / ui-architecture.md §preview) に相互参照リンク追加
- [ ] markdownlint pass: `bash scripts/check-markdownlint.sh` で全 doc lint clean
- [ ] E2E 自動化検討 deferred issue が `/create-task` で起票完了 (issue 番号を PR 本文に記載)
- [ ] PR 本文に `Refs #618` `Refs #484` 明記、`Closes` keyword は禁止 (Iron Law 4)
- [ ] PR Self-Test Report 規約: machine-verifiable は `[x]`、machine-unverifiable は plain bullet `-`

### machine-unverifiable

- 本 spec PR 自体には実機検証は不要 (doc のみで完結)。`#484` の T1/T2 実機実施は v0.2.0 リリース直前に Idios が別段階で実施 (PR レビュー時の Self-Test Report で Spec PR との切り分けを明記)
- `#618` spec 化中に発見した実装不備の処理ルート: 軽微なら本 PR / 重大は別 issue 起票完了 (発見しなければ "発見ゼロ" を PR 本文に明記)

### Cross-issue link

- PR 本文の `## Summary` に「Refs #618」「Refs #484」を明記
- `/create-task` で起票した deferred issue 番号も PR 本文に追記

---

## 参照 doc / 既存実装

- 関連 plan: `C:\Users\idios\.claude\plans\github-l2-issue-issue-l2-issue-issue-glittery-dusk.md` (本セッションで作成、L2 v0.2.0 ロードマップ全体)
- 既存実装: `gui/src-tauri/src/lib.rs:42-859` (`VideoServer` 系)
- 既存 doc: `docs/system-architecture.md` / `docs/ui-architecture.md` / `docs/release-process.md` / `docs/l2-workflow.md`
- 関連 issue: `#618` / `#484` / `#465` (Phase 3 preview 実装) / `#523` (ffmpeg 中断) / `#589` (PreviewScreen state flow) / `#645` (preview 微細タイムライン) / `#668` (Portable ZIP 同梱物健全性、本 spec の前提条件 cross-link)
- 関連 PR: `#540` (#465 実装本体) / `#623` (Phase 2.5 detecting/complete 本物化、関連)

---

## Implementation Status (post-merge, 2026-05-02)

### 結果サマリ

- **PR**: [#672](https://github.com/Idios/kobutachan-allaganeye/pull/672) **MERGED** at 2026-05-02T02:39:34Z, merge commit `3951917a93a7f7740e182f3c70c2d35d2ba80556` to `develop-0.2.0`
- **plan**: [docs/superpowers/plans/2026-05-01-l2-tier0-release-gates-implementation.md](../plans/2026-05-01-l2-tier0-release-gates-implementation.md) — 16 task subagent-driven (Execution Status section に詳細記録)
- **作成 worktree**: `dazzling-mestorf-10914f` (branch `claude/dazzling-mestorf-10914f`)

### 出力 deliverable

| 種別 | path | 状態 |
| --- | --- | --- |
| 新規 doc | `docs/axum-video-server.md` | 254 行、§1-9 + 脅威モデル、commit 3951917 配下 |
| 新規 doc | `docs/l2-e2e-checklist.md` | ~298 行 (Round 1 fix 後)、§1-8 + T1/T2 詳細 + 障害注入 (a) |
| 更新 doc | `docs/release-process.md` §94 | 新 doc 2 件チェック + §97 を l2-e2e-checklist.md §3 T1 に置換 |
| 更新 doc | `docs/system-architecture.md` §2.4 | axum-video-server.md への blockquote cross-ref |
| 更新 doc | `docs/ui-architecture.md` §5 preview | 同上 |

### 起票済 deferred follow-up issue

- [#670](https://github.com/Idios/kobutachan-allaganeye/issues/670): axum video server 改善 (token 失効 API + graceful shutdown)、`task` / `l2a-gui` / `deferred` / `P3-low`、parent #618
- [#671](https://github.com/Idios/kobutachan-allaganeye/issues/671): E2E test 自動化 feasibility 検討 (Playwright / Tauri mock driver)、`task` / `l2a-gui` / `deferred` / `P3-low`、parent #484

### Round 1 review (Idios `relaxed-yalow-564511`) 5 件指摘 → fix 完了 (commit `1335861`)

1. **Critical** (jq field): `.start`/`.end` → `.start_time`/`.end_time` (実 schema は `docs/metadata-spec.md` §Match line 90-91 / `allaganeye/metadata_types.py:30-31`)
2. **Important** (T1.2 CLI smoke): `allaganeye.bat --version` を T1.2 に追加し「CLI smoke + GUI 起動」化 ([#527](https://github.com/Idios/kobutachan-allaganeye/issues/527) 別 exe 方式整合)
3. **Minor** (T1.6 metadata path): `metadata.json` 出力先を blockquote で明示 + `$METADATA_JSON` 変数化
4. **Minor** (T2.3 alt expected): #574 実装後 / 未実装時 (手動 drop) の 2 経路で記述
5. **Minor** (§5 seek p95): 30 random seek + P95 (28 番目) + DevTools record で計測条件を pin

### close-issue 残作業 (compact 後の次セッション)

- `/close-issue 618` 起動: 受け入れ条件 5/5 (うち #5 plan ID literal は Idios review で容認済 △→○ 振替)。詳細手順は plan の Execution Status section 参照
- `/close-issue 484` 起動: 受け入れ条件 4/5 (1 件 △ T1/T2 実機実施はリリース直前)。skill 内で抽出 + 検証
- worktree cleanup: project policy で Idios 手動 (`.claude/worktrees/dazzling-mestorf-10914f/` 削除)

### Final reviewer (subagent-driven-development) Approve メモ

3 件 Minor (post-merge polish、blocker でない):

- M1: `docs/axum-video-server.md:233-234` の anchor format (system-architecture.md / ui-architecture.md) は GitHub-style で生成済だが、render 結果は post-merge で要確認
- M2: `docs/release-process.md:96` と `:98` の "Idios 実機で全件実施" 表現が部分重複 (line 96 = 実行 gate、line 98 = doc 新設 gate で意図は分かれる)
- M3: `docs/l2-e2e-checklist.md:258` §6 成功基準で T2 skip 条件が `#523` のみ言及、`#574` も明示すると ambiguity 削減 (parenthetical "(#574 未マージ時は手動 drop 代替)" 追加可能)

これらは別 PR で polish 可能 (本 PR スコープ外)。
