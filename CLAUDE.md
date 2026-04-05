# Allagan Eye

## プロジェクト概要

FF14 PvPコンテンツ「フロントライン」の長時間録画動画（OBS, MP4/MKV）から、試合単位の分割・ハイライト抽出・投稿価値の評価を段階的に自動化するCLIツール。

### 段階的アーキテクチャ

**コアレイヤー（L1〜L4）**

| レイヤー | 処理 | 技術 | 状態 |
|---|---|---|---|
| L1: 試合分割 | 暗転検知で試合単位に分割 | FFmpeg（検知+分割） | **実装中** |
| L2: メタデータ化 | キルログ・音声・チャットをタイムスタンプ化 | Tesseract / Whisper | 未着手 |
| L3: 価値評価 | 抽出データをLLMが判定 | Claude API / Gemini API | 未着手 |
| L4: 自動編集 | 判定に基づき動画切り出し・投稿提案 | MoviePy / FFmpeg | 未着手 |

**拡張レイヤー（L5〜L7、暫定）**

| レイヤー | 処理 | 状態 |
|---|---|---|
| L5: guard 連携 | allaganeye-guard 統合 | 計画中 |
| L6: 配布・UX | ゼロ環境構築配布、GUI | 計画中 |
| L7: プライバシー・精密分割 | プレイヤー名ぼかし、再エンコード分割 | 計画中 |

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
allaganeye split <video_path> --gpu     # GPU アクセラレーション検知
allaganeye split <video_path> --workers 8  # ワーカー数指定
allaganeye debug-brightness <video_path>   # フレーム輝度 CSV 出力
```

## アーキテクチャ

### データフロー（L1）

```
MP4/MKV入力 → probe.py（ffprobe でメタデータ取得）
           → detector.py（ffmpeg 並列 -ss プローブで暗転検知 → 試合境界タイムスタンプ）
           → splitter.py（FFmpeg -c copy で無劣化分割）
           → 出力: 試合ごとのMP4 + metadata.json
```

### モジュール構成

| モジュール | 責務 |
|---|---|
| `cli.py` | Typer CLIエントリポイント。コマンドルーティング |
| `config.py` | 設定管理（検知閾値、出力パス等） |
| `exceptions.py` | エラークラス + exit code マッピング |
| `commands/split_matches.py` | split コマンドのオーケストレーション。タイムスタンプ表示・gap 検出・sample_interval 自動調整 |
| `commands/debug_brightness.py` | debug-brightness コマンド。フレーム輝度を CSV 出力（閾値チューニング用） |
| `video/probe.py` | ffprobe でメタデータ取得（解像度、fps、長さ） |
| `video/detector.py` | ffmpeg 並列プローブで暗転検知、試合境界抽出（CPU モード） |
| `video/gpu_detector.py` | GPU アクセラレーション検知（チャンク並列デコード） |
| `video/splitter.py` | FFmpeg で動画分割（-c copy） |

### 検知アルゴリズム（detector.py）

**Pass 1: 粗いスキャン**
1. `duration_hint` から `sample_interval` 秒間隔のタイムスタンプを生成（長時間動画は自動で 2-3s に調整）
2. 各タイムスタンプで `ffmpeg -threads 1 -ss {t} -i` により 1 フレームを 320x180 grayscale でデコード
3. `ThreadPoolExecutor(max_workers=min(cpu_count, 24))` で並列実行
4. 各フレームの平均輝度が `blackout_threshold` 以下なら暗転と判定
5. 連続する暗転フレームを `_group_blackout_regions()` で blackout region にマージ

**transition expansion**
6. 各暗転領域の前後で brightness < 55（`_TRANSITION_THRESHOLD`）のフレームが連続する区間を暗転領域に含めて拡張

**Pass 2: 精密計測**
7. 各暗転候補の ±5s を 0.25s 間隔で再プローブし、正確な持続時間を計測

**フィルタリング・抽出**
8. `min(min_blackout_duration, 1.5)` 未満の短い暗転を除外（リスポーン暗転の誤判定防止）
9. blackout region 間の非暗転区間を試合セグメントとして抽出（暗転内パディング付き）

**GPU モード** (`--gpu`)
- CPU モードの Pass 1 を GPU チャンク並列デコードで代替（`gpu_detector.py`）
- 動画を N チャンク（`min(cpu_count, 16)`）に分割し、各チャンクで長寿命の ffmpeg プロセスを `-hwaccel auto` + `fps` フィルタで起動
- GPU 初期化コストを分散し、1プロセスあたり多数フレームをデコードすることで効率化
- Pass 1 以降の処理（transition expansion, Pass 2, フィルタリング）は CPU/GPU 共通
- GPU 利用不可時は自動で CPU モードにフォールバック

### Exit Codes

| コード | 意味 |
|---|---|
| 0 | 正常終了 |
| 1 | 一般エラー |
| 2 | 入力ファイル不正（存在しない、未対応形式） |
| 3 | FFmpeg / ffprobe エラー |
| 4 | 検知失敗（試合境界が見つからない） |
| 5 | 設定値不正（パラメータの範囲外等） |

### 外部依存

- **ffmpeg / ffprobe**: 4.1 以上。PATH、`ALLAGANEYE_FFMPEG` 環境変数、または OS 別既知パスから自動検索（`allaganeye/ffmpeg_path.py`）
  - Windows: winget (`Gyan.FFmpeg`) のインストール先を自動検索
  - macOS: Homebrew (`/opt/homebrew/bin`, `/usr/local/bin`) を自動検索
- **Python パッケージ**: numpy, typer（opencv-python は L1 では不要。L2 以降で使用予定）
- **対応プラットフォーム**: Windows（メイン）、Linux（CI 済み）、macOS（動作想定、CI は将来）

### 動画サンプルデータ

テスト・開発用の録画データは環境変数 `ALLAGANEYE_SAMPLE_VIDEO_DIR` で指定する。

```bash
# Windows (デフォルトの録画保存先)
set ALLAGANEYE_SAMPLE_VIDEO_DIR=E:\royalstraightflesh\videos

# Linux / macOS
export ALLAGANEYE_SAMPLE_VIDEO_DIR=/path/to/videos
```

- MKV: OBSの長時間録画（30-80GB、複数試合を含む）
- サブディレクトリ（`20260116/` 等）: 手動で試合分割済みのMP4（`YYYYMMDD_N.mp4`）
- 未設定の場合、`sample_video_dir` fixture を使うテスト（`slow` マーカー）はスキップされる

## セキュリティ検査（allaganeye-guard 連携）

外部ユーザーから受領した動画ファイルを処理する前に、独立ツール `allaganeye-guard` でセキュリティ検査を行う。詳細は `docs/guard-integration.md` を参照。

- **リポジトリ**: [Idios/kobutachan-allaganeye-guard](https://github.com/Idios/kobutachan-allaganeye-guard)
- `allaganeye-guard verify <file>` で検査、PASS なら `allaganeye split` で処理
- 将来的に `--verify` オプションで自動呼び出しを実装予定
- guard がインストールされていなくても allaganeye 本体は正常動作する
- **開発・リリース同期**: guard 実装後、allaganeye のレイヤーリリース時に guard との互換性チェックが必要になる。ディレクターが両プロジェクトの同期を管理する（`docs/guard-integration.md` 参照）

## リリース戦略

詳細は `docs/release-strategy.md` を参照。要約:

- `develop-x.x.x` が日常の統合先、`main` はリリース時のみ更新
- 各ロールの PR はすべて `develop-x.x.x` にマージ
- リリース時に `develop-x.x.0 → main` マージ + タグ打ち
- レイヤーごとに minor バージョン（L1=0.1, L2=0.2, L3=0.3, L4=0.4）

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
- 作成者明示: 本文末尾に `作成: <session-id>`
- ラベル: prefix ラベル + `role:*` + 優先度（`P1-high` / `P2-medium` / `P3-low`）
- `[bug]`/`[refactor]` は初期ラベル `role:lead-engineer`（方針コメント必要）
- `role:*` ラベルは「次に誰が行動すべきか」を示す。作業進行に合わせて付替える
- `Closes`/`Fixes` キーワードは使わない（クローズは手動）

## PR 作成ルール

詳細は `docs/roles/protocol.md` を参照。要約:

- **PR 作成前**: ベースブランチをリベースし、`ruff check .` / `ruff format --check .` / `pytest` を通すこと
- ベースブランチ: `develop-x.x.x`（`main` ではない）
- ロールラベル: レビュー担当の `role:*` を付与（元 issue 作成者ロール優先）
- コード変更 PR: `role:tester` も付与（テスト実施のため）
- マージ方法: `gh pr merge <番号> --squash`
- コード変更はテスター確認必須、ドキュメントのみはレビューのみ
- コミットメッセージに `[<session-id>]` を含める

## ユーザー指示の短縮記法

| 記法 | 展開 |
|---|---|
| `is<N>` | GitHub Issue #N を参照 |
| `pr<N>` | GitHub PR #N を参照 |
| `issue#<N>` | GitHub Issue #N を参照 |
| `PR#<N>` | GitHub PR #N を参照 |
