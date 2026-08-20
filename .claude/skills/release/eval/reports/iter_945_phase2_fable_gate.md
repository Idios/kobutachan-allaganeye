# EPT レポート: #945 Phase 2 (/release Step 0a-2 + Self-Test Fable 欄)

シナリオ定義は [`../scenario_a_fable_overview_gate.md`](../scenario_a_fable_overview_gate.md)。
判定基準 (defect-class = 成果物が変わったもの) と帰属分類は
[`../../review-pr/eval/reports/iter_945_fable_firing_point.md`](../../review-pr/eval/reports/iter_945_fable_firing_point.md)
と同一。

---

## Iteration 0 (baseline / red 実証)

対象テキスト: `HEAD~1` の `.claude/skills/release/SKILL.md` (Step 0a-2 を含まない)。

| Scenario | 成否 | accuracy (raw) | tool_uses | duration | retries |
| --- | --- | --- | --- | --- | --- |
| R-1 | **x (失敗)** | **2/5** | 2 | 167.0s | 0 |

### red の中身 — 今回は accuracy が判別力を持った

**[critical] 要件 2 が `x`** で判定 = 失敗。executor は改修前テキストを読んで
「この遷移点 (Step 0a 完了直後、Step 0b 着手前) にレビュワー起動の規定は**見つからなかった**」と
正しく結論し、`Codex` / `allaganeye-fable-consult` の双方について非該当の根拠まで示した。
そのうえで要件 2 / 3 / 4 を「レビュー自体が発生しないので充足できない」と自己申告した。

> **#949 の EPT では accuracy が改修前でも満点になり判別力を持たなかった**
> ([[feedback_ept_checklist_leaks_the_answer]])。今回そうならなかったのは、
> 要件 2 が「**数値が記録に含まれる**」という、**その機構が存在しない限り生成できない出力**を
> 要求しているため。成果物の*性質*ではなく*機構の産物*を要求すると red が出る。
> **checklist 設計の再利用可能な知見。**

### 構造化 reflection (iteration 0)

**R-1 #1 — 帰属: 改修対象 (Phase 2 で解消)**

- Issue: Step 0a → Step 0b の遷移点にレビュワー起動規定が存在しない。executor は
  `CLAUDE.md` の Iron Law 6 Pre-flight Step 5 と fable-consult の推奨トリガー 3 点を
  横断参照したうえで「いずれにも該当しない」と結論した
- General Fix Rule: 評価用 checklist は対象文書に実在が確認できる機構のみを前提に設計する
  (executor 自身の指摘。**これは harness への指摘だが、裏を返せば
  「機構が無い」ことを checklist が正しく検出した**という意味でもある)

---

## Iteration 1

### Changes

`/release` Step 0a-2 の新設 + `.github/pull_request_template.md` の Fable 欄 +
`check-pr-checklist.test.js` の pin 更新と生 exit code テスト。

### 実行結果

| Scenario | 成否 | accuracy (raw) | tool_uses | duration | retries | 新規 unclear | うち defect-class |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R-1 | o | 5/5 | 2 | 63.3s | 0 | 2 | **1** |

**red からの反転**: `x (2/5)` → `o (5/5)`。executor は
`Agent(subagent_type=allaganeye-fable-consult)` を名指しで起動し、
`fable 俯瞰レビュー: 実施 (finding N 件 / 消化 M 件 / 残 K 件 → Track D PR 本文へ転記)` を
skill 逐語で出し、残 K 件の転記義務にも言及した。duration も 167.0s → 63.3s。

### 構造化 reflection (iteration 1)

**R-1 #2 — 帰属: 改修対象 (defect、iteration 2 で修正)**

- Issue: Step 0a-2 が渡すべき材料として挙げた 3 点のうち **2 点がその時点で存在しない**。
  リリース PR 本文は Step 3 で作られ、CHANGELOG の「対象バージョンセクション」も
  見出しリネームが Step 3。この時点では `## [Unreleased]` のまま
- **executor は代替物を自力で発明して渡していた** — 「コミット分析結果のサマリー草稿」を
  release notes の代わりに、`[Unreleased]` の中身を対象バージョンセクションの代わりに
- Cause: step の配置 (#945 が Step 0a 直後に固定) と、参照する成果物の確定タイミング
  (Step 3) の整合を取っていなかった
- General Fix Rule: あるステップが**後続ステップの成果物**を入力として要求する場合、
  その成果物が当該時点で実在するかを検証する。無いものを対象に書くと、
  実行者が代替物を発明して渡すことになり、渡す材料が実行者ごとに変わる

**R-1 #3 — 帰属: harness (対応不要)**: シナリオが CHANGELOG 未リネーム状態を明示しているが、
改修前テキストでは Step 0a→0b の判断に関与しない情報だった。iteration 1 以降は関与する。

### 次の修正 (= iteration 2)

対象を 2 点へ絞り、**その時点で実在するものだけ**を挙げる:

- `CHANGELOG.md` の `## [Unreleased]` セクションの内容
- Step 0a の受け入れゲート達成状況

あわせて **release notes を別途渡す必要がない**ことを明記した —
`extract_release_notes.py` が CHANGELOG の当該セクションを丸ごと抽出して Release 本文に
するので、**CHANGELOG を見ることが release notes を見ることと等しい**。

(収束判定: 0 consecutive clears / 打ち切りまで 2 round)

---

## Iteration 2

### Changes

上記の材料リスト修正のみ。

### 実行結果

| Scenario | 成否 | accuracy | tool_uses | duration | 新規 unclear | うち defect-class |
| --- | --- | --- | --- | --- | --- | --- |
| R-1 | o | 5/5 | 2 | 82.2s | 1 | **1** (Track D 未定義) |

**R-1 #4 — 帰属: 改修対象 (iteration 3 で修正)**: 「残 K 件は **Track D** の PR 本文へ転記」と
書いたが、Track D の定義は `docs/release-process.md:382` の表にしかなく skill 内に無い。
executor は Step 3 の内容から**推測で対応付けた**。転記先を短縮名だけで指示する場合は
定義を当該ステップ内に 1 行インライン化する。

---

## Iteration 3

### Changes

Track D のインライン定義を追加。**scenario R-2 を新設** (PR テンプレート側の Fable 欄を
実際に埋める側。Step 0a-2 だけ検証してテンプレート欄を検証しないのは Phase 1 で
Codex に指摘された「境界を見ていない」と同じ穴になるため)。

### 実行結果

| Scenario | 成否 | accuracy | tool_uses | duration | 新規 unclear | うち defect-class |
| --- | --- | --- | --- | --- | --- | --- |
| R-1 | o | 5/5 | 2 | 66.6s | 2 | **1** (転記先 slot 欠落) |
| R-2 (code PR、非該当) | o | 4/4 | 2 | 57.8s | 1 | 0 |

**R-1 #5 — 帰属: 改修対象 (iteration 4 で修正)。ledger `obligation-without-aggregation-slot`
の 3 回目の再発**: 「Track D PR 本文へ転記」と義務づけているのに、転記先 (Step 3 の PR body
テンプレート) に置き場所が無い。executor は「どの見出し配下に書くか指定がない」と報告。

| 発生 | 義務の場所 | slot が無かった箇所 |
| --- | --- | --- |
| #949 iter0 | subagent の記録義務 | final message の `## meta` |
| #949 iter5 | Step 5a/5.0 の 1 行記録 | `/review-pr` Step 6 テンプレート |
| 本件 iter3 | Step 0a-2 の転記義務 | `/release` Step 3 の PR body |

個別 patch を止めてクラスで閉じた — Step 3 に `### fable 俯瞰レビュー (Step 0a-2)` を新設し、
**「どこかへ転記せよ」と書く規約は転記先テンプレートの名前付きスロットと必ず対で用意する**
という原則を skill に明記。

---

## Iteration 4

### 実行結果

| Scenario | 成否 (self-report) | accuracy | tool_uses | duration | 新規 unclear | うち defect-class |
| --- | --- | --- | --- | --- | --- | --- |
| R-1 | o | 5/5 | 2 | 58.5s | **0** | 0 |
| R-2 (doc-only + spec 新規、**該当**) | o (自己申告) | 4/4 | 2 | 118.2s | 2 | **1 (成果物が誤り)** |

### 本 EPT で最も重い finding — 自己申告は満点、成果物は誤り

R-2 は **2 trigger 両該当の PR に対し `非実施` と記入した**。正解は `実施`。
executor 自身は 4/4 と自己採点しており、**self-report では検出できない**。

- Cause: テンプレートの Fable 行が起動条件を `review-pr/SKILL.md` へ**委譲**していた。
  テンプレートだけを読む記入者は条件を確認できず、`CLAUDE.md` の推奨トリガーが
  「原則。強制ではない」と advisory 表現なので**非実施側に倒れた**
- **同じ原因が iteration 3 の R-2 (code PR) では偶然正解 (非実施) を出していた。**
  非該当ケースだけ見ていたら「正しく動いている」と誤認していた
- General Fix Rule: **記入者が実際に読む場所に決定的な条件を置く。**
  別ファイルへ委譲すると、委譲先を読まない実行者が周辺の緩い記述に倒れる

### 次の修正 (= iteration 5)

テンプレート行に 2 条件 ((a) doc-only / (b) specs・plans への新規追加) を**インライン化**。
非実施の理由も「2 条件のどちらに非該当か」を書かせる形にした。

---

## Iteration 5 (convergence 1/2)

### 実行結果

| Scenario | 成否 | accuracy | tool_uses | duration | 新規 unclear | うち defect-class |
| --- | --- | --- | --- | --- | --- | --- |
| R-1 | o | 5/5 | 2 | 55.0s | **0** | 0 |
| R-2 (回帰テスト: iter4 で誤答したのと同一シナリオ) | o | 4/4 | 2 | 151.4s | 2 | **0** |

**回帰は解消**。R-2 は `実施 (finding 1 件 / 消化 1 件 / 残 0 件)` と正しく記入し、
(a)(b) 両条件の該当を根拠として明示した。R-1 は user-level の `fable-consult` (prefix なし) が
存在し `CLAUDE.md` がそれを禁じていることまで踏まえており、改名の理由も伝わっている。

---

## Iteration 6 (convergence 2/2)

**skill / doc の変更なし** (収束を確定させるため対象テキストを固定)。
base の #985 / #986 / #987 を取り込んだが、いずれも `release/SKILL.md` の L269 以降を触っており
Step 0a-2 (L35-71) とは自動マージが成立。マージ後に **Step 3 が「バージョンバンプと PR 作成」の
ままで転記先 slot (L248) が Step 3 の範囲 (L164-269) 内に残っている**ことを行番号で確認した
(自動マージが通っても参照先が別 step へずれれば doc として壊れるため)。

### 実行結果

| Scenario | 成否 | accuracy | tool_uses | duration | 新規 unclear | うち defect-class |
| --- | --- | --- | --- | --- | --- | --- |
| R-1 | o | 5/5 | 2 | 63.9s | 1 (harness) | **0** |
| R-2 | o | 4/4 | 2 | 137.4s | 1 (harness) | **0** |

両者の unclear は同一で、**dry-run 指示 (実行禁止) と skill の「実測値記入 required」の
メタ衝突**。executor は数値を捏造せず衝突自体を報告しており、対処として正しい。
skill の欠陥ではないので修正しない。

> **iteration 5 + 6 で 2 consecutive clears を達成。**

---

## 収束サマリ (#945 Phase 2)

| iteration | 対象テキスト | defect-class | 判定 |
| --- | --- | --- | --- |
| 0 | 改修**前** | — | **red baseline (x、2/5)** |
| 1 | Step 0a-2 新設 + Fable 欄 | 1 (材料が未生成) | — |
| 2 | 材料リスト修正 | 1 (Track D 未定義) | — |
| 3 | Track D 定義 + R-2 新設 | 1 (転記先 slot) | — |
| 4 | 転記先 slot 新設 | **1 (成果物が誤り)** | — |
| 5 | 起動条件インライン化 | 0 | **clear 1/2** |
| 6 | 変更なし | 0 | **clear 2/2** |

**捕まえた欠陥 4 件はすべて「義務は書いたが受け皿・参照先が実在しない」型**:

1. 材料 3 点中 2 点が Step 3 まで存在しない → executor が代替物を発明
2. `Track D` が skill 内で未定義 → executor が推測で対応付け
3. 転記先の見出しが未固定 → 「指定がない」と報告 (同クラス 3 回目)
4. 起動条件を別ファイルへ委譲 → **成果物が実際に誤り**

**4 は両分岐を covered したから見えた。** 同じ原因が非該当ケースでは偶然正解を出しており、
片側だけの scenario なら「正しく動いている」と誤認していた。

## Codex adversarial-review (Pre-flight Step 5) — 3 round

EPT の 2 consecutive clears **後**に Codex へかけたところ、EPT が見ていなかった層が出た。
**EPT は「指示を読んだ実行者が正しく動けるか」を測るが、「gate が回避できるか」は測らない。**
両者は別の層であり、片方だけでは足りない。

| round | verdict | finding | 対応 |
| --- | --- | --- | --- |
| 1 | needs-attention | [medium] checkbox の消化しか見ておらず「実行せずに緑」 | semantic validator 新設 (Idios 裁定) |
| 2 | needs-attention | [high] 行の削除 / 節外 decoy / 重複で無効化可 | 走査を Self-Test 節内に限定・1 本必須 |
| | | [medium] file list 不可時の silent skip = false-green | **fail-closed へ変更** + workflow permissions 明示 |
| | | [low] placeholder 判定が広く false-red | 既知トークンのみへ絞る |
| 3 | needs-attention | [medium] **doc と実装の契約が食い違う** — round 2 でコードを fail-closed に変えたのに、round 1 で書いた §「見ていない集合」の「skip する」記述を直していなかった | doc を実装の契約へ書き換え |

> **round 3 で新しい回避形は出ず、設計自体への否定もなかった。** 出たのは doc/code の
> 同期漏れ 1 件のみで、whack-a-mole (同一クラスが 3 周) には至っていない。
>
> **この 1 件は自分のミス。** 挙動を変えたのに、その挙動を説明した doc を直さなかった。
> しかも「skip する (意図的に安全側)」という**逆の主張**が残っており、
> 運用者向けの runbook として有害だった。[[feedback_mirroring_impl_copies_latent_bugs]] の
> 変種 — 未検証の主張が契約 doc に昇格したまま残る。
> **挙動を変える commit では、その挙動を説明している doc を同じ commit で探して直す。**

### round 2 [medium] は自分の判断を覆した

round 1 対応時、私は「file list が取れないときは検査 skip」を **false-red 回避として意図的に選び**、
それを §「見ていない集合」に明記して済ませていた。Codex の指摘は
**required status check で「検査せず緑」は穴**というもので、これは正しい。
「限界を明記する」ことは「穴を塞がない」ことの正当化にならない。

### fail-closed の blast radius を実測した

「全 PR が `listFiles` 成功に依存する」形になるため、bot PR への影響を測った:

| ケース | 結果 |
| --- | --- |
| bot PR (Self-Test 節なし) + listFiles 失敗 | **exit 0** (bot 例外が手前で return) |
| 人間 PR (Self-Test 節あり) + listFiles 失敗 | exit 1 (fail-closed) |

順序が入れ替わると Dependabot が落ちるので、**両方を回帰テストとして pin** した。

### 回避形の実測 (round 2 対応後)

| 記入 | 判定 |
| --- | --- |
| 行を削除 (doc-only PR) | **RED** |
| 行を削除 (code PR、対照) | GREEN |
| Self-Test 節の外に準拠行を置く | **RED** |
| 節内に 2 本 | **RED** |
| 半角 / 全角括弧 / 「理由により非実施」 | **RED** |
| `未実施` / `未実行` / `スキップ` / `N/A` | **RED** |
| 山括弧を含む正当な回答 (対照) | GREEN |
| **`実施 (finding 0 件 / 消化 0 件 / 残 0 件)`** | **GREEN (構造的限界)** |

最後の 1 行は **CI から subagent 起動の有無を観測できない**ため塞げない。
`/review-pr` §「この gate が見ていない集合」に明記した。**塞げないものを塞げたことにしない。**

なお **file list 不可時は fail-closed (red)** であり skip しない (round 2 [medium] で変更)。
round 1 時点の「skip する」という記述は round 3 で doc を実装に合わせて訂正済み。

## harness の知見 (再利用可能)

**#949 の EPT では accuracy が改修前でも満点になり判別力を持たなかった**
([[feedback_ept_checklist_leaks_the_answer]])。今回 red baseline が本当に赤くなった
(`x`、2/5) のは、要件 2 が「**数値が記録に含まれる**」という
**その機構が存在しない限り生成できない出力**を要求しているため。

**成果物の*性質*を述べる checklist は改修前でも満点になる。*機構の産物*を要求すると red が出る。**
