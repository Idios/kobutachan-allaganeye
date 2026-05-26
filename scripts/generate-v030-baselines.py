"""Generate v0.3.0 OBS baseline files (#779).

Reads the selected baselines (defined in ``_BASELINES`` below, matching
``tests/baselines/v0.3.0/README.md`` from #778) and runs:

* ``allaganeye detect <video> --no-cache -o <tmp>`` → captures the full
  ``metadata.json``
* ``allaganeye split --from-metadata <metadata> -o <tmp>`` → produces
  ``match_NNN.mp4`` outputs (FFmpeg ``-c copy`` remux)

producing two files per baseline under ``tests/baselines/v0.3.0/``:

* ``<label>.metadata.json`` — full detect output (used by
  ``scripts/compare-baseline.py`` for bit-exact regression on ``matches`` +
  ``gaps`` per spec §8.2)
* ``<label>.split.json`` — SHA-256 + size of each split MP4 (used to verify
  that the FFmpeg remux output stays byte-identical after perf changes)

Usage::

    python scripts/generate-v030-baselines.py             # all 5 baselines
    python scripts/generate-v030-baselines.py --label obs-20260209  # one only

``ALLAGANEYE_SAMPLE_VIDEO_DIR`` must point at the source video tree (see
``CLAUDE.md §動画サンプルデータ``).

The ``validate_split_baseline`` / ``load_and_validate`` helpers are also
imported by ``tests/scripts/test_generate_v030_baselines.py``.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

_SCHEMA_VERSION = "1"
_LABEL_PATTERN = re.compile(r"^obs-\d{8}$")
_OUTPUT_FILE_PATTERN = re.compile(r"^match_\d{3}\.mp4$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

# Baseline selection (#778). Order matches README selection table:
# shortest first to keep the smoke-run fast.
_BASELINES: list[dict[str, str]] = [
    {
        "label": "obs-20260209",
        "source_relpath": "2026-02-09 23-12-24.mkv",
        "source_dir_label": "root",
    },
    {
        "label": "obs-20260127",
        "source_relpath": "20260127/2026-01-27 21-59-15.mkv",
        "source_dir_label": "20260127",
    },
    {
        "label": "obs-20260116",
        "source_relpath": "20260116/2026-01-16 22-12-57.mkv",
        "source_dir_label": "20260116",
    },
    {
        "label": "obs-20260118",
        "source_relpath": "20260118/2026-01-18 22-15-18.mkv",
        "source_dir_label": "20260118",
    },
    {
        "label": "obs-20260119",
        "source_relpath": "20260119/2026-01-19 22-09-07.mkv",
        "source_dir_label": "20260119",
    },
]


def validate_split_baseline(data: dict) -> None:
    """Validate the ``obs-<label>.split.json`` schema in-place.

    Raises :class:`ValueError` with an error message that mentions the
    offending field name so tests can pinpoint the failure.
    """
    for field in (
        "schema_version",
        "label",
        "source_file",
        "source_size_bytes",
        "source_dir_label",
        "generated_at",
        "splits",
    ):
        if field not in data:
            raise ValueError(f"missing required field: {field}")

    if data["schema_version"] != _SCHEMA_VERSION:
        raise ValueError(
            f"unknown schema_version {data['schema_version']!r}, "
            f"expected {_SCHEMA_VERSION!r}"
        )

    if not isinstance(data["label"], str) or not _LABEL_PATTERN.fullmatch(
        data["label"]
    ):
        raise ValueError(
            f"label {data['label']!r} does not match pattern obs-<YYYYMMDD>"
        )

    if not isinstance(data["source_size_bytes"], int) or data["source_size_bytes"] <= 0:
        raise ValueError(
            "source_size_bytes must be a positive int, "
            f"got {data['source_size_bytes']!r}"
        )

    splits = data["splits"]
    if not isinstance(splits, list) or len(splits) == 0:
        raise ValueError(f"splits must be a non-empty list, got {splits!r}")

    for i, sp in enumerate(splits):
        for field in ("index", "output_file", "size_bytes", "sha256"):
            if field not in sp:
                raise ValueError(f"splits[{i}] missing required field: {field}")
        if not isinstance(sp["index"], int) or sp["index"] <= 0:
            raise ValueError(
                f"splits[{i}].index must be positive int, got {sp['index']!r}"
            )
        if sp["index"] != i + 1:
            raise ValueError(
                f"splits[{i}].index must be {i + 1} "
                f"(sequential from 1), got {sp['index']}"
            )
        if not isinstance(sp["output_file"], str) or not _OUTPUT_FILE_PATTERN.fullmatch(
            sp["output_file"]
        ):
            raise ValueError(
                f"splits[{i}].output_file {sp['output_file']!r} does not match "
                "pattern match_NNN.mp4"
            )
        if not isinstance(sp["size_bytes"], int) or sp["size_bytes"] <= 0:
            raise ValueError(
                f"splits[{i}].size_bytes must be positive int, got {sp['size_bytes']!r}"
            )
        if not isinstance(sp["sha256"], str) or not _SHA256_PATTERN.fullmatch(
            sp["sha256"]
        ):
            raise ValueError(
                f"splits[{i}].sha256 {sp['sha256']!r} is not 64 lowercase hex chars"
            )


def load_and_validate(path: Path) -> dict:
    """Read ``path`` and validate it as a split baseline JSON."""
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_split_baseline(data)
    return data


def _sha256_of_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            data = f.read(chunk)
            if not data:
                break
            h.update(data)
    return h.hexdigest()


def _iso_utc_now() -> str:
    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _baselines_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "tests" / "baselines" / "v0.3.0"


def _generate_one(baseline: dict, sample_dir: Path, out_dir: Path) -> None:
    label = baseline["label"]
    source = sample_dir / baseline["source_relpath"]
    if not source.is_file():
        raise FileNotFoundError(f"source video not found: {source}")

    source_size = source.stat().st_size
    print(f"[{label}] source = {source.name} ({source_size / 1e9:.2f} GB)")

    with tempfile.TemporaryDirectory(prefix=f"v030-baseline-{label}-") as tmp:
        tmp_path = Path(tmp)

        print(f"[{label}] running allaganeye detect ...")
        # ``--gpu`` so the committed baseline records ``use_gpu: true`` /
        # ``gpu_vendor_used`` from the actual accelerated run (matching the
        # established baseline format); without it the auto path records
        # ``null`` (#797 round-4 review).
        subprocess.run(
            [
                sys.executable,
                "-m",
                "allaganeye",
                "detect",
                "--gpu",
                "--no-cache",
                "-o",
                str(tmp_path),
                str(source),
            ],
            check=True,
        )

        metadata_src = tmp_path / "metadata.json"
        if not metadata_src.is_file():
            raise RuntimeError(
                f"[{label}] detect did not produce metadata.json in {tmp_path}"
            )

        # Capture detect's metadata (relative ``output_file`` placeholders such
        # as ``match_001.mp4``) BEFORE running split: ``split --from-metadata -o
        # <tmp>`` rewrites ``output_file`` to absolute tmp paths (see
        # split_matches "updated output_file entries"), which must not leak into
        # the committed, environment-portable baseline (#797 round-4 review).
        metadata_payload = json.loads(metadata_src.read_text(encoding="utf-8"))

        # Split needs the absolute ``source`` path that ``detect`` wrote.
        # We run split off the tmp copy, then write the committed baseline
        # with ``source`` normalised to the relative posix path so the
        # checked-in metadata is environment-portable (codex F1, #779 review).
        print(f"[{label}] running allaganeye split --from-metadata ...")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "allaganeye",
                "split",
                "--from-metadata",
                str(metadata_src),
                "-o",
                str(tmp_path),
            ],
            check=True,
        )

        metadata_payload["source"] = baseline["source_relpath"]
        metadata_dst = out_dir / f"{label}.metadata.json"
        metadata_dst.write_text(
            json.dumps(metadata_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"[{label}] wrote {metadata_dst.name} (source normalised)")

        mp4_files = sorted(tmp_path.glob("match_*.mp4"))
        if not mp4_files:
            raise RuntimeError(f"[{label}] no match_*.mp4 found in {tmp_path}")

        splits: list[dict] = []
        for i, mp4 in enumerate(mp4_files, start=1):
            size = mp4.stat().st_size
            sha = _sha256_of_file(mp4)
            splits.append(
                {
                    "index": i,
                    "output_file": mp4.name,
                    "size_bytes": size,
                    "sha256": sha,
                }
            )
            print(
                f"[{label}]   split {i}: {mp4.name} "
                f"= {size / 1e6:.1f} MB sha={sha[:16]}..."
            )

        payload = {
            "schema_version": _SCHEMA_VERSION,
            "label": label,
            "source_file": baseline["source_relpath"],
            "source_size_bytes": source_size,
            "source_dir_label": baseline["source_dir_label"],
            "generated_at": _iso_utc_now(),
            "splits": splits,
        }
        validate_split_baseline(payload)
        split_dst = out_dir / f"{label}.split.json"
        split_dst.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"[{label}] wrote {split_dst.name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--label",
        help=(
            "Generate only this label (e.g., obs-20260116). "
            "Default: all selected baselines."
        ),
    )
    args = parser.parse_args(argv)

    sample_dir_env = os.environ.get("ALLAGANEYE_SAMPLE_VIDEO_DIR")
    if not sample_dir_env:
        print("ERROR: ALLAGANEYE_SAMPLE_VIDEO_DIR not set", file=sys.stderr)
        return 2
    sample_dir = Path(sample_dir_env)
    if not sample_dir.is_dir():
        print(f"ERROR: {sample_dir} is not a directory", file=sys.stderr)
        return 2

    out_dir = _baselines_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.label:
        targets = [b for b in _BASELINES if b["label"] == args.label]
        if not targets:
            print(f"ERROR: unknown label {args.label!r}", file=sys.stderr)
            return 2
    else:
        targets = _BASELINES

    for baseline in targets:
        _generate_one(baseline, sample_dir, out_dir)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
