# v0.3.1 patch release 設計書 — v0.3.0 retrospective の機構化 + deferred 27 件の吸収

- **status**: draft (Track 0 spec、Idios レビュー待ち)
- **作成日**: 2026-08-05
- **対象リリース**: v0.3.1 (patch)
- **base ブランチ**: `develop-0.3.1` (= `aefcb8c` = v0.3.0 タグと同一 commit)
- **Track 構造**: [`docs/release-process.md` §Patch release の Track 構造](../../release-process.md#patch-release-の-track-構造)
- **前例**: [2026-05-17-v020-v021-retro-codex-integration-design.md](2026-05-17-v020-v021-retro-codex-integration-design.md) (v0.2.1 Track 0)

## 1. 背景

v0.3.0 は 2026-08-04 にリリースされた (タグ `v0.3.0` = `aefcb8c`)。本 spec は次の 2 つを 1 本で扱う。

1. **v0.3.0 開発・リリース工程の retrospective の機構化** — 7 事象を観測した。うち 6 事象は GitHub issue を持たない
2. **deferred 27 件の吸収設計** — `/release` Step 0b / 0c / 0c-2 で open 65 件を全件分類し、27 件を (a) 次 release 吸収と判定した

v0.3.1 のスコープは Idios 指示による。

> 次のバージョンは 0.3.1 とする。README の更新漏れと、deferred になっている issue を棚卸して軽微な問題として残っているものを処理する。またもしセキュリティ指摘が発生したらその対処も行う。基本的に機能追加は行わない。

本 spec には**成立の前提**がもう 1 つある。モデルルーティング spec [2026-07-14-per-use-case-model-routing-design.md](2026-07-14-per-use-case-model-routing-design.md) §8 が、次の retrospective 条項を残していた。

> **retrospective 条項**: v0.3.0 リリース後（または導入から数週間後）に fable-consult / worker の実呼び出し実績を振り返り、形骸化していれば hook 強制化 or 廃止を再検討する。アドバイザリ運用（hook 見送り）の再評価点をここに固定する。

事象 1 (§3.2 E1) はこの条項の消化そのものである。

## 2. 範囲・非範囲

### 2.1 範囲

- v0.3.0 で観測した 7 事象の**全件機構化** (裁定 D1)
- deferred 吸収 27 件の Track 割り当てと直列制約の確定
- 上記を実行するために先に決めておく必要のある 12 の裁定 (§4)
- `/release` Step 0c が要求する **deferred 全件検証結果 table** (§9、27 + 38 + 2 = 67 行)

### 2.2 非範囲

- **機能追加** — Idios 指示による。CLI / GUI の新オプション・新画面は本 release では扱わない
- **L3 検出系の継続開発** — #480 / #753 / #809 / #861 / #866 / #867 / #921 / #925 は deferred 継続 (§9)
- **L4-L6 レイヤー** — 未着手のまま
- **cv2 5.x への移行** — 裁定 D8 で 4.x 固定。5.x 移行は別 issue として起票し deferred
- **実装そのもの** — 本 spec は裁定と分解のみを行う。`.claude/skills/**` および `docs/**` の実編集は Track B、CI job の追加は Track C が担う (理由は §6.1)

## 3. v0.3.0 retrospective サマリ (実測検証結果)

### 3.1 検証方法

7 事象は当初、記憶と PR 本文をもとに記述されていた。spec に載せる前に、**12 エージェントによる並列調査**で 1 件ずつ repo の実態と突き合わせた (worktree 隔離 / read-only、657 tool use)。判定は次の 4 値。

- `CONFIRMED` — 主張が実ファイル・実データと一致
- `PARTLY_CONFIRMED` — 構造的主張は成立するが実測部分に誤りがある
- `REFUTED` — 主張が実態と矛盾する
- `UNVERIFIABLE` — repo からは原理的に検証できない

**その結果、7 事象のうち 5 事象で主張の一部が覆った。** 本 spec は訂正後の事実に基づく。この検証自体が memory `feedback_codex_findings_need_measurement` (「レビュー finding は実測してから直す」) の適用例である。

### 3.2 7 事象の検証結果

| # | 事象 | 判定 | 実測で確定した内容 |
| --- | --- | --- | --- |
| E1 | Fable が呼ばれない | PARTLY | 「1 度も呼ばれなかった」は**誤り** (実質レビュー 4 回)。ただし `.claude/skills/` 全 7 と `.claude/hooks/` 全 4 に `fable` は **0 hit** で、発火点は 1 つも存在しない |
| E2 | Pre-flight を直前に回さず #938 を見落とした | PARTLY | 事象は 1 次資料で確定 (66 分の乖離)。ただし**当該時間帯に base HEAD は不動**で、「base OID 比較」案は本件に対し false-green |
| E3 | `release/*` base の PR で CI が起動しない | PARTLY | 「Track D の最終 release PR で問題になる」は**逆**。#924 は 18 check 全て緑。穴が開いたのは**流し込む側の 11 本** |
| E4 | doc スイープの軸のズレ | PARTLY | 出荷物 2 件の誤りは確定。ただし README.txt は v0.1.x ではなく **v0.2.0 の機能セット**。真因は「軸の不在」ではなく **file set が仕様書に限定されていた**こと |
| E5 | CHANGELOG 見出し日付を検査する仕組みがない | **CONFIRMED** | 4 要素すべて一致。加えて「見出し日付が何の日付か」という**規約自体が未定義** |
| E6 | companion script の出力が末尾しか残らない | PARTLY | **原因帰属が誤り**。全文は job log に永続化されている。欠けているのは**読む規定** |
| E7 | 境界ちょうどの依存バージョンは再 open しうる | PARTLY | **因果が成立しない**。新規 advisory の範囲は `< 7.29.0` なので余裕があっても該当した |

### 3.3 主張が覆った 5 点 (詳細)

#### E1 — Fable は 4 回呼ばれていた。問題は「発火点がない」ことだけ

transcript 実測で `subagent_type: "fable-consult"` の起動は計 8 回、うち導入時の AC 検証 probe 4 件を除く**実質レビューは 4 回**であった。

| 日時 (UTC) | 用途 |
| --- | --- |
| 2026-07-16 06:32 | #893 minimap crop GUI 統合 spec のユーザーレビュー前 |
| 2026-07-31 01:55 | doc-resync branch の final whole-branch review |
| 2026-08-02 08:33 | v0.3.0 リリース直前 blocker (PR #930) の俯瞰レビュー |
| 2026-08-03 13:01 | タグ打ち直前の v0.3.0 リリース記述 俯瞰レビュー |

4 回とも **`/review-pr` / `/iterate-review` のループ外**で、主エージェントの裁量による ad hoc 起動である。一方 Codex adversarial-review は同期間で 50 回以上起動している。

なお比率 (4 対 50) は spec の判断根拠に**使わない**。memory `feedback_jsonl_command_regex_escaped_quotes` のとおり JSONL の `"command"` を正規表現で数える手法は `cd` 前置形や escaped-quote を跨げず系統的に過少計上するため、50 は下限値にすぎない。判断根拠として使えるのは次の構造的事実だけである。

- `grep -rni "fable" .claude/skills/ .claude/hooks/` → **0 hit** (skill 7 本 / hook 4 本)
- 対して Codex は `.claude/hooks/session-start.sh:56` の Iron Law 6 Pre-flight Step 5 として毎セッション注入され、`docs/l2-workflow.md:193` で「**常時 (Pre-flight Step 5 必須実行)**」と定義されている
- routing spec 自身が §6 で「`/review-pr`・`/iterate-review` skill 本体の改修はしない（Fable の pipeline 組込みは別途検討）」と明記しており、**未組込みは漏れではなく意図的な保留**であった

**副次発見 (新規)**: user-level にも同名 `fable-consult` が存在する (`C:/Users/idios/.claude/agents/fable-consult.md`、2026-07-31 作成、`model: fable`)。routing spec §8 は「`fable-consult` は user-level に同名が無いため prefix なし」と前提していたが、現時点で成立しない。**#889 で worker に適用した precedence 非依存化 (`allaganeye-` prefix) が fable-consult だけ未適用**であり、memory `feedback_no_samename_precedence_reliance` が禁じた「同名 precedence 依存」が残存している。

#### E2 — base OID 比較では本件を検出できない

PR #939 は Pre-flight Step 0 / 4 を 13:07 UTC に実行し、PR を 14:13 UTC に作成した。その間の 13:50 UTC に open になった #938 を見落とし、`CHANGELOG.md` と `docs/cli-spec.md` の 2 ファイルで衝突した (merge commit `66223b8` のメッセージと PR 本文 §6 に自白記録あり)。

**しかしこの 66 分間、`release/v0.3.0` の HEAD は 1 度も動いていない。** #930 / #931 / #932 の merge は 12:34 UTC、次の merge は #938 の 14:21 UTC である。したがって:

- **「Pre-flight 時に記録した base OID と PR 作成時の OID が一致するか」を検査しても green になる**
- 本件を捕まえられるのは **open-PR 集合の再サンプリング**だけである

実装が楽な OID 比較だけを入れて「対策済み」とするのは典型的な false-green であり、本 spec はこれを明示的に禁じる (§5.5 の設計制約)。

なお「base OID を記録する仕組みが無い」という当初の主張も不正確で、`.github/pull_request_template.md:67` に `- PR 作成時の base HEAD: <sha>` の plain bullet が既に存在する。欠けているのは**検証**であり、`docs/l2-workflow.md:208` が「plain bullet は validate-checklist が無視するため **CI ゲートは増設しない**」と意図的に宣言している。

#### E3 — 穴は release PR ではなく「流し込む側の 11 本」

`ci.yml:10-13` の trigger は `push: branches: [main, "develop-*"]` / `pull_request: branches: [main, "develop-*"]` である。GitHub の branches filter は PR の **base** に適用される。

- **release PR #924** は base=`main` / head=`release/v0.3.0` なので **18 check が全て走り緑**であった
- 実際に無検査だったのは `release/v0.3.0` を base とする **11 本** (#927 / #929 / #930 / #931 / #932 / #938 / #939 / #940 / #941 / #942 / #943)
- 例: **#938 は Python 実装 3 ファイル + テスト 3 ファイルを変更しながら `validate-checklist` 1 個しか走っていない**
- `markdownlint.yml:5` も同一 filter のため、#932 (13 個の .md) / #943 (CHANGELOG.md 単独) が無検査で通った
- **main に required status checks が存在しない** (branch protection の当該 API が 404、ruleset 0 件)。この欠落を止めるゲートは repo 上に無い

#### E6 — 全文は保存されている。読む規定がない

`codex-companion.mjs` は review 出力の**全文**を永続化している。

- `<CLAUDE_PLUGIN_DATA>/state/<slug>-<hash>/jobs/<jobId>.log` に "Final output" ブロックとして rendered 全文を append (`tracked-jobs.mjs:179`)
- `<jobId>.json` に `rendered` + `result` を保存 (同 158-168)
- 2026-07-20 の実 job log をディスク上で確認済み

真の欠落は、**docs / skill のどこにも保存先 log を読む規定がなく、`docs/l2-workflow.md:872-893` の擬似コードが `result.stdout` / `result.stderr` しか参照していない**ことである。

**副次発見**: `review` / `adversarial-review` の `--background` と `--wait` は**両方とも silent no-op** である。`handleReviewCommand` (`codex-companion.mjs:709`) は無条件に `runForegroundCommand` を呼び、`--background` は `:685` で宣言されるだけで読み出しは `handleTask` (`:758`) のみ。`docs/l2-workflow.md:193` の「`--background` + `run_in_background` で非同期化可」という記載は実装と食い違っており、同じ誤りが memory `project_codex_adversarial_review_direct_invocation` にもある。

#### E7 — 「境界ちょうどだから再 open した」という因果は成立しない

undici の 5 件は 2026-08-03 19:19-19:34 UTC に**新規公開**された GHSA (high×1 / medium×4) で、範囲は `>= 7.0.0, < 7.29.0` である。

- したがって 7.28.0 に「余裕」があっても (例: 7.24.0 が境界で 7.28.0 に居ても) 同じく該当した
- 7.28.0 を patched 境界にしていたのは 2026-06-18/19 公開の**別 8 件**で、これらは今も `< 7.28.0` のまま
- **「余裕のあるバージョンへ上げる」対策は本事象を防げない**

さらに現在の pin は 3 件とも **headroom がゼロ**である。

| 依存 | 現 pin | 上げ先 |
| --- | --- | --- |
| undici | 7.29.0 (`gui/package-lock.json:4220-4222`) | 7.x 最終版。jsdom が `^7.24.5` を要求するため 8.x へ行けない |
| vite | 8.0.16 (`gui/package.json:48`) | 8.0.x 最終版。8.1.0 への bump は #836 で Idios が却下済み (over-bump) |
| serde_with | 3.21.0 (`gui/src-tauri/Cargo.lock:3336-3337`) | crates.io の max_version |

**headroom 検出器を fail 型で導入すると、導入初日から解消不能な恒久 red になる。** これは false-green より悪い「override の常態化」を招く。

**訂正の記録**: `commit 0e163b8` の message に「範囲が `< 7.28.0` から `<= 7.28.0` へ拡大」という誤った記述が残存している (`CHANGELOG.md:257-258` は訂正済み)。

### 3.4 引き継ぎ資料の件数誤り

deferred 棚卸しの引き継ぎ資料は吸収を「26 件」と記載していたが、`comm` による機械突合の結果は次のとおり。

- **open 65 件** (deferred 64 + 非 deferred 1 = #944)
- **吸収 27 件** (資料の `### その他 (4 件)` が実際は 5 件だった)
- **継続 38 件**

## 4. Track 0 で確定した裁定

本 spec が確定させる 12 の裁定。以降の設計と Track 割り当てはすべてこれに従う。

| ID | 裁定 | 根拠 / 影響 |
| --- | --- | --- |
| D1 | **7 事象すべてを v0.3.1 で機構化する** | Idios 判断。Track C が厚くなることを許容 |
| D2 | **CI で直接検査できない行為は Self-Test Report の必須申告 + CI 強制で押さえる** | E1 / E2 / E6 の共通解。#936 を (a) で決着させることが前提 |
| D3 | **プロセス・規約改修は変更の性質で既存 4 Track に分配する (Track E を新設しない)** | 併せて Track B の定義「deferred **UX** 吸収」を「deferred 吸収」へ修正 (#918 隣接の doc fix) |
| D4 | **v0.3.1 は `release/v0.3.1` 統合ブランチを使わず `develop-0.3.1` 直行とする** | 全 PR で full CI が自動的に走り E3 の穴が構造的に消える。v0.2.1 実績 (#773) および `release/SKILL.md:110-111` と一致 |
| D5 | **受け入れゲート §共通項目 を patch にも適用する** | `docs/release-process.md:85,87` の「各 minor リリース」「全 minor リリース」を「各リリース (minor / patch)」へ改める |
| D6 | **CHANGELOG 見出し日付 = タグを打つ日 (JST)** | 過去 4 タグすべてがこれと一致 (v0.1.1 04-20 / v0.2.0 05-16 / v0.2.1 05-17 / v0.3.0 08-04) |
| D7 | **CHANGELOG に `## [Unreleased]` 節を新設し、Track A-C の各 PR はそこへ追記する** | Track D が version 見出しへ確定させる。既リリース済み節を触らせない |
| D8 | **cv2 は 4.x 固定 (`opencv-python-headless>=4.8,<5`)** | 実機検証・baseline 再取得が不要になり、ローカル (4.13) / CI / 出荷物の 3 者が初めて一致する。**5.x 移行は Track 0 で別 issue を起票して deferred** (GT / bit-exact baseline 再取得が要るため patch には載せない) |
| D9 | **#936 (a) のブロッキング範囲は Self-Test Report のみ (10 box)** | Iron Law 1/3/4 群は heading filter の完全一致に掛からないため自動ではブロッキング化しない |
| D10 | **E1 / E2 / E3 / E5 / E6 / E7 を個別 issue として起票する** | 実装計画の PR 表が open issue と 1:1 になる。#870 が問題にする「番号を持たない別 issue 宣言」を spec 自身が再生産しない |
| D11 | **EPT (empirical-prompt-tuning) は振る舞い変更を伴う skill 改修のみに適用する** | 対象 = #935 (判断基準の置換) / #918 (手順変更) / E1 (Fable step 新設)。#856 (語彙統一 4 箇所) は skip し、根拠を PR 本文に明記 |
| D12 | **#326 は別 repo (`Idios/idios-claudecode-tools`) へ転記し、本 repo の #326 は close する** | 本 repo 側に実行できる作業が存在しない。別 repo への起票は Idios が行う。**順序制約 (Idios 判断 2026-08-05)**: 転記は skill / hook / CLAUDE.md 等の基本ドキュメントが固まってから。本 release でそれらを書き換えるのは **#945 / #935 / #856 / #870 / #918 の 5 件**であり、**転記の条件はこの 5 件すべてのマージ後**である。条件を Track で表現しないこと — #918 は `check_version_consistency.py:268` の `args.tag` 分岐を #948 と共有する都合で他 4 件と別 Track に置かれており、「Track B 完了後」と書くと #918 を取りこぼす (Codex Round 1 で実際に検出された)。5 件を載せる PR は [実装計画](../plans/2026-08-05-v031-track-decomposition.md) を参照。固まる前に転記すると転記先テンプレートが旧版を写す |

## 5. 設計

7 事象と 27 issue を横断すると処方は **4 つの根本原因**に収斂する。事象ごとに節を立てると同じ処方を 7 回書くことになるため、根本原因ごとに設計し、事象は各節の実証事例として引用する。

### 5.1 G1: 宣言はあるが発火点がない (advisory-only)

#### 該当

E1 (routing がアドバイザリで skill / hook に 0 件) / E5 (見出し日付の規約が存在しない) / E7 (security 再チェックが受け入れゲートに 1 項目もない) / #936 (Self-Test Report が 10 箇所で「CI 強制」と書かれて実際は非強制) / #870 (triage 入力規範節が存在しない) / #935 P2-3 (異常観測の記録規約なし) / #865 (凍結継続が明文化されていない)

#### G1-1: 「規約導入 3 点セット」を 1 本の条文にする

**問題**: #918 item3 / #912 / #910 / #658 / #876 / #934 の **6 件が同じ要求を別々に書いている**。「新ガードは発火実証まで」という同一の規律が、issue ごとに毎回書き直されている。

**ファイル**: `docs/l2-workflow.md` に新節「規約・ガード導入の 3 点セット」

**変更内容**: 規約 / ガード / チェックを新設するときは次の 3 点を必ず揃える。

1. **発火点** — skill step / CI job / hook のいずれかを、**ファイルと行を指定して**書く。「doc に書いた」だけでは発火点にならない
2. **非実施時の 1 行記録義務** — 実施しなかった場合に理由を 1 行残す義務を課す。既存 reference は `.claude/skills/review-pr/SKILL.md:244-248` の「Codex review 非起動なら `Codex review 起動: 非対象 (理由: …)` を Step 6 に明記」
3. **発火側の red 実証** — 違反を一時注入して **exit code の生値**で発火を観測し、pin test を同梱する。memory `feedback_protective_mechanism_red_verification` の hook 昇格

**参照契機 (誰がいつ引くか)**:

- **`/review-pr` Step 5**: PR が CI job / hook / skill step を新設している場合、本節の 3 点セットに照らして逐条検証し、欠けていれば Step 5b トリアージ表に計上する
- **`superpowers:brainstorming`**: 再発防止機構を設計する creative work で本節を引き、3 点セットを設計に織り込む
- **`/create-task`**: `[task]` / `[refactor]` prefix で「ガードを追加する」issue を起票する際、受け入れ条件に 3 点セットを反映する
- **CLAUDE.md** §開発ワークフロー に 1 行リンクを置く (発見可能性確保)

**受け入れ基準**:

- `docs/l2-workflow.md` に本節が存在し、3 点セットが番号付きで明記されている
- #918 item3 / #912 / #910 / #658 / #876 / #934 の各 PR が個別に「red 実証まで」を書き直さず、本節を参照する形になっている
- 上記 4 経路のうち少なくとも 3 経路から本節への明示リンクが存在する

#### G1-2: Fable の発火点を作る (E1)

**ファイル**: `.claude/skills/release/SKILL.md` / `.claude/skills/review-pr/SKILL.md` / `.claude/agents/fable-consult.md` / `CLAUDE.md` §モデルルーティング

**変更内容**:

1. `/release` に **Step 0a-2「リリース俯瞰レビュー (fable-consult) 必須」** を新設する。Step 0a (受け入れゲート確認、`SKILL.md:22-32`) の直後、Step 0b (deferred 取得) の前に置く。対象は CHANGELOG / release notes / 受け入れゲート達成状況。**finding を Track D の PR 本文へ転記する義務**まで含める (「実行した」だけで緑になるのを防ぐ)
2. 非起動の場合は理由を 1 行明記する (G1-1 の 3 点セット②、`review-pr/SKILL.md:244-248` パターンの踏襲)
3. `/review-pr` に **doc-only PR / spec doc 新規追加 PR では fable-consult を起動する**条件を追加する。既存の「optional Codex review」(`review-pr/SKILL.md:234-248`) と同じ条件付き起動 + 非起動記録の形にする
4. **`fable-consult` を `allaganeye-fable-consult` へ改名する**。user-level に同名が実在するため、#889 で worker に適用した precedence 非依存化を fable-consult にも適用する。CLAUDE.md §モデルルーティング の対応表と `fable-consult の推奨トリガー地点` 節、routing spec §8 の前提記述も同時更新する
5. 呼び出しの有無を **Self-Test Report の必須フィールド**にする (D2、G1-4 と連動)

**false-green の明示**: `/release` Step 0a は「達成 / 未達成 / **該当なし**」の 3 択なので (`.claude/skills/release/SKILL.md:27`)、「該当なし」で通過できる。**finding 件数と消化件数の数値記入を required にしない限り no-op** である。この制約を skill 本文に明記する。

**受け入れ基準**:

- `grep -rn "allaganeye-fable-consult" .claude/skills/` が `release` と `review-pr` の両方で hit する
- `.claude/agents/fable-consult.md` が存在せず `.claude/agents/allaganeye-fable-consult.md` が存在する
- `grep -rn "fable-consult" CLAUDE.md docs/` の全 hit が新名を指す (旧名の残存 0 件)
- Self-Test Report に Fable 起動欄が存在し、未記入で `validate-checklist` が red になることを実証済み (G1-4)

#### G1-3: CHANGELOG 見出し日付の規約と検査 (E5)

**ファイル**: `docs/release-process.md` §タグ運用 / `scripts/check_version_consistency.py` / `.github/workflows/release.yml` / `tests/scripts/`

**変更内容**:

1. **規約を先に確定する** (D6)。`docs/release-process.md` §タグ運用 に「CHANGELOG 見出し日付 = タグを打つ日 (JST)」を 1 行で定義し、§共通項目 のチェックリスト項目を「対象バージョンセクションが存在 (日付 = タグ打ち日 JST / 主要変更点 / breaking changes)」へ具体化する
2. `.claude/skills/release/SKILL.md` の §タグ打ち・GitHub Release 作成 の直前に「見出し日付を当日に更新して commit する」手順を追加する。**現在 skill 全体で `changelog` の grep hit が 0 件**であり、`docs/release-process.md:81` の「/release スキルは CHANGELOG 更新の支援に使う」が実体を伴っていない乖離も同時に解消する
3. `scripts/check_version_consistency.py` に `_check_changelog_heading()` を追加する。`--tag` 指定時のみ発火。`--changelog-date-from <ISO8601>` を CLI 引数で受け、workflow 側が `${{ github.event.head_commit.timestamp }}` を渡す (単体テスト可能な形にする)
4. `scripts/extract_release_notes.py:13` の regex を日付必須へ厳格化し、`tests/scripts/test_extract_release_notes.py` を新設する (現在この script には対応テストが存在しない)

**タイムゾーンの扱い (必須)**: GitHub Actions runner は既定 UTC である。**過去 4 タグ中 2 件 (v0.1.1 02:55 JST / v0.2.1 08:43 JST) で JST 日付と UTC 日付が 1 日ずれる。** naive 実装は 50% の確率で false-red を出し、リリース当日にタグを打ち直す羽目になる。

- 比較前に `zoneinfo` で `Asia/Tokyo` へ**明示変換**する。ハードコードした TZ を docstring と `docs/release-process.md` に規約として明記する
- **JST 深夜値を流して赤/緑の両方を観測する pin test を同梱する** (G1-1 の 3 点セット③)

**Track D の critical path**: 本ガードは Track D で初めて発火する。TZ バグがあると**リリース当日に直列最後の PR が止まる**。Track C 実装時に必ず red 実証を済ませること。

**受け入れ基準**:

- `docs/release-process.md` §タグ運用 に日付規約が 1 行で存在する
- `check_version_consistency.py --tag` が日付不一致で非ゼロ exit する (偽の日付を注入して exit code 生値で確認)
- JST 深夜 (00:00-09:00 JST) のタグ timestamp で false-red が出ないことを pin test で確認済み
- `tests/scripts/test_extract_release_notes.py` が存在し、日付なし CHANGELOG で `SystemExit` することを assert している

#### G1-4: Self-Test Report の CI 強制 (#936、D2 / D9)

**ファイル**: `.github/scripts/check-pr-checklist.js` / `.github/scripts/check-pr-checklist.test.js` (実際に変更するのはこの 2 つ。`.github/pull_request_template.md` と `docs/l2-workflow.md` は (a) 採用により記述が正しくなるため**変更しない**)

**問題の精密化**: checker が Self-Test Report を見ない原因は heading 正規表現だけではない。

- `check-pr-checklist.js:26` の `stripped.split(/^##\s+/m)` は `##` の直後に空白を要求するため `#### Self-Test Report` にマッチしない。h4 節は親 h2 (`## PR チェックリスト`) の本文として吸収される
- `check-pr-checklist.js:31` の heading filter `/^(受け入れ条件|acceptance\s+criteria)\s*$/i` は**完全一致**である
- 実測: 受け入れ条件を `[x]` で埋め、`#### Self-Test Report` に `- [ ]` を 3 件置いた本文を渡すと `{"unchecked":0,"checked":1,"hasAnySection":true}` を返し **CI pass** する

**変更内容 (3 点セットで初めて発火する)**:

1. section 分割を **heading level 準拠**にする (#936 の実装時に訂正。当初案は `split` を `/^#{2,4}\s+/m` へ緩めるだけだったが、実測により却下した。下記「実装時の訂正」参照)
2. heading filter に `Self-Test Report` を **prefix match** で追加する (実際の heading は `#### Self-Test Report (machine-verified — 全件 [x] で validate-checklist 通過)` と括弧書きが付くため `\s*$` の完全一致では拾えない)
3. `check-pr-checklist.test.js:45` の pin test を反転する

**実装時の訂正 (#936 実装 PR、Idios 裁定)**: 当初案の「`split` を `/^#{2,4}\s+/m` へ緩める」は、テンプレート本文では意図どおり動くが**実在の PR 本文には届かない**ことが実測で判明したため、**heading level 準拠の section 抽出**へ変更した。section は「自分と同じか浅いレベルの次 heading」で終わる。

- 直近 merged 25 本のうち **7 本** (#909 #914 #915 #917 #924 #926 #927) は `## Self-Test Report` + `### machine-verified` の形で、素朴な h2-h4 split では counted 0 box = **新 gate が無発火のまま**だった
- **#956** の形 (`## 受け入れ条件` の中に `### 実装計画 PR-A2 の受け入れゲート` 小見出し) では、素朴な split が既存 AC gate を **13 box → 0 box** に縮小させた (silent な gate 縮小)
- heading level 準拠なら、h2 節は配下の h3/h4 を本文として吸収する (= 現行の AC 挙動を厳密保存) 一方、h4 `#### Self-Test Report` は兄弟 h4 `#### 関連ドキュメント` で終わる (D9 の 10 box に収まる)
- 副作用として、h2 `## Self-Test Report` 配下の `### machine-unverifiable` 小見出しも吸収される。同節は規約上 plain bullet `-` で書くため実害はない (実在 25 本すべてで plain bullet、checkbox の使用はゼロ)

**counter のレンダリング整合 (Codex adversarial-review で摘出、同 PR 内で修正)**: gate の対象節が増えるぶん、「GitHub が実際に描画するもの」と counter のズレも影響が広がるため、以下 2 点を同時に硬化した。実測で直近 merged 25 本 + テンプレートのカウントは硬化前後で全ファイル一致する (挙動中立)。

- **HTML コメント除去** ([high] false-green): 描画されないコメント行が heading とみなされて節を打ち切り、その後ろの**可視の**未消化 checkbox が数から漏れていた。base 実装でも `## 受け入れ条件` 節で同じ入力から再現する既存穴
- **task list marker の整合** ([medium] false-green + false-red): `*` / `+` / `1.` / `1)` の checkbox も数える一方、**行中**の checkbox 記法 (文中の言及やコードスパン内の記入例) は数えない。後者を数えると、この checker 自身を説明する PR 本文が誤って red になる

**近似境界 (WONTFIX、Idios 裁定)**: この checker は Markdown parser ではなく regex 近似である。round 3 で「4 space / tab インデント行は Markdown では indented code block なので task item として数えるべきでない (false-red)」が挙がったが、**個別 patch を止めてここで境界を引く**判断をした。根拠は 3 点。

1. 深インデントの task item は実在 25 本 + テンプレートで **0 件**
2. 誤りの向きが **false-red** = 失敗メッセージが見えて自己修正できる。黙って通す false-green より安全
3. 推奨どおりインデントを 0-3 space に制限すると **4 space 以上の入れ子 checkbox が数から漏れる** (false-green 化)。行文脈を見る heuristic も「親項目 → 継続段落 → 入れ子」の形で逆向きの穴を作る

したがって gate は「レンダリング完全一致」ではなく「**false-green を避け、false-red 側に倒す近似**」と定義する。近似が見ていない集合は実装 PR 本文に列挙し、必要になった時点で parser 化 (別 issue) を検討する。

**blast radius (D9)**: テンプレートの `- [ ]` は実測で計 22 box ある (受け入れ条件 2 / Iron Law 1 が 2 / Iron Law 3 が 2 / Iron Law 4 が 1 / Self-Test Report 10 / 関連ドキュメント 5)。heading filter は受け入れ条件側が完全一致のままなので、**Iron Law 1 / 3 / 4 と関連ドキュメントの 4 群・10 box はカウント対象にならない** (`### Iron Law 1: 受け入れ条件検証` は prefix/suffix 付きのため完全一致で弾かれる)。新規に required になるのは **Self-Test Report の 10 box のみ**である。テンプレート本文を通した実測でも 22 box 中 **12 box** (受け入れ条件 2 + Self-Test 10) のみが gate 対象で、この数値は test で固定した。

**false-green の明示**: **split だけ直しても no-op である。** 1 行直して緑になるので、実装者がそこで止まらないよう本 spec と issue に 3 点セットを明記する。さらに上記の訂正のとおり、**テンプレート本文だけで発火実証を済ませると「実在本文には届かない gate」を出荷しうる** (7/25 が無発火だった)。発火実証は実在 PR 本文の形でも行うこと。

**文書側 (10 箇所)**: `docs/l2-workflow.md` L140 / L287 / L345 / L349 / L353 / L359 / L362 と `.github/pull_request_template.md` L72 / L77 / L78 が「CI 強制」を主張している。(a) を採るのでこれらは**正しくなる**ため書き換え不要。ただし正しい記述 (`template` L58 / L103 / L106、`l2-workflow.md:208` の「plain bullet は無視される」) は事実なので触らない。

**#935 との相互作用**: (a) を採ると `docs/l2-workflow.md:287` の「(C) 強制 skip (Self-Test Report の `[ ]` を残し validate-checklist で fail させる)」が**初めて実際に CI red を生む経路**になる。#935 P2-3 の「説明がつくまで pass と記録しない」規約と作用が重なるため、両者は同一 Track で整合を取る。

**受け入れ基準**:

- Self-Test Report に `- [ ]` を 1 件残した PR body で `check-pr-checklist.js` が非ゼロ exit する (実注入で確認)
- Iron Law 1/3/4 群に `- [ ]` を残しても pass することを pin test で固定 (D9 の範囲を回帰から守る)
- `#### Self-Test Report (…)` の括弧書き付き heading が prefix match で拾われることを test で固定
- 実在 merged PR 本文 (直近 25 本) を通して false-red が 0 件であること (gate 拡大で既存の書き方が red 化しないことの対照実験)
- `## 受け入れ条件` 配下に小見出しを持つ本文 (#956 の形) で既存 gate が縮小しないことを pin test で固定

#### G1-5: その他の G1 適用

| 対象 | 変更 |
| --- | --- |
| E7 security 再チェック | `docs/release-process.md` §共通項目 (D5 で patch 適用に改めた後) に 1 行追加 + `/release` の Step 3 とタグ打ちの間に再チェック Step を挿入 |
| #870 triage 入力 | `docs/l2-workflow.md` §タスク発見 (L524-532) を拡張し、**4 系統** (open issues / 監査 spec の未起票表 / 直近 close issue の後継実在確認 / 番号を伴わない「別 issue」宣言の grep) を実行可能なコマンド付きで明文化。`docs/issue-policy.md` §7 から相互参照 |
| #865 AUDIO_FROZEN | 「凍結継続」を明文化する (D 該当なし、Idios 合意済み)。定義は `allaganeye/audio/__init__.py:48` の `AUDIO_FROZEN: Final[bool] = True` |
| #935 P2-3 | 手動ゲートの異常観測記録規約を `docs/l2-workflow.md` §実機検証 trigger 表 §結果記録 (L334-338) に追加する。**`docs/release-process.md` には置かない** — リリース 1 回に 1 度しか読まれず形骸化するため (issue 本文の原則と整合) |

### 5.2 G2: gate は存在するが scope が実物に届いていない (silent no-op)

#### 該当

E3 (`ci.yml` の branches filter が `release/*` を外す) / E4 (doc sweep の file set が仕様書に限定) / E6 (log は全文保存済みなのに読む規定がない) / #944 §5 案 (cli.py だけ見ると export / minimap を落とす) / #868 (paths filter に `pyproject.toml` がない) / #912 / #910 (doc→code 参照に検査なし) / #934 (schema の散文契約 7 件が未検査) / #920 (matrix v2 に 4 行欠落)

#### G2-0 (共通処方): gate を足す前に「この gate が見ていない集合」を列挙する

新設する検査は必ず、**検査対象外になる集合**を docstring と spec に明示列挙する。列挙できない検査は「網羅している」と誤読されるため入れない。以下 G2-1〜G2-5 はすべてこの形式で記述する。

#### G2-1: CI trigger の穴 (E3)

**D4 により、v0.3.1 では `develop-0.3.1` 直行とするため穴は構造的に消える** (`develop-*` が filter に含まれるので全 PR で full CI が走る)。そのうえで将来の minor release のために予防措置を入れる。

**ファイル**: `.github/workflows/ci.yml` (L13 `pull_request.branches`) / `.github/workflows/markdownlint.yml` (L5) / GitHub repository ruleset

**変更内容**:

1. `pull_request.branches` にのみ `release/*` を追加する。**`push.branches` は触らない**
2. main および `release/*` に required status checks を ruleset で宣言する (python / gui-frontend / gui-rust / installer-pester / markdownlint)。設定が repo 外にあるため、`docs/release-process.md` §共通項目 に「ruleset で強制済み」と追記して SSoT 化する

**二重起動の検証結果**: `pull_request.branches` のみに追加する限り**二重起動は発生しない**。`push.branches` にも足すと、`release/*` → main の PR は release ブランチの生存期間ずっと open なので、同一 commit に対し push run (`github.ref=refs/heads/release/vX`) と pull_request run (`github.ref=refs/pull/N/merge`) の 2 本が起動する。concurrency group は `ci-${{ github.workflow }}-${{ github.ref }}` (`ci.yml:18`) で ref を含むため**別 group となり dedupe されない**。windows runner を含む full CI が丸ごと 2 倍走る。

**この gate が見ていない集合 / false-green (必読)**:

- **v0.3.1 では 1 度も発火しない。** D4 により `release/*` base の PR が存在しないため、これは純粋な予防措置である
- red 実証には base=`release/*` の捨て PR を 1 本作るしかない。**Track C はこれを実施し、結果を PR 本文に記録する**
- required status checks を単独で入れると、`ci.yml` が起動しない限り check が never-reported のまま**マージ不能**になる。必ず 1 → 2 の順で入れる

#### G2-2: 機能告知 drift の検査 (E4 / #944)

**ファイル**: `scripts/check_feature_announcement.py` (新規) / `.github/workflows/ci.yml` (既存 `doc-tauri-commands-drift` L221 の直下に job 追加)

**変更内容**: `doc-tauri-commands-drift` と同形式の set-diff job。

- **SSoT** = CHANGELOG.md 最新 version の `### Added` 太字機能名 + CLAUDE.md §コマンド の `allaganeye <sub>` 行
- **CLI サブコマンドの正は typer runtime registry** (`typer.main.get_command(app).commands` を列挙し `hidden=True` を除外)
- **ターゲット** = `Format-ReadmeContent` の生成文字列 / `README.md` / `docs/quickstart.md`
- **exit code** = 1 (告知漏れ) / 2 (抽出不能)。抽出 0 件は **fail-closed で exit 2** (`check_version_consistency.py:9-16` の 1/2 分離を踏襲)

**#944 本文の読み替え (必須)**: issue #944 §5 は「コマンド一覧の正は `allaganeye/cli.py` の `@app.command` 登録とする」と書いているが、**この実装では今回漏れた 2 機能がちょうど検査対象外になる**。

- `cli.py` の `@app.command` は L65 / L292 / L480 の 3 つ (`split` / `detect` / `debug-brightness`) のみ
- `minimap` (`commands/minimap.py:46`) と `export` (`commands/export.py:69`) は `cli.py:650-656` の `register(app)` 経由

**この gate が見ていない集合 / false-green**:

- **キーワード 1 回出現 = 告知**とみなすため、README.md の索引リンクや折りたたみ内に `minimap` が 1 度出るだけで pass する。#944 が指摘した「導線が開発者欄と折りたたみ内にしかない」状態は**緑になる**
- **SSoT 側が人手書式依存**。CHANGELOG の太字にし忘れた機能は機能名集合から消えて検査が黙る (新機能ほど漏れやすい = 検査したい対象と穴が一致)
- **フラグ単位の機能** (`--masked` / `--vtuber` / `--keep-trailing`) は CLI サブコマンド粒度では原理的に捕まらない
- PowerShell here-string の静的抽出が壊れると照合対象 0 件 → exit 2 の fail-closed が無ければ「差分なし」で緑になる

#### G2-3: スクリーンショット陳腐化の検出 (E4 / #944)

**ファイル**: `scripts/check_screenshot_freshness.py` (新規) / `scripts/capture-readme-screens.mjs` の capture マップを JSON へ切り出し

**変更内容**: 各画像について **blob が最後に変化した commit の日時**と、対応する `gui/src/screens/<Screen>.tsx` + `.module.css` の最終変更日時を比較する。併せて `AppScreen` union (`gui/src/state/appStateStore.ts:12-18`) の要素数 / capture マップ件数 / README.md の「N つの観測フェーズ」の N の三者一致を検査する。

**false-green (必読)**: **素朴な `git log -1 --format=%ct` 比較は squash merge で全滅する。** 実測で `image/03-complete.png` の blob は `9544ebe` (2026-05-18) と `aefcb8c` (2026-08-04) で**同一** (`96d87e63980cca8caf17b411a1db654aadedcbca`) だが、commit timestamp 比較は 08-04 を返して緑になる。**blob hash の変化点を辿る実装が必須**である。

**この gate が見ていない集合**: 画面 tsx を触らない子コンポーネント側の変更 (例: `MatchThumb` へのバッジ追加) / 撮り直した画像が正しい画面・正しい状態を写しているか。

#### G2-4: Codex review 出力の保全 (E6)

**ファイル**: `.claude/skills/review-pr/SKILL.md` / `.claude/skills/iterate-review/SKILL.md` / `docs/l2-workflow.md` §Codex fallback (L872-893) / memory `project_codex_adversarial_review_direct_invocation`

**変更内容**: 新しい保存機構は作らない (既に全文が保存されているため)。

1. review 実行後に job log (`<CLAUDE_PLUGIN_DATA>/state/<slug>-<hash>/jobs/<jobId>.log`) を読む手順を skill step として追加する
2. `docs/l2-workflow.md:872-893` の擬似コードを `result.stdout` 依存から log 読みへ改訂する
3. `docs/l2-workflow.md:193` の「`--background` で非同期化可」を「review / adversarial-review は常に foreground blocking。非同期化フラグは受理されるが無視される (openai-codex 1.0.4 時点)」へ訂正する
4. memory `project_codex_adversarial_review_direct_invocation` の同じ誤りも訂正する

**この gate が見ていない集合 / 耐久性**: plugin 内部実装 (`state.mjs` の path 規約 / `tracked-jobs.mjs` の "Final output" ブロック名) への依存が発生し、plugin の version up で silent に壊れる。`state.mjs:13` の `MAX_JOBS = 50` による剪定で古い log が消える可能性があり、長期監査には向かない。version 併記で緩和する。

#### G2-5: その他の G2 適用

| 対象 | 変更 | この gate が見ていない集合 |
| --- | --- | --- |
| #868 | `security-audit.yml` の `pull_request.paths` (L5-11) に `pyproject.toml` (+ 導入するなら `constraints.txt`) を追加。**現在 Python manifest が 1 つも入っておらず、pyproject.toml だけを触る PR ではこの workflow が一切起動しない** — これが「Python 側の脆弱性検知が手動運用のみ」の実体 | 既定ブランチしか scan しないため release 期間中の状態は見ない |
| #912 / #910 | doc→code 参照 guard を **1 script / 1 job に統合**する (両者は同型。順序制約なし) | 参照先が存在することしか見ず、記述内容の正しさは見ない |
| #934 | `schemas/metadata.schema.json` の「JSON Schema で表現できない散文契約」7 件を機械検査化。#372 (close 済み) の解消状態を pin する場所でもある | 散文契約の棚卸しが人手なので、棚卸し漏れは構造的に検査外 |
| #920 / #933 | `docs/output-spec.md` matrix v2 (L88-113) に masked / vtuber 系 verbose 4 行を追加し、実装のガード条件と逐条突合 | 同一表を触るため #920 と #933 は直列化または 1 PR 統合が必須 |
| #876 | `ci.yml` の `installer-pester` job (L264-282) の Pester install に retry を入れる | **正常時は永久に不発。** red 実証手段 (存在しないモジュール名を流す等) を issue 側で指定しないと「retry を書いて緑」で終わる |

### 5.3 G3: SSoT の複製と参照切れ

#### 該当

対象: #913 (定数表が実装値を複製) / #933 (TSDoc 3 件・spec 3 件が実装から drift) / #922 (doc と workflow の不一致) / #923 (既に修正済みで close 漏れ) / #918 item2・item4 (dangling Step 1 参照 / 廃止済み手順の残存) / #856 (Round summary の語彙揺れ) / #916 (pin が doc・CI・ローカルで三重に乖離) / E5 (`/release` skill に CHANGELOG の語が 0 hit)

#### 共通処方

**機械可読な正を実装側に置き、doc は参照にする。** 既存の唯一の完成形は次の 3 点セットである。

1. `scripts/check_version_consistency.py` の `VERSION_LOCATIONS` (機械可読な正)
2. `tests/scripts/test_check_version_consistency.py:389` の doc parity テスト
3. 同 `:428` の発火 pin test

新規に doc / 実装の対応を作る場合はこの 3 点セットに揃える。

#### 個別

| # | 変更 | 備考 |
| --- | --- | --- |
| #913 | `docs/scorebar-detection-design.md` の定数表 2 つ (L69-73 / L109-117) を (a) 参照化 / (b) 現状維持 / (c) 仕様主張と実測記録に分類 のいずれかへ分類し、rationale 列のみ残して実装を正にする | issue 本文は突合先を `scorebar.py` と誤記している。実際の定数は `detector.py` 側 |
| #923 | **実装済み。再検証して close するだけ。** `docs/cli-spec.md:379` は PR #941 で、`export.py` の `--help` は commit `d35386c` (PR #924 に squash) で訂正済み | PR を持たない。本 release の最小コスト項目 |
| #922 | `docs/release-process.md:80` の workflow_dispatch 記述を実態に合わせるか、`release.yml` 側を doc に合わせるかを決めて実施 | 決定に依存して Track が B / C に分かれる |
| #918 | `/release SKILL.md` の 4 箇所 (develop ブランチ作成タイミング / dangling Step 1 参照 / バンプ方向チェック / 廃止済み手順) | `eval/requirements.md:18` の A-5 が**廃止済み手順を pin している**ため同時更新が必須 |
| #856 | 語彙統一 4 箇所 (Round summary / Codex fail fallback の優先順位 / `<version>` の実パス解決 / focus 文字列の矛盾) | **#935 と同一コードフェンス (`l2-workflow.md:171-185`) を触るため同一 PR か直列化が必須** |
| #933 | §A (npm audit 閾値) の採否判断 + §B の個別修正 | #944 §E とスコープが隣接 |

### 5.4 G4: 境界の外を見に行かない (台帳外・diff 外・mirror 元)

#### 該当

E2 (open-PR 集合を 2 回目にサンプリングしない) / E7 (変更していない依存に後発 advisory。dependency-review は base→head 差分しか見ない) / #870 (open issue 以外を triage 入力にしない) / #935 P2-2 (mirror 元の検証状況を見ない) / #934 (契約が実装にしか存在しない)

関連 memory: `feedback_mirroring_impl_copies_latent_bugs` / `feedback_grep_full_doc_before_section_add`

#### G4-1: Pre-flight 鮮度の機械検証 (E2)

**ファイル**: `.github/pull_request_template.md` (§ベース同期確認、L55 / L67) / `.github/scripts/check-preflight-freshness.js` (新規) / `.github/workflows/pr-checklist.yml` (新 job) / `docs/l2-workflow.md:208`

**設計制約 (最重要)**: **base OID 一致比較は本件を検出できない** (§3.3 E2)。実装が楽なため、この 1 行を落とすと実装者は OID 比較だけ入れて「対策済み」にする。

**変更内容**:

1. PR body に `- Pre-flight 時点の同 issue open PR: [#N,...] (または なし)` と `- Pre-flight 時点の同 base open PR: [#N,...]` の宣言フィールドを追加する
2. `pr-checklist.yml` の job が PR opened 時に `gh pr list --search "<Refs #issue>" --state open` と `gh pr list --base <baseRefName> --state open` を実行し、**集合差分**を取る。宣言に無い PR 番号が 1 件でもあれば fail
3. `docs/l2-workflow.md:208` の「plain bullet は CI ゲート増設なし」という規約文を同時改訂する (放置すると doc と CI が乖離する)

**配置先の制約**: `ci.yml` に置くと `pull_request: branches: [main, "develop-*"]` の filter で `release/*` base の PR (= #938 / #939 の track) では 1 job も起動せず**完全な no-op** になる。**必ず branch filter の無い `pr-checklist.yml` 側に置く** (同 workflow は `on: pull_request: types: [opened, edited, synchronize]` で branch filter を持たない)。

**この gate が見ていない集合 / false-green**:

- 宣言フィールドは自己申告なので「#938 も含めて宣言済み」と後から書けば緑になる。ただし宣言した時点で見落としでは無くなるので、握り潰しには PR body の改竄が必要 = **監査可能**
- `GITHUB_TOKEN` の権限や rate limit で `gh pr list` が落ちた場合、fail-open にすると常時 no-op、fail-closed にすると network 不調で全 PR がブロックされる。**fail-closed + 明示的な retry** を採る
- `Refs` 記法の揺れ (`Refs #862` / `#862` / issue 番号無しの release PR) で search key を取り違えると偽陽性・偽陰性の両方が出る

**hook 案を採らない理由**: `PreToolUse` で `gh pr create` を intercept する案には既知の穴が 4 経路ある — `ALLAGANEYE_PREUSE_BYPASS=1` prefix (`preuse.py:77`) / `settings.local.json` の `pretooluse_gate: false` / `tool_name != "Bash"` の無条件 allow (gh MCP / web UI / `gh api` POST 経由) / OID 比較の false-green。D2 (申告の機械検査) を採ったため hook は導入しない。

#### G4-2: 依存の境界外サンプリング (E7)

**ファイル**: `.claude/skills/release/SKILL.md` / `docs/release-process.md` §共通項目 / `.github/workflows/security-audit.yml`

**変更内容**:

1. **タグ打ち直前の security 再チェック gate** を `/release` の Step 3 とタグ打ちの間に挿入する。(a) `security-audit.yml` を `workflow_dispatch` でリリース PR HEAD に対し再実行 / (b) `docs/ci-security-audit.md:126-129` に既記載の `gh api repos/.../dependabot/alerts` を実行
2. `docs/release-process.md` §共通項目 (現在 security 項目ゼロ) にチェックボックスを 1 行追加し、Step 0a ゲートからも参照させる (D5 で patch 適用になったことが前提)
3. `security-audit.yml` に `schedule: cron` を追加する。現在 `grep -rn "schedule:|cron:" .github/workflows/` は**全 workflow 0 hit** で、`docs/ci-security-audit.md:117-121` が明記する構造的ギャップ 3 (「変更されていない既存依存に後から advisory が公開された場合、どの PR も fail しない」) を時間軸で埋める唯一の CI 内手段である

**headroom 検出器を作らない理由 (§3.3 E7)**: 「patched 最小ちょうど pin」の検出は本事象を防げず、かつ現在 3 件とも headroom ゼロで上げ先が存在しないため、fail 型にすると導入初日から恒久 red になる。**本 release では作らない。**

**この gate が見ていない集合**:

- 再チェックが緑でも、その後タグ push までの窓は 0 にできない (本件の実測窓は advisory 公開からタグまで**約 7 時間**)
- Dependabot alert 経路は既定ブランチ (`main`) しか scan しないため、release 期間中は stale な状態を読む
- cron 間隔以内でしか検知できない (daily なら最悪 24h 遅延)

**未解決の前提確認**: `gh api "repos/Idios/kobutachan-allaganeye/dependabot/alerts?state=all&per_page=100"` は HTTP 200 + 空配列を返した (403 ではない)。トークンに `security_events` scope が無いのか、release merge 後に全件 close されたのかを**実装前に切り分ける**こと (§8 オープン点)。

### 5.5 R1: 依存 pin 判断表 (横断レジスタ)

対象: #916 / #863 / #907 を**単一 PR**で決着させる (Idios 合意済み)。

| 対象 | 現状 | 裁定 |
| --- | --- | --- |
| `opencv-python-headless` | `>=4.8` (上限なし)。ローカル 4.13.0.92 / CI と出荷物は 5.x に解決 | **`>=4.8,<5` に固定** (D8)。実機検証・baseline 再取得が不要になり 3 者が一致する。5.x 移行は別 issue |
| `typer` / `click` | `>=0.9,<0.25` / `>=8.0,<8.4` (#863 の暫定 pin) | upstream の解消を確認し、未解消なら `pyproject.toml:11-16` のコメントを「暫定」から**恒久方針**へ書き換える |
| `ruff` / `pyright` | `>=0.4` / `>=1.1` (上限なし)。**pyright はローカル venv に未 install = ローカルの型検査が存在しない** | 上限を付ける。`docs/developer-setup.md:205` に再 install 手順を追記する。markdownlint が既に同型を解いている (`scripts/check-markdownlint.sh:22` の `CLI2_VERSION`) |
| `rich` / `datamodel-code-generator` / `black` / `isort` | 宣言そのものが無い (transitive) | 明示宣言 + 上限。codegen gate (`ci.yml:71-79`) が 3 者の整形出力に依存しているため、固定すれば ping-pong が構造的に止まる |
| constraints 方式 | 未導入 | `constraints.txt` を新設し `ci.yml:69` / `:106` の `pip install -e ".[dev]"` を `-c constraints.txt` 付きへ。`cache-dependency-path` (L29-30 / L101-102) にも追加 |
| 配布 build | `build-portable-zip.ps1:473` の `pip install $RepoRoot --no-cache-dir` は**完全に未固定** | constraints を効かせるかを判断する。効かせないと「CI が検証した cv2」と「ZIP に同梱される cv2」が別物という **#916 と同型の穴が配布側に残る** |

**直列制約 (最重要)**: **`ruff` / `pyright` の pin だけは Track 0 直後に単独で先行させる** (§6.2 の Track A′)。pin が動くと `ruff format --check .` の結果が repo 全体で変わり、並列中の Track B / C の PR が rebase で一斉に赤化する (memory `feedback_ruff_version_drift_md_codeblocks` / `feedback_ruff_format_whole_repo_gate`)。

### 5.6 R2: 実機・長時間検証スロット (横断レジスタ)

Idios の実機は 1 台なので、**Track が違っても物理的に直列**である。Track 表とは別にスロットを管理する。

| # | 検証内容 | 制約 |
| --- | --- | --- |
| #864 | `detector.py` の legacy fps filter path 撤去 → detect baseline gate | **他の `detector.py` / `gpu_detector.py` 変更 PR と並列させない** (baseline gate の帰属が曖昧になる)。他 Track が落ち着いてから着手し 1 回でまとめて回す |
| #652 | verbose split の pipe 経由クラッシュ修正 → CLI 実行確認 | 短時間。#864 と同一スロットに載せられる |
| #944 | GUI スクリーンショット撮り直し (`capture-readme-screens.mjs` = vite dev + Playwright + sample metadata) | memory `project_gui_verification_cache_seed` の cache seed 手法で短縮可能 |
| #882 | 検証データ第 3 系統 | **物理作業は Idios 本人** (ハード選定・購入・コピー)。agent 側は台帳 (`tests/baselines/source-videos.sha256.json`、48 file / 632.1 GiB) の照合と doc 更新のみ |

**#916 は D8 (cv2 4.x 固定) により実機検証が不要になった** ため、本表から外れる。

長時間 GPU job は memory `feedback_long_gpu_job_detached_execution` に従い `Start-Process -WindowStyle Hidden` で独立起動する (harness の background Bash はセッション死と共に kill される)。

## 6. 実装 Track (設計判断)

> **割り付けの正 (SSoT) は [実装計画](../plans/2026-08-05-v031-track-decomposition.md) の PR 表である。本節は issue → Track / PR の割り付けを一切持たない。**
>
> 初版は本節に Track ごとの issue 一覧を持っていたが、Codex adversarial-review が **3 ラウンド連続で「spec と plan の割り付けが同期していない」という同一クラスの finding** を出した。Round 2 で「参照用の派生ビュー」として縮小したが、その縮小版がさらに虚偽の coverage 記述を生んだ (Round 3)。部分的に残す試みが同一セッション中に 3 回とも drift したため、§5.3 G3「SSoT の複製と参照切れ」の処方 (機械可読な正を 1 箇所に置き、他方は参照にする) を本 spec 自身に全面適用し、割り付け情報を撤去した。
>
> 撤去した内容の行き先 — Track / PR 割り付けと事象→issue 対応、同一ファイルを触る組、Track D の作業内容、並列度の上限は、すべて plan が持つ。

### 6.1 Track 0 を裁定のみに限定する理由

`docs/release-process.md:227` は Track 0 を「spec PR / 直列 (最初)」と定義し、前例 (v0.2.1 Track 0) も「4 Lane / 約 14 PR に分解する形で提案する」と決定と分解のみを行っている。

**Track 0 に実装を積むと、直列最初の PR で Track A / B / C の着手が全部待たされ、Track 構造の目的そのものが潰れる。** したがって #935 (effort L) / #936 / #870 / #856 の**実編集は後続 Track へ移す** (どの Track / PR かは [実装計画](../plans/2026-08-05-v031-track-decomposition.md) が持つ)。Track 0 の成果物は本 spec と実装計画、および D10 / D8 に基づく issue 起票のみとする。

### 6.2 Track 構造

base は全 Track `develop-0.3.1` (D4)。Track の意味づけは [`docs/release-process.md` §Patch release の Track 構造](../../release-process.md#patch-release-の-track-構造) に従い、D3 で「変更の性質で既存 4 Track に分配」と確定した。

| Track | 並列性 | 内容 |
| --- | --- | --- |
| **0** | 直列 (最初) | 本 spec + 実装計画 + Track 0 で必要な issue 起票 |
| **A′** | 直列 (Track 0 直後) | lint ツールの pin 先行 |
| **A** | 並列可 | 依存 pin 本体 (constraints 方針、cv2 4.x 固定、typer / click 恒久化) |
| **B** | 並列可 | doc / コード小修正 / skill 文言 |
| **C** | 並列可 | CI / gate |
| **D** | 直列 (最後) | version bump + CHANGELOG 確定 |

**A′ を新設した理由**: lint ツールの版が変わると `ruff format --check .` の結果が repo 全体で変わる。Track B / C を並列で走らせている最中に pin を変えると、先行 PR が rebase 時に一斉に赤化する (memory `feedback_ruff_version_drift_md_codeblocks` / `feedback_ruff_format_whole_repo_gate`)。既存の Track A に含めると並列扱いになるため、直列 slot として切り出した。

**どの issue がどの Track / PR に属するかは [実装計画](../plans/2026-08-05-v031-track-decomposition.md) を参照。** 同一ファイルを触る組の直列化、Track D の作業内容 (6 ファイル 7 フィールド)、実機スロット表、並列度の上限も plan 側にある。

## 7. 受け入れ基準 (全体)

### 7.1 リリース判定

- [ ] `/release` Step 0a の受け入れゲートが全項目「達成」 (D5 で patch 適用に改めた後の §共通項目)
- [ ] 吸収 27 件がすべて close されている、または close できない理由が本 spec §8 に記録されている
- [ ] Track D の version 7 フィールドが `check_version_consistency.py` で exit 0
- [ ] CHANGELOG `## [0.3.1] - YYYY-MM-DD` の日付がタグ打ち日 (JST) と一致し、G1-3 のガードが exit 0

### 7.2 機構の発火実証 (G1-1 の 3 点セット③)

**「導入したが 1 度も赤を出していない」機構をリリース前に洗い出す。** 各項目は違反を一時注入して exit code の生値で観測する。

- [ ] **G1-2 Fable**: Self-Test Report の Fable 欄を未記入にして `validate-checklist` が red になることを確認
- [ ] **G1-3 CHANGELOG 日付**: 偽の日付で非ゼロ exit + JST 深夜値で false-red が出ないことの両方を確認
- [ ] **G1-4 Self-Test Report**: `- [ ]` を 1 件残して red、Iron Law 1/3/4 群に残しても green (D9 の範囲固定)
- [ ] **G2-1 CI trigger**: base=`release/*` の捨て PR を 1 本作り、`ci.yml` が起動することを確認 (**v0.3.1 本体では発火しないため、これが唯一の red 実証手段**)
- [ ] **G2-2 機能告知**: SSoT から機能名を 1 件抜いて exit 1、抽出を壊して exit 2 を確認
- [ ] **G2-3 スクショ陳腐化**: blob 同一・commit 日時のみ新しいケースで**赤になる**ことを確認 (squash merge の false-green を潰した証拠)
- [ ] **G2-5 #876**: 存在しないモジュール名を流して retry が発火することを確認
- [ ] **G4-1 Pre-flight 鮮度**: 宣言に無い open PR を作って fail することを確認

### 7.3 SSoT 整合

- [ ] `grep -rn "fable-consult" CLAUDE.md .claude/` の全 hit が `allaganeye-fable-consult` を指す (旧名 0 件)。**scope は living doc のみ** — `docs/l2-workflow.md:199` (#854 R2 確定) が「実行済み dated plans/specs 内の表記は historical record であり遡及書き換えを行わない。living doc = CLAUDE.md / l2-workflow / skill / hook / 現行 roadmap のみが整合対象」と定めているため、`docs/superpowers/plans/` `docs/superpowers/specs/` 配下は対象外とする。routing spec §8 の命名前提だけは事実として誤りになるので、書き換えではなく「本条項は 2026-08-05 spec G1-2 で消化済み」の 1 行注記を添える
- [ ] `docs/release-process.md` の Track B 定義が「deferred 吸収」になっている (D3)
- [ ] `docs/l2-workflow.md:193` の `--background` 記述が訂正されている (E6)
- [ ] `docs/l2-workflow.md:208` の「CI ゲート増設なし」が G4-1 の実装と整合している

## 8. リスクとオープン点

### 8.1 リスク

| # | リスク | 緩和 |
| --- | --- | --- |
| R-1 | **G2-1 が v0.3.1 中に 1 度も発火しない** (D4 の帰結) | §7.2 で捨て PR による red 実証を必須化 |
| R-2 | **G1-3 の TZ バグがリリース当日に Track D を止める** | Track C 実装時に JST 深夜値の pin test を同梱。過去 4 タグ中 2 件が該当する実データを test fixture にする |
| R-3 | **A′ の pin 先行を怠ると Track B / C が rebase で一斉赤化** | §6.2 で A′ を独立 Track として定義し、理由を明記 |
| R-4 | **Self-Test Report 10 box × PR 本数の運用負荷** | 27 issue → 想定 10-15 PR。埋める手間が形骸化を招くなら D9 の範囲をさらに絞る |
| R-5 | **skill 改修 3 件が同一ファイルで衝突** | 同一ファイルを触る組の対処は [実装計画](../plans/2026-08-05-v031-track-decomposition.md) を参照。#935 × #856 は同一 PR を第一候補にする |
| R-6 | **#882 が Idios の物理作業待ちで release をブロックしうる** | agent 側の作業 (台帳照合 + doc 更新) と物理作業を分離し、物理作業は release 判定から外す |

### 8.2 オープン点 (実装前に決着が必要)

| # | 内容 | 決着方法 |
| --- | --- | --- |
| O-1 | `dependabot/alerts` API が空配列を返す理由 (token scope か、全件 close か) | `security_events` scope 付きトークンで再取得。**G4-2 の案 2 がこの API に依拠するため実装前に必須** |
| O-2 | `.github/dependabot.yml` (version updates) を導入するか | #868 の判断。security updates 経路は稼働しており PR が自動生成される (#758 は merged、#831 は生成されたが未 merge のまま stale 化し 2026-08-05 に superseded として close)。未導入なのは定期 bump のみ。**#831 が 50 日間 open のまま放置された事実は「PR は来るが消化されない」ことを示すので、version updates を有効化する判断材料に含める**。見送る場合は根拠と手動 bump 周期を `docs/ci-security-audit.md` に明文化 |
| O-3 | #922 を doc 修正で解くか `release.yml` 修正で解くか | 決定に依存して Track が B / C に分かれる |
| O-4 | 配布 build (`build-portable-zip.ps1:473`) に constraints を効かせるか | 効かせないと出荷物の cv2 が未固定のまま残る (R1 表) |
| O-5 | JST 深夜帯 (00:00-09:00 JST) にタグを打つ運用を許容するか | 許容するなら G1-3 は `Asia/Tokyo` 固定で足りる。禁止するなら規約に 1 行足して検査を単純化できる |
| O-6 | `annotated tag object` の `taggerdate` が `version-check` job の checkout 後に読めるか (`actions/checkout@v4` は既定 `fetch-depth: 1`) | 実 CI で試すしかない。読めない場合は `github.event.head_commit.timestamp` が唯一の基準日になる |
| O-7 | `.claude/skills/release/eval/requirements.md:24` のシナリオ B が「patch release v0.3.1、deferred 5 件」を前提にしている (実際は 64 件) | #918 の PR で eval も同時更新する。しないと次の EPT で旧前提が復活する |

### 8.3 本 spec が意図的に扱わないもの

- **headroom 検出器** (§3.3 E7 / §5.4 G4-2) — 本事象を防げず、現状 3 件とも headroom ゼロで恒久 red になるため
- **`PreToolUse` hook による `gh pr create` gate** (§5.4 G4-1) — 既知の bypass が 4 経路あり、D2 の申告検査で代替する
- **merge queue** — 守るのは main への最終マージであり、今回の gap (中間 PR) には無関係

## 9. §deferred 全件検証結果 (`/release` Step 0c)

open 65 件 + 前セッションで close 済み 2 件 = **67 行**。(a) 27 件 / (b) 38 件 / (c) 2 件。

本 table は `/release` Step 0c を実施した時点 (2026-08-05、本 spec 作成前) の open issue 集合が対象である。**その後 Track 0 で起票した 9 件 (#945-#953) は本 table に含まれない** — 行き先は [実装計画](../plans/2026-08-05-v031-track-decomposition.md) が持つ (#945-#950 と #952 は v0.3.1 で作業、#951 と #953 は deferred)。

### 9.1 (a) v0.3.1 で吸収 — 27 件

| issue # | title | 分類 | 判断理由 |
| --- | --- | --- | --- |
| #326 | ハイブリッド skill 方式を idios-claudecode-tools テンプレートに反映 | (a) 吸収 | 本 repo に作業なし。別 repo へ転記し close (D12) |
| #376 | トップレベル CLI に -v をバージョン表示エイリアスとして追加 | (a) 吸収 | 軽微。トップレベル parser 限定で実装 (サブコマンドの `-v` = verbose と衝突しない形) |
| #652 | verbose split を pipe 経由で実行すると progressbar が OSError 22 でクラッシュ | (a) 吸収 | 原因既知の小修正。実機 CLI 確認あり |
| #658 | subprocess.run(text=True) encoding 漏れの AST regression test 追加 | (a) 吸収 | `tests/test_ascii_guard.py` を雛形に新設 |
| #856 | skill/workflow doc の細部文言明確化 (EPT #854 残 unclear 3 点) | (a) 吸収 | 語彙統一 4 箇所。EPT skip (D11)。#935 と同一 PR |
| #863 | typer<0.25 / click<8.4 pin の恒久対応 | (a) 吸収 | #916 に統合し単一 PR で決着 |
| #864 | detect legacy fps filter path の撤去 (v0.3.x) | (a) 吸収 | 実機 baseline gate 必要 (R2)。他 detector 変更と並列させない |
| #865 | AUDIO_FROZEN の決着 (解凍 or Q3 撤去) | (a) 吸収 | 「凍結継続」を明文化する方向で決着 (Idios 合意済み) |
| #868 | pip-audit CI + dependabot 導入の決着 | (a) 吸収 | `security-audit.yml` の paths に pyproject.toml が無いのが本当の穴 (G2-5) |
| #870 | roadmap triage 入力ルールの規約化 (台帳外残タスク) | (a) 吸収 | 4 系統を `docs/l2-workflow.md` §タスク発見 に明文化 (G1-5)。#944 がその実例 |
| #876 | installer-pester の PSGallery flaky 対策 | (a) 吸収 | retry 追加。**red 実証手段を issue 側で指定必須** (正常時は永久に不発) |
| #882 | 検証データ保全の恒久策 (第 3 系統) 追加 | (a) 吸収 | 物理作業は Idios。agent 側は台帳照合と doc 更新のみ (R2) |
| #906 | cache corruption warning に cache_path を復元 | (a) 吸収 | `split_matches.py:2251` に `cache_path` 引数を追加する小修正 |
| #907 | lint ツール (ruff / pyright) のバージョン pin | (a) 吸収 | **他のすべてに先行して単独でマージする** (R1 の直列制約。pin が動くと `ruff format --check .` の結果が repo 全体で変わり、並列中の PR が rebase で一斉赤化する) |
| #910 | ui-interaction-spec.md の行番号 anchor を名前参照へ移行 | (a) 吸収 | **AC-1 は PR #932 で完了済み。**残りは参照 guard の CI 化。#912 と 1 job に統合 |
| #912 | system-architecture §2.3 の GUI→CLI 網羅宣言に enforcement がない | (a) 吸収 | #910 と同型。1 script / 1 job に統合 |
| #913 | scorebar-detection-design の定数表が実装値を複製している | (a) 吸収 | rationale 列のみ残し実装を正に (G3) |
| #916 | 未 pin 依存の version drift を封じる (constraints 方針の確定) | (a) 吸収 | cv2 4.x 固定 (D8) により実機検証不要。#863 / #907 を統合 |
| #918 | /release skill の手順記述 3 件 | (a) 吸収 | `check_version_consistency.py:268` の `args.tag` 分岐を #948 と共有するため **#948 と同一 PR に統合**する (plan 参照)。`eval/requirements.md:18` の A-5 が廃止済み手順を pin しているため同時更新必須。EPT 適用 (D11) |
| #920 | output-spec マトリクスに masked / vtuber 系 verbose 出力 4 行が欠落 | (a) 吸収 | #933 と同一表。直列化または 1 PR |
| #922 | release-process の workflow_dispatch 記述が実態と不一致 | (a) 吸収 | 決定に依存 (O-3) |
| #923 | cli-spec の `export --concurrency` が「上書き」と書かれている | (a) 吸収 | **既に修正済み** (PR #941 + `d35386c`)。再検証して close するだけ (`/close-issue`) |
| #933 | v0.3.0 doc 監査でスコープ外に置いた項目 (9 件) | (a) 吸収 | §A の npm audit 閾値判断 + §B の個別修正 |
| #934 | path/schema 契約の機械検査化 | (a) 吸収 | 散文契約 7 件を機械検査化。#372 の解消状態を pin する場所 |
| #935 | レビュー・ゲート規約の見直し 5 件 | (a) 吸収 | 5 箇所編集。EPT 適用 (D11)。#856 と同一 PR |
| #936 | Self-Test Report は CI 強制されていない | (a) 吸収 | (a) checker scope 拡大で決着 (D2 / D9)。3 点セットで初めて発火 (G1-4) |
| #944 | v0.3.0 機能が入口 doc・同梱 README・GUI 文言に未反映 | (a) 吸収 | **本 release の最優先項目。**出荷物 2 件 + 再発防止 CI (G2-2 / G2-3)。GUI は「発見できること」までが範囲 |

### 9.2 (b) deferred 継続 — 38 件

前セッションで Idios が 9 ラウンドに分けて 1 件ずつ確認済み。

| issue # | title | 分類 | 判断理由 |
| --- | --- | --- | --- |
| #28 | L7: --precise フラグ (再エンコード分割モード) の追加 | (b) 継続 | L7 (計画中レイヤー)。機能追加 |
| #32 | Windows/Linux クロスプラットフォームテスト基盤の構築 | (b) 継続 | Windows-only 方針 (#451) のため優先度低 |
| #63 | L7: プレイヤー名ぼかし機能の検討・実装 | (b) 継続 | L7 (計画中レイヤー) |
| #125 | L4: Tesseract OCR によるキルログ抽出 | (b) 継続 | L4 未着手レイヤー |
| #126 | L4: Whisper による音声認識・SE 検出 | (b) 継続 | L4 未着手レイヤー |
| #127 | L4: イベントデータ出力フォーマットの設計 | (b) 継続 | L4 未着手レイヤー |
| #128 | L4: OCR 精度 — ゲーム独自フォントの認識リスク | (b) 継続 | L4 未着手レイヤー (risk) |
| #129 | L4: Whisper ローカル実行の処理時間・リソース消費 | (b) 継続 | L4 未着手レイヤー (risk) |
| #130 | L4: 外部依存の追加と環境構築手順の整備 | (b) 継続 | L4 未着手レイヤー |
| #131 | L5 [LLM拡張]: LLM プラグインアーキテクチャの設計 | (b) 継続 | L5 未着手レイヤー |
| #132 | L5 [LLM拡張]: 投稿価値の評価基準定義 | (b) 継続 | L5 未着手レイヤー |
| #133 | L5 [LLM拡張]: API コスト管理 | (b) 継続 | L5 未着手レイヤー (risk) |
| #134 | L5 [LLM拡張]: API キー管理とセキュリティ | (b) 継続 | L5 未着手レイヤー |
| #135 | L6: ハイライトクリップ自動切り出し | (b) 継続 | L6 未着手レイヤー |
| #136 | L6: サムネイル自動生成 | (b) 継続 | L6 未着手レイヤー |
| #137 | L6: 投稿提案の出力設計 | (b) 継続 | L6 未着手レイヤー |
| #139 | L4-L6 の end-to-end パイプライン設計 | (b) 継続 | L4-L6 未着手レイヤー (question) |
| #140 | L4-L6: 全体処理時間の見積もりとユーザー体験 | (b) 継続 | L4-L6 未着手レイヤー (risk) |
| #150 | L4: openai-whisper の PyTorch 依存によるインストールサイズ肥大化 | (b) 継続 | L4 未着手レイヤー (risk) |
| #151 | L4: OBS 録画に音声トラックが存在しない場合の処理 | (b) 継続 | L4 未着手レイヤー (risk) |
| #152 | L4: Tesseract 日本語言語パックの別途インストール要件 | (b) 継続 | L4 未着手レイヤー (risk) |
| #373 | metadata.json に末尾打ち切り情報を残す | (b) 継続 | #805 で post_match 非破壊化が入り前提が変化。再評価が要る |
| #412 | PR #323 refinement 残存長 segment の warning を機械的に追跡する | (b) 継続 | L1 residual。検出系の継続開発と併せて扱う |
| #432 | 他プロセス使用中による Permission denied 系問題の全体見直し | (b) 継続 | 全体見直しは patch scope 外 |
| #479 | ユーザー要望: Twitch アーカイブ URL からの試合分割取り込み | (b) 継続 | 機能追加。v0.3.1 非範囲 |
| #480 | L3: VTuber scorebar 局在化(P1) + ROI 適応分類(P4) | (b) 継続 | L3 検出系の継続開発 |
| #518 | note -> warnings: Warning[] 構造化 (将来検討) | (b) 継続 | 将来検討 (question) |
| #670 | L3: GUI 動画 HTTP server 改善 (responsiveness) | (b) 継続 | v0.3.0 外と明示済み (#670) |
| #671 | L2a: E2E test 自動化 feasibility 検討 | (b) 継続 | feasibility 検討段階 |
| #742 | 5 spawn site を tauri-plugin-shell::Command に移行 | (b) 継続 | refactor。patch scope 外 |
| #753 | L3: VTuber + minimap キックオフ (parent issue) | (b) 継続 | L3 parent。子 issue の進行に従う |
| #809 | L3: Pass 1 暗転検知の game 領域輝度適応 | (b) 継続 | L3 検出系の継続開発 |
| #861 | L3: QSV/AMF decode hwaccel の扱い確定 | (b) 継続 | 実機検証が要る L3 項目 |
| #866 | L3: two-signal 再アーキ Phase 3-4 (VTuber 検証+cutover) 追跡 | (b) 継続 | L3 検出系の継続開発 |
| #867 | L3: #809 audit 追記 AC 残 2 点の移設 | (b) 継続 | #809 に従属 |
| #921 | --vtuber: 試合間 gap 約 70 秒未満での結合を解消する | (b) 継続 | L3 検出系の継続開発 |
| #925 | masked 録画の baseline 回帰ゲートを追加 | (b) 継続 | L3 検出系。実機 GT が要る |
| #937 | export/minimap 出力パスの同一性判定に残る 4 経路 | (b) 継続 | hardlink / 8.3 / macOS / 予約デバイス名。#934 の機械検査化が先 |

### 9.3 (c) close — 2 件

| issue # | title | 分類 | 判断理由 |
| --- | --- | --- | --- |
| #372 | metadata.json と cache の source パス形式を統一する | (c) close | 解消済み (COMPLETED)。前セッションで close。解消状態の pin は #934 が担う |
| #765 | detect の NVDEC saturation 実機計測結果 (記録) | (c) close | 記録目的を達成 (COMPLETED)。前セッションで close |

## 10. 関連リンク

- [`docs/release-process.md` §Patch release の Track 構造](../../release-process.md#patch-release-の-track-構造)
- [`.claude/skills/release/SKILL.md`](../../../.claude/skills/release/SKILL.md) §Step 0c
- [`docs/l2-workflow.md`](../../l2-workflow.md) §PR 作成 Pre-flight / §Self-Test Report 規約 / §Codex fallback
- [2026-05-17-v020-v021-retro-codex-integration-design.md](2026-05-17-v020-v021-retro-codex-integration-design.md) — v0.2.1 Track 0 (前例)
- [2026-07-14-per-use-case-model-routing-design.md](2026-07-14-per-use-case-model-routing-design.md) — §8 retrospective 条項の消化元
- [`docs/ci-security-audit.md`](../../ci-security-audit.md) — 構造的ギャップ 3 (E7 / G4-2 の根拠)
- [`docs/refactor-pattern.md`](../../refactor-pattern.md) — Phase 分割の判定基準
