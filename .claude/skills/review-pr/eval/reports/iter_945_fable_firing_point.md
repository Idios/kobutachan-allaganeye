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

| Scenario | 成否 | accuracy (raw) | tool_uses | duration | retries | 新規 unclear (raw) | うち defect-class |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F-1 | o | 5/5 | 4 | 148.1s | 0 | 2 | **0** |
| F-2 | o | 5/5 | 3 | 129.0s | 0 | 1 | **0** |

**iteration 2 は clear** (#945 scope 内の defect-class ゼロ)。2 consecutive clears
(iteration 1 + 2) を一旦達成したが、この後 Idios 裁定で Step 5.0 を修正したため
**収束判定はリセットし iteration 3 以降でやり直す** (収束が検証した artifact と
ship する artifact をズラさないため)。

### 構造化 reflection (iteration 2)

**F-1 #4 / F-2 #4 — 帰属: 隣接既存節 → Idios 裁定により (A) PR 内修正へ**

Step 5.0 の非対称は **iteration 1 / 2 で計 4 executor が独立に指摘**した。
さらに重要なのは、4 人が同じ doc-only PR に対して **4 通りの扱いをした**という事実:

| executor | Step 5.0 の扱い |
| --- | --- |
| iter1 F-1 | 起動しないと判断 (除外根拠を自力で作文) |
| iter1 F-2 | 「無条件起動」と読み、Step 5 本文へ独自 1 文で記録 |
| iter2 F-1 | 「skip する明示根拠が無い」ので起動、記録行を自力で新設 |
| iter2 F-2 | 起動、ただし書式発明を避けて既存の Step 5b 統合経路のみに記録 |

**これが非対称の実コスト。** 文体の揺れではなく、起動するか否かの判断自体が割れている。

**F-1 #5 — 帰属: 隣接既存節 (対応しない、Idios 判断待ち)**

- Issue: 「root cause」が skill 内で 2 つの異なるスコープで使われている
  (Step 1.1 M5 = **過去 merged PR の件数** / Step 5c = **diff 内の root cause 種別数**)。
  相互参照も書き分けも無く、Codex trigger 判定時に混同しうる
- General Fix Rule: 同一 skill 内で同じ用語を異なるスコープで使う場合は別名に分ける

---

## Iteration 3 (Step 5.0 修正後)

### Changes

Idios 裁定により Step 5.0 を (A) PR 内修正:

- **起動条件**: code file を 1 つでも touch する PR で起動 / doc-only では非起動
- **起動記録**: `実施` / `非実施` の両分岐に定型を与え、Step 6 の 1 行記録集約 slot にも追加

**この修正が満たす判定文言 (適用前に明示)**: F-1/F-2 要件 2「skill が定義する全レビュアーに
ついて起動有無の 1 行記録がある」と、F-2 要件 5「skill が定義していない記録書式を発明しない」。

### 実行結果

| Scenario | 成否 | accuracy (raw) | tool_uses | duration | retries | 新規 unclear (raw) | うち defect-class |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F-1 | o | 5/5 | 3 | 101.5s | 0 | 1 | **0** (harness) |
| F-2 | o | 5/5 | 3 | 118.2s | 0 | 1 | **0** (隣接既存節) |

**4 通りに割れていた Step 5.0 の扱いが 1 つに収束した**:

- F-1 (doc-only): `code quality subagent 起動: 非実施 (理由: doc-only PR、code file 変更ゼロ)`
- F-2 (code PR): `code quality subagent 起動: 実施 (finding N 件 → Step 5b 表へ統合)`

両者とも skill 定義の書式をそのまま使い、**独自書式の発明はゼロ**。

### 構造化 reflection (iteration 3)

**F-1 #6 — 帰属: harness (iteration 4 で解消)**: 架空 PR に対する dry-run なので
N/M/K の実数を持てない。「判断 + 書式提示までが成果物の上限」とシナリオ側で明示すべき、
という指摘。iteration 4 の prompt に dry-run 明示を追加した (難易度低下ではなく設問の欠落補完)。

**F-2 #5 — 帰属: 隣接既存節 (対応しない、Idios 判断待ち)**

- Issue: 「L1 core ロジック」の定義が skill 内 2 箇所で不一致。Step 5a の Codex 起動条件は
  抽象語 (`L1 (CLI / detector / GPU)`)、Codex fallback の重要 PR 判定は具体ファイル列挙
  (`detector.py` / `gpu_detector.py` / `audio/*.py` / `video/detector.py`)。境界ファイル
  (`video/capture_region.py` 等) で判定が割れうる
- General Fix Rule: 同一概念を複数箇所で参照する規約は、**具体ファイルリストを 1 箇所に正として
  定義**し他はリンクにする。`CLAUDE.md` 自身の「検出力は具体列挙にのみ宿る」を
  **レビュアー起動条件の記述自体にも適用する**
- 帰属判断: 本 PR が触っていない既存節。#945 の scope 外

(収束判定: **1 consecutive clear** / 打ち切りまで 1 round)

---

## Iteration 4 (convergence 2/2)

### Changes

**skill / doc の変更なし** (iteration 3 の clear を確定させるため対象テキストを固定)。
harness のみ: F-1 #6 に対応して prompt に dry-run 前提を明示。

### 実行結果

| Scenario | 成否 | accuracy (raw) | tool_uses | duration | retries | 新規 unclear (raw) | うち defect-class |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F-1 | o | 5/5 | 3 | 80.7s | 0 | 1 | **0** (隣接既存節 / harness) |
| F-2 | o | 5/5 | 3 | 87.1s | 0 | 1 | **0** (tool 制約) |

**iteration 4 は clear。iteration 3 + 4 で 2 consecutive clears を達成。**

F-1 (doc-only) / F-2 (code PR) とも 4 行ないし 5 行の記録 slot をすべて skill 定義の書式で埋め、
**独自書式の発明ゼロ**。duration も 148s / 129s → 81s / 87s と短縮した。

### 構造化 reflection (iteration 4、すべて非 defect)

**F-1 #7 — 帰属: 隣接既存節 + harness (対応しない)**

- Issue: `CLAUDE.md` §「Fable と Codex の棲み分け」の「invariant / 不可逆操作に関わる spec は
  **両方**にかける」は**内容依存で機械判定できない**のに対し、skill の Codex 起動条件は
  数値・カテゴリで機械判定可能。粒度の違う 2 基準が同一トピックに重なっている
- executor の処理は適切: 機械 trigger の判定を採りつつ、内容依存側を「未確認」として明示し、
  **どちらかに黙って倒さなかった**
- General Fix Rule: advisory な原則 (内容依存) と skill の明示 trigger (機械的) が重なる場合、
  判定材料が無いなら機械 trigger をデフォルト採用し、内容依存側は「未確定・要確認」と明示する

**F-2 #6 — 帰属: tool 制約 (skill の欠陥ではない)**

- Issue: `review-pr/SKILL.md` が 787 行あり Read 1 回で truncate される
- General Fix Rule: truncation 警告が出たら必ず offset 付きで次ページを読んでから結論を出す
  (今回 Step 6 テンプレート本体が後半にあり、前半だけで判断すると**書式を自作するリスク**があった)
- 本 skill が長大であること自体は #945 の scope 外

---

## 収束サマリ (#945)

| iteration | 対象テキスト | defect-class | 判定 |
| --- | --- | --- | --- |
| 0 | 改修**前** | 出所ラベル / 記録書式を**両方発明** | **red baseline** |
| 1 | +Fable 発火点 | 0 | clear (ただし後で reset) |
| 2 | 同上 | 0 | clear (ただし後で reset) |
| 3 | +Step 5.0 対称化 | 0 | **clear 1/2** |
| 4 | 変更なし | 0 | **clear 2/2** |

> **iteration 2 の時点で 2 consecutive clears に到達していたが、その後 Idios 裁定で
> Step 5.0 を修正したため収束判定をリセットし、修正後のテキストで取り直した。**
> 収束が検証した artifact と ship する artifact をズラさないための措置
> (#949 の EPT でも同じ判断をしている)。

**本 EPT が捕まえた最大の欠陥**: Step 5.0 の記録義務・起動条件の欠落。
**4 executor が同じ doc-only PR に対し 4 通りの扱い**をしていた (起動判断自体が割れていた)。
これは #945 の当初 scope 外だったが、Idios 裁定で (A) PR 内修正とした。

## Iteration 5 (Codex [medium] 修正の検証、境界 scenario)

### Changes

Step 5.0 の gate を**肯定形 → 否定形**へ反転 (非起動は「変更ファイルがすべて `docs/**` または
`*.md`」の 1 条件のみ)。記録定型の理由文言も同条件へ揃えた。

### 実行結果

| Scenario | 成否 | accuracy (raw) | tool_uses | duration | retries | 新規 unclear (raw) | うち defect-class |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **F-3 (境界: workflow + constraints.txt のみ)** | **o** | **4/4** | 3 | 80.8s | 0 | 1 | **0** |

**修正が効いていることの直接の証拠**: executor は code quality subagent を**起動する**と判断し、
その理由として

> 「`.github/workflows/ci.yml` / `constraints.txt` が `docs/**` でも `*.md` でもない → 非起動条件
> 不成立 → 起動」「**『yml/constraints.txt はソースコードか』という自己解釈の trap は踏んでいない**。
> skill 自身が『肯定形にすると解釈で割れる』と警告している箇所を明示的に回避した」

と述べた。**肯定形のままなら silent skip しえた種別が、否定形で確実に起動側へ倒れた。**

### 構造化 reflection (iteration 5)

**F-3 #1 — 帰属: 改修対象 (#982 由来、非 defect、Idios 判断待ち)**

- Issue: Step 6 の「1 行記録」集約節が **reviewer 起動記録** (code quality / Fable / Codex) と
  **構造チェック記録** (並行 PR 確認 / 外部依存規約 / パス契約) を同じ節に並記しており、
  「specialised reviewer とは何か」が skill 内で定義されていない
- executor は自力で正しく切り分けた (成果物は正しい)
- General Fix Rule: 「reviewer (外部 / subagent への委譲)」と「structural check (skill 内ロジックの
  該当性判定)」を語彙・見出しレベルで区別する
- 帰属: 集約節は #982 で新設したもの。**非 defect** なので本 PR では触らず候補に残す

---

## 本 PR の scope (Phase 1) と繰り越し (Phase 2)

**#945 の作業項目 5 件のうち 2 件は本 PR に含まれない。** 対象ファイルを open PR #978 が
触っており、先に触ると衝突するため (Idios 裁定で stacked PR + Phase 分割を選択):

| 作業項目 | 本 PR |
| --- | --- |
| 1. `/release` Step 0a-2 の新設 (`.claude/skills/release/SKILL.md`) | **Phase 2** (#978 と衝突) |
| 2. 非起動時の 1 行記録 | Phase 1 ✓ |
| 3. `/review-pr` の起動条件 | Phase 1 ✓ |
| 4. `allaganeye-` prefix 改名 | Phase 1 ✓ |
| 5. Self-Test Report の Fable 欄 (`.github/pull_request_template.md`) + red 実証 | **Phase 2** (#978 と衝突) |

したがって **#945 の受け入れ条件のうち「`/release` Step 0a-2 の数値記入 required」と
「Self-Test Report の Fable 欄 + `validate-checklist` red 実証」の 2 件は本 PR では未達**。
PR #978 のマージ後に rebase して追補する。

> **Codex adversarial-review [high] が同じ点を指摘した** (「release firing point が未実装で、
> 受け入れ条件は `allaganeye-fable-consult` が `release` と `review-pr` の**両方**で hit する
> ことを求めている」)。Codex の recommendation は「実装するか、scope を明示的に revise するか」の
> 2 択で、**本 PR は後者を採る**。Idios 裁定に基づく分割であり見落としではない。

## Codex adversarial-review (Pre-flight Step 5)

- job: `review-mt10dn6k-f3co4f` / Verdict: **needs-attention (No-ship)** / findings 2 件
- **[medium] 対応済み (A)**: Step 5.0 の gate が「code file を touch したか」という**肯定形の
  抽象語**で、`.github/workflows/*.yml` / `pyproject.toml` / `constraints.txt` / `*.ps1` /
  lockfile が解釈で割れ、**従来無条件だった code quality review が silent に落ちる**経路が
  あった。**否定形へ反転** (非起動は「変更ファイルがすべて `docs/**` または `*.md`」の 1 条件のみ)。
  判断に迷う種別はすべて起動側に倒れる
- **[high] scope 明示で対応**: 上記 §「本 PR の scope」のとおり

> **この [medium] は本 EPT の scenario 設計の穴でもあった。** F-1 (doc-only) と F-2 (通常 code PR) の
> **両端しか見ておらず、その間の種別 (workflow / config / lockfile) を 1 つも covered して
> いなかった**。scenario F-3 を追加して境界を塞いだ。
> **教訓: gate を新設したら「明確に該当」「明確に非該当」だけでなく「境界」の scenario を置く。**

## Idios 判断待ちの候補 (本 PR では実装しない)

いずれも本 PR が触っていない既存節。#945 の scope 外:

1. **「root cause」の用語衝突** — Step 1.1 M5 は**過去 merged PR の件数**、Step 5c は
   **diff 内の root cause 種別数**。相互参照も書き分けも無い (iteration 2 F-1 指摘)
2. **「L1 core」の定義不一致** — Step 5a は抽象語 (`L1 (CLI / detector / GPU)`)、
   Codex fallback の重要 PR 判定は具体ファイル列挙。境界ファイル
   (`video/capture_region.py` 等) で判定が割れうる。`CLAUDE.md` 自身の
   「検出力は具体列挙にのみ宿る」を**レビュアー起動条件の記述自体にも適用すべき**
   (iteration 3 F-2 指摘)
3. **advisory 原則と機械 trigger の粒度差** — `CLAUDE.md` の「invariant/不可逆操作の spec は
   Fable と Codex の両方にかける」が内容依存で、skill の機械 trigger と重なっている
   (iteration 4 F-1 指摘)
