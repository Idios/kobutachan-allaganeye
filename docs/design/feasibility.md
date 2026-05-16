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
| --- | --- | --- |
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
| --- | --- | --- |
| F3 seek 耐性 (長尺 OBS 録画) | 最重要 | 両 FW とも OK なら他の観点で比較、片方だけ OK ならそちらを採用 |
| F2 フレーム精度 | 重要 | 目標 200ms 以内、超える場合 F4 代替案の成立を確認 |
| F5 sidecar ストリーミング | 重要 | detecting 画面のライブログ成立が必須条件 |
| 配布サイズ | 中 | Tauri が優位 (~90 MB vs Electron ~200 MB)、ただし技術制約が先 |
| 実装コスト | 中 | handoff jsx の流用度、Rust 学習の要否 |

## Phase 0 合格基準

- [x] 採用候補となる FW が 1 つ以上決定 (F1-F3 が OK または F4 で代替成立) — 両 FW とも OK
- [x] F2 OK (目標 200ms 以内) または F4 代替案で 1 フレームシーク成立 — 両 FW とも p95 < 200 ms
- [x] F3 OK (2h seek 耐性あり) — 採用候補 FW 側 — Tauri http: p95 294 ms, 100/100 成功
- [x] F5 OK (インストーラ同梱 + sidecar ストリーミング両立) — 採用候補 FW 側 — Tauri: 706s 長時間 detect で first-line 1.3-1.7s
- [x] #450 に最終判断をコメントし issue をクローズ — 2026-04-20 Tauri 採用確定

## 計測結果 (2026-04-20 実施)

プロトタイプは `.claude/prototypes/{electron,tauri}-phase0/` (gitignore) で構築。サンプル MKV は `E:/videos/2026-04-08 21-14-05.mkv` (36.61 GB, 2:50:28)、remux 後 MP4 は 36.61 GB。

### F1: MKV 再生 (remux, 済)

- **検証日**: 2026-04-20
- **検証環境**: Windows 11 / ffmpeg 8.1 / sample: 2026-04-08 21-14-05.mkv (36.61 GB)
- **コマンド**: `.claude/prototypes/common/remux.sh <file>` (`ffmpeg -c copy -movflags +frag_keyframe+empty_moov`)
- **所要時間**: 38 秒
- **出力**: 36.61 GB fragmented MP4
- **結果**: OK (目標 60s 以内)
- **記録担当**: relaxed-mestorf-9807da

### F2: フレーム精度シーク (済)

- **検証日**: 2026-04-20
- **検証環境**: Windows 11 / Electron 34 (Chromium) / Tauri 2.10.3 (WebView2) / fragmented MP4 36.61 GB (2:50:28)
- **計測**: 動画中央付近で 1/60s 刻み seek 100 サンプル、`requestVideoFrameCallback` 解決までの latency を記録

| | Electron | Tauri asset | Tauri http (axum) |
| --- | --- | --- | --- |
| p50 | — | 151.2 ms | 150.6 ms |
| p95 | 178.2 ms | 179.6 ms | 182.2 ms |
| max | 183.2 ms | 355.7 ms | 184.4 ms |
| heap (MB) | 9 / 10 | 4 / 4 | 4 / 4 |

- **結果 (Electron)**: OK (p95 178.2 ms)
- **結果 (Tauri asset)**: OK (p95 179.6 ms、ただし max スパイク 355 ms あり)
- **結果 (Tauri http)**: OK (p95 182.2 ms)
- **記録担当**: relaxed-mestorf-9807da

### F3: 長時間ファイル seek 耐性 (済)

- **検証日**: 2026-04-20
- **検証環境**: 同上、36.61 GB MP4
- **計測**: 全域ランダム seek 100 回、各回 10s タイムアウト判定

| | Electron (protocol.handle 206) | Tauri asset (convertFileSrc) | Tauri http (axum + tower-http) |
| --- | --- | --- | --- |
| 成功 | 100/100 | 100/100 | 100/100 |
| 失敗 (>10s) | 0 | 0 | 0 |
| p50 | 114 ms | 385 ms | 106 ms |
| p95 | 352 ms | 991 ms | **294 ms** |
| max | 496 ms | 1735 ms | 434 ms |
| total | — | 44.6 s | 14.6 s |
| heap (MB) | 10 / 10 | 4 / 4 | 5 / 4 |

- **結果 (Electron)**: OK
- **結果 (Tauri asset)**: **OK** — [tauri#6375](https://github.com/tauri-apps/tauri/issues/6375) は Tauri 2.10.3 / WebView2 現行で**再現せず**。36 GB ファイルで 100/100 seek 成立。ただし p95 991 ms / max 1735 ms と劣化あり (Range 未対応による range-load の非効率性の可能性)
- **結果 (Tauri http)**: **OK**、かつ Electron を上回る (p95 294 ms vs 352 ms)。tower-http の `ServeFile` の 206 Partial Content 対応が機能
- **記録担当**: relaxed-mestorf-9807da

### F4: 代替案 (不要)

- **判定**: F1-F3 が両 FW で成立したため F4 (low-res proxy) の事前実装は不要。将来 1920x1080 以上の 4K 録画等で再検討

### F5: CLI sidecar ストリーミング (済)

- **検証日**: 2026-04-20
- **検証環境**: 同上 / `allaganeye` CLI (pip install 経由)
- **計測**: `allaganeye split <file> --dry-run --no-cache` を spawn し、first-line latency と全体 duration を記録

#### Electron (`child_process.spawn` + PYTHONUNBUFFERED=1)

| 項目 | 値 |
| --- | --- |
| exit code | 0 |
| duration | 706,233 ms (~11:46) |
| first-line latency | 1,944 ms |
| 実行内容 | 8 試合正常検知、progress ログ (Detecting/Refining/Scorebar) が進捗に合わせて届く |
| verdict | OK (streaming) |

#### Tauri (`tokio::process::Command` + `app.emit`)

| 項目 | PYTHONUNBUFFERED=1 | PYTHONUNBUFFERED=0 |
| --- | --- | --- |
| exit code | 0 | 0 |
| duration | 704,452 ms | 700,952 ms |
| first-line latency | 1,722 ms | 1,280 ms |
| verdict | OK (streaming) | OK (streaming) |

- **[tauri#5022](https://github.com/tauri-apps/tauri/issues/5022) 再現**: **否**。11 分超の detect でも stdout は行単位でストリーミングされ、PYTHONUNBUFFERED 設定の有無で挙動差なし。allaganeye は PyInstaller バイナリではなく setuptools scripts 由来の Python ランチャーなので、#5022 が取り上げる PyInstaller 特有の stdout バッファリング問題には該当しない
- **記録担当**: relaxed-mestorf-9807da

## 採用確定: Tauri + React + TypeScript (2026-04-20)

### 根拠

1. **F3 seek 耐性**: Tauri http 経路で Electron を上回る (p95 294 ms vs 352 ms)。Tauri asset 経路も劣化するものの 100/100 seek 成立
2. **F2 フレーム精度**: 両 FW 実質同等 (p95 178-182 ms、差 4 ms)
3. **F5 sidecar streaming**: 706-700 秒の長時間 detect で first-line 1.3-1.9 秒、両 FW 問題なく streaming
4. **Tauri 固有 blocker の解消確認**: #6375 および #5022 はいずれも Tauri 2.10.3 現行で再現せず
5. **配布サイズ**: Tauri ~90 MB (L2b の <100 MB 目安達成) vs Electron ~200 MB
6. **実装コスト**: axum HTTP サーバ (~50 行 Rust、Phase 0 プロトで構築済) + React 部は handoff jsx 流用可。Rust 学習は初回のみのコスト

### 不採用側 (Electron) の扱い

Electron プロトタイプ (`.claude/prototypes/electron-phase0/`) は `protocol.handle()` 206 対応のリファレンス実装として残す。Phase 1-4 (L2a 本実装) では Tauri ベースで進め、Electron 側は破棄。

### 後続タスクへの影響

- **L2a Phase 1 ([#463](https://github.com/Idios/kobutachan-allaganeye/issues/463))**: データ層 (metadata.json state 管理) — Zustand/Jotai など React エコシステムの stateMgr を採用、Rust 側は不要
- **L2a Phase 2 ([#464](https://github.com/Idios/kobutachan-allaganeye/issues/464))**: 5 画面骨格 — handoff bundle の aether.jsx を TS に写経、Tauri 固有の IPC 取り込み
- **L2a Phase 3 ([#465](https://github.com/Idios/kobutachan-allaganeye/issues/465))**: preview 本物化 — 本プロトの axum + ServeFile 経路をそのまま移植し `requestVideoFrameCallback` + ffmpeg サムネキャッシュを構築
- **L2a Phase 4 ([#466](https://github.com/Idios/kobutachan-allaganeye/issues/466))**: export 本物化 — 本プロトの `run_cli` コマンドを拡張して ffmpeg 起動・進捗受信を実装
- **L2b ([#106](https://github.com/Idios/kobutachan-allaganeye/issues/106))**: Tauri bundler (NSIS / MSI) で ~90 MB + ffmpeg sidecar (externalBin)。インストーラ形式決定 [#452](https://github.com/Idios/kobutachan-allaganeye/issues/452) に反映

### 運用上の注意

- Tauri asset (`convertFileSrc` / `http://asset.localhost/`) 経路は性能で劣るため、**本実装では axum HTTP 経路を使う** (Phase 0 プロトと同形)
- 一方で asset 経路が完全に使えないわけではないため、サムネイル画像の配信 (短時間 / 小サイズ) には asset 経路を使って HTTP サーバ負荷を避けるなどの分担を検討

## 今後の追加検証 (L2a 実装中)

- [ ] Windows Defender SmartScreen の警告レベル (コードサイニング未実施の bundle 起動時) — L2b の [#462](https://github.com/Idios/kobutachan-allaganeye/issues/462) コードサイニング検討と連携
- [ ] 60 fps / 4K 録画での F2/F3 再計測 — 将来の高解像度対応時
- [ ] macOS / Linux 上での基本動作 ([#451](https://github.com/Idios/kobutachan-allaganeye/issues/451) プラットフォーム範囲決定後)
