# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- scorebar V2 で emblem 位置を 1080p 固定座標から動的検出に変更し、4K Game DVR 録画で試合境界が認識できない問題を改善 (#522)

## [0.1.1] - 2026-04-20

L1 (試合分割) の正式リリース版。2026-04-17 に `v0.1.0-preview` として公開後、品質向上を経て `v0.1.1` として正式リリース。verbose 出力の網羅的改善、GPU/CPU 検知精度の一致、進捗バー UX 修正、メタデータ拡充、運用ルール強化。

### Added

- verbose ヘッダに HW 情報 (CPU/GPU/Memory/Disk) を表示 (#377)
- verbose 出力に Pass 1/Pass 2/Scorebar/Splitting の elapsed time を表示 (#386, #387)
- verbose 出力に Filter drop 内訳を表示 (#388)
- verbose 出力に検知候補 metadata、resolved workers 数を表示 (#389)
- キャッシュヒット時にも verbose で検知パラメータを表示 (#380)
- Match 一覧に `[unknown]` マーカーを表示 (#382)
- metadata.json に `detection_params` / `detected_at` を記録 (#370)
- metadata.json の `gaps` 配列に raw 秒フィールドを追加 (#369)
- metadata.json の `output_file` パスを POSIX 区切りに正規化 (#371)
- コーデックに基づく GPU/CPU モード自動選択 (#334)
- 分割前にディスク空き容量をチェック (#338)
- `-V` / `--version` ショートフラグと verbose パイプライン統計 (#336, #337)
- verbose エラー詳細 (traceback + ffmpeg stderr) を出力 (#351)
- CLI 出力仕様マトリクス docs (`docs/output-spec.md`) を新設 (#405)
- 過去 PR audit レポート (`docs/audits/2026-04-19-pr-audit.md`) を追加 (#410)
- ロール定義にユーザー確認ルール / Memory 活用ガイダンスを追加 (#400)
- Director / Lead Engineer 行動規範 A/B/C を docs に明文化 (#399)
- PreToolUse hook で確認ゲートを実装 (#401)
- Quick Start に venv セットアップ手順を追記 (#364)
- 出力ファイル一覧に `.detection_cache.json` を追記 (#360)
- `--gpu` がデフォルト off の理由を README / CLI ヘルプに補足 (#332)

### Changed

- verbose 出力の `audio=on/off` を実態に合わせ `audio=frozen` に修正 (#384)
- verbose 出力の ffmpeg version 文字列を簡潔化 (`8.1` 等) (#383)
- verbose 出力の Total time 表示を全パス (cache hit + split 含む) に統一 (#381)
- `-q` モードで dry-run 通知の出力を抑制 (#418)
- CLI で `-q` / `-v` / `--gpu` / `--no-gpu` 同時指定を排他エラー化 (#419)

### Fixed

- 進捗バー (Detecting/Refining/Scorebar) の上書き表示問題 (#368, #393)
- Pass 2 中の進捗無音問題 (#366)
- 進捗バー ETA ラベル明確化、split 出力表示改善 (#328, #329, #331)
- GPU mode で CPU と Match 境界が一致しない問題 (#392, sample grid 整列)
- Pass 1 統計の verbose 表示漏れ (#386)
- Pass 1 borderline frame 対策 (A3/A4 hysteresis) (#361)
- GPU chunk progress をリアルタイムで進捗バーに反映 (#333)
- 凍結中の音声スキャンをデフォルトで無効化 (#327)
- `scan_fanfare_hits` の FileNotFoundError を `VideoProcessingError` でラップ (#350)
- CLI エラー表示を output matrix v2 (19a/19b/19c) に整合 (#428)

### Internal

- テスト網羅性向上 (オプション組合せ網羅、GPU chunk_timestamps parametric、system_info Linux/Darwin パーサ実解析、metadata gaps shape、Pass 2 進捗、B グループカバレッジ等)
- `setup-session` の開発ブランチ参照とパスを動的化
