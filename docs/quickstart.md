# Quick Start Guide

## 1. 前提条件の確認

### Python 3.11+

```bash
python --version
```

### ffmpeg / ffprobe

```bash
ffmpeg -version
ffprobe -version
```

インストールされていない場合:
- **Windows**: [ffmpeg.org](https://ffmpeg.org/download.html) からダウンロードし、PATH に追加
- **macOS**: `brew install ffmpeg`
- **Linux**: `sudo apt install ffmpeg`

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

### 分割が途中で失敗した場合

途中で失敗しても、成功済みの出力ファイル（`match_001.mp4` 等）は出力ディレクトリに残ります。再実行すれば自動的に上書きされるため、手動削除は不要です。
