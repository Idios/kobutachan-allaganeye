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

1. 現在のバージョンを `pyproject.toml` から取得
2. 前回リリースタグ以降のコミットを分析:
   ```bash
   git log $(git describe --tags --abbrev=0 2>/dev/null || echo "HEAD~50")..HEAD --oneline
   ```
3. バージョン種別を決定（引数指定 or コミット内容から自動判定）
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

   ### チェックリスト
   - [ ] バージョン番号が正しい
   - [ ] 全テスト通過
   - [ ] CLAUDE.md の更新が必要な変更はない
   EOF
   )" --label "release"
   ```
8. ユーザーに PR URL とバージョン変更内容を報告
