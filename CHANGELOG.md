# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-08-01

L3 (配信形式対応 + 性能改善) リリース。エリアマップ切り抜き (`minimap` CLI + GUI 画面) と
並列 export (`export` CLI、GUI 書き出しの Python コア共有) を新設し、masked (チャット欄
マスク) / VTuber (ゲーム画面 inset) の配信録画を検出対象に加えた。detect の chunk decode は
ffmpeg `fps` filter を退役させ frame-index ベースに刷新、post-match trailing の不可逆削除は
`post_match` フラグ方式に置き換えた。NVDEC decode 経路の追加で export / minimap の
再エンコードを高速化し、Portable ZIP 同梱 CLI は PyInstaller で frozen 化した。

### Added

- **`minimap` コマンド** (#481): エリアマップ window を試合ごとに切り抜く。
  `--region X,Y,W,H` 指定で crop + H.264 encode + metadata write-back、省略時は
  領域を自動提案する提案モード (exit 4)。
- **GUI の minimap 統合** (#893): MinimapScreen を追加し、drag-select / 数値入力 /
  自動検出 / 進捗表示まで GUI 内で完結する (Tauri `start_minimap` command)。
- **GUI ExportScreen からの minimap 導線** (#902 / #928): 書き出し後に minimap へ進める
  entry を追加。minimap の default 出力先は、同一セッションで書き出しを実行済みなら
  直近の export 先、未実行なら**動画と同じフォルダ** (ExportScreen の既定と同じ基準) に
  なる。いずれの場合も出力先は画面上で変更できる。
- **`export` コマンド** (#761): `metadata.json` から試合を書き出す。`--codec h264` で
  NVENC / QSV / AMF / libx264 を自動選択し、NVENC 選択時は GPU SKU テーブルの engine 数
  だけ並列スロットを確保する (default の `--codec copy` はディスク I/O 競合を避けるため
  1 並列固定)。`--concurrency` は自動決定されたスロット数を上限として**絞る**方向にのみ
  効く (OBS が NVENC engine を占有している場合などの調整用で、これでスロット数は増えない)。
  スロット数そのものを**引き上げる**には環境変数 `ALLAGANEYE_EXPORT_CONCURRENCY` を使う
  (**NVENC が選択された場合にのみ有効**。SKU テーブル未収録の NVIDIA GPU は既定 1 スロット
  のため、Workstation / Datacenter GPU ではこちらで指定する)。QSV / AMF / libx264 は
  常に 1 スロットで、本環境変数の影響を受けない。GUI の書き出しも同じ Python コアを共有する。
- **masked (チャット欄マスク) 録画の検出対応** (#821 / #822): 全画面にマスク画像が
  合成された録画向けに、mask のない領域を自動検出して再検知する `--masked` を追加。
  anchor presence と segment 検証の 2 層構成で過分割を抑制する。暗転が 1 件も検出
  できなかった録画では `--masked` 未指定でも本 fallback が自動発動する (`--masked` は
  暗転が一部見つかる場合でも強制するためのフラグ)。発動有無は metadata の
  `detection_params.masked_fallback_used` で常に確認できる。`-v` の `masked_fallback=on`
  トークンは **cache hit 時のパラメータ要約行にのみ**出力される点に注意 (fallback が実際に
  発火する cache miss の初回 run では出ない)。初回 run の確認は metadata 側を見ること。
- **detect / split `--vtuber`** (#895): VTuber 配信録画 (ゲーム画面が inset、装飾
  オーバーレイ多数) 向けの timeline 検出を新規追加。暗転起点ではなく「試合中である」
  証拠 (scorebar presence AND 画面運動) の timeline から試合区間を抽出する (V0 anchor
  解決 / V1 全域 10s stride scan / V2 rolling-window 粗 segmentation / V3 gap 裁定 +
  blackout-peek override + 境界 snap / V4 segment 検証)。v0.3.0 開発中は hidden の
  experimental フラグとして先行実装し、GT gate 通過をもって公開扱いにした。
  **OBS / masked path は非接触** (フラグ未指定時の出力は bit-exact で不変)。縮退 4
  trigger (V0 anchor 失敗 / UNKNOWN 過半 / V2 無結果 / V4 が全 segment を drop) で
  従来の band-crop blackout path へ fall back する floor 保証付き。`--masked` との
  同時指定は排他エラー (exit 5)。
  採用可否は verbose の `Timeline (vtuber)` / `V3:` 行で確認できる (metadata.json の
  `detection_params.vtuber` はフラグの要求値を記録するだけで、縮退時も true のまま)。精度 gate は 6 配信者 / GT 67 試合
  (`tests/baselines/v0.3.0/vtuber-gt/*.json`) に対する slow テスト
  `tests/test_vtuber_gt_regression.py` で、短 gap の 1 組を `expected_merge_with_next`
  で合成した実効 66 セグメントと突合し **recall 100% (66/66、missed 0) / spurious 0**。
  tolerance は非対称 (損失方向 15s / 余分方向 300s = 試合内容の欠落を許さない側に厳格)。
  詳細は `docs/superpowers/specs/2026-07-17-vtuber-timeline-detection-design.md`。
- **post-match trailing の非破壊フラグ化** (#805): 試合終了後の trailing 区間を削除する
  代わりに `post_match: true` を付与する。default split の MP4 からは除外しつつ metadata
  には保持し、GUI では badge / dimming と ExportScreen の選択不可行で可視化する。
  `--keep-trailing` で通常 match として MP4 にも出力できる。
- **metadata `capture_regions`** (#810): 検出 ROI の解決結果 (縮退 provenance 込み) を
  `metadata.json` に永続化。
- **Portable ZIP CLI の frozen 化** (#752): 同梱 CLI を PyInstaller `--onedir` で
  frozen exe 化し、従来の `python/` (embeddable Python) + `lib/` 展開を廃止。展開後の
  Python 関連ファイル数が大幅に減少した (旧構成は推定 ~2500、frozen 後は数百規模)。

### Changed

- **detect**: chunk decode の ffmpeg `-vf fps=N` filter を廃止し、dual seek
  (`-ss` を `-i` の前後に二重指定: keyframe への高速ジャンプ + GOP pre-roll の
  正確な trim) + `-fps_mode passthrough` + ffmpeg `select='not(mod(n,N))'`
  (frame-index ベース、PTS 非依存) 方式に移行 (#576)。ffmpeg version 依存の
  frame-selection drift (#560 / #575 / #577) を構造的に除去。**ffmpeg 8.1 上で
  legacy fps filter path を走らせた場合との比較**では、obs-20260118 で見逃されて
  いた 3 件の短時間 blackout (1.4-2.1s) を正しく検出するように動作が変わる
  (legacy 側の結果は 5 matches で、M1 = 177-2610 が単一 match に潰れていた)。
  新 path では Match 1 が 17m23s に短縮、新 Match 2 (15m24s) が追加、Match 3 が
  15m52s に短縮。この新 Match 2 (1686-2610) は 2026-05-21 の Idios 視覚再確認で
  real boundary と確定、`tests/baselines/v0.3.0/ground-truth/obs-20260118.json`
  を 5→6 matches に update 済 (#796 audit 後追補)。
  **v0.2.x からの実差分ではない点に注意**: repo に pin 済みの v0.2.x baseline
  (`tests/baselines/20260118.json`) は既に 6 matches を記録しており、v0.3.0
  baseline との差分は M5 end の 2.25s (6467.5 → 6465.25) のみ。上記の 3 件は
  あくまで legacy path を ffmpeg 8.1 で走らせたときに現れる drift に対する差分
  (詳細は `docs/v030-baseline-audit.md`)。
  **detect の所要時間は v0.2.x より延びる**: 取りこぼしていた短時間 blackout を
  拾うために Pass 2 refinement の発火範囲を広げた結果、probe 数が増えている。
  実測 (RTX 5090) で 5 OBS baseline 合計 ~31 min → ~52 min (約 1.7x)、最も影響の
  大きい obs-20260118 は 7 min → 18 min。検出精度と引き換えの trade-off で、
  更なる最適化は v0.3.x で検討する (#576 spec §10 R12)。
- **metadata.json スキーマ**: `matches[].output_file` を必須から任意に変更 (#805)。
  `post_match: true` の entry は MP4 を生成しないため `output_file` を持たず、
  `matches[]` の件数と出力 MP4 の件数は一致しなくなった。`schema_version` は `"1"` の
  まま (追加 field はすべて optional) なので、metadata.json を読む外部スクリプトは
  `output_file` の有無を存在チェックで判定すること。なお v0.3.0 が書いた post_match 入り
  metadata.json は v0.2.x の GUI では読み込めない (旧 zod が `output_file` を必須として
  いるため)。
- **検知キャッシュの全無効化**: 検知結果の形が変わったため cache version を 2 → 4 に
  更新 (#821 / #805)。v0.2.x が書いた `.detection_cache.json` は再利用されず、
  **処理済みの動画でも v0.3.0 の初回実行はフル再検知になる** (2 回目以降は従来どおり
  cache hit)。
- **`-v` verbose 出力の書式**: 検知パラメータ行に `vtuber=` / `masked=`、cache hit 行に
  `keep_trailing=` / `masked_fallback=` / `region=` を追加し、cache miss 時は
  `Region: <領域>` 行を出力するようにした (#810 / #821 / #908)。masked / `--vtuber`
  採用時のみ専用の統計行 (`masked L2 validation` / `masked L2 zero-gap merge` /
  `Timeline (vtuber)` / `V3:`) が追加される。既定出力と `-q` の内容は不変だが、
  `-v` 出力をパースしている場合は影響する。
- **GUI brightness timeline** (#576 の副作用): #569 で追加した GUI 輝度タイムラインの
  Pass 1 brightness 値が新 path で正確化される (旧 path の fps filter drift で歪んで
  いた値が修正される方向)。timeline 形状の変化が user-visible になる可能性あり。
- **Audit verification**: PR #793 detector を 5 OBS baseline
  (obs-20260116/118/119/127/209、計 54 boundary) に対して
  `scripts/audit-compare.py` (#796 deliverable, PR #799) で ground truth 比較。
  **53/54 agreed (within ±5s、98.1%)**、唯一の残 finding は
  obs-20260116 M6 end (#797) で、本リリースの #803 gate + #805 フラグ化で解消。
  obs-20260118 ground truth は PR #793 detector で新発見した M2 boundary
  (1686-2610s) を Idios 視覚再確認 (2026-05-21) で実 boundary 確定し
  5→6 matches に修正。詳細は `docs/v030-baseline-audit.md`
  §"2026-05-21 PR #793 verification update" 参照。

### Fixed

- **export / minimap の出力パス表示**: 完了行 (`[OK] match NNN -> ...`) と `--json` の
  `output_path` が**絶対パス**になった。従来は `-o` に渡された相対パスをそのまま表示して
  いたため、書き出し先が実際にどこになったのか読み取れなかった。特に shell の quote 忘れで
  `-o E:\a\b` が `E:ab` (ドライブ相対パス) に化けた場合、Windows がカレント基準で解決した
  結果と表示が食い違う。あわせて CLI のテキスト表示は OS ネイティブの区切り文字を使う
  (`--json` 側は GUI 互換のため posix 形式を維持)。
- **detect (scorebar V2)**: post-match content (試合終了後の Limsa /
  colorful interior 等) の彩度高領域を Rescue path が scorebar と誤検出
  する false positive を解消 (#803)。`_find_scorebar_horizontal_range` に
  span width 上限 (`_SCOREBAR_SCAN_MAX_WIDTH_PX=1440`) と中央位置要求
  (span が画面中央 x=960 を含む) の 2 gate を追加。obs-20260116 で試合終了
  (6540、scorebar HUD 残存) 直後の post-match 区間 (6544-6850) が試合内と
  誤分類されていた問題を修正。Primary path (絶対座標 emblem) は無変更。
- **detect (post-match trailing)**: 試合終了後の trailing 区間 (lobby / city
  interior 等) が独立した unknown match (`match_007.mp4`) として出力される
  問題を解消 (#797)。当初は scorebar 不在を probe で確認した上で trailing を
  出力から削除する実装だったが、scorebar 検出が FN する環境 (未対応 HUD /
  4K Game DVR 等) で実試合を silent に失う構造リスクがあったため、
  リリース時点では **削除せず `post_match: true` を付与する非破壊方式**に
  置き換えている (#805)。obs-20260116 では ground truth の 6 試合すべてを許容誤差
  (±5s) 内で検出し、MP4 出力も 6 本になる。trailing は 7 件目の entry として
  `post_match: true` / `output_file` なしで metadata に残る (`matches[]` は 7 件)。
- **GPU / CPU / メモリ検出の wmic 依存を解消** (#860): `wmic` が既定で削除された
  Windows 11 24H2 以降で PowerShell `Get-CimInstance` にフォールバックする。
  GPU vendor を検出できず CPU モードに縮退していた環境を救済。
- **metadata optional field の write 境界を硬化** (#879): GUI (Rust) 側に zod schema の
  4-field mirror を置き、CLI 側でも sanitize してから書き戻すようにした。cache read も
  単一化。
- **GUI の dev/build 依存 (npm) の既知脆弱性 6 件を解消** (#836、`npm audit` green)。
  いずれも vite / vitest / eslint 系の開発ツールチェーン依存で、配布 Tauri bundle には
  同梱されないため利用者への影響はない。
- **`release.yml` の phantom run** (#786): step の `shell` に `${{ matrix.* }}` を
  使うと job が実行されない問題を `defaults.run.shell` で解消。
- **release の version-check が GUI 側の stale version を素通り** (#911): tag と
  突合していたのが `pyproject.toml` のみだったため、`gui/package.json` /
  `gui/src-tauri/tauri.conf.json` / `gui/src-tauri/Cargo.toml` および両 lockfile の
  古いバージョンが silent に通っていた。6 ファイル 7 フィールドすべてを突合し、
  1 つでも不一致なら fail する gate に置き換え。
- **`scripts/validate-fps-retirement.py` の PTS 抽出** (#804): boundary timestamp に
  対して常に固定値 `0.021` を返していた bug を、放出フレーム基準の parse に修正。
- **依存の上限 pin** (#808): `typer<0.25` / `click<8.4` を追加。両者の新版で CLI が
  起動しなくなる非互換があり、CI 赤化として顕在化したもの。runtime 依存の pin なので
  配布物にも効く。
- **GPU fallback 時に行が「未着手」表示のまま残る** (#591 / #899): export 画面・
  minimap 画面で GPU エンコーダが失敗し libx264 で再試行に入ったとき、その試合の行に
  「libx264 で再試行します」という通知だけが出て、行のマークは `○` (未着手) のまま
  だった。NVENC の初期化失敗は 1 フレームも encode せずに落ちるため fallback がその
  試合の最初の進捗イベントになるのが通常ケースで、「未着手なのに再試行中」という
  矛盾した表示になっていた。fallback を受けた時点で行を実行中 (`●`) に倒すよう修正。
  進捗が 0% に戻ること自体は libx264 で encode をやり直すため正しい挙動なので据え置き。
- **GPU fallback 通知が地の文と同じ色で描画される** (#591、v0.2.0 から): export 画面の
  「libx264 で再試行します」通知が、定義されていない CSS 変数を fallback なしで参照して
  いたため宣言ごと無効化され、周囲の文字と同じ色で表示されていた (強調されず埋もれる)。
  テーマ既定のアクセント色で表示するよう修正。同じ欠陥を複製していた minimap 画面
  (v0.3.0 で新規追加のため未出荷) も同時に修正し、未定義 CSS 変数の参照を検出する
  回帰テストを追加した。

### Security

- **cargo audit high × 2** (リリース作業中に検出、Refs #862): RUSTSEC-2026-0194
  (start tag の重複属性チェックが quadratic) / RUSTSEC-2026-0195 (`NsReader` の
  namespace 宣言が無制限に確保される) — いずれも CVSS 7.5、quick-xml 0.38.4 が対象。
  tauri 2.11.1 → plist の transitive のため quick-xml 単独では上げられず、
  `cargo update -p plist` で plist 1.8.0 → 1.10.0 / quick-xml 0.38.4 → 0.41.0 と
  semver 互換の範囲で解消した。`Cargo.toml` は無変更 (tauri は `=2.11.1` のまま)。
  quick-xml は Tauri の plist 読み込み経路にあるため、**配布 GUI に同梱される依存**。
- **npm audit high × 4** (リリース作業中に検出、Refs #862): `npm audit fix` (非
  `--force`) の transitive bump で解消。brace-expansion 5.0.6 → 5.0.9 /
  fast-uri 3.1.2 → 3.1.5 / js-yaml 4.2.0 → 4.3.1 / nanoid 3.3.15 → 3.3.16 /
  postcss 8.5.15 → 8.5.25。`gui/package.json` は無変更。いずれも dev/build
  ツールチェーン依存で、配布 Tauri bundle には同梱されないため利用者への影響はない。
- **serde_with medium × 1** (Dependabot alert #22、Refs #862): GHSA-7gcf-g7xr-8hxj
  — `KeyValueMap` の serializer が要素長から `1` を引いてから最初の key field の
  存在を検証するため、空の内部 sequence / map entry を渡すと `Vec::with_capacity`
  が panic し DoS になる。`tauri 2.11.1 → tauri-utils 2.9.1` の transitive のため
  直接依存ではなく、`cargo update -p serde_with --precise 3.21.0` で semver 互換の
  範囲で 3.18.0 → 3.21.0 と解消した (`Cargo.toml` は無変更、tauri は `=2.11.1` のまま)。
  本プロジェクトは `serde_with` を直接使用しておらず、`KeyValueMap` に攻撃者制御
  データを流す経路も無いため実影響は無い。
  **本件は `cargo audit` では検出できない**: RustSec advisory-db に `serde_with` の
  advisory が存在せず、当該 lockfile に対して `cargo audit` は exit 0 (green) を返す。
  詳細は [`docs/ci-security-audit.md`](docs/ci-security-audit.md) §Dependabot との関係 を参照。

### Performance

- **NVENC export の NVDEC zero-copy decode** (#791): `-hwaccel cuda
  -hwaccel_output_format cuda` で decode → encode を GPU 内に留める。NVDEC decode 段の
  失敗も libx264 fallback の trigger に含めた。RTX 5090 / 2 時間動画 8 試合の
  H.264 並列 export で、ffmpeg の ETA 比較が 10:54 → 約 6:53 (≒1.58x)。
  **この倍率は完了実時間ではなく ETA 同士の比較**である点に注意。GPU 稼働率は
  Task Manager 実測で NVDEC 69% / NVENC 94%。
- **minimap crop (フィルタ有り NVENC) の NVDEC decode** (#899): `-vf crop` があると
  zero-copy が使えないため `-hwaccel cuda` 単独で NVDEC decode + CPU crop + NVENC
  encode する 3-tier fallback を実装。AV1 ソースで 2.29x。
- 当初 v0.3.0 で detect 高速化 path に切替 (#576) で ~10x slowdown が
  発生していたが、Codex perf rescue Option 1 (dual seek: input seek for
  fast container index jump + output seek for accurate chunk_start) を
  commit `a864834` で実装し、perf を legacy 同等以下に復元。
- ただし dual seek 後の accuracy 検証で sub-sample-interval blackout
  (例: obs-20260116 t=2178 = 試合境界、Idios 視覚確認済) を Pass 1 が
  取りこぼすケースを発見。A3 borderline range を `[15, 30) -> [15, 55)`
  に拡張 (#576 A5) して Pass 2 refinement を活性化、accuracy regression
  ゼロに到達。trade-off として Pass 2 probe 数増加で perf cost +1.7x。
- 実測 (RTX 5090): 5 OBS baseline 合計 **~52 min** (legacy ~31 min)。
  spec §7.4 perf gate を 60 min/合計に revise。
- v0.3.x で更なる最適化 (gradient-based trigger / packet PTS parse /
  single-process design) 検討 (#576 spec §10 R12 defer)。

### Deprecated

- env var `ALLAGANEYE_DETECT_FPS_FILTER=1` で旧 fps filter path に
  rollback 可能 (transitional)。**v0.3.x patch release で削除予定**。
  緊急 escape 用途のみ、CI / production で使わないこと。

### Known Issues

- **`--vtuber` の試合間 merge** (#895、追跡: #921): V2 は「試合中である」証拠
  (scorebar presence AND 画面運動) を rolling window (window 9 x stride 10s、quorum 2)
  で平滑化するため、**試合間で証拠が落ちる区間が平滑化を割り込めるだけの長さ・密度に
  ならないと**、2 試合が 1 segment に結合されうる。6 source / GT 67 試合中 **1 境界**
  (shirurori の M7-M8、gap 59s) で実測。当該箇所は試合後の result 画面がスコアバーと
  ほぼ同座標にスコア UI を表示し (result-mimic)、証拠の落ち方が浅かった。
  **gap の長さ単独では結合の可否は決まらない** (境界前後の証拠密度に依存する): 同じ GT
  には 75s 以下の隣接 gap が 9 本あるが、結合したのは上記 1 本だけで、shikke の
  55-71s の 8 本はいずれも正しく分割されている。V2 に hard-gap break を入れる案は Onsal マップのダウンタイム (scorebar FN
  が 120s 以上続く) で誤 break を誘発する副作用があり不採用とし、既知 limitation として
  GT 側に `expected_merge_with_next` 注釈で管理する。試合内容の損失は起きない (結合方向
  のみ) ため、必要なら書き出し後に手動で分割する。暗転ベースの標準 path には影響しない。
  詳細は `docs/superpowers/specs/2026-07-17-vtuber-timeline-detection-design.md` §7.5。

### Internal

- GUI 安定化: detect 中断時の `kill_tracked_processes` invoke + run-id fencing
  (#813)、metadata 境界検証 + load エラー可視化 (#814)、export/cancel 安定化
  (#837)、stderr drain の bounded helper 化 (#838)、metadata / polish (#834)。
- CLI / export 整合 (#840)、detector core 堅牢化 (#842)、テスト配線拡充
  (split SHA gate / wire e2e CI 実走 / VTuber GT、#844 / #845)。
- `--vtuber` の精度 gate 用に 6 source の VTuber ground truth
  (`tests/baselines/v0.3.0/vtuber-gt/*.json`) と境界注釈計測器
  `tests/scripts/poc_vtuber_timeline/gt_boundary_probe.py` を追加 (#895)。
  計測器は評価専用 (CLI / 配布物からは参照されない) で、GT 再現性のため
  production `_tolerant_runs` の copy を pin し drift 時に WARNING を出す。
- v0.3.0 OBS baseline regression 基盤: compare-baseline + ground truth (#777)、
  動画セット選定 5 本 (#778)、baseline 生成 + split.json schema (#779)、
  audit-prepare / audit-compare の再現性硬化とクラッシュ復旧 (#796 / #798 / #800)、
  #805 段階2 追随の baseline 再生成 (#881)。
- probe 失敗 semantics の tri-state 統一契約を導入 (#824、挙動不変)。
- `probe.py::ProbeResult` に `fps_num` / `fps_den` フィールドを追加 (#576)。
  NTSC 60000/1001 等の rational frame rate を float 精度損失なく detector まで
  伝搬させるための内部 API 拡張で、`metadata.json` には出力されない。
- one-off の開発用スクリプトを 2 本追加 (いずれも CI gate ではなく、配布物からも
  参照されない): `scripts/validate-fps-retirement.py` (#576 実装中の evidence 収集用)、
  `scripts/v3-normalize-source-path.py` (PR #793 reexamination の V3 baseline regen で
  絶対 path → 相対 path を正規化し、audit-compare の source-vs-ground-truth 整合を取るため)。
- 開発運用の用途別モデルルーティングを導入 (#889)。
- v0.2.0 / v0.2.1 retrospective 機構化 + Codex 統合 (#775)、PR 作成 Pre-flight
  Step 5 の 3-tier invocation path を明文化 (#795)。
- SSoT 規約の明文化 (#818) と doc の drift 修正 / 一括再同期 (#815 / #862 / #908)、
  skill の追跡切れ防止チェック + broken link 14 件修正 (#817)。
- `scripts/cleanup-claude-branches` の squash merge 検出を branch 名一致から
  OID 同一性ベースに変更 (#827)。
- pyright の解析対象から `.claude/worktrees` を恒久除外 (#828)。
- V6.2 (scorebar HUD 二分探索) を #797 fix として一時実装 (commit
  `f7f8879`)、obs-20260116 実機検証で scorebar V2 detection が 5700-6850 の
  全範囲で True を返し、post-match content (6540 以降) と in-match を区別できない
  false positive が判明し revert (commit `22c8979`)。V2 strengthening の調査を
  新 issue (#803、`bug` / `P2-medium` / `refactor`) で扱い、#797 の scorebar-based
  fix path の blocker とする。経緯は
  `docs/superpowers/specs/2026-05-19-v030-l3-detect-fps-retirement-reexamination-design.md`
  §10 に記録。

## [0.2.1] - 2026-05-17

v0.2.0 リリース直後の patch リリース。Dependabot security alerts 解消と既存 deferred UX issue 5 件の対応、PR マージ前の cargo/npm audit CI 追加 + Windows process tree orphan の Job Object 化を含む。Track A/B-1/B-2/B-3/B-4/C/D 構成 (`docs/superpowers/specs/2026-05-16-security-alerts-response-design.md`)。

### Security

- tauri 2.10.3 → 2.11.1 (medium: Origin Confusion / Remote→Local IPC invocation、GHSA-7gmj-67g7-phm9) (#760)
- fast-uri 3.1.0 → 3.1.2 (high × 2: GHSA-v39h-62p7-jpjc / GHSA-q3j6-qgpj-74h6、dev-only deps via ajv) (#760)
- glib transitive 0.18.5 / rand transitive 0.7.3 は deferred (tauri 上流の kuchikiki / phf_generator 移行待ち、配布物 (Windows Portable ZIP の `allaganeye-gui.exe`) への runtime 影響なし。glib は Linux/macOS GTK 系のみ、rand は build-dep のみ。詳細は `gui/src-tauri/Cargo.lock` および audit log `docs/audit-logs/2026-05-16-v0.2.1-audit.log` 参照) (#760)

### Fixed

- detecting 中の GUI 終了で ffmpeg 子孫プロセスが残留する問題を Windows Job Object (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`) で解消。`start_detect` の spawn site に `ProcessJob` RAII wrapper を適用し、`kill_tracked_processes` で Job handle drop → kernel が tree kill (#756, #772)
- `.github/ISSUE_TEMPLATE/bug_report.yml` の `docs/bug-report-guide.md` link を `develop-0.2.0` から `main` に更新、未公開 placeholder を削除 (#458, #764)
- `docs/design-overview.md` の metadata.json example から stale な `note` 行を削除 (実装本体は #463 で既に retired) (#374, #766)

### Changed

- Portable ZIP 内 `README.txt` を日本語化 (`scripts/build-portable-zip.ps1` Format-ReadmeContent + Pester assertion 更新、法的引用は原文保持) (#749, #768)
- Windows process tree 6 spawn site の audit document を `docs/process-tree-orphan-audit.md` として整理 (#743, #772)

### CI / Infrastructure

- cargo audit + npm audit を PR マージ前に実行する `.github/workflows/security-audit.yml` を追加 (Track C、tauri 2.11 transitive の 19 deferred warnings を考慮し vulnerability のみ fail 設定) (#763)
- `docs/ci-security-audit.md` を新設 (workflow 運用 note) (#763)

## [0.2.0] - 2026-05-16

L2 (GUI + Portable 配布) リリース。Tauri ベースの GUI を新設し、Portable ZIP 配布で zero-environment setup を実現。GPU decode を Intel QSV / AMD d3d11va に拡張、CLI/GUI で metadata.json schema を統一、warnings 基盤を導入。L2 開発プロセスとして markdownlint 導入、Iron Law 6 (PR 作成前ゲート)、`/iterate-review` / `/close-issue` skill 等の workflow / docs / test infra を全般強化。

### Added

#### L2a: GUI (Tauri)

- Tauri プロジェクト bootstrap (#483, #499)
- Phase 1 data layer (detect/split + metadata contract + Zustand store) (#463, #504, #512)
- Phase 2 画面骨格 + [元に戻す] 機能 (#464, #516, #526)
- Phase 3 preview 本物化 + ffmpeg 中断フロー (#465, #523, #540)
- Phase 4 export 本物化 (ffmpeg 呼び出し + 進捗) + GPU encoder auto-select (#466, #545, #591, #596)
- DropScreen DnD + 直近録画リスト (recent.json + Tauri commands) + 詳細設定パネル (#568, #571, #613, #625, #655)
- detecting / complete 画面を本物化 (CLI 連携 + 輝度タイムライン) (#569, #623)
- preview FrameStrip brightness overlay (#645, #735)
- CompleteScreen 「所要」列追加 + threshold 連動 (#586, #588, #626)
- ExportScreen default outDir + ErrorModal tauri-command fallback (#680, #696, #741)
- 編集 draft 自動保存 (リロード耐性) + DraftRestoreModal (#517, #534, #697, #730)
- metadata.json 排他管理 (mtime 検知 + conflict modal) (#514, #532)
- ConflictModal で state.mtime_conflict AppError hint 表示 (#695, #725)
- sample mode 全画面 read-only 化 (#633, #719)
- GUI 5 画面横断 file path 表示統一 (#676, #747)
- GUI クラッシュ・エラー伝搬ハンドリング (#614, #661)
- AppError migration 完遂 (legacy fallback 撤去 + per-code default hint 全 80 site 適用) (#663, #689)
- InlineErrorHint component 新設 + 既存 5 site refactor (#693, #714)
- ErrorModal「Issue 本文をコピー」button 新設 (Plan B clipboard) (#669, #726)
- DropScreen で recentStore error notice 表示 (#698, #733)
- GUI 全画面 a11y polish (focus trap / Escape / DisabledTooltip / jest-axe) (#587, #631)

#### L2b: Portable ZIP installer

- リリース配布 workflow + Portable ZIP ビルドスクリプト (#461, #490)
- Python 3.11.9 + BtbN LGPLv3 FFmpeg 8.1 統一 (#508, #510, #531, #535)
- FFmpeg LGPLv3 LICENSE 同梱 + ソース入手経路を明記 (#509, #541)
- allaganeye-gui.exe を Portable ZIP に同梱 (#570, #615)
- allaganeye.bat ダブルクリックで GUI 起動 (#617, #701)
- Portable ZIP 同梱物の起動時健全性チェック (#668, #702)
- BtbN pin を monthly snapshot に切替 (~24ヶ月 retention) (#705, #721)
- Portable ZIP の SmartScreen 警告手順と署名方針記録 (#462, #495)
- Portable ZIP .bat/README.txt を docs と整合 (#503, #507)

#### GPU decode 拡張

- AV1/VP9 を GPU decode auto-select 対象に追加 (#414, #539)
- vendor probe + `--gpu-vendor` option 基盤 (NVIDIA 実装, AMD/Intel stub) (#546, #554)
- AMD GPU decode を d3d11va + hwdownload で実装 (#553, #578)
- Intel QSV decode 対応 (h264 / hevc / av1) (#550, #581)
- Intel QSV VP9 decode (#582, #585)
- GPU mode UX 三点修正 (#437, #438, #439, #543)

#### Metadata / Warnings 基盤

- metadata.json JSON Schema 化 + 型 codegen 導入 (#612, #627)
- metadata.json schema_version + migration 基盤 (#515, #533)
- warnings 基盤 (Warning type + 空 array) (#518, #544)

#### CLI / verbose

- HW info verbose を multi-CPU / multi-GPU 対応 (#435, #436, #650)
- 3 detect フェーズを最初から並べる多行 eager 表示 (#434, #642)
- single-dash long-option 入力時に `--<name>` ヒント表示 (#440, #632)
- verbose Filter 行に unknown match 件数の別行を追加 (#433, #638)
- 進捗バー ETA 表示の改善 (label / placeholder / visual baseline 維持) (#365, #687)

#### Docs / workflow

- UI interaction spec §1 共通原則 + §2.1-§2.5 各画面 UI 部品状態機械 + §3 拡充 (#590, #593, #598, #600, #603, #605, #608, #610)
- CLI+GUI 統合 system-architecture 新設 + ui-architecture GUI 限定明記 (#527, #542)
- 全 Tauri command の master 一覧 doc (#619, #665)
- v0.2.0 リリース受け入れゲートを定義 (#620, #621)
- L2 Tier 0 release gate (axum-video-server spec + l2-e2e-checklist) (#484, #618, #672)
- 外部ユーザー向けバグ報告ガイド + Issue Form (#458, #459, #497, #498)
- Iron Law 6 新設 (PR 作成前ゲート) (#636, #637)
- L2-0 ワークフロー刷新 + 旧ロール用語掃除 (#448, #449, #472, #473, #595, #597)
- L2 再定義 + L6/L7 削除 + L8→L6 リナンバー (#446, #447)
- markdownlint-cli2 導入 + 既存違反修正 (MD022/031/032/040, MD029/038/028, MD024 siblings_only) (#474, #494, #500, #501, #502)
- empirical-prompt-tuning で 5 スキル改善 (#475, #487, #511, #537)
- `/iterate-review` skill 新設 + `/review-pr` 機能整理 (review-fix ループ自動化) (#706)
- `/close-issue` skill (issue クローズ責務を分離) (#594, #602, #606, #607, #629)
- `claude/*` ブランチ自動削除機構 (#708, #732)
- CI: error.rs hint table drift check / gui-rust cargo test --lib / artifact zip versioning (#611, #616, #622, #686, #692, #715, #751, #754)
- リリース手動手順 (release-strategy.md → release-process.md にリネーム) (#461, #547)
- ESLint で window.confirm/alert/prompt を block (#643, #684)

### Changed

- subprocess 起動を tokio::process::Command に統一 (gui spawn 統一、Lane VII) (#727, #740)
- preuse-hook を exit 2 block → permissionDecision=ask へ (#559, #561)
- issue_close hook を bulk mode に緩和 (#485, #491)
- review-pr skill レビュー専用セッション前提に一本化 (#505, #506)
- review-pr: Iter 2 追記 + scope-guard 逆方向例外 + 摘出課題二択強制 + 環境制約節 + Round N (#562, #563, #564, #565, #567)
- review-pr: checkout 禁止を read 目的に緩和 (#673, #674)
- guard をプログラム結合から運用連携に転換 (#454, #496)
- SideRail 全体削除 (#677, #739)
- `*Error` / `*ErrorHint` 並列構造を unified `*ErrorState` に集約 (#694, #745)
- 残 4 site の `String(e)` を `appErrorMessage(e)` に置き換え (Lane II-b) (#678, #718)
- metadataStore `*ErrorHint` lifecycle pinning (#691, #716)

### Fixed

- scorebar V2 (`_has_scorebar_v2`) を two-path OR semantics に変更 (Primary=absolute `_EMBLEM_POSITIONS` + Rescue=dynamic span + `_EMBLEM_RELATIVE_POSITIONS`)。1080p OBS validated set (20260116/118/119/219) は Primary で完全無回帰、4K Game DVR の HUD scale 差異は Rescue path で救済 (#522)
- Portable ZIP の `integrity-manifest.json` を BOM-less UTF-8 で書き出すように修正 (#729)。`scripts/build-portable-zip.ps1` で `Set-Content -Encoding UTF8` を使うと Windows PowerShell 5.1 (`powershell.exe`) では UTF-8 with BOM を emit し、Tauri GUI 起動時の integrity-check (`serde_json::from_str`) と CLI `--version` の integrity-check (`json.loads`) が双方 BOM 拒否で fail していた。PS 6.0+ (`pwsh`) では BOM-less だったため CI smoke (`shell: pwsh`) が本 bug を mask。`[IO.File]::WriteAllText` + `UTF8Encoding($false)` で PS-agnostic に変更
- 日本語 path で subprocess cp932 失敗 (#656, #657)
- detect 子プロセスの UTF-8 stdout 強制 + lossy decode (#656, #662)
- start_detect 失敗を可視化 + python -m フォールバック (#646, #647)
- detecting ログを overflow: auto + auto-scroll 化 (#639, #641)
- parse_detect_progress_line silent skip を warn 出力に (#648, #731)
- run_split / --from-metadata で brightness_samples を書く (#644, #734)
- scorebar 分類進捗を Refining bar に統合 (#664, #666)
- scorebar classify_blackout に対称 re-probe fallback (#524, #552)
- scorebar V2 で emblem 位置を動的検出し 4K Game DVR 対応 (#522, #525)
- NVENC/AMF 起動失敗 stderr を ffmpeg 8.1 BtbN LGPL に対応 (#604, #609)
- VP9 を NVDEC cuvid から外し soft decode 経路に (#538, #549)
- production build CMD 窓を抑止 (#679, #720)
- StateSwitcher を dev only に絞り topBar との z-index 重複を解消 (#653, #675)
- PreviewScreen state mutation flow + dirty consume confirm (#589, #628)
- get-pip.py SHA pin を pypa/get-pip versioned tag URL に切替 (#681, #703)
- get-pip.py SHA256 pin を PyPA 最新版に更新 (#649, #651)
- Tests.ps1 に UTF-8 BOM 付与 (PS5.1 parse fix) (#704, #713)
- pyproject packages.find 明示 + license SPDX 新形式 (#469, #489)
- markdownlint nested gui/node_modules / build/** を ignore に追加 (#700, #717, #723, #724)
- BtbN LGPL 方針を code/test/docs サイドに浸透 (#508, #535)

### Internal

- L2 開発ロードマップ更新 (8 → 11 → 13 group / 6 → 8 lane wave) (#683, #709, #738)
- Phase 0 計測結果反映 + feasibility.md Electron-vs-Tauri (#450, #467, #468, #470, #471)
- GUI handoff bundle 取込み (#105, #453)
- Lane V Phase 1 (Group I) post-#663 hint UI cleanup spec + 実装計画 (#691, #693, #695, #697, #698, #712)
- L2 Lane I-B Group B spec + plan (#644, #648, #679, #711)
- L2 Lane IV-c Group H spec + plan + plan-fix (#365, #643, #690)
- Lane VI / Group L — hook test infra + resume-plan handoff 規約 (#710, #722, #744)
- workflow / CI / docs 仕上げ (Group G) (#458, #624, #682, #688)
- L2 (v0.2.0) 残作業 roadmap (8 brainstorming groups) (#683)
- developer-setup: venv Permission denied トラブルシュート追記 (#431, #566)
- detection_params 型違反 + Rust load_metadata エラーパステスト追加 (#520, #521, #530)
- baseline を scorebar-on semantics に移行、20260118 の 4 件非FL を除外 (#529, #536)
- legacy 20260118 Match 8 end を 6184.0 → 6465.25 に更新 (#560, #575)
- build-portable-zip.ps1 に Pester v5 テスト追加 (#528, #548)
- launcher template の exit code 伝搬 idiom に Pester regression 追加 (#583, #584)
- release.yml smoke-test Level B 追加 (#572, #579)
- ci(release): build-windows に Portable ZIP smoke-test ステップ追加 (#557, #558)
- CI/Release 軽量化: 二重 zip + shared FFmpeg + cache (#551, #555)
- CI artifact zip 名にバージョン番号を含める (#616, #686)
- CI artifact 名から `-portable` を削除 (#751, #754)
- Stop hook 診断ログ追加 (worktree dir cleanup 切り分け) (#477, #707)
- worktree 残骸 sweep スクリプト (#477, #493)
- CLAUDE.md / project skill / hook の plugin・system プロンプト重複整理 (#667)
- PR 作成・レビュー時の base 同期 + 並行 PR + 摘出処置運用化 (#659, #660)
- archive: l1-detection-redesign.md (#476, #492)
- develop-0.2.0 init (version bump + tools relocation) (#443)
- L1 リリース完了反映 + ロードマップ目標日更新 (#444, #445)
- ffmpeg fps filter の version 依存制約を docs に明記 (#577, #592)
- stderr_tail 末尾長を定数化 (#413, #630)
- AppError stale docstring 更新 (#699, #746)
- ui-architecture §4.9 catch 漏れ AppError fallback 追加 (#696)
- `/close-issue` skill: Refs #N fallback + Iter 2 検証 + reports 整理 (#606, #607, #629)

## [0.1.1] - 2026-04-20

L1 (試合分割) の正式リリース版。2026-04-17 に `v0.1.0-preview` として公開後、品質向上を経て `v0.1.1` として正式リリース。verbose 出力の網羅的改善、GPU/CPU 検知精度の一致、進捗バー UX 修正、メタデータ拡充、運用ルール強化。

### Added

- verbose ヘッダに HW 情報 (CPU/GPU/Memory/Disk) を表示 (#377)
- verbose 出力に Pass 1/Pass 2/Scorebar/Splitting の elapsed time を表示 (#386, #387)
- verbose 出力に Filter drop 内訳を表示 (#388)
- verbose 出力に検知候補 metadata、resolved workers 数を表示 (#389)
- キャッシュヒット時にも verbose で検知パラメータを表示 (#380)
- Match 一覧に `[unknown]` マーカーを表示 (#382)
- metadata.json に `detection_params` / `detected_at` を記録 (#370)
- metadata.json の `gaps` 配列に raw 秒フィールドを追加 (#369)
- metadata.json の `output_file` パスを POSIX 区切りに正規化 (#371)
- コーデックに基づく GPU/CPU モード自動選択 (#334)
- 分割前にディスク空き容量をチェック (#338)
- `-V` / `--version` ショートフラグと verbose パイプライン統計 (#336, #337)
- verbose エラー詳細 (traceback + ffmpeg stderr) を出力 (#351)
- CLI 出力仕様マトリクス docs (`docs/output-spec.md`) を新設 (#405)
- 過去 PR audit レポート (`docs/audits/2026-04-19-pr-audit.md`) を追加 (#410)
- ロール定義にユーザー確認ルール / Memory 活用ガイダンスを追加 (#400)
- Director / Lead Engineer 行動規範 A/B/C を docs に明文化 (#399)
- PreToolUse hook で確認ゲートを実装 (#401)
- Quick Start に venv セットアップ手順を追記 (#364)
- 出力ファイル一覧に `.detection_cache.json` を追記 (#360)
- `--gpu` がデフォルト off の理由を README / CLI ヘルプに補足 (#332)

### Changed

- verbose 出力の `audio=on/off` を実態に合わせ `audio=frozen` に修正 (#384)
- verbose 出力の ffmpeg version 文字列を簡潔化 (`8.1` 等) (#383)
- verbose 出力の Total time 表示を全パス (cache hit + split 含む) に統一 (#381)
- `-q` モードで dry-run 通知の出力を抑制 (#418)
- CLI で `-q` / `-v` / `--gpu` / `--no-gpu` 同時指定を排他エラー化 (#419)

### Fixed

- 進捗バー (Detecting/Refining/Scorebar) の上書き表示問題 (#368, #393)
- Pass 2 中の進捗無音問題 (#366)
- 進捗バー ETA ラベル明確化、split 出力表示改善 (#328, #329, #331)
- GPU mode で CPU と Match 境界が一致しない問題 (#392, sample grid 整列)
- Pass 1 統計の verbose 表示漏れ (#386)
- Pass 1 borderline frame 対策 (A3/A4 hysteresis) (#361)
- GPU chunk progress をリアルタイムで進捗バーに反映 (#333)
- 凍結中の音声スキャンをデフォルトで無効化 (#327)
- `scan_fanfare_hits` の FileNotFoundError を `VideoProcessingError` でラップ (#350)
- CLI エラー表示を output matrix v2 (19a/19b/19c) に整合 (#428)

### Internal

- テスト網羅性向上 (オプション組合せ網羅、GPU chunk_timestamps parametric、system_info Linux/Darwin パーサ実解析、metadata gaps shape、Pass 2 進捗、B グループカバレッジ等)
- `setup-session` の開発ブランチ参照とパスを動的化
