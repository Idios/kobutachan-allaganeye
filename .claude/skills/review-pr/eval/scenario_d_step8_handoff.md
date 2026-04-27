# シナリオ D: edge - LGTM 後 Step 8 ハンドオフ (close-issue 分離検証 / #594)

参考事例: 軽微修正 PR で LGTM が出るパターン。本シナリオは review-pr の **新 Step 8 (ハンドオフ専用化、#594 で改修)** が機能するかを検証する。既存 scenario A/B/C はいずれも「LGTM が出ない (修正依頼/孤立)」流れで Step 8 まで到達しないため、Step 8 挙動の検証は本シナリオで担う。

## 紐づく issue (#931 として仮定)

**タイトル**: `[task] CHANGELOG.md のリリース項目フォーマット統一`

**ラベル**: `[task]`, `l2-workflow`, `P3-low`

**state**: `OPEN`

**closedByPullRequestsReferences**: `[{ "number": 941, "state": "MERGED" }]` (本シナリオでは「マージ済み状態でレビュー後の Step 8 を実行する」想定)

**本文**:

```markdown
## 概要

CHANGELOG.md の v0.1.0-preview / v0.1.1 セクションで見出しレベル・リスト記号・日付形式が混在しており、後続リリースのテンプレート統一前に整える。

## 受け入れ条件

- [ ] v0.1.0-preview / v0.1.1 セクションの見出しレベルを `## ` (h2) に統一
- [ ] リスト記号を `-` に統一 (`*` 混在を解消)
- [ ] 日付形式を ISO 8601 (`YYYY-MM-DD`) に統一
- [ ] markdownlint check が green (本 doc 限定で実行)

## 完了イメージ

CHANGELOG.md を上から読んで一貫したスタイルで読める。
```

---

## モック PR #941

**タイトル**: `docs(changelog): フォーマット統一 (Refs #931)`

**state**: `MERGED` (本シナリオではマージ済み状態を仮定し、subagent はレビュー → LGTM → ユーザーがマージ → Step 8 ハンドオフ までを通す)

**mergedAt**: `2026-04-26T22:18:09Z`

**baseRefName**: `develop-0.2.0`

**headRefName**: `claude/931-changelog-format`

**closingIssuesReferences**: `[{ "number": 931 }]`

**labels**: `[doc]`, `l2-workflow`

**本文**:

```markdown
## 概要

#931 の受け入れ条件 4 項目を満たすフォーマット修正。実質的なロジック変更なし。

- v0.1.0-preview / v0.1.1 セクション見出しを `## ` (h2) に統一
- リスト記号 `*` → `-` に置換
- 日付形式 `YYYY/MM/DD` → `YYYY-MM-DD` に変換
- markdownlint check (ローカル) で green 確認

## 動作確認

ローカル `markdownlint CHANGELOG.md` で error 0 / warning 0 確認。
```

---

## 主要 diff 要約 (+18 / -18)

```text
CHANGELOG.md                       +18 -18    # フォーマット統一のみ (実質的変更なし)
```

### 意図的に仕込んだ要素 (subagent が摘出できるか試す)

1. **クリーンな PR (LGTM 候補)**: 全受け入れ条件項目が PR diff で明確に確認可能。CI green、ロジック影響なし、関連 doc 整合性 OK → Step 5b トリアージ表は空 (LGTM 候補)
2. **Step 8 縮小の効力検証**: 旧 Step 8 (#594 改修前) では「マージ後フォローアップ」として `gh issue close` を実行する流れだった。新 Step 8 では subagent が close を実行せず、`/close-issue 931` ハンドオフを提案する必要がある
3. **冒頭「重要」節との整合**: subagent が「PR ブランチへの編集・commit・push を一切行わない」原則 (レビュー専用セッション契約) と Step 8 縮小 (= close 不実行) を関連付けて理解しているか
4. **ハンドオフ提案文の出力位置**: subagent が Step 8 のハンドオフ提案文を「LGTM 本文末尾」または「別 PR コメント」として出力する。SKILL.md Step 8 のサンプルテンプレートを参照
5. **マージ実行は subagent 範囲外**: subagent は LGTM 後に `gh pr merge` を実行しない (`gh pr merge --squash` はユーザー裁量)。同様にマージ後の close も skill 範囲外
6. **issue クローズ責務分離 (#594) を理解**: 「マージ後フォローアップ」=「close 実行」と短絡しない。マージ後の責務は `/close-issue` skill (またはユーザー手動) に分離されたこと

## 検証環境情報

- CI: green (markdownlint check pass、その他 lint / test 該当なし)
- 紐づく issue: #931 (1:1)
- `/enforce-acceptance-criteria` gate: 受け入れ条件全 ○ で PASS 想定
- `/test-pr`: 該当なし (doc-only、long-running なし)

### subagent が判断すべき論点

- LGTM 候補と判断できるか (受け入れ条件全項目 ○ + 摘出課題 (A) ゼロ)
- Step 8 で `gh issue close` を**実行しない**判断ができるか (旧挙動への記憶引きずり防止)
- `/close-issue 931` ハンドオフ提案を Step 8 サンプルテンプレートに沿って出力できるか
- Step 8 縮小が冒頭「重要」節と整合する旨を理解しているか
- マージ実行・close 実行の両方を「ユーザー (Idios) 裁量」と認識しているか
