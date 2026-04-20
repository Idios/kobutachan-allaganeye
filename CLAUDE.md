# Allagan Eye

## プロジェクト概要

FF14 PvPコンテンツ「フロントライン」の長時間録画動画（OBS, MP4/MKV）から、試合単位の分割・ハイライト抽出・投稿価値の評価を段階的に自動化するCLIツール。

### 段階的アーキテクチャ

**コアレイヤー（L1〜L5）**

| レイヤー | 処理 | 技術 | 状態 |
|---|---|---|---|
| L1: 試合分割 | 暗転検知で試合単位に分割 | FFmpeg（検知+分割） | **リリース済み** (v0.1.0-preview 2026-04-17, v0.1.1 2026-04-20) |
| L2: 配布・統合 | GUI + ゼロ環境構築配布 + guard 統合 | Tauri/PyQt 他 + PyInstaller + allaganeye-guard | **開発中** |
| L3: メタデータ化 | キルログ・音声・チャットをタイムスタンプ化 | Tesseract / Whisper | 未着手 |
| L4: 価値評価 | 抽出データをMLが判定 | ローカル ML（scikit-learn 等） | 未着手 |
| L5: 自動編集 | 判定に基づき動画切り出し・投稿提案 | MoviePy / FFmpeg | 未着手 |

**拡張レイヤー（L6、暫定）**

| レイヤー | 処理 | 状態 |
|---|---|---|
| L6: プライバシー・精密分割 | プレイヤー名ぼかし、再エンコード分割 | 計画中 |

**設計原則**: ツールの独立性・ポータビリティを保つため、Web 経由のサービスや大規模モデルをツールの実行時依存に含めない。AI（LLM）はツール自体の設計と評価にのみ用いる。動画編集・変換は FFmpeg/OpenCV 等のライブラリで実行する。ローカル ML（scikit-learn 等の軽量モデル）は信号処理・分類で必要に応じて使用してよい。

## コマンド

詳細は [`docs/testing-guide.md`](docs/testing-guide.md) を参照（GPU テスト間インターバル、サンプルデータ設定等）。CLI 構文は [`docs/cli-spec.md`](docs/cli-spec.md)、オプション組み合わせごとの出力仕様は [`docs/output-spec.md`](docs/output-spec.md) (#405 マトリクス v2) を参照。

```bash
# テスト
pytest                          # 全テスト（slowマーカー除外）
pytest -m slow                  # 動画ファイル必要なテスト
pytest tests/test_detector.py   # 単体テスト

# Lint / 型チェック
ruff check .
ruff format --check .
pyright

# CLI
allaganeye split <video_path>           # 試合分割
allaganeye split <video_path> -o <dir>  # 出力先指定
allaganeye split <video_path> --gpu     # GPU アクセラレーション検知
allaganeye split <video_path> --workers 8  # ワーカー数指定
allaganeye split <video_path> --no-cache   # キャッシュ無視で再検知
allaganeye split <video_path> --no-audio   # 音声昇格を無効化（視覚のみ）
allaganeye split <video_path> --quiet      # 進捗抑制（出力ファイルのみ）
allaganeye split <video_path> -v           # verbose（環境情報・パイプライン統計を表示、#336）
allaganeye --version                       # バージョン表示（短縮形: -V、#337）
allaganeye debug-brightness <video_path>   # フレーム輝度 CSV 出力
```

## アーキテクチャ

### データフロー（L1）

```
MP4/MKV入力 → probe.py（ffprobe でメタデータ取得）
           → detector.py（ffmpeg 並列 -ss プローブで暗転検知 → 試合境界タイムスタンプ）
           → splitter.py（FFmpeg -c copy で無劣化分割）
           → 出力: 試合ごとのMP4 + metadata.json
```

### モジュール構成

| モジュール | 責務 |
|---|---|
| `cli.py` | Typer CLIエントリポイント。コマンドルーティング |
| `config.py` | 設定管理（検知閾値、出力パス等） |
| `exceptions.py` | エラークラス + exit code マッピング |
| `ffmpeg_path.py` | ffmpeg/ffprobe のパス自動検索（winget, Homebrew, PATH, 環境変数） |
| `commands/split_matches.py` | split コマンドのオーケストレーション。タイムスタンプ表示・gap 検出・sample_interval 自動調整 |
| `commands/debug_brightness.py` | debug-brightness コマンド。フレーム輝度を CSV 出力（閾値チューニング用） |
| `video/probe.py` | ffprobe でメタデータ取得（解像度、fps、長さ） |
| `video/detector.py` | ffmpeg 並列プローブで暗転検知、試合境界抽出（CPU モード） |
| `video/gpu_detector.py` | GPU アクセラレーション検知（チャンク並列デコード） |
| `video/scorebar.py` | スコアバーフィルタリング（暗転分類・試合内/非FL判定）+ 音声昇格 |
| `video/splitter.py` | FFmpeg で動画分割（-c copy） |
| `audio/extract.py` | ffmpeg で音声 PCM 抽出 |
| `audio/features.py` | log-mel スペクトログラム計算と保存 |
| `audio/matcher.py` | 参照 BGM と target の相互相関で peak 検出 |
| `audio/scan.py` | 動画全域を走査して Fanfare ピークを返す |
| `audio/refs/` | 同梱参照特徴量（`fanfare.npz`） |

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
8. `filter_blackouts_with_scorebar()` で各暗転領域の前後フレームのスコアバー有無を判定し、暗転を分類（`match_boundary` / `in_match` / `non_fl`）
9. `non_fl`（非FL暗転）と短い `in_match`（試合内暗転）を除外。隣接する `match_boundary` ペア間の短いギャップをマージ

**音声昇格**（`--no-audio` 未指定時、#288）
- `audio/scan.py` で動画全域の音声から Fanfare ピーク（log-mel 相関 sim ≥ 0.65）を抽出
- `in_match` 分類された暗転のうち、暗転終了後 0-60s 以内に Fanfare ピークがあるものを `match_boundary` に昇格
- スコアバー残像で誤分類された試合境界（例: 2026-04-08 57:53）を救済
- 既知の制約: Fanfare は試合中にも弱いピーク（sim 0.65-0.75）を出すため、本条件のみでは偽陽性が混入しうる。WR 参照 (#301) 同梱後に WR→Fanfare 間隔による (B) 条件を追加して偽陽性除去

**フィルタリング・抽出**
10. `min(min_blackout_duration, _REFINED_MIN_BLACKOUT)` 未満の短い暗転を除外（リスポーン暗転の誤判定防止）
11. blackout region 間の非暗転区間を試合セグメントとして抽出（暗転内パディング付き）

**検出の動作確認済み環境と制限事項**
- 動作確認済み: ハイスペック PC（高速 SSD、高性能 GPU）での OBS 録画。試合間暗転 2-5 秒程度
- 未検証: 低スペック環境でローディング画面が長い（10 秒超）ケース
- 既知の制限: ローディング画面が純粋な黒画面でなく UI 要素（スピナー、ロゴ等）を含む場合、brightness が 15-55 の範囲で変動し暗転が分断されることがある。分断された各区間が `min_blackout_duration` 未満になると試合境界を検出できない

**GPU モード** (`--gpu`)
- CPU モードの Pass 1 を GPU チャンク並列デコードで代替（`gpu_detector.py`）
- 動画を N チャンク（`min(cpu_count, 16)`）に分割し、各チャンクで長寿命の ffmpeg プロセスを `-hwaccel auto` + `fps` フィルタで起動
- GPU 初期化コストを分散し、1プロセスあたり多数フレームをデコードすることで効率化
- Pass 1 以降の処理（transition expansion, Pass 2, フィルタリング）は CPU/GPU 共通
- GPU 利用不可時は自動で CPU モードにフォールバック

### Exit Codes

| コード | 意味 |
|---|---|
| 0 | 正常終了 |
| 1 | 一般エラー |
| 2 | 入力ファイル不正（存在しない、未対応形式） |
| 3 | FFmpeg / ffprobe エラー |
| 4 | 検知失敗（試合境界が見つからない） |
| 5 | 設定値不正（パラメータの範囲外等） |

### 外部依存

- **ffmpeg / ffprobe**: 4.1 以上。PATH、`ALLAGANEYE_FFMPEG` 環境変数、または OS 別既知パスから自動検索（`allaganeye/ffmpeg_path.py`）
  - Windows: winget (`Gyan.FFmpeg`) のインストール先を自動検索
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

## セキュリティ検査（allaganeye-guard 連携）

外部ユーザーから受領した動画ファイルを処理する前に、独立ツール `allaganeye-guard` でセキュリティ検査を行う。詳細は `docs/guard-integration.md` を参照。

- **リポジトリ**: [Idios/kobutachan-allaganeye-guard](https://github.com/Idios/kobutachan-allaganeye-guard)
- `allaganeye-guard verify <file>` で検査、PASS なら `allaganeye split` で処理
- 将来的に `--verify` オプションで自動呼び出しを実装予定
- guard がインストールされていなくても allaganeye 本体は正常動作する
- **外部動画データの検査**: Idios 以外のユーザーが issue・PR に添付した動画は、`allaganeye-guard verify` が PASS するまで処理しない（`docs/guard-integration.md` §8 参照）
- **開発・リリース同期**: allaganeye のレイヤーリリース時に guard との互換性チェックが必要になる（`docs/guard-integration.md` §11 参照）

## リリース戦略

詳細は `docs/release-strategy.md` を参照。要約:

- `develop-x.x.x` が日常の統合先、`main` はリリース時のみ更新
- PR はすべて `develop-x.x.x` にマージ
- リリース時に `develop-x.x.0 → main` マージ + タグ打ち
- レイヤーごとに minor バージョン（L1=0.1, L2=0.2, L3=0.3, L4=0.4, L5=0.5）

## 開発ワークフロー

L2 からは**単一ワークツリー + skill ベースディスパッチ**を採用。詳細は `docs/l2-workflow.md` を参照。

- 旧ロール体制 (director / lead-engineer / engineer / tester) は廃止
- タスク種別ごとの skill (`/plan`, `/implement`, `/review-pr`, `/test-pr`, `/create-task`, `/release`) を呼び分け
- ユーザー (Idios) が戦略・方針を判断し、Claude は選択肢提示と実装を担う

### ユーザー確認ルール

以下のケースでは独断せず、必ず `AskUserQuestion` で確認する:

- **bulk 操作** (3 件以上の issue 編集、ブランチ削除、ラベル一括変更等): 事前にサンプル 1 件提示し「全件 OK / 個別調整 / やめる」
- **曖昧判断**: 実装方針の選択肢が複数ある場合、各案のトレードオフを options として提示し Recommended 付き
- **優先度判定**: `[P1-high, P2-medium, P3-low, deferred]` の 4 択
- **スコープ拡張**: 当初範囲外の変更が必要になったら `[スコープ内 / 別 issue 起票 / 見送り]` の 3 択

PR レビューで「観察 (修正不要)」と独断で結論することは**禁止**。懸念があれば別 issue 起票するか、ユーザーに判断を委ねる (#399 B 由来の原則)。

### Memory 活用 (ユーザー訂正の蓄積)

ユーザーが Claude の判断を訂正した場合、訂正内容を `feedback_*.md` 形式でメモリに蓄積する。蓄積対象の例:

- 優先度判定基準の訂正 (「この観点は P1」「このレベルの UX 品質は P3」等)
- ラベル振り分け基準の訂正 (`deferred` / スコープラベル判定の根拠)
- レビュー判断基準の訂正
- bulk 操作の閾値・順序の訂正

蓄積した基準を次セッション以降で読み返し、同じ訂正を繰り返さないようにする。個別セッションの一時状態 (進行中の PR 番号・作業中の issue 等) は memory ではなく TodoWrite / plan に残す。

## CLAUDE.md 継続改善

ユーザーから「CLAUDE.md に追記して」等の指示があった場合、このファイルを即座に更新する。
更新後は変更箇所をユーザーに報告する。

## GitHub Issue 作成ルール

詳細は `docs/issue-policy.md` を参照。要約:

- プレフィックス: `[bug]`, `[doc]`, `[refactor]`, `[task]`, `[question]`, `[risk]`
- Assignee: 常に `Idios`
- 作成者明示: 本文末尾に `作成: <session-id>`
- ラベル: prefix ラベル + スコープラベル (`l2a-gui` / `l2b-installer` / `l2c-guard` / `l2-workflow` / `l2-decision` / `l1-residual` 等) + 優先度（`P1-high` / `P2-medium` / `P3-low`）
- `Closes`/`Fixes` キーワードは使わない（クローズは手動）

## PR 作成ルール

詳細は `docs/l2-workflow.md` を参照。要約:

- **PR 作成前**: ベースブランチをリベースし、`ruff check .` / `ruff format --check .` / `pytest` を通すこと
- ベースブランチ: `develop-x.x.x`（`main` ではない）
- 作業ブランチ命名: `claude/<scope>-<short-description>` または `claude/<issue-N>-<slug>`
- マージ方法: `gh pr merge <番号> --squash` (ユーザーが実行)
- レビュー: `/review-pr` skill で受け入れ条件チェックリスト検証 (#367 対策)
- コード変更は `/test-pr` skill で実機テスト実施
- コミットメッセージに `[<session-id>]` を含める
- **PR 本文・コミットメッセージで `Closes` / `Fixes` / `Resolves` キーワードを使わない**（issue のクローズは手動で行う）

## ユーザー指示の短縮記法

| 記法 | 展開 |
|---|---|
| `is<N>` | GitHub Issue #N を参照 |
| `pr<N>` | GitHub PR #N を参照 |
| `issue#<N>` | GitHub Issue #N を参照 |
| `PR#<N>` | GitHub PR #N を参照 |
