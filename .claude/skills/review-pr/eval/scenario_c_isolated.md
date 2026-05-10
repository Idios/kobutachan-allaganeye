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

```text
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

## 期待される出力と挙動

### §A フォールバック適用 (孤立 PR)

- 環境制約節 §A (孤立 PR) のフォールバックを適用すること
- `/enforce-acceptance-criteria` は issue 未紐付けのため実行不可 → 代替: PR 本文の目的記述を受け入れ条件の代替として逐条検証
- Step 6 テンプレートの「受け入れ条件チェック」セクションは「該当なし (issue 未紐付け)」と明記し、代替判定根拠を箇条書き
- Step 8 は「紐づく issue がない場合」の分岐に従い `/close-issue` 案内は省略可

### Step 6 (レビュー報告)

- Step 5b トリアージ表を含む**レビュー報告 markdown を生成して presenting する**
- `AskUserQuestion` は呼ばない。`gh pr comment` 等の **PR コメント投稿は一切行わない**
- `CLAUDE.md` 内の `gui/dist/` 未更新箇所 (仕込み要素 2) は (A) として転記
- `.github/workflows/` CI 設定への波及リスク (仕込み要素 2) も (A) として転記
- トリアージ表を省略しない (「軽微」「doc-only」を理由に握り潰さない)

### Step 7 (次のアクション提案)

- 次のアクション提案テンプレートを user に提示する:
  - 判定: 修正依頼 ((A) 課題が残っているため) または LGTM (課題ゼロの場合)
  - 修正依頼の場合: **`/iterate-review $ARGUMENTS` 起動推奨**を明記
  - 孤立 PR では `/close-issue` 案内省略可 (Step 8 分岐に従う)

### per-finding comment 投稿しない

- Step 7 で PR コメント (`gh pr comment`) を自動投稿しない。これは仕様
- 投稿が必要な場合はユーザーが手動で行う

### subagent が判断すべき論点

- 孤立 PR (issue なし) に対して受け入れ条件ゲートをどう扱うか (§A フォールバック適用)
- doc 修正に潜む実装コード / CI 設定への波及リスクをどこまで追跡するか
- 「軽微」ラベルを理由に Step 5b トリアージ表を省略していないか
- LGTM 判定の閾値: 明確な不整合が 2 箇所あるが、「doc-only のスコープでは OK」とするか「修正依頼」とするか
