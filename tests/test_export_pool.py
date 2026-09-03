"""Tests for parallel export pool (#761).

Mocks run_export_attempt to focus on concurrency / cancel / partial
failure semantics. Codex review #3 enforces cancel-without-queue-size
condition.

Resolver-level path contract tests (containment / identity-collision
predicates on ``resolve_output_path`` / ``resolve_output_paths`` themselves)
live in ``tests/test_path_schema_contracts.py`` (#934 P1-3). What remains here
is pool *routing* (the ``test_pool_*`` tests, which prove ``export_matches``
actually reaches the shared resolver -- a different predicate from the
resolver's own contract) plus pool concurrency/cancel/failure behaviour.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from allaganeye.exceptions import ConfigValidationError
from allaganeye.export import pool as pool_module
from allaganeye.export.encoder import EncoderSlot, H264Encoder
from allaganeye.export.pool import (
    ExportMatch,
    _format_start_for_filename,
    _identity_key,
    export_matches,
)
from allaganeye.export.schema import ExportError, ExportResult
from tests.export_match_helpers import make_matches, make_pair


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0.0, "00-00"),
        (5.0, "00-05"),
        (65.0, "01-05"),
        (915.5, "15-15"),  # 15m15s
        (3599.0, "59-59"),
        (3600.0, "1-00-00"),  # 1h ちょうど
        (5021.5, "1-23-41"),  # 1h23m41s -- GUI formatStartForFilename と一致
        (-10.0, "00-00"),  # 負値は 0 clamp (GUI と同じ)
    ],
)
def test_format_start_matches_gui_h_mm_ss(seconds: float, expected: str):
    # P2-20: GUI ExportScreen.tsx formatStartForFilename と bit-identical。
    # 旧実装は通算分 (5021.5 -> "83-41") で 1h 以降に GUI プレビューと乖離した。
    assert _format_start_for_filename(seconds) == expected


def _slots(n: int) -> list[EncoderSlot]:
    return [
        EncoderSlot(
            slot_index=i, encoder_kind=H264Encoder.LIBX264, display_label=f"libx264#{i}"
        )
        for i in range(n)
    ]


def test_runs_n_workers_in_parallel(tmp_path: Path):
    """concurrency = len(slots): max in-flight workers = N."""
    in_flight = 0
    max_in_flight = 0
    lock = threading.Lock()

    def fake_run(*args: Any, **kwargs: Any) -> ExportResult:
        nonlocal in_flight, max_in_flight
        with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
        time.sleep(0.05)
        with lock:
            in_flight -= 1
        return ExportResult(
            match_index=-1,
            output_path=tmp_path / f"out_{kwargs.get('start', 0)}.mp4",
            duration_ms=50,
            encoder_used="libx264",
        )

    with patch("allaganeye.export.pool.run_export_attempt", side_effect=fake_run):
        summary = export_matches(
            matches=make_matches(10),
            slots=_slots(3),
            source_video=tmp_path / "in.mp4",
            output_dir=tmp_path,
            codec="h264",
            name_pattern="{idx:03}.mp4",
            progress_cb=lambda ev: None,
            cancel_event=threading.Event(),
        )
    assert summary.success == 10
    assert summary.failure == 0
    assert max_in_flight == 3  # never exceed slot count


def test_cancel_stops_remaining(tmp_path: Path):
    """cancel_event set -> workers stop pulling. summary.cancelled = True."""
    cancel = threading.Event()
    started = 0
    lock = threading.Lock()

    def fake_run(*args: Any, **kwargs: Any) -> ExportResult:
        nonlocal started
        with lock:
            started += 1
            if started == 2:
                cancel.set()
        time.sleep(0.02)
        if cancel.is_set():
            raise ExportError(kind="cancelled", message="user")
        return ExportResult(
            match_index=-1,
            output_path=tmp_path / "out.mp4",
            duration_ms=20,
            encoder_used="libx264",
        )

    with patch("allaganeye.export.pool.run_export_attempt", side_effect=fake_run):
        summary = export_matches(
            matches=make_matches(20),
            slots=_slots(2),
            source_video=tmp_path / "in.mp4",
            output_dir=tmp_path,
            codec="h264",
            name_pattern="{idx:03}.mp4",
            progress_cb=lambda ev: None,
            cancel_event=cancel,
        )
    assert summary.cancelled is True
    # All 20 matches must not all finish (cancelled mid-run)
    assert summary.success + summary.failure < 20


def test_cancel_marks_true_even_with_empty_queue(tmp_path: Path):
    """Codex review #3: when cancel_event fires after all items dequeued,
    queue.qsize() AND condition would yield cancelled=False (incorrect).
    Single cancel_event.is_set() check correctly reports cancelled=True."""
    cancel = threading.Event()
    lock = threading.Lock()
    n_done = 0

    def fake_run(*args: Any, **kwargs: Any) -> ExportResult:
        nonlocal n_done
        with lock:
            n_done += 1
            if n_done == 3:
                # set cancel immediately after all matches complete
                cancel.set()
        return ExportResult(
            match_index=-1,
            output_path=tmp_path / "out.mp4",
            duration_ms=10,
            encoder_used="libx264",
        )

    with patch("allaganeye.export.pool.run_export_attempt", side_effect=fake_run):
        summary = export_matches(
            matches=make_matches(3),
            slots=_slots(1),
            source_video=tmp_path / "in.mp4",
            output_dir=tmp_path,
            codec="h264",
            name_pattern="{idx:03}.mp4",
            progress_cb=lambda ev: None,
            cancel_event=cancel,
        )
    # All 3 succeed, but cancel_event is set so cancelled=True
    assert summary.success == 3
    assert summary.cancelled is True


def test_partial_failure_other_workers_continue(tmp_path: Path):
    """Other workers continue even when 1 worker returns a failure."""

    def fake_run(*args: Any, **kwargs: Any) -> ExportResult:
        if kwargs.get("start") == 10.0:  # match index 1
            raise ExportError(kind="ffmpeg.exit_failed", message="boom")
        return ExportResult(
            match_index=-1,
            output_path=tmp_path / "out.mp4",
            duration_ms=10,
            encoder_used="libx264",
        )

    with patch("allaganeye.export.pool.run_export_attempt", side_effect=fake_run):
        summary = export_matches(
            matches=make_matches(5),
            slots=_slots(2),
            source_video=tmp_path / "in.mp4",
            output_dir=tmp_path,
            codec="h264",
            name_pattern="{idx:03}.mp4",
            progress_cb=lambda ev: None,
            cancel_event=threading.Event(),
        )
    assert summary.success == 4
    assert summary.failure == 1
    assert summary.cancelled is False


def test_empty_queue_returns_zero_summary(tmp_path: Path):
    summary = export_matches(
        matches=[],
        slots=_slots(3),
        source_video=tmp_path / "in.mp4",
        output_dir=tmp_path,
        codec="h264",
        name_pattern="{idx:03}.mp4",
        progress_cb=lambda ev: None,
        cancel_event=threading.Event(),
    )
    assert summary.success == 0
    assert summary.failure == 0
    assert summary.cancelled is False


def test_empty_slots_raises(tmp_path: Path):
    """0 slots is not executable -> ValueError (caller bug)."""
    with pytest.raises(ValueError):
        export_matches(
            matches=make_matches(1),
            slots=[],
            source_video=tmp_path / "in.mp4",
            output_dir=tmp_path,
            codec="h264",
            name_pattern="{idx:03}.mp4",
            progress_cb=lambda ev: None,
            cancel_event=threading.Event(),
        )


# ---------------------------------------------------------------------------
# B1: --name-pattern sandbox (data loss)
#
# ``output_dir / rendered_name`` lets any pattern (or any metadata-supplied
# ``{type}`` value) escape ``-o`` via ``..`` / an absolute path / a
# drive-relative path, silently overwriting an unrelated file -- with exit 0.
# The predicate is the RESOLVED path, never the pattern string.
# ---------------------------------------------------------------------------


def _explode(*args: Any, **kwargs: Any) -> ExportResult:
    raise AssertionError(
        "run_export_attempt must not be reached for a rejected name pattern"
    )


def _run_pool(
    tmp_path: Path,
    *,
    pattern: str,
    matches: list[ExportMatch] | None = None,
    output_dir: Path | None = None,
    source_video: Path | None = None,
):
    return export_matches(
        matches=make_matches(1) if matches is None else matches,
        slots=_slots(1),
        source_video=source_video or (tmp_path / "in.mp4"),
        output_dir=output_dir if output_dir is not None else tmp_path / "out",
        codec="h264",
        name_pattern=pattern,
        progress_cb=lambda ev: None,
        cancel_event=threading.Event(),
    )


@pytest.mark.parametrize(
    "pattern",
    [
        "../victim.mp4",
        "../../victim.mp4",
        "sub/../../victim.mp4",
        "{idx:03}/../../victim.mp4",
    ],
)
def test_pool_rejects_parent_traversal_pattern(tmp_path: Path, pattern: str):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    with patch("allaganeye.export.pool.run_export_attempt", side_effect=_explode):
        with pytest.raises(ConfigValidationError):
            _run_pool(tmp_path, pattern=pattern, output_dir=out_dir)


@pytest.mark.skipif(
    sys.platform != "win32", reason="backslash separator is Windows-only"
)
def test_pool_rejects_backslash_traversal_pattern(tmp_path: Path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    with patch("allaganeye.export.pool.run_export_attempt", side_effect=_explode):
        with pytest.raises(ConfigValidationError):
            _run_pool(tmp_path, pattern="..\\victim.mp4", output_dir=out_dir)


def test_pool_rejects_absolute_pattern(tmp_path: Path):
    """An absolute pattern ignores -o entirely (Path.__truediv__ semantics)."""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    absolute = str(tmp_path / "victim.mp4")
    with patch("allaganeye.export.pool.run_export_attempt", side_effect=_explode):
        with pytest.raises(ConfigValidationError):
            _run_pool(tmp_path, pattern=absolute, output_dir=out_dir)


@pytest.mark.skipif(
    sys.platform != "win32", reason="drive-relative paths are Windows-only"
)
def test_pool_rejects_drive_relative_pattern(tmp_path: Path):
    """``D:victim.mp4`` is resolved against D:'s own CWD, not against -o.

    The drive letter must differ from -o's: a *same-drive* drive-relative name
    (``C:x.mp4`` under a C: output dir) joins inside the sandbox and stays
    legal, which is exactly the behaviour Windows itself has.
    """
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    other_drive = "Z:" if out_dir.drive.upper() != "Z:" else "Y:"
    with patch("allaganeye.export.pool.run_export_attempt", side_effect=_explode):
        with pytest.raises(ConfigValidationError):
            _run_pool(tmp_path, pattern=f"{other_drive}victim.mp4", output_dir=out_dir)


def test_pool_rejects_escape_via_type_token(tmp_path: Path):
    """The escape can come from metadata, not from the pattern string.

    ``{type}`` is an unvalidated metadata value, so a pattern that looks
    perfectly safe ({idx:03} + no separators) still escapes. Pattern-string
    validation cannot catch this -- only the resolved path can.
    """
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    evil = [
        ExportMatch(
            index=1, start=0.0, end=10.0, type_label="../../../victim"
        )  # -> out/001_../../../victim.mp4 -> tmp_path.parent/victim.mp4
    ]
    with patch("allaganeye.export.pool.run_export_attempt", side_effect=_explode):
        with pytest.raises(ConfigValidationError):
            _run_pool(
                tmp_path,
                pattern="{idx:03}_{type}.mp4",
                matches=evil,
                output_dir=out_dir,
            )


def test_pool_rejects_pattern_resolving_to_source_video(tmp_path: Path):
    """-o pointed at the source's own directory must not overwrite the source."""
    source = tmp_path / "in.mp4"
    source.write_bytes(b"SOURCE")
    with patch("allaganeye.export.pool.run_export_attempt", side_effect=_explode):
        with pytest.raises(ConfigValidationError):
            _run_pool(
                tmp_path,
                pattern="in.mp4",
                output_dir=tmp_path,
                source_video=source,
            )
    assert source.read_bytes() == b"SOURCE"


@pytest.mark.skipif(sys.platform != "win32", reason="NTFS is case-insensitive")
def test_pool_rejects_source_collision_case_insensitively(tmp_path: Path):
    source = tmp_path / "in.mp4"
    source.write_bytes(b"SOURCE")
    with patch("allaganeye.export.pool.run_export_attempt", side_effect=_explode):
        with pytest.raises(ConfigValidationError):
            _run_pool(
                tmp_path,
                pattern="IN.MP4",
                output_dir=tmp_path,
                source_video=source,
            )


def test_pool_accepts_plain_pattern_inside_output_dir(tmp_path: Path):
    """Reverse pin: a normal pattern keeps working, unchanged (no over-reject)."""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    seen: list[Path] = []

    def fake_run(*args: Any, **kwargs: Any) -> ExportResult:
        seen.append(kwargs["output"])
        return ExportResult(
            match_index=-1,
            output_path=kwargs["output"],
            duration_ms=1,
            encoder_used="libx264",
        )

    with patch("allaganeye.export.pool.run_export_attempt", side_effect=fake_run):
        summary = _run_pool(
            tmp_path,
            pattern="{idx:03}_{type}_{start}.mp4",
            matches=make_matches(2),
            output_dir=out_dir,
        )
    assert summary.success == 2
    assert sorted(p.name for p in seen) == [
        "000_match_00-00.mp4",
        "001_match_00-10.mp4",
    ]
    assert all(p.parent == out_dir for p in seen)


def test_pool_accepts_subdirectory_pattern(tmp_path: Path):
    """Reverse pin: a pattern that stays inside -o is NOT rejected.

    A sub-directory pattern is inside the sandbox, so the guard leaves it to
    ffmpeg exactly as before (which fails on the missing dir -- unchanged
    behaviour). The guard must reject escapes only.
    """
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    with patch(
        "allaganeye.export.pool.run_export_attempt",
        side_effect=lambda *a, **kw: ExportResult(
            match_index=-1,
            output_path=kw["output"],
            duration_ms=1,
            encoder_used="libx264",
        ),
    ):
        summary = _run_pool(tmp_path, pattern="sub/{idx:03}.mp4", output_dir=out_dir)
    assert summary.success == 1


# --------------------------------------------------------------------------
# Output *identity* uniqueness (#930 follow-up).
#
# Containment and uniqueness are separate invariants. Two matches can render
# to different STRINGS that denote the SAME file; both then pass containment
# and both pass a string-keyed duplicate check, so both are written and one is
# silently lost while the summary still reports success.
#
# The batch resolver keys on the resolved Path, which is the file's identity:
# PurePath equality/hashing is case-insensitive on Windows, and ``resolve()``
# collapses ``sub/../name`` even when ``sub`` does not exist.
# --------------------------------------------------------------------------


@pytest.mark.skipif(
    sys.platform != "win32", reason="path identity is case-insensitive on Windows only"
)
def test_pool_rejects_case_only_identity_collision(tmp_path: Path):
    """export_matches is the last line of defence for preflight-less callers."""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    with patch("allaganeye.export.pool.run_export_attempt", side_effect=_explode):
        with pytest.raises(ConfigValidationError):
            _run_pool(
                tmp_path,
                pattern="{type}.mp4",
                matches=make_pair("Clip", "clip"),
                output_dir=out_dir,
            )


def test_pool_rejects_dotdot_identity_collision(tmp_path: Path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    with patch("allaganeye.export.pool.run_export_attempt", side_effect=_explode):
        with pytest.raises(ConfigValidationError):
            _run_pool(
                tmp_path,
                pattern="{type}.mp4",
                matches=make_pair("sub/../clip", "clip"),
                output_dir=out_dir,
            )


# --------------------------------------------------------------------------
# Win32 name folding (Codex adversarial-review, round 2)
#
# ``PurePath`` comparison models case-insensitivity, but it is a *string*
# model and stops there. Win32 also strips trailing dots and spaces from every
# path component before opening anything, so ``clip.mp4`` and ``clip.mp4.``
# compare unequal as paths yet name one file -- the exact shape of the bug
# this section is meant to close, one layer deeper.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "folded"),
    [
        ("clip.mp4.", "clip.mp4"),
        ("clip.mp4 ", "clip.mp4"),
        ("clip.mp4. . ", "clip.mp4"),
        ("clip.mp4", "clip.mp4"),  # nothing to strip -> unchanged
        ("...", "..."),  # dots-only: folding would invent an empty component
        (". ", ". "),
    ],
)
def test_identity_key_folding_runs_on_every_platform(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, raw: str, folded: str
):
    """The folding *logic* must be gated even where the OS does not fold.

    CI runs pytest on ubuntu-latest only (`.github/workflows/ci.yml`), so the
    ``skipif(sys.platform != "win32")`` tests in this section never execute
    there -- they gate nothing until Idios runs the suite locally. Driving the
    platform switch directly keeps the logic itself covered on every runner.
    The Windows-only tests stay: they pin the OS *premise*, which cannot be
    faked.
    """
    monkeypatch.setattr(pool_module, "_IS_WINDOWS", True)
    assert _identity_key(tmp_path / raw) == tmp_path / folded
    # ... and the anchor is never folded, only the components below it
    assert _identity_key(tmp_path / raw).anchor == tmp_path.anchor


def test_identity_key_folds_interior_directory_components(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """Interior components fold too -- see the premise test below for why.

    Codex round 3 read this as an over-rejection and recommended folding only
    the filename. That would reopen a real collision (``sub./a.mp4`` lands in
    ``sub/``), so the behaviour is pinned here deliberately.
    """
    monkeypatch.setattr(pool_module, "_IS_WINDOWS", True)
    assert _identity_key(tmp_path / "sub." / "a.mp4") == tmp_path / "sub" / "a.mp4"
    assert _identity_key(tmp_path / "sub " / "a.mp4") == tmp_path / "sub" / "a.mp4"


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 name-trimming premise")
def test_win32_directory_trailing_dot_and_space_premise(tmp_path: Path):
    """Pins the measurement the interior-component folding rests on.

    1. a trailing dot on a directory component really does alias -- so folding
       it is required, not optional
    2. a directory whose name ends in a space cannot exist at all (``mkdir``
       trims it), so the spelling that folding collapses never denotes a
       writable file and nothing addressable is lost
    """
    sub = tmp_path / "sub"
    sub.mkdir()
    (tmp_path / "sub." / "a.mp4").write_bytes(b"X")
    assert (sub / "a.mp4").exists(), "a trailing dot on a directory DOES alias"

    (tmp_path / "spaced ").mkdir()
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith("spaced")] == [
        "spaced"
    ], "a directory name ending in a space cannot exist"


def test_identity_key_is_a_no_op_off_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """POSIX keeps trailing dots/spaces significant -- folding would over-reject."""
    monkeypatch.setattr(pool_module, "_IS_WINDOWS", False)
    for raw in ("clip.mp4.", "clip.mp4 ", "clip.mp4"):
        assert _identity_key(tmp_path / raw) == tmp_path / raw


@pytest.mark.skipif(
    sys.platform != "win32", reason="Win32 strips trailing dots/spaces; POSIX does not"
)
def test_pool_rejects_win32_folded_identity_collision(tmp_path: Path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    with patch("allaganeye.export.pool.run_export_attempt", side_effect=_explode):
        with pytest.raises(ConfigValidationError):
            _run_pool(
                tmp_path,
                pattern="{type}",
                matches=make_pair("clip.mp4", "clip.mp4."),
                output_dir=out_dir,
            )


# --------------------------------------------------------------------------
# NTFS alternate data streams (Codex adversarial-review round 2, follow-up)
#
# ``clip.mp4::$DATA`` names the default stream of ``clip.mp4`` -- writing it
# writes that file -- yet it is a distinct string AND a distinct resolved
# Path, so neither the string check nor the identity key catches the pair.
# Folding it would mean modelling still more Win32 syntax. The rendered name
# is constrained instead: ``:`` is not legal in a Windows filename at all, and
# its only other meaning is the drive separator, which lives in the anchor and
# is already handled by the containment check.
# --------------------------------------------------------------------------


@pytest.mark.skipif(
    sys.platform != "win32", reason="':' is a legal filename character on POSIX"
)
def test_pool_rejects_alternate_data_stream(tmp_path: Path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    with patch("allaganeye.export.pool.run_export_attempt", side_effect=_explode):
        with pytest.raises(ConfigValidationError):
            _run_pool(
                tmp_path,
                pattern="{type}",
                matches=make_pair("clip.mp4", "clip.mp4::$DATA"),
                output_dir=out_dir,
            )


# --------------------------------------------------------------------------
# Reserved device names (#937 (a)).
#
# ``NUL`` / ``CON`` / ``PRN`` / ``AUX`` / ``COM1-9`` / ``LPT1-9`` are device
# names on Windows: writing to one "succeeds" but no file is created, so the
# run would report success for output that does not exist -- the same "written
# but gone" class as the path-identity bugs above, via a different mechanism.
# The name alone decides (no filesystem state), so it is blocked in input
# validation like the ``:`` ADS rule, not folded into the identity key.
# The logic is Windows-gated; CI runs on ubuntu, so the switch is driven
# directly (the OS behaviour varies by API -- see the _WIN32_RESERVED_NAMES
# docstring in pool.py -- which is why this stays a name validation rather
# than a behavioural premise).
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reserved",
    ["NUL", "CON", "PRN", "AUX", "COM1", "COM9", "LPT1", "LPT9", "com3", "nul"],
)
def test_pool_rejects_reserved_device_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, reserved: str
):
    """A rendered bare device name is rejected before any ffmpeg run."""
    monkeypatch.setattr(pool_module, "_IS_WINDOWS", True)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    with patch("allaganeye.export.pool.run_export_attempt", side_effect=_explode):
        with pytest.raises(ConfigValidationError):
            _run_pool(
                tmp_path,
                pattern="{type}",
                matches=make_pair(reserved, "ordinary"),
                output_dir=out_dir,
            )


def test_pool_rejects_reserved_device_name_in_subdirectory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """A reserved name as an interior component is rejected the same way."""
    monkeypatch.setattr(pool_module, "_IS_WINDOWS", True)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    with patch("allaganeye.export.pool.run_export_attempt", side_effect=_explode):
        with pytest.raises(ConfigValidationError):
            _run_pool(
                tmp_path,
                pattern="{type}/{idx:03}.mp4",
                matches=make_pair("AUX", "ordinary"),
                output_dir=out_dir,
            )


@pytest.mark.parametrize(
    "name",
    [
        "NUL.mp4",  # measured on Windows: an extension makes it an ordinary file
        "nulll.mp4",
        "ordinary",
        "COM10.mp4",  # only COM1-9 are reserved
    ],
)
def test_pool_accepts_non_reserved_device_names(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str
):
    """Reverse pin: only the *bare* device name is reserved -- no over-reject."""
    monkeypatch.setattr(pool_module, "_IS_WINDOWS", True)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    def fake_run(*args: Any, **kwargs: Any) -> ExportResult:
        return ExportResult(
            match_index=-1,
            output_path=kwargs["output"],
            duration_ms=1,
            encoder_used="libx264",
        )

    with patch("allaganeye.export.pool.run_export_attempt", side_effect=fake_run):
        summary = _run_pool(
            tmp_path,
            pattern="{type}",
            matches=make_pair(name, "pair_b"),
            output_dir=out_dir,
        )
    assert summary.success == 2


def test_pool_accepts_device_name_off_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """POSIX has no device names -- 'NUL' is an ordinary filename there."""
    monkeypatch.setattr(pool_module, "_IS_WINDOWS", False)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    def fake_run(*args: Any, **kwargs: Any) -> ExportResult:
        return ExportResult(
            match_index=-1,
            output_path=kwargs["output"],
            duration_ms=1,
            encoder_used="libx264",
        )

    with patch("allaganeye.export.pool.run_export_attempt", side_effect=fake_run):
        summary = _run_pool(
            tmp_path,
            pattern="{type}",
            matches=make_pair("NUL", "pair_b"),
            output_dir=out_dir,
        )
    assert summary.success == 2


# --------------------------------------------------------------------------
# Post-write filesystem-identity verification (#937 (b)).
#
# The path-string checks above cannot see aliases that only exist once files
# are on disk: a pre-placed hardlink pair whose names match two rendered
# names, or an NTFS 8.3 short name that aliases a name an earlier match in
# the same run created. export_matches therefore re-checks the *written*
# outputs by (st_dev, st_ino) after the pool finishes. Reachable only with a
# pre-arranged output directory or a crafted metadata.json -- but the
# alternative is a success summary for a silently lost file.
# --------------------------------------------------------------------------


def test_pool_post_write_rejects_hardlink_alias_pair(tmp_path: Path):
    """Two rendered names that were hardlinks before the run are one file."""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    a = out_dir / "clip_a.mp4"
    b = out_dir / "clip_b.mp4"
    a.write_bytes(b"pre-existing hardlink")
    os.link(a, b)  # same inode, two names

    def fake_run(*args: Any, **kwargs: Any) -> ExportResult:
        return ExportResult(
            match_index=-1,
            output_path=kwargs["output"],
            duration_ms=1,
            encoder_used="libx264",
        )

    with patch("allaganeye.export.pool.run_export_attempt", side_effect=fake_run):
        with pytest.raises(ConfigValidationError):
            _run_pool(
                tmp_path,
                pattern="{type}.mp4",
                matches=make_pair("clip_a", "clip_b"),
                output_dir=out_dir,
            )


def test_pool_post_write_accepts_distinct_outputs(tmp_path: Path):
    """Two ordinary pre-existing files keep working -- no over-reject."""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "clip_a.mp4").write_bytes(b"a")
    (out_dir / "clip_b.mp4").write_bytes(b"b")

    def fake_run(*args: Any, **kwargs: Any) -> ExportResult:
        return ExportResult(
            match_index=-1,
            output_path=kwargs["output"],
            duration_ms=1,
            encoder_used="libx264",
        )

    with patch("allaganeye.export.pool.run_export_attempt", side_effect=fake_run):
        summary = _run_pool(
            tmp_path,
            pattern="{type}.mp4",
            matches=make_pair("clip_a", "clip_b"),
            output_dir=out_dir,
        )
    assert summary.success == 2


# --------------------------------------------------------------------------
# Pre-write source-identity guard (#937 (b)).
#
# The preflight overwrite check compares resolved *paths*, so an output name
# that is a hardlink alias of the source video slips past it -- and writing it
# would truncate the input mid-run. The worker compares the real
# (st_dev, st_ino) identity before ffmpeg opens the file: cheap, and it
# prevents an irreversible write instead of detecting it afterwards.
# --------------------------------------------------------------------------


def test_pool_refuses_output_hardlinked_to_source(tmp_path: Path):
    """An output that already IS the source (hardlink alias) must not be written."""
    source = tmp_path / "in.mp4"
    source.write_bytes(b"SOURCE CONTENT")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    os.link(source, out_dir / "000.mp4")

    with patch("allaganeye.export.pool.run_export_attempt", side_effect=_explode):
        with pytest.raises(ConfigValidationError):
            _run_pool(
                tmp_path,
                pattern="{idx:03}.mp4",
                matches=make_matches(1),
                output_dir=out_dir,
                source_video=source,
            )
