"""Tests for export encoder selection (#761).

Mirrors gui/src-tauri/src/lib.rs::tests::select_h264_encoder_* coverage
(those tests are removed in a later task as the logic moves to Python).
"""

from __future__ import annotations

import pytest

from allaganeye.export.encoder import (
    EncoderSlot,
    H264Encoder,
    select_h264_encoder,
)


def test_h264_encoder_ffmpeg_codec_name():
    assert H264Encoder.LIBX264.value == "libx264"
    assert H264Encoder.NVENC.value == "h264_nvenc"
    assert H264Encoder.QSV.value == "h264_qsv"
    assert H264Encoder.AMF.value == "h264_amf"


def test_h264_encoder_display_label():
    assert H264Encoder.NVENC.display_label == "NVENC"
    assert H264Encoder.LIBX264.display_label == "libx264 (CPU)"


def test_h264_encoder_quality_args_nvenc():
    """quality args mirror gui/src-tauri/src/lib.rs:1628-1630 (#591 baseline)."""
    args = H264Encoder.NVENC.quality_args()
    assert args == ("-rc", "vbr", "-cq", "19", "-preset", "p5")


def test_h264_encoder_quality_args_libx264():
    args = H264Encoder.LIBX264.quality_args()
    assert args == ("-crf", "18", "-preset", "medium")


def test_h264_encoder_quality_args_qsv():
    args = H264Encoder.QSV.quality_args()
    assert args == ("-global_quality", "20", "-look_ahead", "1", "-preset", "medium")


def test_h264_encoder_quality_args_amf():
    args = H264Encoder.AMF.quality_args()
    assert args == ("-quality", "quality", "-rc", "cqp", "-qp_i", "19", "-qp_p", "21")


# --- select_h264_encoder ---


def test_select_first_pref_match():
    assert (
        select_h264_encoder(
            vendors=["nvidia", "amd"], preference=["nvidia", "amd", "intel"]
        )
        == H264Encoder.NVENC
    )


def test_select_skips_unavailable_first_pref():
    assert (
        select_h264_encoder(vendors=["amd"], preference=["nvidia", "amd", "intel"])
        == H264Encoder.AMF
    )


def test_select_intel_qsv():
    assert (
        select_h264_encoder(vendors=["intel"], preference=["nvidia", "amd", "intel"])
        == H264Encoder.QSV
    )


def test_select_libx264_fallback_when_no_vendor_match():
    assert (
        select_h264_encoder(vendors=[], preference=["nvidia", "amd", "intel"])
        == H264Encoder.LIBX264
    )


def test_select_libx264_fallback_when_pref_empty():
    assert select_h264_encoder(vendors=["nvidia"], preference=[]) == H264Encoder.LIBX264


def test_select_libx264_fallback_unknown_vendor():
    """Unknown vendor strings (typos, future entries) ignored — libx264 fallback."""
    assert (
        select_h264_encoder(vendors=["mali"], preference=["mali", "nvidia"])
        == H264Encoder.LIBX264
    )


# --- EncoderSlot ---


def test_encoder_slot_is_frozen_dataclass():
    slot = EncoderSlot(
        slot_index=0, encoder_kind=H264Encoder.NVENC, display_label="NVENC #1"
    )
    with pytest.raises(AttributeError):
        slot.slot_index = 1  # type: ignore[misc]
