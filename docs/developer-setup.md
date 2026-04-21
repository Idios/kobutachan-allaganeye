# Developer Setup Guide

このドキュメントは **開発者向け** の手順書です。ソースコードから allaganeye を動かしたい場合、または動作確認やパッケージ変更を行いたい場合のみ参照してください。

一般ユーザーは [Quick Start Guide](quickstart.md) の Portable ZIP 配布物を利用してください（Git/Python/ffmpeg の個別インストールは不要です）。

## 1. 前提条件の確認

開発セットアップには以下 3 つのソフトウェアが必要です。

- **Git**: ソースコードの取得・更新に使います
- **Python 3.11 以上**: 実行環境です（Portable ZIP 同梱の Python とは別に必要です）
- **ffmpeg / ffprobe 4.1 以上**: 動画の解析・分割エンジンです

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
# Windows (コマンドプロンプト)
.venv\Scripts\activate.bat

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Windows (Git Bash / MSYS2)
source .venv/Scripts/activate

# Linux / macOS
source .venv/bin/activate
```

パッケージをインストールする:

```bash
pip install -e ".[dev]"
```

> SSH を使う場合: `git clone git@github.com:Idios/kobutachan-allaganeye.git`

> **注意**: 仮想環境を使わずに `pip install -e .` すると、`allaganeye` コマンドが PATH の通らないディレクトリにインストールされることがあります（特に Microsoft Store 版 Python）。仮想環境の使用を推奨します。

### 仮想環境を抜ける

作業が終わって仮想環境から抜けるときは、どのシェル・OS でも共通で `deactivate` と入力します。

```bash
deactivate
```

## 3. 更新

```bash
cd kobutachan-allaganeye
```

仮想環境を有効化し（[§2](#2-インストール) と同じコマンド）、最新版を取得する:

```bash
git pull
```

editable install (`pip install -e .`) のため、通常は `git pull` だけで更新が反映されます。
依存パッケージが追加・変更された場合のみ `pip install -e ".[dev]"` の再実行が必要です。

## 4. 開発用コマンド

```bash
# テスト（slow マーカー除外）
pytest

# slow マーカー付きテスト（動画ファイル必要）
pytest -m slow

# 単体テスト
pytest tests/test_detector.py

# Lint
ruff check .
ruff format --check .

# 型チェック
pyright
```

## 5. サンプル動画データ

`slow` マーカー付きテストや実動画での動作確認には、環境変数 `ALLAGANEYE_SAMPLE_VIDEO_DIR` で録画データの場所を指定します。

```bash
# Windows
set ALLAGANEYE_SAMPLE_VIDEO_DIR=E:\path\to\videos

# Linux / macOS
export ALLAGANEYE_SAMPLE_VIDEO_DIR=/path/to/videos
```

- MKV: OBS 等で録画した長時間動画（複数試合を含む）
- サブディレクトリ（`20260116/` 等）: 手動で試合分割済みの MP4（`YYYYMMDD_N.mp4`）
- 未設定の場合、`sample_video_dir` fixture を使うテスト（`slow` マーカー）は自動スキップ

## 6. CLI コマンドリファレンス

開発中の動作確認で使う主要コマンド:

```bash
# 試合分割
allaganeye split <video_path>
allaganeye split <video_path> -o <output_dir>
allaganeye split <video_path> --dry-run       # 検知のみ、分割しない
allaganeye split <video_path> --gpu           # GPU アクセラレーション検知
allaganeye split <video_path> --workers 8     # ワーカー数指定
allaganeye split <video_path> --no-cache      # キャッシュ無視で再検知
allaganeye split <video_path> --no-audio      # 音声昇格を無効化
allaganeye split <video_path> -v              # verbose 出力
allaganeye split <video_path> -q              # 進捗抑制

# バージョン
allaganeye --version

# フレーム輝度 CSV 出力（閾値チューニング用）
allaganeye debug-brightness <video_path> --start 100 --end 200 --interval 0.5
```

全オプションと出力仕様は [CLI コマンド仕様](cli-spec.md) および [出力仕様マトリクス](output-spec.md) を参照してください。

## 7. 対応プラットフォーム

| 優先度 | OS | 状態 | 備考 |
|---|---|---|---|
| 1 | Windows | 対応済み | メイン開発・録画環境 |
| 2 | Linux | 未検証 | CI では lint/型チェックのみ実行。実動画での動作確認なし |
| 3 | macOS | 未検証 | Homebrew パス自動検索のコードはあるが動作確認なし |

## 8. 関連ドキュメント

- [パラメータ調整ガイド](tuning-guide.md)
- [CLI コマンド仕様](cli-spec.md)
- [出力仕様マトリクス](output-spec.md)
- [システムアーキテクチャ](design-overview.md)
- [動画処理設計](video-processing.md)
- [リリース戦略](release-strategy.md)
- [コーディング規約](coding-conventions.md)
