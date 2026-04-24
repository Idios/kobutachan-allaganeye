"""Tests for the PreToolUse gate (.claude/hooks/preuse.py, #401 / #559).

The hook is a standalone script invoked by Claude Code with a JSON
payload on stdin.  We import it as a module and drive the entry point
directly so the tests never spawn a subprocess, which keeps them fast
and deterministic on Windows.

Gate activation contract (#559):
- Exit code is always 0 from ``main()``.
- On match, stdout contains a JSON payload with
  ``hookSpecificOutput.permissionDecision == "ask"`` so Claude Code
  surfaces the permission prompt to the user.
- Non-match / bypass / disabled paths leave stdout empty.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import time
from pathlib import Path

import pytest

_HOOK_PATH = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "preuse.py"


def _load_preuse_module():
    """Load the hook script as a module so tests can call ``main()``.

    The script lives outside ``allaganeye/`` so there's no regular import
    path; ``importlib.util`` is the lightest way in without polluting
    ``sys.path``.
    """
    spec = importlib.util.spec_from_file_location("preuse_hook", _HOOK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


preuse = _load_preuse_module()


# ---------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------


@pytest.fixture
def _isolated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect state / settings paths into a tmp directory per test."""
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    state_path = state_dir / "recent_ops.json"
    settings_path = tmp_path / ".claude" / "settings.local.json"

    monkeypatch.setattr(preuse, "_state_path", lambda: state_path)
    monkeypatch.setattr(preuse, "_settings_local_path", lambda: settings_path)

    return {"state": state_path, "settings": settings_path}


def _invoke(event: dict, monkeypatch: pytest.MonkeyPatch) -> tuple[int, str, str]:
    """Drive ``preuse.main()`` with a fake stdin payload.

    Returns ``(rc, stderr, stdout)``.  stdout is where the permission
    prompt payload lands under the #559 ask protocol; stderr is the
    audit log line.
    """
    monkeypatch.setattr(
        sys, "stdin", io.StringIO(json.dumps(event) if event is not None else "")
    )
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out_buf)
    monkeypatch.setattr(sys, "stderr", err_buf)
    rc = preuse.main()
    return rc, err_buf.getvalue(), out_buf.getvalue()


def _bash_event(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _assert_ask(rc: int, stdout: str) -> str:
    """Validate a ``permissionDecision: "ask"`` hookSpecificOutput payload.

    Returns the ``permissionDecisionReason`` body so callers can spot-check
    that pattern-specific messaging (e.g. "PR マージ", "Issue クローズ")
    reached the prompt text shown to the user.
    """
    assert rc == 0, f"ask path must exit 0; got {rc}"
    assert stdout.strip(), "ask path must emit stdout JSON"
    payload = json.loads(stdout)
    hook_out = payload.get("hookSpecificOutput")
    assert isinstance(hook_out, dict), f"missing hookSpecificOutput: {payload!r}"
    assert hook_out.get("hookEventName") == "PreToolUse"
    assert hook_out.get("permissionDecision") == "ask"
    reason = hook_out.get("permissionDecisionReason")
    assert isinstance(reason, str) and reason, "reason must be non-empty string"
    return reason


# ---------------------------------------------------------------
# Always-gated patterns
# ---------------------------------------------------------------


def test_pr_merge_triggers_ask(_isolated_paths, monkeypatch):
    """``gh pr merge`` requests a permission prompt on every invocation (#559)."""
    rc, _err, out = _invoke(_bash_event("gh pr merge 123 --squash"), monkeypatch)
    reason = _assert_ask(rc, out)
    assert "PR マージ" in reason
    assert "gh pr merge 123 --squash" in reason


def test_issue_close_single_allowed(_isolated_paths, monkeypatch):
    """Single ``gh issue close`` is allowed under bulk mode (#485).

    Claude is expected to have taken individual confirmation via
    AskUserQuestion before each close; the hook only catches genuine
    bulk shortcuts (3+ / 60s).
    """
    rc, err, out = _invoke(_bash_event("gh issue close 42"), monkeypatch)
    assert rc == 0
    assert err == ""
    assert out == ""


def test_issue_close_second_allowed(_isolated_paths, monkeypatch):
    """2 ``gh issue close`` calls in 60s are still allowed (below threshold=3)."""
    rc1, _, out1 = _invoke(_bash_event("gh issue close 1"), monkeypatch)
    rc2, _, out2 = _invoke(_bash_event("gh issue close 2"), monkeypatch)
    assert rc1 == 0
    assert rc2 == 0
    assert out1 == ""
    assert out2 == ""


def test_issue_close_third_in_window_triggers_ask(_isolated_paths, monkeypatch):
    """3rd ``gh issue close`` within 60s trips the bulk gate (#485 / #559)."""
    _invoke(_bash_event("gh issue close 1"), monkeypatch)
    _invoke(_bash_event("gh issue close 2"), monkeypatch)
    rc, _, out = _invoke(_bash_event("gh issue close 3"), monkeypatch)
    reason = _assert_ask(rc, out)
    assert "Issue クローズ" in reason or "60 秒" in reason


def test_issue_close_outside_window_resets(_isolated_paths, monkeypatch):
    """close entries older than 60s fall out of the sliding window (#485)."""
    stale = time.time() - 61
    preuse._append_op(_isolated_paths["state"], "gh issue close 1", stale)
    preuse._append_op(_isolated_paths["state"], "gh issue close 2", stale)
    # Fresh 3rd call is NOT gated because stale entries are discarded.
    rc, _, out = _invoke(_bash_event("gh issue close 3"), monkeypatch)
    assert rc == 0
    assert out == ""


# ---------------------------------------------------------------
# Ask payload structural checks (#559)
# ---------------------------------------------------------------


def test_ask_payload_is_single_line_json(_isolated_paths, monkeypatch):
    """The ask payload is a single JSON object on stdout (hooks wire format)."""
    rc, _, out = _invoke(_bash_event("gh pr merge 1"), monkeypatch)
    assert rc == 0
    # Exactly one JSON object followed by an optional newline.
    stripped = out.strip()
    payload = json.loads(stripped)
    # Top-level must contain hookSpecificOutput per Claude Code PreToolUse spec.
    assert set(payload.keys()) == {"hookSpecificOutput"}
    hook_out = payload["hookSpecificOutput"]
    assert hook_out["hookEventName"] == "PreToolUse"
    assert hook_out["permissionDecision"] == "ask"
    assert "permissionDecisionReason" in hook_out


def test_ask_reason_has_command_preview_and_pattern_key(_isolated_paths, monkeypatch):
    """Prompt body includes pattern key tag and a command preview for the user."""
    cmd = "gh pr merge 456 --squash --delete-branch"
    rc, _, out = _invoke(_bash_event(cmd), monkeypatch)
    reason = _assert_ask(rc, out)
    assert "[pr_merge]" in reason
    assert cmd in reason


def test_ask_stderr_audit_log_present(_isolated_paths, monkeypatch):
    """stderr still carries an audit log for offline review (#559)."""
    rc, err, out = _invoke(_bash_event("gh pr merge 1"), monkeypatch)
    _assert_ask(rc, out)
    assert "[preuse:pr_merge]" in err
    assert "ask -> user permission prompt" in err


# ---------------------------------------------------------------
# ALLAGANEYE_PREUSE_BYPASS=1 (escape hatch, #485 / PR #491 review / #559 retained)
# ---------------------------------------------------------------


def test_bypass_allows_blocked_bulk_retry(_isolated_paths, monkeypatch):
    """After the 3rd close triggers ask, prefix-bypass re-execution is allowed."""
    _invoke(_bash_event("gh issue close 1"), monkeypatch)
    _invoke(_bash_event("gh issue close 2"), monkeypatch)
    rc_ask, _, out_ask = _invoke(_bash_event("gh issue close 3"), monkeypatch)
    _assert_ask(rc_ask, out_ask)
    # User approves, Claude retries with bypass prefix.
    rc_bypass, err, out = _invoke(
        _bash_event("ALLAGANEYE_PREUSE_BYPASS=1 gh issue close 3"), monkeypatch
    )
    assert rc_bypass == 0
    assert out == ""
    assert "[preuse:bypass]" in err
    assert "gh issue close 3" in err


def test_bypass_allows_always_gated_pr_merge(_isolated_paths, monkeypatch):
    """Bypass also releases pr_merge (always mode) after user approval."""
    rc_ask, _, out_ask = _invoke(_bash_event("gh pr merge 42 --squash"), monkeypatch)
    _assert_ask(rc_ask, out_ask)
    rc_bypass, err, out = _invoke(
        _bash_event("ALLAGANEYE_PREUSE_BYPASS=1 gh pr merge 42 --squash"), monkeypatch
    )
    assert rc_bypass == 0
    assert out == ""
    assert "[preuse:bypass]" in err


def test_bypass_records_stripped_command_to_state(_isolated_paths, monkeypatch):
    """State keeps the underlying command so bulk counters stay accurate."""
    _invoke(_bash_event("ALLAGANEYE_PREUSE_BYPASS=1 gh issue close 1"), monkeypatch)
    data = json.loads(_isolated_paths["state"].read_text(encoding="utf-8"))
    assert any(entry.get("cmd") == "gh issue close 1" for entry in data)
    # The prefix must NOT be stored -- future _classify relies on ^gh ... anchor.
    assert not any("ALLAGANEYE_PREUSE_BYPASS" in entry.get("cmd", "") for entry in data)


def test_bypass_counts_toward_subsequent_bulk(_isolated_paths, monkeypatch):
    """Bypassed close still adds to the 60s window for non-bypassed retries."""
    _invoke(_bash_event("gh issue close 1"), monkeypatch)
    _invoke(_bash_event("gh issue close 2"), monkeypatch)
    _invoke(_bash_event("gh issue close 3"), monkeypatch)  # ask (NOT recorded, #513)
    _invoke(_bash_event("ALLAGANEYE_PREUSE_BYPASS=1 gh issue close 3"), monkeypatch)
    # Next un-prefixed close triggers ask -- bypass entry (3 in window) plus
    # current (4) exceed threshold=3.
    rc, _, out = _invoke(_bash_event("gh issue close 4"), monkeypatch)
    _assert_ask(rc, out)


def test_bypass_wrong_value_still_passes_through(_isolated_paths, monkeypatch):
    """Only exactly ``ALLAGANEYE_PREUSE_BYPASS=1`` honors; ``=0`` is not magic."""
    _invoke(_bash_event("gh issue close 1"), monkeypatch)
    _invoke(_bash_event("gh issue close 2"), monkeypatch)
    rc, _, out = _invoke(
        _bash_event("ALLAGANEYE_PREUSE_BYPASS=0 gh issue close 3"), monkeypatch
    )
    # The prefix is not recognized, so the command is evaluated as-is.  Because
    # `^gh ...` anchor requires the string to start with `gh`, no pattern
    # matches -- the command is allowed but NOT via bypass path.
    assert rc == 0
    assert out == ""


# ---------------------------------------------------------------
# Bulk-gated patterns
# ---------------------------------------------------------------


def test_issue_create_under_threshold_allowed(_isolated_paths, monkeypatch):
    """2 ``gh issue create`` calls in 60s are allowed (below threshold=3)."""
    rc1, _, out1 = _invoke(_bash_event("gh issue create --title a"), monkeypatch)
    rc2, _, out2 = _invoke(_bash_event("gh issue create --title b"), monkeypatch)
    assert rc1 == 0
    assert rc2 == 0
    assert out1 == ""
    assert out2 == ""


def test_issue_create_third_in_window_triggers_ask(_isolated_paths, monkeypatch):
    """3rd ``gh issue create`` within 60s trips the bulk gate (#401 G-1 / #559)."""
    _invoke(_bash_event("gh issue create --title a"), monkeypatch)
    _invoke(_bash_event("gh issue create --title b"), monkeypatch)
    rc, _, out = _invoke(_bash_event("gh issue create --title c"), monkeypatch)
    reason = _assert_ask(rc, out)
    assert "Issue 起票" in reason or "60 秒" in reason


def test_issue_create_outside_window_resets(_isolated_paths, monkeypatch):
    """Entries older than 60s fall out of the sliding window."""
    # Pre-populate state with 2 stale entries (61s ago).
    stale = time.time() - 61
    preuse._append_op(_isolated_paths["state"], "gh issue create --title old1", stale)
    preuse._append_op(_isolated_paths["state"], "gh issue create --title old2", stale)

    # Fresh 3rd call should *not* be gated because stale entries are
    # discarded at read time.
    rc, _, out = _invoke(_bash_event("gh issue create --title fresh"), monkeypatch)
    assert rc == 0
    assert out == ""


def test_deferred_label_second_in_window_triggers_ask(_isolated_paths, monkeypatch):
    """2 consecutive ``deferred`` label assignments in 60s are gated (#401 G-4)."""
    rc1, _, out1 = _invoke(
        _bash_event('gh issue edit 1 --add-label "deferred"'), monkeypatch
    )
    assert rc1 == 0
    assert out1 == ""
    rc2, _, out2 = _invoke(
        _bash_event('gh issue edit 2 --add-label "deferred"'), monkeypatch
    )
    reason2 = _assert_ask(rc2, out2)
    assert "deferred" in reason2


def test_non_deferred_label_not_gated(_isolated_paths, monkeypatch):
    """Other label edits (P1 / role:*) are not caught by the deferred gate."""
    # Even 3 P1-high assignments should stay allowed -- not on the
    # gated list.
    for i in range(3):
        rc, _, out = _invoke(
            _bash_event(f'gh issue edit {i} --add-label "P1-high"'), monkeypatch
        )
        assert rc == 0
        assert out == ""


# ---------------------------------------------------------------
# Non-gated / disabled paths
# ---------------------------------------------------------------


def test_non_bash_tool_untouched(_isolated_paths, monkeypatch):
    """Other tools (Read / Edit / Write) are never gated."""
    event = {"tool_name": "Edit", "tool_input": {"file_path": "foo", "old_string": "a"}}
    rc, err, out = _invoke(event, monkeypatch)
    assert rc == 0
    assert err == ""
    assert out == ""


def test_arbitrary_bash_untouched(_isolated_paths, monkeypatch):
    """Bash commands outside the gated list run freely."""
    rc, _, out = _invoke(_bash_event("pytest -q"), monkeypatch)
    assert rc == 0
    assert out == ""


def test_empty_command_untouched(_isolated_paths, monkeypatch):
    """Whitespace-only command is treated as no-op."""
    rc, _, out = _invoke(_bash_event("   "), monkeypatch)
    assert rc == 0
    assert out == ""


def test_gate_can_be_disabled_globally(_isolated_paths, monkeypatch):
    """Setting ``pretooluse_gate: false`` disables every gate (#401 switch)."""
    _isolated_paths["settings"].parent.mkdir(parents=True, exist_ok=True)
    _isolated_paths["settings"].write_text(
        json.dumps({"pretooluse_gate": False}), encoding="utf-8"
    )

    rc, _, out = _invoke(_bash_event("gh pr merge 1"), monkeypatch)
    assert rc == 0
    assert out == ""


def test_gate_defaults_on_when_settings_missing(_isolated_paths, monkeypatch):
    """Absent / malformed settings file defaults to enabled (fail-safe)."""
    # No settings file at all.
    rc, _, out = _invoke(_bash_event("gh pr merge 1"), monkeypatch)
    _assert_ask(rc, out)


def test_malformed_settings_keeps_gate_on(_isolated_paths, monkeypatch):
    _isolated_paths["settings"].parent.mkdir(parents=True, exist_ok=True)
    _isolated_paths["settings"].write_text("not json", encoding="utf-8")
    rc, _, out = _invoke(_bash_event("gh pr merge 1"), monkeypatch)
    _assert_ask(rc, out)


# ---------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------


def test_state_file_created_on_first_op(_isolated_paths, monkeypatch):
    """Running a gated command writes to ``.claude/state/recent_ops.json``."""
    assert not _isolated_paths["state"].exists()
    _invoke(_bash_event("gh issue create --title a"), monkeypatch)
    assert _isolated_paths["state"].exists()
    data = json.loads(_isolated_paths["state"].read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert any("gh issue create" in entry.get("cmd", "") for entry in data)


def test_corrupt_state_fails_open(_isolated_paths, monkeypatch):
    """Garbage state file is tolerated (read returns [], write overwrites)."""
    _isolated_paths["state"].write_text("not json", encoding="utf-8")
    # Should not raise, nor falsely trip the bulk gate.
    rc, _, out = _invoke(_bash_event("gh issue create --title a"), monkeypatch)
    assert rc == 0
    assert out == ""


# ---------------------------------------------------------------
# Malformed payloads
# ---------------------------------------------------------------


def test_empty_stdin(_isolated_paths, monkeypatch):
    """Empty payload is a no-op pass (rc=0)."""
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out_buf)
    monkeypatch.setattr(sys, "stderr", err_buf)
    rc = preuse.main()
    assert rc == 0
    assert out_buf.getvalue() == ""


def test_invalid_json_stdin(_isolated_paths, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("<not-json>"))
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out_buf)
    monkeypatch.setattr(sys, "stderr", err_buf)
    rc = preuse.main()
    assert rc == 0
    assert out_buf.getvalue() == ""


def test_missing_tool_input(_isolated_paths, monkeypatch):
    event = {"tool_name": "Bash"}
    rc, _, out = _invoke(event, monkeypatch)
    assert rc == 0
    assert out == ""


# ---------------------------------------------------------------
# State hygiene: asked commands must NOT inflate bulk counters (#513 / #559)
# ---------------------------------------------------------------


def test_asked_bulk_command_not_recorded(_isolated_paths, monkeypatch):
    """Ask'd bulk command must not be recorded to state (#513 A retained in #559).

    Previously every blocked invocation was appended to state, so the
    bulk counter included ghost entries for commands that never ran.
    Under the ask protocol the hook also cannot observe whether the
    user ultimately approved, so the same hygiene rule applies.
    """
    _invoke(_bash_event("gh issue close 1"), monkeypatch)
    _invoke(_bash_event("gh issue close 2"), monkeypatch)
    rc, _, out = _invoke(_bash_event("gh issue close 3"), monkeypatch)
    _assert_ask(rc, out)
    data = json.loads(_isolated_paths["state"].read_text(encoding="utf-8"))
    # Only the two allowed closes are recorded; the ask'd 3rd is dropped.
    assert len(data) == 2
    assert all("close 3" not in entry.get("cmd", "") for entry in data)


def test_asked_always_gated_command_not_recorded(_isolated_paths, monkeypatch):
    """Ask'd always-mode pr_merge must not create any state entry (#513 / #559)."""
    rc, _, out = _invoke(_bash_event("gh pr merge 42 --squash"), monkeypatch)
    _assert_ask(rc, out)
    if _isolated_paths["state"].exists():
        data = json.loads(_isolated_paths["state"].read_text(encoding="utf-8"))
        assert data == []


def test_forgotten_bypass_retry_does_not_inflate_counter(_isolated_paths, monkeypatch):
    """Un-prefixed retries of an ask'd command must not grow state (#513 / #559).

    Regression guard for the scenario: the permission prompt is surfaced
    repeatedly (user keeps cancelling / Claude retries) and must not
    grow ``recent_ops.json``.  Only the eventual bypass-prefixed call
    (or a real un-gated execution) writes state.
    """
    _invoke(_bash_event("gh issue close 1"), monkeypatch)
    _invoke(_bash_event("gh issue close 2"), monkeypatch)
    for _ in range(5):
        rc, _, out = _invoke(_bash_event("gh issue close 3"), monkeypatch)
        _assert_ask(rc, out)
    data = json.loads(_isolated_paths["state"].read_text(encoding="utf-8"))
    assert len(data) == 2
    rc, _, out = _invoke(
        _bash_event("ALLAGANEYE_PREUSE_BYPASS=1 gh issue close 3"), monkeypatch
    )
    assert rc == 0
    assert out == ""
    data = json.loads(_isolated_paths["state"].read_text(encoding="utf-8"))
    assert len(data) == 3


def test_ask_reason_mentions_prompt_flow(_isolated_paths, monkeypatch):
    """Reason body tells the user this came from the permission prompt path.

    Replaces the previous assertion that stderr mentioned the bypass
    prefix: under #559 the primary UX is the Claude Code prompt, and
    the reason text is what the user actually reads.
    """
    _invoke(_bash_event("gh issue create --title a"), monkeypatch)
    _invoke(_bash_event("gh issue create --title b"), monkeypatch)
    rc, _, out = _invoke(_bash_event("gh issue create --title c"), monkeypatch)
    reason = _assert_ask(rc, out)
    assert "permission prompt" in reason
    assert "allow" in reason
    assert "deny" in reason


# ---------------------------------------------------------------
# Classify helper (direct unit coverage)
# ---------------------------------------------------------------


def test_classify_no_match_returns_none():
    key, msg = preuse._classify("echo hello", [])
    assert key is None
    assert msg is None


def test_classify_bulk_threshold_requires_prior_count():
    """Bulk mode only gates on the Nth invocation (count includes current)."""
    now = time.time()
    recent: list[dict] = []
    # 1st: not gated (count=1)
    key, _ = preuse._classify("gh issue create --title a", recent)
    assert key is None
    recent.append({"cmd": "gh issue create --title a", "ts": now})
    # 2nd: not gated (count=2, threshold=3)
    key, _ = preuse._classify("gh issue create --title b", recent)
    assert key is None
    recent.append({"cmd": "gh issue create --title b", "ts": now})
    # 3rd: gated (count would be 3, threshold met)
    key, _ = preuse._classify("gh issue create --title c", recent)
    assert key == "issue_create_bulk"
