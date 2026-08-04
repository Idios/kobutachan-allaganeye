# metadata.json `capture_regions` フィールド (#810) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** detector が解決した capture region (coarse + segments + 縮退 provenance) を metadata.json の
top-level optional field `capture_regions` として永続化し、cache-hit / `split --from-metadata` /
GUI round-trip の全経路で保全する。

**Architecture:** SSoT (schemas/metadata.schema.json) 起点で codegen → zod → writer を更新。
detector には `brightness_callback` と同型の `region_callback` seam を追加し、最終的に有効だった
領域 (`RegionTimeline`) を 1 回だけ通知する。cache には `masked_fallback_used` と同型で top-level
保存 (key 非対象)。spec: `docs/superpowers/specs/2026-07-07-capture-regions-metadata-schema-design.md`

**Tech Stack:** Python 3.11 (TypedDict codegen = datamodel-code-generator) / JSON Schema
draft-2020-12 / zod 4 / vitest / pytest

## Global Constraints

- OBS 標準 path の検出結果 (boundaries) は bit-exact 不変。本変更は観測 (callback) のみで検出分岐を変えない
- `schema_version` は `"1"` のまま (additive optional field、#569/#591 前例)
- 新規検知 (fresh detection) では `capture_regions` を常に書く。OBS では coarse = FULL_FRAME (受け入れ条件 2)
- `source` / `fallback_reason` は free string (enum にしない)。読み手は unknown 値を受容 (forward compat)
- codegen 生成物 (`allaganeye/metadata_types.py` / `gui/src/types/metadata.generated.ts`) は手編集禁止。`python scripts/codegen/generate.py` で再生成
- コミットは Conventional Commits 形式 + `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` 末尾行 (memory 規約)
- PR 本文 / commit に Closes / Fixes / Resolves 禁止 (Iron Law 4)。Refs #810 を使う
- worktree: `E:\projects\kobutachan-tools\kobutachan-allaganeye\.claude\worktrees\810-capture-regions` (branch `claude/810-capture-regions-metadata`)。Bash cwd drift に注意し、git / pytest は `cd <worktree> &&` 明示 (memory 教訓)

---

### Task 1: Schema layer (JSON Schema + codegen + zod + integrity tests)

**Files:**

- Modify: `schemas/metadata.schema.json`
- Regenerate: `allaganeye/metadata_types.py` / `gui/src/types/metadata.generated.ts` (codegen)
- Modify: `gui/src/types/metadata.schema.ts`
- Test: `tests/test_metadata_schema.py`
- Test: `gui/src/types/__tests__/zod-schema-integrity.test.ts`
- Test: `gui/src/types/__tests__/schema-validity.test.ts`
- Test: `gui/src/state/metadataStore.test.ts`

**Interfaces:**

- Produces: JSON Schema `$defs`: `CaptureRegion` / `RegionSegment` / `CaptureRegions`、root optional property `capture_regions`。生成 TypedDict `allaganeye.metadata_types.CaptureRegions` (後続 Task 4 が import する)。zod `CaptureRegionsSchema` + `MetadataSchema.shape.capture_regions` (optional)

- [ ] **Step 1: Python schema テストを先に書く (red)**

`tests/test_metadata_schema.py` 末尾に追加:

```python
def _capture_regions_sample() -> dict:
    return {
        "coarse": {
            "x": 0.0,
            "y": 0.0,
            "w": 1.0,
            "h": 1.0,
            "confidence": 1.0,
            "source": "fallback",
        },
        "segments": [],
        "fallback_reason": None,
    }


def test_capture_regions_valid_sample_passes():
    # #810: OBS 標準 run の形 (coarse=FULL_FRAME / segments 空 / 縮退なし)
    schema = _load_schema()
    sample = _valid_sample()
    sample["capture_regions"] = _capture_regions_sample()
    Draft202012Validator(schema).validate(sample)


def test_capture_regions_omitted_accepted():
    # pre-#810 metadata.json は field 欠落 = valid (後方互換)
    schema = _load_schema()
    sample = _valid_sample()
    assert "capture_regions" not in sample
    Draft202012Validator(schema).validate(sample)


def test_capture_regions_band_with_fallback_reason_passes():
    # --vtuber run: band ROI + 縮退 provenance の両形
    schema = _load_schema()
    sample = _valid_sample()
    regions = _capture_regions_sample()
    regions["coarse"] = {
        "x": 0.1,
        "y": 0.0,
        "w": 0.76,
        "h": 0.042,
        "confidence": 0.9,
        "source": "band",
    }
    sample["capture_regions"] = regions
    Draft202012Validator(schema).validate(sample)
    # 縮退形: coarse=FULL_FRAME + fallback_reason 文字列
    regions2 = _capture_regions_sample()
    regions2["fallback_reason"] = "consensus_miss"
    sample["capture_regions"] = regions2
    Draft202012Validator(schema).validate(sample)


def test_capture_regions_segments_entry_passes():
    schema = _load_schema()
    sample = _valid_sample()
    regions = _capture_regions_sample()
    regions["segments"] = [
        {
            "time_range": [60.0, 1200.0],
            "region": {
                "x": 0.1,
                "y": 0.05,
                "w": 0.8,
                "h": 0.7,
                "confidence": 0.8,
                "source": "tierB",
            },
        }
    ]
    sample["capture_regions"] = regions
    Draft202012Validator(schema).validate(sample)


def test_capture_regions_coordinate_out_of_range_rejected():
    schema = _load_schema()
    sample = _valid_sample()
    regions = _capture_regions_sample()
    regions["coarse"]["x"] = 1.5
    sample["capture_regions"] = regions
    assert not Draft202012Validator(schema).is_valid(sample)


def test_capture_regions_empty_source_rejected():
    schema = _load_schema()
    sample = _valid_sample()
    regions = _capture_regions_sample()
    regions["coarse"]["source"] = ""
    sample["capture_regions"] = regions
    assert not Draft202012Validator(schema).is_valid(sample)


def test_capture_regions_missing_fallback_reason_rejected():
    # writer 契約: fallback_reason は required nullable (常に明示 emit)
    schema = _load_schema()
    sample = _valid_sample()
    regions = _capture_regions_sample()
    del regions["fallback_reason"]
    sample["capture_regions"] = regions
    assert not Draft202012Validator(schema).is_valid(sample)


def test_capture_regions_unknown_field_rejected():
    schema = _load_schema()
    sample = _valid_sample()
    regions = _capture_regions_sample()
    regions["future_field"] = 1
    sample["capture_regions"] = regions
    assert not Draft202012Validator(schema).is_valid(sample)
```

- [ ] **Step 2: red 確認**

Run: `cd E:\projects\kobutachan-tools\kobutachan-allaganeye\.claude\worktrees\810-capture-regions && python -m pytest tests/test_metadata_schema.py -v -k capture_regions`
Expected: `test_capture_regions_omitted_accepted` 以外 FAIL (schema 未更新なので `additionalProperties: false` が root の `capture_regions` を拒否)

- [ ] **Step 3: schemas/metadata.schema.json を更新**

root `properties` の `brightness_samples` の直後に追加:

```json
    "capture_regions": {
      "$ref": "#/$defs/CaptureRegions"
    }
```

`$defs` の `BrightnessSamples` の後に追加 (JSON なので末尾カンマ注意):

```json
    "CaptureRegion": {
      "title": "CaptureRegion",
      "description": "Game capture rectangle in normalized [0,1] frame coordinates (#810). Serialized form of allaganeye/video/capture_region.py::CaptureRegion (to_dict / from_dict).",
      "type": "object",
      "additionalProperties": false,
      "required": ["x", "y", "w", "h", "confidence", "source"],
      "properties": {
        "x": { "type": "number", "minimum": 0, "maximum": 1 },
        "y": { "type": "number", "minimum": 0, "maximum": 1 },
        "w": { "type": "number", "minimum": 0, "maximum": 1 },
        "h": { "type": "number", "minimum": 0, "maximum": 1 },
        "confidence": {
          "description": "Detector confidence in [0,1].",
          "type": "number",
          "minimum": 0,
          "maximum": 1
        },
        "source": {
          "description": "Detector that produced the region. Documented values: \"fallback\" (FULL_FRAME), \"band\" (scorebar band ROI), \"tierA\" (game rectangle), \"tierB\" (future per-segment precise). Free string: readers must accept unknown values (forward compat, same philosophy as warning codes).",
          "type": "string",
          "minLength": 1
        }
      }
    },
    "RegionSegment": {
      "title": "RegionSegment",
      "description": "Per-segment precise region entry (Tier B; consumed by #480/#481). time_range is [t0, t1] in seconds.",
      "type": "object",
      "additionalProperties": false,
      "required": ["time_range", "region"],
      "properties": {
        "time_range": {
          "type": "array",
          "items": { "type": "number", "minimum": 0 },
          "minItems": 2,
          "maxItems": 2
        },
        "region": { "$ref": "#/$defs/CaptureRegion" }
      }
    },
    "CaptureRegions": {
      "title": "CaptureRegions",
      "description": "Capture-region timeline resolved by detection (#810; serialized RegionTimeline). `coarse` is the region actually used for Pass 1 brightness measurement: FULL_FRAME on standard OBS runs, the scorebar band ROI (source=\"band\", NOT the full game rectangle) on --vtuber runs, and the mask-free game rectangle (source=\"tierA\") when the masked fallback produced the result. `segments` is always [] until Tier B per-segment detection lands (#480). `fallback_reason` records band-anchor degradation on --vtuber runs (documented values: \"anchor_error\" = Stage 0 exception, \"consensus_miss\" = no band consensus); null = no degradation. Optional at the root: pre-#810 metadata.json doesn't carry it; cache hits from pre-#810 vtuber/masked caches omit it (region unknown).",
      "type": "object",
      "additionalProperties": false,
      "required": ["coarse", "segments", "fallback_reason"],
      "properties": {
        "coarse": { "$ref": "#/$defs/CaptureRegion" },
        "segments": {
          "type": "array",
          "items": { "$ref": "#/$defs/RegionSegment" }
        },
        "fallback_reason": {
          "type": ["string", "null"],
          "description": "Band-anchor degradation provenance. Free string (readers accept unknown values); null = no degradation."
        }
      }
    }
```

- [ ] **Step 4: codegen 再実行 + Python テスト green 確認**

Run: `cd E:\projects\kobutachan-tools\kobutachan-allaganeye\.claude\worktrees\810-capture-regions && python scripts/codegen/generate.py && python -m pytest tests/test_metadata_schema.py tests/test_metadata_types.py -v`
Expected: codegen が `metadata_types.py` / `metadata.generated.ts` を更新し、pytest 全 PASS。
`git diff allaganeye/metadata_types.py` に `class CaptureRegions(TypedDict)` (coarse / segments / `fallback_reason: str | None`) と `Metadata` への `capture_regions: NotRequired[CaptureRegions]` が現れること

- [ ] **Step 5: GUI zod テストを先に書く (red)**

`gui/src/types/__tests__/zod-schema-integrity.test.ts` — import に `CaptureRegionSchema, CaptureRegionsSchema, RegionSegmentSchema` を追加し、describe 末尾に:

```ts
  it('CaptureRegion: properties match', () => {
    expect(zodKeys(CaptureRegionSchema)).toEqual(
      jsonProps(schema.$defs.CaptureRegion as JsonObjectSchema),
    );
  });

  it('CaptureRegion: required match', () => {
    expect(zodRequired(CaptureRegionSchema)).toEqual(
      jsonRequired(schema.$defs.CaptureRegion as JsonObjectSchema),
    );
  });

  it('RegionSegment: properties match', () => {
    expect(zodKeys(RegionSegmentSchema)).toEqual(
      jsonProps(schema.$defs.RegionSegment as JsonObjectSchema),
    );
  });

  it('RegionSegment: required match', () => {
    expect(zodRequired(RegionSegmentSchema)).toEqual(
      jsonRequired(schema.$defs.RegionSegment as JsonObjectSchema),
    );
  });

  it('CaptureRegions: properties match', () => {
    expect(zodKeys(CaptureRegionsSchema)).toEqual(
      jsonProps(schema.$defs.CaptureRegions as JsonObjectSchema),
    );
  });

  it('CaptureRegions: required match', () => {
    expect(zodRequired(CaptureRegionsSchema)).toEqual(
      jsonRequired(schema.$defs.CaptureRegions as JsonObjectSchema),
    );
  });
```

`gui/src/types/__tests__/schema-validity.test.ts` (test_metadata_schema.py の TS mirror) にも
capture_regions の valid / reject ケースを既存パターンに合わせて追加する (OBS FULL_FRAME sample が
validate に通る / `x: 1.5` が invalid の 2 ケースで十分。Python 側の網羅は Step 1 が担う)。

`gui/src/state/metadataStore.test.ts` に round-trip 保全テストを追加 (既存の
normalizeForPersistence テスト群の隣。既存テストの Metadata fixture 構築ヘルパに合わせること):

```ts
it('normalizeForPersistence preserves capture_regions (#810)', () => {
  // top-level spread で保持される契約を pin する (欠落で GUI 適用時に領域が消えると
  // #481 minimap 等の consumer が cached 情報を失う)
  const meta = buildMetadata(); // 既存 fixture ヘルパ (ファイル内の実名に合わせる)
  meta.capture_regions = {
    coarse: { x: 0, y: 0, w: 1, h: 1, confidence: 1, source: 'fallback' },
    segments: [],
    fallback_reason: null,
  };
  const normalized = normalizeForPersistence(meta);
  expect(normalized.capture_regions).toEqual(meta.capture_regions);
});
```

(`normalizeForPersistence` が export されていない場合は、既存テストが使っている経路
= store の apply 経由 or 内部関数 export に合わせる。既存テストのアクセス方法を踏襲する)

- [ ] **Step 6: red 確認**

Run: `cd E:\projects\kobutachan-tools\kobutachan-allaganeye\.claude\worktrees\810-capture-regions\gui && npm test -- --run src/types src/state/metadataStore.test.ts`
Expected: integrity 新ケース FAIL (`CaptureRegionSchema` 未定義の import error) — vitest の import error も red として扱う

- [ ] **Step 7: zod schema を実装**

`gui/src/types/metadata.schema.ts` — `BrightnessSamplesSchema` の後に追加:

```ts
/**
 * #810 — capture-region timeline resolved by detection. `coarse` is the
 * region Pass 1 actually measured brightness on (FULL_FRAME on standard
 * OBS runs; the scorebar band ROI on --vtuber runs; the mask-free game
 * rectangle when the masked fallback produced the result). `source` and
 * `fallback_reason` are free strings — readers must accept unknown
 * values (forward compat, same philosophy as warning codes).
 */
export const CaptureRegionSchema = z.object({
  x: z.number().min(0).max(1),
  y: z.number().min(0).max(1),
  w: z.number().min(0).max(1),
  h: z.number().min(0).max(1),
  confidence: z.number().min(0).max(1),
  source: z.string().min(1),
});

export const RegionSegmentSchema = z.object({
  time_range: z.tuple([z.number().min(0), z.number().min(0)]),
  region: CaptureRegionSchema,
});

export const CaptureRegionsSchema = z.object({
  coarse: CaptureRegionSchema,
  segments: z.array(RegionSegmentSchema),
  fallback_reason: z.string().nullable(),
});
```

`MetadataSchema` の `brightness_samples` の後に追加:

```ts
    /**
     * #810 -- capture-region timeline. Optional because pre-#810
     * metadata.json (and cache hits from pre-#810 vtuber/masked caches)
     * don't carry it. GUI has no consumer yet; the field round-trips
     * through load -> apply unchanged.
     */
    capture_regions: CaptureRegionsSchema.optional(),
```

- [ ] **Step 8: GUI green 確認**

Run: `cd E:\projects\kobutachan-tools\kobutachan-allaganeye\.claude\worktrees\810-capture-regions\gui && npm test -- --run && npm run typecheck && npm run lint`
Expected: 全 PASS (integrity の root properties テストは zod 追加により再び一致)

- [ ] **Step 9: Python 全体 green + commit**

Run: `cd E:\projects\kobutachan-tools\kobutachan-allaganeye\.claude\worktrees\810-capture-regions && python -m pytest tests/test_metadata_schema.py tests/test_metadata_types.py -q && ruff check . && ruff format --check . && pyright`
Expected: 全 PASS

```bash
cd E:\projects\kobutachan-tools\kobutachan-allaganeye\.claude\worktrees\810-capture-regions
git add schemas/metadata.schema.json allaganeye/metadata_types.py gui/src/types/metadata.generated.ts gui/src/types/metadata.schema.ts tests/test_metadata_schema.py gui/src/types/__tests__/zod-schema-integrity.test.ts gui/src/types/__tests__/schema-validity.test.ts gui/src/state/metadataStore.test.ts
git commit -m "feat(schema): metadata.json に capture_regions field を追加 (Refs #810)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: RegionTimeline 拡張 (fallback_reason + from_dict)

**Files:**

- Modify: `allaganeye/video/capture_region.py:109-124` (RegionTimeline) / `:27` (source docstring)
- Test: `tests/test_capture_region.py`

**Interfaces:**

- Consumes: 既存 `CaptureRegion.to_dict` / `from_dict`
- Produces: `RegionTimeline(coarse, segments=[], fallback_reason=None)`。
  `RegionTimeline.to_dict() -> dict` (keys: coarse / segments / fallback_reason)。
  `RegionTimeline.from_dict(d: dict) -> RegionTimeline` (fallback_reason 欠落 dict も受容)。
  Task 3 (detector) と Task 4 (cache 合成) が使う

- [ ] **Step 1: failing test を書く**

`tests/test_capture_region.py` 末尾に追加:

```python
class TestRegionTimelineSerialization:
    """#810: metadata.json capture_regions round-trip contract."""

    def test_to_dict_includes_fallback_reason_null(self):
        from allaganeye.video.capture_region import FULL_FRAME, RegionTimeline

        d = RegionTimeline(coarse=FULL_FRAME).to_dict()
        assert d["fallback_reason"] is None
        assert d["segments"] == []
        assert d["coarse"]["source"] == "fallback"

    def test_to_dict_includes_fallback_reason_value(self):
        from allaganeye.video.capture_region import FULL_FRAME, RegionTimeline

        d = RegionTimeline(
            coarse=FULL_FRAME, fallback_reason="consensus_miss"
        ).to_dict()
        assert d["fallback_reason"] == "consensus_miss"

    def test_round_trip_with_segments(self):
        from allaganeye.video.capture_region import CaptureRegion, RegionTimeline

        band = CaptureRegion(0.1, 0.0, 0.76, 0.042, confidence=0.9, source="band")
        seg = CaptureRegion(0.1, 0.05, 0.8, 0.7, confidence=0.8, source="tierB")
        timeline = RegionTimeline(
            coarse=band,
            segments=[((60.0, 1200.0), seg)],
            fallback_reason=None,
        )
        restored = RegionTimeline.from_dict(timeline.to_dict())
        assert restored == timeline

    def test_from_dict_accepts_legacy_shape_without_fallback_reason(self):
        # to_dict は常に emit するが、from_dict は防御的に欠落を None 扱いする
        from allaganeye.video.capture_region import FULL_FRAME, RegionTimeline

        d = {"coarse": FULL_FRAME.to_dict(), "segments": []}
        restored = RegionTimeline.from_dict(d)
        assert restored.fallback_reason is None
```

- [ ] **Step 2: red 確認**

Run: `cd E:\projects\kobutachan-tools\kobutachan-allaganeye\.claude\worktrees\810-capture-regions && python -m pytest tests/test_capture_region.py -v -k RegionTimelineSerialization`
Expected: FAIL (`fallback_reason` unexpected keyword / KeyError / `from_dict` AttributeError)

- [ ] **Step 3: RegionTimeline を拡張**

`allaganeye/video/capture_region.py` — `RegionTimeline` を以下に置換:

```python
@dataclass
class RegionTimeline:
    """Coarse region (Pass 1) + per-segment precise regions (#480/#481).

    ``fallback_reason`` (#810) は band anchor 縮退の provenance:
    "anchor_error" (Stage 0 例外) / "consensus_miss" (consensus 不成立) /
    None (縮退なし)。free string (読み手は unknown 値を受容)。
    """

    coarse: CaptureRegion
    segments: list[tuple[tuple[float, float], CaptureRegion]] = field(
        default_factory=list
    )
    fallback_reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "coarse": self.coarse.to_dict(),
            "segments": [
                {"time_range": [t0, t1], "region": r.to_dict()}
                for (t0, t1), r in self.segments
            ],
            "fallback_reason": self.fallback_reason,
        }

    @classmethod
    def from_dict(cls, d: dict) -> RegionTimeline:
        return cls(
            coarse=CaptureRegion.from_dict(d["coarse"]),
            segments=[
                (
                    (s["time_range"][0], s["time_range"][1]),
                    CaptureRegion.from_dict(s["region"]),
                )
                for s in d.get("segments", [])
            ],
            fallback_reason=d.get("fallback_reason"),
        )
```

同ファイル `:27` の source コメントを実態に合わせて修正:

```python
    source: str = "fallback"  # "tierA" | "tierB" | "band" | "fallback"
```

- [ ] **Step 4: green 確認 + commit**

Run: `cd E:\projects\kobutachan-tools\kobutachan-allaganeye\.claude\worktrees\810-capture-regions && python -m pytest tests/test_capture_region.py -q && ruff check allaganeye/video/capture_region.py tests/test_capture_region.py && pyright`
Expected: 全 PASS

```bash
cd E:\projects\kobutachan-tools\kobutachan-allaganeye\.claude\worktrees\810-capture-regions
git add allaganeye/video/capture_region.py tests/test_capture_region.py
git commit -m "feat(video): RegionTimeline に fallback_reason + from_dict を追加 (Refs #810)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: detector 配線 (region_callback seam)

**Files:**

- Modify: `allaganeye/video/detector.py` — `_resolve_detect_region` (:264-307) /
  `detect_match_boundaries` (:377-571) / `_detect_masked_fallback` (:661-794)
- Test: `tests/test_detector.py` (既存 4 テスト更新 + 新規 5 テスト)

**Interfaces:**

- Consumes: Task 2 の `RegionTimeline(coarse, fallback_reason=...)`
- Produces: `detect_match_boundaries(..., region_callback: Callable[[RegionTimeline], None] | None = None)`。
  callback は**成功 run で必ず 1 回だけ**、最終的に有効だった領域で発火。
  内部変更: `_resolve_detect_region -> tuple[CaptureRegion, str | None]`、
  `_detect_masked_fallback -> tuple[list[MatchBoundary], CaptureRegion] | None`。
  Task 4 (`_run_detection` / commands) が region_callback を forward する

- [ ] **Step 1: 新規 failing test を書く**

`tests/test_detector.py` の「Task B4: Stage 0 band anchor resolution」セクション末尾に追加。
既存テスト (`test_detect_match_boundaries_passes_region_to_all_three_call_sites` 周辺) の
monkeypatch パターンを踏襲する:

```python
# ============================================================
# #810: region_callback seam (capture_regions 永続化の配線)
# ============================================================


def _detect_with_region_callback(monkeypatch, *, vtuber, resolve_result=None, **kwargs):
    """共通ハーネス: scan/refine を stub し region_callback の発火を捕捉する。"""
    from pathlib import Path

    from allaganeye.video import detector as det
    from allaganeye.video.capture_region import RegionTimeline

    if resolve_result is not None:
        monkeypatch.setattr(
            det, "_resolve_detect_region", lambda vp, dh: resolve_result
        )
    monkeypatch.setattr(
        det, "_scan_cpu", lambda *a, **kw: {0.0: 100.0, 1.0: 5.0, 2.0: 100.0}
    )
    monkeypatch.setattr(det, "_refine_blackout_regions", lambda *a, **kw: [])

    fired: list[RegionTimeline] = []
    det.detect_match_boundaries(
        Path("test.mp4"),
        duration_hint=3.0,
        sample_interval=1.0,
        min_match_duration=0.5,
        use_gpu=False,
        vtuber=vtuber,
        region_callback=fired.append,
        **kwargs,
    )
    return fired


def test_region_callback_standard_path_full_frame(monkeypatch):
    fired = _detect_with_region_callback(monkeypatch, vtuber=False)
    assert len(fired) == 1
    assert fired[0].coarse.is_full_frame()
    assert fired[0].fallback_reason is None
    assert fired[0].segments == []


def test_region_callback_vtuber_band(monkeypatch):
    from allaganeye.video.capture_region import CaptureRegion

    band = CaptureRegion(0.1, 0.0, 0.76, 0.042, confidence=0.9, source="band")
    fired = _detect_with_region_callback(
        monkeypatch, vtuber=True, resolve_result=(band, None)
    )
    assert len(fired) == 1
    assert fired[0].coarse == band
    assert fired[0].fallback_reason is None


def test_region_callback_vtuber_degraded_carries_reason(monkeypatch):
    from allaganeye.video.capture_region import FULL_FRAME

    fired = _detect_with_region_callback(
        monkeypatch, vtuber=True, resolve_result=(FULL_FRAME, "anchor_error")
    )
    assert len(fired) == 1
    assert fired[0].coarse.is_full_frame()
    assert fired[0].fallback_reason == "anchor_error"


def test_region_callback_masked_fallback_reports_mask_rect(monkeypatch):
    from pathlib import Path

    from allaganeye.video import detector as det
    from allaganeye.video.capture_region import CaptureRegion, RegionTimeline

    rect = CaptureRegion(0.05, 0.1, 0.8, 0.75, confidence=0.8, source="tierA")
    segments = [{"start": 10.0, "end": 500.0, "type": "fl_match"}]
    monkeypatch.setattr(
        det, "_detect_masked_fallback", lambda *a, **kw: (segments, rect)
    )
    # 標準 Pass 1 が 0 blackout -> masked auto-trigger (#821 と同じ経路)
    monkeypatch.setattr(det, "_scan_cpu", lambda *a, **kw: {0.0: 100.0, 1.0: 100.0})

    fired: list[RegionTimeline] = []
    result = det.detect_match_boundaries(
        Path("test.mp4"),
        duration_hint=2.0,
        sample_interval=1.0,
        min_match_duration=0.5,
        use_gpu=False,
        region_callback=fired.append,
    )
    assert result == segments
    assert len(fired) == 1
    assert fired[0].coarse == rect
    assert fired[0].fallback_reason is None


def test_resolve_detect_region_returns_reason_tuple(monkeypatch):
    # #810: 縮退 provenance を呼び出し側へ返す (metadata へ記録するため)
    from pathlib import Path

    from allaganeye.video import capture_region as cr
    from allaganeye.video import detector as det

    # (a) 例外 -> anchor_error
    def _boom(**kw):
        raise RuntimeError("anchor exploded")

    monkeypatch.setattr(cr, "detect_scorebar_band_region", _boom)
    region, reason = det._resolve_detect_region(Path("dummy.mp4"), 400.0)
    assert region.is_full_frame()
    assert reason == "anchor_error"

    # (b) consensus 不成立 (非例外 FULL_FRAME) -> consensus_miss
    monkeypatch.setattr(cr, "detect_scorebar_band_region", lambda **kw: cr.FULL_FRAME)
    region, reason = det._resolve_detect_region(Path("dummy.mp4"), 400.0)
    assert region.is_full_frame()
    assert reason == "consensus_miss"

    # (c) 解決成功 -> reason なし
    band = cr.CaptureRegion(0.1, 0.0, 0.76, 0.042, confidence=0.9, source="band")
    monkeypatch.setattr(cr, "detect_scorebar_band_region", lambda **kw: band)
    region, reason = det._resolve_detect_region(Path("dummy.mp4"), 400.0)
    assert region == band
    assert reason is None
```

- [ ] **Step 2: red 確認**

Run: `cd E:\projects\kobutachan-tools\kobutachan-allaganeye\.claude\worktrees\810-capture-regions && python -m pytest tests/test_detector.py -v -k "region_callback or returns_reason_tuple"`
Expected: FAIL (`region_callback` unexpected keyword / tuple unpack error)

- [ ] **Step 3: detector.py を実装**

(a) `_resolve_detect_region` — シグネチャと縮退分岐を変更 (logger.warning は既存のまま維持):

```python
def _resolve_detect_region(
    video_path: Path, duration_hint: float
) -> tuple[CaptureRegion, str | None]:
    """Stage 0: scorebar 帯 anchor を解決する。失敗時は FULL_FRAME (OBS 安全縮退)。

    OBS (全画面 game) では localize がインセット帯を見つけられず consensus が
    成立しないため FULL_FRAME に縮退し、検出は現行と bit-exact になる。VTuber は
    帯 ROI が解決される。anchor の例外は決して検出を壊さない (FULL_FRAME に握り潰す)。

    Returns:
        (region, fallback_reason)。fallback_reason は #810 の縮退 provenance:
        "anchor_error" (例外縮退) / "consensus_miss" (consensus 不成立) /
        None (解決成功)。metadata.json capture_regions.fallback_reason へ記録される。
    """
    from allaganeye.video.capture_region import (
        detect_scorebar_band_region,
        localize_from_rgb_bytes,
    )

    def _localize_at(t: float):
        return localize_from_rgb_bytes(
            _probe_frame_rgb_hires(video_path, t),
            height=_SCOREBAR_V2_PROBE_HEIGHT,
            width=_SCOREBAR_V2_PROBE_WIDTH,
        )

    try:
        region = detect_scorebar_band_region(
            duration=duration_hint,
            probe_w=_SCOREBAR_V2_PROBE_WIDTH,
            probe_h=_SCOREBAR_V2_PROBE_HEIGHT,
            localize_fn=_localize_at,
        )
    except Exception:
        # Anchor failure must never break detect: degrade to FULL_FRAME so the
        # OBS / error path stays bit-exact with the pre-region behavior.
        # R4: 縮退自体は意図的設計だが、silent にせず痕跡を残す (診断性のみ)。
        logger.warning(
            "scorebar band anchor failed; degrading to FULL_FRAME", exc_info=True
        )
        return FULL_FRAME, "anchor_error"
    if region.is_full_frame():
        # consensus-miss (非例外縮退) も silent にしない (R5): --vtuber 明示 run
        # が FULL_FRAME (汚染 path) で続行することを痕跡に残す。
        logger.warning(
            "band anchor found no scorebar-band consensus; "
            "continuing with FULL_FRAME (--vtuber)"
        )
        return region, "consensus_miss"
    logger.debug("band anchor resolved: %s", region)
    return region, None
```

(b) `detect_match_boundaries` — パラメータ追加 (`masked_fallback_callback` の直後):

```python
# #810: 最終的に有効だった capture region (RegionTimeline) で成功 run ごとに
# 1 回だけ呼ばれる。masked fallback 採用時は mask-free rect、それ以外は
# Stage 0 の解決結果 (band or FULL_FRAME + fallback_reason)。commands 層が
# metadata.json capture_regions として永続化する (brightness_callback と同型)。
region_callback: Callable[[RegionTimeline], None] | None = (None,)
```

Stage 0 呼び出し (:461-463) を tuple unpack に変更:

```python
    detect_region, region_fallback_reason = (
        _resolve_detect_region(video_path, duration_hint) if vtuber else (FULL_FRAME, None)
    )
```

masked 分岐 (:548-571) — 採用時に callback を発火してから return:

```python
    if not vtuber and (masked or not blackout_times):
        masked_result = _detect_masked_fallback(
            ...(既存引数そのまま)...
        )
        if masked_result is not None:
            masked_segments, masked_region = masked_result
            if masked_fallback_callback is not None:
                masked_fallback_callback()
            if region_callback is not None:
                # masked path の縮退 (mask 不発見) はここに到達しない (None 返却で
                # 標準 path 続行) ため fallback_reason は常に None。
                region_callback(RegionTimeline(coarse=masked_region))
            return masked_segments
```

masked 分岐の直後 (標準 / vtuber path 確定点) に標準側の発火を追加:

```python
    # #810: この時点で標準 / vtuber path 確定 (masked fallback 不採用)。
    # Pass 1 で実際に使った detect_region + Stage 0 縮退 provenance を通知する。
    if region_callback is not None:
        region_callback(
            RegionTimeline(coarse=detect_region, fallback_reason=region_fallback_reason)
        )
```

import 追加: `detector.py` 冒頭の `capture_region` import 群に `RegionTimeline` を追加
(既存の `from allaganeye.video.capture_region import CaptureRegion, FULL_FRAME` 形式に合わせる)。

(c) `_detect_masked_fallback` — 返り値を tuple に変更:

- シグネチャ: `-> tuple[list[MatchBoundary], CaptureRegion] | None`
- docstring 1 行目の Returns 記述を「Returns ``(segments, region)``, or ``None`` when no
  mask-free region is found」に更新
- 末尾 (:787-794) を変更:

```python
    effective_min = min(min_blackout_duration, _REFINED_MIN_BLACKOUT)
    segments = _filter_and_extract_segments(
        refined_regions,
        duration_hint,
        min_match_duration,
        effective_min,
        classifications=classifications,
        stats=stats,
    )
    return segments, region
```

- [ ] **Step 4: 既存テストを tuple 契約に更新**

`grep -n "_resolve_detect_region\|_detect_masked_fallback" tests/*.py` で全 monkeypatch /
直接呼び出しサイトを列挙し、以下を含めて全件更新する:

- `tests/test_detector.py:2713` `test_resolve_detect_region_falls_back_full_frame_on_probe_failure`:
  `region = det._resolve_detect_region(...)` → `region, reason = det._resolve_detect_region(...)`、
  末尾に `assert reason == "consensus_miss"` を追加 (probe 全滅 = 非例外 consensus 不成立)
- `tests/test_detector.py:2724` `..._swallows_exceptions...`: tuple unpack + `assert reason == "anchor_error"`
- `tests/test_detector.py:2743` `..._warns_on_consensus_miss...`: tuple unpack + `assert reason == "consensus_miss"`
- `tests/test_detector.py:2771` `test_detect_match_boundaries_passes_region_to_all_three_call_sites`:
  `monkeypatch.setattr(det, "_resolve_detect_region", lambda vp, dh: sentinel)` →
  `lambda vp, dh: (sentinel, None)`
- `_detect_masked_fallback` を直接呼ぶ / stub する既存テスト (masked 系):
  返り値を `(segments, region)` tuple に合わせて unpack / stub 修正

- [ ] **Step 5: green 確認 + commit**

Run: `cd E:\projects\kobutachan-tools\kobutachan-allaganeye\.claude\worktrees\810-capture-regions && python -m pytest tests/test_detector.py -q && ruff check . && ruff format --check . && pyright`
Expected: 全 PASS

```bash
cd E:\projects\kobutachan-tools\kobutachan-allaganeye\.claude\worktrees\810-capture-regions
git add allaganeye/video/detector.py tests/test_detector.py
git commit -m "feat(detector): region_callback seam で capture region を通知 (Refs #810)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: cache + payload + run_detect / run_split 配線

**Files:**

- Modify: `allaganeye/commands/split_matches.py` — `_run_detection` (:821) / `_save_cache` (:1856) /
  `_build_metadata_payload` (:1413) / `_split_and_write_metadata` (:1320) / `run_split` (:211-330) /
  cache-hit 分岐 (:155-173) / `_read_cached_masked_fallback` (:1910) の直後に新 helper
- Modify: `allaganeye/commands/detect.py` — import (:23-46) / cache-hit (:137-149) /
  `_run_detection` 呼び出し (:191-204) / `_save_cache` (:226-234) / payload (:290-312)
- Test: `tests/test_split_matches.py` / `tests/test_detect.py` / `tests/test_metadata_types.py`

**Interfaces:**

- Consumes: Task 1 の `allaganeye.metadata_types.CaptureRegions` (TypedDict)、
  Task 2 の `RegionTimeline` / `FULL_FRAME`、Task 3 の `region_callback`
- Produces: `_build_metadata_payload(..., capture_regions: CaptureRegions | None = None)`、
  `_save_cache(..., capture_regions: dict | None = None)`、
  `_read_cached_capture_regions(cache_path: Path) -> dict | None`、
  `_format_region_token(regions: dict | None) -> str`。
  Task 5 (from-metadata preserve) が `_split_and_write_metadata` の
  `capture_regions` kwarg を使う

- [ ] **Step 1: failing test を書く**

`tests/test_metadata_types.py` — `_build_payload` に kwarg を追加 (required TypedDict 網羅
テストが新 optional field で壊れないことも同時に担保):

```python
# _build_payload 内の _build_metadata_payload 呼び出しに追加:
        capture_regions={
            "coarse": {
                "x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0,
                "confidence": 1.0, "source": "fallback",
            },
            "segments": [],
            "fallback_reason": None,
        },
```

`tests/test_split_matches.py` — 既存 cache テスト群 (`:1148` 周辺の class) の隣に追加:

```python
class TestCaptureRegionsCache:
    """#810: capture_regions の cache 保存 / 引継 / legacy 合成。"""

    def _write_cache(self, cache_path, video_path, *, extra=None, params_extra=None):
        # 既存 cache fixture (cache_video / cache_config) 群のヘルパに合わせて、
        # _save_cache を直接使わず生 JSON を書いて legacy 形を再現する
        import json

        stat = video_path.resolve().stat()
        from allaganeye.commands.split_matches import _CACHE_VERSION

        data = {
            "cache_version": _CACHE_VERSION,
            "source": str(video_path.resolve()),
            "source_size": stat.st_size,
            "source_mtime": stat.st_mtime,
            "probe": {
                "duration": 100.0,
                "width": 1920,
                "height": 1080,
                "fps": 60.0,
                "codec": "h264",
            },
            "params": {
                "sample_interval": 2.0,
                "blackout_threshold": 15.0,
                "min_match_duration": 300.0,
                "min_blackout_duration": 3.0,
                "no_audio": False,
                "vtuber": False,
                "masked": False,
                "keep_trailing": False,
                **(params_extra or {}),
            },
            "masked_fallback_used": False,
            "boundaries": [{"start": 10.0, "end": 50.0, "type": "fl_match"}],
            **(extra or {}),
        }
        cache_path.write_text(json.dumps(data), encoding="utf-8")

    def test_save_cache_records_capture_regions(self, cache_video, tmp_path):
        from allaganeye.commands.split_matches import _save_cache
        import json

        cache_path = tmp_path / ".detection_cache.json"
        regions = {
            "coarse": {
                "x": 0.0,
                "y": 0.0,
                "w": 1.0,
                "h": 1.0,
                "confidence": 1.0,
                "source": "fallback",
            },
            "segments": [],
            "fallback_reason": None,
        }
        _save_cache(
            cache_path,
            cache_video,
            {"duration": 100.0, "width": 1920, "height": 1080, "fps": 60.0},
            2.0,
            SplitConfig(output_dir=tmp_path),
            [{"start": 10.0, "end": 50.0, "type": "fl_match"}],
            capture_regions=regions,
        )
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        assert data["capture_regions"] == regions

    def test_read_cached_capture_regions_returns_recorded(self, cache_video, tmp_path):
        from allaganeye.commands.split_matches import _read_cached_capture_regions

        cache_path = tmp_path / ".detection_cache.json"
        regions = {
            "coarse": {
                "x": 0.1,
                "y": 0.0,
                "w": 0.76,
                "h": 0.042,
                "confidence": 0.9,
                "source": "band",
            },
            "segments": [],
            "fallback_reason": None,
        }
        self._write_cache(cache_path, cache_video, extra={"capture_regions": regions})
        assert _read_cached_capture_regions(cache_path) == regions

    def test_read_cached_capture_regions_legacy_standard_synthesizes_full_frame(
        self, cache_video, tmp_path
    ):
        # pre-#810 cache + 標準 path (vtuber=False / masked_fallback_used=False)
        # は FULL_FRAME 確定なので合成する
        from allaganeye.commands.split_matches import _read_cached_capture_regions

        cache_path = tmp_path / ".detection_cache.json"
        self._write_cache(cache_path, cache_video)
        regions = _read_cached_capture_regions(cache_path)
        assert regions is not None
        assert regions["coarse"]["source"] == "fallback"
        assert regions["coarse"]["x"] == 0.0 and regions["coarse"]["w"] == 1.0
        assert regions["fallback_reason"] is None

    def test_read_cached_capture_regions_legacy_vtuber_returns_none(
        self, cache_video, tmp_path
    ):
        # pre-#810 vtuber cache は band 領域が未知 -> 合成せず None (field 省略)
        from allaganeye.commands.split_matches import _read_cached_capture_regions

        cache_path = tmp_path / ".detection_cache.json"
        self._write_cache(cache_path, cache_video, params_extra={"vtuber": True})
        assert _read_cached_capture_regions(cache_path) is None

    def test_read_cached_capture_regions_legacy_masked_returns_none(
        self, cache_video, tmp_path
    ):
        from allaganeye.commands.split_matches import _read_cached_capture_regions

        cache_path = tmp_path / ".detection_cache.json"
        self._write_cache(cache_path, cache_video, extra={"masked_fallback_used": True})
        assert _read_cached_capture_regions(cache_path) is None

    def test_read_cached_capture_regions_unreadable_returns_none(self, tmp_path):
        from allaganeye.commands.split_matches import _read_cached_capture_regions

        assert _read_cached_capture_regions(tmp_path / "missing.json") is None
```

(fixture 名 `cache_video` / `SplitConfig` import は既存 cache テスト class の実装に合わせて調整)

`tests/test_detect.py` — run_detect の書き込みテスト (file 冒頭の `PROBE_RESULT` /
`BOUNDARIES` / `MODULE_DETECT` 定数と `test_detect_uses_cache_when_present` の
patch 構成を踏襲):

```python
def test_detect_writes_capture_regions_fresh(tmp_path):
    """#810 -- fresh detection: region_callback 経由で capture_regions を書く。"""
    from allaganeye.video.capture_region import FULL_FRAME, RegionTimeline

    def fake_run_detection(*args, **kwargs):
        cb = kwargs.get("region_callback")
        assert cb is not None, (
            "run_detect must pass region_callback to _run_detection (#810)"
        )
        cb(RegionTimeline(coarse=FULL_FRAME))
        return BOUNDARIES

    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    with (
        patch(f"{MODULE_DETECT}.probe_video", return_value=PROBE_RESULT),
        patch(f"{MODULE_DETECT}._run_detection", side_effect=fake_run_detection),
    ):
        run_detect(Path("input.mp4"), config, quiet=True)

    payload = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    regions = payload["capture_regions"]
    assert regions["coarse"]["source"] == "fallback"
    assert regions["coarse"]["x"] == 0.0 and regions["coarse"]["w"] == 1.0
    assert regions["segments"] == []
    assert regions["fallback_reason"] is None


def test_detect_cache_hit_carries_capture_regions(tmp_path):
    """#810 -- cache-hit: cache 記録値が metadata.json へ引き継がれる。

    `_load_cache` を patch して hit させつつ、cache file 実体に capture_regions
    を書いておく (`_read_cached_capture_regions` は file を直接読むため patch 不要)。
    """
    band_regions = {
        "coarse": {
            "x": 0.1,
            "y": 0.0,
            "w": 0.76,
            "h": 0.042,
            "confidence": 0.9,
            "source": "band",
        },
        "segments": [],
        "fallback_reason": None,
    }
    cache_path = tmp_path / ".detection_cache.json"
    cache_path.write_text(
        json.dumps({"capture_regions": band_regions}), encoding="utf-8"
    )
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    with (
        patch(f"{MODULE_DETECT}.probe_video", return_value=PROBE_RESULT),
        patch(f"{MODULE_DETECT}._load_cache", return_value=BOUNDARIES),
        patch(f"{MODULE_DETECT}._run_detection") as mock_detect,
    ):
        run_detect(Path("input.mp4"), config, quiet=True)

    mock_detect.assert_not_called()
    payload = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    assert payload["capture_regions"] == band_regions
```

`tests/test_split_matches.py` — run_split の一気通貫 wiring テスト
(`test_run_split_writes_brightness_samples_when_callback_fires` (#644、:4740-4785) と
同じ decorator / fixture 構成。`# -- #644 brightness_samples wiring --` セクションの隣に
`# -- #810 capture_regions wiring --` セクションを作って追加):

```python
@patch(f"{MODULE}._run_detection")
@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.probe_video")
def test_run_split_writes_capture_regions_when_callback_fires(
    mock_probe, mock_split, mock_run_detection, tmp_path
):
    """#810 -- run_split (一気通貫) で region_callback が発火したら
    capture_regions が metadata.json に書かれること。"""
    from allaganeye.video.capture_region import FULL_FRAME, RegionTimeline

    mock_probe.return_value = PROBE_RESULT

    def fake_run_detection(*args, **kwargs):
        cb = kwargs.get("region_callback")
        assert cb is not None, (
            "run_split must pass region_callback to _run_detection (#810)"
        )
        cb(RegionTimeline(coarse=FULL_FRAME))
        return BOUNDARIES

    mock_run_detection.side_effect = fake_run_detection

    output_dir = tmp_path / "out"
    mock_split.return_value = [
        output_dir / "match_001.mp4",
        output_dir / "match_002.mp4",
    ]
    video = tmp_path / "input.mp4"
    video.write_bytes(b"")
    config = SplitConfig(output_dir=output_dir, min_match_duration=60.0)

    run_split(video, config, verbose=False, quiet=True)

    payload = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))
    assert payload["capture_regions"]["coarse"]["source"] == "fallback"
    assert payload["capture_regions"]["fallback_reason"] is None


@patch(f"{MODULE}._run_detection")
@patch(f"{MODULE}.split_video")
@patch(f"{MODULE}.probe_video")
def test_run_split_omits_capture_regions_when_callback_silent(
    mock_probe, mock_split, mock_run_detection, tmp_path
):
    """#810 -- callback が発火しない run では field を書かない
    (brightness_samples #644 と同型の防御契約)。"""
    mock_probe.return_value = PROBE_RESULT
    mock_run_detection.side_effect = lambda *a, **kw: BOUNDARIES

    output_dir = tmp_path / "out2"
    mock_split.return_value = [
        output_dir / "match_001.mp4",
        output_dir / "match_002.mp4",
    ]
    video = tmp_path / "input.mp4"
    video.write_bytes(b"")
    config = SplitConfig(output_dir=output_dir, min_match_duration=60.0)

    run_split(video, config, verbose=False, quiet=True)

    payload = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))
    assert "capture_regions" not in payload
```

- [ ] **Step 2: red 確認**

Run: `cd E:\projects\kobutachan-tools\kobutachan-allaganeye\.claude\worktrees\810-capture-regions && python -m pytest tests/test_metadata_types.py tests/test_split_matches.py::TestCaptureRegionsCache tests/test_detect.py -v -k "capture_regions"`
Expected: FAIL (`capture_regions` unexpected keyword / `_read_cached_capture_regions` ImportError)

- [ ] **Step 3: split_matches.py を実装**

(a) import 追加 (ファイル冒頭の既存 import 群):

```python
from allaganeye.metadata_types import CaptureRegions
from allaganeye.video.capture_region import FULL_FRAME, RegionTimeline
```

(b) `_build_metadata_payload` — シグネチャに `capture_regions: CaptureRegions | None = None` を
追加 (`brightness_samples` の後)、docstring に 1 段落追加、本体の payload dict 構築後
(`brightness_samples` の既存 skip 処理と同じ位置) に:

```python
    # #810 -- capture region timeline。None (pre-#810 cache hit で領域未知の
    # 経路 / callback 未発火) では key 自体を省略する (brightness_samples と同型)。
    if capture_regions is not None:
        payload["capture_regions"] = capture_regions
```

(c) `_split_and_write_metadata` — シグネチャに `capture_regions: CaptureRegions | None = None`
を追加し、`_build_metadata_payload` 呼び出しへ pass-through。

(d) `_save_cache` — シグネチャに `capture_regions: dict | None = None` を追加、
`cache_data` の `"masked_fallback_used"` の直後:

```python
        # #810: 解決済み capture region timeline (to_dict 形式)。key (params) では
        # なく top-level (masked_fallback_used と同型): 出力 provenance であり
        # cache 一致判定には関与しない。
        "capture_regions": capture_regions,
```

(e) `_read_cached_masked_fallback` の直後に新 helper:

```python
def _read_cached_capture_regions(cache_path: Path) -> dict | None:
    """cache-hit 経路用: cache に記録された capture region timeline を読む (#810)。

    pre-#810 legacy cache (field なし / None) は、cache 記録の params.vtuber ==
    False かつ masked_fallback_used == False なら標準 path 確定 (領域は決定的に
    FULL_FRAME) なので合成して返す。vtuber / masked の legacy cache は領域が
    未知のため None (metadata では field 省略 = 領域不明を偽装しない)。
    cache が読めないときも None。`_load_cache` の hit 判定とは独立に読む
    (`_read_cached_masked_fallback` と同型)。
    """
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    cached = data.get("capture_regions")
    if isinstance(cached, dict):
        return cached
    params = data.get("params", {})
    if not params.get("vtuber", False) and not data.get("masked_fallback_used", False):
        return RegionTimeline(coarse=FULL_FRAME).to_dict()
    return None
```

(f) `_run_detection` — シグネチャに
`region_callback: Callable[[RegionTimeline], None] | None = None` を追加し、
`detect_kwargs` に `"region_callback": region_callback,` を追加
(`masked_fallback_callback` の直後)。

(g) `run_split` — 検出 callback 群 (:218-228) の隣に捕捉を追加:

```python
# #810 -- 最終的に有効だった capture region を捕捉して cache / metadata へ。
captured_region: dict | None = None


def _on_region(timeline: RegionTimeline) -> None:
    nonlocal captured_region
    captured_region = timeline.to_dict()
```

`_run_detection(...)` 呼び出し (:230-242) に `region_callback=_on_region,` を追加。
`_save_cache(...)` (:272-280) に `capture_regions=captured_region,` を追加。
fresh `_split_and_write_metadata(...)` (:309-325) に
`capture_regions=cast("CaptureRegions | None", captured_region),` を追加。
cache-hit `_split_and_write_metadata(...)` (:156-169) に
`capture_regions=cast("CaptureRegions | None", _read_cached_capture_regions(cache_path)),`
を追加 (`masked_fallback_used=_read_cached_masked_fallback(...)` の隣)。

(h) verbose helper — `_display_cache_hit_params` 付近に追加し、両 verbose 経路から呼ぶ:

```python
def _format_region_token(regions: dict | None) -> str:
    """capture region の verbose 1 行表示 (#810)。縮退を silent にしない。"""
    if not isinstance(regions, dict):
        return "unknown"
    coarse = regions.get("coarse")
    if not isinstance(coarse, dict):
        return "unknown"
    source = coarse.get("source", "?")
    if source == "fallback":
        token = "full_frame"
    else:
        token = (
            f"{source}({coarse.get('x', 0):.2f},{coarse.get('y', 0):.2f},"
            f"{coarse.get('w', 0):.2f},{coarse.get('h', 0):.2f})"
        )
    reason = regions.get("fallback_reason")
    return f"{token}, fallback={reason}" if reason else token
```

- `run_split` の `_print_detection_stats(detect_stats)` 直後 (:260):

```python
        if captured_region is not None:
            typer.echo(f"  Region: {_format_region_token(captured_region)}")
```

- `_display_cache_hit_params` — `masked_fallback` 表示行の並びに
  `f"region={_format_region_token(data.get('capture_regions'))}"` token を追加
  (既存の cached_fallback token と同じ echo 文字列内)。

- [ ] **Step 4: detect.py を実装**

- import (:23-46) に `_read_cached_capture_regions` / `_format_region_token` を追加
- `from allaganeye.video.capture_region import RegionTimeline` と
  `from allaganeye.metadata_types import CaptureRegions`、`from typing import cast` を追加
  (既存 import 構成に合わせる)
- cache-hit 分岐 (:140 `masked_fallback_used = _read_cached_masked_fallback(cache_path)` の隣):

```python
            captured_region = _read_cached_capture_regions(cache_path)
```

- fresh 分岐: `captured_region: dict | None = None` を `masked_fallback_used = False` (:133) の
  隣で初期化し、`_on_masked_fallback` の隣に:

```python
        def _on_region(timeline: RegionTimeline) -> None:
            nonlocal captured_region
            captured_region = timeline.to_dict()
```

- `_run_detection(...)` (:191-204) に `region_callback=_on_region,` を追加
- `_save_cache(...)` (:226-234) に `capture_regions=captured_region,` を追加
- verbose: `_print_detection_stats(detect_stats)` (:221) 直後に run_split と同じ Region 行
- `_build_metadata_payload(...)` (:290-312) に
  `capture_regions=cast("CaptureRegions | None", captured_region),` を追加

- [ ] **Step 5: green 確認 + commit**

Run: `cd E:\projects\kobutachan-tools\kobutachan-allaganeye\.claude\worktrees\810-capture-regions && python -m pytest tests/test_metadata_types.py tests/test_split_matches.py tests/test_detect.py -q && ruff check . && ruff format --check . && pyright`
Expected: 全 PASS

```bash
cd E:\projects\kobutachan-tools\kobutachan-allaganeye\.claude\worktrees\810-capture-regions
git add allaganeye/commands/split_matches.py allaganeye/commands/detect.py tests/test_split_matches.py tests/test_detect.py tests/test_metadata_types.py
git commit -m "feat(commands): capture_regions を cache / metadata.json に配線 (Refs #810)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: `split --from-metadata` preserve

**Files:**

- Modify: `allaganeye/commands/split_matches.py` — `run_split_from_metadata` (:439-514)
- Test: `tests/test_split_from_metadata.py`

**Interfaces:**

- Consumes: Task 4 の `_split_and_write_metadata(..., capture_regions=...)`
- Produces: from-metadata round-trip で `capture_regions` が保全される契約

- [ ] **Step 1: failing test を書く**

`tests/test_split_from_metadata.py` の
`test_run_split_from_metadata_preserves_brightness_samples` (#644、:398-434) の隣に追加。
file 既存の `_sample_metadata()` / `_write_metadata()` helper と `PROBE_RESULT` /
`MODULE` 定数をそのまま使う:

```python
# -- #810 capture_regions preserve through --from-metadata --


def test_run_split_from_metadata_preserves_capture_regions(tmp_path):
    """#810 -- --from-metadata 経路で元 metadata.json の capture_regions
    がそのまま新 metadata に引き継がれる (brightness_samples #644 同パターン)。"""
    source = tmp_path / "input.mp4"
    source.write_bytes(b"")

    regions = {
        "coarse": {
            "x": 0.1,
            "y": 0.0,
            "w": 0.76,
            "h": 0.042,
            "confidence": 0.9,
            "source": "band",
        },
        "segments": [],
        "fallback_reason": None,
    }
    payload = _sample_metadata(str(source))
    payload["capture_regions"] = regions
    meta_path = _write_metadata(tmp_path, payload)
    out_dir = tmp_path / "out"
    config = SplitConfig(output_dir=out_dir, min_match_duration=60.0)

    with (
        patch(f"{MODULE}.probe_video", return_value=PROBE_RESULT),
        patch(
            f"{MODULE}.split_video",
            return_value=[out_dir / "match_001.mp4", out_dir / "match_002.mp4"],
        ),
    ):
        run_split_from_metadata(meta_path, config, quiet=True)

    fresh = json.loads((out_dir / "metadata.json").read_text(encoding="utf-8"))
    assert fresh["capture_regions"] == regions


def test_run_split_from_metadata_omits_capture_regions_when_source_lacks(tmp_path):
    """#810 -- pre-#810 metadata (field なし) からは新 metadata でも欠落
    (合成しない。領域不明を偽装しない)。"""
    source = tmp_path / "input.mp4"
    source.write_bytes(b"")

    payload = _sample_metadata(str(source))
    assert "capture_regions" not in payload
    meta_path = _write_metadata(tmp_path, payload)
    out_dir = tmp_path / "out"
    config = SplitConfig(output_dir=out_dir, min_match_duration=60.0)

    with (
        patch(f"{MODULE}.probe_video", return_value=PROBE_RESULT),
        patch(
            f"{MODULE}.split_video",
            return_value=[out_dir / "match_001.mp4", out_dir / "match_002.mp4"],
        ),
    ):
        run_split_from_metadata(meta_path, config, quiet=True)

    fresh = json.loads((out_dir / "metadata.json").read_text(encoding="utf-8"))
    assert "capture_regions" not in fresh
```

- [ ] **Step 2: red 確認**

Run: `cd E:\projects\kobutachan-tools\kobutachan-allaganeye\.claude\worktrees\810-capture-regions && python -m pytest tests/test_split_from_metadata.py -v -k capture_regions`
Expected: preserve テスト FAIL (未実装で field が落ちる)。omits テストは現状でも PASS しうる (防御 pin として追加)

- [ ] **Step 3: preserve を実装**

`run_split_from_metadata` — `preserve_warnings = sanitize_warnings(...)` (:462) の直後:

```python
    # #810 -- preserve capture_regions across `--from-metadata`. 本ランは再検知
    # しないため元 metadata の領域記録を引き継ぐ (#644 brightness_samples と
    # 同じ preserve パターン。深い schema 検証は writer が行わない点も同前例)。
    old_capture_regions = payload.get("capture_regions")
    preserve_capture_regions: CaptureRegions | None = (
        cast("CaptureRegions", old_capture_regions)
        if isinstance(old_capture_regions, dict)
        else None
    )
```

`_split_and_write_metadata(...)` (:494-514) に `capture_regions=preserve_capture_regions,` を追加。

- [ ] **Step 4: green 確認 + commit**

Run: `cd E:\projects\kobutachan-tools\kobutachan-allaganeye\.claude\worktrees\810-capture-regions && python -m pytest tests/test_split_from_metadata.py tests/test_split_matches.py -q && ruff check . && ruff format --check . && pyright`
Expected: 全 PASS

```bash
cd E:\projects\kobutachan-tools\kobutachan-allaganeye\.claude\worktrees\810-capture-regions
git add allaganeye/commands/split_matches.py tests/test_split_from_metadata.py
git commit -m "feat(commands): split --from-metadata で capture_regions を preserve (Refs #810)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Docs 更新

**Files:**

- Modify: `docs/metadata-spec.md` (スキーマ定義 §、`brightness_samples` § の後に新 §)
- Modify: `CLAUDE.md` (モジュール構成表 `video/capture_region.py` 行)
- 確認のみ: `docs/output-spec.md` / `docs/detection-map.md` (変更不要なら PR 本文に根拠記載)

**Interfaces:**

- Consumes: Task 1-5 で確定した実装挙動 (書き込みパス表の正確性)
- Produces: 受け入れ条件 3「`docs/output-spec.md` 等を更新」の充足

- [ ] **Step 1: metadata-spec.md ルート表に行を追加**

`docs/metadata-spec.md:71` (`brightness_samples` 行) の直後:

```markdown
| `capture_regions` | object | 新規検知では ✓ / cache-hit は記録があれば ✓ / 読み込み時は欠落許容 (#810) | 検出が解決した capture region timeline (coarse + segments + 縮退 provenance) | 後述 §capture_regions 参照 |
```

- [ ] **Step 2: 新 § を `brightness_samples` § の後 (`Gap` § の前) に追加**

```markdown
### `capture_regions` オブジェクト (#810)

検出が解決した game capture 領域 (`allaganeye/video/capture_region.py::RegionTimeline` の
serialize 形)。consumer (Pass 1 wiring #809 / scorebar ROI #480 / minimap #481 / GUI) が
一貫参照する共有スキーマ。矩形は解像度非依存の正規化座標 `[0,1]`。

| フィールド | 型 | 必須 | 意味 |
| --- | --- | --- | --- |
| `coarse` | CaptureRegion | ✓ | **その run の Pass 1 輝度計測に実際に使われた領域**。標準 OBS = FULL_FRAME (`{0,0,1,1}`, source=`"fallback"`) / `--vtuber` = scorebar 帯 ROI (source=`"band"`、**game 全矩形ではない**) / masked fallback 採用 run = mask-free game 矩形 (source=`"tierA"`) |
| `segments` | array of RegionSegment | ✓ | Tier B per-segment 精密領域 (`{"time_range": [t0, t1], "region": CaptureRegion}`)。**現状は常に `[]`** (#480 P4 が埋める) |
| `fallback_reason` | string \| null | ✓ (nullable) | band anchor 縮退の provenance。`"anchor_error"` (Stage 0 例外) / `"consensus_miss"` (consensus 不成立) / `null` (縮退なし)。free string: 読み手は unknown 値を受容 |

CaptureRegion は `{x, y, w, h, confidence: number [0,1], source: string}`。`source` の文書化値:
`"fallback"` (FULL_FRAME) / `"band"` (scorebar 帯 ROI) / `"tierA"` (game 矩形) / `"tierB"`
(将来 precise)。free string のため読み手は unknown 値を受容すること。

masked の縮退 (mask 不発見で標準 path に defer) は本フィールドではなく既存の
`detection_params.masked` / `masked_fallback_used` フラグ対から導出する
(`masked=true` かつ `masked_fallback_used=false`)。

**書き込みパス別の挙動**:

| 経路 | 書き込み |
| --- | --- |
| `allaganeye detect` / `allaganeye split` (新規検知) | ✓ 常に書く (OBS は coarse=FULL_FRAME) |
| cache hit | cache 記録があれば ✓ / pre-#810 cache は標準 path 確定 (vtuber=false かつ masked_fallback_used=false) なら FULL_FRAME を合成、vtuber / masked なら ✗ 欠落 (領域不明を偽装しない) |
| `allaganeye split --from-metadata` | 元 metadata から **preserve** (元が欠落なら欠落) |

cache には `.detection_cache.json` top-level (`masked_fallback_used` と同型、cache key 非対象)
で保存される。GUI は読み取り時 zod `CaptureRegionsSchema` (optional) で検証し、`[適用]`
(`normalizeForPersistence`) でも保持する (GUI 側 consumer は未実装、round-trip のみ)。
```

- [ ] **Step 3: CLAUDE.md モジュール表を更新**

`video/capture_region.py` 行の責務説明末尾に追記:

```text
解決結果は metadata.json `capture_regions` に永続化 (#810、RegionTimeline serialize 形 + 縮退 provenance)
```

- [ ] **Step 4: output-spec.md / detection-map.md を確認**

- `docs/output-spec.md`: metadata.json の field 列挙は持たない (grep `metadata.json` で確認済み、
  §マトリクス v2 は CLI オプション組合せ仕様)。verbose 出力に Region 行が増えるが
  output-spec は verbose の行単位仕様を規定していないため変更不要の見込み。
  §保守ルールを読み、該当なしなら PR 本文に「確認の上変更不要 (根拠)」を逐条記載
- `docs/detection-map.md`: 検出 subsystem の状態 map であり metadata schema は範囲外。
  変更不要の見込み (同様に PR 本文へ根拠記載)

- [ ] **Step 5: lint + commit**

Run: `cd E:\projects\kobutachan-tools\kobutachan-allaganeye\.claude\worktrees\810-capture-regions && bash scripts/check-markdownlint.sh`
Expected: `Summary: 0 error(s)`

```bash
cd E:\projects\kobutachan-tools\kobutachan-allaganeye\.claude\worktrees\810-capture-regions
git add docs/metadata-spec.md CLAUDE.md
git commit -m "doc(metadata): capture_regions field の仕様を追加 (Refs #810)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: 全体検証 (final gate)

**Files:** なし (検証のみ。修正が出たら該当 Task の流儀で修正 + commit)

- [ ] **Step 1: Python 全チェック**

Run: `cd E:\projects\kobutachan-tools\kobutachan-allaganeye\.claude\worktrees\810-capture-regions && ruff check . && ruff format --check . && pyright && python -m pytest -q`
Expected: 全 PASS (slow マーカーは除外される)

- [ ] **Step 2: codegen drift ゼロ確認**

Run: `cd E:\projects\kobutachan-tools\kobutachan-allaganeye\.claude\worktrees\810-capture-regions && python scripts/codegen/generate.py && git diff --exit-code allaganeye/metadata_types.py gui/src/types/metadata.generated.ts`
Expected: exit 0 (差分なし)

- [ ] **Step 3: GUI 全チェック**

Run: `cd E:\projects\kobutachan-tools\kobutachan-allaganeye\.claude\worktrees\810-capture-regions\gui && npm run lint && npm run typecheck && npm test -- --run && npm run build`
Expected: 全 PASS

- [ ] **Step 4: cargo check (GUI 変更を含む PR のため Iron Law 6 の全 job)**

Run: `cd E:\projects\kobutachan-tools\kobutachan-allaganeye\.claude\worktrees\810-capture-regions\gui\src-tauri && cargo check`
Expected: PASS (Rust は未変更だが Iron Law 6 の path 別チェックに従い実行)

- [ ] **Step 5: markdownlint**

Run: `cd E:\projects\kobutachan-tools\kobutachan-allaganeye\.claude\worktrees\810-capture-regions && bash scripts/check-markdownlint.sh`
Expected: `Summary: 0 error(s)`

- [ ] **Step 6: OBS baseline (実機、controller が判断)**

detector.py を touch したため (観測 seam のみだが)、実動画 baseline で boundaries 不変 +
metadata diff が `capture_regions` 追加のみであることを確認する。
`docs/testing-guide.md` §「baseline drift の判定」の手順に従う。timestamp churn
(detected_at 等) は非意味的 diff として grep 除外で判定 (memory 教訓)。
実行可否・タイミングは controller が Idios に AskUserQuestion で確認する
(Iron Law 6 実機検証 trigger: `video/detector.py` 変更)。

---

## PR 段階 (plan 外、controller が実施)

1. Pre-flight Step 0-5 (`docs/l2-workflow.md`): Step 0 `gh pr list --search "810" --state open` →
   Step 1-3 base 同期 / 取り込み未済 commit / touched files 交差 → Step 4 並行 PR 再確認 →
   Step 5 codex adversarial-review (tier 1 = `codex-companion.mjs adversarial-review`、
   focus: cache key/provenance 整合・schema 3 層 (JSON Schema/zod/TypedDict) 同期・
   `_detect_masked_fallback` tuple 変更の全呼出サイト・region_callback の 1 回発火保証)
2. PR 作成 (base = `develop-0.3.0`、`Refs #810`、Closes 禁止、Self-Test Report は
   machine-verified `[x]` / unverifiable `-` 書き分け、実機 baseline は AskUserQuestion)
3. `/iterate-review` で review-fix ループ
4. Rust `validate_metadata_for_write` の optional-field 検証硬化 (brightness_samples /
   system_info / capture_regions 共通の既存クラス) の**別 issue 起票文面**を Idios に提示
   (spec §7 決定。AskUserQuestion で文面承認後に `gh issue create`)
5. merge 承認 + Session H (minimap #481) 起動可否は STOP して Idios に確認
