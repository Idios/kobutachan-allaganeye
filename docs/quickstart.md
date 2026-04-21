# Quick Start Guide

Allagan Eye は FF14 フロントラインの長時間録画動画を、試合ごとに自動で分割するツールです。Windows 専用です。

このガイドは **Portable ZIP 版** の使い方です。Git や Python のインストールは不要です。

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

> `C:\Program Files\` や `C:\Windows\` のようなシステムフォルダは**避けてください**。展開や実行に管理者権限が必要になります。

### 1.3 展開手順（Windows 標準機能）

1. エクスプローラでダウンロードした `allaganeye-*-windows.zip` を右クリック
2. **「すべて展開」** を選択
3. 展開先として上記のいずれかのフォルダを指定
4. **展開** をクリック

展開後のフォルダ構成:

```
allaganeye-vX.Y.Z\
├── python\            Python ランタイム（同梱済み、別途インストール不要）
├── lib\               allaganeye 本体
├── ffmpeg\            動画処理エンジン（同梱済み、別途インストール不要）
├── allaganeye.bat     ← このファイルを使います
└── README.txt
```

## 2. 基本の使い方: 動画ファイルを `allaganeye.bat` にドラッグ＆ドロップ

もっとも簡単な手順です。

1. 展開した `allaganeye-vX.Y.Z` フォルダを開く
2. 分割したい動画ファイル（`.mkv` や `.mp4`）を、別のエクスプローラウィンドウやデスクトップから用意
3. 動画ファイルを **`allaganeye.bat`** の上にドラッグ＆ドロップ

コマンドプロンプトのウィンドウが開き、検知と分割が自動で進みます。処理が終わったら、**Enter キーなどで結果を確認してから閉じて**ください。

分割された動画は、**`allaganeye-vX.Y.Z\output\`** フォルダ内に `match_001.mp4` のような形式で保存されます。

> 複数の動画を一度に処理することはできません。1 つずつドラッグ＆ドロップしてください。

## 3. ダブルクリックで起動した場合

`allaganeye.bat` を **ダブルクリック** すると、使い方のヘルプが表示されます。そのまま閉じずに、ヘルプを読んでから動画ファイルをドラッグ＆ドロップすると分割が始まります。

## 4. SmartScreen 警告が出た場合

`allaganeye.bat` には allaganeye 独自の実行ファイル（`.exe`）が含まれないため、通常は Microsoft Defender SmartScreen の警告は出ません。同梱の `python.exe`・`ffmpeg.exe`・`ffprobe.exe` はそれぞれ配布元（python.org / gyan.dev）で署名されています。

しかし、以下の状況では警告が出ることがあります:

- ZIP ダウンロード直後で Windows が「Mark of the Web」を付与している
- 企業ネットワーク等で SmartScreen のポリシーが厳格化されている
- 古い Windows で配布元の署名を信頼していない

### 対処法

**方法 1（推奨）: ZIP のブロックを展開前に解除する**

1. エクスプローラでダウンロードした ZIP を右クリック → **プロパティ**
2. 下部「セキュリティ」欄の **許可する** にチェック
3. **OK** をクリックしてから ZIP を展開

**方法 2: 警告ダイアログで「実行」を選ぶ**

1. 「WindowsによってPCが保護されました」と表示されたら、青色の **詳細情報** をクリック
2. 表示される **実行** ボタンをクリック

**方法 3: それでも解決しない場合**

[Issue を起票](https://github.com/Idios/kobutachan-allaganeye/issues/new) してください。スクリーンショット・Windows のバージョン・SmartScreen の表示内容を添付していただけると助かります。

> 現時点では EV コード署名証明書を導入していません。将来的に allaganeye 独自の `.exe`（PyInstaller や MSI インストーラ）を提供する段階で再検討します (#462)。

## 5. 録画の冒頭・末尾が試合中だった場合

録画開始時にすでに試合中だった場合や、試合中に録画を停止した場合も、該当部分はセグメントとして出力されます。

- **冒頭**: 録画開始（0 秒）から最初の暗転までが 1 つのセグメントになります
- **末尾**: 最後の暗転から録画終了までが 1 つのセグメントになります

これらのセグメントは試合の途中から始まる（または途中で終わる）不完全な録画として扱われ、`metadata.json` では `type: "unknown"` と記録されます。既定では **5 分（300 秒）未満** のセグメントは出力されません。

## 6. うまく分割されないとき

Allagan Eye は FF14 フロントラインの一般的な録画に合わせて調整されていますが、録画環境によって検知が合わないことがあります。

| 症状 | よくある原因 | 対処 |
|---|---|---|
| 試合の途中で分断される | 試合中のリスポーン暗転を誤検知 | 最小暗転時間を長くする |
| 別々の試合がくっついている | 試合間の暗転が検知閾値より明るい | 暗転輝度の閾値を上げる |
| 短い試合だけ出力されない | 最小試合時間で除外された | 最小試合時間を下げる |
| 試合が 1 つも検知されない | 閾値や録画形式が合わない | [パラメータ調整ガイド](tuning-guide.md) を参照 |
| 処理が遅い | サンプリング間隔・並列度の問題 | [パラメータ調整ガイド](tuning-guide.md) を参照 |
| 読み込み画面が長い環境で境界が検出されない | 暗転が UI 要素で分断される | 現バージョンでは未対応。[Issue 起票](https://github.com/Idios/kobutachan-allaganeye/issues/new) で報告してください |

パラメータの具体的な調整方法は [パラメータ調整ガイド](tuning-guide.md) を参照してください。コマンドラインから細かいオプションを指定したい場合は [§7 高度な使い方](#7-高度な使い方コマンドプロンプト) を参照してください。

## 7. 高度な使い方（コマンドプロンプト）

オプション指定付きで起動したい場合は、コマンドプロンプトから呼び出せます。

1. エクスプローラで `allaganeye-vX.Y.Z` フォルダを開く
2. アドレスバーに `cmd` と入力して Enter → そのフォルダでコマンドプロンプトが開く
3. 例:

    ```cmd
    rem 検知結果だけ確認（分割しない）
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

## 8. 更新方法

1. [Releases ページ](https://github.com/Idios/kobutachan-allaganeye/releases/latest) から最新の ZIP をダウンロード
2. 古い `allaganeye-vX.Y.Z` フォルダは、必要なら `output\` フォルダの中身を別の場所にコピーしてから削除
3. 新しい ZIP を展開して同じように使う

> `output\` フォルダには過去に分割した MP4 ファイルと `metadata.json` / `.detection_cache.json` が入っています。作業データを残したい場合は先にコピーしてください。

## 9. アンインストール

展開した `allaganeye-vX.Y.Z` フォルダをまるごと削除してください。レジストリには書き込まないので、他に残るファイルはありません。

## 10. 開発者の方へ

ソースコードから動かしたい、コードを修正したい、テストを追加したい場合は [Developer Setup Guide](developer-setup.md) を参照してください。
