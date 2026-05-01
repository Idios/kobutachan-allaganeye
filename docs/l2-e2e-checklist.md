# L2 E2E Checklist (v0.2.0 リリース品質ゲート)

> **Status**: v0.2.0 リリース直前に Idios が手動実施
> **本 doc の用途**: 2 スコープ (GUI / installer) 合流後のリグレッション検出。`docs/release-process.md §94` v0.2.0 固有項目から本 doc を必須参照
> **CI 自動化方針**: 本 spec で **手動 checklist 主体** に確定。Playwright / Tauri mock driver の feasibility 検討は別 issue (本 PR の続作業で起票、起票後 §7 に番号 back-fill 予定) で v0.3.0+ に follow-up

## §1 Overview

### 目的

L2 (v0.2.0) の 2 スコープ (`l2a-gui` / `l2b-installer`) が合流したリリース成果物 (Portable ZIP) で、ユーザーが体験する E2E フロー (動画 drop → detect → preview 編集 → export) のリグレッションを手動検出する。

### 位置付け

- `docs/release-process.md §94 v0.2.0 (L2: GUI サポート + ゼロ環境構築配布) 固有項目` のチェックリストから本 doc が必須参照される
- 既存 §97 Portable ZIP smoke test を T1 (§3 で定義) に置換 (集約)
- 自動化は v0.2.0 範囲外、別 issue で deferred

### 成功条件

- T1 (基本フロー): 全 step expected 通過
- T2 (エラーリカバリ): 全 step expected 通過
- パフォーマンス目安 (§5 で定義) を満たす
- screenshot + evidence log が `logs/qa/v0.2.0/` 配下に保存

## §2 前提環境

| 項目 | 値 |
| --- | --- |
| OS | Windows 10/11 |
| サンプル動画 | `$ALLAGANEYE_SAMPLE_VIDEO_DIR/2026-04-08 21-14-05.mkv` (9 試合含む録画を default 推奨) |
| Portable ZIP | `allaganeye-v0.2.0-windows.zip` 展開済 |
| 同梱バイナリ健全性 | [#668](https://github.com/Idios/kobutachan-allaganeye/issues/668) のチェックが PASS していること (前提) |
| ffmpeg | 同梱 BtbN LGPL ビルドを使用、PATH に追加されていなくてもよい |

### 環境 variable

- `ALLAGANEYE_SAMPLE_VIDEO_DIR`: ローカル録画ディレクトリの絶対 path
- 起動時に未設定なら動画 drop step (§3 T1.3 で定義) を skip し、Idios 環境でのみ実施

### 出力先

- screenshot: `logs/qa/v0.2.0/T<N>-step<M>-<label>.png`
- evidence log: `logs/qa/v0.2.0/T<N>-step<M>-<label>.log`
