"""Tests for CLI entry point."""

import re
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import click
import pytest
from typer import rich_utils
from typer.main import get_command
from typer.testing import CliRunner

from allaganeye.cli import app
from allaganeye.exceptions import (
    AllaganEyeError,
    DetectionError,
    InputFileError,
    VideoProcessingError,
)

runner = CliRunner()

MODULE = "allaganeye.commands.split_matches.run_split"
DETECT_MODULE = "allaganeye.commands.detect.run_detect"


# --- help assertion helpers ---
#
# Two independent hazards make a bare `"--opt" in result.stdout` unreliable here:
#
# 1. rich splits option names into escape-separated spans whenever colour is enabled
#    (`--vtuber` renders as ESC[1;36m-ESC[0mESC[1;36m-vtuberESC[0m) and wraps long help
#    sentences across panel rows, inserting box-drawing borders mid-sentence. A
#    positive assert then fails, and a negated one (`"--opt" not in stdout`) passes
#    unconditionally -- the false-green that let the --vtuber hidden pin rot.
# 2. Colour cannot be steered through the invocation environment. typer reads
#    GITHUB_ACTIONS / FORCE_COLOR / PY_COLORS *once at import time* into the module
#    constant `typer.rich_utils.FORCE_TERMINAL` and hands it to rich explicitly, which
#    short-circuits rich's own tty/env detection. On CI (GITHUB_ACTIONS=true) an
#    env-driven "no-color" leg is therefore still coloured, so the plain rendering path
#    would never run and looking plain locally is just a legacy-Windows accident.
#
# So: assert the click model for the contract, and check the rendering through the
# `render_help` fixture, which pins the mode by monkeypatching that constant and
# verifies per leg that the output really was plain / coloured.

# Escape sequences that may appear in rendered help. CSI is what typer emits today;
# OSC and the nF/Fe forms are pre-emptive -- a CSI-only regex leaves `ESC]8;;url ESC\`
# residue mid-token the moment a help string gains a hyperlink, which re-opens exactly
# the "negative assert passes on a split token" hole this module exists to close.
_ANSI_RE = re.compile(
    r"\x1b(?:"
    r"\[[0-9;?]*[ -/]*[@-~]"  # CSI: SGR colours, cursor control
    r"|\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC: hyperlink/title, BEL- or ST-terminated
    r"|[ -/]+[0-~]"  # nF: charset designation, e.g. ESC ( B
    r"|[@-Z\\-_]"  # Fe: two-character escapes, e.g. ESC M
    r")"
)

# rich frames option panels with box-drawing borders, so a wrapped sentence reads
# "... from a |" / "|   scorebar-presence ...". Dropping the glyphs before collapsing
# whitespace keeps the sentence contiguous; without it a wording pin would only ever
# match whichever fragment happened to fit on one row.
# Built via chr() so this file stays ASCII: test_ascii_guard.py scans string literal
# *values* (via AST), not source bytes, so a \u escape would not satisfy it.
_PANEL_BORDER_CODEPOINTS = (
    0x2502,
    0x2503,
    0x2506,
    0x2507,
    0x250A,
    0x250B,
    0x254E,
    0x254F,
    0x2551,
)
_PANEL_BORDER_RE = re.compile("[" + "".join(map(chr, _PANEL_BORDER_CODEPOINTS)) + "]")

# A foreground-colour SGR (3x/9x). typer draws the panel frame "dim" (ESC[2m) only, so
# this separates "content was colourised" from "only the frame carried escapes" -- a
# guard that accepts frame escapes stays green even if option names go plain.
_COLOR_SGR_RE = re.compile(r"\x1b\[[0-9;]*(?:3[0-7]|9[0-7])m")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences so help text can be matched literally."""
    return _ANSI_RE.sub("", text)


def _normalize_help(text: str) -> str:
    """Return *text* with escapes, panel borders and rich's wrapping collapsed away.

    Whitespace runs become single spaces, so a pinned sentence matches wherever rich
    chose to break the line. Collapsing can only join text, never split it, so negative
    asserts on the result are at least as strong as on the raw rendering.
    """
    return " ".join(_PANEL_BORDER_RE.sub(" ", _strip_ansi(text)).split())


@pytest.fixture(params=[False, True], ids=["plain", "ansi"])
def render_help(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Callable[[list[str]], str]:
    """Render ``--help`` in a pinned colour mode and return the normalized text.

    Each leg self-verifies that the rendering matched its id. Without that assert the
    "plain" leg silently degrades into a second coloured run on CI (see note above),
    every escape-handling helper here goes untested, and the module reports two legs of
    coverage while exercising one.
    """
    force_terminal: bool = request.param
    monkeypatch.setattr(rich_utils, "FORCE_TERMINAL", force_terminal)
    # FORCE_TERMINAL cannot turn colour *on* from the environment, but the environment
    # can still turn it off: rich honours NO_COLOR, and TERM=dumb drops color_system to
    # None even when forced. A dev shell carrying either would make the "ansi" leg fail
    # for reasons unrelated to the product, so both are neutralised here.
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")

    def _render(argv: list[str]) -> str:
        # COLUMNS is pinned so wrapping (and therefore every pin below) does not depend
        # on the ambient terminal width.
        result = runner.invoke(app, argv, env={"COLUMNS": "120"})
        assert result.exit_code == 0, result.stdout
        raw = result.stdout
        has_escape = "\x1b" in raw
        assert has_escape is force_terminal, (
            f"leg force_terminal={force_terminal!r} rendered with escapes="
            f"{has_escape!r}; this leg is not covering what its id claims"
        )
        normalized = _normalize_help(raw)
        # Residue would let a token stay split, which is how a negative assert goes
        # vacuous; fail loudly instead of matching against half-stripped text.
        assert "\x1b" not in normalized, f"unstripped escape in {normalized!r}"
        return normalized

    return _render


def _sub_command(name: str) -> click.Command:
    """Return the click sub-command *name* built from the typer app."""
    group = get_command(app)
    assert isinstance(group, click.Group), (
        f"expected a click Group, got {type(group)!r}"
    )
    command = group.commands.get(name)
    assert command is not None, (
        f"sub-command {name!r} not found; declared: {sorted(group.commands)}"
    )
    return command


def _find_click_option(command_name: str, option: str) -> click.Parameter | None:
    """Return the parameter declaring *option* on *command_name*, else ``None``."""
    for param in _sub_command(command_name).params:
        if option in param.opts or option in param.secondary_opts:
            return param
    return None


def _click_option(command_name: str, option: str) -> click.Option:
    """Like :func:`_find_click_option` but fails when *option* is missing.

    A removed or renamed flag therefore surfaces as a failure instead of a silent
    pass.
    """
    param = _find_click_option(command_name, option)
    declared = sorted(o for p in _sub_command(command_name).params for o in p.opts)
    assert param is not None, (
        f"option {option!r} is not declared on {command_name!r}; declared: {declared}"
    )
    assert isinstance(param, click.Option), (
        f"{option!r} on {command_name!r} is not an Option: {type(param)!r}"
    )
    return param


# --- Basic tests ---


def test_version(monkeypatch: pytest.MonkeyPatch):
    """--version returns 0 with version output (integrity check skipped for tests)."""
    monkeypatch.setenv("ALLAGANEYE_INTEGRITY_SKIP", "1")
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "allaganeye" in result.stdout


def test_version_short_flag(monkeypatch: pytest.MonkeyPatch):
    """-V should be an alias for --version (issue #337)."""
    monkeypatch.setenv("ALLAGANEYE_INTEGRITY_SKIP", "1")
    result = runner.invoke(app, ["-V"])
    assert result.exit_code == 0
    assert "allaganeye" in result.stdout


def test_strip_ansi_handles_non_csi_escapes():
    """_strip_ansi must clear OSC / charset / Fe escapes, not just CSI colour codes.

    A CSI-only regex leaves `ESC]8;;url ESC\\` residue in the middle of a token, so the
    day a help string gains a hyperlink `--vtuber` splits again and every negative
    assert in this module turns vacuous. Pin the failure mode before it can land.
    """
    hyperlinked = (
        "\x1b]8;;https://example.com/docs\x1b\\"  # OSC 8 open, ST-terminated
        "\x1b[1;36m--vtuber\x1b[0m"  # CSI (what typer emits today)
        "\x1b]8;;\x1b\\"  # OSC 8 close
    )
    assert _strip_ansi(hyperlinked) == "--vtuber"
    # BEL-terminated OSC (window title), charset designation (ESC ( B), Fe (ESC M).
    assert _strip_ansi("\x1b]0;title\x07\x1b(Bplain\x1bMtext") == "plaintext"
    # Belt and braces: no escape byte may survive, whatever the form.
    assert "\x1b" not in _strip_ansi(hyperlinked)


def test_normalize_help_joins_wrapped_panel_rows():
    """Panel borders and wrapping must not break a pinned sentence.

    Without border stripping the wording pins below would silently degrade into
    matching only whichever fragment fits one row at COLUMNS=120.
    """
    bar = chr(0x2502)  # chr(): keep this file ASCII (test_ascii_guard.py)
    wrapped = (
        f"{bar} --vtuber   detects matches from a {bar}\n"
        f"{bar}            scorebar-presence x motion timeline {bar}\n"
    )
    assert (
        "detects matches from a scorebar-presence x motion timeline"
        in _normalize_help(wrapped)
    )


def test_verbose_short_flag_unchanged(render_help: Callable[[list[str]], str]):
    """-v must still map to --verbose (not --version) on the split command.

    Breaking-change policy for v0.1.x: we add -V for --version but keep
    -v = --verbose to avoid disrupting existing preview users (issue #337).
    """
    param = _click_option("split", "-v")
    assert param.name == "verbose"
    assert "--verbose" in param.opts
    help_text = render_help(["split", "--help"])
    # The old `"-v" in help_text` was vacuous: it is a substring of "--verbose",
    # "--vtuber", "-vf", ... Pin the rendered row, where rich puts the long spelling
    # next to the short one, so a dropped `-v` alias is actually caught on screen.
    assert "--verbose -v" in help_text, f"--verbose/-v row missing: {help_text!r}"
    assert "Verbose output" in help_text, f"verbose help missing: {help_text!r}"


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "FF14 Frontline" in result.stdout


def test_split_help():
    result = runner.invoke(app, ["split", "--help"])
    assert result.exit_code == 0
    assert "video_path" in result.stdout.lower() or "VIDEO_PATH" in result.stdout


def test_split_missing_file():
    result = runner.invoke(app, ["split", "nonexistent.mp4"])
    assert result.exit_code == 2
    assert (
        "not found" in result.stdout.lower()
        or "not found" in (result.stderr or "").lower()
    )


def test_split_unsupported_format(tmp_path):
    fake_file = tmp_path / "video.txt"
    fake_file.write_text("not a video")
    result = runner.invoke(app, ["split", str(fake_file)])
    assert result.exit_code == 2
    assert (
        "unsupported" in result.stdout.lower()
        or "unsupported" in (result.stderr or "").lower()
    )


# --- Validation tests (exit code 5) ---


def test_split_negative_sample_interval(tmp_path):
    fake_file = tmp_path / "video.mp4"
    fake_file.write_bytes(b"\x00")
    result = runner.invoke(app, ["split", str(fake_file), "--sample-interval", "-1"])
    assert result.exit_code == 5


def test_split_zero_sample_interval(tmp_path):
    fake_file = tmp_path / "video.mp4"
    fake_file.write_bytes(b"\x00")
    result = runner.invoke(app, ["split", str(fake_file), "--sample-interval", "0"])
    assert result.exit_code == 5


def test_split_blackout_threshold_over_255(tmp_path):
    fake_file = tmp_path / "video.mp4"
    fake_file.write_bytes(b"\x00")
    result = runner.invoke(
        app, ["split", str(fake_file), "--blackout-threshold", "300"]
    )
    assert result.exit_code == 5


def test_split_negative_min_match_duration(tmp_path):
    fake_file = tmp_path / "video.mp4"
    fake_file.write_bytes(b"\x00")
    result = runner.invoke(app, ["split", str(fake_file), "--min-match-duration", "-1"])
    assert result.exit_code == 5


def test_split_negative_min_blackout_duration(tmp_path):
    """--min-blackout-duration -1 should fail validation (must be >= 0)."""
    fake_file = tmp_path / "video.mp4"
    fake_file.write_bytes(b"\x00")
    result = runner.invoke(
        app, ["split", str(fake_file), "--min-blackout-duration", "-1"]
    )
    assert result.exit_code == 5


def test_split_workers_zero(tmp_path):
    """--workers 0 should fail validation (must be >= 1)."""
    fake_file = tmp_path / "video.mp4"
    fake_file.write_bytes(b"\x00")
    result = runner.invoke(app, ["split", str(fake_file), "--workers", "0"])
    assert result.exit_code == 5


def test_split_workers_negative(tmp_path):
    """--workers -1 should fail validation."""
    fake_file = tmp_path / "video.mp4"
    fake_file.write_bytes(b"\x00")
    result = runner.invoke(app, ["split", str(fake_file), "--workers", "-1"])
    assert result.exit_code == 5


# --- Option tests ---


@patch(MODULE)
def test_split_default_options(mock_run_split, fake_video):
    """Default options produce expected SplitConfig values."""
    result = runner.invoke(app, ["split", str(fake_video)])

    assert result.exit_code == 0
    mock_run_split.assert_called_once()
    _, kwargs = mock_run_split.call_args
    config = mock_run_split.call_args[0][1]
    assert config.output_dir == Path("./output")
    assert config.sample_interval == 1.0
    assert config.blackout_threshold == 15.0
    assert config.min_match_duration == 300.0
    assert config.min_blackout_duration == 3.0
    assert config.workers is None
    assert config.use_gpu is None  # auto mode (#334)
    assert config.dry_run is False
    assert kwargs["verbose"] is False
    assert kwargs["quiet"] is False


@patch(MODULE)
def test_split_output_dir_option(mock_run_split, fake_video, tmp_path):
    """Short -o option sets output_dir."""
    out = tmp_path / "custom"
    result = runner.invoke(app, ["split", str(fake_video), "-o", str(out)])

    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.output_dir == out


@patch(MODULE)
def test_split_output_dir_long_form(mock_run_split, fake_video, tmp_path):
    """Long --output-dir option sets output_dir."""
    out = tmp_path / "custom"
    result = runner.invoke(app, ["split", str(fake_video), "--output-dir", str(out)])

    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.output_dir == out


@patch(MODULE)
def test_split_sample_interval(mock_run_split, fake_video):
    """--sample-interval option is forwarded to config."""
    result = runner.invoke(app, ["split", str(fake_video), "--sample-interval", "2.5"])

    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.sample_interval == 2.5


@patch(MODULE)
def test_split_blackout_threshold(mock_run_split, fake_video):
    """--blackout-threshold option is forwarded to config."""
    result = runner.invoke(
        app, ["split", str(fake_video), "--blackout-threshold", "20.0"]
    )

    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.blackout_threshold == 20.0


@patch(MODULE)
def test_split_min_match_duration(mock_run_split, fake_video):
    """--min-match-duration option is forwarded to config."""
    result = runner.invoke(
        app, ["split", str(fake_video), "--min-match-duration", "120"]
    )

    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.min_match_duration == 120.0


@patch(MODULE)
def test_split_min_blackout_duration(mock_run_split, fake_video):
    """--min-blackout-duration option is forwarded to config."""
    result = runner.invoke(
        app, ["split", str(fake_video), "--min-blackout-duration", "5.0"]
    )

    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.min_blackout_duration == 5.0


@patch(MODULE)
def test_split_dry_run(mock_run_split, fake_video):
    """--dry-run flag sets config.dry_run=True."""
    result = runner.invoke(app, ["split", str(fake_video), "--dry-run"])

    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.dry_run is True


@patch(MODULE)
def test_split_workers_option(mock_run_split, fake_video):
    """--workers 8 sets config.workers=8."""
    result = runner.invoke(app, ["split", str(fake_video), "--workers", "8"])

    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.workers == 8


@patch(MODULE)
def test_split_gpu_flag(mock_run_split, fake_video):
    """--gpu sets config.use_gpu=True."""
    result = runner.invoke(app, ["split", str(fake_video), "--gpu"])

    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.use_gpu is True


@patch(MODULE)
def test_split_no_gpu_flag(mock_run_split, fake_video):
    """--no-gpu explicitly sets config.use_gpu=False."""
    result = runner.invoke(app, ["split", str(fake_video), "--no-gpu"])

    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.use_gpu is False


@patch(MODULE)
def test_split_vtuber_flag(mock_run_split, fake_video):
    """--vtuber sets config.vtuber=True on split (L3 B6)."""
    result = runner.invoke(app, ["split", str(fake_video), "--vtuber"])

    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.vtuber is True


@patch(MODULE)
def test_split_vtuber_default_false(mock_run_split, fake_video):
    """Omitting --vtuber keeps config.vtuber=False (OBS full-frame, L3 B6)."""
    result = runner.invoke(app, ["split", str(fake_video)])

    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.vtuber is False


@patch(MODULE)
def test_split_keep_trailing_flag(mock_run_split, fake_video):
    """--keep-trailing sets config.keep_trailing=True on split (#805 段階1)."""
    result = runner.invoke(app, ["split", str(fake_video), "--keep-trailing"])

    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.keep_trailing is True


@patch(MODULE)
def test_split_keep_trailing_default_false(mock_run_split, fake_video):
    """Omitting --keep-trailing keeps config.keep_trailing=False (#797 drop on)."""
    result = runner.invoke(app, ["split", str(fake_video)])

    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.keep_trailing is False


@patch(DETECT_MODULE)
def test_detect_keep_trailing_flag(mock_run_detect, fake_video):
    """--keep-trailing sets config.keep_trailing=True on detect (#805 段階1)."""
    result = runner.invoke(app, ["detect", str(fake_video), "--keep-trailing"])

    assert result.exit_code == 0
    config = mock_run_detect.call_args[0][1]
    assert config.keep_trailing is True


@patch(DETECT_MODULE)
def test_detect_keep_trailing_default_false(mock_run_detect, fake_video):
    """Omitting --keep-trailing keeps config.keep_trailing=False on detect."""
    result = runner.invoke(app, ["detect", str(fake_video)])

    assert result.exit_code == 0
    config = mock_run_detect.call_args[0][1]
    assert config.keep_trailing is False


# Load-bearing claims of the --vtuber help (commit 0ea55a2): who it is for, what it
# actually does, and the limitation users must know about.
_VTUBER_HELP_REQUIRED = (
    "VTuber recording",
    "scorebar-presence x motion timeline",
    "70s may merge",
)
# Pre-P3 wording. Kept as negative pins so a revert to the deferred/experimental
# framing fails instead of quietly shipping (lower-cased before matching).
_VTUBER_HELP_RETIRED = ("experimental", "deferred", "under-detects", "#480")


@pytest.mark.parametrize("command_name", ["split", "detect"])
def test_vtuber_shown_in_help(
    command_name: str, render_help: Callable[[list[str]], str]
):
    """--vtuber は split/detect --help に出る + help 文言も pin する (#895 P3).

    #895 P3 で hidden 解除 (Idios 承認 2026-07-30): timeline 検出 (V0-V4) が 6 source /
    GT 76 試合で recall 100% を実証し、OBS/masked path の bit-exact 非接触も実機 gate で
    確認したため公開扱いにした。

    substring を stdout に直接 assert しないのは、色付き環境 (CI) で rich が option 名を
    ANSI で分割する (`--vtuber` -> ESC[1;36m-ESC[0mESC[1;36m-vtuberESC[0m) ため。
    前身の hidden pin (`"--vtuber" not in result.stdout`) はこの分割により色付き環境で
    常に真になる false-green で、hidden 状態を CI で一度も gate していなかった。

    見逃しの塞ぎ方: `hidden is False` だけでは help=None でも green (この PR の出荷物の
    半分である文言更新が空でも通る) なので model 側で文言を pin し、model pin だけでは
    「書いてあるが描画されない」(再 hidden 化・truncate) を見逃すので描画側でも pin する。
    """
    option = _click_option(command_name, "--vtuber")
    assert option.hidden is False

    # --- model side: the wording itself is part of the contract ---
    help_str = " ".join((option.help or "").split())
    for phrase in _VTUBER_HELP_REQUIRED:
        assert phrase in help_str, (
            f"{command_name} --vtuber help lost {phrase!r}: {help_str!r}"
        )
    lowered = help_str.lower()
    # Scoped to this option's own help on purpose: a whole-page negative would be
    # wrong-scoped (other options legitimately say "frozen"/reference deferred work)
    # and would rot into a flaky pin on unrelated help edits.
    for phrase in _VTUBER_HELP_RETIRED:
        assert phrase not in lowered, (
            f"{command_name} --vtuber help resurrected pre-P3 wording {phrase!r}: "
            f"{help_str!r}"
        )

    # --- render side: the model text must actually reach the screen ---
    rendered = render_help([command_name, "--help"])
    assert "--vtuber" in rendered, f"no --vtuber row in rendered help: {rendered!r}"
    # Containment of the *whole* model string also catches truncation and a re-hidden
    # option, which a phrase-only render pin would miss.
    assert help_str in rendered, f"--vtuber help not rendered verbatim: {rendered!r}"


def test_vtuber_help_identical_across_commands():
    """split と detect の --vtuber help は cli.py 内の複製なので drift させない。

    Each command declares its own literal; without this pin a wording fix applied to one
    copy leaves the other stale while both per-command tests stay green.
    """
    split_help = _click_option("split", "--vtuber").help
    detect_help = _click_option("detect", "--vtuber").help
    # Non-empty first: `None == None` would otherwise satisfy the equality below.
    assert split_help, "split --vtuber has no help"
    assert split_help == detect_help


def test_ansi_leg_colourises_option_name():
    """The coloured leg must colourise the option *name*, not just the panel frame.

    Guarding on "any escape in stdout" is too weak: typer draws the panel border with
    ESC[2m, so such a guard stays green even if rich stopped styling option names --
    at which point the escape-stripping helpers would cover nothing. Even a row-wide
    search is too weak, because neighbouring columns (metavar / required marker) carry
    their own SGR. Scope the search to the span before the name so this stays a real
    canary for the token-splitting hazard the helpers exist to handle.
    """
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(rich_utils, "FORCE_TERMINAL", True)
        mp.delenv("NO_COLOR", raising=False)
        mp.setenv("TERM", "xterm-256color")
        result = runner.invoke(app, ["split", "--help"], env={"COLUMNS": "120"})
    assert result.exit_code == 0, result.stdout
    rows = [
        line for line in result.stdout.splitlines() if "--vtuber" in _strip_ansi(line)
    ]
    assert rows, "no --vtuber row in rendered help"
    row = rows[0]
    name_span = row[: row.index("vtuber")]
    assert _COLOR_SGR_RE.search(name_span) is not None, (
        f"--vtuber option name carries no foreground-colour SGR: {row!r}"
    )


@patch(MODULE)
def test_split_verbose_short(mock_run_split, fake_video):
    """-v flag sets verbose=True."""
    result = runner.invoke(app, ["split", str(fake_video), "-v"])

    assert result.exit_code == 0
    assert mock_run_split.call_args[1]["verbose"] is True


@patch(MODULE)
def test_split_verbose_long(mock_run_split, fake_video):
    """--verbose flag sets verbose=True."""
    result = runner.invoke(app, ["split", str(fake_video), "--verbose"])

    assert result.exit_code == 0
    assert mock_run_split.call_args[1]["verbose"] is True


@patch(MODULE)
def test_split_quiet_short(mock_run_split, fake_video):
    """-q flag sets quiet=True."""
    result = runner.invoke(app, ["split", str(fake_video), "-q"])

    assert result.exit_code == 0
    assert mock_run_split.call_args[1]["quiet"] is True


@patch(MODULE)
def test_split_quiet_long(mock_run_split, fake_video):
    """--quiet flag sets quiet=True."""
    result = runner.invoke(app, ["split", str(fake_video), "--quiet"])

    assert result.exit_code == 0
    assert mock_run_split.call_args[1]["quiet"] is True


@patch(MODULE)
def test_split_all_options_combined(mock_run_split, fake_video, tmp_path):
    """All options combined are correctly forwarded."""
    out = tmp_path / "all"
    result = runner.invoke(
        app,
        [
            "split",
            str(fake_video),
            "-o",
            str(out),
            "--sample-interval",
            "0.5",
            "--blackout-threshold",
            "25.0",
            "--min-match-duration",
            "60",
            "--min-blackout-duration",
            "5.0",
            "--workers",
            "4",
            "--gpu",
            "--dry-run",
            "-v",
        ],
    )

    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.output_dir == out
    assert config.sample_interval == 0.5
    assert config.blackout_threshold == 25.0
    assert config.min_match_duration == 60.0
    assert config.min_blackout_duration == 5.0
    assert config.workers == 4
    assert config.use_gpu is True
    assert config.dry_run is True
    assert mock_run_split.call_args[1]["verbose"] is True


# --- Error exit code tests ---


@patch(MODULE)
def test_split_processing_error_exit_code(mock_run_split, fake_video):
    """VideoProcessingError produces exit code 3."""
    mock_run_split.side_effect = VideoProcessingError("ffmpeg failed")

    result = runner.invoke(app, ["split", str(fake_video)])
    assert result.exit_code == 3


@patch(MODULE)
def test_split_detection_error_exit_code(mock_run_split, fake_video):
    """DetectionError produces exit code 4."""
    mock_run_split.side_effect = DetectionError("No boundaries found")

    result = runner.invoke(app, ["split", str(fake_video)])
    assert result.exit_code == 4


@patch(MODULE)
def test_split_input_file_error_exit_code(mock_run_split, fake_video):
    """InputFileError from run_split produces exit code 2."""
    mock_run_split.side_effect = InputFileError("No video stream found")

    result = runner.invoke(app, ["split", str(fake_video)])
    assert result.exit_code == 2


@patch(MODULE)
def test_split_base_error_exit_code(mock_run_split, fake_video):
    """AllaganEyeError (base class) produces exit code 1."""
    mock_run_split.side_effect = AllaganEyeError("generic error")

    result = runner.invoke(app, ["split", str(fake_video)])
    assert result.exit_code == 1


@patch(MODULE)
def test_split_unexpected_error_exit_code(mock_run_split, fake_video):
    """Unexpected RuntimeError produces exit code 1."""
    mock_run_split.side_effect = RuntimeError("unexpected")

    result = runner.invoke(app, ["split", str(fake_video)])
    assert result.exit_code == 1


# --- Verbose error detail tests (issue #351) ---


@patch(MODULE)
def test_split_verbose_shows_context_detail(mock_run_split, fake_video):
    """VideoProcessingError with context emits 'stderr_tail:' in verbose mode."""
    mock_run_split.side_effect = VideoProcessingError(
        "ffmpeg failed",
        context={
            "command": "ffmpeg -i foo.mp4",
            "return_code": 1,
            "stderr_tail": "NAL unit type 12 not supported",
        },
    )
    result = runner.invoke(app, ["split", str(fake_video), "-v"])
    assert result.exit_code == 3
    combined = result.stdout + (result.stderr or "")
    assert "Error: ffmpeg failed" in combined
    assert "command:" in combined
    assert "return_code:" in combined
    assert "stderr_tail:" in combined
    assert "NAL unit type 12 not supported" in combined


@patch(MODULE)
def test_split_non_verbose_hides_context_detail(mock_run_split, fake_video):
    """Without -v, context detail stays hidden (short error only)."""
    mock_run_split.side_effect = VideoProcessingError(
        "ffmpeg failed",
        context={"stderr_tail": "NAL unit type 12 not supported"},
    )
    result = runner.invoke(app, ["split", str(fake_video)])
    assert result.exit_code == 3
    combined = result.stdout + (result.stderr or "")
    assert "Error: ffmpeg failed" in combined
    assert "stderr_tail" not in combined
    assert "NAL unit type 12 not supported" not in combined


@patch(MODULE)
def test_split_verbose_shows_traceback_for_unexpected(mock_run_split, fake_video):
    """Unexpected Exception emits traceback to stderr in verbose mode."""
    mock_run_split.side_effect = RuntimeError("boom")
    result = runner.invoke(app, ["split", str(fake_video), "-v"])
    assert result.exit_code == 1
    combined = result.stdout + (result.stderr or "")
    assert "Traceback" in combined
    assert "RuntimeError: boom" in combined


@patch(MODULE)
def test_split_non_verbose_hides_traceback_for_unexpected(mock_run_split, fake_video):
    """Without -v, unexpected error shows short one-liner (no traceback)."""
    mock_run_split.side_effect = RuntimeError("boom")
    result = runner.invoke(app, ["split", str(fake_video)])
    assert result.exit_code == 1
    combined = result.stdout + (result.stderr or "")
    assert "Traceback" not in combined
    assert "Unexpected error" in combined
    assert "boom" in combined


# --- Matrix v2 19a/19b/19c error display tests (issue #428) ---


@patch(MODULE)
def test_matrix_19a_verbose_emits_traceback_for_app_error(mock_run_split, fake_video):
    """19a: -v shows Error + verbose_detail + full traceback for AllaganEyeError.

    The traceback must be emitted even though the CLI handler re-raises
    via ``raise typer.Exit from None``: we print the traceback *before*
    the re-raise, when the original exception stack is still attached.
    """
    mock_run_split.side_effect = VideoProcessingError(
        "ffmpeg failed",
        context={
            "command": "ffmpeg -i foo.mp4",
            "return_code": 1,
            "stderr_tail": "NAL unit type 12 not supported",
        },
    )
    result = runner.invoke(app, ["split", str(fake_video), "-v"])
    assert result.exit_code == 3
    combined = result.stdout + (result.stderr or "")
    # Error line + verbose detail + traceback lines all present.
    assert "Error: ffmpeg failed" in combined
    assert "stderr_tail:" in combined
    assert "NAL unit type 12 not supported" in combined
    assert "Traceback" in combined
    assert "VideoProcessingError" in combined
    # Hint must NOT appear in verbose mode (hint is 19b's signal).
    assert "--verbose for full details" not in combined


@patch(MODULE)
def test_matrix_19b_default_emits_hint_for_app_error(mock_run_split, fake_video):
    """19b: default shows Error + 1-line hint (no context, no traceback)."""
    mock_run_split.side_effect = VideoProcessingError(
        "ffmpeg failed",
        context={"stderr_tail": "NAL unit type 12 not supported"},
    )
    result = runner.invoke(app, ["split", str(fake_video)])
    assert result.exit_code == 3
    combined = result.stdout + (result.stderr or "")
    assert "Error: ffmpeg failed" in combined
    # Hint is the defining 19b signal.
    assert "Run with -v / --verbose for full details" in combined
    # Neither context detail nor traceback leak into default mode.
    assert "stderr_tail" not in combined
    assert "NAL unit type" not in combined
    assert "Traceback" not in combined


@patch(MODULE)
def test_matrix_19c_quiet_emits_error_only_for_app_error(mock_run_split, fake_video):
    """19c: -q shows Error only.  No context, no hint, no traceback."""
    mock_run_split.side_effect = VideoProcessingError(
        "ffmpeg failed",
        context={"stderr_tail": "NAL unit type 12 not supported"},
    )
    result = runner.invoke(app, ["split", str(fake_video), "-q"])
    assert result.exit_code == 3
    combined = result.stdout + (result.stderr or "")
    assert "Error: ffmpeg failed" in combined
    assert "--verbose for full details" not in combined
    assert "stderr_tail" not in combined
    assert "NAL unit type" not in combined
    assert "Traceback" not in combined


@patch(MODULE)
def test_matrix_19b_default_emits_hint_for_unexpected(mock_run_split, fake_video):
    """19b applies to non-AllaganEyeError too: one-liner + hint."""
    mock_run_split.side_effect = RuntimeError("boom")
    result = runner.invoke(app, ["split", str(fake_video)])
    assert result.exit_code == 1
    combined = result.stdout + (result.stderr or "")
    assert "Unexpected error: boom" in combined
    assert "Run with -v / --verbose for full details" in combined
    assert "Traceback" not in combined


@patch(MODULE)
def test_matrix_19c_quiet_emits_error_only_for_unexpected(mock_run_split, fake_video):
    """19c for non-AllaganEyeError: one-liner only (no hint, no traceback)."""
    mock_run_split.side_effect = RuntimeError("boom")
    result = runner.invoke(app, ["split", str(fake_video), "-q"])
    assert result.exit_code == 1
    combined = result.stdout + (result.stderr or "")
    assert "Unexpected error: boom" in combined
    assert "--verbose for full details" not in combined
    assert "Traceback" not in combined


@patch(MODULE)
def test_matrix_traceback_includes_exception_class_name(mock_run_split, fake_video):
    """-v traceback must surface the concrete AllaganEyeError subclass.

    Bug reports lean on the subclass name to classify failures; a bare
    base-class ``AllaganEyeError`` would lose the signal.
    """
    mock_run_split.side_effect = DetectionError("no boundaries")
    result = runner.invoke(app, ["split", str(fake_video), "-v"])
    assert result.exit_code == 4
    combined = result.stdout + (result.stderr or "")
    assert "Traceback" in combined
    assert "DetectionError" in combined


@patch(MODULE)
def test_matrix_config_error_follows_matrix(mock_run_split, fake_video):
    """ConfigValidationError (pre-run_split path) still follows the matrix.

    The CLI raises ConfigValidationError itself when -v and -q conflict
    (#419); the reporter must use the correct mode for the *successful*
    option -- i.e. when only -v is passed, -v wins and 19a applies.
    """
    # Invalid threshold raises during SplitConfig.__post_init__ -> CVE.
    # Run with -v so we assert 19a's output shape.
    result = runner.invoke(
        app,
        ["split", str(fake_video), "--blackout-threshold", "-5", "-v"],
    )
    assert result.exit_code == 5
    combined = result.stdout + (result.stderr or "")
    assert "Error:" in combined
    assert "Traceback" in combined
    assert "ConfigValidationError" in combined


def test_matrix_debug_brightness_hint_suppressed(tmp_path):
    """debug-brightness has no -v option; do not show the -v hint on error.

    Input-validation error path triggers InputFileError without -v / -q
    flags available.  The hint would be misleading ("Run with -v" is not
    a valid option here), so ``show_hint=False`` is passed in the
    debug-brightness handler.  Exit code must stay at 2 (InputFileError).
    """
    missing = tmp_path / "does_not_exist.mp4"
    result = runner.invoke(app, ["debug-brightness", str(missing)])
    assert result.exit_code == 2
    combined = result.stdout + (result.stderr or "")
    assert "Error:" in combined
    assert "--verbose for full details" not in combined


# --- Extension support tests ---


@patch(MODULE)
def test_split_mkv_extension(mock_run_split, tmp_path):
    """MKV files are accepted."""
    video = tmp_path / "recording.mkv"
    video.write_bytes(b"")
    result = runner.invoke(app, ["split", str(video)])
    assert result.exit_code == 0
    mock_run_split.assert_called_once()


@patch(MODULE)
def test_split_avi_extension(mock_run_split, tmp_path):
    """AVI files are accepted."""
    video = tmp_path / "recording.avi"
    video.write_bytes(b"")
    result = runner.invoke(app, ["split", str(video)])
    assert result.exit_code == 0
    mock_run_split.assert_called_once()


# ============================================================
# debug-brightness CLI tests
# ============================================================

DEBUG_MODULE = "allaganeye.commands.debug_brightness.run_debug_brightness"


def test_debug_brightness_help():
    """debug-brightness --help shows usage."""
    result = runner.invoke(app, ["debug-brightness", "--help"])
    assert result.exit_code == 0
    assert "video_path" in result.stdout.lower() or "VIDEO_PATH" in result.stdout


def test_debug_brightness_missing_file():
    """Nonexistent file produces exit code 2."""
    result = runner.invoke(app, ["debug-brightness", "nonexistent.mp4"])
    assert result.exit_code == 2
    assert (
        "not found" in result.stdout.lower()
        or "not found" in (result.stderr or "").lower()
    )


def test_debug_brightness_unsupported_format(tmp_path):
    """Unsupported extension produces exit code 2."""
    fake_file = tmp_path / "video.txt"
    fake_file.write_text("not a video")
    result = runner.invoke(app, ["debug-brightness", str(fake_file)])
    assert result.exit_code == 2
    assert (
        "unsupported" in result.stdout.lower()
        or "unsupported" in (result.stderr or "").lower()
    )


@patch(DEBUG_MODULE)
def test_debug_brightness_default_options(mock_run, fake_video):
    """Default options are forwarded correctly."""
    result = runner.invoke(app, ["debug-brightness", str(fake_video)])

    assert result.exit_code == 0
    mock_run.assert_called_once()
    _, kwargs = mock_run.call_args
    assert kwargs["start"] == 0.0
    assert kwargs["end"] is None
    assert kwargs["interval"] == 1.0
    assert kwargs["workers"] is None
    assert kwargs["roi_mode"] is None


@patch(DEBUG_MODULE)
def test_debug_brightness_roi_mode_scorebar(mock_run, fake_video):
    """--roi-mode scorebar is forwarded."""
    result = runner.invoke(
        app, ["debug-brightness", str(fake_video), "--roi-mode", "scorebar"]
    )

    assert result.exit_code == 0
    assert mock_run.call_args[1]["roi_mode"] == "scorebar"


@patch(DEBUG_MODULE)
def test_debug_brightness_roi_mode_scorebar_detail(mock_run, fake_video):
    """--roi-mode scorebar-detail is forwarded."""
    result = runner.invoke(
        app, ["debug-brightness", str(fake_video), "--roi-mode", "scorebar-detail"]
    )

    assert result.exit_code == 0
    assert mock_run.call_args[1]["roi_mode"] == "scorebar-detail"


@patch(DEBUG_MODULE)
def test_debug_brightness_start_end_interval(mock_run, fake_video):
    """--start, --end, --interval are forwarded."""
    result = runner.invoke(
        app,
        [
            "debug-brightness",
            str(fake_video),
            "--start",
            "10.0",
            "--end",
            "60.0",
            "--interval",
            "0.5",
        ],
    )

    assert result.exit_code == 0
    _, kwargs = mock_run.call_args
    assert kwargs["start"] == 10.0
    assert kwargs["end"] == 60.0
    assert kwargs["interval"] == 0.5


@patch(MODULE)
def test_no_cache_option_accepted(mock_run, fake_video):
    """--no-cache option is accepted without error."""
    result = runner.invoke(app, ["split", str(fake_video), "--no-cache"])
    assert result.exit_code == 0
    config = mock_run.call_args[0][1]
    assert config.no_cache is True


# --- Mutually exclusive flag tests (#419) ---
#
# -q / -v and --gpu / --no-gpu are semantically exclusive.  Typer's default
# parse treats each pair as last-wins (silent), so scripts that set both
# end up with non-deterministic behaviour.  Exit code 5 (config-invalid)
# surfaces the mistake instead.


@patch(MODULE)
def test_split_quiet_verbose_mutually_exclusive(mock_run_split, fake_video):
    """-q and -v together exit 5 without calling run_split (#419 P)."""
    result = runner.invoke(app, ["split", str(fake_video), "-q", "-v"])
    assert result.exit_code == 5
    mock_run_split.assert_not_called()
    combined = result.stdout + (result.stderr or "")
    assert "--quiet and --verbose are mutually exclusive" in combined
    assert result.stdout == "", f"stdout must be empty: {result.stdout!r}"


@patch(MODULE)
def test_split_verbose_quiet_mutually_exclusive_order_independent(
    mock_run_split, fake_video
):
    """-v -q (reverse order) also exits 5 (#419 P)."""
    result = runner.invoke(app, ["split", str(fake_video), "-v", "-q"])
    assert result.exit_code == 5
    mock_run_split.assert_not_called()


@patch(MODULE)
def test_split_long_quiet_verbose_mutually_exclusive(mock_run_split, fake_video):
    """Long forms --quiet --verbose are also caught (#419 P)."""
    result = runner.invoke(app, ["split", str(fake_video), "--quiet", "--verbose"])
    assert result.exit_code == 5
    mock_run_split.assert_not_called()


@patch(MODULE)
def test_split_gpu_no_gpu_mutually_exclusive(mock_run_split, fake_video):
    """--gpu and --no-gpu together exit 5 (#419)."""
    result = runner.invoke(app, ["split", str(fake_video), "--gpu", "--no-gpu"])
    assert result.exit_code == 5
    mock_run_split.assert_not_called()
    combined = result.stdout + (result.stderr or "")
    assert "--gpu and --no-gpu are mutually exclusive" in combined
    assert result.stdout == "", f"stdout must be empty: {result.stdout!r}"


@patch(MODULE)
def test_split_no_gpu_gpu_order_independent(mock_run_split, fake_video):
    """--no-gpu --gpu (reverse order) also exits 5 (#419)."""
    result = runner.invoke(app, ["split", str(fake_video), "--no-gpu", "--gpu"])
    assert result.exit_code == 5
    mock_run_split.assert_not_called()


@patch(MODULE)
def test_split_no_gpu_alone_still_works(mock_run_split, fake_video):
    """--no-gpu alone continues to force CPU mode (#419 regression guard)."""
    result = runner.invoke(app, ["split", str(fake_video), "--no-gpu"])
    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.use_gpu is False


@patch(MODULE)
def test_split_gpu_alone_still_works(mock_run_split, fake_video):
    """--gpu alone forces GPU mode (#419 regression guard)."""
    result = runner.invoke(app, ["split", str(fake_video), "--gpu"])
    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.use_gpu is True


@patch(MODULE)
def test_split_neither_gpu_flag_preserves_auto(mock_run_split, fake_video):
    """Neither --gpu nor --no-gpu keeps use_gpu=None (auto-select, #334)."""
    result = runner.invoke(app, ["split", str(fake_video)])
    assert result.exit_code == 0
    config = mock_run_split.call_args[0][1]
    assert config.use_gpu is None


# --- CLI option combination tests ---
#
# The existing per-option tests verify each flag in isolation.  Users run
# the CLI with *combinations* (e.g. ``--dry-run --no-cache -v`` when
# troubleshooting), and individual-flag tests don't guarantee that
# pairwise and three-way interactions still wire through to SplitConfig
# correctly.
#
# Full 2^N cartesian coverage is infeasible (~16k cases for ~14 options).
# Instead we cover three bounded axes:
#
#   1. Real usecase patterns - the combinations a user actually types
#   2. Risk-high pairs - flags that interact via the same code path
#      (cache + dry-run, GPU + cache, etc.)
#   3. Order-independence - Typer should not care about flag order
#
# All cases mock ``run_split`` so a full parametrize sweep is < 1 second.


class TestCliOptionCombinations:
    """Representative CLI flag combinations forward to SplitConfig."""

    @pytest.mark.parametrize(
        ("argv_extras", "expected_config"),
        [
            # --- Real usecase patterns ---
            # Inspect mode: check what would be detected without splitting.
            (["--dry-run", "-v"], {"dry_run": True}),
            # Force fresh inspect: ignore cache and dry-run.
            (
                ["--dry-run", "--no-cache", "-v"],
                {"dry_run": True, "no_cache": True},
            ),
            # Silent bulk processing with audio disabled.
            (["-q", "--no-audio"], {"no_audio": True}),
            # CPU debugging: verbose, force CPU, limit workers.
            (
                ["-v", "--no-gpu", "--workers", "4"],
                {"use_gpu": False, "workers": 4},
            ),
            # Custom output + GPU + workers (typical batch script).
            (
                ["--gpu", "--workers", "8"],
                {"use_gpu": True, "workers": 8},
            ),
            # Tuned detection parameters (no flags).
            (
                [
                    "--sample-interval",
                    "1.0",
                    "--blackout-threshold",
                    "20.0",
                    "--min-match-duration",
                    "180",
                ],
                {
                    "sample_interval": 1.0,
                    "blackout_threshold": 20.0,
                    "min_match_duration": 180.0,
                },
            ),
            # --- Risk-high pairs (shared code paths) ---
            # dry-run writes cache; --no-cache invalidates on read.
            (
                ["--dry-run", "--no-cache"],
                {"dry_run": True, "no_cache": True},
            ),
            # Force fresh GPU detection.
            (
                ["--gpu", "--no-cache"],
                {"use_gpu": True, "no_cache": True},
            ),
            # Full debug invocation.
            (
                ["-v", "--no-cache", "--dry-run"],
                {"no_cache": True, "dry_run": True},
            ),
            # Silent dry-run with fresh detection.
            (
                ["-q", "--dry-run", "--no-cache"],
                {"dry_run": True, "no_cache": True},
            ),
            # --- Three-way flag interaction ---
            # All three boolean flags with GPU.
            (
                ["--no-cache", "--dry-run", "--no-audio", "--gpu"],
                {
                    "no_cache": True,
                    "dry_run": True,
                    "no_audio": True,
                    "use_gpu": True,
                },
            ),
            # Value options + flag combination.
            (
                ["--sample-interval", "2.0", "--no-gpu", "--no-audio"],
                {
                    "sample_interval": 2.0,
                    "use_gpu": False,
                    "no_audio": True,
                },
            ),
        ],
    )
    @patch(MODULE)
    def test_cli_combination_forwards_to_config(
        self, mock_run_split, fake_video, argv_extras, expected_config
    ):
        """Combination of CLI flags forwards expected values to SplitConfig."""
        result = runner.invoke(app, ["split", str(fake_video), *argv_extras])
        assert result.exit_code == 0, (
            f"exit code {result.exit_code} for argv={argv_extras!r}: {result.stdout}"
        )
        config = mock_run_split.call_args[0][1]
        for key, expected in expected_config.items():
            actual = getattr(config, key)
            assert actual == expected, (
                f"argv={argv_extras!r}: expected {key}={expected!r}, got {actual!r}"
            )

    @pytest.mark.parametrize(
        "argv_order",
        [
            ["--dry-run", "-v"],
            ["-v", "--dry-run"],
            ["--no-gpu", "--no-audio", "-v"],
            ["-v", "--no-audio", "--no-gpu"],
            ["--no-audio", "-v", "--no-gpu"],
        ],
    )
    @patch(MODULE)
    def test_flag_order_is_independent(self, mock_run_split, fake_video, argv_order):
        """Flag order does not alter which config fields end up set."""
        result = runner.invoke(app, ["split", str(fake_video), *argv_order])
        assert result.exit_code == 0
        config = mock_run_split.call_args[0][1]
        # Regardless of order, presence of each flag flips its field.
        if "--dry-run" in argv_order:
            assert config.dry_run is True
        if "--no-gpu" in argv_order:
            assert config.use_gpu is False
        if "--no-audio" in argv_order:
            assert config.no_audio is True

    @patch(MODULE)
    def test_verbose_routed_as_kwarg_not_config_in_combo(
        self, mock_run_split, fake_video
    ):
        """Combinations containing -v route verbose as run_split kwarg.

        ``verbose`` is not a SplitConfig field -- it's a display-side
        kwarg for ``run_split``.  Any combination including ``-v`` must
        preserve that routing.
        """
        result = runner.invoke(
            app,
            ["split", str(fake_video), "--dry-run", "--no-cache", "-v"],
        )
        assert result.exit_code == 0
        assert mock_run_split.call_args[1]["verbose"] is True
        # Config still holds the flag values.
        config = mock_run_split.call_args[0][1]
        assert config.dry_run is True
        assert config.no_cache is True


# --- detect command + split --from-metadata (#463) ---


def test_detect_help(render_help: Callable[[list[str]], str]):
    """detect --help renders and keeps --dry-run removed (detect *is* the dry-run).

    The absence check must run on normalized output: a raw
    `"--dry-run" not in result.stdout` passes unconditionally under colour, because
    rich splits option names into escape-separated spans (the same false-green that
    hid the --vtuber pin). The click-model assert carries the contract; the rendered
    negative alone would still pass if stripping ever regressed.
    """
    help_text = render_help(["detect", "--help"])
    assert "detect" in help_text.lower()
    # --dry-run removed from detect (it *is* the dry-run)
    assert _find_click_option("detect", "--dry-run") is None
    assert "--dry-run" not in help_text


@patch("allaganeye.commands.detect.run_detect")
def test_detect_invokes_run_detect(mock_run_detect, fake_video):
    result = runner.invoke(app, ["detect", str(fake_video), "-o", "out"])
    assert result.exit_code == 0, result.stdout
    mock_run_detect.assert_called_once()
    args, _kwargs = mock_run_detect.call_args
    assert args[0] == fake_video


@patch("allaganeye.commands.detect.run_detect")
def test_detect_vtuber_flag(mock_run_detect, fake_video):
    """--vtuber sets config.vtuber=True on detect (L3 B6)."""
    result = runner.invoke(app, ["detect", str(fake_video), "--vtuber"])
    assert result.exit_code == 0, result.stdout
    config = mock_run_detect.call_args[0][1]
    assert config.vtuber is True


@patch("allaganeye.commands.detect.run_detect")
def test_detect_vtuber_default_false(mock_run_detect, fake_video):
    """Omitting --vtuber keeps config.vtuber=False on detect (L3 B6)."""
    result = runner.invoke(app, ["detect", str(fake_video)])
    assert result.exit_code == 0, result.stdout
    config = mock_run_detect.call_args[0][1]
    assert config.vtuber is False


@patch("allaganeye.commands.detect.run_detect")
def test_detect_missing_file_exits_with_input_file_error(mock_run_detect, tmp_path):
    result = runner.invoke(app, ["detect", str(tmp_path / "missing.mp4")])
    assert result.exit_code == 2  # InputFileError
    mock_run_detect.assert_not_called()


@patch("allaganeye.commands.detect.run_detect")
def test_detect_rejects_unsupported_format(mock_run_detect, tmp_path):
    bad = tmp_path / "input.txt"
    bad.write_bytes(b"x")
    result = runner.invoke(app, ["detect", str(bad)])
    assert result.exit_code == 2  # InputFileError (unsupported)
    mock_run_detect.assert_not_called()


@patch("allaganeye.commands.split_matches.run_split_from_metadata")
def test_split_from_metadata_invokes_split_from_metadata(mock_run_from_meta, tmp_path):
    meta = tmp_path / "metadata.json"
    meta.write_text("{}", encoding="utf-8")
    result = runner.invoke(app, ["split", "--from-metadata", str(meta)])
    assert result.exit_code == 0, result.stdout
    mock_run_from_meta.assert_called_once()


def test_split_from_metadata_and_video_path_mutually_exclusive(fake_video, tmp_path):
    meta = tmp_path / "metadata.json"
    meta.write_text("{}", encoding="utf-8")
    result = runner.invoke(
        app, ["split", str(fake_video), "--from-metadata", str(meta)]
    )
    assert result.exit_code == 5  # ConfigValidationError


def test_split_requires_one_of_video_path_or_from_metadata():
    result = runner.invoke(app, ["split"])
    # typer shows help and exits when neither is given, or our mutex error
    assert result.exit_code != 0


@patch("allaganeye.commands.split_matches.run_split_from_metadata")
def test_split_from_metadata_dry_run_rejected(mock_run_from_meta, tmp_path):
    meta = tmp_path / "metadata.json"
    meta.write_text("{}", encoding="utf-8")
    result = runner.invoke(app, ["split", "--from-metadata", str(meta), "--dry-run"])
    assert result.exit_code == 5  # ConfigValidationError
    mock_run_from_meta.assert_not_called()


def test_split_from_metadata_missing_file_exits_with_input_file_error(tmp_path):
    result = runner.invoke(
        app, ["split", "--from-metadata", str(tmp_path / "nope.json")]
    )
    assert result.exit_code == 2  # InputFileError


# --- masked flag and vtuber/masked mutex (L3 A6) ---


@patch(MODULE)
def test_split_masked_flag_sets_config(mock_run_split, fake_video):
    """--masked sets config.masked=True and is threaded through to SplitConfig."""
    result = runner.invoke(app, ["split", str(fake_video), "--masked"])
    assert result.exit_code == 0, result.stdout
    config = mock_run_split.call_args[0][1]
    assert config.masked is True


@patch(MODULE)
def test_split_vtuber_and_masked_mutually_exclusive(mock_run_split, fake_video):
    """--vtuber and --masked together exit 5 without calling run_split."""
    result = runner.invoke(app, ["split", str(fake_video), "--vtuber", "--masked"])
    assert result.exit_code == 5
    mock_run_split.assert_not_called()
    combined = result.stdout + (result.stderr or "")
    assert "--vtuber and --masked are mutually exclusive" in combined
    assert result.stdout == "", f"stdout must be empty: {result.stdout!r}"


@patch("allaganeye.commands.detect.run_detect")
def test_detect_vtuber_and_masked_mutually_exclusive(mock_run_detect, fake_video):
    """--vtuber and --masked together exit 5 on detect without calling run_detect."""
    result = runner.invoke(app, ["detect", str(fake_video), "--vtuber", "--masked"])
    assert result.exit_code == 5
    mock_run_detect.assert_not_called()
    combined = result.stdout + (result.stderr or "")
    assert "--vtuber and --masked are mutually exclusive" in combined
    assert result.stdout == "", f"stdout must be empty: {result.stdout!r}"


# --- single-dash long-option hint (#440) ---


def test_suggest_long_option_hint_matches_top_level():
    """``-version`` argv -> suggest ``--version`` (top-level option, #440)."""
    from allaganeye.cli import _suggest_long_option_hint

    assert _suggest_long_option_hint(["-version"]) == "--version"


def test_suggest_long_option_hint_matches_subcommand_option():
    """``-gpu`` argv -> suggest ``--gpu`` (subcommand-only option, #440).

    Subcommand options like ``--gpu`` belong to ``split`` / ``detect``,
    not the top-level group, so the helper must walk subcommands too.
    """
    from allaganeye.cli import _suggest_long_option_hint

    assert _suggest_long_option_hint(["split", "-gpu"]) == "--gpu"


def test_suggest_long_option_hint_skips_real_short_flag():
    """``-V`` (real short alias, len 1) must NOT be treated as a typo (#440)."""
    from allaganeye.cli import _suggest_long_option_hint

    assert _suggest_long_option_hint(["-V"]) is None
    assert _suggest_long_option_hint(["-v"]) is None


def test_suggest_long_option_hint_skips_double_dash():
    """``--version`` is already correct, return ``None`` (#440)."""
    from allaganeye.cli import _suggest_long_option_hint

    assert _suggest_long_option_hint(["--version"]) is None


def test_suggest_long_option_hint_skips_unknown_token():
    """``-xyz`` where ``--xyz`` isn't a real option -> no misleading hint (#440)."""
    from allaganeye.cli import _suggest_long_option_hint

    assert _suggest_long_option_hint(["-xyz"]) is None


def test_suggest_long_option_hint_empty_argv():
    """Empty argv -> ``None`` (defensive, #440)."""
    from allaganeye.cli import _suggest_long_option_hint

    assert _suggest_long_option_hint([]) is None


def test_main_emits_hint_for_single_dash_version(monkeypatch, capsys):
    """``allaganeye -version`` triggers ``Did you mean --version?`` (#440)."""
    from allaganeye.cli import main

    monkeypatch.setattr("sys.argv", ["allaganeye", "-version"])
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code != 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Did you mean --version?" in combined


def test_main_emits_hint_for_single_dash_help(monkeypatch, capsys):
    """``allaganeye -help`` triggers ``Did you mean --help?`` (#440)."""
    from allaganeye.cli import main

    monkeypatch.setattr("sys.argv", ["allaganeye", "-help"])
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code != 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Did you mean --help?" in combined


def test_main_no_hint_when_double_dash_correct(monkeypatch, capsys):
    """``--version`` works normally without spurious hint (#440 regression guard)."""
    from allaganeye.cli import main

    monkeypatch.setenv("ALLAGANEYE_INTEGRITY_SKIP", "1")
    monkeypatch.setattr("sys.argv", ["allaganeye", "--version"])
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Did you mean" not in combined
    assert "allaganeye" in combined  # version output present


def test_main_short_alias_unchanged(monkeypatch, capsys):
    """``-V`` short alias still prints version, no hint emitted (#440 regression guard)."""
    from allaganeye.cli import main

    monkeypatch.setenv("ALLAGANEYE_INTEGRITY_SKIP", "1")
    monkeypatch.setattr("sys.argv", ["allaganeye", "-V"])
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Did you mean" not in combined
    assert "allaganeye" in combined


def test_main_no_misleading_hint_for_unrelated_typo(monkeypatch, capsys):
    """``-xyz`` (no matching long option) prints click error WITHOUT a hint (#440)."""
    from allaganeye.cli import main

    monkeypatch.setattr("sys.argv", ["allaganeye", "-xyz"])
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code != 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Did you mean" not in combined


# --- Version callback integrity check tests (#668) ---


def test_version_callback_exits_zero_when_integrity_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--version exit 0 + version output when integrity passes."""
    import typer

    from allaganeye import cli

    monkeypatch.setenv("ALLAGANEYE_INTEGRITY_SKIP", "1")

    with pytest.raises(typer.Exit) as exc_info:
        cli.version_callback(True)

    assert (exc_info.value.exit_code or 0) == 0


def test_version_callback_exits_seven_when_integrity_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """--version exit 7 when integrity fails, with stderr message."""
    import typer

    from allaganeye import cli, integrity
    from allaganeye.exceptions import IntegrityError

    def fake_check() -> None:
        raise IntegrityError(
            "integrity check failed: 1 missing, 0 size mismatch",
            context={
                "missing": ["lib/allaganeye/audio/refs/fanfare.npz"],
                "size_mismatch": [],
            },
        )

    monkeypatch.setattr(integrity, "check", fake_check)

    with pytest.raises(typer.Exit) as exc_info:
        cli.version_callback(True)

    assert exc_info.value.exit_code == 7
    captured = capsys.readouterr()
    assert "integrity check failed" in captured.err


def test_version_callback_returns_when_value_false() -> None:
    """value=False (no --version flag) returns silently."""
    from allaganeye import cli

    assert cli.version_callback(False) is None
