# Quick Start Guide

Allagan Eye は FF14 フロントラインの長時間録画動画を、試合ごとに自動で分割する Windows 向けツールです。

> ソースコードから動かしたい開発者の方は [Developer Setup Guide](developer-setup.md) を参照してください。

## 1. ダウンロードと展開

### 1.1 ダウンロード

[Releases ページ](https://github.com/Idios/kobutachan-allaganeye/releases/latest) を開き、**Assets** から `allaganeye-*-windows.zip` をクリックしてダウンロードします。

### 1.2 任意の場所に展開

ダウンロードした ZIP ファイルを、**デスクトップ** など書き込み可能な場所に展開します。管理者権限は不要です。

推奨の場所（どれを選んでも動作します）:

- デスクトップ: `%USERPROFILE%\Desktop\allaganeye\`
- ドキュメントフォルダ: `%USERPROFILE%\Documents\allaganeye\`
- ダウンロードフォルダ: `%USERPROFILE%\Downloads\allaganeye\`

### 1.3 展開手順（Windows 標準機能）

1. エクスプローラでダウンロードした `allaganeye-*-windows.zip` を右クリック
2. **「すべて展開」** を選択
3. 展開先として上記のいずれかのフォルダを指定
4. **展開** をクリック

展開後のフォルダ構成:

```text
allaganeye-vX.Y.Z\
├── allaganeye\             allaganeye 本体（Python ランタイム同梱済み、別途インストール不要）
├── ffmpeg\                 動画処理エンジン（同梱済み、別途インストール不要）
├── allaganeye.bat          ← このファイルを使います
├── allaganeye-gui.exe      GUI 本体（allaganeye.bat のダブルクリックで起動します）
├── integrity-manifest.json 同梱物の整合性検査に使います（削除しないでください）
└── README.txt
```

## 2. 基本の使い方

`allaganeye.bat` を **ダブルクリック** すると Allagan Eye の **GUI** (`allaganeye-gui.exe`) が起動します（v0.2.0 以降、[#617](https://github.com/Idios/kobutachan-allaganeye/issues/617)）。動画ファイル（`.mkv` / `.mp4`）を `allaganeye.bat` の上にドラッグ＆ドロップすると分割が始まります。GUI を使わずヘルプを見たい場合は `allaganeye.bat --help` で表示できます。

出力先は起動方法によって変わります。

- **ドラッグ＆ドロップ時**: `allaganeye-vX.Y.Z\output\` フォルダに `match_001.mp4` のような形式で保存されます
- **GUI 使用時**: 書き出し画面で出力先を指定します（既定は元の動画と同じフォルダ）

出力先には MP4 と一緒に `metadata.json` も書き出されます。これは検知結果（各試合の開始・終了時刻とその分類）を記録したファイルです。後述の `export` / `minimap` コマンドは、動画ではなくこの `metadata.json` を入力に取ります。

> 複数の動画を一度に処理することはできません。1 つずつ渡してください。

## 3. セキュリティ警告が出た場合

ダウンロードした ZIP を展開して初めて `allaganeye.bat` を実行すると、Windows が以下のいずれかの警告を出すことがあります。どちらも Windows の標準的なセキュリティ機能によるもので、悪意のあるソフトではありません。

- **「開いているファイル - セキュリティの警告」**（発行元: 不明な発行元） — ダウンロード由来の `.bat` を実行しようとしたとき
- **「WindowsによってPCが保護されました」** — Microsoft Defender SmartScreen が実行を一旦止めたとき

**方法 1（推奨）: ZIP のブロックを展開前に解除する**

1. ダウンロードした ZIP を右クリック → **プロパティ**
2. 下部「セキュリティ」の **許可する** にチェック → **OK**
3. その後で ZIP を展開

これで ZIP 内の全ファイルに付いた「Mark of the Web」が一括解除され、以降この警告は出なくなります。

**方法 2: 警告ダイアログでそのまま実行する**

- 「開いているファイル - セキュリティの警告」: **実行(R)** ボタンをクリック
- 「WindowsによってPCが保護されました」: 「詳細情報」リンク → **実行** ボタン

ただし `.bat` を実行するたびに再度警告が出るので、繰り返し使う場合は方法 1 がおすすめです。

**方法 3: それでも解決しない場合**

[Issue を起票](https://github.com/Idios/kobutachan-allaganeye/issues/new) してください（スクリーンショットと Windows バージョンを添付）。

## 4. 録画の冒頭・末尾が試合中だった場合

録画開始時にすでに試合中だった場合や、試合中に録画を停止した場合も、該当部分はセグメントとして出力されます。

- **冒頭**: 録画開始（0 秒）から最初の暗転までが 1 つのセグメントになります
- **末尾**: 最後の暗転から録画終了までが 1 つのセグメントになります

これらのセグメントは試合の途中から始まる（または途中で終わる）不完全な録画として扱われ、`metadata.json` では `type: "unknown"` と記録されます。既定では **5 分（300 秒）未満** のセグメントは出力されません。

### 録画の末尾がロビー・街だった場合（v0.3.0 以降）

試合終了後にロビーや街を映したまま録画を止めた場合、その末尾区間は `metadata.json` に `post_match: true` として記録され、**既定では MP4 に出力されません**。スコアバーが最後まで一度も映らない区間を「試合ではない」と判定するためです。

metadata には残るので情報が失われることはありませんが、`output\` フォルダを見ると「最後の区間だけファイルが無い」ように見えます。この区間も MP4 として出力したい場合は `--keep-trailing` を付けてください。

```cmd
allaganeye.bat split "C:\Users\あなた\Videos\動画.mkv" --keep-trailing
```

## 5. うまく分割されないとき

Allagan Eye は FF14 フロントラインの一般的な録画に合わせて調整されていますが、録画環境によって検知が合わないことがあります。

| 症状 | よくある原因 | 対処 |
| --- | --- | --- |
| 試合の途中で分断される | 試合中のリスポーン暗転を誤検知 | 最小暗転時間を長くする |
| 別々の試合がくっついている | 試合間の暗転が検知閾値より明るい | 暗転輝度の閾値を上げる |
| 短い試合だけ出力されない | 最小試合時間で除外された | 最小試合時間を下げる |
| **録画末尾の区間だけ MP4 が出ない** | 試合後のロビー・街と判定された（`post_match`） | `--keep-trailing` を付ける（[§4](#4-録画の冒頭末尾が試合中だった場合) 参照）。最小試合時間を下げても直りません |
| **チャット欄を画像でマスクした録画で検知できない** | 既定の検知が想定する画面と異なる | `detect` / `split` に `--masked` を付ける |
| **配信レイアウト（ゲーム画面が画面全体でない）で検知できない** | 同上 | `detect` / `split` に `--vtuber` を付ける |
| 試合が 1 つも検知されない | 閾値が合わない、または上記 2 つの録画形式 | まず `--masked` / `--vtuber` を試し、それでも駄目なら [パラメータ調整ガイド](tuning-guide.md) を参照 |
| 処理が遅い | サンプリング間隔・並列度の問題 | [パラメータ調整ガイド](tuning-guide.md) を参照 |
| 読み込み画面が長い環境で境界が検出されない | 暗転が UI 要素で分断される | 現バージョンでは未対応。[Issue 起票](https://github.com/Idios/kobutachan-allaganeye/issues/new) で報告してください |

パラメータの具体的な調整方法は [パラメータ調整ガイド](tuning-guide.md) を参照してください。コマンドラインから細かいオプションを指定したい場合は [§6 高度な使い方](#6-高度な使い方コマンドプロンプト) を参照してください。

## 6. 高度な使い方（コマンドプロンプト）

オプション指定付きで起動したい場合は、コマンドプロンプトから呼び出せます。

1. エクスプローラで `allaganeye-vX.Y.Z` フォルダを開く
2. アドレスバーに `cmd` と入力して Enter → そのフォルダでコマンドプロンプトが開く
3. 例:

    ```cmd
    rem 検知結果だけ確認（分割しない、推奨）
    allaganeye.bat detect "C:\Users\あなた\Videos\動画.mkv"

    rem 旧形式（--dry-run）も後方互換で利用可能
    allaganeye.bat split "C:\Users\あなた\Videos\動画.mkv" --dry-run

    rem 出力先を変える
    allaganeye.bat split "C:\Users\あなた\Videos\動画.mkv" -o "%USERPROFILE%\Desktop\matches"

    rem チャット欄をマスクした録画 / 配信レイアウトの録画
    allaganeye.bat detect "C:\Users\あなた\Videos\動画.mkv" --masked
    allaganeye.bat detect "C:\Users\あなた\Videos\動画.mkv" --vtuber

    rem 検知済みの metadata.json から並列で書き出す（H.264 再エンコードも可）
    allaganeye.bat export "%USERPROFILE%\Desktop\matches\metadata.json"
    allaganeye.bat export "%USERPROFILE%\Desktop\matches\metadata.json" --codec h264

    rem エリアマップ（ミニマップ）の領域を提案する
    allaganeye.bat minimap "%USERPROFILE%\Desktop\matches\metadata.json"

    rem 提案された領域で切り抜く
    allaganeye.bat minimap "%USERPROFILE%\Desktop\matches\metadata.json" --region 1520,780,380,380

    rem フレーム輝度を CSV に出す（しきい値の調整用）
    allaganeye.bat debug-brightness "C:\Users\あなた\Videos\動画.mkv"

    rem バージョン確認
    allaganeye.bat --version
    ```

`export` と `minimap` は動画ではなく `metadata.json` を入力に取ります。先に `detect` または `split` を実行して `metadata.json` を作ってください。ミニマップ切り抜きは GUI（観測完了画面の `⬦ ミニマップ切抜き`）からも実行できます。

主要オプションと出力形式の詳細は以下を参照してください:

- [CLI コマンド仕様](cli-spec.md)
- [出力仕様マトリクス](output-spec.md)
- [パラメータ調整ガイド](tuning-guide.md)

## 7. 更新方法

1. [Releases ページ](https://github.com/Idios/kobutachan-allaganeye/releases/latest) から最新の ZIP をダウンロード
2. 古い `allaganeye-vX.Y.Z` フォルダは、必要なら `output\` フォルダの中身を別の場所にコピーしてから削除
3. 新しい ZIP を展開して同じように使う

> `output\` フォルダには過去に分割した MP4 ファイルと `metadata.json` / `.detection_cache.json` が入っています。作業データを残したい場合は先にコピーしてください。

## 8. アンインストール

展開した `allaganeye-vX.Y.Z` フォルダをまるごと削除してください。レジストリには書き込まないので、他に残るファイルはありません。

## 9. 開発者の方へ

ソースコードから動かしたい、コードを修正したい、テストを追加したい場合は [Developer Setup Guide](developer-setup.md) を参照してください。

## 10. ライセンス

Portable ZIP には以下のソフトウェアが同梱されています。詳細な利用条件は各 LICENSE ファイルを参照してください。

- **allaganeye 本体**: MIT License (リポジトリの `LICENSE` ファイル)
- **Python**: PSF License (PyInstaller frozen bundle 内 `allaganeye\_internal\` に同梱。License 全文: <https://docs.python.org/3/license.html>)
- **FFmpeg**: LGPLv3 (`ffmpeg\LICENSE.txt` に全文)
  - ビルド: [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds) の win64-lgpl-shared build
  - 対応 FFmpeg ソース ref: [git.ffmpeg.org](https://git.ffmpeg.org/ffmpeg.git) の n8.1 系列 commit `g75d37c499d` (`scripts/build-portable-zip.ps1` の `$FFmpegAsset` から自動抽出)

allaganeye 本体 (MIT) は FFmpeg バイナリをサブプロセスとしてのみ呼び出しているため、LGPLv3 の linking 制約は allaganeye 本体には及びません。同梱している shared-build DLL は FFmpeg 実行ファイルが動的にロードし、LGPLv3 の配布条件は同梱ライセンステキストで充足しています。
