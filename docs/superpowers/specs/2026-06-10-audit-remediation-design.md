# 2026-06-10 全体監査 remediation 設計

## 背景・目的

2026-06-10 の全体監査 ([`docs/audits/2026-06-10-full-audit.md`](../../audits/2026-06-10-full-audit.md)、以下「監査レポート」) で約 60 件の findings (P1×8 / P2×40 / P3 多数) と横断的な構造パターン 4 つを検出した。本設計はその **対策 (remediation)** と **再発防止 (prevention)** のプログラム全体を定義する。finding ID (P1-1 等) は監査レポートの定義を参照する。

## 決定事項 (2026-06-10 Idios 確認済み)

| 論点 | 決定 |
| --- | --- |
| 即時処置 2 件 | 実施済み (park branch 2 本 push / red test stash 退避) |
| v0.3.0 との関係 | **P1 を v0.3.0 リリースゲート化**。P2 は並行消化分と v0.3.1+/deferred に振り分け。再発防止は v0.3.0 サイクル内に導入 |
| issue 粒度 | **PR 単位グループ** (1 issue = 1 PR で消化できる作業単位、見込み 14-18 本) |
| 再発防止の採用機構 | CI/test guard 強化 + skill 改修 + doc SSoT 規約の 3 本 (定期 full audit は不採用) |
| プログラム構造 | **案 A: 優先度駆動 Wave 方式** (Wave 1 = ゲート + 基盤 → Wave 2 = P2 テーマ → Wave 3 = 棚卸し + P3) |
| 本 spec + 監査レポートのコミット | Wave 1 最初の PR に同梱 (option b、2026-06-10 確定) |

## 追跡方法

- 親 issue は作らない (#753 で実証された「親 issue 本文が腐る」回避)。**本 spec が正**で、各 issue 本文の冒頭に本 spec への参照行を 1 行入れる
- 新規 label は追加しない (L3 spec §5 の規約に従う)。優先度 label (P1-high 等) と既存 label のみ使用
- 進捗は issue の open/close で追跡し、Wave 完了時に本 spec の該当節へ完了日を追記する

## 全体構造

```text
Wave 1 (v0.3.0 リリースゲート + 再発防止基盤): G1-G5 + N1-N3 ... 8 PR、ほぼ全部並列可
Wave 2 (P2 テーマ消化): W1-W6 ... 5-7 PR、Wave 1 完了後に並列
Wave 3 (issue 棚卸し + P3 batch): PR なし、gh 操作中心 (bulk は実行直前に再確認ゲート)
```

v0.3.0 リリース条件への追加: **Wave 1 の全 issue クローズ** (= P1 全消化)。Wave 2 は v0.3.0 に間に合った分だけ取り込み、残りは v0.3.x へ繰り越し可。Wave 3 はリリースと独立。

## Wave 1 詳細

### G1: test marker 配線修正 + marker 規約 meta-test

- 対応: P1-3 (+ 再発防止)
- 変更箇所: `tests/test_v030_baseline_regression.py` / `tests/conftest.py` / 新規 `tests/test_marker_conventions.py`
- 設計:
  - `test_v030_baseline_regression.py` に `pytestmark = [pytest.mark.slow, pytest.mark.slow_detect]` を追加 (他 slow ファイルと同形)。docstring の「CI default deselect」誤認記述も訂正
  - conftest の `_ffmpeg_interval` cooldown は現行 (`slow` のみ参照) を維持する — enforcement hook が「`slow_*` ⇒ `slow`」を collection 時に強制するため、拡張は冗長 (2026-06-10 plan で確定)
  - enforcement (新規): `pytest_collection_modifyitems` hook (tryfirst) が全 collected item の marker を検査し、`slow_probe/slow_detect/slow_pipeline/slow_gpu` を持つのに `slow` を持たない item があれば UsageError で collection を fail させる。純関数 `slow_submarker_violations()` は unit test で検証。testing-guide.md:33 の「slow = サブマーカーのスーパーセット」契約を機械化する (実装時にソーススキャン案から hook 方式へ変更 — runtime enforcement の方が網羅的、2026-06-10 plan 実行で確定)
- 受け入れ条件案: `pytest -m slow --collect-only` が v030 baseline 4 テストを select する / bare `pytest --collect-only` が select しない / meta-test が `slow_detect` 単独付与の fixture コードで fail することをユニットで実証
- 検証: Python path チェック (ruff / pyright / pytest)。実動画実行は不要 (配線のみ)

### G2: GUI detect 中断の kill 配線

- 対応: P1-1
- 変更箇所: `gui/src/screens/DetectingScreen.tsx` / `gui/src-tauri/src/lib.rs` (run id) / `gui/src/__tests__/flow.integration.test.tsx`
- 設計:
  - cancelling phase で `kill_tracked_processes` を invoke してから `CANCEL_CONFIRMED` に遷移
  - detect イベントの run 識別: `start_detect` 起動ごとに run id を払い出し、`detect-progress` / 完了イベントに含める。フロントは現在 run の id 以外を無視 (越境イベント遮断)。具体的な払い出し方式 (戻り値 vs payload) は実装計画で確定
  - 「detecting cancel triggers kill_tracked_processes (#756)」と名乗りながら別経路を検証している flow.integration の describe を修正し、実際に中断クリック → kill invoke を検証するテストを追加
- 受け入れ条件案: 中断クリックで `kill_tracked_processes` が invoke される (unit) / 中断後に旧 run のイベントが UI に反映されない (unit) / 実機: 中断後に ffmpeg プロセスが残らない (Idios 実機検証)
- 検証: GUI path チェック (lint / typecheck / test / build / cargo check) + **Tauri 実機検証を AskUserQuestion で依頼** (Iron Law 6)

### G3: GUI metadata 境界検証 + load エラー可視化

- 対応: P1-2、P2-13、P2-17
- 変更箇所: `gui/src/screens/PreviewScreen.tsx` / `gui/src/state/metadataStore.ts` / `gui/src/screens/DetectingScreen.tsx` or `CompleteScreen.tsx` / `gui/src-tauri/src/lib.rs` (apply guard)
- 設計:
  - 境界編集 (nudge / TC 入力 / FrameStrip) に相互クランプを入れ、apply 前 validation で `end_time > start_time` を強制 (UI ブロック)。Rust `apply_changes` にも同 guard を追加し AppError で返す (多層防御)
  - `loadErrorState` の表示先を配線: detect 完了後の load 失敗は error ルーティング (既存の専用 error view)、CompleteScreen の空状態にも loadErrorState を表示。`restore()` の load 失敗も成功扱いしない
  - `normalizeForPersistence` で `start_display`/`end_display`/`duration_display` を `utils/time.ts` の既存フォーマッタで再生成 (CLI 形式と同一仕様)
- 受け入れ条件案: end<=start が UI でブロックされる / 不正値が Rust 側でも reject される / load 失敗時にエラー内容が画面に出る / apply 後の display 文字列が数値と一致する
- 検証: GUI path チェック + Tauri 実機検証依頼

### G4: #805 段階 1 — trailing drop の痕跡記録 + escape hatch

- 対応: P1-4、P2-2 (P2-1 の audio corroboration は `AUDIO_FROZEN=True` の間 no-op のため**見送り**、#805 に記録)
- 紐づけ: **既存 #805** (新規 issue なし)。#805 へ「段階 1 を v0.3.0 で実施、段階 2 (非破壊化) は本 issue で継続」の triage コメントを先に投稿
- 変更箇所: `allaganeye/detection/warnings.py` / `allaganeye/video/detector.py` / `allaganeye/config.py` + `cli.py` (flag) / `docs/metadata-spec.md` / `docs/cli-spec.md`
- 設計:
  - `WARNING_CODES` に `post_match_trailing_dropped` を追加し、drop 時に `warnings[]` へ `{code, context: {start, end}}` を記録 (`MetadataWarning` は forward-compat 設計済みのため schema_version bump 不要、GUI zod は unknown code 受容済み)
  - escape hatch: `--keep-trailing` flag (split / detect 共通、`SplitConfig.keep_trailing: bool = False`)。True なら `_drop_post_match_trailing` を skip。「released path を触る分岐は明示 gate に」教訓への整合
  - doc: cli-spec へ flag 追記、metadata-spec の warning code 表へ追記 (同 PR 内)
- 受け入れ条件案: drop 発生時に warnings[] へ記録される (unit) / `--keep-trailing` で drop が無効化される (unit) / v0.3.0 baseline 5 本の detect projection (matches+gaps) が bit-exact 維持 (G1 修正後の slow gate で実証) / warnings field 追加が compare-baseline.py の projection に影響しないことを確認
- 検証: Python path チェック + **実動画 baseline gate (`pytest -m slow_detect`) + Idios 実機確認を依頼** (detector.py 変更のため Iron Law 6 実機 trigger に該当)

### G5: doc P1 修正 (即時分のみ)

- 対応: P1-5、P1-6、P1-7
- 変更箇所: `docs/cli-spec.md` (include/exclude 基数、intel 行) / `CLAUDE.md` (音声昇格 frozen 化、war_room.npz、未来形記述)
- 設計: P1 級の誤りのみ最小修正。CLAUDE.md モジュール表更新等の P2 doc drift は W6 (SSoT 規約適用とセット) に残す
- 受け入れ条件案: 3 点の記述が実装と一致 / markdownlint pass
- 検証: `bash scripts/check-markdownlint.sh`

### N1: CI/インフラ guard

- 対応: P3 (stale branch pin 2 件、test_*.sh 未配線)
- 変更箇所: `.github/workflows/ci.yml` / `.github/workflows/check-pr-checklist-test.yml` / `scripts/cleanup-claude-branches.sh`
- 設計:
  - ci.yml の hook-test 系 job に `tests/scripts/test_check_error_hint_drift.sh` 等 3 本の実行 step を追加
  - `check-pr-checklist-test.yml` の push trigger を `develop-*` パターン化
  - `cleanup-claude-branches.sh` の merged 判定を `origin/develop-*` 走査に一般化 (現状 develop-0.2.0 固定で新 branch がいつまでも掃除されない)
- 受け入れ条件案: CI green / sh test 3 本が CI ログに出る / develop-0.3.0 への push で checklist-test が走る
- 備考: GitHub Actions の既知の罠 (`${{ matrix.* }}` × step shell、pwsh redirect) は memory/feedback 既録のテンプレに従う
- **マージ後アクション (stale worktree 掃除)**: ① 修正済み `cleanup-claude-branches.sh` を dry-run → 対象一覧確認 → apply (merged `claude/*` branch 削除) → ② `scripts/cleanup-worktrees.sh` を dry-run → 確認 → apply (orphan worktree 削除)。対象見込み 9 本 (lane-v-pr1〜5 / l2-workflow-458・459 / pr657b-rust-stdout / hopeful-herschel)。未 merge branch (L3 park 3 本: l3-809-pass1-region-wiring / l3-p2-region-detection / l3-vtuber-replan、現役 v030-wave-c) は merged/orphan 判定で自動保護され、dirty worktree は `git worktree remove` の既定動作で拒否されるため安全。**3 件以上の削除のため apply 前に Iron Law 2 の一覧提示 + AskUserQuestion 確認を行う**

### N2: skill 改修 (追跡切れ防止)

- 対応: P2-39 類型 (PR 本文の追跡予定が未起票) / P2-33 (version bump grep) / P3 (skills broken link 14 件)
- 変更箇所: `.claude/skills/close-issue/SKILL.md` / `.claude/skills/release/SKILL.md` / skills 各所の相対リンク
- 設計:
  - close-issue: クローズ前チェックに「対象 issue を閉じた PR (および同 PR の本文・レビュー) に『別 issue で追跡』『follow-up』等の宣言があれば、行き先 issue 番号の実在を確認。未起票なら起票提案」を追加
  - release: deferred レビューに「open issue 本文と直近コメント・spec の矛盾チェック (本文鮮度)」「リリース区間内に not_planned close された issue をコード内参照 (`wired in #N` 等) から検出し残タスクの行き先確認」を追加。version bump の grep 対象に `*.json` (tauri.conf.json / package.json) を追加
  - skills の `../../docs/` → `../../../docs/` 一括修正 (14 件)
- 検証: **skill 改修 PR は empirical-prompt-tuning protocol** (fresh subagent dispatch + 構造化 reflection、Self-Test Report 記載) に従う (CLAUDE.md §skill 改修ワークフロー)

### N3: doc SSoT 規約の明文化 + release gate 追記

- 対応: 再発防止 (doc 値複製 drift の構造的根絶)。**W6 の前提**
- 変更箇所: `docs/coding-conventions.md` (または適切な既存 doc — 追加前に `grep -n '^## '` で全 section を確認し重複回避、memory 教訓) / `docs/release-process.md`
- 設計:
  - SSoT 規約: 「仕様値・定数・挙動説明の正は 1 doc (cli-spec / metadata-spec / 実装 docstring のいずれか) に置き、他 doc はリンク参照する。CLAUDE.md は索引として要約可だが数値を書く場合は出典リンク併記」を規約化。違反の代表事例 (workers 24 が 7 箇所複製) を背景として記載
  - release-process のリリース前チェックに「監査 P1 (本 spec Wave 1) 全クローズ確認」を追記 (既存節との重複を grep 確認の上)
- 検証: markdownlint

### Wave 1 の PR なしアクション

| アクション | 内容 |
| --- | --- |
| #809 受け入れ条件追記 | P1-8 の順序依存 gate 制約 (「scorebar 局在化 consumer の同時/先行 wiring、最低でも region ≠ FULL_FRAME 時は trailing drop 無効化」「`_CACHE_SENSITIVE_FILES` へ capture_region.py 追加」) を issue 本文に追記 |
| #805 triage コメント | 「段階 1 (G4) を v0.3.0、非破壊化 (段階 2) は本 issue 継続。audio corroboration は frozen 解除後に再評価」を投稿し、優先度 label を付与 |
| stale worktree 掃除 | **N1 マージ後**に N1 §マージ後アクション の手順 (branches → worktrees の 2 段、各 dry-run → Iron Law 2 確認 → apply) で実施。見込み 9 本 |

## Wave 2 詳細 (テーマ概要 — 詳細は各実装計画で)

### W1: export/CLI 整合

- 対応: P2-7 / P2-8 / P2-9 / P2-10 / P2-11 / P2-20 / P2-40 + export 系 P3 (concurrency 検証、partial file 掃除、stderr_tail、dead param、stale comment、`{idx}` 衝突検査)
- 骨子: export command を split/detect と同じ `except AllaganEyeError` → exit code マッピングに収める / json モード突入時に stdout reconfigure + stdin buffer 読み / skipped 計上 / output_dir mkdir / debug-brightness interval guard (exit 5) / `{start}` を Python 側 H-MM-SS に統一 (GUI 表示と一致させる)
- 注意: exit code 体系の変更は cli-spec / output-spec の同時更新を伴う (W6 と重なる箇所は W1 側で正を書く)

### W2: GUI export/cancel 安定化

- 対応: P2-14 / P2-15 / P2-16 + cancel 系 P3 (listen leak、cancelRequestedRef、ConfirmExit 文言)
- 骨子: reducer に `cancelling + PROGRESS_COMPLETE → completed` 遷移追加 / start_export に bounded stderr tail drain (start_detect と同型) / `expect` を stdout 先取りで排除

### W3: GUI metadata/polish

- 対応: P2-18 / P2-19 / P2-21 + GUI 系 P3 (mtime 順序、sample nudge、拡張子整合、register_video 累積、capabilities 過剰権限、未使用依存)
- 骨子: name/type_override の in-memory 保持 (apply 後消失の解消) / load 系の BOM strip / thumbnail Semaphore の `OnceLock` static 化 / mtime を read 前に取得
- 注意: detect-progress 間引き等の本格 responsiveness は W3 でやらず、**#670 に本監査の分析 (thumbnail 並列 + イベント無間引きが主因候補) を追記して #670 実装で消化**

### W4: core 堅牢化

- 対応: P2-3 / P2-4 / P2-6 + core 系 P3 (GPU 診断ログ、lo-probe skip、probe duration parse、scorebar logger、format.py dead module 整理)
- 骨子: v2 decode read に全体 deadline (watchdog) / `_borderline_pseudo_regions` の合計長 cap — **cap 値は実測 (待機画面が長い実録画で Pass 2 probe 数を計測) してから決定** / saturated-run・emblem 計算を共有ヘルパに抽出 (capture_region との複製解消) / `detection/format.py` は private 版を寄せて import に置換 or 削除
- 検証: detector.py 変更のため実動画 baseline gate (bit-exact) + 実機検証依頼が必須

### W5: テスト配線拡充

- 対応: P2-22 / P2-23 / P2-24 + test 系 P3 (ErrorModal axe、flow mock default、regression_330 lazy 化、baselines README stale 参照)
- 骨子: split SHA-256 照合の slow test 追加 (detect Class A と同型) / wire e2e の docstring・skip guard 修正 + SIGINT dead test の扱い決定 (削除 or 明示 xfail) / VTuber ground truth ±10s 照合を pytest 化 (`ALLAGANEYE_VTUBER_VIDEO_DIR` 新設、`slow` + `slow_detect` 両 marker — G1 規約準拠)

### W6: doc 一括再同期 (N3 の SSoT 規約適用)

- 対応: P2-25〜P2-35 の残り (G5 で 3 点先行済み) + doc 系 P3
- 骨子: workers 32 / Pass 1 チャンク方式 / #576 記述 / GPU default auto / CLAUDE.md モジュール表・L2 リリース済み・L3 VTuber 保留 / scorebar-detection-design の #803/#797/#811 反映 / system-architecture・quickstart の #752/#761 反映 / versioning 3 箇所 / cli-spec detect・export 節 / developer-setup の BtbN LGPL 手順昇格 / gui-development CI 表 ほか
- 分割可: 「CLI/コマンド仕様系」と「アーキテクチャ説明系」の 2 PR に分けてよい (issue は 1 本)
- 規約: 修正時に SSoT 規約 (N3) を適用し、複製値はリンク化する

## Wave 3 詳細 (issue 棚卸し + P3 batch)

PR を伴わない gh 操作。**3 件以上の編集・起票・クローズを伴うため、実行直前に対象一覧を提示して AskUserQuestion で再確認する** (Iron Law 2)。

| 対象 | アクション | 根拠 |
| --- | --- | --- |
| #412 | close (前提消滅) or 全面書き直し — **PR #323 のコードが系譜から消失している事象の周知 + 再 land 要否判断とセット** | P2-36 |
| #518 | close して残作業 (emitter/GUI 表示) を task として書き直し、または本文 rescope。G4 が warning emitter の実例第 1 号になる | 棚卸し F8 |
| #753 | checklist を現状に同期 (CLAUDE.md 更新済み・サンプル VOD 入手済みのチェック、label 新設禁止の注記、#480 P1 完了の反映) | 棚卸し F7 |
| #670 | 本文に v0.3.0 re-scope の経緯 + 本監査の主因候補分析 (thumbnail 並列 / イベント無間引き) を追記 | 棚卸し F6、P2-21 |
| #804 | deferred 付与 (v0.3.x 扱い) か v0.3.0 必須かを明示判断 | 棚卸し F11 |
| #326 | re-triage (着手条件「L2 完了後」成立済み) | 棚卸し F9 |
| #376 | 維持で可。実装時の両義性 (`split -v`=verbose) を本文に注記 or wontfix 判断 | 棚卸し F12 |
| #765 | 参照先 #762 close に伴う再評価 checkpoint の記述更新 | 棚卸し |
| #327 (audio frozen) | P2-1 (corroboration 案) と P2-5 (メモリ) を解凍条件の検討材料として追記 | P2-1、P2-5 |
| 新規: #762 後継 | [task] QSV/AMF decode hwaccel の扱い確定 (wire する or wontfix を code コメント + CLAUDE.md + release-process から参照解消) | P2-37 |
| 新規: system_info | [bug] wmic 非搭載環境で GPU vendor 検出が全滅 (要実機確認、`Get-CimInstance` fallback 案) | P2-12 |
| 新規: typer pin | [task] typer<0.25 / click<8.4 pin の恒久対応 (P3-low) | 棚卸し F13 |
| 新規 (guard repo): | [bug] VTuber VOD FP 3 点 (短署名衝突 / moov>10MB buffer / cp932 crash) — kobutachan-allaganeye-guard 側 | P2-39 |
| P3 batch | Wave 1/2 の PR に同梱しきれなかった P3 をテーマ別 batch issue (deferred、上限 3 本) にまとめるか見送りを判断 | P3 全般 |

## 検証方針 (横断)

| 変更 path | 必須チェック | 追加検証 |
| --- | --- | --- |
| Python (G1/G4/W1/W4/W5) | `ruff check .` / `ruff format --check .` / `pyright` / `pytest` | detector.py 変更 (G4/W4) は実動画 baseline gate (`pytest -m slow_detect`、G1 修正後) + AskUserQuestion で実機検証依頼 |
| GUI (G2/G3/W2/W3) | `npm run lint` / `typecheck` / `test` / `build` / `cargo check` | Tauri 実機起動の検証を AskUserQuestion で依頼 |
| docs (G5/N3/W6) | `bash scripts/check-markdownlint.sh` | — |
| CI/workflows (N1) | workflow 構文 + CI 実走確認 | — |
| skills (N2) | empirical-prompt-tuning protocol + Self-Test Report | — |

全 PR で Iron Law 6 Pre-flight (Step 0-5、`/codex:adversarial-review` 含む) を実施。PR 作成後は `/iterate-review` で review-fix ループ。

## 順序依存・リスク

- **N3 → W6**: SSoT 規約が doc 一括修正の前提
- **G1 → G4/W4**: baseline gate が正しく回ることが detector 変更検証の前提
- **G3 → W3**: 同ファイル (metadataStore.ts) のため Wave 順で直列化
- **G2 → W2**: 同領域 (lib.rs / cancel path) のため G2 先行
- detector.py は G4 と W4 で 2 回触る (Wave 跨ぎのためコンフリクトなし、レビュー 2 回のコストのみ)
- W6 と W1 で cli-spec が重なる: exit code 等 W1 が実装を変える箇所は W1 側 PR で doc も書き、W6 は W1 マージ後に残りを同期
- リスク: G4 の warnings[] 追加が将来 schema validation を厳格化した consumer を壊す可能性 → `MetadataWarning` の forward-compat 規約 (unknown code 受容) を G4 のテストで pin する

## 新規 issue 起票一覧 (Iron Law 2 確認用)

起票実行前にこの表で最終確認する。prefix・本文は `/create-task` (issue-policy.md) に従い、本文冒頭に本 spec への参照を入れる。

| # | タイトル案 | prefix | label 案 | Wave |
| --- | --- | --- | --- | --- |
| 1 | v0.3.0 baseline regression が slow marker 規約から漏れ documented コマンドで実行されない → #812 | bug | P1-high | 1 (G1) |
| 2 | GUI: detect 中断がプロセスを kill せず二重 detect が可能 → #813 | bug | P1-high, l2a-gui | 1 (G2) |
| 3 | GUI: OUT<IN を apply でき metadata.json が読込不能 + load エラー非表示 → #814 | bug | P1-high, l2a-gui | 1 (G3) |
| 4 | cli-spec / CLAUDE.md の P1 級 drift 修正 (export index 基数 / intel / 音声 frozen) → #815 | doc | P1-high | 1 (G5) |
| 5 | CI guard: tests/scripts/*.sh 配線 + branch pin の develop-* 化 → #816 | task | P2-medium | 1 (N1) |
| 6 | skill 改修: close-issue / release に追跡切れ防止チェック + version grep *.json + broken link 修正 → #817 | task | P2-medium, l2-workflow | 1 (N2) |
| 7 | doc SSoT 規約の明文化 + release gate に監査 P1 クローズ確認を追加 → #818 | doc | P2-medium | 1 (N3) |
| 8 | export/CLI 整合 (エラー枠組み / encoding 自衛 / skipped / output_dir / interval guard / {start}) | bug | P2-medium | 2 (W1) |
| 9 | GUI export/cancel 安定化 (cancelling スタック / stderr drain / expect race) | bug | P2-medium, l2a-gui | 2 (W2) |
| 10 | GUI metadata/polish (name 消失 / BOM / mtime 順序 / thumbnail 並列) | bug | P2-medium, l2a-gui | 2 (W3) |
| 11 | core 堅牢化 (v2 read timeout / pseudo-region cap / saturated-run 共有ヘルパ) | bug | P2-medium | 2 (W4) |
| 12 | テスト配線拡充 (split SHA gate / wire e2e / VTuber ground truth pytest 化) | task | P2-medium | 2 (W5) |
| 13 | doc 一括再同期 (SSoT 規約適用、P2-25〜35 残り + P3 doc 系) | doc | P2-medium | 2 (W6) |
| 14 | QSV/AMF decode hwaccel の扱い確定 (#762 後継) | task | P3-low | 3 |
| 15 | system_info: wmic 非搭載環境で GPU vendor 検出が全滅する | bug | P2-medium, deferred | 3 |
| 16 | typer<0.25 / click<8.4 pin の恒久対応 | task | P3-low, deferred | 3 |
| 17 | (guard repo) VTuber VOD FP 3 点 (短署名衝突 / moov buffer / cp932) | bug | — | 3 |

既存 issue 紐づけ: G4 → #805 / #670 追記 / #809 AC 追記 / #327 追記 / #412・#518・#753・#326・#376・#765・#804 は棚卸しアクション。

## スコープ外 (明示)

- P2-1 audio corroboration: `AUDIO_FROZEN=True` の間 no-op のため見送り (#805 と #327 に記録)
- P2-5 audio scan メモリ: 同上、#327 解凍条件に記録
- 定期 full audit の release gate 化: 不採用 (決定事項)
- #481 (minimap) / #670 (responsiveness) の実装そのもの: 既存の v0.3.0 active set として本プログラムの外 (ただし #670 へ分析結果を提供)
- VTuber pillar 本体 (#809/#810 の wiring): park 継続。本プログラムは制約の明文化 (P1-8) のみ行う

## 完了の定義

- Wave 1: 新規 7 issue クローズ + G4 PR マージ (#805 自体は段階 2 のため open 継続) + PR なしアクション 3 件 (#809 追記 / #805 triage / worktree 掃除) 完了 → v0.3.0 リリースゲート解除
- Wave 2: 6 issue クローズ (v0.3.0 に間に合わない分は v0.3.x へ繰り越し可、繰り越し時は本 spec に追記)
- Wave 3: 棚卸し表の全行に決着 (実施 or 明示的見送り) + 新規 issue 起票完了
