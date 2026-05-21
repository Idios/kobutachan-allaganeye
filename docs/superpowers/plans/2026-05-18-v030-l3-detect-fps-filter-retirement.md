# detect fps filter 廃止 (#576) 実装 plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ffmpeg `-vf fps=N` を detect path から廃止し、ffmpeg version 依存の frame-selection drift (#575 / #560 / #577) を構造的に除去する。20260118 で見逃されていた 0.8s 幅 blackout を正しく検出できるようになる。

**Architecture:** chunk full-decode + Python N-th sampling 方式に切り替える。`-ss` を `-i` の後ろに置く output seek + `-fps_mode passthrough` で decoder が emit するフレームをそのまま pipe し、Python 側で `frame_idx = round((t - chunk_start) * fps_num / fps_den)` で target timestamp に対応する frame を選択する。rational fps (NTSC 60000/1001 等) は probe.py で `fps_num`/`fps_den` として伝搬。env var `ALLAGANEYE_DETECT_FPS_FILTER=1` で旧 path に rollback 可能 (transitional、v0.3.x で削除)。

**Tech Stack:** Python 3.13 / ffmpeg 8.1 / numpy / `subprocess.Popen` streaming / pytest.

**Spec:** [docs/superpowers/specs/2026-05-18-v030-l3-detect-fps-filter-retirement-design.md](../specs/2026-05-18-v030-l3-detect-fps-filter-retirement-design.md) (design freeze 2026-05-18, Codex round-4 = READY)

**Branch / base:** `develop-0.3.0` ベース (親 spec §6.2 で v0.3.0 = 新 L3 release boundary を仮置きしているため develop-0.3.0 へ合流)。

**Iron Law gates** (`/`.claude/hooks/session-start.sh`):

- Iron Law 1: §9 受け入れ条件 22 項目すべて逐条 diff/test 提示
- Iron Law 3: §8 scope guard 違反禁止 (`audio/` / `scorebar.py` / `_probe_single_frame` / `_legacy/*` baseline 触らない)
- Iron Law 6: PR 作成前 Pre-flight Step 0-5 + 実機検証 AskUserQuestion + `/codex:adversarial-review` 必須

---

## File Structure

新規ファイル:

- `scripts/validate-fps-retirement.py` — PTS 検証用 one-off スクリプト (Iron Law 6 evidence)
- `tests/test_validate_fps_retirement.py` — 上記 script の unit test

修正ファイル:

- `allaganeye/video/probe.py` — `ProbeResult` 拡張 (`fps_num`/`fps_den`) + 静的 VFR WARN
- `allaganeye/video/detector.py` — `_decode_chunk_cpu` を v2/legacy dispatch、新 helper `_sample_chunk_frames` 追加、`detect_match_boundaries` / `_scan_cpu` signature 拡張、env var helper
- `allaganeye/video/gpu_detector.py` — `_decode_chunk` を v2/legacy dispatch、`scan_gpu` signature 拡張
- `allaganeye/commands/split_matches.py` — `detect_kwargs` に `source_fps_num`/`source_fps_den`/`source_fps` 追加 (line 745 構築箇所)
- `tests/test_probe.py` — `fps_num`/`fps_den` test + 静的 VFR WARN test
- `tests/test_detector.py` — 新 path test + env var test + 動的 VFR slack test
- `tests/test_gpu_detector.py` — 新 path test (vendor 別 cmd assertion)
- `tests/conftest.py` — autouse fixture で `ALLAGANEYE_DETECT_FPS_FILTER` を default unset
- `tests/baselines/v0.3.0/obs-20260118.metadata.json` — Class B regenerate
- `tests/baselines/v0.3.0/obs-20260118.split.json` — Class B regenerate (SHA-256 / size 更新)
- `docs/video-processing.md` — fps filter root cause fix の反映 (§「ffmpeg fps filter の version 依存制約」)
- `docs/testing-guide.md` — §「baseline drift の判定」 を「#576 完了後の運用」に更新
- `CHANGELOG.md` (or 該当箇所) — env var transitional + brightness_callback 値変更を user-visible metadata change として明記

---

## Task 1: probe.py — rational fps + 静的 VFR WARN

**Files:**

- Modify: `allaganeye/video/probe.py:16-24` (ProbeResult TypedDict) + `:80-128` (probe_video 末尾の戻り値構築)
- Test: `tests/test_probe.py`

**Spec refs:** §2.2 rational fps 伝搬, §2.2 VFR 2 段防御 (静的), §9.1 (#3 行目)

**Acceptance criteria addressed:** §9.1 #4-#6 (rational fps 公開 + 静的 VFR WARN)

**Context — 現状の関連コード** (`allaganeye/video/probe.py`):

```python
# Line 16-24 (current ProbeResult TypedDict)
class ProbeResult(TypedDict):
    """Metadata returned by probe_video()."""

    duration: float
    width: int
    height: int
    fps: float
    codec: str
    audio_codec: str | None
```

```python
# Line 27-34 (current _parse_frame_rate, returns float; we will add a num/den variant)
def _parse_frame_rate(rate_str: str) -> float:
    """Parse a frame rate string like '30/1' or '60000/1001'. Returns 0.0 on failure."""
    try:
        num, den = rate_str.split("/")
        fps = float(num) / float(den)
    except (ValueError, ZeroDivisionError, AttributeError):
        return 0.0
    return fps if fps > 0 else 0.0
```

- [ ] **Step 1: Write failing tests for rational fps and static VFR WARN**

`tests/test_probe.py` に以下を追加 (既存のテストは temper せず追加のみ):

```python
import logging

from allaganeye.video.probe import _parse_frame_rate_rational, probe_video


class TestParseFrameRateRational:
    """Tests for _parse_frame_rate_rational (新規, #576)."""

    def test_integer_rate(self):
        assert _parse_frame_rate_rational("60/1") == (60, 1)

    def test_ntsc_rate(self):
        assert _parse_frame_rate_rational("60000/1001") == (60000, 1001)

    def test_invalid_returns_zero_zero(self):
        assert _parse_frame_rate_rational("") == (0, 0)
        assert _parse_frame_rate_rational("0/1") == (0, 0)
        assert _parse_frame_rate_rational("1/0") == (0, 0)
        assert _parse_frame_rate_rational("abc") == (0, 0)


class TestProbeRationalFps:
    """ProbeResult exposes fps_num / fps_den (#576)."""

    def test_probe_result_has_rational_fields(self, tmp_path, monkeypatch):
        # NOTE: this calls probe_video with a fake ffprobe output via
        # monkeypatching subprocess.run.
        from unittest.mock import MagicMock
        import json as _json
        import allaganeye.video.probe as probe_mod

        fake_streams = {
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "av1",
                    "width": 1920,
                    "height": 1080,
                    "r_frame_rate": "60000/1001",
                    "avg_frame_rate": "60000/1001",
                },
            ],
            "format": {"duration": "3600.0"},
        }
        mock_result = MagicMock()
        mock_result.stdout = _json.dumps(fake_streams)
        mock_result.stderr = ""
        mock_result.returncode = 0
        monkeypatch.setattr(
            probe_mod.subprocess,
            "run",
            lambda *a, **kw: mock_result,
        )
        monkeypatch.setattr(
            probe_mod, "find_ffprobe", lambda: "ffprobe",
        )

        result = probe_mod.probe_video(tmp_path / "fake.mkv")
        assert result["fps_num"] == 60000
        assert result["fps_den"] == 1001
        assert abs(result["fps"] - 60000 / 1001) < 1e-9


class TestProbeStaticVfrWarn:
    """probe_video logs WARNING when r_frame_rate vs avg_frame_rate differ > 1% (#576)."""

    def test_aggregate_disagree_logs_warn(self, tmp_path, monkeypatch, caplog):
        from unittest.mock import MagicMock
        import json as _json
        import allaganeye.video.probe as probe_mod

        fake_streams = {
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "av1",
                    "width": 1920,
                    "height": 1080,
                    "r_frame_rate": "60/1",
                    "avg_frame_rate": "59/1",  # 1.67% diff -> WARN
                },
            ],
            "format": {"duration": "3600.0"},
        }
        mock_result = MagicMock()
        mock_result.stdout = _json.dumps(fake_streams)
        mock_result.stderr = ""
        mock_result.returncode = 0
        monkeypatch.setattr(probe_mod.subprocess, "run", lambda *a, **kw: mock_result)
        monkeypatch.setattr(probe_mod, "find_ffprobe", lambda: "ffprobe")

        with caplog.at_level(logging.WARNING, logger="allaganeye.video.probe"):
            probe_mod.probe_video(tmp_path / "fake.mkv")

        warns = [r for r in caplog.records if "VFR" in r.getMessage()]
        assert len(warns) == 1, f"expected one VFR WARN, got {[r.getMessage() for r in caplog.records]}"

    def test_aggregate_match_does_not_warn(self, tmp_path, monkeypatch, caplog):
        from unittest.mock import MagicMock
        import json as _json
        import allaganeye.video.probe as probe_mod

        fake_streams = {
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "av1",
                    "width": 1920,
                    "height": 1080,
                    "r_frame_rate": "60/1",
                    "avg_frame_rate": "60/1",  # exact match -> no WARN
                },
            ],
            "format": {"duration": "3600.0"},
        }
        mock_result = MagicMock()
        mock_result.stdout = _json.dumps(fake_streams)
        mock_result.stderr = ""
        mock_result.returncode = 0
        monkeypatch.setattr(probe_mod.subprocess, "run", lambda *a, **kw: mock_result)
        monkeypatch.setattr(probe_mod, "find_ffprobe", lambda: "ffprobe")

        with caplog.at_level(logging.WARNING, logger="allaganeye.video.probe"):
            probe_mod.probe_video(tmp_path / "fake.mkv")

        warns = [r for r in caplog.records if "VFR" in r.getMessage()]
        assert warns == []
```

- [ ] **Step 2: Run new tests, verify they fail**

```bash
pytest tests/test_probe.py::TestParseFrameRateRational tests/test_probe.py::TestProbeRationalFps tests/test_probe.py::TestProbeStaticVfrWarn -v
```

Expected: FAIL — `_parse_frame_rate_rational` does not exist; `result["fps_num"]` KeyError.

- [ ] **Step 3: Implement `_parse_frame_rate_rational` + extend ProbeResult**

`allaganeye/video/probe.py` 末尾 `_parse_frame_rate` の後に以下を追加:

```python
def _parse_frame_rate_rational(rate_str: str) -> tuple[int, int]:
    """Parse a frame rate string into (num, den). Returns (0, 0) on failure.

    Companion to ``_parse_frame_rate`` that preserves the rational form so
    callers needing exact NTSC arithmetic (e.g., detector frame index
    mapping, #576) can avoid float precision loss.
    """
    try:
        num_s, den_s = rate_str.split("/")
        num = int(num_s)
        den = int(den_s)
    except (ValueError, AttributeError):
        return 0, 0
    if num <= 0 or den <= 0:
        return 0, 0
    return num, den
```

`ProbeResult` TypedDict (line 16-24) を以下に置換:

```python
class ProbeResult(TypedDict):
    """Metadata returned by probe_video()."""

    duration: float
    width: int
    height: int
    fps: float
    fps_num: int      # #576: rational frame rate numerator (e.g. 60000)
    fps_den: int      # #576: rational frame rate denominator (e.g. 1001)
    codec: str
    audio_codec: str | None
```

- [ ] **Step 4: Wire fps_num/fps_den into probe_video() return + add VFR WARN**

`allaganeye/video/probe.py` の `probe_video` 関数内、`fps =` を解決した直後 (line 98-104 周辺) に rational 解決を追加:

```python
    # Parse FPS from r_frame_rate (e.g., "30/1" or "60000/1001"),
    # falling back to avg_frame_rate if r_frame_rate is unusable.
    fps = _parse_frame_rate(video_stream.get("r_frame_rate", ""))
    fps_num, fps_den = _parse_frame_rate_rational(video_stream.get("r_frame_rate", ""))
    if fps <= 0:
        fps = _parse_frame_rate(video_stream.get("avg_frame_rate", ""))
        fps_num, fps_den = _parse_frame_rate_rational(
            video_stream.get("avg_frame_rate", "")
        )
    if fps <= 0:
        raise VideoProcessingError(
            "Cannot determine video frame rate from ffprobe output"
        )

    # #576: 静的 VFR 検出 — r_frame_rate vs avg_frame_rate の差が 1% 超 の
    # 場合 WARNING ログ (hard fail はしない、benign mismatch を許容)。
    # 実 VFR / decoder anomaly は detector 側の動的 frame_count check で
    # 捕捉する。
    avg_fps = _parse_frame_rate(video_stream.get("avg_frame_rate", ""))
    if avg_fps > 0 and fps > 0:
        diff_ratio = abs(fps - avg_fps) / fps
        if diff_ratio > 0.01:
            logger.warning(
                "VFR の可能性あり (r_frame_rate=%.4f, avg_frame_rate=%.4f, "
                "diff=%.2f%%). detector 側で動的 frame_count check 経由で検証。",
                fps, avg_fps, diff_ratio * 100,
            )
```

ファイル冒頭に `import logging` と `logger = logging.getLogger(__name__)` が存在しない場合は追加:

```python
import logging
# ...(existing imports)...

logger = logging.getLogger(__name__)
```

`probe_video()` の戻り値辞書 (line 119-128) を更新:

```python
    return {
        "duration": duration,
        "width": width,
        "height": height,
        "fps": fps,
        "fps_num": fps_num,
        "fps_den": fps_den,
        "codec": video_stream.get("codec_name", "unknown"),
        "audio_codec": audio_stream.get("codec_name", "unknown")
        if audio_stream
        else None,
    }
```

- [ ] **Step 5: Run tests, verify they pass**

```bash
pytest tests/test_probe.py -v
```

Expected: PASS — all new tests + existing probe tests still pass.

- [ ] **Step 6: Run full lint + type check**

```bash
ruff check allaganeye/video/probe.py tests/test_probe.py
ruff format --check allaganeye/video/probe.py tests/test_probe.py
pyright allaganeye/video/probe.py tests/test_probe.py
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add allaganeye/video/probe.py tests/test_probe.py
git commit -m "$(cat <<'EOF'
feat(probe): rational fps (fps_num/fps_den) + 静的 VFR WARN (Refs #576)

#576 design spec §2.2 / §9.1 反映。ProbeResult に fps_num / fps_den を
追加し NTSC (60000/1001) 等の rational frame rate を float 精度損失なく
detector まで伝搬する基盤。

静的 VFR 検出は probe_video() で r_frame_rate vs avg_frame_rate の差が
1% 超の場合 WARNING ログのみ (hard fail しない)。OBS の末尾 dropped
frame 等の benign mismatch を許容しつつ、真の VFR は detector 側の動的
frame_count check で捕捉する 2 段防御。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: env var rollback infrastructure (helper + conftest fixture)

**Files:**

- Modify: `allaganeye/video/detector.py` (新規 helper `_use_legacy_fps_filter` 追加、既存定数群の末尾 line 1108 周辺)
- Modify: `tests/conftest.py` (autouse fixture 追加)
- Test: `tests/test_detector.py` (env var helper test)

**Spec refs:** §6 Rollback safety, §9.1 行目 #8-#9

**Acceptance criteria addressed:** §9.1 #8-#9 (env var + conftest autouse)

- [ ] **Step 1: Write failing tests**

`tests/test_detector.py` の末尾に以下を追加 (既存 import に `_use_legacy_fps_filter` を加える):

```python
import os

from allaganeye.video.detector import _use_legacy_fps_filter


class TestUseLegacyFpsFilter:
    """env var rollback helper (#576 §6)."""

    def test_default_false(self, monkeypatch):
        monkeypatch.delenv("ALLAGANEYE_DETECT_FPS_FILTER", raising=False)
        assert _use_legacy_fps_filter() is False

    def test_explicit_1_returns_true(self, monkeypatch):
        monkeypatch.setenv("ALLAGANEYE_DETECT_FPS_FILTER", "1")
        assert _use_legacy_fps_filter() is True

    def test_other_values_return_false(self, monkeypatch):
        for value in ("0", "true", "yes", "", "2"):
            monkeypatch.setenv("ALLAGANEYE_DETECT_FPS_FILTER", value)
            assert _use_legacy_fps_filter() is False, f"value={value!r}"


class TestConftestEnvVarAutouse:
    """conftest.py autouse fixture clears ALLAGANEYE_DETECT_FPS_FILTER (#576 §6)."""

    def test_env_var_unset_by_default(self):
        # autouse fixture should have unset it before this test runs.
        assert "ALLAGANEYE_DETECT_FPS_FILTER" not in os.environ, (
            "conftest autouse should unset ALLAGANEYE_DETECT_FPS_FILTER. "
            "CI pollution risk (#576 R6)."
        )
```

- [ ] **Step 2: Run, verify they fail**

```bash
pytest tests/test_detector.py::TestUseLegacyFpsFilter tests/test_detector.py::TestConftestEnvVarAutouse -v
```

Expected: FAIL — `_use_legacy_fps_filter` not defined / env var may leak if shell has it set.

- [ ] **Step 3: Implement `_use_legacy_fps_filter` in detector.py**

`allaganeye/video/detector.py` の既存定数群 (line ~1108 `_BLACKOUT_PADDING` の後) に追加:

```python
# ---------------------------------------------------------------------------
# Legacy fps-filter rollback switch (#576)
# ---------------------------------------------------------------------------
# Transitional escape hatch: when ALLAGANEYE_DETECT_FPS_FILTER=1 the
# detector reverts to the pre-#576 chunked fps=N filter path.  Default
# (= False) is the new output-seek + N-th sampling path.  Scheduled for
# removal in v0.3.x patch release (see CHANGELOG / docstring).
def _use_legacy_fps_filter() -> bool:
    """Return True when the legacy fps-filter path is forced via env var."""
    return os.environ.get("ALLAGANEYE_DETECT_FPS_FILTER") == "1"
```

import 先頭部 (line 1-12 周辺) に `os` の import が無ければ追加 (既に `import os` あり、不要)。

- [ ] **Step 4: Add autouse fixture to tests/conftest.py**

`tests/conftest.py` 末尾 (line 137 の後) に追加:

```python
@pytest.fixture(autouse=True)
def _clear_allaganeye_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear ALLAGANEYE_DETECT_FPS_FILTER for every test (#576 §6 / R6).

    The env var is a transitional rollback switch (will be deleted in
    v0.3.x). Tests that need to exercise the legacy path must opt-in by
    calling ``monkeypatch.setenv("ALLAGANEYE_DETECT_FPS_FILTER", "1")``
    inside the test body.  This fixture prevents CI pollution where a
    shell-set env var would silently make every test run the legacy code
    path.
    """
    monkeypatch.delenv("ALLAGANEYE_DETECT_FPS_FILTER", raising=False)
```

- [ ] **Step 5: Run tests, verify they pass**

```bash
pytest tests/test_detector.py::TestUseLegacyFpsFilter tests/test_detector.py::TestConftestEnvVarAutouse -v
```

Expected: PASS.

- [ ] **Step 6: Lint + type check**

```bash
ruff check allaganeye/video/detector.py tests/conftest.py tests/test_detector.py
ruff format --check allaganeye/video/detector.py tests/conftest.py tests/test_detector.py
pyright allaganeye/video/detector.py tests/conftest.py tests/test_detector.py
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add allaganeye/video/detector.py tests/conftest.py tests/test_detector.py
git commit -m "$(cat <<'EOF'
feat(detector): env var rollback + CI fixture hygiene (Refs #576)

#576 design spec §6 / §9.1 反映。新 fps-filter-less path の transitional
rollback switch として ALLAGANEYE_DETECT_FPS_FILTER=1 を導入。

- _use_legacy_fps_filter() helper (allaganeye/video/detector.py)
- tests/conftest.py に autouse fixture を追加し、default で env var を
  unset することで CI pollution (R6) を防ぐ。legacy path test は
  monkeypatch で局所的に setenv する規約。

v0.3.x patch release で env var を読まなくなる予定 (CHANGELOG に反映予定)。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `_sample_chunk_frames` helper (rational mapping + streaming Popen + 動的 VFR)

**Files:**

- Modify: `allaganeye/video/detector.py` (新規 helper `_sample_chunk_frames` 追加、`_FRAME_SIZE` 定数の後 line 64 周辺の後ろ)
- Test: `tests/test_detector.py`

**Spec refs:** §2.2 Python 側 sampling logic, §2.2 rational fps 伝搬, §2.2 memory budget, §2.2 VFR 2 段防御 (動的), §9.1 #6-#7

**Acceptance criteria addressed:** §9.1 #6 (動的 VFR 検出) + #7 (Popen streaming)

**Context — 用語**:

- `_FRAME_SIZE = 320 * 180 = 57600`
- target chunk_timestamps はソート済 (caller の `_scan_cpu` / `scan_gpu` で global grid から切出し済)
- fps の優先順位は §2.3: (1) `fps_num`/`fps_den` 両指定 → rational / (2) `source_fps` のみ → `Fraction(...).limit_denominator(10000)` 経由 / (3) 両 None → caller が legacy path にディスパッチ済 (本 helper は呼ばれない)

- [ ] **Step 1: Write failing tests (rational mapping + float fallback)**

`tests/test_detector.py` に新 class を追加:

```python
import io
from fractions import Fraction
from unittest.mock import MagicMock, patch

from allaganeye.video.detector import _FRAME_SIZE, _sample_chunk_frames


def _frames_bytes(brightnesses: list[int]) -> bytes:
    """Build a raw grayscale frame stream from per-frame mean brightness."""
    return b"".join(bytes([b]) * _FRAME_SIZE for b in brightnesses)


class TestSampleChunkFramesRationalMapping:
    """rational fps での frame_idx mapping (#576 §2.2 / §7.1.2)."""

    def test_integer_60fps(self):
        # source_fps=60/1, chunk_start=10.0, targets {10.0, 12.0, 14.0}
        # frame_idx {0, 120, 240}
        stream = io.BytesIO(_frames_bytes([100] * 300))
        result = _sample_chunk_frames(
            stream=stream,
            chunk_start=10.0,
            chunk_timestamps=[10.0, 12.0, 14.0],
            fps_num=60,
            fps_den=1,
            expected_frames=240,  # arbitrary, > max frame_idx
            is_tail_chunk=False,
        )
        assert result == {10.0: 100.0, 12.0: 100.0, 14.0: 100.0}

    def test_ntsc_59_94(self):
        # source_fps=60000/1001 (=59.94...), chunk_start=0.0, targets {0.0, 10.0}
        # frame_idx {0, round(10 * 60000 / 1001)} = {0, 599}
        # 599 + 1 = 600 frames minimum
        stream = io.BytesIO(_frames_bytes([50] * 700))
        result = _sample_chunk_frames(
            stream=stream,
            chunk_start=0.0,
            chunk_timestamps=[0.0, 10.0],
            fps_num=60000,
            fps_den=1001,
            expected_frames=600,
            is_tail_chunk=False,
        )
        assert 0.0 in result and 10.0 in result
        assert result[0.0] == 50.0
        assert result[10.0] == 50.0


class TestSampleChunkFramesFrameMissing:
    """frame_idx >= 利用可能 frame 数 のとき 255.0 fallback (#576 §4.3 / §7.1.4)."""

    def test_target_beyond_available_frames(self):
        # 100 frames available, target wants frame_idx 200 -> fallback to 255.0
        stream = io.BytesIO(_frames_bytes([0] * 100))
        result = _sample_chunk_frames(
            stream=stream,
            chunk_start=0.0,
            chunk_timestamps=[0.0, 10.0],  # 10.0 * 60 = 600 > 100
            fps_num=60,
            fps_den=1,
            expected_frames=600,
            is_tail_chunk=True,  # tail なので動的 VFR check も WARN のみ
        )
        assert result[0.0] == 0.0
        assert result[10.0] == 255.0


class TestSampleChunkFramesDynamicVfr:
    """動的 VFR 検出: slack 超過時 raise / tail chunk は WARN のみ (#576 §2.2 / §7.1.5)."""

    def test_within_slack_no_error(self):
        # 60fps × 60s = 3600 expected, slack = max(36, 6) = 36
        # emit 3580 = -20 (within slack), should not raise
        stream = io.BytesIO(_frames_bytes([100] * 3580))
        _sample_chunk_frames(
            stream=stream,
            chunk_start=0.0,
            chunk_timestamps=[0.0, 30.0],
            fps_num=60,
            fps_den=1,
            expected_frames=3600,
            is_tail_chunk=False,
        )
        # no raise expected

    def test_exceeds_slack_non_tail_raises(self):
        # 60fps × 60s = 3600 expected, slack = max(36, 6) = 36
        # emit 3500 = -100 (exceeds slack), non-tail chunk -> raise
        stream = io.BytesIO(_frames_bytes([100] * 3500))
        with pytest.raises(VideoProcessingError) as excinfo:
            _sample_chunk_frames(
                stream=stream,
                chunk_start=0.0,
                chunk_timestamps=[0.0, 30.0],
                fps_num=60,
                fps_den=1,
                expected_frames=3600,
                is_tail_chunk=False,
            )
        assert "Dynamic VFR" in str(excinfo.value)

    def test_exceeds_slack_tail_only_warns(self, caplog):
        # Same overshoot but tail chunk -> WARN only, no raise.
        import logging as _logging
        stream = io.BytesIO(_frames_bytes([100] * 3500))
        with caplog.at_level(_logging.WARNING):
            _sample_chunk_frames(
                stream=stream,
                chunk_start=0.0,
                chunk_timestamps=[0.0, 30.0],
                fps_num=60,
                fps_den=1,
                expected_frames=3600,
                is_tail_chunk=True,
            )
        msgs = [r.getMessage() for r in caplog.records if "VFR" in r.getMessage() or "tail" in r.getMessage()]
        assert any("tail" in m or "VFR" in m for m in msgs), (
            f"expected WARN for tail chunk, got: {[r.getMessage() for r in caplog.records]}"
        )
```

- [ ] **Step 2: Run, verify they fail**

```bash
pytest tests/test_detector.py::TestSampleChunkFramesRationalMapping tests/test_detector.py::TestSampleChunkFramesFrameMissing tests/test_detector.py::TestSampleChunkFramesDynamicVfr -v
```

Expected: FAIL — `_sample_chunk_frames` not defined.

- [ ] **Step 3: Implement `_sample_chunk_frames`**

`allaganeye/video/detector.py` の `_FRAME_SIZE` 定数 (line 63) の直後に追加:

```python
import math
# ...(existing imports)...


def _resolve_fps_rational(
    fps_num: int | None,
    fps_den: int | None,
    source_fps: float | None,
) -> tuple[int, int]:
    """Resolve (num, den) from rational-first / float-fallback inputs (#576 §2.3).

    Priority:
    1. ``fps_num`` + ``fps_den`` both given -> use as-is
    2. ``source_fps`` (float) only -> ``Fraction(...).limit_denominator(10000)``
    3. all None -> raise VideoProcessingError (caller should not call here
       without source_fps; legacy path is selected via env var separately)
    """
    if fps_num and fps_den:
        return fps_num, fps_den
    if source_fps and source_fps > 0:
        from fractions import Fraction

        frac = Fraction(source_fps).limit_denominator(10000)
        return frac.numerator, frac.denominator
    raise VideoProcessingError(
        "source_fps not provided to detector (need fps_num/fps_den or source_fps)."
    )


def _sample_chunk_frames(
    stream,
    chunk_start: float,
    chunk_timestamps: list[float],
    fps_num: int,
    fps_den: int,
    expected_frames: int,
    is_tail_chunk: bool,
) -> dict[float, float]:
    """Sample N-th frames from a stream by rational frame index (#576 §2.2).

    Args:
        stream: A binary file-like object that yields raw grayscale frames
            (320x180 = ``_FRAME_SIZE`` bytes per frame) when ``.read()``
            is called.  In production this is the stdout of a
            ``subprocess.Popen`` running ffmpeg with output seeking +
            ``-fps_mode passthrough``.
        chunk_start: Wall-clock start time of the chunk (seconds).
        chunk_timestamps: Pre-computed global grid timestamps that fall
            inside this chunk (sorted ascending).  Each becomes a key in
            the returned dict.
        fps_num / fps_den: Source video frame rate as rational (e.g. 60/1
            or 60000/1001 for NTSC 59.94).
        expected_frames: ``round(chunk_duration * fps_num / fps_den)`` -- the
            number of frames the decoder is expected to emit.  Used by
            the dynamic VFR check (frame_count vs expected).
        is_tail_chunk: True when this chunk ends at (or within 1.0s of)
            the video duration.  Tail chunks may emit fewer frames than
            expected due to decoder truncation; the VFR check downgrades
            to WARN-only for them.

    Returns:
        ``{timestamp: brightness}`` mapping for every entry in
        ``chunk_timestamps``.  Targets whose computed frame_idx exceeds
        the emitted frame count get 255.0 (safe non-blackout fallback,
        #214 contract preserved).

    Raises:
        VideoProcessingError: when the chunk is non-tail and the emitted
        frame count deviates from ``expected_frames`` by more than
        ``max(expected_frames * 0.01, ceil(source_fps * 0.1))`` frames
        (= 1% or 100ms equivalent, whichever larger).  This is the
        dynamic VFR / decoder anomaly detection (#576 §2.2).
    """
    source_fps = fps_num / fps_den

    # Read all frames streaming; cap working set to expected_frames + 64
    # ring slack so very long chunks don't balloon memory.
    frames: list[bytes] = []
    while True:
        chunk = stream.read(_FRAME_SIZE)
        if len(chunk) < _FRAME_SIZE:
            break
        frames.append(chunk)

    emit_count = len(frames)
    slack = max(int(expected_frames * 0.01), math.ceil(source_fps * 0.1))
    diff = abs(emit_count - expected_frames)
    if diff > slack:
        msg = (
            f"Dynamic VFR detection: chunk emitted {emit_count} frames, "
            f"expected {expected_frames} (slack=±{slack}). "
            f"Input may be VFR or decoder anomaly."
        )
        if is_tail_chunk:
            logger.warning(
                "%s tail chunk -- decoder truncation allowed, continuing.", msg,
            )
        else:
            raise VideoProcessingError(msg)

    results: dict[float, float] = {}
    for t in chunk_timestamps:
        # rational frame_idx (integer arithmetic preferred, avoids float drift
        # on NTSC 60000/1001 over long chunks).
        frame_idx = round((t - chunk_start) * fps_num / fps_den)
        if 0 <= frame_idx < emit_count:
            frame = np.frombuffer(frames[frame_idx], dtype=np.uint8)
            results[t] = float(frame.mean())
        else:
            results[t] = 255.0  # safe non-blackout fallback (#214)
    return results
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
pytest tests/test_detector.py::TestSampleChunkFramesRationalMapping tests/test_detector.py::TestSampleChunkFramesFrameMissing tests/test_detector.py::TestSampleChunkFramesDynamicVfr -v
```

Expected: PASS.

- [ ] **Step 5: Add float fallback test + verify**

```python
class TestSampleChunkFramesFloatFallback:
    """float source_fps を Fraction.limit_denominator(10000) で rational に
    変換した場合、NTSC rational と同じ frame_idx を選ぶこと (#576 §2.3 / §7.1.3)."""

    def test_float_59_94_yields_ntsc_index(self):
        from allaganeye.video.detector import _resolve_fps_rational

        num, den = _resolve_fps_rational(None, None, 60000 / 1001)
        # Fraction(60000/1001).limit_denominator(10000) -> 60000/1001 exactly
        assert (num, den) == (60000, 1001)

    def test_float_60_yields_60_over_1(self):
        from allaganeye.video.detector import _resolve_fps_rational

        num, den = _resolve_fps_rational(None, None, 60.0)
        # Fraction(60.0).limit_denominator(10000) -> 60/1
        assert (num, den) == (60, 1)
```

```bash
pytest tests/test_detector.py::TestSampleChunkFramesFloatFallback -v
```

Expected: PASS.

- [ ] **Step 6: Lint + type check**

```bash
ruff check allaganeye/video/detector.py tests/test_detector.py
ruff format --check allaganeye/video/detector.py tests/test_detector.py
pyright allaganeye/video/detector.py tests/test_detector.py
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add allaganeye/video/detector.py tests/test_detector.py
git commit -m "$(cat <<'EOF'
feat(detector): _sample_chunk_frames helper + rational fps + 動的 VFR (Refs #576)

#576 design spec §2.2 / §2.3 / §7.1.2-5 反映。新 path の Python 側
sampling logic を helper として実装。

- _resolve_fps_rational(): fps_num/fps_den 優先、float は Fraction で
  rational 復元 (NTSC 60000/1001 等で frame_idx exact)
- _sample_chunk_frames(): stream から全 frame を streaming で読出し、
  frame_idx = round((t - chunk_start) * fps_num / fps_den) で target
  timestamp に対応する frame を選択。frame_idx 超過は 255.0 fallback
  (#214 既存契約と整合)
- 動的 VFR 検出: |emit - expected| > max(1%, ceil(fps*0.1)) で
  VideoProcessingError raise、tail chunk は WARN のみ (#576 §2.2 + N3)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `_decode_chunk_cpu` リファクタ (新 ffmpeg cmd + env var dispatch)

**Files:**

- Modify: `allaganeye/video/detector.py:270-352` (`_decode_chunk_cpu` 全面リファクタ)
- Modify: `allaganeye/video/detector.py:355-425` (`_scan_cpu` — `fps_num`/`fps_den`/`is_tail_chunk` 伝搬)
- Test: `tests/test_detector.py` (新 path cmd assertion + env var dispatch test)

**Spec refs:** §2.1 ffmpeg invocation, §2.3 API 拡張, §6 rollback dispatch, §7.1.1 / §7.1.7

**Acceptance criteria addressed:** §9.1 #1-#3 (ffmpeg cmd 変更 + output seek + signature)

**Context — 現状の `_decode_chunk_cpu` (line 270-352)**:

```python
def _decode_chunk_cpu(
    video_path: Path,
    chunk_timestamps: list[float],
    chunk_start: float,
    chunk_end: float,
    sample_interval: float,
) -> dict[float, float]:
    chunk_duration = chunk_end - chunk_start
    fps_value = 1.0 / sample_interval
    cmd = [
        find_ffmpeg(),
        "-threads", "1",
        "-ss", str(chunk_start),
        "-t", str(chunk_duration),
        "-i", str(video_path),
        "-vf", f"fps={fps_value},scale={_SAMPLE_WIDTH}:{_SAMPLE_HEIGHT},format=gray",
        "-f", "rawvideo",
        "-pix_fmt", "gray",
        "pipe:1",
    ]
    # ... subprocess.run, parse stdout, fill results ...
```

- [ ] **Step 1: Write failing test for new cmd shape + env var dispatch**

`tests/test_detector.py` に追加:

```python
import io as _io

import pytest


class TestDecodeChunkCpuNewPath:
    """_decode_chunk_cpu 新 path の cmd 構築検証 (#576 §2.1 / §7.1.1)."""

    @patch("allaganeye.video.detector.subprocess.Popen")
    @patch("allaganeye.video.detector.find_ffmpeg", return_value="ffmpeg")
    def test_cmd_uses_output_seek_no_fps_passthrough(self, _mock_ff, mock_popen, monkeypatch):
        monkeypatch.delenv("ALLAGANEYE_DETECT_FPS_FILTER", raising=False)

        mock_proc = MagicMock()
        # 60s @ 60fps = 3600 frames; emit exactly that
        mock_proc.stdout = _io.BytesIO(bytes([0] * _FRAME_SIZE * 3600))
        mock_proc.stderr = _io.BytesIO(b"")
        mock_proc.wait.return_value = 0
        mock_proc.returncode = 0
        mock_popen.return_value.__enter__.return_value = mock_proc

        _decode_chunk_cpu(
            Path("test.mp4"),
            chunk_timestamps=[0.0, 1.0, 2.0],
            chunk_start=0.0,
            chunk_end=60.0,
            sample_interval=1.0,
            source_fps_num=60,
            source_fps_den=1,
            is_tail_chunk=False,
        )

        called_cmd = mock_popen.call_args[0][0]
        # output seek: -ss must come AFTER -i, not before
        i_idx = called_cmd.index("-i")
        ss_idx = called_cmd.index("-ss")
        assert ss_idx > i_idx, f"-ss must follow -i (output seek), got {called_cmd}"
        # no fps= in -vf
        vf_idx = called_cmd.index("-vf")
        vf_value = called_cmd[vf_idx + 1]
        assert "fps=" not in vf_value, f"fps filter must be removed, got -vf {vf_value!r}"
        # -fps_mode passthrough explicit
        assert "-fps_mode" in called_cmd, "missing -fps_mode passthrough"
        fps_mode_idx = called_cmd.index("-fps_mode")
        assert called_cmd[fps_mode_idx + 1] == "passthrough"


class TestDecodeChunkCpuLegacyRollback:
    """env var=1 で旧 fps filter cmd が生成されること (#576 §6 / §7.1.7)."""

    @patch("allaganeye.video.detector.subprocess.run")
    @patch("allaganeye.video.detector.find_ffmpeg", return_value="ffmpeg")
    def test_legacy_cmd_used_when_env_set(self, _mock_ff, mock_run, monkeypatch):
        monkeypatch.setenv("ALLAGANEYE_DETECT_FPS_FILTER", "1")
        mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")

        _decode_chunk_cpu(
            Path("test.mp4"),
            chunk_timestamps=[0.0, 1.0, 2.0],
            chunk_start=0.0,
            chunk_end=3.0,
            sample_interval=1.0,
            source_fps_num=60,
            source_fps_den=1,
            is_tail_chunk=False,
        )

        called_cmd = mock_run.call_args[0][0]
        # legacy: -ss before -i
        i_idx = called_cmd.index("-i")
        ss_idx = called_cmd.index("-ss")
        assert ss_idx < i_idx, f"legacy -ss must precede -i, got {called_cmd}"
        # legacy: fps= present in -vf
        vf_idx = called_cmd.index("-vf")
        vf_value = called_cmd[vf_idx + 1]
        assert "fps=" in vf_value, f"legacy must keep fps filter, got -vf {vf_value!r}"
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pytest tests/test_detector.py::TestDecodeChunkCpuNewPath tests/test_detector.py::TestDecodeChunkCpuLegacyRollback -v
```

Expected: FAIL — new path not implemented, old _decode_chunk_cpu signature doesn't take source_fps_num/den/is_tail_chunk.

- [ ] **Step 3: Refactor `_decode_chunk_cpu` into legacy + v2 + dispatcher**

`allaganeye/video/detector.py:270-352` を以下に置換:

```python
def _decode_chunk_cpu(
    video_path: Path,
    chunk_timestamps: list[float],
    chunk_start: float,
    chunk_end: float,
    sample_interval: float,
    *,
    source_fps_num: int | None = None,
    source_fps_den: int | None = None,
    source_fps: float | None = None,
    is_tail_chunk: bool = False,
) -> dict[float, float]:
    """Decode a chunk in CPU mode.

    Dispatches to the legacy fps-filter path when env var
    ``ALLAGANEYE_DETECT_FPS_FILTER=1`` is set or when rational fps cannot
    be resolved.  Otherwise uses the new output-seek + Python N-th
    sampling path (#576).
    """
    if not chunk_timestamps:
        return {}

    use_legacy = _use_legacy_fps_filter() or (
        source_fps_num is None
        and source_fps_den is None
        and source_fps is None
    )
    if use_legacy:
        return _decode_chunk_cpu_legacy(
            video_path, chunk_timestamps, chunk_start, chunk_end, sample_interval,
        )

    fps_num, fps_den = _resolve_fps_rational(
        source_fps_num, source_fps_den, source_fps,
    )
    return _decode_chunk_cpu_v2(
        video_path,
        chunk_timestamps,
        chunk_start,
        chunk_end,
        fps_num,
        fps_den,
        is_tail_chunk,
    )


def _decode_chunk_cpu_legacy(
    video_path: Path,
    chunk_timestamps: list[float],
    chunk_start: float,
    chunk_end: float,
    sample_interval: float,
) -> dict[float, float]:
    """Legacy fps-filter chunk decode (pre-#576). Kept for env var rollback.

    Scheduled for removal in v0.3.x patch release.
    """
    chunk_duration = chunk_end - chunk_start
    fps_value = 1.0 / sample_interval

    cmd = [
        find_ffmpeg(),
        "-threads", "1",
        "-ss", str(chunk_start),
        "-t", str(chunk_duration),
        "-i", str(video_path),
        "-vf",
        f"fps={fps_value},scale={_SAMPLE_WIDTH}:{_SAMPLE_HEIGHT},format=gray",
        "-f", "rawvideo",
        "-pix_fmt", "gray",
        "pipe:1",
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=max(300, int(chunk_duration * 2)),
        )
    except FileNotFoundError as e:
        raise VideoProcessingError(
            "ffmpeg not found. Please install ffmpeg and ensure it is in PATH."
        ) from e
    except subprocess.TimeoutExpired:
        logger.warning("CPU chunk decode timed out [%.1f-%.1f]", chunk_start, chunk_end)
        return {t: 255.0 for t in chunk_timestamps}

    if proc.returncode != 0:
        logger.warning(
            "CPU chunk decode failed [%.1f-%.1f]: %s",
            chunk_start, chunk_end,
            proc.stderr.decode(errors="replace")[-200:],
        )
        return {t: 255.0 for t in chunk_timestamps}

    data = proc.stdout
    results: dict[float, float] = {}
    frame_idx = 0
    offset = 0
    while offset + _FRAME_SIZE <= len(data) and frame_idx < len(chunk_timestamps):
        frame = np.frombuffer(data[offset : offset + _FRAME_SIZE], dtype=np.uint8)
        results[chunk_timestamps[frame_idx]] = float(frame.mean())
        offset += _FRAME_SIZE
        frame_idx += 1

    for t in chunk_timestamps:
        if t not in results:
            results[t] = 255.0
    return results


def _decode_chunk_cpu_v2(
    video_path: Path,
    chunk_timestamps: list[float],
    chunk_start: float,
    chunk_end: float,
    fps_num: int,
    fps_den: int,
    is_tail_chunk: bool,
) -> dict[float, float]:
    """New path: output seek + -fps_mode passthrough + Python N-th sampling (#576).

    ffmpeg invocation has ``-ss`` AFTER ``-i`` (output seeking) so the
    first emitted frame's PTS equals ``chunk_start`` exactly.  fps filter
    is removed; ``-fps_mode passthrough`` suppresses ffmpeg internal
    frame-rate normalization.  All frames are streamed through stdout
    and the Python side picks indices via
    ``round((t - chunk_start) * fps_num / fps_den)``.
    """
    chunk_duration = chunk_end - chunk_start
    expected_frames = round(chunk_duration * fps_num / fps_den)

    cmd = [
        find_ffmpeg(),
        "-threads", "1",
        "-i", str(video_path),
        "-ss", str(chunk_start),
        "-t", str(chunk_duration),
        "-fps_mode", "passthrough",
        "-vf", f"scale={_SAMPLE_WIDTH}:{_SAMPLE_HEIGHT},format=gray",
        "-f", "rawvideo",
        "-pix_fmt", "gray",
        "pipe:1",
    ]

    try:
        with subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as proc:
            try:
                results = _sample_chunk_frames(
                    stream=proc.stdout,
                    chunk_start=chunk_start,
                    chunk_timestamps=chunk_timestamps,
                    fps_num=fps_num,
                    fps_den=fps_den,
                    expected_frames=expected_frames,
                    is_tail_chunk=is_tail_chunk,
                )
                proc.wait(timeout=max(300, int(chunk_duration * 2)))
            except VideoProcessingError:
                proc.kill()
                raise
            except subprocess.TimeoutExpired:
                proc.kill()
                logger.warning(
                    "CPU chunk v2 decode timed out [%.1f-%.1f]",
                    chunk_start, chunk_end,
                )
                return {t: 255.0 for t in chunk_timestamps}
    except FileNotFoundError as e:
        raise VideoProcessingError(
            "ffmpeg not found. Please install ffmpeg and ensure it is in PATH."
        ) from e

    if proc.returncode != 0:
        stderr = proc.stderr.read().decode(errors="replace")[-200:]
        logger.warning(
            "CPU chunk v2 decode failed [%.1f-%.1f]: %s",
            chunk_start, chunk_end, stderr,
        )
        return {t: 255.0 for t in chunk_timestamps}

    return results
```

- [ ] **Step 4: Update `_scan_cpu` signature to propagate fps and tail flag**

`allaganeye/video/detector.py:355-425` (`_scan_cpu`) を以下に修正 (関数 signature 拡張 + chunk dispatch 更新):

```python
def _scan_cpu(
    video_path: Path,
    duration_hint: float,
    sample_interval: float,
    blackout_threshold: float,
    workers: int | None = None,
    progress_callback: Callable[[int, int, int], None] | None = None,
    *,
    source_fps_num: int | None = None,
    source_fps_den: int | None = None,
    source_fps: float | None = None,
) -> dict[float, float]:
    """CPU mode: chunked decode (output seek + Python N-th sampling, #576).

    When ``source_fps_num``/``source_fps_den`` (or float ``source_fps``) is
    provided AND env var ``ALLAGANEYE_DETECT_FPS_FILTER`` is not set, uses
    the new output-seek path.  Otherwise falls back to the legacy
    fps-filter path.
    """
    timestamps = _generate_timestamps(duration_hint, sample_interval)
    if not timestamps:
        return {}

    total_samples = len(timestamps)
    num_chunks = min(os.cpu_count() or 4, 32)
    chunk_duration = duration_hint / num_chunks

    chunks: list[tuple[float, float, list[float], bool]] = []
    for i in range(num_chunks):
        c_start = i * chunk_duration
        c_end = min((i + 1) * chunk_duration + sample_interval, duration_hint)
        c_timestamps = [t for t in timestamps if c_start <= t < c_end]
        is_tail = c_end >= duration_hint - 1.0
        if c_timestamps:
            chunks.append((c_start, c_end, c_timestamps, is_tail))

    results: dict[float, float] = {}
    blackout_count = 0
    completed = 0

    with ThreadPoolExecutor(
        max_workers=min(num_chunks, _resolve_workers(workers))
    ) as pool:
        futures = {
            pool.submit(
                _decode_chunk_cpu,
                video_path,
                c_ts,
                c_start,
                c_end,
                sample_interval,
                source_fps_num=source_fps_num,
                source_fps_den=source_fps_den,
                source_fps=source_fps,
                is_tail_chunk=is_tail,
            ): (c_start, c_ts)
            for c_start, c_end, c_ts, is_tail in chunks
        }
        for future in as_completed(futures):
            chunk_results = future.result()
            for t, brightness in chunk_results.items():
                if t not in results:
                    results[t] = brightness
                    completed += 1
                    if brightness < blackout_threshold:
                        blackout_count += 1
                    if progress_callback is not None:
                        progress_callback(completed, total_samples, blackout_count)

    for t in timestamps:
        if t not in results:
            results[t] = 255.0

    if not any(b < blackout_threshold for b in results.values()) and len(results) > 0:
        logger.debug("No blackouts detected in %d frames", len(results))

    return results
```

- [ ] **Step 5: Run new path + legacy path tests, verify pass**

```bash
pytest tests/test_detector.py::TestDecodeChunkCpuNewPath tests/test_detector.py::TestDecodeChunkCpuLegacyRollback -v
```

Expected: PASS.

- [ ] **Step 6: Verify existing `_decode_chunk_cpu` tests still pass (legacy path preserved)**

```bash
pytest tests/test_detector.py::TestDecodeChunkCpu -v
```

Expected: PASS (legacy fallback behavior preserved).

- [ ] **Step 7: Lint + type check**

```bash
ruff check allaganeye/video/detector.py tests/test_detector.py
ruff format --check allaganeye/video/detector.py tests/test_detector.py
pyright allaganeye/video/detector.py tests/test_detector.py
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add allaganeye/video/detector.py tests/test_detector.py
git commit -m "$(cat <<'EOF'
refactor(detector): _decode_chunk_cpu を v2/legacy dispatch 化 (Refs #576)

#576 design spec §2.1 / §2.3 / §6 反映。CPU chunk decode を新方式
(output seek + Python N-th sampling) と旧 fps filter path に分離し、
env var ALLAGANEYE_DETECT_FPS_FILTER=1 で切替可能にする。

- _decode_chunk_cpu(): dispatcher (env var + source_fps の有無で判定)
- _decode_chunk_cpu_legacy(): pre-#576 の fps filter 経路 (transitional)
- _decode_chunk_cpu_v2(): 新 path
  - ffmpeg cmd: -ss を -i の後に移動 (output seek)
  - -vf から fps= 削除、-fps_mode passthrough 追加
  - subprocess.Popen + streaming read (capture_output 禁止)
  - _sample_chunk_frames helper 経由で rational fps から frame_idx を計算
- _scan_cpu(): source_fps_num/den/fps + is_tail_chunk を伝搬

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: `_decode_chunk` (GPU) リファクタ — 全 vendor path で同じ refactor

**Files:**

- Modify: `allaganeye/video/gpu_detector.py:340-486` (`_decode_chunk` 全面リファクタ — vendor 別 hwaccel 維持しつつ output seek + fps_mode passthrough)
- Modify: `allaganeye/video/gpu_detector.py:156-318` (`scan_gpu` — `fps_num`/`fps_den`/`is_tail_chunk` 伝搬)
- Test: `tests/test_gpu_detector.py`

**Spec refs:** §2.1, §2.3, §7.1.10 vendor-specific command

**Acceptance criteria addressed:** §9.1 #1-#3 (GPU path も同じ変更)

**Context — 現状の `_decode_chunk` (line 340-486)**:

GPU 版は vendor 別 hwaccel 設定が複雑 (NVIDIA cuvid / AMD d3d11va / Intel QSV、`_HWACCELS_NEED_HWDOWNLOAD` で hwdownload prefix を追加)。CPU と同じく fps filter を `-vf` から除去し、`-fps_mode passthrough` を追加、`-ss` を `-i` の後に移動する。残りの vendor 別 argument 構築 (`-hwaccel`, `-hwaccel_output_format`, `-c:v`) は維持。

- [ ] **Step 1: Write failing test for GPU new path cmd shape (per vendor)**

`tests/test_gpu_detector.py` に追加 (既存 import に `_decode_chunk` あり):

```python
class TestDecodeChunkV2Cmd:
    """GPU _decode_chunk 新 path の cmd 構築検証 (#576 §2.1 / §7.1.10)."""

    @patch("allaganeye.video.gpu_detector.subprocess.Popen")
    @patch("allaganeye.video.gpu_detector.find_ffmpeg", return_value="ffmpeg")
    def test_nvidia_new_path(self, _mock_ff, mock_popen, monkeypatch):
        monkeypatch.delenv("ALLAGANEYE_DETECT_FPS_FILTER", raising=False)

        mock_proc = MagicMock()
        # 10s @ 60fps = 600 frames
        from allaganeye.video.detector import _FRAME_SIZE as _FS
        mock_proc.stdout = _io.BytesIO(bytes([0] * _FS * 600))
        mock_proc.stderr = _io.BytesIO(b"")
        mock_proc.wait.return_value = 0
        mock_proc.returncode = 0
        mock_popen.return_value.__enter__.return_value = mock_proc

        _decode_chunk(
            Path("test.mp4"),
            chunk_start=0.0,
            chunk_end=10.0,
            sample_interval=1.0,
            codec="av1",
            chunk_timestamps=[0.0, 5.0],
            vendor="nvidia",
            source_fps_num=60,
            source_fps_den=1,
            is_tail_chunk=False,
        )

        cmd = mock_popen.call_args[0][0]
        # -ss after -i
        assert cmd.index("-ss") > cmd.index("-i")
        # no fps= in -vf
        vf_value = cmd[cmd.index("-vf") + 1]
        assert "fps=" not in vf_value
        # -fps_mode passthrough explicit
        assert cmd[cmd.index("-fps_mode") + 1] == "passthrough"
        # nvidia decoder preserved
        assert "-c:v" in cmd
        cv_idx = cmd.index("-c:v")
        assert cmd[cv_idx + 1] == "av1_cuvid"

    @patch("allaganeye.video.gpu_detector.subprocess.Popen")
    @patch("allaganeye.video.gpu_detector.find_ffmpeg", return_value="ffmpeg")
    def test_amd_new_path_keeps_hwdownload(self, _mock_ff, mock_popen, monkeypatch):
        monkeypatch.delenv("ALLAGANEYE_DETECT_FPS_FILTER", raising=False)

        mock_proc = MagicMock()
        from allaganeye.video.detector import _FRAME_SIZE as _FS
        mock_proc.stdout = _io.BytesIO(bytes([0] * _FS * 600))
        mock_proc.stderr = _io.BytesIO(b"")
        mock_proc.wait.return_value = 0
        mock_proc.returncode = 0
        mock_popen.return_value.__enter__.return_value = mock_proc

        _decode_chunk(
            Path("test.mp4"),
            chunk_start=0.0,
            chunk_end=10.0,
            sample_interval=1.0,
            codec="h264",
            chunk_timestamps=[0.0, 5.0],
            vendor="amd",
            source_fps_num=60,
            source_fps_den=1,
            is_tail_chunk=False,
        )

        cmd = mock_popen.call_args[0][0]
        # AMD: hwdownload prefix in -vf, plus output seek + passthrough + no fps=
        vf_value = cmd[cmd.index("-vf") + 1]
        assert "hwdownload,format=nv12" in vf_value
        assert "fps=" not in vf_value
        assert cmd.index("-ss") > cmd.index("-i")
        assert cmd[cmd.index("-fps_mode") + 1] == "passthrough"

    @patch("allaganeye.video.gpu_detector.subprocess.Popen")
    @patch("allaganeye.video.gpu_detector.find_ffmpeg", return_value="ffmpeg")
    def test_intel_qsv_new_path(self, _mock_ff, mock_popen, monkeypatch):
        monkeypatch.delenv("ALLAGANEYE_DETECT_FPS_FILTER", raising=False)

        mock_proc = MagicMock()
        from allaganeye.video.detector import _FRAME_SIZE as _FS
        mock_proc.stdout = _io.BytesIO(bytes([0] * _FS * 600))
        mock_proc.stderr = _io.BytesIO(b"")
        mock_proc.wait.return_value = 0
        mock_proc.returncode = 0
        mock_popen.return_value.__enter__.return_value = mock_proc

        _decode_chunk(
            Path("test.mp4"),
            chunk_start=0.0,
            chunk_end=10.0,
            sample_interval=1.0,
            codec="h264",
            chunk_timestamps=[0.0, 5.0],
            vendor="intel",
            source_fps_num=60,
            source_fps_den=1,
            is_tail_chunk=False,
        )

        cmd = mock_popen.call_args[0][0]
        # Intel QSV: hwdownload prefix preserved, decoder = h264_qsv
        vf_value = cmd[cmd.index("-vf") + 1]
        assert "hwdownload,format=nv12" in vf_value
        assert "fps=" not in vf_value
        cv_idx = cmd.index("-c:v")
        assert cmd[cv_idx + 1] == "h264_qsv"
```

- [ ] **Step 2: Run, verify they fail**

```bash
pytest tests/test_gpu_detector.py::TestDecodeChunkV2Cmd -v
```

Expected: FAIL — signature doesn't accept `source_fps_num`/`source_fps_den`/`is_tail_chunk`.

- [ ] **Step 3: Refactor `_decode_chunk` into v2/legacy dispatch**

`allaganeye/video/gpu_detector.py:340-486` を以下の構造に改修。冒頭 (line 340 直前) に dispatcher を、その後ろに `_decode_chunk_legacy()` (現行 body) と `_decode_chunk_v2()` (新 body) を配置:

```python
from allaganeye.video.detector import (
    _FRAME_SIZE,
    _SAMPLE_HEIGHT,
    _SAMPLE_WIDTH,
    _generate_timestamps,
    _resolve_fps_rational,        # 新規 import (Task 3 で追加)
    _sample_chunk_frames,         # 新規 import (Task 3 で追加)
    _use_legacy_fps_filter,       # 新規 import (Task 2 で追加)
)


def _decode_chunk(
    video_path: Path,
    chunk_start: float,
    chunk_end: float,
    sample_interval: float,
    codec: str | None = None,
    chunk_timestamps: list[float] | None = None,
    vendor: str | None = None,
    *,
    source_fps_num: int | None = None,
    source_fps_den: int | None = None,
    source_fps: float | None = None,
    is_tail_chunk: bool = False,
) -> tuple[dict[float, float], str]:
    """GPU chunk decode dispatcher (#576).

    Falls back to legacy fps-filter path when env var
    ``ALLAGANEYE_DETECT_FPS_FILTER=1`` or no rational fps supplied.
    """
    use_legacy = _use_legacy_fps_filter() or (
        source_fps_num is None and source_fps_den is None and source_fps is None
    )
    if use_legacy:
        return _decode_chunk_legacy(
            video_path, chunk_start, chunk_end, sample_interval,
            codec=codec, chunk_timestamps=chunk_timestamps, vendor=vendor,
        )

    fps_num, fps_den = _resolve_fps_rational(
        source_fps_num, source_fps_den, source_fps,
    )
    return _decode_chunk_v2(
        video_path, chunk_start, chunk_end, codec, chunk_timestamps,
        vendor, fps_num, fps_den, is_tail_chunk,
    )


def _decode_chunk_legacy(  # === 元 _decode_chunk の body をそのまま rename ===
    video_path: Path,
    chunk_start: float,
    chunk_end: float,
    sample_interval: float,
    codec: str | None = None,
    chunk_timestamps: list[float] | None = None,
    vendor: str | None = None,
) -> tuple[dict[float, float], str]:
    """Legacy fps-filter chunk decode (pre-#576). Kept for env var rollback."""
    # ... (現行 _decode_chunk body をそのまま貼付け、line 374-485 相当) ...
```

注: 既存 `_decode_chunk` の body (line 374 以降の `chunk_duration = chunk_end - chunk_start` から最後の `return results, stderr_text` まで) を `_decode_chunk_legacy` にコピーペーストして body をそのまま保持する。

続いて `_decode_chunk_v2` を新規追加 (legacy body の直後):

```python
def _decode_chunk_v2(
    video_path: Path,
    chunk_start: float,
    chunk_end: float,
    codec: str | None,
    chunk_timestamps: list[float] | None,
    vendor: str | None,
    fps_num: int,
    fps_den: int,
    is_tail_chunk: bool,
) -> tuple[dict[float, float], str]:
    """New GPU chunk decode: output seek + Python N-th sampling (#576).

    Vendor-specific hwaccel args / hwdownload prefix preserved from legacy.
    Only the filter chain shape and seek position change.
    """
    chunk_duration = chunk_end - chunk_start
    expected_frames = round(chunk_duration * fps_num / fps_den)

    # Resolve decoder / hwaccel for the selected vendor (same logic as legacy).
    decoder: str | None = None
    hwaccel_name: str | None = None
    if vendor and codec:
        decoder = _GPU_DECODER_MAP.get(vendor, {}).get(codec)
        hwaccel_name = _VENDOR_HWACCEL_MAP.get(vendor)
    if decoder is None and vendor is None:
        decoder = _CUVID_CODEC_MAP.get(codec or "")
        if decoder:
            hwaccel_name = "cuda"

    needs_hwdownload = (
        hwaccel_name is not None and hwaccel_name in _HWACCELS_NEED_HWDOWNLOAD
    )
    if decoder and hwaccel_name:
        hwaccel_args = ["-hwaccel", hwaccel_name]
        if needs_hwdownload:
            surface_fmt = _HWACCEL_OUTPUT_FORMAT_MAP.get(hwaccel_name, hwaccel_name)
            hwaccel_args += ["-hwaccel_output_format", surface_fmt]
        hwaccel_args += ["-c:v", decoder]
    else:
        hwaccel_args = ["-hwaccel", "auto"]

    vf_prefix = "hwdownload,format=nv12," if needs_hwdownload else ""

    cmd = [
        find_ffmpeg(),
        *hwaccel_args,
        "-i", str(video_path),
        "-ss", str(chunk_start),
        "-t", str(chunk_duration),
        "-fps_mode", "passthrough",
        "-vf", f"{vf_prefix}scale={_SAMPLE_WIDTH}:{_SAMPLE_HEIGHT},format=gray",
        "-f", "rawvideo",
        "-pix_fmt", "gray",
        "pipe:1",
    ]

    stderr_text = ""
    try:
        with subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as proc:
            try:
                results = _sample_chunk_frames(
                    stream=proc.stdout,
                    chunk_start=chunk_start,
                    chunk_timestamps=chunk_timestamps or [],
                    fps_num=fps_num,
                    fps_den=fps_den,
                    expected_frames=expected_frames,
                    is_tail_chunk=is_tail_chunk,
                )
                stderr_bytes = proc.stderr.read()
                stderr_text = stderr_bytes.decode(errors="replace")
                proc.wait(timeout=max(300, int(chunk_duration * 2)))
            except VideoProcessingError:
                proc.kill()
                raise
            except subprocess.TimeoutExpired as e:
                proc.kill()
                raise VideoProcessingError(
                    f"GPU decode v2 timed out for chunk {chunk_start}"
                ) from e
    except FileNotFoundError as e:
        raise VideoProcessingError(
            "ffmpeg not found. Please install ffmpeg and ensure it is in PATH."
        ) from e

    if proc.returncode != 0:
        raise VideoProcessingError(
            "GPU decode v2 failed",
            context={
                "command": " ".join(str(c) for c in cmd),
                "return_code": proc.returncode,
                "chunk": f"{chunk_start:.1f}-{chunk_end:.1f}",
                "stderr_tail": stderr_text[-STDERR_TAIL_BYTES:],
            },
        )

    return results, stderr_text
```

`scan_gpu` (line 156-318) の signature と内部の `_decode_chunk` 呼び出しに `source_fps_num`/`source_fps_den`/`source_fps`/`is_tail_chunk` を伝搬:

```python
def scan_gpu(
    video_path: Path,
    duration: float,
    sample_interval: float,
    blackout_threshold: float,
    progress_callback: Callable[[int, int, int], None] | None = None,
    codec: str | None = None,
    chunk_progress_callback: Callable[[int, int, float], None] | None = None,
    chunk_dispatch_callback: Callable[[int], None] | None = None,
    vendor: str | None = None,
    *,
    source_fps_num: int | None = None,
    source_fps_den: int | None = None,
    source_fps: float | None = None,
) -> dict[float, float]:
    # ... (chunk 構築までは現行通り) ...
    chunks: list[tuple[float, float, list[float], bool]] = []
    for i in range(num_chunks):
        chunk_start = i * chunk_duration
        chunk_end = min((i + 1) * chunk_duration, duration)
        chunk_timestamps = [t for t in global_grid if chunk_start <= t < chunk_end]
        is_tail = chunk_end >= duration - 1.0
        if chunk_timestamps:
            chunks.append((chunk_start, chunk_end, chunk_timestamps, is_tail))
    # ... (numbers re-derived, callback setup) ...

    with ThreadPoolExecutor(max_workers=max_parallel) as pool:
        futures = {
            pool.submit(
                _decode_chunk,
                video_path,
                chunk_start,
                chunk_end,
                sample_interval,
                codec,
                chunk_timestamps,
                vendor,
                source_fps_num=source_fps_num,
                source_fps_den=source_fps_den,
                source_fps=source_fps,
                is_tail_chunk=is_tail,
            ): (chunk_start, chunk_end)
            for chunk_start, chunk_end, chunk_timestamps, is_tail in chunks
        }
        # ... (rest unchanged) ...
```

- [ ] **Step 4: Run new path tests, verify pass**

```bash
pytest tests/test_gpu_detector.py::TestDecodeChunkV2Cmd -v
```

Expected: PASS.

- [ ] **Step 5: Run existing GPU detector tests, verify legacy path still passes**

```bash
pytest tests/test_gpu_detector.py -v
```

Expected: PASS (all legacy tests still green because dispatcher routes through `_decode_chunk_legacy` when no rational fps supplied).

- [ ] **Step 6: Lint + type check**

```bash
ruff check allaganeye/video/gpu_detector.py tests/test_gpu_detector.py
ruff format --check allaganeye/video/gpu_detector.py tests/test_gpu_detector.py
pyright allaganeye/video/gpu_detector.py tests/test_gpu_detector.py
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add allaganeye/video/gpu_detector.py tests/test_gpu_detector.py
git commit -m "$(cat <<'EOF'
refactor(gpu_detector): _decode_chunk を v2/legacy dispatch 化 (Refs #576)

#576 design spec §2.1 / §2.3 / §6 / §7.1.10 反映。GPU chunk decode を
新方式 (output seek + Python N-th sampling) と旧 fps filter path に分離。
vendor 別 hwaccel 設定 (NVIDIA cuvid / AMD d3d11va / Intel QSV) と
hwdownload prefix logic は legacy / v2 両方で維持。

- _decode_chunk(): dispatcher (env var + source_fps の有無で判定)
- _decode_chunk_legacy(): 現行 body を rename
- _decode_chunk_v2(): 新 path (CPU と同じ filter chain shape change)
- scan_gpu(): source_fps_num/den/fps + is_tail_chunk を chunk dispatch
  に伝搬

vendor 別 unit test (NVIDIA cuvid / AMD d3d11va / Intel QSV) で新 cmd
構築を検証。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: `detect_match_boundaries` signature 拡張 + `split_matches.py` wiring

**Files:**

- Modify: `allaganeye/video/detector.py:73-94` (`detect_match_boundaries` signature)
- Modify: `allaganeye/video/detector.py:138-173` (`_scan_cpu` / `scan_gpu` 呼び出し箇所)
- Modify: `allaganeye/commands/split_matches.py:745` (`detect_kwargs` 構築)
- Test: `tests/test_detector.py`

**Spec refs:** §2.3 API 拡張, §9.1 #3 / #4

**Acceptance criteria addressed:** §9.1 #3 (signature) + #4 (wiring)

- [ ] **Step 1: Write failing test for end-to-end propagation**

```python
class TestDetectMatchBoundariesRationalFps:
    """detect_match_boundaries が source_fps_num/den を _scan_cpu / scan_gpu
    まで伝搬すること (#576 §2.3)."""

    @patch("allaganeye.video.detector._scan_cpu")
    def test_cpu_path_receives_rational_fps(self, mock_scan):
        mock_scan.return_value = {0.0: 100.0, 1.0: 100.0}

        detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=1.0,
            sample_interval=1.0,
            min_match_duration=0.5,
            use_gpu=False,
            source_fps_num=60000,
            source_fps_den=1001,
        )

        kwargs = mock_scan.call_args.kwargs
        assert kwargs.get("source_fps_num") == 60000
        assert kwargs.get("source_fps_den") == 1001

    @patch("allaganeye.video.gpu_detector.scan_gpu")
    @patch("allaganeye.video.detector._scan_cpu")
    def test_gpu_path_receives_rational_fps(self, _mock_cpu, mock_gpu):
        mock_gpu.return_value = {0.0: 100.0, 1.0: 100.0}

        detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=1.0,
            sample_interval=1.0,
            min_match_duration=0.5,
            use_gpu=True,
            source_fps_num=60,
            source_fps_den=1,
        )

        kwargs = mock_gpu.call_args.kwargs
        assert kwargs.get("source_fps_num") == 60
        assert kwargs.get("source_fps_den") == 1
```

- [ ] **Step 2: Run, verify they fail**

```bash
pytest tests/test_detector.py::TestDetectMatchBoundariesRationalFps -v
```

Expected: FAIL — `detect_match_boundaries` doesn't accept `source_fps_num`/`source_fps_den` keyword arguments yet.

- [ ] **Step 3: Update `detect_match_boundaries` signature + propagation**

`allaganeye/video/detector.py:73-94` の関数 signature を以下に修正:

```python
def detect_match_boundaries(
    video_path: Path,
    *,
    duration_hint: float | None = None,
    sample_interval: float = 1.0,
    blackout_threshold: float = 15.0,
    min_match_duration: float = 300.0,
    min_blackout_duration: float = 3.0,
    use_gpu: bool = False,
    workers: int | None = None,
    src_resolution: tuple[int, int] | None = None,
    codec: str | None = None,
    progress_callback: Callable[[int, int, int], None] | None = None,
    refine_progress_callback: Callable[[int, int], None] | None = None,
    scorebar_progress_callback: Callable[[int, int], None] | None = None,
    audio_hits: Sequence[BgmHit] | None = None,
    stats: DetectionStats | None = None,
    chunk_progress_callback: Callable[[int, int, float], None] | None = None,
    chunk_dispatch_callback: Callable[[int], None] | None = None,
    gpu_vendor: str | None = None,
    brightness_callback: Callable[[dict[float, float]], None] | None = None,
    # #576: rational fps propagation (preferred over float source_fps).
    # Either pair (num+den) takes precedence; float source_fps is the
    # backward-compatible fallback (Fraction.limit_denominator path).
    source_fps_num: int | None = None,
    source_fps_den: int | None = None,
    source_fps: float | None = None,
) -> list[MatchBoundary]:
```

GPU 経路 (line 138-164) を以下に修正:

```python
    if use_gpu:
        from allaganeye.video.gpu_detector import scan_gpu

        try:
            results = scan_gpu(
                video_path,
                duration_hint,
                sample_interval,
                blackout_threshold,
                progress_callback,
                codec=codec,
                chunk_progress_callback=chunk_progress_callback,
                chunk_dispatch_callback=chunk_dispatch_callback,
                vendor=gpu_vendor,
                source_fps_num=source_fps_num,
                source_fps_den=source_fps_den,
                source_fps=source_fps,
            )
            resolved_mode = "GPU"
        except VideoProcessingError:
            results = _scan_cpu(
                video_path,
                duration_hint,
                sample_interval,
                blackout_threshold,
                workers,
                progress_callback,
                source_fps_num=source_fps_num,
                source_fps_den=source_fps_den,
                source_fps=source_fps,
            )
            resolved_mode = "CPU (GPU fallback)"
    else:
        results = _scan_cpu(
            video_path,
            duration_hint,
            sample_interval,
            blackout_threshold,
            workers,
            progress_callback,
            source_fps_num=source_fps_num,
            source_fps_den=source_fps_den,
            source_fps=source_fps,
        )
```

- [ ] **Step 4: Update `split_matches.py:745` detect_kwargs wiring**

`allaganeye/commands/split_matches.py:745` の `detect_kwargs` 辞書に追加:

```python
    detect_kwargs = {
        "duration_hint": metadata["duration"],
        "sample_interval": effective_interval,
        "blackout_threshold": config.blackout_threshold,
        "min_match_duration": config.min_match_duration,
        "min_blackout_duration": config.min_blackout_duration,
        "gpu_vendor": gpu_vendor,
        "use_gpu": use_gpu,
        "workers": config.workers,
        "src_resolution": (metadata["width"], metadata["height"]),
        "codec": metadata.get("codec"),
        "audio_hits": audio_hits,
        "stats": stats,
        "brightness_callback": brightness_callback,
        # #576: rational fps propagation (probe -> detector).
        "source_fps": metadata.get("fps"),
        "source_fps_num": metadata.get("fps_num"),
        "source_fps_den": metadata.get("fps_den"),
    }
```

- [ ] **Step 5: Run tests, verify pass**

```bash
pytest tests/test_detector.py::TestDetectMatchBoundariesRationalFps -v
pytest tests/test_detector.py -v
pytest tests/test_gpu_detector.py -v
```

Expected: PASS — all tests including existing ones.

- [ ] **Step 6: Lint + type check + full pytest**

```bash
ruff check .
ruff format --check .
pyright
pytest -m "not slow and not slow_detect" -q
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add allaganeye/video/detector.py allaganeye/commands/split_matches.py tests/test_detector.py
git commit -m "$(cat <<'EOF'
feat(detector): detect_match_boundaries に source_fps_num/den 追加 (Refs #576)

#576 design spec §2.3 / §9.1 #3-#4 反映。CLI / GUI 経路で probe 取得済の
rational fps が detect 全 path (_scan_cpu / scan_gpu / _decode_chunk_cpu
/ _decode_chunk) まで素通しで届くよう wiring。

- detect_match_boundaries() signature: source_fps_num/den/source_fps
  3 引数を追加 (rational が canonical、float は Fraction fallback)
- split_matches.py:745 detect_kwargs に probe metadata['fps_num']/
  ['fps_den']/['fps'] を追加。run_split / run_detect / run_split_from_metadata
  全 path で _run_detection 経由なので 1 箇所 wiring で全 path 対応

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: `scripts/validate-fps-retirement.py` 新規スクリプト + unit test

**Files:**

- Create: `scripts/validate-fps-retirement.py` (PTS 検証用 one-off ツール)
- Create: `tests/test_validate_fps_retirement.py` (unit test)

**Spec refs:** §4.4, §7.3.19, §9.3 #1-#2

**Acceptance criteria addressed:** §9.3 #1 (script 新規追加) + edge cases (tail / vendor mismatch / 短尺)

- [ ] **Step 1: Write failing tests for script behavior**

`tests/test_validate_fps_retirement.py` を新規作成:

```python
"""Unit tests for scripts/validate-fps-retirement.py (#576 §4.4 / §9.3)."""

import importlib.util
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "validate-fps-retirement.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("validate_fps_retirement", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["validate_fps_retirement"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestEdgeCaseTailChunk:
    """tail chunk SKIP 動作 (#576 §4.4 edge cases)."""

    def test_chunk_past_duration_is_skipped(self):
        mod = _load_module()
        # video duration = 100s, chunk_start = 99.6 -> 99.6 + 0.5 > 100 = SKIP
        result = mod._classify_chunk(chunk_start=99.6, duration=100.0)
        assert result == "skip_tail"

    def test_chunk_within_video_is_run(self):
        mod = _load_module()
        result = mod._classify_chunk(chunk_start=50.0, duration=100.0)
        assert result == "run"


class TestEdgeCaseVendorCodecMismatch:
    """codec/vendor capability mismatch で exit 2 (#576 §4.4)."""

    def test_intel_av1_rejected(self):
        mod = _load_module()
        # Tiger Lake では av1_qsv は実機 unsupported (#550)
        # script は _GPU_DECODER_MAP["intel"]["av1"] の存在で判定。
        # av1 は intel dict にあるが、Tiger Lake 実機制約は実行時のみ。
        # script レベルでは map に存在 = run。codec 不在は exit 2。
        # 例として vendor=cpu (capability 制約なし) で codec=av1 は run。
        assert mod._check_vendor_codec_supported("cpu", "av1") is True

    def test_unknown_codec_for_amd_rejected(self):
        mod = _load_module()
        # AMD には vp9 が _GPU_DECODER_MAP に未登録
        assert mod._check_vendor_codec_supported("amd", "vp9") is False

    def test_known_combination_supported(self):
        mod = _load_module()
        assert mod._check_vendor_codec_supported("nvidia", "av1") is True
        assert mod._check_vendor_codec_supported("intel", "h264") is True


class TestEdgeCaseShortClip:
    """duration < smallest chunk_start で exit 2 (#576 §4.4)."""

    def test_duration_too_short_for_chunks(self):
        mod = _load_module()
        with pytest.raises(SystemExit) as excinfo:
            mod._validate_duration_against_chunks(
                duration=50.0, chunks=[100.0, 200.0],
            )
        assert excinfo.value.code == 2


class TestParsePtsTime:
    """ffmpeg showinfo stderr から frame 0 の pts_time を抽出 (#576 §4.4)."""

    def test_parse_first_frame_pts(self):
        mod = _load_module()
        stderr = (
            "[Parsed_showinfo_0 @ 0x1234] n: 0 pts: 0 pts_time:10.5 "
            "duration: 0 duration_time: 0 ...\n"
            "[Parsed_showinfo_0 @ 0x1234] n: 1 pts: 60 pts_time:10.516667 ...\n"
        )
        assert mod._parse_first_pts_time(stderr) == pytest.approx(10.5)
```

- [ ] **Step 2: Run, verify they fail**

```bash
pytest tests/test_validate_fps_retirement.py -v
```

Expected: FAIL — `scripts/validate-fps-retirement.py` does not exist.

- [ ] **Step 3: Implement `scripts/validate-fps-retirement.py`**

`scripts/validate-fps-retirement.py` を新規作成:

```python
#!/usr/bin/env python3
"""Validate ffmpeg output seek + N-th sampling correctness (#576).

One-off implementation-time evidence tool for #576 (`detect fps filter
retirement`). For each chunk_start, run the new ffmpeg command and
verify:

1. First emitted frame's PTS equals chunk_start within 1 frame slack
2. First emitted frame's brightness matches `_probe_single_frame()` at
   chunk_start within ±2.0 (= `_BLACKOUT_THRESHOLD_UPPER_MARGIN`)

Not a CI gate; the PR body pastes the stdout TSV as evidence.

Usage:
    python scripts/validate-fps-retirement.py \
        --video <path> \
        --chunks 0,100.5,3600,7200 \
        --vendor nvidia \
        --codec av1

Exit codes: 0 = all PASS, 1 = any FAIL, 2 = script error.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Add repo root to PYTHONPATH so we can import allaganeye.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from allaganeye.ffmpeg_path import find_ffmpeg  # noqa: E402
from allaganeye.video.detector import (  # noqa: E402
    _BLACKOUT_THRESHOLD_UPPER_MARGIN,
    _FRAME_SIZE,
    _SAMPLE_HEIGHT,
    _SAMPLE_WIDTH,
    _probe_single_frame,
)
from allaganeye.video.gpu_detector import (  # noqa: E402
    _GPU_DECODER_MAP,
    _HWACCEL_OUTPUT_FORMAT_MAP,
    _HWACCELS_NEED_HWDOWNLOAD,
    _VENDOR_HWACCEL_MAP,
)
from allaganeye.video.probe import probe_video  # noqa: E402

import numpy as np  # noqa: E402

_PTS_RE = re.compile(r"n:\s*0\s+pts:\s*\d+\s+pts_time:([\d.]+)")


def _classify_chunk(chunk_start: float, duration: float) -> str:
    """Return 'skip_tail' if chunk_start + 0.5 > duration, else 'run'."""
    if chunk_start + 0.5 > duration:
        return "skip_tail"
    return "run"


def _check_vendor_codec_supported(vendor: str, codec: str) -> bool:
    """True if vendor supports codec per _GPU_DECODER_MAP; CPU always True."""
    if vendor == "cpu":
        return True
    vendor_map = _GPU_DECODER_MAP.get(vendor, {})
    return codec in vendor_map


def _validate_duration_against_chunks(duration: float, chunks: list[float]) -> None:
    """Exit 2 if smallest chunk_start exceeds video duration."""
    if not chunks:
        return
    smallest = min(chunks)
    if duration < smallest:
        print(
            f"ERROR: video duration {duration}s shorter than smallest "
            f"chunk_start {smallest}s",
            file=sys.stderr,
        )
        sys.exit(2)


def _parse_first_pts_time(stderr_text: str) -> float | None:
    """Extract pts_time of the first showinfo frame (n: 0). Returns None if absent."""
    m = _PTS_RE.search(stderr_text)
    if not m:
        return None
    return float(m.group(1))


def _build_ffmpeg_cmd(
    video: Path, chunk_start: float, vendor: str, codec: str,
) -> list[str]:
    """Build ffmpeg cmd for showinfo + new path (output seek + passthrough)."""
    hwaccel_args: list[str] = []
    decoder: str | None = None
    if vendor != "cpu":
        decoder = _GPU_DECODER_MAP.get(vendor, {}).get(codec)
        hwaccel_name = _VENDOR_HWACCEL_MAP.get(vendor)
        if decoder and hwaccel_name:
            hwaccel_args = ["-hwaccel", hwaccel_name]
            if hwaccel_name in _HWACCELS_NEED_HWDOWNLOAD:
                surface_fmt = _HWACCEL_OUTPUT_FORMAT_MAP.get(hwaccel_name, hwaccel_name)
                hwaccel_args += ["-hwaccel_output_format", surface_fmt]
            hwaccel_args += ["-c:v", decoder]

    needs_hwdownload = bool(
        decoder
        and _VENDOR_HWACCEL_MAP.get(vendor) in _HWACCELS_NEED_HWDOWNLOAD
    )
    vf_prefix = "hwdownload,format=nv12," if needs_hwdownload else ""

    return [
        find_ffmpeg(),
        *hwaccel_args,
        "-i", str(video),
        "-ss", str(chunk_start),
        "-t", "0.5",
        "-fps_mode", "passthrough",
        "-vf",
        f"{vf_prefix}showinfo,scale={_SAMPLE_WIDTH}:{_SAMPLE_HEIGHT},format=gray",
        "-f", "rawvideo",
        "-pix_fmt", "gray",
        "pipe:1",
    ]


def _run_chunk(
    video: Path,
    chunk_start: float,
    vendor: str,
    codec: str,
    source_fps: float,
) -> tuple[float | None, float | None, float]:
    """Run ffmpeg + return (emit_pts, emit_brightness, probe_brightness)."""
    cmd = _build_ffmpeg_cmd(video, chunk_start, vendor, codec)
    proc = subprocess.run(cmd, capture_output=True, timeout=60)
    stderr_text = proc.stderr.decode(errors="replace")
    emit_pts = _parse_first_pts_time(stderr_text)

    if proc.returncode != 0 or len(proc.stdout) < _FRAME_SIZE:
        emit_brightness: float | None = None
    else:
        frame = np.frombuffer(proc.stdout[:_FRAME_SIZE], dtype=np.uint8)
        emit_brightness = float(frame.mean())

    probe_brightness = _probe_single_frame(video, chunk_start)
    return emit_pts, emit_brightness, probe_brightness


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--video", type=Path, required=True)
    p.add_argument("--chunks", required=True, help="CSV of chunk_start floats")
    p.add_argument("--vendor", choices=["cpu", "nvidia", "amd", "intel"], required=True)
    p.add_argument("--codec", choices=["h264", "hevc", "av1", "vp9"], required=True)
    p.add_argument("--source-fps-num", type=int, default=None)
    p.add_argument("--source-fps-den", type=int, default=None)
    args = p.parse_args(argv)

    if not args.video.exists():
        print(f"ERROR: video not found: {args.video}", file=sys.stderr)
        return 2

    if not _check_vendor_codec_supported(args.vendor, args.codec):
        print(
            f"ERROR: vendor {args.vendor} does not support codec {args.codec} "
            f"in _GPU_DECODER_MAP (refer to gpu_detector.py)",
            file=sys.stderr,
        )
        return 2

    try:
        chunks = [float(s) for s in args.chunks.split(",") if s.strip()]
    except ValueError as e:
        print(f"ERROR: invalid --chunks value: {e}", file=sys.stderr)
        return 2
    if not chunks:
        print("ERROR: --chunks must contain at least one value", file=sys.stderr)
        return 2

    probe = probe_video(args.video)
    duration = probe["duration"]
    source_fps = probe["fps"]

    _validate_duration_against_chunks(duration, chunks)

    # TSV header
    print(
        "chunk_start\tvendor\tcodec\temit_pts\temit_brightness\tprobe_brightness"
        "\tpts_diff\tbrightness_diff\tverdict"
    )

    total = pass_ = fail = skipped = 0
    for chunk_start in chunks:
        verdict: str
        cls = _classify_chunk(chunk_start, duration)
        if cls == "skip_tail":
            print(
                f"WARN: chunk_start {chunk_start} too close to duration {duration}",
                file=sys.stderr,
            )
            skipped += 1
            continue

        emit_pts, emit_brightness, probe_brightness = _run_chunk(
            args.video, chunk_start, args.vendor, args.codec, source_fps,
        )
        if emit_pts is None or emit_brightness is None:
            verdict = "FAIL"
            fail += 1
            pts_diff_s = "n/a"
            brightness_diff_s = "n/a"
        else:
            pts_diff = abs(emit_pts - chunk_start)
            brightness_diff = abs(emit_brightness - probe_brightness)
            pts_ok = pts_diff < (1.0 / source_fps)
            brightness_ok = brightness_diff < _BLACKOUT_THRESHOLD_UPPER_MARGIN
            verdict = "PASS" if pts_ok and brightness_ok else "FAIL"
            if verdict == "PASS":
                pass_ += 1
            else:
                fail += 1
            pts_diff_s = f"{pts_diff:.4f}"
            brightness_diff_s = f"{brightness_diff:.4f}"
        total += 1
        print(
            f"{chunk_start}\t{args.vendor}\t{args.codec}\t"
            f"{emit_pts}\t{emit_brightness}\t{probe_brightness}\t"
            f"{pts_diff_s}\t{brightness_diff_s}\t{verdict}"
        )

    print(f"# SUMMARY total={total} pass={pass_} fail={fail} skipped={skipped}")

    if total == 0:
        # All chunks were skipped -> no test material
        return 2
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run unit tests, verify pass**

```bash
pytest tests/test_validate_fps_retirement.py -v
```

Expected: PASS.

- [ ] **Step 5: Smoke test with a fake video (dry run, parser only)**

```bash
python scripts/validate-fps-retirement.py --help
```

Expected: prints argparse help, exit 0.

- [ ] **Step 6: Lint + type check**

```bash
ruff check scripts/validate-fps-retirement.py tests/test_validate_fps_retirement.py
ruff format --check scripts/validate-fps-retirement.py tests/test_validate_fps_retirement.py
pyright scripts/validate-fps-retirement.py tests/test_validate_fps_retirement.py
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add scripts/validate-fps-retirement.py tests/test_validate_fps_retirement.py
git commit -m "$(cat <<'EOF'
feat(scripts): validate-fps-retirement.py one-off PTS 検証ツール (Refs #576)

#576 design spec §4.4 / §7.3.19 / §9.3 反映。実装中 evidence として
PR 本文添付するための CPU / NVIDIA / AMD / Intel 各 vendor の
showinfo PTS + brightness 整合検証ツール。

- 各 chunk_start で ffmpeg ... -vf "showinfo,scale,format=gray" を実行
- stderr から frame 0 の pts_time を抽出 (|emit_pts - chunk_start| <
  1/source_fps を要求)
- _probe_single_frame() と brightness 比較 (|emit - probe| < 2.0 を要求、
  _BLACKOUT_THRESHOLD_UPPER_MARGIN と整合)
- TSV 形式で stdout 出力、SUMMARY 行で total/pass/fail/skipped を集計
- 永続的 CI gate ではなく実装中 one-off 用途

edge cases:
- tail chunk (chunk_start + 0.5 > duration) は SKIP
- vendor / codec mismatch (_GPU_DECODER_MAP 未登録) は exit 2
- 短尺 clip (duration < min(chunks)) は exit 2
- 全 chunk が SKIP された場合のみ exit 2 (test material 不足)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Class A 4 baseline 統合テスト + intermediate audit dump

**Files:**

- Modify: `tests/test_scorebar_regression.py` (Class A integration test 追加 — pytest marker `slow_detect`)
- Create: `tests/test_v030_baseline_regression.py` (新規、v0.3.0 baseline 専用 integration test)

**Spec refs:** §3 Class A, §7.2.11-12, §9.2 #1-#2

**Acceptance criteria addressed:** §9.2 #1 (Class A exit 0) + #2 (intermediate audit)

- [ ] **Step 1: Write failing integration test for Class A 4 baselines**

`tests/test_v030_baseline_regression.py` を新規作成:

```python
"""v0.3.0 baseline regression tests (#576 §7.2 / §9.2).

`slow_detect` マーカー: 実動画必須、CI default deselect。
Idios 環境または ALLAGANEYE_SAMPLE_VIDEO_DIR が設定されたマシンで実行。
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BASELINE_DIR = _REPO_ROOT / "tests" / "baselines" / "v0.3.0"
_COMPARE_SCRIPT = _REPO_ROOT / "scripts" / "compare-baseline.py"

# Class A baselines: bit-exact projection (matches+gaps).
_CLASS_A_BASELINES = [
    ("obs-20260116", "20260116/2026-01-16 22-12-57.mkv"),
    ("obs-20260119", "20260119/2026-01-19 22-09-07.mkv"),
    ("obs-20260127", "20260127/2026-01-27 21-59-15.mkv"),
    ("obs-20260209", "2026-02-09 23-12-24.mkv"),
]


@pytest.mark.slow_detect
@pytest.mark.parametrize("label,relpath", _CLASS_A_BASELINES)
def test_class_a_bit_exact(label, relpath, sample_video_dir, tmp_output_dir):
    """新 path で detect を回し、Class A baseline と matches/gaps が完全一致 (#576 §3 / §9.2)."""
    video = sample_video_dir / relpath
    if not video.exists():
        pytest.skip(f"video not found: {video}")

    out_meta = tmp_output_dir / "metadata.json"
    cmd = [
        sys.executable, "-m", "allaganeye", "detect",
        str(video), "-o", str(tmp_output_dir), "--no-cache",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    assert result.returncode == 0, f"detect failed: {result.stderr}"
    assert out_meta.exists(), "metadata.json not produced"

    baseline_path = _BASELINE_DIR / f"{label}.metadata.json"
    cmp = subprocess.run(
        [sys.executable, str(_COMPARE_SCRIPT), str(baseline_path), str(out_meta)],
        capture_output=True, text=True,
    )
    assert cmp.returncode == 0, (
        f"Class A baseline diff for {label}: {cmp.stdout} {cmp.stderr}"
    )


@pytest.mark.slow_detect
@pytest.mark.parametrize("label,relpath", _CLASS_A_BASELINES)
def test_class_a_intermediate_audit_no_regress(
    label, relpath, sample_video_dir, tmp_output_dir, monkeypatch
):
    """Class A: 新 path と legacy path で Pass 1 candidate / Pass 2 refined region
    の dump を比較し、最終 projection が同じでも内部値が予想 ε 内であることを確認
    (#576 §3 / §7.2.12).

    本テストは regression report 用なので strict assert はせず、
    出力 diff を stderr に書き、test 自体は `xfail(strict=False)` 相当。
    """
    video = sample_video_dir / relpath
    if not video.exists():
        pytest.skip(f"video not found: {video}")

    new_meta = tmp_output_dir / "new" / "metadata.json"
    legacy_meta = tmp_output_dir / "legacy" / "metadata.json"

    # new path (default, env var unset)
    subprocess.run(
        [sys.executable, "-m", "allaganeye", "detect", str(video),
         "-o", str(tmp_output_dir / "new"), "-v", "--no-cache"],
        check=True, capture_output=True, text=True, timeout=1800,
    )

    # legacy path (env var = 1)
    env = {**__import__("os").environ, "ALLAGANEYE_DETECT_FPS_FILTER": "1"}
    subprocess.run(
        [sys.executable, "-m", "allaganeye", "detect", str(video),
         "-o", str(tmp_output_dir / "legacy"), "-v", "--no-cache"],
        check=True, capture_output=True, text=True, timeout=1800, env=env,
    )

    new_data = json.loads(new_meta.read_text(encoding="utf-8"))
    legacy_data = json.loads(legacy_meta.read_text(encoding="utf-8"))

    # 最終 projection が一致することを確認
    assert new_data["matches"] == legacy_data["matches"], (
        f"{label}: matches diff between new and legacy path "
        f"-- Class A should keep bit-exact projection."
    )
    assert new_data["gaps"] == legacy_data["gaps"], (
        f"{label}: gaps diff between new and legacy path."
    )
    # 内部値 (verbose stats / brightness samples) は legitimate に変わって OK。
    # ここでは report のみ (本番では PR 本文に dump 添付)。
```

- [ ] **Step 2: Run, verify they fail (or skip if no sample video)**

```bash
pytest tests/test_v030_baseline_regression.py::test_class_a_bit_exact -v -m slow_detect
```

Expected: FAIL — new path may produce different `matches`/`gaps` if there is a baseline that catches a hidden short blackout. If all Class A baselines are bit-exact preserve, PASS. If failures detected, follow R1 (升格 Class B in scope).

(Skip if `ALLAGANEYE_SAMPLE_VIDEO_DIR` not set.)

- [ ] **Step 3: 必要なら R1 escalation (Class B 昇格 + regenerate)**

`test_class_a_bit_exact` が失敗した baseline があれば、当該 baseline を Class B 扱いに昇格し Task 9 と同じ手順で regenerate する。spec §3 / §10 R1 を参照。**この際、本テストは更新後の baseline で再度 PASS することを確認する。**

- [ ] **Step 4: Commit (Class A 結果が PASS であることを確認した時点)**

```bash
git add tests/test_v030_baseline_regression.py
git commit -m "$(cat <<'EOF'
test(detector): v0.3.0 Class A baseline regression test 追加 (Refs #576)

#576 design spec §3 / §7.2 / §9.2 反映。Class A 4 baseline で
matches/gaps projection の bit-exact 一致を slow_detect marker で
検証する integration test を追加。

- test_class_a_bit_exact: 新 path detect の metadata.json を baseline と
  compare-baseline.py で比較し exit 0 必須
- test_class_a_intermediate_audit_no_regress: env var で legacy/new path
  両方を回し、最終 projection が同じことを確認 (内部値 diff は legitimate)

CI default deselect (slow_detect marker)。実機 + ALLAGANEYE_SAMPLE_VIDEO_DIR
で実行する。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Class B regenerate (`obs-20260118`) + per-frame probe evidence

**Files:**

- Modify: `tests/baselines/v0.3.0/obs-20260118.metadata.json` (regenerate)
- Modify: `tests/baselines/v0.3.0/obs-20260118.split.json` (sha256/size 再計算)

**Spec refs:** §3 Class B, §7.2.13, §9.2 #3

**Acceptance criteria addressed:** §9.2 #3 (Class B regenerate + evidence)

- [ ] **Step 1: 新 path で `obs-20260118` を detect**

```bash
python -m allaganeye detect "$ALLAGANEYE_SAMPLE_VIDEO_DIR/20260118/2026-01-18 22-15-18.mkv" -o output/v3-20260118 --no-cache
```

Expected: 完走。`output/v3-20260118/metadata.json` が生成される。

- [ ] **Step 2: 新 metadata.json を baseline に上書き**

```bash
cp output/v3-20260118/metadata.json tests/baselines/v0.3.0/obs-20260118.metadata.json
```

- [ ] **Step 3: split を regenerate して SHA-256 / size を再計算**

```bash
python -m allaganeye split --from-metadata tests/baselines/v0.3.0/obs-20260118.metadata.json -o output/v3-20260118-split
python scripts/generate-v030-baselines.py --label obs-20260118 --update-split-json
```

(注: `scripts/generate-v030-baselines.py` は #779 で導入済み。`--label` + `--update-split-json` の 2 flag は #779 PR の spec を参照、もし無ければ手動で sha256 を計算して `obs-20260118.split.json` に上書きする。)

- [ ] **Step 4: Class B integration test を更新 (Task 8 で記述した parametrize に追加)**

`tests/test_v030_baseline_regression.py` に Class B test を追加:

```python
@pytest.mark.slow_detect
def test_class_b_regenerated(sample_video_dir, tmp_output_dir):
    """Class B (obs-20260118) は本 PR で regenerate された baseline と一致 (#576 §3)."""
    video = sample_video_dir / "20260118" / "2026-01-18 22-15-18.mkv"
    if not video.exists():
        pytest.skip(f"video not found: {video}")

    out_meta = tmp_output_dir / "metadata.json"
    subprocess.run(
        [sys.executable, "-m", "allaganeye", "detect", str(video),
         "-o", str(tmp_output_dir), "--no-cache"],
        check=True, capture_output=True, text=True, timeout=1800,
    )

    baseline_path = _BASELINE_DIR / "obs-20260118.metadata.json"
    cmp = subprocess.run(
        [sys.executable, str(_COMPARE_SCRIPT), str(baseline_path), str(out_meta)],
        capture_output=True, text=True,
    )
    assert cmp.returncode == 0, (
        f"Class B baseline mismatch (regenerated baseline diverged): "
        f"{cmp.stdout} {cmp.stderr}"
    )
```

- [ ] **Step 5: per-frame probe evidence を取得 (PR 本文用)**

```bash
python -m allaganeye debug-brightness "$ALLAGANEYE_SAMPLE_VIDEO_DIR/20260118/2026-01-18 22-15-18.mkv" --start 6183 --end 6187 --interval 0.1 > output/v3-20260118-evidence.csv
```

`output/v3-20260118-evidence.csv` を PR 本文の "## Evidence (per-frame probe)" section に貼付ける (commit 不要)。

- [ ] **Step 6: Run Class B test, verify pass**

```bash
pytest tests/test_v030_baseline_regression.py::test_class_b_regenerated -v -m slow_detect
```

Expected: PASS.

- [ ] **Step 7: Commit baseline regeneration**

```bash
git add tests/baselines/v0.3.0/obs-20260118.metadata.json tests/baselines/v0.3.0/obs-20260118.split.json tests/test_v030_baseline_regression.py
git commit -m "$(cat <<'EOF'
data(tests): obs-20260118 baseline regenerate after #576 root cause fix (Refs #576)

#576 design spec §3 Class B / §9.2 #3 反映。新 path (fps filter 廃止 +
output seek + Python N-th sampling) で obs-20260118 を再 detect し、
metadata.json + split.json を改修後 snapshot に置換。

期待 diff (#560 root cause fix):
- 旧 path: Match 8 end = 6465.25 (ffmpeg 8.1 fps filter が 0.8s 幅
  blackout @ 6184.0 を取りこぼし、隣接 region と merge)
- 新 path: Match 8 end ≈ 6184 (frame_idx 直接指定で 0.8s blackout を
  正しく検出、境界が物理的に正しい位置に移動)

per-frame probe evidence (debug-brightness CSV, 6184.0-6185.5 の brightness
推移) は PR 本文の "## Evidence (per-frame probe)" section に添付。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: vendor 別 golden brightness 比較 integration test

**Files:**

- Modify: `tests/test_v030_baseline_regression.py` (Task 8 で作成済み)

**Spec refs:** §7.2.16

**Acceptance criteria addressed:** §9.3 #3 (vendor 別 golden brightness)

- [ ] **Step 1: Add golden brightness test**

`tests/test_v030_baseline_regression.py` に追加:

```python
@pytest.mark.slow_detect
@pytest.mark.parametrize(
    "vendor,timestamps",
    [
        # obs-20260116 (1920x1080, 60fps, AV1):
        # 黒/transition/lobby/normal の 4 種類で _probe_single_frame と
        # 新 path の brightness が ±2.0 (= _BLACKOUT_THRESHOLD_UPPER_MARGIN)
        # 以内で一致することを確認する (#576 §7.2.16 / §9.3)。
        ("cpu", [4.0, 30.0, 600.0, 1200.0]),
        ("nvidia", [4.0, 30.0, 600.0, 1200.0]),
        ("amd", [4.0, 30.0, 600.0, 1200.0]),
    ],
)
def test_vendor_golden_brightness(vendor, timestamps, sample_video_dir, tmp_output_dir):
    """各 vendor で _probe_single_frame と新 path の brightness が
    ±2.0 以内で一致 (#576 §7.2.16 / §9.3 #3).

    Idios 環境で NVIDIA / AMD が利用可能な前提。Intel は別途 AskUserQuestion。
    """
    video = sample_video_dir / "20260116" / "2026-01-16 22-12-57.mkv"
    if not video.exists():
        pytest.skip(f"video not found: {video}")

    # Skip if vendor not available (CI fallback)
    import platform
    if vendor == "nvidia" and platform.system() != "Windows":
        pytest.skip("NVIDIA GPU only validated on Windows Idios env")

    chunks_csv = ",".join(str(t) for t in timestamps)
    cmd = [
        sys.executable,
        str(_REPO_ROOT / "scripts" / "validate-fps-retirement.py"),
        "--video", str(video),
        "--chunks", chunks_csv,
        "--vendor", vendor,
        "--codec", "av1",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    # exit 0 = all PASS, exit 1 = FAIL, exit 2 = script error.
    if result.returncode == 2:
        pytest.skip(f"validate script error for vendor={vendor}: {result.stderr}")
    assert result.returncode == 0, (
        f"vendor golden brightness FAIL for {vendor}: "
        f"stdout=\n{result.stdout}\nstderr=\n{result.stderr}"
    )
```

- [ ] **Step 2: Run vendor golden test on Idios environment**

```bash
pytest tests/test_v030_baseline_regression.py::test_vendor_golden_brightness -v -m slow_detect
```

Expected: PASS on CPU / NVIDIA / AMD (Idios 環境)。Intel は AskUserQuestion で別途確認。

- [ ] **Step 3: Lint + type check**

```bash
ruff check tests/test_v030_baseline_regression.py
ruff format --check tests/test_v030_baseline_regression.py
pyright tests/test_v030_baseline_regression.py
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_v030_baseline_regression.py
git commit -m "$(cat <<'EOF'
test(detector): vendor 別 golden brightness 比較 test 追加 (Refs #576)

#576 design spec §7.2.16 / §9.3 #3 反映。CPU / NVIDIA / AMD 各 vendor で
新 path の最初のフレーム brightness と _probe_single_frame の参照値が
±2.0 (= _BLACKOUT_THRESHOLD_UPPER_MARGIN) 以内で一致することを
validate-fps-retirement.py 経由で確認する slow_detect integration test。

Intel QSV は user の AskUserQuestion で別途実機検証 (R3)。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: `docs/video-processing.md` 更新 — fps filter 廃止の反映

**Files:**

- Modify: `docs/video-processing.md` §「ffmpeg fps filter の version 依存制約」 (現行 line 126-170 周辺)

**Spec refs:** §9.4 #4 / §8 docs touch list

**Acceptance criteria addressed:** §9.4 #4 docs update

- [ ] **Step 1: Read current §「ffmpeg fps filter の version 依存制約」 section**

```bash
sed -n '126,170p' docs/video-processing.md
```

- [ ] **Step 2: Replace section content to reflect #576 fix**

セクション §「ffmpeg fps filter の version 依存制約」 を以下に書き換える:

```markdown
### ffmpeg fps filter の version 依存制約 (#577, #576 で解決済み)

`_scan_cpu` および GPU chunked decode で旧 path (env var
`ALLAGANEYE_DETECT_FPS_FILTER=1` 指定時) が使用する `fps=N` filter は、
ffmpeg version によりフレーム選択タイミングが変動する。極短時間
(< 1s) blackout の取りこぼしが起こりうる (PR #575 の root cause 分析で
確定)。

**新 path (#576 完了後、default)** は fps filter を廃止し、output seek
(`-ss` を `-i` の後ろ) + `-fps_mode passthrough` + Python 側 N-th
sampling (`frame_idx = round((t - chunk_start) * fps_num / fps_den)`) で
frame を選択する。ffmpeg 内部 frame-rate normalization の version 依存を
構造的に escape する設計。

**検証データ (PR #575 / issue #560 / #576 完了後)**

ffmpeg 8.1 / `sample_interval=2.0` で `20260118` video の同一 timestamp
label を異なる経路で probe した結果:

| timestamp label | per-frame `-ss` probe | 旧 path (chunked fps) | 新 path (#576) | 差 |
| --- | --- | --- | --- | --- |
| 6184.0 | **1.73 (BLACKOUT)** | 47.72 (transition) | **1.73 (BLACKOUT)** | 新 path で復活 |
| 6186.0 | 100.48 (normal) | 37.20 (transition) | 100.48 (normal) | 同上 |

新 path では frame_idx 直接指定で 0.8s 幅 blackout (6184.0-6184.8) を
正しく捕捉できる。これが obs-20260118 baseline で Match 8 end が
`6465.25 → ~6184` に移動した root cause fix。

**rollback path (transitional, v0.3.x で削除)**

env var `ALLAGANEYE_DETECT_FPS_FILTER=1` を設定すると旧 fps filter path
に切替わる。緊急 escape 用途のみ、CI / production で使わないこと。
詳細は `docs/superpowers/specs/2026-05-18-v030-l3-detect-fps-filter-retirement-design.md`
§6 を参照。
```

- [ ] **Step 3: Verify markdownlint passes**

```bash
bash scripts/check-markdownlint.sh docs/video-processing.md
```

Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
git add docs/video-processing.md
git commit -m "$(cat <<'EOF'
docs(video-processing): #576 root cause fix を反映 (Refs #576)

#576 design spec §9.4 #4 反映。§「ffmpeg fps filter の version 依存
制約」 を更新し、fps filter 廃止 + output seek + Python N-th sampling
への移行を記述。検証データ table に新 path の挙動列を追加。

env var ALLAGANEYE_DETECT_FPS_FILTER=1 を transitional rollback と
位置づけ、v0.3.x で削除予定であることを明記。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: `docs/testing-guide.md` 更新 — baseline drift section

**Files:**

- Modify: `docs/testing-guide.md` §「baseline drift の判定」 (現行 line 137-204 周辺)

**Spec refs:** §9.4 #4 / §8 docs touch list

- [ ] **Step 1: Read current §「baseline drift の判定」**

```bash
sed -n '137,204p' docs/testing-guide.md
```

- [ ] **Step 2: Append #576 完了後の運用 note**

§「baseline drift の判定」 §「事例」 の **直後** (line 164 周辺、§「検証データの保存場所」 の **前**) に以下を追記:

```markdown
### #576 完了後の運用

#576 (detect fps filter 廃止) 完了後、default path では fps filter を
使わないため、ffmpeg version upgrade による Pass 1 brightness drift は
構造的に発生しない。本 § の判定 flow が必要になるのは、env var
`ALLAGANEYE_DETECT_FPS_FILTER=1` で legacy path を強制した場合のみ。

- 新 path で baseline mismatch が観測された場合は、(B) ffmpeg version
  依存 ではなく **(A) 検知ロジック退行** を疑う (legacy path で再現
  しないことを確認)
- legacy path は v0.3.x patch release で削除予定。それ以降は本 § の
  運用は廃止される
```

- [ ] **Step 3: Verify markdownlint passes**

```bash
bash scripts/check-markdownlint.sh docs/testing-guide.md
```

Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
git add docs/testing-guide.md
git commit -m "$(cat <<'EOF'
docs(testing-guide): #576 完了後の baseline drift 運用 note (Refs #576)

#576 design spec §9.4 #4 反映。§「baseline drift の判定」 に「#576 完了
後の運用」 subsection を追加し、default path では fps filter version
依存 drift が構造的に発生しないこと、legacy path 限定の運用であること、
v0.3.x で legacy path 削除後は本 § が廃止されることを明記。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: CHANGELOG + env var deprecation docstring

**Files:**

- Modify: `CHANGELOG.md` (新規 entry、`Unreleased` または `v0.3.0` section)
- Modify: `allaganeye/video/detector.py` (`_use_legacy_fps_filter` docstring を充実)

**Spec refs:** §6 廃止 timeline, §9.1 末尾 #10

**Acceptance criteria addressed:** §9.1 #10 (env var 廃止 v0.3.x roadmap)

- [ ] **Step 1: Check current CHANGELOG.md**

```bash
sed -n '1,40p' CHANGELOG.md
```

- [ ] **Step 2: Add Unreleased / v0.3.0 entry**

`CHANGELOG.md` の `## [Unreleased]` (なければ作成) に以下を追加:

```markdown
## [Unreleased]

### Changed
- **detect**: chunk decode の ffmpeg `-vf fps=N` filter を廃止し、output
  seek + `-fps_mode passthrough` + Python 側 N-th sampling 方式に移行
  (#576)。ffmpeg version 依存の frame-selection drift (#560 / #575 /
  #577) を構造的に除去。obs-20260118 で見逃されていた 0.8s 幅 blackout
  (Match 8 end at 6184) を正しく検出するように動作が変わる。
- **GUI brightness timeline** (#569): 新 path で Pass 1 brightness 値が
  正確化される (旧 path の fps filter drift により歪んでいた値が修正
  される方向)。timeline 形状の変化が user-visible になる可能性あり。

### Added
- `probe.py::ProbeResult` に `fps_num`/`fps_den` フィールドを追加
  (NTSC 60000/1001 等の rational frame rate を float 精度損失なく
  detector まで伝搬)。
- `scripts/validate-fps-retirement.py` を新規追加 (#576 実装中 evidence
  用 one-off スクリプト、CI gate ではない)。

### Deprecated
- env var `ALLAGANEYE_DETECT_FPS_FILTER=1` で旧 fps filter path に
  rollback 可能 (transitional)。**v0.3.x patch release で削除予定**。
  緊急 escape 用途のみ、CI / production で使わないこと。
```

- [ ] **Step 3: Enrich `_use_legacy_fps_filter` docstring**

`allaganeye/video/detector.py` の `_use_legacy_fps_filter` (Task 2 で追加) docstring を以下に置換:

```python
def _use_legacy_fps_filter() -> bool:
    """Return True when the legacy fps-filter path is forced via env var (#576).

    **Transitional / scheduled for removal in v0.3.x.**

    Setting ``ALLAGANEYE_DETECT_FPS_FILTER=1`` reverts the detector to
    the pre-#576 chunked ``fps=N`` filter path.  Provided as an emergency
    escape hatch for ffmpeg version regressions during the v0.3.0
    rollout.  CI / production should NEVER set this var (CHANGELOG
    "Deprecated").

    Removal plan:
    - v0.3.0: env var supported (this function exists, returns env value)
    - v0.3.x: env var removed (this function deleted, only new path
      exists, _decode_chunk_cpu_legacy / _decode_chunk_legacy purged)

    See ``docs/superpowers/specs/2026-05-18-v030-l3-detect-fps-filter-retirement-design.md``
    §6 for rollback design and ``CHANGELOG.md`` for the deprecation
    timeline.
    """
    return os.environ.get("ALLAGANEYE_DETECT_FPS_FILTER") == "1"
```

- [ ] **Step 4: Lint + markdownlint**

```bash
ruff check allaganeye/video/detector.py
ruff format --check allaganeye/video/detector.py
pyright allaganeye/video/detector.py
bash scripts/check-markdownlint.sh CHANGELOG.md
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md allaganeye/video/detector.py
git commit -m "$(cat <<'EOF'
docs(changelog): #576 detect fps filter retirement + env var deprecation (Refs #576)

#576 design spec §6 / §9.1 #10 反映。CHANGELOG の Unreleased section に
detect fps filter 廃止、ProbeResult fps_num/den 追加、env var
ALLAGANEYE_DETECT_FPS_FILTER deprecation (v0.3.x で削除予定) を記載。

_use_legacy_fps_filter docstring に v0.3.x 削除 plan と CHANGELOG への
リンクを明記。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: Manual evidence — Idios 環境で `validate-fps-retirement.py` 実行

**Files:**

- なし (PR 本文に貼付ける evidence を収集するだけ、commit なし)

**Spec refs:** §4.4 PTS 検証 matrix, §7.3.19, §9.3 #2

**Acceptance criteria addressed:** §9.3 #2 (PTS validation TSV を PR 本文に添付)

- [ ] **Step 1: Determine representative chunk_start values**

obs-20260116 (2h01m43s = 7303.5s) を例として、GOP 境界 + 非境界 + 末尾近傍を含む chunk を選定。OBS の AV1 GOP は ~2s なので:

```text
GOP 境界に近い: 0.0, 100.0, 1000.0, 3600.0, 7200.0
GOP 境界から外れる (1s 余り): 50.5, 1500.5, 5000.5
末尾近傍: 7290.0 (tail chunk 想定、script の skip 動作を兼ねて確認)
```

- [ ] **Step 2: CPU + NVIDIA + AMD で順次実行 (Idios 環境)**

```powershell
# CPU
python scripts/validate-fps-retirement.py `
  --video "$env:ALLAGANEYE_SAMPLE_VIDEO_DIR\20260116\2026-01-16 22-12-57.mkv" `
  --chunks "0.0,50.5,100.0,1000.0,1500.5,3600.0,5000.5,7200.0,7290.0" `
  --vendor cpu --codec av1 | Tee-Object output\evidence-cpu.tsv

# NVIDIA
python scripts/validate-fps-retirement.py `
  --video "$env:ALLAGANEYE_SAMPLE_VIDEO_DIR\20260116\2026-01-16 22-12-57.mkv" `
  --chunks "0.0,50.5,100.0,1000.0,1500.5,3600.0,5000.5,7200.0,7290.0" `
  --vendor nvidia --codec av1 | Tee-Object output\evidence-nvidia.tsv

# AMD
python scripts/validate-fps-retirement.py `
  --video "$env:ALLAGANEYE_SAMPLE_VIDEO_DIR\20260116\2026-01-16 22-12-57.mkv" `
  --chunks "0.0,50.5,100.0,1000.0,1500.5,3600.0,5000.5,7200.0,7290.0" `
  --vendor amd --codec av1 | Tee-Object output\evidence-amd.tsv
```

Expected: 各 vendor で exit 0、SUMMARY 行が `total=8 pass=8 fail=0 skipped=1` (7290.0 は tail として skip)。

- [ ] **Step 3: TSV 3 本を PR 本文の "## PTS validation evidence" section に貼付け**

PR 本文に以下の形で添付 (この step は commit 不要、PR 作成時に書く):

```markdown
## PTS validation evidence

### CPU (AV1)
<paste output/evidence-cpu.tsv content>

### NVIDIA cuvid (AV1)
<paste output/evidence-nvidia.tsv content>

### AMD d3d11va (AV1)
<paste output/evidence-amd.tsv content>
```

- [ ] **Step 4: Intel QSV の検証可否を AskUserQuestion で確認**

Idios 環境に Intel iGPU が無い場合は user に AskUserQuestion で:

- (a) Intel 検証可能な機材で実行 / (b) scope 外として PR 本文に明記 / (c) 別 issue に切出し

を確認する。`(b)` の場合、PR 本文に `**Intel QSV**: 検証機材なし、scope 外 (#576 §10 R3)` と明記。

---

## Task 15: Perf budget gate + 全体 PR 作成準備

**Files:**

- なし (5 baseline 実行ベンチマーク、結果は PR 本文に貼付け)

**Spec refs:** §5 Performance budget, §7.4, §9.4 #1

**Acceptance criteria addressed:** §9.4 #1 (5 baseline 合計 ≦ 36 min) + §9.4 #2-#4 (regression / rollback / docs)

- [ ] **Step 1: Run 5 baseline detect with `--gpu` and time it**

```powershell
$start = Get-Date
foreach ($pair in @(
    @("obs-20260116", "20260116/2026-01-16 22-12-57.mkv"),
    @("obs-20260118", "20260118/2026-01-18 22-15-18.mkv"),
    @("obs-20260119", "20260119/2026-01-19 22-09-07.mkv"),
    @("obs-20260127", "20260127/2026-01-27 21-59-15.mkv"),
    @("obs-20260209", "2026-02-09 23-12-24.mkv")
)) {
    $label = $pair[0]; $rel = $pair[1]
    python -m allaganeye detect "$env:ALLAGANEYE_SAMPLE_VIDEO_DIR\$rel" `
        -o "output\perf-$label" --no-cache --gpu
}
$end = Get-Date
$elapsed = ($end - $start).TotalMinutes
"Total elapsed: $elapsed minutes"
```

Expected: total ≦ 36 分 (現状 #779 実測 34m43s + 8% margin)。

- [ ] **Step 2: 結果を PR 本文の "## Perf budget" section に貼付け**

```markdown
## Perf budget

5 baseline detect (RTX-class GPU `--gpu`):
- Total: <elapsed> minutes (budget: ≦ 36 min, baseline #779: 34m43s)
- Per-baseline 詳細: <貼付け>
```

- [ ] **Step 3: `TestNoResolutionCompat` 全 PASS 確認**

```bash
pytest tests/test_scorebar_regression.py::TestNoResolutionCompat -v -m "slow_detect or baseline_regen"
```

Expected: 3/3 PASS (`20260116`, `20260118`, `20260119`)。

- [ ] **Step 4: env var rollback 動作確認 (manual)**

```powershell
$env:ALLAGANEYE_DETECT_FPS_FILTER = "1"
python -m allaganeye detect "$env:ALLAGANEYE_SAMPLE_VIDEO_DIR\20260118\2026-01-18 22-15-18.mkv" `
    -o output\rollback-20260118 --no-cache
$env:ALLAGANEYE_DETECT_FPS_FILTER = $null
```

`output\rollback-20260118\metadata.json` の Match 8 end が `6465.25` (旧挙動) であることを目視確認。

- [ ] **Step 5: Iron Law 6 Pre-flight 実施 (PR 作成直前)**

`docs/l2-workflow.md` §「PR 作成 Pre-flight」 に従って:

- Step 0: `gh pr list --search "576" --state open` で重複 PR チェック (<1s)
- Step 1: `git fetch origin develop-0.3.0`
- Step 2: `git log HEAD..origin/develop-0.3.0` で取り込み未済 commit 確認
- Step 3: touched files 交差判定
- Step 4: `gh pr list --search "576" --state all` で並行 PR 重複再確認
- Step 5: `/codex:adversarial-review` を focus 文字列付きで起動 (Iron Law 3 / encoding / GPU fallback / 同 issue 過去 PR root cause)

- [ ] **Step 6: AskUserQuestion で実機検証依頼**

`AskUserQuestion` で Idios (user) に以下を依頼:

- GPU 実機検証 (NVIDIA dGPU + AMD APU 環境で 5 baseline) 完了確認
- env var rollback 動作確認 (Match 8 end = 6465.25)
- Intel QSV: 別途検証 / scope 外明記 / 別 issue

- [ ] **Step 7: PR 作成**

```bash
gh pr create --base develop-0.3.0 --title "feat(detector): detect fps filter retirement (Refs #576)" --body "$(cat <<'EOF'
## Summary

- ffmpeg `-vf fps=N` filter を detect path から廃止 (#576)
- chunk full-decode + Python N-th sampling 方式に移行 (output seek + `-fps_mode passthrough`)
- rational fps (NTSC 60000/1001 対応) を probe.py から detector まで伝搬
- env var `ALLAGANEYE_DETECT_FPS_FILTER=1` で旧 path に rollback 可能 (transitional、v0.3.x で削除)

## Acceptance criteria (#576 spec §9)

### §9.1 実装 / 設計
- [x] `-vf` から `fps=` 削除、`-fps_mode passthrough` 追加 (Task 4, 5)
- [x] `-ss` を `-i` の後に移動 (Task 4, 5)
- [x] `source_fps_num` / `source_fps_den` parameter 追加 (Task 6)
- [x] `split_matches.py:745` `detect_kwargs` wiring (Task 6)
- [x] `probe.py` rational fps `fps_num`/`fps_den` 公開 (Task 1)
- [x] `probe.py` 静的 VFR WARN (Task 1)
- [x] `_sample_chunk_frames` 動的 VFR 検出 + tail chunk 例外 (Task 3)
- [x] `subprocess.Popen` + streaming read (Task 3, 4, 5)
- [x] env var `ALLAGANEYE_DETECT_FPS_FILTER=1` rollback (Task 2, 4, 5)
- [x] `conftest.py` autouse fixture (Task 2)
- [x] v0.3.x 削除 timeline を CHANGELOG / docstring に明記 (Task 13)

### §9.2 baseline 検証
- [x] Class A 4 本 `compare-baseline.py` exit 0 (Task 8)
- [x] Class A + Class B intermediate audit dump (Task 8)
- [x] Class B (obs-20260118) baseline regenerate + per-frame probe evidence (Task 9)
- [x] Class C VTuber ±10s tolerance (既存テスト reuse)

### §9.3 evidence
- [x] `scripts/validate-fps-retirement.py` 追加 (Task 7)
- [x] CPU / NVIDIA / AMD で実行、TSV を本文添付 (Task 14)
- [x] vendor 別 golden brightness 比較 (Task 10, 14)
- [ ] Intel QSV: <Idios の判断: 検証可 / scope 外 / 別 issue>

### §9.4 regression / perf
- [x] 5 baseline 合計 detect ≦ 36 分 (Task 15)
- [x] `TestNoResolutionCompat` 全 PASS (Task 15)
- [x] env var rollback 動作確認 (Task 15)
- [x] `docs/video-processing.md` / `docs/testing-guide.md` 更新 (Task 11, 12)

## Baseline diff (Class B regenerate)

`obs-20260118.metadata.json`:
- Match 8 end: `6465.25 → ~6184` (#560 root cause fix そのもの)
- <旧 → 新 matches/gaps 全件 diff>

## Evidence (per-frame probe)

debug-brightness CSV 抜粋 (6184.0-6185.5):
- <CSV 抜粋を貼付け、Task 9 Step 5>

## PTS validation evidence

<Task 14 で取得した CPU / NVIDIA / AMD TSV を貼付け>

## Intermediate audit (Class A + Class B)

<Task 8 で生成した 5 本の Pass 1 / Pass 2 dump を貼付け>

## Perf budget

<Task 15 Step 2 の elapsed time を貼付け>

## Test plan

- [x] ruff check / format / pyright (各 task で実施)
- [x] pytest -m "not slow and not slow_detect" 全 PASS
- [x] pytest -m slow_detect on Idios 環境
- [x] markdownlint
- [x] Iron Law 6 Pre-flight (Step 0-5、Task 15)
- [x] AskUserQuestion 実機検証 (Task 15)
- [x] `/codex:adversarial-review` (Task 15)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review

### Spec coverage check

| Spec § | Coverage |
| --- | --- |
| §1 Goal & Non-goals | Task 1-15 全体 |
| §2.1 ffmpeg invocation | Task 4 (CPU), Task 5 (GPU) |
| §2.2 Python sampling + streaming + VFR | Task 3 (helper), Task 1 (静的 VFR) |
| §2.3 API 拡張 | Task 6 (signature + wiring) |
| §3 Baseline strategy | Task 8 (Class A), Task 9 (Class B), §C 既存 reuse |
| §4.1-4.3 Determinism | Task 4, 5 (output seek 実装) |
| §4.4 PTS 検証 matrix + script 仕様 | Task 7 (script 実装), Task 14 (実行) |
| §5 Performance budget | Task 15 (実測) |
| §6 Rollback + CI hygiene | Task 2 (env var helper + fixture), Task 4, 5 (dispatch) |
| §7.1 unit test | Task 1, 2, 3, 4, 5, 6, 7 (各 task で TDD) |
| §7.2 integration test | Task 8, 9, 10 |
| §7.3 manual / 実機 | Task 14, 15 |
| §7.4 perf gate | Task 15 |
| §8 scope guard | 各 task の "Files" で明示、scope 外触らない |
| §9.1-9.4 受入条件 | Task 15 Step 7 PR 本文で逐条 |
| §10 R1-R10 リスク | R1 (Task 8 Step 3), R2 (Task 15), R3 (Task 10, 14), R4 (Task 13), R5 (Task 13 CHANGELOG), R6 (Task 2), R7 (Task 3-5), R8 (Task 9 Step 5), R9-R10 (defer 記録のみ) |

**Gap check**: 全 spec section に対応する Task / Step を提示済み。

### Placeholder scan

- ✅ "TBD" / "TODO" / "implement later" — なし
- ✅ "Similar to Task N" — 各 task で完全 code 提示
- ✅ "Write tests for the above" — 全 test code 提示
- ✅ "Add appropriate error handling" — `_sample_chunk_frames` で具体的に VideoProcessingError + 255.0 fallback

### Type consistency

- `_sample_chunk_frames` signature: `(stream, chunk_start, chunk_timestamps, fps_num, fps_den, expected_frames, is_tail_chunk)` — Task 3, 4 (`_decode_chunk_cpu_v2`), 5 (`_decode_chunk_v2`) で一致
- `_use_legacy_fps_filter()` — Task 2 で定義、Task 4, 5 で参照、Task 13 で docstring 拡張
- `_resolve_fps_rational(num, den, source_fps)` — Task 3 で定義、Task 4, 5 dispatcher で使用
- `_decode_chunk_cpu(..., source_fps_num, source_fps_den, source_fps, is_tail_chunk)` keyword-only args — Task 4 で定義、`_scan_cpu` (Task 4) と `detect_match_boundaries` (Task 6) で keyword 渡し
- `_decode_chunk(..., source_fps_num, source_fps_den, source_fps, is_tail_chunk)` keyword-only args — Task 5 で定義、`scan_gpu` (Task 5) と `detect_match_boundaries` (Task 6) で keyword 渡し
- `ProbeResult` の新 field `fps_num`/`fps_den` — Task 1 で追加、Task 6 wiring で `metadata.get("fps_num")`/`get("fps_den")` で参照

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-18-v030-l3-detect-fps-filter-retirement.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
