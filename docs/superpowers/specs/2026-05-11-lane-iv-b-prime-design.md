# L2 Lane IV-b' (Group J + Group G remainder 調整) 設計

> **Status**: L2 (v0.2.0) Wave 1 polish lane の workflow / CI / docs polish スコープ
> **Scope**: [#692](https://github.com/Idios/kobutachan-allaganeye/issues/692) + [#700](https://github.com/Idios/kobutachan-allaganeye/issues/700) 統合 (1 spec / 2 章 / 2 並行 PR) + [#458](https://github.com/Idios/kobutachan-allaganeye/issues/458) は scope-out (release gate 後 handoff)
> **session**: `tender-moore-2a5d2f` (2026-05-11 brainstorming)
> **roadmap**: [`docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md`](../plans/2026-05-11-l2-v020-roadmap-update.md) §Lane IV-b'
>
> **precedent**: [`docs/superpowers/specs/2026-05-08-lane-iv-b-group-g-design.md`](2026-05-08-lane-iv-b-group-g-design.md) (Wave 0 Lane IV-b、#624 / #458 / #682)

## §1 Overview

Lane IV-b' は L2 (v0.2.0) Wave 1 polish lane の 1 つで、post-#663 cleanup の workflow / CI / docs polish を担う。当初 roadmap (`2026-05-11-l2-v020-roadmap-update.md`) では Group G #458 + Group J #692 #700 の 3 件 / 3 章を想定したが、本 brainstorming session (Q1) で **#458 を scope-out** に確定した:

- **#458 (bug_report.yml)**: 本体は PR [#497](https://github.com/Idios/kobutachan-allaganeye/pull/497) (2026-04-21 develop-0.2.0 マージ済) + PR [#688](https://github.com/Idios/kobutachan-allaganeye/pull/688) (2026-05-08 Wave 0 で field id 凍結 + #669 連動 note 先取り済) で実装完了。受け入れ条件 5 項目中 4 項目検証済、残る 1 項目「New issue UI でテンプレ選択可能」は L2 release (`develop-0.2.0 → main` マージ) 後でないと検証不能。**Lane IV-b' では実装作業を行わず、release gate 後の L3 初期に `/close-issue` skill で UI 実測 → close する handoff として扱う**

実装対象は **2 件 / 2 章 / 2 並行 PR** (Q2):

| issue | priority | 概要 | 本 spec での扱い |
| --- | --- | --- | --- |
| [#692](https://github.com/Idios/kobutachan-allaganeye/issues/692) | P3 (task) | error.rs hint table drift check CI job 追加 | §3 (中核章、mid-weight PR-1) |
| [#700](https://github.com/Idios/kobutachan-allaganeye/issues/700) | P3 (bug) | markdownlint ignore で nested `gui/node_modules` を除外 | §4 (1 行修正、light PR-2) |

加えて、3 件 → 2 件への縮小に伴う roadmap doc 表現の事実訂正を §5 で扱う。

### Lane / wave 設計上の位置づけ

- **Lane IV-b'** = Wave 1 polish lane (Group I Lane V / Group J Lane IV-b' / Group K Lane IV-e) の 1 つ
- file 完全独立 (`.github/scripts/*.sh,*.awk` / `.github/workflows/ci.yml` / `docs/tauri-commands.md` / `gui/src-tauri/src/error.rs` / `.markdownlint-cli2.yaml` / `docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md` / `docs/superpowers/specs/2026-05-11-l2-v020-roadmap-update-design.md`) → Wave 1 全 lane と並行可
- Wave 1 main lane (I-B / II-a / II-b) と file 衝突なし、後段 wave への依存なし

## §2 Goals

1. **#692**: `gui/src-tauri/src/error.rs::default_hint_for_code` (22 hint entries + 2 None entries `subprocess.cancelled` / `internal.error`、or-pattern `io.would_block | io.timed_out` を 2 code に展開して計 24 codes) と `docs/tauri-commands.md` §「AppError default hint mapping」 table の (code, hint) ペア文言完全一致を CI で保証する drift check job (bash + awk、`doc-tauri-commands-drift` precedent 踏襲) を `.github/workflows/ci.yml` に追加。TDD red→green 検証 (故意 drift → red 確認 → revert → green) で挙動を担保
2. **#700**: `.markdownlint-cli2.yaml` の `ignores: node_modules/**` に `**/node_modules/**` を併記し、`gui/node_modules/` 配下 7712 誤検出を 0 にする。CI は `npm install` しないため CI 挙動に影響なし、dev 体験 (`bash scripts/check-markdownlint.sh`) のみ改善
3. **roadmap doc adjustment**: `docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md` および同 design `docs/superpowers/specs/2026-05-11-l2-v020-roadmap-update-design.md` の Lane IV-b' 関連記述 4 ヶ所を 2 件 / 2 章 (#692 / #700) に縮小、#458 は「release gate 後 `/close-issue` handoff」として deferred 表に明記

## §3 #692 hint drift CI 設計

### §3.1 現状

`gui/src-tauri/src/error.rs::default_hint_for_code` (現行、抜粋):

```rust
fn default_hint_for_code(code: &str) -> Option<&'static str> {
    match code {
        "state.mtime_conflict" => Some("metadata.json が他の..."),
        // ... 中略 ...
        "io.would_block" | "io.timed_out" => Some("I/O 処理が..."),  // or-pattern (2 codes)
        // ... 中略 ...
        "subprocess.cancelled" => None,  // None entry
        "internal.error" => None,         // None entry
        _ => None,
    }
}
```

合計 **24 codes** (22 hint entries + 2 None entries、or-pattern を展開済)。Source of truth は error.rs (docstring に「本 fn が source of truth、docs は mirror」と明記)。

`docs/tauri-commands.md` §「AppError default hint mapping (`gui/src-tauri/src/error.rs::default_hint_for_code`)」 table (現行、抜粋):

```markdown
| code | hint |
| ... | ... |
| `state.mtime_conflict` | metadata.json が他の... |
| `io.would_block` | I/O 処理が... |
| `io.timed_out` | I/O 処理が... |
| `subprocess.cancelled` | (hint なし: ユーザー操作によるキャンセルは UI 側で十分な情報を出す) |
| `internal.error` | (hint なし: 内部エラーで具体的アクションがない、message 側で logs 参照を案内) |
```

実装時の前提確認 (writing-plans 段階): docs table で or-pattern が **2 行に展開** されているか **1 行併記** か (`grep` で実物確認)。awk parser はどちらでも対応する設計 (§3.3)。

### §3.2 改修方針 (Q3 (a) Bash + awk + Q4 (a) 文言完全一致 + None 含む)

`.github/scripts/check-error-hint-drift.sh` を新規作成し、`.github/workflows/ci.yml` に `doc-error-hint-drift` job を追加。`doc-tauri-commands-drift` (既存 ci.yml:157、参照: [PR #689](https://github.com/Idios/kobutachan-allaganeye/pull/689) Round 1 で確立) と同じ **awk + sort -u + diff -u pattern** を踏襲。

**抽出 pair 形式**: `<code>\t<hint_normalized>`

- code: ``` `<code>` ``` の backtick を剥がした文字列
- hint: 下記 normalize 適用後の文字列
- None entries: hint = sentinel `<<NONE>>`

**normalize ルール** (両 side 同じ規則):

- whitespace 縮約 (連続 space → 1 space)
- 改行 → space (multi-line hint 対応)
- 前後 trim
- quote (`"`) / カッコ / 「」はそのまま保持 (両 side で同形式前提)
- None sentinel:
  - error.rs `=> None,` の arm → `<<NONE>>`
  - docs `(hint なし: ...)` で始まる cell → `<<NONE>>`

**比較**: 両 pair set を sort して diff -u、差分行があれば exit 1。

### §3.3 実装構造

awk parser を 2 file に外出しする (script-内 inline awk は or-pattern + None で複雑化するため可読性優先、本 spec §9 トレードオフ参照):

```text
.github/scripts/
├── check-error-hint-drift.sh         (新規、メイン)
├── extract-rust-hints.awk            (新規、error.rs parser)
└── extract-doc-hints.awk             (新規、tauri-commands.md parser)
```

#### §3.3.1 `check-error-hint-drift.sh` (擬似コード)

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUST_FILE="gui/src-tauri/src/error.rs"
DOC_FILE="docs/tauri-commands.md"

extract_rust_pairs() {
  awk -f "$SCRIPT_DIR/extract-rust-hints.awk" "$RUST_FILE"
}

extract_doc_pairs() {
  awk -f "$SCRIPT_DIR/extract-doc-hints.awk" "$DOC_FILE"
}

if ! diff -u \
    <(extract_rust_pairs | sort) \
    <(extract_doc_pairs | sort); then
  cat >&2 <<'EOF'

ERROR: error.rs ↔ docs/tauri-commands.md hint drift detected.

Source of truth: gui/src-tauri/src/error.rs::default_hint_for_code
Mirror:          docs/tauri-commands.md §「AppError default hint mapping」 table

Both must be updated in the same PR. See docs/tauri-commands.md docstring +
gui/src-tauri/src/error.rs::default_hint_for_code docstring for the contract.
EOF
  exit 1
fi
```

#### §3.3.2 `extract-rust-hints.awk` (擬似コード)

```awk
# fn default_hint_for_code の match arm を (code, hint) pair に展開
# or-pattern: "a" | "b" => Some("...") → 2 行に展開
# None entry: "c" => None, → c<TAB><<NONE>>

BEGIN { in_fn = 0 }
/^fn default_hint_for_code/ { in_fn = 1; next }
in_fn && /^\}/ { in_fn = 0; exit }

in_fn && /=>/ {
  # 左辺: "code1" | "code2" | ... (or-pattern)
  # 右辺: Some("hint") | None
  # multi-line hint も catch (continuation line で =>) — 実装時に対応
  split_or_pattern_into_codes(...)
  if (right_side ~ /None/) hint = "<<NONE>>"
  else                     hint = normalize(extract_some_arg(...))
  for (c in codes) print c "\t" hint
}
```

#### §3.3.3 `extract-doc-hints.awk` (擬似コード)

```awk
# ## AppError default hint mapping section 内の table row を (code, hint) pair に展開
# `| `code` | hint |` → code<TAB>hint
# `| `code` | (hint なし: ...) |` → code<TAB><<NONE>>

BEGIN { in_section = 0 }
/^## AppError default hint mapping/ { in_section = 1; next }
in_section && /^## / && !/^## AppError default hint mapping/ { in_section = 0; exit }

in_section && /^\| `[^`]+` \|/ {
  # parse table row
  # extract code from `...` and hint from cell after second |
  code = extract_code_backticked(...)
  raw_hint = extract_second_cell(...)
  if (raw_hint ~ /^\(hint なし:/) hint = "<<NONE>>"
  else                            hint = normalize(raw_hint)
  print code "\t" hint
}
```

#### §3.3.4 `.github/workflows/ci.yml` job 追加

`doc-tauri-commands-drift` と相似形:

```yaml
  doc-error-hint-drift:
    name: docs ↔ error.rs hint drift check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Check error.rs ↔ docs/tauri-commands.md hint drift
        run: bash .github/scripts/check-error-hint-drift.sh
```

### §3.4 TDD red→green 検証

1. **(red 1: 文言変更)** docs の 1 hint cell を故意に文言変更 (例: `io.file_not_found` の「パスを確認」→「パスを再確認」)
2. local: `bash .github/scripts/check-error-hint-drift.sh` → exit 1 + diff 出力確認
3. **(green)** 上記変更を revert
4. local 再実行 → exit 0
5. **(red 2: or-pattern code 削除)** docs から `io.timed_out` 行を削除 → exit 1 (`io.timed_out` が error.rs 側にあるが docs 側にない)
6. revert → exit 0
7. **(red 3: None sentinel 変更)** docs の `subprocess.cancelled` cell を `(hint なし: ...)` から実際の文言 (例: "キャンセルされました") に変更 → exit 1 (sentinel mismatch)
8. revert → exit 0
9. **(CI 確認)** PR-1 で `doc-error-hint-drift` job が green であることを確認 (drift なし状態)

検証エビデンスは PR-1 の commit log + Self-Test Report (§7.5) に記述。

### §3.5 受け入れ条件 → §3 対応

| # | issue [#692](https://github.com/Idios/kobutachan-allaganeye/issues/692) 受け入れ条件 | 対応 |
| --- | --- | --- |
| 1 | error.rs から (code, hint) 抽出 script | §3.3.2 `extract-rust-hints.awk` |
| 2 | docs/tauri-commands.md から (code, hint) 抽出 script | §3.3.3 `extract-doc-hints.awk` |
| 3 | sort + diff -u で drift → CI fail | §3.3.1 `check-error-hint-drift.sh` + §3.3.4 ci.yml job |
| 4 | or-pattern / None entries の handling | §3.2 normalize + §3.4 red 2/3 で検証 |
| 5 | 故意 drift → red → fix → green の TDD 検証 | §3.4 手順 |

## §4 #700 markdownlint nested ignore

### §4.1 現状

`.markdownlint-cli2.yaml:43-52`:

```yaml
globs:
  - "**/*.md"

ignores:
  - "node_modules/**"
  - ".venv/**"
  - ".git/**"
  - ".pytest_cache/**"
  - ".ruff_cache/**"
  - "**/kobutachan_allaganeye.egg-info/**"
```

`markdownlint-cli2` の glob 仕様: `node_modules/**` は cwd 直下の `node_modules/` のみ match、nested `gui/node_modules/**` には未到達。`cd gui && npm install` 後の `bash scripts/check-markdownlint.sh` で 7712 errors が誤報告される (issue [#700](https://github.com/Idios/kobutachan-allaganeye/issues/700) 本文)。

CI は `npm install` を実行しないため `gui/node_modules/` 不在、CI 挙動には影響なし。dev 体験のみ阻害。

### §4.2 修正方針

`.markdownlint-cli2.yaml` の `ignores` に `**/node_modules/**` を追加 (issue 本文の推奨案、併記で安全):

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

### §4.3 検証手順

1. **(pre)** `cd gui && npm install` で `gui/node_modules/` を生成
2. **(red)** `bash scripts/check-markdownlint.sh` → 7712 errors (issue 報告通り)
3. **(green)** `.markdownlint-cli2.yaml` を §4.2 修正
4. **(verify)** `bash scripts/check-markdownlint.sh` → 0 errors
5. **(CI 無影響確認)** CI の `markdownlint` job が引き続き pass (CI は `npm install` を実行しないため `gui/node_modules/` 不在、挙動変化なし)

### §4.4 受け入れ条件 → §4 対応

| # | issue [#700](https://github.com/Idios/kobutachan-allaganeye/issues/700) 受け入れ条件 | 対応 |
| --- | --- | --- |
| 1 | `.markdownlint-cli2.yaml` の ignores glob 修正 | §4.2 (1 行追加) |
| 2 | `gui/node_modules/**/*.md` の誤検出 7712 → 0 | §4.3 step 4 |
| 3 | CI markdownlint job pass 維持 | §4.3 step 5 |

## §5 roadmap doc adjustment

### §5.1 修正対象 4 ヶ所 + 関連 design doc 2 ヶ所

[`docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md`](../plans/2026-05-11-l2-v020-roadmap-update.md) の Lane IV-b' 関連記述を 2 件 / 2 章 (#692 / #700) に縮小、#458 は handoff として明記:

| 行 (現在) | 現状 | 修正後 |
| --- | --- | --- |
| 81 | `**並行安全度**: high (...) / **brainstorming 単位**: Lane IV-b' で Group J と統合 (1 spec / 3 章)` | `...1 spec / 2 章 (#458 は scope-out、release gate 後 /close-issue で handoff)` |
| 110 | `#458 (P2、bug_report.yml) // #692 ... // #700 ...` | `#692 ... // #700 ...` + Lane 説明文に「#458 は scope-out、release gate 後 handoff」を脚注追加 |
| 162 | `#458 // #692 // #700` (Wave 1 ASCII 図内) | `#692 // #700` + `(#458 deferred、release gate 後 handoff)` を 1 行追加 |
| 200 | `/superpowers:brainstorming Lane IV-b': Group G #458 + Group J #692 #700 ...` | `/superpowers:brainstorming Lane IV-b': Group J #692 #700 (workflow / CI / docs polish、#458 は release gate 後 handoff)` |
| §4 deferred 表 (255-) | (記述なし) | 「#458 は Lane IV-b' から scope-out、release gate 後 L3 初期に UI 実測 → close 予定 (handoff path)」を 1 行追記 |

更に同 spec の base [`docs/superpowers/specs/2026-05-11-l2-v020-roadmap-update-design.md`](2026-05-11-l2-v020-roadmap-update-design.md) の同等 4 ヶ所 (§4.1 Group G 行 / §4.2 Lane IV-b' 行 / §4.3 file matrix 行 / §4.6 brainstorming 入り口) も整合修正。

実装時は writing-plans フェーズで `grep -n "Lane IV-b'\|Lane IV-b prime\|#458"` で全 hit を確認し、本 §5.1 表の修正方針に従って一括修正する。

### §5.2 同梱 PR (#692 PR-1)

roadmap doc 修正は **PR-1 (#692、mid-weight) に同梱** する (Q1-Q2 + brainstorming session で確定)。PR-2 (#700) は config 1 行修正で trivial、roadmap doc を別 PR にする利益が薄い。

### §5.3 scope creep 警戒の透明化

Iron Law 3 (1 PR = 1 scope) に従えば、roadmap doc 修正は厳密には `#692` issue scope の外にあるが、本 brainstorming session で確定した「Lane IV-b' scope 縮小」という **事実訂正** の性格を持つ:

- 新規 issue 起票するほどの規模ではない (4 行修正 × 2 file)
- Lane IV-b' に紐づく実装 PR で扱うのが trace 上自然
- 別 PR にすると "roadmap doc 修正だけの PR" が発生し PR 数増

このため本 spec doc § で「Lane IV-b' 事実訂正 = Lane IV-b' scope 内」と判断する。PR-1 本文 `## スコープ` 節に明示し透明化する (§6.1)。

## §6 PR 統合方針 + 受け入れ条件統合

### §6.1 PR 構成 (Q2 (a) 2 並行 PR)

#### PR-1 (#692 hint drift CI、mid-weight)

```text
title: feat(ci): error.rs hint table drift check job 追加 (Refs #692)

body 内 scope 宣言:
  ## スコープ

  Lane IV-b' (Group J #692 hint drift CI) を実装:

  - .github/scripts/check-error-hint-drift.sh + 2 awk file (extract-rust-hints.awk
    / extract-doc-hints.awk) 新規作成
  - .github/workflows/ci.yml に doc-error-hint-drift job 追加 (doc-tauri-commands-drift
    precedent 踏襲)
  - ci.yml に shellcheck job 新規追加 (repo 全体 .sh 対象、§7.4)

  加えて、本 brainstorming session で確定した Lane IV-b' scope 縮小 (#458 scope-out、
  release gate 後 handoff) を docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md
  + docs/superpowers/specs/2026-05-11-l2-v020-roadmap-update-design.md に反映する
  fact 訂正修正を同梱 (§5)。

  本 Lane IV-b' spec doc も新規追加: docs/superpowers/specs/2026-05-11-lane-iv-b-prime-design.md

  Refs #692
```

#### PR-2 (#700 markdownlint nested ignore、light)

```text
title: fix(markdownlint): nested gui/node_modules を ignore に追加 (Refs #700)

body 内 scope 宣言:
  ## スコープ

  Lane IV-b' (Group J #700 markdownlint nested ignore) を実装:

  - .markdownlint-cli2.yaml の ignores に **/node_modules/** を追加 (1 行)
  - 検証: bash scripts/check-markdownlint.sh で 7712 → 0

  spec doc は PR-1 に同梱: docs/superpowers/specs/2026-05-11-lane-iv-b-prime-design.md §4

  Refs #700
```

**merge 順序**: 依存なし、どちらが先でも OK。並行レビュー / merge 可。

### §6.2 受け入れ条件統合 (各 PR 本文)

PR-1 本文 `## 受け入れ条件`:

```markdown
## 受け入れ条件 (#692)

- [x] error.rs から (code, hint) 抽出 script (.github/scripts/extract-rust-hints.awk)
- [x] docs/tauri-commands.md から (code, hint) 抽出 script (.github/scripts/extract-doc-hints.awk)
- [x] sort + diff -u で drift → CI fail (ci.yml に doc-error-hint-drift job 追加)
- [x] or-pattern (io.would_block | io.timed_out) / None entries (subprocess.cancelled / internal.error) の handling
- [x] 故意 drift → red → fix → green の TDD 検証 (commit log + Self-Test Report で記録)
```

PR-2 本文 `## 受け入れ条件`:

```markdown
## 受け入れ条件 (#700)

- [x] .markdownlint-cli2.yaml の ignores glob 修正
- [x] gui/node_modules/**/*.md の誤検出 7712 → 0 (local 検証済)
- [x] CI markdownlint job pass 維持 (npm install 不要のため挙動変化なし)
```

### §6.3 chicken-and-egg 回避

本 lane の各 PR 本文に `- [ ]` を含めない (旧 `pr-checklist.yml` 全文 grep 仕様は PR [#688](https://github.com/Idios/kobutachan-allaganeye/pull/688) で section-aware 化済だが、安全マージンとして受け入れ条件は全件 `[x]` で書く)。

### §6.4 Iron Law 整合

| Iron Law | 担保 |
| --- | --- |
| Law 1 (受け入れ条件全件チェック) | PR 各々の §6.2 で逐条 |
| Law 2 (bulk 操作 AskUserQuestion) | 2 PR merge 後の close は `/close-issue` skill で個別実施 (各 PR ↔ 1 issue 1:1、Iron Law 2 bulk 該当せず) |
| Law 3 (1 PR = 1 scope) | PR-1 = 「Lane IV-b' #692 hint drift CI + Lane IV-b' scope 確定 (fact 訂正)」で 1 scope / PR-2 = 「Lane IV-b' #700 markdownlint nested ignore」で 1 scope。scope creep 透明化は §5.3 |
| Law 4 (Closes 禁止) | 両 PR とも `Refs #N` のみ |
| Law 5 (曖昧点 AskUserQuestion) | brainstorming session で Q1-Q6 の 6 質問を実施 (本 spec session メタ参照) |
| Law 6 (PR 作成 Pre-flight) | `git fetch origin develop-0.2.0` + 取り込み未済 commit 確認 + 並行 worktree PR 重複確認を各 PR 作成直前に実施 (§8.1 step 5) |

## §7 Test

### §7.1 #692 検証

- **awk parser TDD**: §3.4 の red→green 手順 (故意 drift × 3 ケース: 文言変更 / or-pattern 1 code 削除 / None sentinel 変更) を local で実施、commit log + Self-Test Report に検証エビデンスを残す
- **CI 統合確認**: PR-1 の CI で `doc-error-hint-drift` job が pass することを確認 (drift なし状態)
- **shellcheck**: 本 lane で追加する `.github/scripts/check-error-hint-drift.sh` + 既存 `scripts/check-markdownlint.sh` / `scripts/cleanup-worktrees.sh` の shellcheck pass を確認 (§7.4 で詳細)
- **awk script の portability**: bash + awk (GNU awk 前提) は ci.yml `runs-on: ubuntu-latest` で動作確認、Windows / macOS local 実行は範囲外 (CI で完結する設計)

### §7.2 #700 検証

§4.3 手順 (pre-install → red → green → CI 無影響確認) を local で実施。本 lane の changed file が `.md` を含むため、PR-1 / PR-2 とも `bash scripts/check-markdownlint.sh` で 0 errors を確認。

### §7.3 自動チェック (path 別)

本 lane の変更 path:

- PR-1:
  - `.github/scripts/check-error-hint-drift.sh` (新規)
  - `.github/scripts/extract-rust-hints.awk` (新規)
  - `.github/scripts/extract-doc-hints.awk` (新規)
  - `.github/workflows/ci.yml` (更新: drift job + shellcheck job 追加)
  - `docs/superpowers/specs/2026-05-11-lane-iv-b-prime-design.md` (新規、本 spec)
  - `docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md` (更新: §5)
  - `docs/superpowers/specs/2026-05-11-l2-v020-roadmap-update-design.md` (更新: §5)
- PR-2:
  - `.markdownlint-cli2.yaml` (更新: 1 行追加)

必要チェック:

- ✓ markdownlint (`bash scripts/check-markdownlint.sh`、PR-1 / PR-2 とも)
- ✓ shellcheck (PR-1 のみ、`.github/scripts/*.sh` + `scripts/*.sh`、§7.4)
- ✓ ci.yml の syntax (GitHub Actions が自動)
- ✗ Python (`ruff` / `pyright` / `pytest`) — touch なし
- ✗ GUI (`npm run lint` / `typecheck` / `test` / `build` / `cargo check`) — touch なし

### §7.4 shellcheck job (新規、PR-1)

Q5 確定: ci.yml に `shellcheck` job を新規追加、対象は **repo 全体の .sh** (`.github/scripts/*.sh` + `scripts/*.sh`)。

#### §7.4.1 想定 ci.yml step

```yaml
  shellcheck:
    name: shellcheck (.github/scripts + scripts)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run shellcheck
        uses: ludeeus/action-shellcheck@master
        with:
          severity: warning
          scandir: '.'
          additional_files: |
            .github/scripts/check-error-hint-drift.sh
            scripts/check-markdownlint.sh
            scripts/cleanup-worktrees.sh
```

または equivalent な `apt-get install shellcheck && shellcheck **/*.sh` step。実装時に既存 CI の style (ludeeus/action-shellcheck vs `apt-get` 直接) を確認し統一する (writing-plans 段階で精査)。

#### §7.4.2 既存 script の shellcheck pass 状況確認

実装時に local で `shellcheck scripts/check-markdownlint.sh scripts/cleanup-worktrees.sh` を実行し pass 状況を確認:

- **pass する場合**: shellcheck job をそのまま追加して PR-1 commit
- **pass しない場合 (warning 1-3 件程度)**: 本 PR 内で軽微修正 (shellcheck pragma 追加 or quote 修正等)。scope creep 透明化は PR-1 本文に追記
- **pass しない場合 (多数 / structural 修正必要)**: 本 PR から shellcheck job を一旦外し、別 issue 起票で対応。`AskUserQuestion` で Idios に判断を仰ぐ (Iron Law 5)

### §7.5 Self-Test Report 規約 (`docs/l2-workflow.md`)

- **machine-verified** (`[x]`):
  - markdownlint pass (両 PR)
  - shellcheck pass (PR-1)
  - drift check CI job green (PR-1)
  - red→green TDD (PR-1、commit log + report)
  - `gui/node_modules/` の `cd gui && npm install` 後の 7712 → 0 (PR-2)
- **machine-unverifiable** (plain bullet `-`):
  - 該当なし (CI workflow / lint config / docs のみの変更、GPU / audio / video detector / GUI Tauri touch なし)

Self-Test Report の `### 実機検証 (machine-unverifiable)` 節は plain bullet `-` で「該当なし」と記述する。

## §8 Rollout

### §8.1 実装順序

```text
1. 本 spec を docs/superpowers/specs/2026-05-11-lane-iv-b-prime-design.md に commit
   (本 brainstorming session の終端、writing-plans 起動前)

2. /superpowers:writing-plans 起動
   → docs/superpowers/plans/2026-05-11-lane-iv-b-prime-implementation.md 作成

3. PR-1 (#692) 実装:
   a. 本 spec doc 新規追加
   b. roadmap doc + 同 design doc の §5.1 表通り 4 ヶ所修正
      (plan.md + design.md の両 file、grep -n "Lane IV-b'\|#458" で hit 確認)
   c. awk script 2 file 作成 (extract-rust-hints.awk / extract-doc-hints.awk)
   d. メイン bash script (.github/scripts/check-error-hint-drift.sh)
   e. ci.yml に doc-error-hint-drift job 追加
   f. ci.yml に shellcheck job 追加 (§7.4.1)
   g. local 検証: shellcheck repo 全体 .sh pass (§7.4.2 で多数失敗時は別判断)
   h. TDD red→green 検証 (§3.4)

4. PR-2 (#700) 実装:
   a. .markdownlint-cli2.yaml 1 行追加
   b. local 検証 (§4.3)

5. Iron Law 6 PR Pre-flight (各 PR 作成直前):
   - git fetch origin develop-0.2.0 && git log HEAD..origin/develop-0.2.0 --oneline
   - 取り込み未済 commit ある場合 → git merge origin/develop-0.2.0 + 自動チェック再実行
   - gh pr list --search "#692|#700|Lane IV-b" --state all で並行 worktree PR 重複確認

6. PR-1 / PR-2 並行作成 (依存なし)
   - 本文は printf | gh pr create --body-file - で渡す (memory feedback_gh_command_ja_heredoc.md)

7. /iterate-review で各 PR review-fix ループ (subagent dispatch + collapse)

8. CI 確認 (各 PR で markdownlint / shellcheck / drift job / 既存 job 全 green)

9. merge (並行 OK、依存なし)

10. /close-issue skill で各 issue 個別 close:
    - #692: 全項目検証 → close
    - #700: 全項目検証 → close
    - #458: 本 lane 対象外 (release gate 後 L3 初期 handoff、本 lane では touch なし)
```

### §8.2 着手順序の根拠

- **PR-1 を先**: spec doc を PR-1 に同梱するため、spec が確定する PR-1 を先行。PR-2 は spec の §4 を Refs して作成
- **PR-2 を後**: config 1 行修正で trivial、PR-1 完了後に立てる方が PR-1 のレビュー集中度高い (同 session で順次着手)
- **merge 順序は任意**: 依存なし、レビュー先着優先

## §9 トレードオフ整理

| 設計ポイント | 選択 | リスク | 緩和 |
| --- | --- | --- | --- |
| #458 を本 lane に含めるか | scope-out (Q1) | roadmap doc の Lane IV-b' エントリと事実乖離 | §5 で roadmap doc 4 ヶ所修正、handoff path を spec + doc に明記 |
| PR 統合 vs 並行 | 2 並行 PR (Q2) | 並行 worktree PR 重複リスク | Iron Law 6 Pre-flight で `gh pr list` 確認、依存なし設計 |
| awk script 言語 | bash + awk (Q3) | bash 経験差で可読性低下 | precedent `doc-tauri-commands-drift` と style 統一、awk 外出しで複雑性緩和 |
| drift 照合範囲 | (code, hint) 文言完全一致 + None (Q4) | 文言の whitespace / 改行 normalize miss で false positive | §3.2 normalize ルール明示、§3.4 red 3 ケースで検証 |
| awk script の外出し | `.github/scripts/extract-*.awk` 2 file | precedent は inline awk | 本 task は or-pattern + None で複雑、可読性優先、`doc-tauri-commands-drift` と style 多少不一致は許容 |
| None sentinel `<<NONE>>` | sentinel 方式 | docs `(hint なし: ...)` 説明文との bridging | drift check 前処理で sentinel 変換、docs 本体は人間向け情報量を保持 |
| spec doc の場所 | PR-1 (mid-weight) に同梱 | PR-2 だけ見た人は spec 文脈不明 | PR-2 本文に spec doc への link を明記 (§6.1) |
| roadmap doc 修正の PR | PR-1 に同梱 | Iron Law 3 scope creep 警戒 | §5.3 で「Lane IV-b' 事実訂正 = scope 内」を明示、PR-1 本文に透明化 |
| shellcheck job 対象 | repo 全体 .sh (Q5) | 既存 script が pass しない場合 scope 拡大 | §7.4.2 で local 事前確認、多数失敗時は AskUserQuestion で判断 |
| spec doc file 名日付 | 2026-05-11 (session 実施日、Q6) | commit 日と乖離する場合あり | precedent (`2026-05-08-lane-iv-b-group-g-design.md`) と整合、trace しやすい |

## §10 Memory feedback / 関連 doc / Iron Law 整合

> Iron Law 整合は §6.4 を参照 (本節では重複させない)。

### §10.1 Memory feedback 適用

- `feedback_gh_command_ja_heredoc.md`: 各 PR 本文 (日本語) は `printf | gh pr create --body-file -` または HEREDOC で渡す
- `feedback_msys_path_conv_git_show.md`: bash tool 経由 `git show <rev>:<path>` は `MSYS_NO_PATHCONV=1` prefix (実装中 spec 確認で参照する場合)
- `feedback_powershell_native_redirect.md`: 本 lane の CI は `runs-on: ubuntu-latest` + bash のため適用外。Windows local 検証時の参考としてのみ保持
- `feedback_skill_revision_empirical.md`: 本 lane は skill 改訂なしのため適用外
- `feedback_taskstop_child_process_leak.md`: 本 lane では `run_in_background` 利用なし、念のため writing-plans 時に subagent dispatch があれば再確認

### §10.2 関連 doc

- [`docs/l2-workflow.md`](../../l2-workflow.md) — PR Pre-flight / Self-Test Report / (A) PR 内修正優先 / 実機検証 trigger
- [`docs/tauri-commands.md`](../../tauri-commands.md) §「AppError default hint mapping」 — #692 drift check 対象 (mirror 側)
- [`gui/src-tauri/src/error.rs`](../../../gui/src-tauri/src/error.rs) — #692 drift check 対象 (source of truth 側)
- [`.markdownlint-cli2.yaml`](../../../.markdownlint-cli2.yaml) — #700 修正対象
- [`.github/workflows/ci.yml`](../../../.github/workflows/ci.yml) §`doc-tauri-commands-drift` — #692 precedent
- [`docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md`](../plans/2026-05-11-l2-v020-roadmap-update.md) — Lane IV-b' エントリ (本 lane で §5 修正)
- [`docs/superpowers/specs/2026-05-11-l2-v020-roadmap-update-design.md`](2026-05-11-l2-v020-roadmap-update-design.md) — 同上 (§5 修正)
- [`docs/superpowers/specs/2026-05-08-lane-iv-b-group-g-design.md`](2026-05-08-lane-iv-b-group-g-design.md) — Wave 0 Lane IV-b spec (#624 / #458 / #682)、本 lane (Lane IV-b') の precedent
- [`.claude/hooks/session-start.sh`](../../../.claude/hooks/session-start.sh) — Iron Law の正
