"""Tests for the ``allaganeye detect`` command (#463)."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from allaganeye.commands.detect import run_detect
from allaganeye.commands.split_matches import build_brightness_samples
from allaganeye.config import SplitConfig
from allaganeye.exceptions import DetectionError
from allaganeye.video.detector import MatchBoundary
from allaganeye.video.probe import ProbeResult

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
        patch(f"{MODULE_DETECT}._load_cache", return_value=BOUNDARIES),
        patch(f"{MODULE_DETECT}._run_detection") as mock_detect,
    ):
        run_detect(Path("input.mp4"), config, quiet=True)

    mock_detect.assert_not_called()
    assert (tmp_path / "metadata.json").exists()


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
        patch(f"{MODULE_DETECT}._load_cache", return_value=BOUNDARIES),
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
