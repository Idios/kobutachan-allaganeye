# Allagan Eye

FF14 フロントラインの長時間録画動画を、試合ごとに自動で分割する Windows 向けツールです。

OBS などで録画した数時間分の動画を入力すると、試合の切れ目を自動検知し、試合ごとの MP4 ファイルに無劣化で分割します。

## クイックスタート

1. [Releases ページ](https://github.com/Idios/kobutachan-allaganeye/releases/latest) から `allaganeye-*-windows.zip` をダウンロード
2. ZIP をデスクトップなどに展開
3. 分割したい動画ファイルを、展開したフォルダ内の `allaganeye.bat` にドラッグ＆ドロップ

分割結果は `allaganeye-*\output\` フォルダに保存されます。

詳しい手順や SmartScreen 警告への対処は [Quick Start Guide](docs/quickstart.md) を参照してください。

## 対応プラットフォーム

Windows 専用です。Python や FFmpeg の事前インストールは必要ありません（ZIP に同梱されています）。

## ドキュメント

### 一般ユーザー向け

- [Quick Start Guide](docs/quickstart.md) — Portable ZIP の使い方、SmartScreen 警告、トラブルシュート
- [パラメータ調整ガイド](docs/tuning-guide.md) — 分割結果が期待と異なるときのチューニング

### 開発者向け

- [Developer Setup Guide](docs/developer-setup.md) — ソースコードから動かす手順（Git / Python / venv）
- [CLI コマンド仕様](docs/cli-spec.md)
- [出力仕様マトリクス](docs/output-spec.md)
- [システムアーキテクチャ](docs/design-overview.md)
- [動画処理設計](docs/video-processing.md)
- [リリース戦略](docs/release-strategy.md)

## ロードマップ

| フェーズ | 機能 | 状態 |
|---|---|---|
| L1 | 試合分割 | リリース済み (v0.1.1) |
| L2 | 配布・統合 (GUI + インストーラ + guard) | 開発中 |
| L3 | メタデータ化（OCR・音声認識） | 予定 |
| L4 | 投稿価値の自動評価 | 予定 |
| L5 | ハイライト自動編集 | 予定 |
| L6 | プライバシー・精密分割 | 計画中 |

## ライセンス

[MIT License](LICENSE)
