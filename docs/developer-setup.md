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

**Windows**:

**推奨: BtbN の LGPLv3 ビルド** (CI / Portable ZIP と同一系列、#508)。[BtbN/FFmpeg-Builds/releases](https://github.com/BtbN/FFmpeg-Builds/releases) の monthly snapshot から `ffmpeg-n8.1-*-win64-lgpl-shared*.zip` (実アセット名は `ffmpeg-n8.1-11-g75d37c499d-win64-lgpl-shared-8.1.zip` のように末尾に snapshot 系列が付く場合がある) をダウンロードして任意のフォルダに展開し、`ALLAGANEYE_FFMPEG` にその `bin/` を指定します:

```bash
# 現在のセッションのみ
set ALLAGANEYE_FFMPEG=C:\path\to\ffmpeg-n8.1-11-g75d37c499d-win64-lgpl-shared-8.1\bin
```

パッケージマネージャ経由でも動作しますが、いずれも **GPL ビルド**であり CI / Portable ZIP 同梱版 (LGPLv3) とライセンス系列が異なります。手軽さを優先する場合のみ使ってください:

```bash
# winget (GPL ビルド)
winget install Gyan.FFmpeg

# scoop (GPL ビルド)
scoop install ffmpeg

# Chocolatey (GPL ビルド)
choco install ffmpeg
```

`winget` のインストール先は自動検索されるため、`Gyan.FFmpeg` を使う場合 PATH 設定は通常不要です (後方互換、`allaganeye/ffmpeg_path.py`)。

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
pip install -e ".[dev]" -c constraints.txt
```

**`-c constraints.txt` を省略しないでください。** `pyproject.toml` の範囲指定は「範囲内の最新」に解決されるため、それだけでは CI・他の開発者・配布物と同じ版になりません (#916)。省略すると `pytest tests/test_dependency_pins.py` が赤くなります。

> SSH を使う場合: `git clone git@github.com:Idios/kobutachan-allaganeye.git`
>
> **注意**: 仮想環境を使わずに `pip install -e .` すると、`allaganeye` コマンドが PATH の通らないディレクトリにインストールされることがあります（特に Microsoft Store 版 Python）。仮想環境の使用を推奨します。

### lint ツールの版を CI と揃える (#907)

`ruff` と `pyright` は `pyproject.toml` の dev extras で **exact pin** してあります (`ruff==0.16.1` / `pyright==1.1.411`)。

**範囲指定 (`>=0.16,<0.17` 等) では足りません。** CI は毎回まっさらな環境へ `pip install -e ".[dev]" -c constraints.txt` するため、範囲内の新リリースが出た瞬間に CI だけが上がり、ローカルは古い範囲内バージョンのまま残ります。これは pin が潰そうとしている drift そのものです。`pyright` は patch リリースで診断が変わるため特に危険です。

pin を更新した後は必ず再インストールしてください。

```bash
pip install -e ".[dev]" -c constraints.txt --upgrade
```

現在の版は **CLI に聞いて**確認します。

```bash
ruff --version
pyright --version
```

**`pyright` はパッケージ版と実行版が別物になりえます。** PyPI の `pyright` は wrapper で、解析器本体の版は `PYRIGHT_PYTHON_FORCE_VERSION` / `PYRIGHT_PYTHON_PYLANCE_VERSION` で上書きできます (`pyright/_utils.py` の `_get_configured_pyright_version()`)。実測:

```text
$ PYRIGHT_PYTHON_FORCE_VERSION=1.1.405 pyright --version
pyright 1.1.405
$ python -c "import importlib.metadata as m; print(m.version('pyright'))"
1.1.411
```

つまり `importlib.metadata` で確認しても runtime の版は保証されません。**`pyright --version` の出力が pin と一致すること**を確認してください。上記の環境変数を設定している場合は、CI (未設定) と結果が食い違います。

> **版の一致は解析対象の環境を保証しません (#974)。** `pyright` は解析する環境を PATH 上の `python` から**別に**解決するため、版が pin どおりでも `.venv` を見ずに `reportMissingImports` を量産することがあります。ゲートを回すときは §4 開発用コマンド の `python -m pyright` を使ってください (activate せずに回す必要があるときだけ、`--pythonpath` に repo root の `.venv` を**絶対パスで**渡します)。

### Windows: `pyright` の install が MAX_PATH で失敗する場合 (#907)

`pyright` は typeshed の stub を大量に同梱しており、パスの深いところへ入れると **Windows の MAX_PATH** に当たって install が失敗します。エラーは次の形で出ます。

```text
ERROR: Could not install packages due to an OSError: [Errno 2] No such file or directory:
'...\site-packages\pyright\dist\dist\typeshed-fallback\stubs\...\<長いファイル名>.pyi'
```

**原因はディスク不足でもパッケージ破損でもなくパス長です。**

数え方を明示します。以下「suffix」は **site-packages の直後の区切り文字を含めた**部分の長さです。**pyright 1.1.411 で全 6344 ファイルを走査した最長 suffix は 127 文字**でした。

```text
\pyright\dist\dist\typeshed-fallback\stubs\oauthlib\oauthlib\oauth2\rfc6749\grant_types\resource_owner_password_credentials.pyi
```

**エラーに出るパスが最長とは限りません** (install 順で最初に失敗したものが表示されます)。上の 127 は pyright 1.1.411 の実測値で、版が変われば変わります。次のコマンドで測り直せます。

```bash
python -c "import pathlib,pyright; r=pathlib.Path(pyright.__file__).parent; sp=r.parent; print(max(len(str(f)[len(str(sp)):]) for f in r.rglob('*')), r)"
```

`site.getsitepackages()` を決め打ちせず **`pyright` のパッケージ位置から導出**しているので、venv の内外やユーザー site へ落ちた場合でも正しい場所を測ります。測定先のパスも併せて出力するので、意図した環境を見ているか確認してください。

**install が完了している環境で実行してください。** 後述の partial install が残っていると、そこを import できてしまい**実際より小さい値を黙って返します** (本 repo の環境で実測 120)。`python -c "import importlib.metadata as m; m.version('pyright')"` が `PackageNotFoundError` を出す場合は partial install です。

Windows の ANSI API はフルパスを **259 文字まで**しか扱えません (終端 NUL を含めて 260)。つまり `len(site-packages) + 127 > 259` で失敗し、これは **site-packages が 133 文字以上**と同値です。

| site-packages の場所 | 長さ | + suffix 127 | 判定 |
| --- | --- | --- | --- |
| Microsoft Store 版 Python のユーザー site-packages (`%LOCALAPPDATA%\Packages\PythonSoftwareFoundation.Python.3.12_...\LocalCache\local-packages\Python312\site-packages`) | 138 | 265 | **NG** (上限 259 超) |
| repo 直下の `.venv` (`<repo>\.venv\Lib\site-packages`) | 74 | 201 | OK (余裕 58 文字) |
| worktree 内の `.venv` (`<repo>\.claude\worktrees\<name>\.venv\Lib\site-packages`) | 119 | 246 | OK (余裕 13 文字) |

**対処は仮想環境を使うこと**です (本 doc が元々推奨している方法)。repo 直下の `.venv` が最も余裕があります。

`LongPathsEnabled` を有効化する方法もありますが、レジストリ変更 + 管理者権限が必要で、他の開発者環境に前提を持ち込むため**推奨しません**。現在の設定は次で確認できます。

```powershell
Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled
```

書き込み先の長さは次で確認できます。venv の外では pip の書き込み先が一意に決まらない (システム側が書ければそこへ、書けなければユーザー側へ落ちる) ため、両方を表示します。

```bash
python -c "import sys,site,sysconfig; venv = sys.prefix != sys.base_prefix; cands = [('venv', sysconfig.get_paths()['purelib'])] if venv else [('system', sysconfig.get_paths()['purelib']), ('user', site.getusersitepackages())]; [print(k, len(q), len(q)+127, 'OK' if len(q)+127 <= 259 else 'NG') for k,q in cands]"
```

**このコマンドが返すのは既定の `pip install` 構成での目安であって保証ではありません。** `PIP_TARGET` / `PIP_PREFIX` / `pip install --target` / pip config の `target` などで書き込み先を変えている場合、venv の中にいても pip は表示されたパスとは別の場所へ書きます。**確実な判定は実際に `pip install` を走らせること**で、本節はそれが失敗したときに原因を読み解くためのものです。

**install が途中で失敗すると partial な `pyright` ディレクトリが残ります。** その状態では `importlib.metadata` が `PackageNotFoundError` を出す一方でファイルは存在するため、再 install の前に残骸を削除してください (削除自体も MAX_PATH に当たる場合は `robocopy` で空ディレクトリと同期する方法があります)。

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
依存パッケージが追加・変更された場合のみ `pip install -e ".[dev]" -c constraints.txt` の再実行が必要です。

## 4. 開発用コマンド

```bash
# テスト（slow マーカー除外）
pytest

# slow マーカー付きテスト（動画ファイル必要）
pytest -m slow

# 単体テスト
pytest tests/test_detector.py

# Lint (touched file だけでなく repo 全体を対象にする。`.` を省略しない)
ruff check .
ruff format --check .

# 型チェック (--pythonpath で解析対象を明示する。理由は下の注記)
pyright --pythonpath "$(dirname "$(git rev-parse --git-common-dir)")/.venv/Scripts/python.exe"
```

> **`ruff format --check` は必ず `.` を付けて repo 全体で回す (#907)**: 触ったファイルだけを指定すると、subagent や別 PR が入れた変更を取りこぼして CI の Format check だけが赤になります。CI (`.github/workflows/ci.yml`) も `ruff format --check .` で全 repo を見ます。
>
> **版がずれていると同じコマンドでも結果が変わります。** `ruff` / `pyright` は `pyproject.toml` の dev extras で上限付きに pin してあるので、pin を更新したら `pip install -e ".[dev]" -c constraints.txt --upgrade` を実行してから回してください (§パッケージのインストール の注記参照)。
>
> **`pyright` は `--pythonpath` を省略しないでください (#974)**: `pyright` は解析対象の環境を **PATH 上の `python`** から解決します。venv を activate していない状態で回すと venv の site-packages を見ず、大量の `reportMissingImports` を出します (実測: `183 errors, 4 warnings`。うち `Import "pytest" could not be resolved` 等)。
>
> **どの呼び方が効くかは実測した。** `--pythonpath --verbose` で pyright が実際に採った search path を見た結果:
>
> | 呼び方 | cwd | 解析対象 |
> | --- | --- | --- |
> | `pyright` (素) | どこでも | PATH の `python`。activate 依存で不定 |
> | `python -m pyright` | worktree | **venv ではない** (system python の site-packages が出た)。wrapper は `sys.executable` を pyright へ渡さないので、`python -m` にしても解析対象は変わらない |
> | `pyright --pythonpath .venv/Scripts/python.exe` | repo root | venv ✓ (`exit 0`) |
> | 同上 | worktree | **`183 errors` / `exit 1`** — worktree に `.venv` は無い |
> | `pyright --pythonpath <repo root の .venv を絶対パスで>` | どこでも | venv ✓ (`exit 0`) |
>
> したがって **`--pythonpath` が唯一の確実な指定手段**で、`python -m pyright` はこの問題を解決しません。§4 に載せた `git rev-parse --git-common-dir` から解決する形は、repo root でも worktree でも同じ venv を指すので copy-paste でそのまま使えます (両方で `exit 0` を実測)。
>
> **worktree で相対パスを使わないでください。** `.claude/worktrees/<name>/` に `.venv` は存在しません (venv は repo root にのみ作る)。相対指定は**存在しない interpreter を渡すこと**になり、この症状をそのまま再現します。
>
> **`pyright` は解決できない interpreter を渡しても hard fail せず、ただ赤くなります。** 赤の理由が画面に出ないので、`reportMissingImports` が大量に出たら**まず環境の解決を疑ってください** (型エラーを直そうとしても直りません)。
>
> **CI は PATH の python へ直接 install するのでこの問題が起きず、ローカルだけが赤くなります。** そのため CI (`.github/workflows/ci.yml`) は素の `pyright` のままで正しく、ここを揃える必要はありません。
>
> なお **`pyright --version` の一致確認ではこの問題を検出できません**。版が pin どおりでも、解析対象の環境はそれとは別に解決されるためです。

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
allaganeye split <video_path> --no-audio      # 音声昇格の無効化フラグ（#327 で凍結、#865 で期限なし凍結が正式方針。常にスキップ）
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

### 依存 constraints の bump 手順 (#916)

Python 依存は 2 層で管理します。

| ファイル | 役割 | 書き方 |
| --- | --- | --- |
| `pyproject.toml` | **外部への互換範囲の宣言** (公開契約)。PyPI から install する第三者が満たすべき範囲 | 上限付きの範囲 (`>=X,<Y`)。直接 import するものだけを宣言する |
| `constraints.txt` | **この repo 自身の再現環境**。CI / ローカル / Portable ZIP build を同一版に揃える | `name==version` の exact pin のみ |

**範囲指定は再現環境になりません。** `opencv-python-headless>=4.8,<5` は実測で 4.14.0.94 に解決します (bit-exact baseline を取得した 4.13.0.92 とは別実装)。再現は `constraints.txt` の `==` が担います。

bump 手順:

1. `constraints.txt` の該当行を更新する。値は必ず `pyproject.toml` の範囲内にすること (矛盾すると pip が `ResolutionImpossible` で落ちる)
2. `pip install -e ".[dev]" -c constraints.txt --upgrade` で再インストールする
3. `pytest tests/test_dependency_pins.py` が緑になることを確認する。**pip は constraints file の未使用行を無言で無視する**ため、この test が「pin が実際に効いているか」の唯一の検査です
4. 影響範囲に応じて追加検証する (下表)

| bump するもの | 追加で必要な検証 |
| --- | --- |
| `opencv-python-headless` / `numpy` / `scipy` | **bit-exact baseline の再取得** (`pytest -m slow_detect`、実機 GPU で数時間規模)。検出出力が変わりうるため必須。`cv2` の場合は `tests/test_dependency_pins.py` の `getBuildInformation` の `GUI:` 行 assert も実出力に合わせて再確認する |
| `datamodel-code-generator` / `black` / `isort` | `python scripts/codegen/generate.py --py` を実行し `git diff --exit-code allaganeye/metadata_types.py` が緑であること (CI の codegen gate と同じ検査) |
| `rich` | `pytest tests/test_cli.py` (help 出力の整形に影響する) |

同時に触る場所: `constraints.txt` / `pyproject.toml` (範囲を外れる場合) / `.github/workflows/ci.yml` (install 行を増やした場合は `-c` を付ける) / `scripts/build-portable-zip.ps1` (同上。Pester の `Dependency constraints wiring (#916)` が statement 数と call-form を pin している)。

**`-c` の射程外**: `[build-system] requires` の `setuptools` は PEP 517 の分離ビルド環境で解決されるため constraints では固定できません。`pip` 自身の版も固定していません。第三者の `pip install kobutachan-allaganeye` にも効きません (そちらは `pyproject.toml` の範囲だけが効く)。
