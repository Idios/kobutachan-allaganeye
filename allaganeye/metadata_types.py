# AUTO-GENERATED -- DO NOT EDIT.
# Regenerate with `python scripts/codegen/generate.py` (issue #612).
# Source: schemas/metadata.schema.json

from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict


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
    output_file: str


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
    GPU vendor probe snapshot recorded by detect/split (#591). GUI export uses this to pick the H.264 encoder (NVENC / QSV / AMF / libx264). Optional at the root because pre-#591 metadata.json files don't carry it.
    """

    gpu_vendors_available: list[str]
    gpu_vendor_used: str | None
    vendor_preference: list[str]


class BrightnessSamples(TypedDict):
    """
    Pre-rendered Pass 1 brightness timeline (#569). The CLI writer caps `values` to ~512 entries via downsampling so the GUI complete screen can draw the SVG without recomputing. Optional at the root: pre-#569 metadata.json and detect cache hits skip the field; CompleteScreen falls back to a sample curve when missing.
    """

    interval_s: float
    values: list[float]


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
    detection_params: DetectionParams
    matches: list[Match]
    gaps: list[Gap]
    warnings: NotRequired[list[MetadataWarning]]
    system_info: NotRequired[SystemInfo]
    brightness_samples: NotRequired[BrightnessSamples]
