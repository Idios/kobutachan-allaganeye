# EPT: レビュー・ゲート規約の導出化 (#935 / #856 / #870 + spec G1-1)

対象: `docs/l2-workflow.md` §Step 5 の focus 導出手順 / §規約・ガード導入の 3 点セット / §triage 入力 4 系統、`.claude/skills/review-pr/SKILL.md` Step 5・§5c、`.claude/hooks/session-start.sh` Step 5 文言、`CLAUDE.md` §destructive write boundary audit checklist。

上流 protocol: <https://github.com/mizchi/skills/tree/main/meta/empirical-prompt-tuning> (vendoring せず都度参照。本 run では `gh api repos/mizchi/skills/contents/...` で取得)

## Iteration 0 (description / body consistency)

`review-pr` / `iterate-review` の frontmatter `description` は無変更。body 変更は Step 5 / §5c / eval requirements の条文差し替えと新節追加であり、description が主張する scope (PR レビューのオーケストレーション + トリアージ) を逸脱しない。gap なし。

## シナリオと要件チェックリスト (事前固定)

| シナリオ | 対象 | 内容 |
| --- | --- | --- |
| A (中央値) | Step 5 focus 導出 (`l2-workflow` + hook + CLAUDE.md) | `--archive-dir` を新設し `os.replace()` で MP4 を移動する PR に対し、Step 5 の実行計画と focus 文字列を書かせる |
| B (edge) | `/review-pr` Step 5 の G1-1 逐条検証 | CI job + script + 規約文 + PR template を新設する PR に対し、Step 5 の検証項目を列挙させる |
| C (edge) | §triage 入力 4 系統 | v0.3.2 の roadmap triage で入力と実行コマンドを列挙させる |

要件は各シナリオ 5 項目 ([critical] 2 項目) を dispatch 前に固定し、以後変更していない (A-1〜A-5 / B-1〜B-5 / C-1〜C-5)。条文は本 PR の `eval/requirements.md` 差分および各 round の dispatch prompt に記録。

## Iteration 0.5: red baseline (改修**前**テキスト)

**目的**: 散文だけの PR における「発火側の red 実証」(G1-1 ③) の代替として、改修前テキストで同一シナリオを回し、要求される振る舞いが出ないことを観測する。入力は base commit `b5de787` から切り出した同一 section で、modality (ファイル 1 本を Read) は改修後と揃えた。

| シナリオ | Success | unclear points | retries | tool_uses | duration_ms |
| --- | --- | --- | --- | --- | --- |
| A | ○ | **2** | 0 | 1 | 142,943 |
| B | **×** (B-1 / B-2 とも [critical] ×) | 4 | 0 | 1 | 160,054 |
| C | ○ | 3 | **1** | 1 | 183,745 |

**red の中身**:

- **B は [critical] 2 項目が × で明確な失敗**。改修前テキストには 3 点セットが存在せず、executor は「file に根拠のない項目は追加しない」と明記したうえで発火点・red 実証・非実施記録のいずれも検証項目に挙げられなかった
- **A の unclear point 2 件が、本 PR の修正内容と一致した**:
  - 「固定 3 bullet のみで、diff から導出せよという step が無い」→ General Fix Rule =「adversarial review の focus は例示提供前に diff 導出 step を必須化せよ」= #935 P2-1 そのもの
  - 「`<version>` placeholder に解決手段が無い」= #856 item3 そのもの
- **C は unclear point 1 件目が #870 と一致** (「タスク発見は日常の着手選定に最適化されており、リリース前の網羅的 triage を想定していない」)。かつ **retry 1 回** — 一度 open issue のみの計画を作りかけて作り直している

**測定上の限界 (正直な記録)**: mizchi protocol は要件チェックリストを executor に渡す契約なので、「instruction がそれを指示しているか」を問う要件では**チェックリスト自体が答えを漏らす**。A と C が [critical] ○ になったのはこの漏洩によるもので、instruction が要求を満たしていた訳ではない (executor 自身が「file には記載が無いため Scenario の要求仕様に基づき自分の判断で追加した」と明記している)。したがって本 run では protocol の定める**主軸である qualitative 側 (unclear points / discretionary fill-ins / retries)** を判定に用い、accuracy は補助に留める。

## Iteration 1 (改修後、fresh subagent × 3)

| シナリオ | Success | unclear points | retries | tool_uses | duration_ms |
| --- | --- | --- | --- | --- | --- |
| A | ○ | **0** | 0 | 1 | 151,535 |
| B | ○ (red の × から反転) | **0** | 0 | 1 | 76,558 |
| C | ○ | **0** | 0 | 1 | 86,028 |

新規 unclear point **0 件** → **clear #1**。red baseline で挙がった 5 件 (A2 / B4 相当 / C1) はすべて消えた。B の duration は 160s → 77s (-52%)、C は 184s → 86s (-53%)。C の retry も 1 → 0。

## Iteration 2 (fresh subagent × 3)

この round の直前に、dogfooding と Codex adversarial-review で見つけた欠陥を反映している (下記「本 run で発見・修正した実欠陥」参照)。

| シナリオ | Success | unclear points | retries | tool_uses | duration_ms |
| --- | --- | --- | --- | --- | --- |
| A | ○ | 1 (**harness 起因**) | 0 | 1 | 171,807 |
| B | ○ | **0** | 0 | 1 | 64,014 |
| C | ○ | **0** | 0 | 1 | 42,716 |

A の 1 件は「CLAUDE.md の対の checklist を参照せよと書かれているが、この評価タスクの制約で CLAUDE.md を読めない」という **eval harness 起因**。実運用では CLAUDE.md は毎セッション自動注入されるため読み取り障壁は存在しない。**instruction の欠陥ではないが、raw count としては 1 と記録する。** harness 側を次 round で修正した (CLAUDE.md 該当節を scenario A の入力に併載)。

## Iteration 3 (harness 修正後、fresh subagent × 3)

| シナリオ | Success | unclear points | retries | tool_uses | duration_ms |
| --- | --- | --- | --- | --- | --- |
| A | ○ | 1 (**harness 起因**: 「コマンド非実行」制約) | 0 | 1 | 140,242 |
| B | ○ | 1 (**隣接する既存節**の該当判定) | 0 | 1 | 79,752 |
| C | ○ | **0** | 0 | 1 | 94,166 |

- A: CLAUDE.md 併載により前 round の指摘は解消。新たに「plan only 制約で grep を実行できないため focus は draft」という指摘が出たが、これはシナリオが仮想 PR である以上構造的に発生するもので instruction の欠陥ではない。次 round では prompt 側で明示的に除外した
- B: **本 PR の変更点ではなく、同じ抜粋に含まれる既存の §installer / workflow 系ブロック**について「workflow ファイルを touch しただけで該当するのか」が判定不能という指摘。これは実在する曖昧さなので **(A) PR 内で修正**した (該当判定 = 「外部依存の DL / 取得を追加・変更している」ことであって path を touch したことではない、+ 非該当時の 1 行記録義務)

## Iteration 4 (該当判定 fix 後、fresh subagent × 3)

| シナリオ | Success | unclear points | retries | tool_uses | duration_ms |
| --- | --- | --- | --- | --- | --- |
| A | ○ | **0** | 0 | 1 | 94,052 |
| B | ○ | **0** | 0 | 1 | 98,868 |
| C | ○ | **0** | 0 | 1 | 66,595 |

B は追加した該当判定に従い「外部依存規約: 非該当 (理由: 本 PR に外部依存の DL / 取得なし)」を自力で導出し、Step 6 への 1 行記録まで書いた。round 3 の指摘は解消。

## 収束判定

| round | A | B | C | raw 合計 | 改修テキストに帰属する件数 |
| --- | --- | --- | --- | --- | --- |
| red baseline | 2 | 4 (B-1/B-2 **[critical] ×**) | 3 | 9 | — (改修前) |
| 1 | 0 | 0 | 0 | **0** | **0** |
| 2 | 1 (harness) | 0 | 0 | 1 | **0** |
| 3 | 1 (harness) | 1 (隣接既存節) | 0 | 2 | **0** |
| 4 | 0 | 0 | 0 | **0** | **0** |

- **改修テキストに帰属する新規 unclear point は 4 round 連続で 0**。停止条件 (2 consecutive clears) は **round 1 → round 2 で充足**している
- **raw count でも round 1 と round 4 が 3 シナリオとも 0**。ただし raw 基準では round 1 と round 4 は連続していない (間に harness 起因 2 件と隣接既存節 1 件を挟む) ため、「raw で 2 round 連続 0」は主張しない
- 停止条件を満たした後も 2 round 追加で回し、harness の欠陥 2 件と隣接既存節の曖昧さ 1 件を消化した。うち隣接既存節の 1 件は **(A) PR 内で修正**した
- 発散 (3 round 以上 unclear point が減らない) には該当しない

## 本 run で発見・修正した実欠陥 (EPT / dogfooding / Codex 由来)

いずれも「散文だけ足して機械検査が無い」状態を避けるための実測から出た。

1. **triage 系統 (4) の self-hit**: doc に書いた grep コマンド自身が本節にマッチする。`| grep -v 'grep -rnE'` を追加
2. **focus 導出 grep の doc self-hit**: 同型。`CODE` に code path の pathspec を入れて解決
3. **不可逆操作 grep が本 codebase の実書込を見ていなかった**: Python/Rust の write API しか見ておらず、実書込の大半を担う ffmpeg subprocess を捕捉できていなかった。**PR #930 の diff に対する実測は 2a = 0 hit (production code) / 2b = 30 hit** — 規約が防ごうとしている当の欠陥を検出できていなかった。2b (subprocess 層) を必須化
4. **Step 5 の起動コマンドが実行不能**: `VAR=... node "$VAR/..."` は `$VAR` が代入前に展開されて空になり、MSYS が裸の `/scripts/...` を `C:\Program Files\Git\scripts\...` へ書き換えて `MODULE_NOT_FOUND`。**本 run で実際に踏んだ**。`export` を独立文に分離。あわせて `| tee` が rc を握り潰す点も併記
5. **G1-1 の発火点の過大主張 (Codex [high] / No-ship)**: 参照契機 表が 4 経路を主張していたが、`create-task` は grep 0 hit、`superpowers:brainstorming` は plugin で編集不可。自分自身が G1-1 ①に違反していた。`create-task` に節を新設して 3 経路を実在化し、brainstorming 行は「規律のみ」へ降格
6. **§installer / workflow ブロックの該当判定が不明 (EPT round 3)**: trigger が「外部依存の DL / 取得の追加・変更」であって path touch ではないことを明示 + 非該当時の 1 行記録義務

## 失敗パターン台帳 (本 target prompt 用)

- **doc 内 grep の self-hit**: doc がパターン自身を含むため、その doc を scan 対象にすると必ず自己マッチする
  - General Fix Rule: doc に実行可能な grep を載せるときは、**その doc 自身を対象に含めた場合の self-hit を必ず実測**し、pathspec か後段 `grep -v` で落とす
  - Seen in: dogfooding (focus 導出) / dogfooding (triage 系統 4)
- **能力の層を 1 つしか見ない検出器**: 「不可逆書込」を言語 API だけで定義すると、subprocess が実行する書込を落とす
  - General Fix Rule: 検出器を書いたら**過去の実欠陥 (positive control) に対して非ゼロ hit を返すことを実測**する。返さないなら層が足りない
  - Seen in: dogfooding (2a/2b)
- **発火点の過大主張**: 参照契機を表に書くと「実装済み」に見えるが、参照先に条文が無ければ no-op
  - General Fix Rule: 発火点を主張したら**参照先ファイルを grep して条文の実在を確認**する。編集不能な plugin は発火点に数えない
  - Seen in: Codex adversarial-review round 1

## 環境・制約の記録

- dispatch: `general-purpose` / `model: sonnet` / 3 並列 / 各 round は **fresh subagent** (同一 agent の再利用なし)
- 入力は round ごとに切り出した同一 section を中立名のファイル (`.ept-tmp/rN/scen*_instructions.md`) で与え、red / green で modality を揃えた。当該一時ファイルは commit していない
- 12 回の dispatch 後も worktree の tracked file に subagent 由来の変更は無いことを `git status --porcelain` で確認済み
