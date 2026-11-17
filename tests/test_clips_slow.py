"""Slow real-video test: `allaganeye clips` が実際に動画を切り抜ける (#135).

サンプル録画 (`ALLAGANEYE_SAMPLE_VIDEO_DIR/20260116/20260116_1.mp4`) の
KO 区間 493.4 秒を含む metadata を作り、`clips` で 1 本書き出して ffprobe で
長さを測る。`copy` はキーフレームに丸められるので長さは厳密一致しない
（ずれの上限だけを見る）。`h264` は再エンコードなので指定長に一致する。

Missing-video policy: サンプル動画 / ffmpeg が無い環境では skip。
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from allaganeye.commands import clips as clips_cmd
from allaganeye.ffmpeg_path import find_ffmpeg

pytestmark = pytest.mark.slow

EVENT_TIMESTAMP = 493.4
PRE = 2.0
POST = 2.0
EXPECTED_LENGTH = PRE + POST + 1.5  # イベント区間 1.5 秒 + 前後マージン
COPY_TOLERANCE = 2.5  # キーフレーム間隔（OBS 録画で通常 2 秒）+ 余裕
H264_TOLERANCE = 0.6

runner = CliRunner()


def _sample_video() -> Path:
    env = os.environ.get("ALLAGANEYE_SAMPLE_VIDEO_DIR")
    if not env:
        pytest.skip("ALLAGANEYE_SAMPLE_VIDEO_DIR not set")
    video = Path(env) / "20260116" / "20260116_1.mp4"
    if not video.is_file():
        pytest.skip(f"sample video not found: {video}")
    if find_ffmpeg() is None:
        pytest.skip("ffmpeg not found")
    return video


def _metadata(tmp_path: Path, video: Path) -> Path:
    payload = {
        "schema_version": "1",
        "source": str(video),
        "source_duration": 944.0,
        "source_duration_display": "15:44",
        "detected_at": "2026-11-16T00:00:00Z",
        "detection_params": {"sample_interval": 2.0},
        "matches": [{"index": 1, "start_time": 0.0, "end_time": 944.0}],
        "gaps": [],
        "events": [
            {
                "signal_id": "ko_indicator",
                "timestamp": EVENT_TIMESTAMP,
                "end": EVENT_TIMESTAMP + 1.5,
                "score": 0.93,
                "evidence": {"samples": 15},
                "match_index": 1,
            }
        ],
    }
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _duration(path: Path) -> float:
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    # find_ffmpeg returns the ffmpeg binary; ffprobe sits next to it.
    ffprobe = Path(ffmpeg).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
    if not ffprobe.is_file():
        ffprobe = Path("ffprobe")
    out = subprocess.run(
        [
            str(ffprobe),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(out.stdout.strip())


@pytest.mark.parametrize(
    ("codec", "tolerance"),
    [("copy", COPY_TOLERANCE), ("h264", H264_TOLERANCE)],
)
def test_clips_writes_a_playable_clip(
    tmp_path: Path, codec: str, tolerance: float
) -> None:
    video = _sample_video()
    metadata = _metadata(tmp_path, video)
    app = typer.Typer()

    @app.callback()
    def _() -> None:
        pass

    clips_cmd.register(app)

    result = runner.invoke(
        app,
        [
            "clips",
            str(metadata),
            "--pre",
            str(PRE),
            "--post",
            str(POST),
            "--codec",
            codec,
            "-o",
            str(tmp_path / "out"),
        ],
    )
    assert result.exit_code == 0, result.output

    outputs = sorted((tmp_path / "out").glob("*.mp4"))
    assert len(outputs) == 1, outputs
    assert outputs[0].stat().st_size > 0
    duration = _duration(outputs[0])
    assert abs(duration - EXPECTED_LENGTH) <= tolerance, (duration, EXPECTED_LENGTH)
