# Allagan Eye

## プロジェクト概要

FF14 PvPコンテンツ「フロントライン」の長時間録画動画（OBS, MP4/MKV）から、試合単位の分割・ハイライト抽出・投稿価値の評価を段階的に自動化するCLIツール。

### 段階的アーキテクチャ（L1〜L4）

| レイヤー | 処理 | 技術 | 状態 |
|---|---|---|---|
| L1: 試合分割 | UI変化検知で試合単位に分割 | OpenCV + FFmpeg | **実装中** |
| L2: メタデータ化 | キルログ・音声・チャットをタイムスタンプ化 | Tesseract / Whisper | 未着手 |
| L3: 価値評価 | 抽出データをLLMが判定 | Claude API / Gemini API | 未着手 |
| L4: 自動編集 | 判定に基づき動画切り出し・投稿提案 | MoviePy / FFmpeg | 未着手 |

**設計原則**: AIは判定・評価に使う。動画編集・変換はFFmpeg/OpenCV等のライブラリで実行する。

## コマンド

```bash
# テスト
pytest                          # 全テスト（slowマーカー除外）
pytest -m slow                  # 動画ファイル必要なテスト
pytest tests/test_detector.py   # 単体テスト

# Lint / 型チェック
ruff check .
ruff format --check .
pyright

# CLI
allaganeye split <video_path>           # 試合分割
allaganeye split <video_path> -o <dir>  # 出力先指定
```

## アーキテクチャ

### データフロー（L1）

```
MP4/MKV入力 → probe.py（メタデータ取得）
           → detector.py（OpenCVでUI変化検知 → 試合境界タイムスタンプ）
           → splitter.py（FFmpeg -c copy で無劣化分割）
           → 出力: 試合ごとのMP4 + metadata.json
```

### モジュール構成

| モジュール | 責務 |
|---|---|
| `cli.py` | Typer CLIエントリポイント。コマンドルーティング |
| `config.py` | 設定管理（検知閾値、出力パス等） |
| `exceptions.py` | エラークラス + exit code マッピング |
| `commands/split_matches.py` | split コマンドのオーケストレーション |
| `video/probe.py` | ffprobe でメタデータ取得（解像度、fps、長さ） |
| `video/detector.py` | OpenCV でフレーム解析、試合境界検知 |
| `video/splitter.py` | FFmpeg で動画分割（-c copy） |

### Exit Codes

| コード | 意味 |
|---|---|
| 0 | 正常終了 |
| 1 | 一般エラー |
| 2 | 入力ファイル不正（存在しない、未対応形式） |
| 3 | FFmpeg / OpenCV エラー |
| 4 | 検知失敗（試合境界が見つからない） |

### 外部依存

- **ffmpeg / ffprobe**: PATH に存在する必要あり
- **Python パッケージ**: opencv-python, ffmpeg-python, typer

### 動画サンプルデータ

テスト・開発用の録画データ: `E:\royalstraightflesh\videos\`
- MKV: OBSの長時間録画（30-80GB、複数試合を含む）
- サブディレクトリ（`20260116/` 等）: 手動で試合分割済みのMP4（`YYYYMMDD_N.mp4`）

## リリース戦略

詳細は `docs/release-strategy.md` を参照。要約:

- トランクベース開発、`main` 保護ブランチ
- レイヤーごとに minor バージョン（L1=0.1, L2=0.2, L3=0.3, L4=0.4）
- タグ: `v<major>.<minor>.<patch>`（Director がリリース時に打刻）

## ロールシステム

マルチエージェント開発に対応。詳細は `docs/roles/protocol.md` を参照。

- `/assume-role <role>`: ロール設定（director, lead-engineer, engineer, tester）
- `/setup-session <role> <number>`: Worktree セットアップ
- `/check-work`: 担当作業の発見・優先順位付け

## CLAUDE.md 継続改善

ユーザーから「CLAUDE.md に追記して」等の指示があった場合、このファイルを即座に更新する。
更新後は変更箇所をユーザーに報告する。

## GitHub Issue 作成ルール

詳細は `docs/issue-policy.md` を参照。要約:

- プレフィックス: `[bug]`, `[doc]`, `[refactor]`, `[task]`, `[question]`, `[risk]`
- Assignee: 常に `Idios`
- ラベル: `bug`, `documentation`, `enhancement`, `question` + `role:*`

## PR 作成ルール

- ロールに応じたレビューワラベルを付与
- テスト通過を確認してからマージ
- チェックリスト未完了の PR はマージしない

## ユーザー指示の短縮記法

| 記法 | 展開 |
|---|---|
| `is<N>` | GitHub Issue #N を参照 |
| `pr<N>` | GitHub PR #N を参照 |
| `issue#<N>` | GitHub Issue #N を参照 |
| `PR#<N>` | GitHub PR #N を参照 |
