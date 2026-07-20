# minimap crop の NVDEC decode 有効化 (#899) design

- 日付: 2026-07-20
- 対象 issue: [#899](https://github.com/Idios/kobutachan-allaganeye/issues/899)
- 顕在化契機: [#893](https://github.com/Idios/kobutachan-allaganeye/issues/893) Phase 2 (PR #897) の実機検証 (Idios、2026-07-20)
- 前提: #481 (minimap crop CLI) / #761 #791 (encode pool + NVDEC zero-copy)
- 決定方式: brainstorming (fallback 戦略 AskUserQuestion、2026-07-20)

## 1. 背景と根本原因

minimap crop (`allaganeye minimap <meta> --region X,Y,W,H`) は `-vf crop=W:H:X:Y` フィルタ付きで H.264 encode する。実機検証で **AV1 1080p60 ソースの crop が GPU 13% / CPU 数コアのみ / 分単位** と判明。実 ffmpeg コマンド:

```text
ffmpeg -ss .. -to .. -i <av1.mkv> -vf crop=358:372:6:3 -c:v h264_nvenc -rc vbr -cq 19 -preset p5 -c:a copy <out>
```

`-c:v h264_nvenc` = GPU encode だが、`-i` の前に `-hwaccel` が無く **decode は CPU ソフトウェア** = AV1 の重いソフトデコードがボトルネック。crop 領域は小さく NVENC encode は軽量なので、GPU は decode 待ちで遊ぶ。

**根本原因**: `allaganeye/export/ffmpeg_runner.py:243`

```python
if codec != "copy" and video_filter is None:      # ← video_filter 有りだと decode hwaccel を挿入しない
    args.extend(_DECODE_HWACCEL_ARGS[encoder])     # NVENC: -hwaccel cuda -hwaccel_output_format cuda
```

`_DECODE_HWACCEL_ARGS[NVENC]` は zero-copy (`-hwaccel_output_format cuda`) で GPU frame を出すため CPU の `crop` filter に渡せず (#481)、フィルタ有り時は NVDEC を丸ごとスキップしていた。export (フィルタ無し) は既に NVDEC zero-copy で GPU decode 済みで、**フィルタ有り = minimap crop だけが取り残されている**。

## 2. 目的 / 非目的

**目的**: crop フィルタ有りの NVENC 経路で NVDEC decode を有効化し、AV1 等の重いソースの decode を GPU に載せて CPU ボトルネックを解消する。

**非目的**:

- export (フィルタ無し) 経路の変更 (#791 の zero-copy NVDEC + 2-tier fallback を維持)。
- AMD/Intel の decode hwaccel wiring (#762 保留、software decode 継続)。
- GPU crop filter (`*_cuda`) や zero-copy + hwdownload 化 (今回は auto-download 方式で足りる)。
- I/O 帯域改善 (ディスク律速は別問題)。

## 3. 設計

### 3.1 コア変更: filter 用 decode-only hwaccel

zero-copy (`-hwaccel_output_format cuda`) ではなく **`-hwaccel cuda` 単独** を使う。これは NVDEC で GPU decode した frame を **自動で system memory に download** するため、CPU の `crop` filter に渡せる。

`allaganeye/export/ffmpeg_runner.py` に新 mapping を追加:

```python
# #899: video_filter 有り (minimap crop) 用の decode-only hwaccel。
# -hwaccel_output_format cuda を付けない = NVDEC decode 後に auto-download し
# CPU crop filter に渡せる。GPU decode + CPU crop + NVENC encode。
_DECODE_HWACCEL_ARGS_FILTERED: dict[H264Encoder, tuple[str, ...]] = {
    H264Encoder.NVENC: ("-hwaccel", "cuda"),  # decode-only, auto-download
    H264Encoder.QSV: (),   # #762 保留 (software decode 継続)
    H264Encoder.AMF: (),   # #762 保留
    H264Encoder.LIBX264: (),
}
```

`_build_ffmpeg_args` の 243 行を分岐:

```python
if codec != "copy":
    if video_filter is None:
        args.extend(_DECODE_HWACCEL_ARGS[encoder])           # zero-copy (export、不変)
    else:
        args.extend(_DECODE_HWACCEL_ARGS_FILTERED[encoder])  # #899: filter 用 decode-only
```

export (フィルタ無し) の argv は完全不変。filter 有り NVENC のみ `-hwaccel cuda` が `-i` 前に付く。

### 3.2 fallback ladder (Idios 選択 B: 3-tier)

filter 有り NVENC の fallback を **3-tier** にする:

| tier | argv | decode | encode |
| --- | --- | --- | --- |
| 1 | `-hwaccel cuda -i .. -vf crop.. -c:v h264_nvenc` | NVDEC (GPU) | NVENC (GPU) |
| 2 | `-i .. -vf crop.. -c:v h264_nvenc` | software (CPU) | NVENC (GPU) |
| 3 | `-i .. -vf crop.. -c:v libx264` | software (CPU) | libx264 (CPU) |

tier2 = **現状の動く経路** (software decode + NVENC)。tier3 = 既存の libx264 fallback。

**遷移条件 (失敗分類)**: tier1 の失敗を **decode 段** と **encode 段** に分類してルーティングする:

- tier1 失敗 stderr が **NVDEC decode 段 pattern** (11 個) にマッチ → **tier2** (software decode + NVENC。非対応 GPU / AV1 NVDEC 無しはここで NVENC encode を維持)。
- tier1 失敗 stderr が **NVENC encode-init 段 pattern** (3 個) にマッチ → **tier3** 直行 (NVENC は tier2 でも失敗するため)。
- tier2 失敗 (software decode は AV1 でも失敗しない前提なので必ず NVENC encode 失敗) → **tier3**。

**pattern 分類**: 既存 `_GPU_ENCODER_FAILURE_PATTERNS[NVENC]` (14 pattern) を 2 サブセットに分割 (値は現行と完全同一、集合の分割のみ):

```python
_NVENC_ENCODE_STAGE_PATTERNS = (
    "no nvenc capable devices found",
    "cannot load cuda driver",
    "openencodesessionex failed",
)  # 3: encoder-init

_NVENC_DECODE_STAGE_PATTERNS = (
    "could not dynamically load cuda", "cannot load libcuda",              # L1 (2)
    "device creation failed", "device setup failed for decoder",
    "no device available for decoder", "failed to create cuda context",
    "cannot init cuda",                                                    # L2 (5)
    "cuvidcreatedecoder", "hwaccel transfer data failed",
    "cuvid: failed", "could not allocate hardware frames",                # L3 (4)
)  # 11: NVDEC decode-stage

_GPU_ENCODER_FAILURE_PATTERNS[NVENC] = _NVENC_ENCODE_STAGE_PATTERNS + _NVENC_DECODE_STAGE_PATTERNS
```

`is_gpu_encoder_failure` (既存) は合成した全 pattern を見るので後方互換 (export の 2-tier fallback 判定は不変)。新規に `_nvenc_decode_stage_failure(stderr) -> bool` を追加し、filter 有り NVENC の tier1→tier2 判定に使う。

### 3.3 適用範囲

3-tier は **filter 有り NVENC のみ**。filter 無し NVENC (export) は現行 2-tier (`[NVDEC zero-copy + NVENC] → [libx264]`) を維持 (#791 validated)。この非対称は意図的 (export は zero-copy が既に効いており、software-decode+NVENC の中間 tier は不要 / #791 挙動を触らない)。

## 4. コンポーネント

| 対象 | 変更 |
| --- | --- |
| `allaganeye/export/ffmpeg_runner.py` `_DECODE_HWACCEL_ARGS_FILTERED` | 新規 mapping (NVENC=`-hwaccel cuda`) |
| `_build_ffmpeg_args` | 243 行分岐 (filter 有り → filtered mapping) |
| `_GPU_ENCODER_FAILURE_PATTERNS` / `_nvenc_decode_stage_failure` | NVENC pattern を 2 サブセット化 + decode 段判定 helper |
| `run_export_attempt` (retry ロジック) | filter 有り NVENC の 3-tier ladder (tier1 失敗を decode/encode 段で routing) |
| `docs/cli-spec.md` / `CLAUDE.md` §GPU モード | filter 有り時の decode hwaccel 挙動を追記 |

## 5. テスト計画 (TDD)

Red-Green-Refactor 遵守。

1. **argv 構築** (unit): filter 有り NVENC → `-hwaccel cuda` 有り・`-hwaccel_output_format cuda` **無し**・`-vf crop` 有り。filter 有り LIBX264 → hwaccel 無し。filter 無し NVENC → zero-copy 不変 (回帰 pin)。filter 有り QSV/AMF → hwaccel 無し (#762 保留)。
2. **decode 段判定** (unit): `_nvenc_decode_stage_failure` が NVDEC 11 pattern で True / encode-init 3 pattern で False。`is_gpu_encoder_failure` (合成) が両方で True (後方互換)。
3. **3-tier ladder** (unit、mock ffmpeg): tier1 が decode-stage stderr で失敗 → tier2 argv (software decode + NVENC) で retry。tier1 が encode-init stderr で失敗 → tier3 (libx264) 直行 (tier2 skip)。tier2 失敗 → tier3。各 tier の argv を検証。
4. **export 非回帰** (unit): filter 無し NVENC の 2-tier fallback が不変。
5. **実機 benchmark** (§6、slow / 手動): 実測。
6. **AC checks**: `ruff check . / ruff format --check . / pyright / pytest`。

## 6. 実機 benchmark (Iron Law 6)

`ffmpeg_runner.py` (encode 経路) 変更のため mock 不可。RTX 5090 + AV1 ソースで実測 (Idios or detached Start-Process、`feedback_long_gpu_job_detached_execution`):

- **before/after**: 同一 match の crop wall-time を tier1 (NVDEC) vs 現状 (software) で比較。GPU util (nvidia-smi) 上昇・wall-time 短縮・CPU 低下を確認。
- **fallback**: `-hwaccel cuda` を強制失敗させ (例: env で NVDEC 無効化 / 非対応 codec) tier2 (software+NVENC) に落ちることを実機で確認。
- 検証ソース: `E:\royalstraightflesh\videos\20260116\2026-01-16 22-12-57.mkv` (AV1 1080p60)。

## 7. スコープ境界 / 移植性

- **released encode path** (`allaganeye/export/ffmpeg_runner.py`)。**#897 (Phase 2 GUI) とは別 PR** (1 PR = 1 scope)。base = develop-0.3.0。
- NVENC のみ。非対応 GPU (AV1 NVDEC 無しの旧 NVIDIA 等) は tier1 失敗 → tier2 (software+NVENC) で graceful degrade (現状同等)。AMD/Intel は #762 まで software decode。
- `-hwaccel cuda` の auto-download は codec 非依存 (H.264/HEVC/AV1 いずれも NVDEC 対応なら効く)。NVDEC が codec 非対応なら decode 段失敗 → tier2。

## 8. 参照

- issue: [#899](https://github.com/Idios/kobutachan-allaganeye/issues/899)
- 前提: #481 / #761 / #791 (`_DECODE_HWACCEL_ARGS` / `_GPU_ENCODER_FAILURE_PATTERNS` 導入)
- 顕在化: #893 Phase 2 (#897)
