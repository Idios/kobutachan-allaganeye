# Allagan Eye

FF14 フロントラインの長時間録画動画を、試合ごとに自動分割する CLI ツール。

OBS 等で録画した数時間分の動画を入力すると、試合の切れ目を自動検知し、試合単位の MP4 ファイルに無劣化で分割します。

## 環境要件

| 要件 | バージョン |
|---|---|
| Python | 3.11 以上 |
| ffmpeg / ffprobe | 4.1 以上（PATH、環境変数、または既知パスから自動検索） |

対応入力形式: MP4, MKV, AVI, MOV

### 対応プラットフォーム

| 優先度 | OS | 状態 | 備考 |
|---|---|---|---|
| 1 | Windows | 対応済み | メイン開発・録画環境 |
| 2 | Linux | 対応済み | CI テスト済み |
| 3 | macOS | 動作想定 | Homebrew パス自動検索対応。CI テストは将来追加 |

## Quick Start

> 詳しいセットアップ手順は [Quick Start Guide](docs/quickstart.md) を参照してください。

```bash
pip install -e .
allaganeye split your_recording.mkv
```

## 使い方

### 試合分割

```bash
allaganeye split <video_path>
```

出力先を指定する場合:

```bash
allaganeye split <video_path> -o <output_dir>
```

### オプション

| オプション | デフォルト | 説明 |
|---|---|---|
| `-o`, `--output-dir` | `./output` | 出力ディレクトリ |
| `--sample-interval` | `1.0` | フレームサンプリング間隔（秒） |
| `--blackout-threshold` | `15.0` | 暗転検知の輝度閾値（0-255） |
| `--min-match-duration` | `300.0` | 最小試合時間（秒）。短いセグメントを除外 |
| `--min-blackout-duration` | `3.0` | 最小暗転時間（秒）。短い暗転を無視 |
| `--workers` | auto | 検知の並列ワーカー数（デフォルト: 自動=CPU コア数、最大24） |
| `--gpu` / `--no-gpu` | `--no-gpu` | GPU アクセラレーション検知（チャンク並列デコード）。GPU が利用不可の場合は CPU にフォールバック |
| `--dry-run` | - | 検知のみ実行し、分割しない |
| `-v`, `--verbose` | - | 詳細ログ出力 |

> うまく分割されない場合は [パラメータ調整ガイド](docs/tuning-guide.md) を参照してください。

### フレーム輝度の確認

暗転検知の閾値をチューニングする際は、`debug-brightness` コマンドでフレーム輝度を CSV 出力できます。

```bash
allaganeye debug-brightness <video_path> --start 100 --end 200 --interval 0.5
```

出力（CSV 形式、stdout）:

```
timestamp,brightness
100.0,12.3
100.5,245.6
101.0,8.1
```

詳細は [CLI コマンド仕様](docs/cli-spec.md) を参照してください。

### 出力

指定ディレクトリに試合ごとの MP4 とメタデータが出力されます。

```
output/
├── match_001.mp4
├── match_002.mp4
├── match_003.mp4
└── metadata.json
```

### Exit Codes

| コード | 意味 |
|---|---|
| 0 | 正常終了 |
| 1 | 一般エラー |
| 2 | 入力ファイル不正（ファイルが存在しない、非対応形式） |
| 3 | FFmpeg / ffprobe エラー |
| 4 | 検知失敗（試合境界が見つからない） |
| 5 | 設定値不正（パラメータの範囲外等） |

## ロードマップ

| フェーズ | 機能 | 状態 |
|---|---|---|
| L1 | 試合分割 | 実装中 |
| L2 | メタデータ化（OCR・音声認識） | 予定 |
| L3 | 投稿価値の自動評価 | 予定 |
| L4 | ハイライト自動編集 | 予定 |

## ドキュメント

- [Quick Start Guide](docs/quickstart.md)
- [パラメータ調整ガイド](docs/tuning-guide.md)
- [CLI コマンド仕様](docs/cli-spec.md)
- [システムアーキテクチャ](docs/design-overview.md)
- [動画処理設計](docs/video-processing.md)
- [リリース戦略](docs/release-strategy.md)

## ライセンス

[MIT License](LICENSE)
