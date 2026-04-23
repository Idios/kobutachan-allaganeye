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

### Step 1: deferred issue のレビュー（必須）

リリース前に `deferred` ラベル付き issue を全件レビューする。このステップはスキップできない。

```bash
gh issue list --repo Idios/kobutachan-allaganeye --state open --label "deferred" --json number,title,labels
```

- 各 issue について、以下の 3 択をユーザーに確認する:
  - **[A] 次バージョンのスコープに含める**: `deferred` を外し、適切なスコープラベル + 優先度ラベル（`P1-high` / `P2-medium` / `P3-low`、ユーザーに選択を求める）に変更
  - **[B] 引き続き deferred**: ラベル変更なし。理由を PR 本文に記載
  - **[C] クローズ**: `gh issue close <番号> --comment "<理由>"` でクローズ
- deferred issue が 0 件の場合のみ自動で次ステップに進む
- 1 件以上ある場合: **必ずユーザーに判断を求めてから** 次に進む
- 3 件以上の bulk 操作になる場合は CLAUDE.md §「自律判断マトリクス」に従い、実行前にサンプル 1 件を提示してユーザー確認を取る

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

1. **事前品質チェック** (CLAUDE.md PR 作成ルール):

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

4. 変更をコミット（session-id を含める、CLAUDE.md PR 作成ルール）:

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
