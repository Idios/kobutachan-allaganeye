"""Fixtures for testing .claude/hooks/*.sh and scripts/cleanup-*.sh (Refs #710).

The hooks under test live in PROJECT_ROOT/.claude/hooks/ and PROJECT_ROOT/scripts/.
Tests run them under an isolated tmp_path so that the developer's real worktree
is never touched.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Callable
from typing import Literal

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = PROJECT_ROOT / "schemas" / "cleanup-output.schema.json"


@dataclass
class HookResult:
    """Result of a hook script invocation."""

    stdout: str
    stderr: str
    exit_code: int
    ndjson: list[dict] = field(default_factory=list)


def _symlink_or_copy(src: Path, dst: Path) -> None:
    """Use symlink when possible; on Windows without Developer Mode fall back to copy."""
    try:
        os.symlink(src, dst, target_is_directory=src.is_dir())
    except (OSError, NotImplementedError):
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """Isolated git repo with .claude/ and scripts/ wired from project root.

    The repo has an initial commit on `develop-0.2.0` (a fixture-internal
    branch name kept for historical continuity; it matches the develop-*
    glob, so cleanup-claude-branches.sh's merge-base logic resolves
    correctly against it regardless of the project's current base branch).
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "develop-0.2.0"], cwd=repo, check=True)
    (repo / "README.md").write_text("test\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@t.invalid",
            "-c",
            "user.name=t",
            "commit",
            "-qm",
            "init",
        ],
        cwd=repo,
        check=True,
    )

    # Wire in real scripts/ + .claude/hooks/ via symlink (fallback: copy).
    _symlink_or_copy(PROJECT_ROOT / "scripts", repo / "scripts")
    (repo / ".claude").mkdir()
    _symlink_or_copy(PROJECT_ROOT / ".claude" / "hooks", repo / ".claude" / "hooks")
    return repo


@pytest.fixture
def make_claude_branch(tmp_repo: Path) -> Callable[..., str]:
    """Create a `claude/<slug>` branch with controllable merged / age properties.

    Args of the returned callable:
      slug: branch name suffix after `claude/`
      merged: if True, branch is merged into develop-0.2.0 (= is-ancestor true)
      age_seconds: forge committer date to `now - age_seconds`

    Returns: full branch ref (`claude/<slug>`).

    Post-condition: HEAD is always on `develop-0.2.0` after the call,
    regardless of the `merged` param. Composable across multiple invocations.
    """

    def _make(slug: str, *, merged: bool, age_seconds: int) -> str:
        branch = f"claude/{slug}"
        # Create branch from develop-0.2.0
        subprocess.run(
            ["git", "checkout", "-q", "-b", branch], cwd=tmp_repo, check=True
        )
        # Make a commit with a forged committer date.
        # Stage only the test file (not scripts/ or .claude/hooks/ which are
        # wired in from PROJECT_ROOT and must not be tracked by the tmp repo's
        # git history -- if tracked, `git checkout develop-0.2.0` for a
        # merged=False branch would delete them from the working tree).
        (tmp_repo / f"{slug}.txt").write_text("x")
        subprocess.run(["git", "add", "--", f"{slug}.txt"], cwd=tmp_repo, check=True)
        forged_ts = int(time.time()) - age_seconds
        env = {
            **os.environ,
            "GIT_COMMITTER_DATE": f"@{forged_ts} +0000",
            "GIT_AUTHOR_DATE": f"@{forged_ts} +0000",
        }
        subprocess.run(
            [
                "git",
                "-c",
                "user.email=t@t.invalid",
                "-c",
                "user.name=t",
                "commit",
                "-qm",
                f"work {slug}",
            ],
            cwd=tmp_repo,
            env=env,
            check=True,
        )
        if merged:
            # Merge into develop-0.2.0
            subprocess.run(
                ["git", "checkout", "-q", "develop-0.2.0"], cwd=tmp_repo, check=True
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.email=t@t.invalid",
                    "-c",
                    "user.name=t",
                    "merge",
                    "-q",
                    "--no-ff",
                    branch,
                    "-m",
                    f"merge {branch}",
                ],
                cwd=tmp_repo,
                check=True,
            )
        else:
            subprocess.run(
                ["git", "checkout", "-q", "develop-0.2.0"], cwd=tmp_repo, check=True
            )

        # cleanup-claude-branches.sh requires an `origin/develop-0.2.0` ref to test
        # ancestor-ship. Mirror local develop-0.2.0 into refs/remotes/origin/.
        subprocess.run(
            ["git", "update-ref", "refs/remotes/origin/develop-0.2.0", "HEAD"],
            cwd=tmp_repo,
            check=True,
        )
        return branch

    return _make


@pytest.fixture
def make_worktree_dir(tmp_repo: Path) -> Callable[..., Path]:
    """Create .claude/worktrees/<name>/ in one of 3 states.

    state:
      "empty"     -- empty directory (cleanup target)
      "non_empty" -- has a stray.txt inside (skipped, rmdir would fail)
      "active"   -- has .git file referencing tmp_repo's main .git (active worktree)
    """

    def _make(name: str, state: Literal["empty", "non_empty", "active"]) -> Path:
        d = tmp_repo / ".claude" / "worktrees" / name
        d.mkdir(parents=True)
        if state == "non_empty":
            (d / "stray.txt").write_text("x")
        elif state == "active":
            (d / ".git").write_text(f"gitdir: {tmp_repo / '.git'}\n")
        return d

    return _make


@pytest.fixture
def run_hook(tmp_repo: Path) -> Callable[..., HookResult]:
    """Invoke a hook bash script under tmp_repo with CLAUDE_PROJECT_DIR set.

    Args:
      script: path relative to tmp_repo (e.g. "scripts/cleanup-worktrees.sh")
      *args: extra CLI args passed to the script

    Returns: HookResult with stdout/stderr/exit_code and parsed NDJSON lines
    (any stdout line that successfully parses as a JSON object).
    """

    def _run(script: str, *args: str) -> HookResult:
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_repo)}
        proc = subprocess.run(
            ["bash", str(tmp_repo / script), *args],
            cwd=tmp_repo,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        ndjson: list[dict] = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                ndjson.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return HookResult(
            stdout=proc.stdout,
            stderr=proc.stderr,
            exit_code=proc.returncode,
            ndjson=ndjson,
        )

    return _run


@pytest.fixture(scope="session")
def cleanup_schema() -> dict:
    """Load schemas/cleanup-output.schema.json once per test session."""
    return json.loads(SCHEMA_PATH.read_text())


@pytest.fixture(scope="session")
def assert_valid_ndjson(cleanup_schema: dict) -> Callable[[list[dict]], None]:
    """Validate a list of NDJSON event dicts against the cleanup-output schema."""
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(cleanup_schema)

    def _assert(events: list[dict]) -> None:
        for i, evt in enumerate(events):
            errors = list(validator.iter_errors(evt))
            assert not errors, (
                f"Event #{i} failed schema validation: {evt}\n"
                + "\n".join(e.message for e in errors)
            )

    return _assert


@pytest.fixture
def with_gh_stub(tmp_repo: Path, monkeypatch):
    """Provide a `gh` stub on PATH that echoes a canned response.

    Args of the returned callable:
      response: literal string the stub will print on stdout.

    Returns: None (callable side-effect).
    """
    stub_src = PROJECT_ROOT / "tests" / "hooks" / "_gh_stub.sh"

    def _install(response: str) -> None:
        bin_dir = tmp_repo / "bin"
        bin_dir.mkdir(exist_ok=True)
        gh_target = bin_dir / "gh"
        shutil.copy2(stub_src, gh_target)
        gh_target.chmod(0o755)
        monkeypatch.setenv("GH_STUB_RESPONSE", response)
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    return _install
