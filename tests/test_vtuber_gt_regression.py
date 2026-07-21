"""VTuber timeline GT (P3, #895)。

GT (tests/baselines/v0.3.0/vtuber-gt/*.json) `--vtuber` detect
と突合する。slow test は実 VOD 必須 (ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER)。
compare_detection_to_gt は pure なので unit でも検証する。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_GT_DIR = Path(__file__).parent / "baselines" / "v0.3.0" / "vtuber-gt"


def apply_expected_merge(matches: list[dict]) -> list[dict]:
    """GT matches の expected_merge_with_next: true を適用して合成 GT match 列を返す。

    expected_merge_with_next=true の match は次の match と合成する:
    - start = 当該 match の start_time
    - end = 次 match の end_time
    - index = 当該 match の index (先頭 match の index を採用)
    末尾 match に expected_merge_with_next=true が付いている場合は ValueError。
    """
    result: list[dict] = []
    i = 0
    while i < len(matches):
        m = matches[i]
        if m.get("expected_merge_with_next"):
            if i + 1 >= len(matches):
                raise ValueError(
                    f"expected_merge_with_next=true on last match (index {m['index']}); "
                    "annotation error"
                )
            nxt = matches[i + 1]
            merged = dict(m)
            merged["end_time"] = nxt["end_time"]
            result.append(merged)
            i += 2
        else:
            result.append(m)
            i += 1
    return result


def compare_detection_to_gt(
    detected: list[dict], gt_matches: list[dict], tolerance_sec: float
) -> dict:
    """segment と GT の 1:1 (overlap 最大対応)。"""
    unmatched_det = list(range(len(detected)))
    matched_pairs: list[tuple[int, int]] = []
    for gi, g in enumerate(gt_matches):
        best = None
        for di in unmatched_det:
            d = detected[di]
            ov = min(d["end_time"], g["end_time"]) - max(
                d["start_time"], g["start_time"]
            )
            if ov > 0 and (best is None or ov > best[1]):
                best = (di, ov)
        if best is not None:
            matched_pairs.append((gi, best[0]))
            unmatched_det.remove(best[0])
    missed = [
        g["index"]
        for gi, g in enumerate(gt_matches)
        if gi not in [p[0] for p in matched_pairs]
    ]
    spurious = [detected[di]["start_time"] for di in unmatched_det]
    errors = []
    for gi, di in matched_pairs:
        g, d = gt_matches[gi], detected[di]
        errors.append(
            (
                g["index"],
                d["start_time"] - g["start_time"],
                d["end_time"] - g["end_time"],
            )
        )
    max_abs = max((max(abs(ds), abs(de)) for _, ds, de in errors), default=0.0)
    return {
        "matched": len(matched_pairs),
        "missed": missed,
        "spurious": spurious,
        "boundary_errors": errors,
        "max_abs_error": max_abs,
    }


class TestApplyExpectedMerge:
    def test_no_merge_flags(self):
        matches = [
            {"index": 1, "start_time": 100.0, "end_time": 500.0},
            {"index": 2, "start_time": 600.0, "end_time": 1000.0},
        ]
        result = apply_expected_merge(matches)
        assert len(result) == 2
        assert result[0]["start_time"] == 100.0
        assert result[1]["end_time"] == 1000.0

    def test_merge_first_with_next(self):
        matches = [
            {
                "index": 1,
                "start_time": 100.0,
                "end_time": 500.0,
                "expected_merge_with_next": True,
            },
            {"index": 2, "start_time": 600.0, "end_time": 1000.0},
            {"index": 3, "start_time": 1100.0, "end_time": 1500.0},
        ]
        result = apply_expected_merge(matches)
        assert len(result) == 2
        assert result[0]["start_time"] == 100.0
        assert result[0]["end_time"] == 1000.0
        assert result[0]["index"] == 1
        assert result[1]["start_time"] == 1100.0

    def test_merge_preserves_original_fields(self):
        matches = [
            {
                "index": 7,
                "start_time": 7714.0,
                "end_time": 8753.0,
                "expected_merge_with_next": True,
                "notes": "test",
            },
            {"index": 8, "start_time": 8812.0, "end_time": 9767.0},
        ]
        result = apply_expected_merge(matches)
        assert len(result) == 1
        assert result[0]["start_time"] == 7714.0
        assert result[0]["end_time"] == 9767.0
        assert result[0]["notes"] == "test"

    def test_merge_last_match_raises(self):
        matches = [
            {
                "index": 1,
                "start_time": 100.0,
                "end_time": 500.0,
                "expected_merge_with_next": True,
            },
        ]
        import pytest

        with pytest.raises(ValueError, match="last match"):
            apply_expected_merge(matches)

    def test_empty_matches(self):
        assert apply_expected_merge([]) == []


class TestCompareUnit:
    def test_exact_match(self):
        det = [{"start_time": 100.0, "end_time": 500.0}]
        gt = [{"index": 1, "start_time": 100.0, "end_time": 500.0}]
        r = compare_detection_to_gt(det, gt, 15.0)
        assert r["matched"] == 1 and not r["missed"] and not r["spurious"]
        assert r["max_abs_error"] == 0.0

    def test_missed_and_spurious(self):
        det = [{"start_time": 2000.0, "end_time": 2400.0}]
        gt = [{"index": 1, "start_time": 100.0, "end_time": 500.0}]
        r = compare_detection_to_gt(det, gt, 15.0)
        assert r["missed"] == [1] and len(r["spurious"]) == 1

    def test_boundary_error_signs(self):
        det = [{"start_time": 90.0, "end_time": 520.0}]
        gt = [{"index": 1, "start_time": 100.0, "end_time": 500.0}]
        r = compare_detection_to_gt(det, gt, 15.0)
        (_, ds, de) = r["boundary_errors"][0]
        assert ds == -10.0 and de == 20.0

    def test_one_to_one_matching(self):
        # 1 が 2 GT を二重 match しない
        det = [{"start_time": 100.0, "end_time": 900.0}]
        gt = [
            {"index": 1, "start_time": 100.0, "end_time": 400.0},
            {"index": 2, "start_time": 500.0, "end_time": 900.0},
        ]
        r = compare_detection_to_gt(det, gt, 15.0)
        assert r["matched"] == 1 and len(r["missed"]) == 1


def _gt_files():
    return sorted(_GT_DIR.glob("*.json")) if _GT_DIR.exists() else []


@pytest.mark.slow
@pytest.mark.slow_detect
@pytest.mark.parametrize("gt_path", _gt_files(), ids=lambda p: p.stem)
def test_vtuber_gt_match(gt_path, tmp_path):
    """VOD で --vtuber detect し GT と突合 (matched/missed/spurious + )。"""
    gt = json.loads(gt_path.read_text(encoding="utf-8"))
    gt_matches = apply_expected_merge(gt["matches"])
    base = Path(
        os.environ.get("ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER", "E:/allaganeye-samples")
    )
    video = (
        base / gt["source_file"]
        if gt.get("source_dir_label") == "vtuber-samples"
        else None
    )
    if gt.get("source_dir_label") == "gyawa_vatos":
        video = Path("E:/videos/gyawa_vatos") / gt["source_file"]
    if video is None or not video.exists():
        pytest.skip(f"sample video not found: {gt['source_file']}")
    out = tmp_path / gt_path.stem
    env = {**os.environ, "PYTHONUTF8": "1", "ALLAGANEYE_INTEGRITY_SKIP": "1"}
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "allaganeye",
            "detect",
            str(video),
            "--vtuber",
            "--no-cache",
            "-o",
            str(out),
        ],
        capture_output=True,
        text=True,
        timeout=3600,
        env=env,
    )
    assert r.returncode == 0, r.stderr[-2000:]
    meta = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
    result = compare_detection_to_gt(meta["matches"], gt_matches, gt["tolerance_sec"])
    assert result["matched"] == len(gt_matches), result
    assert not result["missed"] and not result["spurious"], result
    assert result["max_abs_error"] <= gt["tolerance_sec"], result["boundary_errors"]
