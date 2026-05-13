"""Tests for scripts/cleanup-worktrees.sh after NDJSON migration (Refs #710).

Covers 3 directory states × 2 modes (dry-run / apply) + schema conformance.
"""

from pathlib import Path


def _of_event(events: list[dict], evt: str) -> list[dict]:
    return [e for e in events if e.get("event") == evt]


def test_empty_dir_dry_run_emits_would_remove(
    tmp_repo: Path, make_worktree_dir, run_hook, assert_valid_ndjson,
) -> None:
    make_worktree_dir("foo", state="empty")
    result = run_hook("scripts/cleanup-worktrees.sh")
    assert_valid_ndjson(result.ndjson)
    would = _of_event(result.ndjson, "would_remove")
    assert any(e["name"] == "foo" for e in would), result.stdout


def test_empty_dir_apply_emits_removed(
    tmp_repo: Path, make_worktree_dir, run_hook, assert_valid_ndjson,
) -> None:
    make_worktree_dir("foo", state="empty")
    result = run_hook("scripts/cleanup-worktrees.sh", "--apply")
    assert_valid_ndjson(result.ndjson)
    removed = _of_event(result.ndjson, "removed")
    assert any(e["name"] == "foo" for e in removed), result.stdout
    # Directory actually gone
    assert not (tmp_repo / ".claude" / "worktrees" / "foo").exists()


def test_non_empty_dir_dry_run_emits_would_skip(
    tmp_repo: Path, make_worktree_dir, run_hook, assert_valid_ndjson,
) -> None:
    make_worktree_dir("bar", state="non_empty")
    result = run_hook("scripts/cleanup-worktrees.sh")
    assert_valid_ndjson(result.ndjson)
    ws = _of_event(result.ndjson, "would_skip")
    assert any(e["name"] == "bar" and e["reason"] == "not-empty" for e in ws), result.stdout


def test_non_empty_dir_apply_emits_kept(
    tmp_repo: Path, make_worktree_dir, run_hook, assert_valid_ndjson,
) -> None:
    make_worktree_dir("bar", state="non_empty")
    result = run_hook("scripts/cleanup-worktrees.sh", "--apply")
    assert_valid_ndjson(result.ndjson)
    kept = _of_event(result.ndjson, "kept")
    assert any(e["name"] == "bar" and e["reason"] == "not-empty" for e in kept), result.stdout
    # Directory survives
    assert (tmp_repo / ".claude" / "worktrees" / "bar").exists()


def test_active_worktree_emits_skip(
    tmp_repo: Path, make_worktree_dir, run_hook, assert_valid_ndjson,
) -> None:
    make_worktree_dir("baz", state="active")
    result = run_hook("scripts/cleanup-worktrees.sh", "--apply")
    assert_valid_ndjson(result.ndjson)
    skip = _of_event(result.ndjson, "skip")
    assert any(e["name"] == "baz" and e["reason"] == "active" for e in skip), result.stdout


def test_summary_event_is_emitted_last_with_counts(
    tmp_repo: Path, make_worktree_dir, run_hook, assert_valid_ndjson,
) -> None:
    make_worktree_dir("e1", state="empty")
    make_worktree_dir("e2", state="empty")
    make_worktree_dir("ne", state="non_empty")
    result = run_hook("scripts/cleanup-worktrees.sh", "--apply")
    assert_valid_ndjson(result.ndjson)
    summaries = _of_event(result.ndjson, "summary")
    assert len(summaries) == 1
    s = summaries[0]
    assert s["script"] == "cleanup-worktrees"
    assert s["apply"] is True
    assert s["removed"] == 2
    assert s["kept"] == 1
    assert s["total"] == 3
    assert s["orphan_candidates"] == 3
    # summary is the LAST event
    assert result.ndjson[-1]["event"] == "summary"
