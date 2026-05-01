# Developer Setup Guide

このドキュメントは **開発者向け** の手順書です。ソースコードから allaganeye を動かしたい場合、または動作確認やパッケージ変更を行いたい場合のみ参照してください。

一般ユーザーは [Quick Start Guide](quickstart.md) の Portable ZIP 配布物を利用してください（Git/Python/ffmpeg の個別インストールは不要です）。

## 1. 前提条件の確認

開発セットアップには以下 3 つのソフトウェアが必要です。

- **Git**: ソースコードの取得・更新に使います
- **Python 3.11 (3.11.9 推奨)**: 実行環境です（Portable ZIP 同梱の Python とは別に必要です）。CI と Portable ZIP は 3.11.9 で固定しているため、ローカルも同じ patch に揃えると挙動差を避けられます
- **ffmpeg / ffprobe 8.1 LGPLv3 推奨**: 動画の解析・分割エンジンです。最低 4.1 で動作しますが、CI / Portable ZIP は BtbN の LGPLv3 8.1 shared に固定しているので同系列を推奨します

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
winget install Python.Python.3.11

# Microsoft Store
# Microsoft Store で「Python 3.11」を検索してインストール
```

**macOS**:

```bash
# python.org からインストーラをダウンロード（推奨）
# https://www.python.org/downloads/

# Homebrew
brew install python@3.11
```

**Linux (Ubuntu/Debian)**:

```bash
sudo apt update && sudo apt install python3 python3-pip python3-venv
```

#### インストール確認

```bash
python --version   # "Python 3.11.9" (推奨) または "Python 3.11.x" 以上が表示されること
pip --version      # pip が利用可能であること
```

> **注意**: Windows では `python` の代わりに `py` コマンドが必要な場合があります。`py --version` で確認してください。

### ffmpeg / ffprobe (4.1 以上)

```bash
ffmpeg -version
ffprobe -version
```

**推奨: ffmpeg 8.1 LGPLv3** (CI / Portable ZIP と同じ系列)。**最低バージョン: 4.1**（`-avoid_negative_ts make_zero` 等の機能を使用）が、CI / Portable ZIP 同梱版との挙動差を避けるため 8.1 LGPLv3 を推奨します。

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
ffmpeg -version   # "ffmpeg version 8.1" (推奨) または "ffmpeg version 4.x" 以上が表示されること
ffprobe -version  # 同上
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
>
> **注意**: 仮想環境を使わずに `pip install -e .` すると、`allaganeye` コマンドが PATH の通らないディレクトリにインストールされることがあります（特に Microsoft Store 版 Python）。仮想環境の使用を推奨します。

### 仮想環境を抜ける

作業が終わって仮想環境から抜けるときは、どのシェル・OS でも共通で `deactivate` と入力します。

```bash
deactivate
```

### venv 作成が `Permission denied` で失敗するとき (Windows)

`python -m venv .venv` 実行時に以下のようなエラーが出ることがあります。

```text
Error: [Errno 13] Permission denied: 'E:\tmp\...\.venv\Scripts\python.exe'
```

Windows は使用中ファイルのロックで上書き・削除を拒否するため、既存 `.venv` 内の `python.exe` を別プロセスが掴んでいると再作成が失敗します。

**典型的な原因**:

- 別ターミナルで同じ `.venv` を activate したまま残っている
- VSCode / PyCharm 等の IDE が Python extension 経由で `.venv` を参照している
- Antivirus / Windows Defender が一時的にファイルをスキャン中

**解決手順** (上から順に試す):

1. Python プロセスの確認と終了

    ```powershell
    Get-Process python -ErrorAction SilentlyContinue
    ```

    該当プロセスが見つかったら、他のターミナル / IDE を閉じるか `Stop-Process` で終了させる。

1. VSCode / 他 IDE を完全に閉じてから再実行

    IDE の Python extension が裏で `.venv\Scripts\python.exe` を開いていることがある。ウィンドウを閉じるだけでは解消しない場合、タスクマネージャで該当プロセスが残っていないか確認する。

1. 既存 `.venv` を完全削除して再作成

    ```powershell
    # PowerShell
    Remove-Item -Recurse -Force .venv
    python -m venv .venv
    ```

    ```cmd
    rem コマンドプロンプト
    rmdir /s /q .venv
    python -m venv .venv
    ```

    ```bash
    # Git Bash / MSYS2
    rm -rf .venv
    python -m venv .venv
    ```

1. 別パスで切り分け

    ```bash
    python -m venv C:\temp\test_venv
    ```

    これが成功するなら原因はリポジトリ配下の `.venv` ロックに特定される。失敗するなら Antivirus / 権限周り (書き込み禁止フォルダ等) を疑う。

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

### Windows: Pester v5 (scripts/ 用 PowerShell ユニットテスト)

`scripts/build-portable-zip.ps1` の関数ユニットテスト (`scripts/tests/`) は Pester v5 を使います。build-portable-zip.ps1 を変更する場合のみ必要で、Linux / macOS のみでの開発なら入れなくても構いません (CI が Windows runner で `installer-pester` ジョブとして常時実行します)。

```powershell
# 初回: PowerShell Gallery から Pester v5 をユーザースコープにインストール
# (PowerShell 5.1 では TLS 1.2 を先に有効化する必要があります)
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Install-Module Pester -MinimumVersion 5.0.0 -Scope CurrentUser -Force -SkipPublisherCheck

# テスト実行
Invoke-Pester -Path scripts/tests/ -Output Detailed
```

テスト対象: `Invoke-Download` の SHA256 検証、`Assert-FFmpegLayout` の BtbN 展開レイアウト検証、`Format-ReadmeContent` の LGPLv3 文言。詳細は [`scripts/tests/build-portable-zip.Tests.ps1`](../scripts/tests/build-portable-zip.Tests.ps1)。

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
| --- | --- | --- | --- |
| 1 | Windows | 対応済み | メイン開発・録画環境 |
| 2 | Linux | 未検証 | CI では lint/型チェックのみ実行。実動画での動作確認なし |
| 3 | macOS | 未検証 | Homebrew パス自動検索のコードはあるが動作確認なし |

## 8. 関連ドキュメント

- [パラメータ調整ガイド](tuning-guide.md)
- [CLI コマンド仕様](cli-spec.md)
- [出力仕様マトリクス](output-spec.md)
- [システムアーキテクチャ](design-overview.md)
- [動画処理設計](video-processing.md)
- [リリース戦略・手順](release-process.md)
- [コーディング規約](coding-conventions.md)

## 9. Python / FFmpeg バージョン更新チェックリスト

CI / Portable ZIP / 開発環境の 3 環境で Python と FFmpeg のバージョンを揃えるため、bump 時は以下を**同時に**更新する (#510 で 2026-04-23 に統一)。

### Python (現在 3.11.9 に固定)

| 場所 | キー |
| --- | --- |
| `.github/workflows/ci.yml` | `python-version: "3.11.9"` |
| `.github/workflows/release.yml` (3 ジョブ) | `python-version: '3.11.9'` |
| `scripts/build-portable-zip.ps1` | `$PythonVersion = '3.11.9'` + `$PythonEmbedSha256` |
| `docs/developer-setup.md` §1 | 「Python 3.11 (3.11.9 推奨)」の記載 |

### FFmpeg (現在 BtbN LGPLv3 n8.1 shared / `autobuild-2026-04-22-13-15` に固定)

更新手順:

1. [BtbN/FFmpeg-Builds/releases](https://github.com/BtbN/FFmpeg-Builds/releases) で新しい `autobuild-YYYY-MM-DD-HH-MM` タグを選ぶ
1. 必要な 2 資産 (win64-lgpl-shared-8.1.zip / linux64-lgpl-shared-8.1.tar.xz) の SHA256 を取得:

   ```bash
   gh api repos/BtbN/FFmpeg-Builds/releases/tags/<タグ名> \
     --jq '.assets[] | select(.name | test("n8[.]1.*(win64-lgpl-shared-8[.]1[.]zip|linux64-lgpl-shared-8[.]1[.]tar[.]xz)$")) | {name, digest}'
   ```

1. 以下を**同一タグ・同一 autobuild 系列で**更新 (下表参照)。major version 系列変更 (例: 8.x → 9.x) 時は docs の major version 記述も揃える。cache key に SHA256 が埋め込まれているので、SHA256 を変更すれば CI / release 両方のキャッシュが自動で invalidate される
1. ローカルで Portable ZIP ビルドが緑になることを確認 (`pwsh ./scripts/build-portable-zip.ps1 -Version <version>`) し、PR で CI の `build-windows` と `python` ジョブ両方が通ることを確認する

| 場所 | キー |
| --- | --- |
| `scripts/build-portable-zip.ps1` | `$FFmpegBuildTag` / `$FFmpegAsset` / `$FFmpegSha256` (`$FFmpegSourceCommit` は asset 名から自動抽出) |
| `.github/workflows/ci.yml` (`Cache FFmpeg archive` / `Download FFmpeg archive (cache miss)` / `Install ffmpeg` の 3 ステップ) | cache `key` 内 SHA256 + DL step の URL + install step の `FFMPEG_SHA256` (linux64-lgpl-shared 版) |
| `.github/workflows/release.yml` (`Cache FFmpeg archive` ステップ) | cache `key` 内 SHA256 (win64-lgpl-shared 版、build-portable-zip.ps1 の SHA256 と同じ値) |
| `docs/developer-setup.md` §1 | 「ffmpeg / ffprobe 8.1 LGPLv3 推奨」「推奨: ffmpeg 8.1 LGPLv3」の major version 記述 (系列変更時のみ) |
| `docs/quickstart.md` §10 | 対応 FFmpeg コミット (例: `7f5c90f77e`) の記述 (upstream commit 変更時) |

### get-pip.py の hash drift 対応 (#649)

`$GetPipSha256` ([scripts/build-portable-zip.ps1](../scripts/build-portable-zip.ps1)) は非バージョン管理 URL `https://bootstrap.pypa.io/get-pip.py` を参照しているため、PyPA が pip をリリースするたびに hash が drift し `build-windows` が `SHA256 mismatch` で fail する。FFmpeg / Python embed は versioned URL でピン留めしているのでこの drift は発生しない (get-pip.py 固有の問題)。drift 検知時は以下で更新:

```powershell
Invoke-WebRequest https://bootstrap.pypa.io/get-pip.py -OutFile get-pip.py
Get-FileHash get-pip.py -Algorithm SHA256
```

得られた SHA256 で `scripts/build-portable-zip.ps1` の `$GetPipSha256` を書き換え → develop-0.2.0 ベースで hotfix PR を先行マージ → 既存 PR を rebase で `build-windows` 復旧、という流れ ([#651](https://github.com/Idios/kobutachan-allaganeye/pull/651) が先例)。

長期対応 (versioned URL `https://bootstrap.pypa.io/pip/24.0/get-pip.py` または `.sha256` sidecar の動的検証) は [#649](https://github.com/Idios/kobutachan-allaganeye/issues/649) §長期対応で検討中。
