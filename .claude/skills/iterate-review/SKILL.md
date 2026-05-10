---
name: iterate-review
description: PR 作成後の review-fix ループを subagent dispatch で自動化する。`/review-pr` を fresh subagent で実行し findings を構造化 return させ、主セッションが (A) 修正 / (B)(C) handoff / push / CI wait を行い、Step 5b 表が全ゼロまたは Round 5 / 発散検知まで繰り返す。収束時は summary コメント 1 個を投稿。`/review-pr` の per-finding comment 投稿は本 skill が代替する形で廃止する。
user-invocable: true
argument-hint: <PR番号>
---

PR 作成後の review → fix → review ループを自動化する。指定された PR をレビューと修正のループで収束させ、最終的に summary コメントを投稿する。

## 起動経路 (2 系統)

- **user 手動**: `/iterate-review <PR#>` を Idios が直接 invoke
- **agent 自動**: PR 作成セッション (= 実装した主セッション) が PR 作成完了直後に `/iterate-review <PR#>` を skill として自走呼出。Iron Law 6 Pre-flight 通過後に呼ぶ前提

## 主要フロー (overview)

1. Step 0: Pre-flight (PR open / base sync / 並行 worktree PR)
2. Step 1: ループ初期化 (Round=1, handoff_state=[], findings_history={}, divergence_counter=0)
3. Step 2: Round N 実行 (subagent dispatch → parse → AskUserQuestion → fix/handoff → push → CI wait)
4. Step 3: 判定 (収束 / 発散 / 打ち切り)
5. Step 4: Final summary comment (HEREDOC で投稿、AskUserQuestion 3 択で承認)
6. Step 5: LGTM 候補通知 (user merge → /close-issue handoff)

詳細仕様: [docs/superpowers/specs/2026-05-10-iterate-review-and-review-pr-redesign.md](../../docs/superpowers/specs/2026-05-10-iterate-review-and-review-pr-redesign.md)

## 手順

### Step 0: Pre-flight

PR の状態を確認し、ループ可能か判定する。

```bash
gh pr view $ARGUMENTS --json state,isDraft,headRefName,baseRefName,closingIssuesReferences
```

判定:
- `state == CLOSED` または `state == MERGED` → 「ループ対象外」エラー終了
- `isDraft == true` → AskUserQuestion 3 択 (draft でも進める / draft 解除を待つ / abort)
- それ以外 (state == OPEN + isDraft == false) → Step 1 へ

#### Base sync + 並行 PR 確認

base 最新化 + 直近マージ PR + 並行 worktree PR 重複確認は `/review-pr` Step 2 を踏襲。本 skill では `/review-pr` Step 2 へリンクし、subagent dispatch (Step 2.1) 内で実行されることに依拠して再掲しない。Pre-flight 段階では `gh pr view` の取得のみで十分。

### Step 1: ループ初期化

会話 context 内で以下を保持:

- `Round = 1`
- `handoff_state = []` (要素: `{topic, classification, issue_number, round}`)
- `findings_history = {}` (key: round 番号, value: Step 5b 表)
- `divergence_counter = 0`

### Step 2: Round N 実行

#### Step 2.1 Subagent dispatch

`Agent` tool (subagent_type: `general-purpose`) で fresh subagent を spawn。**毎ラウンド新しい subagent** を起動 (context 汚染回避)。

prompt template (固定):

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
   - **すべての finding に必ず分類 (A) / (B) / (C) / ambiguous のいずれかを付与**
   - **(A) を最優先**: CI failure / latent type error / 隣接ファイル lint 違反 等は全部 (A)
   - **(B) は厳格 3 条件 AND 必須**: `別領域・別機能` AND `1 セッション超の独立設計が必要` AND `本 PR 同梱で受け入れ条件検証が破綻`
   - **(C) は同テーマ既存 issue が存在する場合のみ**
   - 判定に迷う finding は `(A)` を default に置き、ambiguous_judgments に記載
7. final message は以下の構造で return:

   ```markdown
   ## acceptance_criteria_status
   | # | 条件 | 実証 | 判定 |

   ## findings_table
   | # | 摘出内容 | 出所 | 処置 | 根拠 |

   ## ambiguous_judgments
   - <subagent が auto 判断できなかった点。空でもセクション自体は必須記載>

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

1. **全 finding に classification がある**: 各行の処置列が `(A)` / `(B)` / `(C)` / `ambiguous` のいずれか。空欄 / 「観察のみ」 / 「対象外」等は **parse error**
2. **(B) 主張行には trigger 根拠列がある**: rationale 列に「別領域・別機能 AND 1 セッション超 AND 受け入れ条件検証破綻」3 条件への該当言及があるか。1 条件のみの (B) は **parse error** (= subagent が誤分類)
3. **subagent return に「無視」「観察のみ」「スコープ対象外」のキーワードを単独で含む行がない**: 文字列 grep で検出、ヒットしたら **parse error**
4. **`ambiguous_judgments` セクションが存在する** (空でもセクション自体は必須): 不在は parse error

**parse error 時の対処**:

- 1 度目: 主セッションが subagent に対して具体的に欠陥を伝えて再 dispatch (Agent tool 再実行)。具体例: 「Step 5b 表 5 行目の (B) は trigger 根拠が `スコープ外` のみで 3 条件 AND 不成立。(A) に再分類して return せよ」
- 2 度目: AskUserQuestion で user に「subagent が分類規約を満たさない findings を返している。手動でトリアージするか abort するか」を提示

#### Step 2.3 Round summary AskUserQuestion (1 round 1 回のみ)

Round N の集計表示 + AskUserQuestion 2 択。Round 開始時に user 介入を集約する唯一の gate。

提示内容:

````text
Round N findings:
- (A): <件数>
- (B): <件数>
- (C): <件数>
- 受け入れ条件 (Step 3): <全 ✓ / 部分 / 全 ×>
- ambiguous_judgments: <件数> (詳細は別途展開)

選択:
- (i) proceed (本 round の findings を処理) (Recommended、ambiguous なし時)
- (ii) abort (loop 中断、現状で /create-task など手作業に切替)
````

`ambiguous_judgments` がある場合、追加 AskUserQuestion でユーザー判断を仰ぐ。1 AskUserQuestion call は最大 4 questions まで束ねられる仕様 (= AskUserQuestion tool 上限) を活用し、5 件以上は複数 call に分割。1 round あたりの AskUserQuestion 呼び出し総数は「Round summary 1 + ambiguous_judgments の必要分」を上限とする。

`<N>` には PR 番号 ($ARGUMENTS) を埋める。`<handoff_state を箇条書き>` には Step 1 で初期化した `handoff_state` の内容 (空なら "(なし)") を埋める。

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
