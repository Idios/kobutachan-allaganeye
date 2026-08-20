---
name: review-pr
description: PR をレビュー（base ブランチ同期確認 = 最新化 + 直近マージ PR 影響 + 並行 worktree PR 重複、受け入れ条件ゲート、CI、ロジック/ドキュメント整合性、ギャップ分析、摘出課題トリアージ）し、摘出した全課題を (A) PR 内追加修正 (Recommended、デフォルト) / (B) 新規 issue 起票 (限定例外) / (C) 既存 issue 追記 (限定例外) のいずれかに必ず振り分ける (握り潰し禁止)。受け入れ条件全満たし + 摘出課題ゼロ で LGTM 候補、そうでなければ原則 (A) PR 内追加修正で完結する。マージ後は紐づく issue クローズを `/close-issue` skill (または手動クローズ) にハンドオフする (本 skill 内では `gh issue close` を実行しない)。レビュー専用セッションのため PR ブランチへの編集・commit・push は行わない
user-invocable: true
argument-hint: <PR番号>
---

指定された PR をレビューする。`docs/l2-workflow.md` §「レビュー受け入れ基準」に従う。

## 重要: このスキルは「レビュー専用セッション」として動作する

`/review-pr` で起動されたセッションは PR ブランチへの **書き込み系操作 (`Edit` / `Write` / `git commit` / `git push`) を一切行わない**。指摘事項は PR コメントで PR 作成セッションに依頼する (セッション間の責務分離を維持する)。

`git checkout` 自体は read 系操作のため、**ソースを読む目的でのみ許可する** (例: `gh pr diff` だけでは追えない複数ファイル横断の相互参照を IDE で開いて読みたい場合)。ただし checkout 後も `Edit` / `Write` / `git commit` / `git push` は依然禁止。現 worktree のブランチを切り替えたくない場合は `git worktree add ../<name> <PR-branch>` で別 worktree を立てて読む方法も取れる。

背景: 2026-04-22 PR #490 / #495 レビュー時、レビューセッションが合意なく修正 commit & push を実施したため明示的な訂正を受けた (#505)。PR ブランチ・PR 本文は PR 作成セッションの作業領域で、レビューセッションは観察・指摘・依頼に徹する。本質は「書き込みによる責務分離破り」を防ぐことで、checkout 単体は責務分離を破らないため #673 で read 目的に限り許可へ緩和した。

## 手順

### 1. PR 概要取得

```bash
gh pr view $ARGUMENTS --json title,body,headRefName,baseRefName,files,commits,labels
gh pr diff $ARGUMENTS
```

#### 1.1 同 issue 過去 PR 検出 (M5、F4 / F5 / F8 教訓)

##### 元 issue # の抽出ルール (G-1 fix)

PR 本文 + GitHub API の両方から元 issue # を抽出する。どちらか一方の見落としを防ぐため**両方カバー必須**:

```bash
# 1. closingIssuesReferences 経由 (Closes/Fixes/Resolves キーワード由来、機械的取得)
gh pr view <PR#> --json closingIssuesReferences

# 2. PR 本文の Refs/refs/関連 issue 等の手動引用 (本 project では Closes 禁止のため Refs が主)
gh pr view <PR#> --json body | grep -oE "#[0-9]+|Refs[[:space:]]+#[0-9]+"
```

両方の和集合を **元 issue # の集合**として扱う。本 project は Iron Law 4 で Closes / Fixes / Resolves キーワード禁止のため、通常は (2) の Refs 引用が主だが、(1) も保険として実行する。

##### 過去 merged PR 確認

元 issue # 集合の各 # に対し、過去 merged PR 件数を確認する:

```bash
gh pr list --search "<元issue#>" --state merged --limit 10
```

件数 **≥1** (本 PR 以外に同 issue を fix した merged PR が既存) なら、Step 5b トリアージ表の **冒頭に警告行**を必ず追加する:

> 「同 issue で過去に merged PR `<N>` 件あります (PR #..., #...)。前回 fix の root cause が今回の変更で完全解消しているか、Step 5 / 5a で重点的に確認してください」

意図的な multi-phase 分割 (例: AppError migration #663→#689→#714 系の Phase 分割、[`docs/refactor-pattern.md`](../../../docs/refactor-pattern.md)) の場合は元 issue の本文 / コメントで明示確認し、警告を「意図的分割と確認済」として処置する。

##### 意図的分割の確認失敗時 fallback (G-4 fix)

元 issue の本文 / コメントを Read しても「意図的な multi-phase 分割」かどうかが判断できない場合 (= 元 issue が「再発したらまた直す」程度の bug fix で Phase 設計が無いケース) は、警告行を**通常通り出す** (= 「意図的分割と確認済」処置にはしない)。warning は user 判断に倒し、Step 7 提案で `/iterate-review` 起動時に Idios が手動で root cause sweep の重点確認を行う。

**block / threshold は設けない** (spec O2 (a) 確定値、警告のみ → user 判断)。F4 (#656 cp932 → #662 UTF-8 二段) や F8 (deferred 持ち越し) と同型の reoccurring fix を事前検出する。

### 2. ベースブランチ同期確認

CI green は **内部整合性のみ** を保証し、base 取り込み時の機能 regression や並行 worktree PR 重複は検出できない。Step 3 (受け入れ条件) に入る前に、base 最新化 + 直近マージ PR 影響 + 並行 PR 重複を必ず確認する。

> read-only 操作のみで完結するため、本 SKILL 冒頭「重要」節 (PR ブランチ書き込み禁止) と整合する。`git merge` / `git rebase` / `git push` は本 step でも一切実行しない。`git checkout` は冒頭の方針に従い read 目的でのみ許可だが、Step 2 (base 同期確認) は `gh` / `git fetch` / `git log` で完結するため checkout する必要はない。

#### 2.1 ベースブランチ形式確認

- `baseRefName` が `develop-x.x.x` 形式であることを確認 (`main` 直接は通常禁止)
- 例外はホットフィックス PR のみ

#### 2.2 base 最新化と直近マージ PR 列挙

```bash
# base を最新化 (read-only 操作)
git fetch origin <baseRefName>

# PR メタを取得 (作成日時、base/head SHA、touched files、mergeStateStatus)
gh pr view "$ARGUMENTS" --json createdAt,baseRefOid,headRefOid,changedFiles,files,mergeStateStatus

# PR 作成日以降に同 base へマージされた他 PR を列挙
gh pr list --base <baseRefName> --state merged \
  --search "merged:>=<PR.createdAt>" \
  --json number,title,mergedAt,files --limit 30
```

各列挙 PR の `files[].path` と当該 PR の `files[].path` を **交差判定** し、交差ありの PR を「影響候補」としてリスト化する。交差ゼロなら本 step は「影響候補なし」で 2.3 を skip 可。

#### 2.3 base 同期判定と進め方確認 (影響候補がある場合のみ)

- `mergeStateStatus` が `BEHIND` の場合、PR head は base 最新を取り込んでいない
- 影響候補 PR がある + `BEHIND` の組合せでは、base / head の同ファイル grep 対比で develop 側追加機能 (新フィールド・関数引数・schema 変更・新規エクスポート等) の保持を逐条確認する。具体的なコマンド (`gh api .../contents` + `diff` 比較 + 注意ファイル一覧) は `docs/l2-workflow.md` §「PR 作成 Pre-flight」 §「機能 regression 検出手順」 を参照
- 結果を AskUserQuestion で 3 択提示する:
  - **(A) PR 作成者に rebase / merge 取り込み + 再検証を依頼するコメントを投稿** (Recommended) — 機能 regression リスクあり時の既定
  - **(B) 影響候補は確認済み・regression なしと判定し Step 3 へ進む** — base / head grep 対比で develop 側追加が PR head に保持されていることを実証できた場合
  - **(C) 詳細調査を続ける** — 判定保留

#### 2.4 並行 worktree 同 issue PR 重複確認 (`feedback_concurrent_worktree_pr_check.md` 昇格)

```bash
# PR が参照する元 issue 番号を抽出 (closingIssuesReferences + 本文 Refs #N)
gh pr view "$ARGUMENTS" --json closingIssuesReferences,body

# 各 issue について同 issue を参照する PR を全件検索 (open / merged / closed 含む)
gh pr list --search "<元issue#>" --state all \
  --json number,headRefName,state,createdAt,mergedAt --limit 20
```

当該 PR 以外に open or merged の PR が検出されたら AskUserQuestion で 3 択提示する:

- **(A) 重複扱いで close 提案** (Recommended、明らかな機能重複時) — PR 作成者に方針相談コメントを投稿
- **(B) スコープ分担で並走** — 各 PR がカバーする範囲を本 PR レビュー報告に明記
- **(C) 既マージ済みで対象外** — 別 PR が既にマージ済みで本 PR が不要なら close 提案

並行 PR 検出ゼロなら Step 6 レポート末尾に「並行 PR 確認: 検出ゼロ」と 1 行記録する。

##### Red Flags

| 浮かんだ思考 | 実態 |
| --- | --- |
| 「最近 fetch したから OK」 | 数分でも別 PR がマージされうる。Step 2.2 は毎レビュー実施 |
| 「mergeStateStatus が CLEAN だから影響候補も問題なし」 | CLEAN は merge 可否のみで機能 regression は判定しない |
| 「並行 PR は計画段階で確認済みのはずだから skip」 | 計画後に別 worktree が PR を提出するケースあり (#646 / PR #647)。Step 2.4 はレビュー時にも実施 |

### 3. 受け入れ条件チェックリスト (#367 対策)

**まず `/enforce-acceptance-criteria $ARGUMENTS` を呼び出し**、Iron Law (全項目の逐条検証) によるゲートを通過させる。このスキルが未達と判定した場合、ここで処理を終了し修正依頼フローへ進む。

**束ね PR (複数 issue を同時に閉じる PR) の場合**: PR が N 個の issue を参照する場合、各 issue の受け入れ条件を**独立に**逐条検証する。受け入れ条件チェック表は issue ごとに節を分け、`| # 910-1 | 910-2 |` のように issue 番号プレフィックス付きで採番する。「束ねたから条件は共通だろう」は Iron Law 1 違反 (Red Flag)。`/enforce-acceptance-criteria` を N 回呼び出すか、1 回呼び出しで全 issue 分を網羅させる。

**孤立 PR (紐づく issue が存在しない PR) / `/enforce-acceptance-criteria` 実行不可時**: 「§環境制約とフォールバック」節の §A (孤立 PR) / §B (enforce-acceptance-criteria 実行不可) に従う。受け入れ条件ゲートを skip せず、代替判定根拠を必ず明示する。

ゲート通過後、以下の補助チェックを行う:

- [ ] **実装内容が PR 説明と一致**: 差分と PR body の乖離を検出 (PR body に書かれていない無関係な変更がないか = scope-guard 観点)
- [ ] **テスト存在**: 変更行に対応する test ケースがあるか
  - 新規関数・メソッド: 単体テスト必須
  - バグ修正: baseline FAIL → FIX 検証テストが望ましい
  - UI/出力変更: スナップショットテストまたは contract テスト
- [ ] **複数 issue 束ね時の合理性**: 1 PR で複数 issue を閉じる場合、束ねる理由が PR 本文に明記されているか
- [ ] **Phase 分割時の子 issue 起票**: 「Phase 2 は別途」等で残タスクを先送りする場合、子 issue 番号が親 issue に記載されているか
- [ ] **`Closes` / `Fixes` / `Resolves` キーワードが使われていない**: issue クローズは手動で行う（`/enforce-acceptance-criteria` が verified を返していればこの項目は自動 PASS。二重チェックになるため明示スキップ可）

補足: `/enforce-acceptance-criteria` は受け入れ条件の逐条検証、Step 5a は補足ギャップ分析 (カバレッジ・観点・エッジケース) を担う。両者は排他ではなく、受け入れ条件で読めない未テスト分岐や未考慮観点を Step 5a で拾う責務分担。

### 4. CI / Lint / Test ステータス確認

```bash
gh pr checks $ARGUMENTS
```

- 全 green: 次へ
- 失敗あり: 失敗ジョブ名と概要をユーザーに報告し、修正依頼コメントを投稿
- 未完了: 完了を待つ or ユーザーに判断を仰ぐ

### 5. ロジック / ドキュメントレビュー

PR の変更種別に応じて以下を確認する。**code quality (logic / architecture / security) 部分は plugin subagent に委譲し、project 固有の doc 整合性確認のみを本 skill で実施する**。

#### 5.0 plugin subagent による code quality review (Skill `superpowers:requesting-code-review`)

`superpowers:requesting-code-review` skill が dispatch する `superpowers:code-reviewer` subagent に code quality 観点 (logic correctness / architecture / security / code smell / best practices) のレビューを委譲する。subagent は本 skill の責務外の項目 (受け入れ条件 / base sync / 並行 PR / project doc 整合 / マージ後 handoff) には介入しない。

> **subagent 起動規約**: 本 dispatch は [`docs/l2-workflow.md` §subagent 起動規約](../../../docs/l2-workflow.md#subagent-起動規約-746-phase-c--741-task-5-教訓) に準拠する。HARD-GATE (Stop conditions / 独断 fix 禁止 / orphan commit 防止) を遵守し、scope を超える発見は BLOCKED 報告で controller (本 skill) に escalate する。F6 (#732) / F7 (#741) と同型の事象を再発させない。

入力に渡す情報:

- PR 番号 (`$ARGUMENTS`)
- PR タイトル / 本文 / diff (Step 1 で取得済み)
- 重点観点: logic correctness / architecture (`CLAUDE.md` §モジュール構成、`docs/design-overview.md`) / security (subprocess 呼び出し / 外部入力 / 認証情報) / code smell

戻り値の扱い:

- subagent からは指摘リスト (各指摘 = 1 行: 観点 / 該当 path:line / 説明) が返る想定
- 各指摘を Step 5b トリアージ表の 1 行として転記。出所列に「subagent: code quality (<観点>)」と前置 (例: `出所 = subagent: code quality (リネーム影響)`)
- 重複指摘 (同一 path + 同一観点が project 固有 doc 整合性 (Step 5.1) と subagent 双方から出る) は **path + 観点** を de-dup キーとして 1 件に統合し、出所列に両方記載 (`出所 = subagent: code quality (<観点>) + Step 5.1`)
- subagent の指摘も project の (A)/(B)/(C) 分類に従う。subagent が「観察のみ」を返した場合でも握り潰さず (A)/(B)/(C) いずれかに振り分ける (Iron Law 3)

#### 5.1 project 固有 doc 整合性確認

**共通観点**:

- 変更の意図が PR の説明と一致しているか

**ドキュメント変更 PR の場合**:

- doc 内容が元 issue の要件と一致しているか
- doc が言及するソースコード (関数名、ファイルパス、設定値) が現状と整合しているか
- 関連する既存 doc (`CLAUDE.md`, `docs/cli-spec.md`, `docs/design-overview.md`, `docs/l2-workflow.md` 等) との矛盾がないか
- doc が言及するテスト / CLI 出力サンプルが実装と一致しているか

**コード / テスト変更 PR の場合**:

- 関連ドキュメント (`docs/cli-spec.md`, `docs/design-overview.md`, `README.md`, `CLAUDE.md` 等) が更新されているか
- **特に CLAUDE.md / docs に「追加予定」「今後実装」等の予告記述があり、本 PR がその実装に該当する場合、予告文を実装済み記述に更新すること。更新漏れは Step 6 で修正依頼対象**
- コード変更がドキュメント記述と矛盾していないか
- 出力形式変更の場合、`docs/cli-spec.md` の出力例も更新されているか (#343 系の再発防止)

**installer / workflow 系 PR の場合 (#L-γ M2、F2 教訓)**

> **該当判定**: 本ブロックの trigger は「**外部依存の DL / 取得を追加・変更している**」ことであって、`.github/workflows/**` や `scripts/**` を touch したこと自体ではない。workflow ファイルを触っていても外部依存の取得が無ければ**非該当**。非該当と判定したら Step 6 に `外部依存規約: 非該当 (理由: 本 PR に外部依存の DL / 取得なし)` を 1 行記録する (§「規約・ガード導入の 3 点セット」②)。

- 外部依存 (Python / npm / cargo / OS binary tarball 等) の DL URL が **immutable** か (`master` / `main` / `latest` / `raw HEAD` を含まない)
- [`docs/l2-workflow.md` §外部依存規約](../../../docs/l2-workflow.md#外部依存規約-649651703721-教訓) §受け入れ可能なソース / §禁止パターン に沿うか
- 違反があれば Step 5b トリアージ表で **(A)** PR 内修正 とし、URL pin 形式 (versioned tag / SHA pin 等) への変更を要請

**パス生成点・表示点を触る PR の場合**:

- ユーザーに提示するパス (完了行 / `--json` / GUI) または永続化するパスの**生成・整形箇所**を変更しているなら、[`docs/output-spec.md` §ユーザーに提示するパスの契約](../../../docs/output-spec.md) に照らして検証する (絶対化されているか / `os.path.abspath` であって `Path.resolve()` でないか / `--json` は POSIX・人間向け行はネイティブ区切りか)
- **非該当なら Step 6 に `パス契約: 非該当 (理由: パスの生成点・表示点に変更なし)` を 1 行記録する** (§「規約・ガード導入の 3 点セット」②)
- 契約と実装が食い違っていたら **doc 側が誤っている可能性を先に疑う**。契約 doc は実装を読んで書かれたとは限らない (#966 で、PR 本文の主張を実装未確認のまま契約 doc へ写した実例がある)

**規約 / ガード / チェックを新設する PR の場合 (G1-1)**:

- 本 PR が CI job / hook / skill step / 規約文を**新設**しているなら、[`docs/l2-workflow.md` §「規約・ガード導入の 3 点セット」](../../../docs/l2-workflow.md) の 3 点に照らして**逐条検証**する:
  1. **発火点**が skill step / CI job / hook のいずれかに**ファイルと行で**指定されているか (「doc に書いた」だけでは発火点ではない)
  2. **非実施時の 1 行記録義務**が課されているか (skip と失念が事後に区別できるか)
  3. **発火側の red 実証** — 違反を一時注入し **exit code の生値**で発火を観測した記録 + pin test が同梱されているか
- 欠けている項目は Step 5b トリアージ表に計上する。**③ が最も落ちやすい** — 保護機構は不発でも green のままなので、CI が no-op を mask する

**diff 外 doc の確認ができない場合の処置**: 関連 doc の整合性確認がレビューセッションで完結しない (ファイルが session context 外 / アクセス不可 / 判断に専門領域知識が必要) 場合、「確認不要」と自己判断して省略せず、**(A) PR コメントで PR 作成セッションに整合性確認を依頼** する。Iron Law 3 / 5 に従い、曖昧な判断は独断で skip しない。

### 5a. ギャップ分析 (明示指示不要で自動実施)

Step 3 (受け入れ条件) / Step 5 (ロジック・ドキュメント) が拾いきれない未テスト分岐・未考慮観点を洗い出す。`/review-pr` 呼び出し時は指示の有無に関わらず標準業務として実施する (#511)。

**列挙プロセス (軸ごとに列挙し優先度付け)**

| 軸 | 取り方 | シグナル |
| --- | --- | --- |
| カバレッジ | 変更行のうち test が hit しない分岐を洗い出す | 未テスト分岐残数 |
| 観点 | happy path / error path / edge case を網羅 | 観点欠落 |
| エッジケース | 入力境界 (空 / null / 巨大) / 並行性 / resource 枯渇 | 想定外入力 |
| 優先度 | 受け入れ条件関連 = P1 必須、nice-to-have = P3 推奨 | ブロッカー判定 |

**long-running / integration 検証観点**

- 長時間動画 (2 時間以上) / GPU mode / audio 統合 / 大規模入力 等は mock 不可
- レビュー側は「手動検証が必要」と明示し、PR 作成セッションが PR 提出前に実機検証済みであることを確認する。未実施なら受け入れ条件未充足として (A) PR コメントで再検証を要求 (`docs/l2-workflow.md` §「実機検証 trigger 表」 参照)
- 自動 CI で担保できる範囲と、手動検証が必須な範囲の境界を明示してユーザー / PR 作成セッションに伝達する
- **手動ゲートの異常観測記録の確認 (Refs #935 P2-3)**: 実機検証の記録に「実施中に観測した想定外の挙動」が書かれているか、**または「観測ゼロ」が明記されているか**を確認する。未記載なら Step 5b トリアージ表へ計上する ([`docs/l2-workflow.md` §「実施中に観測した想定外の挙動」](../../../docs/l2-workflow.md) 参照)。**「主目的は達成した (N/N 完走)」だけの記録は pass の根拠にならない** — 観測された異常は主目的の成否とは別の軸である。異常が別 issue へ切り離されている場合は、切り離し先が 1 行で記録されているかまで確認する

**大規模 refactor 観点 (#L-γ A1)**

- 本 PR が `touched files > 30 file` または `diff > 1000 line` を超える場合、Phase 分割すべきだった可能性を疑う
- [`docs/refactor-pattern.md`](../../../docs/refactor-pattern.md) §4 判定基準 (green / regression なし / consumer が選択的に乗り換え可能) を引き、Step 5b トリアージ表で (A) PR 内 Phase 分割提案 or (B) 別 issue で Phase 設計 spec を起票する
- AppError migration (#663→#689→#714/716/725/730/733→#745→#746) を reference 実例として参照

**optional Codex review (Codex 統合、C3)**

以下のいずれかを満たす PR で Codex review を併走させる (人手 trigger or skill 内 auto)。agent 実行は tier 1 = companion script `codex-companion.mjs review --base develop-X.Y.Z` の Bash 実行 (slash `/codex:review` は `disable-model-invocation: true` のため agent から invoke 不可 = Idios 専用 tier 3。`docs/l2-workflow.md` §Step 5 の invocation path (3-tier、#795) 参照):

- PR diff が大きい (touched > 15 file or > 500 lines)、または
- 過去 root cause が複数 (Step 1.1 M5 警告 ≥2 件)、または
- L1 (CLI / detector / GPU) の core ロジック変更を含む

#### 起動記録 (該当時 / 不該当時とも必須、H-4 fix)

起動した / しなかったの**どちらの場合も**、Step 6 レビュー報告に以下のいずれか 1 行を明記する。**両分岐に定型がある** — 片方だけを定型化すると、定型のない側は実行者ごとの作文になり表記が揺れる:

> `Codex review 起動: 対象 (理由: <上記 3 条件のどれに該当したか>)`
>
> `Codex review 起動: 非対象 (理由: touched <N> file / single root cause / non-L1-core)`

これがないと「Codex review を意図的に skip したのか / 忘れたのか」が事後追跡できない (Iron Law 5 整合)。

> **記録義務は分岐を網羅する。** 本節と下記「Codex 出力の読み取り」の 2 record は、いずれも
> **起こりうる状態すべてに定型を用意する**方針で書いてある (起動 = 対象 / 非対象、
> 読み取り = 成功 / 失敗 / 非起動)。新しい記録義務を足すときも同じ原則に従うこと。
> 異常系だけに定型を置くと、正常系のたびに実行者が文言を発明する

#### Codex 出力の読み取り (#949、openai-codex 1.0.4 時点)

Codex review が exit 0 で完了したら、**finding を stdout から拾う前に保存済み全文を読む**。契約の正は [`docs/l2-workflow.md` §「Codex 出力の読み取り」](../../../docs/l2-workflow.md) で、本 step はその適用にあたる。

1. review を実行した worktree の cwd のまま、**`CLAUDE_PLUGIN_ROOT` を張り直してから**直前の review job の **id を特定する**。以下は**同じ Bash 呼び出しの中で**実行する — Bash tool は呼び出し間で env var を保持しないため、review 実行時の `export` はこの時点で消えており、空のまま使うと `node "/scripts/codex-companion.mjs"` に展開されて `MODULE_NOT_FOUND` になる (実測):

   ```bash
   ls "$HOME/.claude/plugins/cache/openai-codex/codex/"
   export CLAUDE_PLUGIN_ROOT="$HOME/.claude/plugins/cache/openai-codex/codex/<解決した version>"
   node "$CLAUDE_PLUGIN_ROOT/scripts/codex-companion.mjs" status --json
   ```

   `latestFinished` を先に見て **`jobClass` が `"review"`** ならその `.id`、違えば `recent[]` を先頭から走査して最初に `jobClass == "review"` になった entry の `.id` を採る (この順で最新の review job が一意に決まる。詳細は [`docs/l2-workflow.md` §「Codex 出力の読み取り」](../../../docs/l2-workflow.md))

2. その id を**明示して** `result` を実行する (`--json` は不要。プレーン出力が rendered 全文。`CLAUDE_PLUGIN_ROOT` は step 1 と同じ Bash 呼び出しなら張り直し不要):

   ```bash
   node "$CLAUDE_PLUGIN_ROOT/scripts/codex-companion.mjs" result <job-id>
   ```

   **id を省略しない。** 省略時の選択は `jobClass` を見ずに「現 session の最新完了 job」を返すだけなので、同じ session で `/codex:rescue` や `task` を走らせていると **review ではない job の出力を review の finding として取り込む**

3. exit 0 なら、その出力を finding の入力とする。**stdout に見えていた分だけで triage しない**
4. **成否にかかわらず、Step 6 レビュー報告に次のいずれか 1 行を必ず書く** (3 状態すべてに定型がある。`成功` 以外は理由が必須):

   > `Codex 出力読み取り: 成功 (job <job-id> の result 全文を finding の入力にした)`
   >
   > `Codex 出力読み取り: 失敗 (理由: <result の stderr 先頭 1 行>)。stdout に見えた範囲のみで triage した`
   >
   > `Codex 出力読み取り: 非起動 (理由: <上記「起動記録」の非対象行と同じ理由>)`

   `失敗` は **fallback ではない**ので Codex fallback notice とは別物。この 1 行が無いと「全文を読んだ」「読めなかった」「そもそも起動していない」が事後に区別できない ([`docs/l2-workflow.md` §「規約・ガード導入の 3 点セット」](../../../docs/l2-workflow.md) ②)

   **読み取りが失敗したときの再試行・原因診断は任意**。1 行記録して先へ進んでよい (原因診断は本 step の責務ではない)。ただし cwd が review 実行時の worktree と違っていた場合だけは、cwd を直して 1 度だけやり直す — これは診断ではなく手順ミスの訂正である

   > **`/iterate-review` の subagent mode で実行している場合**、この 1 行は Step 6 レビュー報告ではなく final message の `## meta` に同名で書く (controller が Step 4 Final summary へ転記する)。`非起動` を選んだときは、上記「起動記録」の非対象行を**この行の理由として畳んでよい** (固定 5 セクションに専用スロットを増やさない)

`--background` / `--wait` は付けない。`review` / `adversarial-review` では受理されるだけで無視され、常に foreground blocking になる (openai-codex 1.0.4 時点)。長時間 review を非同期化したい場合は Bash tool の `run_in_background: true` を使う。

Codex の finding は Step 5b トリアージ表に「出所 = codex:review」と記載して統合する。Codex に直接 commit させない (M3 整合)。

#### Codex fail 時の fallback 手順 (C6、L-β β-5 で追加)

Codex CLI が exit code 非ゼロを返した場合、[`docs/l2-workflow.md` §Codex fallback](../../../docs/l2-workflow.md#codex-fallback) の検出条件 table に従い:

> **step の優先順 (逐語、#856 item2)**: step 1 の分類後、**必ず step 2 の重要 PR 判定を先に評価する**。重要 PR に該当したら step 2 の AskUserQuestion で確定させ、**step 3 / 4 は評価しない (短絡)**。step 3 / 4 は「重要 PR に該当しなかった場合」にのみ到達する分岐であり、step 2 と並列の選択肢ではない。判定順は `1 → 2 → (2 に該当すれば終了) → 3 または 4` である。

1. stderr を keyword match (rate-limit / quota / 429 / auth / timeout 等) で分類
2. **重要 PR 判定 (I-5 fix、spec C6 限界節)**: 以下のいずれかを満たす場合は「重要 PR」とし、**自動 fallback の前に user に AskUserQuestion 3 択を提示**:
   - release 直前 (`pyproject.toml` version bump を含む or develop-X.Y.Z → main 統合 PR)
   - 大規模 refactor (touched > 30 file or diff > 1000 line)
   - L1 core ロジック変更 (detector.py / gpu_detector.py / audio/*.py / video/detector.py)

   AskUserQuestion 3 択 (Recommended 順):
   - (A) Codex 復旧待ち (本 PR 一時 abort、Codex 復旧後に再 invoke) [Recommended]
   - (B) Claude fallback で push (superpowers `requesting-code-review` subagent fallback)
   - (C) abort (本 PR 全体停止、user 手動判断)
3. **明確な failure (重要 PR でない)** → 自動 fallback: superpowers `requesting-code-review` subagent を起動する。**focus の渡し方 (#856 item4)**: tier 1 の `codex-companion.mjs review` は **focus positional を受け付けない**ため「Codex に渡した focus 文字列」は**存在しない**。「流用」できる文字列は無いので、fallback subagent には [`docs/l2-workflow.md` §「Step 5 の focus 導出手順」](../../../docs/l2-workflow.md) で**導出した focus を渡す** (project 固有 focus を Codex 側へ渡す場合に `adversarial-review` subcommand で使うはずだったものと同じ導出結果)
4. **曖昧 (重要 PR でない)** → user に AskUserQuestion (再試行 / Claude fallback / abort) 3 択
5. fallback 実行時は **Step 6 レビュー報告に「Codex fallback notice」を必須記載** (Iron Law 5 整合、template は docs/l2-workflow.md §Codex fallback 参照)

詳細運用は `CLAUDE.md` §Codex 運用 を参照。

ここで列挙した観点は Step 5b トリアージ表で必ず処置分類を付ける。観察コメントのみで終える (= 握り潰す) のは禁止。

### 5b. 摘出課題のトリアージ (握り潰し禁止、原則 (A) で完結)

Step 3 (受け入れ条件未達) / Step 4 (CI 失敗) / Step 5 (ロジック・ドキュメント不整合) / Step 5a (ギャップ分析) で洗い出した**すべての摘出課題**を下記トリアージ表に記載する。各行は必ず処置分類 (A / B / C) のいずれかに割り当てる。**未分類 (観察のみ / 握り潰し / スコープ対象外と自己判断して無視) は禁止**。

> **方針: 摘出問題は原則 (A) PR 内追加修正で PR を完結させる** (`docs/l2-workflow.md` §「(A) PR 内修正優先 規約」)。**理由: レビュー摘出のたびに別 issue を起票すると issue が減らないどころか増え、運用が破綻する。本 PR 内で完結できる修正は本 PR で行う方が追跡コストが低い。** 別 issue 起票は後述の限定例外 trigger に該当する場合のみ。

**処置分類 (3 択、(A) Recommended)**

- **(A) PR コメントで本 PR 内修正依頼 (Recommended、デフォルト)**: 本 PR 内で追加修正してマージまで進める。Step 7 の次のアクション提案で `/iterate-review` ループを起動し PR 作成セッションに依頼。**摘出課題はまずこの選択肢を検討する**
- **(B) 新規 issue 起票 (限定例外)**: 以下の trigger のいずれかに該当する課題のみ。Step 7 完了後または Step 8 マージ後に `/create-task` で起票:
  - **別領域・別機能** (例: 別ファイル群のセキュリティ問題、別レイヤー実装、別担当領域) で着手 issue スコープ外
  - **大規模リファクタ** (独立設計が必要、工数 1 セッション超、本 PR に同梱すると diff が肥大化して受け入れ条件検証が破綻する)
  - **外部依存・側チケット調整が必要** (上流ライブラリ変更、別リポ修正待ち等)

  > ※ subagent mode (`/iterate-review` 経由) 時は §G.2.1 item 3 の AND 3 条件が優先 (機械処理 parse error 抑止)。standalone mode と subagent mode の非対称は意図的設計。

- **(C) 既存 issue 追記 (限定例外)**: 既存 issue の受け入れ条件・残タスクに該当するため、当該 issue にコメントで方針記録を追記。同 issue の重複起票を避けるとき

**AskUserQuestion で処置選択肢を提示する場合**: (A) を必ず最初の選択肢として `(Recommended)` ラベル付きで表示する。**`(Recommended)` ラベルは表示順規約であって最終選択結果を強制するものではない**。(B) / (C) は限定例外 trigger を `description` フィールドに明記する。**(B) trigger 強該当時は description で具体的に該当根拠を説明** する (例: 「audio module は本 PR スコープ外 = 別レイヤー、独立 security 修正 → (B) 該当」)。例:

```js
options: [
  { label: "(A) 本 PR 内で追加修正 (Recommended)", description: "本 PR の品質を底上げする修正は (A) で同梱が原則 (`docs/l2-workflow.md` §「(A) PR 内修正優先 規約」)" },
  { label: "(B) 別 issue 起票 (別領域 / 大規模 / 外部依存のみ)", description: "本件は audio module で本 PR スコープ外 (detector/format) → 別領域 trigger 強該当、独立した security 修正" },
  { label: "(C) 既存 issue 追記", description: "既存 issue #N が同テーマで未クローズ → 重複起票回避" }
]
```

**(A) を選ばない理由として NG な合理化** (これらが浮かんだら STOP):

| 浮かんだ思考 | 実態 |
| --- | --- |
| 「PR が大きくなるから別 issue にしよう」 | (A) が原則。サイズだけを理由に (B) を選ばない。本当に diff が肥大化するなら「大規模リファクタ」trigger を満たすか先に判定 |
| 「本 PR の受け入れ条件と直結しないから別 issue」 | (A) が原則。本 PR の品質を底上げする修正は (A) で同梱する。直結性ではなく「別領域・別機能」trigger を満たすかで判定 |
| 「軽微だから別 issue で後でまとめて」 | (A) が原則。軽微なら本 PR 内で即時修正の方が安い。後回しにすると忘れる |
| 「摘出課題が多いから一部は別 issue で分離」 | 件数では分離しない。各課題ごとに (A) / (B) trigger を独立判定する |

**判定基準**

- 受け入れ条件・PR 本文記載の目的に直結する課題 → **(A)**
- PR 本文に記載ないが発見された欠陥・リスク・観点抜け → 既存 issue が該当すれば **(C)**、なければ **(B)**
- 「スコープ対象外だから指摘不要」「軽微だから無視」「観察のみで OK」は**禁止** (Iron Law 3 違反 / #399 B 再発パターン)

**判定に迷いがちな典型ケース (baseline 評価で抽出)**

| ケース | 推奨処置 | 補足 |
| --- | --- | --- |
| PR 本文に記載のある軽微なスコープ外変更 (無関係な lint fix / 型リネーム 等) | **(A) revert 要求** または **(B) 別 issue 起票** を `AskUserQuestion` で確定 | Iron Law 3「軽微だから」の独断禁止。scope-guard skill に委譲可 |
| スコープ外変更に伴う追従テスト不足 | 元変更の処置に連動: (A) revert → 追従テスト指摘は消滅 / (B) スコープ拡大合意 → 同 PR 内で (A) 追加要求 | 二重構造なので元スコープ判定を先に確定する |
| 参照ファイル追加 (バイナリ等) の実体未検証 | **(A) PR コメント** (サイズ・次元・生成条件の PR 本文追記を要求) | enforce-acceptance-criteria §Step 3 チェック項目直結 |
| doc 変更 PR で発見した CI 設定 (`.github/workflows/`) との矛盾 | **(A) PR コメント** (パス変更スコープに含まれる) | doc-only の境界を越える。「波及が大きい」の目安 — **(A) 目安**: 同一 PR で対応可能 (CI YAML 1-2 箇所の path 書換え / テスト追加 1-2 ファイル / doc 追従 1-2 箇所)。**(B) 目安**: 別レイヤー実装変更を伴う (検知パイプライン / GUI / CLI への連鎖修正 / 既存テスト再実行工数が GPU / 音声統合で 30 分超 / 別担当領域)。判断に迷う場合は AskUserQuestion でユーザー (Idios) 判断に回す |
| 束ね PR で分離推奨と判断 | **(A) 分離依頼** (束ねの合理性を問い、分離 or 合理性説明を要求) | 束ね合理性が明記されていれば合意可、なければ分離優先 |
| 予告文 (「今後実装」「追加予定」) の実装に該当する PR での予告文更新漏れ | **(A) PR コメント** (本 skill Step 5 にも明記された修正依頼対象) | CLAUDE.md / docs の予告文更新は受け入れ条件レベル |
| markdownlint violation (MD028 / MD056 / MD060 等) を発見 | **(A) PR コメント** (本 PR 内で fix) | fix recipe は [`docs/markdownlint-guide.md`](../../../docs/markdownlint-guide.md) §typical fixes (M10) を参照。typical なのは MD028 (blockquote 連結) / MD056+MD060 (table cell の \| escape) / MD060 compact-style |
| installer / `.github/workflows/` 系 PR で `master` / `main` / `latest` を含む URL を発見 | **(A) PR コメント** (immutable URL pin への変更を要請) | 規約は [`docs/l2-workflow.md` §外部依存規約](../../../docs/l2-workflow.md#外部依存規約-649651703721-教訓) (M2)。F2 (#649→#651→#703→#721) 系の再発防止 |
| 大規模 PR (touched > 30 file or diff > 1000 line) で Phase 分割の検討漏れ | **(A) PR コメント** (Phase 分割提案) または **(B)** Phase 設計 spec 起票 | 判定基準は [`docs/refactor-pattern.md`](../../../docs/refactor-pattern.md) §4 (A1)。AppError migration が reference 実例 |

**root cause 識別時は Step 5c (同種パターン sweep 規約、本節の直後で詳述) に従う**: explicit N 箇所のみ列挙ではなく、`grep -nE '...'` 全件 sweep の hits を本表に転記すること。**先に下記 Step 5c の手順を確認してから本表を埋めること** (Step 5b → 5c の flow 順は doc 上の順序、運用上は 5c の sweep 結果を 5b 表に転記する)。

**トリアージ表テンプレート** (Step 6 のレビュー報告に必須で含める)

| # | 摘出内容 | 出所 | 処置 | 根拠 |
| --- | --- | --- | --- | --- |
| 1 | <具体的な課題> | 受け入れ条件 #N / CI / 5a カバレッジ / 5a 観点 / 5a エッジケース / 5 ロジック / 5 ドキュメント | (A) PR コメント / (B) 新規 issue / (C) 既存 #N 追記 | <なぜその分類か (受け入れ条件直結・PR 本文外・既存 issue と重複 等)> |

表が空で終わるのは「本当に摘出課題ゼロ」の場合のみ。**1 件でも摘出したら必ず表に載せる**。

### 5c. 同種パターン全件 sweep 規約 (Refs #682)

Step 5 / 5a / 5b で root cause (literal mismatch / 古い API 残存 / DCE 誇張表現 等) を識別したら、explicit な N 箇所だけを列挙して implementer に依頼するのは **Red Flag** (PR #675 で 3 round 分散の実害)。以下を必須化する:

1. **全件 grep 提示**: `grep -nE 'pattern1|pattern2|...'` で repo 全体から hits を抽出
2. **トリアージ表に grep hits を全件転記**: Step 5b の表に各 hit を 1 行ずつ記載 (file:line + 該当パターン + 処置分類)
3. **修正依頼本文に grep コマンドと hits を同梱**: PR コメントの修正依頼にも grep コマンドを引用

「explicit な 4 箇所」を依頼すると implementer が同 file 内の他 hits を見落とし、Round 2/3 で再指摘するパターンが発生する (#682 issue 本文 PR #675 経緯参照)。

**複数 root cause が混在する場合** (literal mismatch / 古い API 残存 / DCE 誇張表現 / **base regression (他 PR 由来フィールド欠落)** 等の異なる種類が同一 PR で発生): 各 root cause を最初に個別識別し、root cause ごとに独立した grep コマンドを生成する。base regression は Step 2.2 で列挙した影響候補 PR のフィールド・関数引数・新規エクスポートが本 PR の変更対象ファイルに統合されているか確認することで検出する。異なる root cause を同一 grep パターンで混在させると sweep 漏れが発生するため、root cause 数 = grep コマンド数を原則とする。

#### 意味クラス root cause の sweep (Refs #935 P2-2)

上記 1-3 は **root cause が文字列パターンとして表現できる**場合の手順である (literal mismatch / 古い API 残存 / 命名 drift 等)。root cause が**意味クラス** — 単一の grep パターンでは表現できないもの — の場合は、パターンではなく**能力の呼び出し箇所を全列挙して述語を 1 件ずつ当てる**。

代表的な意味クラス (いずれかに該当したら本手順へ):

| 意味クラス | 全列挙する対象 | 各件に当てる述語 |
| --- | --- | --- |
| **破壊的操作の述語** | 不可逆書込 (上書き / 削除 / truncate) の全呼び出し | 削除・上書きの対象を選ぶ判定が、名前・文字列一致ではなく**解決後の同一性** (OID / realpath / content hash) か |
| **外部入力の検証** | CLI option / metadata field / GUI 自由入力 / 環境変数の全取得点 | 値が書込先・実行対象の決定に到達するか。到達するなら sandbox 検証があるか |
| **パス解決規則** | ユーザーに提示する / 永続化する path の全生成点 | 絶対化されているか。相対・ドライブ相対のまま外へ出ていないか |

**手順**:

1. **能力の呼び出し箇所を全列挙する。** パターンは「欠陥の形」ではなく**「能力の形」**で書く:

   ```bash
   # 例: 不可逆書込の全呼び出し (欠陥ではなく能力を拾う)。2 層とも実行する
   # 層 1: 直接の write API (実測 103 hit)
   grep -rnE '(open\([^)]*["'"'"']w|write_text|write_bytes|unlink|rmtree|os\.remove|truncate|os\.replace|fs::remove|fs::write)' \
     allaganeye/ gui/src-tauri/src/
   # 層 2: subprocess 経由の書込 -- 本 codebase では実書込の大半が ffmpeg (実測 31 hit)
   grep -rnE '(subprocess\.(run|Popen)|Command::new)' allaganeye/ gui/src-tauri/src/
   ```

   > **層 2 を省略すると sweep は無意味になる**: 本 codebase の不可逆書込の大半は **ffmpeg subprocess** が行うため、層 1 だけでは「出力先パスを決める箇所」が 1 件も挙がらない。#930 の diff に対する実測は 層 1 = 0 hit (production code) / subprocess・出力先パス系 = 30 hit だった。

2. **各 hit に述語を 1 件ずつ当て、判定結果を Step 5b の表に転記する。** 「diff 内にあるか」ではなく「述語を満たすか」で分類する。**diff 外の hit も対象**である (root cause が横断クラスである以上、同じ欠陥が diff 外に既存で潜んでいる可能性がまさに論点)
3. 述語を満たさない hit は、diff 内なら **(A)**、diff 外なら Step 5b の判定基準で **(A)** / **(B)** を決める。**「diff 外だから対象外」は理由にならない。** 対象外にするなら「別領域・別機能」trigger を満たすかで判定する
4. hit にはコメント・docstring も混入する (粗い網)。**網を細くして取りこぼすより、粗く拾って仕分ける**方を選ぶ

> **なぜ grep だけでは足りないか**: 「破壊的操作の述語が弱い」という root cause は、欠陥側の文字列では表現できない。**正しい実装と誤った実装が同じ語彙を使う**ためである。能力側 (書込呼び出し) を全列挙して述語を人が当てるしかない。この構造は memory `feedback_destructive_predicate_needs_identity` / `feedback_source_scan_guard_scope` で 2 度実証されている。

#### mirror 元の検証状況確認 (Refs #935 P2-2)

**mirror 元を参照する実装を書いた / 見つけた場合、mirror 元自身の検証状況を確認する。**

- 「既存の X と同じ形にした」「X から移植した」「X をミラーした」という記述・コメント・PR 本文を見つけたら、**X が検証済みである根拠を確認する**
- **mirror 元は「正」ではなく「未検証の前例」である可能性がある。** 検証済みの根拠 (test / 実機確認 / レビュー記録) が辿れないなら、mirror 先と同じ観点で mirror 元も点検し、欠陥があれば Step 5b の表に**両方**を計上する
- 3 世代以上の複製 (A → B → C) を見つけたら **最初の A まで遡る**。複製が進むほど「前例があるから正しい」という誤った確信だけが強まる

> **根拠**: PR #930 の欠陥は GUI → Python → Python の 3 世代複製で同クラスの 2 例目が新設されたものだった。memory `feedback_mirroring_impl_copies_latent_bugs` (「mirror 元は『正』でなく未検証の前例。#899→#591 で 2 リリース分の潜在バグを発掘」) が同じ構造を別件で実証している。

### 6. レビュー結果をユーザーに報告

Step 5b のトリアージ表を前提に、以下のテンプレート構造で**レビュー報告 markdown を生成して presenting する** (`AskUserQuestion` は呼ばない、PR コメント投稿もしない)。Step 7 / 8 へ自動進行する。

**重要**: 「課題はあるがスコープ外だから放置」の選択肢は存在しない。摘出課題は必ず表経由で (A)/(B)/(C) に振り分ける。

**レビュー報告テンプレート** (PR コメントまたはユーザー提示時の推奨構造):

````markdown
# Review Round N

- **前回差分**: <Round 2 以降のみ: 前 Round で指摘した課題のうち解消したもの / 未解消のもの>
- **本 Round 新出**: <Round 2 以降のみ: 本 Round で新規に発見した課題>
- (Round 1 では上記 2 行を省略可)

## ベース同期確認 (Step 2)

- **形式 (2.1)**: `baseRefName` = <name> (`develop-x.x.x` 形式の確認結果)
- **base 最新化と直近マージ PR (2.2)**: `mergeStateStatus` = <CLEAN / BEHIND>、影響候補 PR = <なし / [#N (touched: `<path>`)]>
- **同期判定 (2.3)**: skip (影響候補なし) / 確認済み・regression なし / 取り込み依頼コメント投稿 / 詳細調査
- **並行 worktree PR (2.4)**: 検出ゼロ / [#M (理由: 重複 / 並走 / 既マージ)] (束ね PR の場合は `- #500: <結果>` `- #501: <結果>` のように issue ごとに bullet で列記)

## 受け入れ条件チェック (逐条)

| # | 条件 | 実証 (diff / test / log) | 判定 |
|---|---|---|---|
| 1 | <条件 1> | `path/to/file.py:123` / `test_xxx` / CI log | ○ / × / 部分的 |
| 2 | ... | ... | ... |

## ギャップ分析 (Step 5a)

- **カバレッジ**: <未テスト分岐 / 観点欠落 / なし>
- **観点**: <happy path / error path / edge case の抜け / なし>
- **エッジケース**: <入力境界 / 並行性 / resource 枯渇 / なし>

## 摘出課題トリアージ (Step 5b、握り潰し禁止)

| # | 摘出内容 | 出所 | 処置 | 根拠 |
|---|---|---|---|---|
| 1 | <具体的な課題> | 受け入れ条件 #N / CI / 5a カバレッジ / 5a 観点 / 5a エッジケース / 5 ロジック / 5 ドキュメント | (A) PR コメント / (B) 新規 issue / (C) 既存 #N 追記 | <分類根拠> |

※ 摘出課題ゼロの場合のみ「該当なし」と明記して表省略可。1 件でも摘出したら必ず表に載せる。

## 検証推奨

- **自動 (CI)**: `pytest tests/test_xxx.py::test_yyy` / `ruff check .`
- **手動検証 (PR 作成セッション側で実施済みのはず)**: <long-running / GPU / audio 統合 の具体手順>

## 判定

<LGTM / 修正依頼 / ブロッカー>

[<session-id>]
````

### 7. 次のアクション提案 (PR コメント投稿は廃止)

本 skill は Step 6 のレビュー報告を user に提示するのみで、`gh pr comment` 等の **PR コメント投稿は一切行わない**。代わりに次のアクション提案を以下のテンプレートで user に提示する:

```markdown
## 次のアクション提案

判定: <LGTM / 修正依頼 / ブロッカー>

### 推奨フロー
- **(A) 修正依頼が残っている場合**: `/iterate-review $ARGUMENTS` で review-fix ループを起動し、最終 summary コメントを 1 個投稿してマージ準備まで自動化
- **(A) 課題ゼロかつ受け入れ条件 ✓**: ユーザーが `gh pr merge $ARGUMENTS --squash` で squash merge → 紐づく issue は `/close-issue <issue#>` でクローズ
- **発散・スコープ問題が疑われる場合**: scope-guard skill / 設計再検討
```

PR コメント投稿が必要な特殊ケース (例: 別レビュアーへ正式に依頼書を残したい) は **ユーザーが手動で行う**。skill が自動投稿することはない。

**補足: scope-guard 発動時の AskUserQuestion 投げ先**

スコープ逸脱に該当する摘出課題で (A) / (B) を確定する場合、AskUserQuestion は**ユーザー (Idios) に対して**実施する。PR 作成セッションではない。

根拠: scope-guard skill は Iron Law 3 の執行機構として人間メンテナの判断 (a)/(b)/(c) を強制するゲートであり、PR 作成セッション側に判断権限はない (`scope-guard/SKILL.md` §Step 3 参照)。

### 7a. 再レビューラウンド管理 (`/iterate-review` に移管)

Round 2+ の再レビュー管理 (収束判定 / 発散判定 / 打ち切り判断) は `/iterate-review` skill (新規) に移管した。本 skill は単一 round の review エンジンとしてのみ動作する。

複数 round 自動実行が必要な場合は `/iterate-review <PR#>` を invoke すること。

### 8. マージ後の close-issue handoff (PR が MERGED 状態の場合)

本 skill はレビュー専用セッション契約のため `gh issue close` / `gh pr merge` を一切実行しない (冒頭「重要」節と同じ責務分離原則に基づく、Iron Law 4 担保)。close 操作は専用 skill `/close-issue <番号>` または手動で実施すること。

PR がマージ済みで本 skill が呼ばれた場合 (= 確認用の事後レビュー) のみ意味がある節。マージ前の課題ハンドオフは `/iterate-review` Step 5 (LGTM 候補通知) で吸収する。

#### 手順

1. 受け入れ条件最終検証 (Step 3) を実施
2. 紐づく issue 番号を抽出 (`gh pr view <PR#> --json closingIssuesReferences,body` + 本文 `Refs #N` 抽出)
3. ユーザーに `/close-issue <番号>` を案内 (本 skill では実行しない、Iron Law 4)
4. 検証結果を summary コメント (1 個) として PR に投稿することを user に提案 (`AskUserQuestion`「投稿する / 投稿しない」、フォーマットは `/iterate-review` Step 4 の summary template と同一 = `docs/superpowers/specs/2026-05-10-iterate-review-and-review-pr-redesign.md` §4.2 参照)

#### マージ前 (`OPEN` state) で本 skill が呼ばれた場合

通常フロー (Step 1-7) のみ実施し、本 Step 8 は skip する。残課題対応は `/iterate-review` 推奨を Step 7 で提示済み。

#### 孤立 PR (issue 紐付けなし) の場合

`/close-issue` 案内は省略可 (issue がないため)。Step 7 で提示した「次のアクション」に従う。

## 環境制約とフォールバック

各 Step の前提が欠けている状況 (受け入れ条件ゲートが動かない / CI が未整備 / 参照リソースにアクセスできない 等) で、レビューを**完全 skip せず**に代替判定する手順を規定する。fallback 適用時は「どの制約が発生してどう代替したか」を Step 6 の報告テンプレート冒頭に 1 行明示する。

### §A. 孤立 PR (紐づく issue が存在しない)

対象: PR 本文に `#N` / `Refs #N` / `Fixes #N` 等の issue 参照がない。chore / doc 軽微修正 / skill 運用由来 PR に多い。

**適用手順**:

1. Step 3 の `/enforce-acceptance-criteria` は issue 番号を特定できないため実行不可。代わりに Step 3 補助チェック (実装内容 ⇔ PR 本文一致 / Closes キーワード不在 / テスト存在) を**必須チェック**として実施
2. Step 5 ドキュメント整合性と Step 5a ギャップ分析で「PR 本文に書かれた目的」を受け入れ条件の代替として扱う
3. Step 5b トリアージは通常通り実施 (握り潰し禁止)
4. Step 6 テンプレートの「受け入れ条件チェック」セクションは「該当なし (issue 未紐付け)」と明記し、代替判定根拠を箇条書き
5. Step 8 は「紐づく issue がない場合」の分岐に従う

### §B. `/enforce-acceptance-criteria` 実行不可

対象: skill 未配備環境 / 別セッションで subagent 実行中 / slash command が disable された環境。

**適用手順**:

1. 代替として本 SKILL.md Step 3 + `enforce-acceptance-criteria/SKILL.md` の手順を手動で再現する (`gh pr view $ARGUMENTS --json body` で PR 本文を取得し、受け入れ条件節を抽出 → 各条件を diff / test / log で実証)
2. Step 6 テンプレート冒頭に「fallback: /enforce-acceptance-criteria 未実行 — 手動で Iron Law 1 逐条検証を実施」と明示
3. 手動実施でも**逐条引用 + diff / test 対応付け**の質は妥協しない (Iron Law 1 違反は skill 実行有無に関わらず NG)
4. Step 3 補助チェックの **`Closes` / `Fixes` / `Resolves` キーワード不在** は §B fallback 時も**必須チェック** として実施する。`/enforce-acceptance-criteria` が動く場合は二重チェックになるため明示スキップ可だが、fallback 時は enforce-ac の自動検証がないため省略しない

### §C. CI 未設定 / CI failing が意図的

対象: 新規リポジトリで CI 未整備 / CI が temporary disabled / CI 失敗が既知で対応済み。

**適用手順**:

1. Step 4 で CI 未設定 / skip 状況を明示 (例: 「CI 未設定のため手動 lint / test 実行を求める」)
2. PR 本文に手動検証ログが記録されているか確認。記録がなければ (A) PR コメントで追記要求
3. 手動検証の範囲も明示する (lint / typecheck / unit test / 手動シナリオテスト のどこまでカバーか)

### §D. doc-only PR の CI 波及検証

対象: doc 変更 PR で PR 本文が「doc-only だからテスト不要」と主張する場合。

**適用手順**:

1. doc 内で変更されたパス・ファイル名・コマンド例が `.github/workflows/` の YAML や `allaganeye/` コード内でも参照されているか `grep` で確認
2. 変更範囲が「純粋な文章のみ」(参照パス・識別子 変更を含まない) であれば CI 波及チェックをスキップ可
3. パス・識別子 変更を含む場合は CI 設定 / コード参照の整合性を Step 5 ドキュメント整合性チェックで必須項目化
4. `grep` 検証の判定水準:
   - (i) grep が残存 import / 参照を検出 → (A) PR コメントで修正依頼
   - (ii) grep 結果なし + CI typecheck green (pyright / tsc) → 実質的に未使用と判定可、追加対応不要
   - (iii) grep 結果なし + CI typecheck 未設定 → typecheck 追加を (B) 別 issue 起票 or PR 作成セッションに依頼
   - 動的 import (`importlib` / `import()` 実行時解決) は grep / typecheck だけでは検出不可。該当ソースに動的 import が含まれる場合は PR 作成セッションに実機検証を依頼

**doc-only PR での旧用語 literal sweep**: doc-only PR であっても用語 / フィールド名 / コマンド名が変更された場合 (パス変更を含まない場合でも)、他ファイルへの旧用語残存を root cause として識別し Step 5c sweep を適用する。本 §D の「パス・識別子変更」はパス名に限らず PR で変更された任意のキーワード (用語 / フィールド名 / 関数名) を含む。旧用語が他ファイルに散在している場合は用語統一の root cause として Step 5c 全件 sweep が必要。

### §E. 参照ファイル追加 (バイナリ等) を伴う PR

対象: 特徴量ファイル / 画像 / 音声参照 / sample data 等のバイナリを PR で追加する場合。

**適用手順**:

1. `gh pr diff $ARGUMENTS --name-only` で追加ファイルの存在を確認
2. PR 本文にファイルサイズ・次元・生成条件・validated set の出典が明記されているか確認
3. 明記なしなら (A) PR コメントで追記要求
4. 実体の参照整合性が受け入れ条件に含まれる場合 (例: `audio/refs/wr.npz` のロードテスト) は、該当テストが含まれるか確認

### §F. 束ね PR の追加手順 (Step 3 補足)

対象: 1 PR で 2 件以上の issue を同時に閉じる PR。Step 3 冒頭で言及した独立検証の詳細手順。

**適用手順**:

1. PR 本文から参照 issue 番号をすべて列挙 (`Refs #N #M` 形式)
2. `gh issue view <番号>` を各 issue に対し実行し、受け入れ条件を独立に取得
3. Step 6 テンプレートの「受け入れ条件チェック」表を issue ごとに節分け (`### Issue #N` / `### Issue #M`)
4. 束ね合理性が PR 本文に明記されているか Step 3 補助チェックで確認。明記なしなら (A) PR コメントで合理性説明または分離を要求

### §G. Subagent invocation mode

`/iterate-review` から subagent として呼ばれた場合の動作契約。

#### G.1 Mode 検出

呼び出し prompt に以下のマーカーが含まれている場合 subagent mode:

`__ITERATE_REVIEW_SUBAGENT_MODE__`

(`/iterate-review` Step 2.1 の prompt template に固定文字列として埋め込む)

#### G.2 動作差分

| 観点 | Standalone mode | Subagent mode |
| --- | --- | --- |
| Step 2.3 base sync AskUserQuestion | 通常通り | skip: 影響候補ありなら findings に「需 user 判断: base regression」と記載 |
| Step 2.4 並行 PR AskUserQuestion | 通常通り | skip: 検出されたら findings に記載 |
| Step 5b 摘出 AskUserQuestion (個別 (A)/(B)/(C)) | 通常通り | skip: skill 内基準で auto 分類、ambiguous case のみ findings の `ambiguous_judgments` に明示 |
| Step 6 報告 | conversation 内 presenting | final message に markdown で含める |
| Step 7 次のアクション提案 | user に提示 | skip: orchestrator (`/iterate-review`) が代行 |
| Step 8 マージ後 handoff | 必要なら実行 | skip |
| `gh pr comment` 投稿 | 一切しない (本 skill 改訂後) | 一切しない (subagent mode でも禁止) |

#### G.2.1 Subagent mode 自動分類規約 ((A) 強優先 + 握り潰し禁止)

Subagent mode で Step 5b の (A)/(B)/(C) 自動分類を行う際の厳格規約:

1. **すべての finding に必ず分類を付与する**: 観察コメントのみ・スコープ対象外と自己判断・軽微だから無視 は **すべて NG** (orchestrator 側 parse error として再 dispatch される)
2. **default は (A)**: 「指摘は原則すべて PR 内対応」を継承。CI failure / latent type error / 隣接ファイル lint 違反 / 古い API 残存 / 古い doc 記述 / 環境起因の問題 等は全部 (A)
3. **(B) は厳格 3 条件 AND**: `別領域・別機能` AND `1 セッション超の独立設計が必要` AND `本 PR 同梱で受け入れ条件検証が破綻` の **すべて満たす場合のみ** (B)。1 つでも欠ければ (A)。**サイズ単独 / scope-out 単独 / 受け入れ条件直結性単独では (B) 化不可**。**注 (C2 設計意図)**: subagent mode (本項) は AND 3 条件で厳格判定 (機械処理のため parse error リスク低減を優先)。standalone `/review-pr` 単体使用時は Step 5b の OR 3 択 trigger (`外部依存・側チケット調整が必要` 単独でも (B) 有効) を継続する。この非対称は意図的設計
4. **(C) は重複起票回避 trigger のみ**: 同テーマの既存 issue が存在する場合のみ。「新規 issue を作るべきだが既存に書いた方が綺麗」は不可
5. **判定に迷う finding**: findings_table の処置列に `(A)*` と記載し (default は (A))、`ambiguous_judgments` セクションに当該 finding を詳述する。findings_table に `ambiguous` 単独で記載することは禁止 (`(A)*` + ambiguous_judgments 補足が正式記法、orchestrator はこの行を ambiguous_judgments セクションと cross-reference してユーザー gate に bubble する)
6. **rationale 列に判定根拠を必ず記載**: (B) を選ぶ場合は 3 条件 AND 該当根拠、(C) を選ぶ場合は既存 issue 番号、(A) は省略可

#### G.3 戻り値構造 (subagent → orchestrator)

final message に以下のセクションを順序固定で含める:

1. `## acceptance_criteria_status` (各条件 ✓/×/部分的 + evidence)
2. `## findings_table` (Step 5b トリアージ表 markdown、各行に分類必須)
3. `## ambiguous_judgments` (auto 判断できなかった点。空でもセクション自体は必須記載)
4. `## recommendation` (LGTM / fix-required / divergent)
5. `## meta` (mergeStateStatus / 並行 PR 状態 / CI 状態。round 番号は `/iterate-review` 側管理のため不要)

## 呼び出し例

```text
/review-pr 443
```

ユーザーが PR 番号を指定して呼び出す。Claude は自動的に段階を進め、要所で `AskUserQuestion` により判断を仰ぐ。

## Red flags (レビュー中に浮かんだら STOP)

Iron Law Red Flags と呼応。以下の合理化が浮かんだら LGTM 寸前でも止まる。

| 出てくる合理化 | 実態 |
| --- | --- |
| 「受け入れ条件は大体満たしてる」 | Iron Law 1 違反。逐条引用 + diff / test の対応付けが必須 |
| 「明らかな diff だからレビュー簡略化でよい」 | Step 5a ギャップ分析 skip は NG。明示指示不要で自動実施 |
| 「unit test pass だから手動検証不要」 | GPU / audio / 長時間動画は mock 不可。PR 作成セッションに実機検証実施 (or 結果報告) を要求 |
| 「観察コメントだけ残して別 issue にしない」 | #399 B 違反。観察で止めず、別 issue 起票または scope-guard で escalate |
| 「スコープ対象外だから PR コメントも issue 化も不要」 | **握り潰しパターン**。Iron Law 3 違反。Step 5b トリアージで (B) 新規 issue か (C) 既存 issue 追記 のどちらかに必ず振り分ける。「対象外」という理由で沈めてはいけない |
| 「軽微だから言及しなくてよい」「ついでに誰かが直すだろう」 | 摘出した瞬間にトリアージ対象。軽微度は処置分類 (A)/(B)/(C) の選択根拠であって、握り潰しの根拠にはならない |
| 「束ねた issue は条件が共通だろう、1 件分で代表検証」 | Iron Law 1 違反。束ね PR は各 issue の受け入れ条件を独立に逐条検証する (Step 3 束ね PR 節 / 環境制約 §F 参照) |
| 「孤立 PR (issue なし) だから受け入れ条件ゲートは skip してよい」 | 環境制約 §A 違反。skip ではなく fallback (PR 本文の目的記述を代替として逐条検証) を適用する |
| 「doc-only だから CI 影響は検証しなくてよい」 | 環境制約 §D 違反。パス・識別子変更を含む doc PR は `.github/workflows/` / コード側参照に波及し得る。grep 検証が必須 |
| 「参照ファイル (バイナリ) の存在は diff で確認したから実体検証は不要」 | 環境制約 §E 違反。サイズ・次元・生成条件の PR 本文明記を (A) PR コメントで要求する |
| 「explicit N 箇所だけ列挙して全件 grep を要求しない」 | divergence 原因。詳細は **Step 5c (同種パターン sweep 規約、canonical)** 参照。PR #675 で 3 round 必要だった失敗パターン |
| 「standalone mode で findings を PR コメントで投稿しよう」 | 本 skill は comment 投稿しない契約 (改訂ルール)。投稿が必要な場合のみ user が手動で行う |
| 「subagent mode で AskUserQuestion を呼ぼう」 | `/iterate-review` には届かない。findings の `ambiguous_judgments` に記載するのが正しい (§G.3) |

## よくある失敗

- **受け入れ条件の逐条引用を飛ばす**: 「全項目 OK」のサマリで済ませる → Iron Law 1 違反。`/enforce-acceptance-criteria` の出力を再確認し、条件 1 つずつに diff / test / log を対応付ける
- **ギャップ分析を自然言語コメントだけで書く**: 「テスト不足ぎみ」等の印象コメント → Step 5a の軸 (カバレッジ / 観点 / エッジケース) に紐付けて具体化し、軸ごとに「未テスト箇所 X」「欠落観点 Y」で列挙する
- **摘出課題を「PR スコープ外」と自己判断して握り潰す**: 「本 PR の範囲ではないから言及不要」「軽微なので指摘しなくてよい」と判定して PR コメントにも issue にも残さない → **最重要の失敗パターン**。Iron Law 3 違反。Step 5b トリアージ表で全課題を (A) PR コメント / (B) 新規 issue / (C) 既存 issue 追記 のいずれかに必ず振り分ける。「言及しない」は選択肢に存在しない
- **束ね PR を 1 件として扱い各 issue の独立検証を省略**: 「束ねているから条件は共通」「1 つ検証すれば代表として OK」と判断して 1 件分の受け入れ条件のみチェック → Iron Law 1 違反。Step 3 束ね PR 節 / 環境制約 §F に従い、各 issue の受け入れ条件を独立に逐条検証する
- **参照ファイル追加時の実体確認省略**: バイナリ追加を diff の name-only でしか確認せず、サイズ・次元・生成条件の PR 本文明記を要求しない → 環境制約 §E 違反。(A) PR コメントで追記要求する
- **doc 変更 PR が CI 設定に与える波及を検証しない**: 「doc だから CI には関係ない」と判断して `.github/workflows/` / コード側参照の grep 確認を省略 → 環境制約 §D 違反。パス・識別子変更を含む doc 修正は波及確認が必須
- **再レビュー時に前回指摘の全件追跡を省略**: Round 2 以降で「前回指摘の解消確認」と「本 Round 新出」を分けずに混在レポートする → /iterate-review Step 3 (収束 / 発散判定) 違反。前 Round の (A) 課題を findings_history で 1 件ずつ照合し解消/未解消を明示する
- **long-running 検証を自己判断で OK とする**: unit test pass = 全部 OK と誤解。GPU / 長時間動画 / audio 統合は mock 不可のため、PR 作成セッションに実機検証実施 (or 結果報告) を明示要求する
- **提示フォーマットを無視して口語で書く**: レビュー結果が PR コメントに混在して追跡困難 → Step 6 の「レビュー報告テンプレート」構造で投稿
- **explicit N 箇所だけ列挙して全件 grep を要求しない (PR #675 Round 1/3 divergence)**: PR #675 で 3 種類の root cause (literal「関数本体先頭」訂正 / 旧 API `vi.stubEnv('DEV', '' as any)` / DCE 誇張表現) が複数 file に散在し、各 Round で explicit な N 箇所のみ列挙したため Round 1 → 2 → 3 と divergence 発生。詳細手順 (grep 全件 sweep / トリアージ表全件転記 / 修正依頼本文に grep 同梱) は **Step 5c (同種パターン sweep 規約、canonical)** 参照。

## 参考

- `docs/l2-workflow.md` §「レビュー受け入れ基準 (#367 対策)」 / §「タスク種別と進め方」の "PR テスト" 行
- `docs/issue-policy.md` — issue ラベル・ライフサイクル
- #367 — レビュープロセス改善の経緯
- #511 — 本 skill への #475 memory 由来 3 観点 + [mizchi empirical-prompt-tuning](https://github.com/mizchi/chezmoi-dotfiles/blob/main/dot_claude/skills/empirical-prompt-tuning/SKILL.md) 参考ブラッシュアップ
