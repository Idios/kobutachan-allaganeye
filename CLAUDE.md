# Allagan Eye

## プロジェクト概要

FF14 PvPコンテンツ「フロントライン」の長時間録画動画（OBS, MP4/MKV）から、試合単位の分割・ハイライト抽出・投稿価値の評価を段階的に自動化するCLIツール。

### 段階的アーキテクチャ

**コアレイヤー（L1〜L6）**

| レイヤー | 処理 | 技術 | 状態 |
| --- | --- | --- | --- |
| L1: 試合分割 | 暗転検知で試合単位に分割 | FFmpeg（検知+分割） | **リリース済み** (v0.1.0-preview 2026-04-17, v0.1.1 2026-04-20) |
| L2: 配布・統合 | GUI + ゼロ環境構築配布 | Tauri 2.x + React 19 + TS | **開発中** |
| L3 (new): 配信形式対応 + 性能改善 | minimap 切抜き / masked (チャット欄画像マスク) 品質 / export 並列・ZIP size・detect 高速化 (2026-07-06 rescope #872: VTuber 動画対応は v0.4.0 期へ後送、GUI responsiveness は v0.3.0 外 #670) | OpenCV / template matching / NVENC・QSV・AMF / Tauri | **開発中** (v0.3.0 target) |
| L4 (former L3): メタデータ化 | キルログ・音声・チャットをタイムスタンプ化 | Tesseract / Whisper | 未着手 |
| L5 (former L4): 価値評価 | 抽出データを ML が判定 | ローカル ML（scikit-learn 等） | 未着手 |
| L6 (former L5): 自動編集 | 判定に基づき動画切り出し・投稿提案 | MoviePy / FFmpeg | 未着手 |

**拡張レイヤー（L7、暫定）**

| レイヤー | 処理 | 状態 |
| --- | --- | --- |
| L7 (former L6): プライバシー・精密分割 | プレイヤー名ぼかし、再エンコード分割 | 計画中 |

**設計原則**: ツールの独立性・ポータビリティを保つため、Web 経由のサービスや大規模モデルをツールの実行時依存に含めない。AI（LLM）はツール自体の設計と評価にのみ用いる。動画編集・変換は FFmpeg/OpenCV 等のライブラリで実行する。ローカル ML（scikit-learn 等の軽量モデル）は信号処理・分類で必要に応じて使用してよい。

## コマンド

詳細は [`docs/testing-guide.md`](docs/testing-guide.md) を参照（GPU テスト間インターバル、サンプルデータ設定等）。CLI 構文は [`docs/cli-spec.md`](docs/cli-spec.md)、オプション組み合わせごとの出力仕様は [`docs/output-spec.md`](docs/output-spec.md) (#405 マトリクス v2)、CLI と GUI の全体構成・起動経路は [`docs/system-architecture.md`](docs/system-architecture.md) (#527) を参照。

> **配布物の起動経路**: Portable ZIP の `allaganeye.bat` 引数なしダブルクリック (v0.2.0+ #617) = GUI (`allaganeye-gui.exe`) 起動 / `allaganeye.bat <args>` = CLI 起動 / Tauri bundle の `allaganeye-gui.exe` 直接 = GUI 起動。**別 exe 方式** (#527 で確定)。

```bash
# テスト
pytest                          # 全テスト（slowマーカー除外）
pytest -m slow                  # 動画ファイル必要なテスト
pytest tests/test_detector.py   # 単体テスト

# Lint / 型チェック
ruff check .
ruff format --check .
pyright
bash scripts/check-markdownlint.sh   # markdownlint (CI と同 version で全 .md チェック、--fix で自動修正)
# violation の fix recipe / ignore pattern 規約は docs/markdownlint-guide.md を参照

# CLI
allaganeye detect <video_path>                          # 検知のみ (metadata.json 出力、#463)
allaganeye split --from-metadata <metadata.json>        # metadata.json から分割のみ (#463)
allaganeye split <video_path>           # 試合分割 (detect + split の一気通貫、後方互換)
allaganeye split <video_path> -o <dir>  # 出力先指定
allaganeye split <video_path> --gpu     # GPU アクセラレーション検知
allaganeye split <video_path> --workers 8  # ワーカー数指定
allaganeye split <video_path> --no-cache   # キャッシュ無視で再検知
allaganeye split <video_path> --no-audio   # 音声昇格の無効化フラグ（#327 で凍結中のため現在は常にスキップ）
allaganeye split <video_path> --quiet      # 進捗抑制（出力ファイルのみ）
allaganeye split <video_path> -v           # verbose（環境情報・パイプライン統計を表示、#336）
allaganeye --version                       # バージョン表示（短縮形: -V、#337）
allaganeye debug-brightness <video_path>   # フレーム輝度 CSV 出力

# GUI (L2a Tauri、#483 で bootstrap)
# 詳細は docs/gui-development.md を参照
cd gui && npm install                   # 初回セットアップ
cd gui && npm run tauri dev             # dev ウィンドウ起動
cd gui && npm test                      # vitest 単体テスト
cd gui && npm run lint                  # eslint
cd gui && npm run typecheck             # tsc --noEmit
cd gui && npm run build                 # vite build (gui/dist/ 生成)
cd gui/src-tauri && cargo check         # Rust 型/依存チェック
```

## アーキテクチャ

### データフロー（L1）

```text
MP4/MKV入力 → probe.py（ffprobe でメタデータ取得）
           → detector.py（ffmpeg 並列 -ss プローブで暗転検知 → 試合境界タイムスタンプ）
           → splitter.py（FFmpeg -c copy で無劣化分割）
           → 出力: 試合ごとのMP4 + metadata.json
```

### モジュール構成

| モジュール | 責務 |
| --- | --- |
| `cli.py` | Typer CLIエントリポイント。コマンドルーティング |
| `config.py` | 設定管理（検知閾値、出力パス等） |
| `exceptions.py` | エラークラス + exit code マッピング |
| `ffmpeg_path.py` | ffmpeg/ffprobe のパス自動検索（winget, Homebrew, PATH, 環境変数） |
| `commands/split_matches.py` | split コマンドのオーケストレーション。タイムスタンプ表示・gap 検出・sample_interval 自動調整 |
| `commands/debug_brightness.py` | debug-brightness コマンド。フレーム輝度を CSV 出力（閾値チューニング用） |
| `video/probe.py` | ffprobe でメタデータ取得（解像度、fps、長さ） |
| `video/detector.py` | ffmpeg 並列プローブで暗転検知、試合境界抽出（CPU モード） |
| `video/gpu_detector.py` | GPU アクセラレーション検知（チャンク並列デコード） |
| `video/capture_region.py` | 検出 ROI（`CaptureRegion`）の解決。scorebar 帯 anchor の多フレーム consensus（`detect_scorebar_band_region`）/ FULL_FRAME 縮退。`--vtuber` gate 内でのみ有効（L3 Phase 1。検出 subsystem の現状 map は [docs/detection-map.md](docs/detection-map.md)）。解決結果は metadata.json `capture_regions` に永続化 (#810、RegionTimeline serialize 形 + 縮退 provenance) |
| `video/presence.py` | presence（scorebar 在/不在）ベースの試合検出エンジン + GT 突合ハーネス基盤（L3 Phase 1。2 信号 fusion 再アーキ spec 参照） |
| `video/scorebar.py` | スコアバーフィルタリング（暗転分類・試合内/非FL判定）+ 音声昇格 |
| `video/splitter.py` | FFmpeg で動画分割（-c copy） |
| `audio/extract.py` | ffmpeg で音声 PCM 抽出 |
| `audio/features.py` | log-mel スペクトログラム計算と保存 |
| `audio/matcher.py` | 参照 BGM と target の相互相関で peak 検出 |
| `audio/scan.py` | 動画全域を走査して Fanfare ピークを返す |
| `audio/refs/` | 同梱参照特徴量（`fanfare.npz` / `war_room.npz`、#306） |
| `commands/detect.py` | detect コマンド。検知のみ実行し metadata.json を出力 (#463) |
| `detection/` | 検知パイプラインの共有ヘルパ (#463)。`format.py` (フォーマッタ) / `metadata_writer.py` (atomic read/write) |
| `gui/` | L2a Tauri GUI (React 19 + TS + Vite + Zustand + zod)。`#483` で bootstrap、`#463` で data 層、`#464` で画面骨格 + CSS Modules、`#516` で `[元に戻す]` 機能、`#514` で排他管理 (mtime 検知 + ConflictModal)、`#587` で a11y polish (focus trap / Escape / DisabledTooltip / jest-axe)。詳細は [docs/gui-development.md](docs/gui-development.md) / [docs/design/README.md](docs/design/README.md) / [docs/ui-architecture.md](docs/ui-architecture.md) / [docs/ui-interaction-spec.md](docs/ui-interaction-spec.md) (#590, UI 部品ごとの操作 → 状態遷移 / store mutation / 例外処理) / [docs/a11y-policy.md](docs/a11y-policy.md) (#587, screen reader scope / キーボード全機能 / focus visible 等) |
| `gui/src/screens/` | 5 画面 (drop / detecting / complete / preview / export) + phase reducer。#464 で追加 |
| `gui/src/components/` | 共通 UI コンポーネント (AllaganCorner / AllaganSigil / WindowChrome / BrightnessTimeline / RestoreButton / SampleModeBanner / ConflictModal 等)。#464 で追加、#633 で sample mode 全画面 read-only |
| `gui/src/state/` | Zustand store (`appStateStore` = screen + selection + detectionParams / `metadataStore` = load/apply/restore/loadSample / `recentStore` = `<install dir>/recent.json` 履歴 #571 + PR #655 Round 2 で exe ディレクトリ配置に変更) |
| `gui/src/styles/tokens.css` | `aetherTheme` の CSS 変数定義 (#464 で追加) |
| `gui/src/styles/path-display.module.css` | 5 画面横断のファイルパス表示 CSS Module (`.pathDisplay` container / `.pathSecondary` parent dir 行 RTL ellipsis truncate)、#676 で追加 (`docs/ui-interaction-spec.md §1.6` 参照) |
| `gui/src/utils/path.ts` | Windows / POSIX path 操作 utility。`stripExtendedPathPrefix` (Windows `\\?\` prefix 除去) / `joinPath` (OS-appropriate separator) / `splitPath` (fileName + parentDir 分解、#676 で追加) |
| `gui/src-tauri/` | Tauri 2 Rust バックエンド (`load_metadata` / `apply_changes` / `restore_from_original` / `check_backup_exists` / `get_metadata_mtime` / `start_export` / `enumerate_h264_encoders` (#761) / `read_recent` / `add_recent` / `clear_recent` (#571) command、axum/tower-http による動画配信は #465 で実装)。`start_export` は Python subprocess を起動して JSON Lines で進捗を受け取り、`enumerate_h264_encoders` は GPU SKU table から利用可能エンコーダスロット一覧を返す (#761) |

### 検知アルゴリズム（detector.py）

**Pass 1: 粗いスキャン**

1. `duration_hint` から `sample_interval` 秒間隔のタイムスタンプを生成（長時間動画は自動で 2-3s に調整）
2. 各タイムスタンプで `ffmpeg -threads 1 -ss {t} -i` により 1 フレームを 320x180 grayscale でデコード
3. `ThreadPoolExecutor(max_workers=min(cpu_count, 32))` で並列実行
4. 各フレームの平均輝度が `blackout_threshold` 以下なら暗転と判定
5. 連続する暗転フレームを `_group_blackout_regions()` で blackout region にマージ

**transition expansion**
6. 各暗転領域の前後で brightness < 55（`_TRANSITION_THRESHOLD`）のフレームが連続する区間を暗転領域に含めて拡張

**Pass 2: 精密計測**
7. 各暗転候補の ±5s を 0.25s 間隔で再プローブし、正確な持続時間を計測

**スコアバーフィルタリング**（`src_resolution` 提供時、CLIのデフォルトパス）
8. `filter_blackouts_with_scorebar()` で各暗転領域の前後フレームのスコアバー有無を判定し、暗転を分類（`match_boundary` / `in_match` / `non_fl`）。V2 検出 (`_has_scorebar_v2`) は 1920x1080 リサイズ後に **two-path OR semantics** で GC 紋章 3 点 AND 判定 (#307, #522): **Primary=absolute `_EMBLEM_POSITIONS`** (pre-#522 validated)、**Rescue=dynamic span (`_find_scorebar_horizontal_range`) + `_EMBLEM_RELATIVE_POSITIONS` 相対比**。Primary pass で short-circuit、両 path fail で False。`raw_rgb` None / opencv 未インストール時のみ None → V1 (`_has_scorebar`, channel-std + edge) フォールバック。1080p OBS validated set の挙動を完全保持しつつ 4K Game DVR の HUD スケール差異は Rescue で救済
9. `non_fl`（非FL暗転）と短い `in_match`（試合内暗転）を除外。隣接する `match_boundary` ペア間の短いギャップをマージ

**音声昇格**（#288。**現在は凍結中 #327**: `AUDIO_FROZEN=True` のため `--no-audio` の値に関わらずスキャンは常にスキップされ、verbose では `audio=frozen` と表示される #384。以下は解凍時の挙動）

- `audio/scan.py` で動画全域の音声から Fanfare ピーク（log-mel 相関 sim ≥ 0.65）を抽出
- `in_match` 分類された暗転のうち、暗転終了後 0-60s 以内に Fanfare ピークがあるものを `match_boundary` に昇格
- スコアバー残像で誤分類された試合境界（例: 2026-04-08 57:53）を救済
- 既知の制約: Fanfare は試合中にも弱いピーク（sim 0.65-0.75）を出すため、本条件のみでは偽陽性が混入しうる。WR 参照は #306 で同梱済み（`war_room.npz`）。解凍時に WR→Fanfare 間隔による (B) 条件を追加して偽陽性を除去する計画（#327 の解凍判断と合わせて再評価）

**フィルタリング・抽出**
10. `min(min_blackout_duration, _REFINED_MIN_BLACKOUT)` 未満の短い暗転を除外（リスポーン暗転の誤判定防止）
11. blackout region 間の非暗転区間を試合セグメントとして抽出（暗転内パディング付き）

**検出の動作確認済み環境と制限事項**

- 動作確認済み: ハイスペック PC（高速 SSD、高性能 GPU）での OBS 録画。試合間暗転 2-5 秒程度
- 未検証: 低スペック環境でローディング画面が長い（10 秒超）ケース
- 既知の制限: ローディング画面が純粋な黒画面でなく UI 要素（スピナー、ロゴ等）を含む場合、brightness が 15-55 の範囲で変動し暗転が分断されることがある。分断された各区間が `min_blackout_duration` 未満になると試合境界を検出できない
- 既知の制限 (legacy fps filter path、#576 で v0.3.0 構造的対策実装済): ffmpeg `fps` filter のフレーム選択は version 依存で、8.1 で output PTS と実フレーム内容に最大 ~1.1s のオフセットが発生する事例あり (#575)。v0.3.0 default の新 path (`-vf select='not(mod(n,N))'` + dual seek、frame-index ベース) は ffmpeg version 非依存。緊急 rollback が必要な場合のみ env var `ALLAGANEYE_DETECT_FPS_FILTER=1` で legacy path に戻せる (transitional、v0.3.x patch release で削除予定)。判定 flow は [`docs/testing-guide.md`](docs/testing-guide.md) §「baseline drift の判定」、検証データは [`docs/video-processing.md`](docs/video-processing.md) §「ffmpeg fps filter の version 依存制約」を参照
- post-match trailing の扱い ([#805](https://github.com/Idios/kobutachan-allaganeye/issues/805) 段階2 Phase 1 で default path 非破壊化済): 試合終了後の trailing (lobby/city) は `_flag_post_match_trailing` (#797 の不可逆削除を置換) が **scorebar 不在を根拠に `post_match: true` フラグ付与**するのみで、削除はしない。default split (MP4) からは除外しつつ metadata には保持する (detect / split --from-metadata / export 全経路でフラグ保持 + MP4 除外)。これにより「scorebar FN 環境 (未対応 HUD layout / 4K Game DVR 等) で実試合の trailing を silent に削除しうる」という旧 silent-loss リスクは構造的に消滅した (削除という不可逆操作自体が存在しない)。視覚 UX (badge/dimming + ExportScreen non-selectable row) は Phase 2 で #805 にて継続

**GPU モード** (`--gpu`)

- CPU モードの Pass 1 を GPU チャンク並列デコードで代替（`gpu_detector.py`）
- 動画を N チャンク（短動画は `min(cpu_count, 16)`、長動画は `_TARGET_CHUNK_WALL_SECS=90s` を目安に `_MAX_CHUNKS=32` まで細分化 / #437）に分割し、各チャンクで長寿命の ffmpeg プロセスを `-hwaccel auto` + `fps` フィルタで起動
- ffmpeg 並列上限は `max_parallel = min(cpu_count, 16)` で固定、長動画では chunks > max_parallel となり wave 実行（chunk 完了ごとにラベル更新頻度を確保）
- GPU 初期化コストを分散し、1プロセスあたり多数フレームをデコードすることで効率化
- Pass 1 以降の処理（transition expansion, Pass 2, フィルタリング）は CPU/GPU 共通
- GPU 利用不可時は自動で CPU モードにフォールバック
- vendor 自動選択 (#546 / #553 / #550 / #582): `allaganeye.system_info.probe_gpu_vendors()` で検出した GPU から `_VENDOR_PREFERENCE = ("nvidia", "amd", "intel")` 順で選択。実装済み vendor は NVIDIA (cuvid, #546) / AMD (d3d11va + hwdownload, #553) / Intel (QSV + hwdownload, #550 h264/hevc/av1 + #582 vp9) の 3 つ。default (auto) は NVIDIA > AMD > Intel の preference 順で実装済み vendor を選ぶ
- probe 結果は metadata.json `system_info` フィールドに記録され (#591)、GUI export 画面が H.264 再エンコードのエンコーダ選択 (NVENC / QSV / AMF / libx264 fallback) に使う。`--no-gpu` 指定時でも probe は実行し `gpu_vendors_available` を埋めるが、`gpu_vendor_used` は `null` になる
- GUI export の H.264 再エンコード (#761): GUI 書き出し開始時に `start_export` Tauri コマンドへ単発 invoke → Python subprocess が `enumerate_h264_encoders` で決定した N スロット分の ffmpeg を pool 並列で spawn。GPU 初期化失敗 (NVENC `No NVENC capable devices found` 等) は Python 側で検知して libx264 で 1 回 retry し、`stage="fallback"` の `export-progress` イベントを emit (フロントエンドが per-match notice 表示)
- NVENC 選択時は NVDEC zero-copy decode 経路 (`-hwaccel cuda -hwaccel_output_format cuda` を `-i` の前に挿入、#791)。NVENC encoder init failure に加え NVDEC decode-stage 失敗 (CUDA dynamic load / device creation / decoder device setup / `cuvidCreateDecoder` / `hwaccel transfer data failed` 等) も libx264 fallback の trigger 対象 (`_GPU_ENCODER_FAILURE_PATTERNS[NVENC]` 計 14 pattern = encoder-init 3 + NVDEC 11 を 3 layer 構成: Layer 1 CUDA dynamic load 2 / Layer 2 device creation・setup 5 / Layer 3 decoder・transfer 4)。QSV/AMF 側の decode hwaccel は #762 で実機検証込みで wire 予定 (現状 `_DECODE_HWACCEL_ARGS` で `()` no-op)

### Exit Codes

| コード | 意味 |
| --- | --- |
| 0 | 正常終了 |
| 1 | 一般エラー |
| 2 | 入力ファイル不正（存在しない、未対応形式） |
| 3 | FFmpeg / ffprobe エラー |
| 4 | 検知失敗（試合境界が見つからない） |
| 5 | 設定値不正（パラメータの範囲外等） |
| 7 | 同梱物欠損 (Portable ZIP integrity-manifest.json で listed file が missing / size 不一致、#668) |

### 外部依存

- **ffmpeg / ffprobe**: 4.1 以上。PATH、`ALLAGANEYE_FFMPEG` 環境変数、または OS 別既知パスから自動検索（`allaganeye/ffmpeg_path.py`）。配布版・開発環境ともに LGPLv3 版 (BtbN FFmpeg-Builds `win64-lgpl-shared`、libdav1d 入り) の使用を推奨 (#508)
  - Windows: `ALLAGANEYE_FFMPEG` で BtbN LGPL ビルドを指定する運用を推奨。既存 winget (`Gyan.FFmpeg`, GPL) のインストール先も後方互換で自動検索される
  - macOS: Homebrew (`/opt/homebrew/bin`, `/usr/local/bin`) を自動検索
- **Python パッケージ**: numpy, typer, scipy, opencv-python-headless（scorebar V2 検出で使用 #307）
- **対応プラットフォーム**: Windows のみ（実動画での動作確認済み）。Linux・macOS は未検証（CI では lint/型チェックのみ ubuntu で実行）

### 動画サンプルデータ

テスト・開発用の録画データは環境変数 `ALLAGANEYE_SAMPLE_VIDEO_DIR` で指定する。

```bash
# Windows (デフォルトの録画保存先)
set ALLAGANEYE_SAMPLE_VIDEO_DIR=E:\royalstraightflesh\videos

# Linux / macOS
export ALLAGANEYE_SAMPLE_VIDEO_DIR=/path/to/videos
```

- MKV: OBSの長時間録画（30-80GB、複数試合を含む）
- サブディレクトリ（`20260116/` 等）: 手動で試合分割済みのMP4（`YYYYMMDD_N.mp4`）
- 未設定の場合、`sample_video_dir` fixture を使うテスト（`slow` マーカー）はスキップされる
- VTuber/masked 系 slow テスト用 VOD は別変数 `ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER`（既定 `E:/allaganeye-samples`）。詳細は [`docs/testing-guide.md`](docs/testing-guide.md) §サンプル動画データの設定

## Portable ZIP 哲学

ツール側はユーザー環境を変更しない。ファイル関連付け / レジストリ / PATH / 自動起動登録は提案禁止。展開 = インストール、削除 = アンインストール の Portable ZIP 哲学を維持する (2026-04-27 ユーザー方針確定)。

## 外部依存 URL 規約

> §アーキテクチャ §外部依存 (runtime deps: ffmpeg / Python pkg / platforms) とは別。本 § は **DL URL の pin ルール**。

外部依存 (Python / npm / cargo / OS binary tarball 等) の DL コードは **immutable URL** で pin する。詳細・受け入れ可能ソース・禁止パターン・検証手順は [`docs/l2-workflow.md` §外部依存規約](docs/l2-workflow.md#外部依存規約-649651703721-教訓) を参照。

代表事例: get-pip.py SHA pin (#649→#651→#703)、BtbN FFmpeg monthly snapshot (#721)。

## セキュリティ検査（allaganeye-guard 運用連携）

外部ユーザーから受領した動画ファイルを処理する前に、独立ツール `allaganeye-guard` でセキュリティ検査を行う。**プログラムレベルでの結合は行わず**、エージェント (= Claude + 人間メンテナ Idios) が手動で `allaganeye-guard verify` を実行する運用ルールとする (2026-04-21 方針確定、#454 参照)。詳細は [`docs/guard-integration.md`](docs/guard-integration.md)、外部ユーザー向けバグ報告案内は [`docs/bug-report-guide.md`](docs/bug-report-guide.md) を参照。

- **リポジトリ**: [Idios/kobutachan-allaganeye-guard](https://github.com/Idios/kobutachan-allaganeye-guard) (独立パッケージ)
- **運用**: `allaganeye-guard verify <file>` → PASS (exit 0 / 1) 後に `allaganeye split` で処理
- **外部動画データの検査**: Idios 以外のユーザーが issue・PR に添付した動画は、`allaganeye-guard verify` が PASS するまで処理しない (`docs/guard-integration.md` §5 参照)
- allaganeye 側に guard を import する実装・optional-deps・統合 exit code は持たない (独立性維持)

## リリース戦略

詳細は [`docs/release-process.md`](docs/release-process.md) を参照。Patch release (v0.M.N → v0.M.(N+1)) は [§Patch release の Track 構造](docs/release-process.md#patch-release-の-track-構造) (Track A-D 並列化) に従う。

## 開発ワークフロー

L2 からは**単一ワークツリー + skill ベースディスパッチ**を採用。詳細は `docs/l2-workflow.md` を参照。

- 既存 skill: `/review-pr`, `/iterate-review`, `/enforce-acceptance-criteria`, `/scope-guard`, `/create-task`, `/close-issue`, `/release`
- 計画立案・実装・PR テストは Plan モード + 通常ツール + TodoWrite で代替
- ユーザー (Idios) が戦略・方針を判断し、Claude は選択肢提示と実装を担う
- skill (`.claude/skills/*/SKILL.md`) 改修 PR は mizchi `empirical-prompt-tuning` protocol に従う。詳細は [`docs/l2-workflow.md` §skill 改修ワークフロー](docs/l2-workflow.md#skill-改修ワークフロー-empirical-prompt-tuning) を参照

### `/iterate-review` workflow と (A) 強優先方針

PR 作成後は `/iterate-review <PR#>` で review-fix ループを自走させる (user 手動 or agent 自動)。本 skill は **「指摘は原則すべて PR 内対応」** の (A) 強優先方針 + (B) 厳格 3 条件 AND + 握り潰し防止 validation により、CI failure / latent issue / 隣接 lint 違反 等を当 PR 内で消化し、派生 issue 数を最小化する (issue 数収束)。

### Iron Law と強制メカニズム

プロジェクト基本ルールは `.claude/hooks/session-start.sh` の Iron Law (5 条 + Red Flags 表) として毎セッション先頭に注入される。条文と Red Flags の正は同ファイル。違反が 1% でも疑われる状況では STOP し `AskUserQuestion` でユーザー確認する。

強制メカニズム (7 層) の詳細は [docs/l2-workflow.md](docs/l2-workflow.md) §強制メカニズム を参照。

### Memory 活用 (ユーザー訂正の蓄積)

ユーザーが Claude の判断を訂正した場合、訂正内容を `feedback_*.md` 形式でメモリに蓄積する。蓄積対象の例:

- 優先度判定基準の訂正 (「この観点は P1」「このレベルの UX 品質は P3」等)
- ラベル振り分け基準の訂正 (`deferred` / スコープラベル判定の根拠)
- レビュー判断基準の訂正
- bulk 操作の閾値・順序の訂正

蓄積した基準を次セッション以降で読み返し、同じ訂正を繰り返さないようにする。個別セッションの一時状態 (進行中の PR 番号・作業中の issue 等) は memory ではなく TodoWrite / plan に残す。

### バグ修正時の方針

バグ修正は「修正実装」だけで完了せず、**根本原因分析 + 類似バグ調査 + 必要なら追加 issue 起票** をセットで行う。指示通りに直すだけでは同種のバグが残り続けるため、根本原因の横展開で品質を底上げする。

#### encoding boundary audit checklist (#656/#657/#662 教訓)

subprocess / IPC / OS API を介した encoding fix を行うときは、**以下 3 層をすべて audit** すること。1 層だけ fix すると別層で再発する (F4: PR #657 Python 側 fix → #662 Rust 側追加 fix が必要だった事例)。

1. **Python 側** (CLI / scripts): `subprocess.Popen(..., encoding=...)` / `sys.stdout.reconfigure(encoding='utf-8')` / `os.fsencode` / `Path` の Unicode 扱い
2. **Rust 側** (Tauri / `gui/src-tauri/`): `tokio::process::Command` の stdin/stdout encoding / `OsString` / `Path::to_string_lossy()` の `\u{FFFD}` 混入 / `serde_json::from_str` の BOM 拒否
3. **OS code page**: Windows なら `chcp 65001` 想定の動作 / cp932 環境での fallback / GitHub Actions runner (`pwsh` UTF-8 BOM-less 出力 vs PowerShell 5.1 BOM 付き)

実装 PR では各 fix が 3 層のうちどこを touch するか PR 本文に明示。3 層に跨る fix は **Phase 分割の対象**になりうる (`docs/refactor-pattern.md`)。

#### `/codex:rescue` 限定使用 (C4、spec O5 (b) 確定)

根本原因分析 / 類似バグ調査 phase で `/codex:rescue` を限定的に併用してよい。常用は禁止 (Codex review = tier 1 `codex-companion.mjs review` を優先)。詳細は §Codex 運用 §rescue を参照。

### 大規模 refactor の Phase 分割

単一 PR で touched files > 30 file or diff > 1000 line を超えそうな refactor は [`docs/refactor-pattern.md`](docs/refactor-pattern.md) §1 適用条件を確認し、Phase 分割を検討する。AppError migration (#663→#689→#714/716/725/730/733→#745→#746) が reference 実例。

## Plugin との関係 (override 宣言)

session 先頭で有効化されている plugin (`superpowers` v5.0.7 / `andrej-karpathy-skills` v1.0.0) のプロセス規律を以下のとおり全面採用する。本 project と plugin の見解が分かれる点は project 側の立場をここで明示する。

- **TDD** (`superpowers:test-driven-development`): HARD-GATE を全面採用。Red-Green-Refactor (NO PRODUCTION CODE WITHOUT FAILING TEST FIRST) を遵守する
- **Brainstorming** (`superpowers:brainstorming`): creative work (新規 feature / bug fix / refactor) 前に必ず invoke する
- **Plan execution** (`superpowers:subagent-driven-development`): plan 実行時は fresh subagent + 2-stage review (spec + code quality) を採用する
- **Code review** (`superpowers:requesting-code-review` subagent): `/review-pr` が code quality 部分を当 subagent に委譲する形で利用する。base sync / acceptance criteria gate / triage / post-merge handoff の project 固有部分は維持
- **Worktree**: トリガー別に住み分け。
  - Idios が新規セッションを立ち上げた場合: Claude Code session が自動生成する `.claude/worktrees/<name>/` を使用 (L2 workflow §単一ワークツリー)
  - plugin のワークフロー (例: `superpowers:using-git-worktrees`) が worktree 作成を要求する場合: plugin の per-feature 手動 worktree を使用

## Codex 運用

Codex (`openai-codex` プラグイン 1.0.4) を Iron Law 3 / 5 と衝突しない形で workflow に統合する。設計原則: **Codex は adversarial second-opinion 専用、自身に独断 fix させない**。詳細 spec は [`docs/superpowers/specs/2026-05-17-v020-v021-retro-codex-integration-design.md`](docs/superpowers/specs/2026-05-17-v020-v021-retro-codex-integration-design.md) §4.3 / §7。

### review / adversarial-review (C2 / C3)

- 全 turn 自動の Stop-time review gate は **OFF のまま**保持 (spec O1 (b) 確定)
- 代わりに `/review-pr` (Step 5a) と `/iterate-review` 内で**明示 invocation**
- Iron Law 6 Pre-flight Step 5 として Codex adversarial-review を必ず実行 ([`docs/l2-workflow.md` §PR 作成 Pre-flight](docs/l2-workflow.md#pr-作成-pre-flight-iron-law-6-サブ条))
- **invocation path は 3-tier** (#795): slash command `/codex:adversarial-review` は plugin frontmatter `disable-model-invocation: true` により agent から invoke 不可のため、**tier 1 (default) = companion script 直接呼び出し** (`codex-companion.mjs adversarial-review`、本物の Codex を agent 一気通貫) / tier 2 (fallback) = Codex CLI fail 時のみ superpowers subagent + Codex fallback notice (C6) / tier 3 (escalation) = Idios が直接 slash command invoke。詳細は [`docs/l2-workflow.md` §Step 5 の invocation path](docs/l2-workflow.md#step-5-の-invocation-path-3-tier795)

### rescue (C4)

- `/codex:rescue` は **root-cause 調査専用** (spec O5 (b) 確定、常用禁止)
- rescue の slash command は `disable-model-invocation` **なし** = agent からの invoke 可 (3-tier (#795) の制約は review / adversarial-review のみ。rescue を tier 3 = Idios 専用と誤読しない)
- 機能実装 / refactor / docs 改修等の default invocation は禁止
- 使う場合は rescue prompt に `<action_safety>` で「scope を超える finding → 独断 fix 禁止、BLOCKED 報告」を必ず明記 (M3 整合)
- `--write` default のままだが、Codex が write する場合は staging のみ、commit / push は controller の明示指示後
- rescue 完了後、Idios に finding を提示し AskUserQuestion で「本 PR 修正 / 別 issue / 無視」の 3 択
- `/scope-guard` skill が Codex commit (`git log --author='codex\|Codex'`) を検査範囲に含める

### Token 枯渇時の fallback (C6)

Codex CLI が rate-limit / quota / network / auth 等で fail した場合、Claude Code 側で superpowers subagent (`requesting-code-review` for review、`systematic-debugging` for rescue) を fallback として起動する。**fallback 実行時は skill report に「Codex fallback notice」を必須記載** (Iron Law 5 整合、Codex review 済との誤認防止)。

詳細 (検出条件 / 戦略 / 擬似コード example) は [`docs/l2-workflow.md` §Codex fallback](docs/l2-workflow.md#codex-fallback) を参照。

### subagent + Codex 直列構成 (C5)

大規模実装 / 重要 PR では superpowers `subagent-driven-development` で Claude 内 fresh subagent が実装 → controller が reachability 確認 → Codex review (agent 実行は `codex-companion.mjs review` = 3-tier の tier 1 と同様、slash `/codex:review` は Idios 専用) で adversarial pass → Claude + Idios で triage、の **4 stage 直列**で進める。Iron Law 6 Pre-flight Step 5 (C2、PR 作成直前 / 必須) とは別用途で、`/review-pr` 段階の **deep-dive** で使う optional flow。

詳細 (Flow 図 / 違い table / 並列ではなく直列にする理由) は [`docs/l2-workflow.md` §subagent + Codex 直列構成](docs/l2-workflow.md#subagent--codex-直列構成-c5) を参照。

## CLAUDE.md 継続改善

ユーザーから「CLAUDE.md に追記して」等の指示があった場合、このファイルを即座に更新する。
更新後は変更箇所をユーザーに報告する。

## GitHub Issue 作成ルール

詳細は [`docs/issue-policy.md`](docs/issue-policy.md) を参照。

## PR 作成ルール

PR Pre-flight・path 別自動チェック・実機検証 trigger・Self-Test Report 規約・(A) PR 内修正優先・PR 規約 (develop ベース / Closes 禁止 / 1 PR = 1 scope / session-id 等) は [`docs/l2-workflow.md`](docs/l2-workflow.md) 各 § を参照。Iron Law 6 (`.claude/hooks/session-start.sh`) も参照。

resume task prompt 生成 (skill / session が user に dispatch 用 prompt を提示する場面) は [`docs/l2-workflow.md`](docs/l2-workflow.md) §「resume-plan handoff protocol」 で定義した `EXECUTOR: self|dispatch (origin=..., generated=...)` ディレクティブを遵守する (#722)。

## ユーザー指示の短縮記法

| 記法 | 展開 |
| --- | --- |
| `is<N>` | GitHub Issue #N を参照 |
| `pr<N>` | GitHub PR #N を参照 |
| `issue#<N>` | GitHub Issue #N を参照 |
| `PR#<N>` | GitHub PR #N を参照 |
