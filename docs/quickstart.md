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

PATH が通っていない場合は、ターミナルを再起動するか環境変数の設定を確認してください。

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
```

詳細は `allaganeye split --help` で確認できます。
