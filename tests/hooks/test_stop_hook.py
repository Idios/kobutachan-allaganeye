"""Tests for .claude/hooks/stop.sh (Refs #707 / #710).

stop.sh is unchanged by the #710 NDJSON migration. These tests confirm:
- normal cleanup flow logs NDJSON lines from both cleanup scripts
- cleanup script failure (exit 42) is logged with `cleanup exit=42`
- missing cleanup script is logged with `NOT FOUND at <path>`
- hook itself always exits 0 even when cleanup fails
"""

from pathlib import Path


def _read_log(tmp_repo: Path) -> str:
    log = tmp_repo / ".claude" / "state" / "stop-hook.log"
    if not log.exists():
        return ""
    return log.read_text()


def test_stop_hook_logs_normal_cleanup(
    tmp_repo: Path, run_hook,
) -> None:
    """Both cleanup scripts present and succeed -> log records both blocks
    + NDJSON lines from each.
    """
    result = run_hook(".claude/hooks/stop.sh")
    assert result.exit_code == 0
    log = _read_log(tmp_repo)
    assert "stop.sh invoked" in log
    assert "cleanup-worktrees.sh: present" in log
    assert "cleanup-claude-branches.sh: present" in log
    # NDJSON summary events from both scripts appear in the log
    assert '"event":"summary"' in log
    assert '"script":"cleanup-worktrees"' in log
    assert '"script":"cleanup-claude-branches"' in log


def test_stop_hook_logs_cleanup_script_failure(
    tmp_repo: Path, run_hook,
) -> None:
    """Replace cleanup-worktrees.sh with a stub that exits 42 -> log records
    `cleanup exit=42`. stop.sh still exits 0.
    """
    # Replace the symlink/copy with a stub.
    target = tmp_repo / "scripts" / "cleanup-worktrees.sh"
    if target.is_symlink():
        target.unlink()
    elif target.exists():
        target.unlink()
    target.write_text("#!/usr/bin/env bash\nexit 42\n")
    target.chmod(0o755)

    result = run_hook(".claude/hooks/stop.sh")
    assert result.exit_code == 0
    log = _read_log(tmp_repo)
    assert "cleanup exit=42" in log


def test_stop_hook_handles_missing_cleanup_script(
    tmp_repo: Path, run_hook,
) -> None:
    """Remove cleanup-claude-branches.sh -> log records `NOT FOUND at <path>`."""
    target = tmp_repo / "scripts" / "cleanup-claude-branches.sh"
    if target.is_symlink():
        target.unlink()
    elif target.exists():
        target.unlink()

    result = run_hook(".claude/hooks/stop.sh")
    assert result.exit_code == 0
    log = _read_log(tmp_repo)
    assert "cleanup-claude-branches.sh: NOT FOUND" in log


def test_stop_hook_swallows_errors_and_exits_zero(
    tmp_repo: Path, run_hook,
) -> None:
    """Even when both cleanup scripts fail, stop.sh exits 0."""
    for name in ("cleanup-worktrees.sh", "cleanup-claude-branches.sh"):
        target = tmp_repo / "scripts" / name
        if target.is_symlink():
            target.unlink()
        elif target.exists():
            target.unlink()
        target.write_text("#!/usr/bin/env bash\nexit 99\n")
        target.chmod(0o755)

    result = run_hook(".claude/hooks/stop.sh")
    assert result.exit_code == 0
