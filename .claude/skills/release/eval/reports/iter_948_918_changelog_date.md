# release empirical-prompt-tuning (#948 CHANGELOG 見出し日付 + #918 手順記述 3 件)

mizchi protocol: <https://github.com/mizchi/skills/tree/main/meta/empirical-prompt-tuning> §ワークフロー 4 両面評価。
fresh subagent (`general-purpose`, `model: sonnet`) を iteration ごとに新規 dispatch (同一 agent の再利用は empirical Red Flag)。

## 変更概要

- **Step 4 新設** (#948): タグ打ち直前に CHANGELOG 見出し日付を当日 (JST) へ更新し、`--changelog-date-from` 付きで検査してから commit する
- **Step 2-4 の分岐元 / PR 宛先 分離** (#918 item1 の延長): 同一変数で書かれていた 2 つの役割を表で分離
- **Step 3-6 の dangling "Step 1" 参照解消** (#918 item2)
- **`gh release create --notes-from-tag` の廃止済み手順を訂正** (#918 item4)
- **Step 0a に patch release の fallback 追加** (D5 の帰結)
- **frontmatter description の更新** (Iteration 0 で検出)
- `eval/requirements.md`: A-5 を `--list-paths` ベースへ置換、シナリオ B を実測 67 件へ訂正、A-9 / A-10 / B-10 / C-7 追加

## Iteration 0 (静的、description / body 整合チェック)

**検出**: frontmatter `description` が「deferred issue レビュー → バージョンバンプ → リリース PR 作成」で、body が新たに持った **CHANGELOG 見出し日付確定 (Step 4)** を含んでいなかった。

protocol の警告どおり、これを放置すると executor が body を description に合わせて読み替え、Step 4 を飛ばしたまま accuracy だけ高く出る (false positive)。iteration 1 の前に description を更新して解消。

## Iteration table

| iter | 変更 | scenario A | scenario B | scenario C | 新規不明瞭点 (in-scope) |
| --- | --- | --- | --- | --- | --- |
| 1 | Step 4 新設 + #918 item1/2/4 + description 更新 | ○ 8/8 [critical] (tool_uses 10 / 390s) | ○ 9/9 (11 / 116s) | ○ 6/6 (6 / 198s) | **4 件**: Step 4 の commit 先未定義 (A・C が独立に報告) / 分岐元と PR 宛先の混同 (A) / patch にレイヤー固有ブロックが無い場合の扱い (B) |
| 2 | iter1 の 4 件を反映 + A-9 / A-10 / B-10 / C-7 を新設 | ○ **10/10** (9 / 212s) | ○ **10/10** (13 / 376s) | ○ **7/7** (13 / 256s) | **1 件**: Step 4 の説明文が `main` を名指し (patch の 2-hop で不正確) — C が報告 |
| 3 | iter2 の 1 件を反映 (宛先を Step 2-4 の表へ委譲) | ○ **10/10** (9 / 313s) | — | ○ **7/7** (12 / 354s) | **1 件**: `eval/requirements.md` A-3 に残っていた "Step 1" 参照 (C が報告、#918 item2 の取りこぼし) |

- **成功判定**: 全 iteration・全 scenario で `[critical]` 全項目 ○ = 成功 (○)。accuracy は iter2 以降 1.00
- **A-9 / A-10 / B-10 / C-7 は iteration 1 の findings を受けて iteration 2 の前に追加**した項目。既存 `[critical]` の増減はしていない (「合格しやすくする方向へ動かさない」という protocol の趣旨に照らし、新規発見の欠陥を足すのは可)。iter1 と iter2 の accuracy を直接比較しない
- `tool_uses` は 6-13 の範囲に収まり、scenario 間の 3-5x 級の偏り (自己完結性の低さの兆候) は無し

## 構造化 reflection (iteration をまたいで潰した点)

- **Issue**: Step 4 の `git commit` に載せ先の記載が無く、`main` が保護ブランチである事実と衝突する / **Cause**: 周囲の step が全て PR 経由なのに Step 4 だけ commit を裸で書いた / **General Fix Rule**: **保護ブランチ境界の近くで直接 commit を指示する step は、対象ブランチを明示し repo の保護規則との整合を述べる**。沈黙を「レビュー省略可」と読ませない → `release/vX.Y.Z` (リリース PR head) へ載せること + Step 4 はマージ前に実行することを明記
- **Issue**: 分岐元 (`release/v0.3.0` を切る元) と PR 宛先 (`--base`) が同じ「ベースブランチ」という 1 語で書かれ、`--base develop-0.3.0` になりうる / **Cause**: 構造的に別の役割へ同じ変数名を再利用した / **General Fix Rule**: **1 つの変数が複数 step で構造的に異なる役割に使われるなら、各使用箇所で役割を再宣言するか、役割ごとに別名を与える** → 表で 2 列に分離し、実例 (PR #924 = head `release/v0.3.0` / base `main`) を添えた
- **Issue**: patch release には対応するレイヤー固有ゲートブロックが存在しないのに、Step 0a は「2 ブロック提示」と無条件に書いていた / **Cause**: D5 で §共通項目 を patch へ広げた結果あらわになった穴 / **General Fix Rule**: **固定 N ブロック構造を前提にする step は、名前付きブロックが当該リリース種別に存在しない場合の fallback を明記する** → 「§共通項目 のみ提示 + 該当なしと明示」を追加
- **Issue**: Step 4 の説明文が「同じ PR に乗って `main` へ渡る」と書いていたが、patch で `develop-<新バージョン>` を経由する場合は宛先が違う / **Cause**: 説明文を minor の 1-hop 前提で書き、同一 skill の Step 2-4 の表 (2-hop を定義済み) と再突合しなかった / **General Fix Rule**: **説明文が特定のブランチ名を名指しするときは、先行 step の決定表を正として「実際の PR 宛先」という言い方に書き換える** → 宛先を Step 2-4 の表へ委譲
- **Issue**: `eval/requirements.md` A-3 が存在しない "Step 1" を参照していた / **Cause**: skill 側の改番を eval 側へ伝播していなかった (#918 item2 と同型の取りこぼし) / **General Fix Rule**: **skill の step 番号を変えたら、その skill の `eval/*.md` を旧番号で grep する**

## Codex Pre-flight findings との関係

EPT とは別に Iron Law 6 Pre-flight Step 5 の Codex adversarial-review を 3 round 実施し、計 4 件 (high 1 / medium 3) を消化した。EPT が拾ったのは**手順記述の曖昧さ**、Codex が拾ったのは**コードの failure scenario** で、重複はゼロだった。両者は別レイヤーとして併存させる価値がある (CLAUDE.md §Fable と Codex の棲み分け と同趣旨)。

## 収束判定

**iteration 2 と iteration 3 の 2 回連続で、全 scenario の `[critical]` が全件 ○** (2 consecutive clears)。iteration 3 で残った 1 件は eval doc の参照ズレで、手順そのものの構造的欠陥ではない (同 iteration 内で修正済み)。

構造的欠陥 (新 step の載せ先未定義 / 分岐先の取り違え / patch fallback 不在) はすべて解消したため、mizchi 収束条件「構造的欠陥が解消された時点での打ち切り可」にも合致する。

## 残った細部不明瞭点 (deferred、本 PR スコープ外)

いずれも **#948 / #918 の変更に由来しない pre-existing の papercut**。executor は自力で正しく解決しており `[critical]` を落としていないため、[#962](https://github.com/Idios/kobutachan-allaganeye/issues/962) で追跡する (2026-08-08 Idios 判断で別 issue 起票)。

1. **Step 3 の実行順序**: 3-2 (ファイル編集) が 3-3 (ブランチ作成) より前に並んでおり、字面どおりだと dirty tree のまま `git pull` する
2. **Step 0c-2 の `<前タグ>` プレースホルダ**に解決コマンドが添えられていない (Step 2-2 の `git describe --tags --abbrev=0` と重複定義)
3. **Step 0a の bulk pre-check** のサンプル件数・選び方が未規定 (Step 0c 側にしか詳細が無い)
4. **Step 0a の項目 1/3/4** は Step 2/3 が生む成果物を参照するため、Track 構造の patch release では再評価点が不明
5. **Step 0c-2 の「確認する」の相互作用手段** (AskUserQuestion か否か) が未規定
6. **patch の 2-hop** (`release/vX.Y.Z → develop-x.x.x → main`) が明示 step になっておらず、hop 1 マージ後 hop 2 前に日付ドリフトを見つけた場合の手順が無い
7. `release.yml` の非同期完了を待たずに `develop-<次>` を切りうる (確認コマンドが無い)
