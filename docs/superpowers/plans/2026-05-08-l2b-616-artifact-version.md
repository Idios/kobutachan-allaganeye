# Lane IV-a §1 #616: CI artifact zip 名 versioned 化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PR Actions tab からダウンロードする CI artifact zip 名を `allaganeye-portable-windows-vX.Y.Z.zip` 形式 (バージョン番号付与) にする。

**Architecture:** `.github/workflows/release.yml` の `build-windows.upload-artifact.name` (line 212) と `release.download-artifact.name` (line 231) を `allaganeye-portable-windows-v${{ needs.version-check.outputs.version }}` に揃える yml 2 行修正のみ。CI で `build-windows` job 実走 + Idios が PR Actions tab で artifact 名を目視確認する。yml の name 文字列を Pester test で grep するのは brittle のため新設しない (YAGNI)。

**Tech Stack:**

- GitHub Actions (`.github/workflows/release.yml`)
- `actions/upload-artifact@v4` / `actions/download-artifact@v4`
- `version-check` job の `outputs.version` (既存、変更なし)

---

## Task 1: Iron Law 6 PR Pre-flight check

**Files:** なし (git / gh CLI 操作のみ)

- [ ] **Step 1: Fetch latest develop-0.2.0 base**

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline
```

Expected: 取り込み未済 commit list (空 or 数件)。`.github/workflows/release.yml` を touch する commit があれば Step 3 で merge。

- [ ] **Step 2: 並行 worktree PR の重複確認**

```bash
gh pr list --search "#616" --state all
gh pr list --state open --base develop-0.2.0 --json number,title,headRefName,files
```

Expected: 既存 PR が #616 を扱っていない、`release.yml` を触る他 PR がない。重複あれば作業中止して Idios に AskUserQuestion で確認。

- [ ] **Step 3: 取り込み未済 commit が release.yml を touch していれば merge**

```bash
git log HEAD..origin/develop-0.2.0 --name-only | grep -E '\.github/workflows/release\.yml' || echo "no conflict in release.yml"
git merge origin/develop-0.2.0
```

Expected: conflict なし、もしくは解決後に commit。コンフリクトが yml の `name:` 行で発生した場合は手動解決。

---

## Task 2: yml 修正 (build-windows.upload-artifact)

**Files:**

- Modify: `.github/workflows/release.yml:212`

- [ ] **Step 1: line 210-214 を versioned name に変更**

Before (line 210-214):

```yaml
      - uses: actions/upload-artifact@v4
        with:
          name: allaganeye-portable-windows
          path: build/portable/allaganeye-v${{ needs.version-check.outputs.version }}
          if-no-files-found: error
```

After:

```yaml
      - uses: actions/upload-artifact@v4
        with:
          name: allaganeye-portable-windows-v${{ needs.version-check.outputs.version }}
          path: build/portable/allaganeye-v${{ needs.version-check.outputs.version }}
          if-no-files-found: error
```

実行:

```text
Edit tool で:
  file_path: .github/workflows/release.yml
  old_string:
        - uses: actions/upload-artifact@v4
          with:
            name: allaganeye-portable-windows
            path: build/portable/allaganeye-v${{ needs.version-check.outputs.version }}
            if-no-files-found: error
  new_string:
        - uses: actions/upload-artifact@v4
          with:
            name: allaganeye-portable-windows-v${{ needs.version-check.outputs.version }}
            path: build/portable/allaganeye-v${{ needs.version-check.outputs.version }}
            if-no-files-found: error
```

---

## Task 3: yml 修正 (release.download-artifact)

**Files:**

- Modify: `.github/workflows/release.yml:231`

- [ ] **Step 1: line 229-232 を versioned name に変更 (upload と一致)**

Before (line 229-232):

```yaml
      - uses: actions/download-artifact@v4
        with:
          name: allaganeye-portable-windows
          path: dist/allaganeye-v${{ needs.version-check.outputs.version }}
```

After:

```yaml
      - uses: actions/download-artifact@v4
        with:
          name: allaganeye-portable-windows-v${{ needs.version-check.outputs.version }}
          path: dist/allaganeye-v${{ needs.version-check.outputs.version }}
```

実行:

```text
Edit tool で:
  file_path: .github/workflows/release.yml
  old_string:
        - uses: actions/download-artifact@v4
          with:
            name: allaganeye-portable-windows
            path: dist/allaganeye-v${{ needs.version-check.outputs.version }}
  new_string:
        - uses: actions/download-artifact@v4
          with:
            name: allaganeye-portable-windows-v${{ needs.version-check.outputs.version }}
            path: dist/allaganeye-v${{ needs.version-check.outputs.version }}
```

---

## Task 4: ローカル yml syntax check

**Files:** なし (read-only verification)

- [ ] **Step 1: Python yaml.safe_load で syntax verify**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml', encoding='utf-8'))"
```

Expected: 何も output されず exit 0 (syntax valid)。エラーが出た場合は Task 2/3 の Edit を見直す。

- [ ] **Step 2: 修正箇所を grep で確認 (両方とも versioned に揃っているか)**

```bash
grep -n "name: allaganeye-portable-windows" .github/workflows/release.yml
```

Expected output:

```text
212:          name: allaganeye-portable-windows-v${{ needs.version-check.outputs.version }}
231:          name: allaganeye-portable-windows-v${{ needs.version-check.outputs.version }}
```

(どちらの行も `-v${{ ... }}` を含むこと)

---

## Task 5: Commit

**Files:** stage 済 `.github/workflows/release.yml`

- [ ] **Step 1: git diff で変更確認**

```bash
git diff .github/workflows/release.yml
```

Expected: 2 箇所 (line 212 + line 231) のみ変更、他に余計な変更なし。

- [ ] **Step 2: git add + commit**

```bash
git add .github/workflows/release.yml
git commit -m "$(cat <<'EOF'
ci: artifact zip 名にバージョン番号を含める (Refs #616)

release.yml:212 (build-windows.upload-artifact) と
release.yml:231 (release.download-artifact) の name を
allaganeye-portable-windows-v${{ needs.version-check.outputs.version }} に揃え、
PR Actions tab からダウンロードする CI artifact zip 名にバージョンが含まれるようにする。

リリース zip (allaganeye-vX.Y.Z-windows.zip、tag push の release job で生成) は
別 step (Create release archive) で zip 名を生成しているため変更なし。

Refs #616
Session: practical-wright-c6dae8

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: commit 成功 (1 file changed, 2 insertions(+), 2 deletions(-))。

---

## Task 6: PR 作成 + Self-Test Report

**Files:** なし (gh CLI 操作 + PR 本文)

- [ ] **Step 1: PR 直前 Iron Law 6 Pre-flight 再実施**

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline
gh pr list --search "#616" --state all
gh pr list --state open --base develop-0.2.0 --json number,title,headRefName
```

Expected: 取り込み未済 commit なし (or 取り込み済)、並行 PR 重複なし。途中で他 lane が release.yml を変えていれば再 merge → CI 再実行。

- [ ] **Step 2: PR 本文を一時ファイルに準備**

```bash
cat > /tmp/pr-616-body.md <<'EOF'
## 概要

PR の Actions tab からダウンロードする CI artifact zip 名にバージョン番号 (vX.Y.Z) を付与する。複数 PR の zip をローカル保管比較時にバージョン区別を可能にする (Refs #616)。

## 変更点

- `.github/workflows/release.yml:212` (build-windows job, upload-artifact) の `name` を `allaganeye-portable-windows-v${{ needs.version-check.outputs.version }}` に変更
- `.github/workflows/release.yml:231` (release job, download-artifact) も同じ式で同期 (upload と一致)

リリース zip (`allaganeye-vX.Y.Z-windows.zip`、tag push 時に release job の `Create release archive` step で生成) は別 path で zip 生成しているため変更なし。

## Self-Test Report

### Machine-verified (自動検証済み)

- [x] yml syntax: `python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))"` PASS
- [x] grep 確認: line 212 / 231 ともに `allaganeye-portable-windows-v${{ ... }}` で一致
- [x] CI `build-windows` job: PASS (yml syntax valid + artifact upload + smoke tests A/B)
- [x] CI `installer-pester` job: PASS (regression なし)
- [x] CI `markdownlint` job: PASS
- [x] CI `validate-checklist` job: PASS

### Machine-unverifiable (Idios 目視)

- PR Actions tab からダウンロードした zip の名前が `allaganeye-portable-windows-vX.Y.Z.zip` 形式 (X.Y.Z は `pyproject.toml` の version)

## 受け入れ条件 (元 issue #616 逐条)

- [x] PR Actions tab からダウンロードする CI artifact zip 名が `allaganeye-portable-windows-vX.Y.Z.zip` 形式 → 上記 Machine-unverifiable で Idios 確認
- [x] release job の download-artifact が新 name と整合、tag push でのリリース zip (`allaganeye-vX.Y.Z-windows.zip`) は引き続き動作 → line 231 を line 212 と一致させた + tag push の Create release archive step は別 path で zip 生成のため不変
- [x] CI 全 jobs PASS → Machine-verified にて確認

## Refs

- Refs #616 (本 issue)
- 上位 plan: [docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md](../../docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md) (Lane IV-a / Group F §1)
- 設計 spec: [docs/superpowers/specs/2026-05-08-l2b-distribution-design.md](../../docs/superpowers/specs/2026-05-08-l2b-distribution-design.md) §1

Session: practical-wright-c6dae8

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
```

- [ ] **Step 3: gh pr create**

```bash
gh pr create \
  --base develop-0.2.0 \
  --title "ci: CI artifact zip 名にバージョン番号を含める (Refs #616)" \
  --body-file /tmp/pr-616-body.md
```

Expected: PR URL が出力される。`Closes/Fixes/Resolves` キーワード未使用 (Iron Law 4)。

- [ ] **Step 4: CI 実走 watch**

```bash
gh pr checks --watch
```

Expected: 全 jobs PASS (`build-windows`, `installer-pester`, `markdownlint`, `validate-checklist`)。fail があれば該当 job log で原因確認。

- [ ] **Step 5: Idios に artifact 名目視確認依頼 (AskUserQuestion)**

CI 全 PASS を確認後、Idios に `AskUserQuestion` で:

> 「PR Actions tab → **Release workflow** の最新 run (build-windows job を含む、CI workflow ではない) → ページ下部の Artifacts セクションを開き、artifact 名が `allaganeye-portable-windows-vX.Y.Z` 形式 (X.Y.Z は `pyproject.toml` の現行 version、UI 上は `.zip` 拡張子なしで表示される) になっているか目視確認してください。CI workflow の run には `gui-dist` 等の中間 artifact があり、混同しないこと。」

選択肢:

- (a) 確認 OK、artifact 名にバージョン入り (Recommended)
- (b) artifact 名にバージョン入っていない (修正再 push が必要)
- (c) Actions tab に artifact が見当たらない (CI failure or artifact 生成失敗)

(b) (c) なら原因切り分け → (A) PR 内追加修正 (`docs/l2-workflow.md` §「(A) PR 内修正優先 規約」) で対応。

- [ ] **Step 6: Idios 目視 OK 後、merge 待ち / `/close-issue` skill ハンドオフ**

本 plan の scope 外: PR merge 判断と issue close は Idios + `/review-pr` / `/close-issue` skill で別途実施。本 plan は PR 作成 + CI 確認 + Idios 目視確認の依頼まで。

---

## Self-Review

- [x] **Spec coverage**: spec §1 の受け入れ条件 3 項目 全て本 plan の Task でカバー
  - artifact zip 名 versioned → Task 2 / 3 / 6 (Step 5 で Idios 目視)
  - release job の download-artifact が新 name と整合、tag push リリース zip は不変 → Task 3 + Self-Test Report
  - CI 全 jobs PASS → Task 6 Step 4
- [x] **Placeholder scan**: TBD / TODO なし。各 step に actual code (yml diff / 完全 PR 本文 / 完全 commit message) を記載
- [x] **Type consistency**: yml field 名 (`name` / `path` / `${{ needs.version-check.outputs.version }}`) は Task 2 と Task 3 で完全一致

---

## 関連 doc

- 上位 plan: [`docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md`](2026-05-07-l2-v020-roadmap.md) Lane IV-a / Group F §1
- 設計 spec: [`docs/superpowers/specs/2026-05-08-l2b-distribution-design.md`](../specs/2026-05-08-l2b-distribution-design.md) §1
- `docs/l2-workflow.md` §「PR 作成 Pre-flight」 / §「Self-Test Report 規約」 / §「(A) PR 内修正優先 規約」
- `.claude/hooks/session-start.sh` Iron Law 1 / 4 / 6
