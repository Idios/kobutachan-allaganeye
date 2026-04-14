"""Bundled reference feature files for BGM detection.

Files in this directory are non-reversible feature representations
(log-mel spectrogram coefficients) generated from short BGM segments.
Use :func:`get_reference_path` to obtain a filesystem path that works
both in development and from an installed wheel.
"""

from importlib.resources import as_file, files
from pathlib import Path

_PACKAGE = __name__


def get_reference_path(name: str) -> Path:
    """Resolve a bundled reference feature file to a filesystem path.

    *name* is the file stem (e.g. ``"fanfare"``); the ``.npz`` extension
    is appended automatically.  Raises ``FileNotFoundError`` if the
    reference is not present.
    """
    resource = files(_PACKAGE).joinpath(f"{name}.npz")
    with as_file(resource) as path:
        if not path.exists():
            raise FileNotFoundError(
                f"Reference feature '{name}' not found in {_PACKAGE}"
            )
        return Path(path)
