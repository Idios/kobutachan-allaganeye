"""Tests for scripts/cleanup-claude-branches.sh after NDJSON migration (Refs #710 / #732).

PR #732 mock scenarios 5 件 × 2 modes (dry-run / apply) + summary consistency.
"""

from pathlib import Path


def _of_event(events, evt):
    return [e for e in events if e.get("event") == evt]


# ---------- Scenario 1: merged + 古い + active なし → deleted ----------

def test_merged_old_inactive_apply_deletes(
    make_claude_branch, run_hook, assert_valid_ndjson,
) -> None:
    make_claude_branch("scenario1", merged=True, age_seconds=86400 * 2)
    result = run_hook("scripts/cleanup-claude-branches.sh", "--apply")
    assert_valid_ndjson(result.ndjson)
    deleted = _of_event(result.ndjson, "deleted")
    assert any(e["name"] == "claude/scenario1" for e in deleted), result.stdout


def test_merged_old_inactive_dry_run_would_delete(
    make_claude_branch, run_hook, assert_valid_ndjson,
) -> None:
    make_claude_branch("scenario1b", merged=True, age_seconds=86400 * 2)
    result = run_hook("scripts/cleanup-claude-branches.sh")
    assert_valid_ndjson(result.ndjson)
    wd = _of_event(result.ndjson, "would_delete")
    assert any(e["name"] == "claude/scenario1b" for e in wd), result.stdout


# ---------- Scenario 2: not merged → kept, reason=not-merged ----------

def test_not_merged_kept(
    make_claude_branch, run_hook, assert_valid_ndjson,
) -> None:
    make_claude_branch("scenario2", merged=False, age_seconds=86400 * 2)
    result = run_hook("scripts/cleanup-claude-branches.sh", "--apply")
    assert_valid_ndjson(result.ndjson)
    kept = _of_event(result.ndjson, "kept")
    assert any(
        e["name"] == "claude/scenario2" and e["reason"] == "not-merged" for e in kept
    ), result.stdout


# ---------- Scenario 3: active worktree が参照 → kept, reason=active ----------

def test_active_worktree_kept(
    tmp_repo: Path, make_claude_branch, run_hook, assert_valid_ndjson,
) -> None:
    import subprocess
    branch = make_claude_branch("scenario3", merged=True, age_seconds=86400 * 2)
    # Create an active worktree referencing this branch.
    wt_dir = tmp_repo / ".claude" / "worktrees" / "scenario3-wt"
    subprocess.run(
        ["git", "worktree", "add", "-q", str(wt_dir), branch],
        cwd=tmp_repo, check=True,
    )
    result = run_hook("scripts/cleanup-claude-branches.sh", "--apply")
    assert_valid_ndjson(result.ndjson)
    kept = _of_event(result.ndjson, "kept")
    assert any(
        e["name"] == branch and e["reason"] == "active" for e in kept
    ), result.stdout


# ---------- Scenario 4: 24h cooldown 内 → kept, reason=cooldown ----------

def test_cooldown_kept(
    make_claude_branch, run_hook, assert_valid_ndjson,
) -> None:
    # age_seconds=600 (10 minutes ago) — well within 24h cooldown
    make_claude_branch("scenario4", merged=True, age_seconds=600)
    result = run_hook("scripts/cleanup-claude-branches.sh", "--apply")
    assert_valid_ndjson(result.ndjson)
    kept = _of_event(result.ndjson, "kept")
    assert any(
        e["name"] == "claude/scenario4" and e["reason"] == "cooldown" for e in kept
    ), result.stdout


# ---------- Scenario 5: prefix 違い (feature/xxx) → 列挙対象外 ----------

def test_non_claude_prefix_ignored(
    tmp_repo: Path, run_hook, assert_valid_ndjson,
) -> None:
    import subprocess
    subprocess.run(
        ["git", "checkout", "-q", "-b", "feature/not-touched"],
        cwd=tmp_repo, check=True,
    )
    subprocess.run(["git", "checkout", "-q", "develop-0.2.0"], cwd=tmp_repo, check=True)
    result = run_hook("scripts/cleanup-claude-branches.sh", "--apply")
    assert_valid_ndjson(result.ndjson)
    # No event references feature/not-touched
    for e in result.ndjson:
        assert e.get("name") != "feature/not-touched", result.stdout


# ---------- summary counter 一貫性 ----------

def test_summary_counts_match_events(
    make_claude_branch, run_hook, assert_valid_ndjson,
) -> None:
    make_claude_branch("s-a", merged=True, age_seconds=86400 * 2)
    make_claude_branch("s-b", merged=False, age_seconds=86400 * 2)
    make_claude_branch("s-c", merged=True, age_seconds=600)
    result = run_hook("scripts/cleanup-claude-branches.sh", "--apply")
    assert_valid_ndjson(result.ndjson)
    summaries = _of_event(result.ndjson, "summary")
    assert len(summaries) == 1
    s = summaries[0]
    assert s["script"] == "cleanup-claude-branches"
    assert s["apply"] is True
    assert s["total"] == 3
    assert s["deleted"] == 1  # s-a
    assert s["kept"] == 2     # s-b (not-merged) + s-c (cooldown)
    assert result.ndjson[-1]["event"] == "summary"


def test_empty_branch_list_emits_zero_summary(
    run_hook, assert_valid_ndjson,
) -> None:
    result = run_hook("scripts/cleanup-claude-branches.sh", "--apply")
    assert_valid_ndjson(result.ndjson)
    summaries = _of_event(result.ndjson, "summary")
    assert len(summaries) == 1
    assert summaries[0]["total"] == 0
