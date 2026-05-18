"""Parallel H.264 export pipeline (#761)."""

from allaganeye.export.encoder import (
    EncoderSlot,
    H264Encoder,
    enumerate_h264_encoders,
    select_h264_encoder,
)
from allaganeye.export.ffmpeg_runner import (
    is_gpu_encoder_failure,
    run_export_attempt,
)
from allaganeye.export.nvenc_probe import probe_nvenc_engine_count
from allaganeye.export.pool import ExportMatch, export_matches
from allaganeye.export.schema import (
    ExportError,
    ExportResult,
    ExportSummary,
    ProgressEvent,
)

__all__ = [
    "EncoderSlot",
    "ExportError",
    "ExportMatch",
    "ExportResult",
    "ExportSummary",
    "H264Encoder",
    "ProgressEvent",
    "enumerate_h264_encoders",
    "export_matches",
    "is_gpu_encoder_failure",
    "probe_nvenc_engine_count",
    "run_export_attempt",
    "select_h264_encoder",
]
