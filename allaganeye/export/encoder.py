"""H.264 encoder selection logic (#761).

Ported from gui/src-tauri/src/lib.rs:1597-1678 (H264Encoder + select_h264_encoder)
so CLI and GUI share a single source of truth. See spec §4.1.

NOTE: enumerate_h264_encoders depends on probe_nvenc_engine_count which lives
in nvenc_probe.py — that import is added in Task 4.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class H264Encoder(Enum):
    """H.264 encoder identifiers.

    The ``value`` is the literal ``-c:v`` argument passed to ffmpeg.
    """

    LIBX264 = "libx264"
    NVENC = "h264_nvenc"
    QSV = "h264_qsv"
    AMF = "h264_amf"

    @property
    def display_label(self) -> str:
        return _DISPLAY_LABELS[self]

    def quality_args(self) -> tuple[str, ...]:
        """Vendor-specific quality / preset args.

        Ported from gui/src-tauri/src/lib.rs:1621-1642 (#591 baseline).
        Targets visual parity with libx264 CRF 18; RD curves differ per
        encoder so the mapping is approximate.
        """
        return _QUALITY_ARGS[self]


_DISPLAY_LABELS: dict[H264Encoder, str] = {
    H264Encoder.LIBX264: "libx264 (CPU)",
    H264Encoder.NVENC: "NVENC",
    H264Encoder.QSV: "QSV",
    H264Encoder.AMF: "AMF",
}

_QUALITY_ARGS: dict[H264Encoder, tuple[str, ...]] = {
    H264Encoder.LIBX264: ("-crf", "18", "-preset", "medium"),
    H264Encoder.NVENC: ("-rc", "vbr", "-cq", "19", "-preset", "p5"),
    H264Encoder.QSV: ("-global_quality", "20", "-look_ahead", "1", "-preset", "medium"),
    H264Encoder.AMF: (
        "-quality",
        "quality",
        "-rc",
        "cqp",
        "-qp_i",
        "19",
        "-qp_p",
        "21",
    ),
}


@dataclass(frozen=True)
class EncoderSlot:
    """One parallel worker's encoder assignment.

    Phase 1 (#761): all NVENC slots are identical (just differ by ``slot_index``).
    Phase 2 (#762): slots may be mixed vendor (Nvenc#0, Nvenc#1, Amf#0).
    """

    slot_index: int
    encoder_kind: H264Encoder
    display_label: str


def select_h264_encoder(vendors: list[str], preference: list[str]) -> H264Encoder:
    """First vendor preference present in ``vendors`` → its encoder; libx264 fallback.

    Equivalent to gui/src-tauri/src/lib.rs:1666-1678. Unknown vendor strings
    in ``preference`` are skipped.
    """
    for pref in preference:
        if pref in vendors:
            match pref:
                case "nvidia":
                    return H264Encoder.NVENC
                case "intel":
                    return H264Encoder.QSV
                case "amd":
                    return H264Encoder.AMF
                case _:
                    continue
    return H264Encoder.LIBX264


def enumerate_h264_encoders(
    vendors: list[str],
    preference: list[str],
    gpu_models: list[str],
) -> list[EncoderSlot]:
    """Vendor + GPU 検出結果から並列実行可能な encoder slot 列を作る。

    Phase 1 (#761): NVENC 選択時のみ N slots、他は 1 slot。
    Phase 2 (#762): mixed vendor slot 列 ``[Nvenc#0, Nvenc#1, Amf#0]`` を返す
    よう拡張可能 (本実装は単一 vendor のみ)。
    """
    # 局所 import で循環依存を避ける (nvenc_probe → encoder の参照は ないが念のため)
    from allaganeye.export.nvenc_probe import probe_nvenc_engine_count

    primary = select_h264_encoder(vendors, preference)
    if primary == H264Encoder.NVENC:
        n = probe_nvenc_engine_count(gpu_models)
        return [
            EncoderSlot(
                slot_index=i,
                encoder_kind=H264Encoder.NVENC,
                display_label=f"NVENC #{i + 1}",
            )
            for i in range(n)
        ]
    return [
        EncoderSlot(
            slot_index=0,
            encoder_kind=primary,
            display_label=primary.display_label,
        )
    ]
