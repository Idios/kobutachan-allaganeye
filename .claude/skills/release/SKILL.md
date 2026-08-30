---
name: release
description: deferred issue レビュー → バージョンバンプ → リリース PR 作成 → タグ打ち直前の CHANGELOG 見出し日付確定 を自動化する
---

# リリーススキル

バージョンバンプとリリース PR を作成します。

## 引数

`$ARGUMENTS` にバージョン種別を指定（省略時は自動判定）:

- `patch`: バグ修正のみ
- `minor`: 新機能追加
- `major`: 破壊的変更

自動判定ルール（引数省略時）: 前回タグ以降のコミット prefix から判定。`feat:` / `feat(...)` があれば minor、`!` または `BREAKING CHANGE` があれば major、それ以外（`fix` / `docs` / `refactor` / `chore` / `test` のみ）は patch。判断が曖昧な場合はユーザーに確認する。

## 手順

### Step 0a: リリース受け入れゲートの確認（必須）

リリース PR を作成する前に、[`docs/release-process.md` §レイヤーリリース受け入れゲート](../../../docs/release-process.md) のチェックリストを全件達成しているか確認する。本ステップはスキップできない。

1. 対象バージョン (例 `v0.2.0`) を特定し、§共通項目 + §`v0.x.0` (L?) 固有項目 の 2 ブロックをユーザーに提示
   - **patch release には対応するレイヤー固有ブロックが存在しない**（固有項目は minor の `v0.x.0` 単位でしか定義されない）。その場合は §共通項目 のみを提示し、「レイヤー固有項目は該当なし（patch release のため）」と**明示**する。黙って 1 ブロックだけ出して済ませない
   - §共通項目 は minor / patch の**両方**に適用される（裁定 D5）。patch だからと本ゲートごと省略しない
2. 各項目について「達成 / 未達成 / 該当なし」を 1 件ずつ確認する。3 件以上の bulk 確認になる場合は **Step 0c の [§bulk 件数の運用](#bulk-件数の運用-iron-law-2-整合) と同じ規約**に従う (サンプル 1 件提示 + 3 択)。本 step 固有の差分は選択肢の意味だけで、件数の閾値・サンプルの選び方・「個別調整」選択時の挙動は同じ:
   - 件数 ≤2: 1 件ずつ AskUserQuestion で個別確認
   - 件数 ≥3: サンプル **1 件** (下記 §Track 構造の除外を適用した**後の母集団**の先頭)。本 step での「並び順」は [`docs/release-process.md` §レイヤーリリース受け入れゲート §共通項目](../../../docs/release-process.md) の記載順 — 4 点セットのうち**並び順だけが対象集合ごとに違う**ので、ここで上書きする + 「全件 OK (= 全件 達成) / 個別調整 / 中止」の 3 択
   - **「個別調整」選択時は 1 件ずつの確認に進む** (Step 0c と同じ挙動)。「全件 OK」で通した場合、全項目を「達成」として記録する
3. 1 件でも未達成があれば本スキルは中断し、ユーザーに残タスクの優先処理を依頼 (ただし下記 **Track 構造の patch release** の例外を先に読むこと)
4. 全件達成を確認してから Step 0b へ進む。**Track 構造の patch release では「全件達成」を「除外 3 項目を『Track D で達成予定』と記録し、残り全件が達成」と読み替える** (下記例外節)。読み替えないと、定義上到達しない条件を待って Step 0b / Step 0a-2 が永久に起動しない

#### Track 構造の patch release における再評価点 (#962 項目 4)

**[`docs/release-process.md` §Patch release の Track 構造](../../../docs/release-process.md#patch-release-の-track-構造) に従う patch release では、§共通項目 の一部は Step 0a の時点で構造的に未達である。** Track D (version bump + CHANGELOG) が直列最後だからで、これを「未達 → 中断」と扱うと release が永久に始まらない。

| §共通項目 | Step 0a 時点 | 満たされる時点 |
| --- | --- | --- |
| 対象スコープの全 PR がマージ済み | **未達でよい** (Track A-C 進行中) | Track D PR 作成の直前 |
| バージョン保持箇所が全箇所 `x.y.z` | **未達でよい** (旧版のまま) | Step 3 のバンプ後 |
| CHANGELOG に対象バージョンセクションがある | **未達でよい** (`## [Unreleased]`) | Step 3 の節見出し改名後 |
| 上記以外の項目 | **達成が必要** | Step 0a |

- Step 0a では上記 3 項目を **「Track D で達成予定」**として記録し、中断しない。それ以外の項目に未達があれば従来どおり中断する
- **上記 3 項目は Step 0a の項目 2 (bulk 確認) の母集団から除外する。** サンプル選定 (先頭 1 件) の対象にもしないし、「全件 OK」を選んだときの一括「達成」記録の対象にもしない。除外しないと、bulk の記録規約 (全項目を「達成」として記録) と本節の記録規約 (「Track D で達成予定」) が同じ項目に対して衝突する。**本節の記録が優先**する
- **再評価点は Step 3 のバンプ・CHANGELOG 改名を終えた直後** (Step 3 の検証コマンドが exit 0 になった時点)。ここで 3 項目を再確認し、1 件でも未達ならリリース PR を作らない
- minor / major release ではこの例外を使わない (Track 構造の適用対象外。[`docs/release-process.md` §適用条件](../../../docs/release-process.md#適用条件))

注意: 本ゲートは Iron Law 1 (受け入れ条件全充足) のリリースレベル展開。`deferred` review (Step 0b / 0c) はゲート §共通項目内の 1 行に対応するため、Step 0b / 0c はゲート確認の延長として扱う。

### Step 0a-2: リリース俯瞰レビュー (allaganeye-fable-consult、必須) (#945)

Step 0a の全件達成 (Track 構造の patch release では Step 0a 項目 4 の読み替え後の意味) を確認したら、**`Agent(subagent_type=allaganeye-fable-consult)` を起動して
リリース記述を俯瞰レビューさせる**。本ステップはスキップできない。

**対象** (2 点をまとめて渡す。**本 step の時点で実在するものだけを挙げてある**):

- **`CHANGELOG.md` の `## [Unreleased]` セクションの内容** — [`docs/release-process.md` §CHANGELOG entry の記述規約](../../../docs/release-process.md) を満たしているか。読者 (FF14 プレイヤー) の語彙で書けているか、内部語彙が混入していないか
- **Step 0a の受け入れゲート達成状況** — 「達成」と付けた項目が実際に達成の実質を持つか

> **release notes を別途渡す必要はない。** [`scripts/extract_release_notes.py`](../../../scripts/extract_release_notes.py) が CHANGELOG の当該セクションを**丸ごと抽出して GitHub Release 本文にする**ので、**CHANGELOG を見ることが release notes を見ることと等しい**。
>
> **この時点で存在しないものを対象に挙げない。** 見出しの `## [Unreleased]` → `## [<版>] - YYYY-MM-DD` へのリネームも、リリース PR 本文も **Step 3** で作られる。本 step は Step 0a 直後 (Step 0b より前) に置かれているため、それらはまだ無い。無いものを対象に書くと、実行者が代替物を発明して渡すことになる (#945 Phase 2 の EPT で実際に発生した)。

**観点**: 利用者から見た振る舞いの記述漏れ / 内部語彙の混入 / 既存 doc との矛盾 / スコープ過大。
コードの技術的欠陥は対象外 (それは Codex、`CLAUDE.md` §「Fable と Codex の棲み分け」)。

#### 起動記録 (実施 / 非実施とも必須、数値記入 required)

以下のいずれか 1 行を、**本 step の直後にユーザーへ提示し、かつ Track D PR 本文の
`### fable 俯瞰レビュー (Step 0a-2)` スロットへ転記する** (転記先は Step 3-6 の PR body テンプレートに定義済み)。

> `fable 俯瞰レビュー: 実施 (finding N 件 / 消化 M 件 / 残 K 件 → Track D PR 本文へ転記)`
>
> `fable 俯瞰レビュー: 非実施 (理由: <1 行>)`

**記録の置き場所を揮発的な対話画面で指定しない。** 本 step は Step 0a の全件達成確認が**終わった後**に
走るので、「Step 0a の 3 択と同じ画面」のような指定は、記録を書く時点で既に閉じている画面を指す。
記録先は**永続する成果物の名前付きスロット**で指定する (転記先の見出しを固定してあるのと同じ方式)。

**ただし転記先の PR 本文は Step 3-6 まで存在しない。** 生成時刻が転記先の生成時刻より前なので、
**その間の保管場所も指定する**: 本 step で生成した 1 行を **TodoWrite / セッションの plan に逐語で退避**し、
Step 3-6 で PR body を組むときにそこから貼る。保管場所を決めないと、
「揮発的な画面に書くな」という規約と「まだ書き込む先が無い」という物理状況が衝突し、
実行者ごとに保管手段を発明することになる。

**`実施` は N / M / K の数値記入が必須。** 数値を required にしないとこの step は no-op になる —
Step 0a の判定は「達成 / 未達成 / **該当なし**」の 3 択で、**「該当なし」で通過できてしまう**ため
(#945 が明示した false-green の制約)。**残 K 件がある場合は Track D の PR 本文へ転記する義務がある。**
「実施した」とだけ書いて finding をゼロ件のまま放置する経路を塞ぐ。

**Track D = version bump + CHANGELOG を担う直列最後の PR** ([`docs/release-process.md` §Patch release の Track 構造](../../../docs/release-process.md#patch-release-の-track-構造))。本 skill では **Step 3-6 で作る hop 1 の PR** がこれにあたる。**hop 数 = 2 の構成でも転記先は hop 1 の PR 本文 1 箇所**で、hop 2 は同じ本文を流用してよいが転記義務の対象ではない (「リリース PR」と単数で書くと、2 本ある構成でどちらか決まらなくなる)。転記先を短縮名だけで書くと、Track 構造を知らない実行者が対応表を推測で埋めることになるため定義をここに置く。

**転記先の見出しは Step 3 の PR body テンプレートの `### fable 俯瞰レビュー (Step 0a-2)`** に固定してある。転記義務を課すだけで転記先に置き場所を作らないと、実行者ごとに書式と位置が割れる (#949 で 2 度、本 step で 3 度目に観測したクラス)。**「どこかへ転記せよ」と書く規約は、転記先テンプレートの名前付きスロットと必ず対で用意する。**

> **記録義務は分岐を網羅する**: 実施 / 非実施の両方に定型を置いてある。異常系・非該当だけに
> 定型を用意すると、正常系のたびに実行者が文言を発明して表記が揺れる
> (`/review-pr` §「起動記録」と同じ原則)。

### Step 0b: deferred 全件取得 (M9、F8 教訓)

リリース前に `deferred` ラベル付き issue を全件取得する。**release-blocker label は新設しない** (M8 撤回、2026-05-17 確定) — 取得対象は `deferred` 単独で十分。

```bash
gh issue list --repo Idios/kobutachan-allaganeye --state open --label "deferred" --limit 200 \
  --json number,title,labels,createdAt,updatedAt
```

- 件数 0 → deferred 分類 (Step 0c) は skip。ただし **Step 0c-2 の not_planned 残タスク確認** (リリース区間ベース、deferred 件数と独立) は必ず実施してから Step 2 へ進む (本文鮮度は対象 deferred が無いため skip 可)
- 件数 ≥1 → **Step 0c-2 (本文鮮度 + not_planned) を実施後**、Step 0c で全件分類

### Step 0c: deferred 1 件ずつ 3 択分類 (M9 再設計版)

Step 0b で取得した各 deferred issue について、AskUserQuestion で以下 3 択を user に提示:

- **(a) 次 release で吸収**: 本 release / 次 patch の **Track B 吸収候補** とする。spec PR (Track 0) の table に記録
- **(b) deferred 継続**: ラベル変更なし。本 release では取り込まない (次 cycle に再評価)
- **(c) close**: `gh issue close <番号> --comment "<理由>"` でクローズ (won't fix / 再現不能 / 仕様変更等)

#### bulk 件数の運用 (Iron Law 2 整合)

**本節が bulk 確認規約の定義側**で、以下の **4 点セット (件数閾値 / サンプル数 / 並び順 / 「個別調整」時の挙動)** を持つ。借用側 (Step 0a) は「本節と同じ規約」とだけ書く — 4 点のどれかを借用側にしか書かないと、定義側を直接読んだ実行者に届かない。

- 件数 ≤2: 1 件ずつ AskUserQuestion で個別確認
- 件数 ≥3: **先に Iron Law 2 bulk pre-check** (サンプル **1 件**提示 + 「全件 OK (= 全件 (b) deferred 継続) / 個別調整 / やめる」3 択)
- **並び順**: サンプルの「先頭」は **Step 0b の `gh issue list` の出力順** (= 既定の作成日時降順) の先頭を指す。取得コマンドに `--sort` を足さない限りこの順が正
- 「全件 OK」選択時の挙動 (B-2/B-3 fix): **全件を (b) deferred 継続として処置**し、Step 0c table の分類列を全件 `(b) deferred 継続` で埋める。「全件 (a) 次 release 吸収」と読み違えやすいため pre-check の選択肢 description で「(b) 継続」を明示する規約とする。「全件 (a) 次 release 吸収」を意図する場合は user が `Other` で明示する
- 「個別調整」選択時のみ 1 件ずつの確認に進む

#### Step 0c 結果の spec PR table 化 (Track 0)

(a) / (b) / (c) 各分類結果を spec PR (Track 0、`docs/superpowers/specs/<date>-v0.M.N+1-patch-design.md`) の §deferred 全件検証結果 table に保存:

```markdown
### §deferred 全件検証結果 (`/release` Step 0c)

| issue # | title | 分類 | 判断理由 |
| --- | --- | --- | --- |
| #374 | ... | (a) 次 patch 吸収 | UX critical |
| #432 | ... | (b) deferred 継続 | L3 scope |
| #555 | ... | (c) close | 再現不能 |
```

(a) と分類された issue 群が [`docs/release-process.md` §Patch release の Track 構造](../../../docs/release-process.md#patch-release-の-track-構造) の **Track B 吸収候補** となる。Track B PR は本 spec PR の table をリンクで引く。

#### Step 0c で block する条件 (release PR 作成前 gate)

- deferred 件数 > 0 かつ Step 0c の確認が完了していない → release PR 作成を block (本 skill が abort)
- (a) 分類 issue 群が次 release scope に取り込まれる commit / PR plan を持たない → block (`/iterate-review` / `/create-task` で Track B PR の plan を先に作る)

F8 (deferred 持ち越し: #374 / #458 / #743 / #749 / #756 が v0.2.1 まで漏れた事例) の根本対策。

#### Step 0c-2: deferred 本文鮮度 + not_planned 残タスク確認 (#817 / audit P2-39)

**実行順序**: 本確認は Step 0c の分類 (bulk pre-check 含む) の**前に**実施する。bulk pre-check で「全件 OK (= 全件 (b) 継続)」を選ぶ場合も省略しない (古い本文・orphan 残タスクのまま継続するのを防ぐのが目的のため)。なお **本文鮮度** は各 deferred issue 単位のため deferred 0 件時はスキップ可だが、**not_planned 残タスク** はリリース区間ベース (deferred 件数と独立) のため deferred 0 件でも必ず実施する。

以下 2 点を確認する (closed 側から open 側への参照切れの構造的検出):

- **本文鮮度**: 各 deferred issue の本文と直近コメントを、関連 spec / design doc と突合する。本文が現状の実装・方針と矛盾 (鮮度切れ) している場合は、分類前に `gh issue edit <番号>` での本文更新を提案する (古い前提のまま (b) 継続すると次 cycle も腐り続けるため、#753「親 issue 本文が腐る」と同型の予防)
- **not_planned 残タスク**: リリース区間 (前タグ〜HEAD) の commit / doc が参照する issue 番号のうち、コード/doc 内マーカー (`wired in #N` / `Refs #N` / `TODO(#N)` 等) が指す `#N` が **not_planned で close** されている場合、その残タスクの行き先 (再起票要否) を確認する (#762 が not_planned close されて残タスクが orphan 化した事例)。マーカー探索の具体例:

  ```bash
  # 前タグを解決する。プレースホルダのままにしない (#962 項目 2)。
  # **この 1 行が `PREV_TAG` の唯一の定義**で、Step 2-2 のコミット分析はこれを参照する
  # (定義を 2 箇所に写すと片方だけ変わって区間がズレる)。
  # タグが 1 つも無い repo では describe が失敗するので fallback を持つ。
  PREV_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "HEAD~50")

  # リリース区間の diff から issue 参照マーカーを抽出
  git log "$PREV_TAG"..HEAD -p -- '*.py' '*.md' '*.rs' '*.ts' | grep -oE '(wired in|Refs|TODO\() ?#[0-9]+'
  # 抽出した各 #N の close 理由を確認 (not_planned を検出)
  gh issue view <N> --json state,stateReason --jq '"\(.state) \(.stateReason)"'
  ```

  **確認は AskUserQuestion で行う (#962 項目 5)。** 「確認する」を動詞句のまま残すと、実行者ごとに
  自由記述の問い合わせになったり独断で行き先を決めたりして記録が残らない。検出した
  not_planned issue **1 件につき**、次の 3 択を提示する:

  - **(a) `/create-task` で残タスクを再起票**: 行き先が無く、まだ必要な作業が残っている
  - **(b) 対応不要 (マーカーが陳腐化)**: 実装済み / 方針変更でマーカー側が古い
  - **(c) 既存 issue に集約済み**: 行き先の issue 番号を user が指定する

  **2 問目 (常に一緒に提示する)**: マーカー除去の行き先 —
  「別 issue に切る」 / 「本 release で消す」 / **「該当なし ((a) / (c) を選んだため)」**。
  1 回の呼び出しの中で「1 問目の回答に応じて 2 問目を出す」ことは機構上できないので、
  **2 問目は常に提示し、選択肢に「該当なし」を含める**。こうすると 1 件あたりの呼び出しは
  常に 1 回で、下記の件数閾値と数が合う。

  > **選択肢の列挙は途中に散文を挟まず 1 塊で閉じる。** 補足規約をリストの途中へ差し込むと、
  > リストの外延が視覚的に閉じてしまい、後続の選択肢 ((c) 等) を提示し損ねる。

  検出が 3 件以上なら、先に **Iron Law 2 bulk pre-check** ([§bulk 件数の運用](#bulk-件数の運用-iron-law-2-整合) と同じ規約) を通す。結果は Step 0c の spec PR table と同じ場所へ 1 行ずつ記録する。**検出ゼロなら「not_planned 残タスク: 検出 0 件」を 1 行記録する** — 無記載だと「検査してゼロ」と「検査していない」が区別できない

### Step 1: 廃止 (Step 0b / 0c へ統合済み。欠番であって読み落としではない)

### Step 2: リリース準備

1. 現在のバージョンを `pyproject.toml` から取得
2. 前回リリースタグ以降のコミットを分析:

   ```bash
   # Step 0c-2 で解決した $PREV_TAG をそのまま使う (定義は Step 0c-2 の 1 箇所だけ)。
   # **shell を跨ぐと変数は消える。** 空のまま `git log ..HEAD` を実行すると空の範囲を
   # exit 0 で返す (= 沈黙した false-green) ので、必ず非空を確認してから使う。
   # 別 shell なら Step 0c-2 と同一の 1 行で再解決してから下を実行する。
   # ガードは対話 shell に貼っても窓が閉じない形にする (`exit 1` は対話 shell 自体を終了させる)。
   if [ -z "$PREV_TAG" ]; then
     echo "PREV_TAG が空です (Step 0c-2 の定義を再実行してから続けてください)" >&2
   else
     git log "$PREV_TAG"..HEAD --oneline
   fi
   ```

3. バージョン種別を決定（引数指定 or 上記「自動判定ルール」）
4. **分岐元ブランチ**と**リリース PR の宛先 (`--base`)** を分けて特定する。**この 2 つは同じとは限らない**:

   | 種別 | 分岐元 (`release/v<新バージョン>` をここから切る) | リリース PR の `--base` | `main` までの hop 数 |
   | --- | --- | --- | --- |
   | minor / major | `develop-<新バージョン>`（既存 develop ブランチ） | **`main`** | **1** |
   | patch (`develop-<新バージョン>` **あり**) | `develop-<新バージョン>` | `develop-<新バージョン>` | **2** |
   | patch (`develop-<新バージョン>` **なし**) | `main` | `main` | **1** |

   - 実例 (minor): v0.3.0 = PR [#924](https://github.com/Idios/kobutachan-allaganeye/pull/924) は head=`release/v0.3.0` / **base=`main`**、分岐元は `develop-0.3.0`。**`--base` に分岐元をそのまま渡すと、リリース PR が `main` ではなく develop を向く**
   - 判断が曖昧な場合は `git branch -r | grep -E 'origin/develop-|origin/main'` の結果を提示してユーザー確認

5. **hop 数が 2 のときは、`main` へ到達するまでに PR を 2 本作る** (#962 項目 6)。表の「hop 数」列が 2 の行に該当したら、以下を**明示の作業単位として計画に入れる**。1 本目だけ出して終わったと誤認する経路をここで塞ぐ:

   | hop | head | base | 作る Step | 実例 (v0.2.1) |
   | --- | --- | --- | --- | --- |
   | **hop 1** | **`<hop1 head>`** | `develop-<新バージョン>` | Step 3-6 | [#773](https://github.com/Idios/kobutachan-allaganeye/pull/773) |
   | **hop 2** | `develop-<新バージョン>` | `main` | **Step 3-7** (下記) | [#774](https://github.com/Idios/kobutachan-allaganeye/pull/774) |

   > **`<hop1 head>` はここで 1 度だけ決める変数**で、Step 3-2 / 3-5 / 3-6 と Step 4 の表はすべてこの変数を指す。ブランチ名を各所にリテラルで書くと、下記の変種が効くのが 1 箇所だけになり、後続 step が古い名前を持ち続ける:
   >
   > | 条件 | `<hop1 head>` |
   > | --- | --- |
   > | 通常 | `release/v<新バージョン>` |
   > | spec が「`release/vX.Y.Z` 統合ブランチを作らない」と裁定 (例: v0.3.1 の裁定 D4) | **`claude/v<新バージョン のドットを - に置換>-release-track-d`** (例: v0.3.1 → `claude/v0-3-1-release-track-d`) |
   >
   > **`claude/<slug>` のような名前空間だけの指定にしない。** この値は Step 3-2 / 3-5 / 3-6 と Step 4 の表の 4 箇所で**同一**でなければならないので、構成規則まで固定する。
   >
   > **hop 1 を省く変種ではない。** 裁定が出ている場合でも hop 1 の PR 自体は作る (head が `claude/<slug>` になるだけ) し、**hop 2 は変わらず必要**。「release ブランチを作らない = PR は 1 本」と読み違えない。
   >
   > **タグを打つのは hop 2 のマージ後、`main` の HEAD に対して**である ([`docs/release-process.md` §タグ運用](../../../docs/release-process.md#タグ運用))。hop 1 のマージ時点でタグを打たない。

6. **`develop-<次バージョン>` を切るタイミングを取り違えない** (#918 item1)。上の表で言う `develop-<新バージョン>` は**今リリースするバージョンの開発統合先**であり、**既に存在している**ブランチである。本スキルが新規作成することはない。

   *次*のバージョン用の `develop-<次バージョン>` は、**タグ打ちと GitHub Release 作成が完了した後**に `main` から切る（[`docs/release-process.md`](../../../docs/release-process.md) §レイヤー間の移行手順 の 5、§ルール の 4）。リリース PR を `main` へマージする前でも、タグを打つ前でもない。切った直後に[バージョン保持箇所](../../../docs/versioning.md)を全箇所まとめて次バージョンへ更新する。**「完了した」の判定は Step 5 の後に置いた [§タグ打ち・GitHub Release 作成](#タグ打ちgithub-release-作成) の完了確認コマンドで行う** (#962 項目 7)。

### Step 3: バージョンバンプと PR 作成

> **実行順序は下の番号どおりで、読み替えてはいけない** (#962 項目 1)。特に
> **リリースブランチの作成 (3-2) はバージョン編集 (3-3) より前**である。逆にすると
> 編集済みの dirty tree のまま `git checkout <分岐元>; git pull` することになり、
> checkout 失敗・pull の merge 中断・編集の巻き戻しのいずれかを踏む。
> 順序は **branch 作成 → 編集 → 検証 → commit → push → PR** で固定する。

1. **分岐元ブランチに居ることを確定させてから事前品質チェックを回す** ([`docs/l2-workflow.md`](../../../docs/l2-workflow.md) §「PR 作成 path 別自動チェック」)。**在ブランチを先に確定する**のは、3-1 の修正を「分岐元ブランチ上で commit」するために、その時点で既に分岐元に居る必要があるため (別ブランチから移ろうとすると、まさに 3-2 が防いでいる dirty checkout になる):

   ```bash
   git checkout <分岐元ブランチ>   # 既に居るなら no-op
   git pull
   ```

   ```bash
   ruff check .
   ruff format --check .
   pytest
   # pyright は PATH の python から解析環境を解決するため --pythonpath 必須 (省略は false-red、#974)。
   # git 解決形にすると repo root / worktree の両方で効く (worktree に .venv は無い)。
   pyright --pythonpath "$(dirname "$(git rev-parse --git-common-dir)")/.venv/Scripts/python.exe"
   ```

   いずれか失敗したら修正する。**修正した場合は分岐元ブランチ上で commit し、上の 4 コマンドだけを回し直して (`git checkout` / `git pull` は再実行しない — ローカル commit で ahead になった状態で pull すると余計な merge を踏む) 緑を確認してから 3-2 へ進む。** commit message は `fix: <要約> [<session-id>]` とし、**push はしない** (この commit は 3-2 で切る `<hop1 head>` に含まれて hop 1 PR に乗る)。 `git stash` で退避する形は採らない — 退避すると修正が作業ツリーから消えて 3-1 が再び赤に戻り、「緑を確認してから進む」が成立しない (退避を選択肢に置くなら退避 → 復帰 → 再検証の 3 段を書き切る必要があるので、ここではその複雑さを持ち込まない)。**「3-1 が全部緑で、作業ツリーが clean」になって初めて 3-2 へ進む。**

2. **hop 1 の head ブランチ (`<hop1 head>`、Step 2-5 で決めた変数) を作成する**（3-1 で分岐元に居ることは確定済み。PR の `--base` とは**別物**なので取り違えない）。**バージョン編集より前**に行う:

   ```bash
   git checkout -b <hop1 head>
   ```

   3-1 で `git checkout <分岐元ブランチ>` / `git pull` を済ませてあるので、ここでは分岐だけを行う
   (同じ pull を 2 度書くと、どちらが正か / 片方を飛ばしてよいかが読み手ごとに割れる)。

   > **裁定で `release/vX.Y.Z` を作らない場合も本手順は飛ばさない。** `<hop1 head>` が `claude/<slug>` に解決されるだけで、コマンド列は同一である。どちらの形でも「**編集前にブランチを確定させる**」という本 step の目的は変わらない。

3. [`docs/versioning.md`](../../../docs/versioning.md) §バージョン管理場所 に挙がっている**全フィールド**の version を新バージョンへ更新する（フィールド一覧の機械可読な正は [`scripts/check_version_consistency.py`](../../../scripts/check_version_consistency.py) の `VERSION_LOCATIONS`、#911）。1 ファイルが複数フィールドを持つことがある（ファイル数 < フィールド数）ので、ファイル単位で数えて満足しないこと。lockfile (`gui/package-lock.json` / `gui/src-tauri/Cargo.lock`) は **該当フィールドの直接編集を既定**とする（バンプでは version 以外を動かさないため。依存そのものを更新したい場合はパッケージマネージャを使い、バンプとは別コミットに分ける）。このとき**旧バージョン文字列の一括置換はしない** — lockfile には依存由来の部分一致（`0.3.0` に対する `30.3.0` 等）が多数あり誤爆する。該当フィールドの行だけをピンポイントで直す。更新できたら必ず検証する:

   - **あわせて `CHANGELOG.md` の節見出しを改名する**（#952）。開発中の節は `## [Unreleased]` で、リリース時に `## [<新バージョン>] - YYYY-MM-DD` へ改名する。**日付はこの時点では暫定**でよく、タグを打つ当日に Step 4 で確定させる。**この改名を飛ばすと直後の検証コマンドが失敗する** — `check_version_consistency.py --tag` は「バージョン `<新バージョン>` の節がありません」を返す（`check_changelog_heading` は該当版の節の存在を必須にしている）。既にリリース済みのバージョン節は触らない（裁定 D7）
   - **entry の内容**は [`docs/release-process.md`](../../../docs/release-process.md) §CHANGELOG entry の記述規約 に従う。3 部構成（太字機能名 + issue 番号 / 使い方 2-3 行 / 詳細リンク）で書き、内部用語は spec 側へ寄せる。利用者から見た振る舞いが変わらない変更（CI ガード / 開発 doc / skill / テスト / 版 pin）に entry は不要
   - **entry が 1 件も無い（節が空の）場合は、それが判断の結果であることを 1 行記録する**（3 点セット②）。リリース PR 本文へ次の形で書く。無記載では「判断して不要と決めた」と「書き忘れた」が区別できない:

     ```text
     CHANGELOG entry: 本リリースは内部専用の変更のみ (対象 PR: #A #B #C) — 利用者から見た振る舞いの変化なし
     ```

     entry が 1 件以上ある場合は、**entry を持たない PR の一覧**を同じ形で記録する。各 PR 本文の `CHANGELOG entry: 不要 (内部専用 — ...)` の 1 行が根拠になる（`.github/pull_request_template.md` §関連ドキュメント / マトリクス更新）

   ```bash
   python scripts/check_version_consistency.py --tag v<新バージョン>

   # entry の書き方 (内部用語 / ### Internal 節) を検査する。CI の
   # changelog-style job と同じ判定 (exit 1 = 規約違反 / exit 2 = 構造エラー)。
   python scripts/check_changelog_style.py
   ```

   exit 0 でなければ先に進まない（exit 1 = フィールド間 or tag との不一致 / exit 2 = 検査自体の構造エラー）。`release.yml` の `version-check` job が tag push 時に同じスクリプトで同じ判定を行うため、ここを飛ばすとリリース当日に fail する。`--tag` は**期待値の文字列**を渡すだけで、git tag が既に存在する必要はない（タグ打ちは本スキル範囲外の後工程）

   > **ここが Step 0a の [§Track 構造の patch release における再評価点](#track-構造の-patch-release-における再評価点-962-項目-4) で予告した再評価点である** (#962 項目 4)。Track 構造の patch release で「Track D で達成予定」として通した §共通項目 3 件 (全 PR マージ済み / バージョン保持箇所 / CHANGELOG 対象セクション) を、この 2 コマンドの exit 0 と、**hop ごとの open PR 照会**の結果で**今ここで**再確認する。`<base>` のような未定義のプレースホルダを使わず、Step 2-4 / 2-5 で決めた値をそのまま渡す:
   >
   > ```bash
   > # hop 1 の宛先 (= Step 2-4 の表の「リリース PR の `--base`」) に未マージの PR が残っていないか
   > gh pr list --base <リリース PR の宛先> --state open --json number,title
   >
   > # hop 数 = 2 のときは hop 2 の宛先も見る (hop 1 だけ見て緑にしない)
   > gh pr list --base main --state open --json number,title
   > ```
   >
   > **本 release のスコープに属する PR** が 1 件でも open なら「全 PR マージ済み」は未達である。1 件でも未達ならリリース PR を作らない。
   >
   > 更新対象を `grep -r '<旧バージョン>' --include='*.py' --include='*.toml' --include='*.json'` で拾う旧手順は使わない。`Cargo.lock` のように上記 glob のどれにも載らない保持ファイルがあり、取りこぼす（#817 / audit P2-33 の手順を #911 で置換）

4. 変更をコミット（session-id を含める、[`docs/l2-workflow.md`](../../../docs/l2-workflow.md) §「PR 規約」 §「コミットメッセージ session-id」）:

   ```bash
   # バージョンを保持する「全ファイル」を stage する。path は手で列挙せず
   # --list-paths から得る (VERSION_LOCATIONS が正なので、保持先が増えても
   # 取りこぼさない)。--list-paths は path を重複なしで返すので、出力行数は
   # フィールド数ではなくファイル数になる (1 ファイル 2 フィールドの箇所がある)。
   # pyproject.toml だけを stage して他を置き去りにすると
   # release.yml の version-check job が fail する (#911)。
   # git add は cwd 側の repo に効くので、Step 3-3 でバンプしたのと同じツリーを
   # cwd にすること (worktree 作業中なら worktree root)。--list-paths の出力自体は
   # repo root 相対の固定文字列で cwd には依存しない
   # **`--list-paths` に CHANGELOG.md は含まれない** (実測: pyproject.toml / tauri.conf.json /
   # Cargo.toml / package.json / package-lock.json / Cargo.lock の 6 ファイルのみ)。
   # 3-3 で改名した CHANGELOG.md を明示的に足さないと、節見出しが unstaged のまま残り、
   # CHANGELOG 抜きの PR が出来て release.yml の version-check がタグ push 時に落ちる。
   git add -- $(python scripts/check_version_consistency.py --list-paths) CHANGELOG.md
   git commit -m "chore: bump version to <新バージョン> [<session-id>]"

   # commit 後に stage 漏れを検出する。合格条件 = 出力に **3-3 で編集したファイル
   # (バージョン保持 6 ファイル + CHANGELOG.md) が 1 つも現れない**こと。
   # 出力が空である必要はない (無関係な残留は可)。
   # 「バージョン保持ファイルが出ないこと」だけを条件にすると、外延を外部スクリプトに
   # 委ねているぶん CHANGELOG の漏れを見逃す
   git status --short
   ```

   バージョン保持ファイル以外の差分が残っている場合は、バンプと混ぜず別コミットに分ける
   （このコミットは version bump 単独に保つ）。**3-1 で直した lint 等はここには残らない** —
   3-1 の規約により、それらは 3-2 より前に分岐元で commit 済みだからである
   （旧版は stash / 持ち越しを想定して「3-1 で直した lint 等」を例に挙げていたが、
   その前提は 3-1 の clean-tree 規約と両立しない）

5. hop 1 の head ブランチを push:

   ```bash
   git push -u origin <hop1 head>
   ```

6. リリース PR を作成（`--base` は Step 2-4 の表の**リリース PR の宛先**。minor / major では **`main`** であって分岐元の develop ではない。Windows + Git Bash での日本語本文破損回避のため `printf | --body-file -` 方式）:

    ```bash
    printf '%s\n' "## Release v<新バージョン>

    ### 変更内容
    <コミット分析結果のサマリー>

    ### deferred issue レビュー結果
    <Step 0c の 3 択分類結果を記載>

    ### fable 俯瞰レビュー (Step 0a-2)
    <Step 0a-2 の記録行をそのまま転記。残 K 件があれば 1 件 1 行で列挙し、
     各行に (A) 本 PR 内対応 / (B) 新規 issue / (C) 既存 issue 追記 の処置を付ける。
     残ゼロなら「残 0 件」と明記する>

    ### チェックリスト
    - [ ] バージョン保持フィールドが全て一致 (\`python scripts/check_version_consistency.py --tag v<新バージョン>\` が exit 0)
    - [ ] 全テスト通過 (\`pytest\`, \`ruff check .\`, \`ruff format --check .\`, \`pyright --pythonpath <repo root の .venv の python>\`)
    - [ ] deferred issue を全件レビュー済み
    - [ ] CLAUDE.md の更新が必要な変更はない

    作成: <session-id>" | gh pr create \
      --title "Release v<新バージョン>" \
      --body-file - \
      --base <リリース PR の宛先> \
      --label "release" \
      --assignee Idios
    ```

7. **hop 数が 2 のときのみ: hop 2 の PR (`develop-<新バージョン> → main`) を作る** (#962 項目 6)。Step 2-5 の表で hop 数 = 2 に該当した場合、3-6 で作った PR は `develop-<新バージョン>` 止まりであり、**`main` にはまだ何も入っていない**。hop 1 がマージされたら続けて:

   ```bash
   # hop 1 が実際にマージされたことを確認してから hop 2 を作る
   gh pr view <hop 1 の PR 番号> --json state,mergedAt -q '"\(.state) \(.mergedAt)"'

   gh pr create \
     --title "Release v<新バージョン>" \
     --body-file - \
     --base main \
     --head develop-<新バージョン> \
     --label "release" \
     --assignee Idios
   ```

   hop 2 の PR 本文は hop 1 と同じテンプレートでよい (`### 変更内容` を hop 1 へのリンクに置き換えてよい)。**hop 2 も required status check 8 件を満たす必要がある**ので、CI 1 サイクル分をタグ打ち当日の所要時間に見込む

8. ユーザーに PR URL とバージョン変更内容を報告 (hop 数 = 2 なら **2 本ぶんの URL**)

### Step 4: CHANGELOG 見出し日付をタグ打ち日に合わせる（タグ打ちの直前、必須）

> **本 step の適用範囲を先に確定する。** 以下の本文と表は **hop 数 = 1 の構成** (minor / major と、
> `develop-<新バージョン>` を持たない patch) を前提に書いてある。**hop 数 = 2 の構成では
> 「リリース PR」を hop 2 の PR に読み替える** — hop 1 は既にマージされていてよく、その場合の
> 手順は下記 §「hop 1 マージ後・hop 2 前に日付ドリフトを見つけた場合」が正である。
> (適用範囲の切り替え条件を step の末尾に置くと、本文を先に読んだ実行者が hop 1 前提の表を引く。)

`CHANGELOG.md` の対象バージョン見出しは `## [<新バージョン>] - YYYY-MM-DD` の形をとり、**日付 = そのタグを打つ日 (JST)** とする（[`docs/release-process.md`](../../../docs/release-process.md) §タグ運用、裁定 D6 / #948）。リリース PR の作成からタグ打ちまでは日を跨ぐことがある（v0.3.0 では見出し日付が 2 回書き換わった）ため、**タグを打つ当日に**見出し日付を確認・更新して commit する。

1. `CHANGELOG.md` の `## [<新バージョン>] - ...` の日付を**当日の JST 日付**へ直す。**既にリリース済みのバージョン節は触らない**（裁定 D7）
2. 検査してから commit する:

   ```bash
   # 基準日はローカル時刻を offset 付き ISO8601 で渡す（スクリプトが Asia/Tokyo へ変換する）。
   python scripts/check_version_consistency.py --tag v<新バージョン> \
     --changelog-date-from "$(python -c 'import datetime; print(datetime.datetime.now().astimezone().isoformat())')"

   git add -- CHANGELOG.md
   git commit -m "docs: set CHANGELOG date for v<新バージョン> [<session-id>]"
   ```

   exit 0 でなければタグを打たない（exit 1 = 見出し日付 / バンプ方向の不一致、exit 2 = 検査自体の構造エラー）。**同じ検査を `release.yml` の `version-check` job がタグ push 時に実行する**ため、ここを飛ばすと*タグを打った後に*赤くなり、タグの打ち直しが必要になる

**この commit をどこへ載せるか**: リリース PR の head ブランチへ載せる。リリース PR はまだマージ前なので、この commit は同じ PR に乗って Step 2-4 で決めた**宛先**へ渡る（minor / major なら `main`。patch で `develop-<新バージョン>` を経由する場合はまずそこへ渡り、後続の `develop-<新バージョン> → main` PR で `main` に載る）。**宛先の名前は Step 2-4 の表が正**で、ここの記述で上書きしない。

**載せ方は head ブランチが保護対象かどうかで変わる**（[`docs/release-process.md`](../../../docs/release-process.md) §ブランチ保護と required status checks が保護対象の正）。

| head ブランチ | 保護 | 載せ方 |
| --- | --- | --- |
| `<hop1 head>` = `release/v<新バージョン>`（通常） | **あり** | **専用の PR を 1 本作って merge する**（下記手順） |
| `<hop1 head>` = `claude/<slug>`（`release/*` を作らない裁定のとき） | なし | 直接 commit / push してよい |
| `develop-<新バージョン>`（hop 1 マージ後、hop 2 の head） | なし | 直接 commit / push してよい (下記 §hop 1 マージ後) |

#### hop 1 マージ後・hop 2 前に日付ドリフトを見つけた場合 (#962 項目 6)

hop 数 = 2 の patch release では、hop 1 (`→ develop-<新バージョン>`) をマージしてから
hop 2 (`develop-<新バージョン> → main`) をマージするまでに日を跨ぐことがある。
このとき見出し日付が「タグを打つ日」とズレる。**タグは hop 2 のマージ後に `main` へ打つ**ので、
ズレたままだと `version-check` job がタグ push 時に落ちる。

直し方は **hop 2 の head である `develop-<新バージョン>` が保護対象かどうか**だけで決まり、
上の表と同じ判定になる:

- `develop-*` は保護対象ではない → **`develop-<新バージョン>` へ直接 commit / push してよい**。
  hop 2 の PR が open のままなら、その push が自動で PR に載る (新しい PR を作り直さない)
- 何らかの理由で `develop-*` が保護対象になっている場合は、上の「保護対象の head へ載せる手順」を
  `release/v<新バージョン>` の代わりに `develop-<新バージョン>` を base として実行する

**タグ打ちを翌日以降へ延ばす判断をしたなら、その時点で直さず、実際にタグを打つ当日に Step 4 をもう一度回す。** 「先に直しておく」と、また日を跨いだときに二重にズレる。

> **なぜ minor / major では PR が要るのか**: `required_status_checks` は PR のマージだけでなく**対象 ref への `git push` すべて**に適用される。`release/*` は保護対象なので直接 push は `GH013: Repository rule violations found` で reject される（実測。`docs/release-process.md` §対象 ref の選び方 の表）。「日付のためだけの PR は作らない」という初版の指示は**この保護の導入により無効**になった。

保護対象の head へ載せる手順:

```bash
git checkout -b claude/changelog-date-v<新バージョン> release/v<新バージョン>
# 上記 1. / 2. の編集と検査をこのブランチで行う
git push -u origin claude/changelog-date-v<新バージョン>
gh pr create --base release/v<新バージョン> --title "docs: set CHANGELOG date for v<新バージョン>" --body-file -
```

この PR も required status check 8 件を満たす必要がある。**CI 1 サイクル分（十数分）をタグ打ち当日の所要時間に見込んでおくこと。** PR 本文は通常どおり Self-Test Report を埋める（`validate-checklist` が required なので、未消化 checkbox があるとマージできない）。

> **実行順序の制約** (hop 数 = 1 の構成、= minor / major と `develop-<新バージョン>` を持たない patch): Step 4 は**リリース PR をマージする前**に実行する。**hop 数 = 2 の構成では本文は hop 2 の PR に読み替える** — hop 1 は既にマージされていてよく、その場合の手順は上記 §「hop 1 マージ後・hop 2 前に日付ドリフトを見つけた場合」が正である。`main` は保護ブランチ（`release/vX.Y.Z → main` のマージのみ受け付ける、[`docs/release-process.md`](../../../docs/release-process.md) §ルール 1）なので、マージ後に日付だけ直そうとしても直接 commit できない。**Step 4 → リリース PR マージ → タグ打ちを同じ JST 日のうちに終える**のが正しい順序で、v0.3.0 もこの順で確定させている。
>
> なお基準日を省いた `python scripts/check_version_consistency.py --tag v<新バージョン>` は、日付欄の**存在**しか見ない（値は比較しない）。Step 3 のバンプ時点ではタグを打つ日が未確定なので、そちらでは省略形で構わない。

### Step 5: security 再チェック（タグ打ちの直前、必須）

**変更していない既存依存に対して、後から公開された advisory を能動的に取りに行く工程。**

v0.3.0 では advisory 公開からタグ打ちまで **約 7 時間**の窓があり、その間に公開された undici の新規 advisory 5 件（`>= 7.0.0, < 7.29.0`）を直前に踏んだ（`0e163b8`）。PR 時点の CI は依存を触った PR でしか起動しないため、リリース直前に静止した repo は構造的に無検査になる（[`docs/ci-security-audit.md`](../../../docs/ci-security-audit.md) §構造的ギャップ 3）。

**注意: 「余裕のあるバージョンへ上げる」対策では防げない。** 上記 5 件は新規公開の GHSA で、7.28.0 に余裕があっても同じく該当した。したがって headroom 検出器は作らない（[#950](https://github.com/Idios/kobutachan-allaganeye/issues/950)）。

1. `security-audit.yml` をリリース PR の HEAD に対して実行する:

   ```bash
   gh workflow run security-audit.yml --ref <リリース PR の head ブランチ>
   gh run list --workflow security-audit.yml --limit 1
   ```

   `cargo audit` / `pip audit` / `npm audit` の 3 job が緑であること。`dependency review` は `pull_request` 以外では skip されるので、この経路では走らない（それが正しい）。

2. Dependabot alert の open 分を直接確認する:

   ```bash
   gh api repos/Idios/kobutachan-allaganeye/dependabot/alerts --paginate \
     -q '.[] | select(.state=="open") | [.number, .security_advisory.severity, .dependency.package.name, (.security_vulnerability.first_patched_version.identifier // "NONE")] | @tsv'
   ```

   **`?state=all` を付けてはいけない。** `all` は本 API の有効値ではなく、無効値は 422 ではなく **HTTP 200 + 空配列**で返る（`state=bogusvalue` と挙動が一致する。2026-08-20 実測）。つまり「alert ゼロ」に見える緑が作れてしまう。state は絞らず、上記のとおり `jq` 側で `select(.state=="open")` する。

3. 未対応の open alert が残る場合は、タグを打つ前に Idios へ提示して「修正してから出す / 既知として出す」を判断してもらう。

**実施しなかった場合の記録義務**: 本 Step を実行しなかったときは、リリース PR 本文へ 1 行だけ理由を残す（[`.claude/skills/review-pr/SKILL.md`](../review-pr/SKILL.md) の `Codex review 起動: 非対象 (理由: …)` パターンの踏襲）。

```text
security 再チェック: 非実施 (理由: …)
```

**無記載を許さない。** 記録が無いと「実施して緑だった」と「そもそも実施していない」が区別できず、後から監査できなくなる。

#### この工程が見ていない集合

- **再チェックからタグ push までの窓は 0 にできない。** 本件の実測窓は advisory 公開からタグまで**約 7 時間**
- **Dependabot alert 経路は既定ブランチ（`main`）しか scan しない。** release 期間中は stale な状態を読む（[`docs/ci-security-audit.md`](../../../docs/ci-security-audit.md) に既記載）
- **`security-audit.yml` の `schedule: cron` は daily なので、最悪 24h 遅延する。** さらに cron は **`main` 上の workflow ファイルでしか有効にならない**ため、develop へ入れただけでは 1 度も走らない

### タグ打ち・GitHub Release 作成

リリース PR マージ後の手順。**タグを打つ操作そのものは本スキルの範囲外** (`docs/release-process.md` §タグ運用 が正) だが、
**タグ push 後の `release.yml` 完了確認は本スキルの gate である** — Step 2-6 が「`develop-<次バージョン>` を切ってよいか」の
判定にこの確認結果を使うため。「範囲外」を全体に掛けて完了確認まで user 任せにしない:

- patch リリース: マージされたブランチで `git tag -a v<新バージョン> -m "Release v<新バージョン>: <概要>"` → `git push origin v<新バージョン>`
- minor/major リリース: `develop-<新バージョン>` を `main` にマージしてから `main` でタグ打ち
- **annotated tag（`-a`）で打つ**。`version-check` job は CHANGELOG 見出し日付の基準日として annotated tag の `taggerdate` を第一候補に読む
- **GitHub Release は `git push origin v<新バージョン>` で [`release.yml`](../../../.github/workflows/release.yml) が自動作成する**。本文は [`scripts/extract_release_notes.py`](../../../scripts/extract_release_notes.py) が CHANGELOG.md の該当セクションから抽出し、Portable ZIP も自動添付される
  - **`git push` はトリガであって完了ではない (#962 項目 7)。** `release.yml` はタグ push を trigger に**非同期**で走り、Windows ビルド + PyInstaller + FFmpeg DL を含むため十数分かかる。push した時点を「Release 作成済み」と扱うと、`develop-<次バージョン>` を切る判断 (Step 2-6) が実際の完了より先に出る。**次の 2 つがどちらも通ってから**先へ進む:

    ```bash
    # 1. workflow の完了を待つ (失敗したらここで非ゼロ exit する)
    gh run watch "$(gh run list --workflow release.yml --event push --limit 1 --json databaseId -q '.[0].databaseId')" --exit-status

    # 2. Release 実体と成果物の添付を確認する (assets が空なら ZIP が付いていない)
    gh release view "v<新バージョン>" --json name,isDraft,assets \
      -q '"\(.name) draft=\(.isDraft) assets=\(.assets | length)"'
    ```

    `gh run watch` が非ゼロで返る / `assets=0` / `draft=true` のいずれかなら、**`develop-<次バージョン>` をまだ切らない**。原因を潰すか、[`docs/release-process.md`](../../../docs/release-process.md) §手動リリース手順 (CI 迂回) に従う
  - 手動で `gh release create ... --notes-from-tag` を叩かない（#918 item4）。Release が二重作成されるうえ、`--notes-from-tag` はタグメッセージを本文にするため CHANGELOG の内容が反映されない
  - CI 障害等で手動作成が必要な場合のみ、[`docs/release-process.md`](../../../docs/release-process.md) §手動リリース手順 (CI 迂回) に従う（Actions の一時無効化を含む手順一式がある）
