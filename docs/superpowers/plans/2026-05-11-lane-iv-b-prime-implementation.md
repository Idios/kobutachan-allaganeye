# L2 Lane IV-b' (Group J + Group G remainder 調整) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lane IV-b' polish lane の実装 — (1) error.rs ↔ docs/tauri-commands.md の AppError hint mapping drift を CI で防ぐ (#692) / (2) `.markdownlint-cli2.yaml` で nested `gui/node_modules/` を ignore する (#700) / (3) roadmap doc を 2 件 / 2 章構造に縮小 (#458 scope-out 反映)。2 並行 PR (PR-1 = #692 + adjacency / PR-2 = #700)。

**Architecture:** PR-1 は `.github/scripts/` に bash + awk 3 file (main script + 2 awk parser) を新規追加し、ci.yml に `doc-error-hint-drift` + `shellcheck` の 2 job を追加。並行で本 spec doc 同梱 + roadmap doc/design doc を §5.1 表通り 4 ヶ所修正。PR-2 は `.markdownlint-cli2.yaml` の `ignores` に `**/node_modules/**` を 1 行追加。

**Tech Stack:** bash + GNU awk / GitHub Actions / shellcheck / markdownlint-cli2 / gh CLI

**Spec:** [docs/superpowers/specs/2026-05-11-lane-iv-b-prime-design.md](../specs/2026-05-11-lane-iv-b-prime-design.md)

---

## File Structure

| Path | 種類 | 責務 | 担当 task |
| --- | --- | --- | --- |
| `.github/scripts/extract-rust-hints.awk` | 新規 | error.rs の `default_hint_for_code` match arm から (code, hint) pair を抽出。or-pattern → 各 code に展開、None entry → `<<NONE>>` sentinel | Task 1 |
| `.github/scripts/extract-doc-hints.awk` | 新規 | tauri-commands.md の §「AppError default hint mapping」 table から (code, hint) pair を抽出。code cell の or-pattern (`/` 区切り) → 各 code に展開、`(hint なし: ...)` → `<<NONE>>` sentinel | Task 2 |
| `.github/scripts/check-error-hint-drift.sh` | 新規 | 上 2 parser を呼び sort + diff -u で照合、drift → exit 1 | Task 3 |
| `tests/fixtures/error-hints/sample-error.rs` | 新規 | Task 1-3 用 fixture (or-pattern + None + 通常 hint 計 6 arm) | Task 1 |
| `tests/fixtures/error-hints/sample-tauri-commands.md` | 新規 | Task 2-3 用 fixture (or-pattern / 区切り + None + 通常 hint) | Task 2 |
| `tests/fixtures/error-hints/expected.tsv` | 新規 | 期待出力 (code\thint normalized、sort 済) | Task 1 |
| `tests/scripts/test_error_hint_drift.sh` | 新規 | bash test harness (fixture vs expected) | Task 1-3 |
| `.github/workflows/ci.yml` | 修正 | `doc-error-hint-drift` job + `shellcheck` job 追加 | Task 6, 7 |
| `docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md` | 修正 | Lane IV-b' 4 ヶ所 + deferred 表追記 (§5.1) | Task 8 |
| `docs/superpowers/specs/2026-05-11-l2-v020-roadmap-update-design.md` | 修正 | Lane IV-b' 4 ヶ所 (§5.1 相当) | Task 9 |
| `.markdownlint-cli2.yaml` | 修正 | `ignores` に `**/node_modules/**` 1 行追加 | Task 11 |

---

## Task 0: Pre-flight & shellcheck pass 状況確認

**Goal:** 着手前の状態確認。shellcheck pass 状況を §7.4.2 (spec) の 3 分岐 (pass / 軽微 1-3 件 / 多数) で確定する。

**Files:**

- Check: `scripts/check-markdownlint.sh`, `scripts/cleanup-worktrees.sh`

- [ ] **Step 1: 着手 worktree の git fetch + 取り込み未済 commit 確認 (Iron Law 6)**

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline | head -20
```

Expected: 出力なし (= 取り込み未済 commit なし) or 数件 (取り込み未済あれば次 step で merge)。

- [ ] **Step 2: 取り込み未済 commit ある場合 → merge**

```bash
# Step 1 で commit が出ていた場合のみ
git merge origin/develop-0.2.0
# conflict なければそのまま進む。conflict あれば手動解決。
```

Expected: clean merge or no-op。

- [ ] **Step 3: 並行 worktree PR 重複確認 (Iron Law 6)**

```bash
gh pr list --state open --search "#692 OR #700 OR Lane IV-b" --json number,title,headRefName 2>&1
```

Expected: 該当なし (本 lane で初の PR、Wave 0 で merge 済の #688 など close 状態の PR は --state open フィルタで除外される)。万一 open で既存 PR あれば user に判断仰ぐ。

- [ ] **Step 4: shellcheck がローカルで利用可能か確認**

```bash
which shellcheck 2>&1 || echo "NOT_INSTALLED"
```

Expected: `/usr/bin/shellcheck` 等の path、または `NOT_INSTALLED`。

- [ ] **Step 5: 未インストールなら install 案内**

```bash
# Windows local の場合
# winget install --id koalaman.shellcheck
# または scoop install shellcheck
# または GitHub Releases から static binary を取得
# Linux/macOS: apt install shellcheck / brew install shellcheck
```

Expected: shellcheck v0.9+ が which で見えるようになる。

- [ ] **Step 6: 既存 .sh script の shellcheck 実行**

```bash
shellcheck -S warning scripts/check-markdownlint.sh scripts/cleanup-worktrees.sh 2>&1 | tee /tmp/shellcheck-baseline.log
```

Expected: 出力を `/tmp/shellcheck-baseline.log` に記録。issue 件数を確認 (0 / 1-3 / 多数 で次の分岐判定)。

- [ ] **Step 7: 分岐判定**

| 件数 | 対応 |
| --- | --- |
| 0 (pass) | Task 7 で shellcheck job を素直に追加。既存 script 修正不要 |
| 1-3 (軽微) | Task 7 で shellcheck job 追加 + 既存 script を最小修正 (pragma 追加 or quote 修正)。修正点を PR-1 本文 §「scope creep 透明化」節に記述 |
| 4+ (多数 / structural) | **AskUserQuestion を発動** — 「(a) 本 PR で全件修正、(b) shellcheck job 追加を保留して別 issue 起票、(c) shellcheck warning level → error level を `\|\|true` で許容に変更」の 3 択を user に問う |

判定結果を memo (本 plan 末尾の「Pre-flight log」節に追記)、Task 7 の動作分岐で参照。

---

## Task 1: extract-rust-hints.awk TDD

**Goal:** error.rs の `default_hint_for_code` match arm から `(code, hint_normalized)` pair を抽出する awk script を TDD で作成。or-pattern (`"a" | "b" =>`) を 2 code に展開、None entry を `<<NONE>>` sentinel に変換。

**Files:**

- Create: `.github/scripts/extract-rust-hints.awk`
- Create: `tests/fixtures/error-hints/sample-error.rs`
- Create: `tests/fixtures/error-hints/expected-rust.tsv`
- Create: `tests/scripts/test_extract_rust_hints.sh`

- [ ] **Step 1: fixture sample-error.rs を作成**

`tests/fixtures/error-hints/sample-error.rs`:

```rust
// Minimal fixture for extract-rust-hints.awk TDD.
// Includes: single-line hint, multi-line hint, or-pattern, None entry, catch-all.

fn default_hint_for_code(code: &str) -> Option<&'static str> {
    match code {
        "state.mtime_conflict" => Some(
            "metadata.json が他のプロセスで書き換えられました。「リロード」で最新を読み直すか、「上書き」で現在の編集を強制適用してください"
        ),
        "io.file_not_found" => Some(
            "ファイルが見つかりません。パスを確認してください"
        ),
        "io.would_block" | "io.timed_out" => Some(
            "I/O 処理がタイムアウト / ブロックされました。少し時間をおいて再試行してください"
        ),
        "subprocess.cancelled" => None,
        "internal.error" => None,
        _ => None,
    }
}
```

- [ ] **Step 2: 期待出力 expected-rust.tsv を作成 (sort 済)**

`tests/fixtures/error-hints/expected-rust.tsv` (各行は `<code>\t<hint>` 形式で間の `\t` は TAB 文字 1 個。下記 code block は MD010 を一時的に許容):

<!-- markdownlint-disable MD010 -->
```text
internal.error	<<NONE>>
io.file_not_found	ファイルが見つかりません。パスを確認してください
io.timed_out	I/O 処理がタイムアウト / ブロックされました。少し時間をおいて再試行してください
io.would_block	I/O 処理がタイムアウト / ブロックされました。少し時間をおいて再試行してください
state.mtime_conflict	metadata.json が他のプロセスで書き換えられました。「リロード」で最新を読み直すか、「上書き」で現在の編集を強制適用してください
subprocess.cancelled	<<NONE>>
```
<!-- markdownlint-enable MD010 -->

Note: catch-all `_` arm は emit しない (codes に `_` literal 含まれないため、後述 awk 実装で除外)。

- [ ] **Step 3: test harness test_extract_rust_hints.sh を作成**

`tests/scripts/test_extract_rust_hints.sh`:

```bash
#!/usr/bin/env bash
# TDD harness for .github/scripts/extract-rust-hints.awk
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AWK_FILE="$SCRIPT_DIR/.github/scripts/extract-rust-hints.awk"
FIXTURE="$SCRIPT_DIR/tests/fixtures/error-hints/sample-error.rs"
EXPECTED="$SCRIPT_DIR/tests/fixtures/error-hints/expected-rust.tsv"

if [[ ! -f "$AWK_FILE" ]]; then
  echo "FAIL: awk script not found: $AWK_FILE" >&2
  exit 1
fi

actual=$(awk -f "$AWK_FILE" "$FIXTURE" | sort)
expected=$(sort "$EXPECTED")

if [[ "$actual" == "$expected" ]]; then
  echo "PASS: extract-rust-hints.awk matches expected"
  exit 0
else
  echo "FAIL: drift detected"
  diff -u <(echo "$expected") <(echo "$actual")
  exit 1
fi
```

```bash
chmod +x tests/scripts/test_extract_rust_hints.sh
```

- [ ] **Step 4: red 確認 (awk script なし)**

```bash
bash tests/scripts/test_extract_rust_hints.sh
```

Expected: `FAIL: awk script not found: .../.github/scripts/extract-rust-hints.awk` で exit 1。

- [ ] **Step 5: extract-rust-hints.awk を実装**

`.github/scripts/extract-rust-hints.awk`:

```awk
#!/usr/bin/env -S awk -f
# Extract (code, hint_normalized) pairs from
# gui/src-tauri/src/error.rs::default_hint_for_code match arms.
#
# Output format: <code>\t<hint_normalized>
#   - code: from string literal "code" in the arm's left side
#   - hint: from Some("...") string literal, whitespace-collapsed to single space
#   - or-pattern ("a" | "b" => Some(...)) emits one row per code
#   - None entries (=> None,) emit <<NONE>> as the hint
#   - catch-all (_ => None,) is skipped (no quoted code literal)
#
# Approach: accumulate fn body into a single buffer (newlines → space),
# then scan with regex for each match arm and emit pairs.

BEGIN {
    in_fn = 0
    buf = ""
}

/^fn default_hint_for_code/ {
    in_fn = 1
    next
}

in_fn && /^\}/ {
    in_fn = 0
}

in_fn {
    buf = buf " " $0
}

END {
    # Scan buf for match arms. Each arm matches:
    #   "code1" ( | "code2" )* => ( Some( "hint" ) | None ) ,
    # We extract them one at a time, shrinking buf as we go.
    while (match(buf, /"[a-zA-Z0-9_.]+"([[:space:]]*\|[[:space:]]*"[a-zA-Z0-9_.]+")*[[:space:]]*=>[[:space:]]*(Some\([[:space:]]*"[^"]*"[[:space:]]*\)|None)[[:space:]]*,/)) {
        arm = substr(buf, RSTART, RLENGTH)
        buf = substr(buf, RSTART + RLENGTH)
        process_arm(arm)
    }
}

function process_arm(arm,    sep_idx, left, right, hint, n, i, code, raw) {
    sep_idx = index(arm, "=>")
    if (sep_idx == 0) return
    left = substr(arm, 1, sep_idx - 1)
    right = substr(arm, sep_idx + 2)

    if (right ~ /None/) {
        hint = "<<NONE>>"
    } else {
        # Extract Some("...") arg between first " and last " inside Some(...)
        if (!match(right, /Some\([[:space:]]*"[^"]*"[[:space:]]*\)/)) return
        raw = substr(right, RSTART, RLENGTH)
        # strip Some(   "...")
        sub(/^Some\([[:space:]]*"/, "", raw)
        sub(/"[[:space:]]*\)$/, "", raw)
        hint = raw
        gsub(/[[:space:]]+/, " ", hint)
        sub(/^ /, "", hint)
        sub(/ $/, "", hint)
    }

    # Extract codes from left side ("a" | "b" | ...)
    while (match(left, /"[a-zA-Z0-9_.]+"/)) {
        code = substr(left, RSTART + 1, RLENGTH - 2)
        print code "\t" hint
        left = substr(left, RSTART + RLENGTH)
    }
}
```

- [ ] **Step 6: green 確認**

```bash
bash tests/scripts/test_extract_rust_hints.sh
```

Expected: `PASS: extract-rust-hints.awk matches expected`、exit 0。

もし FAIL の場合: diff 出力を確認し、awk 実装を修正。よくある修正点:

- regex の POSIX vs gawk 差異: `[[:space:]]` は POSIX 互換、`[a-zA-Z0-9_.]+` も互換
- `match()` 関数の戻り値: 0 = no match、>0 = byte position
- `RSTART` / `RLENGTH` のリセット: 別 `match()` 後に更新される
- 改行を含む `Some("...")` の hint normalize で改行→space 変換が効いているか

- [ ] **Step 7: commit**

```bash
git add .github/scripts/extract-rust-hints.awk \
        tests/fixtures/error-hints/sample-error.rs \
        tests/fixtures/error-hints/expected-rust.tsv \
        tests/scripts/test_extract_rust_hints.sh
git -c commit.gpgsign=false commit -m "feat(ci): extract-rust-hints.awk TDD (or-pattern + None entry handling) (Refs #692)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: extract-doc-hints.awk TDD

**Goal:** `docs/tauri-commands.md` の §「AppError default hint mapping」 table 行から `(code, hint_normalized)` pair を抽出する awk script を TDD で作成。code cell 内の or-pattern (例: `` `io.would_block` / `io.timed_out` ``) を 2 code に展開、`(hint なし: ...)` を `<<NONE>>` sentinel に変換。

**Files:**

- Create: `.github/scripts/extract-doc-hints.awk`
- Create: `tests/fixtures/error-hints/sample-tauri-commands.md`
- Create: `tests/fixtures/error-hints/expected-doc.tsv`
- Create: `tests/scripts/test_extract_doc_hints.sh`

- [ ] **Step 1: fixture sample-tauri-commands.md を作成**

`tests/fixtures/error-hints/sample-tauri-commands.md`:

```markdown
# Sample tauri-commands.md (fixture for extract-doc-hints.awk TDD)

## 他の section (本 awk は処理しない)

| col | val |
| --- | --- |
| `not.a.code` | should be ignored |

## AppError default hint mapping (`gui/src-tauri/src/error.rs::default_hint_for_code`)

> 本 table の文言は ... と完全一致させる (規約)。

| code | hint |
| --- | --- |
| `state.mtime_conflict` | metadata.json が他のプロセスで書き換えられました。「リロード」で最新を読み直すか、「上書き」で現在の編集を強制適用してください |
| `io.file_not_found` | ファイルが見つかりません。パスを確認してください |
| `io.would_block` / `io.timed_out` | I/O 処理がタイムアウト / ブロックされました。少し時間をおいて再試行してください |
| `subprocess.cancelled` | (hint なし: ユーザー操作によるキャンセルは UI 側で十分な情報を出す) |
| `internal.error` | (hint なし: 内部エラーで具体的アクションがない、message 側で logs 参照を案内) |

## 関連 (本 awk は処理しない)

- See spec ...
```

- [ ] **Step 2: 期待出力 expected-doc.tsv を作成 (sort 済)**

`tests/fixtures/error-hints/expected-doc.tsv` (Task 1 と同様、間の `\t` は TAB 1 個):

<!-- markdownlint-disable MD010 -->
```text
internal.error	<<NONE>>
io.file_not_found	ファイルが見つかりません。パスを確認してください
io.timed_out	I/O 処理がタイムアウト / ブロックされました。少し時間をおいて再試行してください
io.would_block	I/O 処理がタイムアウト / ブロックされました。少し時間をおいて再試行してください
state.mtime_conflict	metadata.json が他のプロセスで書き換えられました。「リロード」で最新を読み直すか、「上書き」で現在の編集を強制適用してください
subprocess.cancelled	<<NONE>>
```
<!-- markdownlint-enable MD010 -->

(Task 1 expected-rust.tsv と同一形式 + 同一 sorted ordering。drift check で diff -u が空になる前提)

- [ ] **Step 3: test harness test_extract_doc_hints.sh を作成**

`tests/scripts/test_extract_doc_hints.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AWK_FILE="$SCRIPT_DIR/.github/scripts/extract-doc-hints.awk"
FIXTURE="$SCRIPT_DIR/tests/fixtures/error-hints/sample-tauri-commands.md"
EXPECTED="$SCRIPT_DIR/tests/fixtures/error-hints/expected-doc.tsv"

if [[ ! -f "$AWK_FILE" ]]; then
  echo "FAIL: awk script not found: $AWK_FILE" >&2
  exit 1
fi

actual=$(awk -f "$AWK_FILE" "$FIXTURE" | sort)
expected=$(sort "$EXPECTED")

if [[ "$actual" == "$expected" ]]; then
  echo "PASS: extract-doc-hints.awk matches expected"
  exit 0
else
  echo "FAIL: drift detected"
  diff -u <(echo "$expected") <(echo "$actual")
  exit 1
fi
```

```bash
chmod +x tests/scripts/test_extract_doc_hints.sh
```

- [ ] **Step 4: red 確認 (awk なし)**

```bash
bash tests/scripts/test_extract_doc_hints.sh
```

Expected: `FAIL: awk script not found: .../.github/scripts/extract-doc-hints.awk`。

- [ ] **Step 5: extract-doc-hints.awk を実装**

`.github/scripts/extract-doc-hints.awk`:

```awk
#!/usr/bin/env -S awk -f
# Extract (code, hint_normalized) pairs from
# docs/tauri-commands.md §「AppError default hint mapping」 table rows.
#
# Output format: <code>\t<hint_normalized>
#   - code: from `code` (backtick-wrapped) in the first cell; cell may contain
#     multiple codes separated by " / " (e.g. `io.would_block` / `io.timed_out`)
#   - hint: second cell, whitespace-collapsed to single space
#   - None entry: hint cell starts with "(hint なし:" → <<NONE>> sentinel
#
# Approach: state-machine on lines. Enter target section when seeing
# "## AppError default hint mapping" header, exit on next "## " header or EOF.
# Inside section, parse rows that start with "| `".

BEGIN {
    in_section = 0
}

# Enter target section
/^## AppError default hint mapping/ {
    in_section = 1
    next
}

# Exit on next ## heading (other than entering line)
in_section && /^## / {
    in_section = 0
}

# Parse table row: | `code` ... | hint |
in_section && /^\| `/ {
    process_row($0)
}

function process_row(line,    code_cell, hint_cell, codes, n, i, code, hint, pipe_idx, second_pipe_idx, third_pipe_idx) {
    # Find pipe boundaries. Format: | cell1 | cell2 |
    # Note: cells may contain " / " or backticks but not literal |.
    pipe_idx = index(line, "|")
    if (pipe_idx != 1) return  # row must start with |
    rest = substr(line, 2)
    second_pipe_idx = index(rest, "|")
    if (second_pipe_idx == 0) return
    code_cell = substr(rest, 1, second_pipe_idx - 1)
    rest2 = substr(rest, second_pipe_idx + 1)
    third_pipe_idx = index(rest2, "|")
    if (third_pipe_idx == 0) {
        hint_cell = rest2
    } else {
        hint_cell = substr(rest2, 1, third_pipe_idx - 1)
    }

    # Extract hint
    gsub(/^[[:space:]]+|[[:space:]]+$/, "", hint_cell)
    if (hint_cell ~ /^\(hint なし:/) {
        hint = "<<NONE>>"
    } else {
        hint = hint_cell
        gsub(/[[:space:]]+/, " ", hint)
        sub(/^ /, "", hint)
        sub(/ $/, "", hint)
    }

    # Extract codes from code_cell — find all `...` patterns
    while (match(code_cell, /`[a-zA-Z0-9_.]+`/)) {
        code = substr(code_cell, RSTART + 1, RLENGTH - 2)
        print code "\t" hint
        code_cell = substr(code_cell, RSTART + RLENGTH)
    }
}
```

- [ ] **Step 6: green 確認**

```bash
bash tests/scripts/test_extract_doc_hints.sh
```

Expected: `PASS: extract-doc-hints.awk matches expected`、exit 0。

- [ ] **Step 7: commit**

```bash
git add .github/scripts/extract-doc-hints.awk \
        tests/fixtures/error-hints/sample-tauri-commands.md \
        tests/fixtures/error-hints/expected-doc.tsv \
        tests/scripts/test_extract_doc_hints.sh
git -c commit.gpgsign=false commit -m "feat(ci): extract-doc-hints.awk TDD (or-pattern '/' split + None handling) (Refs #692)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: check-error-hint-drift.sh implementation

**Goal:** Task 1-2 で作成した 2 awk parser を呼び、sort + diff -u で照合して drift → exit 1 する bash script を実装。fixture vs fixture で互いに一致することを確認。

**Files:**

- Create: `.github/scripts/check-error-hint-drift.sh`
- Create: `tests/scripts/test_check_error_hint_drift.sh`

- [ ] **Step 1: check-error-hint-drift.sh を実装**

`.github/scripts/check-error-hint-drift.sh`:

```bash
#!/usr/bin/env bash
# Check drift between gui/src-tauri/src/error.rs::default_hint_for_code
# and docs/tauri-commands.md §「AppError default hint mapping」 table.
#
# Source of truth: error.rs (docstring states "本 fn が source of truth、docs は mirror")
# Mirror:          docs/tauri-commands.md
# Both must agree on (code, hint) pairs after normalization.
#
# Exit codes:
#   0 — no drift detected
#   1 — drift detected (or input files missing)
#
# Refs: https://github.com/Idios/kobutachan-allaganeye/issues/692

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

RUST_FILE="${RUST_FILE:-$REPO_ROOT/gui/src-tauri/src/error.rs}"
DOC_FILE="${DOC_FILE:-$REPO_ROOT/docs/tauri-commands.md}"

if [[ ! -f "$RUST_FILE" ]]; then
    echo "ERROR: Rust source not found: $RUST_FILE" >&2
    exit 1
fi
if [[ ! -f "$DOC_FILE" ]]; then
    echo "ERROR: Docs file not found: $DOC_FILE" >&2
    exit 1
fi

RUST_PAIRS=$(awk -f "$SCRIPT_DIR/extract-rust-hints.awk" "$RUST_FILE" | sort)
DOC_PAIRS=$(awk -f "$SCRIPT_DIR/extract-doc-hints.awk" "$DOC_FILE" | sort)

if diff -u <(echo "$RUST_PAIRS") <(echo "$DOC_PAIRS") > /dev/null; then
    echo "OK: error.rs ↔ docs/tauri-commands.md hint mapping in sync ($(echo "$RUST_PAIRS" | wc -l) entries)"
    exit 0
fi

cat >&2 <<'EOF'

ERROR: error.rs ↔ docs/tauri-commands.md hint drift detected.

Source of truth: gui/src-tauri/src/error.rs::default_hint_for_code
Mirror:          docs/tauri-commands.md §「AppError default hint mapping」 table

Both must be updated in the same PR. See docs/tauri-commands.md docstring +
gui/src-tauri/src/error.rs::default_hint_for_code docstring for the contract.

Diff (- = error.rs side, + = docs side):
EOF
diff -u <(echo "$RUST_PAIRS") <(echo "$DOC_PAIRS") >&2 || true
exit 1
```

```bash
chmod +x .github/scripts/check-error-hint-drift.sh
```

- [ ] **Step 2: test_check_error_hint_drift.sh を作成 (fixture vs fixture)**

`tests/scripts/test_check_error_hint_drift.sh`:

```bash
#!/usr/bin/env bash
# Integration test: check-error-hint-drift.sh against fixture files.
# Fixtures are designed to match (expected pairs identical), so the
# script should exit 0.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

export RUST_FILE="$SCRIPT_DIR/tests/fixtures/error-hints/sample-error.rs"
export DOC_FILE="$SCRIPT_DIR/tests/fixtures/error-hints/sample-tauri-commands.md"

if bash "$SCRIPT_DIR/.github/scripts/check-error-hint-drift.sh"; then
    echo "PASS: fixtures match"
    exit 0
else
    echo "FAIL: fixtures should match but drift detected" >&2
    exit 1
fi
```

```bash
chmod +x tests/scripts/test_check_error_hint_drift.sh
```

- [ ] **Step 3: red 確認 → 即 green 確認 (fixture 設計上一致するので即 green になる)**

```bash
bash tests/scripts/test_check_error_hint_drift.sh
```

Expected: `OK: error.rs ↔ docs/tauri-commands.md hint mapping in sync (6 entries)` + `PASS: fixtures match`、exit 0。

(本 task は Task 1-2 で fixture を一致するよう設計しているので、新規 awk parser が正しければ即 PASS。awk 実装の bug があれば FAIL → Task 1 or 2 に戻って修正。)

- [ ] **Step 4: local shellcheck で .sh を lint**

```bash
shellcheck -S warning .github/scripts/check-error-hint-drift.sh \
                     tests/scripts/test_extract_rust_hints.sh \
                     tests/scripts/test_extract_doc_hints.sh \
                     tests/scripts/test_check_error_hint_drift.sh
```

Expected: 0 warning。warning あれば即修正。

- [ ] **Step 5: commit**

```bash
git add .github/scripts/check-error-hint-drift.sh \
        tests/scripts/test_check_error_hint_drift.sh
git -c commit.gpgsign=false commit -m "feat(ci): check-error-hint-drift.sh integration (Refs #692)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: 実機 (error.rs + tauri-commands.md) で run → drift なし確認

**Goal:** real file (project の現状) で drift なし (= source of truth と mirror が一致) を確認。drift があれば、それは本 lane 着手前から存在する問題で、別途 spec で扱う判断が必要 (本 lane scope 外なので AskUserQuestion 発動)。

- [ ] **Step 1: 実機 run**

```bash
bash .github/scripts/check-error-hint-drift.sh
```

Expected: `OK: error.rs ↔ docs/tauri-commands.md hint mapping in sync (24 entries)`、exit 0。

(error.rs の or-pattern を 2 code に展開した結果、合計 24 codes。docs も `/` 区切り展開後で 24 codes。)

- [ ] **Step 2: もし drift 検出された場合 → AskUserQuestion**

drift がある場合、それは PR #689 (Group A AppError migration) または別 PR で混入した文言不一致。本 lane の責務範囲を超える可能性あり。

```text
AskUserQuestion:
"check-error-hint-drift.sh の初回実機 run で drift が検出された。
原因 1: PR #689 以降の commit で error.rs か docs/tauri-commands.md の片側のみ更新された
原因 2: awk parser の bug (Task 1-2 の implementation)
原因 3: その他

対応案:
(a) 本 lane で docs/tauri-commands.md を error.rs に揃える修正を同梱 (scope creep を §6.4 で透明化)
(b) 別 issue 起票して本 lane scope 外、drift check job 自体は本 PR で merge し、修正 PR を別途
(c) awk parser を再点検 (Task 1-2 に戻る)
"
```

選択結果を本 plan の「Pre-flight log」節に追記。

- [ ] **Step 3: 確認結果を memo**

drift なし (exit 0) なら本 plan 「Pre-flight log」に `Task 4: real-run PASS (24 entries in sync)` を追記。

---

## Task 5: TDD red×3 (§3.4 故意 drift)

**Goal:** spec §3.4 の red×3 ケース (文言変更 / or-pattern code 削除 / None sentinel 変更) で drift check が正しく fail することを実証。Self-Test Report のエビデンスとして commit log にも残す。

**Files:**

- Touch (temporary): `docs/tauri-commands.md` (revert 必須)

- [ ] **Step 1: red 1 — 文言変更**

```bash
# `io.file_not_found` の hint cell を一時的に変更
git diff --quiet docs/tauri-commands.md  # 事前に clean 確認
sed -i.bak 's/パスを確認するか/パスを再確認するか/' docs/tauri-commands.md
bash .github/scripts/check-error-hint-drift.sh && echo "UNEXPECTED PASS" || echo "EXPECTED FAIL (exit code: $?)"
```

Expected: `ERROR: error.rs ↔ docs/tauri-commands.md hint drift detected.` + diff 出力、exit 1。

- [ ] **Step 2: revert (red 1)**

```bash
mv docs/tauri-commands.md.bak docs/tauri-commands.md
bash .github/scripts/check-error-hint-drift.sh
```

Expected: `OK: ...`、exit 0。

- [ ] **Step 3: red 2 — or-pattern code 削除**

```bash
# `io.would_block` / `io.timed_out` 行を一時的に `io.would_block` のみに変更
cp docs/tauri-commands.md docs/tauri-commands.md.bak
sed -i 's/`io.would_block` \/ `io.timed_out`/`io.would_block`/' docs/tauri-commands.md
bash .github/scripts/check-error-hint-drift.sh && echo "UNEXPECTED PASS" || echo "EXPECTED FAIL (io.timed_out missing)"
```

Expected: 出力で `+ io.timed_out<TAB>I/O 処理が...` (docs 側に欠ける code) が `-` 行として error.rs 側に存在する diff となり exit 1。`<TAB>` は TAB 文字 1 個。

- [ ] **Step 4: revert (red 2)**

```bash
mv docs/tauri-commands.md.bak docs/tauri-commands.md
bash .github/scripts/check-error-hint-drift.sh
```

Expected: `OK: ...`、exit 0。

- [ ] **Step 5: red 3 — None sentinel 変更**

```bash
# `subprocess.cancelled` の `(hint なし: ...)` を実際の文言に変更
cp docs/tauri-commands.md docs/tauri-commands.md.bak
sed -i 's/(hint なし: ユーザー操作.*)/キャンセルされました/' docs/tauri-commands.md
bash .github/scripts/check-error-hint-drift.sh && echo "UNEXPECTED PASS" || echo "EXPECTED FAIL (None sentinel mismatch)"
```

Expected: `subprocess.cancelled` の hint が `<<NONE>>` (error.rs 側) vs `キャンセルされました` (docs 側) で diff、exit 1。

- [ ] **Step 6: revert (red 3)**

```bash
mv docs/tauri-commands.md.bak docs/tauri-commands.md
bash .github/scripts/check-error-hint-drift.sh
git diff --quiet docs/tauri-commands.md  # 完全 revert 確認
```

Expected: `OK: ...`、exit 0、`git diff --quiet` も exit 0 (差分なし)。

- [ ] **Step 7: TDD log を保存 (Self-Test Report 用)**

```bash
mkdir -p docs/superpowers/specs/lane-iv-b-prime-evidence
cat > docs/superpowers/specs/lane-iv-b-prime-evidence/tdd-red-green-log.md <<'EOF'
# TDD red×3 verification log (Lane IV-b' #692)

Spec: docs/superpowers/specs/2026-05-11-lane-iv-b-prime-design.md §3.4

## red 1: 文言変更
- 変更: `io.file_not_found` hint cell を「パスを確認」→「パスを再確認」
- 結果: exit 1、diff 出力で文言 mismatch を明示

## red 2: or-pattern code 削除
- 変更: docs から `io.timed_out` を削除 (or-pattern を `io.would_block` のみに)
- 結果: exit 1、`+ io.timed_out\t...` 行が docs side に欠落

## red 3: None sentinel 変更
- 変更: `subprocess.cancelled` の cell を `(hint なし: ...)` → 「キャンセルされました」
- 結果: exit 1、Rust side `<<NONE>>` vs docs side 実文言 mismatch

## green (revert 後)
- すべての revert 後で `OK: error.rs ↔ docs/tauri-commands.md hint mapping in sync (24 entries)`
- `git diff --quiet docs/tauri-commands.md` exit 0
EOF
```

- [ ] **Step 8: commit**

```bash
git add docs/superpowers/specs/lane-iv-b-prime-evidence/
git -c commit.gpgsign=false commit -m "test: TDD red×3 verification log for hint drift check (Refs #692)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: ci.yml に doc-error-hint-drift job 追加

**Goal:** `.github/workflows/ci.yml` に `doc-error-hint-drift` job を追加し、push / pull_request トリガで drift check を自動実行。precedent は同 file の `doc-tauri-commands-drift` (行 157+)。

**Files:**

- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: ci.yml の `doc-tauri-commands-drift` job の直後に doc-error-hint-drift job を挿入**

`.github/workflows/ci.yml` の `doc-tauri-commands-drift` job (現在 157-178 行付近、`installer-pester:` の前) の直後に以下を追加:

```yaml
  doc-error-hint-drift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Check error.rs ↔ docs/tauri-commands.md hint mapping drift
        shell: bash
        run: bash .github/scripts/check-error-hint-drift.sh
```

実装時の参考: `doc-tauri-commands-drift` job 構造 (現状):

```yaml
  doc-tauri-commands-drift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Check tauri-commands.md drift vs lib.rs (name-level set-diff)
        shell: bash
        run: |
          set -euo pipefail
          # ... inline awk + sort -u + diff -u ...
```

本 task の job は同等の構造で、inline ではなく外部 script (`.github/scripts/check-error-hint-drift.sh`) を呼ぶ点が異なる。

- [ ] **Step 2: ci.yml の yaml syntax を local 確認**

```bash
# Python の場合
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))" && echo "YAML OK"

# または yq があれば
# yq eval '.jobs.doc-error-hint-drift' .github/workflows/ci.yml
```

Expected: `YAML OK`、または yq 出力で新 job が見える。

- [ ] **Step 3: act / GH Actions local runner で動作確認 (option、skip 可)**

```bash
# act がインストールされていれば
# act -j doc-error-hint-drift
```

act 未インストールなら skip。CI 上の実証は PR-1 push 時に行う (Task 10)。

- [ ] **Step 4: commit**

```bash
git add .github/workflows/ci.yml
git -c commit.gpgsign=false commit -m "feat(ci): doc-error-hint-drift job 追加 (Refs #692)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: ci.yml に shellcheck job 追加 + 既存 script 対応

**Goal:** ci.yml に shellcheck job を新規追加 (Q5 確定、repo 全体 .sh 対象)。Task 0 で確認した既存 script の shellcheck 状況に応じて修正も同梱。

**Files:**

- Modify: `.github/workflows/ci.yml`
- Possibly modify: `scripts/check-markdownlint.sh`, `scripts/cleanup-worktrees.sh` (Task 0 結果による)

- [ ] **Step 1: ci.yml に shellcheck job 追加**

Task 6 で追加した `doc-error-hint-drift` job の直後に挿入:

```yaml
  shellcheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run shellcheck on all .sh files
        uses: ludeeus/action-shellcheck@2.0.0
        with:
          severity: warning
          scandir: '.'
          additional_files: '.github/scripts/*.sh tests/scripts/*.sh scripts/*.sh'
```

注: `ludeeus/action-shellcheck@2.0.0` のバージョン pin。 `@master` は再現性に難。`2.0.0` の存在は実装時に `gh api /repos/ludeeus/action-shellcheck/releases` で確認、最新 stable に合わせる。

- [ ] **Step 2: Task 0 結果分岐**

| Task 0 結果 | 本 step の対応 |
| --- | --- |
| pass (0 件) | 次 step (yaml verify) へ |
| 軽微 (1-3 件) | 既存 script に shellcheck pragma または quote 修正を最小限で追加。ファイル単位で commit を分けて track |
| 多数 (4+ 件) | Task 0 で AskUserQuestion 済の判断結果に従う (本 PR で全件修正 / 別 issue 起票 / `\|\|true` 許容) |

軽微修正の例 (`scripts/check-markdownlint.sh` で SC2086 想定):

```bash
# 修正前
markdownlint-cli2 $files
# 修正後
markdownlint-cli2 "$files"
# または shellcheck disable 行追加 (やむを得ない場合)
# shellcheck disable=SC2086
```

- [ ] **Step 3: local shellcheck で repo 全体 .sh が pass することを確認**

```bash
shellcheck -S warning .github/scripts/*.sh tests/scripts/*.sh scripts/*.sh
echo "exit: $?"
```

Expected: 出力なし、exit 0。

- [ ] **Step 4: ci.yml yaml syntax 確認**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))" && echo "YAML OK"
```

Expected: `YAML OK`。

- [ ] **Step 5: commit (修正があれば 2 commit に分割)**

```bash
# ci.yml shellcheck job 追加分
git add .github/workflows/ci.yml
git -c commit.gpgsign=false commit -m "feat(ci): shellcheck job 追加 (repo 全体 .sh) (Refs #692)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"

# 既存 script の shellcheck 対応分 (該当あれば)
git add scripts/*.sh
git -c commit.gpgsign=false commit -m "fix(scripts): shellcheck warnings 対応 (Refs #692)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: roadmap plan.md (§5.1 表通り 4 ヶ所修正)

**Goal:** `docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md` の Lane IV-b' 関連記述を 2 件 / 2 章 (#692 / #700) に縮小、#458 は handoff として明記。spec §5.1 表通り。

**Files:**

- Modify: `docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md`

- [ ] **Step 1: 修正対象 hit を grep で全列挙**

```bash
grep -n "Lane IV-b'\|#458\|Group J" docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md
```

Expected: spec §5.1 表で示した 4 ヶ所 (行 81 付近、行 110 付近、行 162 付近、行 200 付近) + 関連の hit (§4 deferred 表追記対象、255 付近)。実際の行番号は本 task 実行時の git HEAD 状態に依存。

- [ ] **Step 2: 行 81 付近を修正 (Group G 並行安全度行)**

該当箇所 (現状):

```markdown
**並行安全度**: high (`.github/ISSUE_TEMPLATE/bug_report.yml` 独立) / **brainstorming 単位**: Lane IV-b' で Group J と統合 (1 spec / 3 章)
```

修正後:

```markdown
**並行安全度**: high (`.github/ISSUE_TEMPLATE/bug_report.yml` 独立) / **brainstorming 単位**: 本 issue は Lane IV-b' から scope-out (PR #497 + PR #688 で実装完了済、残るは L2 release 後の UI 実測のみ、release gate 後に `/close-issue` で handoff)。Lane IV-b' は Group J 単独 (1 spec / 2 章)
```

- [ ] **Step 3: 行 110 付近を修正 (Lane IV-b' description)**

該当箇所 (現状):

```markdown
  Lane IV-b'  Group G remainder + Group J 統合 (workflow / CI / docs polish)
              #458 (P2、bug_report.yml) // #692 (error.rs hint drift CI) // #700 (markdownlint nested ignore)
              file 完全独立、PR 並行可
              1 spec / 3 章
```

修正後:

```markdown
  Lane IV-b'  Group J 単独 (workflow / CI / docs polish)
              #692 (error.rs hint drift CI) // #700 (markdownlint nested ignore)
              file 完全独立、PR 並行可
              1 spec / 2 章

              ※ Group G #458 は本 lane から scope-out (実装完了済、release gate 後 /close-issue handoff)
```

- [ ] **Step 4: 行 162 付近を修正 (Wave 1 ASCII 図)**

該当箇所 (現状):

```markdown
  Lane IV-b'  Group G remainder + Group J 統合 (workflow / CI / docs polish)
              #458 (P2、bug_report.yml) // #692 (error.rs hint drift CI) // #700 (markdownlint nested ignore)
              file 完全独立、PR 並行可
              1 spec / 3 章
```

修正後: Step 3 と同一に修正 (本 doc は ASCII 図と説明文で 2 ヶ所同記述あり、grep -n で 2 件 hit するため両方修正)。

- [ ] **Step 5: 行 200 付近を修正 (brainstorming 入り口)**

該当箇所 (現状):

```markdown
/superpowers:brainstorming Lane IV-b': Group G #458 + Group J #692 #700 (workflow / CI / docs polish)
```

修正後:

```markdown
/superpowers:brainstorming Lane IV-b': Group J #692 #700 (workflow / CI / docs polish、#458 は scope-out)
```

- [ ] **Step 6: §4 deferred 表に #458 handoff 追記**

該当箇所 (現状の §「v0.2.0 外確定 (deferred ラベル維持、6 件)」 直前):

```markdown
## 4. deferred / v0.2.0 対象外
```

修正方針: §「v0.2.0 外確定」の表の直下、または別 sub-section として追加:

```markdown
### Group G #458 — Lane IV-b' から scope-out (handoff)

[#458](https://github.com/Idios/kobutachan-allaganeye/issues/458) (P2、bug_report.yml) は本 plan 公開時点で実装作業完了済 (PR #497 + PR #688)、残る受け入れ条件 1 件「New issue UI からテンプレ選択可能」は L2 release (`develop-0.2.0 → main` マージ) 後に main 反映済みの環境で実測する必要があるため、Lane IV-b' (Wave 1) から scope-out した。

release gate (Wave 3) 後、L3 初期に `/close-issue` skill で実測 → close する handoff path で運用する。
```

- [ ] **Step 7: markdownlint pass 確認**

```bash
bash scripts/check-markdownlint.sh docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md
```

Expected: `0 error(s)`。

- [ ] **Step 8: commit**

```bash
git add docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md
git -c commit.gpgsign=false commit -m "docs(roadmap): Lane IV-b' を Group J 単独に縮小 (#458 scope-out) (Refs #458 #692 #700)

本 brainstorming session (spec docs/superpowers/specs/2026-05-11-lane-iv-b-prime-design.md §5)
で確定した Lane IV-b' scope 縮小を roadmap plan に反映。

- Lane IV-b' = Group J 単独 (1 spec / 2 章、#692 + #700)
- Group G #458 は Lane IV-b' から scope-out (実装完了済、release gate 後
  /close-issue handoff)
- §4 deferred 表に #458 handoff path を追記

Refs #458 #692 #700

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: roadmap design.md (§5.1 相当 4 ヶ所修正)

**Goal:** `docs/superpowers/specs/2026-05-11-l2-v020-roadmap-update-design.md` の Lane IV-b' 関連記述も整合修正。Task 8 の plan.md と同じ趣旨。

**Files:**

- Modify: `docs/superpowers/specs/2026-05-11-l2-v020-roadmap-update-design.md`

- [ ] **Step 1: 修正対象 hit を grep で列挙**

```bash
grep -n "Lane IV-b'\|#458\|Group J" docs/superpowers/specs/2026-05-11-l2-v020-roadmap-update-design.md
```

Expected: spec §5.1 表で示した 4 ヶ所相当 (§4.1 Group G 行、§4.2 Lane IV-b' 行、§4.3 file matrix 行、§4.6 brainstorming 入り口)。

- [ ] **Step 2: §4.1 Group G 行を修正**

該当箇所 (現状):

```markdown
| **G** | **l2-workflow 残** | **1** | OPEN | [#458](...) (P2) |
```

修正後 (notes column の追加またはコメント):

```markdown
| **G** | **l2-workflow 残** | **1** | OPEN | [#458](...) (P2) — Lane IV-b' から scope-out (release gate 後 handoff) |
```

- [ ] **Step 3: §4.2 Lane IV-b' 行を修正 (Wave 1 lane 表内)**

該当箇所 (現状、Wave 1 ASCII 図内):

```markdown
  Lane IV-b'  Group G remainder + Group J 統合 (workflow / CI / docs polish)
              #458 (P2、bug_report.yml) // #692 (error.rs hint drift CI) // #700 (markdownlint nested ignore)
              file 完全独立、PR 並行可
              1 spec / 3 章
```

修正後:

```markdown
  Lane IV-b'  Group J 単独 (workflow / CI / docs polish)
              #692 (error.rs hint drift CI) // #700 (markdownlint nested ignore)
              file 完全独立、PR 並行可
              1 spec / 2 章

              ※ Group G #458 は本 lane から scope-out (実装完了済、release gate 後 /close-issue handoff)
```

- [ ] **Step 4: §4.3 file 衝突 matrix 行を修正**

該当箇所 (現状):

```markdown
| IV-b' (#458 #692 #700) | ... | ✓ #692 | ✓ #692 | ✓ #458 | ✓ #700 | | |
```

修正後 (issue template 列の ✓ #458 を削除し、lane ラベルから #458 を外す):

```markdown
| IV-b' (#692 #700) | ... | ✓ #692 | ✓ #692 | | ✓ #700 | | |
```

- [ ] **Step 5: §4.6 brainstorming 入り口を修正**

該当箇所 (現状):

```markdown
/superpowers:brainstorming Lane IV-b': Group G #458 + Group J #692 #700 (workflow / CI / docs polish)
```

修正後:

```markdown
/superpowers:brainstorming Lane IV-b': Group J #692 #700 (workflow / CI / docs polish、#458 は scope-out)
```

- [ ] **Step 6: markdownlint pass 確認**

```bash
bash scripts/check-markdownlint.sh docs/superpowers/specs/2026-05-11-l2-v020-roadmap-update-design.md
```

Expected: `0 error(s)`。

- [ ] **Step 7: commit**

```bash
git add docs/superpowers/specs/2026-05-11-l2-v020-roadmap-update-design.md
git -c commit.gpgsign=false commit -m "docs(roadmap-spec): Lane IV-b' design doc を Group J 単独に縮小 (Refs #458 #692 #700)

Task 8 で更新した roadmap plan.md と整合する形で base design doc も修正。
Lane IV-b' = Group J 単独 (#692 + #700)、Group G #458 は scope-out + handoff。

Refs #458 #692 #700

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: PR-1 作成

**Goal:** PR-1 (#692 + adjacency: spec doc + roadmap doc 修正 + drift CI job + shellcheck job + 既存 script 修正) を作成し、CI を pass させる。

**Files:** (touch なし)

- [ ] **Step 1: PR-1 Pre-flight 再実行 (Iron Law 6)**

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline | head -20
```

Expected: 出力なし (取り込み未済 commit なし) または数件 (取り込み未済あれば次 step で merge)。

```bash
# 取り込み未済 commit あれば
# git merge origin/develop-0.2.0
# conflict なければ続行、conflict あれば手動解決
```

- [ ] **Step 2: 並行 worktree PR 重複確認**

```bash
gh pr list --state open --json number,title,headRefName \
  | jq '.[] | select(.title | test("#692|#700|Lane IV-b") )'
```

Expected: 該当なし。万一 open で並行 PR あれば user 判断仰ぐ。

- [ ] **Step 3: 本 worktree branch を push**

```bash
git push -u origin claude/tender-moore-2a5d2f
```

Expected: branch が origin に push される。

- [ ] **Step 4: PR-1 本文を作成 (printf | gh pr create --body-file -)**

```bash
printf '%s\n' \
'## スコープ' \
'' \
'Lane IV-b'\'' (Group J #692 hint drift CI) を実装。' \
'' \
'- `.github/scripts/check-error-hint-drift.sh` + 2 awk file (extract-rust-hints.awk / extract-doc-hints.awk) 新規作成' \
'- `.github/workflows/ci.yml` に `doc-error-hint-drift` job 追加 (`doc-tauri-commands-drift` precedent 踏襲)' \
'- `.github/workflows/ci.yml` に `shellcheck` job 新規追加 (repo 全体 .sh 対象、Q5)' \
'- 本 brainstorming session で確定した Lane IV-b'\'' scope 縮小 (#458 scope-out、release gate 後 handoff) を `docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md` + `docs/superpowers/specs/2026-05-11-l2-v020-roadmap-update-design.md` に反映 (fact 訂正、§5)' \
'- 本 Lane IV-b'\'' spec doc を新規追加: `docs/superpowers/specs/2026-05-11-lane-iv-b-prime-design.md`' \
'' \
'Refs #692' \
'' \
'## 受け入れ条件 (#692)' \
'' \
'- [x] error.rs から (code, hint) 抽出 script (`.github/scripts/extract-rust-hints.awk`)' \
'- [x] docs/tauri-commands.md から (code, hint) 抽出 script (`.github/scripts/extract-doc-hints.awk`)' \
'- [x] sort + diff -u で drift → CI fail (ci.yml に `doc-error-hint-drift` job 追加)' \
'- [x] or-pattern (`io.would_block | io.timed_out`) / None entries (`subprocess.cancelled` / `internal.error`) の handling' \
'- [x] 故意 drift → red → fix → green の TDD 検証 (`docs/superpowers/specs/lane-iv-b-prime-evidence/tdd-red-green-log.md`)' \
'' \
'## Test plan (本 PR 提出前にローカルで実行済)' \
'' \
'- [x] `bash tests/scripts/test_extract_rust_hints.sh` → PASS' \
'- [x] `bash tests/scripts/test_extract_doc_hints.sh` → PASS' \
'- [x] `bash tests/scripts/test_check_error_hint_drift.sh` → PASS' \
'- [x] `bash .github/scripts/check-error-hint-drift.sh` → OK (24 entries in sync)' \
'- [x] §3.4 red×3 (文言変更 / or-pattern code 削除 / None sentinel 変更) → 3 ケース exit 1、revert で exit 0' \
'- [x] `shellcheck -S warning .github/scripts/*.sh tests/scripts/*.sh scripts/*.sh` → 0 warning' \
'- [x] `bash scripts/check-markdownlint.sh` → 0 error' \
'- [x] `python -c "import yaml; yaml.safe_load(open('\''.github/workflows/ci.yml'\''))"` → YAML OK' \
'' \
'## scope creep 透明化' \
'' \
'本 PR は (a) #692 実装 / (b) shellcheck job + 既存 script 軽微修正 / (c) Lane IV-b'\'' scope 縮小の roadmap doc fact 訂正 / (d) Lane IV-b'\'' spec doc 新規追加 を含む。Iron Law 3 (1 PR = 1 scope) との整合は spec [§5.3](docs/superpowers/specs/2026-05-11-lane-iv-b-prime-design.md#L53-scope-creep-警戒の透明化) で「Lane IV-b'\'' 事実訂正 = scope 内」と判断、(d) は spec doc 同梱の慣習に従う。' \
'' \
'## 実機検証 (machine-unverifiable)' \
'' \
'- 該当なし (CI workflow / lint config / docs のみの変更、GPU / audio / video detector / GUI Tauri touch なし)' \
'' \
'session-id: tender-moore-2a5d2f' \
  | gh pr create --base develop-0.2.0 --title "feat(ci): error.rs hint table drift check job 追加 (Refs #692)" --body-file -
```

Expected: PR URL が出力される。memo (本 plan 末尾の Pre-flight log に追記)。

- [ ] **Step 5: PR 番号を取得して CI watch**

```bash
PR_NUM=$(gh pr view --json number --jq .number)
echo "PR-1: #$PR_NUM"
gh pr checks "$PR_NUM" --watch
```

Expected: 全 CI job が pass (markdownlint / shellcheck / doc-error-hint-drift / 既存 全 job)。

- [ ] **Step 6: CI 失敗時の対応**

`/iterate-review` skill を起動するか、CI log を確認して inline 修正:

- markdownlint fail: 該当 file を bash scripts/check-markdownlint.sh で local 確認、修正
- shellcheck fail: local で再 lint、修正
- doc-error-hint-drift fail: error.rs と docs/tauri-commands.md の drift を解消
- yaml syntax fail: ci.yml の structure 確認

各修正 commit → push → CI 再 watch。

- [ ] **Step 7: PR-1 メタ情報を本 plan に記録**

```bash
# 本 plan の末尾「Pre-flight log」節に追記:
# - PR-1 URL
# - PR-1 番号
# - PR-1 作成時刻
```

---

## Task 11: PR-2 — .markdownlint-cli2.yaml 修正 + local 検証 + commit

**Goal:** PR-2 (#700) の実装。`.markdownlint-cli2.yaml` の `ignores` に `**/node_modules/**` を 1 行追加、local で 7712 → 0 を確認。

**Files:**

- Modify: `.markdownlint-cli2.yaml`

**Note:** Task 11-12 は PR-1 と独立、並行作業可。実行環境としては **同 worktree で PR-1 の branch を base に作業すると merge 順序問題が出るため、別 worktree (新規 session) で PR-2 を作るのが望ましい**。本 plan は同 worktree 直列実行を想定 (説明簡素化)、subagent dispatch なら別 worktree dispatch を推奨。

- [ ] **Step 1: PR-1 完了確認 (または別 worktree 切り替え)**

```bash
# Option A: 同 worktree 直列 — PR-1 が merge されてから PR-2 着手
gh pr view --json number,state --jq '{number: .number, state: .state}'
# state: "MERGED" なら次へ。"OPEN" なら待機 or 別 worktree で PR-2 を並行

# Option B: 別 worktree (新 session) で PR-2 作成
# git worktree add .claude/worktrees/<auto-name>-pr2 develop-0.2.0
# cd .claude/worktrees/<auto-name>-pr2
```

- [ ] **Step 2: pre-install で gui/node_modules/ を生成 (red 確認用)**

```bash
cd gui && npm install
cd ..
ls gui/node_modules | head -5
```

Expected: `gui/node_modules/` 配下に大量の package directory。

- [ ] **Step 3: red 確認 — 修正前の markdownlint 結果**

```bash
bash scripts/check-markdownlint.sh 2>&1 | tail -5
```

Expected: 7000+ errors (issue #700 報告では 7712、依存 package 更新で前後する)。

- [ ] **Step 4: .markdownlint-cli2.yaml を修正**

`.markdownlint-cli2.yaml` の `ignores` セクションを以下に変更:

```yaml
ignores:
  - "node_modules/**"
  - "**/node_modules/**"  # nested (gui/node_modules 等) も除外 (#700)
  - ".venv/**"
  - ".git/**"
  - ".pytest_cache/**"
  - ".ruff_cache/**"
  - "**/kobutachan_allaganeye.egg-info/**"
```

- [ ] **Step 5: green 確認 — 修正後の markdownlint 結果**

```bash
bash scripts/check-markdownlint.sh 2>&1 | tail -5
```

Expected: `0 error(s)`。

- [ ] **Step 6: CI 無影響確認 — .markdownlint-cli2.yaml の glob 仕様を ad-hoc に確認**

```bash
# CI は npm install 未実行のため gui/node_modules/ 不在、挙動変化なし
# 念のため: cwd 直下の hypothetical node_modules も引き続き ignore されることを確認
# (node_modules/** glob が残っているので OK、目視で .markdownlint-cli2.yaml 確認)
cat .markdownlint-cli2.yaml | grep -A 7 "^ignores:"
```

Expected: `node_modules/**` と `**/node_modules/**` の両 entry が見える。

- [ ] **Step 7: commit**

```bash
git add .markdownlint-cli2.yaml
git -c commit.gpgsign=false commit -m "fix(markdownlint): nested gui/node_modules を ignore に追加 (Refs #700)

.markdownlint-cli2.yaml の ignores glob を node_modules/** から
{node_modules/**, **/node_modules/**} の併記に変更。markdownlint-cli2 の
glob 仕様で node_modules/** は cwd 直下のみ match し nested (gui/node_modules/)
に届かない問題を解消。

検証:
- 修正前: bash scripts/check-markdownlint.sh で 7712 errors
- 修正後: bash scripts/check-markdownlint.sh で 0 errors
- CI 影響なし (CI は npm install しないため gui/node_modules/ 不在)

Refs #700

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: PR-2 作成

**Goal:** PR-2 (#700) を作成、CI pass を確認。

- [ ] **Step 1: PR-2 Pre-flight (Iron Law 6)**

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline | head -20
gh pr list --state open --json number,title --jq '.[] | select(.title | test("#700|markdownlint") )'
```

Expected: 取り込み未済 commit なし、並行 PR なし (PR-1 は #692 で別 issue なので重複に該当しない)。

- [ ] **Step 2: branch を push**

```bash
git push -u origin "$(git branch --show-current)"
```

- [ ] **Step 3: PR-2 本文作成**

```bash
printf '%s\n' \
'## スコープ' \
'' \
'Lane IV-b'\'' (Group J #700 markdownlint nested ignore) を実装。' \
'' \
'- `.markdownlint-cli2.yaml` の `ignores` に `**/node_modules/**` を 1 行追加' \
'- `markdownlint-cli2` の glob 仕様で `node_modules/**` は cwd 直下のみ match し nested (`gui/node_modules/`) に届かない問題を解消' \
'- CI は `npm install` 未実行のため `gui/node_modules/` 不在、CI 挙動変化なし' \
'' \
'spec doc は PR-1 に同梱: [docs/superpowers/specs/2026-05-11-lane-iv-b-prime-design.md §4](docs/superpowers/specs/2026-05-11-lane-iv-b-prime-design.md)' \
'' \
'Refs #700' \
'' \
'## 受け入れ条件 (#700)' \
'' \
'- [x] `.markdownlint-cli2.yaml` の ignores glob 修正' \
'- [x] `gui/node_modules/**/*.md` の誤検出 7712 → 0 (local 検証済)' \
'- [x] CI markdownlint job pass 維持 (npm install 不要のため挙動変化なし)' \
'' \
'## Test plan (本 PR 提出前にローカルで実行済)' \
'' \
'- [x] `cd gui && npm install` で gui/node_modules/ を用意' \
'- [x] 修正前 `bash scripts/check-markdownlint.sh` → 7712 errors (red 確認)' \
'- [x] `.markdownlint-cli2.yaml` に `**/node_modules/**` を追加' \
'- [x] 修正後 `bash scripts/check-markdownlint.sh` → 0 errors (green)' \
'- [x] `.markdownlint-cli2.yaml` の syntax (yaml load) OK' \
'' \
'## 実機検証 (machine-unverifiable)' \
'' \
'- 該当なし (lint config 1 行修正のみ、GPU / audio / video detector / GUI Tauri touch なし)' \
'' \
'session-id: tender-moore-2a5d2f' \
  | gh pr create --base develop-0.2.0 --title "fix(markdownlint): nested gui/node_modules を ignore に追加 (Refs #700)" --body-file -
```

Expected: PR URL 出力。

- [ ] **Step 4: CI watch**

```bash
PR_NUM=$(gh pr view --json number --jq .number)
echo "PR-2: #$PR_NUM"
gh pr checks "$PR_NUM" --watch
```

Expected: 全 CI job pass。

- [ ] **Step 5: PR-2 メタ情報を本 plan に記録**

本 plan 末尾「Pre-flight log」節に PR-2 URL / 番号 / 作成時刻を追記。

---

## Pre-flight log (実装中追記用)

実装フェーズで追記する記録。各 task 完了時に状況を memo。

### Task 0 結果 (2026-05-11 session `tender-moore-2a5d2f`)

- 取り込み未済 commit: **なし** (worktree は `origin/develop-0.2.0` と同期)
- 並行 worktree PR: **なし** (`gh pr list --state open --search "#692 OR #700 OR Lane IV-b"` 出力 `[]`)
- shellcheck install: **NOT_INSTALLED** (Windows local + sandbox 制限で winget / WSL apt の install attempt 不可)
- shellcheck local 実行: **skip** (未 install のため、subagent 環境では install できず)
- Manual static analysis (代替):
  - `scripts/check-markdownlint.sh` (27 lines): 0 issues estimated (set -euo pipefail / BASH_SOURCE / quote 全て clean)
  - `scripts/cleanup-worktrees.sh` (108 lines): 1 warning estimated (line 94 `[[ -z "$(ls -A "$d" 2>/dev/null)" ]]` で SC2012 `Use find instead of ls`)
  - 合計 estimated: 1 warning (軽微 1-3 範囲)
- **判定: 軽微 1-3 件 branch を採用** — Task 7 で shellcheck job 追加 + 既存 script に必要最小限の修正 (SC2012 pragma or `find` 置換、本 PR 内で透明化)
- shellcheck CI 上動作: `ludeeus/action-shellcheck@master` (または pinned version) が `ubuntu-latest` で shellcheck を auto-install して実行するため、local 未 install は CI 動作に影響なし。Task 7 「local shellcheck で repo 全体 .sh が pass」step は CI 実証 (PR-1 push 時) で代替する
- 多数 (4+) でなかったため AskUserQuestion 発動なし

### Task 4 結果 (実機 drift run)

- exit code: [TBD - 0 (sync) or 1 (drift)]
- entries 数: [TBD - 24 entries 想定]
- drift 検出時の AskUserQuestion 結果: [該当時のみ TBD]

### PR-1 メタ情報

- PR URL: [TBD]
- PR 番号: [TBD]
- 作成時刻: [TBD]
- CI 結果: [TBD]
- merge 時刻: [TBD]

### PR-2 メタ情報

- PR URL: [TBD]
- PR 番号: [TBD]
- 作成時刻: [TBD]
- CI 結果: [TBD]
- merge 時刻: [TBD]

---

## 完了後の handoff (本 plan 外、参考)

各 PR merge 後の手順:

1. `/close-issue` skill 起動 (PR-1 ↔ #692、PR-2 ↔ #700 を個別 close)
   - 受け入れ条件の merge 後 base ブランチでの実測再検証
   - 未消化チェックボックスや残タスクのトリアージ
   - 個別 issue を Idios 確認後 `gh issue close`
2. **#458 は本 lane では touch なし** — release gate (Wave 3、`/release` skill) 後の L3 初期に別 session で:
   - `develop-0.2.0 → main` マージ後の New issue UI で「[bug] バグ報告」テンプレ選択を実測
   - `/close-issue` で #458 を close
