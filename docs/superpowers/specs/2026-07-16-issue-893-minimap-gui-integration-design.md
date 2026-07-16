# minimap crop の GUI 統合 (#893) design

- 日付: 2026-07-16
- 対象 issue: [#893](https://github.com/Idios/kobutachan-allaganeye/issues/893) (親: #753 / 前提: #481)
- 前提の CLI 実装: [2026-07-08 minimap crop design](2026-07-08-issue-481-minimap-crop-design.md)
  (§7「`--json` (GUI subprocess mode) は v1 では実装しない (GUI 統合は別 issue)」/
  §11「GUI 統合 … 別 issue 起票候補として PR 後に提示。preview 上の領域ドラッグ選択は
  `--region` 初回測定ハードルの本命解消策として同 issue で扱う」)
- 決定方式: brainstorming (AskUserQuestion 3 点 + 設計案 A〜F 承認、2026-07-16)

## 1. 背景と目的

L3 v0.3.0 の主要 feature「minimap 切抜き」(#481、minimap 前倒し #872) は CLI では完結
しているが、GUI ユーザーは `allaganeye minimap` の CLI 併用が必要で、v0.3.0 の GUI 完結性を
欠いている。本 design は GUI 上で minimap crop を完結させる:

- 動画上の overlay で領域を確認・調整 (ドラッグ選択)
- 実行ボタンで crop 開始、進捗を画面に表示
- 完了後は `minimap_regions` が GUI セッションに反映される

CLI 側 (#481、PR #884/#885) は実装済みで、本 issue で新設するのは **CLI `minimap` の
`--stdin`/`--json` subprocess mode** / **Tauri `start_minimap` + `detect_minimap_regions`
command** / **`MinimapScreen`** の 3 点。既存 export 基盤 (JSON Lines wire / encoder pool /
GPU fallback / process tracker / cancel) を最大限流用し、released detect/split/export 経路と
cache key には一切触れない。

## 2. 決定ログ (brainstorming、2026-07-16)

| 論点 | 選択肢 | 決定 (Idios) |
| --- | --- | --- |
| 画面配置 | 新規専用画面 / ExportScreen 拡張 / PreviewScreen 拡張 | **新規 minimap 専用画面** (`MinimapScreen`)。export(per-match encode)/preview(IN/OUT 境界) と責務分離。single global region を全試合に適用する minimap の性質に専用画面が意味的に自然で、full-frame video overlay の場所も確保できる |
| 提案モード (seed 自動検出) の扱い | opt-in ボタンで pre-fill / open 時に自動実行 / v1 は純手動のみ | **opt-in ボタンで pre-fill**。画面は手動ドラッグ選択の空矩形で始まり、「自動検出を試す」ボタンで seed 検出を実行して代表 match の提案領域を矩形に反映。重い全試合 sampling を明示 opt-in にし、手動測定だけのユーザーを待たせない。CLI exit 4 の「提案 print」を GUI では「矩形 pre-fill」に翻訳 |
| #514 排他 (mtime 検知) との整合 | 完了後に store 自動 reload / ConflictModal に委ねる / minimap_regions は書かず再読込のみ | **完了後に store 自動 reload** (mtime 更新 + minimap_regions 反映)。実行前 dirty guard も併設。自分の write-back を外部 conflict にしない |
| 設計案 A〜F 承認 | この方針で spec へ / per-match include は v1 外 / seed --json は v1 外 | **この方針で spec 執筆へ** (per-match include・seed 自動検出とも v1 に含める) |

## 3. 全体像 (3 層、export と同型)

```text
MinimapScreen (React)
  ├─ seed 提案: invoke('detect_minimap_regions', {req:{metadataJson, excludedIndexes}})
  │     └─ allaganeye minimap --stdin --json  (提案モード)
  │          → proposal 行を stdout に emit → Rust が集約して Vec<Proposal> を返す
  └─ crop 実行: invoke('start_minimap', {req:{metadataJson, region, outputDir, namePattern, excludedIndexes}})
        └─ Tauri start_minimap (lib.rs) — start_export と同型
             └─ allaganeye minimap --stdin --json --region X,Y,W,H --output-dir … --name-pattern … [--exclude …]
                  ├─ JSON Lines progress (result/error/fallback) → `minimap-progress` Tauri event
                  └─ minimap_regions を atomic write-back (既存 CLI crop 経路そのまま)
        → 完了後: metadataStore.reloadFromDisk() で mtime 更新 + minimap_regions 反映
```

- **検出は毎回 fresh 実行** (detection cache 非使用)。detect param を追加しないため cache key
  3 箇所問題 (`feedback_detection_flag_cache_key`) は構造的に発生しない (#481 と同じ)。
- **released 経路非接触**: 新設は minimap の subprocess mode と GUI 画面のみ。detector.py /
  scorebar.py / detect / split / export の既存経路は変更しない。

## 4. コンポーネント構成

| モジュール | 変更 | 責務 |
| --- | --- | --- |
| `allaganeye/commands/minimap.py` | 変更 | `--stdin` (metadata を stdin から UTF-8 read、export `_load_metadata` 同型) + `--json` (WireWriter で ndjson emit) を追加。crop モードの `progress_cb` を `--json` 時は `WireWriter.emit` に、提案モードの proposal 表示を `--json` 時は `{"type":"proposal",…}` 行に切替える。既存の plain-text / exit code 契約は `--json` 無し時のまま非破壊 |
| `allaganeye/export/schema.py` | 変更 (追加) | 提案 event 用の payload 型 (`type="proposal"`) を追加。crop の result/error/fallback は既存 `ProgressEvent` をそのまま流用 |
| `gui/src-tauri/src/lib.rs` | 変更 (追加) | `start_minimap` command (start_export と同型: subprocess spawn + stdin metadata + JSON Lines parse → `minimap-progress` emit + PROCESS_TRACKER + Job Object tree-kill) / `detect_minimap_regions` command (提案モード subprocess を起動し proposal 行を集約して返す。PROCESS_TRACKER 管理で unmount kill 可) |
| `gui/src/screens/MinimapScreen.tsx` (新規) | 新規 | full-frame video + ドラッグ選択 overlay + 数値 region 入力 + 自動検出ボタン + 設定 (出力先/命名/include) + 進捗 (progressBox + per-match list) |
| `gui/src/screens/MinimapScreen.module.css` (新規) | 新規 | 画面 CSS (aetherTheme tokens 準拠) |
| `gui/src/screens/reducers/minimap.ts` (新規) | 新規 | export reducer 同型の phase reducer (idle→running→completed/error/cancelling) |
| `gui/src/state/appStateStore.ts` | 変更 | `AppScreen` に `'minimap'` 追加 + navigate 経路 |
| `gui/src/state/metadataStore.ts` | 変更 | 完了後 reload 用の `reloadFromDisk()` action (既存 `load()` の mtime 記録 + minimap_regions 反映を再利用) |
| `docs/ui-interaction-spec.md` | 変更 | minimap 画面の操作 → 状態遷移 § 追加 |
| `docs/cli-spec.md` / `docs/output-spec.md` | 変更 | `minimap --stdin --json` 記載 |

## 5. データフロー / wire protocol

### 5.1 CLI `--json` mode (crop)

- Rust `start_minimap` は `allaganeye minimap --stdin --json --region X,Y,W,H --output-dir <dir>
  --name-pattern <pat> [--exclude a,b,c]` を spawn し、metadata JSON を stdin に流す
  (export と同一 I/O 契約)。
- crop モードは既に `export_matches(progress_cb=…)` を使用しているため、`--json` 時に
  `progress_cb` を `WireWriter.emit` に差し替えるだけで per-match の `result` / `error` /
  `fallback` 行が stdout に流れる。Rust 側は export と同じ parser で受けて `minimap-progress`
  event を emit する。
- event 名は **`minimap-progress`** (export の `export-progress` とは別チャネル。cross-talk /
  迷子 event を構造的に回避)。payload 形は export の `ExportProgressPayload` と同一
  (`{match_index, percent, stage, message?, fallback_from?}`)。
- 終了 code は既存 crop 契約のまま (成功 0 / 一部失敗 1 / SIGINT cancel 130)。Rust は
  `ExportSummary` 相当 (`{success, failure, skipped, cancelled}`) を返す。

### 5.2 CLI `--json` mode (提案)

- `detect_minimap_regions` は `allaganeye minimap --stdin --json` (`--region` 無し = 提案モード)
  を spawn。提案モードは `resolve_match_regions` の結果を、`--json` 時に 1 match 1 行の
  `{"type":"proposal","match_index":N,"region":{"x":px,"y":py,"w":pw,"h":ph},"confidence":c,"scattered":bool}`
  として emit する (pixel 座標、そのまま `--region` に使える値)。提案が出ない match は
  `{"type":"proposal","match_index":N,"region":null}` を emit。exit code は既存の 4 のまま
  (提案モードは自動確定不可)。
- Rust は proposal 行を集約し `Vec<MinimapProposal>` を返す。frontend は「自動検出中…」の
  loading state を表示し、返った proposal から矩形を pre-fill する。exit 4 は「crop してない」の
  正常シグナルなので Rust はエラー化しない (proposal を得られれば成功扱い)。

### 5.3 store reload (完了後、#514 整合)

- crop 完了 (`start_minimap` の invoke resolve) 後、`metadataStore.reloadFromDisk()` を呼ぶ:
  1. `get_metadata_mtime` で最新 mtime を取得 (load 時と同じ「mtime を先に取る」#834 順序)
  2. `load_metadata` で metadata.json を再読込
  3. store の `metadata` / `loadedMtimeMs` を更新 (`minimap_regions` を含む全 field を反映)
- minimap crop は matches を触らず `minimap_regions` を追加するだけなので reload は安全
  (境界編集の取りこぼしは起きない)。自分の write-back を外部変更 conflict にしない。
- **実行前 dirty guard**: 実行ボタン押下時に store が dirty (未保存の matches 編集あり) なら
  「先に [適用] するか変更を破棄してください」を促し crop を抑止する。sample mode
  (`filePath === null`) では disk が無いため crop 自体を disable (export/preview と同方針)。

## 6. MinimapScreen UI

### 6.1 レイアウト

```text
┌─ MinimapScreen ────────────────────────────────────────┐
│ [◀ 一覧へ]   <source path>   ミニマップ切抜き            │
│ ┌─ video pane (full-frame) ──────────┐  ┌─ 設定 ──────┐ │
│ │  <video> + ドラッグ選択 overlay      │  │ 領域 X,Y,W,H │ │
│ │  [◀ ▶ scrubber / match セレクタ]     │  │ [自動検出]   │ │
│ │                                     │  │ 出力先 [参照]│ │
│ └─────────────────────────────────────┘  │ 命名規則     │ │
│ ┌─ 切抜き一覧 (per-match include) ──────┐  │ [⬦ 切抜き]  │ │
│ │ ☑ 001 …  ☑ 002 …  — 003 (試合後)     │  │ progressBox │ │
│ └─────────────────────────────────────┘  └──────────────┘ │
└────────────────────────────────────────────────────────┘
```

### 6.2 video pane + overlay

- **full-frame `<video>`**: `register_video` (axum、preview と同経路) で 1 本の video を配信。
  代表 match (最初の非 post_match match) の中点へ seek し、match 内を移動できる簡易 scrubber /
  match セレクタを置く (エリアマップが映るフレームを選べる。lobby では映らないため試合内を見る)。
- **ドラッグ選択 overlay**: video 要素上に絶対配置した `div` の選択矩形 (canvas 不要、既存
  FrameStrip の SVG overlay と同じく軽量 DOM で足りる)。ドラッグで矩形を描き、ハンドルで
  リサイズ。element 座標 → 正規化 (0–1、video の `videoWidth`/`videoHeight` と表示サイズの比で
  変換) → source pixel を算出。
- **数値 region 入力** `X,Y,W,H` (source pixel、CLI `--region` と同値): ドラッグと双方向同期。
  精密指定・再現に使える。validation は CLI `_parse_region` と同じ境界 (負値不可 / w,h ≥ 16 /
  frame はみ出し不可)。
- **「自動検出を試す」ボタン**: `detect_minimap_regions` を実行。現在表示中の match の proposal が
  あればそれを、無ければ全 match 中の最高 confidence proposal を矩形に pre-fill。proposal が
  1 件も無い / scattered の場合は inline notice で best-effort 契約を明示 (「自動検出できません
  でした。動画を見ながら手動で範囲を指定してください」)。

### 6.3 設定・進捗 (export と同型)

- **出力先**: default `<metadata dir>/minimap` (CLI default 準拠)。`open({directory})` の参照
  ボタン + `stripExtendedPathPrefix` 正規化 (export と同じ)。
- **命名規則**: default `{idx:03}_{type}_{start}_minimap.mp4` (CLI default 準拠)。変数 hint 表示。
- **per-match include**: export と同型の checkbox (default 全選択、post_match は強制除外 + 「試合後」
  badge、`type_override==='skip'` も除外)。`--exclude` に渡す。
- **進捗**: `progressBox` (overall bar + 経過/残り) + per-match list (`✓/●/!/○/—` mark +
  per-file bar + error/fallback notice)。`minimap-progress` event 駆動。**中断**は
  `kill_tracked_processes` (export と同一)。完了後は「フォルダを開く」
  (`open_folder_in_explorer` 流用)。

## 7. ナビゲーション

- `AppScreen` に `'minimap'` を追加。
- **入口**: CompleteScreen のアクションバーに「⬦ ミニマップ切抜き」ボタンを追加
  (「⬦ 全試合書き出し」の隣)。`navigate('minimap')`。
- **戻り**: MinimapScreen の「◀ 一覧へ」で `navigate('complete')`。crop 実行中は戻る抑止
  (export 同様、先に中断を促す)。

## 8. エラー処理

| 状況 | 挙動 |
| --- | --- |
| region 未指定 / 不正 (parse 不能 / 負値 / w,h < 16 / frame はみ出し) | 実行ボタン disable + reason tooltip (CLI `_parse_region` と同じ境界を frontend でも検証)。subprocess に渡っても CLI が exit 5 で弾く (二重防御) |
| 実行前 dirty (未保存 matches 編集) | crop 抑止 + 「先に適用/破棄」promptで案内 |
| sample mode (`filePath===null`) | 画面全体 read-only (SampleModeBanner)。crop / 自動検出 disable |
| 提案モードで proposal 無し / scattered | inline notice (best-effort 契約)。crop 自体はブロックしない (手動指定に誘導) |
| GPU encoder init 失敗 | libx264 retry (#761 `_GPU_ENCODER_FAILURE_PATTERNS` 流用) + `minimap-progress` の `fallback` stage → per-match notice |
| 一部 match encode 失敗 | export と同じ summary 契約 (`success>0` なら完了扱いで per-match error 表示、`success==0 && failure>0` は error phase) |
| SIGINT / 中断 | `kill_tracked_processes` → Python が 130 → `cancelled` summary |
| subprocess spawn / stdin write 失敗 | `subprocess.*` AppError (export と同 code) を toErrorState で表示 |

## 9. テスト計画 (TDD)

Red-Green-Refactor を遵守 (NO PRODUCTION CODE WITHOUT FAILING TEST FIRST)。

1. **CLI `--json` crop** (Python unit): `--stdin` で metadata を読み `--region` crop、WireWriter に
   result/error/fallback が ndjson で流れる (mock encode)。`--json`/`--quiet` 排他。invalid stdin →
   exit 2 + clean stderr (export と同型)。
2. **CLI `--json` 提案** (Python unit): 提案モード + `--json` で `{"type":"proposal",…}` 行 emit、
   proposal 無し match は `region:null`、exit 4 維持。
3. **schema**: 提案 event 型 (`type="proposal"`) の serialize/deserialize。`test_export_schema` に追加。
4. **Rust `start_minimap`** (cargo test): subprocess 引数組み立て / JSON Lines parse → `minimap-progress`
   / summary 集約 / cancel。既存 `start_export` テスト同型。
5. **Rust `detect_minimap_regions`** (cargo test): proposal 行の集約 / exit 4 を成功扱い /
   PROCESS_TRACKER 登録。
6. **MinimapScreen** (vitest + `npm run typecheck`): 画面 render / ドラッグ→正規化→pixel 変換 /
   数値入力双方向同期 / region validation / include checkbox / progress event 反映 / 中断 /
   実行前 dirty guard / sample mode read-only。vitest は型検査しない教訓 (`feedback_gui_vitest_skips_typecheck`)
   に従い typecheck を controller が別途回す。
7. **metadataStore.reloadFromDisk** (vitest): 完了後 mtime 更新 + minimap_regions 反映 +
   false conflict が起きないこと。
8. **codegen drift**: 提案 event 型が codegen 対象なら `scripts/codegen/generate.py` 後 diff ゼロ。
9. **released 経路非回帰**: detector.py / scorebar.py / detect / split / export の既存経路
   非接触を PR diff で構造的に示す。crop の plain-text mode (既存) が `--json` 追加で壊れないこと。

## 10. 実機検証 (Iron Law 6)

`gui/src-tauri/**` (Rust command) + subprocess crop encode を含むため mock 不可。PR 時に
`AskUserQuestion` で Idios に Tauri 実機検証を依頼する:

- MinimapScreen で video 表示 → ドラッグ選択 → 自動検出 → crop 実行 → 進捗 → 完了 →
  minimap_regions 反映 (mtime conflict が出ないこと) の一気通貫。
- GPU crop encode (NVENC / QSV / AMF) の実機動作 + libx264 fallback。
- 検証は cache seed 方式で数秒読込 (`project_gui_verification_cache_seed`)。検証用 metadata は
  `E:\royalstraightflesh\videos\20260116\..._allaganeye\` (minimap 未実行 = 提案モードの実機
  テストに好適)。長尺全試合 crop は detached Start-Process 手順
  (`feedback_long_gpu_job_detached_execution`) を検証手順書に含める。

## 11. スコープ境界 (やらない)

- **VTuber inset 対応** (v0.4.0 期 #866。正規化座標 forward-compat のみ確保)。
- **円形ナビマップの切抜き** (需要が出たら別 issue)。
- **動的追跡** (試合内 region timeline)。single global region を全試合に適用する #481 契約を維持。
- **per-match で異なる region の指定** (GUI でも 1 region を全試合に適用)。
- **自動確定 crop (IoU 0.9 級の自動検出)** — #481 §6.3 STOP のまま v1 スコープ外。GUI 自動検出は
  あくまで pre-fill の best-effort seed。
- **提案モードの region を metadata に永続化** (#481 と同じく crop 実行時の `source:"manual"` のみ書く)。

## 12. Doc 更新 (#818 SSoT gate 準拠)

- `docs/cli-spec.md`: `minimap --stdin --json` (GUI subprocess mode) の記載。
- `docs/output-spec.md`: minimap の `--json` 出力行 (result/error/fallback/proposal) を追記。
- `docs/ui-interaction-spec.md`: MinimapScreen の操作 → 状態遷移 / store mutation / 例外処理 §。
- `docs/superpowers/specs/2026-06-29-v030-l3-roadmap.md`: v0.3.0 scope に「minimap crop GUI 統合
  (#893)」を SSoT 追記 (受け入れ条件 5)。
- `CLAUDE.md`: `MinimapScreen` を `gui/src/screens/` 記述に追加 / minimap の GUI 完結を反映。
- `docs/system-architecture.md`: GUI 起動経路・画面一覧に minimap を追記 (該当あれば)。

## 13. 参照

- issue: [#893](https://github.com/Idios/kobutachan-allaganeye/issues/893) / 親
  [#753](https://github.com/Idios/kobutachan-allaganeye/issues/753) / 前提
  [#481](https://github.com/Idios/kobutachan-allaganeye/issues/481)
- CLI 側 design: [2026-07-08-issue-481-minimap-crop-design.md](2026-07-08-issue-481-minimap-crop-design.md)
- 同型パターン: export subprocess (`start_export` in `gui/src-tauri/src/lib.rs` / `allaganeye
  export --stdin --json` in `allaganeye/commands/export.py` / `WireWriter` in
  `allaganeye/export/wire.py`) / ExportScreen 進捗 UI (`gui/src/screens/ExportScreen.tsx`) /
  PreviewScreen video 配信 (`register_video` axum)
- 基盤: encoder pool (#761 / #791) / #514 mtime 排他 (ConflictModal) / #810 CaptureRegion /
  #805 post_match 除外
- roadmap: [2026-06-29-v030-l3-roadmap.md](2026-06-29-v030-l3-roadmap.md) §4 Phase 2 / rescope #872
