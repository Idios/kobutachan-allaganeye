# minimap crop NVDEC decode 有効化 (#899) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** crop フィルタ有りの NVENC 経路で NVDEC decode (`-hwaccel cuda` auto-download) を有効化し、AV1 等の重いソースの decode を GPU に載せて CPU ボトルネックを解消する。

**Architecture:** `allaganeye/export/ffmpeg_runner.py` の argv 構築に filter 用 decode-only hwaccel を追加し、fallback を 3-tier ladder (`[NVDEC+NVENC]` → `[software decode+NVENC]` → `[libx264]`) に拡張する。export (filter 無し) は不変。

**Tech Stack:** Python (ffmpeg subprocess argv builder) / pytest。

## Global Constraints

- **spec**: `docs/superpowers/specs/2026-07-20-issue-899-nvdec-crop-decode-design.md` が SSoT。
- **export (filter 無し) 非接触**: filter 無し NVENC の zero-copy argv (`-hwaccel cuda -hwaccel_output_format cuda`) と 2-tier fallback (#791) を変更しない。変更は filter 有り経路のみ。
- **filter 用 decode-only hwaccel**: NVENC = `("-hwaccel", "cuda")` (`-hwaccel_output_format cuda` を付けない = auto-download)。QSV/AMF/LIBX264 = `()` (software、#762 保留)。
- **3-tier は filter 有り NVENC のみ**。tier2 = software decode + NVENC (silent、`fallback_cb` を呼ばない = 出力品質不変)。tier3 = libx264 (既存 `fallback_cb` 通知)。
- **pattern 分割は値同一**: 既存 `_GPU_ENCODER_FAILURE_PATTERNS[NVENC]` 14 個を encode-init 3 + decode-stage 11 に集合分割するのみ (文字列は不変)。
- **commit の Co-Authored-By は `Claude Fable 5 <noreply@anthropic.com>`** 固定。
- **released encode path**。PR は develop-0.3.0 ベース、#897 (GUI) とは別 PR。

---

## Task 1: filter 用 decode-only hwaccel + argv 分岐

**Files:**

- Modify: `allaganeye/export/ffmpeg_runner.py` (`_DECODE_HWACCEL_ARGS_FILTERED` 追加、`_build_ffmpeg_args` の decode hwaccel 分岐 + `force_software_decode` param)
- Test: `tests/test_ffmpeg_runner.py` (既存があれば追記、無ければ新規)

**Interfaces:**

- Consumes: 既存 `_DECODE_HWACCEL_ARGS` / `H264Encoder` / `_build_ffmpeg_args(ffmpeg, video, start, end, output, codec, encoder, video_filter=None)`。
- Produces: `_build_ffmpeg_args(..., video_filter=None, *, force_software_decode: bool = False)`。filter 有り NVENC (force_software_decode=False) は `-hwaccel cuda` (no `-hwaccel_output_format`) を `-i` 前に挿入。force_software_decode=True は decode hwaccel を一切挿入しない。`_DECODE_HWACCEL_ARGS_FILTERED[H264Encoder]`。

- [ ] **Step 1: Write the failing tests**

`tests/test_ffmpeg_runner.py` に追加 (既存 import に合わせる):

```python
from pathlib import Path
from allaganeye.export.ffmpeg_runner import _build_ffmpeg_args
from allaganeye.export.encoder import H264Encoder


def _args(**kw):
    return _build_ffmpeg_args(
        "ffmpeg", Path("in.mkv"), 10.0, 20.0, Path("out.mp4"),
        "h264", kw.pop("encoder", H264Encoder.NVENC), kw.pop("video_filter", None),
        **kw,
    )


def test_filtered_nvenc_uses_decode_only_hwaccel():
    args = _args(video_filter="crop=100:100:0:0")
    # decode-only: -hwaccel cuda BUT NOT -hwaccel_output_format cuda
    assert "-hwaccel" in args
    i = args.index("-hwaccel")
    assert args[i + 1] == "cuda"
    assert "-hwaccel_output_format" not in args
    # filter still applied, before -c:v
    assert "-vf" in args and "crop=100:100:0:0" in args
    assert args.index("-vf") < args.index("-c:v")
    # hwaccel is before -i
    assert args.index("-hwaccel") < args.index("-i")


def test_filtered_nvenc_force_software_decode_omits_hwaccel():
    args = _args(video_filter="crop=100:100:0:0", force_software_decode=True)
    assert "-hwaccel" not in args
    assert "-vf" in args  # filter still applied


def test_unfiltered_nvenc_zerocopy_unchanged():
    args = _args(video_filter=None)
    # export path: full zero-copy NVDEC (regression pin)
    assert "-hwaccel" in args and "cuda" in args
    assert "-hwaccel_output_format" in args
    assert args[args.index("-hwaccel_output_format") + 1] == "cuda"


def test_filtered_libx264_no_hwaccel():
    args = _args(encoder=H264Encoder.LIBX264, video_filter="crop=100:100:0:0")
    assert "-hwaccel" not in args
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_ffmpeg_runner.py -k "filtered or zerocopy" -v`
Expected: FAIL (`_DECODE_HWACCEL_ARGS_FILTERED` 未定義 / `force_software_decode` 未対応 / filtered NVENC が現状 hwaccel 無し)。

- [ ] **Step 3: Add filtered mapping**

`allaganeye/export/ffmpeg_runner.py`、`_DECODE_HWACCEL_ARGS` 定義の直後に追加:

```python
# #899: video_filter 有り (minimap crop 等) 用の decode-only hwaccel。
# -hwaccel_output_format cuda を付けない = NVDEC decode 後に auto-download し
# CPU crop filter に渡せる。GPU decode + CPU crop + NVENC encode。
_DECODE_HWACCEL_ARGS_FILTERED: dict[H264Encoder, tuple[str, ...]] = {
    H264Encoder.NVENC: ("-hwaccel", "cuda"),  # decode-only, auto-download
    H264Encoder.QSV: (),  # #762 保留 (software decode 継続)
    H264Encoder.AMF: (),  # #762 保留
    H264Encoder.LIBX264: (),
}
```

- [ ] **Step 4: Add `force_software_decode` + branch to `_build_ffmpeg_args`**

signature を変更 (`video_filter` の後に keyword-only を追加):

```python
def _build_ffmpeg_args(
    ffmpeg: str,
    video: Path,
    start: float,
    end: float,
    output: Path,
    codec: str,
    encoder: H264Encoder,
    video_filter: str | None = None,
    *,
    force_software_decode: bool = False,
) -> list[str]:
```

docstring に 1 行追記:

```text
    #899: video_filter 有りの NVENC は zero-copy でなく `-hwaccel cuda` 単独
    (auto-download) で GPU decode + CPU crop。force_software_decode=True は
    decode hwaccel を挿入しない (3-tier ladder の tier2 = software decode + NVENC)。
```

decode hwaccel 挿入部 (現行 `if codec != "copy" and video_filter is None:`) を置換:

```python
    if codec != "copy" and not force_software_decode:
        if video_filter is None:
            args.extend(_DECODE_HWACCEL_ARGS[encoder])           # zero-copy (export、不変)
        else:
            args.extend(_DECODE_HWACCEL_ARGS_FILTERED[encoder])  # #899: decode-only
```

- [ ] **Step 5: Run to verify pass**

Run: `pytest tests/test_ffmpeg_runner.py -k "filtered or zerocopy" -v`
Expected: PASS (4 tests)。

- [ ] **Step 6: Guard existing tests + lint**

Run: `pytest tests/test_ffmpeg_runner.py -q && ruff check allaganeye/export/ffmpeg_runner.py tests/test_ffmpeg_runner.py && ruff format --check allaganeye/export/ffmpeg_runner.py tests/test_ffmpeg_runner.py`
Expected: 既存 argv テストも PASS (export 非破壊)。lint clean。

- [ ] **Step 7: Commit**

```bash
git add allaganeye/export/ffmpeg_runner.py tests/test_ffmpeg_runner.py
git commit -m "feat(#899): decode-only hwaccel for filtered NVENC crop path (Refs #899)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 2: NVENC pattern 分割 + decode 段判定 helper

**Files:**

- Modify: `allaganeye/export/ffmpeg_runner.py` (`_GPU_ENCODER_FAILURE_PATTERNS[NVENC]` を 2 サブセット合成に、`_nvenc_decode_stage_failure` 追加)
- Test: `tests/test_ffmpeg_runner.py`

**Interfaces:**

- Consumes: 既存 `_GPU_ENCODER_FAILURE_PATTERNS` / `is_gpu_encoder_failure(stderr, encoder)`。
- Produces: `_NVENC_ENCODE_STAGE_PATTERNS` (3) / `_NVENC_DECODE_STAGE_PATTERNS` (11) / `_nvenc_decode_stage_failure(stderr_text: str) -> bool`。`_GPU_ENCODER_FAILURE_PATTERNS[NVENC]` は 2 サブセットの結合 (値不変)。

- [ ] **Step 1: Write the failing tests**

```python
from allaganeye.export.ffmpeg_runner import (
    _nvenc_decode_stage_failure,
    is_gpu_encoder_failure,
)
from allaganeye.export.encoder import H264Encoder


def test_nvenc_decode_stage_failure_true_for_nvdec_patterns():
    assert _nvenc_decode_stage_failure("... cuvidCreateDecoder failed ...")
    assert _nvenc_decode_stage_failure("... hwaccel transfer data failed ...")
    assert _nvenc_decode_stage_failure("... Cannot load libcuda ...")


def test_nvenc_decode_stage_failure_false_for_encode_init():
    assert not _nvenc_decode_stage_failure("... No NVENC capable devices found ...")
    assert not _nvenc_decode_stage_failure("... OpenEncodeSessionEx failed ...")


def test_is_gpu_encoder_failure_backward_compat():
    # 合成集合なので encode-init も decode-stage も True (既存契約不変)
    assert is_gpu_encoder_failure("No NVENC capable devices found", H264Encoder.NVENC)
    assert is_gpu_encoder_failure("cuvidCreateDecoder failed", H264Encoder.NVENC)
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_ffmpeg_runner.py -k "decode_stage or backward_compat" -v`
Expected: FAIL (`_nvenc_decode_stage_failure` 未定義)。

- [ ] **Step 3: Split patterns + add helper**

`_GPU_ENCODER_FAILURE_PATTERNS` の直前に 2 サブセットを定義し、NVENC entry を結合に置換 (文字列は現行と完全同一):

```python
# #899: NVENC の失敗 pattern を 2 段に分割 (値は #791 の 14 個と同一)。
# encode-init: NVENC encoder が使えない -> libx264 直行 (tier3)。
_NVENC_ENCODE_STAGE_PATTERNS: tuple[str, ...] = (
    "no nvenc capable devices found",
    "cannot load cuda driver",
    "openencodesessionex failed",
)
# decode-stage: NVDEC decode が失敗 (`-hwaccel cuda`) -> software decode + NVENC (tier2)。
_NVENC_DECODE_STAGE_PATTERNS: tuple[str, ...] = (
    "could not dynamically load cuda",
    "cannot load libcuda",
    "device creation failed",
    "device setup failed for decoder",
    "no device available for decoder",
    "failed to create cuda context",
    "cannot init cuda",
    "cuvidcreatedecoder",
    "hwaccel transfer data failed",
    "cuvid: failed",
    "could not allocate hardware frames",
)
```

`_GPU_ENCODER_FAILURE_PATTERNS` の `H264Encoder.NVENC:` の値 (14 個のタプル) を次に置換:

```python
    H264Encoder.NVENC: _NVENC_ENCODE_STAGE_PATTERNS + _NVENC_DECODE_STAGE_PATTERNS,
```

`is_gpu_encoder_failure` の直後に helper を追加:

```python
def _nvenc_decode_stage_failure(stderr_text: str) -> bool:
    """True iff stderr は NVDEC decode 段 (`-hwaccel cuda`) の失敗を示す。

    #899: filter 有り NVENC の tier1 (NVDEC+NVENC) 失敗を、decode 段
    (-> tier2 software decode + NVENC) か encode 段 (-> tier3 libx264) かに
    振り分けるために使う。
    """
    text = stderr_text.lower()
    return any(p in text for p in _NVENC_DECODE_STAGE_PATTERNS)
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_ffmpeg_runner.py -k "decode_stage or backward_compat" -v`
Expected: PASS。

- [ ] **Step 5: Guard + lint**

Run: `pytest tests/test_ffmpeg_runner.py -q && ruff check allaganeye/export/ffmpeg_runner.py`
Expected: PASS (既存 fallback 判定不変)、lint clean。

- [ ] **Step 6: Commit**

```bash
git add allaganeye/export/ffmpeg_runner.py tests/test_ffmpeg_runner.py
git commit -m "feat(#899): split NVENC failure patterns into decode/encode stages (Refs #899)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 3: run_export_attempt の 3-tier ladder

**Files:**

- Modify: `allaganeye/export/ffmpeg_runner.py` (`run_export_attempt` の retry ロジック)
- Test: `tests/test_ffmpeg_runner.py`

**Interfaces:**

- Consumes: `_build_ffmpeg_args(..., force_software_decode=...)` (Task 1) / `_nvenc_decode_stage_failure` / `is_gpu_encoder_failure` (Task 2) / 既存 `_run_single_attempt` / `_AttemptOutcome` / `ExportResult` / `fallback_cb`。
- Produces: filter 有り NVENC の tier1 失敗が decode 段なら tier2 (software decode + NVENC、`fallback_cb` は呼ばない) で 1 回 retry。tier2 成功で `encoder_used="h264_nvenc", fallback_from=None`。tier2 失敗 or tier1 encode 段は既存 tier3 (libx264) へ。

- [ ] **Step 1: Write the failing tests**

`_run_single_attempt` を monkeypatch して各 attempt の argv と outcome を制御する。既存テストの mock 流儀に合わせる (無ければ以下で新規)。

```python
import threading
from allaganeye.export import ffmpeg_runner as fr
from allaganeye.export.ffmpeg_runner import run_export_attempt, _AttemptOutcome
from allaganeye.export.encoder import H264Encoder


def _run(monkeypatch, tmp_path, outcomes):
    """outcomes: list of (returncode, stderr). 各 attempt に順に返す。captured に argv 記録。"""
    captured = []
    it = iter(outcomes)

    def fake_attempt(args, duration, progress_cb, cancel_event):
        captured.append(args)
        rc, err = next(it)
        return _AttemptOutcome(returncode=rc, stderr_tail=err)

    monkeypatch.setattr(fr, "_run_single_attempt", fake_attempt)
    monkeypatch.setattr(fr, "find_ffmpeg", lambda: "ffmpeg")
    res = run_export_attempt(
        tmp_path / "in.mkv", 10.0, 20.0, tmp_path / "out.mp4", "h264",
        H264Encoder.NVENC, progress_cb=lambda *a: None, fallback_cb=None,
        cancel_event=threading.Event(), video_filter="crop=100:100:0:0",
    )
    return res, captured


def test_tier1_decode_failure_retries_software_decode_nvenc(monkeypatch, tmp_path):
    # tier1 (NVDEC) decode 失敗 -> tier2 (software decode + NVENC) 成功
    res, captured = _run(monkeypatch, tmp_path, [
        (1, "cuvidCreateDecoder failed"),  # tier1
        (0, ""),                            # tier2
    ])
    assert len(captured) == 2
    assert "-hwaccel" in captured[0]                 # tier1 = NVDEC
    assert "-hwaccel" not in captured[1]             # tier2 = software decode
    assert "-c:v" in captured[1] and "h264_nvenc" in captured[1]  # still NVENC encode
    assert res.encoder_used == "h264_nvenc"
    assert res.fallback_from is None


def test_tier1_encode_failure_skips_to_libx264(monkeypatch, tmp_path):
    # tier1 encode-init 失敗 -> tier2 skip -> tier3 libx264
    res, captured = _run(monkeypatch, tmp_path, [
        (1, "No NVENC capable devices found"),  # tier1
        (0, ""),                                 # tier3 (libx264)
    ])
    assert len(captured) == 2
    assert "h264_nvenc" not in captured[1] and "libx264" in captured[1]
    assert res.encoder_used == "libx264"
    assert res.fallback_from == "h264_nvenc"


def test_tier2_failure_falls_to_libx264(monkeypatch, tmp_path):
    # tier1 decode 失敗 -> tier2 (software+NVENC) も失敗 -> tier3 libx264
    res, captured = _run(monkeypatch, tmp_path, [
        (1, "hwaccel transfer data failed"),  # tier1 decode
        (1, "No NVENC capable devices found"),  # tier2 encode fail
        (0, ""),                                # tier3 libx264
    ])
    assert len(captured) == 3
    assert "-hwaccel" in captured[0]
    assert "-hwaccel" not in captured[1] and "h264_nvenc" in captured[1]
    assert "libx264" in captured[2]
    assert res.encoder_used == "libx264"
    assert res.fallback_from == "h264_nvenc"
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_ffmpeg_runner.py -k "tier1 or tier2" -v`
Expected: FAIL (現状 2-tier なので tier2 が挿入されず captured / encoder_used が不一致)。

- [ ] **Step 3: Insert tier2 before the libx264 block**

`run_export_attempt` の `if outcome.returncode == 0: return ...` (1st attempt 成功) の直後、既存の「GPU encoder init failure -> libx264 retry」ブロックの**直前**に tier2 を挿入:

```python
    # #899 tier2: filter 有り NVENC の tier1 (NVDEC decode) が decode 段で失敗
    # した場合のみ software decode + NVENC で 1 回 retry する (encode は GPU 維持)。
    # tier2 は出力品質が変わらないため fallback_cb は呼ばない (silent decode retry)。
    # tier2 が失敗したら outcome を上書きして下の libx264 (tier3) ブロックへ流す。
    if (
        codec == "h264"
        and encoder == H264Encoder.NVENC
        and video_filter is not None
        and _nvenc_decode_stage_failure(outcome.stderr_tail)
    ):
        tier2_args = _build_ffmpeg_args(
            ffmpeg, video, start, end, output, codec, encoder, video_filter,
            force_software_decode=True,
        )
        outcome = _run_single_attempt(tier2_args, duration, progress_cb, cancel_event)
        if cancel_event.is_set():
            if not output_pre_existed:
                output.unlink(missing_ok=True)
            raise ExportError(kind="cancelled", message="export cancelled by user")
        if outcome.returncode == 0:
            return ExportResult(
                match_index=-1,
                output_path=output,
                duration_ms=int((time.monotonic() - started) * 1000),
                encoder_used=encoder.value,
                fallback_from=None,
            )
        # tier2 も失敗 -> outcome は tier2 の失敗。下の libx264 ブロックが拾う。
```

(既存の `if (codec == "h264" and encoder != LIBX264 and is_gpu_encoder_failure(outcome.stderr_tail, encoder)):` ブロックはそのまま。tier1 encode 段失敗 → tier2 skip → このブロックが tier1 outcome で発火。tier2 失敗 → このブロックが tier2 outcome で発火。いずれも libx264 = tier3。)

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_ffmpeg_runner.py -k "tier1 or tier2" -v`
Expected: PASS (3 tests)。

- [ ] **Step 5: Full suite + lint + type**

Run: `pytest tests/test_ffmpeg_runner.py -q && ruff check allaganeye/export/ffmpeg_runner.py && pyright allaganeye/export/ffmpeg_runner.py`
Expected: PASS。既存 export fallback テスト (filter 無し 2-tier) 不変。

- [ ] **Step 6: Commit**

```bash
git add allaganeye/export/ffmpeg_runner.py tests/test_ffmpeg_runner.py
git commit -m "feat(#899): 3-tier fallback ladder for filtered NVENC (NVDEC->sw decode->libx264) (Refs #899)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 4: docs

**Files:**

- Modify: `CLAUDE.md` (§GPU モードの NVDEC 記述)
- Modify: `docs/cli-spec.md` (minimap crop の decode hwaccel 挙動、あれば)

**Interfaces:** N/A (doc only)。

- [ ] **Step 1: CLAUDE.md**

§GPU モードの「NVENC 選択時は NVDEC zero-copy decode 経路 …」の段落に、filter 有り (minimap crop) の挙動を 1-2 文追記:

```markdown
- minimap crop 等 `-vf crop` フィルタ有りの NVENC 経路は zero-copy が使えない (GPU frame を CPU crop に渡せない) ため、#899 で `-hwaccel cuda` 単独 (auto-download) で NVDEC decode + CPU crop + NVENC encode する。fallback は 3-tier: NVDEC decode 段失敗 → software decode + NVENC (silent) → NVENC encode 失敗 → libx264。`_DECODE_HWACCEL_ARGS_FILTERED` / `_nvenc_decode_stage_failure` (`ffmpeg_runner.py`)。
```

- [ ] **Step 2: cli-spec (該当あれば)**

`grep -n 'minimap\|crop\|NVENC\|hwaccel' docs/cli-spec.md` で minimap crop の encode 記述を確認。あれば decode の GPU 化を 1 行注記、無ければ skip (PR 本文に「cli-spec に該当記述なし」と明記)。

- [ ] **Step 3: markdownlint**

Run: `bash scripts/check-markdownlint.sh`
Expected: PASS。

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md docs/
git commit -m "doc(#899): NVDEC decode for filtered NVENC crop path (Refs #899)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## 完了ゲート (PR 作成前)

- [ ] `pytest tests/test_ffmpeg_runner.py -v` 全 PASS
- [ ] `ruff check . && ruff format --check . && pyright`
- [ ] `pytest -q` (full suite、encode path 変更のため回帰確認)
- [ ] `bash scripts/check-markdownlint.sh`
- [ ] **実機 benchmark (Iron Law 6、Idios)**: RTX 5090 + AV1 ソース (`E:\royalstraightflesh\videos\20260116\2026-01-16 22-12-57.mkv`) で minimap crop の per-match wall-time を before (develop-0.3.0) / after (本ブランチ) 比較。GPU util 上昇・CPU 低下・wall-time 短縮を nvidia-smi + 時間計測で確認。`-hwaccel cuda` 強制失敗時の tier2 fallback も実機確認。detached Start-Process 手順 (`feedback_long_gpu_job_detached_execution`)。
- [ ] Iron Law 6 Pre-flight (Step 0 重複 PR check → base develop-0.3.0 同期 → Codex adversarial-review: 3-tier routing / export 非回帰 / fallback 網羅 focus)
- [ ] PR 本文に before/after benchmark 数値 + 3-tier 契約 + export 非接触の根拠を明記

## Self-Review (plan 執筆後)

- **Spec coverage**: §3.1 core = Task 1 / §3.2 fallback (pattern split + ladder) = Task 2 + Task 3 / §4 docs = Task 4 / §6 benchmark = 完了ゲート。全 § に task 対応。
- **Placeholder scan**: 各 code step に実コード記載。Task 4 Step 2 は grep 手順明示。
- **Type consistency**: `_build_ffmpeg_args(..., force_software_decode=bool)` (Task 1 定義 → Task 3 使用) / `_nvenc_decode_stage_failure` (Task 2 定義 → Task 3 使用) / `_DECODE_HWACCEL_ARGS_FILTERED` / pattern サブセット名を全 task で一貫。
