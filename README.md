# Allagan Eye

FF14 PvPコンテンツ「フロントライン」の長時間録画動画から、試合単位の分割・ハイライト抽出・投稿価値の評価を段階的に自動化するCLIツール。

## 段階的アーキテクチャ

```
L1: 試合分割        ← 現在のスコープ
 ↓
L2: メタデータ化    (OCR / 音声認識でタイムスタンプ化)
 ↓
L3: 価値評価        (LLMによる投稿価値判定)
 ↓
L4: 自動編集        (切り出し + 投稿提案)
```

## 現在の機能（L1: 試合分割）

OBS録画のMP4/MKVファイルを入力し、OpenCVによるUI変化検知で試合境界を検出。FFmpegのコピーモード（`-c copy`）で無劣化・高速に試合ごとのMP4ファイルへ分割する。

### コマンド

```bash
# 試合分割
allaganeye split <video_path>

# 出力先を指定
allaganeye split <video_path> -o <output_dir>
```

### 出力

```
output/
├── match_001.mp4
├── match_002.mp4
├── match_003.mp4
└── metadata.json    # 各試合の開始/終了時刻、推定情報
```

### Exit Codes

| コード | 意味 |
|---|---|
| 0 | 正常終了 |
| 1 | 一般エラー |
| 2 | 入力ファイル不正 |
| 3 | FFmpeg / OpenCV エラー |
| 4 | 検知失敗（試合境界が見つからない） |

## 前提条件

- Python 3.11+
- ffmpeg / ffprobe（PATH に存在すること）
- OBS 録画の MP4 または MKV ファイル

## セットアップ

```bash
# 開発用インストール
pip install -e ".[dev]"

# テスト実行
pytest

# Lint
ruff check .
pyright
```

## プロジェクト構成

```
kobutachan-allaganeye/
├── allaganeye/           # メインパッケージ
│   ├── cli.py            # CLI エントリポイント
│   ├── config.py         # 設定管理
│   ├── exceptions.py     # エラークラス
│   ├── commands/         # コマンド実装
│   │   └── split_matches.py
│   └── video/            # 動画処理
│       ├── detector.py   # UI変化検知
│       ├── splitter.py   # 動画分割
│       └── probe.py      # メタデータ取得
├── tests/                # テスト
├── docs/                 # ドキュメント
├── .claude/              # Claude Code 設定
└── .github/workflows/    # CI
```

## ロードマップ

- [ ] **L1**: 試合分割（UI変化検知 + FFmpeg分割）
- [ ] **L2**: メタデータ化（Tesseract OCR + Whisper音声認識）
- [ ] **L3**: 価値評価（Claude API / Gemini API によるハイライト判定）
- [ ] **L4**: 自動編集（MoviePy切り出し + YouTube投稿提案）

## 関連ドキュメント

- [システムアーキテクチャ](docs/design-overview.md)
- [CLIコマンド仕様](docs/cli-spec.md)
- [動画処理設計](docs/video-processing.md)
- [Issue作成ルール](docs/issue-policy.md)
- [コーディング規約](docs/coding-conventions.md)
- [バージョニング](docs/versioning.md)
