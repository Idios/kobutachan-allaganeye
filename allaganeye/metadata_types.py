# AUTO-GENERATED -- DO NOT EDIT.
# Regenerate with `python scripts/codegen/generate.py` (issue #612).
# Source: schemas/metadata.schema.json

from __future__ import annotations

from typing import Any, Literal, NotRequired, TypeAlias, TypedDict


class DetectionParams(TypedDict):
    """
    Parameters used by the detector when this metadata.json was produced.
    """

    sample_interval: float
    blackout_threshold: float
    min_match_duration: float
    min_blackout_duration: float
    no_audio: bool
    use_gpu: float | bool | None
    workers: float | None
    vtuber: NotRequired[bool]
    masked: NotRequired[bool]
    masked_fallback_used: NotRequired[bool]


class Match(TypedDict):
    """
    Single match segment. JSON Schema is the strict writer contract; reader-side passthrough for GUI-only edit fields (name / type_override / edited) is provided by zod (.passthrough() on MatchSchema) and only round-trips inside metadata.draft.json, never metadata.json proper.
    """

    index: int
    start_time: float
    end_time: float
    start_display: str
    end_display: str
    duration: float
    duration_display: str
    type: Literal["fl_match", "unknown"]
    output_file: NotRequired[str]
    post_match: NotRequired[bool]


class Gap(TypedDict):
    """
    Inter-match idle gap >= 5 minutes (min_gap=300.0).
    """

    start_time: float
    end_time: float
    start_display: str
    end_display: str
    duration: float
    duration_display: str


class MetadataWarning(TypedDict):
    """
    Structured warning entry (#518). Future codes should be appended to allaganeye/detection/warnings.py::WARNING_CODES; readers must accept unknown codes (forward compat).
    """

    code: str
    message_en: NotRequired[str]
    severity: NotRequired[Literal["info", "warn", "error"]]
    context: NotRequired[dict[str, Any]]


class SystemInfo(TypedDict):
    """
    GPU vendor probe snapshot recorded by detect/split (#591, extended #761). GUI export uses this to pick the H.264 encoder (NVENC / QSV / AMF / libx264) and query the NVENC parallel slot count SKU table. Optional at the root because pre-#591 metadata.json files don't carry it.
    """

    gpu_vendors_available: list[str]
    gpu_vendor_used: str | None
    vendor_preference: list[str]
    gpu: NotRequired[list[str]]


class BrightnessSamples(TypedDict):
    """
    Pre-rendered Pass 1 brightness timeline (#569). The CLI writer caps `values` to ~512 entries via downsampling so the GUI complete screen can draw the SVG without recomputing. Optional at the root: pre-#569 metadata.json and detect cache hits skip the field; CompleteScreen falls back to a sample curve when missing.
    """

    interval_s: float
    values: list[float]


class CaptureRegion(TypedDict):
    """
    Game capture rectangle in normalized [0,1] frame coordinates (#810). Serialized form of allaganeye/video/capture_region.py::CaptureRegion (to_dict / from_dict).
    """

    x: float
    y: float
    w: float
    h: float
    confidence: float
    source: str


TimeRangeItem: TypeAlias = float


class RegionSegment(TypedDict):
    """
    Per-segment precise region entry (Tier B; consumed by #480/#481). time_range is [t0, t1] in seconds.
    """

    time_range: list[TimeRangeItem]
    region: CaptureRegion


class MinimapRegionEntry(TypedDict):
    """
    #481: one per-match minimap crop entry. `match_index` references Match.index (1-based). `region` is the normalized crop rectangle used by `allaganeye minimap --region`.
    """

    match_index: int
    region: CaptureRegion


class CaptureRegions(TypedDict):
    """
    Capture-region timeline resolved by detection (#810; serialized RegionTimeline). `coarse` is the region actually used for Pass 1 brightness measurement: FULL_FRAME on standard OBS runs, the scorebar band ROI (source="band", NOT the full game rectangle) on --vtuber runs, and the mask-free game rectangle (source="tierA") when the masked fallback produced the result. `segments` is always [] until Tier B per-segment detection lands (#480). `fallback_reason` records band-anchor degradation on --vtuber runs (documented values: "anchor_error" = Stage 0 exception, "consensus_miss" = no band consensus); null = no degradation. Optional at the root: pre-#810 metadata.json doesn't carry it; cache hits from pre-#810 vtuber/masked caches omit it (region unknown).
    """

    coarse: CaptureRegion
    segments: list[RegionSegment]
    fallback_reason: str | None


class Metadata(TypedDict):
    """
    metadata.json contract between allaganeye CLI and the L2a Tauri GUI (#463). Machine-readable source of truth (#612). The human-readable counterpart lives in docs/metadata-spec.md; refine-style semantic constraints (e.g. end_time >= start_time) are enforced by zod (GUI) and InputFileError checks (CLI), not by this schema.
    """

    schema_version: NotRequired[Literal["1"]]
    source: str
    source_duration: float
    source_duration_display: str
    source_fps: NotRequired[float]
    detected_at: str
    detection_started_at: NotRequired[str]
    detection_completed_at: NotRequired[str]
    detection_params: DetectionParams
    matches: list[Match]
    gaps: list[Gap]
    warnings: NotRequired[list[MetadataWarning]]
    system_info: NotRequired[SystemInfo]
    brightness_samples: NotRequired[BrightnessSamples]
    capture_regions: NotRequired[CaptureRegions]
    minimap_regions: NotRequired[list[MinimapRegionEntry]]
