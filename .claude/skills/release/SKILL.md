---
name: release
description: deferred issue レビュー → バージョンバンプ → リリース PR 作成を自動化する
---

# リリーススキル

バージョンバンプとリリース PR を作成します。

## 引数

`$ARGUMENTS` にバージョン種別を指定（省略時は自動判定）:

- `patch`: バグ修正のみ
- `minor`: 新機能追加
- `major`: 破壊的変更

自動判定ルール（引数省略時）: 前回タグ以降のコミット prefix から判定。`feat:` / `feat(...)` があれば minor、`!` または `BREAKING CHANGE` があれば major、それ以外（`fix` / `docs` / `refactor` / `chore` / `test` のみ）は patch。判断が曖昧な場合はユーザーに確認する。

## 手順

### Step 0a: リリース受け入れゲートの確認（必須）

リリース PR を作成する前に、[`docs/release-process.md` §レイヤーリリース受け入れゲート](../../../docs/release-process.md) のチェックリストを全件達成しているか確認する。本ステップはスキップできない。

1. 対象バージョン (例 `v0.2.0`) を特定し、§共通項目 + §`v0.x.0` (L?) 固有項目 の 2 ブロックをユーザーに提示
2. 各項目について「達成 / 未達成 / 該当なし」を 1 件ずつ確認 (3 件以上の bulk 確認になる場合はサンプル提示 + 全件 OK / 個別調整 / 中止 の 3 択)
3. 1 件でも未達成があれば本スキルは中断し、ユーザーに残タスクの優先処理を依頼
4. 全件達成を確認してから Step 0b へ進む

注意: 本ゲートは Iron Law 1 (受け入れ条件全充足) のリリースレベル展開。`deferred` review (Step 0b / 0c) はゲート §共通項目内の 1 行に対応するため、Step 0b / 0c はゲート確認の延長として扱う。

### Step 0b: deferred 全件取得 (M9、F8 教訓)

リリース前に `deferred` ラベル付き issue を全件取得する。**release-blocker label は新設しない** (M8 撤回、2026-05-17 確定) — 取得対象は `deferred` 単独で十分。

```bash
gh issue list --repo Idios/kobutachan-allaganeye --state open --label "deferred" --limit 200 \
  --json number,title,labels,createdAt,updatedAt
```

- 件数 0 → Step 1 へ skip
- 件数 ≥1 → Step 0c で全件分類

### Step 0c: deferred 1 件ずつ 3 択分類 (M9 再設計版)

Step 0b で取得した各 deferred issue について、AskUserQuestion で以下 3 択を user に提示:

- **(a) 次 release で吸収**: 本 release / 次 patch の **Track B 吸収候補** とする。spec PR (Track 0) の table に記録
- **(b) deferred 継続**: ラベル変更なし。本 release では取り込まない (次 cycle に再評価)
- **(c) close**: `gh issue close <番号> --comment "<理由>"` でクローズ (won't fix / 再現不能 / 仕様変更等)

#### bulk 件数の運用 (Iron Law 2 整合)

- 件数 ≤2: 1 件ずつ AskUserQuestion で個別確認
- 件数 ≥3: **先に Iron Law 2 bulk pre-check** (サンプル 1 件提示 + 「全件 OK / 個別調整 / やめる」3 択) → 「個別調整」選択時のみ 1 件ずつの確認に進む

#### Step 0c 結果の spec PR table 化 (Track 0)

(a) / (b) / (c) 各分類結果を spec PR (Track 0、`docs/superpowers/specs/<date>-v0.M.N+1-patch-design.md`) の §deferred 全件検証結果 table に保存:

```markdown
### §deferred 全件検証結果 (`/release` Step 0c)

| issue # | title | 分類 | 判断理由 |
| --- | --- | --- | --- |
| #374 | ... | (a) 次 patch 吸収 | UX critical |
| #432 | ... | (b) deferred 継続 | L3 scope |
| #555 | ... | (c) close | 再現不能 |
```

(a) と分類された issue 群が [`docs/release-process.md` §Patch release の Track 構造](../../../docs/release-process.md#patch-release-の-track-構造) の **Track B 吸収候補** となる。Track B PR は本 spec PR の table をリンクで引く。

#### Step 0c で block する条件 (release PR 作成前 gate)

- deferred 件数 > 0 かつ Step 0c の確認が完了していない → release PR 作成を block (本 skill が abort)
- (a) 分類 issue 群が次 release scope に取り込まれる commit / PR plan を持たない → block (`/iterate-review` / `/create-task` で Track B PR の plan を先に作る)

F8 (deferred 持ち越し: #374 / #458 / #743 / #749 / #756 が v0.2.1 まで漏れた事例) の根本対策。

### Step 2: リリース準備

1. 現在のバージョンを `pyproject.toml` から取得
2. 前回リリースタグ以降のコミットを分析:

   ```bash
   git log $(git describe --tags --abbrev=0 2>/dev/null || echo "HEAD~50")..HEAD --oneline
   ```

3. バージョン種別を決定（引数指定 or 上記「自動判定ルール」）
4. ベースブランチを特定:
   - **minor/major**: 現在の `develop-<新バージョン>` （既存 develop ブランチ）
   - **patch**: ホットフィックス扱い。現在の `develop-<新バージョン>` がある場合はそこへ、無ければ `main` へ PR。判断が曖昧な場合は `git branch -r | grep -E 'origin/develop-|origin/main'` の結果を提示してユーザー確認

### Step 3: バージョンバンプと PR 作成

1. **事前品質チェック** ([`docs/l2-workflow.md`](../../../docs/l2-workflow.md) §「PR 作成 path 別自動チェック」):

   ```bash
   ruff check .
   ruff format --check .
   pytest
   pyright
   ```

   いずれか失敗したら修正してから以下に進む
2. `pyproject.toml` の `version` を更新（他にバージョン参照箇所があれば `grep -r '<旧バージョン>' --include='*.py' --include='*.toml'` で確認し同時更新）
3. リリースブランチを作成（Step 2-4 で特定したベースブランチから分岐）:

   ```bash
   git checkout <ベースブランチ>
   git pull
   git checkout -b release/v<新バージョン>
   ```

4. 変更をコミット（session-id を含める、[`docs/l2-workflow.md`](../../../docs/l2-workflow.md) §「PR 規約」 §「コミットメッセージ session-id」）:

   ```bash
   git add pyproject.toml
   git commit -m "chore: bump version to <新バージョン> [<session-id>]"
   ```

5. リリースブランチを push:

   ```bash
   git push -u origin release/v<新バージョン>
   ```

6. リリース PR を作成（base は Step 2-4 で特定したベースブランチ、Windows + Git Bash での日本語本文破損回避のため `printf | --body-file -` 方式）:

    ```bash
    printf '%s\n' "## Release v<新バージョン>

    ### 変更内容
    <コミット分析結果のサマリー>

    ### deferred issue レビュー結果
    <Step 1 の判断結果を記載>

    ### チェックリスト
    - [ ] バージョン番号が正しい
    - [ ] 全テスト通過 (\`pytest\`, \`ruff check .\`, \`ruff format --check .\`, \`pyright\`)
    - [ ] deferred issue を全件レビュー済み
    - [ ] CLAUDE.md の更新が必要な変更はない

    作成: <session-id>" | gh pr create \
      --title "Release v<新バージョン>" \
      --body-file - \
      --base <ベースブランチ> \
      --label "release" \
      --assignee Idios
    ```

7. ユーザーに PR URL とバージョン変更内容を報告

### タグ打ち・GitHub Release 作成

リリース PR マージ後の手順（本スキル範囲外、`docs/release-process.md` §タグ運用 を参照）:

- patch リリース: マージされたブランチで `git tag v<新バージョン>` → `git push origin v<新バージョン>`
- minor/major リリース: `develop-<新バージョン>` を `main` にマージしてから `main` でタグ打ち
- `gh release create v<新バージョン> --notes-from-tag` で GitHub Release 作成
