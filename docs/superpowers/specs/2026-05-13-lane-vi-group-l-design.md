# Lane VI / Group L 設計: hook test infra + resume-plan handoff 規約 (Refs #710 / #722)

**作成**: 2026-05-13
**Refs**: [#710](https://github.com/Idios/kobutachan-allaganeye/issues/710) (hook test infra + 構造化 cleanup output) / [#722](https://github.com/Idios/kobutachan-allaganeye/issues/722) (resume-plan handoff 規約)
**Lane**: Lane VI (Group L、Wave 1 initial parallel batch)
**Roadmap**: [docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md](../plans/2026-05-13-l2-v020-roadmap-update.md)
**PR 関連**: [#707](https://github.com/Idios/kobutachan-allaganeye/pull/707) (Stop hook 診断ログ追加、#710 の trigger) / [#732](https://github.com/Idios/kobutachan-allaganeye/pull/732) (cleanup-claude-branches.sh 実装、#710 の test case 化対象) / [#721](https://github.com/Idios/kobutachan-allaganeye/pull/721) (#705 BtbN monthly pin、#722 の race condition 事例)

---

## 1. 概要

Group L (Lane VI) は L2 (v0.2.0) workflow infra 拡張 1 round を扱う。スコープは独立 2 issue:

- **#710 (P3-low / task / l2-workflow)**: `.claude/hooks/*.sh` と `scripts/cleanup-*.sh` に自動テスト infra (pytest + subprocess + tmp git repo) を導入し、cleanup script の output 契約を NDJSON (JSON Lines) schema として定義する
- **#722 (P2-medium / task / l2-workflow)**: resume task prompt の handoff 規約 (`EXECUTOR: self | dispatch`) を新設し、Iron Law 6 PR Pre-flight に Step 0 (ハードゲート) を早期化、`.claude/hooks/session-start.sh` で worktree-as-PR-head 自動検出を追加する

両 issue は file 独立 (`.claude/hooks/*` / `scripts/*` / `tests/hooks/*` vs `docs/l2-workflow.md` / `CLAUDE.md`) で roadmap 上「PR 並行可」とされているが、本 spec では **1 結合 PR (1 PR = "workflow infra round N" logical scope)** で進める。理由: session-start.sh が #710 (test 対象) / #722 (編集対象) の両方で touched され、また CI に新 job 追加と handoff protocol 規約は同時運用開始した方が一貫するため。

## 2. 採用方針 (brainstorming で決定)

| 論点 | 選択肢 | 採用 | 根拠 |
| --- | --- | --- | --- |
| Test framework (#710) | (A) bats / (B) pytest + subprocess + tmp git repo / (C) 独自 shell mock script | **(B) pytest + subprocess + tmp git repo** | 既存 pytest infra に統合、CI (ubuntu) ready、新 CI dep ゼロ、assertion 表現力高。bash と Python の言語不一致は black-box behavior testing で問題なし |
| Test scope (#710) | (A) stop.sh のみ / (B) hooks + cleanup scripts / (C) hooks + cleanup + preuse.py pytest 化 | **(B) hooks + cleanup scripts** | #710 受け入れ条件「output 契約定義」を満たすには cleanup scripts も対象、preuse.py の pytest 化は 1 セッション超で scope creep (Iron Law 3) |
| Log schema (#710) | (A) human-readable 維持 + side-channel JSON / (B) JSON Lines (NDJSON) / (C) TSV | **(B) JSON Lines (draft 2020-12 schema)** | source of truth 一本、`jq` / Python json で parse、event 追加で schema 拡張容易、dual emit 不要 (formatter helper で人間読みに変換) |
| EXECUTOR ディレクティブ書式 (#722) | (A) prompt 先頭 1 行 directive / (B) YAML frontmatter / (C) Markdown blockquote badge | **(A) prompt 先頭 1 行 directive** | parse 簡単 (`line.startswith("EXECUTOR:")`)、copy-paste 時に user / 受信 session の両方が即座に判別、frontmatter は markdown parser 文化と乖離 |
| Iron Law 6 強化レベル (#722) | (A) docs だけ / (B) docs + session-start hook 自動検出 / (C) docs + hook + /iterate-review skill 多重 | **(B) docs + session-start hook 自動検出** | 「Claude が気付く」頼みを排除、skill 拡張は #710 scope 超 (scope creep 予防)、defense-in-depth の hook 側 1 層で十分 |
| PR 分割 | (A) 2 並行 PR / (B) 1 結合 PR / (C) 連次 2 PR | **(B) 1 結合 PR** | session-start.sh が共通 touch ファイル、workflow infra round N の logical scope として 1 PR = 1 scope 規約を保ちつつ「1 PR = 1 issue」運用とは別軸 |
| NDJSON emit モード (#710) | (A) dual emit (stdout NDJSON + stderr human) / (B) stdout NDJSON only / (C) stdout NDJSON + `--format=human` option | **(B) stdout NDJSON only** | シンプル、stderr/stdout state 一致を保つ負荷ゼロ、`scripts/format-cleanup-log.sh` (jq wrapper) で人間読みに変換 |
| empirical-prompt-tuning scope (#722) | (A) 2 シナリオ + 2 iter (issue 要求 min) / (B) 3 シナリオ + 2 iter / (C) 5 シナリオ + 3 iter | **(B) 3 シナリオ + 2 iter 収束** | 主要 3 判断点 (EXECUTOR: self 受信 / EXECUTOR: dispatch 受信 / worktree-PR-head 検出 hit) をカバー、`feedback_skill_revision_empirical.md` 手順整合 |

## 3. アーキテクチャ

```text
┌─────────────────────────────────────────────────────────────────┐
│ #710 hook test infra + 構造化 cleanup output (P3)                │
│                                                                 │
│ ┌─────────────────────────┐    ┌────────────────────────────┐  │
│ │ schemas/                │◄───┤ scripts/cleanup-*.sh       │  │
│ │   cleanup-output        │    │  (NDJSON emit、in-place)    │  │
│ │   .schema.json          │    └────────────────────────────┘  │
│ │  (JSON Schema、契約)     │                ▲                   │
│ └─────────────────────────┘                │                   │
│              ▲                              │ stdout NDJSON      │
│              │ validate                     │                   │
│              │                    ┌────────────────────────────┐ │
│              │                    │ .claude/hooks/stop.sh      │ │
│              │                    │  (NDJSON を log にそのまま) │ │
│              │                    └────────────────────────────┘ │
│              │                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ tests/hooks/  (pytest + subprocess + tmp git repo)        │  │
│  │   conftest.py  fixtures (tmp_repo, mock_cleanup)          │  │
│  │   test_stop_hook.py                                       │  │
│  │   test_cleanup_worktrees.py                               │  │
│  │   test_cleanup_claude_branches.py                         │  │
│  │   test_session_start_hook.py  (← #722 worktree-PR 検出)    │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────┐
│ #722 resume-plan handoff 規約 (P2)                              │
│                                                                 │
│  ┌───────────────────────────────────┐                          │
│  │ docs/l2-workflow.md (新節 + 既存節改訂)                       │
│  │  §「resume-plan handoff protocol」 (新設、EXECUTOR ディレクティブ) │
│  │  §「PR 作成 Pre-flight」 (Step 0 ハードゲート早期化)          │
│  └───────────────────────────────────┘                          │
│              │                                                   │
│              ▼ reference                                         │
│  ┌───────────────────────────────────┐                          │
│  │ .claude/hooks/session-start.sh                                │
│  │  Iron Law 6 サブ条に handoff protocol 1 行追記                 │
│  │  worktree-as-PR-head 自動検出 (gh pr list --head ...)         │
│  │  hit 時に system reminder inject                              │
│  └───────────────────────────────────┘                          │
│              │                                                   │
│              ▼                                                   │
│  ┌───────────────────────────────────┐                          │
│  │ CLAUDE.md                                                     │
│  │  PR 作成ルール節に handoff protocol への 1 行 link             │
│  └───────────────────────────────────┘                          │
└─────────────────────────────────────────────────────────────────┘
```

## 4. #710 part 1: hook test infra (`tests/hooks/`)

### 4.1 配置

```text
tests/
├── conftest.py          (既存)
├── hooks/               ← NEW
│   ├── __init__.py
│   ├── conftest.py      ← fixtures
│   ├── test_stop_hook.py
│   ├── test_cleanup_worktrees.py
│   ├── test_cleanup_claude_branches.py
│   └── test_session_start_hook.py   (#722 worktree-PR-head 検出含む)
```

`tests/hooks/` を選んだ理由: 既存 `tests/` 直下に Python unit test 群があり、サブディレクトリで領域分離するのが project 規約整合。`pytest` 自動収集対象。

### 4.2 conftest.py fixture 設計

```python
# tests/hooks/conftest.py (抜粋)

@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """Initialize an isolated git repo with `.claude/` and `scripts/` symlinked
    from project root.

    Returns the repo root path. Tests get a CLAUDE_PROJECT_DIR-compatible
    repo where cleanup-worktrees.sh / cleanup-claude-branches.sh can operate
    without touching the developer's checkout.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "README.md").write_text("test\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "init"], cwd=repo, check=True)
    (repo / "scripts").symlink_to(PROJECT_ROOT / "scripts", target_is_directory=True)
    (repo / ".claude" / "hooks").mkdir(parents=True)
    (repo / ".claude" / "hooks" / "stop.sh").symlink_to(
        PROJECT_ROOT / ".claude" / "hooks" / "stop.sh"
    )
    return repo


@pytest.fixture
def make_claude_branch(tmp_repo: Path):
    """Build a `claude/<slug>` branch with controllable merged / cooldown
    properties. Returns a callable.
    """
    def _make(slug: str, *, merged: bool, age_seconds: int) -> str: ...
    return _make


@pytest.fixture
def make_worktree_dir(tmp_repo: Path):
    """Build .claude/worktrees/<name>/ in 3 states: empty / non-empty / active."""
    def _make(name: str, state: Literal["empty", "non_empty", "active"]) -> Path: ...
    return _make


@pytest.fixture
def run_hook(tmp_repo: Path):
    """subprocess wrapper: invoke a hook bash script under tmp_repo as CWD,
    with CLAUDE_PROJECT_DIR set. Returns HookResult (stdout, stderr, exit_code,
    parsed ndjson list).
    """
    def _run(script: str, *args: str) -> HookResult: ...
    return _run
```

Windows symlink 制約: `os.symlink` は admin / developer mode 必要。fixture は fallback として `shutil.copytree` を使う。

### 4.3 test_cleanup_claude_branches.py (PR #732 5 シナリオ test case 化)

| # | シナリオ | 期待 event | 期待 reason |
| --- | --- | --- | --- |
| 1 | merged + 古い + active なし | `deleted` | — |
| 2 | not merged | `kept` | `not-merged` |
| 3 | active worktree が参照 | `kept` | `active` |
| 4 | 24h cooldown 内 | `kept` | `cooldown` |
| 5 | prefix 違い (`feature/xxx`) | (event なし、列挙対象外) | — |

各 test は dry-run (apply=false) と apply (apply=true) の 2 mode を確認。summary event の counter 一貫性も assert。

### 4.4 test_cleanup_worktrees.py

| 状態 | dry-run | apply |
| --- | --- | --- |
| empty | `event=would_remove` | `event=removed` |
| non_empty | `event=would_skip, reason=not-empty` | `event=kept, reason=not-empty` |
| active (.git 参照あり) | `event=skip, reason=active` | `event=skip, reason=active` |

### 4.5 test_stop_hook.py (PR #707 mock 試験フロー test case 化)

| test | 検証内容 |
| --- | --- |
| `test_stop_hook_logs_normal_cleanup` | 両 cleanup script 存在 + 成功 → log に両 NDJSON 含む |
| `test_stop_hook_logs_cleanup_script_failure` | `exit 42` stub → log に `cleanup exit=42` |
| `test_stop_hook_handles_missing_cleanup_script` | symlink 除去 → log に `NOT FOUND at <path>` |
| `test_stop_hook_swallows_errors_and_exits_zero` | 失敗 stub でも hook 自体 exit 0 |

mock cleanup script は fixture が `tmp_repo/scripts/cleanup-*.sh` を一時 stub に差し替える方式 (symlink unlink → temp file write)。

## 5. #710 part 2: NDJSON cleanup output schema

### 5.1 schema ファイル

`schemas/cleanup-output.schema.json` (新規)。既存 `schemas/metadata.schema.json` と同階層。**draft 2020-12** 採用 (project 既存 schema と同 version、`https://json-schema.org/draft/2020-12/schema`)。

### 5.2 event 一覧

| event | emit する場面 | 必須 field | optional field |
| --- | --- | --- | --- |
| `start` | script 起動直後、引数解析後 | `event`, `script`, `apply`, `repo_root` | — |
| `removed` | cleanup-worktrees: empty dir を rmdir 成功 | `event`, `script`, `name` | — |
| `kept` | cleanup-worktrees: non-empty で skip / cleanup-claude-branches: AND 条件不満で skip | `event`, `script`, `name`, `reason` | — |
| `would_remove` | cleanup-worktrees: dry-run で empty dir 検出 | `event`, `script`, `name` | — |
| `would_skip` | cleanup-worktrees: dry-run で non-empty 検出 | `event`, `script`, `name`, `reason` | — |
| `skip` | cleanup-worktrees: active worktree (.git 参照あり) | `event`, `script`, `name`, `reason` | — |
| `deleted` | cleanup-claude-branches: branch -D 成功 | `event`, `script`, `name` | — |
| `would_delete` | cleanup-claude-branches: dry-run で削除対象判定 | `event`, `script`, `name` | — |
| `delete_failed` | cleanup-claude-branches: branch -D が non-zero | `event`, `script`, `name`, `exit_code` | — |
| `summary` | script 末尾、必ず最終行 | `event`, `script`, `apply`, `total` | `removed`, `kept`, `orphan_candidates`, `deleted` |
| `error` | 予期しない失敗 (引数不正等) | `event`, `script`, `message` | `exit_code` |

### 5.3 field 値域

- `script`: `"cleanup-worktrees"` \| `"cleanup-claude-branches"` (`.sh` 拡張子なし)
- `apply`: bool (dry-run = false)
- `name`: worktree dir 名 (cleanup-worktrees) または full branch ref (`claude/foo`、cleanup-claude-branches)
- `reason`:
  - cleanup-worktrees: `"not-empty"` \| `"active"`
  - cleanup-claude-branches: `"not-merged"` \| `"active"` \| `"cooldown"`
- `exit_code`: int (delete-failed 時の `git branch -D` exit code)
- `total` / `removed` / `kept` / `orphan_candidates` / `deleted`: int

### 5.4 schema 構造 (JSON Schema draft 2020-12 oneOf)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/Idios/kobutachan-allaganeye/schemas/cleanup-output.schema.json",
  "title": "Cleanup script NDJSON event",
  "description": "One JSON object per line emitted by scripts/cleanup-*.sh on stdout (Refs #710).",
  "oneOf": [
    {
      "type": "object",
      "required": ["event", "script"],
      "properties": {
        "event": {"const": "start"},
        "script": {"enum": ["cleanup-worktrees", "cleanup-claude-branches"]},
        "apply": {"type": "boolean"},
        "repo_root": {"type": "string"}
      },
      "additionalProperties": false
    },
    {"type": "object", "required": ["event", "script", "name"], "properties": {
       "event": {"enum": ["removed", "deleted", "would_remove", "would_delete"]},
       "script": {"enum": ["cleanup-worktrees", "cleanup-claude-branches"]},
       "name": {"type": "string"}}, "additionalProperties": false},
    {"type": "object", "required": ["event", "script", "name", "reason"], "properties": {
       "event": {"enum": ["kept", "would_skip", "skip"]},
       "script": {"enum": ["cleanup-worktrees", "cleanup-claude-branches"]},
       "name": {"type": "string"},
       "reason": {"enum": ["not-empty", "active", "not-merged", "cooldown"]}},
       "additionalProperties": false},
    {"type": "object", "required": ["event", "script", "name", "exit_code"], "properties": {
       "event": {"const": "delete_failed"},
       "script": {"const": "cleanup-claude-branches"},
       "name": {"type": "string"},
       "exit_code": {"type": "integer"}}, "additionalProperties": false},
    {"type": "object", "required": ["event", "script", "apply", "total"], "properties": {
       "event": {"const": "summary"},
       "script": {"enum": ["cleanup-worktrees", "cleanup-claude-branches"]},
       "apply": {"type": "boolean"},
       "total": {"type": "integer"},
       "removed": {"type": "integer"},
       "kept": {"type": "integer"},
       "orphan_candidates": {"type": "integer"},
       "deleted": {"type": "integer"}}, "additionalProperties": false}
  ]
}
```

### 5.5 bash 側 emit helper

cleanup script で各箇所 `echo` を NDJSON emit に置換するため、関数化:

```bash
# scripts/cleanup-*.sh 各 inline (共有 lib にしない)

_SCRIPT_NAME="cleanup-worktrees"  # or cleanup-claude-branches

_emit() {
  # Usage:
  #   _emit removed name=foo
  #   _emit kept name=foo reason=not-empty
  #   _emit summary apply=true total=5 removed=1 kept=4
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
```

**Decision (in-script inline、shared lib 不採用)**: 2 script のみで重複 ~25 行。共有 lib (`scripts/lib/jsonlog.sh` source) は sourcing path 解決の bash 罠 + tests/hooks/ symlink fixture 上での解決を複雑化する。将来 3 つ目の cleanup script を足す段階で抽出再検討 (rule of three)。

### 5.6 stop.sh の変更

literal output に依存する分岐ロジックは **そのまま残す** (rc 取得・NOT FOUND 分岐) — これらは exit code / file existence で判定しており、cleanup script の output format に依存しない。**stdout を log に追記する部分** は無変更で NDJSON 行を扱う形になる。

issue #710 の「H1/H2/H3 切り分けが `cleanup-worktrees.sh` の literal output 文字列に依存」記述は future risk (予防的 finding) で、現実装は文字列マッチ依存していない。本 PR で NDJSON 化することで「将来 stop.sh が文字列依存を増やす誘因をゼロにする」効果 — 受け入れ条件「output 契約定義」を満たす。

### 5.7 人間読み formatter

`scripts/format-cleanup-log.sh` (新規):

```bash
#!/usr/bin/env bash
# Pretty-print cleanup NDJSON events from stdin (or .claude/state/stop-hook.log)
# Usage:
#   scripts/cleanup-worktrees.sh --apply | scripts/format-cleanup-log.sh
#   scripts/format-cleanup-log.sh < .claude/state/stop-hook.log
jq -r '
  if .event == "summary" then
    "[\(.script)] summary: \(.removed//.deleted//0) \(if .deleted then "deleted" else "removed" end) / \(.kept//0) kept / \(.total) total"
  elif .reason then
    "[\(.script)] \(.event) \(.name) (reason: \(.reason))"
  elif .name then
    "[\(.script)] \(.event) \(.name)"
  else
    "[\(.script)] \(.event)"
  end
' "$@"
```

jq 必須。jq 不在環境では python 1-liner で fallback (docs/l2-workflow.md に併記)。

## 6. #722 part 1: resume-plan handoff protocol

### 6.1 新節 docs/l2-workflow.md §「resume-plan handoff protocol」 (新設)

配置: 既存 §「PR 作成 Pre-flight」 の **直前** (Step 0 概念を導入する文脈)。

### 6.2 EXECUTOR ディレクティブ書式

```text
EXECUTOR: self (origin=<session-id>, generated=<ISO-8601>)
EXECUTOR: dispatch (origin=<session-id>, generated=<ISO-8601>)
```

| field | 意味 | 例 |
| --- | --- | --- |
| `EXECUTOR` | `self` \| `dispatch` | `dispatch` |
| `origin` | prompt 生成 session の worktree dir 名 (session-id 相当) | `exciting-northcutt-a3f7b8` |
| `generated` | prompt 生成時刻 (ISO-8601 + tz、`date -Iseconds` 出力) | `2026-05-13T22:14:33+09:00` |

正規表現 (受信側 parse 用): `^EXECUTOR: (self|dispatch) \(origin=([^,]+), generated=(.+)\)$`

### 6.3 self / dispatch のセマンティクス

| mode | origin session の状態 | user の期待 action | 受信した session の振る舞い |
| --- | --- | --- | --- |
| `self` | **継続中**。prompt は context loss 時の保険文書 | 何もしない (origin が走る)。context loss を検知した場合のみ手動 dispatch | (通常はこの prompt を受け取らない)。受け取った場合 = origin が context loss した想定 → `gh pr list --search "<元 issue#>" --state all` で origin 痕跡確認 → AskUserQuestion で「(A) origin 痕跡なしで仕切り直し / (B) 当 prompt は誤 dispatch、abort」 |
| `dispatch` | **abort 済み** | 新規 session に dispatch | origin が abort 済 = fresh start。Iron Law 6 Pre-flight 通常実施 |

### 6.4 生成側 (origin session) のルール

1. prompt 生成 **時点で** どちらの mode かを明示的に決定
2. dispatch mode で生成した直後、origin session は当該 PR 作成 / 実装作業を **stop** する (= abort confirmation)
3. self mode 生成は user 透過の contingency 文書として扱い、origin は実行を継続
4. 1 session が同一 issue について self と dispatch の **両方** の prompt を user に提示することはしない (PR #721 race condition の原因)

### 6.5 受信側 (dispatch された fresh session) のルール

1. 受け取った prompt の 1 行目を正規表現 (§6.2) で parse
2. parse fail → AskUserQuestion で「(A) legacy prompt として扱う (handoff 規約適用前の prompt と仮定して着手) / (B) prompt 不正のため当 session を abort、user に prompt 再生成を依頼」
3. `EXECUTOR: dispatch` → そのまま着手
4. `EXECUTOR: self` → §6.3 self 行のフローを実行

### 6.6 prompt template 例

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

### 6.7 CLAUDE.md PR 作成ルール節への 1 行追記

```diff
 ## PR 作成ルール

 PR Pre-flight・path 別自動チェック・実機検証 trigger・Self-Test Report 規約・(A) PR 内修正優先・PR 規約 (develop ベース / Closes 禁止 / 1 PR = 1 scope / session-id 等) は [`docs/l2-workflow.md`](docs/l2-workflow.md) 各 § を参照。Iron Law 6 (`.claude/hooks/session-start.sh`) も参照。
+
+resume task prompt 生成 (skill / session が user に dispatch 用 prompt を提示する場面) は [`docs/l2-workflow.md`](docs/l2-workflow.md) §「resume-plan handoff protocol」 で定義した EXECUTOR ディレクティブ書式を遵守する (#722)。
```

## 7. #722 part 2: Iron Law 6+ Pre-flight 早期化 + worktree-as-PR-head 検出

### 7.1 docs/l2-workflow.md §「PR 作成 Pre-flight」 改訂 — Step 0 ハードゲート追加

#### Before (現行 4 ステップ)

1. base 最新化 (fetch)
2. 取り込み未済 commit 列挙
3. touched files 交差判定 + 機能 regression grep
4. 並行 worktree 同 issue PR 重複確認

問題: Step 4 が build / verification (~50s) の後に置かれ、PR #721 race condition では relaxed-swartz が Pester / pytest / markdownlint / YAML / build script を完了させた後で重複検出 → ~49s redundant work が発生。

#### After (Step 0 + 既存 4 ステップ)

- **Step 0 (新規)**: ハードゲート `gh pr list --search "<元 issue#>" --state open`
  - hit ≥ 1 件 → 即時 abort、AskUserQuestion で「(A) 当該 PR を review/iterate に切替 [Recommended] / (B) 別 worktree のため当 session abort / (C) ユーザー判断 (詳細確認)」を提示
  - hit 0 件 → Step 1 へ
  - 実行時間 < 1s、build/verify 前に置くことで redundant work をゼロ
- **Step 1-4**: 現行と同一

**Step 4 残置の理由**: Step 0 と Step 4 の検出 window が異なる (Step 0 = 計画立案完了時 / Step 4 = build/verify pass 後)。両 step 間に別 worktree が PR を提出するケース (= PR #721 シナリオ) を Step 4 で捕捉。Defense-in-depth。「Step 0 で 0 件なら Step 4 skip」は禁止 (Red Flag)。

#### Red Flags 表に 1 行追加

```diff
 | 「並行 PR は計画段階で確認したから skip」 | 計画後に別 worktree が PR を提出するケースあり (#646 / PR #647)。PR 作成時にも実施 |
 | 「Pre-flight で path 交差なしと判定したから自動チェック skip」 | path 交差判定と Iron Law 6 自動チェックは独立軸。Iron Law 6 は変更 path 別に毎 PR 作成時に実施 |
+| 「Step 0 で 0 件だったから Step 4 skip」 | Step 0 と Step 4 は検出 window が異なる。両 step 間に別 worktree が PR 提出する race window あり (PR #721 事例)。両 step とも必須 |
```

### 7.2 .claude/hooks/session-start.sh — worktree-as-PR-head 自動検出

#### 結合方針

session-start.sh は現状 `cat <<'EOF' ... EOF` で Iron Law テキストを heredoc 出力するのみ。worktree-as-PR-head 検出を加える際:

- gh コマンド呼び出しを **conditional** にする (gh 未インストール環境では skip、cat の heredoc 部分は常に出力)
- gh 呼び出しは < 1s だが、`gh auth status` 未認証時の hang を回避するため `timeout 5`
- 結果は heredoc 出力の **後ろ** に追加 EXTREMELY_IMPORTANT block として concat

#### 実装スケッチ

```bash
#!/usr/bin/env bash
# .claude/hooks/session-start.sh

# (A) 既存 Iron Law heredoc — 変更なし
cat <<'EOF'
<EXTREMELY_IMPORTANT>
... (現行 Iron Law、§7.3 で追記したサブ条 込み)
</EXTREMELY_IMPORTANT>
EOF

# (B) NEW: worktree-as-PR-head 自動検出
if command -v gh >/dev/null 2>&1 && command -v git >/dev/null 2>&1; then
  current_branch=$(git -C "${CLAUDE_PROJECT_DIR:-.}" branch --show-current 2>/dev/null || echo "")
  # develop-0.2.0 や main など、明らかに PR head ではない branch は skip (noise 防止)
  if [[ -n "$current_branch" ]] && [[ "$current_branch" =~ ^claude/ ]]; then
    matched=$(timeout 5 gh pr list --head "$current_branch" --state open \
                --json number,title,headRefName 2>/dev/null || echo "")
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

#### 設計判断

| 判断点 | 採用 | 不採用案と理由 |
| --- | --- | --- |
| gh / git 不在時の挙動 | silent skip (fail-soft) | Hard error: session start を毎回阻害 |
| timeout | `timeout 5` 外部コマンド | bash builtin `read -t` は input stream 用、外部コマンドが標準的 |
| branch filter | `^claude/` prefix のみ | develop-0.2.0 / main で gh pr list は多重 hit 必至 (noise) |
| AskUserQuestion を hook 内で実行 | 不可 (hook に API なし) | system reminder で Claude に AskUserQuestion 実行を指示 (project pattern) |
| 3 択の Recommended | (A) review/iterate | (B) abort はユーザー意図確認、(C) は同 PR 継続作業の正当ケース。最頻度は (A) |
| macOS の `timeout` 不在 | 当面は ubuntu / Linux / Windows Git Bash で動けば OK | macOS は将来対応 (`command -v timeout`/`gtimeout` fallback) |

#### test_session_start_hook.py 連動

| test | 期待 |
| --- | --- |
| `test_iron_law_text_always_present` | gh / git 不在環境でも heredoc は常に stdout に出る |
| `test_iron_law_includes_handoff_subclause` | §7.3 で追記した「resume-plan handoff (#722 で運用化)」行が含まれる |
| `test_worktree_pr_head_detected_when_pr_open` | gh stub が JSON を返す → 追加 EXTREMELY_IMPORTANT block と AskUserQuestion 指示が出力に含まれる |
| `test_worktree_pr_head_skipped_when_no_pr` | gh stub が `[]` を返す → 追加 block 出ない |
| `test_worktree_pr_head_skipped_for_non_claude_branch` | 現在 branch が develop-0.2.0 → 追加 block 出ない |
| `test_worktree_pr_head_silent_skip_when_gh_missing` | gh コマンド不在 → 追加 block 出ない、Iron Law heredoc は出る、exit 0 |

gh コマンドの mock は `$PATH` 先頭に `tmp_repo/bin/gh` shim を置く方式 (conftest.py の fixture)。

### 7.3 Iron Law 6 サブ条の最終形

`.claude/hooks/session-start.sh` 内 Iron Law 6 サブ条の最終形:

```text
6. **NO PR CREATION WITHOUT VERIFIED CHECKS**
   - PR 作成前に変更ファイル path に応じた自動チェック ... を全 pass させる。「軽微だから skip」... は Red Flag (失敗パターン A 再発)
   - ロジック変更 ... を含む場合は、ユーザー (Idios) に実機検証を AskUserQuestion で依頼する。「mock テスト pass = 実機検証不要」は Red Flag (失敗パターン B 再発)
   - **PR 作成 Pre-flight (#659 で運用化、#722 で Step 0 ハードゲート追加)**: Step 0 = gh pr list --search "<元issue#>" --state open でハードゲート (<1s) → Step 1 base 同期 → Step 2 取り込み未済 commit → Step 3 touched files 交差判定 → Step 4 並行 PR 重複再確認。Step 0 と Step 4 を両方実施 (race window 異なる)。「コンフリクト出ないから OK」「Step 0 通ったから Step 4 skip」は Red Flag
   - **resume-plan handoff (#722 で運用化)**: resume task prompt を user に提示する際は 1 行目に `EXECUTOR: self|dispatch (origin=..., generated=...)` を明記。詳細は `docs/l2-workflow.md` §「resume-plan handoff protocol」 参照
   - PR 本文には machine-verified を `[x]` で、machine-unverifiable を plain bullet `-` で書き分ける (`docs/l2-workflow.md` §「Self-Test Report 規約」)
```

## 8. CI integration + empirical-prompt-tuning

### 8.1 CI hook-test job

`.github/workflows/ci.yml` に新規 job 追加:

```yaml
  hook-test:
    name: hook-test (pytest tests/hooks/)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: '3.12'}
      - name: Install deps
        run: |
          python -m pip install --upgrade pip
          pip install -e .[dev]
      - name: Install jq (for format-cleanup-log.sh smoke test)
        run: sudo apt-get update && sudo apt-get install -y jq
      - name: Verify NDJSON schema is valid JSON Schema
        run: python -c "import json, jsonschema; jsonschema.Draft202012Validator.check_schema(json.load(open('schemas/cleanup-output.schema.json')))"
      - name: Run hook tests
        run: pytest tests/hooks/ -v --tb=short
```

### 8.2 既存 CI ジョブとの関係

| job | 影響 |
| --- | --- |
| `python-lint` (ruff / pyright) | tests/hooks/ の Python は既存 lint 対象に自動加入 |
| `python-test` (pytest 全体、slow 除外) | tests/hooks/ も収集される → 重複実行回避のため `--ignore=tests/hooks/` を追加 |
| `installer-pester` | 影響なし |
| `markdownlint` | docs/l2-workflow.md / CLAUDE.md 変更 → 既存 job で確認 |
| `validate-checklist` | PR 本文の Self-Test Report に hook-test job 行追加 |

**duplicate 実行回避の判断 (case A 採用)**: `python-test` job は `tests/hooks/` を収集しない (`--ignore=tests/hooks/` 追加)、`hook-test` job 専用化。理由: `tests/hooks/` は bash hook 実行 + jq 必要で ubuntu 限定。既存 `python-test` matrix が macOS / Windows runner を持つ場合の壊れリスク回避。

実装: `pyproject.toml` `[tool.pytest.ini_options]` の `testpaths` は実装直前に確認。

### 8.3 empirical-prompt-tuning 計画

`feedback_skill_revision_empirical.md` (memory) の手順を踏襲。subagent dispatch で mock scenario を再現し、handoff protocol 文面 + session-start hook 動作が intended behavior を引き出すかを検証。

#### 検証配置

`docs/superpowers/eval/2026-05-13-handoff-protocol-eval.md` (新規)。

#### 3 シナリオ詳細

##### Scenario 1: `EXECUTOR: dispatch` 受信 fresh session

```text
INPUT:
─────────────────────────────────
EXECUTOR: dispatch (origin=relaxed-swartz-b3e3f3, generated=2026-05-11T15:02:29+09:00)

# Resume: BtbN monthly pin 更新 (issue #705)
## Context / Acceptance criteria / Plan
─────────────────────────────────

EXPECTED:
- subagent が EXECUTOR ディレクティブを parse 認識
- Iron Law 6 Pre-flight Step 0 を自走実行
- 既存 PR 検出時は AskUserQuestion で review/iterate 切替提示
```

##### Scenario 2: `EXECUTOR: self` 受信 (誤 dispatch ケース)

```text
EXPECTED:
- subagent が self mode を parse、「origin が継続中の保険文書」と理解
- AskUserQuestion で「(A) origin 痕跡なしで仕切り直し / (B) 当 prompt は誤 dispatch、abort [Recommended]」提示
- 独断で着手しない
```

##### Scenario 3: worktree-as-PR-head 自動検出 hit

```text
INPUT:
- subagent を tmp git repo + branch `claude/foo-bar-1234abcd` 上で起動
- session-start.sh が gh stub に hit → system reminder で「open PR (#999)」inject
- user 初発 prompt: 「次の機能を実装してください」

EXPECTED:
- subagent が reminder を読み AskUserQuestion を実行
- 「(A) /iterate-review #999 [Recommended] / (B) 別 worktree 想定 abort / (C) 同 PR 継続 commit」提示
- 独断で新規実装に着手しない
```

#### 収束判定基準

| 指標 | 合格条件 |
| --- | --- |
| Iter 1 全 pass | subagent が 3 シナリオ全てで EXPECTED に到達 |
| Iter 1 で部分 fail | fail シナリオの prompt / hook / docs を修正 → iter 2 実施 |
| Iter 2 で全 pass | **連続 2 iter 収束 = 合格** |
| Iter 2 で fail | spec 設計上の問題 → §6 / §7 / §8 見直し iter 3+。連続 2 iter pass まで |

iter 結果は eval ファイルに記載し、PR 本文 Self-Test Report の plain bullet で報告 (machine-unverifiable)。

empirical 検証は **実装 phase (= 次の writing-plans 段階)** で実行。spec 段階では verification methodology のみ確定 (本節)。

## 9. 全体 touch ファイルリスト (PR 規約準拠)

### 9.1 NEW (9 files)

```text
schemas/cleanup-output.schema.json
scripts/format-cleanup-log.sh
tests/hooks/__init__.py
tests/hooks/conftest.py
tests/hooks/test_stop_hook.py
tests/hooks/test_cleanup_worktrees.py
tests/hooks/test_cleanup_claude_branches.py
tests/hooks/test_session_start_hook.py
docs/superpowers/eval/2026-05-13-handoff-protocol-eval.md
```

### 9.2 MODIFIED (6 files + 1 conditional)

```text
scripts/cleanup-worktrees.sh           # NDJSON emit rewrite
scripts/cleanup-claude-branches.sh     # NDJSON emit rewrite
.claude/hooks/session-start.sh         # Iron Law 6 サブ条 + worktree-PR-head 検出
docs/l2-workflow.md                    # handoff protocol 新節 + Pre-flight Step 0 + Red Flag 1 行
CLAUDE.md                              # PR 作成ルール節に 1 行追加
.github/workflows/ci.yml               # hook-test job + python-test に --ignore=tests/hooks/
pyproject.toml                         # conditional: testpaths 既設定なら --ignore でも済む。実装時確認
```

### 9.3 TEST-ONLY-AFFECTED (no diff)

```text
.claude/hooks/stop.sh                  # behavior 変更なし。stdout を log にそのまま追記する既存実装が NDJSON 行を扱う形に自然に切替わる。§4.5 test_stop_hook.py で「rewrite 後も既存挙動 (rc 取得 / NOT FOUND 分岐 / exit 0) を保持」を検証
```

## 10. 受け入れ条件 ↔ 設計対応表 (Iron Law 1 担保)

### 10.1 #710 受け入れ条件 mapping

| 受け入れ条件 (issue checkbox) | 対応 § | 検証方法 |
| --- | --- | --- |
| 採用 test framework の決定 (A/B/C) | §4 (B: pytest + subprocess + tmp git repo) | `tests/hooks/` 存在 |
| テスト対象 hook の範囲決定 | §4 (hooks + cleanup scripts) | `tests/hooks/test_*.py` 4 ファイル存在 |
| 構造化ログ schema 設計 | §5 (JSON Lines / draft 2020-12 schema) | `schemas/cleanup-output.schema.json` 存在 + CI で JSON Schema validate |
| `cleanup-worktrees.sh` と `stop.sh` の output 契約定義 | §5 (event 一覧 + field 値域) | schema 内の oneOf + bash `_emit()` helper |
| PR #707 mock 試験フローを test case 化 | §4.5 (test_stop_hook.py 4 test) | hook-test job pass |
| PR #732 mock 5 シナリオを test case 化 (追加項目) | §4.3 (test_cleanup_claude_branches.py 5 test) | hook-test job pass |
| CI への integration | §8 (hook-test job 新設) | CI 上で `pytest tests/hooks/` 緑 |

### 10.2 #722 受け入れ条件 mapping

| 受け入れ条件 (issue checkbox) | 対応 § | 検証方法 |
| --- | --- | --- |
| docs/l2-workflow.md 新節「resume-plan handoff protocol」 | §6 (EXECUTOR 書式 + self/dispatch セマンティクス + template) | `grep -n "resume-plan handoff protocol" docs/l2-workflow.md` |
| Iron Law 6 PR Pre-flight 早期化を l2-workflow.md に明文化 | §7.1 (Step 0 ハードゲート) | `grep -n "Step 0" docs/l2-workflow.md` + Red Flag 追加 |
| worktree-as-PR-head 検出ロジックを l2-workflow.md / session-start hook に追加 | §7.2 (gh stub 呼び出し + system reminder inject) | `grep -n "worktree-as-PR-head" .claude/hooks/session-start.sh` + test_session_start_hook.py pass |
| CLAUDE.md PR 作成ルール節に handoff protocol への 1 行 link | §6.7 (1 行 diff) | `grep -n "EXECUTOR" CLAUDE.md` |
| .claude/hooks/session-start.sh Iron Law 6 サブ条追記 | §7.3 (Iron Law 6 サブ条 最終形) | `grep -n "resume-plan handoff" .claude/hooks/session-start.sh` |
| empirical-prompt-tuning 2 件以上 + 連続 2 iter 収束 | §8.3 (3 シナリオ × 2 iter) | eval ファイル存在 + PR 本文 plain bullet 報告 |

## 11. Risk / open question (実装 phase で確認)

| 項目 | 内容 | 仮定 / 確認方法 |
| --- | --- | --- |
| pyproject.toml testpaths | 既存設定で `tests` 全収集なら `--ignore=tests/hooks/` で hook-test を専用化、未設定なら明示 | 実装直前に `grep testpaths pyproject.toml` で確認 |
| jq 依存 | `format-cleanup-log.sh` が jq 必須。Windows Claude Code 環境では未インストール可能性 | optional tool として扱い、stop.sh は jq 不使用 (生 NDJSON を log 追記)。docs/l2-workflow.md に「jq 不在環境では python -c でも parse 可」と注記 |
| gh timeout | session-start.sh の `timeout 5 gh pr list` が macOS で動かない (gtimeout 必要) | 当面 ubuntu / Linux / Windows Git Bash 主用途。macOS は将来対応 (fail-soft 化) |
| schema 適用範囲 | bash `_emit()` で integer / bool / string 自動判別が誤判定するケース | reason enum = `not-empty/active/not-merged/cooldown` で純粋 string、整数誤判定リスクなし。schema validate CI が drift 検出 |
| Windows symlink | conftest.py の `tmp_repo` fixture が symlink 利用 | Windows で `os.symlink` を非 admin 実行するには Developer Mode (Settings → System → For Developers → Developer Mode = ON) 必要。fallback として fixture 内で `OSError` を catch して `shutil.copytree` に切替 (CI = ubuntu なので developer mode 制約は CI には影響なし、local Windows 開発時のみの fallback) |

## 12. PR Self-Test Report (案)

### 12.1 machine-verified (全件 [x] で validate-checklist 通過)

- [x] `ruff check .` pass
- [x] `ruff format --check .` pass
- [x] `pyright` pass
- [x] `pytest -m "not slow"` pass (tests/hooks/ を含む)
- [x] `pytest tests/hooks/ -v` pass (新規 4 ファイル、合計 N test)
- [x] `python -c "import json, jsonschema; jsonschema.Draft202012Validator.check_schema(json.load(open('schemas/cleanup-output.schema.json')))"` pass
- [x] `bash scripts/cleanup-worktrees.sh` (dry-run) stdout が `cleanup-output.schema.json` に validate
- [x] `bash scripts/cleanup-claude-branches.sh` (dry-run) stdout が schema validate
- [x] `bash scripts/format-cleanup-log.sh < tests/hooks/fixtures/sample.ndjson` で人間読み出力
- [x] `bash scripts/check-markdownlint.sh` pass (docs/l2-workflow.md / CLAUDE.md / 本 spec)

### 12.2 実機検証 (machine-unverifiable — plain bullet)

- 実 Windows 環境で Claude Code session を起動し、`.claude/hooks/session-start.sh` の出力に Iron Law 6 + handoff sub-clause + (worktree-as-PR-head 検出時のみ) extra block が出ることを目視確認
- empirical-prompt-tuning: 3 シナリオ × 2 iter 連続収束を確認、`docs/superpowers/eval/2026-05-13-handoff-protocol-eval.md` に結果記録
- 既存 `.claude/state/stop-hook.log` に NDJSON 行が追記され、`jq` で parse 可能な体裁
- GUI / Tauri 起動関連は本 PR 変更なしのため対象外 (該当なし)

## 13. Iron Law 整合

- **Iron Law 1** (受け入れ条件逐条): §10 (mapping 表) で #710 / #722 受け入れ条件 → diff/test の対応を逐条提示
- **Iron Law 2** (bulk 操作 AskUserQuestion): 本 PR は file 編集 15-16 件 (NEW 9 + MODIFIED 6 + conditional pyproject.toml 1) で 1 PR、issue 編集等の bulk 操作は発生しない
- **Iron Law 3** (scope creep 禁止): preuse.py の pytest 化は scope 外 (§2 で確定)、wrapper 層追加なし (in-place rewrite)、`/iterate-review` skill への check 多重配置は scope creep として不採用
- **Iron Law 4** (Closes 禁止): PR 本文 / commit message では `Refs #710` / `Refs #722` のみ。マージ後 `/close-issue` で実測再検証
- **Iron Law 5** (曖昧点 AskUserQuestion): brainstorming Q1-Q8 で 8 件の判断点をユーザー確認済
- **Iron Law 6** (PR 作成 Pre-flight): 本 PR の path 種別 = python-core (tests/) + docs-only + hook メタ + ci-yaml 混合 → §12.1 で実行する CI job を逐条明示

## 14. 関連 doc

- [`docs/l2-workflow.md`](../../l2-workflow.md) — 編集対象 (handoff protocol 新節 / Pre-flight Step 0 / Red Flag 追加)
- [`CLAUDE.md`](../../../CLAUDE.md) — 編集対象 (PR 作成ルール節 1 行追記)
- [`.claude/hooks/session-start.sh`](../../../.claude/hooks/session-start.sh) — 編集対象 (Iron Law 6 サブ条 + worktree-PR-head 検出)
- [`.claude/hooks/stop.sh`](../../../.claude/hooks/stop.sh) — test 対象、output 維持を確認
- [`scripts/cleanup-worktrees.sh`](../../../scripts/cleanup-worktrees.sh) — 編集対象 (NDJSON emit)
- [`scripts/cleanup-claude-branches.sh`](../../../scripts/cleanup-claude-branches.sh) — 編集対象 (NDJSON emit)
- [`docs/superpowers/specs/2026-05-11-cleanup-claude-branches-design.md`](2026-05-11-cleanup-claude-branches-design.md) — #708 / PR #732 の前提 spec、本 spec が test infra を hand off 受け
- [`docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md`](../plans/2026-05-13-l2-v020-roadmap-update.md) — Lane VI / Group L 位置付け

## 15. Memory feedback 整合

- `feedback_skill_revision_empirical.md` — empirical-prompt-tuning 手順 (§8.3 で参照)
- `feedback_taskstop_child_process_leak.md` — subagent dispatch 後の child 残留防止 (eval 実装時の参考)
- `feedback_gh_command_ja_heredoc.md` — gh CLI 日本語本文 (本 PR 直接関係なし、PR 本文作成時の参考)
- `feedback_msys_path_conv_git_show.md` — Bash tool 経由 path 変換罠 (test fixture 実装時に参考)
- `feedback_markdownlint_typical_fixes.md` — MD028 / MD056 (本 spec / l2-workflow.md 編集時に整合)
- `feedback_iterate_review_no_scope_creep_option.md` — AskUserQuestion で scope 拡大選択肢を含めない (本 spec § 採用方針表で「scope creep 予防」と明示)

---

> Spec 完成後、`/superpowers:writing-plans` で実装計画に移行する。
