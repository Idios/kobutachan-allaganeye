"""Tests for scripts/cleanup-claude-branches.sh after NDJSON migration (Refs #710 / #732).

PR #732 mock scenarios 5 件 x 2 modes (dry-run / apply) + summary consistency.
"""

from pathlib import Path


def _of_event(events, evt):
    return [e for e in events if e.get("event") == evt]


# ---------- Scenario 1: merged + 古い + active なし -> deleted ----------


def test_merged_old_inactive_apply_deletes(
    make_claude_branch,
    run_hook,
    assert_valid_ndjson,
) -> None:
    make_claude_branch("scenario1", merged=True, age_seconds=86400 * 2)
    result = run_hook("scripts/cleanup-claude-branches.sh", "--apply")
    assert_valid_ndjson(result.ndjson)
    deleted = _of_event(result.ndjson, "deleted")
    assert any(e["name"] == "claude/scenario1" for e in deleted), result.stdout


def test_merged_old_inactive_dry_run_would_delete(
    make_claude_branch,
    run_hook,
    assert_valid_ndjson,
) -> None:
    make_claude_branch("scenario1b", merged=True, age_seconds=86400 * 2)
    result = run_hook("scripts/cleanup-claude-branches.sh")
    assert_valid_ndjson(result.ndjson)
    wd = _of_event(result.ndjson, "would_delete")
    assert any(e["name"] == "claude/scenario1b" for e in wd), result.stdout


# ---------- Scenario 2: not merged -> kept, reason=not-merged ----------


def test_not_merged_kept(
    make_claude_branch,
    run_hook,
    assert_valid_ndjson,
) -> None:
    make_claude_branch("scenario2", merged=False, age_seconds=86400 * 2)
    result = run_hook("scripts/cleanup-claude-branches.sh", "--apply")
    assert_valid_ndjson(result.ndjson)
    kept = _of_event(result.ndjson, "kept")
    assert any(
        e["name"] == "claude/scenario2" and e["reason"] == "not-merged" for e in kept
    ), result.stdout


# ---------- Scenario 3: active worktree が参照 -> kept, reason=active ----------


def test_active_worktree_kept(
    tmp_repo: Path,
    make_claude_branch,
    run_hook,
    assert_valid_ndjson,
) -> None:
    import subprocess

    branch = make_claude_branch("scenario3", merged=True, age_seconds=86400 * 2)
    # Create an active worktree referencing this branch.
    wt_dir = tmp_repo / ".claude" / "worktrees" / "scenario3-wt"
    subprocess.run(
        ["git", "worktree", "add", "-q", str(wt_dir), branch],
        cwd=tmp_repo,
        check=True,
    )
    result = run_hook("scripts/cleanup-claude-branches.sh", "--apply")
    assert_valid_ndjson(result.ndjson)
    kept = _of_event(result.ndjson, "kept")
    assert any(e["name"] == branch and e["reason"] == "active" for e in kept), (
        result.stdout
    )


# ---------- Scenario 4: 24h cooldown 内 -> kept, reason=cooldown ----------


def test_cooldown_kept(
    make_claude_branch,
    run_hook,
    assert_valid_ndjson,
) -> None:
    # age_seconds=600 (10 minutes ago) -- well within 24h cooldown
    make_claude_branch("scenario4", merged=True, age_seconds=600)
    result = run_hook("scripts/cleanup-claude-branches.sh", "--apply")
    assert_valid_ndjson(result.ndjson)
    kept = _of_event(result.ndjson, "kept")
    assert any(
        e["name"] == "claude/scenario4" and e["reason"] == "cooldown" for e in kept
    ), result.stdout


# ---------- Scenario 5: prefix 違い (feature/xxx) -> 列挙対象外 ----------


def test_non_claude_prefix_ignored(
    tmp_repo: Path,
    run_hook,
    assert_valid_ndjson,
) -> None:
    import subprocess

    subprocess.run(
        ["git", "checkout", "-q", "-b", "feature/not-touched"],
        cwd=tmp_repo,
        check=True,
    )
    subprocess.run(["git", "checkout", "-q", "develop-0.2.0"], cwd=tmp_repo, check=True)
    result = run_hook("scripts/cleanup-claude-branches.sh", "--apply")
    assert_valid_ndjson(result.ndjson)
    # No event references feature/not-touched
    for e in result.ndjson:
        assert e.get("name") != "feature/not-touched", result.stdout


# ---------- summary counter 一貫性 ----------


def test_summary_counts_match_events(
    make_claude_branch,
    run_hook,
    assert_valid_ndjson,
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
    assert s["kept"] == 2  # s-b (not-merged) + s-c (cooldown)
    assert result.ndjson[-1]["event"] == "summary"


def test_empty_branch_list_emits_zero_summary(
    run_hook,
    assert_valid_ndjson,
) -> None:
    result = run_hook("scripts/cleanup-claude-branches.sh", "--apply")
    assert_valid_ndjson(result.ndjson)
    summaries = _of_event(result.ndjson, "summary")
    assert len(summaries) == 1
    assert summaries[0]["total"] == 0


# ---------- Scenario 6: origin/develop-0.3.0 のみ存在 (develop-* 一般化, #816) ----------


def test_merged_to_newer_develop_branch_deleted(
    tmp_repo: Path,
    make_claude_branch,
    run_hook,
    assert_valid_ndjson,
) -> None:
    """develop-0.2.0 が origin から消えても現行 origin/develop-* で merged 判定できる (#816).

    実環境の再現: origin/develop-0.2.0 は v0.2.x 期の後に削除済みで、
    origin/develop-0.3.0 のみが存在する。旧実装 (develop-0.2.0 固定) では
    not-merged 扱いで永遠に kept になる (audit 2026-06-10 P3)。
    """
    import subprocess

    make_claude_branch("scenario6", merged=True, age_seconds=86400 * 2)
    # NOTE: make_claude_branch は呼び出しごとに origin/develop-0.2.0 を HEAD へ
    # 再 mirror するため (conftest)、ref の削除/付け替えは最後の呼び出しの後で行う。
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/develop-0.3.0", "HEAD"],
        cwd=tmp_repo,
        check=True,
    )
    subprocess.run(
        ["git", "update-ref", "-d", "refs/remotes/origin/develop-0.2.0"],
        cwd=tmp_repo,
        check=True,
    )
    result = run_hook("scripts/cleanup-claude-branches.sh", "--apply")
    assert_valid_ndjson(result.ndjson)
    deleted = _of_event(result.ndjson, "deleted")
    assert any(e["name"] == "claude/scenario6" for e in deleted), result.stdout


# ---------- Scenario 7: origin/develop-* も origin/main も無い -> 安全側 keep ----------


def test_no_develop_remote_refs_keeps_branch(
    tmp_repo: Path,
    make_claude_branch,
    run_hook,
    assert_valid_ndjson,
) -> None:
    """origin/develop-* が 1 本も無く origin/main も無い場合は not-merged で keep (安全側)."""
    import subprocess

    make_claude_branch("scenario7", merged=True, age_seconds=86400 * 2)
    # NOTE: make_claude_branch は呼び出しごとに origin/develop-0.2.0 を HEAD へ
    # 再 mirror するため (conftest)、ref の削除/付け替えは最後の呼び出しの後で行う。
    subprocess.run(
        ["git", "update-ref", "-d", "refs/remotes/origin/develop-0.2.0"],
        cwd=tmp_repo,
        check=True,
    )
    result = run_hook("scripts/cleanup-claude-branches.sh", "--apply")
    assert_valid_ndjson(result.ndjson)
    kept = _of_event(result.ndjson, "kept")
    assert any(
        e["name"] == "claude/scenario7" and e["reason"] == "not-merged" for e in kept
    ), result.stdout


# ---------- Scenario 8: 複数 origin/develop-* 共存時は sort -V 最新が選ばれる ----------


def test_latest_develop_selected_among_multiple(
    tmp_repo: Path,
    make_claude_branch,
    run_hook,
    assert_valid_ndjson,
) -> None:
    """複数 origin/develop-* 共存時、sort -V 最新のみが merge base になる (#816).

    旧 origin/develop-0.2.0 (branch を含まない) と新 origin/develop-0.3.0
    (branch を含む) が共存するとき、最新の 0.3.0 が選ばれて deleted になる。
    選択を誤って 0.2.0 を使うと kept になるため、version 選択を pin する。
    """
    import subprocess

    make_claude_branch("scenario8", merged=True, age_seconds=86400 * 2)
    # NOTE: make_claude_branch は呼び出しごとに origin/develop-0.2.0 を HEAD へ
    # 再 mirror するため (conftest)、ref の付け替えは最後の呼び出しの後で行う。
    # origin/develop-0.2.0 (旧、branch を含まない) と origin/develop-0.3.0
    # (新、branch を含む) を共存させる。最新 = 0.3.0 が選ばれれば deleted になる。
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/develop-0.2.0", "HEAD^1"],
        cwd=tmp_repo,
        check=True,
    )
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/develop-0.3.0", "HEAD"],
        cwd=tmp_repo,
        check=True,
    )
    result = run_hook("scripts/cleanup-claude-branches.sh", "--apply")
    assert_valid_ndjson(result.ndjson)
    deleted = _of_event(result.ndjson, "deleted")
    assert any(e["name"] == "claude/scenario8" for e in deleted), result.stdout


# ---------- Scenario 9: stale な旧 develop にのみ merged -> 安全側 keep (Codex HIGH) ----------


def test_merged_only_to_stale_older_develop_kept(
    tmp_repo: Path,
    make_claude_branch,
    run_hook,
    assert_valid_ndjson,
) -> None:
    """stale な旧 origin/develop-* にのみ merged な branch は削除しない (#816 Codex HIGH).

    Stop hook は fetch/prune しないため、origin 側で削除済みの旧 develop の
    remote-tracking ref がローカルに残存しうる。merge base を sort -V 最新の
    develop に限定することで、旧 ref だけを根拠にした削除を防ぐ。
    """
    import subprocess

    make_claude_branch("scenario9", merged=True, age_seconds=86400 * 2)
    # NOTE: make_claude_branch は呼び出しごとに origin/develop-0.2.0 を HEAD へ
    # 再 mirror するため (conftest)、ref の付け替えは最後の呼び出しの後で行う。
    # origin/develop-0.2.0 (= HEAD、branch を含む stale 旧 ref) はそのまま残し、
    # 現行 develop に相当する origin/develop-0.3.0 を HEAD^1 (branch を含まない)
    # に置く = 「旧にのみ merged、現行には未 merged」を再現する。
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/develop-0.3.0", "HEAD^1"],
        cwd=tmp_repo,
        check=True,
    )
    result = run_hook("scripts/cleanup-claude-branches.sh", "--apply")
    assert_valid_ndjson(result.ndjson)
    kept = _of_event(result.ndjson, "kept")
    assert any(
        e["name"] == "claude/scenario9" and e["reason"] == "not-merged" for e in kept
    ), result.stdout


# ---------- Scenario 10: 最新 develop に未 merged でも origin/main に merged -> deleted ----------


def test_merged_to_main_but_not_latest_develop_deleted(
    tmp_repo: Path,
    make_claude_branch,
    run_hook,
    assert_valid_ndjson,
) -> None:
    """origin/main fallback の pin: 最新 develop が含まなくても main に merged なら削除可."""
    import subprocess

    make_claude_branch("scenario10", merged=True, age_seconds=86400 * 2)
    # NOTE: make_claude_branch は呼び出しごとに origin/develop-0.2.0 を HEAD へ
    # 再 mirror するため (conftest)、ref の付け替えは最後の呼び出しの後で行う。
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/main", "HEAD"],
        cwd=tmp_repo,
        check=True,
    )
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/develop-0.2.0", "HEAD^1"],
        cwd=tmp_repo,
        check=True,
    )
    result = run_hook("scripts/cleanup-claude-branches.sh", "--apply")
    assert_valid_ndjson(result.ndjson)
    deleted = _of_event(result.ndjson, "deleted")
    assert any(e["name"] == "claude/scenario10" for e in deleted), result.stdout


# ---------- Scenario 11: double-digit version は sort -V でのみ正しく最新判定 ----------


def test_latest_develop_uses_version_sort_for_double_digits(
    tmp_repo: Path,
    make_claude_branch,
    run_hook,
    assert_valid_ndjson,
) -> None:
    """develop-0.10.0 vs 0.9.0 で version sort が最新を選ぶことを pin (#816).

    `sort -V` が lexical `sort` に退行すると 0.9.0 > 0.10.0 と誤判定し、
    branch を含まない旧 develop が merge base になって kept に倒れる
    (v0.10.0 到達時に silent 再発する bug class)。本テストはその退行で fail する。
    """
    import subprocess

    make_claude_branch("scenario11", merged=True, age_seconds=86400 * 2)
    # NOTE: make_claude_branch は呼び出しごとに origin/develop-0.2.0 を HEAD へ
    # 再 mirror するため (conftest)、ref の削除/付け替えは最後の呼び出しの後で行う。
    subprocess.run(
        ["git", "update-ref", "-d", "refs/remotes/origin/develop-0.2.0"],
        cwd=tmp_repo,
        check=True,
    )
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/develop-0.9.0", "HEAD^1"],
        cwd=tmp_repo,
        check=True,
    )
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/develop-0.10.0", "HEAD"],
        cwd=tmp_repo,
        check=True,
    )
    result = run_hook("scripts/cleanup-claude-branches.sh", "--apply")
    assert_valid_ndjson(result.ndjson)
    deleted = _of_event(result.ndjson, "deleted")
    assert any(e["name"] == "claude/scenario11" for e in deleted), result.stdout


def _rev_parse(repo: Path, ref: str) -> str:
    """Return the commit OID of ref in repo."""
    import subprocess

    return subprocess.run(
        ["git", "rev-parse", ref],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


# ---------- Scenario 12: squash-merged (is-ancestor=false) + gh OID 一致 -> deleted (#827) ----------


def test_squash_merged_via_gh_deleted(
    tmp_repo: Path,
    make_claude_branch,
    run_hook,
    assert_valid_ndjson,
    with_gh_stub,
) -> None:
    """squash マージ済み branch は is-ancestor=false だが gh が merged head OID を報告 -> deleted (#827).

    本 repo の PR は --squash マージのため branch tip が base の祖先にならず、
    旧実装では永遠に not-merged 扱いだった。gh pr list --state merged の
    headRefOid 集合に local branch tip の OID が一致すれば merged と判定して削除する。
    OID 同一性で照合するため headRefName 衝突による誤削除は起こらない (#827 codex HIGH)。
    """
    branch = make_claude_branch("scenario12", merged=False, age_seconds=86400 * 2)
    # gh stub は `gh pr list ... --jq '.[].headRefOid'` の出力 (改行区切り OID) を模す。
    with_gh_stub(_rev_parse(tmp_repo, branch))
    result = run_hook("scripts/cleanup-claude-branches.sh", "--apply")
    assert_valid_ndjson(result.ndjson)
    deleted = _of_event(result.ndjson, "deleted")
    assert any(e["name"] == branch and e.get("merged_via") == "gh" for e in deleted), (
        result.stdout
    )
    # start event records the gh augmentation succeeded.
    start = _of_event(result.ndjson, "start")
    assert start and start[0].get("gh_merged_lookup") == "ok", result.stdout


# ---------- Scenario 13: gh が空 [] -> is-ancestor=false は kept (OR が過剰削除しない) ----------


def test_gh_empty_does_not_over_delete(
    make_claude_branch,
    run_hook,
    assert_valid_ndjson,
    with_gh_stub,
) -> None:
    """gh が merged PR を 1 件も返さないとき、is-ancestor=false branch は kept (安全側)."""
    make_claude_branch("scenario13", merged=False, age_seconds=86400 * 2)
    with_gh_stub("")  # 空 = merged PR head OID なし
    result = run_hook("scripts/cleanup-claude-branches.sh", "--apply")
    assert_valid_ndjson(result.ndjson)
    kept = _of_event(result.ndjson, "kept")
    assert any(
        e["name"] == "claude/scenario13" and e["reason"] == "not-merged" for e in kept
    ), result.stdout


# ---------- Scenario 14: gh 非ゼロ exit -> is-ancestor fallback で kept + status=error ----------


def test_gh_failure_falls_back_to_ancestor(
    tmp_repo: Path,
    make_claude_branch,
    run_hook,
    assert_valid_ndjson,
    with_gh_stub,
) -> None:
    """gh が失敗 (非ゼロ exit) したら集合を空に倒し is-ancestor のみで判定 (安全側 kept).

    gh が「全 branch を merged」と誤って報告する状況を防ぐ: 失敗時は削除根拠に
    しない。start.gh_merged_lookup=error で fallback を可視化する。
    """
    branch = make_claude_branch("scenario14", merged=False, age_seconds=86400 * 2)
    # 一致する OID を返しても exit!=0 なら無視されねばならない。
    with_gh_stub(_rev_parse(tmp_repo, branch), exit_code=1)
    result = run_hook("scripts/cleanup-claude-branches.sh", "--apply")
    assert_valid_ndjson(result.ndjson)
    kept = _of_event(result.ndjson, "kept")
    assert any(
        e["name"] == "claude/scenario14" and e["reason"] == "not-merged" for e in kept
    ), result.stdout
    start = _of_event(result.ndjson, "start")
    assert start and start[0].get("gh_merged_lookup") == "error", result.stdout


# ---------- Scenario 15: gh merged だが cooldown 内 -> kept cooldown (gh が AND3 を bypass しない) ----------


def test_gh_merged_still_respects_cooldown(
    tmp_repo: Path,
    make_claude_branch,
    run_hook,
    assert_valid_ndjson,
    with_gh_stub,
) -> None:
    """gh が merged と報告しても 24h cooldown 内なら削除しない (AND3 を bypass しない)."""
    branch = make_claude_branch("scenario15", merged=False, age_seconds=600)
    with_gh_stub(_rev_parse(tmp_repo, branch))
    result = run_hook("scripts/cleanup-claude-branches.sh", "--apply")
    assert_valid_ndjson(result.ndjson)
    kept = _of_event(result.ndjson, "kept")
    assert any(
        e["name"] == "claude/scenario15" and e["reason"] == "cooldown" for e in kept
    ), result.stdout


# ---------- Scenario 16: 同名 branch 再作成で OID 不一致 -> kept (data-loss 防止, codex HIGH) ----------


def test_gh_oid_mismatch_recreated_branch_kept(
    tmp_repo: Path,
    make_claude_branch,
    run_hook,
    assert_valid_ndjson,
    with_gh_stub,
) -> None:
    """merged PR の head 名と同名だが local tip OID が異なる branch は削除しない (#827 codex HIGH).

    claude/foo が squash-merged 後に同名で再作成され未 merge の新 commit を積んだ
    ケースを再現する。gh が返す merged head OID (= 別 commit) と local branch tip が
    一致しないため、headRefName が衝突しても kept になる (不可逆 data-loss を防止)。
    """
    make_claude_branch("scenario16", merged=False, age_seconds=86400 * 2)
    # gh は当該 branch tip とは異なる OID (base develop-0.2.0 の commit) を merged head として返す。
    # 旧 name-match 実装ではここで誤削除された (codex HIGH)。OID 一致必須なら kept。
    with_gh_stub(_rev_parse(tmp_repo, "develop-0.2.0"))
    result = run_hook("scripts/cleanup-claude-branches.sh", "--apply")
    assert_valid_ndjson(result.ndjson)
    kept = _of_event(result.ndjson, "kept")
    assert any(
        e["name"] == "claude/scenario16" and e["reason"] == "not-merged" for e in kept
    ), result.stdout
