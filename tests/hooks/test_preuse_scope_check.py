"""Tests for M7 path-to-scope multi-scope detection in preuse.py (L-alpha M7)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

# preuse.py を動的に load (.claude/hooks/ は package ではないため)
_PREUSE_PATH = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "preuse.py"
_spec = importlib.util.spec_from_file_location("preuse", _PREUSE_PATH)
assert _spec is not None and _spec.loader is not None
preuse = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(preuse)


# ---------------------------------------------------------------
# _classify_path
# ---------------------------------------------------------------


def test_classify_path_known_scopes() -> None:
    assert preuse._classify_path("allaganeye/cli.py") == "l1-cli"
    assert preuse._classify_path("allaganeye/video/detector.py") == "l1-cli"
    assert preuse._classify_path("tests/test_cli.py") == "l1-cli"
    assert preuse._classify_path("gui/src/App.tsx") == "l2a-gui"
    assert preuse._classify_path("gui/src-tauri/src/lib.rs") == "l2a-gui"
    assert preuse._classify_path("gui/scripts/generate-ts.mjs") == "l2a-gui"
    # gui/ direct-child catch-all (Round 1 Finding 2 fix)
    assert preuse._classify_path("gui/package.json") == "l2a-gui"
    assert preuse._classify_path("gui/vite.config.ts") == "l2a-gui"
    assert preuse._classify_path("gui/index.html") == "l2a-gui"
    assert preuse._classify_path("gui/tsconfig.json") == "l2a-gui"
    assert preuse._classify_path("gui/eslint.config.js") == "l2a-gui"
    assert preuse._classify_path("gui/.prettierrc.json") == "l2a-gui"
    assert preuse._classify_path("gui/.gitignore") == "l2a-gui"
    assert preuse._classify_path("gui/package-lock.json") == "l2a-gui"
    assert preuse._classify_path("gui/README.md") == "l2a-gui"
    assert preuse._classify_path("scripts/build-portable-zip.ps1") == "l2b-installer"
    assert preuse._classify_path(".github/workflows/ci.yml") == "l2-ci"
    assert (
        preuse._classify_path(".github/ISSUE_TEMPLATE/bug_report.yml") == "l2-workflow"
    )
    assert preuse._classify_path(".claude/hooks/stop.sh") == "l2-workflow"
    assert preuse._classify_path(".agents/skills/review-pr/SKILL.md") == "l2-workflow"
    assert preuse._classify_path("docs/refactor-pattern.md") == "l2-docs"
    assert preuse._classify_path("docs/l2-workflow.md") == "l2-docs"
    assert preuse._classify_path("AGENTS.md") == "l2-docs"
    assert preuse._classify_path("README.md") == "l2-docs"
    assert preuse._classify_path("pyproject.toml") == "l1-cli"
    assert preuse._classify_path(".markdownlint-cli2.yaml") == "l2-ci"
    assert preuse._classify_path(".gitignore") == "l2-workflow"


def test_classify_path_unknown() -> None:
    assert preuse._classify_path("unrecognized-dir/file.txt") is None
    assert preuse._classify_path("benchmarks/x.json") is None
    assert preuse._classify_path("random.txt") is None


# ---------------------------------------------------------------
# _check_scope_creep
# ---------------------------------------------------------------


def test_check_scope_creep_single_scope_allow() -> None:
    """Single-scope commit (allaganeye/ + tests/) is allow (no ask)."""
    paths = [
        "allaganeye/cli.py",
        "allaganeye/video/detector.py",
        "tests/test_cli.py",
    ]
    should_ask, _ = preuse._check_scope_creep(paths)
    assert should_ask is False


def test_check_scope_creep_multi_scope_ask() -> None:
    """Multi-scope commit (l1-cli + l2a-gui) triggers ask."""
    paths = ["allaganeye/cli.py", "gui/src/App.tsx"]
    should_ask, reason = preuse._check_scope_creep(paths)
    assert should_ask is True
    assert "multi-scope" in reason
    assert "l1-cli" in reason
    assert "l2a-gui" in reason
    assert "Iron Law 3" in reason


def test_check_scope_creep_three_scopes_ask() -> None:
    """3+ scope cross-cutting commit triggers ask."""
    paths = [
        "allaganeye/cli.py",
        "gui/src/App.tsx",
        ".github/workflows/ci.yml",
    ]
    should_ask, reason = preuse._check_scope_creep(paths)
    assert should_ask is True
    assert "multi-scope" in reason


def test_check_scope_creep_unknown_path_ask() -> None:
    """Unknown path triggers ask (table メンテ漏れの可能性)."""
    paths = ["allaganeye/cli.py", "weird/new/dir.txt"]
    should_ask, reason = preuse._check_scope_creep(paths)
    assert should_ask is True
    assert "unknown" in reason
    assert "weird/new/dir.txt" in reason


def test_check_scope_creep_empty_paths_allow() -> None:
    """Empty paths (nothing staged) is allow (no ask)."""
    should_ask, _ = preuse._check_scope_creep([])
    assert should_ask is False


def test_check_scope_creep_docs_only_single_scope() -> None:
    """docs/ + AGENTS.md (both l2-docs) is single scope, allow."""
    paths = ["docs/refactor-pattern.md", "AGENTS.md", "docs/l2-workflow.md"]
    should_ask, _ = preuse._check_scope_creep(paths)
    assert should_ask is False


# ---------------------------------------------------------------
# _GIT_COMMIT_RE
# ---------------------------------------------------------------


def test_git_commit_re_matches() -> None:
    """Standard git commit invocations should match."""
    assert preuse._GIT_COMMIT_RE.match("git commit -m 'foo'")
    assert preuse._GIT_COMMIT_RE.match("git commit -am 'foo'")
    assert preuse._GIT_COMMIT_RE.match("  git commit")
    assert preuse._GIT_COMMIT_RE.match("git commit --amend")


def test_git_commit_re_does_not_match_unrelated() -> None:
    """Non-commit git commands and similar substrings should not match."""
    assert not preuse._GIT_COMMIT_RE.match("git status")
    assert not preuse._GIT_COMMIT_RE.match("git diff")
    assert not preuse._GIT_COMMIT_RE.match("ggit commit")  # typo, leading "ggit"
    assert not preuse._GIT_COMMIT_RE.match("echo git commit")
