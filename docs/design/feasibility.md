# GUI Phase 0 フィージビリティ検証

実装着手前に以下の技術的不確定要素を検証し、結果を本ファイルに記録する。

## Phase 0 の位置付け (2026-04-20 更新)

[#450 GUI フレームワーク決定](https://github.com/Idios/kobutachan-allaganeye/issues/450) は **Phase 0 の結果をもって最終判断**する運用に変更した。調査 ([2026-04-20 コメント](https://github.com/Idios/kobutachan-allaganeye/issues/450)) で以下が判明した:

- **Electron** と **Tauri** のいずれでも MKV コンテナを `<video>` タグで直接再生することは Chromium のポリシーにより不可 (両者とも `video/x-matroska` をデコーダに渡さない)。回避策は ffmpeg `-c copy` で fragmented MP4 へ remux する ingest 処理。
- **Tauri** には以下の blocker を確認済み:
  - [tauri#6375](https://github.com/tauri-apps/tauri/issues/6375): `convertFileSrc` / `asset://` が 3.5 GiB 超のファイル seek でクラッシュ。OBS 2h 録画 (30-80 GB) に直撃。回避には Rust 側で Range 対応の HTTP サーバ (axum / rocket_seek_stream) を自前実装する必要あり。
  - [tauri#5022](https://github.com/tauri-apps/tauri/issues/5022): PyInstaller でビルドした sidecar の stdout がプロセス終了時まで一括出力される。detecting 画面のライブログに影響。`PYTHONUNBUFFERED=1` + `sys.stdout.reconfigure(line_buffering=True)` で回避可能だが要検証。
- **Electron** は [`protocol.handle`](https://www.electronjs.org/docs/latest/api/protocol) で 206 Partial Content を扱うパターンが成熟しており、長尺ファイルの seek は標準機能で対応可能。

このため Phase 0 では **Electron と Tauri の両方で最小プロトタイプを構築し F1-F5 を計測**、結果比較で #450 を確定する。

## 検証対象フレームワーク

| 候補 | 担当セクション | 備考 |
|---|---|---|
| Electron + React + TypeScript | 各 F 項目「Electron」 | handoff bundle jsx の 1:1 移植が容易 |
| Tauri + React + TypeScript | 各 F 項目「Tauri」 | 配布サイズ ~10 MB、ただし #6375 の回避実装が必要 |

## サンプル動画

`ALLAGANEYE_SAMPLE_VIDEO_DIR` 環境変数に設定された OBS 録画を使う (既定: `E:/royalstraightflesh/videos`)。

- **F1/F3 主計測**: 2:50:28 の長尺 MKV (30+ GB) を少なくとも 1 本
- **F2 計測補助**: 30-60 分程度の MKV を補助的に使用してよい (長尺での seek 回数を抑えるため)

## 検証項目

### F1: MKV 再生 (remux 前提)

- **目的**: `ffmpeg -c copy` で fragmented MP4 に remux した出力を両 FW で安定再生できるか、および remux に要する時間が許容範囲内か
- **手順**:
  1. 2h+ MKV をサンプルに `ffmpeg -i <in.mkv> -c copy -movflags +frag_keyframe+empty_moov <out.mp4>` を実行し所要時間を計測 (目標: 2h 録画で 60s 以内)
  2. Electron: 生成 MP4 を `<video>` に `file://` で読み込み、再生・一時停止・シークを確認
  3. Tauri: 同 MP4 を WebView2 の `<video>` に読み込み、再生・一時停止・シークを確認 (ただし F3 の blocker 検証を兼ねる)
  4. NG の場合、元 MKV をそのまま `<video>` に渡したときの挙動も記録
- **結果 (Electron)**: [ ] 検証待ち
- **結果 (Tauri)**: [ ] 検証待ち

### F2: フレーム精度シーク

- **目的**: 60 fps 録画で 1 フレーム単位シークが実用速度 (目標 200 ms 以内) で可能か
- **手順**:
  1. サンプル MP4 (F1 の remux 出力) で `currentTime` を 1/60s (~16.7ms) 単位で変更
  2. `requestVideoFrameCallback` によるフレーム確定までの時間を 100 サンプル計測し p50/p95 を記録
  3. Electron / Tauri それぞれで計測
  4. 代替案: ffmpeg でのサムネイル抽出キャッシュ (`~/.allaganeye/cache/<hash>/thumbs/*.webp`) に切り替え可能か確認
- **結果 (Electron)**: [ ] 検証待ち
- **結果 (Tauri)**: [ ] 検証待ち

### F3: 長時間ファイルの seek 耐性

- **目的**: 2h+ ファイルで seek が破綻 (バッファロード失敗、メモリリーク、UI フリーズ) しないか
- **手順**:
  1. Electron: `protocol.handle()` で 206 Partial Content に対応したハンドラを実装、ランダム seek 100 回連続実行
  2. Tauri: `convertFileSrc` (= `asset://`) を直接使う場合 ([tauri#6375](https://github.com/tauri-apps/tauri/issues/6375)) と、axum などで Range 対応 HTTP サーバを Rust 側に立てる場合の両方を試す
  3. メモリ使用量 (Task Manager)、フレーム落ちの有無を記録
- **結果 (Electron)**: [ ] 検証待ち
- **結果 (Tauri)**: [ ] 検証待ち

### F4: 代替案のフィージビリティ (F1-F3 のいずれかが NG の場合)

- **目的**: low-res proxy ファイル (480p h264) の事前生成で UX を成立させられるか
- **手順**:
  1. `allaganeye detect` 完了時に proxy を並行生成するフローを試作
  2. proxy 生成時間を計測 (2h 録画で 5 分以内が目標)
  3. 書き出し時は元動画を使用する分岐を確認
- **結果**: [ ] 検証待ち (F1-F3 が両 FW いずれかで OK なら不要)

### F5: ffmpeg sidecar / subprocess の同梱配布

- **目的**: L2b (#106) インストーラ形式と整合して ffmpeg バイナリを同梱できるか、および Python CLI のストリーミング呼び出しが成立するか
- **手順**:
  1. Electron: `electron-builder` の `extraResources` で `ffmpeg.exe` を同梱、`child_process.spawn` で `allaganeye` CLI の stdout を行単位で受信できるか確認
  2. Tauri: `tauri.conf.json` の `externalBin` で `ffmpeg.exe` を同梱、`Command.sidecar().spawn()` で `allaganeye` CLI の stdout が行単位で流れるか確認 ([tauri#5022](https://github.com/tauri-apps/tauri/issues/5022) 回避策 `PYTHONUNBUFFERED=1` + `sys.stdout.reconfigure(line_buffering=True)` 込み)
  3. Windows Defender SmartScreen の警告レベルを両 FW で確認 (コードサイニング未実施時)
- **結果 (Electron)**: [ ] 検証待ち
- **結果 (Tauri)**: [ ] 検証待ち

## 検証結果の記録フォーマット

各項目が完了したら以下のテンプレで追記する:

```markdown
### F1: MKV 再生 (Electron, 済)
- **検証日**: YYYY-MM-DD
- **検証環境**: OS / framework version / sample video
- **結果**: OK / NG
- **実測値**: (seek 時間、メモリ等)
- **判断**: 実装続行 / 代替案採用
- **記録担当**: (session-id)
```

## フレームワーク選定基準

Phase 0 完了後、以下を総合して #450 を確定する:

| 観点 | 重み | 判断基準 |
|---|---|---|
| F3 seek 耐性 (長尺 OBS 録画) | 最重要 | 両 FW とも OK なら他の観点で比較、片方だけ OK ならそちらを採用 |
| F2 フレーム精度 | 重要 | 目標 200ms 以内、超える場合 F4 代替案の成立を確認 |
| F5 sidecar ストリーミング | 重要 | detecting 画面のライブログ成立が必須条件 |
| 配布サイズ | 中 | Tauri が優位 (~90 MB vs Electron ~200 MB)、ただし技術制約が先 |
| 実装コスト | 中 | handoff jsx の流用度、Rust 学習の要否 |

## Phase 0 合格基準

- [ ] 採用候補となる FW が 1 つ以上決定 (F1-F3 が OK または F4 で代替成立)
- [ ] F2 OK (目標 200ms 以内) または F4 代替案で 1 フレームシーク成立
- [ ] F3 OK (2h seek 耐性あり) — 採用候補 FW 側
- [ ] F5 OK (インストーラ同梱 + sidecar ストリーミング両立) — 採用候補 FW 側
- [ ] #450 に最終判断をコメントし issue をクローズ

全項目合格で Phase 1 (データ層) に進む。両 FW とも NG かつ F4 でも成立しない場合は #450 で代替候補 (PySide6 / Textual 等) を再検討、または L2 スコープ見直しを #105 のコメントで提起する。
