# EPT レポート: #945 allaganeye-fable-consult の発火点

シナリオ定義は [`../scenario_h_fable_firing_point.md`](../scenario_h_fable_firing_point.md)。

判定基準・harness の限界は [`iter_949_codex_output_read.md`](iter_949_codex_output_read.md) §「測定設計上の前提」
と同一 (要件チェックリストは executor に渡るので accuracy は判別力を持たない。primary は
unclear points / discretionary fill-ins の内容、auxiliary は `tool_uses`)。
unclear point は **改修対象 / harness / 隣接既存節**に帰属を分ける。

---

## Iteration 0 (baseline / red 実証)

対象テキスト: `HEAD~1` の `.claude/skills/review-pr/SKILL.md` と `CLAUDE.md` (本 PR の改修を含まない)。

| Scenario | 成否 | accuracy (raw) | tool_uses | duration | retries |
| --- | --- | --- | --- | --- | --- |
| F-1 (発火する側) | o | 5/5 | 3 | 139.1s | 0 |

### red の中身 (accuracy は満点でも判別力は discretionary fill-ins にある)

executor は `fable-consult` を**起動する判断自体には到達した**。ただしその経路と成果物が問題:

- 根拠を `CLAUDE.md` §モデルルーティング から**輸入**した。executor 自身の言:
  「fable-consult は review-pr の手順から**一度も参照されず**、CLAUDE.md という別文書の
  cross-cutting policy として**孤立している**」
- **出所ラベルを発明した** — `出所 = subagent: fable-consult (doc quality)`
  (改修後の skill が定義するのは `出所 = fable:consult`)
- **Step 6 の記録行書式を発明した** — skill テンプレートに置き場が無いため独自に 2 行追加

> **これが #945 が言う「発火点が 1 つも存在しない」の実証**。skill を読んだだけでは
> 起動判断も書式も決まらず、実行者ごとに別々の label / 書式が生まれる。

### 構造化 reflection (iteration 0)

**F-1 #1 — 帰属: 改修対象 (本 PR で解消)**

- Issue: doc-only PR に対して doc/spec 品質を見る reviewer が SKILL.md 内に存在しない。
  Step 5.0 は code quality 固定、Step 5a の Codex trigger は file/line/L1-core という code 向け信号のみ
- General Fix Rule: PR の内容種別 (code / doc) ごとに reviewer を出し分ける skill は、
  各種別に「専用 reviewer 名 + 明示的な起動/非起動条件 + report の記録スロット」の 3 点セットを
  **skill 本体に**持たせる。別文書のポリシー表に置いたまま skill から参照しない構成は、
  実行者が探し当てられるかどうかに依存する

**F-1 #2 — 帰属: 改修対象 (本 PR で解消) + 隣接既存節 (未対応)**

- Issue: Step 6 の記録スロットが特定 reviewer にしか用意されていない
- General Fix Rule: 記録義務を 1 つの reviewer にだけ適用せず「reviewer 起動判断点」という
  抽象クラス全体に適用し、テンプレートも新規 reviewer 追加に耐える形にする

---

## Iteration 1

### Changes

`/review-pr` Step 5a に §「optional 俯瞰レビュー (allaganeye-fable-consult)」を新設
(2 trigger / 渡す観点 / `出所 = fable:consult` / 起動記録の両分岐定型 / N・M・K 数値必須)。
Step 6 の「1 行記録」集約 slot に Fable 行を追加。agent 改名 + CLAUDE.md 追随。

### 実行結果

| Scenario | 成否 | accuracy (raw) | tool_uses | duration | retries | 新規 unclear (raw) | うち defect-class |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F-1 (発火する側) | o | 5/5 | 3 | 108.0s | 0 | 1 | **0** |
| F-2 (発火しない側) | o | 5/5 | 3 | 154.2s | 0 | 1 | **0** |

**F-1**: 2 trigger の**両方**に該当すると正しく判定し起動。`出所 = fable:consult` を
skill 逐語で採用 (iteration 0 の発明が消えた)。N/M/K 必須も正しく引用。

**F-2**: Fable を**起動しないと正しく判定**し、理由を PR 固有の実測値
(3 file / 90 line / single root cause / non-L1-core) で記述。
要件 5 (書式を発明しない) に対し、**skill が定義していない slot を作らないよう明示的に回避**した
と自己申告している。**発火する側 / しない側の対がどちらも期待どおり動いた。**

### 構造化 reflection (iteration 1)

**F-1 #3 / F-2 #3 — 帰属: 隣接既存節 (本 PR では未対応、Idios 判断待ち)**

**2 executor が独立に同じ点を挙げた。**

- Issue: Step 5.0 (`superpowers:requesting-code-review` → `code-reviewer` subagent) には
  **起動記録義務も doc-only 時の適用除外も無い**。Step 5a の Fable / Codex が
  「明示 trigger + 該当/不該当とも記録必須」を持つのと**非対称**
- Cause: 記録義務の設計が「起動するかどうかが分岐する reviewer」にのみ適用され、
  「常時起動」の reviewer には及んでいない non-uniform な構造
- General Fix Rule: 複数の専門レビュアーを定義する skill は、常時起動 / 条件付き起動を問わず
  **全レビュアーに同一の起動記録スロット**を課す。分岐構造によって記録義務の有無を変えると、
  後から「記録漏れなのか、そもそも記録不要設計なのか」が追跡できない
- **帰属判断**: Step 5.0 は本 PR が触っていない**既存節**であり #945 の scope 外。
  ただし本 PR が同じ skill に「記録義務は分岐を網羅する」原則 (#949) を入れた直後なので、
  **この非対称は自分で入れた原則が condemn する形**になっている。Idios 判断待ちの候補として残す

> **iteration 1 は clear** (defect-class ゼロ)。唯一の指摘は隣接既存節への言及で、
> 2 scenario とも成果物は期待どおり。

(収束判定: **1 consecutive clear** / 打ち切りまで 1 round)

---

## Iteration 2 (convergence 2/2)

### Changes

**skill / doc の変更なし** (iteration 1 の clear を確定させるため対象テキストを固定)。

### 実行結果

(iteration 2 の subagent 結果を以下に記録)
