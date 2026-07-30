# CLI コマンド仕様

> **スコープ**: 本 doc は CLI (`allaganeye` サブコマンド) の構文を扱う。GUI (`allaganeye-gui.exe`) と CLI の起動経路・全体像は [system-architecture.md](system-architecture.md) を参照。

CLI コマンド・引数・オプションの**構文**をまとめる。各オプション組み合わせごとの**出力側**の期待仕様は [`docs/output-spec.md`](output-spec.md) に分離して定義されており、新規 CLI オプション追加時はそちらのマトリクスも更新する (#405)。

## 前提条件

| 要件 | 説明 |
| --- | --- |
| ffmpeg / ffprobe 4.1+ | 以下の順序で自動検索: (1) PATH (`shutil.which`) (2) `ALLAGANEYE_FFMPEG` 環境変数で指定したディレクトリ (3) OS 別既知パス（Windows: winget `Gyan.FFmpeg`、macOS: Homebrew）。配布版・dev 環境ともに LGPLv3 版 (BtbN FFmpeg-Builds `win64-lgpl-shared`) の使用を推奨 (#508)。winget `Gyan.FFmpeg` は GPL 版で、後方互換 fallback として自動検索される |

## グローバルオプション

| オプション | 説明 |
| --- | --- |
| `--version` | バージョン表示 |
| `--help` | ヘルプ表示 |

## split コマンド

試合単位で動画を分割する。`detect` との関係:

- **`allaganeye split <video>`**: 従来通り、検知 → 分割を一気通貫で実行 (後方互換)
- **`allaganeye split --from-metadata <metadata.json>`**: 既存の `metadata.json` を読み込んで分割のみ実行 (#463)
- **`allaganeye detect <video>`** (別コマンド、後述): 検知のみ実行し `metadata.json` を出力

GUI (L2a) は `detect` で観測し、ユーザー編集後に `split --from-metadata` を呼ぶ 2 段階フローを採用。

### 構文

```bash
allaganeye split <video_path> [OPTIONS]
allaganeye split --from-metadata <metadata.json> [OPTIONS]
```

### 引数

| 引数 | 必須 | 説明 |
| --- | --- | --- |
| `video_path` | 下記いずれか | 入力動画ファイルのパス（MP4/MKV/AVI/MOV）。`--from-metadata` と排他 |
| `--from-metadata` | 下記いずれか | `allaganeye detect` が出力した `metadata.json` のパス。指定時は検知をスキップし分割のみ実行 (#463)。`video_path` / `--dry-run` と排他 |

### オプション

| オプション | デフォルト | 説明 |
| --- | --- | --- |
| `-o`, `--output-dir` | `./output` | 出力ディレクトリ |
| `--sample-interval` | `1.0` | フレームサンプリング間隔（秒） |
| `--blackout-threshold` | `15.0` | 暗転検知の輝度閾値（0-255） |
| `--min-match-duration` | `300.0` | 最小試合時間（秒）。これより短いセグメントは無視 |
| `--min-blackout-duration` | `3.0` | 最小暗転時間（秒）。これより短い暗転は無視 |
| `--workers` | auto | 検知の並列ワーカー数。auto の解決値は実装の cap に従う (正: `allaganeye/video/detector.py` の `_resolve_workers` docstring) |
| `--gpu` | `false` | GPU アクセラレーション検知を強制（チャンク並列デコード）。利用不可時は CPU フォールバック。**`--no-gpu` と同時指定は排他エラー (exit 5) (#419)** |
| `--no-gpu` | `false` | GPU を無効化し CPU 検知を強制する。**`--gpu` と同時指定は排他エラー (exit 5) (#419)** |
| `--gpu-vendor` | `auto` | 使用する GPU vendor を明示指定 (#546 / #553 / #550 / #582)。値: `auto` / `nvidia` / `amd` / `intel`。**3 vendor すべて実装済み** (`nvidia`=cuvid #546 / `amd`=d3d11va+hwdownload #553 / `intel`=QSV+hwdownload #550 h264/hevc/av1 + #582 vp9)。probe に無い vendor を要求すると exit 5。default は probe 結果から `_VENDOR_PREFERENCE` (nvidia > amd > intel) 順で選ぶ |
| `--no-cache` | `false` | キャッシュされた検知結果を無視して再検知する |
| `--keep-trailing` | `false` | default は試合後 trailing を `post_match: true` フラグ化して metadata に保持し、default split (MP4) から除外する (#805 段階2 で不可逆削除を廃止)。本フラグ指定時は flagging を skip し、trailing を通常 match として MP4 分割・保持する (#797 probe 無効化)。段階2 で `post_match_trailing_dropped` warning は emit されなくなった (flag が代替) |
| `--no-audio` | `false` | 音声ベースの試合境界昇格（Fanfare スキャン）を無効化する。**現在は音声モジュールが凍結中（#327）のため、本フラグの値に関わらずスキャンは常にスキップされる。verbose 出力では `audio=frozen` と表示される (#384)** |
| `--masked` | `false` | チャット欄マスク画像が全画面に合成された録画向け。mask のない領域を自動検出して再検知する。暗転が一部見つかる場合でも本フラグ指定でこの経路を強制する。**`--vtuber` と同時指定は排他エラー (exit 5)** |
| `--dry-run` | `false` | 検知のみ実行し分割しない（検知結果はキャッシュに保存される） |
| `-v`, `--verbose` | `false` | 詳細出力（メタデータ詳細、gap 情報）。**`-q` と同時指定は排他エラー (exit 5) (#419)** |
| `-q`, `--quiet` | `false` | 進捗出力を抑制（出力ファイル一覧のみ）。**`-v` と同時指定は排他エラー (exit 5) (#419)** |

`--gpu` / `--no-gpu` のいずれも指定しない場合はコーデックから自動選択される (H.264/HEVC/AV1/VP9 → GPU、それ以外 → CPU) (#414)。ハードウェア要件は [`docs/video-processing.md`](video-processing.md) §「コーデック + vendor 自動選択（#334, #414, #546, #550）」を参照。

### 出力

- `output/match_001.mp4`, `match_002.mp4`, ...
- `output/metadata.json` — 分割結果（機械可読）
- `output/.detection_cache.json` — 検知結果キャッシュ（同一ソース・同一パラメータの再実行を高速化。`--no-cache` で無視）

### verbose (`-v`) 出力例

```text
allaganeye 0.1.1 (ffmpeg 8.1, Python 3.12.10, Windows 11)
  CPU: AMD Ryzen 9 9950X3D (16C/32T)
  GPU: NVIDIA GeForce RTX 5090 (32GB VRAM)
  Memory: 61.6 GB
  Disk: 1359.5 / 3726.0 GB free on E:
Probing: recording.mkv
  Duration: 10228.7s, Resolution: 1920x1080, FPS: 60.00, Codec: h264
Detecting match boundaries (interval=3.0s, threshold=15.0, workers=auto (24), min_match=300.0s, min_blackout=3.0s, audio=frozen, vtuber=off, masked=off)
Detecting  #################################### 100%
Refining   #################################### 100%
Scorebar   #################################### 100%
Splitting  #################################### 100%
...
```

#### マルチ CPU / マルチ GPU 環境の出力例 (#435 / #436)

複数 CPU ソケットや iGPU + dGPU 構成の場合、`CPU:` / `GPU:` 行が以下の形式に切り替わる。シングル CPU + シングル GPU では上の単行表示が維持される。

```text
allaganeye 0.2.x (ffmpeg 8.1, Python 3.12.10, Windows 11)
  CPU: AMD Ryzen 9 9950X3D 16-Core Processor (16C/32T)
  GPU:
    - NVIDIA GeForce RTX 5090 (32GB VRAM)
    - AMD Radeon(TM) Graphics
  Memory: 61.6 GB
  Disk: 1359.5 / 3726.0 GB free on E:
```

- `CPU:` 同モデル N ソケット時: `AMD EPYC 7763 64-Core Processor x2 (128C/256T)` (`xN` 表記、コア数は全 CPU 合計)
- `CPU:` 異モデル混在時: `Intel Xeon Gold 6154 + AMD EPYC 7763 (92C/128T)` (` + ` 連結)
- `GPU:` 2 つ以上検出時: `GPU:` ヘッダ行 + `- <name>` の bullet 列挙 (4 スペース インデント、上の出力例参照)。NVIDIA は `(NGB VRAM)` が付与され、iGPU と dGPU が NVIDIA 名 ベースで重複排除される

ヘッダ各行の意味:

| 行 | 意味 | 取得失敗時 |
| --- | --- | --- |
| 1 行目 | allaganeye / ffmpeg / Python / OS のバージョン | ffmpeg は `(unknown)` にフォールバック |
| `CPU:` | CPU モデル + `(物理Core/論理Thread)` (#377)。マルチソケットは同モデル `xN` / 異モデル ` + ` 連結、コア数は全 CPU 合計 (#435) | `(unavailable)` / `(unknown CPU) (NT)` 等 |
| `GPU:` | GPU モデル (+ NVIDIA のみ VRAM) (#377)。2 つ以上検出時は `GPU:` ヘッダ + bullet 列挙の multi-line block (#436) | `(unavailable)` |
| `Memory:` | 物理メモリ総量 (#377) | `(unavailable)` |
| `Disk:` | 出力先ディスクの空き / 総量 (#377) | `(unavailable)` |

HW 情報は全て best-effort。取得失敗しても `(unavailable)` を返すのみで検知は継続する。`psutil` 等の重量依存は使わず、OS ネイティブツール (`wmic` / `nvidia-smi` / `/proc` / `sysctl`) を subprocess で呼び出す。

### verbose + キャッシュヒット時の出力 (#380)

`.detection_cache.json` がヒットすると Pass 1 / Pass 2 は実行されないため、検知フェーズの summary や progress bar は出力されない。代わりに verbose モードではキャッシュに記録された検知パラメータを表示し、troubleshoot に必要な context を保つ:

```text
allaganeye 0.1.1 (ffmpeg 8.1, Python 3.12.10, Windows 11)
  CPU: AMD Ryzen 9 9950X3D (16C/32T)
  GPU: NVIDIA GeForce RTX 5090 (32GB VRAM)
  Memory: 61.6 GB
  Disk: 1359.5 / 3726.0 GB free on E:
Probing: recording.mkv
  Duration: 10228.7s, Resolution: 1920x1080, FPS: 60.00, Codec: h264
Cache hit: detection params from .detection_cache.json
  sample_interval=3.0s, threshold=15.0, min_match=300.0s, min_blackout=3.0s, audio=frozen, vtuber=off, masked=off, keep_trailing=off, masked_fallback=off, region=full_frame
Detected 8 match(es) in recording.mkv (2:50:28) (cached)
  Match 1:   00:00 -   15:17  (15m17s)  [unknown]
  ...
Splitting  #################################### 100%
  Splitting: 8 matches, 0m05s
Total: 0m07s
```

`audio` 表示は cache-miss 側の Detecting summary と同じヘルパ (`_audio_status_str`) を経由するため、`AUDIO_FROZEN` 状態を反映する (#384)。masked fallback 採用 run (masked=on または masked_fallback=on) のみ、パラメータ行の `masked_fallback` の直後 (`region=` の前) に `masked_algo=N` トークンが挿入される (N は `_MASKED_ALGO_VERSION`、#822)。

#### キャッシュ再読み込み失敗時のフォールバック

`_load_cache_hit` 検証通過後でも race condition / 破損 / 権限変更等で helper 側の読み直しが失敗しうる。その場合はヘッダ (`Cache hit: detection params from ...`) を常に emit した上で、失敗理由を `(unavailable: ...)` 行で通知する。split 本体は妨げない (helper は raise しない):

| シナリオ | 出力 |
| --- | --- |
| JSON parse 失敗 (破損) | `(unavailable: cache file is not valid JSON)` |
| `params` キー欠落 / `params` が dict でない / 空 dict | `(unavailable: cache file has no params section)` |
| I/O エラー (削除・権限・ディスク障害) | `(unavailable: cache file unreadable - <ExceptionClassName>)` |
| 個別パラメータキーの欠落 (旧バージョンキャッシュ等) | 該当トークンのみ `?` にフォールバック (`threshold=?` 等)、他は表示 |

出力例 (JSON 破損ケース):

```text
Cache hit: detection params from .detection_cache.json
  (unavailable: cache file is not valid JSON)
Detected 8 match(es) in recording.mkv (2:50:28) (cached)
  ...
```

verbose モードの UX 目的 (= 情報取得) を優先する設計。silent return だと「verbose が効いていない」と誤認する恐れがあるため、ヘッダは常時 emit する (#380 review)。

### 検知フェーズの進捗バー (#368 / #393)

検知パイプラインは 3 フェーズに分かれ、それぞれ独立した進捗バーを 1 行ずつ表示する:

| バー | フェーズ | 進捗単位 |
| --- | --- | --- |
| `Detecting` | Pass 1 の全区間粗スキャン | 推定サンプル数 |
| `Refining` | Pass 2 の暗転候補精密計測 | プローブ件数 |
| `Scorebar` | 暗転の in_match / non_fl 分類 | 対象領域数 |
| `Splitting` | ffmpeg `-c copy` による無劣化分割 | 出力マッチ数 |

各バーは前のバーが 100% 到達 → 改行して確定 → 次のバーが新しい行で開始する。過去のバーが `\r` で上書きされたり、単位切替で 100% → 99% に逆戻りしたりすることはない。

### verbose stats の内訳行 (#386 / #387 / #388)

検知完了後、verbose は以下の順でパイプライン統計を出力する:

```text
  Pass 1 (CPU): 3410 samples, 31 blackout frames (0.9%), 5m50s
  Pass 2: 18 regions refined, 1m03s
  Scorebar: 15 match_boundary, 2 in_match, 1 non_fl, 0m12s
  Filter: 15 candidates -> 8 matches
    6 dropped (below min_match_duration)
    1 dropped (other)
  masked L2 validation: 1 segment(s) dropped (below quorum)
  masked L2 zero-gap merge: 1 pair(s) merged (flank flicker split)
  + 1 unknown match (録画途中試合)
  Splitting: 9 matches, 1m02s
```

上記の `masked L2` 行は **masked fallback 採用 run のみ表示**される (OBS 通常 run では出力されない)。

| 行 | 内容 |
| --- | --- |
| `Pass 1` | Pass 1 のサンプル数・暗転フレーム数・所要時間 |
| `Pass 2` | Pass 2 精密計測の region 数・所要時間 (#366) |
| `Scorebar` | Scorebar 分類 (match_boundary / in_match / non_fl / unknown) のカウントと所要時間 (#386) |
| `Filter` | Scorebar 通過後の候補数 → 最終 match 数。`below_min_match_duration` / `other` が 0 より大きい場合のみ内訳を追加出力 (#388)。masked fallback 採用 run では Filter 後に Layer 2 validation (drop/merge) が match 数をさらに変更する。録画途中で開始 / 終了する `unknown` 試合 (Detected には含まれるが Filter "kept" には含まれない) がある場合、内訳の直下に `+ N unknown match (録画途中試合)` 行を出力 (#433) |
| `masked L2 validation` | masked fallback 採用 run のみ。`_validate_match_segments` が 15-probe at-anchor quorum (>=2) 判定で除去した segment 数 (#822) |
| `masked L2 zero-gap merge` | masked fallback 採用 run のみ。flank flicker 由来の零ギャップ隣接 validated ペアをマージした件数 (#822) |
| `Splitting` | 分割フェーズの match 数・所要時間 (#387) |

`Filter` セクションは候補数がゼロかつドロップがゼロの場合 (whole-video fallback により match が生成されたケース) は出力を省略する。`dropped (below min_match_duration)` は **セグメント長が `min_match_duration` に満たなかった数**、`dropped (other)` は短尺動画の whole-video 候補不適合等の残余カウント。`in_match` / `non_fl` はここに含まれず、上の Scorebar 行がそのカウントを担う (重複防止)。

### metadata.json

分割結果の機械可読な記録。外部ツールやスクリプトから参照可能。L4 (former L3, メタデータ化) パイプラインの入力として使用予定。L4 未着手のため、フィールド構造は暫定であり破壊的変更の可能性がある。

**キーフレーム精度の注意点**: `split` は `ffmpeg -c copy` で再エンコードなしに分割する。このため各 match の `start_time` / `end_time` は元動画のキーフレーム位置に丸められ、検知された boundary とは最大でキーフレーム間隔 (OBS 録画で通常 2 秒) 程度ずれうる。従来 `note` フィールドに埋めていた文言はスキーマから取り除き、本仕様書の説明に移した (#463)。

**スキーマ契約の総論**は [`docs/metadata-spec.md`](metadata-spec.md) を参照。生成契約・書き込み方針・GUI 編集契約・`metadata.original.json` policy・手動編集シナリオ・将来拡張が集約されている。

**トップレベル:** (`schemas/metadata.schema.json` の全 16 field を掲載。フィールドごとの詳細契約は [`docs/metadata-spec.md`](metadata-spec.md) が正)

| フィールド | 型 | 説明 |
| --- | --- | --- |
| `schema_version` | string | metadata スキーマの版数 (現行 `"1"`)。欠落は v1 として読む (#515) |
| `source` | string | 入力動画のファイルパス |
| `source_duration` | float | 入力動画の総再生時間（秒） |
| `source_duration_display` | string | 総再生時間の表示形式（MM:SS or H:MM:SS） |
| `source_fps` | float \| null | 入力動画のフレームレート。ffprobe で取得できない場合 `null` |
| `detected_at` | string | 検知パイプライン開始直前のタイムスタンプ (`detection_started_at` と同値、後方互換のため維持、UTC ISO 8601 秒精度、`Z` 終端、例: `"2026-04-19T12:34:56Z"`)。`run_split` 開始直後に生成し、キャッシュヒット時も本ランの生成時刻を記録する |
| `detection_started_at` | string | 検知パイプライン開始直前のタイムスタンプ (#586)。`detected_at` と同値。新規書き込みは ✓ / 読み込み時は欠落許容 (legacy metadata.json)。`--from-metadata` 経路は元 metadata の値を pass-through |
| `detection_completed_at` | string | metadata.json 書き込み直前のタイムスタンプ (#586)。GUI CompleteScreen が `completed - started` で「所要」を表示。新規書き込みは ✓ / 読み込み時は欠落許容。`--from-metadata` 経路は元 metadata の値を pass-through |
| `detection_params` | object | 検知パラメータのスナップショット（下表） |
| `matches` | array | 検出された試合セグメント |
| `gaps` | array | 試合間の有意なギャップ（>=5分） |
| `warnings` | array | 検知時の警告エントリ (#518)。現行は常に空配列 |
| `system_info` | object | 検知実行環境の記録 (#591)。GPU vendor は export のエンコーダ選択に使われる |
| `brightness_samples` | object | GUI タイムライン描画用の輝度サンプル (#569) |
| `capture_regions` | object | 解決された検出 ROI とその縮退 provenance (#810) |
| `minimap_regions` | array | `minimap` コマンドが書き戻すエリアマップ切抜き領域 (#481) |

**matches[]:**

| フィールド | 型 | 説明 |
| --- | --- | --- |
| `index` | int | 1始まりの試合番号 |
| `start_time` | float | 開始時刻（秒） |
| `end_time` | float | 終了時刻（秒） |
| `start_display` | string | 開始時刻の表示形式 |
| `end_display` | string | 終了時刻の表示形式 |
| `duration` | float | 試合時間（秒） |
| `duration_display` | string | 試合時間の表示形式 |
| `type` | string | セグメントの種別（`"fl_match"` / `"unknown"`） |
| `output_file` | string | 出力ファイルパス（POSIX 区切り、例: `output/match_001.mp4`）。Windows 実行時も `/` で記録される |

**gaps[]:**

| フィールド | 型 | 説明 |
| --- | --- | --- |
| `start_time` | float | ギャップ開始時刻（秒） |
| `end_time` | float | ギャップ終了時刻（秒） |
| `start_display` | string | ギャップ開始時刻の表示形式 |
| `end_display` | string | ギャップ終了時刻の表示形式 |
| `duration` | float | ギャップ時間（秒） |
| `duration_display` | string | ギャップ時間の表示形式 |

**detection_params:**

検知実行時の設定スナップショット。`.detection_cache.json` の `params` と重複するキーは同一値になる（互換性のため）。

| フィールド | 型 | 説明 |
| --- | --- | --- |
| `sample_interval` | float | 実効サンプリング間隔（秒）。長時間動画では `_auto_sample_interval` によってユーザー指定値から自動調整された値。`.detection_cache.json` の `params.sample_interval` と同じ値 |
| `blackout_threshold` | float | 暗転検知の輝度閾値（0-255） |
| `min_match_duration` | float | 最小試合時間（秒） |
| `min_blackout_duration` | float | 最小暗転時間（秒） |
| `no_audio` | bool | 音声ベースの境界昇格 (Fanfare スキャン) を無効化したか |
| `use_gpu` | bool \| null | GPU 検知の指定値。`null` は CLI で `--gpu` を指定せずコーデック自動選択に任せたことを示す |
| `workers` | int \| null | 並列ワーカー数の指定値。`null` は auto (`_resolve_workers` が実装の cap で解決) を示す |

## detect コマンド

検知のみ実行し `metadata.json` を生成する (#463)。`split` コマンドから検知部分だけを分離したもので、GUI (L2a) が検知結果を編集する前段として使う想定。`split --from-metadata` と対で使い、検知と分割を分離運用できる。

### 構文

```bash
allaganeye detect <video_path> [OPTIONS]
```

### 引数

| 引数 | 必須 | 説明 |
| --- | --- | --- |
| `video_path` | Yes | 入力動画ファイルのパス（MP4/MKV/AVI/MOV） |

### オプション

`split` と概ね同じオプションセットだが、`--dry-run` は存在せず (detect 自体が "dry-run 相当" のため)、`--progress-format` は detect 固有 (GUI wrapper 用、#569)。

| オプション | デフォルト | 説明 |
| --- | --- | --- |
| `-o`, `--output-dir` | `./output` | 出力ディレクトリ (`metadata.json` の配置先) |
| `--sample-interval` | `1.0` | フレームサンプリング間隔（秒） |
| `--blackout-threshold` | `15.0` | 暗転検知の輝度閾値（0-255） |
| `--min-match-duration` | `300.0` | 最小試合時間（秒） |
| `--min-blackout-duration` | `3.0` | 最小暗転時間（秒） |
| `--workers` | auto | 検知の並列ワーカー数 |
| `--gpu` / `--no-gpu` | auto | GPU 強制 / CPU 強制 (排他) |
| `--gpu-vendor` | `auto` | 使用する GPU vendor を明示指定 (`auto` / `nvidia` / `amd` / `intel`)。split と同仕様 |
| `--no-cache` | `false` | キャッシュ無視で再検知 |
| `--keep-trailing` | `false` | post-match trailing の flagging を skip し通常 match として保持 (#805 段階2、default は flag して MP4 除外・metadata 保持) |
| `--no-audio` | `false` | 音声昇格無効化 (現在 frozen) |
| `--masked` | `false` | チャット欄マスク録画向けの mask-free 領域自動検出 + 再検知。split と同仕様 |
| `-v`, `--verbose` | `false` | 詳細出力 |
| `-q`, `--quiet` | `false` | 進捗出力抑制 |
| `--progress-format` | `text` | 進捗の出力形式。`text` は click progress bar + typer ステータス行、`json` は stdout に 1 行 1 JSON (`phase` / `completed` / `total` / `elapsed_s`) を emit し人間可読出力を全抑制する (Tauri GUI wrapper 用、#569)。`text` / `json` 以外は exit 5 |

### 出力

- `<output_dir>/metadata.json` のみ (MP4 ファイルは生成されない)
- `<output_dir>/.detection_cache.json` — `split` と共有する検知結果キャッシュ

`matches[].output_file` は `match_001.mp4`, `match_002.mp4`, ... のプレースホルダ名 (相対パス)。後続の `allaganeye split --from-metadata` がこの名前で実際の MP4 を生成する。

### Exit Codes

`split` と同じ (0 / 1 / 2 / 3 / 4 / 5)。

### 典型的な使用例

```bash
# 検知のみ (GUI と連携する場合の前段)
allaganeye detect recording.mkv -o output/

# GUI で metadata.json を編集後、分割のみ実行
allaganeye split --from-metadata output/metadata.json -o output/

# あるいは従来通りの一気通貫 (後方互換)
allaganeye split recording.mkv -o output/
```

## export コマンド

detect/split が生成した `metadata.json` をもとに、N 並列で試合 MP4 を書き出す (#761)。

### 構文

```bash
# 通常モード (metadata.json をディスクから読み込む)
allaganeye export <metadata_path> --output-dir DIR [--codec copy|h264]
                                  [--concurrency N] [--name-pattern PATTERN]
                                  [--quiet|--json] [--include I,J,K] [--exclude I,J,K]

# stdin モード (GUI subprocess が in-memory 編集済み metadata を渡す場合)
echo '<metadata-json>' | allaganeye export --stdin [...]
```

### 引数

| 引数 | 必須 | 説明 |
| --- | --- | --- |
| `metadata_path` | `--stdin` と排他 | detect/split が生成した `metadata.json` のパス |
| `--stdin` | `metadata_path` と排他 | stdin から metadata JSON を読み込む (GUI subprocess モード。未保存 in-memory 編集 + filePath が null の sample mode に対応) |

### オプション

| オプション | デフォルト | 説明 |
| --- | --- | --- |
| `--output-dir DIR` | (必須) | 出力先ディレクトリ (省略不可) |
| `--codec copy\|h264` | `copy` | `copy` (FFmpeg `-c copy`、無劣化分割) または `h264` (NVENC / QSV / AMF / libx264 で再エンコード) |
| `--concurrency N` | SKU テーブル値 | 同時 export スロット数を上書き (`enumerate_h264_encoders` が返す値のデフォルト: RTX 5090 → 3、RTX 4090/4080/4070 → 2、RTX 4060 / 不明 NVIDIA → 1、QSV / AMF / libx264 → 1)。**`--codec copy` 時は本フラグより先にスロットが 1 に切り詰められるため無効** — 再エンコードしない `-c copy` を並列化してもディスク I/O を奪い合うだけでスループットが上がらないため (`allaganeye/commands/export.py`) |
| `--name-pattern PATTERN` | `{idx:03}_{type}_{start}.mp4` | 出力ファイル名テンプレート。使用可能トークン: `{idx}` / `{idx:03}` / `{type}` / `{start}` (MM-SS 形式。1 時間以上の場合は H-MM-SS、例: `1-23-41`) / `{date}` |
| `--include I,J,K` | (すべて対象) | metadata の `matches[].index` (**1 始まり**) と照合する match フィルタ (カンマ区切り)。`--exclude` との併用時は `include - exclude` が有効集合 |
| `--exclude I,J,K` | (なし) | metadata の `matches[].index` (**1 始まり**) と照合する除外フィルタ (カンマ区切り)。`type_override == "skip"` の match は本フラグに関係なく常に除外。`post_match: true` の match も無条件除外 (`--include` 指定でも MP4 化されない、#805 Phase 1 契約) |
| `--quiet` | `false` | 進捗出力を抑制 (success/error 行は stderr に出力される)。`--json` と排他 |
| `--json` | `false` | stdout に JSON Lines を emit する (GUI subprocess wire protocol)。`--quiet` と排他 |

### NVENC engine 数プローブ

`--codec h264` 指定時、**NVENC が primary encoder に選択された場合のみ** `enumerate_h264_encoders` が `metadata.json` の `system_info.gpu` (GPU モデル名リスト) を SKU テーブルで参照し、並列スロット数を決定する。

| GPU モデル | NVENC engine 数 | 出典 |
| --- | --- | --- |
| RTX 5090 | 3 | NVIDIA 公式 spec |
| RTX 5080 / 5070 / 4090 / 4080 / 4070 | 2 | NVIDIA 公式 spec |
| RTX 5060 / 4060 | 1 | NVIDIA 公式 spec |
| 不明 NVIDIA | 1 (保守的 default) | `_DEFAULT_NVENC_COUNT` |
| AMD AMF / Intel QSV / libx264 fallback | 1 | (NVENC probe は実行されない) |

#### SKU テーブルでカバーされない NVIDIA カードの挙動

以下のカードは SKU テーブルにないため `_DEFAULT_NVENC_COUNT = 1` にフォールバックする:

- **Consumer Pascal/Turing/Ampere** (GTX 10x0 / 16x0 / RTX 20x0 / 30x0): 全て NVENC engine = 1 のため **default=1 で正しい**。性能上の問題なし
- **Workstation Ampere** (RTX A4000 / A5000 / A6000 等): 実際は **NVENC engine = 2** だが default=1 で起動 → 性能を活かせない (under-utilization)。`ALLAGANEYE_EXPORT_CONCURRENCY=2` で env override すると 2 並列実行可能
- **Datacenter** (Tesla T4 / A100 / H100 / L4 等): T4 は 1 engine、A100 は 3、H100 は 3。default=1 で起動 → env override 推奨
- **Quadro Turing pro** (Quadro RTX 6000 / 8000): NVENC engine = 2、同上

#### NVENC engine 数の動的取得について

NVIDIA は **NVENC engine 数を直接公開する API を持たない** (`nvidia-smi` の session count は engine 数ではなく同時 session 上限のみ; NVML / NVENC SDK も同様)。そのため SKU テーブル + env override 方式を採用している (#761)。新しい GPU 世代がリリースされたら本テーブルを更新する。

#### env override

環境変数 `ALLAGANEYE_EXPORT_CONCURRENCY` を設定するとすべての SKU テーブル値を上書きする。用途:

- **Contention 回避**: OBS 等の他プロセスが NVENC engine を占有 → `(engine 数 - 使用中)` に設定して timeshare 低速化を回避
- **Under-utilization 解消**: SKU テーブル未カバーの workstation/datacenter カードで実際の engine 数に合わせる (例: A6000 なら `=2`、H100 なら `=3`)
- **保守的に動かす**: `=1` 指定でレガシー sequential 動作 (デバッグ時)

```bash
# RTX A6000 (NVENC 2 engine) で 2 並列実行
ALLAGANEYE_EXPORT_CONCURRENCY=2 allaganeye export <metadata.json> --codec h264

# H100 (NVENC 3 engine) で 3 並列
ALLAGANEYE_EXPORT_CONCURRENCY=3 allaganeye export <metadata.json> --codec h264

# OBS 録画中 (1 engine 占有) で RTX 5090 を 2 並列に下げる
ALLAGANEYE_EXPORT_CONCURRENCY=2 allaganeye export <metadata.json> --codec h264
```

**非 NVIDIA 環境への影響なし**: `probe_nvenc_engine_count` は NVENC が primary encoder に選ばれた時のみ呼ばれる。AMD / Intel / CPU のみのユーザーには SKU テーブルは参照されない (常に 1 slot)。

### Exit Codes

| コード | 意味 |
| --- | --- |
| 0 | 全 match 成功 (exclude された match を除く) |
| 1 | 1 件以上の match が失敗 (部分失敗または全失敗) または予期せぬ例外 |
| 2 | 入力エラー (metadata 読み込み失敗 / JSON 不正 / `source` フィールド欠落 / `--concurrency <= 0` 等の引数不正)。出力ディレクトリは不在でも自動作成されるため exit 2 にはならない |
| 3 | ffmpeg / IO エラー (VideoProcessingError 等の `AllaganEyeError` を exit code にマッピング) |
| 5 | 設定値不正 (ConfigValidationError 等の `AllaganEyeError` を exit code にマッピング) |
| 130 | SIGINT (Ctrl+C) によるキャンセル |

### Wire protocol (`--json` モード)

stdout の各行は JSON オブジェクト 1 件:

- `{"type":"progress","match_index":N,"percent":P,"stage":"encoding"|"done"}`
- `{"type":"fallback","match_index":N,"fallback_from":"h264_nvenc","fallback_to":"libx264","message":"..."}`
- `{"type":"result","match_index":N,"output_path":"...","duration_ms":N,"encoder_used":"h264_nvenc"|"libx264"|...}`
- `{"type":"error","match_index":N,"error_kind":"...","error_message":"...","error_hint":null|"..."}`
- `{"type":"summary","success":N,"failure":N,"skipped":N,"cancelled":bool}` (常に最終行)

## minimap コマンド

> **用語**: 「minimap」はコマンド名・オプション名で使う通称。実体は**エリアマップ window**（フロントライン戦場全体図を示す半透過 overlay）であり、HUD 右上などに表示される円形ナビゲーションマップではない。

`metadata.json` を入力に、試合ごとのエリアマップ window 領域を検出・切り抜いた MP4 を出力する (#481)。

2 つの動作モードを持つ:

- **提案モード** (`--region` 未指定): 領域を自動検出して `--region X,Y,W,H` 形式で提案を表示する。エンコードは行わず常に exit 4 で終了する。提案は best-effort（出た提案は信頼できるが、出ないことがある）
- **crop モード** (`--region X,Y,W,H`): 指定座標で全対象試合を切り抜き H.264 MP4 を出力する。エンコード前に `minimap_regions` を `metadata.json` へ atomic write-back する。NVENC 選択時は `-vf crop` フィルタが GPU frame を CPU に渡すため zero-copy 不可となり、`-hwaccel cuda` 単独 (auto-download) で NVDEC decode + CPU crop + NVENC encode する (#899、`_DECODE_HWACCEL_ARGS_FILTERED`)

### 構文

```bash
# 提案モード (領域検出のみ、exit 4)
allaganeye minimap <metadata.json>

# crop モード (指定領域で切り抜き、H.264 encode)
allaganeye minimap <metadata.json> --region X,Y,W,H [-o DIR] [--include I,J,K]
                  [--name-pattern PATTERN] [--quiet]
```

### 引数

| 引数 | 必須 | 説明 |
| --- | --- | --- |
| `metadata_path` | Yes | `allaganeye detect` / `allaganeye split` が生成した `metadata.json` のパス |

### オプション

| オプション | デフォルト | 説明 |
| --- | --- | --- |
| `--region X,Y,W,H` | (なし) | 切り抜き領域をピクセル座標で指定（左上原点）。省略時は提案モードになる |
| `-o DIR` / `--output-dir DIR` | `<metadata dir>/minimap/` | 出力 MP4 の書き出し先ディレクトリ |
| `--include I,J,K` | (全試合) | 対象 match index（`matches[].index`、**1 始まり**）をカンマ区切りで指定。`post_match` 試合は `--include` 指定時も常に除外 |
| `--name-pattern PATTERN` | `{idx:03}_{type}_{start}_minimap.mp4` | 出力ファイル名テンプレート。使用可能トークン: `{idx}` / `{idx:03}` / `{type}` / `{start}` (MM-SS 形式。1 時間以上の場合は H-MM-SS) / `{date}` |
| `--quiet` | `false` | 進捗出力を抑制する |
| `--json` | `false` | JSON Lines モードで stdout に出力（GUI subprocess 用）。`metadata_path` は stdin ではなく positional 引数として渡す。各行の形式は [output-spec.md §「minimap コマンド出力」](output-spec.md) を参照 |
| `--expected-mtime MS` | (なし) | crop モード書き込み前の CAS guard。`metadata.json` の現在 mtime (Unix ms) を指定する。実 mtime と不一致なら **exit 6** で即終了（外部変更検知）。GUI の ConflictModal 検知に対応 |

### 対象試合の決定順序 (crop モード)

1. `post_match: true` の試合を**無条件除外**（`--include` より優先、#805 Phase 1 契約）
2. `--include` 指定時は指定 index のみに絞る
3. `type_override == "skip"` の試合を除外
4. `edited.start_time` / `edited.end_time` が存在する場合はそちらを採用（`metadata.json` GUI 編集値を尊重）

### Exit Codes

| コード | 意味 |
| --- | --- |
| 0 | 全 match の crop 成功 |
| 1 | 1 件以上の match が encode 失敗（部分失敗含む）または予期せぬ例外 |
| 2 | 入力エラー（`metadata.json` 読み込み失敗 / `source` フィールド欠落等） |
| 4 | 提案モード正常終了（常に exit 4。crop なし） |
| 5 | `--region` 値不正（非整数 / 負値 / `W` か `H` が 16 未満 / フレーム境界越え等 ConfigValidationError） |
| 6 | metadata write-back の CAS 衝突（`--expected-mtime` と実 mtime の不一致）。GUI が ConflictModal を表示する |
| 130 | SIGINT (Ctrl+C) によるキャンセル |

## debug-brightness コマンド

フレーム輝度を CSV 出力する。暗転検知の閾値チューニング用。

### 構文

```bash
allaganeye debug-brightness <video_path> [OPTIONS]
```

### 引数

| 引数 | 必須 | 説明 |
| --- | --- | --- |
| `video_path` | Yes | 入力動画ファイルのパス（MP4/MKV/AVI/MOV） |

### オプション

| オプション | デフォルト | 説明 |
| --- | --- | --- |
| `--start` | `0.0` | 開始時刻（秒） |
| `--end` | 動画全長 | 終了時刻（秒） |
| `--interval` | `1.0` | サンプリング間隔（秒） |
| `--workers` | auto | 並列ワーカー数。auto の解決値は実装の cap に従う (正: `_resolve_workers` docstring) |
| `--roi-mode` | なし | ROI 分析モード。`scorebar`: スコアバー ROI の輝度・色情報を追加出力。`scorebar-detail`: セクション別の詳細情報も出力 |

### 出力形式

CSV 形式で stdout に出力。パイプやリダイレクトで利用可能。

```text
timestamp,brightness
0.0,12.3
1.0,245.6
2.0,8.1
```

| フィールド | 型 | 説明 |
| --- | --- | --- |
| `timestamp` | float | タイムスタンプ（秒、小数点1桁） |
| `brightness` | float | フレームの平均輝度（0.0-255.0、小数点1桁） |

### Exit Codes

| コード | 意味 |
| --- | --- |
| 0 | 正常終了 |
| 1 | 一般エラー |
| 2 | 入力ファイル不正 |
| 3 | FFmpeg / ffprobe エラー |
| 4 | 試合境界が見つからない |
| 5 | 設定値不正（パラメータの範囲外等）。`--interval <= 0` は ConfigValidationError (exit 5) で即終了 |
| 7 | 同梱物欠損 (Portable ZIP integrity-manifest.json で listed file が missing / size 不一致) #668 |

### エラー表示 (#428 / #405 matrix v2)

`split` コマンドのエラーは `-v` / `-q` によって出力量が変わる。すべてのエラーは stderr に出力される (stdout は壊れたデータを残さないよう空のまま)。

| モード | 出力形式 (AllaganEyeError 系) | 出力形式 (予期せぬ例外) |
| --- | --- | --- |
| `-v` (19a) | `Error: <msg>` + `verbose_detail()` コンテキスト (ffmpeg stderr_tail 等) + full traceback | full traceback (``__cause__`` / ``__context__`` 含む) |
| default (19b) | `Error: <msg>` + `(Run with -v / --verbose for full details)` 1 行 hint (実際は 2 スペースインデント) | `Unexpected error: <exc>` + 1 行 hint |
| `-q` (19c) | `Error: <msg>` のみ | `Unexpected error: <exc>` のみ |

`debug-brightness` には `-v` / `-q` がないため、エラーは上表の default 形式に準じるが、**存在しないオプションを誘導しないよう -v hint は出さない** (対応オプションがない場合は `show_hint=False`)。

verbose モードの traceback は CLI ハンドラが `raise typer.Exit(...) from None` で上位に抜ける直前、元の例外が `sys.exc_info()` に残っている段階で `traceback.format_exception(type(exc), exc, exc.__traceback__)` により生成される。`from None` で traceback 自体を抑制しているわけではなく、典型的なユーザーには邪魔になるため default / -q では出さない設計。

出力例 (ffmpeg 失敗 + `-v`):

```text
Error: ffmpeg failed
  command: ffmpeg -i recording.mkv ...
  return_code: 1
  stderr_tail:
    NAL unit type 12 not supported
Traceback (most recent call last):
  File "...\allaganeye\cli.py", line 163, in split
    run_split(video_path, config, verbose=verbose, quiet=quiet)
  ...
allaganeye.exceptions.VideoProcessingError: ffmpeg failed
```

出力例 (同じエラー / default):

```text
Error: ffmpeg failed
  (Run with -v / --verbose for full details)
```

出力例 (同じエラー / `-q`):

```text
Error: ffmpeg failed
```

### click-level option-parse error (#440 / PR #632)

`split` / `debug-brightness` 等のサブコマンド entrypoint より前で発生する click-level option-parse error (例: `allaganeye -version` のような single-dash long-option typo) は AllaganEyeError 系の `-v` / `-q` 切替制御の対象外。`allaganeye/cli.py` の `_suggest_long_option_hint` (line 537-571) と `main()` (line 574-611) で捕捉し、click 標準メッセージに続けて `Did you mean --<name>?` ヒントを stderr に出力する。

捕捉対象は `click.exceptions.NoSuchOption` / `UsageError` / `ClickException` (および `Abort`)。`NoSuchOption` 経路では `_suggest_long_option_hint` が argv を走査し、`-` 始まり (`--` でない) かつ長さ >= 2 の token を `--<name>` として既知の long option (typer app + 全 subcommand + `help`) と照合する。マッチしないときは hint を出さず、無関係な typo に誤導しないようにする。

出力例 (`allaganeye -version`):

```text
Usage: allaganeye [OPTIONS] COMMAND [ARGS]...
Try 'allaganeye --help' for help.

Error: No such option: -v
Did you mean --version?
```

- 出力先: stderr (click `exc.show()` + `click.echo(..., err=True)` の hint 行)
- 終了コード: 2 (`NoSuchOption.exit_code` = click UsageError 系のデフォルト)
- `-v` / `-q` の影響なし (click level / AllaganEyeError 経路と独立)
- `debug-brightness` の click-level error も本経路を通る。`-v` / `-q` を持たないサブコマンドだが、click-level hint 自体はサブコマンド固有の `-v` 案内を含まない (既知 long option 集合に `--version` 等のグローバル option が含まれるのみ)
