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


# ---------------------------------------------------------------------------
# デコーダ異常の検出 (Codex adversarial-review)
# ---------------------------------------------------------------------------


class _FakeStdout:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)

    def read(self, _size: int) -> bytes:
        return self._chunks.pop(0) if self._chunks else b""

    def close(self) -> None:
        pass


class _FakeProcess:
    def __init__(self, chunks: list[bytes], returncode: int) -> None:
        self.stdout = _FakeStdout(chunks)
        self.returncode = returncode
        self.killed = False

    def poll(self) -> int | None:
        return None if self.stdout._chunks else self.returncode

    def kill(self) -> None:
        self.killed = True

    def wait(self) -> int:
        return self.returncode


def _run_fake(monkeypatch: pytest.MonkeyPatch, proc: _FakeProcess):
    from allaganeye.video import frames

    monkeypatch.setattr(frames.subprocess, "Popen", lambda *a, **k: proc)
    monkeypatch.setattr(frames, "find_ffmpeg", lambda: "ffmpeg")
    return list(frames.iter_gray_frames(Path("in.mp4"), fps=10.0, frame_size=(4, 2)))


def test_iter_reports_decoder_failure_after_partial_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """途中まで読めた場合もデコーダ異常は握り潰さない。

    ここを「0 フレームのときだけ raise」にすると、途中で死んだデコードが
    「正常終了 + 途中までのイベント」として publish される。
    """
    from allaganeye.exceptions import VideoProcessingError

    frame = bytes(8)
    proc = _FakeProcess([frame, frame], returncode=1)
    with pytest.raises(VideoProcessingError, match="ffmpeg"):
        _run_fake(monkeypatch, proc)


def test_iter_rejects_truncated_final_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """半端な最終フレームは捨てずにエラーにする (不完全なデータで成功と言わない)。"""
    from allaganeye.exceptions import VideoProcessingError

    proc = _FakeProcess([bytes(8), bytes(3)], returncode=0)
    with pytest.raises(VideoProcessingError, match="truncated"):
        _run_fake(monkeypatch, proc)


def test_iter_accepts_clean_eof(monkeypatch: pytest.MonkeyPatch) -> None:
    """通常の EOF (0 バイト + exit 0) はエラーにしない。"""
    proc = _FakeProcess([bytes(8), bytes(8)], returncode=0)
    frames = _run_fake(monkeypatch, proc)
    assert [timestamp for timestamp, _ in frames] == [0.0, 0.1]


def test_iter_translates_launch_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """ffmpeg を起動できない (壊れた exe / 実行権限なし) ときも traceback にしない。

    `Popen` の `OSError` は `AllaganEyeError` 系に乗らないため、そのままでは
    exit 3 にならず CLI の `--json` にも error 行が出ない。
    """
    from allaganeye.exceptions import VideoProcessingError
    from allaganeye.video import frames

    def boom(*_args: object, **_kwargs: object) -> object:
        raise OSError(22, "not executable")

    monkeypatch.setattr(frames.subprocess, "Popen", boom)
    monkeypatch.setattr(frames, "find_ffmpeg", lambda: "ffmpeg")
    with pytest.raises(VideoProcessingError, match="ffmpeg"):
        list(frames.iter_gray_frames(Path("in.mp4"), fps=10.0, frame_size=(4, 2)))


def test_iter_does_not_kill_after_clean_eof(monkeypatch: pytest.MonkeyPatch) -> None:
    """stdout が EOF でもプロセスが未 reap のことがある。ここで kill しない。

    ffmpeg は終了処理で stdout を先に閉じるため、`poll()` が None でも
    正常終了している場合がある。kill すると exit -9 を「失敗」と誤判定する。
    """

    class _AlwaysRunning(_FakeProcess):
        def poll(self) -> int | None:
            return None

    running = _AlwaysRunning([bytes(8)], returncode=0)
    frames = _run_fake(monkeypatch, running)
    assert len(frames) == 1
    assert running.killed is False
