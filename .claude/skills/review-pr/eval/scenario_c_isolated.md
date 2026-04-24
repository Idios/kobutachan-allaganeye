# シナリオ C: edge - 孤立 PR (紐づく issue なし、doc-only、CI 観点欠如)

参考事例: #495 (docs installer Portable ZIP) / #497 (外部ユーザー bug report)

## 紐づく issue

**なし** (chore-level の doc 軽微修正として PR 直接作成された)

---

## モック PR #920

**タイトル**: `docs(gui): GUI インストール手順を最新 Tauri bundle 配置に追従`

**baseRefName**: `develop-0.2.0`

**labels**: `[doc]`, `l2a-gui`

**本文**:
```markdown
## 概要

GUI の動作確認手順ドキュメントで参照しているビルド成果物パスが旧世代のまま。
最新の Tauri 2.x bundle 配置に追従する軽微な修正。

- `docs/gui-development.md` 内の `gui/dist/` 記述を `gui/src-tauri/target/release/bundle/` に更新
- README.md のセットアップ手順で言及している関連コマンドを最新化

## 動作確認

手動で手順をなぞって起動可能なことを確認済み。
ドキュメントのみの修正なので追加テストは不要。
```

---

## 主要 diff 要約 (+28 / -22)

```
docs/gui-development.md             +18 -15    # gui/dist → gui/src-tauri/target/release/bundle
README.md                           +8  -5     # セットアップ手順のパス追従
docs/design/README.md               +2  -2     # 関連する 1 箇所のパス追従
```

### 意図的に仕込んだ要素 (subagent が摘出できるか試す)

1. **紐づく issue なし**: PR 本文に issue 参照がない。`/enforce-acceptance-criteria` は受け入れ条件が存在しないため動作できない。環境制約節のフォールバックが必要
2. **ドキュメント整合性の追加漏れ**:
   - `CLAUDE.md` 内でも `gui/dist/` を 1 箇所参照している (§モジュール構成 表内) が更新されていない → 摘出対象
   - `.github/workflows/` の CI 設定で `gui/dist` を参照している YAML が 1 ファイルあるが更新されていない (実際には path が変わると CI が壊れる可能性) → 摘出対象
3. **CI 確認の不在**: PR 本文に「ドキュメントのみなのでテスト不要」と記載。CI の lint/test は pass しているが、パス変更が CI 設定に影響していないかの確認が欠落
4. **スコープ判定の曖昧さ**: 「軽微」とされるがパス変更は実装コードと CI 設定に影響し得る。doc-only と見なして処置を軽くすべきか、影響範囲調査を要求すべきかの判断点
5. **握り潰しリスク**: CI 設定の更新漏れは「PR のスコープは doc 修正だから別 issue」と判断して (B) 新規 issue に回すのが正しい。(A) PR コメントで即修正を要求するほどか否かの判定が必要

## 検証環境情報

- CI: green (lint / test は pass だが、パス変更が workflow yaml に波及していない点は自動検知されていない)
- 紐づく issue: なし
- `/enforce-acceptance-criteria` gate: 実行不可 (受け入れ条件が存在しない)
- `/test-pr`: 該当なし (doc-only)

### subagent が判断すべき論点

- 孤立 PR (issue なし) に対して受け入れ条件ゲートをどう扱うか
- doc 修正に潜む実装コード / CI 設定への波及リスクをどこまで追跡するか
- 「軽微」ラベルを理由に Step 5b トリアージ表を省略していないか
- LGTM 判定の閾値: 明確な不整合が 2 箇所あるが、「doc-only のスコープでは OK」とするか「修正依頼」とするか
