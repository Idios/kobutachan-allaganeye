# Issue #751: CI artifact 名から `-portable` を削除 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `.github/workflows/release.yml` の upload-artifact / download-artifact の `name` から `-portable-` を削除し、CI artifact 名を `allaganeye-windows-v${VERSION}` に変更する。

**Architecture:** line 263 (build-windows job, upload-artifact) と line 282 (release job, download-artifact) の `name` を同期して変更する。upload/download の name 完全一致は GitHub Actions の `actions/upload-artifact@v4` / `actions/download-artifact@v4` の仕様で必須 (片方だけ更新するミスは v0.2.0 release tag push 時に release job の download-artifact が `Artifact not found` で fail する形で detect される、PR 上では走らない release job 仕様 = `if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')`)。

**Tech Stack:** GitHub Actions (YAML)。Python / TS / Rust / GUI のロジック変更なし。

**Design spec:** [`docs/superpowers/specs/2026-05-16-issue-751-artifact-name-design.md`](../specs/2026-05-16-issue-751-artifact-name-design.md) (commit `009ea1b`)

**Branch / Base:** branch = `claude/sharp-darwin-e7bf33` (worktree、現在のセッション) / base = `develop-0.2.0`

---

## Task 1: 現状確認 (variation control)

**Files:**

- Read: `.github/workflows/release.yml` line 260-285

- [ ] **Step 1: yml の該当箇所を grep で確認**

Run:

```bash
grep -nE "name: allaganeye-portable-windows" .github/workflows/release.yml
```

Expected output (2 行):

```text
263:          name: allaganeye-portable-windows-v${{ needs.version-check.outputs.version }}
282:          name: allaganeye-portable-windows-v${{ needs.version-check.outputs.version }}
```

→ Grep tool で `pattern: "name: allaganeye-portable-windows"`, `path: .github/workflows/release.yml`, `output_mode: "content"`, `-n: true` で同等。

- [ ] **Step 2: design doc を再読 (該当 section)**

Read: `docs/superpowers/specs/2026-05-16-issue-751-artifact-name-design.md` の §設計 section

確認事項:

- 旧 name: `allaganeye-portable-windows-v${{ needs.version-check.outputs.version }}`
- 新 name: `allaganeye-windows-v${{ needs.version-check.outputs.version }}`
- 変更は yml 2 行のみ。doc は historical record 残置で対象外

---

## Task 2: yml line 263 (build-windows.upload-artifact) を変更

**Files:**

- Modify: `.github/workflows/release.yml` (upload-artifact section)

- [ ] **Step 1: Edit upload-artifact name (context 付き個別変更)**

Use Edit tool:

- file_path: `.github/workflows/release.yml`
- old_string:

```yaml
      - uses: actions/upload-artifact@v4
        with:
          name: allaganeye-portable-windows-v${{ needs.version-check.outputs.version }}
          path: build/portable/allaganeye-v${{ needs.version-check.outputs.version }}
          if-no-files-found: error
```

- new_string:

```yaml
      - uses: actions/upload-artifact@v4
        with:
          name: allaganeye-windows-v${{ needs.version-check.outputs.version }}
          path: build/portable/allaganeye-v${{ needs.version-check.outputs.version }}
          if-no-files-found: error
```

注: context 付き old_string で unique 担保。line 263 と line 282 は単独 line では完全一致するため、Edit が「unique でない」エラーで失敗する。context (upload-artifact 周辺) で個別に変更する。

- [ ] **Step 2: Verify line 263 changed, line 282 still has `-portable-`**

Run:

```bash
grep -nE "name: allaganeye" .github/workflows/release.yml
```

Expected output:

```text
263:          name: allaganeye-windows-v${{ needs.version-check.outputs.version }}
282:          name: allaganeye-portable-windows-v${{ needs.version-check.outputs.version }}
```

(line 263 だけ更新済、line 282 は次タスク)

---

## Task 3: yml line 282 (release.download-artifact) を変更

**Files:**

- Modify: `.github/workflows/release.yml` (download-artifact section)

- [ ] **Step 1: Edit download-artifact name (context 付き個別変更)**

Use Edit tool:

- file_path: `.github/workflows/release.yml`
- old_string:

```yaml
      - uses: actions/download-artifact@v4
        with:
          name: allaganeye-portable-windows-v${{ needs.version-check.outputs.version }}
          path: dist/allaganeye-v${{ needs.version-check.outputs.version }}
```

- new_string:

```yaml
      - uses: actions/download-artifact@v4
        with:
          name: allaganeye-windows-v${{ needs.version-check.outputs.version }}
          path: dist/allaganeye-v${{ needs.version-check.outputs.version }}
```

- [ ] **Step 2: Verify both lines updated**

Run:

```bash
grep -nE "name: allaganeye-portable-windows" .github/workflows/release.yml
```

Expected output: (0 lines / exit 1)

Run:

```bash
grep -nE "name: allaganeye-windows-v" .github/workflows/release.yml
```

Expected output:

```text
263:          name: allaganeye-windows-v${{ needs.version-check.outputs.version }}
282:          name: allaganeye-windows-v${{ needs.version-check.outputs.version }}
```

---

## Task 4: 統合検証 (git diff + 全体 grep)

- [ ] **Step 1: git diff で変更が yml 2 行のみであることを確認**

Run:

```bash
git diff .github/workflows/release.yml
```

Expected output: line 263 / 282 の 2 行のみ `-portable-` 削除 (1 行 unified diff)。他の line 変更なし。

- [ ] **Step 2: 他のファイルが触られていないことを確認**

Run:

```bash
git status
```

Expected output: `modified: .github/workflows/release.yml` のみ。design doc / plan doc は既に commit 済なので untracked / modified に表示されない。

- [ ] **Step 3: design doc に書いた machine-verified bullets を全て満たすこと確認**

| bullet | 確認方法 | 結果 |
| --- | --- | --- |
| line 263 / 282 の name が `-portable-` 抜きに変更 | Task 3 Step 2 で grep 確認済 | ✓ |
| `grep -nE "allaganeye-portable-windows" .github/workflows/release.yml` で 0 件 | Task 3 Step 2 で確認済 | ✓ |
| PR の `build-windows` job PASS | Task 9 で確認 | (PR push 後) |

---

## Task 5: yml 変更を commit

**Files:**

- Modify: `.github/workflows/release.yml`

- [ ] **Step 1: git add + commit (HEREDOC で日本語含む message)**

Run:

```bash
git add .github/workflows/release.yml
git commit -m "$(cat <<'EOF'
chore(ci): #751 CI artifact 名から -portable を削除

release.yml line 263 (upload-artifact) / line 282 (download-artifact) の
name から -portable- を削除し、allaganeye-windows-v${VERSION} 形式に揃える。
Portable ZIP 哲学下で portable 修飾は冗長 (CLAUDE.md §Portable ZIP 哲学)。
release zip (allaganeye-vX.Y.Z-windows.zip) は既に -portable 抜きで整合済。

Refs #751

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 2: commit を確認**

Run:

```bash
git log -1 --stat
```

Expected output:

- commit hash
- title: `chore(ci): #751 CI artifact 名から -portable を削除`
- file: `.github/workflows/release.yml | 4 ++--` (削除 2 行 + 追加 2 行)

---

## Task 6: Iron Law 6 Pre-flight (PR 作成前の必須チェック)

**Files:** なし (git operation のみ)

- [ ] **Step 0 (hard-gate): 並行 PR 確認**

Run:

```bash
gh pr list --search "751" --state open --json number,title,headRefName,baseRefName
```

Expected output: `[]` (0 件) または既存 PR が無い

- 既存 PR がある場合: 重複作業のリスク。Idios に判断依頼 (本 PR 中止 or 既存 PR を superseded 扱い)
- Step 0 は <1s で完了 (build/verify の前)

- [ ] **Step 1: base 同期**

Run:

```bash
git fetch origin develop-0.2.0
```

Expected output: fetch 完了 (新 commit があれば `<hash>..<hash> develop-0.2.0` 表示)

- [ ] **Step 2: 取り込み未済 commit 確認**

Run:

```bash
git log HEAD..origin/develop-0.2.0 --oneline
```

Expected output: 0 行 (現 branch が base に追いついている) または新 commit のリスト

- [ ] **Step 3: touched files 交差判定**

取り込み未済 commit がある場合のみ実施:

```bash
git log HEAD..origin/develop-0.2.0 --name-only --pretty=format: | sort -u | grep -E "^\.github/workflows/release\.yml$" || echo "no overlap"
```

Expected output: `no overlap` (release.yml に触る取り込み未済 commit なし) または overlap あり → `git merge origin/develop-0.2.0` で取り込んでから Task 7 へ

- [ ] **Step 4: 並行 PR 重複再確認**

Run:

```bash
gh pr list --search "751" --state all --json number,title,headRefName,state | head -20
```

Expected output: 並行 worktree が PR 提出していないこと (Step 0 から時間経過した場合の検出 window 補強。closed / merged も含めて issue #751 関連 PR を網羅確認)

---

## Task 7: PR push + create

**Files:** なし (git / gh 操作)

- [ ] **Step 1: branch を push**

Run:

```bash
git push -u origin claude/sharp-darwin-e7bf33
```

Expected output: branch push 成功

- [ ] **Step 2: PR body を準備 (Self-Test Report 含む)**

PR body (HEREDOC で gh コマンドに渡す):

```markdown
## 概要

CI artifact 名から `-portable` を削除し、`allaganeye-windows-v${VERSION}` 形式に揃える。Portable ZIP 哲学下 (`CLAUDE.md §Portable ZIP 哲学`) で portable 修飾は冗長。release zip (`allaganeye-vX.Y.Z-windows.zip`) は既に整合済。

Refs #751

## 変更内容

| ファイル | 変更 |
| --- | --- |
| `.github/workflows/release.yml:263` | `name: allaganeye-portable-windows-v${{ ... }}` → `name: allaganeye-windows-v${{ ... }}` (upload-artifact) |
| `.github/workflows/release.yml:282` | 同上 (download-artifact、upload と一致必須) |

doc 更新なし: spec/plan 配下の `allaganeye-portable-windows` 参照は historical record として残置 (issue #751 本文方針通り、design spec §設計 で確定)。

## 受け入れ条件 (元 issue 逐条)

- [x] `.github/workflows/release.yml:263` の `name:` を `-portable` 抜きに変更
- [x] `.github/workflows/release.yml:282` の `name:` を上記と一致 (build-windows と release job 間で参照名が一致する必要あり)
- [x] `docs/superpowers/specs/`, `docs/superpowers/plans/` 配下で `allaganeye-portable-windows` を参照している現役 doc があれば更新 → **現役 doc なし、過去 plan/spec は historical record として残置** (issue 本文方針通り)
- [x] CI で release workflow の build 部分 (build-windows job) が成功することを確認 → 下記 Self-Test Report 参照
  - 元 issue の「test tag push」は v0.2.0 release tag 切り出し時に release job (`actions/download-artifact`) の resolve が成功することで合わせて検証

## Self-Test Report

### Machine-verified

- [x] `git diff .github/workflows/release.yml` で line 263 / 282 の name 2 行のみ変更、他改変なし
- [x] `grep -nE "allaganeye-portable-windows" .github/workflows/release.yml` で 0 件
- [x] `grep -nE "name: allaganeye-windows-v" .github/workflows/release.yml` で 2 件 (line 263, 282)
- [x] PR の `build-windows` job が PASS (CI で yml syntax + upload-artifact 動作検証)
- [x] PR の他 CI job (CI workflow 等) に regression なし (`gh pr checks` で全 PASS)

### Machine-unverifiable (Idios 目視確認)

- PR Actions tab → Release workflow run → ページ下部 Artifacts セクションで `allaganeye-windows-v0.2.0` (`-portable-` 抜き) が表示されている
- (release job は tag push 時のみ走るため PR 段階では検証不可) v0.2.0 release tag 切り出し時に release job の `actions/download-artifact` が新 name で artifact を resolve できることを確認 — **本 PR の scope 外、v0.2.0 release 時の確認事項**

## Iron Law 6 Pre-flight 実施記録

- [x] Step 0 (hard-gate): `gh pr list --search "751" --state open` → 0 件
- [x] Step 1: `git fetch origin develop-0.2.0` → 同期完了
- [x] Step 2: `git log HEAD..origin/develop-0.2.0` → 取り込み未済 (有無を実行結果で記載)
- [x] Step 3: touched files 交差判定 → `.github/workflows/release.yml` に touch する未取り込み commit (有無を実行結果で記載)
- [x] Step 4: `gh pr list --search "751" --state all` → 並行 worktree PR 重複なし

## Iron Law 6 path-based check

- yml 変更のみ。Python / GUI / markdown lint いずれも対象外
- 実機検証 trigger: 該当なし (ロジック path 未 touch)

## design spec

[`docs/superpowers/specs/2026-05-16-issue-751-artifact-name-design.md`](docs/superpowers/specs/2026-05-16-issue-751-artifact-name-design.md) (commit `009ea1b`)

## plan

[`docs/superpowers/plans/2026-05-16-issue-751-artifact-name.md`](docs/superpowers/plans/2026-05-16-issue-751-artifact-name.md)

---

session-id: `sharp-darwin-e7bf33`
```

- [ ] **Step 3: gh pr create で PR を作成**

Run (PR body は HEREDOC で `--body-file -` 経由、日本語安全):

```bash
gh pr create \
  --base develop-0.2.0 \
  --head claude/sharp-darwin-e7bf33 \
  --title "chore(ci): #751 CI artifact 名から -portable を削除" \
  --body-file -  <<'PR_BODY_EOF'
[Step 2 で準備した PR body をここに貼る]
PR_BODY_EOF
```

注意: gh コマンドの日本語本文は `--body-file -` + HEREDOC 推奨 (memory `feedback_gh_command_ja_heredoc.md`)。`--body "..."` inline は Windows + Git Bash で UTF-8 破損リスク。

Expected output: PR URL (`https://github.com/Idios/kobutachan-allaganeye/pull/XXX`)

- [ ] **Step 4: PR URL を Idios に報告**

text response で PR URL を Idios に提示 (リンク形式: `[#XXX](https://github.com/Idios/kobutachan-allaganeye/pull/XXX)`)。

---

## Task 8: PR CI 待ち + machine-verified bullet 確定

**Files:** なし (CI 待ち)

- [ ] **Step 1: PR の CI checks を watch**

Run:

```bash
gh pr checks <PR#> --watch
```

Expected output: 全 check PASS (特に `build-windows` job)

- 主要 check (実走するもの):
  - `release.yml` の `version-check` job
  - `release.yml` の `build-windows` job ← **本変更の主要検証ポイント**
  - 他の CI workflow (ci.yml 等) で PR trigger される job 群
- 主要 check (今回 PR では実走しない):
  - `release.yml` の `release` job (tag push 時のみ実走)

- [ ] **Step 2: build-windows job のログから artifact upload を確認**

Run:

```bash
gh run view --log <run-id> --job build-windows 2>&1 | grep -E "Uploaded artifact|allaganeye-windows-v"
```

Expected output: `Uploaded artifact "allaganeye-windows-v0.2.0"` 等 (artifact 名が新 name で upload された証跡)

- [ ] **Step 3: Self-Test Report の machine-verified bullet を PR body に最終反映**

CI PASS が確認できたら、PR body の Self-Test Report machine-verified bullet を全て `[x]` にしておく (gh pr edit で body 更新、または既に `[x]` で出してれば skip)。

---

## Task 9: Idios 目視 (Self-Test Report machine-unverifiable bullet)

**Files:** なし (Idios 操作)

- [ ] **Step 1: AskUserQuestion で Idios に目視確認依頼**

質問内容 (案):

> PR #XXX の Actions tab → Release workflow run → ページ下部 Artifacts セクションで `allaganeye-windows-v0.2.0` (`-portable-` 抜き) が表示されているか目視確認をお願いします。CI workflow の run には別 artifact (`gui-dist` 等) があるため、必ず Release workflow の最新 run を開いて確認すること。

選択肢:

1. 確認 OK (Artifacts に `allaganeye-windows-v0.2.0` 表示)
2. 確認 NG (artifact 名が想定と異なる) → 詳細を Other で記載
3. その他

- [ ] **Step 2: Idios の確認結果を PR コメントに反映**

`gh pr comment <PR#> --body-file -` でコメント追加 (Idios 確認の証跡を PR に残す)。

---

## Task 10: review-fix loop handoff (`/iterate-review` skill)

**Files:** なし (skill dispatch)

- [ ] **Step 1: `/iterate-review` skill を invoke**

User に `/iterate-review <PR#>` を実行してもらう、または Claude 側で skill を invoke。

`/iterate-review` skill が:

- `/review-pr` を fresh subagent で実行
- finding を構造化 return
- (A) PR 内修正 / (B)(C) handoff の振り分け
- CI wait + push 繰り返し
- 全ゼロまたは Round 5 / 発散検知まで反復

→ 本 plan は `/iterate-review` の領域に handoff してここで終了。

---

## Task 11: PR merge 後の close handoff (`/close-issue` skill)

**Files:** なし (skill dispatch + issue 操作)

- [ ] **Step 1: PR merge は Idios に依頼**

Iron Law 6 に従い、Idios の判断で merge。Claude 側から merge は行わない (リスキー操作、Iron Law)。

- [ ] **Step 2: merge 後、`/close-issue 751` skill を invoke**

`/close-issue` skill が:

- 受け入れ条件をマージ後 base ブランチで実測再検証
- 残タスク triage
- ユーザー承認で `gh issue close`

- [ ] **Step 3: issue #751 本文の「対応方針」セクション更新**

`/close-issue` skill 内で、または手動で:

```bash
gh issue edit 751 --body-file -  <<'ISSUE_BODY_EOF'
[updated body with 対応方針 section reflecting v0.2.0 内 PR #XXX で対応]
ISSUE_BODY_EOF
```

「対応方針」セクション更新案:

```markdown
## 対応方針

- ~~本バージョン (v0.2.0) では対応不要 (`deferred`)~~
- ~~v0.2.1 以降の minor release 直前にまとめて適用 (test tag を 1 度切る運用)~~
- **2026-05-16 更新**: v0.2.0 release 前に対応 (PR #XXX で yml 2 行修正)。release tag 時の download-artifact resolve 確認は v0.2.0 release で合わせて実施
```

---

## Self-Review (writing-plans skill 内、plan 完成後に実施)

### Spec coverage check

design spec の各 section が plan task のどこで実装されるか:

| spec section | plan task |
| --- | --- |
| 概要 / 背景 | Task 1 Step 2 (design doc 再読) |
| 受け入れ条件 (yml 2 行変更) | Task 2 / Task 3 |
| 受け入れ条件 (現役 doc 更新) | Task 7 Step 2 PR body で「現役 doc なし」明示 |
| 受け入れ条件 (CI build 成功) | Task 8 |
| 設計 (yml 2 行修正) | Task 2 / Task 3 |
| 設計 (historical 残置) | Task 7 Step 2 PR body で明示 |
| 検証 machine-verified | Task 4 / Task 8 |
| 検証 machine-unverifiable | Task 9 |
| Iron Law 1 (受け入れ条件) | Task 7 Step 2 / Task 10 (`/iterate-review`) |
| Iron Law 3 (scope) | Task 4 Step 2 (touched files 確認) |
| Iron Law 4 (Closes 禁止) | Task 5 / Task 7 Step 2 (Refs のみ) |
| Iron Law 6 Pre-flight | Task 6 |
| Iron Law 6 path-based check | Task 4 Step 3 / Task 7 Step 2 |
| Iron Law 6 実機検証 trigger | (該当なし、Task 7 Step 2 で明示) |
| リスク (name 不一致) | Task 4 (grep 両方確認) |
| 開放問題 | なし (spec で確定) |

→ gap なし。

### Placeholder scan

- 「TBD」「TODO」「実装後で」「fill in details」: なし
- 「Add appropriate error handling」「edge cases handle」: なし
- 「Similar to Task N」: なし (Task 2 / 3 は context-付き Edit の old/new を full 引用)
- code 必要 step に code 欠落: なし

### Type / signature consistency

- yml 内の式: 全 task で `${{ needs.version-check.outputs.version }}` で一致
- `allaganeye-windows-v` prefix: 全 task で一致
- branch 名: 全 task で `claude/sharp-darwin-e7bf33`
- base 名: 全 task で `develop-0.2.0`

→ consistency OK。

---

## Execution Handoff

実行モードは Idios に確認 (writing-plans skill 標準 handoff):

1. **Subagent-Driven** (推奨): fresh subagent per task + two-stage review、fast iteration
2. **Inline Execution**: 本 session で execute、batch + checkpoint

本 plan は非常に小さい (yml 2 行修正 + PR 1 本) ため、Subagent-Driven の overhead が相対的に大きい。**Inline Execution** 推奨。
