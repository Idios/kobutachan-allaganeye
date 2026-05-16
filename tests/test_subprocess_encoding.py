"""#656 -- subprocess.run(text=True) is encoding='utf-8', errors='replace' を明示する.

Windows OS default encoding (cp932) は ffmpeg/ffprobe の UTF-8 stderr を decode できず、
日本語含む path で UnicodeDecodeError を起こす。本 test は全 ``subprocess.run(text=True, ...)``
呼び出しで ``encoding='utf-8'`` + ``errors='replace'`` が指定されていることを mock で pin する。
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from allaganeye.commands.split_matches import _probe_ffmpeg_version
from allaganeye.system_info import _run_text
from allaganeye.video.probe import probe_video
from allaganeye.video.splitter import _ffmpeg_split


def _make_run_capture(
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
) -> tuple[Any, dict[str, Any]]:
    """Return a fake ``subprocess.run`` + dict to capture kwargs."""
    captured: dict[str, Any] = {}

    def fake_run(*args: Any, **kwargs: Any) -> MagicMock:
        captured["args"] = args
        captured["kwargs"] = kwargs
        result = MagicMock()
        result.stdout = stdout
        result.stderr = stderr
        result.returncode = returncode
        return result

    return fake_run, captured


def _assert_utf8_encoding(captured: dict[str, Any], where: str) -> None:
    kwargs = captured.get("kwargs", {})
    assert kwargs.get("encoding") == "utf-8", f"{where}: encoding='utf-8' 必須 (#656)"
    assert kwargs.get("errors") == "replace", f"{where}: errors='replace' 必須 (#656)"
    assert kwargs.get("text") is True, f"{where}: text=True 維持"


def test_probe_video_uses_utf8_encoding(tmp_path: Path) -> None:
    """probe_video の subprocess.run は encoding='utf-8', errors='replace' を渡す (#656)."""
    video = tmp_path / "テスト.mp4"
    video.write_bytes(b"")
    fake_run, captured = _make_run_capture(
        stdout='{"format": {"duration": "10.0"}, "streams": []}'
    )
    # Probe の戻り値組み立てが内部で stream/format を要求しても、
    # subprocess.run の kwargs は captured 済み (mock 直後に書き込まれる) なので
    # 後段の例外は suppress する。
    with (
        patch("allaganeye.video.probe.find_ffprobe", return_value="ffprobe"),
        patch("allaganeye.video.probe.subprocess.run", side_effect=fake_run),
        contextlib.suppress(Exception),
    ):
        probe_video(video)
    _assert_utf8_encoding(captured, "probe.py")


def test_ffmpeg_split_uses_utf8_encoding(tmp_path: Path) -> None:
    """splitter._ffmpeg_split の subprocess.run は encoding='utf-8' を渡す (#656)."""
    input_path = tmp_path / "テスト.mp4"
    input_path.write_bytes(b"")
    output = tmp_path / "out.mp4"
    fake_run, captured = _make_run_capture(returncode=0)
    with (
        patch("allaganeye.video.splitter.find_ffmpeg", return_value="ffmpeg"),
        patch("allaganeye.video.splitter.subprocess.run", side_effect=fake_run),
        contextlib.suppress(Exception),
    ):
        _ffmpeg_split(input_path, start=0.0, end=1.0, output=output)
    _assert_utf8_encoding(captured, "splitter.py")


def test_run_text_uses_utf8_encoding() -> None:
    """system_info._run_text の subprocess.run は encoding='utf-8' を渡す (#656)."""
    fake_run, captured = _make_run_capture(stdout="ok")
    with patch("allaganeye.system_info.subprocess.run", side_effect=fake_run):
        _run_text(["dummy"])
    _assert_utf8_encoding(captured, "system_info.py")


def test_probe_ffmpeg_version_uses_utf8_encoding() -> None:
    """split_matches._probe_ffmpeg_version の subprocess.run は encoding='utf-8' を渡す (#656).

    関数内で ``import subprocess`` しているが、Python の import cache によって
    global ``subprocess`` module を共有する。``find_ffmpeg`` を mock し、
    ``subprocess.run`` を patch することで kwargs を捕捉する。
    """
    fake_run, captured = _make_run_capture(stdout="ffmpeg version 8.1\n")
    # split_matches.py:_probe_ffmpeg_version は関数 local で
    # ``from allaganeye.ffmpeg_path import find_ffmpeg`` / ``import subprocess`` するため、
    # 元の module の symbol を patch する (関数呼出ごとに re-resolve される)。
    with (
        patch("allaganeye.ffmpeg_path.find_ffmpeg", return_value="ffmpeg"),
        patch("subprocess.run", side_effect=fake_run),
    ):
        _probe_ffmpeg_version()
    _assert_utf8_encoding(captured, "split_matches.py")
