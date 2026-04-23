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
├── python\            Python ランタイム（同梱済み、別途インストール不要）
├── lib\               allaganeye 本体
├── ffmpeg\            動画処理エンジン（同梱済み、別途インストール不要）
├── allaganeye.bat     ← このファイルを使います
└── README.txt
```

## 2. 基本の使い方

`allaganeye.bat` を **ダブルクリック** すると使い方のヘルプが表示されます。動画ファイル（`.mkv` / `.mp4`）を `allaganeye.bat` の上にドラッグ＆ドロップすると分割が始まります。

分割された動画は `allaganeye-vX.Y.Z\output\` フォルダに `match_001.mp4` のような形式で保存されます。

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

## 5. うまく分割されないとき

Allagan Eye は FF14 フロントラインの一般的な録画に合わせて調整されていますが、録画環境によって検知が合わないことがあります。

| 症状 | よくある原因 | 対処 |
|---|---|---|
| 試合の途中で分断される | 試合中のリスポーン暗転を誤検知 | 最小暗転時間を長くする |
| 別々の試合がくっついている | 試合間の暗転が検知閾値より明るい | 暗転輝度の閾値を上げる |
| 短い試合だけ出力されない | 最小試合時間で除外された | 最小試合時間を下げる |
| 試合が 1 つも検知されない | 閾値や録画形式が合わない | [パラメータ調整ガイド](tuning-guide.md) を参照 |
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

    rem バージョン確認
    allaganeye.bat --version
    ```

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
- **Python**: PSF License (`python\LICENSE.txt`)
- **FFmpeg**: LGPLv3 (`ffmpeg\LICENSE.txt` に全文)
  - ビルド: [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds) の win64-lgpl static build
  - 対応 FFmpeg コミット: [git.ffmpeg.org](https://git.ffmpeg.org/ffmpeg.git) の commit `7f5c90f77e` (v8.1 系列)

allaganeye 本体 (MIT) は FFmpeg バイナリをサブプロセスとしてのみ呼び出しているため、LGPLv3 の static linking 制約は allaganeye 本体には及びません。
