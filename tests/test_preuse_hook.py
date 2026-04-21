"""Tests for the PreToolUse gate (.claude/hooks/preuse.py, #401).

The hook is a standalone script invoked by Claude Code with a JSON
payload on stdin.  We import it as a module and drive the entry point
directly so the tests never spawn a subprocess, which keeps them fast
and deterministic on Windows.
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


def _invoke(event: dict, monkeypatch: pytest.MonkeyPatch) -> tuple[int, str]:
    """Drive ``preuse.main()`` with a fake stdin payload.  Return (rc, stderr)."""
    monkeypatch.setattr(
        sys, "stdin", io.StringIO(json.dumps(event) if event is not None else "")
    )
    err_buf = io.StringIO()
    monkeypatch.setattr(sys, "stderr", err_buf)
    rc = preuse.main()
    return rc, err_buf.getvalue()


def _bash_event(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


# ---------------------------------------------------------------
# Always-gated patterns
# ---------------------------------------------------------------


def test_pr_merge_always_gated(_isolated_paths, monkeypatch):
    """``gh pr merge`` is gated on the very first invocation (#401 G-2)."""
    rc, err = _invoke(_bash_event("gh pr merge 123 --squash"), monkeypatch)
    assert rc == 2
    assert "PR マージ" in err


def test_issue_close_single_allowed(_isolated_paths, monkeypatch):
    """Single ``gh issue close`` is allowed under bulk mode (#485).

    Claude is expected to have taken individual confirmation via
    AskUserQuestion before each close; the hook only catches genuine
    bulk shortcuts (3+ / 60s).
    """
    rc, err = _invoke(_bash_event("gh issue close 42"), monkeypatch)
    assert rc == 0
    assert err == ""


def test_issue_close_second_allowed(_isolated_paths, monkeypatch):
    """2 ``gh issue close`` calls in 60s are still allowed (below threshold=3)."""
    rc1, _ = _invoke(_bash_event("gh issue close 1"), monkeypatch)
    rc2, _ = _invoke(_bash_event("gh issue close 2"), monkeypatch)
    assert rc1 == 0
    assert rc2 == 0


def test_issue_close_third_in_window_triggers_gate(_isolated_paths, monkeypatch):
    """3rd ``gh issue close`` within 60s trips the bulk gate (#485)."""
    _invoke(_bash_event("gh issue close 1"), monkeypatch)
    _invoke(_bash_event("gh issue close 2"), monkeypatch)
    rc, err = _invoke(_bash_event("gh issue close 3"), monkeypatch)
    assert rc == 2
    assert "Issue クローズ" in err or "60 秒" in err


def test_issue_close_outside_window_resets(_isolated_paths, monkeypatch):
    """close entries older than 60s fall out of the sliding window (#485)."""
    stale = time.time() - 61
    preuse._append_op(_isolated_paths["state"], "gh issue close 1", stale)
    preuse._append_op(_isolated_paths["state"], "gh issue close 2", stale)
    # Fresh 3rd call is NOT gated because stale entries are discarded.
    rc, _ = _invoke(_bash_event("gh issue close 3"), monkeypatch)
    assert rc == 0


# ---------------------------------------------------------------
# ALLAGANEYE_PREUSE_BYPASS=1 (user-approved one-shot bypass, PR #491 review)
# ---------------------------------------------------------------


def test_bypass_allows_blocked_bulk_retry(_isolated_paths, monkeypatch):
    """After the 3rd close is blocked, prefix-bypass re-execution is allowed."""
    _invoke(_bash_event("gh issue close 1"), monkeypatch)
    _invoke(_bash_event("gh issue close 2"), monkeypatch)
    rc_block, _ = _invoke(_bash_event("gh issue close 3"), monkeypatch)
    assert rc_block == 2
    # User approves, Claude retries with bypass prefix.
    rc_bypass, err = _invoke(
        _bash_event("ALLAGANEYE_PREUSE_BYPASS=1 gh issue close 3"), monkeypatch
    )
    assert rc_bypass == 0
    assert "[preuse:bypass]" in err
    assert "gh issue close 3" in err


def test_bypass_allows_always_gated_pr_merge(_isolated_paths, monkeypatch):
    """Bypass also releases pr_merge (always mode) after user approval."""
    rc_block, _ = _invoke(_bash_event("gh pr merge 42 --squash"), monkeypatch)
    assert rc_block == 2
    rc_bypass, err = _invoke(
        _bash_event("ALLAGANEYE_PREUSE_BYPASS=1 gh pr merge 42 --squash"), monkeypatch
    )
    assert rc_bypass == 0
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
    _invoke(_bash_event("gh issue close 3"), monkeypatch)  # blocked & recorded
    _invoke(_bash_event("ALLAGANEYE_PREUSE_BYPASS=1 gh issue close 3"), monkeypatch)
    # Next un-prefixed close is still blocked -- counter includes the bypass.
    rc, _ = _invoke(_bash_event("gh issue close 4"), monkeypatch)
    assert rc == 2


def test_bypass_wrong_value_still_blocked(_isolated_paths, monkeypatch):
    """Only exactly ``ALLAGANEYE_PREUSE_BYPASS=1`` honors; ``=0`` is not magic."""
    _invoke(_bash_event("gh issue close 1"), monkeypatch)
    _invoke(_bash_event("gh issue close 2"), monkeypatch)
    rc, _ = _invoke(
        _bash_event("ALLAGANEYE_PREUSE_BYPASS=0 gh issue close 3"), monkeypatch
    )
    # The prefix is not recognized, so the command is evaluated as-is.  Because
    # `^gh ...` anchor requires the string to start with `gh`, no pattern
    # matches -- the command is allowed but NOT via bypass path.
    assert rc == 0


def test_bypass_block_message_mentions_bypass_option(_isolated_paths, monkeypatch):
    """Block stderr instructs Claude to retry with the bypass prefix."""
    _invoke(_bash_event("gh issue close 1"), monkeypatch)
    _invoke(_bash_event("gh issue close 2"), monkeypatch)
    _, err = _invoke(_bash_event("gh issue close 3"), monkeypatch)
    assert "ALLAGANEYE_PREUSE_BYPASS=1" in err


# ---------------------------------------------------------------
# Bulk-gated patterns
# ---------------------------------------------------------------


def test_issue_create_under_threshold_allowed(_isolated_paths, monkeypatch):
    """2 ``gh issue create`` calls in 60s are allowed (below threshold=3)."""
    rc1, _ = _invoke(_bash_event("gh issue create --title a"), monkeypatch)
    rc2, _ = _invoke(_bash_event("gh issue create --title b"), monkeypatch)
    assert rc1 == 0
    assert rc2 == 0


def test_issue_create_third_in_window_triggers_gate(_isolated_paths, monkeypatch):
    """3rd ``gh issue create`` within 60s trips the bulk gate (#401 G-1)."""
    _invoke(_bash_event("gh issue create --title a"), monkeypatch)
    _invoke(_bash_event("gh issue create --title b"), monkeypatch)
    rc, err = _invoke(_bash_event("gh issue create --title c"), monkeypatch)
    assert rc == 2
    assert "Issue 起票" in err or "60 秒" in err


def test_issue_create_outside_window_resets(_isolated_paths, monkeypatch):
    """Entries older than 60s fall out of the sliding window."""
    # Pre-populate state with 2 stale entries (61s ago).
    stale = time.time() - 61
    preuse._append_op(_isolated_paths["state"], "gh issue create --title old1", stale)
    preuse._append_op(_isolated_paths["state"], "gh issue create --title old2", stale)

    # Fresh 3rd call should *not* be gated because stale entries are
    # discarded at read time.
    rc, _ = _invoke(_bash_event("gh issue create --title fresh"), monkeypatch)
    assert rc == 0


def test_deferred_label_second_in_window_triggers_gate(_isolated_paths, monkeypatch):
    """2 consecutive ``deferred`` label assignments in 60s are gated (#401 G-4)."""
    rc1, _ = _invoke(_bash_event('gh issue edit 1 --add-label "deferred"'), monkeypatch)
    rc2, err2 = _invoke(
        _bash_event('gh issue edit 2 --add-label "deferred"'), monkeypatch
    )
    assert rc1 == 0
    assert rc2 == 2
    assert "deferred" in err2


def test_non_deferred_label_not_gated(_isolated_paths, monkeypatch):
    """Other label edits (P1 / role:*) are not caught by the deferred gate."""
    # Even 3 P1-high assignments should stay allowed -- not on the
    # gated list.
    for i in range(3):
        rc, _ = _invoke(
            _bash_event(f'gh issue edit {i} --add-label "P1-high"'), monkeypatch
        )
        assert rc == 0


# ---------------------------------------------------------------
# Non-gated / disabled paths
# ---------------------------------------------------------------


def test_non_bash_tool_untouched(_isolated_paths, monkeypatch):
    """Other tools (Read / Edit / Write) are never gated."""
    event = {"tool_name": "Edit", "tool_input": {"file_path": "foo", "old_string": "a"}}
    rc, err = _invoke(event, monkeypatch)
    assert rc == 0
    assert err == ""


def test_arbitrary_bash_untouched(_isolated_paths, monkeypatch):
    """Bash commands outside the gated list run freely."""
    rc, _ = _invoke(_bash_event("pytest -q"), monkeypatch)
    assert rc == 0


def test_empty_command_untouched(_isolated_paths, monkeypatch):
    """Whitespace-only command is treated as no-op."""
    rc, _ = _invoke(_bash_event("   "), monkeypatch)
    assert rc == 0


def test_gate_can_be_disabled_globally(_isolated_paths, monkeypatch):
    """Setting ``pretooluse_gate: false`` disables every gate (#401 switch)."""
    _isolated_paths["settings"].parent.mkdir(parents=True, exist_ok=True)
    _isolated_paths["settings"].write_text(
        json.dumps({"pretooluse_gate": False}), encoding="utf-8"
    )

    rc, _ = _invoke(_bash_event("gh pr merge 1"), monkeypatch)
    assert rc == 0


def test_gate_defaults_on_when_settings_missing(_isolated_paths, monkeypatch):
    """Absent / malformed settings file defaults to enabled (fail-safe)."""
    # No settings file at all.
    rc, _ = _invoke(_bash_event("gh pr merge 1"), monkeypatch)
    assert rc == 2


def test_malformed_settings_keeps_gate_on(_isolated_paths, monkeypatch):
    _isolated_paths["settings"].parent.mkdir(parents=True, exist_ok=True)
    _isolated_paths["settings"].write_text("not json", encoding="utf-8")
    rc, _ = _invoke(_bash_event("gh pr merge 1"), monkeypatch)
    assert rc == 2


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
    rc, _ = _invoke(_bash_event("gh issue create --title a"), monkeypatch)
    assert rc == 0


# ---------------------------------------------------------------
# Malformed payloads
# ---------------------------------------------------------------


def test_empty_stdin(_isolated_paths, monkeypatch):
    """Empty payload is a no-op pass (rc=0)."""
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    err_buf = io.StringIO()
    monkeypatch.setattr(sys, "stderr", err_buf)
    rc = preuse.main()
    assert rc == 0


def test_invalid_json_stdin(_isolated_paths, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("<not-json>"))
    err_buf = io.StringIO()
    monkeypatch.setattr(sys, "stderr", err_buf)
    rc = preuse.main()
    assert rc == 0


def test_missing_tool_input(_isolated_paths, monkeypatch):
    event = {"tool_name": "Bash"}
    rc, _ = _invoke(event, monkeypatch)
    assert rc == 0


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
