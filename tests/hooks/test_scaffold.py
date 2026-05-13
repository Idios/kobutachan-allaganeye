"""Smoke test: verify fixtures load and tmp_repo is set up correctly (Refs #710)."""

from pathlib import Path


def test_tmp_repo_has_git_dir(tmp_repo: Path) -> None:
    assert (tmp_repo / ".git").is_dir()


def test_tmp_repo_has_scripts_and_hooks(tmp_repo: Path) -> None:
    assert (tmp_repo / "scripts" / "cleanup-worktrees.sh").exists()
    assert (tmp_repo / "scripts" / "cleanup-claude-branches.sh").exists()
    assert (tmp_repo / ".claude" / "hooks" / "stop.sh").exists()


def test_schema_loads(cleanup_schema: dict) -> None:
    assert cleanup_schema["$id"].endswith("cleanup-output.schema.json")
    assert cleanup_schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_make_claude_branch_and_run_hook(make_claude_branch, run_hook) -> None:
    """End-to-end sanity: build a branch, run cleanup-claude-branches.sh (dry-run),
    confirm it executes without error.
    """
    make_claude_branch("scaffold-test", merged=True, age_seconds=86400 * 2)
    result = run_hook("scripts/cleanup-claude-branches.sh")
    # NOTE: At this point cleanup-claude-branches.sh still uses literal output
    # (NDJSON migration happens in Task 4). This smoke test asserts only that
    # the script runs and the fixture wiring works, not the output format.
    assert result.exit_code == 0


def test_format_cleanup_log_smoke(tmp_path, run_hook, make_worktree_dir, tmp_repo):
    """End-to-end: NDJSON from cleanup-worktrees.sh -> format-cleanup-log.sh ->
    human-readable lines.
    """
    import subprocess

    make_worktree_dir("foo", state="empty")
    cleanup = subprocess.run(
        ["bash", str(tmp_repo / "scripts" / "cleanup-worktrees.sh"), "--apply"],
        cwd=tmp_repo,
        capture_output=True,
        text=True,
        check=True,
    )
    fmt = subprocess.run(
        ["bash", str(tmp_repo / "scripts" / "format-cleanup-log.sh")],
        input=cleanup.stdout,
        cwd=tmp_repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "[cleanup-worktrees] removed foo" in fmt.stdout
    assert "[cleanup-worktrees] summary:" in fmt.stdout
