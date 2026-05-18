# v0.3.0 docs cleanup + 新 L3 整合性監査 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** v0.3.0 開発期間中の doc 整理として、3 件の P3 deferred doc issue ([#634](https://github.com/Idios/kobutachan-allaganeye/issues/634) / [#635](https://github.com/Idios/kobutachan-allaganeye/issues/635) / [#654](https://github.com/Idios/kobutachan-allaganeye/issues/654)) を消化し、新 L3 redefinition (PR [#776](https://github.com/Idios/kobutachan-allaganeye/pull/776)) 後の active docs 整合性を網羅監査し、不要 doc / source を triage する。

**Architecture:** Phase 0 (read-only audit) → Phase 1 (triage via AskUserQuestion) → Phase 2 (3 件 doc fix 実装) → Phase 3 (conditional audit-derived fix) → PR submission with Iron Law 6 Pre-flight. 全 docs only / 1 PR / base = `develop-0.3.0`。詳細 spec は [`docs/superpowers/specs/2026-05-18-v030-docs-cleanup-l3-audit-design.md`](../specs/2026-05-18-v030-docs-cleanup-l3-audit-design.md)。

**Tech Stack:**

- Markdown (docs editing — primary deliverable)
- `gh` CLI 2.x (PR 作成 + Pre-flight Step 0/4)
- `bash scripts/check-markdownlint.sh` (markdownlint via CI と同 version)
- `git` (Iron Law 6 Pre-flight + commit workflow)
- Codex `/codex:adversarial-review` (Pre-flight Step 5)

---

## File Structure

### Files modified (確定)

| Path | 由来 | 責務 |
| --- | --- | --- |
| `docs/output-spec.md` | #654 + #634 | `:117` Closed Issue 一覧の `#388` 行更新 + matrix v2 click-level error 行追加 |
| `docs/cli-spec.md` | #634 | §「エラー表示」に click-level option-parse error サブセクション追加 |
| `docs/l2-workflow.md` | #635 | §「PR 作成ルール」 から §「Self-Test Report 規約」 への cross-link 追加 |

### Files modified (条件付き、Phase 1 triage 結果による)

| Path | 条件 |
| --- | --- |
| 他 active docs | Phase 0A finding (a) triage で同 PR 修正と決定された場合 (期待値 0 件) |
| broken link / orphan を持つ doc | Phase 0B-doc finding (a) triage で同 PR 修正と決定された場合 |
| `.github/pull_request_template.md` | #635 選択肢 R 採用時 (Phase 2.3 で AskUserQuestion 確定) |

### Files NOT modified (明示)

| Path | 理由 |
| --- | --- |
| `docs/superpowers/specs/*.md` / `docs/superpowers/plans/*.md` (既存 archive) | §4.1 文脈保存ルール (PR [#776](https://github.com/Idios/kobutachan-allaganeye/pull/776) spec で確定) |
| `allaganeye/**/*.py` / `gui/src/**` / `gui/src-tauri/**` 本体 | docs only PR。`DEPRECATED` 等の grep 結果は triage で別 issue 化 |

### Files NOT created

本 plan ではテストコード新規作成なし (docs only)。検証は markdownlint / Grep / 視覚的 review で実施。

---

## PR Organization

| 項目 | 値 |
| --- | --- |
| PR タイトル (確定) | `docs: v0.3.0 P3 deferred doc cleanup (#634 #635 #654) + L3 整合性監査 + 不要整理` |
| base ブランチ | `develop-0.3.0` |
| Iron Law 6 Pre-flight | 必須 (Step 0 / Step 1-4 / Step 5 `/codex:adversarial-review`) |
| Closes キーワード | **禁止** (Iron Law 4)。マージ後 `/close-issue` skill で手動 close |
| 実機検証 | 不要 (docs only) |
| 自動チェック | markdownlint のみ ([`scripts/check-markdownlint.sh`](../../scripts/check-markdownlint.sh)) |

---

## Wave A: Phase 0 監査 (read-only investigation)

> 出力は **findings table**。`docs/superpowers/specs/2026-05-18-v030-docs-cleanup-l3-audit-design.md` §6 参照。

### Task A1: L3 整合性 grep (active docs 全件)

**Files:**

- Read: `CLAUDE.md`, `README.md`, `docs/*.md` (`docs/superpowers/` を除く), `.github/**/*.{md,yml}`, `.claude/skills/**/*.md`, `.claude/hooks/**`
- Output: findings table (memo, 後で PR body へ転載)

- [ ] **Step 1: Grep "L3" in CLAUDE.md / README.md**

Use Grep tool:

```text
pattern: L3
path: CLAUDE.md
output_mode: content
-n: true
```

```text
pattern: L3
path: README.md
output_mode: content
-n: true
```

Expected: CLAUDE.md は §段階的アーキテクチャ の layer table のみ (新 L3 + L4 (former L3) を含む正しい行)。README.md は 0 件 (PR #776 で ロードマップ削除済)。

- [ ] **Step 2: Grep "L3" in docs/*.md (superpowers/ 除外)**

Use Grep tool:

```text
pattern: L3
path: docs
glob: *.md
output_mode: content
-n: true
head_limit: 200
```

期待されるヒット (smoke check 時点で確認済): `docs/issue-policy.md` / `docs/ui-interaction-spec.md` (false positive `#L399`) / `docs/cli-spec.md:205` / `docs/design-overview.md` / `docs/l2-workflow.md:538,540` (memory tier 用法) / `docs/testing-guide.md` / `docs/reference-videos.md` / `docs/release-process.md`。

`docs/superpowers/` 配下のヒットは出力に含まれる場合があるが、§4.1 文脈保存ルールで本 plan の対象外なので分類時に除外。

- [ ] **Step 3: Grep "L3" in .github/ + .claude/skills/ + .claude/hooks/**

Use Grep tool:

```text
pattern: L3
path: .github
output_mode: content
-n: true
```

```text
pattern: L3
path: .claude/skills
output_mode: content
-n: true
```

```text
pattern: L3
path: .claude/hooks
output_mode: content
-n: true
```

Expected: `.github/` は 0 件 (smoke check 確認済)。`.claude/skills/` / `.claude/hooks/` の出力を収集。

- [ ] **Step 4: 各 hit を 3 区分に分類**

各 hit を以下に分類して memo に記録:

- **(i) 新 L3 として正しい**: `L3` 単独表記が文脈 (v0.3.0 / VTuber / minimap / perf) で新 L3 と確定できる
- **(ii) `L4 (former L3)` ナミング適用済**: 旧 L3 (= 新 L4) を指す箇所が `L4 (former L3, …)` ナミングで書かれている
- **(iii) ambiguous (要修正)**: 新旧不明 / `L3 初期` 等の時間表現で意図不明 / layer table 不一致 / false positive

各 hit について `<path>:<line>: <classification> — <one-line 根拠>` 形式の table エントリを作る。

Memo 出力形式 (例):

```text
| file:line | mention | classification | 根拠 |
| --- | --- | --- | --- |
| docs/issue-policy.md:48 | "L3 以降のレイヤーは…" | (i) | "新 L3" と次行で明示 |
| docs/cli-spec.md:205 | "L4 (former L3, メタデータ化)" | (ii) | ナミング正しい |
| docs/ui-interaction-spec.md:997 | "#L399" | (iii) false-positive | TSX line ref、layer ではない |
```

期待値: (i) と (ii) のみ。(iii) は 0 件。

- [ ] **Step 5: Memo に Phase 0A findings table を保存**

memo 上に table を構造化して保存。Phase 1 triage と PR body 記載で使う。

(コミット不要 — read-only audit)

### Task A2: Layer table 行単位照合 (CLAUDE.md / design-overview.md / release-process.md)

**Files:**

- Read: `CLAUDE.md`, `docs/design-overview.md`, `docs/release-process.md`

- [ ] **Step 1: Read CLAUDE.md §段階的アーキテクチャ**

Use Read tool:

```text
file_path: CLAUDE.md
limit: 50
```

§段階的アーキテクチャ のテーブル行 (L1 〜 L7) を抽出して memo に貼る。

期待行例:

```text
| L1: 試合分割 | … | リリース済み (…) |
| L2: 配布・統合 | … | 開発中 |
| L3 (new): 配信形式対応 + 性能改善 | … | 開発中 (v0.3.0 target) |
| L4 (former L3): メタデータ化 | … | 未着手 |
| L5 (former L4): 価値評価 | … | 未着手 |
| L6 (former L5): 自動編集 | … | 未着手 |
| L7 (former L6): プライバシー・精密分割 | … | 計画中 |
```

- [ ] **Step 2: Read docs/design-overview.md §段階的アーキテクチャ ASCII art**

Use Read tool:

```text
file_path: docs/design-overview.md
limit: 50
```

ASCII art (L1 〜 L7) の各 layer 行を memo に貼る。

- [ ] **Step 3: Read docs/release-process.md Layer-to-version 表**

Use Read tool:

```text
file_path: docs/release-process.md
limit: 40
```

`L3 (new)` / `L4 (former L3)` / `L5 (former L4)` / `L6 (former L5)` / `L7 (former L6)` の roadmap 行を memo に貼る。

- [ ] **Step 4: 3 ファイルの layer 命名一致確認**

各 L1〜L7 の名称が 3 ファイル間で一致しているか行単位で確認。

期待値: 完全一致。差分があれば Phase 0A findings の (iii) に追加して Phase 1 で triage。

Memo 出力形式 (例):

```text
| layer | CLAUDE.md | design-overview.md | release-process.md | 一致? |
| --- | --- | --- | --- | --- |
| L3 | "L3 (new): 配信形式対応 + 性能改善" | "L3 (new): 配信形式対応 + 性能改善" | "L3 (new): 配信形式対応 + 性能改善" | YES |
| L4 | "L4 (former L3): メタデータ化" | "L4 (former L3): メタデータ化" | "L4 (former L3): メタデータ化" | YES |
```

(コミット不要)

### Task A3: §9 Doc mapping table cross-reference

**Files:**

- Read: `docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md` §9

- [ ] **Step 1: Read redefinition spec §9 doc mapping table**

Use Read tool:

```text
file_path: docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md
offset: 260
limit: 50
```

§9.1 Primary / §9.2 Secondary / §9.3 Other / §9 Files NOT touched 一覧を memo に貼る。

- [ ] **Step 2: 各 doc が plan 通りに更新されたか確認**

§9.1 Primary 3 件 (`CLAUDE.md` / `docs/design-overview.md` / `docs/release-process.md`) の更新内容と現状を Grep / Read で照合。差分があれば Phase 0A findings (iii) に追加。

§9.2 Secondary 5 件 (`docs/cli-spec.md` / `docs/l2-workflow.md` / `docs/issue-policy.md` / `docs/reference-videos.md` / `docs/ui-interaction-spec.md`) も同様。

§9.3 Other 1 件 (`docs/testing-guide.md` の §「v0.3.0 L3 work 用 regression baseline」 新節) も確認。

§9 Files NOT touched 2 件 (`docs/l2-workflow.md` の "memory tier" L3 と `docs/ui-interaction-spec.md` の "#L399" TSX line ref) が実際に新 L3 layer と無関係であることを再確認。

(コミット不要)

### Task A4: Phase 0B-doc broken link audit

**Files:**

- Read: `docs/*.md` (`docs/superpowers/` を除く)
- Output: broken-link findings memo

- [ ] **Step 1: Markdown link 全抽出**

Use Grep tool:

```text
pattern: \[.+?\]\(.+?\)
path: docs
glob: *.md
output_mode: content
-n: true
head_limit: 300
multiline: false
```

`docs/superpowers/` を除外するため出力をフィルタ (path 開頭が `docs/superpowers/` のものは捨てる)。

- [ ] **Step 2: link target の sample check**

抽出した link を以下 3 区分に分類:

- 外部 URL (`https://...`): 検証不要
- 相対パス (`./foo.md`, `../foo.md`, `bar.md`): file 存在を Glob で確認
- セクション参照 (`#section-name`, `bar.md#section`): target file 内に該当 heading があるか確認

不存在の link を memo に記録 (`broken-link findings`)。

期待値: 0 件 (smoke check 範囲では発見なし)。

- [ ] **Step 3: §「節参照」 規約準拠の link 検証**

`docs/l2-workflow.md` §「doc 節参照健全性確認」 (line 408+) の規約に従い、`§「<セクション名>」` 形式の参照を抽出:

Use Grep tool:

```text
pattern: §「[^」]+」
path: docs
glob: *.md
output_mode: content
-n: true
head_limit: 200
```

各参照が target doc の `##` / `###` heading と文字列一致するかを sample check。不一致を memo に記録。

(コミット不要)

### Task A5: Phase 0B-doc orphan doc check

**Files:**

- Glob: `docs/*.md`
- Read: 各 doc が参照されているか

- [ ] **Step 1: docs/*.md 全件 list**

Use Glob tool:

```text
pattern: docs/*.md
```

出力 list を memo に保存。`docs/superpowers/` 配下は除外。

- [ ] **Step 2: 各 doc が参照されているか Grep**

各 `docs/<file>.md` について、ファイル名で参照されているか確認:

Use Grep tool (各 file ごとに):

```text
pattern: <filename>.md
path: .
output_mode: count
head_limit: 5
```

`CLAUDE.md` / `README.md` / 他の `docs/*.md` / `.github/` / `.claude/` / `gui/src/` 等から参照されていることを確認。

参照数 0 の doc を **orphan candidates** として memo に記録。

期待値: 0 件 (全 doc が CLAUDE.md / README.md / 他 doc から最低 1 箇所参照されている見込み)。

(コミット不要)

### Task A6: Phase 0B-doc stale info heuristic scan

**Files:**

- Grep: `docs/*.md`

- [ ] **Step 1: Version note pattern grep**

Use Grep tool:

```text
pattern: TBD|TODO: remove after|TODO\s*\(remove
path: docs
glob: *.md
output_mode: content
-n: true
head_limit: 100
```

Use Grep tool:

```text
pattern: \(暫定\)|\(計画中\)|\(未確定\)
path: docs
glob: *.md
output_mode: content
-n: true
head_limit: 100
```

ヒットを memo に保存。

- [ ] **Step 2: Version-specific stale check**

Use Grep tool:

```text
pattern: v0\.1\.[0-9x]|v0\.2\.[0-9x]|v0\.2\.1
path: docs
glob: *.md
output_mode: content
-n: true
head_limit: 200
```

`v0.2.0` / `v0.2.1` リリース済 (commit `983951b` / `22031f6` 確認済) なので、"リリース時に確定" / "TBD" が残っているか確認。

memo に `stale-info findings` を記録。各 finding は以下形式:

```text
| file:line | content | reason (なぜ stale か) |
| --- | --- | --- |
```

(コミット不要)

### Task A7: Phase 0B-src DEPRECATED grep (shallow)

**Files:**

- Grep: `allaganeye/**/*.py`, `gui/src/**/*.{ts,tsx}`, `gui/src-tauri/src/**/*.rs`, `scripts/**`, `.github/scripts/**`

- [ ] **Step 1: Python source DEPRECATED grep**

Use Grep tool:

```text
pattern: DEPRECATED|TODO: remove after|XXX|FIXME: remove
path: allaganeye
glob: *.py
output_mode: content
-n: true
head_limit: 100
```

ヒットを memo に保存。

- [ ] **Step 2: TS/TSX source grep**

Use Grep tool:

```text
pattern: DEPRECATED|TODO: remove after|XXX|FIXME: remove
path: gui/src
output_mode: content
-n: true
head_limit: 100
```

- [ ] **Step 3: Rust source grep**

Use Grep tool:

```text
pattern: DEPRECATED|TODO: remove after|XXX|FIXME: remove
path: gui/src-tauri/src
output_mode: content
-n: true
head_limit: 100
```

- [ ] **Step 4: Scripts grep**

Use Grep tool:

```text
pattern: DEPRECATED|TODO: remove after|XXX|FIXME: remove
path: scripts
output_mode: content
-n: true
head_limit: 50
```

```text
pattern: DEPRECATED|TODO: remove after|XXX|FIXME: remove
path: .github/scripts
output_mode: content
-n: true
head_limit: 50
```

- [ ] **Step 5: Memo に Phase 0B-src findings table を保存**

全 hit を以下形式で memo に保存:

```text
| file:line | mention | comment 内容 | triage 候補 |
| --- | --- | --- | --- |
```

(コミット不要 — read-only)

---

## Wave B: Phase 1 triage

### Task B1: 監査 findings を AskUserQuestion で triage

**Files:**

- Read: Phase 0 で作成した memo (findings table)

- [ ] **Step 1: findings サマリ作成**

Phase 0A / 0B-doc / 0B-src の memo を統合して 1 つの summary table にまとめる。各 finding に ID (e.g., `A1-001`, `B-doc-001`, `B-src-001`) を付与。

期待値: Phase 0A は 0 件 / Phase 0B-doc は 数件以下 / Phase 0B-src は 数件以下。

- [ ] **Step 2: triage の必要性判断**

合計 finding 数:

- 0 件 → Phase 1 skip して Phase 2 へ進む
- 1〜5 件 → 全 finding を 1 つの AskUserQuestion で triage
- 6 件以上 → finding を category 別 (0A / 0B-doc / 0B-src) に分けて複数の AskUserQuestion で triage

- [ ] **Step 3: AskUserQuestion で各 finding を triage**

各 finding に対して以下 3 択を提示:

```text
Q: "<finding ID>: <要約> をどう処理するか?"
Options:
  (a) 本 PR 内で修正 (推奨、scope 内) - description: "diff 数行程度の修正なら同 PR 内で消化"
  (b) 別 issue 起票 - description: "本 PR より大きい / 別 scope / 深い分析が必要"
  (c) skip - description: "false positive / 意図的残置"
```

複数 finding をまとめる場合は multi-question or multi-option を使う。

- [ ] **Step 4: triage 結果を memo に追記**

各 finding に最終決定 (a/b/c) を付記:

```text
| ID | file:line | finding | triage | 備考 |
| --- | --- | --- | --- | --- |
| A1-001 | ... | ... | (a) | Wave D Task D-001 で fix |
| B-doc-001 | ... | ... | (b) | 新 issue 起票 (Wave F 後) |
```

(コミット不要)

---

## Wave C: Phase 2 — 3 件 doc fix 実装

### Task C1: #654 fix (docs/output-spec.md:117 #388 行更新)

**Files:**

- Modify: `docs/output-spec.md` (line 117)

- [ ] **Step 1: 現状の :117 行を Read で確認**

Use Read tool:

```text
file_path: docs/output-spec.md
offset: 115
limit: 5
```

期待: `- [#388](https://github.com/Idios/kobutachan-allaganeye/issues/388) (Filter drop 内訳)`

実際の内容と異なる場合 (smoke check 時点で確認済の形式が変わっている場合) は Phase 1 triage 結果を再評価。

- [ ] **Step 2: row 12 (`:63`) の表現を確認**

Use Read tool:

```text
file_path: docs/output-spec.md
offset: 60
limit: 5
```

row 12 で `(Filter drop 内訳 + unknown match 行)` の表現を確認。本 fix で `:117` を同じ表現に合わせる。

- [ ] **Step 3: :117 行を Edit で書き換え**

Use Edit tool:

```text
file_path: docs/output-spec.md
old_string: - [#388](https://github.com/Idios/kobutachan-allaganeye/issues/388) (Filter drop 内訳)
new_string: - [#388](https://github.com/Idios/kobutachan-allaganeye/issues/388) / [#433](https://github.com/Idios/kobutachan-allaganeye/issues/433) (Filter drop 内訳 + unknown match 行)
```

- [ ] **Step 4: 残骸ゼロ確認**

Use Grep tool:

```text
pattern: \(Filter drop 内訳\)$
path: docs/output-spec.md
output_mode: content
-n: true
```

Expected: 0 hits (`(Filter drop 内訳)` 単独 — 行末 `)` 直前 — が残っていない。`(Filter drop 内訳 + unknown match 行)` 形式のみ残る)。

`#654` 受け入れ条件 (`Grep "Filter drop 内訳"` で残骸ゼロ確認) を充足。

- [ ] **Step 5: markdownlint check**

Run: `bash scripts/check-markdownlint.sh docs/output-spec.md`
Expected: pass (no violation).

violation 出たら fix recipe を `docs/markdownlint-guide.md` で確認して修正。

- [ ] **Step 6: Commit**

```bash
git add docs/output-spec.md
git commit -m "$(cat <<'EOF'
docs(output-spec): :117 Closed Issue 一覧に #433 を反映 (Refs #654)

PR #638 (Refs #433) で row 12 の表現が拡張されたが :117 の対応する
Closed Issue 行に #433 が反映されていなかったため、row 12 と整合させる。

採用形式 (a 行拡張): #388 / #433 (Filter drop 内訳 + unknown match 行)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task C2: #634 prep — allaganeye/cli.py 実装読み合わせ

**Files:**

- Read: `allaganeye/cli.py` (lines 498-574)

- [ ] **Step 1: cli.py の click-level hint 実装を Read で再確認**

Use Read tool:

```text
file_path: allaganeye/cli.py
offset: 495
limit: 85
```

`_suggest_long_option_hint` / `main()` の実装内容を memo に保存:

- どの click error 型を捕捉するか (NoSuchOption / UsageError 等)
- hint 出力フォーマット (`Did you mean --<name>?`)
- stderr に出力か stdout か
- `-v` / `-q` モードでの挙動差

memo 例:

```text
- 捕捉対象: click.exceptions.NoSuchOption (single-dash long-option typo)
- 出力例: `Error: no such option: -version. Did you mean --version?`
- 出力先: stderr
- 終了コード: 5 (設定値不正)
- `-v` / `-q` の影響: traceback 出力なし (click level なので AllaganEyeError 系の verbose hint と独立)
```

`#634` 受け入れ条件 (「doc 修正が `allaganeye/cli.py:498-574` 実装と整合」) のための準備。

(コミット不要 — preparatory read)

### Task C3: #634 fix part 1 — docs/cli-spec.md エラー表示節に click-level subsection 追加

**Files:**

- Modify: `docs/cli-spec.md` (§「エラー表示」、line 376+)

- [ ] **Step 1: cli-spec.md §「エラー表示」 を Read で確認**

Use Read tool:

```text
file_path: docs/cli-spec.md
offset: 370
limit: 60
```

§「エラー表示」 の現状構造 (行 376+ あたりから始まり、`split` / `debug-brightness` を扱う section) を確認。

- [ ] **Step 2: 新規サブセクション "click-level option-parse error" を追加**

§「エラー表示」 の末尾 (`-q` モード出力例の直後) に以下を Edit で追加:

```markdown

### click-level option-parse error (#440 / PR #632)

`split` / `debug-brightness` 等のサブコマンド entrypoint より前で発生する click-level option-parse error (例: `allaganeye -version` のような single-dash long-option typo) は AllaganEyeError 系の `-v` / `-q` 切替制御の対象外。`allaganeye/cli.py:498-574` の `_suggest_long_option_hint` / `main()` で捕捉し、`Did you mean --<name>?` ヒントを stderr に出力する。

出力例 (`allaganeye -version`):

\`\`\`text
Error: no such option: -version. Did you mean --version?
\`\`\`

- 出力先: stderr
- 終了コード: 5 (設定値不正)
- `-v` / `-q` の影響なし (click level / AllaganEyeError 経路と独立)
- `debug-brightness` には `-v` / `-q` がないため hint も `-v` 案内を含まない (実装側で `show_hint=False` 等価)
```

Edit tool の `old_string` には現状の `-q` 出力例直後の context (例: `Error: ffmpeg failed` の closing fence + 空行) を指定する。Task C2 Step 1 で読んだ実際の内容を `old_string` に指定。

- [ ] **Step 3: Grep で追加 subsection の見出し確認**

Use Grep tool:

```text
pattern: ^### click-level option-parse error
path: docs/cli-spec.md
output_mode: content
-n: true
```

Expected: 1 hit (新規 subsection が追加されている)。

- [ ] **Step 4: markdownlint check**

Run: `bash scripts/check-markdownlint.sh docs/cli-spec.md`
Expected: pass.

violation 出たら fix recipe を `docs/markdownlint-guide.md` で確認して修正。よくある violation: heading の前後空行、fenced code block の言語タグ、行末 trailing space。

- [ ] **Step 5: Commit**

```bash
git add docs/cli-spec.md
git commit -m "$(cat <<'EOF'
docs(cli-spec): エラー表示節に click-level option-parse error subsection 追加 (Refs #634)

PR #632 (Refs #440) で実装した click level の Did you mean ヒント
出力を docs に追記。AllaganEyeError 系の -v / -q 切替制御とは独立する
ことを明示。

実装参照: allaganeye/cli.py:498-574 (_suggest_long_option_hint / main)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task C4: #634 fix part 2 — docs/output-spec.md matrix v2 に click-level error 行追加

**Files:**

- Modify: `docs/output-spec.md` (matrix v2、line 99 周辺)

- [ ] **Step 1: matrix v2 構造を Read で確認**

Use Read tool:

```text
file_path: docs/output-spec.md
offset: 95
limit: 15
```

matrix v2 の 19a / 19b / 19c 行が以下のような形式であることを確認:

```text
| `-v` (19a) | ... | ... |
| default (19b) | ... | ... |
| `-q` (19c) | ... | ... |
```

- [ ] **Step 2: matrix v2 末尾に 19d 行を追加**

Use Edit tool で `-q (19c)` 行の直後に以下を挿入:

```markdown
| click-level option-parse error (19d) | `Error: no such option: -X. Did you mean --X?` (stderr / `-v` / `-q` の影響なし、click level / 終了コード 5) | (該当なし — click level なので AllaganEyeError 系の例外経路を通らない) |
```

`old_string` は `-q (19c)` 行の末尾を含む文脈。

- [ ] **Step 3: 関連 Issue 分類セクションに #634 / #440 / PR #632 を追加**

Use Read tool:

```text
file_path: docs/output-spec.md
offset: 107
limit: 30
```

§「関連 Issue 分類」 の「マージ済」 リストに以下を追加:

```markdown
- [#440](https://github.com/Idios/kobutachan-allaganeye/issues/440) / [#634](https://github.com/Idios/kobutachan-allaganeye/issues/634) (click-level option-parse error hint, PR [#632](https://github.com/Idios/kobutachan-allaganeye/pull/632))
```

挿入位置: 既存リストの末尾 (例: `#419 (...排他)` の直後)。

- [ ] **Step 4: markdownlint check**

Run: `bash scripts/check-markdownlint.sh docs/output-spec.md`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add docs/output-spec.md
git commit -m "$(cat <<'EOF'
docs(output-spec): matrix v2 に click-level error 行 19d 追加 (Refs #634)

PR #632 (Refs #440) で実装した click level error hint を matrix v2 に
19d 行として追加し、関連 Issue 分類セクションにも #440 / #634 / PR #632
を反映。

実装参照: allaganeye/cli.py:498-574

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task C5: #635 decision — 選択肢 Q / R 採否を AskUserQuestion で確定

**Files:**

- Read: `docs/l2-workflow.md` (§「Self-Test Report 規約」 line 325-342)
- Read: `.github/pull_request_template.md` (line 43-49, 87-89)

- [ ] **Step 1: docs/l2-workflow.md §「PR 作成ルール」 と §「Self-Test Report 規約」 の位置関係を Read で確認**

Use Grep tool:

```text
pattern: ^## PR 作成ルール|^## Self-Test Report 規約
path: docs/l2-workflow.md
output_mode: content
-n: true
```

§「PR 作成ルール」 の line 番号 (PR 作成 Pre-flight 等) と §「Self-Test Report 規約」 の line 番号 (325-342) を memo に記録。

- [ ] **Step 2: .github/pull_request_template.md の Self-Test 説明コメントを Read で確認**

Use Read tool:

```text
file_path: .github/pull_request_template.md
offset: 40
limit: 60
```

Pre-flight 節 / Self-Test Report 節 / 実機検証 節の **convention 案内コメント** が既存であることを確認。

- [ ] **Step 3: AskUserQuestion で Q / R 採否を確定**

```text
Q: "#635 の対応方法を確定してください"
Options:
  (Q) docs/l2-workflow.md §「PR 作成ルール」 から §「Self-Test Report 規約」 への cross-link 追加のみ (推奨、最小)
  (R) (Q) に加えて .github/pull_request_template.md の Pre-flight / 実機検証 節コメントを explicit 化 (例: "# convention: machine-verified は `[x]`、machine-unverifiable は plain `-`" 1 行追加)
  (P) verify-only close (docs / template 変更なし、現状で受入条件を満たしているとして close)
```

`description` を各 option に付ける (spec §3 表参照)。

- [ ] **Step 4: 決定を memo に記録**

選択結果を memo に。以後の Task C6 はこの選択結果に従って分岐。

(コミット不要 — decision step)

### Task C6: #635 apply — l2-workflow.md cross-link (+ optional PR template explicit 化)

**Files:**

- Modify: `docs/l2-workflow.md`
- Modify (条件付き): `.github/pull_request_template.md`

> **Step 0**: Task C5 Step 4 の決定で (P) verify-only が選ばれた場合は Task C6 全体を skip し、close-issue 時に「受入条件は既存 doc で充足」と memo して進む。(Q) または (R) が選ばれた場合のみ以下を実行。

- [ ] **Step 1: docs/l2-workflow.md §「PR 作成ルール」 の現状内容を Read で確認**

Use Read tool で §「PR 作成ルール」 の段落構造 (前後 30 行程度) を確認。Task C5 Step 1 で取得した line 番号を offset に使う。

- [ ] **Step 2: §「PR 作成ルール」 に cross-link 1 行追加 (選択肢 Q)**

§「PR 作成ルール」 セクション内 (適切な subsection 末尾) に以下を Edit で追加:

```markdown

> **checkbox 表記 convention**: Self-Test Report (machine-verified) は `- [x]` (CI ゲート対象)、実機検証 (machine-unverifiable) は plain bullet `-` (CI ゲート対象外) で書き分ける。詳細は本 doc §「Self-Test Report 規約」 (line 325-342) を参照。
```

挿入位置は §「PR 作成ルール」 の冒頭付近 (Pre-flight 説明の前あたり) が読者の認知効率に良い。Task C5 Step 1 で確認した実際の構造に合わせて Edit `old_string` を選ぶ。

- [ ] **Step 3 (選択肢 R 採用時のみ): .github/pull_request_template.md にコメント強化**

> Task C5 で (Q) のみ選ばれた場合は Step 3 を skip。

Use Edit tool で Pre-flight 節 or Self-Test Report 節のコメントに「machine-verified vs machine-unverifiable」 convention の 1 行を明示追加:

```markdown
<!--
convention: machine-verified は `- [x]` (Self-Test Report 節)、
machine-unverifiable は plain bullet `-` (実機検証 節) で書き分ける。
詳細は docs/l2-workflow.md §「Self-Test Report 規約」 参照。
-->
```

`pr-checklist.yml` workflow を壊さないよう、既存 heading 名 (`Self-Test Report`, `実機検証`, `関連ドキュメント / マトリクス更新`) は触らないこと。

- [ ] **Step 4: markdownlint check**

Run: `bash scripts/check-markdownlint.sh docs/l2-workflow.md`

選択肢 R 採用時:

```bash
bash scripts/check-markdownlint.sh docs/l2-workflow.md .github/pull_request_template.md
```

Expected: pass.

- [ ] **Step 5: §「Self-Test Report 規約」 への cross-link が活きていることを Grep で確認**

Use Grep tool:

```text
pattern: §「Self-Test Report 規約」
path: docs/l2-workflow.md
output_mode: content
-n: true
```

Expected: ≥ 2 hits (元から `originally from feedback_pr_validate_checklist.md` 行と新規追加の cross-link)。

- [ ] **Step 6: Commit**

```bash
git add docs/l2-workflow.md
# 選択肢 R 採用時のみ:
# git add .github/pull_request_template.md
git commit -m "$(cat <<'EOF'
docs(l2-workflow): §「PR 作成ルール」 に checkbox convention cross-link 追加 (Refs #635)

memory feedback_pr_validate_checklist.md / 既存 §「Self-Test Report 規約」
の convention (machine-verified = [x] / machine-unverifiable = plain -)
を PR 作成ルール本体からも参照できるよう cross-link 追加。

選択肢 Q (cross-link のみ) を採用。<選択肢 R 採用時は文を「+ PR template
コメントに convention 案内 1 行追加」 に変える>。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Wave D: Phase 3 (conditional) — 監査 finding 実装

> Wave B Task B1 Step 4 の triage で (a) 同 PR 内修正 と決定された finding が存在する場合のみ実行。0 件なら全 task を skip して Wave E へ。

### Task D-template: 各 finding に対する fix task (1 task / finding)

**Files:**

- Modify: triage で指定された finding の対象 file

各 finding ごとに以下のテンプレで task を作る (執行時に動的に展開):

- [ ] **Step 1: 該当 file の Read で現状確認**

Use Read tool で finding に該当する line 周辺を読む。

- [ ] **Step 2: Edit で修正**

Edit tool で具体的修正を適用 (e.g., L3 ambiguous な単独表記を `L3 (new)` または `L4 (former L3)` に書き換え / broken link を正しい target に修正 / stale info の `TBD` を確定値に置換)。

- [ ] **Step 3: Grep で残骸ゼロ確認**

修正対象が「旧 L3 単独表記の置換」なら:

```text
pattern: <旧表現>
path: <修正 file>
output_mode: content
```

Expected: 0 hits.

- [ ] **Step 4: markdownlint check**

```bash
bash scripts/check-markdownlint.sh <修正 file>
```

- [ ] **Step 5: Commit**

```bash
git add <修正 file>
git commit -m "$(cat <<'EOF'
docs(<scope>): <finding ID> <要約> 修正 (Refs <related issue ?>)

Phase 0 audit finding <ID> として検出された <問題> を修正。

(背景: ...)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

各 finding ごとに 1 commit (frequent commits 原則)。

---

## Wave E: PR submission

### Task E1: 全 docs に対する最終 markdownlint pass

**Files:**

- Read-only: all touched docs

- [ ] **Step 1: 全 touched files に markdownlint 実行**

```bash
bash scripts/check-markdownlint.sh
```

Expected: pass (no violation across all `.md` files in repo).

violation 出たら該当 task に戻って修正。

- [ ] **Step 2: `Grep "L3"` で ambiguous 残存ゼロ確認**

Use Grep tool:

```text
pattern: ^L3[^ \(]|[^a-zA-Z]L3[^a-zA-Z\(]
path: docs
glob: *.md
output_mode: content
-n: true
head_limit: 50
```

`L3 (new)` / `L3 (former L3)` / `L4 (former L3)` のような曖昧でない表現を除外して、単独 `L3` 表記が残っているか確認。`docs/superpowers/` 配下は §4.1 で対象外なので無視。

Expected: 0 hits in active docs。

- [ ] **Step 3: `Grep "(Filter drop 内訳)"` で expanded form のみであることを再確認**

Use Grep tool:

```text
pattern: \(Filter drop 内訳[^+]
path: docs
output_mode: content
-n: true
```

Expected: 0 hits (`(Filter drop 内訳 + ...)` 拡張形式以外はゼロ)。

### Task E2: Iron Law 6 Pre-flight Step 0-4

**Files:**

- Read: `gh pr list` 出力, `git log` 出力

- [ ] **Step 0: 各 issue ごとに既存 open PR がないか確認 (ハードゲート)**

```bash
gh pr list --search "634" --state open
gh pr list --search "635" --state open
gh pr list --search "654" --state open
```

Expected: 各々 0 件。1 件以上ある場合は **PR 作成中止** して別 PR と統合を判断。

- [ ] **Step 1: base 同期確認**

```bash
git fetch origin develop-0.3.0
```

- [ ] **Step 2: 取り込み未済 commit 列挙**

```bash
git log HEAD..origin/develop-0.3.0 --oneline
```

ヒット commit を memo に記録。Wave A の revert commit (`5737bb5`) 等で diverged している場合あり。

- [ ] **Step 3: 取り込み未済 commit の touched files vs 本 PR の touched files 交差確認**

```bash
git log HEAD..origin/develop-0.3.0 --name-only --format=
git diff origin/develop-0.3.0..HEAD --name-only
```

交差なし → そのまま進む。
交差あり → `git merge origin/develop-0.3.0` または `git rebase origin/develop-0.3.0` で取り込んでから検証再実行。

- [ ] **Step 4: 並行 PR 全件 (open + closed) 再確認**

```bash
gh pr list --search "634" --state all
gh pr list --search "635" --state all
gh pr list --search "654" --state all
```

過去 7 日以内に同じ issue を扱った PR がないか確認 (closed/merged 含む)。重複あれば PR 作成中止判断。

### Task E3: `/codex:adversarial-review` (Pre-flight Step 5)

**Files:**

- Codex を起動

- [ ] **Step 1: focus 文字列を準備**

spec §9 「Codex adversarial-review focus」 をコピー:

```text
Verify (i) Iron Law 3 — only docs cleanup / L3 audit changes, no incidental refactors leaked. (ii) Phase 0A audit comprehensive — `L3` mentions in CLAUDE.md / README.md / docs/*.md (excluding superpowers/) / .github/**/*.md|yml / .claude/skills/**/*.md / .claude/hooks/** all classified (i/ii/iii). (iii) #634 doc example matches current `allaganeye/cli.py:498-574` `_suggest_long_option_hint` / `main()` behavior. (iv) #635 cross-link points to live section. (v) 0B findings triage decisions are reasonable (本 PR / 別 issue / skip).
```

- [ ] **Step 2: `/codex:adversarial-review` を起動**

`/codex:adversarial-review` skill を invoke。focus 文字列を引数に渡す。

- [ ] **Step 3: Codex 結果を受領 + triage**

Codex の finding を以下に分類:

- LGTM / no issue → PR 作成へ進む
- minor 指摘 (本 PR 内修正可能) → 該当 Wave に戻って修正、再度 Pre-flight Step 0 から
- major 指摘 (scope 拡大) → PR 作成中止、別 issue / 別 spec で扱う判断

Codex token 枯渇等で fail した場合は `docs/l2-workflow.md` §「Codex fallback」 に従って superpowers `requesting-code-review` subagent で fallback (fallback notice を skill report に必ず記載)。

### Task E4: PR 作成

**Files:**

- 操作: `gh pr create`

- [ ] **Step 1: PR 本文を準備**

PR 本文テンプレ:

```markdown
## 概要

v0.3.0 開発期間中の doc 整理。3 件の P3 deferred doc issue (#634 / #635 / #654) を消化し、新 L3 redefinition 後の active docs 整合性を網羅監査し、不要 doc / source を triage。

詳細: [`docs/superpowers/specs/2026-05-18-v030-docs-cleanup-l3-audit-design.md`](docs/superpowers/specs/2026-05-18-v030-docs-cleanup-l3-audit-design.md)

## 変更点

- `docs/output-spec.md`: :117 Closed Issue 一覧 #388 行に #433 反映 (Refs #654) + matrix v2 に click-level error 行 19d 追加 (Refs #634)
- `docs/cli-spec.md`: §「エラー表示」 に click-level option-parse error subsection 追加 (Refs #634)
- `docs/l2-workflow.md`: §「PR 作成ルール」 に Self-Test Report 規約 cross-link 追加 (Refs #635)
- (条件付き) Wave D 監査 finding fix
- (条件付き) `.github/pull_request_template.md` (Refs #635 選択肢 R 採用時)

## 受け入れ条件

[元 issue の受け入れ条件を逐条記載、Iron Law 1]

- [x] **#654 cond 1**: `docs/output-spec.md:117` の `#388` 行が `#388 / #433 (Filter drop 内訳 + unknown match 行)` 形式 — 対応 diff: `docs/output-spec.md:117`
- [x] **#654 cond 2**: row 12 (`:63`) と Closed Issue 一覧 (`:117`) の表現整合 — 対応 diff: `docs/output-spec.md:117` 追加
- [x] **#634 cond 1**: `docs/cli-spec.md` のエラー表示章に click-level option-parse error の hint 出力例追加 — 対応 diff: `docs/cli-spec.md` §「click-level option-parse error」
- [x] **#634 cond 2**: `docs/output-spec.md` matrix v2 に click-level error 行追加 — 対応 diff: `docs/output-spec.md` 19d 行
- [x] **#634 cond 3**: doc 修正が `allaganeye/cli.py:498-574` 実装と整合 — 対応: Task C2 で読み合わせ済、docstring と出力例が一致
- [x] **#635 cond 1**: `docs/l2-workflow.md` §「PR 作成ルール」 に checkbox convention の cross-link / 言及あり — 対応 diff: `docs/l2-workflow.md` §「PR 作成ルール」 + Self-Test Report 規約 cross-link
- [x] **#635 cond 2**: `.github/pull_request_template.md` の convention 案内コメントは既存 — 対応: 確認済 (line 43-49, 87-89)、(R) 選択時のみ追加 explicit comment

## PR チェックリスト (Iron Law 遵守確認)

[PR template の Iron Law 1-6 ブロックをコピー]

### Iron Law 6: PR 作成前検証

#### ベース同期確認

- PR 作成時の base HEAD: `<sha>` (Task E2 Step 1 出力を貼る)
- PR head の base 取り込み: <取り込み不要 / merge 済み (commit `<sha>`)>
- 直近マージ PR の影響: <なし / [#N] (touched files 交差確認済み)>
- 並行 PR 確認: <なし / [#N] (理由: ...)>

#### Self-Test Report (machine-verified — 全件 `[x]` で validate-checklist 通過)

- [x] `bash scripts/check-markdownlint.sh` pass — Task E1 Step 1
- [x] `ruff check .` — N/A: Python 変更なし
- [x] `ruff format --check .` — N/A: Python 変更なし
- [x] `pyright` — N/A: Python 変更なし
- [x] `pytest` — N/A: Python 変更なし
- [x] `cd gui && npm run lint` — N/A: GUI 変更なし
- [x] `cd gui && npm run typecheck` — N/A: GUI 変更なし
- [x] `cd gui && npm test` — N/A: GUI 変更なし
- [x] `cd gui && npm run build` — N/A: GUI 変更なし
- [x] `cargo check --manifest-path gui/src-tauri/Cargo.toml` — N/A: Rust 変更なし
- [x] `Invoke-Pester -Path scripts/tests/` — N/A: installer / pester 変更なし

#### 関連ドキュメント / マトリクス更新

- [x] 関連ドキュメント更新 — 本 PR は docs 改修自体
- [x] 新規 CLI オプション追加時: matrix 更新 — 該当なし (新規 option 追加なし)
- [x] CLAUDE.md / docs/l2-workflow.md 更新要否確認 — 該当範囲のみ更新済
- [x] 出力書式変更時 cli-spec.md 出力例更新 — click-level error 出力例追加済
- [x] doc セクション参照健全性 — Grep "§「Self-Test Report 規約」" / "§「PR 作成ルール」" / "§「エラー表示」" / Closed Issue 一覧 確認済

#### 実機検証 (machine-unverifiable — plain bullet で書く)

- 該当なし (gpu_detector.py / audio/ / video/detector.py / gui/ 変更なし、docs only)

## 監査結果 (Phase 0 output)

### Phase 0A — L3 整合性監査 (active docs 全件)

| file:line | mention | classification | 根拠 |
| --- | --- | --- | --- |

[Wave A Task A1-A3 の memo を転載]

→ 結果: <X 件中 X 件が (i) または (ii) 分類、(iii) 0 件>

### layer table 3 ファイル一致確認

| layer | CLAUDE.md | design-overview.md | release-process.md | 一致 |
| --- | --- | --- | --- | --- |

[Wave A Task A2 Step 4 memo 転載]

→ 結果: <全行一致 / 不一致あり (詳細)>

### Phase 0B-doc — 不要 doc 監査

[Wave A Task A4-A6 の findings table 転載 + Wave B triage 結果]

### Phase 0B-src — 不要 source 監査 (shallow)

[Wave A Task A7 の findings table 転載 + Wave B triage 結果]

## 関連

- Refs #634 / #635 / #654
- Base branch: `develop-0.3.0`
- Session: intelligent-dirac-34edf4
- Spec: [docs/superpowers/specs/2026-05-18-v030-docs-cleanup-l3-audit-design.md](docs/superpowers/specs/2026-05-18-v030-docs-cleanup-l3-audit-design.md)
- Plan: [docs/superpowers/plans/2026-05-18-v030-docs-cleanup-l3-audit-plan.md](docs/superpowers/plans/2026-05-18-v030-docs-cleanup-l3-audit-plan.md)

## 備考

- Closes / Fixes / Resolves キーワード非使用 (Iron Law 4)。マージ後 `/close-issue 634` / `635` / `654` で手動 close。
- #635 採用方針: <Q / R / P>
- Phase 0 audit findings から派生した別 issue (Wave B triage (b)): <一覧 or "なし">
- Phase 0B-src `DEPRECATED` 系で深い分析が必要なものは「dead-code audit (v0.3.0 派生)」issue として後続起票予定
```

- [ ] **Step 2: PR push + 作成**

```bash
git push -u origin claude/intelligent-dirac-34edf4
```

```bash
gh pr create --base develop-0.3.0 --title "docs: v0.3.0 P3 deferred doc cleanup (#634 #635 #654) + L3 整合性監査 + 不要整理" --body-file - <<'EOF'
[Step 1 のテンプレを貼る]
EOF
```

- [ ] **Step 3: PR URL を memo / ユーザーに報告**

```bash
gh pr view --json url --jq '.url'
```

PR URL をユーザーに報告。

### Task E5: `/iterate-review` で review-fix loop

**Files:**

- 操作: `/iterate-review <PR#>`

- [ ] **Step 1: `/iterate-review <PR#>` を起動**

CI が pass し review feedback が settle するまで自走させる。findings は (A) PR 内追加修正 が原則 (`docs/l2-workflow.md` §「(A) PR 内修正優先 規約」)。

- [ ] **Step 2: 収束したら summary コメント確認**

`/iterate-review` が自動で summary を投稿。LGTM が出るまで loop。

---

## Wave F: Post-merge handoff (out of PR scope)

> マージ後に実行。本 plan の責務外だが完了条件として記載。

### Task F1: 各 issue を `/close-issue` skill で順次 close

- [ ] `/close-issue 654` (受入条件 2 件を base ブランチで実測検証 → close)
- [ ] `/close-issue 634` (受入条件 3 件を base ブランチで実測検証 → close)
- [ ] `/close-issue 635` (受入条件 2 件を base ブランチで実測検証 → close)

### Task F2: Wave B triage で (b) 別 issue 化された findings の起票

- [ ] `/create-task` skill で各 finding を新規 issue 化

### Task F3: `DEPRECATED` 系 deep audit を新規 issue 化 (option)

- [ ] Phase 0B-src で `DEPRECATED` / `FIXME` が複数発見されていた場合、「dead-code audit (v0.3.0 派生)」issue として `/create-task` 起票

---

## Self-Review checklist (plan 書き上がり後の確認)

### Spec coverage

- [x] §2 ゴール 1 (3 件 doc deferred issue 受入条件充足) → Wave C Task C1 / C3 / C4 / C6
- [x] §2 ゴール 2 (新 L3 / `L4 (former L3)` 表記の active docs 全件正確性) → Wave A Task A1 + Wave E Task E1 Step 2
- [x] §2 ゴール 3 (layer table 3 ファイル一致) → Wave A Task A2
- [x] §2 ゴール 4 (broken link / orphan / DEPRECATED triage) → Wave A Task A4-A7 + Wave B Task B1 + Wave D
- [x] §2 ゴール 5 (PR タイトル + base = develop-0.3.0) → Wave E Task E4 Step 2
- [x] §6 Phase 0A 監査手法 → Wave A Task A1-A3
- [x] §6 Phase 0B-doc 監査手法 → Wave A Task A4-A6
- [x] §6 Phase 0B-src 監査手法 → Wave A Task A7
- [x] §7 R1 (scope creep) → Wave B Task B1 Step 2 (件数別 triage 戦略) + spec §3 cleanup 観点 (i) shallow only
- [x] §7 R3 (PR #632 drift) → Wave C Task C2 (preparatory read)
- [x] §7 R4 (markdownlint) → 各 task に markdownlint check step
- [x] §7 R5 (layer table 見落とし) → Wave A Task A2 (行単位照合)
- [x] §8 各 issue 受入条件 → Wave E Task E4 Step 1 PR 本文に逐条
- [x] §8 自動チェック (markdownlint / Grep "Filter drop 内訳" / Grep "L3") → Wave E Task E1
- [x] §9 Iron Law 6 Pre-flight Step 0-5 → Wave E Task E2 + E3
- [x] §9 Closes 禁止 → Wave E Task E4 Step 1 (PR 本文に明示)

### Placeholder scan

- 「TBD」「TODO」「implement later」「fill in details」 → grep して該当なしを確認 (本 plan の対象 hit は heuristic detection の対象 pattern として記載されているのみ、Wave A Task A6 で。これは正当な使用)

### Type / 名称一貫性

- `bash scripts/check-markdownlint.sh` 表記が全 task で統一 ✓
- `(Filter drop 内訳 + unknown match 行)` 表記が #654 関連 task で統一 ✓
- `_suggest_long_option_hint` / `main()` 関数名が Task C2 + Task C3 + Task C4 + Codex focus で一致 ✓
- finding ID convention (`A1-001` / `B-doc-001` / `B-src-001`) が Wave A + Wave B + Wave D で一致 ✓

OK。

---

## 関連 spec / doc

- 設計仕様: [docs/superpowers/specs/2026-05-18-v030-docs-cleanup-l3-audit-design.md](../specs/2026-05-18-v030-docs-cleanup-l3-audit-design.md)
- L3 redefinition 元 spec: [docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md](../specs/2026-05-18-v030-l3-redefinition-design.md)
- Iron Law / Pre-flight: [`.claude/hooks/session-start.sh`](../../../.claude/hooks/session-start.sh) + [`docs/l2-workflow.md`](../../l2-workflow.md)
- markdownlint guide: [`docs/markdownlint-guide.md`](../../markdownlint-guide.md)
- Self-Test Report 規約: [`docs/l2-workflow.md` §「Self-Test Report 規約」](../../l2-workflow.md)
- (A) PR 内修正優先 規約: [`docs/l2-workflow.md` §「(A) PR 内修正優先 規約」](../../l2-workflow.md)
- Codex fallback: [`docs/l2-workflow.md` §「Codex fallback」](../../l2-workflow.md)
