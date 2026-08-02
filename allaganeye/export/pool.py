"""Parallel match-export orchestrator (#761).

Starts N workers via ThreadPoolExecutor; each worker pulls matches from a
shared queue and launches one ffmpeg via run_export_attempt. cancel_event
propagates to workers and kills in-flight ffmpeg processes. See spec section 4.4.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from queue import Empty, Queue

from allaganeye.exceptions import ConfigValidationError
from allaganeye.export.encoder import EncoderSlot, H264Encoder
from allaganeye.export.ffmpeg_runner import run_export_attempt
from allaganeye.export.schema import (
    ExportError,
    ExportResult,
    ExportSummary,
    ProgressEvent,
)


@dataclass(frozen=True)
class ExportMatch:
    """Single match to export. Mirrors metadata.json matches[] entry."""

    index: int
    start: float
    end: float
    type_label: str  # "match" / "non_fl" / etc. -- used by name_pattern
    video_filter: str | None = (
        None  # #481: optional ffmpeg -vf filter string (minimap crop etc.)
    )


def _format_filename(m: ExportMatch, pattern: str) -> str:
    """Render the output filename per ``pattern``.

    Tokens: ``{idx}`` / ``{idx:03}`` / ``{type}`` / ``{start}`` / ``{date}``.
    Mirrors gui/src/utils/filename.ts ``formatMatchFilename`` (#932).
    """
    start_disp = _format_start_for_filename(m.start)
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    out = pattern
    out = out.replace("{idx:03}", f"{m.index:03d}")
    out = out.replace("{idx}", str(m.index))
    out = out.replace("{type}", m.type_label)
    out = out.replace("{start}", start_disp)
    out = out.replace("{date}", today)
    return out


def _format_start_for_filename(seconds: float) -> str:
    """H-MM-SS / MM-SS form (`:` is invalid in Windows filenames).

    Mirrors gui/src/utils/filename.ts ``formatStartForFilename`` so the GUI
    preview and the CLI's actual output agree past the 1-hour mark
    (audit P2-20). Non-finite / negative inputs clamp to 0.
    """
    if not math.isfinite(seconds) or seconds < 0:
        seconds = 0.0
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h > 0:
        return f"{h}-{m:02d}-{s:02d}"
    return f"{m:02d}-{s:02d}"


def _render_and_sandbox(
    m: ExportMatch,
    pattern: str,
    *,
    output_dir: Path,
    source_video: Path,
) -> tuple[str, Path, Path]:
    """Shared body of the two public resolvers.

    Returns ``(rendered, candidate, resolved)``:

    * ``rendered``  -- the pattern with its tokens substituted (for messages)
    * ``candidate`` -- ``output_dir / rendered``, i.e. what ffmpeg is handed
    * ``resolved``  -- the normalised absolute path, i.e. the file's *identity*

    ``resolved`` is returned rather than recomputed by the caller on purpose.
    A second ``candidate.resolve()`` would sit outside this function's
    ``try``/``except``, so an OSError there would escape as an exit-1 traceback
    instead of the mapped exit 5; it would also open a fresh TOCTOU window in
    which a symlink could change between the two calls. Resolve once.
    """
    rendered = _format_filename(m, pattern)
    candidate = output_dir / rendered
    try:
        root = output_dir.resolve()
        resolved = candidate.resolve()
        source = source_video.resolve()
    except (OSError, ValueError) as e:  # invalid chars / NUL byte / bad drive
        raise ConfigValidationError(
            f"--name-pattern produced an unusable output path {rendered!r}: {e}"
        ) from e

    if resolved == root or not resolved.is_relative_to(root):
        raise ConfigValidationError(
            f"--name-pattern must stay inside the output directory: {rendered!r} "
            f"resolves to {resolved} (outside {root}). Remove '..' segments and "
            "absolute/drive-relative paths (note: the {type} token is taken "
            "verbatim from metadata.json)"
        )
    if resolved == source:
        raise ConfigValidationError(
            f"--name-pattern would overwrite the source video: {rendered!r} "
            f"resolves to {resolved}. Choose a different --output-dir or pattern"
        )
    return rendered, candidate, resolved


def resolve_export_output_paths(
    matches: Sequence[ExportMatch],
    pattern: str,
    *,
    output_dir: Path,
    source_video: Path,
) -> list[Path]:
    """Resolve every match's output path and reject duplicate *identities*.

    Containment and uniqueness are two different invariants, and checking
    them on two different representations is what let a bug through:
    :func:`resolve_export_output_path` judged containment on the **resolved
    path**, while the callers' duplicate check keyed a dict on the **rendered
    string**. Two renderings can both stay inside ``output_dir`` and still
    denote the same file, so both passed both checks and both were written --
    the later one silently replacing the earlier, with the summary still
    reporting two successes.

    Concretely, on Windows:

    * ``Clip.mp4`` vs ``clip.mp4`` -- different strings, one file (NTFS is
      case-insensitive)
    * ``sub/../clip.mp4`` vs ``clip.mp4`` -- ``..`` is normalised away even
      when ``sub`` does not exist, so both open ``clip.mp4``

    Keying on the resolved ``Path`` catches both without any hand-written
    normalisation, because ``PurePath`` equality and hashing already follow
    the platform's own rules (case-insensitive on Windows, case-sensitive on
    POSIX -- where ``Clip.mp4`` really is a second file and must stay legal).

    The rendered names -- not the resolved key -- are quoted in the error, so
    the message points at the ``--name-pattern`` / ``{type}`` values the user
    can actually change.

    Returns the ``output_dir / rendered`` paths in ``matches`` order (the
    unresolved form, exactly as :func:`resolve_export_output_path` returns).

    Raises:
        ConfigValidationError: any match escapes ``output_dir``, targets
            ``source_video``, or shares an output identity with an earlier
            match. Exit code 5.
    """
    out: list[Path] = []
    seen: dict[Path, str] = {}  # resolved identity -> first rendered name
    for m in matches:
        rendered, candidate, resolved = _render_and_sandbox(
            m, pattern, output_dir=output_dir, source_video=source_video
        )
        first = seen.get(resolved)
        if first is not None:
            if first == rendered:
                # Same string as well as same file: the long-standing
                # "pattern has no {idx}" case. Keep its original wording.
                raise ConfigValidationError(
                    "name pattern produces duplicate output filenames "
                    f"({rendered!r}); add {{idx}} or {{idx:03}} to the "
                    "--name-pattern"
                )
            raise ConfigValidationError(
                "name pattern maps two matches onto the same output file: "
                f"{first!r} and {rendered!r} both resolve to {resolved}; add "
                "{idx} or {idx:03} to the --name-pattern (two names can differ "
                "as text yet denote one file -- e.g. letter case on Windows, or "
                "a '..' segment; the {type} token is taken verbatim from "
                "metadata.json)"
            )
        seen[resolved] = rendered
        out.append(candidate)
    return out


def resolve_export_output_path(
    m: ExportMatch,
    pattern: str,
    *,
    output_dir: Path,
    source_video: Path,
) -> Path:
    """Render ``pattern`` for ``m`` and sandbox the result to ``output_dir`` (B1).

    Single-match check. It validates ``m`` **in isolation**, so it cannot see
    that two matches collide -- use :func:`resolve_export_output_paths` for
    any code path that handles a whole match list.

    ``output_dir / rendered`` is not confined to ``output_dir``:
    ``Path.__truediv__`` happily accepts ``..`` segments, an absolute path, or
    (on Windows) a drive-relative path, all of which land outside ``-o``. That
    made ``--name-pattern "../victim.mp4"`` silently overwrite an unrelated
    file and exit 0.

    The predicate is the **resolved path**, never the pattern string: the
    ``{type}`` token is an unvalidated metadata.json value, so a pattern that
    contains no separator at all can still render one. (Same lesson as the
    project's "destructive predicates must use identity, not names" rule.)

    Rejects (``ConfigValidationError`` -> exit 5):

    1. the rendered path resolves outside ``output_dir`` (or *is*
       ``output_dir`` itself, which is not a writable file target)
    2. the rendered path resolves onto ``source_video`` -- exporting a match
       onto its own source truncates the input mid-read

    A rendered name that stays inside ``output_dir`` is returned unchanged
    (``output_dir / rendered``, not the resolved form) so accepted patterns
    behave exactly as before, symlinks included.

    This runs BOTH here (per match, inside :func:`export_matches`) and in the
    CLI preflight of ``export`` / ``minimap``. The preflight exists to fail
    early with a readable message before any ffmpeg / metadata write-back
    work; this copy is the last line of defence for callers that never go
    through the preflight (the GUI passes a free-text pattern straight to the
    Tauri command, and future in-process callers would too). Neither layer may
    be dropped on the grounds that "the other one checks".
    """
    _rendered, candidate, _resolved = _render_and_sandbox(
        m, pattern, output_dir=output_dir, source_video=source_video
    )
    return candidate


def export_matches(
    matches: list[ExportMatch],
    slots: list[EncoderSlot],
    *,
    source_video: Path,
    output_dir: Path,
    codec: str,
    name_pattern: str,
    progress_cb: Callable[[ProgressEvent], None],
    cancel_event: threading.Event | None = None,
) -> ExportSummary:
    """Run N workers (= len(slots)) in parallel and return an aggregated summary.

    cancel_event:
        When set, workers exit on the next queue.get_nowait(). In-flight
        ffmpeg processes are killed inside run_export_attempt
        (ExportError(kind='cancelled')).

    Codex review #3: summary.cancelled is determined solely by
    ``cancel_event.is_set()``. Do NOT AND with ``queue.qsize() > 0`` -- that
    would produce a false negative if cancel fires after all items are dequeued.
    """
    if not slots:
        raise ValueError("export_matches: slots is empty (need at least 1)")

    # B1: sandbox every rendered name BEFORE spawning a single ffmpeg. Doing it
    # here (and not only inside the worker) keeps the run all-or-nothing: with a
    # {type}-driven escape only some matches are out of bounds, and a
    # worker-only check would already have written the earlier ones.
    #
    # The batch form also rejects two matches that resolve onto the SAME file.
    # That check is inherently list-level, so the per-match re-validation in the
    # worker below cannot express it -- this is the only place it can live for
    # callers that skip the CLI preflight (GUI / in-process).
    resolve_export_output_paths(
        matches, name_pattern, output_dir=output_dir, source_video=source_video
    )

    cancel_event = cancel_event or threading.Event()

    queue: Queue[ExportMatch] = Queue()
    for m in matches:
        queue.put(m)

    summary = ExportSummary()
    summary_lock = threading.Lock()
    cancelled_results: list[bool] = []  # any worker saw cancel

    def worker(slot: EncoderSlot) -> None:
        while not cancel_event.is_set():
            try:
                m = queue.get_nowait()
            except Empty:
                return

            def on_progress(percent: float, stage: str, _idx: int = m.index) -> None:
                progress_cb(ProgressEvent.progress(_idx, percent, stage))

            def on_fallback(
                src: H264Encoder, dst: H264Encoder, msg: str, _idx: int = m.index
            ) -> None:
                progress_cb(ProgressEvent.fallback(_idx, src.value, dst.value, msg))

            # B1: re-validate on the path that is actually handed to ffmpeg, so
            # no future edit can reintroduce an unchecked `output_dir / name`.
            output_path = resolve_export_output_path(
                m, name_pattern, output_dir=output_dir, source_video=source_video
            )
            try:
                result = run_export_attempt(
                    video=source_video,
                    start=m.start,
                    end=m.end,
                    output=output_path,
                    codec=codec,
                    encoder=slot.encoder_kind,
                    progress_cb=on_progress,
                    fallback_cb=on_fallback,
                    cancel_event=cancel_event,
                    video_filter=m.video_filter,
                )
                # match_index is overwritten by the caller value in ExportResult
                result_with_idx = ExportResult(
                    match_index=m.index,
                    output_path=result.output_path,
                    duration_ms=result.duration_ms,
                    encoder_used=result.encoder_used,
                    fallback_from=result.fallback_from,
                )
                progress_cb(
                    ProgressEvent.result(
                        m.index,
                        result_with_idx.output_path,
                        result_with_idx.duration_ms,
                        result_with_idx.encoder_used,
                    )
                )
                with summary_lock:
                    summary.success += 1
            except ExportError as e:
                progress_cb(ProgressEvent.error(m.index, e))
                with summary_lock:
                    summary.failure += 1
                if e.kind == "cancelled":
                    cancelled_results.append(True)

    with ThreadPoolExecutor(
        max_workers=len(slots), thread_name_prefix="export-worker"
    ) as ex:
        futures = [ex.submit(worker, slot) for slot in slots]
        for f in futures:
            f.result()  # propagate exceptions (workers catch internally, so normally None)

    # Codex review #3: cancel check uses cancel_event.is_set() alone
    summary.cancelled = cancel_event.is_set() or bool(cancelled_results)
    return summary
