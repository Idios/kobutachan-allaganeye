# L-γ docs codify Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** v0.2.0/v0.2.1 retrospective spec の L-γ (docs codify) を 3 PR で実装し、A1 (refactor-pattern.md 新設) / A2 (release-process.md Track 構造追記) / M2+M4+M10 (依存規約 + encoding checklist + markdownlint 参照経路強化) を docs 側で完結させる。skill 側の参照リンク追加は L-β で行うため、本 plan は docs と CLAUDE.md 編集のみに focus する。

**Architecture:** 各 PR は独立 reviewable。新規 doc (A1) と既存 doc 追記 (A2 / M2 / M4 / M10) を Lane 内で並列着手可能だが、推奨は γ-1 → γ-2 → γ-3 の順 (依存はないが review 負荷の分散用)。docs/markdownlint-guide.md 自体は commit adcae66 で既存生成済、本 Lane では non-skill な参照経路追加のみ。

**Tech Stack:** Markdown + markdownlint-cli2 + Bash (verification grep) + git

**Spec reference:** [docs/superpowers/specs/2026-05-17-v020-v021-retro-codex-integration-design.md](../specs/2026-05-17-v020-v021-retro-codex-integration-design.md) §A1 / §A2 / §M2 / §M4 / §M10

**Worktree:** `E:\projects\kobutachan-tools\kobutachan-allaganeye\.claude\worktrees\nervous-hoover-464244` (branch: `claude/nervous-hoover-464244`, base: develop の最新)

---

## File Structure

| 種別 | path | 担当 Task |
| --- | --- | --- |
| 新規 | `docs/refactor-pattern.md` | Task 1 (γ-1) |
| 更新 | `CLAUDE.md` (§開発ワークフロー / §リリース戦略 / §コマンド / §外部依存 新設 / §バグ修正時の方針) | Task 1 / 2 / 3 |
| 更新 | `docs/release-process.md` (§Patch release Track 構造 新設) | Task 2 (γ-2) |
| 更新 | `docs/l2-workflow.md` (§外部依存規約 新設) | Task 3 (γ-3) |
| 更新 | `docs/markdownlint-guide.md` (header note) | Task 3 (γ-3) |
| 更新 | `.markdownlint-cli2.yaml` (header comment) | Task 3 (γ-3) |
| 更新 | `scripts/check-markdownlint.sh` (error 出力末尾参照リンク) | Task 3 (γ-3) |

skill 側の参照リンク追加 (`/review-pr` Step 5a / `/scope-guard` / `/iterate-review` Step 2.4) は **L-β scope** とし、本 plan の範囲外。

---

## Pre-flight (実装開始前に 1 回)

- [ ] **Step 0.1: base ブランチを fetch して up-to-date 確認**

```bash
git fetch origin develop-0.3.0 2>&1 || git fetch origin main
git status
```

Expected: `Your branch is up to date with 'origin/<base>'` または ahead-only。develop-0.3.0 が無ければ main を base とする (release cycle 開始前)。

- [ ] **Step 0.2: spec の §A1 / §A2 / §M2 / §M4 / §M10 を一通り read**

```bash
sed -n '/^### 4.1/,/^### 4.2/p' docs/superpowers/specs/2026-05-17-v020-v021-retro-codex-integration-design.md | wc -l
```

Expected: 100+ 行 (A1 / A2 セクション + 参照契機が読める)。

- [ ] **Step 0.3: 既存 docs の current state を grep**

```bash
grep -n "Phase 分割\|refactor-pattern\|Patch release Track\|外部依存規約\|encoding boundary" CLAUDE.md docs/l2-workflow.md docs/release-process.md
```

Expected: 既存記述ゼロ件 (本 plan で新設するため)。

---

## Task 1 (PR γ-1): A1 docs/refactor-pattern.md 新設

**Files:**

- Create: `docs/refactor-pattern.md`
- Modify: `CLAUDE.md` (§開発ワークフロー or 末尾 §参考 directory に 1 行リンク追加)

- [ ] **Step 1.1: docs/refactor-pattern.md を新規作成 (全文)**

以下の content で `docs/refactor-pattern.md` を Write:

```markdown
# 大規模 refactor の Phase 分割パターン

単一 PR で touched files > 30 file or diff > 1000 line になりそうな refactor を **Phase 分割**するためのガイド。AppError migration (#663→#689→#714/716/725/730/733→#745→#746) を実例として codify する。

## 1. 適用条件

以下のいずれかを満たす場合に Phase 分割を**検討**する:

- 単一 PR で `git diff --stat` の touched files > 30 file
- 単一 PR で `git diff --shortstat` の `+lines, -lines` 合計 > 1000 line
- consumer (caller) 数が多く、一度に乗り換えると base regression を全 site で検出することになる
- legacy fallback と新 API が long-lived に並存する必要がある

**例外**: 自動生成 file の bulk regenerate (codegen / formatter pass) は touched > 30 でも Phase 不要。

## 2. Phase 設計原則

| Phase | 内容 | green 維持 |
| --- | --- | --- |
| Phase 0 | 設計 spec + 影響範囲 inventory (consumer 件数 / call site list) | docs only |
| Phase 1 | data layer / 共通 helper / 型定義 (consumer 0 でも green) | 新 API 追加、旧 API 残存 |
| Phase 2+ | 個別 site migration (per-site が独立 reviewable) | 各 site が新 API へ乗り換え、旧 API は引き続き動作 |
| Phase Final | legacy fallback 撤去、stale docstring sweep | 旧 API 削除、参照ゼロ確認 |

各 Phase の切れ目で **「green / regression なし / consumer が選択的に乗り換え可能」** を満たす粒度を維持する。

## 3. Reference: AppError migration (実例)

| PR | Phase | 内容 |
| --- | --- | --- |
| #663 | Phase 0 (spec) | AppError 型定義 + 全 site inventory (80 site) |
| #689 | Phase 1 | AppError 型 + helper 追加、legacy fallback 残存 |
| #714 / #716 / #725 / #730 / #733 | Phase 2 (per-site migration) | 5 PR で個別 site の AppError 化を分担 |
| #745 | Phase 3 | `*Error / *ErrorHint` 並列構造を unified `*ErrorState` に集約 |
| #746 | Phase Final | legacy fallback 撤去 + stale docstring sweep |

各 PR は base sync + Pre-flight Step 0-4 を通り、独立 reviewable。Phase 1 完了後の commit 数 = 約 80 site の 0% migration、Phase 2 完了後 = 100% migration、Phase Final で legacy 削除という flow。

## 4. Phase 切れ目の判定基準

1 PR で**以下 3 条件すべてを満たす**粒度に分ける:

- **green**: 当該 PR をマージ後、CI が green (pyright / pytest / lint / build / cargo check)
- **regression なし**: 既存機能の振る舞いが変わらない (新 API が opt-in、旧 API が default 動作維持)
- **consumer が選択的に乗り換え可能**: per-site で乗り換えタイミングを選べる (一括強制ではない)

3 条件が **同時に満たせない**場合、その PR は範囲が広すぎる → さらに小さな Phase に分割する。

## 5. 関連 doc

- [docs/superpowers/specs/2026-05-08-l2-appError-migration-completion-design.md](superpowers/specs/2026-05-08-l2-appError-migration-completion-design.md) — AppError migration 元 spec
- [docs/l2-workflow.md](l2-workflow.md) §subagent 起動規約 — Phase 単位 subagent dispatch
- [docs/issue-policy.md](issue-policy.md) §`deferred` ラベル運用 — Phase 分割で sub-issue を起票する場合のルール
```

- [ ] **Step 1.2: markdownlint check**

```bash
npx --prefix gui markdownlint-cli2 docs/refactor-pattern.md
```

Expected: `Summary: 0 error(s)`。

- [ ] **Step 1.3: CLAUDE.md に reference link を追加 (§開発ワークフロー 末尾)**

CLAUDE.md の §開発ワークフロー 末尾 (`### バグ修正時の方針` の直前) に以下の 1 行を追加:

```markdown
### 大規模 refactor の Phase 分割

単一 PR で touched files > 30 file or diff > 1000 line を超えそうな refactor は [`docs/refactor-pattern.md`](docs/refactor-pattern.md) §1 適用条件を確認し、Phase 分割を検討する。AppError migration (#663→#689→#714/716/725/730/733→#745→#746) が reference 実例。
```

- [ ] **Step 1.4: reference link grep で検証**

```bash
grep -nE "refactor-pattern" CLAUDE.md
```

Expected: 1 行 hit (新規追加した link)。

- [ ] **Step 1.5: markdownlint で CLAUDE.md も再確認**

```bash
npx --prefix gui markdownlint-cli2 CLAUDE.md docs/refactor-pattern.md
```

Expected: 0 error。

- [ ] **Step 1.6: PR γ-1 を 1 commit にまとめる**

```bash
git add docs/refactor-pattern.md CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: 大規模 refactor Phase 分割パターンを codify (Refs spec L-γ A1)

retro spec §A1 の実装。AppError migration (#663→#689→#714/716/725/730/733→
#745→#746) を実例とする Phase 設計原則と判定基準を docs/refactor-pattern.md
として codify。CLAUDE.md §開発ワークフローから参照リンクを設置。

参照経路の skill 側 (/review-pr Step 5a / /scope-guard) への link 追加は
L-β skill 改訂 Lane に分離。本 PR は docs + CLAUDE.md のみ。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2 (PR γ-2): A2 docs/release-process.md に Track 構造追記

**Files:**

- Modify: `docs/release-process.md` (§Patch release Track 構造 新設)
- Modify: `CLAUDE.md` (§リリース戦略 から Track 構造 anchor へのリンク追加)

- [ ] **Step 2.1: docs/release-process.md の current state 確認**

```bash
grep -nE "^## |^### " docs/release-process.md | head -30
```

既存セクション一覧を取得して、追記位置 (例: 末尾 or §マイナーリリース の直後) を決定。

- [ ] **Step 2.2: docs/release-process.md に §Patch release の Track 構造 を追記**

既存 doc の末尾 (または レイヤーリリースゲート § の直後で文脈が合う場所) に以下を追加:

```markdown
## Patch release の Track 構造

v0.M.N → v0.M.(N+1) の patch release を **Track A-D 構造**で並列化する。v0.2.1 (PR #759-#774) で確立した運用パターン。

### 適用条件

- security alert / Dependabot patch
- deferred UX 吸収 (`/release` skill Step 0c (M9) で「次 patch 吸収」と判定された issue 群)
- CI / build gate 追加
- 緊急 bug fix の集約

minor release (v0.M.0 → v0.(M+1).0) や major refactor は本 Track 構造の対象外、別 plan で扱う。

### Track 規約

| Track | 内容 | 並列性 | reference (v0.2.1) |
| --- | --- | --- | --- |
| Track 0 | spec PR (`docs/superpowers/specs/<date>-v0.M.N+1-patch-design.md`) | 直列 (最初) | #759 |
| Track A | security / dependency (Dependabot / cargo audit / npm audit) | 並列可 | #760 |
| Track B | deferred UX 吸収 (Step 0c で取り込み判定された issue 群) | 並列可 | #764 / #766 / #768 / #772 |
| Track C | CI / build gate 追加 (security-audit.yml 等) | 並列可 | #763 |
| Track D | version bump + CHANGELOG | 直列 (最後) | #773 |

Track A / B / C は worktree 別 / 並列着手可能。Track D は他全 Track のマージ後に直列実行する (version bump が他 PR と base 衝突しないようにするため)。

### `/release` skill との連携

Step 0a 受け入れゲート → Step 0b deferred 全件取得 → Step 0c 1 件ずつ (a) 次release吸収 / (b) deferred 継続 / (c) close 分類。Step 0c で (a) と分類された issue 群が **Track B 吸収候補** となり、spec PR (Track 0) の table に記録される。

詳細な Step 0c 運用は [`.claude/skills/release/SKILL.md`](../.claude/skills/release/SKILL.md) を参照。

### 参考: v0.2.1 patch release (2026-05-16)

v0.2.0 release 後の patch として、4 Track + spec を計 10 PR (#759 spec / #760 Track A / #763 Track C / #764, #766, #768, #772 Track B / #769, #771 Track C 軽量化 / #773 Track D) で完結した実例。
```

- [ ] **Step 2.3: markdownlint check**

```bash
npx --prefix gui markdownlint-cli2 docs/release-process.md
```

Expected: 0 error。

- [ ] **Step 2.4: CLAUDE.md §リリース戦略 に Track 構造への参照リンクを追加**

CLAUDE.md §リリース戦略 の現行記述:

```markdown
## リリース戦略

詳細は [`docs/release-process.md`](docs/release-process.md) を参照。
```

を以下に書き換え:

```markdown
## リリース戦略

詳細は [`docs/release-process.md`](docs/release-process.md) を参照。Patch release (v0.M.N → v0.M.(N+1)) は [§Patch release の Track 構造](docs/release-process.md#patch-release-の-track-構造) (Track A-D 並列化) に従う。
```

- [ ] **Step 2.5: reference link grep で検証**

```bash
grep -nE "Patch release.*Track|patch-release-の-track" CLAUDE.md docs/release-process.md
```

Expected: CLAUDE.md と docs/release-process.md の両方に hit。

- [ ] **Step 2.6: markdownlint で両 file を再確認**

```bash
npx --prefix gui markdownlint-cli2 CLAUDE.md docs/release-process.md
```

Expected: 0 error。

- [ ] **Step 2.7: PR γ-2 を 1 commit にまとめる**

```bash
git add docs/release-process.md CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: patch release の Track 構造を release-process.md に codify (Refs spec L-γ A2)

retro spec §A2 の実装。v0.2.1 で確立した Track A-D 並列化パターン
(#759 spec / #760 Track A / #763 Track C / #764 etc. Track B / #773 Track D)
を docs/release-process.md §Patch release の Track 構造として codify。
/release skill (M9) の Step 0c との連携を明示。

CLAUDE.md §リリース戦略 から Track 構造 anchor へのリンクを追加。
参照経路の /release skill / brainstorming skill / /create-task skill への
明示は L-β skill 改訂 Lane で対応。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3 (PR γ-3): M2 依存規約 + M4 encoding checklist + M10 markdownlint 参照経路強化

**Files:**

- Modify: `docs/l2-workflow.md` (§外部依存規約 新設)
- Modify: `CLAUDE.md` (§外部依存 新設 + §バグ修正時の方針 に encoding checklist 追記 + §コマンド の markdownlint 行直下にリンク)
- Modify: `docs/markdownlint-guide.md` (header note 追加)
- Modify: `.markdownlint-cli2.yaml` (header comment)
- Modify: `scripts/check-markdownlint.sh` (error 出力末尾の参照リンク)

### Step 3a (M2): docs/l2-workflow.md §外部依存規約 新設

- [ ] **Step 3.1: docs/l2-workflow.md の current state 確認**

```bash
grep -nE "^## " docs/l2-workflow.md | tail -10
```

末尾近辺の §参考 直前 を追記位置候補とする。

- [ ] **Step 3.2: docs/l2-workflow.md に §外部依存規約 を追加 (§参考 の直前に挿入)**

```markdown
## 外部依存規約 (#649/#651/#703/#721 教訓)

外部依存 (Python / npm / cargo / OS binary tarball 等) の DL コードは **immutable URL** で pin する。`master` / `main` / `latest` / `raw HEAD` を含む URL は禁止。

### Why

PR #649 → #651 (get-pip.py SHA pin) → #703 (versioned tag URL 切替) → #721 (BtbN monthly snapshot) の 3 hotfix 連発 (F2)。最初から immutable URL ルールがあれば 1 PR で完結した。BtbN daily の retention 14 日 / get-pip.py master の breaking change 等、上流側の breaking が DL URL に影響する。

### 受け入れ可能なソース

| ソース | 形式 | 例 |
| --- | --- | --- |
| PyPA versioned tag | `https://github.com/pypa/<repo>/raw/<tag>/...` | get-pip.py |
| BtbN monthly snapshot | `https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-YYYY-MM-{28,29,30,31}-*/...` | FFmpeg n8.1 |
| npm registry version pin | `package.json` の `dependencies` で `"^X.Y.Z"` (transitive は package-lock.json で fix) | tauri / vite |
| cargo registry version pin | `Cargo.toml` の `tauri = "2.11"` (transitive は Cargo.lock で fix) | tauri-utils |
| SHA-pinned download | `https://.../...-<commit-hash>.tar.gz` + SHA256 checksum | FFmpeg checksum |

### 禁止パターン

| パターン | 理由 |
| --- | --- |
| `https://.../master/...` | upstream master の breaking が即影響 |
| `https://.../main/...` | 同上 |
| `https://.../latest/...` | retention / 互換性が保証されない |
| `https://raw.githubusercontent.com/.../HEAD/...` | HEAD は git ref として可変 |
| `npm install <pkg>` (version 未指定) | semver caret semantics で意図せぬ major up に脱する |

### 検証手順

`scripts/build-portable-zip.ps1` / `.github/workflows/*.yml` / 任意の install script を編集する場合:

1. 該当行のコメントに「must be immutable (versioned tag / SHA pinned)」と記載
2. Pester regression (`tests/installer/build-portable-zip.Tests.ps1`) で URL に `master`, `main`, `latest`, `HEAD` の literal が含まれていないことを assert
3. `/review-pr` skill が installer / workflow PR を review するときに本 § を引いて URL 規約適合を Step 5b トリアージで逐条検証
```

- [ ] **Step 3.3: markdownlint check (docs/l2-workflow.md)**

```bash
npx --prefix gui markdownlint-cli2 docs/l2-workflow.md
```

Expected: 0 error。

### Step 3b (M4): CLAUDE.md §バグ修正時の方針 に encoding boundary checklist 追記

- [ ] **Step 3.4: CLAUDE.md §バグ修正時の方針 の current state 確認**

```bash
grep -n "^## バグ修正時の方針\|^### " CLAUDE.md | head -20
```

§バグ修正時の方針 の位置と末尾を確認。

- [ ] **Step 3.5: §バグ修正時の方針 末尾に encoding boundary checklist を追記**

CLAUDE.md §バグ修正時の方針 末尾に以下を追加:

```markdown
### encoding boundary audit checklist (#656/#657/#662 教訓)

subprocess / IPC / OS API を介した encoding fix を行うときは、**以下 3 層をすべて audit** すること。1 層だけ fix すると別層で再発する (F4: PR #657 Python 側 fix → #662 Rust 側追加 fix が必要だった事例)。

1. **Python 側** (CLI / scripts): `subprocess.Popen(..., encoding=...)` / `sys.stdout.reconfigure(encoding='utf-8')` / `os.fsencode` / `Path` の Unicode 扱い
2. **Rust 側** (Tauri / gui/src-tauri/): `tokio::process::Command` の stdin/stdout encoding / `OsString` / `Path::to_string_lossy()` の `\u{FFFD}` 混入 / `serde_json::from_str` の BOM 拒否
3. **OS code page**: Windows なら `chcp 65001` 想定の動作 / cp932 環境での fallback / GitHub Actions runner (`pwsh` UTF-8 BOM 出力 vs PowerShell 5.1 BOM 付き)

実装 PR では各 fix が 3 層のうちどこを touch するか PR 本文に明示。3 層に跨る fix は **Phase 分割の対象**になりうる (`docs/refactor-pattern.md`)。
```

### Step 3c (M2 続き): CLAUDE.md §外部依存 新設

- [ ] **Step 3.6: CLAUDE.md に §外部依存 を新設 (§コマンド or §開発ワークフロー の直後の自然な位置)**

CLAUDE.md の §コマンド の直後に以下の section を追加:

```markdown
## 外部依存

外部依存 (Python / npm / cargo / OS binary tarball 等) の DL コードは **immutable URL** で pin する。詳細・受け入れ可能ソース・禁止パターン・検証手順は [`docs/l2-workflow.md` §外部依存規約](docs/l2-workflow.md#外部依存規約) を参照。

代表事例: get-pip.py SHA pin (#649→#651→#703)、BtbN FFmpeg monthly snapshot (#721)。
```

### Step 3d (M10): markdownlint 参照経路強化 (non-skill 側)

- [ ] **Step 3.7: .markdownlint-cli2.yaml の current state を確認**

```bash
head -10 .markdownlint-cli2.yaml
```

既存 header の有無を確認。

- [ ] **Step 3.8: .markdownlint-cli2.yaml に header comment を追加 (file 先頭、既存 config の上)**

`.markdownlint-cli2.yaml` の先頭に以下を追加:

```yaml
# markdownlint-cli2 config for kobutachan-allaganeye.
# Ignore patterns must use `**/<name>/**` form (1-level paths break nested matches).
# Typical violation fixes (MD028 / MD056 / MD060) and ignore pattern history: see docs/markdownlint-guide.md
```

(YAML comment は `#`、既存 config の `globs:` などの直前に置く。indent はゼロ。)

- [ ] **Step 3.9: scripts/check-markdownlint.sh の error 出力に参照リンクを追加**

`scripts/check-markdownlint.sh` の current state を Read で確認。typical な構造は:

```bash
#!/usr/bin/env bash
set -euo pipefail
npx --prefix gui markdownlint-cli2 "**/*.md" "#node_modules" ...
```

script の末尾 (or trap 内) に以下のような hint print を追加 (lint failure 時のみ出力):

```bash
# scripts/check-markdownlint.sh の構造に応じて挿入
trap 'rc=$?; [[ $rc -ne 0 ]] && echo "See docs/markdownlint-guide.md for typical fixes (MD028 / MD056 / MD060) and ignore pattern rules." >&2; exit $rc' EXIT
```

(既存 trap がある場合は merge する。set -e で fail させたままで OK。)

- [ ] **Step 3.10: CLAUDE.md §コマンド の markdownlint 行直下に link を追加**

CLAUDE.md §コマンド の markdownlint 行:

```markdown
bash scripts/check-markdownlint.sh   # markdownlint (CI と同 version で全 .md チェック、--fix で自動修正)
```

の直下に以下の 1 行を追加:

```markdown
# violation の fix recipe / ignore pattern 規約は docs/markdownlint-guide.md を参照
```

- [ ] **Step 3.11: docs/markdownlint-guide.md header に non-skill 参照経路の note を追加 (任意)**

既存 `docs/markdownlint-guide.md` (commit adcae66 で作成済) の §1 強制パターン 直前に以下を追加 (optional、自然な flow):

```markdown
## このドキュメントの位置付け

- `.markdownlint-cli2.yaml` の header comment / `scripts/check-markdownlint.sh` の fail 時 hint / `CLAUDE.md` §コマンド の markdownlint 行直下 / `/review-pr` skill Step 5b / `/iterate-review` skill Step 2.4 から参照される
- 違反 fix で迷ったとき、ignore pattern を新規追加するとき、glob semantics を再確認したいときに引く
```

(既存 §1 の前に置く。`/review-pr` `/iterate-review` 参照は L-β でそれぞれの skill 側に reference を入れるが、本 doc の header note では先行的に列挙して発見可能性を確保する。)

### Step 3e: 検証と commit

- [ ] **Step 3.12: 全 reference link を grep で検証**

```bash
echo "--- markdownlint-guide refs ---"
grep -nE "markdownlint-guide" CLAUDE.md .markdownlint-cli2.yaml scripts/check-markdownlint.sh docs/markdownlint-guide.md
echo "--- l2-workflow 外部依存規約 refs ---"
grep -nE "外部依存規約|外部依存$" CLAUDE.md docs/l2-workflow.md
echo "--- refactor-pattern refs (Task 1 で追加分の再確認) ---"
grep -nE "refactor-pattern" CLAUDE.md docs/refactor-pattern.md
echo "--- encoding boundary refs ---"
grep -nE "encoding boundary" CLAUDE.md
```

Expected: 各セクションで該当 file に複数 hit (実装漏れがないこと)。

- [ ] **Step 3.13: 全 file の markdownlint check**

```bash
npx --prefix gui markdownlint-cli2 docs/l2-workflow.md docs/markdownlint-guide.md docs/refactor-pattern.md docs/release-process.md CLAUDE.md
```

Expected: 0 error。

- [ ] **Step 3.14: PR γ-3 を 1 commit にまとめる**

```bash
git add docs/l2-workflow.md docs/markdownlint-guide.md CLAUDE.md .markdownlint-cli2.yaml scripts/check-markdownlint.sh
git commit -m "$(cat <<'EOF'
docs: 外部依存規約 + encoding checklist + markdownlint 参照経路 (Refs spec L-γ M2/M4/M10)

retro spec §M2 / §M4 / §M10 の docs 側完成形を 1 PR に bundle:

- M2: docs/l2-workflow.md §外部依存規約 新設 (immutable URL pin、受け入れ可能ソース
  / 禁止パターン / 検証手順)。CLAUDE.md §外部依存 から link
- M4: CLAUDE.md §バグ修正時の方針 末尾に encoding boundary audit checklist
  追加 (Python / Rust / OS code page の 3 層)
- M10: 既存 docs/markdownlint-guide.md (commit adcae66) への non-skill 参照経路
  強化 — .markdownlint-cli2.yaml header / scripts/check-markdownlint.sh trap /
  CLAUDE.md §コマンド の markdownlint 行直下 / guide doc header の位置付け note

skill 側の参照リンク (/review-pr Step 5b / /scope-guard / /iterate-review Step 2.4)
は L-β skill 改訂 Lane で追加。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Lane 完了後の最終確認

- [ ] **Step 4.1: Lane γ の全 commit が claude/nervous-hoover-464244 branch HEAD に乗っていることを確認**

```bash
git log --oneline -8
```

Expected: 直近 3 commit が γ-1 / γ-2 / γ-3、その前に既存の retro spec / memory cleanup / O1-O5 / 追補 commits が並ぶ。

- [ ] **Step 4.2: 全 markdownlint pass**

```bash
bash scripts/check-markdownlint.sh
```

Expected: 0 error。

- [ ] **Step 4.3: 全 reference link が他 file から resolve できる**

```bash
echo "--- Lane γ で追加した全 ref を一括 grep ---"
grep -rnE "refactor-pattern|外部依存規約|encoding boundary|markdownlint-guide|Patch release.*Track" CLAUDE.md docs/ .markdownlint-cli2.yaml scripts/check-markdownlint.sh
```

Expected: 5 トピックすべてで 2+ file hit。

- [ ] **Step 4.4: PR 化判断 (本 Lane 単独で PR を出すか、L-α まで進めて bundle するか)**

Lane γ 単独で develop-0.3.0 への PR を出す: branch を develop-0.3.0 base で push → `gh pr create`。
L-α まで bundle: branch 維持で次 Lane plan 作成へ進む。

判断は user (Idios) に確認 (AskUserQuestion)。

---

## 受け入れ基準 (L-γ 全体)

spec §A1 / §A2 / §M2 / §M4 / §M10 の受け入れ基準のうち **docs 側に閉じる項目** をすべて満たす:

- [x] `docs/refactor-pattern.md` 存在 + AppError migration を実例として §3 reference に明示 + 判定基準 (§4) 記載
- [x] CLAUDE.md §開発ワークフロー / §リリース戦略 / §コマンド / §外部依存 / §バグ修正時の方針 から各 doc への参照リンク存在
- [x] `docs/release-process.md` §Patch release の Track 構造 が v0.2.1 を reference に持つ
- [x] `docs/l2-workflow.md` §外部依存規約 が受け入れ可能ソース / 禁止パターン / 検証手順を持つ
- [x] `.markdownlint-cli2.yaml` header + `scripts/check-markdownlint.sh` trap から `docs/markdownlint-guide.md` への参照
- [x] 全 markdownlint pass

skill 側参照リンク (`/review-pr` Step 5a / 5b、`/iterate-review` Step 2.4、`/scope-guard`、`/release` Step 0、`/create-task`) は **L-β scope** で達成する。本 plan の受け入れ基準には含めない。

## リスクと緩和策

| # | リスク | 緩和 |
| --- | --- | --- |
| RL1 | CLAUDE.md への追記で行数増加 (200 行制限の MEMORY.md 規約とは別だが、認知負荷) | 各追記を 5-10 行以内の要約 + doc へのリンクで構成、本文の詳細は docs/ に置く |
| RL2 | scripts/check-markdownlint.sh の trap 改変で既存挙動が変わる | exit code は preserve、stderr に 1 行追加するのみ。CI も pass する設計 |
| RL3 | markdownlint-guide.md の参照経路 5 件のうち skill 側 2 件 (review-pr / iterate-review) が本 Lane 外のため、L-γ 単独 review では参照不完全に見える | PR 本文に「skill 側は L-β scope」と明記、L-γ 単独 acceptance は §A1 / §M10 の docs 部分のみ |

---

## 次の Lane plan 作成 tasks (L-γ 完了後に着手)

L-γ 実装で得た学び (CLAUDE.md 編集 pattern、markdownlint hint の入れ方等) を踏まえ、以下 3 plan を順次作成する。本 plan のテンプレートを reuse 可能:

- `docs/superpowers/plans/2026-05-17-v030-lane-alpha-ci-hook.md` (M1 / M6 / M7)
- `docs/superpowers/plans/2026-05-17-v030-lane-beta-skill-revision.md` (M3 / M5 / M9 / C2 / C3 / C4 / C6 skeleton + skill 側 reference links)
- `docs/superpowers/plans/2026-05-17-v030-lane-delta-codex-ops.md` (C1 / C5 / C6 完成版)
