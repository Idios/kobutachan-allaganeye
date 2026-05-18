# Design: detect fps filter 廃止 (#576)

| Field | Value |
| --- | --- |
| **Status** | design freeze (2026-05-18) |
| **Issue** | [#576](https://github.com/Idios/kobutachan-allaganeye/issues/576) |
| **Parent spec** | [2026-05-18-v030-l3-redefinition-design.md](2026-05-18-v030-l3-redefinition-design.md) §6.2 / §7.1 (Phase 1 Wave 1a) |
| **Related root cause** | PR [#575](https://github.com/Idios/kobutachan-allaganeye/pull/575) / issue [#560](https://github.com/Idios/kobutachan-allaganeye/issues/560) — ffmpeg 8.1 `fps=N` filter で output PTS と実フレーム内容に最大 ~1.1s offset |
| **Adversarial review** | Codex 4-round review (round-1 full → round-2/3/4 verification) で全 finding 反映済み、§11 process notes |
| **Scope** | v0.3.0 Phase 1 Wave 1a |

## §1. Goal & Non-goals

**Goal**: `allaganeye/video/detector.py::_decode_chunk_cpu` と `allaganeye/video/gpu_detector.py::_decode_chunk` から ffmpeg `-vf fps=N` を廃止し、ffmpeg version 依存の frame-selection drift (#575 / #560 / #577) を構造的に除去する。CPU と GPU で sampling logic を共通化する。

**"regression なし" の定義**: 「regression なし」は **`matches` + `gaps` projection の bit-exact 維持** を指す。内部 sample brightness 値は frame index 直接指定により正確化される方向に変化することが期待され、これは regression ではなく正常化として扱う。intermediate audit (Pass 1 候補 / Pass 2 refinement 経路) で内部 stability を別途確認する (§3 / §7)。

**Non-goals**:

- Pass 2 refinement (`_probe_single_frame`) は touch しない (per-frame -ss probe で既に fps filter 非依存)
- scorebar V2 classification (`_probe_frame_rgb_hires`) は touch しない
- audio promote / Fanfare scan は touch しない (audio は現在 frozen-by-default、再有効化時の前提条件は §10 R9 参照)
- Pillar 3 の他 issue (#761 export 並列 / #670 GUI HTTP / #752 ZIP) は scope 外
- detect 高速化そのものは副次目的 (regression しないことが必須、改善は bonus)

## §2. 採用 approach: chunk full-decode + Python N-th sampling

### §2.1 ffmpeg invocation の変更

**現行** (`detector.py:293-310` / `gpu_detector.py:409-425`):

```text
ffmpeg -threads 1 -ss <chunk_start> -t <chunk_dur> -i <video> \
  -vf "[hwdownload,format=nv12,]fps=<1/interval>,scale=320:180,format=gray" \
  -f rawvideo -pix_fmt gray pipe:1
```

**新方式**:

```text
ffmpeg -threads 1 [hwaccel_args] -i <video> -ss <chunk_start> -t <chunk_dur> \
  -fps_mode passthrough \
  -vf "[hwdownload,format=nv12,]scale=320:180,format=gray" \
  -f rawvideo -pix_fmt gray pipe:1
```

変更点:

1. `-ss <chunk_start>` を `-i <video>` の **後** に移動 (input seek → output seek)。chunk_start 直前 keyframe から discard decode し、emit する frame は chunk_start ちょうどから始まる
2. `-vf` から `fps=<value>` を削除。scale + format=gray のみ残る (hwdownload prefix は hwaccel に応じて維持)
3. `-fps_mode passthrough` を明示。ffmpeg 内部の `-vsync` 既定値による frame-rate normalization (duplicate / drop) を抑止し、decoder が emit したフレームをそのまま pipe に流す

### §2.2 Python 側 sampling logic + streaming read

新 helper `_sample_chunk_frames(stream, chunk_start, chunk_timestamps, fps_num, fps_den, expected_frames, is_tail_chunk) -> dict[float, float]`:

```text
1. subprocess.Popen で起動した ffmpeg の stdout から _FRAME_SIZE byte ずつ
   ストリーミング読出し (capture_output 禁止)
2. target timestamp t in chunk_timestamps:
   # rational fps での整数優先計算
   frame_idx = round((t - chunk_start) * fps_num / fps_den)
   if frame_idx is in available frame range:
     results[t] = mean(frame[frame_idx])
   else:
     results[t] = 255.0  # safe non-blackout fallback
3. emit frame 総数を expected_frames (= round(chunk_duration * fps_num / fps_den))
   と比較し、以下のロジックで動的 VFR 検出:

   slack = max(expected_frames * 0.01, ceil(source_fps * 0.1))
        # ≒ 1% または 100ms 分のフレーム数、どちらか大きい方
        # source_fps=60 なら最低 6 frame の絶対 slack

   if abs(emit_count - expected_frames) > slack:
     if is_tail_chunk (chunk_end >= duration - 1.0):
       WARNING ログのみ
       # tail chunk は decoder truncation で benign に frame 不足が
       # 起こりうる (§4.3 と整合)。hard fail させない
     else:
       raise VideoProcessingError(
         "Dynamic VFR detection: chunk <X>-<Y> emitted N frames, "
         "expected M (slack=±K). Input may be VFR or decoder anomaly."
       )
```

**rational fps 伝搬**:

- `probe.py` の `ProbeResult` に `fps_num: int, fps_den: int` を追加 (既存 `fps: float` も互換維持)
- `detect_match_boundaries` signature に `source_fps_num: int | None = None, source_fps_den: int | None = None` を追加 (`source_fps: float` 既存パラメータは deprecated 経路として残す)
- `_scan_cpu` / `scan_gpu` / `_decode_chunk_cpu` / `_decode_chunk` 全てに `fps_num` / `fps_den` を伝搬
- NTSC 60000/1001 (59.94005994) のような非整数フレームレートでも整数演算 (`num*t / den`) で frame_idx が exact
- 60fps CFR では rational と float の差は実用上ゼロ (float 精度 1e-15 × 432k frames = 0.001 frame 累積) — baseline 互換は維持

**memory budget**: 各 chunk で in-flight に保持する frame 数は target_count + small ring buffer (例: `max(target_count, 64)` frames)。chunk 内で frame_idx 順に読み出してから target index に到達する frame だけ保持。OOM を防ぐため `subprocess.run(capture_output=True)` は使用禁止。

**VFR 2 段防御**:

- **静的検出 (probe 段階)**: `r_frame_rate` と `avg_frame_rate` の比較は **WARNING のみ** (hard fail しない)
  - 閾値: aggregate diff > 1% で WARNING ログ "VFR の可能性あり (r=X, avg=Y)"
  - hard fail しない理由: OBS の末尾 dropped frame 等で aggregate mismatch が benign に発生するため
- **動的検出 (sampling 段階)**: `_sample_chunk_frames` で emit frame 総数 vs expected の差が `max(expected_frames * 0.01, ceil(source_fps * 0.1))` を超え、かつ tail chunk でない場合に `VideoProcessingError` で hard fail
  - これが真の VFR / decoder anomaly を捕捉する load-bearing check
  - chunk 単位で発火するため、partial VFR (一部の chunk のみ) も検出可能
  - tail chunk (chunk_end >= duration - 1.0s) は decoder truncation を許容し WARN のみ
  - 60fps なら絶対 slack ≧ 6 frame、24fps なら ≧ 3 frame、chunk-boundary GOP 不整合を許容
- packet-level PTS variance check は将来検討 (本 PR scope 外、§10 R10 で記録)

### §2.3 API 拡張

```python
detect_match_boundaries(
    video_path,
    *,
    duration_hint: float | None = None,
    source_fps: float | None = None,        # 既存 / float 後方互換
    source_fps_num: int | None = None,      # 新規 (rational 経路、推奨)
    source_fps_den: int | None = None,      # 新規 (rational 経路、推奨)
    ...
) -> list[MatchBoundary]
```

**fps 解決の優先順位**:

1. `source_fps_num` + `source_fps_den` が両方与えられた場合 → rational (整数演算)
2. `source_fps` (float) のみ与えられた場合 → `Fraction(source_fps).limit_denominator(10000)` で float から rational に変換 (互換動作)
3. 両方 None → 旧 fps filter path (env var rollback 経由のみ、§6)

`_scan_cpu` / `scan_gpu` / `_decode_chunk_cpu` / `_decode_chunk` も `fps_num` / `fps_den` を受ける。

`split_matches.py:745` の `detect_kwargs` 構築箇所に以下を追加:

```python
detect_kwargs["source_fps"] = metadata["fps"]
detect_kwargs["source_fps_num"] = metadata["fps_num"]
detect_kwargs["source_fps_den"] = metadata["fps_den"]
```

これにより probe 段階で取得した rational が detector まで素通しで届く (`run_split` / `run_detect` / `run_split_from_metadata` 全 path で `_run_detection` 経由なので 1 箇所 wiring で全 path 対応)。

## §3. Baseline strategy (3 class 分類、二段検証)

| Class | 対象 | 期待挙動 | 検証方法 |
| --- | --- | --- | --- |
| **A** (projection bit-exact + intermediate audit) | `obs-20260116` / `obs-20260119` / `obs-20260127` / `obs-20260209` | `matches` + `gaps` projection 完全一致 **かつ** Pass 1 candidate / Pass 2 refined region の intermediate audit で内部 stability 確認 | `compare-baseline.py` exit 0 **+ verbose audit dump 比較** |
| **B** (regenerate + evidence) | `obs-20260118` | Match 8 end が `6465.25 → ~6184` または隣接 region と再 merge した値に変わる (#560 root cause fix そのもの) | **本 PR 内で baseline を regenerate して commit**、PR 本文に per-frame probe evidence (`debug-brightness` CSV) と旧 → 新 diff を逐条提示 |
| **C** (tolerance) | `vtuber-primary-ground-truth.json` | ground truth 5 試合 ±10s 以内、index 順序一致 | 親 spec §8.5 既存ルール |

**intermediate audit 内容** (Class A 全 4 本 + Class B 1 本 = 計 5 本で実施):

- Pass 1 で `brightness < pass1_blackout_threshold` と判定された timestamp の集合 (旧 vs 新)
- A3 borderline pseudo-region の数 / 範囲 (旧 vs 新)
- Pass 2 refinement 後の region 数 / 各 region の (start, end) (旧 vs 新)
- 旧 → 新 で内部値が変わったが最終 projection (matches/gaps) は同一であることを確認

PR 本文に "## Intermediate audit" section として 5 本の比較を機械生成 dump で添付する。

**Class B baseline 更新の手順 (PR 内)**:

1. 新 path 実装後 `allaganeye detect 20260118.../ -o output/v3-20260118` 実行
2. 出力 `metadata.json` を `tests/baselines/v0.3.0/obs-20260118.metadata.json` に上書き
3. split も regenerate (`allaganeye split --from-metadata`) し `obs-20260118.split.json` の SHA-256 + size も更新
4. PR 本文の "## Baseline diff" section で旧 → 新の `matches` / `gaps` 全件 diff を表記
5. PR 本文の "## Evidence (per-frame probe)" section に `allaganeye debug-brightness 20260118.../` の出力から 6184.0-6185.5 周辺の brightness CSV を抜粋して添付 (新検知が物理的に正しいことの証跡)
6. `tests/baselines/_legacy/20260118.json` (PR #575 で更新済み) は **触らない** — legacy baseline 系 (`TestNoResolutionCompat`) は scorebar OFF 比較で別目的

## §4. Determinism と output seeking の根拠

### §4.1 なぜ output seeking か

`-ss` を `-i` の前に置く現行方式 (input seek) は **「最寄り keyframe にジャンプ → そこから decode 開始」** の挙動で、emit される最初の frame の PTS は chunk_start より前 (keyframe PTS) になる。frame index N → 時刻 t の mapping が chunk ごとに keyframe offset でずれる。

`-ss` を `-i` の後に置く output seek は **「keyframe から decode → chunk_start 未満の frame は discard → chunk_start ちょうどから emit」**。frame_idx 0 = chunk_start exactly。`source_fps` と組合せて frame_idx N → 時刻 `chunk_start + N / source_fps` の不変式が成立する。

### §4.2 determinism 担保

issue #214 の chunked decode 移行が確立した「同一 chunk を同一 ffmpeg で decode する限り frame N は run 間で一意」という性質を保持する。新方式は filter pipeline から fps filter を抜くだけで decode 自体は変えないため、#214 の determinism guarantee は継承される。

### §4.3 emit frame 数の上限・下限

理論値: chunk_duration × source_fps frames。

実際: decoder の末端で round-down が起きうる (chunk_duration が GOP 境界で割り切れない場合に 1-2 frame 不足)。新 sampling logic は `frame_idx >= len(frames)` のケースを 255.0 (safe non-blackout) で fallback、現行と同じ挙動を維持。

### §4.4 PTS 検証 matrix (実装中 one-off validation)

実装 PR の早期段階で、新 ffmpeg invocation が宣言通りの frame を emit することを実 runtime で証明する。**permanent CI gate ではなく実装中 evidence**として PR 本文添付。

| vendor | hwaccel | codec | 検証点 |
| --- | --- | --- | --- |
| CPU | — | AV1 / H264 / HEVC | GOP 境界スタート + 非境界スタート × 各 codec |
| NVIDIA | cuvid | AV1 / H264 / HEVC | 同上 (Idios 環境で実機) |
| AMD | d3d11va | H264 / HEVC | 同上 (Idios 環境で実機) |
| Intel | QSV | H264 / HEVC / AV1 / VP9 | 不可なら AskUserQuestion で別途依頼 / 不可確定なら scope 外明記 |

検証は `scripts/validate-fps-retirement.py` (新規スクリプト、本 PR に含める) を Idios 環境で実行する。

**`scripts/validate-fps-retirement.py` 仕様**:

```text
usage: validate-fps-retirement.py
  --video <path>           入力動画
  --chunks <CSV float>     検証する chunk_start のリスト (例: "0,100.5,3600,7200")
  --vendor <name>          cpu | nvidia | amd | intel
  --codec <name>           h264 | hevc | av1 | vp9
  [--source-fps-num <int>] rational num (省略時 ffprobe から取得)
  [--source-fps-den <int>] rational den (同上)

動作:
  1. 各 chunk_start で:
     a. ffmpeg -i <video> -ss <chunk_start> -t 0.5 [hwaccel] \
            -fps_mode passthrough \
            -vf "[hwdownload,format=nv12,]showinfo,scale=320:180,format=gray" \
            -f rawvideo -pix_fmt gray pipe:1
        を実行 (showinfo を最初に挟むことで filter graph 入力時 PTS を stderr に出力)
     b. stderr から frame 0 の "pts_time:X" を抽出
     c. pipe stdout の frame 0 を読んで brightness を計算
     d. _probe_single_frame(video, chunk_start) で参照 brightness を取得
  2. 各 chunk について以下を判定:
     - |emit_pts - chunk_start| < 1 / source_fps (frame 0 timing 検証)
     - |emit_brightness - probe_brightness| < 2.0 (brightness 整合検証、
       _BLACKOUT_THRESHOLD_UPPER_MARGIN と整合)

output (stdout):
  TSV: chunk_start, vendor, codec, emit_pts, emit_brightness,
       probe_brightness, pts_diff, brightness_diff, verdict (PASS|FAIL)
  最終行: # SUMMARY total=N pass=M fail=K skipped=S

exit code:
  0 = all chunks PASS (skipped は exit 0 を阻害しない)
  1 = any chunk FAIL
  2 = script error (ffmpeg not found, args invalid, codec/vendor mismatch 等)

edge cases:
  - tail chunk: chunk_start + 0.5 > duration の場合
    → SKIP with stderr "WARN: chunk_start <X> too close to duration <Y>"
    → PASS/FAIL count に含めず、SUMMARY 行に "skipped=N" 併記
    → 全 chunk が skip された場合のみ exit 2 (test material 不足)

  - codec/vendor capability mismatch:
    → `allaganeye.video.gpu_detector._GPU_DECODER_MAP[vendor]` を参照し
       指定 codec が未登録なら early reject
    → exit 2 with stderr "ERROR: vendor <X> does not support codec <Y>
       in _GPU_DECODER_MAP (refer to gpu_detector.py)"
    → 例: --vendor intel --codec av1 (Tiger Lake 想定) は実機 ffmpeg を
       叩く前に reject、ffmpeg 起動コストを削減
    → CPU vendor は capability 制約なし (any codec OK)

  - 短尺 clip / chunk_start が duration 超過:
    → exit 2 with stderr "ERROR: video duration <X>s shorter than
       smallest chunk_start <Y>s"
```

実装 PR で本スクリプトを Idios 環境で実行し、出力 TSV を PR 本文 "## PTS validation evidence" section に貼付ける。

スクリプトは CI gate ではない (= CI で常時実行はしない)。実装中の one-off validation 用。永続的な regression 検出は §7 の test plan が担う。

## §5. Performance budget

| 項目 | 現状 | 新方式 | delta |
| --- | --- | --- | --- |
| chunk 内 decode 量 | 全フレーム (fps filter は post-decode) | 全フレーム | ±0 |
| output seek の discard decode | 0 | keyframe → chunk_start (GOP/2 平均、~1s × 60fps = 60 frame) × 32 chunk | GPU で +1-3s, CPU で +10-30s wall-clock |
| filter pipeline cost | fps + scale + gray | scale + gray | わずかに減 |
| pipe IO 量 | 0.5 fps × 320×180 = 28.8 KB/s/chunk | source_fps × 320×180 = 3.5 MB/s/chunk (60fps) | +120x だが streaming read で memory bounded |
| Python in-flight memory per chunk | ~1 MB | `max(target_count, 64) frames × 57.6 KB` ≒ 数 MB (streaming) | OOM 防止のため Popen streaming 必須 |
| Python numpy.mean per frame | N_target frames | N_target frames (sampling 後のみ計算) | ±0 |

**現状ベンチマーク** (#779 実測): 5 baseline 合計 detect = 34m43s on RTX-class GPU `--gpu`。

**新方式の見込み**: +1-3s × 5 = ±10s 程度の wall-clock 増。約 34m43s → 34m53s (+0.5%)。

regression 上限は §7 の test plan で **「5 baseline 合計が 36 分以内」** で gate。

## §6. Rollback safety: env var migration switch + CI hygiene

**スコープ**: v0.3.0 リリース内では旧 path をビルドに含めて残し、`ALLAGANEYE_DETECT_FPS_FILTER=1` で旧 fps filter 経路に強制切替可能とする。v0.3.x patch release で削除する旨を docstring と CHANGELOG に明記。

**実装**:

```python
def _use_legacy_fps_filter() -> bool:
    return os.environ.get("ALLAGANEYE_DETECT_FPS_FILTER") == "1"
```

`_decode_chunk_cpu` / `_decode_chunk` 冒頭で分岐し、True なら現行の fps filter コマンドを生成、False なら新コマンドを生成。

**default**: False (= 新 path)。env var を意識的に立てたユーザーのみ旧挙動になる。

**CI hygiene**:

- `tests/conftest.py` の autouse fixture で `ALLAGANEYE_DETECT_FPS_FILTER` を default で unset / monkeypatch.delenv する
- 旧 path 専用 test (`test_legacy_fps_filter_via_env_var`) のみ env var を局所的に set する (monkeypatch.setenv)
- CI workflow で env var を export しないことを README で明記

**廃止 timeline**: v0.3.x で `_use_legacy_fps_filter` 関数と旧 path 全削除、env var を読まなくする。本 spec の "scope 外" としつつ v0.3.x の継続項目として記録 (CHANGELOG entry / v0.3.x roadmap issue で追跡)。

## §7. Test plan

### §7.1 unit test (mock subprocess)

1. **新 path 構築**: `_decode_chunk_cpu` / `_decode_chunk` が `-ss` を `-i` の後に置き、`-vf` に `fps=` を含まないこと、`-fps_mode passthrough` を含むことを確認 (cmd assertion)
2. **rational frame index mapping**: 既知の brightness 列を mock subprocess stdout に返させ、(a) `fps_num=60, fps_den=1` で target {10.0, 12.0, 14.0} が frame_idx {0, 120, 240} を選ぶ、(b) `fps_num=60000, fps_den=1001` (NTSC 59.94) で target {0.0, 10.0} が frame_idx {0, 599} (= `round(10 * 60000 / 1001)`) を選ぶ、両ケースを assert
3. **float fps fallback**: `source_fps=59.94` (float のみ) 経路で `Fraction(...).limit_denominator(10000)` 経由で rational に変換され、上記 (b) と同じ index 選択になることを確認
4. **frame 不足時 fallback**: emit frame 数 < target_idx の場合、該当 target が 255.0 で埋まることを確認 (#214 既存契約と整合)
5. **動的 VFR 検出**: (a) non-tail chunk で emit 不足が slack 超過 → `VideoProcessingError` raise / (b) tail chunk で同じ不足 → WARN のみで正常終了 / (c) slack 範囲内なら normal exit。slack = `max(expected * 0.01, ceil(source_fps * 0.1))`
6. **静的 VFR WARN**: probe で `r_frame_rate` vs `avg_frame_rate` 差 > 1% の動画を入力した場合 WARNING ログが出ること、ただし `VideoProcessingError` は raise されないこと
7. **env var rollback**: `ALLAGANEYE_DETECT_FPS_FILTER=1` 設定時に旧 fps filter cmd が生成されることを確認 (monkeypatch で局所的に set、global pollution 防止)
8. **CI fixture hygiene**: autouse fixture により default で env var が unset 状態であることを確認
9. **streaming read**: `subprocess.run(capture_output=True)` が使われていないことを implementation level で assert (mock 経由で Popen が呼ばれることを確認)
10. **vendor 別 command 構築**: NVIDIA cuvid / AMD d3d11va / Intel QSV それぞれで `hwdownload` prefix と新 `-vf` が共存することを確認

### §7.2 integration test (slow_detect marker)

1. **Class A 4 本**: `obs-20260116` / `obs-20260119` / `obs-20260127` / `obs-20260209` で `compare-baseline.py` exit 0
2. **Class A intermediate audit**: 上記 4 本で Pass 1 candidate / Pass 2 refined region の dump を旧 path (env var=1) と比較し、最終 projection が同じでも内部値の差が予想 ε 内であることを確認 (test 自体は warning report のみ、人間が PR review)
3. **Class B 1 本**: `obs-20260118` で新 baseline と一致 (PR 内で regenerate 後)
4. **Class C VTuber**: `vtuber-primary-ground-truth.json` の 5 試合 ±10s 内検出 + index 順序一致 (既存テスト reuse)
5. **legacy regression**: `TestNoResolutionCompat[20260116/118/119]` 全 PASS
6. **vendor 別 golden brightness** (unit ではなく integration): Idios 環境で CPU / NVIDIA / AMD それぞれで `obs-20260116` の特定 timestamp (黒/transition/lobby/normal の 4 種類) で `_probe_single_frame` 結果と ±2.0 以内で一致することを確認

### §7.3 manual / 実機検証 (Iron Law 6)

1. **GPU 実機検証 (Idios 環境)**: NVIDIA dGPU + AMD APU dual 環境で 5 baseline detect 完走、`compare-baseline.py` exit 0 (Class A) / regenerate diff approve (Class B)
2. **env var rollback 動作確認**: `ALLAGANEYE_DETECT_FPS_FILTER=1` で `20260118` を detect → Match 8 end が `6465.25` で残ることを確認
3. **PTS 検証 matrix 実施** (§4.4 参照): `scripts/validate-fps-retirement.py` を Idios 環境の CPU / NVIDIA / AMD で実行し、PR 本文に出力 TSV を貼る (exit 0 必須)。Intel は user に AskUserQuestion で別途依頼

### §7.4 perf budget gate

1. 5 baseline 合計 detect 時間 ≦ 36 分 (現状 34m43s + 8% margin)

## §8. Scope guard (Iron Law 3 防壁)

**touch する箇所**:

- `allaganeye/video/detector.py` (`_decode_chunk_cpu`, `_scan_cpu`, `detect_match_boundaries` signature)
- `allaganeye/video/gpu_detector.py` (`_decode_chunk`, `scan_gpu` signature)
- `allaganeye/video/probe.py` (rational fps `fps_num`/`fps_den` 公開 + 静的 VFR WARN: `r_frame_rate` vs `avg_frame_rate` 差比較、hard fail しない)
- `allaganeye/commands/split_matches.py` (`detect_kwargs["source_fps_num"]` / `["source_fps_den"]` / `["source_fps"]` 追加、`detect_kwargs` 構築箇所は `:745`)
- `tests/test_detector.py` (新 path + env var + frame_count test)
- `tests/test_gpu_detector.py` (新 path 確認)
- `tests/test_probe.py` (VFR detection test)
- `tests/conftest.py` (env var clean autouse fixture)
- `tests/baselines/v0.3.0/obs-20260118.metadata.json` (regenerate)
- `tests/baselines/v0.3.0/obs-20260118.split.json` (regenerate, sha256/size 再計算)
- `scripts/validate-fps-retirement.py` (新規、PTS 検証用 one-off)
- `docs/video-processing.md` §「ffmpeg fps filter の version 依存制約」 (root cause fix 反映)
- `docs/testing-guide.md` §「baseline drift の判定」 (#576 完了で fps filter 経由の drift は構造的に消滅)

**touch しない箇所** (Iron Law 3):

- `_probe_single_frame` (Pass 2 refinement, fps filter 非依存で既に正しい)
- `_probe_frame_rgb` / `_probe_frame_rgb_hires` (scorebar 用 hires probe)
- `audio/scan.py` / `audio/matcher.py` (Fanfare 昇格は別 path、§10 R9 で再有効化時の前提として記録)
- `scorebar.py` の classification logic
- `_legacy/*.json` baseline (TestNoResolutionCompat 用、scorebar OFF 経路)
- 他 Pillar 3 issue (#761, #670, #752, #762)

## §9. 受け入れ条件

### §9.1 実装 / 設計

- [ ] `_decode_chunk_cpu` / `_decode_chunk` の `-vf` から `fps=` 削除、`-fps_mode passthrough` 追加
- [ ] `-ss` を `-i` の後に移動 (output seek)
- [ ] `source_fps_num` / `source_fps_den` parameter を `detect_match_boundaries` / `_scan_cpu` / `scan_gpu` / `_decode_chunk_cpu` / `_decode_chunk` に追加、既存 `source_fps: float` は後方互換 fallback として残す
- [ ] `split_matches.py:745` `detect_kwargs["source_fps_num"]` / `["source_fps_den"]` / `["source_fps"]` 追加
- [ ] `probe.py` rational fps `fps_num`/`fps_den` を `ProbeResult` に公開 (既存 `fps: float` も維持)
- [ ] `probe.py` 静的 VFR WARN (`r_frame_rate` vs `avg_frame_rate` 差 > 1% で WARNING ログ、hard fail しない)
- [ ] `_sample_chunk_frames` 動的 VFR 検出 (slack = `max(expected * 0.01, ceil(fps * 0.1))` 超過時、tail chunk 除く)
- [ ] 実装は `subprocess.Popen` + streaming read (`subprocess.run(capture_output=True)` 禁止)
- [ ] env var `ALLAGANEYE_DETECT_FPS_FILTER=1` で旧 path に rollback 可能
- [ ] `conftest.py` autouse fixture で env var を default unset
- [ ] env var 廃止の v0.3.x roadmap 言及を CHANGELOG/docstring に追加

### §9.2 baseline 検証

- [ ] Class A 4 本 (`obs-20260116/20260119/20260127/20260209`) で `compare-baseline.py` exit 0
- [ ] Class A 4 本 + Class B 1 本 = 計 5 本で Pass 1/Pass 2 intermediate audit dump を PR 本文添付
- [ ] Class B 1 本 (`obs-20260118`) baseline を本 PR 内で regenerate、PR 本文に diff 明記 + `debug-brightness` CSV evidence 添付
- [ ] Class C (`vtuber-primary-ground-truth.json`) ±10s tolerance 内

### §9.3 evidence (実装中 one-off validation)

- [ ] `scripts/validate-fps-retirement.py` を本 PR 内に新規追加 (仕様は §4.4 参照)
- [ ] 上記スクリプトを Idios 環境の CPU / NVIDIA / AMD で実行し、TSV 出力を PR 本文 "## PTS validation evidence" section に貼付け (exit 0 必須)
- [ ] vendor 別 golden brightness 比較 (CPU / NVIDIA / AMD) を Idios 環境で実施し PR 本文添付
- [ ] Intel QSV の検証は AskUserQuestion で user に別途依頼するか、不可確定なら scope 外明記

### §9.4 regression / perf

- [ ] 5 baseline 合計 detect 時間 ≦ 36 分
- [ ] `TestNoResolutionCompat` 全 PASS
- [ ] env var rollback の動作確認 (Idios 実機)
- [ ] `docs/video-processing.md` / `docs/testing-guide.md` の fps filter 言及更新

## §10. リスク・open question

| ID | リスク | 緩和 |
| --- | --- | --- |
| R1 | Class A の matches/gaps projection が崩れる (極短 blackout が他 baseline にも潜在) | PR 内で 4 本を順に detect → diff を確認 → diff あれば Class B 扱いに昇格して baseline regenerate (本 PR scope に含める)。さらに Pass 1/Pass 2 intermediate audit dump で内部 stability も明示 |
| R2 | output seek の discard decode が長 GOP video で予想より遅い | perf budget 36 分 gate で検出、超過時は input seek + PTS metadata parse へ pivot (別 brainstorm) |
| R3 | 一部 hwaccel (Intel QSV 等) で hwdownload + scale=gray の挙動が ffmpeg 内部実装に依存し新パイプで decode 失敗 | vendor 別 unit test (command 構築) + Idios 環境での実機検証 (NVIDIA / AMD) + vendor 別 golden brightness 比較。Intel は user 側に検証可能な機材がない場合は AskUserQuestion で別途依頼 |
| R4 | env var rollback path の保守コストが膨らむ | v0.3.x で削除を明記、docstring に "transitional" マーク、`conftest.py` autouse fixture で CI pollution 防止 |
| R5 | brightness_callback (#569 GUI timeline) の値が新 path で変わる | callback の dict key (timestamp grid) は同一、value のみ正確化 = GUI timeline は意図通り改善方向 (旧 fps filter の drift で歪んでいた値が直る)。release notes と CHANGELOG に明記、user-visible metadata 変更として扱う |
| R6 (Codex review 由来) | env var CI contamination | `conftest.py` autouse fixture で default unset、legacy 専用 test だけ monkeypatch で局所 set、CI workflow も env var を export しない |
| R7 (Codex review 由来) | memory blowup if not streaming | `subprocess.Popen` + streaming read 必須化、`subprocess.run(capture_output=True)` 禁止を §9 受入条件と implementation review で gate |
| R8 (Codex review 由来) | trust chain for Class B baseline regeneration | Class B 新 baseline は per-frame probe evidence (`debug-brightness` CSV) を PR 本文に必須添付。new path が物理現実と一致することの独立証跡 |
| R9 (deferred) | audio promote false positive when audio frozen-by-default 解除時 | audio は現在 `audio/__init__.py` で frozen。再有効化時 (将来の別 issue) には audio-enabled regression run を 20260118 で実施することが前提条件として §1 Non-goals + R9 に記録 |
| R10 (deferred) | packet-level PTS variance による精密 VFR 検出 が本 PR では未実装 | aggregate `r_frame_rate` vs `avg_frame_rate` での静的 WARN + 動的 frame_count check の 2 段防御 (§2.2) が現状対応。packet PTS variance check は ffprobe `-show_packets` 経由で実装可能だが性能 cost と複雑性を考えて本 PR scope 外。VFR 入力で動的 check をすり抜けるケースが実観測されたら別 issue 起票 |

## §11. Process notes (adversarial review history)

本 spec は Codex CLI (`/codex:codex-rescue` subagent) による 4-round adversarial review を経て freeze に至った。design 段階の load-bearing 仮定を runtime evidence / test 仕様で裏付ける形に格上げするのが目的。

### Round-1 (full adversarial review)

- 結果: CONCERNS / proceed_with_amendments
- Findings:
  - F1 HIGH (output seeking guarantee): runtime PTS validation matrix が必要 → §4.4 PTS 検証 matrix 追加
  - F2 HIGH (float source_fps NTSC drift): VFR 検出 + frame_count sanity check が必要 → §2.2 / probe.py 拡張
  - F3 MED (hwdownload+scale=gray chain shape): vendor 別 golden brightness 比較が必要 → §7.2.16
  - F4 HIGH (Class A bit-exact overclaim): Pass 1/Pass 2 intermediate audit が必要 → §3 二段検証
  - F5 MED (vendor unit test overclaim): manual artifact に格下げ → §7.1 / §7.2 分離
  - F6 LOW (audio promote interaction): R9 として defer
  - Rnew1 (env var CI contamination): `conftest.py` autouse fixture → §6
  - Rnew2 (pipe data volume / memory): `subprocess.Popen` streaming 必須 → §2.2
  - Rnew3 (Class B trust chain): per-frame probe evidence 必須 → §3 / §9.2

### Round-2 (amendment verification)

- 結果: NEAR_READY / 3 must-fix
- Must-fix:
  - N1a (rational fps gap): float-only `source_fps` を canonical にしない → §2.2 / §2.3 rational fps propagation
  - N1b (VFR gate 過剰却下): aggregate diff の hard fail を WARN に変更、frame_count check で hard fail → §2.2 VFR 2 段防御
  - N2 (validate script 仕様不足): `scripts/validate-fps-retirement.py` の args/output/exit code 明示 → §4.4 script 仕様

### Round-3 (amendment verification)

- 結果: NEAR_READY / 2 PARTIAL
- 残存:
  - N1b/N3 (dynamic VFR tail chunk false positive): slack 式 + tail chunk WARN-only に変更 → §2.2 slack 式
  - N2 (script edge case 未定義): tail chunk SKIP / codec-vendor mismatch early reject / 短尺 clip exit 2 → §4.4 edge cases

### Round-4 (final verification)

- 結果: **READY**
- Drive-by check: clean
- N1b/N3: RESOLVED, N2: RESOLVED

---

review process artifact (Codex finding raw text) は本 spec とは別管理。Idios の判断で本 spec 完成後に廃棄、または PR 本文に history snippet として転記。
