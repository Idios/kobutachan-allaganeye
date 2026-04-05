# Quick Start Guide

## 1. 前提条件の確認

### Python 3.11+

```bash
python --version
```

### ffmpeg / ffprobe (4.1 以上)

```bash
ffmpeg -version
ffprobe -version
```

**最低バージョン: 4.1**（`-avoid_negative_ts make_zero` 等の機能を使用）

#### インストール方法

**Windows**（いずれか 1 つ）:

```bash
# winget（推奨）
winget install Gyan.FFmpeg

# scoop
scoop install ffmpeg

# Chocolatey
choco install ffmpeg
```

パッケージマネージャを使わない場合は [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) から `ffmpeg-release-essentials.zip` をダウンロードし、展開先の `bin/` フォルダを PATH に追加してください。

**macOS**:

```bash
brew install ffmpeg
```

**Linux (Ubuntu/Debian)**:

```bash
sudo apt update && sudo apt install ffmpeg
```

#### インストール確認

```bash
ffmpeg -version   # "ffmpeg version 4.x" 以上が表示されること
ffprobe -version  # "ffprobe version 4.x" 以上が表示されること
```

**PATH が通らない場合**: Allagan Eye は winget のインストール先を自動検索するため、多くの場合 PATH の手動設定は不要です。自動検索で見つからない場合は `ALLAGANEYE_FFMPEG` 環境変数に ffmpeg/ffprobe の入ったディレクトリを指定してください:

```bash
# Windows
set ALLAGANEYE_FFMPEG=C:\path\to\ffmpeg\bin

# Linux / macOS
export ALLAGANEYE_FFMPEG=/path/to/ffmpeg/bin
```

## 2. インストール

```bash
git clone git@github.com:Idios/kobutachan-allaganeye.git
cd kobutachan-allaganeye
pip install -e .
```

> このリポジトリは private です。アクセス権のある GitHub アカウントで SSH 認証が必要です。

## 3. 動画を分割する

```bash
allaganeye split your_recording.mkv
```

`./output/` に試合ごとの MP4 ファイルと `metadata.json` が出力されます。

### 出力先を変更する

```bash
allaganeye split your_recording.mkv -o ~/Desktop/matches
```

### 分割せずに検知結果だけ確認する

```bash
allaganeye split your_recording.mkv --dry-run
```

## 4. うまく分割されない場合

試合の区切りが正しく検知されない場合、パラメータを調整してください。

```bash
# 暗転の閾値を上げる（明るめのロード画面にも対応）
allaganeye split your_recording.mkv --blackout-threshold 25.0

# 短い試合も含める（デフォルト: 300秒 = 5分）
allaganeye split your_recording.mkv --min-match-duration 120.0

# リスポーン暗転で試合が分断される場合、最小暗転時間を上げる（デフォルト: 3秒）
allaganeye split your_recording.mkv --min-blackout-duration 5.0
```

**ヒント**: `debug-brightness` コマンドで特定区間のフレーム輝度を確認し、`--blackout-threshold` の適切な値を決められます。

```bash
allaganeye debug-brightness your_recording.mkv --start 900 --end 1000 --interval 0.5
```

### パラメータの目安

| パラメータ | デフォルト | 用途 |
|---|---|---|
| `--blackout-threshold` | 15.0 | 暗転判定の輝度閾値（0-255）。上げると明るめの暗転も検知 |
| `--min-match-duration` | 300.0 | 最小試合時間（秒）。短い試合も含めたい場合は下げる |
| `--min-blackout-duration` | 3.0 | 最小暗転時間（秒）。リスポーン暗転（1-2s）を除外するため 3s がデフォルト |
| `--sample-interval` | 1.0 | フレームサンプリング間隔（秒）。大きくすると高速だが検知精度が下がる |
| `--workers` | auto | 並列ワーカー数（デフォルト: CPU コア数、最大 24） |
| `--gpu` / `--no-gpu` | `--no-gpu` | GPU アクセラレーション検知 |

詳細は `allaganeye split --help` で確認できます。

### 分割が途中で失敗した場合

途中で失敗しても、成功済みの出力ファイル（`match_001.mp4` 等）は出力ディレクトリに残ります。再実行すれば自動的に上書きされるため、手動削除は不要です。

## 開発者向け

### 実動画テストの実行

実動画を使った統合テスト（`pytest -m slow`）には以下の環境変数が必要:

```bash
# Windows
set ALLAGANEYE_SAMPLE_VIDEO_DIR=E:\path\to\videos

# Linux / macOS
export ALLAGANEYE_SAMPLE_VIDEO_DIR=/path/to/videos
```
