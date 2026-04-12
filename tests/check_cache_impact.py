"""Pre-commit check for detection cache invalidation.

Usage:
    python -m tests.check_cache_impact          # staged changes
    python -m tests.check_cache_impact --all    # all uncommitted changes
"""

import subprocess
import sys

from tests.detection_cache import _CACHE_SENSITIVE_FILES


def _get_changed_files(*, all_changes: bool = False) -> list[str]:
    """Return changed file paths relative to repo root."""
    if all_changes:
        # Staged + unstaged
        cmd_staged = ["git", "diff", "--cached", "--name-only"]
        cmd_unstaged = ["git", "diff", "--name-only"]
        staged = subprocess.run(cmd_staged, capture_output=True, text=True, check=False)
        unstaged = subprocess.run(
            cmd_unstaged, capture_output=True, text=True, check=False
        )
        files = set(staged.stdout.splitlines()) | set(unstaged.stdout.splitlines())
        return [f.strip() for f in files if f.strip()]

    cmd = ["git", "diff", "--cached", "--name-only"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return [f.strip() for f in result.stdout.splitlines() if f.strip()]


def _check_impact(changed_files: list[str]) -> list[str]:
    """Return cache-sensitive files that appear in changed_files."""
    # Normalize to forward slashes for comparison
    changed_normalized = {f.replace("\\", "/") for f in changed_files}
    return [f for f in _CACHE_SENSITIVE_FILES if f in changed_normalized]


def main() -> int:
    """Entry point for ``python -m tests.check_cache_impact``."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Check if git changes affect the test detection cache"
    )
    parser.addoption = parser.add_argument  # type: ignore[attr-defined]
    parser.add_argument(
        "--all",
        action="store_true",
        help="Check all uncommitted changes (staged + unstaged)",
    )
    args = parser.parse_args()

    changed = _get_changed_files(all_changes=args.all)
    impacted = _check_impact(changed)

    if impacted:
        print("WARNING: The following changes will invalidate the detection cache:")
        for f in impacted:
            print(f"  - {f} (modified)")
        print()
        print("Next `pytest -m slow` will require full detection (~3-5 hours).")
        print("Use `pytest -m slow --clear-test-cache` for a clean full run.")
        return 1

    print("OK: No cache-sensitive files modified. Detection cache remains valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
