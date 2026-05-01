# L2 E2E Checklist (v0.2.0 リリース品質ゲート)

> **Status**: v0.2.0 リリース直前に Idios が手動実施
> **本 doc の用途**: 2 スコープ (GUI / installer) 合流後のリグレッション検出。`docs/release-process.md §94` v0.2.0 固有項目から本 doc を必須参照
> **CI 自動化方針**: 本 spec で **手動 checklist 主体** に確定。Playwright / Tauri mock driver の feasibility 検討は [#671](https://github.com/Idios/kobutachan-allaganeye/issues/671) で v0.3.0+ に follow-up

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
- 未設定なら `[参照...]` ボタンで個別動画を選択 (T1.3 操作の代替経路)

### 出力先

- screenshot: `logs/qa/v0.2.0/T<N>-step<M>-<label>.png`
- evidence log: `logs/qa/v0.2.0/T<N>-step<M>-<label>.log`

## §3 T1: 基本フロー (正常系)

### T1.1 Portable ZIP 展開

**操作:**

1. `allaganeye-v0.2.0-windows.zip` を任意のディレクトリに展開
2. 展開後ディレクトリに `allaganeye.bat` / `allaganeye-gui.exe` / `bin/ffmpeg.exe` などが揃っていることを確認

**Expected:**

- 同梱物の存在を visual で確認
- [#668](https://github.com/Idios/kobutachan-allaganeye/issues/668) 同梱物健全性チェックが PASS する状態 (T1.2 で起動時 check)

**Evidence:**

- screenshot: `logs/qa/v0.2.0/T1-step1-extracted.png` (展開後ディレクトリ)
- log: なし

### T1.2 GUI 起動

**操作:**

1. `allaganeye-gui.exe` をダブルクリックで起動

**Expected:**

- Tauri ウィンドウが開く (DropScreen 表示)
- [#668](https://github.com/Idios/kobutachan-allaganeye/issues/668) 健全性 check が PASS した状態でモーダル表示なし
- `logs/error-YYYYMMDD.log` にエラー記録なし

**Evidence:**

- screenshot: `logs/qa/v0.2.0/T1-step2-launched.png` (起動直後の DropScreen)
- log: `allaganeye-gui.exe` 起動直後の `logs/error-YYYYMMDD.log` を copy → `logs/qa/v0.2.0/T1-step2-startup.log`

### T1.3 サンプル動画 drop → detecting → complete

**操作:**

1. GUI ウィンドウに `$ALLAGANEYE_SAMPLE_VIDEO_DIR/2026-04-08 21-14-05.mkv` を drag & drop (または `[参照...]` ボタンで選択)

**Expected:**

- DropScreen → DetectingScreen に即時遷移
- フェーズバー (Detecting / Refining) が進行
- ライブログ panel に CLI stdout が行単位で stream
- 検知時間: ≤ 10 min (GPU mode、§5 パフォーマンス目安)
- 検知完了後 CompleteScreen に自動遷移
- 試合一覧に 9 件のカードが表示される

**Evidence:**

- screenshot: `logs/qa/v0.2.0/T1-step3-detecting.png`, `T1-step3-complete.png`
- log: CLI stdout 全文 + 検知時間記録 → `logs/qa/v0.2.0/T1-step3-detect.log`

### T1.4 preview で境界 ±5s 調整

**操作:**

1. CompleteScreen で 1 試合のカードを double-click
2. PreviewScreen に遷移
3. 開始 / 終了境界を ±5s 範囲で調整
4. `[適用]` ボタンで保存

**Expected:**

- PreviewScreen で動画が再生可能 (axum video server 経由)
- 境界調整後 `metadata.json` に変更が反映される
- `[元に戻す]` ボタンが **enabled 状態であることを visual で確認** (押下はしない、復元動作は本 step のスコープ外)

**Evidence:**

- screenshot: `logs/qa/v0.2.0/T1-step4-preview.png`, `T1-step4-applied.png`
- log: `metadata.json` の diff → `logs/qa/v0.2.0/T1-step4-metadata-diff.log`

### T1.5 export で 9 試合 MP4 書き出し

**操作:**

1. ExportScreen に遷移
2. `[全試合書き出し]` をクリック
3. 進捗が完了するまで待つ

**Expected:**

- 9 試合分の MP4 が `output/` 配下に生成
- export 時間: ≤ 3 min (copy mode、§5 パフォーマンス目安)
- ExportScreen 内 sub-label の text (`(NVENC)` / `(QSV)` / `(AMF)` / `libx264 (CPU)` のいずれか) を **visual 確認**、環境の GPU vendor と一致すること

**Evidence:**

- screenshot: `logs/qa/v0.2.0/T1-step5-exporting.png`, `T1-step5-done.png`
- log: ExportScreen 内部ログ + 出力 MP4 一覧 → `logs/qa/v0.2.0/T1-step5-export.log`

### T1.6 出力検証 (合計時間 ±1s)

**操作:**

1. 出力された 9 試合 MP4 の duration 合計を `ffprobe` + `awk` で取得:

   ```bash
   # 合計時間を計算 (ffprobe 出力を秒単位で sum)
   for f in output/*.mp4; do
     ffprobe -v error -show_entries format=duration -of csv=p=0 "$f"
   done | awk '{sum += $1} END {print sum}'
   ```

2. 元動画の試合領域 timestamp 合計を `metadata.json` から `jq` で抽出:

   ```bash
   jq '[.matches[] | .end - .start] | add' output/metadata.json
   ```

3. 1 と 2 の差分を計算し、絶対値が ≤ 1.0 であることを確認

**Expected:**

- 差分 ≤ 1s (合計時間ベース)

**Evidence:**

- log: `ffprobe` 結果 + 差分計算結果 → `logs/qa/v0.2.0/T1-step6-duration-check.log`

## §4 T2: エラーリカバリ

> **障害注入手段**: 本 spec で **(a) export 中に Tauri × ボタンで process kill** を採用 (再現性高、[#523](https://github.com/Idios/kobutachan-allaganeye/issues/523) と動作定義が連動)。別 (b) read-only path / (c) input 削除 は OS 依存で除外 (spec §4.3)
>
> **前提**: [#523](https://github.com/Idios/kobutachan-allaganeye/issues/523) (ffmpeg 中断と graceful kill) の実装が前提。**[#523](https://github.com/Idios/kobutachan-allaganeye/issues/523) 完了前は T2 を skip 可、ただし checklist 本体には記述しておく** (将来の T2 enable 時にすぐ実施可能)

### T2.1 障害注入: export 中に Tauri × ボタンで process kill

**操作:**

1. T1.5 と同じ手順で export を開始 (9 試合の書き出し)
2. **5 試合目以降の出力中** で Tauri ウィンドウの × ボタンをクリック
3. confirm dialog ([#523](https://github.com/Idios/kobutachan-allaganeye/issues/523) 実装) で `[OK]` を選択
4. アプリが graceful kill → 終了

**Expected:**

- confirm dialog が表示される
- `[OK]` で子 ffmpeg process が graceful kill (SIGTERM 相当)
- アプリがクラッシュなく終了 (Rust panic / JS error なし)

**Evidence:**

- screenshot: `logs/qa/v0.2.0/T2-step1-confirm-dialog.png`, `T2-step1-cancelled.png`
- log: `logs/error-YYYYMMDD.log` を copy → `logs/qa/v0.2.0/T2-step1-error.log` (panic / 例外なし確認)

### T2.2 完成 MP4 の保護

**操作:**

1. `output/` ディレクトリを開く
2. 既に書き出し完了済の MP4 (kill 直前まで完成していた試合) を確認

**Expected:**

- 完成済 MP4 (4-5 試合分相当) は破損なく残る
- kill 時に出力中だった 1 試合分の MP4 は incomplete または 0 byte の可能性あり (許容)
- 未着手の試合は `output/` に MP4 ファイルが存在しない

**Evidence:**

- log: `output/*.mp4` 一覧 + 各 MP4 の duration (`ffprobe`) → `logs/qa/v0.2.0/T2-step2-output-state.log`

### T2.3 失敗試合のエラー表示 UI 検証

**操作:**

1. アプリを再起動 (`allaganeye-gui.exe` 再実行)
2. 前回 metadata.json が自動 restore ([#574](https://github.com/Idios/kobutachan-allaganeye/issues/574) で実装予定、未実装なら手動で再 drop)
3. ExportScreen を確認

**Expected:**

- 前回 export の状態が CompleteScreen / ExportScreen に反映される ([#574](https://github.com/Idios/kobutachan-allaganeye/issues/574) 実装後)
- 失敗 / 未完了試合に notice / fallback マーカーが表示される ([#591](https://github.com/Idios/kobutachan-allaganeye/issues/591) fallback notice + 本 spec の error UI 拡張)
- ユーザーが失敗試合のみ再 export 可能

**Evidence:**

- screenshot: `logs/qa/v0.2.0/T2-step3-restored.png`, `T2-step3-error-ui.png`
- log: `logs/error-YYYYMMDD.log` の最新 + 再起動後の起動 log → `logs/qa/v0.2.0/T2-step3-restart.log`

### T2 skip 条件

- [#523](https://github.com/Idios/kobutachan-allaganeye/issues/523) 未マージ時は T2 全 step を skip し、checklist には「[#523](https://github.com/Idios/kobutachan-allaganeye/issues/523) マージ後に実施」と注記
- [#574](https://github.com/Idios/kobutachan-allaganeye/issues/574) 未マージ時は T2.3 expected の「自動 restore」を「手動 drop で代替」と注記

### T2 障害注入 (b) (c) を採用しない理由 (spec §4.3 抜粋)

- (b) read-only path: OS / FS 依存 (NTFS read-only attribute, Windows ACL) で再現性低
- (c) input 削除中: Windows FS lock により export 中の削除が拒否される可能性、再現困難

## §5 パフォーマンス目安

| 計測対象 | 目安 | 計測手段 |
| --- | --- | --- |
| 検知時間 (GPU mode) | ≤ 10 min | DetectingScreen の経過時間表示 + CLI verbose 出力 |
| 9 試合 export (copy mode) | ≤ 3 min | ExportScreen 進捗 + CLI verbose |
| GUI seek p95 | ≤ 200 ms | DevTools Performance タブで `<video>` element の `seeked` event 計測 |

### 計測の record

- 各値を `logs/qa/v0.2.0/perf-summary.log` に記載
- 目安超過時は **目安充足ラインまでパフォーマンス改善** または **目安を緩和する根拠を Idios 判断で記録**

## §6 成功基準

- [ ] T1.1-T1.6 全て expected 通過
- [ ] T2.1-T2.3 全て expected 通過 ([#523](https://github.com/Idios/kobutachan-allaganeye/issues/523) 未マージ時は skip 注記)
- [ ] §5 パフォーマンス目安 全項目を実測値で satisfy
- [ ] 9 試合 MP4 が全て `output/` に生成
- [ ] `logs/qa/v0.2.0/` 配下に screenshot + evidence log が保存される
- [ ] T1.6 合計時間差分 ≤ 1s

## §7 CI 自動化方針

### v0.2.0 方針 (本 spec で確定)

- **手動 checklist 主体** (本 doc) のみ
- CI 実行は対象外
- Idios 実機 (Windows + ALLAGANEYE_SAMPLE_VIDEO_DIR 設定済) で実施

### v0.3.0+ で feasibility 検討 (別 issue で deferred 追跡)

- **Playwright** (Tauri webview 対応): browser context で assertion 可、cross-platform 制約あり
- **Tauri mock driver** (公式提供): Phase 0 で feasibility 検証必要、frontend のみ vitest e2e に近い
- 詳細: [#671](https://github.com/Idios/kobutachan-allaganeye/issues/671) で v0.3.0+ に follow-up

## §8 References

- [`docs/release-process.md` §94 v0.2.0 (L2: GUI サポート + ゼロ環境構築配布) 固有項目](./release-process.md#v020-l2-gui-サポート--ゼロ環境構築配布-固有項目) — 本 doc を必須参照
- [`docs/l2-workflow.md` §実機検証 trigger 表](./l2-workflow.md) — 実機検証ルール
- [`docs/ui-architecture.md` §5 preview](./ui-architecture.md#5-各画面の-phase-state) — preview 画面の状態機械
- [`docs/axum-video-server.md`](./axum-video-server.md) — preview 画面の動画配信仕様 (T1.4 関連)
- [#668](https://github.com/Idios/kobutachan-allaganeye/issues/668) — Portable ZIP 同梱バイナリ健全性 (本 doc 前提)
- [#523](https://github.com/Idios/kobutachan-allaganeye/issues/523) — ffmpeg 実行中の安全な中断 (T2 障害注入 (a) の実装前提)
- [#574](https://github.com/Idios/kobutachan-allaganeye/issues/574) — 前回 metadata 自動再現 (T2.3 expected の前提)
- [#591](https://github.com/Idios/kobutachan-allaganeye/issues/591) — H.264 GPU encoder auto-select / fallback notice (T1.5 / T2.3 関連)
