# GitHub Issue 作成ポリシー

> 対象: このリポジトリで作業する全エージェント（Claude Code / Codex / その他 LLM）および人間

---

## 1. 基本ルール

- **アサイン**: 全 issue を `Idios` にアサインする
- **言語**: タイトル・本文ともに日本語で記述する
- **重複確認**: issue を作成する前に既存 issue を検索し、同一内容がなければ作成する
- **粒度**: 1 issue = 1 つの問題・タスク。複数の問題をまとめない
- **作成者の明示**: 本文の末尾に `作成: <session-id>` を記載する（例: `作成: lead-1`）。issue クローズ時の責任者特定に使用する

---

## 2. タイトル形式

```json
[prefix] 概要を簡潔に（〜40文字以内）
```

### prefix 一覧

| prefix | 意味 | GitHub ラベル |
| -------- | ------ | -------------- |
| `[bug]` | 動作が仕様・期待と異なる不具合 | `bug` |
| `[doc]` | ドキュメントの誤記・矛盾・欠落 | `doc` |
| `[refactor]` | 振る舞いを変えないコード改善 | `refactor` |
| `[question]` | 設計意図の確認・判断が必要な事項 | `question` |
| `[risk]` | セキュリティ・運用上のリスク・懸念 | `risk` |
| `[task]` | 調査・確認・セットアップ作業 | `task` |

### スコープラベル

上記の prefix ラベルに加えて、対象スコープに応じて以下のラベルを付与する。

| ラベル | 対象スコープ |
| -------- | ----------- |
| `l2a-gui` | L2 GUI 関連 (#105 系) |
| `l2b-installer` | L2 インストーラ関連 (#106 系) |
| `l2-workflow` | 開発プロセス改善 + allaganeye-guard 運用連携 doc 整備 |
| `l2-decision` | 方針判断が必要な issue |
| `l1-residual` | L1 残課題 (#412-#440 系) |

> `l2c-guard` ラベルは 2026-04-21 廃止 (guard との program integration 構想を破棄、#454 参照)。関連 doc 整備は `l2-workflow` で追跡。

L3 以降のレイヤーは着手時に運用ルールを判断する。v0.3.0 (新 L3) は新規ラベルを追加せず title prefix で識別する (詳細は下の §v0.3.0 新 L3 work の title prefix 規約 参照)。

#### v0.3.0 新 L3 work の title prefix 規約

v0.3.0 (= 新 L3) work では **新規 layer label を追加しない**。issue title prefix で識別する:

```text
[type] L3: <要約>                                    ← 新 L3 (VTuber+minimap+perf, v0.3.0 target)
[type] L4 (former L3): <要約>                        ← 旧 L3 (OCR/Whisper), L4 にスライド
[type] L5 (former L4): <要約>                        ← 旧 L4 (ML)
[type] L6 (former L5): <要約>                        ← 旧 L5 (auto edit)
[type] L7 (former L6): <要約>                        ← 旧 L6 (privacy)
```

詳細は [`docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md`](superpowers/specs/2026-05-18-v030-l3-redefinition-design.md) §5 を参照。

### 優先度ラベル

issue の優先度を示すラベル。全 issue に必須ではなく、優先順位の判断が必要な場合に付与する。

| ラベル | 意味 | 付与基準 |
| -------- | ------ | ---------- |
| `P1-high` | 高: 後続タスクの前提条件となる | 他の issue やリリースがこの完了を待っている |
| `P2-medium` | 中: 計画内で対応すべき | ロードマップ上のタスク、品質改善 |
| `P3-low` | 低: 余裕があれば対応 | 技術的負債、改善提案、調査 |

- 優先度の判断はユーザー (Idios) が行う。Claude は `AskUserQuestion` で選択肢を提示
- 優先度ラベルは prefix ラベル・スコープラベルと併用する
- 判断が難しい場合はラベルなしでよい（未付与 = 未判定）

### path↔scope 対応表 (preuse.py scope check 用、M7)

`.claude/hooks/preuse.py` の git commit pre-hook がこの表を参照して **multi-scope detection** を行う。新規 top-level dir を repo に追加した時は本表も同時に更新すること (path↔scope のメンテ責任)。

| path glob (regex 風) | scope label | 該当 prefix label |
| --- | --- | --- |
| `^allaganeye/` | l1-cli | bug / refactor / task |
| `^tests/` | l1-cli | test |
| `^gui/src/` | l2a-gui | feat(gui) / fix(gui) |
| `^gui/src-tauri/` | l2a-gui | feat(gui) / refactor(gui) |
| `^gui/scripts/` | l2a-gui | task |
| `^gui/[^/]+$` (catch-all、`gui/` 直下の package.json / vite.config.ts / index.html / tsconfig*.json / eslint.config.js / .prettierrc.json / README.md / .gitignore / package-lock.json 等) | l2a-gui | feat(gui) / chore(gui) |
| `^scripts/` | l2b-installer | feat(installer) / fix(installer) |
| `^\.github/workflows/` | l2-ci | ci |
| `^\.github/ISSUE_TEMPLATE/` | l2-workflow | task / doc |
| `^\.claude/` | l2-workflow | refactor(skill) / chore(hooks) |
| `^docs/` | l2-docs | doc |
| `^CLAUDE\.md$` | l2-docs | doc |
| `^README\.md$` | l2-docs | doc |
| `^pyproject\.toml$` | l1-cli | chore |
| `^\.markdownlint-cli2\.yaml$` | l2-ci | chore(ci) |
| `^\.gitignore$` | l2-workflow | chore |

#### 判定規則

- **distinct scope 数 ≥ 2**: multi-scope commit。preuse.py が `permissionDecision=ask` で 3 択 (a) revert / (b) 別 issue / (c) scope 拡大 を user に提示
- **unknown path**: 上記表に hit しない path が staged されている。preuse.py が ask 判定。本表に追記するか、確かに新規 scope なら scope 拡大として user 承認

#### メンテナンス

新規 top-level dir (例: `audit/` 新設) を repo に追加するときは:

1. 本表に対応行を追加 (scope label を決める)
2. `.claude/hooks/preuse.py` の `_PATH_SCOPE_MAP` (in-source の正本) も同期更新

doc と source の同期は CI で drift check 可能 (future)。

---

## 3. 本文フォーマット

prefix に応じて以下のテンプレートを使用する。

### [bug] テンプレート

```markdown
## 概要
<1〜2 文で何が起きているか>

## 該当コード
<ファイルパス:行番号> または コードブロック

## 問題
<なぜ誤りか、どんな条件で発現するか>

## 修正方針
<修正方法の案>
```

### [doc] テンプレート

```markdown
## 概要
<何がどう誤っているか>

## 対象箇所
<ファイルパス と 行番号またはセクション名>

## 誤記内容 / 矛盾内容
<現状の記載 vs 正しい内容（表形式推奨）>

## 対応方針
<修正方法の案>
```

### [refactor] テンプレート

```markdown
## 概要
<何を改善したいか>

## 該当箇所
<ファイルパス:行番号>

## 問題
<現状の何が問題か>

## 対応方針
<改善方法の案>
```

### [question] テンプレート

```markdown
## 概要
<何を確認したいか>

## 現状
<現在のコード・ドキュメントの状態>

## 確認事項
<箇条書きで確認したい点>

## 対応方針
<確認後に想定される対応>
```

### [risk] テンプレート

```markdown
## 概要
<どんなリスク・懸念があるか>

## 現状
<現在の状態>

## 問題
<何がリスクになるか、どんな被害が起きうるか>

## 対応方針
<リスク低減策の案>
```

### [task] テンプレート

```markdown
## 概要
<何をするタスクか>

## 背景
<なぜこのタスクが必要か>

## 確認項目 / 作業項目
- [ ] 項目1
- [ ] 項目2

## 対応方針
<作業の進め方・完了条件>
```

---

## 4. issue を作成すべきケース

以下の場合は issue を作成する：

- コードまたはドキュメントに誤り・矛盾・欠落を発見したが、**現在のタスクのスコープ外**である
- 修正が必要だが、**設計判断が必要**で自律的に直せない
- 将来対応すべき**技術的負債・未決事項**を記録したい

---

## 5. issue を作成すべきでないケース

以下の場合は issue を作成せず、直接修正する：

- 現在のタスクのスコープ内で即座に直せる軽微な誤字・フォーマット
- ユーザーから明示的に修正を依頼されている

---

## 6. コミットと issue の紐付け

issue に関連するコミットを作成する場合、コミットメッセージに `#番号` を含める。

```text
fix: total_assets=0 のとき誤フォールバックする不具合を修正 (#7)
```

### ルール

- **関連する issue がある修正には必ず `#番号` を含める**
- `Closes` / `Fixes` / `Resolves` キーワードは使わない（issue のクローズは手動で行う。詳細は §7 参照）
- 1つのコミットが複数の issue に関連する場合は全て記載する（例: `#2, #3`）

---

## 7. Issue のライフサイクル管理

Issue のスコープラベル (`l2a-gui`, `l2b-installer` 等) と優先度で作業対象を特定する。

### コメント確認原則

issue の状態を判断する前に、**必ずコメント全文を確認する**（`gh issue view <番号> --comments`）。ボディだけで状態を判断してはならない。コメントには着手宣言、完了報告、テスト結果など、ボディに反映されていない最新情報が含まれる。

### 着手時

- issue にコメント `着手: <session-id>` を投稿する（監査・トレーサビリティ用に worktree 名を記録）

### 完了時（PR 作成時）

作業完了後に PR を提出したら、以下を行う:

1. **issue にコメント**: `完了: <session-id> → PR #番号`（対応内容の要約を添える）
2. **チェックボックスの更新**: issue 本文にチェックボックス（`- [ ]`）がある場合、完了した項目にチェックを入れる（`gh issue edit <番号> --body "..."` で本文を更新）

```bash
# 完了コメントの例
gh issue comment <番号> --body "完了: relaxed-mestorf-9807da → PR #42
暗転検知の閾値パラメータを追加"
```

### PR マージ後（クローズ）

PR マージ後、受け入れ条件を**マージ後 base ブランチで実測再検証**してから関連 issue をクローズする (Iron Law 4)。クローズは以下のいずれかのルートで実施する:

- **`/close-issue <issue番号>` skill** (推奨、#594 で新設): マージ後の受け入れ条件実測再検証 + 残タスクトリアージ + ユーザー承認後の close を一気通貫で実施
- **ユーザー (Idios) 手動クローズ**: 上記と同等の検証を手動で実施

```bash
# 手動クローズ時のコマンド例
gh issue close <番号> --repo Idios/kobutachan-allaganeye \
  --comment "マージ確認: <session-id> ← PR #番号"
```

詳細は `docs/l2-workflow.md` §「Issue クローズルール」 / `.claude/skills/close-issue/SKILL.md` を参照。

**例外: 未完了のチェックボックスがある場合**

issue 本文に未チェックの項目（`- [ ]`）が残っている場合、クローズせず残作業を継続する。残タスクが別スコープになる場合は子 issue を新規起票し、親 issue 本文に子 issue 番号を記載する (#367 対策)。

---

## 8. Issue クローズポリシー

### クローズしてよいケース

| ケース | 例 |
| --- | --- |
| 問題が解決した | PR マージにより修正完了 |
| 重複 | 別 issue で対応済み |
| 対応不要と最終判断 | 仕様通り（won't fix）、再現不能 |
| 無効化 | 前提が変わり issue 自体が無意味に |

### クローズしてはいけないケース

| ケース | 代わりの対応 |
| --- | --- |
| 現バージョンのスコープ外 | `deferred` ラベルを付与して open のまま残す |
| 優先度が低い | `P3-low` ラベルのまま open |

**「スコープ外 ≠ クローズ」が原則**。未解決の issue をクローズすると将来の再検討漏れにつながる。

### `deferred` ラベルの運用

- **付与タイミング**: 現バージョンのスコープ外と判断した時点で付与する
- **見直しタイミング**: バージョンリリース（タグ打ち）時にユーザー (Idios) が全 `deferred` issue をレビューし、次バージョンのスコープに含めるか判断する
- **スコープに含める場合**: `deferred` を外し、適切なスコープラベル + 優先度ラベルに変更する
- **引き続き先送りの場合**: そのまま残す

#### v0.3.0 期間中の運用 (2026-05-18 以降)

**`deferred` ラベルを外す = v0.3.0 (新 L3) で必須対応** と扱う:

- v0.3.0 着手対象に選定された issue: `deferred` を外す
- それ以外の issue (旧 L3 = L4 へ繰り下げ、旧 L4-L6 等): `deferred` を維持
- 検索: v0.3.0 アクティブセット = `is:open -label:deferred`

詳細は [`docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md`](superpowers/specs/2026-05-18-v030-l3-redefinition-design.md) §5.2 を参照。

#### `l1-residual` + `deferred` dual-label 規約

`l1-residual` ラベル**単独では** v0.2.0 (L2) scope から自動で外れない。L1 期間積み残し issue を現バージョン (L2 以降) scope 外と明示するには **`deferred` + `l1-residual` の dual-label** が必要。両ラベルは別目的:

- `deferred` = scope 判定 (現バージョンで対応しない、release 時にレビュー)
- `l1-residual` = 起源カテゴリ (L1 期間の積み残し)

scope 判定には `deferred` が必須。実在の dual-label 運用例: [#412](https://github.com/Idios/kobutachan-allaganeye/issues/412) `[enhancement,deferred,l1-residual]`、[#634](https://github.com/Idios/kobutachan-allaganeye/issues/634) `[P3-low,doc,deferred,l1-residual]`。

棚卸し時に分類漏れを検出する query:

```bash
# l1-residual だけ付いて deferred 不在 = 分類漏れ
gh issue list --state open --label l1-residual \
  --json number,labels \
  --jq '.[] | select(([.labels[].name] | index("deferred")) | not) | "#\(.number) needs deferred"'
```

## GitHub Issue Forms の制約 (URL pre-fill 不可)

GitHub Issue Forms (`.yml` schema、`.github/ISSUE_TEMPLATE/bug_report.yml` 等) は **`title` / `labels` / `assignees` / `projects` / `template` 以外の custom field** (textarea / input / dropdown など、`id:` で指定する field) を **URL query string で pre-fill しない** (GitHub 仕様、2026-05 時点)。

例えば `?template=bug_report.yml&actual=HELLO` でも `実際の動作` textarea は空のまま開く。Markdown 形式の従来 template (`*.md` ファイル) なら `?body=...` で pre-fill 可能だが、Issue Forms はサポートされない。長年の feature request あり (参考: <https://github.com/orgs/community/discussions/22335>) だが未実装。

**設計時の代替策**: ErrorModal 等で「クラッシュ情報を自動添付」する設計が必要な場合、URL pre-fill ではなく **clipboard copy + 手動 paste** 方式を使う (Plan B、#669 / PR #726 で採用)。`navigator.clipboard.writeText()` で Markdown 本文を組み立てて、user が form の textarea にペーストする UX が standard。

---

## 9. gh コマンド例

```bash
# [bug] の例
gh issue create \
  --repo Idios/kobutachan-allaganeye \
  --title "[bug] ○○が△△のとき誤動作する" \
  --body "..." \
  --label "bug" --label "P1-high" \
  --assignee "Idios"

# [task] の例 (L2 GUI スコープ)
gh issue create \
  --repo Idios/kobutachan-allaganeye \
  --title "[task] ○○を調査する" \
  --body "..." \
  --label "task" --label "l2a-gui" --label "P2-medium" \
  --assignee "Idios"
```

> **PowerShell での注意**: 本文に特殊文字（バッククォート、シングルクォート等）が含まれる場合は
> ヒアストリング（`@'...'@`）または変数（`$body = @'...'@`）を使うこと。
