---
name: close-issue
description: PR マージ後の issue クローズを担う skill。受け入れ条件をマージ後 base ブランチで実測再検証 (Iron Law 4 担保ルート) し、未消化チェックボックスや残タスクを (B) 新 issue / (C) 既存 issue 追記 にトリアージしてからユーザー承認で `gh issue close` を実行する。1:1 / 束ね PR (1 PR で N issue close) / Phase 分割 (N PR で 1 issue close) の各ケースに対応。`/review-pr` Step 8 から分離 (#594)
user-invocable: true
argument-hint: <issue番号>
---

指定された issue を「マージ後の受け入れ条件実測再検証」を経てクローズする。

> Iron Law 4 (`.claude/hooks/session-start.sh`) 担保ルート。詳細な条文は hook を参照。

## 制約

本 skill は PR ブランチへの編集・commit・push は行わない (レビュー専用セッションと同等の read-only 制約)。ただし base ブランチ (main / develop-x.x.x) への read-only な検証コマンド (pytest / ruff check / grep) は実施する。

## 起動

```text
/close-issue <issue番号>
```

issue 番号 1 つに対して 1 回呼び出す。issue ⇔ PR の関係に応じて以下の分岐 (ケース A/B/C) を持つ。

## 手順

### 1. issue 取得

```bash
gh issue view "$ARGUMENTS" --repo Idios/kobutachan-allaganeye \
  --json title,body,state,assignees,labels,closedByPullRequestsReferences --comments
```

- `state == OPEN` を確認 (`CLOSED` の場合は本 skill 対象外、`AskUserQuestion` で再オープン or 別対応を確認)
- `closedByPullRequestsReferences` で紐づく PR 一覧を取得
- 本文末尾の `作成: <session-id>` で起票元セッション ID を確認 (close コメント記載に使用)。記載なし / 空欄の場合は close コメント本文での「起票元 session-id」言及は省略可
- **本 skill 実行 session-id の取得**: `pwd` で現在のディレクトリパス (例: `.../.claude/worktrees/hopeful-darwin-616414`) を取得し、最終ディレクトリ名を session-id とする (例: `hopeful-darwin-616414`)。Step 7 の close コメントには**実行 session-id を必ず含める** (起票 session-id の有無に関わらず)

#### Refs #N fallback (closedByPullRequestsReferences が空の場合)

本プロジェクトは Iron Law 4 (`Closes/Fixes/Resolves` キーワード禁止 / `docs/issue-policy.md` §6) のため `closedByPullRequestsReferences` は**通常空**。fallback ルートが正規経路 (例外運用ではない)。Step 1 の bash 直後に以下を実行する:

1. **timeline API (第 1 段)**:

   ```bash
   gh api repos/Idios/kobutachan-allaganeye/issues/"$ARGUMENTS"/timeline \
     --jq '[.[] | select(.event=="cross-referenced") | select(.source.issue.pull_request != null) | {pr: .source.issue.number, state: .source.issue.state}]'
   ```

   - `cross-referenced` イベントから PR (`pull_request != null`) を列挙
   - 返却される `state` は `closed` (実態は merged の近似情報)。確定的な merged 判定は Step 3 で `gh pr view` 経由で実施

2. **`gh search prs` (第 2 段、timeline ゼロ件 or 補完用)**:

   ```bash
   gh search prs '"Refs #'"$ARGUMENTS"'"' --repo Idios/kobutachan-allaganeye --json number,state,title,url
   ```

   - PR 本文中の `Refs #N` 文字列で全 PR を検索
   - `state==merged` を直接返すため state 判定が明確

3. **dedupe ポリシー**: 両方ヒットした PR は **`gh search prs` の `state==merged` を真値**として採用 (timeline の `closed` は近似情報)。両ルート結果の和集合を取り、PR 番号で重複排除する。
4. **`gh issue view` の `closedByPullRequestsReferences` が非空のケース**: 古い `Closes` 記述が残った issue や手動入力で稀にあるため、当該フィールドが返した PR と fallback 経路の結果を統合 (PR 番号で重複排除)。本プロジェクトでは fallback 経路結果が主、`closedByPullRequestsReferences` は補助的に扱う。

### 2. 紐づく PR の関係性判定 (ケース分岐)

Step 1 で取得した PR 一覧 (closedByPullRequestsReferences または fallback 経路) の件数と、各 PR の close 対象 issue 件数 (closingIssuesReferences または PR 本文 `Refs #(\d+)` 抽出) でケース判定する。

#### ケース A: 1:1 (issue 1 件 + PR 1 件)

Step 1 で取得した PR 一覧が 1 件、かつその PR の close 対象 issue が本 issue 1 件のみ。最も典型的なパターン。

- `closingIssuesReferences` (`gh pr view <PR#> --json closingIssuesReferences`) が本 issue 1 件のみ、または
- `closingIssuesReferences` が空でも PR 本文 `Refs #(\d+)` 抽出結果が本 issue 1 件のみ (本プロジェクト運用)

#### ケース B: 束ね PR (1 PR で N issue close)

Step 1 で取得した PR 一覧が 1 件だが、その PR が複数 issue を close する。

例: PR #500 が #401 と #402 を close する。

**本プロジェクトでの判定** (Iron Law 4 で `Closes` 禁止のため `closingIssuesReferences` も通常空):

- PR 本文から `Refs #(\d+)` 表記を正規表現で抽出する fallback ルートを使う:

  ```bash
  gh pr view <PR#> --repo Idios/kobutachan-allaganeye --json body --jq '.body' \
    | grep -oE '#[0-9]+' | sort -u
  ```

- `closingIssuesReferences` が非空ならそれを優先、空なら PR 本文 `Refs` 抽出結果を採用

#### ケース C: Phase 分割 (N PR で 1 issue close)

Step 1 で取得した PR 一覧が複数件返る。Phase 1 / Phase 2 のように複数 PR で 1 issue を分割消化する。

### 3. 各 PR のマージ状態確認

```bash
gh pr view <PR#> --repo Idios/kobutachan-allaganeye \
  --json state,mergedAt,baseRefName,headRefName,files
```

- 全 PR が `MERGED` であることを確認。1 件でも `OPEN` / `CLOSED (unmerged)` があれば close 不可、ユーザーに状況報告して terminate
- `mergedAt` を取得 (Phase 分割では最終マージ日時を実測検証の基準点とする)
- `baseRefName` が `develop-x.x.x` または `main` であることを確認 (`develop-x.x.x` 由来の場合、`main` への昇格はリリース時に別途行われる前提)
- `files` で変更ファイル一覧を取得 (Step 4 / Step 5 の対応付けに使用)

### 4. 受け入れ条件の抽出と diff 対応付け

issue body から `## 受け入れ条件` 節 (または `## 確認項目 / 作業項目`) を抽出し、各項目を以下の表に整理する。

| # | 受け入れ条件項目 | 対応 PR | 関連 diff (path:line) | 関連テスト | 検証方法 |
|---|---|---|---|---|---|
| 1 | <条件 1 を逐条引用> | #PR# | `path/to/file.py:123` | `tests/test_x.py::test_y` | 静的 / 動的 / 実測必要 |
| 2 | ... | ... | ... | ... | ... |

- ケース B: 本 issue 分の受け入れ条件のみ抽出 (他 issue 分は除外)。「束ねたから条件は共通」という独断は Iron Law 1 違反
- ケース C: 全 PR の diff を統合してマッピング (Phase ごとに切り分けない)
- **受け入れ条件外の追加変更の扱い**: PR diff には受け入れ条件項目に直接対応しない変更 (関連 doc 整合更新、ファイル内別 section 修正、`/review-pr` 段階で承認された scope-guard 例外、無関係 lint fix 等) が含まれることがある。これらは上記マッピング表には**含めず**、別途「補記欄」または「受け入れ条件外 diff」節に記録する。**受け入れ条件外 diff は close 判定 (○/×) の阻害要因にしない** (受け入れ条件 = 元 issue 本文の該当節に列挙された項目のみ)。ただし `/review-pr` 段階で scope-guard 観点で指摘されている残課題があれば、Step 6 トリアージで (B)/(C) として扱う
- **ファイル内 section 粒度の分離**: 1 ファイル (例: `CLAUDE.md`) の中で受け入れ条件対応 section と無関係 section が同時に変更されている場合、対応 section のみを対応 diff として記録する。Section 単位の `grep` / `Read` で範囲を絞り込む (例: `grep -n "^## " CLAUDE.md` で section 開始行を一覧 → 対応 section の範囲内 diff のみ評価)

### 5. マージ後の base ブランチで実測再検証

`base` ブランチ (Step 3 で取得した `baseRefName`) のマージ済み状態で各項目を verify。

```bash
# ローカルの base ブランチを最新化 (read-only)
git fetch origin <baseRefName>
git log origin/<baseRefName> --oneline -20  # マージ済 PR の commit が含まれることを確認
```

検証手段は項目の性質に応じて使い分ける:

- **静的検証** (本 skill 内で実行可):
  - `gh pr view <PR#> --json files` の変更ファイルに対し、期待 path:line でコードが存在するか `grep` / `Read`
  - 受け入れ条件項目に対応する関数・型・docs 記述が現状コードに存在するか
  - **CI green の扱い**: PR の last CI が green であることは Iron Law 4 「実測再検証」の代替には**ならない**。CI green は補助根拠として close コメントに記録できるが、`grep` / `Read` の静的検証は必須。静的検証コマンドが実行不能な環境では下記「環境制約 §C」フォールバックを適用する (skip 不可)
- **動的検証** (短時間で済むもののみ本 skill 内で実行可):
  - 単体テスト 1-2 件: `pytest tests/test_x.py::test_y` 実行し PASS 確認
  - lint: `ruff check <path>` 実行
- **実測必要** (本 skill 範囲外):
  - long-running テスト (動画処理 / GPU / audio 統合)、UI 動作確認、リリース動作検証等
  - これらは PR レビュー段階で `/test-pr` 実施済みの前提。実施記録 (PR コメント / issue コメント / メモリ) を確認し、未実施なら ユーザー (Idios) に `/test-pr` 実施を依頼してから再 dispatch
- **動的検証 vs 実測必要 の判定基準** (境界明示):
  - **動的検証可能** (skill 内で実行): unit/integration テストで `slow` マーカーなし + CI で実行されている範囲 + 30 秒以内目安。GPU/audio を伴わない CPU-only テスト。`ruff check` / `pyright` 等の静的解析。`pytest tests/test_x.py::test_y` で 1-2 件のみ単体実行
  - **実測必要** (skill 範囲外、`/test-pr` 既実施確認のみ): `pytest -m slow`、動画処理 (1 分超)、GPU mode (`--gpu`)、audio 統合 (`audio/scan` フル走査)、UI 動作確認 (Tauri GUI 起動)、リリース動作検証
  - 判断に迷う場合は `AskUserQuestion` でユーザー (Idios) に分類確認
- **`/test-pr` 既実施記録の取得とアクセス不可時の対応**:
  - PR コメント取得: `gh pr view <PR#> --comments` で `/test-pr` 実施記録の有無を確認
  - issue コメント取得: `gh issue view <番号> --comments` で同様に確認 (PR コメントに見つからない場合の fallback)
  - **コメント取得に成功して実施記録が見つかる**: 「実測必要」項目を ○ と判定し、記録のコメント URL / コマンド / 結果サマリを close コメントに引用する
  - **コメント取得に失敗 or 実施記録が見つからない**: `AskUserQuestion` でユーザー (Idios) に「`/test-pr` 既実施か」を確認。記録不在の場合は close を保留し、`/test-pr` 実施依頼を提示する (skill 内で `/test-pr` を実行しない)
  - 「PR 本文に実施したと書いてあるから OK」と独断して ○ にしない (実施記録の所在まで確認するのが必須)

各項目に判定を付ける: ○ (満たす) / × (満たさない) / 部分的 / 実測必要。

### 5b. 受け入れ条件以外のチェックボックス確認

issue 本文中の `## 受け入れ条件` 以外の `- [ ]` (例: `## 確認項目 / 作業項目`、`## 関連 doc 更新`) も全消化されているか確認する。未チェック項目があれば Step 6 でトリアージ。該当節がない / `- [ ]` ゼロ件の場合はその旨を明示記録 (「該当なし」) して Step 6 へ進む (節の存在確認ステップを skip しない)。

**参照先 PR/issue の実在確認**: PR 本文や issue 本文で「#XXX で対応」「#YYY と関連」のように別 PR/issue 番号が言及されている場合 (特に未チェック項目の追跡先として書かれている場合)、`gh issue view <番号> --json state,title` または `gh pr view <番号> --json state` で実在確認を行う。

- **実在 + マージ済 / クローズ済**: 当該タスクは追跡完了とみなして Step 6 トリアージ表の「処置済み」欄に記録
- **実在 + open**: 当該 issue/PR の進行状況を確認。残タスク追跡先として有効、Step 6 では (C) 既存 issue 追記で運用可
- **実在しない (404 / null)**: 当該タスクを「未追跡の残タスク」として扱う。Step 6 で (B) `/create-task` で正式に起票し、参照先番号の不在を close コメントの備考欄に記載する

「PR 本文に書かれているから対応済み」と独断するのは握り潰しパターン (Iron Law 3 違反 / `/review-pr` skill の Red Flag に該当)。

### 6. トリアージと残タスク処置

- **全項目 ○**: ユーザーに close 提案 (Step 7 へ)
- **1 項目以上 × or 部分的**: 残タスクを必ずトリアージ表に記載し、(B) / (C) のいずれかに振り分ける (Iron Law 1, 3 と整合、握り潰し禁止)
  - **(B) 新 issue 起票**: 残タスクが本 issue のスコープから外れる場合、`/create-task` で別 issue として起票
  - **(C) 既存 issue 追記**: 既存の関連 issue に `gh issue comment` で残タスクを追記
- **「実測必要」が残る場合**: ユーザーに `/test-pr` 等の手動検証実施を提案し、結果が来てから本 skill を再 dispatch

トリアージ表テンプレート:

| # | 残タスク | 出所 (受け入れ条件 #N / 確認項目 / その他) | 処置 (B/C) | 起票/追記先 |
|---|---|---|---|---|
| 1 | <具体的な残タスク> | 受け入れ条件 #3 が部分的 | (B) | 新 issue (`/create-task` で起票予定) |

「軽微だから記載不要」は禁止 (Iron Law 3 違反 / 握り潰しパターン)。

### 7. ユーザー承認後の close

**重要 (close 実行前の絶対条件)**: Step 7 のユーザー承認は `AskUserQuestion` ツールを使い、ユーザー (Idios) の明示的な「はい」回答を得るまで `gh issue close` を実行しない。回答が得られていない / 「いいえ」 / 曖昧な回答の場合は close せず、ユーザーに残作業を返す。subagent や自動実行で `AskUserQuestion` を skip するのは Iron Law 4 + Iron Law 5 違反 (本 skill が Iron Law 4 の唯一の担保ルートであるため、ユーザー承認 gate を skip すると担保自体が失われる)。

`AskUserQuestion` で以下を提示し、ユーザー (Idios) の承認を得る:

- 受け入れ条件全項目 ○ + 未チェック `- [ ]` 全消化 + 残タスク (B)/(C) 処置完了 → close 実行
- 上記未達 → close せず、ユーザーに残作業を返す

承認後、close コマンドを実行 (Windows + Git Bash で日本語本文は HEREDOC):

```bash
gh issue close "$ARGUMENTS" --repo Idios/kobutachan-allaganeye --comment "$(cat <<'EOF'
実測再検証完了 (close-issue skill / [<session-id>])

- マージ済 PR: #<PR#1> [, #<PR#2>, ...]
- 受け入れ条件: 全 N 項目 ○ (静的 + 動的検証で確認)
- 未チェック `- [ ]`: 全消化
- 残タスク: なし [もしくは (B) 新 issue #<番号> / (C) 既存 issue #<番号> に追記]

検証方法サマリ: <静的 grep / 単体テスト pytest / `/test-pr` 結果参照 等>
EOF
)"
```

`<session-id>` は本 skill 実行中の worktree 名 (例: `hopeful-darwin-616414`) を使用する。

## ケース別運用 (詳細)

### ケース A: 1:1 (最も典型)

ステップ 1-7 をそのまま適用。Step 4 のマッピング表は 1 PR 1 issue で完結する。

### ケース B: 束ね PR (1 PR で N issue close)

PR は 1 件、close 対象 issue は N 件。本 skill は **issue 単位** で起動するため、issue ごとに `/close-issue <番号>` を**呼び分ける**運用。

- 各 issue の受け入れ条件は**独立**に逐条検証 (Step 4 で他 issue 分を混ぜない)
- 例: PR #500 が #401 と #402 を close する場合 → `/close-issue 401` と `/close-issue 402` を別個に実行する
- `/review-pr` の Step 5b で束ね PR の独立検証は完了している前提 (本 skill ではマージ後の実測再検証のみ担当)
- ただし `/review-pr` 段階で独立検証が省略されていた疑いがある場合 (Step 5b トリアージ表に各 issue 分が分けられていない等)、本 skill 内で独立検証を補完する。「レビュー段階で済んでいるはず」の楽観で済ませない (Iron Law 1)

### ケース C: Phase 分割 (N PR で 1 issue close)

Phase 1 / Phase 2 のように複数 PR で 1 issue を分割消化するケース。本 skill は **最終 PR マージ後** に呼ぶ運用。

- 受け入れ条件は全 PR 統合状態で初めて実測可能 (Step 5 で全 PR 統合済み base ブランチを参照)
- Phase 途中段階で呼び出された場合 (Step 3 で未マージ PR を検出): close 不可、ユーザーに「全 Phase マージ完了後に再実行」と報告
- Step 4 の対応表では PR を縦に並べて受け入れ条件項目との対応を整理する (どの PR がどの項目を満たすか可視化)
- Phase 分割は `closedByPullRequestsReferences` が複数件で機械判定可能。手動検出に頼らない

## 環境制約とフォールバック

### §A. 受け入れ条件節が抽出できない issue

issue 本文に `## 受け入れ条件` 節がない、または整っていない場合 (古い issue / 簡易起票 / バグ報告 等)。

**適用手順**:

1. issue 本文の代替記述 (`## 確認項目`、`## 完了条件`、`## 完了イメージ` 等) を受け入れ条件相当として扱う
2. 該当節が皆無の場合、「PR で何を達成すれば close 可とみなせるか」を `AskUserQuestion` でユーザー (Idios) に確認
3. ユーザー判断後、Step 4-5 を実施
4. 「曖昧だから飛ばしてよい」は Iron Law 5 違反。必ずユーザー確認を経由する

### §B. PR が draft / unmerged / closed unmerged

Step 3 で全 PR が `MERGED` でないケース。

**適用手順**:

1. 状況をユーザーに報告 (`gh pr view` 出力を提示)
2. 取りうる選択肢を `AskUserQuestion` で提示:
   - (i) 未マージ PR のマージ完了を待つ (本 skill を一旦 terminate)
   - (ii) 該当 PR が放棄されている → 残タスクを (B) 新 issue 起票して issue 自体を `not planned` クローズ (ユーザー承認必須)
   - (iii) その他: ユーザー判断
3. close は実行しない

### §C. base ブランチが実測検証できない環境

worktree 内で `git fetch origin <baseRefName>` が失敗する、または検証コマンド (pytest / ruff) が実行不能な環境 (CI 一時障害、依存欠落 等)。

**適用手順**:

1. 静的検証 (`gh pr view --json files` + `Read` / `Grep`) で代替可能な範囲はそれで実施
2. 動的検証が必須な項目は「実測必要」マークを付け、ユーザーに `/test-pr` 別環境実施を依頼
3. 「環境制約で検証 skip」は Iron Law 4 違反。実測検証ルートを欠落させない

### §D. issue クローズ後にコメント追記が必要な場合

close 後に追加情報 (関連 PR 番号 / 検証ログ / 残タスク子 issue 番号) を補足する場合。

**適用手順**:

1. close コメント自体に必要情報を含める (Step 7 のテンプレートに沿う)
2. close 後に追加情報が判明した場合は `gh issue comment <番号> --body-file - <<'EOF' ... EOF` で追記
3. 必要なら `gh issue edit` で本文 (チェックボックス等) も更新

## Red flags (本 skill 実行中に浮かんだら STOP)

| 浮かんだ思考 | 実態 |
|---|---|
| 「PR diff 上の `- [ ]` 確認だけで close 可」 | Iron Law 4 違反。マージ後の base ブランチで実測再検証 (Step 5) が必須 |
| 「束ねた issue だから 1 件で代表検証してよい」 | Iron Law 1 違反。各 issue を独立に逐条検証する (ケース B) |
| 「Phase 1 マージ済みだから Phase 2 を待たずに close できる」 | ケース C 違反。最終 PR マージ後にのみ close 可能 |
| 「実測必要項目を skill 内で全部検証しよう」 | long-running / GPU / audio は本 skill 範囲外。`/test-pr` 既実施を確認するに留める |
| 「× 項目があるが軽微だから close してよい」 | Iron Law 3 違反。残タスクは (B)/(C) にトリアージ、握り潰し禁止 |
| 「受け入れ条件節が無いから自分の判断で close 基準を決めよう」 | Iron Law 5 違反。`AskUserQuestion` でユーザー確認 (環境制約 §A) |
| 「ユーザー承認なしで close したほうが速い」 | Iron Law 4 + Iron Law 5 違反。close は必ず Step 7 のユーザー承認を経由 |
| 「`closedByPullRequestsReferences` 空 = 紐づく PR なし」と即断してよい | Iron Law 4 で `Closes` 禁止のため当該フィールドは通常空。Step 1 fallback ルート (`gh api .../timeline` cross-referenced-event + `gh search prs '"Refs #N"'`) で再列挙する (`Refs #N` fallback サブセクション) |

## よくある失敗

- **`closedByPullRequestsReferences` のみで PR 件数判定**: 本プロジェクトは Iron Law 4 (`Closes` 禁止) のため当該フィールドは**通常空**。Step 1 fallback ルート (`gh api .../timeline` cross-referenced-event + `gh search prs '"Refs #N"'`) を経由して紐づく PR を列挙する。timeline API の state は `closed` (実態は merged の近似)、search の state は `merged` で明確 — dedupe 時は search の `merged` を真値として採用
- **Phase 分割の見落とし**: 単一 PR で完結したつもりが、`Refs #N` 記述由来で複数 PR が立っているケースあり。Step 1 fallback で取得した PR 一覧の件数で機械判定する (Step 2 ケース C)
- **束ね PR で他 issue 分の受け入れ条件まで検証**: ケース B では本 issue 分のみ抽出する。他 issue は別 `/close-issue` 呼び出しで扱う
- **実測必要項目を skill 内で動的検証しようとする**: long-running は範囲外。ユーザーに `/test-pr` 既実施を確認するに留める (Step 5)
- **× 項目を「軽微」と自己判定して close**: Iron Law 3 違反。トリアージ表で (B)/(C) に振り分ける (Step 6)
- **close コメントから session-id / 検証方法サマリを省略**: 監査・トレーサビリティ用。Step 7 のテンプレートを省略しない
- **未マージ PR があるのに skill を続行**: Step 3 で全 PR `MERGED` を確認、未マージなら terminate (環境制約 §B)

## 呼び出し例

```text
/close-issue 594
```

ユーザーが issue 番号を指定して呼び出す。Claude は自動的に段階を進め、要所で `AskUserQuestion` により判断を仰ぐ (特に Step 6 のトリアージ確定 / Step 7 の close 承認)。

## 参考

- `/review-pr` SKILL.md Step 8 (本 skill へのハンドオフ元)
- `docs/issue-policy.md` §7 「Issue のライフサイクル管理」 / §8 「Issue クローズポリシー」
- `docs/l2-workflow.md` §「レビュー受け入れ基準 (#367 対策)」 (review-pr → /close-issue の運用フロー、`### Issue クローズルール` サブセクション)
- Iron Law 4 (`.claude/hooks/session-start.sh`)
- 本 skill 改修経緯: #594 (新設) / #607 (`Refs #N` fallback) / #606 (eval/reports 構造整理)
- 先行事例 (empirical-prompt-tuning による skill 改修): #511 (review-pr ブラッシュアップ)
