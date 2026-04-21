---
name: release
description: バージョンバンプとリリースPRの作成を自動化する
---

# リリーススキル

バージョンバンプとリリース PR を作成します。

## 引数

`$ARGUMENTS` にバージョン種別を指定（省略時は自動判定）:
- `patch`: バグ修正のみ
- `minor`: 新機能追加
- `major`: 破壊的変更

## 手順

### Step 1: deferred issue のレビュー（必須）

リリース前に `deferred` ラベル付き issue を全件レビューする。このステップはスキップできない。

```bash
gh issue list --repo Idios/kobutachan-allaganeye --state open --label "deferred" --json number,title,labels
```

- 各 issue について、次バージョンのスコープに含めるか・引き続き deferred かをユーザーに確認する
- スコープに含める場合: `deferred` を外し、適切なスコープラベル + 優先度ラベルに変更
- deferred issue が 0 件の場合のみ自動で次ステップに進む
- 1 件以上ある場合: **必ずユーザーに判断を求めてから** 次に進む

### Step 2: リリース準備

1. 現在のバージョンを `pyproject.toml` から取得
2. 前回リリースタグ以降のコミットを分析:
   ```bash
   git log $(git describe --tags --abbrev=0 2>/dev/null || echo "HEAD~50")..HEAD --oneline
   ```
3. バージョン種別を決定（引数指定 or コミット内容から自動判定）

### Step 3: バージョンバンプと PR 作成

4. `pyproject.toml` の `version` を更新
5. リリースブランチを作成:
   ```bash
   git checkout -b release/v<新バージョン>
   ```
6. 変更をコミット:
   ```bash
   git add pyproject.toml
   git commit -m "chore: bump version to <新バージョン>"
   ```
7. リリース PR を作成:
   ```bash
   gh pr create --title "Release v<新バージョン>" --body "$(cat <<'EOF'
   ## Release v<新バージョン>

   ### 変更内容
   <コミット分析結果のサマリー>

   ### deferred issue レビュー結果
   <Step 1 の判断結果を記載>

   ### チェックリスト
   - [ ] バージョン番号が正しい
   - [ ] 全テスト通過
   - [ ] deferred issue を全件レビュー済み
   - [ ] CLAUDE.md の更新が必要な変更はない
   EOF
   )" --label "release" --assignee Idios
   ```
8. ユーザーに PR URL とバージョン変更内容を報告
