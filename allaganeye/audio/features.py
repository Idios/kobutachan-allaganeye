"""Log-mel spectrogram feature extraction and persistence.

The features are deliberately one-way: the mel filterbank discards FFT
phase and aggregates magnitudes into ``n_mels`` bands, so the original
audio cannot be perceptually reconstructed from the saved features.

The on-disk ``.npz`` format is pickle-free: metadata is stored as a JSON
string and ``fmax=None`` is persisted as ``NaN``.  This allows
``load_features`` to use ``allow_pickle=False``, closing the RCE vector
that would otherwise exist when reading ``.npz`` files from untrusted
sources.
"""

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.signal import stft


@dataclass(frozen=True)
class LogMelConfig:
    """Configuration for log-mel feature extraction.

    Defaults match the reference implementation used to ship the bundled
    feature files.  Reference and target features must use the same
    config to be comparable.
    """

    sample_rate: int = 22050
    n_fft: int = 2048
    hop: int = 512
    n_mels: int = 80
    fmin: float = 0.0
    fmax: float | None = None  # defaults to sample_rate / 2

    @property
    def effective_fmax(self) -> float:
        return self.fmax if self.fmax is not None else self.sample_rate / 2

    @property
    def frames_per_second(self) -> float:
        return self.sample_rate / self.hop


def _hz_to_mel(hz: np.ndarray | float) -> np.ndarray:
    return 2595.0 * np.log10(1 + np.asarray(hz, dtype=np.float64) / 700.0)


def _mel_to_hz(mel: np.ndarray | float) -> np.ndarray:
    return 700.0 * (10 ** (np.asarray(mel, dtype=np.float64) / 2595.0) - 1)


def mel_filterbank(config: LogMelConfig) -> np.ndarray:
    """Slaney-style triangular mel filterbank.

    Returns a (n_mels, n_fft // 2 + 1) matrix that maps a magnitude-spectrum
    column to mel-scale energies.  Each filter is area-normalized so that
    bands at higher frequencies (which span more FFT bins) do not dominate.
    """
    n_freqs = config.n_fft // 2 + 1
    fft_freqs = np.linspace(0, config.sample_rate / 2, n_freqs)
    mel_points = np.linspace(
        _hz_to_mel(config.fmin),
        _hz_to_mel(config.effective_fmax),
        config.n_mels + 2,
    )
    hz_points = _mel_to_hz(mel_points)

    fb = np.zeros((config.n_mels, n_freqs), dtype=np.float32)
    for m in range(config.n_mels):
        lo, ctr, hi = hz_points[m], hz_points[m + 1], hz_points[m + 2]
        rising = (fft_freqs - lo) / (ctr - lo + 1e-10)
        falling = (hi - fft_freqs) / (hi - ctr + 1e-10)
        triangle = np.maximum(0, np.minimum(rising, falling))
        fb[m] = triangle

    enorm = 2.0 / (hz_points[2 : config.n_mels + 2] - hz_points[: config.n_mels])
    fb *= enorm[:, np.newaxis]
    return fb


def log_mel_spectrogram(
    audio: np.ndarray,
    config: LogMelConfig | None = None,
) -> np.ndarray:
    """Compute log-mel spectrogram of mono PCM in [-1, 1].

    Returns a (n_mels, n_frames) float32 array.  ``log1p`` is used so the
    output is non-negative and stable for silent input.
    """
    if config is None:
        config = LogMelConfig()

    _, _, z = stft(
        audio,
        fs=config.sample_rate,
        nperseg=config.n_fft,
        noverlap=config.n_fft - config.hop,
        boundary=None,  # type: ignore[arg-type]
        padded=False,
    )
    power = (np.abs(z) ** 2).astype(np.float32)
    fb = mel_filterbank(config)
    mel_power = fb @ power
    return np.log1p(mel_power).astype(np.float32)


_FEATURE_FILE_FORMAT_VERSION = 2


def save_features(
    path: Path,
    features: np.ndarray,
    config: LogMelConfig,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Save features and config metadata as a compressed .npz file.

    Features are stored as float16 to keep file size minimal.  ``config``
    fields are persisted so the file can be loaded without external
    knowledge of the extraction parameters.  ``metadata`` must be
    JSON-serializable; it is stored as a JSON string so the file can be
    loaded without ``allow_pickle=True``.
    """
    if features.ndim != 2 or features.shape[0] != config.n_mels:
        raise ValueError(
            f"features shape {features.shape} does not match config n_mels={config.n_mels}"
        )
    payload = {
        "features": features.astype(np.float16),
        "format_version": np.array(_FEATURE_FILE_FORMAT_VERSION, dtype=np.int32),
    }
    for key, value in asdict(config).items():
        # fmax=None is the only optional field; persist it as NaN so the
        # column stays numeric and readable without allow_pickle.
        if key == "fmax" and value is None:
            payload[f"config__{key}"] = np.array(np.nan, dtype=np.float64)
        else:
            payload[f"config__{key}"] = np.array(value)
    if metadata:
        payload["metadata"] = np.array(json.dumps(metadata))

    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **payload)


def load_features(path: Path) -> tuple[np.ndarray, LogMelConfig, dict[str, Any]]:
    """Load features, config, and metadata from a .npz file.

    Returns features as float32 (upcast from stored float16) for matcher
    compatibility.  Raises ``ValueError`` on format mismatch.  Uses
    ``allow_pickle=False`` so malicious ``.npz`` inputs cannot execute
    code via pickle during load.
    """
    with np.load(path, allow_pickle=False) as data:
        version = int(data["format_version"])
        if version != _FEATURE_FILE_FORMAT_VERSION:
            raise ValueError(
                f"Unsupported feature file format version {version} "
                f"(expected {_FEATURE_FILE_FORMAT_VERSION})"
            )
        features = data["features"].astype(np.float32)

        config_kwargs: dict[str, Any] = {}
        for key in ("sample_rate", "n_fft", "hop", "n_mels"):
            config_kwargs[key] = int(data[f"config__{key}"])
        config_kwargs["fmin"] = float(data["config__fmin"])
        fmax_val = float(data["config__fmax"])
        config_kwargs["fmax"] = None if math.isnan(fmax_val) else fmax_val
        config = LogMelConfig(**config_kwargs)

        metadata: dict[str, Any] = (
            json.loads(str(data["metadata"])) if "metadata" in data else {}
        )

    return features, config, metadata
