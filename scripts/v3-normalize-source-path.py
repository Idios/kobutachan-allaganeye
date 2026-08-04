"""One-off: normalize V3 baseline metadata.json `source` to relative path.

PR #793 V3 detects (obs-20260119/127/209) were invoked with absolute Windows
paths under ``$ALLAGANEYE_SAMPLE_VIDEO_DIR``, so resulting metadata.json
``source`` fields are absolute paths.  Legacy baselines (and ground-truth
files) use the ``<dir-label>/<filename>.mkv`` relative format, which
``scripts/audit-compare.py`` requires for source-vs-ground-truth matching.

This script strips the ``$ALLAGANEYE_SAMPLE_VIDEO_DIR`` prefix (default
``E:/royalstraightflesh/videos/``) and normalizes separators to ``/``.
Skips files that are already relative.

Usage:

    python scripts/v3-normalize-source-path.py

Per Iron Law 3 (NO SCOPE CREEP WITHOUT NEW ISSUE): kept as documented
one-off because every V3 detect requires this normalization until detect
itself stores relative paths.  Deletion candidate once detect adopts
relative-path storage (separate v0.3.x issue).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_DEFAULT_PREFIX = "E:/royalstraightflesh/videos/"


def _resolved_prefix() -> str:
    env = os.environ.get("ALLAGANEYE_SAMPLE_VIDEO_DIR", "")
    if not env:
        return _DEFAULT_PREFIX
    norm = env.replace("\\", "/")
    if not norm.endswith("/"):
        norm += "/"
    return norm


def normalize(path: Path, prefix: str) -> None:
    if not path.exists():
        print(f"{path}: SKIP (file not present)")
        return
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    old = data["source"]
    norm = old.replace("\\", "/")
    if norm.lower().startswith(prefix.lower()):
        new = norm[len(prefix) :]
    else:
        new = norm
    if old == new:
        print(f"{path}: already relative ({new})")
        return
    data["source"] = new
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"{path}: source -> {new}")


def main() -> None:
    prefix = _resolved_prefix()
    for label in ("obs-20260119", "obs-20260127", "obs-20260209"):
        normalize(Path(f"tests/baselines/v0.3.0/{label}.metadata.json"), prefix)


if __name__ == "__main__":
    main()
