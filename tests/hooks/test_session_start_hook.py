"""Tests for .claude/hooks/session-start.sh (Refs #722).

Two scopes:
  1. Iron Law 6 sub-clause text (handoff + Step 0 references)  <- Task 10
  2. worktree-as-PR-head 自動検出 (gh pr list --head)            <- Task 11
"""

from pathlib import Path


# ---------- Iron Law 6 sub-clause text (Task 10) ----------


def test_session_start_outputs_iron_law_block(tmp_repo: Path, run_hook) -> None:
    """The fundamental Iron Law block is always emitted."""
    result = run_hook(".claude/hooks/session-start.sh")
    assert result.exit_code == 0
    assert "<EXTREMELY_IMPORTANT>" in result.stdout
    assert "Iron Law" in result.stdout


def test_session_start_includes_handoff_subclause(
    tmp_repo: Path, run_hook,
) -> None:
    """Iron Law 6 includes the new handoff sub-clause (#722)."""
    result = run_hook(".claude/hooks/session-start.sh")
    assert "resume-plan handoff" in result.stdout
    assert "EXECUTOR" in result.stdout
    assert "#722" in result.stdout


def test_session_start_mentions_step_zero_pre_flight(
    tmp_repo: Path, run_hook,
) -> None:
    """Iron Law 6 sub-clause references Step 0 hard-gate (#722)."""
    result = run_hook(".claude/hooks/session-start.sh")
    assert "Step 0" in result.stdout
    assert "gh pr list" in result.stdout
