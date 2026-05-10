# `/iterate-review` 新規追加 + `/review-pr` 機能整理 設計

> **Status**: design (brainstorming 確定、writing-plans 直前)
> **作成**: 2026-05-10 / session `quizzical-goldstine-f91cfb`
> **対象**: 新規 skill `/iterate-review` + 既存 skill `/review-pr` の再設計
> **関連**: 既存 `.claude/skills/review-pr/SKILL.md` / `docs/l2-workflow.md` §「レビュー受け入れ基準」/ Iron Law (`.claude/hooks/session-start.sh`)
> **トリガー**: ユーザー要求「PR 作成後、`/review-pr` を新規作成したサブエージェントで実行し、指摘事項に対応したら再度サブエージェントで `/review-pr` を実行して指摘がなくなるまで繰り返すようスキルを改善したい」(2026-05-10) +「指摘の per-finding PR コメント投稿を廃止、代わりに全指摘対応完了後の summary コメント 1 個に集約。`/review-pr` の機能を整理。両 skill を empirical-prompt-tuning で抜け漏れ・冗長排除」

## §0 概要

### 目的

PR 作成後の review → fix → review ループを `/iterate-review` 新規 skill で自動化し、`/review-pr` が現在持っている per-finding コメント投稿と再レビューラウンド管理を `/iterate-review` 側に集約する。 `/review-pr` は read-only な review エンジンとしてスリム化する。

### 期待効果

- review-fix サイクルの主セッション往復を主導化、ユーザー (Idios) の介入は per-round 1 回 + 収束時 1 回に集約
- per-finding PR コメントの noise を排除し、PR ごとに summary コメント 1 個のみ残す (review 履歴の可読性向上)
- `/review-pr` の責務を「レビュー本体」に集中、iteration management や comment 投稿は `/iterate-review` に移管 (single responsibility)
- **issue 数の収束 (重要)**: 「指摘は原則すべて PR 内対応」の (A) 強優先方針 + (B) 3 条件 AND 厳格判定 + 握り潰し禁止 validation により、PR 1 個あたりの派生 issue 数を最小化。CI failure / latent issue / 隣接ファイルの軽微な問題は当 PR 内で消化し、別 issue にしない (#5 ユーザー要求)
- `feedback_skill_revision_empirical.md` (memory) 規約に基づく empirical-prompt-tuning + post-tuning skill boundary audit で抜け漏れ・冗長・スコープ重複を構造的に除去

### スコープ境界

- 対象: 新規 `/iterate-review` skill / 既存 `/review-pr` skill 改訂 / summary comment template / 両 skill の eval/ (mock シナリオ + requirements + 2 iteration)
- 対象外: PR 作成自動化 / 自動 merge / 自動 close-issue (Iron Law 4 / 5 担保のため依然手動)
- 対象外: `/enforce-acceptance-criteria` / `/scope-guard` / `/create-task` / `/close-issue` / `/release` の機能変更 (`/iterate-review` から呼び出すのみで内部改変なし)

## §1 主要決定事項

ブレインストーミングで AskUserQuestion により確定:

| 観点 | 決定 |
| --- | --- |
| 改善対象 | **新規 skill `/iterate-review`** + 既存 `/review-pr` 改訂の 2 本立て |
| Fix 主体 | **主セッション (orchestrator)** が Edit / Write / commit / push を実行 |
| AskUserQuestion gate (subagent 内) | **subagent は skip + 構造化 findings を return**、主セッションが gate を所持 |
| 停止条件 | **Step 5b 表が (A)/(B)/(C) すべてゼロ** |
| 上限ラウンド | **5** (`/review-pr` 7a 「打ち切り判断」と一致) |
| Round cap / 発散検知時 | **AskUserQuestion 2 択** (i) PR 破棄 + scope-guard 整理 + 再 PR (Recommended) / (ii) abort 手動介入。「残課題を別 issue 化して merge」は #5 (issue 数収束方針) と矛盾するため選択肢から除外 |
| (A) 強優先方針 | **「指摘は原則すべて PR 内対応」**: CI error / latent issue / 隣接ファイルの潜在問題 等も (A) として PR 内修正。(B) trigger は厳格 3 条件 AND (`別領域・別機能` AND `1 セッション超の独立設計` AND `本 PR 同梱で受け入れ条件検証が破綻`) |
| 握り潰し防止機構 | subagent return の全 findings に分類必須 (A/A*/B/C のいずれか)、未分類は parse error → 再 dispatch / user gate へ強制 escalation |
| 起動経路 | **user 手動起動** (`/iterate-review <PR#>`) **+ agent 自動起動** (PR 作成後の主セッションが自走呼出) の両方を許容 |
| (B)/(C) 再 flag 防止 | **H3** = `/iterate-review` state 追跡 + PR body deferred block の併用 |
| CI 待ち | **W1** = push 後 CI green poll (`gh pr checks --watch`、15 分 timeout で escalate) |
| per-finding PR コメント | **廃止** (現 `/review-pr` Step 7 を全削除) |
| 代替投稿 | **収束時に 1 回だけ summary コメント投稿** (HEREDOC + `--body-file -`) |
| アプローチ骨格 | Approach 1 (薄い orchestrator skill、state は会話 + PR body) ベース |
| empirical-prompt-tuning | mock scenario + subagent dispatch + 2 iteration を両 skill に適用 |

## §2 設計: `/iterate-review` skill 本体

### §2.1 メタ情報

- **配置**: `.claude/skills/iterate-review/SKILL.md`
- **frontmatter**:
  - `name: iterate-review`
  - `user-invocable: true`
  - `argument-hint: <PR番号>`
  - `description`: 「PR 作成後の review-fix ループを subagent dispatch で自動化する。`/review-pr` を fresh subagent で実行し findings を構造化 return させ、主セッションが (A) 修正 / (B)(C) handoff / push / CI wait を行い、Step 5b 表が全ゼロまたは Round 5 / 発散検知まで繰り返す。収束時は summary コメント 1 個を投稿。`/review-pr` の per-finding comment 投稿は本 skill が代替する形で廃止する」
- **想定行数**: 280-380 行 (anti-sweep 機構 + (A) bias 強化分で増加)
- **起動経路 2 系統 (両方サポート)**:
  - **user 手動起動**: `/iterate-review <PR#>` を Idios が直接 invoke
  - **agent 自動起動**: PR 作成セッション (= 実装した主セッション) が PR 作成完了直後に `/iterate-review <PR#>` を skill として自走呼出。Iron Law 6 Pre-flight 通過後に呼ぶことが前提 (PR 作成自体は autonomous で OK だが PR 作成の Iron Law 6 は依然厳守)
- **想定ユーザー**: Idios (手動) / 実装主セッション (自動)、PR 作成直後

### §2.2 主要フロー

```text
/iterate-review <PR#>
  Step 0: Pre-flight (PR open / base sync / 並行 worktree PR)
  Step 1: ループ初期化 (Round=1, handoff_state=[], findings_history={}, divergence_counter=0)
  Step 2: Round N 実行
    2.1 Agent tool で fresh subagent に /review-pr (gate skip mode) dispatch
    2.2 structured findings parse
    2.3 Round summary AskUserQuestion (proceed / abort)
    2.4 (A) 各 finding を Edit + ローカル check + commit
    2.5 (B) handoff: /create-task で起票 (3 件以上は AskUserQuestion bulk 確認)
    2.6 (C) handoff: gh issue comment + PR body deferred block 更新
    2.7 push + gh pr checks --watch (15 分 timeout)
  Step 3: 判定
    3.1 (A)/(B)/(C) all 0 → Step 4
    3.2 divergence (3 round 連続 (A) 件数 >= 前) → user gate 2 択 (PR 破棄+再 PR / abort)
    3.3 Round 5 cap → user gate 2 択 (同上)
  Step 4: Final summary comment (HEREDOC で投稿、AskUserQuestion 3 択で承認)
  Step 5: LGTM 候補通知 (user merge → /close-issue handoff、自動 merge は実行しない)
```

### §2.3 Step 0: Pre-flight (~30 行)

- `gh pr view $ARGUMENTS --json state,isDraft,headRefName,baseRefName,closingIssuesReferences` で状態取得
- `state == CLOSED / MERGED` → 「ループ対象外」エラー終了
- `isDraft == true` → AskUserQuestion 3 択 (draft でも進める / draft 解除を待つ / abort)
- base 最新化 + 直近マージ PR + 並行 worktree PR 重複確認は `/review-pr` Step 2 を踏襲 (本 skill では `/review-pr` Step 2 へリンクし、subagent dispatch 内で実行されることに依拠して再掲しない)

### §2.4 Step 1: ループ初期化 (~10 行)

会話 context 内で以下を保持:

- `Round = 1`
- `handoff_state = []` (要素: `{topic, classification, issue_number, round}`)
- `findings_history = {}` (key: round 番号, value: Step 5b 表)
- `divergence_counter = 0` (3 連続で発散検知)

### §2.5 Step 2: Round N 実行 (~100 行)

#### Step 2.1 Subagent dispatch

`Agent` tool (subagent_type: `general-purpose`) で fresh subagent を spawn。prompt template (固定):

````text
__ITERATE_REVIEW_SUBAGENT_MODE__

PR #<N> を review してください。`/review-pr` skill を invoke しますが、以下の特例を必ず適用してください:

1. Step 6 / Step 7 の AskUserQuestion / `gh pr comment` 投稿 を SKIP
2. Step 5b トリアージ表を markdown 表形式で final message に含める
3. 以下の deferred topics は findings から exclude:
   <handoff_state を箇条書き、空なら "(なし)">
4. PR body の `<!-- iterate-review:deferred:start --> ... <!-- iterate-review:deferred:end -->` ブロック内 topics も exclude
5. Step 3 の受け入れ条件逐条検証結果 (`/enforce-acceptance-criteria`) も final message に含める
6. **(A) 強優先方針 + 握り潰し禁止**:
   - **すべての finding に必ず分類 (A) / (A)* / (B) / (C) のいずれかを付与** (`(A)*` は ambiguous case の cross-reference 記法)。観察コメントのみ / スコープ対象外と自己判断 / 軽微だから無視 は **すべて NG** (parse error として orchestrator が再 dispatch)
   - **(A) を最優先**: 「指摘は原則すべて PR 内対応」。CI failure / latent type error / 隣接ファイル lint 違反 / 古い API 残存 / 古い doc 記述 等は全部 (A)
   - **(B) は厳格 3 条件 AND 必須**: 「`別領域・別機能` AND `1 セッション超の独立設計が必要` AND `本 PR 同梱で受け入れ条件検証が破綻`」。1 つでも該当しなければ (A) に分類。**サイズ単独 / scope-out 単独 / 受け入れ条件直結性単独では (B) 化不可**
   - **(C) は同テーマ既存 issue が存在する場合のみ**: 重複起票回避が唯一の trigger。「新規 issue を作るべきだが既存に書いた方が綺麗」は不可
   - 判定に迷う finding は `(A)*` と記載し、ambiguous_judgments に詳述する (`ambiguous` 単独記載は禁止。`(A)*` が正式記法 = §G.2.1 item 5 準拠。orchestrator 側で user gate)
7. final message は以下の構造で return:

   ```markdown
   ## acceptance_criteria_status
   | # | 条件 | 実証 | 判定 |

   ## findings_table
   | # | 摘出内容 | 出所 | 処置 | 根拠 |

   ## ambiguous_judgments
   - <subagent が auto 判断できなかった点。orchestrator → user gate に bubble するため明示>

   ## recommendation
   <LGTM / fix-required / divergent>

   ## meta
   - mergeStateStatus: <CLEAN/BEHIND/...>
   - 並行 PR: <検出ゼロ / [#X handled]>
   - CI status: <green/failing/pending>
   ```
````

#### Step 2.2 Findings parse + 握り潰し防止 validation

Agent tool の戻り値 markdown から `## findings_table` セクションの表行を抽出。各行を `{round, n, finding, source, classification, rationale}` として `findings_history[round]` に蓄積。

**抽出時の必須 validation (握り潰し防止)**:

1. **全 finding に classification がある**: 各行の処置列が `(A)` / `(A)*` / `(B)` / `(C)` のいずれか。空欄 / 「観察のみ」 / 「対象外」/ `ambiguous` 単独等は **parse error**
2. **(B) 主張行には trigger 根拠列がある**: rationale 列に「別領域・別機能 AND 1 セッション超 AND 受け入れ条件検証破綻」3 条件への該当言及があるか。1 条件のみの (B) は **parse error** (= subagent が誤分類)
3. **subagent return に「無視」「観察のみ」「スコープ対象外」のキーワードを単独で含む行がない**: 文字列 grep で検出、ヒットしたら **parse error**
4. **`ambiguous_judgments` セクションが存在する** (空でもセクション自体は必須): 不在は parse error

**parse error 時の対処**:

- 1 度目: 主セッションが subagent に対して具体的に欠陥を伝えて再 dispatch (Agent tool 再実行)
- 2 度目: AskUserQuestion で user に「 subagent が分類規約を満たさない findings を返している。手動でトリアージするか abort するか」を提示

これにより subagent が「スコープ外だから言及しない」「軽微だから無視」「観察コメントのみ残す」等の **握り潰しパターン** を構造的に弾く。

#### Step 2.3 Round summary AskUserQuestion (1 round 1 回のみ)

Round N の集計表示 + AskUserQuestion 2 択:

```text
Round N findings:
- (A): <件数>
- (B): <件数>
- (C): <件数>
- 受け入れ条件 (Step 3): <全 ✓ / 部分 / 全 ×>
- ambiguous_judgments: <件数> (詳細は別途展開)

選択:
- (i) proceed (本 round の findings を処理) (Recommended、ambiguous なし時)
- (ii) abort (loop 中断、現状で /create-task など手作業に切替)
```

`ambiguous_judgments` がある場合、追加 AskUserQuestion でユーザー判断を仰ぐ。 1 AskUserQuestion call は最大 4 questions まで束ねられる仕様 (= AskUserQuestion tool 上限) を活用し、5 件以上は複数 call に分割。1 round あたりの AskUserQuestion 呼び出し総数は 「Round summary 1 + ambiguous_judgments の必要分」 を上限とする。

#### Step 2.4 (A) findings 修正

各 (A) に対し主セッションが:

1. 該当 path:line を Read で内容確認
2. Edit で修正
3. 変更 path に応じた local check (Iron Law 6 サブ条 = `docs/l2-workflow.md` §「PR 作成 path 別自動チェック」):
   - Python (`*.py`): `ruff check . && ruff format --check . && pyright && pytest`
   - GUI (`gui/src/**`, `gui/src-tauri/**`): `npm run lint && npm run typecheck && npm test && npm run build && cargo check`
   - Markdown (`docs/**.md`, `*.md`): `bash scripts/check-markdownlint.sh`
4. **1 round = 1 commit** で集約: 全 (A) を 1 つの commit にまとめる (round 単位の atomicity を確保、Round 別 SHA を summary コメントで参照しやすくするため)。message テンプレ: `fix(round-N): <要約> (Refs #<元 issue>)`。例外として、push 失敗で reset → 再 commit が必要な場合のみ複数 commit になる可能性を許容

#### Step 2.5 (B) findings handoff (新規 issue 起票、限定例外パス)

> **(B) 起票は限定例外**: 「指摘は原則すべて PR 内対応」(§1 (A) 強優先方針) に従い、ほとんどの finding は (A) で消化される。本 step に来るのは Step 2.2 validation を通過した「真に (B) trigger 3 条件 AND 該当」の finding のみ。スコープ単独・サイズ単独・受け入れ条件直結性単独で (B) 化された finding はここに到達しない (= validation で reject される)。

各 (B) に対し:

1. **(B) trigger 3 条件 AND 達成** を再確認: `別領域・別機能` AND `1 セッション超の独立設計が必要` AND `本 PR 同梱で受け入れ条件検証が破綻` の **すべて満たす** ことを rationale で確認。1 つでも欠ける場合は (A) に再分類して Step 2.4 へ戻す
2. **3 件以上の (B) は Iron Law 2 に従い AskUserQuestion で全件確認** (1 件 sample 提示 + 「全件 OK / 個別調整 / やめる」3 択)。3 件以上の (B) が一度に出るのは **設計疑い** のシグナルであり、user に「PR スコープが大きすぎる可能性」を提示
3. 2 件以下はそのまま `/create-task` で起票
4. 起票後の issue 番号を `handoff_state` に追加
5. PR body の deferred block を更新:

   ```bash
   gh pr edit $ARGUMENTS --body-file - <<'EOF'
   <既存 body>

   <!-- iterate-review:deferred:start -->
   ## Deferred Findings (managed by /iterate-review)

   - [B] Round 1: <topic 50 字以内> → deferred-to: #708 (新規)
   - [C] Round 2: <topic> → deferred-to: #680 (既存)

   <!-- iterate-review:deferred:end -->
   EOF
   ```

#### Step 2.6 (C) findings handoff (既存 issue 追記)

1. 既存 issue へ `gh issue comment <既存 issue#> --body-file -` で方針記録 (HEREDOC、UTF-8 対策)
2. `handoff_state` 追加 + PR body deferred block 更新 (Step 2.5 同様)

#### Step 2.7 Push + CI wait

- `git push origin <head-branch>`
- `gh pr checks $ARGUMENTS --watch` で CI 状態確定 (success / failure) を 15 分まで待機
- **CI green (success)**: 次 round へ進める
- **CI red (failure)**: 本 step では abort しない。次 round の `/review-pr` Step 4 が CI 失敗を findings に拾う前提 (`/review-pr` Step 4 「失敗あり: 失敗ジョブ名と概要を user に報告」を踏襲)。CI red が複数 round 連続で再発生する場合は §2.6 divergence 検知で打切り判定
- **timeout (15 分超)**: AskUserQuestion 3 択 (待ち続ける / CI 無視で次 round / abort)

### §2.6 Step 3: 収束 / 発散 / 打ち切り判定 (~40 行)

#### Step 3.1 収束 (success path)

(A)/(B)/(C) all 0 → Step 4 へ。

#### Step 3.2 発散検知

- `divergence_counter` 管理:
  - Round N の (A) 件数 `>=` 前 round の (A) 件数 (= 減少していない、増えた場合も含む) → `counter++`
  - Round N の (A) 件数 `<` 前 round の (A) 件数 (= 減少) → `counter = 0` にリセット
  - Round 1 (前 round 不在) の場合は counter 初期値 0 のまま
- `counter == 3` (= 3 round 連続で減少なし) → user gate 2 択

#### Step 3.3 ラウンドキャップ

Round == 5 + 未収束 → user gate 2 択。

#### Step 3.4 user gate 2 択 (発散・キャップ共通)

```text
- (i) PR 破棄 + scope 整理 + 再 PR (Recommended)
    → 現 PR を `gh pr close` (branch 維持、後続調査用に残す)
    → /scope-guard で残課題を整理し sub-PR に分割
    → /create-task で必要なら子 issue を整備
    → 各 sub-PR を順次作成 → /iterate-review で個別収束
    → user 主導の workflow、本 skill は abort して引き継ぐ
- (ii) abort (state を残して手動介入)
    → /iterate-review は終了、PR / branch は現状維持
    → user が手動で残 finding を判断 (merge する / 修正続行 / scope-guard 等)
```

> **(iii) 残 (A) 別 issue 化選択肢の不採用**: 「残 (A) を別 issue 化して merge」は #5 (issue 数収束方針) と矛盾するため**選択肢から除外**。Round 5 まで来たということは PR スコープが大きすぎたか実装方針が不適切のため、PR 単位での再構成 (i) が筋。残 (A) を逃がし弁にしないことで「(A) 内消化」原則を機構的に担保する。
>
> **手動 abort 後の運用**: (ii) を選んだ場合、user が手動で「現 PR を merge」「修正続行」を判断するが、無造作に「残 (A) を別 issue 化」しないこと。PR scope が現状で正しいか先に再検討する。

### §2.7 Step 4: Final summary comment (~30 行)

§4 で詳述。1 PR コメントを投稿 (HEREDOC + `--body-file -`)。投稿前 AskUserQuestion 3 択 (投稿する / 微調整 / skip)。

### §2.8 Step 5: 次の handoff (~20 行)

「LGTM 候補です。`gh pr merge $ARGUMENTS --squash` で merge してください。マージ後は `/close-issue <issue#>` で実測再検証してから手動クローズしてください」を user に提示。本 skill 内で merge / close は実行しない (Iron Law 4 + 5 担保)。

### §2.9 環境制約・フォールバック

- **§A 孤立 PR (issue 紐付けなし)**: `/review-pr` §A を継承。subagent prompt に「孤立 PR fallback 適用」と明記
- **§B `/enforce-acceptance-criteria` 実行不可**: subagent 側で fallback、本 skill は subagent 結果に従う
- **session crash mid-loop**: state は会話 + PR body deferred block。再 invoke で deferred block + 残 commit から推論して継続可能 (PR body は永続)

### §2.10 Red Flags (本 skill 固有)

| 浮かんだ思考 | 実態 |
| --- | --- |
| 「subagent の findings を信じすぎず、自分で再判定」 | Iron Law 5 違反。subagent が Step 5b で出した分類は尊重する。再判定は user gate のみ |
| 「Round 6 で打ち切らずあと 1 回」 | divergence パターン。skill 規定の cap (5) を破らない |
| 「(A) 修正で副次的に (B) trigger 該当の変更が発生」 | scope-guard 案件。Step 2.4 中に追加 (B) 判定なら次 round へ持ち越さず即 handoff (ただし 3 条件 AND 厳格判定) |
| 「summary コメント前に LGTM コメントを別途投稿」 | 二重投稿。final summary が LGTM の役割も兼ねる |
| 「per-finding でコメント投稿した方が個別追跡しやすい」 | 仕様違反。per-finding 投稿は本設計で全廃 (ユーザー指示) |
| 「軽微な指摘だから observe 表記で済ませよう」 | **握り潰しパターン**。Step 2.2 validation で parse error。すべての finding は (A)/(A)*/(B)/(C) のいずれかに必ず分類 |
| 「scope 外だから (B) 起票しよう」 | (A) 強優先方針違反。scope 外単独は (B) trigger 不成立。3 条件 AND を確認、満たさなければ (A) |
| 「CI が flaky / 環境起因だから無視で OK」 | 仕様違反。CI failure / latent issue / 環境起因問題はすべて (A) で PR 内対応 |
| 「Round 5 で残った 1 件くらい別 issue にしておこう」 | (iii) 不採用方針違反。残 (A) を別 issue に逃がさず、PR 破棄 (i) または手動 abort (ii) のいずれかで対応 |
| 「issue 数を増やしたくないが、本件は scope-out なので例外」 | (B) trigger 3 条件 AND を再確認。1 つでも欠ければ (A)。「例外」が頻発するのは判定基準のブレ |

## §3 設計: `/review-pr` 機能整理

### §3.1 変更方針サマリ

| 区分 | Step / 節 | 変更 | 理由 |
| --- | --- | --- | --- |
| 維持 | Step 1 (PR 概要) / Step 2 (base sync 2.1-2.4) / Step 3 (受け入れ条件) / Step 4 (CI) / Step 5.0 (code quality subagent) / Step 5.1 (doc 整合) / Step 5a (gap) / Step 5b (triage) / Step 5c (pattern sweep) / §A-§F | そのまま | レビュー本体ロジックは健在 |
| **修正** | Step 6 (レビュー結果報告) | `AskUserQuestion 4 択` を削除、報告 markdown を生成して終わり | `/iterate-review` が user gate を担う。重複削除 |
| **削除** | Step 7 修正依頼コメント投稿 | 全節削除 | per-finding `gh pr comment` を全廃 (ユーザー指示) |
| **削除** | Step 7a 再レビューラウンド管理 | 全節削除 (`/iterate-review` Step 3 へ移管) | iteration management は `/iterate-review` の責務 |
| **修正** | Step 8 マージ後ハンドオフ | 「マージ済みなら `/close-issue` へ」のみ残す。標準フロー (open + 課題あり) は `/iterate-review` 推奨 + 「課題なら手動修正」の 2 択にスリム化 | comment 廃止に整合 |
| **新設** | §G Subagent invocation mode | 新規節追加 | `/iterate-review` から呼ばれた時の挙動を契約として明記 |
| 維持 | Red Flags 表 | Step 7 関連 (「PR ブランチを checkout して自分で修正」等) は文言整理。残りは維持 | Iron Law 関連は触らない |

### §3.2 整理後の Step 構造

```text
1. PR 概要取得                          (維持)
2. ベースブランチ同期確認               (維持、subagent mode で 2.3/2.4 AskUserQuestion skip)
3. 受け入れ条件チェックリスト           (維持)
4. CI / Lint / Test ステータス確認      (維持)
5. ロジック / ドキュメントレビュー       (維持)
   5.0 plugin subagent code quality
   5.1 project 固有 doc 整合性
5a. ギャップ分析                        (維持)
5b. 摘出課題トリアージ                  (維持、subagent mode で AskUserQuestion skip)
5c. 同種パターン全件 sweep              (維持)
6. レビュー結果報告                     (修正: AskUserQuestion 削除、報告 markdown 生成のみ)
7. 次のアクション提案                   (修正: comment 投稿廃止、推奨アクションを user に提示)
8. マージ後のハンドオフ (MERGED state)  (修正: スリム化、summary 投稿は user 承認任意)
§A-§F. 環境制約とフォールバック         (維持)
§G. Subagent invocation mode            (新設)
```

### §3.3 修正後 Step 6 (レビュー結果報告)

**Before**: 報告 markdown 生成 + `AskUserQuestion` 4 択 (LGTM / 修正依頼 / 修正依頼 + 派生 issue / LGTM + 派生 issue) + Step 7 / 8 を実行

**After**: 報告 markdown を生成して presenting only。`AskUserQuestion` は呼ばず Step 7 / 8 へ自動進行。報告テンプレート自体 (受け入れ条件表 / トリアージ表 / 検証推奨 / 判定) は完全維持。

### §3.4 修正後 Step 7 (次のアクション提案)

**Before**: LGTM なら `gh pr comment "LGTM. ..."` 投稿 / 修正依頼なら per-finding `gh pr comment --body-file -` 投稿

**After**: 投稿は一切行わない。代わりに次のアクション提案を user に提示:

```markdown
## 次のアクション提案

判定: <LGTM / 修正依頼 / ブロッカー>

### 推奨フロー
- **(A) 修正依頼が残っている場合**: `/iterate-review $ARGUMENTS` で review-fix ループを起動し、最終 summary コメントを 1 個投稿してマージ準備まで自動化
- **(A) 課題ゼロかつ受け入れ条件 ✓**: ユーザーが `gh pr merge $ARGUMENTS --squash` で squash merge → 紐づく issue は `/close-issue <issue#>` でクローズ
- **発散・スコープ問題が疑われる場合**: scope-guard skill / 設計再検討
```

PR コメント投稿が必要な特殊ケース (例: 別レビュアーへ正式に依頼書を残したい) はユーザーが手動で行う。skill が自動投稿することはない。

### §3.5 修正後 Step 8 (マージ後ハンドオフ)

**Before**: PR に紐づく issue 番号特定 → `/close-issue <番号>` 提案 + 孤立 PR の (B)/(C) 残処理確認 + マージ済み skill 呼び出しフォールバック

**After**: マージ済み (`MERGED`) 状態のみ意味がある節として明記:

```markdown
### 8. マージ後の close-issue handoff (PR が MERGED 状態の場合)

PR がマージ済みで本 skill が呼ばれた場合 (= 確認用の事後レビュー):

1. 受け入れ条件最終検証 (Step 3) を実施
2. 紐づく issue 番号を抽出
3. ユーザーに `/close-issue <番号>` を案内 (本 skill では実行しない、Iron Law 4)
4. 検証結果を summary コメント (1 個) として PR に投稿することを user に提案
   (`AskUserQuestion`「投稿する / 投稿しない」、フォーマットは `/iterate-review` Step 4 と同一)
```

「マージ前の課題ハンドオフ」(現状 Step 8 主目的のひとつ) は `/iterate-review` Step 5 で吸収。

### §3.6 新設 §G. Subagent invocation mode

```markdown
## §G. Subagent invocation mode

`/iterate-review` から subagent として呼ばれた場合の動作契約。

### G.1 Mode 検出

呼び出し prompt に以下のマーカーが含まれている場合 subagent mode:

`__ITERATE_REVIEW_SUBAGENT_MODE__`

(`/iterate-review` Step 2.1 の prompt template に固定文字列として埋め込む)

### G.2 動作差分

| 観点 | Standalone mode | Subagent mode |
| --- | --- | --- |
| Step 2.3 base sync AskUserQuestion | 通常通り | skip: 影響候補ありなら findings に「需 user 判断: base regression」と記載 |
| Step 2.4 並行 PR AskUserQuestion | 通常通り | skip: 検出されたら findings に記載 |
| Step 5b 摘出 AskUserQuestion (個別 (A)/(B)/(C)) | 通常通り | skip: skill 内基準で auto 分類、ambiguous case のみ findings の `ambiguous_judgments` に明示 |
| Step 6 報告 | conversation 内 presenting | final message に markdown で含める |
| Step 7 次のアクション提案 | user に提示 | skip: orchestrator (`/iterate-review`) が代行 |
| Step 8 マージ後 handoff | 必要なら実行 | skip |
| `gh pr comment` 投稿 | 一切しない (本 skill 改訂後) | 一切しない (subagent mode でも禁止) |

### G.2.1 Subagent mode 自動分類規約 ((A) 強優先 + 握り潰し禁止)

Subagent mode で Step 5b の (A)/(B)/(C) 自動分類を行う際の厳格規約:

1. **すべての finding に必ず分類を付与する**: 観察コメントのみ・スコープ対象外と自己判断・軽微だから無視 は **すべて NG** (orchestrator 側 parse error として再 dispatch される)
2. **default は (A)**: 「指摘は原則すべて PR 内対応」(`/iterate-review` §1 (A) 強優先方針) を継承。CI failure / latent type error / 隣接ファイル lint 違反 / 古い API 残存 / 古い doc 記述 / 環境起因の問題 等は全部 (A)
3. **(B) は厳格 3 条件 AND**: `別領域・別機能` AND `1 セッション超の独立設計が必要` AND `本 PR 同梱で受け入れ条件検証が破綻` の **すべて満たす場合のみ** (B)。1 つでも欠ければ (A)。**サイズ単独 / scope-out 単独 / 受け入れ条件直結性単独では (B) 化不可**
4. **(C) は重複起票回避 trigger のみ**: 同テーマの既存 issue が存在する場合のみ。「新規 issue を作るべきだが既存に書いた方が綺麗」は不可
5. **判定に迷う finding**: `(A)*` と記載し、`ambiguous_judgments` セクションに詳述する (`ambiguous` 単独記載は禁止。`(A)*` が正式記法。orchestrator 側で user gate)
6. **rationale 列に判定根拠を必ず記載**: (B) を選ぶ場合は 3 条件 AND 該当根拠、(C) を選ぶ場合は既存 issue 番号、(A) は省略可

### G.3 戻り値構造 (subagent → orchestrator)

final message に以下のセクションを順序固定で含める:

1. `## acceptance_criteria_status` (各条件 ✓/×/部分的 + evidence)
2. `## findings_table` (Step 5b トリアージ表 markdown、各行に分類必須)
3. `## ambiguous_judgments` (auto 判断できなかった点。空でもセクション自体は必須記載)
4. `## recommendation` (LGTM / fix-required / divergent)
5. `## meta` (mergeStateStatus / 並行 PR 状態 / CI 状態。round 番号は `/iterate-review` 側管理のため不要)
```

### §3.7 削除節の影響評価

| 失われる機能 | 代替 |
| --- | --- |
| 個別の修正依頼コメント (path:line + 修正案 fenced block) | `/iterate-review` の主セッションが直接 Edit で修正 |
| Round N の前回差分追跡 | `/iterate-review` の `findings_history` で全 round 追跡、final summary に集約 |
| 別セッション再 invoke のレビュー履歴 | `/iterate-review` final summary が PR コメント永続化 |

`/review-pr` を別セッションのレビュアー (= reviewer ≠ author) が手動コメントするユースケースは本プロジェクトでは想定外 (Idios 単独運用) のため、影響は最小。ただし spec / SKILL.md に「reviewer = author 前提」と明示する。

### §3.8 Red Flags 整理

**削除する Red Flag** (Step 7 関連):

- 「PR ブランチを checkout して自分で修正した方が速い」 → `/iterate-review` 経由で主セッションが修正するのが標準なので削除

**維持する Red Flag**: 受け入れ条件「大体満たしてる」/ unit test 万能 / 観察のみ / スコープ対象外で握り潰し / 束ね PR / 孤立 PR / doc-only / バイナリ追加 / explicit N 箇所 sweep / PR ブランチ checkout (read 目的の例外)

**新規追加する Red Flag**:

- 「standalone mode で findings を PR コメントで投稿しよう」 → 本 skill は comment 投稿しない契約 (改訂ルール)
- 「subagent mode で AskUserQuestion を呼ぼう」 → `/iterate-review` には届かない、findings の `ambiguous_judgments` に記載が正

## §4 設計: Summary コメント仕様

### §4.1 配信元

- **`/iterate-review` Step 4** (収束時、必須): 1 PR コメント投稿
- **`/review-pr` Step 8 (MERGED state)** (任意、user 承認時のみ): 同フォーマット流用

### §4.2 テンプレート

````markdown
# /iterate-review Summary

PR は <R> ラウンドの review-fix で収束。全 findings 解消完了。

## Findings by Round

| Round | (A) | (B) | (C) | 主な topic |
|---|---|---|---|---|
| 1 | <n> | <n> | <n> | <"; "区切り 30 字以内> |
| <R> | 0 | 0 | 0 | 収束 |

## Resolutions

### (A) PR 内修正
- Round <R> #<n>: `path:line` <topic 50 字以内> → `<commit SHA[:7]>`

### (B) 別 issue 起票
- Round <R>: <topic> → #<新規 issue#> (新規)

### (C) 既存 issue 追記
- Round <R>: <topic> → #<既存 issue#> (追記コメント link)

(各 section 該当なしなら "(なし)" のみ)

## Final 受け入れ条件 (acceptance criteria)

| # | 条件 | 実証 | 判定 |
|---|---|---|---|
| 1 | <条件> | `path:line` / `test_name` / CI log | ✓ |

## Final State

- CI: ✓ green (last commit `<SHA[:7]>`)
- 受け入れ条件: 全 ✓
- (A) 残: 0 / (B) handoff: <#N1, #N2 or なし> / (C) handoff: <#M1 or なし>
- 並行 PR: <検出ゼロ / [#X handled]>
- base sync: <CLEAN / 取り込み済み>

[<session-id>]
````

### §4.3 投稿方式 (Windows + Git Bash UTF-8 対策)

`feedback_gh_command_ja_heredoc.md` 準拠で `--body-file -` + HEREDOC:

```bash
gh pr comment <PR#> --body-file - <<'EOF'
# /iterate-review Summary
...
EOF
```

inline `--body "..."` は日本語が UTF-8 破損するため禁止。

### §4.4 投稿前 user 承認 gate

`/iterate-review` Step 4 で AskUserQuestion 3 択:

- (i) 投稿する (Recommended)
- (ii) 微調整して投稿 (markdown を user に提示 → 修正 → 再承認)
- (iii) skip 投稿 (loop は終了、コメントは残さない)

`/review-pr` Step 8 (MERGED state) でも同じ承認フロー。

### §4.5 length 対策

| 手法 | 採否 |
| --- | --- |
| `<details>` で Round 詳細を折り畳み | 採用 |
| 別コメントに分離 | 不採用 (「1 つにまとめて」要求と矛盾) |
| topic 文字数制限 (30 / 50 字) | 採用 |

`<details>` 適用例 (Round 詳細表):

```markdown
<details>
<summary>Round 1 詳細 (4 件)</summary>

| # | Finding | Class | Resolution |
|---|---|---|---|
| 1 | ... | (A) | ... |

</details>
```

## §5 設計: empirical-prompt-tuning 計画

### §5.1 対象スキル & eval 配置

| スキル | eval 配置 | 既存 | 新規 |
| --- | --- | --- | --- |
| `/iterate-review` | `.claude/skills/iterate-review/eval/` | なし | フル一式 |
| `/review-pr` | `.claude/skills/review-pr/eval/` | あり (scenario A-E + reports) | 既存更新 + scenario F 追加 |

`feedback_skill_revision_empirical.md` (memory) 準拠で **mock シナリオ + subagent dispatch + 要件チェックリスト + 2 iteration**。

### §5.2 `/iterate-review/eval/` 新規構築

#### ファイル一覧

```text
eval/
├── requirements.md                      # 要件チェックリスト 24 項目
├── scenario_a_simple_fix.md             # 1-2 round で収束する単純 (A) 修正
├── scenario_b_divergence.md             # 3 round 無進捗で divergence gate (PR 破棄+再 PR)
├── scenario_c_round_cap.md              # Round 5 で cap gate (PR 破棄+再 PR)
├── scenario_d_lgtm_first.md             # Round 1 で 0 findings (即収束)
├── scenario_e_bc_handoff.md             # (B)/(C) handoff + 再 flag 防止
├── scenario_f_ci_timeout.md             # CI 15 分 timeout
├── scenario_g_subagent_mode.md          # /review-pr subagent mode 連携
├── scenario_h_summary_format.md         # summary コメント format 検証
├── scenario_i_anti_sweep.md             # 握り潰し防止 validation + (A) 強優先 + (B) 3 条件 AND
└── reports/
    ├── iter_0_baseline.md
    ├── iter_1_revaluation.md
    └── summary.md
```

#### `requirements.md` 主要 20 項目 (抜粋)

| # | 要件 | 検証 scenario |
| --- | --- | --- |
| 1 | Step 0 で MERGED/CLOSED は abort、draft は 3 択 AskUserQuestion | a, d |
| 2 | Step 2.1 prompt template に必須要素 (gate skip / structured return / deferred-list) | e, g |
| 3 | Step 2.3 Round summary AskUserQuestion = 1 round 1 回のみ | 全 |
| 4 | Step 2.5 (B) 3 件以上は bulk AskUserQuestion (Iron Law 2) | e |
| 5 | Step 2.7 push 後 CI green wait + 15 分 timeout で 3 択 escalate (CI red は次 round に流す) | f |
| 6 | Step 3.1 (A)/(B)/(C) 全ゼロ判定 | a, d |
| 7 | Step 3.2 divergence counter で 3 round 連続無進捗検知 → 2 択 gate (PR 破棄+再 PR / abort) | b |
| 8 | Step 3.3 Round 5 cap で 2 択 gate (同上) | c |
| 9 | Step 4 summary コメント 1 個 (HEREDOC) | h |
| 10 | summary template の必須 5 要素 (Round 表 / Resolutions / 受け入れ条件 / Final State / session-id) | h |
| 11 | summary 投稿前 AskUserQuestion 3 択 | h |
| 12 | (B)/(C) handoff 後 PR body deferred block 更新 | e |
| 13 | (B)/(C) handoff の subagent prompt exclusion 反映 | e |
| 14 | Step 2.2 握り潰し防止 validation: 全 finding 分類必須 / (B) 3 条件 AND 根拠必須 / 「無視」「観察のみ」キーワード弾き / ambiguous_judgments セクション必須 | a, e (新追加 scenario_i_anti_sweep.md でも検証) |
| 15 | (A) 強優先方針: CI failure / latent issue / 隣接 lint 違反は (A) 分類 | a, scenario_i |
| 16 | (B) 厳格 3 条件 AND: 1 条件のみは (A) に再分類 | scenario_i |
| 17 | Iron Law 1: マージ前に受け入れ条件全達成 | 全 |
| 18 | Iron Law 2: 3+ bulk 前 AskUserQuestion | e |
| 19 | Iron Law 3: scope-creep は (B)/(C) 振り分け (3 条件 AND 厳守) | a, e, scenario_i |
| 20 | Iron Law 4: skill 内で `gh pr merge` / `gh issue close` 実行禁止 | 全 |
| 21 | Iron Law 5: 曖昧点で AskUserQuestion (subagent `ambiguous_judgments` bubble) | a |
| 22 | Iron Law 6: push 前 local check pass + CI green wait | a, f |
| 23 | Red Flag 違反パターンが skill 文中に明記 (新規 5 項目含む) | static check |
| 24 | agent 自動起動 (PR 作成セッションが skill として呼ぶ) でも Standalone と同等動作 | scenario_a で agent-trigger variant 作成 |

### §5.3 `/review-pr/eval/` 更新

#### 既存ファイル更新

- `requirements.md`: `Step 6 AskUserQuestion 削除` / `Step 7 comment 投稿全廃` / `§G subagent mode` の項目追加
- `scenario_a_central.md` ~ `scenario_e_sweep_*.md`: 期待 output から「per-finding comment 投稿」を削除、「報告 markdown 生成」に置換
- `scenario_d_step8_handoff.md`: MERGED state での summary 投稿確認 + `/close-issue` 案内 のみ残す

#### 新規追加

- `scenario_f_subagent_mode.md`:
  - mock `/iterate-review` からの dispatch シミュレーション
  - prompt 内 `__ITERATE_REVIEW_SUBAGENT_MODE__` マーカー検出
  - Step 2.3 / 2.4 / 5b / 6 / 7 / 8 AskUserQuestion 全 skip
  - 戻り値の必須 5 セクション
  - `gh pr comment` 呼び出し皆無

#### `reports/` (新規)

- `iter_0_post_redesign_baseline.md`
- `iter_1_post_redesign_revaluation.md`
- `summary_post_redesign.md`

(既存 reports/ は historical record として残し、新ファイル名で post-redesign 結果を記録)

### §5.4 Iteration 手順 (2 iteration 標準)

#### Iter 0: Baseline

1. `/iterate-review` SKILL.md 初版執筆
2. `/review-pr` SKILL.md 改訂版執筆
3. 各 scenario で subagent dispatch (general-purpose) → scenario の mock PR data + 該当 skill 文を渡してドライラン
4. expected behavior (requirements 列挙項目) と actual の diff を `iter_0_baseline.md` に記録
5. ギャップを抽出 (典型: 要件未カバー / 冗長 / 矛盾 / placeholder / Red Flag 漏れ)

#### Iter 1: Revaluation

1. iter_0 ギャップに基づき SKILL.md 修正
2. 同 scenario で再 dispatch
3. `iter_1_revaluation.md` に改善結果を記録
4. 全 requirements が pass / non-blocker のみであれば iteration 終了

#### Iter 2 (任意)

iter_1 で structural gap が残った場合のみ実施。残らなければ skip。

#### Summary

`summary.md` (or `summary_post_redesign.md`) に最終結果を集約。failure があれば「deferred 別 issue 起票」を提案 (本 PR 内で対応するか別 issue かは Iron Law 3 + scope-guard 判断)。

### §5.5 Post-tuning skill boundary audit (新規必須 step)

両 skill の iter_1 完了後、**両者のスコープ境界を audit する** ステップを必須化する。empirical tuning 単体では「各 skill が個別に要件を満たしているか」しか検証されないため、**冗長重複と境界欠落を別途チェック** する必要がある (ユーザー要求 #3)。

#### audit 観点

1. **冗長判定** (両 skill が同じ責務を重複保持していないか):
   - 例: `/review-pr` Step 2 base sync ↔ `/iterate-review` Step 0 Pre-flight の重複度
   - 期待: `/review-pr` で base sync 検証 / `/iterate-review` Step 0 は PR 状態のみ確認 + base sync は subagent 内 `/review-pr` Step 2 に委ねる
   - 各 step で「どちらが行うか」が一意に決まるか確認

2. **境界欠落判定** (どちらにも責務が無く落ちている操作がないか):
   - 例: `(A) 修正後の post-fix 検証`, `(B)/(C) handoff 後の deferred block update timing`, `divergence_counter リセット条件` 等が両 skill 内のいずれかに明記されているか
   - 期待: すべての state transition に「誰が責任を持つか」が決まっている

3. **重複文章判定** (同じガイダンスが両 skill に冗長記載されていないか):
   - Iron Law 関連 / Red Flag 表 / 環境制約 §A-§F 等が両方に書かれていれば一方を canonical 化、もう一方は参照のみにする
   - canonical 候補: project 全体の規約は `docs/l2-workflow.md`、skill 個別の例外は当該 SKILL.md

4. **誤誘導判定** (片方の skill が他方の skill 出力に依存して誤解する箇所がないか):
   - 例: `/review-pr` の戻り値構造が変わった時 `/iterate-review` の parser が壊れる箇所
   - 例: subagent mode マーカー文字列が両方で一致しているか (`__ITERATE_REVIEW_SUBAGENT_MODE__`)
   - クロスリファレンスの整合性確認

#### audit 手順

1. iter_1 完了後、両 SKILL.md を並べて読む
2. 上記 4 観点それぞれで Q&A 形式チェックリストを作る:
   - 冗長: 同じことを 2 箇所で書いていないか? (Y → 1 箇所に統合)
   - 欠落: ある操作の責務が両 skill にも `docs/l2-workflow.md` にも書いていないか? (Y → 該当先に追加)
   - 重複文章: 共通 ガイダンスが冗長に書かれていないか? (Y → canonical 化 + 参照)
   - 誤誘導: 一方の変更で他方が壊れる contract 不整合がないか? (Y → contract section を増設して合意)
3. audit 結果を `audit.md` (両 eval/ どちらかに配置、例: `.claude/skills/iterate-review/eval/skill_boundary_audit.md`) として記録
4. 修正が必要なら iter_2 として再評価。境界が clean なら audit 完了

#### audit を skip できる条件

両 skill の SKILL.md が両方とも 「自セッション内で完結する責務 + 他 skill を呼び出す call site」 のみで構成され、共通ガイダンスが両方に展開されていないことが目視で明らか、かつ scenario_g (subagent mode 連携) の iter_1 が pass している場合は audit を簡略可。

ただし「明らか」の自己判断は Iron Law 5 違反リスク (Red Flag) のため、判断に迷ったら **必ず audit を実施** する。

## §6 影響範囲

### §6.1 ファイル追加

- `.claude/skills/iterate-review/SKILL.md` (新規 ~340 行、anti-sweep + (A)-bias 記載分増)
- `.claude/skills/iterate-review/eval/requirements.md` (24 項目)
- `.claude/skills/iterate-review/eval/scenario_a_simple_fix.md` ~ `scenario_h_summary_format.md` (8 ファイル) + `scenario_i_anti_sweep.md` (新規 anti-sweep + (A) 強優先 + (B) 3 条件 AND 検証)
- `.claude/skills/iterate-review/eval/reports/iter_0_baseline.md`, `iter_1_revaluation.md`, `summary.md`
- `.claude/skills/iterate-review/eval/skill_boundary_audit.md` (§5.5 audit 結果記録)

### §6.2 ファイル修正

- `.claude/skills/review-pr/SKILL.md` (Step 6 / 7 / 7a / 8 改訂、§G 追加。差分 ~150 行)
- `.claude/skills/review-pr/eval/requirements.md` (項目追加 / 削除 marked-out)
- `.claude/skills/review-pr/eval/scenario_a_central.md` ~ `scenario_e_sweep_*.md` (期待 output 更新)
- `.claude/skills/review-pr/eval/scenario_d_step8_handoff.md` (MERGED 限定に変更)
- `.claude/skills/review-pr/eval/scenario_f_subagent_mode.md` (新規追加)
- `.claude/skills/review-pr/eval/reports/iter_0_post_redesign_baseline.md`, `iter_1_post_redesign_revaluation.md`, `summary_post_redesign.md` (新規追加)
- `docs/l2-workflow.md` § 「タスク種別と進め方」 (skill 一覧に `/iterate-review` 追記、起動経路 「user 手動 + agent 自走」 両方を明記)
- `CLAUDE.md` § 「コマンド」 / § 「開発ワークフロー」 / § 「Plugin との関係」 (skill 一覧 + workflow 整理 + (A) 強優先方針追記 + agent 自走起動経路追記)
- `.claude/hooks/session-start.sh` は修正対象外: Iron Law 自体は変更しない。`/iterate-review` は既存 Iron Law を遵守する機構であって新ルールを追加しない

### §6.3 ユーザー (Idios) 体感への影響

| 項目 | Before | After |
| --- | --- | --- |
| PR 作成後の review トリガー | `/review-pr <PR#>` で 1 round 実施 → 修正コメント手動対応 → 再 invoke | `/iterate-review <PR#>` で自走 (manual or PR 作成 agent 自動起動) → user は per-round 確認 + 収束時承認のみ |
| PR コメント数 | per-finding (大量) | summary 1 個 (収束時) |
| AskUserQuestion 回数 | 多 (Step 2.3 / 2.4 / 5b / 6 / 7 + 再 invoke ごとに繰返し) | 1 round に 1-2 回 + 収束時 1 回 + (発散・cap 時) 1 回 (2 択) |
| Round 履歴の永続化 | PR コメント (散在) | summary コメント 1 個 (集約) + PR body deferred block (B/C) |
| 派生 issue 数 | 「scope-out → 別 issue」が頻発、issue 数が増え続ける | (A) 強優先 + (B) 3 条件 AND 厳格 + 握り潰し validation で派生 issue を最小化 (issue 数収束) |
| Round cap (5) 到達時 | 4 択 (split / redesign / scope-narrow / abort) で迷う | 2 択 (PR 破棄 + 再 PR / abort) で workflow が明確 |
| 摘出問題の取りこぼし | reviewer が「対象外」「軽微」で握り潰し可能 (人間判断) | subagent return 時の自動 validation で構造的に防止 (parse error → 再 dispatch / user gate) |

## §7 Iron Law 整合性

| Iron Law | 関連箇所 | 整合性 |
| --- | --- | --- |
| 1: PR merge には全受け入れ条件 ✓ | `/iterate-review` 各 round で `/review-pr` 経由 `/enforce-acceptance-criteria` 呼出 / Step 5 で merge は user に委譲 | ✓ |
| 2: 3+ bulk operation 前に AskUserQuestion | Step 2.5 (B) 3 件以上で bulk AskUserQuestion | ✓ |
| 3: scope-creep は新 issue | (B)/(C) handoff 機構が scope-out を別 issue 化 | ✓ |
| 4: Closes/Fixes/Resolves 禁止、手動 close | Step 5 で merge は user / close は `/close-issue` handoff | ✓ |
| 5: 曖昧点は独断禁止 | subagent `ambiguous_judgments` を main session が user gate に bubble / divergence・cap 時 user gate 2 択 | ✓ |
| 6: PR creation には verified check | 本 skill は PR 作成後に走るため Iron Law 6 主体は PR 作成セッションだが、各 round の push 前 local check + push 後 CI green wait で品質保持 | ✓ |

## §8 自己参照リスク (注意点)

新規 `/iterate-review` 導入 PR 自体は `/iterate-review` がまだ使えないため、人間が手作業で多 round review-fix する必要がある。

**対応策**:

- spec / plan に「初回 PR (本設計の実装 PR) は手動 review」と明記
- 初回 PR の review は **改訂後 `/review-pr` が動作確認の意味で使える** (subagent mode は使わないが、Step 1-5 + 6 報告生成は新版で動く)
- 初回 PR マージ後の **2 回目以降の使用 PR** から `/iterate-review` を実運用

## §9 plan 段取り (writing-plans handoff 用、概略)

writing-plans に handoff 後、概ね以下の粒度で plan へ展開予定:

- **T1**: `/review-pr` SKILL.md 改訂 (Step 6 / 7 / 7a / 8 + §G 追加 + §G.2.1 (A) 強優先 + 握り潰し防止規約) + eval 既存 scenario 更新 + scenario_f 新規 + iter_0_post_redesign_baseline
- **T2**: `/iterate-review` SKILL.md 初版 + eval requirements 24 項目 + 9 scenario (scenario_i_anti_sweep 含む) + iter_0_baseline
- **T3**: 両 skill iter_0 → iter_1 改善 (gap 修正) + reports 完成 + summary
- **T4**: post-tuning skill boundary audit (§5.5) + audit.md 記録 + 必要なら iter_2
- **T5**: `docs/l2-workflow.md` 更新 (skill 一覧 + 新ワークフロー反映 + agent 自動起動経路明記)
- **T6**: `CLAUDE.md` 「コマンド」section / 「skill 一覧」 / 「Plugin との関係」更新 + (A) 強優先方針追記
- **T7**: PR 作成 + 手動 review (初回のみ)

## §10 参考

- `.claude/skills/review-pr/SKILL.md` (改訂対象)
- `.claude/skills/review-pr/eval/` (既存 eval 構造の参考)
- `docs/l2-workflow.md` § 「レビュー受け入れ基準」 / § 「PR 作成 Pre-flight」 / § 「Self-Test Report 規約」
- `.claude/hooks/session-start.sh` (Iron Law)
- `CLAUDE.md` § 「Plugin との関係」 (TDD / brainstorming / subagent-driven-development 採用方針)
- memory: `feedback_skill_revision_empirical.md` (empirical-prompt-tuning ガイド)
- memory: `feedback_gh_command_ja_heredoc.md` (UTF-8 対策)
- 関連 PR / issue: 本 skill 群が初運用される PR、および `/review-pr` の改訂源 issue は plan 化時に確定
