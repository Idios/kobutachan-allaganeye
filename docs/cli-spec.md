# CLI コマンド仕様

## 前提条件

| 要件 | 説明 |
|---|---|
| ffmpeg / ffprobe 4.1+ | 以下の順序で自動検索: (1) PATH (`shutil.which`) (2) `ALLAGANEYE_FFMPEG` 環境変数で指定したディレクトリ (3) OS 別既知パス（Windows: winget `Gyan.FFmpeg`、macOS: Homebrew） |

## グローバルオプション

| オプション | 説明 |
|---|---|
| `--version` | バージョン表示 |
| `--help` | ヘルプ表示 |
| `--verbose` / `-v` | 詳細ログ出力 |

## split コマンド

試合単位で動画を分割する。

### 構文

```bash
allaganeye split <video_path> [OPTIONS]
```

### 引数

| 引数 | 必須 | 説明 |
|---|---|---|
| `video_path` | Yes | 入力動画ファイルのパス（MP4/MKV/AVI/MOV） |

### オプション

| オプション | デフォルト | 説明 |
|---|---|---|
| `-o`, `--output-dir` | `./output` | 出力ディレクトリ |
| `--sample-interval` | `1.0` | フレームサンプリング間隔（秒） |
| `--blackout-threshold` | `15.0` | 暗転検知の輝度閾値（0-255） |
| `--min-match-duration` | `300.0` | 最小試合時間（秒）。これより短いセグメントは無視 |
| `--min-blackout-duration` | `3.0` | 最小暗転時間（秒）。これより短い暗転は無視 |
| `--workers` | auto | 検知の並列ワーカー数（デフォルト: 自動=`min(cpu_count, 24)`） |
| `--gpu` / `--no-gpu` | `false` | GPU アクセラレーション検知（チャンク並列デコード）。利用不可時は CPU フォールバック |
| `--dry-run` | `false` | 検知のみ実行し分割しない |
| `-v`, `--verbose` | `false` | 詳細ログ出力 |

### 出力

- `output/match_001.mp4`, `match_002.mp4`, ...
- `output/metadata.json`

### metadata.json

分割結果の機械可読な記録。外部ツールやスクリプトから参照可能。L2（メタデータ化）パイプラインの入力として使用予定。L2 未着手のため、フィールド構造は暫定であり破壊的変更の可能性がある。

**トップレベル:**

| フィールド | 型 | 説明 |
|---|---|---|
| `source` | string | 入力動画のファイルパス |
| `source_duration` | float | 入力動画の総再生時間（秒） |
| `source_duration_display` | string | 総再生時間の表示形式（MM:SS or H:MM:SS） |
| `note` | string | キーフレーム精度に関する注意書き |
| `matches` | array | 検出された試合セグメント |
| `gaps` | array | 試合間の有意なギャップ（≥5分） |

**matches[]:**

| フィールド | 型 | 説明 |
|---|---|---|
| `index` | int | 1始まりの試合番号 |
| `start_time` | float | 開始時刻（秒） |
| `end_time` | float | 終了時刻（秒） |
| `start_display` | string | 開始時刻の表示形式 |
| `end_display` | string | 終了時刻の表示形式 |
| `duration` | float | 試合時間（秒） |
| `duration_display` | string | 試合時間の表示形式 |
| `output_file` | string | 出力ファイルパス |

**gaps[]:**

| フィールド | 型 | 説明 |
|---|---|---|
| `start_display` | string | ギャップ開始時刻 |
| `end_display` | string | ギャップ終了時刻 |
| `duration_display` | string | ギャップ時間 |

## debug-brightness コマンド

フレーム輝度を CSV 出力する。暗転検知の閾値チューニング用。

### 構文

```bash
allaganeye debug-brightness <video_path> [OPTIONS]
```

### 引数

| 引数 | 必須 | 説明 |
|---|---|---|
| `video_path` | Yes | 入力動画ファイルのパス（MP4/MKV/AVI/MOV） |

### オプション

| オプション | デフォルト | 説明 |
|---|---|---|
| `--start` | `0.0` | 開始時刻（秒） |
| `--end` | 動画全長 | 終了時刻（秒） |
| `--interval` | `1.0` | サンプリング間隔（秒） |
| `--workers` | auto | 並列ワーカー数（デフォルト: 自動=`min(cpu_count, 24)`） |

### 出力形式

CSV 形式で stdout に出力。パイプやリダイレクトで利用可能。

```
timestamp,brightness
0.0,12.3
1.0,245.6
2.0,8.1
```

| フィールド | 型 | 説明 |
|---|---|---|
| `timestamp` | float | タイムスタンプ（秒、小数点1桁） |
| `brightness` | float | フレームの平均輝度（0.0-255.0、小数点1桁） |

### Exit Codes

| コード | 意味 |
|---|---|
| 0 | 正常終了 |
| 1 | 一般エラー |
| 2 | 入力ファイル不正 |
| 3 | FFmpeg / ffprobe エラー |
| 4 | 試合境界が見つからない |
| 5 | 設定値不正（パラメー���の範囲外等） |
| 6 | セキュリティ検査不合��（allaganeye-guard 連携時） |
