# L-α CI / hook 補強 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** retro spec の L-α (CI/hook 補強) を 3 PR で実装。M1 (release.yml PS5.1 dual matrix) / M6 (stop.sh orphan 検出 + session-start.sh 警告表示) / M7 (docs/issue-policy.md §path↔scope 対応表 + preuse.py heuristic scope check) を完成させ、F1 / F6 / F7 の再発を実行時に検出可能にする。

**Architecture:** 各 PR は独立 reviewable。M1 は CI workflow 変更で `windows-latest` runner 上の matrix 化 (~+5-10 min/PR で許容)、M6 は既存 stop.sh + session-start.sh の延伸、M7 は preuse.py の heuristic + docs 表新設。M7 は TodoWrite 直接読みではなく **staged paths の multi-scope 検出**で簡略化 (preuse.py から TodoWrite state にアクセスできないため)、false positive 寄り safety で運用。

**Tech Stack:** GitHub Actions YAML matrix / Bash (stop.sh) / Python (preuse.py、stdlib only) / Pester (Windows test) / markdownlint-cli2

**Spec reference:** [docs/superpowers/specs/2026-05-17-v020-v021-retro-codex-integration-design.md](../specs/2026-05-17-v020-v021-retro-codex-integration-design.md) §M1 / §M6 / §M7

**Worktree:** `E:\projects\kobutachan-tools\kobutachan-allaganeye\.claude\worktrees\nervous-hoover-464244` (branch: `claude/nervous-hoover-464244`, base: `develop-0.3.0`)

---

## File Structure

| 種別 | path | 担当 Task |
| --- | --- | --- |
| 更新 | `.github/workflows/release.yml` (build-windows job に matrix.shell を追加) | Task 1 (α-1, M1) |
| 更新 | `.claude/hooks/stop.sh` (orphan commit 検出 step 追加) | Task 2 (α-2, M6) |
| 更新 | `.claude/hooks/session-start.sh` (前セッション orphan 警告表示) | Task 2 (α-2, M6) |
| 更新 | `docs/issue-policy.md` (§path↔scope 対応表 新設) | Task 3 (α-3, M7) |
| 更新 | `.claude/hooks/preuse.py` (scope check 拡張) | Task 3 (α-3, M7) |
| 新規 | `tests/hooks/test_preuse_scope_check.py` | Task 3 (α-3, M7) |

---

## Pre-flight (実装開始前に 1 回)

- [ ] **Step 0.1: base ブランチ最新化**

```bash
git fetch origin develop-0.3.0
git status
```

Expected: `Your branch is ahead of 'origin/develop-0.3.0' by N commits`。working tree clean。

- [ ] **Step 0.2: 既存 hook test 場所を確認**

```bash
ls tests/hooks/ 2>&1
```

Expected: `test_preuse_*` 系の既存テスト file がある (`pytest tests/hooks/` で実行される)。

- [ ] **Step 0.3: issue #737 (M1 で close 予定) の current state を確認**

```bash
gh issue view 737 --json number,state,title,labels
```

Expected: state OPEN、label `enhancement / role:lead-engineer / P3-low / deferred / l2b-installer`。本 Lane で close 候補。

---

## Task 1 (PR α-1, M1): release.yml に PowerShell 5.1 matrix を追加

**Files:**

- Modify: `.github/workflows/release.yml` (build-windows job)

### 設計判断

`build-windows` job を `strategy.matrix.shell: [pwsh, powershell]` で 2 並列実行する。各 step の `shell:` を `${{ matrix.shell }}` に書き換える。Artifact upload は `pwsh` (PS 7+) のみで行い (現状の挙動を保持)、`powershell` (PS 5.1) は smoke-test 専用。これにより M1 受け入れ基準「PS 5.1 silent regression を CI が検出」を満たす。

PR CI 時間影響: build-windows が 2 並列で wall-clock +0 min、Windows minute は ×2 (~14 min → ~28 min)。release.yml は paths-filter で gate されているため毎 PR 走らない (Python-only 等は skip)。

### 実装手順

- [ ] **Step 1.1: release.yml build-windows job の現状を確認**

```bash
sed -n '90,115p' .github/workflows/release.yml
```

`runs-on: windows-latest` + `needs: version-check` + steps 群 (pwsh) を把握。

- [ ] **Step 1.2: build-windows job に strategy.matrix.shell を追加**

`.github/workflows/release.yml` の `build-windows:` job 定義に以下を追加 (`runs-on:` の直前):

```yaml
  build-windows:
    needs: version-check
    runs-on: windows-latest
    strategy:
      fail-fast: false  # PS 5.1 と pwsh の独立検出のため fail-fast: false
      matrix:
        shell: [pwsh, powershell]
    name: build-windows (${{ matrix.shell }})
    steps:
```

(既存の `runs-on:` 行はそのままで、`needs:` の後に `strategy:` block を挿入。`name:` で job display 名に shell を出す。)

- [ ] **Step 1.3: build-windows 内の `shell: pwsh` を `shell: ${{ matrix.shell }}` に置換**

`.github/workflows/release.yml` の build-windows 内 6 箇所の `shell: pwsh` (line 135 / 140 / 145 / 152 / 167 / 197 / 253 等、grep で正確に取得して置換):

```bash
# 確認
grep -n "shell: pwsh" .github/workflows/release.yml | head -10
```

各 hit が build-windows job 内 (line 92-310 の範囲) なら `${{ matrix.shell }}` に置換。`release:` job (line 311+) の `shell: pwsh` は **置換しない** (linux runner なので shell 関係ない、別 job)。

実装は Edit tool で 1 箇所ずつ context つきで置換 (`replace_all` は build-windows と release で混在するため不適切):

```bash
# 例: line 135 の Smoke test --version
```

各 step に `shell: ${{ matrix.shell }}` を適用。

- [ ] **Step 1.4: upload-artifact step を pwsh 限定にする**

`.github/workflows/release.yml` の upload-artifact step (line ~298):

```yaml
      - uses: actions/upload-artifact@v4
        if: github.event_name == 'pull_request' || (github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v'))
```

を以下に変更:

```yaml
      - uses: actions/upload-artifact@v4
        # matrix で 2 shell 並列実行する場合、artifact 名衝突を避けるため pwsh のみで upload。
        # PS 5.1 job は smoke-test 専用 (M1 / F1 regression 検出)。
        if: matrix.shell == 'pwsh' && (github.event_name == 'pull_request' || (github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')))
```

- [ ] **Step 1.5: release job の needs を build-windows pwsh job に絞る**

`.github/workflows/release.yml` の `release:` job (line ~311) の `needs:` を確認。現状は `needs: [version-check, build-windows]`。matrix 化により `build-windows` は 2 job (pwsh / powershell) になるため、`needs: [version-check, build-windows]` は両方の完了を待つ default 挙動になる。

問題点: release job は artifact download に依存するが、artifact upload は pwsh のみ。release job は両 matrix の完了を待つことで PS 5.1 smoke-test 結果も confirm されてから release tag を打つ flow になる。これは想定通り (M1 受け入れ基準: PS 5.1 で fail なら release blocker)。

修正不要。

- [ ] **Step 1.6: ローカルで yaml syntax check**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml', encoding='utf-8')); print('YAML OK')"
```

Expected: `YAML OK`。

- [ ] **Step 1.7: act または workflow_dispatch dry-run で smoke test (オプション)**

local act が無ければ skip。push 後の CI 実行で確認する。

- [ ] **Step 1.8: 既存 issue #737 を本 PR 内で close する宣言を PR 本文に書く準備**

commit message に `Closes #737` を**書かない** (Iron Law 4)。代わりに `Refs #737` のみ。マージ後の post-merge 検証で手動 close。

- [ ] **Step 1.9: PR α-1 を commit**

```bash
git add .github/workflows/release.yml
git commit -m "$(cat <<'EOF'
ci(release): build-windows に PowerShell 5.1 dual matrix を追加 (Refs spec L-α M1, Refs #737)

release.yml の build-windows job を strategy.matrix.shell: [pwsh, powershell]
で 2 並列実行する。`shell: pwsh` を `shell: ${{ matrix.shell }}` に置換し、
6 smoke-test step を両 shell で実行。upload-artifact は pwsh 限定にして
artifact 名衝突を回避。release job は両 matrix 完了後に走るため、PS 5.1 で
fail すれば release blocker になる (F1 silent regression 検出)。

memory feedback_ps_setcontent_utf8_bom の hook 昇格 (#737 で tracking)。
issue #737 は post-merge 受け入れ条件検証後に手動 close。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2 (PR α-2, M6): stop.sh に orphan commit 検出 + session-start.sh で警告表示

**Files:**

- Modify: `.claude/hooks/stop.sh` (orphan detection block 追加)
- Modify: `.claude/hooks/session-start.sh` (前セッション警告表示 block 追加)
- `.gitignore` 確認 (`.claude/state/orphan-commits.log` が gitignored であること)

### 設計判断

stop.sh で `git fsck --unreachable --no-reflogs` を実行し、author 名に `claude` を含む unreachable commit (heuristic) を `.claude/state/orphan-commits.log` に append する。session-start.sh は次セッション開始時にこのログを読んで警告表示し、user が `git cherry-pick` で復旧したら手動でログを clear する運用。

heuristic (author 名 grep) は false positive あり (例: `Claude Opus` co-author trailer 持ちの正常 commit) のため、警告のみで block しない。誤検出時は user が無視するだけで済む。

### 実装手順

- [ ] **Step 2.1: stop.sh の current state を Read**

既に把握済 (74 行、cleanup-worktrees + cleanup-claude-branches を順次起動、`{ ... } >> "$LOG" 2>&1` で集約ログ)。

- [ ] **Step 2.2: stop.sh に orphan commit 検出 block を追加**

`.claude/hooks/stop.sh` の既存 `{ ... } >> "$LOG" 2>&1` block (cleanup 起動) の **直後** (= block を抜けた後) に以下を追加:

```bash
# Orphan commit detection (M6, F7 #741 教訓)
# subagent が detached HEAD で commit すると orphan 化することがある。
# git fsck で unreachable commit を抽出し、claude author の commit を
# .claude/state/orphan-commits.log に記録。session-start.sh が次セッション
# 開始時に表示する。
ORPHAN_LOG="$REPO_ROOT/.claude/state/orphan-commits.log"
{
  echo "===== $(date -Iseconds 2>/dev/null || date) stop.sh orphan check ====="
  if command -v git >/dev/null 2>&1 && [[ -d "$REPO_ROOT/.git" ]]; then
    UNREACHABLE=$(cd "$REPO_ROOT" && git fsck --unreachable --no-reflogs 2>/dev/null | awk '$2 == "commit" {print $3}')
    if [[ -n "$UNREACHABLE" ]]; then
      for sha in $UNREACHABLE; do
        AUTHOR=$(cd "$REPO_ROOT" && git show --no-patch --format="%an" "$sha" 2>/dev/null || echo "?")
        SUBJECT=$(cd "$REPO_ROOT" && git show --no-patch --format="%s" "$sha" 2>/dev/null || echo "?")
        # heuristic: author に "laude" を含む (Claude / claude) なら orphan 候補
        if [[ "$AUTHOR" == *"laude"* ]]; then
          echo "  orphan candidate: $sha | $AUTHOR | $SUBJECT"
          echo "$(date -Iseconds 2>/dev/null || date)|$sha|$AUTHOR|$SUBJECT" >> "$ORPHAN_LOG"
        fi
      done
    else
      echo "  no unreachable commits"
    fi
  else
    echo "  git unavailable, skip orphan check"
  fi
} >> "$LOG" 2>&1
```

(既存 `{ ... }` block の後、`exit 0` の前に挿入する。)

- [ ] **Step 2.3: session-start.sh の current state を確認**

```bash
head -30 .claude/hooks/session-start.sh
tail -20 .claude/hooks/session-start.sh
```

Iron Law inject の structure を把握し、追加位置を決定 (Iron Law block の **直前** に「過去の orphan 警告」block を出すのが自然)。

- [ ] **Step 2.4: session-start.sh に前セッション orphan 警告表示 block を追加**

`.claude/hooks/session-start.sh` の Iron Law inject (typically `cat <<'EOF'` の前) に以下を挿入:

```bash
# 前セッションで stop.sh が記録した orphan commit があれば警告表示 (M6)
ORPHAN_LOG="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}/.claude/state/orphan-commits.log"
if [[ -f "$ORPHAN_LOG" ]] && [[ -s "$ORPHAN_LOG" ]]; then
  cat <<EOF
⚠️ 前セッションで orphan commit が検出されました (M6 / F7):

$(head -10 "$ORPHAN_LOG")

復旧手順:
- 該当 commit が必要なら: git cherry-pick <SHA> で現 HEAD 上に再生成
- ノイズ (Claude Opus co-author の正常 commit 等) なら: rm "$ORPHAN_LOG" で警告クリア

(本警告は false positive を許容する heuristic です。詳細は docs/l2-workflow.md §subagent 起動規約 を参照)

EOF
fi
```

- [ ] **Step 2.5: `.gitignore` を確認**

```bash
grep -E "\.claude/state/?$|orphan-commits" .gitignore 2>&1
```

`.claude/state/` または `.claude/state/*` が ignore されているか確認。されていれば orphan-commits.log も自動的に ignored。なければ追加:

```bash
# .gitignore 既存内容に応じて必要なら追記
echo ".claude/state/" >> .gitignore  # 既存に無い場合のみ
```

(orphan-commits.log は state file なので、既存の `.claude/state/` ignore を継承する想定。)

- [ ] **Step 2.6: hook test (任意)**

```bash
# fake unreachable commit を意図的に作って stop.sh を invoke (manual test)
# 本格的な test は tests/hooks/test_stop_orphan.py で書くこともできるが、本 PR では skip して
# 実機検証 (次セッションで warning が出るか) で確認する
```

- [ ] **Step 2.7: PR α-2 を commit**

```bash
git add .claude/hooks/stop.sh .claude/hooks/session-start.sh
# .gitignore を変更した場合は同時に add
git commit -m "$(cat <<'EOF'
fix(hooks): stop.sh に orphan commit 検出 + session-start.sh で警告表示 (Refs spec L-α M6)

retro spec §M6 の実装。F7 (#741 Task 5 cda0f8e の detached HEAD orphan) と
同型の事象を session 終端で検出する hook を追加。

stop.sh:
- 既存 cleanup ステップの後に git fsck --unreachable --no-reflogs を実行
- author に "laude" を含む unreachable commit を .claude/state/orphan-commits.log に
  追記 (heuristic、false positive 許容)

session-start.sh:
- 前セッションで記録された orphan log を Iron Law inject の前に表示
- 復旧手順 (git cherry-pick / log clear) を表示

memory feedback_subagent_orphaned_commit の hook 昇格。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3 (PR α-3, M7): docs/issue-policy.md §path↔scope 対応表 + preuse.py heuristic scope check

**Files:**

- Modify: `docs/issue-policy.md` (§path↔scope 対応表 新設)
- Modify: `.claude/hooks/preuse.py` (scope check 拡張)
- Create: `tests/hooks/test_preuse_scope_check.py`

### 設計判断

preuse.py は Claude の TodoWrite state に直接アクセスできない (hook は Bash 実行前に発火する独立 process)。そのため spec が想定する「in_progress todo の scope と staged paths の照合」は不可能。

代替設計: **staged paths の multi-scope 検出** に簡略化。`git commit` 前に `git diff --staged --name-only` で touched files を取得し、`docs/issue-policy.md §path↔scope 対応表` に基づき:

- **distinct scope 数 ≥ 2** → permissionDecision=ask (heuristic: 多 scope 跨ぎ commit は scope creep の可能性)
- **unknown path (対応表 hit 無し)** → permissionDecision=ask (heuristic: 新規 dir は対応表メンテ漏れ or 未分類)
- **single scope** → allow (block しない)

これにより F6 (PR #732 commit `8eff1d2` で bash + gui test 跨ぎ scope creep) と同型の事象を実行時に user 確認させる。false positive (意図的な cross-cutting commit) は user が「許可」を選ぶだけで通過する。

### 実装手順

- [ ] **Step 3.1: docs/issue-policy.md §path↔scope 対応表 を新設**

`docs/issue-policy.md` の §優先度ラベル の **直後** (line ~63 付近) に以下を挿入:

```markdown
### path↔scope 対応表 (preuse.py scope check 用、M7)

preuse.py の git commit pre-hook がこの表を参照して **multi-scope detection** を行う。新規 top-level dir を repo に追加した時は本表も同時に更新すること (path↔scope のメンテ責任)。

| path glob (regex 風) | scope label | 該当 prefix label |
| --- | --- | --- |
| `^allaganeye/` | l1 / l2-cli | bug / refactor / task |
| `^tests/` | l1 / l2-cli | test |
| `^gui/src/` | l2a-gui | feat(gui) / fix(gui) |
| `^gui/src-tauri/` | l2a-gui | feat(gui) / refactor(gui) |
| `^gui/scripts/` | l2a-gui | task |
| `^scripts/` | l2b-installer | feat(installer) / fix(installer) |
| `^\.github/workflows/` | l2-ci | ci |
| `^\.github/ISSUE_TEMPLATE/` | l2-workflow | task / doc |
| `^\.claude/` | l2-workflow | refactor(skill) / chore(hooks) |
| `^docs/` | l2-docs | doc |
| `^CLAUDE\.md$` | l2-docs | doc |
| `^README\.md$` | l2-docs | doc |
| `^pyproject\.toml$` | l1 / l2-cli | chore |
| `^\.markdownlint-cli2\.yaml$` | l2-ci | chore(ci) |
| `^\.gitignore$` | l2-workflow | chore |

#### 判定規則

- **distinct scope 数 ≥ 2**: multi-scope commit。preuse.py が `permissionDecision=ask` で 3 択 (a) revert / (b) 別 issue / (c) scope 拡大 を user に提示
- **unknown path**: 上記表に hit しない path が staged されている。preuse.py が ask 判定。本表に追記するか、確かに新規 scope なら scope 拡大として user 承認

#### メンテナンス

新規 top-level dir (例: `audit/` 新設) を repo に追加するときは:

1. 本表に対応行を追加 (scope label を決める)
2. preuse.py の `_PATH_SCOPE_MAP` (in-source の正本) も同期更新

doc と source の同期は CI で drift check 可能 (future)。
```

- [ ] **Step 3.2: markdownlint check**

```bash
npx --prefix gui markdownlint-cli2 docs/issue-policy.md 2>&1 | tail -3
```

Expected: 0 error。

- [ ] **Step 3.3: preuse.py に scope check 実装を追加**

preuse.py の構造を確認:

```bash
grep -nE "^def |^_[A-Z_]+ =|^GH_BLOCK|^BULK" .claude/hooks/preuse.py | head -20
```

既存の `_emit_ask()` や `_state_path()` を活用。

`_PATH_SCOPE_MAP` と検出関数を file 末尾近く (main() の前) に追加:

```python
# ---- M7 path↔scope multi-scope detection ------------------------------------
# docs/issue-policy.md §path↔scope 対応表 と同期。新規 top-level dir を追加
# したらここも更新する (drift 検出は future CI check)。

_PATH_SCOPE_MAP: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^allaganeye/"), "l1-cli"),
    (re.compile(r"^tests/"), "l1-cli"),
    (re.compile(r"^gui/src/"), "l2a-gui"),
    (re.compile(r"^gui/src-tauri/"), "l2a-gui"),
    (re.compile(r"^gui/scripts/"), "l2a-gui"),
    (re.compile(r"^scripts/"), "l2b-installer"),
    (re.compile(r"^\.github/workflows/"), "l2-ci"),
    (re.compile(r"^\.github/ISSUE_TEMPLATE/"), "l2-workflow"),
    (re.compile(r"^\.claude/"), "l2-workflow"),
    (re.compile(r"^docs/"), "l2-docs"),
    (re.compile(r"^CLAUDE\.md$"), "l2-docs"),
    (re.compile(r"^README\.md$"), "l2-docs"),
    (re.compile(r"^pyproject\.toml$"), "l1-cli"),
    (re.compile(r"^\.markdownlint-cli2\.yaml$"), "l2-ci"),
    (re.compile(r"^\.gitignore$"), "l2-workflow"),
]

_GIT_COMMIT_RE = re.compile(r"^\s*git\s+commit\b")


def _classify_path(path: str) -> str | None:
    """Return scope label for path, or None if path is not in mapping."""
    for pattern, scope in _PATH_SCOPE_MAP:
        if pattern.match(path):
            return scope
    return None


def _get_staged_paths(repo_root: Path) -> list[str]:
    """Run `git diff --staged --name-only` and return staged file paths."""
    try:
        result = subprocess.run(
            ["git", "diff", "--staged", "--name-only"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return []
        lines = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
        return lines
    except Exception:
        return []


def _check_scope_creep(paths: list[str]) -> tuple[bool, str]:
    """
    Heuristic scope check. Returns (should_ask, reason).
    - distinct scope count >= 2 → ask
    - any unknown path → ask
    - else → allow (no ask)
    """
    if not paths:
        return False, ""
    scopes: set[str] = set()
    unknown: list[str] = []
    for p in paths:
        s = _classify_path(p)
        if s is None:
            unknown.append(p)
        else:
            scopes.add(s)
    if len(scopes) >= 2:
        return True, (
            f"multi-scope commit detected (scopes: {sorted(scopes)}).\n"
            f"staged paths (first 5): {paths[:5]}.\n"
            f"参照: docs/issue-policy.md §path↔scope 対応表"
        )
    if unknown:
        return True, (
            f"unknown scope path(s) detected: {unknown[:5]}.\n"
            f"対応表 (docs/issue-policy.md) 未登録の path。意図的なら scope 拡大として approve、\n"
            f"そうでなければ revert または対応表更新を検討してください。"
        )
    return False, ""
```

(import section に `import subprocess` がなければ追加。`re` / `Path` は既存 import を活用。)

- [ ] **Step 3.4: preuse.py の main flow に scope check を組み込む**

既存の `main()` (or `_decide_for_command`) の冒頭で `git commit` を検出して scope check を呼ぶ:

```python
def _decide_for_command(command: str, *, recent_ops: list[dict], now: float) -> tuple[bool, str]:
    """
    既存の bulk operation gate 等の判定。
    M7 scope check は別途 _check_git_commit_scope() で先に判定し、必要なら ask を return。
    """
    # M7: git commit の場合は staged paths の multi-scope 判定を先に行う
    if _GIT_COMMIT_RE.match(command):
        repo_root = _project_root()
        paths = _get_staged_paths(repo_root)
        should_ask, reason = _check_scope_creep(paths)
        if should_ask:
            return True, f"M7 scope check: {reason}"

    # 以降、既存の bulk gate 判定...
    # (現状のコード継続)
```

(具体的な main flow の構造は preuse.py を Read で確認してから合わせる。`return True, reason` は ask を発火させる規約。)

- [ ] **Step 3.5: hook test を追加**

`tests/hooks/test_preuse_scope_check.py` を新規作成:

```python
"""Tests for M7 path↔scope multi-scope detection in preuse.py."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

# preuse.py を動的に load
PREUSE_PATH = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "preuse.py"
spec = importlib.util.spec_from_file_location("preuse", PREUSE_PATH)
preuse = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(preuse)


def test_classify_path_known_scopes() -> None:
    assert preuse._classify_path("allaganeye/cli.py") == "l1-cli"
    assert preuse._classify_path("gui/src/App.tsx") == "l2a-gui"
    assert preuse._classify_path("gui/src-tauri/src/lib.rs") == "l2a-gui"
    assert preuse._classify_path("scripts/build-portable-zip.ps1") == "l2b-installer"
    assert preuse._classify_path(".github/workflows/ci.yml") == "l2-ci"
    assert preuse._classify_path(".claude/hooks/stop.sh") == "l2-workflow"
    assert preuse._classify_path("docs/refactor-pattern.md") == "l2-docs"
    assert preuse._classify_path("CLAUDE.md") == "l2-docs"


def test_classify_path_unknown() -> None:
    assert preuse._classify_path("unrecognized-dir/file.txt") is None
    assert preuse._classify_path("benchmarks/x.json") is None


def test_check_scope_creep_single_scope_allow() -> None:
    paths = ["allaganeye/cli.py", "allaganeye/detector.py", "tests/test_cli.py"]
    should_ask, _ = preuse._check_scope_creep(paths)
    assert should_ask is False


def test_check_scope_creep_multi_scope_ask() -> None:
    paths = ["allaganeye/cli.py", "gui/src/App.tsx"]
    should_ask, reason = preuse._check_scope_creep(paths)
    assert should_ask is True
    assert "multi-scope" in reason
    assert "l1-cli" in reason
    assert "l2a-gui" in reason


def test_check_scope_creep_unknown_path_ask() -> None:
    paths = ["allaganeye/cli.py", "weird/new/dir.txt"]
    should_ask, reason = preuse._check_scope_creep(paths)
    assert should_ask is True
    assert "unknown" in reason


def test_check_scope_creep_empty_paths() -> None:
    should_ask, _ = preuse._check_scope_creep([])
    assert should_ask is False


def test_git_commit_re_matches() -> None:
    assert preuse._GIT_COMMIT_RE.match("git commit -m 'foo'")
    assert preuse._GIT_COMMIT_RE.match("  git commit")
    assert not preuse._GIT_COMMIT_RE.match("git status")
    assert not preuse._GIT_COMMIT_RE.match("ggit commit")
```

- [ ] **Step 3.6: 既存 test も含めて hook tests を実行**

```bash
pytest tests/hooks/test_preuse_scope_check.py -v 2>&1 | tail -20
```

Expected: 6 tests pass。

- [ ] **Step 3.7: 既存 preuse test と統合実行 (regression check)**

```bash
pytest tests/hooks/ -v --tb=short 2>&1 | tail -30
```

Expected: 既存 test + 新 test all pass。

- [ ] **Step 3.8: 実機 dry-run (任意)**

```bash
# 意図的に multi-scope commit を staging して preuse.py を invoke
git add docs/issue-policy.md .claude/hooks/preuse.py tests/hooks/test_preuse_scope_check.py
# git commit --dry-run は preuse hook を発火しないため、手動で preuse.py に input を投入してテスト
echo '{"tool_name":"Bash","tool_input":{"command":"git commit -m test"}}' | python .claude/hooks/preuse.py 2>&1 | head -20
git reset HEAD docs/issue-policy.md .claude/hooks/preuse.py tests/hooks/test_preuse_scope_check.py  # reset
```

Expected: output JSON に `"permissionDecision": "ask"` と reason に `multi-scope` が出る。

(`docs/issue-policy.md` = l2-docs、`.claude/hooks/preuse.py` = l2-workflow、`tests/hooks/test_preuse_scope_check.py` = l1-cli の 3 scope 跨ぎ。)

- [ ] **Step 3.9: PR α-3 を commit**

```bash
git add docs/issue-policy.md .claude/hooks/preuse.py tests/hooks/test_preuse_scope_check.py
git commit -m "$(cat <<'EOF'
feat(hooks): preuse.py に path↔scope multi-scope detection を追加 (Refs spec L-α M7)

retro spec §M7 の実装。F6 (PR #732 commit 8eff1d2 で bash + gui test 跨ぎ
scope creep) と同型の事象を git commit 前に検出。

docs/issue-policy.md:
- §path↔scope 対応表 を §優先度ラベル の直後に新設
- 各 top-level dir / glob を l1-cli / l2a-gui / l2b-installer / l2-ci /
  l2-workflow / l2-docs の scope label にマップ
- 新規 top-level dir 追加時のメンテ責任を明記

.claude/hooks/preuse.py:
- _PATH_SCOPE_MAP (in-source 正本) を docs の表と同期して定義
- _classify_path / _check_scope_creep を実装
- git commit の Bash command を検出した場合、staged paths の multi-scope
  判定を行い、distinct scope >= 2 or unknown path で permissionDecision=ask
- 単一 scope の commit は素通り (false positive 抑制)

tests/hooks/test_preuse_scope_check.py:
- 6 unit test (classify / multi-scope / unknown / empty / regex)

spec O4 (b) heuristic + AskUserQuestion 確定値に沿う設計。TodoWrite との
直接統合は preuse.py からアクセスできないため、staged paths の multi-scope
detection で代替 (false positive 寄り safety)。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Lane 完了後の最終確認

- [ ] **Step 4.1: branch HEAD が 3 commit (α-1 / α-2 / α-3) を含む**

```bash
git log --oneline -10
```

Expected: 直近 3 commit が L-α、その前に L-γ 3 commit + retro spec / memory / O1-O5 commits。

- [ ] **Step 4.2: 全 markdownlint pass**

```bash
bash scripts/check-markdownlint.sh
```

Expected: 0 error。

- [ ] **Step 4.3: 全 hook test pass**

```bash
pytest tests/hooks/ -v
```

Expected: all green。

- [ ] **Step 4.4: yaml syntax 確認**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml', encoding='utf-8')); print('release.yml OK')"
```

- [ ] **Step 4.5: 次の Lane 移行判断**

L-β / L-δ plan 作成へ進むか、ここまでで PR 化して checkpoint を打つかを user に確認 (AskUserQuestion)。

---

## 受け入れ基準 (L-α 全体)

spec §M1 / §M6 / §M7 の docs / CI / hook 側に閉じる項目をすべて満たす:

- [x] release.yml build-windows が PS 7+ / 5.1 dual matrix で実行される
- [x] artifact upload は pwsh 限定
- [x] stop.sh に orphan commit 検出 step 存在 + .claude/state/orphan-commits.log に追記
- [x] session-start.sh が前セッションの orphan log を Iron Law 前に表示
- [x] docs/issue-policy.md に §path↔scope 対応表 存在
- [x] preuse.py に `_PATH_SCOPE_MAP` + multi-scope detection 実装
- [x] tests/hooks/test_preuse_scope_check.py で 6 test pass
- [x] markdownlint + pytest hooks all green

skill 側の参照リンク (`/scope-guard` skill から path↔scope 対応表への参照) は L-β scope で達成。

## リスクと緩和策

| # | リスク | 緩和 |
| --- | --- | --- |
| RL1 | release.yml matrix で Windows minute が 2x になる | release.yml は paths-filter で gate 済 (毎 PR 走らない)。許容 |
| RL2 | orphan detection の false positive (Claude Opus co-author trailer 持ち正常 commit) | warning のみで block しない。user が rm log で clear する運用、許容 |
| RL3 | preuse.py multi-scope check の false positive (意図的な cross-cutting commit) | ask 判定で user が approve 可能、block ではない |
| RL4 | path↔scope 対応表のメンテ責任 (新規 top-level dir 追加時の同期忘れ) | preuse.py の unknown path 判定で ask が出るため、漏れは検知される (運用で吸収) |
| RL5 | preuse.py の subprocess.run (git diff) で hook が遅延 | timeout=5s 設定、git 不在環境は skip。実用上の遅延 < 100ms |

---

## 次の Lane plan 作成 tasks (L-α 完了後に着手)

L-α で得た学び (multi-scope detection の false positive 制御、hook test pattern) を踏まえ:

- `docs/superpowers/plans/2026-05-17-v030-lane-beta-skill-revision.md` (M3 / M5 / M9 / C2 / C3 / C4 / C6 skeleton)
- `docs/superpowers/plans/2026-05-17-v030-lane-delta-codex-ops.md` (C1 / C5 / C6 完成版)
