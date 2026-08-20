# EPT レポート: #949 Codex 出力の読み取り (review-pr / iterate-review 横断)

対象 skill は 2 本 (`/review-pr` Step 5a / `/iterate-review` Step 2.1・2.2・Step 4) だが、
同一テーマの 1 改修なので本ファイルに集約する。シナリオ定義は
[`../scenario_g_codex_output_read.md`](../scenario_g_codex_output_read.md) (G-1 / G-2) と
[`../../../iterate-review/eval/scenario_g_codex_output_read.md`](../../../iterate-review/eval/scenario_g_codex_output_read.md) (G-3)。

## 測定設計上の前提 (この harness が測れないもの)

**要件チェックリストは executor に渡るので「指示が書いてあるか」は測れない。**
チェックリストが成果物の性質を述べた時点で、executor は指示に無くても自力で
その性質を満たしにいく。実際 iteration 0 (改修**前**テキスト) でも全 executor が
self-report accuracy 5/5 を返した。**したがって accuracy は本 harness では判別力を持たない。**

判定は以下で行う:

- **primary (qualitative)**: unclear points / discretionary fill-ins の内容。
  「doc に書かれていないので自力で埋めた / ソースを逆引きした」が出れば red
- **auxiliary (quantitative)**: `tool_uses`。skill 内に recipe が無いと executor は
  外部 (plugin ソース等) を descend するので step 数が膨らむ

accuracy 数値は raw として記録するが、収束判定には使わない。

## 帰属の分類

unclear point は 3 つに帰属を分ける。**改修の効果測定に使えるのは (1) だけ。**

1. **改修対象**: 本 PR が新設した節が扱うべき事項
2. **harness**: シナリオ / チェックリストの書き方に由来するもの
3. **隣接既存節**: 本 PR が触っていない既存記述の問題 (別途 triage)

---

## Iteration 0 (baseline / red 実証)

### 対象テキスト

`develop-0.3.1` HEAD (`35a1da6`) の以下 3 ファイル。**本 PR の改修を含まない**:

- `.claude/skills/review-pr/SKILL.md`
- `.claude/skills/iterate-review/SKILL.md`
- `docs/l2-workflow.md`

### 実行結果 (per scenario)

| Scenario | 成否 (self-report) | accuracy (raw、判別力なし) | tool_uses | duration | retries | Weak phase |
| --- | --- | --- | --- | --- | --- | --- |
| G-1 (review-pr 中央値) | o | 6/6 | **18** | 295.4s | 0 | Trace all OK |
| G-2 (review-pr edge: 読み取り失敗) | o | 5/5 | **12** | 137.5s | 0 | Trace all OK |
| G-3 (iterate-review edge: 非起動申告) | o | 5/5 | 6 | 151.2s | 0 | Trace all OK |

> **accuracy は全 scenario で満点。改修前テキストなのに満点である**という事実が、
> 前提節で述べた「チェックリストは判別力を持たない」の実証そのもの。
> 判別力があったのは `tool_uses` の skew (G-1 18 / G-2 12 vs G-3 6) と unclear points の中身。
> 18 / 12 は「skill 内に recipe が無いので plugin ソースを descend した」step。

### 構造化 reflection (iteration 0 で surfaced)

**G-1 #1 — 帰属: 改修対象 (red の本体)**

- Issue: `l2-workflow.md` §Codex fallback の擬似コードが `integrate_findings(result.stdout)` と書いており、
  **「stdout を一次ソースにするな」という要件と正面から矛盾する記述が正の doc 内に存在する**
- Cause: doc が `codex-companion.mjs` の job 永続化アーキテクチャを実装まで読まずに書かれ、
  「Bash 実行 → stdout をそのまま使う」という単純化されたメンタルモデルのまま固定化されている
- General Fix Rule: 外部 CLI をラップする手順を doc に書くときは、対象 script の実装を最低 1 度読み
  「stdout は完全か / 結果は永続化されるか」を確認してから擬似コードを固定する

**G-1 #2 — 帰属: 改修対象**

- Issue: usage 文言と `l2-workflow.md` は `--background` で非同期化可と断定するが、v1.0.4 実装
  (`handleReviewCommand`) は `options.background` を全く参照せず常に foreground 完走する
- Cause: plugin の usage 表記と実装分岐が世代ずれしており、doc は usage をそのまま転記していた
- General Fix Rule: 外部 plugin の CLI flag を doc に書くときは `--help` 文字列でなく
  `if (options.<flag>)` の実装分岐まで grep して「本当にそのフラグが効くか」を確認する

**G-1 #3 — 帰属: 改修対象 (iteration 1 で修正)**

- Issue: skill は「finding を Step 5b に統合せよ」とだけ書き、**複数 job が並走しうる場合の
  一意な参照方法 (job id) に一切触れていない**。同一 workspace で hook / gate / rescue からも
  同じ CLI が起動されうる
- Cause: 「1 回の呼び出し = 1 個の結果」という単純シナリオしか想定されていない
- General Fix Rule: 同じ CLI が複数の起動経路を持つ場合、手順書には**結果を一意に特定する
  識別子 (id) を明示的に運ぶ**設計原則を必ず書く。「最新のものを使う」という暗黙前提は
  並走環境で壊れる

> **この 3 件目は iteration 0 の commit `7fd4920` が作り込んだ欠陥**でもある。
> 当時の §「Codex 出力の読み取り」は「job-id は省略する」と**明示的に指示していた**。
> 実装 (`lib/job-control.mjs` の `matchJobReference`) を再確認したところ、reference 省略時は
> `filtered[0]` = **現 session の最新完了 job を `jobClass` を見ずに返す**。同 session で
> `/codex:rescue` (CLAUDE.md §Codex 運用 C4 で許可されている) や `task` が後から完了すると、
> **review でない job の出力を review の finding として取り込む**。実測で確認済み。

**G-2 #1 — 帰属: 改修対象**

- Issue: 「Codex review 本体は成功したが、保存済み全文の回収コマンドが失敗した」ケースに対応する
  記録テンプレートが `l2-workflow.md` / `review-pr/SKILL.md` のどちらにも存在しない。存在するのは
  「起動条件不該当」用と「Codex CLI 自体が fail」用の 2 つだけ
- Cause: fallback 検出条件表・擬似コードが一貫して「review 起動コマンド」の exit code だけを
  分岐条件にしており、companion script の副次コマンド (結果取得) の失敗モードを設計に含めていない
- General Fix Rule: 外部 CLI ラッパーを exit code ベースで分岐させる規約を書くときは、
  「どのサブコマンドの exit code が判定対象か」を明示し、副次コマンドが独立に失敗しうるなら
  その専用テンプレートも用意する

**G-2 #2 — 帰属: 改修対象 (red の本体)**

- Issue: authoritative full review text を取得するサブコマンド名 (`result`) が対象 doc の
  どこにも明記されておらず、**エラー文言を plugin ソース (`lib/job-control.mjs`) から
  逆引きして初めて特定できた**
- Cause: doc は起動コマンドだけを詳述し、実行後に完全な出力を取り出す手段に一切言及がない
- General Fix Rule: skill/doc が外部ツールの「起動」だけでなく「結果取得」を前提とする運用を
  想定するなら、そのサブコマンド名と代表的な失敗文言も doc に明記する

> この 2 件が **改修前テキストの red baseline**。`tool_uses = 12` (G-3 の 2 倍) は
> 「skill 内に recipe が無く外部を descend した」ことの定量的裏付け。

**G-3 #1 — 帰属: 隣接既存節**

- Issue: Step 2.2 validation item 3 (「無視」「観察のみ」「スコープ対象外」単独行の grep) だけが
  item 1/2/4/5 と違い `findings_table` へのスコープ限定を持たず、`## meta` の正当な状態記録行まで
  false parse error に巻き込みうる
- Cause: item 3 の主語が "subagent return" と広いまま
- General Fix Rule: 特定フィールドの言い逃れ表現を封じる検証規則は、その対象フィールドに
  grep のスコープを明示的に限定して書く

**G-3 #2 — 帰属: 改修対象**

- Issue: `/review-pr` Step 5a の H-4 記録義務を `/iterate-review` が継承する設計なのに、
  Step 4 Final summary の固定 template に対応スロットが無い。**記録は 1 回生成された直後の
  境界で構造的に失われる**
- Cause: 義務を課した上流 step と、集約する下流 template が同期していない
- General Fix Rule: 上流 step が「必ず記録せよ」と義務付けたレコード種別は、集約先の
  summary/report template にも対応する明示スロットを用意する

### Discretionary fill-ins (iteration 0)

- G-1: `status --json` → `result <job-id>` の **2 段階手順を自力で設計した**
  (`codex-companion.mjs` / `lib/job-control.mjs` / `lib/state.mjs` を読んで)。
  Step 5b 出所列の `codex:review (job <id>, plugin v<version>)` 記法も独自追加
- G-2: 「companion CLI 経由で全文取得」を `result` サブコマンドと**自力で特定した**
  (根拠はエラー文言の一致のみ)。記録行の挿入位置も既存慣習から類推
- G-3: 「Codex 出力を読んだか」を `Codex review 起動` / `Codex review 出力読了` の
  **2 行に自力で分割**。要件 3-5 の説明先として `ambiguous_judgments` を**自力で選択**
  (固定 5 セクションに置き場が無いため)

### Ledger updates

- Added: **stdout-as-primary-source** (G-1 #1) — 永続化される外部 CLI 出力を stdout 前提で書く
- Added: **usage-string-transcribed-without-implementation-check** (G-1 #2) — `--help` 文言を
  実装分岐を確認せず doc へ転記する
- Added: **latest-instead-of-identity** (G-1 #3) — 並走しうる対象を「最新」で選び一意識別子で
  選ばない。memory `feedback_destructive_predicate_needs_identity` と同一クラス
- Added: **undocumented-companion-subcommand** (G-2 #2) — 起動コマンドのみ文書化し
  結果取得コマンドを文書化しない
- Added: **obligation-without-aggregation-slot** (G-3 #2) — 記録義務を課すが集約先 template に
  スロットが無い
- Added: **unscoped-keyword-grep** (G-3 #1、帰属は隣接既存節)

### 適用した修正 (commit `7fd4920`)

1. `docs/l2-workflow.md` §Step 5 に「Codex 出力の読み取り」を新設 (`result` の実コマンド /
   cwd 制約 / 失敗時の 1 行記録義務 / 耐久性の限界)
2. `/review-pr` Step 5a に読み取り step + 「読み取り失敗」専用の 1 行テンプレート
3. `/iterate-review` prompt template item 8 + `## meta` の申告行 + Step 2.2 validation 6 +
   Step 4 Final summary の `## Codex 出力読み取り` 節 (= 集約スロット)

ledger の **stdout-as-primary-source / undocumented-companion-subcommand /
obligation-without-aggregation-slot** はこれで解消。**latest-instead-of-identity は未解消**
(むしろ「job-id は省略する」と明示して悪化させた) ため iteration 1 の theme とする。

(収束判定: 0 consecutive clears / 打ち切りまで 2 round)

---

## Iteration 1

### Changes (diff from iteration 0)

**theme: 読み取り対象の job を一意に特定する** (ledger pattern `latest-instead-of-identity`)

- `docs/l2-workflow.md` §「Codex 出力の読み取り」: 「job-id は省略する」を撤回し、
  `status --json` で `jobClass == "review"` の最新 id を採ってから `result <job-id>` を叩く
  2 段階へ変更。省略が壊れる条件 (`matchJobReference` が `jobClass` を見ない / 同 session の
  rescue・task が後から完了する) を明記
- 同 §Codex fallback 擬似コードも 2 段階へ追随
- `/review-pr` Step 5a の手順を同じ 2 段階へ変更
- (bundled micro-fix、G-3 #1 由来) `/iterate-review` Step 2.2 item 3 の grep スコープを
  `findings_table` / `ambiguous_judgments` に限定。**iteration 0 で `## meta` に必須申告行を
  足したため、正しく申告するほど false parse error になる経路が新設されていた**

**この修正が満たす判定文言 (適用前に明示)**: G-1 要件 4「job id を渡すか省略するかの決定と理由」と、
G-1 #3 の General Fix Rule「結果を一意に特定する識別子を明示的に運ぶ」。

### 実測による裏取り (推論で直さない)

| 主張 | 実測 |
| --- | --- |
| reference 省略時は `jobClass` を見ずに最新完了 job を返す | `lib/job-control.mjs:191-195` `matchJobReference` が `filtered[0]` を返す。predicate は status のみ判定 |
| `status --json` が id と種別を出す | 実行して `latestFinished` = `{id, kind:"adversarial-review", jobClass:"review", status:"completed"}` を確認 |
| `result <job-id>` が全文を print する | 実行して rendered 全文 + Codex session ID + resume コマンドを確認 |
| 読み取り失敗は exit 非ゼロ + 明確な文言 | `result` を対象なしで実行し exit 1 + `No finished Codex jobs found for this repository yet.` を確認 |

### 実行結果 (per scenario)

| Scenario | 成否 (self-report) | accuracy (raw) | tool_uses | duration | retries | Weak phase |
| --- | --- | --- | --- | --- | --- | --- |
| G-1 | o | 6/6 | 6 (**iter0 比 -67%**) | 68.2s (**-77%**) | 0 | Trace all OK |
| G-2 | o | 5/5 | 2 (**-83%**) | 80.3s (**-41%**) | 0 | Trace all OK |
| G-3 | o | 5/5 | 6 (±0) | 193.8s (+28%) | 0 | Trace all OK |

> **`tool_uses` の崩れ方が本 iteration の主要な signal。** iteration 0 で G-1 / G-2 が
> 18 / 12 step を費やしていたのは plugin ソースを descend していたからで、
> 手順が skill 内に入った iteration 1 では 6 / 2 に落ちた。3 scenario の skew も解消
> (18/12/6 → 6/2/6)。accuracy は相変わらず全部満点で判別力なし。

### 構造化 reflection (iteration 1 で新規に surfaced)

**G-1 #4 — 帰属: harness / 構造 (対応不要と判断)**

- Issue: skill (簡潔) と l2-workflow (詳細) の 2 ファイルにまたがるため、根拠まで知るには両方読む必要がある
- Cause: 「skill は簡潔、doc が詳細」は本 project の意図的な分担
- General Fix Rule: 分散する場合、簡潔側に「詳細側のどのレベルの情報が要るか」を一言添える
- **判断**: 既存の doc 分担方針そのものへの指摘であり、本 PR の scope 外。対応しない

**G-2 #1 — 帰属: harness (iteration 2 で修正)**

- Issue: シナリオが「2 本目の command が exit 1」とだけ書き、`status` 段と `result` 段の
  どちらで落ちたかを特定していない
- Cause: iteration 1 で読み取りが 2 段階になったのに、シナリオが 1 段階前提のまま圧縮されていた
- General Fix Rule: 複数ステップの CLI プロトコルを 1 文に圧縮したシナリオを与えられたら、
  欠落した中間ステップを推測で補って事実として書かない
- **判断**: skill ではなく harness の欠陥。scenario G-2 を修正した (難易度低下ではない)

**G-3 #1 — 帰属: 改修対象 (iteration 2 で修正)**

- Issue: Step 2.2 item 6 は理由必須を `失敗` だけ名指しし、`非起動` には要求していない。
  「名指しされていない分岐は緩い」と読める
- Cause: 共通の正当化理由 (事後に区別できない) を与えながら、parse error 条件は 1 分岐しか
  明文化していなかった
- General Fix Rule: 列挙型の状態値に共通の正当化理由を与える validation rule は、
  parse error 条件も分岐ごとに**対称に**明文化する

**G-3 #2 — 帰属: 改修対象 (iteration 2 で修正、ledger 再発)**

- Issue: `/review-pr` H-4 の「Codex review 起動: 非対象」記録に、`/iterate-review` の固定
  5 セクションに専用スロットが無い。executor は `## meta` に独自 bullet を生やした
- Cause: 委譲元 skill の記録義務カタログと、委譲先 skill の固定出力スキーマが非同期
- General Fix Rule: 呼び出し先 skill が新しい 1 行記録義務を追加したら、呼び出し元 skill の
  固定出力スキーマにも対応する named slot を同時に追加する

> **ledger 再発の分析**: `obligation-without-aggregation-slot` は iteration 0 で
> Added 済みだった。**なぜ既存 fix が再発を防げなかったか** — iteration 0 の fix は
> 「読み取り」の record にだけ slot を作り、**同じ Step 5a が課す姉妹義務 (H-4 の起動記録)**
> を見落としていた。1 件の義務に対して slot を 1 個作る対応では、同一 step が複数の義務を
> 課している場合に取りこぼす。iteration 2 では slot を増やす代わりに、
> `非起動` の理由へ H-4 record を畳む形にした (契約の面積を増やさない)

### Discretionary fill-ins (iteration 1 で新規)

- G-1: **成功時**の Step 6 記録行を自力で作文 (skill が定型を持つのは「非該当時」「失敗時」のみ)。
  iteration 0 でも同じ fill-in が出ており **2 回連続で再発**
- G-1: `status --json` の出力を jq で抜くか目視で採るかは未規定
- G-2: 読み取り失敗時に retry するか否かが未規定。記録行を表内に書くか本文に書くかも未規定
- G-3: `Codex review 起動` bullet を `## meta` に**自力で新設** (G-3 #2 と同根)

### Ledger updates

- Re-seen: **obligation-without-aggregation-slot** (初出 iter 0) — 既存 fix が防げなかった理由は
  「同一 step の姉妹義務を見落とし、義務 1 件につき slot 1 個で対応した」ため
- Added: **asymmetric-enumeration-rule** (G-3 #1) — 列挙型状態値の一部分岐だけに
  parse error 条件を明文化する
- Added: **template-only-for-the-failure-branch** (G-1 discretionary の再発) — 記録義務の
  定型を異常系にだけ用意し、正常系を実行者の作文に任せる

### 次の修正 (= iteration 2、commit `013ff30`)

1. `/review-pr` Step 5a: `成功` / `失敗` / `非起動` の**3 状態すべてに定型**を与える
2. `/iterate-review` Step 2.2 item 6: `失敗` と `非起動` の**両方で理由必須**に統一
3. `/iterate-review` prompt template item 8: H-4 の起動記録は slot を増やさず
   `非起動` の理由へ畳む旨を明記
4. (harness) scenario G-2 にどちらの段で落ちたかを明記

(収束判定: 0 consecutive clears / 打ち切りまで 2 round)

---

## Iteration 2

### Changes (diff from iteration 1)

**theme: 記録行の対称化** (ledger pattern `template-only-for-the-failure-branch` /
`asymmetric-enumeration-rule` / `obligation-without-aggregation-slot` 再発)

上記「次の修正」4 点。**この修正が満たす判定文言 (適用前に明示)**: G-1 要件 6 の
「出所の記録方法」を成功系にも与えること、および G-3 要件 2「非起動が理由付きで書かれている」を
skill 本文側の parse error 条件と一致させること。

### 実行結果 (per scenario)

| Scenario | 成否 (self-report) | accuracy (raw) | tool_uses | duration | retries | 新規 unclear |
| --- | --- | --- | --- | --- | --- | --- |
| G-1 | o | 6/6 | 8 | 114.4s | 0 | 1 件 (改修対象) |
| G-2 | o | 5/5 | 2 (±0) | 75.0s (-7%) | 0 | 1 件 (executor 自身が「doc の欠落ではない」と分類) |
| G-3 | o | 5/5 | 6 (±0) | 126.5s (-35%) | 0 | **0 件** |

### 構造化 reflection (iteration 2 で新規に surfaced)

**G-1 #5 — 帰属: 改修対象 (iteration 3 で修正、3 回連続の再発)**

- Issue: §「起動条件不該当時の明示記録」は**非起動時の定型しか持たず**、起動した (trigger 該当) 場合に
  Step 6 へ書く「起動: 対象」行の文言が doc に存在しない
- Cause: 節タイトルが「不該当時」に限定されており、該当ケースの記録要否・文言が明文化されていない
- General Fix Rule: 「非該当ケースの明示記録」を義務化する節を書くときは、対になる「該当ケース」の
  記録要否・文言も同節内で明示する

**G-2 #2 — 帰属: 改修対象 (軽微、iteration 3 で修正)**

- Issue: `result <job-id>` 失敗時に再試行・原因診断をすべきかが未規定
- Cause: §「Codex 出力の読み取り」は失敗時の**対処**は規定するが、**原因診断の要否**は規定していない。
  executor 自身が「これは意図的な範囲限定であり doc の欠落ではない」と分類している
- General Fix Rule: 「読めなかったら記録して進む」系の規約は、記録義務とは別に
  「原因診断は必須か任意か」を明示しておくと、実行者が余計な再試行ループに入るのを防げる

**G-3 — 新規 unclear point なし。** iteration 2 で入れた「slot を増やさず `非起動` の理由へ畳む」
設計をそのまま実行し、Step 2.2 item 3 のスコープ限定も正しく引用した。

### Ledger updates

- Re-seen (**3 回目**): **template-only-for-the-failure-branch** (iter 0 / 1 / 2 で連続)。
  **なぜ既存 fix が防げなかったか** — iteration 2 の fix は「読み取り」record の 3 分岐だけを
  対称化し、**姉妹 record である「起動」の分岐対称化を見落とした**。record ごとに個別対応して
  いる限り、次の record でまた同じことが起きる

> **whack-a-mole の停止判断**: 同一クラスが 3 iteration 連続で現れたので、個別 patch を止めて
> クラスごと閉じる (memory `feedback_adversarial_review_whackamole` の適用)。
> 根本要因を 1 行にすると **「記録義務の定型を異常系・非該当だけに用意してきたため、
> 正常系・該当のたびに実行者が文言を発明していた」**。iteration 3 では個別の穴を埋めるのではなく、
> **「記録義務は起こりうる状態すべてに定型を用意する」原則を節内に明記**して以後の記録義務追加にも
> 効かせる。発散 (divergence) 判定には該当しない — unclear point は毎回**減っており** (G-3 は 0)、
> 同一クラスの残骸が最後に 1 件残っていただけである

### 次の修正 (= iteration 3、commit `2a9693c`)

1. §「起動条件不該当時の明示記録」→ §「起動記録 (該当時 / 不該当時とも必須)」へ改題し、
   `対象` / `非対象` の**両方に定型**を置く
2. 同節に「記録義務は起こりうる状態すべてに定型を用意する」原則を明記 (クラスごと閉じる)
3. 読み取り失敗時の再試行・原因診断は**任意**と明記 (cwd 取り違えのみ 1 度やり直す)
4. 改題に伴う §「セクション名」grep sweep (旧名残骸 0 件を確認)
5. sweep 中に発見した取り残しを修正 — `iterate-review/SKILL.md:65` に iteration 0 の
   「job-id 省略」記述が残り、iteration 1 で撤回した指示と**矛盾していた**

(収束判定: 0 consecutive clears / 打ち切りまで 2 round)

---

## Iteration 3

### Changes (diff from iteration 2)

**theme: 記録義務の分岐網羅をクラスごと閉じる**。上記「次の修正」5 点。

**この修正が満たす判定文言 (適用前に明示)**: G-1 #5 の General Fix Rule
「対になる該当ケースの記録要否・文言も同節内で明示する」、および G-2 #2 の
「原因診断は必須か任意かを明示する」。

### 実行結果 (per scenario)

(iteration 3 の subagent 結果を以下に記録)
