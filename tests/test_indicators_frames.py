"""Tests for the frame reader behind `allaganeye indicators` (#1106)."""

from __future__ import annotations

from pathlib import Path

import pytest

from allaganeye.video.frames import build_frame_command


def _index_of(command: list[str], token: str) -> int:
    return command.index(token)


def test_command_puts_ss_before_i(tmp_path: Path) -> None:
    """`-ss` は `-i` の前 (入力シーク) でなければ精度が出ない。"""
    video = tmp_path / "in.mp4"
    command = build_frame_command(video, fps=10.0, start=493.2)
    assert _index_of(command, "-ss") < _index_of(command, "-i")
    assert command[_index_of(command, "-ss") + 1] == "493.200"


def test_command_puts_t_after_i(tmp_path: Path) -> None:
    """`-t` は `-i` の後に置く。

    入力側の `-t` は出力タイムスタンプをずらす (実測で GOP 分ずれた)。
    引数の順序が変わると全フレームの時刻が静かにずれるので、ここで固定する。
    """
    video = tmp_path / "in.mp4"
    command = build_frame_command(video, fps=10.0, start=10.0, duration=5.0)
    assert _index_of(command, "-t") > _index_of(command, "-i")
    assert command[_index_of(command, "-t") + 1] == "5.000"


def test_command_omits_t_without_duration(tmp_path: Path) -> None:
    command = build_frame_command(tmp_path / "in.mp4", fps=2.0)
    assert "-t" not in command


def test_command_streams_raw_gray(tmp_path: Path) -> None:
    command = build_frame_command(tmp_path / "in.mp4", fps=10.0)
    assert command[-1] == "-"
    assert command[command.index("-f") + 1] == "rawvideo"
    assert command[command.index("-pix_fmt") + 1] == "gray"
    assert command[command.index("-vf") + 1] == "fps=10.0"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"fps": 0.0}, "fps"),
        ({"fps": -1.0}, "fps"),
        ({"fps": 1.0, "start": -0.5}, "start"),
        ({"fps": 1.0, "duration": 0.0}, "duration"),
        ({"fps": 1.0, "duration": -2.0}, "duration"),
    ],
)
def test_command_rejects_invalid_arguments(
    tmp_path: Path, kwargs: dict, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        build_frame_command(tmp_path / "in.mp4", **kwargs)
