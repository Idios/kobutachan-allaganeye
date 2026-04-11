現在のロールに応じた対応可能な作業（Issue・PR）を調査し、ロールの責務と優先度に基づいて次に取り組むべき作業を提案します。

以下の手順を実行してください:

**重要: issue の状態判断時は `gh issue view <番号> --comments` で必ずコメント全文を確認すること。** ボディだけで判断してはならない（コメントに着手宣言・完了報告・テスト結果など最新情報が含まれる）。

## ステップ 1: ロールと現在の状態を確認する

1. `ROLE` ファイルを読んで現在のロールを確認する
2. 現在のセッション ID を確認する（未宣言の場合はユーザーに確認する）
3. `docs/roles/protocol.md` を読む（未読の場合のみ）

## ステップ 2: ロール別の作業候補を調査する

以下の **ロール名に該当するセクション** のみを実行する。

---

### ディレクター の場合

**Issues の調査:**

```bash
gh issue list --state open --json number,title,labels,comments --limit 50
```

以下の条件に合うものを抽出する:
- タイトルが `[question]` で始まる issue（方針・判断の回答が必要）
- `role:director` ラベルが付いた issue

抽出した各 issue について、**着手状態を確認する:**

```bash
gh issue view <番号> --comments
```

- **対応可能**: `着手:` コメントがないもの
- **着手済み**: 他セッションが `着手:` コメントを投稿済み → 対象外

**PRs の調査:**

```bash
gh pr list --state open --label "role:director" --json number,title,headRefName,author,createdAt
```

`role:director` ラベルが付いた PR（ディレクターがレビュー担当）を抽出する。**自セッションが作成した PR はレビュー対象から除外する**（ブランチ名の `<session-id>/` プレフィックスまたは PR body の `[<session-id>]` で判定）。

**ディレクター定期見直し（担当 Issue/PR の処理後に実施）:**

担当 Issue・PR がなくても、以下の見直しを毎回行う。

**(a) 滞留 Issue/PR の検出:**

```bash
gh issue list --state all --json number,title,state,labels,comments,createdAt,closedAt --limit 30
gh pr list --state all --json number,title,state,labels,comments,createdAt,mergedAt --limit 30
```

以下を検出して報告する:
- **マージ済み PR に対応する issue がオープンのまま** — 作成者にクローズを依頼するコメントを投稿
- **テスト未実施でマージされたコード PR** — テスト issue を作成して `role:tester` に割り当て
- **レビューで複数回差し戻された PR** — 原因パターンを特定し、再発防止策を提案
- **着手済みだが長期間（3日以上）進展がない issue** — 担当セッションへの確認コメントを提案

**(b) プロセスルールの整合性チェック:**

Explore サブエージェントを使い、**ロール定義・プロトコル・コマンド間** の矛盾・欠落を検出する:
- `docs/roles/protocol.md` のルール vs `.claude/commands/` の実装
- `docs/issue-policy.md` のラベルルール vs 実際の GitHub ラベル運用
- `docs/roles/*.md` のロール定義間の整合性

問題を発見した場合:
- ディレクターのスコープ内（`docs/`, `.claude/`）なら直接修正して PR を作成
- 他ロールのスコープなら issue を作成して `role:*` ラベルで割り当て

**(c) 見直し結果の報告:**

上記 (a)(b) の結果を、担当 Issue/PR の一覧と合わせて報告する。

---

### リードエンジニア の場合

**Issues の調査:**

```bash
gh issue list --state open --json number,title,labels --limit 50
```

以下の条件に合うものを抽出する:
- `role:lead-engineer` ラベルが付いた issue
- またはタイトルが `[question]`/`[risk]`/`[bug]`/`[refactor]`/`[doc]` で始まる issue（ラベル未付与の場合のフォールバック）

抽出した各 issue について、**着手状態を確認する:**

```bash
gh issue view <番号> --comments
```

- **対応可能**: `着手:` コメントがないもの
- **着手済み**: 他セッションが `着手:` コメントを投稿済み → 対象外
- **ブロック中**: `ブロック:` コメントが投稿されている → 対象外（ブロック原因の解決待ち）

**PRs の調査:**

```bash
gh pr list --state open --label "role:lead-engineer" --json number,title,headRefName,author,createdAt
```

`role:lead-engineer` ラベルが付いた PR（リードエンジニアがレビュー担当）を抽出する。**自セッションが作成した PR はレビュー対象から除外する**（ブランチ名の `<session-id>/` プレフィックスまたは PR body の `[<session-id>]` で判定）。

---

### エンジニア の場合

**Issues の調査:**

```bash
gh issue list --state open --json number,title,labels --limit 50
```

以下の条件に合うものを候補として抽出する:
- `role:engineer` ラベルが付いた issue
- またはタイトルが `[task]`/`[bug]`/`[refactor]` で始まる issue（ラベル未付与の場合のフォールバック）

抽出した各 issue について、**着手状態と方針コメントを確認する:**

```bash
gh issue view <番号> --comments
```

各 issue を以下のいずれかに分類する:
- **対応可能**: `着手:` コメントがなく、`[bug]`/`[refactor]` の場合はリードエンジニアの方針コメントがある
- **着手済み**: 他セッションが `着手:` コメントを投稿済み → 対象外
- **ブロック中**: `ブロック:` コメントが投稿されている → 対象外（ブロック原因の解決待ち）
- **方針待ち**: `[bug]` / `[refactor]` でリードエンジニアの方針コメントがない → 対象外

**PRs の調査（修正依頼された自 PR）:**

```bash
gh pr list --state open --label "role:engineer" --json number,title,headRefName,author,createdAt
```

`role:engineer` ラベルが付いた PR（レビューで修正依頼された自分の PR）を抽出する。**自セッションが作成した PR のうちレビュー待ち状態のものは、自分ではレビューできないため除外する**。

---

### テスター の場合

**Issues の調査:**

```bash
gh issue list --state open --json number,title,labels --limit 50
```

以下の条件に合うものを抽出する:
- `role:tester` ラベルが付いた issue
- またはタイトルが `[task]` で始まる issue（ラベル未付与の場合のフォールバック）

候補 issue について着手状態を確認する:

```bash
gh issue view <番号> --comments
```

- **対応可能**: `着手:` コメントがないもの
- **着手済み**: 他セッションが `着手:` コメントを投稿済み → 対象外
- **ブロック中**: `ブロック:` コメントが投稿されている → 対象外（ブロック原因の解決待ち）

**PRs の調査（テスト対象 + 修正依頼された自 PR）:**

```bash
gh pr list --state open --label "role:tester" --json number,title,headRefName,author,createdAt
```

`role:tester` ラベルが付いた PR を抽出する。これにはテスト対象の PR と、レビューで修正依頼された自分の PR の両方が含まれる。**自セッションが作成した PR のうちレビュー待ち状態のものは、自分ではレビューできないため除外する**。

---

## ステップ 3: 優先順位を判断して次の作業を提案する

ステップ 2 で収集した作業候補に、ロールの責務に基づいて優先順位を付ける。

### 優先順位の判断基準（全ロール共通）

以下の順で優先度が高い:

1. **他ロールをブロックしている作業** — レビュー待ち PR、方針回答待ちの `[question]`、テスト待ちの PR
2. **`P1-high` ラベル付きの Issue/PR**
3. **`[bug]` の修正** — 品質に直結
4. **`[risk]` の評価** — 放置するとリスクが拡大
5. **`P2-medium` または優先度ラベルなしの `[task]`/`[refactor]`/`[doc]`**
6. **`P3-low` ラベル付きの作業**

### ロール別の追加判断基準

**ディレクター:**
- 定期見直し (a)(b) で検出した問題への対応を、担当 Issue/PR と同列で優先判断する
- 他ロールの作業を止めている問題（未クローズ issue、ルール不整合）は最優先

**リードエンジニア:**
- PR レビューは issue 対応より優先（エンジニア・テスターの手を止めないため）
- `[question]` への回答は次点（他ロールの判断待ちを解消）

**エンジニア:**
- `[bug]` は `[task]`/`[refactor]` より優先
- 依存関係がある issue は上流から順に着手

**テスター:**
- コード変更 PR のテストは issue 対応より優先（マージがブロックされるため）
- `P1-high` のテスト issue は最優先

### 待機時のプロアクティブ改善

担当 Issue・PR がゼロの場合、待機せず **自ロールの専門領域でコードベースの改善点を探す**。Explore サブエージェントを活用し、発見した問題は issue として報告する（`docs/issue-policy.md` に従う）。

**原則:**
- 調査のみ行い、直接修正はしない（issue で報告し、通常のレビューフローに乗せる）
- 明確な問題だけを issue 化する。些末な指摘や好みの問題は報告しない
- 1回の check-work で起票する issue は **最大3件** とする（issue 乱立防止）

**ロール別の着眼点:**

| ロール | 調査対象 | 着眼点 |
|---|---|---|
| リードエンジニア | ソースコード, `docs/` | ソースコード実装と技術ドキュメントの矛盾、設計上の懸念 |
| エンジニア | ソースコード, テスト | コード品質、エラーハンドリングの不備、テストカバレッジの穴 |
| テスター | テスト, スクリプト | テストコードと仕様の乖離、スクリプトの不備、ユーザビリティ上の問題 |

> ディレクターは既存の「定期見直し (a)(b)」で同等の機能を持つため、このフォールバックは不要。

### 提案の形式

判断結果を以下の形式でユーザーに提示する:

```
## 次の作業の提案（<ロール名> / <セッション ID>）

### 推奨: #<番号> <タイトル>
**理由:** <なぜこれを最優先と判断したか（1文）>

### その他の候補（優先度順）
1. #<番号> <タイトル> — <状態>
2. #<番号> <タイトル> — <状態>

### 対象外
- #<番号> ... → <除外理由>
```

担当 Issue・PR がゼロの場合は以下の形式にする:

```
## 次の作業の提案（<ロール名> / <セッション ID>）

担当 Issue・PR はありません。プロアクティブ改善を実施します。
```

この場合、ユーザー確認なしで上記「待機時のプロアクティブ改善」に進む。

担当作業がある場合は以下で停止:

「上記の提案で進めてよいですか？別の作業を優先する場合は番号を教えてください。」

## ステップ 4: 作業を開始する

ユーザーが承認または別の作業を指定したら、`docs/roles/<ロール名>.md` の「作業の進め方」セクションに従って作業を開始する。

**Issue に着手する場合（エンジニア・テスター）:**
1. `gh issue comment <番号> --body "着手: <session-id>"` で着手宣言する
2. ブランチを作成する: `git checkout -b <session-id>/issue-<番号>-<slug>`
3. issue の内容を改めて詳しく読んで作業を開始する

**Issue に着手する場合（ディレクター・リードエンジニア）:**
1. issue の詳細を読む: `gh issue view <番号> --comments`
2. ロール定義の作業手順に従って対応する（ドキュメント更新、方針回答のコメント投稿など）

**作業完了後（PR 提出時）:**
1. 関連 issue に完了コメントを投稿する: `gh issue comment <番号> --body "完了: <session-id> → PR #<PR番号>"`
2. issue の `role:*` ラベルを次の担当ロール（= PR レビュー担当）に付替える: `gh issue edit <番号> --remove-label "role:<自分>" --add-label "role:<レビュー担当>"`
3. issue 本文にチェックボックスがあれば、完了した項目をチェックする: `gh issue edit <番号> --body "..."`
4. **作業ブランチに戻る**: `git checkout <session-id>/work` — PR 作成後に feature ブランチへ追加コミットしない
5. 詳細は `docs/issue-policy.md` §7 参照

**PR のテストを完了した場合（テスター）:**
1. テスト結果コメントを PR に投稿する
2. `role:tester` ラベルを外す。PR に他の `role:*` ラベル（レビュー担当）が残っていればそのまま。`role:tester` のみの場合はマージ担当ラベルを付ける
3. **作業ブランチに戻る**: `git checkout <session-id>/work`

**PR をレビューする場合:**
1. `/review-pr <番号>` スキルを呼び出してレビューを開始する
