# NVDEC zero-copy decode for export path Implementation Plan (#791)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ffmpeg input decode を NVENC encoder path で NVDEC に dispatch し (`-hwaccel cuda -hwaccel_output_format cuda` を `-i` の前に conditional 追加)、decode → encode を GPU memory 内で zero-copy 完結させて per-NVENC engine utilization を ~58% → ~90%+ へ向上させる。QSV / AMF にも同等の mapping を wire し #762 multi-vendor 実装時に活用する。

**Architecture:** `_build_ffmpeg_args` 内に encoder→decode hwaccel args の static dict (`_DECODE_HWACCEL_ARGS`) を導入。`codec == "h264"` のとき mapping を `-i {video}` の前に挿入し、`codec == "copy"` および `encoder == LIBX264` は空 tuple で自然に除外する。既存の wire protocol / progress event / cancel / libx264 fallback retry は無修正。

**Tech Stack:** Python 3.13 / pytest / unittest.mock / ffmpeg (BtbN LGPL build) / RTX 5090 (Iron Law 6 検証)

**Spec:** [docs/superpowers/specs/2026-05-19-issue-791-nvdec-zero-copy-design.md](../specs/2026-05-19-issue-791-nvdec-zero-copy-design.md)

---

## File Structure

**Modified:**

- [`allaganeye/export/ffmpeg_runner.py`](../../../allaganeye/export/ffmpeg_runner.py) — module-level `_DECODE_HWACCEL_ARGS` dict + `_build_ffmpeg_args` の 1 行追加

**Modified (tests):**

- [`tests/test_export_ffmpeg_runner.py`](../../../tests/test_export_ffmpeg_runner.py) — unit test 6 件 + integration test 2 件追加

**No new files.** 既存 2 ファイルへの追加のみ。

---

## Task 1: TDD T1 — NVENC mapping 導入

**Files:**

- Modify: `allaganeye/export/ffmpeg_runner.py`
- Test: `tests/test_export_ffmpeg_runner.py`

- [ ] **Step 1: Write the failing test (T1: NVENC inserts cuda hwaccel before -i)**

`tests/test_export_ffmpeg_runner.py` の末尾に追加:

```python
# --- _build_ffmpeg_args: decode hwaccel (#791) ---

from allaganeye.export.ffmpeg_runner import _build_ffmpeg_args


def test_build_args_nvenc_inserts_hwaccel_cuda_before_input(tmp_path: Path):
    args = _build_ffmpeg_args(
        ffmpeg="ffmpeg",
        video=tmp_path / "in.mp4",
        start=0.0,
        end=10.0,
        output=tmp_path / "out.mp4",
        codec="h264",
        encoder=H264Encoder.NVENC,
    )
    # -hwaccel cuda -hwaccel_output_format cuda が連続で含まれる
    idx_hwaccel = args.index("-hwaccel")
    assert args[idx_hwaccel : idx_hwaccel + 4] == [
        "-hwaccel",
        "cuda",
        "-hwaccel_output_format",
        "cuda",
    ]
    # -i より前に置かれている (ffmpeg input flag 規則)
    idx_i = args.index("-i")
    assert idx_hwaccel < idx_i
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_export_ffmpeg_runner.py::test_build_args_nvenc_inserts_hwaccel_cuda_before_input -v
```

Expected: FAIL — `ValueError: '-hwaccel' is not in list` (現在の `_build_ffmpeg_args` は `-hwaccel` を出力しない)

- [ ] **Step 3: Write minimal implementation**

`allaganeye/export/ffmpeg_runner.py` を編集。

3a. Import 直後 (line 18 付近、`_GPU_ENCODER_FAILURE_PATTERNS` の前) に mapping を追加:

```python
_DECODE_HWACCEL_ARGS: dict[H264Encoder, tuple[str, ...]] = {
    # #791: encoder→decode hwaccel mapping。NVENC は NVDEC → NVENC zero-copy
    # (CUDA memory)。QSV/AMF は #762 multi-vendor 実装時に活用。LIBX264 は
    # 空 tuple で hwaccel なし (GPU→CPU memcpy 回避)。
    H264Encoder.NVENC: ("-hwaccel", "cuda", "-hwaccel_output_format", "cuda"),
    H264Encoder.QSV: ("-hwaccel", "qsv", "-hwaccel_output_format", "qsv"),
    H264Encoder.AMF: ("-hwaccel", "d3d11va"),
    H264Encoder.LIBX264: (),
}
```

> **Note (Codex Round 1 Finding 1 + Idios decision)**: 上記 mapping は初期 plan。Round 1 review で Codex adversarial-review が「Intel/AMD 未検証変更」として HIGH 指摘 → Idios 判断で QSV/AMF を `()` no-op に変更 (実 wire は #762)。最終的な mapping と判断記録は spec §3.1 / §6.5 を参照。

3b. `_build_ffmpeg_args` (line 113-146) の本体を以下に置換:

```python
def _build_ffmpeg_args(
    ffmpeg: str,
    video: Path,
    start: float,
    end: float,
    output: Path,
    codec: str,
    encoder: H264Encoder,
) -> list[str]:
    """Construct the ffmpeg argv list. Mirrors pre-#761 build_ffmpeg_args in gui/src-tauri/src/lib.rs (see #591/#761).

    #791: codec=="h264" のとき encoder に対応する decode hwaccel 引数を
    `-i` の前に挿入する。codec=="copy" / encoder==LIBX264 は除外。
    """
    args: list[str] = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "info",
        "-progress",
        "pipe:2",
        "-y",
    ]
    if codec != "copy":
        args.extend(_DECODE_HWACCEL_ARGS[encoder])
    args.extend(
        [
            "-ss",
            f"{start:.3f}",
            "-to",
            f"{end:.3f}",
            "-i",
            str(video),
        ]
    )
    if codec == "copy":
        args.extend(["-c", "copy"])
    else:
        args.extend(["-c:v", encoder.value])
        args.extend(list(encoder.quality_args()))
        args.extend(["-c:a", "copy"])
    args.append(str(output))
    return args
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_export_ffmpeg_runner.py::test_build_args_nvenc_inserts_hwaccel_cuda_before_input -v
```

Expected: PASS

- [ ] **Step 5: Run full test file to verify no regression**

```bash
pytest tests/test_export_ffmpeg_runner.py -v
```

Expected: 全 test PASS (既存 8 件 + 新規 1 件 = 9 件)

- [ ] **Step 6: Commit**

```bash
git add allaganeye/export/ffmpeg_runner.py tests/test_export_ffmpeg_runner.py
git commit -m "feat(export): #791 NVENC decode hwaccel mapping (T1)

Add _DECODE_HWACCEL_ARGS dict and insert decode hwaccel args before
-i in _build_ffmpeg_args when codec is h264. NVENC entry routes input
decode to NVDEC with CUDA output format for zero-copy NVDEC->NVENC."
```

---

## Task 2: TDD T2/T3 — QSV / AMF mapping 確認

**Files:**

- Test: `tests/test_export_ffmpeg_runner.py`

- [ ] **Step 1: Write the failing test (T2: QSV)**

`tests/test_export_ffmpeg_runner.py` に追加:

```python
def test_build_args_qsv_inserts_hwaccel_qsv_before_input(tmp_path: Path):
    args = _build_ffmpeg_args(
        ffmpeg="ffmpeg",
        video=tmp_path / "in.mp4",
        start=0.0,
        end=10.0,
        output=tmp_path / "out.mp4",
        codec="h264",
        encoder=H264Encoder.QSV,
    )
    idx_hwaccel = args.index("-hwaccel")
    assert args[idx_hwaccel : idx_hwaccel + 4] == [
        "-hwaccel",
        "qsv",
        "-hwaccel_output_format",
        "qsv",
    ]
    assert idx_hwaccel < args.index("-i")
```

- [ ] **Step 2: Run test to verify it passes (already passing — mapping covers all 4 encoders)**

```bash
pytest tests/test_export_ffmpeg_runner.py::test_build_args_qsv_inserts_hwaccel_qsv_before_input -v
```

Expected: PASS (Task 1 で QSV mapping も既に追加済のため。regression guard として保持)

- [ ] **Step 3: Write the failing test (T3: AMF)**

```python
def test_build_args_amf_inserts_hwaccel_d3d11va_before_input(tmp_path: Path):
    args = _build_ffmpeg_args(
        ffmpeg="ffmpeg",
        video=tmp_path / "in.mp4",
        start=0.0,
        end=10.0,
        output=tmp_path / "out.mp4",
        codec="h264",
        encoder=H264Encoder.AMF,
    )
    idx_hwaccel = args.index("-hwaccel")
    # AMF は -hwaccel_output_format 指定なし (issue 仕様)
    assert args[idx_hwaccel : idx_hwaccel + 2] == ["-hwaccel", "d3d11va"]
    assert "-hwaccel_output_format" not in args
    assert idx_hwaccel < args.index("-i")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_export_ffmpeg_runner.py::test_build_args_amf_inserts_hwaccel_d3d11va_before_input -v
```

Expected: PASS (Task 1 で AMF mapping も追加済)

- [ ] **Step 5: Commit**

```bash
git add tests/test_export_ffmpeg_runner.py
git commit -m "test(export): #791 QSV / AMF decode hwaccel regression tests (T2/T3)

Regression guards for QSV (-hwaccel qsv -hwaccel_output_format qsv) and
AMF (-hwaccel d3d11va, no output_format per issue spec) mapping entries
added in Task 1. Real-world verification deferred to #762."
```

---

## Task 3: TDD T4/T5 — LIBX264 / copy mode exclusion

**Files:**

- Test: `tests/test_export_ffmpeg_runner.py`

- [ ] **Step 1: Write test (T4: LIBX264 has no hwaccel)**

```python
def test_build_args_libx264_has_no_hwaccel(tmp_path: Path):
    args = _build_ffmpeg_args(
        ffmpeg="ffmpeg",
        video=tmp_path / "in.mp4",
        start=0.0,
        end=10.0,
        output=tmp_path / "out.mp4",
        codec="h264",
        encoder=H264Encoder.LIBX264,
    )
    # GPU->CPU memcpy 回避: libx264 path には decode hwaccel を付けない
    assert "-hwaccel" not in args
    assert "-hwaccel_output_format" not in args
    # libx264 自体は使われる
    assert "libx264" in args
```

- [ ] **Step 2: Run test to verify it passes**

```bash
pytest tests/test_export_ffmpeg_runner.py::test_build_args_libx264_has_no_hwaccel -v
```

Expected: PASS (`_DECODE_HWACCEL_ARGS[LIBX264] = ()` で空 tuple、extend で何も追加されない)

- [ ] **Step 3: Write test (T5: copy codec excludes hwaccel even with NVENC encoder)**

```python
def test_build_args_copy_codec_has_no_hwaccel_even_with_nvenc_encoder(
    tmp_path: Path,
):
    """codec='copy' は decode/encode しないため、encoder が NVENC でも hwaccel 不要."""
    args = _build_ffmpeg_args(
        ffmpeg="ffmpeg",
        video=tmp_path / "in.mp4",
        start=0.0,
        end=10.0,
        output=tmp_path / "out.mp4",
        codec="copy",
        encoder=H264Encoder.NVENC,
    )
    assert "-hwaccel" not in args
    assert "-hwaccel_output_format" not in args
    # -c copy が指定されている
    idx_c = args.index("-c")
    assert args[idx_c + 1] == "copy"
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_export_ffmpeg_runner.py::test_build_args_copy_codec_has_no_hwaccel_even_with_nvenc_encoder -v
```

Expected: PASS (`if codec != "copy"` guard で extend skip)

- [ ] **Step 5: Commit**

```bash
git add tests/test_export_ffmpeg_runner.py
git commit -m "test(export): #791 libx264 / copy mode exclusion regression tests (T4/T5)

Regression guards: libx264 mapping returns empty tuple (no GPU->CPU
memcpy in CPU encode path) and codec=copy guard skips hwaccel insertion
even when encoder=NVENC (stream copy bypasses decode/encode)."
```

---

## Task 4: TDD T6 — Position before -ss / -to / -i

**Files:**

- Test: `tests/test_export_ffmpeg_runner.py`

- [ ] **Step 1: Write test (T6: hwaccel before all input flags)**

```python
def test_build_args_hwaccel_positioned_before_ss_to_i(tmp_path: Path):
    """ffmpeg の -hwaccel は input flag であり -ss/-to/-i より前に置く必要がある."""
    args = _build_ffmpeg_args(
        ffmpeg="ffmpeg",
        video=tmp_path / "in.mp4",
        start=1.5,
        end=12.5,
        output=tmp_path / "out.mp4",
        codec="h264",
        encoder=H264Encoder.NVENC,
    )
    idx_hwaccel = args.index("-hwaccel")
    idx_ss = args.index("-ss")
    idx_to = args.index("-to")
    idx_i = args.index("-i")
    assert idx_hwaccel < idx_ss
    assert idx_hwaccel < idx_to
    assert idx_hwaccel < idx_i
```

- [ ] **Step 2: Run test to verify it passes**

```bash
pytest tests/test_export_ffmpeg_runner.py::test_build_args_hwaccel_positioned_before_ss_to_i -v
```

Expected: PASS (実装で hwaccel extend を `-ss/-to/-i` extend より前に置いている)

- [ ] **Step 3: Commit**

```bash
git add tests/test_export_ffmpeg_runner.py
git commit -m "test(export): #791 hwaccel positioned before -ss/-to/-i (T6)

ffmpeg input flag ordering invariant: -hwaccel must precede -ss/-to/-i
(per ffmpeg docs, hwaccel applies to the next input). Regression guard
against accidental reordering."
```

---

## Task 5: Integration tests — Popen call argv assertion

**Files:**

- Test: `tests/test_export_ffmpeg_runner.py`

- [ ] **Step 1: Write integration test (I1: NVENC 1st attempt argv includes -hwaccel cuda)**

```python
@patch("allaganeye.export.ffmpeg_runner.subprocess.Popen")
def test_run_export_attempt_nvenc_argv_includes_hwaccel_cuda(
    mock_popen: MagicMock, tmp_path: Path
):
    """run_export_attempt → Popen に渡る argv に -hwaccel cuda が含まれる."""
    proc = MagicMock()
    proc.stderr = MagicMock()
    proc.stderr.readline = MagicMock(
        side_effect=[
            b"out_time_ms=1000000\n",
            b"progress=end\n",
            b"",
        ]
    )
    proc.wait = MagicMock(return_value=0)
    proc.returncode = 0
    mock_popen.return_value = proc

    run_export_attempt(
        video=tmp_path / "in.mp4",
        start=0.0,
        end=10.0,
        output=tmp_path / "out.mp4",
        codec="h264",
        encoder=H264Encoder.NVENC,
        progress_cb=lambda p, s: None,
        fallback_cb=None,
        cancel_event=threading.Event(),
    )
    # Popen の 1st positional arg (argv list) を取得
    first_call_args = mock_popen.call_args_list[0]
    argv = first_call_args.args[0]
    assert "-hwaccel" in argv
    idx = argv.index("-hwaccel")
    assert argv[idx : idx + 4] == [
        "-hwaccel",
        "cuda",
        "-hwaccel_output_format",
        "cuda",
    ]
```

- [ ] **Step 2: Run test to verify it passes**

```bash
pytest tests/test_export_ffmpeg_runner.py::test_run_export_attempt_nvenc_argv_includes_hwaccel_cuda -v
```

Expected: PASS

- [ ] **Step 3: Write integration test (I2: libx264 fallback retry argv lacks hwaccel)**

```python
@patch("allaganeye.export.ffmpeg_runner.subprocess.Popen")
def test_run_export_attempt_libx264_fallback_argv_lacks_hwaccel(
    mock_popen: MagicMock, tmp_path: Path
):
    """NVENC init fail → libx264 retry の 2nd Popen call argv に -hwaccel なし.

    libx264 path で -hwaccel を付けると GPU→CPU memcpy が逆コストになるため、
    fallback retry では確実に decode hwaccel を外すことを担保する.
    """
    proc_nvenc = MagicMock()
    proc_nvenc.stderr = MagicMock()
    proc_nvenc.stderr.readline = MagicMock(
        side_effect=[
            b"[h264_nvenc @ 0xfff] No NVENC capable devices found\n",
            b"",
        ]
    )
    proc_nvenc.wait = MagicMock(return_value=1)
    proc_nvenc.returncode = 1

    proc_libx264 = MagicMock()
    proc_libx264.stderr = MagicMock()
    proc_libx264.stderr.readline = MagicMock(
        side_effect=[
            b"out_time_ms=1000000\n",
            b"progress=end\n",
            b"",
        ]
    )
    proc_libx264.wait = MagicMock(return_value=0)
    proc_libx264.returncode = 0

    mock_popen.side_effect = [proc_nvenc, proc_libx264]

    run_export_attempt(
        video=tmp_path / "in.mp4",
        start=0.0,
        end=10.0,
        output=tmp_path / "out.mp4",
        codec="h264",
        encoder=H264Encoder.NVENC,
        progress_cb=lambda p, s: None,
        fallback_cb=lambda f, t, m: None,
        cancel_event=threading.Event(),
    )
    # 1st call (NVENC) は hwaccel あり、2nd call (libx264 retry) は hwaccel なし
    first_argv = mock_popen.call_args_list[0].args[0]
    second_argv = mock_popen.call_args_list[1].args[0]
    assert "-hwaccel" in first_argv
    assert "-hwaccel" not in second_argv
    assert "libx264" in second_argv
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_export_ffmpeg_runner.py::test_run_export_attempt_libx264_fallback_argv_lacks_hwaccel -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_export_ffmpeg_runner.py
git commit -m "test(export): #791 integration tests for Popen argv (I1/I2)

I1: run_export_attempt -> Popen 1st call argv contains
'-hwaccel cuda -hwaccel_output_format cuda' for NVENC encoder.
I2: NVENC init fail -> libx264 retry 2nd Popen call argv lacks
'-hwaccel' (GPU->CPU memcpy avoidance in CPU encode fallback)."
```

---

## Task 6: 全 export test 回帰確認 + ruff / pyright

**Files:** なし (verification only)

- [ ] **Step 1: Run full export test suite**

```bash
pytest tests/test_export_ffmpeg_runner.py tests/test_export_pool.py tests/test_export_cli.py tests/test_export_encoder.py tests/test_export_nvenc_probe.py tests/test_export_schema.py tests/test_export_wire_protocol.py -v
```

Expected: 全 PASS。既存 test (8 件 in ffmpeg_runner.py + 他 6 ファイル) と新規 8 件 (T1-T6 + I1-I2) が全て通る。

- [ ] **Step 2: Run full test suite**

```bash
pytest
```

Expected: PASS (slow marker 除く)

- [ ] **Step 3: Lint check**

```bash
ruff check . && ruff format --check .
```

Expected: All checks passed.

- [ ] **Step 4: Type check**

```bash
pyright
```

Expected: 0 errors, 0 warnings. (`_DECODE_HWACCEL_ARGS` は `dict[H264Encoder, tuple[str, ...]]` で完全に型付け済)

- [ ] **Step 5: 失敗時の対応**

- ruff format 違反 → `ruff format .` で自動修正後 commit
- pyright 型エラー → 該当箇所を修正 (mapping access が `KeyError` 可能性ありと指摘されたら enum を全 case 網羅していることを mypy/pyright に示すため `assert encoder in _DECODE_HWACCEL_ARGS` を追加 or `.get(encoder, ())` に変更)
- pytest fail → 該当 test の Expected と実 output を比較し原因特定。GUI 側は touch していないので GUI test は影響なし

- [ ] **Step 6: Commit (if formatting / type fixes were needed)**

```bash
git add -A
git commit -m "chore(export): #791 ruff format / pyright fixes"
```

Format / type が pass している場合は本 commit 不要。

---

## Task 7: Iron Law 6 Pre-flight + PR 作成

**Files:** なし (verification + PR creation)

- [ ] **Step 0: Hard gate — 重複 PR 検出 (<1s)**

```bash
gh pr list --search "791" --state open --json number,title,headRefName
```

Expected: `[]` (issue#791 用 open PR なし)。何か返ってきたら作業中断、既存 PR との関係を確認。

- [ ] **Step 1: Base branch 同期**

```bash
git fetch origin develop-0.3.0
```

- [ ] **Step 2: 取り込み未済 commit 確認**

```bash
git log HEAD..origin/develop-0.3.0 --oneline
```

Expected: 空 (Pre-flight 開始時に base 最新)。commit が出てきたら merge / rebase を判断:

- 自動 merge 可能 → `git merge origin/develop-0.3.0`
- conflict → 手動解決
- conflict なくても touched files が交差する場合 → Step 3 で再確認

- [ ] **Step 3: Touched files 交差判定**

```bash
git log HEAD..origin/develop-0.3.0 --name-only --pretty=format: | sort -u | grep -E "(allaganeye/export/ffmpeg_runner\.py|tests/test_export_ffmpeg_runner\.py)" || echo "no overlap"
```

Expected: `no overlap`。overlap があれば変更内容を確認し、必要なら merge 後に test 再実行。

- [ ] **Step 4: 並行 PR 重複再確認**

```bash
gh pr list --search "791" --state all --json number,title,state
gh pr list --search "NVDEC" --state open --json number,title,state
gh pr list --search "hwaccel cuda" --state open --json number,title,state
```

Expected: state=open で issue#791 関連の他 PR なし。

- [ ] **Step 5: Codex adversarial-review**

```text
/codex:adversarial-review focus="Iron Law 3 scope creep / NVDEC encoding boundary / GPU fallback path correctness / past PR same-issue root cause"
```

Expected: Codex が verdict (PROCEED / PROCEED-WITH-FIXES / HALT) + findings list を返す。mandatory fix があれば反映後 Step 5 を再実行。

- [ ] **Step 6: PR push**

```bash
git push -u origin claude/mystifying-poincare-51645d
```

- [ ] **Step 7: PR 作成**

PR 本文を以下の構成で作成:

```bash
gh pr create --base develop-0.3.0 --title "feat(export): #791 NVDEC zero-copy decode for NVENC path" --body "$(cat <<'EOF'
## 期待値 (issue #791)

ffmpeg input decode が NVDEC に dispatch される (`-hwaccel cuda -hwaccel_output_format cuda` を NVENC encoder path に conditional 追加)。decode → encode が GPU memory 内で zero-copy 完結し、per-NVENC engine utilization が ~58% → ~90%+ に到達、実効スループットが #761 の 2x → 理想 3x に近づく。

## 現状 → 修正内容

- 修正前: `_build_ffmpeg_args` は `-hwaccel` を出力せず CPU decode → GPU encode の memcpy 中継
- 修正後: encoder→decode hwaccel args の static mapping (`_DECODE_HWACCEL_ARGS`) を導入し、`codec=="h264"` のとき encoder に応じて `-i` の前に挿入
  - NVENC → `-hwaccel cuda -hwaccel_output_format cuda` (NVDEC→NVENC zero-copy)
  - QSV → `-hwaccel qsv -hwaccel_output_format qsv` (#762 で活用)
  - AMF → `-hwaccel d3d11va` (#762 で活用)
  - LIBX264 → 空 tuple (GPU→CPU memcpy 回避)
- libx264 fallback retry path は mapping table の自然な結果として hwaccel なし、既存 fallback ロジック無修正
- codec=copy path は codec guard で hwaccel skip、既存挙動維持

## 受け入れ条件 (issue#791 §確認項目 / 作業項目 逐条)

- [x] `_build_ffmpeg_args` に NVENC encoder 時のみ `-hwaccel cuda -hwaccel_output_format cuda` を追加 (input file の前) — Task 1 / T1 (test pass) / `_build_ffmpeg_args` modified
- [x] codec 別 NVDEC 対応確認 — T1/T2/T3 で argv 構築正確性を assert。silent CPU fallback は ffmpeg 既定挙動 (spec §6 N4、各 codec 実機検証は対象外)
- [x] libx264 fallback path への適用回避 — T4 + I2 で hwaccel 不在を assert (mapping 自然な結果)
- [x] #762 multi-vendor 対応統合 — QSV / AMF mapping を wire (T2/T3)、実機検証は #762
- [x] テスト: NVDEC 適用時の wire protocol / progress event / cancel が無修正で動作 — 既存 test 4 件 (success / fallback / cancel / both fail) が無修正で pass
- [ ] 実機検証 (Iron Law 6): RTX 5090 で N=3 並列 H.264 export → Task Manager Video Encode ~90%+ 持続 + Video Decode 非ゼロ (~50-90% 想定) を 30 秒以上目視
- [ ] 計測比較: pre/post の ETA / 実時間記録 (CHANGELOG 追記は `/release` Step で v0.3.0 時に対応)
- [x] codec=copy への適用回避 — T5 で hwaccel 不在を assert

## Self-Test Report

machine-verified (automated):

- [x] `pytest tests/test_export_ffmpeg_runner.py -v` — 8 新規 + 8 既存 = 16 件全 PASS
- [x] `pytest` — slow marker 除外で全 PASS
- [x] `ruff check . && ruff format --check .` — clean
- [x] `pyright` — 0 errors

machine-unverifiable (実機 / 別環境):

- RTX 5090 N=3 並列 export の Video Encode ~90%+ 持続 (Iron Law 6 trigger、Idios 環境で実施依頼)
- Video Decode 非ゼロ (~50-90%) の Task Manager 目視確認
- AMD / Intel decode hwaccel の動作確認 (該当環境なし、#762 implementation phase で検証)

## 関連

- 元 issue: #791
- 前提 PR: #787 (#761 NVENC parallel export)
- 関連 issue: #762 (multi-vendor encoder pool、AMF/QSV decode hwaccel 実機検証担当)
- spec: [docs/superpowers/specs/2026-05-19-issue-791-nvdec-zero-copy-design.md](docs/superpowers/specs/2026-05-19-issue-791-nvdec-zero-copy-design.md)
- plan: [docs/superpowers/plans/2026-05-19-issue-791-nvdec-zero-copy-plan.md](docs/superpowers/plans/2026-05-19-issue-791-nvdec-zero-copy-plan.md)

## Iron Law 遵守

- Iron Law 3 (NO SCOPE CREEP): mapping 4 encoder + tests + spec + plan 以外の変更なし。multi-vendor encoder pool 本体 (#762) は非含
- Iron Law 4 (NO Closes/Fixes/Resolves): 本 PR にキーワードなし、merge 後 `/close-issue 791` で手動クローズ予定
- Iron Law 6 (Pre-flight): Step 0-5 完了済、Idios 実機検証は別途依頼

session-id: mystifying-poincare-51645d
EOF
)"
```

- [ ] **Step 8: PR 番号を控える**

```bash
gh pr view --json number,url
```

PR# を記録 (以降の `/iterate-review <PR#>` で使用)。

---

## Task 8: 実機検証依頼 (Iron Law 6) + iterate-review

**Files:** なし (user verification)

- [ ] **Step 1: Idios に実機検証を `AskUserQuestion` で依頼**

Question: "RTX 5090 環境で N=3 並列 H.264 export 実機検証をお願いできますか? 検証手順 (spec §5.1) は以下:

1. 同一 metadata.json で N=3 並列 H.264 export 実行
2. 30 秒以上 Task Manager `Performance > GPU 0` で目視:
   - Video Encode ~90%+ 持続
   - Video Decode 非ゼロ (~50-90% 想定)
3. 完了時刻記録 (#761 baseline 10:54 比 1.5-2x 短縮 = 5-7 分台が target)
4. `PowerShell Get-Counter '\GPU Engine(*engtype_VideoDecode*)\Utilization Percentage'` で per-engine NVDEC 補助確認"

Options:

- 「実施完了、結果を返答」(検証 OK / NG を別途報告)
- 「PR review 後に実施」(まず /iterate-review でレビューを進める)
- 「実施できない、現状で merge」(検証なしで進める、Iron Law 6 違反のため非推奨)

- [ ] **Step 2: /iterate-review で review-fix ループ**

実機検証と並行 or 完了後に:

```text
/iterate-review <PR#>
```

review findings に対して:

- (A) 本 PR 内修正 (推奨、デフォルト)
- (B) 別 issue 起票 (限定例外)
- (C) 既存 issue 追記 (限定例外)

iterate-review skill が CI / lint / review 全 pass まで自走。

- [ ] **Step 3: Merge 後 `/close-issue 791`**

iterate-review summary で LGTM 確定後、Idios に merge 承認を得てから merge。merge 後:

```text
/close-issue 791
```

skill が受け入れ条件をマージ後 base ブランチで実測再検証し、Iron Law 4 担保ルートで `gh issue close` を実行。

---

## Self-Review (writing-plans skill §Self-Review)

### 1. Spec coverage

spec §8 受け入れ条件 8 項目すべてに対応 task あり:

- `_build_ffmpeg_args` に NVENC hwaccel 追加 → Task 1
- codec 別 NVDEC 対応 unit test → Task 1-2 (T1/T2/T3)
- libx264 fallback 回避 → Task 3 (T4) + Task 5 (I2)
- #762 multi-vendor mapping wire → Task 2 (T2/T3)
- wire protocol / progress event / cancel 既存 test 保護 → Task 6 (regression)
- Iron Law 6 実機検証 → Task 8 Step 1
- pre/post 計測 → Task 8 Step 1 内で記録依頼
- codec=copy 適用回避 → Task 3 (T5)

spec §3.1 mapping の 4 entry → Task 1 Step 3a で全 entry 一括追加。

spec §4.3 既存 test 保護 → Task 6 Step 1。

spec §5 Iron Law 6 → Task 8 Step 1。

### 2. Placeholder scan

- "TBD" / "TODO" / "implement later": なし
- "Add appropriate error handling": なし (新規 error path なし)
- "Write tests for the above": なし (各 test の actual code を提示)
- "Similar to Task N": なし (Task 2-5 で各 test の完全 code を repeat)
- 説明なしの "what to do": なし (各 step に code block + 期待 output)

### 3. Type consistency

- `_DECODE_HWACCEL_ARGS: dict[H264Encoder, tuple[str, ...]]` — Task 1 で定義、全 task で一貫
- `_build_ffmpeg_args` シグネチャ unchanged
- `H264Encoder.NVENC / QSV / AMF / LIBX264` — encoder.py の既存 enum (line 22-25)、test/impl で一貫使用
- mock_popen.call_args_list[N].args[0] — Task 5 で argv 取得方法を統一

### 4. Ambiguity

- Task 1 Step 3a の mapping 配置場所: "`_GPU_ENCODER_FAILURE_PATTERNS` の前" と明示
- Task 6 Step 5 で ruff / pyright fail 時の対応を具体化済
- Task 7 Step 5 で Codex adversarial-review の focus 文字列を明示

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-19-issue-791-nvdec-zero-copy-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** — Fresh subagent per task + two-stage review。Task 1-6 が独立に進められる構造のため subagent dispatch が効果的。CLAUDE.md `superpowers:subagent-driven-development` 採用宣言済。

**2. Inline Execution** — 本セッションで `executing-plans` で batch 実行。Task が小粒で 6 commit に分かれるため checkpoint レビューが頻繁になる。

Which approach?
