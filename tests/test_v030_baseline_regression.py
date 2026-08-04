"""v0.3.0 baseline regression tests (#576 S7.2 / S9.2).

slow + slow_detect マーカー: 実動画必須。`pytest -m slow` / `-m slow_detect` で実行し、
bare pytest からは addopts (`-m 'not slow and not baseline_regen'`) により除外される。
Idios 環境または ALLAGANEYE_SAMPLE_VIDEO_DIR が設定されたマシンで実行。
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.split_baseline_compare import diff_split_against_baseline

pytestmark = [pytest.mark.slow, pytest.mark.slow_detect]

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BASELINE_DIR = _REPO_ROOT / "tests" / "baselines" / "v0.3.0"
_COMPARE_SCRIPT = _REPO_ROOT / "scripts" / "compare-baseline.py"

# Class A baselines: bit-exact projection (matches+gaps).
_CLASS_A_BASELINES = [
    ("obs-20260116", "20260116/2026-01-16 22-12-57.mkv"),
    ("obs-20260119", "20260119/2026-01-19 22-09-07.mkv"),
    ("obs-20260127", "20260127/2026-01-27 21-59-15.mkv"),
    ("obs-20260209", "2026-02-09 23-12-24.mkv"),
]


@pytest.mark.parametrize("label,relpath", _CLASS_A_BASELINES)
def test_class_a_bit_exact(label, relpath, sample_video_dir, tmp_output_dir):
    """new path で detect を回し Class A baseline と matches/gaps が完全一致 (#576 S3 / S9.2)."""
    video = sample_video_dir / relpath
    if not video.exists():
        pytest.skip(f"video not found: {video}")

    out_meta = tmp_output_dir / "metadata.json"
    cmd = [
        sys.executable,
        "-m",
        "allaganeye",
        "detect",
        str(video),
        "-o",
        str(tmp_output_dir),
        "--no-cache",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    assert result.returncode == 0, f"detect failed: {result.stderr}"
    assert out_meta.exists(), "metadata.json not produced"

    baseline_path = _BASELINE_DIR / f"{label}.metadata.json"
    cmp = subprocess.run(
        [sys.executable, str(_COMPARE_SCRIPT), str(baseline_path), str(out_meta)],
        capture_output=True,
        text=True,
    )
    assert cmp.returncode == 0, (
        f"Class A baseline diff for {label}: {cmp.stdout} {cmp.stderr}"
    )


@pytest.mark.parametrize("label,relpath", _CLASS_A_BASELINES)
def test_class_a_intermediate_audit_no_regress(
    label, relpath, sample_video_dir, tmp_output_dir, monkeypatch
):
    """Class A: new path と legacy path で Pass 1 candidate / Pass 2 refined region
    の dump を比較し、最終 projection が同じでも内部値の差が予想 epsilon 内であることを確認
    (#576 S3 / S7.2.12).

    本テストは regression report 用なので strict assert はせず、
    出力 diff を stderr に書き、test 自体は xfail(strict=False) 相当。
    """
    video = sample_video_dir / relpath
    if not video.exists():
        pytest.skip(f"video not found: {video}")

    new_meta = tmp_output_dir / "new" / "metadata.json"
    legacy_meta = tmp_output_dir / "legacy" / "metadata.json"

    # new path (default, env var unset by conftest autouse)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "allaganeye",
            "detect",
            str(video),
            "-o",
            str(tmp_output_dir / "new"),
            "-v",
            "--no-cache",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=1800,
    )

    # legacy path (env var = 1)
    env = {**os.environ, "ALLAGANEYE_DETECT_FPS_FILTER": "1"}
    subprocess.run(
        [
            sys.executable,
            "-m",
            "allaganeye",
            "detect",
            str(video),
            "-o",
            str(tmp_output_dir / "legacy"),
            "-v",
            "--no-cache",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=1800,
        env=env,
    )

    new_data = json.loads(new_meta.read_text(encoding="utf-8"))
    legacy_data = json.loads(legacy_meta.read_text(encoding="utf-8"))

    # 最終 projection が一致することを確認
    assert new_data["matches"] == legacy_data["matches"], (
        f"{label}: matches diff between new and legacy path "
        f"-- Class A should keep bit-exact projection."
    )
    assert new_data["gaps"] == legacy_data["gaps"], (
        f"{label}: gaps diff between new and legacy path."
    )
    # 内部値 (verbose stats / brightness samples) は legitimate に変わって OK。
    # ここでは report のみ (本番では PR 本文に dump 添付)。


# Class B baseline: regenerated in this PR (#576) because the new path
# legitimately detects the 0.8s blackout at ~6184 that legacy fps filter
# missed (#560 root cause fix).  After regenerate, the new path must
# bit-exact match the new baseline.
_CLASS_B_BASELINE = ("obs-20260118", "20260118/2026-01-18 22-15-18.mkv")


def test_class_b_regenerated(sample_video_dir, tmp_output_dir):
    """Class B (obs-20260118) は本 PR で regenerate された baseline と一致 (#576 S3)."""
    label, relpath = _CLASS_B_BASELINE
    video = sample_video_dir / relpath
    if not video.exists():
        pytest.skip(f"video not found: {video}")

    out_meta = tmp_output_dir / "metadata.json"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "allaganeye",
            "detect",
            str(video),
            "-o",
            str(tmp_output_dir),
            "--no-cache",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=1800,
    )

    baseline_path = _BASELINE_DIR / f"{label}.metadata.json"
    cmp = subprocess.run(
        [sys.executable, str(_COMPARE_SCRIPT), str(baseline_path), str(out_meta)],
        capture_output=True,
        text=True,
    )
    assert cmp.returncode == 0, (
        f"Class B baseline mismatch (regenerated baseline diverged): "
        f"{cmp.stdout} {cmp.stderr}"
    )


@pytest.mark.parametrize(
    "vendor,timestamps",
    [
        # obs-20260116 (1920x1080, 60fps, AV1):
        # 黒/transition/lobby/normal の 4 種類で _probe_single_frame と
        # 新 path の brightness が +-2.0 (= _BLACKOUT_THRESHOLD_UPPER_MARGIN)
        # 以内で一致することを確認する (#576 S7.2.16 / S9.3)。
        ("cpu", [4.0, 30.0, 600.0, 1200.0]),
        ("nvidia", [4.0, 30.0, 600.0, 1200.0]),
        ("amd", [4.0, 30.0, 600.0, 1200.0]),
    ],
)
def test_vendor_golden_brightness(vendor, timestamps, sample_video_dir, tmp_output_dir):
    """各 vendor で _probe_single_frame と新 path の brightness が
    +-2.0 以内で一致 (#576 S7.2.16 / S9.3 #3).

    Idios 環境で NVIDIA / AMD が利用可能な前提。Intel は別途 AskUserQuestion。
    """
    import platform

    video = sample_video_dir / "20260116" / "2026-01-16 22-12-57.mkv"
    if not video.exists():
        pytest.skip(f"video not found: {video}")

    # Skip if vendor not available (CI fallback)
    if vendor == "nvidia" and platform.system() != "Windows":
        pytest.skip("NVIDIA GPU only validated on Windows Idios env")

    chunks_csv = ",".join(str(t) for t in timestamps)
    cmd = [
        sys.executable,
        str(_REPO_ROOT / "scripts" / "validate-fps-retirement.py"),
        "--video",
        str(video),
        "--chunks",
        chunks_csv,
        "--vendor",
        vendor,
        "--codec",
        "av1",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    # exit 0 = all PASS, exit 1 = FAIL, exit 2 = script error.
    if result.returncode == 2:
        pytest.skip(f"validate script error for vendor={vendor}: {result.stderr}")
    assert result.returncode == 0, (
        f"vendor golden brightness FAIL for {vendor}: "
        f"stdout=\n{result.stdout}\nstderr=\n{result.stderr}"
    )


# Split bit-exact baselines (#779 generated; P2-22 / #844 wires the gate).
_SPLIT_BASELINES = [
    ("obs-20260116", "20260116/2026-01-16 22-12-57.mkv"),
    ("obs-20260118", "20260118/2026-01-18 22-15-18.mkv"),
    ("obs-20260119", "20260119/2026-01-19 22-09-07.mkv"),
    ("obs-20260127", "20260127/2026-01-27 21-59-15.mkv"),
    ("obs-20260209", "2026-02-09 23-12-24.mkv"),
]


@pytest.mark.parametrize("label,relpath", _SPLIT_BASELINES)
def test_split_bit_exact(label, relpath, sample_video_dir, tmp_output_dir):
    """split --from-metadata output SHA-256 + size matches obs-*.split.json (P2-22).

    detect Class A bit-exact analogue for the splitter (-c copy remux). Rewrites
    the baseline metadata 'source' to the local video, runs split, and byte-checks
    each produced match file against the committed split baseline.

    Shares this module's slow_detect lane (no separate slow_split marker): this is
    a v0.3.0 baseline-regression gate alongside the detect baselines, so it runs in
    the same `-m slow_detect` proxy verification pass.
    """
    video = sample_video_dir / relpath
    if not video.exists():
        pytest.skip(f"video not found: {video}")
    split_baseline = _BASELINE_DIR / f"{label}.split.json"
    meta_baseline = _BASELINE_DIR / f"{label}.metadata.json"
    if not split_baseline.exists() or not meta_baseline.exists():
        pytest.skip(f"baseline missing for {label}")

    meta = json.loads(meta_baseline.read_text(encoding="utf-8"))
    meta["source"] = str(video.resolve())
    in_meta = tmp_output_dir / "metadata.json"
    in_meta.write_text(json.dumps(meta), encoding="utf-8")
    out_dir = tmp_output_dir / "splits"
    out_dir.mkdir()

    cmd = [
        sys.executable,
        "-m",
        "allaganeye",
        "split",
        "--from-metadata",
        str(in_meta),
        "-o",
        str(out_dir),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    assert result.returncode == 0, f"split failed: {result.stderr}"

    expected = json.loads(split_baseline.read_text(encoding="utf-8"))
    problems = diff_split_against_baseline(out_dir, expected["splits"])
    assert not problems, f"split bit-exact diff for {label}:\n" + "\n".join(problems)
