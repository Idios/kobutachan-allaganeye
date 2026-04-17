"""Unit tests for allaganeye.audio.scan -- mocked pipeline (#288)."""

from pathlib import Path
from unittest.mock import patch

import numpy as np

from allaganeye.audio.features import LogMelConfig
from allaganeye.audio.scan import scan_fanfare_hits


_SCAN_MODULE = "allaganeye.audio.scan"


def _fake_features() -> tuple[list[np.ndarray], LogMelConfig, dict]:
    """Small reference features compatible with LogMelConfig defaults.

    Returns a list (as load_features_multi does) with a single ref, which
    exercises the common fanfare single-ref code path.
    """
    config = LogMelConfig()
    features = np.ones((config.n_mels, 10), dtype=np.float32)
    return [features], config, {}


@patch(f"{_SCAN_MODULE}.find_match_peaks")
@patch(f"{_SCAN_MODULE}.sliding_cosine_similarity")
@patch(f"{_SCAN_MODULE}.log_mel_spectrogram")
@patch(f"{_SCAN_MODULE}.extract_pcm")
@patch(f"{_SCAN_MODULE}.load_features_multi")
@patch(f"{_SCAN_MODULE}.get_reference_path")
def test_scan_fanfare_hits_wires_pipeline(
    mock_ref_path,
    mock_load,
    mock_extract,
    mock_logmel,
    mock_corr,
    mock_peaks,
):
    """The four audio primitives are invoked in order and their output returned."""
    mock_ref_path.return_value = Path("/fake/fanfare.npz")
    mock_load.return_value = _fake_features()
    mock_extract.return_value = np.zeros(22050, dtype=np.float32)
    mock_logmel.return_value = np.zeros((80, 100), dtype=np.float32)
    mock_corr.return_value = np.zeros(91, dtype=np.float32)
    expected = [{"timestamp": 50.0, "similarity": 0.72}]
    mock_peaks.return_value = expected

    result = scan_fanfare_hits(Path("/fake/video.mkv"))

    assert result == expected
    mock_ref_path.assert_called_once_with("fanfare")
    mock_load.assert_called_once()
    mock_extract.assert_called_once()
    mock_logmel.assert_called_once()
    mock_corr.assert_called_once()
    mock_peaks.assert_called_once()


@patch(f"{_SCAN_MODULE}.find_match_peaks")
@patch(f"{_SCAN_MODULE}.sliding_cosine_similarity")
@patch(f"{_SCAN_MODULE}.log_mel_spectrogram")
@patch(f"{_SCAN_MODULE}.extract_pcm")
@patch(f"{_SCAN_MODULE}.load_features_multi")
@patch(f"{_SCAN_MODULE}.get_reference_path")
def test_scan_fanfare_hits_forwards_threshold(
    mock_ref_path,
    mock_load,
    mock_extract,
    mock_logmel,
    mock_corr,
    mock_peaks,
):
    """Threshold and min_gap_seconds are forwarded to find_match_peaks."""
    mock_ref_path.return_value = Path("/fake/fanfare.npz")
    features_list, config, _ = _fake_features()
    mock_load.return_value = (features_list, config, {})
    mock_extract.return_value = np.zeros(22050, dtype=np.float32)
    mock_logmel.return_value = np.zeros((80, 100), dtype=np.float32)
    mock_corr.return_value = np.zeros(91, dtype=np.float32)
    mock_peaks.return_value = []

    scan_fanfare_hits(Path("/fake/v.mkv"), threshold=0.8, min_gap_seconds=45.0)

    kwargs = mock_peaks.call_args.kwargs
    assert kwargs["threshold"] == 0.8
    assert kwargs["min_gap_seconds"] == 45.0
    assert kwargs["frames_per_second"] == config.frames_per_second


@patch(f"{_SCAN_MODULE}.get_reference_path")
def test_scan_fanfare_hits_uses_custom_ref_name(mock_ref_path):
    """ref_name parameter is passed to get_reference_path."""
    from allaganeye.exceptions import VideoProcessingError

    mock_ref_path.side_effect = FileNotFoundError("stop early")

    try:
        scan_fanfare_hits(Path("/fake/v.mkv"), ref_name="war_room")
    except VideoProcessingError:
        pass

    mock_ref_path.assert_called_once_with("war_room")


@patch(f"{_SCAN_MODULE}.get_reference_path")
def test_scan_fanfare_hits_missing_ref_raises_video_processing_error(mock_ref_path):
    """FileNotFoundError from get_reference_path is wrapped as VideoProcessingError (#350)."""
    import pytest

    from allaganeye.exceptions import VideoProcessingError

    mock_ref_path.side_effect = FileNotFoundError("fanfare.npz not found")

    with pytest.raises(VideoProcessingError, match="fanfare reference feature missing"):
        scan_fanfare_hits(Path("/fake/v.mkv"))


@patch(f"{_SCAN_MODULE}.find_match_peaks")
@patch(f"{_SCAN_MODULE}.log_mel_spectrogram")
@patch(f"{_SCAN_MODULE}.extract_pcm")
@patch(f"{_SCAN_MODULE}.load_features_multi")
@patch(f"{_SCAN_MODULE}.get_reference_path")
def test_scan_fanfare_hits_multi_ref_takes_max(
    mock_ref_path,
    mock_load,
    mock_extract,
    mock_logmel,
    mock_peaks,
):
    """When multiple refs are bundled, the per-frame max of similarities is used.

    Exercises the War Room multi-ref OR logic introduced in #289.  We hand
    two refs where each individually matches a different offset; the
    combined curve should peak above both.
    """
    config = LogMelConfig()
    ref_a = np.ones((config.n_mels, 5), dtype=np.float32)
    ref_b = np.ones((config.n_mels, 5), dtype=np.float32)
    mock_ref_path.return_value = Path("/fake/war_room.npz")
    mock_load.return_value = ([ref_a, ref_b], config, {})
    mock_extract.return_value = np.zeros(22050, dtype=np.float32)
    # Craft a target where only different positions are "good" for each ref.
    # We control the sliding_cosine_similarity via patch below.
    target = np.ones((config.n_mels, 50), dtype=np.float32)
    mock_logmel.return_value = target
    mock_peaks.return_value = []

    sim_a = np.zeros(46, dtype=np.float32)
    sim_a[10] = 0.9  # peak at frame 10
    sim_b = np.zeros(46, dtype=np.float32)
    sim_b[30] = 0.8  # peak at frame 30

    with patch(f"{_SCAN_MODULE}.sliding_cosine_similarity", side_effect=[sim_a, sim_b]):
        scan_fanfare_hits(Path("/fake/v.mkv"), ref_name="war_room")

    # The similarity curve passed to find_match_peaks should be the
    # element-wise max of the two individual curves.
    called_sim = mock_peaks.call_args.args[0]
    assert called_sim.shape == (46,)
    assert called_sim[10] == 0.9
    assert called_sim[30] == 0.8
    # All other positions remain 0 because max(0, 0) = 0
    assert called_sim[20] == 0.0
