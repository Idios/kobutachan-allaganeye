"""Tests for allaganeye.audio.features module."""

import numpy as np
import pytest

from allaganeye.audio.features import (
    LogMelConfig,
    load_features,
    log_mel_spectrogram,
    mel_filterbank,
    save_features,
)


def test_logmelconfig_defaults():
    cfg = LogMelConfig()
    assert cfg.sample_rate == 22050
    assert cfg.n_fft == 2048
    assert cfg.hop == 512
    assert cfg.n_mels == 80
    assert cfg.fmin == 0.0
    assert cfg.fmax is None
    assert cfg.effective_fmax == 11025.0
    assert cfg.frames_per_second == pytest.approx(22050 / 512)


def test_logmelconfig_explicit_fmax():
    cfg = LogMelConfig(fmax=8000.0)
    assert cfg.effective_fmax == 8000.0


def test_mel_filterbank_shape():
    cfg = LogMelConfig()
    fb = mel_filterbank(cfg)
    assert fb.shape == (cfg.n_mels, cfg.n_fft // 2 + 1)
    assert fb.dtype == np.float32


def test_mel_filterbank_nonnegative():
    """All filter weights are non-negative (triangular filters)."""
    fb = mel_filterbank(LogMelConfig())
    assert np.all(fb >= 0)


def test_log_mel_spectrogram_shape():
    cfg = LogMelConfig()
    audio = np.random.RandomState(0).randn(cfg.sample_rate * 2).astype(np.float32) * 0.1
    spec = log_mel_spectrogram(audio, cfg)
    assert spec.shape[0] == cfg.n_mels
    assert spec.shape[1] > 0
    assert spec.dtype == np.float32


def test_log_mel_spectrogram_silence_gives_zero():
    """Pure silence yields zero log-mel (log1p(0) = 0)."""
    cfg = LogMelConfig()
    audio = np.zeros(cfg.sample_rate, dtype=np.float32)
    spec = log_mel_spectrogram(audio, cfg)
    assert np.all(spec == 0.0)


def test_log_mel_spectrogram_default_config():
    """Calling without explicit config uses LogMelConfig defaults."""
    audio = np.random.RandomState(1).randn(22050).astype(np.float32) * 0.1
    spec_default = log_mel_spectrogram(audio)
    spec_explicit = log_mel_spectrogram(audio, LogMelConfig())
    np.testing.assert_array_equal(spec_default, spec_explicit)


def test_save_load_features_roundtrip(tmp_path):
    """Saved features are recovered (within float16 precision) after load."""
    cfg = LogMelConfig(n_mels=40)
    rng = np.random.RandomState(2)
    features = rng.randn(40, 100).astype(np.float32)
    out = tmp_path / "test.npz"
    save_features(out, features, cfg, {"label": "test", "src": "fixture"})

    loaded, loaded_cfg, metadata = load_features(out)
    assert loaded.shape == features.shape
    assert loaded.dtype == np.float32
    np.testing.assert_allclose(loaded, features, rtol=1e-2, atol=1e-3)
    assert loaded_cfg == cfg
    assert metadata == {"label": "test", "src": "fixture"}


def test_save_features_preserves_none_fmax(tmp_path):
    """fmax=None survives the round-trip without becoming numeric."""
    cfg = LogMelConfig(fmax=None)
    out = tmp_path / "test.npz"
    save_features(out, np.zeros((cfg.n_mels, 10), dtype=np.float32), cfg)

    _, loaded_cfg, _ = load_features(out)
    assert loaded_cfg.fmax is None


def test_save_features_explicit_fmax(tmp_path):
    """Numeric fmax survives the round-trip."""
    cfg = LogMelConfig(fmax=8000.0)
    out = tmp_path / "test.npz"
    save_features(out, np.zeros((cfg.n_mels, 10), dtype=np.float32), cfg)

    _, loaded_cfg, _ = load_features(out)
    assert loaded_cfg.fmax == 8000.0


def test_save_features_rejects_shape_mismatch(tmp_path):
    """Saving features with wrong leading dimension raises ValueError."""
    cfg = LogMelConfig(n_mels=80)
    bad = np.zeros((40, 10), dtype=np.float32)
    out = tmp_path / "test.npz"
    with pytest.raises(ValueError, match="n_mels"):
        save_features(out, bad, cfg)


def test_save_features_creates_parent_dirs(tmp_path):
    """save_features creates parent directories as needed."""
    cfg = LogMelConfig()
    nested = tmp_path / "a" / "b" / "c.npz"
    save_features(nested, np.zeros((cfg.n_mels, 5), dtype=np.float32), cfg)
    assert nested.exists()


def test_load_features_format_version_mismatch(tmp_path):
    """Loading a file with an incompatible format_version raises."""
    cfg = LogMelConfig()
    out = tmp_path / "test.npz"
    np.savez_compressed(
        out,
        features=np.zeros((cfg.n_mels, 5), dtype=np.float16),
        format_version=np.array(99, dtype=np.int32),
        config__sample_rate=np.array(cfg.sample_rate),
        config__n_fft=np.array(cfg.n_fft),
        config__hop=np.array(cfg.hop),
        config__n_mels=np.array(cfg.n_mels),
        config__fmin=np.array(cfg.fmin),
        config__fmax=np.array("__none__", dtype=object),
    )
    with pytest.raises(ValueError, match="format version"):
        load_features(out)
