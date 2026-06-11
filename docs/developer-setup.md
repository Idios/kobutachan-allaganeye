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

テスト対象: `Invoke-Download` の SHA256 検証、`Assert-FFmpegLayout` の BtbN 展開レイアウト検証、`Format-ReadmeContent` の LGPLv3 文言、`File encoding (#704)` の BOM 検証 (PS5.1 + 日本語コメント parse 担保)、`Integrity manifest encoding (#729)` の BOM-less byte-level 検証 (`[IO.File]::WriteAllText` + `UTF8Encoding($false)` の canonical pattern pin)。詳細は [`scripts/tests/build-portable-zip.Tests.ps1`](../scripts/tests/build-portable-zip.Tests.ps1)。

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
allaganeye split <video_path> --no-audio      # 音声昇格の無効化フラグ（#327 で凍結中のため現在は常にスキップ）
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
| `scripts/build-portable-zip.ps1` | `python --version` sanity check (line ~448) で `^Python 3\.11\.` を期待 |
| `docs/developer-setup.md` §1 | 「Python 3.11 (3.11.9 推奨)」の記載 |

### FFmpeg (現在 BtbN LGPLv3 n8.1 shared / `autobuild-2026-04-30-13-44` monthly snapshot に固定)

更新手順 (#705 monthly snapshot policy):

1. [BtbN/FFmpeg-Builds/releases](https://github.com/BtbN/FFmpeg-Builds/releases) で **monthly snapshot** = タグ名が `autobuild-YYYY-MM-{28,29,30,31}-*` (各月末日 daily が survive したもの) を選ぶ。**daily 中間タグ (例: `autobuild-2026-05-06-13-32`) は禁止** (~14 日で BtbN GC、Pester `BtbN pinning policy (#705)` regression test で reject される)。
1. その release の `checksums.sha256` から win64 + linux64 の 2 資産 SHA256 を取得:

   ```bash
   curl -sL "https://github.com/BtbN/FFmpeg-Builds/releases/download/<タグ名>/checksums.sha256" \
     | grep -E 'win64-lgpl-shared-8\.1\.zip$|linux64-lgpl-shared-8\.1\.tar\.xz$'
   ```

   2 行出力 = 各 asset の SHA256 + ファイル名。BtbN naming は monthly snapshot のタイミングで OLD format (`ffmpeg-n<ver>-<count>-g<commit>-...`) と NEW format (`ffmpeg-n<ver>-...`) のどちらにもなりうる。`Get-FFmpegSourceRef` は両対応済 (`scripts/tests/build-portable-zip.Tests.ps1` の `Describe 'Get-FFmpegSourceRef'` 参照)。
1. 以下の場所を**同一タグ・同一 SHA256 系列で**更新する (下表、常時更新の 3 行 + 条件付き 2 行 = 計 5 行)。major version 系列変更 (例: 8.x → 9.x) 時は docs の major version 記述 (下表 4-5 行目) も揃える。cache key に SHA256 が埋め込まれているので、SHA256 を変更すれば CI / release 両方のキャッシュが自動で invalidate される。
1. ローカルで Portable ZIP build が緑になることを確認 (`pwsh ./scripts/build-portable-zip.ps1 -Version <version> -SkipArchive`) し、PR で CI の `build-windows` と `python` と `installer-pester` ジョブが全て通ることを確認する

| 場所 | キー |
| --- | --- |
| `scripts/build-portable-zip.ps1` | `$FFmpegBuildTag` / `$FFmpegAsset` / `$FFmpegSha256` (`$FFmpegSourceRef` は asset 名から自動抽出) |
| `.github/workflows/ci.yml` (`Cache FFmpeg archive` / `Download FFmpeg archive (cache miss)` / `Install ffmpeg` の 3 ステップ) | cache `key` 内 SHA256 + DL step の URL + install step の `FFMPEG_SHA256` (linux64-lgpl-shared 版) |
| `.github/workflows/release.yml` (`Cache FFmpeg archive` ステップ) | cache `key` 内 SHA256 (win64-lgpl-shared 版、build-portable-zip.ps1 の SHA256 と同じ値) |
| `docs/developer-setup.md` §1 | 「ffmpeg / ffprobe 8.1 LGPLv3 推奨」「推奨: ffmpeg 8.1 LGPLv3」の major version 記述 (系列変更時のみ) |
| `docs/quickstart.md` §10 | 対応 FFmpeg ソース ref (commit hash の場合は `g<commit>`、release tag の場合は `n<version>`) の記述 (upstream ref 変更時) |

### PyInstaller フローでの version pin (#752 以降)

v0.3.0 で Portable ZIP の build フローを Python 3.11 embed + `pip install --target lib` から **PyInstaller `--onedir`** に切り替えた (`docs/superpowers/specs/2026-05-18-issue-752-portable-zip-file-count-reduction-design.md`)。これに伴い旧 `$PythonVersion` / `$PythonEmbedUrl` / `$PythonEmbedSha256` / `$GetPipUrl` / `$GetPipSha256` 定数は `scripts/build-portable-zip.ps1` から削除。

bump 手順:

1. `scripts/installer/requirements-pyinstaller.txt` の 2 行 (`pyinstaller==<ver>` + `pyinstaller-hooks-contrib==<ver>`) を更新
2. Idios の手元で `pwsh -File scripts/build-portable-zip.ps1 -Version <test-ver> -SkipArchive` を実行、frozen output が生成されることを確認
3. CI smoke-test (Lv A `--version` / Lv B `detect` 3s / integrity exit 7 fall-through) が PASS することを確認
4. 実機 split (1:25 動画 1 本) で video detection (+ audio module の frozen build での import 健全性) + GUI export が動作することを Idios 実機検証

bump 頻度: 4-6 か月毎を目安、PyInstaller 公式 release notes を確認して numpy / scipy / cv2 hook の互換性を事前確認する。

Python interpreter 自体は CI 上 `actions/setup-python@v5` で 3.11.9 に pin される (`.github/workflows/release.yml`)。local build では `python --version` (PATH 上の `python` コマンド) を build script 冒頭で sanity check する。

> **履歴**: 旧 Python 3.11 embed + get-pip.py SHA pin フローは [#649](https://github.com/Idios/kobutachan-allaganeye/issues/649) (PR [#651](https://github.com/Idios/kobutachan-allaganeye/pull/651)) → [PR #675](https://github.com/Idios/kobutachan-allaganeye/pull/675) Round 2 #7 → [#681](https://github.com/Idios/kobutachan-allaganeye/issues/681) / PR [#703](https://github.com/Idios/kobutachan-allaganeye/pull/703) の versioned tag 化を経て [#752](https://github.com/Idios/kobutachan-allaganeye/issues/752) で PyInstaller `--onedir` に移行した。
