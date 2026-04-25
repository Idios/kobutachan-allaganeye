# CLI コマンド仕様

> **スコープ**: 本 doc は CLI (`allaganeye` サブコマンド) の構文を扱う。GUI (Allagan Eye.exe) と CLI の起動経路・全体像は [system-architecture.md](system-architecture.md) を参照。

CLI コマンド・引数・オプションの**構文**をまとめる。各オプション組み合わせごとの**出力側**の期待仕様は [`docs/output-spec.md`](output-spec.md) に分離して定義されており、新規 CLI オプション追加時はそちらのマトリクスも更新する (#405)。

## 前提条件

| 要件 | 説明 |
|---|---|
| ffmpeg / ffprobe 4.1+ | 以下の順序で自動検索: (1) PATH (`shutil.which`) (2) `ALLAGANEYE_FFMPEG` 環境変数で指定したディレクトリ (3) OS 別既知パス（Windows: winget `Gyan.FFmpeg`、macOS: Homebrew）。配布版・dev 環境ともに LGPLv3 版 (BtbN FFmpeg-Builds `win64-lgpl-shared`) の使用を推奨 (#508)。winget `Gyan.FFmpeg` は GPL 版で、後方互換 fallback として自動検索される |

## グローバルオプション

| オプション | 説明 |
|---|---|
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
|---|---|---|
| `video_path` | 下記いずれか | 入力動画ファイルのパス（MP4/MKV/AVI/MOV）。`--from-metadata` と排他 |
| `--from-metadata` | 下記いずれか | `allaganeye detect` が出力した `metadata.json` のパス。指定時は検知をスキップし分割のみ実行 (#463)。`video_path` / `--dry-run` と排他 |

### オプション

| オプション | デフォルト | 説明 |
|---|---|---|
| `-o`, `--output-dir` | `./output` | 出力ディレクトリ |
| `--sample-interval` | `1.0` | フレームサンプリング間隔（秒） |
| `--blackout-threshold` | `15.0` | 暗転検知の輝度閾値（0-255） |
| `--min-match-duration` | `300.0` | 最小試合時間（秒）。これより短いセグメントは無視 |
| `--min-blackout-duration` | `3.0` | 最小暗転時間（秒）。これより短い暗転は無視 |
| `--workers` | auto | 検知の並列ワーカー数（デフォルト: 自動=`min(cpu_count, 24)`） |
| `--gpu` | `false` | GPU アクセラレーション検知を強制（チャンク並列デコード）。利用不可時は CPU フォールバック。**`--no-gpu` と同時指定は排他エラー (exit 5) (#419)** |
| `--no-gpu` | `false` | GPU を無効化し CPU 検知を強制する。**`--gpu` と同時指定は排他エラー (exit 5) (#419)** |
| `--gpu-vendor` | `auto` | 使用する GPU vendor を明示指定 (#546 / #553)。値: `auto` / `nvidia` / `amd` / `intel`。**実装済みは `nvidia` (cuvid, #546) と `amd` (d3d11va + hwdownload, #553)**。`intel` は **exit 5** (#550 で実装予定)。probe に無い vendor を要求すると exit 5。default は probe 結果から `_VENDOR_PREFERENCE` (nvidia > amd > intel) 順で実装済み vendor を選ぶ |
| `--no-cache` | `false` | キャッシュされた検知結果を無視して再検知する |
| `--no-audio` | `false` | 音声ベースの試合境界昇格（Fanfare スキャン）を無効化する。**現在は音声モジュールが凍結中（#327）のため、本フラグの値に関わらずスキャンは常にスキップされる。verbose 出力では `audio=frozen` と表示される (#384)** |
| `--dry-run` | `false` | 検知のみ実行し分割しない（検知結果はキャッシュに保存される） |
| `-v`, `--verbose` | `false` | 詳細出力（メタデータ詳細、gap 情報）。**`-q` と同時指定は排他エラー (exit 5) (#419)** |
| `-q`, `--quiet` | `false` | 進捗出力を抑制（出力ファイル一覧のみ）。**`-v` と同時指定は排他エラー (exit 5) (#419)** |

`--gpu` / `--no-gpu` のいずれも指定しない場合はコーデックから自動選択される (H.264/HEVC/AV1/VP9 → GPU、それ以外 → CPU) (#414)。ハードウェア要件は [`docs/video-processing.md`](video-processing.md) §「コーデック自動選択」を参照。

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
Detecting match boundaries (interval=3.0s, threshold=15.0, workers=auto, min_match=300.0s, min_blackout=3.0s, audio=frozen)
Detecting  #################################### 100% 0:00:22
Refining   #################################### 100% 0:00:15
Scorebar   #################################### 100% 0:00:08
Splitting  #################################### 100% 0:00:05
...
```

ヘッダ各行の意味:

| 行 | 意味 | 取得失敗時 |
|---|---|---|
| 1 行目 | allaganeye / ffmpeg / Python / OS のバージョン | ffmpeg は `(unknown)` にフォールバック |
| `CPU:` | CPU モデル + `(物理Core/論理Thread)` (#377) | `(unavailable)` / `(unknown CPU) (NT)` 等 |
| `GPU:` | GPU モデル (+ NVIDIA のみ VRAM) (#377) | `(unavailable)` |
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
  sample_interval=3.0s, threshold=15.0, min_match=300.0s, min_blackout=3.0s, audio=frozen
Detected 8 match(es) in recording.mkv (2:50:28) (cached)
  Match 1:   00:00 -   15:17  (15m17s)  [unknown]
  ...
Splitting  #################################### 100% 0:00:05
  Splitting: 8 matches, 0m05s
Total: 0m07s
```

`audio` 表示は cache-miss 側の Detecting summary と同じヘルパ (`_audio_status_str`) を経由するため、`AUDIO_FROZEN` 状態を反映する (#384)。

#### キャッシュ再読み込み失敗時のフォールバック

`_load_cache` 検証通過後でも race condition / 破損 / 権限変更等で helper 側の読み直しが失敗しうる。その場合はヘッダ (`Cache hit: detection params from ...`) を常に emit した上で、失敗理由を `(unavailable: ...)` 行で通知する。split 本体は妨げない (helper は raise しない):

| シナリオ | 出力 |
|---|---|
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

verbose モードの UX 目的 (= 情報取得) を優先する設計。silent return だと「verbose が効いていない」と誤認する恐れがあるため、ヘッダは常時 emit する (#380 tester review)。

### 検知フェーズの進捗バー (#368 / #393)

検知パイプラインは 3 フェーズに分かれ、それぞれ独立した進捗バーを 1 行ずつ表示する:

| バー | フェーズ | 進捗単位 |
|---|---|---|
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
  Splitting: 8 matches, 1m02s
```

| 行 | 内容 |
|---|---|
| `Pass 1` | Pass 1 のサンプル数・暗転フレーム数・所要時間 |
| `Pass 2` | Pass 2 精密計測の region 数・所要時間 (#366) |
| `Scorebar` | Scorebar 分類 (match_boundary / in_match / non_fl / unknown) のカウントと所要時間 (#386) |
| `Filter` | Scorebar 通過後の候補数 → 最終 match 数。`below_min_match_duration` / `other` が 0 より大きい場合のみ内訳を追加出力 (#388) |
| `Splitting` | 分割フェーズの match 数・所要時間 (#387) |

`Filter` セクションは候補数がゼロかつドロップがゼロの場合 (whole-video fallback により match が生成されたケース) は出力を省略する。`dropped (below min_match_duration)` は **セグメント長が `min_match_duration` に満たなかった数**、`dropped (other)` は短尺動画の whole-video 候補不適合等の残余カウント。`in_match` / `non_fl` はここに含まれず、上の Scorebar 行がそのカウントを担う (重複防止)。

### metadata.json

分割結果の機械可読な記録。外部ツールやスクリプトから参照可能。L3（メタデータ化）パイプラインの入力として使用予定。L3 未着手のため、フィールド構造は暫定であり破壊的変更の可能性がある。

**キーフレーム精度の注意点**: `split` は `ffmpeg -c copy` で再エンコードなしに分割する。このため各 match の `start_time` / `end_time` は元動画のキーフレーム位置に丸められ、検知された boundary とは最大でキーフレーム間隔 (OBS 録画で通常 2 秒) 程度ずれうる。従来 `note` フィールドに埋めていた文言はスキーマから取り除き、本仕様書の説明に移した (#463)。

**スキーマ契約の総論**は [`docs/metadata-spec.md`](metadata-spec.md) を参照。生成契約・書き込み方針・GUI 編集契約・`metadata.original.json` policy・手動編集シナリオ・将来拡張が集約されている。

**トップレベル:**

| フィールド | 型 | 説明 |
|---|---|---|
| `source` | string | 入力動画のファイルパス |
| `source_duration` | float | 入力動画の総再生時間（秒） |
| `source_duration_display` | string | 総再生時間の表示形式（MM:SS or H:MM:SS） |
| `detected_at` | string | **metadata.json 生成時刻** (UTC ISO 8601 秒精度、`Z` 終端、例: `"2026-04-19T12:34:56Z"`)。`run_split` 開始直後に生成し、キャッシュヒット時も本ランの生成時刻を記録する。検知自体が cache から復元されたか否かではなく、当該 metadata ファイルがいつ書き出されたかのトレーサビリティとして機能する |
| `detection_params` | object | 検知パラメータのスナップショット（下表） |
| `matches` | array | 検出された試合セグメント |
| `gaps` | array | 試合間の有意なギャップ（>=5分） |

**matches[]:**

| フィールド | 型 | 説明 |
|---|---|---|
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
|---|---|---|
| `start_time` | float | ギャップ開始時刻（秒） |
| `end_time` | float | ギャップ終了時刻（秒） |
| `start_display` | string | ギャップ開始時刻の表示形式 |
| `end_display` | string | ギャップ終了時刻の表示形式 |
| `duration` | float | ギャップ時間（秒） |
| `duration_display` | string | ギャップ時間の表示形式 |

**detection_params:**

検知実行時の設定スナップショット。`.detection_cache.json` の `params` と重複するキーは同一値になる（互換性のため）。

| フィールド | 型 | 説明 |
|---|---|---|
| `sample_interval` | float | 実効サンプリング間隔（秒）。長時間動画では `_auto_sample_interval` によってユーザー指定値から自動調整された値。`.detection_cache.json` の `params.sample_interval` と同じ値 |
| `blackout_threshold` | float | 暗転検知の輝度閾値（0-255） |
| `min_match_duration` | float | 最小試合時間（秒） |
| `min_blackout_duration` | float | 最小暗転時間（秒） |
| `no_audio` | bool | 音声ベースの境界昇格 (Fanfare スキャン) を無効化したか |
| `use_gpu` | bool \| null | GPU 検知の指定値。`null` は CLI で `--gpu` を指定せずコーデック自動選択に任せたことを示す |
| `workers` | int \| null | 並列ワーカー数の指定値。`null` は auto（`_resolve_workers` が `min(cpu_count, 24)` で解決）を示す |

## detect コマンド

検知のみ実行し `metadata.json` を生成する (#463)。`split` コマンドから検知部分だけを分離したもので、GUI (L2a) が検知結果を編集する前段として使う想定。`split --from-metadata` と対で使い、検知と分割を分離運用できる。

### 構文

```bash
allaganeye detect <video_path> [OPTIONS]
```

### 引数

| 引数 | 必須 | 説明 |
|---|---|---|
| `video_path` | Yes | 入力動画ファイルのパス（MP4/MKV/AVI/MOV） |

### オプション

`split` と同じオプションセットだが `--dry-run` は存在しない (detect 自体が "dry-run 相当" のため)。

| オプション | デフォルト | 説明 |
|---|---|---|
| `-o`, `--output-dir` | `./output` | 出力ディレクトリ (`metadata.json` の配置先) |
| `--sample-interval` | `1.0` | フレームサンプリング間隔（秒） |
| `--blackout-threshold` | `15.0` | 暗転検知の輝度閾値（0-255） |
| `--min-match-duration` | `300.0` | 最小試合時間（秒） |
| `--min-blackout-duration` | `3.0` | 最小暗転時間（秒） |
| `--workers` | auto | 検知の並列ワーカー数 |
| `--gpu` / `--no-gpu` | auto | GPU 強制 / CPU 強制 (排他) |
| `--no-cache` | `false` | キャッシュ無視で再検知 |
| `--no-audio` | `false` | 音声昇格無効化 (現在 frozen) |
| `-v`, `--verbose` | `false` | 詳細出力 |
| `-q`, `--quiet` | `false` | 進捗出力抑制 |

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

## debug-brightness コマンド

フレーム輝度を CSV 出力する。暗転検知の閾値チューニング用。

### 構文

```bash
allaganeye debug-brightness <video_path> [OPTIONS]
```

### 引数

| 引数 | 必須 | 説明 |
|---|---|---|
| `video_path` | Yes | 入力動画ファイルのパス（MP4/MKV/AVI/MOV） |

### オプション

| オプション | デフォルト | 説明 |
|---|---|---|
| `--start` | `0.0` | 開始時刻（秒） |
| `--end` | 動画全長 | 終了時刻（秒） |
| `--interval` | `1.0` | サンプリング間隔（秒） |
| `--workers` | auto | 並列ワーカー数（デフォルト: 自動=`min(cpu_count, 24)`） |
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
|---|---|---|
| `timestamp` | float | タイムスタンプ（秒、小数点1桁） |
| `brightness` | float | フレームの平均輝度（0.0-255.0、小数点1桁） |

### Exit Codes

| コード | 意味 |
|---|---|
| 0 | 正常終了 |
| 1 | 一般エラー |
| 2 | 入力ファイル不正 |
| 3 | FFmpeg / ffprobe エラー |
| 4 | 試合境界が見つからない |
| 5 | 設定値不正（パラメータの範囲外等） |

### エラー表示 (#428 / #405 matrix v2)

`split` コマンドのエラーは `-v` / `-q` によって出力量が変わる。すべてのエラーは stderr に出力される (stdout は壊れたデータを残さないよう空のまま)。

| モード | 出力形式 (AllaganEyeError 系) | 出力形式 (予期せぬ例外) |
|---|---|---|
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
