"""Tests for .claude/hooks/session-start.sh (Refs #722).

Two scopes:
  1. Iron Law 6 sub-clause text (handoff + Step 0 references)  <- Task 10
  2. worktree-as-PR-head 自動検出 (gh pr list --head)            <- Task 11
"""

import os
import subprocess
import pytest
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


# ---------- worktree-as-PR-head detection (Task 11) ----------


def test_worktree_pr_head_detected_when_pr_open(
    tmp_repo: Path, run_hook, with_gh_stub,
) -> None:
    """gh stub returns non-empty JSON -> extra EXTREMELY_IMPORTANT block is emitted."""
    # Put tmp_repo on a claude/* branch
    subprocess.run(
        ["git", "checkout", "-q", "-b", "claude/some-pr-head"],
        cwd=tmp_repo, check=True,
    )
    with_gh_stub('[{"number":999,"title":"test","headRefName":"claude/some-pr-head"}]')
    result = run_hook(".claude/hooks/session-start.sh")
    assert result.exit_code == 0
    # Two EXTREMELY_IMPORTANT blocks total (Iron Law + worktree-PR-head)
    assert result.stdout.count("<EXTREMELY_IMPORTANT>") >= 2
    assert "worktree-as-PR-head" in result.stdout
    assert "claude/some-pr-head" in result.stdout


def test_worktree_pr_head_skipped_when_no_pr(
    tmp_repo: Path, run_hook, with_gh_stub,
) -> None:
    """gh stub returns [] -> only the base Iron Law block is emitted."""
    subprocess.run(
        ["git", "checkout", "-q", "-b", "claude/no-pr-yet"],
        cwd=tmp_repo, check=True,
    )
    with_gh_stub("[]")
    result = run_hook(".claude/hooks/session-start.sh")
    assert result.exit_code == 0
    # Only ONE EXTREMELY_IMPORTANT block (the Iron Law one)
    assert result.stdout.count("<EXTREMELY_IMPORTANT>") == 1
    assert "worktree-as-PR-head" not in result.stdout


def test_worktree_pr_head_skipped_for_non_claude_branch(
    tmp_repo: Path, run_hook, with_gh_stub,
) -> None:
    """Branch not starting with `claude/` -> detection skipped entirely (no gh call)."""
    # tmp_repo's default branch is develop-0.2.0 -- already non-claude
    with_gh_stub('[{"number":999,"title":"should not appear"}]')
    result = run_hook(".claude/hooks/session-start.sh")
    assert result.exit_code == 0
    assert result.stdout.count("<EXTREMELY_IMPORTANT>") == 1
    assert "worktree-as-PR-head" not in result.stdout


def test_worktree_pr_head_silent_skip_when_gh_missing(
    tmp_repo: Path, run_hook, monkeypatch,
) -> None:
    """gh not on PATH -> fail-soft: Iron Law still emitted, no extra block, exit 0."""
    import shutil as _shutil

    subprocess.run(
        ["git", "checkout", "-q", "-b", "claude/no-gh-env"],
        cwd=tmp_repo, check=True,
    )
    # Build a PATH that keeps bash (required by run_hook) but excludes gh.
    # On POSIX, standard system dirs are tried; on Windows we must keep the
    # Git-for-Windows usr/bin dir that ships bash.exe.
    bash_path = _shutil.which("bash")
    if bash_path is None:
        pytest.skip("bash not found; cannot run hook")
    bash_dir = str(Path(bash_path).parent)

    # Collect standard POSIX dirs that exist (empty on Windows, that's fine).
    posix_dirs = [p for p in ["/usr/bin", "/bin", "/usr/local/bin"] if Path(p).exists()]
    # Build minimal PATH: bash dir + any posix dirs that exist.
    minimal = os.pathsep.join([bash_dir, *posix_dirs])

    monkeypatch.setenv("PATH", minimal)
    # Ensure gh is not found in the minimal PATH
    if _shutil.which("gh", path=minimal):
        pytest.skip("gh available in minimal PATH; cannot exercise missing-gh branch")
    result = run_hook(".claude/hooks/session-start.sh")
    assert result.exit_code == 0
    assert result.stdout.count("<EXTREMELY_IMPORTANT>") == 1
    assert "worktree-as-PR-head" not in result.stdout
