"""Generate baseline detection results for regression tests.

Usage:
    python tests/generate_baselines.py

Requires ALLAGANEYE_SAMPLE_VIDEO_DIR to be set.
Runs detection WITHOUT scorebar filtering (src_resolution=None)
and saves results to tests/baselines/<name>.json.
"""

import json
import os
import time
from pathlib import Path

from allaganeye.video.detector import detect_match_boundaries
from allaganeye.video.probe import probe_video

_BASELINES_DIR = Path(__file__).parent / "baselines"
_TARGET_SUBDIRS = ["20260116", "20260118", "20260119"]


def _find_source_mkv(subdir: Path) -> Path | None:
    mkvs = sorted(subdir.glob("*.mkv"))
    if not mkvs:
        return None
    return max(mkvs, key=lambda p: p.stat().st_size)


def main() -> None:
    env_path = os.environ.get("ALLAGANEYE_SAMPLE_VIDEO_DIR")
    if not env_path:
        print("ERROR: ALLAGANEYE_SAMPLE_VIDEO_DIR not set")
        return

    base = Path(env_path)
    _BASELINES_DIR.mkdir(exist_ok=True)

    for name in _TARGET_SUBDIRS:
        subdir = base / name
        mkv = _find_source_mkv(subdir)
        if mkv is None:
            print(f"SKIP {name}: no MKV found")
            continue

        print(f"Processing {name}: {mkv.name} ...")
        meta = probe_video(mkv)

        start = time.monotonic()
        boundaries = detect_match_boundaries(
            mkv,
            duration_hint=meta["duration"],
            sample_interval=2.0,
            blackout_threshold=15.0,
            min_match_duration=300.0,
            min_blackout_duration=3.0,
            # src_resolution omitted -> no scorebar filtering
        )
        elapsed = time.monotonic() - start

        # GPU cooldown
        time.sleep(1)

        baseline = {
            "name": name,
            "source": mkv.name,
            "duration": meta["duration"],
            "width": meta["width"],
            "height": meta["height"],
            "match_count": len(boundaries),
            "boundaries": boundaries,
            "elapsed": round(elapsed, 1),
        }

        out_path = _BASELINES_DIR / f"{name}.json"
        out_path.write_text(
            json.dumps(baseline, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"  -> {out_path.name}: {len(boundaries)} matches, {elapsed:.1f}s")

    print("Done.")


if __name__ == "__main__":
    main()
