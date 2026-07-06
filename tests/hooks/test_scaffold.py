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


def test_format_cleanup_log_smoke(
    tmp_path, run_hook, make_worktree_dir, tmp_repo, bash_exe
):
    """End-to-end: NDJSON from cleanup-worktrees.sh -> format-cleanup-log.sh ->
    human-readable lines.
    """
    import subprocess

    make_worktree_dir("foo", state="empty")
    cleanup = subprocess.run(
        [
            bash_exe,
            (tmp_repo / "scripts" / "cleanup-worktrees.sh").as_posix(),
            "--apply",
        ],
        cwd=tmp_repo,
        capture_output=True,
        text=True,
        check=True,
    )
    fmt = subprocess.run(
        [bash_exe, (tmp_repo / "scripts" / "format-cleanup-log.sh").as_posix()],
        input=cleanup.stdout,
        cwd=tmp_repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "[cleanup-worktrees] removed foo" in fmt.stdout
    assert "[cleanup-worktrees] summary:" in fmt.stdout


def test_resolved_bash_is_not_wsl_launcher(bash_exe: str) -> None:
    """On Windows, PATH `bash` is often the WSL launcher (WindowsApps), which
    cannot execute scripts given by Windows path -- backslashes are stripped
    and it exits 127 (#875). The resolver must never select it.
    """
    assert "windowsapps" not in bash_exe.lower()


def test_resolver_rejects_wsl_only_environment(monkeypatch) -> None:
    """Windows machine with no Git Bash and only the WSL launcher on PATH:
    the resolver returns None so bash_exe skips instead of failing (#875).
    """
    from tests.hooks import conftest as hooks_conftest

    monkeypatch.setattr(hooks_conftest.sys, "platform", "win32")
    monkeypatch.setattr(
        hooks_conftest.shutil,
        "which",
        lambda cmd: (
            r"C:\Users\u\AppData\Local\Microsoft\WindowsApps\bash.exe"
            if cmd == "bash"
            else None
        ),
    )
    # No Git Bash anywhere on disk (covers the hardcoded Program Files probes).
    monkeypatch.setattr(hooks_conftest.Path, "is_file", lambda self: False)
    assert hooks_conftest._resolve_bash() is None
