# Lane VI / Group L Implementation Plan (#710 hook test infra + #722 resume-plan handoff)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** L2 workflow infra 拡張 1 round を 1 結合 PR で実装する。`.claude/hooks/*` と `scripts/cleanup-*.sh` に pytest+subprocess ベースの自動テスト infra を導入 + cleanup output を NDJSON 構造化 (#710)、`docs/l2-workflow.md` に resume-plan handoff 規約 (`EXECUTOR: self|dispatch`) と Iron Law 6 Step 0 ハードゲートを追加 + `.claude/hooks/session-start.sh` で worktree-as-PR-head 自動検出 (#722)。

**Architecture:** Schema-first in-place rewrite。`schemas/cleanup-output.schema.json` (draft 2020-12) を契約として cleanup scripts と pytest を結ぶ。cleanup scripts は in-place で書き換え、wrapper 層は導入しない (drift 防止)。テストは pytest+subprocess+tmp git repo で hook を black-box 検証。

**Tech Stack:** Python 3.11.9 (既存 CI 整合) / pytest / subprocess / jsonschema (draft 2020-12) / bash (cleanup scripts + hooks) / jq (formatter helper) / GitHub Actions ubuntu-latest

**Spec:** [docs/superpowers/specs/2026-05-13-lane-vi-group-l-design.md](../specs/2026-05-13-lane-vi-group-l-design.md)

---

## File Structure

### NEW (9 files)

| path | 責務 |
| --- | --- |
| `schemas/cleanup-output.schema.json` | NDJSON event 契約 (JSON Schema draft 2020-12) |
| `scripts/format-cleanup-log.sh` | NDJSON → 人間読み変換 (jq wrapper) |
| `tests/hooks/__init__.py` | Python パッケージマーカー (空) |
| `tests/hooks/conftest.py` | 4 fixtures: tmp_repo / make_claude_branch / make_worktree_dir / run_hook |
| `tests/hooks/test_stop_hook.py` | stop.sh の 4 挙動を黒箱検証 |
| `tests/hooks/test_cleanup_worktrees.py` | cleanup-worktrees.sh の 3 状態 × 2 mode |
| `tests/hooks/test_cleanup_claude_branches.py` | cleanup-claude-branches.sh の 5 シナリオ × 2 mode |
| `tests/hooks/test_session_start_hook.py` | session-start.sh の Iron Law text + worktree-PR-head 検出 |
| `docs/superpowers/eval/2026-05-13-handoff-protocol-eval.md` | empirical-prompt-tuning 3 シナリオ + iter 結果 |

### MODIFIED (6 files + 1 conditional)

| path | 変更内容 |
| --- | --- |
| `scripts/cleanup-worktrees.sh` | echo → `_emit()` (NDJSON) 全置換 |
| `scripts/cleanup-claude-branches.sh` | echo → `_emit()` (NDJSON) 全置換 |
| `.claude/hooks/session-start.sh` | Iron Law 6 サブ条 (handoff + Step 0) 追記 + worktree-PR-head 検出ブロック追加 |
| `docs/l2-workflow.md` | §「resume-plan handoff protocol」 新設 + §「PR 作成 Pre-flight」 Step 0 + Red Flag 1 行追加 |
| `CLAUDE.md` | PR 作成ルール節に EXECUTOR への 1 行 link |
| `.github/workflows/ci.yml` | `hook-test` job 新設 + 既存 `python` job の Test step に `--ignore=tests/hooks/` |
| `pyproject.toml` | conditional: testpaths は既設 (`testpaths = ["tests"]`) で auto-collect なため、`--ignore` 戦略で対応するため触らない見込み |

### TEST-ONLY-AFFECTED (no diff)

| path | 検証内容 |
| --- | --- |
| `.claude/hooks/stop.sh` | NDJSON 化後も既存挙動 (rc 取得 / NOT FOUND 分岐 / exit 0) を保持することを Task 5 で確認 |

---

## Task ordering rationale

1. **Phase 1-2 (Tasks 1-2)**: schema + test infra scaffold (基盤)
2. **Phase 3 (Tasks 3-4)**: cleanup scripts TDD (red → green)
3. **Phase 4 (Task 5)**: stop.sh behavior preservation 検証 (no-diff、cleanup scripts が NDJSON 化した後で確認)
4. **Phase 5 (Task 6)**: format-cleanup-log.sh (NDJSON 確定後、人間読み helper)
5. **Phase 6-7 (Tasks 7-9)**: #722 docs 変更 (l2-workflow.md / CLAUDE.md)
6. **Phase 8 (Tasks 10-11)**: session-start.sh TDD (docs 確定後、reference を docs に貼るため)
7. **Phase 9 (Task 12)**: CI integration (全 tests が green 後)
8. **Phase 10 (Tasks 13-14)**: empirical-prompt-tuning eval doc + iter 実行
9. **Phase 11 (Task 15)**: PR Pre-flight + 作成

---

## Task 1: NDJSON Schema (cleanup-output.schema.json)

**Files:**

- Create: `schemas/cleanup-output.schema.json`

- [ ] **Step 1: Write the schema (full draft 2020-12 JSON Schema)**

Create `schemas/cleanup-output.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/Idios/kobutachan-allaganeye/schemas/cleanup-output.schema.json",
  "title": "Cleanup script NDJSON event",
  "description": "One JSON object per line emitted by scripts/cleanup-*.sh on stdout (Refs #710). Each line MUST match exactly one of the variants below.",
  "oneOf": [
    {
      "type": "object",
      "required": ["event", "script", "apply", "repo_root"],
      "properties": {
        "event": {"const": "start"},
        "script": {"enum": ["cleanup-worktrees", "cleanup-claude-branches"]},
        "apply": {"type": "boolean"},
        "repo_root": {"type": "string"}
      },
      "additionalProperties": false
    },
    {
      "type": "object",
      "required": ["event", "script", "name"],
      "properties": {
        "event": {"enum": ["removed", "deleted", "would_remove", "would_delete"]},
        "script": {"enum": ["cleanup-worktrees", "cleanup-claude-branches"]},
        "name": {"type": "string"}
      },
      "additionalProperties": false
    },
    {
      "type": "object",
      "required": ["event", "script", "name", "reason"],
      "properties": {
        "event": {"enum": ["kept", "would_skip", "skip"]},
        "script": {"enum": ["cleanup-worktrees", "cleanup-claude-branches"]},
        "name": {"type": "string"},
        "reason": {"enum": ["not-empty", "active", "not-merged", "cooldown"]}
      },
      "additionalProperties": false
    },
    {
      "type": "object",
      "required": ["event", "script", "name", "exit_code"],
      "properties": {
        "event": {"const": "delete_failed"},
        "script": {"const": "cleanup-claude-branches"},
        "name": {"type": "string"},
        "exit_code": {"type": "integer"}
      },
      "additionalProperties": false
    },
    {
      "type": "object",
      "required": ["event", "script", "apply", "total"],
      "properties": {
        "event": {"const": "summary"},
        "script": {"enum": ["cleanup-worktrees", "cleanup-claude-branches"]},
        "apply": {"type": "boolean"},
        "total": {"type": "integer"},
        "removed": {"type": "integer"},
        "kept": {"type": "integer"},
        "orphan_candidates": {"type": "integer"},
        "deleted": {"type": "integer"}
      },
      "additionalProperties": false
    },
    {
      "type": "object",
      "required": ["event", "script", "message"],
      "properties": {
        "event": {"const": "error"},
        "script": {"enum": ["cleanup-worktrees", "cleanup-claude-branches"]},
        "message": {"type": "string"},
        "exit_code": {"type": "integer"}
      },
      "additionalProperties": false
    }
  ]
}
```

- [ ] **Step 2: Run schema validity check**

```bash
python -c "import json, jsonschema; jsonschema.Draft202012Validator.check_schema(json.load(open('schemas/cleanup-output.schema.json'))); print('OK')"
```

Expected output: `OK`

If fails: re-check JSON syntax + draft 2020-12 keywords.

- [ ] **Step 3: Commit**

```bash
git add schemas/cleanup-output.schema.json
git commit -m "feat(schemas): cleanup-output.schema.json (NDJSON event 契約、Refs #710)

draft 2020-12、6 variants:
- start / removed-deleted-would_remove-would_delete / kept-would_skip-skip /
  delete_failed / summary / error
- script enum (cleanup-worktrees | cleanup-claude-branches)
- reason enum (not-empty | active | not-merged | cooldown)

scripts/cleanup-*.sh stdout の契約として hooks + tests/hooks/ から参照する。

Refs #710

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: tests/hooks/ scaffold (`__init__.py` + conftest.py + smoke test)

**Files:**

- Create: `tests/hooks/__init__.py`
- Create: `tests/hooks/conftest.py`
- Create: `tests/hooks/test_scaffold.py` (smoke test、後で削除可能だが一旦残す)

- [ ] **Step 1: Create empty `__init__.py`**

```bash
touch tests/hooks/__init__.py
```

- [ ] **Step 2: Write conftest.py (full content)**

Create `tests/hooks/conftest.py`:

```python
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
from typing import Callable, Literal

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

    The repo has an initial commit on `develop-0.2.0` (the project's default
    base branch). cleanup-claude-branches.sh's merge-base logic resolves
    correctly against this branch.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "develop-0.2.0"], cwd=repo, check=True)
    (repo / "README.md").write_text("test\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t.invalid", "-c", "user.name=t",
         "commit", "-qm", "init"],
        cwd=repo, check=True,
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
    """

    def _make(slug: str, *, merged: bool, age_seconds: int) -> str:
        branch = f"claude/{slug}"
        # Create branch from develop-0.2.0
        subprocess.run(["git", "checkout", "-q", "-b", branch], cwd=tmp_repo, check=True)
        # Make a commit with a forged committer date.
        (tmp_repo / f"{slug}.txt").write_text("x")
        subprocess.run(["git", "add", "."], cwd=tmp_repo, check=True)
        forged_ts = int(time.time()) - age_seconds
        env = {**os.environ,
               "GIT_COMMITTER_DATE": f"@{forged_ts} +0000",
               "GIT_AUTHOR_DATE": f"@{forged_ts} +0000"}
        subprocess.run(
            ["git", "-c", "user.email=t@t.invalid", "-c", "user.name=t",
             "commit", "-qm", f"work {slug}"],
            cwd=tmp_repo, env=env, check=True,
        )
        if merged:
            # Merge into develop-0.2.0
            subprocess.run(["git", "checkout", "-q", "develop-0.2.0"], cwd=tmp_repo, check=True)
            subprocess.run(
                ["git", "-c", "user.email=t@t.invalid", "-c", "user.name=t",
                 "merge", "-q", "--no-ff", branch, "-m", f"merge {branch}"],
                cwd=tmp_repo, check=True,
            )
        else:
            subprocess.run(["git", "checkout", "-q", "develop-0.2.0"], cwd=tmp_repo, check=True)

        # cleanup-claude-branches.sh requires an `origin/develop-0.2.0` ref to test
        # ancestor-ship. Mirror local develop-0.2.0 into refs/remotes/origin/.
        subprocess.run(
            ["git", "update-ref", "refs/remotes/origin/develop-0.2.0", "HEAD"],
            cwd=tmp_repo, check=True,
        )
        return branch

    return _make


@pytest.fixture
def make_worktree_dir(tmp_repo: Path) -> Callable[..., Path]:
    """Create .claude/worktrees/<name>/ in one of 3 states.

    state:
      "empty"     — empty directory (cleanup target)
      "non_empty" — has a stray.txt inside (skipped, rmdir would fail)
      "active"   — has .git file referencing tmp_repo's main .git (active worktree)
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
            cwd=tmp_repo, env=env, capture_output=True, text=True, timeout=30,
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
            stdout=proc.stdout, stderr=proc.stderr,
            exit_code=proc.returncode, ndjson=ndjson,
        )

    return _run


@pytest.fixture
def cleanup_schema() -> dict:
    """Load schemas/cleanup-output.schema.json once per test session-equivalent."""
    return json.loads(SCHEMA_PATH.read_text())


@pytest.fixture
def assert_valid_ndjson(cleanup_schema):
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
```

- [ ] **Step 3: Write a scaffold smoke test**

Create `tests/hooks/test_scaffold.py`:

```python
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
```

- [ ] **Step 4: Run smoke test to verify scaffold**

```bash
pytest tests/hooks/test_scaffold.py -v
```

Expected: all 4 tests pass (4 passed). If `test_make_claude_branch_and_run_hook` fails with `git` errors, verify Git is on PATH and `git init -b develop-0.2.0` is supported (git ≥ 2.28).

- [ ] **Step 5: Commit**

```bash
git add tests/hooks/__init__.py tests/hooks/conftest.py tests/hooks/test_scaffold.py
git commit -m "test(hooks): tests/hooks/ scaffold (conftest fixtures + smoke test、Refs #710)

conftest.py: tmp_repo / make_claude_branch / make_worktree_dir / run_hook /
cleanup_schema / assert_valid_ndjson の 6 fixtures。
PROJECT_ROOT/.claude/hooks/ と PROJECT_ROOT/scripts/ を symlink (Windows は
copy fallback) で isolated tmp_repo に wiring。

test_scaffold.py: fixture wiring の smoke test (Task 3-4 でこれら fixture を
本格的な NDJSON 検証 test に展開する)。

Refs #710

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: cleanup-worktrees.sh NDJSON migration (TDD)

**Files:**

- Create: `tests/hooks/test_cleanup_worktrees.py`
- Modify: `scripts/cleanup-worktrees.sh` (echo → `_emit()` 全置換)

- [ ] **Step 1: Write failing tests (red)**

Create `tests/hooks/test_cleanup_worktrees.py`:

```python
"""Tests for scripts/cleanup-worktrees.sh after NDJSON migration (Refs #710).

Covers 3 directory states × 2 modes (dry-run / apply) + schema conformance.
"""

from pathlib import Path

import pytest


def _events(result) -> list[dict]:
    return result.ndjson


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
    # summary is the LAST event
    assert result.ndjson[-1]["event"] == "summary"
```

- [ ] **Step 2: Run failing tests to verify red**

```bash
pytest tests/hooks/test_cleanup_worktrees.py -v
```

Expected: all 6 tests FAIL (cleanup-worktrees.sh still emits literal text, NDJSON list is empty/non-conforming).

- [ ] **Step 3: Rewrite cleanup-worktrees.sh to emit NDJSON**

Replace the entire contents of `scripts/cleanup-worktrees.sh` with:

```bash
#!/usr/bin/env bash
# cleanup-worktrees.sh — Sweep orphan .claude/worktrees/ directories (Refs #477 / #710).
#
# Output: stdout NDJSON (one JSON object per line). Schema: schemas/cleanup-output.schema.json.
# Pretty-printing: `scripts/cleanup-worktrees.sh | scripts/format-cleanup-log.sh`.
#
# Behavior (unchanged from pre-#710):
#   1. `git worktree prune` for git metadata first.
#   2. Scan .claude/worktrees/<name>/. If empty + not active, rmdir.
#
# Usage:
#   scripts/cleanup-worktrees.sh           # dry-run
#   scripts/cleanup-worktrees.sh --apply   # actually rmdir
#
# Exit: 0 normal / 1 arg error / 2 unexpected failure.

set -euo pipefail

_SCRIPT_NAME="cleanup-worktrees"

# NDJSON emitter. Usage:
#   _emit start apply=true repo_root=/path
#   _emit removed name=foo
#   _emit kept name=foo reason=not-empty
#   _emit summary apply=true total=3 removed=2 kept=1 orphan_candidates=3
_emit() {
  local out='{'
  out+="\"event\":\"$1\""; shift
  out+=",\"script\":\"$_SCRIPT_NAME\""
  for kv in "$@"; do
    local k="${kv%%=*}"
    local v="${kv#*=}"
    if [[ "$v" =~ ^-?[0-9]+$ ]] || [[ "$v" == "true" || "$v" == "false" ]]; then
      out+=",\"$k\":$v"
    else
      v="${v//\\/\\\\}"; v="${v//\"/\\\"}"
      out+=",\"$k\":\"$v\""
    fi
  done
  out+='}'
  printf '%s\n' "$out"
}

COMMON_GIT_DIR="$(git rev-parse --git-common-dir 2>/dev/null || true)"
if [[ -z "$COMMON_GIT_DIR" ]]; then
  _emit error message="not a git repo (run from within the allaganeye checkout)" exit_code=2 >&2
  exit 2
fi
COMMON_GIT_DIR="$(cd "$COMMON_GIT_DIR" && pwd)"
REPO_ROOT="$(dirname "$COMMON_GIT_DIR")"

WT_DIR="$REPO_ROOT/.claude/worktrees"
APPLY=0

while (( $# > 0 )); do
  case "$1" in
    --apply|-a) APPLY=1 ;;
    -h|--help)
      awk 'NR==1 && /^#!/ {next} /^# ?/ {sub(/^# ?/, ""); print; next} {exit}' "$0"
      exit 0
      ;;
    *)
      _emit error message="unknown arg '$1'" exit_code=1 >&2
      exit 1
      ;;
  esac
  shift
done

if (( APPLY )); then
  _emit start apply=true repo_root="$REPO_ROOT"
else
  _emit start apply=false repo_root="$REPO_ROOT"
fi

if [[ ! -d "$WT_DIR" ]]; then
  _emit summary apply="$([[ $APPLY -eq 1 ]] && echo true || echo false)" \
                total=0 removed=0 kept=0 orphan_candidates=0
  exit 0
fi

# Step 1: git worktree prune (silent — its output is not part of our NDJSON contract).
if (( APPLY )); then
  git -C "$REPO_ROOT" worktree prune >/dev/null 2>&1 || true
else
  git -C "$REPO_ROOT" worktree prune --dry-run >/dev/null 2>&1 || true
fi

# Step 2: scan
orphan_count=0
removed_count=0
kept_count=0

for d in "$WT_DIR"/*/; do
  [[ -d "$d" ]] || continue
  name="$(basename "$d")"

  if [[ -e "$d/.git" ]]; then
    _emit skip name="$name" reason=active
    continue
  fi

  orphan_count=$((orphan_count + 1))

  if (( APPLY )); then
    if rmdir "$d" 2>/dev/null; then
      _emit removed name="$name"
      removed_count=$((removed_count + 1))
    else
      _emit kept name="$name" reason=not-empty
      kept_count=$((kept_count + 1))
    fi
  else
    if [[ -z "$(ls -A "$d" 2>/dev/null)" ]]; then
      _emit would_remove name="$name"
      removed_count=$((removed_count + 1))
    else
      _emit would_skip name="$name" reason=not-empty
      kept_count=$((kept_count + 1))
    fi
  fi
done

if (( APPLY )); then
  _emit summary apply=true total="$orphan_count" removed="$removed_count" \
                kept="$kept_count" orphan_candidates="$orphan_count"
else
  _emit summary apply=false total="$orphan_count" removed="$removed_count" \
                kept="$kept_count" orphan_candidates="$orphan_count"
fi
```

- [ ] **Step 4: Run tests to verify green**

```bash
pytest tests/hooks/test_cleanup_worktrees.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/hooks/test_cleanup_worktrees.py scripts/cleanup-worktrees.sh
git commit -m "feat(scripts): cleanup-worktrees.sh の output を NDJSON 化 (Refs #710)

stdout NDJSON only (schemas/cleanup-output.schema.json 準拠):
- start / would_remove / would_skip / skip / removed / kept / summary
- _emit() inline helper で event 1 行ごとに dump
- 既存挙動 (git worktree prune → scan → rmdir) は不変

tests/hooks/test_cleanup_worktrees.py (6 test):
- empty + dry-run / empty + apply / non_empty + dry-run / non_empty + apply
  / active worktree / summary counter 一貫性
- 全 event を assert_valid_ndjson fixture で schema validate

Refs #710

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: cleanup-claude-branches.sh NDJSON migration (TDD)

**Files:**

- Create: `tests/hooks/test_cleanup_claude_branches.py`
- Modify: `scripts/cleanup-claude-branches.sh`

- [ ] **Step 1: Write failing tests (red)**

Create `tests/hooks/test_cleanup_claude_branches.py`:

```python
"""Tests for scripts/cleanup-claude-branches.sh after NDJSON migration (Refs #710 / #732).

PR #732 mock scenarios 5 件 × 2 modes (dry-run / apply) + summary consistency.
"""

from pathlib import Path

import pytest


def _of_event(events, evt):
    return [e for e in events if e.get("event") == evt]


# ---------- Scenario 1: merged + 古い + active なし → deleted ----------

def test_merged_old_inactive_apply_deletes(
    tmp_repo: Path, make_claude_branch, run_hook, assert_valid_ndjson,
) -> None:
    make_claude_branch("scenario1", merged=True, age_seconds=86400 * 2)
    result = run_hook("scripts/cleanup-claude-branches.sh", "--apply")
    assert_valid_ndjson(result.ndjson)
    deleted = _of_event(result.ndjson, "deleted")
    assert any(e["name"] == "claude/scenario1" for e in deleted), result.stdout


def test_merged_old_inactive_dry_run_would_delete(
    tmp_repo: Path, make_claude_branch, run_hook, assert_valid_ndjson,
) -> None:
    make_claude_branch("scenario1b", merged=True, age_seconds=86400 * 2)
    result = run_hook("scripts/cleanup-claude-branches.sh")
    assert_valid_ndjson(result.ndjson)
    wd = _of_event(result.ndjson, "would_delete")
    assert any(e["name"] == "claude/scenario1b" for e in wd), result.stdout


# ---------- Scenario 2: not merged → kept, reason=not-merged ----------

def test_not_merged_kept(
    tmp_repo: Path, make_claude_branch, run_hook, assert_valid_ndjson,
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
    tmp_repo: Path, make_claude_branch, run_hook, assert_valid_ndjson,
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
    tmp_repo: Path, make_claude_branch, run_hook, assert_valid_ndjson,
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
    tmp_repo: Path, run_hook, assert_valid_ndjson,
) -> None:
    result = run_hook("scripts/cleanup-claude-branches.sh", "--apply")
    assert_valid_ndjson(result.ndjson)
    summaries = _of_event(result.ndjson, "summary")
    assert len(summaries) == 1
    assert summaries[0]["total"] == 0
```

- [ ] **Step 2: Run failing tests to verify red**

```bash
pytest tests/hooks/test_cleanup_claude_branches.py -v
```

Expected: all 8 tests FAIL (cleanup-claude-branches.sh still emits literal text).

- [ ] **Step 3: Rewrite cleanup-claude-branches.sh to emit NDJSON**

Replace the entire contents of `scripts/cleanup-claude-branches.sh` with:

```bash
#!/usr/bin/env bash
# cleanup-claude-branches.sh — Delete safe `claude/*` local branches (Refs #708 / #710).
#
# Output: stdout NDJSON (one JSON object per line). Schema: schemas/cleanup-output.schema.json.
#
# Safety AND conditions (unchanged from pre-#710):
#   1. merged: ancestor of origin/develop-0.2.0 or origin/main
#   2. active 不在: not referenced by any active worktree
#   3. cooldown: last commit ≥ 24h ago
#   (prefix filter: claude/* only is listed)
#
# Usage:
#   scripts/cleanup-claude-branches.sh           # dry-run
#   scripts/cleanup-claude-branches.sh --apply   # actually delete
#
# Exit: 0 normal / 1 arg error / 2 not a git repo.

set -u

_SCRIPT_NAME="cleanup-claude-branches"

_emit() {
  local out='{'
  out+="\"event\":\"$1\""; shift
  out+=",\"script\":\"$_SCRIPT_NAME\""
  for kv in "$@"; do
    local k="${kv%%=*}"
    local v="${kv#*=}"
    if [[ "$v" =~ ^-?[0-9]+$ ]] || [[ "$v" == "true" || "$v" == "false" ]]; then
      out+=",\"$k\":$v"
    else
      v="${v//\\/\\\\}"; v="${v//\"/\\\"}"
      out+=",\"$k\":\"$v\""
    fi
  done
  out+='}'
  printf '%s\n' "$out"
}

COMMON_GIT_DIR="$(git rev-parse --git-common-dir 2>/dev/null || true)"
if [[ -z "$COMMON_GIT_DIR" ]]; then
  _emit error message="not a git repo (run from within the allaganeye checkout)" exit_code=2 >&2
  exit 2
fi
COMMON_GIT_DIR="$(cd "$COMMON_GIT_DIR" && pwd)"
REPO_ROOT="$(dirname "$COMMON_GIT_DIR")"

APPLY=0
while (( $# > 0 )); do
  case "$1" in
    --apply|-a) APPLY=1 ;;
    -h|--help)
      awk 'NR==1 && /^#!/ {next} /^# ?/ {sub(/^# ?/, ""); print; next} {exit}' "$0"
      exit 0
      ;;
    *)
      _emit error message="unknown arg '$1'" exit_code=1 >&2
      exit 1
      ;;
  esac
  shift
done

if (( APPLY )); then
  _emit start apply=true repo_root="$REPO_ROOT"
else
  _emit start apply=false repo_root="$REPO_ROOT"
fi

mapfile -t BRANCHES < <(git -C "$REPO_ROOT" branch --list 'claude/*' --format='%(refname:short)')

deleted=0
kept=0
COOLDOWN_THRESHOLD=$(($(date +%s) - 86400))

# Build active-branch set from worktree list.
declare -A ACTIVE_BRANCHES=()
while IFS= read -r line; do
  if [[ "$line" == "branch refs/heads/"* ]]; then
    ACTIVE_BRANCHES["${line#branch refs/heads/}"]=1
  fi
done < <(git -C "$REPO_ROOT" worktree list --porcelain)

for branch in "${BRANCHES[@]}"; do
  # AND 2: active 不在判定
  if [[ -n "${ACTIVE_BRANCHES[$branch]:-}" ]]; then
    _emit kept name="$branch" reason=active
    kept=$((kept + 1))
    continue
  fi

  # AND 1: merged 判定
  merged=0
  if git -C "$REPO_ROOT" merge-base --is-ancestor "$branch" "origin/develop-0.2.0" 2>/dev/null; then
    merged=1
  elif git -C "$REPO_ROOT" merge-base --is-ancestor "$branch" "origin/main" 2>/dev/null; then
    merged=1
  fi
  if [[ "$merged" -eq 0 ]]; then
    _emit kept name="$branch" reason=not-merged
    kept=$((kept + 1))
    continue
  fi

  # AND 3: cooldown
  last_ct=$(git -C "$REPO_ROOT" log -1 --format=%ct "$branch" -- 2>/dev/null || echo "")
  if [[ -z "$last_ct" ]] || [[ "$last_ct" -ge "$COOLDOWN_THRESHOLD" ]]; then
    _emit kept name="$branch" reason=cooldown
    kept=$((kept + 1))
    continue
  fi

  # 全 AND 満足 — 削除対象
  if [[ "$APPLY" -eq 1 ]]; then
    git -C "$REPO_ROOT" branch -D "$branch" >/dev/null 2>&1
    rc=$?
    if [[ "$rc" -eq 0 ]]; then
      _emit deleted name="$branch"
      deleted=$((deleted + 1))
    else
      _emit delete_failed name="$branch" exit_code="$rc"
      kept=$((kept + 1))
    fi
  else
    _emit would_delete name="$branch"
    deleted=$((deleted + 1))
  fi
done

_emit summary apply="$([[ $APPLY -eq 1 ]] && echo true || echo false)" \
              total="${#BRANCHES[@]}" deleted="$deleted" kept="$kept"
exit 0
```

- [ ] **Step 4: Run tests to verify green**

```bash
pytest tests/hooks/test_cleanup_claude_branches.py -v
```

Expected: all 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/hooks/test_cleanup_claude_branches.py scripts/cleanup-claude-branches.sh
git commit -m "feat(scripts): cleanup-claude-branches.sh の output を NDJSON 化 (Refs #710)

stdout NDJSON only (schemas/cleanup-output.schema.json 準拠):
- start / kept (active|not-merged|cooldown) / deleted / would_delete /
  delete_failed / summary
- 既存 AND 3 条件 (merged + active 不在 + cooldown) ロジックは不変

tests/hooks/test_cleanup_claude_branches.py (8 test): PR #732 mock 5 scenarios:
- merged + 古い + active なし → deleted / would_delete
- not-merged → kept (reason: not-merged)
- active worktree が参照 → kept (reason: active)
- 24h cooldown 内 → kept (reason: cooldown)
- prefix 違い (feature/xxx) → 列挙対象外
+ summary counter 一貫性 / 空 branch list

Refs #710 #732

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: stop.sh behavior preservation 検証 (TEST-ONLY, no .sh diff)

**Files:**

- Create: `tests/hooks/test_stop_hook.py`

**Note:** stop.sh は edit しない。NDJSON 化後も stdout を log に追記する既存挙動が NDJSON 行をそのまま通すことを確認する黒箱テストのみ。

- [ ] **Step 1: Write tests**

Create `tests/hooks/test_stop_hook.py`:

```python
"""Tests for .claude/hooks/stop.sh (Refs #707 / #710).

stop.sh is unchanged by the #710 NDJSON migration. These tests confirm:
- normal cleanup flow logs NDJSON lines from both cleanup scripts
- cleanup script failure (exit 42) is logged with `cleanup exit=42`
- missing cleanup script is logged with `NOT FOUND at <path>`
- hook itself always exits 0 even when cleanup fails
"""

from pathlib import Path

import pytest


def _read_log(tmp_repo: Path) -> str:
    log = tmp_repo / ".claude" / "state" / "stop-hook.log"
    if not log.exists():
        return ""
    return log.read_text()


def test_stop_hook_logs_normal_cleanup(
    tmp_repo: Path, run_hook,
) -> None:
    """Both cleanup scripts present and succeed → log records both blocks
    + NDJSON lines from each.
    """
    result = run_hook(".claude/hooks/stop.sh")
    assert result.exit_code == 0
    log = _read_log(tmp_repo)
    assert "stop.sh invoked" in log
    assert "cleanup-worktrees.sh: present" in log
    assert "cleanup-claude-branches.sh: present" in log
    # NDJSON summary events from both scripts appear in the log
    assert '"event":"summary"' in log
    assert '"script":"cleanup-worktrees"' in log
    assert '"script":"cleanup-claude-branches"' in log


def test_stop_hook_logs_cleanup_script_failure(
    tmp_repo: Path, run_hook,
) -> None:
    """Replace cleanup-worktrees.sh with a stub that exits 42 → log records
    `cleanup exit=42`. stop.sh still exits 0.
    """
    # Replace the symlink/copy with a stub.
    target = tmp_repo / "scripts" / "cleanup-worktrees.sh"
    if target.is_symlink():
        target.unlink()
    elif target.exists():
        target.unlink()
    target.write_text("#!/usr/bin/env bash\nexit 42\n")
    target.chmod(0o755)

    result = run_hook(".claude/hooks/stop.sh")
    assert result.exit_code == 0
    log = _read_log(tmp_repo)
    assert "cleanup exit=42" in log


def test_stop_hook_handles_missing_cleanup_script(
    tmp_repo: Path, run_hook,
) -> None:
    """Remove cleanup-claude-branches.sh → log records `NOT FOUND at <path>`."""
    target = tmp_repo / "scripts" / "cleanup-claude-branches.sh"
    if target.is_symlink():
        target.unlink()
    elif target.exists():
        target.unlink()

    result = run_hook(".claude/hooks/stop.sh")
    assert result.exit_code == 0
    log = _read_log(tmp_repo)
    assert "cleanup-claude-branches.sh: NOT FOUND" in log


def test_stop_hook_swallows_errors_and_exits_zero(
    tmp_repo: Path, run_hook,
) -> None:
    """Even when both cleanup scripts fail, stop.sh exits 0."""
    for name in ("cleanup-worktrees.sh", "cleanup-claude-branches.sh"):
        target = tmp_repo / "scripts" / name
        if target.is_symlink():
            target.unlink()
        elif target.exists():
            target.unlink()
        target.write_text("#!/usr/bin/env bash\nexit 99\n")
        target.chmod(0o755)

    result = run_hook(".claude/hooks/stop.sh")
    assert result.exit_code == 0
```

- [ ] **Step 2: Run tests to verify green**

```bash
pytest tests/hooks/test_stop_hook.py -v
```

Expected: all 4 tests pass (stop.sh unchanged, just confirming behavior preserved post-NDJSON).

- [ ] **Step 3: Commit**

```bash
git add tests/hooks/test_stop_hook.py
git commit -m "test(hooks): test_stop_hook.py — stop.sh の挙動保持を verify (Refs #710)

cleanup-worktrees.sh / cleanup-claude-branches.sh の NDJSON 化 (Task 3, 4)
後も stop.sh は無変更で動作することを 4 test で確認:
- normal flow: 両 cleanup の NDJSON summary が log に記録される
- cleanup-worktrees.sh が exit 42 → log に \`cleanup exit=42\`
- cleanup-claude-branches.sh 不在 → log に \`NOT FOUND\`
- 両 script 失敗でも stop.sh は exit 0

stop.sh 自体は本 PR で diff なし (#710 受け入れ条件「output 契約定義」を満たす
ために必要十分な範囲を cleanup scripts 側に限定、scope creep 回避)。

Refs #710

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: format-cleanup-log.sh helper

**Files:**

- Create: `scripts/format-cleanup-log.sh`

- [ ] **Step 1: Write a smoke test that verifies the helper produces expected human-readable output**

Add the following to `tests/hooks/test_scaffold.py` (append, do not replace):

```python
def test_format_cleanup_log_smoke(tmp_path, run_hook, make_worktree_dir, tmp_repo):
    """End-to-end: NDJSON from cleanup-worktrees.sh → format-cleanup-log.sh →
    human-readable lines.
    """
    import subprocess
    make_worktree_dir("foo", state="empty")
    cleanup = subprocess.run(
        ["bash", str(tmp_repo / "scripts" / "cleanup-worktrees.sh"), "--apply"],
        cwd=tmp_repo, capture_output=True, text=True, check=True,
    )
    fmt = subprocess.run(
        ["bash", str(tmp_repo / "scripts" / "format-cleanup-log.sh")],
        input=cleanup.stdout, cwd=tmp_repo, capture_output=True, text=True, check=True,
    )
    assert "[cleanup-worktrees] removed foo" in fmt.stdout
    assert "[cleanup-worktrees] summary:" in fmt.stdout
```

- [ ] **Step 2: Run test to verify red (script doesn't exist)**

```bash
pytest tests/hooks/test_scaffold.py::test_format_cleanup_log_smoke -v
```

Expected: FAIL with `No such file or directory` for format-cleanup-log.sh.

- [ ] **Step 3: Write format-cleanup-log.sh**

Create `scripts/format-cleanup-log.sh`:

```bash
#!/usr/bin/env bash
# format-cleanup-log.sh — Pretty-print cleanup NDJSON events from stdin or file.
#
# Usage:
#   scripts/cleanup-worktrees.sh --apply | scripts/format-cleanup-log.sh
#   scripts/format-cleanup-log.sh < .claude/state/stop-hook.log
#
# Requires: jq. Without jq, falls back to plain echo of stdin.
#
# Output format (one line per NDJSON event):
#   [cleanup-worktrees] removed foo
#   [cleanup-worktrees] kept bar (reason: not-empty)
#   [cleanup-worktrees] summary: 1 removed / 1 kept / 2 total

set -u

if ! command -v jq >/dev/null 2>&1; then
  # jq 不在環境では NDJSON をそのまま流す (回避策: python -c 等で parse)
  cat "$@"
  exit 0
fi

jq -r '
  if .event == "start" then
    "[\(.script)] start (apply=\(.apply))"
  elif .event == "summary" then
    if .deleted then
      "[\(.script)] summary: \(.deleted) deleted / \(.kept // 0) kept / \(.total) total"
    else
      "[\(.script)] summary: \(.removed // 0) removed / \(.kept // 0) kept / \(.total) total"
    end
  elif .event == "error" then
    "[\(.script)] error: \(.message)"
  elif .reason then
    "[\(.script)] \(.event) \(.name) (reason: \(.reason))"
  elif .name then
    "[\(.script)] \(.event) \(.name)"
  else
    "[\(.script)] \(.event)"
  end
' "$@"
```

```bash
chmod +x scripts/format-cleanup-log.sh
```

- [ ] **Step 4: Run test to verify green**

```bash
pytest tests/hooks/test_scaffold.py::test_format_cleanup_log_smoke -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/format-cleanup-log.sh tests/hooks/test_scaffold.py
git commit -m "feat(scripts): format-cleanup-log.sh (NDJSON pretty-print helper、Refs #710)

cleanup-*.sh の stdout NDJSON を 1 行サマリの人間読み text に変換する jq wrapper。
jq 不在環境では cat fallback。

例:
  scripts/cleanup-worktrees.sh --apply | scripts/format-cleanup-log.sh
    [cleanup-worktrees] removed foo
    [cleanup-worktrees] kept bar (reason: not-empty)
    [cleanup-worktrees] summary: 1 removed / 1 kept / 2 total

tests/hooks/test_scaffold.py::test_format_cleanup_log_smoke で E2E verify。

Refs #710

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: docs/l2-workflow.md — §「resume-plan handoff protocol」 new section

**Files:**

- Modify: `docs/l2-workflow.md` (insert new section before §「PR 作成 Pre-flight」)

- [ ] **Step 1: Locate insertion point**

```bash
grep -n "^## PR 作成 Pre-flight" docs/l2-workflow.md
```

Expected: line 75 (or similar). Insert the new section immediately before this line.

- [ ] **Step 2: Insert the new section**

Use Edit tool to add the following BEFORE the line `## PR 作成 Pre-flight (Iron Law 6 サブ条)`. The block uses 4-backtick outer fence so the embedded 3-backtick fences below are unambiguous:

````markdown
## resume-plan handoff protocol (Iron Law 6 サブ条、#722)

> 2026-05-13 #722 で導入。PR #721 (#705 BtbN monthly pin) で発生した race condition の再発防止。

session が contingency 用 resume task prompt を生成して user に提示する際は、prompt の **1 行目** に EXECUTOR ディレクティブを必ず記述する。書式は固定で、機械パース可能・人間も即座に判別可能とする。

### EXECUTOR ディレクティブ書式

```text
EXECUTOR: self (origin=<session-id>, generated=<ISO-8601>)
EXECUTOR: dispatch (origin=<session-id>, generated=<ISO-8601>)
```

| field | 意味 | 例 |
| --- | --- | --- |
| `EXECUTOR` | `self` または `dispatch` | `dispatch` |
| `origin` | prompt 生成 session の worktree dir 名 (session-id 相当) | `exciting-northcutt-a3f7b8` |
| `generated` | prompt 生成時刻 (ISO-8601 + tz、`date -Iseconds` 出力) | `2026-05-13T22:14:33+09:00` |

正規表現 (受信側 parse 用): `^EXECUTOR: (self|dispatch) \(origin=([^,]+), generated=(.+)\)$`

### self / dispatch のセマンティクス

| mode | origin session の状態 | user の期待 action | 受信した session の振る舞い |
| --- | --- | --- | --- |
| `self` | **継続中**。prompt は context loss 時の保険文書 | 何もしない (origin が走る)。context loss を検知した場合のみ手動 dispatch | (通常は受け取らない)。受け取った場合 = origin が context loss した想定 → `gh pr list --search "<元 issue#>" --state all` で origin 痕跡確認 → `AskUserQuestion` で「(A) origin 痕跡なしで仕切り直し / (B) 当 prompt は誤 dispatch、abort」を提示 |
| `dispatch` | **abort 済み** | 新規 session に dispatch | origin が abort 済 = fresh start。Iron Law 6 Pre-flight 通常実施 |

### 生成側 (origin session) のルール

1. prompt 生成 **時点で** どちらの mode かを明示的に決定
2. dispatch mode で生成した直後、origin session は当該 PR 作成 / 実装作業を **stop** する (= abort confirmation)
3. self mode 生成は user 透過の contingency 文書として扱い、origin は実行を継続
4. 1 session が同一 issue について self と dispatch の **両方** の prompt を user に提示することはしない (PR #721 race condition の原因)

### 受信側 (dispatch された fresh session) のルール

1. 受け取った prompt の 1 行目を上記正規表現で parse
2. parse fail → `AskUserQuestion` で「(A) legacy prompt として扱う (handoff 規約適用前と仮定して着手) / (B) prompt 不正のため当 session を abort、user に prompt 再生成を依頼」
3. `EXECUTOR: dispatch` → そのまま着手
4. `EXECUTOR: self` → 上記 self 行のフローを実行

### prompt template 例

```text
EXECUTOR: dispatch (origin=exciting-northcutt-a3f7b8, generated=2026-05-13T22:14:33+09:00)

# Resume: <タスク表題> (issue #<N>)

## Context
<原 issue 状況、関連 PR、最終決定事項を 5-10 行>

## Acceptance criteria
<受け入れ条件をフルコピー>

## Plan
<手順を箇条書き、最後の "STOP and ask user" 点を明示>
```

template 内の各節は既存実装と整合する位置取り。Iron Law 4 (Closes 禁止) 適用。
````

(末尾に必ず空行を 1 つ入れて、その下の `## PR 作成 Pre-flight` の H2 と空行で区切る)

- [ ] **Step 3: Run markdownlint**

```bash
bash scripts/check-markdownlint.sh docs/l2-workflow.md
```

Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
git add docs/l2-workflow.md
git commit -m "docs(l2-workflow): resume-plan handoff protocol 節新設 (Refs #722)

session が contingency 用 resume task prompt を user に提示する際の規約。
prompt 先頭 1 行に \`EXECUTOR: self|dispatch (origin=..., generated=...)\` を
記述し、origin が継続実行 (self) か abort (dispatch) かを prompt 自身で自記。
PR #721 (#705 BtbN monthly pin) の race condition 再発防止。

- self / dispatch セマンティクス表
- 生成側 / 受信側ルール
- prompt template 例 (Iron Law 4 Closes 禁止整合)
- parse 用正規表現

Refs #722

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: docs/l2-workflow.md — §「PR 作成 Pre-flight」 Step 0 + Red Flag

**Files:**

- Modify: `docs/l2-workflow.md` (rewrite Pre-flight 4 ステップ + Red Flags 表 +1 行)

- [ ] **Step 1: Add Step 0 hard-gate to Pre-flight section**

In `docs/l2-workflow.md`, find the section starting with `### 4 ステップ手順` under `## PR 作成 Pre-flight (Iron Law 6 サブ条)`. Replace the 4-step list to add Step 0:

Find:

```bash
# 1. base 最新化 (read-only fetch)
git fetch origin <base>            # <base> = develop-0.2.0 等
```

Replace the entire `### 4 ステップ手順` code block with:

```bash
# 0. ★ ハードゲート (#722 で追加): <1s で実行、build/verify の前に置く
gh pr list --search "<元issue#>" --state open \
  --json number,headRefName,state,createdAt
# hit ≥ 1 件 → 即時 abort、AskUserQuestion で
#   (A) 当該 PR を review/iterate に切替 [Recommended]
#   (B) 別 worktree のため当 session abort
#   (C) ユーザー判断 (詳細確認)
# hit 0 件 → Step 1 へ

# 1. base 最新化 (read-only fetch)
git fetch origin <base>            # <base> = develop-0.2.0 等

# 2. 取り込み未済 commit 列挙
git log HEAD..origin/<base> --oneline

# 3. touched files 交差判定 (取り込み未済 commit が当 PR と同 path を触っていないか)
#    - 当 PR の touched files
git diff --name-only origin/<base>
#    - 取り込み未済 commit の touched files
git diff --name-only HEAD origin/<base>
#    両者の交差ありなら、base 取り込み (merge or rebase) + 検証再実行が必要

# 4. 並行 worktree 同 issue PR 重複確認 (Step 0 と検出 window が異なるため再実行必須)
gh pr list --search "<元issue#>" --state all \
  --json number,headRefName,state,createdAt
```

- [ ] **Step 2: Update section heading and explanatory text**

Find the line `## PR 作成 Pre-flight (Iron Law 6 サブ条)` and the paragraph below it. Edit the explanatory text to mention #722 Step 0:

Find:

```markdown
PR 作成前に base 最新化と並行 worktree PR 重複を必ず確認する。`feedback_pr_review_base_merge_regression.md` (PR #627 Round 4 で発覚した base 取り込み機能 regression) と `feedback_concurrent_worktree_pr_check.md` (#646 / PR #647 並行作業重複) の skill / 規約昇格として運用化 (2026-04-29 #659)。
```

Replace with:

```markdown
PR 作成前に base 最新化と並行 worktree PR 重複を必ず確認する。`feedback_pr_review_base_merge_regression.md` (PR #627 Round 4 で発覚した base 取り込み機能 regression) と `feedback_concurrent_worktree_pr_check.md` (#646 / PR #647 並行作業重複) の skill / 規約昇格として運用化 (2026-04-29 #659)。2026-05-13 #722 で Step 0 ハードゲートを追加 (build/verify 前に `gh pr list --search "<元issue#>" --state open` を <1s で実行、PR #721 で発生した 49s redundant work 再発を防止)。Step 0 と Step 4 は検出 window が異なるため両方とも実施する。
```

- [ ] **Step 3: Add Red Flag entry**

Find the Red Flags table in `### Red Flags` subsection. After the last row of the table, before the closing of the section, add:

```markdown
| 「Step 0 で 0 件だったから Step 4 skip」 | Step 0 と Step 4 は検出 window が異なる。両 step 間に別 worktree が PR 提出する race window あり (PR #721 事例)。両 step とも必須 |
```

- [ ] **Step 4: Run markdownlint**

```bash
bash scripts/check-markdownlint.sh docs/l2-workflow.md
```

Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add docs/l2-workflow.md
git commit -m "docs(l2-workflow): PR 作成 Pre-flight に Step 0 ハードゲート追加 (Refs #722)

build/verify 前に \`gh pr list --search\` を <1s で実行し、既存 open PR を
検出した時点で即時 abort。PR #721 (#705 BtbN monthly pin) で発生した
\"build/verify 49s 完走後に Step 4 で重複検出 → abort\" の redundant work
再発を防止。

Step 0 と Step 4 は検出 window が異なる (Step 0 = 計画立案完了時 /
Step 4 = build/verify pass 後) ため両方実施。Red Flags 表に
「Step 0 で 0 件だったから Step 4 skip」を追加。

Refs #722

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: CLAUDE.md — 1-line reference to handoff protocol

**Files:**

- Modify: `CLAUDE.md` (PR 作成ルール節)

- [ ] **Step 1: Locate the existing PR 作成ルール section**

```bash
grep -n "^## PR 作成ルール" CLAUDE.md
```

Expected: 1 line found.

- [ ] **Step 2: Add a new paragraph after the existing single-line description**

Use Edit tool. Find:

```markdown
## PR 作成ルール

PR Pre-flight・path 別自動チェック・実機検証 trigger・Self-Test Report 規約・(A) PR 内修正優先・PR 規約 (develop ベース / Closes 禁止 / 1 PR = 1 scope / session-id 等) は [`docs/l2-workflow.md`](docs/l2-workflow.md) 各 § を参照。Iron Law 6 (`.claude/hooks/session-start.sh`) も参照。
```

Replace with:

```markdown
## PR 作成ルール

PR Pre-flight・path 別自動チェック・実機検証 trigger・Self-Test Report 規約・(A) PR 内修正優先・PR 規約 (develop ベース / Closes 禁止 / 1 PR = 1 scope / session-id 等) は [`docs/l2-workflow.md`](docs/l2-workflow.md) 各 § を参照。Iron Law 6 (`.claude/hooks/session-start.sh`) も参照。

resume task prompt 生成 (skill / session が user に dispatch 用 prompt を提示する場面) は [`docs/l2-workflow.md`](docs/l2-workflow.md) §「resume-plan handoff protocol」 で定義した `EXECUTOR: self|dispatch (origin=..., generated=...)` ディレクティブを遵守する (#722)。
```

- [ ] **Step 3: Run markdownlint**

```bash
bash scripts/check-markdownlint.sh CLAUDE.md
```

Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(CLAUDE): PR 作成ルール節に handoff protocol への 1 行追記 (Refs #722)

resume task prompt 生成時の EXECUTOR ディレクティブ規約への参照を 1 行追加。
詳細規約は docs/l2-workflow.md §「resume-plan handoff protocol」 (#722 で
新設) に集中、CLAUDE.md は entry point として 1 行 link のみ保持。

Refs #722

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: session-start.sh Iron Law 6 sub-clause + handoff line (TDD)

**Files:**

- Create: `tests/hooks/test_session_start_hook.py`
- Modify: `.claude/hooks/session-start.sh`

- [ ] **Step 1: Write failing tests for Iron Law 6 sub-clause text**

Create `tests/hooks/test_session_start_hook.py`:

```python
"""Tests for .claude/hooks/session-start.sh (Refs #722).

Two scopes:
  1. Iron Law 6 sub-clause text (handoff + Step 0 references)  ← Task 10
  2. worktree-as-PR-head 自動検出 (gh pr list --head)            ← Task 11
"""

from pathlib import Path

import pytest


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
```

- [ ] **Step 2: Run failing tests**

```bash
pytest tests/hooks/test_session_start_hook.py::test_session_start_includes_handoff_subclause tests/hooks/test_session_start_hook.py::test_session_start_mentions_step_zero_pre_flight -v
```

Expected: 2 FAIL (these strings not yet in the heredoc).

Note: `test_session_start_outputs_iron_law_block` should already pass.

- [ ] **Step 3: Edit session-start.sh heredoc to add handoff sub-clause and Step 0 reference**

Use Edit tool on `.claude/hooks/session-start.sh`. Find the Iron Law 6 block ending lines:

```text
   - **PR 作成 Pre-flight (#659 で運用化)**: `git fetch origin <base>` → `git log HEAD..origin/<base>` で取り込み未済 commit を確認 → 当 PR の touched files と交差するなら `git merge origin/<base>` で取り込み + 自動チェック再実行 → `gh pr list --search "<元issue#>" --state all` で並行 worktree PR 重複確認。「コンフリクト出ないから OK」「最近 fetch したから OK」は Red Flag (失敗パターン C 再発、`docs/l2-workflow.md` §「PR 作成 Pre-flight」 参照)
   - PR 本文には machine-verified を `[x]` で、machine-unverifiable を plain bullet `-` で書き分ける (`docs/l2-workflow.md` §「Self-Test Report 規約」)。詳細手順は `docs/l2-workflow.md` §「PR 作成 path 別自動チェック」 / §「実機検証 trigger 表」 参照
```

Replace with:

```text
   - **PR 作成 Pre-flight (#659 で運用化、#722 で Step 0 ハードゲート追加)**: Step 0 = `gh pr list --search "<元issue#>" --state open` でハードゲート (<1s、build/verify の前) → Step 1 base 同期 (`git fetch origin <base>`) → Step 2 取り込み未済 commit (`git log HEAD..origin/<base>`) → Step 3 touched files 交差判定 → Step 4 並行 PR 重複再確認 (`gh pr list --search "<元issue#>" --state all`)。Step 0 と Step 4 は検出 window が異なるため両方実施。「コンフリクト出ないから OK」「Step 0 で 0 件だったから Step 4 skip」は Red Flag (失敗パターン C 再発、`docs/l2-workflow.md` §「PR 作成 Pre-flight」 参照)
   - **resume-plan handoff (#722 で運用化)**: resume task prompt を user に提示する際は 1 行目に `EXECUTOR: self|dispatch (origin=..., generated=...)` を明記。生成側 origin が継続実行 (self) か abort (dispatch) かを prompt 自身で自記する。詳細は `docs/l2-workflow.md` §「resume-plan handoff protocol」 参照
   - PR 本文には machine-verified を `[x]` で、machine-unverifiable を plain bullet `-` で書き分ける (`docs/l2-workflow.md` §「Self-Test Report 規約」)。詳細手順は `docs/l2-workflow.md` §「PR 作成 path 別自動チェック」 / §「実機検証 trigger 表」 参照
```

- [ ] **Step 4: Run tests to verify green**

```bash
pytest tests/hooks/test_session_start_hook.py -v
```

Expected: all 3 tests in this task PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/hooks/test_session_start_hook.py .claude/hooks/session-start.sh
git commit -m "feat(hooks): session-start.sh Iron Law 6 サブ条に Step 0 + handoff 追記 (Refs #722)

Iron Law 6 サブ条 (PR 作成 Pre-flight) を以下のとおり拡張:
- Step 0 ハードゲート (#722): build/verify 前に \`gh pr list --search\` を <1s で実行
- Step 0 / Step 4 両方実施を明記 (検出 window が異なる)
- handoff sub-clause: resume task prompt 先頭の EXECUTOR ディレクティブを要求

tests/hooks/test_session_start_hook.py (Task 10 分 3 test):
- Iron Law block の常時出力
- handoff sub-clause 文字列 (EXECUTOR / resume-plan handoff / #722)
- Step 0 + gh pr list の Pre-flight 言及

Task 11 で worktree-as-PR-head 検出ブロックを追加する。

Refs #722

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: session-start.sh worktree-as-PR-head 自動検出 (TDD)

**Files:**

- Modify: `tests/hooks/test_session_start_hook.py` (append 4 tests)
- Modify: `.claude/hooks/session-start.sh` (append detection block)
- Create: `tests/hooks/_gh_stub.sh` (test fixture stub script)

- [ ] **Step 1: Add the gh stub fixture**

Create a shared stub file `tests/hooks/_gh_stub.sh`:

```bash
#!/usr/bin/env bash
# gh stub for session-start.sh tests. Reads the canned response from
# $GH_STUB_RESPONSE env var (literal string passed through).
# Usage in tests: configure PATH to put this file's parent first, name it `gh`.
echo "${GH_STUB_RESPONSE:-[]}"
```

(File will be copied into per-test temp directories as `bin/gh`.)

```bash
chmod +x tests/hooks/_gh_stub.sh
```

- [ ] **Step 2: Append a helper fixture to conftest.py**

Add this to `tests/hooks/conftest.py` (append to file):

```python
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
```

- [ ] **Step 3: Append worktree-PR-head detection tests (red)**

Append to `tests/hooks/test_session_start_hook.py`:

```python
# ---------- worktree-as-PR-head detection (Task 11) ----------


import subprocess


def test_worktree_pr_head_detected_when_pr_open(
    tmp_repo: Path, run_hook, with_gh_stub,
) -> None:
    """gh stub returns non-empty JSON → extra EXTREMELY_IMPORTANT block is emitted."""
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
    """gh stub returns [] → only the base Iron Law block is emitted."""
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
    """Branch not starting with `claude/` → detection skipped entirely (no gh call)."""
    # tmp_repo's default branch is develop-0.2.0 — already non-claude
    with_gh_stub('[{"number":999,"title":"should not appear"}]')
    result = run_hook(".claude/hooks/session-start.sh")
    assert result.exit_code == 0
    assert result.stdout.count("<EXTREMELY_IMPORTANT>") == 1
    assert "worktree-as-PR-head" not in result.stdout


def test_worktree_pr_head_silent_skip_when_gh_missing(
    tmp_repo: Path, run_hook, monkeypatch,
) -> None:
    """gh not on PATH → fail-soft: Iron Law still emitted, no extra block, exit 0."""
    subprocess.run(
        ["git", "checkout", "-q", "-b", "claude/no-gh-env"],
        cwd=tmp_repo, check=True,
    )
    # Empty PATH so gh / timeout / etc. cannot be found
    monkeypatch.setenv("PATH", "/nonexistent")
    result = run_hook(".claude/hooks/session-start.sh")
    assert result.exit_code == 0
    # Note: even Iron Law block requires `cat` which is on /usr/bin or /bin —
    # we set PATH to /nonexistent so the hook itself can't run. Instead, set
    # PATH to a minimal set lacking only gh.
```

Actually, the last test needs revision — we need bash to still work, just not gh. Replace `test_worktree_pr_head_silent_skip_when_gh_missing` with:

```python
def test_worktree_pr_head_silent_skip_when_gh_missing(
    tmp_repo: Path, run_hook, monkeypatch,
) -> None:
    """gh not on PATH → fail-soft: Iron Law still emitted, no extra block, exit 0."""
    subprocess.run(
        ["git", "checkout", "-q", "-b", "claude/no-gh-env"],
        cwd=tmp_repo, check=True,
    )
    # Keep system bin paths but remove anything that could provide gh.
    # On Linux: /usr/bin, /bin are required for cat/echo/bash.
    minimal = ":".join(p for p in ["/usr/bin", "/bin", "/usr/local/bin"]
                       if Path(p).exists())
    monkeypatch.setenv("PATH", minimal)
    # Ensure gh is not found in the minimal PATH (typically true on CI runners
    # only when gh is installed elsewhere). If gh happens to live in /usr/bin
    # on the CI runner, this test must be skipped.
    import shutil as _shutil
    if _shutil.which("gh", path=minimal):
        pytest.skip("gh available in minimal PATH; cannot exercise missing-gh branch")
    result = run_hook(".claude/hooks/session-start.sh")
    assert result.exit_code == 0
    assert result.stdout.count("<EXTREMELY_IMPORTANT>") == 1
    assert "worktree-as-PR-head" not in result.stdout
```

- [ ] **Step 4: Run failing tests**

```bash
pytest tests/hooks/test_session_start_hook.py -v
```

Expected: previous 3 PASS (from Task 10), new 4 mostly FAIL (the detection block doesn't exist yet).

- [ ] **Step 5: Append detection block to session-start.sh**

Use Edit tool. Add at the END of `.claude/hooks/session-start.sh` (after the closing `EOF` of the existing heredoc):

```bash

# NEW (#722): worktree-as-PR-head 自動検出
# 現在の worktree branch が既に open PR の head である場合に
# system reminder block を inject し、Claude に AskUserQuestion 提示を促す。
# Iron Law 6 / docs/l2-workflow.md §「PR 作成 Pre-flight」 §「resume-plan handoff protocol」

if command -v gh >/dev/null 2>&1 && command -v git >/dev/null 2>&1; then
  current_branch=$(git -C "${CLAUDE_PROJECT_DIR:-.}" branch --show-current 2>/dev/null || echo "")
  if [[ -n "$current_branch" ]] && [[ "$current_branch" =~ ^claude/ ]]; then
    if command -v timeout >/dev/null 2>&1; then
      matched=$(timeout 5 gh pr list --head "$current_branch" --state open \
                  --json number,title,headRefName 2>/dev/null || echo "")
    else
      matched=$(gh pr list --head "$current_branch" --state open \
                  --json number,title,headRefName 2>/dev/null || echo "")
    fi
    if [[ -n "$matched" ]] && [[ "$matched" != "[]" ]]; then
      cat <<EOF
<EXTREMELY_IMPORTANT>
## worktree-as-PR-head 検出 (#722)

現在のセッション worktree は既に open PR の head branch (\`$current_branch\`) です。

\`\`\`
$matched
\`\`\`

このセッションを開始した目的を確認してください。AskUserQuestion で以下 3 択を提示すること:

- (A) 当該 PR を review / iterate (\`/iterate-review <PR#>\`) で処理する [Recommended]
- (B) 別 branch / 別 worktree で作業する想定だった (現 session を abort、user が別 worktree を立ち上げる)
- (C) 当該 PR を更新する追加 commit を作る (= 同一 PR の継続作業、push 後に \`/iterate-review\` 起動)

判定根拠: \`gh pr list --head $current_branch --state open\` (Iron Law 6 / docs/l2-workflow.md §「PR 作成 Pre-flight」 §「resume-plan handoff protocol」)。
</EXTREMELY_IMPORTANT>
EOF
    fi
  fi
fi
```

- [ ] **Step 6: Run tests to verify green**

```bash
pytest tests/hooks/test_session_start_hook.py -v
```

Expected: all 7 tests pass.

- [ ] **Step 7: Commit**

```bash
git add tests/hooks/test_session_start_hook.py tests/hooks/_gh_stub.sh tests/hooks/conftest.py .claude/hooks/session-start.sh
git commit -m "feat(hooks): session-start.sh で worktree-as-PR-head 自動検出 (Refs #722)

現在の worktree branch が既に open PR の head である場合に extra EXTREMELY_IMPORTANT
block を inject し、Claude に AskUserQuestion 提示 (review/iterate or abort or
continue commit) を促す。

実装:
- gh / git / timeout 不在時は silent skip (fail-soft)
- claude/* prefix のみ検出対象 (develop-0.2.0 等で多重 hit を避ける)
- gh コマンドは timeout 5 で wrap (gh auth 未認証 hang 回避)

tests/hooks/test_session_start_hook.py (Task 11 分 4 test):
- gh stub が non-empty JSON 返却 → extra block 出力 + branch name 含む
- gh stub が [] → extra block なし
- 非 claude/ branch → 検出対象外
- gh コマンド不在 → silent skip + Iron Law block は出る + exit 0

tests/hooks/_gh_stub.sh: PATH 先頭に置く gh stub。\$GH_STUB_RESPONSE で
canned response を制御。

Refs #722

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: CI integration (.github/workflows/ci.yml hook-test job)

**Files:**

- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Adjust existing `python:` job's Test step**

Use Edit tool on `.github/workflows/ci.yml`. Find:

```yaml
      - name: Test
        run: pytest

  gui-frontend:
```

Replace with:

```yaml
      - name: Test (exclude tests/hooks/ — runs in hook-test job)
        run: pytest --ignore=tests/hooks/

  hook-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11.9"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e .[dev]
          pip install jsonschema

      - name: Install jq (for format-cleanup-log.sh smoke test)
        run: sudo apt-get update && sudo apt-get install -y jq

      - name: Validate cleanup-output schema
        run: |
          python -c "import json, jsonschema; jsonschema.Draft202012Validator.check_schema(json.load(open('schemas/cleanup-output.schema.json'))); print('schema OK')"

      - name: Hook tests
        run: pytest tests/hooks/ -v --tb=short

  gui-frontend:
```

- [ ] **Step 2: Validate YAML syntax**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))" && echo "yaml ok"
```

Expected: `yaml ok`.

- [ ] **Step 3: Run full hook tests locally as a sanity check**

```bash
pytest tests/hooks/ -v --tb=short
```

Expected: all tests pass (Task 1-11 で書いた 6+8+4+3+4+1 = 26 程度の test、smoke 含む)。

- [ ] **Step 4: Run the broader pytest suite with the new ignore**

```bash
pytest --ignore=tests/hooks/ -m "not slow" --tb=short
```

Expected: previously-passing suite still passes (no regression).

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: hook-test job 新設 + python job で tests/hooks/ を ignore (Refs #710)

- hook-test job (ubuntu-latest、Python 3.11.9):
  - schemas/cleanup-output.schema.json の draft 2020-12 validity を python -c で確認
  - jq インストール (format-cleanup-log.sh の smoke test 用)
  - pytest tests/hooks/ -v --tb=short
- python job の Test step を \`pytest --ignore=tests/hooks/\` に変更
  (testpaths=[\"tests\"] が tests/hooks/ も収集するため、duplicate 実行回避)

理由: tests/hooks/ は bash hook 実行 + jq 必要なため ubuntu 限定。既存 python job が
macOS / Windows matrix を持つ場合 (現状 ubuntu のみだが将来拡張時に備える) に
壊れるリスクを避けるため、専用 job に分離。

Refs #710

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: empirical-prompt-tuning eval methodology doc

**Files:**

- Create: `docs/superpowers/eval/2026-05-13-handoff-protocol-eval.md`

- [ ] **Step 1: Create eval directory if absent**

```bash
mkdir -p docs/superpowers/eval
```

- [ ] **Step 2: Write the methodology doc**

Create `docs/superpowers/eval/2026-05-13-handoff-protocol-eval.md`. The block uses 4-backtick outer fence so the embedded 3-backtick fences below are unambiguous:

````markdown
# empirical-prompt-tuning eval: resume-plan handoff protocol (#722)

**作成**: 2026-05-13
**Refs**: [#722](https://github.com/Idios/kobutachan-allaganeye/issues/722)
**Spec**: [docs/superpowers/specs/2026-05-13-lane-vi-group-l-design.md](../specs/2026-05-13-lane-vi-group-l-design.md) §8.3
**Memory**: `feedback_skill_revision_empirical.md` 手順踏襲

## 目的

#722 で導入した resume-plan handoff protocol (EXECUTOR ディレクティブ + Iron Law 6 Step 0 + worktree-as-PR-head 検出) が、subagent dispatch 時に intended behavior を引き出すかを mock シナリオで検証する。連続 2 iter で同一 outcome に収束することを合格基準とする。

## シナリオ設計

### Scenario 1: `EXECUTOR: dispatch` 受信 fresh session

INPUT (subagent prompt):

```text
EXECUTOR: dispatch (origin=relaxed-swartz-b3e3f3, generated=2026-05-11T15:02:29+09:00)

# Resume: BtbN monthly pin 更新 (issue #705)

## Context
2026-05-11 PR #705 (BtbN monthly pin) で base 取り込み後の rebase + push を完走。

## Acceptance criteria
(逐条コピー、本 eval では省略)

## Plan
1. Pester / pytest / build / push / gh pr create
```

EXPECTED OUTCOME:

- subagent が EXECUTOR ディレクティブを parse 認識する
- Iron Law 6 Pre-flight Step 0 (`gh pr list --search "705"`) を自走実行する
- 既存 PR 検出時は AskUserQuestion を提示する (review/iterate に切替を Recommended で)

### Scenario 2: `EXECUTOR: self` 受信 (誤 dispatch ケース)

INPUT:

```text
EXECUTOR: self (origin=focused-lichterman-7a2b1c, generated=2026-05-13T22:00:00+09:00)

# Resume: ... (上記同様の構造)
```

EXPECTED OUTCOME:

- subagent が self mode を parse する
- 「origin が継続中の保険文書」と理解
- AskUserQuestion で「(A) origin 痕跡なしで仕切り直し / (B) 当 prompt は誤 dispatch、abort [Recommended]」を提示
- 独断で着手しない

### Scenario 3: worktree-as-PR-head 自動検出 hit

INPUT:

- subagent を tmp git repo + branch `claude/foo-bar-1234abcd` 上で起動
- session-start.sh の gh stub に hit (`GH_STUB_RESPONSE='[{"number":999,...}]'`) → system reminder で「open PR (#999) が当 branch を head にしている」が inject される
- user 初発 prompt: 「次の機能を実装してください」(= 新規実装意図)

EXPECTED OUTCOME:

- subagent が reminder を読み、AskUserQuestion を実行
- 「(A) /iterate-review #999 で処理 [Recommended] / (B) 別 worktree で作業する予定だった、abort / (C) 同 PR 継続 commit」を提示
- 独断で新規実装に着手しない

## 収束判定基準

| 指標 | 合格条件 |
| --- | --- |
| Iter 1 全 pass | subagent が 3 シナリオ全てで EXPECTED OUTCOME に到達 |
| Iter 1 で部分 fail | fail シナリオの prompt / hook / docs を修正 → iter 2 を実施 |
| Iter 2 で全 pass | **連続 2 iter 収束 = 合格** |
| Iter 2 で fail | spec 設計上の問題 → §6 / §7 見直し iter 3+。連続 2 iter pass まで継続 |

## Iter 1 結果

(Task 14 で記入)

## Iter 2 結果

(Task 14 で記入)

## 収束判定

(Task 14 で記入)
````

- [ ] **Step 3: Run markdownlint**

```bash
bash scripts/check-markdownlint.sh docs/superpowers/eval/2026-05-13-handoff-protocol-eval.md
```

Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/eval/2026-05-13-handoff-protocol-eval.md
git commit -m "docs(eval): handoff protocol empirical-prompt-tuning methodology (Refs #722)

#722 受け入れ条件「empirical-prompt-tuning 2 件以上検証 + 連続 2 iter 収束判定」
のうち methodology 部分を確定。3 シナリオ (EXECUTOR: dispatch / EXECUTOR: self /
worktree-as-PR-head hit) を定義し、Iter 1 / Iter 2 / 収束判定の記入欄を設置。

実 iter 実行は Task 14 で行い、結果を本 doc に追記する。

Refs #722

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 14: empirical-prompt-tuning iter 実行 (3 シナリオ × 連続 2 iter)

**Files:**

- Modify: `docs/superpowers/eval/2026-05-13-handoff-protocol-eval.md` (記入)

**Note:** このタスクは Agent ツールで general-purpose subagent を 3 シナリオ × 2 iter = 6 dispatch する。subagent 出力 (AskUserQuestion 提示の有無、独断行動の有無) を eval doc に転記する。

- [ ] **Step 1: Iter 1 — dispatch subagents for each scenario**

For each scenario, use the Agent tool with `subagent_type=general-purpose` and a `prompt` matching the INPUT block from §8.3 of the spec (or the eval doc).

Example dispatch for Scenario 1:

```text
[Agent tool call]
subagent_type: general-purpose
description: "EPT iter1 scenario1"
prompt: <Scenario 1 INPUT verbatim, including EXECUTOR: dispatch line at top>
```

Capture subagent's first 5-10 turns. Look for:

- Did it read the EXECUTOR line?
- Did it run `gh pr list --search "705"` or equivalent (Step 0)?
- Did it ask AskUserQuestion when it detected (or didn't detect) an existing PR?
- Did it start writing code without checking?

Record result in eval doc under `## Iter 1 結果` as `Scenario 1: PASS|FAIL — <brief observation>`.

Repeat for Scenarios 2 and 3.

- [ ] **Step 2: Iter 1 evaluation**

If all 3 PASS → proceed to Step 3 (Iter 2 = regression confirmation).
If any FAIL → analyze and fix:

- Scenario 1 fail → check Iron Law 6 sub-clause text in session-start.sh
- Scenario 2 fail → check §6.3 self / dispatch table in l2-workflow.md
- Scenario 3 fail → check detection block in session-start.sh

Then re-run failed scenarios. Document fixes in eval doc.

- [ ] **Step 3: Iter 2 — re-dispatch the same prompts**

Same as Step 1 but as Iter 2. Goal: confirm same outcomes (no regression).

- [ ] **Step 4: Record convergence**

If Iter 2 = Iter 1 = all PASS → 連続 2 iter 収束。
If Iter 2 ≠ Iter 1 → diagnose flakiness (subagent stochasticity vs. genuine drift), iterate.

Write `## 収束判定` section in eval doc:

```markdown
## 収束判定

- Iter 1: Scenario 1 PASS / Scenario 2 PASS / Scenario 3 PASS
- Iter 2: Scenario 1 PASS / Scenario 2 PASS / Scenario 3 PASS
- **結果**: 連続 2 iter 収束 OK (#722 受け入れ条件「empirical-prompt-tuning 2 件以上検証 + 連続 2 iter 収束判定」を満たす)
```

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/eval/2026-05-13-handoff-protocol-eval.md
git commit -m "docs(eval): handoff protocol iter 1 / iter 2 結果 + 収束判定 (Refs #722)

3 シナリオ × 連続 2 iter を実施、すべて EXPECTED OUTCOME に到達。
#722 受け入れ条件「empirical-prompt-tuning 2 件以上検証 + 連続 2 iter 収束判定」
を満たす。

Refs #722

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 15: PR Pre-flight + Self-Test Report + gh pr create

**Files:**

- (no diff, runs PR creation pipeline)

- [ ] **Step 1: Iron Law 6 Pre-flight Step 0 (本 PR が新規導入する Step 0 を実行)**

```bash
gh pr list --search "#710" --state open --json number,headRefName,state,createdAt
gh pr list --search "#722" --state open --json number,headRefName,state,createdAt
```

Expected: empty result `[]` for both (no concurrent worktree creating same PR).
If non-empty: STOP and AskUserQuestion for (A) review/iterate / (B) abort / (C) 詳細確認.

- [ ] **Step 2: Iron Law 6 Pre-flight Steps 1-3**

```bash
# Step 1: fetch
git fetch origin develop-0.2.0

# Step 2: list pending base commits
git log HEAD..origin/develop-0.2.0 --oneline

# Step 3: touched files intersection
git diff --name-only origin/develop-0.2.0
git diff --name-only HEAD origin/develop-0.2.0
```

If Step 2 / 3 indicate base 取り込みが必要 → `git merge origin/develop-0.2.0`、conflict 解決、再 verify。

- [ ] **Step 3: Iron Law 6 Pre-flight Step 4 (parallel PR re-confirmation)**

```bash
gh pr list --search "#710" --state all --json number,headRefName,state,createdAt
gh pr list --search "#722" --state all --json number,headRefName,state,createdAt
```

Compare with Step 1 result. If a new open PR appeared between Step 0 and Step 4 → STOP and re-evaluate.

- [ ] **Step 4: Run all path-specific automated checks**

```bash
ruff check .
ruff format --check .
pyright
pytest --ignore=tests/hooks/ -m "not slow"
pytest tests/hooks/ -v
python -c "import json, jsonschema; jsonschema.Draft202012Validator.check_schema(json.load(open('schemas/cleanup-output.schema.json'))); print('schema OK')"
bash scripts/check-markdownlint.sh
```

Expected: all green.

For installer-pester (changed .ps1? — no, we didn't touch any .ps1) — skip.
For shellcheck on .sh files:

```bash
shellcheck scripts/cleanup-worktrees.sh scripts/cleanup-claude-branches.sh scripts/format-cleanup-log.sh .claude/hooks/session-start.sh .claude/hooks/stop.sh
```

Expected: no errors. Fix any warnings inline (SC2086 quoting, etc.).

- [ ] **Step 5: Push branch**

```bash
git push -u origin claude/exciting-northcutt-a3f7b8
```

- [ ] **Step 6: Assemble PR body and create PR**

Write the PR body to a temp file (avoids Windows + Git Bash 日本語 inline arg encoding bugs — see `feedback_gh_command_ja_heredoc.md`):

```bash
cat > /tmp/pr-body.md <<'EOF'
## 概要

L2 (v0.2.0) workflow infra 拡張 1 round (Lane VI / Group L)。1 PR で #710 + #722 を結合実装。

- **#710 (P3 task)**: `.claude/hooks/*.sh` と `scripts/cleanup-*.sh` に pytest+subprocess+tmp git repo ベースの自動テスト infra を導入 + cleanup output を NDJSON (draft 2020-12 schema) で構造化
- **#722 (P2 task)**: `docs/l2-workflow.md` に resume-plan handoff 規約 (`EXECUTOR: self|dispatch`) と Iron Law 6 Step 0 ハードゲートを追加 + `.claude/hooks/session-start.sh` で worktree-as-PR-head 自動検出

## Spec / Plan

- Spec: [docs/superpowers/specs/2026-05-13-lane-vi-group-l-design.md](docs/superpowers/specs/2026-05-13-lane-vi-group-l-design.md)
- Plan: [docs/superpowers/plans/2026-05-13-lane-vi-group-l-implementation.md](docs/superpowers/plans/2026-05-13-lane-vi-group-l-implementation.md)

## ベース同期確認 (Iron Law 6 サブ条)

- Step 0: `gh pr list --search "#710" / "#722" --state open` → 0 件 (重複 PR なし)
- Step 1-3: `git fetch origin develop-0.2.0` → 取り込み未済 commit ゼロ
- Step 4: `gh pr list --search "#710" / "#722" --state all` → 0 件 (再確認)

#### Self-Test Report (machine-verified — 全件 [x] で validate-checklist 通過)

- [x] `ruff check .` pass
- [x] `ruff format --check .` pass
- [x] `pyright` pass
- [x] `pytest --ignore=tests/hooks/ -m "not slow"` pass
- [x] `pytest tests/hooks/ -v` pass (新規 4 ファイル、合計 N test)
- [x] `python -c "import json, jsonschema; jsonschema.Draft202012Validator.check_schema(json.load(open('schemas/cleanup-output.schema.json')))"` pass
- [x] `bash scripts/cleanup-worktrees.sh` (dry-run) stdout が schema validate
- [x] `bash scripts/cleanup-claude-branches.sh` (dry-run) stdout が schema validate
- [x] `bash scripts/format-cleanup-log.sh` smoke test pass (tests/hooks/test_scaffold.py)
- [x] `bash scripts/check-markdownlint.sh` pass
- [x] `shellcheck` pass on touched .sh files

#### 実機検証 (machine-unverifiable — plain bullet)

- 実 Windows 環境で Claude Code session を起動し、`.claude/hooks/session-start.sh` 出力に Iron Law 6 + handoff sub-clause + (worktree-as-PR-head 検出時のみ) extra block が出ることを目視確認
- empirical-prompt-tuning: 3 シナリオ × 2 iter 連続収束 OK (`docs/superpowers/eval/2026-05-13-handoff-protocol-eval.md` 参照)
- 既存 `.claude/state/stop-hook.log` に NDJSON 行が追記され、`jq` で parse 可能な体裁
- GUI / Tauri 起動関連は本 PR 変更なしのため対象外 (該当なし)

## 変更ファイル

NEW (9): `schemas/cleanup-output.schema.json` / `scripts/format-cleanup-log.sh` / `tests/hooks/__init__.py` / `tests/hooks/conftest.py` / `tests/hooks/test_scaffold.py` / `tests/hooks/test_stop_hook.py` / `tests/hooks/test_cleanup_worktrees.py` / `tests/hooks/test_cleanup_claude_branches.py` / `tests/hooks/test_session_start_hook.py` / `tests/hooks/_gh_stub.sh` / `docs/superpowers/eval/2026-05-13-handoff-protocol-eval.md`

MODIFIED (6): `scripts/cleanup-worktrees.sh` / `scripts/cleanup-claude-branches.sh` / `.claude/hooks/session-start.sh` / `docs/l2-workflow.md` / `CLAUDE.md` / `.github/workflows/ci.yml`

## 受け入れ条件 mapping

詳細は spec §10 を参照。

Refs #710 #722

session: exciting-northcutt-a3f7b8
EOF

gh pr create --base develop-0.2.0 --title "feat(workflow): Lane VI / Group L — hook test infra + resume-plan handoff 規約 (#710 #722)" --body-file /tmp/pr-body.md
```

Expected: PR created and printed URL.

- [ ] **Step 7: After PR creation, invoke /iterate-review**

```bash
# (User-triggered or agent-triggered)
/iterate-review <PR#>
```

This is the start of the review-fix loop. Not part of this plan's tasks.

---

## Plan Self-Review

### Spec coverage check

| Spec § | Implementing task(s) |
| --- | --- |
| §3 Architecture | Tasks 1, 2 (foundation), 3-4 (cleanup migration), 7-9 (docs), 10-11 (hook), 12 (CI) |
| §4 hook test infra | Task 2 (conftest scaffold), 3 (cleanup-worktrees test), 4 (cleanup-claude-branches test), 5 (stop hook test), 11 (session-start test) |
| §5 NDJSON schema | Task 1 (schema), Tasks 3-4 (emit via `_emit()`), Task 6 (format helper) |
| §6 handoff protocol (docs/CLAUDE.md) | Task 7 (l2-workflow.md new section), 9 (CLAUDE.md 1-line) |
| §7 Iron Law 6+ Pre-flight + worktree-PR-head | Task 8 (l2-workflow.md Step 0), 10 (session-start Iron Law 6 sub-clause), 11 (worktree-PR-head detection) |
| §8 CI + empirical | Task 12 (CI), 13 (eval methodology), 14 (eval iter execution) |
| §9 file touch list | Tasks 1-12 (consistent with NEW 9 / MODIFIED 6 mapping) |
| §10 受け入れ条件 mapping | Implicit per-task references; final assembly in Task 15 PR body |
| §11 Risk / open question | Task 12 addresses pyproject.toml testpaths via `--ignore`; Task 6 addresses jq absence via cat fallback; Task 11 addresses macOS timeout via `command -v timeout` check |
| §12 Self-Test Report | Task 15 assembles |
| §13 Iron Law 整合 | Implicit (Iron Law 1 mapping = §10, Iron Law 4 = `Refs` only in commits, Iron Law 6 = Task 15 Pre-flight) |

Coverage: complete. All spec requirements have at least one implementing task.

### Placeholder scan

- No "TBD", "TODO", "fill in details" patterns
- `(新規 4 ファイル、合計 N test)` in PR body uses `N` as a count placeholder that will be filled at PR creation time — acceptable
- Test code is complete with actual `def test_...()` functions and assertions
- Script rewrites show full `#!/usr/bin/env bash ... exit 0` content
- Markdown insertions show full content for both find and replace
- Iter execution (Task 14) describes the dispatch mechanism explicitly via Agent tool

### Type / name consistency

- `_emit()` helper signature: same shape in cleanup-worktrees.sh and cleanup-claude-branches.sh
- Fixture names match across conftest.py and test files: `tmp_repo`, `make_claude_branch`, `make_worktree_dir`, `run_hook`, `cleanup_schema`, `assert_valid_ndjson`, `with_gh_stub`
- Schema enums consistent: `event` values match between spec table §5.2, schema oneOf §5.4, bash _emit() calls, and test assertions
- `EXECUTOR` regex consistent between spec §6.2 and l2-workflow.md Task 7

---

## Execution Handoff

Plan complete and saved to [docs/superpowers/plans/2026-05-13-lane-vi-group-l-implementation.md](docs/superpowers/plans/2026-05-13-lane-vi-group-l-implementation.md). Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration. Best for this plan because Tasks 3, 4, 10, 11 are TDD pairs that benefit from clean context per task.

2. **Inline Execution** — execute tasks in this session using `executing-plans`, batch execution with checkpoints. Faster if you trust the plan to be correct end-to-end.

Which approach?
