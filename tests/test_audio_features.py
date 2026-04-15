"""Tests for allaganeye.audio.features module."""

import pickle

import numpy as np
import pytest

from allaganeye.audio.features import (
    LogMelConfig,
    load_features,
    load_features_multi,
    log_mel_spectrogram,
    mel_filterbank,
    save_features,
    save_features_multi,
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


def test_save_load_features_metadata_json_types(tmp_path):
    """Metadata preserves JSON-safe types (str, int, float, bool, None, list)."""
    cfg = LogMelConfig(n_mels=20)
    out = tmp_path / "test.npz"
    metadata = {
        "label": "fanfare",
        "count": 3,
        "duration": 5.0,
        "active": True,
        "tags": ["bgm", "ref"],
        "note": None,
    }
    save_features(out, np.zeros((cfg.n_mels, 5), dtype=np.float32), cfg, metadata)
    _, _, loaded = load_features(out)
    assert loaded == metadata


def test_save_features_rejects_non_json_metadata(tmp_path):
    """Non-JSON-serializable metadata values are rejected at save time."""
    cfg = LogMelConfig(n_mels=20)
    out = tmp_path / "test.npz"
    with pytest.raises(TypeError):
        save_features(
            out,
            np.zeros((cfg.n_mels, 5), dtype=np.float32),
            cfg,
            {"when": np.datetime64("2026-04-15")},
        )


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
        config__fmax=np.array(np.nan, dtype=np.float64),
    )
    with pytest.raises(ValueError, match="format version"):
        load_features(out)


def test_load_features_refuses_pickle(tmp_path):
    """A .npz containing a pickled object array is rejected by load_features.

    Regression guard: if ``allow_pickle=True`` ever slips back in, this test
    breaks. The payload below is a minimal pickle-only object array.
    """
    out = tmp_path / "malicious.npz"
    # Craft a legitimate-looking header but include a pickle-only object array.
    np.savez_compressed(
        out,
        features=np.zeros((80, 5), dtype=np.float16),
        format_version=np.array(2, dtype=np.int32),
        config__sample_rate=np.array(22050),
        config__n_fft=np.array(2048),
        config__hop=np.array(512),
        config__n_mels=np.array(80),
        config__fmin=np.array(0.0),
        config__fmax=np.array(np.nan, dtype=np.float64),
        metadata=np.array({"evil": object()}, dtype=object),
    )
    # Sanity: the crafted file genuinely requires pickle to read metadata.
    with np.load(out, allow_pickle=True) as data:
        pickle.dumps(data["metadata"].item())  # ensures object-array payload

    with pytest.raises(ValueError, match="allow_pickle=False"):
        load_features(out)


# --- Multi-reference format (v3, #289) ---


def test_save_load_features_multi_roundtrip(tmp_path):
    """Saved multi-ref features are recovered (within float16 precision)."""
    cfg = LogMelConfig(n_mels=40)
    rng = np.random.RandomState(7)
    refs = [
        rng.randn(40, 60).astype(np.float32),
        rng.randn(40, 100).astype(np.float32),
    ]
    out = tmp_path / "multi.npz"
    save_features_multi(out, refs, cfg, {"windows": [{"w": 0}, {"w": 1}]})

    loaded, loaded_cfg, metadata = load_features_multi(out)
    assert len(loaded) == 2
    for i, (ref, exp) in enumerate(zip(loaded, refs, strict=True)):
        assert ref.shape == exp.shape, f"ref {i} shape"
        np.testing.assert_allclose(ref, exp, rtol=1e-2, atol=1e-3)
    assert loaded_cfg == cfg
    assert metadata == {"windows": [{"w": 0}, {"w": 1}]}


def test_load_features_multi_accepts_legacy_single_ref(tmp_path):
    """load_features_multi transparently wraps a v2 file into a 1-element list."""
    cfg = LogMelConfig(n_mels=20)
    features = np.ones((20, 30), dtype=np.float32)
    out = tmp_path / "legacy.npz"
    save_features(out, features, cfg, {"label": "legacy"})

    loaded, loaded_cfg, metadata = load_features_multi(out)
    assert len(loaded) == 1
    np.testing.assert_allclose(loaded[0], features, rtol=1e-2, atol=1e-3)
    assert loaded_cfg == cfg
    assert metadata == {"label": "legacy"}


def test_save_features_multi_rejects_empty_list(tmp_path):
    cfg = LogMelConfig()
    out = tmp_path / "empty.npz"
    with pytest.raises(ValueError, match="at least one reference"):
        save_features_multi(out, [], cfg)


def test_save_features_multi_rejects_shape_mismatch(tmp_path):
    cfg = LogMelConfig(n_mels=80)
    good = np.zeros((80, 10), dtype=np.float32)
    bad = np.zeros((40, 10), dtype=np.float32)
    out = tmp_path / "bad.npz"
    with pytest.raises(ValueError, match=r"features_list\[1\]"):
        save_features_multi(out, [good, bad], cfg)


def test_load_features_multi_refuses_pickle(tmp_path):
    """Multi-ref load also uses allow_pickle=False.

    Crafts a v3-shaped file with pickle-only metadata; loading must raise
    rather than deserialize the malicious object.
    """
    out = tmp_path / "malicious_multi.npz"
    np.savez_compressed(
        out,
        features_0=np.zeros((80, 5), dtype=np.float16),
        n_refs=np.array(1, dtype=np.int32),
        format_version=np.array(3, dtype=np.int32),
        config__sample_rate=np.array(22050),
        config__n_fft=np.array(2048),
        config__hop=np.array(512),
        config__n_mels=np.array(80),
        config__fmin=np.array(0.0),
        config__fmax=np.array(np.nan, dtype=np.float64),
        metadata=np.array({"evil": object()}, dtype=object),
    )
    with np.load(out, allow_pickle=True) as data:
        pickle.dumps(data["metadata"].item())

    with pytest.raises(ValueError, match="allow_pickle=False"):
        load_features_multi(out)
