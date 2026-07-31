"""Tests for the ``allaganeye detect`` command (#463)."""

import json
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from allaganeye.commands.detect import run_detect
from allaganeye.commands.split_matches import CacheHit, build_brightness_samples
from allaganeye.config import SplitConfig
from allaganeye.exceptions import DetectionError
from allaganeye.video.detector import MatchBoundary
from allaganeye.video.probe import ProbeResult

if TYPE_CHECKING:
    from allaganeye.metadata_types import CaptureRegions

PROBE_RESULT: ProbeResult = {
    "duration": 1800.0,
    "width": 1920,
    "height": 1080,
    "fps": 30.0,
    "fps_num": 30,
    "fps_den": 1,
    "codec": "h264",
    "audio_codec": "aac",
}

BOUNDARIES: list[MatchBoundary] = [
    {"start": 0.0, "end": 600.0, "type": "fl_match"},
    {"start": 610.0, "end": 1200.0, "type": "fl_match"},
]

MODULE_DETECT = "allaganeye.commands.detect"
MODULE_SPLIT = "allaganeye.commands.split_matches"


@pytest.fixture(autouse=True)
def _mock_audio_scan():
    """Detect also consumes the shared ``_run_audio_scan`` helper."""
    with patch(f"{MODULE_SPLIT}._run_audio_scan", return_value=None) as m:
        yield m


def _mock_detect_only(tmp_path: Path):
    """Common patches for ``run_detect`` pipeline tests."""
    return (
        patch(f"{MODULE_DETECT}.probe_video", return_value=PROBE_RESULT),
        patch(f"{MODULE_DETECT}._run_detection", return_value=BOUNDARIES),
    )


def test_detect_writes_metadata_without_note(tmp_path):
    probe, detect = _mock_detect_only(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    with probe, detect:
        run_detect(Path("input.mp4"), config, quiet=True)

    meta_path = tmp_path / "metadata.json"
    assert meta_path.exists()
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    # `note` was retired in #463
    assert "note" not in payload
    assert payload["source"] == str(Path("input.mp4"))
    assert payload["source_duration"] == PROBE_RESULT["duration"]
    assert len(payload["matches"]) == len(BOUNDARIES)
    assert payload["matches"][0]["output_file"] == "match_001.mp4"
    assert payload["matches"][1]["output_file"] == "match_002.mp4"


def test_detect_writes_detection_started_and_completed_at(tmp_path):
    """detect 経路でも detection_started_at / completed_at が書かれる (#586).

    GUI CompleteScreen「所要」列が detect-only パスで生成された
    metadata.json に対しても elapsed を計算できるよう、両フィールドが
    payload に存在し、completed_at >= started_at であることを確認する。
    """
    from datetime import datetime

    probe, detect = _mock_detect_only(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    with probe, detect:
        run_detect(Path("input.mp4"), config, quiet=True)

    payload = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    started_at = payload["detection_started_at"]
    completed_at = payload["detection_completed_at"]

    assert isinstance(started_at, str) and started_at.endswith("Z")
    assert isinstance(completed_at, str) and completed_at.endswith("Z")

    started_parsed = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    completed_parsed = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
    assert completed_parsed >= started_parsed

    # started_at は detected_at と同値で書く (案 B 後方互換).
    assert started_at == payload["detected_at"]


def test_detect_does_not_call_split_video(tmp_path):
    probe, detect = _mock_detect_only(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    with probe, detect, patch(f"{MODULE_SPLIT}.split_video") as mock_split:
        run_detect(Path("input.mp4"), config, quiet=True)

    mock_split.assert_not_called()


def test_detect_uses_placeholder_output_file_names(tmp_path):
    probe, detect = _mock_detect_only(tmp_path)
    config = SplitConfig(output_dir=tmp_path / "nested", min_match_duration=60.0)
    with probe, detect:
        run_detect(Path("input.mp4"), config, quiet=True)

    payload = json.loads((tmp_path / "nested" / "metadata.json").read_text("utf-8"))
    names = [m["output_file"] for m in payload["matches"]]
    assert names == ["match_001.mp4", "match_002.mp4"]


def test_detect_raises_when_no_boundaries(tmp_path):
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    with (
        patch(f"{MODULE_DETECT}.probe_video", return_value=PROBE_RESULT),
        patch(f"{MODULE_DETECT}._run_detection", return_value=[]),
        pytest.raises(DetectionError),
    ):
        run_detect(Path("input.mp4"), config, quiet=True)


def test_detect_uses_cache_when_present(tmp_path):
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    with (
        patch(f"{MODULE_DETECT}.probe_video", return_value=PROBE_RESULT),
        patch(
            f"{MODULE_DETECT}._load_cache_hit",
            return_value=CacheHit(
                boundaries=BOUNDARIES, masked_fallback_used=False, capture_regions=None
            ),
        ),
        patch(f"{MODULE_DETECT}._run_detection") as mock_detect,
    ):
        run_detect(Path("input.mp4"), config, quiet=True)

    mock_detect.assert_not_called()
    assert (tmp_path / "metadata.json").exists()


def test_detect_verbose_cache_miss_summary_includes_vtuber_token(tmp_path, capsys):
    """detect の cache-miss verbose summary に vtuber token が出る (PR #823 R2).

    run_split 側の Detecting summary (R1 fix) と同形。初回 (cache-miss) 実行でも
    検出 mode の provenance が stdout に残ることを pin する。
    """
    config = SplitConfig(
        output_dir=tmp_path, min_match_duration=60.0, no_cache=True, vtuber=True
    )
    with (
        patch(f"{MODULE_DETECT}.probe_video", return_value=PROBE_RESULT),
        patch(f"{MODULE_DETECT}._run_detection", return_value=BOUNDARIES),
    ):
        run_detect(Path("input.mp4"), config, verbose=True)
    out = capsys.readouterr().out
    assert "Detecting match boundaries" in out
    assert "vtuber=on" in out

    config_off = SplitConfig(
        output_dir=tmp_path, min_match_duration=60.0, no_cache=True
    )
    with (
        patch(f"{MODULE_DETECT}.probe_video", return_value=PROBE_RESULT),
        patch(f"{MODULE_DETECT}._run_detection", return_value=BOUNDARIES),
    ):
        run_detect(Path("input.mp4"), config_off, verbose=True)
    out = capsys.readouterr().out
    assert "vtuber=off" in out


def test_detect_verbose_cache_miss_prints_region_line(tmp_path, capsys):
    """detect fresh 経路の verbose に Region: 行が出る (#810 round-2 #3 wiring pin).

    run_split 側 (`test_verbose_cache_miss_prints_region_line`) と対の detect 版。
    """
    from allaganeye.video.capture_region import FULL_FRAME, RegionTimeline

    def fake_run_detection(*args, **kwargs):
        cb = kwargs.get("region_callback")
        assert cb is not None, (
            "run_detect must pass region_callback to _run_detection (#810)"
        )
        cb(RegionTimeline(coarse=FULL_FRAME))
        return BOUNDARIES

    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0, no_cache=True)
    with (
        patch(f"{MODULE_DETECT}.probe_video", return_value=PROBE_RESULT),
        patch(f"{MODULE_DETECT}._run_detection", side_effect=fake_run_detection),
    ):
        run_detect(Path("input.mp4"), config, verbose=True)
    out = capsys.readouterr().out
    assert "Region: full_frame" in out


def test_detect_verbose_cache_miss_summary_includes_masked_token(tmp_path, capsys):
    """detect の cache-miss verbose summary に masked token が出る (vtuber と同型)."""
    config = SplitConfig(
        output_dir=tmp_path, min_match_duration=60.0, no_cache=True, masked=True
    )
    with (
        patch(f"{MODULE_DETECT}.probe_video", return_value=PROBE_RESULT),
        patch(f"{MODULE_DETECT}._run_detection", return_value=BOUNDARIES),
    ):
        run_detect(Path("input.mp4"), config, verbose=True)
    out = capsys.readouterr().out
    assert "masked=on" in out

    config_off = SplitConfig(
        output_dir=tmp_path, min_match_duration=60.0, no_cache=True
    )
    with (
        patch(f"{MODULE_DETECT}.probe_video", return_value=PROBE_RESULT),
        patch(f"{MODULE_DETECT}._run_detection", return_value=BOUNDARIES),
    ):
        run_detect(Path("input.mp4"), config_off, verbose=True)
    out = capsys.readouterr().out
    assert "masked=off" in out


def test_detect_records_masked_fallback_used(tmp_path):
    """detect 経路でも resolved path が metadata に記録される (run_split と同型)."""

    def fake_run_detection(*args, **kwargs):
        cb = kwargs.get("masked_fallback_callback")
        assert cb is not None, (
            "run_detect must pass masked_fallback_callback to _run_detection"
        )
        cb()
        return BOUNDARIES

    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0, no_cache=True)
    with (
        patch(f"{MODULE_DETECT}.probe_video", return_value=PROBE_RESULT),
        patch(f"{MODULE_DETECT}._run_detection", side_effect=fake_run_detection),
    ):
        run_detect(Path("input.mp4"), config, quiet=True)

    payload = json.loads((tmp_path / "metadata.json").read_text("utf-8"))
    assert payload["detection_params"]["masked"] is False
    assert payload["detection_params"]["masked_fallback_used"] is True


def test_detect_writes_system_info_to_metadata(tmp_path, monkeypatch):
    """#591 -- detect で書き出した metadata.json に system_info が含まれる."""
    monkeypatch.setattr(
        "allaganeye.system_info.probe_gpu_vendors",
        lambda: ["nvidia", "amd"],
    )
    probe, detect = _mock_detect_only(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    with probe, detect:
        run_detect(Path("input.mp4"), config, quiet=True)

    payload = json.loads((tmp_path / "metadata.json").read_text("utf-8"))
    assert "system_info" in payload
    info = payload["system_info"]
    assert info["gpu_vendors_available"] == ["nvidia", "amd"]
    # detect は h264 codec -> use_gpu=True で auto 選択 -> vendor=nvidia
    assert info["gpu_vendor_used"] == "nvidia"
    assert info["vendor_preference"] == ["nvidia", "amd", "intel"]


def test_detect_records_vendor_used_null_when_cpu_forced(tmp_path, monkeypatch):
    """#591 -- --no-gpu (use_gpu=False) では vendor_used=None だが available は埋まる."""
    monkeypatch.setattr(
        "allaganeye.system_info.probe_gpu_vendors",
        lambda: ["nvidia"],
    )
    probe, detect = _mock_detect_only(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0, use_gpu=False)
    with probe, detect:
        run_detect(Path("input.mp4"), config, quiet=True)

    payload = json.loads((tmp_path / "metadata.json").read_text("utf-8"))
    info = payload["system_info"]
    assert info["gpu_vendor_used"] is None
    assert info["gpu_vendors_available"] == ["nvidia"]


def test_detect_cache_hit_records_vendor_used_null(tmp_path, monkeypatch):
    """#591 -- cache hit でも system_info を書く (vendor_used=None, probe は実行)."""
    monkeypatch.setattr(
        "allaganeye.system_info.probe_gpu_vendors",
        lambda: ["intel"],
    )
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    with (
        patch(f"{MODULE_DETECT}.probe_video", return_value=PROBE_RESULT),
        patch(
            f"{MODULE_DETECT}._load_cache_hit",
            return_value=CacheHit(
                boundaries=BOUNDARIES, masked_fallback_used=False, capture_regions=None
            ),
        ),
    ):
        run_detect(Path("input.mp4"), config, quiet=True)

    payload = json.loads((tmp_path / "metadata.json").read_text("utf-8"))
    info = payload["system_info"]
    assert info["gpu_vendor_used"] is None  # cache hit で detect していない
    assert info["gpu_vendors_available"] == ["intel"]


# ---------------------------------------------------------------------------
# #569 -- GUI integration: --progress-format json + brightness_samples
# ---------------------------------------------------------------------------


def test_build_brightness_samples_downsamples_to_target():
    """`build_brightness_samples` should keep the array under the target."""
    raw = {float(i): float(i % 256) for i in range(2048)}
    out = build_brightness_samples(raw, target_samples=512)
    assert out is not None
    values = out["values"]
    assert isinstance(values, list)
    assert len(values) <= 512
    # Stride must be deterministic and >= 1.
    interval_s = out["interval_s"]
    assert isinstance(interval_s, float)
    assert interval_s >= 1.0


def test_build_brightness_samples_returns_none_for_empty():
    assert build_brightness_samples({}) is None


def test_build_brightness_samples_preserves_order_and_values():
    """Values must come out in timestamp order (sorted by key)."""
    raw = {2.0: 50.0, 0.0: 10.0, 1.0: 30.0}
    out = build_brightness_samples(raw, target_samples=10)
    assert out is not None
    assert out["values"] == [10.0, 30.0, 50.0]
    assert out["interval_s"] == 1.0


def test_detect_json_progress_emits_lifecycle_events(tmp_path, capsys):
    """``--progress-format json`` produces start/probing/done JSON lines."""
    probe, detect = _mock_detect_only(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    with probe, detect:
        run_detect(
            Path("input.mp4"),
            config,
            quiet=False,
            progress_format="json",
        )

    captured = capsys.readouterr().out
    lines = [json.loads(line) for line in captured.splitlines() if line.strip()]
    phases = [e["phase"] for e in lines]
    # Always emits start (first) and done (last). probing fires after probe_video.
    assert phases[0] == "start"
    assert phases[-1] == "done"
    assert "probing" in phases
    # `done` must include the metadata path so the GUI can load_metadata.
    done = next(e for e in lines if e["phase"] == "done")
    assert done["metadata_path"].endswith("metadata.json")
    assert done["matches"] == len(BOUNDARIES)


def test_detect_json_progress_suppresses_human_text(tmp_path, capsys):
    """json mode must not interleave ``Probing:`` / ``Metadata:`` with JSON.

    The GUI's stdout parser scans line-by-line and skips non-JSON
    lines, but a regression that puts a stray text line between two
    JSON events would still confuse the eyeballed log view.
    """
    probe, detect = _mock_detect_only(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    with probe, detect:
        run_detect(
            Path("input.mp4"),
            config,
            quiet=False,
            progress_format="json",
        )

    captured = capsys.readouterr().out
    for raw in captured.splitlines():
        line = raw.strip()
        if not line:
            continue
        # Every non-blank stdout line must parse as JSON in json mode.
        json.loads(line)


def test_detect_text_mode_still_writes_human_status(tmp_path, capsys):
    probe, detect = _mock_detect_only(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    with probe, detect:
        run_detect(
            Path("input.mp4"),
            config,
            quiet=False,
            progress_format="text",
        )

    captured = capsys.readouterr().out
    assert "Probing:" in captured
    assert "Metadata:" in captured


def test_detect_writes_brightness_samples_when_callback_fires(tmp_path):
    """When detection emits brightness, metadata.json carries the timeline."""

    def _detect_with_brightness(*args, **kwargs):
        cb = kwargs.get("brightness_callback")
        if cb is not None:
            # Synthesize a tiny brightness map that simulates Pass 1 output.
            cb({0.0: 80.0, 1.0: 12.0, 2.0: 90.0, 3.0: 88.0})
        return BOUNDARIES

    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    with (
        patch(f"{MODULE_DETECT}.probe_video", return_value=PROBE_RESULT),
        patch(
            f"{MODULE_DETECT}._run_detection",
            side_effect=_detect_with_brightness,
        ),
    ):
        run_detect(Path("input.mp4"), config, quiet=True)

    payload = json.loads((tmp_path / "metadata.json").read_text("utf-8"))
    assert "brightness_samples" in payload
    samples = payload["brightness_samples"]
    assert samples["values"] == [80.0, 12.0, 90.0, 88.0]
    assert samples["interval_s"] == 1.0


def test_detect_omits_brightness_samples_when_callback_silent(tmp_path):
    """No brightness data -> field is absent (don't write {values: []})."""
    probe, detect = _mock_detect_only(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    with probe, detect:
        run_detect(Path("input.mp4"), config, quiet=True)

    payload = json.loads((tmp_path / "metadata.json").read_text("utf-8"))
    assert "brightness_samples" not in payload


# #805 段階2 -- post_match_trailing_dropped warning emission stopped (W1)


def test_detect_does_not_pass_trailing_drop_callback(tmp_path):
    """detect 経路は trailing_drop_callback を `_run_detection` に渡さず、
    warnings は emit されない (#805 段階2 W1)。

    post_match flag が warning を代替したため callback チェーンは除去された。
    callback kwarg が渡らないこと + payload の warnings が [] であることを assert。
    """

    def _detect_no_callback(*args, **kwargs):
        assert "trailing_drop_callback" not in kwargs, (
            "run_detect must NOT pass trailing_drop_callback to _run_detection "
            "(#805 段階2: callback removed, post_match flag replaces it)"
        )
        return BOUNDARIES

    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    with (
        patch(f"{MODULE_DETECT}.probe_video", return_value=PROBE_RESULT),
        patch(
            f"{MODULE_DETECT}._run_detection",
            side_effect=_detect_no_callback,
        ),
    ):
        run_detect(Path("input.mp4"), config, quiet=True)

    payload = json.loads((tmp_path / "metadata.json").read_text("utf-8"))
    assert payload["warnings"] == []


def test_detect_no_trailing_drop_writes_empty_warnings(tmp_path):
    """callback 不発 (drop なし) なら detect の warnings は [] (#805 段階1)。"""
    probe, detect = _mock_detect_only(tmp_path)
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    with probe, detect:
        run_detect(Path("input.mp4"), config, quiet=True)

    payload = json.loads((tmp_path / "metadata.json").read_text("utf-8"))
    assert payload["warnings"] == []


def test_detect_carries_post_match_flag_to_metadata(tmp_path):
    """detect 経路が post_match-flagged boundary を非破壊で metadata に搬送する (#805 段階2).

    detector の `_flag_post_match_trailing` が最終 segment に post_match=True を
    立てて返すと、run_detect はそれを active から分離し、output_file 無しの
    post_match Match として metadata に書く。active match は従来どおり
    placeholder output_file を持つ。
    """
    boundaries_with_post: list[MatchBoundary] = [
        {"start": 0.0, "end": 600.0, "type": "fl_match"},
        {"start": 600.0, "end": 700.0, "type": "unknown", "post_match": True},
    ]
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    with (
        patch(f"{MODULE_DETECT}.probe_video", return_value=PROBE_RESULT),
        patch(f"{MODULE_DETECT}._run_detection", return_value=boundaries_with_post),
    ):
        run_detect(Path("input.mp4"), config, quiet=True)

    payload = json.loads((tmp_path / "metadata.json").read_text("utf-8"))
    matches = payload["matches"]
    assert len(matches) == 2

    # active match: placeholder output_file 有り、post_match flag 無し。
    active = matches[0]
    assert active["index"] == 1
    assert active["output_file"] == "match_001.mp4"
    assert "post_match" not in active

    # post_match match: flag True、output_file 無し、index は active の後 (2)。
    trailing = matches[1]
    assert trailing["post_match"] is True
    assert "output_file" not in trailing
    assert trailing["index"] == 2


# ---------------------------------------------------------------------------
# #810 -- capture_regions wiring through run_detect
# ---------------------------------------------------------------------------


def test_detect_writes_capture_regions_fresh(tmp_path):
    """#810 -- fresh detection: region_callback 経由で capture_regions を書く。"""
    from allaganeye.video.capture_region import FULL_FRAME, RegionTimeline

    def fake_run_detection(*args, **kwargs):
        cb = kwargs.get("region_callback")
        assert cb is not None, (
            "run_detect must pass region_callback to _run_detection (#810)"
        )
        cb(RegionTimeline(coarse=FULL_FRAME))
        return BOUNDARIES

    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    with (
        patch(f"{MODULE_DETECT}.probe_video", return_value=PROBE_RESULT),
        patch(f"{MODULE_DETECT}._run_detection", side_effect=fake_run_detection),
    ):
        run_detect(Path("input.mp4"), config, quiet=True)

    payload = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    regions = payload["capture_regions"]
    assert regions["coarse"]["source"] == "fallback"
    assert regions["coarse"]["x"] == 0.0 and regions["coarse"]["w"] == 1.0
    assert regions["segments"] == []
    assert regions["fallback_reason"] is None


def test_detect_cache_hit_carries_capture_regions(tmp_path):
    """#810 -- cache-hit: cache 記録値が metadata.json へ引き継がれる。

    `_load_cache_hit` を patch して CacheHit (with capture_regions) を返す (#879)。
    """
    band_regions: CaptureRegions = {
        "coarse": {
            "x": 0.1,
            "y": 0.0,
            "w": 0.76,
            "h": 0.042,
            "confidence": 0.9,
            "source": "band",
        },
        "segments": [],
        "fallback_reason": None,
    }
    config = SplitConfig(output_dir=tmp_path, min_match_duration=60.0)
    with (
        patch(f"{MODULE_DETECT}.probe_video", return_value=PROBE_RESULT),
        patch(
            f"{MODULE_DETECT}._load_cache_hit",
            return_value=CacheHit(
                boundaries=BOUNDARIES,
                masked_fallback_used=False,
                capture_regions=band_regions,
            ),
        ),
        patch(f"{MODULE_DETECT}._run_detection") as mock_detect,
    ):
        run_detect(Path("input.mp4"), config, quiet=True)

    mock_detect.assert_not_called()
    payload = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    assert payload["capture_regions"] == band_regions
