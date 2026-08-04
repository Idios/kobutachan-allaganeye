# 2026-06-10 全体監査レポート (Fable)

## メタ情報

- 実施日: 2026-06-10 / モデル: Claude Fable 5
- 対象: branch `develop-0.3.0` (HEAD: ef26bd9)
- 手法: 6 観点並列監査 (コア検知 / CLI・export・インフラ / GUI / テスト / ドキュメント / issue トラッカー) + 主セッションによる P1 全件のコード再検証
- 対策設計: [`docs/superpowers/specs/2026-06-10-audit-remediation-design.md`](../superpowers/specs/2026-06-10-audit-remediation-design.md)
- 表記: `[確実]` = コードを読んで論理的に確認済み / `[要検証]` = 実機・実動画でないと断定不可

## 即時処置 (2026-06-10 実施済み)

| 処置 | 内容 |
| --- | --- |
| park branch 保全 | `claude/l3-809-pass1-region-wiring` (22 commits) と `claude/l3-vtuber-replan` が origin 未 push だったため push (PR なし、保全のみ) |
| red test 退避 | `tests/test_config.py` の未コミット diff (`region_blackout_threshold` テスト 2 件、config.py 側 field 未実装で必ず fail) を `git stash push -m "audit 2026-06-10: region_blackout_threshold red tests (park #809 leftover)"` で退避。bare `pytest` を green に復旧 |

## P1: 重大 (すべて再検証済み・確実)

### コード

| ID | 問題 | 場所 |
| --- | --- | --- |
| P1-1 | GUI の detect「中断」がプロセスを kill しない。phase 遷移のみで Python + 最大 32 本の ffmpeg は走り続け、drop 画面から同一動画への二重 detect も起動できる (detect イベントに run 識別子がなく越境受信もありうる)。`kill_tracked_processes` の production 呼び出しは ExportScreen と ConfirmExitModal のみ | `gui/src/screens/DetectingScreen.tsx:314-321` |
| P1-2 | OUT < IN の境界編集を無検証で apply でき、metadata.json が GUI 自身で読めなくなる。書き込みは素通し、次回 load は zod refine で reject → load エラーは非表示 (P2-13) のため「No metadata」の空画面になり GUI 内に復旧手段なし | `gui/src/screens/PreviewScreen.tsx`、`gui/src/state/metadataStore.ts:152-176`、`gui/src/types/metadata.schema.ts:29-31` |
| P1-3 | v0.3.0 baseline regression がマーカー配線ミスで「回したつもりで回らない」。4 テストが `slow_detect` 単独付与で、addopts `-m 'not slow and not baseline_regen'` は除外せず (サンプル動画がある環境で bare pytest が数時間級 detect を実行)、逆に docs 推奨の `pytest -m slow` / `pytest -m "slow or baseline_regen"` では deselect される。conftest の GPU cooldown (`slow` のみ参照) も効かない | `tests/test_v030_baseline_regression.py:28,62,143,181`、`pyproject.toml:53`、`tests/conftest.py:136` |
| P1-4 | #805 の trailing drop が metadata.json に一切の痕跡を残さない。記録は verbose 用 stats のみで `warnings[]` は常に空 (`detection/warnings.py` の scaffold 未配線)。消えた試合の start/end が残らず手動復旧も不可。`MetadataWarning` は forward-compat 設計済みのため warning code 追加だけで schema bump 不要 | `allaganeye/video/detector.py:1985-1992`、`allaganeye/detection/warnings.py:43-59` |

### ドキュメント

| ID | 問題 | 場所 |
| --- | --- | --- |
| P1-5 | export `--include`/`--exclude` を「0 始まり」と記載、実装は metadata の 1 始まり `index` と照合。doc どおり `--exclude 0` しても先頭 match は除外されず誤った match 集合が silent に書き出される | `docs/cli-spec.md:353-354` ↔ `allaganeye/commands/export.py:149` |
| P1-6 | `--gpu-vendor intel` が「exit 5 (#550 で実装予定)」のまま。実装済み (#550/#582) で、CLAUDE.md・tuning-guide と矛盾 | `docs/cli-spec.md:56` ↔ `allaganeye/cli.py:130-139` |
| P1-7 | CLAUDE.md が「音声昇格」を現役機能として記述。実際は `AUDIO_FROZEN: Final[bool] = True` (#327) で Fanfare スキャンは常にスキップ。`audio/refs/` 行も `war_room.npz` (#306 同梱済) 未反映、「WR 参照 (#301) 同梱後に」の未来形記述も古い | CLAUDE.md §検知アルゴリズム ↔ `allaganeye/audio/__init__.py:48` |

### 設計上の地雷 (実装前に固定すべき制約)

| ID | 問題 | 場所 |
| --- | --- | --- |
| P1-8 | #809 の wiring 順序依存。`capture_region.py` は production import ゼロ (pure additive で安全) だが、#809 (Pass 1 領域輝度適応) だけが先に wire されると、scorebar 系 probe (絶対座標 Primary + 中央跨ぎ必須 Rescue) は full-frame 前提のままなので VTuber 録画で (a) 全暗転が `non_fl` 分類で除去、(b) trailing drop が確定 False 連発で最終試合喪失、が同時に起きる。#809 の受け入れ条件に「scorebar 局在化 consumer の同時/先行 wiring、最低でも region ≠ FULL_FRAME 時は trailing drop 無効化 gate」の明記が必要 | `allaganeye/video/capture_region.py`、`allaganeye/video/detector.py:943-947,1176-1182` |

## P2: 重要な改善

### コア検知パイプライン

- **P2-1** [確実] trailing drop が単一検出器に全依存: classify 側は majority vote + re-probe + audio の多重防御なのに drop 側は `_has_scorebar_v2` 単発のみ (`detector.py:1977`)。`audio_hits` 流用で「窓内に Fanfare ピークがあれば keep」を追加可能だが、`AUDIO_FROZEN=True` の間は no-op (対策設計では見送り、#805 に記録)
- **P2-2** [確実] trailing drop に opt-out gate がない: 「released path を触る分岐は明示 gate に閉じ込める」教訓に対する唯一の例外 (`detector.py:413-421`)。escape hatch (`--keep-trailing` 等) が必要
- **P2-3** [確実] v2 decode path の read に timeout 保護がない: legacy は `subprocess.run(timeout=)` 保護があったが、v2 の `stream.read(_FRAME_SIZE)` は無期限ブロック可能で ffmpeg ハング時に detect 全体が永久停止する堅牢性 regression (`detector.py:644-653`、`gpu_detector.py:666-676`)
- **P2-4** [要検証] `_borderline_pseudo_regions` (#576 A5) にコスト上限がない: brightness 15-55 の待機画面が長時間続く録画で Pass 2 probe が非有界に増える (1h で ~14,400 ffmpeg 起動の試算) (`detector.py:1548-1578`)
- **P2-5** [要検証] audio scan の全長一括処理は 8h 級録画でピーク十数 GB のメモリ (`audio/scan.py:66`、`audio/features.py:98-109`)。frozen 中は実害なし、解凍前にチャンク化が必要
- **P2-6** [確実] `capture_region.py` が detector の saturated-run / emblem 計算ロジックを複製しており、片側修正で「OBS parity」が silent に壊れる構造 (`capture_region.py:199-299` ↔ `detector.py:1140-1238`)

### CLI / export

- **P2-7** [確実] `allaganeye export` だけが cli.py のエラーハンドリング枠組みの外: `AllaganEyeError` 未捕捉で raw traceback + exit 1。`--json` モードで summary 終端行が emit されず wire 契約が破れる (`commands/export.py:118-249`、`cli.py:588-625`)
- **P2-8** [確実] JSON wire の Python 層 encoding 自衛がない: `sys.stdout.reconfigure(encoding="utf-8")` 相当がなく Rust 側の `PYTHONIOENCODING` 注入頼み。CLI 単体 + cp932 console で非 ASCII path が壊れる (`export/wire.py:24`、`commands/export.py:48`)
- **P2-9** [確実] `ExportSummary.skipped` がどの経路でも increment されず常に 0 (`export/schema.py:43`)
- **P2-10** [確実] export は output_dir を検証も mkdir もしない (split/detect と非対称)。`-o` 先が無いと全 match ffmpeg fail → exit 1 (doc は exit 2 と主張 = doc 側も誤り)
- **P2-11** [確実] `debug-brightness --interval 0` (または負値) で `_generate_timestamps` が無限ループ → hang/OOM (`commands/debug_brightness.py:48` → `detector.py:775-782`)
- **P2-12** [要検証] system_info の Windows probe が `wmic` 依存: wmic 非搭載の Win11 24H2+ クリーン環境で AMD/Intel-only 機の vendor 検出が全滅し GUI export が libx264 固定に silent degrade (`system_info.py:99` ほか)
- **P2-40** [要検証] export の cancel 応答性: stderr `readline()` ブロック依存 + timeout 無しで ffmpeg 無出力 stall 時に worker が永久待ち。Windows CLI では `f.result()` ブロック中に Ctrl+C ハンドラ実行が遅延しうる (`export/ffmpeg_runner.py:119-126`、`commands/export.py:184-190`)

### GUI

- **P2-13** [確実] `metadataStore.loadErrorState` を表示する UI が存在せず、load 失敗 (zod 違反/JSON 破損/BOM) が無言で「No metadata」になる (`metadataStore.ts:280`)。P1-2 と連鎖
- **P2-14** [確実] export reducer: `cancelling` 中の `PROGRESS_COMPLETE` が未処理で「中断中…」のまま永久スタック。復帰ボタンも disabled でアプリ再起動が必要 (`screens/reducers/export.ts:34-37`)
- **P2-15** [確実] `start_export` が stderr を pipe したまま drain しない: 大量 stderr で子がブロックし export ハングの可能性 + crash 時 traceback が失われる。`start_detect` は tail 収集しており非対称 (`lib.rs:2777`)
- **P2-16** [確実] `start_export` の `expect("tracked just inserted")` がユーザー cancel との race で panic しうる (正常 cancel が「アプリ内部エラー」報告に化ける) (`lib.rs:2849-2854`)
- **P2-17** [確実] 境界編集 apply 後も `*_display` 文字列が再計算されず、数値と表示が矛盾した metadata.json が永続化される (`metadataStore.ts:163-173`)
- **P2-18** [確実] 試合名 (name) 編集が apply で黙って消える (normalize が name を strip + `clearDraft()` でセッション内からも消失) (`metadataStore.ts:184-211`)
- **P2-19** [確実] `load_metadata` が UTF-8 BOM 付き metadata.json を「invalid JSON」で拒否: CLAUDE.md の encoding checklist が明示する既知クラス (`lib.rs:87-100`)
- **P2-20** [確実] 命名トークン `{start}` の GUI 表示 (`1-23-41`) と Python 実出力 (通算分 `83-41`) が 1 時間以降で食い違う (`ExportScreen.tsx:1003` ↔ `export/pool.py:55-59`)
- **P2-21** [確実] thumbnail ffmpeg の Semaphore が invoke 単位で生成され画面全体ではアンバウンド並列 (試合 N 件 = N 本同時 spawn)。#670 (responsiveness) の主因候補はサーバではなくこれ + progress イベント無間引き (`lib.rs:1201`)

### テスト

- **P2-22** [確実] v0.3.0 split SHA-256 baseline (`obs-*.split.json`) に自動比較テストが存在しない: splitter regression は「generator 再実行 + 手動 diff」でしか検出できない
- **P2-23** [確実] export wire protocol e2e の skip 前提が誤り: docstring は「sample video 必要」と claim するが実際は lavfi 自前生成で動画不要。slow marker で CI から外れ GUI⇔Python 契約の唯一の e2e が常に deselect。SIGINT cancel テストは実行環境が存在しない dead test (`tests/test_export_wire_protocol.py`)。注意: CI の BtbN ffmpeg は LGPL で libx264 非同梱
- **P2-24** [確実] VTuber ground truth (±10s gate、commit 済み) が pytest に未配線で消費者は手動実験 script のみ。#809 wiring 着手時の gate 不在構造

### ドキュメント

- **P2-25** [確実] worker auto 上限「min(cpu_count, 24)」が 6 doc 7 箇所に残存 — 実装は 32 (cli-spec:53,262,446 / video-processing:51,378 / benchmarks:78 / tuning-guide:173,249)
- **P2-26** [確実] CPU Pass 1 の説明が「タイムスタンプごとの並列 `-ss` プローブ」のまま — 実装は #214 以降チャンク分割デコード (CLAUDE.md §データフロー / video-processing.md)
- **P2-27** [確実] video-processing.md の #576 新 path 説明が中間設計のまま (「output seek + Python 側 sampling」と記載、実装は dual seek + `select` filter)
- **P2-28** [確実] tuning-guide「デフォルト = --no-gpu」は誤り — 実際は codec ベース auto (#414)
- **P2-29** [確実] CLAUDE.md モジュール表に v0.2〜v0.3 の新 module 群が未掲載 (capture_region / export/ package / commands/export / encoder_slots / metadata_types / integrity / system_info / detection 3 module / tools)。§コマンドにも `allaganeye export` がない
- **P2-30** [確実] CLAUDE.md / design-overview の L2 が「開発中」のまま (v0.2.0 2026-04-26 / v0.2.1 2026-05-16 リリース済み)。L3 行も VTuber 保留 (2026-06 re-plan) 未反映
- **P2-31** [確実] scorebar-detection-design.md が #803 (中央跨ぎ選択 + 幅上限 1440px、doc の「最長 run」記述は実装と逆) / #797 trailing drop / #811 localize_scorebar を未反映
- **P2-32** [確実] system-architecture.md の起動経路・export 経路が #752/#761 以前のまま (同一 doc 内 §2.6 と矛盾)。quickstart.md §1.3 の ZIP フォルダ構成も旧レイアウト
- **P2-33** [確実] versioning.md「バージョン管理場所: pyproject.toml のみ」 — 実際は tauri.conf.json / package.json 含め 3 箇所。release skill の bump grep では JSON を検出できず bump 漏れの温床
- **P2-34** [確実] cli-spec: detect 節に `--progress-format` と `--gpu-vendor` がない / export 節の `--quiet`・`--concurrency` (切り詰めのみ・`copy` 時 1 slot 固定)・exit 2 の記述 3 点が実装不一致
- **P2-35** [確実] developer-setup.md が「LGPL 推奨」と書きつつ Windows 手順は GPL の `winget Gyan.FFmpeg` を「推奨」 — #508 方針と自己矛盾

### Issue トラッカー

- **P2-36** [確実・要ユーザー確認] #412 の前提コードが消失: PR #323 (28 分超 segment 二段スキャン、2026-04-17 merge) の `_refine_long_segments` 等が main・v0.1.x tag・develop-0.3.0 のどの系譜にも存在しない (tag 内容 + code search で確認)。元 bug #317 は #793 の A5 で再修正済み
- **P2-37** [確実] QSV/AMF decode hwaccel の残タスクが orphan 化: コード・CLAUDE.md が「#762 で wire 予定」と参照する #762 は not_planned close 済み、後継 issue ゼロ
- **P2-38** [確実] #805 が triage 未了 (priority/deferred なし) のまま 2 週間。規約上「deferred なし = v0.3.0 必須」に該当するが実働なし
- **P2-39** [確実] PR #811 が約束した guard repo への follow-up issue (VTuber VOD の FP 3 点: 短署名衝突 / moov>10MB buffer / cp932 crash) が未起票

## P3: 軽微

### コード (コア)

- GPU 診断ログが AMD 構成で常に「decode active」誤報告 (`gpu_detector.py:341-358`)
- `_probe_scorebar_context` が ffmpeg 不在 (VideoProcessingError) をログなしで None に握る (`scorebar.py:73-88`)
- merge probe / re-probe で不要な低解像度 probe が常時実行され ffmpeg 起動 2 倍 (`scorebar.py:58-67`)
- probe.py の duration 非数値文字列で uncaught ValueError (exit 3 でなく exit 1) (`probe.py:153`)
- metadata_writer の atomic write に fsync なし (OS クラッシュで torn file の可能性) (`metadata_writer.py:52-57`)
- `min_match_duration` 縮小が trailing drop 検査窓を縮める隠れ結合 (`detector.py:1958`)
- rescue path の bar_width exclusive/inclusive 1px 不整合 (`detector.py:1306` ↔ `:1183`)
- `_largest_component_region` の `import cv2` unguarded (`capture_region.py:143`)、`y_bottom` docstring の inclusive/exclusive 不整合 (`capture_region.py:59-69`)
- GPU chunk 失敗時の fallback が実行中 chunk の完走 join を待つ (遅延が不可視) (`gpu_detector.py:287-294`)
- `metadata_types.py` の `workers: float | None` 型劣化 (codegen 元 schema 側の問題)
- `detection/format.py` が dead module (production 未使用、private 版が生存) + `disabled_emitter()` production 未使用

### コード (export / CLI / scripts)

- cancel・失敗時の部分書き出し .mp4 が残置される (`ffmpeg_runner.py:120-122,263-276`)
- `--concurrency` 0/負値が silent 無視 (`commands/export.py:180-181`)
- `{idx}` なし `--name-pattern` の filename 衝突未検証 (`export/pool.py:38-52`)
- stderr_tail から GPU エラー行が progress noise で押し出されうる (`ffmpeg_runner.py:128-148`)
- AMF failure patterns 3 件が実機未検証
- dead parameter 2 件 (`pool.py:38` codec / `validate-fps-retirement.py:142` source_fps)
- `scripts/regen_audio_refs.py` と `allaganeye/tools/regen_audio_refs.py` がほぼ完全重複
- stale コメント「Patterns mirror gui/src-tauri/src/lib.rs:1738+」(Rust 側は #761 移管で削除済み) (`ffmpeg_runner.py:39`)
- stale branch pin 2 件: `scripts/cleanup-claude-branches.sh:94` (develop-0.2.0 固定 → 新 branch が掃除されない) / `.github/workflows/check-pr-checklist-test.yml:10` (develop-0.3.0 push でテストが走らない)

### GUI

- sample mode でキーボード nudge が read-only を貫通 (`PreviewScreen.tsx:515-544`)
- DraftRestoreModal だけ focus trap・Escape なし (a11y-policy 乖離)
- ExportScreen の `listen()` mount race で unlisten リーク (DropScreen の cancelled パターンと非対称)
- 死にコード/未使用依存: `cancelRequestedRef` (書き込みのみ)、Cargo.toml 未使用 5 件 (hyper / tokio-util / urlencoding / percent-encoding / dirs)、`clear_recent` UI 不在、`@tauri-apps/api` が devDependencies
- capabilities の `shell:allow-execute` / `shell:allow-spawn` 過剰権限 (#545 で独自 command 化済みのため未使用)
- `register_video` token が解放されず累積 (`lib.rs:846-850`)
- ConfirmExitModal 文言「中間ファイルは破棄」が実態 (部分 .mp4 残置) と不一致
- load 時 mtime 取得が read 後で TOCTOU が silent overwrite 側に倒れる (`metadataStore.ts:246-251`)
- `untrack_child` の Job handle drop による意図しない tree kill (異常系のみ、要検証) (`lib.rs:1735-1739`)
- 受理拡張子 (.avi 受理/.m4v 拒否) とエラーヒント (逆) の不整合 (`DropScreen.tsx:46` ↔ `error.rs:180-181`)
- detect-progress イベントのスロットリングなし (#670 関連) (`DetectingScreen.tsx:477-523`)

### テスト

- ErrorModal に jest-axe 未適用 (a11y-policy「全 modal」と矛盾)
- flow.integration の invoke mock default が寛容 (`Promise.resolve()`) で新 command の silent pass
- `tests/scripts/test_*.sh` 3 本が CI 未配線
- test_regression_330 が import 時に ffmpeg subprocess 実行 (collection 低速化)
- `tests/baselines/v0.3.0/README.md` の「Rust 側 unit test」参照が stale (正は `tests/test_export_ffmpeg_runner.py`)
- detection cache の `_CACHE_SENSITIVE_FILES` 手動列挙 (capture_region 配線時に追加忘れリスク)
- legacy fps filter path テスト群は現状正当。env var 削除時にテスト整理を同時実施 (削除 issue に明記要)

### ドキュメント / プロセス

- skills の `../../docs/` 相対リンク 14 件が 1 階層不足で broken (正: `../../../docs/`) (review-pr 5 / iterate-review 4 / scope-guard 1 / create-task 1 ほか)
- gui-development.md の CI「3 ジョブ」(実際 8) + テスト一覧が bootstrap 時点
- release-process.md §手動リリース手順に「Python 3.11.9 embed」残存 (同 doc 内 #752 記述と矛盾)
- versioning.md「Director」旧用語
- metadata-spec §将来の拡張に #810 未掲載
- cli-spec の行番号参照 drift (`:521`)、metadata.json トップレベル表に新 field 5 件欠落 (抜粋であることの明記なし)
- output-spec の適用範囲に detect コマンド不在
- design/bundle/README.md のバンドル内パス不一致 (歴史的 artifact、注記 1 行で可)
- issue 本文の鮮度切れ: #518 (scaffold 実装済みで question の役目終了) / #670 (v0.3.0 re-scope 未反映) / #753 (checklist 乖離) / #326 (着手条件成立済みで放置) / #376 (-V conflict なし、意味論判断のみ) / #804 (deferred 付与曖昧)
- PR #808 の typer/click pin 恒久対応が未起票
- #765 の参照先 #762 が not_planned close 済みで再評価 checkpoint の一部が宙

## 健全確認事項 (突合して問題なし)

- subprocess encoding は CLI コア全域で cp932 暗黙依存ゼロ (#656 系教訓の完全反映)。Rust 側 3 層 (PYTHONIOENCODING / byte-level read / from_utf8_lossy) も detect/export とも堅牢
- metadata-spec ↔ metadata_types ↔ zod ↔ writer/migrations は完全一致 (#612 codegen + CI drift gate が機能)。tauri-commands.md も 26 command 一致
- CI: typer/click pin (#808)、BtbN immutable pin、`defaults.run.shell` 化など既知の罠はすべて対処済み
- NVENC 14 pattern / QSV `Error creating a MFX session` の教訓反映、scorebar 閾値の実測根拠 docstring、リソース管理 (Popen/tempfile) はほぼ完璧
- L3 新規コード (#807/#811) は production import ゼロの pure additive で released path を構造的に保護
- #793 (fps filter retirement) は env var gate + 自動 legacy fallback で教訓どおり
- GUI store テストの独立性 (beforeEach reset)、schema 4 面 drift gate、jest-axe (ErrorModal 以外) は良好

## 横断的な構造所見

1. **「commit 済みだが未配線」の資産が 4 つ**: warnings scaffold / VTuber ground truth / split SHA baseline / format.py。配線だけで価値が出る (warnings scaffold は #805 の最小緩和にそのまま使える)
2. **cancel path だけ品質が一段低い**: detect 中断は kill せず (P1-1)、export 中断は完了 race でスタック (P2-14)、kill 後は partial file 残置。cancel ライフサイクルの横断的な揃えが必要
3. **doc drift は 2 パターンに収斂**: 「複数 doc への値の複製」と「実装後の『予定』文言残存」。metadata-spec 方式 (正 1 箇所 + リンク) の水平展開で構造的に再発を減らせる
4. **issue 追跡の死角は「closed 側から open 側への参照切れ」3 類型**: merge されたのに系譜から消えた (#323→#412) / 残タスク追記直後に not_planned close (#762) / PR 本文の「別 issue で」が未起票 (PR #811→guard)

## v0.3.0 リリースへの示唆

現在の v0.3.0 active set は #481 (minimap) と #670 (responsiveness) の実装 2 本 + #805 の方針判断 (VTuber pillar は park 済み、性能 pillar は消化済み)。#805 は「v0.3.0 で warnings 記録 (最小) + escape hatch を入れ、非破壊化は #805 本体で」という段階案がコスト最小。#670 は本監査でフロント側 2 点 (thumbnail 並列アンバウンド + progress 無間引き) が主因候補と特定済み。
