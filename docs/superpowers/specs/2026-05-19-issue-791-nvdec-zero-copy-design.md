# NVDEC zero-copy decode for export path (#791)

- 日付: 2026-05-19
- 起票元: issue [#791](https://github.com/Idios/kobutachan-allaganeye/issues/791) [task] L3: export 経路に NVDEC zero-copy decode 追加 (#761 派生)
- 前提 PR: [#787](https://github.com/Idios/kobutachan-allaganeye/pull/787) feat(export): NVENC parallel export Python-first shared core (#761) (squash merged to develop-0.3.0 `d55ae03`)
- 関連 issue: [#762](https://github.com/Idios/kobutachan-allaganeye/issues/762) (multi-vendor encoder pool、本 spec の AMF/QSV decode hwaccel mapping を活用)、[#765](https://github.com/Idios/kobutachan-allaganeye/issues/765) (detect 側 NVDEC saturation、本 spec とは独立)
- 関連 spec: [docs/superpowers/specs/2026-05-18-nvenc-parallel-export-design.md](2026-05-18-nvenc-parallel-export-design.md) (#761 NVENC parallel export 基盤)
- 関連 docs: [docs/l2-workflow.md](../../l2-workflow.md) (Iron Law 6 Pre-flight、Self-Test Report 規約)、[docs/refactor-pattern.md](../../refactor-pattern.md)

## 1. 背景と動機

PR [#787](https://github.com/Idios/kobutachan-allaganeye/pull/787) で N=3 並列 NVENC export が完成。RTX 5090 の 3 物理 video encode engine が driver load-balance で全稼働 (Idios 環境 2026-05-19 計測: 各 engine ~58% 稼働、`PowerShell Get-Counter '\GPU Engine(*engtype_VideoEncode*)\Utilization Percentage'`)。一方:

- ffmpeg input decode は CPU 側で処理 ([`allaganeye/export/ffmpeg_runner.py::_build_ffmpeg_args`](../../../allaganeye/export/ffmpeg_runner.py))
- Task Manager: Video Decode (NVDEC) 0%、Video Encode ~58% 平均
- 2 時間動画 8 試合 export ETA 10:54 ≈ 12x realtime aggregate、theoretical max (3 engine × 12x ≈ 36x) の ~33% 止まり
- #761 受け入れ条件「Video Encode ~90%+ 持続」は **feeding bottleneck** で未達 (encoder 余力ではない)

CPU decode → memcpy → GPU encode の中継が支配的。`-hwaccel cuda -hwaccel_output_format cuda` を input flag として与えると ffmpeg は NVDEC で decode し、出力フォーマットを CUDA memory に保つ → 後段の `h264_nvenc` が同じ CUDA buffer から read することで **GPU memory 内 zero-copy** が成立する。

CUDA SDK のインストール不要 (BtbN LGPL ffmpeg に NVDEC build 同梱、RTX 5090 driver で動作)。Code 変更は `_build_ffmpeg_args` への 2-3 行追加レベル。

## 2. Goals と non-goals

### Goals

- **G1**: NVENC encoder 選択時、ffmpeg input decode が NVDEC に dispatch される (`-hwaccel cuda -hwaccel_output_format cuda` 付与)
- **G2**: NVENC のみ wire し、QSV / AMF mapping は `()` (no-op) で key 保持する。実際の wire は #762 (multi-vendor encoder pool) phase で実機検証込みで行う。理由: Codex adversarial-review (#791 Iron Law 6 Pre-flight Step 5) で「Intel/AMD 未検証変更」HIGH finding が出たため、Idios 判断で scope を NVENC に限定。
- **G3**: libx264 fallback path には decode hwaccel を**適用しない** (GPU→CPU memcpy が逆コストになるため)
- **G4**: `codec="copy"` path には適用しない (decode/encode しないため不要)
- **G5**: 既存の wire protocol / progress event / cancel / libx264 fallback retry を**無修正で維持**
- **G6**: 実機検証 (Iron Law 6): RTX 5090 で N=3 並列 H.264 export → Task Manager Video Encode ~90%+ 持続 + Video Decode 非ゼロ (~50-90% 想定) を 30 秒以上目視

### Non-goals

- **N1**: multi-vendor encoder pool 本体 ([#762](https://github.com/Idios/kobutachan-allaganeye/issues/762)) の実装は対象外。decode hwaccel mapping は wire しておくが、AMF/QSV slot を実際に作る orchestrator 変更は #762 で
- **N2**: AMD / Intel 環境での実機検証は対象外 (Idios 環境に該当 GPU なし)。AMF/QSV の decode hwaccel 引数は ffmpeg 公式 doc に基づき wire し、実機検証は #762 implementation phase で行う
- **N3**: detect 側 (`gpu_detector.py`) への NVDEC 適用は対象外 (`gpu_detector.py` は既に長寿命 ffmpeg + `-hwaccel auto` で動作、計測は #765 で記録済)
- **N4**: 未対応 codec の `-hwaccel cuda` silent CPU fallback は ffmpeg 既定挙動を信頼。argv が正しく構築されることを unit test で確認するに留め、各 codec 別 NVDEC 実機検証は対象外
- **N5**: CHANGELOG 追記は対象外 (`/release` Step で v0.3.0 release 時に対応)
- **N6**: QSV / AMF decode hwaccel の本 PR 内 wire (Codex Finding 1 を受け #762 へ deferred)

## 3. アーキテクチャ

`_build_ffmpeg_args` 内で **encoder → decode hwaccel args** の static mapping を導入し、`codec == "h264"` かつ `encoder != LIBX264` のときのみ `-i {video}` の**前**に挿入する。

```text
ffmpeg -hide_banner -loglevel info -progress pipe:2 -y
       [-hwaccel <vendor> [-hwaccel_output_format <fmt>]]   ← NEW (input flag)
       -ss <start> -to <end>
       -i <video>
       -c:v <encoder> <quality_args> -c:a copy
       <output>
```

ffmpeg の `-hwaccel` は **per-input flag** であり `-i` の前に置く必要がある。これは ffmpeg 公式 doc および `_build_ffmpeg_args` 既存の `-ss` / `-to` の位置 (input flag) と整合。

### 3.1 Mapping

`allaganeye/export/ffmpeg_runner.py` に追加:

```python
_DECODE_HWACCEL_ARGS: dict[H264Encoder, tuple[str, ...]] = {
    H264Encoder.NVENC: ("-hwaccel", "cuda", "-hwaccel_output_format", "cuda"),
    H264Encoder.QSV: (),  # deferred to #762
    H264Encoder.AMF: (),  # deferred to #762
    H264Encoder.LIBX264: (),
}
```

- **NVENC**: `cuda` decode + `cuda` output format -> NVDEC frame が CUDA memory に留まり NVENC へ zero-copy
- **QSV**: `()` (no-op) -- deferred to #762. Real wire: `("-hwaccel", "qsv", "-hwaccel_output_format", "qsv")`, requires Intel iGPU real-machine verification
- **AMF**: `()` (no-op) -- deferred to #762. Real wire: `("-hwaccel", "d3d11va")`, requires AMD dGPU real-machine verification
- **LIBX264**: 空 tuple -> hwaccel 引数なし (CPU decode + CPU encode のまま)

**未登録 enum 追加時の risk**: `_DECODE_HWACCEL_ARGS[encoder]` は direct subscript (`.get(encoder, ())` ではない) のため、`H264Encoder` enum に新規メンバーを追加し `_DECODE_HWACCEL_ARGS` への登録を忘れた場合は merge-time test failure (KeyError) で検出される。これは意図的設計: silently miss を防ぐため。将来の encoder 追加 PR (例: AV1) は本 mapping にも entry を追加すること (空 tuple `()` でも OK)。

### 3.2 挿入条件

```python
def _build_ffmpeg_args(...) -> list[str]:
    args: list[str] = [ffmpeg, "-hide_banner", "-loglevel", "info",
                       "-progress", "pipe:2", "-y"]
    if codec != "copy":
        args.extend(_DECODE_HWACCEL_ARGS[encoder])   # ← NEW
    args.extend(["-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(video)])
    if codec == "copy":
        args.extend(["-c", "copy"])
    else:
        args.extend(["-c:v", encoder.value])
        args.extend(list(encoder.quality_args()))
        args.extend(["-c:a", "copy"])
    args.append(str(output))
    return args
```

| codec | encoder | hwaccel 挿入? | 結果 |
| --- | --- | --- | --- |
| `"h264"` | NVENC | YES (cuda + cuda) | NVDEC->NVENC zero-copy |
| `"h264"` | QSV | NO (empty tuple, deferred to #762) | CPU decode + QSV encode |
| `"h264"` | AMF | NO (empty tuple, deferred to #762) | CPU decode + AMF encode |
| `"h264"` | LIBX264 | NO (empty tuple) | CPU decode + CPU encode |
| `"copy"` | (任意) | NO (codec guard) | stream copy のみ |

### 3.3 libx264 fallback retry path との関係

`run_export_attempt` は NVENC 初期化失敗時に `_build_ffmpeg_args(..., encoder=H264Encoder.LIBX264)` で retry argv を作る ([`ffmpeg_runner.py:198`](../../../allaganeye/export/ffmpeg_runner.py#L198))。LIBX264 の mapping は `()` なので **自動的に hwaccel なし** になる。条件分岐の追加不要 = 既存 fallback ロジックを 1 行も触らない。

これは「libx264 fallback path には NVDEC を適用しない」という issue 要件 (GPU→CPU memcpy が逆に遅くなる回避) を mapping table の自然な結果として満たす。

## 4. テスト計画 (TDD)

`tests/test_export_ffmpeg_runner.py` に追加。`_build_ffmpeg_args` は module-private (`_` prefix) だが、既存 test 同様に from-import して直接呼ぶ (test only)。

### 4.1 unit test (red → green の順で追加)

| # | Test 名 | Assert |
| --- | --- | --- |
| T1 | `test_build_args_nvenc_inserts_hwaccel_cuda_before_input` | argv に `["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]` が連続で含まれ、その index が `-i` の index より小さい |
| T2 | `test_build_args_qsv_has_no_hwaccel_deferred_to_762` | QSV mapping は no-op: argv に `-hwaccel` / `-hwaccel_output_format` なし (#762 で wire、Codex adversarial-review #791 + Idios 判断) |
| T3 | `test_build_args_amf_has_no_hwaccel_deferred_to_762` | AMF mapping は no-op: argv に `-hwaccel` / `-hwaccel_output_format` なし (#762 で wire、Codex adversarial-review #791 + Idios 判断) |
| T4 | `test_build_args_libx264_has_no_hwaccel` | `-hwaccel` 文字列が argv に存在しないこと (`"-hwaccel" not in args`) |
| T5 | `test_build_args_copy_codec_has_no_hwaccel_even_with_nvenc_encoder` | `codec="copy"` + encoder=NVENC で argv に `-hwaccel` なし、`-c copy` あり |
| T6 | `test_build_args_hwaccel_positioned_before_ss_to` | `-hwaccel` 引数群が `-ss` / `-to` / `-i` のいずれよりも前 (ffmpeg 仕様準拠) |
| T7 | `test_nvenc_nvdec_decode_failure_*` (3 tests) | NVDEC decode-stage failure patterns (`cuvidcreatedecoder` / `failed to create cuda context` / `hwaccel transfer data failed`) が `is_gpu_encoder_failure` で True を返す (Codex Finding 2 対応) |

### 4.2 integration test (run_export_attempt 経路、subprocess mock)

| # | Test 名 | Assert |
| --- | --- | --- |
| I1 | `test_run_export_attempt_nvenc_argv_includes_hwaccel_cuda` | Popen 1st call (`mock_popen.call_args_list[0]`) の argv に `-hwaccel cuda` が含まれる |
| I2 | `test_run_export_attempt_libx264_fallback_argv_lacks_hwaccel` | NVENC init fail -> libx264 retry シナリオで、Popen 2nd call (`mock_popen.call_args_list[1]`) の argv に `-hwaccel` なし |
| I3 | `test_run_export_attempt_nvdec_decode_failure_triggers_libx264_retry` | NVDEC decode failure (`cuvidCreateDecoder failed`) stderr -> libx264 retry argv lacks `-hwaccel` (Codex Finding 2 対応) |

### 4.3 既存 test の保護

既存の `test_run_export_attempt_nvenc_success` / `test_run_export_attempt_nvenc_init_fail_falls_back_to_libx264` / `test_run_export_attempt_cancel_event_kills_ffmpeg` / `test_run_export_attempt_both_attempts_fail` は **無修正で pass** する (argv 追加のみで stdin/stdout/stderr の扱い不変)。

### 4.4 ruff / pyright / pytest 全 pass

- `ruff check .` / `ruff format --check .` / `pyright` / `pytest` を PR 作成前 Pre-flight で全 pass
- GUI 側変更なし (Python のみ) のため `npm run lint` / `typecheck` / `test` / `build` / `cargo check` は不要 (該当 path 未 touch)

## 5. Iron Law 6 実機検証

Idios 環境 (Windows 11 + RTX 5090 + BtbN LGPL ffmpeg) で以下を `AskUserQuestion` で依頼:

### 5.1 検証手順

1. 同一 metadata.json (#761 計測で使用した 2 時間動画 8 試合のもの) で N=3 並列 H.264 export 実行
2. 実行中 30 秒以上 Task Manager `Performance > GPU 0` で目視:
   - `Video Encode` engine 利用率 ~90%+ 持続 (各 engine ではなく aggregate)
   - `Video Decode` engine 利用率が **非ゼロ** (~50-90% 想定、CPU decode 時の 0% からの上昇)
3. `PowerShell Get-Counter '\GPU Engine(*engtype_VideoDecode*)\Utilization Percentage'` で per-engine NVDEC 利用率を補助確認
4. 完了時刻と ETA を記録。#761 baseline (2 時間動画 8 試合 ≈ 10:54) と比較し、1.5-2x 短縮 (5-7 分台) を目標
5. fallback 経路の sanity check: NVENC 初期化を意図的に失敗させる手段がない場合は省略 (既存 test でカバー)

### 5.2 期待結果

| Metric | #761 baseline | 本 PR target |
| --- | --- | --- |
| Video Encode 平均 | ~58% (3 engine) | ~90%+ |
| Video Decode 平均 | 0% | 非ゼロ (~50-90%) |
| 8 試合 export 実時間 | 10:54 | 5-7 分台 |
| Aggregate throughput | ~12x realtime | ~20-30x realtime |

実測値が target を下回った場合 (例: Video Encode が ~70% 止まり) は別の bottleneck (disk I/O / metadata parse 等) を疑い、本 PR は merge せず追加調査 issue 起票で対応する。

### 5.3 AMD/Intel 検証

本 PR ではスコープ外。Codex adversarial-review (§6.5 Finding 1) + Idios 判断で AMF/QSV mapping は `()` (no-op) とした。実際の wire と実機検証は **#762 implementation phase** に持ち越し。PR 本文の Self-Test Report で「AMD/Intel decode hwaccel は #762 へ deferred」として記載。

## 6. リスクと対応

| Risk | 対応 |
| --- | --- |
| 入力動画の codec が NVDEC 未対応 (例: 特殊な MKV) | ffmpeg は `-hwaccel cuda` 指定でも未対応 codec で silent CPU fallback。動作は維持されるが zero-copy 効果は失われる。issue 仕様通り「silent fallback を unit test で verify」は **argv が正しく構築されること** までを担保 (各 codec 別 NVDEC 実機検証は対象外、N4) |
| NVDEC engine 数 (1) < NVENC engine 数 (3) で feeding bottleneck 継続 | RTX 5090 は NVDEC 2 engine + NVENC 3 engine。N=3 並列で NVDEC 飽和の可能性あり。目視確認で Video Decode が 100% 近く貼り付いていれば feeding 律速の余地が残るが、CPU decode→memcpy より高速なので net positive。target 未達時は §5.2 の通り追加調査 |
| `-hwaccel_output_format cuda` 指定により h264_nvenc が CUDA buffer を受け取れない GPU/driver | RTX 5090 + BtbN LGPL ffmpeg + 最新 driver では動作確認可能。古い driver では `-hwaccel_output_format` を解釈できない可能性があるが、Idios 環境 (本 PR の Iron Law 6 検証ターゲット) は最新 driver を維持しているため検証可能。Idios 以外のユーザー環境での古い driver 互換性は本 PR スコープ外、回帰時は別 issue で対応 |
| argv の順序ミスで `-hwaccel` が `-i` の後に置かれる (input flag 規則違反) | T1-T3 + T6 で `-i` / `-ss` / `-to` より前にあることを assert |
| NVDEC decode-stage failure が libx264 fallback を trigger しない | `_GPU_ENCODER_FAILURE_PATTERNS[NVENC]` に NVDEC decode stderr patterns を追加 (§6.5 Finding 2 対応)。T7 / I3 でカバー |

## 6.5 Codex adversarial-review findings (#791 Iron Law 6 Pre-flight Step 5)

Codex review verdict: `needs-attention` (2 HIGH).

### Finding 1: QSV/AMF mapping unverified for Intel/AMD users

Codex argued that wiring QSV/AMF mapping changes the ffmpeg argv for Intel/AMD users without Idios environment validation, creating regression risk.

**Idios decision**: Limit this PR to NVENC. Set QSV/AMF mapping entries to `()`. Real wire happens in #762 with multi-vendor encoder pool + AMD/Intel real-machine verification.

### Finding 2: libx264 fallback only matches encoder-init failure patterns

Codex pointed out that `-hwaccel cuda` injection adds a new failure surface (NVDEC decode stage). The pre-existing `is_gpu_encoder_failure` patterns only match encoder-init stderr (e.g. `no nvenc capable devices found`). Decode-stage failures (e.g. `cuvidCreateDecoder failed`) bypass the libx264 retry.

**Idios decision**: Extend `is_gpu_encoder_failure[NVENC]` with NVDEC decode-stage patterns in this PR.

Patterns added (11 NVDEC pattern を 3 layer 構成、Round 2 で Layer 1/2 拡充):

- **Layer 1** (CUDA dynamic library load / device init、最早期):
  - `could not dynamically load cuda`
  - `cannot load libcuda`
- **Layer 2** (CUDA device creation / decoder device setup):
  - `device creation failed`
  - `device setup failed for decoder`
  - `no device available for decoder`
  - `failed to create cuda context`
  - `cannot init cuda`
- **Layer 3** (decoder creation / frame transfer、最後段):
  - `cuvidcreatedecoder` (cuvidCreateDecoder failed)
  - `hwaccel transfer data failed`
  - `cuvid: failed`
  - `could not allocate hardware frames`

### Finding 2.1: CUDA device-setup layer 追加 (Codex Round 2 提起)

Round 1 で Layer 3 (decoder creation / frame transfer) のみカバーしたが、Codex Round 2 で **Layer 1 (CUDA dynamic load) + Layer 2 (device creation/setup) も新しい failure surface** と指摘 (`-hwaccel cuda` 注入で発生する早期失敗が encoder-init より前段で起きる可能性)。

**Idios decision**: 本 PR で Layer 1+2 patterns 5 件 (`could not dynamically load cuda` / `cannot load libcuda` / `device creation failed` / `device setup failed for decoder` / `no device available for decoder`) を追加し、3 layer 構成として整理 (上記 list 参照)。対応 commit `80c77c2`、対応 unit test 4 件 (`test_nvenc_nvdec_cuda_dynamic_load_failure` / `test_nvenc_nvdec_device_creation_failure` / `test_nvenc_nvdec_device_setup_failure` / `test_nvenc_nvdec_no_device_available`)。

**実機 stderr corpus との突合**: 本 PR の pattern set は Codex 3 round の review で coverage を validated したが、`feedback_ffmpeg_qsv_stderr_pattern.md` memory 教訓 (「実機 stderr で確認しないと検出漏れ」) は NVENC 側にも同 surface あり。Iron Law 6 trigger (Idios RTX 5090) で actual stderr corpus 取得後、必要なら #791 派生 issue として pattern 追加 / regex 化 等の継続検討。

Coverage: new unit tests (T7 series) for `is_gpu_encoder_failure` + integration test (I3) for full `run_export_attempt` retry path with NVDEC decode failure stderr.

## 7. スコープ境界

- ✅ 本 PR: NVENC decode hwaccel mapping + NVDEC fallback pattern 拡張 + unit test (T1-T7 / I1-I3) + RTX 5090 実機検証
- ❌ 本 PR外 (#762 担当): multi-vendor encoder pool 本体 (slot list の `[Nvenc; 3, Amf; 1]` 化、`enumerate_h264_encoders` 拡張)
- ❌ 本 PR外 (#762 担当): AMF/QSV decode hwaccel の wire と実機検証 (Codex Finding 1 + Idios 判断で deferred、§6.5)
- ❌ 本 PR外 (#765 担当): detect 側 NVDEC saturation 計測
- ❌ 本 PR外 (`/release` 担当): CHANGELOG 追記

## 8. 受け入れ条件

issue [#791](https://github.com/Idios/kobutachan-allaganeye/issues/791) `## 確認項目 / 作業項目` に対応:

- [ ] `allaganeye/export/ffmpeg_runner.py::_build_ffmpeg_args` に NVENC encoder 時のみ `-hwaccel cuda -hwaccel_output_format cuda` を追加 (input file の前) → §3.2
- [ ] codec 別 NVDEC 対応確認 (silent CPU fallback の unit test) → T1-T6 (argv 構築の正しさを assert、各 codec 別 NVDEC 実機検証は N4 で対象外)
- [ ] libx264 fallback path への適用回避 → §3.3 (mapping 自然な結果)
- [ ] #762 multi-vendor 対応統合 (AMF=`-hwaccel d3d11va`, QSV=`-hwaccel qsv`) -- deferred to #762 per Codex Finding 1 + Idios decision (§6.5)
- [ ] テスト: NVDEC 適用時の wire protocol / progress event / cancel が無修正で動作 → §4.3 既存 test 保護
- [ ] 実機検証 (Iron Law 6): RTX 5090 で N=3 並列 H.264 export → §5.1 / §5.2
- [ ] 計測比較: pre/post の ETA / 実時間記録 → §5.2 (CHANGELOG 追記は N5 で対象外)
- [ ] codec=copy への適用回避 → §3.2 codec guard + T5

## 9. PR 構成

- 単一 PR、squash merge to `develop-0.3.0`
- branch 名: `claude/mystifying-poincare-51645d` (現在の worktree、auto-generated)
- PR 本文: §8 受け入れ条件を逐条引用 + Self-Test Report (machine-verified `[x]` + machine-unverifiable plain bullet 規約、[`docs/l2-workflow.md`](../../l2-workflow.md) §「Self-Test Report 規約」)
- Closes / Fixes / Resolves キーワード**禁止** (Iron Law 4)、マージ後 `/close-issue` で手動クローズ

## 10. 進行フロー

1. 本 spec を `docs/superpowers/specs/2026-05-19-issue-791-nvdec-zero-copy-design.md` に commit
2. `/superpowers:writing-plans` で実装 plan を生成 (test-first / TDD)
3. plan 実行 → ruff / pyright / pytest pass → Iron Law 6 Pre-flight (Step 0-5) → PR 作成
4. `/iterate-review <PR#>` で review-fix ループ
5. merge → `/close-issue 791` で受け入れ条件再検証 + クローズ
