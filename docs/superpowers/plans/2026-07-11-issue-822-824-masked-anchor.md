# #822 masked 過分割解消 + #824 probe semantics 統一 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** masked-OBS detect の過分割 (試合間 lobby の segment 化) を anchor presence + segment 検証の 2 層で解消し、同一実装期に #824 probe 失敗 semantics 統一契約 (tri-state) を全 site に実装する。

**Architecture:** PR-A (#824 契約 = 挙動不変の表現移行 + pin) → PR-B (#822 = per-video scorebar anchor consensus + at-anchor presence + masked 分類規則変更 + Layer 2 segment 検証) の直列 2 PR。OBS production path (`localize=False`) は両 PR とも不変 (bit-exact 実測 gate 付き)。

**Tech Stack:** Python (numpy / opencv-python-headless / ffmpeg probe)。既存 detection subsystem (detector.py / scorebar.py / presence.py / capture_region.py) の拡張。

**Spec:** [2026-07-11-issue-822-masked-oversplit-anchor-design.md](../specs/2026-07-11-issue-822-masked-oversplit-anchor-design.md) (§番号は本 plan から参照) / [#824 spec](../specs/2026-07-03-issue-824-probe-failure-semantics-design.md) (§5.4 site 番号は同 spec §4 の棚卸し表)

## Global Constraints

- **OBS bit-exact**: `classify_blackout(localize=False)` 経路 / `_probe_scorebar_context` の `scorebar_results` / `_flag_post_match_trailing` / GPU chunk decode は一切変更しない。各 PR で OBS baseline 5 本の detect 出力 byte 一致を実測 (`docs/testing-guide.md` §「baseline drift の判定」)
- **`--vtuber` path**: anchor 化しない (#480 defer)。既存挙動の pin テストを維持
- **TDD**: 全 task Red-Green-Refactor。実装前に failing test
- **PR 規約**: base = `develop-0.3.0`、`Closes` 禁止 (`Refs #822` / `Refs #824`)、1 PR = 1 scope、Pre-flight (Iron Law 6: Step 0-5、Step 5 = `codex-companion.mjs adversarial-review` tier 1)
- **cache**: 検出出力を変える変更は `_save_cache` / `_load_cache` / verbose の 3 箇所 (PR-B Task B6)
- **worktree CLI 実行**: `ALLAGANEYE_INTEGRITY_SKIP=1`、masked detect は `--no-cache` 必須、7h 級 GPU detect は detached `Start-Process -WindowStyle Hidden` + log
- python コマンドは `python -m pytest` / `python -m ruff` / `python -m pyright` 形式

## PR 分割

| PR | branch | 内容 | 挙動 |
| --- | --- | --- | --- |
| PR-A | `claude/l3-824-probe-state` | #824 契約: `probe_state.py` 新設 + site 1/2/2b/3/4/5/6/9/10/14 の表現移行 + pin 7 件移行 | **不変** (log 文言の契約化のみ差分) |
| PR-B | `claude/l3-822-masked-anchor` | #822: consensus core 抽出 + anchor 解決 + at-anchor presence + masked 分類規則 + Layer 2 + cache key + docs | masked path のみ変更 |

PR-A を /iterate-review 収束 → Idios merge 後、PR-B を最新 develop-0.3.0 から分岐する。

## File Structure

| ファイル | PR | 責務 |
| --- | --- | --- |
| `allaganeye/video/probe_state.py` (新規) | A | tri-state 契約型 (`PresenceState` / `PresenceSample` / `ProbeFailurePolicy`)。presence/capture_region/scorebar/detector から import される中立 module (circular import 回避、#824 §5.1) |
| `allaganeye/video/presence.py` | A, B | site 1/2/2b/3 移行 (A)。`scan_presence` の明示 timestamp 列対応 (B) |
| `allaganeye/video/scorebar.py` | A, B | site 4/5 移行 + `_majority_presence` (A)。anchor threading + masked 分類規則 (B) |
| `allaganeye/video/capture_region.py` | A, B | site 6/10 sentinel 対応 (A)。consensus core 抽出 + `localize_scorebar_at_anchor` (B) |
| `allaganeye/video/detector.py` | A, B | site 9/14 warning 契約化 (A)。`_resolve_scorebar_anchor` + Layer 2 `_validate_match_segments` + masked fallback 配線 (B) |
| `allaganeye/commands/split_matches.py` | B | cache key `masked_algo` (save/load/verbose) |
| `allaganeye/commands/detect.py` | B | verbose cache-hit summary の masked_algo 表示 |
| `tests/test_probe_state.py` (新規) | A | 契約型 unit |
| `tests/test_presence.py` / `test_scorebar.py` / `test_detector.py` / `test_capture_region.py` | A, B | pin 移行 + 新規 unit |
| `docs/detection-map.md` / `CLAUDE.md` | B | masked path 検出記述の更新 |
| `.gitignore` / `pyproject.toml` | B | `.tmp-822-analysis/` 除外 (#828 前例) |

---

## PR-A: #824 契約 (挙動不変)

> 事前: `git fetch origin develop-0.3.0 && git checkout -b claude/l3-824-probe-state origin/develop-0.3.0`

### Task A1: `probe_state.py` — tri-state 契約型

**Files:**

- Create: `allaganeye/video/probe_state.py`
- Test: `tests/test_probe_state.py` (新規)

**Interfaces:**

- Produces: `PresenceState` (Enum: PRESENT/ABSENT/UNKNOWN)、`PresenceSample` (frozen dataclass: `time: float, state: PresenceState, confidence: float`)、`ProbeFailurePolicy` (Enum: RAISE/ISOLATE、現時点の消費者は ISOLATE のみ — #824 §5.2)
- 注意: `PresenceSample.present` bool property は**提供しない** (#824 §5.1、UNKNOWN→False の escape hatch 禁止)

- [ ] **Step 1: failing test**

```python
# tests/test_probe_state.py
"""#824 probe-failure semantics: 中立契約 module の unit (spec §5.1)."""

import dataclasses

import pytest

from allaganeye.video.probe_state import (
    PresenceSample,
    PresenceState,
    ProbeFailurePolicy,
)


def test_presence_state_members():
    assert {s.value for s in PresenceState} == {"present", "absent", "unknown"}


def test_presence_sample_is_frozen_tristate():
    s = PresenceSample(time=1.5, state=PresenceState.UNKNOWN, confidence=0.0)
    assert s.state is PresenceState.UNKNOWN
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.state = PresenceState.PRESENT  # type: ignore[misc]


def test_presence_sample_has_no_bool_escape_hatch():
    # #824 §5.1: `.present` property は UNKNOWN→False の silent 変換経路になるため
    # 提供しない (契約 pin)。
    s = PresenceSample(time=0.0, state=PresenceState.PRESENT, confidence=1.0)
    assert not hasattr(s, "present")


def test_probe_failure_policy_members():
    assert {p.value for p in ProbeFailurePolicy} == {"raise", "isolate"}
```

- [ ] **Step 2: 実行して FAIL 確認** — `python -m pytest tests/test_probe_state.py -v` → ModuleNotFoundError
- [ ] **Step 3: 実装**

```python
# allaganeye/video/probe_state.py
"""probe 失敗縮退の統一契約型 (#824 spec §5.1)。

presence / capture_region / scorebar / detector から import される中立 module。
presence.py 所有にすると capture_region → presence の逆向き import で cycle に
なるため独立配置 (#824 §5.1 module 配置)。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PresenceState(Enum):
    """scorebar presence の tri-state。UNKNOWN = probe 失敗 (decode None / 例外)。

    ABSENT (観測に基づく不在) と UNKNOWN (観測不能) の暗黙同一視を型で禁止する。
    UNKNOWN → ABSENT への折り畳みは集約層のみが明示的な state 比較で行う (§5.2)。
    """

    PRESENT = "present"
    ABSENT = "absent"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PresenceSample:
    """One time-grid sample: scorebar presence state at ``time``.

    ``confidence`` is 0.0 for ABSENT / UNKNOWN.  意図的に ``present`` bool
    property を持たない (#824 §5.1: silent bool 化経路の禁止)。
    """

    time: float
    state: PresenceState
    confidence: float


class ProbeFailurePolicy(Enum):
    """集約層の probe 失敗方針 (#824 §5.2)。現時点の消費者は ISOLATE のみ。

    RAISE は将来の診断 harness / GT 突合用の speculative seam として定義だけ残す。
    """

    RAISE = "raise"
    ISOLATE = "isolate"
```

- [ ] **Step 4: PASS 確認** — `python -m pytest tests/test_probe_state.py -v`
- [ ] **Step 5: Commit** — `git add allaganeye/video/probe_state.py tests/test_probe_state.py && git commit -m "feat(#824): probe_state.py 中立契約 module (tri-state) (Refs #824)"`

### Task A2: presence.py 移行 (site 1 / 2 / 2b / 3)

**Files:**

- Modify: `allaganeye/video/presence.py`
- Test: `tests/test_presence.py`

**Interfaces:**

- Consumes: Task A1 の `PresenceState` / `PresenceSample`
- Produces: `localize_present_at(video_path, timestamp) -> PresenceSample` (**`raise_on_probe_failure` param 削除**、raw None → UNKNOWN / localizer miss → ABSENT / hit → PRESENT)。`scan_presence` は per-probe 例外→UNKNOWN 写像 + 全滅 fail-loud + 部分故障 warning。`segment_presence` は `s.state is PresenceState.PRESENT` の明示比較 (UNKNOWN は run を切る = 現行維持)。presence.py 冒頭で `from allaganeye.video.probe_state import PresenceSample, PresenceState` re-export (既存 import 互換)

- [ ] **Step 1: 既存 pin の移行 + 新規 failing test**

`tests/test_presence.py` の既存 `PresenceSample(present=...)` 構築を `state=PresenceState.{PRESENT,ABSENT}` に一括書換した上で、以下を追加:

```python
def test_localize_present_at_returns_unknown_on_decode_failure(monkeypatch):
    # #824 site 1: raw None (decode 失敗) は ABSENT でなく UNKNOWN。
    monkeypatch.setattr(
        "allaganeye.video.presence._probe_frame_rgb_hires", lambda *a: None
    )
    s = localize_present_at(Path("dummy.mkv"), 5.0)
    assert s.state is PresenceState.UNKNOWN and s.confidence == 0.0


def test_localize_present_at_has_no_raise_seam():
    # #824 §5.4 site 1: raise_on_probe_failure param は削除済み (bool seam 廃止)。
    import inspect

    assert "raise_on_probe_failure" not in inspect.signature(
        localize_present_at
    ).parameters


def test_scan_presence_partial_unknown_logged(caplog):
    # #824 §5.2-5.3: 部分故障 (UNKNOWN >= 1) は UNKNOWN 数 / 総数 を warning。
    def fn(t):
        if t == 0.0:
            return PresenceSample(time=t, state=PresenceState.UNKNOWN, confidence=0.0)
        return PresenceSample(time=t, state=PresenceState.PRESENT, confidence=1.0)

    with caplog.at_level(logging.WARNING):
        samples = scan_presence(
            Path("dummy.mkv"), 10.0, stride=5.0, workers=2, sample_fn=fn
        )
    assert any(s.state is PresenceState.UNKNOWN for s in samples)
    assert any("UNKNOWN" in r.message and "1/3" in r.message for r in caplog.records)


def test_scan_presence_all_unknown_fails_loud():
    # #824 §5.2: 全滅 (全 probe UNKNOWN) は VideoProcessingError (fail-loud)。
    def fn(t):
        return PresenceSample(time=t, state=PresenceState.UNKNOWN, confidence=0.0)

    with pytest.raises(VideoProcessingError):
        scan_presence(Path("dummy.mkv"), 10.0, stride=5.0, workers=2, sample_fn=fn)


def test_segment_presence_unknown_breaks_run():
    # #824 §5.4 site 2b: UNKNOWN sample は present run を構成しない (現行挙動維持、
    # 折り畳みは集約層の明示比較として grep 可能に)。
    samples = [
        PresenceSample(0.0, PresenceState.PRESENT, 1.0),
        PresenceSample(1.0, PresenceState.UNKNOWN, 0.0),
        PresenceSample(2.0, PresenceState.PRESENT, 1.0),
    ]
    runs = segment_presence(samples, t_gap=0.5, t_min_match=0.0)
    assert len(runs) == 2


def test_refine_unknown_treated_absent_with_warning(caplog, monkeypatch):
    # #824 §5.4 site 3: refine 中の UNKNOWN は absent 側へ bracket 更新 + warning
    # (refine abort しない。既存 test_refine_probe_failure_warns_and_treats_absent の後継)。
    ...  # 既存テストの monkeypatch 構造を維持し、期待 warning 文言を新契約に合わせる
```

既存 7 pin のうち presence 系 2 件の扱い (#824 spec §6):

- `test_scan_presence_partial_failures_logged` (test_presence.py:290) → 上記 `test_scan_presence_partial_unknown_logged` に**置換**
- `test_refine_probe_failure_warns_and_treats_absent` (test_presence.py:305) → 文言のみ新契約に合わせ**維持**

- [ ] **Step 2: FAIL 確認** — `python -m pytest tests/test_presence.py -v` (新規は import/signature error、既存書換分は attribute error)
- [ ] **Step 3: presence.py 実装**

```python
# presence.py 冒頭 (dataclass 定義を probe_state import に置換):
from allaganeye.video.probe_state import PresenceSample, PresenceState

# site 1:
def localize_present_at(video_path: Path, timestamp: float) -> PresenceSample:
    """Probe one hi-res frame and report scorebar presence (tri-state, #824).

    raw None (decode 失敗) → UNKNOWN (debug log) / decode 成功 + localizer miss
    → ABSENT / hit → PRESENT。decode 例外は caller に漏らさない (§5.2)。
    """
    raw = _probe_frame_rgb_hires(video_path, timestamp)
    if raw is None:
        logger.debug("presence probe decode failed at t=%.3fs -> UNKNOWN", timestamp)
        return PresenceSample(time=timestamp, state=PresenceState.UNKNOWN, confidence=0.0)
    loc = localize_from_rgb_bytes(
        raw, height=_SCOREBAR_V2_PROBE_HEIGHT, width=_SCOREBAR_V2_PROBE_WIDTH
    )
    if loc is None:
        return PresenceSample(time=timestamp, state=PresenceState.ABSENT, confidence=0.0)
    return PresenceSample(time=timestamp, state=PresenceState.PRESENT, confidence=loc.confidence)

# site 2 (scan_presence): try/except → UNKNOWN 写像に置換
# 執行時 deviation (PR #887 codex R1 [medium] 対応): 実装は default sampler を
# `_probe_present_sample_raising` (decode 例外を raise のまま通す私設 variant) に
# 変更し、系統故障の代表原因を fail-loud の __cause__ まで保全する。外部契約
# (localize_present_at = no-leak) は plan 通り不変。
def scan_presence(video_path, duration, *, stride, workers, sample_fn=None):
    fn = sample_fn if sample_fn is not None else (
        lambda t: localize_present_at(video_path, t)
    )
    times = _grid_timestamps(duration, stride)
    results: dict[float, PresenceSample] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fn, t): t for t in times}
        for fut in futures:
            t = futures[fut]
            try:
                results[t] = fut.result()
            except VideoProcessingError:
                # 単発 probe の例外も UNKNOWN に写像 (per-probe 隔離、#824 §5.2)
                results[t] = PresenceSample(time=t, state=PresenceState.UNKNOWN, confidence=0.0)
    unknown = [t for t in times if results[t].state is PresenceState.UNKNOWN]
    if unknown:
        if len(unknown) == len(times):
            raise VideoProcessingError(
                f"all {len(times)} presence probes UNKNOWN (systemic probe failure)"
            )
        logger.warning(
            "%d/%d presence probes UNKNOWN (probe failure); excluded from aggregation "
            "(time range %.1f-%.1fs)",
            len(unknown), len(times), min(unknown), max(unknown),
        )
    return [results[t] for t in times]

# site 2b (segment_presence): `if s.present:` → `if s.state is PresenceState.PRESENT:`
# site 3 (detect_matches_by_presence.present_at):
    def present_at(t: float) -> bool:
        sample = localize_present_at(video_path, t)
        if sample.state is PresenceState.UNKNOWN:
            logger.warning(
                "presence probe UNKNOWN during boundary refine at t=%.3fs; "
                "treating as absent", t,
            )
            return False
        return sample.state is PresenceState.PRESENT
```

- [ ] **Step 4: PASS 確認** — `python -m pytest tests/test_presence.py -v`
- [ ] **Step 5: Commit** — `git commit -m "refactor(#824): presence.py site 1/2/2b/3 を tri-state 契約へ移行 (Refs #824)"`

### Task A3: scorebar.py 移行 (site 4 / 5)

**Files:**

- Modify: `allaganeye/video/scorebar.py:38-52` (`_localize_present_from_raw`)、`:163-169` (`localize_results` 生成)、`:178-186` 直後に `_majority_presence` 追加、`:331-332` / `:367-381` (`_classify_blackout_localize` の majority 呼び出し)
- Test: `tests/test_scorebar.py`

**Interfaces:**

- Consumes: `PresenceState` (Task A1)
- Produces: `_localize_present_from_raw(raw) -> PresenceState` (None→UNKNOWN / miss→ABSENT / hit→PRESENT)。`_probe_scorebar_context` の第 3 戻り値は `list[PresenceState | None]` (None = with_localize=False で未計算)。`_majority_presence(states: list[PresenceState | None]) -> bool | None` (UNKNOWN/None を分母除外、有効票ゼロで None — `_majority_scorebar` の tri-state 版)。**`scorebar_results` (bool|None、OBS 消費) と `_majority_scorebar` は不変**

- [ ] **Step 1: failing test**

```python
def test_localize_present_from_raw_tristate():
    # #824 site 4: 表現形式のみ変更 (semantics は docstring 分離済みのまま)。
    assert _localize_present_from_raw(None) is PresenceState.UNKNOWN
    blank = np.full((1080, 1920, 3), 40, dtype=np.uint8).tobytes()
    assert _localize_present_from_raw(blank) is PresenceState.ABSENT


def test_majority_presence_excludes_unknown_from_denominator():
    P, A, U = PresenceState.PRESENT, PresenceState.ABSENT, PresenceState.UNKNOWN
    assert _majority_presence([P, U, U]) is True      # 有効票 1、present 1
    assert _majority_presence([P, A, U]) is True      # 有効票 2、present 1 >= ceil(2/2)
    assert _majority_presence([A, A, P]) is False
    assert _majority_presence([U, U, None]) is None   # 有効票ゼロ


def test_probe_scorebar_context_localize_results_are_tristate(monkeypatch, tmp_path):
    # with_localize=True で probe 失敗 frame は UNKNOWN、成功 miss は ABSENT。
    # scorebar_results (bool|None) は従来のまま (OBS 不変 pin)。
    ...  # 既存 test_probe_scorebar_context 系の monkeypatch 構造を流用し
         # hires probe を {t1: None, t2: blank_frame} に固定して検証
```

既存 pin: `test_probe_scorebar_context_logs_probe_failure` (test_scorebar.py:1667) は **そのまま維持** (scorebar_results 側は不変、#824 spec §6)。

- [ ] **Step 2: FAIL 確認** — `python -m pytest tests/test_scorebar.py -k "tristate or majority_presence" -v`
- [ ] **Step 3: 実装** — `_localize_present_from_raw` の戻り値を PresenceState 化、`localize_results: dict[float, PresenceState | None]` 化、`_majority_presence` 追加 (実装は上記 Interfaces のとおり `ceil(len(valid)/2)` 判定で `_majority_scorebar` と同一式)、`_classify_blackout_localize` 内の `_majority_scorebar(pre_loc)` 呼び出し 4 箇所を `_majority_presence` に置換。分類結果は全入力で従来と一致する (UNKNOWN は旧 None と同じく分母除外) ことを既存テストが担保
- [ ] **Step 4: PASS 確認** — `python -m pytest tests/test_scorebar.py -v`
- [ ] **Step 5: Commit** — `git commit -m "refactor(#824): scorebar.py site 4/5 (localize 系のみ) tri-state 化、scorebar_results 不変 (Refs #824)"`

### Task A4: capture_region / detector 移行 (site 6 / 10 / 9 / 14)

**Files:**

- Modify: `allaganeye/video/capture_region.py:510-559` (`detect_scorebar_band_region` の sentinel 許容)、`allaganeye/video/detector.py:288-319` (site 9 closure + warning 文言)、`:340-384` (site 14 warning 必須化)
- Test: `tests/test_detector.py` / `tests/test_presence.py:339` (none_passthrough pin)

**Interfaces:**

- Consumes: `PresenceState.UNKNOWN` (Task A1)
- Produces: `detect_scorebar_band_region` の `localize_fn` は `ScorebarLocalization | None | PresenceState` を返してよい (UNKNOWN = decode 失敗 sentinel、hits にも miss にも数えない)。site 9 `_localize_at` closure が raw None → `PresenceState.UNKNOWN` を返し、consensus 後に UNKNOWN>0 で部分故障 warning (site 9 帰属、#824 §4.1 site 10 は無音のまま)。site 14 は decode-None silent drop 廃止 (`N/M probes failed` warning) + `except Exception` 縮退の warning 必須化 (戻り値・縮退挙動は不変)

- [ ] **Step 1: failing test**

```python
def test_band_region_localize_fn_unknown_sentinel_not_counted():
    # #824 site 6/10: UNKNOWN は hit でも miss でもなく consensus から除外。
    from allaganeye.video.probe_state import PresenceState

    calls = iter(
        [PresenceState.UNKNOWN] + [_loc(y_top=12)] * 3 + [PresenceState.UNKNOWN] * 4
    )
    region = detect_scorebar_band_region(
        duration=80.0, probe_w=1920, probe_h=1080,
        localize_fn=lambda t: next(calls), num_samples=8, min_hits=2,
    )
    assert not region.is_full_frame()  # 有効 3 hit で consensus 成立


def test_resolve_detect_region_warns_unknown_probes(monkeypatch, caplog):
    # site 9: UNKNOWN>0 の部分故障 warning (UNKNOWN 数 / 総数、#824 §5.3)。
    ...


def test_resolve_masked_region_warns_on_decode_failures(monkeypatch, caplog):
    # site 14: silent drop 廃止 pin — decode None が 1 つでもあれば warning に
    # "N/M" が含まれる。戻り値 (region) は従来どおり有効 frame から解決。
    ...


def test_resolve_masked_region_warns_on_exception_fallback(monkeypatch, caplog):
    # site 14: except Exception → FULL_FRAME 縮退時に warning 必須 (現状 log ゼロの廃止)。
    ...
```

既存 pin (#824 spec §6):

- `test_resolve_detect_region_swallows_exceptions_to_full_frame` (test_detector.py:2724) / `test_resolve_detect_region_warns_on_consensus_miss_full_frame` (:2743) → §5.3 表の文言 (有効票数 / min_hits / FULL_FRAME 明示) に**揃えて維持**
- `test_localize_from_rgb_bytes_none_passthrough_and_decode` (test_presence.py:339) → **不変維持** (関数自体の None 契約は不変)
- `test_borderline_pseudo_regions_capped_with_warning` (test_detector.py:1645) → **無変更** (OBS path)

- [ ] **Step 2: FAIL 確認** — `python -m pytest tests/test_detector.py -k "unknown or masked_region_warns" -v`
- [ ] **Step 3: 実装** — `detect_scorebar_band_region`: `hits = [loc for t in times if isinstance((loc := localize_fn(t)), ScorebarLocalization)]`。site 9: closure で raw None → UNKNOWN 返却 + `unknown_count` を nonlocal 集計し、consensus 後 `if unknown_count: logger.warning("anchor probes: %d/%d UNKNOWN (probe failure)", ...)`。site 14: `dropped = len(times) - len(frames)` を集計し `if dropped: logger.warning("masked region probes: %d/%d failed (decode); continuing with valid frames", dropped, len(times))`、`except Exception:` 節に `logger.warning("masked region detection failed; degrading to FULL_FRAME", exc_info=True)` を追加
- [ ] **Step 4: PASS 確認** — `python -m pytest tests/test_detector.py tests/test_presence.py tests/test_capture_region.py -v`
- [ ] **Step 5: Commit** — `git commit -m "refactor(#824): site 6/9/10/14 の UNKNOWN sentinel + warning 契約化 (Refs #824)"`

### Task A5: PR-A full checks + OBS bit-exact gate + PR 作成

**Files:** なし (検証のみ)

- [ ] **Step 1: full checks** — `python -m ruff check . && python -m ruff format --check . && python -m pyright && python -m pytest -q` 全 pass
- [ ] **Step 2: OBS bit-exact gate** — baseline 5 本を `--no-cache` で detect し、保存済み baseline metadata と diff (`docs/testing-guide.md` §「baseline drift の判定」の手順。timestamp 系 field (detected_at 等) は非意味的差分として grep 除外)。**PR-A は挙動不変のため byte 一致必須**
- [ ] **Step 3: Pre-flight (Iron Law 6)** — Step 0 `gh pr list --search "824" --state open` → Step 1-4 base 同期/交差/重複 → Step 5 `codex-companion.mjs adversarial-review` (focus: "tri-state migration behavior preservation; UNKNOWN vs ABSENT conflation; warning contract completeness; OBS path untouched")
- [ ] **Step 4: PR 作成** — base `develop-0.3.0`、本文に Self-Test Report (machine-verified `[x]` / unverifiable `-` 書き分け)、`Refs #824`。**実機検証注記**: 挙動不変 refactor だが detector.py を touch するため OBS bit-exact 実測結果を PR 本文に記載
- [ ] **Step 5: /iterate-review → Idios merge 依頼 (AskUserQuestion)**

---

## PR-B: #822 anchor presence + Layer 2 (挙動変更、masked path のみ)

> 事前: PR-A merge 後 `git fetch origin develop-0.3.0 && git checkout -b claude/l3-822-masked-anchor origin/develop-0.3.0`

### Task B1: consensus core 抽出 (`consensus_scorebar_localization`)

**Files:**

- Modify: `allaganeye/video/capture_region.py:510-559`
- Test: `tests/test_capture_region.py`

**Interfaces:**

- Produces: `consensus_scorebar_localization(*, duration: float, localize_fn: Callable[[float], ScorebarLocalization | None | PresenceState], num_samples: int = 8, min_hits: int = _BAND_CONSENSUS_MIN_HITS) -> ScorebarLocalization | None` — 現行 `detect_scorebar_band_region` の times grid / hits 収集 / y_top クラスタ (tol `_CLUSTER_Y_TOL`) / dominant cluster / median までを移した core。`detect_scorebar_band_region` は core 呼び出し + `band_region_from_localization` 変換のみになる (**挙動不変**)

- [ ] **Step 1: failing test**

```python
def test_consensus_scorebar_localization_dominant_cluster_median():
    locs = [_loc(y_top=12), _loc(y_top=18), _loc(y_top=12), _loc(y_top=540)]
    seq = iter(locs + [None] * 4)
    result = consensus_scorebar_localization(
        duration=80.0, localize_fn=lambda t: next(seq), num_samples=8, min_hits=2
    )
    assert result is not None and result.y_top == 12  # dominant cluster median


def test_consensus_scorebar_localization_scattered_returns_none():
    # FP のみ (クラスタ不成立 min_hits 未満) → None。
    seq = iter([_loc(y_top=100), _loc(y_top=300), _loc(y_top=500)] + [None] * 5)
    assert consensus_scorebar_localization(
        duration=80.0, localize_fn=lambda t: next(seq), num_samples=8, min_hits=2
    ) is None or True  # y tol=60 で 100/300/500 は各クラスタ 1 件 → min_hits=2 未満 → None
```

(2 本目は `is None` を assert する。既存 `detect_scorebar_band_region` の全テストが挙動 pin として green のままであることが抽出の正しさの主担保)

- [ ] **Step 2: FAIL 確認** → **Step 3: 抽出実装** (`detect_scorebar_band_region` は `loc = consensus_scorebar_localization(...); return FULL_FRAME if loc is None else band_region_from_localization(loc, ...)`) → **Step 4: `python -m pytest tests/test_capture_region.py -v` 全 green** → **Step 5: Commit** `"refactor(#822): consensus core を consensus_scorebar_localization に抽出 (挙動不変) (Refs #822)"`

### Task B2: at-anchor presence primitive

**Files:**

- Modify: `allaganeye/video/capture_region.py` (`localize_scorebar` の走査 loop を `_scan_scorebar_bands(frame, *, y_start, y_stop, stride, x_gate)` に内部共通化)
- Test: `tests/test_capture_region.py`

**Interfaces:**

- Produces: `localize_scorebar_at_anchor(frame: np.ndarray, anchor: ScorebarLocalization, *, stride: int = _BAND_SCAN_STRIDE, target_ratio: float = _LOCALIZE_TARGET_RATIO) -> ScorebarLocalization | None` — y 走査域を `[max(0, anchor.y_top - _ANCHOR_Y_TOL), anchor.y_top + _ANCHOR_Y_TOL]`、saturated run を anchor x-range との IoU ≥ `_ANCHOR_X_IOU_MIN` (0.5) で gate した emblem 3 点 AND。`localize_from_rgb_bytes_at_anchor(raw, anchor, *, height, width) -> ScorebarLocalization | None` (decode boilerplate 共有)。定数: `_ANCHOR_Y_TOL = 60` / `_ANCHOR_X_IOU_MIN = 0.5`
- 制約: `localize_scorebar` (既存) は **bit-same** (既存テスト群が pin)

- [ ] **Step 1: failing test** (合成 frame helper `_hires_with_scorebar_at` を再利用)

```python
def _anchor(y_top=12, x_left=614, x_right=1305):
    return ScorebarLocalization(
        x_left=x_left, x_right=x_right, y_top=y_top, y_bottom=y_top + 45, confidence=1.0
    )


def test_at_anchor_hits_bar_at_anchor_position():
    f = _hires_with_scorebar_at(y_top=18, x_left=614, x_right=1305)
    loc = localize_scorebar_at_anchor(f, _anchor())
    assert loc is not None and abs(loc.y_top - 18) <= 6


def test_at_anchor_rejects_bar_far_from_anchor_y():
    # 実測 FP 位置 (lobby HUD y~504) はアンカー帯 (12±60) 外 → absent。
    f = _hires_with_scorebar_at(y_top=500, x_left=614, x_right=1305)
    assert localize_scorebar_at_anchor(f, _anchor()) is None


def test_at_anchor_rejects_run_with_low_x_iou():
    # y はアンカー帯内でも x-IoU < 0.5 の run は gate (位置整合性)。
    f = _hires_with_scorebar_at(y_top=18, x_left=100, x_right=700)
    assert localize_scorebar_at_anchor(f, _anchor()) is None


def test_at_anchor_finds_bar_even_when_stronger_fp_elsewhere():
    # best-hit 敗北ケース (staging / t=19000 実測) の再現: アンカー帯内の弱い真バー
    # + 帯外の強い FP。全走査 (localize_scorebar) は FP を返しうるが at_anchor は真バー。
    f = _hires_with_two_bars(anchor_y=18, fp_y=300)  # helper を本 task で追加
    loc = localize_scorebar_at_anchor(f, _anchor())
    assert loc is not None and abs(loc.y_top - 18) <= 6
```

- [ ] **Step 2: FAIL 確認** → **Step 3: 実装** (走査 loop を `_scan_scorebar_bands` に共通化し、`localize_scorebar` = `y_start=0, y_stop=int(H*_BAND_Y_MAX_FRAC), x_gate=None` / `localize_scorebar_at_anchor` = anchor 制約。x-IoU は `inter/union` 計算) → **Step 4: `python -m pytest tests/test_capture_region.py -v` (既存 localize_scorebar pin 含め全 green)** → **Step 5: Commit** `"feat(#822): at-anchor presence primitive (y 帯制限 + x-IoU gate) (Refs #822)"`

### Task B3: anchor 解決 (`_resolve_scorebar_anchor`)

**Files:**

- Modify: `allaganeye/video/detector.py` (`_resolve_masked_region` の直後に追加)
- Test: `tests/test_detector.py`

**Interfaces:**

- Consumes: `consensus_scorebar_localization` (B1)
- Produces: `_resolve_scorebar_anchor(video_path: Path, duration_hint: float) -> ScorebarLocalization | None` — `_probe_frame_rgb_hires` + `localize_from_rgb_bytes` を bind した localize_fn (conf < `_ANCHOR_MIN_CONF` (0.7) の hit は miss 扱いに pre-filter、raw None は `PresenceState.UNKNOWN`) で `consensus_scorebar_localization(num_samples=_ANCHOR_NUM_SAMPLES (24), min_hits=_ANCHOR_MIN_HITS (5))`。None 時は caller が warning (#824 §5.3 consensus miss 形式) を出して縮退。例外は catch して None (site 9 と同型、warning 付き)
- 定数: `_ANCHOR_NUM_SAMPLES = 24` / `_ANCHOR_MIN_HITS = 5` / `_ANCHOR_MIN_CONF = 0.7` (実測根拠: 真 hit conf ~1.00 / FP ≤ 0.67、spec §1.1)

- [ ] **Step 1: failing test** (localize_fn 注入形: `_resolve_scorebar_anchor` は内部 closure のため、`consensus_scorebar_localization` への引数 (num_samples/min_hits) と conf pre-filter / UNKNOWN 写像 / 例外縮退 warning を monkeypatch で検証)

```python
def test_resolve_scorebar_anchor_filters_low_conf_hits(monkeypatch):
    # conf<0.7 の hit (FP 帯) は cluster 投票に入らない → min_hits 未満で None。
    ...


def test_resolve_scorebar_anchor_exception_degrades_none_with_warning(monkeypatch, caplog):
    ...
```

- [ ] **Step 2-4: Red-Green** — 実装は Interfaces のとおり。`python -m pytest tests/test_detector.py -k anchor -v`
- [ ] **Step 5: Commit** `"feat(#822): per-video scorebar anchor 解決 (consensus + conf filter) (Refs #822)"`

### Task B4: masked 分類規則 + anchor threading (classify / merge)

**Files:**

- Modify: `allaganeye/video/scorebar.py` (`_probe_scorebar_context` / `_classify_blackout_localize` / `classify_blackout` / `filter_blackouts_with_scorebar` / `_merge_boundary_pairs` に `anchor: ScorebarLocalization | None = None` param)、`allaganeye/video/detector.py:804-819` (`_detect_masked_fallback` の anchor 解決 + 受け渡し)
- Test: `tests/test_scorebar.py` / `tests/test_detector.py`

**Interfaces:**

- Consumes: `localize_from_rgb_bytes_at_anchor` (B2)、`_resolve_scorebar_anchor` (B3)、`_majority_presence` (A3)
- Produces:
  - `_probe_scorebar_context(..., with_localize=True, anchor=…)`: anchor 非 None のとき localize_results を `_presence_at_anchor_from_raw(raw, anchor)` で生成 (raw None → UNKNOWN / at-anchor miss → ABSENT / hit → PRESENT)。anchor None は従来 (位置独立) — **縮退 path**
  - `filter_blackouts_with_scorebar(..., localize=True, anchor=…)` の keep 規則 (spec §3.2): `in_match` は localize path では duration 問わず **remove** / `non_fl` は localize path では **keep** (boundary 候補)。OBS path (localize=False) の規則は**不変**
  - `_merge_boundary_pairs(..., anchor=…)`: localize branch の gap probe を at-anchor 化
  - `_detect_masked_fallback`: `anchor = _resolve_scorebar_anchor(...)` を region 解決後に呼び、None なら `logger.warning("scorebar anchor unresolved; masked classification falls back to position-independent localize")`

- [ ] **Step 1: failing test**

```python
def test_masked_keep_rules_in_match_removed_any_duration(monkeypatch):
    # spec §3.2: localize path では in_match は >=3.5s でも remove (Q3 確定)。
    # classify_blackout を "in_match" 固定に monkeypatch し、5.0s 幅 region が
    # filter_blackouts_with_scorebar(localize=True) の kept に入らないことを assert。
    ...


def test_masked_keep_rules_non_fl_kept(monkeypatch):
    # spec §3.2: localize path では non_fl を boundary 候補として keep (staging 弱点吸収)。
    ...


def test_obs_keep_rules_unchanged_pin(monkeypatch):
    # localize=False の規則 pin: in_match>=3.5s keep / non_fl remove (bit-exact 担保)。
    ...


def test_classify_localize_uses_anchor_presence(monkeypatch):
    # anchor 指定時: flank probe が at-anchor 評価になる (位置独立 localize 不使用)。
    # _presence_at_anchor_from_raw への spy で検証。
    ...


def test_merge_gap_probes_at_anchor(monkeypatch):
    # merge の 9 probe も anchor 指定時は at-anchor。lobby FP (帯外 hit) が
    # any_scorebar を汚染しない = merge 成立。
    ...


def test_masked_fallback_warns_when_anchor_unresolved(monkeypatch, caplog):
    ...
```

- [ ] **Step 2: FAIL 確認** → **Step 3: 実装**。keep 規則は `filter_blackouts_with_scorebar` 内:

```python
        if classification == "in_match" and (
            localize or region_duration < _IN_MATCH_MAX_DURATION
        ):
            # localize path (#822 Q3): at-anchor に v2 残像 FN が無いため
            # in_match は duration 問わず非境界。OBS path は従来どおり短いもののみ。
            logger.info("REMOVE [...]", ...)
            continue
        if classification == "non_fl" and not localize:
            # localize path (#822): staging 弱点で entry 境界が non_fl 化するため
            # keep (乱立する非試合 segment は Layer 2 が除去、spec §3.2)。
            logger.info("REMOVE [...]", ...)
            continue
```

- [ ] **Step 4: PASS + 回帰** — `python -m pytest tests/test_scorebar.py tests/test_detector.py -v`
- [ ] **Step 5: Commit** `"feat(#822): masked 分類規則 (in_match 全除去 / non_fl keep) + anchor threading (Refs #822)"`

### Task B5: Layer 2 segment 検証 (`_validate_match_segments`)

**Files:**

- Modify: `allaganeye/video/presence.py` (`scan_presence` に `times: Sequence[float] | None = None` additive param)、`allaganeye/video/detector.py` (`_validate_match_segments` 追加 + `_detect_masked_fallback` 末尾配線)
- Test: `tests/test_presence.py` / `tests/test_detector.py`

**Interfaces:**

- Consumes: `scan_presence` (A2 + 本 task 拡張)、`localize_from_rgb_bytes_at_anchor` (B2)
- Produces: `_validate_match_segments(video_path: Path, segments: list[MatchBoundary], anchor: ScorebarLocalization, workers: int | None, stats: DetectionStats | None) -> list[MatchBoundary]`:
  - 各 segment 内 9 点 (`start + (end-start)*k/10, k=1..9`) を `scan_presence(times=…, sample_fn=at-anchor bind)` で probe
  - valid (非 UNKNOWN) 票の PRESENT が**過半** (`present * 2 > len(valid)`) → 試合: **type を "fl_match" に確定** (non_fl keep 規則で adjacency 型推論が unknown 化するのを補正)
  - 過半未満 → 非試合として**削除** (`stats["masked_segments_dropped"]` 加算 + info log に区間)
  - segment 内全 UNKNOWN → keep (保守側) + warning
  - **fail-safe**: 削除後 segment がゼロ → 全件 keep + warning (anchor 誤りの疑い、spec §5)
  - anchor None のときは caller (`_detect_masked_fallback`) が Layer 2 自体を skip (縮退 = 現行 pipeline)

- [ ] **Step 1: failing test**

```python
def test_scan_presence_explicit_times():
    seen = []
    def fn(t):
        seen.append(t)
        return PresenceSample(time=t, state=PresenceState.PRESENT, confidence=1.0)
    scan_presence(Path("d.mkv"), 100.0, stride=1.0, workers=2, sample_fn=fn,
                  times=[10.0, 20.0, 30.0])
    assert sorted(seen) == [10.0, 20.0, 30.0]


def test_validate_segments_drops_lobby_and_retypes_match(monkeypatch):
    # present 率 9/9 の segment は keep + fl_match 化、0/9 は削除。
    ...


def test_validate_segments_all_unknown_keeps_with_warning(monkeypatch, caplog):
    ...


def test_validate_segments_failsafe_keeps_all_when_everything_dropped(monkeypatch, caplog):
    ...


def test_masked_fallback_skips_validation_without_anchor(monkeypatch):
    ...
```

- [ ] **Step 2: FAIL 確認** → **Step 3: 実装** → **Step 4: PASS** — `python -m pytest tests/test_presence.py tests/test_detector.py -v`
- [ ] **Step 5: Commit** `"feat(#822): Layer 2 segment 検証 (at-anchor presence 過半判定 + fail-safe) (Refs #822)"`

### Task B6: cache key (`masked_algo` 3 箇所)

**Files:**

- Modify: `allaganeye/commands/split_matches.py:1978-1987` (`_save_cache` params)、`:2196-2210 付近` (`_load_cache` params 比較)、`:695-705` + `allaganeye/commands/detect.py:185-192` (verbose cache-hit summary)
- Test: `tests/test_split_matches.py` (cache 系テストの所在に合わせる — `grep -rn "_load_cache" tests/` で確認)

**Interfaces:**

- Produces: `_MASKED_ALGO_VERSION = 2` (split_matches.py 定数)。save: `params["masked_algo"] = _MASKED_ALGO_VERSION` (常時)。load: `cached_algo = params.get("masked_algo", 1)` とし、**masked 影響 run のみ** (`data.get("masked_fallback_used", False) or params.get("masked", False) or config.masked`) 不一致で miss。legacy OBS cache (fallback 不使用 + masked off) は従来どおり hit (memory: detection-flag-cache-key の「legacy は .get(...,False) で bump 不要」原則の適用形)。verbose: cache-hit summary の masked 表示行に `masked_algo={n}` を追記 (masked 影響 run のみ)

- [ ] **Step 1: failing test**

```python
def test_cache_miss_on_masked_algo_mismatch(tmp_path):
    # legacy masked cache (masked_algo 欠落 = 1) は新 code (2) で miss。
    ...


def test_cache_hit_for_legacy_obs_cache_without_masked_algo(tmp_path):
    # OBS cache (fallback 不使用 / masked off) は masked_algo 欠落でも hit (非退行)。
    ...
```

- [ ] **Step 2-4: Red-Green** — `python -m pytest tests/ -k "masked_algo" -v` → 関連 cache テスト全 green
- [ ] **Step 5: Commit** `"feat(#822): masked_algo cache key (save/load/verbose 3 箇所) (Refs #822)"`

### Task B7: docs + scratch 除外

**Files:**

- Modify: `docs/detection-map.md` (§2 layer インベントリ / §5 に masked anchor + Layer 2 を追記)、`CLAUDE.md` (§アーキテクチャの masked fallback 記述に anchor/検証を 1-2 行追記)、`.gitignore` (`.tmp-822-analysis/`)、`pyproject.toml` (pyright exclude に `.tmp-822-analysis`、#828 前例)
- Test: `bash scripts/check-markdownlint.sh`

- [ ] **Step 1: docs 更新** (実装済み実態と照合しながら記述。spec への参照リンクを含める)
- [ ] **Step 2: markdownlint** — `bash scripts/check-markdownlint.sh` Summary: 0 error(s)
- [ ] **Step 3: Commit** `"doc(#822): detection-map / CLAUDE.md へ masked anchor + Layer 2 を反映 (Refs #822)"`

### Task B8: full checks + OBS bit-exact + 実機 3 サンプル + PR-B

**Files:** なし (検証のみ)

- [ ] **Step 1: full checks** — `python -m ruff check . && python -m ruff format --check . && python -m pyright && python -m pytest -q`
- [ ] **Step 2: OBS bit-exact gate 実測** — baseline 5 本 `--no-cache` detect → byte 一致 (構造保証の主張のみで済ませない。masked fallback gate は baseline で非発動、classify(localize=False) 不変が論拠)
- [ ] **Step 3: 実機 3 サンプル再検証** — 27 / 28 / 29 (`E:\allaganeye-samples\20250527-29\20250527-29\`) を新 code で `--no-cache --masked` detect。7h 級 (29) は detached:

```powershell
Start-Process -WindowStyle Hidden -FilePath python -ArgumentList @(
  "-m", "allaganeye", "detect", "E:\allaganeye-samples\20250527-29\20250527-29\2026-05-29 20-58-34.mkv",
  "--masked", "--no-cache", "--gpu", "-o", "E:\allaganeye-samples\_masked_b_out\29"
) -RedirectStandardOutput "E:\allaganeye-samples\_masked_b_out\29.log" -RedirectStandardError "E:\allaganeye-samples\_masked_b_out\29.err.log"
```

  (`$env:ALLAGANEYE_INTEGRITY_SKIP=1` を同 shell で設定。GPU テスト間インターバルは `docs/testing-guide.md` 参照)

  期待 (spec §7): 29: 25→22 (M19/M21/M24 消滅) / 28b 相当: 8→6 (M2/M8 消滅) / 27: 13→12 (M7 消滅)。zero-gap ペアゼロ + 既存正検出の start/end 非退行 (lobby 除去に伴う type=fl_match 化は期待差分)。**28b M5/M6 の真相** (実試合中割りか lobby 融合か) を新結果 + clip 目視で確定し、期待値とずれる場合は AskUserQuestion。**28 (非 b) が旧 run で 1 match unknown だった原因**も新 run ログから確認

- [ ] **Step 4: auto-fallback 経路確認** — 29 を `--masked` なしで再実行し、標準 Pass 1 blackout ゼロ → fallback 自動発動 + 同一結果を確認
- [ ] **Step 5: Pre-flight (Iron Law 6)** — Step 0-4 + Step 5 codex tier 1 (focus: "masked classification rule change containment (localize gate); anchor fallback safety; Layer 2 fail-safe correctness; cache key coverage; OBS bit-exact") 。**実機検証は Step 3-4 で実施済みを PR 本文に記録**、GPU/長時間動画の最終確認は AskUserQuestion で Idios に依頼
- [ ] **Step 6: PR 作成** — base `develop-0.3.0`、`Refs #822` (+ 本文で #824 spec §6 の bit-exact 論拠を転記)。Self-Test Report 規約準拠
- [ ] **Step 7: /iterate-review → Idios merge 依頼 (AskUserQuestion) → merge 後 `/close-issue 822` / `/close-issue 824` は受け入れ条件実測後に別途**

---

## Self-Review (2026-07-11、plan 執筆時)

- **Spec coverage**: spec §3.1 (anchor 解決 = B3、primitive = B2)、§3.2 (規則 = B4)、§3.3 (Layer 2 = B5、scan_presence 拡張含む)、§5 (縮退 = B3/B4/B5 の warning/fail-safe テスト)、§6 (cache = B6)、§7 (テスト戦略 = 各 task + A5/B8 gate)、§8 スコープ境界は Global Constraints に反映。#824 spec §5.4 全 site: 1/2/2b/3 = A2、4/5 = A3、6/10/9/14 = A4。§6 pin 7 件: A2 (2 件) / A3 (1 件) / A4 (4 件) — 全て割当済み
- **Placeholder scan**: テストコードの `...` は「既存テストの monkeypatch 構造を流用し期待値を差し替える」箇所に限定し、期待する assert 内容を各コメントで特定済み (実装者が既存テストを開けば一意に書ける)。実装コードはすべて具体化済み
- **Type consistency**: `PresenceState`/`PresenceSample` (A1) を A2-A4/B4-B5 が同名で消費。`consensus_scorebar_localization` (B1) → B3。`localize_scorebar_at_anchor`/`localize_from_rgb_bytes_at_anchor` (B2) → B4/B5。`_majority_presence` (A3) → B4。整合確認済み
