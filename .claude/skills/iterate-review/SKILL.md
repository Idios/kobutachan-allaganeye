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

1. Step 0: Pre-flight (PR open / draft / state 確認のみ。base sync は subagent dispatch 内 /review-pr Step 2 に委譲)
2. Step 1: ループ初期化 (Round=1, handoff_state=[], findings_history={}, divergence_counter=0)
3. Step 2: Round N 実行 (subagent dispatch → parse → AskUserQuestion → fix/handoff → push → CI wait)
4. Step 3: 判定 (収束 / 発散 / 打ち切り)
5. Step 4: Final summary comment (HEREDOC で投稿、AskUserQuestion 3 択で承認)
6. Step 5: LGTM 候補通知 (user merge → /close-issue handoff)

詳細仕様: [docs/superpowers/specs/2026-05-10-iterate-review-and-review-pr-redesign.md](../../../docs/superpowers/specs/2026-05-10-iterate-review-and-review-pr-redesign.md)

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

> **subagent 起動規約**: 本 dispatch は [`docs/l2-workflow.md` §subagent 起動規約](../../../docs/l2-workflow.md#subagent-起動規約-746-phase-c--741-task-5-教訓) に準拠する。`__ITERATE_REVIEW_SUBAGENT_MODE__` marker + `(A)*` / ambiguous_judgments の自己申告 (下記 prompt template の item 6 / 7) で HARD-GATE (Stop conditions / 独断 fix 禁止) を担保する。controller (本 skill) が Step 2.2 validation で「無視 / 観察のみ / スコープ対象外」キーワード単独行を parse error とすることで、subagent の独断 fix 倍数を 0 に抑える。F6 / F7 と同型の事象を再発させない。
>
> **Codex fallback (C6)**: subagent が `/review-pr` 内で Codex review (tier 1 = companion script `codex-companion.mjs review` の Bash 実行。slash `/codex:review` は `disable-model-invocation: true` のため agent から invoke 不可 = Idios 専用 tier 3、`docs/l2-workflow.md` §Step 5 の invocation path (3-tier、#795) 参照) を実行して fail した場合は [`docs/l2-workflow.md` §Codex fallback](../../../docs/l2-workflow.md#codex-fallback) の手順に従い superpowers `requesting-code-review` subagent を fallback として起動する。Final summary comment (Step 4) に「Codex fallback notice」を必須記載 (Iron Law 5 整合)。**Step 2.3 の per-round Round summary AskUserQuestion ではなく、収束時に 1 回投稿する Step 4 の summary comment を指す。**
>
> **Codex 出力の読み取り (#949、openai-codex 1.0.4 時点)**: Codex review が exit 0 で完了した場合、subagent は `/review-pr` §「Codex 出力の読み取り」に従い `codex-companion.mjs status --json` で `jobClass == "review"` の job id を特定し、`result <job-id>` で**保存済み全文**を読んでから finding を統合する (**job id は省略しない**)。stdout に見えた分だけで triage するのは禁止。読み取りに失敗した (= `result` が exit 非ゼロ) 場合は理由を 1 行記録する義務があり、subagent は下記 prompt template item 7 の `## meta` に `Codex 出力読み取り` 行として申告し、controller はそれを Step 4 の Final summary へ転記する。**fallback ではないので Codex fallback notice とは別行**。`--background` / `--wait` は付けない (受理されるが無視される)。

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
   - **すべての finding に必ず分類 (A) / (A)* / (B) / (C) のいずれかを付与** (`(A)*` は ambiguous case の cross-reference 記法)
   - **指摘は原則すべて PR 内対応 (Iron Law 1 担保)**: 観察コメントのみ / スコープ対象外と自己判断 / 軽微だから無視 は **すべて NG** (parse error として orchestrator が再 dispatch)
   - **(A) を最優先**: CI failure / latent type error / 隣接ファイル lint 違反 等は全部 (A)
   - **(B) は厳格 3 条件 AND 必須**: `別領域・別機能` AND `1 セッション超の独立設計が必要` AND `本 PR 同梱で受け入れ条件検証が破綻`。**サイズ単独 / scope-out 単独 / 受け入れ条件直結性単独では (B) 化不可**
   - **(C) は同テーマ既存 issue が存在する場合のみ**
   - 判定に迷う finding は `(A)*` と記載し、ambiguous_judgments に詳述する (`ambiguous` 単独記載は禁止。`(A)*` が正式記法 = §G.2.1 item 5 準拠)
7. final message は以下の構造で return する。**下の ```markdown fence は提示のためのもので、return には含めない** (fence 込みで返すか裸で返すかが割れると、セクション終端の判定まで揺れる):

   ```markdown
   ## acceptance_criteria_status
   | # | 条件 | 実証 | 判定 |
   | --- | --- | --- | --- |
   | 1 | <元 issue の受け入れ条件を逐語> | `path:line` / `test_name` / CI job 名 | ○ |
   <条件 1 件につき 1 行。判定は **○ / × / partial の 3 値のみ** (他の記号を使わない)。
    **受け入れ条件がゼロになる原因は 2 通りあり、どちらもセクションを空にせず 1 行を置く**
    (原因の分岐を数えずに定型文を 1 つしか置かないと、書かれていない分岐で実行者が文言を発明する):

    | 原因 | 条件列に書く literal | 判定 |
    | --- | --- | --- |
    | issue はあるが `## 受け入れ条件` 節が無い | `受け入れ条件なし (issue に \`## 受け入れ条件\` 節が存在しない)` | `○` |
    | PR に紐づく issue that が無い (孤立 PR、`/review-pr` §A fallback) | `受け入れ条件なし (PR に紐づく issue が存在しない = 孤立 PR、§A fallback 適用)` | `○` |

    いずれも実証列には代替判定根拠を書く。**この 3 値が本 skill 全体の正**で、
    controller 側の Round summary (Step 2.3) と Final summary (Step 4.2) も同じ記号を使う —
    `✓` 等の別記号を view ごとに使うと写像規則が必要になり、片方の view にだけ
    「他の記号を使わない」と書いた形は、書かれていない view を緩いと読ませる抜け道になる。
    受け入れ条件を持たない issue なら、判定列 `○` の 1 行に
    「受け入れ条件なし (issue に `## 受け入れ条件` 節が存在しない)」と書く — セクションは空にしない>

   ## findings_table
   | # | 摘出内容 | 出所 | 処置 | 根拠 |
   | --- | --- | --- | --- | --- |
   <finding 1 件につき 1 行。**ゼロ件なら見出し + ヘッダ行 + 区切り行の 3 行だけを返し、
    データ行を 1 行も書かない** — literal の正は Step 2.2 §「findings ゼロ件の記法」。
    空でもセクション自体は必須記載 (ambiguous_judgments と同じ規約)>

   ## ambiguous_judgments
   - <subagent が auto 判断できなかった点を 1 件 1 行。**空なら箇条書き行を 1 行も書かず、見出しだけを残す**
     (findings_table のゼロ件がデータ行 0 行なのと対応する。`- (なし)` のような自由文は書かない)>

   ## recommendation
   <LGTM / fix-required / divergent。決定規則: findings_table のデータ行が 0 行 かつ
    受け入れ条件が全件実証済なら `LGTM` / findings が 1 件以上なら `fix-required` /
    同一 topic が round を跨いで再出現しているなら `divergent`。
    **収束判定は controller が findings 件数で行う** (Step 3.1) ため、本フィールドは
    controller の判定を上書きしない — 食い違ったら controller 側が正>

   ## meta
   - mergeStateStatus: <CLEAN/BEHIND/...>
   - 並行 PR: <検出ゼロ / [#X handled]>
   - CI status: <green/failing/pending>
   - Codex 出力読み取り: <成功 (job <job-id> の result 全文を finding の入力にした) / 失敗 (理由: <1 行>、stdout の範囲のみで triage) / 非起動 (理由: <起動条件のどれに不該当か>)>
     <非起動 の理由は `/review-pr` を読まずとも書けるよう、代表形をここに置く:
      `条件1 touched <N> file / <M> lines・条件2 再発 root cause <K> 件・条件3 core 変更対象ファイル 該当 0`>
   ```

8. **Codex review を起動した場合は、finding を `/review-pr` §「Codex 出力の読み取り」の手順で保存済み全文から取り込む。** stdout に見えた分だけで triage しない。`## meta` の `Codex 出力読み取り` 行は**省略不可**で、`失敗` と `非起動` は**理由も必須** (省略はいずれも parse error)。`非起動` の理由には `/review-pr` の「起動記録 (該当時 / 不該当時とも必須)」の非対象行の内容を畳んでよい — **この行以外に Codex 関連の slot を新設しない**
````

#### Step 2.2 Findings parse + 握り潰し防止 validation

Agent tool の戻り値 markdown から `## findings_table` セクションの表行を抽出。各行を `{round, n, finding, source, classification, rationale}` として `findings_history[round]` に蓄積。

#### findings ゼロ件の記法 (#995)

**ゼロ件は例外ではなく通常経路である** (§4.1 が「Round 1 で 0 findings (即収束)」を想定ケースとして
扱っている)。記法を定義しないと実行者ごとに割れ、正しい return が parse error 扱いになる。

**正 — この 3 行をそのままコピーして返す** (`## findings_table` の literal はここ 1 箇所だけが正。
Step 2.1 prompt template item 7 の記述もこのブロックを指す — **行番号ではなく名前で参照する**):

```markdown
## findings_table
| # | 摘出内容 | 出所 | 処置 | 根拠 |
| --- | --- | --- | --- | --- |
```

**区切り行 (`| --- | ... |`) は必須**で、**データ行として数えない**。区切り行が無いと GFM の表として
成立せず、「markdown 表形式で返せ」という要求 (Step 2.1 の subagent 契約) と矛盾する。
Step 4.2 の summary テンプレートも区切り行を**持っている**。**ここで揃えるのは「区切り行の有無」という軸だけ**で、
区切り行の字面 (`| --- |` と `|---|` のパディング差) は揃えていない。

誤りの形と、それを落とす validation item:

| 誤った return | 落ちる item |
| --- | --- |
| `\| - \| なし \| - \| - \| - \|` のようなプレースホルダ **データ行** | **item 1** (処置列が `(A)` / `(A)*` / `(B)` / `(C)` のいずれでもない) |
| `なし` / `N/A` / `該当なし` 等の**自由文**をセクション本文に置く | **item 1** (`\|` で始まらない非空行は表行として読めないため。下記 item 1 の後半を参照) |
| `## findings_table` セクション**自体を省く** | **item 4** (必須セクションの存在検査。ゼロ件とセクション欠落は別事象で、セクションが無い return は「表を作り忘れた / 別書式で返した」と区別できない) |

> **記録義務は分岐を網羅する** (`/review-pr` §「起動記録」、#945)。異常系・非ゼロ件だけに定型を
> 用意すると、正常系 (ゼロ件) のたびに実行者が文言を発明して表記が揺れる。本節はその原則の適用で、
> `## ambiguous_judgments` の「空でもセクション自体は必須記載」と同じ書式・同じ理由である。

**下記 validation item 1-7 に対するゼロ件記法の当たり方** (各項目 1 件ずつ)。
**前提: return 全体が Step 2.1 の final message テンプレート (`## acceptance_criteria_status` /
`## findings_table` / `## ambiguous_judgments` / `## recommendation` / `## meta`) を備えていること。**
本表は「ゼロ件記法がこの item を壊さないか」を見るものであって、「findings_table セクション単体で
足りる」という意味ではない (item 4 / 6 は別セクションの存在を見る):

| item | 検査内容 | ヘッダ行のみの return での判定 |
| --- | --- | --- |
| 1 | 全 finding に classification がある | **通る**。データ行が 0 行なので「classification を欠く行」も 0 行 |
| 2 | (B) 主張行には trigger 根拠列がある | **通る**。(B) 行が 0 行 |
| 3 | 「無視」「観察のみ」「スコープ対象外」を単独で含む行がない | **通る**。ヘッダ行にこれらの語は含まれない (`なし` 等の自由文は本 item ではなく **item 1** で落ちる。帰属は上の誤り表が正) |
| 4 | 必須セクションが存在する | **通る (条件付き)**。ゼロ件でも `## findings_table` / `## ambiguous_judgments` を**両方**置くこと。どちらかを省けば本 item で parse error |
| 5 | 受け入れ条件の未達が findings に反映されている | **通る (条件付き)**。`## acceptance_criteria_status` が全件実証済であることが前提。`×` / `partial` が 1 行でもあるのに findings 0 件なら parse error |
| 6 | (A) 強優先方針違反検出 | **通る**。分類対象の finding が 0 件 |
| 7 | `## meta` に `Codex 出力読み取り` 行がある | **通る (条件付き)**。findings 件数とは独立だが、`## meta` に当該行が無ければ本 item で parse error。Codex 非起動なら `非起動 (理由: ...)` で理由括弧まで必須。禁止語彙は item 7 本文の 3 行が正 (ここには写さない) |

**セクションの定義**: 「セクション」とは **`##` 見出し行から次の `##` 見出し行の直前まで**を指す
(次の見出し行はそのセクションに含まない)。

**item ごとの検査対象 roster (本節が正)**。**「scope を共有する item の集合」ではなく
`(item, 対象セクション, 期待する行形式)` の三つ組で定義する** — 同じセクションを見る item でも
期待する行形式が違うため、集合に畳むと「同じ検査を両セクションに適用する」と読まれて衝突する
(実際 `## ambiguous_judgments` は `-` 始まりの箇条書きが正なので、findings_table 用の
「パイプ始まりでなければ parse error」を当てると 1 件でも書いた時点で必ず落ちる):

| item | 対象セクション | 期待する行形式 |
| --- | --- | --- |
| 1 | `## findings_table` **のみ** | 見出し行 / パイプ始まりの表行 |
| 2 | `## findings_table` のデータ行 | (B) 行の根拠列 |
| 3 | `## findings_table` + `## ambiguous_judgments` | 行形式は問わない (キーワード grep のみ) |
| 4 | `## findings_table` + `## ambiguous_judgments` | セクションの**存在**のみ |
| 5 | `## acceptance_criteria_status` × `## findings_table` の横断 | 判定列と finding の対応 |
| 6 | `## findings_table` のデータ行 | 処置列の分類 |
| 7 | `## meta` | 状態語 + 理由括弧 + 語彙 |

**この表を各 item の本文へ再掲しない** — 再掲すると membership が割れる
(定義だけを 1 箇所にしても roster が複数箇所にあれば同じことが起きる)。

**return 全体の空白の扱い**: セクション間の空行・末尾改行・インデントは**有意ではない**。
検査はいずれも非空行に対して行う。**dispatch prompt の `__ITERATE_REVIEW_SUBAGENT_MODE__` marker は
return に echo しない** (marker は入力側の契約)。

**抽出時の必須 validation (握り潰し防止)**:

1. **全 finding に classification がある / セクション内に表行以外の本文を置かない**: `## findings_table` セクション内の**非空行は、見出し行 (`##` で始まる) か、ヘッダ行・区切り行・データ行 (いずれもパイプ文字で始まる)** でなければならない。パイプ文字で始まらない非空行 (`なし` / `N/A` / `該当なし` / 説明文 等) があれば **parse error** — 自由文を許すと「ゼロ件」と「表を書かずに散文で済ませた」が区別できなくなる。データ行については、各行の処置列が `(A)` / `(A)*` / `(B)` / `(C)` のいずれか。`(A)*` は ambiguous_judgments セクションとの cross-reference が必須 (subagent が自動判断できなかった finding に使用、`ambiguous` 単独記載は禁止)。空欄 / 「観察のみ」 / 「対象外」/ `ambiguous` 単独等は **parse error**。Round 2+ で `handoff_state` に既登録の topic が再度 findings_table に含まれる場合も **parse error** (= subagent が exclusion を尊重していない)
2. **(B) 主張行には trigger 根拠列がある**: rationale 列に「別領域・別機能 AND 1 セッション超 AND 受け入れ条件検証破綻」3 条件への該当言及があるか。1 条件のみの (B) は **parse error** (= subagent が誤分類)
3. **subagent return に「無視」「観察のみ」「スコープ対象外」のキーワードを単独で含む行がない**: 文字列 grep で検出、ヒットしたら **parse error**。**検査範囲は上記 §セクションの定義 の roster に従う** (ここに再掲しない)。roster に無いセクション — とりわけ `## meta` の状態記録行 (`Codex 出力読み取り: 非起動 (理由: ...)` 等) は**対象外**である。記録義務を課した行が握り潰し検出に巻き込まれると、正しく申告するほど parse error になるため
4. **必須セクションが存在する** (空でもセクション自体は必須): `## findings_table` / `## ambiguous_judgments` の**いずれかが不在なら parse error**。**`## findings_table` をこの item に含めるのが要点** — 含めないと、セクションごと落とした return が「データ行 0 行」と同じ観測値になり、item 1 / 2 / 6 を空虚に通過して「(A)/(B)/(C) all 0 = 収束」→ LGTM summary 投稿まで静かに通る (不在が『違反ゼロ』と同じ観測値になる検査は false-green を生む)
5. **受け入れ条件の未達が findings に反映されている**: `## acceptance_criteria_status` に `×` / `partial` / 未実証の行があるなら、**その各行に対応する `(A)` finding が `## findings_table` に存在しなければ parse error**。
   **これが無いと「受け入れ条件が落ちているのに findings ゼロ」= 収束 → LGTM が通る** (Codex adversarial-review [high])。
   Step 2.2 は findings_table しか件数に数えないため、未達の受け入れ条件は (A) finding に変換されない限り
   Step 3.1 の収束判定から**構造的に見えない**。ゼロ件記法を整備したことで、この経路は
   「正しく見える return」として通りやすくなっている
6. **(A) 強優先方針違反検出**: `latent issue / CI failure / 隣接ファイル lint 違反 / 古い API 残存 / 古い doc 記述` 等の典型 (A) trigger を含む finding が (A) 以外 ((A)* / (B) / (C)) に分類されている場合は **parse error**
7. **`## meta` に `Codex 出力読み取り` 行がある** (#949): `成功` / `失敗 (理由: ...)` / `非起動 (理由: ...)` のいずれかで始まること。行の不在は **parse error**。**`失敗` と `非起動` はどちらも理由が必須**で、理由括弧を欠いたものは parse error (根拠は「読んだ」「読めなかった」「起動していない」を事後に区別できなくすることであり、この理屈は 2 分岐に等しく効く。片方だけを名指しすると、名指しされていない側が緩いと読める抜け道になる)。`非起動` の理由は `/review-pr` Step 5a §「起動記録 (該当時 / 不該当時とも必須)」の非対象行と同一内容でよい (**同 record の専用スロットは増やさず本行に畳む**)。畳んだ完成形の例:

   ```text
   - Codex 出力読み取り: 非起動 (理由: 条件1 touched 4 file / 210 lines・条件2 再発 root cause 1 件・条件3 core 変更対象ファイル 該当 0)
   ```

   > **理由の literal の正は prompt template 側 (Step 2.1 の `## meta` に置いた代表形) 1 箇所**で、
   > 上の行はそれを scenario 値で埋めた例にすぎない。**同じ literal の worked example を 2 箇所に持たない** —
   > 持つと片方だけ古くなる。
   >
   > **`非起動` の理由が下記のいずれかに当たったら parse error にする。**
   >
   > - `single root cause` を含む
   > - `non-L1-core` を含む
   > - `root cause` が出現するのに、その直前が `再発` **でない** (= 修飾語の無い裸の用法)
   >
   > 3 番目は「裸の」を判定可能な形に落としたもの。**単純な部分文字列一致で `root cause` を
   > 禁止すると、正の代表形が含む `条件2 再発 root cause <K> 件` 自身に当たって、
   > 指示どおり書いた return が parse error になる** (禁止語彙 gate は、正の literal に対して
   > 緑になること (positive fixture) と旧語彙に対して赤になること (negative fixture) の
   > 両方を確認してから置く)。禁止リストの正は本 3 行だけで、他所は名前で参照する
   > `/review-pr` は 3 条件を 1 つずつ実測値付きで書くことを要求しており、旧語彙は「どの条件が
   > どう不成立だったか」を事後に復元できない (= 監査不能な skip)。
   >
   > 上記の語彙検査を除けば **本 validation は構文検査** — 状態語で始まっているか、`失敗` / `非起動` に理由括弧があるか、の 2 点を見る。**理由の中身が十分に具体的かどうか (`(理由: 特になし)` のような空疎な理由) までは検査しない。** 意味の妥当性は Step 2.3 の Round summary で controller が目視する

**parse error 時の対処**:

- 1 度目: 主セッションが subagent に対して具体的に欠陥を伝えて再 dispatch (Agent tool 再実行)。具体例: 「Step 5b 表 5 行目の (B) は trigger 根拠が `スコープ外` のみで 3 条件 AND 不成立。(A) に再分類して return せよ」
- 2 度目: AskUserQuestion で user に「subagent が分類規約を満たさない findings を返している。手動でトリアージするか abort するか」を提示

#### Step 2.3 Round summary AskUserQuestion (1 round 1 回のみ)

Round N の集計表示 + AskUserQuestion 2 択。Round 開始時の主要 gate (例外: Step 2.5 (B) 3+ bulk Iron Law 2 gate / Step 2.7 timeout gate / ambiguous_judgments 拡張)。

提示内容:

````text
Round N findings:
- (A): <件数>
- (B): <件数>
- (C): <件数>
- 受け入れ条件 (Step 3): <全 ○ / partial あり / 全 ×>
- ambiguous_judgments: <件数> (詳細は別途展開)

選択:
- (i) proceed (本 round の findings を処理) (Recommended、ambiguous なし時)
- (ii) abort (loop 中断、現状で /create-task など手作業に切替)
````

`ambiguous_judgments` がある場合、追加 AskUserQuestion でユーザー判断を仰ぐ。1 AskUserQuestion call は最大 4 questions まで束ねられる仕様 (= AskUserQuestion tool 上限) を活用し、5 件以上は複数 call に分割。1 round あたりの AskUserQuestion 呼び出し総数は「Round summary 1 + ambiguous_judgments の必要分 + Step 2.5/2.7 の例外 gate」を上限とする。

##### AskUserQuestion 設計規約 (scope 拡大選択肢を出さない、#732 教訓)

subagent reviewer が「scope 外」(= (B) 起票 or (A) re-run 推奨) と判定した finding について、controller (主セッション) が AskUserQuestion を組み立てる際、**「本 PR 内修正 (scope 拡大)」を選択肢に追加しない**。subagent recommendation を**第一の選択肢 (Recommended)** に置き、subagent が挙げた選択肢のみ提示する。user が `Other` で明示提案するまで scope 拡大は出さない。

**Why**: PR #732 (#708 = bash + docs scope) で Round 2/3 ともに、subagent reviewer が「(A) re-run」または「(B) 新規 issue 起票」を recommended と判定したが、controller が AskUserQuestion に「本 PR 内修正」を選択肢として追加 → user が選択 → 本 PR 内 commit (`8eff1d2` / `ee77e37`) で scope 拡大が発生。両回とも user が「scope 拡大」を選んだが、それは controller が **そもそも選択肢として提示した**から。subagent recommended のみを提示していれば scope creep は発生しなかった。「Round 2 で 1 件本 PR 内修正した実績がある」を Round 3 で sweep に倒した根拠にしたのも、典型的な Red Flag 「ついで」合理化。

Iron Law 3 と CLAUDE.md plugin override 規約は「user の明示判断が最優先」だが、選択肢の提示自体が誘導である以上、user の選択を「user 判断」と扱って scope creep を正当化するのは責任転嫁。

**How to apply**:

1. subagent reviewer の recommendation を **第一の選択肢 (Recommended)** にする
2. ambiguous_judgments の処置は subagent が挙げた選択肢のみ提示。controller が独自に「本 PR 内修正」「scope 拡大」を**追加しない**
3. scope 拡大が本当に必要 (連続して同種 finding が出る等) と思ったら、user に AskUserQuestion で問う前に **`/scope-guard` skill** を呼び、scope 拡大の妥当性を独立判定する
4. user が `Other` 経由で「本 PR 内修正したい」と明示した場合のみ scope 拡大に倒す
5. 「Round N で同じ **sweep root cause** ((b)、`/review-pr` §「root cause の 2 用法」) を 1 件本 PR 内修正した」は Round N+1 で sweep の根拠に**ならない**。各 finding は独立に subagent recommended に従う

関連 PR: #732 (commit `8eff1d2`, `ee77e37` が scope creep 該当)。

`<N>` には PR 番号 ($ARGUMENTS) を埋める。`<handoff_state を箇条書き>` には Step 1 で初期化した `handoff_state` の内容 (空なら "(なし)") を埋める。

#### Step 2.4 (A) findings 修正

各 (A) に対し主セッションが:

1. 該当 path:line を Read で内容確認
2. Edit で修正
3. 変更 path に応じた local check (Iron Law 6 サブ条 = `docs/l2-workflow.md` §「PR 作成 path 別自動チェック」):
   - Python (`*.py`): `ruff check . && ruff format --check . && pyright --pythonpath "$(dirname "$(git rev-parse --git-common-dir)")/.venv/Scripts/python.exe" && pytest` (`--pythonpath` 省略は false-red、#974。macOS / Linux は `.venv/bin/python`)
   - GUI (`gui/src/**`, `gui/src-tauri/**`): `npm run lint && npm run typecheck && npm test && npm run build && cargo check`
   - Markdown (`docs/**.md`, `*.md`): `bash scripts/check-markdownlint.sh` (violation fix recipe は [`docs/markdownlint-guide.md`](../../../docs/markdownlint-guide.md) §typical fixes を参照、M10)
4. **1 round = 1 commit** で集約: 全 (A) を 1 つの commit にまとめる (round 単位の atomicity を確保、Round 別 SHA を summary コメントで参照しやすくするため)。message テンプレ: `fix(round-N): <要約> (Refs #<元 issue>)`。例外として、push 失敗で reset → 再 commit が必要な場合のみ複数 commit になる可能性を許容

> **M5 同 issue 過去 PR 警告の併走**: `/review-pr` Step 1.1 で同 issue 過去 merged PR が ≥1 件検出された場合、その警告は subagent の Step 5b 表冒頭に転記されて return される。controller (本 skill) は Step 2.2 parse 後の Step 2.3 Round summary 提示時に user に再度明示する (**再発 root cause** ((a)、`/review-pr` §「root cause の 2 用法」) の重点確認の促し。ここは過去 merged PR 単位の話で、Step 5c の sweep root cause ((b)) ではない)。

#### Step 2.5 (B) findings handoff (新規 issue 起票、限定例外パス)

> **(B) 起票は限定例外 (Iron Law 3 担保)**: 「指摘は原則すべて PR 内対応」(§1 (A) 強優先方針) に従い、ほとんどの finding は (A) で消化される。本 step に来るのは Step 2.2 validation を通過した「真に (B) trigger 3 条件 AND 該当」の finding のみ。スコープ単独・サイズ単独・受け入れ条件直結性単独で (B) 化された finding はここに到達しない (= validation で reject される)。scope-creep の受け皿は Iron Law 3 担保。
>
> **注 (C2 設計意図)**: 本 skill が dispatch する **subagent mode では §G.2.1 通り AND 3 条件** (`別領域・別機能` AND `1 セッション超の独立設計が必要` AND `本 PR 同梱で受け入れ条件検証が破綻`) で厳格判定する。**standalone `/review-pr` 単体使用時は OR 3 択** (`外部依存・側チケット調整が必要` 単独でも (B) trigger として有効) を許容する。この非対称は **意図的設計**: standalone は人間レビュアーが文脈判断するため柔軟性を持つ、subagent mode は機械処理のため parse error リスクを減らすべく厳格化している。

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

#### Step 2.6 (C) findings handoff (既存 issue 追記、Iron Law 3 担保)

1. 既存 issue へ `gh issue comment <既存 issue#> --body-file -` で方針記録 (HEREDOC、UTF-8 対策。`feedback_gh_command_ja_heredoc.md` 準拠):

   ```bash
   gh issue comment <既存 issue#> --body-file - <<'EOF'
   ## /iterate-review Round <N> 由来の追記

   PR #<PR#> をレビュー中に本 issue (#<既存 issue#>) と関連する課題を発見。
   
   - **finding**: <topic 50 字以内>
   - **本 PR スコープ判定**: (C) 既存 issue 追記 (重複起票回避)
   
   詳細は PR #<PR#> 内で議論。
   
   [<session-id>]
   EOF
   ```

2. `handoff_state` 追加 + PR body deferred block 更新 (Step 2.5 同様)

#### Step 2.7 Push + CI wait

- `git push origin <head-branch>`
- `gh pr checks $ARGUMENTS --watch` で CI 状態確定 (success / failure) を 15 分まで待機
- **CI green (success)**: 次 round へ進める
- **CI red (failure)**: 本 step では abort しない。次 round の `/review-pr` Step 4 が CI 失敗を findings に拾う前提 (`/review-pr` Step 4 「失敗あり: 失敗ジョブ名と概要を user に報告」を踏襲)。CI red が複数 round 連続で再発生する場合は §2.6 divergence 検知で打切り判定
- **timeout (15 分超)**: AskUserQuestion 3 択 (待ち続ける (timeout 30 分に延長して poll 継続) / CI 無視で次 round / abort)

実装ノート: `gh pr checks --watch` の timeout は CLI 側で直接制御できないため、以下のいずれかで wrap する:

- **Linux / macOS**: `timeout 900 gh pr checks ...`
- **Windows + Git Bash (coreutils 版 timeout 利用可能時)**: `timeout 900 gh pr checks ...` (Git Bash 環境で `which timeout` が `/usr/bin/timeout` 等を指すこと、Windows 標準の `timeout.exe` ではないことを確認)
- **PowerShell (Windows 標準)**: `Start-Job -ScriptBlock { gh pr checks $args[0] --watch } -ArgumentList <PR#> | Wait-Job -Timeout 900`

### Step 3: 収束 / 発散 / 打ち切り判定

#### Step 3.1 収束 (success path)

(A)/(B)/(C) all 0 **かつ `## acceptance_criteria_status` が全件実証済** → Step 4 (Final summary comment) へ。

> **findings 件数だけで収束を決めない** (Codex adversarial-review [high])。受け入れ条件に `×` / `partial` が
> 残ったまま findings がゼロなら、それは収束ではなく **Iron Law 1 の未達**である。Step 2.2 の
> validation item 5 が「未達の受け入れ条件は (A) finding として現れる」ことを強制するので、
> 正常な経路では両者は一致する。**一致しない return が来たら収束させず parse error として再 dispatch する。**

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
    → user に `gh pr close` (branch 維持、後続調査用に残す) を**提案** (skill は実行しない、Iron Law 4 担保)
    → /scope-guard で残課題を整理し sub-PR に分割
    → /create-task で必要なら子 issue を整備
    → 各 sub-PR を順次作成 → /iterate-review で個別収束
    → user 主導の workflow、本 skill は abort して引き継ぐ
- (ii) abort (state を残して手動介入)
    → /iterate-review は終了、PR / branch は現状維持
    → user が手動で残 finding を判断 (merge する / 修正続行 / scope-guard 等)
```

> **(iii) 残 (A) 別 issue 化選択肢の不採用**: 「残 (A) を別 issue 化して merge」は issue 数収束方針 と矛盾するため**選択肢から除外**。Round 5 まで来たということは PR スコープが大きすぎたか実装方針が不適切のため、PR 単位での再構成 (i) が筋。残 (A) を逃がし弁にしないことで「(A) 内消化」原則を機構的に担保する (Iron Law 3 担保)。
>
> **(ii) abort 選択後の運用**: user が手動で残 finding を判断する (merge する / 修正続行 / /scope-guard 等)。/iterate-review は終了し PR / branch は現状維持のため、user 主導の workflow に切り替わる。

### Step 4: Final summary comment

(A)/(B)/(C) all 0 で収束したら、1 PR コメントを投稿する。

#### 4.1 投稿前 user 承認

> Round 1 で 0 findings (即収束) でも summary 投稿は実施推奨。skip 選択肢 (iii) は loop 終了のみで、コメント未投稿の場合 PR の review-fix 履歴が残らない。受け入れ条件実証記録としての価値があるため (i) が Recommended。

AskUserQuestion 3 択:

- (i) 投稿する (Recommended)
- (ii) 微調整して投稿 (markdown を user に提示 → 修正 → 再承認)
- (iii) skip 投稿 (loop は終了、コメントは残さない)

#### 4.2 summary template

`````markdown
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
| 1 | <条件> | `path:line` / `test_name` / CI log | ○ |

## Final State

- CI: green (last commit `<SHA[:7]>`)
- 受け入れ条件: 全 ○
- (A) 残: 0 / (B) handoff: <#N1, #N2 or なし> / (C) handoff: <#M1 or なし>
- 並行 PR: <検出ゼロ / [#X handled]>
- base sync: <CLEAN / 取り込み済み>

## Codex 出力読み取り (#949)

(各 Round の subagent `## meta` から転記。全 Round 成功なら "全 Round 成功" の 1 行でよい。1 Round でも失敗 / 非起動があれば Round 番号付きで列挙する)

- Round <N>: <成功 / 失敗 (理由: <1 行>、stdout の範囲のみで triage) / 非起動 (理由)>

## Codex fallback notice (J-4 fix、C6 整合)

(Round 内で Codex review (`codex-companion.mjs review`) が fail し fallback で代替実行した場合は以下を必須記載。fallback ゼロなら "(なし)" を残す)

> **Codex fallback notice**: Round <N> で Codex CLI が <検出条件: rate.?limit / 429 / quota / auth / timeout 等> で fail したため、Claude Code (superpowers:requesting-code-review) で代替実行しました。
> Codex 側の review は次セッションで再試行を推奨します。
> stderr 要約: <stderr の先頭 200 字>

(Iron Law 5 整合、Idios が Codex review 済と誤認するリスク回避)

[<session-id>]
`````

#### 4.3 投稿コマンド (HEREDOC + `--body-file -`)

```bash
gh pr comment <PR#> --body-file - <<'EOF'
# /iterate-review Summary
...
EOF
```

inline `--body "..."` は日本語が UTF-8 破損するため禁止 (`feedback_gh_command_ja_heredoc.md`)。

#### 4.4 length 対策

Round 数 5 + findings 多数で極端に長くなる場合:

- `<details>` で Round 詳細を折り畳み
- topic 文字数制限 (30 / 50 字)

`<details>` 適用例:

```markdown
<details>
<summary>Round 1 詳細 (4 件)</summary>

| # | Finding | Class | Resolution |
|---|---|---|---|
| 1 | ... | (A) | ... |

</details>
```

### Step 5: 次の handoff

「LGTM 候補です。`gh pr merge $ARGUMENTS --squash` で merge してください。マージ後は `/close-issue <issue#>` で実測再検証してから手動クローズしてください」を user に提示。

本 skill 内で merge / close は実行しない (Iron Law 4 + 5 担保)。

## 環境制約・フォールバック

- **§A 孤立 PR (issue 紐付けなし)**: `/review-pr` §A を継承。subagent prompt に「孤立 PR fallback 適用」と明記
- **§B `/enforce-acceptance-criteria` 実行不可**: subagent 側で fallback、本 skill は subagent 結果に従う
- **session crash mid-loop**: state は会話 + PR body deferred block。再 invoke で deferred block + 残 commit から推論して継続可能 (PR body は永続)

## Red Flags (本 skill 固有、Iron Law Red Flags と呼応)

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

## 呼び出し例

```text
/iterate-review 443
```

ユーザーが PR 番号を指定して呼び出す、または PR 作成セッションが skill として自走呼出する。
