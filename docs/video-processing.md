# 動画処理設計

## 概要

L1 の動画処理は以下の3段階で構成される:

1. **probe**: ffprobe で入力動画のメタデータを取得
2. **detect**: ffmpeg 並列プローブで暗転を検知し、試合境界を特定
3. **split**: FFmpeg で試合ごとに動画を分割

## probe（メタデータ取得）

ffprobe を使用して以下の情報を取得:

- コーデック（映像/音声）
- 解像度
- フレームレート（r_frame_rate → avg_frame_rate フォールバック）
- 総再生時間
- コンテナ形式

## detect（試合境界検知）

試合境界の検知は 2 つのアプローチを組み合わせて行う:

1. **暗転検知**: フレームの平均輝度に基づく暗転区間の検出（全録画で動作）
2. **スコアバーフィルタリング**: FL UI（画面上部のスコアバー）の有無による暗転の分類・除外（`src_resolution` 指定時に有効）

暗転検知で候補を収集し、スコアバーフィルタリングで誤検知を除去する多段構成。

### 暗転検知の原理

フロントラインの試合間には必ずロード画面（暗転）が入る。この特性を利用し、暗転区間をセパレータとして試合を分割する。

### フレームサンプリング方式

全フレームの解析はコストが高いため、一定間隔（デフォルト1秒）でフレームをサンプリングする。

**方式**: ffmpeg の `-ss`（入力シーク）で各タイムスタンプに直接ジャンプし、1フレームのみデコード。

```bash
ffmpeg -ss {timestamp} -i input.mkv -frames:v 1 -s 320x180 -pix_fmt gray -f rawvideo pipe:1
```

- `-ss` を `-i` の前に配置（入力シーク = キーフレームベースの高速シーク）
- `-s 320x180`: 輝度計算に十分な低解像度（デコード負荷 1/36）
- `-pix_fmt gray`: grayscale でパイプ出力（Python 側の変換不要）
- パイプから `numpy.frombuffer` + `numpy.mean` で平均輝度を計算

### 並列実行

`ThreadPoolExecutor(max_workers=min(cpu_count, 24))` で複数タイムスタンプを同時にプローブ。各 ffmpeg プロセスは独立したキーフレームシークを行うため、不要フレームのデコードが発生しない。`--workers` オプションで明示指定も可能。

**設計経緯**: OpenCV `VideoCapture` → シーケンシャル `grab()`/`read()` → ffmpeg `select` フィルタ → **並列 `-ss` プローブ** と段階的に改善。select フィルタは全フレームをデコード後にフィルタリングするため、大容量ファイルで効果がなかった。

### 暗転判定とフィルタリング

1. 平均輝度が `blackout_threshold`（デフォルト 15.0）以下 → 暗転フレーム
2. 連続する暗転フレームを blackout region にマージ（tolerance: `sample_interval * 2`）
3. `min_blackout_duration`（デフォルト 3.0s）未満の短い暗転を除外

**`min_blackout_duration` の背景**: FF14 FL ではダウン→リスポーン時に 1-2 秒の暗転が発生する。これを試合境界と誤判定すると試合が途中で分断される。3.0s をデフォルトにすることで、リスポーン暗転（1-2s）を確実に除外し、試合間暗転（5s+）のみを検知する。

### 暗転内パディング

`-c copy` モードではキーフレーム単位での分割となり、指定した分割点から最大 ~2s のずれが発生する。カット点が暗転区間の内部に収まることを保証するため、分割境界を暗転リージョンの内側に 3.0s オフセットする（`_BLACKOUT_PADDING`）。短い暗転区間ではリージョン長の半分にクランプ。

### エラーハンドリング

- ffmpeg プローブ失敗: 輝度 255.0（非暗転）として扱い、偽陽性（暗転見逃し）を回避
- ffmpeg タイムアウト（30s/プローブ）: 同上
- `duration_hint` 未指定: `VideoProcessingError` を送出（プローブにはduration が必須）

### 遷移領域の拡張検知（transition expansion）

暗転に隣接する「遷移領域」（brightness < `_TRANSITION_THRESHOLD=55.0`）を暗転領域に含めて拡張する。

**背景**: 試合境界の暗転が短い（2-3s）場合、暗転の持続時間だけでは判別できないケースがある。しかし試合境界後にはロビー画面（brightness ~51）が 10-20s 続くのに対し、リスポーン後は即座に brightness 60+ に復帰する。この差異を利用し、暗転 + ロビー画面を一体の領域として扱うことで検知を可能にする。

| 暗転タイプ | 暗転 | 直後の brightness | 拡張後 duration | 結果 |
|---|---|---|---|---|
| リスポーン (1-1.5s) | < 15 | 即 60+ | 1-1.5s | 除外 |
| 試合境界 + ロビー (2-3s) | < 15 | ~51 が 20s | 22-23s | **検出** |

### 2パス精密計測（refine）

粗いスキャンで検出した暗転候補を、細かい interval で再プローブし正確な持続時間を計測する。

**背景**: interval=1.0s では 2.0s の暗転と 1.5s のリスポーン暗転が同じ計測値（1.0s）になり区別できない。transition expansion も発動しないパターン（暗転後すぐに明るい画面に復帰する試合境界）が存在する。

| パス | interval | 目的 |
|---|---|---|
| Pass 1（既存） | 1.0-3.0s | 全区間スキャン → 暗転候補収集 |
| Pass 2（精密計測） | 0.25s | 候補 ±5s を再プローブ → 正確な持続時間 |

精密計測後は `_REFINED_MIN_BLACKOUT=1.5s` で判定:

- 2.0s 暗転 → 計測 1.5-1.75s ≥ 1.5 → **検出**
- 1.5s リスポーン → 計測 1.0-1.25s < 1.5 → **除外**

追加プローブ数は ~400（暗転候補 ~10箇所 × ±5s / 0.25s）で、Pass 1 の 5-15%。

### GPU アクセラレーション検知（`--gpu`）

`--gpu` オプションにより Pass 1 の粗いスキャンを GPU チャンク並列デコードで実行できる（`gpu_detector.py`）。

**方式**: 動画を N チャンクに分割し、各チャンクで長寿命の ffmpeg プロセスを並列実行する。chunk 数は動画長に応じて動的調整される (#437):

- 短動画 (目安: 24 分以下): `max_parallel = min(cpu_count, 16)` を chunk 数として使用（従来通り）
- 長動画: `math.ceil(duration / _TARGET_CHUNK_WALL_SECS)` (90s/chunk 目安) で細分化、上限 `_MAX_CHUNKS=32`
- ffmpeg 並列上限は常に `max_parallel` で固定。chunks > max_parallel の場合は wave 実行となり、chunk 完了ごとのラベル更新頻度を確保する
- 最初の chunk が完了する前に `chunk_dispatch_callback` で `Detecting [dispatching N chunks, ...]` を表示し、長時間動画での 0% 停滞誤解を回避

```bash
ffmpeg -hwaccel auto -ss <chunk_start> -t <chunk_duration> -i input.mkv \
  -vf "fps=1/{interval},scale=320:180,format=gray" -f rawvideo pipe:1
```

- `-hwaccel auto`: GPU デコードを自動選択（NVIDIA CUDA, Intel QSV 等）
- `fps=1/{interval}`: sample_interval に基づくフレームフィルタ
- 1プロセスあたり多数フレームをデコードするため、GPU 初期化コストが分散される

**CPU モードとの差異**: CPU モードはタイムスタンプごとに独立した ffmpeg プロセスを起動する（`-ss` プローブ方式）。GPU モードは少数の長寿命プロセスでチャンク全体をデコードする。Pass 1 以降（transition expansion, Pass 2, フィルタリング）は共通。

**フォールバック**: GPU デコードに失敗した場合は `VideoProcessingError` を送出し、呼び出し元（`detector.py`）が自動で CPU モードにフォールバックする。

### コーデック + vendor 自動選択（#334, #414, #546）

`--gpu` / `--no-gpu` 未指定時は probe で取得した codec と GPU vendor を元に GPU/CPU を自動選択する (`_resolve_gpu_mode`)。判定セットは `_GPU_PREFERRED_CODECS` に定義。

**codec × 推奨 GPU decode (参考)**

| Codec | auto 選択 | NVDEC 要件 | Intel QSV 要件 | AMD VCN 要件 |
|---|---|---|---|---|
| H.264 | GPU | 全世代 | 全世代 | 全世代 |
| HEVC | GPU | Maxwell GM206+ | Skylake+ | VCN 1.0+ |
| AV1 | GPU (#414) | RTX 30 (Ampere) 以降 | Arc / Gen12 以降 | VCN 4.0 以降 |
| VP9 | GPU (#414) — NVIDIA は soft decode (#538), AMD は `vp9_amf` 利用可 | Maxwell 以降 (#538 で NVDEC 経路除外) | Gen9+ | VCN 1.0+ |
| その他 (mpeg2video, vc1, prores 等) | CPU | — | — | — |

- VP9 は `_GPU_PREFERRED_CODECS` に残すが NVIDIA 経路 (`_GPU_DECODER_MAP["nvidia"]`) からは除外 (#538 / #549)。理由: ffmpeg 8.1 の `vp9_cuvid` は frame を `nv12 + csp:gbr` で tag し、後段の swscaler が gray 変換を `EOPNOTSUPP (-129)` として reject する。NVIDIA auto-select で GPU mode に振られても `_decode_chunk` は else branch (`-hwaccel auto`) を使い、ffmpeg 側で soft decode (native) が選ばれる (実測 speed 2.64x)。`vp9_cuvid` の ffmpeg 側修正が入った時点で NVIDIA 経路の復活検討。AMD は #553 で d3d11va 経路に統一しているため csp:gbr 問題なし (filter 先頭で `hwdownload,format=nv12` 経由で system memory に降ろす)。

**vendor × codec 実装状況 (#546 / #553)**

| Vendor | hwaccel | h264 | hevc | av1 | vp9 | 備考 |
|---|---|---|---|---|---|---|
| NVIDIA (NVDEC cuvid) | `cuda` | `h264_cuvid` | `hevc_cuvid` | `av1_cuvid` | (soft, #538/#549) | dGPU 想定、dual GPU では優先選択 |
| AMD (d3d11va) | `d3d11va` | `h264` | `hevc` | `av1` | (未登録) | #553 で実装。AMF decoder ではなく d3d11va + native decoder + filter 先頭 `hwdownload,format=nv12` で allaganeye filter pipeline と整合させる。RDNA2+ iGPU (Granite Ridge) で実測 speed 23x (SW 7.6x 比 3x 高速) |
| Intel (QSV) | (未実装) | (未実装) | (未実装) | (未実装) | (未対応) | #550 で実装予定。`--gpu-vendor intel` は現在 exit 5 |
| Apple (VideoToolbox) | — | — | — | — | — | Windows ffmpeg 未同梱、別 issue 追跡 |

**vendor 自動選択ロジック (`_resolve_gpu_mode` + `_select_gpu_vendor`)**

1. `allaganeye.system_info.probe_gpu_vendors()` が platform 別 probe (nvidia-smi / wmic / lspci / system_profiler) で検出した vendor list を取得
2. `--gpu-vendor <vendor>` explicit の場合: `available` に含まれない、または `_VENDOR_HWACCEL_MAP` に未登録 (intel) なら `ConfigValidationError` (exit 5)
3. `--gpu-vendor auto` (default) の場合: `_VENDOR_PREFERENCE = ("nvidia", "amd", "intel")` x `available` x 実装済み (`_VENDOR_HWACCEL_MAP` に含まれる) の最上位を選択。現時点で実装済みは NVIDIA + AMD (d3d11va, #553)。Intel は #550 で追跡
4. codec が `_GPU_PREFERRED_CODECS` に含まれない場合は CPU mode。vendor が None (GPU 検出失敗 / 未実装 vendor のみ検出) でも codec match なら `use_gpu=True` を返し、`scan_gpu` の legacy path (`-hwaccel auto`) に入る。ffmpeg 側で GPU decode 失敗時は上記フォールバック経路で CPU 自動切替 (#334 既存挙動を維持)

**フォールバック経路**

- ハードウェアが新 codec に未対応の場合、ffmpeg の `-hwaccel <hwaccel>` が GPU decode に失敗 → 上記フォールバック経路で CPU に自動切替
- 明示的に GPU を使いたい場合は `--gpu` フラグで強制可能（対応しない codec では起動時に GPU decode 失敗で exit）
- `_GPU_DECODER_MAP["nvidia"]` には mpeg2video / mpeg4 / vp8 / mpeg1video も登録済みだが、`_GPU_PREFERRED_CODECS` に含めず auto では CPU (`--gpu` 明示時のみ GPU decode 経路)

### スコアバーフィルタリング（Phase 3, #111）

暗転検知だけでは分類できない暗転パターンを、フロントラインのスコアバー（画面上部の 3GC 得点バー）の有無で判別する。`src_resolution` が `detect_match_boundaries` に渡された場合に有効化される。

#### スコアバー検出（`_has_scorebar`）

暗転前後のフレームを RGB でプローブし、スコアバー ROI（画面上部中央 35-65%、高さ 0-4%）の色特性を分析する。

| 判定条件 | 閾値 | 根拠 |
|---|---|---|
| ROI 平均輝度 | 20 < brightness < 140 | FL 試合中の典型範囲。暗転 (<20) やリザルト (>140) を除外 |
| 3 セクション RGB チャンネル std | max > 15.0 | FL スコアバーの 3GC 色分離（FL=26-48, lobby=4-5, queue=8-9） |

ROI を左・中央・右の 3 セクションに分割し、各セクションの RGB 平均値の cross-section std を計算。FL スコアバーは赤/青/黄の色帯で構成されるため、高い cross-section std を示す。

#### 暗転分類（`classify_blackout`）

各暗転リージョンの前後 3 フレーム（1 秒間隔）のスコアバー判定結果を多数決で集約し、4 種類に分類する。

| 分類 | 条件 | 対応パターン | 処理 |
|---|---|---|---|
| `in_match` | 前後ともスコアバーあり | キャラダウン暗転 (#107)、FL 試合間境界 | < 3.5s → 除去、≥ 3.5s → 保持 |
| `match_boundary` | 片側のみスコアバーあり | 試合開始/終了 | 保持 |
| `non_fl` | 前後ともスコアバーなし | 非 FL コンテンツ境界 (#108/#109) | 除去 |
| `unknown` | プローブ失敗 | — | 保持（安全側） |

#### `in_match` の duration guard

`in_match` 分類のうち短い暗転（< `_IN_MATCH_MAX_DURATION=3.5s`）のみを除去する。

| 種別 | Duration（精密計測値） | 処理 |
|---|---|---|
| キャラダウン暗転 | 1.0-2.0s | 除去 |
| FL 試合間の短い境界 | 4.5s+ | 保持 |
| FL 試合間の長い境界 | 7s+ | 保持 |

閾値 3.5s はキャラダウン最大値 (2.0s) と短い境界最小値 (4.5s) のギャップ中間に設定。

#### match_boundary ペアマージ（`_merge_boundary_pairs`）

FL 試合間の遷移は 2 つの暗転を伴うことがある:

```text
FL 試合 A → 暗転₁ (match_boundary) → ロビー/結果画面 → 暗転₂ (match_boundary) → FL 試合 B
```

各暗転は正しく `match_boundary` と分類されるが、間のロビー区間が偽の短い「試合」として検出される。連続する `match_boundary` ペアのギャップ（≤ `_MERGE_GAP_MAX=600s`）を 9 点プローブし、全点でスコアバーが検出されなければ 1 つのリージョンにマージする。

- **9 点プローブの根拠**: FL 試合中はリスポーン等で一時的にスコアバーが消えるが、9 点中少なくとも 1 点は True になる（実測: 2/9）。ロビー/結果画面は 0/9。
- **`_MERGE_GAP_MAX=600s` の根拠**: 実測のロビー/結果画面ギャップは 83-468s（1.4-7.8 分）。600s で十分なマージンを確保。

#### 閾値の根拠データ

| パラメータ | 値 | 実測分布 |
|---|---|---|
| `_SCOREBAR_CHANNEL_STD_THRESHOLD` | 15.0 | lobby=4-5, queue=8-9, **FL=26-48** |
| `_IN_MATCH_MAX_DURATION` | 3.5s | キャラダウン=1.0-2.0s, **境界=4.5s+** |
| `_MERGE_GAP_MAX` | 600s | 結果画面=83-266s, lobby=232-468s |

#### 既知の制約

- 冒頭/末尾の暗転では pre/post timestamps がクランプされ、プローブ点数が減少する（#143 で重複排除済み）
- `match_boundary` ペアマージは 9 点プローブで FL コンテンツを検出できない場合に誤マージの可能性がある（実測では未発生）

## 設計経緯

### 検知方式の選定

| # | 方式 | 不採用理由 |
|---|---|---|
| 1 | OpenCV `VideoCapture` ランダムシーク | 大容量 MKV でシーク不安定。キーフレーム距離に依存し再現性が低い |
| 2 | OpenCV 逐次 `grab()`/`read()` | 全フレームをデコード。60fps/2h で実用的な速度が出ない |
| 3 | ffmpeg `select` フィルタ (`select='not(mod(t,N))'`) | フィルタ前に全フレームをデコードするため、方式 2 と同じボトルネック |
| **4** | **ffmpeg 並列 `-ss` プローブ（採用）** | キーフレームベースシーク + 1 フレームのみデコード。並列化で性能確保 |

### 検知精度の課題と対策

#### 課題 1: リスポーン暗転の誤検知（#60）

- **現象**: ダウン→リスポーン時の 1-1.5s 暗転を試合境界と誤判定
- **対策**: `min_blackout_duration=3.0` で短い暗転を除外
- **根拠**: リスポーン暗転は 1.0-1.5s、試合境界暗転は 2.0-7.0s（実測）

#### 課題 2: 試合境界の未検出 — パターン B（#71）

- **現象**: 短い暗転 (2.5s) + ロビー画面 (~51 brightness, 20s) が `min_blackout_duration` で除外される
- **対策**: transition expansion — 暗転に隣接する低輝度フレーム (brightness < 55) を暗転領域に含めて拡張
- **根拠**: ロビー画面 ~51 vs ゲーム画面 60-120（実測）。閾値 55.0 で分離可能

#### 課題 3: 試合境界の未検出 — パターン C（#77）

- **現象**: 短い暗転 (2.0s) + 明るい画面 (~79) では transition expansion が発動しない
- **対策**: 2パス精密計測 — 暗転候補を ±5s / 0.25s 間隔で再プローブし正確な持続時間を計測
- **根拠**: interval=1.0 では 2.0s 暗転と 1.5s リスポーンが同じ計測値になるが、interval=0.25 なら区別可能（実測）

#### 課題 4: `_REFINED_MIN_BLACKOUT` の閾値調整

- **初期実装**: `_REFINED_MIN_BLACKOUT = 1.8` で実装
- **問題**: 0.25s 間隔の精密計測では、2.0s の暗転が 1.75s と計測される（サンプリング間隔分の誤差）。1.75 < 1.8 のため、検出すべき試合境界暗転がフィルタされてしまう
- **修正**: `_REFINED_MIN_BLACKOUT = 1.5` に引き下げ。2.0s 暗転は 1.5-1.75s と計測され、1.5 以上なので検出される。リスポーン暗転 (1.0-1.5s) は 0.75-1.25s と計測され、1.5 未満なので除外される
- **教訓**: 離散サンプリングの計測誤差（最大 `interval` 秒）を閾値設計に織り込む必要がある

#### 検討したが不採用の手法

| 手法 | 不採用理由 |
|---|---|
| ヒストグラム比較 | カラープローブが必要でアーキテクチャ変更が大きい。L1 スコープ外 |
| テンプレートマッチング | OpenCV 再導入 + UI バージョン依存。保守コスト高 |
| 暗転前後の輝度変化率 | パターン C では前後とも ~79 で変化なし。効果なし |
| `min_blackout_duration` の単純引き下げ | リスポーン暗転 (1.0-1.5s) と試合境界 (2.0s) の差が 0.5s しかなく、粗い計測では区別不能。#60 が再発する |

#### 課題 5: キャラダウン暗転の誤検出（#107）

- **現象**: 試合中のダウン→リスポーン暗転（1-2s）が試合境界と判定され、試合が分断される
- **対策**: `classify_blackout` で前後のスコアバーを検査し、`in_match` (< 3.5s) を除去
- **根拠**: キャラダウン暗転は前後ともスコアバーあり（同一試合内）で、duration ≤ 2.0s

#### 課題 6: 非 FL コンテンツの誤検出（#108/#109）

- **現象**: 録画開始/終了時のロビー、他コンテンツとの切替暗転が試合境界と判定される
- **対策**: `classify_blackout` で前後のスコアバーを検査し、`non_fl`（両側なし）を除去
- **根拠**: 非 FL コンテンツではスコアバー ROI にカラーバンドが存在しない

#### 課題 7: FL 試合間二重境界による過検知

- **現象**: FL 試合間の遷移が 2 つの暗転として検出され、間のロビー区間が偽の試合になる
- **対策**: `_merge_boundary_pairs` で連続 `match_boundary` ペアをマージ
- **根拠**: ロビー/結果画面にはスコアバーが存在しない（9 点プローブで確認）

#### 検討したが不採用・問題があった方式（Phase 3）

| 方式 | 不採用理由 |
|---|---|
| `in_match` 無条件除去（初期実装） | FL 試合間境界も `in_match` に分類されるため、7→3 試合の致命的退行 |
| duration guard のみ (`_IN_MATCH_MAX_DURATION=5.0`) | `non_fl` 誤分類には効果なし。退行を部分的にしか修正できず（7→4） |
| `_SCOREBAR_CHANNEL_STD_THRESHOLD=8.0`（初期値） | キュー画面 (ch_std=8-9) が FL と判定される偽陽性 |
| 中間点 1 点プローブによるペアマージ | FL 試合中のリスポーン等で一時的にスコアバーが消え、実試合を誤マージ（7→6） |
| 3 点プローブ (25%, 50%, 75%) | True フレームの位置によっては検出を外す。5 点でも同様（位置依存の脆弱性） |

### 将来の拡張

- ヒストグラム比較による画面遷移検知
- リザルト画面のテンプレートマッチング
- UIオーバーレイ（HP/MPバー）の検知

## 性能チューニング

37GB/2h AV1 MKV での実測に基づく最適化。詳細なベンチマーク結果は [`docs/benchmarks.md`](benchmarks.md) を参照。

| 施策 | 変更 | 効果 | 根拠 |
|---|---|---|---|
| `max_workers` 引き上げ | 8 → `min(cpu_count, 24)` | ~3x スループット | 32コア環境で 8 は過少。ボトルネックは per-probe デコード |
| `-threads 1` | ffmpeg プロセスに追加 | スレッド競合防止 | workers=24 × デフォルトスレッド数 = 768 スレッドで逆に遅くなる |
| `sample_interval` 自動調整 | 1h+→2.0s, 2h+→3.0s | プローブ数半減-1/3 | 暗転区間 5s+ なので interval=3.0 でも検知可能 |
| 2パス精密計測 | 暗転候補のみ 0.25s | +5-15% プローブ | 精密計測は ~400 プローブ追加のみ |

## split（動画分割）

### FFmpeg コピーモード

```bash
ffmpeg -y -ss <start> -i input.mkv -to <duration> -c copy -avoid_negative_ts make_zero output.mp4
```

- `-y`: 上書き確認なし（自動生成ファイル名のため安全）
- `-ss` を `-i` の前に配置: 入力シーク（高速）
- `-to`: 相対時間指定（`-ss` が `-i` の前のため）
- `-c copy`: 再エンコードなし（高速・無劣化）
- `-avoid_negative_ts make_zero`: タイムスタンプ補正

### 出力命名規則

```text
match_001.mp4
match_002.mp4
...
```

ゼロパディング3桁。

### 分割方式の設計判断

- **`-c copy` モード採用理由**: 再エンコード不要で高速・無劣化。L1 の目的は粗い試合分割であり、フレーム精度は不要
- **暗転パディング (3.0s)**: `-c copy` はキーフレーム単位でしか分割できない（OBS デフォルト 2s GOP）。カットポイントを暗転領域の内側に 3.0s オフセットすることで、キーフレームドリフトが試合映像を切り落とすことを防止
- **非採用: `--precise` 再エンコードモード**: 実装コスト大、L1 では不要（#28 として起票済み、P3）
- **非採用: Segment Muxer 一括分割**: 単一 ffmpeg プロセスで `-f segment` による一括分割。起票時は `-ss` が `-i` の後（デコードシーク）で個別分割が遅かったが、PR #21 で input seeking に移行済み。demuxer シーク × N のオーバーヘッドは ~350ms で無視可能。一方 Segment Muxer はファイル全体を順次読みし、ギャップセグメントの書き出し・削除も必要で I/O が増加する。実装複雑度に見合う改善が得られないため見送り（#50）

### 部分失敗時の動作

途中で失敗した場合、成功済みの出力ファイルは出力ディレクトリに残る。再実行すれば `-y` により自動上書きされるため、手動削除は不要。
