"""Unit tests for allaganeye.audio.scan — mocked pipeline (#288)."""

from pathlib import Path
from unittest.mock import patch

import numpy as np

from allaganeye.audio.features import LogMelConfig
from allaganeye.audio.scan import scan_fanfare_hits


_SCAN_MODULE = "allaganeye.audio.scan"


def _fake_features() -> tuple[np.ndarray, LogMelConfig, dict]:
    """Small reference features compatible with LogMelConfig defaults."""
    config = LogMelConfig()
    features = np.ones((config.n_mels, 10), dtype=np.float32)
    return features, config, {}


@patch(f"{_SCAN_MODULE}.find_match_peaks")
@patch(f"{_SCAN_MODULE}.sliding_cosine_similarity")
@patch(f"{_SCAN_MODULE}.log_mel_spectrogram")
@patch(f"{_SCAN_MODULE}.extract_pcm")
@patch(f"{_SCAN_MODULE}.load_features")
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
@patch(f"{_SCAN_MODULE}.load_features")
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
    features, config, _ = _fake_features()
    mock_load.return_value = (features, config, {})
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
    mock_ref_path.side_effect = FileNotFoundError("stop early")

    try:
        scan_fanfare_hits(Path("/fake/v.mkv"), ref_name="war_room")
    except FileNotFoundError:
        pass

    mock_ref_path.assert_called_once_with("war_room")
