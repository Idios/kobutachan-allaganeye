# CLI コマンド仕様

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
| `--dry-run` | `false` | 検知のみ実行し分割しない |
| `-v`, `--verbose` | `false` | 詳細ログ出力 |

### 出力

- `output/match_001.mp4`, `match_002.mp4`, ...
- `output/metadata.json`

### Exit Codes

| コード | 意味 |
|---|---|
| 0 | 正常終了 |
| 1 | 一般エラー |
| 2 | 入力ファイル不正 |
| 3 | FFmpeg / ffprobe エラー |
| 4 | 試合境界が見つからない |
| 5 | 設定値不正（パラメータの範囲外等） |
