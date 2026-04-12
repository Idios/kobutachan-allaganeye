# Quick Start Guide

## 1. 前提条件の確認

Allagan Eye を使うには以下の 3 つのソフトウェアが必要です:

- **Git**: ツールのダウンロードと更新に使います
- **Python**: ツールの実行環境です
- **ffmpeg**: 動画の解析・分割を行うエンジンです

### Git

```bash
git --version
```

#### インストール方法

**Windows**（いずれか 1 つ）:

```bash
# git-scm.com からインストーラをダウンロード（推奨）
# https://git-scm.com/downloads/win → デフォルト設定でインストール

# winget
winget install Git.Git
```

**macOS**:

```bash
# Xcode Command Line Tools（推奨）
xcode-select --install

# Homebrew
brew install git
```

**Linux (Ubuntu/Debian)**:

```bash
sudo apt update && sudo apt install git
```

#### インストール確認

```bash
git --version   # "git version 2.x" 以上が表示されること
```

### Python 3.11+

```bash
python --version
```

#### インストール方法

**Windows**（いずれか 1 つ）:

```bash
# python.org からインストーラをダウンロード（推奨）
# https://www.python.org/downloads/ → 「Add python.exe to PATH」にチェックを入れてインストール

# winget
winget install Python.Python.3.13

# Microsoft Store
# Microsoft Store で「Python 3.13」を検索してインストール
```

**macOS**:

```bash
# python.org からインストーラをダウンロード（推奨）
# https://www.python.org/downloads/

# Homebrew
brew install python@3.13
```

**Linux (Ubuntu/Debian)**:

```bash
sudo apt update && sudo apt install python3 python3-pip python3-venv
```

#### インストール確認

```bash
python --version   # "Python 3.11.x" 以上が表示されること
pip --version      # pip が利用可能であること
```

> **注意**: Windows では `python` の代わりに `py` コマンドが必要な場合があります。`py --version` で確認してください。

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
# Windows（現在のセッションのみ）
set ALLAGANEYE_FFMPEG=C:\path\to\ffmpeg\bin

# Linux / macOS（現在のセッションのみ）
export ALLAGANEYE_FFMPEG=/path/to/ffmpeg/bin
```

**永続化する場合**:

```bash
# Windows: システム環境変数に追加（管理者権限不要）
setx ALLAGANEYE_FFMPEG "C:\path\to\ffmpeg\bin"

# Linux (bash): ~/.bashrc に追記
echo 'export ALLAGANEYE_FFMPEG=/path/to/ffmpeg/bin' >> ~/.bashrc

# macOS (zsh): ~/.zshrc に追記
echo 'export ALLAGANEYE_FFMPEG=/path/to/ffmpeg/bin' >> ~/.zshrc
```

## 2. インストール

```bash
git clone https://github.com/Idios/kobutachan-allaganeye.git
cd kobutachan-allaganeye
python -m venv .venv
```

仮想環境を有効化する:

```bash
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Windows (Git Bash / MSYS2)
source .venv/Scripts/activate

# Linux / macOS
source .venv/bin/activate
```

パッケージをインストールする:

```bash
pip install -e .
```

> SSH を使う場合: `git clone git@github.com:Idios/kobutachan-allaganeye.git`

> **注意**: 仮想環境を使わずに `pip install -e .` すると、`allaganeye` コマンドが PATH の通らないディレクトリにインストールされることがあります（特に Microsoft Store 版 Python）。仮想環境の使用を推奨します。

## 3. 更新

```bash
cd kobutachan-allaganeye
source .venv/Scripts/activate   # または上記の有効化コマンド
git pull
```

editable install (`pip install -e .`) のため、通常は `git pull` だけで更新が反映されます。
依存パッケージが追加・変更された場合のみ `pip install -e .` の再実行が必要です。

## 4. 動画を分割する

### 対応する録画

このツールは **FF14 フロントライン（FL）の複数試合を含む長時間録画** を試合ごとに分割します。FL の試合間にはロード画面（暗転）が入るため、この暗転をセパレータとして検知し、試合を分割します。

- OBS 等で録画した MP4 / MKV ファイルに対応
- 1 回の録画に複数試合が含まれている場合に効果を発揮
- 1 試合だけの録画では分割する境界がないため、検知結果は 0 件になります

### 基本的な使い方

まず `--dry-run` で検知結果を確認してから本実行するのがおすすめです。

```bash
# 1. 検知結果だけ確認（動画は分割しない）
allaganeye split your_recording.mkv --dry-run

# 2. 結果が正しければ本実行
allaganeye split your_recording.mkv
```

`./output/` に試合ごとの MP4 ファイルと `metadata.json` が出力されます。

### 出力先を変更する

```bash
allaganeye split your_recording.mkv -o ~/Desktop/matches
```

### GPU アクセラレーション

GPU 対応環境（NVIDIA CUDA, Intel QSV 等）では `--gpu` で暗転検知を GPU で実行できます。

```bash
allaganeye split your_recording.mkv --gpu
```

GPU が利用できない場合は自動で CPU モードにフォールバックします。どちらが速いかはコーデックや環境によって異なります。使い分けの判断方法は [パラメータ調整ガイド](tuning-guide.md) を参照してください。

### 録画の冒頭・末尾が試合中だった場合

録画開始時にすでに試合中だった場合や、試合中に録画を停止した場合でも、該当部分はセグメントとして出力されます。

- **冒頭**: 録画開始（0秒）から最初の暗転までが 1 つのセグメントになります
- **末尾**: 最後の暗転から録画終了までが 1 つのセグメントになります

これらのセグメントは試合の途中から始まる（または途中で終わる）不完全な録画のため、`metadata.json` では `type: "unknown"` として記録されます。`--min-match-duration`（デフォルト 300 秒）より短い場合は出力されません。

## 6. うまく分割されない場合

デフォルト設定は FL の一般的な録画に合わせて調整されており、多くの場合そのまま使えます。

うまくいかない場合は以下の症状に応じて対処してください。詳細な対処法と各パラメータの値の決め方は [パラメータ調整ガイド](tuning-guide.md) を参照してください。

| 症状 | 主な原因 | 対処の方向 |
|---|---|---|
| 試合の途中で分断される | リスポーン暗転の誤検知 | `--min-blackout-duration` を上げる |
| 別々の試合がくっつく | 暗転閾値が低すぎる | `--blackout-threshold` を上げる |
| 短い試合が出力されない | 最小試合時間で除外 | `--min-match-duration` を下げる |
| 試合が 1 つも検知されない | 閾値/録画形式の問題 | [パラメータ調整ガイド](tuning-guide.md) を参照 |
| 処理が遅い | サンプリング間隔/並列度 | [パラメータ調整ガイド](tuning-guide.md) を参照 |

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
